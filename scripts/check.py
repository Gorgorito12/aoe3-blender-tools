# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the game-ready checks on a building, headless: what the add-on's Check button does
(core/validate.py: the triangle budget measured for its footprint class, overlapping faces,
UVs outside their region, repeated corners, normals...).

    python scripts/check.py [--preset WHITE_HOUSE | --params <building.json>] [--detail LOW|MEDIUM]
                            [--budget 6000] [--no-profile] [--json]

Prints one line per finding (ERROR, WARNING or INFO); with --json, one JSON object per line
({"level", "message"}) for the studio to read. Exit status 1 when there is an error.

or with Blender: blender -b --factory-startup -P scripts/check.py -- [same options]
"""
import dataclasses
import json
import os
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aoe3_blender_tools.core import blender_io, building, paint, validate  # noqa: E402
from aoe3_blender_tools.core import profile as calibration  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main():
    if opt("--params"):
        from aoe3_blender_tools.core import schema
        with open(opt("--params"), encoding="utf-8") as fh:
            p = schema.params_from_dict(json.load(fh))
    else:
        key = opt("--preset", "WHITE_HOUSE")
        if key not in building.PRESETS:
            print(f"no preset {key}")
            return 2
        p = building.PRESETS[key]
    if opt("--detail"):
        p = dataclasses.replace(p, detail=opt("--detail"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    model = building.build(p)
    obj = blender_io.create_object(model, paint.paint_rgba(model) if p.player_colour else paint.paint(model))
    prof = None if "--no-profile" in argv else calibration.load()
    prop = None
    if p.style == "PROP" and prof is not None:       # a prop is held to the game's own props
        _kind, folder = building.STYLES["PROP"].game(building.clamp_params(p))
        prop = calibration.prop_group(folder or "objects")
    found = validate.check(obj, int(opt("--budget", "6000")), prof, prop)
    for level, message in found:
        print(json.dumps({"level": level, "message": message}) if "--json" in argv else f"{level:8} {message}")
    errors = sum(1 for level, _ in found if level == validate.ERROR)
    warnings = sum(1 for level, _ in found if level == validate.WARNING)
    if "--json" not in argv:
        print(f"{p.name}: {errors} errors, {warnings} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
