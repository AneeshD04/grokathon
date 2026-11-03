"""One-pass spoken card. No network: JPEG fetch, Grok, and flood HTTP are faked.

Run from bots/: ``python -m unittest tests.test_demo_card tests.test_flooded_road -q``
"""

from __future__ import annotations

import io
import contextlib
import unittest
from pathlib import Path
from unittest.mock import patch

from camwatch.__main__ import main
from camwatch.card import format_card, load_demo_cameras, pick_sensor, redact, run_card
from camwatch.model import Camera
from demo_card import demo_line, sensor_line
from grok_client import GrokClientError

ROOT = Path(__file__).resolve().parents[1]
FLOODED = ROOT / "camwatch" / "fixtures" / "flooded-road.jpg"
FERRY = "https://www.houstontranstar.org/snapshots/cctv/180.jpg"
JF13 = {
    "id": "145",
    "name": "JF13-3",
    "lat": 29.81,
    "lon": -94.33,
    "water_level": 3.51,
    "bank_height": 2.405,
    "status": "stream_elevation_alert",
    "source": "sample",
}


class SpokenLineTests(unittest.TestCase):
    def test_hazard_and_clear_lines_name_the_gauge(self) -> None:
        self.assertEqual(
            demo_line("impassable", JF13),
            "Do not drive through because JF13-3 is above its bank.",
        )
        self.assertEqual(
            demo_line("dry", JF13),
            "The camera is still clear, but the sensor JF13-3 is above its bank.",
        )
        self.assertEqual(
            sensor_line(JF13),
            "Sensor JF13-3 is above its bank. Water is 3.51. The bank is 2.405.",
        )
        self.assertEqual(sensor_line(None), "No flood sensor.")

    def test_below_bank_does_not_use_the_hazard_clause(self) -> None:
        low = {"name": "JF13-3", "water_level": 1.0, "bank_height": 2.405}
        self.assertEqual(
            sensor_line(low),
            "Sensor JF13-3 is below its bank. Water is 1. The bank is 2.405.",
        )
        self.assertEqual(demo_line("dry", low), "The camera is still clear.")


