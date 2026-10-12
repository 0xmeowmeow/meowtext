"""User journeys and boundaries for the Kitty-first release."""

import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, Select, Checkbox, Button

from meowtext import library
from meowtext.__main__ import main
from meowtext.catalog import resolve
from meowtext.discovery import (
    Discovery,
    describe,
    representatives,
    starter_index,
    font_key,
)
from meowtext.compose import layout_font
from meowtext.effects import PRESETS, BannerStyle, apply_style
from meowtext.errors import RenderError
from meowtext.export import to_plain, to_markdown
from meowtext.grid import Cell, Color, Grid
from meowtext.integration import kitty_session
from meowtext.project import Project, save_project
from meowtext.studio import MeowText
from meowtext.choices import Choices


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.environment = patch.dict(os.environ, {"MEOWTEXT_HOME": self.tmp.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.project = Project(
            text="Hello", font_name="standard", style=PRESETS["cyan"].clone()
        )

    def test_saved_artwork_survives_missing_font_and_reopens_recipe(self):
        original = library.render_project(self.project).grid
        library.save("hello", self.project, grid=original)
        with patch(
            "meowtext.library.project_font", side_effect=RenderError("font gone")
        ):
            self.assertEqual(to_plain(library.artwork("hello")), to_plain(original))
        loaded = library.load("hello")
        self.assertEqual(loaded.text, "Hello")
        self.assertNotEqual(
            to_plain(library.render_project(loaded, "Bye").grid), to_plain(original)
        )
        self.assertEqual(loaded.text, "Hello")
        with self.assertRaises(RenderError):
            library.save("hello", self.project)
        library.save("hello", Project(text="Bye", font_name="standard"), replace=True)
        self.assertEqual(library.load("hello").text, "Bye")

    def test_validation_and_broken_library(self):
        for name in ("../escape", "x/y", "name with spaces", "$(whoami)", ""):
            with self.assertRaises(RenderError):
                library.save(name, self.project)
        with self.assertRaises(RenderError):
            library.load("missing")
        root = library.library_dir()
        root.mkdir(exist_ok=True)
        (root / "broken.json").write_text("{")
        with self.assertRaises(RenderError):
            library.artwork("broken")

    def test_cli_save_show_and_markdown(self):
        project = Path(self.tmp.name) / "original.meowtext"
        save_project(project, self.project)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["save", "test", str(project)]), 0)
        output = Path(self.tmp.name) / "banner.md"
        self.assertEqual(
            main(["show", "test", "--format", "markdown", "-o", str(output)]), 0
        )
        self.assertTrue(output.read_text().startswith("```text\n"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["show", "absent"]), 1)

    def test_wrapper_preserves_streams_arguments_stdin_and_exit_status(self):
        library.save("hello", self.project)
        command = [
            sys.executable,
            "-m",
            "meowtext",
            "run",
            "hello",
            "--",
            sys.executable,
            "-c",
            "import sys; print(sys.stdin.read()); print(sys.argv[1]); sys.exit(7)",
            "$x; spaces",
        ]
        result = subprocess.run(
            command, input="pipeline data", text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "pipeline data\n$x; spaces\n")
        self.assertIn("\x1b[", result.stderr)
        self.assertNotIn("\x1b[", result.stdout)
        after = subprocess.run(
            [
                sys.executable,
                "-m",
                "meowtext",
                "run",
                "hello",
                "--after",
                "--",
                sys.executable,
                "-c",
                "import sys;sys.stderr.write('first\\n');sys.exit(3)",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(after.returncode, 3)
        self.assertTrue(after.stderr.startswith("first\n\x1b["))

    def test_shell_script_is_valid_zsh_idempotent_and_kitty_scoped(self):
        library.save("hello", self.project)
        library.bind("ll", "hello")
        source = library.shell_script("zsh", "hello")
        script = Path(self.tmp.name) / "integration.zsh"
        script.write_text(source)
        subprocess.run(["zsh", "-n", str(script)], check=True, capture_output=True)
        result = subprocess.run(
            [
                "zsh",
                "-f",
                "-c",
                'source "$1"; source "$1"; print -l $preexec_functions; meowtext-off; print count=${#preexec_functions}',
                "zsh",
                str(script),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "_meowtext_preexec\ncount=0\n")
        with self.assertRaises(RenderError):
            library.bind("git; echo hacked", "hello")
        library.bind("ll", None)
        self.assertEqual(library.bindings(), {})
        self.assertIn("KITTY_WINDOW_ID", source)

    def test_favourites_and_kitty_session(self):
        font = resolve("figlet", "standard")
        self.assertTrue(library.toggle_favourite(font))
        self.assertIn(font_key(font), library.favourites())
        self.assertFalse(library.toggle_favourite(font))
        self.assertNotIn(font_key(font), library.favourites())
        session = kitty_session("hello", ["printf", "word with spaces"])
        self.assertIn("--location=hsplit --bias=78", session)
        self.assertIn("'word with spaces'", session)
        with self.assertRaises(RenderError):
            kitty_session("hello", ["echo", "\nlaunch evil"])


class DiscoveryTests(unittest.TestCase):
    def test_exploration_keeps_full_rounds_and_back_restores_exact_choices(self):
        items = starter_index()
        start = Discovery(items, count=6)
        original = [i.font.id for i in start.choices]
        for step in range(12):
            start.narrow(step % 6)
            self.assertEqual(len(start.choices), 6)
            self.assertEqual(len({i.font.id for i in start.choices}), 6)
            self.assertEqual(
                {i.font.id for i in start.scope}, {i.font.id for i in items}
            )
        for step in range(12):
            start.back()
        self.assertEqual([i.font.id for i in start.choices], original)
        start.reset(query="no-such-font")
        self.assertEqual(start.choices, [])

    def test_solid_colours_replace_roles_and_markdown_fences_are_safe(self):
        grid = Grid([[Cell("X", Color(255, 0, 0), fg_slot=1)]])
        out = apply_style(grid, PRESETS["cyan"])
        self.assertEqual(out.get(0, 0).fg, Color(101, 232, 237))
        self.assertEqual(grid.get(0, 0).fg, Color(255, 0, 0))
        self.assertTrue(to_markdown(Grid([[Cell("`")] * 4])).startswith("`````text\n"))


class StudioTests(unittest.TestCase):
    def test_compare_to_saved_command_and_small_terminal(self):
        async def drive(tmp):
            index = starter_index()
            app = MeowText(index=index)
            async with app.run_test(size=(140, 48)) as pilot:
                await pilot.pause(0.4)
                self.assertIsNotNone(app.last_banner)
                self.assertIsNone(app.project.style.gradient)
                self.assertEqual(app.project.style.stops, PRESETS["cyan"].stops)
                initial = len(app.discovery.pool)
                await pilot.click("#like-0")
                await pilot.pause()
                self.assertEqual(len(app.discovery.history), 1)
                self.assertEqual(len(app.discovery.choices), app.discovery.count)
                await pilot.click("#font-back")
                await pilot.pause()
                self.assertEqual(len(app.discovery.pool), initial)
                await pilot.click("#star-0")
                await pilot.pause()
                self.assertIn(
                    font_key(app.discovery.choices[0].font), library.favourites()
                )
                await pilot.press("f3")
                await pilot.pause()
                self.assertTrue(app.query_one("#solid-field").display)
                self.assertFalse(app.query_one("#gradient-settings").display)
                app.query_one("#fill", Choices).value = "gradient"
                await pilot.pause()
                self.assertTrue(app.query_one("#gradient-settings").display)
                self.assertFalse(app.query_one("#solid-field").display)
                app.query_one("#readable-gradients", Checkbox).value = False
                await pilot.pause()
                self.assertFalse(app.project.style.readable_gradients)
                app.query_one("#readable-gradients", Checkbox).value = True
                await pilot.pause()
                self.assertTrue(app.project.style.readable_gradients)
                app.query_one("#outline-mode", Choices).value = "shade"
                await pilot.pause()
                self.assertTrue(app.query_one("#outline-settings").display)
                app.action_save_tab()
                await pilot.pause()
                app.query_one("#save-name", Input).value = "test-design"
                await pilot.click("#save-design")
                await pilot.pause()
                self.assertIn("test-design", library.entries())
                self.assertEqual(app.usage_command, "meowtext show test-design")
                await pilot.click("#copy-command")
                self.assertEqual(app._clipboard, "meowtext show test-design")
                app.query_one("#use-mode", Select).value = "after"
                await pilot.pause()
                self.assertIn("--after -- ls", app.usage_command)
                app.action_fonts()
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                self.assertFalse(app.query_one("#sidebar").display)
                self.assertLessEqual(app.query_one("#sections").region.right, 80)
                app.action_inspect()
                await pilot.pause()
                await pilot.press("escape")
                self.assertEqual(len(app.screen_stack), 1)

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive(tmp))


class RestoredWorkflowTests(unittest.TestCase):
    def test_names_follow_words_and_save_name_without_replacing_custom_paths(self):
        async def drive():
            app = MeowText(index=starter_index())
            async with app.run_test(size=(100, 34)) as pilot:
                await pilot.pause()
                app.query_one("#text", Input).value = "Hello Kitty!"
                await pilot.pause(0.25)
                self.assertEqual(
                    app.query_one("#save-name", Input).value, "Hello-Kitty"
                )
                self.assertEqual(
                    app.query_one("#export-path", Input).value, "Hello-Kitty.html"
                )
                app.query_one("#save-name", Input).value = "my-design"
                await pilot.pause()
                self.assertEqual(
                    app.query_one("#export-path", Input).value, "my-design.html"
                )
                app.query_one("#format", Select).value = "png"
                await pilot.pause()
                self.assertEqual(
                    app.query_one("#export-path", Input).value, "my-design.png"
                )
                app.query_one("#text", Input).value = "Changed words"
                await pilot.pause(0.25)
                self.assertEqual(app.query_one("#save-name", Input).value, "my-design")
                app.query_one("#export-path", Input).value = "/tmp/chosen-name.png"
                await pilot.pause()
                app.query_one("#save-name", Input).value = "different-design"
                await pilot.pause()
                self.assertEqual(
                    app.query_one("#export-path", Input).value, "/tmp/chosen-name.png"
                )
                app.query_one("#format", Select).value = "markdown"
                await pilot.pause()
                self.assertEqual(
                    app.query_one("#export-path", Input).value, "/tmp/chosen-name.md"
                )
                app.action_save_tab()
                await pilot.pause()
                app._save()
                await pilot.pause()
                app.query_one("#use-mode", Select).value = "markdown"
                await pilot.pause()
                self.assertIn("different-design.md", app.usage_command)
                app.query_one("#use-mode", Select).value = "watch"
                await pilot.pause()
                self.assertEqual(app.usage_command, "meowtext watch different-design")

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())

    def test_all_outline_and_motion_controls_survive_save_and_reopen(self):
        from meowtext.effects import Animation
        from meowtext.project import dumps_project

        project = Project(
            text="MEOW",
            font_name="standard",
            style=BannerStyle(
                gradient="fire",
                outline=True,
                outline_mode="double",
                outline_scope="letter",
                outline_distance=6,
                outline_place="outside",
                outline_sides="tb",
                outline_gradient="ice",
                outline_direction="opposite",
                outline_speed=2.5,
                outline_bands=True,
                outline_dx=-2,
                outline_dy=1,
                shadow=True,
                shadow_char="·",
                shadow_dx=-3,
                shadow_dy=2,
            ),
            animation=Animation(
                name="trace",
                speed=2,
                direction="pingpong",
                travel=90,
                layers="outline",
                pattern="letter",
                reveal="runner",
            ),
        )
        project.font_source = resolve("figlet", "standard").source

        async def drive():
            app = MeowText(project, index=starter_index())
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(dumps_project(app.project), dumps_project(project))
                await pilot.click("#use-font")
                await pilot.pause()
                self.assertEqual(app.query_one("#sections").active, "adjust")
                self.assertFalse(app.query_one("#sidebar").display)
                self.assertGreater(app.query_one("#decoration-preview").size.width, 100)
                self.assertTrue(app.query_one("#trace-settings").display)
                self.assertFalse(app.query_one("#motion-layers-field").display)
                app.set_focus(None)
                app._tune_bank("outline")
                await pilot.pause(0.2)
                control = app.query_one("#outline-mode", Choices)
                self.assertGreaterEqual(
                    control.parent.region.bottom, control.region.bottom
                )
                await pilot.click("#outline-mode")
                await pilot.press("home", "right")
                await pilot.pause()
                self.assertEqual(app.project.style.outline_mode, "shade")
                for key, value in [
                    ("outline-distance", "3"),
                    ("outline-mode", "contour"),
                    ("outline-scope", "word"),
                    ("motion", "march"),
                    ("motion-direction", "backward"),
                    ("motion-layers", "letters"),
                    ("motion-travel", "180"),
                ]:
                    app.query_one("#" + key, Choices).value = value
                    await pilot.pause()
                app.playing = False
                self.assertTrue(app.query_one("#motion-layers-field").display)
                self.assertFalse(app.query_one("#trace-settings").display)
                self.assertEqual(app.project.style.outline_distance, 3)
                self.assertEqual(app.project.animation.direction, "backward")
                self.assertEqual(app.project.animation.travel, 180)
                app.action_save_tab()
                await pilot.pause()
                app._save()
                await pilot.pause()
                saved = library.load("MEOW")
                self.assertEqual(
                    json.loads(dumps_project(saved)),
                    json.loads(dumps_project(app.project)),
                )
                app._open_saved("MEOW")
                await pilot.pause()
                self.assertEqual(
                    json.loads(dumps_project(saved)),
                    json.loads(dumps_project(app.project)),
                )

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())

    def test_playback_matches_original_compositor_for_every_animation(self):
        from meowtext.effects import ANIMATIONS, Animation
        from meowtext.playback import frames

        project = Project(
            text="MEOW", font_name="standard", style=PRESETS["sunset-rim"].clone()
        )
        for _, name in ANIMATIONS:
            project.animation = Animation(
                name=name,
                speed=2,
                direction="backward",
                pattern="rows",
                reveal="runner",
            )
            stream = frames(project)
            seen = []
            for number in range(5):
                frame = next(stream)
                self.assertEqual(
                    frame, library.render_project(project, frame=number).grid, name
                )
                seen.append(frame)
            if name != "none":
                self.assertTrue(any(f != seen[0] for f in seen[1:]), name)


