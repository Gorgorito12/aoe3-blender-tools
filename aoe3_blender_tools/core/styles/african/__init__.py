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
from . import layouts, parts, sizes, skin

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
    SKIN = skin.colours(C)
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

    def stains(region, w, h, n, k=0.12, size=1.0):
        skin.stains(pr, region, w, h, n, k, size)

    def line(region, u0, v0, u1, v1, color, width=None):
        (x0, y0), (x1, y1) = pr.P(region, u0, v0), pr.P(region, u1, v1)
        pr.cv.line(x0, y0, x1, y1, color, width or lw)

    def straw(region, base, w, h, density=160.0):
        """Loose straw: many short thin strands down the slope, a little slanted, light and dark."""
        thin = max(1, lw // 2)
        for _ in range(int(w * h * density)):
            u, v = float(rng.uniform(0, w)), float(rng.uniform(0, h))
            ln = float(rng.uniform(0.1, 0.32))
            du = ln * float(rng.uniform(-0.4, 0.4))
            f = float(rng.choice([0.6, 0.72, 0.85, 1.18, 1.3]))
            line(region, u, min(h, v + ln), u + du, v, _shade(base, f), thin)

    def shade_band(region, w, v0, v1, f, steps=4):
        """A soft darkening from v0 (strongest, factor f) towards v1: under an eave, at the foot."""
        for j in range(steps):
            a = v0 + (v1 - v0) * j / steps
            b = v0 + (v1 - v0) * (j + 1) / steps
            pr.tone(region, 0, max(0.0, min(a, b)), w, max(a, b), 1 - (1 - f) * (1 - j / steps) / 2)

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
            skin.coat(pr, region, "wall_mud", SKIN)
            shade_band(region, w, h, h - 0.7, 0.72)                            # under the thatch's eave
            shade_band(region, w, 0, 0.45, 0.7)                                 # the splashed foot
            if spec.get("bands"):
                band(region, 0.28, 0.42, w)
                band(region, h - 0.22, h - 0.1, w)
            if spec["door"] is not None:
                door(region, spec["door"], spec["door_w"], spec["door_h"])
        else:
            earth = ADOBE if spec.get("sahel", True) else MUD
            skin.coat(pr, region, "wall_adobe" if spec.get("sahel", True) else "wall_mud", SKIN)
            if not spec.get("sahel", True):
                shade_band(region, w, h, h - 0.6, 0.75)                         # under the thatch's eave
            if spec.get("sahel", True):
                for _ in range(int(w * 1.2)):                                   # rain runs from the top
                    u, rw_ = float(rng.uniform(0, w)), float(rng.uniform(0.06, 0.22))
                    v0 = h * float(rng.uniform(0.2, 0.7))
                    for j in range(3):                                          # fading downwards
                        pr.tone(region, u, v0 + (h - v0) * j / 3, min(w, u + rw_), h, 0.95)
                band(region, h - 0.32, h - 0.18, w)
            else:
                band(region, 0.28, 0.42, w)
            shade_band(region, w, 0, 0.9, 0.62)                                 # the splashed foot
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
        pr.base("thatch", THATCH, role="roof")
        straw("thatch", THATCH, rt.world_w, rt.world_h)
        shade_band("thatch", rt.world_w, 0, 0.25, 0.7)                               # the eave's cut ends
        stains("thatch", rt.world_w, rt.world_h, int(rt.world_w * rt.world_h * 0.3) + 1, 0.16)
    if "dome" in at:
        rd = at["dome"]
        skin.coat(pr, "dome", "dome", SKIN)
    if "roof_flat" in at:
        skin.coat(pr, "roof_flat", "roof_flat", SKIN)
    if "parapet" in at:
        skin.coat(pr, "parapet", "parapet", SKIN)
    if "trim" in at:
        skin.coat(pr, "trim", "trim", SKIN)
    pr.base("wood", WOOD, role="timber")
    rw = at["wood"]
    stains("wood", rw.world_w, rw.world_h, 6, 0.2)
    u = 0.0
    while u < rw.world_w:                                                        # planks and their gaps
        pw = float(rng.uniform(0.12, 0.22))
        pr.tone("wood", u, 0, min(rw.world_w, u + pw), rw.world_h, float(rng.uniform(0.82, 1.12)))
        pr.vline("wood", u, 0, rw.world_h, _shade(WOOD, 0.45), lw)
        u += pw
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
        MORTAR = (142, 122, 90)
        pr.base("stone", MORTAR, role="stone")
        v = 0.0
        while v < rs.world_h:                                                    # rubble: uneven stones
            hh = float(rng.uniform(0.24, 0.5))
            u = -float(rng.uniform(0, 0.3))
            while u < rs.world_w:
                ww = float(rng.uniform(0.3, 0.8))
                t = int(rng.integers(-28, 29))
                gap = float(rng.uniform(0.015, 0.04))
                dv = float(rng.uniform(-0.04, 0.04))
                c = tuple(max(0, min(255, k + t)) for k in STONE)
                pr.paint_on("stone", max(0.0, u + gap), max(0.0, v + gap + dv), min(rs.world_w, u + ww - gap),
                            min(rs.world_h, v + hh - gap + dv), c, _shade(c, 0.62))
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
    if "slab" in at:
        rs2 = at["slab"]
        pr.base("slab", WOOD, role="timber")
        vv = 0.0
        while vv < rs2.world_h:
            pr.hline("slab", vv, 0, rs2.world_w, _shade(WOOD, 0.72))
            vv += 0.2
    if "rail" in at:
        rr2 = at["rail"]
        pr.fill("rail", _shade(WOOD, 0.45))
        pr.rect("rail", 0, 0, rr2.world_w, 0.1, WOOD, _shade(WOOD, 0.7))
        pr.rect("rail", 0, rr2.world_h - 0.12, rr2.world_w, rr2.world_h, WOOD, _shade(WOOD, 0.7))
        band("rail", rr2.world_h - 0.24, rr2.world_h - 0.14, rr2.world_w)
        u = 0.06
        while u < rr2.world_w - 0.05:
            pr.rect("rail", u, 0.1, u + 0.06, rr2.world_h - 0.24, _shade(WOOD, 1.1))
            u += 0.15
    if "crop" in at:
        rc2 = at["crop"]
        pr.fill("crop", (112, 128, 52))
        pr.rect("crop", 0, rc2.world_h * 0.7, rc2.world_w, rc2.world_h, (176, 150, 70))      # the heads
        for k in range(6):
            pr.vline("crop", rc2.world_w * (k + 0.5) / 6, 0, rc2.world_h * 0.7, (88, 104, 40))
