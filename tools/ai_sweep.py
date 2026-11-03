# SPDX-License-Identifier: GPL-3.0-or-later
"""Repaints presets with the local ComfyUI at several strengths and seeds, without Blender, and
measures each result: how far the edges moved, how far the mean colour drifted, and the local
contrast against the stock textures' (tools/palette_survey.py). Development tool.

    venv\\Scripts\\python -I tools\\ai_sweep.py --out <folder> [--presets COLONIAL_HOUSE,TIMBER_HOUSE]
        [--strengths 0.3,0.45,0.6] [--seeds 1,2] [--regions front,roof] [--size 512] [--url ...]

Writes <out>/<preset>_s<strength>_seed<seed>.png (the texture), <preset>_original.png and
report.json; prints one line per result.
"""
import dataclasses
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from core import airepaint, building, comfy, paint  # noqa: E402
from core.pngio import encode_png  # noqa: E402
import palette_survey  # noqa: E402


def main(argv):
    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    out = opt("--out", os.path.join(ROOT, "out", "ai_sweep"))
    presets = opt("--presets", "COLONIAL_HOUSE,COLONIAL_TRADING_HOUSE,TIMBER_HOUSE,TIMBER_INN,WHITE_HOUSE").split(",")
    strengths = [float(x) for x in opt("--strengths", "0.3,0.45,0.6").split(",")]
    seeds = [int(x) for x in opt("--seeds", "1,2").split(",")]
    regions = opt("--regions", None)
    regions = regions.split(",") if regions else None
    size = int(opt("--size", "1024"))
    client = comfy.Client(opt("--url", comfy.DEFAULT_URL), timeout=120)
    problems = client.check()
    if problems:
        raise SystemExit("; ".join(problems))
    os.makedirs(out, exist_ok=True)
    rows = []
    for key in presets:
        p = dataclasses.replace(building.PRESETS[key], texture_size=size, player_colour=True)
        model = building.build(p)
        tex = paint.paint_rgba(model)
        with open(os.path.join(out, f"{key.lower()}_original.png"), "wb") as f:
            f.write(encode_png(tex))
        for st in strengths:
            for seed in seeds:
                t0 = time.time()
                new, report = airepaint.repaint(tex, model, client, strength=st, seed=seed, regions=regions)
                secs = time.time() - t0
                name = f"{key.lower()}_s{st:.2f}_seed{seed}.png"
                with open(os.path.join(out, name), "wb") as f:
                    f.write(encode_png(new))
                per = []
                for r in report:
                    if "skipped" in r:
                        continue
                    x0, y0, x1, y1 = airepaint.region_rect(model, tex, r["region"])
                    a, b = tex[y0:y1, x0:x1], new[y0:y1, x0:x1]
                    per.append({"region": r["region"], "shift": airepaint.edge_shift(a, b),
                                "colour": float(np.abs(a[:, :, :3].reshape(-1, 3).mean(0)
                                                       - b[:, :, :3].reshape(-1, 3).mean(0)).max()),
                                "contrast_before": round(palette_survey.measure(a)["contrast"], 3),
                                "contrast_after": round(palette_survey.measure(b)["contrast"], 3)})
                moved = [x["region"] for x in per if tuple(x["shift"]) != (0, 0)]
                row = {"preset": key, "strength": st, "seed": seed, "seconds": round(secs, 1), "file": name,
                       "regions": per, "moved": moved}
                rows.append(row)
                c0 = np.mean([x["contrast_before"] for x in per]) if per else 0
                c1 = np.mean([x["contrast_after"] for x in per]) if per else 0
                print(f"{key} s={st} seed={seed}: {len(per)} regions in {secs:.0f} s; moved {moved or 'none'}; "
                      f"contrast {c0:.3f} -> {c1:.3f}")
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
