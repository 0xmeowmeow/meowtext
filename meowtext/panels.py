"""Panels a phosphor page can hold.

An image is fitted without stretching, then turned into one green. A helix
twists as you scan it. Data can be drawn as glyphs, cells, an array, a dial,
or a gauge. A four-way readout and an equalizer bar are the two strips under
the poster. The equalizer takes levels, which can come from cava.
"""

from __future__ import annotations

from pathlib import Path

import math
import shutil
import subprocess
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from meowtext.grid import Color

INK = Color(150, 255, 214)
DIM = Color(46, 120, 96)
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
_BAYER = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
DATA_MODES = ("glyphs", "cells", "array", "dial", "gauge")
AMBER = Color(255, 168, 48)
AMBER_DIM = Color(120, 64, 16)


def render_image(
    source: str | None,
    width: int,
    height: int,
    *,
    auto_levels: bool = False,
    negative: bool = False,
    dither: bool = False,
) -> Image.Image:
    """Fit a picture into the panel, then make it one green.

    ``source`` is the file baked into the TUI. ``None`` leaves the slot empty
    so the person running it can choose a file. The fit covers the panel and
    crops the overflow. It does not stretch.
    """

    if not source:
        return _empty(width, height, "pick an image")
    picture = Image.open(source).convert("RGB")
    fitted = cover(picture, width, height)
    luma = _luma(fitted)
    if auto_levels:
        luma = _levels(luma)
    if negative:
        luma = luma.point(lambda value: 255 - value)
    if dither:
        return _dither(luma)
    return _greenscale(luma)


def cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale uniformly until the panel is full, then crop the extra."""

    width = max(1, width)
    height = max(1, height)
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def render_svg(svg: bytes | str, width: int, height: int, *, crop: tuple[float, float, float, float] = (0, 0, 1, 1)) -> Image.Image:
    """Rasterise an SVG, crop a window of it, and fit that window to the panel.

    ``crop`` is left, top, right, bottom in fractions of the drawing.
    """

    raw = svg.encode("utf-8") if isinstance(svg, str) else svg
    raster = _magick_svg(raw, max(width, height) * 2)
    left, top, right, bottom = crop
    box = (
        int(raster.width * left),
        int(raster.height * top),
        int(raster.width * right),
        int(raster.height * bottom),
    )
    window = raster.crop(box) if box[2] > box[0] and box[3] > box[1] else raster
    return _greenscale(_luma(cover(window.convert("RGB"), width, height)))


BASES_PER_TURN = 10
_COMPLEMENT = {"A": "T", "T": "A", "G": "C", "C": "G"}
DEFAULT_SEQUENCE = "ATGGCTACGA" "CCTAGGTTAC" "GATCCGTAAG"


def complement(base: str) -> str:
    return _COMPLEMENT.get(base.upper(), "N")


def helix_rungs(sequence: str, phase: float = 0.0) -> list[dict]:
    """One record per base pair.

    Ten pairs make one turn. The angle increases by 36 degrees per step up
    the axis, which is a right-handed helix: thumb up the axis, fingers
    curling the way the strand turns. A second turn is the same ten sections
    stacked on the first.
    """

    rungs = []
    for index, base in enumerate(sequence.upper()):
        if base not in _COMPLEMENT:
            continue
        theta = index * math.tau / BASES_PER_TURN + phase
        rungs.append(
            {
                "index": index,
                "base": base,
                "pair": complement(base),
                "theta": theta,
                "x": math.cos(theta),
                "z": math.sin(theta),
            }
        )
    return rungs


def render_helix(width: int, height: int, scan: float, *, bases: str = DEFAULT_SEQUENCE) -> Image.Image:
    """Watson and Crick's ladder, wound.

    ``scan`` walks the sequence. The pair under the scan is turned to face
    you, and the ten sections of the turn move with it.
    """

    sequence = "".join(base for base in bases.upper() if base in _COMPLEMENT) or "ATGCGTACGA"
    chosen = min(len(sequence) - 1, int(_unit(scan) * (len(sequence) - 1)))
    phase = -chosen * math.tau / BASES_PER_TURN
    rungs = helix_rungs(sequence, phase)
    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    if len(rungs) < 2:
        return image
    margin = 18
    rise = (height - margin * 2) / (len(rungs) - 1)
    radius = width * 0.30
    cx = width / 2
    font = _font(max(9, int(min(rise * 0.7, width * 0.08))))
    placed = []
    for rung in rungs:
        y = height - margin - rung["index"] * rise
        placed.append({**rung, "y": y, "x1": cx + rung["x"] * radius, "x2": cx - rung["x"] * radius})
    segments = []
    for rung, nxt in zip(placed, placed[1:]):
        front = (rung["z"] + nxt["z"]) / 2
        segments.append((front, (rung["x1"], rung["y"], nxt["x1"], nxt["y"])))
        segments.append((-front, (rung["x2"], rung["y"], nxt["x2"], nxt["y"])))
    for front, line in sorted(segments, key=lambda item: item[0]):
        colour = INK if front > 0 else DIM
        draw.line(line, fill=_rgb(colour), width=3 if front > 0 else 2)
    for rung in sorted(placed, key=lambda item: abs(item["z"])):
        span = abs(rung["x"])
        facing = span > 0.82
        colour = INK if rung["index"] == chosen or facing else DIM
        draw.line((rung["x1"], rung["y"], rung["x2"], rung["y"]), fill=_rgb(colour), width=2 if facing else 1)
        for point, front in ((rung["x1"], rung["z"]), (rung["x2"], -rung["z"])):
            mark = 3.2 if front > 0.2 else 2.2
            draw.ellipse(_dot(point, rung["y"], mark), fill=_rgb(INK if front > 0 else DIM))
        if not facing:
            continue
        bonds = 3 if rung["base"] in "GC" else 2
        for bond in range(bonds):
            bx = cx + (bond - (bonds - 1) / 2) * span * radius * 0.22
            draw.ellipse(_dot(bx, rung["y"], 1.3), fill=_rgb(INK))
        left_base, right_base = (rung["base"], rung["pair"]) if rung["x"] >= 0 else (rung["pair"], rung["base"])
        draw.text((cx - radius * 0.55, rung["y"] - 7), left_base, font=font, fill=_rgb(INK))
        draw.text((cx + radius * 0.28, rung["y"] - 7), right_base, font=font, fill=_rgb(INK))
    return image


def render_amber_crt(
    curves: list[list[float]],
    columns: list[float],
    width: int,
    height: int,
    *,
    border: str = "ticks",
    glow: float = 0.85,
) -> Image.Image:
    """The amber photograph, drawn as a CRT rather than a tilted frame.

    The upper half is a fan of dotted arcs leaving a hot cusp. The lower half
    is columns of points under a bright ridge. The frame stays square.
    """

    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        tiny = ImageFont.truetype(str(Path.home() / ".local/share/fonts/TerminessNerdFontMono-Regular.ttf"), max(10, width // 58))
        label = ImageFont.truetype(str(Path.home() / ".local/share/fonts/TerminessNerdFontMono-Regular.ttf"), max(11, width // 48))
    except OSError:
        tiny = _font(11)
        label = _font(13)
    left, right = int(width * 0.12), int(width * 0.90)
    top, bottom = int(height * 0.12), int(height * 0.84)
    mid = int(top + (bottom - top) * 0.46)
    frame = AMBER
    if border != "none":
        draw.rectangle((left, top, right, bottom), outline=_rgb(frame), width=1)
    draw.text((left, max(1, top - 16)), "SBARI-SDIL-BRYAN-DDEC77", font=tiny, fill=_heat(AMBER, 0.35))
    cycle = "CYCLE  1871"
    draw.text((left + (right - left) * 0.28, max(2, top - 28)), cycle, font=tiny, fill=_heat(AMBER, 0.45))
    time = "TIME  0.10+50"
    draw.text((left + (right - left) * 0.62, max(2, top - 28)), time, font=tiny, fill=_heat(AMBER, 0.45))
    if border == "ticks":
        for mark, text in enumerate(("5", "10", "15", "20")):
            x = left + int((mark + 1) / 5 * (right - left))
            draw.line((x, bottom, x, bottom - 6), fill=_rgb(frame))
            draw.line((x, top, x, top + 5), fill=_rgb(frame))
            draw.text((x - 6, bottom + 3), text, font=tiny, fill=_heat(AMBER, 0.4))
        for step in range(1, 5):
            y = top + int(step / 5 * (bottom - top))
            draw.line((left, y, left + 5, y), fill=_rgb(frame))
            draw.line((right, y, right - 5, y), fill=_rgb(frame))
    draw.text(((left + right) / 2 - 28, bottom + 16), "R-AXIS", font=label, fill=_rgb(frame))
    _vertical_amber(image, "Z-AXIS", left - 16, (top + bottom) // 2, label)
    draw.line((left + 2, mid, right - 2, mid), fill=_heat(AMBER, 0.7), width=1)
    _amber_arcs(draw, curves, left, top, right, mid)
    _amber_columns(draw, columns, left, mid, right, bottom)
    return bloom(image, glow)


def _amber_arcs(draw: ImageDraw.ImageDraw, curves: list[list[float]], left: int, top: int, right: int, mid: int) -> None:
    count = max(12, (len(curves) or 1) * 2)
    cusp_x = left + (right - left) * 0.04
    cusp_y = mid - 1
    span_x = (right - left) * 1.05
    span_y = (mid - top) * 1.05
    for index in range(count):
        weight = 0.7
        if curves:
            row = curves[min(len(curves) - 1, index * len(curves) // count)]
            if row:
                weight = sum(_unit(value) for value in row) / len(row)
        depth = index / max(1, count - 1)
        for step in range(80):
            t = step / 79
            reach = (0.22 + 0.78 * depth) * (0.4 + 0.6 * weight)
            x = cusp_x + t * span_x * reach
            bow = math.sin(t * math.pi * 0.9) * (0.25 + 0.7 * depth)
            y = cusp_y - (0.05 * t + bow) * span_y * (0.45 + 0.55 * weight)
            if x < left + 2 or x > right - 2 or y < top + 2 or y > mid - 2:
                continue
            heat = (1 - t) * (1 - depth * 0.65) * (0.35 + 0.65 * weight)
            draw.ellipse(_dot(x, y, 1.15), fill=_heat(AMBER, heat))


def _amber_columns(draw: ImageDraw.ImageDraw, columns: list[float], left: int, mid: int, right: int, bottom: int) -> None:
    heights = columns or [0.2]
    inner_w = right - left - 8
    inner_h = bottom - mid - 8
    for index in range(inner_w // 4):
        x_norm = index / max(1, inner_w // 4 - 1)
        sample_at = min(len(heights) - 1, int(x_norm * (len(heights) - 1)))
        envelope = _unit(heights[sample_at])
        x = left + 4 + index * 4
        y = bottom - 4
        limit = mid + 4 + (1 - envelope) * inner_h
        while y > limit:
            rise = 0 if inner_h == 0 else (bottom - 4 - y) / inner_h
            heat = envelope * (0.15 + 0.85 * rise)
            if rise > envelope - 0.04:
                heat = min(1.0, heat + 0.45)
            draw.ellipse(_dot(x, y, 1.05), fill=_heat(AMBER, heat))
            y -= 4


def _vertical_amber(image: Image.Image, text: str, x: int, y: int, font) -> None:
    scratch = Image.new("RGBA", (int(font.getlength(text)) + 4, 16), (0, 0, 0, 0))
    ImageDraw.Draw(scratch).text((0, 0), text, font=font, fill=_rgb(AMBER) + (255,))
    turned = scratch.rotate(90, expand=True)
    image.paste(turned, (max(0, x), max(0, y - turned.height // 2)), turned)


def render_gif(path: str, width: int, height: int, scan: float) -> Image.Image:
    """One frame of a GIF. ``scan`` walks the frames from first to last."""

    picture = Image.open(path)
    frames = getattr(picture, "n_frames", 1)
    picture.seek(min(frames - 1, int(_unit(scan) * (frames - 1))))
    return _greenscale(_luma(cover(picture.convert("RGB"), width, height)))


def render_data(values: list[float], mode: str, width: int, height: int) -> Image.Image:
    """The same numbers, drawn as glyphs, cells, an array, a dial, or a gauge."""

    mode = mode if mode in DATA_MODES else "cells"
    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    amounts = [_unit(value) for value in values] or [0.0]
    if mode == "glyphs":
        _glyphs(draw, amounts, width, height)
    elif mode == "array":
        _array(draw, amounts, width, height)
    elif mode == "dial":
        _dial(draw, sum(amounts) / len(amounts), width, height)
    elif mode == "gauge":
        _gauge(draw, sum(amounts) / len(amounts), width, height)
    else:
        _cells(draw, amounts, width, height)
    return image


def render_points(
    series: list[list[float]],
    layout: str,
    width: int,
    height: int,
    ink: Color,
    *,
    perspective: bool = False,
) -> Image.Image:
    """Points across a curve, or a column of points for each value.

    With perspective, the top of the panel is the far edge: it narrows, the
    way a sheet of the plot tips away from you.
    """

    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = 8
    inner_w = max(1, width - pad * 2)
    inner_h = max(1, height - pad * 2)
    if layout == "columns":
        heights = series[0] if series else []
        if not heights:
            return image
        for index, amount in enumerate(heights):
            x_norm = (index + 0.5) / len(heights)
            span = _unit(amount)
            top = pad + int((1 - span) * inner_h)
            y = height - pad
            while y >= top:
                y_norm = (y - pad) / inner_h
                heat = span * (0.25 + 0.75 * (1 - y_norm))
                px, py = _on_plane(x_norm, y_norm, pad, inner_w, inner_h, perspective)
                draw.ellipse(_dot(px, py, 1.5), fill=_heat(ink, heat))
                y -= 4
        return image
    depth_count = max(1, len(series) - 1)
    for depth, row in enumerate(series):
        if len(row) < 2:
            continue
        for index, amount in enumerate(row):
            x_norm = index / (len(row) - 1)
            y_norm = 1 - _unit(amount)
            if perspective:
                y_norm = min(1.0, y_norm * 0.82 + depth / depth_count * 0.18)
            heat = (1 - x_norm) * (0.45 + 0.55 * _unit(amount))
            px, py = _on_plane(x_norm, y_norm, pad, inner_w, inner_h, perspective)
            draw.ellipse(_dot(px, py, 1.7), fill=_heat(ink, heat))
    return image


def bloom(image: Image.Image, amount: float) -> Image.Image:
    """A phosphor bloom. ``amount`` is 0 for a hard point, 1 for a wide halo."""

    if amount <= 0:
        return image.convert("RGB")
    base = image.convert("RGB")
    radius = max(0.6, (1.1 + amount * 5) * min(base.size) / 560)
    haze = base.filter(ImageFilter.GaussianBlur(radius=radius))
    haze = ImageEnhance.Brightness(haze).enhance(0.2 + amount)
    return ImageChops.screen(base, haze)


def recede(image: Image.Image, amount: float = 0.12) -> Image.Image:
    """Tip the sheet back. The far edge, at the top, grows narrower."""

    if amount <= 0:
        return image
    width, height = image.size
    inset = width * amount
    output = [(inset, 0), (width - 1 - inset, 0), (width - 1, height - 1), (0, height - 1)]
    source = [(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)]
    return image.transform(image.size, Image.Transform.PERSPECTIVE, _quad(output, source), Image.Resampling.BICUBIC)


def render_selector(options: tuple[str, str, str, str], selected: int, width: int, height: int) -> Image.Image:
    """Four readouts. One of them is the lit choice."""

    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font(max(11, height // 6))
    row = height / 4
    for index, label in enumerate(options):
        top = int(index * row) + 2
        lit = index == selected % 4
        if lit:
            draw.rectangle((2, top, width - 3, top + int(row) - 4), outline=_rgb(INK))
        draw.text((10, top + 2), label, font=font, fill=_rgb(INK if lit else DIM))
    return image


def render_equalizer(levels: list[float], width: int, height: int) -> Image.Image:
    """Vertical bars, the shape cava draws. ``levels`` are 0 to 1."""

    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    if not levels:
        return image
    draw = ImageDraw.Draw(image)
    gap = max(1, width // (len(levels) * 8) or 1)
    bar_w = max(1, (width - gap * (len(levels) + 1)) // len(levels))
    for index, level in enumerate(levels):
        amount = _unit(level)
        left = gap + index * (bar_w + gap)
        top = int(height - 4 - amount * (height - 8))
        draw.rectangle((left, top, left + bar_w, height - 4), fill=_rgb(INK))
        draw.rectangle((left, max(0, top - 3), left + bar_w, max(0, top - 1)), fill=_rgb(DIM))
    return image


def _luma(image: Image.Image) -> Image.Image:
    return image.convert("L")


def _levels(luma: Image.Image) -> Image.Image:
    histogram = luma.histogram()
    total = sum(histogram)
    if total == 0:
        return luma
    low = 0
    seen = 0
    for index, count in enumerate(histogram):
        seen += count
        if seen >= total * 0.01:
            low = index
            break
    high = 255
    seen = 0
    for index in range(255, -1, -1):
        seen += histogram[index]
        if seen >= total * 0.01:
            high = index
            break
    if high <= low:
        return luma
    scale = 255 / (high - low)
    return luma.point(lambda value, low=low, scale=scale: int(max(0, min(255, (value - low) * scale))))


def _greenscale(luma: Image.Image) -> Image.Image:
    red = luma.point(lambda value: int(value * INK.r / 255))
    green = luma.point(lambda value: int(value * INK.g / 255))
    blue = luma.point(lambda value: int(value * INK.b / 255))
    return Image.merge("RGB", (red, green, blue))


def _dither(luma: Image.Image) -> Image.Image:
    pixels = luma.load()
    image = Image.new("RGB", luma.size, (0, 0, 0))
    out = image.load()
    for y in range(luma.height):
        for x in range(luma.width):
            threshold = (_BAYER[y % 4][x % 4] + 0.5) / 16 * 255
            out[x, y] = _rgb(INK) if pixels[x, y] >= threshold else (0, 0, 0)
    return image


def _empty(width: int, height: int, caption: str) -> Image.Image:
    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, image.width - 2, image.height - 2), outline=_rgb(DIM))
    draw.text((8, 8), caption, font=_font(max(11, height // 8)), fill=_rgb(DIM))
    return image


def _glyphs(draw, amounts, width, height) -> None:
    font = _font(max(12, height // 4))
    marks = " .:-=+*#%@"
    text = "".join(marks[min(len(marks) - 1, int(amount * (len(marks) - 1)))] for amount in amounts)
    draw.text((6, height // 3), text[: max(1, width // 10)], font=font, fill=_rgb(INK))


def _cells(draw, amounts, width, height) -> None:
    columns = max(1, round(math.sqrt(len(amounts))))
    rows = math.ceil(len(amounts) / columns)
    cell_w = width / columns
    cell_h = height / rows
    for index, amount in enumerate(amounts):
        column, row = index % columns, index // columns
        pad = 2
        box = (
            int(column * cell_w) + pad,
            int(row * cell_h) + pad,
            int((column + 1) * cell_w) - pad,
            int((row + 1) * cell_h) - pad,
        )
        colour = INK if amount > 0.66 else DIM if amount > 0.33 else Color(16, 40, 32)
        draw.rectangle(box, fill=_rgb(colour))


def _array(draw, amounts, width, height) -> None:
    font = _font(max(11, height // (len(amounts) + 2)))
    for index, amount in enumerate(amounts[:12]):
        draw.text((8, 4 + index * (height // max(1, min(12, len(amounts))))), f"{index:02d}  {amount:0.2f}", font=font, fill=_rgb(INK))


def _dial(draw, amount, width, height) -> None:
    radius = min(width, height) * 0.36
    cx, cy = width / 2, height / 2
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, start=135, end=45, fill=_rgb(DIM), width=max(2, width // 40))
    end = (135 + amount * 270) % 360
    if amount > 0:
        draw.arc(box, start=135, end=end, fill=_rgb(INK), width=max(2, width // 40))
    angle = math.radians(225 - amount * 270)
    draw.line(
        [(cx, cy), (cx + math.cos(angle) * radius * 0.7, cy - math.sin(angle) * radius * 0.7)],
        fill=_rgb(INK),
        width=max(2, width // 50),
    )


def _gauge(draw, amount, width, height) -> None:
    top = height * 0.4
    draw.rounded_rectangle((8, top, width - 8, top + height * 0.2), radius=height * 0.1, fill=_rgb(DIM))
    if amount > 0:
        draw.rounded_rectangle((8, top, 8 + (width - 16) * amount, top + height * 0.2), radius=height * 0.1, fill=_rgb(INK))


def _magick_svg(raw: bytes, width: int) -> Image.Image:
    executable = shutil.which("magick") or shutil.which("convert")
    if executable is None:
        raise RuntimeError("SVG panels need ImageMagick. Install the imagemagick system package.")
    completed = subprocess.run(
        [executable, "-background", "none", "svg:-", "-resize", f"{max(1, width)}x", "png:-"],
        input=raw,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace")[:200] or "svg raster failed")
    return Image.open(BytesIO(completed.stdout)).convert("RGBA")


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_FONT, max(1, size))
    except OSError:
        return ImageFont.load_default()


def _rgb(ink: Color) -> tuple[int, int, int]:
    return (ink.r, ink.g, ink.b)


def _on_plane(x_norm: float, y_norm: float, pad: int, inner_w: int, inner_h: int, perspective: bool) -> tuple[float, float]:
    y_norm = max(0.0, min(1.0, y_norm))
    if perspective:
        inset = 0.18 * (1 - y_norm)
        x_norm = inset + x_norm * (1 - 2 * inset)
    return pad + x_norm * inner_w, pad + y_norm * inner_h


def _heat(ink: Color, heat: float) -> tuple[int, int, int]:
    """Hot is nearly white. Cool is a deep shade of the same ink."""

    heat = max(0.0, min(1.0, heat))
    hot = (255, 244, 214)
    mid = (ink.r, ink.g, ink.b)
    cool = (max(8, ink.r // 4), max(4, ink.g // 6), max(0, ink.b // 8))
    if heat >= 0.6:
        mix = (heat - 0.6) / 0.4
        return tuple(int(mid[channel] + (hot[channel] - mid[channel]) * mix) for channel in range(3))
    mix = heat / 0.6
    return tuple(int(cool[channel] + (mid[channel] - cool[channel]) * mix) for channel in range(3))


def _quad(output: list[tuple[float, float]], source: list[tuple[float, float]]) -> list[float]:
    """Perspective coefficients that land the source rectangle on ``output``."""

    rows = []
    rhs = []
    for (ox, oy), (sx, sy) in zip(output, source):
        rows.append([ox, oy, 1, 0, 0, 0, -sx * ox, -sx * oy])
        rhs.append(sx)
        rows.append([0, 0, 0, ox, oy, 1, -sy * ox, -sy * oy])
        rhs.append(sy)
    return _solve(rows, rhs)


def _solve(rows: list[list[float]], rhs: list[float]) -> list[float]:
    size = len(rhs)
    grid = [rows[index][:] + [rhs[index]] for index in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(grid[row][col]))
        grid[col], grid[pivot] = grid[pivot], grid[col]
        scale = grid[col][col]
        if abs(scale) < 1e-12:
            return [1, 0, 0, 0, 1, 0, 0, 0]
        for column in range(col, size + 1):
            grid[col][column] /= scale
        for row in range(size):
            if row == col:
                continue
            factor = grid[row][col]
            for column in range(col, size + 1):
                grid[row][column] -= factor * grid[col][column]
    return [grid[index][size] for index in range(size)]


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _dot(x: float, y: float, radius: float) -> tuple[float, float, float, float]:
    return (x - radius, y - radius, x + radius, y + radius)
