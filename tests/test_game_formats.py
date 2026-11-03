# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the game format readers and writers (aoe3game), on synthetic data only.

    python -I tests/test_game_formats.py          (texture tests are skipped without numpy)
"""
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import animxml, deploy, gr2, gr2_write, proto  # noqa: E402

try:
    import numpy as np
    from aoe3game import bundle, ddt
except ImportError:          # plain Python without numpy
    np = None


def box(w=4.0, d=3.0, h=2.0):
    """An open-bottom box in Blender's basis: positions, normals, uvs, triangles."""
    P, N, UV, T = [], [], [], []
    x, y = w / 2, d / 2
    faces = [((0, 0, 1), [(-x, -y, h), (x, -y, h), (x, y, h), (-x, y, h)]),
             ((0, -1, 0), [(-x, -y, 0), (x, -y, 0), (x, -y, h), (-x, -y, h)]),
             ((0, 1, 0), [(x, y, 0), (-x, y, 0), (-x, y, h), (x, y, h)]),
             ((1, 0, 0), [(x, -y, 0), (x, y, 0), (x, y, h), (x, -y, h)]),
             ((-1, 0, 0), [(-x, y, 0), (-x, -y, 0), (-x, -y, h), (-x, y, h)])]
    for n, quad in faces:
        b = len(P)
        for p, uv in zip(quad, [(0, 0), (1, 0), (1, 1), (0, 1)]):
            P.append(p)
            N.append(n)
            UV.append(uv)
        T += [(b, b + 1, b + 2), (b, b + 3, b + 2)]       # mixed winding on purpose
    return P, N, UV, T


def model_bytes(**kw):
    P, N, UV, T = box()
    return gr2_write.static_model("box", P, N, UV, T, texture=r"C:\x\art\mod\buildings\box\box.ddt",
                                  bump=r"C:\x\art\shadows_selections\flat.ddt",
                                  bones=[("bone_flag_civ", (0.0, 0.0, 2.5))], **kw)


