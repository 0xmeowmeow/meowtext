"""Decorations applied after a font has been rendered.

Order is gradient, then outline, then drop shadow. The outline hugs the
letters. The shadow is a copy of the outlined letters, shifted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from meowtext.grid import Cell, Color, Grid, is_empty, is_ink


PALETTES: dict[str, tuple[Color, ...]] = {
    "rainbow": (
        Color(255, 0, 64),
        Color(255, 140, 0),
        Color(255, 230, 0),
        Color(0, 210, 80),
        Color(0, 190, 255),
        Color(90, 80, 255),
        Color(200, 0, 180),
    ),
    "fire": (
        Color(40, 0, 0),
        Color(180, 20, 0),
        Color(255, 90, 0),
        Color(255, 190, 40),
        Color(255, 245, 200),
    ),
    "ice": (
        Color(4, 16, 48),
        Color(0, 90, 170),
        Color(80, 210, 255),
        Color(230, 250, 255),
    ),
    "metal": (
        Color(28, 28, 34),
        Color(90, 92, 104),
        Color(210, 212, 220),
        Color(255, 255, 255),
        Color(130, 132, 145),
    ),
    "toxic": (
        Color(0, 40, 0),
        Color(0, 170, 30),
        Color(170, 255, 0),
        Color(240, 255, 180),
    ),
    "sunset": (
        Color(28, 0, 48),
        Color(170, 20, 80),
        Color(255, 110, 40),
        Color(255, 200, 120),
    ),
    "mono": (
        Color(50, 50, 55),
        Color(245, 245, 245),
    ),
}

DEFAULT_OUTLINE = Color(90, 90, 110)
DEFAULT_OUTLINE_HEX = DEFAULT_OUTLINE.hex()
DEFAULT_SHADOW = Color(40, 40, 48)
DEFAULT_SHADOW_HEX = DEFAULT_SHADOW.hex()

# Named colours for the selectors. "ice" matches the ice preset's outline.
COLOURS: dict[str, Color] = {
    "slate": DEFAULT_OUTLINE,
    "ink": DEFAULT_SHADOW,
    "white": Color(245, 245, 245),
    "black": Color(0, 0, 0),
    "red": Color(220, 50, 50),
    "orange": Color(255, 140, 0),
    "yellow": Color(255, 220, 60),
    "green": Color(40, 200, 90),
    "cyan": Color(40, 210, 220),
    "blue": Color(70, 110, 255),
    "violet": Color(160, 90, 255),
    "pink": Color(255, 90, 170),
    "ice": Color(180, 230, 255),
}

SYMBOLS: tuple[tuple[str, str], ...] = (
    ("shade ░", "░"),
    ("medium ▒", "▒"),
    ("heavy ▓", "▓"),
    ("block █", "█"),
    ("dot ·", "·"),
    ("bullet •", "•"),
    ("star *", "*"),
    ("plus +", "+"),
    ("hash #", "#"),
    ("circle ○", "○"),
    ("disc ●", "●"),
    ("square □", "□"),
    ("slash ╱", "╱"),
    ("tilde ~", "~"),
)

OUTLINE_MODES: tuple[tuple[str, str], ...] = (
    ("Shade", "shade"),
    ("Thick", "thick"),
    ("Contour", "contour"),
    ("Heavy", "heavy"),
    ("Double", "double"),
    ("Blocks", "blocks"),
)

ANIMATIONS: tuple[tuple[str, str], ...] = (
    ("None", "none"),
    ("Hue cycle", "hue"),
    ("March", "march"),
    ("Pulse", "pulse"),
    ("Sparkle", "sparkle"),
    ("Scan", "scan"),
)

# Box-drawing sets for outlines that follow the letter shape.
# h/v are edges. se/sw/ne/nw are the four outer corners.
_CONTOURS: dict[str, dict[str, str]] = {
    "contour": {
        "h": "─", "v": "│",
        "se": "╭", "sw": "╮", "ne": "╰", "nw": "╯",
        "SE": "┌", "SW": "┐", "NE": "└", "NW": "┘",
        "fill": "┼",
    },
    "heavy": {
        "h": "━", "v": "┃",
        "se": "┏", "sw": "┓", "ne": "┗", "nw": "┛",
        "SE": "┏", "SW": "┓", "NE": "┗", "NW": "┛",
        "fill": "╋",
    },
    "double": {
        "h": "═", "v": "║",
        "se": "╔", "sw": "╗", "ne": "╚", "nw": "╝",
        "SE": "╔", "SW": "╗", "NE": "╚", "NW": "╝",
        "fill": "╬",
    },
}


def colour_name(colour: Color) -> str:
    for name, value in COLOURS.items():
        if value == colour:
            return name
    return "slate"


@dataclass(slots=True)
class BannerStyle:
    """How to decorate a rendered banner. ``None`` leaves that effect off."""

    gradient: str | None = None
    direction: str = "horizontal"
    outline: bool = False
    outline_char: str = "░"
    outline_color: Color = DEFAULT_OUTLINE
    outline_mode: str = "shade"
    outline_gradient: str | None = None
    shadow: bool = False
    shadow_dx: int = 1
    shadow_dy: int = 1
    shadow_color: Color = DEFAULT_SHADOW
    shadow_char: str | None = None
    hue: float = 0.0

    def clone(self) -> BannerStyle:
        return replace(self)


PRESETS: dict[str, BannerStyle] = {
    "plain": BannerStyle(),
    "rainbow": BannerStyle(gradient="rainbow"),
    "fire": BannerStyle(gradient="fire", shadow=True),
    "ice": BannerStyle(gradient="ice", outline=True, outline_color=Color(180, 230, 255)),
    "stamp": BannerStyle(outline=True, shadow=True, shadow_dx=2, shadow_dy=1),
    "pop": BannerStyle(
        gradient="sunset",
        outline=True,
        shadow=True,
        shadow_dx=2,
        shadow_dy=1,
    ),
}


def resolve_palette(name: str) -> tuple[Color, ...]:
    """A named palette, or comma-separated hex stops such as ``#f00,#00f``."""

    key = name.strip().lower()
    if key in PALETTES:
        return PALETTES[key]
    stops = [Color.from_hex(part) for part in name.split(",") if part.strip()]
    if len(stops) >= 2:
        return tuple(stops)
    raise ValueError(f"unknown palette {name!r}")


