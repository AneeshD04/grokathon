"""In-process ModelWatch: poll cached flood-risk + coral, emit Flask alerts.

This lives on the BDBI Flask app. It does **not** rewrite DualCNN-LSTM
(`flood_model.py`) and it does **not** trigger a NASA GPM/SMAP redownload.
Flood polling only reads the Redis keys already written by `POST /api/flood-risk`.
If those keys are missing, live inference is skipped and the skip is recorded
on `GET /api/modelwatch/status`.

Coral uses the on-disk GBR CSV bundle (`coral_bleaching_loader.get_bundle`).
No Grok. No Twilio. Dummy `GET /api/flood` polygons are ignored.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

logger = logging.getLogger("modelwatch")

bp = Blueprint("modelwatch", __name__)

# Great Barrier Reef box from the ModelWatch spec (lon 142–154, lat -24–-10).
GBR_BBOX = [142.0, -24.0, 154.0, -10.0]

# Demo OEM counties. Harris/Galveston will not intersect GBR — that is honest.
DEMO_WATCHES = (
    {
        "geofence_id": "galveston-county",
        "county": "Galveston County",
        "bbox": [-95.17, 29.02, -94.37, 29.67],
        "sources": ["model"],
    },
    {
        "geofence_id": "harris-county",
        "county": "Harris County",
        "bbox": [-95.95, 29.52, -94.98, 30.17],
        "sources": ["model"],
    },
)

FLOOD_SKIP_REASON = (
    "no flood-risk Redis cache for the watch centroid; skipped live DualCNN-LSTM "
    "inference to avoid a NASA GPM IMERG + SMAP redownload"
)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(moment: datetime | None = None) -> str:
    moment = moment or _utc_now()
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return uuid.uuid4().hex


def centroid(bbox: list[float]) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0


def boxes_overlap(left: list[float], right: list[float]) -> bool:
    left_min_lon, left_min_lat, left_max_lon, left_max_lat = left
    right_min_lon, right_min_lat, right_max_lon, right_max_lat = right
    return (
        left_min_lon < right_max_lon
        and left_max_lon > right_min_lon
        and left_min_lat < right_max_lat
        and left_max_lat > right_min_lat
    )


def point_in_bbox(lat: float, lon: float, bbox: list[float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def valid_bbox(bbox: Any) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        min_lon, min_lat, max_lon, max_lat = (float(item) for item in bbox)
    except (TypeError, ValueError):
        return False
    return min_lon < max_lon and min_lat < max_lat


def _decode_redis(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def flood_cache_keys(lat: float, lon: float) -> list[str]:
    """Keys written by routes.py and flood_model.py. Read-only — never populate."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return [
        f"flood_risk_{lat:.2f}_{lon:.2f}",
        f"flood_inference:{round(lat, 3)}:{round(lon, 3)}:{date_str}",
    ]


def _latest(series: Any) -> Any:
    if not isinstance(series, list):
        return None
    for value in reversed(series):
        if value is not None:
            return value
    return None


class ModelWatchState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.watches: dict[str, dict] = {}
        self.alerts: deque[dict] = deque(maxlen=500)
        self.dedupe: dict[str, tuple[str, float]] = {}
        self.subscribers: list[Queue] = []
        self.last_poll: dict[str, Any] | None = None

    def reset(self) -> None:
        with self.lock:
            self.watches.clear()
            self.alerts.clear()
            self.dedupe.clear()
            self.subscribers.clear()
            self.last_poll = None


state = ModelWatchState()


def seed_demo_watches() -> None:
    with state.lock:
        if state.watches:
            return
    for spec in DEMO_WATCHES:
        create_watch(dict(spec))


