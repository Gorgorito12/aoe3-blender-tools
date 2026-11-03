# SPDX-License-Identifier: GPL-3.0-or-later
"""Region repainting against a stand-in ComfyUI (no GPU): sizes, alpha, untouched regions,
player-colour pixels and alignment.

    venv\\Scripts\\python -I tests\\test_airepaint.py
"""
import dataclasses
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import airepaint, building, comfy, paint  # noqa: E402
from fake_comfy import FakeComfy  # noqa: E402


def noisy(rgb):
    """What a repaint might do: grain and a colour drift, the drawing in place."""
    rng = np.random.default_rng(int(rgb.sum()) % 1000)
    out = rgb.astype(np.int32) + rng.integers(-18, 19, rgb.shape) + np.array([12, -6, 4])
    return np.clip(out, 0, 255).astype(np.uint8)


class Helpers(unittest.TestCase):
    def test_tiles_cover_and_stay_short(self):
        for w, h in ((300, 100), (100, 300), (90, 90), (1000, 41)):
            ts = airepaint.tiles(w, h)
            cover = np.zeros((h, w), bool)
            for x0, y0, x1, y1 in ts:
                cover[y0:y1, x0:x1] = True
                self.assertLessEqual(max(x1 - x0, y1 - y0), airepaint.TILE_ASPECT * min(x1 - x0, y1 - y0) + 1)
            self.assertTrue(cover.all(), (w, h))

    def test_resize_keeps_a_flat_image_flat(self):
        img = np.full((37, 53, 3), 120, np.uint8)
        for h, w in ((100, 140), (12, 20)):
            out = airepaint.resize(img, h, w)
            self.assertEqual(out.shape, (h, w, 3))
            self.assertAlmostEqual(float(out.min()), 120.0, places=3)
            self.assertAlmostEqual(float(out.max()), 120.0, places=3)

    def test_edge_shift_finds_a_move(self):
        a = np.zeros((60, 60, 3), np.uint8)
        a[20:40, 15:30] = 255
        b = np.roll(a, 2, axis=1)
        self.assertEqual(airepaint.edge_shift(a, a), (0, 0))
        self.assertEqual(airepaint.edge_shift(a, b), (2, 0))


class Repaint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = dataclasses.replace(building.PRESETS["COLONIAL_HOUSE"], texture_size=512, player_colour=True)
        cls.model = building.build(cls.p)
        cls.tex = paint.paint_rgba(cls.model)
        with FakeComfy(transform=noisy) as fake:
            cls.out, cls.report = airepaint.repaint(cls.tex, cls.model, comfy.Client(fake.url), strength=0.4, seed=3)
            cls.prompts = list(fake.prompts)

    def test_size_and_alpha_kept(self):
        self.assertEqual(self.out.shape, self.tex.shape)
        self.assertTrue((self.out[:, :, 3] == self.tex[:, :, 3]).all())

    def test_regions_repainted_or_skipped_with_a_reason(self):
        done = [r["region"] for r in self.report if "skipped" not in r]
        self.assertIn("front", done)
        self.assertIn("roof", done)
        self.assertTrue(all(r.get("skipped") or r.get("tiles") for r in self.report))
        self.assertEqual(len(self.prompts), sum(r.get("tiles", 0) for r in self.report))
        ks = [n for wf in self.prompts for n in wf.values() if n["class_type"] == "KSampler"]
        self.assertTrue(all(abs(k["inputs"]["denoise"] - 0.4) < 1e-9 for k in ks))

    def test_only_repainted_regions_changed(self):
        changed = (self.out[:, :, :3] != self.tex[:, :, :3]).any(axis=2)
        inside = np.zeros(changed.shape, bool)
        for r in self.report:
            if "skipped" not in r:
                x0, y0, x1, y1 = airepaint.region_rect(self.model, self.tex, r["region"])
                inside[y0:y1, x0:x1] = True
        self.assertFalse(changed[~inside].any(), "a pixel outside the repainted regions changed")
        self.assertGreater(changed[inside].mean(), 0.5)

    def test_player_colour_pixels_kept(self):
        keep = self.tex[:, :, 3] < 255
        self.assertGreater(keep.sum(), 0)
        self.assertTrue((self.out[:, :, :3][keep] == self.tex[:, :, :3][keep]).all())

    def test_nothing_moved_and_colour_kept(self):
        for r in self.report:
            if "skipped" in r:
                continue
            x0, y0, x1, y1 = airepaint.region_rect(self.model, self.tex, r["region"])
            a, b = self.tex[y0:y1, x0:x1], self.out[y0:y1, x0:x1]
            self.assertEqual(airepaint.edge_shift(a, b), (0, 0), r["region"])
            d = np.abs(a[:, :, :3].reshape(-1, 3).mean(0) - b[:, :, :3].reshape(-1, 3).mean(0)).max()
            self.assertLess(d, 3.0, r["region"])

    def test_blend_zero_changes_nothing(self):
        with FakeComfy(transform=noisy) as fake:
            out, _ = airepaint.repaint(self.tex, self.model, comfy.Client(fake.url), strength=0.4, seed=3,
                                       regions=["front"], blend=0.0)
        self.assertTrue((out == self.tex).all())


class Guard(unittest.TestCase):
    def test_a_region_whose_edges_move_is_kept(self):
        p = dataclasses.replace(building.PRESETS["COLONIAL_HOUSE"], texture_size=512)
        model = building.build(p)
        tex = paint.paint_rgba(model)
        with FakeComfy(transform=lambda rgb: np.roll(rgb, 6, axis=1)) as fake:
            out, report = airepaint.repaint(tex, model, comfy.Client(fake.url), strength=0.5, seed=1,
                                            regions=["front"])
        r = report[0]
        self.assertIn("kept", r.get("skipped", ""))
        self.assertEqual(len(fake.prompts), 2 * len(airepaint.tiles(*[v + 2 * airepaint.MARGIN for v in (
            airepaint.region_rect(model, tex, "front")[2] - airepaint.region_rect(model, tex, "front")[0],
            airepaint.region_rect(model, tex, "front")[3] - airepaint.region_rect(model, tex, "front")[1])])))
        self.assertTrue((out == tex).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
