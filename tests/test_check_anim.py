# SPDX-License-Identifier: GPL-3.0-or-later
"""The animation checks (aoe3game/anim_check.py, tools/check_anim.py) on synthetic rigs and clips:
each failure that once reached a preview (a mounted gun that floats off its post as it turns, a
reload that puts the same magazine back, a head that whips round and tips back, a dismount removed
without a word) must FAIL, and its fixed version must PASS; so must the ordinary clips. No game
file is used.

    venv\\Scripts\\python -I tests\\test_check_anim.py
"""
import io
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import check_anim  # noqa: E402
from aoe3game import anim_check as ac  # noqa: E402
from aoe3game.gr2_anim import STOCK, animation_file, axis_quat  # noqa: E402

FPS = 30
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
IDQ = (0.0, 0.0, 0.0, 1.0)

# A biped with the game's bone names, standing on the ground (y = 0), facing +z, arms hanging
# (metres; the unit's left is -x). [name, parent, offset from the parent]
HUMAN_BONES = [
    ("Bip01", None, (0, 0, 0)), ("Bip01 Pelvis", "Bip01", (0, 1.0, 0)),
    ("Bip01 Spine", "Bip01 Pelvis", (0, 0.1, 0)), ("Bip01 Spine1", "Bip01 Spine", (0, 0.3, 0)),
    ("Bip01 Neck", "Bip01 Spine1", (0, 0.3, 0)), ("Bip01 Head", "Bip01 Neck", (0, 0.1, 0)),
    ("Bip01 L Thigh", "Bip01 Pelvis", (-0.1, -0.05, 0)), ("Bip01 L Calf", "Bip01 L Thigh", (0, -0.45, 0)),
    ("Bip01 L Foot", "Bip01 L Calf", (0, -0.42, 0)), ("Bip01 L Toe0", "Bip01 L Foot", (0, -0.06, 0.12)),
    ("Bip01 R Thigh", "Bip01 Pelvis", (0.1, -0.05, 0)), ("Bip01 R Calf", "Bip01 R Thigh", (0, -0.45, 0)),
    ("Bip01 R Foot", "Bip01 R Calf", (0, -0.42, 0)), ("Bip01 R Toe0", "Bip01 R Foot", (0, -0.06, 0.12)),
    ("Bip01 L UpperArm", "Bip01 Spine1", (-0.2, 0.25, 0)), ("Bip01 L Forearm", "Bip01 L UpperArm", (0, -0.3, 0)),
    ("Bip01 L Hand", "Bip01 L Forearm", (0, -0.25, 0)),
    ("Bip01 R UpperArm", "Bip01 Spine1", (0.2, 0.25, 0)), ("Bip01 R Forearm", "Bip01 R UpperArm", (0, -0.3, 0)),
    ("Bip01 R Hand", "Bip01 R Forearm", (0, -0.25, 0)),
]


def rig(bones, name="rig"):
    return ac.Model.of_dict({"basis": "metres", "bones": [
        {"name": n, "parent": p, "position": list(o)} for n, p, o in bones]}, name)


def human():
    return rig(HUMAN_BONES, "human")


def clip(duration, channels, fps=FPS):
    """A clip from functions of time: {bone: (position(t) or None, quaternion(t) or None)}."""
    times = np.linspace(0.0, duration, int(round(duration * fps)) + 1)
    keyed = {}
    for bone, (pf, qf) in channels.items():
        pos = None if pf is None else np.array([pf(t) for t in times])
        quats = None if qf is None else np.array([qf(t) for t in times])
        keyed[bone] = (times, pos, quats, None)
    return ac.Clip.of_keys(duration, keyed)


def turn(axis, degrees):
    return lambda t: axis_quat(axis, degrees(t) if callable(degrees) else degrees)


def ease(t, t0, t1):
    u = min(max((t - t0) / (t1 - t0), 0.0), 1.0)
    return u * u * (3 - 2 * u)


def results(report, check=None, item=None):
    return [r for r in report.results if (check is None or r.check == check)
            and (item is None or item in r.item)]


def status(report, check, item=None):
    rs = results(report, check, item)
    assert rs, (check, item, [r.line() for r in report.results])
    return ac.FAIL if any(r.status == ac.FAIL for r in rs) else rs[0].status


def human_job(clips, ground=0.0, **extra):
    spec = {"ground": ground, "actors": {"man": {"model": human(), "rig": "human"}}, "clips": clips}
    spec.update(extra)
    return ac.Job(spec)


# --------------------------------------------------------------------------------------------------
# 1. A mounted gun that floats off its post as it turns


