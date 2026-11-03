"""Map grok_client labels onto the #17 alert classes.

Live frames go through ``grok_client.classify_frame`` (env or the gitignored
.env). The filename/sidecar fallback runs only when that call raises
``GrokClientError``, or when the caller asked for the fixture classifier.

grok_client label → alert class:
  dry              → all_clear
  wet              → standing_water
  standing water   → standing_water
  impassable       → overtopped_road
  people in water  → overtopped_road
Debris and smoke stay on the fixture path; grok_client does not emit them.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import grok_client
from grok_client import GrokClientError

from camwatch.model import (
    DEFAULT_SUMMARY,
    Frame,
    VisionResult,
    canonical_class,
)

# Shared with the chat proxy (#33). Unset means 2/min: one camera at the slow
# end of the 15–30s sample window. Not a second CamWatch-only counter.
DEFAULT_GROK_MAX_RPM = 2

logger = logging.getLogger("camwatch")

# grok_client.LABELS → issue #17 alert vocabulary. Do not replace the schema.
GROK_LABEL_TO_CLASS = {
    "dry": "all_clear",
    "wet": "standing_water",
    "standing water": "standing_water",
    "impassable": "overtopped_road",
    "people in water": "overtopped_road",
}

# First match wins. "flooded-road" must beat a generic "water" token.
_FILENAME_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("flooded-road", "flooded", "flood", "overtop"), "overtopped_road"),
    (("standing-water", "standing"), "standing_water"),
    (("debris", "wreckage"), "debris"),
    (("smoke", "fire"), "smoke"),
    (("all-clear", "all_clear", "clear", "dry"), "all_clear"),
    (("water",), "standing_water"),
)


class VisionError(Exception):
    pass


def grok_max_rpm(env: dict[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    raw = (source.get("GROK_MAX_RPM") or "").strip()
    if not raw:
        return DEFAULT_GROK_MAX_RPM
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("GROK_MAX_RPM is not an integer; Grok vision is off")
        return 0


def build_classifier(env: dict[str, str] | None = None, *, fixture: bool = False) -> "Classifier":
    """Live path uses grok_client. An explicit fixture env does not call xAI.

    ``env={}`` or ``fixture=True`` is the flooded-road test path. ``env is
    None`` (the CLI default) lets grok_client read the process environment
    and, if that is empty, the gitignored .env file.
    """
    fallback = FallbackVision()
    if fixture:
        return fallback
    if env is not None and (not (env.get("XAI_API_KEY") or "").strip() or grok_max_rpm(env) <= 0):
        return fallback
    rpm = grok_max_rpm(None if env is None else env)
    return LiveGrokVision(fallback=fallback, rpm=rpm)


class Classifier:
    def classify(self, frame: Frame) -> VisionResult:
        raise NotImplementedError


class FallbackVision(Classifier):
    """Offline classifier for the demo inject and missing-key path."""

    def classify(self, frame: Frame) -> VisionResult:
        sidecar = _read_sidecar(frame.path)
        if sidecar is not None:
            return sidecar
        name = (frame.filename or "").lower()
        for tokens, vision_class in _FILENAME_RULES:
            if any(token in name for token in tokens):
                return VisionResult(
                    vision_class=vision_class,
                    confidence=0.99,
                    summary=DEFAULT_SUMMARY[vision_class],
                    uncertain=False,
                    backend="fallback",
                )
        return VisionResult(
            vision_class="all_clear",
            confidence=0.2,
            summary="Vision: no hazard keyword and no Grok vision result.",
            uncertain=True,
            backend="fallback",
        )


class LiveGrokVision(Classifier):
    """One grok_client call per frame. Fixture labels only after GrokClientError."""

    def __init__(
        self,
        fallback: FallbackVision | None = None,
        classify_frame=grok_client.classify_frame,
        rpm: int | None = DEFAULT_GROK_MAX_RPM,
        clock=time.monotonic,
    ) -> None:
        self.fallback = fallback
        self._classify_frame = classify_frame
        self._rpm = rpm
        self._clock = clock
        self._calls: list[float] = []

    def classify(self, frame: Frame) -> VisionResult:
        if not self._allow():
            # Do not relabel a live still from its filename just because the cap is full.
            raise VisionError("GROK_MAX_RPM reached")
        name = frame.camera_name or frame.filename or "camera"
        try:
            label = self._classify_frame(frame.jpeg, name)
            return result_from_grok_label(label)
        except GrokClientError:
            logger.warning("grok vision failed; using fixture fallback")
            if self.fallback is None:
                raise
            return self.fallback.classify(frame)

    def _allow(self) -> bool:
        if self._rpm is None:
            return True
        if self._rpm <= 0:
            return False
        now = self._clock()
        self._calls = [stamp for stamp in self._calls if now - stamp < 60.0]
        if len(self._calls) >= self._rpm:
            return False
        self._calls.append(now)
        return True


def result_from_grok_label(label: str) -> VisionResult:
    vision_class = GROK_LABEL_TO_CLASS.get(label.strip().lower())
    if vision_class is None:
        raise GrokClientError("xAI vision returned an unrecognized label")
    summary = DEFAULT_SUMMARY[vision_class]
    if label.strip().lower() == "people in water":
        summary = "Vision: people in water on the roadway."
    elif label.strip().lower() == "wet":
        summary = "Vision: roadway looks wet; standing water is not clearly overtopped."
    return VisionResult(
        vision_class=vision_class,
        confidence=0.9,
        summary=summary,
        uncertain=False,
        backend="grok",
    )


def _read_sidecar(path: Path | None) -> VisionResult | None:
    if path is None:
        return None
    sidecar = path.with_name(path.name + ".json")
    if not sidecar.is_file():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    vision_class = canonical_class(str(data.get("class", "")))
    if vision_class is None:
        raise VisionError(f"sidecar {sidecar.name} has an unknown class")
    confidence = float(data.get("confidence", 0.99))
    summary = str(data.get("summary") or DEFAULT_SUMMARY[vision_class])
    return VisionResult(
        vision_class=vision_class,
        confidence=max(0.0, min(1.0, confidence)),
        summary=summary,
        uncertain=bool(data.get("uncertain", False)),
        backend="fallback",
    )
