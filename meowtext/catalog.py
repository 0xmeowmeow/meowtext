"""Find fonts and draw one of them into a grid, before effects."""

from __future__ import annotations

import json
import os
import re
import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path

from meowtext.engines import figlet, toilet
from meowtext.engines import tdf as tdf_engine
from meowtext.errors import RenderError
from meowtext.grid import Grid

_ALIASES = {"thedraw": "tdf", "thedrawfonts": "tdf", "tdfiglet": "tdf"}
_LOCK = threading.Lock()
_PARSED_LOCK = threading.Lock()
_TDF: list[FontInfo] | None = None
_PARSED: OrderedDict[str, list[tdf_engine.TdfFont]] = OrderedDict()


@dataclass(frozen=True, slots=True)
class FontInfo:
    engine: str
    name: str
    source: str
    index: int = 0
    kind: str = ""

    @property
    def id(self) -> str:
        return f"{self.engine}\x1f{self.source}\x1f{self.index}"

    def label(self) -> str:
        if self.engine == "tdf":
            stem = Path(self.source).stem
            text = f"{self.name} · {self.kind}" if stem.lower() == self.name.lower() else f"{self.name} · {stem}"
        else:
            text = self.name
        if len(text) > 42:
            return text[:41] + "…"
        return text


@dataclass(slots=True)
class EngineOutput:
    grid: Grid
    missing: tuple[str, ...] = ()
    folded: bool = False


def canonical(engine: str) -> str:
    key = engine.strip().lower()
    key = _ALIASES.get(key, key)
    if key not in {"figlet", "toilet", "tdf"}:
        raise RenderError("engine must be figlet, toilet, or tdf")
    return key


def list_fonts(engine: str) -> list[FontInfo]:
    key = canonical(engine)
    if key == "figlet":
        return [
            FontInfo("figlet", name, str(path), 0, "flf")
            for name, path in sorted(figlet.font_index().items())
        ]
    if key == "toilet":
        return [
            FontInfo("toilet", name, str(path), 0, "tlf")
            for name, path in sorted(toilet.font_index().items())
        ]
    return load_tdf()


@dataclass(frozen=True, slots=True)
class FontFamily:
    """One row in the font list. Colour copies of a TheDraw font share a row."""

    key: str
    kind: str
    stem: str
    members: tuple[FontInfo, ...]

    def label(self) -> str:
        if len(self.members) == 1:
            text = self.members[0].label()
        else:
            text = f"{self.stem} · {len(self.members)} colours"
        if len(text) > 42:
            return text[:41] + "…"
        return text


_COLOUR_WORD = (
    "blue|blu|brown|brow|brn|cyan|cya|cyn|green|grn|gray|grey|gra|"
    "gold|gld|purple|purp|pur|red|yellow|yel|white|wht|black|blk|"
    "pink|orange|org|magenta|margen|marge|marg"
)
_COLOUR_SUFFIX = re.compile(
    rf"(?ix)(?:[\s_\-]+|(?<=[a-z])(?=[A-Z]))"
    rf"(?:(?:dk|drk|dark|lt|light|d)(?=[A-Za-z]))?"
    rf"(?:{_COLOUR_WORD})$"
)
_KIND_ORDER = {"block": 0, "outline": 1, "color": 2}


def colour_stem(name: str) -> str | None:
    """The shared name of a colour copy, such as ``Nuclear`` from ``Nuclear Blue``."""

    match = _COLOUR_SUFFIX.search(name)
    if match is None:
        return None
    stem = name[: match.start()].strip(" _-")
    if len(stem) < 2:
        return None
    return stem


