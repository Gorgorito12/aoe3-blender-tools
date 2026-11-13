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
    from aoe3game import bundle, collision, ddt
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

    def test_clone_drops_comments_that_span_dropped_lines(self):
        # a comment opened on one line and closed on a <Tech> line, as in the mod's town center
        template = ('<Unit id="7" name="Hall">\r\n\t\t<DBID>7</DBID>\r\n'
                    "\t\t<!-- <Tech column='1'>A</Tech>\r\n"
                    "\t\t<Tech column='2'>B</Tech> -->\r\n"
                    "\t\t<!-- Fake buttons -->\r\n"
                    "\t\t<Tech column='3'>C</Tech>\r\n"
                    "\t\t<UnitType>Building</UnitType>\r\n\t</Unit>")
        block = proto.clone_unit(template, name="NewHall", uid=25009, fields={})
        ET.fromstring(block)                                   # well formed
        self.assertNotIn("<!--", block)
        self.assertNotIn("<Tech", block)
        self.assertIn("<UnitType>Building</UnitType>", block)

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

    def test_apply_many_and_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst, b = self.make_copy(tmp)
            b2 = os.path.join(tmp, "bundle2")
            os.makedirs(os.path.join(b2, "art", "mod", "buildings", "inn"))
            with open(os.path.join(b2, "art", "mod", "buildings", "inn", "inn.gr2"), "wb") as f:
                f.write(b"model2")
            with open(os.path.join(b2, "bundle.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "Inn", "template": "House", "unit": {"AnimFile": "mod\\buildings\\inn\\inn.xml"},
                           "strings": {"DisplayNameID": "Inn"}}, f)
            before = self.digest(inst)
            d = deploy.Deployment(inst)
            m = d.apply_many([b, b2], log=lambda s: None)
            self.assertEqual(m["units"], ["Tower", "Inn"])
            self.assertEqual(len(set(m["unit_ids"])), 2)
            self.assertEqual(len(set(m["strings"])), 3)
            text, _ = proto.read_text(os.path.join(inst, "data", "protoy.xml"))
            self.assertIn('name="Tower"', text)
            self.assertIn('name="Inn"', text)
            d.apply_many([b2], log=lambda s: None)         # again: replaces both
            text, _ = proto.read_text(os.path.join(inst, "data", "protoy.xml"))
            self.assertNotIn('name="Tower"', text)
            self.assertEqual(text.count('name="Inn"'), 1)
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

    def test_a_budget_halves_the_painting_and_nothing_else(self):
        P, N, UV, T = box()
        tex = np.random.default_rng(1).integers(0, 255, (64, 64, 4), np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            bundle.write(tmp, name="Box", prefix="mod", positions=P, normals=N, uvs=UV, triangles=T,
                         texture_rgba=tex, footprint_m=(4, 3), texture_max=32, bump_max=16)
            base = os.path.join(tmp, "art", "mod", "buildings", "box", "box")
            with open(base + ".ddt", "rb") as f:
                main = ddt.read_header(f.read())
            with open(base + "_b.ddt", "rb") as f:
                bump = ddt.read_header(f.read())
        self.assertEqual((main.width, bump.width), (32, 16))
        self.assertTrue((ddt.fitted(tex, 32) == ddt.mip_chain(tex)[1]).all())   # the game's own mip level
        self.assertIs(ddt.fitted(tex, 64), tex)                                 # a smaller budget only

    def test_a_style_can_name_the_rubble(self):
        self.assertEqual(bundle.game_size((14.6, 14.6), rubble="BuildingRubble6x6")["rubble"], "BuildingRubble6x6")
        self.assertNotEqual(bundle.game_size((14.6, 14.6))["rubble"], "BuildingRubble6x6")

    def test_a_building_can_carry_its_own_collision_boxes(self):
        P, N, UV, T = box()
        boxes = [(-2.0, 2.0, -1.0, 3.0, 0.0, 4.0), (-1.0, 1.0, -3.0, -1.0, 0.0, 2.0)]
        with tempfile.TemporaryDirectory() as tmp:
            tex = np.full((32, 32, 4), 255, np.uint8)
            desc = bundle.write(tmp, name="Box", prefix="mod", positions=P, normals=N, uvs=UV, triangles=T,
                                texture_rgba=tex, footprint_m=(4, 3), collision_boxes=boxes)
            path = os.path.join(tmp, "data", "physics", "box.shp")
            self.assertIn(os.path.join("data", "physics", "box.shp"), desc["files"])
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            with open(os.path.join(tmp, "art", "mod", "buildings", "box", "box.xml"), encoding="utf-8") as f:
                anim = f.read()
        self.assertIn('shape="box"', anim)
        self.assertNotIn("outpost_generic\"", anim)
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8" ?>\r\n<hke '))
        root = ET.fromstring(text)
        types = [o.get("type") for o in root.iter("hkobject")]
        self.assertEqual(types.count("hkBoxShape"), 2)
        self.assertEqual(types[-1], "hkListShape")
        u = bundle.UNITS_PER_METER
        half, centre = collision.stored(boxes[1], u)       # (x, y, z) -> (-x, z, -y) * units
        self.assertAlmostEqual(half[0], 1.0 * u)
        self.assertAlmostEqual(half[1], 1.0 * u)
        self.assertAlmostEqual(centre[1], 1.0 * u)
        self.assertAlmostEqual(centre[2], 2.0 * u)
        with self.assertRaises(ValueError):
            collision.shape_xml([(0.0, 0.0, 0.0, 1.0, 0.0, 1.0)], u)

    def test_normal_map(self):
        img = np.full((32, 32, 3), 200, np.uint8)
        img[:, 16:] = 60                                   # a dark band: lower ground
        nm = ddt.normal_from_texture(img, blur=0)
        self.assertEqual(nm.shape, (32, 32, 4))
        self.assertTrue((nm[..., 0] == 0).all())           # no specular
        self.assertTrue((abs(nm[2:-2, 2:12, 3].astype(int) - 128) <= 1).all())   # flat: X 0
        self.assertGreater(nm[10, 15, 3], 160)             # the edge leans toward +X (downhill)
        data = ddt.write_normal_map(nm)
        h = ddt.read_header(data)
        self.assertEqual((h.format, h.usage, h.alpha, h.mips), (ddt.DXT5, 6, 0, 1))
        back = ddt.decode(data).astype(int)
        for c in (1, 2, 3):
            self.assertLess(abs(back[..., c] - nm[..., c]).mean(), 3.0)

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
            self.assertTrue(lp["textures"][0].endswith("box_lp_b.ddt"))    # each texture's relief
            self.assertTrue(dmg["textures"][0].endswith("box_b.ddt"))
            with open(base + "_b.ddt", "rb") as f:
                self.assertEqual(ddt.read_header(f.read()).format, ddt.DXT5)
            root = ET.parse(base + ".xml").getroot()
            files = [f.text for f in root.iter("file")]
            self.assertIn(r"mod\buildings\box\box_lp", files)
            self.assertIn(r"mod\buildings\box\box_damaged", files)
            logic = [l.get("type") for l in root.iter("logic")]
            self.assertEqual(logic[:2], ["LowPoly", "Destruction"])
            # every model reference has the shape, the low-poly one too (else the game ignores it)
            lp_ref = next(a for a in root.iter("assetreference") if a.findtext("file", "").endswith("box_lp"))
            self.assertTrue(lp_ref.get("shape"))
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
        # a low-poly model alone still borrows the skeleton that gives the shape
        with tempfile.TemporaryDirectory() as tmp:
            bundle.write(tmp, name="Box", prefix="mod", positions=P, normals=N, uvs=UV, triangles=T,
                         texture_rgba=tex, footprint_m=(4, 3), variants={"lowpoly": variants["lowpoly"]})
            root = ET.parse(os.path.join(tmp, "art", "mod", "buildings", "box", "box.xml")).getroot()
            refs = [a for a in root.iter("assetreference")
                    if a.get("type") == "GrannyModel" and a.findtext("file", "").startswith("mod")]
            self.assertTrue(refs and all(a.get("shape") for a in refs), [a.attrib for a in refs])
            self.assertTrue(list(root.iter("simskeleton")))

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


class PropAnim(unittest.TestCase):
    """A prop's anim file, against the layout measured on the stock files (2026-11-10):
    Art\\nuggets\\bear_campsite\\nugget_bear_campsite.xml and Art\\objects\\el_dorado\\el_dorado.xml."""

    def test_a_prop_has_a_component_and_an_idle_anim_and_nothing_of_a_building(self):
        text = animxml.prop("Barrel", "mod\\objects\\barrel\\barrel", decal=(4.0, 4.0))
        root = ET.fromstring(text)
        self.assertEqual([e.tag for e in root], ["component", "anim"])
        self.assertNotIn("BuildingCompletion", text)
        self.assertNotIn("submodel", text)
        self.assertNotIn("construction", text)
        self.assertEqual(root.find("component/assetreference/file").text,
                         "mod\\objects\\barrel\\barrel")
        self.assertEqual(root.find("anim").text.strip(), "Idle")

    def test_the_decal_is_a_selection_square_without_a_ground_texture(self):
        root = ET.fromstring(animxml.prop("Barrel", "mod\\objects\\barrel\\barrel", decal=(8.0, 8.0)))
        decal = root.find("component/decal")
        self.assertIsNone(decal.find("texture"))
        self.assertIsNotNone(decal.find("selectedtexture"))
        self.assertEqual(decal.find("width").text, "8.00")

    def test_a_ground_texture_is_written_with_its_bump_as_the_stock_nuggets_do(self):
        root = ET.fromstring(animxml.prop("Barrel", "mod\\objects\\barrel\\barrel", decal=(4.0, 4.0),
                                          ground="mod\\objects\\barrel\\barrel_ground"))
        decal = root.find("component/decal")
        self.assertEqual(decal.find("effecttype").text, "bump")
        self.assertEqual(decal.find("texture").text, "mod\\objects\\barrel\\barrel_ground")
        self.assertIsNotNone(decal.find("bumptexture"))

    def test_no_decal_at_all(self):
        root = ET.fromstring(animxml.prop("Barrel", "mod\\objects\\barrel\\barrel"))
        self.assertIsNone(root.find("component/decal"))

    def test_a_death_model_adds_its_component_and_a_death_anim(self):
        text = animxml.prop("Barrel", "mod\\objects\\barrel\\barrel",
                            death_model="mod\\objects\\barrel\\barrel_dead",
                            death_anim="mod\\objects\\barrel\\barrel_deathanim")
        root = ET.fromstring(text)
        self.assertEqual([e.get("a") for e in root.findall("anim/attach")],
                         [a for a, _c, _p in animxml.COLLAPSE_SMOKE])
        self.assertEqual([e.text.strip() for e in root.findall("anim")], ["Idle", "Death"])
        self.assertEqual([e.text.strip() for e in root.findall("component")], ["Barrel", "BarrelDeath"])

    def test_a_death_animation_alone_is_ignored(self):
        root = ET.fromstring(animxml.prop("Barrel", "mod\\objects\\barrel\\barrel",
                                          death_anim="mod\\objects\\barrel\\x"))
        self.assertEqual([e.text.strip() for e in root.findall("anim")], ["Idle"])

    def test_bones_are_defined_so_a_socket_reaches_the_game(self):
        root = ET.fromstring(animxml.prop("Barrel", "mod\\objects\\barrel\\barrel",
                                          bones=("bone_main", "bone_smoke")))
        self.assertEqual([e.text for e in root.findall("definebone")], ["bone_main", "bone_smoke"])


@unittest.skipIf(np is None, "needs numpy")
class GroupingDeploy(unittest.TestCase):
    def test_a_grouping_goes_into_every_groupings_folder_and_undo_takes_it_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            for d in ("art", "data", os.path.join("RM", "groupings"), os.path.join("RM3", "groupings")):
                os.makedirs(os.path.join(tmp, d))
            old = os.path.join(tmp, "RM3", "groupings", "Native Test 1.xml")
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("<grouping/>")
            src = os.path.join(tmp, "Native Test 1.xml")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("<grouping><units/></grouping>")
            d = deploy.Deployment(tmp)
            written = d.add_grouping(src, log=lambda s: None)
            self.assertEqual(len(written), 2)
            self.assertEqual(open(old, encoding="utf-8").read(), "<grouping><units/></grouping>")
            d.undo(log=lambda s: None)
            self.assertFalse(os.path.exists(os.path.join(tmp, "RM", "groupings", "Native Test 1.xml")))
            self.assertEqual(open(old, encoding="utf-8").read(), "<grouping/>")


class PropSet(unittest.TestCase):
    """One unit, many models on one texture: the Variation layout of the stock colony props."""

    def test_the_anim_file_is_one_component_with_a_variation_per_model(self):
        text = animxml.prop_set("Goods", ["mod\\objects\\goods\\goods_0", "mod\\objects\\goods\\goods_1"])
        root = ET.fromstring(text.split("?>", 1)[1])
        comps = root.findall("component")
        self.assertEqual(len(comps), 1)
        logic = comps[0].find("logic")
        self.assertEqual(logic.get("type"), "Variation")
        files = [d.find("assetreference/file").text for d in logic.findall("data")]
        self.assertEqual(files, ["mod\\objects\\goods\\goods_0", "mod\\objects\\goods\\goods_1"])
        idle = root.find("anim")
        self.assertEqual(idle.text.strip(), "Idle")
        self.assertEqual(idle.find("assetreference").get("type"), "GrannyAnim")
        self.assertEqual(idle.find("component").text, "Goods")
        with self.assertRaises(ValueError):
            animxml.prop_set("Empty", [])

    def test_a_set_bundle_writes_every_model_on_one_texture_and_reads_back(self):
        P, N, UV, T = box()
        tex = np.full((32, 32, 4), 255, np.uint8)
        models = [{"positions": P, "normals": N, "uvs": UV, "triangles": T}] * 3
        with tempfile.TemporaryDirectory() as tmp:
            desc = bundle.write_set(tmp, name="Goods", prefix="mod", models=models, texture_rgba=tex,
                                    footprint_m=(2, 2))
            art = os.path.join(tmp, "art", "mod", "objects", "goods")
            names = sorted(os.listdir(art))
            for i in range(3):
                data = open(os.path.join(art, f"goods_{i}.gr2"), "rb").read()
                doc = gr2.load(data)
                tex_names = [t.get("FromFileName") for t in doc.root().get("Textures")]
                self.assertIn("C:\\aoe3bt\\art\\mod\\objects\\goods\\goods.ddt", tex_names)
            readme = open(os.path.join(tmp, "README.txt"), encoding="utf-8").read()
        self.assertEqual([n for n in names if n.endswith(".ddt") and not n.endswith("_b.ddt")], ["goods.ddt"])
        self.assertEqual(desc["kind"], "PROP")
        self.assertEqual(desc["set"], 3)
        self.assertEqual(desc["unit"]["AnimFile"], "mod\\objects\\goods\\goods.xml")
        self.assertNotIn("DeadReplacement", desc["unit"])
        self.assertIn("variation", readme)


class PropBundle(unittest.TestCase):
    def _write(self, tmp, **kw):
        P, N, UV, T = box()
        tex = np.full((32, 32, 4), 255, np.uint8)
        return bundle.write(tmp, name="Barrel", prefix="mod", positions=P, normals=N, uvs=UV,
                            triangles=T, texture_rgba=tex, footprint_m=(4, 3), **kw)

    def test_a_prop_goes_to_the_objects_folder_with_no_building_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            desc = self._write(tmp, kind="PROP")
        self.assertEqual(desc["kind"], "PROP")
        names = [os.path.basename(f) for f in desc["files"]]
        self.assertIn(os.path.join("art", "mod", "objects", "barrel", "barrel.gr2"), desc["files"])
        self.assertNotIn("barrel_death.gr2", names)             # a prop does not sink when killed
        self.assertNotIn("DeadReplacement", desc["unit"])       # and leaves no rubble
        self.assertNotIn("PlacementFile", desc["unit"])
        self.assertIn("AnimFile", desc["unit"])
        self.assertIn("ObstructionRadiusX", desc["unit"])

    def test_the_folder_can_be_chosen_for_a_treasure(self):
        with tempfile.TemporaryDirectory() as tmp:
            desc = self._write(tmp, kind="PROP", folder="nuggets")
        self.assertTrue(desc["unit"]["AnimFile"].startswith("mod\\nuggets\\barrel"))

    def test_a_building_is_unchanged_and_still_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            desc = self._write(tmp)
        self.assertEqual(desc["kind"], "BUILDING")
        self.assertIn("DeadReplacement", desc["unit"])
        self.assertIn(os.path.join("art", "mod", "buildings", "barrel", "barrel_death.gr2"),
                      desc["files"])

    def test_an_unknown_kind_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self._write(tmp, kind="TREASURE")

    def test_the_prop_readme_does_not_talk_about_building_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, kind="PROP")
            text = open(os.path.join(tmp, "README.txt"), encoding="utf-8").read()
        self.assertIn("map object", text)
        self.assertNotIn("construction stages", text)
        self.assertNotIn("<Train>", text)


