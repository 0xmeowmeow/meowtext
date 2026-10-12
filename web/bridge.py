"""Browser adapter. Compositing, rasterisation, discovery and exports stay shared."""
import base64
import json
import math
from pathlib import Path

import pyfiglet
from meowtext import catalog, raster
from meowtext.ansi import fit_width, parse_ansi
from meowtext.catalog import FontInfo
from meowtext.compose import layout_font, present
from meowtext.discovery import Discovery, Specimen, describe
from meowtext.effects import Animation, BannerStyle, PRESETS, OUTLINE_MODES, ANIMATIONS, PALETTES, TRACE_PATTERNS, SHADOW_STYLES
from meowtext.errors import RenderError
from meowtext.export import to_png, FORMAT_LABELS, export_notice
from meowtext.animation_export import export_design
from meowtext.project import Project, dumps_project, project_from_dict, _style_to
from meowtext.library import prepare_roles


def browser_figlet(text, name):
    return fit_width(parse_ansi(pyfiglet.Figlet(font=name, width=10000, justify="left").renderText(text)))


def configure():
    catalog.figlet.render = browser_figlet
    catalog.toilet.render = browser_figlet
    catalog.figlet.available = lambda: True
    catalog.toilet.available = lambda: True
    # Relative sources survive both the build directory and /app in Pyodide.
    catalog.figlet.font_index = lambda: {p.stem: p for p in Path("pyfiglet/fonts").glob("*.flf")}
    catalog.toilet.font_index = lambda: {p.stem: p for p in Path("pyfiglet/fonts").glob("*.tlf")}
    catalog._TDF = [FontInfo("tdf", h.name, str(p), h.index, h.kind)
                    for p in sorted(Path("fonts/builtin").glob("*.TDF"))
                    for h in catalog.tdf_engine.peek_file(p)]


configure()
project = Project(text="meowtext", font_name="ansi_shadow", style=PRESETS["cyan"].clone(), animation=Animation(name="hue"))
source = None
source_key = None
palette = None
discovery = None


def use_font_index():
    """Font discovery covers the catalogue; files are fetched only when used."""
    raw = json.loads(Path("/app/font-index.json").read_text())
    fonts = [FontInfo(**i["font"]) for i in raw]
    catalog.figlet.font_index = lambda: {f.name: Path(f.source) for f in fonts if f.engine == "figlet"}
    catalog.toilet.font_index = lambda: {f.name: Path(f.source) for f in fonts if f.engine == "toilet"}
    catalog._TDF = [f for f in fonts if f.engine == "tdf"]


def configuration(items):
    global discovery
    discovery = Discovery(items)
    default = next(i for i in items if i.font.engine == project.engine and i.font.name == project.font_name)
    # The public collections include both "ANSI Shadow" and "ansi_shadow".
    # Keep the actual default selected in the opening comparison.
    discovery.choices[0] = default
    return {"project": json.loads(dumps_project(project)), "choices": choice_data(),
            "fonts": len(items), "engines": {key: sum(i.font.engine == key for i in items) for key in ("figlet", "toilet", "tdf")},
            "looks": {k: _style_to(v) for k, v in PRESETS.items()},
            "edges": OUTLINE_MODES, "motions": ANIMATIONS, "tracePatterns": TRACE_PATTERNS,
            "shadows": {key: {"label": label, "style": {name: value.hex() if hasattr(value, "hex") else value
                                                       for name, value in style.items()}}
                        for key, (label, style) in SHADOW_STYLES.items()},
            "palettes": list(PALETTES), "formats": FORMAT_LABELS,
            "notices": {fmt: [export_notice(fmt, False), export_notice(fmt, True)] for fmt in FORMAT_LABELS}}


def encode(grid):
    return "data:image/png;base64," + base64.b64encode(to_png(grid)).decode("ascii")


def resolve_font(font):
    if font.engine == "tdf" and font.source:
        exact = next((f for f in catalog._TDF if f.source == font.source and f.index == font.index), None)
        if exact:
            return exact
        if font.source.startswith("/app/fonts/"):
            raise RenderError("Import the original .tdf file for this project: " + Path(font.source).name)
        portable = next((f for f in catalog._TDF if Path(f.source).name.casefold() == Path(font.source).name.casefold() and f.index == font.index), None)
        if portable:
            return portable
    return catalog.resolve(font.engine, font.name)


def current_source():
    global source, source_key, palette
    key = (project.engine, project.font_name, project.font_source, project.font_index, project.text,
           json.dumps(json.loads(dumps_project(project))["letters"], sort_keys=True),
           project.role_splits, project.style.outline_scope, project.animation.name == "trace")
    if source is None or key != source_key:
        # Source identity must agree for rendering and similarity exploration.
        font = resolve_font(FontInfo(project.engine, project.font_name, project.font_source, project.font_index))
        source, missing, folded = layout_font(project.text, font, project.letters or None)
        if source.width * source.height > 20000:
            raise RenderError("This artwork is too large for the browser. Shorten the text or choose a smaller font.")
        if missing:
            raise RenderError("This font is missing: " + " ".join(missing))
        if (project.animation.name == "trace" or project.style.outline_scope == "letter") and not source.spans:
            source.spans = catalog.measure_spans(font, project.text)
        # Split roles on fresh source cells only; replaying splits changes IDs.
        palette = prepare_roles(source, project)
        project.roles = {slot: role.clone() for slot, role in palette.roles.items()}
        source_key = key
    else:
        palette.hue = project.hue
        palette.roles.update(project.roles)
    return source


