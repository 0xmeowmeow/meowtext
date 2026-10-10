"""Write a banner for a terminal, a browser, Kitty, or another program."""

from __future__ import annotations

import base64
import json
from io import BytesIO

from meowtext.errors import RenderError
from meowtext.grid import Cell, Color, Grid, is_empty
from meowtext.palette import RelationPalette, Role, rgb_to_hsv

# mIRC colour numbers are not VGA indexes. 0 is white, 1 is black.
_MIRC: tuple[Color, ...] = (
    Color(255, 255, 255),
    Color(0, 0, 0),
    Color(0, 0, 127),
    Color(0, 147, 0),
    Color(255, 0, 0),
    Color(127, 0, 0),
    Color(156, 0, 156),
    Color(252, 127, 0),
    Color(255, 255, 0),
    Color(0, 252, 0),
    Color(0, 147, 147),
    Color(0, 255, 255),
    Color(0, 0, 252),
    Color(255, 0, 255),
    Color(127, 127, 127),
    Color(210, 210, 210),
)

FORMATS = ("ansi", "plain", "html", "json", "png", "kitty", "irc")

_MONO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def export(grid: Grid, fmt: str) -> str | bytes:
    key = fmt.lower().lstrip(".")
    aliases = {"ans": "ansi", "txt": "plain", "htm": "html"}
    key = aliases.get(key, key)
    writers = {
        "ansi": to_ansi,
        "plain": to_plain,
        "html": to_html,
        "json": to_json,
        "png": to_png,
        "kitty": to_kitty,
        "irc": to_irc,
    }
    if key not in writers:
        known = ", ".join(FORMATS)
        raise RenderError(f"unknown format {fmt!r} (expected {known})")
    return writers[key](grid)


def to_plain(grid: Grid) -> str:
    return "\n".join("".join(cell.char or " " for cell in row) for row in grid.rows) + (
        "\n" if grid.rows else ""
    )


def to_ansi(grid: Grid) -> str:
    lines: list[str] = []
    for row in grid.rows:
        parts: list[str] = []
        last_fg: Color | None = object()  # type: ignore[assignment]
        last_bg: Color | None = object()  # type: ignore[assignment]
        for cell in row:
            codes: list[str] = []
            if cell.fg != last_fg:
                codes.append("39" if cell.fg is None else f"38;2;{cell.fg.r};{cell.fg.g};{cell.fg.b}")
                last_fg = cell.fg
            if cell.bg != last_bg:
                codes.append("49" if cell.bg is None else f"48;2;{cell.bg.r};{cell.bg.g};{cell.bg.b}")
                last_bg = cell.bg
            if codes:
                parts.append("\x1b[" + ";".join(codes) + "m")
            parts.append(cell.char or " ")
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def to_html(grid: Grid) -> str:
    body: list[str] = []
    for row in grid.rows:
        for cell in row:
            styles: list[str] = []
            if cell.fg is not None:
                styles.append(f"color:{cell.fg.hex()}")
            if cell.bg is not None:
                styles.append(f"background:{cell.bg.hex()}")
            char = _html_escape(cell.char or " ").replace(" ", "&nbsp;")
            if styles:
                body.append(f'<span style="{";".join(styles)}">{char}</span>')
            else:
                body.append(char)
        body.append("\n")
    picture = "".join(body)
    return (
        "<!DOCTYPE html>\n"
        '<meta charset="utf-8">\n'
        "<title>meowtext</title>\n"
        "<pre style=\"margin:0;background:#000;color:#eee;line-height:1.05;"
        "font-family:'DejaVu Sans Mono',ui-monospace,monospace\">"
        f"{picture}</pre>\n"
    )


def to_json(grid: Grid) -> str:
    """Versioned cell document. This is the interchange for other programs."""

    cells = []
    for row in grid.rows:
        encoded = []
        for cell in row:
            item: dict[str, str | int] = {"c": cell.char or " "}
            if cell.fg is not None:
                item["fg"] = cell.fg.hex()
            if cell.bg is not None:
                item["bg"] = cell.bg.hex()
            if cell.fg_slot is not None:
                item["fg_slot"] = cell.fg_slot
            if cell.bg_slot is not None:
                item["bg_slot"] = cell.bg_slot
            encoded.append(item)
        cells.append(encoded)
    document: dict = {"meowtext": 1, "width": grid.width, "height": grid.height, "cells": cells}
    palette = grid.palette if isinstance(grid.palette, RelationPalette) else None
    if palette is not None and (palette.roles or palette.hue):
        document["hue"] = palette.hue
        document["roles"] = {
            str(slot): _role_json(role) for slot, role in sorted(palette.roles.items())
        }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _role_json(role: Role) -> dict[str, str | float | bool]:
    payload: dict[str, str | float | bool] = {
        "base": role.base.hex(),
        "name": role.name,
        "linked": role.linked,
    }
    if not role.linked:
        payload["h"] = role.hue
        payload["s"] = role.sat
        payload["v"] = role.val
    return payload


