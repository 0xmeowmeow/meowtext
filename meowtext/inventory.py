"""Visual effect inventories and lettering made by the app's own renderer."""

from functools import lru_cache
from math import ceil
from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.geometry import Size
from textual.widgets import Static
from textual.containers import Vertical

from meowtext.choices import Choices
from meowtext.compose import present, layout_font
from meowtext.catalog import resolve
from meowtext.effects import Animation, BannerStyle, PRESETS
from meowtext.grid import Cell, Color, Grid
from meowtext.previews import fit_preview
from meowtext.tui import to_rich


@lru_cache(maxsize=12)
def lettering(words, face="future"):
    try:
        return layout_font(words, resolve("toilet", face))[0]
    except Exception:
        if words == "FX":
            return Grid(
                [[Cell(c) for c in line] for line in ("█▀▀ ▀▄▀", "█▀  ▄▀▄", "▀   ▀ ▀")]
            )
        return Grid([[Cell(c) for c in words.upper()]])


class Lettering(Static):
    """A section heading is a font specimen too."""

    DEFAULT_CSS = "Lettering { height: 3; text-wrap: nowrap; content-align: center middle; color: #65e8ed; }"

    def __init__(self, words, **kwargs):
        self.words = words
        self.face = "pagga" if words == "LOOKS" else "future"
        super().__init__(to_rich(lettering(words, self.face)), **kwargs)

    def on_resize(self):
        self.update(
            Text("▰ " + self.words + " ▰", style="bold")
            if self.size.height < 3
            else to_rich(lettering(self.words, self.face))
        )


