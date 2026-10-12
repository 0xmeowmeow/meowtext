"""Decorations applied after a font has been rendered.

Order is gradient, then outline, then drop shadow. The outline hugs the
letters. The shadow is a copy of the outlined letters, shifted.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import math

from meowtext.grid import Cell, Color, Grid, is_empty, is_ink
from meowtext.palette import rotate_hue, lift_gradient


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

PALETTES.update({
    "aurora": tuple(Color.from_hex(c) for c in ('#49c99b', '#75e5e8', '#ae91ff', '#ecbaff')),
    "neon": tuple(Color.from_hex(c) for c in ('#c877ff', '#ff82ce', '#70e7ff')),
    "lagoon": tuple(Color.from_hex(c) for c in ('#4b9fe8', '#63dccd', '#c6f5bb')),
    "candy": tuple(Color.from_hex(c) for c in ('#ff98bc', '#ffd99b', '#b9a3ff', '#98e9ed')),
    "copper": tuple(Color.from_hex(c) for c in ('#bd825b', '#f1bd87', '#fff0c4', '#d99170')),
    "opal": tuple(Color.from_hex(c) for c in ('#acebe7', '#e6b9f6', '#fff4d6', '#a6c5ff')),
    "citrus": tuple(Color.from_hex(c) for c in ('#b4dc54', '#f7ed80', '#ffb85c')),
    "mint": tuple(Color.from_hex(c) for c in ('#5fcd9b', '#a1f2cc', '#edf9dc')),
})

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
    ("upper ▀", "▀"),
    ("lower ▄", "▄"),
    ("left ▌", "▌"),
    ("right ▐", "▐"),
    ("dot ·", "·"),
    ("bullet •", "•"),
    ("star *", "*"),
    ("plus +", "+"),
    ("hash #", "#"),
    ("circle ○", "○"),
    ("disc ●", "●"),
    ("square □", "□"),
    ("box ■", "■"),
    ("diamond ◆", "◆"),
    ("lozenge ◇", "◇"),
    ("triangle ▲", "▲"),
    ("heart ♥", "♥"),
    ("star ★", "★"),
    ("spark ✦", "✦"),
    ("slash ╱", "╱"),
    ("backslash ╲", "╲"),
    ("cross ✕", "✕"),
    ("tilde ~", "~"),
    ("line ─", "─"),
    ("bar │", "│"),
    ("double ═", "═"),
    ("heavy ━", "━"),
    ("corner ┌", "┌"),
    ("round ╭", "╭"),
    ("braille ⠁", "⠁"),
    ("braille ⣿", "⣿"),
    ("braille ⠿", "⠿"),
    ("shade ▁", "▁"),
    ("shade ▃", "▃"),
    ("shade ▅", "▅"),
    ("shade ▇", "▇"),
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
    ("Trace", "trace"),
    ("Shimmer", "shimmer"),
    ("Ripple", "ripple"),
    ("Breathe", "breathe"),
    ("Colour wave", "wave"),
)

TRACE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Around the outline", "outline"),
    ("Across the rows", "rows"),
    ("Each letter together", "letter"),
    ("Out from the centre", "centre"),
)

TRACE_REVEALS: tuple[tuple[str, str], ...] = (
    ("Draw on", "draw"),
    ("Runner", "runner"),
)

ANIM_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("Forward", "forward"),
    ("Backward", "backward"),
    ("Ping-pong", "pingpong"),
)

# Spatial directions. The "-back" forms run the same axis the other way,
# so an outline can be light where the letters are dark.
GRADIENT_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("Left to right", "horizontal"),
    ("Right to left", "horizontal-back"),
    ("Top to bottom", "vertical"),
    ("Bottom to top", "vertical-back"),
    ("Diagonal down", "diagonal"),
    ("Diagonal up", "diagonal-back"),
)
OUTLINE_DIRECTIONS: tuple[tuple[str, str], ...] = GRADIENT_DIRECTIONS + (
    ("Opposite the letters", "opposite"),
)

ANIM_LAYERS: tuple[tuple[str, str], ...] = (
    ("Everything", "all"),
    ("Letters", "letters"),
    ("Outline", "outline"),
    ("Colour roles", "roles"),
)

ANIM_SPEEDS: tuple[tuple[str, str], ...] = (
    ("Slow", "0.5"),
    ("Steady", "1"),
    ("Brisk", "2"),
    ("Fast", "3"),
)

ANIM_TRAVELS: tuple[tuple[str, str], ...] = (
    ("A little", "60"),
    ("A quarter", "90"),
    ("Halfway", "180"),
    ("The whole way", "360"),
)

OUTLINE_PLACES: tuple[tuple[str, str], ...] = (
    ("Outside and inside", "both"),
    ("Outside", "outside"),
    ("Inside the holes", "inside"),
)

OUTLINE_SCOPES: tuple[tuple[str, str], ...] = (
    ("Whole word", "word"),
    ("Each letter", "letter"),
)

OUTLINE_DISTANCES: tuple[tuple[str, str], ...] = (
    ("Auto", "0"),
    ("1 cell", "1"),
    ("2 cells", "2"),
    ("3 cells", "3"),
    ("4 cells", "4"),
    ("6 cells", "6"),
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
    stops: tuple[Color, ...] | None = None
    bands: bool = False
    outline: bool = False
    outline_char: str = "░"
    outline_color: Color = DEFAULT_OUTLINE
    outline_mode: str = "shade"
    outline_gradient: str | None = None
    outline_stops: tuple[Color, ...] | None = None
    outline_direction: str = "horizontal"
    outline_speed: float = 1.0
    outline_bands: bool = False
    outline_sides: str = "tblr"
    outline_distance: int = 0
    outline_place: str = "both"
    outline_scope: str = "word"
    outline_dx: int = 0
    outline_dy: int = 0
    shadow: bool = False
    shadow_dx: int = 1
    shadow_dy: int = 1
    shadow_color: Color = DEFAULT_SHADOW
    shadow_char: str | None = None
    hue: float = 0.0
    recolour_roles: bool = False
    readable_gradients: bool = True

    def clone(self) -> BannerStyle:
        return replace(self)


@dataclass(slots=True)
class Animation:
    """One preview motion. Save stores the frame on screen, plus these settings."""

    name: str = "none"
    speed: float = 1.0
    direction: str = "forward"
    travel: int = 360
    layers: str = "all"
    pattern: str = "outline"
    reveal: str = "draw"

    def clone(self) -> Animation:
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

# Complete starting points. Existing names and project recipes remain valid.
PRESETS.update({
    "cyan": BannerStyle(stops=(Color(101, 232, 237),) * 2),
    "amber": BannerStyle(stops=(Color(255, 189, 105),) * 2),
    "paper": BannerStyle(stops=(Color(240, 239, 230),) * 2),
    "orchid": BannerStyle(stops=(Color(211, 157, 255),) * 2),
    "acid": BannerStyle(stops=(Color(179, 239, 115),) * 2),
    "rose": BannerStyle(stops=(Color(255, 140, 163),) * 2),
    "deep-sea": BannerStyle(gradient="ice", direction="vertical"),
    "chrome": BannerStyle(gradient="metal", direction="vertical", shadow=True),
    "ember": BannerStyle(gradient="fire", direction="vertical-back"),
    "sunrise": BannerStyle(gradient="sunset", direction="vertical", shadow=True),
    "toxic": BannerStyle(gradient="toxic", shadow=True, shadow_color=Color(20, 60, 5)),
    "rainbow-bands": BannerStyle(gradient="rainbow", bands=True),
    "ice-rim": BannerStyle(gradient="ice", outline=True, outline_mode="contour", outline_color=Color(120, 230, 255)),
    "gold-rim": BannerStyle(stops=(Color(255, 216, 120),)*2, outline=True, outline_mode="double", outline_color=Color(150, 95, 25)),
    "violet-shadow": BannerStyle(stops=(Color(205, 162, 255),)*2, shadow=True, shadow_color=Color(100, 42, 150), shadow_dx=2),
    "cyan-shadow": BannerStyle(stops=(Color(130, 248, 250),)*2, shadow=True, shadow_color=Color(20, 100, 120), shadow_dx=2),
    "blacklight": BannerStyle(stops=(Color(65, 10, 120),Color(226, 124, 255)), outline=True, outline_color=Color(195, 255, 110)),
    "arcade": BannerStyle(gradient="rainbow", bands=True, shadow=True, shadow_color=Color(70, 30, 105), shadow_dx=2),
    "blueprint": BannerStyle(stops=(Color(90, 160, 230),Color(210, 244, 255)), outline=True, outline_mode="contour", outline_color=Color(30, 85, 130)),
    "silver-stamp": BannerStyle(gradient="metal", bands=True, outline=True, shadow=True),
    "sunset-rim": BannerStyle(gradient="sunset", outline=True, outline_gradient="ice", outline_direction="opposite"),
    "terminal-green": BannerStyle(stops=(Color(75, 230, 120),)*2),
})


PRESETS.update({
    "aurora": BannerStyle(gradient="aurora", direction="diagonal", outline=True, outline_mode="contour", outline_color=Color(121, 238, 202)),
    "synthwave": BannerStyle(gradient="neon", bands=True, outline=True, outline_mode="heavy", outline_color=Color(100, 72, 151), shadow=True, shadow_color=Color(48, 31, 80), shadow_dx=2),
    "lagoon": BannerStyle(gradient="lagoon", direction="vertical"),
    "candy": BannerStyle(gradient="candy", outline=True, outline_mode="double", outline_color=Color(245, 160, 206)),
    "copper": BannerStyle(gradient="copper", direction="vertical", bands=True, shadow=True, shadow_color=Color(88, 46, 33)),
    "opal": BannerStyle(gradient="opal", direction="diagonal", outline=True, outline_mode="contour", outline_color=Color(152, 175, 212)),
    "citrus": BannerStyle(gradient="citrus", direction="vertical-back", shadow=True, shadow_color=Color(52, 70, 22)),
    "mint-chip": BannerStyle(gradient="mint", direction="vertical", shadow=True, shadow_dx=2, shadow_color=Color(36, 66, 54)),
    "rose-gold": BannerStyle(stops=(Color(255, 151, 175), Color(255, 225, 165), Color(225, 164, 122)), outline=True, outline_mode="contour", outline_color=Color(240, 184, 137)),
    "prism": BannerStyle(gradient="rainbow", direction="diagonal", bands=True, outline=True, outline_mode="double", outline_color=Color(207, 225, 255)),
    "glacier": BannerStyle(gradient="ice", direction="vertical-back", outline=True, outline_mode="blocks", outline_color=Color(92, 157, 204)),
    "hot-pink": BannerStyle(stops=(Color(255, 97, 182),)*2, outline=True, outline_mode="heavy", outline_color=Color(144, 101, 220), shadow=True, shadow_color=Color(63, 26, 72), shadow_dx=2),
})

# Fixed periods keep preview, reverse/ping-pong and every export on one clock.
LIGHT_MOTIONS = {"shimmer": 48, "ripple": 48, "breathe": 64, "wave": 48}


def resolve_palette(name: str) -> tuple[Color, ...]:
    """A named palette, or comma-separated hex stops such as ``#f00,#00f``."""

    key = name.strip().lower()
    if key in PALETTES:
        return PALETTES[key]
    stops = [Color.from_hex(part) for part in name.split(",") if part.strip()]
    if len(stops) >= 2:
        return tuple(stops)
    raise ValueError(f"unknown palette {name!r}")


