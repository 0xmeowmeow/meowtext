"""Rasterise terminal cells without glyph overhang or stretched block elements."""

from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

from meowtext.errors import RenderError
from meowtext.grid import Grid

MONO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


@lru_cache(maxsize=16)
def _font(size):
    try:
        return ImageFont.truetype(MONO_FONT, size)
    except OSError as exc:
        raise RenderError(f"could not load {MONO_FONT}") from exc


@lru_cache(maxsize=2048)
def _mask(char: str, size: int):
    font = _font(size)
    width = max(1, round(font.getlength("M")))
    height = sum(font.getmetrics())
    mask = Image.new("L", (width, height))
    draw = ImageDraw.Draw(mask)
    # Terminal block elements are fractions of a cell, not typographic glyphs.
    # In DejaVu, e.g. the upper half extends into 3/4 of the line box, and a
    # full block overhangs its neighbours. Drawing the font directly doubled
    # strokes and erased edges when the next cell's background was painted.
    code = ord(char) if len(char) == 1 else 0
    if char == "▀":
        draw.rectangle((0, 0, width - 1, (height + 1) // 2 - 1), fill=255)
    elif 0x2581 <= code <= 0x2588:
        pixels = round(height * (code - 0x2580) / 8)
        draw.rectangle((0, height - pixels, width - 1, height - 1), fill=255)
    elif 0x2589 <= code <= 0x258F:
        pixels = round(width * (0x2590 - code) / 8)
        draw.rectangle((0, 0, pixels - 1, height - 1), fill=255)
    elif char == "▐":
        draw.rectangle(((width + 1) // 2, 0, width - 1, height - 1), fill=255)
    elif char == "▔":
        draw.rectangle((0, 0, width - 1, max(1, round(height / 8)) - 1), fill=255)
    elif char == "▕":
        draw.rectangle(
            (width - max(1, round(width / 8)), 0, width - 1, height - 1), fill=255
        )
    elif 0x2596 <= code <= 0x259F:
        # top-left, top-right, bottom-left, bottom-right quadrants
        bits = (4, 8, 1, 13, 9, 7, 11, 2, 6, 14)[code - 0x2596]
        mx, my = (width + 1) // 2, (height + 1) // 2
        for bit, rect in zip(
            (1, 2, 4, 8),
            (
                (0, 0, mx - 1, my - 1),
                (mx, 0, width - 1, my - 1),
                (0, my, mx - 1, height - 1),
                (mx, my, width - 1, height - 1),
            ),
        ):
            if bits & bit:
                draw.rectangle(rect, fill=255)
    else:
        # A separate cell mask clips overhanging outlines and letters. All
        # backgrounds are composited independently, as in a terminal.
        draw.text((0, 0), char, font=font, fill=255)
    return mask


def rasterize(grid: Grid, font_size: int = 18, background=(0, 0, 0)) -> Image.Image:
    """Paint a grid at its natural 1-column / 1-line geometry."""
    font = _font(font_size)
    cell_w, cell_h = max(1, round(font.getlength("M"))), sum(font.getmetrics())
    image = Image.new(
        "RGB", (max(1, grid.width * cell_w), max(1, grid.height * cell_h)), background
    )
    for y, row in enumerate(grid.rows):
        for x, cell in enumerate(row):
            left, top = x * cell_w, y * cell_h
            if cell.bg is not None:
                image.paste(
                    (cell.bg.r, cell.bg.g, cell.bg.b),
                    (left, top, left + cell_w, top + cell_h),
                )
            if cell.char not in ("", " "):
                fg = (cell.fg.r, cell.fg.g, cell.fg.b) if cell.fg else (230, 230, 230)
                image.paste(fg, (left, top), _mask(cell.char, font_size))
    return image


def fit_image(grid: Grid, width: int, height: int, cell_size=(10, 20)):
    """Fit both axes once, padding to whole terminal cells without stretching.

    Returns (image, columns, rows). Never enlarges a font automatically.
    """
    import math

    width, height = max(1, width), max(1, height)
    cw, ch = cell_size
    factor = min(1, width / max(1, grid.width), height / max(1, grid.height))
    pixels = (
        max(1, round(grid.width * cw * factor)),
        max(1, round(grid.height * ch * factor)),
    )
    columns, rows = min(width, math.ceil(pixels[0] / cw)), min(
        height, math.ceil(pixels[1] / ch)
    )
    # Draw once at sufficient resolution, then downsample once. Padding keeps
    # the final TGP placement from changing the aspect to fit whole cells.
    source = rasterize(grid, max(18, ch), background=(9, 15, 23))
    source = source.resize(pixels, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (columns * cw, rows * ch), (9, 15, 23))
    canvas.paste(
        source, ((canvas.width - pixels[0]) // 2, (canvas.height - pixels[1]) // 2)
    )
    return canvas, columns, rows
