"""FAST flood/water labels from JPEG pixels. No Grok, no overnight loop."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger("camwatch")


def mean_rgb(jpeg: bytes) -> tuple[float, float, float] | None:
    """Average RGB of a downsampled still. None when the JPEG cannot be read."""
    if not jpeg or not jpeg.startswith(b"\xff\xd8"):
        return None
    try:
        from PIL import Image
    except ImportError:
        logger.info("Pillow is not installed; FAST color classify is skipped")
        return None
    try:
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        image.thumbnail((48, 48))
        pixels = list(image.getdata())
    except (OSError, ValueError, SyntaxError):
        return None
    if not pixels:
        return None
    count = float(len(pixels))
    red = sum(pixel[0] for pixel in pixels) / count
    green = sum(pixel[1] for pixel in pixels) / count
    blue = sum(pixel[2] for pixel in pixels) / count
    return red, green, blue


def class_from_rgb(red: float, green: float, blue: float) -> tuple[str, float, bool]:
    """Map mean RGB onto the #17 classes.

    Tuned on the CamWatch fixtures: flooded-road.jpg is steel-blue
    ``(78, 110, 121)``; clear-road.jpg is gray ``(208, 208, 208)``.
    """
    luma = (red + green + blue) / 3.0
    blue_excess = blue - red
    if blue_excess >= 30 and luma < 140:
        return "overtopped_road", 0.72, False
    if blue_excess >= 18 and luma < 170:
        return "standing_water", 0.64, False
    return "all_clear", 0.55, False
