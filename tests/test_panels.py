"""Panels fit a picture without stretching, then keep one green."""

from __future__ import annotations

import unittest

from PIL import Image

import math

from meowtext.panels import (
    BASES_PER_TURN,
    cover,
    helix_rungs,
    render_data,
    render_equalizer,
    render_helix,
    render_image,
    render_selector,
    render_svg,
)


class PanelTests(unittest.TestCase):
    def test_cover_fills_the_panel_without_stretching(self) -> None:
        wide = Image.new("RGB", (100, 40), (200, 10, 10))
        middle = Image.new("RGB", (20, 40), (10, 10, 200))
        wide.paste(middle, (40, 0))
        fitted = cover(wide, 40, 40)
        self.assertEqual(fitted.size, (40, 40))
        red, green, blue = fitted.getpixel((20, 20))
        self.assertGreater(blue, red)

    def test_greenscale_levels_negative_and_dither(self) -> None:
        source = self._picture()
        plain = render_image(source, 40, 30)
        self.assertEqual(plain.size, (40, 30))
        self.assertTrue(_green(plain))
        negative = render_image(source, 40, 30, negative=True)
        self.assertGreater(_mean(plain), _mean(negative))
        render_image(source, 40, 30, auto_levels=True)
        dithered = render_image(source, 40, 30, dither=True)
        colours = {pixel for pixel in dithered.getdata()}
        self.assertLessEqual(len(colours), 2)
        empty = render_image(None, 40, 30)
        self.assertEqual(empty.size, (40, 30))

    def test_helix_is_a_right_handed_turn_of_ten(self) -> None:
        sequence = "ATGCGTACGA" * 2
        rungs = helix_rungs(sequence)
        self.assertEqual(len(rungs), 20)
        self.assertEqual(BASES_PER_TURN, 10)
        self.assertAlmostEqual(rungs[1]["theta"] - rungs[0]["theta"], math.tau / 10)
        self.assertAlmostEqual(rungs[10]["theta"] - rungs[0]["theta"], math.tau)
        self.assertGreater(rungs[1]["z"], rungs[0]["z"])
        self.assertEqual(rungs[0]["pair"], "T")
        self.assertEqual(rungs[2]["pair"], "C")
        self.assertNotEqual(render_helix(80, 160, 0, bases=sequence).tobytes(), render_helix(80, 160, 0.5, bases=sequence).tobytes())
        for mode in ("glyphs", "cells", "array", "dial", "gauge"):
            self.assertEqual(render_data([0.2, 0.8], mode, 60, 40).size, (60, 40))

    def test_selector_and_equalizer(self) -> None:
        first = render_selector(("A", "B", "C", "D"), 0, 80, 60)
        third = render_selector(("A", "B", "C", "D"), 2, 80, 60)
        self.assertNotEqual(first.tobytes(), third.tobytes())
        quiet = render_equalizer([0.1] * 8, 80, 40)
        loud = render_equalizer([0.9] * 8, 80, 40)
        self.assertGreater(_mean(loud), _mean(quiet))

    def test_svg_crop_fits_the_panel(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#fff"/></svg>'
        image = render_svg(svg, 32, 24, crop=(0.25, 0.25, 0.75, 0.75))
        self.assertEqual(image.size, (32, 24))
        self.assertTrue(_green(image))

    def _picture(self) -> str:
        path = "/tmp/phosphor-panel-source.png"
        image = Image.new("RGB", (60, 30), (230, 230, 230))
        image.save(path)
        return path


def _mean(image) -> float:
    values = [sum(pixel) for pixel in image.getdata()]
    return sum(values) / len(values)


def _green(image) -> bool:
    for red, green, blue in image.getdata():
        if red + green + blue < 24:
            continue
        if green <= red or green <= blue:
            return False
    return True


if __name__ == "__main__":
    unittest.main()
