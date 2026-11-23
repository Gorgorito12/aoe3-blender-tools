# SPDX-License-Identifier: GPL-3.0-or-later
"""Poses edited as world frames (aoe3game/gr2_pose.py: two-bone IK, keys) and the pieces of
tools/make_pray.py that need no game: synthetic skeletons, keys and triangles only.

    venv\\Scripts\\python -I tests\\test_make_pray.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import make_pray as mp  # noqa: E402
from aoe3game.gr2_anim import STOCK, Rig, animation_file, Animation  # noqa: E402
from aoe3game.gr2_pose import Keys, local_axis, two_bone_ik  # noqa: E402

IDQ = np.array([0.0, 0.0, 0.0, 1.0])


def leg():
    """root -> thigh -> calf -> foot -> toe: a leg hanging down, slightly bent forward (+z)."""
    return Rig(["Root", "Thigh", "Calf", "Foot", "Toe"], [-1, 0, 1, 2, 3],
               [(np.array([0.0, 1.0, 0.0]), IDQ), (np.array([0.1, 0.0, 0.0]), IDQ),
                (np.array([0.0, -0.5, 0.03]), IDQ), (np.array([0.0, -0.5, -0.03]), IDQ),
                (np.array([0.0, -0.1, 0.2]), IDQ)], STOCK)


class IK(unittest.TestCase):
    def setUp(self):
        self.rig = leg()
        self.pose = self.rig.by_name(self.rig.rest_worlds())
        self.hinge = local_axis(self.pose["thigh"][:3, :3], (1, 0, 0))

    def solve(self, target, pole=(0, 0, 1), end=None):
        return two_bone_ik(self.pose, self.rig, "thigh", "calf", "foot", target, pole, self.hinge, self.hinge,
                           end_frame=end)

    def test_reaches_the_target_and_keeps_the_lengths(self):
        target = np.array([0.15, 0.35, 0.3])
        p = self.solve(target)
        self.assertTrue(np.allclose(p["foot"][:3, 3], target, atol=1e-9))
        for a, b, n in (("thigh", "calf", 0.5), ("calf", "foot", 0.5)):
            self.assertAlmostEqual(np.linalg.norm(p[b][:3, 3] - p[a][:3, 3]),
                                   np.linalg.norm(self.pose[b][:3, 3] - self.pose[a][:3, 3]), places=9)
        self.assertTrue(np.allclose(p["thigh"][:3, 3], self.pose["thigh"][:3, 3]))

    def test_knee_goes_toward_the_pole(self):
        target = np.array([0.1, 0.4, 0.0])
        fwd, back = self.solve(target, (0, 0, 1)), self.solve(target, (0, 0, -1))
        self.assertGreater(fwd["calf"][2, 3], 0.2)
        self.assertLess(back["calf"][2, 3], -0.2)

    def test_a_limb_solved_where_it_is_does_not_change(self):
        p = self.solve(self.pose["foot"][:3, 3].copy(), pole=(0, 0, 1))
        for k in self.pose:
            self.assertTrue(np.allclose(p[k], self.pose[k], atol=1e-9), k)

    def test_end_frame_is_set_and_carries_the_branch(self):
        rot = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])
        p = self.solve(np.array([0.1, 0.3, 0.2]), end=rot)
        self.assertTrue(np.allclose(p["foot"][:3, :3], rot))
        rel_before = np.linalg.inv(self.pose["foot"]) @ self.pose["toe"]
        rel_after = np.linalg.inv(p["foot"]) @ p["toe"]
        self.assertTrue(np.allclose(rel_before, rel_after))

    def test_out_of_reach_is_clamped_to_the_limb(self):
        p = self.solve(np.array([0.1, -2.0, 0.0]))
        length = sum(np.linalg.norm(self.pose[b][:3, 3] - self.pose[a][:3, 3])
                     for a, b in (("thigh", "calf"), ("calf", "foot")))
        self.assertAlmostEqual(np.linalg.norm(p["foot"][:3, 3] - p["thigh"][:3, 3]), length, places=5)


class KeyInterpolation(unittest.TestCase):
    def test_equal_keys_hold_exactly(self):
        k = Keys([(0, {"a": 1.0, "v": [0, 0, 0]}), (1, {"a": 2.0, "v": [0, 0, 0]}), (2, {"a": 2.0, "v": [1, 0, 0]})])
        for t in np.linspace(1.0, 2.0, 11):
            self.assertEqual(k.at(t)["a"], 2.0)
        for t in np.linspace(0.0, 1.0, 11):
            self.assertTrue(np.array_equal(k.at(t)["v"], np.zeros(3)))

    def test_no_overshoot_and_keys_are_hit(self):
        k = Keys([(0, {"a": 0.0}), (1, {"a": 1.0}), (1.5, {"a": 1.1}), (3, {"a": 0.0})])
        vals = [k.at(t)["a"] for t in np.linspace(0, 3, 301)]
        self.assertLessEqual(max(vals), 1.1 + 1e-12)
        self.assertGreaterEqual(min(vals), -1e-12)
        for t, v in ((0, 0.0), (1, 1.0), (1.5, 1.1), (3, 0.0)):
            self.assertAlmostEqual(k.at(t)["a"], v)

    def test_eases_in_and_out(self):
        k = Keys([(0, {"a": 0.0}), (1, {"a": 1.0})])
        self.assertLess(k.at(0.05)["a"], 0.05 * 0.2)
        self.assertGreater(k.at(0.95)["a"], 1 - 0.05 * 0.2)

    def test_a_channel_missing_from_a_key_holds(self):
        k = Keys([(0, {"a": 0.0, "b": 5.0}), (1, {"a": 1.0}), (2, {"b": 7.0})])
        self.assertEqual(k.at(1.0)["b"], 5.0)
        self.assertEqual(k.at(1.5)["a"], 1.0)


class Clips(unittest.TestCase):
    def keys(self):
        base = {"ltoe": np.zeros(3), "rtoe": np.zeros(3), "lpalm": np.zeros(3), "rpalm": np.zeros(3), "x": 0.0}
        far = dict(base, rtoe=np.array([0.0, 0.0, -0.6]))
        return [(0.0, base), (1.0, far), (2.0, far)]

    def test_a_step_rises_before_it_travels_and_lands_before_it_stops(self):
        clip = mp.Clip("t", self.keys(), [(None, {"r": 0.1}), (None, {})], arc=0.0)
        for t in np.linspace(0, 1, 101):
            toe = clip.at(t)["rtoe"]
            if t <= mp.STEP_IN or t >= 1 - mp.STEP_IN:
                self.assertAlmostEqual(toe[2], 0.0 if t <= mp.STEP_IN else -0.6)
            if toe[1] < 0.02:
                self.assertTrue(abs(toe[2]) < 1e-9 or abs(toe[2] + 0.6) < 1e-9, t)
        self.assertAlmostEqual(clip.at(1.0)["rtoe"][1], 0.0)

    def test_waves_vanish_at_the_loop_ends(self):
        clip = mp.Clip("t", [(0.0, {"x": 0.0}), (10.0, {"x": 0.0})], length=10.0, arc=0.0,
                       waves=lambda t: {"x": mp.ease_wave(t, 5.0, 2.0) + mp.ease_wave(t, 10.0 / 3, 1.0)})
        self.assertAlmostEqual(clip.at(0.0)["x"], 0.0)
        self.assertAlmostEqual(clip.at(10.0)["x"], 0.0)
        eps = 1e-4
        self.assertLess(abs(clip.at(eps)["x"]) / eps, 1e-2)          # no speed at the seam
        self.assertLess(abs(clip.at(10.0 - eps)["x"]) / eps, 1e-2)

    def test_a_moving_hand_swings_out_in_front(self):
        k = self.keys()
        k[1][1]["rpalm"] = np.array([0.0, 0.3, 0.0])
        clip = mp.Clip("t", k, arc=0.12)
        self.assertGreater(clip.at(0.5)["rpalm"][2], 0.05)
        self.assertGreater(clip.at(0.5)["rpalm"][0], 0.0)              # the right hand to its side
        self.assertTrue(np.allclose(clip.at(1.0)["rpalm"], [0.0, 0.3, 0.0]))

    def test_reverse_moves_the_lifts_with_their_spans(self):
        keys = [(0.0, {"a": 0.0}), (1.0, {"a": 1.0}), (3.0, {"a": 2.0}), (4.0, {"a": 3.0})]
        lifts = [(None, {"r": 0.1}), (None, {}), (None, {"l": 0.2})]
        back, back_lifts = mp.reverse(keys, lifts, 4.0)
        self.assertEqual([t for t, _c in back], [0.0, 1.0, 3.0, 4.0])
        self.assertEqual([c["a"] for _t, c in back], [3.0, 2.0, 1.0, 0.0])
        self.assertEqual([sp for _n, sp in back_lifts], [{"l": 0.2}, {}, {"r": 0.1}])


class Pieces(unittest.TestCase):
    def test_ray_crossings_of_a_closed_box(self):
        v = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], np.float64)
        faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
                 (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
        tris = v[np.array(faces)]
        d = np.array([0.0, 0.0, 1.0])
        self.assertEqual(len(mp._hits(np.array([0.3, 0.4, -1.0]), d, tris)), 2)
        self.assertEqual(len(mp._hits(np.array([0.3, 0.4, 0.5]), d, tris)), 1)
        self.assertAlmostEqual(mp._first_hit(np.array([0.3, 0.4, 0.5]), d, tris), 0.5)

    def test_anim_blocks_name_every_part(self):
        text = mp.anim_blocks([1, 3], ["male", "female"])
        for name in ("villager_male_pray1_in", "villager_female_pray3_loop", "villager_male_pray3_out"):
            self.assertIn(mp.FOLDER + "\\" + name, text)
        self.assertEqual(text.count("<anim>"), 12)

    def test_clip_written_and_read_back(self):
        rig = leg()
        times = np.linspace(0, 1, 11)
        poses = []
        base = rig.by_name(rig.rest_worlds())
        hinge = local_axis(base["thigh"][:3, :3], (1, 0, 0))
        for t in times:
            target = np.array([0.1, 0.25 + 0.1 * t, 0.2])
            poses.append(two_bone_ik(base, rig, "thigh", "calf", "foot", target, (0, 0, 1), hinge, hinge))
        frames = [rig.localise(p) for p in poses]
        tracks = [(n, times, np.array([f[i][0] for f in frames]), np.array([f[i][1] for f in frames]))
                  for i, n in enumerate(rig.names)]
        data = animation_file("t", 1.0, "Root", tracks)
        a = Animation.load(data)
        for t, p in zip(times, poses):
            q = rig.by_name(rig.pose(a, float(t)))
            self.assertLess(mp.pose_gap(p, q), 1e-5)


if __name__ == "__main__":
    unittest.main()
