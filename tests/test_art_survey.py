# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/art_survey.py on synthetic files (no game data). Plain Python:

    python -I tests/test_art_survey.py
"""
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import art_survey  # noqa: E402
import xmbedit  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import gr2_write  # noqa: E402
from core import profile  # noqa: E402

ANIM = b"""<?xml version="1.0" encoding="utf-8"?>
<animfile>
  <definebone>bone_flag</definebone>
  <attachment>
    <component>
      <assetreference type="GrannyModel"><file>units\\foo\\foo.gr2</file></assetreference>
    </component>
  </attachment>
  <anim>Idle
    <assetreference type="GrannyAnim"><file>units\\shared\\idle.gr2</file></assetreference>
  </anim>
  <logic type="Variation"><component>Default</component></logic>
</animfile>
"""

BUILDING = b"""<animfile><anim>Bored<assetreference type="GrannyModel"><file>buildings\\bar\\bar.gr2</file>
</assetreference></anim><attachpoint name="hotspot_flag"/></animfile>"""


def ddt(width, height, fmt=1, alpha=8):
    return b"RTS3" + bytes([0, alpha, fmt, 5]) + struct.pack("<II", width, height) + b"\0" * 32


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def make_bar(path, files):
    """A minimal legacy archive in the layout tools/bar.py reads."""
    head = bytearray(0x124)
    head[:4] = b"ESPN"
    body = b""
    entries = []
    for name, data in files:
        entries.append((name, 0x124 + len(body), len(data)))
        body += data
    table = struct.pack("<I", 4) + "Art\\".encode("utf-16-le") + struct.pack("<I", len(entries))
    for name, off, size in entries:
        table += struct.pack("<III", off, size, size) + b"\0" * 16
        table += struct.pack("<I", len(name)) + name.encode("utf-16-le")
    struct.pack_into("<II", head, 0x118, len(entries), 0x124 + len(body))
    write(path, bytes(head) + body + table)


class FootprintClassTest(unittest.TestCase):
    def test_model_size_wins_over_an_odd_class(self):
        def cls(count, ratio, side):
            return {"count": count, "obstruction_over_half_side": {"median": ratio},
                    "side_units": {"median": side}}
        pr = profile.Profile({"classes": {"4x4": cls(60, 0.72, 5.5), "6x6": cls(50, 0.82, 7.3),
                                          "8x8": cls(200, 0.9, 8.8), "6x8": cls(11, 0.57, 14.0),
                                          "6x4": cls(5, 0.8, 7.0)}})
        upm = profile.UNITS_PER_METER
        self.assertEqual(pr.footprint_class(9.9, 8.8), "4x4")
        self.assertEqual(pr.footprint_class(11.9, 12.6), "6x6")     # not the 5-building 6x4
        self.assertEqual(pr.footprint_class(14.6, 14.6), "8x8")
        self.assertEqual(pr.footprint_class(44.5, 23.6), "8x8")     # not the long-wall 6x8
        # without model sizes: the old rule, by the obstruction side
        old = profile.Profile({"classes": {"8x8": {"count": 5, "obstruction_over_half_side": {"median": 0.9}}}})
        self.assertEqual(old.footprint_class(14.6 * upm / upm, 14.6), "8x8")


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.base = os.path.join(t, "base")
        self.mod = os.path.join(t, "mod")
        write(os.path.join(self.base, "art", "units", "shared", "idle.gr2"), b"GR2FAKE" * 4)
        make_bar(os.path.join(self.base, "art", "art.bar"),
                 [("units\\stock\\stock.xml", BUILDING), ("units\\stock\\stock.ddt", ddt(1024, 1024))])
        write(os.path.join(self.mod, "art", "units", "foo", "foo.xml"), ANIM)
        write(os.path.join(self.mod, "art", "units", "foo", "foo.gr2"), b"GR2FAKE" * 4)
        write(os.path.join(self.mod, "art", "units", "foo", "foo.ddt"), ddt(512, 256))
        elems, attrs, root = xmbedit.from_xml(BUILDING)
        xmb = xmbedit.wrap(xmbedit.encode(elems, attrs, root), True)
        write(os.path.join(self.mod, "art", "buildings", "bar", "bar.xml.xmb"), xmb)
        write(os.path.join(self.mod, "art", "buildings", "bar", "broken.xml"), b"<animfile><oops></animfile>")

    def tearDown(self):
        self.tmp.cleanup()

    def test_base_with_bar(self):
        rep = art_survey.survey([self.base], use_bar=True)
        self.assertEqual(rep["counts"], {"model": 1, "texture": 1, "anim": 1})
        tex = next(iter(rep["files"]["texture"].values()))
        self.assertEqual((tex["width"], tex["height"], tex["magic"]), (1024, 1024, "RTS3"))
        self.assertIn(("hotspot_flag", 1), [tuple(x) for x in rep["attach_points"]])

    def test_mod_against_reference(self):
        out = os.path.join(self.tmp.name, "out")
        self.assertEqual(art_survey.main([self.base, "--bar", "--out", out + "_base"]), 0)
        code = art_survey.main([self.mod, "--out", out, "--reference", os.path.join(out + "_base", "report.json"),
                                "--label", "TestMod"])
        self.assertEqual(code, 0)
        with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["label"], "TestMod")
        self.assertEqual(rep["counts"]["anim"], 2)               # the XML and the compressed XMB
        self.assertEqual(len(rep["errors"]), 1)                  # broken.xml is reported, not fatal
        foo = next(v for k, v in rep["per_anim"].items() if k.endswith("foo.xml"))
        self.assertEqual((foo["own"], foo["reference"], foo["unresolved"]), (1, 1, 0))
        self.assertEqual(foo["category"], "units")
        bar_anim = next(v for k, v in rep["per_anim"].items() if k.endswith("bar.xml.xmb"))
        self.assertEqual(bar_anim["unresolved"], 1)              # bar.gr2 exists nowhere
        self.assertEqual(rep["anim_categories"], {"units": 1, "buildings": 1})
        self.assertIn(["Idle", 1], rep["anim_names"])
        self.assertIn(["bone_flag", 1], rep["attach_points"])
        self.assertIn(["Variation", 1], rep["logic_types"])
        tex = next(iter(rep["files"]["texture"].values()))
        self.assertEqual((tex["width"], tex["height"]), (512, 256))
        with open(os.path.join(out, "summary.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("| only their own files | 0 |", md)
        self.assertIn("| both | 1 |", md)

    def test_usage_without_out(self):
        self.assertEqual(art_survey.main([self.mod]), 2)

    def test_paths_and_categories(self):
        self.assertEqual(art_survey.norm(r"Art\Mod\x\y.xml.xmb"), r"mod\x\y.xml")
        known = {r"mod\buildings\a\a.gr2", r"buildings\b.xml"}
        self.assertEqual(art_survey.resolve(r"Mod\Buildings\A\A", known), r"mod\buildings\a\a.gr2")
        self.assertEqual(art_survey.resolve("buildings/b.xml.xmb", known), r"buildings\b.xml")
        self.assertIsNone(art_survey.resolve(r"buildings\c", known))
        self.assertEqual(art_survey.category(r"art\Mod\buildings\x\x.xml"), "buildings")
        self.assertEqual(art_survey.category(r"art\units\x\x.xml"), "units")
        self.assertEqual(art_survey.category(r"art\x.xml"), "(other)")

    def test_buildings_joined_and_profiled(self):
        """A mod building: its proto, an anim file naming the model without extension, a real
        (uncompressed) model written by the game exporter, and the profile measured from it."""
        t = self.tmp.name
        game = os.path.join(t, "game")
        size, h = 8.0, 6.0
        P = [(-size / 2, -size / 2, 0), (size / 2, -size / 2, 0), (size / 2, size / 2, h), (-size / 2, size / 2, h)]
        model = gr2_write.static_model("tower", P, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                       [(0, 1, 2), (0, 2, 3)], texture=r"D:\x\art\Mod\buildings\tower\tower.ddt",
                                       bump="b", bones=[("bone_flag_civ", (0, 0, h))])
        write(os.path.join(game, "art", "Mod", "buildings", "tower", "tower.gr2"), model)
        write(os.path.join(game, "art", "Mod", "buildings", "tower", "tower.ddt"), ddt(256, 256, 8, 1))
        anim = (b'<animfile><submodel>s<component>c<assetreference type="GrannyModel">'
                rb'<file>buildings\constructions\4x4_stage1</file></assetreference></component></submodel>'
                rb'<component>m<assetreference type="GrannyModel"><file>Mod\buildings\tower\tower</file>'
                b'</assetreference><decal><width>6.00</width><height>6.00</height></decal></component></animfile>')
        write(os.path.join(game, "art", "Mod", "buildings", "tower", "tower.xml"), anim)
        units = "".join(rf'<Unit id="{i}" name="Tower{i}"><AnimFile>Mod\buildings\tower\tower.xml</AnimFile>'
                        f"<ObstructionRadiusX>2.0</ObstructionRadiusX><ObstructionRadiusZ>2.0</ObstructionRadiusZ>"
                        f"<DeadReplacement>BuildingRubble2x2</DeadReplacement><UnitType>Building</UnitType></Unit>"
                        for i in range(3))
        units += '<Unit id="9" name="Soldier"><AnimFile>x.xml</AnimFile><UnitType>Unit</UnitType></Unit>'
        write(os.path.join(game, "data", "protoy.xml"), f"<Proto>{units}</Proto>".encode())
        out = os.path.join(t, "out")
        prof = os.path.join(t, "prof", "buildings.json")
        self.assertEqual(art_survey.main([game, "--out", out, "--proto", os.path.join(game, "data", "protoy.xml"),
                                          "--profile-out", prof]), 0)
        with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(len(rep["buildings"]), 3)              # the soldier is not a building
        b = rep["buildings"][0]
        self.assertEqual((b["tris"], b["verts"]), (2, 4))
        self.assertEqual(b["stages"], ["4x4"])
        self.assertEqual(b["decal"], [6.0, 6.0])
        self.assertAlmostEqual(b["size_m"][0], size, places=3)
        self.assertEqual(b["texture"], {"size": "256x256", "format": 8, "alpha": 1})
        self.assertIn("bone_flag_civ", b["bones"])
        with open(prof, encoding="utf-8") as fh:
            p = json.load(fh)
        c = p["classes"]["4x4"]
        self.assertEqual(c["count"], 3)
        self.assertEqual(c["tris"]["median"], 2)
        side = size * art_survey.STOCK_UNITS_PER_METER
        self.assertAlmostEqual(c["obstruction_over_half_side"]["median"], round(2.0 / (side / 2), 3))
        self.assertEqual(c["stages"], [["4x4", 3]])
        self.assertNotIn("tower", json.dumps(p).lower())          # measurements only


if __name__ == "__main__":
    unittest.main(verbosity=2)
