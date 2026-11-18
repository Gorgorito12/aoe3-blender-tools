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
            self.assertGreater(int(colour.sum()), 250, glyph)

    def test_all_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp]), 0)
            names = sorted(p.name for p in pathlib.Path(tmp).iterdir())
            self.assertEqual(names, sorted(msi.BOLD_FILES.values()))
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp, "--check"]), 0)
            (pathlib.Path(tmp) / "stat_icon_rof.ddt").write_bytes(b"RTS3")
            self.assertEqual(msi.main(["--style", "bold", "--all", tmp, "--check"]), 1)


class SoftStyle(unittest.TestCase):
    def test_first_set_unchanged_format(self):
        h = ddt.read_header(msi.encode("stopwatch"))
        self.assertEqual((h.width, h.height, h.format, h.mips), (16, 16, ddt.DXT3, 1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
