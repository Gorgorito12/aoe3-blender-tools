# SPDX-License-Identifier: GPL-3.0-or-later
"""Repainting a unit's texture by body part, on synthetic data only: the skin of the packed vertex
stream, attachments hung on a bone, the UV atlas and its masks (tools/uv_atlas.py), the painting
recipes (tools/retexture.py, the AI op against a stand-in ComfyUI), the DXT5 colour writer, the
bitmap font and the overlay folder of tools/named_models.py. No GPU, no game files.

    venv\\Scripts\\python -I tests\\test_retexture.py
"""
import json
import os
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import bitfont  # noqa: E402
import named_models as nm  # noqa: E402
import retexture  # noqa: E402
import uv_atlas  # noqa: E402
from aoe3game import animxml, ddt, gr2, gr2_mesh, gr2_write  # noqa: E402
from core import comfy  # noqa: E402
from core.pngio import encode_png, read_png  # noqa: E402
from fake_comfy import FakeComfy  # noqa: E402

STOCK = ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.0)      # Y up, as the units
ZUP = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0), 1.0)         # Z up, as many hats


def translate(x, y, z, scale=1.0):
    m = np.eye(4) * scale
    m[3] = (x, y, z, 1.0)
    return m


def quad(u0, v0, u1, v1, z0, z1, x=0.0):
    """Two triangles: positions (Blender space) and UVs (v up) of a quad."""
    pos = np.array([[x, 0, z0], [x + 0.2, 0, z0], [x + 0.2, 0, z1], [x, 0, z1]], np.float32)
    uv = np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], np.float32)
    return pos, uv, np.array([[0, 1, 2], [0, 2, 3]])


def body_model():
    """A 'unit' of three islands: a head quad, a left-thigh quad, and a sliver whose UV runs over
    several tiles (left out of the layout)."""
    parts = [quad(0.0, 0.5, 0.5, 1.0, 1.6, 1.9), quad(0.5, 0.0, 1.0, 0.5, 0.4, 0.9, 0.3)]
    pos = np.concatenate([p for p, _, _ in parts] + [np.zeros((3, 3), np.float32)])
    uv = np.concatenate([u for _, u, _ in parts] + [np.array([[0.1, 0.1], [0.2, 4.5], [0.3, 0.1]], np.float32)])
    tris = np.concatenate([parts[0][2], parts[1][2] + 4, np.array([[8, 9, 10]])])
    bones = np.array([[0, -1]] * 4 + [[1, -1]] * 4 + [[0, -1]] * 3)
    weights = np.array([[1.0, 0.0]] * 11, np.float32)
    mesh = {"name": "body", "positions": pos, "normals": None, "uvs": uv, "triangles": tris,
            "face_textures": np.zeros(len(tris), np.int64), "bound_to": ["Bip01 Head", "Bip01 L Thigh"],
            "skin_names": ["Bip01 Head", "Bip01 L Thigh"], "vertex_bones": bones,
            "vertex_weights": weights, "file_positions": pos}
    return {"meshes": [mesh], "bones": [], "skipped": [], "textures": ["t.ddt"], "basis": STOCK,
            "bind": {"Bip01 Head": translate(0.0, 1.8, 0.0)}}


