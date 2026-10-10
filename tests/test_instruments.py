"""The instrument parts stay inside their boxes and move with the value."""

from __future__ import annotations

import math
import unittest

from meowtext.grid import Grid
from meowtext.instruments import (
    GREEN,
    THEMES,
    brackets,
    frame,
    kitty_place,
    plate,
    readout,
    shade,
    specimen,
)
from meowtext.pixels import CELL_H, CELL_W, dial, fader, gauge, lamp


class InstrumentTests(unittest.TestCase):
    def test_gauge_fill_grows_smoothly(self) -> None:
        low = _opaque_right(gauge(0.2, GREEN))
        high = _opaque_right(gauge(0.8, GREEN))
        self.assertGreater(high, low)
        self.assertEqual(gauge(0.5, GREEN).size, (20 * CELL_W, 2 * CELL_H))

    def test_fader_thumb_rises_with_the_value(self) -> None:
        down = _bright_center(fader(0, GREEN))
        up = _bright_center(fader(1, GREEN))
        self.assertLess(up[1], down[1])

    def test_frame_corners_and_clear_inside(self) -> None:
        grid = Grid.blank(6, 4)
        frame(grid, 0, 0, 6, 4, GREEN, style="double")
        self.assertEqual(_row(grid, 0), "╔════╗")
        self.assertEqual(_row(grid, 1), "║    ║")
        self.assertEqual(_row(grid, 3), "╚════╝")

    def test_brackets_leave_the_middle_open(self) -> None:
        grid = Grid.blank(10, 5)
        brackets(grid, 0, 0, 10, 5, GREEN, arm=2)
        self.assertEqual(_row(grid, 0), "┌─      ─┐")
        self.assertEqual(grid.get(4, 0).char, " ")
        self.assertEqual(grid.get(0, 2).char, " ")

    def test_dial_is_a_circle_and_the_needle_moves(self) -> None:
        face = dial(1, GREEN)
        self.assertEqual(face.size, (16 * CELL_W, 8 * CELL_H))
        self.assertLess(_rim_spread(face), 0.08)
        rest = _needle_angle(dial(0, GREEN))
        half = _needle_angle(dial(0.5, GREEN))
        full = _needle_angle(dial(1, GREEN))
        self.assertLess(rest[0], 0)
        self.assertLess(rest[1], 0)
        self.assertGreater(half[1], 0)
        self.assertGreater(full[0], 0)
        self.assertLess(full[1], 0)

    def test_plate_readout_and_lamp(self) -> None:
        grid = Grid.blank(10, 3)
        plate(grid, 0, 0, 8, "PAGE", GREEN)
        self.assertEqual(_row(grid, 0)[:8], "  PAGE  ")
        self.assertEqual(grid.get(0, 0).bg, GREEN)
        readout(grid, 0, 1, 8, "MASS", "99", GREEN)
        self.assertEqual(_row(grid, 1)[:8], "MASS  99")
        dim = lamp(0, GREEN)
        lit = lamp(1, GREEN)
        self.assertGreater(_opaque_count(lit), _opaque_count(dim))
        self.assertEqual(shade(0), "░")
        self.assertEqual(shade(1), "█")

    def test_themes_name_parts_the_library_has(self) -> None:
        from meowtext import instruments

        self.assertGreaterEqual(len(THEMES), 6)
        for theme in THEMES:
            self.assertTrue(theme.elements)
            self.assertTrue(theme.sources)
            for name in theme.elements:
                self.assertTrue(callable(getattr(instruments, name)), name)

    def test_specimen_is_a_kitty_picture(self) -> None:
        image, columns, rows = specimen()
        self.assertEqual(image.size, (columns * CELL_W, rows * CELL_H))
        placed = kitty_place(image, columns, rows)
        self.assertTrue(placed.startswith("\x1b_Ga=T,f=100,"))
        self.assertIn(f"c={columns},r={rows}", placed)
        self.assertIn("z=-1", placed)
        self.assertTrue(placed.endswith("\x1b\\"))


def _row(grid: Grid, y: int) -> str:
    return "".join(cell.char or " " for cell in grid.rows[y])


def _opaque_count(image) -> int:
    return sum(1 for value in image.getchannel("A").getdata() if value > 40)


def _opaque_right(image) -> int:
    alpha = image.getchannel("A")
    right = 0
    for x in range(image.width):
        if any(alpha.getpixel((x, y)) > 200 for y in range(image.height)):
            right = x
    return right


def _rim_spread(image) -> float:
    alpha = image.getchannel("A")
    cx, cy = image.width / 2, image.height / 2
    dists = []
    for y in range(image.height):
        for x in range(image.width):
            if alpha.getpixel((x, y)) > 40:
                dists.append(math.hypot(x - cx, y - cy))
    outer = [d for d in dists if d > max(dists) * 0.8]
    mean = sum(outer) / len(outer)
    variance = sum((d - mean) ** 2 for d in outer) / len(outer)
    return math.sqrt(variance) / mean


def _needle_angle(image) -> tuple[float, float]:
    """Mean offset of the needle body. x is right, y is up."""

    alpha = image.getchannel("A")
    cx, cy = image.width / 2, image.height / 2
    limit = min(image.size)
    sx = sy = 0.0
    count = 0
    for y in range(image.height):
        for x in range(image.width):
            if alpha.getpixel((x, y)) > 200:
                dx, dy = x - cx, cy - y
                distance = math.hypot(dx, dy)
                if 0.12 * limit < distance < 0.34 * limit:
                    sx += dx
                    sy += dy
                    count += 1
    self_check = count > 0
    assert self_check
    return sx / count, sy / count


def _bright_center(image) -> tuple[float, float]:
    alpha = image.getchannel("A")
    total = 0
    sx = 0.0
    sy = 0.0
    for y in range(image.height):
        for x in range(image.width):
            if alpha.getpixel((x, y)) > 200:
                total += 1
                sx += x
                sy += y
    self_check = total > 0
    assert self_check
    return sx / total, sy / total


if __name__ == "__main__":
    unittest.main()
