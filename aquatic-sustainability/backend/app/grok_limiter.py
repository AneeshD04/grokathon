"""Flask-side Grok/xAI usage cap (issue #33).

Same env name as CamWatch: ``GROK_MAX_RPM`` (default 2). This is not a
second counter and not a Grok swarm — concurrent calls default to 1.

This module never talks to api.x.ai. Callers pass a mockable callable.
PIN dry-run notify must use ``pin_notify_body`` (no Grok).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DEFAULT_GROK_MAX_RPM = 2
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_CACHE_TTL_S = 600.0

TEMPLATES = {
    "chat": (
        "Safety Agent is on a template fallback (Grok cap or 429). "
        "DualCNN-LSTM flood risk is unchanged. Confirm before any notify."
    ),
    "draft_alert": (
        "WARNING: flood risk in the watched county. Secure vessels / move "
        "inventory upland. This is a drafted OEM notice — not sent."
    ),
    "flood_risk": (
        "Cached flood-risk only. DualCNN-LSTM probability for this point is "
        "unchanged. Not a water-quality lab result."
    ),
    "nws": (
        "Use the cached NWS / api.weather.gov product for this point. "
        "Grok did not rewrite it."
    ),
    "notify": "{severity} for {place}: {summary}",
}


@dataclass(frozen=True)
class GrokResult:
    text: str
    source: str  # grok | cache | template
    purpose: str
    degraded: bool
    reason: str | None = None


def grok_max_rpm(env: dict[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    raw = (source.get("GROK_MAX_RPM") or "").strip()
    if not raw:
        return DEFAULT_GROK_MAX_RPM
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def grok_max_concurrent(env: dict[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    raw = (source.get("GROK_MAX_CONCURRENT") or "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENT
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CONCURRENT


def grok_cache_ttl_s(env: dict[str, str] | None = None) -> float:
    source = os.environ if env is None else env
    raw = (source.get("GROK_CACHE_TTL_S") or "").strip()
    if not raw:
        return DEFAULT_CACHE_TTL_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_S


def fast_start(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return (source.get("FAST_START") or "").strip().lower() in ("1", "true", "yes")


def cache_key_latlon(purpose: str, lat: float, lon: float) -> str:
    return f"{purpose}:{float(lat):.2f}:{float(lon):.2f}"


def cache_key_roster(purpose: str, place_ids: Sequence[str]) -> str:
    """One key for the whole roster so chat does not swarm per POI."""
    digest = hashlib.sha256(
        ",".join(sorted(str(item) for item in place_ids)).encode("utf-8")
    ).hexdigest()[:16]
    return f"{purpose}:roster:{digest}"


def pin_notify_body(severity: str, place: str, summary: str) -> str:
    """PIN dry-run copy. Never calls Grok."""
    return TEMPLATES["notify"].format(
        severity=(severity or "INFO").upper(),
        place=place or "watched area",
        summary=summary or "sandbox notify",
    )


def is_quota_error(exc: BaseException) -> bool:
    for attr in ("status", "status_code", "code"):
        if getattr(exc, attr, None) == 429:
            return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "quota" in text


class GrokLimiter:
    """Process-local RPM + concurrency cap, TTL cache, 429 → template."""

    def __init__(
        self,
        *,
        max_rpm: int | None = None,
        max_concurrent: int | None = None,
        cache_ttl_s: float | None = None,
        mock: bool = False,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_rpm = DEFAULT_GROK_MAX_RPM if max_rpm is None else max(0, int(max_rpm))
        self.max_concurrent = (
            DEFAULT_MAX_CONCURRENT if max_concurrent is None else max(1, int(max_concurrent))
        )
        self.cache_ttl_s = (
            DEFAULT_CACHE_TTL_S if cache_ttl_s is None else max(0.0, float(cache_ttl_s))
        )
        self.mock = mock
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._sema = threading.BoundedSemaphore(self.max_concurrent)
        self._stamps: list[float] = []
        self._cache: dict[str, tuple[float, str]] = {}
        self.calls = 0
        self.cache_hits = 0
        self.degraded = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "GrokLimiter":
        return cls(
            max_rpm=grok_max_rpm(env),
            max_concurrent=grok_max_concurrent(env),
            cache_ttl_s=grok_cache_ttl_s(env),
            mock=fast_start(env),
        )

    def call(
        self,
        purpose: str,
        cache_key: str,
        fn: Callable[[], str],
    ) -> GrokResult:
        kind = purpose if purpose in TEMPLATES else "chat"
        template = TEMPLATES[kind]

        if kind == "notify":
            return self._template(
                kind,
                pin_notify_body("INFO", "watched area", "sandbox notify"),
                "notify",
            )

        cached = self._cache_get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            return GrokResult(cached, "cache", kind, False)

        if self.mock or self.max_rpm <= 0:
            return self._template(kind, template, "fast_start" if self.mock else "rpm")

        if not self._sema.acquire(blocking=False):
            return self._template(kind, template, "concurrent")

        try:
            if not self._allow_rpm():
                return self._template(kind, template, "rpm")
            try:
                text = fn()
            except Exception as exc:
                if is_quota_error(exc):
                    return self._template(kind, template, "429")
                raise
        finally:
            self._sema.release()

        text = (text or "").strip() or template
        self._cache_put(cache_key, text)
        self.calls += 1
        return GrokResult(text, "grok", kind, False)

    def _template(self, purpose: str, text: str, reason: str) -> GrokResult:
        self.degraded += 1
        return GrokResult(text, "template", purpose, True, reason)

    def _allow_rpm(self) -> bool:
        now = self._clock()
        with self._lock:
            self._stamps = [stamp for stamp in self._stamps if now - stamp < 60.0]
            if len(self._stamps) >= self.max_rpm:
                return False
            self._stamps.append(now)
            return True

    def _cache_get(self, key: str) -> str | None:
        now = self._clock()
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                return None
            expires, text = hit
            if expires < now:
                self._cache.pop(key, None)
                return None
            return text

    def _cache_put(self, key: str, text: str) -> None:
        with self._lock:
            self._cache[key] = (self._clock() + self.cache_ttl_s, text)


_default: GrokLimiter | None = None
_default_lock = threading.Lock()


def get_limiter() -> GrokLimiter:
    """One process-wide limiter so chat does not grow a second counter."""
    global _default
    with _default_lock:
        if _default is None:
            _default = GrokLimiter.from_env()
        return _default


def reset_limiter() -> None:
    global _default
    with _default_lock:
        _default = None
