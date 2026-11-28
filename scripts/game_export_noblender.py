# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental: the game export of scripts/game_export.py without Blender, for a modder who has
none. Same options, same bundle; what Blender did is done here:

    the game mesh         core/gamemesh.py (Blender's triangles, vertices and normals; measured)
    the icon, portrait    core/softrender.py (Blender's camera; its light fitted to Blender's)
    the checks            core/checks.py (the rules core/validate.py applies in Blender)

    python -I scripts/game_export_noblender.py --out DIR [--preset WHITE_HOUSE | --params <building.json>]
        [the other options of scripts/game_export.py] [--compare <bundle made with Blender>]

--compare: a bundle of the same building made by scripts/game_export.py; each file is compared
with it and the differences listed. Whether a bundle made here looks the same in game is still to
verify: Blender stays the default way until it has been seen there.
"""
import dataclasses
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np  # noqa: E402

from aoe3game import bundle  # noqa: E402
from core import building, checks, gamemesh, paint, softrender  # noqa: E402
from core import profile as calibration  # noqa: E402
from core.styles import african  # noqa: E402

argv = sys.argv[1:]
ATTACH_BONES = {"flag_attach": "bone_flag_civ", "chimney_attach": "bone_chimney"}   # as blender_io's


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def textured(model, p):
    return paint.paint_rgba(model) if p.player_colour else paint.paint(model)


def variants(p, model, mesh, texture, lowpoly=True, damaged=True, lowpoly_texture=512):
    """blender_io.game_variants without Blender: the damaged texture on the same mesh, and the
    generator's LOW detail as the low-poly model."""
    out = {}
    if damaged:
        positions, normals, uvs, tris = mesh
        out["damaged"] = {"positions": positions, "normals": normals, "uvs": uvs, "triangles": tris}
        if not building.texture_budget(p):
            out["damaged"]["texture_rgba"] = paint.damaged(model, texture)
    if lowpoly and p.detail != "LOW":
        lp = dataclasses.replace(p, detail="LOW", name=p.name + "_LowPolyTemp",
                                 texture_size=min(lowpoly_texture, p.texture_size))
        lp_model = building.build(lp)
        positions, normals, uvs, tris = gamemesh.mesh(lp_model)
        out["lowpoly"] = {"positions": positions, "normals": normals, "uvs": uvs, "triangles": tris,
                          "texture_rgba": textured(lp_model, lp)}
    return out


def export_set(out, name):
    from core.styles.props import sets
    models, combined = sets.build_set(name, texture_size=int(opt("--texture-size", "256")))
    texture = paint.paint_rgba(combined)
    meshes, widest, last = [], (0.0, 0.0), None
    for m in models:
        positions, normals, uvs, tris = last = gamemesh.mesh(m)
        meshes.append({"positions": positions, "normals": normals, "uvs": uvs, "triangles": tris})
        w = m.dims["footprint"]
        widest = w if w[0] * w[1] > widest[0] * widest[1] else widest
    icon, portrait = (None, None) if "--no-icons" in argv else softrender.icon_and_portrait(*last, texture)
    desc = bundle.write_set(out, name=combined.params.name, prefix=opt("--prefix", "mod"), models=meshes,
                            texture_rgba=texture, footprint_m=widest, icon_rgba=icon, portrait_rgba=portrait,
                            display_name=opt("--display"), template=opt("--template", "PropsColony"),
                            texture_format=opt("--texture", "DXT3"), folder=opt("--folder", "objects"))
    print(f"{desc['name']}: a set of {desc['set']} models, {sum(len(m['triangles']) for m in meshes)} triangles "
          f"in all; {len(desc['files'])} files in {out} (without Blender)")
    return 0


def compare(out, other):
    """Each file of this bundle against the same file of a bundle made with Blender."""
    from aoe3game import ddt
    same, near, differ = [], [], []
    for base, _dirs, files in os.walk(out):
        for f in files:
            mine = os.path.join(base, f)
            rel = os.path.relpath(mine, out)
            theirs = os.path.join(other, rel)
            if not os.path.isfile(theirs):
                differ.append(f"{rel}: not in the Blender bundle")
                continue
            a, b = open(mine, "rb").read(), open(theirs, "rb").read()
            if a == b:
                same.append(rel)
            elif f.lower().endswith(".ddt"):
                x, y = ddt.decode(a, 0).astype(int), ddt.decode(b, 0).astype(int)
                if x.shape != y.shape:
                    differ.append(f"{rel}: {x.shape} against {y.shape}")
                    continue
                share = float((np.abs(x - y).max(axis=2) > 8).mean())
                (near if share < 0.01 else differ).append(f"{rel}: {share:.2%} of the pixels differ by more than 8")
            else:
                differ.append(f"{rel}: {len(a)} bytes against {len(b)}")
    for base, _dirs, files in os.walk(other):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), other)
            if not os.path.isfile(os.path.join(out, rel)):
                differ.append(f"{rel}: only in the Blender bundle")
    print(f"against {other}: {len(same)} files the same byte for byte, {len(near)} pictures nearly the same, "
          f"{len(differ)} different")
    for line in near + differ:
        print("  ", line)
    return {"same": same, "near": near, "differ": differ}


