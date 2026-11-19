# SPDX-License-Identifier: GPL-3.0-or-later
"""A static model of your own (.obj with its .mtl, .glb or .gltf) as a game bundle, without Blender:
the same files as scripts/game_export.py writes for a generated building (the .gr2, its .ddt
texture and bump map, the anim file, icon and portrait, the proto and string entries).

    python -I scripts/mesh_to_game.py --in <model> --out <dir> --name <Name>
        [--up y|z] [--scale F | --fit METRES | --fit-units N] [--turn 0|90|180|270] [--flat]
        [--texture-png <file.png>] [--kind BUILDING|PROP] [--folder buildings]
        [--template House] [--prefix mod] [--display "Shown name"] [--texture DXT3|DXT1|BGRA]
        [--no-icons] [--no-profile] [--check-only]

--up: the file's vertical axis (OBJ and glTF: y). --scale multiplies the file's units into metres
(a model in centimetres: 0.01); --fit makes the plot's longer side that many metres instead;
--fit-units that many game units (a building of the game's 4x4 class: 4; its obstruction is a
little smaller, as the stock buildings' are).
--turn faces it another way. --texture-png replaces the model's picture (a JPEG one must be
converted, or given here as PNG). --check-only prints the checks and writes nothing.

Refused, with the reason: no texture coordinates, two pictures (the game takes one per model),
Draco or meshopt compression, a skin (a unit with bones). An imported model has no low-poly or
damaged variant and no technical sheet: those come from the generator.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import numpy as np  # noqa: E402

from aoe3game import bundle  # noqa: E402
from core import checks, meshprep, pngio, softrender  # noqa: E402
from core import profile as calibration  # noqa: E402
from core.objio import MeshError  # noqa: E402


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    src, out, name = opt("--in"), opt("--out"), opt("--name")
    if not src or not name or not (out or "--check-only" in argv):
        print(__doc__)
        return 2
    if not name.replace("_", "").isalnum():
        print(f"--name: letters, digits and _ only, not {name!r}")
        return 2
    try:
        mesh = meshprep.load(src)
        rgba = None
        if opt("--texture-png"):
            with open(opt("--texture-png"), "rb") as fh:
                rgba = np.asarray(pngio.read_png(fh.read()))
        texture = meshprep.texture_rgba(mesh, rgba)
        prep = meshprep.prepare(mesh, up=opt("--up", "y"), scale=float(opt("--scale", "1")),
                                fit=float(opt("--fit")) if opt("--fit") else
                                (float(opt("--fit-units")) / bundle.UNITS_PER_METER if opt("--fit-units") else None),
                                turn=int(opt("--turn", "0")), flat="--flat" in argv)
    except (MeshError, OSError, ValueError) as e:
        print(f"refused: {e}")
        return 1
    for w in prep["warnings"]:
        print(f"warning: {w}")
    w, d = prep["footprint"]
    print(f"{name}: {len(prep['triangles'])} triangles, {len(prep['positions'])} vertices; "
          f"{w:.2f} x {d:.2f} m ({w * bundle.UNITS_PER_METER:.2f} x {d * bundle.UNITS_PER_METER:.2f} game units), "
          f"{prep['height']:.2f} m tall; texture {texture.shape[1]} x {texture.shape[0]}")
    prof = None if "--no-profile" in argv else calibration.load(opt("--profile"))
    kind = opt("--kind", "BUILDING").upper()
    if kind not in ("BUILDING", "PROP"):
        print("--kind: BUILDING or PROP")
        return 2
    prop = calibration.prop_group(opt("--folder") or "objects") if kind == "PROP" and prof is not None else None
    bad = 0
    for level, message in checks.check(meshprep.check_mesh(prep, texture.shape), 6000, prof, prop):
        print(f"check: {level} {message}")
        bad += level == checks.ERROR
    if "--check-only" in argv:
        return 1 if bad else 0
    icon = portrait = None
    if "--no-icons" not in argv:
        icon, portrait = softrender.icon_and_portrait(prep["positions"], prep["normals"], prep["uvs"],
                                                      prep["triangles"], texture)
    desc = bundle.write(
        out, name=name, prefix=opt("--prefix", "mod"), positions=prep["positions"], normals=prep["normals"],
        uvs=prep["uvs"], triangles=prep["triangles"], texture_rgba=texture, footprint_m=prep["footprint"],
        icon_rgba=icon, portrait_rgba=portrait, display_name=opt("--display"),
        template=opt("--template", "House"), kind=kind, folder=opt("--folder"),
        texture_format=opt("--texture", "DXT3"), profile=prof)
    print(f"obstruction {desc['size']['radius']}, texture {desc['texture']['format']}, "
          f"player colour {desc['texture']['player_colour']}")
    for f in desc["files"]:
        print("  ", f)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
