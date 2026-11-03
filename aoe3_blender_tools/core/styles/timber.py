# SPDX-License-Identifier: GPL-3.0-or-later
"""The European timber-framed style: a ground floor of rubble stone, brick or timber, upper floors
of timber framing (posts, rails and braces painted over plaster or brick infill) jutting out over
the street on joists, a steep tiled roof with its gables framed like the walls, dormers on the
front slope, brick chimneys and a hanging sign. The shutters, the door and the sign take the
player colour."""
import math
from dataclasses import replace

from ..kit import Builder, gable_roof_size, gable_roof_z
from ..painter import PLAYER_GREY, _shade
from .colonial import bays

NAME = "TIMBER"
STOREY_H = 2.7          # an upper storey
GROUND_STONE_H = 3.0    # a ground floor of stone or brick is taller
EAVE = 0.35
DORMER_W, DORMER_H, DORMER_INSET, DORMER_PITCH = 1.2, 1.1, 0.8, 1.0
CHOICES = {"ground_floor": ("STONE", "BRICK", "TIMBER"), "infill": ("PLASTER", "BRICK"),
           "bracing": ("CROSS", "CURVED", "PLAIN")}


def clamp(p):
    p = replace(p, colors=dict(p.colors))
    p.width = max(5.0, min(24.0, p.width))
    p.depth = max(4.5, min(16.0, p.depth))
    p.storeys = max(1, min(3, int(p.storeys)))
    p.plinth = max(0.15, min(0.6, p.plinth))
    p.roof_pitch = max(0.7, min(1.6, p.roof_pitch))
    p.bay_spacing = max(1.6, p.bay_spacing)
    p.chimneys = max(0, min(2, int(p.chimneys)))
    for key, vals in CHOICES.items():
        v = str(getattr(p, key)).upper()
        setattr(p, key, v if v in vals else vals[0])
    p.jetty = bool(p.jetty) and p.storeys >= 2
    p.jetty_depth = max(0.2, min(0.8, p.jetty_depth))
    p.dormers = max(0, min(int(p.dormers), int((p.width - 2.0) / 2.2), 4))
    p.signboard = bool(p.signboard)
    p.cupola = p.flagpole = p.portico = p.wings = p.balcony = p.bell_gable = False
    p.back_portico, p.arcade, p.plan = "NONE", "NONE", "BLOCK"
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "LOW"
    p.texture_size = 1 << int(round(math.log2(max(256, min(4096, p.texture_size)))))
    return p


def _openings(bays_, door, ground, storeys, storey_h):
    """(u0, v0, u1, v1) per opening, and the top of each storey's openings."""
    out = []
    for uc in bays_:
        for st in range(storeys):
            base = st * storey_h
            if ground and door is not None and abs(uc - door) < 0.01:
                out.append((uc - 0.55, 0.0, uc + 0.55, 2.2))
            elif ground:
                out.append((uc - 0.35, 1.0, uc + 0.35, 2.0))
            else:
                out.append((uc - 0.45, base + 0.7, uc + 0.45, base + 2.0))
    tops = [2.0] if ground else [st * storey_h + 2.0 for st in range(storeys)]
    return out, tops


def opening_tops(spec, p):
    return spec["tops"]


