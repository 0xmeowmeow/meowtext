"""Textual frontend. The banner engine does not depend on this module."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, Select, Static, Switch, TextArea
from textual.widgets.option_list import Option

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
    OUTLINE_DISTANCES,
    OUTLINE_MODES,
    OUTLINE_PLACES,
    OUTLINE_SCOPES,
    PRESETS,
    TRACE_PATTERNS,
    TRACE_REVEALS,
    Animation,
    BannerStyle,
    colour_name,
)
from meowtext.errors import RenderError
from meowtext.export import export
from meowtext.grid import Cell, Color, Grid
from meowtext.packs import (
    list_favourites,
    load_favourite,
    load_palettes,
    load_presets,
    load_symbols,
    save_favourite,
    save_palette,
    save_preset,
    save_symbol,
)
from meowtext.palette import RelationPalette, hsv_to_rgb, rgb_to_hsv, role_place, used_slots
from meowtext.project import Project, allocate_path, load_project, project_filename, roles_from_palette, save_project
from meowtext.widgets import Cycle

_SUFFIX = {
    "ansi": ".ans",
    "plain": ".txt",
    "html": ".html",
    "json": ".json",
    "png": ".png",
    "kitty": ".kitty",
    "irc": ".irc",
}
_SECTIONS = ("look", "outline", "shadow", "colour", "animate", "notes")
_SECTION_OPTIONS = (
    ("Look", "look"),
    ("Outline", "outline"),
    ("Shadow", "shadow"),
    ("Colour", "colour"),
    ("Animate", "animate"),
    ("Notes", "notes"),
)
_KINDS = (("block", "Block"), ("outline", "Outline"), ("color", "Colour"))
_PAINT_COLOURS = ("keep",) + tuple(COLOURS)


def to_rich(grid: Grid, focus: int | None = None, cursor: tuple[int, int] | None = None) -> Text:
    """Draw the banner. ``focus`` leaves one colour role bright and dims the rest."""

    text = Text()
    if not grid.rows:
        return text
    for y, row in enumerate(grid.rows):
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
    """The preview. It can take focus while you paint, so the arrows stay on the banner."""

    can_focus = True


class MeowText(App):
    """Type a line, pick a font, decorate it, and export the banner."""

    TITLE = "meowtext"
    SUB_TITLE = "left and right cycle a control"
    CSS = """
    Screen { background: #101114; }
    #text { width: 1fr; }
    #engine { width: 24; }
    #middle { height: 1fr; }
    #side { width: 36; height: 1fr; border-right: solid #2c3038; }
    #filter { margin: 0; }
    #variant { height: 1; padding: 0 1; }
    #font-list { height: 1fr; border: none; padding: 0; }
    #stage { width: 1fr; height: 1fr; }
    #inspector { width: 46; height: 1fr; border-left: solid #2c3038; background: #181a20; }
    #section { height: 1; padding: 0 1; background: #22262e; }
    .page { height: 1fr; padding: 0 1; }
    Cycle { height: 1; width: 1fr; }
    #meta, #paint-bar { height: 1; padding: 0 1; color: #9aa1ab; background: #101114; }
    #stage-scroll { height: 1fr; background: #000; border: solid #2c3038; }
    #preview { width: auto; height: auto; padding: 1 2; background: #000; color: #e8e6e3; }
    .toolbar { height: auto; padding: 0 1; background: #181a20; }
    Label.tag { width: auto; height: 1; padding: 0 1 0 0; color: #c4c8d0; }
    #dx, #dy, #odx, #ody, #hue, #role-h, #role-s, #role-v, #stop-h, #stop-s, #stop-v { width: 8; }
    #role { width: 1fr; }
    #path, #palette-name, #preset-name, #custom-symbol { width: 1fr; }
    #notes { height: 1fr; }
    #favourites { height: 8; }
    Button { margin: 0 1 0 0; }
    """
    BINDINGS = [
        Binding("ctrl+s", "project", "Project"),
        Binding("ctrl+e", "paint", "Paint"),
        Binding("ctrl+y", "copy", "Copy"),
        Binding("ctrl+f", "focus_filter", "Find"),
        Binding("ctrl+t", "focus_text", "Text"),
        Binding("ctrl+b", "favourite", "Favourite"),
        Binding("ctrl+o", "open", "Open", show=False),
        Binding("ctrl+left", "section_prev", show=False, priority=True),
        Binding("ctrl+right", "section_next", show=False, priority=True),
    ]

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self._opened = project
        self._families: list[FontFamily] = []
        self._family_by_key: dict[str, FontFamily] = {}
        self._by_id: dict[str, FontInfo] = {}
        self._picked: dict[str, str] = {}
        self.font_id: str | None = None
        self._updating = False
        self._ui_ready = False
        self.last_banner: Banner | None = None
        self._relations = RelationPalette()
        self._source: Grid | None = None
        self._source_key: tuple | None = None
        self._source_missing: tuple[str, ...] = ()
        self._source_folded = False
        self._role_sig: tuple | None = None
        self._role_echoes = 0
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="toolbar"):
            yield Input(value="meow", placeholder="Banner text", id="text", compact=True, max_length=240)
            yield Cycle((("FIGlet", "figlet"), ("TOIlet", "toilet"), ("TheDraw", "tdf")), "figlet", id="engine")
        with Horizontal(id="middle"):
            with Vertical(id="side"):
                yield Input(placeholder="Filter fonts", id="filter", compact=True)
                yield Cycle((("—", ""),), "", id="variant", label="Colour")
                yield OptionList(id="font-list")
            with Vertical(id="stage"):
                yield Static("", id="meta")
                yield Static("", id="paint-bar")
                with ScrollableContainer(id="stage-scroll"):
                    yield BannerView("", id="preview")
            with Vertical(id="inspector"):
                yield Cycle(_SECTION_OPTIONS, "look", id="section", label="Section")
                yield from self._pages()
        with Horizontal(classes="toolbar"):
            yield Cycle(
                (
                    ("ANSI", "ansi"),
                    ("Plain", "plain"),
                    ("HTML", "html"),
                    ("JSON", "json"),
                    ("PNG", "png"),
                    ("Kitty", "kitty"),
                    ("IRC", "irc"),
                ),
                "ansi",
                id="format",
                label="Export",
            )
            yield Input(value="banner.ans", id="path", compact=True)
            yield Button("Export", id="export")
            yield Button("Copy", id="copy")
            yield Button("Open", id="open")
        yield Footer()

    def _pages(self) -> ComposeResult:
        with VerticalScroll(id="page-look", classes="page"):
            yield Cycle(tuple((name.title(), name) for name in self._presets), "rainbow", id="preset", label="Look")
            yield Switch(value=True, id="gradient")
            yield Label("Gradient on", id="gradient-label", classes="tag")
            yield Cycle(self._palette_options(), "rainbow", id="palette", label="Palette")
            yield Cycle(
                (("Across", "horizontal"), ("Down", "vertical"), ("Diagonal", "diagonal")),
                "horizontal",
                id="direction",
                label="Direction",
            )
            yield Label("Favourites", classes="tag")
            yield OptionList(id="favourites")
            yield Input(placeholder="Name this look", id="preset-name", compact=True)
            yield Button("Save look", id="save-preset")
        with VerticalScroll(id="page-outline", classes="page"):
            yield Switch(value=False, id="outline")
            yield Label("Outline off", id="outline-label", classes="tag")
            yield Cycle(OUTLINE_MODES, "shade", id="outline-mode", label="Mode")
            yield Cycle(self._symbols, "░", id="symbol", label="Symbol")
            yield Input(placeholder="Add a symbol", id="custom-symbol", compact=True, max_length=2)
            yield Button("Add symbol", id="add-symbol")
            yield Cycle(tuple((name, name) for name in COLOURS), "slate", id="outline-colour", label="Colour")
            yield Cycle(self._palette_options(off=True), "off", id="outline-gradient", label="Gradient")
            yield Cycle(
                (("Across", "horizontal"), ("Down", "vertical"), ("Diagonal", "diagonal")),
                "horizontal",
                id="outline-direction",
                label="Direction",
            )
            yield Cycle(ANIM_SPEEDS, "1", id="outline-speed", label="Cycle speed")
            yield Cycle(OUTLINE_DISTANCES, "0", id="outline-distance", label="Distance")
            yield Cycle(OUTLINE_PLACES, "both", id="outline-place", label="Place")
            yield Cycle(OUTLINE_SCOPES, "word", id="outline-scope", label="Around")
            yield Switch(value=True, id="side-t")
            yield Label("Top", classes="tag")
            yield Switch(value=True, id="side-b")
            yield Label("Bottom", classes="tag")
            yield Switch(value=True, id="side-l")
            yield Label("Left", classes="tag")
            yield Switch(value=True, id="side-r")
            yield Label("Right", classes="tag")
            yield Label("Shift", classes="tag")
            yield Input(value="0", id="odx", compact=True, type="integer", classes="nudge")
            yield Input(value="0", id="ody", compact=True, type="integer", classes="nudge")
        with VerticalScroll(id="page-shadow", classes="page"):
            yield Switch(value=False, id="shadow")
            yield Label("Shadow off", id="shadow-label", classes="tag")
            yield Label("Shift", classes="tag")
            yield Input(value="1", id="dx", compact=True, type="integer", classes="nudge")
            yield Input(value="1", id="dy", compact=True, type="integer", classes="nudge")
            yield Cycle(tuple((name, name) for name in COLOURS), "ink", id="shadow-colour", label="Colour")
            yield Cycle((("same", "same"),) + self._symbols, "same", id="shadow-symbol", label="Symbol")
        with VerticalScroll(id="page-colour", classes="page"):
            yield Cycle((("Letters", "letters"), ("Outline", "outline")), "letters", id="grad-which", label="Editing")
            yield Cycle((("Smooth", "smooth"), ("Bands", "bands")), "smooth", id="blend", label="Blend")
            yield Cycle((("Stop 1", "0"),), "0", id="stop", label="Stop")
            yield Label("H", classes="tag")
            yield Input(value="0", id="stop-h", compact=True, type="integer", classes="nudge")
            yield Label("S", classes="tag")
            yield Input(value="100", id="stop-s", compact=True, type="integer", classes="nudge")
            yield Label("V", classes="tag")
            yield Input(value="100", id="stop-v", compact=True, type="integer", classes="nudge")
            yield Button("Add stop", id="add-stop")
            yield Button("Remove stop", id="remove-stop")
            yield Input(placeholder="Save palette as", id="palette-name", compact=True)
            yield Button("Save palette", id="save-palette")
            with Vertical(id="relations"):
                yield Label("Hue", classes="tag")
                yield Button("-", id="hue-minus")
                yield Input(value="0", id="hue", compact=True, type="integer", classes="nudge")
                yield Button("+", id="hue-plus")
                yield Label("Role", classes="tag")
                yield Select((("—", -1),), value=-1, allow_blank=False, id="role", compact=True)
                yield Label("Link", classes="tag")
                yield Switch(value=True, id="link")
                yield Label("Focus", classes="tag")
                yield Switch(value=False, id="focus-role")
                yield Label("H", classes="tag")
                yield Input(value="0", id="role-h", compact=True, type="integer", classes="nudge")
                yield Label("S", classes="tag")
                yield Input(value="100", id="role-s", compact=True, type="integer", classes="nudge")
                yield Label("V", classes="tag")
                yield Input(value="100", id="role-v", compact=True, type="integer", classes="nudge")
                yield Button("Split sections", id="split")
        with VerticalScroll(id="page-animate", classes="page"):
            yield Cycle(ANIMATIONS, "none", id="animation", label="Motion")
            yield Cycle(ANIM_SPEEDS, "1", id="anim-speed", label="Speed")
            yield Cycle(ANIM_DIRECTIONS, "forward", id="anim-direction", label="Direction")
            yield Cycle(ANIM_TRAVELS, "360", id="anim-travel", label="Travel")
            yield Cycle(ANIM_LAYERS, "all", id="anim-layers", label="Moves")
            yield Cycle(TRACE_PATTERNS, "outline", id="trace-pattern", label="Trace")
            yield Cycle(TRACE_REVEALS, "draw", id="trace-reveal", label="Trace does")
        with Vertical(id="page-notes", classes="page"):
            yield TextArea(id="notes")
            yield Static(
                "Notes are saved with the project and with a favourite. "
                "Palettes, symbols, and looks you save are loaded from ~/.config/meowtext. "
                "Ctrl+E paints the banner. Tab switches between the banner and one letter.",
                id="notes-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#paint-bar", Static).display = False
        self.query_one("#variant", Cycle).display = False
        for name in _SECTIONS:
            if name != "look":
                self.query_one(f"#page-{name}").display = False
        self._reload_favourites()
        self._ui_ready = True
        self._fill_fonts()
        if self._opened is not None:
            self._apply_project(self._opened)
        self.query_one("#text", Input).focus()

    def on_cycle_changed(self, event: Cycle.Changed) -> None:
        if not self._ui_ready or self._updating:
            return
        choice = event.cycle.id
        if choice == "section":
            self._section = event.value
            self._show_section()
            return
        if choice == "engine":
            self.font_id = None
            self._letters.clear()
            self._patches.clear()
            self._fill_fonts()
            return
        if choice == "format":
            self._sync_suffix()
            return
        if choice == "variant":
            family = self._current_family()
            if family is not None and event.value:
                self._picked[family.key] = event.value
                self.font_id = event.value
                self._render_preview()
            return
        if choice == "animation":
            self._read_animation()
            self._set_animation(event.value)
            return
        if choice in {"anim-speed", "anim-direction", "anim-travel", "anim-layers", "trace-pattern", "trace-reveal"}:
            self._read_animation()
            self._render_preview()
            return
        if choice == "palette":
            self._stops = None if event.value != "edited" else self._stops
            self._after_style_edit()
            self._sync_stops()
            return
        if choice == "outline-gradient":
            self._outline_stops = None if event.value != "edited" else self._outline_stops
            self._after_style_edit()
            self._sync_stops()
            return
        if choice == "grad-which":
            self._sync_stops()
            return
        if choice == "blend":
            if self._choice("grad-which", "letters") == "outline":
                self._outline_bands = event.value == "bands"
            else:
                self._bands = event.value == "bands"
            self._after_style_edit()
            return
        if choice == "stop":
            self._sync_stops()
            return
        if choice == "preset":
            self._apply_preset(event.value)
            return
        self._after_style_edit()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if not self._ui_ready or self._updating:
            return
        if event.switch.id == "link":
            self._toggle_link(event.value)
            return
        if event.switch.id == "focus-role":
            self._render_preview()
            return
        if event.switch.id == "gradient":
            self.query_one("#gradient-label", Label).update("Gradient on" if event.value else "Gradient off")
        if event.switch.id == "outline":
            self.query_one("#outline-label", Label).update("Outline on" if event.value else "Outline off")
        if event.switch.id == "shadow":
            self.query_one("#shadow-label", Label).update("Shadow on" if event.value else "Shadow off")
        self._after_style_edit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._ui_ready:
            return
        field = event.input.id
        if field == "filter":
            self._fill_fonts()
            return
        if field == "hue":
            if not self._updating:
                self._set_hue_from_input()
            return
        if field in {"role-h", "role-s", "role-v"}:
            if not self._updating:
                self._set_role_from_inputs()
            return
        if field in {"stop-h", "stop-s", "stop-v"}:
            if not self._updating and self._section == "colour":
                self._set_stop_from_inputs()
            return
        if field in {"path", "preset-name", "palette-name", "custom-symbol"} or self._updating:
            return
        if field == "text":
            self._patches.clear()
        else:
            self._sync_preset_selection()
        self._render_preview()

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
        elif button == "hue-minus":
            self._nudge_hue(-15)
        elif button == "hue-plus":
            self._nudge_hue(15)
        elif button == "split":
            self._split_role()
        elif button == "add-stop":
            self._add_stop()
        elif button == "remove-stop":
            self._remove_stop()
        elif button == "save-palette":
            self._save_palette()
        elif button == "save-preset":
            self._save_preset()
        elif button == "add-symbol":
            self._add_symbol()

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self._ui_ready or self._updating or event.select.id != "role":
            return
        try:
            slot = int(event.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if slot < 0:
            return
        if self._role_echoes:
            self._role_echoes -= 1
            self._show_role_editor()
            return
        self._arm_focus()
        self._render_preview()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if not self._ui_ready or self._updating or event.option_list.id != "font-list":
            return
        option_id = event.option_id
        if not option_id or str(option_id).startswith("header"):
            return
        family = self._family_by_key.get(str(option_id))
        if family is None:
            return
        chosen = self._picked.get(family.key, family.members[0].id)
        if chosen == self.font_id and family.key == self._family_key():
            return
        self.font_id = chosen
        self._show_variant(family)
        self._letters.clear()
        self._patches.clear()
        self._render_preview()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "favourites" or not event.option_id:
            return
        try:
            project = load_favourite(Path(str(event.option_id)))
        except RenderError as exc:
            self.notify(str(exc), severity="error")
            return
        self._apply_project(project)
        self.notify(f"Loaded {Path(str(event.option_id)).stem}")

    def on_key(self, event) -> None:
        focused = self.focused
        if isinstance(focused, Switch) and event.key in {"left", "right"}:
            focused.value = event.key == "right"
            event.stop()
            return
        if isinstance(focused, Input) and "nudge" in focused.classes and event.key in {"left", "right"}:
            self._nudge_input(focused, -1 if event.key == "left" else 1)
            event.stop()
            return
        if isinstance(focused, Select) and event.key in {"left", "right"}:
            self._cycle_select(focused, 1 if event.key == "right" else -1)
            event.stop()
            return
        if not self._paint or isinstance(focused, (Input, TextArea)):
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

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_text(self) -> None:
        self.query_one("#text", Input).focus()

    def action_section_next(self) -> None:
        self._step_section(1)

    def action_section_prev(self) -> None:
        self._step_section(-1)

    def action_project(self) -> None:
        """Save the editable project. An existing file keeps its bytes."""

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
        self._reload_favourites()
        self.notify(f"Favourite {path.name}")

    def action_paint(self) -> None:
        self._paint = not self._paint
        self.query_one("#paint-bar", Static).display = self._paint
        if self._paint:
            self._letter = self._first_letter()
            self.query_one("#preview", Static).focus()
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
            self.query_one("#engine", Cycle).set_value(project.engine if project.engine in {"figlet", "toilet", "tdf"} else "figlet")
            self.query_one("#notes", TextArea).text = project.notes
            self.notes = project.notes
            self._set_style_widgets(project.style)
            self._stops = project.style.stops
            self._outline_stops = project.style.outline_stops
            self._bands = project.style.bands
            self._outline_bands = project.style.outline_bands
            self._write_animation(project.animation)
            self._patches = {(x, y): cell.clone() for x, y, cell in project.patches}
            self._letters = {char: grid.copy() for char, grid in project.letters.items()}
            self._relations = RelationPalette(hue=project.hue)
            self._relations.roles = {slot: role.clone() for slot, role in project.roles.items()}
            self._pending_roles = self._relations.roles
        finally:
            self._updating = False
        self.font_id = None
        self._source_key = None
        self._fill_fonts()
        self._select_project_font(project)
        self._sync_stops()
        self._render_preview()

    def _select_project_font(self, project: Project) -> None:
        match = None
        for font in self._by_id.values():
            if font.name == project.font_name and font.index == project.font_index:
                if not project.font_source or font.source == project.font_source or Path(font.source).name == Path(project.font_source).name:
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
        if family is None:
            return
        self._picked[family.key] = match.id
        options = self.query_one("#font-list", OptionList)
        ids = [str(option.id) for option in options.options]
        if family.key in ids:
            options.highlighted = ids.index(family.key)
        self._show_variant(family)

    def _palette_options(self, off: bool = False) -> tuple[tuple[str, str], ...]:
        options = [("flat", "off")] if off else []
        options.extend((name, name) for name in self._palettes)
        options.append(("edited", "edited"))
        return tuple(options)

    def _show_section(self) -> None:
        for name in _SECTIONS:
            self.query_one(f"#page-{name}").display = name == self._section
        if self._section == "colour":
            self._sync_stops()

    def _step_section(self, delta: int) -> None:
        index = _SECTIONS.index(self._section)
        self._section = _SECTIONS[(index + delta) % len(_SECTIONS)]
        self._updating = True
        try:
            self.query_one("#section", Cycle).set_value(self._section)
        finally:
            self._updating = False
        self._show_section()

    def _engine_name(self) -> str:
        return self._choice("engine", "figlet")

    def _choice(self, widget_id: str, default: str = "") -> str:
        value = self.query_one(f"#{widget_id}", Cycle).value
        return default if value is None or value == "" else str(value)

    def _fill_fonts(self) -> None:
        engine = self._engine_name()
        if engine == "tdf" and not tdf_ready():
            self.query_one("#meta", Static).update("Indexing TheDraw fonts…")
            self.run_worker(self._index_tdf, thread=True, exclusive=True, group="tdf-index")
            return
        fonts = list_fonts(engine)
        self._by_id = {font.id: font for font in fonts}
        families = group_fonts(fonts)
        self._families = families
        self._family_by_key = {family.key: family for family in families}
        query = self.query_one("#filter", Input).value.strip().lower()
        matched = families
        if query:
            matched = [
                family
                for family in families
                if query in family.stem.lower()
                or any(query in member.name.lower() or query in Path(member.source).name.lower() for member in family.members)
            ]
        options = self.query_one("#font-list", OptionList)
        options.clear_options()
        rows: list[Option] = []
        if engine == "tdf":
            for kind, title in _KINDS:
                group = [family for family in matched if family.kind == kind]
                if kind == "color" and len(group) > 400:
                    group = group[:400]
                if not group:
                    continue
                rows.append(Option(title, id=f"header-{kind}", disabled=True))
                rows.extend(Option(family.label(), id=family.key) for family in group)
        else:
            visible = matched[:1200]
            rows.extend(Option(family.label(), id=family.key) for family in visible)
        placeholder = self.query_one("#filter", Input)
        shown = sum(1 for row in rows if row.id and not str(row.id).startswith("header"))
        placeholder.placeholder = f"Filter {len(families)} fonts" if shown >= len(matched) else f"{shown} shown — keep typing"
        if not rows:
            self.font_id = None
            self._render_preview()
            return
        options.add_options(rows)
        ids = [str(row.id) for row in rows if row.id and not str(row.id).startswith("header")]
        current = self._family_for_font(self.font_id or "")
        if current is None or current.key not in ids:
            current = self._family_by_key.get(self._default_family_key(matched))
        if current is None:
            return
        self.font_id = self._picked.get(current.key, current.members[0].id)
        self._updating = True
        try:
            options.highlighted = ids.index(current.key)
        finally:
            self._updating = False
        self._show_variant(current)
        self._render_preview()

    def _default_family_key(self, families: list[FontFamily]) -> str:
        wanted = {"figlet": "ansi shadow", "toilet": "future"}.get(self._engine_name())
        if wanted:
            for family in families:
                if family.stem.lower() == wanted or any(member.name.lower() == wanted for member in family.members):
                    return family.key
        for family in families:
            if not family.key.startswith("header"):
                return family.key
        return families[0].key

    def _index_tdf(self) -> None:
        load_tdf()
        self.call_from_thread(self._tdf_indexed)

    def _tdf_indexed(self) -> None:
        if self._engine_name() == "tdf":
            self._fill_fonts()

    def _family_for_font(self, font_id: str) -> FontFamily | None:
        if not font_id:
            return None
        for family in self._families:
            if any(member.id == font_id for member in family.members):
                return family
        return None

    def _family_key(self) -> str:
        family = self._family_for_font(self.font_id or "")
        return family.key if family else ""

    def _current_family(self) -> FontFamily | None:
        return self._family_for_font(self.font_id or "")

    def _show_variant(self, family: FontFamily) -> None:
        cycle = self.query_one("#variant", Cycle)
        if len(family.members) < 2:
            cycle.display = False
            return
        options = [(member.name, member.id) for member in family.members]
        chosen = self._picked.get(family.key, family.members[0].id)
        if chosen not in {member.id for member in family.members}:
            chosen = family.members[0].id
        self._updating = True
        try:
            cycle.set_options(options, chosen)
            cycle.display = True
        finally:
            self._updating = False

    def _apply_preset(self, name: str) -> None:
        style = self._presets.get(name)
        if style is None:
            return
        self._stops = style.stops
        self._outline_stops = style.outline_stops
        self._bands = style.bands
        self._outline_bands = style.outline_bands
        self._set_style_widgets(style)
        self._sync_stops()
        self._render_preview()

    def _set_style_widgets(self, style: BannerStyle) -> None:
        self._updating = True
        try:
            self.query_one("#gradient", Switch).value = style.gradient is not None
            self.query_one("#gradient-label", Label).update("Gradient on" if style.gradient else "Gradient off")
            palette = "edited" if style.stops else (style.gradient if style.gradient in self._palettes else "rainbow")
            self.query_one("#palette", Cycle).set_value(palette if style.gradient or style.stops else "rainbow")
            self.query_one("#direction", Cycle).set_value(style.direction)
            self.query_one("#outline", Switch).value = style.outline
            self.query_one("#outline-label", Label).update("Outline on" if style.outline else "Outline off")
            self.query_one("#outline-mode", Cycle).set_value(style.outline_mode)
            self._ensure_symbol(style.outline_char)
            self.query_one("#symbol", Cycle).set_value(style.outline_char)
            self.query_one("#outline-colour", Cycle).set_value(colour_name(style.outline_color))
            outline_gradient = "edited" if style.outline_stops else (style.outline_gradient or "off")
            self.query_one("#outline-gradient", Cycle).set_value(outline_gradient)
            self.query_one("#outline-direction", Cycle).set_value(style.outline_direction)
            self.query_one("#outline-speed", Cycle).set_value(self._nearest_speed(style.outline_speed))
            self.query_one("#outline-distance", Cycle).set_value(str(style.outline_distance))
            self.query_one("#outline-place", Cycle).set_value(style.outline_place)
            self.query_one("#outline-scope", Cycle).set_value(style.outline_scope)
            for side, widget_id in (("t", "side-t"), ("b", "side-b"), ("l", "side-l"), ("r", "side-r")):
                self.query_one(f"#{widget_id}", Switch).value = side in (style.outline_sides or "tblr")
            self.query_one("#odx", Input).value = str(style.outline_dx)
            self.query_one("#ody", Input).value = str(style.outline_dy)
            self.query_one("#shadow", Switch).value = style.shadow
            self.query_one("#shadow-label", Label).update("Shadow on" if style.shadow else "Shadow off")
            self.query_one("#dx", Input).value = str(style.shadow_dx)
            self.query_one("#dy", Input).value = str(style.shadow_dy)
            self.query_one("#shadow-colour", Cycle).set_value(colour_name(style.shadow_color))
            self.query_one("#shadow-symbol", Cycle).set_value(style.shadow_char or "same")
        finally:
            self._updating = False

    def _after_style_edit(self) -> None:
        self._sync_preset_selection()
        self._render_preview()

    def _sync_preset_selection(self) -> None:
        style = self._style()
        match = next((name for name, preset in self._presets.items() if preset == style), "custom")
        preset = self.query_one("#preset", Cycle)
        if match not in {value for _, value in preset.options}:
            options = list(preset.options)
            if not any(value == "custom" for _, value in options):
                options.append(("Custom", "custom"))
            self._updating = True
            try:
                preset.set_options(options, match)
            finally:
                self._updating = False
            return
        if preset.value == match:
            return
        self._updating = True
        try:
            preset.set_value(match)
        finally:
            self._updating = False

    def _sync_suffix(self) -> None:
        fmt = self._choice("format", "ansi")
        suffix = _SUFFIX.get(fmt)
        if suffix is None:
            return
        current = Path(self.query_one("#path", Input).value or "banner.ans")
        if current.suffix == ".meowtext":
            return
        self._updating = True
        try:
            self.query_one("#path", Input).value = str(current.with_suffix(suffix))
        finally:
            self._updating = False

    def _style(self) -> BannerStyle:
        gradient_on = self.query_one("#gradient", Switch).value
        palette = self._choice("palette", "rainbow")
        outline_gradient = self._choice("outline-gradient", "off")
        shadow_symbol = self._choice("shadow-symbol", "same")
        sides = "".join(
            side
            for side, widget_id in (("t", "side-t"), ("b", "side-b"), ("l", "side-l"), ("r", "side-r"))
            if self.query_one(f"#{widget_id}", Switch).value
        )
        return BannerStyle(
            gradient=None if not gradient_on else ("rainbow" if palette == "edited" else palette),
            direction=self._choice("direction", "horizontal"),
            stops=self._stops,
            bands=self._bands,
            outline=self.query_one("#outline", Switch).value,
            outline_char=self._choice("symbol", "░"),
            outline_color=COLOURS.get(self._choice("outline-colour", "slate"), DEFAULT_OUTLINE),
            outline_mode=self._choice("outline-mode", "shade"),
            outline_gradient=None if outline_gradient in {"off", "edited"} else outline_gradient,
            outline_stops=self._outline_stops,
            outline_direction=self._choice("outline-direction", "horizontal"),
            outline_speed=float(self._choice("outline-speed", "1") or 1),
            outline_bands=self._outline_bands,
            outline_sides=sides,
            outline_distance=int(self._choice("outline-distance", "0") or 0),
            outline_place=self._choice("outline-place", "both"),
            outline_scope=self._choice("outline-scope", "word"),
            outline_dx=self._number("odx", 0),
            outline_dy=self._number("ody", 0),
            shadow=self.query_one("#shadow", Switch).value,
            shadow_dx=self._number("dx", 1),
            shadow_dy=self._number("dy", 1),
            shadow_color=COLOURS.get(self._choice("shadow-colour", "ink"), DEFAULT_SHADOW),
            shadow_char=None if shadow_symbol == "same" else shadow_symbol,
        )

    def _read_animation(self) -> None:
        self._animation = Animation(
            name=self._choice("animation", "none"),
            speed=float(self._choice("anim-speed", "1") or 1),
            direction=self._choice("anim-direction", "forward"),
            travel=int(self._choice("anim-travel", "360") or 360),
            layers=self._choice("anim-layers", "all"),
            pattern=self._choice("trace-pattern", "outline"),
            reveal=self._choice("trace-reveal", "draw"),
        )

    def _write_animation(self, motion: Animation) -> None:
        self._animation = motion.clone()
        self._updating = True
        try:
            self.query_one("#animation", Cycle).set_value(motion.name if motion.name in {value for _, value in ANIMATIONS} else "none")
            self.query_one("#anim-speed", Cycle).set_value(self._nearest_speed(motion.speed))
            self.query_one("#anim-direction", Cycle).set_value(motion.direction)
            travel = str(motion.travel if str(motion.travel) in {value for _, value in ANIM_TRAVELS} else 360)
            self.query_one("#anim-travel", Cycle).set_value(travel)
            self.query_one("#anim-layers", Cycle).set_value(motion.layers)
            self.query_one("#trace-pattern", Cycle).set_value(motion.pattern)
            self.query_one("#trace-reveal", Cycle).set_value(motion.reveal)
        finally:
            self._updating = False
        self._set_animation(self._animation.name)

    def _nearest_speed(self, speed: float) -> str:
        choices = [float(value) for _, value in ANIM_SPEEDS]
        nearest = min(choices, key=lambda item: abs(item - speed))
        return str(int(nearest)) if nearest == int(nearest) else str(nearest)

    def _set_animation(self, name: str) -> None:
        self._animation.name = name if name in {item for _, item in ANIMATIONS} else "none"
        self._frame = 0
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None
        if self._animation.name != "none":
            self._anim_timer = self.set_interval(0.12, self._tick_animation)
        self._render_preview()

    def _tick_animation(self) -> None:
        self._frame += 1
        self._render_preview()

    def _number(self, widget_id: str, default: int) -> int:
        raw = self.query_one(f"#{widget_id}", Input).value.strip()
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(-8, min(8, value))

    def _render_preview(self) -> None:
        style = self._style()
        self._enable_controls(style)
        font = self._by_id.get(self.font_id or "")
        preview = self.query_one("#preview", Static)
        meta = self.query_one("#meta", Static)
        if font is None:
            self.last_banner = None
            self._source = None
            self._sync_roles(Grid())
            message = "No font selected."
            if self._engine_name() == "tdf" and not tdf_ready():
                message = "Indexing TheDraw fonts…"
            elif self._engine_name() == "tdf" and tdf_ready() and not self._families:
                message = "No TheDraw fonts in ~/.config/tdfgo/fonts"
            preview.update(message)
            meta.update(message)
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
            preview.update(Text(str(exc), style="italic #a8a8a8"))
            meta.update(Text(str(exc), style="red"))
            return
        self.last_banner = banner
        self._sync_roles(self._source or Grid())
        self._show_frame()
        meta.update(self._describe(banner))
        self._refresh_paint_bar()

    def _show_frame(self) -> None:
        preview = self.query_one("#preview", Static)
        banner = self.last_banner
        text = self.query_one("#text", Input).value
        if banner is None:
            return
        if not text:
            preview.update(Text("Type a banner.", style="italic #888"))
            return
        if not banner.grid.rows:
            preview.update(Text("Nothing to draw.", style="italic #888"))
            return
        focus = self._selected_slot() if self.query_one("#focus-role", Switch).value else None
        cursor = self._cursor if self._paint and self._paint_target == "banner" else None
        preview.update(to_rich(banner.grid, focus, cursor))

    def _enable_controls(self, style: BannerStyle) -> None:
        self.query_one("#palette", Cycle).disabled = style.gradient is None and self._stops is None
        self.query_one("#direction", Cycle).disabled = style.gradient is None and self._stops is None
        outlined = style.outline
        adaptive = style.outline_mode in {"contour", "heavy", "double", "blocks"}
        for widget_id in (
            "outline-mode",
            "outline-colour",
            "outline-gradient",
            "outline-direction",
            "outline-speed",
            "outline-distance",
            "outline-place",
            "outline-scope",
        ):
            self.query_one(f"#{widget_id}", Cycle).disabled = not outlined
        self.query_one("#symbol", Cycle).disabled = (not outlined) or adaptive

    def _active_stops(self) -> tuple[Color, ...]:
        which = self._choice("grad-which", "letters")
        if which == "outline":
            if self._outline_stops:
                return self._outline_stops
            name = self._choice("outline-gradient", "off")
            if name in self._palettes:
                return self._palettes[name]
            return self._palettes.get("rainbow", (Color(255, 0, 64), Color(0, 190, 255)))
        if self._stops:
            return self._stops
        name = self._choice("palette", "rainbow")
        if name in self._palettes:
            return self._palettes[name]
        return self._palettes.get("rainbow", (Color(255, 0, 64), Color(0, 190, 255)))

    def _store_stops(self, stops: tuple[Color, ...]) -> None:
        if self._choice("grad-which", "letters") == "outline":
            self._outline_stops = stops
            self.query_one("#outline", Switch).value = True
            self._updating = True
            try:
                self.query_one("#outline-gradient", Cycle).set_value("edited")
            finally:
                self._updating = False
        else:
            self._stops = stops
            self.query_one("#gradient", Switch).value = True
            self._updating = True
            try:
                self.query_one("#palette", Cycle).set_value("edited")
            finally:
                self._updating = False

    def _sync_stops(self) -> None:
        stops = self._active_stops()
        cycle = self.query_one("#stop", Cycle)
        options = [(f"Stop {index + 1}", str(index)) for index in range(len(stops))]
        current = cycle.value if cycle.value in {value for _, value in options} else "0"
        which = self._choice("grad-which", "letters")
        bands = self._outline_bands if which == "outline" else self._bands
        self._updating = True
        try:
            cycle.set_options(options, current)
            self.query_one("#blend", Cycle).set_value("bands" if bands else "smooth")
            index = int(current)
            hue, sat, val = rgb_to_hsv(stops[index])
            self._set_quiet("#stop-h", str(int(round(hue)) % 360))
            self._set_quiet("#stop-s", str(int(round(sat * 100))))
            self._set_quiet("#stop-v", str(int(round(val * 100))))
        finally:
            self._updating = False

    def _set_stop_from_inputs(self) -> None:
        stops = list(self._active_stops())
        try:
            index = int(self._choice("stop", "0"))
            hue = float(self.query_one("#stop-h", Input).value)
            sat = float(self.query_one("#stop-s", Input).value) / 100
            val = float(self.query_one("#stop-v", Input).value) / 100
        except ValueError:
            return
        if index < 0 or index >= len(stops):
            return
        current_h, current_s, current_v = rgb_to_hsv(stops[index])
        if (
            abs((hue % 360) - current_h) < 0.51
            and abs(sat - current_s) < 0.005
            and abs(val - current_v) < 0.005
        ):
            return
        colour = hsv_to_rgb(hue, sat, val)
        stops[index] = colour
        self._store_stops(tuple(stops))
        self._after_style_edit()

    def _add_stop(self) -> None:
        stops = list(self._active_stops())
        stops.append(stops[-1] if stops else Color(255, 255, 255))
        self._store_stops(tuple(stops))
        self._sync_stops()
        self._after_style_edit()

    def _remove_stop(self) -> None:
        stops = list(self._active_stops())
        if len(stops) <= 2:
            self.notify("A gradient keeps at least two stops")
            return
        try:
            index = int(self._choice("stop", "0"))
        except ValueError:
            index = len(stops) - 1
        del stops[max(0, min(index, len(stops) - 1))]
        self._store_stops(tuple(stops))
        self._sync_stops()
        self._after_style_edit()

    def _save_palette(self) -> None:
        name = self.query_one("#palette-name", Input).value.strip().lower()
        if not name:
            self.notify("Name the palette first", severity="warning")
            return
        stops = self._active_stops()
        save_palette(name, stops)
        self._palettes = dict(load_palettes())
        self._refresh_palette_cycles()
        if self._choice("grad-which", "letters") == "outline":
            self._outline_stops = None
            self.query_one("#outline-gradient", Cycle).set_value(name)
        else:
            self._stops = None
            self.query_one("#palette", Cycle).set_value(name)
        self.notify(f"Palette {name} saved")
        self._after_style_edit()

    def _refresh_palette_cycles(self) -> None:
        self.query_one("#palette", Cycle).set_options(self._palette_options(), self._choice("palette", "rainbow"))
        self.query_one("#outline-gradient", Cycle).set_options(
            self._palette_options(off=True), self._choice("outline-gradient", "off")
        )

    def _save_preset(self) -> None:
        name = self.query_one("#preset-name", Input).value.strip().lower()
        if not name:
            self.notify("Name the look first", severity="warning")
            return
        save_preset(name, self._style())
        self._presets = load_presets()
        options = tuple((item.title(), item) for item in self._presets)
        self.query_one("#preset", Cycle).set_options(options, name)
        self.notify(f"Look {name} saved")

    def _add_symbol(self) -> None:
        char = self.query_one("#custom-symbol", Input).value.strip()[:1]
        if not char:
            self.notify("Type the symbol first", severity="warning")
            return
        save_symbol(char)
        self._symbols = load_symbols()
        self.query_one("#symbol", Cycle).set_options(self._symbols, char)
        shadow = list(self.query_one("#shadow-symbol", Cycle).options)
        if char not in {value for _, value in shadow}:
            shadow.append((f"yours {char}", char))
        self.query_one("#shadow-symbol", Cycle).set_options(shadow, self._choice("shadow-symbol", "same"))
        self.notify(f"Added {char}")
        self._after_style_edit()

    def _ensure_symbol(self, char: str) -> None:
        cycle = self.query_one("#symbol", Cycle)
        if char in {value for _, value in cycle.options}:
            return
        options = list(cycle.options)
        options.append((char, char))
        cycle.set_options(options, char)

    def _reload_favourites(self) -> None:
        options = self.query_one("#favourites", OptionList)
        options.clear_options()
        paths = list_favourites()
        if paths:
            options.add_options(Option(path.stem, id=str(path)) for path in paths)

    def _nudge_hue(self, delta: float) -> None:
        self._relations.hue = (self._relations.hue + delta) % 360
        self._set_quiet("#hue", str(int(round(self._relations.hue)) % 360))
        self._render_preview()

    def _set_hue_from_input(self) -> None:
        try:
            hue = float(self.query_one("#hue", Input).value) % 360
        except ValueError:
            return
        if abs(hue - (self._relations.hue % 360)) < 0.5:
            return
        self._relations.hue = hue
        self._render_preview()

    def _toggle_link(self, linked: bool) -> None:
        slot = self._selected_slot()
        if slot is None or slot not in self._relations.roles:
            return
        role = self._relations.roles[slot]
        if role.linked == linked:
            return
        if linked:
            self._relations.link_role(slot)
        else:
            self._relations.break_role(slot)
        self._role_sig = None
        self._render_preview()

    def _set_role_from_inputs(self) -> None:
        slot = self._selected_slot()
        if slot is None or slot not in self._relations.roles:
            return
        role = self._relations.roles[slot]
        if role.linked:
            return
        try:
            hue = float(self.query_one("#role-h", Input).value)
            sat = float(self.query_one("#role-s", Input).value) / 100
            val = float(self.query_one("#role-v", Input).value) / 100
        except ValueError:
            return
        if (
            abs((hue % 360) - role.hue) < 0.51
            and abs(sat - role.sat) < 0.005
            and abs(val - role.val) < 0.005
        ):
            return
        self._relations.set_hsv(slot, hue, sat, val)
        self._role_sig = None
        self._render_preview()

    def _split_role(self) -> None:
        slot = self._selected_slot()
        if slot is None or self._source is None or slot not in self._relations.roles:
            return
        made = self._relations.split(self._source, slot)
        name = self._relations.roles[slot].name
        if made == 0:
            self.notify(f"{name} is already one section")
        else:
            self.notify(f"Split {name} into {made + 1} sections")
        self._role_sig = None
        self._render_preview()

    def _arm_focus(self) -> None:
        switch = self.query_one("#focus-role", Switch)
        if switch.value:
            return
        self._updating = True
        try:
            switch.value = True
        finally:
            self._updating = False

    def _selected_slot(self) -> int | None:
        value = self.query_one("#role", Select).value
        if value is Select.NULL or value is None:
            return None
        try:
            slot = int(value)
        except (TypeError, ValueError):
            return None
        return None if slot < 0 else slot

    def _sync_roles(self, source: Grid) -> None:
        row = self.query_one("#relations")
        slots = used_slots(source)
        if not slots:
            row.display = False
            return
        self._relations.ensure(source)
        row.display = True
        signature = tuple(
            (
                slot,
                self._relations.roles[slot].name,
                self._relations.roles[slot].linked,
                self._relations.color(slot).hex(),
                *role_place(source, slot),
            )
            for slot in slots
        )
        if signature != self._role_sig:
            options = []
            for slot, name, linked, hex_color, sections, where in signature:
                label = Text()
                label.append("█ ", style=hex_color)
                note = name if linked else f"{name} · own"
                extra = f" · {sections} sections" if sections > 1 else ""
                label.append(f"{note} · {where}{extra}")
                options.append((label, slot))
            select = self.query_one("#role", Select)
            current = select.value
            self._updating = True
            try:
                before = select.value
                select.set_options(options)
                if select.value != before:
                    self._role_echoes += 1
                if current in slots and select.value != current:
                    select.value = current
                    self._role_echoes += 1
            finally:
                self._updating = False
            self._role_sig = signature
        self._show_role_editor()
        role = self._relations.roles.get(self._selected_slot() or -1)
        locked = role is None or role.linked
        for widget_id in ("role-h", "role-s", "role-v"):
            self.query_one(f"#{widget_id}").disabled = locked

    def _show_role_editor(self) -> None:
        slot = self._selected_slot()
        if slot is None or slot not in self._relations.roles:
            return
        role = self._relations.roles[slot]
        if role.linked:
            hue, sat, val = rgb_to_hsv(role.paint(self._relations.hue))
        else:
            hue, sat, val = role.hue, role.sat, role.val
        link = self.query_one("#link", Switch)
        if link.value != role.linked:
            self._updating = True
            try:
                link.value = role.linked
            finally:
                self._updating = False
        self._set_quiet("#role-h", str(int(round(hue)) % 360))
        self._set_quiet("#role-s", str(int(round(sat * 100))))
        self._set_quiet("#role-v", str(int(round(val * 100))))
        shown = str(int(round(self._relations.hue)) % 360)
        if self.query_one("#hue", Input).value != shown and not self._hue_focused():
            self._set_quiet("#hue", shown)

    def _hue_focused(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input) and focused.id == "hue"

    def _set_quiet(self, selector: str, value: str) -> None:
        widget = self.query_one(selector, Input)
        if widget.value == value:
            return
        self._updating = True
        try:
            widget.value = value
        finally:
            self._updating = False

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
        source = self._source or Grid()
        if used_slots(source):
            parts.append(f"hue {int(round(self._relations.hue)) % 360}°")
            own = sum(1 for slot in used_slots(source) if slot in self._relations.roles and not self._relations.roles[slot].linked)
            if own:
                parts.append(f"{own} edited alone")
            if self.query_one("#focus-role", Switch).value:
                slot = self._selected_slot()
                if slot is not None and slot in self._relations.roles:
                    parts.append(f"showing {self._relations.roles[slot].name}")
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
        elif key == "down":
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
            existing = glyph.get(x, y)
            painted = existing.clone()
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
        existing = self.last_banner.grid.get(x, y)
        painted = existing.clone()
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
        if font is None:
            glyph = Grid([[Cell(char)]])
        else:
            glyph, _missing, _folded = layout_font(char, font)
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
        bar.update(f"Paint {where} · colour {self._paint_colour} · [ ] colour · , . letter · tab switches")

    def _nudge_input(self, widget: Input, delta: int) -> None:
        step = 15 if widget.id in {"hue", "role-h", "stop-h"} else 5 if widget.id in {"role-s", "role-v", "stop-s", "stop-v"} else 1
        try:
            value = int(widget.value or "0")
        except ValueError:
            value = 0
        widget.value = str(value + delta * step)

    def _cycle_select(self, select: Select, delta: int) -> None:
        values = [value for _prompt, value in select._options if value is not Select.NULL]  # type: ignore[attr-defined]
        if not values:
            return
        try:
            index = values.index(select.value)
        except ValueError:
            index = 0
        select.value = values[(index + delta) % len(values)]


def _plain(grid: Grid) -> str:
    return "\n".join("".join(cell.char or " " for cell in row) for row in grid.rows)
