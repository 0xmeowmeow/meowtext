"""Local font discovery: soft neighbourhoods with room to explore."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from meowtext.catalog import FontInfo, group_fonts, list_fonts, render
from meowtext.errors import RenderError
from meowtext.grid import Grid, is_ink

CATEGORIES = (
    "All",
    "Gothic",
    "Script",
    "Slanted",
    "Thin lines",
    "Compact",
    "Big blocks",
    "Outline",
    "ANSI colour",
)
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

    @property
    def description(self) -> str:
        """Human vocabulary supplements the measured silhouette, never replaces it."""
        labels = [c for c in self.categories if c != "All"]
        labels = ["Gothic / blackletter" if c == "Gothic" else c for c in labels]
        height = round(2 ** (self.features[1] * 4) - 1)
        size = "tall" if height >= 10 else "small" if height <= 4 else "medium"
        weight = "open strokes" if self.features[2] < 0.7 else "dense strokes"
        return " · ".join([*labels[:2], size, weight, self.font.engine.upper()])


def named_categories(font: FontInfo) -> tuple[str, ...]:
    name = re.sub(r"[_-]+", " ", font.name.casefold())
    categories = []
    if re.search(r"goth|fraktur|black\s*letter|old\s*eng|medieval|cloister", name):
        categories.append("Gothic")
    if re.search(r"script|cursiv|handwrit|calligraph", name):
        categories.append("Script")
    if re.search(r"slant|italic|lean|speed", name):
        categories.append("Slanted")
    return tuple(categories)


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
    cats = ["All", *named_categories(font)]
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
                    tuple(
                        dict.fromkeys(
                            ("All", *named_categories(font), *item["categories"])
                        )
                    ),
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
        ("figlet", "Gothic"),
        ("figlet", "Script"),
        ("figlet", "Mini"),
        ("figlet", "Bubble"),
        ("figlet", "Shadow"),
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
    measured = sum((x - y) ** 2 for x, y in zip(a.features, b.features))
    named_a, named_b = set(named_categories(a.font)), set(named_categories(b.font))
    # A recognisable family name is useful evidence when silhouettes disagree.
    if named_a and named_b and named_a.isdisjoint(named_b):
        measured += 1.0
    elif bool(named_a) != bool(named_b):
        measured += 0.7
    return measured


def shape_key(item: Specimen):
    """Keep copies and colour variants from occupying a comparison round.

    The catalogue still contains every font. Only the comparison treats equal
    measured shapes as one candidate; ANSI colour alone is not a new shape.
    """
    return tuple(
        round(value, 8) for index, value in enumerate(item.features) if index != 5
    )


def distinct_shapes(items, exclude=()):
    seen = {shape_key(item) for item in exclude}
    names = {}
    for item in exclude:
        names.setdefault(item.font.name.casefold().strip(), []).append(item)
    result = []
    for item in items:
        key = shape_key(item)
        name = item.font.name.casefold().strip()
        # Copies ported between FIGlet and TheDraw can differ slightly in
        # spacing. Keep them accessible in Browse all, but avoid showing three
        # effectively identical Frakturs in a nine-font comparison.
        similar = any(
            sum(
                (a - b) ** 2
                for index, (a, b) in enumerate(zip(item.features, other.features))
                if index != 5
            )
            < 0.08
            for other in names.get(name, ())
        )
        if key not in seen and not similar:
            seen.add(key)
            names.setdefault(name, []).append(item)
            result.append(item)
    return result


def representatives(
    items: list[Specimen], count: int = 6, offset: int = 0
) -> list[Specimen]:
    """Farthest-first selection avoids a page of near-identical font names."""
    if not items or count <= 0:
        return []
    items = distinct_shapes(items)
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
        self.scope = items[:]
        self.count = count
        self.history = []
        self.seed = None
        self.offset = 0
        self.explorers = set()
        self.choices = []
        self._choose()

    def reset(self, category="All", query="", favourites=None) -> None:
        terms = query.casefold().split()

        def matches(item):
            names = " ".join(
                (item.font.name, Path(item.font.source).name, item.description)
            )
            if "Gothic" in item.categories:
                names += " fraktur medieval old english blackletter black letter"
            return (
                category in item.categories
                and all(term in names.casefold() for term in terms)
                and (favourites is None or font_key(item.font) in favourites)
            )

        self.scope = [item for item in self.all if matches(item)]
        self.pool = self.scope[:]
        self.history.clear()
        self.seed = None
        self.offset = 0
        self._choose()

    def _choose(self):
        self.explorers = set()
        if not self.pool:
            self.choices = []
            return
        if self.seed is None:
            # Include familiar directions on the first page. Farthest-first
            # alone tended to spend every slot on an eccentric visual outlier.
            chosen = []
            if not self.offset:
                for category, familiar in (
                    ("Big blocks", "ANSI Shadow"),
                    ("Gothic", "FB-Gothic Cy"),
                    ("Thin lines", "future"),
                    ("ANSI colour", ""),
                    ("Script", "Script"),
                    ("Compact", "pagga"),
                ):
                    candidates = [
                        i
                        for i in distinct_shapes(self.pool, chosen)
                        if category in i.categories
                    ]
                    if candidates and len(chosen) < self.count:
                        chosen.append(
                            min(
                                candidates,
                                key=lambda i: (
                                    i.font.name != familiar,
                                    abs(i.features[1] - 0.75)
                                    + abs(i.features[0] - 0.8),
                                    len(i.font.name),
                                    i.font.name,
                                ),
                            )
                        )
            for item in representatives(
                distinct_shapes(self.pool, chosen), self.count, self.offset
            ):
                if item not in chosen:
                    chosen.append(item)
                if len(chosen) == self.count:
                    break
        else:
            # Four close shapes plus two escape routes at the default six.
            # Search the original scope every time, so one click never deletes
            # a branch of the catalogue. The user chooses when they are done.
            close_count = max(2, self.count - max(1, self.count // 3))
            near = distinct_shapes(self.pool, [self.seed])
            start = self.offset % max(1, len(near))
            near = near[start:] + near[:start]
            chosen = [self.seed]
            window = near[: max(close_count * 4, 12)]
            for item in representatives(window, close_count - 1):
                if item not in chosen:
                    chosen.append(item)
            outside = distinct_shapes(
                [i for i in self.scope if i not in self.pool], chosen
            )
            if not outside:
                outside = distinct_shapes(
                    [i for i in self.all if i not in self.pool], chosen
                )
            if outside:
                ordered = sorted(
                    outside, key=lambda i: distance(i, self.seed), reverse=True
                )
                # Rotate the exploratory candidates too, rather than repeating
                # the same extreme outlier on every page.
                start = self.offset % len(ordered)
                outside = ordered[start:] + ordered[:start]
                for item in representatives(outside, self.count - len(chosen)):
                    chosen.append(item)
                    self.explorers.add(item.font.id)
        # Small result sets remain useful: fill spare places with clearly
        # labelled nearby and far-away alternatives. Favourites/list mode uses
        # the unpadded pool directly, so it never invents saved favourites.
        if len(chosen) < self.count:
            remaining = distinct_shapes(self.all, chosen)
            if remaining:
                anchor = self.seed or chosen[0]
                remaining.sort(key=lambda i: distance(i, anchor))
                for item in representatives(
                    remaining, self.count - len(chosen), self.offset
                ):
                    chosen.append(item)
                    self.explorers.add(item.font.id)
        self.choices = chosen[: self.count]

    def narrow(self, index: int) -> None:
        seed = self.choices[index]
        self.history.append(
            (
                self.pool[:],
                self.scope[:],
                self.choices[:],
                self.seed,
                self.offset,
                self.explorers.copy(),
            )
        )
        # Following a wildcard explicitly broadens the search again.
        if seed not in self.scope:
            self.scope = self.all[:]
        previous = self.seed
        self.seed = seed
        ranked = sorted(
            self.scope,
            key=lambda item: distance(item, seed)
            + (0.15 * distance(item, previous) if previous else 0),
        )
        size = min(len(ranked), max(self.count * 6, int(len(self.pool) * 0.55)))
        self.pool = [seed, *[i for i in ranked if i != seed]][:size]
        self.offset = 0
        self._choose()

    def back(self) -> None:
        if self.history:
            (
                self.pool,
                self.scope,
                self.choices,
                self.seed,
                self.offset,
                self.explorers,
            ) = self.history.pop()

    def more(self) -> None:
        self.offset += self.count
        self._choose()

    def resize(self, count):
        if count != self.count:
            self.count = count
            self._choose()
