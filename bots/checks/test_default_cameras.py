"""Checked-in Houston camera list for the CamWatch demo.

From the repo root::

    python3 -m unittest bots.checks.test_default_cameras
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_DATA = Path(__file__).resolve().parents[1] / "data" / "camwatch_default.json"
_FIELDS = ("id", "name", "still_url", "lat", "lon", "why")


class DefaultCamerasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(_DATA.is_file(), f"missing {_DATA}")
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
        self.assertIsInstance(raw, dict)
        self.data = raw
        cameras = raw.get("cameras")
        self.assertIsInstance(cameras, list)
        self.cameras = cameras

    def test_file_exists(self) -> None:
        self.assertTrue(_DATA.is_file())

    def test_cap_is_eight(self) -> None:
        self.assertEqual(self.data["cap"], 8)

    def test_eight_cameras(self) -> None:
        self.assertEqual(len(self.cameras), 8)

    def test_each_camera_has_required_fields(self) -> None:
        for index, camera in enumerate(self.cameras):
            self.assertIsInstance(camera, dict, f"camera {index}")
            for field in _FIELDS:
                self.assertIn(field, camera, f"camera {index} missing {field}")
                value = camera[field]
                self.assertIsNotNone(value, f"camera {index} {field}")
                if isinstance(value, str):
                    self.assertTrue(value.strip(), f"camera {index} {field} is blank")
            self.assertIsInstance(camera["lat"], (int, float))
            self.assertNotIsInstance(camera["lat"], bool)
            self.assertIsInstance(camera["lon"], (int, float))
            self.assertNotIsInstance(camera["lon"], bool)

    def test_still_urls_end_with_jpg(self) -> None:
        for index, camera in enumerate(self.cameras):
            still_url = camera["still_url"]
            self.assertIsInstance(still_url, str, f"camera {index} still_url")
            self.assertTrue(
                still_url.endswith(".jpg"),
                f"camera {index} still_url does not end with .jpg: {still_url}",
            )

    def test_first_camera_name_contains_galveston_ferry(self) -> None:
        self.assertGreaterEqual(len(self.cameras), 1)
        name = self.cameras[0]["name"]
        self.assertIsInstance(name, str)
        self.assertIn("Galveston Ferry", name)


if __name__ == "__main__":
    unittest.main()
