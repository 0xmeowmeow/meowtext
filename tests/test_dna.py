"""The ASCII helix is the 1BNA pair on a right-handed ten-base screw."""

from __future__ import annotations

import math
import unittest

from meowtext.dna import BASES_PER_TURN, RISE, TWIST, _polymer, _template_pair, render_ascii


class DnaTests(unittest.TestCase):
    def test_pair_uses_the_1bna_radii(self) -> None:
        pair = _template_pair()
        sugars = [atom for atom in pair if atom[1] == "C1'"]
        phosphates = [atom for atom in pair if atom[1] == "P"]
        self.assertLess(abs(sugars[0][4] - sugars[1][4]), 1.2)
        for phosphate in phosphates:
            radius = math.hypot(phosphate[2], phosphate[3])
            self.assertGreater(radius, 8.0)
            self.assertLess(radius, 12.0)
        chain_a = next(atom for atom in pair if atom[0] == "A" and atom[1] == "P")
        self.assertGreater(chain_a[2], 0)

    def test_ten_bases_close_one_right_handed_turn(self) -> None:
        atoms = _polymer(BASES_PER_TURN + 1, 0)
        step = len(_polymer(1, 0))
        first = atoms[0]
        tenth = atoms[BASES_PER_TURN * step]
        turned = atoms[step]
        self.assertEqual(tenth[0], first[0])
        self.assertEqual(tenth[1], first[1])
        self.assertAlmostEqual(tenth[2], first[2], places=4)
        self.assertAlmostEqual(tenth[3], first[3], places=4)
        self.assertAlmostEqual(tenth[4] - first[4], BASES_PER_TURN * RISE, places=4)
        twist = math.atan2(turned[3], turned[2]) - math.atan2(first[3], first[2])
        self.assertAlmostEqual((twist + math.pi) % math.tau - math.pi, TWIST, places=4)

    def test_ascii_column_is_narrow_and_names_the_bonds(self) -> None:
        text = render_ascii("ATGCGTACGA", 0, turns=1)
        lines = text.splitlines()
        self.assertEqual(len(lines), 11)
        self.assertIn("right-handed", lines[0])
        self.assertIn("10/turn", lines[0])
        self.assertIn("A··T", lines[0])
        self.assertNotIn("A···T", lines[0])
        self.assertLessEqual(max(len(line) for line in lines), 42)
        self.assertIn("A··T", lines[-1])
        guanine = render_ascii("G", 0, turns=1)
        self.assertIn("G···C", guanine.splitlines()[0])
        self.assertIn("G···C", guanine.splitlines()[-1])

    def test_the_next_turn_repeats_the_rung(self) -> None:
        lines = render_ascii("ATGCGTACGA", 0, turns=2).splitlines()[1:]
        self.assertEqual(len(lines), 20)
        self.assertEqual(lines[-1][2:], lines[-11][2:])
        turned = render_ascii("A", 0, turns=2).splitlines()[1:]
        self.assertEqual(turned[-1][2:], turned[-11][2:])
        self.assertNotEqual(turned[-1][2:], turned[-6][2:])
        self.assertIn("A··T", turned[-1])
        self.assertNotIn("·", turned[-6])
        spans = [_span(line[2:]) for line in lines]
        self.assertEqual(spans[-1], max(spans))
        self.assertGreater(spans[-1], spans[-3])


def _span(body: str) -> int:
    ink = [index for index, char in enumerate(body) if char != " "]
    if not ink:
        return 0
    return ink[-1] - ink[0]


if __name__ == "__main__":
    unittest.main()
