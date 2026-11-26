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
sys.path.insert(0, os.path.join(ROOT, "tests"))

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


# The textured screen: tiny textures written here (no game data), drawn at 256 x 192 (a quarter of
# the 1024 x 768 layout space, so 1 pixel = 4 layout units).
SCREEN = r"""<layout>
  <gadget name="atlasRight" size1024="0 0 512 384" background="ui\ingame\atlas" textureCoords="0.5 0 1 1"/>
  <gadget name="secret" size1024="512 0 1024 384" background="ui\ingame\red" hidden=""/>
  <gadget name="SettlerCountDialog-defaultPanelEurMax" size1024="0 384 256 768" background="ui\ingame\red"/>
  <gadget name="SettlerCountDialog-defaultPanelAsiMax" size1024="0 384 256 768" background="ui\ingame\atlas"/>
  <gadget name="top" size1024="256 384 512 768" background="ui\ingame\red" z="2"/>
  <gadget name="under" size1024="256 384 512 768" background="ui\ingame\atlas" z="1"/>
  <gadget name="tiled" size1024="512 384 768 768" background="ui\ingame\checker" tileBackground=""/>
  <gadget name="half" size1024="768 384 1024 768" backgroundColor="0 0 255" backgroundAlpha="0.5"/>
  <gadget name="clockTimer" size1024="512 0 1024 384" background="ui\ingame\atlas"/>
</layout>"""


def write_textures(folder):
    """atlas: left half blue, right half green; red; red_cult: yellow; checker: 2 x 2 black and white."""
    import numpy as np
    from core.pngio import encode_png
    from aoe3game import ddt
    os.makedirs(os.path.join(folder, "ui", "ingame"), exist_ok=True)
    atlas = np.zeros((4, 8, 4), np.uint8)
    atlas[..., 3] = 255
    atlas[:, :4, 2] = 255
    atlas[:, 4:, 1] = 255
    red = np.zeros((4, 4, 3), np.uint8)
    red[..., 0] = 255
    yellow = np.zeros((4, 4, 3), np.uint8)
    yellow[..., :2] = 255
    checker = np.zeros((2, 2, 3), np.uint8)
    checker[0, 0] = checker[1, 1] = 255
    for name, img in (("atlas", atlas), ("red_cult", yellow), ("checker", checker)):
        with open(os.path.join(folder, "ui", "ingame", name + ".png"), "wb") as fh:
            fh.write(encode_png(img))
    with open(os.path.join(folder, "ui", "ingame", "red.ddt"), "wb") as fh:
        fh.write(ddt.write_bgra(red, mips=False))


class Textured(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_textures(self.tmp.name)
        self.root = up.parse(SCREEN)

    def tearDown(self):
        self.tmp.cleanup()

    def draw(self, **kw):
        tex = up.Textures(overrides=[self.tmp.name], suffix=kw.pop("suffix", None))
        return up.render_screen([self.root], 256, 192, tex, **kw), tex

    def test_crop_hidden_culture_order_tile_alpha_moment(self):
        img, tex = self.draw()
        self.assertEqual(img.shape, (192, 256, 3))
        self.assertEqual(tuple(img[48, 64]), (0, 255, 0))       # textureCoords: the atlas' right half
        self.assertEqual(tuple(img[48, 192]), (0, 0, 0))        # hidden, and the clock waits for its moment
        self.assertEqual(tuple(img[144, 32]), (255, 0, 0))      # Eur's resource panel, not Asi's
        self.assertEqual(tuple(img[144, 96]), (255, 0, 0))      # z 2 over z 1, whatever the file order
        self.assertEqual(tuple(img[144, 224]), (0, 0, 128))     # half blue over black
        self.assertEqual(tex.missing, set())
        asi, _ = self.draw(culture="Asi")
        self.assertEqual(tuple(asi[144, 16]), (0, 0, 255))      # the Asian skin: the atlas, blue on its left
        shown, _ = self.draw(show_hidden=True)
        self.assertEqual(tuple(shown[48, 192])[0], 255)         # the hidden red gadget drawn when asked
        clock, _ = self.draw(moments_on={"clock": True})
        self.assertEqual(tuple(clock[48, 250]), (0, 255, 0))    # the moment switched on

    def test_tile_repeats_at_the_texture_size(self):
        # at 2048 px a texel is 2 px wide: the 2 x 2 checker repeats every 4 px, as it does in the
        # first texels (bilinear filtering softens it the same way in each repeat)
        tex = up.Textures(overrides=[self.tmp.name])
        big = up.render_screen([self.root], 2048, 1536, tex)
        x0, y0 = 1024, 768                                      # the tiled gadget's corner
        row = [int(big[y0 + 1, x0 + 1 + 2 * k, 0]) for k in range(6)]
        self.assertGreater(row[0], row[1] + 40)
        self.assertEqual(row[0::2], [row[0]] * 3)
        self.assertEqual(row[1::2], [row[1]] * 3)

    def test_suffix_takes_the_variant_where_it_exists(self):
        img, tex = self.draw(suffix="cult")
        self.assertEqual(tuple(img[144, 96]), (255, 255, 0))    # red -> red_cult (yellow)
        self.assertEqual(tuple(img[48, 64]), (0, 255, 0))       # atlas has no _cult: the shared one
        self.assertTrue(tex.used[r"ui\ingame\red"].endswith("red_cult.png"))

    def test_missing_textures_are_listed(self):
        tex = up.Textures(overrides=[self.tmp.name])
        up.render_screen([up.parse('<layout><gadget name="x" size1024="0 0 10 10" background="ui\\nothere"/></layout>')],
                         64, 48, tex)
        self.assertEqual(tex.missing, {r"ui\nothere"})

    def test_scene_of_a_copy_and_the_cli(self):
        import hud_copy
        with tempfile.TemporaryDirectory() as copy:
            hud_copy.make(copy)
            stems = [s for s, _ in up.scene_layouts(copy, "min")]
            self.assertEqual(stems[:2], ["uimainnew", "uiunitselectionmin"])    # loose, and Data3.bar's
            out = os.path.join(copy, "screen.png")
            r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "ui_preview.py"), "--game", copy,
                                "--scene", "min", "--size", "512x384", "--moment", "selected=off", "--out", out],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("512x384", r.stdout)
            self.assertIn(r"ui\ingame\nothere  NOT FOUND", r.stdout)
            with open(out, "rb") as fh:
                img = read_png(fh.read())
            self.assertEqual(img.shape[:2], (384, 512))
            r_, g_, b_ = (int(v) for v in img[5, 250, :3])                   # the title bar's texture
            self.assertTrue(abs(r_ - 200) < 12 and abs(g_ - 120) < 12 and abs(b_ - 40) < 12, (r_, g_, b_))
            bad = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "ui_preview.py"), "--game", copy,
                                  "--scene", "min", "--moment", "nosuch=on", "--out", out], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("no moment", bad.stderr)

    def test_box_mode_still_needs_one_layout(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "ui_preview.py"), "--out", "x.png"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
