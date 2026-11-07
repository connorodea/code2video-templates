"""Shared typography and frame-independent drawing helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math
import os
import random
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]


def clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def ease(value: float) -> float:
    return 1.0 - (1.0 - clamp(value)) ** 3


def mix(a: float, b: float, value: float) -> float:
    return a + (b - a) * value


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))


def blend(a: str, b: str, value: float) -> tuple[int, int, int]:
    return tuple(round(mix(x, y, value)) for x, y in zip(rgb(a), rgb(b)))


def font_path(mono: bool = False) -> Path:
    custom = os.environ.get("SIGNATURE_MOTION_FONT")
    candidates = [Path(custom)] if custom else []
    # Reuse the OFL font already tracked in this repository. Do not fetch fonts.
    candidates += [ROOT / "apple-notes-video/vendor/assets/InterVariable.ttf"]
    if mono:
        candidates += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")]
    candidates += [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise RuntimeError("No usable font. Set SIGNATURE_MOTION_FONT to a local TTF or OTF file.")


@lru_cache(maxsize=256)
def font(size: int | float, weight: int = 700, mono: bool = False) -> ImageFont.FreeTypeFont:
    result = ImageFont.truetype(str(font_path(mono)), max(1, int(round(size))))
    try:
        axes = result.get_variation_axes()
        values = []
        for axis in axes:
            name = axis["name"].decode("utf8").lower()
            target = weight if "weight" in name else min(32, max(14, size))
            if "weight" not in name and "optical" not in name:
                target = axis["default"]
            values.append(max(axis["minimum"], min(axis["maximum"], target)))
        result.set_variation_by_axes(values)
    except (AttributeError, OSError):
        pass
    return result


def text(draw: ImageDraw.ImageDraw, xy, value: str, size: float, fill, weight: int = 700,
         anchor: str = "lt", max_width: float | None = None, spacing: float = 0):
    """Draw actual glyphs, fitting by measured width instead of character estimates."""
    chosen = max(1, round(size))
    if max_width:
        while chosen > 6 and draw.textlength(value, font=font(chosen, weight)) > max_width:
            chosen -= 1
    face = font(chosen, weight)
    draw.text(xy, value, font=face, fill=fill, anchor=anchor, spacing=spacing)
    return draw.textbbox(xy, value, font=face, anchor=anchor, spacing=spacing)


def wrap(value: str, max_width: float, size: float, weight: int = 700) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    current = ""
    for word in value.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font(size, weight)) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def label(draw, xy, value, size, color):
    return text(draw, xy, value.upper(), size, color, weight=600)


def footer(draw, config, color=None):
    w, h = config["width"], config["height"]
    ink = color or config["palette"]["foreground"]
    s = min(w, h)
    label(draw, (w * .075, h * .89), config["brand"], s * .021, ink)
    if config.get("demo"):
        text(draw, (w * .925, h * .89), "DEMO", s * .018, ink, weight=600, anchor="rt")


@lru_cache(maxsize=12)
def paper(w: int, h: int, background: str, seed: int) -> Image.Image:
    image = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    base = rgb(background)
    # Sparse fiber marks remain static: no shimmering per-frame noise.
    for _ in range(int(w * h / 600)):
        x, y = rng.randrange(w), rng.randrange(h)
        shade = tuple(max(0, v - rng.randrange(4, 14)) for v in base)
        draw.line((x, y, x + rng.randrange(1, 4), y), fill=shade, width=1)
    return image


def draw_lines(draw, lines, x, y, size, color, max_width, line_height=1.12, weight=700):
    for index, line in enumerate(lines):
        text(draw, (x, y + index * size * line_height), line, size, color,
             weight=weight, max_width=max_width)


def phase(config, frame_index):
    return clamp(frame_index / (config["fps"] * config["duration"]))