class PaintWorkflowTests(unittest.TestCase):
    def test_cancel_undo_and_apply_keep_original_font_unchanged(self):
        from meowtext.paint_editor import PaintEditor

        async def drive():
            app = MeowText(
                Project(text="MEOW", font_name="standard"), index=starter_index()
            )
            async with app.run_test(size=(110, 36)) as pilot:
                await pilot.pause()
                original = app.last_banner.grid.copy()
                editor = PaintEditor(app.project, app.font, original)
                app.push_screen(editor, app._paint_result)
                await pilot.pause()
                editor.paint("X")
                await pilot.pause()
                self.assertEqual(app.project.patches, ())
                await pilot.click("#paint-undo")
                await pilot.pause()
                self.assertEqual(editor.grid, original)
                editor.paint("X")
                await pilot.click("#paint-cancel")
                await pilot.pause()
                self.assertEqual(app.project.patches, ())
                editor = PaintEditor(app.project, app.font, original)
                app.push_screen(editor, app._paint_result)
                await pilot.pause()
                editor.paint("X")
                await pilot.click("#paint-apply")
                await pilot.pause()
                self.assertEqual(app.last_banner.grid.get(0, 0).char, "X")
                self.assertTrue(app.project.patches)
                editor = PaintEditor(app.project, app.font, app.last_banner.grid)
                app.push_screen(editor, app._paint_result)
                await pilot.pause()
                editor.query_one("#paint-target", Select).value = "letter:M"
                await pilot.pause()
                editor.paint("Y")
                await pilot.click("#paint-apply")
                await pilot.pause()
                self.assertEqual(app.project.letters["M"].get(0, 0).char, "Y")
                self.assertNotEqual(layout_font("M", app.font)[0].get(0, 0).char, "Y")

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())


