"""Bbox filter for the Houston/coastal camera seed. No Grok."""

import importlib.util
import os
import sys
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_spec = importlib.util.spec_from_file_location(
    "cameras",
    os.path.join(BACKEND_DIR, "app", "cameras.py"),
)
cameras = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cameras)

HOUSTON = (-95.9, 29.2, -94.7, 30.1)
PINELLAS = (-82.85, 27.60, -82.55, 28.00)
EMPTY = (0.0, 0.0, 1.0, 1.0)


class CameraBboxTests(unittest.TestCase):
    def test_seed_has_houston_and_coastal(self):
        catalog = cameras.load_catalog()
        self.assertGreaterEqual(len(catalog), 20)
        sources = {camera["source"] for camera in catalog}
        self.assertIn("transtar", sources)
        self.assertIn("fl511", sources)
        self.assertTrue(any(camera["coastal"] for camera in catalog))

    def test_houston_bbox_returns_geolocated_transtar(self):
        found = cameras.cameras_in_bbox(HOUSTON)
        self.assertGreaterEqual(len(found), 8)
        self.assertTrue(all(camera["source"] == "transtar" for camera in found))
        self.assertTrue(all("lat" in camera and "lon" in camera for camera in found))
        ids = {camera["id"] for camera in found}
        self.assertIn("transtar-180", ids)
        self.assertIn("transtar-181", ids)
        self.assertIn("transtar-8024", ids)
        self.assertNotIn("fl511-1004", ids)

    def test_pinellas_bbox_returns_fl511(self):
        found = cameras.cameras_in_bbox(PINELLAS)
        self.assertGreaterEqual(len(found), 8)
        self.assertTrue(all(camera["source"] == "fl511" for camera in found))
        self.assertIn("fl511-1004", {camera["id"] for camera in found})

    def test_empty_bbox(self):
        self.assertEqual(cameras.cameras_in_bbox(EMPTY), [])

    def test_parse_bbox(self):
        self.assertEqual(cameras.parse_bbox("-95.9,29.2,-94.7,30.1"), HOUSTON)
        self.assertIsNone(cameras.parse_bbox(None))
        self.assertIsNone(cameras.parse_bbox("1,2,3"))
        self.assertIsNone(cameras.parse_bbox("a,b,c,d"))
        self.assertIsNone(cameras.parse_bbox("1,2,0,3"))

    def test_lookup(self):
        ferry = cameras.camera_by_id("transtar-180")
        self.assertIsNotNone(ferry)
        self.assertEqual(ferry["name"], "Galveston Ferry @ Galveston Ferry Landing")
        self.assertTrue(str(ferry["still_url"]).endswith("/180.jpg"))
        self.assertIsNone(cameras.camera_by_id("missing"))


if __name__ == "__main__":
    unittest.main()
