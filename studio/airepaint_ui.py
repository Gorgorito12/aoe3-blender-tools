# SPDX-License-Identifier: GPL-3.0-or-later
"""The building screen's AI repaint: the building's texture repainted region by region by the
local ComfyUI (core/airepaint.py), in a thread of the studio, each region shown as it is done;
it can be stopped between regions. The result is kept as a PNG the game export then uses
(scripts/game_export.py --texture-png) in place of the painted texture."""
import base64
import os
import threading
import time

from . import use_core

use_core()
import numpy as np  # noqa: E402

from core import airepaint, building, comfy, schema  # noqa: E402
from core import paint as painter  # noqa: E402

from . import engine  # noqa: E402


class AiError(ValueError):
    pass


def _png(rgba):
    return "data:image/png;base64," + base64.b64encode(painter.png_bytes(np.asarray(rgba, np.uint8), level=3)).decode("ascii")


def regions(data):
    """Every region of the building's texture: its size and the material the repaint would ask
    for (None: left as painted)."""
    p = schema.params_from_dict(data)
    model = building.build(p)
    k = model.atlas.size / max(1, p.texture_size)            # the atlas is laid out at twice the size
    out = []
    for name, r in model.atlas.regions.items():
        w, h = int(r.w / k), int(r.h / k)
        out.append({"name": name, "material": airepaint.material_of(name, model.params), "size": [w, h],
                    "small": min(w, h) < airepaint.MIN_SIDE})
    return {"regions": out, "walls": airepaint.group(model, "WALLS"), "roofs": airepaint.group(model, "ROOFS")}


class Run:
    """One repaint in its thread."""

    def __init__(self, data, url, *, strength=0.45, seed=1, regions=None, blend=1.0, prompt="", extra="", guard=True,
                 lora="", lora_strength=0.8):
        if not 0.05 <= float(strength) <= 0.95:
            raise AiError("strength: 0.05 to 0.95")
        if not 0.0 <= float(blend) <= 1.0:
            raise AiError("blend: 0 to 1")
        if lora and not 0.0 <= float(lora_strength) <= 1.5:
            raise AiError("LoRA strength: 0 to 1.5")
        self.params = schema.params_from_dict(data)
        self.client = comfy.Client(url, timeout=180)
        if not self.client.alive():
            raise AiError(f"ComfyUI does not answer at {url}: start it, or set its address in Settings")
        with engine._lock:
            self.model = building.build(self.params)
            self.start = (painter.paint_rgba(self.model) if self.params.player_colour
                          else painter.paint(self.model))
        if self.start.shape[2] == 3:
            self.start = np.concatenate([self.start, np.full(self.start.shape[:2] + (1,), 255, np.uint8)], axis=2)
        names = list(self.model.atlas.regions)
        if regions is not None:
            unknown = set(regions) - set(names)
            if unknown:
                raise AiError("no such region: " + ", ".join(sorted(unknown)))
        if lora and lora not in self.client.loras():
            raise AiError(f"ComfyUI has no LoRA {lora} in models/loras")
        self.args = {"strength": float(strength), "seed": int(seed), "regions": regions, "blend": float(blend),
                     "prompt": prompt or None, "guard": bool(guard),
                     **airepaint.lora_args(lora or None, lora_strength, extra)}
        self.status, self.error, self.report = "running", None, None
        self.progress = {"done": 0, "of": len(regions) if regions is not None else len(names), "region": None}
        self.latest, self.version, self.result = None, 0, None
        self.cancelled = False
        self.started = time.time()
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def _on_progress(self, i, n, name):
        if self.cancelled:
            raise comfy.ComfyError("stopped")
        with self.lock:
            self.progress = {"done": i, "of": n, "region": name}

    def _on_region(self, texture):
        with self.lock:
            self.latest = texture
            self.version += 1

    def _work(self):
        try:
            out, report = airepaint.repaint(self.start, self.model, self.client, on_progress=self._on_progress,
                                            on_region=self._on_region, **self.args)
            with self.lock:
                self.result, self.report, self.status = out, report, "done"
                self.latest, self.version = out, self.version + 1
        except Exception as e:                  # shown on the page, never lost in the thread
            with self.lock:
                self.status = "cancelled" if self.cancelled else "failed"
                self.error = str(e)

    def cancel(self):
        self.cancelled = True
        try:
            self.client.interrupt()               # what ComfyUI is drawing now stops too
        except Exception:
            pass

    def state(self, since=-1):
        with self.lock:
            out = {"status": self.status, "progress": dict(self.progress), "error": self.error,
                   "version": self.version, "seconds": round(time.time() - self.started, 1),
                   "report": self.report}
            if self.version != since and self.latest is not None:
                out["image"] = _png(self.latest)
            return out

    def save(self, folder):
        """The repainted texture as a PNG for the game export; the regions done so far when it
        was stopped."""
        with self.lock:
            tex = self.result if self.result is not None else self.latest
        if tex is None:
            raise AiError("nothing repainted yet")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{self.params.name}_ai_{time.strftime('%Y%m%d-%H%M%S')}.png")
        with open(path, "wb") as fh:
            fh.write(painter.png_bytes(np.asarray(tex, np.uint8)))
        return path