@unittest.skipIf(np is None, "needs numpy")
class ReadBack(unittest.TestCase):
    """aoe3game/gr2_mesh.py: a model written here comes back as it went."""

    def setUp(self):
        from aoe3game import gr2_mesh
        self.gr2_mesh = gr2_mesh
        self.P, self.N, self.UV, self.T = box()
        self.data = gr2_write.static_model("Crate", self.P, self.N, self.UV, self.T, texture="t.ddt",
                                           bump="t_b.ddt", bones=[("bone_smoke", (0.5, -1.0, 2.0))])

    def test_positions_uvs_and_triangles_come_back(self):
        m = self.gr2_mesh.read(self.data)
        part = m["meshes"][0]
        key = lambda rows: sorted(tuple(round(float(v), 3) for v in r) for r in rows)   # noqa: E731
        self.assertEqual(key(part["positions"]), key(self.P))
        self.assertEqual(key(part["uvs"]), key(self.UV))
        self.assertEqual(len(part["triangles"]), len(self.T))
        self.assertEqual(m["skipped"], [])

    def test_the_winding_faces_the_way_the_normals_do(self):
        part = self.gr2_mesh.read(self.data)["meshes"][0]
        p, t = part["positions"], part["triangles"]
        face = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
        self.assertTrue(((face * part["normals"][t[:, 0]]).sum(1) > 0).all())

    def test_a_socket_comes_back_where_it_was_put(self):
        bones = {name: at for name, _parent, at in self.gr2_mesh.read(self.data)["bones"]}
        self.assertEqual(tuple(round(v, 3) for v in bones["bone_smoke"]), (0.5, -1.0, 2.0))
        self.assertIn("bone_main", bones)

    def test_an_animation_has_no_mesh(self):
        anim = gr2_write.sink_animation("Crate", [], 2.0)
        self.assertEqual(self.gr2_mesh.read(anim)["meshes"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
