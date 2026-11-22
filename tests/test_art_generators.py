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
        drawn = [m for m, (_, icon) in make_rings.MARKERS.items() if icon in make_rings.CARTOON_DRAWN]
        for marker in drawn:
            self.assertIn(f"aura_{marker}.xml", names)
            self.assertIn(f"icon_{marker}.ddt", names)
        for marker in set(make_rings.MARKERS) - set(drawn):  # only a drawn sheet has their icons
            self.assertNotIn(f"aura_{marker}.xml", names)
        self.assertEqual(len(names), 319)

    def test_markers_show_their_ring_and_their_own_icon(self):
        for marker, (ring, _) in make_rings.MARKERS.items():
            if f"aura_{marker}.xml" not in self.files:
                continue
            text = self.files[f"aura_{marker}.xml"].decode("utf-8")
            self.assertIn(f"effects\\myrings\\ring_{ring}_unit.particle", text, marker)
            self.assertIn(f"effects\\myrings\\icon_{marker}_unit.particle", text, marker)

    @unittest.skipIf(np is None, "numpy not available")
    def test_cartoon_icons_are_flat_and_outlined(self):
        """Each marker icon is uncompressed, transparent at its corners, has a dark outline and some bright colour."""
        for marker in make_rings.MARKERS:
            if f"icon_{marker}.ddt" not in self.files:
                continue
            data = self.files[f"icon_{marker}.ddt"]
            hd = ddt.read_header(data)
            self.assertEqual(hd.format, ddt.BGRA, marker)
            self.assertEqual(hd.width, make_rings.CARTOON_SIZE, marker)
            px = ddt.decode(data).astype(int)
            for y, x in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
                self.assertEqual(px[y, x, 3], 0, marker)
            solid = px[px[..., 3] == 255]
            self.assertGreater(len(solid), 0.15 * px.shape[0] * px.shape[1], marker)
            dark = (solid[:, :3].max(axis=1) < 60).mean()
            self.assertGreater(dark, 0.10, marker)          # the outline
            self.assertGreater(solid[:, :3].max(), 200, marker)

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
        cartoons = {f"icon_{marker}.ddt" for marker in make_rings.MARKERS}
        for name, data in self.files.items():
            if name.endswith(".ddt") and name not in cartoons:
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

    def test_range_ring_particle_is_as_wide_as_the_ring(self):
        """The game draws a flat particle `scale` metres wide in all (measured in game: the scale was once the half
        width, and every range ring showed half its radius), so a ring of r metres has its rim at r."""
        import re
        for radius in make_rings.RANGES:
            text = self.files[f"range_{radius}.particle"].decode("utf-8")
            scale = float(re.search(r"<scale>([0-9.]+)</scale>", text)[1])
            self.assertAlmostEqual(scale / 2 * make_rings.BANDS[0][1], radius, delta=0.002, msg=radius)

    @unittest.skipIf(np is None, "numpy not available")
    def test_range_ring_line_ends_at_its_radius(self):
        """The line's outer edge, read from the texture and the particle's width, is at the ring's radius."""
        import re
        for radius in (4, 12, 30, 100):
            text = self.files[f"range_{radius}.particle"].decode("utf-8")
            scale = float(re.search(r"<scale>([0-9.]+)</scale>", text)[1])
            px = ddt.decode(self.files[f"range_{radius}.ddt"])
            side = px.shape[0]
            row = px[side // 2, side // 2:, 3].astype(int)       # from the centre to the right edge
            solid = np.nonzero(row >= row.max() // 2)[0]
            outer = (solid.max() + 1) / (side / 2) * scale / 2     # metres from the centre
            texel = scale / side
            self.assertLess(abs(outer - radius), 2 * texel, (radius, outer))
            inner = solid.min() / (side / 2) * scale / 2
            line = max(make_rings.RANGE_LINE, make_rings.RANGE_LINE_PER_METRE * radius)
            self.assertLess(abs((outer - inner) - line), 2 * texel, (radius, outer - inner))

    def test_rank_knots_are_symmetric_and_keep_their_place(self):
        """Every knot is symmetric left to right, stays in its sprite, and ends at the same lowest height in the
        game (its tails), which keeps the HP bar clear; ranks 4 and 5 are larger sprites around the same centre."""
        lows = []
        for rank in range(1, 6):
            glyph, scale = make_rings.rank_mark(rank)
            self.assertGreaterEqual(scale, 1.0, rank)  # rank 1 fits the sprite; a larger knot gets a larger sprite
            self.assertGreater(scale, 1.0, rank)  # the sprite holds the knot over its centre (the bar)
            for x, y, r, _ in glyph:  # each circle has its mirror image
                self.assertTrue(any(abs(x + x2) < 1e-6 and abs(y - y2) < 1e-6 and abs(r - r2) < 1e-9
                                    for x2, y2, r2, _ in glyph), (rank, x, y))
            reach = max(max(abs(x), abs(y)) + r for x, y, r, _ in glyph) + make_rings.KNOT_OUTLINE / scale
            self.assertLessEqual(reach, 1.0, rank)
            lows.append(max(y + r for x, y, r, _ in glyph) * scale)  # in ranks 1 to 3's sprite units
        self.assertAlmostEqual(min(lows), max(lows), places=2)
        self.assertAlmostEqual(max(lows), -make_rings.RANK_TAIL_LIFT, places=6)  # the tails over the bar's height
        self.assertFalse(hasattr(make_rings, "RANK_STARS"))  # no stars any more

    @unittest.skipIf(np is None, "numpy not available")
    def test_rank_marks_differ_have_loops_and_shine(self):
        """The loops show (texels not of the cord's colour closed in by it on four sides), ranks differ in shape, the
        colours are bronze, silver and gold, and the cord is shaded: lighter texels and darker ones of one hue."""
        masks = []
        for rank, colour in sorted(make_rings.RANKS.items()):  # the base tones sampled from the approved sheet
            px = ddt.decode(self.files[f"icon_rank_{rank}.ddt"]).astype(int)
            cord = (px[..., 3] == 255) & (px[..., :3].sum(axis=2) > 200)
            masks.append(cord)
            body = px[cord][:, :3]
            self.assertTrue((abs(np.median(body, axis=0) - colour) < 40).all(), (rank, np.median(body, axis=0)))
            luma = body.sum(axis=1)
            self.assertGreater(np.percentile(luma, 90) - np.percentile(luma, 10), 60, rank)  # the shine
            left = np.maximum.accumulate(cord, axis=1)
            right = np.maximum.accumulate(cord[:, ::-1], axis=1)[:, ::-1]
            up = np.maximum.accumulate(cord, axis=0)
            down = np.maximum.accumulate(cord[::-1], axis=0)[::-1]
            holes = int((~cord & left & right & up & down).sum())
            self.assertGreater(holes, 20, rank)
            self.assertGreater((cord == cord[:, ::-1]).mean(), 0.95, rank)  # symmetric
        for a in range(5):
            for b in range(a + 1, 5):
                self.assertGreater((masks[a] != masks[b]).sum(), 60, (a + 1, b + 1))
        bronze = ddt.decode(self.files["icon_rank_1.ddt"]).astype(int)
        shown = bronze[(bronze[..., 3] == 255) & (bronze[..., :3].sum(axis=2) > 200)][:, :3]
        self.assertTrue(0.5 < np.median(shown[:, 1]) / np.median(shown[:, 0]) < 0.72)  # copper-bronze, as approved

    @unittest.skipIf(np is None, "numpy not available")
    def test_rank_marks_are_centred_on_the_bar(self):
        """Rule: a mark over a unit is horizontally centred on the unit's HP bar. The sprite hangs centred on the unit,
        so the knot must sit on the texture's vertical centre line: its bounding box and its alpha-weighted centre."""
        for rank in range(1, 6):
            px = ddt.decode(self.files[f"icon_rank_{rank}.ddt"]).astype(float)
            alpha = px[..., 3]
            n = alpha.shape[1]
            cols = np.nonzero(alpha.max(axis=0) > 0)[0]
            self.assertEqual(cols.min(), n - 1 - cols.max(), rank)  # as much room on the left as on the right
            centre = (alpha.sum(axis=0) * (np.arange(n) + 0.5)).sum() / alpha.sum()
            self.assertAlmostEqual(centre, n / 2, delta=0.05, msg=rank)
            rows = np.nonzero(alpha.max(axis=1) > 0)[0]
            self.assertLess(rows.max(), n / 2, rank)  # the knot over the sprite's centre, which is at the bar
        for name, data in self.files.items():
            if name.startswith("icon_rank_") and name.endswith(".particle"):
                height = float(data.decode().split("<centerheight>")[1].split("<")[0])
                kind = name[:-len(".particle")].split("_")[-1]
                if kind in make_rings.RANK_BAR_HEIGHTS:
                    self.assertAlmostEqual(height, make_rings.RANK_BAR_HEIGHTS[kind], places=3, msg=name)

    def test_bad_folder_is_refused(self):
        self.assertNotEqual(run_tool("make_rings.py", "--folder", "a\\b", "--check").returncode, 0)

    @unittest.skipIf(np is None, "numpy not available")
    def test_rank_marks_from_drawn_images(self):
        """--rank-shapes: drawn marks (synthetic here: rings of growing height on a stem, symmetric) placed by the
        same rules as the knots: centred on the HP bar (bounding box and alpha centroid), their lowest pixel at the
        same height over the bar for every rank, a larger drawing in a larger sprite."""
        import json
        from core.pngio import encode_png
        with tempfile.TemporaryDirectory() as tmp:
            for rank in range(1, 6):
                h, w = 120 + 30 * rank, 160
                yy, xx = np.mgrid[0:h, 0:w]
                ring = np.abs(np.hypot(xx - 79.5, yy - 50) - 35) < 10
                stem = (np.abs(xx - 79.5) < 6) & (yy > 80)
                bar = (np.abs(yy - (h - 12)) < 8) & (np.abs(xx - 79.5) < 70)
                rgba = np.zeros((h, w, 4), np.uint8)
                rgba[ring | stem | bar] = (230, 180, 40, 255)
                with open(os.path.join(tmp, f"rank_{rank}.png"), "wb") as f:
                    f.write(encode_png(rgba))
            with open(os.path.join(tmp, "shapes.json"), "w") as f:
                json.dump({"pixels_per_unit": 100}, f)
            make_rings.RANK_SHAPES = tmp
            make_rings._image_placement.cache_clear()
            make_rings.rank_ddt.cache_clear()
            try:
                lows, scales = [], []
                for rank in range(1, 6):
                    px = ddt.decode(make_rings.rank_ddt(rank)).astype(float)
                    alpha = px[..., 3]
                    n = alpha.shape[1]
                    self.assertEqual(n, make_rings.RANK_SHAPE_TEXTURE)
                    cols = np.nonzero(alpha.max(axis=0) > 0)[0]
                    self.assertLessEqual(abs(cols.min() - (n - 1 - cols.max())), 1, rank)
                    centre = (alpha.sum(axis=0) * (np.arange(n) + 0.5)).sum() / alpha.sum()
                    self.assertAlmostEqual(centre, n / 2, delta=0.5, msg=rank)
                    scale = make_rings.rank_scale(rank)
                    rows = np.nonzero(alpha.max(axis=1) > 127)[0]
                    lows.append((n / 2 - (rows.max() + 1)) / (n / 2) * scale)  # glyph units over the centre
                    scales.append(scale)
                for low in lows:
                    self.assertAlmostEqual(low, make_rings.RANK_TAIL_LIFT, delta=0.05)
                self.assertEqual(scales, sorted(scales))  # taller drawings, larger sprites
            finally:
                make_rings.RANK_SHAPES = None
                make_rings._image_placement.cache_clear()
                make_rings.rank_ddt.cache_clear()

    def test_command_line_check(self):
        """One run of the tool (about 40 s: every texture is drawn in plain Python)."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in self.files.items():
                with open(os.path.join(tmp, name), "wb") as f:
                    f.write(data)
            result = run_tool("make_rings.py", "--out", tmp, "--folder", "myrings", "--check")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("319 files, 0 differ", result.stdout)

    @unittest.skipIf(np is None, "numpy not available")
    def test_icons_from_a_drawn_sheet(self):
        """--icon-sheet: a 3 x 3 sheet on white (synthetic: a dark-outlined coloured square with a white middle in each
        cell, of a size by cell). Every marker gets its icon, the ground is transparent, the icon's own white stays
        opaque, every icon is centred and drawn at one scale (the largest one's side SHEET_FILL of the texture)."""
        from core.pngio import encode_png
        cell = 90
        sheet = np.full((3 * cell, 3 * cell, 3), 255, np.uint8)
        sides = {}
        for name, (r, c) in make_rings.SHEET_CELLS.items():
            side = 30 + 4 * (3 * r + c)
            sides[name] = side
            y0, x0 = r * cell + (cell - side) // 2, c * cell + (cell - side) // 2
            sheet[y0:y0 + side, x0:x0 + side] = (20, 16, 12)                # the outline
            sheet[y0 + 4:y0 + side - 4, x0 + 4:x0 + side - 4] = (40 * r, 200, 60 * c)
            m = side // 2
            sheet[y0 + m - 3:y0 + m + 3, x0 + m - 3:x0 + m + 3] = 255       # its own white
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sheet.png")
            with open(path, "wb") as f:
                f.write(encode_png(sheet))
            make_rings.ICON_SHEET = path
            make_rings._sheet_icons.cache_clear()
            make_rings.cartoon_ddt.cache_clear()
            try:
                files = make_rings.wanted_files("myrings")
                size = make_rings.CARTOON_SIZE
                largest = max(sides.values())
                for marker, (ring, icon) in make_rings.MARKERS.items():
                    self.assertIn(f"aura_{marker}.xml", files)
                    self.assertIn(f"effects\\myrings\\ring_{ring}_unit.particle",
                                  files[f"aura_{marker}.xml"].decode("utf-8"))
                    px = ddt.decode(files[f"icon_{marker}.ddt"]).astype(int)
                    self.assertEqual(ddt.read_header(files[f"icon_{marker}.ddt"]).format, ddt.BGRA)
                    a = px[..., 3]
                    self.assertEqual(a[0, 0], 0, marker)
                    self.assertEqual(a[size // 2, size // 2], 255, marker)           # the white middle stays
                    self.assertGreater(px[size // 2, size // 2, :3].min(), 200, marker)
                    rows = np.nonzero(a.max(axis=1) > 127)[0]
                    cols = np.nonzero(a.max(axis=0) > 127)[0]
                    self.assertLessEqual(abs(cols.min() - (size - 1 - cols.max())), 2, marker)
                    self.assertLessEqual(abs(rows.min() - (size - 1 - rows.max())), 2, marker)
                    want = sides[icon] / largest * make_rings.SHEET_FILL * size
                    self.assertAlmostEqual(cols.max() + 1 - cols.min(), want, delta=2.5, msg=marker)
                self.assertEqual(files["icon_food.ddt"], files["icon_hunt.ddt"])  # meat for both
            finally:
                make_rings.ICON_SHEET = None
                make_rings._sheet_icons.cache_clear()
                make_rings.cartoon_ddt.cache_clear()

    def test_range_rings_in_player_colours(self):
        """--player-colours: range_<N>_p<k> for every player of RANGE_PLAYERS, the same texture, the particle tinted."""
        make_rings.PLAYER_COLOURS = True
        try:
            files = make_rings.wanted_files("myrings")
        finally:
            make_rings.PLAYER_COLOURS = False
        for radius in make_rings.RANGES:
            for k, (r, g, b) in enumerate(make_rings.RANGE_PLAYERS):
                text = files[f"range_{radius}_p{k}.particle"].decode("utf-8")
                self.assertIn(f"<color>{r << 16 | g << 8 | b}</color>", text)
                self.assertIn(f"effects\\myrings\\range_{radius}</file>", text)
                self.assertIn(f"range_{radius}_p{k}.particle", files[f"range_{radius}_p{k}.xml"].decode("utf-8"))
        self.assertIn("<color>16777215</color>", files["range_12.particle"].decode("utf-8"))


class AuraRings(unittest.TestCase):
    """make_aura_rings.py without the game: the recolouring and the model files it names (synthetic texels)."""

    @unittest.skipIf(np is None, "numpy not available")
    def test_recolour_keeps_alpha_and_takes_the_ring_colour(self):
        import make_aura_rings
        rgba = np.zeros((4, 4, 4), np.uint8)
        rgba[0, 0] = (200, 220, 40, 255)   # the stock gradient's yellow-green end
        rgba[1, 1] = (20, 170, 140, 255)   # its teal end
        rgba[2, 2] = (30, 30, 30, 0)       # transparent: untouched
        main, light = make_rings.RINGS["damage"]
        out = make_aura_rings.recolour(rgba, (main, light)).astype(int)
        self.assertTrue((out[..., 3] == rgba[..., 3]).all())
        self.assertTrue((out[2, 2] == rgba[2, 2]).all())
        hue = lambda c: __import__("colorsys").rgb_to_hsv(*(np.array(c[:3]) / 255))[0]
        for texel in (out[0, 0], out[1, 1]):  # magenta, whatever the stock hue
            self.assertLess(min(abs(hue(texel) - hue(main)), 1 - abs(hue(texel) - hue(main))), 0.06)

    @unittest.skipIf(np is None, "numpy not available")
    def test_anti_rings(self):
        """Each variant reads as adverse on a synthetic ring like the stock one (an outer band and an inner line):
        dash leaves gaps around it, teeth add texels inside the outer band, hatch cuts the band and darkens it."""
        import make_aura_rings
        n = 64
        yy, xx = np.mgrid[0:n, 0:n]
        r = np.hypot((xx + 0.5) / n * 2 - 1, (yy + 0.5) / n * 2 - 1)
        rgba = np.zeros((n, n, 4), np.uint8)
        ring = ((r > 0.8) & (r < 0.97)) | ((r > 0.56) & (r < 0.64))
        rgba[ring] = (200, 60, 160, 255)
        colours = make_rings.RINGS["damage"]
        shown = (rgba[..., 3] > 0).sum()
        dash = make_aura_rings.anti_level(rgba, colours, "dash")
        self.assertLess((dash[..., 3] > 0).sum(), 0.8 * shown)
        teeth = make_aura_rings.anti_level(rgba, colours, "teeth")
        between = (r > 0.66) & (r < 0.78)
        self.assertEqual((rgba[..., 3][between] > 0).sum(), 0)
        self.assertGreater((teeth[..., 3][between] > 0).sum(), 20)
        hatch = make_aura_rings.anti_level(rgba, colours, "hatch")
        self.assertLess((hatch[..., 3] > 0).sum(), shown)
        kept = hatch[..., 3] > 0
        self.assertLess(hatch[kept][:, :3].max(axis=1).mean(), rgba[kept][:, :3].max(axis=1).mean())
        self.assertEqual(set(make_aura_rings.NEGATIVE) - set(make_rings.RINGS), set())

    def test_models_by_size(self):
        import make_aura_rings
        make_rings.FOLDER = "myrings"
        text = make_rings.xml("wood", logic=make_aura_rings.mesh_logic("wood"))
        for branch, size, _, _ in make_rings.SHAPES:
            self.assertIn(f"<{branch}>", text)
            self.assertIn(f"effects\\myrings\\auraring_wood_{size}</file>", text)
        self.assertIn('type="GrannyModel"', text)
        self.assertNotIn("replacetexture", text)


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
