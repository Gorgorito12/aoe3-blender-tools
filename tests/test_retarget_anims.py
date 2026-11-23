# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of aoe3game/gr2_retarget.py and tools/retarget_anims.py on synthetic rigs, animations, tag
files and anim files (nothing of the game). Needs numpy (the venv):

    venv\\Scripts\\python -I tests/test_retarget_anims.py
"""
import math
import os
import struct
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, precomp  # noqa: E402
from aoe3game.gr2_anim import STOCK, Animation, Rig, animation_file, axis_quat  # noqa: E402
from aoe3game.gr2_retarget import Retarget, retarget_precomp, tag_bone  # noqa: E402
import retarget_anims as ra  # noqa: E402

I = np.array([0.0, 0.0, 0.0, 1.0])


def rig(bones):
    """A Rig from [(name, parent name or None, position, quaternion)] in the game's basis."""
    names = [b[0] for b in bones]
    parents = [names.index(b[1]) if b[1] else -1 for b in bones]
    rest = [(np.array(b[2], np.float64), np.array(b[3], np.float64)) for b in bones]
    return Rig(names, parents, rest, STOCK)


def source_rig():
    # the Macehualtin's layout: a master bone above the biped, the bar and the launch point on it
    return rig([("bone_master", None, (0, 0, 0), I),
                ("Bip01", "bone_master", (0, 1.0, 0), I),
                ("Bip01 Spine", "Bip01", (0, 0.1, 0), I),
                ("Bip01 R Hand", "Bip01 Spine", (0.4, 0.4, 0), I),
                ("Bip01 Prop1", "Bip01 R Hand", (0, 0, 0), axis_quat((1, 0, 0), 20)),
                ("bone hitpointbar", "bone_master", (0, 3.0, 0), I),
                ("bone_launchpoint", "bone_master", (0.2, 1.7, 1.1), I)])


def target_rig(spine_turn=0.0):
    # a standard infantry layout: the biped is the root (taller), longer arm, an end bone, the bar
    # on the biped's root
    return rig([("Bip01", None, (0, 1.2, 0), I),
                ("Bip01 Spine", "Bip01", (0, 0.1, 0), axis_quat((0, 0, 1), spine_turn)),
                ("Bip01 R Hand", "Bip01 Spine", (0.5, 0.45, 0), axis_quat((0, 0, 1), -spine_turn)),
                ("Bip01 Prop1", "Bip01 R Hand", (0.01, 0, 0), I),
                ("Bip01 Prop1_end", "Bip01 Prop1", (0, 0, 0.1), I),
                ("bone hitpointbar", "Bip01", (0, 1.8, 0), I)])


def clip(src, local_at, duration=1.0, n=11, group="bone_master"):
    """A source animation: local_at(t) -> {bone: (position, quaternion)} over the rest."""
    times = np.linspace(0.0, duration, n)
    tracks = []
    for i, name in enumerate(src.names):
        pos, quat = [], []
        for t in times:
            p, q = local_at(t).get(name, src.rest[i])
            pos.append(p)
            quat.append(q)
        tracks.append((name, times, np.array(pos), np.array(quat)))
    return Animation.load(animation_file("test", duration, group, tracks))


