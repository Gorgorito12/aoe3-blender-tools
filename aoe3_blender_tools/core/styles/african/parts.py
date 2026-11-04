# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces African buildings are composed of, as plain dicts (a layout), and the code that
declares their regions and builds them with the kit. A layout lists pieces in metres:

    {"kind": "hut", "x": 0, "y": 0, "r": 2.5, "wall_h": 2.3, "roof_h": 3.0, "door": True}
    {"kind": "block", "x0": -3, "x1": 3, "y0": -2, "y1": 2, "h": 3, "door": True, "parapet": 0.5}
    {"kind": "granary", ...}, {"kind": "pot", ...}, {"kind": "fence", ...}, {"kind": "tower", ...},
    {"kind": "canopy", ...}, {"kind": "stack", ...}, {"kind": "deck", ...}, {"kind": "field", ...}

Each round wall and each block wall gets its own region (its door is painted where the geometry
has it); thatch, domes, roofs, wood, cloth and stone share one region each, sized for the
largest piece. Layouts face -Y like every style (the front, with the door, is at -Y)."""
import math

from ... import joints
from ...kit import cone_roof_size, dome_size, ring_size

DOOR_ANGLE = 1.5 * math.pi          # the round walls' doors face -Y
SIDE_OF = {"front": "-y", "back": "+y", "left": "-x", "right": "+x"}


def sides(medium, big=False):
    if big:
        return 32 if medium else 10
    return 24 if medium else 8


def door_u(r, n):
    """u of the door on a round wall of radius r and n sides (ring starts at angle 0)."""
    girth = 2 * r * math.sin(math.pi / n) * n
    return girth * DOOR_ANGLE / (2 * math.pi)


# --------------------------------------------------------------------------------------------------
# regions

def declare(b, layout, medium):
    """Declares every region the layout needs, in a fixed order. Returns the facades (round and
    block walls with their openings) for the painter and the damaged texture."""
    need = {}
    facades = {}

    def want(name, w, h):
        if name in need:
            need[name] = (max(need[name][0], w), max(need[name][1], h))
        else:
            need[name] = (w, h)

    for i, piece in enumerate(layout):
        k = piece["kind"]
        piece["id"] = i
        if k in ("hut", "granary", "tower"):
            n = sides(medium, piece.get("big", False))
            if medium and piece["r"] < 1.6:
                n = 16
            piece["n"] = n
            wall = f"rw{i}"
            piece["wall_region"] = wall
            want(wall, *ring_size(piece["r"], piece["wall_h"], n))
            if piece.get("base"):
                want("plinth", *ring_size(piece["r"] + 0.15, piece["base"], n))
            roof = piece.get("roof", "cone" if k != "granary" else "dome")
            if roof == "cone":
                want("thatch", *cone_roof_size(piece["r"], piece["roof_h"], n, piece.get("overhang", 0.4)))
            elif roof == "dome":
                want("dome", *dome_size(piece["r"], piece["roof_h"], n))
            elif roof == "crenel":
                want("roof_flat", 2 * piece["r"] + 0.2, 2 * piece["r"] + 0.2)
            want("wood", 2.0, 3.0)
            du = door_u(piece["r"], n) if piece.get("door") else None
            facades[wall] = {"kind": "round", "bays": [du] if du is not None else [], "door": du,
                             "storeys": 1, "door_w": piece.get("door_w", 1.0), "door_h": piece.get("door_h", 1.9),
                             "tops": [piece.get("door_h", 1.9)], "bands": piece.get("bands", True)}
        elif k == "block":
            w, d, h = piece["x1"] - piece["x0"], piece["y1"] - piece["y0"], piece["h"]
            for face, length in (("front", w), ("back", w), ("left", d), ("right", d)):
                if face in piece.get("joined", ()):                # ends inside its neighbour: no wall
                    continue
                name = f"bk{i}_{face}"
                want(name, length, h)
                door = piece.get("door") is True and face == "front" or piece.get("door") == face
                win = piece.get("windows", 1)
                bays = _bays(length, win, door)
                facades[name] = {"kind": "block", "bays": bays, "door": length / 2 if door else None, "storeys": 1,
                                 "tops": [2.1], "h": h, "sahel": piece.get("sahel", True),
                                 "openings": _block_openings(bays, length / 2 if door else None, h)}
            want("roof_flat", max(w, d) + 0.2, min(w, d) + 0.2)
            want("trim", 2.0, h + 1.2)
            if piece.get("parapet"):
                want("parapet", max(w, d) + 0.4, piece["parapet"] + 0.4)
            if piece.get("roof") == "thatch":
                want("thatch", max(w, d) + 1.2, math.hypot(min(w, d) / 2 + 0.5, (min(w, d) / 2 + 0.5) * 0.8) + 0.3)
            want("wood", 2.0, 3.0)
            if medium:
                want("reveal", 1.2, 2.4)
        elif k == "pot":
            want("pot", *ring_size(piece["r"], piece["h"] + 0.3, 12))
        elif k in ("fence", "canopy", "stack", "deck"):
            want("wood", 2.0, 3.0)
            if k == "canopy":
                want("cloth" if piece.get("cloth", True) else "thatch",
                     piece["x1"] - piece["x0"] + 0.2, piece["y1"] - piece["y0"] + 0.4)
            if k == "fence" and piece.get("stone"):
                want("stone", 4.0, piece["h"] + 0.5)
            if k == "stack":
                want(piece.get("region", "wood"), 2.0, 2.0)
        elif k == "field":
            want("field", piece["x1"] - piece["x0"], piece["y1"] - piece["y0"])
            if piece.get("plants"):
                want("crop", 1.0, 1.2)
        elif k in PROPS:
            for name, w, h in PROPS[k]:
                want(name, w, h)
        elif k == "plinth":
            want("plinth", max(piece["x1"] - piece["x0"], piece["y1"] - piece["y0"]) + 0.2, 1.0)
    for name in sorted(need, key=lambda n: (not n.startswith(("rw", "bk")), n)):
        b.region(name, *need[name])
    return facades


PROPS = {"balcony": [("slab", 6.0, 1.2), ("rail", 6.0, 1.0)], "basket": [("thatch", 2.0, 1.0)], "sack": [("thatch", 2.0, 1.0)], "logs": [("wood", 2.0, 3.0)],
         "rack": [("wood", 2.0, 3.0)], "drum": [("wood", 2.0, 3.0), ("pot", 2.0, 1.0)],
         "well": [("stone", 4.0, 1.2), ("wood", 2.0, 3.0)], "fire": [("stone", 4.0, 1.2), ("wood", 2.0, 3.0)],
         "crane": [("wood", 2.0, 3.0)], "stones": [("stone", 4.0, 1.2)], "frame": [("wood", 2.0, 3.0)]}


def _bays(length, windows, door):
    out = []
    if door:
        out.append(length / 2)
    if windows and length > 3.0:
        if door:
            out += [length * 0.2, length * 0.8] if length > 4.5 else []
        else:
            out += [length * (k + 1) / (windows + 1) for k in range(windows)]
    return sorted(out)


def _block_openings(bays, door, h):
    out = []
    for u in bays:
        if door is not None and abs(u - door) < 0.01:
            out.append((u - 0.55, 0.0, u + 0.55, min(2.1, h - 0.5)))
        else:
            out.append((u - 0.3, 1.2, u + 0.3, min(1.9, h - 0.6)))
    return out


# --------------------------------------------------------------------------------------------------
# joints

def solids(layout):
    """The solid volumes of a layout as shapes for core/joints.py: what a neighbour can collide
    with, from the widest it gets (the plinth or the eave) to its highest point."""
    out = []
    for i, p in enumerate(layout):
        k = p["kind"]
        z0 = p.get("z", 0.0)
        name = f"{k} {i}"
        if k in ("hut", "granary", "tower"):
            roof = p.get("roof", "cone" if k != "granary" else "dome")
            r = p["r"] + max(0.15 if p.get("base") else 0.0, p.get("overhang", 0.4) if roof == "cone" else 0.0)
            z1 = z0 + p.get("stilts", 0.0) + p.get("base", 0.0) + p["wall_h"] + p.get("roof_h", 0.0) + (
                0.6 if roof == "crenel" else 0.0)
            out.append({"shape": "circle", "x": p["x"], "y": p["y"], "r": r, "z0": z0, "z1": z1, "name": name,
                        "sides": 10 if p.get("big") else 8})
        elif k == "block":
            z1 = z0 + p["h"] + p.get("parapet", 0.0) + (0.3 if p.get("merlons") else 0.0)
            shape = {"shape": "rect", "x0": p["x0"], "y0": p["y0"], "x1": p["x1"], "y1": p["y1"], "z0": z0,
                     "z1": z1, "name": name}
            if p.get("roof") == "thatch":
                shape["z1"] = z0 + p["h"] + 0.4
            else:
                shape["roof"] = z0 + p["h"]
            out.append(shape)
    return out


def junctions(layout):
    """The bad joints of a layout: [] when every pair of volumes is apart or embedded."""
    return [m for _, _, m in joints.problems(solids(layout))]


# --------------------------------------------------------------------------------------------------
# geometry

def emit(b, layout, medium):
    """Builds every piece of the layout. Returns the highest point and where it is."""
    top = (0.0, 0.0, 0.0)
    for piece in layout:
        k = piece["kind"]
        z_top = 0.0
        if k in ("hut", "granary", "tower"):
            z_top = _round(b, piece, medium)
            at = (piece["x"], piece["y"], z_top)
        elif k == "block":
            z_top = _block(b, piece, medium)
            at = ((piece["x0"] + piece["x1"]) / 2, (piece["y0"] + piece["y1"]) / 2, z_top)
        elif k == "pot":
            if not medium:                                 # low detail: no small props
                continue
            x, y, r, h, z = piece["x"], piece["y"], piece["r"], piece["h"], piece.get("z", 0.0)
            n = 12
            start = len(b.faces)
            b.frustum(x, y, r * 0.75, r, z, z + h * 0.45, n, "pot")
            b.frustum(x, y, r, r * 0.55, z + h * 0.45, z + h * 0.8, n, "pot")
            b.frustum(x, y, r * 0.55, r * 0.6, z + h * 0.8, z + h, n, "pot")
            b.disc(x, y, r * 0.6, z + h, n, "pot")
            _smooth(b, start)
            at = (piece["x"], piece["y"], piece["h"])
        elif k == "fence":
            if piece.get("medium_only") and not medium:
                continue
            if piece.get("stone"):
                _stone_wall(b, piece)
            else:
                b.fence(piece["points"], piece["h"], "wood", kind=piece.get("type", "RAILS"),
                        closed=piece.get("closed", False), gap=piece.get("gap"))
            at = (0.0, 0.0, piece["h"])
        elif k == "canopy":
            b.canopy(piece["x0"], piece["x1"], piece["y0"], piece["y1"], piece["z_hi"], piece["z_lo"],
                     "cloth" if piece.get("cloth", True) else "thatch", "wood", slope=piece.get("slope", "-y"))
            at = (piece["x0"], piece["y0"], piece["z_hi"])
        elif k == "stack":
            if not medium:
                continue
            r = piece.get("region", "wood")
            b.box(piece["x0"], piece["x1"], piece["y0"], piece["y1"], piece.get("z", 0.0), piece["z1"], r, r)
            at = (piece["x0"], piece["y0"], piece["z1"])
        elif k == "deck":
            _deck(b, piece)
            at = (piece["x0"], piece["y0"], piece["z"])
        elif k == "field":
            _field(b, piece, medium)
            at = (piece["x0"], piece["y0"], 0.3)
        elif k == "plinth":
            b.box(piece["x0"], piece["x1"], piece["y0"], piece["y1"], 0.0, piece["h"], "plinth", "plinth")
            at = (piece["x0"], piece["y0"], piece["h"])
        elif k in PROPS:
            if not medium and k != "balcony":
                continue
            start = len(b.faces)
            _prop(b, piece)
            if k in ("basket", "sack", "drum", "well"):
                _smooth(b, start)
            dz = piece.get("z", 0.0) if k != "balcony" else 0.0
            if dz:                                         # standing on a deck or a plinth
                for f in b.faces[start:]:
                    f.pts = [(x, y, z + dz) for x, y, z in f.pts]
                b.faces[start:] = [f for f in b.faces[start:]          # bottoms lying on the deck are hidden
                                   if any(abs(z - dz) > 1e-6 for _, _, z in f.pts)]
            at = (piece.get("x", 0.0), piece.get("y", 0.0), 0.5 + dz)
        if at[2] > top[2]:
            top = at
    return top


def _smooth(b, start):
    """Smooth shading on the faces added since `start` that are not flat tops or bottoms: round
    walls and roofs light as one surface instead of facets (no extra triangles; the flat faces
    keep their edges sharp)."""
    for f in b.faces[start:]:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = f.pts[0], f.pts[1], f.pts[2]
        ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = (nx * nx + ny * ny + nz * nz) ** 0.5
        if ln > 1e-12 and abs(nz) / ln < 0.995:
            f.smooth = True


def _round(b, p, medium):
    x, y, r, n = p["x"], p["y"], p["r"], p["n"]
    z0 = p.get("z", 0.0)
    if p.get("stilts"):                                    # a granary raised on posts (one at low detail)
        s = p["stilts"]
        spots = [(x + 0.7 * r * math.cos(math.pi / 4 + a * math.pi / 2), y + 0.7 * r * math.sin(math.pi / 4 + a * math.pi / 2))
                 for a in range(4)] if medium else [(x, y)]
        w = 0.08 if medium else 0.2
        for px, py in spots:
            b.box(px - w, px + w, py - w, py + w, z0, z0 + s, "wood", "wood", skip=("top",))
        b.disc(x, y, r, z0 + s, n, p["wall_region"], down=True)
        z0 += s
    if p.get("base"):
        b.ring(x, y, r + 0.15, z0, z0 + p["base"], n, "plinth")
        ring_in = [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
        ring_out = [(x + (r + 0.15) * math.cos(2 * math.pi * i / n), y + (r + 0.15) * math.sin(2 * math.pi * i / n))
                    for i in range(n + 1)]
        zb = z0 + p["base"]
        for (ax, ay), (bx, by), (cx, cy), (dx, dy) in zip(ring_out, ring_out[1:], ring_in[1:], ring_in):
            b.face_out([(ax, ay, zb), (bx, by, zb), (cx, cy, zb), (dx, dy, zb)], "plinth", (0.0, 0.0, 1.0))
        z0 = zb
    z1 = z0 + p["wall_h"]
    start = len(b.faces)
    b.ring(x, y, r, z0, z1, n, p["wall_region"])
    _smooth(b, start)
    roof = p.get("roof", "cone" if p["kind"] != "granary" else "dome")
    start = len(b.faces)
    if roof == "cone":
        fin = p.get("finial", 0.0) if medium else 0.0
        if medium:
            tiers = 4 if r >= 3.0 else (3 if r >= 1.3 else 2)
            top = b.thatch_cone(x, y, r, z1, p["roof_h"], n, "thatch", overhang=p.get("overhang", 0.4),
                                tiers=tiers, lip=0.1 + 0.03 * r, finial=fin, finial_region="wood")
        else:
            top = b.cone_roof(x, y, r, z1, p["roof_h"], n, "thatch", overhang=p.get("overhang", 0.4))
        _smooth(b, start)
        top += fin
        ov = p.get("overhang", 0.4)
        if medium and p["kind"] == "hut" and ov >= 0.4:     # posts holding the eave (a veranda)
            slope = p["roof_h"] / r
            rp = r + ov * 0.7
            zp = z1 - slope * (rp - r) - 0.06
            m = 8 if r < 3 else 12
            for j in range(m):
                a = 2 * math.pi * (j + 0.5) / m
                if abs(math.sin(a) + 1) < 0.08:             # keep the door clear
                    continue
                px, py = x + rp * math.cos(a), y + rp * math.sin(a)
                b.box(px - 0.06, px + 0.06, py - 0.06, py + 0.06, z0 - p.get("base", 0.0), zp, "wood", "wood",
                      skip=("top",))
    elif roof == "dome":
        top = b.dome(x, y, r, z1, p["roof_h"], n, "dome", rings=3 if medium else 2)
        _smooth(b, start)
    else:
        top = _crenel(b, x, y, r, z1, n, p["wall_region"])
    if medium and p.get("door"):                           # the door's frame: jambs and lintel
        dx, dy = x, y - r
        w = p.get("door_w", 1.0) / 2
        dh = z0 + p.get("door_h", 1.9)
        b.box(dx - w - 0.12, dx + w + 0.12, dy - 0.16, dy + 0.06, dh, dh + 0.14, "wood", "wood")
        for jx in (dx - w - 0.12, dx + w):
            b.box(jx, jx + 0.12, dy - 0.14, dy + 0.04, z0, dh, "wood", "wood", skip=("top",))
    if medium and p["kind"] == "granary" and p.get("stilts"):   # a ladder up to the granary
        lx, ly = x, y - r - 0.35
        zt = z0 + p["wall_h"] * 0.6
        for rx in (lx - 0.25, lx + 0.2):
            b.box(rx, rx + 0.05, ly, ly + 0.05, 0.0, zt, "wood", "wood")
        for k in range(1, int(zt / 0.35)):
            b.box(lx - 0.2, lx + 0.2, ly + 0.005, ly + 0.045, k * 0.35, k * 0.35 + 0.04, "wood", "wood")
    return top


def _crenel(b, x, y, r, z1, n, region):
    """A flat top with a parapet ring for a round wall that ends at z1."""
    t = 0.25
    b.ring(x, y, r, z1, z1 + 0.6, n, region)
    inner = [(x + (r - t) * math.cos(2 * math.pi * i / n), y + (r - t) * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    outer = [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    for (ax, ay), (bx, by) in zip(inner, inner[1:]):
        b.facing([(ax, ay, z1), (bx, by, z1), (bx, by, z1 + 0.6), (ax, ay, z1 + 0.6)],
                 [(0, 0), (0.5, 0), (0.5, 0.6), (0, 0.6)], region, (x - (ax + bx) / 2, y - (ay + by) / 2, 0.0))
    for (ax, ay), (bx, by), (cx, cy), (dx, dy) in zip(outer, outer[1:], inner[1:], inner):
        b.face_out([(ax, ay, z1 + 0.6), (bx, by, z1 + 0.6), (cx, cy, z1 + 0.6), (dx, dy, z1 + 0.6)], "roof_flat",
                   (0.0, 0.0, 1.0))
    b.disc(x, y, r - t, z1, n, "roof_flat")
    return z1 + 0.6


def _block(b, p, medium):
    i = p["id"]
    x0, x1, y0, y1, h = p["x0"], p["x1"], p["y0"], p["y1"], p["h"]
    z0 = p.get("z", 0.0)
    walls = (("front", (x0, y0, z0), (1.0, 0.0, 0.0), x1 - x0), ("back", (x1, y1, z0), (-1.0, 0.0, 0.0), x1 - x0),
             ("left", (x0, y1, z0), (0.0, -1.0, 0.0), y1 - y0), ("right", (x1, y0, z0), (0.0, 1.0, 0.0), y1 - y0))
    joined = p.get("joined", ())
    open_sides = tuple(SIDE_OF[j] for j in joined)
    for face, origin, ua, length in walls:
        if face in joined:
            continue
        region = f"bk{i}_{face}"
        spec = b._african_facades[region]
        if medium and spec["openings"]:
            b.wall(origin, ua, length, h, region, spec["openings"])
        else:
            b.flat_wall(origin, ua, length, h, region)
    zt = z0 + h
    roof = p.get("roof", "flat")
    if roof == "thatch":
        hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
        top = b.hipped_roof((x0 + x1) / 2, (y0 + y1) / 2, hx + 0.5, hy + 0.5, zt - 0.4, 0.8, region="thatch") \
            if p.get("hipped", True) else zt
    else:
        top = b.flat_roof(x0, x1, y0, y1, zt, "roof_flat", parapet_h=p.get("parapet", 0.0),
                          parapet_region="parapet" if p.get("parapet") else None,
                          merlons=(p.get("merlons", 0.0) if medium else 0.0), open_sides=open_sides)
    if medium and p.get("sahel", True) and roof != "thatch":
        _buttresses(b, p, z0, h, top)
    if medium and p.get("beams"):                          # toron: beam ends on the front and sides
        zb = z0 + h - 0.45
        # along the sides they stop short of a joined end
        a0, a1 = y0 + (1.2 if "-y" in open_sides else 0.3), y1 - (1.2 if "+y" in open_sides else 0.3)
        c0, c1 = x0 + (1.2 if "-x" in open_sides else 0.3), x1 - (1.2 if "+x" in open_sides else 0.3)
        if "-y" not in open_sides:
            b.beam_ends("-y", y0, c0, c1, zb, max(3, int((c1 - c0) / 0.9)), 0.35, "wood")
        if "-x" not in open_sides:
            b.beam_ends("-x", x0, a0, a1, zb, max(2, int((a1 - a0) / 0.9)), 0.35, "wood")
        if "+x" not in open_sides:
            b.beam_ends("+x", x1, a0, a1, zb, max(2, int((a1 - a0) / 0.9)), 0.35, "wood")
    return top


def _buttresses(b, p, z0, h, top):
    """Sahel buttresses: pilasters against the walls rising above the parapet into pinnacles,
    and waterspouts at the roof's level."""
    x0, x1, y0, y1 = p["x0"], p["x1"], p["y0"], p["y1"]
    zt = max(top, z0 + h) + 0.35
    out = 0.18
    joined = tuple(SIDE_OF[j] for j in p.get("joined", ()))
    near = {"-y": ("-x", "+x"), "+y": ("-x", "+x"), "-x": ("-y", "+y"), "+x": ("-y", "+y")}
    for side, a0, a1 in (("-y", x0, x1), ("+y", x0, x1), ("-x", y0, y1), ("+x", y0, y1)):
        if side in joined:
            continue
        lo, hi = near[side]                                 # keep clear of a joined end
        a0, a1 = a0 + (1.2 if lo in joined else 0.0), a1 - (1.2 if hi in joined else 0.0)
        L = a1 - a0
        if L < 1.2:                                         # too short for two pilasters
            continue
        n = max(2, int(L / 1.8) + 1)
        for k in range(n):
            a = a0 + 0.2 + (L - 0.4) * k / (n - 1)
            if side in ("-y", "+y"):
                if p.get("door") is True and side == "-y" and abs(a - (x0 + x1) / 2) < 0.9:
                    continue
                ya, yb = (y0 - out, y0) if side == "-y" else (y1, y1 + out)
                b.box(a - 0.15, a + 0.15, ya, yb, z0, zt, "trim", "trim",
                      skip=(("+y",) if side == "-y" else ("-y",)) + ("top",))
                b.pyramid(a - 0.15, a + 0.15, ya, yb, zt, 0.35, "trim")
            else:
                xa, xb = (x0 - out, x0) if side == "-x" else (x1, x1 + out)
                b.box(xa, xb, a - 0.15, a + 0.15, z0, zt, "trim", "trim",
                      skip=(("+x",) if side == "-x" else ("-x",)) + ("top",))
                b.pyramid(xa, xb, a - 0.15, a + 0.15, zt, 0.35, "trim")
    zs = z0 + h + 0.1                                       # waterspouts on the front and back
    for yy, (ya, yb) in ((y0, (y0 - 0.6, y0)), (y1, (y1, y1 + 0.6))):
        if ("-y" if yy == y0 else "+y") in joined:
            continue
        for a in (x0 + (x1 - x0) * 0.3, x0 + (x1 - x0) * 0.7):
            b.box(a - 0.07, a + 0.07, ya, yb, zs, zs + 0.12, "wood", "wood",
                  skip=("+y",) if yy == y0 else ("-y",))


