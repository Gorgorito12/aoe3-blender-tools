# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces African buildings are composed of, as plain dicts (a layout), and the code that
declares their regions and builds them with the kit. A layout lists pieces in metres:

    {"kind": "hut", "x": 0, "y": 0, "r": 2.5, "wall_h": 2.3, "roof_h": 3.0, "door": True}
    {"kind": "block", "x0": -3, "x1": 3, "y0": -2, "y1": 2, "h": 3, "door": True, "parapet": 0.5}
    {"kind": "granary", ...}, {"kind": "pot", ...}, {"kind": "fence", ...}, {"kind": "tower", ...},
    {"kind": "canopy", ...}, {"kind": "stack", ...}, {"kind": "deck", ...}, {"kind": "field", ...}

Each round wall and each block wall gets its own region (its door is painted where the geometry
has it); thatch, domes, roofs, wood, cloth and stone share one region each, sized for the
largest piece. Layouts face -Y like every style (the front, with the door, is at -Y). The shape a
building must have comes from the real models: see CLAUDE.md and tests/test_shape.py."""
import math

from ... import joints
from ...kit import cone_roof_size, dome_size, ring_size

DOOR_ANGLE = 1.5 * math.pi          # the round walls' doors face -Y
SIDE_OF = {"front": "-y", "back": "+y", "left": "-x", "right": "+x"}
PIER_FACE = (1.3, 0.1, 1.2, 4.8, 1.5)  # a pier's side painted: foot's width, top's two ends, height, its chamfer


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
                             "tops": [piece.get("door_h", 1.9)], "bands": piece.get("bands", True),
                             "sahel": piece.get("sahel", False)}
        elif k == "block":
            w, d, h = piece["x1"] - piece["x0"], piece["y1"] - piece["y0"], piece["h"]
            for face, length in (("front", w), ("back", w), ("left", d), ("right", d)):
                if face in piece.get("joined", ()):                # ends inside its neighbour: no wall
                    continue
                name = f"bk{i}_{face}"
                want(name, length, h)
                door = piece.get("door") is True and face == "front" or piece.get("door") == face
                win = 0 if face in piece.get("blank", ()) else piece.get("windows", 1)
                bays = _bays(length, win, door)
                facades[name] = {"kind": "block", "bays": bays, "door": length / 2 if door else None, "storeys": 1,
                                 "tops": [2.1], "h": h, "sahel": piece.get("sahel", True),
                                 "gate": bool(door and piece.get("gate")), "foot": piece.get("foot", False),
                                 "shutters": piece.get("shutters", False),
                                 "band": piece.get("band", True), "art": piece.get("art", {}).get(face),
                                 "closed": [],
                                 "openings": _block_openings(bays, length / 2 if door else None, h,
                                                             piece.get("gate", (1.1, 2.1)), piece.get("sill"))}
                for u, v, ww, wh, closed in piece.get("win", {}).get(face, ()):
                    facades[name]["openings"].append((u - ww / 2, v, u + ww / 2, v + wh))
                    if closed:
                        facades[name]["closed"].append(u - ww / 2)
            want("roof_flat", max(w, d) + 0.2, min(w, d) + 0.2)
            want("trim", 2.0, h + 1.2)
            if piece.get("parapet"):
                want("parapet", max(w, d) + 0.4, piece["parapet"] + 0.4)
            if piece.get("painted"):
                want("step", 2.0, 1.0)
            if piece.get("coping"):
                want(piece["coping"], max(w, d) + 0.4, piece["parapet"] + 0.4)
            if piece.get("roof") == "thatch":
                want("thatch", max(w, d) + 1.2, math.hypot(min(w, d) / 2 + 0.5, (min(w, d) / 2 + 0.5) * 0.8) + 0.3)
            want("wood", 2.0, 3.0)
            if medium:
                want("reveal", 2.4, 3.2)
        elif k == "pot":
            want("pot", *ring_size(piece["r"], piece["h"] + 0.3, 12))
        elif k == "ground":
            want("yard", 2 * piece["half"] + 0.6, 2 * piece["half"] + 0.6)
        elif k == "plot":
            want("field", 2 * piece["r"] + 0.4, 2 * piece["r"] + 0.4)
            want("crop", 1.2, 1.4)
            want("crop_head", 0.4, 0.4)
            want("wood", 2.0, 3.0)
        elif k == "shed":
            want("wood", 2.0, 3.0)
            want("planks", piece["x1"] - piece["x0"] + 0.2, piece["y1"] - piece["y0"] + 0.2)
            want("planks", piece["y1"] - piece["y0"] + 0.2, piece["x1"] - piece["x0"] + 0.2)
        elif k == "stairs":
            want(piece.get("region", "trim"), 3.2, 1.2)
        elif k == "door_frame":
            want("frame", 2.2, 3.0)
        elif k == "mast":
            want("frame", 2.2, 3.0)
        elif k == "pier":
            want("pier", PIER_FACE[4] + 0.4, PIER_FACE[3])
            want("pier_cap", 1.4, 1.2)
        elif k == "banner":
            want("banner", piece["w"] + 0.1, piece["h"] + 0.1)
            want("wood", 2.0, 3.0)
        elif k == "hatch":
            want("trim", 2.0, 3.0)
            want("planks", 1.2, 1.0)
        elif k == "lookout":
            want("wood", 2.0, 3.0)
            want("planks", piece["w"] + 0.2, piece["w"] + 0.2)
        elif k in ("fence", "canopy", "stack", "deck"):
            want("wood", 2.0, 3.0)
            if k == "canopy":
                sq = max(piece["x1"] - piece["x0"], piece["y1"] - piece["y0"])
                want("cloth" if piece.get("cloth", True) else "thatch", sq + 0.2, sq + 0.4)
            if k == "fence" and piece.get("stone"):
                want(piece.get("material", "stone"), 4.0, piece["h"] + 0.5)
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
    want("wood", 2.0, 3.0)
    for name in sorted(need, key=lambda n: (not n.startswith(("rw", "bk")), n)):
        b.region(name, *need[name])
    return facades


PROPS = {"balcony": [("slab", 6.0, 1.2), ("rail", 6.0, 1.0)], "basket": [("thatch", 2.0, 1.0)], "sack": [("thatch", 2.0, 1.0)], "logs": [("wood", 2.0, 3.0)],
         "rack": [("wood", 2.0, 3.0), ("pot", 2.0, 1.0)], "drum": [("wood", 2.0, 3.0), ("pot", 2.0, 1.0)],
         "well": [("stone", 4.0, 1.2), ("wood", 2.0, 3.0)], "fire": [("stone", 4.0, 1.2), ("wood", 2.0, 3.0)],
         "crane": [("wood", 2.0, 3.0)], "stones": [("stone", 4.0, 1.2)], "frame": [("wood", 2.0, 3.0)],
         "crate": [("crate", 1.4, 0.7)], "barrel": [("barrel", 1.8, 1.0), ("crate", 1.4, 0.7)], "barrow": [("wood", 2.0, 3.0), ("crate", 1.4, 0.7)],
         "ore": [("stone", 4.0, 1.2)], "anvil": [("stone", 4.0, 1.2), ("iron", 0.8, 0.8)],
         "bellows": [("hide", 1.4, 1.4), ("wood", 2.0, 3.0)], "furnace": [("rw_clay", 3.0, 1.8), ("iron", 0.8, 0.8)],
         "forge": [("trim", 2.0, 3.0), ("ember", 0.6, 0.6), ("iron", 0.8, 0.8)],
         "trough": [("stone", 4.0, 1.2), ("iron", 0.8, 0.8)], "shields": [("hide", 1.4, 1.4), ("wood", 2.0, 3.0)],
         "hide_rack": [("hide", 1.4, 1.4), ("wood", 2.0, 3.0)], "dummy": [("wood", 2.0, 3.0), ("thatch", 2.0, 1.0)],
         "weigh": [("wood", 2.0, 3.0), ("iron", 0.8, 0.8)], "boat": [("planks", 3.2, 1.6), ("wood", 2.0, 3.0)],
         "fish_rack": [("wood", 2.0, 3.0), ("hide", 1.4, 1.4)], "wheel": [("wood", 2.0, 3.0)]}


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


def _block_openings(bays, door, h, size=(1.1, 2.1), sill=None):
    out = []
    for u in bays:
        if door is not None and abs(u - door) < 0.01:
            out.append((u - size[0] / 2, 0.0, u + size[0] / 2, min(size[1], h - 0.5)))
        else:
            lo, hi = (1.2, min(1.9, h - 0.6)) if h >= 2.4 else (h * 0.35, h * 0.72)   # a low upper room
            if sill is not None:                              # high on a tower
                lo, hi = h * sill, h * sill + 1.1
            out.append((u - 0.3, lo, u + 0.3, hi))
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
                        "sides": 10 if p.get("big") else 8, "mass": p.get("mass")})
        elif k == "block":
            z1 = z0 + p["h"] + p.get("parapet", 0.0) + (0.3 if p.get("merlons") else 0.0)
            shape = {"shape": "rect", "x0": p["x0"], "y0": p["y0"], "x1": p["x1"], "y1": p["y1"], "z0": z0,
                     "z1": z1, "name": name, "mass": p.get("mass")}
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
            n = piece.get("n", 12)
            start = len(b.faces)
            if piece.get("belly"):                         # a round body, a short neck, a rim
                prof, v = ((0.5, 0.0), (0.9, 0.18), (1.0, 0.42), (0.86, 0.66), (0.5, 0.82), (0.45, 0.9), (0.6, 1.0)), 0.0
                for (ra, za), (rc, zc) in zip(prof, prof[1:]):
                    b.frustum(x, y, r * ra, r * rc, z + h * za, z + h * zc, n, "pot", v0=v)
                    v += math.hypot(r * (rc - ra), h * (zc - za))
            else:
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
        elif k == "pier":
            _pier(b, piece)
            at = (piece["foot"][0], piece["foot"][2], piece["h"])
        elif k == "door_frame":
            _door_frame(b, piece)
            at = (piece["x"], piece["y"], piece["h"])
        elif k == "mast":
            x, y, z, r = piece["x"], piece["y"], piece["z"], 0.05
            b.box(x - r, x + r, y - r, y + r, z, z + piece["h"], "frame", "frame")
            at = (x, y, z + piece["h"])
        elif k == "banner":
            if medium:
                _banner(b, piece)
            at = (piece["x"], piece["y"], piece["z1"])
        elif k == "spouts":
            if medium:
                for sx, sy, f in piece["at"]:
                    _spout(b, sx, sy, piece["z"], f)
            at = (0.0, 0.0, piece["z"])
        elif k == "hatch":
            if medium:
                x, y, z = piece["x"], piece["y"], piece["z"]
                b.box(x - 0.5, x + 0.5, y - 0.4, y + 0.4, z, z + 0.32, "trim", "planks", skip=())
                b.log(x + 0.5, y - 0.42, x + 0.5, y + 0.42, z + 0.42, 0.04, 4, "wood")
            at = (piece["x"], piece["y"], piece["z"])
        elif k == "canopy":
            if medium and piece.get("cloth", True):
                b.draped_cloth(piece["x0"], piece["x1"], piece["y0"], piece["y1"], piece["z_hi"], piece["z_lo"],
                               "cloth", "wood", slope=piece.get("slope", "-y"), rafters=piece.get("rafters", 0),
                               z_base=piece.get("z", 0.0), scallops=piece.get("scallops", True),
                               nu=piece.get("nu", 5), nv=piece.get("nv", 3), post=piece.get("post", 0.07),
                               on_wall=piece.get("on_wall", False))
            else:
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
        elif k == "shed":
            if medium:
                b.timber_roof(piece["x0"], piece["x1"], piece["y0"], piece["y1"], piece["z_hi"], piece["z_lo"], "planks",
                              "wood", slope=piece.get("slope", "-y"), rafters=piece.get("rafters", 4),
                              z_base=piece.get("z", 0.0), posts=piece.get("posts", (True, True)),
                              boards=piece.get("boards", True))
            else:
                b.canopy(piece["x0"], piece["x1"], piece["y0"], piece["y1"], piece["z_hi"], piece["z_lo"],
                         "planks", "wood", slope=piece.get("slope", "-y"))
            at = (piece["x0"], piece["y0"], piece["z_hi"])
        elif k == "stairs":
            _stairs(b, piece, medium)
            at = (piece["x"], piece["y"], piece["z1"])
        elif k == "lookout":
            _lookout(b, piece, medium)
            at = (piece["x"], piece["y"], piece["z"] + 1.0)
        elif k == "field":
            _field(b, piece, medium)
            at = (piece["x0"], piece["y0"], 0.3)
        elif k == "plot":
            _plot(b, piece, medium)
            at = (0.0, 0.0, 1.4)
        elif k == "ground":
            _ground(b, piece, medium)
            at = (0.0, 0.0, piece["h"])
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
            tiers = 6 if r >= 2.0 else (5 if r >= 1.3 else 4)
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
        top = b.dome(x, y, r, z1, p["roof_h"], n, "dome", rings=6 if medium else 2)
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
        real = [o for o in spec["openings"] if o[1] == 0.0 or not p.get("painted")]
        if medium and real:
            b.wall(origin, ua, length, h, region, real)
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
                          parapet_region=p.get("coping", "parapet") if p.get("parapet") else None,
                          merlons=(p.get("merlons", 0.0) if medium else 0.0), open_sides=open_sides)
    if medium and p.get("sahel", True) and roof != "thatch" and not p.get("plain"):
        _buttresses(b, p, z0, h, top)
    if p.get("pinnacles"):                                 # finials on the parapet's corners
        i = 0.14
        spots = [(x0 + i, y0 + i), (x1 - i, y0 + i), (x1 - i, y1 - i), (x0 + i, y1 - i)]
        if medium and x1 - x0 > 5.0:                       # and halfway along a long side
            spots += [((x0 + x1) / 2, y0 + i), ((x0 + x1) / 2, y1 - i)]
        for px, py in spots:
            if ("-y" in open_sides and py < y0 + 1.0) or ("+y" in open_sides and py > y1 - 1.0) or (
                    "-x" in open_sides and px < x0 + 1.0) or ("+x" in open_sides and px > x1 - 1.0):
                continue
            step = medium and p.get("pinnacles") == "stepped"
            if step:                                       # two steps, then the point
                b.box(px - 0.2, px + 0.2, py - 0.2, py + 0.2, top, top + 0.2, "parapet", "parapet")
                b.box(px - 0.13, px + 0.13, py - 0.13, py + 0.13, top + 0.2, top + 0.42, "parapet", "parapet", skip=("top",))
                b.pyramid(px - 0.13, px + 0.13, py - 0.13, py + 0.13, top + 0.42, 0.3, "parapet")
            else:
                b.box(px - 0.17, px + 0.17, py - 0.17, py + 0.17, top, top + 0.3, "parapet", "parapet", skip=("top",))
                b.pyramid(px - 0.17, px + 0.17, py - 0.17, py + 0.17, top + 0.3, 0.32, "parapet")
    if medium and p.get("beams"):                          # toron: beam ends on the front and sides
        zb = z0 + h - 0.45
        # along the sides they stop short of a joined end
        # (off the pilasters' spacing, or a beam's side falls flush on a pilaster's)
        a0, a1 = y0 + (1.2 if "-y" in open_sides else 0.337), y1 - (1.2 if "+y" in open_sides else 0.3)
        c0, c1 = x0 + (1.2 if "-x" in open_sides else 0.337), x1 - (1.2 if "+x" in open_sides else 0.3)
        gap = p.get("beam_gap", 0.9)
        ln, sz = (0.15, 0.11) if p.get("painted") else (0.35, 0.14)
        sides = p["beams"] if isinstance(p["beams"], tuple) else ("-y", "-x", "+x")
        if "-y" not in open_sides and "-y" in sides:
            b.beam_ends("-y", y0, c0, c1, zb, max(3, int((c1 - c0) / gap)), ln, "wood", size=sz)
        if "-x" not in open_sides and "-x" in sides:
            b.beam_ends("-x", x0, a0, a1, zb, max(2, int((a1 - a0) / gap)), ln, "wood", size=sz)
        if "+x" not in open_sides and "+x" in sides:
            b.beam_ends("+x", x1, a0, a1, zb, max(2, int((a1 - a0) / gap)), ln, "wood", size=sz)
        if "+y" in sides:                                  # few at the back, where they cost and show least
            b.beam_ends("+y", y1, c0, c1, zb, max(2, int((c1 - c0) / (gap * 1.7))), ln, "wood", size=sz)
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


def _lintel(b, face, origin, u0, u1, zt, zs):
    """A timber over a window and a sill under it, standing out of the wall."""
    ox, oy = origin[0], origin[1]
    d = 0.1
    for z0, z1, r in ((zt + 0.14, zt + 0.26, "wood"), (zs - 0.14, zs - 0.06, "step")):
        if face == "front":
            b.box(ox + u0 - 0.16, ox + u1 + 0.16, oy - d, oy, z0, z1, r, r, skip=("+y",))
        elif face == "back":
            b.box(ox - u1 - 0.16, ox - u0 + 0.16, oy, oy + d, z0, z1, r, r, skip=("-y",))
        elif face == "left":
            b.box(ox - d, ox, oy - u1 - 0.16, oy - u0 + 0.16, z0, z1, r, r, skip=("+x",))
        else:
            b.box(ox, ox + d, oy + u0 - 0.16, oy + u1 + 0.16, z0, z1, r, r, skip=("-x",))


def _pier(b, p):
    """A pier over a corner of the walls, `foot` and `top` both (x0, x1, y0, y1), the walls lying
    the way `into` says, (sx, sy). It leans into both walls until little stands out, a thin cap
    climbs from its edge into them, and a narrow chamfer down its outer corner divides it, the
    one line that says what it is. Its sides share one painted side, the chamfer has its own."""
    sx, sy = p["into"]
    tx0, tx1, ty0, ty1 = p["top"]
    z0, z1 = p.get("z", 0.0), p.get("z", 0.0) + p["h"]
    outer = {(1, 1): 0, (-1, 1): 1, (-1, -1): 2, (1, -1): 3}[(sx, sy)]    # the corner away from the walls
    rise = 0.09

    def ring(rect, cut):
        """The rectangle's corners in order, the outer one cut off; which of them are the chamfer."""
        x0, x1, y0, y1 = rect
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        pts, tags = [], []
        for i, (x, y) in enumerate(corners):
            if i != outer:
                pts.append((x, y))
                tags.append(False)
                continue
            for qx, qy in (corners[i - 1], corners[(i + 1) % 4]):
                ln = math.hypot(qx - x, qy - y)
                pts.append((x + (qx - x) / ln * cut, y + (qy - y) / ln * cut))
                tags.append(True)
        return pts, tags

    def cap(x, y):
        ox, oy = tx0 if sx > 0 else tx1, ty0 if sy > 0 else ty1
        return z1 + rise * (abs(x - ox) / (tx1 - tx0) + abs(y - oy) / (ty1 - ty0))

    foot, tags = ring(p["foot"], p.get("chamfer", 0.14))
    top = [(x, y, cap(x, y)) for x, y in ring(p["top"], p.get("chamfer", 0.14) * 0.55)[0]]
    w, a, c, h, lane = PIER_FACE
    cx, cy = sum(q[0] for q in foot) / len(foot), sum(q[1] for q in foot) / len(foot)
    for i, q in enumerate(foot):
        j = (i + 1) % len(foot)
        mx, my = (q[0] + foot[j][0]) / 2 - cx, (q[1] + foot[j][1]) / 2 - cy
        if tags[i] and tags[j]:
            u, uvs = lane, ((0.0, 0.0), (0.3, 0.0), (0.24, h), (0.06, h))
        else:
            u, uvs = 0.0, ((0.0, 0.0), (w, 0.0), (c, h), (a, h))
        b.facing([(*q, z0), (*foot[j], z0), top[j], top[i]], [(u + e, f) for e, f in uvs], "pier", (mx, my, 0.1))
    b.face_out(top, "pier_cap", (0.0, 0.0, 1.0))


