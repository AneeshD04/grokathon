"""Pure comparisons of a stream gauge against its bank height."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def above_bank(water_level, bank_height) -> bool:
    """True when the water surface is higher than the top of the bank."""
    return float(water_level) > float(bank_height)


def surplus_feet(water_level, bank_height) -> float:
    """Feet of water above the bank. Negative when the stream is still below it."""
    return float(water_level) - float(bank_height)


def spoken_gauge(warning: dict) -> str:
    """One sentence naming the gauge and how it sits relative to the bank.

    The surplus is the water level minus the bank height, rounded half away
    from zero to two decimal places so 1.105 feet is spoken as 1.11.
    """
    name = warning["name"]
    water = warning["water_level"]
    bank = warning["bank_height"]
    shown = _round_half_up(Decimal(str(water)) - Decimal(str(bank)), 2)
    feet = f"{shown:.2f}"
    if above_bank(water, bank):
        return f"The stream at {name} is above the bank by {feet} feet."
    if shown < 0:
        return f"The stream at {name} is below the bank by {abs(shown):.2f} feet."
    return f"The stream at {name} is level with the bank, surplus {feet} feet."


def _round_half_up(value: Decimal, places: int) -> Decimal:
    quant = Decimal("1").scaleb(-places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)
