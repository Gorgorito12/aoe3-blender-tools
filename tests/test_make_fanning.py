# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces of tools/make_fanning.py that need no game: the timing of the shots and their tags, the
left palm's schedule, the pistol's kick, the hammer measured on a pistol mesh, the keys filled in.

    venv\\Scripts\\python -I tests\\test_make_fanning.py
"""
import os
import re
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import make_fanning as mf  # noqa: E402


class Timing(unittest.TestCase):
    def test_the_game_pace_and_the_real_gap_between_shots(self):
        self.assertAlmostEqual(mf.rate(), (2.2 + 2.0) / 4.5)
        times = mf.shot_times(6)
        gaps = np.diff(times) / mf.rate()
        self.assertTrue(np.allclose(gaps, 0.28, atol=0.001), gaps)
        self.assertAlmostEqual(times[0] / mf.rate(), 0.45, places=2)

    def test_the_last_shot_leaves_time_to_come_back_to_ready(self):
        times = mf.shot_times(6)
        self.assertLess(times[-1] + mf.THROUGH + 0.26, mf.LENGTH["attack"] - 0.05)

    def test_today_the_engine_paced_the_borrowed_clip_at_0_644(self):
        # (0.90 + 2.0) / 4.5: the measured 210 ms between tags 0.15 of a 0.90 s clip apart
        self.assertAlmostEqual(0.15 * 0.9 / mf.rate(0.9), 0.2095, places=3)


class Schedule(unittest.TestCase):
    def test_starts_and_ends_in_ready_and_brushes_the_hammer_at_each_shot(self):
        sched = mf.schedule(6)
        self.assertEqual(sched[0], (0.0, "ready"))
        self.assertEqual(sched[-1], (mf.LENGTH["attack"], "ready"))
        times = [t for t, _ in sched]
        self.assertEqual(times, sorted(times))
        self.assertEqual(len(set(times)), len(times))
        for t in mf.shot_times(6):
            self.assertIn((t - mf.BRUSH, "B-"), sched)
            self.assertIn((t + mf.BRUSH, "B+"), sched)
            self.assertIn((t - mf.SWEEP, "A"), sched)
            self.assertIn((t + mf.THROUGH, "C"), sched)

    def test_every_shot_but_the_last_returns_over_the_top(self):
        names = [p for _, p in mf.schedule(6)]
        self.assertEqual(names.count("R"), 5)
        self.assertEqual(names.count("A"), 6)
        for place in ("A", "R"):
            self.assertGreater(mf.PLACES[place][1], mf.PLACES["B"][1])
        self.assertGreater(mf.PLACES["R"][1], mf.PLACES["A"][1])
        self.assertGreater(mf.PLACES["A"][2], 0.0)     # ahead of the hammer
        self.assertLess(mf.PLACES["C"][2], 0.0)        # behind it

    def test_the_kick_is_zero_at_each_shot_and_peaks_after_it(self):
        keys = dict(mf.recoil_keys(6))
        for t in mf.shot_times(6):
            self.assertEqual(keys[t], 0.0)
            self.assertEqual(keys[t + mf.RECOIL_PEAK], mf.RECOIL_DEG)
            self.assertEqual(keys[t + mf.RECOIL_END], 0.0)


class Tags(unittest.TestCase):
    def test_three_lines_a_shot_at_the_shot_fractions(self):
        lines = mf.tag_lines(6)
        self.assertEqual(len(lines), 18)
        attack = [float(re.search(r">([0-9.]+)<", x).group(1)) for x in lines if 'type="Attack"' in x]
        self.assertEqual(attack, [round(t / 2.2, 3) for t in mf.shot_times(6)])
        self.assertEqual(attack, [0.191, 0.31, 0.428, 0.547, 0.666, 0.785])

    def test_the_flash_is_drawn_on_the_muzzle_bone_not_the_hand(self):
        # the stock musketshot draws on "R Hand": the flash showed at the hand (in game, 2026-11-26)
        lines = mf.tag_lines(6)
        particles = [x for x in lines if 'type="Particles"' in x]
        self.assertEqual(len(particles), 6)
        self.assertTrue(all(f'particlename="{mf.PARTICLE_SET}"' in x for x in particles))
        self.assertNotIn("musketshot", "\n".join(lines))
        block = mf.particleset_block()
        self.assertIn(f'<particleset name="{mf.PARTICLE_SET}">', block)
        self.assertEqual(block.count(f'bone="{mf.PARTICLE_BONE}"'), 4)
        self.assertIn("effects\\weapon_fire\\musket_fire_A.particle", block)
        self.assertNotIn("R Hand", block)
        self.assertEqual(mf.FLASH_BONE, "bip01 " + mf.PARTICLE_BONE.lower())
        # the check's times are the tags' as written (fractions rounded to 3 places)
        tagged = [float(re.search(r">([0-9.]+)<", x).group(1)) * 2.2 for x in particles]
        self.assertTrue(np.allclose(mf.flash_times(6), tagged))

    def test_the_anim_blocks_name_both_clips(self):
        xml = mf.anim_blocks(6)
        self.assertIn("RangedAttackSharpshoot", xml)
        self.assertIn("SharpshootIdle", xml)
        self.assertEqual(xml.count('type="Attack"'), 6)
        self.assertIn(mf.FOLDER + "\\" + mf.NAMES["attack"], xml)
        self.assertEqual(xml.count("<anim>"), xml.count("</anim>"))


class Hammer(unittest.TestCase):
    def test_the_top_of_the_frame_at_the_rear_of_the_barrel(self):
        # a barrel along +y from y 0 to 0.4, 0.04 thick (z 0.03 to 0.07), a grip below its rear (-z)
        barrel = np.array([[x, y, z] for x in (0.04, 0.10) for y in np.linspace(0.0, 0.4, 9) for z in (0.03, 0.07)])
        grip = np.array([[x, y, z] for x in (0.04, 0.10) for y in (-0.14, -0.06) for z in (-0.13, -0.05)])
        h = mf.hammer_point(np.concatenate([barrel, grip]))
        self.assertAlmostEqual(h[2], 0.07)
        self.assertAlmostEqual(h[0], 0.07)
        self.assertLess(h[1], 0.06)                     # at the rear end of the barrel, not at the muzzle


def pistol():
    """A barrel along +y (y 0 to 0.4, z 0.03 to 0.07) and a grip hanging from its rear end toward -z."""
    barrel = [[x, y, z] for x in (0.04, 0.10) for y in (0.0, 0.4) for z in (0.03, 0.07)]
    grip = [[x, -0.12, -0.12] for x in (0.04, 0.10)] + [[0.07, -0.05, -0.13]]
    return np.array(barrel + grip, np.float64)


class Grip(unittest.TestCase):
    def test_the_grip_hangs_from_the_rear_of_the_barrel(self):
        g = mf.grip_geometry(pistol())
        self.assertAlmostEqual(g["top"][1], 0.0)           # the barrel's rear end
        self.assertLess(g["butt"][2], -0.1)
        self.assertAlmostEqual(np.linalg.norm(g["axis"]), 1.0)
        self.assertLess(g["axis"] @ g["barrel"], 0.0)      # the butt behind the barrel's rear, as a revolver's

    def test_held_by_the_grip_the_centre_is_on_the_palm_and_the_axis_along_the_knuckles(self):
        g = mf.grip_geometry(pistol())
        palm, finger, normal = np.array([0.0, 0.08, 0.01]), np.array([0.0, 1.0, 0.0]), np.array([-1.0, 0.0, 0.0])
        h2p = mf.hold_frame(np.eye(4), palm, finger, normal, g)
        knuckles = np.cross(finger, normal)
        dist, ang = mf.hold_error(h2p, palm, knuckles, g)
        self.assertLess(dist, 1e-9)
        self.assertLess(ang, 1e-6)
        barrel = h2p[:3, :3] @ g["barrel"]
        self.assertGreater(barrel @ finger, 0.5)           # the barrel out over the fingers
        # held by the top of the frame (the grip's top on the palm) fails both measures
        top = np.eye(4)
        top[:3, 3] = palm - g["top"]
        dist, ang = mf.hold_error(top, palm, knuckles, g)
        self.assertGreater(dist, 0.05)
        self.assertGreater(ang, 30.0)


class Keys(unittest.TestCase):
    def test_missing_values_are_filled_between_their_neighbours(self):
        keys = [(0.0, {"a": 0.0, "b": np.array([0.0, 0.0])}), (1.0, {"a": None, "b": np.array([2.0, 2.0])}),
                (2.0, {"a": 4.0, "b": None})]
        out = mf._complete(keys, {"c": {0.0: 1.0, 2.0: 3.0}}, {"d": 7.0})
        self.assertAlmostEqual(out[1][1]["a"], 2.0)
        self.assertTrue(np.allclose(out[2][1]["b"], [2.0, 2.0]))
        self.assertAlmostEqual(out[1][1]["c"], 2.0)
        self.assertEqual(out[0][1]["d"], 7.0)


if __name__ == "__main__":
    unittest.main()
