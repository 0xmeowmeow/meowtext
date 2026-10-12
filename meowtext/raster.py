"""Rasterise terminal cells without glyph overhang or stretched block elements."""

from functools import lru_cache
import unicodedata
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


def cell_size(size=18):
    font = _font(size)
    return max(1, round(font.getlength("M"))), sum(font.getmetrics())


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
    if 0x2500 <= code <= 0x257F and "DIAGONAL" not in unicodedata.name(char, ""):
        # Box drawing joins at the cell edges. Font ascent/descent would leave
        # gaps between every line, especially in thin ANSI and contour fonts.
        name = unicodedata.name(char).removeprefix("BOX DRAWINGS ")
        directions = set(name.split()) & {"LEFT", "RIGHT", "UP", "DOWN"}
        if "HORIZONTAL" in name:
            directions.update(("LEFT", "RIGHT"))
        if "VERTICAL" in name:
            directions.update(("UP", "DOWN"))
        cx, cy = width // 2, height // 2
        thickness = max(1, round(size / (9 if "HEAVY" in name else 18)))
        if "ARC" in name:
            # Rounded corners are not square elbows. Keep the same edge
            # connections while leaving the corner's centre genuinely curved.
            radius = max(1, min(width // 2, height // 2))
            sx = 1 if "RIGHT" in directions else -1
            sy = 1 if "DOWN" in directions else -1
            ox, oy = cx + sx * radius, cy + sy * radius
            angle = {(1,1):180, (1,-1):90, (-1,1):270, (-1,-1):0}[sx,sy]
            draw.arc((ox-radius,oy-radius,ox+radius,oy+radius), angle, angle+90, fill=255, width=thickness)
            draw.line((cx,cy+sy*radius,cx,height-1 if sy>0 else 0),fill=255,width=thickness)
            draw.line((cx+sx*radius,cy,width-1 if sx>0 else 0,cy),fill=255,width=thickness)
            return mask
        if "DASH" in name:
            count = 4 if "QUADRUPLE" in name else 3 if "TRIPLE" in name else 2
            horizontal = "HORIZONTAL" in name
            length = width if horizontal else height
            for index in range(count):
                start = round(index * length / count)
                end = max(start, round((index + .65) * length / count) - 1)
                draw.line((start,cy,end,cy) if horizontal else (cx,start,cx,end),fill=255,width=thickness)
            return mask
        for direction in directions:
            double = "DOUBLE" in name and "DASH" not in name
            # Mixed single/double junctions name the weight of each axis.
            if "SINGLE" in name:
                axis = "HORIZONTAL" if direction in {"LEFT", "RIGHT"} else "VERTICAL"
                double = f"{direction} DOUBLE" in name or f"{axis} DOUBLE" in name
            offsets = (-max(1, thickness), max(1, thickness)) if double else (0,)
            for offset in offsets:
                hx, vy = cx, cy
                if double and "SINGLE" not in name:
                    horizontal = directions & {"LEFT", "RIGHT"}
                    vertical = directions & {"UP", "DOWN"}
                    if direction in horizontal and vertical:
                        sx = 1 if direction == "RIGHT" else -1
                        hx += sx * (max(1,thickness) if len(vertical)==2 else offset*(1 if "DOWN" in vertical else -1))
                    if direction in vertical and horizontal:
                        sy = 1 if direction == "DOWN" else -1
                        vy += sy * (max(1,thickness) if len(horizontal)==2 else offset*(1 if "RIGHT" in horizontal else -1))
                if direction == "LEFT":
                    line = (0, cy + offset, hx, cy + offset)
                elif direction == "RIGHT":
                    line = (hx, cy + offset, width - 1, cy + offset)
                elif direction == "UP":
                    line = (cx + offset, 0, cx + offset, vy)
                else:
                    line = (cx + offset, vy, cx + offset, height - 1)
                draw.line(line, fill=255, width=thickness)
    elif 0x2591 <= code <= 0x2593:
        # Stable terminal stippling, without a font's margins or overhang.
        level = code - 0x2590
        for y in range(height):
            for x in range(width):
                if ((x % 2) + 2 * (y % 2)) < level:
                    draw.point((x, y), fill=255)
    elif char == "▀":
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
    cell_w, cell_h = cell_size(font_size)
    image = Image.new(
        "RGBA" if len(background) == 4 else "RGB", (max(1, grid.width * cell_w), max(1, grid.height * cell_h)), background
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
