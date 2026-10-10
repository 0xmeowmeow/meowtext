"""Continuous parts, drawn in real pixels.

A terminal cell is the wrong place for a circle or a smooth meter. eventhorizon
draws the black hole the same way: real pixels through the kitty graphics
protocol, placed under the text. A cell in kitty and Ghostty is 10 by 22
pixels, so a round dial is given a square of those pixels instead of a ring of
characters.

Lines, frames, and readouts stay on the cell grid. They are what a cell is good at.
"""

from __future__ import annotations

import base64
import math
from io import BytesIO

from PIL import Image, ImageDraw

from meowtext.grid import Color

# Measured for kitty and Ghostty in the luminet notes.
CELL_W = 10
CELL_H = 22


def dial(value: float, ink: Color, *, columns: int = 16, rows: int = 8) -> Image.Image:
    """A round meter. Zero is lower left, full is lower right, and the top is halfway."""

    image, draw, scale = _canvas(columns, rows)
    width, height = image.size
    radius = min(width, height) * 0.40
    cx, cy = width / 2, height / 2
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    dim = _rgba(ink, 80)
    bright = _rgba(ink, 255)
    width_px = max(2, 2 * scale)
    # Pillow measures degrees clockwise from the east. 135° is lower left,
    # and clockwise through the top lands on 45°, the lower right.
    draw.arc(box, start=135, end=45, fill=dim, width=width_px)
    covered = 135 + _unit(value) * 270
    if _unit(value) > 0:
        draw.arc(box, start=135, end=covered % 360, fill=bright, width=width_px)
    for mark in (0, 0.25, 0.5, 0.75, 1):
        _tick(draw, cx, cy, radius, _needle_angle(mark), bright, scale)
    angle = _needle_angle(value)
    tip = (
        cx + math.cos(angle) * radius * 0.72,
        cy - math.sin(angle) * radius * 0.72,
    )
    draw.line([(cx, cy), tip], fill=bright, width=width_px)
    hub = max(3, 3 * scale)
    draw.ellipse((cx - hub, cy - hub, cx + hub, cy + hub), fill=bright)
    return _finish(image, scale)


def gauge(value: float, ink: Color, *, columns: int = 20, rows: int = 2) -> Image.Image:
    """A smooth horizontal meter. The fill is a length, not a count of blocks."""

    image, draw, scale = _canvas(columns, rows)
    width, height = image.size
    pad = 2 * scale
    thickness = max(4 * scale, int(height * 0.42))
    top = (height - thickness) / 2
    radius = thickness / 2
    track = (pad, top, width - pad, top + thickness)
    draw.rounded_rectangle(track, radius=radius, fill=_rgba(ink, 50))
    inner = (width - 2 * pad) * _unit(value)
    if inner > 1:
        draw.rounded_rectangle((pad, top, pad + inner, top + thickness), radius=radius, fill=_rgba(ink, 255))
    return _finish(image, scale)


def fader(value: float, ink: Color, *, columns: int = 3, rows: int = 8, vertical: bool = True) -> Image.Image:
    """A smooth track and a thumb. Up and right are full."""

    image, draw, scale = _canvas(columns, rows)
    width, height = image.size
    amount = _unit(value)
    if vertical:
        thickness = max(3 * scale, int(width * 0.28))
        left = (width - thickness) / 2
        margin = thickness
        draw.rounded_rectangle(
            (left, margin, left + thickness, height - margin),
            radius=thickness / 2,
            fill=_rgba(ink, 50),
        )
        travel = height - 3 * margin
        center = margin + (1 - amount) * travel
        thumb = thickness * 1.6
        draw.rounded_rectangle(
            (left - thickness * 0.3, center - thumb / 2, left + thickness * 1.3, center + thumb / 2),
            radius=scale * 2,
            fill=_rgba(ink, 255),
        )
    else:
        thickness = max(3 * scale, int(height * 0.28))
        top = (height - thickness) / 2
        margin = thickness
        draw.rounded_rectangle(
            (margin, top, width - margin, top + thickness),
            radius=thickness / 2,
            fill=_rgba(ink, 50),
        )
        travel = width - 3 * margin
        center = margin + amount * travel
        thumb = thickness * 1.6
        draw.rounded_rectangle(
            (center - thumb / 2, top - thickness * 0.3, center + thumb / 2, top + thickness * 1.3),
            radius=scale * 2,
            fill=_rgba(ink, 255),
        )
    return _finish(image, scale)


def lamp(value: float, ink: Color, *, columns: int = 3, rows: int = 2) -> Image.Image:
    """A glowing disc. Empty is a dim ring. Full is a solid light."""

    image, draw, scale = _canvas(columns, rows)
    width, height = image.size
    amount = _unit(value)
    cx, cy = width / 2, height / 2
    radius = min(width, height) * 0.36
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=_rgba(ink, 140),
        width=max(1, scale),
    )
    if amount > 0:
        glow = radius * (0.35 + 0.65 * amount)
        draw.ellipse((cx - glow, cy - glow, cx + glow, cy + glow), fill=_rgba(ink, int(40 + 200 * amount)))
    return _finish(image, scale)


def paste(base: Image.Image, part: Image.Image, column: int, row: int) -> None:
    """Lay a part onto a panel at a cell position."""

    base.alpha_composite(part, (column * CELL_W, row * CELL_H))


def kitty_place(image: Image.Image, columns: int, rows: int, *, image_id: int = 1) -> str:
    """One kitty graphics sequence. The picture sits under later text, as in eventhorizon.

    ``z=-1`` places it beneath glyphs. ``c`` and ``r`` are the cell rectangle it
    occupies. ``q=2`` asks the terminal not to answer.
    """

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
    placement = f"i={image_id},c={columns},r={rows},q=2,z=-1"
    parts: list[str] = []
    step = 4096
    for offset in range(0, max(len(payload), 1), step):
        piece = payload[offset : offset + step]
        more = 1 if offset + step < len(payload) else 0
        control = f"a=T,f=100,{placement},m={more}" if offset == 0 else f"m={more}"
        parts.append(f"\x1b_G{control};{piece}\x1b\\")
    return "".join(parts)


def _canvas(columns: int, rows: int, scale: int = 2) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    columns = max(1, columns)
    rows = max(1, rows)
    image = Image.new("RGBA", (columns * CELL_W * scale, rows * CELL_H * scale), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image), scale


def _finish(image: Image.Image, scale: int) -> Image.Image:
    if scale == 1:
        return image
    return image.resize((image.width // scale, image.height // scale), Image.Resampling.LANCZOS)


def _rgba(ink: Color, alpha: int) -> tuple[int, int, int, int]:
    return (ink.r, ink.g, ink.b, alpha)


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _needle_angle(value: float) -> float:
    return math.radians(225 - _unit(value) * 270)


def _tick(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, angle: float, color, scale: int) -> None:
    inner = radius * 0.86
    outer = radius * 1.02
    draw.line(
        [
            (cx + math.cos(angle) * inner, cy - math.sin(angle) * inner),
            (cx + math.cos(angle) * outer, cy - math.sin(angle) * outer),
        ],
        fill=color,
        width=max(1, scale),
    )
