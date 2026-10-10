"""Reusable instrument parts.

Lines, frames, plates, and readouts draw on the banner grid. A cell is good
at those. Dials, gauges, faders, and lamps are circles and smooth lengths, so
they are real pixels in :mod:`meowtext.pixels`, placed through the kitty
graphics protocol the way eventhorizon places the black hole.

The included reference pictures fall into six themes. Left-out pictures are
not part of these themes.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from meowtext.grid import Cell, Color, Grid
from meowtext.pixels import CELL_H, CELL_W, dial, fader, gauge, kitty_place, lamp, paste

GREEN = Color(40, 200, 90)
AMBER = Color(230, 180, 80)
CYAN = Color(40, 210, 220)
VIOLET = Color(160, 90, 255)
MAGENTA = Color(255, 90, 170)
PAPER = Color(16, 17, 20)

INKS = {
    "green": GREEN,
    "amber": AMBER,
    "cyan": CYAN,
    "violet": VIOLET,
    "magenta": MAGENTA,
}

# corners, top, side. One cell wide.
_FRAMES = {
    "single": "┌┐└┘─│",
    "double": "╔╗╚╝═║",
    "thick": "┏┓┗┛━┃",
    "round": "╭╮╰╯─│",
    "dashed": "┌┐└┘┄┆",
}

_SHADES = ("░", "▒", "▓", "█")


@dataclass(frozen=True, slots=True)
class Theme:
    """A family of pictures, and the parts that show up in it."""

    id: str
    name: str
    feeling: str
    elements: tuple[str, ...]
    sources: tuple[str, ...]


THEMES: tuple[Theme, ...] = (
    Theme(
        "phosphor",
        "Phosphor",
        "One ink on a black field. The light is the information.",
        ("text", "plate", "readout", "rule", "frame"),
        (
            "tui-inspo: the gene-code poster, the waveform tube, Echoes of the Extinct",
            "tui-inspo: the amber plot and the amber radial, still one ink",
            "aesthetic-inspo: the oxide rack, dashed construction lines",
        ),
    ),
    Theme(
        "instrument",
        "Instrument",
        "A panel. The word, the meter, and the label are one drawing.",
        ("frame", "brackets", "plate", "readout", "gauge", "dial", "fader", "ticks", "reticle"),
        (
            "tui-inspo: the satellite console, the flight arc",
            "moodboard-ecwatch: the ship layout and the named network map",
            "aesthetic-inspo: the Etak screen and the city on a plinth",
        ),
    ),
    Theme(
        "glyph",
        "Glyph",
        "A letter built like a building: dither, bevel, a repeating border.",
        ("band", "frame", "lamp", "plate"),
        (
            "demo scene: the Zetra alphabet",
            "moodboard-ecwatch: GOO 2, the divine machine",
            "pixel-space-inspo: Team17, Grace",
            "rexpaint-inspo: the mushroom-hunt title, the snowy ship",
            "icons: the shou symbol",
        ),
    ),
    Theme(
        "living",
        "Living structure",
        "A node, a tube, a repeat. The machine and the organism share a drawing.",
        ("reticle", "ticks", "rule", "readout"),
        (
            "aesthetic-inspo: the notebook of branching networks",
            "Biological Inspiration: crystals, molecules, penicillium",
            "blueprint: reaction-diffusion",
        ),
    ),
    Theme(
        "object",
        "Object",
        "A bezel, a key, a tube. The screen has weight.",
        ("frame", "dial", "fader", "plate"),
        (
            "Lab aesthetics: the Dragon 128, the nixie pendant",
            "Cassette Futurism: the keypad",
            "aesthetic-inspo: the CRT bezel",
            "tui-inspo: the computer room",
        ),
    ),
    Theme(
        "state",
        "State",
        "One shape, shown empty, then filling, then full.",
        ("lamp", "gauge", "fader"),
        (
            "moodboard-ecwatch: the three columns",
            "tui-inspo: the download bar beside the planet",
        ),
    ),
)


def shade(value: float) -> str:
    """Four steps from a dim block to a solid one."""

    index = round(_unit(value) * (len(_SHADES) - 1))
    return _SHADES[index]


def text(grid: Grid, x: int, y: int, message: str, ink: Color) -> None:
    """Write a single-width line. Characters past the string are left alone."""

    for index, char in enumerate(message):
        _put(grid, x + index, y, char, ink)


def rule(
    grid: Grid,
    x: int,
    y: int,
    length: int,
    ink: Color,
    *,
    vertical: bool = False,
    char: str | None = None,
) -> None:
    """A phosphor line. Horizontal by default."""

    mark = char if char else ("│" if vertical else "─")
    for step in range(max(0, length)):
        if vertical:
            _put(grid, x, y + step, mark, ink)
        else:
            _put(grid, x + step, y, mark, ink)


def frame(
    grid: Grid,
    x: int,
    y: int,
    width: int,
    height: int,
    ink: Color,
    *,
    style: str = "single",
) -> None:
    """A closed border. The inside is left as it was."""

    if width < 2 or height < 2:
        return
    nw, ne, sw, se, horizontal, vertical = _FRAMES.get(style, _FRAMES["single"])
    _put(grid, x, y, nw, ink)
    _put(grid, x + width - 1, y, ne, ink)
    _put(grid, x, y + height - 1, sw, ink)
    _put(grid, x + width - 1, y + height - 1, se, ink)
    for column in range(1, width - 1):
        _put(grid, x + column, y, horizontal, ink)
        _put(grid, x + column, y + height - 1, horizontal, ink)
    for row in range(1, height - 1):
        _put(grid, x, y + row, vertical, ink)
        _put(grid, x + width - 1, y + row, vertical, ink)


def brackets(
    grid: Grid,
    x: int,
    y: int,
    width: int,
    height: int,
    ink: Color,
    *,
    arm: int = 2,
) -> None:
    """Corner marks only, the way a HUD brackets a region."""

    if width < 2 or height < 2:
        return
    arm = max(1, min(arm, width // 2, height // 2))
    nw, ne, sw, se, horizontal, vertical = _FRAMES["single"]
    _put(grid, x, y, nw, ink)
    _put(grid, x + width - 1, y, ne, ink)
    _put(grid, x, y + height - 1, sw, ink)
    _put(grid, x + width - 1, y + height - 1, se, ink)
    for step in range(1, arm):
        _put(grid, x + step, y, horizontal, ink)
        _put(grid, x + width - 1 - step, y, horizontal, ink)
        _put(grid, x + step, y + height - 1, horizontal, ink)
        _put(grid, x + width - 1 - step, y + height - 1, horizontal, ink)
        if step < height:
            _put(grid, x, y + step, vertical, ink)
            _put(grid, x + width - 1, y + step, vertical, ink)
            _put(grid, x, y + height - 1 - step, vertical, ink)
            _put(grid, x + width - 1, y + height - 1 - step, vertical, ink)


def band(grid: Grid, x: int, y: int, width: int, height: int, char: str, ink: Color) -> None:
    """A border made by repeating one glyph, as on a poster frame."""

    if width < 1 or height < 1 or not char:
        return
    mark = char[0]
    for column in range(width):
        _put(grid, x + column, y, mark, ink)
        _put(grid, x + column, y + height - 1, mark, ink)
    for row in range(height):
        _put(grid, x, y + row, mark, ink)
        _put(grid, x + width - 1, y + row, mark, ink)


def plate(grid: Grid, x: int, y: int, width: int, label: str, ink: Color, *, paper: Color = PAPER) -> None:
    """A solid caption bar. The ink is the bar; the letters sit in the paper colour."""

    if width < 1:
        return
    shown = label[:width]
    pad = width - len(shown)
    left = pad // 2
    body = " " * left + shown + " " * (pad - left)
    for index, char in enumerate(body):
        grid.set(x + index, y, Cell(char or " ", paper, ink))


def readout(grid: Grid, x: int, y: int, width: int, label: str, value: str, ink: Color) -> None:
    """A name on the left and a value on the right, one row."""

    if width < 1:
        return
    name = label[:width]
    room = max(0, width - len(name) - 1)
    shown = value[:room]
    gap = max(1, width - len(name) - len(shown)) if shown else 0
    if not shown:
        text(grid, x, y, name[:width], ink)
        return
    text(grid, x, y, (name + " " * gap + shown)[:width], ink)


def ticks(grid: Grid, x: int, y: int, count: int, ink: Color, *, vertical: bool = False) -> None:
    """Scale marks along an edge."""

    mark = "┤" if vertical else "┬"
    for step in range(max(0, count)):
        if vertical:
            _put(grid, x, y + step, mark, ink)
        else:
            _put(grid, x + step, y, mark, ink)


def reticle(grid: Grid, x: int, y: int, size: int, ink: Color) -> None:
    """A bracketed cross, as on the scanning posters."""

    size = max(3, size)
    if size % 2 == 0:
        size += 1
    brackets(grid, x, y, size, size, ink, arm=2)
    for row in range(1, size - 1):
        _put(grid, x, y + row, "│", ink)
        _put(grid, x + size - 1, y + row, "│", ink)
    center = size // 2
    _put(grid, x + center, y + center, "+", ink)


def specimen(ink: Color = GREEN) -> tuple[Image.Image, int, int]:
    """The continuous parts, as one picture. Lines and frames stay on the cell grid."""

    columns, rows = 48, 10
    image = Image.new("RGBA", (columns * CELL_W, rows * CELL_H), (0, 0, 0, 0))
    paste(image, dial(0.35, ink), 0, 1)
    paste(image, fader(0.7, ink), 18, 1)
    paste(image, gauge(0.62, ink), 22, 3)
    paste(image, gauge(0.3, ink), 22, 6)
    for index, level in enumerate((0.05, 0.4, 0.7, 1)):
        paste(image, lamp(level, ink), 22 + index * 4, 8)
    return image, columns, rows


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _put(grid: Grid, x: int, y: int, char: str, ink: Color) -> None:
    if x < 0 or y < 0 or not char:
        return
    grid.set(x, y, Cell(char[0], ink, None))


if __name__ == "__main__":
    import sys

    picture, columns, rows = specimen()
    sys.stdout.write(kitty_place(picture, columns, rows))
    sys.stdout.write("\n")
