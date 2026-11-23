# SPDX-License-Identifier: GPL-3.0-or-later
"""A model taken apart by bone and written again (aoe3game/gr2_parts.py) and the pieces of
tools/make_gun_camel.py that need no game: synthetic streams, meshes and placements only.

    venv\\Scripts\\python -I tests\\test_gun_camel.py
"""
import math
import os
import struct
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import make_gun_camel as gc  # noqa: E402
from aoe3game import gr2, gr2_mesh, gr2_parts, gr2_skin, gr2_write  # noqa: E402
from aoe3game.gr2_anim import Rig  # noqa: E402


def packed_stream(rigid_normals, skinned_normal):
    """A packed vertex stream: one rigid block of four vertices on bone 0, one skinned vertex."""
    head = 64
    table = struct.pack("<HHI", 1, 0, 0)
    block = bytearray(112)
    xs, ys, zs = [0.0, 1.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0], [0.5] * 4
    struct.pack_into("<12f", block, 0, *xs, *ys, *zs)
    for k, n in enumerate(rigid_normals):
        block[48 + 4 * k:52 + 4 * k] = bytes(n) + b"\xff"
    struct.pack_into("<8f", block, 80, *([0.25, 0.75] * 4))
    sk = bytearray(32)
    struct.pack_into("<3f", sk, 0, 2.0, 2.0, 2.0)
    sk[12:16] = bytes([255, 0, 0, 0])
    sk[16:20] = bytes(skinned_normal) + b"\xff"
    struct.pack_into("<2f", sk, 24, 0.5, 0.5)
    body = table + bytes(block) + bytes(sk)
    words = [gr2_mesh.FD_MAGIC, head + len(body) - 12, 0, 5, 1, len(table), 1, 112, 1, 32, 4, 1]
    return struct.pack("<12I", *words) + bytes(head - 48) + body


def quad_model(name="part", tris=None):
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (3, 0, 0), (3, 1, 0)]
    nrm = [(0, 0, 1)] * len(pos)
    uvs = [(p[0] / 3.0, p[1]) for p in pos]
    tris = tris or [(0, 1, 2), (0, 2, 3), (4, 5, 6), (1, 4, 2)]
    return gr2_write.static_model(name, pos, nrm, uvs, tris, texture="t\\a.ddt", bump="t\\a_b.ddt")


class PackedNormals(unittest.TestCase):
    def test_bytes_biased_by_64_of_127(self):
        raw = packed_stream([(127, 64, 64), (0, 64, 64), (64, 127, 64), (64, 48, 125)], (64, 64, 0))
        n = gr2_parts.packed_normals(raw)
        self.assertEqual(n.shape, (5, 3))
        self.assertTrue(np.allclose(n[0], (1, 0, 0), atol=0.02))
        self.assertTrue(np.allclose(n[1], (-1, 0, 0), atol=0.02))
        self.assertTrue(np.allclose(n[2], (0, 1, 0), atol=0.02))
        self.assertTrue(np.allclose(n[3], (0, -0.25, 0.97), atol=0.03))
        self.assertTrue(np.allclose(n[4], (0, 0, -1), atol=0.02))
        self.assertTrue(np.allclose(np.linalg.norm(n, axis=1), 1.0))

    def test_a_bad_stream_is_refused(self):
        raw = bytearray(packed_stream([(64, 64, 127)] * 4, (64, 64, 127)))
        raw[0] ^= 1
        with self.assertRaises(gr2.Gr2Error):
            gr2_parts.packed_normals(bytes(raw))


class Components(unittest.TestCase):
    def test_welded_by_position(self):
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0.0], [2, 0, 0], [1, 1, 0],
                        [5, 5, 5], [6, 5, 5], [5, 6, 5]], np.float64)
        tris = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        c = gr2_parts.components(pos, tris)
        self.assertEqual(c[0], c[1])            # share the corner (1, 0, 0), stored twice
        self.assertNotEqual(c[0], c[2])
        self.assertEqual(list(c), [0, 0, 1])


class Cut(unittest.TestCase):
    def test_only_the_triangles_change(self):
        data = quad_model()
        keep = np.array([True, True, False, True])
        out = gr2_parts.cut_triangles(data, "part", keep)
        a, b = gr2_mesh.read(data)["meshes"][0], gr2_mesh.read(out)["meshes"][0]
        self.assertEqual(len(b["triangles"]), 3)
        self.assertTrue(np.array_equal(a["triangles"][keep], b["triangles"]))
        self.assertTrue(np.array_equal(a["file_positions"], b["file_positions"]))
        self.assertTrue(gr2.crc_ok(out))
        g = gr2.load(out).root().get("Meshes")[0].get("PrimaryTopology").get("Groups")
        self.assertEqual(struct.unpack_from("<3i", g.raw, 0), (0, 0, 3))

    def test_wrong_mask_or_mesh(self):
        data = quad_model()
        with self.assertRaises(ValueError):
            gr2_parts.cut_triangles(data, "part", [True])
        with self.assertRaises(KeyError):
            gr2_parts.cut_triangles(data, "nothing", [True] * 4)


