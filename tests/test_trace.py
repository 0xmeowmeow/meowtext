"""Concurrent Trace paths, decoration pacing, and complete exported reveals."""
import json
import math
import re
import shutil
import unittest
from io import BytesIO

from PIL import Image

from meowtext.animation_export import export_design, timeline
from meowtext.compose import present
from meowtext.effects import Animation, BannerStyle, trace, trace_plan
from meowtext.grid import Cell, Color, Grid, is_ink
from meowtext.project import Project
from meowtext.raster import rasterize


def ink(grid):
    return {(x, y) for y, row in enumerate(grid.rows) for x, cell in enumerate(row) if is_ink(cell)}


def letters():
    # Touching letters, disconnected strokes, unequal sizes, and two lines.
    grid = Grid([[Cell(c, Color(70, 100, 140)) if c != ' ' else Cell() for c in row]
                 for row in ('AAABB', 'A A B', 'AAABB', '     ', ' C C ', ' CCC ')])
    grid.spans = (('A', 0, 0, 3, 3), ('B', 3, 0, 2, 3), ('C', 1, 4, 3, 2))
    return grid


class ConcurrentTraceTests(unittest.TestCase):
    def test_every_letter_and_background_seed_starts_and_finishes_together(self):
        source = letters()
        for scope in ('word', 'letter'):
            for dx, dy in ((2, 1), (-2, -1)):
                style = BannerStyle(outline=True, outline_distance=3, outline_scope=scope,
                                    outline_dx=-1, outline_dy=1, shadow=True, shadow_dx=dx, shadow_dy=dy)
                complete = present(source, style)
                groups = complete.letter_ink
                self.assertEqual([len(g) for g in groups], [8, 5, 5])
                # Decoration can touch/cover gaps but must not consume letter paths.
                self.assertTrue(all(complete.get(x, y).char in 'ABC' for g in groups for x, y in g))
                for pattern in ('outline', 'rows', 'letter', 'centre'):
                    plan = trace_plan(complete, pattern)
                    self.assertEqual(plan.steps, 8)
                    background = ink(complete) - set().union(*map(set, groups))
                    self.assertEqual(len(plan.paths) - 3, math.ceil(len(background) / 8))
                    self.assertEqual(set().union(*map(set, plan.paths)), ink(complete))
                    self.assertEqual(sum(map(len, plan.paths)), len(ink(complete)))
                    for direction in ('forward', 'backward'):
                        motion = Animation(name='trace', pattern=pattern, direction=direction)
                        first = present(source, style, animation=motion, frame=0)
                        penultimate = present(source, style, animation=motion, frame=6)
                        final = present(source, style, animation=motion, frame=7)
                        self.assertEqual(len(ink(first)), len(plan.paths))
                        for path in plan.paths:
                            self.assertEqual(len(ink(first) & set(path)), 1)
                            if len(path) > 1:
                                self.assertLess(len(ink(penultimate) & set(path)), len(path))
                        self.assertEqual(final, complete)
                        self.assertEqual(present(source, style, animation=motion, frame=100), complete)

    def test_word_length_and_background_size_do_not_extend_the_cycle(self):
        for count in (1, 10, 80):
            source = Grid([[Cell('X') for _ in range(count * 3)] for _ in range(3)])
            source.spans = tuple(('X', i * 3, 0, 3, 3) for i in range(count))
            for distance in (1, 6):
                complete = present(source, BannerStyle(outline=True, outline_distance=distance, shadow=True))
                self.assertEqual(timeline(complete, Animation(name='trace')).count, 9)

    def test_pingpong_reaches_the_complete_artwork_at_every_speed(self):
        source = letters()
        style = BannerStyle(outline=True, shadow=True)
        complete = present(source, style)
        for speed in (.5, 1, 2, 3, 1.7):
            motion = Animation(name='trace', direction='pingpong', speed=speed)
            plan = timeline(complete, motion)
            self.assertTrue(plan.loop)
            self.assertEqual(plan.count % 2, 0)
            self.assertEqual(plan.step, 1)
            self.assertEqual(plan.duration, 120)
            # The actual editor advances integer frames, not export subframes.
            self.assertEqual(present(source, style, animation=motion,
                                     frame=math.ceil(7 / speed)), complete)
            self.assertEqual(present(source, style, animation=motion,
                                     frame=(plan.count // 2) * plan.step), complete)
            self.assertEqual(present(source, style, animation=motion, frame=plan.count * plan.step),
                             present(source, style, animation=motion, frame=0))

    def test_runner_lights_every_path_and_loops_on_the_shared_period(self):
        complete = present(letters(), BannerStyle(outline=True, shadow=True))
        plan = trace_plan(complete)
        for direction in ('forward', 'backward', 'pingpong'):
            motion = Animation(name='trace', reveal='runner', direction=direction, speed=1.7)
            exported = timeline(complete, motion)
            first = trace(complete, motion, 0)
            self.assertEqual(ink(first), ink(complete))
            self.assertTrue(all(first.get(*path[0]).fg != complete.get(*path[0]).fg for path in plan.paths))
            self.assertNotEqual(trace(complete, motion, 2), first)
            self.assertEqual(trace(complete, motion, exported.count * exported.step), first)

    def test_background_colour_cells_participate(self):
        source = Grid([[Cell(' ', bg=Color(20, 40, 80)) for _ in range(4)]])
        source.spans = (('A', 0, 0, 2, 1), ('B', 2, 0, 2, 1))
        motion = Animation(name='trace')
        self.assertEqual(ink(trace(source, motion, 0)), {(0, 0), (2, 0)})
        self.assertEqual(trace(source, motion, 1), source)
        runner = trace(source, Animation(name='trace', reveal='runner'), 0)
        self.assertNotEqual(runner.get(0, 0).bg, source.get(0, 0).bg)

    def test_unlabelled_art_splits_lines_and_empty_art_is_safe(self):
        source = Grid([[Cell(c) for c in row] for row in ('XX XX', '     ', 'YY YY')])
        self.assertEqual(len(ink(trace(source, Animation(name='trace'), 0))), 4)
        for source in (Grid(), Grid.blank(4, 2), Grid([[Cell('X')]])):
            self.assertEqual(trace(source, Animation(name='trace'), 0), source)
            self.assertEqual(timeline(source, Animation(name='trace')).count, 1)

    def test_exports_use_parallel_length_and_match_the_preview(self):
        source = letters()
        project = Project(style=BannerStyle(outline=True, shadow=True), animation=Animation(name='trace'))
        document = export_design(source, project, 'html')
        payload = json.loads(re.search(r'<script id="meowtext-animation" type="application/json">(.*?)</script>', document, re.S)[1])
        self.assertEqual(payload['count'], 8)
        self.assertFalse(payload['loop'])
        complete = present(source, project.style)
        for offset, changes in payload['changes']:
            for frame in (0, 3, 7):
                preview = present(source, project.style, animation=project.animation, frame=frame)
                self.assertEqual(payload['characters'][changes[frame]], preview.get(offset % complete.width, offset // complete.width).char or ' ')
        for fmt in ('gif', 'apng'):
            image = Image.open(BytesIO(export_design(source, project, fmt)))
            self.assertEqual(image.n_frames, 8)
            if fmt == 'gif':
                self.assertNotIn('loop', image.info)
            else:
                for frame in (0, 3, 7):
                    image.seek(frame)
                    preview = present(source, project.style, animation=project.animation, frame=frame)
                    self.assertEqual(image.convert('RGB').tobytes(), rasterize(preview).tobytes())
        kitty = export_design(source, project, 'kitty')
        self.assertEqual(len(re.findall(r'\x1b_Ga=[tf],', kitty)), 8)
        self.assertIn('s=3,v=2', kitty)

    @unittest.skipUnless(shutil.which('figlet'), 'FIGlet is not installed')
    def test_native_recipes_measure_touching_letters_even_for_long_text(self):
        from meowtext.library import render_project
        text = 'M' * 41
        project = Project(text=text, font_name='small', animation=Animation(name='trace'))
        first = render_project(project).grid
        self.assertEqual(len(first.letter_ink), len(text))
        self.assertEqual(len(ink(first)), len(text))

    @unittest.skipUnless(shutil.which('figlet'), 'FIGlet is not installed')
    def test_native_multiline_spans_cover_all_letter_ink(self):
        from meowtext.catalog import resolve, measure_spans
        from meowtext.compose import layout_font
        font = resolve('figlet', 'standard')
        for text in ('A\nB', 'A\n\nB', 'a\nW', '\nA\nB'):
            source = layout_font(text, font)[0]
            source.spans = measure_spans(font, text)
            complete = present(source, BannerStyle())
            self.assertEqual(len(complete.letter_ink), 2)
            self.assertEqual(set().union(*map(set, complete.letter_ink)), ink(source))
            self.assertEqual(len(ink(trace(complete, Animation(name='trace'), 0))), 2)
