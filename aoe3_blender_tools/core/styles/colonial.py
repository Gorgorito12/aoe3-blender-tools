# SPDX-License-Identifier: GPL-3.0-or-later
"""The Spanish colonial style: whitewashed walls on a low plinth, small windows with iron grilles
(rejas) and wooden shutters, a plank door, a clay tile roof (two slopes, or hipped) with a wide
eave, and optionally a wooden balcony, a portal (a front arcade of wooden posts or masonry arches
under a lean-to roof), a bell gable (espadana) over the front and a one-storey wing at the back
(an L plan). The shutters and the door leaf take the player colour."""
import math
from dataclasses import replace

from ..atlas import Region
from ..kit import (Builder, arcade_front_h, gable_roof_size, hipped_roof_size,
                   shed_roof_size)
from ..painter import PLAYER_GREY, _shade

NAME = "COLONIAL"
STOREY_H = 2.9
EAVE = 0.45             # the roof's overhang beyond the walls
SHED_PITCH = 0.22       # the portal's lean-to roof
MIN_STEP = 1.5          # a window, its shutters and some wall
CHOICES = {"roof_type": ("GABLE", "HIPPED"), "ridge": ("ALONG", "ACROSS"), "arcade": ("NONE", "FRONT"),
           "arcade_posts": ("WOOD", "MASONRY"), "plan": ("BLOCK", "L")}


def _choice(value, key):
    v = str(value).upper()
    return v if v in CHOICES[key] else CHOICES[key][0]


def clamp(p):
    """Returns a copy with values the geometry can build."""
    p = replace(p, colors=dict(p.colors))
    p.width = max(5.0, min(30.0, p.width))
    p.depth = max(4.5, min(20.0, p.depth))
    p.storeys = max(1, min(3, int(p.storeys)))
    p.plinth = max(0.15, min(0.6, p.plinth))
    p.roof_pitch = max(0.25, min(0.8, p.roof_pitch))
    p.bay_spacing = max(MIN_STEP, p.bay_spacing)
    p.chimneys = max(0, min(2, int(p.chimneys)))
    for key in CHOICES:
        setattr(p, key, _choice(getattr(p, key), key))
    p.arcade_depth = max(1.6, min(3.5, p.arcade_depth))
    if p.width < 6.0:
        p.arcade = "NONE"
    p.balcony = bool(p.balcony) and p.storeys >= 2
    if p.plan == "L" and (p.width < 8.0 or p.depth < 6.0):
        p.plan = "BLOCK"
    if p.plan == "L":                 # the wing's roof runs into a gable whose ridge is along X
        p.roof_type, p.ridge = "GABLE", "ALONG"
        p.wing_width = max(3.5, min(p.wing_width, p.width * 0.6, p.depth - 1.0))
        p.wing_depth = max(3.0, min(p.wing_depth, 10.0))
    p.bell_gable = bool(p.bell_gable)
    p.rejas = bool(p.rejas)
    p.cupola = False
    p.flagpole = False
    p.portico = False
    p.wings = False
    p.back_portico = "NONE"
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "LOW"
    p.texture_size = 1 << int(round(math.log2(max(256, min(4096, p.texture_size)))))
    return p


def bays(length, spacing, margin=1.0):
    """An odd number of evenly spaced bays (one on the axis), `margin` from the corners, at the
    spacing closest to `spacing`."""
    usable = length - 2 * margin
    if usable < MIN_STEP:
        return [length / 2]
    best, n = (1e9, 1), 3
    while usable / (n - 1) >= MIN_STEP:
        score = abs(usable / (n - 1) - spacing)
        if score < best[0]:
            best = (score, n)
        n += 2
    n = best[1]
    return [length / 2] if n == 1 else [margin + i * usable / (n - 1) for i in range(n)]