def apply_style(
    grid: Grid,
    style: BannerStyle,
    phase: float = 0.0,
    pulse: float = 1.0,
) -> Grid:
    result = grid
    if style.gradient:
        result = gradient(result, resolve_palette(style.gradient), style.direction, phase)
    if style.outline:
        stops = resolve_palette(style.outline_gradient) if style.outline_gradient else None
        result = outline(
            result,
            style.outline_char[:1] or "░",
            style.outline_color,
            mode=style.outline_mode,
            stops=stops,
            direction=style.direction,
            phase=phase,
            pulse=pulse,
        )
    if style.shadow:
        result = drop_shadow(
            result,
            style.shadow_dx,
            style.shadow_dy,
            style.shadow_color,
            style.shadow_char,
        )
    return result


def gradient(
    grid: Grid,
    stops: tuple[Color, ...],
    direction: str = "horizontal",
    phase: float = 0.0,
) -> Grid:
    """Recolour ink. Font colours on those cells are replaced."""

    if not stops or grid.height == 0:
        return grid.copy()
    result = grid.copy()
    width = result.width
    height = result.height
    for y, row in enumerate(result.rows):
        for x, cell in enumerate(row):
            if not is_ink(cell):
                continue
            if cell.fg_slot is not None or cell.bg_slot is not None:
                continue
            colour = _sample(stops, _position(x, y, width, height, direction, phase))
            painted = cell.clone()
            if cell.char in ("", " ") and cell.bg is not None:
                painted.bg = colour
            else:
                painted.fg = colour
            row[x] = painted
    return result


