"""Turn text plus a font plus a style into a banner."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

from meowtext.catalog import FontInfo, default_font, render, resolve
from meowtext.effects import (
    Animation,
    BannerStyle,
    animation_phase,
    apply_style,
    motion_clock,
    scan,
    sparkle,
    trace,
)
from meowtext.errors import RenderError
from meowtext.grid import Cell, Grid
from meowtext.palette import RelationPalette, paint

MAX_TEXT = 240


@dataclass(slots=True)
class Banner:
    grid: Grid
    font: FontInfo
    missing: tuple[str, ...]
    folded: bool


def clean_text(text: str) -> str:
    """Keep newlines. Drop other control characters so they cannot hide in a banner."""

    kept: list[str] = []
    for char in text.replace("\r\n", "\n").replace("\r", "\n"):
        if char == "\n":
            kept.append(char)
        elif char == "\t":
            kept.append(" ")
        elif char < " " or char == "\x7f":
            continue
        else:
            kept.append(char)
    return "".join(kept)


def render_banner(
    text: str,
    engine: str = "figlet",
    font: str | None = None,
    style: BannerStyle | None = None,
) -> Banner:
    info = resolve(engine, font) if font else default_font(engine)
    return render_font(text, info, style or BannerStyle())


def layout_font(
    text: str,
    font: FontInfo,
    letters: dict[str, Grid] | None = None,
) -> tuple[Grid, tuple[str, ...], bool]:
    """The unpainted banner. Colour TheDraw cells still carry their palette roles.

    ``letters`` replaces individual glyphs. The banner is then set letter by
    letter, so those shapes can be edited without rewriting the font file.
    """

    text = clean_text(text)
    if len(text) > MAX_TEXT:
        raise RenderError(f"text is limited to {MAX_TEXT} characters")
    if text == "":
        return Grid(), (), False
    if letters:
        return _layout_letters(text, font, letters)
    drawn = render(font, text)
    return drawn.grid, drawn.missing, drawn.folded


def present(
    source: Grid,
    style: BannerStyle,
    palette: RelationPalette | None = None,
    anim: str = "none",
    frame: int = 0,
    animation: Animation | None = None,
    patches: tuple[tuple[int, int, Cell], ...] = (),
) -> Grid:
    """Resolve colour roles, decorate, then apply one frame of animation."""

    motion = animation or Animation(name=anim)
    palette = palette or RelationPalette(hue=style.hue)
    palette.ensure(source)
    phase, hue_offset, outline_phase, pulse = _motion(motion, frame, style.outline_speed)
    styled = apply_style(
        paint(source, palette, hue_offset),
        style,
        phase=phase,
        pulse=pulse,
        outline_phase=outline_phase,
    )
    if motion.name == "sparkle":
        styled = sparkle(styled, int(motion_clock(frame, motion)))
    elif motion.name == "scan":
        styled = scan(styled, int(motion_clock(frame, motion)))
    elif motion.name == "trace":
        styled = trace(styled, motion, frame)
    if patches:
        styled = _apply_patches(styled, patches)
    return styled


def _motion(motion: Animation, frame: int, outline_speed: float) -> tuple[float, float, float, float]:
    """Letter phase, role hue, outline phase, and outline pulse for this frame."""

    if motion.name not in {"hue", "march", "pulse"}:
        return 0.0, 0.0, 0.0, 1.0
    clock = motion_clock(frame, motion)
    if motion.name == "pulse":
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(clock / 2.5))
        return 0.0, 0.0, 0.0, pulse
    phase, hue_offset = animation_phase(clock, motion.travel)
    if motion.name == "march":
        hue_offset = 0.0
    outline_phase = animation_phase(clock * (outline_speed if outline_speed > 0 else 1.0), motion.travel)[0]
    layers = motion.layers
    if layers == "letters":
        return phase, 0.0, 0.0, 1.0
    if layers == "outline":
        return 0.0, 0.0, outline_phase, 1.0
    if layers == "roles":
        if motion.name == "march":
            hue_offset = animation_phase(clock, motion.travel)[1]
        return 0.0, hue_offset, 0.0, 1.0
    return phase, hue_offset, outline_phase, 1.0


def _apply_patches(grid: Grid, patches: tuple[tuple[int, int, Cell], ...]) -> Grid:
    out = grid.copy()
    for x, y, cell in patches:
        if y < 0 or x < 0 or y >= out.height or x >= out.width:
            continue
        painted = cell.clone()
        painted.fg_slot = None
        painted.bg_slot = None
        out.set(x, y, painted)
    return out


_GLYPHS: OrderedDict[tuple[str, str], tuple[Grid, tuple[str, ...], bool]] = OrderedDict()


def _layout_letters(
    text: str,
    font: FontInfo,
    letters: dict[str, Grid],
) -> tuple[Grid, tuple[str, ...], bool]:
    missing: list[str] = []
    folded = False
    blocks: list[Grid] = []
    for line in text.split("\n"):
        pieces: list[Grid] = []
        spans: list[tuple[str, int, int, int, int]] = []
        x = 0
        for char in line:
            if char in letters and letters[char].height:
                piece = letters[char].copy()
            else:
                piece, glyph_missing, glyph_folded = _cached_glyph(font, char)
                piece = piece.copy()
                folded = folded or glyph_folded
                for item in glyph_missing:
                    if item not in missing:
                        missing.append(item)
            if piece.width == 0:
                piece = Grid.blank(1, max(piece.height, 1))
            pieces.append(piece)
            spans.append((char, x, 0, piece.width, piece.height))
            x += piece.width
        block = _hstack(pieces) if pieces else Grid.blank(0, 1)
        block.spans = tuple(spans)
        blocks.append(block)
    return _vstack(blocks), tuple(missing), folded


def _cached_glyph(font: FontInfo, char: str) -> tuple[Grid, tuple[str, ...], bool]:
    key = (font.id, char)
    cached = _GLYPHS.get(key)
    if cached is not None:
        _GLYPHS.move_to_end(key)
        return cached
    drawn = render(font, char)
    stored = (drawn.grid, drawn.missing, drawn.folded)
    _GLYPHS[key] = stored
    while len(_GLYPHS) > 400:
        _GLYPHS.popitem(last=False)
    return stored


def _hstack(pieces: list[Grid]) -> Grid:
    height = max(piece.height for piece in pieces)
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


def _vstack(blocks: list[Grid]) -> Grid:
    width = max((block.width for block in blocks), default=0)
    rows: list[list[Cell]] = []
    spans: list[tuple[str, int, int, int, int]] = []
    y = 0
    for block in blocks:
        for char, x, sy, w, h in block.spans:
            spans.append((char, x, y + sy, w, h))
        for row in block.rows:
            padded = [cell.clone() for cell in row]
            if len(padded) < width:
                padded.extend(Cell() for _ in range(width - len(padded)))
            rows.append(padded[:width] if width else [])
        y += block.height
    grid = Grid(rows)
    grid.spans = tuple(spans)
    return grid


def render_font(
    text: str,
    font: FontInfo,
    style: BannerStyle | None = None,
    palette: RelationPalette | None = None,
) -> Banner:
    style = style or BannerStyle()
    source, missing, folded = layout_font(text, font)
    if source.height == 0 and text == "":
        return Banner(Grid(), font, (), False)
    if palette is None:
        palette = RelationPalette(hue=style.hue)
    else:
        palette.hue = style.hue
    return Banner(present(source, style, palette), font, missing, folded)
