# SPDX-License-Identifier: GPL-3.0-or-later
"""aoe3game/uilayout.py: an interface layout read and written back byte for byte, and edits that
change only what they are about. Synthetic layouts only (nothing of a game). Plain Python.

    python -I tests/test_uilayout.py
"""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from aoe3game import uilayout as ul  # noqa: E402

# the oddities of hand-written game layouts, in one file
ODD = """<?xml version="1.0" encoding="utf-8"?>\r
\r
<layout>\r
\t<gadget name="panel" type="unitselectionpanel" size1024="342 629 700 768" z="105">\r
\t\t<gadget name="panel-tab" Type="button" size1024 ="674 641 701 696" foreground='ui\\ingame\\tab' hidden>\r
\t\t\t<command>uiShowCommandPanel()</command>\r
\t\t</gadget>\r
\t<!--gadget name="old" type="gadget" size1024="0 0 1 1"/-->\r
\t\t<gadget name="panel-name" type="formatText" textfont="StatText" textfontsize="12" size1024="400 640 560 660">\r
\t\t\t$$20104$$Name <icon="(16)(ui\\ingame\\stat_icon_attack)">\r
\t\t<gadget name="panel-hp" type="formatText" size1024="400 660 560 680"/>\r
\t</gadget>\r
\t</gadget>\r
\t<GADGET NAME="Second" size1024="0 0 10 10"><![CDATA[a < b]]></GADGET>\r
\t</gadget>\r
\t<gadget name="open" size1024="0 0 1 1">\r
</layout>\r
"""


class RoundTrip(unittest.TestCase):
    def test_odd_layout_is_written_back_byte_for_byte(self):
        for data in (ODD.encode("utf-8"), b"\xef\xbb\xbf" + ODD.encode("utf-8"),
                     b"\xff\xfe" + ODD.encode("utf-16-le"), ODD.encode("cp1252").replace(b"Name", b"N\xe9me")):
            self.assertEqual(ul.parse(data).data(), data)

    def test_the_tree_follows_the_games_reading(self):
        doc = ul.parse(ODD.encode())
        names = [g.get("name") for g in doc.gadgets()]
        self.assertEqual(names, ["panel", "panel-tab", "panel-name", "panel-hp", "Second", "open"])
        panel, tab, name, hp, second, still_open = doc.gadgets()
        self.assertEqual(tab.get("type"), "button")            # Type, any case
        self.assertEqual(tab.get("size1024"), "674 641 701 696")  # spaces around =
        self.assertEqual(tab.get("hidden"), "")                 # a bare attribute
        self.assertEqual(tab.get("FOREGROUND"), "ui\\ingame\\tab")
        self.assertIs(hp.parent, name)                          # panel-hp inside panel-name
        self.assertIs(name.parent, panel)
        self.assertEqual(name.close, "</gadget>")
        self.assertEqual(still_open.close, "")                  # closed by </layout>
        layout = doc.root.elements()[0]
        self.assertIn("stray", [c.kind for c in layout.children])   # a </gadget> that closes nothing
        self.assertEqual(ul.rect(panel), (342.0, 629.0, 700.0, 768.0))
        self.assertIn("$$20104$$Name", name.own_text())
        self.assertNotIn("old", names)                          # a commented gadget stays a comment

    def test_random_layouts_round_trip(self):
        rng = random.Random(4)
        pieces = ['<gadget name="g{n}" size1024="{a} {b} {c} {d}">', "</gadget>", '<gadget name="s{n}"/>',
                  "<!-- c{n} -->", "text {n}", "\r\n\t", "\n  ", "</stray>", '<x a = "1" B=\'2\' c>', "<?pi?>",
                  "<![CDATA[<<{n}>>]]>", "& < >"]
        for _ in range(300):
            parts = []
            for n in range(rng.randrange(1, 40)):
                parts.append(rng.choice(pieces).format(n=n, a=rng.randrange(1024), b=rng.randrange(768),
                                                       c=rng.randrange(1024), d=rng.randrange(768)))
            data = "<layout>" + "".join(parts) + rng.choice(["</layout>", ""])
            self.assertEqual(ul.parse(data.encode()).text(), data)


