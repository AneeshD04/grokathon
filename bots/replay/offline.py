"""Print one saved camera scene offline. No HTTP and no model API calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Spoken lines for JF13-3 with water above the bank, used only if demo_card
# cannot be imported. Same pair demo_card.main() prints for that sensor.
_FALLBACK_SENTENCES = {
    "impassable": "Do not drive through because JF13-3 is above its bank.",
    "dry": "The camera is still clear, but the sensor JF13-3 is above its bank.",
}

try:
    from bots.demo_card import demo_line
except ImportError:

    def demo_line(vision_class: str, warning: dict | None) -> str:
        key = " ".join((vision_class or "").strip().lower().split())
        if key in _FALLBACK_SENTENCES:
            return _FALLBACK_SENTENCES[key]
        return _FALLBACK_SENTENCES["dry"]


_SCENE = Path(__file__).resolve().parent / "scene.json"


def load_scene(path: Path | None = None) -> dict:
    target = _SCENE if path is None else path
    with target.open(encoding="utf-8") as handle:
        scene = json.load(handle)
    if not isinstance(scene, dict):
        raise ValueError("scene must be a JSON object")
    return scene


def _warning(sensor: dict) -> dict:
    """Map the scene sensor onto the keys demo_line reads."""
    return {
        "name": sensor.get("name"),
        "water_level": sensor.get("water", sensor.get("water_level")),
        "bank_height": sensor.get("bank", sensor.get("bank_height")),
        "status": sensor.get("status"),
    }


def main() -> None:
    scene = load_scene()
    camera = scene["camera"]
    name = str(camera["name"])
    label = str(scene["label"])
    print(f"{name} {label}")
    print(demo_line(label, _warning(scene["sensor"])))


if __name__ == "__main__":
    main()