def opposite_direction(direction: str) -> str:
    """The same axis, running the other way."""

    paired = {
        "horizontal": "horizontal-back",
        "horizontal-back": "horizontal",
        "vertical": "vertical-back",
        "vertical-back": "vertical",
        "diagonal": "diagonal-back",
        "diagonal-back": "diagonal",
    }
    return paired.get(direction, "vertical-back")


def _turn(stops: tuple[Color, ...] | None, hue: float) -> tuple[Color, ...] | None:
    if not stops or not hue:
        return stops
    return tuple(rotate_hue(colour, hue) for colour in stops)


def apply_style(
    grid: Grid,
    style: BannerStyle,
    phase: float = 0.0,
    pulse: float = 1.0,
    outline_phase: float | None = None,
    letter_hue: float = 0.0,
    outline_hue: float = 0.0,
    light_motion: Animation | None = None,
    frame: float = 0,
) -> Grid:
    result = grid.copy()
    if result.letter_ink is None:
        result.letter_ink = tuple(tuple(group) for group in _ink_groups(result))
    if style.recolour_roles or (style.stops and len(set(style.stops)) == 1):
        result = result.copy()
        for row in result.rows:
            for cell in row:
                cell.fg_slot = None
    if style.gradient or style.stops:
        stops = _turn(style.stops if style.stops else resolve_palette(style.gradient), letter_hue)
        result = gradient(result, stops or (), style.direction, phase, bands=style.bands, readable=style.readable_gradients and len(set(stops or ())) > 1)
    if light_motion and light_motion.name in LIGHT_MOTIONS:
        result = colour_motion(result, light_motion, frame, style.readable_gradients)
    if style.outline:
        if style.outline_gradient:
            stops = style.outline_stops if style.outline_stops else resolve_palette(style.outline_gradient)
        else:
            stops = None
        direction = style.outline_direction
        if direction == "opposite":
            direction = opposite_direction(style.direction)
        result = outline(
            result,
            style.outline_char[:1] or "░",
            rotate_hue(style.outline_color, outline_hue) if outline_hue else style.outline_color,
            mode=style.outline_mode,
            stops=_turn(stops, outline_hue),
            direction=direction,
            phase=phase if outline_phase is None else outline_phase,
            pulse=pulse,
            bands=style.outline_bands,
            sides=style.outline_sides,
            distance=style.outline_distance,
            place=style.outline_place,
            scope=style.outline_scope,
            shift_x=style.outline_dx,
            shift_y=style.outline_dy,
            readable=style.readable_gradients,
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
    bands: bool = False,
    readable: bool = False,
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
            colour = _sample(stops, _position(x, y, width, height, direction, phase), bands)
            if readable:
                colour = lift_gradient(colour)
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
    *,
    bands: bool = False,
    sides: str = "tblr",
    distance: int = 0,
    place: str = "both",
    scope: str = "word",
    shift_x: int = 0,
    shift_y: int = 0,
    readable: bool = False,
) -> Grid:
    """Paint a rim around the ink. The rim does not cover the letters.

    ``shade`` and ``thick`` repeat one symbol. ``contour``, ``heavy``,
    ``double`` and ``blocks`` pick a glyph from the way the letter sits
    against that cell, so corners turn and straight edges stay straight.
    ``sides`` is a mix of ``t``, ``b``, ``l`` and ``r``. ``place`` is
    ``outside``, ``inside``, or ``both``. ``scope`` ``letter`` rims each
    letter; ``word`` rims the whole banner as one shape.
    """

    if grid.height == 0 or grid.width == 0:
        return grid.copy()
    source = grid.copy()
    source.normalize()
    if scope == "letter":
        return _outline_letters(
            source, char, colour, mode, stops, direction, phase, pulse,
            bands, sides, distance, place, shift_x, shift_y, readable,
        )
    return _outline_region(
        source, char, colour, mode, stops, direction, phase, pulse,
        bands, sides, distance, place, shift_x, shift_y, readable,
    )


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


