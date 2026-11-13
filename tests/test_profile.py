# SPDX-License-Identifier: GPL-3.0-or-later
"""The profiles shipped with the add-on: that they load, answer for a kind of art, and name no
file of the mod they were measured on.

    python -I tests/test_profile.py
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import profile  # noqa: E402

FOLDER = os.path.join(ROOT, "aoe3_blender_tools", "profiles")
STOCK_FOLDERS = {"units", "buildings", "buildingsets", "homecity", "terrain", "effects", "ui",
                 "nuggets", "objects", "animation_library", "shadows_selections", "cinematic",
                 "lightsets", "cursors", "impacts", "lighting", "other", "*"}


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


class Shipped(unittest.TestCase):
    def test_no_profile_names_a_file_or_a_folder_of_the_mod(self):
        for name in sorted(os.listdir(FOLDER)):
            with open(os.path.join(FOLDER, name), encoding="utf-8") as fh:
                data = json.load(fh)
            for s in strings(data):
                if s in ("buildinglarge.xml", "buildingsmall.xml"):      # the original game's own
                    continue
                self.assertIsNone(re.search(r"\.(ddt|gr2|xml|xmb|bar|tga|png)\b", s, re.I), (name, s))
                self.assertNotIn(":\\", s, (name, s))
            for g in data.get("groups", []):                    # groupings.json groups by kind, not folder
                self.assertIn(g.get("category", "*"), STOCK_FOLDERS, (name, g.get("category")))
                self.assertGreaterEqual(g.get("count", g.get("files", 0)), 8, name)   # never one file's numbers

    def test_the_texture_profile_answers_for_a_kind_of_art(self):
        art = profile.art("textures")
        self.assertIsNotNone(art)
        own = art.group("own", "buildings", "diffuse", "*")
        stock = art.group("stock", "buildings", "diffuse", "*")
        for g in (own, stock):
            for key in ("grain", "saturation", "luminance", "light"):
                self.assertEqual(len(g[key]), 3, key)
                self.assertLessEqual(g[key][0], g[key][2], key)
        self.assertLess(own["grain"][1], stock["grain"][1])       # the finding the fit rests on

    def test_nearest_falls_back_from_the_material_to_the_category_to_the_stock_art(self):
        art = profile.art("textures")
        g, what = art.nearest("buildings", "diffuse", "no such material")
        self.assertEqual(what, "own buildings")
        g, what = art.nearest("nuggets", "diffuse")
        self.assertTrue(what.startswith(("own", "stock")), what)
        self.assertEqual(art.nearest("no such folder", "no such role"), (None, None))

    def test_the_model_profile_gives_a_prop_its_budget(self):
        objects, treasures = profile.prop_group("objects"), profile.prop_group("nuggets")
        self.assertEqual((objects["origin"], objects["category"]), ("stock", "objects"))
        self.assertEqual(treasures["category"], "nuggets")
        self.assertLess(objects["tris"][1], treasures["tris"][1])
        settled = [g for g in profile.art("groupings").groups if g["kind"] == "settlement"]
        self.assertTrue(settled and all(len(g["clear"]) == 3 for g in settled))
        units = profile.art("models").group("own", "units")
        self.assertIn("animations", profile.art("models").group("stock", "animation_library"))
        self.assertGreater(units["bones"][1], 10)

    def test_a_missing_profile_is_none(self):
        self.assertIsNone(profile.art("no such profile"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
