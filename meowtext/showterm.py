"""Phosphor variations and the next picture group, as terminal-sized panels.

Run ``python3 -m meowtext.showterm`` to write the PNGs. Each panel is a whole
number of terminal cells (10 by 22), the size kitty uses for one cell.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from meowtext.phosphor import PhosphorView, phosphor_panel
from meowtext.pixels import CELL_H, CELL_W

OUT = Path("/tmp/meowtext-show")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

YELLOW = (232, 214, 64)
CYAN = (48, 214, 220)
GREEN = (70, 220, 90)
ORANGE = (232, 140, 48)
PINK = (230, 110, 170)
PURPLE = (150, 96, 220)
DIM = (70, 78, 72)
PAPER = (0, 0, 0)


def phosphor_variations() -> list[tuple[str, Image.Image]]:
    """Four ways the phosphor page can sit in a terminal."""

    columns, rows = 48, 14
    views = (
        ("Quiet", PhosphorView(glow="soft")),
        ("Ruled", PhosphorView(border=True, texture="graph", glow="soft")),
        ("Chunky", PhosphorView(border=True, texture="plus", font="terminus", glow="soft")),
        ("Hot", PhosphorView(border=True, texture="both", glow="strong", font="hack")),
    )
    panels = []
    for name, view in views:
        panel = phosphor_panel(
            PhosphorView(
                border=view.border,
                font=view.font,
                texture=view.texture,
                glow=view.glow,
                width=columns * CELL_W,
                height=rows * CELL_H,
            )
        )
        panels.append((name, panel))
    return panels


def access_node() -> Image.Image:
    """Yellow and cyan. A status column, one ring, a trace along the bottom."""

    image, draw = _board(60, 16)
    title, body, small = _faces(15, 12, 11)
    draw.text((16, 10), "://ACCESS_DATA_NODE", font=title, fill=YELLOW)
    draw.text((250, 14), "SERVER 12-D  /  LEVEL 3", font=small, fill=CYAN)
    _box(draw, 16, 40, 168, 250)
    draw.text((26, 48), "SERVER_STATUS", font=small, fill=YELLOW)
    for index, (label, ink) in enumerate(
        (("ONLINE", CYAN), ("ONLINE", CYAN), ("ONLINE", CYAN), ("OFFLINE", DIM))
    ):
        y = 72 + index * 22
        draw.text((26, y), label, font=small, fill=ink)
        draw.text((150, y), str(index + 1), font=small, fill=ink)
    draw.text((26, 176), "LOOKUP_DATA", font=small, fill=YELLOW)
    for index, (code, value) in enumerate((("LND", "787"), ("SYD", "556"), ("NYC", "019"), ("LAX", "977"))):
        y = 198 + index * 20
        draw.text((26, y), code, font=small, fill=YELLOW)
        draw.text((78, y), value, font=small, fill=CYAN)
    _ring(draw, 330, 168)
    draw.text((470, 48), "SIGNAL", font=small, fill=YELLOW)
    draw.text((470, 68), "82", font=title, fill=CYAN)
    draw.text((470, 108), "FLOW A", font=small, fill=YELLOW)
    draw.text((470, 126), "+174.03", font=body, fill=CYAN)
    draw.text((470, 156), "FLOW B", font=small, fill=YELLOW)
    draw.text((470, 174), "+126.88", font=body, fill=CYAN)
    _trace(draw, 16, 300, 568, 40)
    return image


def colony_ship() -> Image.Image:
    """Three decks of nodes and tubes, and a short key."""

    image, draw = _board(60, 16)
    small = _faces(11)[0]
    draw.rectangle((4, 4, 404, 348), outline=PURPLE, width=2)
    draw.text((420, 12), "SHIP KEY", font=small, fill=YELLOW)
    key = (("w", YELLOW, "Weapons"), ("e", ORANGE, "Engine"), ("l", CYAN, "Life"), ("h", GREEN, "Hold"))
    for index, (mark, ink, name) in enumerate(key):
        y = 40 + index * 28
        draw.rectangle((420, y, 438, y + 16), outline=ink)
        draw.text((424, y + 1), mark, font=small, fill=ink)
        draw.text((448, y + 1), name, font=small, fill=ink)
    decks = (
        ("DECK 1", ((30, 36, YELLOW, "w"), (120, 28, CYAN, "l"), (210, 36, ORANGE, "e"), (300, 28, GREEN, "h"))),
        ("DECK 2", ((40, 36, CYAN, "l"), (130, 20, ORANGE, "e"), (230, 36, YELLOW, "w"), (310, 48, GREEN, "h"))),
        ("DECK 3", ((36, 40, GREEN, "h"), (140, 28, YELLOW, "w"), (240, 40, CYAN, "l"), (320, 24, ORANGE, "e"))),
    )
    for index, (name, nodes) in enumerate(decks):
        top = 14 + index * 112
        draw.line((12, top + 100, 392, top + 100), fill=PURPLE)
        draw.text((16, top), name, font=small, fill=YELLOW)
        centers = []
        for x, y, ink, mark in nodes:
            px, py = 24 + x, top + y
            draw.rectangle((px, py, px + 36, py + 22), outline=ink)
            draw.text((px + 12, py + 4), mark, font=small, fill=ink)
            centers.append((px + 18, py + 11))
        for start, end in zip(centers, centers[1:]):
            draw.line((start, end), fill=DIM)
    return image


def fastfetch() -> Image.Image:
    """A pink block mark beside a hardware card. Green bars, yellow labels."""

    image, draw = _board(60, 16)
    title, body, small = _faces(16, 13, 11)
    _mark(draw, 24, 48)
    draw.text((250, 16), "Hey,", font=title, fill=GREEN)
    _box(draw, 250, 52, 320, 200)
    draw.text((270, 60), "Hardware", font=small, fill=YELLOW)
    rows = (("CPU", "Ryzen 5", 0.0), ("RAM", "12.6 / 15.9", 0.79), ("DRIVE", "313 / 464", 0.67), ("DRIVE", "148 / 488", 0.31))
    for index, (label, value, level) in enumerate(rows):
        y = 88 + index * 36
        draw.text((266, y), label, font=small, fill=YELLOW)
        draw.text((320, y), value, font=small, fill=GREEN)
        if level:
            _bar(draw, 430, y + 2, 120, 12, level)
    draw.text((250, 276), "Bonsoir.", font=body, fill=ORANGE)
    return image


def write_panels(directory: Path = OUT) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, panel in phosphor_variations():
        path = directory / f"phosphor-{name.lower()}.png"
        panel.save(path)
        saved.append(path)
    for name, panel in (
        ("access-node", access_node()),
        ("colony-ship", colony_ship()),
        ("fastfetch", fastfetch()),
    ):
        path = directory / f"{name}.png"
        panel.save(path)
        saved.append(path)
    return saved


def _board(columns: int, rows: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (columns * CELL_W, rows * CELL_H), PAPER)
    return image, ImageDraw.Draw(image)


def _faces(*sizes: int) -> tuple[ImageFont.ImageFont, ...]:
    return tuple(ImageFont.truetype(FONT, size) for size in sizes)


def _box(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, ink: tuple[int, int, int] = YELLOW) -> None:
    draw.rectangle((x, y, x + width, y + height), outline=ink)


def _ring(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    for index, radius in enumerate((112, 88, 66, 46, 28, 12)):
        ink = CYAN if index % 2 == 0 else YELLOW
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=ink, width=2)
    draw.line((cx - 120, cy, cx + 120, cy), fill=DIM)
    draw.line((cx, cy - 120, cx, cy + 120), fill=DIM)


def _trace(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int) -> None:
    mid = y + height // 2
    points = []
    for step in range(width):
        t = step / width
        wave = math.sin(t * 16) * (height * 0.28) + math.sin(t * 47) * (height * 0.12)
        points.append((x + step, mid - wave))
    draw.line(points, fill=YELLOW, width=1)
    for spike in (0.18, 0.47, 0.73):
        sx = x + int(width * spike)
        draw.line((sx, mid - 16, sx, mid + 10), fill=CYAN)


def _bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, level: float) -> None:
    draw.rectangle((x, y, x + width, y + height), outline=GREEN)
    draw.rectangle((x, y, x + int(width * level), y + height), fill=GREEN)


def _mark(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """Characters, the way the fastfetch portrait is drawn."""

    art = (
        "    ++      ++",
        "  ++++++  ++++++",
        " +++++++++++++++",
        " +++  ++++  +++",
        " +++  ++++  +++",
        " +++++++++++++++",
        "   +++++++++++",
        "     +++++++",
        "      +++++",
        "    +++++++++",
        "  +++++++++++++",
        " +++++++++++++++",
        " +++        +++",
        " +++        +++",
        "  ++        ++",
    )
    face = ImageFont.truetype(FONT, 16)
    for index, line in enumerate(art):
        draw.text((x, y + index * 16), line, font=face, fill=PINK)


def main() -> None:
    for path in write_panels():
        print(path)


if __name__ == "__main__":
    main()