def grid_from_json(document: dict) -> Grid:
    version = document.get("meowtext")
    if version != 1:
        raise RenderError(f"unsupported meowtext document version: {version!r}")
    rows: list[list[Cell]] = []
    for row in document.get("cells", []):
        cells: list[Cell] = []
        for item in row:
            fg = Color.from_hex(item["fg"]) if item.get("fg") else None
            bg = Color.from_hex(item["bg"]) if item.get("bg") else None
            fg_slot = item.get("fg_slot")
            bg_slot = item.get("bg_slot")
            cells.append(
                Cell(
                    str(item.get("c") or " "),
                    fg,
                    bg,
                    int(fg_slot) if fg_slot is not None else None,
                    int(bg_slot) if bg_slot is not None else None,
                )
            )
        rows.append(cells)
    grid = Grid(rows)
    grid.normalize()
    roles = document.get("roles")
    if isinstance(roles, dict):
        palette = RelationPalette(hue=float(document.get("hue") or 0))
        for key, item in roles.items():
            base = Color.from_hex(str(item["base"]))
            hue, sat, val = rgb_to_hsv(base)
            palette.roles[int(key)] = Role(
                base,
                str(item.get("name") or key),
                bool(item.get("linked", True)),
                float(item.get("h", hue)),
                float(item.get("s", sat)),
                float(item.get("v", val)),
            )
        if palette.roles:
            palette.next_id = max(palette.roles) + 1
        grid.palette = palette
    return grid


def to_irc(grid: Grid) -> str:
    """mIRC colour codes, the kind IRC and some BBS clients still accept."""

    lines: list[str] = []
    for row in grid.rows:
        parts: list[str] = []
        last: tuple[int | None, int | None] | None = None
        for cell in row:
            fg = _nearest_mirc(cell.fg) if cell.fg is not None else None
            bg = _nearest_mirc(cell.bg) if cell.bg is not None else None
            pair = (fg, bg)
            if pair != last:
                if fg is None and bg is None:
                    parts.append("\x03")
                elif bg is None:
                    parts.append(f"\x03{fg:02d}")
                else:
                    parts.append(f"\x03{fg if fg is not None else 1:02d},{bg:02d}")
                last = pair
            parts.append(cell.char or " ")
        parts.append("\x03")
        lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def to_png(grid: Grid, font_size: int = 18) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RenderError("PNG export needs Pillow") from exc

    try:
        font = ImageFont.truetype(_MONO_FONT, font_size)
    except OSError as exc:
        raise RenderError(f"could not load {_MONO_FONT}") from exc

    cell_w = max(1, int(round(font.getlength("M"))))
    ascent, descent = font.getmetrics()
    cell_h = max(1, ascent + descent)
    width = max(1, grid.width * cell_w)
    height = max(1, grid.height * cell_h)
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid.rows):
        for x, cell in enumerate(row):
            if is_empty(cell):
                continue
            left, top = x * cell_w, y * cell_h
            if cell.bg is not None:
                draw.rectangle(
                    (left, top, left + cell_w - 1, top + cell_h - 1),
                    fill=(cell.bg.r, cell.bg.g, cell.bg.b),
                )
            if cell.char not in ("", " "):
                fill = (cell.fg.r, cell.fg.g, cell.fg.b) if cell.fg else (230, 230, 230)
                draw.text((left, top), cell.char, font=font, fill=fill)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def to_kitty(grid: Grid) -> str:
    """Kitty graphics protocol. ``cat`` the file inside Kitty to show it."""

    payload = base64.standard_b64encode(to_png(grid)).decode("ascii")
    parts: list[str] = []
    step = 4096
    for offset in range(0, max(len(payload), 1), step):
        piece = payload[offset : offset + step]
        more = 1 if offset + step < len(payload) else 0
        control = f"a=T,f=100,m={more}" if offset == 0 else f"m={more}"
        parts.append(f"\x1b_G{control};{piece}\x1b\\")
    return "".join(parts)


def _nearest_mirc(colour: Color) -> int:
    best = 0
    best_distance = 1e18
    for index, candidate in enumerate(_MIRC):
        distance = (
            (colour.r - candidate.r) ** 2
            + (colour.g - candidate.g) ** 2
            + (colour.b - candidate.b) ** 2
        )
        if distance < best_distance:
            best = index
            best_distance = distance
    return best


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