class Gr2Test(unittest.TestCase):
    def test_container_and_crc(self):
        data = model_bytes()
        self.assertEqual(data[:16], gr2.MAGIC)
        self.assertTrue(gr2.crc_ok(data))
        facts = gr2.header_facts(data[:1024])
        self.assertEqual((facts["version"], facts["sections"], facts["raw"]), (6, 1, True))
        broken = bytearray(data)
        broken[-1] ^= 0xFF
        self.assertFalse(gr2.crc_ok(bytes(broken)))

    def test_relocations_point_inside_the_section(self):
        c = gr2.read_container(model_bytes())
        size = len(c.data[0])
        for (s, off), (ts, to) in c.relocs.items():
            self.assertEqual((s, ts), (0, 0))
            self.assertLess(off + 4, size + 1)
            self.assertLess(to, size)
        sec = c.sections[0]
        self.assertLessEqual(sec.first16, sec.first8)
        self.assertLessEqual(sec.first8, sec.data_size)

    def test_model_reads_back(self):
        st = gr2.load(model_bytes()).stats()
        self.assertEqual((st["tris"], st["verts"]), (10, 20))
        self.assertEqual(st["index_bits"], [16])
        self.assertEqual(st["art_tool"]["name"], "ESPostExport")
        self.assertEqual([b["name"] for b in st["bones"]], ["bone_main", "box", "bone_flag_civ"])
        self.assertEqual(st["textures"][1], r"C:\x\art\mod\buildings\box\box.ddt")
        self.assertEqual(st["materials"][2]["effect"], "bumpspec_mask_alphatest")
        # Blender (x, y, z) metres -> stored (-x, z, -y) * 0.615157485
        lo, hi = st["bbox"]
        u = gr2_write.STOCK_BASIS["units_per_meter"]
        self.assertAlmostEqual(hi[1], 2.0 * u, places=5)
        self.assertAlmostEqual(lo[2], -1.5 * u, places=5)
        self.assertAlmostEqual(st["bones"][2]["position"][1], 2.5 * u, places=5)

    def test_winding_follows_the_normals(self):
        d = gr2.load(model_bytes())
        r = d.root()
        vs = r.get("VertexDatas")[0].get("Vertices")
        P, N = vs.column("Position"), vs.column("Normal")
        idx = r.get("TriTopologies")[0].get("Indices16")
        ii = struct.unpack(f"<{idx.count}H", idx.raw)
        for k in range(0, len(ii), 3):
            a, b, c = (P[i] for i in ii[k:k + 3])
            u = [b[j] - a[j] for j in range(3)]
            v = [c[j] - a[j] for j in range(3)]
            g = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            n = N[ii[k]]
            self.assertGreater(sum(g[j] * n[j] for j in range(3)), 0)

    def test_v_flip(self):
        def vs(flip):
            r = gr2.load(model_bytes(v_flip=flip)).root()
            return r.get("VertexDatas")[0].get("Vertices").column("TextureCoordinates0")
        self.assertEqual([round(1 - v, 5) for _u, v in vs(True)], [round(v, 5) for _u, v in vs(False)])

    def test_tree_dump(self):
        lines = gr2.dump_tree(gr2.load(model_bytes()))
        self.assertIn('ArtToolInfo.FromArtToolName = "ESPostExport"', lines)
        self.assertIn("ArtToolInfo.UnitsPerMeter = 0.615157485", lines)
        self.assertIn("ArtToolInfo.RightVector = -1 0 0", lines)
        self.assertIn("Materials[2].Maps[0].Map = -> Materials[1]", lines)
        self.assertIn("Meshes[0].PrimaryVertexData = -> VertexDatas[0]", lines)
        self.assertTrue(any(l.startswith("VertexDatas[0].Vertices = [20] x 32 B sha256 ") for l in lines))
        self.assertIn("TriTopologies[0].Indices = [0]", lines)
        self.assertIn('Skeletons[0].Bones[2].Name = "bone_flag_civ"', lines)

    def test_compressed_files_are_refused(self):
        data = bytearray(model_bytes())
        sec_at = 0x20 + struct.unpack_from("<I", data, 0x2C)[0]
        struct.pack_into("<I", data, sec_at, 2)          # Oodle1
        with self.assertRaises(gr2.Compressed):
            gr2.read_container(bytes(data))
        self.assertFalse(gr2.header_facts(bytes(data[:1024]))["raw"])

    def test_large_meshes_use_32_bit_indices(self):
        n = 70000
        P = [(i * 0.001, 0.0, 0.0) for i in range(n)]
        data = gr2_write.static_model("big", P, [(0, 0, 1)] * n, [(0, 0)] * n,
                                      [(0, 1, 2), (n - 3, n - 2, n - 1)], texture="t", bump="b")
        self.assertEqual(gr2.load(data).stats()["index_bits"], [32])


class AnimTest(unittest.TestCase):
    def test_building_anim_file(self):
        text = animxml.building("Tower", r"mod\buildings\tower\tower.gr2", decal=(9.0, 7.5),
                                stages="3x3", bones=("bone_flag_civ",), chimney_bone="bone_chimney")
        root = ET.fromstring(text.encode("utf-8"))
        self.assertEqual(root.tag, "animfile")
        files = [f.text for f in root.iter("file")]
        self.assertIn(r"mod\buildings\tower\tower", files)
        for k in (1, 2, 3):
            self.assertIn(rf"buildings\constructions\3x3_stage{k}", files)
        self.assertFalse(any(f.endswith(".gr2") for f in files))
        self.assertEqual([b.text for b in root.iter("definebone")], ["bone_flag_civ", "bone_chimney"])
        logic = [l.get("type") for l in root.iter("logic")]
        self.assertEqual(logic, ["Variation", "BuildingCompletion"])
        refs = [s.get("ref") for s in root.iter("submodelref")]
        self.assertEqual(refs[-1], "Tower")
        self.assertIn("<width>9.00</width>", text)

    def test_stage_class(self):
        self.assertEqual(animxml.stage_class(4, 4), "2x2")
        self.assertEqual(animxml.stage_class(7.6, 6), "4x4")
        self.assertEqual(animxml.art_path(r"art/mod/x/y.gr2"), r"mod\x\y")