class RigidModel(unittest.TestCase):
    def setUp(self):
        self.src = quad_model()
        part = gr2_parts.mesh_parts(self.src)[0]
        self.part = part
        sel = np.array([True, True, False, False])
        self.a = gc.sub_part(part, sel)
        self.b = gc.sub_part(part, ~sel)

    def bones(self):
        spin = np.eye(4)
        spin[:3, 3] = (2.5, 0.5, 0.0)
        return [("root", -1, np.eye(4)), ("bone_a", 0, gc.tr((0.5, 0.5, 0.0))), ("bone_b", 1, spin)]

    def write(self):
        parts = [dict(self.a, name="a", bone="bone_a"), dict(self.b, name="b", bone="bone_b")]
        return gr2_parts.rigid_model(self.src, "root", self.bones(), parts)

    def test_read_back_parts_bones_materials(self):
        data = self.write()
        self.assertTrue(gr2.crc_ok(data))
        read = gr2_mesh.read(data)
        self.assertEqual([m["name"] for m in read["meshes"]], ["a", "b"])
        self.assertEqual([m["bound_to"] for m in read["meshes"]], [["bone_a"], ["bone_b"]])
        self.assertTrue(np.allclose(read["meshes"][0]["file_positions"], self.a["positions"], atol=1e-6))
        self.assertEqual(len(read["meshes"][1]["triangles"]), 2)
        rig = Rig.of(gr2.load(data).root())
        rest = rig.by_name(rig.rest_worlds())
        self.assertTrue(np.allclose(rest["bone_b"][:3, 3], (2.5, 0.5, 0.0), atol=1e-6))
        self.assertTrue(read["textures"] and any("a.ddt" in (t or "") for t in read["textures"]))

    def test_a_turned_bone_turns_only_its_part(self):
        data = self.write()
        read = gr2_mesh.read(data)
        skel = read["skeletons"][0]
        rig = Rig.of(gr2.load(data).root())
        pose = rig.by_name(rig.rest_worlds())
        turn = gc.tr((2.5, 0.5, 0.0)) @ gc.rot4(gc.axis_matrix(gc.Z, 90.0)) @ gc.tr((-2.5, -0.5, 0.0))
        pose["bone_b"] = turn @ pose["bone_b"]
        exact = {n: pose[n.lower()] for n in rig.names}
        a, b = read["meshes"]
        pa = gr2_skin.deform(a["file_positions"], a["vertex_bones4"], a["vertex_weights4"], a["skin_names"], skel, exact)
        pb = gr2_skin.deform(b["file_positions"], b["vertex_bones4"], b["vertex_weights4"], b["skin_names"], skel, exact)
        self.assertTrue(np.allclose(pa, a["file_positions"], atol=1e-6))
        self.assertTrue(np.allclose(pb, gc.apply(turn, b["file_positions"]), atol=1e-5))


class SwivelCut(unittest.TestCase):
    def test_pieces_and_post(self):
        # a body at x >= 0, and two pieces at x < -0.2 above y 1.6: a vertical post and a bar on it
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0],
                        [-0.3, 1.7, 0], [-0.3, 2.4, 0], [-0.3, 2.4, 0.1],
                        [-0.3, 2.45, -0.3], [-0.3, 2.45, 0.7], [-0.3, 2.5, 0.2]], np.float64)
        tris = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        part = {"positions": pos, "triangles": tris, "vertex_bone": np.zeros(len(pos), np.int64),
                "skin_names": ["Chest"]}
        mask, pieces = gc.swivel_pieces(part, "Chest", -0.18, 1.6)
        self.assertEqual(list(mask), [False, True, True])
        posts = [p for p in pieces if p[2]]
        self.assertEqual(len(posts), 1)
        self.assertEqual(list(posts[0][1]), [1])
        top = gc.post_top(part, pieces)
        self.assertAlmostEqual(top[1], 2.4)
        self.assertAlmostEqual(top[0], -0.3)


class FakeSource:
    trunnion = np.array([0.05, 1.2, 0.1])
    barrel_at = np.array([0.05, 1.3, 0.4])
    crank_at = np.array([0.22, 1.25, -0.5])
    muzzle_at = np.array([0.05, 1.2, 1.25])
    handle = np.array([0.31, 1.03, -0.5])
    seat = 0.06
    breech_top = np.array([0.05, 1.43, -0.75])
    mag_top = np.array([0.0, 2.4, -0.3])
    mag_base = np.array([0.0, 1.5, -0.3])
    ammo_rest = gc.tr((0.0, 1.95, -0.31))
    parts = {}


