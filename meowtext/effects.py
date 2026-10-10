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
)

TRACE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Around the outline", "outline"),
    ("Across the rows", "rows"),
    ("One letter, then the next", "letter"),
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
    outline_phase: float | None = None,
) -> Grid:
    result = grid
    if style.gradient:
        stops = style.stops if style.stops else resolve_palette(style.gradient)
        result = gradient(result, stops, style.direction, phase, bands=style.bands)
    if style.outline:
        if style.outline_gradient:
            stops = style.outline_stops if style.outline_stops else resolve_palette(style.outline_gradient)
        else:
            stops = None
        result = outline(
            result,
            style.outline_char[:1] or "░",
            style.outline_color,
            mode=style.outline_mode,
            stops=stops,
            direction=style.outline_direction,
            phase=phase if outline_phase is None else outline_phase,
            pulse=pulse,
            bands=style.outline_bands,
            sides=style.outline_sides,
            distance=style.outline_distance,
            place=style.outline_place,
            scope=style.outline_scope,
            shift_x=style.outline_dx,
            shift_y=style.outline_dy,
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
            bands, sides, distance, place, shift_x, shift_y,
        )
    return _outline_region(
        source, char, colour, mode, stops, direction, phase, pulse,
        bands, sides, distance, place, shift_x, shift_y,
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
        piece = _outline_region(
            crop, char, colour, mode, stops, direction, phase, pulse,
            bands, sides, distance, place, shift_x, shift_y,
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
                        direction, phase, pulse, step, mode == "thick", bands,
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


def trace(grid: Grid, animation: Animation, frame: int) -> Grid:
    """Reveal the banner along a path, or run a bright point along that path."""

    order = _trace_order(grid, animation.pattern)
    if not order:
        return grid.copy()
    clock = int(motion_clock(frame, animation))
    if animation.reveal == "runner":
        return _trace_runner(grid, order, clock)
    return _trace_draw(grid, order, clock)


def _trace_order(grid: Grid, pattern: str) -> list[tuple[int, int]]:
    ink = [
        (x, y)
        for y, row in enumerate(grid.rows)
        for x, cell in enumerate(row)
        if is_ink(cell)
    ]
    if pattern == "rows":
        return sorted(ink, key=lambda item: (item[1], item[0]))
    if pattern == "centre":
        cx = (grid.width - 1) / 2
        cy = (grid.height - 1) / 2
        return sorted(ink, key=lambda item: (abs(item[0] - cx) + abs(item[1] - cy), item[1], item[0]))
    groups = _ink_groups(grid)
    if pattern == "letter":
        ordered: list[tuple[int, int]] = []
        for group in groups:
            ordered.extend(sorted(group, key=lambda item: (item[1], item[0])))
        return ordered
    ordered = []
    for group in groups:
        edge, inner = _perimeter(group)
        ordered.extend(edge)
        ordered.extend(sorted(inner, key=lambda item: (item[1], item[0])))
    return ordered


def _ink_groups(grid: Grid) -> list[list[tuple[int, int]]]:
    """Letters split by a blank column, each letter's ink cells together."""

    height = grid.height
    groups: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for x in range(grid.width):
        column = [(x, y) for y in range(height) if is_ink(grid.get(x, y))]
        if column:
            current.extend(column)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
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


def _trace_draw(grid: Grid, order: list[tuple[int, int]], clock: int) -> Grid:
    shown = set(order[: max(0, clock + 1)])
    out = grid.copy()
    for y, row in enumerate(out.rows):
        for x, cell in enumerate(row):
            if is_ink(cell) and (x, y) not in shown:
                row[x] = Cell()
    return out


def _trace_runner(grid: Grid, order: list[tuple[int, int]], clock: int) -> Grid:
    hot: dict[tuple[int, int], int] = {}
    for age in range(4):
        hot[order[(clock - age) % len(order)]] = age
    out = grid.copy()
    for (x, y), age in hot.items():
        cell = out.get(x, y)
        if cell.fg is None:
            continue
        gain = 1.8 - age * 0.25
        bright = cell.clone()
        bright.fg = Color(
            min(255, int(cell.fg.r * gain)),
            min(255, int(cell.fg.g * gain)),
            min(255, int(cell.fg.b * gain)),
        )
        out.set(x, y, bright)
    return out
