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
    if k == "mast":
        return piece["x"], piece["y"], piece["z"] + piece["h"]
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


def pier(fx0, fx1, fy0, fy1, tx0, tx1, ty0, ty1, h, into, climb=(1, 1)):
    return {"kind": "pier", "foot": (fx0, fx1, fy0, fy1), "top": (tx0, tx1, ty0, ty1), "h": h, "into": into, "climb": climb}


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
        # the small huts and the gate towers at 20 sides, not 16: the court has no room left for
        # props, and the class's real town centers carry over 3,083 triangles (rounder huts, +216)
        for x, y in ((-3.3, 3.3), (3.3, 3.3)):
            out.append(hut(x, y, 1.0, 1.7, 1.7, overhang=0.2, finial=0.25, door=True, door_w=0.7, door_h=1.3, big=True,
                           sides=20))
        # y -2.65, not -3.0: closer to the gate the eave of each hut comes within 0.08 m of a gate
        # tower's, which is neither apart (0.25 m) nor embedded - the rule in core/joints.py
        out += [hut(-3.3, -2.65, 0.9, 1.6, 1.6, overhang=0.2, door=True, door_w=0.7, door_h=1.2, big=True, sides=20),
                hut(3.3, -2.65, 0.9, 1.6, 1.6, overhang=0.2, door=True, door_w=0.7, door_h=1.2, big=True, sides=20)]
        out += court(P, 1.2, 0.0, 1.8, kind="PALISADE", width=2.2)
        out += [tower(-1.65, -P + 0.3, 0.55, 2.8, roof="cone", roof_h=1.3, overhang=0.2, sides=20),   # the gate's towers
                tower(1.65, -P + 0.3, 0.55, 2.8, roof="cone", roof_h=1.3, overhang=0.2, sides=20)]
        return out + [yard(x0=-P + 0.2, y0=-P + 0.2, x1=P - 0.2, y1=P)]
    # a keep with four wings, walled round, round towers at the corners
    t = {"kind": "tower", "r": 0.8, "wall_h": 3.4, "roof_h": 0.0, "roof": "crenel", "bands": True, "sahel": True}
    c = P - 0.8
    # two rows of beam ends (toron) round the keep, above the wings' merlons: the court has no room
    # left for props, and the class's real town centers carry over 3,083 triangles (+192)
    out = [{"kind": "tower", "x": 0.0, "y": 0.0, "r": 2.3, "wall_h": 5.7, "roof_h": 0.0, "roof": "crenel",
            "bands": True, "big": True, "flag": True, "sahel": True, "beams": (0.74, 0.93), "beam_n": 12}]
    out += [block(-1.3, 1.3, -P, -1.7, 2.8, door=True, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("back",)),
            block(-1.3, 1.3, 1.7, P, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("front",)),
            block(-P, -1.7, -1.3, 1.3, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("right",)),
            block(1.7, P, -1.3, 1.3, 2.8, parapet=0.4, merlons=0.8, beams=True, windows=0, joined=("left",))]
    for cx, cy in ((-c, -c), (c, -c), (-c, c), (c, c)):
        out.append({**t, "x": cx, "y": cy})
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):   # a wall from wing to wing through each corner
        out.append(earth_wall([(sx * 1.3, sy * c), (sx * c, sy * c), (sx * c, sy * 1.3)], 1.8, crenels=True))
    # x 2.8, not 2.9: at 2.9 the outer side of each flight lands in the plane of a merlon on
    # the wing's parapet (3 mm apart) and the two faces flicker against each other in game
    out += [stairs(-2.8, 3.2, 2.8, d="-y", w=0.7, run=1.8, n=7), stairs(2.8, 3.2, 2.8, d="-y", w=0.7, run=1.8, n=7)]
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
                lookout(2.6, 2.6, 1.3, 3.9),                 # 3.9: at 3.8 it stood under the class's lowest height
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
               shed(-2.7, 2.7, -3.2, -1.5, 2.7, 2.3, rafters=14, posts=(False, True)),   # 14: 13 left it under its class
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
    # measured on four views of the reference. Symmetric: the towers stand out past the wings, the
    # rear wall lies back between them, and every corner left exposed has its pier. Metres on the plan
    t = sizes.TALL
    K = {"mass": "keep", "plain": True, "painted": True}   # windows in the texture, the triangles in the detail
    W = P - 0.3                                           # half the width of the wings
    T, ti = W + 0.72, W - 2.38                            # a tower's outer and inner sides
    front, bay, hall_y, tower_y, lb, back = -3.2, -4.4, -1.5, 1.3, 4.6, 3.6
    Hw, Hg, Hb, Hh, Ht = 3.87 / t, 3.3 / t, 4.1 / t, 6.55 / t, 7.76 / t  # the tops of the walls under their parapets
    bx, ux, hx, ax = 2.93, 2.1, 3.3, 1.55                 # half the bay, its upper part, the hall, the awning
    tw, depth = T - ti, lb - tower_y
    L = tower_y - front                                   # the side walls of the wings
    piers = []
    for m in (-1, 1):                                     # the left side's piers, drawn once, and their mirror

        def corner(fx, fy0, fy1, tx, ty0, ty1, h, into, climb=(1, 1)):
            fx, tx = sorted((m * fx[0], m * fx[1])), sorted((m * tx[0], m * tx[1]))
            piers.append(pier(*fx, fy0, fy1, *tx, ty0, ty1, h, (-m * into[0], into[1]), climb))

        corner((W + 0.42, W - 0.72), front - 0.6, front + 0.6, (W, W - 0.66), front - 0.14, front + 0.5, 3.1 / t, (1, 1))
        corner((bx + 0.4, bx - 0.5), bay - 0.5, bay + 0.5, (bx + 0.02, bx - 0.5), bay - 0.14, bay + 0.1, 3.24 / t, (1, 1), (0, 1))
        corner((T + 0.85, T - 0.3), tower_y - 0.55, tower_y + 0.56, (T + 0.1, T - 0.3), tower_y - 0.12, tower_y + 0.5, 4.85 / t, (1, 1))
        corner((T + 0.85, T - 0.45), lb - 0.5, lb + 0.68, (T + 0.1, T - 0.42), lb - 0.47, lb + 0.12, 4.85 / t, (1, -1))
        corner((ti + 0.45, ti - 0.45), lb - 0.45, lb + 0.68, (ti + 0.42, ti - 0.12), lb - 0.42, lb + 0.12, 4.85 / t, (-1, -1))
    # beside the balcony the stairs climb in a recess cut into the terrace: its walls are the front of
    # each wing, kept short for that, and the side of the balcony
    D, rise, sb = 0.8, 3.87 - 3.3, bx - 0.17                # how far back it goes, how high, where its outer wall stands
    pit = (D / 2, 3.3, D, rise, "shade")
    far = hall_y + 0.1 - (bay + 0.08)                      # the length of the balcony's sides
    return [block(-W, -sb, front, front + D, Hw, parapet=0.32, foot=True, pinnacles="stepped", windows=0, joined=("back",),
                  runs_on=(("-x", "+y"),), win={"front": [(1.38, 1.6, 0.46, 0.8, False)], "right": [pit]}, **K),
            block(sb, W, front, front + D, Hw, parapet=0.32, foot=True, pinnacles="stepped", windows=0, joined=("back",),
                  runs_on=(("+x", "+y"),), win={"front": [(W - sb - 1.38, 1.6, 0.46, 0.8, False)], "left": [pit]}, **K),
            block(-W, -bx, front + D, tower_y, Hw, parapet=0.32, foot=True, windows=0, joined=("front", "back", "right"),
                  runs_on=(("-x", "-y"),), win={"left": [(L - 2.4, 1.3, 0.8, 1.3, True)]}, **K),
            block(bx, W, front + D, tower_y, Hw, parapet=0.32, foot=True, windows=0, joined=("front", "back", "left"),
                  runs_on=(("+x", "-y"),), win={"right": [(2.4 - D, 1.3, 0.8, 1.3, True)]}, **K),
            block(-ux, ux, front, tower_y, Hw, windows=0, band=False, joined=("back", "front", "left", "right"), **K),
            block(-bx, -ux, front + D, tower_y, Hw, windows=0, band=False, joined=("back", "front", "left", "right"), **K),
            block(ux, bx, front + D, tower_y, Hw, windows=0, band=False, joined=("back", "front", "left", "right"), **K),
            block(-bx, bx, bay, front, Hg, parapet=0.14, coping="coping", door=True, foot=True, gate=(1.6, 2.5),
                  windows=0, joined=("back",), band=False, **K),
            # over its shoulders the bay's middle goes on up as the balcony, back to the hall, in low walls
            block(-ux, ux, bay + 0.08, hall_y + 0.1, Hb - Hg, z=Hg, parapet=0.34, coping="coping", windows=0,
                  art={"front": "frieze"}, joined=("back",), band=False,
                  win={"right": [(far - 0.8 - (D + 0.3) / 2, 0.01, D + 0.3, rise, "shade")],
                       "left": [(0.8 + (D + 0.3) / 2, 0.01, D + 0.3, rise, "shade")]}, **K),
            block(-hx, hx, hall_y, back, Hh - Hw, z=Hw, parapet=0.34, beams=("-y", "+y"), beam_gap=0.5, pinnacles="stepped",
                  windows=0, win={"front": [(0.8, 0.12, 0.95, 1.12, True), (2 * hx - 0.8, 0.12, 0.95, 1.12, True),
                                                       (hx, 0.23, 2 * ax, 1.75, "recess")],
                                             "left": [(back + 0.45, 0.1, 1.0, 1.35, True)],
                                             "back": [(hx, 0.45, 0.42, 0.7, False)]}, **K),
            block(-T, -ti, tower_y, lb, Ht, parapet=0.34, beams=("-y", "-x", "+y"), beam_gap=0.5, foot=True,
                  pinnacles="stepped", windows=0, win={"front": [(tw / 2, 5.15, 0.42, 0.8, False)],
                                  "left": [(depth / 2, 5.45, 0.42, 0.75, False), (depth / 2, 2.1, 0.42, 0.7, False)],
                                  "back": [(tw * 0.5, 5.2, 0.42, 0.75, False), (tw * 0.5, 2.1, 0.42, 0.7, False)]}, **K),
            block(ti, T, tower_y, lb, Ht, parapet=0.34, beams=("-y", "+x", "+y"), beam_gap=0.5, foot=True,
                  pinnacles="stepped", windows=0, win={"front": [(tw / 2, 5.15, 0.42, 0.8, False)],
                                  "right": [(depth / 2, 5.45, 0.42, 0.75, False), (depth / 2, 2.1, 0.42, 0.7, False)],
                                  "back": [(tw * 0.5, 5.2, 0.42, 0.75, False), (tw * 0.5, 2.1, 0.42, 0.7, False)]}, **K),
            block(-ti - 0.2, ti + 0.2, tower_y, back, Hw, windows=0, band=False, joined=("front",), **K),
            *piers,
            # the awning over the balcony, the jars, banners by the gate, steps up to the door
            {**canopy(-ax, ax, hall_y - 1.4, hall_y - 0.02, 5.95 / t, 5.85 / t, cloth=True), "z": Hb,
             "scallops": False, "nu": 10, "nv": 6, "post": 0.06, "on_wall": True, "post_region": "frame", "curl": 0.26},
            {"kind": "pot", "x": 0.74, "y": -2.75, "r": 0.42, "h": 0.92, "z": Hb, "n": 12, "belly": True},
            {"kind": "pot", "x": 1.17, "y": -3.3, "r": 0.31, "h": 0.64, "z": Hb, "n": 12, "belly": True},
            {"kind": "banner", "x": -2.09, "y": bay - 0.02, "w": 0.54, "z1": 3.0, "h": 1.35},
            {"kind": "banner", "x": 1.55, "y": bay - 0.02, "w": 0.54, "z1": 3.0, "h": 1.35},
            {"kind": "door_frame", "x": 0.0, "y": bay, "w": 1.6, "h": 2.5},
            {**stairs(-(sb + ux) / 2, front - 0.3, rise / t, d="+y", w=sb - ux - 0.02, run=D + 0.3, n=2),
             "region": "pit_step", "top": "pit_tread", "z": 3.3},
            {"kind": "ledge", "box": (-bx - 0.03, -bx + 0.5, bay - 0.03, front - 0.3, 3.3, 3.62)},
            {"kind": "ledge", "box": (bx - 0.5, bx + 0.03, bay - 0.03, front - 0.3, 3.3, 3.62)},
            {"kind": "batter", "x": -sb, "side": 1, "d": 0.2, "y0": front, "y1": front + D, "z0": 3.3, "z1": 4.19},
            {"kind": "batter", "x": sb, "side": -1, "d": 0.2, "y0": front, "y1": front + D, "z0": 3.3, "z1": 4.19},
            {**stairs((sb + ux) / 2, front - 0.3, rise / t, d="+y", w=sb - ux - 0.02, run=D + 0.3, n=2),
             "region": "pit_step", "top": "pit_tread", "z": 3.3},
            {"kind": "mast", "x": 1.1, "y": back - 0.3, "z": 6.55, "h": 2.5, "flag": True},   # the owner's flag flies from it
            {**stairs(0.0, bay - 0.8, 0.34, d="+y", w=2.9, run=0.8, n=2), "region": "step", "top": "tread"}]


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
        if q["kind"] in ("block", "shed", "granary", "hut", "tower", "lookout", "canopy", "pot", "pier") and \
                q.get("z", 0.0) > 0.7:
            q["z"] *= k
        if q["kind"] == "pier":
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
