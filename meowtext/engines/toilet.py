"""TOIlet fonts (``.tlf``) via the ``toilet`` program.

FIGlet fonts stay on the figlet engine. Toilet's own fonts are the
``.tlf`` files, which use a different renderer.
"""

from __future__ import annotations

from meowtext.ansi import parse_ansi
from meowtext.engines.external import font_directory, run_tool, tool_available
from meowtext.errors import RenderError
from meowtext.grid import Grid


def available() -> bool:
    return tool_available("toilet")


_names: list[str] | None = None


def font_names() -> list[str]:
    global _names
    if _names is not None:
        return _names
    directory = font_directory()
    if not directory.is_dir():
        _names = []
    else:
        _names = sorted(path.stem for path in directory.glob("*.tlf"))
    return _names


def render(text: str, font: str) -> Grid:
    if not available():
        raise RenderError("toilet is not installed")
    if font not in set(font_names()):
        raise RenderError(f"no TOIlet font named {font!r}")
    raw = run_tool(
        ["toilet", "-d", str(font_directory()), "-f", font, "-w", "10000"],
        text,
    )
    return parse_ansi(raw)