def _door_frame(b, p):
    """Posts and a lintel round the door, standing a little out of a wall that looks -Y."""
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    t, out = 0.13, 0.08
    for x0, x1, z0, z1 in ((x - w / 2 - t, x - w / 2, 0.0, h), (x + w / 2, x + w / 2 + t, 0.0, h),
                           (x - w / 2 - t, x + w / 2 + t, h, h + t)):
        b.box(x0, x1, y - out, y, z0, z1, "frame", "frame", skip=("+y",) if z0 else ("+y", "top"))


def _banner(b, p):
    """A cloth hanging from a rod on a wall that looks -Y, with a slight swing."""
    x, y, w, z1, h = p["x"], p["y"], p["w"], p["z1"], p["h"]
    n = 5
    for j in range(n):
        s0, s1 = j / n, (j + 1) / n
        o0, o1 = 0.04 * (j % 2), 0.04 * ((j + 1) % 2)
        b.facing([(x + w * s0, y - o0, z1 - h), (x + w * s1, y - o1, z1 - h), (x + w * s1, y - o1, z1), (x + w * s0, y - o0, z1)],
                 [(w * s0, 0.0), (w * s1, 0.0), (w * s1, h), (w * s0, h)], "banner", (0.0, -1.0, 0.0), smooth=True)
    b.log(x - 0.12, y - 0.06, x + w + 0.12, y - 0.06, z1 + 0.03, 0.025, 4, "wood")


