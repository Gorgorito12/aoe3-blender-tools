# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture survey on textures made here (no game, no mod): what each measure says, how a
texture is told own from stock, and that the profile names no file.

    venv\\Scripts\\python -I tests\\test_texture_survey.py
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import palette_survey  # noqa: E402
import texture_survey as ts  # noqa: E402
from aoe3game import ddt  # noqa: E402


def noise(side=64, seed=0, base=(150, 110, 80)):
    rng = np.random.default_rng(seed)
    rgb = np.clip(np.array(base) + rng.integers(-30, 31, (side, side, 3)), 0, 255)
    return np.dstack([rgb, np.full((side, side), 255)]).astype(np.uint8)


def ramp(side=64):
    x = np.linspace(20, 230, side)[None, :, None] * np.ones((side, 1, 3))
    return np.dstack([x, np.full((side, side), 255)]).astype(np.uint8)


def write(folder, rel, rgba, fmt=ddt.BGRA):
    path = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(ddt.write(rgba, fmt, alpha=1, usage=0, mips=True))
    return path


class Names(unittest.TestCase):
    def test_the_category_is_the_original_games_folder_however_deep(self):
        self.assertEqual(ts.category("art/units/spc/x.ddt"), "units")
        self.assertEqual(ts.category("art/SomeMod/buildings/a/b.ddt"), "buildings")
        self.assertEqual(ts.category("Art1.bar:Art\\nuggets\\x\\y.ddt"), "nuggets")
        self.assertEqual(ts.category("art/SomeMod/people/x.ddt"), "other")     # never the mod's name

    def test_the_role_comes_from_the_name_or_from_the_blue_of_a_normal_map(self):
        self.assertEqual(ts.role_of("art/units/a/musketeer.ddt", "units"), "diffuse")
        self.assertEqual(ts.role_of("art/units/a/musketeer_b.ddt", "units"), "bump")
        self.assertEqual(ts.role_of("art/units/a/musketeer_spec.ddt", "units"), "spec")
        self.assertEqual(ts.role_of("art/units/a/musketeer_icon.ddt", "units"), "ui")
        self.assertEqual(ts.role_of("art/buildings/a/house_ground.ddt", "buildings"), "decal")
        self.assertEqual(ts.role_of("art/units/a/odd.ddt", "units", mean=[128, 128, 250]), "bump")
        self.assertEqual(ts.role_of("art/terrain/a/x.ddt", "terrain"), "terrain")

    def test_the_material_is_what_the_name_says_or_nothing(self):
        self.assertEqual(ts.material_of("art/buildings/a/wood_planks.ddt"), "wood")
        self.assertEqual(ts.material_of("art/buildings/a/RoofTiles02.ddt"), "roof")
        self.assertEqual(ts.material_of("art/buildings/a/brick_wall.ddt"), "brick")
        self.assertEqual(ts.material_of("art/units/a/musketeer.ddt"), "")


