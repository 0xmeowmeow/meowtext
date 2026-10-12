"""Export fidelity: pixels, complete motion, timing, and loss notices."""
import base64
import json
import re
import unittest
from io import BytesIO

from PIL import Image

from meowtext.animation_export import export_design, timeline
from meowtext.compose import present
from meowtext.effects import Animation, BannerStyle
from meowtext.export import export_notice, to_html, to_png
from meowtext.grid import Cell, Color, Grid
from meowtext.project import Project
from meowtext.raster import cell_size, rasterize


class ExportFidelityTests(unittest.TestCase):
    def setUp(self):
        self.source = Grid([[Cell("█", Color(10, 80, 180)), Cell("▀", Color(255, 90, 20), Color(20, 30, 40))],
                            [Cell("│", Color(255, 255, 255)), Cell(" ", bg=Color(30, 140, 50))]])
        self.project = Project(style=BannerStyle(gradient="rainbow", outline=True, shadow=True),
                               animation=Animation(name="hue"))

    def payload(self, document):
        return json.loads(re.search(r'<script id="meowtext-frames" type="application/json">(.*?)</script>', document, re.S)[1])

    def test_png_is_current_composed_frame_and_keeps_backgrounds(self):
        png = export_design(self.source, self.project, "png", frame=7)
        expected = rasterize(present(self.source, self.project.style, animation=self.project.animation, frame=7))
        self.assertEqual(Image.open(BytesIO(png)).tobytes(), expected.tobytes())
        cw, ch = cell_size()
        image = rasterize(self.source)
        self.assertEqual(image.getpixel((cw + 1, ch + 1)), (30, 140, 50))
        self.assertEqual(image.getpixel((cw + 1, ch - 1)), (20, 30, 40))
        # A vertical stroke reaches both cell edges, without typographic gaps.
        self.assertEqual(image.getpixel((cw // 2, ch)), (255, 255, 255))
        self.assertEqual(image.getpixel((cw // 2, 2 * ch - 1)), (255, 255, 255))

    def test_html_embeds_the_same_png_and_escapes_text(self):
        self.source.rows[0][0].char = "</script>"
        document = to_html(self.source)
        payload = self.payload(document)
        self.assertEqual(base64.b64decode(payload["frames"][0].split(",", 1)[1]), to_png(self.source))
        self.assertIn("&lt;/script&gt;", document)
        self.assertNotIn("https://", document)

    def test_html_and_apng_keep_every_hue_frame_and_timing(self):
        document = export_design(self.source, self.project, "html")
        payload = self.payload(document)
        png = Image.open(BytesIO(export_design(self.source, self.project, "apng")))
        self.assertEqual(len(payload["frames"]), 30)
        self.assertEqual(png.n_frames, 30)
        self.assertEqual(payload["duration"], 120)
        for index in (0, 7, 29):
            expected = rasterize(present(self.source, self.project.style, animation=self.project.animation, frame=index))
            png.seek(index)
            html_frame = Image.open(BytesIO(base64.b64decode(payload["frames"][index].split(",", 1)[1])))
            self.assertEqual(png.convert("RGB").tobytes(), expected.tobytes())
            self.assertEqual(html_frame.tobytes(), expected.tobytes())

    def test_reveal_finishes_and_holds_in_both_directions(self):
        for direction in ("forward", "backward"):
            self.project.animation = Animation(name="trace", direction=direction)
            payload = self.payload(export_design(self.source, self.project, "html"))
            self.assertFalse(payload["loop"])
            final = base64.b64decode(payload["frames"][-1].split(",", 1)[1])
            self.assertEqual(final, to_png(present(self.source, self.project.style)))

    def test_export_notices_explain_actual_losses(self):
        for fmt in ("png", "ansi", "json", "plain", "markdown", "irc"):
            self.assertIn("Animation will be lost", export_notice(fmt, True))
        self.assertIn("backgrounds", export_notice("plain"))
        self.assertNotIn("Animation will be lost", export_notice("html", True))
        self.assertIn("first frame", export_notice("apng", True))
        self.assertIn("complete animation", export_notice("kitty", True))

    def test_kitty_contains_complete_frames_and_a_terminal_owned_clock(self):
        data = export_design(self.source, self.project, "kitty")
        packets = re.findall(r"\x1b_G([^;]*);(.*?)\x1b\\", data, re.S)
        frames, buffer = [], ""
        for header, payload in packets:
            control = dict(item.split("=", 1) for item in header.split(","))
            if control["a"] in {"t", "f"}:
                buffer += payload
                if control["m"] == "0":
                    frames.append(base64.b64decode(buffer)); buffer = ""
        self.assertEqual(len(frames), 30)
        for index in (0, 7, 29):
            expected = present(self.source, self.project.style, animation=self.project.animation, frame=index)
            self.assertEqual(frames[index], to_png(expected))
        self.assertIn("r=1,z=120", data)
        self.assertIn("s=3,v=1", data)
        self.assertNotIn("a=d", data)
        self.project.animation = Animation(name="trace")
        self.assertIn("s=3,v=2", export_design(self.source, self.project, "kitty"))

    def test_animation_period_includes_border_speed_and_limits(self):
        self.assertEqual(timeline(self.source, Animation(name="hue", speed=2), .5).count, 30)
        self.assertEqual(timeline(self.source, Animation(name="march", direction="pingpong"), 1).count, 48)
        from meowtext.errors import RenderError
        with self.assertRaises(RenderError):
            timeline(self.source, Animation(name="hue", speed=.001))
