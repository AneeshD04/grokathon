"""GovWatch tests use recorded fixtures only. No network. No Grok. No Twilio."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from govwatch.clients import MemoryCache
from govwatch.normalize import normalize_nws_collection, normalize_usgs_collection
from govwatch.poll import DEFAULT_BBOX, FIXTURE_DIR, Poller, fixture_fetchers, main


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class NormalizeTests(unittest.TestCase):
    def test_nws_texas_flash_flood_becomes_pin(self) -> None:
        alerts = normalize_nws_collection(
            _load("nws-texas-flash-flood.json"),
            geofence_id="galveston-county",
            bbox=DEFAULT_BBOX,
        )
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["source"], "nws")
        self.assertEqual(alert["severity"], "critical")
        self.assertEqual(alert["title"], "Flash Flood Warning")
        self.assertTrue(29.18 <= alert["lat"] <= 29.48)
        self.assertTrue(-95.12 <= alert["lon"] <= -94.62)
        self.assertTrue(alert["dedupe_key"].startswith("nws:"))

    def test_usgs_only_above_flood_stage(self) -> None:
        alerts = normalize_usgs_collection(
            _load("usgs-galveston-gauge.json"),
            geofence_id="galveston-county",
            bbox=DEFAULT_BBOX,
            flood_stage_ft=4.0,
        )
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["source"], "usgs")
        self.assertEqual(alert["severity"], "critical")
        self.assertAlmostEqual(alert["lat"], 29.4608)
        self.assertIn("08077650", alert["dedupe_key"])


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, alert: dict) -> dict:
        self.calls.append(alert)
        return {"alert": alert, "deduped": False}


class PollerTests(unittest.TestCase):
    def test_fixture_replay_posts_nws_and_usgs(self) -> None:
        nws, usgs = fixture_fetchers()
        publisher = FakePublisher()
        posted = Poller(publisher=publisher, fetch_nws=nws, fetch_usgs=usgs).once()
        sources = {row["source"] for row in posted}
        self.assertEqual(sources, {"nws", "usgs"})
        self.assertEqual(len(publisher.calls), 2)

    def test_second_pass_is_deduped(self) -> None:
        nws, usgs = fixture_fetchers()
        publisher = FakePublisher()
        poller = Poller(publisher=publisher, fetch_nws=nws, fetch_usgs=usgs, now=lambda: 100.0)
        self.assertEqual(len(poller.once()), 2)
        self.assertEqual(len(poller.once()), 0)
        self.assertEqual(len(publisher.calls), 2)

    def test_cache_skips_second_fetch(self) -> None:
        hits = {"nws": 0, "usgs": 0}

        def nws() -> dict:
            hits["nws"] += 1
            return _load("nws-texas-flash-flood.json")

        def usgs() -> dict:
            hits["usgs"] += 1
            return _load("usgs-galveston-gauge.json")

        cache = MemoryCache(ttl_s=600, now=lambda: 1.0)
        poller = Poller(
            publisher=FakePublisher(),
            fetch_nws=nws,
            fetch_usgs=usgs,
            cache=cache,
            now=lambda: 1.0,
        )
        poller.once()
        poller.once()
        self.assertEqual(hits, {"nws": 1, "usgs": 1})


class CliTests(unittest.TestCase):
    def test_once_file_sink(self) -> None:
        out = Path(__file__).resolve().parent / "_tmp-govwatch.jsonl"
        if out.exists():
            out.unlink()
        try:
            code = main(["--once", "--sink", "file", "--out", str(out)])
            self.assertEqual(code, 0)
            lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(lines), 2)
            sources = {row["alert"]["source"] for row in lines}
            self.assertEqual(sources, {"nws", "usgs"})
        finally:
            if out.exists():
                out.unlink()


if __name__ == "__main__":
    unittest.main()
