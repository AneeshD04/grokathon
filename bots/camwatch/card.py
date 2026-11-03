"""One-pass spoken demo. One still, one vision call, then stop.

Uses the CamWatch camera file, JPEG fetch, and ``grok_client.classify_frame``.
The filename fixture runs only when that call raises ``GrokClientError``, or
when the caller passes ``fixture=True`` (the existing ``--fixture`` switch).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path

import grok_client
from grok_client import GrokClientError

from camwatch.config import load_config
from camwatch.model import Camera, Frame
from camwatch.sources import FrameFetchError, frames_for_camera
from camwatch.vision import FallbackVision
from demo_card import demo_line, sensor_line

logger = logging.getLogger("camwatch")

_DEFAULT_CAMERAS = Path(__file__).resolve().parent.parent / "data" / "camwatch_default.json"


class CardError(Exception):
    """A demo pass could not finish. The message never includes the API key."""


def load_demo_cameras(path: Path | None = None) -> list[Camera]:
    """Load the Houston demo list. The checked-in file has 8 cameras."""
    target = _DEFAULT_CAMERAS if path is None else path
    return list(load_config(target).cameras)


def run_card(
    *,
    cameras_path: Path | None = None,
    camera_id: str | None = None,
    fixture: bool = False,
    fetcher=None,
    classify_frame=None,
    load_warnings=None,
    cameras: list[Camera] | None = None,
) -> str:
    """Fetch one still, classify it once, and return the spoken card text.

    The default camera is the first entry (Galveston Ferry). This function
    does not sleep and does not sample the rest of the list.
    """
    chosen = list(cameras) if cameras is not None else load_demo_cameras(cameras_path)
    if not chosen:
        raise CardError("camera list is empty")
    camera = _select(chosen, camera_id)
    if fetcher is None:
        from camwatch.sources import fetch_jpeg as fetcher
    classify = classify_frame if classify_frame is not None else grok_client.classify_frame
    warnings = load_warnings if load_warnings is not None else _load_flood_warnings
    frame = _one_frame(camera, fetcher)
    label = _label_for(frame, fixture=fixture, classify_frame=classify)
    warning = _warning(warnings)
    return format_card(camera.name, label, warning)


def format_card(camera_name: str, label: str, warning: dict | None) -> str:
    lines = (
        f"camera: {camera_name}",
        f"label: {label}",
        f"sensor: {sensor_line(warning)}",
        demo_line(label, warning),
    )
    return "\n".join(lines) + "\n"


def pick_sensor(points) -> dict | None:
    """Prefer flood sensor 145 (JF13-3), then any gauge above its bank."""
    if not isinstance(points, list):
        return None
    records = [item for item in points if isinstance(item, dict)]
    for point in records:
        if str(point.get("id", "")) == "145":
            return point
    for point in records:
        water = point.get("water_level")
        bank = point.get("bank_height")
        if isinstance(water, (int, float)) and isinstance(bank, (int, float)) and water > bank:
            return point
    return records[0] if records else None


def redact(text: str) -> str:
    """Drop ``XAI_API_KEY`` if it ever shows up in an error string."""
    secret = os.environ.get("XAI_API_KEY") or ""
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def _select(cameras: list[Camera], camera_id: str | None) -> Camera:
    if not camera_id:
        return cameras[0]
    for camera in cameras:
        if camera.id == camera_id:
            return camera
    raise CardError(f"camera {camera_id} is not in the demo list")


def _one_frame(camera: Camera, fetcher) -> Frame:
    if not camera.still_url and camera.inbox_dir is None:
        raise CardError(f"camera {camera.id} has no still")
    try:
        frames = frames_for_camera(camera, fetcher=fetcher)
    except FrameFetchError as exc:
        raise CardError(redact(str(exc))) from None
    if not frames:
        raise CardError(f"camera {camera.id} returned no JPEG")
    return replace(frames[0], camera_name=camera.name)


def _label_for(frame: Frame, *, fixture: bool, classify_frame) -> str:
    if fixture:
        return FallbackVision().classify(frame).vision_class
    name = frame.camera_name or frame.filename or "camera"
    try:
        label = classify_frame(frame.jpeg, name)
    except GrokClientError as exc:
        logger.warning("grok vision failed; using fixture fallback: %s", redact(str(exc)))
        return FallbackVision().classify(frame).vision_class
    if not isinstance(label, str) or not label.strip():
        raise CardError("vision returned an empty label")
    return label.strip()


def _warning(load_warnings) -> dict | None:
    try:
        points = load_warnings()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("flood warnings unavailable: %s", redact(str(exc)))
        return None
    return pick_sensor(points)


def _load_flood_warnings():
    from feeds.flood_warnings import load_warnings

    return load_warnings()