class RoleRecoveryTests(unittest.TestCase):
    def test_split_sections_and_edited_colours_survive_project_round_trip(self):
        from meowtext.project import dumps_project, project_from_dict
        from meowtext.palette import rgb_to_hsv

        source = Grid([[Cell("X", fg_slot=4), Cell(), Cell("X", fg_slot=4)]])
        project = Project(text="XX", font_name="standard", role_splits=(4,))
        first = source.copy()
        palette = library.prepare_roles(first, project)
        self.assertEqual(first.get(0, 0).fg_slot, 4)
        self.assertEqual(first.get(2, 0).fg_slot, 16)
        palette.set_hsv(16, *rgb_to_hsv(Color(40, 210, 220)))
        project.roles = palette.roles
        recovered = project_from_dict(json.loads(dumps_project(project)))
        second = source.copy()
        restored = library.prepare_roles(second, recovered)
        self.assertEqual(first, second)
        self.assertEqual(restored.color(16), Color(40, 210, 220))
        self.assertNotEqual(restored.color(4), restored.color(16))


class FavouriteVariantTests(unittest.TestCase):
    def test_starred_font_is_available_when_family_index_does_not_include_it(self):
        async def drive():
            index = starter_index()
            favourite = index.pop().font
            library.toggle_favourite(favourite)
            app = MeowText(index=index)
            async with app.run_test(size=(100, 34)) as pilot:
                await pilot.pause()
                app.query_one("#font-mode", Select).value = "favourites"
                await pilot.pause()
                self.assertEqual(
                    [item.font for item in app.discovery.choices], [favourite]
                )

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            asyncio.run(drive())


