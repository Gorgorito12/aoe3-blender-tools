# SPDX-License-Identifier: GPL-3.0-or-later
"""Props and treasures (core/styles/props) against what the original game's own measure
(docs/art-findings.md): triangles inside their group's middle half, a treasure's main piece
leaning and its cargo spilled round it, never upright in a row.

    venv/Scripts/python -I tests/test_props.py
"""
import dataclasses
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building  # noqa: E402
from core.styles import props  # noqa: E402
from core.styles.african import compose, sizes  # noqa: E402
from core.styles.props import recipes  # noqa: E402

UPM = sizes.UNITS_PER_METER
KEYS = [k for k, p in building.PRESETS.items() if p.style == "PROP"]


def tris(model):
    return sum(len(f.pts) - 2 for f in model.faces)


class Props(unittest.TestCase):
    def test_there_is_a_preset_for_every_recipe(self):
        self.assertEqual(sorted(building.PRESETS[k].prop_type for k in KEYS), sorted(recipes.TYPES))

    def test_every_prop_is_inside_its_groups_triangles(self):
        for key in KEYS:
            with self.subTest(key=key):
                p = building.clamp_params(building.PRESETS[key])
                lo, target, hi = props.budget(p.prop_type)
                n = tris(building.build(p))
                self.assertLessEqual(n, hi)
                if p.prop_type in recipes.TREASURES:       # a treasure fills its cargo up to the median
                    self.assertGreaterEqual(n, lo)

    def test_a_treasure_is_about_as_wide_as_the_games_own(self):
        for key in KEYS:
            p = building.clamp_params(building.PRESETS[key])
            if p.prop_type not in recipes.TREASURES:
                continue
            with self.subTest(key=key):
                w, d = building.build(p).dims["footprint"]
                self.assertTrue(3.0 <= max(w, d) * UPM <= 7.7, max(w, d) * UPM)   # the game's: 4.3 / 4.7 / 7.7

    def test_a_treasures_main_piece_leans_and_its_cargo_is_spilled(self):
        for t in recipes.TREASURES:
            with self.subTest(t=t):
                p = building.clamp_params(building.prop(t))
                pieces = props.layout(p)
                main, cargo = pieces[:len(recipes.RECIPES[t]["main"])], pieces[len(recipes.RECIPES[t]["main"]):]
                self.assertTrue(any(m.get("turn") or m.get("tilt") for m in main), "upright and square")
                self.assertGreaterEqual(len(cargo), 3)
                self.assertTrue(any(c.get("tilt") for c in cargo), "nothing knocked over")
                self.assertGreater(len({round(c.get("turn", 0.0), 3) for c in cargo}), 1, "all turned alike")
                for c in cargo:                            # within reach of the plot, not scattered
                    self.assertLessEqual(math.hypot(c["x"], c["y"]), recipes.RECIPES[t]["plot"] / 2 * math.sqrt(2))

    def test_the_seed_gives_another_arrangement_and_the_same_seed_the_same(self):
        p = building.prop("BROKEN_CART")
        a = props.layout(building.clamp_params(p))
        b = props.layout(building.clamp_params(p))
        c = props.layout(building.clamp_params(dataclasses.replace(p, seed=p.seed + 1)))
        self.assertEqual(a, b)
        self.assertNotEqual([(x["x"], x["y"]) for x in a], [(x["x"], x["y"]) for x in c])

    def test_the_low_model_keeps_the_main_piece_and_costs_less(self):
        for key in KEYS:
            with self.subTest(key=key):
                p = building.PRESETS[key]
                med, low = building.build(p), building.build(dataclasses.replace(p, detail="LOW"))
                self.assertLessEqual(tris(low), tris(med))
                self.assertGreater(tris(low), 0)

    def test_every_uv_is_inside_its_region(self):
        for key in KEYS:
            with self.subTest(key=key):
                m = building.build(building.PRESETS[key])
                for f in m.faces:
                    r = m.atlas[f.region]
                    for u, v in f.uvs:
                        self.assertTrue(-1e-4 <= u <= r.world_w + 1e-4 and -1e-4 <= v <= r.world_h + 1e-4,
                                        (f.region, u, v))

    def test_a_pose_lays_a_barrel_on_its_side_and_keeps_it_on_the_ground(self):
        from core.kit import Builder
        from core.styles.african import parts
        for tilt, lean in ((0.0, 0.0), (math.pi / 2, 0.0), (math.pi / 2, 1.0), (0.3, 2.0)):
            piece = {"kind": "barrel", "x": 1.0, "y": -0.5, "tilt": tilt, "lean": lean, "turn": 0.7}
            b = Builder(256, True)
            parts.declare(b, [piece], True)
            b.pack()
            b._african_facades = {}
            parts.emit(b, [piece], True)
            zs = [q[2] for f in b.faces for q in f.pts]
            self.assertAlmostEqual(min(zs), 0.0, places=6)
            if tilt == math.pi / 2:                        # lying: no higher than it is round
                self.assertLess(max(zs), 0.6)

    def test_a_prop_is_exported_as_one(self):
        kind, folder = props.game(building.clamp_params(building.prop("BROKEN_CART")))
        self.assertEqual((kind, folder), ("PROP", "nuggets"))
        self.assertEqual(props.game(building.clamp_params(building.prop("ROCKS")))[1], "objects")


if __name__ == "__main__":
    unittest.main(verbosity=2)
