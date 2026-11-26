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