class DemoCardTests(unittest.TestCase):
    def test_default_list_is_eight_and_starts_at_the_ferry(self) -> None:
        cameras = load_demo_cameras()
        self.assertEqual(len(cameras), 8)
        self.assertEqual(cameras[0].id, "180")
        self.assertEqual(cameras[0].name, "Galveston Ferry @ Galveston Ferry Landing")
        self.assertEqual(cameras[0].still_url, FERRY)
        self.assertTrue(all(camera.still_url for camera in cameras))

    def test_one_pass_prints_name_label_sensor_and_sentence(self) -> None:
        jpeg = FLOODED.read_bytes()
        calls = {"fetch": [], "vision": 0}

        def fetch(url):
            calls["fetch"].append(url)
            return jpeg

        def classify(data, name):
            calls["vision"] += 1
            self.assertEqual(name, "Galveston Ferry @ Galveston Ferry Landing")
            self.assertTrue(data.startswith(b"\xff\xd8"))
            return "dry"

        text = run_card(fetcher=fetch, classify_frame=classify, load_warnings=lambda: [JF13])
        self.assertEqual(calls["fetch"], [FERRY])
        self.assertEqual(calls["vision"], 1)
        self.assertEqual(
            text,
            "\n".join(
                [
                    "camera: Galveston Ferry @ Galveston Ferry Landing",
                    "label: dry",
                    "sensor: Sensor JF13-3 is above its bank. Water is 3.51. The bank is 2.405.",
                    "The camera is still clear, but the sensor JF13-3 is above its bank.",
                ]
            )
            + "\n",
        )

    def test_impassable_uses_the_do_not_drive_line(self) -> None:
        text = run_card(
            fetcher=lambda url: FLOODED.read_bytes(),
            classify_frame=lambda data, name: "impassable",
            load_warnings=lambda: [JF13],
        )
        self.assertIn("label: impassable\n", text)
        self.assertIn("Do not drive through because JF13-3 is above its bank.\n", text)

    def test_grok_error_falls_back_once_and_does_not_retry(self) -> None:
        calls = {"n": 0}

        def classify(data, name):
            calls["n"] += 1
            raise GrokClientError("xAI vision HTTP 503")

        text = run_card(
            fetcher=lambda url: FLOODED.read_bytes(),
            classify_frame=classify,
            load_warnings=lambda: [JF13],
        )
        self.assertEqual(calls["n"], 1)
        self.assertIn("label: all_clear\n", text)
        self.assertIn("The camera is still clear, but the sensor JF13-3 is above its bank.\n", text)
        self.assertNotIn("503", text)

    def test_fixture_flag_does_not_call_grok(self) -> None:
        calls = {"n": 0}
        camera = Camera(
            id="inject",
            name="Injected flood",
            lat=29.7,
            lon=-95.3,
            geofence_id="houston-demo",
            still_url="https://example.test/flooded-road.jpg",
        )

        def classify(data, name):
            calls["n"] += 1
            return "dry"

        text = run_card(
            cameras=[camera],
            fixture=True,
            fetcher=lambda url: FLOODED.read_bytes(),
            classify_frame=classify,
            load_warnings=lambda: [JF13],
        )
        self.assertEqual(calls["n"], 0)
        self.assertIn("label: overtopped_road\n", text)
        self.assertIn("Do not drive through because JF13-3 is above its bank.\n", text)

    def test_prefers_sensor_145_over_another_gauge(self) -> None:
        other = {"id": "9", "name": "OTHER", "water_level": 9.0, "bank_height": 1.0}
        self.assertEqual(pick_sensor([other, JF13])["id"], "145")
        text = format_card("Cam", "dry", JF13)
        self.assertIn("JF13-3", text)

    def test_cli_card_is_one_shot_even_with_loop(self) -> None:
        jpeg = FLOODED.read_bytes()
        calls = {"vision": 0}

        def classify(data, name):
            calls["vision"] += 1
            return "dry"

        buf = io.StringIO()
        with (
            patch("camwatch.sources.fetch_jpeg", lambda url, timeout=10.0, opener=None: jpeg),
            patch("grok_client.classify_frame", classify),
            patch("feeds.flood_warnings.load_warnings", return_value=[JF13]),
            patch("camwatch.__main__.time.sleep") as sleep,
            patch("camwatch.__main__.HttpAlertsClient") as client,
            contextlib.redirect_stdout(buf),
        ):
            code = main(["--card", "--loop"])
        self.assertEqual(code, 0)
        self.assertEqual(calls["vision"], 1)
        sleep.assert_not_called()
        client.assert_not_called()
        self.assertIn("camera: Galveston Ferry @ Galveston Ferry Landing\n", buf.getvalue())
        self.assertIn("label: dry\n", buf.getvalue())

    def test_camera_id_fetches_only_that_still(self) -> None:
        seen = []

        def fetch(url):
            seen.append(url)
            return FLOODED.read_bytes()

        text = run_card(
            camera_id="8024",
            fetcher=fetch,
            classify_frame=lambda data, name: "wet",
            load_warnings=lambda: [JF13],
        )
        self.assertEqual(seen, ["https://www.houstontranstar.org/snapshots/cctv/8024.jpg"])
        self.assertIn("camera: Buffalo Speedway@N Braeswood\n", text)
        self.assertIn("label: wet\n", text)

    def test_redact_strips_the_api_key(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "super-secret-key"}, clear=False):
            self.assertEqual(redact("super-secret-key failed"), "[redacted] failed")
            self.assertNotIn("super-secret-key", redact("bearer super-secret-key"))


if __name__ == "__main__":
    unittest.main()
