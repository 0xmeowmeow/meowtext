"""Engine, effect, and export tests. TheDraw samples are built in memory."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from meowtext.ansi import parse_ansi
from meowtext.effects import BannerStyle, apply_style, drop_shadow, gradient, outline, resolve_palette
from meowtext.engines.tdf import parse_tdf, render_font
from meowtext.export import export, grid_from_json, to_ansi, to_plain
from meowtext.grid import VGA, Cell, Color, Grid, is_ink
from meowtext.palette import RelationPalette, hue_delta, paint, role_place, rotate_hue, used_slots

MAGIC = b"\x13TheDraw FONTS file\x1a"
MARKER = b"\x55\xaa\x00\xff"


def _font_body(name: str, font_type: int, spacing: int, glyphs: dict[str, bytes]) -> bytes:
    encoded = name.encode("ascii")[:12]
    body = bytearray()
    body.append(len(encoded))
    body += encoded.ljust(12, b"\x00")
    body += b"\x00\x00\x00\x00"
    body.append(font_type)
    body.append(spacing)
    size_at = len(body)
    body += b"\x00\x00"
    offsets = [0xFFFF] * 94
    data = bytearray()
    for char, raw in glyphs.items():
        offsets[ord(char) - 33] = len(data)
        data += raw
    for offset in offsets:
        body += offset.to_bytes(2, "little")
    body[size_at : size_at + 2] = len(data).to_bytes(2, "little")
    body += data
    return bytes(body)


def _bundle(*bodies: bytes) -> bytes:
    blob = MAGIC + MARKER + bodies[0]
    for body in bodies[1:]:
        blob += MARKER + body
    return blob


class GridTests(unittest.TestCase):
    def test_ansi_truecolor_and_named_red(self) -> None:
        grid = parse_ansi("\x1b[38;2;1;2;3mZ\x1b[31mX\x1b[0m")
        self.assertEqual(grid.rows[0][0].char, "Z")
        self.assertEqual(grid.rows[0][0].fg, Color(1, 2, 3))
        self.assertEqual(grid.rows[0][1].char, "X")
        self.assertEqual(grid.rows[0][1].fg, Color(*VGA[4]))

    def test_plain_round_trip_and_json(self) -> None:
        grid = Grid([[Cell("A", Color(1, 2, 3)), Cell()], [Cell("B", bg=Color(4, 5, 6))]])
        grid.normalize()
        self.assertEqual(to_plain(grid), "A \nB \n")
        restored = grid_from_json(json.loads(export(grid, "json")))
        self.assertEqual(restored, grid)
        ansi = to_ansi(grid)
        self.assertIn("38;2;1;2;3", ansi)
        self.assertIn("\x1b[0m", ansi)

    def test_gradient_outline_and_shadow(self) -> None:
        row = [Cell("X") for _ in range(5)]
        painted = gradient(Grid([row]), resolve_palette("rainbow"), "horizontal")
        self.assertNotEqual(painted.rows[0][0].fg, painted.rows[0][-1].fg)
        rimmed = outline(Grid([[Cell("#")]]), "#", Color(1, 2, 3))
        self.assertEqual((rimmed.width, rimmed.height), (3, 3))
        self.assertEqual(rimmed.get(1, 1).char, "#")
        self.assertEqual(rimmed.get(0, 0).char, "#")
        self.assertEqual(rimmed.get(0, 0).fg, Color(1, 2, 3))
        shadowed = drop_shadow(Grid([[Cell("A")]]), 1, 1, Color(9, 9, 9))
        self.assertEqual(shadowed.get(0, 0).char, "A")
        self.assertEqual(shadowed.get(1, 1).char, "A")
        self.assertEqual(shadowed.get(1, 1).fg, Color(9, 9, 9))
        self.assertTrue(is_ink(shadowed.get(1, 1)))
        contour = outline(Grid([[Cell("#")]]), mode="contour")
        self.assertEqual(
            ["".join(cell.char for cell in row) for row in contour.rows],
            ["╭─╮", "│#│", "╰─╯"],
        )
        thick = outline(Grid([[Cell("#")]]), mode="thick")
        self.assertEqual((thick.width, thick.height), (5, 5))
        graded = outline(Grid([[Cell("X") for _ in range(5)]]), stops=resolve_palette("rainbow"))
        self.assertNotEqual(graded.get(0, 0).fg, graded.get(graded.width - 1, 0).fg)
        still = apply_style(Grid([[Cell("X") for _ in range(6)]]), BannerStyle(gradient="rainbow"), phase=0)
        moved = apply_style(Grid([[Cell("X") for _ in range(6)]]), BannerStyle(gradient="rainbow"), phase=0.4)
        self.assertNotEqual(still.get(0, 0).fg, moved.get(0, 0).fg)


class TdfTests(unittest.TestCase):
    def test_color_block_outline_and_a_second_font(self) -> None:
        color = _font_body(
            "Color",
            2,
            0,
            {"A": bytes([2, 2, ord("A"), 0x0C, ord("B"), 0x0A, 0x0D, ord("C"), 0x0E, ord("D"), 0x0F, 0x00])},
        )
        block = _font_body(
            "Block",
            1,
            1,
            {"!": bytes([2, 1, ord("["), ord("]"), 0x00])},
        )
        outline_glyph = bytes(
            [
                4,
                2,
                ord("E"),
                ord("A"),
                ord("A"),
                ord("F"),
                0x0D,
                ord("C"),
                ord("O"),
                ord("O"),
                ord("D"),
                0x0D,
                ord("K"),
                ord("B"),
                ord("B"),
                ord("L"),
                ord("&"),
                0x00,
            ]
        )
        outline = _font_body("Line", 0, 0, {"!": outline_glyph})
        fonts = parse_tdf(_bundle(color, block))
        self.assertEqual([font.name for font in fonts], ["Color", "Block"])
        grid, missing, folded = render_font(fonts[0], "a")
        self.assertEqual(to_plain(grid), "AB\nCD\n")
        self.assertTrue(folded)
        self.assertEqual(missing, ())
        self.assertEqual(grid.get(0, 0).fg, Color(*VGA[0x0C]))
        self.assertEqual(grid.get(0, 0).fg_slot, 0x0C)
        self.assertEqual(grid.get(1, 0).fg_slot, 0x0A)

        lined = parse_tdf(_bundle(outline))[0]
        picture = to_plain(render_font(lined, "!")[0])
        self.assertEqual(picture.splitlines(), ["╒══╗", "│  ║", "└──╜"])

        spaced, _, _ = render_font(fonts[1], "! !")
        # "!" is 2 wide, the word space uses that width, and letter-spacing is 1.
        self.assertEqual(to_plain(spaced).splitlines(), ["[]    []"])

    def test_real_font_directory_if_present(self) -> None:
        root = Path.home() / ".config" / "tdfgo" / "fonts"
        if not root.is_dir():
            self.skipTest("no TheDraw font directory")
        sample = root / "1911.TDF"
        if not sample.exists():
            sample = next(path for path in root.iterdir() if path.suffix.lower() == ".tdf")
        fonts = parse_tdf(sample.read_bytes(), source=str(sample))
        self.assertGreaterEqual(len(fonts), 1)
        grid, _missing, _folded = render_font(fonts[0], "HI")
        ink = any(cell.char not in ("", " ") for row in grid.rows for cell in row)
        self.assertTrue(ink, to_plain(grid))


class RelationTests(unittest.TestCase):
    def test_hue_rotation_keeps_the_gap_between_red_and_blue(self) -> None:
        red = Color(*VGA[4])
        blue = Color(*VGA[1])
        gap = hue_delta(red, blue)
        turned_red = rotate_hue(red, 40)
        turned_blue = rotate_hue(blue, 40)
        self.assertAlmostEqual(hue_delta(turned_red, turned_blue), gap, places=4)
        self.assertNotEqual(turned_red, red)
        self.assertEqual(rotate_hue(Color(*VGA[0]), 90), Color(*VGA[0]))
        self.assertEqual(rotate_hue(Color(*VGA[15]), 90), Color(*VGA[15]))

    def test_unlinking_one_role_leaves_the_other_in_the_group(self) -> None:
        grid = Grid(
            [[Cell("R", fg_slot=4), Cell("B", fg_slot=1), Cell("R", fg_slot=4)]]
        )
        palette = RelationPalette()
        palette.ensure(grid)
        palette.break_role(4)
        palette.set_hsv(4, 120, 1, 1)
        palette.hue = 40
        painted = paint(grid, palette)
        self.assertEqual(painted.get(0, 0).fg, painted.get(2, 0).fg)
        self.assertNotEqual(painted.get(0, 0).fg, rotate_hue(Color(*VGA[4]), 40))
        self.assertEqual(painted.get(1, 0).fg, rotate_hue(Color(*VGA[1]), 40))
        self.assertEqual(grid.get(0, 0).fg_slot, 4)

    def test_split_sections_can_then_be_edited_apart(self) -> None:
        grid = Grid(
            [
                [Cell("A", fg_slot=4), Cell("A", fg_slot=4)],
                [Cell(), Cell()],
                [Cell("B", fg_slot=4), Cell()],
            ]
        )
        palette = RelationPalette()
        palette.ensure(grid)
        made = palette.split(grid, 4)
        self.assertEqual(made, 1)
        self.assertEqual(len(set(used_slots(grid))), 2)
        new_slot = grid.get(0, 2).fg_slot
        assert new_slot is not None and new_slot != 4
        palette.set_hsv(new_slot, 200, 1, 1)
        painted = paint(grid, palette)
        self.assertNotEqual(painted.get(0, 0).fg, painted.get(0, 2).fg)
        self.assertEqual(painted.get(0, 0).fg, painted.get(1, 0).fg)

    def test_json_keeps_the_roles(self) -> None:
        from meowtext.export import export, grid_from_json
        import json

        grid = Grid([[Cell("R", Color(*VGA[4]), fg_slot=4)]])
        palette = RelationPalette(hue=15)
        palette.ensure(grid)
        grid.palette = palette
        restored = grid_from_json(json.loads(export(grid, "json")))
        self.assertEqual(restored.get(0, 0).fg_slot, 4)
        assert isinstance(restored.palette, RelationPalette)
        self.assertEqual(restored.palette.hue, 15)
        self.assertEqual(restored.palette.roles[4].name, "red")

    def test_role_place_tells_ink_from_background(self) -> None:
        grid = Grid(
            [
                [Cell("A", fg_slot=4), Cell("A", fg_slot=4)],
                [Cell(" ", bg_slot=3), Cell()],
            ]
        )
        self.assertEqual(role_place(grid, 4), (1, "ink"))
        self.assertEqual(role_place(grid, 3), (1, "background"))


class ToolTests(unittest.TestCase):
    def test_figlet_and_toilet(self) -> None:
        from meowtext.compose import render_banner
        from meowtext.effects import BannerStyle

        banner = render_banner("Hi", "figlet", "small", BannerStyle(gradient="mono"))
        self.assertGreater(banner.grid.width, 1)
        self.assertTrue(any(cell.fg is not None for row in banner.grid.rows for cell in row))
        toilet = render_banner("Hi", "toilet", "future")
        self.assertGreater(toilet.grid.height, 1)
        png = export(banner.grid, "png")
        self.assertIsInstance(png, bytes)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn("\x1b_G", export(banner.grid, "kitty"))
        self.assertIn("<span", export(banner.grid, "html"))


if __name__ == "__main__":
    unittest.main()