def _spout(b, x, y, z, face):
    """A wooden waterspout through a parapet."""
    L, w = 0.5, 0.07
    if face == "-y":
        b.box(x - w, x + w, y - L, y, z, z + 0.1, "wood", "wood", skip=("+y",))
    elif face == "+y":
        b.box(x - w, x + w, y, y + L, z, z + 0.1, "wood", "wood", skip=("-y",))
    elif face == "-x":
        b.box(x - L, x, y - w, y + w, z, z + 0.1, "wood", "wood", skip=("+x",))
    else:
        b.box(x, x + L, y - w, y + w, z, z + 0.1, "wood", "wood", skip=("-x",))


def _stairs(b, p, medium):
    """Earthen stairs up a wall: `n` steps from (x, y), rising in `dir` to z1, `w` wide."""
    x, y, w, z1, n, d = p["x"], p["y"], p["w"], p["z1"], p.get("n", 7) if medium else 3, p.get("dir", "+x")
    run = p.get("run", 2.8) / n
    r, zb = p.get("region", "trim"), p.get("z", 0.0)
    for k in range(n):
        a, c, z = k * run, (k + 1) * run, zb + z1 * (k + 1) / n
        if d == "+x":
            b.box(x + a, x + c, y - w / 2, y + w / 2, zb, z, r, r, skip=() if k == n - 1 else ("+x",))
        elif d == "-x":
            b.box(x - c, x - a, y - w / 2, y + w / 2, zb, z, r, r, skip=() if k == n - 1 else ("-x",))
        elif d == "+y":
            b.box(x - w / 2, x + w / 2, y + a, y + c, zb, z, r, r, skip=() if k == n - 1 else ("+y",))
        else:
            b.box(x - w / 2, x + w / 2, y - c, y - a, zb, z, r, r, skip=() if k == n - 1 else ("-y",))


