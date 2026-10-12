"""A meowtext project is the banner you can open again.

The painted exports (ANSI, PNG, and the rest) are a picture. A project is
the picture's recipe: the words, the font, both gradients, the outline, the
shadow, the colour roles, the animation, notes, and any cells or letters
you edited. Saving never replaces a file that is already there.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from meowtext.effects import Animation, BannerStyle
from meowtext.errors import RenderError
from meowtext.grid import Cell, Color, Grid
from meowtext.palette import RelationPalette, Role, rgb_to_hsv

PROJECT_VERSION = 1


@dataclass(slots=True)
class Project:
    text: str = "meow"
    engine: str = "figlet"
    font_name: str = ""
    font_source: str = ""
    font_index: int = 0
    style: BannerStyle = field(default_factory=BannerStyle)
    hue: float = 0.0
    roles: dict[int, Role] = field(default_factory=dict)
    animation: Animation = field(default_factory=Animation)
    notes: str = ""
    patches: tuple[tuple[int, int, Cell], ...] = ()
    letters: dict[str, Grid] = field(default_factory=dict)
    role_splits: tuple[int, ...] = ()


def project_filename(text: str, font_name: str) -> str:
    """A file name taken from the words and the font."""

    words = _slug(text) or "banner"
    font = _slug(font_name) or "font"
    return f"{words}-{font}.meowtext"


def allocate_path(directory: Path, filename: str, owned: Path | None = None) -> Path:
    """The next free path. ``owned`` is this session's file and may be rewritten."""

    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if owned is not None and owned.name == filename:
        return owned
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    number = 2
    while True:
        nxt = directory / f"{stem}-{number}{suffix}"
        if owned is not None and owned == nxt:
            return owned
        if not nxt.exists():
            return nxt
        number += 1


def save_project(path: Path, project: Project) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_project(project), encoding="utf-8")


def load_project(path: Path) -> Project:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"could not read {path.name}") from exc
    return project_from_dict(document, path.name)


def project_from_dict(document: object, name: str = "project") -> Project:
    if not isinstance(document, dict) or document.get("meowtext") != "project":
        raise RenderError(f"{name} is not a meowtext project")
    version = document.get("version")
    if version != PROJECT_VERSION:
        raise RenderError(f"unsupported meowtext project version: {version!r}")
    style = _style_from(document.get("style") or {})
    animation = _animation_from(document.get("animation") or {})
    return Project(
        text=str(document.get("text") or ""),
        engine=str(document.get("engine") or "figlet"),
        font_name=str(document.get("font_name") or ""),
        font_source=str(document.get("font_source") or ""),
        font_index=int(document.get("font_index") or 0),
        style=style,
        hue=float(document.get("hue") or 0),
        roles=_roles_from(document.get("roles") or {}),
        animation=animation,
        notes=str(document.get("notes") or ""),
        patches=_patches_from(document.get("patches") or []),
        letters=_letters_from(document.get("letters") or {}),
        role_splits=tuple(int(slot) for slot in document.get("role_splits") or ()),
    )


