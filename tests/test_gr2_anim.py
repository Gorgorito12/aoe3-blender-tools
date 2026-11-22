# SPDX-License-Identifier: GPL-3.0-or-later
"""Animations read, posed, retargeted and written (aoe3game/gr2_anim.py) and the pieces of
tools/make_dismount.py that need no game: synthetic skeletons and curves only, no game files.

    venv\\Scripts\\python -I tests\\test_gr2_anim.py
"""
import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import make_dismount as md  # noqa: E402
from aoe3game import gr2  # noqa: E402
from aoe3game.gr2_anim import (STOCK, Animation, Basis, Curve, Rig, animation_file, axis_quat,  # noqa: E402
                               frame, matrix_quat, slerp, split)
from aoe3game.gr2_skin import quat_matrix  # noqa: E402

IDQ = np.array([0.0, 0.0, 0.0, 1.0])


def rig_a():
    """root -> pelvis -> thigh, and a hand hanging from the root."""
    return Rig(["Root", "Pelvis", "Thigh", "Hand"], [-1, 0, 1, 0],
               [(np.zeros(3), IDQ), (np.array([0, 1.0, 0]), IDQ), (np.array([0.1, -0.1, 0]), IDQ),
                (np.array([0.4, 1.2, 0]), IDQ)], STOCK)


def rig_b():
    """The same bones, another hierarchy: the thigh hangs from the root, the hand from the pelvis."""
    return Rig(["Root", "Pelvis", "Thigh", "Hand"], [-1, 0, 0, 1],
               [(np.zeros(3), IDQ), (np.array([0, 1.0, 0]), IDQ), (np.array([0.1, 0.9, 0]), IDQ),
                (np.array([0.4, 0.2, 0]), IDQ)], STOCK)


class Curves(unittest.TestCase):
    def test_degree1_is_linear_between_knots(self):
        c = Curve(1, [0.0, 1.0, 2.0], [0.0, 10.0, 30.0])
        self.assertAlmostEqual(c.sample(0.5)[0], 5.0)
        self.assertAlmostEqual(c.sample(1.5)[0], 20.0)
        self.assertAlmostEqual(c.sample(2.0)[0], 30.0)

    def test_degree2_matches_the_uniform_quadratic_b_spline(self):
        # the runtime's 2x1 weights on uniform knots: (1-s)^2/2, 1/2 + s - s^2, s^2/2 over P[i-2..i]
        knots = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        ctrl = [0.0, 4.0, 1.0, 7.0, 2.0, 5.0]
        c = Curve(2, knots, ctrl)
        for t in (2.25, 2.5, 3.75):
            i = int(math.floor(t)) + 1                  # the span k[i-1] <= t < k[i]
            s = t - knots[i - 1]
            want = (1 - s) ** 2 / 2 * ctrl[i - 2] + (0.5 + s - s * s) * ctrl[i - 1] + s * s / 2 * ctrl[i]
            self.assertAlmostEqual(c.sample(t)[0], want, places=6)

    def test_single_knot_is_constant(self):
        c = Curve(0, [0.0], [1.0, 2.0, 3.0])
        self.assertEqual(list(c.sample(7.0)), [1.0, 2.0, 3.0])


class Frames(unittest.TestCase):
    def test_quaternion_round_trip(self):
        q = axis_quat((1, 2, 3), 70)
        q2 = matrix_quat(quat_matrix(q))
        self.assertAlmostEqual(abs(float(q @ q2)), 1.0, places=9)

    def test_slerp_ends_and_middle(self):
        a, b = IDQ, axis_quat((0, 1, 0), 90)
        np.testing.assert_allclose(slerp(a, b, 0), a, atol=1e-9)
        np.testing.assert_allclose(slerp(a, b, 1), b, atol=1e-9)
        np.testing.assert_allclose(slerp(a, b, 0.5), axis_quat((0, 1, 0), 45), atol=1e-9)

    def test_basis_conversion_max_inches_to_stock(self):
        # a raw 3ds Max file: right +x, up +z, back -y, inches
        mx = Basis((1, 0, 0), (0, 0, 1), (0, -1, 0), 39.370079)
        c, s = mx.to(STOCK)
        up_in_max = np.array([0, 0, 39.370079])        # one metre up
        np.testing.assert_allclose(s * (c @ up_in_max), [0, STOCK.upm, 0], atol=1e-6)
        right_in_max = np.array([39.370079, 0, 0])
        np.testing.assert_allclose(s * (c @ right_in_max), [-STOCK.upm, 0, 0], atol=1e-6)


