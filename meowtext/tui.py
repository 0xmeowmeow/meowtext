"""Textual frontend. The banner engine does not depend on this module.

The settings are one grid under the banner, not a form. The highlighted
setting changes with the left and right arrows. A letter shown on a row
changes that setting immediately. 1 through 6 change section. Fonts stay
hidden until Ctrl+F: type a search, and up and down walk the matches.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Footer, Header, Input, Static, TextArea

from meowtext.board import Board, Knob
from meowtext.catalog import FontFamily, FontInfo, group_fonts, list_fonts, load_tdf, measure_spans, tdf_ready
from meowtext.compose import Banner, layout_font, present
from meowtext.effects import (
    ANIM_DIRECTIONS,
    ANIM_LAYERS,
    ANIM_SPEEDS,
    ANIM_TRAVELS,
    ANIMATIONS,
    COLOURS,
    DEFAULT_OUTLINE,
    DEFAULT_SHADOW,
    GRADIENT_DIRECTIONS,
    OUTLINE_DIRECTIONS,
    OUTLINE_DISTANCES,
    OUTLINE_MODES,
    OUTLINE_PLACES,
    OUTLINE_SCOPES,
    TRACE_PATTERNS,
    TRACE_REVEALS,
    Animation,
    BannerStyle,
    colour_name,
)
from meowtext.errors import RenderError
from meowtext.export import export
from meowtext.grid import Cell, Color, Grid
from meowtext.packs import list_favourites, load_favourite, load_palettes, load_presets, load_symbols, save_favourite
from meowtext.palette import RelationPalette, hsv_to_rgb, rgb_to_hsv, used_slots
from meowtext.project import Project, allocate_path, load_project, project_filename, roles_from_palette, save_project

_SUFFIX = {
    "ansi": ".ans",
    "plain": ".txt",
    "html": ".html",
    "json": ".json",
    "png": ".png",
    "kitty": ".kitty",
    "irc": ".irc",
}
_SECTIONS = (
    ("look", "Look"),
    ("outline", "Outline"),
    ("shadow", "Shadow"),
    ("colour", "Colour"),
    ("animate", "Animate"),
    ("notes", "Notes"),
)
_ON = (("On", "on"), ("Off", "off"))
_SIDES = (
    ("all four", "tblr"),
    ("top and bottom", "tb"),
    ("left and right", "lr"),
    ("top", "t"),
    ("bottom", "b"),
    ("left", "l"),
    ("right", "r"),
    ("none", "none"),
)
_FORMATS = (
    ("ANSI", "ansi"),
    ("Plain", "plain"),
    ("HTML", "html"),
    ("JSON", "json"),
    ("PNG", "png"),
    ("Kitty", "kitty"),
    ("IRC", "irc"),
)
_ENGINES = (("FIGlet", "figlet"), ("TOIlet", "toilet"), ("TheDraw", "tdf"))
_PAINT_COLOURS = ("keep",) + tuple(COLOURS)
_NUMBERS = {
    "hue": 15,
    "stop-h": 15,
    "role-h": 15,
    "stop-s": 5,
    "stop-v": 5,
    "role-s": 5,
    "role-v": 5,
    "odx": 1,
    "ody": 1,
    "dx": 1,
    "dy": 1,
}


def to_rich(
    grid: Grid,
    focus: int | None = None,
    cursor: tuple[int, int] | None = None,
    offset: tuple[int, int] = (0, 0),
) -> Text:
    """Draw the banner. ``offset`` is blank space so the letters sit in the middle."""

    text = Text()
    if not grid.rows:
        return text
    across, down = offset
    if down:
        text.append("\n" * down)
    for y, row in enumerate(grid.rows):
        if across:
            text.append(" " * across)
        for x, cell in enumerate(row):
            chosen = focus is None or cell.fg_slot == focus or cell.bg_slot == focus
            fg = cell.fg if chosen else _dim(cell.fg)
            bg = cell.bg if chosen else _dim(cell.bg)
            style = ""
            if fg is not None:
                style += fg.hex()
            elif not chosen:
                style += "#3a3a3a"
            if bg is not None:
                style += f" on {bg.hex()}"
            if cursor == (x, y):
                style += " reverse"
            text.append(cell.char or " ", style=style or None)
        if y != len(grid.rows) - 1:
            text.append("\n")
    return text


def _dim(color: Color | None) -> Color | None:
    if color is None:
        return None
    return Color(color.r // 5, color.g // 5, color.b // 5)


class BannerView(Static):
    """The preview. It takes the keys while you are painting."""

    can_focus = True


class MeowText(App):
    """Type a line, pick a font, decorate it, and export the banner."""

    TITLE = "meowtext"
    SUB_TITLE = "letter changes it · shift+letter back · arrows move · 1–6 section · ctrl-f fonts"
    CSS = """
    Screen { background: #101114; }
    #text { width: 1fr; height: 1; }
    #fonts { height: auto; width: 100%; background: #181a20; }
    #filter { width: 100%; height: 1; }
    #matches { height: auto; max-height: 6; padding: 0 1; color: #d7dbe2; background: #181a20; }
    #stage { width: 100%; height: 1fr; }
    #meta, #paint-bar { height: 1; padding: 0 1; color: #9aa1ab; }
    #stage-scroll { width: 100%; height: 1fr; background: #000; }
    #preview { width: auto; height: auto; background: #000; color: #e8e6e3; }
    #deck { height: auto; max-height: 16; background: #181a20; border-top: solid #2c3038; }
    #inspector { height: auto; width: 100%; }
    #notes { height: 6; }
    .toolbar { height: 1; padding: 0 1; background: #181a20; }
    #path { width: 1fr; height: 1; }
    Button {
        height: 1;
        min-height: 1;
        min-width: 0;
        margin: 0 1 0 0;
        padding: 0 1;
        border: none;
    }
    Input { height: 1; min-height: 1; }
    """
    BINDINGS = [
        Binding("ctrl+s", "project", "Project", priority=True),
        Binding("ctrl+e", "paint", "Paint", priority=True),
        Binding("ctrl+y", "copy", "Copy", priority=True),
        Binding("ctrl+f", "focus_filter", "Fonts", priority=True),
        Binding("ctrl+t", "focus_text", "Type", priority=True),
        Binding("ctrl+b", "favourite", "Favourite", priority=True),
        Binding("ctrl+o", "open", "Open", show=False, priority=True),
        Binding("ctrl+left", "section_prev", show=False, priority=True),
        Binding("ctrl+right", "section_next", show=False, priority=True),
        Binding("escape", "back", "Back", priority=True),
    ]

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self._opened = project
        self._families: list[FontFamily] = []
        self._family_by_key: dict[str, FontFamily] = {}
        self._by_id: dict[str, FontInfo] = {}
        self._picked: dict[str, str] = {}
        self.font_id: str | None = None
        self._font_at = 0
        self._updating = False
        self._ui_ready = False
        self._rendering = False
        self.last_banner: Banner | None = None
        self._relations = RelationPalette()
        self._source: Grid | None = None
        self._source_key: tuple | None = None
        self._source_missing: tuple[str, ...] = ()
        self._source_folded = False
        self._role_sig: tuple | None = None
        self._animation = Animation()
        self._frame = 0
        self._anim_timer = None
        self._stops: tuple[Color, ...] | None = None
        self._outline_stops: tuple[Color, ...] | None = None
        self._bands = False
        self._outline_bands = False
        self._palettes = dict(load_palettes())
        self._presets = load_presets()
        self._symbols = load_symbols()
        self._patches: dict[tuple[int, int], Cell] = {}
        self._letters: dict[str, Grid] = {}
        self._paint = False
        self._paint_target = "banner"
        self._cursor = (0, 0)
        self._letter_cursor = (0, 0)
        self._letter = "m"
        self._paint_colour = "keep"
        self._owned: Path | None = None
        self._pending_roles: dict | None = None
        self._section = "look"
        self.notes = ""
        self._anchor: tuple | None = None
        self.knobs = {
            "preset": "rainbow",
            "gradient": "on",
            "palette": "rainbow",
            "direction": "horizontal",
            "engine": "figlet",
            "format": "ansi",
            "recall": "",
            "outline": "off",
            "outline-mode": "shade",
            "symbol": "░",
            "outline-colour": "slate",
            "outline-gradient": "off",
            "outline-direction": "horizontal",
            "outline-speed": "1",
            "outline-distance": "0",
            "outline-place": "both",
            "outline-scope": "word",
            "sides": "tblr",
            "odx": "0",
            "ody": "0",
            "shadow": "off",
            "dx": "1",
            "dy": "1",
            "shadow-colour": "ink",
            "shadow-symbol": "same",
            "grad-which": "letters",
            "blend": "smooth",
            "stop": "0",
            "stop-h": "0",
            "stop-s": "100",
            "stop-v": "100",
            "hue": "0",
            "role": "",
            "link": "on",
            "focus-role": "off",
            "role-h": "0",
            "role-s": "100",
            "role-v": "100",
            "animation": "none",
            "anim-speed": "1",
            "anim-direction": "forward",
            "anim-travel": "360",
            "anim-layers": "all",
            "trace-pattern": "outline",
            "trace-reveal": "draw",
        }

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="fonts"):
            yield Input(value="meow", placeholder="Words", id="text", compact=True, max_length=240)
        with Vertical(id="stage"):
            yield Static("", id="meta")
            yield Static("", id="paint-bar")
            with ScrollableContainer(id="stage-scroll"):
                yield BannerView("", id="preview")
        with Vertical(id="deck"):
            yield Input(placeholder="Font name", id="filter", compact=True)
            yield Static("", id="matches")
            yield Board(_SECTIONS, id="inspector")
            yield TextArea(id="notes")
        with Horizontal(classes="toolbar"):
            yield Input(value="banner.ans", id="path", compact=True)
            yield Button("Export", id="export")
            yield Button("Copy", id="copy")
            yield Button("Open", id="open")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#paint-bar", Static).display = False
        self.query_one("#filter", Input).display = False
        self.query_one("#matches", Static).display = False
        self.query_one("#notes", TextArea).display = False
        self._ui_ready = True
        self._fill_fonts()
        self._refresh_board()
        if self._opened is not None:
            self._apply_project(self._opened)
        self.query_one("#inspector", Board).focus()

    def on_board_turn(self, event: Board.Turn) -> None:
        self._cycle_knob(event.knob, event.delta)

    def on_board_go(self, event: Board.Go) -> None:
        self._go(event.section)

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._ui_ready or self._updating:
            return
        if event.input.id == "filter":
            self._font_at = 0
            self._move_font(0)
        elif event.input.id == "text":
            self._patches.clear()
            self._render_preview()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            self._close_search()
            self.query_one("#inspector", Board).focus()
        elif event.input.id == "text":
            self.query_one("#inspector", Board).focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.notes = event.text_area.text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "export":
            self.action_export()
        elif button == "copy":
            self.action_copy()
        elif button == "open":
            self.action_open()

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Input) and focused.id == "filter" and event.key in {"up", "down", "pageup", "pagedown"}:
            step = 5 if event.key in {"pageup", "pagedown"} else 1
            if event.key in {"up", "pageup"}:
                step = -step
            self._move_font(step)
            event.stop()
            return
        if not self._paint or not isinstance(focused, BannerView):
            return
        if event.key in {"left", "right", "up", "down"}:
            self._move_cursor(event.key)
            event.stop()
            return
        if event.key == "tab":
            self._paint_target = "letter" if self._paint_target == "banner" else "banner"
            self._refresh_paint_bar()
            self._show_frame()
            event.stop()
            return
        if event.character in {",", "."}:
            self._step_letter(1 if event.character == "." else -1)
            event.stop()
            return
        if event.character in {"[", "]"}:
            self._step_paint_colour(1 if event.character == "]" else -1)
            event.stop()
            return
        if event.key in {"backspace", "delete"}:
            self._paint_char(" ")
            event.stop()
            return
        if event.character and event.character.isprintable():
            self._paint_char(event.character)
            event.stop()

    def _close_search(self) -> None:
        self.query_one("#filter", Input).display = False
        self.query_one("#matches", Static).display = False
        self.query_one("#inspector", Board).display = True
        self.query_one("#notes", TextArea).display = self._section == "notes"

    def action_focus_filter(self) -> None:
        self._font_at = self._index_of_current_font()
        self.query_one("#inspector", Board).display = False
        self.query_one("#notes", TextArea).display = False
        field = self.query_one("#filter", Input)
        field.display = True
        field.focus()
        self._show_matches()

    def action_focus_text(self) -> None:
        self._close_search()
        self.query_one("#text", Input).focus()

    def action_back(self) -> None:
        if self._paint:
            self.action_paint()
            return
        self._close_search()
        if self._section == "notes":
            self._go("look")
            return
        self.query_one("#inspector", Board).focus()

    def action_section_next(self) -> None:
        self._step_section(1)

    def action_section_prev(self) -> None:
        self._step_section(-1)

    def action_project(self) -> None:
        self._render_preview()
        font = self._by_id.get(self.font_id or "")
        project = self._project()
        filename = project_filename(project.text, font.name if font else project.font_name)
        try:
            path = allocate_path(Path.cwd(), filename, self._owned)
            save_project(path, project)
        except (OSError, RenderError) as exc:
            self.notify(str(exc), severity="error")
            return
        self._owned = path
        self.query_one("#path", Input).value = str(path)
        self.notify(f"Saved {path.name}")

    def action_export(self) -> None:
        self._render_preview()
        if self.last_banner is None or not self.last_banner.grid.rows:
            self.notify("Nothing to export", severity="warning")
            return
        fmt = self._choice("format", "ansi")
        path = Path(self.query_one("#path", Input).value).expanduser()
        if path.suffix == ".meowtext":
            path = path.with_suffix(_SUFFIX.get(fmt, ".ans"))
        try:
            data = export(self.last_banner.grid, fmt)
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, bytes):
                path.write_bytes(data)
            else:
                path.write_text(data, encoding="utf-8")
        except (OSError, RenderError) as exc:
            self.notify(str(exc), severity="error")
            return
        self.notify(f"Wrote {path}")

    def action_copy(self) -> None:
        self._render_preview()
        if self.last_banner is None or not self.last_banner.grid.rows:
            self.notify("Nothing to copy", severity="warning")
            return
        fmt = self._choice("format", "ansi")
        if fmt == "png":
            self.notify("PNG is binary. Export it, or copy ANSI instead.", severity="warning")
            return
        try:
            data = export(self.last_banner.grid, fmt)
        except RenderError as exc:
            self.notify(str(exc), severity="error")
            return
        self.copy_to_clipboard(str(data))
        self.notify(f"Copied {fmt}")

    def action_open(self) -> None:
        path = Path(self.query_one("#path", Input).value).expanduser()
        if path.suffix != ".meowtext":
            self.notify("Open a .meowtext project", severity="warning")
            return
        try:
            project = load_project(path)
        except RenderError as exc:
            self.notify(str(exc), severity="error")
            return
        self._owned = path
        self._apply_project(project)
        self.notify(f"Opened {path.name}")

    def action_favourite(self) -> None:
        self._render_preview()
        try:
            path = save_favourite(self._project())
        except OSError as exc:
            self.notify(str(exc), severity="error")
            return
        self.knobs["recall"] = str(path)
        self._refresh_board()
        self.notify(f"Favourite {path.name}")

    def action_paint(self) -> None:
        self._paint = not self._paint
        self.query_one("#paint-bar", Static).display = self._paint
        if self._paint:
            self._letter = self._first_letter()
            self.query_one("#preview", Static).focus()
        else:
            self.query_one("#inspector", Board).focus()
        self._refresh_paint_bar()
        self._show_frame()

    def _project(self) -> Project:
        font = self._by_id.get(self.font_id or "")
        style = self._style()
        style.hue = self._relations.hue
        return Project(
            text=self.query_one("#text", Input).value,
            engine=self._engine_name(),
            font_name=font.name if font else "",
            font_source=font.source if font else "",
            font_index=font.index if font else 0,
            style=style,
            hue=self._relations.hue,
            roles=roles_from_palette(self._relations),
            animation=self._animation.clone(),
            notes=self.notes,
            patches=tuple((x, y, cell.clone()) for (x, y), cell in sorted(self._patches.items())),
            letters={char: grid.copy() for char, grid in self._letters.items()},
        )

    def _apply_project(self, project: Project) -> None:
        self._updating = True
        try:
            self.query_one("#text", Input).value = project.text
            self.knobs["engine"] = project.engine if project.engine in {"figlet", "toilet", "tdf"} else "figlet"
            self.query_one("#notes", TextArea).text = project.notes
            self.notes = project.notes
            self._write_style(project.style)
            self._stops = project.style.stops
            self._outline_stops = project.style.outline_stops
            self._bands = project.style.bands
            self._outline_bands = project.style.outline_bands
            self._write_animation(project.animation)
            self._patches = {(x, y): cell.clone() for x, y, cell in project.patches}
            self._letters = {char: grid.copy() for char, grid in project.letters.items()}
            self._relations = RelationPalette(hue=project.hue)
            self._relations.roles = {slot: role.clone() for slot, role in project.roles.items()}
            self.knobs["hue"] = str(int(round(project.hue)) % 360)
            self._pending_roles = self._relations.roles
        finally:
            self._updating = False
        self.font_id = None
        self._source_key = None
        self._fill_fonts()
        self._select_project_font(project)
        self._sync_stop_numbers()
        self._refresh_board()
        self._render_preview()

    def _select_project_font(self, project: Project) -> None:
        match = None
        for font in self._by_id.values():
            if font.name == project.font_name and font.index == project.font_index:
                if not project.font_source or Path(font.source).name == Path(project.font_source).name or font.source == project.font_source:
                    match = font
                    break
        if match is None:
            for font in self._by_id.values():
                if font.name.lower() == project.font_name.lower():
                    match = font
                    break
        if match is None:
            return
        self.font_id = match.id
        family = self._family_for_font(match.id)
        if family is not None:
            self._picked[family.key] = match.id

    def _choice(self, key: str, default: str = "") -> str:
        value = self.knobs.get(key, default)
        return default if value is None or value == "" else str(value)

    def _engine_name(self) -> str:
        return self._choice("engine", "figlet")

    def _go(self, section: str) -> None:
        self._section = section
        notes = self.query_one("#notes", TextArea)
        searching = self.query_one("#filter", Input).display
        notes.display = section == "notes" and not searching
        self._refresh_board(reset=True)
        if section == "notes":
            notes.focus()
        elif not isinstance(self.focused, Input):
            self.query_one("#inspector", Board).focus()

    def _step_section(self, delta: int) -> None:
        names = [name for name, _label in _SECTIONS]
        index = names.index(self._section) if self._section in names else 0
        self._go(names[(index + delta) % len(names)])

    def _cycle_knob(self, key: str, delta: int) -> None:
        if key == "variant":
            self._cycle_variant(delta)
            return
        if key == "add-stop":
            self._add_stop()
            return
        if key == "remove-stop":
            self._remove_stop()
            return
        if key == "split":
            self._split_role()
            return
        if not self._enabled(key):
            return
        if key in _NUMBERS:
            self._nudge_number(key, delta * _NUMBERS[key])
            return
        options = self._options(key)
        if not options:
            return
        values = [value for _label, value in options]
        current = self.knobs.get(key, values[0])
        index = values.index(current) if current in values else 0
        self._set_knob(key, values[(index + delta) % len(values)])

    def _set_knob(self, key: str, value: str) -> None:
        self.knobs[key] = value
        if self._updating:
            return
        if key == "preset":
            self._apply_preset(value)
            return
        if key == "engine":
            self.font_id = None
            self._letters.clear()
            self._patches.clear()
            self._fill_fonts()
            return
        if key == "recall" and value:
            try:
                self._apply_project(load_favourite(Path(value)))
            except RenderError as exc:
                self.notify(str(exc), severity="error")
            return
        if key.startswith("anim") or key == "animation" or key.startswith("trace"):
            self._arm_animation()
        elif key in {"stop", "stop-h", "stop-s", "stop-v", "blend", "grad-which"}:
            self._apply_stop(key)
        elif key in {"hue", "role", "link", "focus-role", "role-h", "role-s", "role-v"}:
            self._apply_role(key)
        self._sync_preset_selection()
        self._refresh_board()
        self._render_preview()

    def _nudge_number(self, key: str, delta: int) -> None:
        try:
            value = int(self.knobs.get(key, "0"))
        except ValueError:
            value = 0
        if key in {"odx", "ody", "dx", "dy"}:
            value = max(-8, min(8, value + delta))
        elif key in {"stop-s", "stop-v", "role-s", "role-v"}:
            value = max(0, min(100, value + delta))
        else:
            value = (value + delta) % 360
        self._set_knob(key, str(value))

    def _enabled(self, key: str) -> bool:
        gradient = self.knobs.get("gradient") == "on"
        outlined = self.knobs.get("outline") == "on"
        adaptive = self.knobs.get("outline-mode") in {"contour", "heavy", "double", "blocks"}
        if key in {"palette", "direction"}:
            return gradient
        if key == "symbol":
            return outlined and not adaptive
        if key.startswith("outline-") or key in {"sides", "odx", "ody"}:
            return outlined
        if key in {"role-h", "role-s", "role-v"}:
            return self.knobs.get("link") != "on"
        return True

    def _options(self, key: str) -> list[tuple[str, str]]:
        if key == "preset":
            options = [(name, name) for name in self._presets]
            if self.knobs.get("preset") not in self._presets:
                options.append(("custom", "custom"))
            return options
        if key in {"gradient", "outline", "shadow", "link", "focus-role"}:
            return list(_ON)
        if key == "palette":
            return [(name, name) for name in self._palettes] + [("edited", "edited")]
        if key == "direction":
            return list(GRADIENT_DIRECTIONS)
        if key == "engine":
            return list(_ENGINES)
        if key == "format":
            return list(_FORMATS)
        if key == "recall":
            return [("(none)", "")] + [(path.stem, str(path)) for path in list_favourites()]
        if key == "outline-mode":
            return list(OUTLINE_MODES)
        if key == "symbol":
            options = list(self._symbols)
            if self.knobs.get("symbol") not in {value for _label, value in options}:
                options.append((self.knobs.get("symbol", "░"), self.knobs.get("symbol", "░")))
            return options
        if key == "outline-colour" or key == "shadow-colour":
            return [(name, name) for name in COLOURS]
        if key == "outline-gradient":
            return [("flat", "off")] + [(name, name) for name in self._palettes] + [("edited", "edited")]
        if key == "outline-direction":
            return list(OUTLINE_DIRECTIONS)
        if key in {"outline-speed", "anim-speed"}:
            return list(ANIM_SPEEDS)
        if key == "outline-distance":
            return list(OUTLINE_DISTANCES)
        if key == "outline-place":
            return list(OUTLINE_PLACES)
        if key == "outline-scope":
            return list(OUTLINE_SCOPES)
        if key == "sides":
            options = list(_SIDES)
            if self.knobs.get("sides") not in {value for _label, value in options}:
                options.append((self.knobs.get("sides", "tblr"), self.knobs.get("sides", "tblr")))
            return options
        if key == "shadow-symbol":
            return [("same", "same")] + list(self._symbols)
        if key == "grad-which":
            return [("Letters", "letters"), ("Outline", "outline")]
        if key == "blend":
            return [("Smooth", "smooth"), ("Bands", "bands")]
        if key == "stop":
            stops = self._active_stops()
            return [(f"Stop {index + 1}", str(index)) for index in range(len(stops))]
        if key == "animation":
            return list(ANIMATIONS)
        if key == "anim-direction":
            return list(ANIM_DIRECTIONS)
        if key == "anim-travel":
            return list(ANIM_TRAVELS)
        if key == "anim-layers":
            return list(ANIM_LAYERS)
        if key == "trace-pattern":
            return list(TRACE_PATTERNS)
        if key == "trace-reveal":
            return list(TRACE_REVEALS)
        if key == "role":
            source = self._source or Grid()
            return [(f"{self._relations.roles[slot].name}", str(slot)) for slot in used_slots(source) if slot in self._relations.roles]
        return []

    def _text(self, key: str) -> str:
        value = self.knobs.get(key, "")
        for label, item in self._options(key):
            if item == value:
                return label
        return value or "—"

    def _rows(self) -> list[Knob]:
        def knob(key: str, hotkey: str, label: str) -> Knob:
            return Knob(key, hotkey, label, self._text(key), self._enabled(key))

        section = self._section
        if section == "look":
            rows = [
                knob("preset", "p", "Look"),
                knob("gradient", "g", "Gradient"),
                knob("palette", "c", "Palette"),
                knob("direction", "d", "Direction"),
                knob("engine", "e", "Engine"),
                knob("format", "x", "Export"),
                knob("recall", "r", "Recall"),
            ]
        elif section == "outline":
            rows = [
                knob("outline", "o", "Outline"),
                knob("outline-mode", "m", "Mode"),
                knob("symbol", "y", "Symbol"),
                knob("outline-colour", "c", "Colour"),
                knob("outline-gradient", "g", "Gradient"),
                knob("outline-direction", "d", "Direction"),
                knob("outline-speed", "s", "Speed"),
                knob("outline-distance", "i", "Distance"),
                knob("outline-place", "p", "Place"),
                knob("outline-scope", "a", "Around"),
                knob("sides", "e", "Sides"),
                knob("odx", "h", "Shift across"),
                knob("ody", "v", "Shift down"),
            ]
        elif section == "shadow":
            rows = [
                knob("shadow", "o", "Shadow"),
                knob("dx", "x", "Across"),
                knob("dy", "y", "Down"),
                knob("shadow-colour", "c", "Colour"),
                knob("shadow-symbol", "g", "Symbol"),
            ]
        elif section == "colour":
            rows = [
                knob("grad-which", "w", "Editing"),
                knob("blend", "b", "Blend"),
                knob("stop", "n", "Stop"),
                knob("stop-h", "h", "Hue"),
                knob("stop-s", "s", "Saturation"),
                knob("stop-v", "t", "Value"),
            ]
            if used_slots(self._source or Grid()):
                rows.extend(
                    [
                        knob("hue", "u", "Role hue"),
                        knob("role", "r", "Role"),
                        knob("link", "l", "Link"),
                        knob("focus-role", "f", "Focus"),
                        knob("role-h", "j", "This hue"),
                        knob("role-s", "a", "This saturation"),
                        knob("role-v", "i", "This value"),
                        Knob("split", "k", "Split", "the sections of this role", True),
                    ]
                )
        elif section == "animate":
            rows = [
                knob("animation", "a", "Motion"),
                knob("anim-speed", "s", "Speed"),
                knob("anim-direction", "d", "Direction"),
                knob("anim-travel", "t", "Travel"),
                knob("anim-layers", "l", "Moves"),
                knob("trace-pattern", "p", "Trace"),
                knob("trace-reveal", "r", "Trace does"),
            ]
        else:
            rows = []
        family = self._current_family()
        if family is not None and len(family.members) > 1 and section == "look":
            chosen = self._picked.get(family.key, family.members[0].id)
            label = next((member.name for member in family.members if member.id == chosen), family.members[0].name)
            rows.insert(0, Knob("variant", "v", "Font colour", label, True))
        return rows

    def _refresh_board(self, reset: bool = False) -> None:
        board = self.query_one("#inspector", Board)
        board.show(self._section, self._rows(), 0 if reset else None)

    def _apply_preset(self, name: str) -> None:
        style = self._presets.get(name)
        if style is None:
            return
        self._updating = True
        try:
            self._write_style(style)
            self._stops = style.stops
            self._outline_stops = style.outline_stops
            self._bands = style.bands
            self._outline_bands = style.outline_bands
            self.knobs["preset"] = name
        finally:
            self._updating = False
        self._sync_stop_numbers()
        self._refresh_board()
        self._render_preview()

    def _write_style(self, style: BannerStyle) -> None:
        self.knobs["gradient"] = "on" if style.gradient else "off"
        self.knobs["palette"] = "edited" if style.stops else (style.gradient or "rainbow")
        self.knobs["direction"] = style.direction
        self.knobs["outline"] = "on" if style.outline else "off"
        self.knobs["outline-mode"] = style.outline_mode
        self.knobs["symbol"] = style.outline_char
        self.knobs["outline-colour"] = colour_name(style.outline_color)
        self.knobs["outline-gradient"] = "edited" if style.outline_stops else (style.outline_gradient or "off")
        self.knobs["outline-direction"] = style.outline_direction
        self.knobs["outline-speed"] = self._nearest_speed(style.outline_speed)
        self.knobs["outline-distance"] = str(style.outline_distance)
        self.knobs["outline-place"] = style.outline_place
        self.knobs["outline-scope"] = style.outline_scope
        self.knobs["sides"] = style.outline_sides if style.outline_sides in {value for _label, value in _SIDES} else (style.outline_sides or "none")
        self.knobs["odx"] = str(style.outline_dx)
        self.knobs["ody"] = str(style.outline_dy)
        self.knobs["shadow"] = "on" if style.shadow else "off"
        self.knobs["dx"] = str(style.shadow_dx)
        self.knobs["dy"] = str(style.shadow_dy)
        self.knobs["shadow-colour"] = colour_name(style.shadow_color)
        self.knobs["shadow-symbol"] = style.shadow_char or "same"

    def _sync_preset_selection(self) -> None:
        match = next((name for name, preset in self._presets.items() if preset == self._style()), "custom")
        self.knobs["preset"] = match

    def _style(self) -> BannerStyle:
        gradient_on = self.knobs.get("gradient") == "on"
        palette = self._choice("palette", "rainbow")
        outline_gradient = self._choice("outline-gradient", "off")
        shadow_symbol = self._choice("shadow-symbol", "same")
        sides = self.knobs.get("sides", "tblr")
        if sides == "none":
            sides = ""
        return BannerStyle(
            gradient=None if not gradient_on else ("rainbow" if palette == "edited" else palette),
            direction=self._choice("direction", "horizontal"),
            stops=self._stops,
            bands=self._bands,
            outline=self.knobs.get("outline") == "on",
            outline_char=self._choice("symbol", "░")[:1],
            outline_color=COLOURS.get(self._choice("outline-colour", "slate"), DEFAULT_OUTLINE),
            outline_mode=self._choice("outline-mode", "shade"),
            outline_gradient=None if outline_gradient in {"off", "edited"} else outline_gradient,
            outline_stops=self._outline_stops,
            outline_direction=self._choice("outline-direction", "horizontal"),
            outline_speed=float(self._choice("outline-speed", "1") or 1),
            outline_bands=self._outline_bands,
            outline_sides=sides,
            outline_distance=self._int("outline-distance", 0),
            outline_place=self._choice("outline-place", "both"),
            outline_scope=self._choice("outline-scope", "word"),
            outline_dx=self._int("odx", 0),
            outline_dy=self._int("ody", 0),
            shadow=self.knobs.get("shadow") == "on",
            shadow_dx=self._int("dx", 1),
            shadow_dy=self._int("dy", 1),
            shadow_color=COLOURS.get(self._choice("shadow-colour", "ink"), DEFAULT_SHADOW),
            shadow_char=None if shadow_symbol == "same" else shadow_symbol[:1],
        )

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.knobs.get(key, default))
        except ValueError:
            return default

    def _nearest_speed(self, speed: float) -> str:
        choices = [float(value) for _label, value in ANIM_SPEEDS]
        nearest = min(choices, key=lambda item: abs(item - speed))
        return str(int(nearest)) if nearest == int(nearest) else str(nearest)

    def _write_animation(self, motion: Animation) -> None:
        self.knobs["animation"] = motion.name if motion.name in {value for _label, value in ANIMATIONS} else "none"
        self.knobs["anim-speed"] = self._nearest_speed(motion.speed)
        self.knobs["anim-direction"] = motion.direction
        self.knobs["anim-travel"] = str(motion.travel if str(motion.travel) in {value for _label, value in ANIM_TRAVELS} else 360)
        self.knobs["anim-layers"] = motion.layers
        self.knobs["trace-pattern"] = motion.pattern
        self.knobs["trace-reveal"] = motion.reveal
        self._arm_animation()

    def _arm_animation(self) -> None:
        self._animation = Animation(
            name=self._choice("animation", "none"),
            speed=float(self._choice("anim-speed", "1") or 1),
            direction=self._choice("anim-direction", "forward"),
            travel=int(self._choice("anim-travel", "360") or 360),
            layers=self._choice("anim-layers", "all"),
            pattern=self._choice("trace-pattern", "outline"),
            reveal=self._choice("trace-reveal", "draw"),
        )
        self._frame = 0
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None
        if self._animation.name != "none":
            self._anim_timer = self.set_interval(0.12, self._tick_animation)
        if not self._updating:
            self._render_preview()

    def _tick_animation(self) -> None:
        self._frame += 1
        self._render_preview()

    def _active_stops(self) -> tuple[Color, ...]:
        fallback = self._palettes.get("rainbow", (Color(255, 0, 64), Color(0, 190, 255)))
        if self._choice("grad-which", "letters") == "outline":
            if self._outline_stops:
                return self._outline_stops
            name = self._choice("outline-gradient", "off")
            return self._palettes.get(name, fallback)
        if self._stops:
            return self._stops
        return self._palettes.get(self._choice("palette", "rainbow"), fallback)

    def _store_stops(self, stops: tuple[Color, ...]) -> None:
        if self._choice("grad-which", "letters") == "outline":
            self._outline_stops = stops
            self.knobs["outline"] = "on"
            self.knobs["outline-gradient"] = "edited"
        else:
            self._stops = stops
            self.knobs["gradient"] = "on"
            self.knobs["palette"] = "edited"

    def _sync_stop_numbers(self) -> None:
        stops = self._active_stops()
        try:
            index = int(self.knobs.get("stop", "0"))
        except ValueError:
            index = 0
        index = min(max(index, 0), len(stops) - 1)
        hue, sat, val = rgb_to_hsv(stops[index])
        self.knobs["stop"] = str(index)
        self.knobs["stop-h"] = str(int(round(hue)) % 360)
        self.knobs["stop-s"] = str(int(round(sat * 100)))
        self.knobs["stop-v"] = str(int(round(val * 100)))
        self.knobs["blend"] = "bands" if (self._outline_bands if self._choice("grad-which") == "outline" else self._bands) else "smooth"

    def _apply_stop(self, key: str) -> None:
        if key == "blend":
            bands = self.knobs.get("blend") == "bands"
            if self._choice("grad-which") == "outline":
                self._outline_bands = bands
            else:
                self._bands = bands
            return
        if key == "grad-which":
            self._sync_stop_numbers()
            return
        if key == "stop":
            self._sync_stop_numbers()
            return
        stops = list(self._active_stops())
        try:
            index = int(self.knobs.get("stop", "0"))
            hue = float(self.knobs.get("stop-h", "0"))
            sat = float(self.knobs.get("stop-s", "100")) / 100
            val = float(self.knobs.get("stop-v", "100")) / 100
        except ValueError:
            return
        if index < 0 or index >= len(stops):
            return
        stops[index] = hsv_to_rgb(hue, sat, val)
        self._store_stops(tuple(stops))

    def _add_stop(self) -> None:
        if self._section != "colour":
            return
        stops = list(self._active_stops())
        stops.append(stops[-1] if stops else Color(255, 255, 255))
        self._store_stops(tuple(stops))
        self.knobs["stop"] = str(len(stops) - 1)
        self._sync_stop_numbers()
        self._refresh_board()
        self._render_preview()

    def _remove_stop(self) -> None:
        if self._section != "colour":
            return
        stops = list(self._active_stops())
        if len(stops) <= 2:
            self.notify("A gradient keeps at least two stops")
            return
        try:
            index = int(self.knobs.get("stop", "0"))
        except ValueError:
            index = len(stops) - 1
        del stops[max(0, min(index, len(stops) - 1))]
        self._store_stops(tuple(stops))
        self._sync_stop_numbers()
        self._refresh_board()
        self._render_preview()

    def _selected_slot(self) -> int | None:
        try:
            slot = int(self.knobs.get("role", ""))
        except ValueError:
            return None
        return slot

    def _apply_role(self, key: str) -> None:
        if key == "hue":
            self._relations.hue = float(self._int("hue", 0)) % 360
            return
        slot = self._selected_slot()
        if slot is None or slot not in self._relations.roles:
            return
        if key == "link":
            if self.knobs.get("link") == "on":
                self._relations.link_role(slot)
            else:
                self._relations.break_role(slot)
            return
        if key == "role":
            self._sync_role_numbers()
            return
        if key in {"role-h", "role-s", "role-v"} and self.knobs.get("link") != "on":
            self._relations.set_hsv(
                slot,
                float(self._int("role-h", 0)),
                self._int("role-s", 100) / 100,
                self._int("role-v", 100) / 100,
            )

    def _sync_role_numbers(self) -> None:
        slot = self._selected_slot()
        if slot is None or slot not in self._relations.roles:
            return
        role = self._relations.roles[slot]
        if role.linked:
            hue, sat, val = rgb_to_hsv(role.paint(self._relations.hue))
        else:
            hue, sat, val = role.hue, role.sat, role.val
        self.knobs["link"] = "on" if role.linked else "off"
        self.knobs["role-h"] = str(int(round(hue)) % 360)
        self.knobs["role-s"] = str(int(round(sat * 100)))
        self.knobs["role-v"] = str(int(round(val * 100)))

    def _split_role(self) -> None:
        slot = self._selected_slot()
        if slot is None or self._source is None or slot not in self._relations.roles:
            return
        made = self._relations.split(self._source, slot)
        name = self._relations.roles[slot].name
        self.notify(f"{name} is already one section" if made == 0 else f"Split {name} into {made + 1} sections")
        self._role_sig = None
        self._refresh_board()
        self._render_preview()

    def _fill_fonts(self) -> None:
        engine = self._engine_name()
        if engine == "tdf" and not tdf_ready():
            self.query_one("#meta", Static).update("Indexing TheDraw fonts…")
            self.run_worker(self._index_tdf, thread=True, exclusive=True, group="tdf-index")
            return
        fonts = list_fonts(engine)
        self._by_id = {font.id: font for font in fonts}
        self._families = group_fonts(fonts)
        self._family_by_key = {family.key: family for family in self._families}
        if self.font_id not in self._by_id:
            self.font_id = self._default_font_id()
        self._render_preview()

    def _default_font_id(self) -> str | None:
        wanted = {"figlet": "ansi shadow", "toilet": "future"}.get(self._engine_name())
        for family in self._families:
            for member in family.members:
                if wanted and member.name.lower() == wanted:
                    return member.id
        if self._families:
            return self._families[0].members[0].id
        return None

    def _index_tdf(self) -> None:
        load_tdf()
        self.call_from_thread(self._tdf_indexed)

    def _tdf_indexed(self) -> None:
        if self._engine_name() == "tdf":
            self._fill_fonts()

    def _family_for_font(self, font_id: str) -> FontFamily | None:
        for family in self._families:
            if any(member.id == font_id for member in family.members):
                return family
        return None

    def _cycle_variant(self, delta: int) -> None:
        family = self._current_family()
        if family is None or len(family.members) < 2:
            return
        ids = [member.id for member in family.members]
        current = self._picked.get(family.key, ids[0])
        index = ids.index(current) if current in ids else 0
        chosen = ids[(index + delta) % len(ids)]
        self._picked[family.key] = chosen
        self.font_id = chosen
        self._letters.clear()
        self._patches.clear()
        self._refresh_board()
        self._render_preview()

    def _current_family(self) -> FontFamily | None:
        return self._family_for_font(self.font_id or "")

    def _index_of_current_font(self) -> int:
        family = self._current_family()
        matched = self._filtered_fonts()
        if family is None:
            return 0
        for index, item in enumerate(matched):
            if item.key == family.key:
                return index
        return 0

    def _filtered_fonts(self) -> list[FontFamily]:
        query = self.query_one("#filter", Input).value.strip().lower()
        if not query:
            return list(self._families)
        return [
            family
            for family in self._families
            if query in family.stem.lower()
            or any(query in member.name.lower() or query in Path(member.source).name.lower() for member in family.members)
        ]

    def _move_font(self, delta: int) -> None:
        matched = self._filtered_fonts()
        if not matched:
            self._show_matches()
            return
        self._font_at = (self._font_at + delta) % len(matched)
        family = matched[self._font_at]
        chosen = self._picked.get(family.key, family.members[0].id)
        if chosen not in {member.id for member in family.members}:
            chosen = family.members[0].id
        self.font_id = chosen
        self._picked[family.key] = chosen
        self._letters.clear()
        self._patches.clear()
        self._show_matches()
        self._render_preview()

    def _show_matches(self) -> None:
        matched = self._filtered_fonts()
        view = self.query_one("#matches", Static)
        if not matched:
            view.update("No fonts match.")
            view.display = True
            return
        self._font_at = min(self._font_at, len(matched) - 1)
        start = max(0, min(self._font_at - 2, len(matched) - 5))
        lines = [f"{len(matched)} fonts · type to narrow · up down · pgup pgdn · enter keeps"]
        for index in range(start, min(start + 5, len(matched))):
            mark = "▸ " if index == self._font_at else "  "
            lines.append(mark + matched[index].label())
        view.update("\n".join(lines))
        view.display = True

    def _render_preview(self) -> None:
        if not self._ui_ready or self._rendering:
            return
        self._rendering = True
        try:
            self._draw_preview()
        except Exception as exc:
            self._report_crash(exc)
        finally:
            self._rendering = False

    def _report_crash(self, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        try:
            self.query_one("#meta", Static).update(message)
            self.notify(message, severity="error")
        except Exception:
            return

    def _draw_preview(self) -> None:
        style = self._style()
        font = self._by_id.get(self.font_id or "")
        preview = self.query_one("#preview", Static)
        meta = self.query_one("#meta", Static)
        if font is None:
            self.last_banner = None
            self._source = None
            meta.update("No font selected." if self._families or self._engine_name() != "tdf" else "Indexing TheDraw fonts…")
            return
        text = self.query_one("#text", Input).value
        try:
            if not text:
                self._source = None
                self._source_key = None
                banner = Banner(Grid(), font, (), False)
            else:
                letter_sig = tuple((char, _plain(grid)) for char, grid in sorted(self._letters.items()))
                key = (font.id, text, letter_sig)
                if key != self._source_key:
                    source, missing, folded = layout_font(text, font, self._letters or None)
                    if style.outline and style.outline_scope == "letter" and not source.spans:
                        source.spans = measure_spans(font, text)
                    self._source = source
                    self._source_missing = missing
                    self._source_folded = folded
                    self._source_key = key
                    if self._pending_roles is not None:
                        self._relations.roles = self._pending_roles
                        self._pending_roles = None
                    else:
                        self._relations.drop_splits()
                    self._role_sig = None
                elif style.outline and style.outline_scope == "letter" and self._source is not None and not self._source.spans:
                    self._source.spans = measure_spans(font, text)
                assert self._source is not None
                banner = Banner(
                    present(
                        self._source,
                        style,
                        self._relations,
                        animation=self._animation,
                        frame=self._frame,
                        patches=tuple((x, y, cell) for (x, y), cell in self._patches.items()),
                    ),
                    font,
                    self._source_missing,
                    self._source_folded,
                )
        except RenderError as exc:
            self.last_banner = None
            preview.update(self._centered_line(str(exc), "italic #a8a8a8"))
            meta.update(str(exc))
            return
        self.last_banner = banner
        self._note_roles()
        self._show_frame()
        meta.update(self._describe(banner))
        self._refresh_paint_bar()

    def _note_roles(self) -> None:
        source = self._source or Grid()
        slots = used_slots(source)
        if slots:
            self._relations.ensure(source)
        signature = tuple(slots)
        if signature != self._role_sig:
            self._role_sig = signature
            if slots and self.knobs.get("role") not in {str(slot) for slot in slots}:
                self.knobs["role"] = str(slots[0])
            self._sync_role_numbers()
            if self._section == "colour":
                self._refresh_board()

    def _show_frame(self) -> None:
        preview = self.query_one("#preview", Static)
        banner = self.last_banner
        text = self.query_one("#text", Input).value
        if banner is None:
            return
        if not text:
            preview.update(self._centered_line("Type a banner. Ctrl-t jumps to the words.", "italic #888"))
            return
        if not banner.grid.rows:
            preview.update(self._centered_line("Nothing to draw.", "italic #888"))
            return
        focus = self._selected_slot() if self.knobs.get("focus-role") == "on" else None
        cursor = self._cursor if self._paint and self._paint_target == "banner" else None
        width, height = self._view_size()
        across = max(0, (width - banner.grid.width) // 2)
        down = max(0, (height - banner.grid.height) // 2)
        preview.update(to_rich(banner.grid, focus, cursor, (across, down)))
        self._center_scroll(banner.grid.width, banner.grid.height, across, down)

    def _view_size(self) -> tuple[int, int]:
        view = self.query_one("#stage-scroll", ScrollableContainer)
        return view.size.width, view.size.height

    def _centered_line(self, message: str, style: str) -> Text:
        width, height = self._view_size()
        text = Text()
        down = max(0, (height - 1) // 2)
        across = max(0, (width - len(message)) // 2)
        if down:
            text.append("\n" * down)
        if across:
            text.append(" " * across)
        text.append(message, style=style)
        return text

    def _center_scroll(self, grid_width: int, grid_height: int, across: int, down: int) -> None:
        view = self.query_one("#stage-scroll", ScrollableContainer)
        width, height = view.size
        if self._paint and self._paint_target == "banner":
            target = (max(0, self._cursor[0] + across - width // 2), max(0, self._cursor[1] + down - height // 2))
        else:
            target = (
                0 if across else max(0, (grid_width - width) // 2),
                0 if down else max(0, (grid_height - height) // 2),
            )
        anchor = (target, width, height, grid_width, grid_height)
        if anchor == self._anchor:
            return
        self._anchor = anchor
        view.scroll_to(target[0], target[1], animate=False)

    def on_resize(self, event) -> None:
        self._anchor = None
        if self._ui_ready and self.last_banner is not None and not self._rendering:
            try:
                self._show_frame()
            except Exception as exc:
                self._report_crash(exc)

    def _describe(self, banner: Banner) -> str:
        if not banner.grid.rows:
            return banner.font.name
        parts = [f"{banner.grid.width}×{banner.grid.height}", banner.font.engine, banner.font.name]
        if banner.font.kind:
            parts.append(banner.font.kind)
        if self._letters:
            parts.append("letters placed separately")
        if banner.folded:
            parts.append("used the other letter case")
        if banner.missing:
            parts.append("missing " + "".join(banner.missing[:16]))
        if self._paint:
            parts.append("painting the banner" if self._paint_target == "banner" else f"painting {self._letter}")
        return " · ".join(parts)

    def _move_cursor(self, key: str) -> None:
        if self._paint_target == "letter":
            glyph = self._ensure_letter(self._letter)
            x, y = self._letter_cursor
            width = max(glyph.width, 1)
            height = max(glyph.height, 1)
        else:
            grid = self.last_banner.grid if self.last_banner else Grid()
            x, y = self._cursor
            width = max(grid.width, 1)
            height = max(grid.height, 1)
        if key == "left":
            x = max(0, x - 1)
        elif key == "right":
            x = min(width - 1, x + 1)
        elif key == "up":
            y = max(0, y - 1)
        else:
            y = min(height - 1, y + 1)
        if self._paint_target == "letter":
            self._letter_cursor = (x, y)
        else:
            self._cursor = (x, y)
        self._refresh_paint_bar()
        self._show_frame()

    def _paint_char(self, char: str) -> None:
        colour = None if self._paint_colour == "keep" else COLOURS.get(self._paint_colour)
        if self._paint_target == "letter":
            glyph = self._ensure_letter(self._letter)
            x, y = self._letter_cursor
            painted = glyph.get(x, y).clone()
            painted.char = char
            if colour is not None:
                painted.fg = colour
            glyph.set(x, y, painted)
            self._source_key = None
            self._render_preview()
            return
        if self.last_banner is None:
            return
        x, y = self._cursor
        painted = self.last_banner.grid.get(x, y).clone()
        painted.char = char
        if colour is not None:
            painted.fg = colour
        self._patches[(x, y)] = painted
        self._render_preview()

    def _ensure_letter(self, char: str) -> Grid:
        glyph = self._letters.get(char)
        if glyph is not None and glyph.height:
            return glyph
        font = self._by_id.get(self.font_id or "")
        glyph = layout_font(char, font)[0] if font is not None else Grid([[Cell(char)]])
        if glyph.height == 0:
            glyph = Grid([[Cell(char)]])
        self._letters[char] = glyph
        return glyph

    def _first_letter(self) -> str:
        for char in self.query_one("#text", Input).value:
            if char not in {" ", "\n", "\t"}:
                return char
        return "m"

    def _step_letter(self, delta: int) -> None:
        chars = [char for char in self.query_one("#text", Input).value if char not in {" ", "\n", "\t"}]
        if not chars:
            return
        try:
            index = chars.index(self._letter)
        except ValueError:
            index = 0
        self._letter = chars[(index + delta) % len(chars)]
        self._letter_cursor = (0, 0)
        self._refresh_paint_bar()

    def _step_paint_colour(self, delta: int) -> None:
        index = _PAINT_COLOURS.index(self._paint_colour) if self._paint_colour in _PAINT_COLOURS else 0
        self._paint_colour = _PAINT_COLOURS[(index + delta) % len(_PAINT_COLOURS)]
        self._refresh_paint_bar()

    def _refresh_paint_bar(self) -> None:
        bar = self.query_one("#paint-bar", Static)
        if not self._paint:
            return
        if self._paint_target == "letter":
            where = f"letter {self._letter} {self._letter_cursor[0]},{self._letter_cursor[1]}"
        else:
            where = f"banner {self._cursor[0]},{self._cursor[1]}"
        bar.update(f"Paint {where} · colour {self._paint_colour} · [ ] colour · , . letter · tab switches · esc stops")


def _plain(grid: Grid) -> str:
    return "\n".join("".join(cell.char or " " for cell in row) for row in grid.rows)
