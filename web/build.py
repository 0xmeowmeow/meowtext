"""Build the static browser edition: python web/build.py (Pillow required)."""
from pathlib import Path
import dataclasses
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import zipfile
import gzip

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
DIST = WEB / "dist"
DIST.mkdir(exist_ok=True)
manifest = json.loads((WEB / "runtime-manifest.json").read_text())
runtime_name = "pyodide-" + manifest["version"]
runtime_dir = DIST / runtime_name
runtime_dir.mkdir(exist_ok=True)
for name, info in manifest["files"].items():
    path = runtime_dir / name
    old_path = DIST / "pyodide" / name
    if not path.exists() and old_path.exists() and hashlib.sha256(old_path.read_bytes()).hexdigest() == info["sha256"]:
        shutil.copy2(old_path, path)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]:
        continue
    if "--download-runtime" not in sys.argv:
        raise SystemExit("Missing or changed runtime files. Build with --download-runtime to fetch the pinned, checksum-verified release.")
    from urllib.request import urlopen
    data = urlopen(info["url"], timeout=60).read()
    if hashlib.sha256(data).hexdigest() != info["sha256"]:
        raise SystemExit(f"Runtime checksum mismatch: {name}")
    path.write_bytes(data)
with tempfile.TemporaryDirectory(prefix="meowtext-web-") as temp:
    # Use the same substantial headings as the accepted Kitty inventory. Keep
    # these source grids as a portable fallback when TOIlet is not installed.
    from meowtext.catalog import resolve
    from meowtext.compose import layout_font
    from meowtext.grid import Grid, Cell
    headings = json.loads((WEB / "lettering.json").read_text())
    with zipfile.ZipFile(WEB / "vendor/pyfiglet-1.0.4-py3-none-any.whl") as wheel:
        wheel.extractall(temp)
    sys.path.insert(0, temp)
    spec = importlib.util.spec_from_file_location("web_bridge", WEB / "bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    from meowtext.catalog import list_fonts, render, resolve
    from meowtext.discovery import describe, Specimen
    from meowtext.catalog import FontInfo
    from meowtext.compose import layout_font, present
    from meowtext.effects import Animation, BannerStyle, PRESETS, OUTLINE_MODES, ANIMATIONS
    from meowtext.export import to_png
    from meowtext.animation_export import export_design
    from meowtext.project import Project

    index = []
    for font in list_fonts("figlet"):
        try:
            item = describe(render(font, "MEOW").grid, font)
            index.append(dataclasses.asdict(item))
        except Exception as exc:
            print(f"Skipping {font.name}: {exc}")
    (DIST / "font-index.json").write_text(json.dumps(index, separators=(",", ":")))
    assets = DIST / "assets"
    assets.mkdir(exist_ok=True)
    from meowtext.grid import Grid, Cell
    sample = Grid([[Cell(c) for c in row] for row in ("█▀▀ ▀▄▀", "█▀  ▄▀▄", "▀   ▀ ▀")])
    from meowtext.raster import rasterize
    from meowtext.animation_export import timeline
    from PIL import Image
    def specimen_png(path, grid):
        rasterize(grid, background=(0,0,0,0)).save(path, format="PNG")
    for heading in ("looks", "edges", "motion", "keep"):
        letters = Grid([[Cell(c) for c in row] for row in headings[heading]])
        specimen_png(assets / f"heading-{heading}.png", present(letters, PRESETS["cyan"]))
    for name, style in PRESETS.items():
        specimen_png(assets / f"look-{name}.png", present(sample, style))
    for _, mode in (("Off", "off"), *OUTLINE_MODES):
        style = BannerStyle(gradient="ice", outline=mode != "off", outline_mode=mode)
        specimen_png(assets / f"edge-{mode}.png", present(sample, style))
    for _, name in ANIMATIONS:
        style = PRESETS["rainbow"].clone()
        style.outline, style.outline_mode, style.outline_scope = True, "contour", "letter"
        p = Project(style=style, animation=Animation(name=name))
        complete = present(sample, style)
        plan = timeline(complete, p.animation)
        pictures = [rasterize(present(sample, style, animation=p.animation, frame=i*plan.step), background=(0,0,0,0)) for i in range(plan.count)]
        pictures[0].save(assets / f"motion-{name}.png", format="PNG", save_all=True, append_images=pictures[1:], duration=plan.duration, loop=0 if plan.loop else 1, disposal=0, blend=0)
        specimen_png(assets / f"motion-{name}-still.png", complete)
    logo, _, _ = layout_font("meowtext", resolve("figlet", "ansi_shadow"))
    mark = Grid([[Cell(c) for c in row] for row in headings["logo"]])
    (assets / "logo.png").write_bytes(to_png(present(mark, PRESETS["rainbow"])))
    (assets / "startup.png").write_bytes(export_design(logo, bridge.project, "apng"))
    (assets / "startup-still.png").write_bytes(to_png(present(logo, bridge.project.style)))
    tile = present(logo, PRESETS["ice-rim"])
    from meowtext.raster import rasterize
    image = rasterize(tile)
    from PIL import Image
    from PIL import ImageDraw
    canvas = Image.new("RGB", (960, 600), (9, 16, 23))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((22, 22, 937, 296), outline=(101,232,237), width=2)
    image.thumbnail((870, 230), Image.Resampling.LANCZOS)
    canvas.paste(image, ((960 - image.width) // 2, 155 - image.height // 2))
    for tile_index, (heading, sample_file) in enumerate((("looks","look-rainbow.png"),("edges","edge-double.png"),("motion","motion-hue-still.png"))):
        left = 22 + 311*tile_index
        draw.rectangle((left,312,left+293,577), fill=(16,31,41), outline=(49,82,98), width=2)
        label = Image.open(assets / f"heading-{heading}.png").convert("RGBA")
        label.thumbnail((246,55), Image.Resampling.LANCZOS)
        canvas.paste(label, (left+(293-label.width)//2,333), label)
        swatch = Image.open(assets / sample_file).convert("RGBA")
        swatch.thumbnail((232,156), Image.Resampling.LANCZOS)
        canvas.paste(swatch, (left+(293-swatch.width)//2,390+(164-swatch.height)//2),swatch)
    canvas.save(assets / "tile.png")

    modules = ("__init__", "ansi", "animation_export", "catalog", "compose", "discovery",
               "effects", "errors", "export", "grid", "library", "packs", "palette", "project", "raster")
    items = [Specimen(FontInfo(**i["font"]), tuple(i["features"]), tuple(i["categories"])) for i in index]
    bootstrap = bridge.configuration(items)
    starter_fonts = {bridge.project.font_name, *(c["name"] for c in bootstrap["choices"])}
    bootstrap["specimens"] = {c["name"]: bridge.handle({"action":"specimen", "font":{k:c[k] for k in ("name","engine","source","index")}, "text":bridge.project.text}) for c in bootstrap["choices"]}
    # The full catalogue remains available; downloading hundreds of unselected
    # fonts must not block the first edit.
    font_files = {}
    font_dir = DIST / "fonts"
    font_dir.mkdir(exist_ok=True)
    for path in (Path(temp) / "pyfiglet/fonts").iterdir():
        if path.suffix not in {".flf", ".tlf"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        target = font_dir / f"{digest}-{path.name}"
        shutil.copy2(path, target)
        font_files[path.stem] = {"file":path.name, "url":f"fonts/{target.name}"}
    with zipfile.ZipFile(DIST / "runtime.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for module in modules:
            archive.write(ROOT / "meowtext" / f"{module}.py", f"meowtext/{module}.py")
        for path in (ROOT / "meowtext/engines").glob("*.py"):
            archive.write(path, f"meowtext/engines/{path.name}")
        for path in Path(temp).rglob("*"):
            if path.suffix in {".flf", ".tlf"} and path.stem not in starter_fonts:
                continue
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(temp))
        archive.write(WEB / "bridge.py", "bridge.py")
        archive.write(WEB / "vendor/DejaVuSansMono.ttf", "DejaVuSansMono.ttf")
        archive.write(DIST / "font-index.json", "font-index.json")

    renderer_hash = hashlib.sha256((DIST / "runtime.zip").read_bytes()).hexdigest()
    renderer_name = "renderer-" + renderer_hash[:16] + ".zip"
    (DIST / "runtime.zip").rename(DIST / renderer_name)
    files = {f"{runtime_name}/{name}":{**info, "size":(runtime_dir / name).stat().st_size,
             "label": {"pyodide.js":"Loader", "pyodide.asm.mjs":"Engine support", "pyodide.asm.wasm":"Python engine", "python_stdlib.zip":"Python library", "pyodide-lock.json":"Package index"}.get(name, "Image tools")}
             for name, info in manifest["files"].items() if "LICENSE" not in name}
    files[renderer_name] = {"sha256":renderer_hash, "size":(DIST / renderer_name).stat().st_size, "label":"Meowtext + starter fonts"}
    boot = {"runtime":runtime_name, "renderer":renderer_name, "files":files, "fonts":font_files}
    (DIST / "boot.json").write_text(json.dumps(boot, separators=(",", ":")))

    # A subset of the same licensed monospace face keeps UI metrics predictable.
    from fontTools.ttLib import TTFont
    from fontTools import subset
    font = TTFont(WEB / "vendor/DejaVuSansMono.ttf")
    options = subset.Options(); options.flavor = "woff2"
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=list(range(32, 256)) + [0x2190,0x2191,0x2192,0x2193,0x21b5,0x21b6,0x21ba,0x25b6,0x25b8,0x25c6,0x2161])
    sub.subset(font); font.flavor = "woff2"; font.save(DIST / "studio-mono.woff2")

for name in ("index.html", "app.js", "worker.js", "style.css", ".htaccess"):
    shutil.copy2(WEB / name, DIST / name)
build_id = hashlib.sha256(b"".join((WEB / name).read_bytes() for name in ("index.html", "app.js", "worker.js", "style.css")) + renderer_hash.encode()).hexdigest()[:16]
bootstrap["build"] = build_id
document = (DIST / "index.html").read_text().replace("BUILD_ID", build_id)
document = document.replace("pyodide/LICENSE", runtime_name + "/LICENSE")
document = document.replace("<!-- BOOTSTRAP -->", '<script type="application/json" id="bootstrap">' + json.dumps(bootstrap, separators=(",", ":")).replace("<", "\\u003c") + '</script>')
(DIST / "index.html").write_text(document)
# Compress once during build, not on every visit at the shared host.
for path in [*runtime_dir.glob("*.wasm"), *runtime_dir.glob("*.mjs"), *runtime_dir.glob("*.js"), *runtime_dir.glob("*.json")]:
    path.with_name(path.name + ".gz").write_bytes(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))
    import brotli
    compressed = path.with_name(path.name + ".br")
    if not compressed.exists() or compressed.stat().st_mtime < path.stat().st_mtime:
        compressed.write_bytes(brotli.compress(path.read_bytes(), quality=11))
for path in (WEB / "vendor").glob("*LICENSE.txt"):
    shutil.copy2(path, DIST / path.name)
print(f"Built {len(index)} fonts and shared renderer in {DIST}")
