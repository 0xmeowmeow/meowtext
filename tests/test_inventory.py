"""Regressions from the screenshot review: geometry, discovery and keyboard feel."""

import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from textual.widgets import Input
from meowtext.catalog import FontInfo
from meowtext.choices import Choices
from meowtext.discovery import Discovery, starter_index
from meowtext.grid import Cell, Color, Grid
from meowtext.inventory import Inventory, FontCard
from meowtext.raster import rasterize, fit_image
from meowtext.studio import MeowText


class GeometryTests(unittest.TestCase):
    def test_blocks_are_exact_fractions_and_neighbours_do_not_overpaint(self):
        red, blue = Color(255, 0, 0), Color(0, 0, 255)
        g = Grid(
            [[Cell("▀", red), Cell("▄", red), Cell("█", red, blue), Cell(" ", bg=blue)]]
        )
        image = rasterize(g)
        w, h = image.width // 4, image.height
        for x in range(w):
            for y in range(h):
                self.assertEqual(
                    image.getpixel((x, y)), (255, 0, 0) if y < h // 2 else (0, 0, 0)
                )
                self.assertEqual(
                    image.getpixel((w + x, y)),
                    (255, 0, 0) if y >= h // 2 else (0, 0, 0),
                )
                self.assertEqual(image.getpixel((2 * w + x, y)), (255, 0, 0))
                self.assertEqual(image.getpixel((3 * w + x, y)), (0, 0, 255))

    def test_fit_constrains_both_axes_and_preserves_terminal_cell_aspect(self):
        for width, height in ((100, 3), (20, 40), (38, 6), (1, 1)):
            grid = Grid(
                [
                    [Cell("█", Color(255, 255, 255)) for _ in range(width)]
                    for _ in range(height)
                ]
            )
            for available in ((40, 5), (18, 11), (1, 1)):
                image, cols, rows = fit_image(grid, *available, cell_size=(10, 20))
                self.assertLessEqual(cols, available[0])
                self.assertLessEqual(rows, available[1])
                self.assertEqual(image.size, (cols * 10, rows * 20))
                mask = image.convert("L").point(lambda x: 255 if x > 80 else 0)
                box = mask.getbbox()
                self.assertIsNotNone(box)
                actual_w, actual_h = box[2] - box[0], box[3] - box[1]
                scale = min(1, available[0] / width, available[1] / height)
                self.assertLessEqual(abs(actual_w - width * 10 * scale), 1.1)
                self.assertLessEqual(abs(actual_h - height * 20 * scale), 1.1)


class DiscoveryInventoryTests(unittest.TestCase):
    def test_copies_and_colour_variants_leave_room_for_different_shapes(self):
        items = starter_index()
        copies = []
        for item in items:
            for index in range(4):
                features = list(item.features)
                features[5] = float(index % 2)
                features[2] += index * 0.001
                copies.append(
                    replace(
                        item,
                        font=replace(
                            item.font, source=f"/copy-{index}/{item.font.name}"
                        ),
                        features=tuple(features),
                    )
                )
        discovery = Discovery(copies + items, count=9)
        for _ in range(5):
            self.assertEqual(len(discovery.choices), 9)
            self.assertEqual(len({i.font.name for i in discovery.choices}), 9)
            discovery.narrow(1)

    def test_gothic_synonyms_and_exploration_never_collapse_into_one_tile(self):
        items = starter_index()
        gothic = next((i for i in items if "Gothic" in i.categories), None)
        if gothic is None:
            # Family-name search is independent of optional font packs.
            gothic = replace(
                items[0],
                font=FontInfo("figlet", "Gothic", "/gothic-fixture"),
                categories=("All", "Gothic"),
            )
            items.append(gothic)
        d = Discovery(items)
        for query in ("gothic", "blackletter", "fraktur", "medieval", "old english"):
            d.reset(query=query)
            self.assertIn(gothic, d.pool)
            self.assertEqual(len(d.choices), 6)
            self.assertTrue(d.explorers)
            for _ in range(5):
                d.narrow(0)
                self.assertEqual(len(d.choices), 6)
                self.assertEqual(len(set(i.font.id for i in d.choices)), 6)


