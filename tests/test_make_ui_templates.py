# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the interface's texture pieces (aoe3game/uiatlas.py), the PSD writer and reader
(aoe3game/psd.py), ddt.write_like and tools/make_ui_templates.py, on a synthetic copy made here (no
game data). Needs numpy (the venv); Pillow, when present, reads the merged image too.

    venv/Scripts/python -I tests/test_make_ui_templates.py
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import make_ui_templates as mut  # noqa: E402
import ui_preview as up  # noqa: E402
from aoe3game import ddt, psd, uiatlas  # noqa: E402
from core.pngio import encode_png  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "make_ui_templates.py")

# A main screen and a minimap panel in the 1024 x 768 space. The atlas is 64 x 64: the frame is its
# top half (0..32), a row shares the frame's top 8 pixels, the European resource panel its bottom left
# quarter; the bottom right quarter is used by no gadget. A Max skin never shows in the minimised
# interface; a hidden panel shows when the game shows it; the clock waits for its moment.
MAIN = r"""<layout>
  <gadget name="SettlerCountDialog-defaultPanelEurMin" size1024="220 630 345 768" background="ui\ingame\atlas" textureCoords="0 0.5 0.5 1"/>
  <gadget name="SettlerCountDialog-defaultPanelEurMax" size1024="220 630 345 768" background="ui\ingame\atlas" textureCoords="0.5 0.5 1 1"/>
  <gadget name="clockTimer" size1024="300 0 700 60" background="ui\ingame\clock"/>
  <gadget name="menu" size1024="900 0 1024 30" hidden="">
    <gadget name="menu-button" size1024="900 0 1024 30" textureCoords="0 0 1 1">
      <stateEntry background="ui\ingame\clock"/><stateEntry background="ui\ingame\atlas"/>
    </gadget>
  </gadget>
  <gadget name="icon" size1024="0 0 10 10" background="ui\units\not_ingame"/>
</layout>"""
MINIMAP = r"""<layout>
  <gadget name="minimapPanel" size1024="0 628 342 768" background="ui\ingame\atlas" textureCoords="0 0 1 0.5"/>
  <gadget name="trainsandcontains-row0" size1024="700 509 1024 547" background="ui\ingame\atlas" textureCoords="0 0 1 0.125"/>
</layout>"""


def atlas_rgba():
    rng = np.random.default_rng(7)
    img = rng.integers(0, 256, (64, 64, 4)).astype(np.uint8)
    img[..., 3] = 255
    img[40:44, 10:20, 3] = 0                  # a hole in the resource panel
    img[0:2, :, 3] = 136                       # a soft top edge on the frame
    return img


def make_copy(folder):
    os.makedirs(os.path.join(folder, "data"))
    os.makedirs(os.path.join(folder, "art", "ui", "ingame"))
    os.makedirs(os.path.join(folder, "Startup"))
    with open(os.path.join(folder, "data", "uimainnew.xml"), "w", encoding="utf-8") as fh:
        fh.write(MAIN)
    with open(os.path.join(folder, "data", "uiminimappanelnewmin.xml"), "w", encoding="utf-8") as fh:
        fh.write(MINIMAP)
    with open(os.path.join(folder, "art", "ui", "ingame", "atlas.ddt"), "wb") as fh:
        fh.write(ddt.write(atlas_rgba(), ddt.DXT3, alpha=4, mips=False))
    clock = np.zeros((16, 32, 4), np.uint8)
    clock[...] = (90, 60, 30, 255)
    with open(os.path.join(folder, "art", "ui", "ingame", "clock.ddt"), "wb") as fh:
        fh.write(ddt.write(clock, ddt.BGRA, alpha=1, mips=True))
    with open(os.path.join(folder, "Startup", "uhc.cfg"), "w", encoding="utf-8") as fh:
        fh.write("asianCivs Egyptians Zulu Maori\nNativeCivs WallMapu\n")
    return folder


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True, text=True)


