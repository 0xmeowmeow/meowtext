"""Command line. With no subcommand, open the TUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meowtext import __version__
from meowtext.catalog import canonical, list_fonts
from meowtext.compose import render_banner
from meowtext.effects import OUTLINE_MODES, PALETTES, PRESETS, BannerStyle
from meowtext.errors import MeowTextError, RenderError
from meowtext.export import FORMATS, export
from meowtext.grid import Color

_SUFFIXES = {
    ".ans": "ansi",
    ".ansi": "ansi",
    ".txt": "plain",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".png": "png",
    ".kitty": "kitty",
    ".irc": "irc",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meowtext",
        description="Decorate text with FIGlet, TOIlet, and TheDraw fonts.",
    )
    parser.add_argument("--version", action="version", version=f"meowtext {__version__}")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("tui", help="open the banner editor (also the default)")

    render = commands.add_parser("render", help="render one banner")
    render.add_argument("text", nargs="*", help="banner text; joined with spaces")
    render.add_argument("-e", "--engine", default="figlet", help="figlet, toilet, or tdf")
    render.add_argument("-f", "--font", help="font name, or for TheDraw FILE or FILE::name")
    render.add_argument("-o", "--output", help="write here instead of stdout")
    render.add_argument("--format", choices=FORMATS, help="output format (default: from -o, else ansi)")
    render.add_argument("--preset", choices=tuple(PRESETS), default="plain")
    render.add_argument("--gradient", help="palette name, 'none', or #hex,#hex stops")
    render.add_argument("--direction", choices=("horizontal", "vertical", "diagonal"))
    render.add_argument("--outline", action="store_true")
    render.add_argument("--no-outline", action="store_true")
    render.add_argument("--outline-char", default=None)
    render.add_argument("--outline-color", default=None)
    render.add_argument("--outline-mode", choices=tuple(mode for _, mode in OUTLINE_MODES))
    render.add_argument("--outline-gradient", help="palette name for a gradient outline, or omit for a flat colour")
    render.add_argument("--shadow", action="store_true")
    render.add_argument("--no-shadow", action="store_true")
    render.add_argument("--shadow-dx", type=int)
    render.add_argument("--shadow-dy", type=int)
    render.add_argument("--shadow-color", default=None)
    render.add_argument("--shadow-char", default=None)
    render.add_argument("--hue", type=float, default=0, help="rotate TheDraw colour roles, in degrees")
    render.epilog = "palettes: " + ", ".join(PALETTES)

    fonts = commands.add_parser("fonts", help="list fonts")
    fonts.add_argument("-e", "--engine", default="figlet")
    fonts.add_argument("-q", "--query", default="")
    fonts.add_argument("-n", "--limit", type=int, default=200)

    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            return _render(args)
        if args.command == "fonts":
            return _fonts(args)
        from meowtext.tui import MeowText

        MeowText().run()
        return 0
    except MeowTextError as exc:
        print(f"meowtext: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


def _render(args: argparse.Namespace) -> int:
    if args.text:
        text = " ".join(args.text)
    elif sys.stdin.isatty():
        raise RenderError("give the banner text, or pipe it in")
    else:
        text = sys.stdin.read()
    style = _style_from_args(args)
    banner = render_banner(text, args.engine, args.font, style)
    fmt = args.format
    if fmt is None and args.output:
        fmt = _SUFFIXES.get(Path(args.output).suffix.lower(), "ansi")
    fmt = fmt or "ansi"
    data = export(banner.grid, fmt)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        return 0
    if isinstance(data, bytes):
        raise RenderError(f"{fmt} output needs -o path")
    sys.stdout.write(data)
    return 0


def _style_from_args(args: argparse.Namespace) -> BannerStyle:
    style = PRESETS[args.preset].clone()
    if args.gradient:
        style.gradient = None if args.gradient.lower() == "none" else args.gradient
    if args.direction:
        style.direction = args.direction
    if args.outline:
        style.outline = True
    if args.no_outline:
        style.outline = False
    if args.outline_char:
        style.outline_char = args.outline_char[:1]
    if args.outline_color:
        style.outline_color = Color.from_hex(args.outline_color)
    if args.outline_mode:
        style.outline_mode = args.outline_mode
    if args.outline_gradient:
        style.outline_gradient = None if args.outline_gradient == "off" else args.outline_gradient
        style.outline = True
    if args.shadow:
        style.shadow = True
    if args.no_shadow:
        style.shadow = False
    if args.shadow_dx is not None:
        style.shadow_dx = args.shadow_dx
    if args.shadow_dy is not None:
        style.shadow_dy = args.shadow_dy
    if args.shadow_color:
        style.shadow_color = Color.from_hex(args.shadow_color)
    if args.shadow_char:
        style.shadow_char = args.shadow_char[:1]
    if args.hue:
        style.hue = args.hue
    return style


def _fonts(args: argparse.Namespace) -> int:
    engine = canonical(args.engine)
    query = args.query.lower()
    shown = 0
    for font in list_fonts(engine):
        haystack = f"{font.name} {Path(font.source).name}".lower()
        if query and query not in haystack:
            continue
        if engine == "tdf":
            print(f"{Path(font.source).stem}\t{font.index}\t{font.kind}\t{font.name}")
        else:
            print(font.name)
        shown += 1
        if shown >= args.limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
