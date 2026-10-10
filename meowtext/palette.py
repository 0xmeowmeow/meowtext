"""Colour roles for ANSI TheDraw fonts.

A colour font does not store finished RGB. Each cell stores a DOS palette
index. Cells that share an index are the same role: the red parts stay
related to the blue parts. Rotating the hue moves every linked role by the
same amount, so the gaps between them stay put. Greys have no hue and do
not move. A role can be unlinked and edited on its own, and a role that
paints several separate sections can be split so each section is its own role.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meowtext.grid import VGA, Cell, Color, Grid

DOS_NAMES: tuple[str, ...] = (
    "black",
    "blue",
    "green",
    "cyan",
    "red",
    "magenta",
    "brown",
    "grey",
    "dark grey",
    "light blue",
    "light green",
    "light cyan",
    "light red",
    "pink",
    "yellow",
    "white",
)


def rgb_to_hsv(color: Color) -> tuple[float, float, float]:
    """Hue in degrees, saturation and value in 0..1."""

    red, green, blue = color.r / 255, color.g / 255, color.b / 255
    high = max(red, green, blue)
    low = min(red, green, blue)
    delta = high - low
    if delta == 0:
        hue = 0.0
    elif high == red:
        hue = (60 * ((green - blue) / delta)) % 360
    elif high == green:
        hue = (60 * ((blue - red) / delta) + 120) % 360
    else:
        hue = (60 * ((red - green) / delta) + 240) % 360
    saturation = 0.0 if high == 0 else delta / high
    return hue, saturation, high


def hsv_to_rgb(hue: float, saturation: float, value: float) -> Color:
    hue = hue % 360
    saturation = min(1.0, max(0.0, saturation))
    value = min(1.0, max(0.0, value))
    sector = hue / 60
    chroma = value * saturation
    mix = chroma * (1 - abs(sector % 2 - 1))
    match = value - chroma
    index = int(sector) % 6
    red, green, blue = (
        (chroma, mix, 0),
        (mix, chroma, 0),
        (0, chroma, mix),
        (0, mix, chroma),
        (mix, 0, chroma),
        (chroma, 0, mix),
    )[index]
    return Color(
        int(round((red + match) * 255)),
        int(round((green + match) * 255)),
        int(round((blue + match) * 255)),
    )


def rotate_hue(color: Color, degrees: float) -> Color:
    """Shift hue. Neutral colours (black, grey, white) stay where they are."""

    hue, saturation, value = rgb_to_hsv(color)
    if saturation < 1e-4:
        return color
    return hsv_to_rgb(hue + degrees, saturation, value)


def hue_delta(left: Color, right: Color) -> float:
    """Signed-independent gap between two hues, in degrees."""

    first, second = rgb_to_hsv(left)[0], rgb_to_hsv(right)[0]
    return (second - first) % 360


@dataclass(slots=True)
class Role:
    """One colour a banner can refer to, and whether it still follows the group."""

    base: Color
    name: str
    linked: bool = True
    hue: float = 0.0
    sat: float = 0.0
    val: float = 0.0

    def paint(self, shift: float) -> Color:
        if not self.linked:
            return hsv_to_rgb(self.hue, self.sat, self.val)
        return rotate_hue(self.base, shift)

    def clone(self) -> Role:
        return Role(self.base, self.name, self.linked, self.hue, self.sat, self.val)


@dataclass(slots=True)
class RelationPalette:
    """The roles in one banner, plus the hue shift applied to every linked role."""

    hue: float = 0.0
    roles: dict[int, Role] = field(default_factory=dict)
    next_id: int = 16

    def color(self, slot: int, hue_offset: float = 0.0) -> Color:
        shift = self.hue + hue_offset
        role = self.roles.get(slot)
        if role is None:
            if 0 <= slot < 16:
                return rotate_hue(Color(*VGA[slot]), shift)
            return Color(255, 255, 255)
        return role.paint(shift)

    def ensure(self, grid: Grid) -> None:
        """Create a role for every index the grid uses, without touching edits."""

        for slot in used_slots(grid):
            if slot in self.roles:
                continue
            if 0 <= slot < 16:
                base = Color(*VGA[slot])
                name = DOS_NAMES[slot]
            else:
                base = Color(255, 255, 255)
                name = f"section {slot}"
            hue, sat, val = rgb_to_hsv(base)
            self.roles[slot] = Role(base, name, True, hue, sat, val)
        if self.roles:
            self.next_id = max(self.next_id, max(self.roles) + 1)

    def drop_splits(self) -> None:
        """Forget sections made by splitting. The sixteen DOS roles stay."""

        self.roles = {slot: role for slot, role in self.roles.items() if slot < 16}
        self.next_id = 16

    def break_role(self, slot: int) -> None:
        """Stop this role following the group. It keeps the colour it has now."""

        role = self.roles[slot]
        if role.linked:
            hue, sat, val = rgb_to_hsv(role.paint(self.hue))
            role.hue, role.sat, role.val = hue, sat, val
            role.linked = False

    def link_role(self, slot: int) -> None:
        """Put this role back under the shared hue shift."""

        self.roles[slot].linked = True

    def set_hsv(self, slot: int, hue: float, sat: float, val: float) -> None:
        """Edit one role on its own. Doing so unlinks it from the group."""

        self.break_role(slot)
        role = self.roles[slot]
        role.hue = hue % 360
        role.sat = min(1.0, max(0.0, sat))
        role.val = min(1.0, max(0.0, val))

    def split(self, grid: Grid, slot: int) -> int:
        """Give each extra connected section of ``slot`` a role of its own.

        The first section keeps the original role, so a font with one red
        shape is unchanged. New roles start as copies, still linked, and can
        then be edited alone. Returns how many new roles were made.
        """

        if slot not in self.roles:
            return 0
        components = _sections(grid, slot)
        if len(components) < 2:
            return 0
        parent = self.roles[slot]
        made = 0
        for component in components[1:]:
            new_id = self.next_id
            self.next_id += 1
            made += 1
            clone = parent.clone()
            clone.name = f"{parent.name} {made + 1}"
            self.roles[new_id] = clone
            for x, y in component:
                cell = grid.rows[y][x]
                if cell.fg_slot == slot:
                    cell.fg_slot = new_id
                if cell.bg_slot == slot:
                    cell.bg_slot = new_id
        return made


def role_place(grid: Grid, slot: int) -> tuple[int, str]:
    """How many separate patches use ``slot``, and whether it is ink or background."""

    sections = len(_sections(grid, slot))
    as_ink = False
    as_background = False
    for row in grid.rows:
        for cell in row:
            if cell.fg_slot == slot:
                as_ink = True
            if cell.bg_slot == slot:
                as_background = True
    if as_ink and as_background:
        where = "ink and background"
    elif as_background:
        where = "background"
    else:
        where = "ink"
    return sections, where


def used_slots(grid: Grid) -> list[int]:
    """Palette indexes in the order they first appear."""

    found: list[int] = []
    seen: set[int] = set()
    for row in grid.rows:
        for cell in row:
            for slot in (cell.fg_slot, cell.bg_slot):
                if slot is None or slot in seen:
                    continue
                seen.add(slot)
                found.append(slot)
    return found


def paint(grid: Grid, palette: RelationPalette, hue_offset: float = 0.0) -> Grid:
    """Resolve roles to RGB. The source grid is not modified."""

    painted = grid.copy()
    painted.palette = palette
    for row in painted.rows:
        for cell in row:
            if cell.fg_slot is not None:
                cell.fg = palette.color(cell.fg_slot, hue_offset)
            if cell.bg_slot is not None:
                cell.bg = palette.color(cell.bg_slot, hue_offset)
    return painted


def _sections(grid: Grid, slot: int) -> list[list[tuple[int, int]]]:
    """4-connected groups of cells that use ``slot`` as foreground or background."""

    height = len(grid.rows)
    seen: set[tuple[int, int]] = set()
    groups: list[list[tuple[int, int]]] = []
    for y, row in enumerate(grid.rows):
        for x, cell in enumerate(row):
            if (x, y) in seen or (cell.fg_slot != slot and cell.bg_slot != slot):
                continue
            group: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                group.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) in seen or ny < 0 or ny >= height or nx < 0 or nx >= len(grid.rows[ny]):
                        continue
                    other = grid.rows[ny][nx]
                    if other.fg_slot == slot or other.bg_slot == slot:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            groups.append(group)
    return groups