def gun_scene(right):
    """A body with a post, and a gun hung on the post's top: its yaw bone on the post, the casing
    (and its trunnion) 0.3 m ahead. `right`: the gun turns about the post (its yaw bone), else about
    the casing's own centre (the first preview's mistake)."""
    body = rig([("root", None, (0, 0, 0)), ("chest", "root", (0, 1.5, 0)), ("post", "chest", (0, 0.4, 0))], "body")
    gun = rig([("groot", None, (0, 0, 0)), ("yaw", "groot", (0, 0, 0)), ("casing", "yaw", (0, 0.05, 0.3)),
               ("barrel", "casing", (0, 0, 0.4))], "gun")
    swing = turn(Y, lambda t: 90.0 * ease(t, 0.2, 1.8))
    body_clip = clip(2.0, {"chest": (None, turn(X, lambda t: 3.0 * math.sin(math.pi * t)))})
    gun_clip = clip(2.0, {"yaw": (None, swing)} if right else {"casing": (None, swing)})
    return ac.Job({
        "ground": 0.0,
        "actors": {"body": {"model": body}, "gun": {"model": gun, "attach": {"to": "body", "bone": "post"}}},
        "clips": {"aim": {"anims": {"body": body_clip, "gun": gun_clip}, "duration": 2.0, "loop": False}},
        "mounts": [{"name": "gun on its post", "part": "gun:casing", "mount": "body:post"}],
    })


class FloatingGun(unittest.TestCase):
    def test_turned_about_its_own_centre_it_leaves_the_post(self):
        rep = ac.check(gun_scene(right=False))
        self.assertEqual(status(rep, "mount"), ac.FAIL)
        r = results(rep, "mount")[0]
        self.assertGreater(r.value, 0.3)                 # 2 x 0.3 x sin 45: about 0.42 m at 90 degrees
        self.assertTrue(r.risks and r.risks[0][1] > 1.0)  # the worst frames are late in the turn
        self.assertFalse(rep.ok)

    def test_turned_about_the_post_it_stays(self):
        rep = ac.check(gun_scene(right=True))
        self.assertEqual(status(rep, "mount"), ac.PASS)
        self.assertLess(results(rep, "mount")[0].value, 1e-6)
        self.assertTrue(rep.ok, rep.text())

    def test_a_seat_given_in_the_part(self):
        job = gun_scene(right=False)
        job.spec["mounts"][0]["seat"] = [0, -0.05, -0.3]     # the post's top in the casing's frame
        self.assertEqual(status(ac.check(job), "mount"), ac.FAIL)


# --------------------------------------------------------------------------------------------------
# 2. A reload that puts the same magazine back


def reload_job(kind):
    """A gun on the ground with a magazine in its well and a spare in a crate. kind: "same" (the
    magazine lifted and seated again: the incomplete action), "toss" (the magazine thrown aside and
    sunk, the spare lifted out of the crate and seated), "pop" (the spare appears in the hand in the
    open), "swap" ("toss", and at the last frame the two bones trade places, as a clip that must
    end as the next one starts)."""
    gun = rig([("groot", None, (0, 0, 0)), ("well", "groot", (0, 1.0, 0)), ("mag", "groot", (0, 1.0, 0)),
               ("spare", "groot", (0.6, 0.2, -0.4)), ("crate", "groot", (0.6, 0.2, -0.4))], "gun")
    well, crate = np.array([0, 1.0, 0]), np.array([0.6, 0.2, -0.4])
    away = np.array([-1.2, 0.0, 0.3])

    def mag(t):
        if kind == "same":
            return well + (0, 0.3 * math.sin(math.pi * ease(t, 0.3, 2.0)), 0)
        lift = well + (0, 0.3, 0)
        if t < 0.8:
            return well + (lift - well) * ease(t, 0.2, 0.8)
        p = lift + (away - lift) * ease(t, 0.8, 1.4)
        return p - (0, 0.25 * ease(t, 1.6, 2.4), 0)       # lies on the ground, then sinks out of sight

    def spare(t):
        if kind == "same":
            return crate
        if kind == "pop":
            return crate if t < 1.0 else well + np.array([0, 0.3, 0]) * (1 - ease(t, 1.0, 2.0))
        lift = crate + (0, 0.5, 0)
        p = crate + (lift - crate) * ease(t, 0.6, 1.2)
        return p + (well - lift) * ease(t, 1.2, 2.0)

    def at_end(f, g):
        return (lambda t: g(t) if t >= 2.5 - 1e-6 else f(t)) if kind == "swap" else f

    duration = 2.5
    gun_clip = clip(duration, {"mag": (at_end(mag, lambda t: well), None),
                               "spare": (at_end(spare, lambda t: crate), None)})
    return ac.Job({
        "ground": 0.0,
        "actors": {"gun": {"model": gun}},
        "clips": {"reload": {"anims": {"gun": gun_clip}, "duration": duration, "loop": False,
                             "routes": {"magazine": {"start": "well", "end": "hidden"},
                                        "spare": {"start": "hidden", "end": "well"}}}},
        "capsules": [{"name": "crate", "a": {"bone": "gun:crate", "offset": [0, -0.1, 0]},
                      "b": {"bone": "gun:crate", "offset": [0, 0.1, 0]}, "radius": 0.2}],
        "props": {"magazine": {"bone": "gun:mag", "size": 0.08},
                  "spare": {"bone": "gun:spare", "size": 0.08, "hide_in": ["crate"], "twin": "magazine"}},
        "places": {"well": {"point": "gun:well", "radius": 0.03}},
    })


