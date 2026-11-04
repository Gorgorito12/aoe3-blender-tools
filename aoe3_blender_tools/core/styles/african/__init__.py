# SPDX-License-Identifier: GPL-3.0-or-later
"""The African style, after the "Shared African Buildings" style guide: thirteen building types
(BuildingParams.building_type), each in two architectures (BuildingParams.architecture):
SUBSAHARAN (round mud huts with thatched cones, log fences) and SAHEL (adobe blocks with flat
roofs, parapets and beam ends, domed granaries). Each building is laid out on the plan its
guide reference gives (sizes.py) and built from the pieces in parts.py. Player colour: bands at
the foot and the top of the walls, cloths, banners."""
import math
from dataclasses import replace

import numpy as np

from ...kit import Builder
from ...painter import PLAYER_GREY, _shade
from . import facade, layouts, parts, sizes, skin

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


def ground_decal(p, size=512):
    """The ground a building lies on, RGBA for the game's decal, or None to use the game's own:
    sand worn by feet, thinning out irregularly into the grass."""
    if (p.building_type, p.architecture) != ("PALACE", "SAHEL"):
        return None
    rng = np.random.default_rng(p.seed + 11)

    def noise(cells):
        """Smooth noise from -1 to 1, about `cells` blobs across."""
        g = rng.uniform(-1.0, 1.0, (cells + 2, cells + 2))
        t = np.linspace(0.0, cells, size)
        i = t.astype(int)
        f = (t - i)[None, :]
        c = (t - i)[:, None]
        f, c = f * f * (3 - 2 * f), c * c * (3 - 2 * c)
        top = g[np.ix_(i, i)] * (1 - f) + g[np.ix_(i, i + 1)] * f
        low = g[np.ix_(i + 1, i)] * (1 - f) + g[np.ix_(i + 1, i + 1)] * f
        return top * (1 - c) + low * c

    y, x = np.mgrid[-1.0:1.0:size * 1j, -1.0:1.0:size * 1j]
    edge = np.maximum(np.abs(x), np.abs(y)) * 0.65 + np.hypot(x, y) * 0.35   # a rounded square
    rim = 0.8 + 0.14 * noise(4) + 0.1 * noise(11) + 0.06 * noise(36)
    alpha = np.clip((rim - edge) / 0.05, 0.0, 1.0)
    tone = 1.0 + 0.14 * noise(7) + 0.1 * noise(24) + 0.08 * noise(80)
    grit = rng.uniform(-1.0, 1.0, (size, size)) * 0.03
    out = np.zeros((size, size, 4), np.uint8)
    for ch, value in enumerate((142, 106, 68)):
        out[..., ch] = np.clip(value * (tone + grit), 0, 255)
    out[..., 3] = np.clip(alpha * 215, 0, 255)
    return out


def reference(p):
    """(obstruction radius in game units, proto template) of the building the guide names."""
    return sizes.radius(p.building_type), sizes.template(p.building_type)


def obstruction(p):
    return sizes.obstruction(p.building_type, p.architecture)


