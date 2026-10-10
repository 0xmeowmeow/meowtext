"""Fit a complete banner preview without starting or probing a terminal UI."""

from PIL import Image
from rich.style import Style
from rich.text import Text
from meowtext.grid import Grid
from meowtext.raster import rasterize
from meowtext.tui import to_rich


def fit_preview(grid: Grid, width: int, height: int) -> Text:
    """Native cells when they fit; a complete pixel thumbnail for large banners."""
    if not grid.width or not grid.height:
        return Text("Type some words to see this font", style="#899bab")
    width, height = max(1, width), max(1, height)
    if grid.width <= width and grid.height <= height:
        return to_rich(grid)
    picture = rasterize(grid, background=(9, 15, 23)).convert("RGBA")
    # Half-blocks carry two square-ish pixels per terminal cell.
    picture.thumbnail((width, height * 2), Image.Resampling.LANCZOS)
    background = Image.new("RGB", picture.size, (9, 15, 23))
    background.paste(picture, mask=picture.getchannel("A"))
    out = Text()
    for y in range(0, background.height, 2):
        for x in range(background.width):
            top = background.getpixel((x, y))
            bottom = background.getpixel((x, min(y + 1, background.height - 1)))
            out.append("▀", Style(color=f"rgb{top}", bgcolor=f"rgb{bottom}"))
        out.append("\n")
    return out
