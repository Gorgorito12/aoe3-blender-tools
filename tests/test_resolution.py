# SPDX-License-Identifier: GPL-3.0-or-later
"""BuildingParams.poly: the segments of every body that is not a box. That 1.0 changes nothing,
that the floors hold, and that a lower number really costs fewer triangles without breaking a
joint.

    venv\\Scripts\\python -I tests\\test_resolution.py
"""
import dataclasses
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building, resolution  # noqa: E402
from core.kit import Builder  # noqa: E402
from core.styles import african  # noqa: E402
from core.styles.african import layouts, parts, sizes  # noqa: E402

BASES = (3, 4, 5, 6, 8, 10, 12, 16, 24, 32)


def tris(params):
    return sum(len(f.pts) - 2 for f in building.build(params).faces)


class Neutral(unittest.TestCase):
    def test_a_factor_of_one_returns_every_count_untouched(self):
        for base in BASES:
            self.assertEqual(resolution.scale(base, 1.0, 3), base)
            self.assertEqual(resolution.sides(base, 1.0), base)
            self.assertEqual(resolution.rings(base, 1.0), base)
            self.assertEqual(resolution.segments(base, 1.0), base - base % 2)
        self.assertEqual(resolution.scale(7, None, 3), 7)

    def test_the_default_is_one(self):
        self.assertEqual(building.BuildingParams().poly, 1.0)

    def test_a_building_at_one_is_the_building_that_was_always_built(self):
        for key in ("WHITE_HOUSE_1914", "AFRICAN_TOWN_CENTER_SUBSAHARAN", "COLONIAL_TRADING_HOUSE"):
            p = building.PRESETS[key]
            a, b = building.build(p), building.build(dataclasses.replace(p, poly=1.0))
            self.assertEqual([f.pts for f in a.faces], [f.pts for f in b.faces], key)
            self.assertEqual([f.uvs for f in a.faces], [f.uvs for f in b.faces], key)


class Floors(unittest.TestCase):
    def test_a_round_body_never_falls_below_its_floor(self):
        for f in (0.01, 0.1, 0.3):
            self.assertGreaterEqual(resolution.sides(8, f), resolution.MIN_SIDES)
            self.assertGreaterEqual(resolution.rings(6, f), resolution.MIN_RINGS)
            self.assertGreaterEqual(resolution.segments(6, f), resolution.MIN_SEGMENTS)

    def test_an_arch_keeps_an_even_number_of_segments(self):
        for f in (0.3, 0.55, 0.8, 1.0, 1.4, 1.9):
            self.assertEqual(resolution.segments(6, f) % 2, 0, f)

    def test_the_builder_carries_the_factor(self):
        b = Builder(1024, True, 0.5)
        self.assertEqual((b.sides(24), b.rings(6), b.segments(6)), (12, 3, 2))
        self.assertEqual(Builder(1024, True).sides(24), 24)
        self.assertEqual(Builder(1024, True, None).sides(24), 24)


class Error(unittest.TestCase):
    def test_the_sag_falls_as_the_sides_rise(self):
        errors = [resolution.chord_error(2.0, n) for n in (6, 8, 12, 24)]
        self.assertEqual(errors, sorted(errors, reverse=True))
        self.assertAlmostEqual(resolution.chord_error(2.0, 8), 2.0 * (1 - math.cos(math.pi / 8)), 9)

    def test_sides_for_keeps_the_sag_under_what_was_asked(self):
        for r in (0.5, 1.0, 2.0, 6.0):
            n = resolution.sides_for(r, resolution.ERROR_SEEN)
            self.assertLessEqual(resolution.chord_error(r, n), resolution.ERROR_SEEN + 1e-9, r)
            self.assertGreaterEqual(n, resolution.MIN_SIDES)

    def test_a_wider_body_needs_more_sides(self):
        self.assertGreater(resolution.sides_for(8.0), resolution.sides_for(1.0))


class Cost(unittest.TestCase):
    """What the multiplier is for: a building that is cheaper, or finer, where it is round."""

    def test_round_styles_get_cheaper_and_finer(self):
        for key in ("AFRICAN_HOUSE_SUBSAHARAN", "AFRICAN_GRANARY_SAHEL", "WHITE_HOUSE_1914"):
            p = building.PRESETS[key]
            cheap, same, fine = (tris(dataclasses.replace(p, poly=f)) for f in (0.5, 1.0, 1.5))
            self.assertLess(cheap, same, key)
            self.assertGreater(fine, same, key)

    def test_the_saving_is_worth_having(self):
        p = building.PRESETS["AFRICAN_HOUSE_SUBSAHARAN"]
        self.assertLess(tris(dataclasses.replace(p, poly=0.5)), 0.6 * tris(p))

    def test_a_building_made_of_boxes_does_not_change(self):
        p = building.PRESETS["COLONIAL_HOUSE"]          # no arcade, no round body at all
        self.assertEqual(tris(dataclasses.replace(p, poly=0.5)), tris(p))
        self.assertEqual(tris(dataclasses.replace(p, poly=1.5)), tris(p))

    def test_an_arcade_follows_it(self):
        p = building.PRESETS["COLONIAL_TRADING_HOUSE"]
        self.assertLess(tris(dataclasses.replace(p, poly=0.5)), tris(p))

    def test_a_composed_building_spends_what_it_saves_on_props(self):
        """The African composer fills up to the class budget, so a cheaper shape buys more props
        instead of fewer triangles. Worth knowing before anyone uses poly to save there."""
        p = building.PRESETS["AFRICAN_PALACE_SAHEL"]
        target, lo, hi = sizes.tris_target(p.building_type, p.architecture)
        for f in (0.5, 1.0, 1.5):
            self.assertTrue(lo <= tris(dataclasses.replace(p, poly=f)) <= hi, f)


class Joints(unittest.TestCase):
    """The rule poly must not break: a round wall never loses the sides core/joints.py measures
    an embedding on, so no layout that was sound becomes unsound."""

    def test_a_round_wall_keeps_its_low_detail_sides(self):
        for big in (False, True):
            low = parts.sides(False, big)
            for f in (0.1, 0.5, 0.75, 1.0):
                self.assertGreaterEqual(parts.sides(False, big, f), low, (big, f))
                self.assertGreaterEqual(parts.sides(True, big, f), low, (big, f))

    def test_no_preset_gains_a_bad_joint(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN":
                continue
            for detail in ("LOW", "MEDIUM"):
                q = african.clamp(dataclasses.replace(p, detail=detail))
                base = parts.junctions(layouts.layout(q, sizes.side_m(q.building_type),
                                                      detail == "MEDIUM"))
                for f in (0.5, 0.75, 1.3):
                    r = african.clamp(dataclasses.replace(q, poly=f))
                    now = parts.junctions(layouts.layout(r, sizes.side_m(r.building_type),
                                                         detail == "MEDIUM"))
                    self.assertEqual(now, base, (key, detail, f))


class Clamping(unittest.TestCase):
    def test_every_style_clamps_a_silly_factor(self):
        for key in ("WHITE_HOUSE", "COLONIAL_HOUSE", "TIMBER_HOUSE", "AFRICAN_HOUSE_SAHEL"):
            p = building.PRESETS[key]
            for f in (0.0, -3.0, 50.0):
                m = building.build(dataclasses.replace(p, poly=f))
                self.assertGreater(len(m.faces), 10, (key, f))


if __name__ == "__main__":
    unittest.main(verbosity=2)