class KeyboardInventoryTests(unittest.TestCase):
    def test_tab_arrows_tune_undo_and_small_terminal(self):
        async def drive():
            app = MeowText(index=starter_index())
            async with app.run_test(size=(150, 46)) as pilot:
                await pilot.pause(0.25)
                app.query_one("#font-tile-0", FontCard).focus()
                await pilot.press("right")
                self.assertEqual(app.focused.id, "font-tile-1")
                await pilot.press("i")
                await pilot.pause()
                self.assertEqual(app.screen.banner.font, app.discovery.choices[1].font)
                # Background rendering/indexing can finish during inspection.
                app._gallery_result(
                    app._gallery_generation, 0, app.last_banner.grid, None
                )
                app._index_status(11, 11)
                app._indexed(starter_index())
                await pilot.pause(0.2)
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(app.focused.id, "font-tile-1")
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(len(app.discovery.choices), 9)
                self.assertEqual(app.focused.id, "font-tile-0")
                await pilot.press("space")
                await pilot.pause()
                self.assertEqual(app.query_one("#sections").active, "adjust")
                self.assertEqual(app.focused.id, "look-inventory")
                await pilot.press("tab")
                self.assertEqual(app.focused.id, "edge-inventory")
                await pilot.press("home", "right")
                await pilot.pause()
                self.assertTrue(app.project.style.outline)
                self.assertEqual(app.project.style.outline_mode, "shade")
                await pilot.press("tab", "right")
                await pilot.pause()
                self.assertEqual(app.focused.id, "motion-inventory")
                self.assertEqual(app.project.animation.name, "hue")
                self.assertTrue(app.playing)
                await pilot.press("ctrl+z")
                await pilot.pause()
                self.assertEqual(app.project.animation.name, "none")
                await pilot.press("enter")
                await pilot.pause()
                self.assertTrue(app.query_one("#motion-details").display)
                self.assertEqual(app.focused.id, "motion")
                await pilot.press("right")
                await pilot.pause()
                self.assertEqual(app.project.animation.name, "hue")
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(app.focused.id, "motion-inventory")
                await pilot.press("shift+tab")
                self.assertEqual(app.focused.id, "edge-inventory")
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                for name in ("fill", "outline", "motion"):
                    bank = app.query_one(f"#{name}-pane")
                    self.assertLessEqual(bank.region.right, 80)
                    self.assertGreater(bank.region.width, 20)
                await pilot.press("tab", "end")
                await pilot.pause()
                self.assertEqual(app.project.animation.name, "trace")
                self.assertGreater(app.query_one("#motion-inventory").scroll_y, 0)
                self.assertIn(
                    "Trace", app.query_one("#motion-inventory").render_line(0).text
                )

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())

    def test_every_palette_option_is_visible_and_mouse_applies_without_enter(self):
        async def drive():
            app = MeowText(index=starter_index())
            async with app.run_test(size=(150, 46)) as pilot:
                await pilot.pause()
                await pilot.press("f3", "enter")
                await pilot.pause()
                app.query_one("#fill", Choices).focus()
                await pilot.press("right")
                await pilot.pause()
                palette = app.query_one("#palette", Choices)
                self.assertGreaterEqual(palette.size.height, 2)
                palette.focus()
                await pilot.press("end")
                await pilot.pause()
                self.assertTrue(app.query_one("#stops-field").display)
                app.query_one("#fill", Choices).focus()
                await pilot.press("home")
                await pilot.pause()
                colours = app.query_one("#solid-name", Choices)
                colours.focus()
                await pilot.press("home")
                await pilot.pause()
                await pilot.click("#solid-name", offset=(2, 1))
                await pilot.pause()
                self.assertNotEqual(colours.value, "slate")

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())
