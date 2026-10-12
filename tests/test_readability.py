"""Legible gradients throughout a cycle, motion and portable export contracts."""
import json
import unittest
from io import BytesIO

from PIL import Image

from meowtext.animation_export import export_design, timeline
from meowtext.compose import present
from meowtext.effects import ANIMATIONS, PALETTES, PRESETS, LIGHT_MOTIONS, Animation, BannerStyle
from meowtext.grid import Cell, Color, Grid
from meowtext.palette import GRADIENT_LUMINANCE, lift_gradient, luminance
from meowtext.project import Project, dumps_project, project_from_dict


class ReadabilityTests(unittest.TestCase):
    def test_palettes_stay_readable_between_stops_and_during_hue_cycles(self):
        source = Grid([[Cell('█') for _ in range(25)]])
        for name in PALETTES:
            for frame in range(30):
                for bands in (False, True):
                    art = present(source, BannerStyle(gradient=name,bands=bands), animation=Animation(name='hue'),frame=frame)
                    with self.subTest(palette=name,frame=frame,bands=bands):
                        self.assertGreaterEqual(min(luminance(c.fg) for c in art.rows[0]),GRADIENT_LUMINANCE)

    def test_shadows_solids_and_original_roles_keep_their_authored_colours(self):
        black = Color(0,0,0)
        source = Grid([[Cell('X')]])
        self.assertEqual(present(source,BannerStyle(stops=(black,black))).get(0,0).fg,black)
        styled=present(source,BannerStyle(gradient='ice',shadow=True,shadow_color=black))
        self.assertEqual(styled.get(1,1).fg,black)
        role=Grid([[Cell('X',fg_slot=1)]])
        self.assertEqual(present(role,BannerStyle(gradient='ice')).get(0,0).fg,Color(0,0,170))

    def test_opt_out_roundtrips_and_old_projects_get_the_fix(self):
        source=Grid([[Cell('X'),Cell('X')]])
        project=Project(style=BannerStyle(gradient='ice',readable_gradients=False))
        raw=json.loads(dumps_project(project))
        restored=project_from_dict(raw)
        self.assertFalse(restored.style.readable_gradients)
        self.assertEqual(present(source,restored.style).get(0,0).fg,PALETTES['ice'][0])
        del raw['style']['readable_gradients']
        self.assertTrue(project_from_dict(raw).style.readable_gradients)
        self.assertGreaterEqual(luminance(lift_gradient(Color(0,0,255))),GRADIENT_LUMINANCE)
        self.assertEqual(lift_gradient(Color(255,255,255)),Color(255,255,255))

    def test_gradient_borders_remain_visible_during_pulse(self):
        source=Grid([[Cell('X')]])
        style=BannerStyle(outline=True,outline_mode='thick',outline_gradient='ice')
        for frame in range(32):
            art=present(source,style,animation=Animation(name='pulse'),frame=frame)
            for row in art.rows:
                for cell in row:
                    if cell.fg:
                        self.assertGreaterEqual(luminance(cell.fg),GRADIENT_LUMINANCE)


class AddedMotionTests(unittest.TestCase):
    def setUp(self):
        self.source=Grid([[Cell('█'),Cell('▀'),Cell('X')],[Cell('█'),Cell(' ',bg=Color(42,100,135)),Cell('█')]])

    def test_new_motions_are_distinct_periodic_and_keep_the_letters(self):
        signatures=[]
        for name,period in LIGHT_MOTIONS.items():
            project=Project(style=PRESETS['lagoon'].clone(),animation=Animation(name=name))
            a=present(self.source,project.style,animation=project.animation,frame=0)
            b=present(self.source,project.style,animation=project.animation,frame=13)
            end=present(self.source,project.style,animation=project.animation,frame=period)
            self.assertEqual(a.rows,end.rows,name)
            self.assertNotEqual(a.rows,b.rows,name)
            self.assertEqual([[c.char for c in r] for r in a.rows],[[c.char for c in r] for r in b.rows])
            signatures.append(tuple(c.fg for row in b.rows for c in row))
            for direction in ('forward','backward','pingpong'):
                motion=Animation(name=name,speed=2,direction=direction)
                plan=timeline(a,motion)
                cycle=48 if direction=='pingpong' else period
                self.assertAlmostEqual(plan.count*plan.duration,cycle/2*120)
            self.assertEqual(project_from_dict(json.loads(dumps_project(project))).animation.name,name)
        self.assertEqual(len(set(signatures)),len(LIGHT_MOTIONS))

    def test_gif_plays_a_complete_cycle_and_trace_does_not_repeat(self):
        for name in LIGHT_MOTIONS:
            project=Project(style=PRESETS['aurora'].clone(),animation=Animation(name=name))
            gif=Image.open(BytesIO(export_design(self.source,project,'gif')))
            self.assertGreater(gif.n_frames,1)
            self.assertEqual(gif.info.get('loop'),0)
            duration=0
            for n in range(gif.n_frames):
                gif.seek(n);duration+=gif.info['duration']
                self.assertEqual(gif.size,(55,88))
            self.assertEqual(duration,LIGHT_MOTIONS[name]*120)
        project.animation=Animation(name='trace')
        gif=Image.open(BytesIO(export_design(self.source,project,'gif')))
        self.assertNotIn('loop',gif.info)
        gif.seek(gif.n_frames-1)
        self.assertGreater(len(gif.convert('RGB').getcolors(100000)),1)

    def test_every_preset_and_motion_renders_and_has_a_complete_export_period(self):
        self.assertGreaterEqual(len(PRESETS),40)
        self.assertGreaterEqual(len(ANIMATIONS),11)
        for name,style in PRESETS.items():
            for _,motion in ANIMATIONS:
                art=present(self.source,style,animation=Animation(name=motion),frame=7)
                self.assertGreater(art.width,0,name)
                self.assertGreater(timeline(art,Animation(name=motion)).count,0,motion)


if __name__=='__main__':
    unittest.main()
