"""Grok limiter: cache, RPM, concurrency, 429 templates. No live xAI."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_spec = importlib.util.spec_from_file_location(
    "grok_limiter",
    os.path.join(BACKEND_DIR, "app", "grok_limiter.py"),
)
gl = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["grok_limiter"] = gl
_spec.loader.exec_module(gl)


class _Quota(Exception):
    def __init__(self, message: str, status: int = 429) -> None:
        super().__init__(message)
        self.status = status


class GrokLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        gl.reset_limiter()
        self.clock = {"t": 10.0}

    def tearDown(self) -> None:
        gl.reset_limiter()

    def _limiter(self, **kwargs) -> gl.GrokLimiter:
        kwargs.setdefault("clock", lambda: self.clock["t"])
        kwargs.setdefault("max_rpm", 2)
        kwargs.setdefault("max_concurrent", 1)
        kwargs.setdefault("cache_ttl_s", 600.0)
        kwargs.setdefault("mock", False)
        return gl.GrokLimiter(**kwargs)

    def test_cache_hit_does_not_call_again(self) -> None:
        n = {"n": 0}

        def fn() -> str:
            n["n"] += 1
            return "drafted once"

        limiter = self._limiter()
        key = gl.cache_key_roster("draft_alert", ["pier", "marina"])
        first = limiter.call("draft_alert", key, fn)
        second = limiter.call("draft_alert", key, fn)
        self.assertEqual(first.source, "grok")
        self.assertEqual(second.source, "cache")
        self.assertEqual(second.text, "drafted once")
        self.assertEqual(n["n"], 1)
        self.assertEqual(limiter.calls, 1)
        self.assertEqual(limiter.cache_hits, 1)

    def test_latlon_cache_rounds_like_flood_risk(self) -> None:
        self.assertEqual(
            gl.cache_key_latlon("flood_risk", 29.301, -94.797),
            "flood_risk:29.30:-94.80",
        )

    def test_rpm_cap_returns_template_without_calling(self) -> None:
        n = {"n": 0}

        def fn() -> str:
            n["n"] += 1
            return f"live-{n['n']}"

        limiter = self._limiter(max_rpm=1)
        first = limiter.call("chat", "a", fn)
        second = limiter.call("chat", "b", fn)
        self.assertEqual(first.text, "live-1")
        self.assertEqual(second.source, "template")
        self.assertEqual(second.reason, "rpm")
        self.assertTrue(second.degraded)
        self.assertEqual(n["n"], 1)
        self.clock["t"] = 71.0
        third = limiter.call("chat", "c", fn)
        self.assertEqual(third.source, "grok")
        self.assertEqual(n["n"], 2)

    def test_concurrent_cap_second_call_templates(self) -> None:
        started = threading.Event()
        release = threading.Event()
        n = {"n": 0}
        limiter = self._limiter(max_rpm=8, max_concurrent=1)

        def slow() -> str:
            n["n"] += 1
            started.set()
            self.assertTrue(release.wait(2.0))
            return "live-slow"

        holder: list[gl.GrokResult] = []
        thread = threading.Thread(
            target=lambda: holder.append(limiter.call("chat", "slow", slow))
        )
        thread.start()
        self.assertTrue(started.wait(2.0))
        blocked = limiter.call("chat", "other", lambda: "should-not-run")
        self.assertEqual(blocked.source, "template")
        self.assertEqual(blocked.reason, "concurrent")
        release.set()
        thread.join(2.0)
        self.assertEqual(holder[0].source, "grok")
        self.assertEqual(n["n"], 1)

    def test_429_degrades_to_template_without_secret(self) -> None:
        secret = "sk-secret-should-never-leak"

        def fn() -> str:
            raise _Quota(f"xAI HTTP 429 quota; key={secret}")

        limiter = self._limiter()
        result = limiter.call("chat", "k", fn)
        self.assertEqual(result.source, "template")
        self.assertEqual(result.reason, "429")
        self.assertNotIn(secret, result.text)
        self.assertNotIn("sk-secret", result.text)
        self.assertIn("template fallback", result.text)

    def test_fast_start_never_calls(self) -> None:
        n = {"n": 0}
        limiter = self._limiter(mock=True)
        result = limiter.call("flood_risk", gl.cache_key_latlon("flood_risk", 29.3, -94.8), lambda: n.__setitem__("n", 1) or "live")
        self.assertEqual(result.source, "template")
        self.assertEqual(result.reason, "fast_start")
        self.assertEqual(n["n"], 0)

    def test_from_env_fast_start_and_rpm_zero(self) -> None:
        limiter = gl.GrokLimiter.from_env({"FAST_START": "1", "GROK_MAX_RPM": "4"})
        self.assertTrue(limiter.mock)
        off = gl.GrokLimiter.from_env({"GROK_MAX_RPM": "0"})
        n = {"n": 0}
        result = off.call("nws", "nws:1", lambda: n.__setitem__("n", 1) or "live")
        self.assertEqual(result.reason, "rpm")
        self.assertEqual(n["n"], 0)

    def test_pin_notify_never_invokes_callable(self) -> None:
        n = {"n": 0}

        def fn() -> str:
            n["n"] += 1
            return "grok should not draft notify"

        limiter = self._limiter()
        result = limiter.call("notify", "notify:pin", fn)
        body = gl.pin_notify_body("warning", "Galveston County", "flood watch")
        self.assertEqual(result.source, "template")
        self.assertEqual(result.reason, "notify")
        self.assertEqual(n["n"], 0)
        self.assertEqual(body, "WARNING for Galveston County: flood watch")
        self.assertNotIn("grok", body.lower())

    def test_get_limiter_is_a_singleton(self) -> None:
        previous = os.environ.get("GROK_MAX_RPM")
        os.environ["GROK_MAX_RPM"] = "2"
        try:
            first = gl.get_limiter()
            second = gl.get_limiter()
            self.assertIs(first, second)
        finally:
            if previous is None:
                os.environ.pop("GROK_MAX_RPM", None)
            else:
                os.environ["GROK_MAX_RPM"] = previous

    def test_quota_helper_reads_urllib_style_code(self) -> None:
        class HttpErr(Exception):
            def __init__(self) -> None:
                super().__init__("HTTP Error 429: Too Many Requests")
                self.code = 429

        self.assertTrue(gl.is_quota_error(HttpErr()))
        self.assertTrue(gl.is_quota_error(RuntimeError("rate limit exceeded")))
        self.assertFalse(gl.is_quota_error(RuntimeError("timeout")))


if __name__ == "__main__":
    unittest.main()
