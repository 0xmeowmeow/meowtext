"""The phosphor screen as a terminal UI.

The plate, the readouts, and the frames are cells. The picture, the wave,
and the round meters are pixels, because a curve does not fit in a cell.
Keys 1–4 swap the look. ``a`` changes the panel arrangement. The same
readings run through the wave, the data bars, and the meters.
"""

from __future__ import annotations

import math
import select
import shutil
import sys
import termios
import tty
from dataclasses import dataclass

from PIL import Image, ImageDraw

from meowtext.grid import Color
from meowtext.panels import bloom, render_image
from meowtext.phosphor import DIM, EYE, GLOWS, INK, PhosphorView, _texture, _trace
from meowtext.pixels import CELL_H, CELL_W, dial, fader, gauge, kitty_place

BLACK = Color(0, 0, 0)
_READINGS = (12, 40, 75, 90, 55)
_ARRANGEMENTS = ("wave", "beside", "stack", "grid")
_EYE: dict[tuple[int, int], Image.Image] = {}
_PLACED: dict[tuple, str] = {}

LOOKS: tuple[tuple[str, str, PhosphorView], ...] = (
    ("1", "quiet", PhosphorView(glow="soft")),
    ("2", "ruled", PhosphorView(border=True, texture="graph", glow="soft")),
    ("3", "chunky", PhosphorView(border=True, texture="plus", font="terminus", glow="soft")),
    ("4", "hot", PhosphorView(border=True, texture="both", glow="strong", font="hack")),
)


@dataclass(frozen=True, slots=True)
class _Panel:
    kind: str
    box: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class _Placed:
    image_id: int
    column: int
    row: int
    image: Image.Image
    stable: bool = False


def readings(tick: int, count: int) -> list[float]:
    """A window of the signal, long enough for the wave to move."""

    count = max(2, count)
    values = []
    for step in range(count):
        index = tick + step
        place = (index / 7) % len(_READINGS)
        left = int(place) % len(_READINGS)
        right = (left + 1) % len(_READINGS)
        mix = place - int(place)
        base = _READINGS[left] * (1 - mix) + _READINGS[right] * mix
        swell = 16 * math.sin(index / 11) + 7 * math.sin(index / 4)
        values.append(max(0.0, min(100.0, base + swell)))
    return values