def openings(spec, storey_h=STOREY_H):
    """(u0, v0, u1, v1) of every opening of a facade (v from the plinth top), the same rectangles
    the painter draws."""
    out = []
    for uc in spec["bays"]:
        for st in range(spec.get("storeys", 1)):
            base = st * storey_h
            if st == 0 and spec.get("door") is not None and abs(uc - spec["door"]) < 0.01:
                out.append((uc - 0.65, 0.0, uc + 0.65, 2.5))
            elif st == 0:
                out.append((uc - 0.4, 0.9, uc + 0.4, 2.2))
            elif st == 1 and any(abs(uc - b) < 0.01 for b in spec.get("balcony", ())):
                out.append((uc - 0.4, base + 0.1, uc + 0.4, base + 2.15))
            else:       # no wider than the window below: the wall stays one polygon with holes
                out.append((uc - 0.4, base + 0.6, uc + 0.4, base + 2.1))
    return out


def opening_tops(spec, p):
    return [2.2 if s == 0 else s * STOREY_H + 2.1 for s in range(spec.get("storeys", p.storeys))]


def build(p, params):
    W, D = p.width, p.depth
    medium = p.detail == "MEDIUM"
    z0 = p.plinth
    wall_h = p.storeys * STOREY_H
    wall_top = z0 + wall_h
    pitch = p.roof_pitch
    gable = p.roof_type == "GABLE"
    along = p.ridge == "ALONG"
    ex, ey = W / 2 + EAVE, D / 2 + EAVE
    if gable:
        ridge_z = wall_top + pitch * (D / 2 if along else W / 2)
    else:
        ridge_z = wall_top - pitch * EAVE + pitch * min(ex, ey)

    def roof_z(x, y):
        if gable and along:
            return wall_top + pitch * (D / 2 - abs(y))
        if gable:
            return wall_top + pitch * (W / 2 - abs(x))
        return wall_top - pitch * EAVE + pitch * max(0.0, min(ex - abs(x), ey - abs(y)))

    # --- layout -----------------------------------------------------------------------------------
    front_bays = bays(W, p.bay_spacing)
    if not any(abs(u - W / 2) < 0.01 for u in front_bays):
        front_bays = sorted(front_bays + [W / 2])
    eave_front = (not gable) or along
    facades = {
        "front": {"bays": front_bays, "door": W / 2, "storeys": p.storeys, "eave": eave_front,
                  "shutters": True},
        "back": {"bays": bays(W, p.bay_spacing * 1.5), "door": None, "storeys": p.storeys,
                 "eave": eave_front, "shutters": True},
        "side": {"bays": [D / 2] if D < 10.0 else bays(D, 3.5), "door": None, "storeys": p.storeys,
                 "eave": (not gable) or not along, "shutters": False},
    }
    gaps = [b - a for a, b in zip(front_bays, front_bays[1:])] or [W]
    bal_half = min(max(1.3, min(gaps) + 0.6), W / 2 - 0.8)
    if p.balcony:
        facades["front"]["balcony"] = [u for u in front_bays if abs(u - W / 2) <= bal_half - 0.55]
    hw, wd = p.wing_width / 2, p.wing_depth
    wx = W / 2 - 0.3 - hw
    if p.plan == "L":
        facades["wing_long"] = {"bays": bays(wd, p.bay_spacing), "door": None, "storeys": 1, "eave": True,
                                "shutters": True}
        facades["wing_short"] = {"bays": bays(2 * hw, p.bay_spacing), "door": None, "storeys": 1,
                                 "eave": False, "shutters": True}
    arcade = p.arcade == "FRONT"
    ya = -D / 2 - p.arcade_depth                      # the portal's front plane
    n_arch = max(2, int(round(W / 3.0)))
    post_half = 0.13 if p.arcade_posts == "WOOD" else 0.22
    kind = "POST" if p.arcade_posts == "WOOD" else "ARCH"
    shed_top = z0 + STOREY_H - 0.15
    arc_top = shed_top - SHED_PITCH * p.arcade_depth - 0.05
    arc_h = arc_top - z0
    span = (W - 2 * post_half * (n_arch + 1)) / n_arch
    rise = max(0.3, min(span / 2, arc_h - 0.45 - 1.7))     # piers of 1.7 m at least: a flat arch
    wing_top = z0 + STOREY_H
    rz_w = wing_top + pitch * hw
    if rz_w <= wall_top - 0.05:
        y0_w = D / 2 - 0.1                            # the wing's roof ends against the back wall
    else:
        y0_w = D / 2 - (rz_w - wall_top) / pitch - 0.1  # it runs into the main roof
    bell_w = min(3.2, max(1.8, W * 0.28))
    bell_z0 = wall_top - 0.6
    bell_h = ridge_z - bell_z0 + 0.4
    bell_peak = 0.35 * bell_w

    # --- atlas ------------------------------------------------------------------------------------
    b = Builder(p.texture_size, medium)
    b.region("front", W, wall_h)
    b.region("back", W, wall_h)
    b.region("side", D, wall_h)
    if gable:
        roof, gab = gable_roof_size(W / 2, D / 2, pitch, "X" if along else "Y", EAVE)
        if p.plan == "L":
            wroof, wgab = gable_roof_size(hw, wd / 2, pitch, "Y", EAVE)
            length = D / 2 + wd + EAVE - y0_w
            roof = (max(roof[0], length + 0.2), max(roof[1], wroof[1]))
            gab = (max(gab[0], wgab[0]), max(gab[1], wgab[1]))
    else:
        roof, gab = hipped_roof_size(ex, ey, pitch), None
    b.region("roof", *roof)
    b.region("plinth", max(W, D) + 0.4, max(z0, 0.3))
    b.region("white", 2.0, 3.5)
    if gab:
        b.region("gable", *gab)
    if medium:
        b.region("reveal", 1.4, 2.6)
        b.region("ridge", max(W, D) + 2 * EAVE + 0.4, 0.4)
    if p.plan == "L":
        b.region("wing_long", wd, STOREY_H)
        b.region("wing_short", 2 * hw, STOREY_H)
    if arcade:
        b.region("shed", *shed_roof_size(W, p.arcade_depth + 0.15, SHED_PITCH))
        b.region("post", 2.0, arc_h)
        b.region("arcade", W, arcade_front_h(arc_h, n_arch, -W / 2, W / 2, post_half, kind, medium,
                                             lintel_h=0.45, arch_rise=rise))
    if p.balcony:
        b.region("slab", 2 * bal_half, 1.0)
        b.region("rail", 2 * bal_half, 0.9)
    if p.bell_gable:
        b.region("bell", bell_w, bell_h + bell_peak)
    b.pack()

    def make_wall(origin, ua, length, height, region, spec):
        if medium:
            b.wall(origin, ua, length, height, region, openings(spec))
        else:
            b.flat_wall(origin, ua, length, height, region)

    # --- geometry ---------------------------------------------------------------------------------
    b.box(-W / 2 - 0.1, W / 2 + 0.1, -D / 2 - 0.1, D / 2 + 0.1, 0, z0, "plinth", "plinth")
    make_wall((-W / 2, -D / 2, z0), (1.0, 0.0, 0.0), W, wall_h, "front", facades["front"])
    make_wall((W / 2, D / 2, z0), (-1.0, 0.0, 0.0), W, wall_h, "back", facades["back"])
    make_wall((-W / 2, D / 2, z0), (0.0, -1.0, 0.0), D, wall_h, "side", facades["side"])
    make_wall((W / 2, -D / 2, z0), (0.0, 1.0, 0.0), D, wall_h, "side", facades["side"])
    if gable:
        b.gable_roof(0.0, 0.0, W / 2, D / 2, wall_top, pitch, "X" if along else "Y", "roof",
                     gable_region="gable", overhang=EAVE)
        if medium:
            if along:
                b.ridge_cap((-ex, 0.0), (ex, 0.0), ridge_z, "ridge")
            else:
                b.ridge_cap((0.0, -ey), (0.0, ey), ridge_z, "ridge")
    else:
        b.hipped_roof(0.0, 0.0, ex, ey, wall_top - pitch * EAVE, pitch)

    if p.plan == "L":
        b.box(wx - hw - 0.1, wx + hw + 0.1, D / 2 + 0.1, D / 2 + wd + 0.1, 0, z0, "plinth", "plinth",
              skip=("-y",))
        make_wall((wx - hw, D / 2 + wd, z0), (0.0, -1.0, 0.0), wd, STOREY_H, "wing_long", facades["wing_long"])
        make_wall((wx + hw, D / 2, z0), (0.0, 1.0, 0.0), wd, STOREY_H, "wing_long", facades["wing_long"])
        make_wall((wx + hw, D / 2 + wd, z0), (-1.0, 0.0, 0.0), 2 * hw, STOREY_H, "wing_short",
                  facades["wing_short"])
        b.gable_roof(wx, D / 2 + wd / 2, hw, wd / 2, wing_top, pitch, "Y", "roof", gable_region="gable",
                     overhang=EAVE, gables=(False, True), ends=(y0_w, D / 2 + wd + EAVE))
        if medium:
            b.ridge_cap((wx, y0_w), (wx, D / 2 + wd + EAVE), rz_w, "ridge")

    if arcade:
        b.box(-W / 2, W / 2, ya - 0.15, -D / 2 - 0.1, 0, z0, "plinth", "plinth", skip=("+y",))
        b.arcade(-W / 2, W / 2, ya, z0, arc_h, n_arch, 0.35, post_half, "post", "arcade", kind=kind,
                 lintel_h=0.45, arch_rise=rise)
        b.shed_roof((-W / 2, -D / 2, 0.0), (1.0, 0.0, 0.0), W, p.arcade_depth + 0.15, shed_top, SHED_PITCH,
                    "shed")

    if p.balcony:
        b.balcony(-bal_half, bal_half, -D / 2, z0 + STOREY_H + 0.05, 0.8, "slab", "rail")

    if p.bell_gable:
        apex = b.bell_gable(0.0, -D / 2 - 0.03, bell_z0, bell_w, bell_h, 0.35, "bell",
                            peak=bell_peak, side_region="white")
        b.attach["flag_attach"] = apex
    else:
        b.attach["flag_attach"] = (0.0, 0.0, ridge_z + 0.1)

    if gable and along:
        spots = [(-(W / 2 - 1.3), D * 0.22), (W / 2 - 1.3, D * 0.22)]
    elif gable:
        spots = [(W * 0.22, D / 2 - 1.3), (W * 0.22, -(D / 2 - 1.3))]
    else:
        spots = [(-(W / 2 - 1.6), D * 0.18), (W / 2 - 1.6, D * 0.18)]
    kept = []
    for cx, cy in spots[:p.chimneys]:
        if p.bell_gable and abs(cx) < bell_w / 2 + 0.8 and cy < -D / 2 + 1.5:
            continue
        kept.append((cx, cy))
        top = ridge_z + 0.5
        b.chimney(cx, cy, roof_z(cx, cy) - 0.4, top, side="white", band="white", cap_top="white")
    if kept:
        cx, cy = kept[0]
        b.attach["chimney_attach"] = (cx, cy, ridge_z + 0.75)

    notes = []
    if params.balcony and not p.balcony:
        notes.append("Balcony: needs two storeys or more.")
    if str(params.arcade).upper() == "FRONT" and not arcade:
        notes.append("Portal: needs a front of 6 m or more.")
    if str(params.plan).upper() == "L" and p.plan != "L":
        notes.append("L plan: needs a block of 8 x 6 m or more.")
    if int(params.chimneys) > p.chimneys:
        notes.append(f"Chimneys {params.chimneys} -> {p.chimneys}: two at most in this style.")
    return b.finish(p, facades, {"wall_h": wall_h, "storeys": p.storeys, "ridge_z": ridge_z}, notes)


