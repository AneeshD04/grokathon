"""Verdicts for compare_rumor.

From the repo root: python3 -m unittest bots.rumor.test_check
From bots/: python3 -m unittest rumor.test_check
"""

from __future__ import annotations

import unittest

from .check import CAMERA_LABELS, POST_KINDS, compare_rumor

_FLOOD = (
    "wet",
    "standing water",
    "impassable",
    "people in water",
    "overtopped road",
)
_BLOCKED = ("impassable", "people in water", "overtopped road")
_CLEAR = ("dry", "all-clear")


class CompareRumorTests(unittest.TestCase):
    def test_rumor_clear_is_contradicted(self) -> None:
        for label in _CLEAR:
            got = compare_rumor("rumor", label)
            self.assertEqual(got["verdict"], "contradicted")
            self.assertEqual(got["line"], "the camera still shows the road open.")

    def test_rumor_blocked_is_supported(self) -> None:
        for label in _BLOCKED:
            got = compare_rumor("rumor", label)
            self.assertEqual(got["verdict"], "supported")
            self.assertEqual(got["line"], "the camera shows the road is not passable.")

    def test_rumor_partial_water_is_inconclusive(self) -> None:
        for label in ("wet", "standing water"):
            got = compare_rumor("rumor", label)
            self.assertEqual(got["verdict"], "inconclusive")
            self.assertEqual(
                got["line"],
                "the camera shows water but does not show the road closed.",
            )

    def test_confirmed_water_and_closure_are_supported(self) -> None:
        for label in ("impassable", "overtopped road", "people in water"):
            got = compare_rumor("confirmed", label)
            self.assertEqual(got["verdict"], "supported")
            self.assertEqual(got["line"], "the camera shows the road is not passable.")
        standing = compare_rumor("confirmed", "standing water")
        self.assertEqual(standing["verdict"], "supported")
        self.assertEqual(standing["line"], "the camera shows standing water on the road.")

    def test_confirmed_clear_is_contradicted(self) -> None:
        for label in _CLEAR:
            got = compare_rumor("confirmed", label)
            self.assertEqual(got["verdict"], "contradicted")
            self.assertEqual(got["line"], "the camera still shows the road open.")

    def test_confirmed_wet_is_inconclusive(self) -> None:
        got = compare_rumor("confirmed", "wet")
        self.assertEqual(got["verdict"], "inconclusive")
        self.assertEqual(got["line"], "the camera shows a wet road but not standing water.")

    def test_irrelevant_is_ignore_for_every_label(self) -> None:
        for label in CAMERA_LABELS:
            got = compare_rumor("irrelevant", label)
            self.assertEqual(got, {"verdict": "ignore", "line": "the post is not about the road."})

    def test_evacuation_flood_is_supported_and_dry_is_contradicted(self) -> None:
        for label in _FLOOD:
            got = compare_rumor("evacuation", label)
            self.assertEqual(got["verdict"], "supported")
            self.assertEqual(got["line"], "the camera shows flooding on the road.")
        dry = compare_rumor("evacuation", "dry")
        self.assertEqual(dry["verdict"], "contradicted")
        self.assertEqual(dry["line"], "the camera shows a dry road.")
        clear = compare_rumor("evacuation", "all-clear")
        self.assertEqual(clear["verdict"], "contradicted")
        self.assertEqual(clear["line"], "the camera still shows the road open.")

    def test_lines_are_one_sentence_without_markdown(self) -> None:
        for kind in POST_KINDS:
            for label in CAMERA_LABELS:
                line = compare_rumor(kind, label)["line"]
                self.assertEqual(line, line.strip())
                self.assertFalse("\n" in line)
                self.assertEqual(line.count("."), 1)
                self.assertTrue(line.endswith("."))
                for mark in ("*", "_", "`", "#", "[", "]"):
                    self.assertNotIn(mark, line)

    def test_unknown_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            compare_rumor("gossip", "dry")
        with self.assertRaises(ValueError):
            compare_rumor("rumor", "flooded")

    def test_return_has_only_verdict_and_line(self) -> None:
        got = compare_rumor("rumor", "dry")
        self.assertEqual(set(got), {"verdict", "line"})


if __name__ == "__main__":
    unittest.main()
