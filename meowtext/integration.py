"""Put saved artwork around ordinary commands without changing their streams."""

from __future__ import annotations

import shlex
import shutil
import signal
import subprocess
import sys

from meowtext.errors import RenderError
from meowtext.export import to_ansi
from meowtext.library import artwork, valid_name, load


def command_args(args: list[str]) -> list[str]:
    args = args[1:] if args and args[0] == "--" else args
    if not args:
        raise RenderError(
            "give a command after --, for example: meowtext run neon -- ls"
        )
    return args


def run(name: str, args: list[str], *, after: bool = False) -> int:
    args = command_args(args)
    banner = to_ansi(artwork(name))
    # Decoration is diagnostic output, so piping the command's data remains safe.
    if not after:
        sys.stderr.write(banner)
        sys.stderr.flush()
    try:
        child = subprocess.Popen(args)
    except FileNotFoundError as exc:
        raise RenderError(
            f"command not found: {args[0]}. Shell aliases work with shell integration; run accepts executable commands."
        ) from exc
    try:
        result = child.wait()
    except KeyboardInterrupt:
        try:
            child.send_signal(signal.SIGINT)
            result = child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                result = child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                result = child.wait()
        return 130
    if after:
        sys.stderr.write(banner)
        sys.stderr.flush()
    return result if result >= 0 else 128 - result


def kitty_session(name: str, args: list[str], *, animated: bool = False) -> str:
    valid_name(name)
    args = command_args(args)
    if any("\n" in arg or "\r" in arg for arg in args):
        raise RenderError("Kitty frame command arguments must not contain newlines")
    show = shlex.join(
        [sys.executable, "-m", "meowtext", "watch" if animated else "show", name]
    )
    command = shlex.join(args)
    return f"layout splits\nlaunch --hold --title=meowtext {show}\nlaunch --location=hsplit --bias=78 {command}\nfocus\n"


def frame(name: str, args: list[str]) -> int:
    artwork(name)
    kitty = shutil.which("kitty")
    if not kitty:
        raise RenderError(
            "Kitty is not installed; use meowtext run for an inline banner"
        )
    animated = load(name).animation.name != "none"
    result = subprocess.run(
        [kitty, "--session", "-"],
        input=kitty_session(name, args, animated=animated),
        text=True,
    )
    return result.returncode
