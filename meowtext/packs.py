"""Palettes, symbols, presets, and favourites you add without editing the program.

They live in ``~/.config/meowtext``. The built-in sets stay in the program.
A file here adds to them, and a palette or preset with the same name is the
one the editor shows.
"""

from __future__ import annotations

import json
from pathlib import Path

from meowtext.effects import PALETTES, PRESETS, SYMBOLS, BannerStyle
from meowtext.grid import Color
from meowtext.project import Project, dumps_project, load_project, project_filename, allocate_path


def config_dir() -> Path:
    path = Path.home() / ".config" / "meowtext"
    path.mkdir(parents=True, exist_ok=True)
    return path


def font_dir() -> Path:
    path = config_dir() / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def favourite_dir() -> Path:
    path = config_dir() / "favourites"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_palettes() -> dict[str, tuple[Color, ...]]:
    found = dict(PALETTES)
    raw = _read_json(config_dir() / "palettes.json")
    if not isinstance(raw, dict):
        return found
    for name, stops in raw.items():
        colours = _colours(stops)
        if colours is not None:
            found[str(name)] = colours
    return found


def save_palette(name: str, stops: tuple[Color, ...]) -> None:
    path = config_dir() / "palettes.json"
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raw = {}
    raw[name] = [colour.hex() for colour in stops]
    _write_json(path, raw)


def load_symbols() -> tuple[tuple[str, str], ...]:
    found = list(SYMBOLS)
    seen = {value for _, value in found}
    raw = _read_json(config_dir() / "symbols.json")
    if isinstance(raw, list):
        for item in raw:
            char = str(item)[:1]
            if char and char not in seen and char != " ":
                seen.add(char)
                found.append((f"yours {char}", char))
    return tuple(found)


def save_symbol(char: str) -> None:
    char = char[:1]
    if not char or char == " ":
        return
    path = config_dir() / "symbols.json"
    raw = _read_json(path)
    if not isinstance(raw, list):
        raw = []
    if char not in raw:
        raw.append(char)
    _write_json(path, raw)


def load_presets() -> dict[str, BannerStyle]:
    found = {name: preset.clone() for name, preset in PRESETS.items()}
    raw = _read_json(config_dir() / "presets.json")
    if not isinstance(raw, dict):
        return found
    from meowtext.project import _style_from

    for name, item in raw.items():
        if isinstance(item, dict):
            found[str(name)] = _style_from(item)
    return found


def save_preset(name: str, style: BannerStyle) -> None:
    from meowtext.project import _style_to

    path = config_dir() / "presets.json"
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raw = {}
    raw[name] = _style_to(style)
    _write_json(path, raw)


def list_favourites() -> list[Path]:
    return sorted(favourite_dir().glob("*.meowtext"))


def save_favourite(project: Project) -> Path:
    filename = project_filename(project.text, project.font_name)
    path = allocate_path(favourite_dir(), filename)
    path.write_text(dumps_project(project), encoding="utf-8")
    return path


def load_favourite(path: Path) -> Project:
    return load_project(path)


def _colours(raw: object) -> tuple[Color, ...] | None:
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    stops: list[Color] = []
    for item in raw:
        try:
            stops.append(Color.from_hex(str(item)))
        except ValueError:
            return None
    return tuple(stops)


def _read_json(path: Path) -> object:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
