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
from meowtext.export import FORMATS, export, export_notice
from meowtext.grid import Color

_SUFFIXES = {
    ".ans": "ansi",
    ".ansi": "ansi",
    ".txt": "plain",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".png": "png",
    ".apng": "apng",
    ".gif": "gif",
    ".kitty": "kitty",
    ".irc": "irc",
    ".md": "markdown",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    project: Path | None = None
    if len(argv) == 1 and argv[0].endswith(".meowtext") and not argv[0].startswith("-"):
        project = Path(argv[0])
        argv = []
    parser = argparse.ArgumentParser(
        prog="meowtext",
        description="Decorate text with FIGlet, TOIlet, and TheDraw fonts.",
    )
    parser.add_argument(
        "--version", action="version", version=f"meowtext {__version__}"
    )
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("tui", help="open the banner editor (also the default)")
    commands.add_parser("legacy", help="open the preserved original editor")
    commands.add_parser("styles", help="list presets and your saved designs")
    watch = commands.add_parser(
        "watch", help="play a saved animation in Kitty; Ctrl+C exits"
    )
    watch.add_argument("name")

    run = commands.add_parser(
        "run", help="show artwork before or after an ordinary command"
    )
    run.add_argument("name", help="saved design name")
    run.add_argument(
        "--after",
        action="store_true",
        help="show the banner after the command finishes",
    )
    frame = commands.add_parser(
        "frame", help="open Kitty with artwork above a running command"
    )
    frame.add_argument("name")

    save = commands.add_parser(
        "save", help="save an editable project and its finished artwork to your library"
    )
    save.add_argument("name")
    save.add_argument("project", type=Path)
    save.add_argument("--replace", action="store_true")

    show = commands.add_parser(
        "show", help="summon saved artwork, or reuse its style with new words"
    )
    show.add_argument("name")
    show.add_argument("text", nargs="*")
    show.add_argument("--format", choices=FORMATS, default="ansi")
    show.add_argument("-o", "--output")

    artwork_export = commands.add_parser("export", help="export a project, including its animation")
    artwork_export.add_argument("project", type=Path)
    artwork_export.add_argument("--format", choices=FORMATS)
    artwork_export.add_argument("-o", "--output", required=True)
    artwork_export.add_argument("--frame", type=int, default=0, help="frame to use for a still (default: 0)")

    shell = commands.add_parser(
        "shell",
        help="print Kitty command-banner integration (no startup files changed)",
    )
    shell.add_argument("shell", choices=("zsh", "fish"))
    shell.add_argument("--style", help="saved artwork to show before every command")

    bind = commands.add_parser(
        "bind", help="attach a saved banner to a command or alias name"
    )
    bind.add_argument("name", help="command or alias, e.g. git or ll")
    bind.add_argument("style", nargs="?", help="saved banner; omit with --remove")
    bind.add_argument("--remove", action="store_true")

    render = commands.add_parser("render", help="render one banner")
    render.add_argument("text", nargs="*", help="banner text; joined with spaces")
    render.add_argument(
        "-e", "--engine", default="figlet", help="figlet, toilet, or tdf"
    )
    render.add_argument(
        "-f", "--font", help="font name, or for TheDraw FILE or FILE::name"
    )
    render.add_argument("-o", "--output", help="write here instead of stdout")
    render.add_argument(
        "--format", choices=FORMATS, help="output format (default: from -o, else ansi)"
    )
    render.add_argument("--preset", choices=tuple(PRESETS), default="plain")
    render.add_argument("--gradient", help="palette name, 'none', or #hex,#hex stops")
    render.add_argument(
        "--direction",
        choices=(
            "horizontal",
            "horizontal-back",
            "vertical",
            "vertical-back",
            "diagonal",
            "diagonal-back",
        ),
    )
    render.add_argument("--outline", action="store_true")
    render.add_argument("--no-outline", action="store_true")
    render.add_argument("--outline-char", default=None)
    render.add_argument("--outline-color", default=None)
    render.add_argument(
        "--outline-mode", choices=tuple(mode for _, mode in OUTLINE_MODES)
    )
    render.add_argument(
        "--outline-gradient",
        help="palette name for a gradient outline, or omit for a flat colour",
    )
    render.add_argument("--shadow", action="store_true")
    render.add_argument("--no-shadow", action="store_true")
    render.add_argument("--shadow-dx", type=int)
    render.add_argument("--shadow-dy", type=int)
    render.add_argument("--shadow-color", default=None)
    render.add_argument("--shadow-char", default=None)
    render.add_argument(
        "--hue", type=float, default=0, help="rotate TheDraw colour roles, in degrees"
    )
    render.epilog = "palettes: " + ", ".join(PALETTES)

    fonts = commands.add_parser("fonts", help="list fonts")
    fonts.add_argument("-e", "--engine", default="figlet")
    fonts.add_argument("-q", "--query", default="")
    fonts.add_argument("-n", "--limit", type=int, default=200)
    fonts.add_argument(
        "--fetch", action="store_true", help="download extra FIGlet and TOIlet fonts"
    )

    command_tail: list[str] = []
    if argv and argv[0] in {"run", "frame"} and "--" in argv:
        split = argv.index("--")
        command_tail, argv = argv[split + 1 :], argv[:split]
    args = parser.parse_args(argv)
    try:
        from meowtext import library

        if args.command == "watch":
            from meowtext.playback import watch

            return watch(args.name)
        if args.command in {"run", "frame"}:
            from meowtext.integration import run as run_command, frame as frame_command

            if args.command == "run":
                return run_command(args.name, command_tail, after=args.after)
            return frame_command(args.name, command_tail)
        if args.command == "save":
            from meowtext.project import load_project

            path = library.save(
                args.name, load_project(args.project), replace=args.replace
            )
            print(f"Saved {args.name}. Summon it: meowtext show {args.name}")
            return 0
        if args.command == "show":
            project = library.load(args.name)
            if args.format in {"html", "apng", "gif"} or (args.format == "kitty" and project.animation.name != "none"):
                print(export_notice(args.format, project.animation.name != "none"), file=sys.stderr)
                if args.text:
                    project.text = " ".join(args.text)
                    project.patches = ()
                return _write(_export_project(project, args.format), args.output, args.format)
            if project.animation.name != "none":
                print(export_notice(args.format, True), file=sys.stderr)
            grid = (
                library.render_project(
                    library.load(args.name), " ".join(args.text)
                ).grid
                if args.text
                else library.artwork(args.name)
            )
            return _write(export(grid, args.format), args.output, args.format)
        if args.command == "export":
            from meowtext.project import load_project
            fmt = args.format or _SUFFIXES.get(Path(args.output).suffix.lower(), "html")
            project = load_project(args.project)
            print(export_notice(fmt, project.animation.name != "none"), file=sys.stderr)
            return _write(_export_project(project, fmt, args.frame), args.output, fmt)
        if args.command == "styles":
            print("Presets: " + ", ".join(PRESETS))
            print(
                "Saved: "
                + (", ".join(library.entries()) or "none yet — save one in the editor")
            )
            return 0
        if args.command == "shell":
            print(library.shell_script(args.shell, args.style), end="")
            return 0
        if args.command == "bind":
            if not args.remove and not args.style:
                raise RenderError("give a saved style name, or --remove")
            library.bind(args.name, None if args.remove else args.style)
            print("Binding saved. Reload your meowtext shell integration to apply it.")
            return 0
        if args.command == "render":
            return _render(args)
        if args.command == "fonts":
            return _fonts(args)
        from meowtext.project import load_project

        if args.command == "legacy":
            from meowtext.tui import MeowText
        else:
            from meowtext.studio import MeowText

        opened = load_project(project) if project is not None else None
        MeowText(opened).run()
        return 0
    except (MeowTextError, OSError, ValueError) as exc:
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
    if fmt == "gif":
        print(export_notice(fmt), file=sys.stderr)
    data = export(banner.grid, fmt)
    return _write(data, args.output, fmt)


def _export_project(project, fmt, frame=0):
    from meowtext import library
    from meowtext.compose import layout_font
    from meowtext.catalog import measure_spans
    from meowtext.animation_export import export_design

    font = library.project_font(project)
    source, _, _ = layout_font(project.text, font, project.letters or None)
    if project.style.outline and project.style.outline_scope == "letter" and not source.spans:
        source.spans = measure_spans(font, project.text)
    palette = library.prepare_roles(source, project)
    return export_design(source, project, fmt, frame, palette)


def _write(data: str | bytes, output: str | None, fmt: str) -> int:
    if output:
        path = Path(output)
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
        style.stops = None
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
        style.outline_gradient = (
            None if args.outline_gradient == "off" else args.outline_gradient
        )
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
    if args.fetch:
        from meowtext.fonts_extra import fetch_extra_fonts

        added = fetch_extra_fonts()
        print(f"extra fonts ready ({added} new)")
        return 0
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