def _prop(b, p):
    k = p["kind"]
    x, y = p.get("x", 0.0), p.get("y", 0.0)
    if k == "balcony":                                     # a gallery on posts in front of a wall at -Y
        x0, x1, yw, z, d = p["x0"], p["x1"], p["y_wall"], p["z"], p.get("depth", 1.2)
        b.balcony(x0, x1, yw, z, d, "slab", "rail")
        for px in [x0 + 0.15 + (x1 - x0 - 0.3) * j / max(1, int((x1 - x0) / 1.8)) for j in range(int((x1 - x0) / 1.8) + 1)]:
            b.box(px - 0.07, px + 0.07, yw - d + 0.05, yw - d + 0.19, 0.0, z - 0.12, "wood", "wood", skip=("top",))
    elif k == "basket":
        r, h = p.get("r", 0.3), p.get("h", 0.35)
        b.frustum(x, y, r * 0.8, r, 0.0, h, 12, "thatch")
        b.disc(x, y, r, h, 12, "thatch")
    elif k == "sack":
        r, h = p.get("r", 0.25), p.get("h", 0.55)
        b.frustum(x, y, r, r * 1.05, 0.0, h * 0.6, 8, "thatch")
        b.frustum(x, y, r * 1.05, r * 0.35, h * 0.6, h, 8, "thatch")
        b.disc(x, y, r * 0.35, h, 8, "thatch")
    elif k == "logs":                                      # a pile: two layers along X or Y
        L, n, r = p.get("length", 2.0), p.get("n", 4), p.get("r", 0.12)
        along = p.get("along", "x")
        for layer in range(2):
            m = n - layer
            for j in range(m):
                off = (j - (m - 1) / 2) * 2.05 * r
                z = r + layer * 1.75 * r
                if along == "x":
                    b.log(x - L / 2, y + off, x + L / 2, y + off, z, r, 8, "wood")
                else:
                    b.log(x + off, y - L / 2, x + off, y + L / 2, z, r, 8, "wood")
    elif k == "rack":                                      # two posts, a bar and spears
        w = p.get("w", 1.6)
        for px in (x - w / 2, x + w / 2):
            b.box(px - 0.05, px + 0.05, y - 0.05, y + 0.05, 0.0, 1.5, "wood", "wood")
        b.log(x - w / 2, y + 0.06, x + w / 2, y + 0.06, 1.3, 0.035, 6, "wood")
        for j in range(5):
            sx = x - w / 2 + 0.25 + (w - 0.5) * j / 4
            b.box(sx - 0.02, sx + 0.02, y + 0.1, y + 0.14, 0.0, 1.9, "wood", "wood")
            b.pyramid(sx - 0.035, sx + 0.035, y + 0.085, y + 0.155, 1.9, 0.22, "pot")
    elif k == "drum":
        r, h = p.get("r", 0.3), p.get("h", 0.7)
        b.frustum(x, y, r * 0.7, r, 0.0, h, 12, "wood")
        b.disc(x, y, r, h, 12, "pot")
    elif k == "well":
        b.frustum(x, y, 0.75, 0.75, 0.0, 0.7, 16, "stone")
        b.disc(x, y, 0.75, 0.7, 16, "stone")
        for px in (x - 0.7, x + 0.62):
            b.box(px, px + 0.08, y - 0.04, y + 0.04, 0.7, 1.9, "wood", "wood")
        b.log(x - 0.72, y, x + 0.72, y, 1.75, 0.05, 6, "wood")
    elif k == "fire":                                      # a ring of stones and crossed logs
        for j in range(8):
            a = 2 * math.pi * j / 8
            sx, sy = x + 0.5 * math.cos(a), y + 0.5 * math.sin(a)
            b.box(sx - 0.1, sx + 0.1, sy - 0.1, sy + 0.1, 0.0, 0.18, "stone", "stone")
        b.log(x - 0.35, y - 0.1, x + 0.35, y + 0.1, 0.08, 0.06, 6, "wood")
        b.log(x - 0.1, y - 0.35, x + 0.1, y + 0.35, 0.2, 0.06, 6, "wood")
    elif k == "crane":                                     # a shear-legs crane with its beam
        h = p.get("h", 4.0)
        for px in (x - 0.8, x + 0.8):
            b.box(px - 0.08, px + 0.08, y - 0.08, y + 0.08, 0.0, h, "wood", "wood")
        b.log(x - 0.9, y, x + 0.9, y, h - 0.1, 0.09, 8, "wood")
        b.log(x, y - 0.1, x, y - 2.2, h - 0.3, 0.07, 8, "wood")
        b.box(x - 0.015, x + 0.015, y - 2.115, y - 2.085, 1.2, h - 0.3, "wood", "wood")
    elif k == "stones":                                    # cut blocks, stacked
        n = p.get("n", 6)
        for j in range(n):
            layer = j // 3
            col = j % 3
            bx = x + (col - 1) * 0.62 + (0.15 if layer % 2 else 0.0)
            bz = layer * 0.42
            b.box(bx - 0.28, bx + 0.28, y - 0.3, y + 0.3, bz, bz + 0.4, "stone", "stone")
    elif k == "frame":                                     # a timber frame (a siege engine being built)
        w, d, h = p.get("w", 3.0), p.get("d", 1.6), p.get("h", 2.4)
        for px in (x - w / 2, x + w / 2):
            for py in (y - d / 2, y + d / 2):
                b.box(px - 0.08, px + 0.08, py - 0.08, py + 0.08, 0.0, h, "wood", "wood")
        for py in (y - d / 2, y + d / 2):
            b.log(x - w / 2, py, x + w / 2, py, h - 0.1, 0.09, 8, "wood")
            b.log(x - w / 2, py, x + w / 2, py, 0.5, 0.08, 8, "wood")
        b.log(x - w / 2 + 0.3, y - d / 2, x + w / 2 - 0.3, y + d / 2, h * 0.6, 0.08, 8, "wood")
        b.log(x - w / 2, y, x + w / 2 + 1.2, y, h + 0.3, 0.1, 8, "wood")


