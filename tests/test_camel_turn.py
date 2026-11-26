# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/camel_turn.py: the TURN and RISE sections' bytes (the layout the DLL's turretArc reads), their place in an
aim file, and the stepping cycle's seams. No game files needed."""
import math
import os
import struct
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))

import camel_turn as ct  # noqa: E402


def aim_file(version=2, yaws=(30.0, 90.0, 150.0), bones=("Bip01 L Hand",), clips=(("fire", 3),), band=False):
    """A small aim file laid out as make_gun_camel.aim_table writes one."""
    out = [b"UHCA", struct.pack("<I", version), ct.name32("bone_yaw"), ct.name32("bone_turret"),
           struct.pack("<3f", 0.1, 0.2, 0.3), struct.pack("<3f", 0.4, 0.5, 0.6)]
    if version >= 2:
        out.append(struct.pack("<f", 90.0))
    out += [struct.pack("<I", len(yaws)), struct.pack(f"<{len(yaws)}f", *yaws), struct.pack("<I", len(bones))]
    out += [ct.name32(b) for b in bones]
    out.append(struct.pack("<I", len(clips)))
    for name, frames in clips:
        out += [name.encode().ljust(64, b"\0"), struct.pack("<fI", 1.0, frames),
                np.arange(frames * len(yaws) * len(bones) * 7, dtype="<f4").tobytes()]
    if band:
        out += [b"BAND", struct.pack("<I", 1), struct.pack("<2f", 40.0, 50.0)]
        out += [b"SETL", struct.pack("<I", 1), b"fire".ljust(64, b"\0"), struct.pack("<fI", 1.0, 3),
                np.zeros(2 * 3 * len(yaws) * len(bones) * 7, "<f4").tobytes()]
    return b"".join(out)


def parts(points=4, nb=3, ng=2):
    body = np.arange(2 * points * nb * 7, dtype=np.float32).reshape(2, points, nb, 7)
    gun = -np.arange(2 * points * ng * 7, dtype=np.float32).reshape(2, points, ng, 7)
    return ([f"body {i}" for i in range(nb)], body), ([f"gunner {i}" for i in range(ng)], gun)


class Section(unittest.TestCase):
    def test_layout_is_the_dlls(self):
        """The order ReadAim reads: TURN, u32 1, step, rise, settle, rate, points; then the body's part and
        the gunner's, each its count, its 32-byte names and float32 [way][point][bone][7]."""
        body, gunner = parts()
        data = ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner)
        self.assertEqual(data[:4], b"TURN")
        self.assertEqual(struct.unpack_from("<I4fI", data, 4), (1, 30.0, 0.30000001192092896, 0.30000001192092896, 90.0, 4))
        at = 28
        self.assertEqual(struct.unpack_from("<I", data, at)[0], 3)
        self.assertEqual(data[at + 4:at + 36].rstrip(b"\0"), b"body 0")
        at += 4 + 3 * 32
        first = struct.unpack_from("<7f", data, at)
        self.assertEqual(first, tuple(float(v) for v in body[1][0, 0, 0]))
        # [way 1][point 0][bone 0] comes after way 0's points
        way1 = at + 4 * (4 * 3 * 7)
        self.assertEqual(struct.unpack_from("<f", data, way1)[0], float(body[1][1, 0, 0, 0]))
        at += 4 * body[1].size
        self.assertEqual(struct.unpack_from("<I", data, at)[0], 2)
        self.assertEqual(data[at + 4:at + 36].rstrip(b"\0"), b"gunner 0")
        self.assertEqual(len(data), at + 4 + 2 * 32 + 4 * gunner[1].size)

    def test_round_trip(self):
        body, gunner = parts()
        data = ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner)
        step, rise, settle, rate, got, end = ct.read_turn_section(data)
        self.assertEqual((step, rate, end), (30.0, 90.0, len(data)))
        self.assertEqual(got[0][0], body[0])
        np.testing.assert_array_equal(got[1][1], gunner[1])

    def test_a_part_of_the_wrong_shape_is_refused(self):
        body, gunner = parts()
        with self.assertRaises(ValueError):
            ct.turn_section(30.0, 0.3, 0.3, 90.0, (body[0][:2], body[1]), gunner)

    def test_rise_follows_turn(self):
        body, gunner = parts()
        """RISE version 2: b"RISE", u32 2, u32 K, then the body's [way 2][K][bone][7] and the gunner's (way 0
        then way 1), TURN's bones in TURN's order: the layout the DLL reads."""
        rise = (np.arange(2 * 5 * 3 * 7, dtype=np.float32).reshape(2, 5, 3, 7),
                -np.arange(2 * 5 * 2 * 7, dtype=np.float32).reshape(2, 5, 2, 7))
        data = ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner) + ct.rise_section(*rise)
        *_x, end = ct.read_turn_section(data)
        self.assertEqual(data[end:end + 4], b"RISE")
        self.assertEqual(struct.unpack_from("<II", data, end + 4), (2, 5))
        # [way 1][k 0][bone 0] follows way 0's five poses of three bones
        self.assertEqual(struct.unpack_from("<f", data, end + 12 + 4 * 5 * 3 * 7)[0], float(rise[0][1, 0, 0, 0]))
        b, g, stop = ct.read_rise_section(data, end, 3, 2)
        self.assertEqual(stop, len(data))
        np.testing.assert_array_equal(b, rise[0])
        np.testing.assert_array_equal(g, rise[1])
        with self.assertRaises(ValueError):
            ct.rise_section(rise[0][0], rise[1][0])        # no way: refused


