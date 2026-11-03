"""Compare a post kind to one camera label.

Pure: no I/O, no clock, no model call. Each line is a single sentence.
"""

from __future__ import annotations

POST_KINDS = ("rumor", "confirmed", "irrelevant", "evacuation")
CAMERA_LABELS = (
    "dry",
    "wet",
    "standing water",
    "impassable",
    "people in water",
    "all-clear",
    "overtopped road",
)

# Road looks open. These contradict a claim that it is closed or flooded.
_CLEAR = frozenset({"dry", "all-clear"})
# Road is not passable. These support a rumor and a confirmed closure.
_BLOCKED = frozenset({"impassable", "people in water", "overtopped road"})
# Any water or closure. Evacuation is supported by every label in this set.
_FLOOD = frozenset(
    {
        "wet",
        "standing water",
        "impassable",
        "people in water",
        "overtopped road",
    }
)

_ROAD_OPEN = "the camera still shows the road open."
_NOT_PASSABLE = "the camera shows the road is not passable."
_STANDING = "the camera shows standing water on the road."
_FLOODING = "the camera shows flooding on the road."
_DRY_ROAD = "the camera shows a dry road."
_IGNORE = "the post is not about the road."
_RUMOR_PARTIAL = "the camera shows water but does not show the road closed."
_CONFIRMED_WET = "the camera shows a wet road but not standing water."


def compare_rumor(post_kind: str, camera_label: str) -> dict[str, str]:
    """Return ``{"verdict", "line"}`` for one post kind and one camera label.

    Verdicts are ``supported``, ``contradicted``, ``ignore``, or
    ``inconclusive``. ``inconclusive`` is only the wet and standing-water
    gaps the rumor and confirmed rules do not settle.
    """
    if post_kind not in POST_KINDS:
        raise ValueError(f"unknown post_kind: {post_kind}")
    if camera_label not in CAMERA_LABELS:
        raise ValueError(f"unknown camera_label: {camera_label}")

    if post_kind == "irrelevant":
        return {"verdict": "ignore", "line": _IGNORE}
    if post_kind == "rumor":
        return _rumor(camera_label)
    if post_kind == "confirmed":
        return _confirmed(camera_label)
    return _evacuation(camera_label)


def _rumor(camera_label: str) -> dict[str, str]:
    if camera_label in _CLEAR:
        return {"verdict": "contradicted", "line": _ROAD_OPEN}
    if camera_label in _BLOCKED:
        return {"verdict": "supported", "line": _NOT_PASSABLE}
    return {"verdict": "inconclusive", "line": _RUMOR_PARTIAL}


def _confirmed(camera_label: str) -> dict[str, str]:
    if camera_label in _BLOCKED:
        return {"verdict": "supported", "line": _NOT_PASSABLE}
    if camera_label == "standing water":
        return {"verdict": "supported", "line": _STANDING}
    if camera_label in _CLEAR:
        return {"verdict": "contradicted", "line": _ROAD_OPEN}
    return {"verdict": "inconclusive", "line": _CONFIRMED_WET}


def _evacuation(camera_label: str) -> dict[str, str]:
    if camera_label == "dry":
        return {"verdict": "contradicted", "line": _DRY_ROAD}
    if camera_label in _FLOOD:
        return {"verdict": "supported", "line": _FLOODING}
    return {"verdict": "contradicted", "line": _ROAD_OPEN}
