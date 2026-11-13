# SPDX-License-Identifier: GPL-3.0-or-later
"""Several meshes on one texture (core/group.py) and generated prop sets (core/styles/props/sets.py),
without Blender:

    venv/Scripts/python -I tests/test_group.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import group, paint  # noqa: E402
from core.styles.props import sets  # noqa: E402


def square(n=1.0):
    """A flat square of side n metres with its UVs over the whole image: two triangles."""
    pos = [(0, 0, 0), (n, 0, 0), (n, n, 0), (0, n, 0)]
    uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
    return pos, uvs, [(0, 1, 2), (0, 2, 3)]


class Pack(unittest.TestCase):
    def test_texel_is_uv_length_per_metre(self):
        pos, uvs, tris = square(2.0)
        self.assertAlmostEqual(group.texel(uvs, tris, pos), 0.5)

    def test_every_mesh_lands_at_one_density_and_no_two_boxes_overlap(self):
        items = [("big", 0.25, (0.0, 0.0, 1.0, 1.0)), ("small", 1.0, (0.0, 0.0, 1.0, 1.0)),
                 ("strip", 0.5, (0.0, 0.0, 1.0, 0.25))]
        atlas = group.plan(items, 512)
        per_metre = {n: atlas[n].w / (atlas[n].world_w) for n, _, _ in items}
        self.assertLess(max(per_metre.values()) / min(per_metre.values()), 1.1, per_metre)
        self.assertGreater(atlas["big"].w, 3 * atlas["small"].w)     # 4 m against 1 m of surface
        rects = [atlas[n] for n, _, _ in items]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertTrue(a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y)

    def test_each_meshs_pixels_are_found_again_through_its_new_uvs(self):
        rng = np.random.default_rng(1)
        imgs = {"a": np.full((64, 64, 4), (200, 30, 30, 255), np.uint8),
                "b": np.full((32, 32, 4), (30, 200, 30, 255), np.uint8),
                "c": rng.integers(0, 255, (16, 16, 4), dtype=np.uint8)}
        imgs["c"][:, :, 3] = 255
        imgs["c"][:, :8, :3] = (30, 30, 200)
        boxes = {"a": (0.0, 0.0, 1.0, 1.0), "b": (0.0, 0.0, 1.0, 1.0), "c": (0.0, 0.0, 0.5, 1.0)}
        crops, snapped = {}, {}
        for n, img in imgs.items():
            (x0, y0, x1, y1), snapped[n] = group.snap(boxes[n], img.shape)
            crops[n] = img[y0:y1, x0:x1]
        atlas = group.plan([(n, 1.0, snapped[n]) for n in imgs], 256)
        out = group.composite(atlas, crops)
        for n, colour in (("a", (200, 30, 30)), ("b", (30, 200, 30)), ("c", (30, 30, 200))):
            uv = group.remap([(0.25, 0.5), (0.4, 0.6) if n == "c" else (0.75, 0.25)], snapped[n], atlas[n], 256)
            for u, v in uv:
                px = out[int((1 - v) * 256), int(u * 256), :3]
                self.assertLess(int(np.abs(px.astype(int) - colour).max()), 4, (n, px))
            self.assertTrue(((uv >= 0) & (uv <= 1)).all())

    def test_the_gutters_take_the_edge_colour_not_grey(self):
        atlas = group.plan([("a", 1.0, (0, 0, 1, 1)), ("b", 1.0, (0, 0, 1, 1))], 128)
        out = group.composite(atlas, {"a": np.full((8, 8, 4), (250, 0, 0, 255), np.uint8),
                                      "b": np.full((8, 8, 4), (0, 0, 250, 255), np.uint8)})
        r = atlas["a"]
        if r.x + r.w + 1 < 128:
            self.assertEqual(tuple(out[r.y + 1, r.x + r.w + 1, :3]), (250, 0, 0))


class GeneratedSets(unittest.TestCase):
    def test_every_variant_is_centred_and_all_share_one_atlas(self):
        for name in sets.SETS:
            with self.subTest(name=name):
                models, combined = sets.build_set(name)
                self.assertEqual(len(models), len(sets.SETS[name]))
                for m in models:
                    self.assertIs(m.atlas, combined.atlas)
                    xs = [q[0] for f in m.faces for q in f.pts]
                    ys = [q[1] for f in m.faces for q in f.pts]
                    self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0.0, places=6)
                    self.assertAlmostEqual((min(ys) + max(ys)) / 2, 0.0, places=6)
                    self.assertAlmostEqual(min(q[2] for f in m.faces for q in f.pts), 0.0, places=6)
                    self.assertLessEqual(sum(len(f.pts) - 2 for f in m.faces), 268)   # a settlement piece's upper quartile
                rgba = paint.paint_rgba(combined)
                self.assertEqual(rgba.shape, (256, 256, 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
