# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/make_pie.py. Needs numpy (the venv):

    venv/Scripts/python -I tests/test_pie.py
"""
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import make_pie as mp  # noqa: E402
from aoe3game import ddt  # noqa: E402


def decoded(frame, frames=mp.FRAMES):
    return np.asarray(ddt.decode(mp.encode(frame, frames))).astype(np.int32)


class Pie(unittest.TestCase):
    def test_format(self):
        data = mp.encode(0)
        h = ddt.read_header(data)
        self.assertEqual((h.width, h.height, h.format, h.usage, h.mips), (32, 32, ddt.BGRA, 0, 1))
        self.assertEqual(len(data), 16 + 8 + 32 * 32 * 4)
        self.assertTrue((decoded(0)[..., 3] == 255).all())

    def test_frame_zero_is_all_blue_inside_a_gold_frame(self):
        img = decoded(0)
        b = mp.BORDER
        inside = img[b:-b, b:-b, :3]
        self.assertTrue((np.abs(inside - np.round(mp.COVERED)) <= 1).all())
        ring = np.ones(img.shape[:2], bool)
        ring[b:-b, b:-b] = False
        self.assertTrue((np.abs(img[ring, :3] - mp.GOLD) <= 1).all())

    def test_the_clear_wedge_grows_clockwise_from_twelve(self):
        b = mp.BORDER
        shares = []
        for k in range(mp.FRAMES):
            inside = decoded(k)[b:-b, b:-b, :3].astype(np.float32)
            clear = (inside - mp.COVERED) / (mp.CLEAR - mp.COVERED)
            shares.append(float(clear[..., 2].mean()))
        self.assertLess(shares[0], 0.01)  # all covered, up to the rounding of the covered colour
        self.assertTrue(all(a < c for a, c in zip(shares, shares[1:])))
        for k, share in enumerate(shares):
            self.assertAlmostEqual(share, k / mp.FRAMES, delta=0.02)
        # a quarter done: the top right quadrant is clear, the top left one still covered
        img = decoded(mp.FRAMES // 4 + 1)
        n = mp.SIZE
        self.assertTrue((np.abs(img[b + 2, n - b - 3, :3] - np.round(mp.CLEAR)) <= 1).all())
        self.assertTrue((np.abs(img[b + 2, b + 2, :3] - np.round(mp.COVERED)) <= 1).all())

    def test_check_finds_a_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mp.main(["--out", tmp, "--frames", "4"]), 0)
            self.assertEqual(sorted(os.listdir(tmp)), [f"pie_{k:02d}.ddt" for k in range(4)])
            self.assertEqual(mp.main(["--out", tmp, "--frames", "4", "--check"]), 0)
            with open(os.path.join(tmp, "pie_02.ddt"), "r+b") as f:
                f.seek(100)
                f.write(b"\x00")
            self.assertEqual(mp.main(["--out", tmp, "--frames", "4", "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
