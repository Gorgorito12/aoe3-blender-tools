# SPDX-License-Identifier: GPL-3.0-or-later
"""The volumes of every African building meet properly: clearly apart or truly embedded
(core/joints.py), at both details, on the presets and on random parameters.

    venv\\Scripts\\python -I tests\\test_african_joints.py
"""
import dataclasses
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building, joints  # noqa: E402
from core.styles import african  # noqa: E402
from core.styles.african import layouts, parts, sizes  # noqa: E402


def layout_of(params, detail):
    p = african.clamp(dataclasses.replace(params, detail=detail))
    return layouts.layout(p, sizes.side_m(p.building_type), detail == "MEDIUM")


def circle(x, y, r, z1, sides=10):
    return {"shape": "circle", "x": x, "y": y, "r": r, "z0": 0.0, "z1": z1, "sides": sides}


def rect(x0, y0, x1, y1, z1):
    return {"shape": "rect", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "z0": 0.0, "z1": z1}


class Rule(unittest.TestCase):
    def test_a_wing_with_its_corners_out_of_the_tower_is_bad(self):
        self.assertEqual(joints.classify(circle(0, 0, 3.0, 7.2), rect(-2.6, -7.6, 2.6, -2.5, 4.4)), "bad")

    def test_a_wing_ending_inside_the_low_polygon_is_embedded(self):
        self.assertEqual(joints.classify(circle(0, 0, 3.6, 7.2), rect(-2.2, -7.6, 2.2, -2.6, 4.4)), "embedded")

    def test_inside_the_radius_but_outside_the_low_polygon_is_bad(self):
        r = 3.0 * math.cos(math.pi / 8) + 0.05                  # between the polygon and the circle
        self.assertEqual(joints.classify(circle(0, 0, 3.0, 7.0, 8), rect(-1, -6, 1, -math.sqrt(r * r - 1), 4)), "bad")

    def test_a_taller_piece_cannot_end_inside_a_lower_one(self):
        self.assertEqual(joints.classify(circle(0, 0, 3.6, 3.0), rect(-2.2, -7.6, 2.2, -2.6, 4.4)), "bad")

    def test_a_sliver_of_air_is_bad(self):
        self.assertEqual(joints.classify(rect(0, 0, 2, 2, 3), rect(2.1, 0, 4, 2, 3)), "bad")

    def test_flush_walls_are_bad_and_a_clear_gap_is_fine(self):
        self.assertEqual(joints.classify(rect(0, 0, 2, 2, 3), rect(2.0, 0, 4, 2, 3)), "bad")
        self.assertEqual(joints.classify(rect(0, 0, 2, 2, 3), rect(2.3, 0, 4, 2, 3)), "apart")

    def test_a_piece_on_a_roof_is_not_a_joint(self):
        top = dict(rect(0, 0, 1, 1, 5), z0=3.0)
        self.assertEqual(joints.classify(rect(0, 0, 4, 4, 3.0), top), "apart")


class Buildings(unittest.TestCase):
    def test_every_preset(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN":
                continue
            for detail in ("LOW", "MEDIUM"):
                with self.subTest(key=key, detail=detail):
                    self.assertEqual(parts.junctions(layout_of(p, detail)), [])

    def test_random_parameters(self):
        rng = random.Random(11)
        for i in range(60):
            p = african.random_params(rng, i, building.BuildingParams)
            with self.subTest(i=i):
                self.assertEqual(parts.junctions(layout_of(p, p.detail)), [])


if __name__ == "__main__":
    unittest.main()
