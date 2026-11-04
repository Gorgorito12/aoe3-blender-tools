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
from core.styles.african import compose, layouts, parts, sizes  # noqa: E402


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


class Piers(unittest.TestCase):
    def test_a_palace_pier_runs_out_into_the_walls(self):
        pieces = layout_of(building.PRESETS["AFRICAN_PALACE_SAHEL"], "MEDIUM")
        piers = [q for q in pieces if q["kind"] == "pier"]
        walls = [q for q in pieces if q["kind"] == "block" and not q.get("z")]
        self.assertEqual(len(piers), 10)                   # every exposed corner, both sides alike
        for q in piers:
            fx0, fx1, fy0, fy1 = q["foot"]
            tx0, tx1, ty0, ty1 = q["top"]
            self.assertLess(tx1 - tx0, fx1 - fx0 + 0.01)   # it narrows as it rises
            self.assertLess(ty1 - ty0, fy1 - fy0 + 0.01)
            sx, sy = q["into"]
            ox, oy = tx0 if sx > 0 else tx1, ty0 if sy > 0 else ty1    # its top's outer corner
            ix, iy = tx1 if sx > 0 else tx0, ty1 if sy > 0 else ty0    # and the one in the walls
            self.assertTrue(any(w["x0"] < ix < w["x1"] and w["y0"] < iy < w["y1"] for w in walls), q)
            self.assertLess(abs(ox - ix) + abs(oy - iy), 1.5, q)


class Composition(unittest.TestCase):
    def test_nothing_is_left_alone_on_the_plot(self):
        """Every prop stands near a structure or another prop: a building is one place."""
        for key, params in building.PRESETS.items():
            if params.style != "AFRICAN":
                continue
            p = african.clamp(dataclasses.replace(params, detail="MEDIUM"))
            S = 2 * sizes.court_half(p.building_type) + 0.2
            pieces = layouts.structure(p, S, True)
            ground = compose.survey(pieces, S)
            done = layouts.layout(p, S, True)
            props = done[len([q for q in pieces if q["kind"] != "yard"]):]
            base = ground.solid.copy()
            for q in props:
                if q["kind"] == "boat" or q.get("z"):
                    continue
                d = compose.reach(base)
                i = abs(ground.X[0] - q["x"]).argmin()
                j = abs(ground.Y[:, 0] - q["y"]).argmin()
                with self.subTest(key=key, prop=q["kind"]):
                    self.assertLessEqual(float(d[j, i]), compose.MAX_REACH + 1.5)
                base |= ground.disc(q["x"], q["y"], 0.3)

    def test_the_same_parameters_give_the_same_building(self):
        p = african.clamp(building.PRESETS["AFRICAN_ARMORY_SAHEL"])
        S = sizes.side_m(p.building_type)
        self.assertEqual(layouts.layout(p, S, True), layouts.layout(p, S, True))

    def test_an_armory_is_an_armory_and_a_quarry_a_quarry(self):
        want = {"ARMORY": {"anvil", "bellows", "rack", "shields", "trough"}, "QUARRY": {"crate", "barrel", "stones", "crane"},
                "CUSTOMS": {"weigh", "crate"}, "WAR_CAMP": {"dummy", "rack", "fire"}, "DOCK": {"boat"}}
        for key, params in building.PRESETS.items():
            if params.style == "AFRICAN" and params.building_type in want:
                p = african.clamp(params)
                kinds = {q["kind"] for q in layouts.layout(p, sizes.side_m(p.building_type), True)}
                with self.subTest(key):
                    self.assertLessEqual(want[params.building_type], kinds)


if __name__ == "__main__":
    unittest.main()
