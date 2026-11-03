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

from ...kit import cone_roof_size, dome_size, ring_size

DOOR_ANGLE = 1.5 * math.pi          # the round walls' doors face -Y


def sides(medium, big=False):
    if big:
        return 20 if medium else 10
    return 16 if medium else 8


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
                name = f"bk{i}_{face}"
                want(name, length, h)
                door = piece.get("door") is True and face == "front" or piece.get("door") == face
                win = piece.get("windows", 1)
                bays = _bays(length, win, door)
                facades[name] = {"kind": "block", "bays": bays, "door": length / 2 if door else None, "storeys": 1,
                                 "tops": [2.1], "h": h, "sahel": piece.get("sahel", True),
                                 "openings": _block_openings(bays, length / 2 if door else None, h)}
            want("roof_flat", max(w, d) + 0.2, min(w, d) + 0.2)
            if piece.get("parapet"):
                want("parapet", max(w, d) + 0.4, piece["parapet"] + 0.4)
            if piece.get("roof") == "thatch":
                want("thatch", max(w, d) + 1.2, math.hypot(min(w, d) / 2 + 0.5, (min(w, d) / 2 + 0.5) * 0.8) + 0.3)
            want("wood", 2.0, 3.0)
            if medium:
                want("reveal", 1.2, 2.4)
        elif k == "pot":
            want("pot", *ring_size(piece["r"], piece["h"], 8))
        elif k in ("fence", "canopy", "stack", "deck"):
            want("wood", 2.0, 3.0)
            if k == "canopy":
                want("cloth" if piece.get("cloth", True) else "thatch",
                     piece["x1"] - piece["x0"] + 0.2, piece["y1"] - piece["y0"] + 0.4)
            if k == "fence" and piece.get("stone"):
                want("stone", 4.0, piece["h"] + 0.3)
            if k == "stack":
                want(piece.get("region", "wood"), 2.0, 2.0)
        elif k == "field":
            want("field", piece["x1"] - piece["x0"], piece["y1"] - piece["y0"])
        elif k == "plinth":
            want("plinth", max(piece["x1"] - piece["x0"], piece["y1"] - piece["y0"]) + 0.2, 1.0)
    for name in sorted(need, key=lambda n: (not n.startswith(("rw", "bk")), n)):
        b.region(name, *need[name])
    return facades


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
            n = 8
            b.ring(piece["x"], piece["y"], piece["r"], piece.get("z", 0.0), piece.get("z", 0.0) + piece["h"], n, "pot")
            b.disc(piece["x"], piece["y"], piece["r"], piece.get("z", 0.0) + piece["h"], n, "pot")
            at = (piece["x"], piece["y"], piece["h"])
        elif k == "fence":
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
        if at[2] > top[2]:
            top = at
    return top


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
    b.ring(x, y, r, z0, z1, n, p["wall_region"])
    roof = p.get("roof", "cone" if p["kind"] != "granary" else "dome")
    if roof == "cone":
        fin = p.get("finial", 0.0) if medium else 0.0
        top = b.cone_roof(x, y, r, z1, p["roof_h"], n, "thatch", overhang=p.get("overhang", 0.4),
                          finial=fin, finial_region="wood")
        top += fin
    elif roof == "dome":
        top = b.dome(x, y, r, z1, p["roof_h"], n, "dome", rings=3 if medium else 2)
    else:
        top = _crenel(b, x, y, r, z1, n, p["wall_region"])
    if medium and p.get("door"):                           # a lintel over the door
        dx, dy = x, y - r
        w = p.get("door_w", 1.0) / 2 + 0.1
        dh = z0 + p.get("door_h", 1.9)
        b.box(dx - w, dx + w, dy - 0.16, dy + 0.06, dh, dh + 0.14, "wood", "wood")
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
    for face, origin, ua, length in walls:
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
                          merlons=(p.get("merlons", 0.0) if medium else 0.0))
    if medium and p.get("beams"):                          # toron: beam ends on the front and sides
        zb = z0 + h - 0.45
        b.beam_ends("-y", y0, x0 + 0.3, x1 - 0.3, zb, max(3, int((x1 - x0) / 0.9)), 0.35, "wood")
        b.beam_ends("-x", x0, y0 + 0.3, y1 - 0.3, zb, max(2, int((y1 - y0) / 0.9)), 0.35, "wood")
        b.beam_ends("+x", x1, y0 + 0.3, y1 - 0.3, zb, max(2, int((y1 - y0) / 0.9)), 0.35, "wood")
    return top


def _stone_wall(b, p):
    pts = p["points"] + ([p["points"][0]] if p.get("closed") else [])
    for i, (a, c) in enumerate(zip(pts, pts[1:])):
        if p.get("gap") is not None and i == p["gap"]:
            continue
        b._panel(a, c, 0.0, p["h"], 0.45, "stone")


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
    n = p.get("rows", 6)
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