def _lookout(b, p, medium):
    """A watch platform on four posts, with a rail and a ladder."""
    x, y, w, z = p["x"], p["y"], p["w"], p["z"]
    h = w / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box(x + sx * h - 0.07, x + sx * h + 0.07, y + sy * h - 0.07, y + sy * h + 0.07, 0.0, z + 0.9, "wood", "wood")
    b.box(x - h - 0.12, x + h + 0.12, y - h - 0.12, y + h + 0.12, z - 0.12, z, "planks", "planks")
    if medium:
        for (ax, ay, cx, cy) in ((x - h, y - h, x + h, y - h), (x - h, y + h, x + h, y + h),
                                 (x - h, y - h, x - h, y + h), (x + h, y - h, x + h, y + h)):
            b.log(ax, ay, cx, cy, z + 0.75, 0.035, 4, "wood")
        lx, ly = x - 0.25, y - h - 0.24
        for rx in (lx, lx + 0.45):
            b.box(rx, rx + 0.05, ly, ly + 0.05, 0.0, z, "wood", "wood")
        for k in range(1, int(z / 0.4)):
            b.box(lx + 0.05, lx + 0.45, ly + 0.005, ly + 0.045, k * 0.4, k * 0.4 + 0.04, "wood", "wood")


def _barrel(b, x, y, r, h, z=0.0):
    b.frustum(x, y, r * 0.8, r, z, z + h / 2, 8, "barrel")
    b.frustum(x, y, r, r * 0.8, z + h / 2, z + h, 8, "barrel", v0=h / 2)
    b.disc(x, y, r * 0.8, z + h, 8, "crate")