def run(look: str | None = None) -> None:
    """Full-screen phosphor. ``1``–``4`` change the look, ``a`` the arrangement."""

    names = {key: name for key, name, _view in LOOKS}
    chosen = look if look in names.values() else "quiet"
    arrangement = 0
    tick = 0
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            _paint(chosen, _ARRANGEMENTS[arrangement], tick)
            ready, _, _ = select.select([fd], [], [], 0.12)
            tick += 1
            if not ready:
                continue
            key = sys.stdin.read(1)
            if key in {"q", "Q", "\x03"}:
                return
            if key in {"a", "A", "\t"}:
                arrangement = (arrangement + 1) % len(_ARRANGEMENTS)
                sys.stdout.write("\x1b[2J\x1b_Ga=d\x1b\\")
            else:
                chosen = names.get(key, chosen)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        sys.stdout.write("\x1b_Ga=d\x1b\\\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def _paint(look: str, arrangement: str, tick: int) -> None:
    columns, rows = _size()
    rows = max(12, rows - 1)
    view = next(item[2] for item in LOOKS if item[1] == look)
    text, placed = _screen(columns, rows, look, arrangement, view, tick)
    parts = ["\x1b[H"]
    for panel in placed:
        parts.append(f"\x1b[{panel.row + 1};{panel.column + 1}H")
        parts.append(_placement(panel))
    parts.append(text)
    sys.stdout.write("".join(parts))
    sys.stdout.flush()


def _screen(
    columns: int,
    rows: int,
    look: str,
    arrangement: str,
    view: PhosphorView,
    tick: int,
) -> tuple[str, list[_Placed]]:
    columns = max(columns, 48)
    rows = max(rows, 14)
    cells = [[(" ", None, None) for _ in range(columns)] for _ in range(rows)]
    samples = readings(tick, max(24, columns // 2))
    latest = samples[-1]

    def put(x: int, y: int, text: str, fg: Color, bg: Color | None = None) -> None:
        for offset, char in enumerate(text):
            if 0 <= y < rows and 0 <= x + offset < columns and char:
                cells[y][x + offset] = (char, fg, bg)

    plate = " PAGE D READY "
    put((columns - len(plate)) // 2, 0, plate, BLACK, INK)
    put(1, 0, "INDEX", DIM)
    put(columns - 12, 0, f"VOICE {latest:5.0f}", INK)
    put(columns - 12, 1, f"MODE  {arrangement[:5]:<5}", DIM)
    title = "WAVEFORM DISPLAY"
    put((columns - len(title)) // 2, 2, title, DIM)
    put(1, 3, "─" * (columns - 2), DIM)
    shown = "  ".join(f"{int(value):3d}" for value in samples[-8:])
    put(2, 4, f"DATA  {shown}", INK)

    frame = INK if view.border else DIM
    placed: list[_Placed] = []
    image_id = 1
    for kind, box in _regions(arrangement, 1, 6, columns - 2, rows - 2):
        _box(put, box[0], box[1], box[2], box[3], frame)
        inner = (box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1)
        if inner[2] - inner[0] < 4 or inner[3] - inner[1] < 2:
            continue
        put(inner[0], inner[1], kind.upper(), DIM)
        body = (inner[0], inner[1] + 1, inner[2], inner[3])
        if kind == "data":
            _bars(put, body, samples)
            continue
        picture = _pixels(kind, view, body, samples)
        if picture is None:
            continue
        _hole(cells, body)
        placed.append(_Placed(image_id, body[0], body[1], picture, stable=kind == "image"))
        image_id += 1

    put(1, rows - 1, f"{look}  {arrangement}    1-4 look    a arrange    q close", DIM)
    put(1, rows - 1, look, INK)
    return _ansi(cells), placed


def _regions(name: str, left: int, top: int, right: int, bottom: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    width = right - left
    height = bottom - top
    if name == "beside" and width >= 36:
        cut = left + max(14, width * 2 // 5)
        return [("image", (left, top, cut - 1, bottom)), ("wave", (cut + 1, top, right, bottom))]
    if name == "stack" and height >= 16 and width >= 36:
        mid = top + height * 3 // 5
        third = max(10, width // 3)
        return [
            ("wave", (left, top, right, mid - 1)),
            ("image", (left, mid + 1, left + third - 1, bottom)),
            ("data", (left + third + 1, mid + 1, left + 2 * third - 1, bottom)),
            ("meter", (left + 2 * third + 1, mid + 1, right, bottom)),
        ]
    if name == "grid" and width >= 36 and height >= 16:
        mid_x = left + width // 2
        mid_y = top + height // 2
        return [
            ("image", (left, top, mid_x - 1, mid_y - 1)),
            ("wave", (mid_x + 1, top, right, mid_y - 1)),
            ("data", (left, mid_y + 1, mid_x - 1, bottom)),
            ("meter", (mid_x + 1, mid_y + 1, right, bottom)),
        ]
    return [("wave", (left, top, right, bottom))]


def _placement(panel: _Placed) -> str:
    columns = max(1, panel.image.width // CELL_W)
    rows = max(1, panel.image.height // CELL_H)
    if not panel.stable:
        return kitty_place(panel.image, columns, rows, image_id=panel.image_id)
    key = (panel.image_id, panel.column, panel.row, columns, rows)
    cached = _PLACED.get(key)
    if cached is None:
        cached = kitty_place(panel.image, columns, rows, image_id=panel.image_id)
        _PLACED[key] = cached
    return cached


def _pixels(kind: str, view: PhosphorView, box: tuple[int, int, int, int], samples: list[float]) -> Image.Image | None:
    columns = box[2] - box[0] + 1
    rows = box[3] - box[1] + 1
    if columns < 2 or rows < 2:
        return None
    if kind == "wave":
        return _wave(view, columns, rows, samples)
    if kind == "image":
        return _eye(columns, rows)
    if kind == "meter":
        return _meter(samples[-1] / 100, columns, rows)
    return None


def _wave(view: PhosphorView, columns: int, rows: int, samples: list[float]) -> Image.Image:
    width, height = columns * CELL_W, rows * CELL_H
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = max(0.35, min(width / 900, height / 340))
    _texture(draw, (0, 0, width - 1, height - 1), view.texture, scale)
    pad = max(4, int(10 * scale))
    _trace(draw, pad, pad, max(2, width - 2 * pad), max(2, height - 2 * pad), scale)
    quiet = _fade(image, 0.22)
    _series(quiet, samples, pad)
    flat = Image.new("RGB", quiet.size, (0, 0, 0))
    flat.paste(quiet, mask=quiet.getchannel("A"))
    return bloom(flat, GLOWS.get(view.glow, GLOWS["soft"]))


def _series(image: Image.Image, samples: list[float], pad: int) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    span = max(1, len(samples) - 1)

    def line(offset: int, alpha: int, weight: int) -> None:
        points = []
        for index, value in enumerate(samples):
            shifted = samples[(index + offset) % len(samples)]
            x = pad + (index / span) * (width - 2 * pad)
            y = height - pad - (shifted / 100) * (height - 2 * pad)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=(INK.r, INK.g, INK.b, alpha), width=weight)

    for offset, alpha in ((18, 28), (9, 48)):
        line(offset, alpha, 1)
    line(0, 70, 3)
    line(0, 230, 1)


def _eye(columns: int, rows: int) -> Image.Image:
    key = (columns * CELL_W, rows * CELL_H)
    cached = _EYE.get(key)
    if cached is None:
        cached = render_image(EYE, key[0], key[1])
        _EYE[key] = cached
    return cached


def _meter(value: float, columns: int, rows: int) -> Image.Image:
    canvas = Image.new("RGBA", (columns * CELL_W, rows * CELL_H), (0, 0, 0, 0))
    gauge_rows = 2 if rows >= 5 else 1
    dial_rows = max(2, rows - gauge_rows)
    dial_columns = min(columns, max(4, round(dial_rows * CELL_H / CELL_W)))
    _paste(canvas, dial(value, INK, columns=dial_columns, rows=dial_rows), 0, 0)
    if columns - dial_columns >= 3:
        _paste(
            canvas,
            fader(value, INK, columns=min(3, columns - dial_columns), rows=dial_rows),
            (columns - 3) * CELL_W,
            0,
        )
    _paste(canvas, gauge(value, INK, columns=columns, rows=gauge_rows), 0, dial_rows * CELL_H)
    return canvas


def _bars(put, box: tuple[int, int, int, int], samples: list[float]) -> None:
    left, top, right, bottom = box
    width = right - left + 1
    height = bottom - top + 1
    if width < 2 or height < 2:
        return
    for column in range(width):
        index = min(len(samples) - 1, round(column / max(1, width - 1) * (len(samples) - 1)))
        fill = max(0, round((samples[index] / 100) * (height - 1)))
        for row in range(height):
            rising = height - 1 - row
            if rising < fill:
                put(left + column, top + row, "█", INK)
            elif rising == 0:
                put(left + column, top + row, "·", DIM)


def _fade(image: Image.Image, factor: float) -> Image.Image:
    red, green, blue, alpha = image.split()
    return Image.merge("RGBA", (red, green, blue, alpha.point(lambda value: int(value * factor))))


def _paste(base: Image.Image, part: Image.Image, x: int, y: int) -> None:
    part = part.convert("RGBA")
    if x >= base.width or y >= base.height:
        return
    clipped = part.crop((0, 0, min(part.width, base.width - x), min(part.height, base.height - y)))
    base.paste(clipped, (x, y), clipped)


def _hole(cells, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if 0 <= y < len(cells) and 0 <= x < len(cells[0]):
                cells[y][x] = ("", None, None)


def _box(put, left: int, top: int, right: int, bottom: int, ink: Color) -> None:
    if right <= left or bottom <= top:
        return
    put(left, top, "┌" + "─" * (right - left - 1) + "┐", ink)
    put(left, bottom, "└" + "─" * (right - left - 1) + "┘", ink)
    for y in range(top + 1, bottom):
        put(left, y, "│", ink)
        put(right, y, "│", ink)


def _ansi(cells: list[list[tuple[str, Color | None, Color | None]]]) -> str:
    lines = []
    for y, row in enumerate(cells):
        parts = [f"\x1b[{y + 1};1H"]
        skip = 0
        last_fg: Color | None = object()  # type: ignore[assignment]
        last_bg: Color | None = object()  # type: ignore[assignment]
        for char, fg, bg in row:
            if char == "":
                skip += 1
                last_fg = object()  # type: ignore[assignment]
                last_bg = object()  # type: ignore[assignment]
                continue
            if skip:
                parts.append(f"\x1b[{skip}C")
                skip = 0
            codes: list[str] = []
            if fg != last_fg:
                codes.append("39" if fg is None else f"38;2;{fg.r};{fg.g};{fg.b}")
                last_fg = fg
            if bg != last_bg:
                codes.append("49" if bg is None else f"48;2;{bg.r};{bg.g};{bg.b}")
                last_bg = bg
            if codes:
                parts.append("\x1b[" + ";".join(codes) + "m")
            parts.append(char)
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return "".join(lines)


def _size() -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=(80, 24))
    return size.columns, size.lines


def main() -> None:
    look = sys.argv[1] if len(sys.argv) > 1 else None
    run(look)


if __name__ == "__main__":
    main()
