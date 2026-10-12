"""Named, editable styles with frozen artwork for instant shell use."""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

from meowtext.catalog import list_fonts, measure_spans, resolve
from meowtext.compose import Banner, layout_font, present
from meowtext.discovery import font_key
from meowtext.errors import RenderError
from meowtext.export import to_ansi, to_json, grid_from_json
from meowtext.grid import Grid
from meowtext.packs import config_dir
from meowtext.palette import RelationPalette
from meowtext.project import Project, dumps_project, load_project


def valid_name(name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
        raise RenderError("use a name of 1–64 letters, numbers, hyphens or underscores")
    return name


def library_dir() -> Path:
    return config_dir() / "library"


def _atomic(path: Path, data: str, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            temporary.replace(path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def project_font(project: Project):
    fonts = list_fonts(project.engine)
    # Exact source first; filename/name/index also works after moving machines.
    for font in fonts:
        if font.source == project.font_source and font.index == project.font_index:
            return font
    portable = [
        font
        for font in fonts
        if Path(font.source).name == Path(project.font_source).name
        and font.index == project.font_index
        and font.name == project.font_name
    ]
    if len(portable) == 1:
        return portable[0]
    return resolve(project.engine, project.font_name)


def render_project(project: Project, text: str | None = None, frame: int = 0) -> Banner:
    project = copy.deepcopy(project)
    font = project_font(project)
    words = project.text if text is None else text
    source, missing, folded = layout_font(words, font, project.letters or None)
    if (
        (project.animation.name == "trace"
         or (project.style.outline and project.style.outline_scope == "letter"))
        and not source.spans
    ):
        source.spans = measure_spans(font, words)
    palette = prepare_roles(source, project)
    # Cell coordinates describe the saved artwork, not a different string.
    grid = present(
        source,
        project.style,
        palette,
        animation=project.animation,
        frame=frame,
        patches=project.patches if text is None else (),
    )
    return Banner(grid, font, missing, folded)


def prepare_roles(source: Grid, project: Project) -> RelationPalette:
    """Replay the original role-splitting engine before restoring edited colours."""
    palette = RelationPalette(
        hue=project.hue,
        roles={slot: role.clone() for slot, role in project.roles.items() if slot < 16},
    )
    palette.ensure(source)
    for slot in project.role_splits:
        palette.split(source, slot)
    palette.roles.update({slot: role.clone() for slot, role in project.roles.items()})
    return palette


def save(
    name: str, project: Project, *, grid: Grid | None = None, replace: bool = False
) -> Path:
    """One atomic bundle; replacement is explicit. Shell cache is disposable."""
    name = valid_name(name)
    root = library_dir()
    root.mkdir(parents=True, exist_ok=True)
    bundle = root / f"{name}.json"
    if bundle.exists() and not replace:
        raise RenderError(
            f"{name!r} already exists; choose another name or use --replace"
        )
    grid = grid if grid is not None else render_project(project).grid
    payload = (
        json.dumps(
            {
                "library_version": 1,
                "project": json.loads(dumps_project(project)),
                "artwork": json.loads(to_json(grid)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    # A new save must never race into replacing another user's creation.
    if not replace:
        try:
            _atomic(bundle, payload, replace=False)
        except FileExistsError as exc:
            raise RenderError(f"{name!r} already exists") from exc
    else:
        _atomic(bundle, payload)
    _atomic(root / f"{name}.ans", to_ansi(grid))
    return bundle


def entries() -> list[str]:
    root = library_dir()
    return sorted(p.stem for p in root.glob("*.json") if p.is_file())


def _bundle(name: str) -> dict:
    path = library_dir() / f"{valid_name(name)}.json"
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or raw.get("library_version") != 1:
            raise ValueError("unsupported library version")
        return raw
    except (OSError, ValueError) as exc:
        raise RenderError(f"could not open saved style {name!r}: {exc}") from exc


def load(name: str) -> Project:
    from meowtext.project import project_from_dict

    raw = _bundle(name)
    return project_from_dict(raw.get("project"), name)


def artwork(name: str) -> Grid:
    try:
        return grid_from_json(_bundle(name)["artwork"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderError(f"invalid saved artwork {name!r}") from exc


def favourites() -> set[str]:
    path = config_dir() / "font-favourites.json"
    try:
        data = json.loads(path.read_text())
        return (
            set(data)
            if isinstance(data, list) and all(isinstance(v, str) for v in data)
            else set()
        )
    except (OSError, ValueError):
        return set()


def toggle_favourite(font) -> bool:
    saved = favourites()
    key = font_key(font)
    enabled = key not in saved
    saved.add(key) if enabled else saved.remove(key)
    _atomic(
        config_dir() / "font-favourites.json",
        json.dumps(sorted(saved), indent=2) + "\n",
    )
    return enabled


def bindings() -> dict[str, str]:
    try:
        data = json.loads((config_dir() / "command-banners.json").read_text())
        if isinstance(data, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            return data
    except (OSError, ValueError):
        pass
    return {}


def bind(command: str, name: str | None) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.+-]{0,63}", command):
        raise RenderError("bind a command or alias name, without arguments")
    saved = bindings()
    if name is None:
        saved.pop(command, None)
    else:
        _bundle(name)
        saved[command] = valid_name(name)
    _atomic(config_dir() / "command-banners.json", json.dumps(saved, indent=2) + "\n")


def shell_script(shell: str, default: str | None = None) -> str:
    """Render once, then let the shell cat a file. Never evaluate command text."""
    if shell not in {"zsh", "fish"}:
        raise RenderError("automatic command banners support zsh and fish")
    mappings = bindings()
    names = set(mappings.values())
    if default:
        names.add(valid_name(default))
    for name in names:
        _atomic(library_dir() / f"{name}.ans", to_ansi(artwork(name)))
    paths = {
        key: str(library_dir() / f"{value}.ans") for key, value in mappings.items()
    }
    fallback = str(library_dir() / f"{default}.ans") if default else ""
    if shell == "zsh":
        cases = "\n".join(
            f"    {shlex.quote(key)}) banner={shlex.quote(path)} ;;"
            for key, path in paths.items()
        )
        return f"""# Generated by meowtext. Only this shell session is changed.
autoload -Uz add-zsh-hook
_meowtext_preexec() {{
  emulate -L zsh
  [[ -n "$KITTY_WINDOW_ID" && -t 1 ]] || return 0
  local -a words
  words=("${{(@z)1}}")
  local banner={shlex.quote(fallback)}
  case "${{words[1]}}" in
{cases}
  esac
  [[ -n "$banner" && -r "$banner" ]] && command cat -- "$banner"
  return 0
}}
meowtext-off() {{ add-zsh-hook -d preexec _meowtext_preexec; }}
add-zsh-hook -d preexec _meowtext_preexec
add-zsh-hook preexec _meowtext_preexec
"""
    quote = lambda s: "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"
    cases = "\n".join(
        f"    case {quote(key)}\n      set banner {quote(path)}"
        for key, path in paths.items()
    )
    return f"""# Generated by meowtext. Only this shell session is changed.
functions -e _meowtext_preexec
function _meowtext_preexec --on-event fish_preexec
  set -q KITTY_WINDOW_ID; or return 0
  isatty stdout; or return 0
  set -l words (string split ' ' -- (string trim -- "$argv[1]"))
  set -l banner {quote(fallback)}
  switch "$words[1]"
{cases}
  end
  if test -n "$banner"; and test -r "$banner"
    command cat -- "$banner"
  end
end
function meowtext-off
  functions -e _meowtext_preexec
end
"""
