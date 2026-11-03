"""One spoken sentence for the flood demo. Stdlib only; no network and no .env."""

from __future__ import annotations

import json
from pathlib import Path

# Spoken labels and the alert-class spellings that mean the same thing.
_HAZARD = {
    "impassable",
    "people in water",
    "standing water",
    "overtopped road",
    "water over roadway",
    "water over road",
}

_CLEAR = {
    "dry",
    "all clear",
    "clear",
}


def demo_line(vision_class: str, warning: dict | None) -> str:
    """Return one short sentence a person can read aloud."""
    kind = _kind(vision_class)
    above, name = _above_bank(warning)
    if kind == "hazard":
        if above:
            return f"Do not drive through because {_bank_clause(name)}."
        return "Do not drive through."
    if kind == "clear":
        if above:
            return f"The camera is still clear, but {_bank_clause(name, sensor_word=True)}."
        return "The camera is still clear."
    label = " ".join((vision_class or "unknown").split()) or "unknown"
    if above:
        return f"The camera reports {label}, and {_bank_clause(name, sensor_word=True)}."
    return f"The camera reports {label}."


def _bank_clause(name: str, *, sensor_word: bool = False) -> str:
    if name.lower() in {"sensor", "the sensor"}:
        return "the sensor is above its bank"
    if sensor_word:
        return f"the sensor {name} is above its bank"
    return f"{name} is above its bank"


def _kind(vision_class: str) -> str:
    text = (vision_class or "").strip().lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split()).strip(" .,;:!")
    if text in _HAZARD:
        return "hazard"
    if text in _CLEAR:
        return "clear"
    return "other"


def _above_bank(warning: dict | None) -> tuple[bool, str]:
    if not isinstance(warning, dict):
        return False, "the sensor"
    name = _text(warning, "name", "SensorName", "Name") or "the sensor"
    water = _number(warning, "water_level", "WaterLevel", "StreamElevationLatestValue")
    bank = _number(warning, "bank_height", "BankHeight", "TopOfBank")
    if water is None or bank is None:
        return False, name
    return water > bank, name


def _number(record: dict, *keys: str) -> float | None:
    for key in keys:
        if key not in record or record[key] in (None, ""):
            continue
        try:
            return float(record[key])
        except (TypeError, ValueError):
            continue
    return None


def _text(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def warnings_path() -> Path:
    """``bots/data/flood_warnings.json`` relative to the repo that holds this file."""
    repo = Path(__file__).resolve().parent.parent
    return repo / "bots" / "data" / "flood_warnings.json"


def load_warning(path: Path | None = None) -> dict | None:
    target = warnings_path() if path is None else path
    with target.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    points = payload if isinstance(payload, list) else [payload]
    first: dict | None = None
    for item in points:
        if not isinstance(item, dict):
            continue
        if first is None:
            first = item
        if str(item.get("id", "")) == "145":
            return item
    return first


def main() -> None:
    warning = load_warning()
    print(demo_line("impassable", warning))
    print(demo_line("dry", warning))


if __name__ == "__main__":
    main()