def outline(
    grid: Grid,
    char: str = "░",
    colour: Color = DEFAULT_OUTLINE,
    mode: str = "shade",
    stops: tuple[Color, ...] | None = None,
    direction: str = "horizontal",
    phase: float = 0.0,
    pulse: float = 1.0,
) -> Grid:
    """Paint a rim around the ink. The rim does not cover the letters.

    ``shade`` and ``thick`` repeat one symbol. ``contour``, ``heavy``,
    ``double`` and ``blocks`` pick a glyph from the way the letter sits
    against that cell, so corners turn and straight edges stay straight.
    """

    if grid.height == 0 or grid.width == 0:
        return grid.copy()
    source = grid.copy()
    source.normalize()
    width, height = source.width, source.height
    margin = 2 if mode == "thick" else 1
    ink = [[is_ink(cell) for cell in row] for row in source.rows]
    result = Grid.blank(width + margin * 2, height + margin * 2)

    def ink_at(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height and ink[y][x]

    for y in range(height):
        for x in range(width):
            if not ink[y][x]:
                continue
            for dy in range(-margin, margin + 1):
                for dx in range(-margin, margin + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if max(abs(dx), abs(dy)) > margin:
                        continue
                    nx, ny = x + dx, y + dy
                    if ink_at(nx, ny):
                        continue
                    dest_x, dest_y = nx + margin, ny + margin
                    if is_ink(result.get(dest_x, dest_y)):
                        continue
                    distance = max(abs(dx), abs(dy))
                    glyph = _outline_glyph(mode, char, nx, ny, ink_at)
                    tint = _outline_tint(
                        colour, stops, dest_x, dest_y,
                        width + margin * 2, height + margin * 2,
                        direction, phase, pulse, distance,
                    )
                    result.set(dest_x, dest_y, Cell(glyph, tint))
    for y, row in enumerate(source.rows):
        for x, cell in enumerate(row):
            if is_ink(cell):
                result.set(x + margin, y + margin, cell.clone())
    result.normalize()
    return result


def _outline_glyph(mode: str, char: str, x: int, y: int, ink_at) -> str:
    if mode in {"shade", "thick"}:
        return char or "░"
    north, south = ink_at(x, y - 1), ink_at(x, y + 1)
    west, east = ink_at(x - 1, y), ink_at(x + 1, y)
    if mode == "blocks":
        if north and not south and not west and not east:
            return "▀"
        if south and not north and not west and not east:
            return "▄"
        if west and not east and not north and not south:
            return "▌"
        if east and not west and not north and not south:
            return "▐"
        return "█"
    glyphs = _CONTOURS.get(mode, _CONTOURS["contour"])
    if north and west:
        return glyphs["NW"]
    if north and east:
        return glyphs["NE"]
    if south and west:
        return glyphs["SW"]
    if south and east:
        return glyphs["SE"]
    if north or south:
        return glyphs["h"]
    if west or east:
        return glyphs["v"]
    # Only a diagonal touches the letter: an outer corner.
    if ink_at(x + 1, y + 1):
        return glyphs["se"]
    if ink_at(x - 1, y + 1):
        return glyphs["sw"]
    if ink_at(x + 1, y - 1):
        return glyphs["ne"]
    if ink_at(x - 1, y - 1):
        return glyphs["nw"]
    return glyphs["fill"]


def _outline_tint(
    colour: Color,
    stops: tuple[Color, ...] | None,
    x: int,
    y: int,
    width: int,
    height: int,
    direction: str,
    phase: float,
    pulse: float,
    distance: int,
) -> Color:
    if stops:
        base = _sample(stops, _position(x, y, width, height, direction, phase))
    else:
        base = colour
    if distance > 1:
        base = Color(base.r // 2, base.g // 2, base.b // 2)
    if pulse != 1:
        base = Color(
            min(255, int(base.r * pulse)),
            min(255, int(base.g * pulse)),
            min(255, int(base.b * pulse)),
        )
    return base


def sparkle(grid: Grid, frame: int) -> Grid:
    """Brighten a shifting handful of ink cells."""

    out = grid.copy()
    for y, row in enumerate(out.rows):
        for x, cell in enumerate(row):
            if not is_ink(cell) or cell.fg is None:
                continue
            if (x * 17 + y * 31 + frame * 13) % 11:
                continue
            bright = cell.clone()
            bright.fg = Color(
                min(255, cell.fg.r + 140),
                min(255, cell.fg.g + 140),
                min(255, cell.fg.b + 140),
            )
            row[x] = bright
    return out


def scan(grid: Grid, frame: int) -> Grid:
    """A bright band travelling across the banner."""

    if grid.width == 0:
        return grid.copy()
    pos = frame % (grid.width + 6) - 3
    out = grid.copy()
    for y, row in enumerate(out.rows):
        for x, cell in enumerate(row):
            if not is_ink(cell) or cell.fg is None:
                continue
            distance = abs(x - pos)
            if distance > 2:
                continue
            gain = 1 + (2 - distance) * 0.45
            bright = cell.clone()
            bright.fg = Color(
                min(255, int(cell.fg.r * gain)),
                min(255, int(cell.fg.g * gain)),
                min(255, int(cell.fg.b * gain)),
            )
            row[x] = bright
    return out


def drop_shadow(
    grid: Grid,
    dx: int = 1,
    dy: int = 1,
    colour: Color = DEFAULT_SHADOW,
    char: str | None = None,
) -> Grid:
    """Copy ink by ``(dx, dy)`` in one flat colour, then draw the original on top."""

    if grid.height == 0 or (dx == 0 and dy == 0):
        return grid.copy()
    source = grid.copy()
    source.normalize()
    pad_left = max(0, -dx)
    pad_top = max(0, -dy)
    width = source.width + pad_left + max(0, dx)
    height = source.height + pad_top + max(0, dy)
    result = Grid.blank(width, height)
    for y, row in enumerate(source.rows):
        for x, cell in enumerate(row):
            if not is_ink(cell):
                continue
            shadow_char = char if char else (cell.char if cell.char not in ("", " ") else "█")
            sx, sy = x + dx + pad_left, y + dy + pad_top
            if not is_ink(result.get(sx, sy)):
                result.set(sx, sy, Cell(shadow_char[:1] or "█", colour))
    for y, row in enumerate(source.rows):
        for x, cell in enumerate(row):
            if is_ink(cell) or not is_empty(cell):
                result.set(x + pad_left, y + pad_top, cell.clone())
    result.normalize()
    return result


def _position(x: int, y: int, width: int, height: int, direction: str, phase: float = 0.0) -> float:
    horizontal = 0.0 if width <= 1 else x / (width - 1)
    vertical = 0.0 if height <= 1 else y / (height - 1)
    if direction == "vertical":
        base = vertical
    elif direction == "diagonal":
        base = (horizontal + vertical) / 2
    else:
        base = horizontal
    if phase == 0:
        return base
    return (base + phase) % 1.0


def _sample(stops: tuple[Color, ...], t: float) -> Color:
    t = min(1.0, max(0.0, t))
    if len(stops) == 1:
        return stops[0]
    scaled = t * (len(stops) - 1)
    index = min(int(scaled), len(stops) - 2)
    local = scaled - index
    left, right = stops[index], stops[index + 1]
    return Color(
        int(left.r + (right.r - left.r) * local),
        int(left.g + (right.g - left.g) * local),
        int(left.b + (right.b - left.b) * local),
    )
