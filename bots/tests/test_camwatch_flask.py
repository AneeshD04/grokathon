"""Issue #94: one-pass CamWatch prefers Flask /api/alerts and FAST vision."""

from __future__ import annotations

import unittest
from camwatch.alerts import (
    FLASK_ALERT_CANDIDATES,
    STUB_ALERTS_URL,
    resolve_alerts_base_url,
)
from camwatch.heuristic import class_from_rgb, mean_rgb
from camwatch.model import Camera
from camwatch.sources import frame_from_bytes
from camwatch.vision import FallbackVision, HeuristicVision, LiveGrokVision, build_classifier
from camwatch.worker import WatchState, run_once
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOODED = ROOT / "camwatch" / "fixtures" / "flooded-road.jpg"
CLEAR = ROOT / "camwatch" / "fixtures" / "clear-road.jpg"


class _Memory:
    def __init__(self) -> None:
        self.alerts: list[dict] = []

    def publish(self, alert: dict) -> dict:
        self.alerts.append(alert)
        return {"alert": alert, "deduped": False}


class FlaskBusResolveTests(unittest.TestCase):
    def test_prefers_flask_5001_over_stub(self) -> None:
        def probe(url: str) -> bool:
            return url == "http://127.0.0.1:5001"

        self.assertEqual(
            resolve_alerts_base_url(STUB_ALERTS_URL, probe=probe),
            "http://127.0.0.1:5001",
        )
        self.assertEqual(resolve_alerts_base_url(None, probe=probe), "http://127.0.0.1:5001")

    def test_custom_url_is_kept(self) -> None:
        def probe(url: str) -> bool:
            raise AssertionError(f"must not probe Flask when url is {url}")

        self.assertEqual(
            resolve_alerts_base_url("http://127.0.0.1:9", probe=probe),
            "http://127.0.0.1:9",
        )

    def test_stub_when_flask_is_down(self) -> None:
        self.assertEqual(
            resolve_alerts_base_url(None, probe=lambda url: False),
            STUB_ALERTS_URL,
        )
        self.assertEqual(
            resolve_alerts_base_url(STUB_ALERTS_URL, probe=lambda url: False),
            STUB_ALERTS_URL,
        )

    def test_flask_5000_if_5001_is_down(self) -> None:
        def probe(url: str) -> bool:
            return url == "http://127.0.0.1:5000"

        self.assertEqual(resolve_alerts_base_url(None, probe=probe), "http://127.0.0.1:5000")
        self.assertEqual(FLASK_ALERT_CANDIDATES[0], "http://127.0.0.1:5001")


class FastHeuristicTests(unittest.TestCase):
    def test_flooded_fixture_without_filename_keyword(self) -> None:
        rgb = mean_rgb(FLOODED.read_bytes())
        if rgb is None:
            self.skipTest("Pillow is required for FAST color classify")
        vision_class, _, _ = class_from_rgb(*rgb)
        self.assertEqual(vision_class, "overtopped_road")
        frame = frame_from_bytes(FLOODED.read_bytes(), filename="180.jpg")
        result = HeuristicVision().classify(frame)
        self.assertEqual(result.vision_class, "overtopped_road")
        self.assertEqual(result.backend, "heuristic")
        self.assertFalse(result.uncertain)

    def test_clear_fixture_without_filename_keyword(self) -> None:
        frame = frame_from_bytes(CLEAR.read_bytes(), filename="181.jpg")
        result = HeuristicVision().classify(frame)
        self.assertEqual(result.vision_class, "all_clear")
        self.assertEqual(result.backend, "heuristic")

    def test_build_classifier_fast_does_not_use_grok(self) -> None:
        self.assertIsInstance(build_classifier(vision="fast"), HeuristicVision)
        self.assertIsInstance(build_classifier(fixture=True), FallbackVision)
        self.assertIsInstance(build_classifier({}), FallbackVision)
        self.assertIsInstance(
            build_classifier({"XAI_API_KEY": "test-key-not-real"}, vision="grok"),
            LiveGrokVision,
        )

    def test_fast_pass_posts_flood_and_skips_all_clear(self) -> None:
        flooded = Camera(
            id="180",
            name="Galveston Ferry",
            lat=29.32,
            lon=-94.77,
            geofence_id="houston-demo",
            still_url="https://www.houstontranstar.org/snapshots/cctv/180.jpg",
        )
        dry = Camera(
            id="181",
            name="Clear Road",
            lat=29.31,
            lon=-94.77,
            geofence_id="houston-demo",
            still_url="https://www.houstontranstar.org/snapshots/cctv/181.jpg",
        )
        jpegs = {
            flooded.still_url: FLOODED.read_bytes(),
            dry.still_url: CLEAR.read_bytes(),
        }
        sink = _Memory()
        alerts = run_once(
            [flooded, dry],
            classifier=HeuristicVision(),
            publisher=sink,
            state=WatchState(),
            max_frames=8,
            fetcher=lambda url: jpegs[url],
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["source"], "camera")
        self.assertEqual(alerts[0]["severity"], "critical")
        self.assertEqual(alerts[0]["dedupe_key"], "cam:180:water_over_road")
        self.assertEqual(alerts[0]["evidence"]["raw"]["vision_backend"], "heuristic")


if __name__ == "__main__":
    unittest.main()
