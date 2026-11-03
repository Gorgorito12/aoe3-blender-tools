# SPDX-License-Identifier: GPL-3.0-or-later
"""Measures the stock building textures: mean colour and local contrast, the targets the material
swatches are fitted to (core/materials.py TARGET_CONTRAST). Development tool; it reads the
archives of a game copy and prints numbers, it writes nothing.

    venv\\Scripts\\python -I tools\\palette_survey.py <Art*.bar> [...] [--filter buildings] [--limit 80]

Local contrast: the standard deviation of the luminance minus its 9 x 9 box blur, over the mean
luminance, on opaque pixels of mip level 1 (half size). It is the fine grain a texture carries
once its large shapes (windows, beams, courses) are taken away.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import ddt  # noqa: E402
import bar  # noqa: E402

SKIP = ("icon", "portrait", "normal", "_b.ddt", "ground", "decal", "bump", "spec", "selection",
        "construct", "shadow", "_n.ddt")


def box_blur(a, r):
    """Mean over a (2r+1) square, edges wrapped."""
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += np.roll(np.roll(a, dy, 0), dx, 1)
    return out / (2 * r + 1) ** 2


def measure(rgba):
    rgb = rgba[:, :, :3].astype(np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    opaque = rgba[:, :, 3] > 250
    if opaque.sum() < 64:
        opaque = np.ones_like(opaque)
    fine = lum - box_blur(lum, 4)
    mean = float(lum[opaque].mean())
    return {"mean_rgb": [round(float(c), 1) for c in rgb[opaque].mean(axis=0)],
            "contrast": float(fine[opaque].std()) / max(mean, 1.0)}


def main(argv):
    flt = argv[argv.index("--filter") + 1].lower() if "--filter" in argv else "buildings"
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 80
    bars = [a for a in argv if a.lower().endswith(".bar")]
    rows = []
    for path in bars:
        entries = bar.read_entries(path)
        with open(path, "rb") as f:
            for name, off, size in entries:
                low = name.lower()
                if flt not in low or not low.endswith(".ddt") or any(s in low for s in SKIP):
                    continue
                f.seek(off)
                data = f.read(size)
                try:
                    hd = ddt.read_header(data)
                    rgba = ddt.decode(data, 1 if len(hd.levels) > 1 else 0)
                except Exception as exc:          # a format this reader does not know: report it
                    print(f"skip {name}: {exc}")
                    continue
                m = measure(rgba)
                rows.append((name, m))
                print(f"{m['contrast']:.4f}  {m['mean_rgb']}  {name}")
                if len(rows) >= limit:
                    break
        if len(rows) >= limit:
            break
    if rows:
        c = sorted(m["contrast"] for _, m in rows)
        print(f"\n{len(rows)} textures: local contrast median {np.median(c):.4f}, "
              f"25 % {np.percentile(c, 25):.4f}, 75 % {np.percentile(c, 75):.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