def _prop(b, p):
    k = p["kind"]
    x, y = p.get("x", 0.0), p.get("y", 0.0)
    if k == "crate":                                       # a crate, with a smaller one on it
        s = p.get("s", 0.32)
        b.box(x - s, x + s, y - s, y + s, 0.0, 2 * s, "crate", "crate")
        if p.get("stacked"):
            t = s * 0.72
            b.box(x - t + 0.05, x + t + 0.05, y - t, y + t, 2 * s, 2 * s + 2 * t, "crate", "crate", skip=("bottom",))
    elif k == "barrel":
        _barrel(b, x, y, p.get("r", 0.26), p.get("h", 0.72))
    elif k == "barrow":                                    # a wooden barrow with its load
        b.box(x - 0.45, x + 0.35, y - 0.28, y + 0.28, 0.3, 0.6, "crate", "crate")
        b.log(x + 0.5, y - 0.3, x + 0.5, y + 0.3, 0.2, 0.2, 8, "wood")
        for py in (y - 0.22, y + 0.22):
            b.log(x - 0.95, py, x + 0.45, py, 0.34, 0.03, 4, "wood")
    elif k == "ore":                                       # a heap of broken ore
        for dx, dy, r, h in ((0.0, 0.0, 0.55, 0.42), (0.42, 0.18, 0.3, 0.26), (-0.36, 0.24, 0.26, 0.2)):
            b.frustum(x + dx, y + dy, r, r * 0.25, 0.0, h, 6, "stone")
            b.disc(x + dx, y + dy, r * 0.25, h, 6, "stone")
    elif k == "anvil":                                     # iron on a stump of stone
        b.box(x - 0.2, x + 0.2, y - 0.16, y + 0.16, 0.0, 0.42, "stone", "stone")
        b.box(x - 0.3, x + 0.3, y - 0.09, y + 0.09, 0.42, 0.56, "iron", "iron", skip=("bottom",))
    elif k == "bellows":                                   # two skin bags and a clay pipe
        for dx in (-0.2, 0.2):
            b.frustum(x + dx, y, 0.16, 0.2, 0.0, 0.2, 6, "hide")
            b.frustum(x + dx, y, 0.2, 0.08, 0.2, 0.32, 6, "hide")
            b.disc(x + dx, y, 0.08, 0.32, 6, "hide")
        d = p.get("to", (0.0, 0.8))
        b.log(x, y + 0.1, x + d[0], y + d[1], 0.1, 0.04, 4, "wood")
    elif k == "furnace":                                   # a clay shaft furnace, as iron was smelted
        h = p.get("h", 1.5)
        b.frustum(x, y, 0.58, 0.3, 0.0, h, 8, "rw_clay")
        b.disc(x, y, 0.3, h, 8, "iron")
        b.box(x - 0.17, x + 0.17, y - 0.6, y - 0.44, 0.0, 0.34, "iron", "iron")
    elif k == "forge":                                     # a hearth with a tapering chimney
        b.box(x - 0.8, x + 0.8, y - 0.6, y + 0.6, 0.0, 0.62, "trim", "trim")
        b.frustum(x, y + 0.1, 0.6, 0.24, 0.62, p.get("h", 5.0), 4, "trim", phase=math.pi / 4)
        b.disc(x, y + 0.1, 0.24, p.get("h", 5.0), 4, "iron", phase=math.pi / 4)
        b.box(x - 0.42, x + 0.42, y - 0.66, y - 0.6, 0.2, 0.56, "ember", "ember", skip=("+y",))
    elif k == "trough":                                    # the quenching trough
        w = p.get("w", 0.6)
        b.box(x - w, x + w, y - 0.24, y + 0.24, 0.0, 0.42, "stone", "iron")
    elif k == "shields":                                   # shields of hide on a rail
        n, a, c = p.get("n", 3), p.get("a", 0.26), p.get("c", 0.42)
        w = 0.34 * n
        for px in (x - w, x + w):
            b.box(px - 0.04, px + 0.04, y - 0.04, y + 0.04, 0.0, 1.3, "wood", "wood")
        b.log(x - w, y - 0.05, x + w, y - 0.05, 1.2, 0.03, 4, "wood")
        for j in range(n):
            sx = x - w + 2 * w * (j + 0.5) / n
            pts = [(sx + a * math.cos(2 * math.pi * i / 10), y - 0.09, 0.8 + c * math.sin(2 * math.pi * i / 10))
                   for i in range(10)]
            b.face_out(pts, "hide", (0.0, -1.0, 0.0))
    elif k == "hide_rack":                                 # a skin stretched to dry
        for px in (x - 0.55, x + 0.55):
            b.box(px - 0.04, px + 0.04, y - 0.04, y + 0.04, 0.0, 1.5, "wood", "wood")
        b.log(x - 0.6, y, x + 0.6, y, 1.42, 0.035, 4, "wood")
        b.face_out([(x - 0.45, y - 0.05, 0.42), (x + 0.45, y - 0.05, 0.42), (x + 0.5, y - 0.05, 1.38),
                    (x - 0.5, y - 0.05, 1.38)], "hide", (0.0, -1.0, 0.0))
    elif k == "dummy":                                     # a training post
        b.box(x - 0.06, x + 0.06, y - 0.06, y + 0.06, 0.0, 1.5, "wood", "wood")
        b.log(x - 0.5, y, x + 0.5, y, 1.15, 0.04, 4, "wood")
        b.frustum(x, y, 0.16, 0.2, 0.75, 1.1, 6, "thatch")
        b.frustum(x, y, 0.15, 0.1, 1.5, 1.72, 6, "thatch")
        b.disc(x, y, 0.1, 1.72, 6, "thatch")
    elif k == "weigh":                                     # the customs' beam scale
        for dx in (-0.45, 0.45):
            b.box(x + dx - 0.05, x + dx + 0.05, y - 0.05, y + 0.05, 0.0, 1.9, "wood", "wood")
        b.log(x - 0.58, y, x + 0.58, y, 1.85, 0.05, 6, "wood")
        b.log(x - 0.7, y - 0.1, x + 0.7, y - 0.1, 1.5, 0.03, 4, "iron")
        for dx in (-0.6, 0.6):
            b.box(x + dx - 0.22, x + dx + 0.22, y - 0.32, y + 0.12, 0.72, 0.8, "wood", "wood")
            b.box(x + dx - 0.01, x + dx + 0.01, y - 0.11, y - 0.09, 0.8, 1.48, "iron", "iron")
    elif k == "boat":                                      # a dugout hauled out and turned over
        L, w, h = p.get("length", 3.0), p.get("w", 0.75), 0.42
        st = [(-L / 2, 0.08, 0.1), (-L / 4, w / 2, h), (L / 4, w / 2, h), (L / 2, 0.08, 0.1)]
        for (ax, aw, ah), (cx, cw, ch) in zip(st, st[1:]):
            b.face_out([(x + ax, y - aw, 0.0), (x + cx, y - cw, 0.0), (x + cx, y, ch), (x + ax, y, ah)], "planks",
                       (0.0, -1.0, 1.0))
            b.face_out([(x + cx, y + cw, 0.0), (x + ax, y + aw, 0.0), (x + ax, y, ah), (x + cx, y, ch)], "planks",
                       (0.0, 1.0, 1.0))
        for ex, nx in ((-L / 2, -1.0), (L / 2, 1.0)):
            b.face_out([(x + ex, y - 0.08, 0.0), (x + ex, y + 0.08, 0.0), (x + ex, y, 0.1)], "planks", (nx, 0.0, 0.0))
    elif k == "fish_rack":                                 # fish drying on a line
        for px in (x - 0.8, x + 0.8):
            b.box(px - 0.04, px + 0.04, y - 0.04, y + 0.04, 0.0, 1.5, "wood", "wood")
        b.log(x - 0.8, y, x + 0.8, y, 1.42, 0.025, 4, "wood")
        for j in range(5):
            fx = x - 0.56 + 0.28 * j
            b.face_out([(fx - 0.06, y - 0.03, 1.38), (fx + 0.06, y - 0.03, 1.38), (fx, y - 0.03, 0.92)], "hide",
                       (0.0, -1.0, 0.0))
    elif k == "wheel":                                     # a cartwheel waiting for its axle
        b.log(x, y - 0.05, x, y + 0.05, p.get("r", 0.42), p.get("r", 0.42), 8, "wood")
    elif k == "balcony":                                     # a gallery on posts in front of a wall at -Y
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
    mat = p.get("material", "stone")
    ends = set()
    for i, (a, c) in enumerate(zip(pts, pts[1:])):
        if p.get("gap") is not None and i == p["gap"]:
            continue
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
        b._panel((a[0] + ux * t / 2, a[1] + uy * t / 2), (c[0] - ux * t / 2, c[1] - uy * t / 2), 0.0, p["h"], t, mat)
        ends.update((a, c))
    h = t / 2 + 0.06
    for px, py in sorted(ends):
        b.box(px - h, px + h, py - h, py + h, 0.0, p["h"] + 0.25, mat, mat)
    if b.medium and p.get("crenels", True):                # merlons along the top
        for i, (a, c) in enumerate(zip(pts, pts[1:])):
            if p.get("gap") is not None and i == p["gap"]:
                continue
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            m = int((L - 0.8) / 0.9)
            for j in range(m):
                f = (0.4 + 0.45 + j * 0.9) / L
                mx, my = a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f
                b.box(mx - 0.2, mx + 0.2, my - 0.2, my + 0.2, p["h"], p["h"] + 0.3, mat, mat)


