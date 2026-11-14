# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/named_models.py on a tiny game folder written here: the list a contact sheet is made of,
and a proto name followed through protoy.xml and its anim file to the model it shows.

    python -I tests\\test_named_models.py
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import named_models as nm  # noqa: E402

PROTO = """<?xml version="1.0" encoding="utf-8"?>
<Proto version="4">
\t<Unit id="1" name="Soldier"><AnimFile>units\\soldier\\soldier.xml</AnimFile></Unit>
\t<Unit id="2" name="Ghost"><AnimFile>units\\ghost\\ghost.xml</AnimFile></Unit>
\t<Unit id="3" name="Nothing"><DBID>3</DBID></Unit>
\t<Unit id="4" name="Depot"><AnimFile>buildings\\depot\\depot.xml</AnimFile></Unit>
</Proto>
"""
ANIM = """<animfile>
\t<component>ModelComp<logic type="LowPoly">
\t\t<normal><assetreference type="GrannyModel"><file>units\\soldier\\soldier</file></assetreference></normal>
\t\t<lowpoly><assetreference type="GrannyModel"><file>units\\soldier\\lp_soldier</file></assetreference></lowpoly>
\t</logic></component>
\t<anim>Idle<component>ModelComp</component></anim>
</animfile>
"""
DEPOT = """<animfile>
\t<submodel>stage<component>s<assetreference type="GrannyModel"><file>buildings\\depot\\stage</file>
\t\t</assetreference></component></submodel>
\t<component>Depot<logic type="Culture">
\t\t<iroquois><logic type="BuildingCompletion"><p0><submodelref ref="stage"/></p0>
\t\t\t<p100><assetreference type="GrannyModel"><file>buildings\\depot\\typo</file></assetreference></p100>
\t\t</logic></iroquois>
\t\t<mediterranean><assetreference type="GrannyModel"><file>buildings\\depot\\med</file></assetreference>
\t\t</mediterranean>
\t\t<brazilian><assetreference type="GrannyModel"><file>buildings\\depot\\brazil</file></assetreference>
\t\t</brazilian>
\t</logic></component>
</animfile>
"""


