"""One ModelWatch pass: centroid sample, then publish model alerts."""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Mapping
from typing import Any, Callable

from modelwatch.clients import PLACE_TYPES

logger = logging.getLogger("modelwatch")

# Great Barrier Reef box from the issue: lon 142..154, lat -24..-10.
GBR_BBOX = [142.0, -24.0, 154.0, -10.0]


def _env_float(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return float(raw)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


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


def point_in_polygon(lat: float, lon: float, coords: list[dict]) -> bool:
    ring: list[tuple[float, float]] = []
    for point in coords:
        if not isinstance(point, dict) or "lat" not in point or "lng" not in point:
            continue
        ring.append((float(point["lng"]), float(point["lat"])))
    if len(ring) < 3:
        return False
    inside = False
    previous = len(ring) - 1
    for index, (lon_i, lat_i) in enumerate(ring):
        lon_j, lat_j = ring[previous]
        crosses = (lat_i > lat) != (lat_j > lat)
        if crosses and lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i:
            inside = not inside
        previous = index
    return inside


def _latest(series: Any) -> Any:
    if not isinstance(series, list):
        return None
    for value in reversed(series):
        if value is not None:
            return value
    return None


def _max_flood_prob(payload: dict) -> tuple[float | None, dict]:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        result = {}
    points = result.get("points") or []
    probs: list[float] = []
    if isinstance(points, list):
        for point in points:
            if isinstance(point, dict) and point.get("prob") is not None:
                probs.append(float(point["prob"]))
    if not probs:
        return None, result
    return max(probs), result


def _coral_signal(bundle: dict) -> tuple[float | None, bool]:
    models = bundle.get("models") if isinstance(bundle, dict) else None
    lstm = (models or {}).get("lstm") if isinstance(models, dict) else None
    if not isinstance(lstm, dict):
        return None, False
    probs: list[float] = []
    for series in lstm.get("prob_severe") or []:
        value = _latest(series)
        if value is not None:
            probs.append(float(value))
    severe_class = False
    for series in lstm.get("predicted_class") or []:
        value = _latest(series)
        if value is not None and int(value) >= 2:
            severe_class = True
            break
    return (max(probs) if probs else None), severe_class


def _slim_businesses(rows: list) -> list[dict]:
    slim: list[dict] = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        slim.append(
            {
                "place_id": row.get("place_id"),
                "name": row.get("name"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "types": row.get("types") or [],
                "phone": row.get("phone"),
            }
        )
    return slim


class Poller:
    def __init__(
        self,
        client: Any,
        *,
        now: Callable[[], float] | None = None,
        dedupe_s: float | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.client = client
        self.now = now or time.time
        self.environ = environ if environ is not None else os.environ
        self.dedupe_s = dedupe_s if dedupe_s is not None else _env_float(self.environ, "MODELWATCH_DEDUPE_S", 3600.0)
        self._seen: dict[str, tuple[str, float]] = {}

    def once(self) -> list[dict]:
        posted: list[dict] = []
        try:
            watches = self.client.list_watches()
        except Exception:
            logger.exception("modelwatch could not list watches")
            return posted
        drought_regions = self._load_drought()
        coral_bundle: dict | None = None
        coral_loaded = False
        for watch in watches:
            if not isinstance(watch, dict):
                continue
            if "model" not in [str(item) for item in (watch.get("sources") or [])]:
                continue
            bbox = watch.get("bbox")
            if not _valid_bbox(bbox):
                logger.info(
                    "skipping watch %s: county-only, no bbox",
                    watch.get("id") or watch.get("geofence_id") or "unknown",
                )
                continue
            lat, lon = centroid(bbox)
            drafts = self._hazards(watch, lat, lon, drought_regions)
            if boxes_overlap(bbox, GBR_BBOX):
                if not coral_loaded:
                    coral_bundle = self._load_coral()
                    coral_loaded = True
                coral = self._coral_draft(watch, lat, lon, coral_bundle or {})
                if coral is not None:
                    drafts.append(coral)
            if not drafts:
                continue
            businesses, reason = self._businesses(bbox)
            for draft in drafts:
                raw = dict(draft["evidence_raw"])
                raw["businesses"] = businesses
                if reason:
                    raw["businesses_reason"] = reason
                alert = {
                    "source": "model",
                    "severity": draft["severity"],
                    "lat": lat,
                    "lon": lon,
                    "geofence_id": draft["geofence_id"],
                    "title": draft["title"],
                    "summary": draft["summary"],
                    "evidence": {"raw": raw},
                    "dedupe_key": draft["dedupe_key"],
                }
                published = self._publish(alert)
                if published is not None:
                    posted.append(published)
        return posted

    def _hazards(
        self,
        watch: dict,
        lat: float,
        lon: float,
        drought_regions: list,
    ) -> list[dict]:
        geofence_id = str(watch.get("geofence_id") or watch.get("id") or "watch")
        drafts: list[dict] = []
        flood = self._flood_draft(geofence_id, lat, lon)
        if flood is not None:
            drafts.append(flood)
        drought = self._drought_draft(geofence_id, lat, lon, drought_regions)
        if drought is not None:
            drafts.append(drought)
        return drafts

    def _flood_draft(self, geofence_id: str, lat: float, lon: float) -> dict | None:
        try:
            payload = self.client.flood_risk(lat, lon)
        except Exception:
            logger.exception("flood-risk failed for %s", geofence_id)
            return None
        prob, result = _max_flood_prob(payload if isinstance(payload, dict) else {})
        if prob is None:
            logger.info("flood-risk for %s returned no points", geofence_id)
            return None
        warning_at = _env_float(self.environ, "FLOOD_WARNING_PROB", 0.5)
        critical_at = _env_float(self.environ, "FLOOD_CRITICAL_PROB", 0.75)
        if prob >= critical_at:
            severity = "critical"
            threshold = critical_at
        elif prob >= warning_at:
            severity = "warning"
            threshold = warning_at
        else:
            return None
        synthetic = bool(result.get("synthetic")) or _truthy(self.environ.get("FAST_START_FLOOD_DATA"))
        summary = (
            f"Flood probability {prob:.2f} from DualCNN-LSTM. "
            "The model is delayed. Inputs are NASA GPM IMERG and SMAP."
        )
        if synthetic:
            summary += " Grids are synthetic."
        return {
            "severity": severity,
            "geofence_id": geofence_id,
            "title": f"Flood model {severity}",
            "summary": summary,
            "dedupe_key": f"model:{geofence_id}:flood",
            "evidence_raw": {
                "hazard": "flood",
                "model": "DualCNN-LSTM",
                "endpoint": "POST /api/flood-risk",
                "max_prob": prob,
                "threshold": threshold,
                "inputs": "NASA GPM IMERG + SMAP",
                "latency": "delayed",
                "synthetic": synthetic,
                "trained": True,
            },
        }

    def _drought_draft(self, geofence_id: str, lat: float, lon: float, regions: list) -> dict | None:
        threshold = _env_float(self.environ, "DROUGHT_WATCH_RISK", 0.7)
        match: dict | None = None
        for region in regions:
            if not isinstance(region, dict):
                continue
            try:
                risk = float(region.get("risk"))
            except (TypeError, ValueError):
                continue
            coords = region.get("coords") or []
            if risk >= threshold and isinstance(coords, list) and point_in_polygon(lat, lon, coords):
                match = region
                break
        if match is None:
            return None
        risk = float(match["risk"])
        name = str(match.get("name") or "unnamed")
        return {
            "severity": "watch",
            "geofence_id": geofence_id,
            "title": "Drought dummy watch",
            "summary": (
                f"Dummy drought polygon {name} risk {risk:.2f}. "
                "This layer is hardcoded and untrained."
            ),
            "dedupe_key": f"model:{geofence_id}:drought",
            "evidence_raw": {
                "hazard": "drought",
                "model": "dummy",
                "endpoint": "GET /api/drought",
                "risk": risk,
                "region": name,
                "threshold": threshold,
                "trained": False,
                "latency": "delayed",
            },
        }

    def _coral_draft(self, watch: dict, lat: float, lon: float, bundle: dict) -> dict | None:
        geofence_id = str(watch.get("geofence_id") or watch.get("id") or "watch")
        prob, severe_class = _coral_signal(bundle)
        warning_at = 0.5
        critical_at = 0.75
        tripped = severe_class or (prob is not None and prob > warning_at)
        if not tripped:
            return None
        if severe_class or (prob is not None and prob >= critical_at):
            severity = "critical"
        else:
            severity = "warning"
        shown = 0.0 if prob is None else prob
        return {
            "severity": severity,
            "geofence_id": geofence_id,
            "title": f"Coral bleaching {severity}",
            "summary": (
                f"Coral bleaching prob_severe {shown:.2f} on the Great Barrier Reef model. "
                "The model is delayed."
            ),
            "dedupe_key": f"model:{geofence_id}:coral",
            "evidence_raw": {
                "hazard": "coral",
                "model": "gbr-lstm",
                "endpoint": "GET /api/coral-bleaching",
                "prob_severe": prob,
                "threshold": warning_at,
                "trained": True,
                "latency": "delayed",
            },
        }

    def _load_drought(self) -> list:
        try:
            regions = self.client.drought()
        except Exception:
            logger.exception("drought lookup failed")
            return []
        return regions if isinstance(regions, list) else []

    def _load_coral(self) -> dict:
        try:
            bundle = self.client.coral()
        except Exception:
            logger.exception("coral lookup failed")
            return {}
        return bundle if isinstance(bundle, dict) else {}

    def _businesses(self, bbox: list[float]) -> tuple[list[dict], str | None]:
        try:
            payload = self.client.businesses(bbox, PLACE_TYPES)
        except Exception:
            logger.exception("places lookup failed")
            return [], "places lookup failed"
        if not isinstance(payload, dict):
            return [], "places lookup failed"
        rows = payload.get("businesses") or []
        if not isinstance(rows, list):
            rows = []
        slim = _slim_businesses(rows)
        source = str(payload.get("source") or "")
        if source == "fixture" and not slim:
            return slim, "Places key missing; fixture list was empty inside the polygon"
        if source == "fixture":
            return slim, "Places key missing; fixture roster"
        if not slim:
            return slim, "no businesses inside the polygon"
        return slim, None

    def _publish(self, alert: dict) -> dict | None:
        key = alert["dedupe_key"]
        severity = alert["severity"]
        previous = self._seen.get(key)
        now = self.now()
        if previous is not None:
            last_severity, last_at = previous
            if last_severity == severity and (now - last_at) < self.dedupe_s:
                return None
        self.client.publish(alert)
        self._seen[key] = (severity, now)
        return alert


def _valid_bbox(bbox: Any) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        min_lon, min_lat, max_lon, max_lat = (float(item) for item in bbox)
    except (TypeError, ValueError):
        return False
    return min_lon < max_lon and min_lat < max_lat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="modelwatch.poll")
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("pass --once, or run python -m modelwatch.loop")
    logging.basicConfig(level=logging.INFO)
    from modelwatch.clients import HttpClients

    posted = Poller(HttpClients()).once()
    print(f"posted {len(posted)} alert(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
