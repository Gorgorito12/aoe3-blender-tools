# SPDX-License-Identifier: GPL-3.0-or-later
"""The structure of each African building type, as a list of pieces (see parts.py), laid out on its
reference plan (`side` metres, centred on the origin, front at -Y). A piece with "flag": True carries
the civilization flag. What a building holds is program.py, placed by compose.py; what is here is
what makes each one itself: its levels, its timber, its silhouette, for what it is used for. Volumes
meet by the rule of core/joints.py.

The game's buildings are compounds: their walls or fence run on the edge of the obstruction, the
yard and everything in it stays inside, the roofs carry things too, and one mass holds nearly all
of the plan (measured on the stock and the mod's models). So a layout is drawn at human size on a
plan of half side P (sizes.court_half), walls on P, and the whole model is scaled up afterwards
(sizes.SCALE): doors, crates and walls grow together, as tall as the game's."""
from . import compose, sizes


def flag_point(piece, medium=True):
    k = piece["kind"]
    if k in ("hut", "granary", "tower"):
        z = piece.get("z", 0.0) + piece.get("stilts", 0.0) + piece.get("base", 0.0) + piece["wall_h"]
        if piece.get("roof", "cone" if k != "granary" else "dome") == "cone":
            z += piece["roof_h"] + (piece.get("finial", 0.0) if medium else 0.0)
        elif piece.get("roof") == "crenel":
            z += 0.6
        else:
            z += piece["roof_h"]
        return (piece["x"], piece["y"], z)
    if k == "block":
        return ((piece["x0"] + piece["x1"]) / 2, (piece["y0"] + piece["y1"]) / 2,
                piece.get("z", 0.0) + piece["h"] + piece.get("parapet", 0.0))
    if k == "field":
        return (piece["x0"] + 0.4, piece["y0"] + 0.4, 0.6)
    if k == "plot":
        return (-3.6, -3.6, 1.6)
    return (0.0, 0.0, 3.0)


def hut(x, y, r, wall_h, roof_h, **kw):
    return {"kind": "hut", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof_h": roof_h, **kw}


def block(x0, x1, y0, y1, h, **kw):
    return {"kind": "block", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "h": h, **kw}


def pot(x, y, r=0.28, h=0.5):
    return {"kind": "pot", "x": x, "y": y, "r": r, "h": h}


def prop(kind, x, y, **kw):
    return {"kind": kind, "x": x, "y": y, **kw}


def goods(x, y, n=4):
    """Baskets and sacks in a cluster."""
    out = []
    for j in range(n):
        dx, dy = (j % 3) * 0.7, (j // 3) * 0.7
        out.append(prop("basket" if j % 2 == 0 else "sack", x + dx, y + dy))
    return out


# --------------------------------------------------------------------------------------------------
# what buildings are made of

def granary(x, y, r, wall_h, roof_h, roof="dome", **kw):
    return {"kind": "granary", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof_h": roof_h, "roof": roof,
            "bands": False, **kw}


def stack(x0, x1, y0, y1, z1, region="wood", z=0.0):
    return {"kind": "stack", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z1": z1, "region": region, "z": z}


def canopy(x0, x1, y0, y1, z_hi, z_lo, cloth=True, slope="-y", rafters=0):
    return {"kind": "canopy", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z_hi": z_hi, "z_lo": z_lo,
            "cloth": cloth, "slope": slope, "rafters": rafters}


def shed(x0, x1, y0, y1, z_hi, z_lo, slope="-y", rafters=4, z=0.0, posts=(True, True), boards=True):
    """A timber roof: a lean-to on posts, or a roof of boards on top of a lower wing."""
    return {"kind": "shed", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z_hi": z_hi, "z_lo": z_lo, "slope": slope,
            "rafters": rafters, "z": z, "posts": posts, "boards": boards}


def stairs(x, y, z1, d="+x", w=0.7, run=2.8, n=7):
    return {"kind": "stairs", "x": x, "y": y, "z1": z1, "dir": d, "w": w, "run": run, "n": n}


def lookout(x, y, w, z):
    return {"kind": "lookout", "x": x, "y": y, "w": w, "z": z}


def tower(x, y, r, wall_h, roof="cone", roof_h=0.0, **kw):
    return {"kind": "tower", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof": roof, "roof_h": roof_h,
            "bands": True, **kw}


def ring_points(r, n, cx=0.0, cy=0.0, start=0.0):
    import math
    return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n))
            for i in range(n)]