class Pieces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.copy = make_copy(self.tmp.name)
        self.m = mut.Copy(self.copy).ui_map("min", (1920, 1080))

    def tearDown(self):
        self.tmp.cleanup()

    def test_atlases_pieces_and_numbers(self):
        self.assertEqual(list(self.m.atlases), [r"ui\ingame\atlas", r"ui\ingame\clock"])
        atlas = self.m.atlases[r"ui\ingame\atlas"]
        got = [(p.number, p.rect, p.gadgets) for p in atlas.pieces]
        self.assertEqual(got, [(1, (0, 0, 64, 8), ["trainsandcontains-row0"]),
                               (2, (0, 0, 64, 32), ["minimapPanel"]),
                               (3, (0, 0, 64, 64), ["menu-button"]),
                               (4, (0, 32, 32, 64), ["SettlerCountDialog-defaultPanelEurMin"])])
        # the Max skin is not in the minimised interface; a texture outside ui\ingame is not either
        self.assertNotIn("SettlerCountDialog-defaultPanelEurMax", [g for p in atlas.pieces for g in p.gadgets])
        clock = self.m.atlases[r"ui\ingame\clock"]
        self.assertEqual([p.gadgets for p in clock.pieces], [["clockTimer", "menu-button"]])   # one rectangle shared
        self.assertEqual([u.role for u in clock.pieces[0].uses], ["background", "state 0"])

    def test_when_names_overlaps_unused(self):
        atlas = self.m.atlases[r"ui\ingame\atlas"]
        p = {q.number: q for q in atlas.pieces}
        self.assertEqual(p[2].when(), "always")
        self.assertEqual(p[4].when(), "European resource panel skin")
        self.assertEqual(p[3].when(), "when the game shows it")
        self.assertEqual(p[2].name, "Minimap frame")
        self.assertEqual(p[3].name, "Menu button, pressed")
        self.assertEqual(atlas.overlaps(), [(0, 1), (0, 2), (1, 2), (2, 3)])
        self.assertEqual(atlas.clusters(), [[0, 1, 2, 3]])
        self.assertFalse(atlas.unused().any())             # the menu button covers it all
        m2 = uiatlas.atlas_map([("main", up.parse(MINIMAP))], lambda k: (64, 64), "min")
        unused = m2.atlases[r"ui\ingame\atlas"].unused()
        self.assertTrue(unused[40:, :].all() and not unused[:32].any())

    def test_stretch(self):
        atlas = self.m.atlases[r"ui\ingame\atlas"]
        frame = atlas.pieces[1]
        (sx, _), (sy, _) = frame.stretch_range()
        self.assertAlmostEqual(sx, 342 * 1.875 / 64, places=3)   # 64 px drawn 641 px wide: enlarged
        self.assertAlmostEqual(sy, 140 * 1.40625 / 32, places=3)
        self.assertTrue(frame.enlarged)
        m = uiatlas.atlas_map([("main", up.parse(MINIMAP))], lambda k: (1024, 512), "min")
        big = m.atlases[r"ui\ingame\atlas"].pieces[1]         # 1024 x 256 px for 342 x 140 units
        self.assertFalse(big.enlarged)
        self.assertTrue(big.uneven)                           # 0.63 across, 0.77 down: not the screen's 4:3