def _deck(b, p):
    x0, x1, y0, y1, z = p["x0"], p["x1"], p["y0"], p["y1"], p["z"]
    b.box(x0, x1, y0, y1, z - 0.2, z, "wood", "wood")
    nx, ny = max(2, int((x1 - x0) / 2.0) + 1), max(2, int((y1 - y0) / 2.0) + 1)
    for i in range(nx):
        for j in range(ny):
            px = x0 + 0.2 + (x1 - x0 - 0.4) * i / (nx - 1)
            py = y0 + 0.2 + (y1 - y0 - 0.4) * j / (ny - 1)
            b.ring(px, py, 0.12, 0.0, z - 0.2, 6, "wood")


def _ground(b, p, medium):
    """The trodden earth a building stands on: one low terrace with rounded corners and a sloping
    edge that runs into the terrain, so all of it is one place and units walk off it."""
    H, h, out = p["half"], p["h"], 0.45
    c = 0.5                                                # how far the corners are cut
    top = [(H - c, -H), (H, -H + c), (H, H - c), (H - c, H), (-H + c, H), (-H, H - c), (-H, -H + c), (-H + c, -H)]
    k = (H + out) / H
    b.face_out([(x, y, h) for x, y in top], "yard", (0.0, 0.0, 1.0))
    for i in range(8):
        (ax, ay), (cx, cy) = top[i], top[(i + 1) % 8]
        b.face_out([(ax, ay, h), (ax * k, ay * k, 0.0), (cx * k, cy * k, 0.0), (cx, cy, h)], "yard",
                   (ax + cx, ay + cy, 1.0))


