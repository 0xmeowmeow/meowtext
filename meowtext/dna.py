"""B-DNA from 1BNA, drawn as a column of text.

The Dickerson dodecamer's central pair, A6 with T19, is set in its own
plane. That pair is stacked on the ideal B-DNA screw: 36 degrees and
3.4 angstroms, right-handed, ten pairs to a turn. The next turn is the
same turn again. Scanning rotates the screw so the chosen pair faces you.
A·T is drawn with two bonds and G·C with three.
"""

from __future__ import annotations

import math
from pathlib import Path

PDB = Path(__file__).resolve().parents[1] / "examples" / "pdb" / "1BNA.pdb"
BASES_PER_TURN = 10
RISE = 3.4
TWIST = math.tau / BASES_PER_TURN
_COMPLEMENT = {"A": "T", "T": "A", "G": "C", "C": "G"}
_BACKBONE = {"P", "OP1", "OP2", "O5'", "C5'", "C4'", "O4'", "C3'", "O3'", "C2'"}
_WIDTH = 17
_CENTER = 8.0
_SCALE = 1.45


def complement(base: str) -> str:
    return _COMPLEMENT.get(base.upper(), "N")


def bonds(base: str) -> int:
    """Watson–Crick hydrogen bonds: two for A·T, three for G·C."""

    return 3 if base.upper() in "GC" else 2


def helix_steps(length: int, phase: float = 0.0) -> list[dict]:
    """Axis samples for a right-handed screw. Ten steps close one turn."""

    steps = []
    for index in range(length):
        theta = index * TWIST + phase
        steps.append(
            {
                "index": index,
                "theta": theta,
                "x": math.cos(theta),
                "y": math.sin(theta),
                "z": index * RISE,
            }
        )
    return steps


def render_ascii(sequence: str, scan: float = 0.0, *, turns: int = 3) -> str:
    """One row per base pair. The wide rung is the pair facing you."""

    bases = "".join(char for char in sequence.upper() if char in "ATGC")
    if not bases:
        bases = "CGCGAATTCGCG"
    count = max(1, turns) * BASES_PER_TURN
    bases = (bases * (count + 1))[:count]
    chosen = min(count - 1, int(max(0.0, min(1.0, scan)) * (count - 1)))
    # π puts that pair on the near side, where both phosphates face you.
    phase = math.pi - chosen * TWIST
    rows = [_row(bases, index, phase, chosen) for index in range(count)]
    rows.reverse()
    pair = bases[chosen]
    header = f"1BNA  right-handed  10/turn  {chosen + 1:>2} {pair}{'·' * bonds(pair)}{complement(pair)}"
    return "\n".join([header, *rows])


def _polymer(length: int, phase: float) -> list[tuple[str, str, float, float, float]]:
    """Stacked copies of the 1BNA pair. Each item is chain, atom, x, y, z."""

    pair = _template_pair()
    placed = []
    for index in range(length):
        theta = index * TWIST + phase
        cos, sin = math.cos(theta), math.sin(theta)
        rise = index * RISE
        for chain, name, x, y, z in pair:
            placed.append((chain, name, cos * x - sin * y, sin * x + cos * y, z + rise))
    return placed


def _template_pair() -> list[tuple[str, str, float, float, float]]:
    """A6·T19 with z along the pair normal and chain A on +x."""

    atoms = _parse_pdb(PDB)
    plane = [
        (atom[4], atom[5], atom[6])
        for atom in atoms
        if (atom[2], atom[3]) in {("A", 6), ("B", 19)} and atom[0] not in _BACKBONE
    ]
    normal = _plane_normal(plane)
    carbon_a = _xyz(atoms, "C1'", "A", 6)
    carbon_next = _xyz(atoms, "C1'", "A", 7)
    if _dot(normal, _sub(carbon_next, carbon_a)) < 0:
        normal = tuple(-value for value in normal)
    carbon_b = _xyz(atoms, "C1'", "B", 19)
    origin = tuple((carbon_a[i] + carbon_b[i]) / 2 for i in range(3))
    across = _sub(carbon_a, carbon_b)
    across = _sub(across, _mul(normal, _dot(across, normal)))
    x_axis = _unit(across)
    y_axis = _cross(normal, x_axis)
    wanted = (("A", "P"), ("A", "C1'"), ("B", "P"), ("B", "C1'"))
    points = []
    for chain, name in wanted:
        found = _xyz(atoms, name, chain, 6 if chain == "A" else 19)
        relative = _sub(found, origin)
        points.append((chain, name, _dot(relative, x_axis), _dot(relative, y_axis), _dot(relative, normal)))
    return points