def build(p, params):
    W, D = p.width, p.depth
    medium = p.detail == "MEDIUM"
    z0 = p.plinth
    ground_h = GROUND_STONE_H if p.ground_floor in ("STONE", "BRICK") else STOREY_H
    zg = z0 + ground_h
    uppers = p.storeys - 1
    up_h = uppers * STOREY_H
    wall_top = zg + up_h
    j = p.jetty_depth if p.jetty else 0.0
    hy = D / 2 + j                                   # the upper floors' half-depth (the roof's)
    pitch = p.roof_pitch
    ridge_z = wall_top + pitch * hy
    ex = W / 2 + EAVE

    # --- layout ---------------------------------------------------------------------------------
    facades = {}

    def facade(name, length, door, ground, storeys, storey_h, spacing=None, single=False):
        bs = [length / 2] if single else bays(length, spacing or p.bay_spacing)
        if door is not None and not any(abs(u - door) < 0.01 for u in bs):
            bs = sorted(bs + [door])
        ops, tops = _openings(bs, door, ground, storeys, storey_h)
        facades[name] = {"bays": bs, "door": door, "storeys": storeys, "ground": ground,
                         "openings": ops, "tops": tops, "storey_h": storey_h}

    facade("front_g", W, W / 2, True, 1, ground_h)
    facade("back_g", W, None, True, 1, ground_h, spacing=p.bay_spacing * 1.6)
    facade("side_g", D, None, True, 1, ground_h, single=D < 10.0)
    if uppers:
        facade("front_u", W, None, False, uppers, STOREY_H)
        facade("back_u", W, None, False, uppers, STOREY_H, spacing=p.bay_spacing * 1.6)
        facade("side_u", D + 2 * j, None, False, uppers, STOREY_H, single=D + 2 * j < 10.0)
    n_dorm = p.dormers
    reach = hy - DORMER_INSET - (DORMER_H + DORMER_PITCH * DORMER_W / 2) / pitch
    if reach < 0.3:
        n_dorm = 0
    dorm_x = [-W / 2 + (i + 1) * W / (n_dorm + 1) for i in range(n_dorm)]
    sign_x = min(W / 2 - 0.6, 1.6)                   # beside the door, from the centre
    sign_z = zg - 0.55

    # --- atlas ----------------------------------------------------------------------------------
    b = Builder(p.texture_size, medium)
    b.region("front_g", W, ground_h)
    b.region("back_g", W, ground_h)
    b.region("side_g", D, ground_h)
    if uppers:
        b.region("front_u", W, up_h)
        b.region("back_u", W, up_h)
        b.region("side_u", D + 2 * j, up_h)
    roof, gab = gable_roof_size(W / 2, hy, pitch, "X", EAVE)
    b.region("roof", *roof)
    b.region("gable", *gab)
    b.region("plinth", max(W, D) + 0.4, max(z0, 0.3))
    b.region("brick", 3.0, 3.0)
    b.region("ends", 0.8, 0.4)
    if n_dorm:
        b.region("dormer", DORMER_W, DORMER_H)
        b.region("dormer_side", 1.6, 1.8)
    if j:
        b.region("soffit", W, j)
    if medium:
        b.region("reveal", 1.2, 2.2)
        b.region("ridge", W + 2 * EAVE + 0.4, 0.4)
    if p.signboard:
        b.region("sign", 0.6, 0.5)
    b.pack()

    def make_wall(origin, ua, length, height, region):
        if medium:
            b.wall(origin, ua, length, height, region, facades[region]["openings"])
        else:
            b.flat_wall(origin, ua, length, height, region)

    # --- geometry -------------------------------------------------------------------------------
    b.box(-W / 2 - 0.1, W / 2 + 0.1, -D / 2 - 0.1, D / 2 + 0.1, 0, z0, "plinth", "plinth")
    make_wall((-W / 2, -D / 2, z0), (1.0, 0.0, 0.0), W, ground_h, "front_g")
    make_wall((W / 2, D / 2, z0), (-1.0, 0.0, 0.0), W, ground_h, "back_g")
    make_wall((-W / 2, D / 2, z0), (0.0, -1.0, 0.0), D, ground_h, "side_g")
    make_wall((W / 2, -D / 2, z0), (0.0, 1.0, 0.0), D, ground_h, "side_g")
    if uppers:
        make_wall((-W / 2, -hy, zg), (1.0, 0.0, 0.0), W, up_h, "front_u")
        make_wall((W / 2, hy, zg), (-1.0, 0.0, 0.0), W, up_h, "back_u")
        make_wall((-W / 2, hy, zg), (0.0, -1.0, 0.0), D + 2 * j, up_h, "side_u")
        make_wall((W / 2, -hy, zg), (0.0, 1.0, 0.0), D + 2 * j, up_h, "side_u")
    if j:
        n_ends = max(3, int(W / 1.5))                # joist ends show on the street front only
        b.jetty(-W / 2, W / 2, -D / 2, zg, j, "soffit", "ends", n_ends, side=-1)
        b.jetty(-W / 2, W / 2, D / 2, zg, j, "soffit", "ends", 0, side=1)
    b.gable_roof(0.0, 0.0, W / 2, hy, wall_top, pitch, "X", "roof", gable_region="gable", overhang=EAVE)
    if medium:
        b.ridge_cap((-ex, 0.0), (ex, 0.0), ridge_z, "ridge")
    for x in dorm_x:
        b.dormer(x, 0.0, hy, wall_top, pitch, -1, DORMER_INSET, DORMER_W, DORMER_H, DORMER_PITCH,
                 wall_region="dormer", roof_region="roof", cheek_region="dormer_side")
    b.attach["flag_attach"] = (0.0, 0.0, ridge_z + 0.1)

    kept = []
    for cx, cy in [(-(W / 2 - 1.2), hy * 0.45), (W / 2 - 1.2, hy * 0.45)][:p.chimneys]:
        kept.append((cx, cy))
        foot = gable_roof_z(cx, cy, 0.0, 0.0, W / 2, hy, wall_top, pitch) - 0.4
        b.chimney(cx, cy, foot, ridge_z + 0.6, side="brick", band="brick", cap_top="brick")
    if kept:
        b.attach["chimney_attach"] = (kept[0][0], kept[0][1], ridge_z + 0.85)

    if p.signboard:
        # an iron bracket from the front wall and the board hanging from it, across the street
        b.box(sign_x - 0.04, sign_x + 0.04, -D / 2 - 0.9, -D / 2, sign_z, sign_z + 0.08, "ends", "ends",
              skip=("+y",))
        b.box(sign_x - 0.025, sign_x + 0.025, -D / 2 - 0.85, -D / 2 - 0.3, sign_z - 0.45, sign_z, "sign", "ends")

    notes = []
    if int(params.dormers) > n_dorm:
        notes.append(f"Dormers {params.dormers} -> {n_dorm}: they must fit the front slope.")
    if params.jetty and not p.jetty:
        notes.append("Jetty: needs two storeys or more.")
    if int(params.chimneys) > p.chimneys:
        notes.append(f"Chimneys {params.chimneys} -> {p.chimneys}: two at most in this style.")
    return b.finish(p, facades, {"wall_h": ground_h + up_h, "storeys": p.storeys, "ridge_z": ridge_z}, notes)