def create_watch(body: dict) -> dict:
    bbox = body.get("bbox")
    county = (body.get("county") or "").strip() or None
    if not valid_bbox(bbox) and not county:
        raise ValueError("bbox or county is required")
    if bbox is not None and not valid_bbox(bbox):
        raise ValueError("bbox must be [minLon, minLat, maxLon, maxLat]")
    sources = body.get("sources") or ["model"]
    sources = [str(item) for item in sources]
    geofence_id = (body.get("geofence_id") or "").strip()
    if not geofence_id:
        if county:
            geofence_id = "-".join(county.lower().split())
        else:
            min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox)
            geofence_id = f"bbox:{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"
    watch = {
        "id": _new_id(),
        "geofence_id": geofence_id,
        "bbox": [float(x) for x in bbox] if valid_bbox(bbox) else None,
        "county": county,
        "sources": sources,
        "created_at": _iso_z(),
    }
    with state.lock:
        state.watches[watch["id"]] = watch
    return watch


def list_watches() -> list[dict]:
    with state.lock:
        return list(state.watches.values())


def get_watch(watch_id: str) -> dict | None:
    with state.lock:
        found = state.watches.get(watch_id)
        if found is not None:
            return found
        for watch in state.watches.values():
            if watch.get("geofence_id") == watch_id:
                return watch
    return None


def list_alerts(since: str | None = None) -> list[dict]:
    with state.lock:
        alerts = list(state.alerts)
    if since:
        alerts = [alert for alert in alerts if alert.get("ts", "") >= since]
    alerts.sort(key=lambda alert: alert.get("ts") or "")
    return alerts


def subscribe() -> Queue:
    queue: Queue = Queue(maxsize=100)
    with state.lock:
        state.subscribers.append(queue)
    return queue


def unsubscribe(queue: Queue) -> None:
    with state.lock:
        if queue in state.subscribers:
            state.subscribers.remove(queue)


def publish_alert(alert: dict, *, now: float | None = None) -> tuple[dict, bool]:
    """Store an alert on the in-process Flask bus. Dedup by key + window."""
    now = time.time() if now is None else now
    dedupe_s = _env_float("MODELWATCH_DEDUPE_S", 3600.0)
    key = str(alert.get("dedupe_key") or "")
    severity = str(alert.get("severity") or "")
    with state.lock:
        previous = state.dedupe.get(key)
        if previous is not None:
            last_severity, last_at = previous
            if last_severity == severity and (now - last_at) < dedupe_s:
                existing = next(
                    (item for item in reversed(state.alerts) if item.get("dedupe_key") == key),
                    None,
                )
                if existing is not None:
                    return existing, True
        stored = dict(alert)
        stored.setdefault("id", _new_id())
        stored.setdefault("ts", _iso_z())
        stored.setdefault("source", "model")
        stored.setdefault("impacted_businesses", [])
        state.alerts.append(stored)
        state.dedupe[key] = (severity, now)
        subscribers = list(state.subscribers)
    for queue in subscribers:
        try:
            queue.put_nowait(stored)
        except Exception:
            continue
    return stored, False


def read_flood_cache(redis, lat: float, lon: float) -> tuple[dict | None, str | None]:
    if redis is None:
        return None, None
    for key in flood_cache_keys(lat, lon):
        try:
            raw = redis.get(key)
        except Exception as exc:
            logger.warning("flood cache read failed for %s: %s", key, exc)
            continue
        payload = _decode_redis(raw)
        if isinstance(payload, dict):
            return payload, key
    return None, None


def _flood_result(payload: dict) -> dict:
    if "points" in payload:
        return payload
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def max_in_bbox_prob(result: dict, bbox: list[float]) -> tuple[float | None, dict | None]:
    points = result.get("points") or []
    best: tuple[float, dict] | None = None
    if not isinstance(points, list):
        return None, None
    for point in points:
        if not isinstance(point, dict) or point.get("prob") is None:
            continue
        try:
            lat = float(point["lat"])
            lon = float(point["lon"])
            prob = float(point["prob"])
        except (KeyError, TypeError, ValueError):
            continue
        if not point_in_bbox(lat, lon, bbox):
            continue
        if best is None or prob > best[0]:
            best = (prob, point)
    if best is None:
        return None, None
    return best[0], best[1]


