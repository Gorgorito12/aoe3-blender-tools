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
    return (0.0, 0.0, 3.0)


def hut(x, y, r, wall_h, roof_h, **kw):
    return {"kind": "hut", "x": x, "y": y, "r": r, "wall_h": wall_h, "roof_h": roof_h, **kw}


def block(x0, x1, y0, y1, h, **kw):
    return {"kind": "block", "x0": x0, "x1": x1, "y0": y0, "y1": y1, "h": h, **kw}


def pot(x, y, r=0.28, h=0.5):
    return {"kind": "pot", "x": x, "y": y, "r": r, "h": h}


# --------------------------------------------------------------------------------------------------

def house(p, S, medium):
    if p.architecture == "SUBSAHARAN":
        return [hut(-0.9, 0.4, 2.4, 2.3, 2.9, overhang=0.45, finial=0.5, door=True, base=0.25, flag=True),
                {"kind": "granary", "x": 2.6, "y": -1.6, "r": 0.9, "wall_h": 1.1, "roof_h": 1.2, "roof": "cone",
                 "overhang": 0.25, "stilts": 0.5, "bands": False},
                pot(-2.4, -2.7), pot(-1.8, -3.0, 0.22, 0.4)]
    return [block(-3.0, 2.6, -2.2, 2.0, 3.0, door=True, parapet=0.55, merlons=1.2, beams=True, windows=1),
            block(0.6, 2.0, 0.2, 1.6, 1.3, z=3.0, door="front", parapet=0.3, windows=0, flag=True),
            pot(-3.4, -2.6), pot(-2.8, -2.9, 0.22, 0.4)]


TYPES = {"HOUSE": house}


def layout(p, S, medium):
    fn = TYPES.get(p.building_type, house)
    return fn(p, S, medium)