class InTheAimFile(unittest.TestCase):
    def test_appended_after_every_section_and_replaced(self):
        body, gunner = parts()
        for aim in (aim_file(), aim_file(band=True), aim_file(version=1)):
            self.assertEqual(ct.aim_sections(aim), (None, len(aim)))
            sec = ct.turn_section(30.0, 0.3, 0.3, 90.0, body, gunner) + ct.rise_section(
                np.ones((2, 2, 3, 7)), np.ones((2, 2, 2, 7)))
            new = ct.with_turn(aim, sec)
            self.assertTrue(new.startswith(aim))
            self.assertEqual(ct.aim_sections(new), (len(aim), len(new)))
            again = ct.with_turn(new, sec)
            self.assertEqual(again, new)

    def test_trailing_bytes_are_refused(self):
        with self.assertRaises(ValueError):
            ct.with_turn(aim_file() + b"junk1234", b"")


class Cycle(unittest.TestCase):
    def test_a_step_ends_where_it_began(self):
        for s in (1.0, -1.0):
            for lead in (True, False):
                a0, h0 = ct.foot_cycle(0.0, s, 30.0, lead)
                a1, h1 = ct.foot_cycle(1.0 - 1e-9, s, 30.0, lead)
                self.assertAlmostEqual(a0, 0.0)
                self.assertAlmostEqual(a1, 0.0, places=5)
                self.assertAlmostEqual(h0, 0.0)
                self.assertAlmostEqual(h1, 0.0, places=5)

    def test_a_planted_foot_stays_put_in_the_world(self):
        """The model turns s * p * step; a planted foot's angle in the model is the opposite, so in the world
        it does not move while it is planted."""
        for s in (1.0, -1.0):
            for lead, planted in ((True, np.linspace(0.5, 0.99, 8)), (False, np.linspace(0.0, 0.49, 8))):
                world = [ct.foot_cycle(p, s, 30.0, lead)[0] + s * p * 30.0 for p in planted]
                self.assertLess(max(world) - min(world), 1e-9)
                self.assertEqual({ct.foot_cycle(p, s, 30.0, lead)[1] for p in planted}, {0.0})

    def test_the_lead_foot_is_the_one_ahead(self):
        # two hooves side by side ahead of the origin: turning right (+x), the right one leads
        left, right = np.array([-0.2, 0.0, 1.0]), np.array([0.2, 0.0, 1.0])
        self.assertTrue(ct.lead_of(right, left, 1.0))
        self.assertTrue(ct.lead_of(left, right, -1.0))
        # behind the origin the rump swings the other way
        self.assertTrue(ct.lead_of(left * [1, 1, -1], right * [1, 1, -1], 1.0))

    def test_heading(self):
        z = np.array([0.0, 0.0, 1.0])
        v = ct.rot_heading(90.0) @ z
        self.assertAlmostEqual(math.degrees(math.atan2(v[0], v[2])), 90.0)

    def test_timeline_is_the_dlls(self):
        """ShownHeading: smoothstep lift over the rise, 1 between, 1 - smoothstep over the settle; the phase is
        |by| * share turned / step, mod 1."""
        tl = ct.turn_timeline(90.0, step=60.0, rise=0.3, settle=0.3, rate=90.0)
        self.assertAlmostEqual(tl[-1][0], 1.6)
        self.assertEqual(tl[0][2], 0.0)
        self.assertEqual(tl[-1][2], 0.0)
        self.assertAlmostEqual(tl[-1][1], 90.0)
        mid = [x for x in tl if 0.35 < x[0] < 1.25]
        self.assertTrue(all(x[2] == 1.0 for x in mid))
        t, _h, lift, _p = tl[3]                               # 0.1 s into the rise
        self.assertAlmostEqual(lift, ct.smooth(0.1 / 0.3), places=6)
        t, h, lift, phase = tl[24]                            # 0.8 s: 0.5 s of the 1 s turn
        self.assertAlmostEqual(phase, (90.0 * 0.5 / 60.0) % 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