# --------------------------------------------------------------------------------------------------
# Texture

def paint(pr, model):
    p = model.params
    at = pr.at
    C = pr.C
    TIMBER, PLASTER, STONE, BRICK = C["timber"], C["plaster"], C["stone"], C["brick"]
    TILE, GLASS, LEAD = C["tile"], C["glass"], C["lead"]
    SHUT = PLAYER_GREY if pr.pc else C["door"]
    DOOR = PLAYER_GREY if pr.pc else C["door"]
    lw = pr.lw
    ppm = pr.px_per_m
    BEAM = 0.16                                      # timber width, metres

    def beam_v(region, u, v0, v1):
        pr.rect(region, u - BEAM / 2, v0, u + BEAM / 2, v1, TIMBER, _shade(TIMBER, 0.7))

    def beam_h(region, v, u0, u1, h=BEAM):
        pr.rect(region, u0, v - h / 2, u1, v + h / 2, TIMBER, _shade(TIMBER, 0.7))

    def brace(region, a, b):
        (x0, y0), (x1, y1) = pr.P(region, *a), pr.P(region, *b)
        pr.cv.line(x0, y0, x1, y1, TIMBER, BEAM * ppm * 0.9)

    def curved(region, u0, v0, u1, v1):
        """A curved brace from the foot of one post (u0, v0) up to the next post (u1, v1)."""
        pts = [(u0 + (u1 - u0) * math.sin(t * math.pi / 2), v0 + (v1 - v0) * (1 - math.cos(t * math.pi / 2)))
               for t in [i / 6 for i in range(7)]]
        for a, b2 in zip(pts, pts[1:]):
            brace(region, a, b2)

    def window(region, u0, v0, u1, v1, shutters):
        pr.rect(region, u0 - 0.06, v0 - 0.06, u1 + 0.06, v1 + 0.06, TIMBER)
        pr.rect(region, u0, v0, u1, v1, GLASS)
        step = 0.13                                  # leaded panes
        for k in range(1, int((u1 - u0) / step) + 1):
            pr.vline(region, u0 + k * step, v0, v1, LEAD)
        for k in range(1, int((v1 - v0) / step) + 1):
            pr.hline(region, v0 + k * step, u0, u1, LEAD)
        pr.vline(region, (u0 + u1) / 2, v0, v1, TIMBER, lw)
        if shutters:
            sw = (u1 - u0) / 2
            for a in (u0 - 0.06 - sw, u1 + 0.06):
                pr.rect(region, a, v0 - 0.04, a + sw, v1 + 0.04, SHUT, _shade(SHUT, 0.65))
                pr.mark(region, a, v0 - 0.04, a + sw, v1 + 0.04)
                pr.hline(region, (v0 + v1) / 2, a, a + sw, _shade(SHUT, 0.7))
                for vv in (v0 + 0.1, v1 - 0.1):
                    pr.hline(region, vv, a + 0.04, a + sw - 0.04, _shade(SHUT, 0.7))

    def door(region, u0, v0, u1, v1):
        pr.rect(region, u0 - 0.12, v0, u1 + 0.12, v1 + 0.15, TIMBER, _shade(TIMBER, 0.7))
        pr.rect(region, u0, v0, u1, v1, DOOR, _shade(DOOR, 0.6), lw)
        pr.mark(region, u0 + 0.04, v0, u1 - 0.04, v1 - 0.04)
        u = u0 + 0.14
        while u < u1 - 0.05:
            pr.vline(region, u, v0, v1, _shade(DOOR, 0.72))
            u += 0.14
        for vv in (v0 + 0.4, v1 - 0.5):
            pr.rect(region, u0 + 0.05, vv - 0.04, u1 - 0.05, vv + 0.04, C["iron"])

    def rubble(region, color):
        """Rubble stone in rough courses."""
        r = at[region]
        pr.base(region, _shade(color, 0.72), role="stone")
        v = 0.0
        while v < r.world_h:
            hgt = float(pr.rng.uniform(0.22, 0.4))
            u = -float(pr.rng.uniform(0, 0.4))
            while u < r.world_w:
                wid = float(pr.rng.uniform(0.3, 0.7))
                t = int(pr.rng.integers(-14, 15))
                c = tuple(max(0, min(255, k + t)) for k in color)
                pr.paint_on(region, max(0.0, u + 0.025), v + 0.025, min(r.world_w, u + wid - 0.025),
                            min(r.world_h, v + hgt - 0.025), c)
                u += wid
            v += hgt

    def bricks(region):
        r = at[region]
        pr.fill(region, (186, 176, 164))
        j = 0
        v = 0.0
        while v < r.world_h:
            off = (j % 2) * 0.12
            u = -off
            while u < r.world_w:
                t = int(pr.rng.integers(-12, 12))
                pr.rect(region, max(u + 0.01, 0), v + 0.012, min(u + 0.24, r.world_w), min(v + 0.08, r.world_h),
                        tuple(max(0, min(255, c + t)) for c in BRICK))
                u += 0.25
            v += 0.09
            j += 1

    def infill(region):
        if p.infill == "BRICK":
            bricks(region)
        else:
            pr.base(region, PLASTER, role="infill")

    def framing(region, spec):
        """Posts at the corners and beside every window, rails at the floors, sills and lintels,
        braces in the panels between windows."""
        r = at[region]
        sw, sh = r.world_w, r.world_h
        sth = spec["storey_h"]
        edges = sorted({0.0, sw, *[o[0] - 0.12 for o in spec["openings"]], *[o[2] + 0.12 for o in spec["openings"]]})
        posts = []
        for u in edges:
            if not posts or u - posts[-1] > 0.45:
                posts.append(min(max(u, BEAM / 2), sw - BEAM / 2))
        filled = []
        for a, b2 in zip(posts, posts[1:]):          # an extra post in wide panels
            filled.append(a)
            if b2 - a > 1.6:
                filled.append((a + b2) / 2)
        posts = filled + [posts[-1]]
        for st in range(spec["storeys"]):
            base = st * sth
            for u in posts:
                beam_v(region, u, base, base + sth)
            beam_h(region, base + BEAM / 2, 0, sw)
            beam_h(region, base + 0.6, 0, sw, 0.12)
            beam_h(region, base + 2.1, 0, sw, 0.12)
            beam_h(region, base + sth - BEAM / 2, 0, sw)
            if p.bracing != "PLAIN":
                ops = [o for o in spec["openings"] if base <= o[1] < base + sth]
                for a, b2 in zip(posts, posts[1:]):
                    mid = (a + b2) / 2
                    if any(o[0] - 0.2 < mid < o[2] + 0.2 for o in ops):
                        continue
                    lo, hi = base + 0.6, base + 2.1
                    if p.bracing == "CROSS":
                        brace(region, (a, lo), (b2, hi))
                        brace(region, (a, hi), (b2, lo))
                    else:
                        curved(region, a, base + 0.25, b2 - 0.05, hi)

    for region, spec in model.facades.items():
        r = at[region]
        sw, sh = r.world_w, r.world_h
        if spec["ground"] and p.ground_floor == "STONE":
            rubble(region, STONE)
        elif spec["ground"] and p.ground_floor == "BRICK":
            bricks(region)
        else:
            infill(region)
            framing(region, spec)
        for (u0, v0, u1, v1) in spec["openings"]:
            if v0 == 0.0:
                door(region, u0, v0, u1, v1)
            else:
                if spec["ground"] and p.ground_floor != "TIMBER":
                    pr.rect(region, u0 - 0.12, v1, u1 + 0.12, v1 + 0.16, _shade(STONE, 1.05), _shade(STONE, 0.7))
                window(region, u0, v0, u1, v1, not spec["ground"])

    # the gables carry the framing on: posts, a collar and braces over the infill
    infill("gable")
    rg = at["gable"]
    u = 0.0
    while u <= rg.world_w + 1e-6:
        beam_v("gable", min(max(u, BEAM / 2), rg.world_w - BEAM / 2), 0, rg.world_h)
        u += 0.9
    beam_h("gable", BEAM / 2, 0, rg.world_w)
    beam_h("gable", rg.world_h * 0.45, 0, rg.world_w)
    if p.bracing != "PLAIN":
        brace("gable", (rg.world_w / 2 - 1.0, BEAM), (rg.world_w / 2, rg.world_h * 0.45))
        brace("gable", (rg.world_w / 2 + 1.0, BEAM), (rg.world_w / 2, rg.world_h * 0.45))

    def tiles(region):
        """Plain clay tiles in staggered courses, their rounded ends darker."""
        r = at[region]
        pr.base(region, _shade(TILE, 0.6), role="roof")
        v, row = 0.0, 0
        while v < r.world_h:
            u = -(row % 2) * 0.09
            while u < r.world_w:
                t = int(pr.rng.integers(-12, 13))
                c = tuple(max(0, min(255, k + t)) for k in TILE)
                pr.paint_on(region, max(0.0, u + 0.01), v, min(r.world_w, u + 0.17), min(v + 0.19, r.world_h), c)
                pr.paint_on(region, max(0.0, u + 0.01), v, min(r.world_w, u + 0.17), min(v + 0.04, r.world_h),
                            _shade(c, 0.75))
                u += 0.18
            v += 0.17
            row += 1

    tiles("roof")
    if "ridge" in at:
        tiles("ridge")
    rubble("plinth", STONE)
    bricks("brick")
    pr.base("ends", TIMBER, role="timber")
    if "soffit" in at:
        pr.base("soffit", _shade(TIMBER, 0.8), role="timber")
        rs = at["soffit"]
        u = 0.2
        while u < rs.world_w:
            pr.vline("soffit", u, 0, rs.world_h, _shade(TIMBER, 0.6), lw)
            u += 0.9
    if "reveal" in at:
        pr.fill("reveal", _shade(TIMBER, 0.85))
    if "dormer" in at:
        infill("dormer")
        rd = at["dormer"]
        window("dormer", 0.25, 0.2, rd.world_w - 0.25, rd.world_h - 0.15, False)
        for u in (BEAM / 2, rd.world_w - BEAM / 2):
            beam_v("dormer", u, 0, rd.world_h)
    if "dormer_side" in at:
        infill("dormer_side")
        rd = at["dormer_side"]
        beam_h("dormer_side", BEAM / 2, 0, rd.world_w)
        beam_v("dormer_side", BEAM / 2, 0, rd.world_h)
    if "sign" in at:
        rs = at["sign"]
        board = PLAYER_GREY if pr.pc else (150, 40, 36)
        pr.rect("sign", 0, 0, rs.world_w, rs.world_h, TIMBER)
        pr.rect("sign", 0.05, 0.05, rs.world_w - 0.05, rs.world_h - 0.05, board)
        pr.mark("sign", 0.05, 0.05, rs.world_w - 0.05, rs.world_h - 0.05)
        cx, cy = pr.P("sign", rs.world_w / 2, rs.world_h / 2)            # a jug
        pr.cv.ellipse(cx, cy, 0.11 * ppm, 0.12 * ppm, (214, 180, 90))
        pr.rect("sign", rs.world_w / 2 - 0.05, rs.world_h / 2 + 0.08, rs.world_w / 2 + 0.05,
                rs.world_h / 2 + 0.17, (214, 180, 90))


def random_params(rng, i, BuildingParams):
    """Random timber-framed options for the sweep (rng: random.Random)."""
    return BuildingParams(
        name=f"Timber{i}", style=NAME, width=rng.uniform(5, 20), depth=rng.uniform(4.5, 14),
        storeys=rng.randint(1, 3), plinth=rng.choice([0.2, 0.3, 0.5]), roof_pitch=rng.uniform(0.7, 1.6),
        bay_spacing=rng.uniform(1.6, 3.2), chimneys=rng.randint(0, 3), jetty=rng.random() < 0.7,
        jetty_depth=rng.uniform(0.2, 0.8), dormers=rng.randint(0, 5),
        ground_floor=rng.choice(["STONE", "BRICK", "TIMBER"]), infill=rng.choice(["PLASTER", "BRICK"]),
        bracing=rng.choice(["CROSS", "CURVED", "PLAIN"]), signboard=rng.random() < 0.4,
        detail=rng.choice(["LOW", "MEDIUM"]), texture_size=256, player_colour=rng.random() < 0.3,
        materials=rng.random() < 0.3)
