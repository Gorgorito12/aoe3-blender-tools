# SPDX-License-Identifier: GPL-3.0-or-later
"""Renders contact sheets of the models a model survey measured: a grid of sampled models per
origin and category, each with its own texture when the texture survey found it. To look at how
the art of a mod is built - its proportions, its silhouettes, how its textures sit on its models.

    venv\\Scripts\\python tools\\model_sheets.py <models.json> --cache <survey cache> --out <folder>
        [--textures <textures.json>] [--groups own:buildings,stock:nuggets] [--cell 160]
        [--cols 8] [--rows 6] [--seed 3]

The sheets are pictures of the mod's art: they are written outside any repository, like the
reports they come from. Needs Blender (the bpy module) and numpy.
"""
import json
import os
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import model_survey as ms  # noqa: E402
import texture_survey as ts  # noqa: E402
from aoe3_blender_tools.aoe3game import ddt, gr2_mesh  # noqa: E402
from aoe3_blender_tools.core import blender_io, gr2_import, render  # noqa: E402
from aoe3_blender_tools.core.pngio import encode_png  # noqa: E402


def texture_index(textures):
    """{file stem: record} of the diffuse textures, the largest of each name."""
    out = {}
    for t in textures:
        if "error" in t or t.get("role") in ("bump", "spec", "ui", "decal"):
            continue
        stem = os.path.splitext(os.path.basename(ts.norm(t["path"]).replace("\\", "/")))[0]
        if stem not in out or t["w"] > out[stem]["w"]:
            out[stem] = t
    return out


def image_for(record, index):
    for name in record.get("textures", ()):
        stem = os.path.splitext(name)[0]
        if stem.endswith(("_b", "_n", "_spec", "_s")) or stem not in index:
            continue
        t = index[stem]
        try:
            data = ts._read(*t["at"])
            hd = ddt.read_header(data)
            level = 0
            while level + 1 < len(hd.levels) and max(hd.width, hd.height) >> (level + 1) >= 256:
                level += 1
            rgba = ddt.decode(data, level).copy()
            rgba[:, :, 3] = 255
            return blender_io._image_from_array("sheet_tex", rgba)
        except Exception:
            continue
    return None


def render_one(record, cache, index, cell):
    data = ts._read(*record["at"])
    model = gr2_mesh.read(ms.raw_bytes(data, record["md5"], (None, cache, cache)))
    if not model["meshes"]:
        return None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = gr2_import.create(model, "m", image_for(record, index) if index else None)
    rgba = render.render_rgba(obj, size=cell)
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return (rgba[:, :, :3] * a + np.array([70, 80, 70]) * (1 - a)).astype(np.uint8)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    src = next((a for a in argv if a.lower().endswith(".json") and a != opt("--textures")), None)
    cache, out = opt("--cache"), opt("--out")
    if not src or not cache or not out:
        print(__doc__)
        return 2
    with open(src, encoding="utf-8") as fh:
        models = json.load(fh)["models"]
    index = None
    if opt("--textures"):
        with open(opt("--textures"), encoding="utf-8") as fh:
            index = texture_index(ts.name(json.load(fh)["textures"]))
    wanted = [tuple(g.split(":")) for g in opt("--groups", "own:buildings,own:units,stock:nuggets,stock:objects").split(",")]
    cell, cols, rows = int(opt("--cell", "160")), int(opt("--cols", "8")), int(opt("--rows", "6"))
    rng = np.random.default_rng(int(opt("--seed", "3")))
    os.makedirs(out, exist_ok=True)
    for origin, cat in wanted:
        pool, seen = [], set()
        for r in models:
            if ("error" in r or r["origin"] != origin or r["category"] != cat or not r.get("tris")
                    or r["md5"] in seen or any(lay.startswith("FD:") for lay in r["layouts"])):
                continue
            seen.add(r["md5"])
            pool.append(r)
        if not pool:
            print(f"{origin} {cat}: nothing to render")
            continue
        order = rng.permutation(len(pool))
        sheet = np.full((rows * cell, cols * cell, 3), 40, np.uint8)
        lines, n = [], 0
        for i in order:
            if n >= cols * rows:
                break
            r = pool[int(i)]
            try:
                img = render_one(r, cache, index, cell)
            except Exception as exc:
                lines.append(f"skipped ({type(exc).__name__}): {r['path']}")
                continue
            if img is None:
                continue
            y, x = divmod(n, cols)
            sheet[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell] = img
            lines.append(f"row {y + 1} col {x + 1}: {r['tris']} tris, {r['bones']} bones, size {r.get('size')}  {r['path']}")
            n += 1
        path = os.path.join(out, f"models_{origin}_{cat}.png")
        with open(path, "wb") as fh:
            fh.write(encode_png(sheet))
        with open(path[:-4] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(f"{origin} {cat}: {len(pool)} distinct models with plain vertices, {n} shown\n" + "\n".join(lines) + "\n")
        print(f"{origin} {cat}: {n} of {len(pool)} -> {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