def put(folder, rel, data):
    path = os.path.join(folder, *rel.split("\\"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data.encode("utf-8") if isinstance(data, str) else data)


class ListTest(unittest.TestCase):
    def test_a_list_is_captions_and_targets(self):
        text = ("\ufeff# a comment\n\nNow | ypThuggee\n  Later|units\\x\\y.gr2  \n"
                "Janissary\nTwo | bars | x\n")
        self.assertEqual(nm.parse_list(text), [("Now", "ypThuggee"), ("Later", "units\\x\\y.gr2"),
                                               ("Janissary", "Janissary"), ("Two", "bars | x")])
        with self.assertRaises(ValueError):
            nm.parse_list("caption |   \n")

    def test_what_a_target_is(self):
        self.assertEqual(nm.kind("ypThuggee"), "proto")
        self.assertEqual(nm.kind("units\\x\\x.xml"), "anim")
        self.assertEqual(nm.kind("units\\x\\x.xml.xmb"), "anim")
        self.assertEqual(nm.kind("units\\x\\x.gr2"), "model")
        self.assertEqual(nm.kind("units/x/x"), "model")


class GameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        g = self.tmp.name
        put(g, "data\\protoy.xml", PROTO)
        put(g, "art\\units\\soldier\\soldier.xml", ANIM)
        put(g, "art\\units\\soldier\\soldier.gr2", b"model")
        put(g, "art\\units\\soldier\\soldier.ddt", b"own")
        put(g, "art\\units\\soldier\\soldier_b.ddt", b"bump")
        put(g, "art\\units\\other\\soldier.ddt", b"elsewhere")
        put(g, "art\\units\\other\\shared.ddt", b"shared")
        put(g, "art\\buildings\\depot\\depot.xml", DEPOT)
        for name in ("stage", "med", "brazil"):
            put(g, f"art\\buildings\\depot\\{name}.gr2", b"model")
        self.game = nm.Game(g)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_proto_name_gives_its_full_detail_model(self):
        r = self.game.resolve("soldier")                       # names are not case-sensitive
        self.assertEqual(r["proto"], "Soldier")
        self.assertEqual(r["anim"], "units\\soldier\\soldier.xml")
        self.assertEqual(r["model"], "units\\soldier\\soldier.gr2")

    def test_an_anim_file_or_a_model_path(self):
        self.assertEqual(self.game.resolve("units\\soldier\\soldier.xml")["model"],
                         "units\\soldier\\soldier.gr2")
        self.assertEqual(self.game.resolve("art/units/Soldier/soldier")["model"],
                         "units\\soldier\\soldier.gr2")

    def test_a_missing_model_falls_to_the_next_finished_one(self):
        r = self.game.resolve("Depot")
        self.assertEqual(r["model"], "buildings\\depot\\med.gr2")          # not the construction stage
        self.assertEqual(r["skipped"], ["buildings\\depot\\typo.gr2"])

    def test_a_preferred_branch(self):
        self.assertEqual(self.game.resolve("Depot@brazilian")["model"], "buildings\\depot\\brazil.gr2")
        self.assertEqual(self.game.resolve("Depot", ["brazilian"])["model"], "buildings\\depot\\brazil.gr2")
        self.assertEqual(self.game.resolve("Depot@mediterranean", ["brazilian"])["model"],
                         "buildings\\depot\\med.gr2")
        self.assertEqual(nm.split_prefer("Depot@A, b"), ("Depot", ["a", "b"]))
        self.assertEqual(nm.split_prefer("units\\x@y\\z"), ("units\\x@y\\z", []))

    def test_why_an_entry_has_no_model(self):
        for target, short in (("Nobody", "no such proto"), ("Nothing", "no AnimFile"),
                              ("Ghost", "anim file missing"),
                              ("units\\soldier\\lp_soldier.gr2", "model file missing")):
            with self.assertRaises(nm.Missing) as cm:
                self.game.resolve(target)
            self.assertEqual(cm.exception.short, short)

    def test_a_texture_is_the_diffuse_of_the_models_own_folder_first(self):
        model = "units\\soldier\\soldier.gr2"
        self.assertEqual(self.game.texture(["C:\\src\\Art\\x\\soldier_b.ddt", "C:\\src\\soldier.tga"], model),
                         ("units\\soldier\\soldier.ddt", b"own"))
        self.assertEqual(self.game.texture(["shared.ddt"], model), ("units\\other\\shared.ddt", b"shared"))
        self.assertIsNone(self.game.texture(["missing.ddt", None], model))

    def test_an_anim_file_can_replace_a_texture(self):
        put(self.tmp.name, "art\\units\\soldier\\reskin.xml", ANIM.replace(
            "<file>units\\soldier\\soldier</file>",
            "<file>units\\soldier\\soldier</file><replacetexture><from>units\\soldier\\soldier</from>"
            "<to>units\\other\\shared</to></replacetexture>"))
        game = nm.Game(self.tmp.name)
        r = game.resolve("units\\soldier\\reskin.xml")
        self.assertEqual(r["replace"], {"units\\soldier\\soldier": "units\\other\\shared"})
        self.assertEqual(game.texture(["E:\\src\\Art\\units\\soldier\\soldier.ddt"], r["model"], r["replace"]),
                         ("units\\other\\shared.ddt", b"shared"))
        self.assertEqual(game.texture(["soldier.ddt"], r["model"], r["replace"])[0], "units\\other\\shared.ddt")
        self.assertEqual(game.texture(["soldier.ddt"], r["model"])[0], "units\\soldier\\soldier.ddt")
        self.assertEqual(nm.art_key("D:\\age3w\\art\\Units\\X\\y.ddt"), "units\\x\\y")


if __name__ == "__main__":
    unittest.main(verbosity=2)