def earth_wall(points, h, crenels=False):
    """A plain wall of earth between two parts of a compound."""
    return {"kind": "fence", "points": points, "h": h, "stone": True, "crenels": crenels, "material": "trim"}


def yard(**kw):
    """Where the props of this building stay (inside a wall)."""
    return {"kind": "yard", **kw}


def court(P, back, gate, h=1.5, kind="earth", width=2.0):
    """The wall of a compound from a building at y = back, round the front of the plot at P, with
    a gate of `width` centred on x = gate."""
    a = [(-P, back), (-P, -P), (gate - width / 2, -P)]
    c = [(gate + width / 2, -P), (P, -P), (P, back)]
    if kind == "earth":
        return [earth_wall(a, h), earth_wall(c, h)]
    return [{"kind": "fence", "points": a, "h": h, "type": kind}, {"kind": "fence", "points": c, "h": h, "type": kind}]


# --------------------------------------------------------------------------------------------------
# the buildings

def house(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # one round room, its small store against it
        return [hut(-0.2, 0.1, 1.6, 2.1, 2.5, overhang=0.3, finial=0.4, door=True, door_w=0.9, door_h=1.7, base=0.15,
                    big=True, flag=True)]
    # a house with a room on its roof
    return [block(-P, P, -P + 0.4, P, 2.5, door=True, parapet=0.4, merlons=1.2, beams=True, windows=0),
            block(-1.3, 0.3, -0.2, 1.3, 1.3, z=2.5, door="front", parapet=0.25, windows=0, flag=True, plain=True)]


def town_center(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # the great hut, the wives' huts, one wall round all
        out = [hut(0.0, 0.3, 2.5, 2.8, 3.6, overhang=0.4, finial=0.7, door=True, door_w=1.3, door_h=2.1,
                   base=0.25, big=True, flag=True)]
        for x, y in ((-3.3, 3.3), (3.3, 3.3)):
            out.append(hut(x, y, 1.0, 1.7, 1.7, overhang=0.2, finial=0.25, door=True, door_w=0.7, door_h=1.3, big=True))
        out += [hut(-3.3, -3.0, 0.9, 1.6, 1.6, overhang=0.2, door=True, door_w=0.7, door_h=1.2, big=True),
                hut(3.3, -3.0, 0.9, 1.6, 1.6, overhang=0.2, door=True, door_w=0.7, door_h=1.2, big=True)]
        out += court(P, 1.2, 0.0, 1.8, kind="PALISADE", width=2.2)
        out += [tower(-1.65, -P + 0.3, 0.55, 2.8, roof="cone", roof_h=1.3, overhang=0.2),   # the gate's towers
                tower(1.65, -P + 0.3, 0.55, 2.8, roof="cone", roof_h=1.3, overhang=0.2)]
        return out + [yard(x0=-P + 0.2, y0=-P + 0.2, x1=P - 0.2, y1=P)]
    # a keep with four wings, walled round, round towers at the corners
    t = {"kind": "tower", "r": 0.8, "wall_h": 3.4, "roof_h": 0.0, "roof": "crenel", "bands": True, "sahel": True}
    c = P - 0.8
    out = [{"kind": "tower", "x": 0.0, "y": 0.0, "r": 2.3, "wall_h": 5.7, "roof_h": 0.0, "roof": "crenel",
            "bands": True, "big": True, "flag": True, "sahel": True}]
    out += [block(-1.3, 1.3, -P, -1.7, 2.8, door=True, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("back",)),
            block(-1.3, 1.3, 1.7, P, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("front",)),
            block(-P, -1.7, -1.3, 1.3, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("right",)),
            block(1.7, P, -1.3, 1.3, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("left",))]
    for cx, cy in ((-c, -c), (c, -c), (-c, c), (c, c)):
        out.append({**t, "x": cx, "y": cy})
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):   # a wall from wing to wing through each corner
        out.append(earth_wall([(sx * 1.3, sy * c), (sx * c, sy * c), (sx * c, sy * 1.3)], 1.8, crenels=True))
    out += [stairs(-2.9, 3.2, 2.8, d="-y", w=0.7, run=1.8, n=7), stairs(2.9, 3.2, 2.8, d="-y", w=0.7, run=1.8, n=7)]
    return out + [yard(x0=-c, y0=-c, x1=c, y1=c)]


def granary_type(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # silos on stilts on one wooden floor
        return [{"kind": "deck", "x0": -P, "x1": P, "y0": -P, "y1": P, "z": 0.35},
                granary(-1.4, -1.1, 1.0, 1.4, 1.6, roof="cone", overhang=0.25, z=0.35, flag=True),
                granary(1.4, -1.1, 0.9, 1.3, 1.4, roof="cone", overhang=0.2, z=0.35),
                granary(0.1, 1.5, 1.1, 1.5, 1.7, roof="cone", overhang=0.25, z=0.35)]
    # domed silos on a platform with its steps, as high as a house
    return [{"kind": "plinth", "x0": -P, "x1": P, "y0": -P + 0.5, "y1": P, "h": 0.5},
            granary(-1.4, -0.7, 1.1, 2.0, 1.4, z=0.5, flag=True), granary(1.45, -0.8, 0.95, 1.8, 1.2, z=0.5),
            granary(0.0, 1.5, 1.2, 2.2, 1.5, z=0.5),
            stairs(0.0, -P - 0.1, 0.5, d="+y", w=1.4, run=0.6, n=3)]


def market(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # a store in the middle, stalls leaning on it
        return [hut(0.0, 1.0, 2.2, 2.4, 3.0, overhang=0.3, finial=0.5, door=True, door_w=1.0, door_h=1.8, base=0.2,
                    flag=True),
                canopy(-P, -2.0, -0.4, 3.2, 2.4, 2.0, cloth=False, slope="-x"),
                shed(2.0, P, -0.4, 3.2, 2.6, 2.1, slope="+x", rafters=4),
                canopy(-P, -0.9, -P, -1.0, 2.4, 1.9, cloth=True), canopy(0.9, P, -P, -1.0, 2.5, 2.0, cloth=True)]
    # the merchants' court: a hall along the back, a wing each side, stalls inside
    return [block(-P, P, 1.9, P, 3.4, door=True, parapet=0.4, merlons=0.8, beams=True, windows=2, flag=True),
            block(-1.6, 1.6, 2.5, 4.2, 1.4, z=3.4, door="front", parapet=0.25, windows=0, plain=True),
            block(-P + 0.2, -3.0, -P, 2.2, 2.6, parapet=0.3, windows=0, joined=("back",)),
            block(3.0, P - 0.2, -P, 2.2, 2.6, parapet=0.3, windows=0, joined=("back",)),
            canopy(-2.7, -0.9, -2.0, 1.7, 2.3, 1.9, cloth=True, slope="+x"),
            canopy(0.9, 2.7, -2.0, 1.7, 2.3, 1.9, cloth=True, slope="-x"),
            yard(x0=-2.8, y0=-P, x1=2.8, y1=1.7)]


def war_camp(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # a palisade on the edge, a watchtower at its corner
        return [block(-P + 0.3, 0.8, 0.9, P - 0.3, 3.0, door=True, roof="thatch", sahel=False, windows=0, flag=True),
                lookout(2.6, 2.6, 1.3, 3.8),
                {"kind": "fence", "points": [(-0.3, -P), (P, -P), (P, P), (-P, P), (-P, -P), (-2.3, -P)], "h": 2.3,
                 "type": "PALISADE"},
                yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=P - 0.3)]
    return [block(-P, 0.8, 0.8, P, 3.0, door=True, parapet=0.4, merlons=0.8, beams=True, windows=1),
            {"kind": "tower", "x": 2.6, "y": 2.6, "r": 1.2, "wall_h": 4.8, "roof_h": 0.0, "roof": "crenel",
             "bands": True, "flag": True, "sahel": True}] + court(P, 0.8, -1.6, 1.8) + [
            yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=0.8)]


def stockade(p, P, medium):
    import math
    stone = p.wall_upgrade == "STONE"
    if p.architecture == "SUBSAHARAN":
        n = 12 if medium else 8                           # segment 0 faces -Y: the entrance
        pts = ring_points(P + 0.2, n, start=-math.pi / 2 - math.pi / n)
        return [{"kind": "fence", "points": pts, "h": 2.2, "type": "PALISADE", "closed": True, "gap": 0, "stone": stone},
                hut(-1.3, 1.1, 1.3, 1.9, 2.1, overhang=0.25, finial=0.3, door=True, door_w=0.8, door_h=1.4, flag=True),
                hut(1.75, 1.3, 1.0, 1.7, 1.8, overhang=0.2, door=True, door_w=0.7, door_h=1.3),
                tower(1.9, -1.9, 0.8, 3.8, roof="cone", roof_h=1.4, overhang=0.2),     # the bottom quadrant
                yard(r=P - 0.3)]
    h = P
    return [{"kind": "fence", "points": [(-1.0, -h), (-h, -h), (-h, h), (h, h), (h, -h), (1.0, -h)], "h": 2.4,
             "type": "PALISADE", "stone": stone},
            block(-3.0, -0.3, 0.5, 3.2, 2.8, door=True, parapet=0.3, merlons=0.8, beams=True, windows=0, flag=True),
            block(0.2, 3.0, 1.0, 3.2, 2.4, door=True, parapet=0.3, windows=0),
            tower(2.4, -2.4, 0.9, 4.2, roof="crenel", sahel=True),                     # the bottom quadrant
            yard(x0=-h + 0.3, y0=-h + 0.3, x1=h - 0.3, y1=h - 0.3)]


def armory(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # the store under thatch, a smithy roofed with boards
        return [block(-P, 1.2, 0.6, P, 3.7, door=True, roof="thatch", sahel=False, windows=1, flag=True),
                shed(1.3, P, -1.0, P, 2.7, 2.1, slope="+x", rafters=4, posts=(False, True))] + \
            court(P, 0.6, -1.3, 1.5, kind="PALISADE") + [yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=P)]
    # two levels of roof, the workshop's in boards on rafters, the yard under a tarp on bare beams
    return [block(-P, 0.6, 0.0, P, 3.4, door=True, parapet=0.4, merlons=0.8, beams=True, windows=1, flag=True),
            block(-3.1, -1.1, 1.1, 3.2, 1.2, z=3.4, parapet=0.25, windows=1, plain=True),
            block(0.3, P, 1.2, 3.6, 2.5, door="front", parapet=0.3, windows=0, joined=("left",)),
            shed(0.9, 3.5, 1.4, 3.4, 3.3, 2.9, rafters=4, z=2.5),
            canopy(0.9, 3.5, -1.5, 1.0, 2.2, 1.8, cloth=True, rafters=3)] + \
        court(P, 0.0, -1.6, 1.6) + [yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=1.1)]


def depot(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # a tall barn for the engines, open at the front
        return [block(-P, P, 0.7, P, 3.9, door=True, roof="thatch", sahel=False, windows=2, flag=True),
                shed(-P, -0.4, -2.0, 0.6, 2.6, 2.1, rafters=5, posts=(False, True)),
                shed(1.4, P, -2.0, 0.6, 2.5, 2.0, rafters=4, posts=(False, True), boards=False)] + \
            court(P, 0.7, 1.2, 1.5, kind="PALISADE") + [yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=0.7)]
    return [block(-P, P, 0.7, P, 3.6, door=True, parapet=0.4, merlons=0.8, beams=True, windows=2, flag=True),
            block(-3.0, -0.6, 1.4, 3.2, 1.2, z=3.6, parapet=0.25, windows=0, plain=True),
            canopy(-P, -0.4, -2.2, 0.5, 2.6, 2.1, cloth=True, rafters=3)] + \
        court(P, 0.7, 1.2, 1.6) + [yard(x0=-P + 0.3, y0=-P + 0.3, x1=P - 0.3, y1=0.7)]


def quarry(p, P, medium):
    if p.architecture == "SUBSAHARAN":                    # the overseer's hut, awnings against it
        return [hut(0.0, 0.6, 2.0, 2.2, 2.7, overhang=0.3, finial=0.4, door=True, door_w=1.0, door_h=1.8, base=0.2,
                    flag=True),
                shed(1.9, P, -1.2, 2.8, 2.5, 2.0, slope="+x", rafters=3),
                canopy(-P, -1.9, -1.2, 2.8, 2.4, 1.9, cloth=True, slope="-x")]
    # the master mason's hall, a room on top, a striped awning each side, as in the guide
    return [block(-2.2, 2.2, -0.8, P, 3.2, door=True, parapet=0.4, merlons=0.8, beams=True, windows=1, flag=True),
            block(-1.4, 1.4, 0.9, 3.0, 1.2, z=3.2, parapet=0.25, windows=0, plain=True),
            canopy(2.4, P, -0.8, 3.4, 2.5, 1.9, cloth=True, slope="+x", rafters=3),
            canopy(-P, -2.4, -0.8, 3.4, 2.5, 1.9, cloth=True, slope="-x", rafters=3)]


def plot(p, P, medium):
    # dark worked earth and dense clumps: sorghum in the south, millet in the Sahel
    crop = "sorghum" if p.architecture == "SUBSAHARAN" else "millet"
    return [{"kind": "plot", "r": P, "crop": crop, "seed": int(p.seed), "flag": True}]


def dock(p, P, medium):
    deck = {"kind": "deck", "x0": -P, "x1": P, "y0": -P, "y1": 0.3, "z": 0.45}
    if p.architecture == "SUBSAHARAN":
        deck["y1"] = P                                    # on the water: all of it stands on the boards
        return [deck, hut(-1.5, 2.0, 1.6, 2.1, 2.5, overhang=0.3, finial=0.4, door=True, door_w=0.9, door_h=1.7, base=0.2, flag=True),
                hut(2.15, 2.2, 1.2, 1.8, 2.0, overhang=0.25, door=True, door_w=0.8, door_h=1.4, base=0.2),
                shed(0.6, P, -2.2, 0.3, 2.6, 2.2, rafters=3, z=0.45)]
    return [deck, block(-P, 0.4, 0.5, P, 4.1, door=True, parapet=0.4, merlons=0.8, beams=True, windows=1, flag=True),
            block(0.8, P, 0.9, P, 2.5, door="front", parapet=0.3, windows=0),
            shed(0.8, P, -2.2, 0.3, 2.6, 2.2, rafters=3, z=0.45)]


def customs(p, P, medium):
    two = p.storeys >= 2
    h = 5.0 if two else 3.6
    if p.architecture == "SUBSAHARAN":                    # a colonial hall under thatch, its porch of timber
        out = [block(-2.7, 2.7, -1.4, P, h, door=True, roof="thatch", sahel=False, windows=3, flag=True),
               shed(-2.7, 2.7, -3.2, -1.5, 2.7, 2.3, rafters=13, posts=(False, True)),
               shed(2.8, P, -1.4, P, 2.3, 1.9, slope="+x", rafters=6, posts=(False, True)),
               shed(-P, -2.8, -1.4, P, 2.3, 1.9, slope="-x", rafters=6, posts=(False, True))] +             court(P, -2.0, 0.0, 1.0, kind="RAILS", width=2.4)
    else:
        out = [block(-2.7, 2.7, -1.4, P, h, door=True, parapet=0.4, merlons=0.8, beams=True, windows=3, flag=True),
               canopy(-2.7, 2.7, -3.2, -1.6, 2.7, 2.3, cloth=True),
               shed(2.9, P, -1.4, P, 2.3, 1.9, slope="+x", rafters=3, posts=(False, True)),
               canopy(-P, -2.9, -1.4, P, 2.3, 1.9, cloth=True, slope="-x")]
        if not two:
            out.append(block(-2.4, 0.4, 0.2, 2.6, 1.3, z=h, parapet=0.25, windows=1, plain=True))
    if two:
        out.append({"kind": "balcony", "x0": -2.8, "x1": 2.8, "y_wall": -1.4, "z": 2.9, "depth": 0.9})
    return out


def palace(p, P, medium):
    import math
    if p.architecture == "SUBSAHARAN":                    # a hill fort: palisade, gate, royal compound
        n = 20 if medium else 12
        R = P + 0.2
        pts = ring_points(R, n, start=-math.pi / 2 - math.pi / n)
        gx = R * math.sin(math.pi / n) + 0.7
        gy = -R * math.cos(math.pi / n)
        return [{"kind": "fence", "points": pts, "h": 2.8, "type": "PALISADE", "closed": True, "gap": 0},
                tower(-gx, gy, 0.8, 4.4, roof="cone", roof_h=1.6, overhang=0.25),      # the gate's towers
                tower(gx, gy, 0.8, 4.4, roof="cone", roof_h=1.6, overhang=0.25),
                block(-2.8, 2.8, 2.0, 4.6, 3.2, door=True, roof="thatch", sahel=False, windows=2),   # the royal hall
                hut(0.0, -1.0, 2.2, 2.8, 3.6, overhang=0.4, finial=0.7, door=True, door_w=1.2, door_h=2.0,
                    base=0.25, big=True, flag=True),
                hut(-4.25, -0.8, 1.1, 1.8, 1.9, overhang=0.25, finial=0.3, door=True, door_w=0.8, door_h=1.4, big=True),
                hut(4.25, -0.8, 1.1, 1.8, 1.9, overhang=0.25, finial=0.3, door=True, door_w=0.8, door_h=1.4, big=True),
                yard(r=R - 0.4)]
    # one stepped mass: two tall towers at the back, a high hall between them, a lower storey in
    # front with terraces, a gate in a projecting bay and a balcony with an awning above it
    K = {"mass": "keep", "plain": True, "painted": True}   # windows in the texture, the triangles in the detail
    front = -4.5                                          # the lower storey's front
    bay = -5.5                                            # the gate bay's front
    tw = 3.2                                              # a tower's side
    W = P - 0.3
    Hl, Hb = 3.3, 3.7                                     # the lower storey, the gate bay
    Ht = 7.4                                              # the towers
    z = Hl * sizes.TALL
    tall = sizes.TALL
    return [block(-W, W, front, 1.2, Hl, parapet=0.45, beams=True, beam_gap=1.3, foot=True, pinnacles=True, windows=2,
                  joined=("back",), blank=("front",), shutters=True, **K),
            block(-3.0, 3.0, bay, front + 0.2, Hb, parapet=0.5, door=True, foot=True, gate=(2.0, 2.7), windows=0,
                  art={"front": "frieze"}, pinnacles=True, joined=("back",), **K),
            block(-3.2, 3.2, -1.7, 2.2, 2.9, z=Hl, parapet=0.45, beams=True, beam_gap=1.3, pinnacles=True, flag=True,
                  windows=2, shutters=True, blank=("left", "right", "back"), **K),
            block(-W, -W + tw, 1.2, W, Ht, parapet=0.5, beams=True, beam_gap=0.8, foot=True, pinnacles="stepped",
                  windows=1, sill=0.62, blank=("right", "back"), **K),
            block(W - tw, W, 1.2, W, Ht, parapet=0.5, beams=True, beam_gap=0.8, foot=True, pinnacles="stepped",
                  windows=1, sill=0.62, blank=("left", "back"), **K),
            block(-1.9, 1.9, 1.0, W - 0.2, 5.6, parapet=0.45, foot=True, windows=0, **K),
            # the balcony's walls
            block(-2.1, -1.75, -4.3, -1.5, 0.9, z=Hl, windows=0, band=False, joined=("back",), **K),
            block(1.75, 2.1, -4.3, -1.5, 0.9, z=Hl, windows=0, band=False, joined=("back",), **K),
            # the buttresses: they lean in and die into the wall at their thin top
            {"kind": "pylon", "x": -W + 0.55, "y": front, "w": 0.95, "d": 1.15, "h": Hl * 0.94, "face": "-y"},
            {"kind": "pylon", "x": W - 0.55, "y": front, "w": 0.95, "d": 1.15, "h": Hl * 0.94, "face": "-y"},
            {"kind": "pylon", "x": -2.6, "y": bay, "w": 0.85, "d": 1.1, "h": Hb * 0.94, "face": "-y"},
            {"kind": "pylon", "x": 2.6, "y": bay, "w": 0.85, "d": 1.1, "h": Hb * 0.94, "face": "-y"},
            {"kind": "pylon", "x": -W, "y": 1.85, "w": 1.05, "d": 1.3, "h": Ht * 0.7, "face": "-x"},
            {"kind": "pylon", "x": -W, "y": 4.6, "w": 1.05, "d": 1.3, "h": Ht * 0.7, "face": "-x"},
            {"kind": "pylon", "x": W, "y": 1.85, "w": 1.05, "d": 1.3, "h": Ht * 0.7, "face": "+x"},
            {"kind": "pylon", "x": W, "y": 4.6, "w": 1.05, "d": 1.3, "h": Ht * 0.7, "face": "+x"},
            {"kind": "pylon", "x": -W, "y": -3.9, "w": 0.95, "d": 1.0, "h": Hl * 0.94, "face": "-x"},
            {"kind": "pylon", "x": W, "y": -3.9, "w": 0.95, "d": 1.0, "h": Hl * 0.94, "face": "+x"},
            # the balcony over the gate: an awning, its posts on the terrace, jars
            {**canopy(-1.5, 1.5, -3.4, -1.7, 5.5, 5.0, cloth=True), "z": Hl},
            {"kind": "pot", "x": -0.4, "y": -2.3, "r": 0.34, "h": 0.8, "z": Hl, "n": 8},
            {"kind": "pot", "x": 0.35, "y": -2.5, "r": 0.26, "h": 0.6, "z": Hl, "n": 8},
            # the way up to the hall's roof, a hatch on the other terrace
            {**stairs(-3.75, -3.6, 2.9, d="+y", w=0.8, run=3.2, n=6), "z": z},
            {"kind": "hatch", "x": 4.2, "y": -2.6, "z": z + 0.001},
            # banners by the gate, spouts through the parapets, steps up to the door
            {"kind": "banner", "x": -2.05, "y": bay - 0.02, "w": 0.7, "z1": 3.05, "h": 1.75},
            {"kind": "banner", "x": 1.35, "y": bay - 0.02, "w": 0.7, "z1": 3.05, "h": 1.75},
            {"kind": "spouts", "z": (Hl + 0.15) * tall, "at": [(-3.9, front, "-y"), (3.9, front, "-y"), (-W, -1.5, "-x"), (W, -1.5, "+x")]},
            {**stairs(0.0, bay - 1.2, 0.54, d="+y", w=3.2, run=1.2, n=3), "region": "step"}]


TYPES = {"HOUSE": house, "TOWN_CENTER": town_center, "GRANARY": granary_type, "MARKET": market,
         "WAR_CAMP": war_camp, "STOCKADE": stockade, "ARMORY": armory, "DEPOT": depot, "QUARRY": quarry,
         "PLOT": plot, "DOCK": dock, "CUSTOMS": customs, "PALACE": palace}


def taller(pieces):
    """Walls and roofs at the height of the real models; doors and things keep their size."""
    k = sizes.TALL
    for q in pieces:
        for key in ("wall_h", "roof_h", "h", "z_hi", "z_lo", "z1"):
            if key in q and q["kind"] in ("hut", "granary", "tower", "block", "shed", "canopy", "stairs", "lookout"):
                q[key] *= k
        if q["kind"] in ("block", "shed", "granary", "hut", "tower", "lookout", "canopy", "pot", "pylon") and \
                q.get("z", 0.0) > 0.7:
            q["z"] *= k
        if q["kind"] == "pylon":
            q["h"] *= k
    return pieces


def structure(p, S, medium):
    """The building without its contents; S is unused: the plot is its reference's. It stands on one
    common ground, as the real models stand on their base: that is what makes it one place."""
    P = sizes.court_half(p.building_type)
    pieces = taller(TYPES.get(p.building_type, house)(p, P, medium))
    if p.building_type in ("PLOT", "DOCK", "GRANARY") or (p.building_type == "PALACE" and p.architecture == "SAHEL"):
        return pieces                                     # a field, a floor of its own, one solid mass
    return [{"kind": "ground", "half": P, "h": sizes.GROUND}] + pieces


def layout(p, S, medium):
    pieces = structure(p, S, medium)
    if not medium:                                        # the low model carries no props
        return [pc for pc in pieces if pc["kind"] != "yard"]
    return compose.compose(pieces, p, 2 * sizes.court_half(p.building_type) + 0.2)
