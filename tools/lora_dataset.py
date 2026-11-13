# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the pictures a LoRA of the mod's own hand is trained on, from the texture survey's
report: pieces of the textures the mod itself made and its models wear.

    venv\\Scripts\\python -I tools\\lora_dataset.py <textures.json> --out <folder>
        [--categories buildings,buildingsets,homecity,objects,nuggets,other] [--side 512]
        [--max 900] [--trigger aoe3bt] [--seed 1]

Only textures tagged `own` are used: never the original game's, which are its publisher's. Only
skins (role diffuse: a texture a model names), 512 pixels and up, so nothing is enlarged. A
texture larger than --side gives several pieces, taken where there is something drawn (a piece
that is mostly the flat ground between the strips is skipped).

Each piece is written as <n>.png with <n>.txt beside it: the trigger word, what it is for, the
material when the name says it. The folder holds the mod's art: it belongs outside any
repository, and so does the LoRA trained on it.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import texture_survey as ts  # noqa: E402
from aoe3game import ddt  # noqa: E402
from core.pngio import encode_png  # noqa: E402

WHAT = {"buildings": "a building", "buildingsets": "a building", "homecity": "a city building",
        "objects": "a map object", "nuggets": "a map object", "units": "a unit", "other": "a model"}


def pick(records, categories, side=512):
    """The records a dataset may use: own, worn by a model, big enough, in the categories, each
    distinct texture once."""
    out, seen = [], set()
    for r in records:
        if "error" in r or r.get("origin") != "own" or r.get("role") != "diffuse":
            continue
        if r["category"] not in categories or min(r["w"], r["h"]) < side or r["md5"] in seen:
            continue
        seen.add(r["md5"])
        out.append(r)
    return out


def drawn(piece, flat=0.45):
    """False for a piece that is mostly one flat colour: the unused ground of an atlas."""
    q = (piece[:, :, :3] // 8).reshape(-1, 3)
    _, counts = np.unique(q, axis=0, return_counts=True)
    return counts.max() / len(q) < flat and float(piece[:, :, :3].std()) > 12.0


def pieces(rgba, side=512, rng=None, per=4):
    """Up to `per` pieces of side x side out of a texture, on a grid, the drawn ones only."""
    h, w = rgba.shape[:2]
    spots = [(y, x) for y in range(0, h - side + 1, side) for x in range(0, w - side + 1, side)]
    if rng is not None:
        rng.shuffle(spots)
    out = []
    for y, x in spots:
        p = rgba[y:y + side, x:x + side]
        if drawn(p):
            out.append(p)
        if len(out) >= per:
            break
    return out


def caption(record, trigger):
    words = [trigger, f"texture of {WHAT.get(record['category'], 'a model')} for a strategy game"]
    if record.get("material"):
        words.append(record["material"])
    words.append("flat even lighting")
    return ", ".join(words)


def build(records, out, categories, side=512, limit=900, trigger="aoe3bt", seed=1):
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(seed)
    chosen = pick(records, categories, side)
    order = rng.permutation(len(chosen))
    n = used = 0
    for i in order:
        r = chosen[int(i)]
        try:
            rgba = ddt.decode(ts._read(*r["at"]), 0)
        except Exception:
            continue
        got = pieces(rgba, side, rng)
        used += bool(got)
        for p in got:
            n += 1
            with open(os.path.join(out, f"{n:05d}.png"), "wb") as fh:
                fh.write(encode_png(np.ascontiguousarray(p[:, :, :3])))
            with open(os.path.join(out, f"{n:05d}.txt"), "w", encoding="utf-8") as fh:
                fh.write(caption(r, trigger))
            if n >= limit:
                return n, used, len(chosen)
    return n, used, len(chosen)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    src = next((a for a in argv if a.lower().endswith(".json")), None)
    out = opt("--out")
    if not src or not out:
        print(__doc__)
        return 2
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    records = ts.name(data["textures"])
    if opt("--models"):
        with open(opt("--models"), encoding="utf-8") as fh:
            ts.mark_use(records, json.load(fh)["models"])
    cats = opt("--categories", "buildings,buildingsets,homecity,objects,nuggets,other").split(",")
    n, used, pool = build(records, out, cats, int(opt("--side", "512")), int(opt("--max", "900")),
                          opt("--trigger", "aoe3bt"), int(opt("--seed", "1")))
    print(f"{n} pieces from {used} of {pool} of the mod's own textures -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