def _leaf(b, x, y, ang, L, droop, w):
    """A leaf: it rises from (x, y), arches and falls over, a narrow closed blade of 3 sides so it
    shows from every way (no transparency: the alpha is the player colour's)."""
    ca, sa = math.cos(ang), math.sin(ang)
    cross = [(-sa * w, ca * w, 0.0), (sa * w, -ca * w, 0.0), (0.0, 0.0, w)]
    spine = [(0.0, 0.05), (L * 0.5, L * 0.72), (L, L * 0.72 - droop)]
    rings = []
    for j, (d, z) in enumerate(spine[:-1]):
        k = 1.0 - 0.3 * j
        rings.append([(x + ca * d + c[0] * k, y + sa * d + c[1] * k, z + c[2] * k) for c in cross])
    tip = (x + ca * spine[-1][0], y + sa * spine[-1][0], spine[-1][1])
    for j in range(len(rings) - 1):
        for i in range(3):
            a0, a1, c0, c1 = rings[j][i], rings[j][(i + 1) % 3], rings[j + 1][i], rings[j + 1][(i + 1) % 3]
            mx = (a0[0] + a1[0]) / 2 - x - ca * spine[j][0]
            my = (a0[1] + a1[1]) / 2 - y - sa * spine[j][0]
            mz = (a0[2] + a1[2]) / 2 - spine[j][1]
            b.facing([a0, a1, c1, c0], [(0.1 * i, 0.3 * j), (0.1 * (i + 1), 0.3 * j), (0.1 * (i + 1), 0.3 * j + 0.3),
                                        (0.1 * i, 0.3 * j + 0.3)], "crop", (mx, my, mz + 0.01), smooth=True)
    for i in range(3):
        a0, a1 = rings[-1][i], rings[-1][(i + 1) % 3]
        mx, my = (a0[0] + a1[0]) / 2 - tip[0], (a0[1] + a1[1]) / 2 - tip[1]
        b.facing([a0, a1, tip], [(0.1 * i, 0.9), (0.1 * (i + 1), 0.9), (0.1 * i + 0.05, 1.15)], "crop",
                 (mx, my, 0.3), smooth=True)


