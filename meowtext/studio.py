"""The focused Kitty editor: compare, style, adjust, save and use."""

from __future__ import annotations

import copy
import os
import re
import shlex
from pathlib import Path

from rich.text import Text
from textual import work, on
from textual.worker import get_current_worker
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import (
    Grid as TileGrid,
    Horizontal,
    Vertical,
    VerticalScroll,
    ScrollableContainer,
)
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from meowtext import library
from meowtext.choices import Choices
from meowtext.inventory import Inventory, Lettering, Showcase, FontCard
from meowtext.catalog import FontInfo, list_fonts, measure_spans, group_fonts
from meowtext.compose import Banner, layout_font, present
from meowtext.discovery import (
    CATEGORIES,
    Discovery,
    Specimen,
    build_index,
    describe,
    font_key,
    starter_index,
)
from meowtext.effects import (
    Animation,
    BannerStyle,
    PALETTES,
    PRESETS,
    GRADIENT_DIRECTIONS,
    OUTLINE_MODES,
    COLOURS,
    SYMBOLS,
    ANIMATIONS,
    ANIM_DIRECTIONS,
    ANIM_LAYERS,
    ANIM_TRAVELS,
    TRACE_PATTERNS,
    TRACE_REVEALS,
    OUTLINE_SCOPES,
    OUTLINE_PLACES,
    OUTLINE_DIRECTIONS,
    resolve_palette,
)
from meowtext.errors import MeowTextError, RenderError
from meowtext.export import FORMATS, FORMAT_LABELS, export_notice
from meowtext.animation_export import export_design
from meowtext.grid import Color, Grid
from meowtext.palette import RelationPalette, used_slots, rgb_to_hsv
from meowtext.packs import (
    load_palettes,
    load_presets,
    load_symbols,
    list_favourites,
    load_favourite,
)
from meowtext.project import Project, save_project, load_project
from meowtext.tui import to_rich, _dim
from meowtext.previews import fit_preview
from meowtext.raster import fit_image

try:
    # Import before Textual owns input: the library queries terminal capabilities.
    from textual_image.widget import TGPImage
except ImportError:
    TGPImage = None