class Reload(unittest.TestCase):
    def test_the_same_magazine_put_back_fails_its_route(self):
        rep = ac.check(reload_job("same"))
        self.assertEqual(status(rep, "route", "magazine"), ac.FAIL)
        self.assertIn("the script says hidden", results(rep, "route", "magazine")[0].detail)
        self.assertEqual(status(rep, "route", "spare"), ac.FAIL)
        self.assertFalse(rep.ok)

    def test_tossed_and_replaced_passes(self):
        rep = ac.check(reload_job("toss"))
        self.assertEqual(status(rep, "route"), ac.PASS)
        self.assertEqual(status(rep, "prop"), ac.PASS)
        self.assertTrue(rep.ok, rep.text())

    def test_a_spare_that_pops_into_the_hand_fails(self):
        rep = ac.check(reload_job("pop"))
        self.assertEqual(status(rep, "prop", "spare"), ac.FAIL)
        self.assertIn("appeared", results(rep, "prop", "spare")[0].detail)

    def test_twins_trading_places_are_not_seen(self):
        rep = ac.check(reload_job("swap"))
        self.assertEqual(status(rep, "prop"), ac.PASS, rep.text())
        self.assertEqual(status(rep, "route"), ac.PASS, rep.text())
        self.assertIn("swap", results(rep, "route", "magazine")[0].detail)

    def test_without_the_twin_the_swap_is_a_jump(self):
        job = reload_job("swap")
        del job.spec["props"]["spare"]["twin"]
        self.assertEqual(status(ac.check(job), "prop"), ac.FAIL)


# --------------------------------------------------------------------------------------------------
# 3. A head that whips round and tips back


class Head(unittest.TestCase):
    def test_a_whip_past_90_and_back_fails(self):
        whip = clip(2.0, {"Bip01 Head": (None, lambda t: (
            ac.matrix_quat(ac.quat_matrix(axis_quat(Y, 100.0 * ease(t, 0.9, 1.0)))
                           @ ac.quat_matrix(axis_quat(X, -55.0 * ease(t, 0.9, 1.0))))))})
        rep = ac.check(human_job({"reload": {"anims": {"man": whip}}}))
        self.assertEqual(status(rep, "look", "head yaw"), ac.FAIL)
        self.assertEqual(status(rep, "look", "head pitch up"), ac.FAIL)
        self.assertEqual(status(rep, "speed"), ac.FAIL)
        self.assertGreater(results(rep, "look", "head yaw")[0].value, 90)
        self.assertEqual(status(rep, "look", "head pitch down"), ac.PASS)

    def test_a_calm_look_passes(self):
        calm = clip(2.0, {"Bip01 Head": (None, lambda t: (
            ac.matrix_quat(ac.quat_matrix(axis_quat(Y, 45.0 * ease(t, 0.3, 1.5)))
                           @ ac.quat_matrix(axis_quat(X, 20.0 * ease(t, 0.3, 1.5))))))})
        rep = ac.check(human_job({"reload": {"anims": {"man": calm}}}))
        for item in ("head yaw", "head pitch up", "head pitch down"):
            self.assertEqual(status(rep, "look", item), ac.PASS)
        self.assertEqual(status(rep, "speed"), ac.PASS)
        self.assertTrue(rep.ok, rep.text())

    def test_the_head_is_judged_from_the_chest(self):
        # the whole trunk turns 80 degrees and the head with it: no turn of the head
        trunk = clip(1.0, {"Bip01 Spine": (None, turn(Y, lambda t: 80.0 * ease(t, 0.0, 1.0)))})
        rep = ac.check(human_job({"turn": {"anims": {"man": trunk}}}))
        self.assertLess(results(rep, "look", "head yaw")[0].value, 1.0)

    def test_a_clip_may_raise_a_limit(self):
        whip = clip(2.0, {"Bip01 Head": (None, turn(Y, lambda t: 85.0 * ease(t, 0.0, 2.0)))})
        clips = {"look_back": {"anims": {"man": whip}, "limits": {"look_yaw": 90}}}
        self.assertEqual(status(ac.check(human_job(clips)), "look", "head yaw"), ac.PASS)


# --------------------------------------------------------------------------------------------------
# 4. A dismount removed without saying so


def dismount_jobs():
    """(baseline, the same clip with the rider left in the saddle)."""
    def get_off(t):
        u = ease(t, 0.3, 1.7)
        return (0.8 * (1 - u), 1.2 * (1 - u), 0.0)
    base = human_job({"deploy": {"anims": {"man": clip(2.0, {"Bip01": (get_off, None)})}},
                      "idle": {"anims": {"man": clip(1.0, {})}}}, ground=None)
    stay = human_job({"deploy": {"anims": {"man": clip(2.0, {"Bip01": (lambda t: (0.8, 1.2, 0.0), None)})}},
                      "idle": {"anims": {"man": clip(1.0, {})}}}, ground=None)
    return base, stay