def _hstack(pieces: list[Grid]) -> Grid:
    height = max((piece.height for piece in pieces), default=0)
    rows: list[list[Cell]] = [[] for _ in range(height)]
    for piece in pieces:
        piece.normalize()
        for y in range(height):
            if y < piece.height:
                rows[y].extend(cell.clone() for cell in piece.rows[y])
            else:
                rows[y].extend(Cell() for _ in range(piece.width))
    grid = Grid(rows)
    x = 0
    letters = []
    for piece in pieces:
        letters.extend(tuple((px + x, py) for px, py in group) for group in _letters(piece))
        x += piece.width
    grid.letter_ink = tuple(letters)
    grid.normalize()
    return grid


def _vstack(pieces: list[Grid]) -> Grid:
    width = max((piece.width for piece in pieces), default=0)
    rows: list[list[Cell]] = []
    for piece in pieces:
        for row in piece.rows:
            padded = [cell.clone() for cell in row]
            if len(padded) < width:
                padded.extend(Cell() for _ in range(width - len(padded)))
            rows.append(padded[:width] if width else [])
    grid = Grid(rows)
    y = 0
    letters = []
    for piece in pieces:
        letters.extend(tuple((px, py + y) for px, py in group) for group in _letters(piece))
        y += piece.height
    grid.letter_ink = tuple(letters)
    grid.normalize()
    return grid


