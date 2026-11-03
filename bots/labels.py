"""Map CamWatch vision labels onto alert classes.

Same grouping as ``camwatch.vision.GROK_LABEL_TO_CLASS`` and ``bots/README.md``:
dry → all-clear, wet / standing water → standing water,
impassable / people in water → overtopped road.
"""

from __future__ import annotations

# Display names from bots/README.md. vision.py stores the same classes as
# all_clear / standing_water / overtopped_road.
ALERT_CLASS = {
    "dry": "all-clear",
    "wet": "standing water",
    "standing water": "standing water",
    "impassable": "overtopped road",
    "people in water": "overtopped road",
}


def alert_class(vision_label: str) -> str:
    """Return the alert class for one CamWatch vision label.

    Raises ValueError when the label is not in the CamWatch map.
    """
    key = vision_label.strip().lower()
    try:
        return ALERT_CLASS[key]
    except KeyError:
        raise ValueError(f"unknown vision label: {vision_label!r}") from None
