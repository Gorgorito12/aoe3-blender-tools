# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a preset headless and write it as a game bundle (model, texture, anim file, proto
fields and strings) for `tools/game_deploy.py`.

    python scripts/game_export.py --out DIR [--preset WHITE_HOUSE] [--detail LOW|MEDIUM]
                                  [--prefix mod] [--name NAME] [--display "Shown name"]
                                  [--template House] [--no-v-flip] [--player-colour]
                                  [--profile <profile.json> | --no-profile]

The calibration profile (default: the one shipped in aoe3_blender_tools/profiles/) sets the
obstruction, ground decal, construction stages and rubble from the measured buildings of the same
footprint class.

or with Blender: blender -b --factory-startup -P scripts/game_export.py -- [same options]
"""
import dataclasses
import os
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

from aoe3_blender_tools.core import blender_io, building, paint  # noqa: E402
from aoe3_blender_tools.core import profile as calibration  # noqa: E402
from aoe3game import bundle  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main():
    out = opt("--out")
    if not out:
        print(__doc__)
        return 2
    key = opt("--preset", "WHITE_HOUSE")
    p = dataclasses.replace(building.PRESETS[key])
    if opt("--detail"):
        p = dataclasses.replace(p, detail=opt("--detail"))
    if opt("--name"):
        p = dataclasses.replace(p, name=opt("--name"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    model = building.build(p)
    obj = blender_io.create_object(model, paint.paint(model))
    positions, normals, uvs, tris = blender_io.game_mesh(obj)
    desc = bundle.write(
        out, name=p.name, prefix=opt("--prefix", "mod"), positions=positions, normals=normals,
        uvs=uvs, triangles=tris, texture_rgba=blender_io.texture_rgba(obj),
        bones=blender_io.game_bones(obj), footprint_m=tuple(obj["aoe3_footprint"]),
        display_name=opt("--display"), template=opt("--template", "House"),
        v_flip="--no-v-flip" not in argv, player_colour="--player-colour" in argv,
        profile=None if "--no-profile" in argv else calibration.load(opt("--profile")))
    print(f"{p.name}: {len(tris)} triangles, {len(positions)} vertices; "
          f"obstruction {desc['size']['radius']}, decal {desc['size']['decal']}, "
          f"stages {desc['size']['stages']}, class {desc['size'].get('class')}")
    for f in desc["files"]:
        print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
