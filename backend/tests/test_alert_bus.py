import asyncio
import contextlib
import json
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.main import app
from app.store import MAX_ALERTS, MAX_WATCHES, bus


@pytest.fixture(autouse=True)
def clean_bus():
    bus.reset()
    bus.max_alerts = MAX_ALERTS
    bus.max_watches = MAX_WATCHES
    yield
    bus.reset()
    bus.max_alerts = MAX_ALERTS
    bus.max_watches = MAX_WATCHES


def test_watch_requires_bbox_or_county():
    client = TestClient(app)
    response = client.post("/api/watches", json={"sources": ["nws"]})
    assert response.status_code == 422


def test_create_watch_from_county():
    client = TestClient(app)
    response = client.post(
        "/api/watches",
        json={"county": "Galveston County", "sources": ["nws", "camera"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["geofence_id"] == "galveston-county"
    assert body["sources"] == ["nws", "camera"]
    listed = client.get("/api/watches")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_publish_then_list_since():
    client = TestClient(app)
    created = client.post("/api/alerts", json=_alert("cam:1:water"))
    assert created.status_code == 201
    payload = created.json()
    assert payload["deduped"] is False
    assert payload["alert"]["source"] == "camera"
    assert payload["alert"]["id"]

    again = client.get("/api/alerts", params={"since": "1970-01-01T00:00:00Z"})
    assert again.status_code == 200
    assert len(again.json()) == 1

    future = client.get("/api/alerts", params={"since": "2999-01-01T00:00:00Z"})
    assert future.json() == []

    bad = client.get("/api/alerts", params={"since": "not-a-date"})
    assert bad.status_code == 400


def test_dedupe_suppresses_second_publish():
    client = TestClient(app)
    first = client.post("/api/alerts", json=_alert("cam:1:water")).json()
    second = client.post("/api/alerts", json=_alert("cam:1:water", title="again"))
    assert second.status_code == 201
    body = second.json()
    assert body["deduped"] is True
    assert body["alert"]["id"] == first["alert"]["id"]
    assert len(client.get("/api/alerts").json()) == 1


def test_rejects_non_http_thumb_url():
    client = TestClient(app)
    payload = _alert("cam:bad")
    payload["evidence"] = {"thumb_url": "javascript:alert(1)", "raw": {}}
    assert client.post("/api/alerts", json=payload).status_code == 422
    payload["evidence"] = {"thumb_url": "file:///etc/passwd", "raw": {}}
    assert client.post("/api/alerts", json=payload).status_code == 422


def test_alert_cap_drops_oldest():
    bus.max_alerts = 2
    client = TestClient(app)
    client.post("/api/alerts", json=_alert("cam:a"))
    client.post("/api/alerts", json=_alert("cam:b"))
    client.post("/api/alerts", json=_alert("cam:c"))
    keys = [row["dedupe_key"] for row in client.get("/api/alerts").json()]
    assert keys == ["cam:b", "cam:c"]


def test_watch_cap_returns_429():
    bus.max_watches = 1
    client = TestClient(app)
    first = client.post(
        "/api/watches", json={"county": "Galveston County", "sources": ["nws"]}
    )
    assert first.status_code == 201
    second = client.post(
        "/api/watches", json={"county": "Harris County", "sources": ["nws"]}
    )
    assert second.status_code == 429


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("ALERT_BUS_TOKEN", "secret-token")
    client = TestClient(app)
    denied = client.post("/api/alerts", json=_alert("cam:token"))
    assert denied.status_code == 401
    ok = client.post(
        "/api/alerts",
        json=_alert("cam:token"),
        headers={"X-Alert-Bus-Token": "secret-token"},
    )
    assert ok.status_code == 201


def test_post_shows_up_on_sse_within_one_second():
    elapsed = asyncio.run(_sse_roundtrip())
    assert elapsed < 1.0


async def _sse_roundtrip() -> float:
    # ASGITransport cannot interleave an open SSE response with a later POST
    # on the same client. A real server lets one connection stream and another post.
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError("alert bus server exited during startup")
            await asyncio.sleep(0.01)
        else:
            raise TimeoutError("alert bus server did not start")

        sockets = server.servers[0].sockets
        assert sockets is not None
        port = sockets[0].getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        timeout = httpx.Timeout(5.0)
        found: dict = {}
        ready = asyncio.Event()

        async with (
            httpx.AsyncClient(base_url=base_url, timeout=timeout) as stream_client,
            httpx.AsyncClient(base_url=base_url, timeout=timeout) as post_client,
        ):

            async def listen() -> None:
                async with stream_client.stream("GET", "/api/alerts/stream") as response:
                    assert response.status_code == 200
                    async for line in response.aiter_lines():
                        ready.set()
                        if line.startswith("data: "):
                            found["alert"] = json.loads(line[6:])
                            return

            task = asyncio.create_task(listen())
            try:
                await asyncio.wait_for(ready.wait(), timeout=2.0)
                started = time.perf_counter()
                posted = await post_client.post("/api/alerts", json=_alert("cam:sse:water"))
                assert posted.status_code == 201
                await asyncio.wait_for(task, timeout=1.0)
                elapsed = time.perf_counter() - started
                assert found["alert"]["dedupe_key"] == "cam:sse:water"
                assert found["alert"]["id"] == posted.json()["alert"]["id"]
                return elapsed
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
    finally:
        server.should_exit = True
        await server_task


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
