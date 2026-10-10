"""FIGlet fonts (``.flf``) via the ``figlet`` program."""

from __future__ import annotations

from meowtext.ansi import parse_ansi
from meowtext.engines.external import font_directory, run_tool, tool_available
from meowtext.errors import RenderError
from meowtext.grid import Grid


def available() -> bool:
    return tool_available("figlet")


_names: list[str] | None = None


def font_names() -> list[str]:
    global _names
    if _names is not None:
        return _names
    directory = font_directory()
    if not directory.is_dir():
        _names = []
    else:
        _names = sorted(path.stem for path in directory.glob("*.flf"))
    return _names


def render(text: str, font: str) -> Grid:
    if not available():
        raise RenderError("figlet is not installed")
    if font not in set(font_names()):
        raise RenderError(f"no FIGlet font named {font!r}")
    raw = run_tool(
        ["figlet", "-d", str(font_directory()), "-f", font, "-w", "10000"],
        text,
    )
    return parse_ansi(raw)
