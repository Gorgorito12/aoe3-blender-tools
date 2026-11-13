# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture maker: the seam measure, the tiling, the de-lighting, and the three ways to make a
texture (a photograph, a prompt, and neither ComfyUI nor a GPU). No GPU: the AI paths run against
tests/fake_comfy.py.

    venv\\Scripts\\python -I tests\\test_texmaker.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import comfy, materials, texmaker  # noqa: E402
from fake_comfy import FakeComfy  # noqa: E402


def photo(side=512, seed=0):
    """A photograph as one comes: brighter to one side (the light of the day), with grain. It
    does not tile: its left and right edges are far apart."""
    rng = np.random.default_rng(seed)
    x = np.linspace(40, 215, side, dtype=np.float32)[None, :, None]
    return np.clip(x + rng.integers(-12, 13, (side, side, 3)), 0, 255).astype(np.uint8)


class Seam(unittest.TestCase):
    def test_a_tileable_image_measures_about_one(self):
        rng = np.random.default_rng(1)
        noise = rng.integers(0, 256, (64, 64, 3)).astype(np.uint8)       # wraps as well as it joins
        self.assertLess(texmaker.seam(noise), 1.3)

    def test_an_image_that_does_not_tile_measures_far_more(self):
        self.assertGreater(texmaker.seam(photo(128)), 3.0)


class Tiling(unittest.TestCase):
    def test_wrap_blend_closes_the_join(self):
        before = photo(256)
        after = texmaker.wrap_blend(before)
        self.assertGreater(texmaker.seam(before), 3.0)
        self.assertLess(texmaker.seam(after), 1.3)
        self.assertEqual(after.shape, (256, 256, 3))

    def test_the_borders_are_pixels_that_were_neighbours_so_nothing_is_invented_there(self):
        src = photo(256, seed=3)
        out = texmaker.wrap_blend(src)
        first, last = np.roll(src[128], 128, axis=0), np.roll(src[127], 128, axis=0)
        self.assertTrue((out[0, :40] == first[:40]).all())    # rolled by half; only the middle
        self.assertTrue((out[-1, :40] == last[:40]).all())    # band is blended

    def test_resampling_keeps_it_tileable(self):
        out = materials.resample(texmaker.wrap_blend(photo(256)).astype(np.float32), 64)
        self.assertLess(texmaker.seam(out), 1.4)

    def test_the_sheet_repeats_the_texture(self):
        t = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)
        s = texmaker.sheet(t)
        self.assertEqual(s.shape, (12, 12, 3))
        self.assertTrue((s[4:8, 4:8] == t).all())


class Delight(unittest.TestCase):
    def test_the_broad_light_is_divided_out(self):
        src = texmaker.wrap_blend(photo(256))       # as make() does it: tiled first, then de-lit
        out = texmaker.delight(src)
        def broad(a):
            return materials.resample(a[:, :, :3].astype(np.float32), 4)[:, :, 0]
        before, after = float(np.ptp(broad(src))), float(np.ptp(broad(out)))
        self.assertGreater(before, 60)                 # the light across the photograph
        self.assertLess(after, before / 3)             # most of it divided out
        self.assertEqual(out.dtype, np.uint8)
        self.assertLess(abs(float(out.mean()) - float(src.mean())), 4)   # its colour is kept


class Make(unittest.TestCase):
    def test_without_comfyui_a_photograph_still_becomes_a_tileable_swatch(self):
        out, report = texmaker.make(photo(), size=128, gen=256)
        self.assertEqual(out.shape, (128, 128, 3))
        self.assertEqual(report["mode"], "photo")
        self.assertLess(report["seam"], texmaker.SEAM_OK)
        self.assertGreater(report["seam_before"], 3.0)
        self.assertNotIn("note", report)

    def test_a_prompt_alone_needs_comfyui(self):
        with self.assertRaises(ValueError):
            texmaker.make(prompt="dry golden grass thatch")
        with self.assertRaises(ValueError):
            texmaker.make(client=object())        # no prompt and no reference

    def test_a_prompt_draws_a_texture_and_the_words_reach_comfyui(self):
        with FakeComfy() as fake:
            out, report = texmaker.make(prompt="dry golden grass thatch",
                                        client=comfy.Client(fake.url), size=128, gen=256)
        self.assertEqual(report["mode"], "prompt")
        self.assertEqual(out.shape, (128, 128, 3))
        self.assertLess(report["seam"], texmaker.SEAM_OK)
        texts = [n["inputs"]["text"] for wf in fake.prompts for n in wf.values()
                 if n["class_type"] == "CLIPTextEncode"]
        self.assertTrue(any("dry golden grass thatch" in t for t in texts), texts)
        self.assertTrue(any("seamless tileable" in t for t in texts), texts)
        self.assertEqual(sum(1 for wf in fake.prompts
                             if any(n["class_type"] == "EmptyLatentImage" for n in wf.values())), 1)

    def test_a_photograph_with_a_prompt_is_repainted_first(self):
        with FakeComfy() as fake:
            out, report = texmaker.make(photo(), prompt="weathered planks",
                                        client=comfy.Client(fake.url), size=128, gen=256)
        self.assertEqual(report["mode"], "photo+ai")
        self.assertIn("repainting the reference", report["steps"])
        self.assertIn("hiding the blend", report["steps"])
        self.assertLess(texmaker.seam(out), texmaker.SEAM_OK)

    def test_the_healing_pass_cannot_break_the_tiling(self):
        """Whatever the AI draws, the borders are kept, so the texture still repeats."""
        with FakeComfy(transform=lambda rgb: np.full_like(rgb, 7)) as fake:
            tiled = texmaker.wrap_blend(photo(256))
            out = texmaker.heal(tiled, comfy.Client(fake.url), prompt="anything")
        self.assertTrue((out[0] == tiled[0]).all())
        self.assertTrue((out[:, -1] == tiled[:, -1]).all())
        self.assertFalse((out[128] == tiled[128]).all())      # the middle was redrawn
        self.assertLess(texmaker.seam(out), 1.3)

    def test_a_lora_reaches_every_pass_with_its_trigger_word(self):
        with FakeComfy() as fake:
            out, report = texmaker.make(prompt="mud brick wall", client=comfy.Client(fake.url),
                                        size=64, gen=128, lora="own_hand.safetensors", lora_strength=0.7)
        self.assertEqual(report["lora"], "own_hand.safetensors")
        self.assertEqual(len(fake.prompts), 2)                       # the drawing and the healing
        for wf in fake.prompts:
            self.assertEqual(wf["lora"]["inputs"]["lora_name"], "own_hand.safetensors")
            self.assertEqual(wf["lora"]["inputs"]["strength_model"], 0.7)
            self.assertTrue(any(texmaker.TRIGGER in n["inputs"]["text"] for n in wf.values()
                                if n["class_type"] == "CLIPTextEncode"))

    def test_the_seed_and_the_size_are_reported(self):
        out, report = texmaker.make(photo(), size=64, gen=128, seed=12)
        self.assertEqual((report["seed"], report["size"]), (12, 64))
        self.assertEqual(out.shape[0], 64)


