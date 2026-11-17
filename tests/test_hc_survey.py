# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/hc_survey.py on a tiny game folder written here (plain Python): two home cities, their
anim files (one with a compiled twin), models written by gr2_write in the stock basis, in 3ds Max
inches and with a root scaled by 100, textures with and without the (u,a,f,m) suffix, a model
shared by both cities, one used by a unit outside them, and the plan for one city.

    python -I tests\\test_hc_survey.py
"""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_write  # noqa: E402
import hc_survey as hs  # noqa: E402
import xmbedit  # noqa: E402

P = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
T = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
N = [(0, 0, 1)] * 4
UV = [(0, 0), (1, 0), (0, 1), (1, 1)]
ART = "C:\\Games\\Age of Empires 3\\art\\"


def model(texture, bump, upm=gr2_write.STOCK_BASIS["units_per_meter"], root_scale=None):
    data = bytearray(gr2_write.static_model("m", P, N, UV, T, texture=texture, bump=bump,
                                            units_per_meter=upm))
    if root_scale:
        doc = gr2.load(bytes(data))
        bone = doc.root().get("Skeletons")[0].get("Bones")[0]
        at = doc.c.sections[bone.at[0]].data_offset + bone.at[1] + bone.type.member("Transform").offset
        struct.pack_into("<I3f4f9f", data, at, 7, 0, 0, 0, 0, 0, 0, 1,
                         root_scale, 0, 0, 0, root_scale, 0, 0, 0, root_scale)
        struct.pack_into("<I", data, 0x28, gr2.file_crc(data))
    return bytes(data)


def ddt(usage, alpha, fmt, mips):
    return b"RTS3" + bytes((usage, alpha, fmt, mips)) + struct.pack("<II", 4, 4) + b"\0" * 16


HC_A = """<?xml version="1.0" encoding="utf-8"?>
<homecity>
\t<civ>Testland</civ>
\t<visual>test\\test_homecity.xml</visual>
\t<!-- <visual>test\\old_homecity.xml</visual> -->
\t<backgroundvisual>test\\sky.xml</backgroundvisual>
\t<pathdata>test\\path.gr2</pathdata>
\t<building>
\t\t<name>Market</name>
\t\t<visual>
\t\t\t<file>test\\market.xml</file>
\t\t\t<bone>bone_market</bone>
\t\t</visual>
\t\t<props><prop><visual>units\\guy\\guy.xml</visual></prop></props>
\t</building>
</homecity>
"""
HC_B = """<homecity><civ>Otherland</civ>
<visual>other\\other_homecity.xml</visual>
</homecity>
"""
TOP = """<animfile>
\t<component>main<assetreference type="GrannyModel">
\t\t<file>Homecity\\test\\main</file>
\t</assetreference></component>
\t<attachment>guard<include>units\\guy\\guy.xml</include></attachment>
\t<anim>Idle<assetreference type="GrannyAnim"><file>homecity\\test\\wave</file></assetreference></anim>
</animfile>
"""
SKY_PLAIN = """<animfile><component>sky<assetreference type="GrannyModel">
<file>homecity\\test\\old_sky</file></assetreference></component></animfile>
"""
SKY_TWIN = """<animfile><component>sky<assetreference type="GrannyModel">
<file>homecity\\test\\sky</file></assetreference></component></animfile>
"""
MARKET = """<animfile><component>m<assetreference type="GrannyModel">
<file>homecity\\test\\shared</file></assetreference></component>
<component>s<assetreference type="GrannyModel"><file>homecity\\test\\scaled</file></assetreference>
</component></animfile>
"""
OTHER = """<animfile><component>m<assetreference type="GrannyModel">
<file>homecity\\test\\shared</file></assetreference></component></animfile>
"""
GUY = """<animfile><component>g<assetreference type="GrannyModel">
<file>units\\guy\\guy</file></assetreference></component></animfile>
"""
GUY_WORLD = """<animfile><component>g<assetreference type="GrannyModel">
<file>units\\guy\\guy</file></assetreference></component></animfile>
"""


def put(folder, rel, data):
    path = os.path.join(folder, *rel.split("\\"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data.encode("utf-8") if isinstance(data, str) else data)


def build(g):
    put(g, "data\\homecitytestland.xml", HC_A)
    put(g, "data\\homecityotherland.xml", HC_B)
    put(g, "data\\protoy.xml", "<proto/>")
    put(g, "Campaign\\Act 1\\homecitytestland.xml", HC_A)
    a = "art\\homecity\\test\\"
    put(g, a + "test_homecity.xml", TOP)
    put(g, a + "sky.xml", SKY_PLAIN)
    put(g, a + "sky.xml.xmb", xmbedit.encode(*xmbedit.from_xml(SKY_TWIN.encode())))
    plain = os.path.join(g, "art", "homecity", "test", "sky.xml")
    os.utime(plain, (1_500_000_000, 1_500_000_000))   # the compiled twin is the newer: it is read
    put(g, a + "market.xml", MARKET)
    put(g, a + "main.gr2", model(ART + "homecity\\test\\main.tga",
                                 ART + "homecity\\test\\main_b.(6,0,9,8).tga", upm=39.370079))
    put(g, a + "main.ddt", ddt(0, 1, 8, 8))
    put(g, a + "main_b.(6,0,9,8).ddt", ddt(6, 0, 9, 8))
    put(g, a + "main.(0,1,8,8).tga", b"tga")
    put(g, a + "sky.gr2", model("D:\\a\\art\\homecity\\test\\sky.jpg", "D:\\x\\flat.ddt"))
    put(g, a + "sky.ddt", ddt(0, 4, 8, 8))
    put(g, a + "shared.gr2", model(ART + "homecity\\test\\shared.png", "nowhere.tga"))
    put(g, a + "scaled.gr2", model(ART + "homecity\\test\\main.tga", "x.tga", root_scale=100.0))
    put(g, a + "path.gr2", model("p.ddt", "p.ddt"))
    put(g, a + "unused.ddt", ddt(0, 0, 8, 1))
    put(g, "art\\homecity\\other\\other_homecity.xml", OTHER)
    put(g, "art\\units\\guy\\guy.xml", GUY)
    put(g, "art\\units\\guy\\guy.gr2", model("guy.ddt", "guy_b.ddt", upm=1000.0))
    put(g, "art\\units\\guy\\guy_world.xml", GUY_WORLD)


class ScanTest(unittest.TestCase):
    def test_paths_text_lines_and_comments(self):
        got = [([t for t, _a in s], v, n) for s, v, n in hs.scan(HC_A)]
        self.assertIn((["homecity", "visual"], "test\\test_homecity.xml", 4), got)
        self.assertNotIn("test\\old_homecity.xml", [v for _s, v, _n in got])
        self.assertIn((["homecity", "building", "visual", "file"], "test\\market.xml", 11), got)

    def test_a_file_the_parser_would_refuse(self):
        text = "<a>\n<b>x</b>\n<c><d>y</d>\n</a>"          # <c> never closed
        got = [([t for t, _a in s], v, n) for s, v, n in hs.scan(text)]
        self.assertEqual(got, [(["a", "b"], "x", 2), (["a", "c", "d"], "y", 3)])

    def test_home_city_references_and_their_base(self):
        info = hs.hc_refs(HC_A)
        self.assertEqual(info["civ"], "Testland")
        bases = {r["value"]: (r["tag"], r["base"], r["line"]) for r in info["refs"]}
        self.assertEqual(bases["test\\test_homecity.xml"], ("visual", "homecity", 4))
        self.assertEqual(bases["test\\market.xml"], ("visual/file", "homecity", 11))
        self.assertEqual(bases["test\\path.gr2"], ("pathdata", "homecity", 7))
        self.assertEqual(bases["units\\guy\\guy.xml"][1], "art")

    def test_anim_references(self):
        kinds = sorted((r["kind"], r["value"]) for r in hs.anim_refs(TOP))
        self.assertEqual(kinds, [("anim", "homecity\\test\\wave"), ("include", "units\\guy\\guy.xml"),
                                 ("model", "Homecity\\test\\main")])

    def test_option_b(self):
        self.assertEqual(hs.option_b("Mod\\homecity"), "homecity\\Mod")
        self.assertEqual(hs.option_b("x\\y\\z"), "x\\y\\z")

    def test_paths(self):
        self.assertEqual(hs.join_key("homecity", "..\\Mod\\homecity\\x.xml"), "mod\\homecity\\x.xml")
        self.assertIsNone(hs.join_key("", "..\\x"))
        self.assertEqual(hs.model_key("Homecity\\T\\m"), "homecity\\t\\m.gr2")


class TextureTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(hs.split_texture(ART + "homecity\\x\\a.(0,1,8,8).tga"),
                         ("homecity\\x", "a", ".tga", "0,1,8,8"))
        self.assertEqual(hs.split_texture("J:\\aa\\b.jpg"), (None, "b", ".jpg", None))
        self.assertEqual(hs.split_texture("units\\c.ddt"), ("units", "c", ".ddt", None))

    def test_header_digits(self):
        self.assertEqual(hs.ddt_digits(ddt(6, 0, 9, 8)), "6,0,9,8")
        self.assertIsNone(hs.ddt_digits(b"DDS "))

    def test_need(self):
        t = lambda ext, suffix=None: {"ext": ext, "suffix": suffix}
        self.assertEqual(hs.texture_need([]), "none")
        self.assertEqual(hs.texture_need([t(".tga", "0,1,8,8")]), "ok")
        self.assertEqual(hs.texture_need([t(".tga"), t(".png")]), "needed")
        self.assertEqual(hs.texture_need([t(".png"), t(".ddt")]), "ask")

    def test_suffix_in_place(self):
        self.assertEqual(hs._with_suffix("D:\\a\\art\\x\\y.jpg", "0,4,8,8"), "D:\\a\\art\\x\\y.(0,4,8,8).tga")


class BasisTest(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(hs.world_fixes({"upm": 0.615157, "up": (0, 1, 0), "root_scale": 1}), [])
        self.assertEqual(hs.world_fixes({"upm": 39.37008, "up": (0, 0, 1)}), ["basis"])
        self.assertEqual(hs.world_fixes({"upm": 1000.0, "up": (0, 0, 1)}), ["upm1000"])
        self.assertEqual(hs.world_fixes({"upm": 0.615157, "up": (0, 1, 0), "root_scale": 100}),
                         ["bone100"])
        self.assertEqual(hs.world_fixes({"upm": 39.37008, "up": (0, 0, 1), "root_scale": 60}),
                         ["basis", "root_scaled"])
        self.assertEqual(hs.basis_of({}), "unknown")

    def test_stock_extent(self):
        self.assertAlmostEqual(hs.stock_extent({"size": [64, 1, 1], "upm": 39.370079}), 1.0, 2)
        self.assertAlmostEqual(hs.stock_extent({"size": [64, 1, 1], "upm": 1000.0}), 1.0, 2)


class SurveyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        build(cls.tmp.name)
        cls.res = hs.survey(cls.tmp.name, "Mod\\homecity")
        cls.rows = {r["key"]: r for r in cls.res["files"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_home_city_files(self):
        labels = sorted(h["label"] for h in self.res["homecities"])
        self.assertEqual(labels, ["Otherland", "Testland", "Testland [Campaign\\Act 1]"])

    def test_what_is_reached(self):
        r = self.rows
        self.assertEqual(r["homecity\\test\\main.gr2"]["status"], "mod")
        self.assertEqual(r["homecity\\test\\wave.gr2"]["status"], "missing")
        self.assertEqual(r["homecity\\test\\wave.gr2"]["kind"], "anim")
        self.assertEqual(r["homecity\\test\\path.gr2"]["kind"], "pathdata")
        # the compiled twin wins: its model is reached, the plain file's is not followed alone
        self.assertIn("homecity\\test\\sky.gr2", r)
        self.assertEqual(r["homecity\\test\\sky.gr2"]["lines"][0][0], "homecity\\test\\sky.xml.xmb")

    def test_measures(self):
        m = self.rows["homecity\\test\\main.gr2"]
        self.assertEqual(m["basis"], "max_inches")
        self.assertEqual(m["world_fix"], ["basis"])
        self.assertEqual(m["texture_fix"], "needed")
        tex = {t["stem"]: t for t in m["texture_info"]}
        self.assertEqual(tex["main"]["header"], "0,1,8,8")
        self.assertEqual(tex["main"]["usual"], "colour")
        self.assertEqual(tex["main"]["sources"], ["main.(0,1,8,8).tga"])
        self.assertEqual(tex["main_b"]["suffix"], "6,0,9,8")
        self.assertEqual(tex["main_b"]["header"], "6,0,9,8")
        self.assertEqual(self.rows["homecity\\test\\scaled.gr2"]["world_fix"], ["bone100"])
        self.assertEqual(self.rows["homecity\\test\\scaled.gr2"]["root_scale"], 100.0)
        sky = self.rows["homecity\\test\\sky.gr2"]
        self.assertEqual(sky["world_fix"], [])
        how = {t["stem"]: t["how"] for t in sky["texture_info"]}
        self.assertEqual(how, {"sky": "art path", "flat": "missing"})

    def test_shared_and_used_elsewhere(self):
        shared = self.rows["homecity\\test\\shared.gr2"]
        self.assertTrue(shared["shared"])
        self.assertTrue(shared["move"].startswith("ask"))
        guy = self.rows["units\\guy\\guy.gr2"]
        self.assertEqual(guy["world_refs"], ["units\\guy\\guy_world.xml"])
        self.assertTrue(guy["move"].startswith("no"))
        self.assertEqual(guy["world_fix"], ["upm1000"])
        self.assertEqual(self.rows["homecity\\test\\main.gr2"]["move"], "yes")

    def test_uses(self):
        r = self.rows
        # the market (a building's <visual>) names shared and scaled; Otherland's scene names shared
        self.assertEqual(r["homecity\\test\\scaled.gr2"]["uses"], ["building"])
        self.assertEqual(r["homecity\\test\\shared.gr2"]["uses"], ["building", "other"])
        self.assertEqual(r["homecity\\test\\main.gr2"]["uses"], ["other"])
        self.assertEqual(r["homecity\\test\\path.gr2"]["uses"], ["other"])
        self.assertIn("outside", r["units\\guy\\guy.gr2"]["uses"])
        uses = self.res["texture_uses"]
        # main.ddt: the scene's main.gr2 and the market's scaled.gr2 both store it
        self.assertEqual(hs.use_label(uses["homecity\\test\\main.ddt"]["uses"]), "shared")
        self.assertEqual(hs.use_label({"building"}), "building")
        self.assertEqual(hs.use_label({"other", "outside"}), "other")
        self.assertEqual(hs.use_label(set()), "")
        sky = [t for t in self.res["textures"] if t["resolved"] == "homecity\\test\\sky.ddt"][0]
        self.assertEqual((sky["use"], sky["width"], sky["height"], sky["bytes"]), ("other", 4, 4, 32))

    def test_use_of_a_reference(self):
        uses = {r["value"]: r["use"] for r in hs.hc_refs(HC_A)["refs"]}
        self.assertEqual(uses["test\\market.xml"], "building")
        self.assertEqual(uses["test\\test_homecity.xml"], "visual")
        self.assertEqual(uses["test\\sky.xml"], "backgroundvisual")
        self.assertEqual(uses["units\\guy\\guy.xml"], "prop")

    def test_stock_only(self):
        art = hs.Art(os.path.join(self.tmp.name, "art"), loose=False)
        self.assertEqual(art.loose, {})
        self.assertIsNone(art.size("homecity\\test\\main.ddt"))

    def test_reports_and_plan(self):
        out = os.path.join(self.tmp.name, "_report")
        hs.write_reports(self.res, out)
        for name in ("models.csv", "textures.csv", "refs.csv", "summary.md", "report.json"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        text = hs.plan(self.res, "testland")
        self.assertIn("`Mod\\homecity\\Testland\\main.gr2`", text)
        self.assertIn("main.(0,1,8,8).tga", text)
        self.assertIn("`data\\homecitytestland.xml` line 4 `<visual>`: `test\\test_homecity.xml` -> "
                      "A `..\\Mod\\homecity\\Testland\\test_homecity.xml` / B "
                      "`Mod\\Testland\\test_homecity.xml`", text)
        self.assertIn("line 3 (model): `Homecity\\test\\main` -> `Mod\\homecity\\Testland\\main`", text)
        self.assertIn("unused.ddt` (reached by nothing)", text)
        with self.assertRaises(SystemExit):
            hs.plan(self.res, "nowhere")


if __name__ == "__main__":
    unittest.main()
