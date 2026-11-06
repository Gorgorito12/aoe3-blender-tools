# SPDX-License-Identifier: GPL-3.0-or-later
"""Every building has its technical sheet, and the sheet is what the model is today.

    venv\\Scripts\\python -I tests\\test_specs.py

After changing a building: venv\\Scripts\\python -I tools\\spec_sheets.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import spec_sheets  # noqa: E402
from core import building, profile, specs  # noqa: E402

PROTO = """<proto><Unit id="1" name="Keep"><MaxHitpoints>900.0000</MaxHitpoints><LOS>20.0000</LOS>
<Cost resourcetype="Wood">300.0000</Cost><Cost resourcetype="Gold">50.0000</Cost><Train row="0">A</Train>
<Flag>SelectWithObstruction</Flag><Flag>Tracked</Flag></Unit><Unit id="2" name="Other"><LOS>9</LOS></Unit></proto>"""


class Sheets(unittest.TestCase):
    def test_every_preset_has_its_sheet_and_it_is_current(self):
        prof = profile.load()
        for key, params in building.PRESETS.items():
            with self.subTest(key=key):
                path = os.path.join(spec_sheets.OUT, params.name + ".md")
                self.assertTrue(os.path.exists(path), "no sheet: run tools/spec_sheets.py")
                with open(path, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), spec_sheets.sheet(key, prof)[0], "old sheet: run tools/spec_sheets.py")

    def test_the_index_names_every_building(self):
        with open(os.path.join(spec_sheets.OUT, "README.md"), encoding="utf-8") as fh:
            text = fh.read()
        for params in building.PRESETS.values():
            self.assertIn(f"[{params.name}]({params.name}.md)", text)

    def test_a_sheet_has_every_section(self):
        text = spec_sheets.sheet("AFRICAN_PALACE_SAHEL")[0]
        for title in ("## Size", "## Triangles", "## Texture", "## Collision and footprint", "## Shape against"):
            self.assertIn(title, text)
        self.assertNotIn("## Game data", text)              # the game's numbers stay out of the repository

    def test_the_palaces_textures_stay_under_3_mb(self):
        f = spec_sheets.sheet("AFRICAN_PALACE_SAHEL")[1]
        self.assertEqual((f["texture"], f["bump"], f["painted"]), (1024, 512, 2048))
        self.assertLess(f["texture_mb"], 3.0)

    def test_the_numbers_are_the_models(self):
        f = spec_sheets.sheet("AFRICAN_PALACE_SAHEL")[1]
        self.assertEqual(sum(c for _, c in f["parts"]), f["tris"])
        self.assertGreater(f["tris"], 2 * f["tris_low"])


class Proto(unittest.TestCase):
    def test_a_unit_is_read_from_the_game_data(self):
        p = specs.proto_of(PROTO, "Keep")
        self.assertEqual(p["hit points"], "900.0000")
        self.assertEqual(p["cost"], [("Wood", "300.0000"), ("Gold", "50.0000")])
        self.assertEqual(p["trains"], 1)

    def test_a_unit_without_an_entry_takes_its_template(self):
        self.assertEqual(specs.proto_of(PROTO, "New", "Other")["source"], "Other")
        self.assertIsNone(specs.proto_of(PROTO, "New"))

    def test_the_tool_refuses_game_numbers_in_the_repository(self):
        with self.assertRaises(SystemExit):
            spec_sheets.main(["--proto", "x.xml"])


if __name__ == "__main__":
    unittest.main()