GROUP = {"count": 40, "grain": [0.16, 0.29, 0.40], "saturation": [0.21, 0.36, 0.45],
         "luminance": [65.0, 92.0, 123.0]}           # the shape of an entry of the texture profile


class Style(unittest.TestCase):
    """How far a texture is from a group of the mod's own, and bringing it there."""

    def loud(self):
        rng = np.random.default_rng(4)                 # saturated and grainy, as SDXL paints
        img = np.clip(np.array([200, 120, 30]) + rng.integers(-70, 71, (128, 128, 3)), 0, 255)
        return texmaker.wrap_blend(img.astype(np.uint8))

    def test_the_measures_are_the_surveys(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import texture_survey
        img = self.loud()
        half = texmaker._half(img.astype(np.float32))
        rgba = np.dstack([half, np.full(half.shape[:2], 255)]).astype(np.uint8)
        theirs, ours = texture_survey.measure(rgba), texmaker.measures(img)
        self.assertAlmostEqual(ours["grain"], theirs["grain"], 2)
        self.assertAlmostEqual(ours["saturation"], theirs["saturation"][1], 2)
        self.assertAlmostEqual(ours["luminance"], theirs["luminance"][1], 0)

    def test_the_distance_is_in_widths_of_the_groups_middle_half(self):
        d = texmaker.distance(self.loud(), GROUP)
        m = d["measured"]
        self.assertAlmostEqual(d["saturation"], (m["saturation"] - 0.36) / 0.24, 1)
        self.assertGreater(d["off"], 1.0)                          # well outside what the mod does
        self.assertEqual(d["off"], max(abs(d[k]) for k in texmaker.MEASURES))

    def test_match_brings_grain_and_saturation_to_the_median_and_keeps_the_tiling(self):
        img = self.loud()
        out = texmaker.match(img, GROUP)
        d = texmaker.distance(out, GROUP)
        self.assertLess(abs(d["grain"]), 0.15)
        self.assertLess(abs(d["saturation"]), 0.25)
        self.assertLess(texmaker.seam(out), texmaker.SEAM_OK)
        self.assertLess(np.abs(out.mean((0, 1)) @ texmaker.LUM - img.mean((0, 1)) @ texmaker.LUM), 12)

    def test_make_reports_the_style_and_fits_when_asked(self):
        class One:
            def nearest(self, category, role, material):
                return GROUP, f"own {category}, {material}"
        out, report = texmaker.make(photo(), size=64, gen=128, material="wood", profile=One())
        self.assertEqual(report["style"]["against"], "own buildings, wood")
        self.assertIn("off", report["style"])
        fitted, r2 = texmaker.make(photo(), size=64, gen=128, material="wood", profile=One(), fit=True)
        self.assertIn("before_fit", r2["style"])
        self.assertLessEqual(abs(r2["style"]["grain"]), abs(report["style"]["grain"]) + 0.05)
        self.assertLess(r2["seam"], texmaker.SEAM_OK)

    def test_the_shipped_profile_answers_for_a_material(self):
        from core import profile
        art = profile.art("textures")
        if art is None:
            self.skipTest("no texture profile shipped")
        group, what = art.nearest("buildings", "diffuse", "wood")
        self.assertIsNotNone(group)
        self.assertEqual(len(group["grain"]), 3)
        self.assertTrue(what.startswith(("own", "stock")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
