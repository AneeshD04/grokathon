"""In-process watch registry and alert bus. Redis is optional and unused."""

import asyncio
import os
from datetime import datetime, timezone

from app.ids import new_ulid
from app.models import Alert, AlertCreate, Watch, WatchCreate, parse_iso

DEDUPE_WINDOW_S = float(os.environ.get("ALERT_DEDUPE_WINDOW_S", "60"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def geofence_id_for(body: WatchCreate) -> str:
    if body.geofence_id and body.geofence_id.strip():
        return body.geofence_id.strip()
    if body.county:
        slug = "-".join(body.county.lower().split())
        return slug
    assert body.bbox is not None
    min_lon, min_lat, max_lon, max_lat = body.bbox
    return f"bbox:{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"


class AlertBus:
    def __init__(self, dedupe_window_s: float = DEDUPE_WINDOW_S) -> None:
        self.dedupe_window_s = dedupe_window_s
        self.alerts: list[Alert] = []
        self.watches: dict[str, Watch] = {}
        self.subscribers: list[asyncio.Queue[Alert]] = []
        self._seen: dict[str, tuple[str, datetime]] = {}

    def reset(self) -> None:
        self.alerts.clear()
        self.watches.clear()
        self.subscribers.clear()
        self._seen.clear()

    def create_watch(self, body: WatchCreate) -> Watch:
        watch = Watch(
            id=new_ulid(),
            geofence_id=geofence_id_for(body),
            bbox=body.bbox,
            county=body.county,
            sources=body.sources,
            camera_ids=body.camera_ids,
            created_at=iso_z(utc_now()),
        )
        self.watches[watch.id] = watch
        return watch

    def list_watches(self) -> list[Watch]:
        return list(self.watches.values())

    def publish(self, body: AlertCreate) -> tuple[Alert, bool]:
        received_at = utc_now()
        previous = self._seen.get(body.dedupe_key)
        if previous is not None:
            previous_id, previous_at = previous
            if (received_at - previous_at).total_seconds() < self.dedupe_window_s:
                existing = next(alert for alert in self.alerts if alert.id == previous_id)
                return existing, True

        alert = Alert(
            id=new_ulid(),
            ts=body.ts or iso_z(received_at),
            source=body.source,
            severity=body.severity,
            lat=body.lat,
            lon=body.lon,
            geofence_id=body.geofence_id,
            title=body.title,
            summary=body.summary,
            evidence=body.evidence,
            dedupe_key=body.dedupe_key,
        )
        self.alerts.append(alert)
        self._seen[body.dedupe_key] = (alert.id, received_at)
        for queue in list(self.subscribers):
            queue.put_nowait(alert)
        return alert, False

    def list_alerts(self, since: str | None) -> list[Alert]:
        if since is None:
            found = list(self.alerts)
        else:
            cutoff = parse_iso(since)
            found = [alert for alert in self.alerts if parse_iso(alert.ts) >= cutoff]
        found.sort(key=lambda alert: alert.ts)
        return found

    def subscribe(self) -> asyncio.Queue[Alert]:
        queue: asyncio.Queue[Alert] = asyncio.Queue()
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Alert]) -> None:
        if queue in self.subscribers:
            self.subscribers.remove(queue)


bus = AlertBus()