class Preview(Static):
    DEFAULT_CSS = """
    Preview { content-align: center middle; text-wrap: nowrap; overflow: hidden; align: center middle; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.grid = Grid()
        self._picture = None
        self._shown = None

    def compose(self):
        if (
            TGPImage is not None
            and not self.app.is_headless
            and os.environ.get("KITTY_WINDOW_ID")
        ):
            self._picture = TGPImage()
            self._picture.display = False
            yield self._picture

    def show(self, grid: Grid) -> None:
        self.grid = grid
        width, height = self.content_size
        if width < 1 or height < 1:
            return
        native = grid.width <= width and grid.height <= height
        if self._picture is not None:
            self._picture.display = not native and bool(grid.width and grid.height)
        if native or self._picture is None or not grid.width or not grid.height:
            if self._picture is not None and self._picture.image is not None:
                self._picture.image = None
            self.update(fit_preview(grid, width, height))
        else:
            from textual_image._terminal import get_cell_size

            picture, columns, rows = fit_image(grid, width, height, get_cell_size())
            self.update("")
            # Explicit placement fixes the auto-size feedback loop that clipped
            # tall fonts and enlarged small ones. The image includes cell padding.
            self._picture.styles.width = columns
            self._picture.styles.height = rows
            self._picture.image = picture
        self._shown = (id(grid), width, height)

    def on_resize(self) -> None:
        if self._shown != (id(self.grid), *self.content_size):
            self.show(self.grid)


class Inspect(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Back")]
    DEFAULT_CSS = """
    Inspect { align: center middle; background: $background 90%; }
    #inspect-box { width: 95%; height: 90%; border: solid #74e9ef; padding: 1 2; }
    #full-art { width: auto; height: auto; text-wrap: nowrap; }
    #inspect-scroll { height: 1fr; }
    """

    def __init__(self, banner: Banner):
        super().__init__()
        self.banner = banner

    def compose(self) -> ComposeResult:
        with Vertical(id="inspect-box"):
            yield Label(
                f"{self.banner.font.name} · {self.banner.grid.width} × {self.banner.grid.height} cells · scroll to inspect"
            )
            with ScrollableContainer(id="inspect-scroll"):
                yield Static(to_rich(self.banner.grid), id="full-art")
            yield Button("Back to editor", id="close-inspect")

    @on(Button.Pressed, "#close-inspect")
    def close(self):
        self.dismiss()

    def on_mount(self):
        self.query_one("#inspect-scroll").focus()


class MeowText(App):
    TITLE = "meowtext"
    AUTO_FOCUS = "#font-tile-0"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #090f17; color: #d9e4ec; }
    #heading { height: 1; padding: 0 1; background: #10202b; color: #7beaf0; }
    #text-row { height: 3; padding: 0 1; }
    #text-row Label { width: 7; content-align: left middle; }
    #text { width: 1fr; }
    #message { width: 45%; content-align: left middle; padding: 0 1; color: #90a5b4; }
    #body { height: 1fr; }
    #sections { width: 1fr; height: 1fr; }
    ContentSwitcher { height: 1fr; }
    TabPane { padding: 0 1; height: 1fr; }
    #sidebar { width: 29; border-left: solid #29404d; padding: 1; }
    #sidebar Label { height: auto; }
    #selected-name { color: #7beaf0; margin-bottom: 1; }
    #selected-preview { height: 9; }
    #selected-meta { height: auto; color: #90a5b4; margin: 1 0; }
    #sidebar Button { width: 100%; margin-bottom: 1; }
    #sidebar .help { color: #90a5b4; height: auto; margin-top: 1; }
    .toolbar { height: 3; }
    .toolbar Select { width: 22; }
    .toolbar Input { width: 1fr; }
    .toolbar Button { min-width: 7; width: auto; }
    #font-mode { width: 19; }
    #font-count { height: 1; color: #90a5b4; padding: 0 1; }
    #font-scroll, #preset-scroll { height: 1fr; }
    .tiles { grid-size: 2; grid-gutter: 1; height: auto; }
    .tile { height: 10; border: solid #29404d; padding: 0 1; }
    .tile.selected { border: solid #7beaf0; background: #0d222c; }
    .tile-title { height: 1; color: #cce4eb; }
    .tile Preview { height: 6; }
    .tile Horizontal { height: 1; }
    .tile Button { height: 1; min-width: 5; width: 1fr; border: none; padding: 0 1; }
    .tile .star { width: 5; min-width: 5; }
    .tile .like { width: 17; }
    Button { background: #142532; color: #d9e4ec; }
    Button:hover, Button:focus { background: #23424d; color: #7beaf0; }
    Button.-primary { background: #4aa5b3; color: #06151c; }
    Input, Select { border: tall #29404d; }
    Input, SelectCurrent { background: #10212c; color: #d9e4ec; }
    Input:focus, Select:focus SelectCurrent { background: #25414a; color: #e5f4f1; }
    #adjust-scroll, #save-scroll { height: 1fr; padding: 1; }
    #decoration-preview { height: 38%; min-height: 6; border-bottom: solid #29404d; padding: 0 1; }
    #decoration-meta { height: 1; color: #90a5b4; }
    #decoration-tabs { height: 1fr; }
    #decoration-tabs TabPane { padding: 0; }
    .control-scroll { height: 1fr; padding: 0 1; }
    .control-scroll Select, .control-scroll SelectCurrent { height: 1; border: none; padding: 0 1; }
    .control-scroll Select { padding: 0; }
    .control-scroll Input { height: 1; border: none; padding: 0 1; }
    .control-scroll Checkbox { height: 1; border: none; padding: 0; margin: 1 0; }
    .control-grid { grid-size: 2; grid-gutter: 1 2; height: auto; grid-rows: 2; }
    .control-grid > .field { height: 2; margin: 0; }
    .control-grid > Checkbox { height: 1; margin: 0; }
    .control-grid > Button { height: 1; border: none; padding: 0 1; }
    .options-body { height: auto; }
    .field { height: auto; margin-bottom: 1; }
    .field Label { height: 1; color: #90a5b4; }
    .field Select, .field Input { width: 100%; }
    .subsettings { height: auto; border-left: solid #29404d; padding-left: 2; }
    .section-label { color: #7beaf0; margin: 1 0; }
    #save-scroll Button { margin: 1 1 0 0; }
    #usage-command { padding: 1; margin-top: 1; background: #10202b; height: auto; color: #a4f7fa; }
    #usage-help { height: auto; color: #90a5b4; margin-top: 1; }
    #library-select { width: 1fr; }
    #notes { height: 5; }
    #index-state { height: 1; color: #90a5b4; padding: 0 1; }
    .hidden { display: none; }
    Screen.compact #sidebar { display: none; }
    Screen.narrow .tiles { grid-size: 1; }
    Screen.narrow .control-grid { grid-size: 1; }
    Screen.compact #message { display: none; }
    Screen.short #decoration-preview { height: 25%; min-height: 3; }
    #decoration-preview { height: 30%; min-height: 4; max-height: 12; border: double #3fbdca; padding: 0 1; }
    #decoration-meta { height: 1; color: #90a5b4; }
    #decoration-panels { height: 1fr; }
    .bank { width: 1fr; height: 1fr; padding: 0 1; border: solid #294653; }
    .bank:focus-within { border: double #b4ef6b; }
    .bank-title { color: #b4ef6b; text-style: bold; height: 1; margin: 0 0 1 0; }
    .bank .control-grid { grid-size: 1; grid-rows: auto; grid-gutter: 0; height: auto; }
    .bank .field { height: auto; margin: 0 0 1 0; }
    .bank .field Label { color: #8faaba; }
    .bank .field Choices { width: 100%; }
    .bank Checkbox { margin: 0 0 1 0; }
    .bank Button { height: 1; min-height: 1; border: none; padding: 0 1; margin: 0 0 1 0; width: 100%; }
    .bank .help { height: auto; color: #8faaba; margin-top: 1; }
    Screen.short .bank-title { margin: 0; }
    Screen.short .bank .field { margin-bottom: 0; }
    Screen.short #decoration-preview { height: 4; min-height: 3; }
    #text-row { height: 3; padding: 0; background: #12242e; }
    #text-row Label { width: 7; padding-left: 1; }
    #text { border: heavy #28434e; background: #0b1922; }
    #text:focus { border: heavy #b6ef6b; }
    #message { width: 30%; }
    #sidebar { display: none; }
    #sections > ContentTabs { background: #172d38; }
    Tab { color: #b5ccd6; text-style: bold; }
    Tab.-active { background: #55d6e7; color: #08151b; }
    .toolbar { height: 3; }
    .toolbar Button { height: 1; border: none; margin-top: 1; }
    #font-count { height: 1; }
    #font-actions { height: 1; }
    #font-actions Button { margin: 0; }
    .tiles { grid-gutter: 0 1; }
    .tile { padding: 0; border: solid #304858; background: #0e1c27; }
    .tile:focus { border: heavy #bbf578; background: #213840; }
    .tile:focus .tile-title { background: #b6ef6b; color: #06171e; text-style: bold; }
    .tile.selected { border: double #65e8ed; }
    .tile-title { background: #203542; color: #e2f3f4; text-style: bold; padding: 0 1; }
    .tile-detail { height: 1; padding: 0 1; color: #a2b9c6; text-wrap: nowrap; }
    #font-grid { grid-size: 2; }
    Screen.wide #font-grid { grid-size: 3; }
    .bank { height: 1fr; background: #101d28; padding: 0; border: solid #315363; }
    .bank:focus-within { background: #1a3039; border: heavy #b6ef6b; }
    .bank Lettering { background: #1d3341; }
    .bank:focus-within Lettering { color: #b6ef6b; background: #28454a; }
    .bank-readout { height: 1; padding: 0 1; color: #c6d9e0; background: #20343e; text-wrap: nowrap; }
    .detail-scroll { height: 1fr; padding: 0 1; }
    .detail-scroll .control-grid { grid-size: 1; grid-rows: auto; grid-gutter: 0; height: auto; }
    .detail-scroll .field { height: auto; margin-bottom: 1; }
    .detail-scroll Input, .detail-scroll Checkbox { height: 1; border: none; padding: 0; }
    .bank .tune-button { height: 1; margin: 0; width: 100%; background: #28434e; color: #d4ebee; }
    #decoration-preview { height: 26%; min-height: 5; max-height: 10; border: double #65e8ed; }
    #decoration-meta { height: 1; background: #142e37; padding: 0 1; color: #c2dce4; }
    Screen.short Lettering { height: 1; }
    Screen.short #decoration-preview { height: 4; min-height: 4; }
    Screen.narrow Showcase { display: none; }
    Screen.narrow #font-grid { grid-size: 1; }
    #preview-transport { height: 1; background: #142e37; }
    #preview-transport #decoration-meta { width: 1fr; }
    #preview-transport Button { height: 1; min-width: 14; width: auto; border: none; padding: 0 1; }
    """
    BINDINGS = [
        Binding("f5", "ui_motion", "", show=False),
        Binding("f6", "playback", "Play / pause", show=False),
        Binding("ctrl+z", "undo_effect", "Undo", show=False),
        Binding("alt+1", "bank('fill')", "", show=False, priority=True),
        Binding("alt+2", "bank('outline')", "", show=False, priority=True),
        Binding("alt+3", "bank('motion')", "", show=False, priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+f", "fonts", "Fonts", priority=True),
        Binding("ctrl+t", "words", "Text", priority=True),
        Binding("ctrl+s", "save_tab", "Save & use", priority=True),
        Binding("ctrl+p", "inspect", "Inspect", priority=True),
        Binding("escape", "back", "Back", priority=True),
        Binding("f1", "section('fonts')", "", show=False),
        Binding("f2", "section('presets')", "", show=False),
        Binding("f3", "section('adjust')", "", show=False),
        Binding("f4", "section('save')", "", show=False),
    ]

    def __init__(
        self, project: Project | None = None, *, index: list[Specimen] | None = None
    ):
        super().__init__()
        self.project = (
            copy.deepcopy(project)
            if project
            else Project(style=PRESETS["cyan"].clone())
        )
        self._undo = []
        self._provided_index = index
        self.discovery = Discovery(index if index is not None else starter_index())
        self.font: FontInfo | None = None
        if project:
            try:
                self.font = library.project_font(project)
            except RenderError:
                pass
        if self.font is None and self.discovery.all:
            self.font = self.discovery.all[0].font
        self.last_banner: Banner | None = None
        self.source = Grid()
        self.source_key = None
        self.frame = 0
        self.playing = self.project.animation.name != "none"
        self._syncing = False
        self._controls_ready = False
        self._index_ready = index is not None
        self._index_pending = None
        self._query_timer = None
        self._preview_timer = None
        self._favourites = library.favourites()
        self._gallery_generation = 0
        self._preset_page = 0
        self._saved_name = ""
        self._name_auto = True
        self._path_auto = True
        self._dirty = False
        self._missing = ()
        self._folded = False
        self._presets = load_presets()
        self._palettes = load_palettes()
        self._symbols = load_symbols()
        for preset in self._presets.values():
            if (
                preset.gradient in self._palettes
                and preset.gradient not in PALETTES
                and not preset.stops
            ):
                preset.stops = self._palettes[preset.gradient]
            if (
                preset.outline_gradient in self._palettes
                and preset.outline_gradient not in PALETTES
                and not preset.outline_stops
            ):
                preset.outline_stops = self._palettes[preset.outline_gradient]
        self._preset_names = list(self._presets)
        self._role_signature = None
        self._variant_fonts = {}
        self._variants_for = None

    def field(self, label: str, widget, id: str | None = None):
        box = Vertical(Label(label), widget, classes="field", id=id)
        return box

    def decoration(self) -> ComposeResult:
        yield Preview(id="decoration-preview")
        with Horizontal(id="preview-transport"):
            yield Static("", id="decoration-meta", markup=False)
            yield Button("Play · F6", id="preview-play")
            yield Button("↺ Replay", id="preview-replay")
        with Horizontal(id="decoration-panels"):
            with Vertical(id="fill-pane", classes="bank"):
                yield Lettering("LOOKS", id="fill-heading")
                yield Static(
                    "", id="fill-readout", classes="bank-readout", markup=False
                )
                yield Inventory(
                    "look",
                    [
                        (name.replace("-", " ").title(), name)
                        for name in self._preset_names
                    ],
                    value="cyan",
                    id="look-inventory",
                    presets=self._presets,
                )
                with VerticalScroll(id="fill-details", classes="detail-scroll hidden"):
                    yield self.field(
                        "Fill",
                        Choices(
                            [
                                ("Solid", "solid"),
                                ("Gradient", "gradient"),
                                ("Font colours", "original"),
                            ],
                            value="solid",
                            allow_blank=False,
                            id="fill",
                        ),
                    )
                    with TileGrid(classes="control-grid", id="solid-field"):
                        yield self.field(
                            "Colour",
                            Choices(
                                [(n.title(), n) for n in COLOURS]
                                + [("Custom…", "custom")],
                                value="cyan",
                                allow_blank=False,
                                id="solid-name",
                            ),
                        )
                        yield self.field(
                            "Custom colour · #hex",
                            Input("#65e8ed", id="solid"),
                            id="custom-solid-field",
                        )
                    with Vertical(id="gradient-settings", classes="options-body"):
                        with TileGrid(classes="control-grid"):
                            yield self.field(
                                "Palette",
                                Choices(
                                    [(n.title(), n) for n in self._palettes]
                                    + [("Custom…", "custom")],
                                    value="ice",
                                    allow_blank=False,
                                    id="palette",
                                ),
                            )
                            yield self.field(
                                "Direction",
                                Choices(
                                    list(GRADIENT_DIRECTIONS),
                                    value="horizontal",
                                    allow_blank=False,
                                    id="direction",
                                ),
                            )
                        yield self.field(
                            "Custom stops · #cyan,#violet as hex values",
                            Input("#65e8ed,#d39dff", id="stops"),
                            id="stops-field",
                        )
                        yield Checkbox("Hard colour bands", id="bands")
                    yield Checkbox("Lift dark gradients", value=True, id="readable-gradients")
                    yield self.field(
                        "Font colour version",
                        Choices(
                            [],
                            prompt="Original colour version",
                            id="font-variant",
                        ),
                        id="variant-field",
                    )
                    yield self.field(
                        "Rotate font colours · degrees",
                        Input("0", id="hue", type="number"),
                        id="hue-field",
                    )
                    yield Button("Browse preset looks", id="to-presets")
                    yield Button("Paint cells or individual letters", id="paint-open")
                    with Vertical(id="roles-section", classes="options-body"):
                        yield Label("ANSI COLOUR ROLES", classes="bank-title")
                        yield Static(
                            "Edit the related colours in an ANSI font. Choose Original font colours in Fill to use these colours.",
                            id="roles-help",
                        )
                        yield Choices(
                            [], prompt="Choose a colour role", id="role-select"
                        )
                        yield Checkbox(
                            "Focus this colour in the preview", id="role-focus"
                        )
                        yield Button("Split into separate sections", id="role-split")
                        with TileGrid(classes="control-grid", id="role-controls"):
                            yield Checkbox(
                                "Follow the shared hue rotation",
                                id="role-linked",
                            )
                            yield self.field(
                                "Colour · #hex",
                                Input("#ffffff", id="role-colour"),
                            )
                            yield self.field(
                                "Hue · 0–360",
                                Input("0", type="number", id="role-hue"),
                            )
                            yield self.field(
                                "Saturation · 0–100",
                                Input("100", type="number", id="role-sat"),
                            )
                            yield self.field(
                                "Brightness · 0–100",
                                Input("100", type="number", id="role-val"),
                            )
                yield Button(
                    "↵ Tune colour  ·  Tab next panel",
                    id="tune-fill",
                    classes="tune-button",
                )
            with Vertical(id="outline-pane", classes="bank"):
                yield Lettering("EDGES", id="outline-heading")
                yield Static(
                    "", id="outline-readout", classes="bank-readout", markup=False
                )
                yield Inventory(
                    "edge",
                    [("No border", "none"), *OUTLINE_MODES],
                    value="none",
                    id="edge-inventory",
                    presets=self._presets,
                )
                with VerticalScroll(
                    id="outline-details", classes="detail-scroll hidden"
                ):
                    yield self.field(
                        "Border style",
                        Choices(
                            [("Off", "none"), *OUTLINE_MODES],
                            value="none",
                            allow_blank=False,
                            id="outline-mode",
                        ),
                    )
                    with Vertical(id="outline-settings", classes="options-body"):
                        with TileGrid(classes="control-grid"):
                            yield self.field(
                                "Width",
                                Choices(
                                    [("Automatic", "0")]
                                    + [
                                        (
                                            f"{i} cell" + ("s" if i != 1 else ""),
                                            str(i),
                                        )
                                        for i in [1, 2, 3, 4, 6]
                                    ],
                                    value="0",
                                    allow_blank=False,
                                    id="outline-distance",
                                ),
                            )
                            yield self.field(
                                "Around",
                                Choices(
                                    list(OUTLINE_SCOPES),
                                    value="word",
                                    allow_blank=False,
                                    id="outline-scope",
                                ),
                            )
                            yield self.field(
                                "Placement",
                                Choices(
                                    list(OUTLINE_PLACES),
                                    value="both",
                                    allow_blank=False,
                                    id="outline-place",
                                ),
                            )
                            yield self.field(
                                "Fill",
                                Choices(
                                    [
                                        ("Solid", "solid"),
                                        ("Gradient", "gradient"),
                                    ],
                                    value="solid",
                                    allow_blank=False,
                                    id="outline-fill",
                                ),
                            )
                            yield self.field(
                                "Colour",
                                Choices(
                                    [(n.title(), n) for n in COLOURS]
                                    + [("Custom…", "custom")],
                                    value="slate",
                                    allow_blank=False,
                                    id="outline-name",
                                ),
                                id="outline-solid-field",
                            )
                        yield self.field(
                            "Custom colour · #hex",
                            Input("#5a5a6e", id="outline-color"),
                            id="outline-color-field",
                        )
                        with TileGrid(
                            classes="control-grid",
                            id="outline-gradient-settings",
                        ):
                            yield self.field(
                                "Palette",
                                Choices(
                                    [(n.title(), n) for n in self._palettes]
                                    + [("Custom…", "custom")],
                                    value="ice",
                                    allow_blank=False,
                                    id="outline-palette",
                                ),
                            )
                            yield self.field(
                                "Direction",
                                Choices(
                                    list(OUTLINE_DIRECTIONS),
                                    value="horizontal",
                                    allow_blank=False,
                                    id="outline-direction",
                                ),
                            )
                            yield self.field(
                                "Motion speed multiplier",
                                Input("1", type="number", id="outline-speed"),
                            )
                            yield Checkbox("Hard colour bands", id="outline-bands")
                            yield self.field(
                                "Custom stops · #hex,#hex",
                                Input("#65e8ed,#d39dff", id="outline-stops"),
                                id="outline-stops-field",
                            )
                        with TileGrid(classes="control-grid"):
                            yield self.field(
                                "Character",
                                Choices(
                                    list(self._symbols),
                                    value="░",
                                    allow_blank=False,
                                    id="outline-char",
                                ),
                                id="outline-char-field",
                            )
                            yield self.field(
                                "Sides",
                                Choices(
                                    [
                                        ("All sides", "tblr"),
                                        ("Top", "t"),
                                        ("Bottom", "b"),
                                        ("Left", "l"),
                                        ("Right", "r"),
                                        ("Top and bottom", "tb"),
                                        ("Left and right", "lr"),
                                    ],
                                    value="tblr",
                                    allow_blank=False,
                                    id="outline-sides",
                                ),
                            )
                            yield self.field(
                                "Move horizontally",
                                Input("0", type="integer", id="outline-dx"),
                            )
                            yield self.field(
                                "Move vertically",
                                Input("0", type="integer", id="outline-dy"),
                            )
                    yield Label("░ DROP SHADOW", classes="bank-title")
                    yield Checkbox("Drop shadow", id="shadow")
                    with TileGrid(id="shadow-settings", classes="control-grid"):
                        yield self.field(
                            "Colour",
                            Choices(
                                [(n.title(), n) for n in COLOURS]
                                + [("Custom…", "custom")],
                                value="ink",
                                allow_blank=False,
                                id="shadow-name",
                            ),
                        )
                        yield self.field(
                            "Custom colour · #hex",
                            Input("#282830", id="shadow-color"),
                            id="shadow-color-field",
                        )
                        yield self.field(
                            "Character",
                            Choices(
                                [("Copy lettering", "copy")] + list(self._symbols),
                                value="copy",
                                allow_blank=False,
                                id="shadow-char",
                            ),
                        )
                        yield self.field(
                            "Horizontal offset",
                            Input("1", type="integer", id="shadow-dx"),
                        )
                        yield self.field(
                            "Vertical offset",
                            Input("1", type="integer", id="shadow-dy"),
                        )
                yield Button(
                    "↵ Tune border  ·  Tab next panel",
                    id="tune-outline",
                    classes="tune-button",
                )
            with Vertical(id="motion-pane", classes="bank"):
                yield Lettering("MOTION", id="motion-heading")
                yield Static(
                    "", id="motion-readout", classes="bank-readout", markup=False
                )
                yield Inventory(
                    "motion",
                    [("Still", "none"), *list(ANIMATIONS)[1:]],
                    value="none",
                    id="motion-inventory",
                    presets=self._presets,
                )
                with VerticalScroll(
                    id="motion-details", classes="detail-scroll hidden"
                ):
                    yield self.field(
                        "Animation",
                        Choices(
                            list(ANIMATIONS),
                            value="none",
                            allow_blank=False,
                            id="motion",
                        ),
                    )
                    with Vertical(id="motion-settings", classes="options-body"):
                        with TileGrid(classes="control-grid"):
                            yield self.field(
                                "Speed",
                                Choices(
                                    [
                                        ("Slow", "0.5"),
                                        ("Steady", "1"),
                                        ("Fast", "2"),
                                        ("Turbo", "3"),
                                    ],
                                    value="1",
                                    allow_blank=False,
                                    id="speed",
                                ),
                            )
                            yield self.field(
                                "Direction",
                                Choices(
                                    list(ANIM_DIRECTIONS),
                                    value="forward",
                                    allow_blank=False,
                                    id="motion-direction",
                                ),
                            )
                            yield self.field(
                                "Animate",
                                Choices(
                                    list(ANIM_LAYERS),
                                    value="all",
                                    allow_blank=False,
                                    id="motion-layers",
                                ),
                                id="motion-layers-field",
                            )
                            yield self.field(
                                "Colour travel",
                                Choices(
                                    list(ANIM_TRAVELS),
                                    value="360",
                                    allow_blank=False,
                                    id="motion-travel",
                                ),
                                id="motion-travel-field",
                            )
                        with TileGrid(classes="control-grid", id="trace-settings"):
                            yield self.field(
                                "Trace path",
                                Choices(
                                    list(TRACE_PATTERNS),
                                    value="outline",
                                    allow_blank=False,
                                    id="trace-pattern",
                                ),
                            )
                            yield self.field(
                                "Trace behaviour",
                                Choices(
                                    list(TRACE_REVEALS),
                                    value="draw",
                                    allow_blank=False,
                                    id="trace-reveal",
                                ),
                            )
                        yield Button("Pause / play", id="play")
                    yield Static(
                        "HTML5 cycles colours on text cells. APNG, GIF and Kitty keep motion; GIF reduces colours. PNG saves the visible frame. Save a project to keep editing; Watch plays it in Kitty.",
                        classes="help",
                    )

                yield Button(
                    "↵ Tune motion  ·  Tab next panel",
                    id="tune-motion",
                    classes="tune-button",
                )

    def compose(self) -> ComposeResult:
        with Horizontal(id="text-row"):
            yield Showcase(id="showcase")
            yield Label("Words")
            yield Input(
                self.project.text,
                id="text",
                max_length=240,
                placeholder="Type your banner text",
            )
            yield Static(
                "Arrows explore. Tab switches panels. Make something loud.",
                id="message",
                markup=False,
            )
        with Horizontal(id="body"):
            with TabbedContent(id="sections", initial="fonts"):
                with TabPane("▧ FONTS / F1", id="fonts"):
                    with Horizontal(classes="toolbar"):
                        yield Input(
                            placeholder="Find a feeling… gothic, thin, script, ANSI",
                            id="search",
                        )
                        yield Select(
                            [(x, x) for x in CATEGORIES],
                            value="All",
                            allow_blank=False,
                            id="category",
                        )
                        yield Select(
                            [
                                ("Discover", "discover"),
                                ("Browse all", "browse"),
                                ("★ Favourites", "favourites"),
                            ],
                            value="discover",
                            allow_blank=False,
                            id="font-mode",
                        )
                    with Horizontal(classes="toolbar", id="font-actions"):
                        yield Button("← Back", id="font-back")
                        yield Button("More choices", id="font-more")
                        yield Button("Start over", id="font-reset")
                        yield Button("Use font →", id="use-font", variant="primary")
                    yield Static("", id="font-count", markup=False)
                    with VerticalScroll(id="font-scroll"):
                        with TileGrid(classes="tiles", id="font-grid"):
                            for i in range(9):
                                with FontCard(classes="tile", id=f"font-tile-{i}"):
                                    yield Static(
                                        "",
                                        id=f"font-title-{i}",
                                        classes="tile-title",
                                        markup=False,
                                    )
                                    yield Static(
                                        "",
                                        id=f"font-detail-{i}",
                                        classes="tile-detail",
                                        markup=False,
                                    )
                                    yield Preview(id=f"font-preview-{i}")
                                    with Horizontal():
                                        yield Button("Use font →", id=f"choose-{i}")
                                        yield Button(
                                            "☆", id=f"star-{i}", classes="star"
                                        )
                                        yield Button(
                                            "Explore ↻",
                                            id=f"like-{i}",
                                            classes="like",
                                        )
                with TabPane("▤ LOOKS / F2", id="presets"):
                    with Horizontal(classes="toolbar"):
                        yield Button("← Previous", id="preset-prev")
                        yield Button("More presets →", id="preset-next")
                        yield Button("Adjust →", id="to-adjust", variant="primary")
                    yield Static("", id="preset-count")
                    with VerticalScroll(id="preset-scroll"):
                        with TileGrid(classes="tiles"):
                            for i in range(6):
                                with Vertical(classes="tile", id=f"preset-tile-{i}"):
                                    yield Static(
                                        "", id=f"preset-title-{i}", classes="tile-title"
                                    )
                                    yield Preview(id=f"preset-preview-{i}")
                                    yield Button("Apply this look", id=f"preset-{i}")
                with TabPane("◈ DECORATE / F3", id="adjust"):
                    yield from self.decoration()
                with TabPane("↗ SAVE & USE / F4", id="save"):
                    with VerticalScroll(id="save-scroll"):
                        yield Label(
                            "1. Give your design a name", classes="section-label"
                        )
                        yield Input(
                            self._suggested_name(self.project.text),
                            placeholder="e.g. neon-cat",
                            id="save-name",
                        )
                        yield Checkbox(
                            "Replace the saved design with this name", id="replace"
                        )
                        yield Button("Save design", id="save-design", variant="primary")
                        yield Label(
                            "2. Choose where it appears", classes="section-label"
                        )
                        yield Select(
                            [
                                ("Show my banner", "show"),
                                ("Play my animation", "watch"),
                                ("Use the style with new words", "words"),
                                ("Before a command", "before"),
                                ("After a command", "after"),
                                ("Beside a running TUI in Kitty", "frame"),
                                ("Before every command · zsh", "zsh"),
                                ("Before every command · fish", "fish"),
                                ("Put it in Markdown", "markdown"),
                            ],
                            value="show",
                            allow_blank=False,
                            id="use-mode",
                        )
                        yield Input(
                            "ls",
                            placeholder="Command to decorate, e.g. htop",
                            id="target-command",
                        )
                        yield Static(
                            "Save your design above to get a ready-to-use command.",
                            id="usage-command",
                            markup=False,
                        )
                        yield Static("", id="usage-help", markup=False)
                        yield Button("Copy command", id="copy-command")
                        yield Label(
                            "Notes · saved with your design", classes="section-label"
                        )
                        yield TextArea(self.project.notes, id="notes")
                        yield Label("Your saved designs", classes="section-label")
                        yield Select(
                            [], prompt="Open a saved design", id="library-select"
                        )
                        yield Select(
                            [(p.stem, str(p)) for p in list_favourites()],
                            prompt="Open a favourite from the original editor",
                            id="old-favourite",
                        )
                        yield Label("Export or open a project", classes="section-label")
                        yield Select(
                            [(FORMAT_LABELS[x], x) for x in (*FORMATS, "project")],
                            value="html",
                            allow_blank=False,
                            id="format",
                        )
                        yield Input(
                            self._suggested_name(self.project.text) + ".html",
                            placeholder="File path",
                            id="export-path",
                        )
                        yield Static("", id="export-notice", markup=False)
                        yield Button("Export file", id="export-file")
                        yield Button("Open .meowtext project", id="open-project")
            with Vertical(id="sidebar"):
                yield Label("YOUR SELECTION")
                yield Static("", id="selected-name", markup=False)
                yield Preview(id="selected-preview")
                yield Static("", id="selected-meta", markup=False)
                yield Button("Inspect full size", id="inspect")
                yield Button("★ Favourite font", id="favourite")
                yield Button("Save & use →", id="to-save", variant="primary")
                yield Static(
                    "Choose keeps a font.\n\nMore like this narrows the choices.\n\nBack returns to the previous set.",
                    classes="help",
                )
        yield Static("Loading font catalogue…", id="index-state", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        self._resize_layout()
        self._sync_controls()
        self._render_selected()
        self._refresh_gallery()
        self._refresh_library()
        self._usage()
        self.set_interval(0.12, self._tick)
        self.query_one("#font-tile-0").focus()
        self.call_after_refresh(self._enable_edits)
        if self._provided_index is None:
            self._index_fonts()
        else:
            self._index_status(len(self.discovery.all), len(self.discovery.all))

    def _enable_edits(self):
        self._controls_ready = True
        self._fit_tiles()

    def on_descendant_focus(self, event):
        if self._controls_ready and not self._closing and len(self.screen_stack) == 1:
            self._focus_help(event.widget)

    def _focus_help(self, widget=None):
        widget = widget or self.focused
        if isinstance(widget, Inventory):
            label = {"look": "LOOKS", "edge": "EDGES", "motion": "MOTION"}[widget.kind]
            message = f"{label} {widget._index()+1}/{len(widget._options)} · Arrows try · Tab panel · Enter tune · Ctrl+Z undo · F5 freezes interface motion"
        elif isinstance(widget, FontCard):
            message = "Arrows compare · Enter explores · Space uses · F favourites · I full size · Ctrl+T words"
            index = int(widget.id.rsplit("-", 1)[1])
            if index < len(self.discovery.choices):
                item = self.discovery.choices[index]
                self.query_one("#message", Static).update(
                    item.font.name + " · " + item.description
                )
        elif isinstance(widget, Choices):
            message = "Arrows change immediately · Tab next setting · Escape returns to specimens · Alt+1/2/3 switches panels"
        else:
            message = f"{len(self.discovery.all):,} fonts · F1 fonts · F2 looks · F3 decorate · F4 save & use · Ctrl+T words"
        self.query_one("#index-state", Static).update(message)

    def _sync_inventories(self):
        style = self.project.style
        name = next(
            (name for name, preset in self._presets.items() if preset == style),
            Select.BLANK,
        )
        self._set_control("look-inventory", name)
        self._set_control(
            "edge-inventory", style.outline_mode if style.outline else "none"
        )
        self._set_control("motion-inventory", self.project.animation.name)
        for bank, label in (
            (
                "fill",
                (
                    str(name).replace("-", " ").title()
                    if name != Select.BLANK
                    else "Custom look"
                ),
            ),
            ("outline", style.outline_mode.title() if style.outline else "No border"),
            (
                "motion",
                (
                    self.project.animation.name.title()
                    if self.project.animation.name != "none"
                    else "Still"
                ),
            ),
        ):
            self.query_one(f"#{bank}-readout", Static).update(
                "◆ " + label + "  ·  arrows try / ↵ tune"
            )

    def on_inventory_tune(self, event: Inventory.Tune):
        name = {"look": "fill", "edge": "outline", "motion": "motion"}[
            event.inventory.kind
        ]
        self._tune_bank(name)

    def _tune_bank(self, name, close=False):
        details = self.query_one(f"#{name}-details")
        inventory = self.query_one(
            {
                "fill": "#look-inventory",
                "outline": "#edge-inventory",
                "motion": "#motion-inventory",
            }[name]
        )
        opening = not close and not details.display
        self.set_focus(None)
        details.set_class(not opening, "hidden")
        inventory.display = not opening
        self.query_one(f"#tune-{name}", Button).label = (
            "Esc · back to specimens" if opening else "↵ Tune  ·  Tab next panel"
        )
        target = (
            self.query_one(
                {"fill": "#fill", "outline": "#outline-mode", "motion": "#motion"}[name]
            )
            if opening
            else inventory
        )
        self.call_after_refresh(target.focus)

    def _remember_effect(self):
        if self._controls_ready:
            self._undo.append(copy.deepcopy(self.project))
            self._undo = self._undo[-40:]

    def action_undo_effect(self):
        if self._undo and self.query_one("#sections", TabbedContent).active == "adjust":
            self.project = self._undo.pop()
            self.frame = 0
            self.source_key = None
            self.playing = self.project.animation.name != "none"
            self._sync_controls()
            self._render_selected()
            self._dirty = True
            self._say("Previous effect restored")

    def action_ui_motion(self):
        widget = self.query_one("#showcase", Showcase)
        widget.running = not widget.running
        self._say(
            "Interface motion playing"
            if widget.running
            else "Interface motion paused · F5 resumes"
        )

    def action_playback(self):
        if self.project.animation.name == "none":
            self._say("Choose a motion specimen to animate this artwork.")
            return
        self.playing = not self.playing
        self._visibility()
        self._say("Animation playing" if self.playing else "Animation paused · F6 resumes")

    def font_action(self, action, index):
        if index >= len(self.discovery.choices):
            return
        item = self.discovery.choices[index]
        if action == "inspect":
            try:
                grid, missing, folded = layout_font(
                    self.query_one("#text", Input).value, item.font
                )
                self.push_screen(
                    Inspect(
                        Banner(present(grid, BannerStyle()), item.font, missing, folded)
                    )
                )
            except (MeowTextError, ValueError) as exc:
                self._say(str(exc))
            return
        if action == "star":
            library.toggle_favourite(item.font)
            self._favourites = library.favourites()
            self._refresh_gallery()
        else:
            self._set_font(item.font)
            if action == "like":
                self.discovery.narrow(index)
                self._refresh_gallery()
                self.query_one("#font-tile-0").focus()
            else:
                self.action_section("adjust")

    def move_card(self, index, x, y):
        columns = (
            3
            if self.screen.has_class("wide")
            else 1 if self.screen.has_class("narrow") else 2
        )
        index = (index + x + y * columns) % max(1, len(self.discovery.choices))
        self.query_one(f"#font-tile-{index}").focus()

    @work(thread=True, exclusive=True, group="index")
    def _index_fonts(self) -> None:
        worker = get_current_worker()
        try:
            result = build_index(
                progress=lambda n, t: self.call_later(self._index_status, n, t),
                stopped=lambda: worker.is_cancelled,
            )
            if not worker.is_cancelled:
                self.call_later(self._indexed, result)
        except Exception as exc:
            if not worker.is_cancelled:
                self.call_later(
                    self._say,
                    f"Could not index every font: {exc}. The starter fonts are available.",
                )

    def _index_status(self, current: int, total: int) -> None:
        self.screen_stack[0].query_one("#index-state", Static).update(
            f"Indexing fonts {current:,}/{total:,} · you can browse the starter set now"
            if current < total
            else f"{total:,} font families indexed locally · Tab moves focus · F1–F4 change section"
        )
        if current == total and len(self.screen_stack) == 1:
            self._focus_help()

    def _indexed(self, items: list[Specimen]) -> None:
        self._index_ready = True
        self.discovery.all = items
        # Avoid replacing the user's current narrowing round under their cursor.
        if self.discovery.history or len(self.screen_stack) > 1:
            self._index_pending = items
            self._say("Full library ready. Start over to explore all fonts.")
        else:
            self._filter()

    def _say(self, message: str) -> None:
        self.screen_stack[0].query_one("#message", Static).update(message)
        if self.size.width < 105:
            self.notify(message, timeout=4)

    def _set_font(self, font: FontInfo) -> None:
        changed = self.font is not None and self.font.id != font.id
        self.font = font
        self.project.engine, self.project.font_name = font.engine, font.name
        self.project.font_source, self.project.font_index = font.source, font.index
        if changed:
            self.project.roles = {}
            self.project.patches = ()
            self.project.letters = {}
            self.project.role_splits = ()
        self._dirty = True
        self._render_selected()

    def _render_selected(self) -> None:
        if self.font is None:
            self._say(
                "No fonts installed. Install figlet and restart, or add TheDraw fonts."
            )
            return
        self.project.text = self.query_one("#text", Input).value
        self.project.engine, self.project.font_name = self.font.engine, self.font.name
        self.project.font_source, self.project.font_index = (
            self.font.source,
            self.font.index,
        )
        try:
            key = (
                self.font.id,
                self.project.text,
                id(self.project.letters),
                self.project.role_splits,
            )
            if key != self.source_key:
                self.source, self._missing, self._folded = layout_font(
                    self.project.text, self.font, self.project.letters or None
                )
                self.project.roles = library.prepare_roles(
                    self.source, self.project
                ).roles
                self.source_key = key
                self._role_signature = None
            if (
                (self.project.animation.name == "trace"
                 or (self.project.style.outline and self.project.style.outline_scope == "letter"))
                and not self.source.spans
            ):
                self.source.spans = measure_spans(self.font, self.project.text)
            relations = RelationPalette(hue=self.project.hue, roles=self.project.roles)
            relations.ensure(self.source)
            grid = present(
                self.source,
                self.project.style,
                relations,
                animation=self.project.animation,
                frame=self.frame,
                patches=self.project.patches,
            )
            self.last_banner = Banner(grid, self.font, self._missing, self._folded)
            self._export_notice()
            preview_grid = grid
            focused = self.query_one("#role-select", Choices).value
            if (
                self.query_one("#role-focus", Checkbox).value
                and focused != Select.BLANK
            ):
                preview_grid = grid.copy()
                for row in preview_grid.rows:
                    for cell in row:
                        if cell.fg_slot != int(focused) and cell.bg_slot != int(
                            focused
                        ):
                            cell.fg, cell.bg = _dim(cell.fg), _dim(cell.bg)
            self.query_one("#selected-preview", Preview).show(preview_grid)
            self.query_one("#decoration-preview", Preview).show(preview_grid)
            self.query_one("#decoration-meta", Static).update(
                f"{self.font.name} · {grid.width} × {grid.height} cells · Ctrl+P inspects at full size · Ctrl+S saves"
            )
            self.query_one("#selected-name", Static).update(self.font.name)
            detail = f"{grid.width} × {grid.height} cells"
            if self._missing:
                detail += "\nMissing: " + " ".join(self._missing)
            if self._folded:
                detail += "\nUppercase substituted"
            self.query_one("#selected-meta", Static).update(detail)
        except (MeowTextError, ValueError) as exc:
            self.last_banner = None
            self._say(str(exc))
        self._mark_selected()
        self._refresh_roles()
        self._refresh_variants()

    def _refresh_variants(self):
        if self.font is None or self._variants_for == self.font.id:
            return
        self._variants_for = self.font.id
        members = next(
            (
                family.members
                for family in group_fonts(list_fonts(self.font.engine))
                if self.font in family.members
            ),
            (self.font,),
        )
        self._variant_fonts = {str(i): font for i, font in enumerate(members)}
        widget = self.query_one("#font-variant", Choices)
        with widget.prevent(widget.Changed):
            widget.set_options(
                [(font.name, key) for key, font in self._variant_fonts.items()]
            )
            widget.value = next(
                key for key, font in self._variant_fonts.items() if font == self.font
            )
        self._visibility()

    def _refresh_roles(self):
        slots = used_slots(self.source)
        signature = tuple((slot, self.project.roles[slot].name) for slot in slots)
        if signature == self._role_signature:
            return
        self._role_signature = signature
        widget = self.query_one("#role-select", Choices)
        with widget.prevent(widget.Changed):
            widget.set_options(
                [(self.project.roles[slot].name, str(slot)) for slot in slots]
            )
            if slots:
                widget.value = str(slots[0])
        self.query_one("#roles-section").display = bool(slots)
        self.query_one("#role-controls").display = bool(slots)
        self.query_one("#role-select").display = bool(slots)
        self.query_one("#role-focus").display = bool(slots)
        self.query_one("#role-split").display = bool(slots)
        self.query_one("#roles-help", Static).update(
            "Edit related colours in this ANSI font. Choose Original font colours in Fill to see these changes."
            if slots
            else "This font has no colour roles. Use Fill to colour it, or choose an ANSI colour font."
        )
        if slots:
            self._show_role()

    def _show_role(self):
        selected = self.query_one("#role-select", Choices).value
        if selected == Select.BLANK:
            return
        role = self.project.roles.get(int(selected))
        if role is None:
            return
        tint = role.paint(self.project.hue)
        hue, sat, val = rgb_to_hsv(tint)
        for key, value in {
            "role-linked": role.linked,
            "role-colour": tint.hex(),
            "role-hue": round(hue, 2),
            "role-sat": round(sat * 100, 2),
            "role-val": round(val * 100, 2),
        }.items():
            self._set_control(key, value)

    def _edit_role(self, name):
        selected = self.query_one("#role-select", Choices).value
        if selected == Select.BLANK:
            return
        palette = RelationPalette(hue=self.project.hue, roles=self.project.roles)
        slot = int(selected)
        try:
            if name == "role-linked":
                (
                    palette.link_role(slot)
                    if self.query_one("#role-linked", Checkbox).value
                    else palette.break_role(slot)
                )
            elif name == "role-colour":
                palette.set_hsv(
                    slot,
                    *rgb_to_hsv(
                        Color.from_hex(self.query_one("#role-colour", Input).value)
                    ),
                )
            else:
                palette.set_hsv(
                    slot,
                    float(self.query_one("#role-hue", Input).value),
                    float(self.query_one("#role-sat", Input).value) / 100,
                    float(self.query_one("#role-val", Input).value) / 100,
                )
        except ValueError:
            return
        self._dirty = True
        self._show_role()
        self._render_selected()

    def _mark_selected(self):
        for i, item in enumerate(self.discovery.choices):
            self.query_one(f"#font-tile-{i}").set_class(
                self.font is not None and item.font.id == self.font.id, "selected"
            )

    def _filter(self) -> None:
        category = str(self.query_one("#category", Select).value)
        mode = str(self.query_one("#font-mode", Select).value)
        query = self.query_one("#search", Input).value
        if mode == "favourites":
            # A starred colour variant may be absent from the family representatives.
            missing = self._favourites - {
                font_key(item.font) for item in self.discovery.all
            }
            if missing:
                for engine in ("figlet", "toilet", "tdf"):
                    for font in list_fonts(engine):
                        if font_key(font) in missing:
                            try:
                                self.discovery.all.append(
                                    describe(layout_font("MEOW", font)[0], font)
                                )
                            except (MeowTextError, ValueError):
                                pass
        self.discovery.reset(
            category, query, self._favourites if mode == "favourites" else None
        )
        self._browse_page = 0
        if mode != "discover":
            self.discovery.choices = self.discovery.pool[: self.discovery.count]
        self._refresh_gallery()

    def _refresh_gallery(self) -> None:
        self._gallery_generation += 1
        generation = self._gallery_generation
        choices = self.discovery.choices
        for i in range(9):
            tile = self.query_one(f"#font-tile-{i}")
            tile.display = i < len(choices)
            if i < len(choices):
                item = choices[i]
                self.query_one(f"#font-title-{i}", Static).update(
                    f"{i+1}  {item.font.name}"
                )
                relation = (
                    "Wildcard · " if item.font.id in self.discovery.explorers else ""
                )
                self.query_one(f"#font-detail-{i}", Static).update(
                    relation + item.description
                )
                tile.tooltip = (
                    item.font.name
                    + " · "
                    + item.description
                    + " · I inspects at full size"
                )
                self.query_one(f"#star-{i}", Button).label = (
                    "★" if font_key(item.font) in self._favourites else "☆"
                )
                self.query_one(f"#font-preview-{i}", Preview).update("Rendering…")
        note = f"{len(self.discovery.pool):,} nearby / {len(self.discovery.all):,} fonts · Enter explores · Space uses · F favourites · Wildcards keep other directions open"
        if not choices:
            note = "No matches. Try All, clear the search, or star some fonts first."
        self.query_one("#font-count", Static).update(note)
        self.query_one("#font-back", Button).disabled = not self.discovery.history
        self._mark_selected()
        self._draw_gallery(generation, choices[:], self.query_one("#text", Input).value)

    @work(thread=True, exclusive=True, group="gallery")
    def _draw_gallery(self, generation, choices, words):
        worker = get_current_worker()
        for i, item in enumerate(choices):
            if worker.is_cancelled:
                return
            try:
                source, missing, folded = layout_font(words, item.font)
                grid = present(source, BannerStyle())
                warning = (
                    "Missing: " + " ".join(missing)
                    if missing
                    else "Uppercase font" if folded else ""
                )
                self.call_later(
                    self._gallery_result, generation, i, grid, None, warning
                )
            except (MeowTextError, ValueError) as exc:
                self.call_later(self._gallery_result, generation, i, None, str(exc))

    def _gallery_result(self, generation, index, grid, error, warning=""):
        if generation != self._gallery_generation:
            return
        editor = self.screen_stack[0]
        view = editor.query_one(f"#font-preview-{index}", Preview)
        if grid is not None:
            view.show(grid)
            if warning:
                item = self.discovery.choices[index]
                editor.query_one(f"#font-detail-{index}", Static).update(
                    warning + " · " + item.description
                )
        else:
            view.update(error or "Could not render")

    def _refresh_presets(self):
        names = self._preset_names[self._preset_page * 6 : self._preset_page * 6 + 6]
        self.query_one("#preset-count", Static).update(
            f"{self._preset_page*6+1}–{self._preset_page*6+len(names)} of {len(self._preset_names)} looks · your words and font stay selected"
        )
        for i in range(6):
            self.query_one(f"#preset-tile-{i}").display = i < len(names)
            if i < len(names):
                name = names[i]
                self.query_one(f"#preset-title-{i}", Static).update(name)
                self.query_one(f"#preset-preview-{i}", Preview).show(
                    present(self.source, self._presets[name])
                )

    @staticmethod
    def _suggested_name(words):
        return (
            re.sub(r"[^A-Za-z0-9_-]+", "-", words.strip()).strip("-_")[:64]
            or "my-banner"
        )

    def _auto_names(self):
        if self._name_auto:
            widget = self.query_one("#save-name", Input)
            with widget.prevent(Input.Changed):
                widget.value = self._suggested_name(
                    self.query_one("#text", Input).value
                )
        self._auto_path()
        self._usage()

    def _auto_path(self, *, format_changed=False):
        self._export_notice()
        widget = self.query_one("#export-path", Input)
        fmt = str(self.query_one("#format", Select).value)
        ext = {
            "project": "meowtext",
            "plain": "txt",
            "ansi": "ans",
            "markdown": "md",
        }.get(fmt, fmt)
        if self._path_auto:
            name = self._suggested_name(self.query_one("#save-name", Input).value)
            path = str(Path(widget.value).parent / f"{name}.{ext}")
        elif format_changed:
            path = (
                str(Path(widget.value).with_suffix(f".{ext}"))
                if widget.value.strip()
                else ""
            )
        else:
            return
        with widget.prevent(Input.Changed):
            widget.value = path

    def _set_control(self, name, value):
        widget = self.query_one(f"#{name}")
        if isinstance(widget, (Select, Choices)):
            # Preserve values from older projects even if they aren't a standard option.
            with widget.prevent(widget.Changed):
                if value != Select.BLANK and value not in {
                    v for _, v in widget._options
                }:
                    widget.set_options(list(widget._options) + [(str(value), value)])
                widget.value = value
        elif isinstance(widget, Input):
            with widget.prevent(Input.Changed):
                widget.value = str(value)
        elif isinstance(widget, Checkbox):
            with widget.prevent(Checkbox.Changed):
                widget.value = value

    def _palette_stops(self, name):
        return self._palettes[name] if name in self._palettes else resolve_palette(name)

    def _sync_controls(self):
        self._syncing = True
        style, motion = self.project.style, self.project.animation
        solid = bool(style.stops and len(set(style.stops)) == 1)
        colour = style.stops[0] if solid else Color.from_hex("#65e8ed")
        values = {
            "fill": (
                "solid"
                if solid
                else "gradient" if style.gradient or style.stops else "original"
            ),
            "solid-name": next(
                (n for n, c in COLOURS.items() if c == colour), "custom"
            ),
            "solid": colour.hex(),
            "palette": (
                "custom" if style.stops and not solid else style.gradient or "ice"
            ),
            "stops": ",".join(
                c.hex()
                for c in style.stops or self._palette_stops(style.gradient or "ice")
            ),
            "direction": style.direction,
            "bands": style.bands,
            "readable-gradients": style.readable_gradients,
            "outline-mode": style.outline_mode if style.outline else "none",
            "outline-distance": str(style.outline_distance),
            "outline-scope": style.outline_scope,
            "outline-place": style.outline_place,
            "outline-sides": style.outline_sides,
            "outline-char": style.outline_char,
            "outline-color": style.outline_color.hex(),
            "outline-name": next(
                (n for n, c in COLOURS.items() if c == style.outline_color), "custom"
            ),
            "outline-fill": (
                "gradient" if style.outline_gradient or style.outline_stops else "solid"
            ),
            "outline-palette": (
                "custom" if style.outline_stops else style.outline_gradient or "ice"
            ),
            "outline-stops": ",".join(
                c.hex()
                for c in style.outline_stops
                or self._palette_stops(style.outline_gradient or "ice")
            ),
            "outline-direction": style.outline_direction,
            "outline-speed": style.outline_speed,
            "outline-bands": style.outline_bands,
            "outline-dx": style.outline_dx,
            "outline-dy": style.outline_dy,
            "shadow": style.shadow,
            "shadow-color": style.shadow_color.hex(),
            "shadow-name": next(
                (n for n, c in COLOURS.items() if c == style.shadow_color), "custom"
            ),
            "shadow-char": style.shadow_char or "copy",
            "shadow-dx": style.shadow_dx,
            "shadow-dy": style.shadow_dy,
            "hue": self.project.hue,
            "motion": motion.name,
            "speed": str(motion.speed).removesuffix(".0"),
            "motion-direction": motion.direction,
            "motion-layers": motion.layers,
            "motion-travel": str(motion.travel),
            "trace-pattern": motion.pattern,
            "trace-reveal": motion.reveal,
        }
        try:
            for name, value in values.items():
                self._set_control(name, value)
        finally:
            self._syncing = False
        self._visibility()
        self._sync_inventories()

    def _visibility(self):
        select = lambda name: self.query_one(f"#{name}", Choices).value
        mode, motion = select("fill"), select("motion")
        self.query_one("#solid-field").display = mode == "solid"
        self.query_one("#custom-solid-field").display = select("solid-name") == "custom"
        self.query_one("#gradient-settings").display = mode == "gradient"
        self.query_one("#stops-field").display = select("palette") == "custom"
        self.query_one("#variant-field").display = (
            mode == "original" and len(self._variant_fonts) > 1
        )
        self.query_one("#hue-field").display = (
            mode == "original" and self.font is not None and self.font.kind == "color"
        )
        self.query_one("#outline-settings").display = self.project.style.outline
        self.query_one("#outline-solid-field").display = (
            select("outline-fill") == "solid"
        )
        self.query_one("#outline-color-field").display = (
            select("outline-name") == "custom"
        )
        self.query_one("#outline-gradient-settings").display = (
            select("outline-fill") == "gradient"
        )
        self.query_one("#outline-stops-field").display = (
            select("outline-palette") == "custom"
        )
        self.query_one("#outline-char-field").display = select("outline-mode") in {
            "shade",
            "thick",
        }
        self.query_one("#shadow-settings").display = self.query_one(
            "#shadow", Checkbox
        ).value
        self.query_one("#shadow-color-field").display = (
            select("shadow-name") == "custom"
        )
        self.query_one("#motion-settings").display = motion != "none"
        self.query_one("#motion-layers-field").display = motion in {"hue", "march"}
        self.query_one("#motion-travel-field").display = motion in {"hue", "march"}
        self.query_one("#trace-settings").display = motion == "trace"
        self.query_one("#play", Button).label = (
            "Pause preview" if self.playing else "Play preview"
        )
        self.query_one("#preview-play", Button).label = (
            "Ⅱ Pause · F6" if self.playing else "▶ Play · F6"
        )
        self.query_one("#preview-play", Button).disabled = motion == "none"
        self.query_one("#preview-replay", Button).disabled = motion == "none"

    def _adjust(self, id):
        if self._syncing:
            return
        if id in {"role-linked", "role-colour", "role-hue", "role-sat", "role-val"}:
            self._edit_role(id)
            return
        self._remember_effect()
        style, motion = self.project.style, self.project.animation
        select = lambda name: str(self.query_one(f"#{name}", Choices).value)
        value = lambda name: self.query_one(f"#{name}", Input).value
        check = lambda name: self.query_one(f"#{name}", Checkbox).value

        def colour(name, custom):
            return COLOURS[name] if name in COLOURS else Color.from_hex(value(custom))

        try:
            if id in {"fill", "solid", "solid-name", "palette", "stops"}:
                mode = select("fill")
                if mode == "solid":
                    tint = colour(select("solid-name"), "solid")
                    style.gradient, style.stops = None, (tint, tint)
                elif mode == "original":
                    style.gradient, style.stops = None, None
                else:
                    palette = select("palette")
                    stops = (
                        resolve_palette(value("stops"))
                        if palette == "custom"
                        else self._palettes.get(palette)
                    )
                    style.gradient, style.stops = (
                        None if palette == "custom" else palette
                    ), stops
                style.recolour_roles = mode != "original"
            if id in {
                "outline-fill",
                "outline-palette",
                "outline-stops",
                "outline-name",
                "outline-color",
            }:
                if select("outline-fill") == "solid":
                    style.outline_color = colour(
                        select("outline-name"), "outline-color"
                    )
                    style.outline_gradient, style.outline_stops = None, None
                else:
                    palette = select("outline-palette")
                    stops = (
                        resolve_palette(value("outline-stops"))
                        if palette == "custom"
                        else self._palettes.get(palette)
                    )
                    style.outline_gradient = (
                        value("outline-stops") if palette == "custom" else palette
                    )
                    style.outline_stops = stops
            for name, attr in {
                "direction": "direction",
                "outline-scope": "outline_scope",
                "outline-place": "outline_place",
                "outline-sides": "outline_sides",
                "outline-char": "outline_char",
                "outline-direction": "outline_direction",
            }.items():
                if id == name:
                    setattr(style, attr, select(name))
            for name in {"shadow", "bands", "outline-bands", "readable-gradients"}:
                if id == name:
                    setattr(style, name.replace("-", "_"), check(name))
            if id == "outline-mode":
                style.outline = select(id) != "none"
                if style.outline:
                    style.outline_mode = select(id)
            if id == "outline-distance":
                style.outline_distance = int(select(id))
            if id == "outline-speed":
                style.outline_speed = max(0.05, min(10, float(value(id))))
            if id in {"outline-dx", "outline-dy", "shadow-dx", "shadow-dy"}:
                setattr(style, id.replace("-", "_"), max(-10, min(10, int(value(id)))))
            if id in {"shadow-name", "shadow-color"}:
                style.shadow_color = colour(select("shadow-name"), "shadow-color")
            if id == "shadow-char":
                style.shadow_char = None if select(id) == "copy" else select(id)
            if id == "hue":
                self.project.hue = float(value(id)) % 360
                self._show_role()
            if id == "motion":
                motion.name = select(id)
                self.frame = 0
                self.playing = motion.name != "none"
            if id == "speed":
                motion.speed = float(select(id))
            if id == "motion-direction":
                motion.direction = select(id)
            if id == "motion-layers":
                motion.layers = select(id)
            if id == "motion-travel":
                motion.travel = int(select(id))
            if id == "trace-pattern":
                motion.pattern = select(id)
            if id == "trace-reveal":
                motion.reveal = select(id)
        except (ValueError, RenderError):
            self._say("Enter a valid colour (#65e8ed) or number to apply this setting.")
            return
        self._dirty = True
        self._visibility()
        self._sync_inventories()
        self._render_selected()

    def on_select_changed(self, event: Select.Changed):
        if not self._controls_ready or self._syncing:
            return
        id = event.select.id
        if id in {"category", "font-mode"}:
            self._filter()
        elif id == "use-mode":
            self._usage()
        elif id == "role-select":
            self._show_role()
            self._render_selected()
        elif id == "font-variant" and str(event.value) in self._variant_fonts:
            self._set_font(self._variant_fonts[str(event.value)])
        elif id == "old-favourite" and event.value != Select.BLANK:
            try:
                self._open_project(load_favourite(Path(str(event.value))))
            except (MeowTextError, OSError, ValueError) as exc:
                self._say(str(exc))
        elif id == "library-select" and event.value != Select.BLANK:
            self._open_saved(str(event.value))
        elif id == "format":
            self._auto_path(format_changed=True)
        else:
            self._adjust(id)

    def on_choices_changed(self, event: Choices.Changed):
        if not self._controls_ready or self._syncing:
            return
        name = event.control.id
        if name == "look-inventory":
            self._remember_effect()
            if event.value in self._presets:
                self.project.style = self._presets[event.value].clone()
                self._dirty = True
                self._sync_controls()
                self._render_selected()
        elif name in {"edge-inventory", "motion-inventory"}:
            target = "outline-mode" if name == "edge-inventory" else "motion"
            self._set_control(target, event.value)
            self._adjust(target)
        elif name == "role-select":
            self._show_role()
            self._render_selected()
        elif name == "font-variant" and str(event.value) in self._variant_fonts:
            self._set_font(self._variant_fonts[str(event.value)])
        else:
            self._adjust(name)
        self._focus_help()

    def on_checkbox_changed(self, event: Checkbox.Changed):
        if event.checkbox.id == "role-focus":
            if self._controls_ready:
                self._render_selected()
            return
        if self._controls_ready and event.checkbox.id != "replace":
            self._adjust(event.checkbox.id)

    def on_text_area_changed(self, event: TextArea.Changed):
        if self._controls_ready and not self._syncing:
            self.project.notes = event.text_area.text
            self._dirty = True

    def on_input_changed(self, event: Input.Changed):
        if not self._controls_ready or self._syncing:
            return
        id = event.input.id
        if id == "search":
            if self._query_timer:
                self._query_timer.stop()
            self._query_timer = self.set_timer(0.12, self._filter)
        elif id == "text":
            self._dirty = True
            if self._preview_timer:
                self._preview_timer.stop()
            self._preview_timer = self.set_timer(0.12, self._text_changed)
        elif id == "save-name":
            self._name_auto = False
            self._auto_path()
            self._usage()
        elif id == "target-command":
            self._usage()
        elif id == "export-path":
            self._path_auto = False
        else:
            self._adjust(id)

    def _text_changed(self):
        self._auto_names()
        self._render_selected()
        self._refresh_gallery()
        self._refresh_presets()

    def on_tabbed_content_tab_activated(self, event):
        if event.tabbed_content.id != "sections":
            return
        self.query_one("#sidebar").display = False
        if event.pane.id == "presets":
            self._refresh_presets()
        if event.pane.id == "adjust":
            self._visibility()
        if event.pane.id == "save":
            self._usage()

    def on_button_pressed(self, event: Button.Pressed):
        id = event.button.id or ""
        if id.startswith("tune-"):
            self._tune_bank(id.removeprefix("tune-"))
        elif id.startswith(("choose-", "like-", "star-")):
            action, index = id.rsplit("-", 1)
            self.font_action(action, int(index))
        elif id == "font-back":
            self.discovery.back()
            self._refresh_gallery()
        elif id == "font-reset":
            with self.query_one("#category").prevent(Select.Changed):
                self.query_one("#category", Select).value = "All"
            with self.query_one("#search").prevent(Input.Changed):
                self.query_one("#search", Input).value = ""
            self._filter()
        elif id == "font-more":
            if self.query_one("#font-mode", Select).value == "discover":
                self.discovery.more()
            else:
                self._browse_page = (getattr(self, "_browse_page", 0) + 1) % max(
                    1,
                    (len(self.discovery.pool) + self.discovery.count - 1)
                    // self.discovery.count,
                )
                self.discovery.choices = self.discovery.pool[
                    self._browse_page
                    * self.discovery.count : (self._browse_page + 1)
                    * self.discovery.count
                ]
            self._refresh_gallery()
        elif id == "use-font":
            self.action_section("adjust")
        elif id == "to-presets":
            self.action_section("presets")
        elif id == "paint-open" and self.last_banner:
            from meowtext.paint_editor import PaintEditor

            self.push_screen(
                PaintEditor(self.project, self.font, self.last_banner.grid),
                self._paint_result,
            )
        elif id == "role-split":
            slot = self.query_one("#role-select", Choices).value
            if slot != Select.BLANK:
                before = len(used_slots(self.source))
                self.project.role_splits += (int(slot),)
                self.source_key = None
                self._dirty = True
                self._render_selected()
                added = len(used_slots(self.source)) - before
                self._say(
                    f"Created {added} separate colour roles"
                    if added
                    else "This colour is already one section"
                )
        elif id == "to-adjust":
            self.action_section("adjust")
        elif id == "to-save":
            self.action_save_tab()
        elif id == "inspect":
            self.action_inspect()
        elif id == "favourite" and self.font:
            enabled = library.toggle_favourite(self.font)
            self._favourites = library.favourites()
            self._refresh_gallery()
            self._say(
                "Font added to favourites"
                if enabled
                else "Font removed from favourites"
            )
        elif id in {"preset-next", "preset-prev"}:
            self._preset_page = (
                self._preset_page + (1 if id == "preset-next" else -1)
            ) % ((len(self._preset_names) + 5) // 6)
            self._refresh_presets()
        elif id.startswith("preset-"):
            index = self._preset_page * 6 + int(id.split("-")[1])
            self.project.style = self._presets[self._preset_names[index]].clone()
            self._dirty = True
            self._sync_controls()
            self._render_selected()
        elif id in {"play", "preview-play"}:
            self.action_playback()
        elif id == "preview-replay":
            self.frame = 0
            self.playing = self.project.animation.name != "none"
            self._visibility()
            self._render_selected()
        elif id == "save-design":
            self._save()
        elif id == "copy-command":
            if self._saved_name and not self._dirty:
                self.copy_to_clipboard(self.usage_command)
                self._say("Command copied. Paste it into your Kitty terminal.")
            else:
                self._say("Save this design first, then copy its command.")
        elif id == "export-file":
            self._export()
        elif id == "open-project":
            try:
                self._open_project(
                    load_project(Path(self.query_one("#export-path", Input).value))
                )
            except (MeowTextError, OSError, ValueError) as exc:
                self._say(str(exc))

    def _paint_result(self, project):
        if project is None:
            return
        self.project.patches = project.patches
        self.project.letters = project.letters
        self.source_key = None
        self._dirty = True
        self._render_selected()

    def _tick(self):
        # Timers may run while a modal owns the screen or children unmount.
        # Never query the editor through the active modal, or a partial DOM.
        if (
            self._closing
            or not self.is_running
            or len(self.screen_stack) != 1
            or not self.query("#showcase")
            or not self.query("#sections")
        ):
            return
        if (
            self.query_one("#sections", TabbedContent).active == "adjust"
            and len(self.screen_stack) == 1
        ):
            self._inventory_frame = getattr(self, "_inventory_frame", 0) + 1
            if self.query_one("#showcase", Showcase).running:
                self.query_one("#motion-inventory", Inventory).advance(
                    self._inventory_frame
                )
        if (
            self.playing
            and self.project.animation.name != "none"
            and self.query_one("#sections", TabbedContent).active == "adjust"
            and len(self.screen_stack) == 1
        ):
            self.frame += 1
            self._render_selected()

    def _save(self):
        try:
            self._render_selected()
            if self.last_banner is None:
                raise RenderError("Choose a font and enter some text first")
            name = self.query_one("#save-name", Input).value.strip()
            library.save(
                name,
                self.project,
                grid=self.last_banner.grid,
                replace=self.query_one("#replace", Checkbox).value,
            )
            self._saved_name = name
            self._dirty = False
            self._refresh_library()
            self._usage()
            self._say(f"Saved {name}. Choose how to use it below.")
        except (MeowTextError, OSError, ValueError) as exc:
            self._say(str(exc))

    def _refresh_library(self):
        widget = self.query_one("#library-select", Select)
        with widget.prevent(widget.Changed):
            widget.set_options([(name, name) for name in library.entries()])

    def _open_saved(self, name):
        try:
            self._open_project(library.load(name))
            self._saved_name = name
            self._dirty = False
            self._name_auto = False
            self._path_auto = True
            self._set_control("save-name", name)
            self._auto_path()
            self._usage()
            self._say(f"Opened {name}")
        except (MeowTextError, OSError, ValueError) as exc:
            self._say(str(exc))

    def _open_project(self, project):
        self.font = library.project_font(project)
        self.project = project
        self.source_key = None
        self.frame = 0
        self.playing = project.animation.name != "none"
        with self.query_one("#text").prevent(Input.Changed):
            self.query_one("#text", Input).value = project.text
        with self.query_one("#notes", TextArea).prevent(TextArea.Changed):
            self.query_one("#notes", TextArea).text = project.notes
        self._name_auto = True
        self._path_auto = True
        self._auto_names()
        self._dirty = True
        self._sync_controls()
        self._render_selected()
        self._refresh_gallery()

    def _export(self):
        try:
            path = Path(self.query_one("#export-path", Input).value).expanduser()
            if path.exists():
                raise RenderError(
                    "That file exists. Enter a new path to keep both copies."
                )
            fmt = str(self.query_one("#format", Select).value)
            self._render_selected()
            if self.last_banner is None:
                raise RenderError("Nothing to export")
            if fmt == "project":
                save_project(path, self.project)
            else:
                data = export_design(self.source, self.project, fmt, self.frame)
                path.parent.mkdir(parents=True, exist_ok=True)
                (
                    path.write_bytes(data)
                    if isinstance(data, bytes)
                    else path.write_text(data, encoding="utf-8")
                )
            self._say(f"Exported {path}. " + export_notice(fmt, self.project.animation.name != "none"))
        except (MeowTextError, OSError, ValueError) as exc:
            self._say(str(exc))

    def _export_notice(self):
        fmt = str(self.query_one("#format", Select).value)
        self.query_one("#export-notice", Static).update(
            export_notice(fmt, self.project.animation.name != "none")
        )

    def _usage(self):
        mode = str(self.query_one("#use-mode", Select).value)
        raw_name = self.query_one("#save-name", Input).value.strip() or "my-banner"
        name = shlex.quote(raw_name)
        markdown_path = shlex.quote(self._suggested_name(raw_name) + ".md")
        self.query_one("#copy-command", Button).disabled = (
            self._dirty or self._saved_name != raw_name
        )
        target = self.query_one("#target-command", Input).value.strip() or "ls"
        self.query_one("#target-command").display = mode in {
            "before",
            "after",
            "frame",
            "words",
        }
        commands = {
            "show": f"meowtext show {name}",
            "watch": f"meowtext watch {name}",
            "words": f"meowtext show {name} {shlex.quote(target)}",
            "before": f"meowtext run {name} -- {target}",
            "after": f"meowtext run {name} --after -- {target}",
            "frame": f"meowtext frame {name} -- {target}",
            "zsh": f'eval "$(meowtext shell zsh --style {name})"',
            "fish": f"meowtext shell fish --style {name} | source",
            "markdown": f"meowtext show {name} --format markdown -o {markdown_path}",
        }
        help = {
            "show": "Paste this in Kitty to show your finished banner.",
            "watch": "Plays your saved animation in Kitty. Press Ctrl+C to return to your terminal.",
            "words": "Replace the words in the box. It reuses your font and effects.",
            "before": "Enter the command you normally run. Your banner appears first; the command then runs normally.",
            "after": "Your banner appears after the command finishes. The command's exit status is preserved.",
            "frame": "Opens a new Kitty window with your banner above the running tool. The tool keeps its own controls.",
            "zsh": "Paste once in a Kitty zsh terminal. Your banner appears before commands. Type meowtext-off to stop. Applies to this terminal session.",
            "fish": "Paste once in a Kitty fish terminal. Type meowtext-off to stop. Applies to this terminal session.",
            "markdown": f"Writes a Markdown code block containing your banner. View it with glow {markdown_path}. Markdown keeps the shape, not the ANSI colours.",
        }
        self.usage_command = commands[mode]
        self.query_one("#usage-command", Static).update(self.usage_command)
        self.query_one("#usage-help", Static).update(help[mode])

    def action_section(self, name):
        # A focused control in the departing pane can otherwise reactivate it.
        self.set_focus(None)
        self.query_one("#sections", TabbedContent).active = name
        if name == "adjust":
            self._tune_bank("fill", close=True)
        target = {
            "fonts": "#search",
            "presets": "#preset-next",
            "adjust": "#look-inventory",
            "save": "#save-name",
        }[name]
        self.call_after_refresh(self.query_one(target).focus)

    def action_bank(self, name):
        self.set_focus(None)
        self.query_one("#sections", TabbedContent).active = "adjust"
        self._tune_bank(name, close=True)
        self.call_after_refresh(
            self.query_one(
                {
                    "fill": "#look-inventory",
                    "outline": "#edge-inventory",
                    "motion": "#motion-inventory",
                }[name]
            ).focus
        )

    def action_fonts(self):
        self.action_section("fonts")
        self.query_one("#search", Input).focus()

    def action_words(self):
        self.query_one("#text", Input).focus()

    def action_save_tab(self):
        self.action_section("save")
        self.query_one("#save-name", Input).focus()

    def action_inspect(self):
        if isinstance(self.focused, FontCard):
            self.font_action("inspect", int(self.focused.id.rsplit("-", 1)[1]))
        elif self.last_banner:
            self.push_screen(Inspect(self.last_banner))

    def action_back(self):
        if isinstance(self.screen, ModalScreen):
            self.screen.dismiss(None)
        elif self.query_one("#sections", TabbedContent).active == "adjust" and any(
            self.query_one("#" + name + "-details").display
            for name in ("fill", "outline", "motion")
        ):
            self._tune_bank(
                next(
                    name
                    for name in ("fill", "outline", "motion")
                    if self.query_one("#" + name + "-details").display
                ),
                close=True,
            )
        elif (
            self.query_one("#sections", TabbedContent).active == "fonts"
            and self.discovery.history
        ):
            self.discovery.back()
            self._refresh_gallery()
        else:
            self.action_fonts()

    def _resize_layout(self, width=None):
        width = self.size.width if width is None else width
        self.screen.set_class(width < 105, "compact")
        self.screen.set_class(self.size.height < 30, "short")
        if self.query("#sidebar"):
            self.query_one("#sidebar").display = False
        wide = width >= 145 and self.size.height >= 37
        self.screen.set_class(wide, "wide")
        if self.discovery.count != (9 if wide else 6):
            self.discovery.resize(9 if wide else 6)
            if self.is_mounted:
                self._refresh_gallery()
        self.screen.set_class(width < 70, "narrow")
        if self.is_mounted:
            self.call_after_refresh(self._fit_tiles)

    def _fit_tiles(self):
        if not self.query("#font-scroll"):
            return
        columns = (
            3
            if self.screen.has_class("wide")
            else 1 if self.screen.has_class("narrow") else 2
        )
        rows = (self.discovery.count + columns - 1) // columns
        height = max(8, self.query_one("#font-scroll").size.height // rows)
        for i in range(9):
            self.query_one(f"#font-tile-{i}").styles.height = height
            self.query_one(f"#font-preview-{i}").styles.height = max(3, height - 5)

    def on_resize(self, event):
        if self.is_mounted:
            self.call_after_refresh(self._resize_layout, event.size.width)
