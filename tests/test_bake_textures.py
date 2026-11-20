# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/bake_textures.py on a synthetic art folder (plain Python, no Granny runtime).

    python -I tests/test_bake_textures.py
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_write  # noqa: E402
import bake_textures as bt  # noqa: E402

P = [(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)]

ANIM = """<animfile>
\t<component>
\t\tLIVE
\t\t<assetreference type="GrannyModel">
\t\t\t<file>stock\\house</file> <!-- the stock house -->
\t\t\t<replacetexture>
\t\t\t\t<from>stock\\house_colour</from>
\t\t\t\t<to>mod\\post\\post</to>
\t\t\t</replacetexture>
\t\t\t<replacetexture><from>stock\\house_bump</from><to>mod\\post\\post_b</to></replacetexture>
\t\t\t<replacetexture><from>stock\\not_in_the_model</from><to>mod\\post\\post</to></replacetexture>
\t\t</assetreference>
\t\t<assetreference type="GrannyModel">
\t\t\t<file>stock\\house</file>
\t\t\t<replacetexture><from>stock\\house_colour</from><to>mod\\post\\missing</to></replacetexture>
\t\t</assetreference>
\t\t<!-- <replacetexture><from>a</from><to>b</to></replacetexture> left as a comment -->
\t</component>
</animfile>
"""


def house():
    return gr2_write.static_model("house", P, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                  [(0, 1, 2), (0, 2, 3)], texture=r"E:\src\Art\stock\house_colour.ddt",
                                  bump=r"E:\src\Art\stock\house_bump.ddt")


def put(root, rel, data):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


class Bake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.art = os.path.join(t, "art")
        put(self.art, r"stock\house.gr2", house())
        put(self.art, r"mod\post\post.ddt", b"RTS3")
        put(self.art, r"mod\post\post_b.ddt", b"RTS3")
        put(self.art, r"mod\post\post.xml", ANIM)
        put(self.art, r"mod\tower\tower.xml", ANIM)          # the same swaps again: one copy
        self.manifest = os.path.join(t, "m.tsv")
        put(t, "m.tsv", "mod\\post\\post.xml\tWoL\\buildings\\post\n"
                        "# comment\nmod\\tower\\tower.xml\tWoL\\buildings\\tower\n")
        self.out = os.path.join(t, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = bt.main(["--manifest", self.manifest, "--art", self.art, "--out", self.out, *extra])
        return code, buf.getvalue()

    def test_bake(self):
        code, text = self.run_tool()
        self.assertEqual(code, 0, text)
        clone = os.path.join(self.out, r"WoL\buildings\post\post_house.gr2")
        with open(clone, "rb") as fh:
            names = [t.get("FromFileName") for t in gr2.load(fh.read()).root().get("Textures")]
        self.assertEqual(sorted(names), [r"C:\art\mod\post\post.ddt", r"C:\art\mod\post\post_b.ddt"])
        self.assertFalse(os.path.exists(os.path.join(self.out, r"WoL\buildings\tower")))   # deduplicated
        with open(os.path.join(self.out, r"mod\post\post.xml"), encoding="utf-8") as fh:
            xml = fh.read()
        self.assertNotIn("<replacetexture><from>stock", xml.replace("<!-- <replacetexture>", ""))
        self.assertEqual(xml.count("<replacetexture>"), 1)                     # only in the comment
        self.assertIn("<file>WoL\\buildings\\post\\post_house</file> <!-- the stock house -->", xml)
        self.assertIn("<file>stock\\house</file>\n\t\t</assetreference>", xml)  # a dead swap only
        with open(os.path.join(self.out, r"mod\tower\tower.xml"), encoding="utf-8") as fh:
            self.assertIn("WoL\\buildings\\post\\post_house", fh.read())       # the first copy
        with open(os.path.join(self.out, "clones.tsv"), encoding="utf-8") as fh:
            rows = fh.read().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn("mod\\post\\post.xml; mod\\tower\\tower.xml", rows[1])
        with open(os.path.join(self.out, "bake.txt"), encoding="utf-8") as fh:
            notes = fh.read()
        self.assertIn("not_in_the_model", notes)
        self.assertIn("missing", notes)

    def test_building_names(self):
        self.assertEqual(bt.building_name("arsenal", "west_arsenal_age2_damaged", "java_arsenal_4"), "arsenal_4_dmg")
        self.assertEqual(bt.building_name("arsenal", "west_arsenal_age2", "java_arsenal"), "arsenal_2")
        self.assertEqual(bt.building_name("post", "jesuit_house_07_deathmodel", "post"), "post_death")
        self.assertEqual(bt.building_name("tc", "lp_tc_age4", "tc_4"), "tc_4_lp")
        self.assertEqual(bt.building_name("tc", "east_tc_age2_con", "tc_2"), "tc_2_con")
        code, text = self.run_tool("--building-names", r"^wol\\buildings\\")
        self.assertEqual(code, 0, text)
        self.assertTrue(os.path.exists(os.path.join(self.out, r"WoL\buildings\post\post.gr2")))

    def test_dry_run_writes_nothing(self):
        code, text = self.run_tool("--dry-run")
        self.assertEqual(code, 0, text)
        self.assertIn("1 copies", text)
        self.assertFalse(os.path.exists(self.out))

    def test_a_name_the_art_holds_is_not_reused(self):
        put(self.art, r"WoL\buildings\post\post_house.gr2", b"other")
        code, text = self.run_tool()
        self.assertEqual(code, 0, text)
        self.assertTrue(os.path.exists(os.path.join(self.out, r"WoL\buildings\post\post_house_2.gr2")))

    def test_refusals(self):
        code, _ = self.run_tool("--out", os.path.join(self.art, "x"))         # last --out wins
        self.assertEqual(code, 1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(bt.main(["--manifest", self.manifest]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