class Inventory(unittest.TestCase):
    def test_a_motion_gone_fails(self):
        base, stay = dismount_jobs()
        rep = ac.check(stay, baseline=base)
        self.assertEqual(status(rep, "inventory", "man motion"), ac.FAIL)
        self.assertIn("name it under removed", results(rep, "inventory")[0].detail)
        self.assertFalse(rep.ok)

    def test_named_under_removed_it_passes(self):
        base, stay = dismount_jobs()
        stay.spec["removed"] = {"deploy:man": "he stays in the saddle (asked for on the review)"}
        rep = ac.check(stay, baseline=base)
        self.assertEqual(status(rep, "inventory"), ac.PASS)
        self.assertIn("removed: he stays", results(rep, "inventory")[0].detail)
        self.assertTrue(rep.ok, rep.text())

    def test_a_clip_gone_fails_unless_named(self):
        base, _ = dismount_jobs()
        gone = human_job({"idle": {"anims": {"man": clip(1.0, {})}}}, ground=None)
        self.assertEqual(status(ac.check(gone, baseline=base), "inventory", "clip present"), ac.FAIL)
        gone.spec["removed"] = {"deploy": "the unit no longer deploys"}
        self.assertEqual(status(ac.check(gone, baseline=base), "inventory", "clip present"), ac.PASS)

    def test_the_same_motion_kept_passes(self):
        base, _ = dismount_jobs()
        self.assertEqual(status(ac.check(base, baseline=base), "inventory"), ac.PASS)


# --------------------------------------------------------------------------------------------------
# Ordinary clips and the other checks


def breathe(t, period=2.0):
    return axis_quat(X, 2.0 * math.sin(2 * math.pi * t / period))


