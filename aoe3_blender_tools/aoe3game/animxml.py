# SPDX-License-Identifier: GPL-3.0-or-later
"""Anim files (the art XML a proto names in <AnimFile>) for a building.

Layout taken from the game's own building files: construction stages reuse the stock stage
models of the footprint class, the finished building is its own submodel with a ground decal,
and the root component picks the submodel by build progress (BuildingCompletion, inside a
Variation logic). Paths are relative to the art folder, with backslashes; model and texture
paths have no extension; particle files keep theirs. Never writes a compiled .xmb.
"""
from xml.sax.saxutils import escape

STAGE_DECAL = r"buildings\constructions\2x2_construction_decal"
GROUND_DECAL = r"buildings\market\market_ground_generic"
SELECTION = r"shadows_selections\selection_square_{0}x{0}"
FLAT_BUMP = r"shadows_selections\flat_normal_black_spec"
CHIMNEY_SMOKE = r"effects\smoke\white_smoke_a.particle"
# The dust a stock house throws when it collapses, attached at the model's origin.
COLLAPSE_SMOKE = (("base smoke", "smoke base", r"effects\smoke\collapsesmoke01.particle"),
                  ("collapse_smoke", "collapse_smoke", r"effects\smoke\collapse_smoke_a.particle"))
STAGE_CLASSES = ("2x2", "3x3", "4x4", "5x5", "6x6")


def art_path(path):
    """Backslashes, no leading art folder, no model or texture extension."""
    p = path.replace("/", "\\").lstrip("\\")
    if p.lower().startswith("art\\"):
        p = p[4:]
    for ext in (".gr2", ".ddt", ".tga", ".png"):
        if p.lower().endswith(ext):
            p = p[:-len(ext)]
    return p


def stage_class(width, depth):
    """The stock construction stage set closest to a footprint in game units (the side of the
    obstruction square: 2 x ObstructionRadius)."""
    side = max(width, depth)
    best = min(STAGE_CLASSES, key=lambda c: abs(int(c[0]) * 2 - side))
    return best


def _decal(tab, texture, width, height, selection=64):
    return (f"{tab}<decal>\n"
            f"{tab}\t<effecttype>bump</effecttype>\n"
            f"{tab}\t<texture>{escape(texture)}</texture>\n"
            f"{tab}\t<selectedtexture>{SELECTION.format(selection)}</selectedtexture>\n"
            f"{tab}\t<bumptexture>{FLAT_BUMP}</bumptexture>\n"
            f"{tab}\t<width>{width:.2f}</width>\n"
            f"{tab}\t<height>{height:.2f}</height>\n"
            f"{tab}</decal>\n")


def _asset(tab, model, shape=None):
    attr = f" shape=\"{escape(shape)}\"" if shape else ""
    return (f"{tab}<assetreference type=\"GrannyModel\"{attr}>\n"
            f"{tab}\t<file>{escape(art_path(model))}</file>\n"
            f"{tab}</assetreference>\n")


def _model_block(tab, model, lowpoly=None, damaged=None, shape=None):
    """The finished model as the stock buildings write it: a Destruction logic (p1 the damaged
    model, p99 the intact one) when there is a damaged model, inside a LowPoly logic (normal /
    lowpoly) when there is a low-poly model; a plain asset reference otherwise. The low-poly
    reference carries the same `shape` as the others, as the stock houses write it: without it
    the game never draws the low-poly model (seen in game, 2026-11-03)."""
    if damaged:
        normal = (f"{tab}<logic type=\"Destruction\">\n"
                  f"{tab}\t<p1>\n{_asset(tab + chr(9) * 2, damaged, shape)}{tab}\t</p1>\n"
                  f"{tab}\t<p99>\n{_asset(tab + chr(9) * 2, model, shape)}{tab}\t</p99>\n"
                  f"{tab}</logic>\n")
    else:
        normal = _asset(tab, model, shape)
    if not lowpoly:
        return normal
    inner = "".join(tab + "\t\t" + line[len(tab):] + "\n" for line in normal.splitlines())
    return (f"{tab}<logic type=\"LowPoly\">\n"
            f"{tab}\t<normal>\n{inner}{tab}\t</normal>\n"
            f"{tab}\t<lowpoly>\n{_asset(tab + chr(9) * 2, lowpoly, shape)}{tab}\t</lowpoly>\n"
            f"{tab}</logic>\n")


