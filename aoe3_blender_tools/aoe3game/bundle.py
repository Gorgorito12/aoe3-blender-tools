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

from . import animxml, collision, ddt, gr2_write

UNITS_PER_METER = gr2_write.STOCK_BASIS["units_per_meter"]
OBSTRUCTION_RATIO = 0.85
DECAL_RATIO = 1.25
FLAT_BUMP_TEXTURE = r"C:\aoe3bt\art\shadows_selections\flat_normal_black_spec.ddt"
# The damage system a building borrows when it has a damaged or a low-poly model, as the mod's
# own large buildings do: the stock outpost's damage skeleton and template. It also gives the
# model references their `shape`, without which the game never draws the low-poly model.
DAMAGE_SKELETON = (r"buildings\outpost\outpost_generic_damaged", r"buildings\outpost\outpost_generic.dmg")
COLLISION_SHAPE = DAMAGE_SKELETON[0].split("\\")[-1].replace("_damaged", "")   # what the model references name
RUBBLE = {"2x2": "BuildingRubble2x2", "3x3": "BuildingRubble3x3", "4x4": "BuildingRubble4x4",
          "5x5": "BuildingRubble5x5", "6x6": "BuildingRubble6x6"}


GROUND_MARGIN = 1.2


def game_size(footprint_m, units_per_meter=UNITS_PER_METER, profile=None, obstruction=None, rubble=None):
    """Obstruction radii, decal size, stage set and rubble for a footprint in metres. With a
    calibration profile (an object with footprint_class, obstruction_ratio, decal_ratio,
    stages and rubble, as core.profile.Profile), its measured ratios replace the defaults.

    obstruction: (rx, rz) in game units, the exact radii of a reference building (a style guide's
    "the same size as ..."); the class is then the profile's NxN class of that size when it has
    one."""
    w, d = (footprint_m[0] * units_per_meter, footprint_m[1] * units_per_meter)
    cls = profile.footprint_class(*footprint_m) if profile is not None else None
    if obstruction is not None and profile is not None:
        side = 2 * min(obstruction)                      # an oblong one belongs to its shorter side's class
        key = f"{side:g}x{side:g}"
        if key in getattr(profile, "classes", {}):
            cls = key
    ratio = (profile.obstruction_ratio(cls) if cls else None) or OBSTRUCTION_RATIO
    dratio = (profile.decal_ratio(cls) if cls else None) or DECAL_RATIO
    rx, rz = round(w / 2 * ratio, 2), round(d / 2 * ratio, 2)
    if obstruction is not None:
        rx, rz = float(obstruction[0]), float(obstruction[1])
    stages = (profile.stages(cls) if cls else None) or animxml.stage_class(2 * rx, 2 * rz)
    rubble = rubble or (profile.rubble(cls) if cls else None) or RUBBLE.get(stages, "BuildingRubble4x4")
    return {"radius": (rx, rz), "decal": (round(w * dratio, 2), round(d * dratio, 2)),
            "stages": stages, "rubble": rubble, "class": cls,
            "placement": "buildinglarge.xml" if max(rx, rz) >= 3 else "buildingsmall.xml"}