def _margin(mode: str, distance: int) -> int:
    if distance:
        return max(1, min(8, distance))
    return 2 if mode == "thick" else 1


def _outline_letters(
    source: Grid,
    char: str,
    colour: Color,
    mode: str,
    stops: tuple[Color, ...] | None,
    direction: str,
    phase: float,
    pulse: float,
    bands: bool,
    sides: str,
    distance: int,
    place: str,
    shift_x: int,
    shift_y: int,
    readable: bool,
) -> Grid:
    """Rim each recorded letter, or each run of ink separated by a gap."""

    regions = _letter_regions(source)
    if not regions:
        return source.copy()
    lines: dict[int, list[Grid]] = {}
    order: list[int] = []
    for x0, y0, x1, y1 in regions:
        crop = Grid(
            [[source.get(x, y).clone() for x in range(x0, x1)] for y in range(y0, y1)]
        )
        crop.normalize()
        crop.letter_ink = tuple(
            clipped for group in _letters(source)
            if (clipped := tuple((x - x0, y - y0) for x, y in group
                                 if x0 <= x < x1 and y0 <= y < y1))
        )
        piece = _outline_region(
            crop, char, colour, mode, stops, direction, phase, pulse,
            bands, sides, distance, place, shift_x, shift_y, readable,
        )
        if y0 not in lines:
            order.append(y0)
            lines[y0] = []
        lines[y0].append(piece)
    stitched = [_hstack(lines[y]) for y in order]
    if len(stitched) == 1:
        return stitched[0]
    return _vstack(stitched)


