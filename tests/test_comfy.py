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


class Lora(unittest.TestCase):
    """Painting with a LoRA, and training one, with ComfyUI's own nodes."""

    def test_without_a_lora_a_workflow_is_what_it_always_was(self):
        a = comfy.texture_workflow(prompt="p", negative="n", seed=1)
        self.assertEqual(a, comfy.texture_workflow(prompt="p", negative="n", seed=1, lora=None))
        self.assertNotIn("lora", a)

    def test_a_lora_sits_between_the_checkpoint_and_what_used_its_model_and_text_encoder(self):
        for wf in (comfy.texture_workflow(prompt="p", negative="n", seed=1, lora="own.safetensors"),
                   comfy.repaint_workflow("x.png", prompt="p", negative="n", denoise=0.4, seed=1,
                                          lora="own.safetensors", lora_strength=0.6)):
            node = wf["lora"]
            self.assertEqual(node["class_type"], comfy.LORA_NODE)
            self.assertEqual((node["inputs"]["model"], node["inputs"]["clip"]), (["1", 0], ["1", 1]))
            users = [v for k, n in wf.items() if k != "lora" for v in n["inputs"].values()
                     if isinstance(v, list) and len(v) == 2 and v[0] in ("1", "lora")]
            self.assertTrue(all(v[0] == "lora" for v in users if v[1] in (0, 1)), users)
            self.assertTrue(any(v == ["1", 2] for v in users))             # the VAE stays the checkpoint's
        self.assertEqual(wf["lora"]["inputs"]["strength_model"], 0.6)

    def test_the_training_workflow_links_dataset_trainer_and_saver(self):
        wf = comfy.train_lora_workflow("own", prefix="loras/own", steps=10, rank=4)
        kinds = [wf[k]["class_type"] for k in sorted(wf)]
        self.assertEqual(kinds[1:], list(comfy.TRAIN_NODES))
        self.assertEqual(wf["4"]["inputs"]["latents"], ["3", 0])
        self.assertEqual(wf["4"]["inputs"]["positive"], ["3", 1])
        self.assertEqual((wf["4"]["inputs"]["steps"], wf["4"]["inputs"]["rank"]), (10, 4))
        self.assertEqual(wf["5"]["inputs"]["lora"], ["4", 0])

    def test_a_training_run_ends_without_a_picture_and_the_client_knows(self):
        with FakeComfy() as fake:
            client = comfy.Client(fake.url)
            self.assertEqual(client.can_train(), [])
            self.assertEqual(client.loras(), ["own_hand.safetensors"])
            entry = client.wait(client.queue(comfy.train_lora_workflow("own", steps=2)), timeout=10)
            self.assertEqual(entry["status"]["status_str"], "success")
        with FakeComfy(missing_nodes=("TrainLoraNode",)) as fake:
            self.assertIn("TrainLoraNode", comfy.Client(fake.url).can_train()[0])

    def test_a_chunk_goes_on_from_the_last_with_less_memory(self):
        wf = comfy.train_lora_workflow("own", steps=400, batch_size=1, accumulate=2,
                                       existing_lora="own_400_steps_00001_.safetensors")
        node = wf["4"]["inputs"]
        self.assertEqual((node["batch_size"], node["grad_accumulation_steps"]), (1, 2))
        self.assertEqual(node["existing_lora"], "own_400_steps_00001_.safetensors")
        self.assertEqual(comfy.train_lora_workflow("own")["4"]["inputs"]["existing_lora"], "[None]")

    def test_a_long_run_is_cut_into_chunks_that_add_up(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import train_lora
        self.assertEqual(train_lora.chunk_plan(1200, 3), [400, 400, 400])
        self.assertEqual(train_lora.chunk_plan(1000, 3), [334, 333, 333])
        self.assertEqual(train_lora.chunk_plan(1200, 3, done=800), [400])
        self.assertEqual(train_lora.chunk_plan(1200, 3, done=500), [300, 400])
        self.assertEqual(train_lora.chunk_plan(1200, 3, done=1200), [])
        self.assertEqual(train_lora.steps_of("own_800_steps_00002_.safetensors"), 800)
        self.assertEqual(train_lora.steps_of("own.safetensors"), 0)

    def test_the_watchdog_interrupts_comfyui_when_memory_runs_short(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import train_lora
        readings = iter([9.0, 6.0, 2.0, 1.5, 1.5, 1.5])
        with FakeComfy() as fake:
            dog = train_lora.Watchdog(comfy.Client(fake.url), 2.5, read=lambda: next(readings, 1.5), every=0.01)
            dog.start()
            for _ in range(200):
                if dog.tripped:
                    break
                dog.join(0.01)
            dog.stop()
            dog.join(1)
            self.assertTrue(dog.tripped)
            self.assertEqual(fake.interrupts, 1)              # once, not every reading
            self.assertLessEqual(dog.lowest, 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
