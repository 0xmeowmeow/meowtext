"""Shared helpers for the figlet and toilet programs."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from meowtext.errors import RenderError

_FONT_DIR: Path | None = None


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def font_directory() -> Path:
    """Directory figlet and toilet read ``.flf`` and ``.tlf`` fonts from."""

    global _FONT_DIR
    if _FONT_DIR is not None:
        return _FONT_DIR
    env = os.environ.get("FIGLET_FONTDIR")
    if env and Path(env).is_dir():
        _FONT_DIR = Path(env)
        return _FONT_DIR
    if tool_available("figlet"):
        try:
            out = subprocess.check_output(
                ["figlet", "-I2"], text=True, timeout=2, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.SubprocessError):
            out = ""
        if out and Path(out).is_dir():
            _FONT_DIR = Path(out)
            return _FONT_DIR
    for candidate in (Path("/usr/share/figlet"), Path("/usr/local/share/figlet")):
        if candidate.is_dir():
            _FONT_DIR = candidate
            return _FONT_DIR
    _FONT_DIR = Path("/usr/share/figlet")
    return _FONT_DIR


def run_tool(command: list[str], text: str) -> str:
    """Run a banner program. ``text`` is stdin so a leading dash is not a flag."""

    env = dict(os.environ)
    env["LC_ALL"] = "C.UTF-8"
    try:
        proc = subprocess.run(
            command,
            input=text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=8,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RenderError(f"{command[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"{command[0]} took too long") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RenderError(detail or f"{command[0]} failed ({proc.returncode})")
    return proc.stdout
