# SPDX-License-Identifier: GPL-3.0-or-later
"""A building bundle: the model (.gr2), its texture (.ddt), icon and portrait, the anim file and
`bundle.json` (the proto fields and strings), at the paths the game expects:

    <out>/art/<prefix>/buildings/<name>/<name>.gr2 | .ddt | .xml | _icon.ddt | _portrait.ddt
    <out>/bundle.json

`deploy.Deployment.apply` puts it into a test copy of the game.

Sizes in the game: the stock buildings declare 0.615157485 model units per metre, and the game's
distances (obstruction radii, decal sizes) are in those units. Calibration values (measured on
the stock and mod buildings; the survey's profile can override them):
- obstruction half-side = OBSTRUCTION_RATIO x the model's half-side (stock house: 2.0 for 2.38);
- ground decal side = DECAL_RATIO x the model's side (stock house: 6.0 for 4.76).
"""
import json
import os

from . import animxml, ddt, gr2_write

UNITS_PER_METER = gr2_write.STOCK_BASIS["units_per_meter"]
OBSTRUCTION_RATIO = 0.85
DECAL_RATIO = 1.25
FLAT_BUMP_TEXTURE = r"C:\aoe3bt\art\shadows_selections\flat_normal_black_spec.ddt"
RUBBLE = {"2x2": "BuildingRubble2x2", "3x3": "BuildingRubble3x3", "4x4": "BuildingRubble4x4",
          "5x5": "BuildingRubble5x5", "6x6": "BuildingRubble6x6"}


def game_size(footprint_m, units_per_meter=UNITS_PER_METER, profile=None):
    """Obstruction radii, decal size, stage set and rubble for a footprint in metres. With a
    calibration profile (an object with footprint_class, obstruction_ratio, decal_ratio,
    stages and rubble, as core.profile.Profile), its measured ratios replace the defaults."""
    w, d = (footprint_m[0] * units_per_meter, footprint_m[1] * units_per_meter)
    cls = profile.footprint_class(*footprint_m) if profile is not None else None
    ratio = (profile.obstruction_ratio(cls) if cls else None) or OBSTRUCTION_RATIO
    dratio = (profile.decal_ratio(cls) if cls else None) or DECAL_RATIO
    rx, rz = round(w / 2 * ratio, 2), round(d / 2 * ratio, 2)
    stages = (profile.stages(cls) if cls else None) or animxml.stage_class(2 * rx, 2 * rz)
    rubble = (profile.rubble(cls) if cls else None) or RUBBLE.get(stages, "BuildingRubble4x4")
    return {"radius": (rx, rz), "decal": (round(w * dratio, 2), round(d * dratio, 2)),
            "stages": stages, "rubble": rubble, "class": cls,
            "placement": "buildinglarge.xml" if max(rx, rz) >= 3 else "buildingsmall.xml"}


def write(out, *, name, prefix, positions, normals, uvs, triangles, texture_rgba, bones=(),
          footprint_m, icon_rgba=None, portrait_rgba=None, display_name=None, rollover="",
          template="House", v_flip=True, player_colour=False, chimney_bone=None, profile=None):
    """Writes the bundle into `out` and returns the bundle description."""
    low = name.lower()
    rel_dir = f"{prefix}\\buildings\\{low}"
    art_dir = os.path.join(out, "art", prefix, "buildings", low)
    os.makedirs(art_dir, exist_ok=True)
    size = game_size(footprint_m, profile=profile)
    texture_name = f"C:\\aoe3bt\\art\\{rel_dir}\\{low}.ddt"
    model = gr2_write.static_model(name, positions, normals, uvs, triangles,
                                   texture=texture_name, bump=FLAT_BUMP_TEXTURE, bones=bones,
                                   v_flip=v_flip, player_colour=player_colour,
                                   source=f"{low}.blend")
    with open(os.path.join(art_dir, low + ".gr2"), "wb") as f:
        f.write(model)
    with open(os.path.join(art_dir, low + ".ddt"), "wb") as f:
        f.write(ddt.write_bgra(texture_rgba, alpha=1, usage=0, mips=True))
    unit = {"AnimFile": f"{rel_dir}\\{low}.xml",
            "ObstructionRadiusX": "%.4f" % size["radius"][0],
            "ObstructionRadiusZ": "%.4f" % size["radius"][1],
            "DeadReplacement": size["rubble"], "PlacementFile": size["placement"]}
    if icon_rgba is not None:
        with open(os.path.join(art_dir, low + "_icon.ddt"), "wb") as f:
            f.write(ddt.write_bgra(icon_rgba, alpha=1, usage=1, mips=False))
        unit["Icon"] = f"{rel_dir}\\{low}_icon"
    if portrait_rgba is not None:
        with open(os.path.join(art_dir, low + "_portrait.ddt"), "wb") as f:
            f.write(ddt.write_bgra(portrait_rgba, alpha=1, usage=0, mips=False))
        unit["PortraitIcon"] = f"{rel_dir}\\{low}_portrait"
    bone_names = [b for b, _ in bones]
    anim = animxml.building(name, f"{rel_dir}\\{low}", decal=size["decal"],
                            stages=size["stages"],
                            bones=[b for b in bone_names if b != chimney_bone],
                            chimney_bone=chimney_bone if chimney_bone in bone_names else None)
    with open(os.path.join(art_dir, low + ".xml"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(anim)
    display = display_name or name
    desc = {"name": name, "template": template, "unit": unit, "size": size,
            "strings": {"DisplayNameID": display, "EditorNameID": display,
                        "RolloverTextID": rollover or display,
                        "ShortRolloverTextID": rollover or display},
            "files": sorted(os.path.relpath(os.path.join(art_dir, f), out)
                            for f in os.listdir(art_dir))}
    with open(os.path.join(out, "bundle.json"), "w", encoding="utf-8") as f:
        json.dump(desc, f, indent=1)
    return desc
