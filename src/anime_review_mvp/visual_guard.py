from __future__ import annotations

from pathlib import Path

from PIL import Image


def looks_like_publisher_bumper(path: Path) -> bool:
    """Identify a flat red-on-white publisher card without trusting editorial text."""
    with Image.open(path) as source:
        image = source.convert("RGB").resize((160, 90), Image.Resampling.BILINEAR)
    pixels = tuple(image.get_flattened_data())
    total = len(pixels)
    near_white = sum(red >= 220 and green >= 220 and blue >= 220 for red, green, blue in pixels)
    strong_red = sum(
        red >= 160 and red >= green + 60 and red >= blue + 60
        for red, green, blue in pixels
    )
    white_ratio = near_white / total
    red_ratio = strong_red / total
    return white_ratio >= 0.35 and red_ratio >= 0.18 and white_ratio + red_ratio >= 0.65
