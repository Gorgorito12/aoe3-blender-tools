# SPDX-License-Identifier: GPL-3.0-or-later
"""Every wall of an African building has its own face: what is painted on it differs from wall to
wall, keeps off the openings, and repeats with the same seed.

    venv\\Scripts\\python -I tests\\test_african_facade.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building  # noqa: E402
from core.styles.african import facade  # noqa: E402


def plans(p):
    m = building.build(p)
    out = {}
    for region, spec in m.facades.items():
        r = m.atlas[region]
        kind = "round" if spec["kind"] == "round" else ("adobe" if spec.get("sahel", True) else "mud")
        if spec["kind"] == "round":
            span = [(spec["door"] - 0.8, spec["door"] + 0.8)] if spec["door"] is not None else []
        else:
            span = [(a, c) for a, _, c, _ in spec["openings"]]
        out[region] = (r.world_w, facade.plan(p.seed, region, r.world_w, r.world_h, kind, p.building_type, span), span)
    return out


class Faces(unittest.TestCase):
    def test_long_walls_are_never_the_same(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN":
                continue
            walls = [m for w, m, _ in plans(p).values() if w >= 3.0 and m]
            with self.subTest(key):
                self.assertEqual(len({tuple(m) for m in walls}), len(walls))

    def test_motifs_keep_off_the_openings(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN":
                continue
            for region, (w, motifs, span) in plans(p).items():
                for name, u, v in motifs:
                    half = facade.SIZES[name][0] / 2
                    for a, c in span:
                        with self.subTest(key=key, region=region, motif=name):
                            self.assertFalse(u + half > a and u - half < c)

    def test_the_same_wall_comes_out_the_same(self):
        self.assertEqual(facade.plan(1, "bk1_front", 6.0, 3.5, "adobe", "ARMORY"),
                         facade.plan(1, "bk1_front", 6.0, 3.5, "adobe", "ARMORY"))

    def test_a_buildings_use_shows_on_its_walls(self):
        p = building.PRESETS["AFRICAN_ARMORY_SAHEL"]
        names = {n for _, m, _ in plans(p).values() for n, _, _ in m}
        self.assertTrue(names & {"shield", "spears", "soot"}, names)


if __name__ == "__main__":
    unittest.main()
