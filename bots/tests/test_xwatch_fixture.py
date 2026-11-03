"""Proof for issue #18: a fixture Galveston flood tweet becomes an alert.

Run from bots/: ``python -m unittest tests.test_xwatch_fixture -v``
"""

from __future__ import annotations

import ast
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camwatch.alerts import HttpAlertsClient
from xwatch.__main__ import main
from xwatch.feed import FeedError, load_fixture, load_rss, parse_rss
from xwatch.model import build_alert, matches, pin_item
from xwatch.worker import WatchState, run_once

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "xwatch" / "fixtures" / "galveston-flood.json"
RSS = ROOT / "xwatch" / "fixtures" / "galveston-flood.rss"
PACKAGE = ROOT / "xwatch"


class _AlertBus(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.posts.append((self.path, self.headers.get("Content-Type"), json.loads(raw)))
        body = json.dumps({"alert": json.loads(raw), "deduped": False}).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AlertBus)
    server.posts = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


class XWatchFixtureTests(unittest.TestCase):
    def test_fixture_tweet_posts_galveston_flood_alert(self) -> None:
        server, thread = _start_server()
        self.addCleanup(_stop_server, server, thread)
        port = server.server_address[1]
        client = HttpAlertsClient(f"http://127.0.0.1:{port}")
        items = load_fixture(FIXTURE)
        state = WatchState()

        first = run_once(items, publisher=client, state=state)
        second = run_once(items, publisher=client, state=state)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(server.posts), 1)
        path, content_type, alert = server.posts[0]
        self.assertEqual(path, "/api/alerts")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(alert["source"], "x")
        self.assertEqual(alert["severity"], "critical")
        self.assertEqual(alert["title"], "X: Galveston flooding")
        self.assertEqual(alert["geofence_id"], "houston-demo")
        self.assertAlmostEqual(alert["lat"], 29.3013, places=3)
        self.assertAlmostEqual(alert["lon"], -94.7977, places=3)
        self.assertEqual(alert["dedupe_key"], "x:fixture-galveston-flood-1")
        self.assertTrue(alert["ts"].endswith("Z"))
        self.assertIsNone(alert["evidence"]["thumb_url"])
        self.assertTrue(alert["evidence"]["raw"]["fixture"])
        self.assertEqual(alert["evidence"]["raw"]["origin"], "fixture")
        self.assertIn("galveston", alert["summary"].lower())
        self.assertIn("flood", alert["summary"].lower())

    def test_cli_file_sink_without_alert_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "alerts.jsonl"
            code = main(
                [
                    "--once",
                    "--sink",
                    "file",
                    "--out",
                    str(out),
                    "--fixture",
                    str(FIXTURE),
                    "--ignore-watches",
                ]
            )
            self.assertEqual(code, 0)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertFalse(record["deduped"])
            self.assertEqual(record["alert"]["dedupe_key"], "x:fixture-galveston-flood-1")
            self.assertEqual(record["alert"]["source"], "x")
            self.assertEqual(record["alert"]["title"], "X: Galveston flooding")
            self.assertTrue(record["alert"]["id"])

    def test_rss_fixture_posts_news_alert_and_skips_unrelated(self) -> None:
        server, thread = _start_server()
        self.addCleanup(_stop_server, server, thread)
        client = HttpAlertsClient(f"http://127.0.0.1:{server.server_address[1]}")
        items = load_rss(str(RSS))
        alerts = run_once(items, publisher=client, state=WatchState())
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["source"], "news")
        self.assertEqual(alert["dedupe_key"], "news:rss-galveston-flood-1")
        self.assertEqual(alert["title"], "News: Galveston flooding")
        self.assertIn("seawall", alert["summary"].lower())

    def test_watch_without_x_or_news_publishes_nothing(self) -> None:
        class _Sink:
            def __init__(self) -> None:
                self.posted = []

            def publish(self, alert: dict) -> dict:
                self.posted.append(alert)
                return {"alert": alert, "deduped": False}

        sink = _Sink()
        items = load_fixture(FIXTURE)
        alerts = run_once(
            items,
            publisher=sink,
            state=WatchState(),
            watches=[{"sources": ["camera"], "bbox": [-96, 28, -94, 31]}],
        )
        self.assertEqual(alerts, [])
        self.assertEqual(sink.posted, [])

    def test_sports_item_does_not_match(self) -> None:
        items = load_fixture(FIXTURE)
        sports = [item for item in items if item.id == "fixture-sports-skip"][0]
        self.assertFalse(matches(pin_item(sports)))

    def test_x_api_host_is_blocked(self) -> None:
        with self.assertRaises(FeedError):
            load_rss("https://api.twitter.com/2/tweets/search/recent")
        with self.assertRaises(FeedError):
            load_rss("https://api.x.com/2/tweets/search/recent")

    def test_package_does_not_call_x_or_grok(self) -> None:
        forbidden = ("api.twitter.com", "api.x.com", "grok_client", "xai", "openai")
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("grok_client", alias.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("grok_client", node.module)
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in ("api.twitter.com", "api.x.com"):
                    self.assertNotIn(f"https://{token}", text.replace("blocked", ""))
            self.assertNotIn("from grok_client", text)
            self.assertNotIn("import grok_client", text)

    def test_rss_parse_skips_non_hazard_item(self) -> None:
        items = parse_rss(RSS.read_text(encoding="utf-8"))
        ids = {item.id for item in items}
        self.assertIn("rss-galveston-flood-1", ids)
        self.assertIn("rss-skip-fair", ids)
        flood = [item for item in items if item.id == "rss-galveston-flood-1"][0]
        fair = [item for item in items if item.id == "rss-skip-fair"][0]
        self.assertTrue(matches(pin_item(flood)))
        self.assertFalse(matches(pin_item(fair)))

    def test_build_alert_pins_galveston_without_coords(self) -> None:
        from xwatch.model import SocialItem

        item = SocialItem(
            id="no-coords",
            text="Flooding on the Galveston seawall near the Strand.",
            origin="fixture",
        )
        alert = build_alert(item)
        self.assertAlmostEqual(alert["lat"], 29.3013, places=3)
        self.assertAlmostEqual(alert["lon"], -94.7977, places=3)
        self.assertEqual(alert["source"], "x")


if __name__ == "__main__":
    unittest.main()
