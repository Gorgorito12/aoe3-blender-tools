# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/make_stat_icon.py. Needs numpy (the venv):

    venv/Scripts/python -I tests/test_stat_icons.py
"""
import os
import pathlib
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import make_stat_icon as msi  # noqa: E402
from aoe3game import ddt  # noqa: E402


class BoldStyle(unittest.TestCase):
    def test_format_as_the_mod_icons(self):
        for glyph in msi.BOLD_GLYPHS:
            data = msi.encode_bold(glyph)
            h = ddt.read_header(data)
            self.assertEqual((h.width, h.height, h.format, h.alpha, h.usage, h.mips), (32, 32, ddt.BGRA, 4, 0, 1),
                             glyph)
            self.assertEqual(len(data), 16 + 8 + 32 * 32 * 4, glyph)

    def test_hard_edges_and_black_outline(self):
        for glyph in msi.BOLD_GLYPHS:
            rgba = np.asarray(ddt.decode(msi.encode_bold(glyph)))
            alpha = rgba[..., 3]
            self.assertEqual(set(np.unique(alpha).tolist()), {0, 255}, glyph)
            shown = alpha == 255
            # every shown texel next to a transparent one is black: the outline closes the glyph
            edge = shown & ~(np.roll(shown, 1, 0) & np.roll(shown, -1, 0) & np.roll(shown, 1, 1) &
                             np.roll(shown, -1, 1))
            self.assertTrue((rgba[edge, :3] == 0).all(), glyph)

    def test_glyph_leaves_room_for_the_outline(self):
        for glyph, draw in msi.BOLD_GLYPHS.items():
            ys, xs = np.nonzero(draw().cover)
            self.assertGreaterEqual(min(xs.min(), ys.min()), 2, glyph)
            self.assertLessEqual(max(xs.max(), ys.max()), 29, glyph)

    def test_strokes_are_thick(self):
        # the glyph's coloured (non-black) area is a good part of the picture, not thin lines
        for glyph in msi.BOLD_GLYPHS:
            rgba = msi.render_bold(glyph)
            colour = (rgba[..., 3] == 255) & (rgba[..., :3].max(axis=2) > 40)
            self.assertGreater(int(colour.sum()), 200, glyph)

    def test_all_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp]), 0)
            names = sorted(p.name for p in pathlib.Path(tmp).iterdir())
            self.assertEqual(names, sorted(msi.BOLD_FILES.values()))
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp, "--check"]), 0)
            (pathlib.Path(tmp) / "stat_icon_rof.ddt").write_bytes(b"RTS3")
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp, "--check"]), 1)


class TypeIcons(unittest.TestCase):
    def test_format_edges_and_room(self):
        for glyph, draw in msi.TYPE_GLYPHS.items():
            data = msi.encode_type(glyph)
            h = ddt.read_header(data)
            self.assertEqual((h.width, h.height, h.format, h.alpha, h.mips), (32, 32, ddt.BGRA, 4, 1), glyph)
            rgba = np.asarray(ddt.decode(data))
            shown = rgba[..., 3] == 255
            self.assertEqual(set(np.unique(rgba[..., 3]).tolist()), {0, 255}, glyph)
            edge = shown & ~(np.roll(shown, 1, 0) & np.roll(shown, -1, 0) & np.roll(shown, 1, 1) &
                             np.roll(shown, -1, 1))
            self.assertTrue((rgba[edge, :3] == 0).all(), glyph)
            ys, xs = np.nonzero(draw().cover)
            self.assertGreaterEqual(min(xs.min(), ys.min()), 2, glyph)
            self.assertLessEqual(max(xs.max(), ys.max()), 29, glyph)
            colour = shown & (rgba[..., :3].max(axis=2) > 40)
            self.assertGreater(int(colour.sum()), 80, glyph)  # a sabre's blade is the thinnest

    def test_coats(self):
        """The standing unit wears red, the line unit blue: the same soldier otherwise."""
        def coat(glyph):
            rgba = msi.render_type(glyph).astype(int)
            torso = rgba[22:29, 8:24, :3].reshape(-1, 3)
            return int((torso[:, 0] - torso[:, 2] > 80).sum()), int((torso[:, 2] - torso[:, 0] > 80).sum())
        red, blue = coat("standing"), coat("line")
        self.assertGreater(red[0], 30)
        self.assertGreater(blue[1], 30)
        self.assertGreater(red[0], 3 * red[1])
        self.assertGreater(blue[1], 3 * blue[0])
        shape = lambda g: msi.render_type(g)[..., 3] == 255  # noqa: E731
        self.assertTrue((shape("standing") == shape("line")).all())

    def test_files_keep_the_mod_names(self):
        paths = [p for files in msi.TYPE_FILES.values() for p in files]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(msi.TYPE_FILES), set(msi.TYPE_GLYPHS))
        for p in paths:
            self.assertTrue(p.startswith(("ui/ingame/", "WoL/ui/ingame/staticons/")), p)
            self.assertTrue(p.endswith(".ddt"), p)
        self.assertIn("WoL/ui/ingame/staticons/stat_icon_ranged.ddt", msi.TYPE_FILES["winged_bullet"])
        self.assertIn("WoL/ui/ingame/staticons/stat_icon_standing_unit.ddt", msi.TYPE_FILES["standing"])

    def test_types_write_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(msi.main(["--types", tmp]), 0)
            written = sorted(str(p.relative_to(tmp)).replace(os.sep, "/") for p in pathlib.Path(tmp).rglob("*.ddt"))
            self.assertEqual(written, sorted(p for files in msi.TYPE_FILES.values() for p in files))
            self.assertEqual(msi.main(["--types", tmp, "--check"]), 0)
            (pathlib.Path(tmp) / "ui/ingame/stat_hero.ddt").write_bytes(b"RTS3")
            self.assertEqual(msi.main(["--types", tmp, "--check"]), 1)


class SoftStyle(unittest.TestCase):
    def test_first_set_unchanged_format(self):
        h = ddt.read_header(msi.encode("stopwatch"))
        self.assertEqual((h.width, h.height, h.format, h.mips), (16, 16, ddt.DXT3, 1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