class RetargetTest(unittest.TestCase):
    def test_rest_gives_the_target_rest(self):
        src, tgt = source_rig(), target_rig()
        rt = Retarget(src, tgt)
        anim = clip(src, lambda t: {})
        got = rt.worlds(rt.source_pose(anim, 0.5))
        for name, w, r in zip(tgt.names, got, tgt.rest_worlds()):
            if name.lower() in ("bone hitpointbar", "bip01 prop1", "bip01 prop1_end"):
                continue                                    # copied from the source, see below
            self.assertTrue(np.allclose(w, r, atol=1e-5), name)

    def test_the_rotation_change_is_the_sources(self):
        src, tgt = source_rig(), target_rig(spine_turn=35.0)    # the target's spine points elsewhere
        rt = Retarget(src, tgt)
        turn = axis_quat((1, 0, 0), 40)
        anim = clip(src, lambda t: {"Bip01 Spine": ((0, 0.1, 0), turn)})
        sp = rt.source_pose(anim, 0.5)
        got = tgt.by_name(rt.worlds(sp))
        s_rest = src.by_name(src.rest_worlds())
        t_rest = tgt.by_name(tgt.rest_worlds())
        for bone in ("bip01 spine", "bip01 r hand"):
            delta_s = sp[bone][:3, :3] @ s_rest[bone][:3, :3].T
            delta_t = got[bone][:3, :3] @ t_rest[bone][:3, :3].T
            self.assertTrue(np.allclose(delta_s, delta_t, atol=1e-5), bone)
        # the target keeps its own bone lengths
        d = np.linalg.norm(got["bip01 r hand"][:3, 3] - got["bip01 spine"][:3, 3])
        self.assertAlmostEqual(d, float(np.linalg.norm([0.5, 0.45, 0])), places=5)

    def test_the_root_moves_by_the_height_ratio(self):
        src, tgt = source_rig(), target_rig()
        rt = Retarget(src, tgt)
        self.assertAlmostEqual(rt.root_scale, 1.2, places=6)
        anim = clip(src, lambda t: {"Bip01": ((0.0, 1.0 - 0.2 * t, 0.5 * t), I)})
        got = tgt.by_name(rt.worlds(rt.source_pose(anim, 1.0)))
        self.assertTrue(np.allclose(got["bip01"][:3, 3], [0.0, 1.2 - 0.24, 0.6], atol=1e-5))

    def test_a_held_bone_keeps_the_sources_frame_in_the_hand(self):
        src, tgt = source_rig(), target_rig(spine_turn=20.0)
        rt = Retarget(src, tgt)
        anim = clip(src, lambda t: {"Bip01 Prop1": ((0.02, 0.01, 0), axis_quat((0, 1, 0), 70 * t))})
        sp = rt.source_pose(anim, 0.7)
        got = tgt.by_name(rt.worlds(sp))
        want = np.linalg.inv(sp["bip01 r hand"]) @ sp["bip01 prop1"]
        have = np.linalg.inv(got["bip01 r hand"]) @ got["bip01 prop1"]
        self.assertTrue(np.allclose(want, have, atol=1e-5))

    def test_a_marker_keeps_the_sources_world_frame(self):
        src, tgt = source_rig(), target_rig()
        rt = Retarget(src, tgt)
        anim = clip(src, lambda t: {"Bip01": ((0.3, 0.8, 0.9), axis_quat((0, 1, 0), 50))})
        got = tgt.by_name(rt.worlds(rt.source_pose(anim, 0.5)))
        self.assertTrue(np.allclose(got["bone hitpointbar"][:3, 3], [0, 3.0, 0], atol=1e-6))

    def test_a_bone_map_matches_other_names(self):
        src = source_rig()
        tgt = rig([("Bip01", None, (0, 1.0, 0), I), ("Bip01 Spine1", "Bip01", (0, 0.1, 0), I)])
        rt = Retarget(src, tgt, bone_map={"Bip01 Spine1": "Bip01 Spine"})
        matched, tgt_only, src_only, root, _s = rt.report()
        self.assertEqual(matched, ["Bip01", "Bip01 Spine1"])
        self.assertEqual(root, "bip01")
        self.assertIn("bone_launchpoint", src_only)
        self.assertEqual(tgt_only, [])

    def test_the_animation_is_named_after_the_target_model(self):
        src, tgt = source_rig(), target_rig(spine_turn=10.0)
        rt = Retarget(src, tgt)
        anim = clip(src, lambda t: {"Bip01 Spine": ((0, 0.1, 0), axis_quat((1, 0, 0), 60 * t)),
                                    "Bip01": ((0, 1.0, 0.3 * t), I)}, duration=1.0, n=31)
        data, times, frames = rt.animation(anim, "Bip01", fps=30)
        root = gr2.load(data).root()
        groups = root.get("TrackGroups")
        self.assertEqual([g.get("Name") for g in groups], ["Bip01"])
        names = [t.get("Name") for t in groups[0].get("TransformTracks")]
        self.assertEqual(names, sorted(tgt.names, key=lambda n: n.encode()))
        back = Animation.load(data)
        self.assertEqual(back.accumulation, anim.accumulation)
        for t in (0.0, 0.37, 1.0):
            want = rt.worlds(rt.source_pose(anim, t))
            got = tgt.pose(back, t)
            for w, g in zip(want, got):
                self.assertTrue(np.allclose(w, g, atol=5e-3))


class PrecompTest(unittest.TestCase):
    def test_tag_names_find_their_bones(self):
        tgt = rig([("Bip01", None, (0, 1, 0), I), ("Bip01 L Toe0", "Bip01", (0, -1, 0.1), I),
                   ("Bip01 Head", "Bip01", (0, 0.7, 0), I), ("bone hitpointbar", "Bip01", (0, 2, 0), I)])
        self.assertEqual(tag_bone("HEAD", tgt), "bip01 head")
        self.assertEqual(tag_bone("L TOE", tgt), "bip01 l toe0")
        self.assertEqual(tag_bone("HITPOINTBAR", tgt), "bone hitpointbar")
        self.assertIsNone(tag_bone("MASTER", tgt))
        self.assertIsNone(tag_bone("LAUNCHPOINT", tgt))

    def test_bone_tags_move_the_others_stay(self):
        rot = struct.pack("<4f", 0, 0, 0, 1)
        doc = precomp.Precomp()
        doc.version, doc.head, doc.names_head = 4, b"\0" * 4, struct.pack("<I", 1)
        doc.middle, doc.blocks, doc.ms_version = b"\0" * 8, 1, 3
        doc.names = ["MASTER", "HEAD", "LAUNCHPOINT"]
        doc.rotations = [[rot] * 3 for _ in range(3)]
        doc.positions = [[(0, 0, 0)] * 3, [(9, 9, 9)] * 3, [(0.2, 1.4, 2.5)] * 3]
        doc.mapping = [(0, [0]), (1, [1]), (2, [2])]
        doc.extra = struct.pack("<I", 0) + b"EP" + struct.pack("<II", 4, 0)
        doc.duration = 1.0
        raw = "m".encode("utf-16-le")
        doc.tail = struct.pack("<I", 1) + raw
        pre = precomp.load(doc.encode())
        tgt = rig([("Bip01", None, (0, 1, 0), I), ("Bip01 Head", "Bip01", (0, 0.7, 0), I)])

        def pose_at(t):
            return tgt.by_name(tgt.worlds([((0, 1, t), I), ((0, 0.7, 0), I)]))
        out, moved, kept = retarget_precomp(pre, tgt, pose_at)
        self.assertEqual(moved, ["HEAD"])
        self.assertEqual(kept, ["MASTER", "LAUNCHPOINT"])
        self.assertTrue(np.allclose(out.positions[1], [(0, 1.7, 0), (0, 1.7, 0.5), (0, 1.7, 1.0)], atol=1e-6))
        self.assertEqual(out.positions[2], pre.positions[2])
        self.assertEqual(out.rotations, pre.rotations)
        self.assertTrue(np.allclose(precomp.load(out.encode()).positions[1], out.positions[1], atol=1e-6))