PROTO = ("<Proto version=\"4\">\r\n"
         "\t<Unit id=\"1\" name=\"House\">\r\n\t\t<DBID>15</DBID>\r\n"
         "\t\t<DisplayNameID>100</DisplayNameID>\r\n"
         "\t\t<AnimFile>buildings\\house\\house.xml</AnimFile>\r\n"
         "\t\t<UnitType>Building</UnitType>\r\n"
         "\t\t<Tech column=\"0\" page=\"2\" row=\"0\">BigHouse</Tech>\r\n"
         "\t\t<Flag>Immoveable</Flag>\r\n\t</Unit>\r\n"
         "\t<Unit id='25000' name ='Other'>\r\n\t\t<DBID>25001</DBID>\r\n\t</Unit>\r\n"
         "</Proto>\r\n")
STRINGS = ("<StringTable version=\"8\">\r\n\t<Language name=\"English\">\r\n"
           "\t\t<String _locID='100'>House</String>\r\n"
           "\t\t<String _locID=\"9000000\">Taken</String>\r\n"
           "\t\t<!-- DON'T WRITE STRINGS DOWN HERE -->\r\n\t</Language>\r\n</StringTable>")


class ProtoTest(unittest.TestCase):
    def test_free_id_skips_ids_and_dbids(self):
        idx = proto.Index(PROTO)
        self.assertEqual(idx.ids, {1, 25000})
        self.assertEqual(idx.dbids, {15, 25001})
        self.assertEqual(idx.free_id(), 25002)

    def test_clone_and_insert(self):
        block = proto.clone_unit(proto.unit_text(PROTO, "House"), name="Tower", uid=25002,
                                 fields={"AnimFile": "mod\\t.xml", "ObstructionRadiusX": "3.0000"})
        self.assertIn('<Unit id="25002" name="Tower">', block)
        self.assertIn("<DBID>25002</DBID>", block)
        self.assertIn("<AnimFile>mod\\t.xml</AnimFile>", block)
        self.assertIn("<ObstructionRadiusX>3.0000</ObstructionRadiusX>", block)
        self.assertNotIn("<Tech", block)
        self.assertIn("<UnitType>Building</UnitType>", block)
        text = proto.insert_unit(PROTO, block)
        end = PROTO.rfind("</Proto>")
        self.assertTrue(text.startswith(PROTO[:end]))
        self.assertTrue(text.endswith("</Proto>\r\n"))
        self.assertEqual(proto.remove_unit(text, "Tower"), PROTO)
        with self.assertRaises(proto.ProtoError):
            proto.insert_unit(text, block)

    def test_add_train(self):
        text = proto.add_train(PROTO, "House", "Tower")
        house = proto.unit_text(text, "House")
        self.assertIn('\t\t<Train column="1" page="6" row="0">Tower</Train>\r\n\t</Unit>', house)
        self.assertEqual(proto.add_train(text, "House", "Tower"), text)        # only once
        again = proto.add_train(text, "House", "Keep")
        self.assertLess(again.find(">Tower</Train>"), again.find(">Keep</Train>"))
        with self.assertRaises(proto.ProtoError):
            proto.add_train(PROTO, "Nobody", "Tower")

    def test_strings(self):
        ids = proto.free_locids(STRINGS, 2)
        self.assertEqual(ids, [9000001, 9000002])
        text = proto.add_strings(STRINGS, {ids[0]: "Tower & keep", ids[1]: "A tower"})
        self.assertLess(text.find("9000002"), text.find("DON'T WRITE"))
        self.assertIn("<String _locID='9000001'>Tower &amp; keep</String>", text)
        self.assertEqual(proto.remove_strings(text, ids), STRINGS)

    def test_text_encodings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "s.xml")
            with open(p, "wb") as f:
                f.write(STRINGS.encode("utf-16"))
            text, enc = proto.read_text(p)
            proto.write_text(p, text, enc)
            with open(p, "rb") as f:
                self.assertEqual(f.read(), STRINGS.encode("utf-16"))