def _stone_wall(b, p):
    """Stone wall panels that stop short of piers at every corner (no overlaps)."""
    pts = p["points"] + ([p["points"][0]] if p.get("closed") else [])
    t = 0.45
    ends = set()
    for i, (a, c) in enumerate(zip(pts, pts[1:])):
        if p.get("gap") is not None and i == p["gap"]:
            continue
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
        b._panel((a[0] + ux * t / 2, a[1] + uy * t / 2), (c[0] - ux * t / 2, c[1] - uy * t / 2), 0.0, p["h"], t, "stone")
        ends.update((a, c))
    h = t / 2 + 0.06
    for px, py in sorted(ends):
        b.box(px - h, px + h, py - h, py + h, 0.0, p["h"] + 0.25, "stone", "stone")
    if b.medium and p.get("crenels", True):                # merlons along the top
        for i, (a, c) in enumerate(zip(pts, pts[1:])):
            if p.get("gap") is not None and i == p["gap"]:
                continue
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            m = int((L - 0.8) / 0.9)
            for j in range(m):
                f = (0.4 + 0.45 + j * 0.9) / L
                mx, my = a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f
                b.box(mx - 0.2, mx + 0.2, my - 0.2, my + 0.2, p["h"], p["h"] + 0.3, "stone", "stone")


