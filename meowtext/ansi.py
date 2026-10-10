"""Read and tidy ANSI/UTF-8 banner output from figlet and toilet."""

from __future__ import annotations

from meowtext.grid import ANSI16, VGA, Cell, Color, Grid, color_256, is_empty


def cp437(byte: int) -> str:
    """One DOS byte as a single Unicode character. Controls become spaces."""

    if byte < 0x20 or byte == 0x7F:
        return " "
    char = bytes([byte]).decode("cp437")
    if char == "\u00a0":
        return " "
    return char


def parse_ansi(text: str) -> Grid:
    """Turn an ANSI/UTF-8 picture into a grid. One character is one cell."""

    text = text.replace("\r\n", "\n").replace("\r", "")
    if text.endswith("\n"):
        text = text[:-1]

    rows: list[list[Cell]] = [[]]
    fg: Color | None = None
    bg: Color | None = None
    bold = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            rows.append([])
            index += 1
            continue
        if char == "\x1b" and index + 1 < len(text):
            kind = text[index + 1]
            if kind == "[":
                final, params, index = _read_csi(text, index + 2)
                if final == "m":
                    fg, bg, bold = _apply_sgr(params, fg, bg, bold)
                continue
            if kind == "]":
                index = _skip_until_st(text, index + 2)
                continue
            index += 1
            continue
        if char < " " or char == "\x7f":
            index += 1
            continue
        rows[-1].append(Cell(char, fg, bg))
        index += 1
    return tighten(Grid(rows))


def _read_csi(text: str, index: int) -> tuple[str, list[int], int]:
    start = index
    while index < len(text) and not ("@" <= text[index] <= "~"):
        index += 1
    final = text[index] if index < len(text) else ""
    body = text[start:index]
    params: list[int] = []
    for part in body.split(";"):
        if part == "":
            params.append(0)
        else:
            try:
                params.append(int(part))
            except ValueError:
                params.append(0)
    return final, params, index + 1 if final else index


def _skip_until_st(text: str, index: int) -> int:
    while index < len(text):
        if text[index] == "\a":
            return index + 1
        if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "\\":
            return index + 2
        index += 1
    return index


def _apply_sgr(
    params: list[int],
    fg: Color | None,
    bg: Color | None,
    bold: bool,
) -> tuple[Color | None, Color | None, bool]:
    if not params:
        params = [0]
    cursor = 0
    while cursor < len(params):
        code = params[cursor]
        if code == 0:
            fg, bg, bold = None, None, False
        elif code == 1:
            bold = True
        elif code == 22:
            bold = False
        elif code == 39:
            fg = None
        elif code == 49:
            bg = None
        elif code in ANSI16:
            slot = ANSI16[code]
            if bold and 30 <= code <= 37:
                slot = ANSI16[code + 60]
            fg = Color(*VGA[slot])
        elif code in {40, 41, 42, 43, 44, 45, 46, 47}:
            bg = Color(*VGA[ANSI16[code - 10]])
        elif code in {100, 101, 102, 103, 104, 105, 106, 107}:
            bg = Color(*VGA[ANSI16[code - 10]])
        elif code in {38, 48} and cursor + 1 < len(params):
            mode = params[cursor + 1]
            target_fg = code == 38
            if mode == 5 and cursor + 2 < len(params):
                colour = color_256(params[cursor + 2])
                cursor += 2
            elif mode == 2 and cursor + 4 < len(params):
                colour = Color(params[cursor + 2], params[cursor + 3], params[cursor + 4])
                cursor += 4
            else:
                colour = None
            if colour is not None:
                if target_fg:
                    fg = colour
                else:
                    bg = colour
        cursor += 1
    return fg, bg, bold


def tighten(grid: Grid) -> Grid:
    """Drop blank rows at the edges and blank columns on the right.

    Leading columns stay. Slanted FIGlet glyphs use them.
    """

    rows = [list(row) for row in grid.rows]
    while rows and all(is_empty(cell) for cell in rows[0]):
        rows.pop(0)
    while rows and all(is_empty(cell) for cell in rows[-1]):
        rows.pop()
    if not rows:
        return Grid()
    last = -1
    for row in rows:
        for x, cell in enumerate(row):
            if not is_empty(cell):
                last = max(last, x)
    if last < 0:
        return Grid()
    trimmed: list[list[Cell]] = []
    width = last + 1
    for row in rows:
        row = row[:width]
        if len(row) < width:
            row.extend(Cell() for _ in range(width - len(row)))
        trimmed.append(row)
    return Grid(trimmed)
