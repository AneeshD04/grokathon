"""TranStar roadway flood warnings → alert bus.

Imports ``feeds.flood_warnings.load_warnings``. The bus enum has no
``transtar`` value (#8 / #51), so a stream-elevation alert is posted as
``source=usgs`` and ``evidence.raw.feed`` names the TranStar sensor.
"""

from __future__ import annotations

import logging

from camwatch.model import iso_now

logger = logging.getLogger("camwatch")

# Closest allowed bus source until #8 adds a transtar value.
_BUS_SOURCE = "usgs"


def load_flood_warnings():
    from feeds.flood_warnings import load_warnings

    return load_warnings()


def build_flood_alerts(points, *, ts: str | None = None, geofence_id: str = "houston-demo") -> list[dict]:
    """One alert per sensor id that is over bank or already flagged."""
    stamp = ts or iso_now()
    alerts: list[dict] = []
    seen: set[str] = set()
    for point in points:
        if not isinstance(point, dict) or not _alerting(point):
            continue
        sensor_id = str(point.get("id") or "").strip()
        if not sensor_id or sensor_id in seen:
            continue
        seen.add(sensor_id)
        lat = point.get("lat")
        lon = point.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        name = str(point.get("name") or sensor_id)
        status = str(point.get("status") or "alert")
        water = point.get("water_level")
        bank = point.get("bank_height")
        over_bank = _over_bank(water, bank)
        summary = f"TranStar roadway flood warning {name}."
        if isinstance(water, (int, float)) and isinstance(bank, (int, float)):
            relation = "above" if over_bank else "below"
            summary = f"TranStar {name}: water {water} {relation} bank {bank}."
        raw = {
            "feed": "transtar-flood-warning",
            "sensor_id": sensor_id,
            "status": status,
            "sensor_name": name,
        }
        if isinstance(water, (int, float)):
            raw["water_level"] = water
        if isinstance(bank, (int, float)):
            raw["bank_height"] = bank
        observed = point.get("observed_at")
        if isinstance(observed, str) and observed:
            raw["observed_at"] = observed
        alerts.append(
            {
                "source": _BUS_SOURCE,
                "severity": "critical" if over_bank else "warning",
                "lat": float(lat),
                "lon": float(lon),
                "geofence_id": geofence_id,
                "title": f"TranStar flood warning {name}",
                "summary": summary,
                "evidence": {"thumb_url": None, "raw": raw},
                "dedupe_key": f"transtar-flood:{sensor_id}:{status}",
                "ts": stamp,
            }
        )
    return alerts


def publish_new_flood_alerts(publisher, state, points=None) -> list[dict]:
    """POST warnings this process has not already sent. Same id is one alert."""
    if points is None:
        try:
            points = load_flood_warnings()
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("flood warnings unavailable: %s", exc)
            return []
    published: list[dict] = []
    for alert in build_flood_alerts(points):
        key = alert["dedupe_key"]
        if key in state.flood_keys:
            continue
        publisher.publish(alert)
        state.flood_keys.append(key)
        published.append(alert)
        logger.info("flood alert %s", key)
    return published


def _alerting(point: dict) -> bool:
    status = str(point.get("status") or "").lower()
    if "alert" in status:
        return True
    return _over_bank(point.get("water_level"), point.get("bank_height"))


def _over_bank(water, bank) -> bool:
    return isinstance(water, (int, float)) and isinstance(bank, (int, float)) and water > bank