def rubble(p):
    return sizes.RUBBLES.get((p.building_type, p.architecture))


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
    k = sizes.scale(p.building_type, p.architecture)      # to the game's size, all of it together
    for f in b.faces:
        f.pts = [(x * k, y * k, z * k) for x, y, z in f.pts]
    b.attach = {name: tuple(c * k for c in at) for name, at in b.attach.items()}
    if (p.building_type, p.architecture) == ("PALACE", "SAHEL"):   # fitted boxes; the others share a stock shape
        b.boxes = [tuple(c * k for c in box) for box in parts.collision(layout)]
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
            earth = ADOBE if spec.get("sahel") else MUD
            skin.coat(pr, region, "wall_adobe" if spec.get("sahel") else "wall_mud", SKIN)
            shade_band(region, w, h, h - 0.7, 0.72)                            # under the thatch's eave
            shade_band(region, w, 0, 0.45, 0.7)                                 # the splashed foot
            span = [(spec["door"] - 0.8, spec["door"] + 0.8)] if spec["door"] is not None else []
            facade.draw(pr, region, facade.plan(pr.p.seed, region, w, h, "round", pr.p.building_type, span), earth, WOOD, BAND)
            if h > 2.4 and not spec.get("sahel"):
                facade.frieze(pr, region, w, h * 0.72, earth, pr.p.seed)
            if spec.get("bands"):
                band(region, 0.28, 0.42, w)
                band(region, h - 0.22, h - 0.1, w)
            if spec["door"] is not None:
                door(region, spec["door"], spec["door_w"], spec["door_h"])
        else:
            earth = ADOBE if spec.get("sahel", True) else MUD
            kept = pr.p.building_type == "PALACE" and spec.get("sahel", True)
            skin.coat(pr, region, "wall_kept" if kept else ("wall_adobe" if spec.get("sahel", True) else "wall_mud"), SKIN)
            if not spec.get("sahel", True):
                shade_band(region, w, h, h - 0.6, 0.75)                         # under the thatch's eave
            if spec.get("art") == "frieze":
                facade.pale_frieze(pr, region, (w - 4.1) / 2, (w + 4.1) / 2, h - 0.62, earth)
            if spec.get("sahel", True):
                for _ in range(0 if kept else int(w * 1.2)):                    # rain runs from the top
                    u, rw_ = float(rng.uniform(0, w)), float(rng.uniform(0.06, 0.22))
                    v0 = h * float(rng.uniform(0.2, 0.7))
                    for j in range(3):                                          # fading downwards
                        pr.tone(region, u, v0 + (h - v0) * j / 3, min(w, u + rw_), h, 0.95)
                if spec.get("band", True):
                    band(region, h - (0.46 if kept else 0.36), h - 0.16, w)
            else:
                band(region, 0.28, 0.42, w)
            if kept:
                facade.weather(pr, region, w, h, h - 0.46, earth, spec.get("foot"))
                if spec.get("foot"):                          # a course of pale stone against the rain
                    facade.foot_stones(pr, region, w, earth)
            else:
                shade_band(region, w, 0, 0.9, 0.62)                             # the splashed foot
            spans = [(u0, u1) for (u0, v0, u1, v1) in spec["openings"]]
            kind = "kept" if kept else ("adobe" if spec.get("sahel", True) else "mud")
            if not kept:                                      # a palace's walls show what the design put there
                facade.draw(pr, region, facade.plan(pr.p.seed, region, w, h, kind, pr.p.building_type, spans), earth, WOOD, BAND)
            if h > 3.2 and not kept:                          # a tall wall carries a frieze
                facade.frieze(pr, region, w, h * 0.68, earth, pr.p.seed)
            for (u0, v0, u1, v1) in spec["openings"]:
                if v0 == 0.0 and spec.get("gate"):
                    facade.gate(pr, region, u0, u1, v1, earth, WOOD, BAND)
                elif v0 == 0.0:
                    pr.rect(region, u0 - 0.1, 0, u1 + 0.1, v1 + 0.14, WOOD, _shade(WOOD, 0.7))
                    pr.rect(region, u0, 0, u1, v1, _shade(WOOD, 0.85), _shade(WOOD, 0.6), lw)
                    uu = u0 + 0.12
                    while uu < u1 - 0.05:
                        pr.vline(region, uu, 0, v1, _shade(WOOD, 0.65))
                        uu += 0.14
                elif kept:                                    # painted: the model keeps the triangles
                    facade.window(pr, region, u0, v0, u1, v1, earth, WOOD, u0 in spec.get("closed", ()))
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
    if "yard" in at:
        skin.coat(pr, "yard", "yard", SKIN)
    if "banner" in at:
        rb2 = at["banner"]
        pr.fill("banner", BAND)
        pr.mark("banner", 0, 0.16, rb2.world_w, rb2.world_h)
        stains("banner", rb2.world_w, rb2.world_h, 3, 0.14, 0.4)
        k = 0
        while k * 0.075 < rb2.world_w:                        # the fringe
            pr.rect("banner", k * 0.075, 0, min(rb2.world_w, k * 0.075 + 0.04), 0.16, (216, 202, 172))
            k += 1
        pr.rect("banner", 0, 0.16, rb2.world_w, 0.22, (216, 202, 172))
    if "coping" in at:
        pr.fill("coping", skin.mix(ADOBE, facade.CREAM, 0.36))
        pr.mottle("coping", 0.5, 0.06)
        pr.mottle("coping", 0.09, 0.05)
    if "step" in at:
        rs3 = at["step"]
        pale = skin.mix(ADOBE, facade.CREAM, 0.55)
        pr.fill("step", _shade(pale, 0.86))
        u = 0.0
        while u < rs3.world_w:                                # long slabs, their joints faint
            bw = float(rng.uniform(1.1, 1.9))
            pr.rect("step", u + 0.01, 0.0, min(rs3.world_w, u + bw - 0.01), rs3.world_h,
                    _shade(pale, float(rng.uniform(0.86, 0.98))))
            u += bw
        facade.worn(pr, "step", 0.0, 0.0, rs3.world_w, rs3.world_h, facade.random.Random(5))
    if "roof_flat" in at:
        skin.coat(pr, "roof_flat", "roof_kept" if pr.p.building_type == "PALACE" else "roof_flat", SKIN)
    if "parapet" in at:
        skin.coat(pr, "parapet", "parapet_kept" if pr.p.building_type == "PALACE" else "parapet", SKIN)
    if "trim" in at:
        skin.coat(pr, "trim", "trim_kept" if pr.p.building_type == "PALACE" else "trim", SKIN)
    if "frame" in at:
        pr.fill("frame", (96, 60, 34))
        pr.mottle("frame", 0.2, 0.08)
        pr.mottle("frame", 0.05, 0.08)
    if "pier" in at:
        skin.coat(pr, "pier", "pier_kept", SKIN)
        w, a, c, h, lane = parts.PIER_FACE
        facade.pier_side(pr, "pier", w, a, c, h)
        facade.pier_chamfer(pr, "pier", lane, 0.3, h)         # the line that divides it
        skin.coat(pr, "pier_cap", "parapet_kept", SKIN)
        pr.tone("pier_cap", 0.0, 0.0, 1.4, 1.2, 1.2)          # the cap takes the light
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
        if pr.p.building_type == "PALACE":                    # painted bands
            for v in (0.28, 0.42, 0.56):
                pr.rect("pot", 0, v, rpo.world_w, v + 0.05, (178, 150, 116))
            pr.mottle("pot", 0.1, 0.1)
    if "plinth" in at:
        rpl = at["plinth"]
        pr.base("plinth", _shade(MUD, 0.7), role="plinth")
        smears("plinth", _shade(MUD, 0.7), rpl.world_w, rpl.world_h, int(rpl.world_w * 4), 0.1)
    if "cloth" in at:
        rc = at["cloth"]
        cw, ch = rc.world_w, rc.world_h
        plain = pr.p.building_type == "PALACE"
        CREAM = (196, 176, 138)
        EARTH = _shade(CLOTH, 0.72)
        pattern = ((BAND, 0.3, True), (CREAM, 0.05, False), (EARTH, 0.22, False), (DARK, 0.04, False),
                   (CREAM, 0.14, False), (DARK, 0.04, False), (EARTH, 0.22, False), (CREAM, 0.05, False))
        pr.fill("cloth", EARTH)
        u, j = 0.0, 0
        if plain:                                             # the owner's plain cloth, two pale stripes
            pattern = ((BAND, 0.22, True), (CREAM, 0.09, False), (BAND, 0.1, True), (CREAM, 0.09, False),
                       (BAND, 2.5, True), (CREAM, 0.09, False), (BAND, 0.1, True), (CREAM, 0.09, False),
                       (BAND, 0.6, True))
        while u < cw:                                         # strips woven on a narrow loom
            col, sw, mine = pattern[j % len(pattern)]
            pr.rect("cloth", u, 0, min(cw, u + sw), ch, col)
            if mine:
                pr.mark("cloth", u, 0, min(cw, u + sw), ch)
            u += sw
            j += 1
        v = 0.0
        while v < ch:                                         # the weft, and blocks across the strips
            pr.tone("cloth", 0, v, cw, min(ch, v + 0.02), 0.93)
            v += 0.05
        for k in range(0 if plain else int(cw / 0.66) + 1):   # where two strips were sewn together
            pr.vline("cloth", k * 0.66, 0, ch, DARK, 1)
        for k in range(int(ch / 0.5) + 1):                    # soft folds down the fall of the cloth
            for j in range(3):
                pr.tone("cloth", 0, k * 0.5 + j * 0.05, cw, k * 0.5 + (j + 1) * 0.05, 0.9 + 0.03 * j)
        stains("cloth", cw, ch, int(cw * ch * 0.5) + 1, 0.18, 1.0)      # worn by sun and hands
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
        SOIL = (62, 44, 32)                                   # worked, watered earth
        pr.base("field", SOIL, role="plinth")
        pr.cracks("field", 0.3, 0.3, keep=0.5)
        for _ in range(int(rfi.world_w * rfi.world_h * 4)):   # clods and straw left in it
            u, v = float(rng.uniform(0, rfi.world_w)), float(rng.uniform(0, rfi.world_h))
            c = _shade(SOIL, float(rng.uniform(0.7, 1.5)))
            pr.paint_on("field", u, v, min(rfi.world_w, u + 0.1), min(rfi.world_h, v + 0.08), c)
        stains("field", rfi.world_w, rfi.world_h, 8, 0.16, 2.5)
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
    if "planks" in at:
        rp2 = at["planks"]
        pr.base("planks", WOOD, role="timber")
        u = 0.0
        while u < rp2.world_w:                                                   # boards with dark gaps
            pw = float(rng.uniform(0.16, 0.3))
            pr.tone("planks", u, 0, min(rp2.world_w, u + pw), rp2.world_h, float(rng.uniform(0.85, 1.25)))
            pr.vline("planks", u, 0, rp2.world_h, _shade(WOOD, 0.4), lw)
            u += pw
    if "crate" in at:
        rc3 = at["crate"]
        pr.base("crate", _shade(WOOD, 1.25), role="timber")
        v = 0.0
        while v < rc3.world_h:
            pr.hline("crate", v, 0, rc3.world_w, _shade(WOOD, 0.55), lw)
            v += 0.14
        u = 0.0
        while u < rc3.world_w:                                                   # the corner battens
            pr.rect("crate", u, 0, min(rc3.world_w, u + 0.07), rc3.world_h, _shade(WOOD, 0.8))
            u += 0.6
    if "barrel" in at:
        rb = at["barrel"]
        pr.base("barrel", _shade(WOOD, 1.15), role="timber")
        u = 0.0
        while u < rb.world_w:
            pr.vline("barrel", u, 0, rb.world_h, _shade(WOOD, 0.6), lw)
            u += 0.11
        for v in (0.1, 0.32, 0.4, 0.62):                                         # the hoops
            pr.rect("barrel", 0, v, rb.world_w, min(rb.world_h, v + 0.05), (58, 52, 50))
    if "iron" in at:
        pr.fill("iron", (58, 56, 60))
    if "ember" in at:
        re = at["ember"]
        pr.fill("ember", (222, 104, 34))
        stains("ember", re.world_w, re.world_h, 5, 0.5, 0.3)
    if "hide" in at:
        rh = at["hide"]
        pr.fill("hide", (150, 116, 80))
        for _ in range(int(rh.world_w * rh.world_h * 14)):                       # a cowhide's patches
            u, v = float(rng.uniform(0, rh.world_w)), float(rng.uniform(0, rh.world_h))
            c = (222, 208, 182) if rng.uniform(0, 1) < 0.5 else (58, 40, 30)
            pr.rect("hide", u, v, min(rh.world_w, u + float(rng.uniform(0.08, 0.26))),
                    min(rh.world_h, v + float(rng.uniform(0.08, 0.2))), c)
    if "rw_clay" in at:
        rk = at["rw_clay"]
        pr.base("rw_clay", _shade(C["tile"], 0.72), role="wall")
        pr.cracks("rw_clay", 0.12, 0.5)
        shade_band("rw_clay", rk.world_w, rk.world_h, rk.world_h - 0.5, 0.3)     # soot at the mouth
    if "crop" in at:
        rc2 = at["crop"]
        for k in range(14):                                   # green at the root, dry yellow at the tips
            t = k / 13
            c = (round(70 + t * 130), round(112 + t * 66), round(30 + t * 26))
            pr.rect("crop", 0, rc2.world_h * k / 14, rc2.world_w, rc2.world_h * (k + 1) / 14, c)
        for k in range(10):
            pr.vline("crop", rc2.world_w * (k + 0.5) / 10, 0, rc2.world_h, (58, 92, 28))
    if "crop_head" in at:
        rh2 = at["crop_head"]
        pr.fill("crop_head", (168, 124, 56))
        stains("crop_head", rh2.world_w, rh2.world_h, 6, 0.3, 0.15)
