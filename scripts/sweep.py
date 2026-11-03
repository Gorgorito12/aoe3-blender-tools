# SPDX-License-Identifier: GPL-3.0-or-later
"""Random parameter sweep: builds many buildings with random options and runs the game-ready checks
on each. It found the edge cases the fixed tests missed (overlapping posts, chimneys, windows and
column bases on small or narrow buildings).

    python scripts/sweep.py [--count N] [--seeds 2026,7,99] [--style NEOCLASSICAL|COLONIAL|ALL]

Prints the failing cases (at most 10) and exits with status 1 when any fails. About 0.25 s a case.
"""
import os
import random
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aoe3_blender_tools.core import blender_io, building, paint, validate  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
count = int(argv[argv.index("--count") + 1]) if "--count" in argv else 200
seeds = [int(x) for x in argv[argv.index("--seeds") + 1].split(",")] if "--seeds" in argv else [2026, 7, 99]
style = (argv[argv.index("--style") + 1] if "--style" in argv else "ALL").upper()


def random_params(rng, i):
    p = building.BuildingParams(
        name=f"Sweep{i}", width=rng.uniform(5, 30), depth=rng.uniform(4, 18), storeys=rng.randint(1, 4),
        plinth=rng.choice([0.3, 0.8, 1.5]), roof_pitch=rng.uniform(0.2, 1.2), bay_spacing=rng.uniform(1.4, 3.0),
        portico=rng.random() < 0.6, columns=rng.choice([2, 4, 6, 8]), column_spacing=rng.uniform(1.2, 3.0),
        portico_depth=rng.uniform(1.5, 6), cupola=rng.random() < 0.4, chimneys=rng.randint(0, 8),
        side_bays=rng.choice([0, 1, 2, 3, 6]), detail=rng.choice(["LOW", "MEDIUM"]), texture_size=256,
        back_portico=rng.choice(["NONE", "BOW"]), bow_radius=rng.uniform(1.0, 8.0), bow_columns=rng.randint(2, 10),
        wings=rng.random() < 0.4, wing_gap=rng.uniform(2, 9), wing_width=rng.uniform(3, 10),
        wing_depth=rng.uniform(3, 10), flagpole=rng.random() < 0.4, shutters=rng.random() < 0.5,
        window_caps=rng.choice(["PEDIMENT", "ALTERNATE"]))
    if rng.random() < 0.1:           # square plans: the hipped roofs become pyramids
        p.depth, p.wing_depth = p.width, p.wing_width
    p.materials = rng.random() < 0.3      # swatches under the painting
    return p


def main():
    bad = []
    total = 0
    for seed in seeds:
        rng = random.Random(seed)
        for i in range(count):
            if style == "COLONIAL" or (style == "ALL" and i % 3 == 2):
                p = building.STYLES["COLONIAL"].random_params(rng, i, building.BuildingParams)
            else:
                p = random_params(rng, i)
            total += 1
            try:
                bpy.ops.wm.read_factory_settings(use_empty=True)
                model = building.build(p)
                obj = blender_io.create_object(model, paint.paint(model))
                probs = [(lv, m) for lv, m in validate.check(obj) if lv != validate.INFO]
            except Exception as exc:     # a sweep reports, it does not stop
                probs = [("EXCEPTION", repr(exc))]
            if probs:
                bad.append((seed, i, p, probs))
    for seed, i, p, probs in bad[:10]:
        shown = {k: round(v, 2) if isinstance(v, float) else v for k, v in p.__dict__.items()
                 if k not in ("colors", "name", "seed", "texture_size")}
        print(f"seed {seed} case {i}: {probs}\n    {shown}")
    print(f"{len(bad)} of {total} cases failed")
    sys.exit(1 if bad else 0)


main()