def texture(w=16, h=16):
    tex = np.zeros((h, w, 4), np.uint8)
    tex[..., :3] = 200
    tex[..., 3] = 255
    tex[h // 2:, : w // 2, 3] = 0           # the player colour under the thigh island
    return tex


class Skin(unittest.TestCase):
    def test_the_packed_stream_gives_each_vertex_its_bones_and_weights(self):
        rigid = np.zeros((4, 3), np.float32)
        table = struct.pack("<HHI", 1, 0, 3)
        block = rigid.T.astype("<f4").tobytes() + bytes(32) + bytes(32)
        tail = b"".join(np.zeros(3, "<f4").tobytes() + bytes(w) + bytes(8) + bytes(8)
                        for w in ([255, 0, 1, 0], [128, 127, 2, 5]))
        head = struct.pack("<12I", 0, 0, 0, 6, 1, len(table), 1, len(block), 2, len(tail), 4, 6)
        raw = bytearray(head + bytes(64 - len(head)) + table + block + tail)
        struct.pack_into("<II", raw, 0, gr2_mesh.FD_MAGIC, len(raw) - 12)
        bones, weights = gr2_mesh.packed_skin(bytes(raw))
        self.assertEqual(bones[:4, 0].tolist(), [3, 3, 3, 3])
        self.assertEqual(bones[4].tolist(), [1, -1])                 # a zero weight names no bone
        self.assertEqual(bones[5].tolist(), [2, 5])
        self.assertAlmostEqual(float(weights[5].sum()), 1.0, places=5)
        with self.assertRaises(gr2.Gr2Error):
            gr2_mesh.packed_skin(bytes(raw[:-4]))


class Attach(unittest.TestCase):
    def part(self, bind):
        p = np.array([[0.0, 0.0, 5.0], [1.0, 0.0, 5.0]], np.float32)   # its bone's origin, and 1 off
        mesh = {"name": "hat", "positions": p, "file_positions": p, "triangles": np.zeros((0, 3), np.int64),
                "uvs": None, "normals": None, "face_textures": np.zeros(0, np.int64)}
        return {"meshes": [mesh], "basis": ZUP, "bind": bind}

    def test_a_hat_sits_on_the_head_whatever_the_files_axes(self):
        body = body_model()
        hat = self.part({"bone_hat": translate(0.0, 0.0, 5.0)})
        placed = gr2_mesh.attach(body, hat, "bone_hat", "HEAD")[0]["positions"]
        self.assertTrue(np.allclose(placed[0], (0.0, 0.0, 1.8), atol=1e-5))
        self.assertAlmostEqual(float(np.linalg.norm(placed[1] - placed[0])), 1.0, places=5)

    def test_an_accessory_without_the_bone_uses_its_only_bone_without_its_scale(self):
        hat = self.part({"objdefault": translate(0.0, 0.0, 5.0, scale=0.1)})
        placed = gr2_mesh.attach(body_model(), hat, "bone_hat", "Bip01 Head")[0]["positions"]
        self.assertTrue(np.allclose(placed[0], (0.0, 0.0, 1.8), atol=1e-5))
        self.assertAlmostEqual(float(np.linalg.norm(placed[1] - placed[0])), 1.0, places=5)

    def test_a_missing_body_bone_is_an_error(self):
        with self.assertRaises(KeyError):
            gr2_mesh.attach(body_model(), self.part({}), "bone_hat", "Bip01 Tail")


ANIM = """<animfile>
  <attachment>hat
    <component>hat<logic type="Tech">
      <none><assetreference type="GrannyModel"><file>hats\\round</file>
        <replacetexture><from>hats\\round</from><to>new\\round_hist</to></replacetexture>
      </assetreference></none>
      <Age3><assetreference type="GrannyModel"><file>hats\\bicorne</file></assetreference></Age3>
    </logic></component>
    <anim>Idle<component>hat</component></anim>
  </attachment>
  <attachment>rider<include>units\\rider.xml</include></attachment>
  <attachment>unused<component>u<assetreference type="GrannyModel"><file>x</file></assetreference></component></attachment>
  <component>ModelComp
    <logic type="LowPoly">
      <normal><assetreference type="GrannyModel"><file>units\\soldier</file></assetreference>
        <attach a="hat" frombone="bone_hat" tobone="HEAD" syncanims="0"/>
      </normal>
      <lowpoly><assetreference type="GrannyModel"><file>units\\lp_soldier</file></assetreference></lowpoly>
    </logic>
    <attach a="rider" frombone="hotspot" tobone="Attachpoint" syncanims="1"/>
    <attach a="ghost" frombone="a" tobone="b"/>
  </component>
  <anim>Idle<component>ModelComp</component></anim>
</animfile>
"""


class Attachments(unittest.TestCase):
    def tree(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(ANIM)
        for el in root.iter():
            el.tag = el.tag.lower()
        return root

    def test_the_idle_component_lists_what_hangs_on_it(self):
        got = animxml.idle_attachments(self.tree())
        self.assertEqual([a["name"] for a in got], ["hat", "rider"])        # ghost is not declared
        hat, rider = got
        self.assertEqual((hat["model"], hat["frombone"], hat["tobone"]), ("hats\\round", "bone_hat", "HEAD"))
        self.assertEqual(hat["swaps"], (("hats\\round", "new\\round_hist"),))
        self.assertEqual(rider["include"], "units\\rider.xml")
        self.assertIsNone(rider["model"])

    def test_a_preferred_branch_picks_the_attachment_model(self):
        hat = animxml.idle_attachments(self.tree(), prefer=("age3",))[0]
        self.assertEqual(hat["model"], "hats\\bicorne")

    def test_bone_names_as_attach_writes_them(self):
        names = ["Bip01", "Bip01 Head", "Bip01 Spine1", "Bip01 Spine", "bone_hat"]
        self.assertEqual(animxml.find_bone(names, "HEAD"), "Bip01 Head")
        self.assertEqual(animxml.find_bone(names, "SPINE1"), "Bip01 Spine1")
        self.assertEqual(animxml.find_bone(names, "BONE_HAT"), "bone_hat")
        self.assertIsNone(animxml.find_bone(names, "tail"))


class Atlas(unittest.TestCase):
    def test_bones_name_body_parts(self):
        cases = {"Bip01 Head": "head", "Bip01 Neck": "head", "Bip01 L UpperArm": "arm_l",
                 "Bip01 R Clavicle": "arm_r", "Bip01 R Hand": "hand_r", "Bip01 L Thigh": "leg_l",
                 "Bip01 R Foot": "foot_r", "Bip01 Spine1": "torso", "Bip01 Pelvis": "torso",
                 "Bip01 Ponytail1": "tail", "Bip01 Prop1": "prop", "Bip01": None, "bone hitpointbar": None}
        for bone, part in cases.items():
            self.assertEqual(uv_atlas.part_of_bone(bone), part, bone)

    def test_islands_take_their_part_from_the_skin_and_drop_stretched_triangles(self):
        isl = uv_atlas.islands(body_model())
        self.assertEqual(sorted(i["part"] for i in isl), ["head", "leg_l"])
        self.assertEqual(sum(i.get("stretched", 0) for i in isl), 0)
        self.assertEqual(sum(i["triangles"] for i in isl), 4)

    def test_without_skin_the_place_on_the_model_names_the_part(self):
        isl = uv_atlas.islands(body_model(), by="position")
        self.assertEqual({i["part"] for i in isl}, {"head", "leg_l", "leg_r"} & {i["part"] for i in isl})
        self.assertIn("head", {i["part"] for i in isl})

    def test_rasterising_covers_the_island_in_texture_pixels(self):
        uv = np.array([[[0.0, 0.5], [0.5, 0.5], [0.5, 1.0]], [[0.0, 0.5], [0.5, 1.0], [0.0, 1.0]]], np.float32)
        m = uv_atlas.rasterise(uv, 16, 16)
        self.assertTrue(m[:8, :8].all())                  # v up: the top left quarter
        self.assertFalse(m[9:, :].any() or m[:, 9:].any())

    def test_the_atlas_files(self):
        with tempfile.TemporaryDirectory() as d:
            uv_atlas.write_atlas(body_model(), texture(), d, size=(32, 32))
            doc = json.load(open(os.path.join(d, "atlas.json"), encoding="utf-8"))
            self.assertEqual(doc["size"], [32, 32])
            self.assertEqual(len(doc["islands"]), 2)
            head = np.asarray(read_png(open(os.path.join(d, "masks", "head.png"), "rb").read()))
            self.assertEqual(head.shape[:2], (32, 32))
            self.assertTrue(head[4, 4] > 0 and head[28, 28] == 0)
            for name in ("legs", "body", "leg_l"):
                self.assertTrue(os.path.exists(os.path.join(d, "masks", name + ".png")), name)
            pic = np.asarray(read_png(open(os.path.join(d, "atlas.png"), "rb").read()))
            self.assertGreaterEqual(pic.shape[1], 512)


class Recipes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = self.tmp.name
        uv_atlas.write_atlas(body_model(), texture(), os.path.join(d, "atlas"))
        with open(os.path.join(d, "start.ddt"), "wb") as fh:
            fh.write(ddt.write_bgra(texture(), alpha=1, mips=False))

    def tearDown(self):
        self.tmp.cleanup()

    def run_recipe(self, ops, client=None, **extra):
        recipe = dict({"texture": "start.ddt", "atlas": "atlas", "out": "out.ddt", "ops": ops}, **extra)
        return retexture.run(recipe, self.d, client)

    def test_a_recolour_stays_inside_its_part_and_keeps_the_player_colour(self):
        start, out, _ = self.run_recipe([{"where": ["part:legs"], "op": "recolour", "colour": "#204080",
                                          "shading": 0}])
        self.assertEqual(out[12, 12, :3].tolist(), [32, 64, 128])     # the thigh island
        self.assertEqual(out[2, 2, :3].tolist(), [200, 200, 200])     # the head, untouched
        self.assertTrue((out[..., 3] == start[..., 3]).all())

    def test_player_bands_edges_and_subtraction(self):
        _s, out, _ = self.run_recipe([
            {"where": ["part:head"], "rows": [[0.0, 0.5]], "op": "player", "amount": 1},
            {"where": ["part:body", "-part:head"], "edge": 1, "op": "recolour", "colour": "#ff0000", "shading": 0}])
        self.assertEqual(out[1, 4, 3], 0)                  # top half of the head shows the team
        self.assertEqual(out[7, 4, 3], 255)
        self.assertEqual(out[15, 12, :3].tolist(), [255, 0, 0])         # the thigh's rim
        self.assertEqual(out[12, 12, :3].tolist(), [200, 200, 200])    # not its middle

    def test_an_empty_selection_is_an_error(self):
        with self.assertRaises(retexture.RecipeError):
            self.run_recipe([{"where": ["part:head"], "near": "#000000", "tol": 5, "op": "recolour",
                              "colour": "#ffffff"}])
        with self.assertRaises(retexture.RecipeError):
            self.run_recipe([{"where": ["part:wing"], "op": "recolour", "colour": "#ffffff"}])

    def test_upscaled_written_as_dxt5_with_a_bump_map(self):
        _s, out, written = self.run_recipe(
            [{"where": ["part:head"], "op": "grain", "amount": 0.3, "cell": 2}],
            scale=2, format="DXT5", mips="full", bump="out_b.ddt")
        self.assertEqual(out.shape[:2], (32, 32))
        data = open(os.path.join(self.d, "out.ddt"), "rb").read()
        hd = ddt.read_header(data)
        self.assertEqual((hd.format, hd.alpha, hd.width), (ddt.DXT5, 1, 32))
        self.assertGreater(hd.mips, 1)
        back = ddt.decode(data, 0)
        self.assertLess(int(np.abs(back[..., 3].astype(int) - out[..., 3]).max()), 20)
        bump = ddt.read_header(open(os.path.join(self.d, "out_b.ddt"), "rb").read())
        self.assertEqual((bump.usage, bump.format), (6, ddt.DXT5))
        self.assertEqual(len(written), 2)

    def test_paste_tone_fill_and_blur(self):
        design = np.zeros((4, 4, 4), np.uint8)
        design[..., 0], design[..., 3] = 255, 255
        with open(os.path.join(self.d, "design.png"), "wb") as fh:
            fh.write(encode_png(design))
        swatch = np.full((4, 4, 3), 90, np.uint8)
        with open(os.path.join(self.d, "swatch.png"), "wb") as fh:
            fh.write(encode_png(swatch))
        _s, out, _ = self.run_recipe([
            {"where": ["part:head"], "op": "paste", "image": "design.png", "box": [0.0, 0.0, 0.25, 0.25]},
            {"where": ["part:legs"], "op": "fill", "swatch": "swatch.png", "tile": 4, "shading": 0},
            {"where": ["part:legs"], "op": "tone", "value": 0.5},
            {"where": ["part:legs"], "op": "blur", "radius": 1, "passes": 1}])
        self.assertEqual(out[1, 1, :3].tolist(), [255, 0, 0])
        self.assertEqual(out[6, 6, :3].tolist(), [200, 200, 200])
        self.assertLess(abs(int(out[12, 12, 0]) - 45), 3)

    def test_the_ai_op_repaints_only_its_selection(self):
        def grainy(rgb):
            rng = np.random.default_rng(1)
            return np.clip(rgb.astype(np.int32) + rng.integers(-30, 31, rgb.shape), 0, 255).astype(np.uint8)
        big = np.zeros((128, 128, 4), np.uint8)
        big[..., :3], big[..., 3] = 150, 255
        with open(os.path.join(self.d, "start.ddt"), "wb") as fh:
            fh.write(ddt.write_bgra(big, alpha=1, mips=False))
        with FakeComfy(transform=grainy) as fake:
            op = {"where": ["part:legs"], "op": "ai", "prompt": "wool", "strength": 0.4, "guard": False}
            _s, out, _ = self.run_recipe([op], comfy.Client(fake.url))
        self.assertTrue((out[:60, :60, :3] == 150).all())               # the head, untouched
        self.assertGreater(int(np.abs(out[80:120, 80:120, :3].astype(int) - 150).max()), 0)
        self.assertEqual(op["_report"][0]["region"], "sel")

    def test_an_ai_selection_too_small_to_repaint_is_a_recipe_error(self):
        with self.assertRaises(retexture.RecipeError):
            self.run_recipe([{"where": ["part:legs"], "op": "ai", "prompt": "wool"}], client=object())


class OwnTexture(unittest.TestCase):
    def model(self):
        P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
        N = np.array([[0, 0, 1]] * 3, np.float32)
        UV = np.array([[0, 0], [1, 0], [0, 1]], np.float32)
        return gr2_write.static_model("Box", P, N, UV, np.array([[0, 1, 2]]),
                                      texture="D:\\src\\art\\units\\box\\box_skin.ddt",
                                      bump="D:\\src\\art\\units\\box\\box_skin_b.ddt")

    def test_the_stored_paths_are_renamed_at_the_same_length_and_the_crc_holds(self):
        data, done = retexture.own_texture_paths(self.model(), {"units\\box\\box_skin": "units\\hst\\box_hst1"})
        self.assertEqual(len(data), len(self.model()))
        self.assertTrue(gr2.crc_ok(data))
        names = gr2_mesh.read(data)["textures"]
        self.assertIn("D:\\src\\art\\units\\hst\\box_hst1.ddt", names)
        self.assertIn("D:\\src\\art\\units\\box\\box_skin_b.ddt", names)   # not asked: kept
        self.assertEqual(len(done), 1)

    def test_another_length_or_no_match_is_refused(self):
        with self.assertRaises(ValueError):
            retexture.own_texture_paths(self.model(), {"units\\box\\box_skin": "units\\b\\x"})
        with self.assertRaises(ValueError):
            retexture.own_texture_paths(self.model(), {"units\\nothing": "units\\nothing2"})


class Writers(unittest.TestCase):
    def test_dxt5_colour_textures_keep_a_smooth_alpha(self):
        img = np.zeros((8, 8, 4), np.uint8)
        img[..., :3] = 120
        img[..., 3] = np.linspace(0, 255, 8, dtype=np.uint8)[None, :]
        data = ddt.write(img, ddt.DXT5, alpha=1)
        back = ddt.decode(data, 0)
        self.assertEqual(ddt.read_header(data).format, ddt.DXT5)
        self.assertLess(int(np.abs(back[..., 3].astype(int) - img[..., 3]).max()), 12)

    def test_the_bitmap_font(self):
        img = np.zeros((20, 60, 3), np.uint8)
        bitfont.draw(img, "Arm 1", 1, 1, (255, 255, 255), scale=2)
        self.assertEqual(bitfont.width("Arm 1", 2), 58)
        self.assertGreater(int((img > 0).sum()), 50)
        bitfont.draw(img, "clip", 55, 15, (255, 0, 0), scale=3)       # partly outside: no error


class Overlay(unittest.TestCase):
    def test_an_overlay_folder_wins_over_the_game(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as extra:
            def put(folder, rel, text):
                path = os.path.join(folder, *rel.split("\\"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            put(game, "data\\protoy.xml", '<Proto><Unit id="1" name="Soldier"><AnimFile>units\\s.xml'
                                          '</AnimFile></Unit></Proto>')
            put(game, "art\\units\\s.xml", ANIM)
            put(game, "art\\units\\soldier.gr2", "x")
            put(extra, "art\\new\\s_hist.xml", ANIM.replace("units\\soldier", "units\\soldier_hist"))
            put(extra, "art\\units\\soldier_hist.gr2", "x")
            put(extra, "data\\protoy.xml", '<Proto><Unit id="1" name="Soldier"><AnimFile>new\\s_hist.xml'
                                           '</AnimFile></Unit></Proto>')
            g = nm.Game(game, [extra])
            r = g.resolve("Soldier")
            self.assertEqual(r["model"], "units\\soldier_hist.gr2")
            self.assertEqual([a["name"] for a in r["attachments"]], ["hat", "rider"])
            self.assertEqual(nm.Game(game).resolve("Soldier")["model"], "units\\soldier.gr2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