def _plot(b, p, medium):
    """Worked earth with an uneven edge, and clumps of arching leaves. A stem with its seed head
    stands in each clump; low detail keeps the earth and a stem per clump."""
    r, seed = p["r"], p.get("seed", 1)

    def noise(i, m):
        return ((i * 2654435761 + seed * 97) >> 8) % m

    n = 16 if medium else 8
    rim = []
    for i in range(n):
        a = 2 * math.pi * i / n
        q = r * (0.88 + 0.12 * (noise(i, 100) / 100))
        sq = 1.0 / max(abs(math.cos(a)), abs(math.sin(a)))     # a rough square, the way a plot is hoed
        rim.append((q * min(sq, 1.22) * math.cos(a), q * min(sq, 1.22) * math.sin(a)))
    b.face_out([(x, y, 0.1) for x, y in rim], "field", (0.0, 0.0, 1.0))
    for i in range(n):
        (ax, ay), (cx, cy) = rim[i], rim[(i + 1) % n]
        b.face_out([(ax, ay, 0.1), (ax * 1.05, ay * 1.05, 0.0), (cx * 1.05, cy * 1.05, 0.0), (cx, cy, 0.1)], "field",
                   (ax + cx, ay + cy, 0.5))
    tall = 1.5 if p["crop"] == "sorghum" else 1.25
    grid = 5 if medium else 3
    step = 2 * r * 0.78 / grid
    for ix in range(grid):
        for iy in range(grid):
            k = ix * grid + iy
            x = -r * 0.78 + step * (ix + 0.5) + (noise(k * 3 + 1, 50) / 100 - 0.25) * step * 0.5
            y = -r * 0.78 + step * (iy + 0.5) + (noise(k * 5 + 2, 50) / 100 - 0.25) * step * 0.5
            h = tall * (0.8 + 0.3 * noise(k * 7 + 3, 100) / 100)
            b.frustum(x, y, 0.05, 0.015, 0.08, 0.08 + h, 3, "crop")
            b.pyramid(x - 0.05, x + 0.05, y - 0.05, y + 0.05, 0.08 + h - 0.22, 0.26, "crop_head")
            if medium:
                leaves = 3
                for j in range(leaves):
                    a = 2 * math.pi * (j + noise(k + j, 100) / 100) / leaves + k
                    _leaf(b, x, y, a, 0.55 + 0.25 * noise(k * 11 + j, 100) / 100, 0.32, 0.028)


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