class DeployTest(unittest.TestCase):
    def make_copy(self, tmp):
        inst = os.path.join(tmp, "Game")
        os.makedirs(os.path.join(inst, "data"))
        os.makedirs(os.path.join(inst, "art", "buildings"))
        with open(os.path.join(inst, "data", "protoy.xml"), "w", encoding="utf-8", newline="") as f:
            f.write(PROTO)
        with open(os.path.join(inst, "data", "stringtabley.xml"), "wb") as f:
            f.write(STRINGS.encode("utf-16"))
        b = os.path.join(tmp, "bundle")
        os.makedirs(os.path.join(b, "art", "mod", "buildings", "tower"))
        with open(os.path.join(b, "art", "mod", "buildings", "tower", "tower.gr2"), "wb") as f:
            f.write(b"model")
        with open(os.path.join(b, "bundle.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "Tower", "template": "House",
                       "unit": {"AnimFile": "mod\\buildings\\tower\\tower.xml"},
                       "strings": {"DisplayNameID": "Tower", "RolloverTextID": "A tower"}}, f)
        return inst, b

    def digest(self, inst):
        out = {}
        for dp, _dn, fn in os.walk(inst):
            for f in fn:
                with open(os.path.join(dp, f), "rb") as fh:
                    out[os.path.relpath(os.path.join(dp, f), inst)] = hashlib.sha256(fh.read()).hexdigest()
        return out

    def test_apply_and_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst, b = self.make_copy(tmp)
            before = self.digest(inst)
            d = deploy.Deployment(inst)
            m = d.apply(b, log=lambda s: None)
            self.assertEqual(m["units"], ["Tower"])
            text, _ = proto.read_text(os.path.join(inst, "data", "protoy.xml"))
            self.assertIn('name="Tower"', text)
            self.assertIn("<DisplayNameID>9000001</DisplayNameID>", text)
            self.assertTrue(os.path.exists(os.path.join(inst, "art", "mod", "buildings", "tower", "tower.gr2")))
            self.assertTrue(os.path.exists(os.path.join(inst, "data", "protoy.xml" + deploy.BACKUP)))
            d.apply(b, log=lambda s: None)                 # again: replaces, never stacks
            text, _ = proto.read_text(os.path.join(inst, "data", "protoy.xml"))
            self.assertEqual(text.count('name="Tower"'), 1)
            d.undo(log=lambda s: None)
            self.assertEqual(self.digest(inst), before)

    def test_show_as(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst, b = self.make_copy(tmp)
            before = self.digest(inst)
            d = deploy.Deployment(inst)
            d.apply(b, log=lambda s: None, show_as="House")
            text, _ = proto.read_text(os.path.join(inst, "data", "protoy.xml"))
            house = proto.unit_text(text, "House")
            self.assertIn(r"<AnimFile>mod\buildings\tower\tower.xml</AnimFile>", house)
            self.assertIn("<DBID>15</DBID>", house)                       # the rest is untouched
            d.undo(log=lambda s: None)
            self.assertEqual(self.digest(inst), before)

    def test_refusals(self):
        with self.assertRaises(deploy.RefusedPath):
            deploy.Deployment(r"C:\Program Files (x86)\Steam\steamapps\common\Game")
        with tempfile.TemporaryDirectory() as tmp:
            inst, b = self.make_copy(tmp)
            with open(os.path.join(inst, "data", "protoy.xml.XMB"), "wb") as f:
                f.write(b"l33t")
            with self.assertRaises(deploy.RefusedPath):
                deploy.Deployment(inst).apply(b, log=lambda s: None)


@unittest.skipIf(np is None, "numpy is not installed")
class DdtTest(unittest.TestCase):
    def test_bgra_round_trip_and_mips(self):
        img = np.zeros((64, 32, 3), np.uint8)
        img[:, :, 0] = 200
        img[:8] = (10, 20, 30)
        data = ddt.write_bgra(img, alpha=1, usage=0, mips=True)
        h = ddt.read_header(data)
        self.assertEqual((h.width, h.height, h.format, h.alpha, h.mips), (32, 64, 1, 1, 4))
        self.assertEqual(h.levels[0], (16 + 8 * 4, 32 * 64 * 4))
        self.assertEqual(data[h.levels[0][0]:h.levels[0][0] + 4], bytes([30, 20, 10, 255]))  # B G R A
        back = ddt.decode(data)
        self.assertTrue((back[:, :, :3] == img).all())
        self.assertEqual(ddt.decode(data, 3).shape, (8, 4, 4))
        self.assertEqual(h.describe(), "32x64 BGRA alpha=player colour usage=0 mips=4")

    def test_dxt1_block(self):
        block = struct.pack("<HHI", 0xF800, 0x001F, 0x55555555)     # every pixel = colour 1 (blue)
        data = b"RTS3" + bytes([0, 0, 4, 1]) + struct.pack("<IIII", 4, 4, 24, 8) + block
        px = ddt.decode(data)
        self.assertEqual(tuple(px[0, 0]), (0, 0, 255, 255))

    def test_dxt_round_trip(self):
        rng = np.random.default_rng(3)
        img = np.zeros((64, 64, 4), np.uint8)
        img[..., :3] = rng.integers(0, 256, 3)                      # flat blocks first
        img[:32, :, :3] = (200, 30, 40)
        img[:, 40:, :3] = np.linspace(0, 255, 24)[None, :, None].astype(np.uint8)
        img[..., 3] = 255
        img[8:12, 8:24, 3] = 0                                        # a player-colour band
        for fmt in (ddt.DXT1, ddt.DXT3):
            data = ddt.write_dxt(img, fmt)
            h = ddt.read_header(data)
            self.assertEqual((h.format, h.width, h.height, h.mips), (fmt, 64, 64, 5))
            self.assertEqual(h.levels[0][1], 64 * 64 // (2 if fmt == ddt.DXT1 else 1))
            back = ddt.decode(data).astype(int)
            self.assertLess(np.abs(back[..., :3] - img[..., :3]).mean(), 3.0)
            self.assertTrue((np.abs(back[:32, :32, :3] - (200, 30, 40)) <= 6).all())   # flat stays flat
        back = ddt.decode(ddt.write_dxt(img, ddt.DXT3))
        self.assertTrue((back[8:12, 8:24, 3] == 0).all())
        self.assertTrue((back[20:, :, 3] == 255).all())
        self.assertEqual(ddt.decode(ddt.write_dxt(img, ddt.DXT3), 4).shape, (4, 4, 4))

    def test_bundle_picks_the_player_colour_shader(self):
        P, N, UV, T = box()
        with tempfile.TemporaryDirectory() as tmp:
            for masked in (False, True):
                tex = np.full((32, 32, 4), 255, np.uint8)
                if masked:
                    tex[4:6, :, 3] = 0
                out = os.path.join(tmp, str(masked))
                desc = bundle.write(out, name="Box", prefix="mod", positions=P, normals=N, uvs=UV,
                                    triangles=T, texture_rgba=tex, footprint_m=(4, 3))
                base = os.path.join(out, "art", "mod", "buildings", "box", "box")
                effect = gr2.load(base + ".gr2").stats()["materials"][2]["effect"]
                with open(base + ".ddt", "rb") as f:
                    h = ddt.read_header(f.read())
                self.assertEqual(desc["texture"], {"format": "DXT3", "player_colour": masked})
                self.assertEqual(h.format, ddt.DXT3)
                self.assertEqual(effect, "bumpspec_mask_pixelxform" if masked else "bumpspec_mask_alphatest")
            with self.assertRaises(ValueError):
                bundle.write(os.path.join(tmp, "x"), name="Box", prefix="mod", positions=P, normals=N,
                             uvs=UV, triangles=T, texture_rgba=tex, footprint_m=(4, 3), texture_format="DXT1")

    def test_bundle_variants(self):
        P, N, UV, T = box()
        tex = np.full((32, 32, 4), 255, np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            variants = {"lowpoly": {"positions": P[:12], "normals": N[:12], "uvs": UV[:12],
                                    "triangles": T[:6], "texture_rgba": tex[:16, :16]},
                        "damaged": {"positions": P, "normals": N, "uvs": UV, "triangles": T}}
            bundle.write(tmp, name="Box", prefix="mod", positions=P, normals=N, uvs=UV,
                         triangles=T, texture_rgba=tex, footprint_m=(4, 3), variants=variants)
            base = os.path.join(tmp, "art", "mod", "buildings", "box", "box")
            lp = gr2.load(base + "_lp.gr2").stats()
            dmg = gr2.load(base + "_damaged.gr2").stats()
            self.assertEqual(lp["tris"], 6)
            self.assertTrue(lp["textures"][1].endswith("box_lp.ddt"))      # its own texture
            self.assertTrue(dmg["textures"][1].endswith("box.ddt"))        # the main one
            self.assertFalse(os.path.exists(base + "_damaged.ddt"))
            root = ET.parse(base + ".xml").getroot()
            files = [f.text for f in root.iter("file")]
            self.assertIn(r"mod\buildings\box\box_lp", files)
            self.assertIn(r"mod\buildings\box\box_damaged", files)
            logic = [l.get("type") for l in root.iter("logic")]
            self.assertEqual(logic[:2], ["LowPoly", "Destruction"])
            self.assertIn(r"mod\buildings\box\box_death", files)
            anims = [a.text.split()[0] for a in root.iter("anim")]
            self.assertIn("Death", anims)
            death = gr2.load(base + "_death.gr2").root()
            group = death.get("Animations")[0].get("TrackGroups")[0]
            self.assertEqual([t.get("Name") for t in group.get("TransformTracks")], ["Box"])
            with open(os.path.join(tmp, "README.txt"), encoding="utf-8") as f:
                readme = f.read()
            self.assertIn("box_lp.gr2", readme)
            self.assertIn("<Train>", readme)
            with open(os.path.join(tmp, "proto_fields.xml"), encoding="utf-8") as f:
                fields = f.read()
            self.assertIn(r"<AnimFile>mod\buildings\box\box.xml</AnimFile>", fields)

    def test_sink_animation(self):
        data = gr2_write.sink_animation("Tower", [("bone_flag_civ", (0.0, 0.0, 5.0))], 6.0,
                                        duration=3.0, steps=4)
        self.assertTrue(gr2.crc_ok(data))
        r = gr2.load(data).root()
        anim = r.get("Animations")[0]
        self.assertAlmostEqual(anim.get("Duration"), 3.0)
        track = anim.get("TrackGroups")[0].get("TransformTracks")[1]
        pc = track.get("PositionCurve")
        knots = struct.unpack("<5f", pc.get("Knots").raw)
        ys = struct.unpack("<15f", pc.get("Controls").raw)[1::3]
        u = gr2_write.STOCK_BASIS["units_per_meter"]
        self.assertEqual(knots, (0.0, 0.75, 1.5, 2.25, 3.0))
        self.assertAlmostEqual(ys[0], 5.0 * u, places=5)               # the flag starts in place
        self.assertAlmostEqual(ys[-1], (5.0 - 6.0) * u, places=5)       # and sinks the height
        self.assertTrue(all(a > b for a, b in zip(ys, ys[1:])))

    def test_icon_compose(self):
        from aoe3game import icons
        shot = np.zeros((256, 256, 4), np.uint8)
        shot[64:192, 64:192] = (250, 250, 250, 255)                  # an opaque white square
        icon = icons.compose(shot, 64)
        self.assertEqual(icon.shape, (64, 64, 3))
        self.assertTrue((icon[32, 32] > 240).all())                  # the building
        self.assertTrue((icon[0, 0] == icons.FRAME_DARK).all())      # the frame
        self.assertLess(int(icon[10, 10].sum()), 300)                # the dark background

    def test_bundle_sizes(self):
        s = bundle.game_size((14.6, 14.6))
        self.assertEqual(s["stages"], "4x4")
        self.assertEqual(s["rubble"], "BuildingRubble4x4")
        self.assertAlmostEqual(s["radius"][0], round(14.6 * 0.615157485 / 2 * bundle.OBSTRUCTION_RATIO, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
