"""The settings under the banner, drawn as one grid.

Each cell prints the letter that changes it. That letter steps the setting
forward and lands there. The same letter with shift steps backward. Arrows
move the highlight the way the grid is drawn: up and down stay in the
column, left and right cross to the other column. Enter steps the
highlighted setting forward, and backspace steps it backward. The digits
and the bracket keys change section.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget


@dataclass(frozen=True, slots=True)
class Knob:
    id: str
    key: str
    label: str
    text: str
    enabled: bool = True


class Board(Widget):
    """The settings under the banner."""

    can_focus = True
    BINDINGS = [
        Binding("up", "up", show=False),
        Binding("down", "down", show=False),
        Binding("left", "left", show=False),
        Binding("right", "right", show=False),
        Binding("shift+left", "lower", show=False),
        Binding("shift+right", "raise_value", show=False),
        Binding("enter", "raise_value", show=False),
        Binding("backspace", "lower", show=False),
        Binding("left_square_bracket", "earlier", show=False),
        Binding("right_square_bracket", "later", show=False),
    ]

    class Turn(Message):
        def __init__(self, knob: str, delta: int) -> None:
            super().__init__()
            self.knob = knob
            self.delta = delta

    class Go(Message):
        def __init__(self, section: str) -> None:
            super().__init__()
            self.section = section

    def __init__(self, sections: tuple[tuple[str, str], ...], **kwargs) -> None:
        super().__init__(**kwargs)
        self.sections = sections
        self.section = sections[0][0]
        self.rows: list[Knob] = []
        self.index = 0

    def show(self, section: str, rows: list[Knob], index: int | None = None) -> None:
        self.section = section
        self.rows = rows
        if index is None:
            self.index = min(self.index, max(len(rows) - 1, 0))
        else:
            self.index = index
        self.refresh()

    def get_content_height(self, container, viewport, width: int) -> int:
        rows = max(1, (len(self.rows) + 1) // 2)
        return 1 + rows

    def render(self) -> Text:
        width = max(self.size.width, 40)
        text = Text()
        tab = max(6, width // len(self.sections))
        for number, (name, label) in enumerate(self.sections, start=1):
            chunk = f" {number} {label} "[:tab].ljust(tab)
            if name == self.section:
                text.append(chunk, style="bold reverse")
            else:
                text.append(chunk, style="#9aa1ab")
        text.append("\n")
        half = max(20, width // 2)
        for start in range(0, len(self.rows), 2):
            if start:
                text.append("\n")
            text.append(self._cell(self.rows[start], start, half))
            if start + 1 < len(self.rows):
                text.append(self._cell(self.rows[start + 1], start + 1, width - half))
        return text

    def _cell(self, knob: Knob, index: int, width: int) -> Text:
        mark = f"{knob.key} " if knob.key else "  "
        room = max(0, width - len(mark))
        rest = f"{knob.label}  {knob.text}"[:room]
        pad = " " * max(0, room - len(rest))
        shown = mark + rest + pad
        if index == self.index:
            return Text(shown, style="bold reverse")
        if not knob.enabled:
            return Text(shown, style="#5c6370")
        text = Text()
        text.append(mark, style="bold #e6b450")
        text.append(rest + pad)
        return text

    def action_up(self) -> None:
        self._move(-1)

    def action_down(self) -> None:
        self._move(1)

    def action_left(self) -> None:
        self._move_column()

    def action_right(self) -> None:
        self._move_column()

    def action_lower(self) -> None:
        self._turn(-1)

    def action_raise_value(self) -> None:
        self._turn(1)

    def action_earlier(self) -> None:
        self._section(-1)

    def action_later(self) -> None:
        self._section(1)

    def _move(self, delta: int) -> None:
        if not self.rows:
            return
        column = self.index % 2
        indexes = [index for index in range(len(self.rows)) if index % 2 == column]
        position = indexes.index(self.index) if self.index in indexes else 0
        self.index = indexes[(position + delta) % len(indexes)]
        self.refresh()

    def _move_column(self) -> None:
        if not self.rows:
            return
        other = self.index + (1 if self.index % 2 == 0 else -1)
        if 0 <= other < len(self.rows):
            self.index = other
            self.refresh()

    def _turn(self, delta: int) -> None:
        if not self.rows:
            return
        knob = self.rows[self.index]
        if knob.enabled:
            self.post_message(self.Turn(knob.id, delta))

    def _section(self, delta: int) -> None:
        names = [name for name, _label in self.sections]
        index = names.index(self.section) if self.section in names else 0
        self.post_message(self.Go(names[(index + delta) % len(names)]))

    def on_key(self, event: events.Key) -> None:
        character = event.character
        if character and character in "123456":
            self.post_message(self.Go(self.sections[int(character) - 1][0]))
            event.stop()
            return
        if character == "+":
            self.post_message(self.Turn("add-stop", 1))
            event.stop()
            return
        if character == "-":
            self.post_message(self.Turn("remove-stop", 1))
            event.stop()
            return
        if character and len(character) == 1 and character.isalpha():
            for index, knob in enumerate(self.rows):
                if knob.key == character.lower() and knob.enabled:
                    self.index = index
                    self.refresh()
                    self.post_message(self.Turn(knob.id, -1 if character.isupper() else 1))
                    event.stop()
                    return

    def on_click(self, event: events.Click) -> None:
        self.focus()
        width = max(self.size.width, 1)
        if event.y <= 0:
            count = len(self.sections)
            picked = min(count - 1, max(0, event.x) * count // width)
            self.post_message(self.Go(self.sections[picked][0]))
            event.stop()
            return
        row = event.y - 1
        half = width // 2
        column = 0 if event.x < half else 1
        index = row * 2 + column
        if index < 0 or index >= len(self.rows):
            return
        self.index = index
        cell_x = event.x if column == 0 else event.x - half
        cell_w = half if column == 0 else width - half
        delta = -1 if cell_x < cell_w / 2 else 1
        knob = self.rows[index]
        self.refresh()
        if knob.enabled:
            self.post_message(self.Turn(knob.id, delta))
        event.stop()
