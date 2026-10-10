"""The Phosphor language, and the page for looking at it.

One ink on black. Plates, readouts, hairlines, and a trace. A second colour
belongs to the next language.
"""

from __future__ import annotations

from pathlib import Path

import math
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw, ImageFont

from meowtext.grid import Color

INK = Color(150, 255, 214)
DIM = Color(46, 120, 96)
PAPER = Color(0, 0, 0)
BASE_W, BASE_H = 960, 560

# Faces for the letters on the page. The default is the one the first panel used.
FONTS: dict[str, tuple[str, str]] = {
    "dejavu": ("DejaVu Sans Mono", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    "liberation": ("Liberation Mono", "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
    "hack": ("Hack", "/usr/share/fonts/truetype/hack/Hack-Regular.ttf"),
    "noto": ("Noto Sans Mono", "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"),
    "freemono": ("FreeMono", "/usr/share/fonts/truetype/freefont/FreeMono.ttf"),
    "terminus": ("Terminess", str(Path.home() / ".local/share/fonts/TerminessNerdFontMono-Regular.ttf")),
}
SCALES: dict[str, float] = {"low": 0.5, "screen": 1.0, "sharp": 2.0}
TEXTURES = ("none", "graph", "plus", "both")
GLOWS = {"none": 0.0, "soft": 0.42, "strong": 0.9}
# Fraction of the whole page the slot occupies. The drawing is scaled to fit
# inside that rectangle, so a split does not stretch the trace.
SLOTS: dict[str, tuple[float, float]] = {
    "whole": (1.0, 1.0),
    "half-width": (0.5, 1.0),
    "half-height": (1.0, 0.5),
    "quarter": (0.5, 0.5),
}


@dataclass(frozen=True, slots=True)
class PhosphorView:
    """One phosphor page. Other TUIs pass this and get back a picture.

    ``border`` frames the wave. ``font`` is a key in :data:`FONTS`. ``scale``
    is ``low``, ``screen``, or ``sharp``. ``texture`` sits under the trace:
    ``graph`` lines, ``plus`` marks, ``both``, or ``none``. ``slot`` is how
    the page is cut when more panels share the screen. ``width`` and
    ``height``, when both are set, are the exact pixel rectangle a host gave
    this view. The page is scaled evenly to fit that rectangle.
    """

    border: bool = False
    font: str = "dejavu"
    scale: str = "screen"
    texture: str = "none"
    slot: str = "whole"
    width: int | None = None
    height: int | None = None
    glow: str = "soft"


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    path: str
    taking: str


# Pictures marked Include that are actually one ink on black.
SOURCES: tuple[Source, ...] = (
    Source(
        "Gene code",
        str(Path.home() / "data/programming/tui-research/tui-inspo/3a6f9c32671bc19d9735e41585f91046.jpg"),
        "One green. A plate across the top, readouts in boxes, a trace running down the side.",
    ),
    Source(
        "Echoes of the Extinct",
        str(Path.home() / "data/programming/tui-research/tui-inspo/12071f86cbb11750a1bde8c4d4d25e20.jpg"),
        "The same green, used as an engraving. Letters and lines are one weight of light.",
    ),
    Source(
        "Waveform",
        str(Path.home() / "data/programming/tui-research/tui-inspo/87fcecd9bf78fafea642900b2ede503b.jpg"),
        "A glass tube. The trace is one line, bright, and the page title sits in a solid bar.",
    ),
    Source(
        "Oxide rack",
        str(Path.home() / "data/programming/kepler-terminal/aesthetic-inspo/533324780897578318_1.png"),
        "Construction lines. Dashed, thin, and the same green as the labels.",
    ),
    Source(
        "Amber plot",
        str(Path.home() / "data/programming/tui-research/tui-inspo/cb4e9f91640c37d7580988d352b8dee1.jpg"),
        "The same language in an amber tube. Still one ink. A frame, axes, and a field of points.",
    ),
    Source(
        "Amber radial",
        str(Path.home() / "data/programming/tui-research/tui-inspo/97bddbd6caddb1c9011908698c11c2fc.jpg"),
        "One ink again. Corner marks, and a circle made of ruled lines rather than a shaded dial.",
    ),
)

# Held back. Two inks, or a picture of a desktop. They belong to a later language.
HELD: tuple[Source, ...] = (
    Source(
        "Access node",
        str(Path.home() / "data/programming/tui-research/tui-inspo/514606000-2a2248cbe83a408d7f8d8e45dba0a47fff23e783acbbbc82fba8c84fbf5c3f65-d.webp"),
        "Yellow and cyan together. That is the instrument panel, not phosphor.",
    ),
    Source(
        "Colony ship",
        str(Path.home() / "data/programming/tui-research/tui-inspo/be6853b016fbf72dac25e23d92bf570b.jpg"),
        "Several inks on one map. Later.",
    ),
    Source(
        "Fastfetch",
        str(Path.home() / "data/programming/tui-research/tui-inspo/8b98642662e4a511d55fec8afe588e29.jpg"),
        "A desktop with a row of colour swatches. The green is only one of them.",
    ),
)


def phosphor_panel(view: PhosphorView | None = None, **options) -> Image.Image:
    """A page in one green, fitted to its slot without stretching.

    The trace, the plate, and the letters keep their ratio. Spare space in a
    short or narrow slot stays black.
    """

    view = view or PhosphorView(**options)
    canvas_w, canvas_h = _canvas_size(view)
    scale = min(canvas_w / BASE_W, canvas_h / BASE_H)
    content = _draw(view, scale)
    if content.size == (canvas_w, canvas_h):
        canvas = content
    else:
        canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
        canvas.paste(content, ((canvas_w - content.width) // 2, (canvas_h - content.height) // 2))
    from meowtext.panels import bloom

    return bloom(canvas, GLOWS.get(view.glow, GLOWS["soft"]))


def _canvas_size(view: PhosphorView) -> tuple[int, int]:
    if view.width and view.height:
        return max(1, view.width), max(1, view.height)
    res = SCALES.get(view.scale, 1.0)
    fraction_w, fraction_h = SLOTS.get(view.slot, (1.0, 1.0))
    return max(1, int(round(BASE_W * res * fraction_w))), max(1, int(round(BASE_H * res * fraction_h)))


def _draw(view: PhosphorView, scale: float) -> Image.Image:
    """The page itself, at ``scale`` times the 960 by 560 design."""

    width, height = max(1, int(BASE_W * scale)), max(1, int(BASE_H * scale))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    face = view.font if view.font in FONTS else "dejavu"
    title = _font(face, _px(22, scale))
    body = _font(face, _px(16, scale))
    small = _font(face, _px(13, scale))
    hair = max(1, round(scale))

    _plate(draw, _px(150, scale), _px(28, scale), _px(660, scale), _px(36, scale), "PAGE D READY", title)
    _label(draw, _px(36, scale), _px(34, scale), "INDEX", small, DIM)
    _readout(draw, _px(830, scale), _px(30, scale), "VOICE", "6", body)
    _readout(draw, _px(830, scale), _px(58, scale), "MODE", "4", body)

    _centered(draw, width, _px(84, scale), "WAVEFORM DISPLAY", body, DIM)
    draw.line((_px(36, scale), _px(116, scale), width - _px(36, scale), _px(116, scale)), fill=_rgba(DIM), width=hair)

    _frame(draw, _px(36, scale), _px(132, scale), width - _px(72, scale), _px(36, scale), hair)
    _label(
        draw,
        _px(52, scale),
        _px(140, scale),
        "DISPLAY   FORMAT A  B    END SEG  128  64  32    STEP  8",
        small,
        INK,
    )

    box = (_px(48, scale), _px(190, scale), width - _px(48, scale), height - _px(28, scale))
    _texture(draw, box, view.texture, scale)
    _trace(draw, box[0] + _px(22, scale), box[1] + _px(12, scale), box[2] - box[0] - _px(44, scale), box[3] - box[1] - _px(24, scale), scale)
    if view.border:
        _frame(draw, box[0], box[1], box[2] - box[0], box[3] - box[1], hair)
    flat = Image.new("RGB", image.size, (0, 0, 0))
    flat.paste(image, mask=image.getchannel("A"))
    return flat


def view_from_query(query: dict[str, list[str]]) -> PhosphorView:
    """Read a review-page query into a view. Unknown values fall back."""

    def first(name: str, default: str) -> str:
        values = query.get(name)
        return values[0] if values else default

    border = first("border", "") in {"1", "on", "true"}
    font = first("font", "dejavu")
    scale = first("scale", "screen")
    texture = first("texture", "none")
    slot = first("slot", "whole")
    return PhosphorView(
        border=border,
        font=font if font in FONTS else "dejavu",
        scale=scale if scale in SCALES else "screen",
        texture=texture if texture in TEXTURES else "none",
        slot=slot if slot in SLOTS else "whole",
        glow=first("glow", "soft") if first("glow", "soft") in GLOWS else "soft",
    )


def page() -> str:
    """One page: the pictures, then the panel made from them."""

    cards = []
    for index, source in enumerate(SOURCES):
        cards.append(
            f"""<figure>
  <img src="/src?n={index}" alt="">
  <figcaption><b>{_esc(source.title)}</b>{_esc(source.taking)}</figcaption>
</figure>"""
        )
    held = []
    for index, source in enumerate(HELD):
        held.append(
            f"""<li><b>{_esc(source.title)}</b> {_esc(source.taking)}</li>"""
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phosphor</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; background: #000; color: #d7d4cc; font: 17px/1.45 "IBM Plex Sans", "Source Sans 3", sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.2rem 4rem; }}
  h1 {{ font-weight: 560; font-size: 1.8rem; margin: 0 0 0.4rem; }}
  h2 {{ font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; color: #8d887c; margin: 2.4rem 0 0.8rem; }}
  p.lede {{ max-width: 40rem; color: #a39e92; margin: 0; }}
  .sources {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; margin-top: 1.4rem; }}
  figure {{ margin: 0; }}
  img {{ width: 100%; height: auto; background: #000; display: block; }}
  figcaption {{ margin-top: 0.45rem; color: #a39e92; font-size: 0.92rem; }}
  figcaption b {{ display: block; color: #f2efe6; font-weight: 600; margin-bottom: 0.15rem; }}
  .panel img {{ width: 100%; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 0.8rem 1.4rem; align-items: center; margin: 0 0 0.8rem; }}
  .controls label {{ color: #c8c2b6; font-size: 0.95rem; }}
  select {{ background: #111; color: #f2efe6; border: 1px solid #333; padding: 0.25rem 0.4rem; font: inherit; }}
  pre.definition {{ background: #0c0c0c; color: #c8c2b6; padding: 0.8rem 1rem; overflow: auto; font: 14px/1.45 "DejaVu Sans Mono", monospace; }}
  pre.helix {{ margin: 0; color: #9dffd8; background: #000; font: 13px/1.05 "Terminess", "DejaVu Sans Mono", monospace; white-space: pre; }}
  ul {{ padding-left: 1.1rem; color: #8d887c; }}
  li {{ margin: 0.35rem 0; }}
  li b {{ color: #c8c2b6; }}
  @media (max-width: 800px) {{ .sources {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
  <h1>Phosphor</h1>
  <p class="lede">One ink on black. The light is the information. These six pictures are the ones I am using. The panel under them is the language taken from them.</p>
  <h2>Pictures</h2>
  <div class="sources">
    {"".join(cards)}
  </div>
  <h2>The view</h2>
  <form class="controls" id="view">
    <label><input type="checkbox" name="border"> Border on the wave</label>
    <label>Font <select name="font">{_options(FONTS, "dejavu")}</select></label>
    <label>Resolution <select name="scale">{_options({"low": "Low", "screen": "Screen", "sharp": "Sharp"}, "screen")}</select></label>
    <label>Under the wave <select name="texture">{_options({"none": "Nothing", "graph": "Graph lines", "plus": "Plus marks", "both": "Lines and pluses"}, "none")}</select></label>
    <label>Slot <select name="slot">{_options({"whole": "Whole", "half-width": "Side by side", "half-height": "Stacked", "quarter": "Four panels"}, "whole")}</select></label>
    <label>Glow <select name="glow">{_options({"none": "None", "soft": "Soft", "strong": "Strong"}, "soft")}</select></label>
  </form>
  <div class="panel"><img id="panel" src="/panel.png" alt="A phosphor page: one green, a plate, readouts, and a trace"></div>
  <script>
    const form = document.getElementById("view");
    const panel = document.getElementById("panel");
    function show() {{
      const query = new URLSearchParams();
      if (form.border.checked) query.set("border", "1");
      query.set("font", form.font.value);
      query.set("scale", form.scale.value);
      query.set("texture", form.texture.value);
      query.set("slot", form.slot.value);
      query.set("glow", form.glow.value);
      panel.src = "/panel.png?" + query.toString();
    }}
    form.addEventListener("change", show);
  </script>
  <h2>Elements</h2>
  <p class="lede">The other parts of that green poster. An image is fitted, then turned one green. The rest are panels: a cropped SVG, a helix you can scan, data drawn a few ways, a four-way readout, and an equalizer.</p>
  <form class="controls" id="elements">
    <label><input type="checkbox" name="levels"> Auto levels</label>
    <label><input type="checkbox" name="negative"> Negative</label>
    <label><input type="checkbox" name="dither"> Dither</label>
    <label>Scan <input type="range" name="scan" min="0" max="100" value="35"></label>
    <label>Data <select name="mode">{_options({"glyphs": "Glyphs", "cells": "Cells", "array": "Array", "dial": "Dial", "gauge": "Gauge"}, "cells")}</select></label>
    <label>Plot border <select name="amberBorder">{_options({"none": "None", "box": "Box", "ticks": "Ticks"}, "ticks")}</select></label>
  </form>
  <div class="sources">
    <figure>
      <img id="eye" src="/eye.png" alt="The eye, fitted and turned green">
      <figcaption><b>Image</b>Crop to the panel, greyscale, then this green. Bake a file into the TUI, or leave the slot empty and the person running it picks one.</figcaption>
    </figure>
    <figure>
      <img id="slot" src="/slot.png" alt="An empty image slot">
      <figcaption><b>Open slot</b>No file was baked. The running TUI asks for one.</figcaption>
    </figure>
    <figure>
      <img src="/svg.png" alt="A cropped SVG in one green">
      <figcaption><b>SVG</b>Drawn at its own size, then a crop of it is fitted to the panel.</figcaption>
    </figure>
    <figure>
      <pre id="helix" class="helix">loading the helix…</pre>
      <figcaption><b>Helix</b>Each row is one base pair from 1BNA, on a right-handed screw. Count ten rows and the same rung is back. @ is the sequence strand and # is its complement; the lighter mark is that strand passing behind. A·T has two bonds and G·C has three. The rung marked &gt; faces you, and scan turns the column.</figcaption>
    </figure>
    <figure>
      <img id="data" src="/data.png?mode=cells" alt="Data drawn as cells">
      <figcaption><b>Data</b>The same numbers as glyphs, cells, an array, a dial, or a gauge.</figcaption>
    </figure>
    <figure>
      <img src="/selector.png" alt="Four readouts, one lit">
      <figcaption><b>Selector</b>Four options. One is the lit readout.</figcaption>
    </figure>
    <figure>
      <img src="/eq.png" alt="Equalizer bars">
      <figcaption><b>Equalizer</b>Bars in the shape cava draws. A live TUI can feed cava's levels into it while the letters are being made.</figcaption>
    </figure>
    <figure>
      <img id="amber" src="/amber.png?border=ticks" alt="Amber plot: a ticked frame, curves of points, and columns of points">
      <figcaption><b>Amber plot</b>A flat CRT frame. Arcs leave a hot cusp. Columns of points sit under a bright ridge and cool toward the baseline.</figcaption>
    </figure>
    <figure>
      <img src="/readout.png" alt="A panel drawn from a readout definition">
      <figcaption><b>Readout</b>This one is drawn from a definition file. The style, the range, the format, and the place it points at are all in that file.</figcaption>
    </figure>
  </div>
  <pre class="definition">{_esc(_definition_text())}</pre>
  <pre class="definition">{_esc(_plot_text())}</pre>
  <script>
    const elements = document.getElementById("elements");
    const eye = document.getElementById("eye");
    const helix = document.getElementById("helix");
    const data = document.getElementById("data");
    function showElements() {{
      const image = new URLSearchParams();
      if (elements.levels.checked) image.set("levels", "1");
      if (elements.negative.checked) image.set("negative", "1");
      if (elements.dither.checked) image.set("dither", "1");
      eye.src = "/eye.png?" + image.toString();
      fetch("/helix.txt?scan=" + (Number(elements.scan.value) / 100)).then((response) => response.text()).then((text) => {{ helix.textContent = text; }});
      data.src = "/data.png?mode=" + elements.mode.value;
      document.getElementById("amber").src = "/amber.png?border=" + elements.amberBorder.value;
    }}
    elements.addEventListener("input", showElements);
    elements.addEventListener("change", showElements);
    showElements();
  </script>
  <h2>Held for the next language</h2>
  <ul>
    {"".join(held)}
  </ul>
</main>
</body>
</html>
"""


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    allowed = {source.path: index for index, source in enumerate(SOURCES)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = page().encode("utf-8")
                self._send(200, "text/html; charset=utf-8", body)
                return
            if parsed.path == "/panel.png":
                buffer = BytesIO()
                phosphor_panel(view_from_query(parse_qs(parsed.query))).save(buffer, format="PNG")
                self._send(200, "image/png", buffer.getvalue())
                return
            if parsed.path == "/helix.txt":
                from meowtext.dna import render_ascii

                try:
                    scan = float(parse_qs(parsed.query).get("scan", ["0"])[0])
                except ValueError:
                    scan = 0
                body = render_ascii("CGCGAATTCGCG", scan, turns=2).encode("utf-8")
                self._send(200, "text/plain; charset=utf-8", body)
                return
            if parsed.path in {"/eye.png", "/slot.png", "/svg.png", "/data.png", "/selector.png", "/eq.png", "/readout.png", "/amber.png"}:
                self._send(200, "image/png", _element_png(parsed.path, parse_qs(parsed.query)))
                return
            if parsed.path == "/src":
                try:
                    number = int(parse_qs(parsed.query).get("n", ["-1"])[0])
                    source = SOURCES[number]
                except (ValueError, IndexError):
                    self._send(404, "text/plain", b"not found")
                    return
                if source.path not in allowed:
                    self._send(404, "text/plain", b"not found")
                    return
                data = open(source.path, "rb").read()
                kind = "image/png" if source.path.endswith(".png") else "image/jpeg"
                if source.path.endswith(".webp"):
                    kind = "image/webp"
                self._send(200, kind, data)
                return
            self._send(404, "text/plain", b"not found")

        def _send(self, status: int, mime: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Phosphor  http://{host}:{port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


def _px(value: float, scale: float) -> int:
    return max(1, int(round(value * scale)))


def _font(name: str, size: int) -> ImageFont.ImageFont:
    path = FONTS.get(name, FONTS["dejavu"])[1]
    try:
        return ImageFont.truetype(path, max(1, size))
    except OSError:
        return ImageFont.load_default()


def _rgba(ink: Color, alpha: int = 255) -> tuple[int, int, int, int]:
    return (ink.r, ink.g, ink.b, alpha)


def _plate(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, label: str, font) -> None:
    draw.rectangle((x, y, x + width, y + height), fill=_rgba(INK))
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x + (width - tw) / 2, y + (height - th) / 2 - bbox[1]), label, font=font, fill=(0, 0, 0, 255))


def _label(draw, x, y, message, font, ink: Color) -> None:
    draw.text((x, y), message, font=font, fill=_rgba(ink))


def _centered(draw, width, y, message, font, ink: Color) -> None:
    bbox = draw.textbbox((0, 0), message, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2, y), message, font=font, fill=_rgba(ink))


def _readout(draw, x, y, name, value, font) -> None:
    _label(draw, x, y, name, font, DIM)
    gap = draw.textbbox((0, 0), name + "  ", font=font)
    _label(draw, x + gap[2] - gap[0], y, value, font, INK)


def _frame(draw, x, y, width, height, weight: int = 1) -> None:
    draw.rectangle((x, y, x + width, y + height), outline=_rgba(INK), width=weight)


def _texture(draw, box: tuple[int, int, int, int], kind: str, scale: float) -> None:
    if kind not in TEXTURES or kind == "none":
        return
    left, top, right, bottom = box
    step = _px(34, scale)
    ink = _rgba(DIM)
    if kind in {"graph", "both"}:
        y = top + step
        while y < bottom:
            draw.line((left, y, right, y), fill=ink, width=max(1, round(scale)))
            y += step
        x = left + step
        while x < right:
            draw.line((x, top, x, bottom), fill=ink, width=max(1, round(scale)))
            x += step
    if kind in {"plus", "both"}:
        arm = _px(4, scale)
        y = top + step // 2
        while y < bottom - arm:
            x = left + step
            while x < right - arm:
                draw.line((x - arm, y, x + arm, y), fill=ink, width=max(1, round(scale)))
                draw.line((x, y - arm, x, y + arm), fill=ink, width=max(1, round(scale)))
                x += step
            y += step


def _trace(draw, x: int, y: int, width: int, height: int, scale: float = 1) -> None:
    """Ordered lines at the back, a tangle at the front. One green."""

    rows = 26
    for index in range(rows):
        t = index / (rows - 1)
        line_y = y + 18 + t * (height - 36)
        left = x + 30 + t * 50
        right = x + width * 0.62 + t * width * 0.28
        tangle = t ** 2
        points = []
        steps = 90
        for step in range(steps):
            u = step / (steps - 1)
            px = left + (right - left) * u
            wave = math.sin(u * 22 + index * 0.7) * (6 + 34 * tangle)
            jag = math.sin(u * 70 + index * 3.1) * 10 * tangle
            py = min(y + height - 2, max(y + 2, line_y + (wave + jag) * tangle))
            points.append((px, py))
        draw.line(points, fill=_rgba(INK, 70), width=max(1, round(3 * scale)))
        draw.line(points, fill=_rgba(INK, 230), width=max(1, round(scale)))


def _options(choices: dict[str, str] | dict[str, tuple[str, str]], selected: str) -> str:
    parts = []
    for key, label in choices.items():
        name = label[0] if isinstance(label, tuple) else label
        mark = " selected" if key == selected else ""
        parts.append(f'<option value="{_esc(key)}"{mark}>{_esc(name)}</option>')
    return "".join(parts)


EYE = str(Path.home() / "data/programming/tui-research/tui-inspo/9cb5a6d225f908867b31514ec42ae3c4.jpg")
_MARK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="36" fill="none" stroke="#fff" stroke-width="6"/>
  <rect x="28" y="28" width="44" height="44" fill="none" stroke="#fff" stroke-width="4"/>
  <circle cx="50" cy="50" r="6" fill="#fff"/>
</svg>"""


def _definition_text() -> str:
    from meowtext.readout import EXAMPLE

    return EXAMPLE.read_text(encoding="utf-8").rstrip()


def _plot_text() -> str:
    from meowtext.readout import EXAMPLE

    return (EXAMPLE.parent / "amber-plot.json").read_text(encoding="utf-8").rstrip()


def _flag(query: dict[str, list[str]], name: str) -> bool:
    return query.get(name, [""])[0] in {"1", "on", "true"}


def _element_png(path: str, query: dict[str, list[str]]) -> bytes:
    from meowtext.panels import render_data, render_equalizer, render_image, render_selector, render_svg

    if path == "/eye.png":
        image = render_image(
            EYE,
            360,
            240,
            auto_levels=_flag(query, "levels"),
            negative=_flag(query, "negative"),
            dither=_flag(query, "dither"),
        )
    elif path == "/slot.png":
        image = render_image(None, 360, 120)
    elif path == "/svg.png":
        image = render_svg(_MARK, 240, 240, crop=(0.15, 0.15, 0.85, 0.85))
    elif path == "/helix.png":
        image = render_image(None, 8, 8)
    elif path == "/data.png":
        mode = query.get("mode", ["cells"])[0]
        image = render_data([0.15, 0.4, 0.55, 0.8, 0.35, 0.9, 0.2, 0.6, 0.45], mode, 360, 180)
    elif path == "/selector.png":
        image = render_selector(("FORMAT A", "FORMAT B", "END SEG", "STEP"), 0, 280, 140)
    elif path == "/readout.png":
        from meowtext.readout import EXAMPLE, load_readout, render_readout

        image = render_readout(load_readout(EXAMPLE), 360, 180)
    elif path == "/amber.png":
        from meowtext.readout import EXAMPLE, load_plot, render_plot

        plot = load_plot(EXAMPLE.parent / "amber-plot.json")
        border = query.get("border", [plot.border])[0]
        if border not in {"none", "box", "ticks"}:
            border = plot.border
        image = render_plot(type(plot)(plot.name, plot.ink, border, plot.readouts), 520, 360)
    else:
        image = render_equalizer([0.2, 0.45, 0.7, 0.9, 0.55, 0.3, 0.65, 0.4, 0.85, 0.25, 0.5, 0.35], 360, 140)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    serve()