class Showcase(Static):
    DEFAULT_CSS = "Showcase { width: 34; height: 3; text-wrap: nowrap; content-align: center middle; }"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame = 0
        self.running = True
        self.tooltip = (
            "Made with Meowtext · click for another look · F5 pauses interface motion"
        )

    def on_mount(self):
        self.tick()
        self.set_interval(0.15, self.tick)

    def tick(self):
        if not self.running and self.frame:
            return
        mode = (self.frame // 70) % 3
        source = lettering("meowtext", "future" if mode == 1 else "pagga")
        style = BannerStyle(gradient=("rainbow", "ice", "fire")[mode], bands=mode == 2)
        art = present(
            source,
            style,
            animation=Animation(name="march", speed=0.5),
            frame=self.frame,
        )
        self.update(to_rich(art))
        self.frame += 1

    def on_click(self):
        self.frame = (self.frame // 70 + 1) * 70
        running = self.running
        self.running = True
        self.tick()
        self.running = running


class Inventory(Choices):
    """One focused panel containing substantial, real effect specimens."""

    DEFAULT_CSS = """
    Inventory { height: 1fr; min-height: 4; max-height: 100%; overflow-y: auto;
        background: #0c1722; scrollbar-size: 1 1; }
    Inventory:focus { background: #152730; }
    """
    BINDINGS = [
        Binding("enter", "tune", "Tune this effect", show=False),
        Binding("tab", "bank(1)", "Next panel", show=False, priority=True),
        Binding("shift+tab", "bank(-1)", "Previous panel", show=False, priority=True),
    ]

    class Tune(Message):
        def __init__(self, inventory):
            super().__init__()
            self.inventory = inventory

    def __init__(self, kind, options, *, presets=None, **kwargs):
        super().__init__(options, **kwargs)
        self.kind = kind
        self.presets = presets or PRESETS
        self.frame = 0
        self._pictures = {}

    def _geometry(self, width):
        columns = max(1, min(3, width // 14))
        return columns, max(1, width // columns)

    def get_content_height(self, container, viewport, width):
        return ceil(len(self._options) / self._geometry(width)[0]) * 7

    def _fit_height(self):
        self.virtual_size = Size(
            self.scrollable_content_region.width,
            self.get_content_height(
                self.size, self.size, self.scrollable_content_region.width
            ),
        )
        self._reveal()
        self.refresh()

    def _reveal(self):
        columns, _ = self._geometry(self.scrollable_content_region.width)
        row = (self._index() // columns) * 7
        if row < self.scroll_y:
            self.scroll_to(y=row, animate=False)
        elif row + 7 > self.scroll_y + self.size.height:
            self.scroll_to(y=max(0, row + 7 - self.size.height), animate=False)

    def _art(self, value, width):
        key = (value, width, self.frame if self.kind == "motion" else 0)
        if key in self._pictures:
            return self._pictures[key]
        # A two-line FX specimen leaves real room for outlines and shadows.
        # It stays native terminal text even in a small inventory slot.
        source = Grid([[Cell(c) for c in line] for line in ("█▀▀ ▀▄▀", "█▀  ▄▀▄")])
        animation = Animation()
        if self.kind == "look":
            style = self.presets[value]
        elif self.kind == "edge":
            style = BannerStyle(
                gradient="ice",
                outline=value != "none",
                outline_mode="shade" if value == "none" else value,
                outline_distance=1,
                outline_color=Color(180, 135, 255),
            )
        else:
            style = BannerStyle(
                gradient="rainbow",
                outline=True,
                outline_mode="contour",
                outline_distance=1,
                outline_color=Color(101, 232, 237),
            )
            animation = Animation(name=value, speed=1)
        art = fit_preview(
            present(source, style, animation=animation, frame=self.frame),
            max(1, width - 2),
            5,
        )
        lines = art.split("\n")
        while lines and not lines[-1].plain:
            lines.pop()
        padded = []
        top = max(0, (5 - len(lines)) // 2)
        for y in range(5):
            line = lines[y - top].copy() if top <= y < top + len(lines) else Text("")
            line.truncate(max(1, width - 2), overflow="crop")
            line.align("center", max(1, width - 2))
            padded.append(line)
        if self.kind != "motion":
            self._pictures[key] = padded
        return padded

    def render(self):
        columns, width = self._geometry(self.scrollable_content_region.width or 36)
        out = Text(no_wrap=True, overflow="crop")
        for start in range(0, len(self._options), columns):
            batch = self._options[start : start + columns]
            arts = [self._art(value, width) for _, value in batch]
            for y in range(7):
                if start or y:
                    out.append("\n")
                for offset, (label, value) in enumerate(batch):
                    index = start + offset
                    selected = value == self.value
                    accent = "#b6f572" if self.has_focus else "#65e8ed"
                    meta = {"choice": index}
                    base = Style(
                        bgcolor="#284149" if selected else "#101e2a", meta=meta
                    )
                    if y == 0:
                        caption = Text(
                            ("▶ " if selected else "  ") + str(label),
                            style=Style(
                                color="#08151b" if selected else "#c1d5de",
                                bgcolor=accent if selected else "#233542",
                                bold=True,
                                meta=meta,
                            ),
                        )
                        caption.truncate(width - 1, overflow="ellipsis", pad=True)
                        caption.stylize(Style(meta=meta))
                        out.append_text(caption)
                        out.append(" ")
                    elif y < 6:
                        line = Text()
                        line.append(
                            "┃" if selected else " ",
                            style=accent if selected else "#233542",
                        )
                        line.append_text(arts[offset][y - 1])
                        line.truncate(width - 1, overflow="crop", pad=True)
                        # Metadata and background only: preserve specimen colours.
                        line.stylize(base)
                        out.append_text(line)
                        out.append(" ")
                    else:
                        out.append(
                            (
                                "┗" + "━" * max(0, width - 2)
                                if selected
                                else " " * (width - 1)
                            )
                            + " ",
                            Style(color=accent, meta=meta),
                        )
        return out

    def advance(self, frame):
        if self.kind == "motion" and self.is_on_screen:
            self.frame = frame
            self.refresh()

    def action_tune(self):
        self.post_message(self.Tune(self))

    def action_bank(self, direction):
        names = ("fill", "outline", "motion")
        current = ("look", "edge", "motion").index(self.kind)
        self.app.action_bank(names[(current + direction) % 3])

    def action_page(self, delta):
        self.action_move(
            delta
            * self._geometry(self.scrollable_content_region.width)[0]
            * max(1, self.size.height // 7)
        )


class FontCard(Vertical, can_focus=True, can_focus_children=False):
    BINDINGS = [
        Binding("left", "move(-1, 0)", "", show=False),
        Binding("right", "move(1, 0)", "", show=False),
        Binding("up", "move(0, -1)", "", show=False),
        Binding("down", "move(0, 1)", "", show=False),
        Binding("enter", "explore", "Explore similar", show=False),
        Binding("space", "use", "Use font", show=False),
        Binding("f", "star", "Favourite", show=False),
        Binding("i", "inspect", "Inspect", show=False),
    ]

    def action_move(self, x, y):
        self.app.move_card(int(self.id.rsplit("-", 1)[1]), x, y)

    def action_explore(self):
        self.app.font_action("like", int(self.id.rsplit("-", 1)[1]))

    def action_use(self):
        self.app.font_action("choose", int(self.id.rsplit("-", 1)[1]))

    def action_star(self):
        self.app.font_action("star", int(self.id.rsplit("-", 1)[1]))

    def action_inspect(self):
        self.app.font_action("inspect", int(self.id.rsplit("-", 1)[1]))
