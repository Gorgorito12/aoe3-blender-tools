# SPDX-License-Identifier: GPL-3.0-or-later
"""The preview renderers draw the game's space as the game does. A unit facing +z has its right hand
at +x (its R bones; in game the explorer's pistol, on Bip01 Prop1 under Bip01 R Hand, is in his
right hand, 2026-11-26): seen from the front, the unit's right is on the screen's left, and seen from
its right side (azimuth 90) it faces the screen's right. Before that date retarget_anims.draw,
check_anim's and make_dismount's renderers drew the mirror image.

    venv\\Scripts\\python -I tests\\test_render_handedness.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import retarget_anims as ra  # noqa: E402

RED, BLUE = (220, 0, 0), (0, 0, 220)


def square(x, z, size=0.2, y=1.0):
    """A square facing every way's a cube: two crossed quads at (x, y, z)."""
    p = np.array([[x - size, y - size, z], [x + size, y - size, z], [x + size, y + size, z], [x - size, y + size, z],
                  [x, y - size, z - size], [x, y - size, z + size], [x, y + size, z + size], [x, y + size, z - size]],
                 np.float64)
    t = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
    return p, t


def scene(right_colour=RED, left_colour=BLUE, nose=True):
    """The unit's right (+x) red, its left (-x) blue, and its nose (+z) green."""
    items = []
    for x, col in ((0.8, right_colour), (-0.8, left_colour)):
        p, t = square(x, 0.0)
        items.append((p, t, None, None, col))
    if nose:
        p, t = square(0.0, 0.8, size=0.1)
        items.append((p, t, None, None, (0, 200, 0)))
    return items


def centre_x(img, colour):
    m = (np.abs(img.astype(int) - np.array(colour)).sum(2) < 120)
    ys, xs = np.nonzero(m)
    return xs.mean() if len(xs) else None


class Handedness(unittest.TestCase):
    def draw(self, az):
        return ra.draw(scene(), width=200, height=200, azimuth=az, elevation=0.0, span=3.0,
                       centre=(0.0, 1.0, 0.0)).astype(np.uint8)

    def test_seen_from_the_front_the_units_right_is_on_the_screens_left(self):
        img = self.draw(0.0)
        self.assertLess(centre_x(img, RED), 100)
        self.assertGreater(centre_x(img, BLUE), 100)

    def test_seen_from_its_right_side_it_faces_the_screens_right(self):
        img = self.draw(90.0)
        self.assertGreater(centre_x(img, (0, 200, 0)), 100)   # the nose (+z)

    def test_the_old_right_handed_picture_is_the_mirror_image(self):
        new = self.draw(0.0)
        old = ra.draw(scene(), width=200, height=200, azimuth=0.0, elevation=0.0, span=3.0,
                      centre=(0.0, 1.0, 0.0), mirror=False).astype(np.uint8)
        self.assertTrue(np.array_equal(new[:, ::-1], old))

    def test_the_camel_drawing_agrees(self):
        import make_gun_camel as mgc
        img = mgc.draw(scene(), width=200, height=200, azimuth=0.0, elevation=0.0, span=3.0,
                       centre=(0.0, 1.0, 0.0), ground=False).astype(np.uint8)
        self.assertLess(centre_x(img, RED), 100)
        img = mgc.draw(scene(), width=200, height=200, azimuth=90.0, elevation=0.0, span=3.0,
                       centre=(0.0, 1.0, 0.0), ground=False).astype(np.uint8)
        self.assertGreater(centre_x(img, (0, 200, 0)), 100)


if __name__ == "__main__":
    unittest.main()