ANIMFILE = r"""<?xml version="1.0" encoding="utf-8"?>
<animfile>
  <definebone>bone_sling</definebone>
  <attachment>sling
    <component>sling</component>
    <include>units\x\sling01.xml</include>
  </attachment>
  <attachment>torch
    <include>effects\projectiles\torch.xml</include>
  </attachment>
  <attachment>shield_01
    <component>shield_01</component>
  </attachment>
  <component>ModelComp
    <logic type="LowPoly">
      <normal>
        <assetreference type="GrannyModel"><file>units\x\x_01</file></assetreference>
        <attach a="sling" frombone="bone_sling" tobone="PROP1" syncanims="1"/>
        <attach a="shield_01" frombone="bone_shield" tobone="Bip01 L ForeArm" syncanims="0"/>
      </normal>
      <lowpoly>
        <assetreference type="GrannyModel"><file>units\x\lp_x_01</file></assetreference>
        <attach a="sling" frombone="bone_sling" tobone="PROP1" syncanims="1"/>
      </lowpoly>
    </logic>
  </component>
  <anim>Volley_standing_attack
    <assetreference type="GrannyAnim">
      <file>animation_library\natives\x\volley_attack1</file>
      <tag type="Attack">0.55</tag>
    </assetreference>
    <component>ModelComp</component>
  </anim>
  <anim>Raze_Attack
    <assetreference type="GrannyAnim">
      <file>animation_library\natives\x\torch_throwA</file>
    </assetreference>
    <assetreference type="GrannyAnim">
      <file>animation_library\shared\other</file>
    </assetreference>
    <component>ModelComp</component>
    <attach a="torch" frombone="ATTACHPOINT" tobone="L HAND" syncanims="0"/>
  </anim>
</animfile>
"""


class AnimFileTest(unittest.TestCase):
    def setUp(self):
        self.root = ra.parse_animfile(ANIMFILE)
        self.recipe = dict(ra.MACEHUALTIN, clips_from="animation_library\\natives\\x",
                           source_animfile="units\\x\\x.xml", target_model="units\\y\\y",
                           component="ModelCompNew")

    def test_clips_of_the_folder_only(self):
        self.assertEqual(ra.anim_clips(self.root, "animation_library\\natives\\x"),
                         ["volley_attack1", "torch_throwA"])
        sling = ra.parse_animfile(ANIMFILE.replace("natives\\x\\volley", "natives\\x\\sling\\volley"))
        self.assertEqual(ra.anim_clips(sling, "animation_library\\natives\\x"), ["torch_throwA"])

    def test_the_blocks(self):
        text = ra.anim_blocks(self.root, self.recipe, {"volley_attack1": "WoL\\new\\volley_attack1",
                                                       "torch_throwa": "WoL\\new\\torch_throwA"})
        self.assertIn("<definebone>bone_sling</definebone>", text)
        self.assertIn("<attachment>sling", text)
        self.assertIn("<attachment>torch", text)
        self.assertNotIn("shield_01", text)
        self.assertEqual(text.count('<attach a="sling"'), 1)
        self.assertIn("<file>WoL\\new\\volley_attack1</file>", text)
        self.assertIn("<file>WoL\\new\\torch_throwA</file>", text)
        self.assertIn("<file>animation_library\\shared\\other</file>", text)
        self.assertIn('<tag type="Attack">0.55</tag>', text)
        self.assertIn('<attach a="torch" frombone="ATTACHPOINT" tobone="L HAND" syncanims="0"/>', text)
        self.assertEqual(text.count("<component>ModelCompNew</component>"), 2)
        ra.parse_animfile("<root>" + text.split("-->", 2)[-1].replace("<!--", "").replace("-->", "") + "</root>")

    def test_recipes(self):
        for name in ra.RECIPES:
            r = ra.load_recipe(name)
            self.assertTrue(r["target_model"] and r["folder"] and r["clips_from"])

    def test_refuses_a_steam_folder(self):
        code = ra.main(["--game", ROOT, "--out",
                        r"C:\Program Files (x86)\Steam\steamapps\common\Age Of Empires 3\x"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
