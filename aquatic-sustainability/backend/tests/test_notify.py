import json
from pathlib import Path

from app.notify import persist_log, reset_logs

PIN = "3408"
GALVESTON = {
    "geofence": "galveston-county",
    "severity": "warning",
    "summary": "Standing water covering two lanes.",
    "approval_pin": PIN,
}
ROSTER_TYPES = {"county_em", "nws", "uscg", "311"}


def test_galveston_roster_and_template(client, monkeypatch):
    monkeypatch.delenv("NOTIFY_SANDBOX_PHONES", raising=False)
    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    body = response.get_json()
    assert body["matched"] is True
    assert body["geofence"] == "galveston-county"
    assert body["sandbox_only"] is True
    assert {org["type"] for org in body["roster"]} == ROSTER_TYPES
    assert all(org["would_notify"] for org in body["roster"])
    assert all(org["phone"] is None and org["email"] is None for org in body["roster"])
    assert body["draft"]["source"] == "template"
    assert "Standing water covering two lanes." in body["draft"]["body"]
    assert "911" not in body["draft"]["body"]
    assert body["mode"] == "dry-run-logged"
    assert body["delivered"] == []


def test_county_name_matches_same_roster(client):
    response = client.post("/api/notify", json={**GALVESTON, "geofence": "Galveston County"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["matched"] is True
    assert body["geofence"] == "galveston-county"
    assert {org["type"] for org in body["roster"]} == ROSTER_TYPES


def test_unknown_geofence_returns_empty_roster(client):
    response = client.post("/api/notify", json={**GALVESTON, "geofence": "travis-county"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["roster"] == []
    assert body["matched"] is False
    assert body["geofence"] == "travis-county"


def test_wrong_pin_rejects_without_log(client, monkeypatch, tmp_path):
    monkeypatch.setenv("NOTIFY_LOG_PATH", str(tmp_path / "notify_log.json"))
    reset_logs()
    response = client.post("/api/notify", json={**GALVESTON, "approval_pin": "0000"})
    assert response.status_code == 403
    assert response.get_json()["detail"] == "invalid_approval_pin"
    assert not (tmp_path / "notify_log.json").exists()


def test_default_dry_run_does_not_need_twilio(client, monkeypatch):
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "+15555550100")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxxxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15555550000")
    response = client.post("/api/notify", json=GALVESTON)
    assert response.status_code == 200
    assert response.get_json()["delivered"] == []
    assert response.get_json()["mode"] == "dry-run-logged"


def test_dry_run_zero_still_does_not_send(client, monkeypatch):
    monkeypatch.setenv("NOTIFY_DRY_RUN", "0")
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "+15555550100")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxxxxxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15555550000")
    response = client.post("/api/notify", json=GALVESTON)
    assert response.status_code == 200
    body = response.get_json()
    assert body["delivered"] == []
    assert body["mode"] == "dry-run-logged"


def test_911_is_refused(client, monkeypatch):
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "9-1-1")
    response = client.post("/api/notify", json=GALVESTON)
    assert response.status_code == 400
    assert "emergency" in response.get_json()["detail"].lower()


def test_extra_to_field_is_rejected(client):
    response = client.post("/api/notify", json={**GALVESTON, "to": "+15555550100"})
    assert response.status_code == 400
    assert "to" in response.get_json()["detail"]


def test_send_correct_pin_logs_and_pretends_success(client, monkeypatch, tmp_path):
    log_path = tmp_path / "notify_log.json"
    monkeypatch.setenv("NOTIFY_LOG_PATH", str(log_path))
    reset_logs()
    response = client.post(
        "/api/notify/send",
        json={
            "geofence_id": "galveston-county",
            "alert_id": "alert-1",
            "message": "Standing water covering two lanes.",
            "business_place_ids": ["fixture-utmb", "fixture-school"],
            "resident_ids": ["r1"],
            "include_ipaws_stub": True,
            "approval_pin": PIN,
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["mode"] == "dry-run-logged"
    assert body["would_notify"]["businesses"] == 2
    assert body["would_notify"]["residents"] == 1
    assert body["would_notify"]["ipaws_stub"] is True
    assert body["draft"]["source"] == "template"
    assert log_path.is_file()
    saved = json.loads(log_path.read_text(encoding="utf-8"))
    assert saved[0]["live_send"] is False
    assert saved[0]["business_place_ids"] == ["fixture-utmb", "fixture-school"]


def test_send_wrong_pin_no_log(client, monkeypatch, tmp_path):
    log_path = tmp_path / "notify_log.json"
    monkeypatch.setenv("NOTIFY_LOG_PATH", str(log_path))
    reset_logs()
    response = client.post(
        "/api/notify/send",
        json={
            "geofence_id": "galveston-county",
            "message": "Standing water covering two lanes.",
            "approval_pin": "9999",
        },
    )
    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "error": "invalid_approval_pin"}
    assert not log_path.exists()


def test_persist_log_writes_json(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIFY_LOG_PATH", str(tmp_path / "notify_log.json"))
    reset_logs()
    persist_log({"id": "x", "live_send": False})
    path = tmp_path / "notify_log.json"
    assert json.loads(path.read_text(encoding="utf-8"))[0]["id"] == "x"
    assert Path(path).is_file()