def render(number=0):
    return present(current_source(), project.style, palette, animation=project.animation,
                   frame=number, patches=project.patches)


def choice_data(browse=False):
    items = discovery.scope if browse else discovery.choices
    return [{"name": i.font.name, "engine": i.font.engine, "source": i.font.source,
             "index": i.font.index, "description": i.description,
             "wildcard": i.font.id in discovery.explorers and not browse}
            for i in items]


def handle(message):
    global project, discovery, source_key, source
    action = message["action"]
    if action == "init":
        raw = json.loads(Path("/app/font-index.json").read_text())
        items = [Specimen(FontInfo(**i["font"]), tuple(i["features"]), tuple(i["categories"])) for i in raw]
        return configuration(items)
    if action == "set":
        candidate = project_from_dict(message["project"])
        # Early web releases labelled the bundled TOIlet fonts as FIGlet.
        if candidate.engine == "figlet" and candidate.font_name not in catalog.figlet.font_index() and candidate.font_name in catalog.toilet.font_index():
            candidate.engine = "toilet"
        for label, value, low, high in (
            ("Motion speed", candidate.animation.speed, .05, 10),
            ("Border speed", candidate.style.outline_speed, .05, 10),
            ("Border distance", candidate.style.outline_distance, 0, 8),
            *((name, getattr(candidate.style, name), -30, 30) for name in ("outline_dx", "outline_dy", "shadow_dx", "shadow_dy")),
        ):
            if not math.isfinite(value) or not low <= value <= high:
                raise RenderError(f"{label} must be between {low} and {high} in the browser.")
        old = project
        project = candidate
        try:
            grid = render(message.get("frame", 0))
        except Exception:
            project = old
            source_key = None
            source = None
            raise
        return {"image": encode(grid), "width": grid.width, "height": grid.height,
                "project": json.loads(dumps_project(project))}
    if action == "frame":
        return {"image": encode(render(message.get("frame", 0)))}
    if action == "compare":
        mode = message.get("mode", "reset")
        if mode == "reset":
            engine = message.get("engine", "")
            discovery.reset(query=" ".join(filter(None, (message.get("query", ""), engine))))
        elif mode == "more":
            discovery.more()
        elif mode == "back":
            discovery.back()
        elif mode == "narrow":
            if message.get("font"):
                font = resolve_font(FontInfo(**message["font"]))
                selected = next((i for i in discovery.all if i.font.id == font.id), None)
                if selected is None:
                    raise RenderError("Select a font before following its neighbours.")
                discovery.narrow(selected)
            else:
                discovery.narrow(message["index"])
        return {"choices": choice_data(message.get("browse", False)), "total": len(discovery.scope)}
    if action == "specimen":
        font = FontInfo(**message["font"])
        grid, missing, _ = layout_font(message.get("text") or "Meow", font)
        if missing:
            raise RenderError("Missing glyphs: " + " ".join(missing))
        from io import BytesIO
        output = BytesIO()
        # Show the authored ANSI colours in the catalogue.
        raster.rasterize(present(grid, PRESETS["plain"] if font.engine == "tdf" else PRESETS["cyan"]), background=(0,0,0,0)).save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    if action == "export":
        fmt = message["format"]
        def progress(done, total):
            try:
                from js import postMessage, JSON
            except ImportError:
                return
            postMessage(JSON.parse(json.dumps({"exportProgress":{"done":done, "total":total}})))
        data = dumps_project(project) if fmt == "project" else export_design(current_source(), project, fmt, message.get("frame", 0), palette, progress=progress)
        if isinstance(data, str):
            data = data.encode("utf-8")
        return {"data": base64.b64encode(data).decode("ascii"), "notice": export_notice(fmt, project.animation.name != "none")}
    if action == "notice":
        return export_notice(message["format"], project.animation.name != "none")
    if action == "font":
        filename = Path(message["name"]).name
        if not filename.lower().endswith(".tdf"):
            raise RenderError("Import a TheDraw .tdf font file.")
        from meowtext.engines import tdf
        path = Path("/app/fonts") / filename
        path.parent.mkdir(exist_ok=True)
        data = base64.b64decode(message["data"])
        if len(data) > 2_000_000:
            raise RenderError("Font files must be smaller than 2 MB.")
        path.write_bytes(data)
        fonts = tdf.load_file(path)
        catalog._PARSED.pop(str(path), None)
        catalog._TDF = [f for f in catalog._TDF if f.source != str(path)]
        discovery.all = [i for i in discovery.all if i.font.source != str(path)]
        imported = []
        for n, f in enumerate(fonts):
            info = FontInfo("tdf", f.name, str(path), n, f.kind)
            catalog._TDF.append(info)
            try:
                item = describe(catalog.render(info, "MEOW").grid, info)
                discovery.all.append(item)
                imported.append(item)
            except RenderError:
                pass
        discovery.reset(query=fonts[0].name)
        if imported:
            # A same-shaped bundled face must not hide the newly imported file.
            discovery.narrow(imported[0])
        return {"choices": choice_data(), "name": fonts[0].name, "fonts": len(discovery.all),
                "engines": {key: sum(i.font.engine == key for i in discovery.all) for key in ("figlet", "toilet", "tdf")}}
    raise RenderError("Unknown browser action")


def dispatch(raw):
    return json.dumps(handle(json.loads(raw)), ensure_ascii=False)
