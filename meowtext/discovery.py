"""Local, measured font discovery. Each choice narrows a reversible search tree."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from meowtext.catalog import FontInfo, group_fonts, list_fonts, render
from meowtext.errors import RenderError
from meowtext.grid import Grid, is_ink

CATEGORIES = ("All", "Thin lines", "Compact", "Big blocks", "Outline", "ANSI colour")
SAMPLE = "MEOW"
_INDEX_LOCK = threading.Lock()


def font_key(font: FontInfo) -> str:
    """Portable identity for a favourite; installation paths may move."""
    return "|".join((font.engine, Path(font.source).name, str(font.index), font.name))


@dataclass(frozen=True)
class Specimen:
    font: FontInfo
    features: tuple[float, ...]
    categories: tuple[str, ...]


def describe(grid: Grid, font: FontInfo) -> Specimen:
    ink = [
        (x, y, c)
        for y, row in enumerate(grid.rows)
        for x, c in enumerate(row)
        if is_ink(c)
    ]
    if not ink:
        raise RenderError("font has no visible sample")
    left, right = min(x for x, _, _ in ink), max(x for x, _, _ in ink)
    top, bottom = min(y for _, y, _ in ink), max(y for _, y, _ in ink)
    width, height = right - left + 1, bottom - top + 1
    count = len(ink)
    blocks = sum(0x2580 <= ord(c.char[0]) <= 0x259F for _, _, c in ink) / count
    lines = (
        sum(
            c.char in "_|/\\-+.,'`" or 0x2500 <= ord(c.char[0]) <= 0x257F
            for _, _, c in ink
        )
        / count
    )
    density = count / (width * height)
    colour = float(font.kind == "color")
    cats = ["All"]
    if lines > 0.60 and blocks < 0.1:
        cats.append("Thin lines")
    if height <= 5 and width <= 34:
        cats.append("Compact")
    if blocks > 0.25 or (height >= 7 and density > 0.45):
        cats.append("Big blocks")
    if font.kind == "outline" or (lines > 0.45 and height >= 5 and density < 0.55):
        cats.append("Outline")
    if colour:
        cats.append("ANSI colour")
    # Normalised occupancy retains coarse shape, in addition to weight and size.
    bins = [0.0] * 24
    for x, y, _ in ink:
        bx, by = min(5, (x - left) * 6 // width), min(3, (y - top) * 4 // height)
        bins[by * 6 + bx] += 1 / count
    vector = (
        math.log2(width + 1) / 6,
        math.log2(height + 1) / 4,
        density * 2,
        blocks * 2,
        lines,
        colour,
        *bins,
    )
    return Specimen(font, vector, tuple(cats))


def available_fonts() -> list[FontInfo]:
    fonts = []
    for engine in ("figlet", "toilet", "tdf"):
        fonts.extend(family.members[0] for family in group_fonts(list_fonts(engine)))
    return fonts


def _cache_file() -> Path:
    return (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "meowtext"
        / "discovery-v1.json"
    )


def build_index(
    fonts: list[FontInfo] | None = None, progress=None, stopped=None
) -> list[Specimen]:
    fonts = available_fonts() if fonts is None else fonts
    path = _cache_file()
    try:
        cached = json.loads(path.read_text())
        if not isinstance(cached, dict):
            cached = {}
    except (OSError, ValueError):
        cached = {}
    updated = {}

    def one(font: FontInfo) -> Specimen | None:
        if stopped and stopped():
            return None
        try:
            stat = Path(font.source).stat()
            key = hashlib.sha256(
                f"{font.id}:{stat.st_size}:{stat.st_mtime_ns}".encode()
            ).hexdigest()
            item = cached.get(key)
            if isinstance(item, dict) and len(item.get("features", [])) == 30:
                result = Specimen(
                    font,
                    tuple(float(x) for x in item["features"]),
                    tuple(item["categories"]),
                )
            else:
                result = describe(render(font, SAMPLE).grid, font)
            updated[key] = {
                "features": result.features,
                "categories": result.categories,
            }
            return result
        except (RenderError, OSError, ValueError, KeyError, TypeError):
            return None

    # Group by source so multiple entries in one TDF file reuse its parsed glyphs.
    ordered = sorted(fonts, key=lambda f: (f.source, f.index))
    result = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, item in enumerate(pool.map(one, ordered)):
            if item is not None:
                result.append(item)
            if (
                progress
                and not (stopped and stopped())
                and (index % 50 == 0 or index == len(ordered) - 1)
            ):
                progress(index + 1, len(ordered))
    result.sort(
        key=lambda item: (item.font.engine, item.font.name.casefold(), item.font.id)
    )
    if stopped and stopped():
        return result
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(updated))
        temporary.replace(path)
    except OSError:
        pass  # An unwritable cache must not prevent font selection.
    return result


def starter_index() -> list[Specimen]:
    """A useful first screen immediately, while the complete library is indexed."""
    from meowtext.catalog import resolve

    found = []
    for engine, name in [
        ("figlet", "ANSI Shadow"),
        ("figlet", "Slant"),
        ("figlet", "Small"),
        ("toilet", "future"),
        ("figlet", "Big"),
        ("toilet", "pagga"),
        ("figlet", "standard"),
        ("figlet", "Digital"),
        ("figlet", "Lean"),
    ]:
        try:
            font = resolve(engine, name)
            item = describe(render(font, SAMPLE).grid, font)
            if all(f.font.id != font.id for f in found):
                found.append(item)
        except RenderError:
            continue
    return found


def distance(a: Specimen, b: Specimen) -> float:
    return sum((x - y) ** 2 for x, y in zip(a.features, b.features))


def representatives(
    items: list[Specimen], count: int = 6, offset: int = 0
) -> list[Specimen]:
    """Farthest-first selection avoids a page of near-identical font names."""
    if not items or count <= 0:
        return []
    chosen = [items[offset % len(items)]]
    remaining = [item for item in items if item != chosen[0]]
    nearest = {item.font.id: distance(item, chosen[0]) for item in remaining}
    while remaining and len(chosen) < count:
        best = max(remaining, key=lambda item: nearest[item.font.id])
        chosen.append(best)
        remaining.remove(best)
        for item in remaining:
            nearest[item.font.id] = min(nearest[item.font.id], distance(item, best))
    return chosen


class Discovery:
    def __init__(self, items: list[Specimen], count: int = 6):
        self.all = items
        self.pool = items[:]
        self.count = count
        self.history: list[list[Specimen]] = []
        self.offset = 0
        self.choices = representatives(self.pool, count)

    def reset(
        self, category: str = "All", query: str = "", favourites: set[str] | None = None
    ) -> None:
        self.pool = [
            item
            for item in self.all
            if category in item.categories
            and query.casefold()
            in f"{item.font.name} {Path(item.font.source).name}".casefold()
            and (favourites is None or font_key(item.font) in favourites)
        ]
        self.history.clear()
        self.offset = 0
        self.choices = representatives(self.pool, self.count)

    def narrow(self, index: int) -> None:
        seed = self.choices[index]
        self.history.append(self.pool[:])
        # Keep each representative in its own group even when silhouettes match.
        choice_ids = {item.font.id for item in self.choices}
        group = [
            item
            for item in self.pool
            if item.font.id not in choice_ids
            and min(
                range(len(self.choices)), key=lambda i: distance(item, self.choices[i])
            )
            == index
        ]
        self.pool = [seed, *sorted(group, key=lambda item: distance(item, seed))]
        self.offset = 0
        self.choices = representatives(self.pool, self.count)

    def back(self) -> None:
        if self.history:
            self.pool = self.history.pop()
        self.offset = 0
        self.choices = representatives(self.pool, self.count)

    def more(self) -> None:
        self.offset = (self.offset + self.count) % max(1, len(self.pool))
        self.choices = representatives(self.pool, self.count, self.offset)