def group_fonts(fonts: list[FontInfo]) -> list[FontFamily]:
    """Collapse TheDraw colour copies. Size copies stay as their own rows."""

    if not fonts or fonts[0].engine != "tdf":
        return [FontFamily(font.id, font.kind, font.name, (font,)) for font in fonts]
    buckets: dict[tuple[str, str], list[tuple[str, FontInfo]]] = defaultdict(list)
    alone: list[FontInfo] = []
    for font in fonts:
        stem = colour_stem(font.name)
        if stem is None:
            alone.append(font)
            continue
        buckets[(font.kind, stem.lower())].append((stem, font))
    families: list[FontFamily] = [
        FontFamily(font.id, font.kind, font.name, (font,)) for font in alone
    ]
    for (kind, key), items in buckets.items():
        if len({font.name for _, font in items}) < 2:
            _, font = items[0]
            families.append(FontFamily(font.id, kind, font.name, (font,)))
            continue
        stem = items[0][0]
        members = tuple(font for _, font in sorted(items, key=lambda item: item[1].name.lower()))
        families.append(FontFamily(f"family\x1f{kind}\x1f{key}", kind, stem, members))
    families.sort(key=lambda family: (_KIND_ORDER.get(family.kind, 9), family.stem.lower()))
    return families


def tdf_ready() -> bool:
    return _TDF is not None


def load_tdf() -> list[FontInfo]:
    global _TDF
    with _LOCK:
        if _TDF is not None:
            return _TDF
        signature = _tdf_signature()
        cached = _read_cache(signature)
        if cached is not None:
            _TDF = cached
            return _TDF
        fonts: list[FontInfo] = []
        for path in tdf_engine.iter_font_files():
            for header in tdf_engine.peek_file(path):
                fonts.append(FontInfo("tdf", header.name, str(path), header.index, header.kind))
        fonts.sort(key=lambda font: (font.name.lower(), Path(font.source).name.lower(), font.index))
        _TDF = fonts
        _write_cache(signature, fonts)
        return _TDF


def default_font(engine: str) -> FontInfo:
    fonts = list_fonts(engine)
    if not fonts:
        raise RenderError(f"no {canonical(engine)} fonts found")
    preferred = {
        "figlet": ("ansi shadow", "standard", "big", "small"),
        "toilet": ("future", "pagga", "emboss"),
        "tdf": (),
    }[canonical(engine)]
    by_name = {font.name.lower(): font for font in fonts}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    return fonts[0]


