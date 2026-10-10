"""Textual frontend. The banner engine does not depend on this module."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    Switch,
)
from textual.widgets.option_list import Option

from meowtext.catalog import FontInfo, list_fonts, load_tdf, tdf_ready
from meowtext.compose import Banner, layout_font, present
from meowtext.effects import (
    ANIMATIONS,
    COLOURS,
    DEFAULT_OUTLINE,
    DEFAULT_SHADOW,
    OUTLINE_MODES,
    PALETTES,
    PRESETS,
    SYMBOLS,
    BannerStyle,
    colour_name,
)
from meowtext.errors import RenderError
from meowtext.export import export
from meowtext.grid import Color, Grid
from meowtext.palette import RelationPalette, rgb_to_hsv, role_place, used_slots

_SUFFIX = {
    "ansi": ".ans",
    "plain": ".txt",
    "html": ".html",
    "json": ".json",
    "png": ".png",
    "kitty": ".kitty",
    "irc": ".irc",
}


def to_rich(grid: Grid, focus: int | None = None) -> Text:
    """Draw the banner. ``focus`` leaves one colour role bright and dims the rest."""

    text = Text()
    if not grid.rows:
        return text
    for y, row in enumerate(grid.rows):
        for cell in row:
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
            text.append(cell.char or " ", style=style or None)
        if y != len(grid.rows) - 1:
            text.append("\n")
    return text


def _dim(color: Color | None) -> Color | None:
    if color is None:
        return None
    return Color(color.r // 5, color.g // 5, color.b // 5)


class MeowText(App):
    """Type a line, pick a font, decorate it, and export the banner."""

    TITLE = "meowtext"
    SUB_TITLE = "FIGlet, TOIlet, TheDraw"
    CSS = """
    Screen { background: #101114; }
    #text { width: 1fr; }
    #engine, #preset, #format { width: 18; }
    #palette, #direction { width: 16; }
    #middle { height: 1fr; }
    #side { width: 38; height: 1fr; border-right: solid #2c3038; }
    #filter { margin: 0 0 0 0; }
    #font-list { height: 1fr; border: none; padding: 0; }
    #stage { width: 1fr; height: 1fr; }
    #meta { height: 1; padding: 0 1; color: #9aa1ab; background: #101114; }
    #stage-scroll { height: 1fr; background: #000; border: solid #2c3038; }
    #preview { width: auto; height: auto; padding: 1 2; background: #000; color: #e8e6e3; }
    .toolbar { height: auto; padding: 0 1; background: #181a20; }
    Label.tag { width: auto; height: 1; padding: 0 1 0 0; color: #c4c8d0; }
    #dx, #dy { width: 7; }
    #hue, #role-h, #role-s, #role-v { width: 8; }
    #role { width: 36; }
    #symbol, #shadow-symbol, #outline-mode, #animation { width: 18; }
    #outline-colour, #shadow-colour, #outline-gradient { width: 14; }
    #path { width: 1fr; }
    Button { margin: 0 1 0 0; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+y", "copy", "Copy"),
        Binding("ctrl+f", "focus_filter", "Find"),
        Binding("ctrl+t", "focus_text", "Text"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._fonts: list[FontInfo] = []
        self._by_id: dict[str, FontInfo] = {}
        self.font_id: str | None = None
        self._updating = False
        self._ui_ready = False
        self.last_banner: Banner | None = None
        self._relations = RelationPalette()
        self._source: Grid | None = None
        self._source_key: tuple[str, str] | None = None
        self._source_missing: tuple[str, ...] = ()
        self._source_folded = False
        self._role_sig: tuple | None = None
        self._role_echoes = 0
        self._anim = "none"
        self._frame = 0
        self._anim_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="toolbar"):
            yield Input(value="meow", placeholder="Banner text", id="text", compact=True, max_length=240)
            yield Select(
                (("FIGlet", "figlet"), ("TOIlet", "toilet"), ("TheDraw", "tdf")),
                value="figlet",
                allow_blank=False,
                id="engine",
                compact=True,
            )
        with Horizontal(id="middle"):
            with Vertical(id="side"):
                yield Input(placeholder="Filter fonts", id="filter", compact=True)
                yield OptionList(id="font-list")
            with Vertical(id="stage"):
                yield Static("", id="meta")
                with ScrollableContainer(id="stage-scroll"):
                    yield Static("", id="preview")
        with Horizontal(classes="toolbar"):
            yield Label("Look", classes="tag")
            yield Select(
                tuple((name.title(), name) for name in (*PRESETS, "custom")),
                value="rainbow",
                allow_blank=False,
                id="preset",
                compact=True,
            )
            yield Label("Gradient", classes="tag")
            yield Switch(value=True, id="gradient")
            yield Select(
                (("Across", "horizontal"), ("Down", "vertical"), ("Diagonal", "diagonal")),
                value="horizontal",
                allow_blank=False,
                id="direction",
                compact=True,
            )
            yield Select(
                tuple((name, name) for name in PALETTES),
                value="rainbow",
                allow_blank=False,
                id="palette",
                compact=True,
            )
        with Horizontal(classes="toolbar"):
            yield Label("Outline", classes="tag")
            yield Switch(value=False, id="outline")
            yield Select(OUTLINE_MODES, value="shade", allow_blank=False, id="outline-mode", compact=True)
            yield Select(SYMBOLS, value="░", allow_blank=False, id="symbol", compact=True)
            yield Select(
                tuple((name, name) for name in COLOURS),
                value="slate",
                allow_blank=False,
                id="outline-colour",
                compact=True,
            )
            yield Select(
                (("flat", "off"),) + tuple((name, name) for name in PALETTES),
                value="off",
                allow_blank=False,
                id="outline-gradient",
                compact=True,
            )
        with Horizontal(classes="toolbar"):
            yield Label("Shadow", classes="tag")
            yield Switch(value=False, id="shadow")
            yield Input(value="1", id="dx", compact=True, type="integer")
            yield Input(value="1", id="dy", compact=True, type="integer")
            yield Select(
                tuple((name, name) for name in COLOURS),
                value="ink",
                allow_blank=False,
                id="shadow-colour",
                compact=True,
            )
            yield Select((("same", "same"),) + SYMBOLS, value="same", allow_blank=False, id="shadow-symbol", compact=True)
        with Horizontal(classes="toolbar"):
            yield Label("Animate", classes="tag")
            yield Select(ANIMATIONS, value="none", allow_blank=False, id="animation", compact=True)
        with Horizontal(id="relations", classes="toolbar"):
            yield Label("Hue", classes="tag")
            yield Button("-", id="hue-minus")
            yield Input(value="0", id="hue", compact=True, type="integer")
            yield Button("+", id="hue-plus")
            yield Label("Role", classes="tag")
            yield Select((("—", -1),), value=-1, allow_blank=False, id="role", compact=True)
            yield Label("Link", classes="tag")
            yield Switch(value=True, id="link")
            yield Label("Focus", classes="tag")
            yield Switch(value=False, id="focus-role")
            yield Label("H", classes="tag")
            yield Input(value="0", id="role-h", compact=True, type="integer")
            yield Label("S", classes="tag")
            yield Input(value="100", id="role-s", compact=True, type="integer")
            yield Label("V", classes="tag")
            yield Input(value="100", id="role-v", compact=True, type="integer")
            yield Button("Split sections", id="split")
        with Horizontal(classes="toolbar"):
            yield Select(
                (
                    ("ANSI", "ansi"),
                    ("Plain", "plain"),
                    ("HTML", "html"),
                    ("JSON", "json"),
                    ("PNG", "png"),
                    ("Kitty", "kitty"),
                    ("IRC", "irc"),
                ),
                value="ansi",
                allow_blank=False,
                id="format",
                compact=True,
            )
            yield Input(value="banner.ans", id="path", compact=True)
            yield Button("Save", id="save")
            yield Button("Copy", id="copy")
        yield Footer()

    def on_mount(self) -> None:
        self._fill_fonts()
        self._ui_ready = True
        self.query_one("#text", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self._ui_ready or self._updating:
            return
        choice = event.select.id
        if choice == "role":
            if self._updating:
                return
            try:
                slot = int(event.value)
            except (TypeError, ValueError):
                slot = -1
            if slot < 0:
                return
            if self._role_echoes:
                self._role_echoes -= 1
                self._show_role_editor()
                return
            self._arm_focus()
            self._render_preview()
            return
        if choice == "preset":
            self._apply_preset(str(event.value))
        elif choice == "engine":
            self.font_id = None
            self._fill_fonts()
        elif choice == "format":
            self._sync_suffix()
        elif choice == "animation":
            self._set_animation(str(event.value))
        else:
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
        if field == "path" or self._updating:
            return
        if field != "text":
            self._sync_preset_selection()
        self._render_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "copy":
            self.action_copy()
        elif event.button.id == "hue-minus":
            self._nudge_hue(-15)
        elif event.button.id == "hue-plus":
            self._nudge_hue(15)
        elif event.button.id == "split":
            self._split_role()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if not self._ui_ready or not event.option_id or event.option_id == self.font_id:
            return
        self.font_id = event.option_id
        self._render_preview()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_text(self) -> None:
        self.query_one("#text", Input).focus()

    def action_save(self) -> None:
        self._render_preview()
        if self.last_banner is None or not self.last_banner.grid.rows:
            self.notify("Nothing to save", severity="warning")
            return
        fmt = self._choice("format", "ansi")
        path = Path(self.query_one("#path", Input).value).expanduser()
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
            self.notify("PNG is binary. Save it, or copy ANSI instead.", severity="warning")
            return
        try:
            data = export(self.last_banner.grid, fmt)
        except RenderError as exc:
            self.notify(str(exc), severity="error")
            return
        self.copy_to_clipboard(str(data))
        self.notify(f"Copied {fmt}")

    def _engine_name(self) -> str:
        return self._choice("engine", "figlet")

    def _choice(self, widget_id: str, default: str) -> str:
        value = self.query_one(f"#{widget_id}", Select).value
        if value is Select.NULL or value is None:
            return default
        return str(value)

    def _fill_fonts(self) -> None:
        engine = self._engine_name()
        if engine == "tdf" and not tdf_ready():
            self.query_one("#meta", Static).update("Indexing TheDraw fonts…")
            self.run_worker(self._index_tdf, thread=True, exclusive=True, group="tdf-index")
            return
        self._fonts = list_fonts(engine)
        self._by_id = {font.id: font for font in self._fonts}
        query = self.query_one("#filter", Input).value.strip().lower()
        matched = self._fonts
        if query:
            matched = [
                font
                for font in self._fonts
                if query in font.name.lower() or query in font.label().lower() or query in Path(font.source).name.lower()
            ]
        visible = matched[:400]
        options = self.query_one("#font-list", OptionList)
        options.clear_options()
        placeholder = self.query_one("#filter", Input)
        if len(matched) > len(visible):
            placeholder.placeholder = f"{len(visible)} of {len(matched)} — keep typing"
        else:
            placeholder.placeholder = f"Filter {len(self._fonts)} fonts"
        if not visible:
            self.font_id = None
            self._render_preview()
            return
        options.add_options(Option(font.label(), id=font.id) for font in visible)
        ids = [font.id for font in visible]
        if self.font_id not in ids:
            self.font_id = self._default_font_id(visible)
        options.highlighted = ids.index(self.font_id)
        self._render_preview()

    def _default_font_id(self, fonts: list[FontInfo]) -> str:
        wanted = {"figlet": "ansi shadow", "toilet": "future"}.get(self._engine_name())
        if wanted:
            for font in fonts:
                if font.name.lower() == wanted:
                    return font.id
        return fonts[0].id

    def _index_tdf(self) -> None:
        load_tdf()
        self.call_from_thread(self._tdf_indexed)

    def _tdf_indexed(self) -> None:
        if self._engine_name() == "tdf":
            self._fill_fonts()

    def _apply_preset(self, name: str) -> None:
        style = PRESETS.get(name)
        if style is None:
            return
        self._updating = True
        try:
            self.query_one("#gradient", Switch).value = style.gradient is not None
            if style.gradient and style.gradient in PALETTES:
                self.query_one("#palette", Select).value = style.gradient
            self.query_one("#direction", Select).value = style.direction
            self.query_one("#outline", Switch).value = style.outline
            self.query_one("#outline-mode", Select).value = style.outline_mode
            self.query_one("#symbol", Select).value = style.outline_char if style.outline_char in dict(SYMBOLS).values() else "░"
            self.query_one("#outline-colour", Select).value = colour_name(style.outline_color)
            self.query_one("#outline-gradient", Select).value = style.outline_gradient or "off"
            self.query_one("#shadow", Switch).value = style.shadow
            self.query_one("#dx", Input).value = str(style.shadow_dx)
            self.query_one("#dy", Input).value = str(style.shadow_dy)
            self.query_one("#shadow-colour", Select).value = colour_name(style.shadow_color)
            self.query_one("#shadow-symbol", Select).value = style.shadow_char or "same"
        finally:
            self._updating = False
        self._render_preview()

    def _after_style_edit(self) -> None:
        self._sync_preset_selection()
        self._render_preview()

    def _sync_preset_selection(self) -> None:
        style = self._style()
        match = next((name for name, preset in PRESETS.items() if preset == style), "custom")
        preset = self.query_one("#preset", Select)
        if preset.value == match:
            return
        self._updating = True
        try:
            preset.value = match
        finally:
            self._updating = False

    def _sync_suffix(self) -> None:
        fmt = self._choice("format", "ansi")
        suffix = _SUFFIX.get(fmt)
        if suffix is None:
            return
        current = Path(self.query_one("#path", Input).value or "banner.ans")
        self._updating = True
        try:
            self.query_one("#path", Input).value = str(current.with_suffix(suffix))
        finally:
            self._updating = False

    def _style(self) -> BannerStyle:
        gradient = self._choice("palette", "rainbow") if self.query_one("#gradient", Switch).value else None
        outline_gradient = self._choice("outline-gradient", "off")
        shadow_symbol = self._choice("shadow-symbol", "same")
        return BannerStyle(
            gradient=gradient,
            direction=self._choice("direction", "horizontal"),
            outline=self.query_one("#outline", Switch).value,
            outline_char=self._choice("symbol", "░"),
            outline_color=COLOURS.get(self._choice("outline-colour", "slate"), DEFAULT_OUTLINE),
            outline_mode=self._choice("outline-mode", "shade"),
            outline_gradient=None if outline_gradient == "off" else outline_gradient,
            shadow=self.query_one("#shadow", Switch).value,
            shadow_dx=self._number("dx", 1),
            shadow_dy=self._number("dy", 1),
            shadow_color=COLOURS.get(self._choice("shadow-colour", "ink"), DEFAULT_SHADOW),
            shadow_char=None if shadow_symbol == "same" else shadow_symbol,
        )

    def _set_animation(self, name: str) -> None:
        self._anim = name if name in {item for _, item in ANIMATIONS} else "none"
        self._frame = 0
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None
        if self._anim != "none":
            self._anim_timer = self.set_interval(0.12, self._tick_animation)
        self._render_preview()

    def _tick_animation(self) -> None:
        self._frame += 1
        self._render_preview()

    def _color(self, widget_id: str, default: Color) -> Color:
        try:
            return Color.from_hex(self.query_one(f"#{widget_id}", Input).value)
        except ValueError:
            return default

    def _number(self, widget_id: str, default: int) -> int:
        raw = self.query_one(f"#{widget_id}", Input).value.strip()
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(-8, min(8, value))

    def _render_preview(self) -> None:
        style = self._style()
        self.query_one("#palette", Select).disabled = style.gradient is None
        self.query_one("#direction", Select).disabled = style.gradient is None
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
            elif self._engine_name() == "tdf" and tdf_ready() and not self._fonts:
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
                key = (font.id, text)
                if key != self._source_key:
                    source, missing, folded = layout_font(text, font)
                    self._source = source
                    self._source_missing = missing
                    self._source_folded = folded
                    self._source_key = key
                    self._relations.drop_splits()
                    self._role_sig = None
                assert self._source is not None
                banner = Banner(
                    present(self._source, style, self._relations, self._anim, self._frame),
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
        outlined = self.query_one("#outline", Switch).value
        adaptive = self._choice("outline-mode", "shade") in {"contour", "heavy", "double", "blocks"}
        self.query_one("#symbol", Select).disabled = (not outlined) or adaptive
        self.query_one("#outline-colour", Select).disabled = not outlined
        self.query_one("#outline-gradient", Select).disabled = not outlined
        self.query_one("#outline-mode", Select).disabled = not outlined
        if not text:
            preview.update(Text("Type a banner.", style="italic #888"))
        elif not banner.grid.rows:
            preview.update(Text("Nothing to draw.", style="italic #888"))
        else:
            focus = self._selected_slot() if self.query_one("#focus-role", Switch).value else None
            preview.update(to_rich(banner.grid, focus))
        meta.update(self._describe(banner))

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
        """Picking a role shows that role and dims the others."""

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
        return " · ".join(parts)
