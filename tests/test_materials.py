# SPDX-License-Identifier: GPL-3.0-or-later
"""The material layer (core/materials.py and the Painter's base()), plain Python with numpy:

    venv\\Scripts\\python -I tests\\test_materials.py
"""
import dataclasses
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building, materials, paint  # noqa: E402


def wall_view(model, rgba, cov):
    """The front facade's pixels and coverage at the final size."""
    k = model.atlas.size // model.params.texture_size
    r = model.atlas["front"]
    sl = (slice(r.y // k, (r.y + r.h) // k), slice(r.x // k, (r.x + r.w) // k))
    return rgba[sl], cov[sl]


class Swatches(unittest.TestCase):
    def test_missing_swatch_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(materials.load("nothing_here", folder=d))

    def test_every_mapped_swatch_ships(self):
        for style, roles in materials.MATERIALS.items():
            for role, (name, tile_m, key, contrast) in materials.plan(style).items():
                with self.subTest(style=style, role=role):
                    self.assertIsNotNone(materials.load(name), f"{name}.png is missing")
                    self.assertGreater(tile_m, 0.2)
                    self.assertIn(key, building.BuildingParams().colors)

    def test_normalise(self):
        sw = materials.load("plaster")
        f = materials.normalise(sw, 120)
        self.assertEqual(f.shape, (120, 120))
        self.assertAlmostEqual(float(f.mean()), 1.0, delta=0.01)
        self.assertGreaterEqual(float(f.min()), 0.7)
        self.assertLessEqual(float(f.max()), 1.3)
        fine = f - materials.resample(materials.resample(f[:, :, None], 8), 120)[:, :, 0]
        self.assertAlmostEqual(float(fine.std()), materials.TARGET_CONTRAST, delta=0.01)

    def test_resample_wraps_without_a_seam(self):
        n = 64
        x = np.arange(n) / n
        img = (128 + 60 * np.sin(2 * np.pi * x)[None, :] * np.cos(2 * np.pi * x)[:, None])[:, :, None]
        for px in (40, 100):
            out = materials.resample(img, px)[:, :, 0]
            inner = np.abs(np.diff(out, axis=1)).max()
            seam = np.abs(out[:, 0] - out[:, -1]).max()
            self.assertLessEqual(seam, inner * 1.5 + 1e-6, px)
            self.assertAlmostEqual(float(out.mean()), float(img.mean()), delta=0.5)

    def test_tile_starts_at_the_offset(self):
        a = np.zeros((20, 30, 3), np.float32)
        f = np.arange(12, dtype=np.float32).reshape(3, 4) / 10 + 0.5
        materials.tile(a, (5, 2, 25, 18), f, (100, 100, 100), offset=(5, 2))
        for y, x in ((2, 5), (7, 13), (17, 24)):
            self.assertAlmostEqual(float(a[y, x, 0]), 100 * float(f[(y - 2) % 3, (x - 5) % 4]), places=3)
        self.assertEqual(float(a[0, 0, 0]), 0.0)


class Painting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.off = building.build(building.PRESETS["MANSION"])
        cls.on = building.build(dataclasses.replace(building.PRESETS["MANSION"], materials=True))
        cls.rgba_off, cls.cov_off = paint.paint_layers(cls.off)
        cls.rgba_on, cls.cov_on = paint.paint_layers(cls.on)

    def test_off_has_no_coverage(self):
        self.assertEqual(int(self.cov_off.max()), 0)

    def test_on_changes_the_walls_only(self):
        a, ca = wall_view(self.off, self.rgba_off, self.cov_off)
        b, cb = wall_view(self.on, self.rgba_on, self.cov_on)
        covered = cb == 255
        self.assertGreater(covered.mean(), 0.15)
        changed = (a[:, :, :3] != b[:, :, :3]).any(axis=2)
        self.assertGreater(changed[covered].mean(), 0.5)        # the grain shows on the wall
        bare = self.cov_on == 0
        same = (self.rgba_off[:, :, :3] == self.rgba_on[:, :, :3]).all(axis=2)
        self.assertTrue(same[bare].all(), "a pixel without swatch changed (windows, trims, roof)")
        self.assertTrue((self.rgba_off[:, :, 3] == self.rgba_on[:, :, 3]).all())

    def test_palette_fit(self):
        b, cb = wall_view(self.on, self.rgba_on, self.cov_on)
        mean = b[:, :, :3][cb == 255].reshape(-1, 3).mean(axis=0)
        want = np.array(self.on.params.colors["wall"], np.float32)
        self.assertLess(float(np.abs(mean - want).max()), 6.0, (mean, want))

    def test_missing_swatch_falls_back_to_the_flat_colour(self):
        saved, cache = materials.FOLDER, dict(materials._cache)
        with tempfile.TemporaryDirectory() as d:
            try:
                materials.FOLDER = d
                materials._cache.clear()
                rgba, cov = paint.paint_layers(self.on)
            finally:
                materials.FOLDER = saved
                materials._cache.clear()
                materials._cache.update(cache)
        self.assertEqual(int(cov.max()), 0)
        self.assertTrue((rgba == self.rgba_off).all())


class ColonialPainting(unittest.TestCase):
    def test_swatches_change_only_their_regions(self):
        off = building.build(dataclasses.replace(building.PRESETS["COLONIAL_HOUSE"], texture_size=512))
        on = building.build(dataclasses.replace(building.PRESETS["COLONIAL_HOUSE"], texture_size=512,
                                                materials=True))
        a, _ = paint.paint_layers(off)
        b, cov = paint.paint_layers(on)
        bare = cov == 0
        self.assertGreater(float((cov == 255).mean()), 0.1)
        self.assertTrue(((a[:, :, :3] == b[:, :, :3]).all(axis=2))[bare].all())
        f, cf = wall_view(on, b, cov)
        top = f.shape[0] * 6 // 10                     # above the dado, which is tinted on the plaster
        mean = f[:top, :, :3][cf[:top] == 255].reshape(-1, 3).mean(axis=0)
        want = np.array(on.params.colors["plaster"], np.float32)
        self.assertLess(float(np.abs(mean - want).max()), 6.0, (mean, want))


if __name__ == "__main__":
    unittest.main(verbosity=2)
