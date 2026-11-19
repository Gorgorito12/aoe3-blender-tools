# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a preset headless and write it as a game bundle (model, texture, anim file, proto
fields and strings) for `tools/game_deploy.py`.

    python scripts/game_export.py --out DIR [--preset WHITE_HOUSE | --params <building.json>]
                                  [--detail LOW|MEDIUM]
                                  [--prefix mod] [--name NAME] [--display "Shown name"]
                                  [--template House] [--kind BUILDING|PROP] [--folder objects]
                                  [--no-v-flip] [--player-colour]
                                  [--texture DXT3|DXT1|BGRA] [--no-icons] [--no-lowpoly] [--no-damaged]
                                  [--materials] [--ai <strength>] [--ai-seed N] [--ai-url URL]
                                  [--texture-png <file>]  (this texture in place of the painted one)
                                  [--profile <profile.json> | --no-profile] [--proto <protoy.xml>]
    python scripts/game_export.py --out DIR --set GOODS|CAMP [--prefix mod] [--texture-size 256]

--params reads any building's parameters from a JSON file (core/schema.params_to_dict; the
studio writes it). A preset of the PROP style is written as a prop (no stages, rubble or damaged model; treasures in
nuggets, map objects in objects). --set writes a generated prop set: one unit whose models are its
variations, on one texture (core/styles/props/sets.py).

The calibration profile (default: the one shipped in aoe3_blender_tools/profiles/) sets the
obstruction, ground decal, construction stages and rubble from the measured buildings of the same
footprint class. SPECS.md beside the bundle is the building's technical sheet; with --proto it also
shows the game's data (hit points, cost) of its unit or template.

or with Blender: blender -b --factory-startup -P scripts/game_export.py -- [same options]
"""
import dataclasses
import os
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from aoe3_blender_tools.core import blender_io, building, paint  # noqa: E402
from aoe3_blender_tools.core import profile as calibration  # noqa: E402
from aoe3_blender_tools.core import render  # noqa: E402
from aoe3_blender_tools.core.styles import african  # noqa: E402
from aoe3game import bundle  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def write_sheet(out, p, desc, vertices, triangles):
    """SPECS.md beside the bundle: the building's technical sheet and what this export wrote."""
    import spec_sheets
    spec_sheets.write_bundle_sheet(out, p, desc, vertices, triangles, opt("--proto"))


def export_set(out, name):
    """A generated prop set as one bundle: one unit, its variations, one texture."""
    from aoe3_blender_tools.core.styles.props import sets
    bpy.ops.wm.read_factory_settings(use_empty=True)
    models, combined = sets.build_set(name, texture_size=int(opt("--texture-size", "256")))
    texture = paint.paint_rgba(combined)
    meshes, widest = [], (0.0, 0.0)
    for i, m in enumerate(models):
        named = dataclasses.replace(m, params=dataclasses.replace(m.params, name=f"{combined.params.name}_{i}"))
        obj = blender_io.create_object(named, texture)
        positions, normals, uvs, tris = blender_io.game_mesh(obj)
        meshes.append({"positions": positions, "normals": normals, "uvs": uvs, "triangles": tris})
        w = m.dims["footprint"]
        widest = w if w[0] * w[1] > widest[0] * widest[1] else widest
    icon, portrait = (None, None) if "--no-icons" in argv else render.icon_and_portrait(obj)
    desc = bundle.write_set(out, name=combined.params.name, prefix=opt("--prefix", "mod"), models=meshes,
                            texture_rgba=texture, footprint_m=widest, icon_rgba=icon, portrait_rgba=portrait,
                            display_name=opt("--display"), template=opt("--template", "PropsColony"),
                            texture_format=opt("--texture", "DXT3"), folder=opt("--folder", "objects"))
    print(f"{desc['name']}: a set of {desc['set']} models, {sum(len(m['triangles']) for m in meshes)} triangles "
          f"in all; {len(desc['files'])} files in {out}")
    return 0


