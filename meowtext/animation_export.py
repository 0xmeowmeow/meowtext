"""Lossless playback exports made by the same compositor as the editor.

HTML contains rendered frames, not browser-dependent approximations of ANSI
glyphs. No fonts, network connection or installed Meowtext are needed to play it.
"""

from __future__ import annotations

import base64
import html
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from io import BytesIO

from meowtext.compose import present
from meowtext.effects import Animation, _trace_order
from meowtext.errors import RenderError
from meowtext.grid import Grid
from meowtext.palette import RelationPalette

FRAME_MS = 120
MAX_FRAMES = 720


@dataclass(frozen=True)
class Timeline:
    count: int = 1
    step: float = 1
    duration: float = FRAME_MS
    loop: bool = True


def _common_period(periods):
    fractions = [Fraction(str(p)).limit_denominator(10000) for p in periods]
    return float(Fraction(math.lcm(*(p.numerator for p in fractions)),
                          math.gcd(*(p.denominator for p in fractions))))


def timeline(grid, motion, outline_speed=1.0):
    """One complete cycle, or an entire reveal ending on the finished artwork."""
    name = motion.name
    if name == "none":
        return Timeline()
    speed = motion.speed if motion.speed > 0 else 1
    loop = True
    if motion.direction == "pingpong":
        period = 48 / speed
    elif name in {"hue", "march"}:
        base = max(1, min(360, motion.travel)) / 12 if name == "hue" else 24
        periods = []
        if motion.layers != "outline":
            periods.append(base)
        if motion.layers in {"outline", "all"}:
            periods.append(base / (outline_speed if outline_speed > 0 else 1))
        period = _common_period(periods) / speed
    elif name == "pulse":
        period = 5 * math.pi / speed
    elif name == "sparkle":
        period = 11 / speed
    elif name == "scan":
        period = (grid.width + 6) / speed
    elif name == "trace":
        ink = len(_trace_order(grid, motion.pattern))
        if motion.reveal == "runner":
            period = max(1, ink) / speed
        else:
            # Include the fully drawn last frame; reveal is not a looping effect.
            count = max(1, math.ceil((ink - 1) / speed) + 1)
            if count > MAX_FRAMES:
                raise RenderError("This reveal exceeds 720 frames. Increase motion speed or shorten the text before exporting animation.")
            return Timeline(count, 1, FRAME_MS, False)
    else:
        raise RenderError(f"Animation {name!r} cannot be exported. Choose a supported motion or a still image.")
    count = max(2, math.ceil(period))
    if count > MAX_FRAMES:
        raise RenderError("This animation cycle exceeds 720 frames. Increase motion speed or simplify the border speed before exporting animation.")
    return Timeline(count, period / count, FRAME_MS * period / count, loop)


def export_design(source, project, fmt, frame=0, palette=None, progress=None):
    """Export a live design; stills use exactly the selected preview frame."""
    from meowtext.export import export, to_png
    from meowtext.raster import rasterize

    palette = palette or RelationPalette(hue=project.hue, roles=project.roles)

    def render(number, motion=project.animation):
        return present(source, project.style, palette, animation=motion,
                       frame=number, patches=project.patches)

    current = render(frame)
    if fmt not in {"html", "apng", "kitty"} or project.animation.name == "none":
        return export(current, fmt)
    complete = render(0, Animation())
    plan = timeline(complete, project.animation, project.style.outline_speed)
    # Bound memory before allocating image sequences. Never silently drop frames.
    from meowtext.raster import cell_size
    cw, ch = cell_size(18)
    pixels = max(1, complete.width * cw) * max(1, complete.height * ch)
    if pixels * plan.count > (60_000_000 if fmt == "apng" else 240_000_000):
        raise RenderError("This animation is too large to export at full fidelity. Shorten the text or increase motion speed, or choose a PNG still.")
    if fmt in {"html", "kitty"}:
        frames = []
        for i in range(plan.count):
            frames.append(to_png(render(i * plan.step)))
            if progress:
                progress(i + 1, plan.count)
        if fmt == "kitty":
            return kitty_player(frames, plan)
        return html_player(frames, complete, plan)
    images = []
    for i in range(plan.count):
        images.append(rasterize(render(i * plan.step)))
        if progress:
            progress(i + 1, plan.count)
    output = BytesIO()
    images[0].save(output, format="PNG", save_all=True, append_images=images[1:],
                   duration=plan.duration, loop=0 if plan.loop else 1,
                   disposal=0, blend=0)
    return output.getvalue()


