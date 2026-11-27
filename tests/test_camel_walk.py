# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/camel_walk.py: the WALK section's bytes (the layout the DLL's turretArc reads), its place in an aim file
after TURN and RISE, the stepping cycle in a line and the DLL's rule for the rise and the settle. No game files
needed."""
import os
import struct
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))

import camel_turn as ct  # noqa: E402
import camel_walk as cw  # noqa: E402
from test_camel_turn import aim_file, parts  # noqa: E402


def walk_parts(points=4, k=3, sizes=(3, 2, 1)):
    out, rises = [], []
    for j, nb in enumerate(sizes):
        out.append(([f"part{j} {i}" for i in range(nb)],
                    (j + 1) * np.arange(points * nb * 7, dtype=np.float32).reshape(points, nb, 7)))
        rises.append(-(j + 1) * np.arange(k * nb * 7, dtype=np.float32).reshape(k, nb, 7))
    return out, rises


class Section(unittest.TestCase):
    def test_layout_is_the_dlls(self):
        """The order ReadAim reads: WALK, u32 1, stride, rise, settle, rate, from, u32 points, K, clip count, the
        64-byte clip names, then the body's, the gunner's and the gun's part: each its count, its 32-byte names,
        float32 [point][bone][7] and its rise [K][bone][7]."""
        prts, rises = walk_parts()
        data = cw.walk_section(1.0, 0.45, 0.45, 120.0, ["a_deployed", "a_fire"], prts, rises)
        self.assertEqual(data[:4], b"WALK")
        got = struct.unpack_from("<I5fIII", data, 4)
        self.assertEqual(got[0], 1)
        self.assertAlmostEqual(got[1], 1.0)
        self.assertAlmostEqual(got[5], cw.OFFSET_FROM, places=6)
        self.assertEqual(got[6:], (4, 3, 2))
        at = 40
        self.assertEqual(data[at:at + 64].rstrip(b"\0"), b"a_deployed")
        at += 2 * 64
        self.assertEqual(struct.unpack_from("<I", data, at)[0], 3)
        self.assertEqual(data[at + 4:at + 36].rstrip(b"\0"), b"part0 0")
        at += 4 + 3 * 32
        self.assertEqual(struct.unpack_from("<7f", data, at), tuple(float(v) for v in prts[0][1][0, 0]))
        at += 4 * prts[0][1].size
        self.assertEqual(struct.unpack_from("<f", data, at + 4)[0], float(rises[0][0, 0, 1]))
        at += 4 * rises[0].size
        self.assertEqual(struct.unpack_from("<I", data, at)[0], 2)

    def test_round_trip(self):
        prts, rises = walk_parts()
        data = cw.walk_section(1.0, 0.45, 0.45, 120.0, ["x"], prts, rises)
        stride, rise, settle, rate, frm, clips, got, end = cw.read_walk_section(data, 0)
        self.assertEqual((clips, end), (["x"], len(data)))
        for (names, arr, r), (n0, a0), r0 in zip(got, prts, rises):
            self.assertEqual(names, n0)
            np.testing.assert_array_equal(arr, a0)
            np.testing.assert_array_equal(r, r0)

    def test_a_gun_part_may_be_empty(self):
        prts, rises = walk_parts(sizes=(3, 2, 0))
        data = cw.walk_section(1.0, 0.45, 0.45, 120.0, [], prts, rises)
        *_x, got, end = cw.read_walk_section(data, 0)
        self.assertEqual((got[2][0], end), ([], len(data)))


class InTheAimFile(unittest.TestCase):
    def test_last_after_turn_and_rise_and_replaced(self):
        body, gunner = parts()
        aim = ct.with_turn(aim_file(band=True), ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner) +
                           ct.rise_section(np.ones((2, 2, 3, 7)), np.ones((2, 2, 2, 7))))
        prts, rises = walk_parts()
        sec = cw.walk_section(1.0, 0.45, 0.45, 120.0, ["x"], prts, rises)
        new = cw.with_walk(aim, sec)
        self.assertTrue(new.startswith(aim))
        self.assertEqual(new[len(aim):len(aim) + 4], b"WALK")
        self.assertEqual(cw.with_walk(new, sec), new)

    def test_a_new_turn_keeps_the_walk(self):
        body, gunner = parts()
        turn = ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner) + ct.rise_section(np.ones((2, 2, 3, 7)),
                                                                                    np.ones((2, 2, 2, 7)))
        aim = ct.with_turn(aim_file(), turn)
        prts, rises = walk_parts()
        sec = cw.walk_section(1.0, 0.45, 0.45, 120.0, ["x"], prts, rises)
        new = cw.with_walk(aim, sec)
        self.assertEqual(ct.with_turn(new, turn), new)


class Cycle(unittest.TestCase):
    def test_a_planted_hoof_runs_back_with_the_ground(self):
        # planted, a hoof moves back by the stride's share of the cycle; both pairs swing once a cycle
        for lead in (True, False):
            for p in np.linspace(0.0, 0.99, 100):
                d0, h0 = cw.foot_line(p, 1.0, lead)
                d1, h1 = cw.foot_line(p + 0.005, 1.0, lead)
                if h0 == 0.0 and h1 == 0.0:
                    self.assertAlmostEqual(d1 - d0, -0.005, places=6)
        self.assertEqual(cw.foot_line(0.0, 1.0, True), (0.0, 0.0))
        self.assertEqual(cw.foot_line(0.0, 1.0, False), (0.0, 0.0))

    def test_the_step_shows_once_the_legs_unfold(self):
        self.assertEqual(cw.offset_weight(cw.OFFSET_FROM - 0.01), 0.0)
        self.assertEqual(cw.offset_weight(1.0), 1.0)
        self.assertAlmostEqual(cw.offset_weight(0.5, settling=True), 0.5)

    def test_the_start_counts_the_way_from_the_unfolding(self):
        frames = cw.timeline(2)
        rising = [f for f in frames if 0.0 < f[1] < 1.0 and not f[3]]
        self.assertTrue(all(ph == 0.0 for _t, lift, ph, _s in rising if lift < cw.OFFSET_FROM))
        self.assertTrue(any(ph > 0.0 for _t, _l, ph, _s in frames))


if __name__ == "__main__":
    unittest.main()
