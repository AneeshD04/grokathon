"""Alert bus sidecar.

POST /api/watches, GET /api/alerts, POST /api/alerts, SSE /api/alerts/stream.
A published alert is queued for every open stream before the POST returns.

This process does not send SMS, email, calls, or 911. Notify lives on #13
and is PIN-gated dry-run only.
"""

import asyncio
import hmac
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.models import AlertCreate, AlertPostResponse, Watch, WatchCreate
from app.store import SubscriberLimitError, WatchLimitError, bus

KEEPALIVE_S = 15.0


def _cors_origins() -> list[str]:
    raw = os.environ.get("ALERT_BUS_CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    if not raw:
        return [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5000",
            "http://localhost:5000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    return [part.strip() for part in raw.split(",") if part.strip()]


async def require_bus_token(request: Request) -> None:
    """Optional shared secret. Unset = local demo. Set if the port is reachable."""
    token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
    if not token:
        return
    provided = request.headers.get("x-alert-bus-token") or ""
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided or not hmac.compare_digest(provided, token):
        raise HTTPException(status_code=401, detail="invalid token")


app = FastAPI(title="Grokathon alert bus", version="0.1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Alert-Bus-Token"],
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/watches", response_model=Watch, status_code=201)
async def create_watch(
    body: WatchCreate, _: None = Depends(require_bus_token)
) -> Watch:
    try:
        return bus.create_watch(body)
    except WatchLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.get("/api/watches", response_model=list[Watch])
async def list_watches(_: None = Depends(require_bus_token)) -> list[Watch]:
    return bus.list_watches()


@app.post("/api/alerts", response_model=AlertPostResponse, status_code=201)
async def create_alert(
    body: AlertCreate, _: None = Depends(require_bus_token)
) -> AlertPostResponse:
    alert, deduped = bus.publish(body)
    return AlertPostResponse(alert=alert, deduped=deduped)


@app.get("/api/alerts")
async def list_alerts(
    since: str | None = Query(default=None),
    _: None = Depends(require_bus_token),
) -> list[dict]:
    try:
        alerts = bus.list_alerts(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [alert.model_dump(mode="json") for alert in alerts]


@app.get("/api/alerts/stream")
async def stream_alerts(
    request: Request, _: None = Depends(require_bus_token)
) -> StreamingResponse:
    try:
        queue = bus.subscribe()
    except SubscriberLimitError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def events():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    alert = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: alert\ndata: {alert.model_dump_json()}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
