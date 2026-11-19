# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/hc_move.py on the tiny game folder of tests/test_hc_survey.py (plain Python): which files
move where, the stored texture names, the reference edits (plain and compiled anim files, home-city
files in both forms), the stage, and an install taken back out byte for byte. The Granny bridge is
replaced by a function that writes a model with the asked names.

    python -I tests\\test_hc_move.py
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from aoe3game import gr2_write  # noqa: E402
import hc_move as hm  # noqa: E402
import hc_survey as hs  # noqa: E402
import test_hc_survey as fixture  # noqa: E402
import xmbedit  # noqa: E402

TARGET = "Mod\\homecity"


def fake_rebake(src, dst, convert, renames):
    """The bridge's rename: the same model written again with the new names."""
    with open(src, "rb") as fh:
        names = hs.measure(fh.read())["textures"]
    swap = dict(renames)
    names = [swap.get(n, n) for n in names]
    with open(dst, "wb") as fh:
        fh.write(gr2_write.static_model("m", fixture.P, fixture.N, fixture.UV, fixture.T,
                                        texture=names[-1], bump=names[0]))
    return "#rebake\tok"


def tree_hashes(folder):
    out = {}
    for top, _dirs, files in os.walk(folder):
        for name in files:
            full = os.path.join(top, name)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, folder)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class MoveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.game = os.path.join(cls.tmp.name, "game")
        fixture.build(cls.game)
        cls.res = hs.survey(cls.game, TARGET)
        cls.plan = hm.plan_moves(cls.res, "Testland", TARGET, "A")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def stage(self, name, form="A", **kw):
        out = os.path.join(self.tmp.name, name)
        meta = hm.stage(self.game, "testland", TARGET, out, None, form=form, rebake=fake_rebake,
                        log=lambda *_: None, **kw)
        return out, meta

    def test_what_moves_where(self):
        m = self.plan["moves"]
        self.assertEqual(m["homecity\\test\\main.gr2"], "Mod\\homecity\\Testland\\main.gr2")
        self.assertEqual(m["homecity\\test\\shared.gr2"], "Mod\\homecity\\_shared\\shared.gr2")
        self.assertEqual(m["homecity\\test\\main.ddt"], "Mod\\homecity\\Testland\\main.ddt")
        self.assertEqual(m["homecity\\test\\sky.xml.xmb"], "Mod\\homecity\\Testland\\sky.xml.xmb")
        self.assertEqual(m["homecity\\test\\test_homecity.xml"],
                         "Mod\\homecity\\Testland\\test_homecity.xml")
        for k in ("units\\guy\\guy.gr2", "homecity\\test\\path.gr2", "homecity\\test\\unused.ddt"):
            self.assertNotIn(k, m)
        self.assertIn("homecity\\test\\unused.ddt", self.plan["left"])
        self.assertEqual(hm.plan_moves(self.res, "Testland", TARGET, "B")["moves"][
            "homecity\\test\\main.gr2"], "homecity\\Mod\\Testland\\main.gr2")
        with self.assertRaises(SystemExit):
            hm.plan_moves(self.res, "Nowhere", TARGET)

    def test_texture_names(self):
        row = next(r for r in self.res["files"] if r["key"] == "homecity\\test\\main.gr2")
        tex = {t["stem"]: t for t in row["texture_info"]}
        art, moves = self.res["art"], self.plan["moves"]
        new, _ = hm.new_texture_name(tex["main"]["stored"], tex["main"], moves, art, hm.DEFAULT_PREFIX)
        self.assertEqual(new, fixture.ART + "Mod\\homecity\\Testland\\main.tga")
        sky = next(r for r in self.res["files"] if r["key"] == "homecity\\test\\sky.gr2")
        flat = next(t for t in sky["texture_info"] if t["stem"] == "flat")
        self.assertEqual(hm.new_texture_name(flat["stored"], flat, moves, art, "")[0], None)
        # with the suffix: the .ddt itself is renamed, and the stored name says the same digits
        sp = hm.plan_moves(self.res, "Testland", TARGET, "A", suffix=True, tex_refs={})
        self.assertEqual(sp["moves"]["homecity\\test\\main.ddt"],
                         "Mod\\homecity\\Testland\\main.(0,1,8,8).ddt")
        self.assertEqual(sp["moves"]["homecity\\test\\main_b.(6,0,9,8).ddt"],   # already has it
                         "Mod\\homecity\\Testland\\main_b.(6,0,9,8).ddt")
        new, _ = hm.new_texture_name(tex["main"]["stored"], tex["main"], sp["moves"], art,
                                     hm.DEFAULT_PREFIX, sp["suffixed"])
        self.assertEqual(new, fixture.ART + "Mod\\homecity\\Testland\\main.(0,1,8,8).tga")
        layout = hm.Layout({hs.norm(v) for v in sp["moves"].values()}, sp["moves"])
        self.assertTrue(hm.resolves_after(new, layout, art.exists))
        self.assertFalse(hm.resolves_after(tex["main"]["stored"], layout, art.exists))
        # a .ddt a home city's anim file names moves but keeps its name; one an anim file
        # outside the home cities names stays where it is
        kept = hm.plan_moves(self.res, "Testland", TARGET, "A", suffix=True,
                             tex_refs={"homecity\\test\\main.ddt": ["homecity\\test\\test_homecity.xml"]})
        self.assertEqual(kept["moves"]["homecity\\test\\main.ddt"], "Mod\\homecity\\Testland\\main.ddt")
        self.assertIn("homecity\\test\\main.ddt", dict(kept["unsuffixed"]))
        out = hm.plan_moves(self.res, "Testland", TARGET, "A", suffix=True,
                            tex_refs={"homecity\\test\\main.ddt": ["units\\guy\\guy_world.xml"]})
        self.assertNotIn("homecity\\test\\main.ddt", out["moves"])

    def test_reencoded_textures(self):
        art = self.res["art"]
        new = b"RTS3" + bytes((0, 1, 8, 3)) + b"\0" * 40
        path = os.path.join(self.tmp.name, "main_new.ddt")
        with open(path, "wb") as fh:
            fh.write(new)

        def entry(key, data=None):
            data = art.read(key) if data is None else data
            return {"sha256": hashlib.sha256(data).hexdigest(), "path": path, "digits": "0,1,8,3"}

        re = {"homecity\\test\\main.ddt": entry("homecity\\test\\main.ddt"),
              "homecity\\test\\main_b.(6,0,9,8).ddt": entry("homecity\\test\\main_b.(6,0,9,8).ddt"),
              "homecity\\test\\sky.ddt": entry("homecity\\test\\sky.ddt", b"other bytes")}
        sp = hm.plan_moves(self.res, "Testland", TARGET, "A", suffix=True, tex_refs={}, reencoded=re)
        # the suffix states the re-encoded header, not the old one
        self.assertEqual(sp["moves"]["homecity\\test\\main.ddt"],
                         "Mod\\homecity\\Testland\\main.(0,1,8,3).ddt")
        self.assertEqual(list(sp["reencoded"]), ["homecity\\test\\main.ddt"])
        why = dict(sp["not_reencoded"])
        self.assertIn("suffix", why["homecity\\test\\main_b.(6,0,9,8).ddt"])
        self.assertIn("changed", why["homecity\\test\\sky.ddt"])
        out, meta = self.stage("stageR", suffix=True, reencoded=re)
        with open(os.path.join(out, "files", "art", "Mod", "homecity", "Testland", "main.(0,1,8,3).ddt"),
                  "rb") as fh:
            self.assertEqual(fh.read(), new)
        self.assertEqual(meta["reencoded"], {"art\\homecity\\test\\main.ddt": "0,1,8,3"})
        with open(os.path.join(out, "files", "art", "Mod", "homecity", "Testland", "main.gr2"), "rb") as fh:
            self.assertIn(fixture.ART + "Mod\\homecity\\Testland\\main.(0,1,8,3).tga",
                          hs.measure(fh.read())["textures"])

    def test_tables_and_the_tree(self):
        tables = hm.plan_moves(self.res, hm.TABLES, TARGET)
        self.assertEqual(tables["moves"], {})                # the fixture's tables name no model

    def test_edits(self):
        text = "<a>\n  <file>X\\y</file> <file>X\\y</file>\n</a>"
        self.assertEqual(hm.edit_lines(text, [(2, "X\\y", "Z")]), "<a>\n  <file>Z</file> <file>X\\y</file>\n</a>")
        with self.assertRaises(ValueError):
            hm.edit_lines(text, [(1, "X\\y", "Z")])
        self.assertEqual(hm._value("homecity\\t\\m", "Mod\\homecity\\T\\m.gr2"), "Mod\\homecity\\T\\m")
        self.assertEqual(hm.hc_value({"resolved": "homecity"}, "Mod\\homecity\\T\\a.xml"),
                         "..\\Mod\\homecity\\T\\a.xml")
        self.assertEqual(hm.hc_value({"resolved": "homecity"}, "homecity\\Mod\\T\\a.xml"),
                         "Mod\\T\\a.xml")

    def test_stage_form_a(self):
        out, meta = self.stage("stageA")
        files = os.path.join(out, "files")
        with open(os.path.join(files, "data", "homecitytestland.xml"), encoding="utf-8") as fh:
            hc = fh.read().split("\n")
        self.assertIn("<visual>..\\Mod\\homecity\\Testland\\test_homecity.xml</visual>", hc[3])
        self.assertIn("..\\Mod\\homecity\\Testland\\market.xml", hc[10])
        self.assertTrue(os.path.exists(os.path.join(files, "Campaign", "Act 1", "homecitytestland.xml")))
        with open(os.path.join(files, "art", "homecity", "other", "other_homecity.xml"), encoding="utf-8") as fh:
            self.assertIn("Mod\\homecity\\_shared\\shared", fh.read())
        with open(os.path.join(files, "art", "Mod", "homecity", "Testland", "sky.xml.xmb"), "rb") as fh:
            twin = xmbedit.to_xml(*xmbedit.parse(xmbedit.decode(fh.read())))
        self.assertIn("Mod\\homecity\\Testland\\sky", twin)
        # only the twin the game reads (the newer) moves; the older one stays where it was
        self.assertFalse(os.path.exists(os.path.join(files, "art", "Mod", "homecity", "Testland", "sky.xml")))
        self.assertIn("art\\homecity\\test\\sky.xml.xmb", meta["moves"])
        self.assertNotIn("art\\homecity\\test\\sky.xml", meta["moves"])
        with open(os.path.join(files, "art", "Mod", "homecity", "Testland", "main.gr2"), "rb") as fh:
            self.assertIn(fixture.ART + "Mod\\homecity\\Testland\\main.tga", hs.measure(fh.read())["textures"])
        with open(os.path.join(out, "moved-files.txt"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertIn("art\\homecity\\test\\main.gr2 -> art\\Mod\\homecity\\Testland\\main.gr2", lines)
        self.assertEqual(len(lines), len(meta["moves"]))
        self.assertTrue(os.path.exists(os.path.join(out, "originals.zip")))
        with self.assertRaises(SystemExit):
            self.stage("stageA")                         # never over an old stage

    def test_stage_form_b(self):
        out, _meta = self.stage("stageB", form="B")
        with open(os.path.join(out, "files", "data", "homecitytestland.xml"), encoding="utf-8") as fh:
            self.assertIn("<visual>Mod\\Testland\\test_homecity.xml</visual>", fh.read())

    def test_install_and_undo(self):
        bed = os.path.join(self.tmp.name, "bed")
        shutil.copytree(self.game, bed)
        before = tree_hashes(bed)
        out, meta = self.stage("stageI")
        hm.install(bed, out, log=lambda *_: None)
        self.assertTrue(os.path.exists(os.path.join(bed, "art", "Mod", "homecity", "Testland", "main.gr2")))
        self.assertFalse(os.path.exists(os.path.join(bed, "art", "homecity", "test", "main.gr2")))
        self.assertTrue(os.path.exists(os.path.join(bed, "art", "homecity", "test", "unused.ddt")))
        with self.assertRaises(SystemExit):
            hm.install(bed, out, log=lambda *_: None)     # its originals are gone now
        hm.undo(bed, log=lambda *_: None)
        self.assertEqual(tree_hashes(bed), before)
        self.assertFalse(os.path.exists(os.path.join(bed, "art", "Mod")))
        with self.assertRaises(SystemExit):
            hm.undo(bed, log=lambda *_: None)

    def test_refuses_steam(self):
        with self.assertRaises(SystemExit):
            hm.refuse_steam(r"C:\Program Files (x86)\Steam\steamapps\common\Age Of Empires 3")


if __name__ == "__main__":
    unittest.main()
