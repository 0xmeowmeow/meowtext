"""Complete playback exports made by the same compositor as the editor.

HTML cycles colours on real text cells. APNG and Kitty retain lossless pixels;
GIF shares a 256-colour palette. Each format uses the same animation timeline.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from fractions import Fraction
from io import BytesIO

from meowtext.compose import present
from meowtext.effects import Animation, LIGHT_MOTIONS, trace_plan
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
    if name == "trace":
        steps = trace_plan(grid, motion.pattern).steps
        if motion.direction == "pingpong":
            # Sample the turnaround exactly, including at fractional speeds.
            period = 2 * max(1, steps - 1) / speed
            count = 2 * max(1, math.ceil(period / 2))
            if count > MAX_FRAMES:
                raise RenderError("This animation cycle exceeds 720 frames. Increase motion speed before exporting animation.")
            return Timeline(count, period / count, FRAME_MS * period / count, True)
        if motion.reveal == "runner":
            period = steps / speed
        else:
            count = max(1, math.ceil((steps - 1) / speed) + 1)
            if count > MAX_FRAMES:
                raise RenderError("This reveal exceeds 720 frames. Increase motion speed or choose a smaller font before exporting animation.")
            return Timeline(count, 1, FRAME_MS, False)
    elif motion.direction == "pingpong":
        period = 48 / speed
    elif name in {"hue", "march"}:
        base = max(1, min(360, motion.travel)) / 12 if name == "hue" else 24
        periods = []
        if motion.layers != "outline":
            periods.append(base)
        if motion.layers in {"outline", "all"}:
            periods.append(base / (outline_speed if outline_speed > 0 else 1))
        period = _common_period(periods) / speed
    elif name in LIGHT_MOTIONS:
        period = LIGHT_MOTIONS[name] / speed
    elif name == "pulse":
        period = 5 * math.pi / speed
    elif name == "sparkle":
        period = 11 / speed
    elif name == "scan":
        period = (grid.width + 6) / speed
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
    if fmt not in {"html", "apng", "gif", "kitty"} or project.animation.name == "none":
        return export(current, fmt)
    complete = render(0, Animation())
    plan = timeline(complete, project.animation, project.style.outline_speed)
    # Bound memory before allocating image sequences. Never silently drop frames.
    from meowtext.raster import cell_size
    cw, ch = cell_size(18)
    pixels = max(1, complete.width * cw) * max(1, complete.height * ch)
    if pixels * plan.count > (60_000_000 if fmt in {"apng", "gif"} else 240_000_000):
        raise RenderError("This animation is too large to export at full fidelity. Shorten the text or increase motion speed, or choose a PNG still.")
    if fmt == "html":
        frames = []
        for i in range(plan.count):
            frames.append(render(i * plan.step))
            if progress:
                progress(i + 1, plan.count)
        return html_player(frames, complete, plan)
    if fmt == "kitty":
        frames = []
        for i in range(plan.count):
            frames.append(to_png(render(i * plan.step)))
            if progress:
                progress(i + 1, plan.count)
        return kitty_player(frames, plan)
    images = []
    for i in range(plan.count):
        images.append(rasterize(render(i * plan.step)))
        if progress:
            progress(i + 1, plan.count)
    if fmt == "gif":
        return gif_player(images, plan)
    output = BytesIO()
    images[0].save(output, format="PNG", save_all=True, append_images=images[1:],
                   duration=plan.duration, loop=0 if plan.loop else 1,
                   disposal=0, blend=0)
    return output.getvalue()


def gif_player(images, plan: Timeline) -> bytes:
    """One stable 256-colour palette, with GIF's centisecond clock.

    A shared palette prevents each frame independently changing the artwork's
    colours. Carry timing rounding forward so a long cycle does not drift.
    Omit the repeat extension for one-shot traces: GIF loop=1 repeats twice.
    """
    from PIL import Image
    samples = Image.new("RGB", (64, 64*len(images)))
    for i, picture in enumerate(images):
        sample = picture.copy()
        sample.thumbnail((64,64), Image.Resampling.NEAREST)
        samples.paste(sample, (0,64*i))
    palette = samples.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    frames = [picture.quantize(palette=palette, dither=Image.Dither.NONE) for picture in images]
    durations, previous = [], 0
    for i in range(len(frames)):
        end = max(previous+1, round((i+1)*plan.duration/10))
        durations.append((end-previous)*10)
        previous = end
    output = BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, disposal=2, optimize=False,
                   **({"loop":0} if plan.loop and len(frames)>1 else {}))
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



# Public compatibility name; the player now cycles colours on HTML text cells.
from meowtext.html_export import html_player
