"""Small cell editor using the existing grid, glyph layout and patch format."""

from __future__ import annotations

import copy

from rich.cells import cell_len
from textual import events
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from meowtext.compose import layout_font
from meowtext.effects import COLOURS
from meowtext.grid import Cell, Grid
from meowtext.tui import to_rich


class PaintCanvas(Static, can_focus=True):
    DEFAULT_CSS = "PaintCanvas { width: auto; height: auto; text-wrap: nowrap; }"

    def on_click(self, event: events.Click):
        self.focus()
        self.screen.move_to(event.x, event.y)

    def on_key(self, event: events.Key):
        editor = self.screen
        x, y = editor.cursor
        if event.key in {"left", "right", "up", "down"}:
            dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[
                event.key
            ]
            editor.move_to(x + dx, y + dy)
        elif event.key in {"delete", "backspace"}:
            editor.paint(" ")
        elif (
            event.character
            and cell_len(event.character) == 1
            and event.character.isprintable()
        ):
            editor.paint(event.character)
        else:
            return
        event.stop()
        event.prevent_default()


class PaintEditor(ModalScreen):
    """Work on a copy. Applying returns only explicit cell and letter edits."""

    DEFAULT_CSS = """
    PaintEditor { align: center middle; background: #090f17 95%; }
    #paint-dialog { width: 96%; height: 94%; border: solid #74e9ef; padding: 1; }
    #paint-tools, #paint-actions { height: 3; }
    #paint-tools Select { width: 1fr; }
    #paint-tools Input { width: 10; }
    #paint-help { height: auto; color: #90a5b4; }
    #paint-scroll { height: 1fr; border: solid #29404d; }
    #paint-position { height: 1; }
    #paint-actions Button { width: 1fr; min-width: 8; }
    """

    def __init__(self, project, font, banner):
        super().__init__()
        self.project = copy.deepcopy(project)
        self.font = font
        self.banner = banner.copy()
        self.grid = self.banner.copy()
        self.patches = {(x, y): c.clone() for x, y, c in project.patches}
        self.cursor = (0, 0)
        self.target = "banner"
        self.undo = []

    def compose(self):
        letters = list(dict.fromkeys(c for c in self.project.text if not c.isspace()))
        with Vertical(id="paint-dialog"):
            yield Static("PAINT · a finished banner or one reusable letter")
            with Horizontal(id="paint-tools"):
                yield Select(
                    [("Finished banner", "banner")]
                    + [(f"Letter {c}", f"letter:{c}") for c in letters],
                    value="banner",
                    allow_blank=False,
                    id="paint-target",
                )
                yield Select(
                    [("Keep colour", "keep")] + [(n.title(), n) for n in COLOURS],
                    value="keep",
                    allow_blank=False,
                    id="paint-colour",
                )
                yield Input("█", max_length=1, id="paint-brush")
                yield Button("Paint cell", id="paint-cell")
            yield Static(
                "Click a cell or use arrow keys. Type to paint; Delete erases. Letter edits repeat wherever that letter appears and use separate letter spacing.",
                id="paint-help",
            )
            with ScrollableContainer(id="paint-scroll"):
                yield PaintCanvas(id="paint-canvas")
            yield Static("", id="paint-position")
            with Horizontal(id="paint-actions"):
                yield Button("Undo", id="paint-undo")
                yield Button("Cancel", id="paint-cancel")
                yield Button("Apply edits", id="paint-apply", variant="primary")

    def on_mount(self):
        self.redraw()
        self.query_one(PaintCanvas).focus()

    def redraw(self):
        self.query_one(PaintCanvas).update(to_rich(self.grid, cursor=self.cursor))
        x, y = self.cursor
        self.query_one("#paint-position", Static).update(
            f"Cell {x+1}, {y+1} · {self.grid.width} × {self.grid.height} cells"
        )
        self.query_one("#paint-undo", Button).disabled = not self.undo

    def move_to(self, x, y):
        self.cursor = (
            max(0, min(x, self.grid.width - 1)),
            max(0, min(y, self.grid.height - 1)),
        )
        self.redraw()

    def on_select_changed(self, event: Select.Changed):
        event.stop()
        if event.select.id != "paint-target" or not self.is_mounted:
            return
        self.target = str(event.value)
        if self.target == "banner":
            self.grid = self.banner.copy()
        else:
            char = self.target.split(":", 1)[1]
            glyph = self.project.letters.get(char)
            self.grid = (
                glyph if glyph is not None else layout_font(char, self.font)[0]
            ).copy()
            if not self.grid.width or not self.grid.height:
                self.grid = Grid([[Cell(char)]])
        self.cursor = (0, 0)
        self.undo = []
        self.redraw()

    def on_input_changed(self, event: Input.Changed):
        event.stop()

    def paint(self, char):
        if (
            cell_len(char) != 1
            or not char.isprintable()
            or not self.grid.width
            or not self.grid.height
        ):
            return
        self.undo.append(
            (
                self.grid.copy(),
                copy.deepcopy(self.patches),
                copy.deepcopy(self.project.letters),
            )
        )
        self.undo = self.undo[-100:]
        x, y = self.cursor
        cell = self.grid.get(x, y).clone()
        cell.char = char
        colour = self.query_one("#paint-colour", Select).value
        if colour in COLOURS:
            cell.fg = COLOURS[colour]
            cell.fg_slot = None
        self.grid.set(x, y, cell)
        if self.target == "banner":
            self.patches[(x, y)] = cell
            self.banner = self.grid.copy()
        else:
            self.project.letters[self.target.split(":", 1)[1]] = self.grid.copy()
        self.redraw()

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        id = event.button.id
        if id == "paint-cell":
            self.paint(self.query_one("#paint-brush", Input).value or " ")
        elif id == "paint-undo" and self.undo:
            self.grid, self.patches, self.project.letters = self.undo.pop()
            if self.target == "banner":
                self.banner = self.grid.copy()
            self.redraw()
        elif id == "paint-cancel":
            self.dismiss(None)
        elif id == "paint-apply":
            self.project.patches = tuple(
                (x, y, c) for (x, y), c in sorted(self.patches.items())
            )
            self.dismiss(self.project)
