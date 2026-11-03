"""Print one Galveston Ferry label. Default mode is offline and spends zero API calls.

``python3 -m bots.oneshot.run`` reads ``bots/replay/scene.json`` when that file
is present and otherwise prints the saved dry-road line. It does not open a
socket, read ``.env``, or call the model API. ``--live`` is accepted and ignored
so a demo run cannot spend a call.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CAMERA = "Galveston Ferry @ Galveston Ferry Landing"
LABEL = "dry"
SENTENCE = "The camera is still clear, but the sensor JF13-3 is above its bank."
WATER = 3.51
BANK = 2.405


def scene_path() -> Path:
    return Path(__file__).resolve().parents[1] / "replay" / "scene.json"


def load_scene(path: Path | None = None) -> tuple[str, str, str]:
    """Return camera, label, and spoken sentence for the one-shot demo."""
    target = scene_path() if path is None else path
    if not target.is_file():
        return CAMERA, LABEL, SENTENCE
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CAMERA, LABEL, SENTENCE
    if not isinstance(payload, dict):
        return CAMERA, LABEL, SENTENCE
    camera = _camera_name(payload) or CAMERA
    label = _label(payload) or LABEL
    sentence = _sentence(payload) or SENTENCE
    return camera, label, sentence


def gauge_surplus() -> str | None:
    """Surplus feet from ``bots.gauge.bank`` when that module imports.

    Uses the saved JF13-3 reading: water 3.51, bank 2.405. Returns None when
    ``bots/gauge/bank.py`` cannot be imported, so the offline demo still runs.
    """
    try:
        from bots.gauge.bank import surplus_feet
    except ImportError:
        return None
    surplus = surplus_feet(WATER, BANK)
    return f"{surplus:.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print one camera label. Default is offline and makes no API calls.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Accepted and ignored. This command stays offline and does not call the API.",
    )
    parser.parse_args(argv)
    camera, label, sentence = load_scene()
    print(camera)
    print(label)
    print(sentence)
    surplus = gauge_surplus()
    if surplus is not None:
        print(f"gauge surplus {surplus}")
    return 0


def _camera_name(payload: dict) -> str:
    camera = payload.get("camera", payload.get("name"))
    if isinstance(camera, str) and camera.strip():
        return camera.strip()
    if isinstance(camera, dict):
        name = camera.get("name") or camera.get("camera")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def _label(payload: dict) -> str:
    label = payload.get("label", payload.get("vision_class"))
    if isinstance(label, str) and label.strip():
        return label.strip()
    return ""


def _sentence(payload: dict) -> str:
    for key in ("sentence", "line", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
