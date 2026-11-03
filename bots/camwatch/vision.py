"""Grok vision classifier and the no-key fallback.

MISSING-KEYS.md: XAI_API_KEY is optional. When it is unset, or the vision
call fails, demo frames are classified from a sidecar JSON or the filename
(``flooded-road.jpg`` → overtopped road). That is what makes the #17
done-when pass without a live key.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from camwatch.model import (
    DEFAULT_SUMMARY,
    Frame,
    VisionResult,
    canonical_class,
)

XAI_API_BASE = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4.7"
# Shared with the chat proxy (#33). Unset means 2/min: one camera at the slow
# end of the 15–30s sample window. Not a second CamWatch-only counter.
DEFAULT_GROK_MAX_RPM = 2

logger = logging.getLogger("camwatch")

_SYSTEM = (
    "You classify one traffic or coastal camera frame for a flood safety demo. "
    "Return ONLY JSON with keys class, confidence, summary, uncertain. "
    "class must be one of: standing_water, overtopped_road, debris, smoke, all_clear. "
    "overtopped_road means water is covering the roadway or lanes. "
    "standing_water means water is visible but the road is not clearly overtopped. "
    "debris means storm debris is blocking the road and water is not the main hazard. "
    "smoke means smoke or active fire. "
    "all_clear means none of those. "
    "confidence is 0 to 1. If you cannot tell, set uncertain true, class all_clear, "
    "and confidence below 0.5. Do not invent gauges, water depth, or street names."
)

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


def build_classifier(env: dict[str, str] | None = None) -> "Classifier":
    """Use Grok when XAI_API_KEY is set and GROK_MAX_RPM allows it.

    Missing key, RPM 0, a full minute window, or HTTP 429 all use the
    offline fallback. The response body from xAI is never logged.
    """
    source = os.environ if env is None else env
    fallback = FallbackVision()
    key = (source.get("XAI_API_KEY") or "").strip()
    rpm = grok_max_rpm(source)
    if not key or rpm <= 0:
        return fallback
    return GrokVision(
        api_key=key,
        model=(source.get("XAI_VISION_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        base_url=(source.get("XAI_API_BASE") or XAI_API_BASE).rstrip("/"),
        fallback=fallback,
        rpm=rpm,
    )


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


class GrokVision(Classifier):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = XAI_API_BASE,
        timeout: float = 30.0,
        fallback: FallbackVision | None = None,
        opener=urllib.request.urlopen,
        rpm: int | None = None,
        clock=time.monotonic,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.fallback = fallback
        self._opener = opener
        self._rpm = rpm
        self._clock = clock
        self._calls: list[float] = []

    def classify(self, frame: Frame) -> VisionResult:
        if not self._allow():
            logger.warning("GROK_MAX_RPM reached; using fallback")
            if self.fallback is None:
                raise VisionError("GROK_MAX_RPM reached")
            return self.fallback.classify(frame)
        try:
            return self._call(frame)
        except (VisionError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
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

    def _call(self, frame: Frame) -> VisionResult:
        import base64

        encoded = base64.standard_b64encode(frame.jpeg).decode("ascii")
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Classify this camera frame. JSON only.",
                        },
                    ],
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Status only. The body and the bearer token stay out of the log.
            if exc.code == 429:
                logger.warning("grok vision HTTP 429; using fallback")
            raise VisionError(f"grok vision HTTP {exc.code}") from exc
        content = payload["choices"][0]["message"]["content"]
        return _parse_grok_json(content)


def _parse_grok_json(content: str) -> VisionResult:
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise VisionError("grok vision did not return JSON")
    data = json.loads(text[start : end + 1])
    vision_class = canonical_class(str(data.get("class", "")))
    if vision_class is None:
        raise VisionError("grok vision returned an unknown class")
    try:
        confidence = float(data.get("confidence", 0.8))
    except (TypeError, ValueError) as exc:
        raise VisionError("grok vision confidence was not a number") from exc
    confidence = max(0.0, min(1.0, confidence))
    uncertain = bool(data.get("uncertain", False))
    summary = str(data.get("summary") or DEFAULT_SUMMARY[vision_class]).strip()
    return VisionResult(
        vision_class=vision_class,
        confidence=confidence,
        summary=summary or DEFAULT_SUMMARY[vision_class],
        uncertain=uncertain,
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
