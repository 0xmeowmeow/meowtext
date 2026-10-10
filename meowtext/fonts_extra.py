"""Download FIGlet and TOIlet fonts that are not already on this machine.

The system font directory is left untouched. New files go in
``~/.config/meowtext/fonts``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from meowtext.errors import RenderError
from meowtext.packs import font_dir

_REPO = "https://github.com/cmatsuoka/figlet-fonts.git"
_FOLDERS = (
    "jave",
    "international",
    "contributed",
    "tlf-contrib",
    "toilet",
    "ms-dos",
    "C64-fonts",
    "Obanner",
    "Obanner-canon",
    "bdffonts",
    "cjkfonts",
)


def fetch_extra_fonts() -> int:
    """Copy fonts the system does not already have. Returns how many were added."""

    if shutil.which("git") is None:
        raise RenderError("git is not installed, so the extra fonts cannot be fetched")
    cache = Path.home() / ".cache" / "meowtext" / "figlet-fonts"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not (cache / ".git").is_dir():
        _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", _REPO, str(cache)])
    _run(["git", "-C", str(cache), "sparse-checkout", "set", *_FOLDERS])
    system = _system_names()
    dest = font_dir()
    seen = set(system)
    added = 0
    for folder in _FOLDERS:
        directory = cache / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".flf", ".tlf"}:
                continue
            key = path.stem.lower()
            if key in seen:
                continue
            seen.add(key)
            shutil.copy2(path, dest / path.name)
            control = path.with_suffix(".flc")
            if control.is_file():
                shutil.copy2(control, dest / control.name)
            added += 1
    from meowtext.engines import figlet, toilet

    figlet._index = None
    toilet._index = None
    return added


def _system_names() -> set[str]:
    from meowtext.engines.external import font_directory

    directory = font_directory()
    if not directory.is_dir():
        return set()
    return {
        path.stem.lower()
        for path in directory.iterdir()
        if path.suffix.lower() in {".flf", ".tlf"}
    }


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RenderError(detail or "could not fetch the extra fonts") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError("fetching the extra fonts took too long") from exc