class Ordinary(unittest.TestCase):
    def test_an_idle_passes_every_check(self):
        idle = clip(2.0, {"Bip01 Spine1": (None, breathe),
                          "Bip01 L Forearm": (None, turn(X, -20.0)), "Bip01 R Forearm": (None, turn(X, -20.0))})
        rep = ac.check(human_job({"idle": {"anims": {"man": idle}, "duration": 2.0}}))
        self.assertTrue(rep.ok, rep.text())
        self.assertEqual(status(rep, "loop"), ac.PASS)
        self.assertEqual(status(rep, "duration"), ac.PASS)
        self.assertEqual(status(rep, "plant"), ac.PASS)
        self.assertEqual(status(rep, "hinge"), ac.PASS)

    def test_a_bow_and_a_crouch_pass(self):
        # the knees go forward and the shins back, the feet stay flat under the hips
        def a(t):
            return 35.0 * math.sin(math.pi * t / 2.0)

        def b(t):
            return a(t) + math.degrees(math.asin(0.45 / 0.42 * math.sin(math.radians(a(t)))))

        def drop(t):
            ra, rb = math.radians(a(t)), math.radians(b(t) - a(t))
            return (0.0, 1.0 - (0.87 - 0.45 * math.cos(ra) - 0.42 * math.cos(rb)), 0.0)
        legs = {}
        for side in ("L", "R"):
            legs[f"Bip01 {side} Thigh"] = (None, turn(X, lambda t: -a(t)))
            legs[f"Bip01 {side} Calf"] = (None, turn(X, lambda t: b(t)))
            legs[f"Bip01 {side} Foot"] = (None, turn(X, lambda t: a(t) - b(t)))
        crouch = clip(2.0, dict(legs, **{"Bip01 Pelvis": (drop, None),
                                         "Bip01 Spine": (None, turn(X, lambda t: 25.0 * math.sin(math.pi * t / 2)))}))
        bow = clip(2.0, {"Bip01 Spine": (None, turn(X, lambda t: 40.0 * math.sin(math.pi * t / 2))),
                         "Bip01 Head": (None, turn(X, lambda t: 20.0 * math.sin(math.pi * t / 2)))})
        rep = ac.check(human_job({"crouch": {"anims": {"man": crouch}, "loop": False},
                                  "bow": {"anims": {"man": bow}, "loop": False}}))
        self.assertTrue(rep.ok, rep.text())
        knee = [r for r in results(rep, "hinge", "left knee") if r.clip == "crouch"][0]
        self.assertEqual(knee.status, ac.PASS)

    def test_a_reversed_elbow_fails(self):
        bad = clip(1.0, {"Bip01 L Forearm": (None, turn(X, lambda t: 60.0 * ease(t, 0, 1)))})
        good = clip(1.0, {"Bip01 L Forearm": (None, turn(X, lambda t: -60.0 * ease(t, 0, 1)))})
        rep = ac.check(human_job({"bad": {"anims": {"man": bad}}, "good": {"anims": {"man": good}}}))
        self.assertEqual(status(rep, "hinge", "left elbow"), ac.FAIL)
        self.assertEqual([r.status for r in results(rep, "hinge", "left elbow") if r.clip == "good"], [ac.PASS])

    def test_a_reversed_knee_fails(self):
        bad = clip(1.0, {"Bip01 R Calf": (None, turn(X, lambda t: -40.0 * ease(t, 0, 1)))})
        rep = ac.check(human_job({"bad": {"anims": {"man": bad}}}, ground=None))
        self.assertEqual(status(rep, "hinge", "right knee"), ac.FAIL)

    def test_a_snap_fails_the_speed(self):
        snap = clip(1.0, {"Bip01 R UpperArm": (None, turn(Y, lambda t: 0.0 if t < 0.5 else 170.0))})
        rep = ac.check(human_job({"snap": {"anims": {"man": snap}}}))
        self.assertEqual(status(rep, "speed"), ac.FAIL)
        self.assertIn("R UpperArm", results(rep, "speed")[0].detail)

    def test_an_exempt_bone_may_spin(self):
        snap = clip(1.0, {"Bip01 R UpperArm": (None, turn(Y, lambda t: 0.0 if t < 0.5 else 170.0))})
        job = human_job({"spin": {"anims": {"man": snap}}}, speed_exempt=["man:bip01 r upperarm"])
        self.assertEqual(status(ac.check(job), "speed"), ac.PASS)

    def test_a_sliding_foot_and_a_sinking_foot_fail(self):
        slide = clip(1.0, {"Bip01": (lambda t: (0.0, 0.0, 0.0), None),
                           "Bip01 L Thigh": (None, turn(X, lambda t: -12.0 * ease(t, 0, 1)))})
        sink = clip(1.0, {"Bip01": (lambda t: (0.0, -0.12 * ease(t, 0, 1), 0.0), None)})
        rep = ac.check(human_job({"slide": {"anims": {"man": slide}}, "sink": {"anims": {"man": sink}}}))
        slid = [r for r in results(rep, "plant", "left foot") if r.clip == "slide"]
        self.assertTrue(any(r.status == ac.FAIL for r in slid), [r.line() for r in slid])
        sunk = [r for r in results(rep, "sink") if r.clip == "sink"]
        self.assertTrue(all(r.status == ac.FAIL for r in sunk), [r.line() for r in sunk])

    def test_a_walk_in_place_is_judged_with_its_ground_speed(self):
        # both feet move back together at 0.25 m/s on the ground: planted on a ground moving under
        # the unit at that speed, skating on a still one
        move = clip(0.6, {"Bip01": (lambda t: (0.0, 0.0, -0.25 * t), None)})
        bad = ac.check(human_job({"skate": {"anims": {"man": move}, "ground_speed": 0.0, "loop": False}}))
        good = ac.check(human_job({"walk": {"anims": {"man": move}, "ground_speed": 0.25, "loop": False}}))
        auto = ac.check(human_job({"walk": {"anims": {"man": move}, "loop": False}}))
        self.assertEqual(status(bad, "plant"), ac.FAIL)
        self.assertEqual(status(good, "plant"), ac.PASS)
        self.assertEqual(status(auto, "plant"), ac.PASS)

    def test_grips(self):
        gun = rig([("groot", None, (0, 0, 0)), ("grip", "groot", (-0.2, 1.1, 0.0))], "gun")
        held = clip(1.0, {"grip": (lambda t: (-0.2, 1.1 + 0.05 * math.sin(math.pi * t), 0.0), None)})
        on = clip(1.0, {"Bip01 L Hand": (lambda t: (0.0, -0.25 + 0.05 * math.sin(math.pi * t), 0.0), None)})
        spec = {"ground": 0.0,
                "actors": {"man": {"model": human(), "rig": "human"}, "gun": {"model": gun}},
                "clips": {"hold": {"anims": {"man": on, "gun": held}},
                          "drift": {"anims": {"man": clip(1.0, {}), "gun": held}}},
                "grips": [{"name": "left hand on the grip", "hand": "man:bip01 l hand", "grip": "gun:grip",
                           "frames": [[0.0, 1.0]]}]}
        rep = ac.check(ac.Job(spec))
        by = {r.clip: r.status for r in results(rep, "grip")}
        self.assertEqual(by, {"hold": ac.PASS, "drift": ac.FAIL})

    def test_a_prop_held_by_its_grip(self):
        # a pistol hung on the hand: its grip's centre on the palm passes; one held by another part
        # (the grip 10 cm away) fails the distance, and a grip turned across the fingers the axis
        def pistol(grip_at):
            return rig([("proot", None, (0, 0, 0)), ("grip", "proot", grip_at)], "pistol")

        def job(grip_at, grip_dir):
            return ac.Job({"ground": 0.0,
                           "actors": {"man": {"model": human(), "rig": "human"},
                                      "pistol": {"model": pistol(grip_at),
                                                 "attach": {"to": "man", "bone": "bip01 r hand"}}},
                           "clips": {"stand": {"anims": {"man": clip(1.0, {})}}},
                           "holds": [{"name": "pistol in the right hand", "hand": "man:bip01 r hand",
                                      "grip": "pistol:grip",
                                      "hand_axis": {"bone": "man:bip01 r hand", "dir": [0, 0, 1]},
                                      "grip_axis": {"bone": "pistol:grip", "dir": grip_dir}}]})
        good = ac.check(job((0.0, 0.0, 0.0), [0, 0, 1]))
        self.assertEqual([r.status for r in results(good, "hold")], [ac.PASS, ac.PASS])
        top = ac.check(job((0.0, 0.1, 0.0), [0, 0, 1]))
        self.assertEqual([r.status for r in results(top, "hold")], [ac.FAIL, ac.PASS])
        across = ac.check(job((0.0, 0.0, 0.0), [1, 0, 0]))
        self.assertEqual([r.status for r in results(across, "hold")], [ac.PASS, ac.FAIL])

    def test_hands_ahead_of_the_chest(self):
        # arms raised forward to a grip pass; an arm swung back behind the chest's plane fails, and
        # a frame range leaves out the beat where the hand goes back on purpose
        fwd = clip(1.0, {"Bip01 R UpperArm": (None, turn(X, -80.0))})
        back = clip(1.0, {"Bip01 R UpperArm": (None, turn(X, lambda t: 60.0 * ease(t, 0.4, 0.6)))})
        rule = {"name": "right hand in front", "point": "man:bip01 r hand", "of": "man:bip01 r upperarm", "min": 0.15}
        rep = ac.check(human_job({"fwd": {"anims": {"man": fwd}}, "back": {"anims": {"man": back}}}, ahead=[rule]))
        by = {r.clip: r.status for r in results(rep, "ahead")}
        self.assertEqual(by, {"fwd": ac.PASS, "back": ac.FAIL})
        early = dict(rule, clips=["back"], frames=[[0.0, 0.3]])
        rep = ac.check(human_job({"back": {"anims": {"man": back}}}, ahead=[early]))
        self.assertEqual(status(rep, "ahead"), ac.FAIL)          # the arm hangs: 0 cm ahead, under 15
        hang = dict(rule, min=-0.01, frames=[[0.0, 0.3]])
        rep = ac.check(human_job({"back": {"anims": {"man": back}}}, ahead=[hang]))
        self.assertEqual(status(rep, "ahead"), ac.PASS)

    def test_crossed_feet_fail(self):
        # the left leg swung across in front of the right (a turn's shuffle) fails; a step forward passes
        across = clip(1.0, {"Bip01 L Thigh": (None, turn(Z, lambda t: 35.0 * ease(t, 0, 1)))})
        step = clip(1.0, {"Bip01 L Thigh": (None, turn(X, lambda t: -25.0 * ease(t, 0, 1)))})
        rep = ac.check(human_job({"across": {"anims": {"man": across}, "loop": False},
                                  "step": {"anims": {"man": step}, "loop": False}}, ground=None))
        by = {r.clip: r.status for r in results(rep, "cross")}
        self.assertEqual(by, {"across": ac.FAIL, "step": ac.PASS})

    def test_a_prop_of_unreal_size_fails(self):
        stick = rig([("sroot", None, (0, 0, 0)), ("foot", "sroot", (0.3, 0.8, 0.2)), ("tip", "foot", (0, 0.85, 0))],
                    "stick")
        spec = {"ground": 0.0, "actors": {"man": {"model": human(), "rig": "human"}, "stick": {"model": stick}},
                "clips": {"idle": {"anims": {"man": clip(1.0, {}), "stick": clip(1.0, {})}}}}
        fits = dict(spec, sizes=[{"name": "stick", "a": "stick:foot", "b": "stick:tip", "of": "man",
                                  "min": 0.30, "max": 0.55}])
        huge = dict(spec, sizes=[{"name": "stick", "a": "stick:foot", "b": "stick:tip", "of": "man",
                                  "min": 0.05, "max": 0.20}])
        self.assertEqual(status(ac.check(ac.Job(fits)), "size"), ac.PASS)
        self.assertEqual(status(ac.check(ac.Job(huge)), "size"), ac.FAIL)

    def test_a_hand_inside_the_torso_fails(self):
        into = clip(1.0, {"Bip01 L UpperArm": (None, turn(Z, lambda t: 60.0 * ease(t, 0, 1)))})
        rep = ac.check(human_job({"into": {"anims": {"man": into}}}))
        self.assertEqual(status(rep, "penetration", "l hand"), ac.FAIL)

    def test_lengths_and_loops(self):
        broken = clip(1.0, {"Bip01 Spine1": (None, turn(X, lambda t: 25.0 * t))})
        rep = ac.check(human_job({"idle": {"anims": {"man": broken}, "duration": 1.5}}))
        self.assertEqual(status(rep, "duration"), ac.FAIL)
        self.assertEqual(status(rep, "loop"), ac.FAIL)
        gentle = clip(1.0, {"Bip01 Spine1": (None, lambda t: breathe(t, 1.0))})
        rep = ac.check(human_job({"idle": {"anims": {"man": gentle}, "duration": 1.0}}))
        self.assertEqual(status(rep, "loop"), ac.PASS)

    def test_actors_of_one_clip_must_be_as_long(self):
        gun = rig([("groot", None, (0, 0, 0))], "gun")
        spec = {"ground": 0.0, "actors": {"man": {"model": human(), "rig": "human"}, "gun": {"model": gun}},
                "clips": {"fire": {"anims": {"man": clip(1.0, {}), "gun": clip(1.2, {})}, "loop": False}}}
        self.assertEqual(status(ac.check(ac.Job(spec)), "duration"), ac.FAIL)