def kitty_player(frames: list[bytes], plan: Timeline) -> str:
    """Upload once; Kitty owns the animation clock after the writer exits.

    https://sw.kovidgoyal.net/kitty/graphics-protocol/#animation
    Keep a unique image ID so exporting another design cannot replace artwork
    already displayed in the terminal. No global image deletion or cursor reset.
    """
    import secrets

    image_id = secrets.randbelow(0xFFFFFFFF) + 1
    gap = max(1, round(plan.duration))
    parts = []
    for index, png in enumerate(frames):
        action = "t" if index == 0 else "f"
        data = base64.b64encode(png).decode("ascii")
        for offset in range(0, len(data), 4096):
            more = int(offset + 4096 < len(data))
            control = f"a={action},i={image_id},q=2,m={more}"
            if offset == 0:
                control += ",f=100"
                if index:
                    control += f",z={gap}"
            parts.append(f"\x1b_G{control};{data[offset:offset+4096]}\x1b\\")
    # The root frame has no gap until explicitly set. Load all frames before
    # placing the image, so a slow pipe never exposes half an animation.
    parts.append(f"\x1b_Ga=a,i={image_id},r=1,z={gap},q=2;\x1b\\")
    parts.append(f"\x1b_Ga=p,i={image_id},q=2;\x1b\\")
    parts.append(f"\x1b_Ga=a,i={image_id},s=3,v={1 if plan.loop else 2},q=2;\x1b\\")
    return "".join(parts)


def html_player(frames: list[bytes], grid: Grid, plan: Timeline | None = None) -> str:
    from meowtext.export import to_plain
    plan = plan or Timeline()
    from meowtext.export import to_png
    urls = ["data:image/png;base64," + base64.b64encode(f).decode("ascii") for f in frames]
    poster = "data:image/png;base64," + base64.b64encode(to_png(grid)).decode("ascii")
    payload = json.dumps({"frames": urls, "duration": plan.duration, "loop": plan.loop}, separators=(",", ":"))
    alternative = html.escape(to_plain(grid))
    animated = len(frames) > 1
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meowtext artwork</title>
<style>
html{{color-scheme:dark;background:#000;color:#eee;font:14px system-ui}}
body{{margin:0;padding:16px}} #art{{display:block;max-width:100%;height:auto}}
nav{{display:flex;gap:8px;margin-top:16px}} button{{font:inherit;padding:8px 14px;cursor:pointer}}
details{{margin-top:16px}} pre{{overflow:auto;white-space:pre;font-family:monospace}}
[hidden]{{display:none!important}}
</style>
<img id="art" src="{poster}" alt="Meowtext artwork; text alternative below">
<nav {'hidden' if not animated else ''}><button id="pause" type="button">Pause</button><button id="replay" type="button">Replay</button><span id="state" role="status"></span></nav>
<details><summary>Text alternative (colours are in the artwork above)</summary><pre><span>{alternative}</span></pre></details>
<noscript>Animation needs JavaScript. The complete still artwork is shown above.</noscript>
<script id="meowtext-frames" type="application/json">{payload}</script>
<script>
const data = JSON.parse(document.getElementById('meowtext-frames').textContent);
const art = document.getElementById('art'), pause = document.getElementById('pause'), state = document.getElementById('state');
let index = 0, running = data.frames.length > 1 && !matchMedia('(prefers-reduced-motion: reduce)').matches;
let elapsed = 0, last = performance.now();
if (running) art.src = data.frames[0];
function label() {{ pause.textContent = running ? 'Pause' : 'Play'; state.textContent = running ? 'Playing' : 'Paused'; }}
pause.onclick = () => {{ running = !running; last = performance.now(); label(); }};
document.getElementById('replay').onclick = () => {{ index = 0; elapsed = 0; art.src = data.frames[0]; running = data.frames.length > 1; last = performance.now(); label(); }};
document.addEventListener('visibilitychange', () => {{ last = performance.now(); }});
function tick(now) {{
  if (running && !document.hidden) {{
    elapsed += now - last;
    if (elapsed >= data.duration) {{
      index += Math.floor(elapsed / data.duration); elapsed %= data.duration;
      if (!data.loop && index >= data.frames.length - 1) {{ index = data.frames.length - 1; running = false; label(); }}
      else index %= data.frames.length;
      art.src = data.frames[index];
    }}
  }}
  last = now; requestAnimationFrame(tick);
}}
label(); requestAnimationFrame(tick);
</script></html>'''
