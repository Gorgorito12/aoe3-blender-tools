# SPDX-License-Identifier: GPL-3.0-or-later
"""The African style, after the "Shared African Buildings" style guide: thirteen building types
(BuildingParams.building_type), each in two architectures (BuildingParams.architecture):
SUBSAHARAN (round mud huts with thatched cones, log fences) and SAHEL (adobe blocks with flat
roofs, parapets and beam ends, domed granaries). Each building is laid out on the plan its
guide reference gives (sizes.py) and built from the pieces in parts.py. Player colour: bands at
the foot and the top of the walls, cloths, banners."""
import math
from dataclasses import replace

from ...kit import Builder
from ...painter import PLAYER_GREY, _shade
from . import layouts, parts, sizes

NAME = "AFRICAN"
CHOICES = {"building_type": sizes.TYPES, "architecture": ("SUBSAHARAN", "SAHEL"), "wall_upgrade": ("WOOD", "STONE")}


def clamp(p):
    p = replace(p, colors=dict(p.colors))
    for key, vals in CHOICES.items():
        v = str(getattr(p, key)).upper()
        setattr(p, key, v if v in vals else vals[0])
    if p.building_type == "CUSTOMS":
        p.storeys = max(1, min(2, int(p.storeys)))
    else:
        p.storeys = 1
    p.width = p.depth = sizes.side_m(p.building_type)
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "LOW"
    p.texture_size = 1 << int(round(math.log2(max(256, min(4096, p.texture_size)))))
    p.cupola = p.flagpole = p.portico = p.wings = p.balcony = p.bell_gable = False
    return p


def reference(p):
    """(obstruction radius in game units, proto template) of the building the guide names."""
    return sizes.radius(p.building_type), sizes.template(p.building_type)


def opening_tops(spec, p):
    return spec.get("tops", [])


def build(p, params):
    medium = p.detail == "MEDIUM"
    layout = layouts.layout(p, sizes.side_m(p.building_type), medium)
    b = Builder(p.texture_size, medium)
    facades = parts.declare(b, layout, medium)
    b.pack()
    b._african_facades = facades
    top = parts.emit(b, layout, medium)
    flag = next((pc for pc in layout if pc.get("flag")), None)
    if flag is not None:
        b.attach["flag_attach"] = layouts.flag_point(flag, medium)
    else:
        b.attach["flag_attach"] = top
    notes = []
    if int(params.storeys) != p.storeys and p.building_type != "CUSTOMS":
        notes.append(f"Storeys {params.storeys} -> {p.storeys}: only the customs house has an upper floor.")
    return b.finish(p, facades, {"wall_h": max([pc.get("wall_h", pc.get("h", 0)) for pc in layout] + [0]),
                                 "storeys": p.storeys, "type": p.building_type, "architecture": p.architecture},
                    notes)


def random_params(rng, i, BuildingParams):
    return BuildingParams(
        name=f"African{i}", style=NAME, building_type=rng.choice(sizes.TYPES),
        architecture=rng.choice(CHOICES["architecture"]), wall_upgrade=rng.choice(CHOICES["wall_upgrade"]),
        storeys=rng.randint(1, 2), detail=rng.choice(["LOW", "MEDIUM"]), texture_size=256,
        player_colour=rng.random() < 0.4, materials=rng.random() < 0.3, seed=rng.randint(1, 9999))


# --------------------------------------------------------------------------------------------------
# Texture