class Death(unittest.TestCase):
    def job(self, sword_falls):
        """A man who falls on his back and the sword he drops: to the ground, or left in the air."""
        sword = rig([("sroot", None, (0, 0, 0)), ("blade", "sroot", (0, 0, 0.6))], "sword")
        fall = clip(2.0, {"Bip01": (lambda t: (0.0, 0.03 * ease(t, 0.2, 1.5), 0.0),
                                    turn(X, lambda t: -90.0 * ease(t, 0.2, 1.5)))})
        drop = clip(2.0, {"sroot": ((lambda t: (0.5, 1.1 * (1 - ease(t, 0.3, 1.0)), 0.0)) if sword_falls
                                    else (lambda t: (0.5, 1.1, 0.0)), None)})
        return ac.Job({"ground": 0.0,
                       "actors": {"man": {"model": human(), "rig": "human"}, "sword": {"model": sword}},
                       "clips": {"death": {"anims": {"man": fall, "sword": drop}, "death": True}}})

    def test_a_part_left_in_the_air_fails(self):
        rep = ac.check(self.job(sword_falls=False))
        self.assertEqual(status(rep, "death", "man"), ac.PASS, rep.text())
        self.assertEqual(status(rep, "death", "sword"), ac.FAIL, rep.text())
        self.assertIn("floats", results(rep, "death", "sword")[0].detail)

    def test_every_part_on_the_ground_passes(self):
        rep = ac.check(self.job(sword_falls=True))
        self.assertEqual(status(rep, "death"), ac.PASS, rep.text())