class Retarget(unittest.TestCase):
    def test_localise_puts_each_bone_on_the_world_frame_of_its_namesake(self):
        a, b = rig_a(), rig_b()
        locs = list(a.rest)
        locs[1] = (np.array([0, 1.0, 0]), axis_quat((0, 0, 1), 30))
        locs[2] = (np.array([0.1, -0.1, 0]), axis_quat((1, 0, 0), 50))
        world = a.by_name(a.worlds(locs))
        back = b.by_name(b.worlds(b.localise(world)))
        for name in world:
            np.testing.assert_allclose(back[name], world[name], atol=1e-9)


class Files(unittest.TestCase):
    def test_animation_written_and_read_back(self):
        rig = rig_a()
        times = np.linspace(0.0, 1.0, 11)
        pos = np.array([[0, 1.0 + 0.1 * t, 0] for t in times])
        quats = np.array([axis_quat((0, 1, 0), 90 * t) for t in times])
        still = np.tile(np.array([0.1, -0.1, 0]), (len(times), 1))
        data = animation_file("test", 1.0, "Root",
                              [("Pelvis", times, pos, quats), ("Thigh", times, still, np.tile(IDQ, (11, 1)))])
        anim = Animation.load(data)
        self.assertAlmostEqual(anim.duration, 1.0, places=6)
        self.assertEqual(anim.group_name, "Root")
        self.assertEqual(anim.tracks["thigh"].position.degree, 0)       # never moves: one knot
        p, q = anim.tracks["pelvis"].local(0.55, (None, None))
        self.assertAlmostEqual(p[1], 1.055, places=5)
        self.assertAlmostEqual(abs(float(q @ axis_quat((0, 1, 0), 49.5))), 1.0, places=5)
        w = rig.by_name(rig.pose(anim, 0.5))
        self.assertAlmostEqual(w["pelvis"][1, 3], 1.05, places=5)
        self.assertTrue(gr2.crc_ok(data))

    def test_tracks_are_sorted_byte_by_byte(self):
        # the stock horse files put "HS Bone Tail_03" before "bone attachpoint"; the runtime binary-searches them
        times = np.array([0.0, 1.0])
        still = np.zeros((2, 3))
        names = ["bone attachpoint", "HS Bone Tail_03", "HS Bone Master", "Bip01 R Hand"]
        data = animation_file("t", 1.0, "HS Bone Master",
                              [(n, times, still, np.tile(IDQ, (2, 1))) for n in names])
        root = gr2.load(data).root()
        got = [t.get("Name") for t in root.get("TrackGroups")[0].get("TransformTracks")]
        self.assertEqual(got, ["Bip01 R Hand", "HS Bone Master", "HS Bone Tail_03", "bone attachpoint"])


