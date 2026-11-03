"""Print the offline flood show. No network and no API calls."""

from __future__ import annotations

import json
from pathlib import Path

_SCENE = Path(__file__).resolve().parents[1] / "replay" / "scene.json"

_CAMERA_FALLBACK = "Galveston Ferry dry"
_GAUGE_FALLBACK = "The stream at JF13-3 is above the bank by 1.11 feet."
_DEMO_FALLBACK = "The camera is still clear, but the sensor JF13-3 is above its bank."
_RUMOR_FALLBACK = "contradicted: the camera still shows the road open."

# Saved JF13-3 reading: 3.51 ft on a 2.405 ft bank, spoken as 1.11 ft over.
_WARNING = {
    "name": "JF13-3",
    "water_level": 3.51,
    "bank_height": 2.405,
}


def camera_line() -> str:
    """Camera name and label from the saved scene, or the dry ferry fallback."""
    if not _SCENE.is_file():
        return _CAMERA_FALLBACK
    try:
        scene = json.loads(_SCENE.read_text(encoding="utf-8"))
        name = str(scene["camera"]["name"]).strip()
        label = str(scene["label"]).strip()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _CAMERA_FALLBACK
    if not name or not label:
        return _CAMERA_FALLBACK
    return f"{name} {label}"


def gauge_line() -> str:
    """Spoken gauge from bots.gauge.bank, or the fixed JF13-3 sentence."""
    try:
        from bots.gauge.bank import spoken_gauge
    except ImportError:
        return _GAUGE_FALLBACK
    return spoken_gauge(_WARNING)


def demo_sentence() -> str:
    """One demo sentence from bots.demo_card, or the clear-camera fallback."""
    try:
        from bots.demo_card import demo_line
    except ImportError:
        return _DEMO_FALLBACK
    return demo_line("dry", _WARNING)


def rumor_verdict() -> str:
    """Rumor versus a dry camera, or the contradicted fallback."""
    try:
        from bots.rumor.check import compare_rumor
    except ImportError:
        return _RUMOR_FALLBACK
    got = compare_rumor("rumor", "dry")
    return f"{got['verdict']}: {got['line']}"


def cost_line() -> str:
    """Zero live calls and the matching dollar estimate."""
    calls = 0
    try:
        from bots.cost_guard import estimated_usd

        usd = estimated_usd(calls)
    except ImportError:
        usd = 0
    shown = format(usd, "g") if isinstance(usd, float) else usd
    return f"{calls} live calls, estimated usd {shown}"


def main() -> None:
    print(camera_line())
    print(gauge_line())
    print(demo_sentence())
    print(rumor_verdict())
    print(cost_line())


if __name__ == "__main__":
    main()
