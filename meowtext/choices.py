"""Visible, keyboard-first options. Moving the cursor applies the new value."""

from math import ceil
from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Select

from meowtext.effects import COLOURS, PALETTES


class Choices(ScrollView, can_focus=True):
    """One Tab stop, a grid of options, and no dropdown or confirmation step."""

    DEFAULT_CSS = """
    Choices { height: auto; min-height: 1; max-height: 8; overflow-y: auto; overflow-x: hidden;
        background: #11212d; color: #cbdce5; padding: 0; text-wrap: nowrap; }
    Choices:focus { background: #19313d; }
    """
    BINDINGS = [
        Binding("left", "move(-1)", "", show=False),
        Binding("right", "move(1)", "", show=False),
        Binding("up", "row(-1)", "", show=False),
        Binding("down", "row(1)", "", show=False),
        Binding("home", "edge(False)", "", show=False),
        Binding("end", "edge(True)", "", show=False),
        Binding("pageup", "page(-1)", "", show=False),
        Binding("pagedown", "page(1)", "", show=False),
    ]
    value = reactive(Select.BLANK, init=False)

    class Changed(Message):
        def __init__(self, control, value):
            super().__init__()
            self.choices = control
            self.value = value

        @property
        def control(self):
            return self.choices

    def __init__(
        self, options, *, value=Select.BLANK, allow_blank=True, prompt="", **kwargs
    ):
        super().__init__(**kwargs)
        self._options = list(options)
        self._line_key = None
        self._lines = []
        self.prompt = prompt
        self.value = value
        if value == Select.BLANK and not allow_blank and self._options:
            self.value = self._options[0][1]

    def set_options(self, options):
        self._options = list(options)
        self._fit_height()
        self.refresh(layout=True)

    def _geometry(self, width):
        longest = max(
            (cell_len(str(label)) + 3 for label, _ in self._options), default=8
        )
        columns = max(1, width // min(22, max(8, longest)))
        return columns, max(1, width // columns)

    def get_content_height(self, container, viewport, width):
        columns, _ = self._geometry(width)
        return max(1, ceil(len(self._options) / columns))

    def render(self):
        columns, width = self._geometry(self.scrollable_content_region.width or 30)
        out = Text(no_wrap=True, overflow="crop")
        for index, (label, value) in enumerate(self._options):
            if index and index % columns == 0:
                out.append("\n")
            chosen = value == self.value
            tone = "#aeef6a" if self.has_focus else "#65e8ed"
            style = Style(
                color="#08151b" if chosen else "#cbdce5",
                bgcolor=tone if chosen else None,
                bold=chosen,
                meta={"choice": index},
            )
            text = Text("▸" if chosen else " ", style=style)
            if value in COLOURS:
                text.append(
                    "■", style=Style(color=COLOURS[value].hex(), meta={"choice": index})
                )
            elif value in PALETTES:
                stops = PALETTES[value]
                for color in (stops[0], stops[len(stops) // 2], stops[-1]):
                    text.append(
                        "▰", style=Style(color=color.hex(), meta={"choice": index})
                    )
            text.append(str(label), style=style)
            text.truncate(width, overflow="ellipsis", pad=True)
            text.stylize(style)
            # Keep swatch colour spans on top of the selection background.
            if value in COLOURS:
                text.stylize(COLOURS[value].hex(), 1, 2)
            elif value in PALETTES:
                stops = PALETTES[value]
                for offset, color in enumerate(
                    (stops[0], stops[len(stops) // 2], stops[-1]), 1
                ):
                    text.stylize(color.hex(), offset, offset + 1)
            out.append_text(text)
        return (
            out if self._options else Text(self.prompt or "No options", style="#8b9fab")
        )

    def render_line(self, y):
        # ScrollView keeps a separate virtual canvas. A Static with overflow
        # still clips its own Rich text to its physical height.
        width = self.scrollable_content_region.width
        key = (
            width,
            self.value,
            self.has_focus,
            tuple(self._options),
            getattr(self, "frame", 0),
        )
        if key != self._line_key:
            console = self.app.console
            lines = console.render_lines(
                self.render(),
                console.options.update(width=max(1, width), height=None),
                style=self.rich_style,
                pad=True,
            )
            self._lines = [Strip(line, width) for line in lines]
            self._line_key = key
        row = y + int(self.scroll_y)
        return (
            self._lines[row]
            if 0 <= row < len(self._lines)
            else Strip.blank(width, self.rich_style)
        )

    def watch_value(self, value):
        if self.is_mounted:
            self.refresh()
            self._reveal()
        self.post_message(self.Changed(self, value))

    def _index(self):
        return next(
            (i for i, (_, value) in enumerate(self._options) if value == self.value), 0
        )

    def _reveal(self):
        columns, _ = self._geometry(self.scrollable_content_region.width)
        row = self._index() // columns
        if row < self.scroll_y:
            self.scroll_to(y=row, animate=False)
        elif row >= self.scroll_y + self.size.height:
            self.scroll_to(y=row - self.size.height + 1, animate=False)
        if self._options:
            self.tooltip = (
                str(self._options[self._index()][0]) + " · arrows preview immediately"
            )

    def action_move(self, delta):
        if self._options:
            index = (self._index() + delta) % len(self._options)
            self.value = self._options[index][1]

    def action_row(self, delta):
        self.action_move(
            delta * self._geometry(self.scrollable_content_region.width)[0]
        )

    def action_page(self, delta):
        self.action_move(
            delta
            * self._geometry(self.scrollable_content_region.width)[0]
            * max(1, self.size.height - 1)
        )

    def action_edge(self, end):
        if self._options:
            self.value = self._options[-1 if end else 0][1]

    def on_focus(self):
        self.refresh()
        self._reveal()

    def on_blur(self):
        self.refresh()

    def on_click(self, event: events.Click):
        index = event.style.meta.get("choice")
        if index is not None and 0 <= index < len(self._options):
            self.focus()
            self.value = self._options[index][1]
            event.stop()

    def on_resize(self):
        self._fit_height()

    def _fit_height(self):
        if self.content_size.width:
            width = self.scrollable_content_region.width
            columns, _ = self._geometry(width)
            rows = max(1, ceil(len(self._options) / columns))
            height = min(8, rows)
            if self.styles.height is None or self.styles.height.value != height:
                self.styles.height = height
            self.virtual_size = Size(width, rows)
            self._reveal()
            self.refresh()
