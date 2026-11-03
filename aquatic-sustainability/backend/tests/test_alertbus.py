from queue import Empty

from app.alertbus import bus


def _alert(dedupe_key: str, title: str = "Water over roadway") -> dict:
    return {
        "source": "camera",
        "severity": "warning",
        "lat": 29.3,
        "lon": -94.8,
        "geofence_id": "galveston-county",
        "title": title,
        "summary": "Vision: standing water covering two lanes.",
        "evidence": {"thumb_url": "https://example.test/frame.jpg", "raw": {}},
        "dedupe_key": dedupe_key,
    }


def test_watch_requires_bbox_or_county(client):
    response = client.post("/api/watches", json={"sources": ["nws"]})
    assert response.status_code == 400


def test_create_watch_from_county(client):
    response = client.post(
        "/api/watches",
        json={"county": "Galveston County", "sources": ["nws", "camera"]},
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["geofence_id"] == "galveston-county"
    assert body["sources"] == ["nws", "camera"]
    listed = client.get("/api/watches")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1


def test_publish_then_list_since(client):
    created = client.post("/api/alerts", json=_alert("cam:1:water"))
    assert created.status_code == 201
    payload = created.get_json()
    assert payload["deduped"] is False
    assert payload["alert"]["source"] == "camera"
    assert payload["alert"]["id"]

    again = client.get("/api/alerts", query_string={"since": "1970-01-01T00:00:00Z"})
    assert again.status_code == 200
    assert len(again.get_json()) == 1

    future = client.get("/api/alerts", query_string={"since": "2999-01-01T00:00:00Z"})
    assert future.get_json() == []

    bad = client.get("/api/alerts", query_string={"since": "not-a-date"})
    assert bad.status_code == 400


def test_dedupe_suppresses_second_publish(client):
    first = client.post("/api/alerts", json=_alert("cam:1:water")).get_json()
    second = client.post("/api/alerts", json=_alert("cam:1:water", title="again"))
    assert second.status_code == 201
    body = second.get_json()
    assert body["deduped"] is True
    assert body["alert"]["id"] == first["alert"]["id"]
    assert len(client.get("/api/alerts").get_json()) == 1


def test_rejects_non_http_thumb_url(client):
    payload = _alert("cam:bad")
    payload["evidence"] = {"thumb_url": "javascript:alert(1)", "raw": {}}
    assert client.post("/api/alerts", json=payload).status_code == 400
    payload["evidence"] = {"thumb_url": "file:///etc/passwd", "raw": {}}
    assert client.post("/api/alerts", json=payload).status_code == 400


def test_alert_cap_drops_oldest(client):
    bus.max_alerts = 2
    client.post("/api/alerts", json=_alert("cam:a"))
    client.post("/api/alerts", json=_alert("cam:b"))
    client.post("/api/alerts", json=_alert("cam:c"))
    keys = [row["dedupe_key"] for row in client.get("/api/alerts").get_json()]
    assert keys == ["cam:b", "cam:c"]


def test_watch_cap_returns_429(client):
    bus.max_watches = 1
    first = client.post(
        "/api/watches", json={"county": "Galveston County", "sources": ["nws"]}
    )
    assert first.status_code == 201
    second = client.post(
        "/api/watches", json={"county": "Harris County", "sources": ["nws"]}
    )
    assert second.status_code == 429


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("ALERT_BUS_TOKEN", "secret-token")
    denied = client.post("/api/alerts", json=_alert("cam:token"))
    assert denied.status_code == 401
    ok = client.post(
        "/api/alerts",
        json=_alert("cam:token"),
        headers={"X-Alert-Bus-Token": "secret-token"},
    )
    assert ok.status_code == 201


def test_publish_reaches_subscriber_immediately():
    queue = bus.subscribe()
    try:
        alert, deduped = bus.publish(
            {
                "source": "camera",
                "severity": "warning",
                "lat": 29.3,
                "lon": -94.8,
                "geofence_id": "galveston-county",
                "title": "Water over roadway",
                "summary": "Vision: standing water covering two lanes.",
                "evidence": {"thumb_url": "https://example.test/frame.jpg", "raw": {}},
                "dedupe_key": "cam:sse:water",
            }
        )
        assert deduped is False
        got = queue.get(timeout=1.0)
        assert got["id"] == alert["id"]
        assert got["dedupe_key"] == "cam:sse:water"
    finally:
        bus.unsubscribe(queue)
        try:
            queue.get_nowait()
        except Empty:
            pass


def test_model_source_is_valid(client):
    payload = _alert("model:flood:1")
    payload["source"] = "model"
    response = client.post("/api/alerts", json=payload)
    assert response.status_code == 201
    assert response.get_json()["alert"]["source"] == "model"