class Measures(unittest.TestCase):
    def test_the_fast_blur_is_the_palette_surveys_blur(self):
        a = np.random.default_rng(1).random((40, 56)).astype(np.float32) * 255
        for r in (1, 4):
            self.assertLess(np.abs(ts.box_blur(a, r) - palette_survey.box_blur(a, r)).max(), 1e-2)

    def test_the_grain_is_the_palette_surveys_contrast(self):
        img = noise(64, seed=3)
        self.assertAlmostEqual(ts.measure(img)["grain"], palette_survey.measure(img)["contrast"], 3)

    def test_a_texture_that_tiles_and_one_that_does_not(self):
        self.assertLess(ts.measure(noise())["seam"], ts.SEAM_OK)
        self.assertGreater(ts.measure(ramp())["seam"], 3.0)

    def test_the_palette_finds_the_colours_and_their_shares(self):
        img = np.zeros((40, 40, 3), np.uint8)
        img[:, :30] = (200, 40, 40)
        img[:, 30:] = (40, 40, 200)
        pal = ts.palette(img, k=2)
        self.assertEqual([round(c[3], 2) for c in pal], [0.75, 0.25])
        self.assertEqual([int(v) for v in pal[0][:3]], [200, 40, 40])

    def test_the_alpha_shares(self):
        img = noise()
        img[:16, :, 3] = 0            # a quarter cut out
        img[16:32, :, 3] = 128        # a quarter in the owner's colour
        m = ts.measure(img)
        self.assertAlmostEqual(m["a_zero"], 0.25, 2)
        self.assertAlmostEqual(m["a_part"], 0.5, 2)

    def test_painted_light_shows_in_light_and_gradient(self):
        lit = noise().astype(np.float32)
        lit[:, :, :3] *= np.linspace(1.3, 0.5, 64)[:, None, None]
        lit = np.clip(lit, 0, 255).astype(np.uint8)
        flat, shaded = ts.measure(noise()), ts.measure(lit)
        self.assertGreater(shaded["light"], 3 * flat["light"])
        self.assertGreater(shaded["gradient"], 1.5)
        self.assertAlmostEqual(flat["gradient"], 1.0, 1)

    def test_the_same_texture_measures_the_same_twice(self):
        self.assertEqual(ts.measure(noise(seed=5), seed=9), ts.measure(noise(seed=5), seed=9))


class Survey(unittest.TestCase):
    def test_loose_textures_are_found_measured_and_told_own_from_stock(self):
        with tempfile.TemporaryDirectory() as mod, tempfile.TemporaryDirectory() as game:
            same, other = noise(seed=1), noise(seed=2)
            write(game, "art/buildings/house/house.ddt", same)
            write(game, "art/units/pike/pike.ddt", same)
            write(mod, "art/buildings/house/house.ddt", same)              # untouched: stock
            write(mod, "art/units/pike/pike.ddt", other)                   # repainted: changed
            write(mod, "art/SomeMod/buildings/fort/fort_wood.ddt", other)  # new: own... same bytes
            write(mod, "art/SomeMod/buildings/fort/fort_b.ddt", noise(seed=4, base=(128, 128, 250)))
            recs = {ts.norm(r["path"]): r for r in ts.survey([mod], [game])}
        self.assertEqual(len(recs), 4)
        self.assertEqual(recs["buildings\\house\\house.ddt"]["origin"], "stock")
        self.assertEqual(recs["units\\pike\\pike.ddt"]["origin"], "changed")
        fort = recs["somemod\\buildings\\fort\\fort_wood.ddt"]
        self.assertEqual((fort["origin"], fort["category"], fort["role"], fort["material"]),
                         ("own", "buildings", "diffuse", "wood"))
        self.assertEqual(recs["somemod\\buildings\\fort\\fort_b.ddt"]["role"], "bump")
        self.assertEqual((fort["w"], fort["h"], fort["format"]), (64, 64, ddt.BGRA))

    def test_a_file_that_is_not_a_texture_is_reported_and_does_not_stop_the_rest(self):
        with tempfile.TemporaryDirectory() as mod:
            write(mod, "art/units/a/a.ddt", noise())
            with open(os.path.join(mod, "art", "units", "a", "broken.ddt"), "wb") as fh:
                fh.write(b"not a texture")
            recs = ts.survey([mod])
        self.assertEqual(sum(1 for r in recs if "error" in r), 1)
        self.assertEqual(sum(1 for r in recs if "grain" in r), 1)
        self.assertEqual({r["origin"] for r in recs}, {"unknown"})


def records(n, origin="own", category="buildings", role="diffuse", material="wood", seed0=0):
    out = []
    for i in range(n):
        r = {"path": f"art\\SecretMod\\buildings\\thing{i}\\thing{i}_{material}.ddt", "md5": f"{seed0}-{i}",
             "w": 256, "h": 256, "format": ddt.DXT3, "alpha": 1, "mips": 7, "bytes": 1000,
             "origin": origin, "category": category, "role": role, "material": material}
        r.update(ts.measure(noise(seed=seed0 + i)))
        out.append(r)
    return out


