"""Turn text plus a font plus a style into a banner."""

from __future__ import annotations

import math
from dataclasses import dataclass

from meowtext.catalog import FontInfo, default_font, render, resolve
from meowtext.effects import BannerStyle, apply_style, scan, sparkle
from meowtext.errors import RenderError
from meowtext.grid import Grid
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


def layout_font(text: str, font: FontInfo) -> tuple[Grid, tuple[str, ...], bool]:
    """The unpainted banner. Colour TheDraw cells still carry their palette roles."""

    text = clean_text(text)
    if len(text) > MAX_TEXT:
        raise RenderError(f"text is limited to {MAX_TEXT} characters")
    if text == "":
        return Grid(), (), False
    drawn = render(font, text)
    return drawn.grid, drawn.missing, drawn.folded


def present(
    source: Grid,
    style: BannerStyle,
    palette: RelationPalette | None = None,
    anim: str = "none",
    frame: int = 0,
) -> Grid:
    """Resolve colour roles, decorate, then apply one frame of animation."""

    palette = palette or RelationPalette(hue=style.hue)
    palette.ensure(source)
    hue_offset = (frame * 12) % 360 if anim == "hue" else 0.0
    phase = (frame % 24) / 24 if anim in {"hue", "march"} else 0.0
    pulse = 1.0
    if anim == "pulse":
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(frame / 2.5))
    styled = apply_style(paint(source, palette, hue_offset), style, phase=phase, pulse=pulse)
    if anim == "sparkle":
        return sparkle(styled, frame)
    if anim == "scan":
        return scan(styled, frame)
    return styled


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