def paint(pr, model):
    at = pr.at
    C = pr.C
    MUD, THATCH, ADOBE, WOOD = C["mud"], C["thatch"], C["adobe"], C["timber"]
    STONE, CLOTH, POT = C["stone"], C["cloth"], C["tile"]
    DARK = (38, 28, 22)
    BAND = PLAYER_GREY if pr.pc else (70, 64, 120)
    lw = pr.lw
    rng = pr.rng

    def band(region, v0, v1, w):
        pr.paint_on(region, 0, v0, w, v1, BAND)
        pr.mark(region, 0, v0, w, v1)

    def smears(region, base, w, h, n, k=0.06):
        """Hand-smoothed earth: short horizontal smears a little lighter or darker."""
        for _ in range(n):
            u, v = float(rng.uniform(0, w)), float(rng.uniform(0, h))
            ln, th = float(rng.uniform(0.2, 0.8)), float(rng.uniform(0.03, 0.08))
            f = 1 + float(rng.uniform(-k, k))
            pr.paint_on(region, u, v, min(w, u + ln), min(h, v + th), _shade(base, f))

    def door(region, u, w, h, arched=True):
        pr.rect(region, u - w / 2 - 0.08, 0, u + w / 2 + 0.08, h + 0.08, WOOD, _shade(WOOD, 0.7))
        pr.rect(region, u - w / 2, 0, u + w / 2, h - (w / 2 if arched else 0), DARK)
        if arched:
            cx, cy = pr.P(region, u, h - w / 2)
            pr.cv.ellipse(cx, cy, w / 2 * pr.px_per_m, w / 2 * pr.px_per_m, DARK, upper_half=True)

    for region, spec in model.facades.items():
        r = at[region]
        w, h = r.world_w, r.world_h
        if spec["kind"] == "round":
            pr.base(region, MUD, role="wall")
            smears(region, MUD, w, h, int(w * h * 3))
            pr.paint_on(region, 0, 0, w, 0.22, _shade(MUD, 0.72))                 # the splashed foot
            if spec.get("bands"):
                band(region, 0.28, 0.42, w)
                band(region, h - 0.22, h - 0.1, w)
            if spec["door"] is not None:
                door(region, spec["door"], spec["door_w"], spec["door_h"])
        else:
            pr.base(region, ADOBE, role="wall")
            smears(region, ADOBE, w, h, int(w * h * 4), 0.05)
            for _ in range(int(w * 1.5)):                                       # rain runs from the top
                u = float(rng.uniform(0, w))
                pr.paint_on(region, u, h * float(rng.uniform(0.3, 0.7)), u + 0.05, h, _shade(ADOBE, 0.9))
            pr.paint_on(region, 0, 0, w, 0.3, _shade(ADOBE, 0.8))
            band(region, h - 0.32, h - 0.18, w)
            for (u0, v0, u1, v1) in spec["openings"]:
                if v0 == 0.0:
                    pr.rect(region, u0 - 0.1, 0, u1 + 0.1, v1 + 0.14, WOOD, _shade(WOOD, 0.7))
                    pr.rect(region, u0, 0, u1, v1, _shade(WOOD, 0.85), _shade(WOOD, 0.6), lw)
                    uu = u0 + 0.12
                    while uu < u1 - 0.05:
                        pr.vline(region, uu, 0, v1, _shade(WOOD, 0.65))
                        uu += 0.14
                else:
                    pr.rect(region, u0, v0, u1, v1, DARK)
                    pr.rect(region, u0 - 0.08, v1, u1 + 0.08, v1 + 0.1, WOOD, _shade(WOOD, 0.7))

    if "thatch" in at:
        rt = at["thatch"]
        pr.base("thatch", _shade(THATCH, 0.8), role="roof")
        v, row = 0.0, 0
        while v < rt.world_h:                                                    # courses of bundles
            u = -(row % 2) * 0.09
            while u < rt.world_w:
                t = int(rng.integers(-14, 15))
                c = tuple(max(0, min(255, k + t)) for k in THATCH)
                pr.paint_on("thatch", max(0.0, u), v, min(rt.world_w, u + 0.17), min(rt.world_h, v + 0.42), c)
                pr.vline("thatch", u + 0.06, v + 0.05, min(rt.world_h, v + 0.4), _shade(c, 0.78))
                pr.vline("thatch", u + 0.12, v + 0.1, min(rt.world_h, v + 0.38), _shade(c, 1.1))
                u += 0.18
            pr.hline("thatch", v + 0.02, 0, rt.world_w, _shade(THATCH, 0.62), lw)
            v += 0.38
            row += 1
        pr.paint_on("thatch", 0, 0, rt.world_w, 0.12, _shade(THATCH, 0.6))           # the ragged eave
    if "dome" in at:
        rd = at["dome"]
        pr.base("dome", _shade(MUD, 1.08), role="wall")
        smears("dome", _shade(MUD, 1.08), rd.world_w, rd.world_h, int(rd.world_w * rd.world_h * 3))
        vv = 0.5
        while vv < rd.world_h:
            pr.hline("dome", vv, 0, rd.world_w, _shade(MUD, 0.85), lw)
            vv += 0.6
    if "roof_flat" in at:
        rf = at["roof_flat"]
        pr.base("roof_flat", _shade(ADOBE, 1.05), role="wall")
        smears("roof_flat", _shade(ADOBE, 1.05), rf.world_w, rf.world_h, int(rf.world_w * rf.world_h * 2))
        for _ in range(3):
            u, v = float(rng.uniform(0.5, rf.world_w - 0.5)), float(rng.uniform(0.5, rf.world_h - 0.5))
            pr.paint_on("roof_flat", u, v, u + 0.6, v + 0.4, _shade(ADOBE, 0.85))
    if "parapet" in at:
        rp = at["parapet"]
        pr.base("parapet", ADOBE, role="wall")
        smears("parapet", ADOBE, rp.world_w, rp.world_h, int(rp.world_w * rp.world_h * 4), 0.05)
    pr.base("wood", WOOD, role="timber")
    rw = at["wood"]
    for k in range(18):
        pr.vline("wood", rw.world_w * (k + 0.5) / 18, 0, rw.world_h, _shade(WOOD, 0.8 + 0.1 * (k % 3)))
    if "pot" in at:
        rpo = at["pot"]
        pr.fill("pot", POT)
        pr.hline("pot", rpo.world_h * 0.7, 0, rpo.world_w, _shade(POT, 0.7), 2 * lw)
    if "plinth" in at:
        rpl = at["plinth"]
        pr.base("plinth", _shade(MUD, 0.7), role="plinth")
        smears("plinth", _shade(MUD, 0.7), rpl.world_w, rpl.world_h, int(rpl.world_w * 4), 0.1)
    if "cloth" in at:
        rc = at["cloth"]
        u, k = 0.0, 0
        while u < rc.world_w:
            col = BAND if k % 2 == 0 else CLOTH
            pr.rect("cloth", u, 0, min(rc.world_w, u + 0.35), rc.world_h, col)
            if k % 2 == 0:
                pr.mark("cloth", u, 0, min(rc.world_w, u + 0.35), rc.world_h)
            u += 0.35
            k += 1
    if "stone" in at:
        rs = at["stone"]
        pr.base("stone", _shade(STONE, 0.7), role="stone")
        v = 0.0
        while v < rs.world_h:
            hh = float(rng.uniform(0.2, 0.35))
            u = -float(rng.uniform(0, 0.3))
            while u < rs.world_w:
                ww = float(rng.uniform(0.25, 0.6))
                t = int(rng.integers(-14, 15))
                pr.paint_on("stone", max(0.0, u + 0.02), v + 0.02, min(rs.world_w, u + ww - 0.02),
                            min(rs.world_h, v + hh - 0.02), tuple(max(0, min(255, c + t)) for c in STONE))
                u += ww
            v += hh
    if "field" in at:
        rfi = at["field"]
        SOIL = (92, 64, 42)
        pr.base("field", SOIL, role="plinth")
        for _ in range(int(rfi.world_w * rfi.world_h * 6)):
            u, v = float(rng.uniform(0, rfi.world_w)), float(rng.uniform(0, rfi.world_h))
            g = (96 + int(rng.integers(-20, 20)), 120 + int(rng.integers(-20, 30)), 40)
            pr.rect("field", u, v, min(rfi.world_w, u + 0.06), min(rfi.world_h, v + 0.16), g)
    if "reveal" in at:
        pr.fill("reveal", _shade(ADOBE, 0.75))