def main():
    out = opt("--out")
    if not out:
        print(__doc__)
        return 2
    if opt("--set"):
        return export_set(out, opt("--set").upper())
    if opt("--params"):                     # any building, as core/schema.params_to_dict writes it
        import json
        from aoe3_blender_tools.core import schema
        with open(opt("--params"), encoding="utf-8") as fh:
            p = schema.params_from_dict(json.load(fh))
    else:
        p = dataclasses.replace(building.PRESETS[opt("--preset", "WHITE_HOUSE")])
    if opt("--detail"):
        p = dataclasses.replace(p, detail=opt("--detail"))
    if opt("--name"):
        p = dataclasses.replace(p, name=opt("--name"))
    if "--player-colour" in argv:
        p = dataclasses.replace(p, player_colour=True)
    if "--materials" in argv:
        p = dataclasses.replace(p, materials=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    model = building.build(p)
    obj = blender_io.create_object(model, paint.paint_rgba(model) if p.player_colour else paint.paint(model))
    if "--ai" in argv:              # repaint with the local ComfyUI (docs/ai-textures.md)
        from aoe3_blender_tools.core import airepaint, comfy
        repainted, report = airepaint.repaint(blender_io.texture_rgba(obj), model,
                                        comfy.Client(opt("--ai-url", comfy.DEFAULT_URL), timeout=120),
                                        strength=float(opt("--ai", "0.45")), seed=int(opt("--ai-seed", "1")))
        blender_io.set_texture_rgba(obj, repainted)
        print("AI repaint:", ", ".join(r["region"] for r in report if "skipped" not in r))
    if opt("--texture-png"):        # a texture made for this building elsewhere (the studio's AI repaint)
        import numpy as np
        from aoe3_blender_tools.core import pngio
        with open(opt("--texture-png"), "rb") as fh:
            rgba = np.asarray(pngio.read_png(fh.read()))
        if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
            print(f"--texture-png: an RGB or RGBA picture is needed, not {rgba.shape}")
            return 1
        if rgba.shape[2] == 3:
            rgba = np.concatenate([rgba, np.full(rgba.shape[:2] + (1,), 255, np.uint8)], axis=2)
        want = blender_io.texture_rgba(obj).shape[:2]
        if rgba.shape[:2] != want:
            print(f"--texture-png is {rgba.shape[1]} x {rgba.shape[0]}; this building's texture is {want[1]} x {want[0]}")
            return 1
        blender_io.set_texture_rgba(obj, rgba.astype(np.uint8))
        print("texture:", opt("--texture-png"))
    positions, normals, uvs, tris = blender_io.game_mesh(obj)
    icon = portrait = None
    ref = building.reference(p)          # a style guide's reference size and proto template
    obstruction = building.obstruction(p)
    if ref and not opt("--template"):
        argv.extend(["--template", ref[1]])
    if "--no-icons" not in argv:
        icon, portrait = render.icon_and_portrait(obj)
    variants = blender_io.game_variants(obj, lowpoly="--no-lowpoly" not in argv,     # a prop is never damaged
                                        damaged="--no-damaged" not in argv and p.style != "PROP")
    ground = african.ground_decal(p) if p.style == "AFRICAN" else None
    kind, folder = opt("--kind", "BUILDING"), opt("--folder")
    if p.style == "PROP" and not opt("--kind"):           # a generated prop is exported as one
        kind, style_folder = building.STYLES["PROP"].game(building.clamp_params(p))
        folder = folder or style_folder
    texture_max, bump_max = building.texture_budget(p) or (None, None)
    desc = bundle.write(
        out, name=p.name, prefix=opt("--prefix", "mod"), positions=positions, normals=normals,
        uvs=uvs, triangles=tris, texture_rgba=blender_io.texture_rgba(obj),
        bones=blender_io.game_bones(obj), footprint_m=tuple(obj["aoe3_footprint"]),
        icon_rgba=icon, portrait_rgba=portrait, variants=variants,
        display_name=opt("--display"), template=opt("--template", "House"),
        kind=kind, folder=folder,
        v_flip="--no-v-flip" not in argv, texture_format=opt("--texture", "DXT3"), obstruction=obstruction,
        ground_rgba=ground, collision_boxes=building.build(p).boxes, rubble=building.rubble(p), texture_max=texture_max, bump_max=bump_max, profile=None if "--no-profile" in argv else calibration.load(opt("--profile")))
    write_sheet(out, p, desc, len(positions), len(tris))
    print(f"{p.name}: {len(tris)} triangles, {len(positions)} vertices; "
          f"obstruction {desc['size']['radius']}, decal {desc['size']['decal']}, "
          f"stages {desc['size']['stages']}, class {desc['size'].get('class')}; texture "
          f"{desc['texture']['format']}, player colour {desc['texture']['player_colour']}")
    for f in desc["files"]:
        print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
