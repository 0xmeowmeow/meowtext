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

FORMATS = ("html", "png", "apng", "gif", "ansi", "plain", "json", "kitty", "irc", "markdown")

FORMAT_LABELS = {
    "html": "HTML5 · text + colour cycling",
    "png": "PNG · still image",
    "apng": "Animated PNG · lossless animation",
    "gif": "Animated GIF · 256 colours",
    "ansi": "ANSI · terminal still",
    "plain": "Plain text · no colour or motion",
    "json": "JSON · cell data, one frame",
    "kitty": "Kitty · artwork + animation",
    "irc": "IRC · 16 colours, one frame",
    "markdown": "Markdown · no colour or motion",
    "project": "Project · editable recipe",
}


def export_notice(fmt: str, animated: bool = False) -> str:
    """Explain the actual contract before a file is written."""
    notices = {
        "html": "HTML5 text cells with an embedded font and fixed alignment. Colours cycle in the page; no image frames. Browser font smoothing can differ slightly from PNG.",
        "png": "Still image of the frame currently shown. Keeps colours, borders and shadows.",
        "apng": "Lossless animated PNG. Open in a modern browser; some image viewers show only its first frame.",
        "gif": "Animated GIF keeps motion, with a shared 256-colour palette. Gradients can show bands or colour shifts; timing rounds to 10 ms. Choose HTML5 or APNG for full colour.",
        "ansi": "One frame with true colour. Appearance depends on the terminal's font and cell size.",
        "plain": "Characters only: removes all colours, including painted backgrounds.",
        "markdown": "Characters in a code block: removes all colours, including painted backgrounds.",
        "json": "Cell data for one frame; this is not an editable project or animation player.",
        "kitty": "Exact artwork for Kitty. Display the downloaded file with cat in Kitty; other terminals may not support it.",
        "irc": "One frame reduced to 16 IRC colours. Colours will change.",
        "project": "Keeps editable settings and animation. Reopen in Meowtext; the original font is required.",
    }
    notice = notices.get(fmt, "")
    if animated:
        if fmt == "html":
            notice += " Plays the animation at editor speed, with Pause and Replay controls."
        elif fmt == "kitty":
            notice += " Kitty plays the complete animation itself, even after cat exits. Requires Kitty 0.20 or newer."
        elif fmt not in {"apng", "gif", "project"}:
            notice += " Animation will be lost. Choose HTML5, Animated PNG, GIF or Kitty to keep it; pause first to choose a still."
    return notice

_MONO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def export(grid: Grid, fmt: str) -> str | bytes:
    key = fmt.lower().lstrip(".")
    aliases = {"ans": "ansi", "txt": "plain", "htm": "html", "md": "markdown"}
    key = aliases.get(key, key)
    writers = {
        "ansi": to_ansi,
        "plain": to_plain,
        "html": to_html,
        "json": to_json,
        "png": to_png,
        "apng": to_png,
        "gif": to_gif,
        "kitty": to_kitty,
        "irc": to_irc,
        "markdown": to_markdown,
    }
    if key not in writers:
        known = ", ".join(FORMATS)
        raise RenderError(f"unknown format {fmt!r} (expected {known})")
    return writers[key](grid)


def to_plain(grid: Grid) -> str:
    return "\n".join("".join(cell.char or " " for cell in row) for row in grid.rows) + (
        "\n" if grid.rows else ""
    )


def to_markdown(grid: Grid) -> str:
    text = to_plain(grid)
    import re

    length = max([2] + [len(m.group()) for m in re.finditer(r"`+", text)]) + 1
    fence = "`" * length
    return f"{fence}text\n{text}{fence}\n"


def to_ansi(grid: Grid) -> str:
    lines: list[str] = []
    for row in grid.rows:
        parts: list[str] = []
        last_fg: Color | None = object()  # type: ignore[assignment]
        last_bg: Color | None = object()  # type: ignore[assignment]
        for cell in row:
            codes: list[str] = []
            if cell.fg != last_fg:
                codes.append(
                    "39"
                    if cell.fg is None
                    else f"38;2;{cell.fg.r};{cell.fg.g};{cell.fg.b}"
                )
                last_fg = cell.fg
            if cell.bg != last_bg:
                codes.append(
                    "49"
                    if cell.bg is None
                    else f"48;2;{cell.bg.r};{cell.bg.g};{cell.bg.b}"
                )
                last_bg = cell.bg
            if codes:
                parts.append("\x1b[" + ";".join(codes) + "m")
            parts.append(cell.char or " ")
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def to_html(grid: Grid) -> str:
    from meowtext.animation_export import html_player, Timeline

    return html_player([grid], grid, Timeline())


def to_gif(grid: Grid) -> bytes:
    from meowtext.animation_export import gif_player, Timeline
    from meowtext.raster import rasterize

    return gif_player([rasterize(grid)], Timeline())


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
    document: dict = {
        "meowtext": 1,
        "width": grid.width,
        "height": grid.height,
        "cells": cells,
    }
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
    from meowtext.raster import rasterize

    image = rasterize(grid, font_size)
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
        control = f"a=T,f=100,q=2,m={more}" if offset == 0 else f"m={more}"
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
