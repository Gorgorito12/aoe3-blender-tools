# SPDX-License-Identifier: GPL-3.0-or-later
"""A small client for a local ComfyUI (https://github.com/comfyanonymous/ComfyUI) and the repaint
workflow the add-on sends it. Standard library only, so it runs inside Blender.

The workflow uses core nodes only (no custom node packs): the region is encoded and partly
re-noised (img2img, `denoise`), and a ControlNet Union model fed with the region's own Canny
edges keeps every edge where it was. See docs/ai-textures.md for the install and the licences.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_URL = "http://127.0.0.1:8188"
CHECKPOINT = "sd_xl_base_1.0.safetensors"
CONTROLNET = "controlnet-union-sdxl-promax.safetensors"
NODES = ("CheckpointLoaderSimple", "LoadImage", "Canny", "ControlNetLoader", "SetUnionControlNetType",
         "ControlNetApplyAdvanced", "CLIPTextEncode", "VAEEncode", "KSampler", "VAEDecode", "SaveImage")


class ComfyError(RuntimeError):
    pass


class Client:
    def __init__(self, url=DEFAULT_URL, timeout=30.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    # -- plumbing --
    def _open(self, path, data=None, headers=None, timeout=None):
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise ComfyError(f"ComfyUI answered {e.code} on {path}: {body[:600]}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ComfyError(f"ComfyUI does not answer at {self.url} ({e}). Is it running?") from None

    def _json(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        return json.loads(self._open(path, data, headers).decode("utf-8"))

    # -- API --
    def alive(self):
        """True when the server answers."""
        try:
            self._json("/system_stats")
            return True
        except ComfyError:
            return False

    def object_info(self):
        return self._json("/object_info")

    def check(self, checkpoint=CHECKPOINT, controlnet=CONTROLNET):
        """Problems that stop a repaint: missing nodes or models ([] when all is there)."""
        info = self.object_info()
        problems = [f"ComfyUI has no node {n}" for n in NODES if n not in info]

        def choices(node, field):
            """The options of a combo input: [[a, b], {...}] or, newer, ["COMBO", {"options": [...]}]."""
            try:
                spec = info[node]["input"]["required"][field]
            except (KeyError, TypeError):
                return []
            if spec and isinstance(spec[0], list):
                return spec[0]
            if spec and spec[0] == "COMBO" and len(spec) > 1:
                return spec[1].get("options", [])
            return []
        if checkpoint not in choices("CheckpointLoaderSimple", "ckpt_name"):
            problems.append(f"checkpoint {checkpoint} is not in ComfyUI's models/checkpoints")
        if controlnet not in choices("ControlNetLoader", "control_net_name"):
            problems.append(f"ControlNet {controlnet} is not in ComfyUI's models/controlnet")
        return problems

    def upload(self, png, name):
        """Uploads a PNG to ComfyUI's input folder; returns the stored name."""
        boundary = "aoe3bt" + uuid.uuid4().hex
        parts = []
        for field, value in (("overwrite", "true"), ("type", "input")):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"\r\n\r\n{value}\r\n"
                         .encode("utf-8"))
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                     "Content-Type: image/png\r\n\r\n".encode("utf-8") + png + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)
        out = json.loads(self._open("/upload/image", body,
                                    {"Content-Type": f"multipart/form-data; boundary={boundary}"}).decode("utf-8"))
        return out["name"] if not out.get("subfolder") else f"{out['subfolder']}/{out['name']}"

    def queue(self, workflow):
        out = self._json("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if out.get("node_errors"):
            raise ComfyError(f"ComfyUI refused the workflow: {json.dumps(out['node_errors'])[:600]}")
        return out["prompt_id"]

    def wait(self, prompt_id, timeout=300.0, poll=0.25):
        """The history entry of a finished prompt."""
        end = time.time() + timeout
        while time.time() < end:
            h = self._json(f"/history/{prompt_id}")
            if prompt_id in h:
                entry = h[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    raise ComfyError(f"ComfyUI failed: {json.dumps(msgs)[:600]}")
                if entry.get("outputs"):
                    return entry
            time.sleep(poll)
        raise ComfyError(f"ComfyUI did not finish in {timeout:.0f} s")

    def fetch(self, filename, subfolder="", kind="output"):
        q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": kind})
        return self._open(f"/view?{q}")

    def run(self, workflow, timeout=300.0):
        """Queues a workflow and returns the PNG bytes of its first saved image."""
        entry = self.wait(self.queue(workflow), timeout)
        for out in entry["outputs"].values():
            for img in out.get("images", []):
                return self.fetch(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
        raise ComfyError("ComfyUI finished without an image")


def repaint_workflow(image_name, *, prompt, negative, denoise, seed, checkpoint=CHECKPOINT,
                     controlnet=CONTROLNET, steps=24, cfg=5.5, control_strength=0.85,
                     canny=(0.15, 0.45), union_type="canny/lineart/anime_lineart/mlsd",
                     sampler="dpmpp_2m", scheduler="karras", prefix="aoe3bt"):
    """The repaint workflow in ComfyUI's API format: img2img of the uploaded region at `denoise`,
    held by a ControlNet Union on the region's own Canny edges."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "3": {"class_type": "Canny", "inputs": {"image": ["2", 0], "low_threshold": canny[0],
                                                "high_threshold": canny[1]}},
        "4": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": controlnet}},
        "5": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["4", 0], "type": union_type}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "8": {"class_type": "ControlNetApplyAdvanced",
              "inputs": {"positive": ["6", 0], "negative": ["7", 0], "control_net": ["5", 0], "image": ["3", 0],
                         "strength": control_strength, "start_percent": 0.0, "end_percent": 1.0, "vae": ["1", 2]}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["1", 0], "seed": int(seed), "steps": int(steps), "cfg": float(cfg),
                          "sampler_name": sampler, "scheduler": scheduler, "positive": ["8", 0],
                          "negative": ["8", 1], "latent_image": ["9", 0], "denoise": float(denoise)}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": prefix}},
    }
