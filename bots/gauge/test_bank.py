"""Bank-height checks for the saved TranStar flood-warning point.

Run from the grokathon repo root:

    python3 -m unittest bots.gauge.test_bank

Or run this file directly:

    python3 bots/gauge/test_bank.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Repo root is the directory that contains bots/, whether this file is loaded
# as a module or executed as a script.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.gauge.bank import above_bank, spoken_gauge, surplus_feet

WARNINGS_PATH = ROOT / "bots" / "data" / "flood_warnings.json"


def load_warnings(path: Path = WARNINGS_PATH) -> list:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("result", payload.get("points", []))
    if not isinstance(payload, list):
        raise ValueError(f"expected a list of warnings in {path}")
    return payload


def warning_named(name: str, warnings: list | None = None) -> dict:
    points = load_warnings() if warnings is None else warnings
    for point in points:
        if isinstance(point, dict) and point.get("name") == name:
            return point
    raise AssertionError(f"no warning named {name}")


class BankTests(unittest.TestCase):
    def test_above_bank_compares_water_to_bank(self) -> None:
        self.assertTrue(above_bank(3.51, 2.405))
        self.assertFalse(above_bank(2.405, 2.405))
        self.assertFalse(above_bank(2.0, 2.405))

    def test_surplus_feet_is_water_minus_bank(self) -> None:
        self.assertEqual(surplus_feet(3.51, 2.405), 3.51 - 2.405)
        self.assertEqual(surplus_feet(2.0, 2.405), 2.0 - 2.405)
        self.assertEqual(surplus_feet(2, 2), 0.0)

    def test_saved_jf13_3_is_spoken_above_the_bank(self) -> None:
        point = warning_named("JF13-3")
        self.assertEqual(point["water_level"], 3.51)
        self.assertEqual(point["bank_height"], 2.405)
        self.assertTrue(above_bank(point["water_level"], point["bank_height"]))
        surplus = surplus_feet(point["water_level"], point["bank_height"])
        self.assertAlmostEqual(surplus, 1.105, places=6)

        line = spoken_gauge(point)
        self.assertIn("JF13-3", line)
        self.assertIn("stream", line.lower())
        self.assertIn("above the bank", line.lower())
        self.assertIn("1.11", line)

    def test_spoken_gauge_uses_the_name_when_the_stream_is_not_over_bank(self) -> None:
        below = spoken_gauge({"name": "SENSOR-9", "water_level": 1.0, "bank_height": 2.25})
        self.assertIn("SENSOR-9", below)
        self.assertIn("below the bank", below)
        self.assertIn("1.25", below)
        self.assertNotIn("above the bank", below)

        level = spoken_gauge({"name": "LEVEL-1", "water_level": 4, "bank_height": 4})
        self.assertIn("LEVEL-1", level)
        self.assertIn("level with the bank", level)
        self.assertIn("0.00", level)


if __name__ == "__main__":
    unittest.main()
