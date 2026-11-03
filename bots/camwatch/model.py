"""Alert payload and camera records for CamWatch.

Field names match docs/SAFETY-AGENT-DESIGN.md and the #11 AlertCreate model:
source, severity, lat, lon, geofence_id, title, summary, evidence, dedupe_key, ts.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Issue #17 and the Safety Agent user story. CAMERA-SOURCES also says "crowd";
# that class is not in #17, so this worker does not emit it.
VISION_CLASSES = (
    "standing_water",
    "overtopped_road",
    "debris",
    "smoke",
    "all_clear",
)

# Shorthand a model might return. Canonical names are VISION_CLASSES.
CLASS_ALIASES = {
    "standing_water": "standing_water",
    "standing water": "standing_water",
    "water": "standing_water",
    "overtopped_road": "overtopped_road",
    "overtopped road": "overtopped_road",
    "overtop": "overtopped_road",
    "overtopped": "overtopped_road",
    "water_over_road": "overtopped_road",
    "water over roadway": "overtopped_road",
    "debris": "debris",
    "smoke": "smoke",
    "all_clear": "all_clear",
    "all-clear": "all_clear",
    "all clear": "all_clear",
    "clear": "all_clear",
}

# severity >= warning is what the Safety Agent treats as notify-worthy.
SEVERITY = {
    "standing_water": "warning",
    "overtopped_road": "critical",
    "debris": "watch",
    "smoke": "warning",
    "all_clear": "info",
}

# Design example: cam:buffalo-1:water_over_road
DEDUPE_SLUG = {
    "standing_water": "standing_water",
    "overtopped_road": "water_over_road",
    "debris": "debris",
    "smoke": "smoke",
    "all_clear": "all_clear",
}

TITLE = {
    "standing_water": "Standing water",
    "overtopped_road": "Water over roadway",
    "debris": "Debris in the roadway",
    "smoke": "Smoke visible",
    "all_clear": "Camera all clear",
}

DEFAULT_SUMMARY = {
    "standing_water": "Vision: standing water visible; roadway not clearly overtopped.",
    "overtopped_road": "Vision: water covering the roadway.",
    "debris": "Vision: debris in the roadway.",
    "smoke": "Vision: smoke visible.",
    "all_clear": "Vision: no standing water, debris, or smoke.",
}

MAX_CAMERAS = 8
MIN_INTERVAL_SECONDS = 15
MAX_INTERVAL_SECONDS = 30
DEFAULT_INTERVAL_SECONDS = 20
MAX_JPEG_BYTES = 5_000_000

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    lat: float
    lon: float
    geofence_id: str
    still_url: str | None = None
    inbox_dir: Path | None = None
    mp4_path: Path | None = None


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    digest: str
    filename: str | None = None
    path: Path | None = None
    thumb_url: str | None = None
    camera_name: str | None = None


@dataclass(frozen=True)
class VisionResult:
    vision_class: str
    confidence: float
    summary: str
    uncertain: bool
    backend: str  # "grok", "fallback", or "heuristic"


def canonical_class(value: str) -> str | None:
    key = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    # CLASS_ALIASES keys use underscores for the canonical tokens and spaces
    # for phrases. Normalize both forms.
    underscored = key.replace(" ", "_")
    if underscored in CLASS_ALIASES:
        return CLASS_ALIASES[underscored]
    if key in CLASS_ALIASES:
        return CLASS_ALIASES[key]
    return None


def check_interval(seconds: float) -> float:
    if seconds < MIN_INTERVAL_SECONDS or seconds > MAX_INTERVAL_SECONDS:
        raise ValueError(
            f"interval must be {MIN_INTERVAL_SECONDS}–{MAX_INTERVAL_SECONDS}s, got {seconds}"
        )
    return seconds


def iso_now(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def new_ulid(ts_ms: int | None = None) -> str:
    """26-char Crockford ULID. The live API mints ids; the file sink needs one."""
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= int.from_bytes(os.urandom(10), "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def severity_for(result: VisionResult) -> str:
    # Uncertain vision must not look like a warning. The design says say so.
    if result.uncertain or result.confidence < 0.5:
        return "info"
    return SEVERITY[result.vision_class]


def should_publish(previous: str | None, vision_class: str) -> bool:
    """POST only on class change. The first all-clear sample is not an alert."""
    if previous == vision_class:
        return False
    if previous is None and vision_class == "all_clear":
        return False
    return True


def build_alert(
    camera: Camera,
    result: VisionResult,
    frame: Frame,
    *,
    ts: str | None = None,
) -> dict:
    summary = result.summary.strip() or DEFAULT_SUMMARY[result.vision_class]
    if result.uncertain and not summary.lower().startswith("uncertain"):
        summary = f"Uncertain. {summary}"
    return {
        "source": "camera",
        "severity": severity_for(result),
        "lat": camera.lat,
        "lon": camera.lon,
        "geofence_id": camera.geofence_id,
        "title": TITLE[result.vision_class],
        "summary": summary,
        "evidence": {
            "thumb_url": frame.thumb_url,
            "raw": {
                "vision_class": result.vision_class,
                "vision_backend": result.backend,
                "confidence": result.confidence,
                "uncertain": result.uncertain,
                "filename": frame.filename,
                "camera_id": camera.id,
                "camera_name": camera.name,
            },
        },
        "dedupe_key": f"cam:{camera.id}:{DEDUPE_SLUG[result.vision_class]}",
        "ts": ts or iso_now(),
    }
