# ArcGIS query: https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query?f=json&where=COUNTY+%3D+%27Pinellas%27+AND+ID+IN+%28%271004%27%2C+%271006%27%2C+%273066%27%2C+%27689%27%2C+%27897%27%2C+%27916%27%2C+%27917%27%2C+%27918%27%2C+%27920%27%2C+%273226%27%2C+%272665%27%2C+%27727%27%29&outFields=ID%2CDESCRIPT%2CCOUNTY%2CHIGHWAY%2CDIRECTION%2CLATITUDE%2CLONGITUDE%2CIMAGE&returnGeometry=false&orderByFields=ID&resultRecordCount=12
# ArcGIS HTTP status: 200
# JPEG URL: https://images-dis.divas.cloud/DGI/chan-10460_h.jpg
# JPEG HTTP status: 200

"""Pinellas County FL511 cameras from the public FDOT ArcGIS layer.

No API key. ``load_seed`` reads the coastal snapshot in
``bots/data/fl511_cameras.json``. ``refresh`` re-queries those cameras
on the FL511 FeatureServer. ``download_jpeg`` fetches one IMAGE still
with the stdlib HTTP client (20s timeout).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

ARCGIS_QUERY_URL = (
    "https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/"
    "FL511_Traffic_Cameras/FeatureServer/0/query"
)
COUNTY = "Pinellas"
TIMEOUT_SECONDS = 20.0
CAMERA_LIMIT = 12
USER_AGENT = "grokathon-fl511/0.1"

# Courtney Campbell Causeway, Bayside Bridge, Gandy / Brighton Bay,
# Pinellas Bayway (Delgado bridge, Sun Blvd, toll plaza, 54th Ave S),
# the SR 679 bridge toward Fort De Soto, and south I-275.
COASTAL_CAMERA_IDS: tuple[str, ...] = (
    "1004",
    "1006",
    "3066",
    "689",
    "897",
    "916",
    "917",
    "918",
    "920",
    "3226",
    "2665",
    "727",
)

_FIELDS = "ID,DESCRIPT,COUNTY,HIGHWAY,DIRECTION,LATITUDE,LONGITUDE,IMAGE"
_REQUIRED = ("id", "name", "lat", "lon", "image_url", "county")
_MAX_JPEG_BYTES = 5 * 1024 * 1024


class Fl511Camera(TypedDict):
    id: str
    name: str
    lat: float
    lon: float
    image_url: str
    county: str


class Fl511Error(Exception):
    """The ArcGIS query or a JPEG download failed."""


def seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "fl511_cameras.json"


def load_seed(path: Path | None = None) -> list[Fl511Camera]:
    """Return the checked-in coastal camera list."""
    seed_file = path or seed_path()
    raw = json.loads(seed_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{seed_file} must be a non-empty JSON list")
    cameras: list[Fl511Camera] = []
    for index, record in enumerate(raw):
        if not isinstance(record, Mapping):
            raise ValueError(f"{seed_file} record {index} must be an object")
        missing = [key for key in _REQUIRED if key not in record]
        if missing:
            raise ValueError(f"{seed_file} record {index} missing {', '.join(missing)}")
        image_url = str(record["image_url"]).strip()
        if urllib.parse.urlparse(image_url).scheme not in {"http", "https"}:
            raise ValueError(f"{seed_file} record {index} image_url must be http or https")
        cameras.append(
            {
                "id": str(record["id"]),
                "name": str(record["name"]),
                "lat": float(record["lat"]),
                "lon": float(record["lon"]),
                "image_url": image_url,
                "county": str(record["county"]),
            }
        )
    return cameras


def arcgis_query_url(
    *,
    county: str = COUNTY,
    camera_ids: Sequence[str] = COASTAL_CAMERA_IDS,
    limit: int = CAMERA_LIMIT,
) -> str:
    """FeatureServer query for ``county``, restricted to ``camera_ids``."""
    ids = [_source_id(str(camera_id)) for camera_id in camera_ids]
    ids = [camera_id for camera_id in ids if camera_id]
    if not ids:
        raise ValueError("camera_ids is empty")
    where = "COUNTY = {} AND ID IN ({})".format(
        _quote(county.strip()),
        ", ".join(_quote(camera_id) for camera_id in ids),
    )
    params = {
        "f": "json",
        "where": where,
        "outFields": _FIELDS,
        "returnGeometry": "false",
        "orderByFields": "ID",
        "resultRecordCount": str(max(limit, len(ids))),
    }
    return f"{ARCGIS_QUERY_URL}?{urllib.parse.urlencode(params)}"


def refresh(
    *,
    county: str = COUNTY,
    camera_ids: Sequence[str] = COASTAL_CAMERA_IDS,
    limit: int = CAMERA_LIMIT,
    timeout: float = TIMEOUT_SECONDS,
) -> list[Fl511Camera]:
    """Re-query ArcGIS and return up to ``limit`` cameras in seed order."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    county_name = county.strip()
    if not county_name:
        raise ValueError("county is required")
    ids = [_source_id(str(camera_id)) for camera_id in camera_ids]
    ids = [camera_id for camera_id in ids if camera_id]
    url = arcgis_query_url(county=county_name, camera_ids=ids, limit=limit)
    payload = _read_json(url, timeout)
    features = payload.get("features")
    if not isinstance(features, list):
        raise Fl511Error("ArcGIS response did not include features")
    by_id: dict[str, Fl511Camera] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        attributes = feature.get("attributes")
        if not isinstance(attributes, Mapping):
            continue
        camera = _camera_from_attributes(attributes)
        if camera is None or camera["county"].casefold() != county_name.casefold():
            continue
        by_id[camera["id"]] = camera
    if not by_id:
        raise Fl511Error("ArcGIS returned no cameras")
    ordered = [by_id[f"fl511-{camera_id}"] for camera_id in ids if f"fl511-{camera_id}" in by_id]
    return ordered[:limit]


