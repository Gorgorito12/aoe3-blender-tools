# SPDX-License-Identifier: GPL-3.0-or-later
r"""Trains a LoRA on a dataset of tools/lora_dataset.py with the local ComfyUI (its own training
nodes, no custom pack), and puts the result where ComfyUI loads LoRAs from.

    venv\Scripts\python -I tools\train_lora.py <dataset folder> --comfy <ComfyUI portable folder>
        [--name aoe3bt_own] [--steps 1200] [--chunks 3] [--rank 16] [--lr 1e-4] [--batch 1]
        [--accumulate 2] [--offload] [--seed 1] [--min-free 2.5] [--resume <file>] [--limit N]
        [--url http://127.0.0.1:8188]

The dataset is copied into ComfyUI's input folder (its loader reads only from there) and the
training is queued in **chunks**: each chunk goes on from the LoRA the last one saved, so a run
that is stopped loses one chunk, never the run (`--resume <file>` starts again from a chunk's
file, the command is printed when a run stops). Batch 1 with 2 accumulation steps learns as
batch 2 does, with less memory.

A watchdog reads the PC's free memory every few seconds: under `--min-free` GB it interrupts
ComfyUI and the run stops there. The lowest free memory seen is reported, so a short trial run
(`--steps 20 --chunks 1`) tells whether the full one fits.

The finished LoRA is ComfyUI's models/loras/<name>.safetensors. Nothing is written into this
repository: a LoRA trained on a mod's art is that mod's, and a model is never committed.

Then: tools/make_texture.py ... --lora <name>.safetensors, or the LoRA field of the AI panels.
"""
import ctypes
import glob
import os
import re
import shutil
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import comfy  # noqa: E402


def free_gb():
    """The PC's free physical memory in GB, or None when it cannot be read."""
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                        ("avail_extended", ctypes.c_ulonglong)]
        st = Status()
        st.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return st.avail / 2 ** 30
        return None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2 ** 20
    except OSError:
        pass
    return None


class Watchdog(threading.Thread):
    """Interrupts ComfyUI when the free memory falls under `limit` GB; keeps the lowest seen."""

    def __init__(self, client, limit, read=free_gb, every=3.0):
        super().__init__(daemon=True)
        self.client, self.limit, self.read, self.every = client, limit, read, every
        self.lowest = None
        self.tripped = False
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            gb = self.read()
            if gb is not None:
                self.lowest = gb if self.lowest is None else min(self.lowest, gb)
                if gb < self.limit and not self.tripped:
                    self.tripped = True
                    try:
                        self.client.interrupt()
                    except comfy.ComfyError:
                        pass
            self._halt.wait(self.every)

    def stop(self):
        self._halt.set()


def steps_of(filename):
    """The steps a saved LoRA holds, from the name ComfyUI's saver gives it (0 when it says none)."""
    m = re.search(r"_(\d+)_steps_", os.path.basename(filename))
    return int(m.group(1)) if m else 0


def chunk_plan(total, chunks, done=0):
    """The steps of each chunk still to train, from `done` up to `total`: the run cut into
    `chunks` near-equal chunks, and the ones `done` already covers left out."""
    chunks = max(1, chunks)
    base, extra = divmod(total, chunks)
    sizes = [base + (1 if i < extra else 0) for i in range(chunks)]
    out, at = [], 0
    for size in sizes:
        if size and at + size > done:
            out.append(at + size - max(at, done))
        at += size
    return out


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    src = next((a for a in argv if not a.startswith("--") and os.path.isdir(a)), None)
    root = opt("--comfy")
    if not src or not root:
        print(__doc__)
        return 2
    base = os.path.join(root, "ComfyUI")
    loras = os.path.join(base, "models", "loras")
    name = opt("--name", "aoe3bt_own")
    client = comfy.Client(opt("--url", comfy.DEFAULT_URL), timeout=60)
    problems = client.can_train() if client.alive() else [f"ComfyUI does not answer at {client.url}"]
    if problems:
        raise SystemExit("; ".join(problems))
    dest = os.path.join(base, "input", name)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    pngs = sorted(glob.glob(os.path.join(src, "*.png")))
    if opt("--limit"):
        pngs = pngs[:int(opt("--limit"))]
    for p in pngs:
        shutil.copy2(p, dest)
        if os.path.exists(p[:-4] + ".txt"):
            shutil.copy2(p[:-4] + ".txt", dest)

    total = int(opt("--steps", "1200"))
    current = opt("--resume")                          # a file of models/loras
    plan = chunk_plan(total, int(opt("--chunks", "3")), steps_of(current) if current else 0)
    seed = int(opt("--seed", "1"))
    dog = Watchdog(client, float(opt("--min-free", "2.5")))
    dog.start()
    print(f"{len(pngs)} pictures, {total} steps in {len(plan)} chunks {plan}; "
          f"free memory now {free_gb() or 0:.1f} GB", flush=True)
    t0 = time.time()
    stopped = None
    for i, steps in enumerate(plan):
        wf = comfy.train_lora_workflow(
            name, prefix=f"loras/{name}", steps=steps, rank=int(opt("--rank", "16")),
            learning_rate=float(opt("--lr", "1e-4")), batch_size=int(opt("--batch", "1")),
            accumulate=int(opt("--accumulate", "2")), seed=seed + i, existing_lora=current,
            offloading="--offload" in argv)
        t1 = time.time()
        try:
            client.wait(client.queue(wf), timeout=float(opt("--timeout", "14400")), poll=5.0)
        except comfy.ComfyError as exc:
            stopped = "the free memory fell under the limit" if dog.tripped else str(exc)
            break
        if dog.tripped:
            stopped = "the free memory fell under the limit"
            break
        made = sorted(glob.glob(os.path.join(base, "output", "loras", name + "_*_steps_*.safetensors")),
                      key=os.path.getmtime)
        if not made:
            stopped = "ComfyUI finished a chunk without saving a LoRA"
            break
        os.makedirs(loras, exist_ok=True)
        done = os.path.join(loras, os.path.basename(made[-1]))
        shutil.move(made[-1], done)
        if current and os.path.exists(os.path.join(loras, current)) and current != os.path.basename(done):
            os.remove(os.path.join(loras, current))    # the chunk before is inside this one
        current = os.path.basename(done)
        print(f"chunk {i + 1}/{len(plan)}: {steps} steps in {time.time() - t1:.0f} s, "
              f"{steps_of(current)} in all; lowest free memory {dog.lowest or 0:.1f} GB", flush=True)
    dog.stop()
    shutil.rmtree(dest, ignore_errors=True)            # the copy of the dataset has done its work
    if stopped:
        print(f"STOPPED: {stopped}. Lowest free memory {dog.lowest or 0:.1f} GB.")
        if current:
            print(f"Go on with: --resume {current}")
        return 1
    target = os.path.join(loras, name + ".safetensors")
    if os.path.exists(target):
        os.remove(target)
    os.replace(os.path.join(loras, current), target)
    print(f"trained in {time.time() - t0:.0f} s -> {target} ({os.path.getsize(target) / 1e6:.1f} MB); "
          f"lowest free memory {dog.lowest or 0:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
