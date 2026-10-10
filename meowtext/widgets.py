"""A one-line control that moves through its choices with the arrow keys."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget


class Cycle(Widget):
    """Shows the current choice. Left and right move to the neighbours."""

    can_focus = True
    BINDINGS = [
        Binding("left", "previous", "Previous", show=False),
        Binding("right", "next", "Next", show=False),
        Binding("enter", "next", "Next", show=False),
    ]

    class Changed(Message):
        def __init__(self, cycle: Cycle, value: str) -> None:
            super().__init__()
            self.cycle = cycle
            self.value = value

    def __init__(
        self,
        options: tuple[tuple[str, str], ...] | list[tuple[str, str]],
        value: str,
        *,
        label: str = "",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.options: list[tuple[str, str]] = list(options)
        self.value = value
        self.label = label

    def render(self) -> Text:
        current = next((text for text, value in self.options if value == self.value), self.value or "—")
        text = Text()
        if self.label:
            text.append(f"{self.label}  ", style="#9aa1ab")
        text.append("◀ ", style="#6c7380")
        text.append(current)
        text.append(" ▶", style="#6c7380")
        return text

    def set_value(self, value: str) -> None:
        self.value = value
        self.refresh()

    def set_options(self, options: list[tuple[str, str]] | tuple[tuple[str, str], ...], value: str | None = None) -> None:
        self.options = list(options)
        if value is not None:
            self.value = value
        elif self.value not in {item for _, item in self.options}:
            self.value = self.options[0][1] if self.options else ""
        self.refresh()

    def action_next(self) -> None:
        self._step(1)

    def action_previous(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        if self.disabled:
            return
        values = [value for _, value in self.options]
        if not values:
            return
        try:
            index = values.index(self.value)
        except ValueError:
            index = 0
        self.value = values[(index + delta) % len(values)]
        self.refresh()
        self.post_message(self.Changed(self, self.value))
