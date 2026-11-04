# SPDX-License-Identifier: GPL-3.0-or-later
"""Generated buildings are shaped like the real ones: the numbers of tools/shape_survey.py, measured
on the game's and the target mod's models (the profile's `shape`), hold for every African preset.
A building is one mass, covers its ground, is as tall as the real ones of its size and has levels.

    venv\\Scripts\\python -I tests\\test_shape.py
"""
import dataclasses
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import shape_survey  # noqa: E402
from core import building, profile  # noqa: E402


def measured(params):
    """The shape of a preset at medium detail, as a real model is measured."""
    m = building.build(dataclasses.replace(params, detail="MEDIUM"))
    pts, tris = [], []
    for f in m.faces:
        n = len(pts)
        pts += [tuple(c * shape_survey.UNITS_PER_METER for c in q) for q in f.pts]
        tris += [(n, n + i, n + i + 1) for i in range(1, len(f.pts) - 1)]
    V, T = np.array(pts, np.float32), np.array(tris)
    rx, rz = building.obstruction(params)
    facts = {"upm": shape_survey.UNITS_PER_METER, "up": (0.0, 0.0, 1.0), "textures": 1, "materials": 1}
    return shape_survey.measure(V, np.zeros((len(V), 2), np.float32), T, facts, rx, rz)


def rules(c, flat_roofs=True):
    """(number, lowest, highest) for a class: from the real models' quartiles. Levels count flat
    roofs: a building under thatch has none to count."""
    out = [("height", c["height"][0], None), ("cover", c["cover"][0], None), ("main", 0.9, None),
           ("parts", None, max(3.0, c["parts"][2]))]
    return out + ([("levels", 2, None)] if flat_roofs else [])


class Shape(unittest.TestCase):
    def test_every_preset_is_shaped_like_the_real_ones(self):
        table = profile.load().data["shape"]
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN" or p.building_type == "PLOT":
                continue
            r = building.reference(p)[0]
            cls = table.get(f"{2 * r:g}x{2 * r:g}") or table["all"]
            s = measured(p)
            flat = p.architecture == "SAHEL" and p.building_type != "GRANARY"   # silos end in domes
            for name, lo, hi in rules(cls, flat):
                with self.subTest(key=key, number=name):
                    if lo is not None:
                        self.assertGreaterEqual(s[name], lo)
                    if hi is not None:
                        self.assertLessEqual(s[name], hi)


if __name__ == "__main__":
    unittest.main()
