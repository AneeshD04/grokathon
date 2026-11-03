"""Turn NWS / USGS payloads into the Safety Agent alert shape."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def nws_severity(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    if key in {"extreme", "severe"}:
        return "critical"
    if key in {"moderate"}:
        return "warning"
    if key in {"minor"}:
        return "watch"
    return "info"


def polygon_centroid(geometry: Any) -> tuple[float, float] | None:
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    ring: list = []
    if geometry.get("type") == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0] if isinstance(coords[0], list) else []
    elif geometry.get("type") == "MultiPolygon" and isinstance(coords, list) and coords:
        first = coords[0]
        ring = first[0] if isinstance(first, list) and first else []
    lats: list[float] = []
    lons: list[float] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lons.append(float(point[0]))
            lats.append(float(point[1]))
        except (TypeError, ValueError):
            continue
    if not lats:
        return None
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def point_in_bbox(lat: float, lon: float, bbox: list[float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def boxes_overlap(left: list[float], right: list[float]) -> bool:
    return (
        left[0] < right[2]
        and left[2] > right[0]
        and left[1] < right[3]
        and left[3] > right[1]
    )


def geometry_bbox(geometry: Any) -> list[float] | None:
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    points: list = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)) and len(node) >= 2 and not isinstance(node[0], (list, tuple)):
            points.append(node)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)

    walk(coords)
    lons: list[float] = []
    lats: list[float] = []
    for point in points:
        try:
            lons.append(float(point[0]))
            lats.append(float(point[1]))
        except (TypeError, ValueError, IndexError):
            continue
    if not lats:
        return None
    return [min(lons), min(lats), max(lons), max(lats)]


def alert_intersects_bbox(geometry: Any, lat: float | None, lon: float | None, bbox: list[float]) -> bool:
    geom_box = geometry_bbox(geometry)
    if geom_box is not None:
        return boxes_overlap(geom_box, bbox)
    if lat is not None and lon is not None:
        return point_in_bbox(lat, lon, bbox)
    return False


def nws_id(properties: dict) -> str:
    raw = properties.get("id") or properties.get("@id") or ""
    text = str(raw)
    if "urn:oid:" in text:
        return text.split("urn:oid:", 1)[-1].replace(".", "-")[-48:]
    return text.rsplit("/", 1)[-1][-48:] or "unknown"


def normalize_nws_feature(feature: dict, *, geofence_id: str, bbox: list[float]) -> dict | None:
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    geometry = feature.get("geometry")
    center = polygon_centroid(geometry)
    lat = center[0] if center else None
    lon = center[1] if center else None
    if not alert_intersects_bbox(geometry, lat, lon, bbox):
        return None
    if lat is None or lon is None:
        lat = (bbox[1] + bbox[3]) / 2.0
        lon = (bbox[0] + bbox[2]) / 2.0
    event = str(props.get("event") or "NWS alert")
    headline = str(props.get("headline") or props.get("description") or event)
    nws_id_value = nws_id(props)
    return {
        "source": "nws",
        "severity": nws_severity(props.get("severity")),
        "lat": lat,
        "lon": lon,
        "geofence_id": geofence_id,
        "title": event,
        "summary": headline[:400],
        "evidence": {
            "raw": {
                "hazard": event,
                "nws_id": props.get("id"),
                "area": props.get("areaDesc"),
                "sent": props.get("sent") or props.get("effective"),
                "expires": props.get("expires"),
                "status": props.get("status"),
                "endpoint": "https://api.weather.gov/alerts/active",
                "cached": True,
            }
        },
        "dedupe_key": f"nws:{nws_id_value}",
        "ts": utc_now(),
    }


def normalize_nws_collection(payload: dict, *, geofence_id: str, bbox: list[float]) -> list[dict]:
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return []
    alerts: list[dict] = []
    for feature in features:
        alert = normalize_nws_feature(feature, geofence_id=geofence_id, bbox=bbox)
        if alert is not None:
            alerts.append(alert)
    return alerts


def _latest_usgs_value(series: dict) -> tuple[float | None, str | None]:
    values = series.get("values") if isinstance(series, dict) else None
    if not isinstance(values, list) or not values:
        return None, None
    points = values[0].get("value") if isinstance(values[0], dict) else None
    if not isinstance(points, list) or not points:
        return None, None
    last = points[-1]
    if not isinstance(last, dict):
        return None, None
    try:
        return float(last.get("value")), str(last.get("dateTime") or "")
    except (TypeError, ValueError):
        return None, None


def normalize_usgs_series(
    series: dict,
    *,
    geofence_id: str,
    bbox: list[float],
    flood_stage_ft: float,
) -> dict | None:
    if not isinstance(series, dict):
        return None
    info = series.get("sourceInfo") if isinstance(series.get("sourceInfo"), dict) else {}
    geo = info.get("geoLocation", {}).get("geogLocation", {}) if isinstance(info.get("geoLocation"), dict) else {}
    try:
        lat = float(geo.get("latitude"))
        lon = float(geo.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not point_in_bbox(lat, lon, bbox):
        return None
    value, when = _latest_usgs_value(series)
    if value is None or value < flood_stage_ft:
        return None
    codes = info.get("siteCode") or []
    site = ""
    if isinstance(codes, list) and codes and isinstance(codes[0], dict):
        site = str(codes[0].get("value") or "")
    name = str(info.get("siteName") or f"USGS {site}" or "USGS gauge")
    over = value - flood_stage_ft
    severity = "critical" if over >= 2.0 else "warning"
    return {
        "source": "usgs",
        "severity": severity,
        "lat": lat,
        "lon": lon,
        "geofence_id": geofence_id,
        "title": f"{name} above flood stage",
        "summary": (
            f"USGS gage height {value:.2f} ft is {over:.2f} ft above the "
            f"{flood_stage_ft:.1f} ft flood stage. Not a DualCNN-LSTM result."
        ),
        "evidence": {
            "raw": {
                "hazard": "gauge",
                "site": site,
                "site_name": name,
                "gage_height_ft": value,
                "flood_stage_ft": flood_stage_ft,
                "observed_at": when,
                "endpoint": "https://waterservices.usgs.gov/nwis/iv/",
                "cached": True,
            }
        },
        "dedupe_key": f"usgs:{site or name}:00065",
        "ts": utc_now(),
    }


def normalize_usgs_collection(
    payload: dict,
    *,
    geofence_id: str,
    bbox: list[float],
    flood_stage_ft: float,
) -> list[dict]:
    value = payload.get("value") if isinstance(payload, dict) else None
    series_list = value.get("timeSeries") if isinstance(value, dict) else None
    if not isinstance(series_list, list):
        return []
    alerts: list[dict] = []
    for series in series_list:
        alert = normalize_usgs_series(
            series,
            geofence_id=geofence_id,
            bbox=bbox,
            flood_stage_ft=flood_stage_ft,
        )
        if alert is not None:
            alerts.append(alert)
    return alerts
