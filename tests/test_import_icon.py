# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/import_icon.py, on synthetic pictures. Needs numpy (the venv):

    venv/Scripts/python -I tests/test_import_icon.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import import_icon as ii  # noqa: E402
from aoe3game import ddt  # noqa: E402

INK = (35, 22, 19)


def badge(w=300, h=200, grey=177):
    """A grey box with a 20-pixel dark outline and a dark band, in a transparent margin."""
    a = np.zeros((h + 40, w + 40, 4), np.uint8)
    a[20:20 + h, 20:20 + w] = INK + (255,)
    a[40:h, 40:w, :3] = grey
    a[h // 2:h // 2 + 10, 40:w, :3] = 60
    return a


class Fit(unittest.TestCase):
    def test_format(self):
        data = ii.encode(ii.fit(badge()))
        h = ddt.read_header(data)
        self.assertEqual((h.width, h.height, h.format, h.alpha, h.usage, h.mips), (32, 32, ddt.BGRA, 4, 0, 1))
        self.assertEqual(len(data), 16 + 8 + 32 * 32 * 4)

    def test_centred_with_equal_margins(self):
        for w, h in ((300, 200), (200, 300), (123, 457)):
            icon = ii.fit(badge(w, h), aspect=0.65)
            ys, xs = np.nonzero(icon[..., 3])
            self.assertEqual(xs.min(), 31 - xs.max(), (w, h))
            self.assertEqual(ys.min(), 31 - ys.max(), (w, h))

    def test_widened_by_the_aspect(self):
        tall = np.zeros((640, 320, 4), np.uint8)
        tall[...] = (200, 200, 200, 255)
        ys, xs = np.nonzero(ii.fit(tall, aspect=0.5)[..., 3])
        self.assertEqual((xs.max() - xs.min() + 1, ys.max() - ys.min() + 1), (32, 32))
        ys, xs = np.nonzero(ii.fit(tall, aspect=1.0)[..., 3])
        self.assertEqual((xs.max() - xs.min() + 1, ys.max() - ys.min() + 1), (16, 32))

    def test_one_scale_on_the_bottom_edge(self):
        small = ii.fit(badge(160, 200), aspect=1.0, set_height=480, valign="bottom")
        ys, xs = np.nonzero(small[..., 3])
        self.assertEqual(ys.max(), 31)
        self.assertEqual(ys.max() - ys.min() + 1, 13)     # its 200 visible rows of 480: 13.3 texels
        with self.assertRaises(ValueError):
            ii.fit(badge(160, 200), set_height=100)

    def test_transparent_texels_have_no_colour(self):
        icon = ii.fit(badge())
        self.assertTrue((icon[icon[..., 3] == 0, :3] == 0).all())


class Tint(unittest.TestCase):
    def test_region_stops_at_the_outline(self):
        a = badge()
        a[:, :, 3][:, :] = 255           # even a visible background outside the outline is not reached
        a[:20, :, :3] = 200
        m = ii.region(a, (100, 60))
        self.assertTrue(m[60, 100] and m[105, 100])   # the face and the band
        self.assertFalse(m[25, 100] or m[5, 100])     # the outline and what lies beyond it

    def test_ramp(self):
        a = badge()
        t = ii.tint(a, ii.region(a, (100, 60)), (199, 90, 33), mid=177)
        self.assertEqual(tuple(t[60, 100, :3]), (199, 90, 33))          # the face is the colour
        band = t[105, 100, :3].astype(int)
        self.assertTrue((band < (199, 90, 33)).all())                    # the band darker, same hue
        self.assertEqual(tuple(t[25, 100, :3]), INK)                     # the outline kept
        lighter = ii.tint(a, ii.region(a, (100, 60)), (199, 90, 33), lighten=0.2, mid=177)
        self.assertTrue((lighter[60, 100, :3].astype(int) > (199, 90, 33)).all())


if __name__ == "__main__":
    unittest.main()
