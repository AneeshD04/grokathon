# Live URL: https://traffic.houstontranstar.org/roadwayfloodwarning/api/floodalert?timestamp=
# HTTP status: 200 (urllib, 2026-11-03). bots/data/flood_warnings.json is that live response.
# https://traffic.houstontranstar.org/api/roadwayfloodwarning.json returned HTTP 403 (empty body).
# The Feb 2024 sample roadwayfloodwarning_sample.json was not used.

"""Houston TranStar roadway flood-warning sensor points (not cameras)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

LIVE_URL = (
    "https://traffic.houstontranstar.org/roadwayfloodwarning/api/floodalert?timestamp="
)
TIMEOUT_S = 20
_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "flood_warnings.json"


def load_warnings():
    """Return flood-warning sensor points, live first, then the saved JSON."""
    try:
        payload = _fetch_json(LIVE_URL)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError, TypeError):
        return _load_saved()
    return _normalize(payload, source="live")


def _fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "grokathon-flood-warnings/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise urllib.error.HTTPError(
                url, status, f"HTTP {status}", response.headers, None
            )
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def _load_saved():
    with _DATA_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("result", data.get("points", []))
        if not isinstance(data, list):
            return _normalize(data, source="sample") if isinstance(data, dict) else []
        if data and isinstance(data[0], dict) and "source" in data[0]:
            return data
        return _normalize(data, source="sample")
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "source" in data[0] and "lat" in data[0]:
            return data
        return _normalize(data, source="sample")
    return []


def _normalize(payload, source):
    points = []
    for record in _records(payload):
        if not isinstance(record, dict):
            continue
        point = _point(record, source)
        if point is not None:
            points.append(point)
    return points


def _records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("result", "points", "data", "Results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if "Latitude" in payload or "lat" in payload:
            return [payload]
    return []


def _point(record, source):
    lat = _number(record, "Latitude", "lat", "latitude")
    lon = _number(record, "Longitude", "lon", "longitude", "lng")
    if lat is None or lon is None:
        return None
    point = {"id": _identifier(record)}
    name = _text(record, "SensorName", "Name", "name")
    road = _text(record, "Road", "road", "RoadName", "Roadway")
    if name:
        point["name"] = name
    elif road:
        point["road"] = road
    point["lat"] = lat
    point["lon"] = lon
    water_level = _number(
        record,
        "StreamElevationLatestValue",
        "water_level",
        "WaterLevel",
    )
    if water_level is not None:
        point["water_level"] = water_level
    bank_height = _number(record, "TopOfBank", "bank_height", "BankHeight")
    if bank_height is not None:
        point["bank_height"] = bank_height
    point["status"] = _status(record)
    point["source"] = source
    observed_at = _text(
        record,
        "StreamElevationLatestTimestamp",
        "Timestamp",
        "observed_at",
    )
    if observed_at:
        point["observed_at"] = observed_at
    return point


def _identifier(record):
    for key in ("SensorId", "id", "Id", "ID"):
        if key in record and record[key] not in (None, ""):
            return str(record[key])
    name = _text(record, "SensorName", "Name", "name")
    return name or ""


def _status(record):
    if "status" in record and isinstance(record["status"], str) and record["status"]:
        return record["status"]
    stream = _flag(record.get("IsStreamElevationAlert"))
    precip = _flag(record.get("IsPrecipitationAlert"))
    if stream and precip:
        return "stream_elevation_alert,precipitation_alert"
    if stream:
        return "stream_elevation_alert"
    if precip:
        return "precipitation_alert"
    return "normal"


def _flag(value):
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return value is True or value == 1


def _number(record, *keys):
    for key in keys:
        if key not in record or record[key] in (None, ""):
            continue
        try:
            return float(record[key])
        except (TypeError, ValueError):
            continue
    return None


def _text(record, *keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