def resolve(engine: str, query: str) -> FontInfo:
    key = canonical(engine)
    fonts = list_fonts(key)
    query = query.strip()
    if not query:
        return default_font(key)
    for font in fonts:
        if font.id == query:
            return font
    if key == "tdf" and "::" in query:
        found = _resolve_tdf_pair(fonts, query)
        if found is not None:
            return found
    exact_case = [
        font for font in fonts if font.name == query or Path(font.source).stem == query
    ]
    if len(exact_case) == 1:
        return exact_case[0]
    exact = [
        font
        for font in fonts
        if font.name.lower() == query.lower() or Path(font.source).stem.lower() == query.lower()
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        named = [font for font in exact if font.name.lower() == query.lower()]
        if len(named) == 1:
            return named[0]
        raise RenderError(_ambiguous(query, exact))
    partial = [
        font
        for font in fonts
        if query.lower() in font.name.lower() or query.lower() in Path(font.source).name.lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise RenderError(f"no {key} font matching {query!r}")
    raise RenderError(_ambiguous(query, partial))


_SPAN_CACHE: OrderedDict[tuple[str, str], tuple[tuple[str, int, int, int, int], ...]] = OrderedDict()


def measure_spans(font: FontInfo, text: str) -> tuple[tuple[str, int, int, int, int], ...]:
    """Where each letter sits. Used when an outline goes around each letter.

    TheDraw already records this while rendering. FIGlet and TOIlet report
    it by measuring how the line grows, once per banner, and only when asked.
    """

    if font.engine == "tdf" or len(text) > 40:
        return ()
    key = (font.id, text)
    cached = _SPAN_CACHE.get(key)
    if cached is not None:
        _SPAN_CACHE.move_to_end(key)
        return cached
    spans: list[tuple[str, int, int, int, int]] = []
    y = 0
    for line in text.split("\n"):
        if line == "":
            y += 1
            continue
        previous = 0
        height = 1
        for index, char in enumerate(line):
            drawn = render(font, line[: index + 1])
            width = drawn.grid.width
            height = drawn.grid.height or 1
            start = min(previous, width)
            spans.append((char, start, y, max(1, width - start), height))
            previous = width
        y += height
    stored = tuple(spans)
    _SPAN_CACHE[key] = stored
    while len(_SPAN_CACHE) > 64:
        _SPAN_CACHE.popitem(last=False)
    return stored


def render(font: FontInfo, text: str) -> EngineOutput:
    if font.engine == "figlet":
        return EngineOutput(figlet.render(text, font.name))
    if font.engine == "toilet":
        return EngineOutput(toilet.render(text, font.name))
    parsed = _parsed_file(Path(font.source))
    if font.index < 0 or font.index >= len(parsed):
        raise RenderError(f"{Path(font.source).name} has no font at index {font.index}")
    grid, missing, folded = tdf_engine.render_font(parsed[font.index], text)
    from meowtext.ansi import tighten

    return EngineOutput(tighten(grid), missing, folded)


def _parsed_file(path: Path) -> list[tdf_engine.TdfFont]:
    key = str(path)
    with _PARSED_LOCK:
        cached = _PARSED.get(key)
        if cached is not None:
            _PARSED.move_to_end(key)
            return cached
    fonts = tdf_engine.load_file(path)
    with _PARSED_LOCK:
        _PARSED[key] = fonts
        while len(_PARSED) > 32:
            _PARSED.popitem(last=False)
    return fonts


def _resolve_tdf_pair(fonts: list[FontInfo], query: str) -> FontInfo | None:
    left, right = query.split("::", 1)
    matches = [
        font
        for font in fonts
        if Path(font.source).stem.lower() == left.lower() or Path(font.source).name.lower() == left.lower()
    ]
    if not matches:
        return None
    if right.isdigit():
        found = [font for font in matches if font.index == int(right)]
    else:
        found = [font for font in matches if font.name.lower() == right.lower()]
    if len(found) == 1:
        return found[0]
    if not found:
        raise RenderError(f"no font {right!r} in {left}")
    raise RenderError(_ambiguous(query, found))


def _ambiguous(query: str, fonts: list[FontInfo]) -> str:
    sample = ", ".join(
        f"{Path(font.source).stem}::{font.name}" if font.engine == "tdf" else font.name for font in fonts[:6]
    )
    extra = "" if len(fonts) <= 6 else f" (+{len(fonts) - 6} more)"
    return f"{query!r} matches {len(fonts)} fonts: {sample}{extra}"


def _cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "meowtext" / "tdf-index-v1.json"


def _tdf_signature() -> str:
    count = 0
    size = 0
    newest = 0
    for path in tdf_engine.iter_font_files():
        try:
            stat = path.stat()
        except OSError:
            continue
        count += 1
        size += stat.st_size
        newest = max(newest, stat.st_mtime_ns)
    return f"{count}:{size}:{newest}"


def _read_cache(signature: str) -> list[FontInfo] | None:
    path = _cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("signature") != signature or not isinstance(payload.get("fonts"), list):
        return None
    fonts: list[FontInfo] = []
    for item in payload["fonts"]:
        try:
            fonts.append(
                FontInfo(
                    "tdf",
                    str(item["name"]),
                    str(item["source"]),
                    int(item["index"]),
                    str(item.get("kind", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
    return fonts


def _write_cache(signature: str, fonts: list[FontInfo]) -> None:
    path = _cache_path()
    payload = {
        "signature": signature,
        "fonts": [
            {"name": font.name, "source": font.source, "index": font.index, "kind": font.kind}
            for font in fonts
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return
