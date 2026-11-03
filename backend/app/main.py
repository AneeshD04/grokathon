"""Alert bus sidecar.

POST /api/watches, GET /api/alerts, POST /api/alerts, SSE /api/alerts/stream.
A published alert is queued for every open stream before the POST returns.
"""

import asyncio

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.models import AlertCreate, AlertPostResponse, Watch, WatchCreate
from app.store import bus

app = FastAPI(title="Grokathon alert bus", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KEEPALIVE_S = 15.0


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/watches", response_model=Watch, status_code=201)
def create_watch(body: WatchCreate) -> Watch:
    return bus.create_watch(body)


@app.get("/api/watches", response_model=list[Watch])
def list_watches() -> list[Watch]:
    return bus.list_watches()


@app.post("/api/alerts", response_model=AlertPostResponse, status_code=201)
def create_alert(body: AlertCreate) -> AlertPostResponse:
    alert, deduped = bus.publish(body)
    return AlertPostResponse(alert=alert, deduped=deduped)


@app.get("/api/alerts")
def list_alerts(since: str | None = Query(default=None)) -> list[dict]:
    try:
        alerts = bus.list_alerts(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [alert.model_dump(mode="json") for alert in alerts]


@app.get("/api/alerts/stream")
async def stream_alerts(request: Request) -> StreamingResponse:
    queue = bus.subscribe()

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
