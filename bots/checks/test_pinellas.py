"""Pinellas demo camera list: four named coastal cameras, cap 4.

From the repo root::

    python3 -m unittest bots.checks.test_pinellas
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

PINELLAS = Path(__file__).resolve().parents[1] / "data" / "pinellas_demo.json"


def load_pinellas() -> dict:
    """Load the checked-in Pinellas demo camera file."""
    with PINELLAS.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise TypeError(f"{PINELLAS.name} must be a JSON object")
    return payload


class PinellasDemoTests(unittest.TestCase):
    def test_file_loads(self) -> None:
        payload = load_pinellas()
        self.assertIn("cap", payload)
        self.assertIn("cameras", payload)
        self.assertIsInstance(payload["cameras"], list)

    def test_cap_is_4(self) -> None:
        self.assertEqual(load_pinellas()["cap"], 4)

    def test_four_cameras(self) -> None:
        cameras = load_pinellas()["cameras"]
        self.assertEqual(len(cameras), 4)
        for camera in cameras:
            self.assertIsInstance(camera, dict)
            self.assertTrue(camera.get("name"))

    def test_names_include_the_four_bridges(self) -> None:
        names = [str(camera["name"]) for camera in load_pinellas()["cameras"]]
        self.assertTrue(any("Courtney Campbell" in name for name in names))
        self.assertTrue(any("Bayside" in name or "CR-611" in name for name in names))
        self.assertTrue(any("Gandy" in name for name in names))
        self.assertTrue(any("Bayway" in name or "Delgado" in name for name in names))