class Tool(unittest.TestCase):
    def test_loop_length_fits_whole_cycles(self):
        dur, cycles = md.loop_length(0.6, 1.2)
        self.assertAlmostEqual(dur, 1.2)
        self.assertEqual(cycles, 1)
        dur, cycles = md.loop_length(4.333, 1.0)
        self.assertEqual(cycles, round(dur / 1.0))

    def test_rotate_about_moves_only_the_branch(self):
        rig = rig_a()
        pose = rig.by_name(rig.rest_worlds())
        out = md.rotate_about(pose, rig, "pelvis", "pelvis", (0, 0, 1), 90)
        np.testing.assert_allclose(out["hand"], pose["hand"])          # not below the pelvis
        np.testing.assert_allclose(out["pelvis"][:3, 3], pose["pelvis"][:3, 3], atol=1e-9)
        self.assertAlmostEqual(out["thigh"][0, 3], 0.1, places=9)      # turned about z through the pelvis

    def test_split_and_frame(self):
        m = frame(np.array([1.0, 2, 3]), axis_quat((0, 1, 0), 30))
        p, q = split(m)
        np.testing.assert_allclose(frame(p, q), m, atol=1e-9)

    def test_anim_blocks_name_both_files(self):
        recipe = dict(md.DEFAULT_RECIPE)
        built = {"idle": (b"", 1.0, [], [], "animation_library\\cavalry\\horse_idle_A", None),
                 "attack": (b"", 1.0, [], [], "animation_library\\cavalry\\horse_idle_A", b"x")}
        horse, rider = md.anim_blocks(recipe, built)
        self.assertIn("<anim>Dismounted_Idle", horse)
        self.assertIn("horse_idle_A</file>", horse)
        self.assertIn("chasseur_horse_attack</file>", horse)
        self.assertIn('<tag type="Attack">0.46</tag>', horse)
        self.assertIn("chasseur_attack</file>", rider)

    def test_hidden_horse_clips_on_foot_only(self):
        recipe = dict(md.DEFAULT_RECIPE, horse="hide")
        idle = "animation_library\\cavalry\\horse_idle_A"
        built = {"idle": (b"", 1.0, [], [], idle, b"x"), "dismount": (b"", 2.5, [], [], idle, b"x"),
                 "mount": (b"", 2.5, [], [], idle, b"x"), "raze_attack": (b"", 1.3, [], [], idle, b"x")}
        horse, rider = md.anim_blocks(recipe, built)
        blocks = {b.split("\n")[0]: b for b in horse.split("\t<anim>")[1:]}
        self.assertIn("chasseur_horse_hidden_idle</file>", blocks["Dismounted_Idle"])
        self.assertIn("chasseur_horse_hidden_raze_attack</file>", blocks["Dismounted_Raze_attack"])
        self.assertIn("chasseur_horse_dismount</file>", blocks["Dismount"])
        self.assertIn("chasseur_horse_mount</file>", blocks["Mount"])
        self.assertNotIn("<component>", horse.replace("<component>ModelComp</component>", ""))
        self.assertIn('<attach a="torch" frombone="ATTACHPOINT" tobone="L HAND" syncanims="0"/>', rider)
        kept_horse, kept_rider = md.anim_blocks(dict(md.DEFAULT_RECIPE), built)
        self.assertNotIn("horse_hidden_", kept_horse)
        self.assertEqual(kept_rider, rider)                          # the rider's blocks do not change

    def test_test_entries_play_heal_and_every_build_name(self):
        idle = "animation_library\\cavalry\\horse_idle_A"
        built = {"heal": (b"", 3.0, [], [], idle, b"x"), "build": (b"", 1.8, [], [], idle, b"x")}
        horse, rider = md.anim_blocks(dict(md.DEFAULT_RECIPE), built)
        names = [b.split("\n")[0] for b in horse.split("\t<anim>")[1:]]
        self.assertEqual(names, ["Heal", "Build", "BuildLifting", "BuildSaw", "BuildStaking"])
        self.assertEqual(rider.count("chasseur_build</file>"), 4)

    def test_bury_moves_only_the_skinned_bones(self):
        maker = md.Maker.__new__(md.Maker)
        maker.horse, maker.r, maker.skinned = rig_a(), {"hidden_depth": 30.0}, {"pelvis", "thigh"}
        pose = maker.horse.by_name(maker.horse.rest_worlds())
        out = maker.bury(pose)
        drop = 30.0 * STOCK.upm * np.asarray(STOCK.up, np.float64)
        for k in ("pelvis", "thigh"):
            np.testing.assert_allclose(out[k][:3, 3], pose[k][:3, 3] - drop, atol=1e-9)
        for k in ("root", "hand"):
            np.testing.assert_allclose(out[k], pose[k])
        self.assertTrue(maker.hidden({"name": "idle"}) is False)          # the recipe keeps the horse
        maker.r = {"horse": "hide"}
        self.assertTrue(maker.hidden({"name": "idle"}))
        self.assertFalse(maker.hidden({"name": "dismount"}))

    def test_test_entries_only_on_request(self):
        names = [e["name"] for e in md.foot_entries(md.DEFAULT_RECIPE)]
        self.assertIn("raze_attack", names)
        self.assertNotIn("heal", names)
        names = [e["name"] for e in md.foot_entries(md.DEFAULT_RECIPE, True)]
        self.assertIn("heal", names)
        self.assertIn("build", names)



if __name__ == "__main__":
    unittest.main()
