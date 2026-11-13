# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture library: what is written beside a made texture, and how one is put under the
painter's drawing in place of a swatch that ships with the add-on.

    venv\\Scripts\\python -I tests\\test_texlib.py
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import materials, texlib  # noqa: E402


def swatch(side=32, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(60, 200, (side, side, 3)).astype(np.uint8)


class Saving(unittest.TestCase):
    def test_the_texture_its_sidecar_and_its_sheet_are_written(self):
        with tempfile.TemporaryDirectory() as d:
            entry = texlib.save(swatch(), "factory_roof", folder=d, licence="my own photograph",
                                tile_m=2.5, role="roof", style="colonial",
                                report={"mode": "photo+ai", "prompt": "rusted iron", "seed": 3,
                                        "seam": 1.1},
                                source="photos/factory.jpg", strength=0.6)
            self.assertEqual(sorted(os.listdir(d)),
                             ["factory_roof.json", "factory_roof.png", "factory_roof_x3.png"])
            with open(os.path.join(d, "factory_roof.json"), encoding="utf-8") as f:
                side = json.load(f)
        self.assertEqual(side["licence"], "my own photograph")
        self.assertEqual((side["style"], side["role"], side["tile_m"]), ("COLONIAL", "roof", 2.5))
        self.assertEqual((side["mode"], side["prompt"], side["seed"], side["seam"]),
                         ("photo+ai", "rusted iron", 3, 1.1))
        self.assertEqual(side["source"], "photos/factory.jpg")
        self.assertEqual(entry["size"], 32)
        self.assertEqual(sorted(side), sorted(texlib.FIELDS))

    def test_a_texture_without_a_licence_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("", "   "):
                with self.assertRaises(ValueError):
                    texlib.save(swatch(), "x", folder=d, licence=bad)
            self.assertEqual(os.listdir(d), [])

    def test_a_name_that_is_a_path_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                texlib.save(swatch(), "../escape", folder=d, licence="mine")

    def test_the_sheet_is_the_texture_three_by_three(self):
        with tempfile.TemporaryDirectory() as d:
            img = swatch(16)
            texlib.save(img, "t", folder=d, licence="mine")
            sheet = texlib.image("t_x3", folder=d)
        self.assertEqual(sheet.shape, (48, 48, 3))
        self.assertTrue((sheet[16:32, 16:32] == img).all())


class Reading(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            img = swatch(64, seed=2)
            texlib.save(img, "mud", folder=d, licence="generated locally", sheet=False)
            self.assertTrue((texlib.image("mud", folder=d) == img).all())
            self.assertEqual(texlib.read("mud", folder=d)["name"], "mud")
            self.assertIsNone(texlib.read("nothing", folder=d))
            self.assertIsNone(texlib.image("nothing", folder=d))

    def test_the_index_lists_the_textures_and_not_their_sheets(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "a", folder=d, licence="mine")
            texlib.save(swatch(seed=1), "b", folder=d, licence="mine")
            self.assertEqual(sorted(texlib.index(d)), ["a", "b"])

    def test_a_texture_dropped_in_by_hand_is_still_listed(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "a", folder=d, licence="mine", sheet=False)
            os.remove(os.path.join(d, "a.json"))
            self.assertEqual(texlib.index(d)["a"]["licence"], "unknown")

    def test_an_empty_or_missing_folder_is_no_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(texlib.index(d), {})
            self.assertEqual(texlib.index(os.path.join(d, "nothing")), {})

    def test_delete_takes_the_sidecar_and_the_sheet_too(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "a", folder=d, licence="mine")
            texlib.delete("a", folder=d)
            self.assertEqual(os.listdir(d), [])


class Installing(unittest.TestCase):
    def tearDown(self):
        texlib.uninstall()

    def test_a_texture_replaces_the_swatch_of_its_style_and_role(self):
        before = materials.MATERIALS["COLONIAL"]["roof"]
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(64), "factory_roof", folder=d, licence="mine", tile_m=1.8,
                        role="roof", style="COLONIAL", sheet=False)
            chosen = texlib.install(folder=d)
            self.assertEqual(chosen, {("COLONIAL", "roof"): "factory_roof"})
            plan = materials.plan("COLONIAL")
            name, tile_m, key, contrast, _grain = plan["roof"]
            self.assertEqual(os.path.basename(name), "factory_roof")
            self.assertEqual(tile_m, 1.8)
            self.assertEqual((key, contrast), (before[2], before[3]))   # colour and grain kept
            img = materials.load(name)                                  # found by its full path
            self.assertIsNotNone(img)
            self.assertEqual(img.shape, (64, 64, 3))
        texlib.uninstall()
        self.assertEqual(materials.MATERIALS["COLONIAL"]["roof"], before)

    def test_a_role_the_style_did_not_have_takes_the_standard_grain(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "cobbles", folder=d, licence="mine", role="paving",
                        style="COLONIAL", sheet=False)
            texlib.install(folder=d)
            self.assertEqual(materials.plan("COLONIAL")["paving"][3], materials.TARGET_CONTRAST)
        texlib.uninstall()
        self.assertNotIn("paving", materials.MATERIALS["COLONIAL"])

    def test_a_texture_without_a_style_or_a_role_is_left_in_the_library(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "loose", folder=d, licence="mine", sheet=False)
            self.assertEqual(texlib.install(folder=d), {})

    def test_only_the_styles_or_names_asked_for(self):
        with tempfile.TemporaryDirectory() as d:
            texlib.save(swatch(), "a", folder=d, licence="mine", role="roof", style="COLONIAL",
                        sheet=False)
            texlib.save(swatch(seed=1), "b", folder=d, licence="mine", role="roof", style="TIMBER",
                        sheet=False)
            self.assertEqual(texlib.install(folder=d, styles=["timber"]), {("TIMBER", "roof"): "b"})
            texlib.uninstall()
            self.assertEqual(texlib.install(folder=d, names=["a"]), {("COLONIAL", "roof"): "a"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