class Design(unittest.TestCase):
    def setUp(self):
        r = gc.rot4(gc.axis_matrix(gc.Y, 90.0))[:3, :3] * 0.9
        self.bind = np.eye(4)
        self.bind[:3, :3] = r
        self.bind[:3, 3] = (0.0, 1.5, 0.4)
        self.post = np.array([-0.24, 2.39, 0.4])

    def test_scale_seen_in_game_and_mirror(self):
        g = gc.GunDesign(FakeSource(), self.bind, self.post, 0.55)
        self.assertAlmostEqual(g.bind_scale, 0.9)
        self.assertAlmostEqual(g.s, 0.55 * 0.9)
        self.assertTrue(np.allclose(g.at["cannon"], self.post + (0, g.s * 0.06, 0)))
        m = gc.GunDesign(FakeSource(), self.bind, self.post, 0.55, mirror=True)
        d, dm = g.handle - g.pivot, m.handle - m.pivot
        self.assertAlmostEqual(d[0], -dm[0])
        self.assertAlmostEqual(d[1], dm[1])
        # drawn through the mount at its bind, the gun is `scale` of its own size: 1 / bind scale
        seen = gc.point(self.bind @ g.S, g.handle) - gc.point(self.bind @ g.S, g.pivot)
        self.assertTrue(np.allclose(seen, d))

    def test_model_frames_and_spin(self):
        g = gc.GunDesign(FakeSource(), self.bind, self.post, 0.7)
        rest = g.frames({})
        spun = g.frames({"barrel": 123.0, "crank": -45.0})
        # the barrel turns about its own axis: its origin stays
        self.assertTrue(np.allclose(spun["barrel"][:3, 3], rest["barrel"][:3, 3]))
        self.assertFalse(np.allclose(spun["barrel"][:3, :3], rest["barrel"][:3, :3]))
        self.assertTrue(np.allclose(spun["barrel"][:3, :3] @ gc.Z, gc.Z))
        self.assertTrue(np.allclose(spun["crank"][:3, :3] @ gc.X, gc.X))
        # the gun model's space is the mount bone's: a design frame and back
        m = g.to_model(rest["crank"])
        back = self.bind @ m
        self.assertTrue(np.allclose(back[:3, 3], rest["crank"][:3, 3]))


class Rhythm(unittest.TestCase):
    def test_whole_turns_so_shots_join(self):
        u = gc.Unit.__new__(gc.Unit)
        u.gun = gc.GunDesign(FakeSource(), np.eye(4), np.zeros(3), 0.55)
        a, b = u.fire_state(0.0, 1.0), u.fire_state(1.0, 1.0)
        self.assertAlmostEqual((b["barrel"] - a["barrel"]) % 360.0, 0.0)
        self.assertAlmostEqual((b["crank"] - a["crank"]) % 360.0, 0.0)
        self.assertAlmostEqual(abs(b["barrel"] / b["crank"]), gc.BARREL_TURNS / gc.CRANK_TURNS)
        self.assertEqual(len(gc.Unit.shots(1.0)), gc.SHOTS)
        self.assertEqual(a["recoil"], 0.0)

    def test_the_reload_starts_and_ends_seated(self):
        self.assertEqual(gc.RELOAD[0], (0.0, "rest"))
        self.assertEqual(gc.RELOAD[-1], (1.0, "rest"))
        u = gc.Unit.__new__(gc.Unit)
        u.variant = "A"
        u.gun = gc.GunDesign(FakeSource(), np.eye(4), np.zeros(3), 0.55)
        keys = u.magazine_keys(np.array([-0.5, 1.0, 0.0]))
        for share in (0.0, 1.0):
            m = u.magazine_frame(keys, share)
            self.assertTrue(np.allclose(m[:3, 3], u.gun.at["ammo"]))
            self.assertTrue(np.allclose(m[:3, :3], np.eye(3)))

    def test_the_climb_holds_the_camel_down(self):
        b = {c["name"]: c for c in gc.CLIPS["B"]}
        self.assertGreater(b["deploy"].get("hold_after", 0.0), 1.0)       # gets off after it lies down
        self.assertGreater(b["undeploy"].get("hold_before", 0.0), 1.0)    # gets on before it rises
        for variant in ("A", "B"):
            names = {c["name"] for c in gc.CLIPS[variant]}
            self.assertTrue({"walk", "jog", "run"} <= names, variant)
            moving = [c for c in gc.CLIPS[variant] if c["name"] in ("walk", "jog", "run")]
            self.assertTrue(all(c.get("gait") and not c.get("rider") for c in moving), variant)

    def test_every_clip_names_its_length(self):
        for variant, clips in gc.CLIPS.items():
            names = [c["anim"] for c in clips]
            self.assertEqual(len(names), len(set(names)), variant)
            for c in clips:
                self.assertTrue(("camel" in c) or ("borrow" in c) or ("still" in c and "length" in c), c)


class Refusals(unittest.TestCase):
    def test_steam_is_refused(self):
        code = gc.main(["--game", "C:\\nowhere", "--out",
                        "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Age Of Empires 3\\x"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