class Lying(unittest.TestCase):
    """The kush (2026-11-26): a camel lying with its body propped on its folded legs, 0.3 m up, its
    knees up and its hind feet splayed out, was shown to the user; a lying animal must lie on its belly
    with its legs folded under it."""

    # the game's quadruped names, every bone on the root (offsets are positions), standing
    BONES = {"HS Bone Master": (0, 0, 0), "HS Bone Pelvis": (0, 1.5, -0.5), "HS Bone Stomach": (0, 1.5, 0.0),
             "HS Bone Chest": (0, 1.5, 0.5),
             "HS Bone Forearm Lt": (-0.2, 0.6, 0.5), "HS Bone Forearm Rt": (0.2, 0.6, 0.5),
             "HS Bone Shin Lt": (-0.2, 0.6, -0.5), "HS Bone Shin Rt": (0.2, 0.6, -0.5),
             "HS Bone Hoof Frnt Lt": (-0.2, 0.1, 0.5), "HS Bone Hoof Frnt Rt": (0.2, 0.1, 0.5),
             "HS Bone Hoof Back Lt": (-0.2, 0.1, -0.5), "HS Bone Hoof Back Rt": (0.2, 0.1, -0.5)}

    def model(self):
        names = list(self.BONES)
        m = ac.Model.of_dict({"basis": "metres", "bones": [
            {"name": n, "parent": None if i == 0 else names[0], "position": list(self.BONES[n])}
            for i, n in enumerate(names)]}, "camel")
        bones = [{"name": n, "bind": ac.frame(np.array(self.BONES[n], float), np.array(IDQ)),
                  "world": ac.frame(np.array(self.BONES[n], float), np.array(IDQ))} for n in names]
        # the torso a box from 1.0 to 2.0 m (the pelvis's half behind, the chest's ahead), a foot point
        # on the ground under each hoof bone
        pos, idx = [], []
        for x in (-0.35, 0.35):
            for y in (1.0, 2.0):
                for z in (-0.8, -0.1, 0.1, 0.8):
                    pos.append((x, y, z))
                    idx.append(names.index("HS Bone Pelvis" if z < 0 else "HS Bone Chest"))
        for n in names:
            if "Hoof" in n:
                x, _y, z = self.BONES[n]
                pos.append((x, 0.0, z))
                idx.append(names.index(n))
        k = len(pos)
        mesh = {"file_positions": np.array(pos, float), "vertex_bones4": np.c_[np.array(idx), -np.ones((k, 3), int)],
                "vertex_weights4": np.c_[np.ones(k), np.zeros((k, 3))], "skin_names": names}
        return ac.Model(m.names, m.parents, m.rest, m.basis, [mesh], {"bones": bones}, "camel")

    def pose(self, down, knee, hoof_out):
        """Channels: the torso `down`, the knees at `knee` m, the hooves `hoof_out` m out to the sides."""
        ch = {}
        for n, (x, y, z) in self.BONES.items():
            if n in ("HS Bone Pelvis", "HS Bone Stomach", "HS Bone Chest"):
                ch[n] = (x, y - down, z)
            elif "Forearm" in n or "Shin" in n:
                ch[n] = (x, knee, z + (0.3 if "Forearm" in n else -0.3))
            elif "Hoof" in n:
                ch[n] = (x + (hoof_out if x > 0 else -hoof_out), 0.05, z)
        return ch

    def clip_of(self, a, b=None, length=1.0):
        b = b or a
        return clip(length, {n: (lambda t, n=n: tuple(np.array(a[n]) + (np.array(b[n]) - np.array(a[n]))
                                                       * ease(t, 0.1, 0.9)), None) for n in a})

    def checked(self, clips):
        return ac.check(ac.Job({"ground": 0.0, "actors": {"camel": {"model": self.model(), "rig": "bare"}},
                                "clips": clips}))

    def test_a_propped_camel_fails_and_the_kush_passes(self):
        kush = self.pose(0.97, 0.05, 0.0)
        propped = self.pose(0.70, 0.40, 0.45)
        rep = self.checked({"kush": {"anims": {"camel": self.clip_of(kush)}},
                        "propped": {"anims": {"camel": self.clip_of(propped)}}})
        by = {}
        for r in results(rep, "lying"):
            by.setdefault(r.clip, set()).add((r.item.split(":")[1].split("(")[0].strip(), r.status))
        self.assertTrue(all(s == ac.PASS for _i, s in by["kush"]), rep.text())
        failed = {i for i, s in by["propped"] if s == ac.FAIL}
        self.assertEqual(failed, {"belly on the ground", "knees on the ground", "legs inside its sides"}, rep.text())

    def test_judged_where_it_lies(self):
        stand = self.pose(0.0, 0.6, 0.0)
        for n in ("HS Bone Forearm Lt", "HS Bone Forearm Rt", "HS Bone Shin Lt", "HS Bone Shin Rt"):
            stand[n] = self.BONES[n]
        kush = self.pose(0.97, 0.05, 0.0)
        rep = self.checked({"down": {"anims": {"camel": self.clip_of(stand, kush, 2.0)}, "loop": False},
                        "idle": {"anims": {"camel": self.clip_of(stand)}},
                        "off": {"anims": {"camel": self.clip_of(self.pose(0.7, 0.4, 0.45))}, "lying": False}})
        items = {r.clip: r.item for r in results(rep, "lying")}
        self.assertIn("the last frame", items["down"])
        self.assertNotIn("idle", items)
        self.assertNotIn("off", items)
        self.assertEqual(status(rep, "lying"), ac.PASS, rep.text())


