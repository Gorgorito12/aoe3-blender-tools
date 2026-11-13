# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the small art generators tools/make_rings.py, tools/make_icons.py and tools/make_bar.py.
Plain Python; the pixel checks need numpy (the venv) and are skipped without it:

    python -I tests/test_art_generators.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import make_bar  # noqa: E402
import make_icons  # noqa: E402
import make_rings  # noqa: E402
from aoe3game import ddt  # noqa: E402

try:
    import numpy as np
except ImportError:          # plain Python without numpy
    np = None


def run_tool(script, *args):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", script), *args],
                          capture_output=True, text=True)


class Rings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = make_rings.wanted_files("myrings")

    def test_every_kind_is_written(self):
        names = set(self.files)
        for colour in make_rings.RINGS:
            self.assertIn(f"ring_{colour}.xml", names)
            self.assertIn(f"ring_{colour}.ddt", names)
        for radius in make_rings.RANGES:
            self.assertIn(f"range_{radius}.xml", names)
        for rank in range(1, 6):
            self.assertIn(f"rank_{rank}.xml", names)
        self.assertIn("aura_gold.xml", names)
        self.assertEqual(len(names), 181)

    def test_paths_name_the_folder(self):
        for name, data in self.files.items():
            if name.endswith((".xml", ".particle")):
                text = data.decode("utf-8")
                self.assertNotIn("\n", text.replace("\r\n", ""), name)       # CRLF, as the game's files
                for line in text.splitlines():
                    if "<file>effects\\" in line and "Chiefpower" not in line:
                        self.assertIn("<file>effects\\myrings\\", line, name)
        other = make_rings.wanted_files("rings")
        self.assertIn(b"effects\\rings\\ring_gold_unit.particle", other["ring_gold.xml"])
        # Only the paths change with the folder: the textures are the same.
        self.assertEqual(other["ring_gold.ddt"], self.files["ring_gold.ddt"])

    def test_textures_are_dxt3_with_mips(self):
        for name, data in self.files.items():
            if name.endswith(".ddt"):
                hd = ddt.read_header(data)
                self.assertEqual(hd.format, ddt.DXT3, name)
                self.assertEqual(hd.width, hd.height, name)
                self.assertEqual(len(hd.levels), hd.mips, name)
                end = hd.levels[-1][0] + hd.levels[-1][1]
                self.assertEqual(end, len(data), name)

    @unittest.skipIf(np is None, "numpy not available")
    def test_ring_is_transparent_in_the_middle_and_coloured_at_the_rim(self):
        px = ddt.decode(self.files["ring_food.ddt"])
        self.assertEqual(px[32, 32, 3], 0)                  # the centre shows the ground
        rim = px[32, 2]                                     # near the outer edge, on the wide band
        self.assertGreater(rim[3], 100)
        self.assertGreater(int(rim[0]), int(rim[2]) + 60)   # food is red

    def test_bad_folder_is_refused(self):
        self.assertNotEqual(run_tool("make_rings.py", "--folder", "a\\b", "--check").returncode, 0)

    def test_command_line_check(self):
        """One run of the tool (about 40 s: every texture is drawn in plain Python)."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in self.files.items():
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(data)
            result = run_tool("make_rings.py", "--out", tmp, "--folder", "myrings", "--check")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("181 files, 0 differ", result.stdout)


class Icons(unittest.TestCase):
    def test_names_and_table(self):
        files = make_icons.wanted("p_")
        self.assertEqual(sorted(files), ["avatar_p_icons.xml", "p_blue.ddt", "p_green.ddt", "p_red.ddt"])
        table = files["avatar_p_icons.xml"].decode("utf-8")
        self.assertIn('<avatar id="p_blue"><image>ui\\playericons\\p_blue</image></avatar>', table)
        self.assertIn("avatar.xml", make_icons.wanted("p_", "avatar.xml"))

    def test_dxt1_64(self):
        hd = ddt.read_header(make_icons.wanted()["test_red.ddt"])
        self.assertEqual((hd.format, hd.width, hd.height, hd.mips), (ddt.DXT1, 64, 64, 1))

    @unittest.skipIf(np is None, "numpy not available")
    def test_glyph_and_frame(self):
        px = ddt.decode(make_icons.wanted()["test_blue.ddt"])
        self.assertTrue((px[32, 32, :3] > 240).all())        # the white diamond in the middle
        self.assertGreater(int(px[8, 8, 2]), int(px[8, 8, 0]) + 80)   # blue background
        self.assertGreater(int(px[1, 32, 2]), int(px[8, 8, 2]))       # the lighter frame

    def test_install_refuses_steam(self):
        with tempfile.TemporaryDirectory() as tmp:
            steam = os.path.join(tmp, "steamapps", "common", "game")
            result = run_tool("make_icons.py", "--out", os.path.join(tmp, "o"), "--install", steam)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.exists(steam))


class Bar(unittest.TestCase):
    def test_layout(self):
        data = make_bar.ddt((0x40, 0xC0, 0xFF))
        hd = ddt.read_header(data)
        self.assertEqual((hd.format, hd.width, hd.height, hd.mips), (ddt.DXT1, 16, 8, 1))
        self.assertEqual(len(data), 16 + 8 + 8 * 8)          # header, one level, 8 blocks

    @unittest.skipIf(np is None, "numpy not available")
    def test_shades(self):
        px = ddt.decode(make_bar.ddt((0xFF, 0x8C, 0x00))).astype(int)
        rows = px[:, 0, :3]
        self.assertTrue((abs(rows[4] - (0xFF, 0x8C, 0x00)) <= 8).all())   # the colour itself
        self.assertGreater(rows[1].sum(), rows[4].sum())                  # a lighter band above
        self.assertLess(rows[7].sum(), rows[4].sum())                     # darker at the bottom
        self.assertTrue((px[:, :, :3] == px[:, :1, :3]).all())            # one colour per row

    def test_colour_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "blue.ddt")
            self.assertEqual(run_tool("make_bar.py", "--colour", "40C0FF", "--out", out).returncode, 0)
            self.assertEqual(run_tool("make_bar.py", "--colour", "40C0FF", "--out", out, "--check").returncode, 0)
            self.assertEqual(run_tool("make_bar.py", "--out", out, "--check").returncode, 1)
            self.assertNotEqual(run_tool("make_bar.py", "--colour", "blue", "--out", out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
