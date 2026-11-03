"""Proof for issue #52: a 404 still falls back to a local one-frame MP4.

Run from bots/: ``python -m unittest tests.test_mp4_fallback -v``

The still and the alert bus are 127.0.0.1 only. No Grok call.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camwatch.config import load_config
from camwatch.alerts import HttpAlertsClient
from camwatch.model import Camera
from camwatch.sources import FrameFetchError, frames_for_camera, jpeg_from_mp4
from camwatch.vision import build_classifier
from camwatch.worker import WatchState, run_once

ROOT = Path(__file__).resolve().parents[1]
FLOODED = ROOT / "camwatch" / "fixtures" / "flooded-road.jpg"
CLEAR = ROOT / "camwatch" / "fixtures" / "clear-road.jpg"


def _one_frame_mp4(jpeg: bytes) -> bytes:
    ftyp_body = b"isom" + b"\x00\x00\x00\x00" + b"isommp41"
    ftyp = (8 + len(ftyp_body)).to_bytes(4, "big") + b"ftyp" + ftyp_body
    mdat = (8 + len(jpeg)).to_bytes(4, "big") + b"mdat" + jpeg
    return ftyp + mdat


class _AlertBus(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_error(404)

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


class Mp4FallbackTests(unittest.TestCase):
    def test_jpeg_roundtrip_and_rejects_a_bare_jpeg(self) -> None:
        jpeg = FLOODED.read_bytes()
        self.assertEqual(jpeg_from_mp4(_one_frame_mp4(jpeg)), jpeg)
        with self.assertRaises(FrameFetchError):
            jpeg_from_mp4(jpeg)

    def test_config_mp4_is_relative_to_the_camera_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = base / "cameras.json"
            cfg.write_text(
                json.dumps(
                    {
                        "cameras": [
                            {
                                "id": "buffalo-1",
                                "name": "Buffalo Speedway",
                                "lat": 29.76,
                                "lon": -95.37,
                                "still_url": "http://127.0.0.1/missing.jpg",
                                "mp4": "fixtures/flooded-road.mp4",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            camera = load_config(cfg).cameras[0]
            self.assertEqual(camera.mp4_path, (base / "fixtures" / "flooded-road.mp4").resolve())

    def test_other_http_errors_do_not_use_the_mp4(self) -> None:
        camera = _camera(Path("flooded-road.mp4"))

        def fetch(_url: str) -> bytes:
            raise FrameFetchError("JPEG GET failed: HTTP 500", status=500)

        with self.assertRaises(FrameFetchError) as caught:
            frames_for_camera(camera, fetcher=fetch)
        self.assertEqual(caught.exception.status, 500)

    def test_live_jpeg_wins_over_the_mp4(self) -> None:
        camera = _camera(Path("flooded-road.mp4"), still_name="clear-road.jpg")

        def fetch(_url: str) -> bytes:
            return CLEAR.read_bytes()

        frame = frames_for_camera(camera, fetcher=fetch)[0]
        self.assertEqual(frame.filename, "clear-road.jpg")
        self.assertNotEqual(frame.jpeg, FLOODED.read_bytes())

    def test_404_mp4_posts_one_alert_without_a_key(self) -> None:
        server, thread = _start_server()
        self.addCleanup(_stop_server, server, thread)
        port = server.server_address[1]
        with tempfile.TemporaryDirectory() as tmp:
            mp4_path = Path(tmp) / "flooded-road.mp4"
            mp4_path.write_bytes(_one_frame_mp4(FLOODED.read_bytes()))
            camera = _camera(mp4_path, still_url=f"http://127.0.0.1:{port}/missing.jpg")
            client = HttpAlertsClient(f"http://127.0.0.1:{port}")
            state = WatchState()
            first = run_once(
                [camera],
                classifier=build_classifier({}),
                publisher=client,
                state=state,
            )
            second = run_once(
                [camera],
                classifier=build_classifier({}),
                publisher=client,
                state=state,
            )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(server.posts), 1)
        path, content_type, alert = server.posts[0]
        self.assertEqual(path, "/api/alerts")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(alert["source"], "camera")
        self.assertEqual(alert["severity"], "critical")
        self.assertEqual(alert["title"], "Water over roadway")
        self.assertEqual(alert["dedupe_key"], "cam:buffalo-1:water_over_road")
        self.assertEqual(alert["evidence"]["raw"]["vision_class"], "overtopped_road")
        self.assertEqual(alert["evidence"]["raw"]["vision_backend"], "fallback")
        self.assertEqual(alert["evidence"]["raw"]["filename"], "flooded-road.mp4")
        self.assertFalse(alert["evidence"]["raw"]["uncertain"])


def _camera(mp4_path: Path, *, still_name: str = "missing.jpg", still_url: str | None = None) -> Camera:
    return Camera(
        id="buffalo-1",
        name="Buffalo Speedway",
        lat=29.76,
        lon=-95.37,
        geofence_id="houston-demo",
        still_url=still_url or f"http://127.0.0.1/{still_name}",
        mp4_path=mp4_path,
    )


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