def _row(bases: str, index: int, phase: float, chosen: int) -> str:
    theta = index * TWIST + phase
    cos, sin = math.cos(theta), math.sin(theta)
    placed = {}
    for chain, name, x, y, _z in _template_pair():
        placed[(chain, name)] = (cos * x - sin * y, sin * x + cos * y)
    cells = [(0, " ")] * _WIDTH

    def paint(col: int, char: str, priority: int) -> None:
        if 0 <= col < _WIDTH and priority >= cells[col][0]:
            cells[col] = (priority, char)

    def column(x: float) -> int:
        return int(round(_CENTER + x / _SCALE))

    a_p = placed[("A", "P")]
    b_p = placed[("B", "P")]
    a_c = placed[("A", "C1'")]
    b_c = placed[("B", "C1'")]
    sugar_a, sugar_b = column(a_c[0]), column(b_c[0])
    base = bases[index]
    left_is_a = sugar_a < sugar_b
    token = (base if left_is_a else complement(base)) + ("·" * bonds(base)) + (complement(base) if left_is_a else base)
    left_sugar, right_sugar = sorted((sugar_a, sugar_b))
    slots = right_sugar - left_sugar - 1
    # Letters sit on the near face. The far face keeps the two strands, so one
    # labeled rung returns every ten pairs.
    if slots >= len(token) and (a_p[1] + b_p[1]) >= 0:
        start = left_sugar + 1 + (slots - len(token)) // 2
        for offset, char in enumerate(token):
            paint(start + offset, char, 3)
        _link(paint, column(a_p[0]), start if left_is_a else start + len(token) - 1)
        _link(paint, column(b_p[0]), start + len(token) - 1 if left_is_a else start)
    for priority, (chain, point) in enumerate(sorted((("A", a_p), ("B", b_p)), key=lambda item: item[1][1]), start=4):
        paint(column(point[0]), _mark(chain, point[1]), priority)
    body = "".join(char for _priority, char in cells).rstrip()
    return ("> " if index == chosen else "  ") + body


def _link(paint, phosphate: int, letter: int) -> None:
    step = 1 if letter > phosphate else -1
    col = phosphate + step
    while col != letter:
        paint(col, "-", 1)
        col += step


def _mark(chain: str, depth: float) -> str:
    """Strand A stays round and strand B stays square, lighter when behind."""

    front = depth >= 0
    if chain == "A":
        return "@" if front else "o"
    return "#" if front else "+"


def _parse_pdb(path: Path) -> list[tuple]:
    atoms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("ATOM"):
            continue
        atoms.append((
            line[12:16].strip(),
            line[17:20].strip(),
            line[21],
            int(line[22:26]),
            float(line[30:38]),
            float(line[38:46]),
            float(line[46:54]),
        ))
    return atoms


def _xyz(atoms, name: str, chain: str, resi: int) -> tuple[float, float, float]:
    for atom in atoms:
        if atom[0] == name and atom[2] == chain and atom[3] == resi:
            return (atom[4], atom[5], atom[6])
    raise KeyError((name, chain, resi))


def _plane_normal(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Direction in which the base atoms spread the least."""

    count = len(points)
    center = tuple(sum(point[i] for point in points) / count for i in range(3))
    cov = [[0.0] * 3 for _ in range(3)]
    for point in points:
        delta = _sub(point, center)
        for row in range(3):
            for col in range(3):
                cov[row][col] += delta[row] * delta[col]
    trace = cov[0][0] + cov[1][1] + cov[2][2]
    shifted = [[(trace if row == col else 0.0) - cov[row][col] for col in range(3)] for row in range(3)]
    vector = [0.2, 0.5, 0.8]
    for _ in range(48):
        nxt = [sum(shifted[row][col] * vector[col] for col in range(3)) for row in range(3)]
        norm = math.sqrt(sum(value * value for value in nxt))
        vector = [value / norm for value in nxt]
    return (vector[0], vector[1], vector[2])


def _sub(a, b) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(vector, scale: float) -> tuple[float, float, float]:
    return (vector[0] * scale, vector[1] * scale, vector[2] * scale)


def _unit(vector) -> tuple[float, float, float]:
    norm = math.sqrt(_dot(vector, vector))
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
