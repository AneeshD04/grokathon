"""Parse Grok vision replies into flood labels. No network.

From the repo root: python3 -m unittest bots.test_grok_client
"""

from __future__ import annotations

import unittest

from bots.grok_client import GrokClientError, _extract_label

_HOUSTON_STATIC = (
    "The frame is unusable camera static, so it cannot be classified."
)


class ExtractLabelTests(unittest.TestCase):
    def test_flood_labels(self) -> None:
        for label in (
            "dry",
            "wet",
            "standing water",
            "impassable",
            "people in water",
        ):
            with self.subTest(label=label):
                self.assertEqual(_extract_label(label), label)
                self.assertEqual(_extract_label(f"  `{label}.` "), label)

    def test_standing_water_inside_a_sentence(self) -> None:
        self.assertEqual(
            _extract_label("There is standing water across the lanes."),
            "standing water",
        )

    def test_houston_transtar_static_frame_is_unusable(self) -> None:
        self.assertEqual(_extract_label(_HOUSTON_STATIC), "unusable")

    def test_unusable_static_or_cannot_be_classified(self) -> None:
        replies = (
            "unusable",
            "UNUSABLE.",
            "`static`",
            "camera static",
            "The camera is static",
            "cannot be classified",
            "This frame cannot be classified.",
            "cannot  be\tclassified",
        )
        for reply in replies:
            with self.subTest(reply=reply):
                self.assertEqual(_extract_label(reply), "unusable")

    def test_refusal_wins_over_a_named_flood_label(self) -> None:
        reply = "The frame cannot be classified; it might be wet."
        self.assertEqual(_extract_label(reply), "unusable")

    def test_unrecognized_label_raises(self) -> None:
        for reply in ("maybe flooded", "hydrostatic pressure"):
            with self.subTest(reply=reply):
                with self.assertRaises(GrokClientError):
                    _extract_label(reply)


if __name__ == "__main__":
    unittest.main()