class Edits(unittest.TestCase):
    def setUp(self):
        self.data = ODD.encode()
        self.doc = ul.parse(self.data)

    def lines_changed(self):
        a, b = self.data.decode().split("\n"), self.doc.text().split("\n")
        return [(x, y) for x, y in zip(a, b) if x != y], len(b) - len(a)

    def test_an_attribute_changes_alone(self):
        tab = ul.find(self.doc, "panel-tab")[0]
        ul.set_attr(tab, "SIZE1024", "1 2 3 4")
        changed, added = self.lines_changed()
        self.assertEqual(added, 0)
        self.assertEqual(len(changed), 1)
        self.assertIn('size1024 ="1 2 3 4"', changed[0][1])      # its own spelling and spacing kept
        ul.set_attr(tab, "foreground", 'a"b')
        self.assertIn("foreground='a\"b'", self.doc.text())       # its own quotes kept
        ul.set_attr(tab, "z", "7")
        self.assertIn(' z="7">', self.doc.text().split("\n")[4])
        ul.set_attr(tab, "hidden", None)
        self.assertNotIn("hidden", self.doc.text().split("\n")[4])

    def test_text_keeps_its_surroundings(self):
        name = ul.find(self.doc, "panel-name")[0]
        ul.set_text(name, "$$1$$Other")
        self.assertIn("\t\t\t$$1$$Other\r\n", self.doc.text())
        hp = ul.find(self.doc, "panel-hp")[0]
        ul.set_text(hp, "{currentUnitHP}")
        self.assertIn('size1024="400 660 560 680">{currentUnitHP}</gadget>', self.doc.text())
        self.assertEqual(ul.parse(self.doc.data()).text(), self.doc.text())

    def test_insert_and_remove(self):
        panel = ul.find(self.doc, "panel")[0]
        before = self.doc.text()
        new = ul.insert(panel, None, '<gadget name="panel-new" type="formatText" size1024="1 1 2 2"/>')
        text = self.doc.text()
        self.assertIn('\t\t<gadget name="panel-new" type="formatText" size1024="1 1 2 2"/>', text)
        self.assertEqual([g.get("name") for g in ul.parse(text.encode()).gadgets()].count("panel-new"), 1)
        ul.remove(new[0])
        self.assertEqual(self.doc.text(), before)
        hp = ul.find(self.doc, "panel-hp")[0]
        ul.insert(hp, None, '<gadget name="child"/>')            # a self-closing parent opens up
        self.assertIn("</gadget>", self.doc.text().split("panel-hp", 1)[1].split("\n")[2])
        self.assertEqual(ul.find(ul.parse(self.doc.data()), "child")[0].parent.get("name"), "panel-hp")

    def test_ui_preview_reads_the_same_tree(self):
        try:
            import numpy  # noqa: F401  (ui_preview draws with it)
        except ImportError:
            self.skipTest("tools/ui_preview.py needs numpy")
        import ui_preview
        root = ui_preview.parse(ODD)
        self.assertEqual([n.name for n, _, _ in ui_preview.gadgets(root)],
                         [g.get("name") for g in self.doc.gadgets()])
        # and the same parents
        self.assertEqual([(ui_preview.gadget_parent(n).name if ui_preview.gadget_parent(n) else None)
                          for n, _, _ in ui_preview.gadgets(root)],
                         [(g.parent.get("name") if g.parent.name_lower == "gadget" else None)
                          for g in self.doc.gadgets()])


class Tables(unittest.TestCase):
    """aoe3game/uidata: what the engine does that the files do not say, in both languages."""

    def load(self, name):
        import json
        with open(os.path.join(ROOT, "aoe3_blender_tools", "aoe3game", "uidata", name + ".json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_every_entry_says_it_in_english_and_spanish(self):
        import re
        for fn in self.load("ui_functions")["functions"]:
            self.assertTrue(fn["en"] and fn["es"] and isinstance(fn["works"], bool), fn["name"])
        for g in self.load("engine_gadgets")["gadgets"]:
            re.compile(g["re"])
            self.assertTrue(g["en"] and g["es"] and g["when"]["en"] and g["when"]["es"], g["re"])
        scene = self.load("hud_scene")
        for m in scene["moments"]:
            self.assertTrue(m["en"] and m["es"] and m["names"] and isinstance(m["on"], bool), m["id"])
        for o in scene["oneOf"]:
            self.assertIn(o["show"], o["choices"])
            self.assertTrue(o["en"] and o["es"])

    def test_the_stubs_are_the_measured_ones(self):
        stubs = {fn["name"] for fn in self.load("ui_functions")["functions"] if not fn["works"]}
        self.assertEqual(stubs, {"currentUnitAttackRange", "currentUnitMinAttackRange", "currentUnitBuildRate",
                                 "currentUnitGatherRate", "currentUnitAttackList", "currentUnitAttackString",
                                 "currentUnitGatherRateString"})


class Fonts(unittest.TestCase):
    def test_fonts3_entries_by_width(self):
        import hud_copy
        from aoe3game import uifonts
        fonts = uifonts.parse(hud_copy.FONTS.encode("utf-16"))
        self.assertEqual(set(fonts), {"test 12", "arial nobold nodrop 12"})
        at = {w: uifonts.lookup(fonts, "Test", 12, w)["AscentHeight"] for w in (640, 800, 1024, 1279, 1280, 1920)}
        self.assertEqual(at, {640: 10, 800: 10, 1024: 12, 1279: 12, 1280: 16, 1920: 16})   # base values at 1024
        self.assertEqual(uifonts.lookup(fonts, "TEST", "12", 1024)["TypeFace"], "Test Face")
        self.assertTrue(uifonts.lookup(fonts, "Test", 12)["Bold"])
        self.assertIsNone(uifonts.lookup(fonts, "Missing", 10))
        self.assertIn(uifonts.FALLBACK, fonts)

    def test_a_truetype_file_is_found_by_its_family(self):
        import hud_copy
        from aoe3game import uifonts
        self.assertEqual(uifonts.ttf_names(hud_copy.ttf_with_name("Formal Test"))["family"], "Formal Test")
        self.assertEqual(uifonts.ttf_names(b"not a font"), {})

    def test_the_string_table_by_number(self):
        import hud_copy
        from aoe3game import proto
        idx = proto.strings_index(hud_copy.STRINGS)
        self.assertEqual(idx[101], ("Colonial Age", "cStringAge"))
        self.assertEqual(idx[102], ("Unused & kept", None))


if __name__ == "__main__":
    unittest.main()