def _deck(b, p):
    x0, x1, y0, y1, z = p["x0"], p["x1"], p["y0"], p["y1"], p["z"]
    b.box(x0, x1, y0, y1, z - 0.2, z, "wood", "wood")
    nx, ny = max(2, int((x1 - x0) / 2.0) + 1), max(2, int((y1 - y0) / 2.0) + 1)
    for i in range(nx):
        for j in range(ny):
            px = x0 + 0.2 + (x1 - x0 - 0.4) * i / (nx - 1)
            py = y0 + 0.2 + (y1 - y0 - 0.4) * j / (ny - 1)
            b.ring(px, py, 0.12, 0.0, z - 0.2, 6, "wood")


def _field(b, p, medium):
    """Tilled ground: a low bed and its ridges (low prisms) along X."""
    x0, x1, y0, y1 = p["x0"], p["x1"], p["y0"], p["y1"]
    b.box(x0, x1, y0, y1, 0.0, 0.08, "field", "field")
    n = p.get("rows", 6) if medium else max(3, p.get("rows", 6) // 2)
    for k in range(n):
        yc = y0 + (y1 - y0) * (k + 0.5) / n
        w = (y1 - y0) / n * 0.35
        zt = 0.08 + (0.22 if medium else 0.15)
        b.face_out([(x0 + 0.2, yc - w, 0.08), (x1 - 0.2, yc - w, 0.08), (x1 - 0.2, yc, zt), (x0 + 0.2, yc, zt)],
                   "field", (0.0, -1.0, 1.0))
        b.face_out([(x1 - 0.2, yc + w, 0.08), (x0 + 0.2, yc + w, 0.08), (x0 + 0.2, yc, zt), (x1 - 0.2, yc, zt)],
                   "field", (0.0, 1.0, 1.0))
        for xe, nx in ((x0 + 0.2, -1.0), (x1 - 0.2, 1.0)):     # the ridge's ends
            b.face_out([(xe, yc - w, 0.08), (xe, yc + w, 0.08), (xe, yc, zt)], "field", (nx, 0.0, 0.0))
        if medium and p.get("plants"):                      # millet along the ridge
            m = p["plants"]
            for j in range(m):
                px = x0 + 0.45 + (x1 - x0 - 0.9) * (j + 0.5 * (k % 2)) / m
                hh = 0.75 + 0.25 * (((j * 7 + k * 3) % 5) / 4)
                b.frustum(px, yc, 0.07, 0.015, zt - 0.02, zt + hh, 4, "crop")