def main():
    out = opt("--out")
    if not out:
        print(__doc__)
        return 2
    if opt("--set"):
        return export_set(out, opt("--set").upper())
    if opt("--params"):
        from core import schema
        with open(opt("--params"), encoding="utf-8") as fh:
            p = schema.params_from_dict(json.load(fh))
    else:
        key = opt("--preset", "WHITE_HOUSE")
        if key not in building.PRESETS:
            print(f"no preset {key}")
            return 2
        p = dataclasses.replace(building.PRESETS[key])
    if opt("--detail"):
        p = dataclasses.replace(p, detail=opt("--detail"))
    if opt("--name"):
        p = dataclasses.replace(p, name=opt("--name"))
    if "--player-colour" in argv:
        p = dataclasses.replace(p, player_colour=True)
    if "--materials" in argv:
        p = dataclasses.replace(p, materials=True)
    model = building.build(p)
    texture = textured(model, p)
    if "--ai" in argv:
        from core import airepaint, comfy
        texture, report = airepaint.repaint(texture, model, comfy.Client(opt("--ai-url", comfy.DEFAULT_URL), timeout=120),
                                            strength=float(opt("--ai", "0.45")), seed=int(opt("--ai-seed", "1")),
                                            **airepaint.lora_args(opt("--ai-lora"), opt("--ai-lora-strength"), opt("--ai-extra")))
        print("AI repaint:", ", ".join(r["region"] for r in report if "skipped" not in r))
    if opt("--texture-png"):
        from core import pngio
        with open(opt("--texture-png"), "rb") as fh:
            rgba = np.asarray(pngio.read_png(fh.read()))
        if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
            print(f"--texture-png: an RGB or RGBA picture is needed, not {rgba.shape}")
            return 1
        if rgba.shape[2] == 3:
            rgba = np.concatenate([rgba, np.full(rgba.shape[:2] + (1,), 255, np.uint8)], axis=2)
        if rgba.shape[:2] != texture.shape[:2]:
            print(f"--texture-png is {rgba.shape[1]} x {rgba.shape[0]}; this building's texture is "
                  f"{texture.shape[1]} x {texture.shape[0]}")
            return 1
        texture = rgba.astype(np.uint8)
        print("texture:", opt("--texture-png"))

    prof = None if "--no-profile" in argv else calibration.load(opt("--profile"))
    prop = None
    if p.style == "PROP" and prof is not None:
        _kind, folder = building.STYLES["PROP"].game(building.clamp_params(p))
        prop = calibration.prop_group(folder or "objects")
    found = checks.check(checks.mesh_of(model, texture.shape), 6000, prof, prop)
    for level, message in found:
        if level != checks.INFO:
            print(f"check: {level} {message}")

    mesh = gamemesh.mesh(model)
    positions, normals, uvs, tris = mesh
    ref = building.reference(p)
    if ref and not opt("--template"):
        argv.extend(["--template", ref[1]])
    icon = portrait = None
    if "--no-icons" not in argv:
        icon, portrait = softrender.icon_and_portrait(positions, normals, uvs, tris, texture)
    var = variants(p, model, mesh, texture, lowpoly="--no-lowpoly" not in argv,
                   damaged="--no-damaged" not in argv and p.style != "PROP")
    ground = african.ground_decal(p) if p.style == "AFRICAN" else None
    kind, folder = opt("--kind", "BUILDING"), opt("--folder")
    if p.style == "PROP" and not opt("--kind"):
        kind, style_folder = building.STYLES["PROP"].game(building.clamp_params(p))
        folder = folder or style_folder
    texture_max, bump_max = building.texture_budget(p) or (None, None)
    bones = [(ATTACH_BONES.get(name.split(".")[0], name), tuple(loc)) for name, loc in sorted(model.attach.items())]
    desc = bundle.write(
        out, name=p.name, prefix=opt("--prefix", "mod"), positions=positions, normals=normals,
        uvs=uvs, triangles=tris, texture_rgba=texture, bones=bones,
        footprint_m=tuple(model.dims["footprint"]), icon_rgba=icon, portrait_rgba=portrait, variants=var,
        display_name=opt("--display"), template=opt("--template", "House"), kind=kind, folder=folder,
        v_flip="--no-v-flip" not in argv, texture_format=opt("--texture", "DXT3"),
        obstruction=building.obstruction(p), ground_rgba=ground, collision_boxes=model.boxes,
        rubble=building.rubble(p), texture_max=texture_max, bump_max=bump_max, profile=prof, height=model.height)
    import spec_sheets
    spec_sheets.write_bundle_sheet(out, p, desc, len(positions), len(tris), opt("--proto"))
    print(f"{p.name}: {len(tris)} triangles, {len(positions)} vertices; "
          f"obstruction {desc['size']['radius']}, decal {desc['size']['decal']}, "
          f"stages {desc['size']['stages']}, class {desc['size'].get('class')}; texture "
          f"{desc['texture']['format']}, player colour {desc['texture']['player_colour']} (without Blender)")
    for f in desc["files"]:
        print("  ", f)
    if opt("--compare"):
        compare(out, opt("--compare"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