class Psd(unittest.TestCase):
    def test_packbits(self):
        rng = np.random.default_rng(3)
        for row in (b"", b"a", b"aa", b"aaa", b"ab" * 70, bytes(300), bytes(rng.integers(0, 3, 999, dtype=np.uint8)),
                    bytes(rng.integers(0, 256, 500, dtype=np.uint8))):
            self.assertEqual(psd.unpackbits(psd.packbits(row), len(row)), row)

    def test_write_read(self):
        rng = np.random.default_rng(5)
        base = np.zeros((30, 50, 4), np.uint8)
        base[...] = (10, 200, 30, 255)
        crop = rng.integers(0, 256, (8, 12, 4)).astype(np.uint8)
        items = [psd.Layer("Original", base, visible=False, locked=True),
                 psd.Group("Paint", [psd.Layer("Pièce 1 (x)", crop, left=4, top=6),
                                     psd.Layer("half", base, opacity=128)]),
                 psd.Group("Guides", [psd.Layer("lines", base)], visible=False)]
        data = psd.write(50, 30, items, guides=[(4, "v"), (6.5, "h")])
        f = psd.read(data)
        self.assertEqual((f.width, f.height), (50, 30))
        self.assertEqual([(p, l.name, l.visible, l.locked) for p, l in f.layers()],
                         [([], "Original", False, True), (["Paint"], "Pièce 1 (x)", True, False),
                          (["Paint"], "half", True, False), (["Guides"], "lines", True, False)])
        self.assertEqual([(g.name, g.visible) for g in f.items if g.is_group], [("Paint", True), ("Guides", False)])
        self.assertEqual(f.guides, [(4.0, "v"), (6.5, "h")])
        lay = f.find("Pièce 1 (x)")
        keep = crop[..., 3] > 0                               # the layer is cut to its visible pixels
        ys, xs = np.nonzero(keep)
        self.assertEqual((lay.left, lay.top), (4 + xs.min(), 6 + ys.min()))
        full = np.zeros((30, 50, 4), np.uint8)
        full[lay.top:lay.top + lay.rgba.shape[0], lay.left:lay.left + lay.rgba.shape[1]] = lay.rgba
        self.assertTrue((full[6:14, 4:16][keep] == crop[keep]).all())
        self.assertEqual(f.find("half").opacity, 128)
        comp, notes = psd.compose(items, 50, 30)
        self.assertEqual(notes, [])
        diff = np.abs(f.composite.astype(int) - comp.astype(int))
        self.assertLessEqual(int(diff.max()), 1)              # the white matte, taken off again
        self.assertEqual(int(comp[0, 0, 3]), 128)             # the half layer alone in that corner
        try:
            from PIL import Image
        except ImportError:
            return
        im = Image.open(io.BytesIO(data))
        im.load()
        self.assertEqual(im.size, (50, 30))
        self.assertTrue((np.asarray(im.convert("RGBA")) == psd.matte(comp)).all())

    def test_compose_skips_and_reports(self):
        a = np.zeros((4, 4, 4), np.uint8)
        a[...] = (255, 0, 0, 255)
        lay = psd.Layer("x", a, blend="mul ")
        img, notes = psd.compose([lay, psd.Group("Guides", [psd.Layer("g", a)])], 4, 4,
                                 skip=lambda it, path: it.name == "Guides")
        self.assertEqual(tuple(img[0, 0]), (255, 0, 0, 255))
        self.assertTrue(notes and "blend mode" in notes[0])


class WriteLike(unittest.TestCase):
    def test_same_pixels_same_bytes_and_changed_blocks(self):
        img = atlas_rgba()
        data = ddt.write(img, ddt.DXT3, alpha=4, mips=False)
        dec = ddt.decode(data)
        out, changed = ddt.write_like(data, dec)
        self.assertEqual((out, changed), (data, 0))
        new = dec.copy()
        new[0:4, 0:4, :3] = 255
        out, changed = ddt.write_like(data, new)
        self.assertEqual(changed, 1)
        self.assertEqual(len(out), len(data))
        self.assertEqual(ddt.read_header(out).describe(), ddt.read_header(data).describe())
        _, a = ddt.level_blocks(data)
        _, b = ddt.level_blocks(out)
        self.assertTrue((a[1:] == b[1:]).all())

    def test_mips_and_formats_kept(self):
        img = np.zeros((16, 32, 4), np.uint8)
        img[...] = (90, 60, 30, 255)
        data = ddt.write(img, ddt.BGRA, alpha=1, usage=1, mips=True)
        new = img.copy()
        new[..., 0] = 200
        out, changed = ddt.write_like(data, new)
        hd, ho = ddt.read_header(data), ddt.read_header(out)
        self.assertEqual((ho.format, ho.alpha, ho.usage, ho.mips), (hd.format, hd.alpha, hd.usage, hd.mips))
        self.assertEqual(changed, -1)
        self.assertEqual(tuple(ddt.decode(out, hd.mips - 1)[0, 0]), (200, 60, 30, 255))
        with self.assertRaises(ddt.DdtError):
            ddt.write_like(data, np.zeros((8, 8, 4), np.uint8))