def download_jpeg(url: str, timeout: float = TIMEOUT_SECONDS) -> tuple[int, bytes]:
    """GET one FL511 still. Returns ``(http_status, jpeg_bytes)``."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("image_url must be http or https")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read(_MAX_JPEG_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise Fl511Error(f"JPEG GET failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise Fl511Error(f"JPEG GET failed: {exc.reason}") from exc
    if status != 200:
        raise Fl511Error(f"JPEG GET failed: HTTP {status}")
    if len(body) > _MAX_JPEG_BYTES:
        raise Fl511Error("JPEG is larger than 5MB")
    if not body.startswith(b"\xff\xd8"):
        raise Fl511Error("response is not a JPEG")
    return status, body


def _camera_from_attributes(attrs: Mapping[str, object]) -> Fl511Camera | None:
    source_id = str(attrs.get("ID") or "").strip()
    image_url = str(attrs.get("IMAGE") or "").strip()
    county = str(attrs.get("COUNTY") or "").strip()
    if not source_id or not county:
        return None
    if urllib.parse.urlparse(image_url).scheme not in {"http", "https"}:
        return None
    lat = _as_float(attrs.get("LATITUDE"))
    lon = _as_float(attrs.get("LONGITUDE"))
    if lat is None or lon is None:
        return None
    return {
        "id": f"fl511-{source_id}",
        "name": _camera_name(attrs, source_id),
        "lat": lat,
        "lon": lon,
        "image_url": image_url,
        "county": county,
    }


def _camera_name(attrs: Mapping[str, object], source_id: str) -> str:
    descript = str(attrs.get("DESCRIPT") or "").strip()
    highway = str(attrs.get("HIGHWAY") or "").strip()
    if descript.lower() == "[not provided]":
        descript = ""
    if descript.startswith("CCC"):
        descript = "Courtney Campbell Causeway" + descript[3:]
    if descript.lower().startswith("at ") and highway:
        return f"{highway} {descript}"
    if descript and highway and highway.lower() not in descript.lower():
        return f"{descript} ({highway})"
    return descript or highway or f"FL511 {source_id}"


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _source_id(camera_id: str) -> str:
    text = camera_id.strip()
    prefix = "fl511-"
    if text.lower().startswith(prefix):
        return text[len(prefix) :]
    return text


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _read_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise Fl511Error(f"ArcGIS query failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise Fl511Error(f"ArcGIS query failed: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise Fl511Error("ArcGIS response was not a JSON object")
    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else error
        raise Fl511Error(f"ArcGIS query failed: {message}")
    return payload


def main() -> None:
    cameras = load_seed()
    print(f"{len(cameras)} {COUNTY} cameras")
    status, body = download_jpeg(cameras[0]["image_url"])
    print(f"JPEG {status} {len(body)} bytes {cameras[0]['image_url']}")


if __name__ == "__main__":
    main()