def write(out, *, name, prefix, positions, normals, uvs, triangles, texture_rgba, bones=(),
          footprint_m, icon_rgba=None, portrait_rgba=None, display_name=None, rollover="",
          template="House", v_flip=True, player_colour=None, chimney_bone=None, profile=None,
          texture_format="DXT3", variants=None, death_animation=None, relief=True, obstruction=None,
          ground_rgba=None, collision_boxes=None, rubble=None, texture_max=None, bump_max=None,
          kind="BUILDING", folder=None):
    """Writes the bundle into `out` and returns the bundle description.

    variants: {"lowpoly": {...}, "damaged": {...}}, each with positions, normals, uvs and
    triangles, and optionally its own texture_rgba (else it uses the main texture). The
    low-poly model is what the game draws at its low model detail setting; the damaged one
    replaces the intact model once the building has lost hit points.

    kind: "BUILDING" (construction stages, rubble, a placement file) or "PROP" (a map object,
    a treasure, a decoration: one component and an Idle anim, nothing of the building logic).
    folder: the art folder the files go under (by default "buildings", or "objects" for a prop;
    the stock game also keeps treasures in "nuggets").

    death_animation: also write `<name>_death.gr2`, the building sinking into the ground with
    the stock collapse dust, played when it is destroyed. By default only a building has one.

    obstruction: (rx, rz) game units, the exact obstruction of a reference building (see game_size).

    relief: also write a bump map for each texture (`<texture>_b.ddt`, DXT5 as the game's own),
    made from the texture's brightness; without it the models use the stock flat normal map.

    player_colour: None decides from the texture: an alpha below 255 anywhere means the
    player-colour shader (the low alpha shows the owner's colour). texture_format: "DXT3" (the
    game's usual building format, keeps the alpha), "DXT1" (no alpha) or "BGRA" (uncompressed).
    """
    import numpy as np
    rgba = np.asarray(texture_rgba)
    if player_colour is None:
        player_colour = rgba.shape[2] == 4 and int(rgba[:, :, 3].min()) < 250
    fmt = {"DXT3": ddt.DXT3, "DXT1": ddt.DXT1, "BGRA": ddt.BGRA}[texture_format.upper()]
    if player_colour and fmt == ddt.DXT1:
        raise ValueError("DXT1 has no alpha: the player-colour mask needs DXT3 or BGRA")
    low = name.lower()
    kind = str(kind).upper()
    if kind not in ("BUILDING", "PROP"):
        raise ValueError(f"kind: BUILDING or PROP, not {kind!r}")
    is_prop = kind == "PROP"
    folder = folder or ("objects" if is_prop else "buildings")
    if death_animation is None:
        death_animation = not is_prop
    rel_dir = f"{prefix}\\{folder}\\{low}"
    art_dir = os.path.join(out, "art", prefix, folder, low)
    os.makedirs(art_dir, exist_ok=True)
    size = game_size(footprint_m, profile=profile, obstruction=obstruction, rubble=rubble)
    def model_file(base, mesh, textures):
        texture, bump = textures
        model = gr2_write.static_model(name, mesh["positions"], mesh["normals"], mesh["uvs"],
                                       mesh["triangles"], texture=texture, bump=bump,
                                       bones=bones, v_flip=v_flip,
                                       player_colour=player_colour, source=f"{base}.blend")
        with open(os.path.join(art_dir, base + ".gr2"), "wb") as f:
            f.write(model)

    def texture_file(base, pixels):
        """Writes the texture and, with `relief`, its bump map; returns both stored names.
        `texture_max`, `bump_max`: the largest side of each, reached by halving the painting."""
        pixels = np.asarray(pixels)
        with open(os.path.join(art_dir, base + ".ddt"), "wb") as f:
            f.write(ddt.write(ddt.fitted(pixels, texture_max) if texture_max else pixels, fmt, alpha=1, usage=0, mips=True))
        bump = FLAT_BUMP_TEXTURE
        if relief:
            with open(os.path.join(art_dir, base + "_b.ddt"), "wb") as f:
                f.write(ddt.write_normal_map(ddt.normal_from_texture(ddt.fitted(pixels, bump_max) if bump_max else pixels)))
            bump = f"C:\\aoe3bt\\art\\{rel_dir}\\{base}_b.ddt"
        return f"C:\\aoe3bt\\art\\{rel_dir}\\{base}.ddt", bump

    main_textures = texture_file(low, rgba)
    model_file(low, {"positions": positions, "normals": normals, "uvs": uvs,
                     "triangles": triangles}, main_textures)
    refs = {}
    for variant, suffix in (("lowpoly", "_lp"), ("damaged", "_damaged")):
        v = (variants or {}).get(variant)
        if not v:
            continue
        own = v.get("texture_rgba")
        textures = texture_file(low + suffix, own) if own is not None else main_textures
        model_file(low + suffix, v, textures)
        refs[variant] = f"{rel_dir}\\{low}{suffix}"
    if death_animation:
        height = max(p[2] for p in positions) if len(positions) else 1.0
        with open(os.path.join(art_dir, low + "_death.gr2"), "wb") as f:
            f.write(gr2_write.sink_animation(name, bones, height * 1.05,
                                             source=f"{low}_death.blend"))
        refs["death"] = f"{rel_dir}\\{low}_death"
    unit = {"AnimFile": f"{rel_dir}\\{low}.xml",
            "ObstructionRadiusX": "%.4f" % size["radius"][0],
            "ObstructionRadiusZ": "%.4f" % size["radius"][1]}
    if not is_prop:                   # a prop leaves no rubble and is not placed by a builder
        unit["DeadReplacement"] = size["rubble"]
        unit["PlacementFile"] = size["placement"]
    if icon_rgba is not None:
        with open(os.path.join(art_dir, low + "_icon.ddt"), "wb") as f:
            f.write(ddt.write(icon_rgba, ddt.DXT1, alpha=0, usage=0, mips=False))
        unit["Icon"] = f"{rel_dir}\\{low}_icon"
    if portrait_rgba is not None:
        with open(os.path.join(art_dir, low + "_portrait.ddt"), "wb") as f:
            f.write(ddt.write(portrait_rgba, ddt.DXT1, alpha=0, usage=0, mips=True))
        unit["PortraitIcon"] = f"{rel_dir}\\{low}_portrait"
    bone_names = [b for b, _ in bones]
    ground = {}
    if ground_rgba is not None:                          # its own ground, wider than the game's: it thins out
        with open(os.path.join(art_dir, low + "_ground.ddt"), "wb") as f:
            f.write(ddt.write(ground_rgba, ddt.DXT3, alpha=8, usage=0, mips=True))
        ground["ground"] = f"{rel_dir}\\{low}_ground"
        size["decal"] = tuple(round(v * GROUND_MARGIN, 2) for v in size["decal"])
    shape_file = None
    if collision_boxes:                                  # its own boxes, beside the game's physics data
        phys_dir = os.path.join(out, "data", "physics")
        os.makedirs(phys_dir, exist_ok=True)
        shape_file = os.path.join(phys_dir, low + ".shp")
        with open(shape_file, "w", encoding="utf-8", newline="") as f:
            f.write(collision.shape_xml(collision_boxes, UNITS_PER_METER))
        ground["shape"] = low
    art = f"{rel_dir}\\{low}"
    if is_prop:
        anim = animxml.prop(name, art, decal=size["decal"], **ground, bones=bone_names,
                            lowpoly=refs.get("lowpoly"))
    else:
        anim = animxml.building(name, art, decal=size["decal"], **ground,
                                stages=size["stages"],
                                bones=[b for b in bone_names if b != chimney_bone],
                                chimney_bone=chimney_bone if chimney_bone in bone_names else None,
                                lowpoly=refs.get("lowpoly"), damaged=refs.get("damaged"),
                                death_anim=refs.get("death"),
                                simskeleton=DAMAGE_SKELETON if ("damaged" in refs or "lowpoly" in refs) else None)
    with open(os.path.join(art_dir, low + ".xml"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(anim)
    display = display_name or name
    desc = {"name": name, "kind": kind, "template": template, "unit": unit, "size": size,
            "texture": {"format": texture_format.upper(), "player_colour": bool(player_colour)},
            "strings": {"DisplayNameID": display, "EditorNameID": display,
                        "RolloverTextID": rollover or display,
                        "ShortRolloverTextID": rollover or display},
            "files": sorted([os.path.relpath(os.path.join(art_dir, f), out) for f in os.listdir(art_dir)]
                            + ([os.path.relpath(shape_file, out)] if shape_file else []))}
    with open(os.path.join(out, "bundle.json"), "w", encoding="utf-8") as f:
        json.dump(desc, f, indent=1)
    write_readme(out, desc, rel_dir=rel_dir, low=low, has=refs, is_prop=is_prop)
    return desc


def write_set(out, *, name, prefix, models, texture_rgba, footprint_m, icon_rgba=None, portrait_rgba=None,
              display_name=None, rollover="", template="PropsColony", v_flip=True, player_colour=None,
              texture_format="DXT3", relief=True, folder="objects", bones=(), decal=False):
    """Writes a prop set into `out`: one unit whose models are its variations, all on **one**
    texture (the generator paints them into one atlas; core/group.py packs meshes made elsewhere
    into one), and returns its description. A grouping or a map script picks a model by its
    `variation`.

    models: [{"positions", "normals", "uvs", "triangles"}], in order; each is written as
    <name>_<n>.gr2. footprint_m: the largest model's (width, depth), for the obstruction.
    template: the proto entry it copies, a stock prop set by default. decal: a selection square
    sized to the largest model (the stock colony set has none)."""
    import numpy as np
    if not models:
        raise ValueError("a prop set needs at least one model")
    rgba = np.asarray(texture_rgba)
    if player_colour is None:
        player_colour = rgba.shape[2] == 4 and int(rgba[:, :, 3].min()) < 250
    fmt = {"DXT3": ddt.DXT3, "DXT1": ddt.DXT1, "BGRA": ddt.BGRA}[texture_format.upper()]
    if player_colour and fmt == ddt.DXT1:
        raise ValueError("DXT1 has no alpha: the player-colour mask needs DXT3 or BGRA")
    low = name.lower()
    rel_dir = f"{prefix}\\{folder}\\{low}"
    art_dir = os.path.join(out, "art", prefix, folder, low)
    os.makedirs(art_dir, exist_ok=True)
    size = game_size(footprint_m)
    with open(os.path.join(art_dir, low + ".ddt"), "wb") as f:
        f.write(ddt.write(rgba, fmt, alpha=1, usage=0, mips=True))
    bump = FLAT_BUMP_TEXTURE
    if relief:
        with open(os.path.join(art_dir, low + "_b.ddt"), "wb") as f:
            f.write(ddt.write_normal_map(ddt.normal_from_texture(rgba)))
        bump = f"C:\\aoe3bt\\art\\{rel_dir}\\{low}_b.ddt"
    texture = f"C:\\aoe3bt\\art\\{rel_dir}\\{low}.ddt"
    refs = []
    for i, m in enumerate(models):
        base = f"{low}_{i}"
        data = gr2_write.static_model(name, m["positions"], m["normals"], m["uvs"], m["triangles"],
                                      texture=texture, bump=bump, bones=bones, v_flip=v_flip,
                                      player_colour=player_colour, source=f"{base}.blend")
        with open(os.path.join(art_dir, base + ".gr2"), "wb") as f:
            f.write(data)
        refs.append(f"{rel_dir}\\{base}")
    unit = {"AnimFile": f"{rel_dir}\\{low}.xml",
            "ObstructionRadiusX": "%.4f" % size["radius"][0],
            "ObstructionRadiusZ": "%.4f" % size["radius"][1]}
    if icon_rgba is not None:
        with open(os.path.join(art_dir, low + "_icon.ddt"), "wb") as f:
            f.write(ddt.write(icon_rgba, ddt.DXT1, alpha=0, usage=0, mips=False))
        unit["Icon"] = f"{rel_dir}\\{low}_icon"
    if portrait_rgba is not None:
        with open(os.path.join(art_dir, low + "_portrait.ddt"), "wb") as f:
            f.write(ddt.write(portrait_rgba, ddt.DXT1, alpha=0, usage=0, mips=True))
        unit["PortraitIcon"] = f"{rel_dir}\\{low}_portrait"
    with open(os.path.join(art_dir, low + ".xml"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(animxml.prop_set(name, refs, bones=[b for b, _ in bones],
                                 decal=size["decal"] if decal else None, selection=bool(decal)))
    display = display_name or name
    desc = {"name": name, "kind": "PROP", "set": len(models), "template": template, "unit": unit, "size": size,
            "texture": {"format": texture_format.upper(), "player_colour": bool(player_colour)},
            "strings": {"DisplayNameID": display, "EditorNameID": display,
                        "RolloverTextID": rollover or display, "ShortRolloverTextID": rollover or display},
            "files": sorted(os.path.relpath(os.path.join(art_dir, f), out) for f in os.listdir(art_dir))}
    with open(os.path.join(out, "bundle.json"), "w", encoding="utf-8") as f:
        json.dump(desc, f, indent=1)
    write_readme(out, desc, rel_dir=rel_dir, low=low, has={}, is_prop=True, models=len(models))
    return desc


README_TEXT = """{name}: files for the game
{rule}

art\\{rel_dir}\\
  {low}.gr2            the model (Granny 2, stock building basis)
  {low}.ddt            its texture{pc}
  {low}_b.ddt          its bump map (if written)
{extra}  {low}.xml            {anim_line}

The unit (data\\protoy.xml): copy the entry of {copy_what} like it ("{template}" was used
here), give it a new name and a free number (id = DBID), and set the fields in
proto_fields.xml. Strings (data\\stringtabley.xml): DisplayNameID, EditorNameID,
RolloverTextID and ShortRolloverTextID need new _locID numbers.

Still to do in the mod's own data, which this bundle does not touch:
{todo_first}- a hotkey context <name>Accel in the key map, if the mod's buildings have them;
- a compiled .xmb next to an edited XML hides the edit: recompile it, or delete it.

tools/game_deploy.py does all of this in a test copy of the game (--builder Settler).
"""


def write_readme(out, desc, *, rel_dir, low, has, is_prop=False, models=0):
    """README.txt and proto_fields.xml for whoever adds the building or prop to a mod by hand.
    models: the number of models of a prop set (0: one model)."""
    extra = ""
    if models:
        extra += (f"  {low}_0.gr2 .. {low}_{models - 1}.gr2  the set's {models} models, its variations, "
                  "on one texture\n")
    if has.get("lowpoly"):
        extra += f"  {low}_lp.gr2 / .ddt  the low-poly model for the low model detail setting\n"
    if has.get("damaged"):
        extra += f"  {low}_damaged.gr2 / .ddt  the damaged model\n"
    if has.get("death"):
        extra += f"  {low}_death.gr2      the death animation (sinks into the ground)\n"
    if "Icon" in desc["unit"]:
        extra += f"  {low}_icon.ddt, {low}_portrait.ddt  icon 64 x 64, portrait 128 x 128\n"
    pc = " (alpha below 255: the player colour)" if desc["texture"]["player_colour"] else ""
    if models:
        anim_line = "the anim file: a Variation of the models and an Idle anim"
        copy_what = "a prop set (one unit, many models)"
        todo_first = ("- put it on the map: a grouping, a map script or the scenario editor places it, and\n"
                      "  a grouping's variation attribute picks one of its models;\n")
    elif is_prop:
        anim_line = "the anim file: the model and its Idle anim"
        copy_what = "a map object or a treasure"
        todo_first = ("- put it on the map: a map script or the scenario editor places a prop; nobody\n"
                      "  builds it;\n")
    else:
        anim_line = ("the anim file: construction stages ({}), ground decal,\n"
                     "                       Idle{}").format(
            desc["size"]["stages"], ", Death" if has.get("death") else "")
        copy_what = "a building"
        todo_first = ("- let someone build it: a <Train> line for it in the builder's unit (a villager), and a\n"
                      "  tech or card that enables it for the civilizations that get it (a new unit is enabled\n"
                      "  for nobody);\n")
    text = README_TEXT.format(
        name=desc["name"], rule="=" * (len(desc["name"]) + 21), rel_dir=rel_dir, low=low, pc=pc,
        extra=extra, anim_line=anim_line, copy_what=copy_what, todo_first=todo_first,
        template=desc["template"])
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
    lines = ["<!-- Fields for the building's <Unit> entry in data\\protoy.xml -->"]
    for k, v in desc["unit"].items():
        lines.append(f"<{k}>{v}</{k}>")
    for k, v in desc["strings"].items():
        lines.append(f"<!-- {k}: a new _locID whose text is \"{v}\" -->")
    with open(os.path.join(out, "proto_fields.xml"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
