"""A readout is a small file that says how a panel gets its numbers.

The file names four things. The style is how the numbers are drawn. The range
is the low and high of the measurement, mapped onto the height of a bar or the
sweep of a dial. The format is the shape of the raw reading. The source is
where that reading comes from: a file beside the definition, a URL, a local
script, or a name in the running program's memory.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from meowtext.grid import Color
from meowtext.panels import AMBER, bloom, recede, render_data, render_equalizer, render_points

STYLES = ("glyphs", "cells", "array", "dial", "gauge", "bars", "points")
FORMATS = ("numbers", "lines", "rows", "json", "csv", "bytes")
LAYOUTS = ("curve", "curves", "columns")
BORDERS = ("none", "box", "ticks")
INKS = {
    "green": Color(150, 255, 214),
    "amber": AMBER,
}
_FLOAT = re.compile(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?")
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "readouts" / "signal.json"


@dataclass(frozen=True, slots=True)
class Plot:
    """A frame and the readouts stacked inside it. Amber plot is two of these."""

    name: str
    ink: str
    border: str
    readouts: tuple[Readout, ...]
    glow: str = "strong"
    perspective: bool = False
    caption: str = ""
    aside: str = ""
    x_axis: str = ""
    y_axis: str = ""
    x_ticks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Readout:
    name: str
    style: str
    source: str
    format: str
    field: str | None
    low: float
    high: float
    count: int
    layout: str = "curve"
    ink: str = "green"
    border: str = "none"
    origin: Path | None = None

    @classmethod
    def from_mapping(cls, data: dict, origin: Path | None = None) -> Readout:
        span = data.get("range") or [0, 1]
        style = str(data.get("style") or "cells")
        form = str(data.get("format") or "numbers")
        layout = str(data.get("layout") or "curve")
        ink = str(data.get("ink") or "green")
        border = str(data.get("border") or "none")
        return cls(
            name=str(data.get("name") or (origin.stem if origin else "readout")),
            style=style if style in STYLES else "cells",
            source=str(data["source"]),
            format=form if form in FORMATS else "numbers",
            field=str(data["field"]) if data.get("field") else None,
            low=float(span[0]),
            high=float(span[1]),
            count=max(1, int(data.get("count") or 16)),
            layout=layout if layout in LAYOUTS else "curve",
            ink=ink if ink in INKS else "green",
            border=border if border in BORDERS else "none",
            origin=origin,
        )


def load_plot(path: Path | str) -> Plot:
    origin = Path(path)
    data = json.loads(origin.read_text(encoding="utf-8"))
    ink = str(data.get("ink") or "amber")
    border = str(data.get("border") or "box")
    glow = str(data.get("glow") or "strong")
    children = []
    for name in data.get("readouts") or []:
        children.append(load_readout(origin.parent / name))
    ticks = data.get("x_ticks") or []
    return Plot(
        name=str(data.get("name") or origin.stem),
        ink=ink if ink in INKS else "amber",
        border=border if border in BORDERS else "box",
        readouts=tuple(children),
        glow=glow if glow in {"none", "soft", "strong"} else "strong",
        perspective=bool(data.get("perspective")),
        caption=str(data.get("caption") or ""),
        aside=str(data.get("aside") or ""),
        x_axis=str(data.get("x_axis") or ""),
        y_axis=str(data.get("y_axis") or ""),
        x_ticks=tuple(str(item) for item in ticks),
    )


def render_plot(plot: Plot, width: int, height: int, memory: dict | None = None) -> Image.Image:
    """Stack the readouts and frame them. A perspective plot is the amber CRT."""

    if plot.perspective and len(plot.readouts) >= 2:
        from meowtext.panels import render_amber_crt

        curves = _series(plot.readouts[0], memory)
        columns = sample(plot.readouts[1], memory)
        glow = {"none": 0.0, "soft": 0.45, "strong": 0.85}.get(plot.glow, 0.85)
        return render_amber_crt(curves, columns, width, height, border=plot.border, glow=glow)
    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    if not plot.readouts:
        return image
    ink = INKS[plot.ink]
    margin_top = 22 if plot.caption or plot.aside else 10
    margin_bottom = 28 if plot.x_axis or plot.x_ticks else 10
    margin_side = 26 if plot.y_axis else 10
    gap = 2
    inner_w = max(1, width - margin_side * 2)
    inner_h = max(1, height - margin_top - margin_bottom - gap * (len(plot.readouts) - 1))
    row_h = max(1, inner_h // len(plot.readouts))
    for index, readout in enumerate(plot.readouts):
        part = render_readout(readout, inner_w, row_h, memory, perspective=plot.perspective)
        image.paste(part, (margin_side, margin_top + index * (row_h + gap)))
    draw = ImageDraw.Draw(image)
    frame = (margin_side, margin_top, margin_side + inner_w, margin_top + inner_h + gap * (len(plot.readouts) - 1))
    for index in range(1, len(plot.readouts)):
        y = margin_top + index * (row_h + gap) - 1
        draw.line((frame[0], y, frame[2], y), fill=_ink_rgb(ink), width=1)
    _frame_detail(image, draw, frame, plot, ink)
    if plot.perspective:
        image = recede(image, 0.1)
    return bloom(image, {"none": 0, "soft": 0.45, "strong": 0.9}.get(plot.glow, 0.9))


def load_readout(path: Path | str) -> Readout:
    origin = Path(path)
    return Readout.from_mapping(json.loads(origin.read_text(encoding="utf-8")), origin)


def sample(readout: Readout, memory: dict | None = None, *, timeout: float = 2) -> list[float]:
    """Read the source, parse it, and map the last values into 0..1."""

    raw = _raw_values(readout, memory, timeout)
    window = raw[-readout.count :]
    return [_scale(value, readout.low, readout.high) for value in window]


def render_readout(
    readout: Readout,
    width: int,
    height: int,
    memory: dict | None = None,
    *,
    perspective: bool = False,
) -> Image.Image:
    """Draw the readout. A source that fails becomes a line of text, not a crash."""

    try:
        values = sample(readout, memory)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired, urllib.error.URLError) as exc:
        return _notice(width, height, str(exc).splitlines()[0][:80])
    if not values and readout.style != "points":
        return _notice(width, height, "no values")
    ink = INKS.get(readout.ink, INKS["green"])
    if readout.style == "points":
        picture = render_points(
            _series(readout, memory),
            readout.layout,
            width,
            height,
            ink,
            perspective=perspective,
        )
    elif readout.style == "bars":
        picture = render_equalizer(values, width, height)
    else:
        picture = render_data(values, readout.style, width, height)
    if readout.border != "none":
        draw = ImageDraw.Draw(picture)
        _border(draw, picture.width, picture.height, readout.border, ink)
    return picture


def _raw_values(readout: Readout, memory: dict | None, timeout: float) -> list[float]:
    kind, _, rest = readout.source.partition(":")
    if not rest:
        raise ValueError("source needs a kind, such as file: or memory:")
    if kind == "memory":
        if memory is None or rest not in memory:
            raise KeyError(f"memory:{rest}")
        held = memory[rest]
        if isinstance(held, (int, float)):
            return [float(held)]
        if isinstance(held, (list, tuple)):
            if held and isinstance(held[0], (list, tuple)):
                return [float(value) for row in held for value in row]
            return [float(value) for value in held]
        return _parse(str(held), readout.format, readout.field)
    if kind == "file":
        path = Path(rest)
        if not path.is_absolute() and readout.origin is not None:
            path = readout.origin.parent / path
        if readout.format == "bytes":
            return [float(byte) for byte in path.read_bytes()]
        return _parse(path.read_text(encoding="utf-8"), readout.format, readout.field)
    if kind == "url":
        with urllib.request.urlopen(rest, timeout=timeout) as response:
            body = response.read()
        if readout.format == "bytes":
            return [float(byte) for byte in body]
        return _parse(body.decode("utf-8", "replace"), readout.format, readout.field)
    if kind == "script":
        completed = subprocess.run(
            shlex.split(rest),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise OSError(completed.stderr.decode("utf-8", "replace")[:160] or "script failed")
        text = completed.stdout.decode("utf-8", "replace")
        return _parse(text, readout.format, readout.field)
    raise ValueError(f"unknown source {kind}")


def _series(readout: Readout, memory: dict | None) -> list[list[float]]:
    if readout.layout == "curves" or readout.format == "rows":
        rows = _raw_rows(readout, memory)
        scaled = []
        for row in rows:
            window = row[-readout.count :]
            scaled.append([_scale(value, readout.low, readout.high) for value in window])
        return [row for row in scaled if row]
    return [sample(readout, memory)]


def _raw_rows(readout: Readout, memory: dict | None) -> list[list[float]]:
    kind, _, rest = readout.source.partition(":")
    if kind == "memory":
        if memory is None or rest not in memory:
            raise KeyError(f"memory:{rest}")
        held = memory[rest]
        if isinstance(held, (list, tuple)) and held and isinstance(held[0], (list, tuple)):
            return [[float(value) for value in row] for row in held]
        return [[float(value) for value in held]]
    text = _text_from(readout, memory)
    rows = []
    for line in text.splitlines():
        piece = line.strip()
        if not piece or piece.startswith("#"):
            continue
        rows.append([float(match) for match in _FLOAT.findall(piece)])
    return rows


def _text_from(readout: Readout, memory: dict | None) -> str:
    kind, _, rest = readout.source.partition(":")
    if kind == "file":
        path = Path(rest)
        if not path.is_absolute() and readout.origin is not None:
            path = readout.origin.parent / path
        return path.read_text(encoding="utf-8")
    if kind == "memory":
        if memory is None or rest not in memory:
            raise KeyError(f"memory:{rest}")
        return str(memory[rest])
    raise ValueError(f"rows need a file or memory source, not {kind}")


def _parse(text: str, form: str, field: str | None) -> list[float]:
    if form == "rows":
        return [float(value) for row in text.splitlines() for value in _FLOAT.findall(row)]
    if form == "lines":
        values = []
        for line in text.splitlines():
            piece = line.strip()
            if not piece or piece.startswith("#"):
                continue
            values.append(float(piece.split()[0]))
        return values
    if form == "json":
        payload = json.loads(text)
        if field:
            payload = _dig(payload, field)
        if isinstance(payload, (int, float)):
            return [float(payload)]
        return [float(value) for value in payload]
    if form == "csv":
        if field and not field.isdigit():
            rows = list(csv.DictReader(io.StringIO(text)))
            return [float(row[field]) for row in rows]
        rows = list(csv.reader(io.StringIO(text)))
        column = int(field) if field else 0
        start = 1 if rows and not _looks_number(rows[0][column]) else 0
        return [float(row[column]) for row in rows[start:] if row and row[column].strip()]
    if form == "bytes":
        return [float(byte) for byte in text.encode("utf-8")]
    return [float(match) for match in _FLOAT.findall(text)]


def _dig(payload, field: str):
    for part in field.split("."):
        if isinstance(payload, list):
            payload = payload[int(part)]
        else:
            payload = payload[part]
    return payload


def _scale(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _looks_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _frame_detail(image: Image.Image, draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], plot: Plot, ink: Color) -> None:
    left, top, right, bottom = frame
    colour = _ink_rgb(ink)
    dim = (max(20, ink.r // 2), max(12, ink.g // 3), max(0, ink.b // 4))
    kind = plot.border
    if kind == "none":
        return
    draw.rectangle((left, top, right, bottom), outline=colour, width=1)
    draw.rectangle((left + 3, top + 3, right - 3, bottom - 3), outline=dim, width=1)
    try:
        font = ImageFont.truetype(_FONT, 12)
        tiny = ImageFont.truetype(_FONT, 11)
    except OSError:
        font = ImageFont.load_default()
        tiny = font
    if plot.caption:
        draw.text((left, max(0, top - 16)), plot.caption, font=tiny, fill=dim)
    if plot.aside:
        wide = draw.textlength(plot.aside, font=tiny)
        draw.text((right - wide, max(0, top - 16)), plot.aside, font=tiny, fill=dim)
    if kind != "ticks":
        return
    step_x = max(18, (right - left) // max(1, len(plot.x_ticks) or 8))
    step_y = max(16, (bottom - top) // 6)
    labels = list(plot.x_ticks)
    mark = 0
    x = left + step_x
    while x < right - 4:
        draw.line((x, top, x, top + 5), fill=colour)
        draw.line((x, bottom, x, bottom - 5), fill=colour)
        if labels:
            text = labels[mark % len(labels)]
            draw.text((x - 4, bottom + 4), text, font=tiny, fill=dim)
            mark += 1
        x += step_x
    y = top + step_y
    while y < bottom - 4:
        draw.line((left, y, left + 5, y), fill=colour)
        draw.line((right, y, right - 5, y), fill=colour)
        y += step_y
    if plot.x_axis:
        wide = draw.textlength(plot.x_axis, font=font)
        draw.text(((left + right - wide) / 2, bottom + 14), plot.x_axis, font=font, fill=colour)
    if plot.y_axis:
        _vertical_text(image, plot.y_axis, 2, int((top + bottom) / 2), font, colour)


def _vertical_text(image: Image.Image, text: str, x: int, y: int, font, fill: tuple[int, int, int]) -> None:
    width = int(font.getlength(text)) + 4
    scratch = Image.new("RGBA", (width, 18), (0, 0, 0, 0))
    ImageDraw.Draw(scratch).text((0, 0), text, font=font, fill=fill + (255,))
    turned = scratch.rotate(90, expand=True)
    image.paste(turned, (x, max(0, y - turned.height // 2)), turned)


def _border(draw: ImageDraw.ImageDraw, width: int, height: int, kind: str, ink: Color) -> None:
    if kind not in BORDERS or kind == "none" or width < 3 or height < 3:
        return
    colour = _ink_rgb(ink)
    draw.rectangle((1, 1, width - 2, height - 2), outline=colour)
    if kind != "ticks":
        return
    step_x = max(14, width // 14)
    step_y = max(14, height // 8)
    for x in range(step_x, width - 2, step_x):
        draw.line((x, 1, x, 6), fill=colour)
        draw.line((x, height - 2, x, height - 7), fill=colour)
    for y in range(step_y, height - 2, step_y):
        draw.line((1, y, 6, y), fill=colour)
        draw.line((width - 2, y, width - 7, y), fill=colour)


def _ink_rgb(ink: Color) -> tuple[int, int, int]:
    return (ink.r, ink.g, ink.b)


def _notice(width: int, height: int, message: str) -> Image.Image:
    image = Image.new("RGB", (max(1, width), max(1, height)), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(_FONT, 14)
    except OSError:
        font = ImageFont.load_default()
    draw.text((8, 8), message, font=font, fill=(46, 120, 96))
    return image