def _coral_signal(bundle: dict, bbox: list[float]) -> tuple[float | None, bool]:
    centroids = bundle.get("centroids") if isinstance(bundle, dict) else None
    models = bundle.get("models") if isinstance(bundle, dict) else None
    lstm = (models or {}).get("lstm") if isinstance(models, dict) else None
    if not isinstance(lstm, dict):
        return None, False
    indexes: list[int] = []
    if isinstance(centroids, list):
        for index, row in enumerate(centroids):
            if not isinstance(row, dict):
                continue
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if point_in_bbox(lat, lon, bbox):
                indexes.append(index)
    if not indexes:
        # Watch intersects the GBR box but a centroid may sit just outside a
        # coarse county bbox — still use the full latest-week series.
        n_series = len(lstm.get("prob_severe") or [])
        indexes = list(range(n_series))
    probs: list[float] = []
    severe_class = False
    prob_series = lstm.get("prob_severe") or []
    class_series = lstm.get("predicted_class") or []
    for index in indexes:
        if index < len(prob_series):
            value = _latest(prob_series[index])
            if value is not None:
                probs.append(float(value))
        if index < len(class_series):
            value = _latest(class_series[index])
            if value is not None and int(value) >= 2:
                severe_class = True
    return (max(probs) if probs else None), severe_class


def load_coral_bundle() -> dict | None:
    try:
        from app.coral_bleaching_loader import get_bundle

        bundle = get_bundle()
    except Exception as exc:
        logger.warning("coral bundle unavailable: %s", exc)
        return None
    return bundle if isinstance(bundle, dict) else None


def _redis_from_app():
    try:
        return getattr(current_app, "redis", None)
    except RuntimeError:
        return None


def _flood_draft(watch: dict, lat: float, lon: float, redis) -> tuple[dict | None, dict]:
    geofence_id = str(watch.get("geofence_id") or watch.get("id") or "watch")
    skip = {
        "geofence_id": geofence_id,
        "endpoint": "POST /api/flood-risk",
        "centroid": {"lat": lat, "lon": lon},
        "skipped": True,
        "reason": FLOOD_SKIP_REASON,
    }
    payload, cache_key = read_flood_cache(redis, lat, lon)
    if payload is None:
        if redis is None:
            skip["reason"] = (
                FLOOD_SKIP_REASON + " (Flask app has no Redis connection)"
            )
        return None, skip
    result = _flood_result(payload)
    bbox = watch.get("bbox")
    if not valid_bbox(bbox):
        skip["reason"] = "county-only watch has no bbox; flood points were not filtered"
        skip["skipped"] = True
        return None, skip
    prob, point = max_in_bbox_prob(result, bbox)
    if prob is None:
        skip["reason"] = "flood-risk cache had no in-polygon points"
        skip["cache_key"] = cache_key
        skip["skipped"] = True
        return None, skip
    warning_at = _env_float("FLOOD_WARNING_PROB", 0.5)
    critical_at = _env_float("FLOOD_CRITICAL_PROB", 0.75)
    if prob >= critical_at:
        severity = "critical"
        threshold = critical_at
    elif prob >= warning_at:
        severity = "warning"
        threshold = warning_at
    else:
        return None, {
            "geofence_id": geofence_id,
            "endpoint": "POST /api/flood-risk",
            "centroid": {"lat": lat, "lon": lon},
            "cache_key": cache_key,
            "max_prob": prob,
            "skipped": False,
            "reason": f"in-polygon max_prob {prob:.2f} below warning threshold {warning_at}",
        }
    synthetic = bool(result.get("synthetic")) or _truthy(os.environ.get("FAST_START_FLOOD_DATA"))
    summary = (
        f"Model: max flood prob {prob:.2f} at ({lat:.2f},{lon:.2f}). "
        "NASA GPM+SMAP, delayed. Not a water-quality lab result."
    )
    if synthetic:
        summary += " Grids are synthetic precip (FAST_START_FLOOD_DATA)."
    evidence = {
        "model": "DualCNN-LSTM",
        "endpoint": "POST /api/flood-risk",
        "max_prob": round(prob, 4),
        "threshold": threshold,
        "inputs": "NASA GPM IMERG + SMAP",
        "latency": "delayed",
        "synthetic": synthetic,
        "trained": True,
        "cache_key": cache_key,
        "businesses_reason": "places lookup not wired in Flask ModelWatch",
    }
    alert_lat = float(point["lat"]) if point else lat
    alert_lon = float(point["lon"]) if point else lon
    return {
        "source": "model",
        "severity": severity,
        "lat": alert_lat,
        "lon": alert_lon,
        "geofence_id": geofence_id,
        "title": f"DualCNN-LSTM flood probability {prob:.2f}",
        "summary": summary,
        "evidence": {**evidence, "raw": evidence},
        "impacted_businesses": [],
        "dedupe_key": f"model:flood-risk:{geofence_id}:{prob:.2f}",
    }, {
        "geofence_id": geofence_id,
        "endpoint": "POST /api/flood-risk",
        "centroid": {"lat": lat, "lon": lon},
        "cache_key": cache_key,
        "max_prob": prob,
        "skipped": False,
        "reason": "cache hit",
    }


