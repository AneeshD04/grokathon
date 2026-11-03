"""In-process Flask alert bus (watches, alerts, SSE).

Does not send SMS, email, calls, or 911. Fan-out notify is PIN-gated dry-run
on the notify blueprint. evidence.thumb_url is stored, never fetched.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, Response, jsonify, request, stream_with_context

bp = Blueprint("alertbus", __name__)

SOURCES = {"camera", "nws", "usgs", "x", "model", "news", "places"}
SEVERITIES = {"info", "watch", "warning", "critical"}
KEEPALIVE_S = 15.0
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_ulid() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), "big")
    value = (timestamp_ms << 80) | randomness
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("ts must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("ts must include a timezone")
    return parsed


class WatchLimitError(Exception):
    pass


class SubscriberLimitError(Exception):
    pass


class AlertBus:
    def __init__(
        self,
        dedupe_window_s: float | None = None,
        max_alerts: int | None = None,
        max_watches: int | None = None,
        max_subscribers: int | None = None,
        queue_maxsize: int | None = None,
    ) -> None:
        self.dedupe_window_s = float(
            os.environ.get("ALERT_DEDUPE_WINDOW_S", "60")
            if dedupe_window_s is None
            else dedupe_window_s
        )
        self.max_alerts = int(
            os.environ.get("ALERT_BUS_MAX_ALERTS", "500") if max_alerts is None else max_alerts
        )
        self.max_watches = int(
            os.environ.get("ALERT_BUS_MAX_WATCHES", "200") if max_watches is None else max_watches
        )
        self.max_subscribers = int(
            os.environ.get("ALERT_BUS_MAX_SUBSCRIBERS", "32")
            if max_subscribers is None
            else max_subscribers
        )
        self.queue_maxsize = int(
            os.environ.get("ALERT_BUS_QUEUE_MAXSIZE", "100")
            if queue_maxsize is None
            else queue_maxsize
        )
        self.alerts: deque[dict[str, Any]] = deque()
        self.watches: dict[str, dict[str, Any]] = {}
        self.subscribers: list[Queue] = []
        self._seen: dict[str, tuple[str, datetime]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self.alerts.clear()
            self.watches.clear()
            self.subscribers.clear()
            self._seen.clear()

    def create_watch(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if len(self.watches) >= self.max_watches:
                raise WatchLimitError("watch registry is full")
            watch = {
                "id": _new_ulid(),
                "geofence_id": geofence_id_for(body),
                "bbox": body.get("bbox"),
                "county": body.get("county"),
                "sources": body["sources"],
                "camera_ids": body.get("camera_ids") or [],
                "created_at": iso_z(utc_now()),
            }
            self.watches[watch["id"]] = watch
            return watch

    def list_watches(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.watches.values())

    def publish(self, body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        received_at = utc_now()
        with self._lock:
            previous = self._seen.get(body["dedupe_key"])
            if previous is not None:
                previous_id, previous_at = previous
                if (received_at - previous_at).total_seconds() < self.dedupe_window_s:
                    existing = next(
                        (alert for alert in self.alerts if alert["id"] == previous_id),
                        None,
                    )
                    if existing is not None:
                        return existing, True

            alert = {
                "id": _new_ulid(),
                "ts": body.get("ts") or iso_z(received_at),
                "source": body["source"],
                "severity": body["severity"],
                "lat": body["lat"],
                "lon": body["lon"],
                "geofence_id": body["geofence_id"],
                "title": body["title"],
                "summary": body["summary"],
                "evidence": body.get("evidence") or {"thumb_url": None, "raw": {}},
                "dedupe_key": body["dedupe_key"],
            }
            self.alerts.append(alert)
            while len(self.alerts) > self.max_alerts:
                self.alerts.popleft()
            self._seen[body["dedupe_key"]] = (alert["id"], received_at)
            subscribers = list(self.subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(alert)
            except Full:
                continue
        return alert, False

    def list_alerts(self, since: str | None) -> list[dict[str, Any]]:
        with self._lock:
            if since is None:
                found = list(self.alerts)
            else:
                cutoff = parse_iso(since)
                found = [alert for alert in self.alerts if parse_iso(alert["ts"]) >= cutoff]
        found.sort(key=lambda alert: alert["ts"])
        return found

    def subscribe(self) -> Queue:
        with self._lock:
            if len(self.subscribers) >= self.max_subscribers:
                raise SubscriberLimitError("too many SSE subscribers")
            queue: Queue = Queue(maxsize=self.queue_maxsize)
            self.subscribers.append(queue)
            return queue

    def unsubscribe(self, queue: Queue) -> None:
        with self._lock:
            if queue in self.subscribers:
                self.subscribers.remove(queue)


bus = AlertBus()


def geofence_id_for(body: dict[str, Any]) -> str:
    geofence_id = (body.get("geofence_id") or "").strip()
    if geofence_id:
        return geofence_id
    county = body.get("county")
    if county:
        return "-".join(str(county).lower().split())
    min_lon, min_lat, max_lon, max_lat = body["bbox"]
    return f"bbox:{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"


def _token_error():
    token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
    if not token:
        return None
    provided = request.headers.get("X-Alert-Bus-Token") or ""
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided or not hmac.compare_digest(provided, token):
        return jsonify({"detail": "invalid token"}), 401
    return None


def _json() -> tuple[dict[str, Any] | None, tuple | None]:
    if not request.is_json:
        return None, (jsonify({"detail": "JSON body required"}), 400)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"detail": "JSON object required"}), 400)
    return body, None


def _check_lon_lat(lon: float, lat: float) -> None:
    if not -180 <= lon <= 180:
        raise ValueError("longitude out of range")
    if not -90 <= lat <= 90:
        raise ValueError("latitude out of range")


def parse_watch(body: dict[str, Any]) -> dict[str, Any]:
    sources = body.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 16:
        raise ValueError("sources is required")
    cleaned_sources = []
    for item in sources:
        if item not in SOURCES:
            raise ValueError("invalid source")
        cleaned_sources.append(item)
    county = body.get("county")
    if county is not None:
        county = str(county).strip() or None
        if county and len(county) > 120:
            raise ValueError("county too long")
    bbox = body.get("bbox")
    if bbox is not None:
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("bbox must be [minLon, minLat, maxLon, maxLat]")
        try:
            min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
        except (TypeError, ValueError) as exc:
            raise ValueError("bbox must be numbers") from exc
        if not (min_lon < max_lon and min_lat < max_lat):
            raise ValueError("bbox min must be less than max")
        _check_lon_lat(min_lon, min_lat)
        _check_lon_lat(max_lon, max_lat)
        bbox = [min_lon, min_lat, max_lon, max_lat]
    if bbox is None and county is None:
        raise ValueError("bbox or county is required")
    camera_ids = body.get("camera_ids") or []
    if not isinstance(camera_ids, list) or len(camera_ids) > 32:
        raise ValueError("camera_ids too long")
    for item in camera_ids:
        if not isinstance(item, str) or len(item) > 120:
            raise ValueError("camera_id too long")
    geofence_id = body.get("geofence_id")
    if geofence_id is not None:
        geofence_id = str(geofence_id).strip() or None
        if geofence_id and len(geofence_id) > 120:
            raise ValueError("geofence_id too long")
    return {
        "bbox": bbox,
        "county": county,
        "sources": cleaned_sources,
        "camera_ids": camera_ids,
        "geofence_id": geofence_id,
    }


def parse_evidence(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"thumb_url": None, "raw": {}}
    if not isinstance(raw, dict):
        raise ValueError("evidence must be an object")
    thumb = raw.get("thumb_url")
    if thumb is not None:
        text = str(thumb).strip()
        if not text:
            thumb = None
        else:
            parsed = urlparse(text)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("thumb_url must be an http(s) URL")
            if parsed.username or parsed.password:
                raise ValueError("thumb_url must not include credentials")
            thumb = text
    payload = raw.get("raw") or {}
    if not isinstance(payload, dict) or len(payload) > 32:
        raise ValueError("evidence.raw has too many keys")
    return {"thumb_url": thumb, "raw": payload}


def parse_alert(body: dict[str, Any]) -> dict[str, Any]:
    source = body.get("source")
    severity = body.get("severity")
    if source not in SOURCES:
        raise ValueError("invalid source")
    if severity not in SEVERITIES:
        raise ValueError("invalid severity")
    try:
        lat = float(body["lat"])
        lon = float(body["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("lat and lon are required") from exc
    _check_lon_lat(lon, lat)
    geofence_id = str(body.get("geofence_id") or "").strip()
    title = str(body.get("title") or "").strip()
    summary = str(body.get("summary") or "").strip()
    dedupe_key = str(body.get("dedupe_key") or "").strip()
    if not geofence_id or len(geofence_id) > 120:
        raise ValueError("geofence_id is required")
    if not title or len(title) > 200:
        raise ValueError("title is required")
    if not summary or len(summary) > 4000:
        raise ValueError("summary is required")
    if not dedupe_key or len(dedupe_key) > 200:
        raise ValueError("dedupe_key is required")
    ts = body.get("ts")
    if ts is not None:
        ts = str(ts).strip()
        parse_iso(ts)
    return {
        "source": source,
        "severity": severity,
        "lat": lat,
        "lon": lon,
        "geofence_id": geofence_id,
        "title": title,
        "summary": summary,
        "evidence": parse_evidence(body.get("evidence")),
        "dedupe_key": dedupe_key,
        "ts": ts,
    }


@bp.before_request
def _require_bus_token():
    return _token_error()


@bp.route("/watches", methods=["POST"])
def create_watch():
    body, err = _json()
    if err:
        return err
    try:
        parsed = parse_watch(body)
        watch = bus.create_watch(parsed)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    except WatchLimitError as exc:
        return jsonify({"detail": str(exc)}), 429
    return jsonify(watch), 201


@bp.route("/watches", methods=["GET"])
def list_watches():
    return jsonify(bus.list_watches())


@bp.route("/alerts", methods=["POST"])
def create_alert():
    body, err = _json()
    if err:
        return err
    try:
        parsed = parse_alert(body)
        alert, deduped = bus.publish(parsed)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    return jsonify({"alert": alert, "deduped": deduped}), 201


@bp.route("/alerts", methods=["GET"])
def list_alerts():
    since = request.args.get("since")
    try:
        alerts = bus.list_alerts(since)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    return jsonify(alerts)


@bp.route("/alerts/stream", methods=["GET"])
def stream_alerts():
    try:
        queue = bus.subscribe()
    except SubscriberLimitError as exc:
        return jsonify({"detail": str(exc)}), 503

    def events():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    alert = queue.get(timeout=KEEPALIVE_S)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: alert\ndata: {json.dumps(alert)}\n\n"
        finally:
            bus.unsubscribe(queue)

    return Response(
        stream_with_context(events()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
