# SPDX-License-Identifier: GPL-3.0-or-later
"""Every African preset at medium detail within its class's triangle target (the median of the
target mod's own building models, +-15 %), and its low detail under half of that.

    venv\\Scripts\\python -I tests\\test_african_budget.py
"""
import dataclasses
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building  # noqa: E402
from core.styles.african import sizes  # noqa: E402


def tris(p, detail):
    return sum(len(f.pts) - 2 for f in building.build(dataclasses.replace(p, detail=detail)).faces)


class AfricanBudget(unittest.TestCase):
    def test_every_preset_near_its_class_target(self):
        for key, p in building.PRESETS.items():
            if p.style != "AFRICAN":
                continue
            with self.subTest(key):
                med, low = tris(p, "MEDIUM"), tris(p, "LOW")
                t, lo, hi = sizes.tris_target(p.building_type)
                self.assertTrue(lo <= med <= hi, (key, med, (lo, hi)))
                self.assertGreater(med, 2 * low, key)


if __name__ == "__main__":
    unittest.main()