class PlaybackTerminalTests(unittest.TestCase):
    def test_watch_starts_without_graphics_probe_and_ctrl_c_restores_terminal(self):
        import fcntl
        import pty
        import select
        import signal
        import struct
        import termios
        import time
        from meowtext.effects import Animation

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"MEOWTEXT_HOME": tmp}),
        ):
            library.save(
                "animated",
                Project(
                    text="MEOW",
                    font_name="standard",
                    style=PRESETS["ice-rim"].clone(),
                    animation=Animation(name="hue"),
                ),
            )
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
            child = subprocess.Popen(
                [sys.executable, "-m", "meowtext", "watch", "animated"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=dict(os.environ, TERM="xterm-kitty"),
            )
            os.close(slave)
            data = b""
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and (
                    b"\x1b[?1049h" not in data or len(data) < 400
                ):
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            data += os.read(master, 65536)
                        except OSError:
                            break
                self.assertIn(b"\x1b[?1049h", data)
                child.send_signal(signal.SIGINT)
                self.assertEqual(child.wait(timeout=5), 0)
                while select.select([master], [], [], 0.1)[0]:
                    try:
                        data += os.read(master, 65536)
                    except OSError:
                        break
                self.assertIn(b"\x1b[?1049l", data)
                self.assertNotIn(b"Traceback", data)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                os.close(master)
