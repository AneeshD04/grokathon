"""Load the local camera list CamWatch samples.

The shared catalog (``shared/cameras/``, issue #9) is not in this lane.
Until that file exists, CamWatch reads a JSON file under ``bots/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from camwatch.model import (
    DEFAULT_INTERVAL_SECONDS,
    MAX_CAMERAS,
    Camera,
    check_interval,
)


@dataclass(frozen=True)
class Config:
    cameras: tuple[Camera, ...]
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    max_cameras: int = MAX_CAMERAS


def load_config(path: Path) -> Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a JSON object")
    default_geofence = str(raw.get("geofence_id") or "houston-demo")
    interval = check_interval(float(raw.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)))
    max_cameras = int(raw.get("max_cameras", MAX_CAMERAS))
    if max_cameras < 1 or max_cameras > MAX_CAMERAS:
        raise ValueError(f"max_cameras must be 1–{MAX_CAMERAS}")
    cameras_raw = raw.get("cameras")
    if not isinstance(cameras_raw, list) or not cameras_raw:
        raise ValueError(f"{path} needs a non-empty cameras list")
    base = path.parent
    cameras = tuple(_camera(item, default_geofence, base) for item in cameras_raw)
    return Config(cameras=cameras, interval_seconds=interval, max_cameras=max_cameras)


def _camera(item: dict, default_geofence: str, base: Path) -> Camera:
    if not isinstance(item, dict):
        raise ValueError("each camera must be an object")
    camera_id = str(item.get("id") or "").strip()
    name = str(item.get("name") or "").strip()
    if not camera_id or not name:
        raise ValueError("camera id and name are required")
    lat = float(item["lat"])
    lon = float(item["lon"])
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"camera {camera_id} lat/lon out of range")
    geofence_id = str(item.get("geofence_id") or default_geofence).strip()
    if not geofence_id:
        raise ValueError(f"camera {camera_id} needs a geofence_id")
    still_url = item.get("still_url") or item.get("still URL") or None
    if isinstance(still_url, str):
        still_url = still_url.strip() or None
    else:
        still_url = None
    inbox_raw = item.get("inbox_dir")
    inbox_dir = None
    if inbox_raw:
        inbox_path = Path(str(inbox_raw))
        if not inbox_path.is_absolute():
            inbox_path = (base / inbox_path).resolve()
        inbox_dir = inbox_path
    if still_url is None and inbox_dir is None:
        raise ValueError(f"camera {camera_id} needs still_url or inbox_dir")
    mp4_path = _local_path(item.get("mp4"), base)
    return Camera(
        id=camera_id,
        name=name,
        lat=lat,
        lon=lon,
        geofence_id=geofence_id,
        still_url=still_url,
        inbox_dir=inbox_dir,
        mp4_path=mp4_path,
    )


def _local_path(raw: object, base: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    if not path.is_absolute():
        path = (base / path).resolve()
    return path