def building(name, model, *, decal, stages="2x2", stage_decal=None, ground=GROUND_DECAL,
             bones=("bone_flag_civ",), chimney_bone=None, lowpoly=None, damaged=None,
             death_anim=None, simskeleton=None, shape=None):
    """The text of a building's anim file.

    name: the building's name (submodel and component names).
    model: the finished model, as an art path (e.g. "Mod\\buildings\\x\\x").
    decal: (width, height) of the ground decal in game units.
    stages: the stock construction stage set ("2x2" ... "6x6").
    bones: bones the model carries that the game uses (the civilization flag).
    chimney_bone: a bone of the model to put chimney smoke on, or None.
    lowpoly: a simpler model for the game's low model detail setting, or None.
    damaged: a damaged model, or None. The stock files put it under p1 and the intact model
        under p99 of a Destruction logic. Seen in game: it is not a state between full
        health and death (the stock houses also look intact until they are destroyed, with
        flames); it only belongs to the destruction.
    death_anim: a Granny animation the building plays when it is destroyed (with the stock
        collapse dust), or None (the building then just goes).
    simskeleton: (damaged model, damage template) of a stock building whose damage system
        this one borrows, as the mod's own buildings do (e.g. the stock outpost's), or None.
        The model references then carry that model's name as their `shape`.
    shape: the building's own collision shape (Data\\PHYSICS\\<shape>.shp), in its place.
    """
    model = art_path(model)
    sw, sh = stage_decal or decal
    sel = 128 if max(decal) > 10 else 64
    out = ['<?xml version="1.0" encoding="utf-8"?>\n', "<animfile>\n"]
    for b in list(bones) + ([chimney_bone] if chimney_bone else []):
        out.append(f"\t<definebone>{escape(b)}</definebone>\n")
    refs = []
    for k in (1, 2, 3):
        sub = f"sub_construction_stage_{k:02d}"
        comp = f"construction_stage_{k:02d}"
        refs.append(sub)
        out.append(f"\t<submodel>\n\t\t{sub}\n")
        out.append(f"\t\t<component>\n\t\t\t{comp}\n")
        out.append("\t\t\t<assetreference type=\"GrannyModel\">\n")
        out.append(f"\t\t\t\t<file>buildings\\constructions\\{stages}_stage{k}</file>\n")
        out.append("\t\t\t</assetreference>\n")
        out.append(_decal("\t\t\t", STAGE_DECAL, sw, sh, sel))
        out.append("\t\t</component>\n")
        out.append(f"\t\t<anim>\n\t\t\tIdle\n\t\t\t<component>{comp}</component>\n\t\t</anim>\n")
        out.append("\t</submodel>\n")
    main = f"{name}_main"
    out.append(f"\t<submodel>\n\t\t{escape(name)}\n")
    if chimney_bone:
        out.append("\t\t<attachment>\n\t\t\tchimney smoke\n\t\t\t<component>\n\t\t\t\tsmoke\n")
        out.append("\t\t\t\t<assetreference type=\"ParticleSystem\">\n")
        out.append(f"\t\t\t\t\t<file>{CHIMNEY_SMOKE}</file>\n")
        out.append("\t\t\t\t</assetreference>\n\t\t\t</component>\n")
        out.append("\t\t\t<anim>\n\t\t\t\tIdle\n\t\t\t\t<component>smoke</component>\n")
        out.append("\t\t\t</anim>\n\t\t</attachment>\n")
    if death_anim:
        for attachment, component, particle in COLLAPSE_SMOKE:
            out.append(f"\t\t<attachment>\n\t\t\t{attachment}\n\t\t\t<component>\n\t\t\t\t{component}\n")
            out.append("\t\t\t\t<assetreference type=\"ParticleSystem\">\n")
            out.append(f"\t\t\t\t\t<file>{particle}</file>\n")
            out.append("\t\t\t\t</assetreference>\n\t\t\t</component>\n")
            out.append(f"\t\t\t<anim>\n\t\t\t\tIdle\n\t\t\t\t<component>{component}</component>\n")
            out.append("\t\t\t</anim>\n\t\t</attachment>\n")
    out.append(f"\t\t<component>\n\t\t\t{escape(main)}\n")
    if simskeleton and not shape:
        shape = art_path(simskeleton[0]).split("\\")[-1]
        if shape.lower().endswith("_damaged"):
            shape = shape[:-len("_damaged")]
    out.append(_model_block("\t\t\t", model, lowpoly=lowpoly, damaged=damaged, shape=shape))
    out.append(_decal("\t\t\t", ground, decal[0], decal[1], sel))
    if chimney_bone:
        out.append(f"\t\t\t<attach a=\"chimney smoke\" frombone=\"{escape(chimney_bone)}\" "
                   f"tobone=\"{escape(chimney_bone)}\" syncanims=\"0\"/>\n")
    out.append("\t\t</component>\n")
    out.append(f"\t\t<anim>\n\t\t\tIdle\n\t\t\t<component>{escape(main)}</component>\n")
    if simskeleton:
        out.append(f"\t\t\t<simskeleton>\n\t\t\t\t<model>{escape(art_path(simskeleton[0]))}</model>\n"
                   f"\t\t\t\t<damagetemplate>{escape(simskeleton[1])}</damagetemplate>\n"
                   "\t\t\t</simskeleton>\n")
    out.append("\t\t</anim>\n")
    if death_anim:
        out.append("\t\t<anim>\n\t\t\tDeath\n\t\t\t<assetreference type=\"GrannyAnim\">\n")
        out.append(f"\t\t\t\t<file>{escape(art_path(death_anim))}</file>\n")
        out.append("\t\t\t</assetreference>\n")
        out.append(f"\t\t\t<component>{escape(main)}</component>\n")
        for attachment, _component, _particle in COLLAPSE_SMOKE:
            out.append(f"\t\t\t<attach a=\"{attachment}\" frombone=\"ATTACHPOINT\" "
                       "tobone=\"ATTACHPOINT\" syncanims=\"0\"/>\n")
        out.append("\t\t</anim>\n")
    out.append("\t</submodel>\n")
    out.append(f"\t<component>\n\t\t{escape(name)}\n")
    out.append("\t\t<logic type=\"Variation\">\n\t\t\t<none>\n")
    out.append("\t\t\t\t<logic type=\"BuildingCompletion\">\n")
    for pct, ref in zip((0, 33, 66, 100), refs + [name]):
        out.append(f"\t\t\t\t\t<p{pct}>\n\t\t\t\t\t\t<submodelref ref=\"{escape(ref)}\"/>\n"
                   f"\t\t\t\t\t</p{pct}>\n")
    out.append("\t\t\t\t</logic>\n\t\t\t</none>\n\t\t</logic>\n\t</component>\n")
    out.append("</animfile>\n")
    return "".join(out)
