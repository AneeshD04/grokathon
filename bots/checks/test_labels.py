"""alert_class maps CamWatch vision labels onto alert classes.

From the repo root: python3 -m unittest bots.checks.test_labels
"""

from __future__ import annotations

import unittest

from bots.labels import alert_class


class AlertClassTests(unittest.TestCase):
    def test_dry_is_all_clear(self) -> None:
        self.assertEqual(alert_class("dry"), "all-clear")

    def test_wet_or_standing_water_is_standing_water(self) -> None:
        self.assertEqual(alert_class("wet"), "standing water")
        self.assertEqual(alert_class("standing water"), "standing water")

    def test_impassable_or_people_in_water_is_overtopped_road(self) -> None:
        self.assertEqual(alert_class("impassable"), "overtopped road")
        self.assertEqual(alert_class("people in water"), "overtopped road")

    def test_unknown_label_raises(self) -> None:
        with self.assertRaises(ValueError):
            alert_class("debris")


if __name__ == "__main__":
    unittest.main()