class Jobs(unittest.TestCase):
    def test_bad_names_are_refused(self):
        with self.assertRaises(ac.JobError):
            human_job({"idle": {"anims": {"nobody": clip(1.0, {})}}})
        job = human_job({"idle": {"anims": {"man": clip(1.0, {})}}},
                        grips=[{"hand": "man:no such bone", "grip": "man:bip01 head"}])
        with self.assertRaises(ac.JobError):
            ac.check(job)

    def test_a_rig_without_some_bones_is_noted(self):
        legless = [b for b in HUMAN_BONES if "Calf" not in b[0] and "Foot" not in b[0] and "Toe" not in b[0]]
        rep = ac.check(ac.Job({"ground": None, "actors": {"man": {"model": rig(legless), "rig": "human"}},
                               "clips": {"idle": {"anims": {"man": clip(1.0, {})}}}}))
        self.assertTrue(any("lacks" in n for n in rep.notes), rep.notes)
        self.assertTrue(rep.ok)


class CommandLine(unittest.TestCase):
    def run_tool(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check_anim.main(argv)
        return code, out.getvalue(), err.getvalue()

    def write_files(self, tmp, head_yaw):
        rig_path = os.path.join(tmp, "man.json")
        with open(rig_path, "w", encoding="utf-8") as f:
            json.dump({"basis": "metres", "bones": [{"name": n, "parent": p, "position": list(o)}
                                                    for n, p, o in HUMAN_BONES]}, f)
        times = np.linspace(0.0, 1.0, 31)
        quats = [axis_quat(Y, head_yaw * ease(t, 0.2, 0.8)) for t in times]
        tracks = [("Bip01 Head", times, np.tile([0.0, 0.1 * STOCK.upm, 0.0], (len(times), 1)), quats)]
        anim = os.path.join(tmp, "look.gr2")
        with open(anim, "wb") as f:
            f.write(animation_file("look", 1.0, "man", tracks))
        return rig_path, anim

    def test_exit_codes_report_and_risk_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig_path, anim = self.write_files(tmp, 40.0)
            code, out, _ = self.run_tool(["--model", rig_path, "--anim", anim, "--duration", "1", "--no-loop"])
            self.assertEqual(code, 0, out)
            self.assertIn("the preview may be made", out)
            rig_path, anim = self.write_files(tmp, 110.0)
            js, png = os.path.join(tmp, "r.json"), os.path.join(tmp, "risk.png")
            code, out, _ = self.run_tool(["--model", rig_path, "--anim", anim, "--duration", "1", "--no-loop",
                                          "--json", js, "--risk-sheet", png])
            self.assertEqual(code, 1, out)
            self.assertIn("FAIL  look", out)
            self.assertIn("the preview is refused", out)
            with open(js, encoding="utf-8") as f:
                data = json.load(f)
            self.assertFalse(data["ok"])
            self.assertTrue(any(r["check"] == "look" and r["status"] == "FAIL" for r in data["risk_frames"]))
            with open(png, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_a_job_file_and_the_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig_path, anim = self.write_files(tmp, 30.0)
            job = {"ground": 0.0, "actors": {"man": {"model": "man.json", "rig": "human"}},
                   "clips": {"look": {"anims": {"man": "look.gr2"}, "duration": 1.0, "loop": False}}}
            path = os.path.join(tmp, "job.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f)
            prev = os.path.join(tmp, "preview")
            code, out, _ = self.run_tool([path, "--preview", prev])
            self.assertEqual(code, 0, out)
            self.assertTrue(os.path.isfile(os.path.join(prev, "look-sheet.png")))

    def test_a_job_that_cannot_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"actors": {"man": {"model": "missing.gr2"}}, "clips": {}}, f)
            code, _, err = self.run_tool([path])
            self.assertEqual(code, 2)
            self.assertIn("check_anim:", err)


if __name__ == "__main__":
    unittest.main()
