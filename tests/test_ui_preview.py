# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/ui_preview.py on a synthetic layout (no game data). Needs numpy (the venv):

    venv/Scripts/python -I tests/test_ui_preview.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import ui_preview as up  # noqa: E402
from core.pngio import read_png  # noqa: E402

# A panel written as hand-edited layouts often are: a comment holding a gadget, an attribute
# name in upper case, spaces around "=", a child placed far outside its parent, a hidden
# gadget, and one closing tag too many at the end.
LAYOUT = """<?xml version="1.0" encoding="utf-8"?>
<layout>
  <gadget name="panel" type="gadget" size1024="100 600 500 760">
    <!--gadget name="commented" type="gadget" size1024="0 0 10 10"/-->
    <gadget name="panel-value" Type="formatText" size1024 ="120 620 200 640">
      <gadget name="panel-speed" type="formatText" size1024="400 700 480 720">Speed: {currentUnitMaxVelocityFloat}</gadget>
    </gadget>
    <gadget name="panel-row0" type="formatText" size1024="120 650 300 664" hidden=""/>
    <gadget name="panel-uhcRow1" type="formatText" size1024="120 666 300 680"/>
  </gadget>
  </gadget>
</layout>
"""


class Parse(unittest.TestCase):
    def setUp(self):
        self.root = up.parse(LAYOUT)
        self.items = up.gadgets(self.root)

    def test_names_depths_and_order(self):
        self.assertEqual([(n.name, d) for n, d, _ in self.items],
                         [("panel", 0), ("panel-value", 1), ("panel-speed", 2), ("panel-row0", 1),
                          ("panel-uhcRow1", 1)])
        self.assertEqual([i for _, _, i in self.items], [1, 2, 3, 4, 5])

    def test_attributes(self):
        value = self.items[1][0]
        self.assertEqual(value.attrs["type"], "formatText")       # names are lower-cased
        self.assertEqual(value.rect, (120.0, 620.0, 200.0, 640.0))
        self.assertIn("hidden", self.items[3][0].attrs)
        self.assertIn("{currentUnitMaxVelocityFloat}", self.items[2][0].text)

    def test_outside_parent(self):
        flags = {n.name: up.outside_parent(n) for n, _, _ in self.items}
        self.assertEqual(flags, {"panel": False, "panel-value": False, "panel-speed": True,
                                 "panel-row0": False, "panel-uhcRow1": False})

    def test_overhang_tolerance(self):
        root = up.parse('<layout><gadget name="a" size1024="0 0 100 100">'
                        '<gadget name="b" size1024="-3 0 103 100"/></gadget></layout>')
        b = up.gadgets(root)[1][0]
        self.assertFalse(up.outside_parent(b))
        self.assertTrue(up.outside_parent(b, tolerance=1))

    def test_hide(self):
        import re
        names = [n.name for n, _, _ in up.gadgets(self.root, re.compile("value"))]
        self.assertEqual(names, ["panel", "panel-row0", "panel-uhcRow1"])   # its child goes too


class Render(unittest.TestCase):
    def test_picture(self):
        import re
        img = up.render(up.parse(LAYOUT), scale=2, mark=re.compile("uhc"), title="T", show_text=True)
        self.assertEqual(img.ndim, 3)
        self.assertEqual(img.shape[2], 3)
        # the drawing area is the boxes' extent plus 8 units each side, at scale 2
        self.assertGreaterEqual(img.shape[1], (500 - 100 + 16) * 2)
        flat = img.reshape(-1, 3)
        has = lambda c: bool(((flat == c).all(axis=1)).any())  # noqa: E731
        self.assertTrue(has(up.OUT_COLOUR))      # the speed box and its legend line
        self.assertTrue(has(up.MARK_COLOUR))     # the marked row

    def test_region(self):
        img = up.render(up.parse(LAYOUT), scale=1, region=(0, 0, 1024, 768))
        self.assertEqual(img.shape[0], 768)


class Cli(unittest.TestCase):
    def test_writes_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "ui.xml")
            out = os.path.join(tmp, "ui.png")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(LAYOUT)
            r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "ui_preview.py"), src,
                                "--out", out, "--mark", "uhc", "--text"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("5 gadgets, 1 outside their parent", r.stdout)
            with open(out, "rb") as fh:
                img = read_png(fh.read())
            self.assertGreater(len(img), 0)


if __name__ == "__main__":
    unittest.main()
