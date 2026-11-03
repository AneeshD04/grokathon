"""Proof for issue #17: a flooded-road JPEG in a test folder creates an alert.

Run from bots/: ``python -m unittest tests.test_flooded_road -v``
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camwatch.__main__ import main
from camwatch.alerts import AlertsPublishError, HttpAlertsClient
from camwatch.config import load_config
from camwatch.catalog import load_city
from camwatch.flood import build_flood_alerts, publish_new_flood_alerts
from camwatch.model import MAX_CAMERAS, Camera, check_interval
from camwatch.sources import FrameFetchError, fetch_jpeg, frame_from_bytes
from camwatch.vision import FallbackVision, LiveGrokVision, VisionError, build_classifier, result_from_grok_label
from camwatch.worker import WatchState, run_once, select_cameras

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "camwatch" / "fixtures"
FLOODED = FIXTURES / "flooded-road.jpg"
CLEAR = FIXTURES / "clear-road.jpg"
EXAMPLE = ROOT / "camwatch" / "cameras.example.json"


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

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/flooded-road.jpg":
            self.send_error(404)
            return
        data = FLOODED.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return


class FloodedRoadTests(unittest.TestCase):
    def test_fixtures_are_jpegs(self) -> None:
        for path in (FLOODED, CLEAR):
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"\xff\xd8"), path.name)
            self.assertGreater(len(data), 100)

    def test_dropping_flooded_road_posts_alert_on_class_change_only(self) -> None:
        server, thread = _start_server()
        self.addCleanup(_stop_server, server, thread)
        port = server.server_address[1]
        client = HttpAlertsClient(f"http://127.0.0.1:{port}")
        camera = _inbox_camera(self._inbox_with("flooded-road.jpg"))
        state = WatchState()

        first = run_once([camera], classifier=FallbackVision(), publisher=client, state=state)
        second = run_once([camera], classifier=FallbackVision(), publisher=client, state=state)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(server.posts), 1)
        path, content_type, alert = server.posts[0]
        self.assertEqual(path, "/api/alerts")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(alert["source"], "camera")
        self.assertEqual(alert["severity"], "critical")
        self.assertEqual(alert["title"], "Water over roadway")
        self.assertEqual(alert["geofence_id"], "houston-demo")
        self.assertAlmostEqual(alert["lat"], 29.76, places=2)
        self.assertAlmostEqual(alert["lon"], -95.37, places=2)
        self.assertEqual(alert["dedupe_key"], "cam:buffalo-1:water_over_road")
        self.assertTrue(alert["ts"].endswith("Z"))
        self.assertIsNone(alert["evidence"]["thumb_url"])
        self.assertEqual(alert["evidence"]["raw"]["vision_class"], "overtopped_road")
        self.assertEqual(alert["evidence"]["raw"]["vision_backend"], "fallback")
        self.assertFalse(alert["evidence"]["raw"]["uncertain"])
        self.assertEqual(alert["evidence"]["raw"]["filename"], "flooded-road.jpg")
        self.assertIn("roadway", alert["summary"].lower())

        clear_path = camera.inbox_dir / "clear-road.jpg"
        shutil.copy(CLEAR, clear_path)
        third = run_once([camera], classifier=FallbackVision(), publisher=client, state=state)
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0]["severity"], "info")
        self.assertEqual(third[0]["dedupe_key"], "cam:buffalo-1:all_clear")
        self.assertEqual(len(server.posts), 2)

    def test_cli_file_sink_without_alert_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            shutil.copy(FLOODED, inbox / "flooded-road.jpg")
            # A non-JPEG with a .jpg name must not become an alert.
            (inbox / "notes.jpg").write_bytes(b"this is not a jpeg")
            out = Path(tmp) / "alerts.jsonl"
            code = main(
                [
                    "--once",
                    "--sink",
                    "file",
                    "--out",
                    str(out),
                    "--inbox",
                    str(inbox),
                    "--cameras",
                    str(EXAMPLE),
                    "--ignore-watches",
                    "--fixture",
                ]
            )
            self.assertEqual(code, 0)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertFalse(record["deduped"])
            self.assertEqual(record["alert"]["dedupe_key"], "cam:buffalo-1:water_over_road")
            self.assertEqual(record["alert"]["severity"], "critical")
            self.assertTrue(record["alert"]["id"])

    def test_http_still_url_uses_filename_and_posts(self) -> None:
        server, thread = _start_server()
        self.addCleanup(_stop_server, server, thread)
        port = server.server_address[1]
        camera = Camera(
            id="galveston-landing",
            name="Galveston Landing (ferry)",
            lat=29.31,
            lon=-94.80,
            geofence_id="houston-demo",
            still_url=f"http://127.0.0.1:{port}/flooded-road.jpg",
        )
        client = HttpAlertsClient(f"http://127.0.0.1:{port}")
        alerts = run_once(
            [camera],
            classifier=build_classifier({}),
            publisher=client,
            state=WatchState(),
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["evidence"]["thumb_url"], camera.still_url)
        self.assertEqual(alerts[0]["evidence"]["raw"]["vision_backend"], "fallback")
        self.assertEqual(alerts[0]["dedupe_key"], "cam:galveston-landing:water_over_road")

    def test_unknown_filename_does_not_alert_without_a_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp)
            shutil.copy(FLOODED, inbox / "IMG_0042.jpg")
            camera = _inbox_camera(inbox)
            alerts = run_once(
                [camera],
                classifier=FallbackVision(),
                publisher=_Memory(),
                state=WatchState(),
            )
            self.assertEqual(alerts, [])

    def test_sidecar_class_overrides_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp)
            image = inbox / "IMG_0042.jpg"
            shutil.copy(FLOODED, image)
            (inbox / "IMG_0042.jpg.json").write_text(
                json.dumps({"class": "debris", "summary": "Vision: debris on the shoulder."}),
                encoding="utf-8",
            )
            alerts = run_once(
                [_inbox_camera(inbox)],
                classifier=FallbackVision(),
                publisher=_Memory(),
                state=WatchState(),
            )
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["severity"], "watch")
            self.assertEqual(alerts[0]["dedupe_key"], "cam:buffalo-1:debris")

    def test_cap_is_eight_and_watches_filter_sources(self) -> None:
        cameras = [
            Camera(
                id=f"cam-{index}",
                name=f"Cam {index}",
                lat=29.7,
                lon=-95.3,
                geofence_id="houston-demo",
                still_url=f"http://127.0.0.1/cam-{index}.jpg",
            )
            for index in range(9)
        ]
        picked = select_cameras(cameras, None, max_cameras=99)
        self.assertEqual(len(picked), MAX_CAMERAS)
        self.assertEqual(picked[-1].id, "cam-7")
        only_b = select_cameras(
            cameras[:2],
            [{"sources": ["camera"], "camera_ids": ["cam-1"]}],
        )
        self.assertEqual([camera.id for camera in only_b], ["cam-1"])
        self.assertEqual(
            select_cameras(cameras[:2], [{"sources": ["x"], "camera_ids": ["cam-0"]}]),
            [],
        )
        self.assertEqual(len(select_cameras(cameras[:2], [])), 2)

    def test_interval_stays_inside_15_to_30(self) -> None:
        self.assertEqual(check_interval(15), 15)
        self.assertEqual(check_interval(20), 20)
        self.assertEqual(check_interval(30), 30)
        with self.assertRaises(ValueError):
            check_interval(14)
        with self.assertRaises(ValueError):
            check_interval(31)
        loaded = load_config(EXAMPLE)
        self.assertEqual(loaded.interval_seconds, 20)
        self.assertEqual(loaded.cameras[0].id, "buffalo-1")

    def test_grok_label_map_and_fixture_fallback_without_network(self) -> None:
        frame = frame_from_bytes(FLOODED.read_bytes(), filename="flooded-road.jpg", camera_name="Buffalo Speedway")
        self.assertEqual(result_from_grok_label("dry").vision_class, "all_clear")
        self.assertEqual(result_from_grok_label("wet").vision_class, "standing_water")
        self.assertEqual(result_from_grok_label("standing water").vision_class, "standing_water")
        self.assertEqual(result_from_grok_label("impassable").vision_class, "overtopped_road")
        self.assertEqual(result_from_grok_label("people in water").vision_class, "overtopped_road")
        self.assertIn("people in water", result_from_grok_label("people in water").summary.lower())

        calls = {"n": 0}

        def classify(jpeg, name):
            calls["n"] += 1
            self.assertEqual(name, "Buffalo Speedway")
            self.assertTrue(jpeg.startswith(b"\xff\xd8"))
            return "impassable"

        live = LiveGrokVision(fallback=FallbackVision(), classify_frame=classify, rpm=None)
        result = live.classify(frame)
        self.assertEqual(result.backend, "grok")
        self.assertEqual(result.vision_class, "overtopped_road")
        self.assertEqual(calls["n"], 1)

        def broken(jpeg, name):
            from grok_client import GrokClientError

            raise GrokClientError("vision failed")

        fallen = LiveGrokVision(fallback=FallbackVision(), classify_frame=broken, rpm=None).classify(frame)
        self.assertEqual(fallen.backend, "fallback")
        self.assertEqual(fallen.vision_class, "overtopped_road")
        self.assertIsInstance(build_classifier({}), FallbackVision)
        self.assertIsInstance(build_classifier(fixture=True), FallbackVision)

    def test_one_new_frame_per_pass_round_robin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a"
            second = root / "b"
            first.mkdir()
            second.mkdir()
            shutil.copy(FLOODED, first / "flooded-road.jpg")
            shutil.copy(FLOODED, second / "flooded-road.jpg")
            cameras = [
                _inbox_camera(first),
                Camera(
                    id="galveston-landing",
                    name="Galveston Landing (ferry)",
                    lat=29.31,
                    lon=-94.80,
                    geofence_id="houston-demo",
                    inbox_dir=second,
                ),
            ]
            sink = _Memory()
            state = WatchState()
            run_once(cameras, classifier=FallbackVision(), publisher=sink, state=state)
            run_once(cameras, classifier=FallbackVision(), publisher=sink, state=state)
            self.assertEqual(
                [alert["dedupe_key"] for alert in sink.alerts],
                [
                    "cam:buffalo-1:water_over_road",
                    "cam:galveston-landing:water_over_road",
                ],
            )

    def test_rpm_skips_without_a_second_grok_call(self) -> None:
        frame = frame_from_bytes(FLOODED.read_bytes(), filename="flooded-road.jpg")
        self.assertIsInstance(
            build_classifier({"XAI_API_KEY": "test-key-not-real", "GROK_MAX_RPM": "0"}),
            FallbackVision,
        )
        calls = {"n": 0}

        def classify(jpeg, name):
            calls["n"] += 1
            return "standing water"

        vision = LiveGrokVision(fallback=FallbackVision(), classify_frame=classify, rpm=1)
        self.assertEqual(vision.classify(frame).vision_class, "standing_water")
        with self.assertRaises(VisionError):
            vision.classify(frame)
        self.assertEqual(calls["n"], 1)

    def test_transtar_default_and_fl511_backup_are_on_disk(self) -> None:
        houston = load_city("houston")
        pinellas = load_city("pinellas", limit=64)
        self.assertEqual(len(houston), 8)
        self.assertGreater(len(pinellas), 8)
        self.assertTrue(houston[0].id.startswith("transtar-"))
        self.assertTrue(houston[0].still_url.startswith("https://"))
        self.assertEqual(pinellas[0].geofence_id, "pinellas-demo")
        self.assertTrue(pinellas[0].still_url.startswith("https://"))
        self.assertTrue(pinellas[0].id.startswith("fl511-"))

    def test_saved_flood_warning_posts_once(self) -> None:
        with patch("feeds.flood_warnings._fetch_json", side_effect=urllib.error.URLError("offline")):
            from feeds.flood_warnings import load_warnings

            points = load_warnings()
        alerts = build_flood_alerts(points)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["evidence"]["raw"]["sensor_id"], "145")
        self.assertEqual(alert["evidence"]["raw"]["sensor_name"], "JF13-3")
        self.assertEqual(alert["evidence"]["raw"]["feed"], "transtar-flood-warning")
        self.assertGreater(alert["evidence"]["raw"]["water_level"], alert["evidence"]["raw"]["bank_height"])
        self.assertEqual(alert["severity"], "critical")
        self.assertEqual(alert["dedupe_key"], "transtar-flood:145:stream_elevation_alert")
        sink = _Memory()
        state = WatchState()
        first = publish_new_flood_alerts(sink, state, points)
        second = publish_new_flood_alerts(sink, state, points)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(sink.alerts), 1)

    def test_bus_token_header_and_retry_skips_vision(self) -> None:
        captured: dict[str, str | None] = {}

        class _Response:
            def read(self) -> bytes:
                return b'{"alert":{"id":"01TEST"},"deduped":false}'

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> bool:
                return False

        def opener(request, timeout=0):
            captured["token"] = request.get_header("X-alert-bus-token")
            captured["body"] = request.data.decode("utf-8")
            return _Response()

        client = HttpAlertsClient("http://127.0.0.1:8000", token="not-a-real-token", opener=opener)
        client.publish({"source": "camera", "title": "Water over roadway"})
        self.assertEqual(captured["token"], "not-a-real-token")
        self.assertNotIn("not-a-real-token", captured["body"])

        class _Flaky:
            def __init__(self) -> None:
                self.calls = 0

            def publish(self, alert: dict) -> dict:
                self.calls += 1
                if self.calls == 1:
                    raise AlertsPublishError("down")
                return {"alert": alert, "deduped": False}

        class _Counting(FallbackVision):
            def __init__(self) -> None:
                self.calls = 0

            def classify(self, frame):
                self.calls += 1
                return super().classify(frame)

        inbox = self._inbox_with("flooded-road.jpg")
        flaky = _Flaky()
        classifier = _Counting()
        state = WatchState()
        with self.assertRaises(AlertsPublishError):
            run_once([_inbox_camera(inbox)], classifier=classifier, publisher=flaky, state=state)
        retried = run_once(
            [_inbox_camera(inbox)],
            classifier=classifier,
            publisher=flaky,
            state=state,
        )
        self.assertEqual(classifier.calls, 1)
        self.assertEqual(flaky.calls, 2)
        self.assertEqual(len(retried), 1)
        self.assertEqual(retried[0]["dedupe_key"], "cam:buffalo-1:water_over_road")

    def _inbox_with(self, name: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="camwatch-inbox-"))
        self.addCleanup(shutil.rmtree, directory, True)
        shutil.copy(FLOODED, directory / name)
        return directory


class _Memory:
    def __init__(self) -> None:
        self.alerts: list[dict] = []

    def publish(self, alert: dict) -> dict:
        self.alerts.append(alert)
        return {"alert": alert, "deduped": False}


def _inbox_camera(directory: Path) -> Camera:
    return Camera(
        id="buffalo-1",
        name="Buffalo Speedway",
        lat=29.76,
        lon=-95.37,
        geofence_id="houston-demo",
        inbox_dir=directory,
    )


class StillUrlSafetyTests(unittest.TestCase):
    def test_rejects_metadata_file_and_credential_urls(self) -> None:
        with self.assertRaises(FrameFetchError):
            fetch_jpeg("http://169.254.169.254/latest/meta-data/")
        with self.assertRaises(FrameFetchError):
            fetch_jpeg("http://metadata.google.internal/")
        with self.assertRaises(FrameFetchError):
            fetch_jpeg("file:///etc/passwd")
        with self.assertRaises(FrameFetchError):
            fetch_jpeg("http://user:pass@example.test/cam.jpg")


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


if __name__ == "__main__":
    unittest.main()
