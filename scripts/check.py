# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the game-ready checks on a building, headless: what the add-on's Check button does
(core/validate.py: the triangle budget measured for its footprint class, overlapping faces,
UVs outside their region, repeated corners, normals...).

    python scripts/check.py [--preset WHITE_HOUSE | --params <building.json>] [--detail LOW|MEDIUM]
                            [--budget 6000] [--no-profile] [--json] [--no-blender]

Prints one line per finding (ERROR, WARNING or INFO); with --json, one JSON object per line
({"level", "message"}) for the studio to read. Exit status 1 when there is an error.

or with Blender: blender -b --factory-startup -P scripts/check.py -- [same options]

Without Blender (no bpy module), or with --no-blender, the same rules run on the generator's own
mesh (core/checks.py, triangulated as Blender's modifier does): the same findings on every preset
at both details (tests/run_tests.py holds them together).
"""
import dataclasses
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:                                        # Blender, or the bpy module
    import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)
    sys.path.insert(0, ROOT)
    from aoe3_blender_tools.core import blender_io, building, checks, paint, validate  # noqa: E402
    from aoe3_blender_tools.core import profile as calibration  # noqa: E402
except ImportError:                         # without Blender: the same rules on the generator's own mesh
    bpy = None
    sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
    from core import building, checks, paint  # noqa: E402
    from core import profile as calibration  # noqa: E402

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
    model = building.build(p)
    texture = paint.paint_rgba(model) if p.player_colour else paint.paint(model)
    prof = None if "--no-profile" in argv else calibration.load()
    prop = None
    if p.style == "PROP" and prof is not None:       # a prop is held to the game's own props
        _kind, folder = building.STYLES["PROP"].game(building.clamp_params(p))
        prop = calibration.prop_group(folder or "objects")
    if bpy is not None and "--no-blender" not in argv:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj = blender_io.create_object(model, texture)
        found = validate.check(obj, int(opt("--budget", "6000")), prof, prop)
    else:                                   # core/checks.py: the same findings (measured on every preset)
        found = checks.check(checks.mesh_of(model, texture.shape), int(opt("--budget", "6000")), prof, prop)
    for level, message in found:
        print(json.dumps({"level": level, "message": message}) if "--json" in argv else f"{level:8} {message}")
    errors = sum(1 for level, _ in found if level == checks.ERROR)
    warnings = sum(1 for level, _ in found if level == checks.WARNING)
    if "--json" not in argv:
        print(f"{p.name}: {errors} errors, {warnings} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
