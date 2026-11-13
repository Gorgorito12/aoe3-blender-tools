# SPDX-License-Identifier: GPL-3.0-or-later
"""Repainting a texture of a mesh the generator did not make: UV zones become regions, each with
its own prompt, and the repaint runs against a stand-in ComfyUI (no GPU).

    venv\Scripts\python -I tests\test_meshtex.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import airepaint, comfy, meshtex  # noqa: E402
from fake_comfy import FakeComfy  # noqa: E402

SIZE = 512


def texture():
    """A plain texture with two halves, as an outside model's might be: roof above, walls below."""
    tex = np.zeros((SIZE, SIZE, 4), np.uint8)
    tex[:, :, 3] = 255
    tex[:SIZE // 2] = (150, 60, 50, 255)
    tex[SIZE // 2:] = (210, 200, 180, 255)
    return tex


def grainy(rgb):
    """What a repaint does: grain and a colour drift (the drift is put back by the repaint, the
    grain is what shows the region was touched)."""
    rng = np.random.default_rng(int(rgb.sum()) % 1000)
    out = rgb.astype(np.int32) + rng.integers(-20, 21, rgb.shape) + np.array([12, -6, 4])
    return np.clip(out, 0, 255).astype(np.uint8)


ZONES = [("roof", 0.0, 0.5, 1.0, 1.0), ("walls", 0.0, 0.0, 1.0, 0.5)]


class Zones(unittest.TestCase):
    def test_uv_zones_become_pixel_regions_with_the_top_row_first(self):
        regions, dropped = meshtex.zone_regions(ZONES, SIZE, margin=0)
        self.assertEqual(dropped, [])
        by = {r.name: r for r in regions}
        self.assertEqual((by["roof"].x, by["roof"].y, by["roof"].w, by["roof"].h), (0, 0, SIZE, SIZE // 2))
        self.assertEqual((by["walls"].x, by["walls"].y), (0, SIZE // 2))

    def test_a_zone_thinner_than_the_smallest_repaint_is_dropped(self):
        zones = ZONES + [("trim", 0.0, 0.0, 1.0, 0.01)]
        regions, dropped = meshtex.zone_regions(zones, SIZE, margin=0)
        self.assertEqual([n for n, _, _ in dropped], ["trim"])
        self.assertEqual(sorted(r.name for r in regions), ["roof", "walls"])

    def test_every_zone_dropped_is_an_error_naming_the_sizes(self):
        with self.assertRaises(ValueError) as e:
            meshtex.model_for([("trim", 0.0, 0.0, 1.0, 0.01)], SIZE)
        self.assertIn("trim", str(e.exception))

    def test_no_zones_means_the_whole_image(self):
        model = meshtex.model_for(None, SIZE, prompts={meshtex.WHOLE: "mud brick"})
        self.assertEqual(list(model.atlas.regions), [meshtex.WHOLE])
        r = model.atlas[meshtex.WHOLE]
        self.assertEqual((r.x, r.y, r.w, r.h), (0, 0, SIZE, SIZE))

    def test_the_region_rect_matches_the_texture_pixels(self):
        model = meshtex.model_for(ZONES, SIZE, margin=0)
        self.assertEqual(airepaint.region_rect(model, texture(), "roof"), (0, 0, SIZE, SIZE // 2))


class Prompts(unittest.TestCase):
    def test_a_zone_carries_its_own_prompt(self):
        model = meshtex.model_for(ZONES, SIZE, prompts={"roof": "rusted corrugated iron"})
        self.assertEqual(airepaint.material_of("roof", model.params), "rusted corrugated iron")
        self.assertIsNone(airepaint.material_of("walls", model.params))      # no prompt: left alone

    def test_a_generated_building_still_uses_its_built_in_table(self):
        from core import building
        p = building.PRESETS["COLONIAL_HOUSE"]
        self.assertIn("plaster", airepaint.material_of("front", p))


class Repaint(unittest.TestCase):
    def test_both_zones_are_repainted_and_nothing_else_moves(self):
        tex = texture()
        model = meshtex.model_for(ZONES, SIZE, margin=0,
                                  prompts={"roof": "clay tiles", "walls": "lime plaster"})
        with FakeComfy(transform=grainy) as fake:
            out, report = airepaint.repaint(tex, model, comfy.Client(fake.url), strength=0.5, seed=1,
                                            guard=False)
        self.assertEqual(sorted(r["region"] for r in report), ["roof", "walls"])
        self.assertTrue(all("skipped" not in r for r in report), report)
        self.assertEqual(out.shape, tex.shape)
        self.assertTrue((out[:, :, 3] == 255).all())
        self.assertTrue(any("clay tiles" in p for p in _texts(fake)))
        self.assertTrue(any("lime plaster" in p for p in _texts(fake)))

    def test_one_zone_only_leaves_the_other_untouched(self):
        tex = texture()
        model = meshtex.model_for(ZONES, SIZE, margin=0, prompts={"roof": "clay", "walls": "plaster"})
        with FakeComfy(transform=grainy) as fake:
            out, _ = airepaint.repaint(tex, model, comfy.Client(fake.url), strength=0.5, seed=1,
                                       regions=["roof"], guard=False)
        self.assertTrue((out[SIZE // 2:] == tex[SIZE // 2:]).all())
        self.assertFalse((out[:SIZE // 2] == tex[:SIZE // 2]).all())

    def test_the_prompt_of_the_whole_image_reaches_comfyui(self):
        tex = texture()
        model = meshtex.model_for(None, SIZE, prompts={meshtex.WHOLE: "weathered iron roof"})
        with FakeComfy(transform=grainy) as fake:
            airepaint.repaint(tex, model, comfy.Client(fake.url), strength=0.5, seed=1, guard=False)
        self.assertTrue(any("weathered iron roof" in p for p in _texts(fake)))


def _texts(fake):
    return [n["inputs"]["text"] for wf in fake.prompts for n in wf.values()
            if n["class_type"] == "CLIPTextEncode"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
