"""Houston/coastal camera catalog: bbox list + JPEG still proxy. No Grok."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import jsonify, request, Response

SEED_PATH = Path(__file__).resolve().with_name("houston_coastal.json")
STILL_TIMEOUT_S = 8
STILL_MAX_BYTES = 2_000_000
ALLOWED_STILL_HOSTS = frozenset(
    {
        "www.houstontranstar.org",
        "houstontranstar.org",
        "images-dis.divas.cloud",
    }
)

_catalog_cache: list[dict] | None = None


def load_catalog(path: Path | None = None) -> list[dict]:
    """Return seeded cameras. Cached after the first successful read."""
    global _catalog_cache
    seed = path or SEED_PATH
    if path is None and _catalog_cache is not None:
        return _catalog_cache
    raw = json.loads(seed.read_text(encoding="utf-8"))
    cameras = [normalize_camera(item) for item in raw if isinstance(item, dict)]
    cameras = [camera for camera in cameras if camera is not None]
    if path is None:
        _catalog_cache = cameras
    return cameras


def normalize_camera(item: dict) -> dict | None:
    try:
        camera_id = str(item["id"]).strip()
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not camera_id:
        return None
    still_url = item.get("still_url") or item.get("image_url")
    return {
        "id": camera_id,
        "name": str(item.get("name") or camera_id),
        "lat": lat,
        "lon": lon,
        "still_url": still_url,
        "hls_url": item.get("hls_url"),
        "source": str(item.get("source") or "unknown"),
        "coastal": bool(item.get("coastal", False)),
    }


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Parse bbox=minLon,minLat,maxLon,maxLat."""
    if not raw:
        return None
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError:
        return None
    if min_lon > max_lon or min_lat > max_lat:
        return None
    return min_lon, min_lat, max_lon, max_lat


def in_bbox(camera: dict, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= camera["lon"] <= max_lon and min_lat <= camera["lat"] <= max_lat


def cameras_in_bbox(
    bbox: tuple[float, float, float, float],
    path: Path | None = None,
) -> list[dict]:
    return [camera for camera in load_catalog(path) if in_bbox(camera, bbox)]


def camera_by_id(camera_id: str, path: Path | None = None) -> dict | None:
    wanted = str(camera_id).strip()
    for camera in load_catalog(path):
        if camera["id"] == wanted:
            return camera
    return None


def list_cameras():
    """GET /api/cameras?bbox=minLon,minLat,maxLon,maxLat"""
    bbox = parse_bbox(request.args.get("bbox"))
    if bbox is None:
        return jsonify(
            {"error": "bbox=minLon,minLat,maxLon,maxLat is required"}
        ), 400
    cameras = cameras_in_bbox(bbox)
    return jsonify({"bbox": list(bbox), "count": len(cameras), "cameras": cameras})


def proxy_still(camera_id: str):
    """GET /api/cameras/<id>/still — catalog URL only, no Grok."""
    camera = camera_by_id(camera_id)
    if camera is None:
        return jsonify({"error": "camera not found"}), 404
    still_url = camera.get("still_url")
    if not still_url:
        return jsonify({"error": "camera has no still_url"}), 404
    host = urlparse(still_url).hostname or ""
    if host not in ALLOWED_STILL_HOSTS:
        return jsonify({"error": "still host is not in the seed allowlist"}), 403
    try:
        upstream = requests.get(
            still_url,
            timeout=STILL_TIMEOUT_S,
            stream=True,
            allow_redirects=False,
        )
    except requests.RequestException:
        return jsonify({"error": "still fetch failed"}), 502
    if upstream.status_code != 200:
        return jsonify({"error": "still upstream error"}), 502
    body = upstream.content[: STILL_MAX_BYTES + 1]
    if len(body) > STILL_MAX_BYTES:
        return jsonify({"error": "still too large"}), 502
    content_type = upstream.headers.get("Content-Type", "image/jpeg")
    return Response(body, status=200, mimetype=content_type.split(";")[0].strip())