def _coral_draft(watch: dict, bundle: dict) -> dict | None:
    bbox = watch.get("bbox")
    if not valid_bbox(bbox) or not boxes_overlap(bbox, GBR_BBOX):
        return None
    geofence_id = str(watch.get("geofence_id") or watch.get("id") or "watch")
    lat, lon = centroid(bbox)
    prob, severe_class = _coral_signal(bundle, bbox)
    warning_at = _env_float("CORAL_WARNING_PROB", 0.5)
    critical_at = _env_float("CORAL_CRITICAL_PROB", 0.75)
    tripped = severe_class or (prob is not None and prob > warning_at)
    if not tripped:
        return None
    if severe_class or (prob is not None and prob >= critical_at):
        severity = "critical"
    else:
        severity = "warning"
    shown = 0.0 if prob is None else prob
    evidence = {
        "model": "gbr-lstm",
        "endpoint": "GET /api/coral-bleaching",
        "prob_severe": None if prob is None else round(prob, 4),
        "threshold": warning_at,
        "inputs": "GBR weekly CSV bundle (on disk)",
        "latency": "delayed",
        "synthetic": False,
        "trained": True,
        "businesses_reason": "places lookup not wired in Flask ModelWatch",
    }
    return {
        "source": "model",
        "severity": severity,
        "lat": lat,
        "lon": lon,
        "geofence_id": geofence_id,
        "title": f"Coral bleaching {severity}",
        "summary": (
            f"Coral bleaching latest-week prob_severe {shown:.2f} on the GBR LSTM. "
            "On-disk weekly CSVs, delayed. Not a water-quality lab result."
        ),
        "evidence": {**evidence, "raw": evidence},
        "impacted_businesses": [],
        "dedupe_key": f"model:coral-bleaching:{geofence_id}:{shown:.2f}",
    }


def poll_once(
    redis=None,
    *,
    now: float | None = None,
    coral_bundle: dict | None = None,
    watches: list[dict] | None = None,
    require_model_source: bool = True,
) -> dict:
    """One pass over watches whose sources include `model`. Cache-only flood."""
    redis = _redis_from_app() if redis is None else redis
    now = time.time() if now is None else now
    posted: list[dict] = []
    skipped: list[dict] = []
    coral_loaded = coral_bundle
    coral_load_attempted = coral_bundle is not None
    for watch in (watches if watches is not None else list_watches()):
        if require_model_source and "model" not in [
            str(item) for item in (watch.get("sources") or [])
        ]:
            continue
        bbox = watch.get("bbox")
        if not valid_bbox(bbox):
            skipped.append(
                {
                    "geofence_id": watch.get("geofence_id") or watch.get("id"),
                    "skipped": True,
                    "reason": "county-only watch has no bbox",
                }
            )
            continue
        lat, lon = centroid(bbox)
        flood_alert, flood_note = _flood_draft(watch, lat, lon, redis)
        skipped.append(flood_note)
        if flood_alert is not None:
            stored, deduped = publish_alert(flood_alert, now=now)
            if not deduped:
                posted.append(stored)
        if boxes_overlap(bbox, GBR_BBOX):
            if not coral_load_attempted:
                coral_loaded = load_coral_bundle()
                coral_load_attempted = True
            if coral_loaded is None:
                skipped.append(
                    {
                        "geofence_id": watch.get("geofence_id"),
                        "endpoint": "GET /api/coral-bleaching",
                        "skipped": True,
                        "reason": "coral CSV bundle unavailable; skipped live inference",
                    }
                )
            else:
                coral_alert = _coral_draft(watch, coral_loaded)
                if coral_alert is not None:
                    stored, deduped = publish_alert(coral_alert, now=now)
                    if not deduped:
                        posted.append(stored)
    report = {
        "ts": _iso_z(),
        "posted": len(posted),
        "alerts": posted,
        "skipped": skipped,
        "nasa_redownload": False,
        "note": (
            "Flood uses Redis cache from POST /api/flood-risk only. "
            "Missing cache skips DualCNN-LSTM / NASA GPM+SMAP. "
            "Coral uses on-disk GBR CSVs when the watch intersects that basin."
        ),
    }
    with state.lock:
        state.last_poll = report
    return report