def _letter_regions(source: Grid) -> list[tuple[int, int, int, int]]:
    """Boxes around each letter. Spans win; otherwise a blank column splits a word."""

    if source.spans:
        regions = []
        for _char, x, y, w, h in source.spans:
            if w > 0 and h > 0:
                regions.append((x, y, x + w, y + h))
        if regions:
            return regions
    height = source.height
    width = source.width
    ink_col = [
        any(is_ink(source.get(x, y)) for y in range(height))
        for x in range(width)
    ]
    regions = []
    start: int | None = None
    for x, on in enumerate(ink_col + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            regions.append((start, 0, x, height))
            start = None
    return regions


def _outline_region(
    source: Grid,
    char: str,
    colour: Color,
    mode: str,
    stops: tuple[Color, ...] | None,
    direction: str,
    phase: float,
    pulse: float,
    bands: bool,
    sides: str,
    distance: int,
    place: str,
    shift_x: int,
    shift_y: int,
    readable: bool,
) -> Grid:
    width, height = source.width, source.height
    if width == 0 or height == 0:
        return source.copy()
    margin = _margin(mode, distance)
    ink = [[is_ink(cell) for cell in row] for row in source.rows]
    outside = _outside_cells(ink)
    shaped = mode not in {"shade", "thick"}
    pad_left = margin + max(0, -shift_x)
    pad_top = margin + max(0, -shift_y)
    pad_right = margin + max(0, shift_x)
    pad_bottom = margin + max(0, shift_y)
    canvas_w = width + pad_left + pad_right
    canvas_h = height + pad_top + pad_bottom
    result = Grid.blank(canvas_w, canvas_h)
    _move_letters(source, result, pad_left, pad_top)

    def ink_at(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height and ink[y][x]

    def solid_at(x: int, y: int) -> bool:
        reach = margin - 1
        for sy in range(y - reach, y + reach + 1):
            for sx in range(x - reach, x + reach + 1):
                if max(abs(sx - x), abs(sy - y)) <= reach and ink_at(sx, sy):
                    return True
        return False

    neighbor_at = solid_at if shaped else ink_at
    for y in range(height):
        for x in range(width):
            if not ink[y][x]:
                continue
            for dy in range(-margin, margin + 1):
                for dx in range(-margin, margin + 1):
                    step = max(abs(dx), abs(dy))
                    if step == 0 or step > margin:
                        continue
                    if shaped and step != margin:
                        continue
                    nx, ny = x + dx, y + dy
                    if ink_at(nx, ny):
                        continue
                    if not _rim_kept(nx, ny, dx, dy, ink, outside, place, sides):
                        continue
                    dest_x = nx + pad_left + shift_x
                    dest_y = ny + pad_top + shift_y
                    if is_ink(result.get(dest_x, dest_y)):
                        continue
                    glyph = _outline_glyph(mode, char, nx, ny, neighbor_at)
                    tint = _outline_tint(
                        colour, stops, dest_x, dest_y, canvas_w, canvas_h,
                        direction, phase, pulse, step, mode == "thick", bands, readable,
                    )
                    result.set(dest_x, dest_y, Cell(glyph, tint))
    for y, row in enumerate(source.rows):
        for x, cell in enumerate(row):
            if is_ink(cell):
                result.set(x + pad_left, y + pad_top, cell.clone())
    result.normalize()
    return result


def _rim_kept(
    x: int,
    y: int,
    dx: int,
    dy: int,
    ink: list[list[bool]],
    outside: list[list[bool]],
    place: str,
    sides: str,
) -> bool:
    if place in {"outside", "inside"}:
        height = len(ink)
        width = len(ink[0]) if height else 0
        beyond = x < 0 or y < 0 or y >= height or x >= width
        is_outside = beyond or outside[y][x]
        if place == "outside" and not is_outside:
            return False
        if place == "inside" and is_outside:
            return False
    if not sides:
        return False
    wanted = set(sides)
    if wanted >= set("tblr"):
        return True
    return _on_side(dx, dy, wanted)


def _on_side(dx: int, dy: int, sides: set[str]) -> bool:
    """``dx, dy`` points from the letter out to the rim cell."""

    if dx < 0 and abs(dx) >= abs(dy) and "l" in sides:
        return True
    if dx > 0 and abs(dx) >= abs(dy) and "r" in sides:
        return True
    if dy < 0 and abs(dy) >= abs(dx) and "t" in sides:
        return True
    if dy > 0 and abs(dy) >= abs(dx) and "b" in sides:
        return True
    return False


def _outside_cells(ink: list[list[bool]]) -> list[list[bool]]:
    """Empty cells a flood from the border can reach. Holes stay False."""

    height = len(ink)
    width = len(ink[0]) if height else 0
    reached = [[False] * width for _ in range(height)]
    stack: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if y in {0, height - 1} or x in {0, width - 1}:
                if not ink[y][x]:
                    stack.append((x, y))
    while stack:
        x, y = stack.pop()
        if reached[y][x] or ink[y][x]:
            continue
        reached[y][x] = True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and not reached[ny][nx] and not ink[ny][nx]:
                stack.append((nx, ny))
    return reached


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
    darken: bool,
    bands: bool,
    readable: bool,
) -> Color:
    if stops:
        base = _sample(stops, _position(x, y, width, height, direction, phase), bands)
    else:
        base = colour
    if darken and distance > 1:
        base = Color(base.r // 2, base.g // 2, base.b // 2)
    if pulse != 1:
        base = Color(
            min(255, int(base.r * pulse)),
            min(255, int(base.g * pulse)),
            min(255, int(base.b * pulse)),
        )
    return lift_gradient(base) if readable and stops and len(set(stops)) > 1 else base


def colour_motion(grid: Grid, animation: Animation, frame: float, readable=True) -> Grid:
    """Move light across the letters while keeping their geometry and base ink.

    These motions run before outlines and shadows. Highlights add light rather
    than blanking or dimming the lettering; wave cycles colour in space.
    """
    out = grid.copy()
    phase = motion_clock(frame, animation) / LIGHT_MOTIONS[animation.name]
    for y, row in enumerate(out.rows):
        for x, cell in enumerate(row):
            if not is_ink(cell):
                continue
            nx, ny = x / max(1, grid.width-1), y / max(1, grid.height-1)
            background_ink = cell.char in ("", " ") and cell.bg is not None
            base = cell.bg if background_ink else cell.fg or Color(230,230,230)
            if animation.name == "wave":
                tint = rotate_hue(base, 100*math.sin(math.tau*(nx*.65+ny*.25-phase)))
                if readable:
                    tint = lift_gradient(tint)
            else:
                if animation.name == "breathe":
                    amount = .42*(.5-.5*math.cos(math.tau*phase))
                else:
                    position = nx*.75+ny*.25 if animation.name == "shimmer" else math.hypot(nx-.5,ny-.5)*1.6
                    amount = .72*max(0,math.cos(math.tau*(position-phase)))**8
                tint = Color(*(round(c+(255-c)*amount) for c in (base.r,base.g,base.b)))
            if background_ink:
                cell.bg = tint
            else:
                cell.fg = tint
    return out


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
    _move_letters(source, result, pad_left, pad_top)
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
    reverse = direction.endswith("-back")
    name = direction[: -len("-back")] if reverse else direction
    if name == "vertical":
        base = vertical
    elif name == "diagonal":
        base = (horizontal + vertical) / 2
    else:
        base = horizontal
    if reverse:
        base = 1.0 - base
    if phase == 0:
        return base
    return (base + phase) % 1.0


def _sample(stops: tuple[Color, ...], t: float, bands: bool = False) -> Color:
    t = min(1.0, max(0.0, t))
    if len(stops) == 1:
        return stops[0]
    if bands:
        if t >= 1:
            return stops[-1]
        return stops[min(len(stops) - 1, int(t * len(stops)))]
    scaled = t * (len(stops) - 1)
    index = min(int(scaled), len(stops) - 2)
    local = scaled - index
    left, right = stops[index], stops[index + 1]
    return Color(
        int(left.r + (right.r - left.r) * local),
        int(left.g + (right.g - left.g) * local),
        int(left.b + (right.b - left.b) * local),
    )


def motion_clock(frame: int, animation: Animation) -> float:
    """Frames after speed and direction. Ping-pong walks out and back."""

    speed = animation.speed if animation.speed > 0 else 1.0
    step = frame * speed
    if animation.direction == "backward":
        return -step
    if animation.direction == "pingpong":
        span = 24.0
        pos = step % (span * 2)
        return pos if pos < span else span * 2 - pos
    return step


def animation_phase(clock: float, travel: int) -> tuple[float, float]:
    """A gradient phase in 0..1, and a hue offset in degrees, both limited by ``travel``."""

    travel = max(1, min(360, int(travel)))
    span = travel / 360
    phase = (clock % 24) / 24
    if phase < 0:
        phase += 1
    phase *= span
    hue = (clock * 12) % travel
    if hue < 0:
        hue += travel
    return phase, hue


def _letters(grid: Grid) -> tuple[tuple[tuple[int, int], ...], ...]:
    if grid.letter_ink is not None:
        return grid.letter_ink
    return tuple(tuple(group) for group in _ink_groups(grid))


def _move_letters(source: Grid, target: Grid, dx: int, dy: int) -> None:
    target.letter_ink = tuple(tuple((x + dx, y + dy) for x, y in group)
                              for group in _letters(source))
    target.spans = tuple((char, x + dx, y + dy, w, h)
                         for char, x, y, w, h in source.spans)


@dataclass(frozen=True)
class TracePlan:
    paths: tuple[tuple[tuple[int, int], ...], ...]
    steps: int

    def turnaround(self, speed: float) -> int:
        # A whole preview tick at the endpoint, even when speed skips cells.
        return max(1, math.ceil((self.steps - 1) / speed))


def trace_plan(grid: Grid, pattern: str = "outline") -> TracePlan:
    """One path per letter, plus enough decoration seeds to keep pace.

    Original ink is recorded before borders and shadows join neighbouring
    letters. A long background is split into balanced paths, each no longer
    than the largest letter. All paths start and finish on the same ticks.
    """
    ink = frozenset((x, y) for y, row in enumerate(grid.rows)
                    for x, cell in enumerate(row) if is_ink(cell))
    return _trace_plan(_letters(grid), ink, pattern)


@lru_cache(maxsize=64)
def _trace_plan(letters, ink, pattern) -> TracePlan:
    used = set()
    paths = []
    for group in letters:
        cells = set(group) & ink - used
        if cells:
            paths.append(_trace_path(cells, pattern))
            used.update(cells)
    steps = max((len(path) for path in paths), default=1)
    background = _trace_path(ink - used, pattern)
    if background:
        seeds = math.ceil(len(background) / steps)
        paths.extend(background[i * len(background) // seeds:
                                (i + 1) * len(background) // seeds]
                     for i in range(seeds))
    return TracePlan(tuple(paths), steps)


def trace(grid: Grid, animation: Animation, frame: float) -> Grid:
    """Trace all letters and decoration in parallel on a common clock."""
    plan = trace_plan(grid, animation.pattern)
    if not plan.paths:
        return grid.copy()
    speed = animation.speed if animation.speed > 0 else 1.0
    clock = frame * speed
    if animation.direction == "pingpong":
        turn = plan.turnaround(speed)
        position = frame % (2 * turn)
        clock = min(plan.steps - 1, min(position, 2 * turn - position) * speed)
    if animation.reveal == "runner":
        if animation.direction == "backward":
            clock = -clock
        return _trace_runner(grid, plan, clock)
    paths = plan.paths
    if animation.direction == "backward":
        paths = tuple(tuple(reversed(path)) for path in paths)
    progress = min(1.0, max(0.0, clock / max(1, plan.steps - 1)))
    shown = set()
    for path in paths:
        count = 1 + math.floor(progress * (len(path) - 1) + 1e-9)
        shown.update(path[:count])
    out = grid.copy()
    for y, row in enumerate(out.rows):
        for x, cell in enumerate(row):
            if is_ink(cell) and (x, y) not in shown:
                row[x] = Cell()
    return out


def _trace_path(cells, pattern: str) -> tuple[tuple[int, int], ...]:
    if not cells:
        return ()
    ordered = sorted(cells, key=lambda item: (item[1], item[0]))
    if pattern == "centre":
        cx = (min(x for x, y in cells) + max(x for x, y in cells)) / 2
        cy = (min(y for x, y in cells) + max(y for x, y in cells)) / 2
        return tuple(sorted(ordered, key=lambda item: abs(item[0] - cx) + abs(item[1] - cy)))
    if pattern in {"rows", "letter"}:
        return tuple(ordered)
    edge, inner = _perimeter(ordered)
    return tuple(edge + inner)


def _ink_groups(grid: Grid) -> list[list[tuple[int, int]]]:
    """Recorded glyphs, with blank row/column runs as an imported-art fallback."""
    if grid.spans:
        return [[(x, y) for y in range(max(0, sy), min(grid.height, sy + h))
                 for x in range(max(0, sx), min(grid.width, sx + w))
                 if is_ink(grid.get(x, y))]
                for char, sx, sy, w, h in grid.spans]
    groups = []
    # Split lines first so aligned letters on different lines start together.
    top = None
    for bottom in range(grid.height + 1):
        on = bottom < grid.height and any(is_ink(c) for c in grid.rows[bottom])
        if on and top is None:
            top = bottom
        elif not on and top is not None:
            current = []
            for x in range(grid.width + 1):
                column = [(x, y) for y in range(top, bottom) if is_ink(grid.get(x, y))]
                if column:
                    current.extend(column)
                elif current:
                    groups.append(current)
                    current = []
            top = None
    return groups


def _perimeter(cells: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Walk the outer cells, then list the cells those surround."""

    present = set(cells)
    if not present:
        return [], []
    edge: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for x, y in cells:
        if any((x + dx, y + dy) not in present for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            edge.append((x, y))
            seen.add((x, y))
    edge.sort(key=lambda item: (item[1], item[0]))
    start = edge[0]
    walked = [start]
    walked_set = {start}
    current = start
    # Clockwise-ish: prefer the next edge cell that continues the walk.
    for _ in range(len(edge)):
        x, y = current
        nxt = None
        for dx, dy in ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)):
            candidate = (x + dx, y + dy)
            if candidate in seen and candidate not in walked_set:
                nxt = candidate
                break
        if nxt is None:
            break
        walked.append(nxt)
        walked_set.add(nxt)
        current = nxt
    leftover = [cell for cell in edge if cell not in walked_set]
    inner = [cell for cell in cells if cell not in seen]
    return walked + leftover, inner


def _trace_runner(grid: Grid, plan: TracePlan, clock: float) -> Grid:
    hot: dict[tuple[int, int], int] = {}
    for path in plan.paths:
        head = math.floor(clock * len(path) / plan.steps + 1e-9)
        for age in range(min(4, len(path))):
            point = path[(head - age) % len(path)]
            hot[point] = min(hot.get(point, age), age)
    out = grid.copy()
    for (x, y), age in hot.items():
        cell = out.get(x, y)
        colour = cell.bg if cell.char in ("", " ") else cell.fg
        if colour is None:
            continue
        gain = 1.8 - age * 0.25
        bright = cell.clone()
        tint = Color(*(min(255, int(c * gain)) for c in (colour.r, colour.g, colour.b)))
        if cell.char in ("", " "):
            bright.bg = tint
        else:
            bright.fg = tint
        out.set(x, y, bright)
    return out