# --------------------------------------------------------------------------------------------------
# Texture

def paint(pr, model):
    p = model.params
    at = pr.at
    C = pr.C
    PL, TILE, TIMBER, IRON = C["plaster"], C["tile"], C["timber"], C["iron"]
    GLASS, DOOR, DADO = C["glass"], C["door"], C["plinth"]
    LINE = _shade(PL, 0.86)
    SHUT = PLAYER_GREY if pr.pc else (70, 96, 92)
    lw = pr.lw

    def window(region, u0, v0, u1, v1, reja, shutters, room):
        w, h = u1 - u0, v1 - v0
        pr.rect(region, u0 - 0.08, v0 - 0.08, u1 + 0.08, v1 + 0.08, _shade(PL, 0.93))     # a lime frame
        pr.rect(region, u0 - 0.1, v1, u1 + 0.1, v1 + 0.14, TIMBER, _shade(TIMBER, 0.7))   # the lintel
        pr.rect(region, u0, v0, u1, v1, GLASS)
        pr.vline(region, (u0 + u1) / 2, v0, v1, TIMBER, lw)                              # casements
        pr.hline(region, v0 + h * 0.55, u0, u1, TIMBER, lw)
        pr.rect(region, u0, v0, u1, v1, None, TIMBER, lw)
        if reja:
            u = u0 + 0.06
            while u < u1 - 0.03:
                pr.vline(region, u, v0 - 0.04, v1 + 0.04, IRON, lw)
                u += 0.13
            for vv in (v0 + h * 0.3, v0 + h * 0.75):
                pr.hline(region, vv, u0 - 0.04, u1 + 0.04, IRON, lw)
        if shutters:
            sw = min(w / 2 + 0.05, room)
            if sw >= 0.2:
                for a in (u0 - 0.06 - sw, u1 + 0.06):
                    pr.rect(region, a, v0 - 0.02, a + sw, v1 + 0.02, SHUT, _shade(SHUT, 0.7))
                    pr.mark(region, a, v0 - 0.02, a + sw, v1 + 0.02)
                    vv = v0 + 0.1
                    while vv < v1 - 0.05:
                        pr.hline(region, vv, a + 0.04, a + sw - 0.04, _shade(SHUT, 0.8))
                        vv += 0.16

    def door(region, u0, v0, u1, v1):
        pr.rect(region, u0 - 0.15, v0, u1 + 0.15, v1 + 0.22, _shade(PL, 0.93))
        pr.rect(region, u0 - 0.15, v1, u1 + 0.15, v1 + 0.2, TIMBER, _shade(TIMBER, 0.7))
        leaf = PLAYER_GREY if pr.pc else DOOR
        pr.rect(region, u0, v0, u1, v1, leaf, _shade(leaf, 0.6), lw)
        pr.mark(region, u0 + 0.05, v0, u1 - 0.05, v1 - 0.05)
        u = u0 + 0.16
        while u < u1 - 0.05:
            pr.vline(region, u, v0, v1, _shade(leaf, 0.7))
            u += 0.16
        pr.vline(region, (u0 + u1) / 2, v0, v1, _shade(leaf, 0.5), lw)
        for vv in (v0 + 0.5, v0 + 1.3, v1 - 0.4):                          # iron studs
            for uu in (u0 + 0.2, u1 - 0.2):
                pr.rect(region, uu - 0.03, vv - 0.03, uu + 0.03, vv + 0.03, IRON)

    def balcony_door(region, u0, v0, u1, v1):
        pr.rect(region, u0 - 0.08, v0, u1 + 0.08, v1 + 0.1, _shade(PL, 0.93))
        pr.rect(region, u0, v0, u1, v1, GLASS, TIMBER, 2 * lw)
        pr.vline(region, (u0 + u1) / 2, v0, v1, TIMBER, 2 * lw)
        for k in (1, 2):
            pr.hline(region, v0 + (v1 - v0) * k / 3, u0, u1, TIMBER, lw)
        pr.rect(region, u0, v0, u1, v0 + 0.6, _shade(TIMBER, 1.1), _shade(TIMBER, 0.7))

    for region, spec in model.facades.items():
        r = at[region]
        sw, sh = r.world_w, r.world_h
        pr.base(region, PL, role="wall")
        pr.paint_on(region, 0, 0, sw, 0.55, DADO, _shade(DADO, 0.8))          # the dado band
        if spec.get("eave"):                                                  # beam ends under the eave
            u = 0.25
            while u < sw - 0.2:
                pr.rect(region, u, sh - 0.22, u + 0.16, sh - 0.04, TIMBER, _shade(TIMBER, 0.7))
                u += 0.62
        ops = openings(spec)
        bays_ = spec["bays"]
        gaps = [b2 - b1 for b1, b2 in zip(bays_, bays_[1:])] or [sw]
        room = max(0.0, min(min(gaps) / 2 - 0.55, min(bays_[0], sw - bays_[-1]) - 0.7))
        for (u0, v0, u1, v1) in ops:
            if v0 == 0.0:
                door(region, u0, v0, u1, v1)
            elif v1 - v0 > 1.9:
                balcony_door(region, u0, v0, u1, v1)
            else:
                ground = v1 <= 2.3
                window(region, u0, v0, u1, v1, p.rejas and ground, spec.get("shutters") and not ground, room)

    if "gable" in at:
        pr.base("gable", PL, role="wall")
        r = at["gable"]
        cx, cy = pr.P("gable", r.world_w / 2, min(r.world_h * 0.45, 1.0))
        rr = 0.18 * pr.px_per_m
        pr.cv.ellipse(cx, cy, rr + lw, rr + lw, TIMBER)
        pr.cv.ellipse(cx, cy, rr, rr, _shade(GLASS, 0.8))

    def tiles(region):
        """Spanish tiles: columns of barrel tiles, each course a little lighter at its lower end."""
        r = at[region]
        pr.base(region, _shade(TILE, 0.62), role="roof")
        u, col = 0.0, 0
        while u < r.world_w:
            v, row = 0.0, 0
            t0 = int(pr.rng.integers(-10, 11))
            while v < r.world_h:
                t = t0 + int(pr.rng.integers(-8, 9))
                c = tuple(max(0, min(255, k + t)) for k in TILE)
                u1 = min(u + 0.19, r.world_w)
                pr.paint_on(region, u + 0.03, v, u1, min(v + 0.42, r.world_h), c)
                pr.paint_on(region, u + 0.03, v, u1, min(v + 0.07, r.world_h), _shade(c, 0.78))
                if u + 0.11 < r.world_w:
                    pr.vline(region, u + 0.11, v + 0.08, min(v + 0.4, r.world_h), _shade(c, 1.12), lw)
                v += 0.4
                row += 1
            u += 0.22
            col += 1

    tiles("roof")
    if "shed" in at:
        tiles("shed")
    if "ridge" in at:
        tiles("ridge")

    PLN = DADO
    pr.base("plinth", _shade(PLN, 0.9), role="plinth")
    rp = at["plinth"]
    u = 0.0
    while u < rp.world_w:
        pr.vline("plinth", u, 0, rp.world_h, _shade(PLN, 0.7), lw)
        u += 0.55
    pr.hline("plinth", rp.world_h - 0.03, 0, rp.world_w, _shade(PLN, 1.1), lw)

    pr.base("white", PL, role="wall")
    if "reveal" in at:
        pr.fill("reveal", _shade(PL, 0.8))

    if "post" in at:
        if p.arcade_posts == "WOOD":
            pr.base("post", TIMBER, role="timber")
            rp = at["post"]
            for i in range(14):
                pr.vline("post", rp.world_w * (i + 0.5) / 14, 0, rp.world_h, _shade(TIMBER, 0.82))
        else:
            pr.base("post", PL, role="wall")
            pr.rect("post", 0, 0, at["post"].world_w, 0.4, DADO, _shade(DADO, 0.8))
    if "arcade" in at:
        ra = at["arcade"]
        if p.arcade_posts == "WOOD":
            pr.base("arcade", TIMBER, role="timber")
            pr.hline("arcade", 0.05, 0, ra.world_w, _shade(TIMBER, 0.7), lw)
            pr.hline("arcade", ra.world_h - 0.06, 0, ra.world_w, _shade(TIMBER, 1.15), lw)
        else:
            pr.base("arcade", PL, role="wall")
            pr.rect("arcade", 0, ra.world_h - 0.12, ra.world_w, ra.world_h, _shade(PL, 0.9), LINE)
    if "slab" in at:
        pr.base("slab", TIMBER, role="timber")
        rs = at["slab"]
        vv = 0.0
        while vv < rs.world_h:
            pr.hline("slab", vv, 0, rs.world_w, _shade(TIMBER, 0.75))
            vv += 0.18
    if "rail" in at:
        rr_ = at["rail"]
        pr.fill("rail", _shade(TIMBER, 0.45))                                  # the gaps
        pr.rect("rail", 0, 0, rr_.world_w, 0.1, TIMBER, _shade(TIMBER, 0.7))      # rails and balusters
        pr.rect("rail", 0, rr_.world_h - 0.12, rr_.world_w, rr_.world_h, TIMBER, _shade(TIMBER, 0.7))
        u = 0.06
        while u < rr_.world_w - 0.05:
            pr.rect("rail", u, 0.1, u + 0.06, rr_.world_h - 0.12, _shade(TIMBER, 1.1))
            u += 0.14
    if "bell" in at:
        rb = at["bell"]
        pr.base("bell", PL, role="wall")
        n = 2 if rb.world_w >= 2.4 else 1
        top = rb.world_h - 0.35 * rb.world_w
        for k in range(n):
            uc = rb.world_w * (k + 1) / (n + 1)
            ow, oh = 0.62, 0.95
            ob = top - oh - 0.35
            pr.rect("bell", uc - ow / 2, ob, uc + ow / 2, ob + oh, (58, 50, 44))
            cx, cy = pr.P("bell", uc, ob + oh)
            pr.cv.ellipse(cx, cy, ow / 2 * pr.px_per_m, ow / 2 * pr.px_per_m, (58, 50, 44), upper_half=True)
            bx, by = pr.P("bell", uc, ob + oh * 0.55)
            pr.cv.ellipse(bx, by, 0.2 * pr.px_per_m, 0.26 * pr.px_per_m, (150, 112, 52))
            pr.rect("bell", uc - 0.24, ob + oh * 0.3, uc + 0.24, ob + oh * 0.4, (130, 96, 44))
            pr.rect("bell", uc - ow / 2 - 0.08, ob - 0.08, uc + ow / 2 + 0.08, ob, _shade(PL, 0.88))
        cx, cy = pr.P("bell", rb.world_w / 2, rb.world_h - 0.3)
        pr.rect("bell", rb.world_w / 2 - 0.04, rb.world_h - 0.55, rb.world_w / 2 + 0.04, rb.world_h - 0.08, IRON)
        pr.rect("bell", rb.world_w / 2 - 0.15, rb.world_h - 0.32, rb.world_w / 2 + 0.15, rb.world_h - 0.26, IRON)


def random_params(rng, i, BuildingParams):
    """Random colonial options for the sweep (rng: random.Random)."""
    return BuildingParams(
        name=f"Colonial{i}", style=NAME, width=rng.uniform(5, 18), depth=rng.uniform(4.5, 14),
        storeys=rng.randint(1, 3), plinth=rng.choice([0.2, 0.3, 0.5]), roof_pitch=rng.uniform(0.25, 0.8),
        bay_spacing=rng.uniform(1.5, 3.5), chimneys=rng.randint(0, 3),
        roof_type=rng.choice(["GABLE", "HIPPED"]), ridge=rng.choice(["ALONG", "ACROSS"]),
        arcade=rng.choice(["NONE", "FRONT"]), arcade_posts=rng.choice(["WOOD", "MASONRY"]),
        arcade_depth=rng.uniform(1.6, 3.5), balcony=rng.random() < 0.5, bell_gable=rng.random() < 0.4,
        plan=rng.choice(["BLOCK", "L"]), wing_width=rng.uniform(3, 9), wing_depth=rng.uniform(3, 9),
        rejas=rng.random() < 0.7, detail=rng.choice(["LOW", "MEDIUM"]), texture_size=256,
        player_colour=rng.random() < 0.3, materials=rng.random() < 0.3)
