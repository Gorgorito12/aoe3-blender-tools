# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/recolor_textures.py: the colour maths (CIEDE2000 against published pairs, OKLCH
round trips), the transform, and the textures it writes (header, mip levels, alpha, bump maps).
Synthetic textures only; needs numpy (the venv):

    venv\\Scripts\\python -I tests/test_recolor_textures.py
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import numpy as np  # noqa: E402

import recolor_textures as rc  # noqa: E402
from aoe3game import ddt  # noqa: E402


def red_field(size=64, seed=1):
    """A noisy crimson texture with a few brown and yellow pixels, like a marsh with soil and stems."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 4), np.uint8)
    img[..., 0] = rng.integers(90, 200, (size, size))
    img[..., 1] = rng.integers(10, 40, (size, size))
    img[..., 2] = rng.integers(15, 45, (size, size))
    img[..., 3] = 255
    img[::7, ::5, :3] = (150, 140, 40)          # yellow stems
    return img


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "recolor_textures.py"), *args],
                          capture_output=True, text=True)


class ColourMaths(unittest.TestCase):
    def test_ciede2000_matches_the_published_pairs(self):
        # Sharma, Wu and Dalal (2005), test data pairs 1, 2, 3, 7, 17, 25 and 34
        pairs = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
                 ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
                 ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
                 ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
                 ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
                 ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
                 ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373)]
        for a, b, expected in pairs:
            self.assertAlmostEqual(float(rc.ciede2000(a, b)), expected, places=3, msg=(a, b))
            self.assertAlmostEqual(float(rc.ciede2000(b, a)), expected, places=3, msg="symmetric")

    def test_lab_of_white_and_black(self):
        np.testing.assert_allclose(rc.srgb_to_lab(np.array([255.0, 255, 255])), [100, 0, 0], atol=0.05)
        np.testing.assert_allclose(rc.srgb_to_lab(np.array([0.0, 0, 0])), [0, 0, 0], atol=0.05)

    def test_oklch_round_trip(self):
        rgb = np.random.default_rng(3).integers(0, 256, (2000, 3)).astype(np.float64)
        back = rc.oklch_to_srgb(rc.srgb_to_oklch(rgb))
        self.assertLess(np.abs(back - rgb).max(), 0.01)

    def test_out_of_gamut_keeps_hue_and_lightness(self):
        lch = rc.srgb_to_oklch(np.array([[200.0, 30, 30]]))
        lch[:, 1] *= 3                               # far outside sRGB
        rgb = rc.oklch_to_srgb(lch)
        self.assertTrue(((rgb >= 0) & (rgb <= 255)).all())
        got = rc.srgb_to_oklch(rgb)
        self.assertAlmostEqual(float(got[0, 0]), float(lch[0, 0]), places=2)
        self.assertLess(abs((got[0, 2] - lch[0, 2] + 180) % 360 - 180), 1.5)


class TheTransform(unittest.TestCase):
    def test_identity_changes_nothing(self):
        px = red_field()[..., :3]
        np.testing.assert_array_equal(rc.Transform().apply(px), px)

    def test_each_control_moves_the_colour_its_way(self):
        red = np.array([[200, 40, 40]], np.uint8)
        before = rc.srgb_to_oklch(red.astype(float))[0]
        darker = rc.srgb_to_oklch(rc.Transform(lightness=0.7).apply(red).astype(float))[0]
        greyer = rc.srgb_to_oklch(rc.Transform(chroma=0.5).apply(red).astype(float))[0]
        magenta = rc.srgb_to_oklch(rc.Transform(hue=-40).apply(red).astype(float))[0]
        self.assertAlmostEqual(darker[0], before[0] * 0.7, places=2)
        self.assertAlmostEqual(greyer[1], before[1] * 0.5, places=2)
        self.assertAlmostEqual((magenta[2] - before[2]) % 360, 320, delta=1.0)
        self.assertGreater(rc.Transform(hue=-40).apply(red)[0, 2], 60)      # blue comes in

    def test_the_hue_window_spares_other_hues(self):
        t = rc.Transform(hue=-40, chroma=0.5, window=(25, 20, 10))
        yellow = np.array([[150, 140, 40]], np.uint8)
        np.testing.assert_array_equal(t.apply(yellow), yellow)
        self.assertFalse((t.apply(np.array([[200, 40, 40]], np.uint8)) == [[200, 40, 40]]).all())


class Textures(unittest.TestCase):
    def check_layout(self, before, after):
        self.assertEqual(len(before), len(after))
        hb, ha = ddt.read_header(before), ddt.read_header(after)
        self.assertEqual(before[:16 + 8 * hb.mips], after[:16 + 8 * ha.mips])    # header and level table

    def test_dxt1_keeps_its_header_and_every_level(self):
        before = ddt.write(red_field(), ddt.DXT1)
        after = rc.recolor_ddt(before, rc.Transform(hue=-10, chroma=0.8, lightness=0.66))
        self.check_layout(before, after)
        hd = ddt.read_header(after)
        for level in range(hd.mips):
            old, new = ddt.decode(before, level), ddt.decode(after, level)
            self.assertEqual(old.shape, new.shape)
            self.assertLess(new[..., :3].mean(), old[..., :3].mean(), level)       # darker on every level

    def test_the_mip_count_of_the_original_is_kept(self):
        # the game's terrain textures go down to 2 x 2 (9 levels for 512); the default writer stops at 4 x 4
        img = red_field(32)
        levels = ddt.mip_chain(img, smallest=2)
        blobs = [ddt.compress(lv, ddt.DXT1) for lv in levels]
        data = bytearray(ddt.MAGIC + bytes([0, 0, ddt.DXT1, len(blobs)]) + struct.pack("<II", 32, 32))
        off = 16 + 8 * len(blobs)
        for b in blobs:
            data += struct.pack("<II", off, len(b))
            off += len(b)
        for b in blobs:
            data += b
        after = rc.recolor_ddt(bytes(data), rc.Transform(chroma=0.5))
        self.check_layout(bytes(data), after)
        self.assertEqual(ddt.read_header(after).mips, 5)

    def test_dxt3_and_dxt5_keep_their_alpha_blocks(self):
        img = red_field()
        img[..., 3] = np.linspace(0, 255, img.shape[1]).astype(np.uint8)[None, :]
        for fmt in (ddt.DXT3, ddt.DXT5):
            before = ddt.write(img, fmt)
            after = rc.recolor_ddt(before, rc.Transform(hue=-30))
            self.check_layout(before, after)
            for off, size in ddt.read_header(before).levels:
                a = np.frombuffer(before, np.uint8, size, off).reshape(-1, 16)
                b = np.frombuffer(after, np.uint8, size, off).reshape(-1, 16)
                np.testing.assert_array_equal(a[:, :8], b[:, :8])

    def test_bgra_keeps_its_alpha_bytes(self):
        img = red_field(32)
        img[..., 3] = np.random.default_rng(5).integers(0, 256, img.shape[:2])
        before = ddt.write(img, ddt.BGRA, alpha=1)
        after = rc.recolor_ddt(before, rc.Transform(hue=-30, chroma=0.7))
        self.check_layout(before, after)
        for level in range(ddt.read_header(before).mips):
            np.testing.assert_array_equal(ddt.decode(before, level)[..., 3], ddt.decode(after, level)[..., 3])

    def test_grey_is_refused(self):
        g = bytearray(ddt.MAGIC + bytes([0, 0, ddt.GREY, 1]) + struct.pack("<IIII", 4, 4, 24, 16)) + bytes(16)
        with self.assertRaises(ddt.DdtError):
            rc.recolor_ddt(bytes(g), rc.Transform(hue=10))


class References(unittest.TestCase):
    def test_mix_weights_and_player_colours(self):
        with tempfile.TemporaryDirectory() as tmp:
            mix = os.path.join(tmp, "mix.xml")
            with open(mix, "w", encoding="utf-8") as fh:
                fh.write('<mix><paint><texture weight="2">a\\b\\grass1</texture>'
                         '<texture weight="4">a\\b\\Grass3</texture><texture>a\\b\\grass1</texture></paint></mix>')
            self.assertEqual(rc.read_mix(mix), {"grass1": 3.0, "grass3": 4.0})
            pc = os.path.join(tmp, "playercolors.xml")
            with open(pc, "w", encoding="utf-8") as fh:
                fh.write('<?xml version="1.0"?><playercolors><player num="0" color1="1 2 3" minimap="1 2 3"/>'
                         '<player num="2" color1="210 40 40" minimap="255 50 50"/>'
                         '<player num="1" color1="45 45 245" minimap="50 50 255 "/></playercolors>')
            colours = rc.read_player_colors(pc)
            self.assertEqual(list(colours), ["player 1", "player 2"])
            self.assertEqual(colours["player 2"], ((210, 40, 40), (255, 50, 50)))

    def test_measure(self):
        px = np.array([[210, 40, 40]] * 10 + [[20, 20, 200]] * 10, np.uint8)
        m = rc.measure(px, {"red": (210, 40, 40)}, 20)
        self.assertAlmostEqual(m["near"]["red"], 0.5)


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.src)
        with open(os.path.join(self.src, "grass.ddt"), "wb") as fh:
            fh.write(ddt.write(red_field(), ddt.DXT1))
        with open(os.path.join(self.src, "grass_b.ddt"), "wb") as fh:
            fh.write(ddt.write_normal_map(np.full((16, 16, 4), 128, np.uint8)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_the_textures_and_skips_bump_maps(self):
        out = os.path.join(self.tmp.name, "out")
        report = os.path.join(self.tmp.name, "report.json")
        r = run_tool(self.src, "--out", out, "--hue", "-10", "--chroma", "0.8", "--lightness", "0.66",
                     "--against", "p2=210,40,40", "--mapcolor", "160,15,30", "--report", report,
                     "--preview", os.path.join(self.tmp.name, "preview.png"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.listdir(out), ["grass.ddt"])
        self.assertIn("grass_b.ddt: skipped: bump map", r.stdout)
        import json
        with open(report, encoding="utf-8") as fh:
            data = json.load(fh)
        t = data["textures"][0]
        self.assertGreater(t["after"]["delta_e"]["p2"], t["before"]["delta_e"]["p2"])
        self.assertNotEqual(data["mapcolor"]["after"], data["mapcolor"]["before"])
        with open(os.path.join(self.tmp.name, "preview.png"), "rb") as fh:
            self.assertEqual(fh.read(4), b"\x89PNG")

    def test_a_dry_run_and_a_measure_write_no_texture(self):
        out = os.path.join(self.tmp.name, "out")
        r = run_tool(self.src, "--out", out, "--hue", "-10", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(out))
        r = run_tool(os.path.join(self.src, "grass.ddt"), "--against", "210,40,40")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dE2000", r.stdout)

    def test_it_refuses_to_overwrite_the_originals_or_write_into_steam(self):
        r = run_tool(self.src, "--out", self.src, "--hue", "-10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("overwrite", r.stderr)
        steam = os.path.join(self.tmp.name, "SteamLibrary", "steamapps", "common", "x")
        r = run_tool(self.src, "--out", steam, "--hue", "-10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Steam", r.stderr)
        self.assertFalse(os.path.exists(steam))


if __name__ == "__main__":
    unittest.main(verbosity=1)
