# SPDX-License-Identifier: GPL-3.0-or-later
"""The logic of the African skins, measured on the final texture: a flat roof is lighter and
smoother than the walls under it, never the same surface.

    venv\\Scripts\\python -I tests\\test_african_skin.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import airepaint, building, paint  # noqa: E402

W = np.array([0.299, 0.587, 0.114], np.float32)


def blur(a, r=4):
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += np.roll(np.roll(a, dy, 0), dx, 1)
    return out / (2 * r + 1) ** 2


def grain(lum):
    return float((lum - blur(lum))[4:-4, 4:-4].std() / max(float(lum.mean()), 1.0))


class Roofs(unittest.TestCase):
    def test_flat_roofs_are_lighter_and_smoother_than_walls(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN" or p.architecture != "SAHEL":
                continue
            m = building.build(p)
            names = list(m.atlas.regions)
            walls = [n for n in names if n.startswith("bk")]
            if "roof_flat" not in names or not walls:
                continue
            tex = np.asarray(paint.paint(m)).astype(np.float32)

            def lum(region):
                x0, y0, x1, y1 = airepaint.region_rect(m, tex, region)
                return tex[y0:y1, x0:x1, :3] @ W
            roof = lum("roof_flat")
            with self.subTest(key):
                wall = max((lum(n) for n in walls), key=lambda a: a.size)
                self.assertGreater(float(roof.mean()), float(wall.mean()) * 1.1, "the roof is not lighter")
                self.assertLess(grain(roof), grain(wall), "the roof is not smoother")


if __name__ == "__main__":
    unittest.main()
