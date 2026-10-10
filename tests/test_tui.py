"""Headless check that the editor draws a banner and can save it."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, Switch

from meowtext.project import load_project, project_filename
from meowtext.tui import MeowText
from meowtext.widgets import Cycle


class TuiTests(unittest.TestCase):
    def test_preview_and_save(self) -> None:
        app = MeowText()

        async def drive() -> None:
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertIsNotNone(app.last_banner)
                assert app.last_banner is not None
                self.assertGreater(app.last_banner.grid.width, 0)
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
                    app.query_one("#format", Cycle).set_value("ansi")
                    app.action_export()
                    data = path.read_bytes()
                self.assertIn(b"\x1b[", data)
                app.action_copy()
                self.assertIn("\x1b[", app._clipboard)
                await pilot.press("ctrl+right")
                self.assertEqual(app._section, "outline")
                app.query_one("#outline", Switch).value = True
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
