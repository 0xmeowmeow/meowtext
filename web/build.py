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

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
DIST = WEB / "dist"
DIST.mkdir(exist_ok=True)
manifest = json.loads((WEB / "runtime-manifest.json").read_text())
runtime_dir = DIST / "pyodide"
runtime_dir.mkdir(exist_ok=True)
for name, info in manifest["files"].items():
    path = runtime_dir / name
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
    with zipfile.ZipFile(WEB / "vendor/pyfiglet-1.0.4-py3-none-any.whl") as wheel:
        wheel.extractall(temp)
    sys.path.insert(0, temp)
    spec = importlib.util.spec_from_file_location("web_bridge", WEB / "bridge.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    from meowtext.catalog import list_fonts, render, resolve
    from meowtext.discovery import describe
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
    sample = Grid([[Cell(c) for c in row] for row in ("█▀▀ ▀▄▀", "█▀  ▄▀▄")])
    for heading in ("looks", "edges", "motion"):
        letters, _, _ = layout_font(heading.upper(), resolve("figlet", "small"))
        (assets / f"heading-{heading}.png").write_bytes(to_png(present(letters, PRESETS["cyan"])))
    for name, style in PRESETS.items():
        (assets / f"look-{name}.png").write_bytes(to_png(present(sample, style)))
    for _, mode in (("Off", "off"), *OUTLINE_MODES):
        style = BannerStyle(gradient="ice", outline=mode != "off", outline_mode=mode)
        (assets / f"edge-{mode}.png").write_bytes(to_png(present(sample, style)))
    for _, name in ANIMATIONS:
        p = Project(style=PRESETS["rainbow"].clone(), animation=Animation(name=name))
        (assets / f"motion-{name}.png").write_bytes(export_design(sample, p, "apng"))
    logo, _, _ = layout_font("meowtext", resolve("figlet", "ansi_shadow"))
    (assets / "logo.png").write_bytes(to_png(present(logo, PRESETS["cyan"])))
    tile = present(logo, PRESETS["ice-rim"])
    from meowtext.raster import rasterize
    image = rasterize(tile)
    from PIL import Image
    canvas = Image.new("RGB", (960, 600), (6, 14, 21))
    image.thumbnail((880, 420), Image.Resampling.LANCZOS)
    canvas.paste(image, ((960 - image.width) // 2, (600 - image.height) // 2))
    canvas.save(assets / "tile.png")

    modules = ("__init__", "ansi", "animation_export", "catalog", "compose", "discovery",
               "effects", "errors", "export", "grid", "library", "packs", "palette", "project", "raster")
    with zipfile.ZipFile(DIST / "runtime.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for module in modules:
            archive.write(ROOT / "meowtext" / f"{module}.py", f"meowtext/{module}.py")
        for path in (ROOT / "meowtext/engines").glob("*.py"):
            archive.write(path, f"meowtext/engines/{path.name}")
        for path in Path(temp).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(temp))
        archive.write(WEB / "bridge.py", "bridge.py")
        archive.write(WEB / "vendor/DejaVuSansMono.ttf", "DejaVuSansMono.ttf")
        archive.write(DIST / "font-index.json", "font-index.json")

for name in ("index.html", "app.js", "worker.js", "style.css", ".htaccess"):
    shutil.copy2(WEB / name, DIST / name)
for path in (WEB / "vendor").glob("*LICENSE.txt"):
    shutil.copy2(path, DIST / path.name)
print(f"Built {len(index)} fonts and shared renderer in {DIST}")
