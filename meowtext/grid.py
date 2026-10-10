"""A banner is a rectangle of terminal cells.

Other programs (a Charmbracelet client, a Kitty graphics export, a web
page) all start from this grid. One cell is one terminal column.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Color:
    """An 8-bit-per-channel colour."""

    r: int
    g: int
    b: int

    def hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_hex(cls, text: str) -> Color:
        raw = text.strip().lstrip("#")
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) != 6:
            raise ValueError(f"not a hex colour: {text!r}")
        return cls(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


# DOS VGA palette, the colours TheDraw stored in a font.
VGA: tuple[tuple[int, int, int], ...] = (
    (0x00, 0x00, 0x00),
    (0x00, 0x00, 0xAA),
    (0x00, 0xAA, 0x00),
    (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00),
    (0xAA, 0x00, 0xAA),
    (0xAA, 0x55, 0x00),
    (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55),
    (0x55, 0x55, 0xFF),
    (0x55, 0xFF, 0x55),
    (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55),
    (0xFF, 0x55, 0xFF),
    (0xFF, 0xFF, 0x55),
    (0xFF, 0xFF, 0xFF),
)

# ANSI SGR 30–37 and 90–97 are not VGA indexes. 31 is red, VGA 1 is blue.
ANSI16: dict[int, int] = {
    30: 0,
    31: 4,
    32: 2,
    33: 6,
    34: 1,
    35: 5,
    36: 3,
    37: 7,
    90: 8,
    91: 12,
    92: 10,
    93: 14,
    94: 9,
    95: 13,
    96: 11,
    97: 15,
}


def color_256(index: int) -> Color:
    """XTerm 256-colour index as RGB."""

    index %= 256
    if index < 16:
        return Color(*VGA[index])
    if index < 232:
        value = index - 16
        steps = (0, 95, 135, 175, 215, 255)
        return Color(steps[value // 36], steps[(value % 36) // 6], steps[value % 6])
    gray = 8 + (index - 232) * 10
    return Color(gray, gray, gray)


@dataclass(slots=True)
class Cell:
    """One terminal column.

    ``fg_slot`` and ``bg_slot`` are palette roles. Colour TheDraw cells keep
    the DOS index here so a later hue shift can move every cell of that role
    together. ``fg`` and ``bg`` are the colours after that shift has been applied.
    """

    char: str = " "
    fg: Color | None = None
    bg: Color | None = None
    fg_slot: int | None = None
    bg_slot: int | None = None

    def clone(self) -> Cell:
        return Cell(self.char, self.fg, self.bg, self.fg_slot, self.bg_slot)


def is_empty(cell: Cell) -> bool:
    """A cell that carries no glyph and no paint."""

    return cell.char in ("", " ") and cell.fg is None and cell.bg is None


def is_ink(cell: Cell) -> bool:
    """A cell that should take part in outline, shadow, and gradients."""

    if cell.bg is not None:
        return True
    return cell.char not in ("", " ")


class Grid:
    """A rectangular banner. Rows are stored left to right, top to bottom."""

    def __init__(self, rows: list[list[Cell]] | None = None) -> None:
        self.rows: list[list[Cell]] = rows or []
        self.palette: object | None = None

    @classmethod
    def blank(cls, width: int, height: int) -> Grid:
        return cls([[Cell() for _ in range(width)] for _ in range(height)])

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def height(self) -> int:
        return len(self.rows)

    def get(self, x: int, y: int) -> Cell:
        if y < 0 or y >= len(self.rows) or x < 0 or x >= len(self.rows[y]):
            return Cell()
        return self.rows[y][x]

    def set(self, x: int, y: int, cell: Cell) -> None:
        if x < 0 or y < 0:
            return
        while len(self.rows) <= y:
            self.rows.append([])
        row = self.rows[y]
        while len(row) <= x:
            row.append(Cell())
        row[x] = cell

    def normalize(self) -> None:
        """Pad every row out to the same width."""

        width = self.width
        for row in self.rows:
            if len(row) < width:
                row.extend(Cell() for _ in range(width - len(row)))

    def copy(self) -> Grid:
        copied = Grid([[cell.clone() for cell in row] for row in self.rows])
        copied.palette = self.palette
        return copied

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Grid):
            return NotImplemented
        return self.rows == other.rows