def dumps_project(project: Project) -> str:
    document = {
        "meowtext": "project",
        "version": PROJECT_VERSION,
        "text": project.text,
        "engine": project.engine,
        "font_name": project.font_name,
        "font_source": project.font_source,
        "font_index": project.font_index,
        "style": _style_to(project.style),
        "hue": project.hue,
        "roles": {str(slot): _role_to(role) for slot, role in sorted(project.roles.items())},
        "animation": {
            "name": project.animation.name,
            "speed": project.animation.speed,
            "direction": project.animation.direction,
            "travel": project.animation.travel,
            "layers": project.animation.layers,
            "pattern": project.animation.pattern,
            "reveal": project.animation.reveal,
        },
        "notes": project.notes,
        "patches": [_patch_to(x, y, cell) for x, y, cell in project.patches],
        "letters": {char: _grid_to(grid) for char, grid in project.letters.items()},
        "role_splits": list(project.role_splits),
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned[:40]


def _style_to(style: BannerStyle) -> dict:
    payload = {
        "gradient": style.gradient,
        "direction": style.direction,
        "stops": _colours(style.stops),
        "bands": style.bands,
        "outline": style.outline,
        "outline_char": style.outline_char,
        "outline_color": style.outline_color.hex(),
        "outline_mode": style.outline_mode,
        "outline_gradient": style.outline_gradient,
        "outline_stops": _colours(style.outline_stops),
        "outline_direction": style.outline_direction,
        "outline_speed": style.outline_speed,
        "outline_bands": style.outline_bands,
        "outline_sides": style.outline_sides,
        "outline_distance": style.outline_distance,
        "outline_place": style.outline_place,
        "outline_scope": style.outline_scope,
        "outline_dx": style.outline_dx,
        "outline_dy": style.outline_dy,
        "shadow": style.shadow,
        "shadow_dx": style.shadow_dx,
        "shadow_dy": style.shadow_dy,
        "shadow_color": style.shadow_color.hex(),
        "shadow_char": style.shadow_char,
        "hue": style.hue,
        "recolour_roles": style.recolour_roles,
        "readable_gradients": style.readable_gradients,
    }
    return payload


def _style_from(raw: dict) -> BannerStyle:
    style = BannerStyle()
    if not isinstance(raw, dict):
        return style
    style.gradient = raw.get("gradient") or None
    style.direction = str(raw.get("direction") or "horizontal")
    style.stops = _colours_from(raw.get("stops"))
    style.bands = bool(raw.get("bands"))
    style.outline = bool(raw.get("outline"))
    style.outline_char = str(raw.get("outline_char") or "░")[:1]
    style.outline_color = _colour(raw.get("outline_color"), style.outline_color)
    style.outline_mode = str(raw.get("outline_mode") or "shade")
    style.outline_gradient = raw.get("outline_gradient") or None
    style.outline_stops = _colours_from(raw.get("outline_stops"))
    style.outline_direction = str(raw.get("outline_direction") or "horizontal")
    style.outline_speed = float(raw.get("outline_speed") or 1)
    style.outline_bands = bool(raw.get("outline_bands"))
    style.outline_sides = str(raw.get("outline_sides") or "tblr")
    style.outline_distance = int(raw.get("outline_distance") or 0)
    style.outline_place = str(raw.get("outline_place") or "both")
    style.outline_scope = str(raw.get("outline_scope") or "word")
    style.outline_dx = int(raw.get("outline_dx") or 0)
    style.outline_dy = int(raw.get("outline_dy") or 0)
    style.shadow = bool(raw.get("shadow"))
    style.shadow_dx = int(raw.get("shadow_dx") or 0)
    style.shadow_dy = int(raw.get("shadow_dy") or 0)
    style.shadow_color = _colour(raw.get("shadow_color"), style.shadow_color)
    shadow_char = raw.get("shadow_char")
    style.shadow_char = None if not shadow_char else str(shadow_char)[:1]
    style.hue = float(raw.get("hue") or 0)
    style.recolour_roles = bool(raw.get("recolour_roles", False))
    style.readable_gradients = bool(raw.get("readable_gradients", True))
    return style


def _animation_from(raw: dict) -> Animation:
    motion = Animation()
    if not isinstance(raw, dict):
        return motion
    motion.name = str(raw.get("name") or "none")
    motion.speed = float(raw.get("speed") or 1)
    motion.direction = str(raw.get("direction") or "forward")
    motion.travel = int(raw.get("travel") or 360)
    motion.layers = str(raw.get("layers") or "all")
    motion.pattern = str(raw.get("pattern") or "outline")
    motion.reveal = str(raw.get("reveal") or "draw")
    return motion


def _role_to(role: Role) -> dict:
    payload: dict[str, str | float | bool] = {
        "base": role.base.hex(),
        "name": role.name,
        "linked": role.linked,
    }
    if not role.linked:
        payload["h"] = role.hue
        payload["s"] = role.sat
        payload["v"] = role.val
    return payload


def _roles_from(raw: dict) -> dict[int, Role]:
    roles: dict[int, Role] = {}
    if not isinstance(raw, dict):
        return roles
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        base = _colour(item.get("base"), Color(255, 255, 255))
        hue, sat, val = rgb_to_hsv(base)
        roles[int(key)] = Role(
            base,
            str(item.get("name") or key),
            bool(item.get("linked", True)),
            float(item.get("h", hue)),
            float(item.get("s", sat)),
            float(item.get("v", val)),
        )
    return roles


def _patch_to(x: int, y: int, cell: Cell) -> dict:
    item: dict[str, str | int] = {"x": x, "y": y, "c": cell.char or " "}
    if cell.fg is not None:
        item["fg"] = cell.fg.hex()
    if cell.bg is not None:
        item["bg"] = cell.bg.hex()
    return item


def _patches_from(raw: list) -> tuple[tuple[int, int, Cell], ...]:
    patches: list[tuple[int, int, Cell]] = []
    if not isinstance(raw, list):
        return ()
    for item in raw:
        if not isinstance(item, dict):
            continue
        fg = Color.from_hex(item["fg"]) if item.get("fg") else None
        bg = Color.from_hex(item["bg"]) if item.get("bg") else None
        patches.append((int(item.get("x") or 0), int(item.get("y") or 0), Cell(str(item.get("c") or " "), fg, bg)))
    return tuple(patches)


def _grid_to(grid: Grid) -> list[list[dict[str, str]]]:
    rows = []
    for row in grid.rows:
        encoded = []
        for cell in row:
            item: dict[str, str] = {"c": cell.char or " "}
            if cell.fg is not None:
                item["fg"] = cell.fg.hex()
            if cell.bg is not None:
                item["bg"] = cell.bg.hex()
            encoded.append(item)
        rows.append(encoded)
    return rows


def _letters_from(raw: dict) -> dict[str, Grid]:
    letters: dict[str, Grid] = {}
    if not isinstance(raw, dict):
        return letters
    for char, rows in raw.items():
        if not isinstance(rows, list):
            continue
        grid_rows: list[list[Cell]] = []
        for row in rows:
            cells: list[Cell] = []
            for item in row:
                if not isinstance(item, dict):
                    cells.append(Cell())
                    continue
                fg = Color.from_hex(item["fg"]) if item.get("fg") else None
                bg = Color.from_hex(item["bg"]) if item.get("bg") else None
                cells.append(Cell(str(item.get("c") or " "), fg, bg))
            grid_rows.append(cells)
        grid = Grid(grid_rows)
        grid.normalize()
        letters[str(char)] = grid
    return letters


def _colours(stops: tuple[Color, ...] | None) -> list[str] | None:
    if not stops:
        return None
    return [colour.hex() for colour in stops]


def _colours_from(raw: object) -> tuple[Color, ...] | None:
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    return tuple(_colour(item, Color(0, 0, 0)) for item in raw)


def _colour(raw: object, default: Color) -> Color:
    if not isinstance(raw, str):
        return default
    try:
        return Color.from_hex(raw)
    except ValueError:
        return default


def roles_from_palette(palette: RelationPalette) -> dict[int, Role]:
    return {slot: role.clone() for slot, role in palette.roles.items()}
