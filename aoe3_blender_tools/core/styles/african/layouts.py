# SPDX-License-Identifier: GPL-3.0-or-later
"""The composition of each African building type, as a list of pieces (see parts.py), laid out
on its reference plan (`side` metres, centred on the origin, front at -Y). A piece with
"flag": True carries the civilization flag."""


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

def house(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        return [hut(-0.9, 0.4, 2.4, 2.3, 2.9, overhang=0.45, finial=0.5, door=True, base=0.25, flag=True),
                {"kind": "granary", "x": 2.9, "y": -1.7, "r": 0.9, "wall_h": 1.1, "roof_h": 1.2, "roof": "cone",
                 "overhang": 0.25, "stilts": 0.5, "bands": False},
                pot(-2.4, -2.7), pot(-1.8, -3.0, 0.22, 0.4)]
    return [block(-3.0, 2.6, -2.2, 2.0, 3.0, door=True, parapet=0.55, merlons=0.6, beams=True, windows=1),
            block(0.6, 2.0, 0.2, 1.6, 1.3, z=3.0, door="front", parapet=0.3, windows=0, flag=True),
            pot(-3.4, -2.6)]


def granary(x, y, r, wall_h, roof_h, roof="dome", **kw):
    return {"kind": "granary", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof_h": roof_h, "roof": roof,
            "bands": False, **kw}


def stack(x0, x1, y0, y1, z1, region="wood", z=0.0):
    return {"kind": "stack", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z1": z1, "region": region, "z": z}


def canopy(x0, x1, y0, y1, z_hi, z_lo, cloth=True, slope="-y"):
    return {"kind": "canopy", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z_hi": z_hi, "z_lo": z_lo,
            "cloth": cloth, "slope": slope}


def town_center(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        out = [hut(0.0, 0.6, 4.0, 3.2, 4.6, overhang=0.6, finial=0.8, door=True, door_w=1.6, door_h=2.3,
                   base=0.35, big=True, flag=True)]
        for x, y in ((-5.1, 5.6), (5.1, 5.6), (-6.3, -2.9), (6.3, -2.9)):
            out.append(hut(x, y, 1.8, 2.0, 2.2, overhang=0.35, finial=0.3, door=True, door_w=0.9, door_h=1.6,
                           base=0.2))
        out += [hut(-6.6, 1.4, 1.4, 1.8, 1.9, overhang=0.3, finial=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
                hut(6.6, 1.4, 1.4, 1.8, 1.9, overhang=0.3, finial=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
                granary(-1.5, 6.9, 0.9, 1.1, 1.2, roof="cone", overhang=0.25, stilts=0.5),
                granary(1.5, 6.9, 0.9, 1.1, 1.2, roof="cone", overhang=0.25, stilts=0.5),
                {"kind": "fence", "points": [(-7.6, -5.6), (-3.0, -5.6)], "h": 1.3, "stone": True, "crenels": False},
                {"kind": "fence", "points": [(3.0, -5.6), (7.6, -5.6)], "h": 1.3, "stone": True, "crenels": False},
                prop("fire", 0.0, -4.4), prop("drum", -1.2, -5.0), prop("drum", 1.2, -5.0, r=0.22, h=0.55),
                prop("rack", -4.4, -4.6), prop("rack", 4.4, -4.6)]
        out += [pot(-2.6, -4.6), pot(-2.0, -4.9, 0.22, 0.4), pot(2.4, -4.7, 0.3, 0.55)]
        out += goods(-2.2, -7.0, 3) + goods(0.8, -7.0, 3)          # at the entrance, outside the wall
        return out
    out = [{"kind": "tower", "x": 0.0, "y": 0.0, "r": 3.6, "wall_h": 6.6, "roof_h": 0.0, "roof": "crenel",
            "bands": True, "big": True, "flag": True}]
    out += [block(-2.2, 2.2, -7.6, -2.6, 3.6, door=True, parapet=0.5, merlons=1.0, beams=True, windows=1,
                  joined=("back",)),
            block(-2.2, 2.2, 2.6, 7.4, 3.6, parapet=0.5, merlons=1.0, beams=True, windows=1, joined=("front",)),
            block(-7.6, -2.6, -2.2, 2.2, 3.6, parapet=0.5, merlons=1.0, beams=True, windows=1, joined=("right",)),
            block(2.6, 7.6, -2.2, 2.2, 3.6, parapet=0.5, merlons=1.0, beams=True, windows=1, joined=("left",))]
    for cx, cy in ((-6.4, -6.4), (6.4, -6.4), (-6.4, 6.4), (6.4, 6.4)):
        out.append({"kind": "tower", "x": cx, "y": cy, "r": 1.0, "wall_h": 4.4, "roof_h": 0.0, "roof": "crenel",
                    "bands": True})
    out += [pot(-3.4, -7.9), pot(3.4, -7.9, 0.3, 0.55), prop("well", -4.6, -4.4),
            prop("rack", 4.2, -4.0), prop("logs", 4.6, 4.6, length=1.8, n=3)]
    out += goods(-5.6, 3.4, 3) + goods(3.4, -5.0, 3)
    return out


def granary_type(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        out = [granary(-2.6, -1.4, 1.4, 1.6, 1.8, roof="cone", overhang=0.35, stilts=0.7, flag=True),
               granary(1.0, -2.6, 1.2, 1.4, 1.6, roof="cone", overhang=0.3, stilts=0.7),
               granary(0.4, 1.9, 1.5, 1.7, 1.9, roof="cone", overhang=0.35, stilts=0.7),
               stack(-4.6, -3.8, 0.8, 2.0, 0.6), stack(3.0, 4.4, 0.4, 1.6, 0.5), pot(2.8, -4.4)]
        return out
    return [{"kind": "plinth", "x0": -4.4, "x1": 3.6, "y0": -3.4, "y1": 3.0, "h": 0.5},
            granary(-2.4, -1.2, 1.4, 2.2, 1.6, z=0.5, flag=True), granary(0.8, -1.4, 1.3, 2.0, 1.5, z=0.5),
            granary(-0.8, 1.6, 1.3, 2.0, 1.5, z=0.5),
            block(1.8, 4.6, 0.6, 3.4, 2.4, door="left", parapet=0.3, windows=0),
            pot(-4.8, -3.6), stack(-4.8, -4.2, 0.8, 2.0, 1.4)]


def market(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        out = [hut(-4.6, 3.4, 2.6, 2.5, 3.0, overhang=0.45, finial=0.5, door=True, base=0.25, flag=True),
               canopy(-1.4, 2.6, -1.0, 2.0, 2.6, 2.1, cloth=False),
               canopy(3.4, 7.4, -1.0, 2.0, 2.6, 2.1, cloth=False),
               canopy(-1.4, 2.6, -6.6, -3.6, 2.6, 2.1, cloth=True),
               canopy(3.4, 7.4, -6.6, -3.6, 2.6, 2.1, cloth=True)]
        out += [stack(-0.8, 0.6, -0.2, 0.8, 0.7, "cloth"), stack(4.2, 5.4, 0.0, 1.0, 0.6),
                stack(0.0, 1.4, -5.8, -4.8, 0.7, "cloth"), pot(5.0, -5.0), pot(6.0, -5.2, 0.24, 0.45),
                pot(-5.6, -1.6), pot(-4.9, -2.0, 0.22, 0.4)]
        out += [hut(-5.2, -3.8, 1.8, 2.1, 2.3, overhang=0.4, finial=0.4, door=True, door_w=0.9, door_h=1.6, base=0.2),
                prop("well", -1.6, -1.6)]
        out += goods(-1.0, 0.3, 3) + goods(4.0, 0.3, 3) + goods(-0.9, -5.4, 3) + goods(4.0, -5.4, 3) + goods(1.0, 3.8, 5)
        return out
    out = [block(-7.6, -1.2, 1.0, 7.0, 4.2, door=True, parapet=0.55, merlons=1.0, beams=True, windows=1, flag=True),
           canopy(0.4, 4.4, 2.0, 5.6, 2.8, 2.3, cloth=True), canopy(4.8, 8.4, 2.0, 5.6, 2.8, 2.3, cloth=True),
           canopy(0.4, 4.4, -6.0, -2.4, 2.8, 2.3, cloth=True), canopy(4.8, 8.4, -6.0, -2.4, 2.8, 2.3, cloth=True),
           canopy(-7.2, -3.2, -6.0, -2.4, 2.8, 2.3, cloth=True)]
    out += [stack(1.2, 2.6, 2.8, 3.8, 0.7, "cloth"), stack(5.6, 7.0, -5.2, -4.2, 0.6),
            pot(-5.0, -0.6), pot(-4.3, -0.9, 0.22, 0.4), stack(-6.4, -5.0, -5.2, -4.0, 0.6, "cloth")]
    out += [block(-7.4, -4.4, -1.6, 0.6, 2.6, door="right", parapet=0.3, windows=0), prop("well", 2.6, -0.6)]
    out += goods(1.0, 2.4, 3) + goods(5.4, 2.4, 3) + goods(1.0, -5.4, 3) + goods(5.4, -5.4, 3) + goods(-6.6, -5.4, 3)
    out += goods(-3.6, -1.0, 4) + [prop("logs", 7.0, 0.4, length=1.8, n=3, along="y")]
    return out


def war_camp(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        out = [block(-5.6, 0.4, 0.6, 5.0, 2.6, door=True, roof="thatch", sahel=False, windows=0, flag=True),
               block(1.6, 6.4, -1.6, 2.8, 2.6, door="left", roof="thatch", sahel=False, windows=0),
               hut(-3.4, -4.2, 1.6, 2.0, 2.2, overhang=0.35, door=True, door_w=0.9, door_h=1.6, base=0.2),
               {"kind": "fence", "points": [(-6.8, -1.4), (-6.8, 6.4), (6.6, 6.4)], "h": 2.2, "type": "PALISADE"},
               stack(2.0, 4.4, -4.6, -4.3, 1.6), pot(0.6, -4.0, 0.5, 0.6)]
        out += [hut(4.6, -4.4, 1.5, 1.9, 2.0, overhang=0.35, door=True, door_w=0.8, door_h=1.5, base=0.2),
                prop("rack", 3.2, -2.6), prop("rack", -1.2, -2.0), prop("fire", 0.2, -1.6),
                prop("drum", -0.4, -4.6), prop("drum", 0.4, -4.9, r=0.22, h=0.55), prop("drum", 1.2, -4.6)]
        return out
    out = [block(-6.2, 1.8, 0.8, 6.0, 3.6, door=True, parapet=0.55, merlons=1.0, beams=True, windows=1),
           {"kind": "tower", "x": 4.6, "y": 3.8, "r": 1.8, "wall_h": 5.4, "roof_h": 0.0, "roof": "crenel",
            "bands": True, "flag": True},
           block(2.4, 6.6, -3.6, 0.4, 3.0, door="left", parapet=0.4, windows=0),
           {"kind": "fence", "points": [(-6.8, -5.6), (6.8, -5.6)], "h": 1.6, "stone": True},
           stack(-3.6, -1.2, -2.6, -2.3, 1.6), pot(-5.0, -2.0, 0.5, 0.6)]
    out += [prop("rack", -2.4, -3.6), prop("rack", 0.4, -3.6), prop("fire", 0.6, -1.2),
            prop("drum", -5.6, -3.6), prop("drum", -4.9, -4.0, r=0.22, h=0.55)]
    return out


def tower(x, y, r, wall_h, roof="cone", roof_h=0.0, **kw):
    return {"kind": "tower", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof": roof, "roof_h": roof_h,
            "bands": True, **kw}


def ring_points(r, n, cx=0.0, cy=0.0, start=0.0):
    import math
    return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n))
            for i in range(n)]


def stockade(p, S, medium):
    import math
    stone = p.wall_upgrade == "STONE"
    if stone:
        p = p    # the upgraded stockade: the same layout, the fence in stone
    if p.architecture == "SUBSAHARAN":
        # a ring of 12 sides whose segment 0 faces -Y: the entrance
        n = 12 if medium else 8
        pts = ring_points(5.6, n, start=-math.pi / 2 - math.pi / n)
        out = [{"kind": "fence", "points": pts, "h": 2.4, "type": "PALISADE", "closed": True, "gap": 0,
                "stone": stone},
               hut(-2.0, 1.6, 1.9, 2.1, 2.4, overhang=0.35, finial=0.4, door=True, door_w=0.9, door_h=1.6, base=0.2,
                   flag=True),
               hut(2.4, 1.8, 1.5, 1.9, 2.0, overhang=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
               tower(2.6, -3.0, 1.2, 4.6, roof="cone", roof_h=1.6, overhang=0.3),      # the bottom quadrant
               pot(-2.4, -1.4), pot(-1.8, -1.8, 0.22, 0.4)]
        if stone:
            out += [granary(-2.8, -2.0, 0.9, 1.1, 1.2, roof="cone", overhang=0.25, stilts=0.5),
                    prop("rack", 0.4, -1.0), prop("drum", 0.6, 0.6)] + goods(-0.6, 3.8, 3)
        return out
    h = 5.6
    pts = [(-h, -h), (h, -h), (h, h), (-h, h)]
    out = [{"kind": "fence", "points": [(-1.4, -h), (-h, -h), (-h, h), (h, h), (h, -h), (1.4, -h)], "h": 2.6,
            "type": "PALISADE", "stone": stone},
           block(-4.6, -0.6, 0.8, 4.6, 3.0, door=True, parapet=0.4, merlons=1.0, beams=True, windows=0, flag=True),
           block(0.6, 4.6, 1.6, 4.6, 2.6, door=True, parapet=0.35, windows=0),
           tower(3.6, -3.6, 1.3, 5.2, roof="crenel"),                                 # the bottom quadrant
           pot(-3.4, -3.0), stack(-1.0, 0.4, -2.0, -1.4, 0.6)]
    if stone:
        out += [granary(-3.6, -2.6, 1.0, 1.6, 1.2), prop("well", 0.4, -3.2), prop("rack", 1.2, 0.6)] + goods(-4.6, -0.4, 3)
    return out


def armory(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        return [block(-5.4, 1.0, 0.2, 5.0, 3.0, door=True, roof="thatch", sahel=False, windows=1, flag=True),
                canopy(1.6, 5.8, -0.6, 3.4, 2.7, 2.2, cloth=False, slope="+x"),
                stack(2.6, 3.6, 0.4, 1.4, 1.1, "stone"),                     # the forge
                stack(4.2, 5.0, 2.2, 2.6, 1.6), pot(-3.0, -1.6, 0.4, 0.6),
                hut(3.4, -3.6, 1.4, 1.8, 1.9, overhang=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
                hut(-3.4, -3.6, 1.7, 2.0, 2.2, overhang=0.4, finial=0.3, door=True, door_w=0.9, door_h=1.6, base=0.2),
                prop("rack", 0.6, -1.4), prop("rack", 0.6, -2.8), prop("fire", 3.1, 0.9),
                prop("logs", 4.6, 4.4, length=1.8, n=4), prop("stones", -0.6, -4.8, n=4),
                prop("drum", -5.4, -1.0), prop("rack", -1.8, -1.4)]
    return [block(-5.6, 1.2, 0.0, 5.4, 4.0, door=True, parapet=0.5, merlons=1.0, beams=True, windows=1, flag=True),
            block(0.8, 5.6, 1.4, 5.2, 2.8, door="front", parapet=0.35, windows=1, joined=("left",)),
            canopy(1.6, 5.6, -2.8, 1.0, 2.6, 2.1, cloth=True),
            stack(-4.2, -3.4, 2.0, 2.8, 5.6, "stone", z=0.0),                       # the forge's chimney
            stack(2.4, 3.4, -2.0, -1.0, 1.0, "stone"), pot(-4.6, -1.2, 0.4, 0.6),
            prop("rack", -2.0, -1.8), prop("rack", -0.2, -1.8), prop("fire", 4.2, -1.6),
            prop("logs", 4.4, -3.8, length=1.8, n=4), prop("stones", -4.0, -3.6, n=5)]


def depot(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        return [canopy(-5.6, 1.6, -1.4, 4.4, 3.6, 3.0, cloth=False, slope="-y"),       # the open workshop
                hut(4.0, 2.6, 1.8, 2.1, 2.3, overhang=0.35, finial=0.4, door=True, door_w=0.9, door_h=1.6,
                    base=0.2, flag=True),
                stack(-4.4, -1.0, 0.0, 0.5, 0.5), stack(-4.4, -1.0, 0.8, 1.3, 0.5), stack(-3.8, -1.6, 0.2, 1.1, 0.9),
                stack(2.4, 5.8, -3.8, -3.3, 0.45), stack(2.4, 5.8, -3.0, -2.5, 0.45), pot(-5.0, -3.4),
                prop("frame", -2.0, 1.6, w=3.0, d=1.6, h=2.2), prop("logs", -2.4, -3.4, length=2.6, n=5),
                prop("logs", 4.1, -0.6, length=2.4, n=4, along="y"),
                hut(4.4, -1.0 - 3.6, 1.3, 1.7, 1.8, overhang=0.3, door=True, door_w=0.8, door_h=1.4, base=0.2),
                prop("frame", -2.6, -1.4, w=2.4, d=1.4, h=1.8), prop("stones", 0.6, -4.6, n=4)]
    return [block(-5.6, 0.6, 0.6, 5.6, 3.6, door=True, parapet=0.5, merlons=1.0, beams=True, windows=1, flag=True),
            canopy(1.2, 5.8, -0.4, 4.6, 3.0, 2.5, cloth=True, slope="+x"),
            stack(2.0, 5.0, 0.6, 1.1, 0.5), stack(2.0, 5.0, 1.4, 1.9, 0.5), stack(2.6, 4.4, 2.6, 3.6, 0.9),
            stack(-4.4, -1.6, -3.4, -2.9, 0.45), pot(3.6, -2.8, 0.4, 0.6),
            prop("frame", 3.4, 1.6, w=3.0, d=1.6, h=2.2), prop("logs", -2.6, -4.4, length=2.6, n=5),
            prop("logs", 5.0, -2.4, length=2.0, n=4, along="y"),
            prop("frame", -1.4, -1.6, w=2.4, d=1.4, h=1.8), prop("stones", 1.0, -4.6, n=4), prop("rack", -4.8, -1.4)]


def quarry(p, S, medium):
    piles = [stack(-5.0, -3.4, -4.4, -3.2, 0.9, "stone"), stack(-3.0, -1.8, -4.6, -3.6, 0.6, "stone"),
             stack(2.6, 4.4, -4.6, -3.0, 1.1, "stone"), stack(4.6, 5.6, -2.4, -1.4, 0.7, "stone"),
             stack(-5.4, -4.2, -2.4, -1.4, 0.5, "stone"),
             prop("stones", -0.6, -4.2, n=9), prop("stones", 1.6, -2.0, n=6), prop("stones", -3.6, -0.6, n=6),
             prop("crane", 1.0, -0.2, h=4.2), prop("logs", 4.6, 0.0, length=1.6, n=3, along="y")]
    piles += [prop("stones", 3.6, 2.4, n=6), prop("stones", -1.6, -2.4, n=6),
              prop("crane", -3.6, -5.2, h=3.6), prop("stones", 5.2, -5.0, n=6)]
    if p.architecture == "SUBSAHARAN":
        piles = piles + [prop("stones", -0.2, 4.6, n=3)]
        return [hut(-2.8, 2.4, 2.0, 2.2, 2.5, overhang=0.4, finial=0.4, door=True, base=0.2, flag=True),
                hut(-5.0, -1.8, 1.3, 1.7, 1.8, overhang=0.4, door=True, door_w=0.8, door_h=1.4, base=0.2),
                canopy(0.8, 5.4, 0.6, 4.4, 2.8, 2.3, cloth=False, slope="+x")] + piles
    return [block(-5.4, -0.4, 0.6, 5.0, 3.2, door=True, parapet=0.45, merlons=1.0, beams=True, windows=1, flag=True),
            canopy(0.6, 5.4, 0.8, 4.8, 2.8, 2.3, cloth=True, slope="+x"),
            block(-7.0, -5.1, 2.0, 4.6, 2.2, door="front", parapet=0.3, windows=0, joined=("right",))] + piles


def plot(p, S, medium):
    h = 4.0
    fence = {"kind": "fence", "points": [(-1.0, -h - 0.2), (-h - 0.2, -h - 0.2), (-h - 0.2, h + 0.2),
                                         (h + 0.2, h + 0.2), (h + 0.2, -h - 0.2), (1.0, -h - 0.2)],
             "h": 1.0, "type": "RAILS", "stone": p.architecture == "SAHEL", "crenels": False}
    if p.architecture == "SAHEL":
        fence["h"] = 0.7
    fence["medium_only"] = True
    return [{"kind": "field", "x0": -h, "x1": h, "y0": -h, "y1": h, "rows": 7, "plants": 8, "flag": True}, fence]


def dock(p, S, medium):
    deck = {"kind": "deck", "x0": -6.0, "x1": 6.0, "y0": -6.2, "y1": 0.4, "z": 0.6}
    dz = deck["z"]
    cargo = [prop("logs", -4.0, -4.6, length=2.0, n=3), prop("rack", 0.0, -5.6, w=2.4), prop("drum", -2.4, -3.6)]
    cargo += goods(2.6, -5.6, 5) + (goods(-4.6, -2.4, 3) if p.architecture == "SUBSAHARAN" else [])
    out = [deck] + [dict(pc, z=dz) for pc in cargo] + [dict(pot(-1.4, -3.4, 0.3, 0.55), z=dz),
                                                        dict(pot(-0.7, -3.2, 0.22, 0.4), z=dz)]
    if p.architecture == "SUBSAHARAN":
        out += [hut(-2.6, 3.0, 2.4, 2.4, 2.8, overhang=0.5, finial=0.5, door=True, base=0.25, flag=True),
                hut(3.4, 3.2, 1.8, 2.1, 2.3, overhang=0.4, door=True, door_w=0.9, door_h=1.6, base=0.2),
                canopy(1.4, 5.6, -3.4, -0.6, 3.0, 2.6, cloth=False)]
        return out
    out += [block(-5.6, 0.8, 1.0, 6.0, 4.0, door=True, parapet=0.5, merlons=1.0, beams=True, windows=1, flag=True),
            block(1.6, 5.6, 1.6, 5.4, 3.0, door=True, parapet=0.4, windows=1),
            prop("crane", 3.6, -1.6, h=4.6)]
    return out


def customs(p, S, medium):
    two = p.storeys >= 2
    h = 6.2 if two else 3.4
    out = []
    if p.architecture == "SUBSAHARAN":
        out.append(block(-4.6, 4.6, -2.6, 3.6, h, door=True, roof="thatch", sahel=False, windows=3, flag=True))
        out.append(canopy(-4.6, 4.6, -4.6, -2.6, 3.0, 2.5, cloth=False))
        out += [hut(-5.4, 5.4, 1.4, 1.9, 2.0, overhang=0.3, finial=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
                hut(5.4, 5.4, 1.4, 1.9, 2.0, overhang=0.3, finial=0.3, door=True, door_w=0.8, door_h=1.5, base=0.2),
                granary(6.0, 0.6, 0.9, 1.3, 1.4, roof="cone", overhang=0.25, stilts=0.6),
                granary(-6.0, 0.6, 0.9, 1.3, 1.4, roof="cone", overhang=0.25, stilts=0.6),
                {"kind": "fence", "points": [(-7.0, -6.6), (-7.0, -1.6)], "h": 1.0, "type": "RAILS",
                 "closed": False, "medium_only": True},
                {"kind": "fence", "points": [(7.0, -6.6), (7.0, -1.6)], "h": 1.0, "type": "RAILS",
                 "closed": False, "medium_only": True},
                prop("rack", 5.6, -3.6, w=1.4), prop("drum", -5.6, -3.4)]
    else:
        out.append(block(-4.6, 4.6, -2.6, 3.6, h, door=True, parapet=0.55, merlons=1.0, beams=True, windows=3,
                         flag=True))
        out.append(canopy(-4.6, 4.6, -4.6, -2.6, 3.0, 2.5, cloth=True))
        out += [block(-7.0, -5.0, 0.6, 4.6, 2.6, door="right", parapet=0.3, windows=0),
                granary(6.0, 1.6, 1.1, 1.8, 1.3), prop("rack", 6.0, -3.0, w=1.4)] + goods(-6.6, -3.0, 3)
    if two:
        out.append({"kind": "balcony", "x0": -3.6, "x1": 3.6, "y_wall": -2.6, "z": 3.4, "depth": 1.1})
        for pc in out:
            if pc["kind"] == "canopy":
                pc["z_hi"], pc["z_lo"] = 3.1, 2.7
    out += [pot(-5.4, -5.2), pot(-4.8, -5.4, 0.22, 0.4), prop("logs", 5.4, 0.6, length=1.8, n=3, along="y")]
    out += goods(2.4, -5.6, 3)
    return out


def palace(p, S, medium):
    import math
    if p.architecture == "SUBSAHARAN":
        n = 20 if medium else 12
        pts = ring_points(10.0, n, start=-math.pi / 2 - math.pi / n)
        out = [{"kind": "fence", "points": pts, "h": 3.2, "type": "PALISADE", "closed": True, "gap": 0}]
        gx = 10.0 * math.sin(math.pi / n) + 0.9
        gy = -10.0 * math.cos(math.pi / n)
        out += [tower(-gx, gy, 1.2, 5.4, roof="cone", roof_h=2.0, overhang=0.35),          # the gate's towers
                tower(gx, gy, 1.2, 5.4, roof="cone", roof_h=2.0, overhang=0.35),
                block(-4.6, 4.6, 2.8, 8.0, 4.2, door=True, roof="thatch", sahel=False, windows=2),   # the royal hall
                hut(0.0, -1.6, 3.4, 3.4, 4.6, overhang=0.6, finial=0.9, door=True, door_w=1.6, door_h=2.3,
                    base=0.35, big=True, flag=True),
                hut(-6.9, -1.8, 1.9, 2.2, 2.4, overhang=0.4, finial=0.4, door=True, door_w=0.9, door_h=1.6, base=0.2),
                hut(6.9, -1.8, 1.9, 2.2, 2.4, overhang=0.4, finial=0.4, door=True, door_w=0.9, door_h=1.6, base=0.2),
                granary(-6.6, 3.2, 1.2, 1.4, 1.6, roof="cone", overhang=0.3, stilts=0.7),
                granary(6.6, 3.2, 1.2, 1.4, 1.6, roof="cone", overhang=0.3, stilts=0.7),
                prop("fire", 0.0, -6.0), prop("rack", -3.4, -6.4), prop("rack", 3.4, -6.4),
                prop("drum", -1.6, -6.6), prop("drum", 1.6, -6.6)]
        return out
    w, t, hw = 9.6, 1.4, 5.0                              # half size, wall thickness, wall height
    e = 1.7                                               # the walls' ends, apart, inside the corner towers
    out = [block(-w + e, -2.4, -w, -w + t, hw, parapet=0.6, merlons=0.8, windows=0),        # front, left of the gate
           block(2.4, w - e, -w, -w + t, hw, parapet=0.6, merlons=0.8, windows=0),
           block(-w + e, w - e, w - t, w, hw, parapet=0.6, merlons=0.8, windows=0),         # back
           block(-w, -w + t, -w + e, w - e, hw, parapet=0.6, merlons=0.8, windows=0),       # sides
           block(w - t, w, -w + e, w - e, hw, parapet=0.6, merlons=0.8, windows=0)]
    for cx in (-w, w):                                    # corner towers
        for cy in (-w, w):
            out.append(block(cx - 1.8, cx + 1.8, cy - 1.8, cy + 1.8, 7.4, parapet=0.6, merlons=0.8, windows=1))
    out += [block(-3.2, -1.8, -w - 0.8, -w + t + 0.8, 6.6, parapet=0.5, merlons=0.7, windows=0),   # the gate's towers
            block(1.8, 3.2, -w - 0.8, -w + t + 0.8, 6.6, parapet=0.5, merlons=0.7, windows=0),
            block(-4.2, 4.2, 0.6, 6.6, 6.4, door=True, parapet=0.6, merlons=1.0, beams=True, windows=2, flag=True),
            granary(-5.0, -3.2, 1.4, 2.2, 1.6), granary(5.0, -3.2, 1.4, 2.2, 1.6),
            prop("well", 0.0, -3.4), pot(-2.6, -5.6)]
    out += goods(-6.0, 1.0, 4) + goods(4.8, 1.0, 4)
    return out


TYPES = {"HOUSE": house, "TOWN_CENTER": town_center, "GRANARY": granary_type, "MARKET": market,
         "WAR_CAMP": war_camp, "STOCKADE": stockade, "ARMORY": armory, "DEPOT": depot, "QUARRY": quarry,
         "PLOT": plot, "DOCK": dock, "CUSTOMS": customs, "PALACE": palace}


def layout(p, S, medium):
    fn = TYPES.get(p.building_type, house)
    return fn(p, S, medium)
