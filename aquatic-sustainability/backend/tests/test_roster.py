"""CRUD tests for the gov-uploaded per-region phone roster. No Twilio."""

import importlib.util
from pathlib import Path

from flask import Flask


def _load_roster():
    path = Path(__file__).resolve().parents[1] / "app" / "roster.py"
    spec = importlib.util.spec_from_file_location("roster_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


roster = _load_roster()


def make_client(tmp_path: Path):
    app = Flask(__name__)
    roster.register_roster(app, store_path=tmp_path / "optin-rosters.json")
    return app.test_client()


def test_empty_region_skips_public_sms(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/roster/galveston-county")
    assert response.status_code == 200
    body = response.get_json()
    assert body["empty"] is True
    assert body["count"] == 0
    assert body["contacts"] == []
    assert body["public_sms"] == "skipped"


def test_add_update_delete_contact(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/roster/galveston-county/contacts",
        json={"phone": "713-555-0100", "label": "Jane Doe"},
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["count"] == 1
    assert body["contacts"][0]["phone"] == "+17135550100"
    assert body["contacts"][0]["label"] == "Jane Doe"
    contact_id = body["contacts"][0]["id"]

    listed = client.get("/api/roster")
    assert listed.get_json()["regions"][0]["count"] == 1

    patched = client.patch(
        f"/api/roster/galveston-county/contacts/{contact_id}",
        json={"label": "Harbor watch", "email": "jane@example.com"},
    )
    assert patched.status_code == 200
    assert patched.get_json()["contact"]["label"] == "Harbor watch"
    assert patched.get_json()["contact"]["email"] == "jane@example.com"

    deleted = client.delete(f"/api/roster/galveston-county/contacts/{contact_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["empty"] is True


def test_replace_from_csv_and_persist(tmp_path: Path) -> None:
    store = tmp_path / "optin-rosters.json"
    client = make_client(tmp_path)
    csv_text = "phone,label\n7135550101,A\n+1 713 555 0102,B\n"
    replaced = client.put("/api/roster/harris-county", json={"csv": csv_text})
    assert replaced.status_code == 200
    body = replaced.get_json()
    assert body["count"] == 2
    assert {row["phone"] for row in body["contacts"]} == {"+17135550101", "+17135550102"}

    other = make_client(tmp_path)
    again = other.get("/api/roster/harris-county")
    assert again.get_json()["count"] == 2
    recipients = roster.public_recipients("harris-county", store_path=store)
    assert len(recipients) == 2


def test_duplicate_and_emergency_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    first = client.post(
        "/api/roster/galveston-county/contacts",
        json={"phone": "+17135550100"},
    )
    assert first.status_code == 201
    dup = client.post(
        "/api/roster/galveston-county/contacts",
        json={"phone": "7135550100"},
    )
    assert dup.status_code == 409
    assert dup.get_json()["error"] == "duplicate_phone"

    emergency = client.post(
        "/api/roster/galveston-county/contacts",
        json={"phone": "911"},
    )
    assert emergency.status_code == 400
    assert emergency.get_json()["error"] == "emergency_number"


def test_import_merges_and_delete_region(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.put(
        "/api/roster/galveston-county",
        json={"contacts": [{"phone": "7135550100", "label": "A"}]},
    )
    imported = client.post(
        "/api/roster/galveston-county/import",
        json={"csv": "7135550100,A\n7135550199,C\n"},
    )
    assert imported.status_code == 200
    assert imported.get_json()["count"] == 2

    missing = client.delete("/api/roster/galveston-county/contacts/nope")
    assert missing.status_code == 404

    cleared = client.delete("/api/roster/galveston-county")
    assert cleared.status_code == 200
    assert cleared.get_json()["empty"] is True
    assert client.get("/api/roster").get_json()["regions"] == []
