"""TOIlet fonts (``.tlf``) via the ``toilet`` program.

FIGlet fonts stay on the figlet engine. Toilet's own fonts are the
``.tlf`` files, which use a different renderer.
"""

from __future__ import annotations

from pathlib import Path

from meowtext.ansi import parse_ansi
from meowtext.engines.external import font_directory, run_tool, tool_available
from meowtext.errors import RenderError
from meowtext.grid import Grid


def available() -> bool:
    return tool_available("toilet")


_index: dict[str, Path] | None = None


def font_index() -> dict[str, Path]:
    """Font name to the file that provides it. The system set wins a clash."""

    global _index
    if _index is not None:
        return _index
    found: dict[str, Path] = {}
    for directory in _directories():
        for path in sorted(directory.glob("*.tlf")):
            found.setdefault(path.stem, path)
    _index = found
    return found


def font_names() -> list[str]:
    return sorted(font_index())


def render(text: str, font: str) -> Grid:
    if not available():
        raise RenderError("toilet is not installed")
    path = font_index().get(font)
    if path is None:
        raise RenderError(f"no TOIlet font named {font!r}")
    raw = run_tool(
        ["toilet", "-d", str(path.parent), "-f", path.stem, "-w", "10000"],
        text,
    )
    return parse_ansi(raw)


def _directories() -> list[Path]:
    from meowtext.packs import font_dir

    found: list[Path] = []
    system = font_directory()
    if system.is_dir():
        found.append(system)
    extra = font_dir()
    if extra.is_dir() and extra not in found:
        found.append(extra)
    return found
