"""Headless check that the editor draws a banner and can save it."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, Select

from meowtext.tui import MeowText


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
                    app.query_one("#format", Select).value = "ansi"
                    app.action_save()
                    data = path.read_bytes()
                self.assertIn(b"\x1b[", data)
                app.action_copy()
                self.assertIn("\x1b[", app._clipboard)

        asyncio.run(drive())


if __name__ == "__main__":
    unittest.main()
