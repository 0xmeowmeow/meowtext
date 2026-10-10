"""Headless check that the editor draws a banner and can save it."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input

from meowtext.board import Board
from meowtext.project import load_project, project_filename
from meowtext.tui import MeowText


class TuiTests(unittest.TestCase):
    def _on_screen(self, app: MeowText, width: int, height: int) -> None:
        stage = app.query_one("#stage")
        fonts = app.query_one("#fonts")
        inspector = app.query_one("#inspector")
        self.assertEqual(stage.region.width, width)
        self.assertGreater(stage.region.y, fonts.region.y)
        self.assertGreaterEqual(inspector.region.y, stage.region.bottom)
        self.assertFalse(app.query_one("#filter").display)
        for widget in (
            app.query_one("#text"),
            app.query_one("#export"),
            app.query_one("#copy"),
            app.query_one("#open"),
            inspector,
            fonts,
        ):
            self.assertGreaterEqual(widget.region.y, 0, widget.id)
            self.assertLessEqual(widget.region.bottom, height, widget.id)
            self.assertLessEqual(widget.region.right, width, widget.id)

    def test_preview_and_save(self) -> None:
        app = MeowText()

        async def drive() -> None:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self._on_screen(app, 120, 40)
                self.assertIsNotNone(app.last_banner)
                assert app.last_banner is not None
                self.assertGreater(app.last_banner.grid.width, 0)
                placed = app.query_one("#preview").content.plain.splitlines()
                content = [index for index, line in enumerate(placed) if line.strip()]
                self.assertTrue(content)
                view = app.query_one("#stage-scroll")
                lead = len(placed[content[0]]) - len(placed[content[0]].lstrip(" "))
                self.assertEqual(lead, max(0, (view.size.width - app.last_banner.grid.width) // 2))
                self.assertEqual(content[0], max(0, (view.size.height - app.last_banner.grid.height) // 2))
                self.assertTrue(
                    any(cell.fg is not None for row in app.last_banner.grid.rows for cell in row)
                )
                app._apply_preset("stamp")
                style = app._style()
                self.assertTrue(style.outline and style.shadow)
                self.assertIsNone(style.gradient)
                app.query_one("#text", Input).value = "Hi"
                app._render_preview()
                self.assertTrue(
                    any(cell.char not in ("", " ") for row in app.last_banner.grid.rows for cell in row)
                )
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "banner.ans"
                    app.query_one("#path", Input).value = str(path)
                    app.knobs["format"] = "ansi"
                    app.action_export()
                    data = path.read_bytes()
                self.assertIn(b"\x1b[", data)
                app.action_copy()
                self.assertIn("\x1b[", app._clipboard)
                board = app.query_one("#inspector", Board)
                board.focus()
                await pilot.press("ctrl+right")
                self.assertEqual(app._section, "outline")
                self.assertLessEqual(board.region.right, 120)
                await pilot.press("D")
                self.assertEqual(app._style().outline_direction, "opposite")
                await pilot.press("m")
                self.assertEqual(app._style().outline_mode, "thick")
                await pilot.press("1")
                self.assertEqual(app._section, "look")
                await pilot.press("g")
                await pilot.press("d")
                self.assertEqual(app.knobs["gradient"], "on")
                self.assertEqual(app._style().direction, "horizontal-back")
                direction = next(index for index, knob in enumerate(board.rows) if knob.id == "direction")
                self.assertEqual(board.index, direction)
                await pilot.press("down")
                self.assertEqual(board.rows[board.index].id, "format")
                await pilot.press("left")
                self.assertEqual(board.rows[board.index].id, "engine")
                await pilot.press("]")
                self.assertEqual(app._section, "outline")
                await pilot.press("1")
                app.query_one("#text", Input).focus()
                previous_font = app.font_id
                await pilot.press("ctrl+f")
                self.assertTrue(app.query_one("#filter").display)
                self.assertIs(app.focused, app.query_one("#filter", Input))
                await pilot.press("down")
                self.assertNotEqual(app.font_id, previous_font)
                await pilot.press("enter")
                self.assertFalse(app.query_one("#filter").display)
                self.assertIsInstance(app.focused, Board)
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                self._on_screen(app, 80, 24)
                await pilot.resize_terminal(120, 40)
                await pilot.pause()
                app.knobs["outline"] = "on"
                app._render_preview()
                self.assertTrue(app._style().outline)
                app.action_paint()
                await pilot.press("x")
                self.assertTrue(app._patches)
                with tempfile.TemporaryDirectory() as tmp:
                    previous = os.getcwd()
                    os.chdir(tmp)
                    try:
                        font = app.last_banner.font.name if app.last_banner else "font"
                        planted = Path(tmp) / project_filename("Hi", font)
                        planted.write_text("keep", encoding="utf-8")
                        app.action_project()
                        self.assertEqual(planted.read_text(encoding="utf-8"), "keep")
                        saved = [path for path in Path(tmp).glob("*.meowtext") if path != planted]
                        self.assertEqual(len(saved), 1)
                        self.assertEqual(load_project(saved[0]).text, "Hi")
                        self.assertEqual(load_project(saved[0]).notes, "")
                    finally:
                        os.chdir(previous)

        asyncio.run(drive())


if __name__ == "__main__":
    unittest.main()