def start_modelwatch(app) -> None:
    """Seed demo watches and start the interval loop (not on the request path)."""
    seed_demo_watches()
    if not _truthy(os.environ.get("MODELWATCH_BACKGROUND", "1")):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    interval = _env_float("MODELWATCH_INTERVAL_S", 720.0)

    def _loop() -> None:
        logger.info("modelwatch interval %.0fs (cache-only flood, no NASA redownload)", interval)
        while True:
            try:
                with app.app_context():
                    poll_once()
            except Exception:
                logger.exception("modelwatch poll failed")
            time.sleep(interval)

    thread = threading.Thread(target=_loop, name="modelwatch", daemon=True)
    thread.start()


@bp.route("/watches", methods=["POST"])
def api_create_watch():
    body = request.get_json(silent=True) or {}
    try:
        watch = create_watch(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(watch), 201


@bp.route("/watches", methods=["GET"])
def api_list_watches():
    return jsonify(list_watches())


@bp.route("/watches/<watch_id>/poll-models", methods=["POST"])
def api_poll_models(watch_id: str):
    watch = get_watch(watch_id)
    if watch is None:
        return jsonify({"error": "watch not found"}), 404
    return jsonify(poll_once(watches=[watch], require_model_source=False))


@bp.route("/modelwatch/poll", methods=["POST"])
def api_poll_all():
    return jsonify(poll_once())


@bp.route("/modelwatch/status", methods=["GET"])
def api_status():
    with state.lock:
        last = state.last_poll
    return jsonify(
        {
            "last_poll": last,
            "watches": len(list_watches()),
            "alerts": len(list_alerts()),
            "nasa_redownload": False,
            "flood_mode": "redis-cache-only",
            "coral_mode": "on-disk-csv",
            "note": (
                "If last_poll.skipped lists a missing flood-risk cache, live "
                "DualCNN-LSTM / NASA GPM+SMAP inference was not run."
            ),
        }
    )


@bp.route("/alerts", methods=["POST"])
def api_create_alert():
    body = request.get_json(silent=True) or {}
    for field in ("source", "severity", "lat", "lon", "geofence_id", "title", "summary", "dedupe_key"):
        if field not in body:
            return jsonify({"error": f"{field} is required"}), 400
    alert, deduped = publish_alert(body)
    return jsonify({"alert": alert, "deduped": deduped}), 201


@bp.route("/alerts", methods=["GET"])
def api_list_alerts():
    since = request.args.get("since")
    return jsonify(list_alerts(since))


@bp.route("/alerts/stream", methods=["GET"])
def api_stream_alerts():
    queue = subscribe()

    @stream_with_context
    def events():
        yield ": connected\n\n"
        try:
            while True:
                try:
                    alert = queue.get(timeout=15)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: alert\ndata: {json.dumps(alert)}\n\n"
        finally:
            unsubscribe(queue)

    return Response(
        events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