class Use(unittest.TestCase):
    def test_a_texture_no_model_names_is_loose(self):
        rows = records(3)
        rows[0]["path"] = "art/buildings/fort/Fort_Wall.ddt"
        rows[1]["path"] = "art/buildings/fort/fort_icon_big.ddt"
        rows[2]["path"] = "art/buildings/fort/fort_wall_b.ddt"
        rows[2]["role"] = "bump"
        models = [{"tris": 120, "textures": ["fort_wall.ddt", "fort_wall_b.tga"]},
                  {"tris": 0, "textures": ["fort_icon_big.ddt"]}]          # an animation: no skin
        self.assertEqual(ts.mark_use(rows, models), 2)
        self.assertEqual([r["role"] for r in rows], ["diffuse", "loose", "bump"])
        self.assertEqual([r["worn"] for r in rows], [True, False, True])

    def test_the_blue_and_the_pink_of_a_normal_map(self):
        for mean in ([128, 128, 250], [25, 110, 250], [250, 150, 250]):
            self.assertEqual(ts.role_of("art/units/a/odd.ddt", "units", mean=mean), "bump", mean)
        self.assertEqual(ts.role_of("art/units/a/odd.ddt", "units", mean=[150, 140, 120]), "diffuse")


class Profile(unittest.TestCase):
    def test_it_names_no_file_and_no_folder(self):
        prof = ts.profile(records(12))
        text = json.dumps(prof)
        for leak in ("SecretMod", "thing", ".ddt", "\\\\", "/"):
            self.assertNotIn(leak, text.replace("9x9", "").replace("q25/50/75", ""), leak)
        self.assertTrue(prof["groups"])

    def test_a_small_group_is_left_out_so_no_number_points_at_one_file(self):
        prof = ts.profile(records(12) + records(3, material="stone", seed0=100))
        mats = {g["material"] for g in prof["groups"]}
        self.assertIn("wood", mats)
        self.assertNotIn("stone", mats)

    def test_copies_of_one_texture_count_once(self):
        rows = records(10)
        prof = ts.profile(rows + [dict(r) for r in rows])
        self.assertEqual((prof["textures"], prof["distinct"]), (20, 10))
        self.assertEqual(next(g for g in prof["groups"] if g["material"] == "wood")["count"], 10)

    def test_a_group_carries_its_quartiles_and_shares(self):
        g = next(g for g in ts.profile(records(12))["groups"]
                 if (g["category"], g["material"]) == ("buildings", "wood"))
        self.assertEqual(len(g["grain"]), 3)
        self.assertLessEqual(g["grain"][0], g["grain"][2])
        self.assertEqual(g["sizes"], [["256x256", 12]])
        self.assertEqual(g["tileable"], 1.0)
        self.assertEqual(g["formats"], {"DXT3": 12})

    def test_unread_textures_are_counted_by_reason(self):
        rows = records(9) + [{"path": "x", "error": "DdtError: format 3 is not decoded"}]
        self.assertEqual(ts.profile(rows)["unread"], {"DdtError: format 3 is not decoded": 1})


class Sheets(unittest.TestCase):
    def test_a_sheet_is_written_per_group_with_its_index(self):
        with tempfile.TemporaryDirectory() as mod, tempfile.TemporaryDirectory() as out:
            for i in range(9):
                write(mod, f"art/buildings/b{i}/b{i}_wood.ddt", noise(seed=i))
            written = ts.sheets(ts.survey([mod]), out, cell=32, cols=4, rows=3)
            self.assertEqual([os.path.basename(p) for p in written], ["unknown_buildings_diffuse_wood.png"])
            self.assertTrue(os.path.exists(written[0][:-4] + ".txt"))
            from core.pngio import read_png
            with open(written[0], "rb") as fh:
                self.assertEqual(read_png(fh.read()).shape[:2], (96, 128))


if __name__ == "__main__":
    unittest.main(verbosity=2)
