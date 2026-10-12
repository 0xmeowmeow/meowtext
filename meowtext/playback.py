"""Play a saved recipe using the original compositor and animation engine."""

from __future__ import annotations

import sys
import time

from rich.console import Console
from rich.live import Live

from meowtext.catalog import measure_spans
from meowtext.compose import layout_font, present
from meowtext.errors import RenderError
from meowtext.library import load, project_font, prepare_roles
from meowtext.palette import RelationPalette


def frames(project):
    """Lay out once, then animate without repeatedly invoking external fonts."""
    font = project_font(project)
    source, _, _ = layout_font(project.text, font, project.letters or None)
    if (
        (project.animation.name == "trace"
         or (project.style.outline and project.style.outline_scope == "letter"))
        and not source.spans
    ):
        source.spans = measure_spans(font, project.text)
    palette = prepare_roles(source, project)
    number = 0
    while True:
        yield present(
            source,
            project.style,
            palette,
            animation=project.animation,
            frame=number,
            patches=project.patches,
        )
        number += 1


def watch(name: str) -> int:
    if not sys.stdout.isatty():
        raise RenderError(
            "animation needs a terminal; use 'meowtext show' to export a frame"
        )
    from meowtext.previews import fit_preview

    project = load(name)
    console = Console(force_terminal=True, color_system="truecolor")
    stream = frames(project)
    # The same 120 ms clock as the editor preserves motion speed across both.
    with Live(console=console, screen=True, auto_refresh=False) as live:
        try:
            while True:
                started = time.monotonic()
                grid = next(stream)
                live.update(
                    fit_preview(grid, console.width, max(3, console.height - 1)),
                    refresh=True,
                )
                time.sleep(max(0, 0.12 - (time.monotonic() - started)))
        except KeyboardInterrupt:
            pass
    return 0
