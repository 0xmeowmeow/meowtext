"""TheDraw font files (``.tdf``).

The layout follows Roy/SAC's notes on the format TheDraw wrote:

* 20-byte magic, then the 4-byte marker ``55 AA 00 FF``
* at byte 24: name length, 12-byte name, 4 unused, type, spacing,
  block size, then 94 little-endian offsets for ``!`` through ``~``
* character data starts at byte 233
* the next font in the file, if any, begins with another marker

Font types: 0 outline, 1 block, 2 colour. Colour glyphs store a DOS
attribute after every character. Outline glyphs store letters that
TheDraw maps to box drawing. ``@`` and ``O`` are spaces. A row ending
in ``&`` is a descender and is not part of the line height.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meowtext.ansi import cp437
from meowtext.errors import RenderError
from meowtext.grid import VGA, Cell, Color, Grid

MAGIC = b"\x13TheDraw FONTS file\x1a"
MARKER = b"\x55\xaa\x00\xff"
CHARSET = "".join(chr(code) for code in range(33, 127))
TYPE_OUTLINE = 0
TYPE_BLOCK = 1
TYPE_COLOR = 2
TYPE_NAMES = {TYPE_OUTLINE: "outline", TYPE_BLOCK: "block", TYPE_COLOR: "color"}

# TheDraw's standard outline letters. See Roy/SAC, "TheDraw Fonts File".
OUTLINE_CHARS = {
    "A": "═",
    "B": "─",
    "C": "│",
    "D": "║",
    "E": "╒",
    "F": "╗",
    "G": "╓",
    "H": "┐",
    "I": "╚",
    "J": "╛",
    "K": "└",
    "L": "╜",
    "M": "╡",
    "N": "╟",
    "O": " ",
    "@": " ",
}

_MAX_FONTS = 40
_MAX_GLYPH_WIDTH = 80
_MAX_GLYPH_ROWS = 64


@dataclass(slots=True)
class Glyph:
    width: int
    body: list[list[Cell]]
    desc: list[list[Cell]] = field(default_factory=list)


@dataclass(slots=True)
class TdfFont:
    name: str
    kind: str
    font_type: int
    spacing: int
    glyphs: dict[str, Glyph]
    source: str = ""
    index: int = 0

    @property
    def line_height(self) -> int:
        if not self.glyphs:
            return 1
        return max(len(glyph.body) + len(glyph.desc) for glyph in self.glyphs.values()) or 1


@dataclass(slots=True)
class TdfHeader:
    name: str
    kind: str
    index: int


def font_dirs() -> list[Path]:
    import os

    found: list[Path] = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        found.append(Path(xdg) / "tdfgo" / "fonts")
    found.append(Path.home() / ".config" / "tdfgo" / "fonts")
    found.append(Path("/usr/local/share/tdfgo/fonts"))
    found.append(Path("/usr/share/tdfgo/fonts"))
    found.append(Path.cwd() / "fonts")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        resolved = path.expanduser()
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def iter_font_files() -> list[Path]:
    files: list[Path] = []
    for directory in font_dirs():
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() == ".tdf":
                files.append(path)
    return files


def peek_file(path: Path) -> list[TdfHeader]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    return [TdfHeader(name, kind, index) for name, kind, index in _walk_headers(data)]


def load_file(path: Path) -> list[TdfFont]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RenderError(f"could not read {path}") from exc
    fonts = parse_tdf(data, source=str(path))
    if not fonts:
        raise RenderError(f"{path.name} has no TheDraw fonts")
    return fonts


def parse_tdf(data: bytes, source: str = "") -> list[TdfFont]:
    fonts: list[TdfFont] = []
    for pos, block, data_start in _walk(data):
        name = _read_name(data, pos)
        font_type = data[pos + 17]
        spacing = data[pos + 18]
        offsets = _read_offsets(data, pos + 21)
        blob = data[data_start : data_start + block]
        glyphs = _read_glyphs(blob, offsets, font_type)
        fonts.append(
            TdfFont(
                name=name or Path(source).stem or "untitled",
                kind=TYPE_NAMES.get(font_type, "unknown"),
                font_type=font_type,
                spacing=spacing,
                glyphs=glyphs,
                source=source,
                index=len(fonts),
            )
        )
        if len(fonts) >= _MAX_FONTS:
            break
    return fonts


def render_font(font: TdfFont, text: str) -> tuple[Grid, tuple[str, ...], bool]:
    """Render ``text``. Returns the grid, missing characters, and whether case was folded."""

    lines = text.split("\n")
    grids = [_render_line(font, line) for line in lines]
    missing: list[str] = []
    folded = False
    rendered: list[Grid] = []
    for grid, line_missing, line_folded in grids:
        rendered.append(grid)
        for char in line_missing:
            if char not in missing:
                missing.append(char)
        folded = folded or line_folded
    return _vstack(rendered, font.line_height), tuple(missing), folded


def _render_line(font: TdfFont, line: str) -> tuple[Grid, list[str], bool]:
    if line == "":
        return Grid.blank(0, font.line_height), [], False
    space_width = _space_width(font)
    glyphs: list[Glyph] = []
    missing: list[str] = []
    folded = False
    for char in line:
        glyph, did_fold, absent = _glyph_for(font, char, space_width)
        folded = folded or did_fold
        if absent and char not in missing:
            missing.append(char)
        glyphs.append(glyph)
    body_h = max((len(glyph.body) for glyph in glyphs), default=1)
    desc_h = max((len(glyph.desc) for glyph in glyphs), default=0)
    spacing = font.spacing
    width = sum(glyph.width for glyph in glyphs) + spacing * max(len(glyphs) - 1, 0)
    grid = Grid.blank(width, body_h + desc_h)
    x = 0
    for index, glyph in enumerate(glyphs):
        # Shorter letters sit on the same baseline as the tallest body.
        _blit(grid, glyph.body, x, body_h - len(glyph.body))
        _blit(grid, glyph.desc, x, body_h)
        x += glyph.width
        if index != len(glyphs) - 1:
            x += spacing
    return grid, missing, folded


def _glyph_for(font: TdfFont, char: str, space_width: int) -> tuple[Glyph, bool, bool]:
    if char == " ":
        return Glyph(space_width, []), False, False
    found = font.glyphs.get(char)
    if found is not None:
        return found, False, False
    swapped = char.swapcase()
    if swapped != char and swapped in font.glyphs:
        return font.glyphs[swapped], True, False
    return _missing_glyph(max(font.line_height, 1)), False, True


def _missing_glyph(height: int) -> Glyph:
    rows = [[Cell() for _ in range(3)] for _ in range(height)]
    mid = len(rows) // 2
    rows[mid] = [Cell("?"), Cell("?"), Cell("?")]
    return Glyph(3, rows, [])


def _space_width(font: TdfFont) -> int:
    for sample in ("n", "N", "o", "O", "x", "X"):
        glyph = font.glyphs.get(sample)
        if glyph is not None and glyph.width:
            return glyph.width
    widths = sorted(glyph.width for glyph in font.glyphs.values() if glyph.width)
    if not widths:
        return max(font.spacing, 2)
    return widths[len(widths) // 2]


def _blit(grid: Grid, rows: list[list[Cell]], origin_x: int, origin_y: int) -> None:
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell.char in ("", " ") and cell.fg is None and cell.bg is None:
                continue
            grid.set(origin_x + x, origin_y + y, cell.clone())


def _vstack(grids: list[Grid], empty_height: int) -> Grid:
    if not grids:
        return Grid()
    width = max((grid.width for grid in grids), default=0)
    rows: list[list[Cell]] = []
    for grid in grids:
        block = grid.rows or Grid.blank(width, empty_height).rows
        for row in block:
            padded = list(row)
            if len(padded) < width:
                padded.extend(Cell() for _ in range(width - len(padded)))
            rows.append(padded[:width] if width else [])
    return Grid(rows)


def _walk_headers(data: bytes) -> list[tuple[str, str, int]]:
    headers: list[tuple[str, str, int]] = []
    for pos, _block, _start in _walk(data):
        font_type = data[pos + 17]
        name = _read_name(data, pos) or f"font {len(headers)}"
        headers.append((name, TYPE_NAMES.get(font_type, "unknown"), len(headers)))
        if len(headers) >= _MAX_FONTS:
            break
    return headers


def _walk(data: bytes) -> list[tuple[int, int, int]]:
    """Return ``(name_pos, block_size, data_start)`` for each font."""

    if len(data) < 233 or not data.startswith(MAGIC):
        return []
    found: list[tuple[int, int, int]] = []
    pos = 24
    while len(found) < _MAX_FONTS and _looks_like_font(data, pos):
        block = int.from_bytes(data[pos + 19 : pos + 21], "little")
        data_start = pos + 209
        if block <= 0 or data_start > len(data):
            break
        block = min(block, len(data) - data_start)
        found.append((pos, block, data_start))
        nxt = _next_font(data, data_start, block)
        if nxt is None or nxt <= pos:
            break
        pos = nxt
    return found


def _next_font(data: bytes, data_start: int, block: int) -> int | None:
    base = data_start + block
    window = data[base : base + 8]
    marker_at = window.find(MARKER)
    if marker_at != -1 and _looks_like_font(data, base + marker_at + 4):
        return base + marker_at + 4
    if _looks_like_font(data, base + 4):
        return base + 4
    if _looks_like_font(data, base):
        return base
    return None


def _looks_like_font(data: bytes, pos: int) -> bool:
    if pos < 0 or pos + 209 > len(data):
        return False
    if data[pos] > 12:
        return False
    return data[pos + 17] in TYPE_NAMES


def _read_name(data: bytes, pos: int) -> str:
    raw = data[pos + 1 : pos + 13].split(b"\x00", 1)[0]
    return raw.decode("cp437", errors="replace").strip()


def _read_offsets(data: bytes, pos: int) -> list[int]:
    return [int.from_bytes(data[pos + i * 2 : pos + i * 2 + 2], "little") for i in range(94)]


def _read_glyphs(blob: bytes, offsets: list[int], font_type: int) -> dict[str, Glyph]:
    cache: dict[int, Glyph | None] = {}
    glyphs: dict[str, Glyph] = {}
    for index, offset in enumerate(offsets):
        if offset == 0xFFFF or offset >= len(blob):
            continue
        if offset not in cache:
            cache[offset] = _read_glyph(blob, offset, font_type)
        glyph = cache[offset]
        if glyph is not None and glyph.width:
            glyphs[CHARSET[index]] = glyph
    return glyphs


def _read_glyph(blob: bytes, offset: int, font_type: int) -> Glyph | None:
    if offset + 2 > len(blob):
        return None
    width = blob[offset]
    if width == 0 or width > _MAX_GLYPH_WIDTH:
        return None
    cursor = offset + 2
    parsed: list[tuple[list[Cell], bool]] = []
    raw_row: list = []

    def finish() -> None:
        cells, marked = _cells_from_row(raw_row, font_type, width)
        parsed.append((cells, marked))

    while cursor < len(blob) and len(parsed) < _MAX_GLYPH_ROWS:
        byte = blob[cursor]
        if byte == 0:
            if raw_row:
                finish()
            raw_row = []
            break
        if byte == 0x0D:
            finish()
            raw_row = []
            cursor += 1
            continue
        if font_type == TYPE_COLOR:
            if cursor + 1 >= len(blob):
                break
            raw_row.append((byte, blob[cursor + 1]))
            cursor += 2
        else:
            raw_row.append(byte)
            cursor += 1
        if len(raw_row) > _MAX_GLYPH_WIDTH:
            return None
    if raw_row and len(parsed) < _MAX_GLYPH_ROWS:
        finish()
    if not parsed:
        return None
    body: list[list[Cell]] = []
    desc: list[list[Cell]] = []
    in_descender = False
    for cells, is_descender in parsed:
        if is_descender:
            in_descender = True
        if in_descender:
            desc.append(cells)
        else:
            body.append(cells)
    if not body and desc:
        body, desc = desc, []
    return Glyph(width, body, desc)


def _cells_from_row(raw: list, font_type: int, width: int) -> tuple[list[Cell], bool]:
    marked = False
    cells: list[Cell] = []
    if font_type == TYPE_COLOR:
        for char_byte, colour in raw:
            cells.append(_color_cell(char_byte, colour))
    elif font_type == TYPE_OUTLINE:
        values = list(raw)
        if values and values[-1] == ord("&"):
            marked = True
            values.pop()
        for value in values:
            if value == ord("&"):
                marked = True
                continue
            cells.append(_outline_cell(value))
    else:
        for value in raw:
            cells.append(Cell(cp437(value)))
    if len(cells) < width:
        cells.extend(Cell() for _ in range(width - len(cells)))
    return cells[:width], marked


def _color_cell(char_byte: int, colour: int) -> Cell:
    char = cp437(char_byte)
    fg = Color(*VGA[colour & 0x0F])
    bg_index = (colour >> 4) & 0x07
    bg = Color(*VGA[bg_index]) if bg_index else None
    if char == " " and bg is None:
        return Cell()
    # The DOS index is the relation. RGB is only the current value of that role.
    return Cell(char, fg, bg, colour & 0x0F, bg_index or None)


def _outline_cell(value: int) -> Cell:
    if 32 <= value < 127:
        mapped = OUTLINE_CHARS.get(chr(value))
        if mapped is not None:
            return Cell(mapped) if mapped != " " else Cell()
        return Cell(chr(value))
    return Cell(cp437(value))