class Tool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.copy = make_copy(os.path.join(self.tmp.name, "copy"))
        self.out = os.path.join(self.tmp.name, "tpl")
        r = run("templates", "--game", self.copy, "--out", self.out, "--overview")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.stdout = r.stdout

    def tearDown(self):
        self.tmp.cleanup()

    def test_templates(self):
        names = sorted(os.listdir(self.out))
        self.assertEqual(names, ["README.txt", "atlas.layers.png", "atlas.psd", "clock.layers.png", "clock.psd",
                                 "pieces.json", "reference_sheet.png"])
        with open(os.path.join(self.out, "atlas.psd"), "rb") as fh:
            f = psd.read(fh.read())
        self.assertEqual([it.name for it in f.items], ["Original", "Paint", "Guides"])
        self.assertTrue(f.items[0].locked and not f.items[0].visible and not f.items[2].visible)
        paint = f.items[1].children
        self.assertEqual([l.name for l in paint],
                         ["1+2+3+4 Train and hold row + Minimap frame + Menu button, pressed + Resource panel, European "
                          "(trainsandcontains-row0, minimapPanel +2)"])
        self.assertEqual([l.name for l in f.items[2].children],
                         ["Unused areas (hatched)", "Stretched pieces", "Outlines and names"])
        self.assertIn((32.0, "h"), f.guides)
        with open(os.path.join(self.out, "README.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("af  Africans (Ethiopians, Egyptians, Zulu): the shared ones + the European and Asian", text)
        self.assertIn("na  Native Americans (XPIroquois, XPSioux, WallMapu): the shared ones + the Native", text)
        self.assertIn("European resource panel: atlas (piece 4)", text)
        self.assertIn("<texture>_<suffix>_gw.ddt", text)

    def test_round_trip_and_paint(self):
        built = os.path.join(self.tmp.name, "built")
        r = run("build", "--game", self.copy, "--in", self.out, "--suffix", "as", "--out", built)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 warnings", r.stdout)
        for name in ("atlas", "clock"):
            with open(os.path.join(self.copy, "art", "ui", "ingame", name + ".ddt"), "rb") as fh:
                original = fh.read()
            with open(os.path.join(built, "ui", "ingame", name + "_as.ddt"), "rb") as fh:
                self.assertEqual(fh.read(), original, name)         # untouched: byte for byte
        # an exported PNG of the Paint group gives the same; a painted piece changes only its blocks
        with open(os.path.join(self.out, "atlas.psd"), "rb") as fh:
            f = psd.read(fh.read())
        flat, _ = psd.compose([f.items[1]], 64, 64)
        flat[36:40, 36:40, :3] = (255, 0, 255)                     # inside the menu button's piece
        flat[34:62, 2:30, 3] = 0                                    # most of the resource panel cut away
        filled = os.path.join(self.tmp.name, "filled")
        os.makedirs(filled)
        with open(os.path.join(filled, "atlas_me.png"), "wb") as fh:
            fh.write(encode_png(flat))
        out2 = os.path.join(self.tmp.name, "built2")
        r = run("build", "--game", self.copy, "--in", filled, "--suffix", "me", "--out", out2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("piece 4 Resource panel, European: its transparency changed", r.stdout)
        with open(os.path.join(out2, "ui", "ingame", "atlas_me.ddt"), "rb") as fh:
            got = ddt.decode(fh.read())
        self.assertEqual(tuple(got[37, 37, :3]), (255, 0, 255))
        self.assertFalse(os.path.exists(os.path.join(out2, "ui", "ingame", "clock_me.ddt")))   # not handed in

    def test_paint_outside_and_size(self):
        m = mut.Copy(self.copy).ui_map("min", (1920, 1080))
        only_minimap = uiatlas.atlas_map([("m", up.parse(MINIMAP))], lambda k: (64, 64), "min")
        atlas = only_minimap.atlases[r"ui\ingame\atlas"]
        original = atlas_rgba()
        painted = original.copy()
        painted[50:60, 50:60, :3] = 0
        final, warnings = mut.check_and_merge(atlas, original, painted)
        self.assertTrue(any("outside every piece" in w for w in warnings))
        self.assertTrue((final[50:60, 50:60] == original[50:60, 50:60]).all())      # dropped
        with self.assertRaises(mut.TemplateError):
            mut.check_and_merge(m.atlases[r"ui\ingame\atlas"], original, painted[:32])

    def test_refusals(self):
        r = run("templates", "--game", self.copy, "--out", os.path.join(self.copy, "out"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("outside the game copy", r.stderr)
        r = run("templates", "--game", self.copy, "--out", self.out, "--only", "nosuch")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a texture of this interface", r.stderr)
        r = run("build", "--game", self.copy, "--in", self.out, "--suffix", "AS!", "--out", self.out + "2")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
