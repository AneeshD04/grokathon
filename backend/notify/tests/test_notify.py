"""Sandbox notify: roster for the UI, SMS only to team numbers."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from notify.main import app, get_sender

GALVESTON = {
    "geofence": "galveston-county",
    "severity": "warning",
    "summary": "Standing water covering two lanes.",
}

ROSTER_TYPES = {"county_em", "nws", "uscg", "311"}


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> None:
        self.calls.append((to, body))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "XAI_API_KEY",
        "NOTIFY_SANDBOX_PHONES",
        "NOTIFY_ROSTER_PATH",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
    ):
        monkeypatch.delenv(name, raising=False)
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_galveston_roster_and_template(client: TestClient) -> None:
    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] is True
    assert body["geofence"] == "galveston-county"
    assert body["sandbox_only"] is True
    assert {org["type"] for org in body["roster"]} == ROSTER_TYPES
    assert all(org["would_notify"] for org in body["roster"])
    assert all(org["phone"] is None and org["email"] is None for org in body["roster"])
    assert body["draft"]["source"] == "template"
    assert "Standing water covering two lanes." in body["draft"]["body"]
    assert "911" not in body["draft"]["body"]


def test_county_name_matches_same_roster(client: TestClient) -> None:
    response = client.post(
        "/api/notify",
        json={**GALVESTON, "geofence": "Galveston County"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched"] is True
    assert body["geofence"] == "galveston-county"
    assert {org["type"] for org in body["roster"]} == ROSTER_TYPES


def test_unknown_geofence_returns_empty_roster(client: TestClient) -> None:
    response = client.post(
        "/api/notify",
        json={**GALVESTON, "geofence": "travis-county"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["roster"] == []
    assert body["matched"] is False
    assert body["geofence"] == "travis-county"


def test_sends_only_sandbox_phones(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "+15555550100, +15555550101")
    fake = FakeSender()
    app.dependency_overrides[get_sender] = lambda: fake

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    assert [call[0] for call in fake.calls] == ["+15555550100", "+15555550101"]
    assert response.json()["delivered"] == [
        {"channel": "sms", "to": "+15555550100"},
        {"channel": "sms", "to": "+15555550101"},
    ]


def test_roster_phones_are_not_destinations(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    roster = [
        {
            "name": "Galveston County Office of Emergency Management",
            "type": "county_em",
            "county": "Galveston",
            "email": "oem@example.test",
            "phone": "+15555550999",
        },
        {
            "name": "National Weather Service Houston/Galveston",
            "type": "nws",
            "county": "Galveston",
            "email": None,
            "phone": None,
        },
        {
            "name": "U.S. Coast Guard Sector Houston-Galveston",
            "type": "uscg",
            "county": "Galveston",
            "email": None,
            "phone": None,
        },
        {
            "name": "City of Galveston 311",
            "type": "311",
            "county": "Galveston",
            "email": None,
            "phone": None,
        },
    ]
    path = tmp_path / "orgs.json"
    path.write_text(json.dumps(roster))
    monkeypatch.setenv("NOTIFY_ROSTER_PATH", str(path))
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "+15555550100")
    fake = FakeSender()
    app.dependency_overrides[get_sender] = lambda: fake

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    assert [call[0] for call in fake.calls] == ["+15555550100"]
    delivered = response.json()["delivered"]
    assert delivered == [{"channel": "sms", "to": "+15555550100"}]
    assert all(item["to"] != "+15555550999" for item in delivered)
    assert "oem@example.test" not in {item["to"] for item in delivered}


def test_sandbox_number_matching_roster_is_refused(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    roster = [
        {
            "name": "Galveston County Office of Emergency Management",
            "type": "county_em",
            "county": "Galveston",
            "email": None,
            "phone": "+1 (555) 555-0999",
        }
    ]
    path = tmp_path / "orgs.json"
    path.write_text(json.dumps(roster))
    monkeypatch.setenv("NOTIFY_ROSTER_PATH", str(path))
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "15555550999")
    fake = FakeSender()
    app.dependency_overrides[get_sender] = lambda: fake

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 400
    assert fake.calls == []


def test_911_is_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "9-1-1")
    fake = FakeSender()
    app.dependency_overrides[get_sender] = lambda: fake

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 400
    assert fake.calls == []


def test_extra_to_field_is_rejected(client: TestClient) -> None:
    response = client.post("/api/notify", json={**GALVESTON, "to": "+15555550100"})

    assert response.status_code == 422


def test_grok_draft_stays_on_the_mock(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    posts: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {"message": {"content": "Warning: standing water on two lanes in galveston-county."}}
                ]
            }

    class FakeClient:
        def __init__(self, timeout: float = 15.0) -> None:
            self.timeout = timeout

        def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> FakeResponse:
            posts.append(url)
            assert headers is not None and headers["Authorization"] == "Bearer test-key"
            return FakeResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr("notify.draft.httpx.Client", FakeClient)

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    assert response.json()["draft"]["source"] == "grok"
    assert posts == ["https://api.x.ai/v1/chat/completions"]


def test_missing_twilio_env_returns_roster(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFY_SANDBOX_PHONES", "+15555550100")

    response = client.post("/api/notify", json=GALVESTON)

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] == []
    assert {org["type"] for org in body["roster"]} == ROSTER_TYPES
    assert body["draft"]["source"] == "template"
