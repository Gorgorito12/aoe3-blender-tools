# SPDX-License-Identifier: GPL-3.0-or-later
"""Writes the technical sheet of every preset into docs/specs/, and their index.

    venv\\Scripts\\python -I tools\\spec_sheets.py [--out <folder>] [--only <PRESET> ...] [--proto <protoy.xml>]

Run it after changing a building: tests/test_specs.py fails until the sheets match the models.
With --proto a sheet also shows the game's data (hit points, cost) of its unit or template. Those
numbers are the game's or the mod's: use it with --out outside the repository, never in docs/specs/.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import shape_survey  # noqa: E402
from aoe3game import bundle  # noqa: E402
from core import building, profile, specs  # noqa: E402
from core.styles import african  # noqa: E402
from core.styles.african import sizes  # noqa: E402

OUT = os.path.join(ROOT, "docs", "specs")


def game_side(params, prof):
    """What an export would give the game: sizes, template, the class's table of shapes."""
    from dataclasses import replace
    model = building.build(replace(params, detail="MEDIUM"))
    ref = building.reference(params)
    obstruction = (ref[0], ref[0]) if ref else None
    size = bundle.game_size(model.dims["footprint"], profile=prof, obstruction=obstruction)
    if params.style == "AFRICAN" and african.ground_decal(african.clamp(params), 8) is not None:
        size["decal"] = tuple(round(v * bundle.GROUND_MARGIN, 2) for v in size["decal"])
    return size, (ref[1] if ref else "House"), model


def style_side(params):
    """A style's triangle target and how much it scales its plan."""
    if params.style != "AFRICAN":
        return None, 1.0
    return (sizes.tris_target(params.building_type, params.architecture),
            sizes.scale(params.building_type, params.architecture))


def shape_of(model, size, prof):
    """The numbers tools/shape_survey.py gives a real model, and its class's table."""
    pts, tris = [], []
    for f in model.faces:
        n = len(pts)
        pts += [tuple(c * bundle.UNITS_PER_METER for c in q) for q in f.pts]
        tris += [(n, n + i, n + i + 1) for i in range(1, len(f.pts) - 1)]
    V, T = np.array(pts, np.float32), np.array(tris)
    facts = {"upm": shape_survey.UNITS_PER_METER, "up": (0.0, 0.0, 1.0), "textures": 1, "materials": 1}
    rx, rz = size["radius"]
    s = shape_survey.measure(V, np.zeros((len(V), 2), np.float32), T, facts, rx, rz)
    table = prof.data["shape"]
    cls = size.get("class") if size.get("class") in table else "all"
    return s, (cls, table[cls])


def facts_of(key, prof):
    params = building.PRESETS[key]
    size, template, model = game_side(params, prof)
    band, scale = style_side(params)
    return specs.facts(params, size, template, bundle.UNITS_PER_METER, key=key, collision=bundle.COLLISION_SHAPE,
                       shape=shape_of(model, size, prof), band=band, scale=scale)


def sheet(key, prof=None, proto=None):
    """The Markdown of a preset's sheet."""
    f = facts_of(key, prof or profile.load())
    return specs.render(f, proto=specs.proto_of(proto, f["name"], f["template"]) if proto else None), f


def index(rows):
    """docs/specs/README.md."""
    upm = bundle.UNITS_PER_METER
    out = ["# Technical sheets", "",
           "One sheet per building, computed from the model by `tools/spec_sheets.py`. Do not edit them:",
           "after changing a building, run the tool. `tests/test_specs.py` fails on a missing or old sheet.",
           "", "Sizes are game units.", "",
           "| Building | Triangles | Low | Width | Depth | Height | Obstruction |", "|---|---|---|---|---|---|---|"]
    for f in sorted(rows, key=lambda r: r["name"]):
        w, d, h = (v * upm for v in f["size_m"])
        rx, rz = f["game"]["radius"]
        out.append(f"| [{f['name']}]({f['name']}.md) | {f['tris']:,} | {f['tris_low']:,} | {w:.2f} | {d:.2f} | "
                   f"{h:.2f} | {2 * rx:g} x {2 * rz:g} |")
    return "\n".join(out) + "\n"


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else OUT
    proto_path = argv[argv.index("--proto") + 1] if "--proto" in argv else None
    only = argv[argv.index("--only") + 1:] if "--only" in argv else None
    if proto_path and os.path.abspath(out) == os.path.abspath(OUT):
        raise SystemExit("--proto brings a game's numbers: use --out outside the repository")
    proto = None
    if proto_path:
        with open(proto_path, encoding="utf-8", errors="ignore") as fh:
            proto = fh.read()
    os.makedirs(out, exist_ok=True)
    prof, rows = profile.load(), []
    for key in only or building.PRESETS:
        text, f = sheet(key, prof, proto)
        with open(os.path.join(out, f["name"] + ".md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        rows.append(f)
    if not only:
        with open(os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(index(rows))
    print(f"{len(rows)} sheets in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
