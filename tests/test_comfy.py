# SPDX-License-Identifier: GPL-3.0-or-later
"""The ComfyUI client and the repaint workflow, against a stand-in server (no GPU needed):

    venv\\Scripts\\python -I tests\\test_comfy.py
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import comfy, pngio  # noqa: E402
from fake_comfy import FakeComfy, _png  # noqa: E402


class Workflow(unittest.TestCase):
    def test_links_point_at_existing_outputs(self):
        wf = comfy.repaint_workflow("r.png", prompt="p", negative="n", denoise=0.4, seed=7)
        outputs = {"CheckpointLoaderSimple": 3, "LoadImage": 2, "Canny": 1, "ControlNetLoader": 1,
                   "SetUnionControlNetType": 1, "CLIPTextEncode": 1, "ControlNetApplyAdvanced": 2,
                   "VAEEncode": 1, "KSampler": 1, "VAEDecode": 1, "SaveImage": 0}
        for key, node in wf.items():
            self.assertIn(node["class_type"], comfy.NODES)
            for value in node["inputs"].values():
                if isinstance(value, list):
                    src, slot = value
                    self.assertIn(src, wf, (key, value))
                    self.assertLess(slot, outputs[wf[src]["class_type"]], (key, value))
        ks = next(n for n in wf.values() if n["class_type"] == "KSampler")
        self.assertEqual((ks["inputs"]["seed"], ks["inputs"]["denoise"]), (7, 0.4))


class ClientRoundTrip(unittest.TestCase):
    def test_upload_run_fetch(self):
        img = np.random.default_rng(1).integers(0, 256, (64, 96, 3), dtype=np.uint8)
        with FakeComfy(transform=lambda rgb: 255 - rgb) as fake:
            c = comfy.Client(fake.url)
            self.assertTrue(c.alive())
            self.assertEqual(c.check(), [])
            name = c.upload(_png(img), "region.png")
            self.assertEqual(name, "region.png")
            out = pngio.read_png(c.run(comfy.repaint_workflow(name, prompt="p", negative="n", denoise=0.5, seed=1)))
            self.assertTrue((out[:, :, :3] == 255 - img).all())

    def test_check_names_what_is_missing(self):
        with FakeComfy(missing_nodes=("Canny",), models=False) as fake:
            problems = comfy.Client(fake.url).check()
        self.assertTrue(any("Canny" in p for p in problems))
        self.assertTrue(any(comfy.CHECKPOINT in p for p in problems))
        self.assertTrue(any(comfy.CONTROLNET in p for p in problems))

    def test_server_down_is_a_clear_error(self):
        c = comfy.Client("http://127.0.0.1:9", timeout=2)
        self.assertFalse(c.alive())
        with self.assertRaises(comfy.ComfyError) as e:
            c.object_info()
        self.assertIn("does not answer", str(e.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
