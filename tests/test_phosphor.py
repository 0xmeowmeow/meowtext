"""Phosphor is one ink on black, and the review page only shows that set."""

from __future__ import annotations

import unittest

from meowtext.phosphor import HELD, SOURCES, page, phosphor_panel, view_from_query


class PhosphorTests(unittest.TestCase):
    def test_the_panel_is_one_green_on_black(self) -> None:
        image = phosphor_panel()
        colours = image.getcolors(image.width * image.height)
        assert colours is not None
        inked = 0
        for count, colour in colours:
            red, green, blue = colour
            if red + green + blue < 24:
                continue
            inked += count
            self.assertGreaterEqual(green + 12, red)
            self.assertGreaterEqual(green + 12, blue)
        self.assertGreater(inked, 1000)

    def test_page_lists_the_pictures_and_holds_the_rest(self) -> None:
        html = page()
        self.assertIn("Phosphor", html)
        self.assertIn("Gene code", html)
        self.assertIn("/panel.png", html)
        self.assertEqual(len(SOURCES), 6)
        self.assertIn("Access node", html)
        self.assertGreater(len(HELD), 0)
        for source in SOURCES:
            self.assertTrue(source.path.endswith((".jpg", ".png", ".webp")))
        self.assertIn("Border on the wave", html)
        self.assertIn("Hack", html)
        self.assertIn("Side by side", html)

    def test_the_view_can_change_border_font_scale_and_texture(self) -> None:
        plain = phosphor_panel()
        self.assertNotEqual(_sample(plain), _sample(phosphor_panel(border=True)))
        self.assertNotEqual(_sample(plain), _sample(phosphor_panel(texture="graph")))
        self.assertNotEqual(_sample(plain), _sample(phosphor_panel(texture="plus")))
        self.assertNotEqual(_sample(plain), _sample(phosphor_panel(font="hack")))
        self.assertNotEqual(_sample(plain), _sample(phosphor_panel(glow="none")))
        self.assertEqual(phosphor_panel(scale="sharp").size, (plain.width * 2, plain.height * 2))
        self.assertEqual(phosphor_panel(scale="low").size, (plain.width // 2, plain.height // 2))
        view = view_from_query({"border": ["1"], "font": ["nope"], "scale": ["huge"], "texture": ["sparkle"], "slot": ["nope"]})
        self.assertTrue(view.border)
        self.assertEqual(view.font, "dejavu")
        self.assertEqual(view.scale, "screen")
        self.assertEqual(view.texture, "none")
        self.assertEqual(view.slot, "whole")

    def test_a_split_slot_keeps_the_page_ratio(self) -> None:
        whole = phosphor_panel()
        side = phosphor_panel(slot="half-width")
        stacked = phosphor_panel(slot="half-height")
        quarter = phosphor_panel(slot="quarter")
        self.assertEqual(side.size, (whole.width // 2, whole.height))
        self.assertEqual(stacked.size, (whole.width, whole.height // 2))
        self.assertEqual(quarter.size, (whole.width // 2, whole.height // 2))
        ratio = _ink_ratio(whole)
        for image in (side, stacked, quarter):
            self.assertAlmostEqual(_ink_ratio(image), ratio, delta=0.03)
        narrow = phosphor_panel(width=220, height=700)
        wide = phosphor_panel(width=900, height=160)
        self.assertEqual(narrow.size, (220, 700))
        self.assertEqual(wide.size, (900, 160))
        self.assertAlmostEqual(_ink_ratio(narrow), ratio, delta=0.04)
        self.assertAlmostEqual(_ink_ratio(wide), ratio, delta=0.04)


def _ink_ratio(image) -> float:
    pixels = image.load()
    min_x, min_y = image.width, image.height
    max_x = max_y = 0
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = pixels[x, y]
            if red + green + blue <= 24:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    return (max_x - min_x + 1) / (max_y - min_y + 1)


def _sample(image) -> bytes:
    return image.tobytes()[::200]


if __name__ == "__main__":
    unittest.main()
