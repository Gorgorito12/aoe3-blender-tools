# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric low-poly neoclassical building, as pure data.

`build(params)` returns a `Model`: faces (corner points, UVs, smooth flag), attach points, the atlas
and the facade layout the painter needs. Nothing here imports Blender, so the geometry can be
tested on its own.

Conventions: metres, Z up, the front (portico) faces -Y, origin at the centre of the footprint
(steps included) on the ground.
"""
import math
from dataclasses import dataclass, field, replace

from .atlas import Atlas, Region

STOREY_H = 3.1          # one storey of wall
FRIEZE_H = 0.4          # band under the cornice (inside the wall height)
CORNICE_H = 0.4


@dataclass
class BuildingParams:
    name: str = "Building"
    width: float = 14.0             # main block, X
    depth: float = 9.0              # main block, Y
    storeys: int = 2
    plinth: float = 0.8             # ground floor level
    roof_pitch: float = 0.54        # rise / run, same on all four sides (hipped roof)
    bay_spacing: float = 1.8        # target distance between window bays
    side_bays: int = 0              # windows per row on the sides; 0 = from bay_spacing
    portico: bool = True
    columns: int = 4                # even, 2..8
    column_spacing: float = 1.8
    portico_depth: float = 3.3
    cupola: bool = True
    chimneys: int = 1               # 0..2
    detail: str = "LOW"             # LOW (flat walls, ~350 tris) or MEDIUM (~1,200 tris: recessed
                                    # windows, balustrade, profiled cornice, finer columns)
    texture_size: int = 1024        # final size; painted at twice that and filtered down
    seed: int = 1870
    colors: dict = field(default_factory=lambda: {
        "wall": (232, 225, 204), "trim": (243, 240, 231), "roof": (70, 78, 90),
        "glass": (52, 66, 82), "door": (64, 50, 40), "brick": (150, 64, 48),
        "lead": (96, 106, 114), "stone": (206, 202, 192), "plinth": (192, 188, 177),
    })


PRESETS = {
    "WHITE_HOUSE": BuildingParams(name="WhiteHouse", side_bays=3),
    "COURTHOUSE": BuildingParams(name="Courthouse", width=11.0, depth=9.0, storeys=1, columns=4,
                                 column_spacing=1.6, portico_depth=2.8, cupola=True, chimneys=2),
    "CAPITOL": BuildingParams(name="Capitol", width=20.0, depth=12.0, storeys=2, columns=6,
                              column_spacing=1.9, portico_depth=3.6, cupola=True, chimneys=0),
    "MANSION": BuildingParams(name="Mansion", width=12.0, depth=8.0, storeys=2, portico=False,
                              cupola=False, chimneys=2),
}


@dataclass
class Face:
    pts: list                 # [(x, y, z), ...] counter-clockwise seen from outside
    region: str
    uvs: list                 # [(u, v), ...] world metres inside the region
    smooth: bool = False


@dataclass
class Model:
    params: BuildingParams
    faces: list
    attach: dict              # name -> (x, y, z)
    atlas: Atlas
    facades: dict             # region -> {"bays": [...], "door": u or None}
    dims: dict                # computed sizes, for the painter and the stats
    notes: list = field(default_factory=list)   # values the geometry had to change


# --------------------------------------------------------------------------------------------------
# Vector helpers (tuples; no mathutils)

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def newell(pts):
    nx = ny = nz = 0.0
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return _norm((nx, ny, nz))


def clamp_params(p):
    """Returns a copy with values the geometry can build."""
    p = replace(p, colors=dict(p.colors))
    p.width = max(4.0, p.width)
    p.depth = max(4.0, p.depth)
    p.storeys = max(1, min(4, int(p.storeys)))
    p.plinth = max(0.2, min(2.0, p.plinth))
    p.roof_pitch = max(0.15, min(1.5, p.roof_pitch))
    p.bay_spacing = max(1.3, p.bay_spacing)
    p.side_bays = max(0, min(15, int(p.side_bays)))
    p.columns = max(2, min(8, int(p.columns) // 2 * 2))
    p.chimneys = max(0, min(2, int(p.chimneys)))
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "LOW"
    p.texture_size = 1 << int(round(math.log2(max(256, min(4096, p.texture_size)))))
    # the portico must fit the front and stay under the roof (its pediment is buried in the roof)
    eave_x, eave_y = p.width / 2 + 0.3, p.depth / 2 + 0.3
    limit = min(eave_x, eave_y) - 0.15
    while p.columns > 2 and ((p.columns - 1) * p.column_spacing / 2 + 1.05 > limit):
        p.columns -= 2
    max_spacing = 2 * (limit - 1.05) / max(1, p.columns - 1)
    p.column_spacing = max(1.2, min(p.column_spacing, max_spacing))
    return p


# --------------------------------------------------------------------------------------------------
# Wall with rectangular openings: one polygon with holes, triangulated by ear clipping

def _area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _slit_polygon(length, height, holes):
    """The wall outline as one simple polygon (counter-clockwise, u right, v up): each stack of
    openings is joined to the bottom edge and to the opening below it by a zero-width slit. The
    slits only add points on the bottom edge and on the top edges of openings, where no other face
    has an edge (the reveals are on the sides and the sill). None when the layout does not allow
    it (an opening wider than the one below it, or overlapping columns)."""
    holes = sorted(holes, key=lambda h: (h[0], h[1]))
    stacks = []
    for h in sorted(holes, key=lambda h: h[1]):
        for st in stacks:
            top = st[-1]
            if h[0] < top[2] and top[0] < h[2]:             # overlapping columns
                if not (top[0] - 1e-9 <= h[0] <= top[2] + 1e-9) or h[1] < top[3] - 1e-9:
                    return None
                st.append(h)
                break
        else:
            stacks.append([h])
    stacks.sort(key=lambda st: st[0][0])
    for a, b in zip(stacks, stacks[1:]):
        if max(x[2] for x in a) > min(x[0] for x in b) - 1e-9:
            return None

    def walk(st, i):
        u0, v0, u1, v1 = st[i]
        seq = [(u0, v0), (u0, v1)]
        if i + 1 < len(st):
            t = (st[i + 1][0], v1)
            seq += [t] + walk(st, i + 1) + [t]
        seq += [(u1, v1), (u1, v0), (u0, v0)]
        return seq

    poly = [(0.0, 0.0)]
    for st in stacks:
        b = (st[0][0], 0.0)
        poly += [b] + walk(st, 0) + [b]
    poly += [(length, 0.0), (length, height), (0.0, height)]
    out = []
    for q in poly:                                         # drop consecutive duplicates
        if not out or abs(out[-1][0] - q[0]) > 1e-9 or abs(out[-1][1] - q[1]) > 1e-9:
            out.append(q)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def _ear_clip(poly):
    """Triangles (index triples into poly) of a simple counter-clockwise polygon that may touch
    itself along zero-width slits. None if it gets stuck."""
    idx = list(range(len(poly)))
    tris = []

    def same(a, b):
        return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9

    def inside(p, a, b, c):
        return _area2(a, b, p) >= -1e-12 and _area2(b, c, p) >= -1e-12 and _area2(c, a, p) >= -1e-12

    guard = 0
    while len(idx) > 3:
        guard += 1
        if guard > 20000:
            return None
        n = len(idx)
        found = False
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if _area2(a, b, c) <= 1e-12:
                continue
            blocked = False
            for j in idx:
                q = poly[j]
                if j in (i0, i1, i2) or same(q, a) or same(q, b) or same(q, c):
                    continue
                if inside(q, a, b, c):
                    blocked = True
                    break
            if not blocked:
                tris.append((i0, i1, i2))
                idx.pop(k)
                found = True
                break
        if not found:
            # only straight or slit-doubled corners left at the front: drop one (no area)
            for k in range(n):
                a, b, c = poly[idx[k - 1]], poly[idx[k]], poly[idx[(k + 1) % n]]
                if abs(_area2(a, b, c)) <= 1e-12:
                    idx.pop(k)
                    found = True
                    break
            if not found:
                return None
    if len(idx) == 3 and _area2(*(poly[i] for i in idx)) > 1e-12:
        tris.append(tuple(idx))
    return tris


def wall_triangles(length, height, holes):
    """[(p0, p1, p2)] in wall coordinates covering the wall minus its openings, or None."""
    poly = _slit_polygon(length, height, holes)
    if poly is None:
        return None
    tris = _ear_clip(poly)
    if tris is None:
        return None
    out = [tuple(poly[i] for i in t) for t in tris if abs(_area2(*(poly[i] for i in t))) > 1e-9]
    area = sum(abs(_area2(*t)) / 2 for t in out)
    want = length * height - sum((h[2] - h[0]) * (h[3] - h[1]) for h in holes)
    return out if abs(area - want) < 1e-6 * max(1.0, want) else None


# --------------------------------------------------------------------------------------------------

def build(params):
    p = clamp_params(params)
    W, D = p.width, p.depth
    plinth = p.plinth
    wall_h = p.storeys * STOREY_H
    wall_top = plinth + wall_h
    eave_z = wall_top + CORNICE_H
    ex, ey = W / 2 + 0.3, D / 2 + 0.3
    pitch = p.roof_pitch
    ridge_z = eave_z + pitch * min(ex, ey)
    front_y = -D / 2
    plinth_y = -D / 2 - 0.2

    def roof_z(x, y):
        return eave_z + pitch * max(0.0, min(ex - abs(x), ey - abs(y)))

    # portico
    port_half = (p.columns - 1) * p.column_spacing / 2 + 0.9 if p.portico else 0.0
    ped_half = port_half + 0.15
    port_y = plinth_y - p.portico_depth if p.portico else plinth_y
    col_y = port_y + 0.6
    col_r = 0.34
    ent_bottom = wall_top - 0.4
    ped_apex = eave_z + ped_half * pitch
    ped_back_y = -(ey - ped_half)          # main roof reaches the apex height there
    ped_y = port_y - 0.05

    # steps in front of the portico, or of the door
    n_steps = max(1, int(round(plinth / 0.2)) - 1)
    step_d = 0.6
    step_half = port_half - 0.6 if p.portico else 1.2
    steps_front = port_y - n_steps * step_d

    # cupola
    drum_r = min(0.95, 0.12 * min(W, D))
    medium = p.detail == "MEDIUM"
    cols = [(-(p.columns - 1) / 2 + i) * p.column_spacing for i in range(p.columns)] if p.portico else []

    # facade layout for the painter (u from the left as seen from outside)
    MIN_STEP = 1.45                         # a 1.0 m window plus its frame and a little wall

    def bays(length):
        """An odd number of evenly spaced bays (symmetric, one on the axis), 1.2 m from the corners
        (the quoins), at the spacing closest to bay_spacing."""
        usable = length - 2.4
        if usable < MIN_STEP:
            return [length / 2]
        best = (1e9, 1)
        n = 3
        while usable / (n - 1) >= MIN_STEP:
            score = abs(usable / (n - 1) - p.bay_spacing)
            if score < best[0]:
                best = (score, n)
            n += 2
        n = best[1]
        if n == 1:
            return [length / 2]
        return [1.2 + i * usable / (n - 1) for i in range(n)]

    def side_bay_list():
        if not p.side_bays:
            return bays(D)
        usable = D - 2.4
        n = p.side_bays
        while n > 1 and usable / (n - 1) < MIN_STEP:
            n -= 1
        return [D / 2] if n == 1 or usable <= 0 else [1.2 + i * usable / (n - 1) for i in range(n)]

    if p.portico:
        # behind the portico: one bay between each pair of columns (the middle one is the door);
        # beside it: bays from the portico edge to 1.2 m from the corner
        mids = [W / 2 + (cols[i] + cols[i + 1]) / 2 for i in range(len(cols) - 1)]
        a, b = port_half + 0.25, W / 2 - 1.2
        side = []
        if b - a >= 0:
            n = max(1, int(round((b - a) / p.bay_spacing)) + 1)
            side = [a + i * (b - a) / (n - 1) for i in range(n)] if n > 1 else [(a + b) / 2]
        front_bays = sorted(set(round(u, 3) for u in mids + [W / 2 + s for s in side] + [W / 2 - s for s in side]))
    else:
        front_bays = sorted(set(round(u, 3) for u in bays(W) + [W / 2]))
    facades = {
        "front": {"bays": front_bays, "door": W / 2},
        "back": {"bays": bays(W), "door": None},
        "side": {"bays": side_bay_list(), "door": None},
    }

    # openings (u0, v0, u1, v1) per facade, in the facade's own coordinates; the same rectangles
    # the painter fills with glass and wood, so a recessed opening shows them on its back face
    def openings(spec):
        out = []
        for uc in spec["bays"]:
            for st in range(p.storeys):
                base = st * STOREY_H
                if st == 0 and spec["door"] is not None and abs(uc - spec["door"]) < 0.01:
                    out.append((uc - 0.7, 0.0, uc + 0.7, 2.75))
                elif st == 0:
                    out.append((uc - 0.5, base + 0.8, uc + 0.5, base + 2.7))
                else:
                    out.append((uc - 0.5, base + 0.55, uc + 0.5, base + 2.2))
        return out


    # --- atlas -----------------------------------------------------------------------------------
    roof_w = max(2 * ex, 2 * ey) + 0.2
    roof_h = math.hypot(min(ex, ey), pitch * min(ex, ey)) + 0.2
    if p.portico:
        roof_h = max(roof_h, math.hypot(ped_half, ped_half * pitch) + 0.2)
        roof_w = max(roof_w, abs(ped_back_y - ped_y) + 0.2)
    regions = [
        Region("front", W, wall_h), Region("back", W, wall_h), Region("side", D, wall_h),
        Region("roof", roof_w, roof_h),
        Region("plinth", max(W, D) + 0.8, plinth), Region("trim", max(W, D) + 1.0, 0.8),
        Region("stone", 8.0, 4.0), Region("brick", 4.0, 3.0),
        Region("white", 2.2, 1.6), Region("cupwin", 0.8, 1.6), Region("lead", 7.0, 2.5),
    ]
    if medium:
        regions += [Region("reveal", 1.6, 2.8), Region("balus", max(W, D) + 1.0, 0.95)]
    if p.portico:
        regions += [Region("pedi", 2 * ped_half, ped_apex - eave_z),
                    Region("column", 2 * math.pi * col_r, ent_bottom - 0.3 - plinth)]
    atlas = Atlas(2 * p.texture_size, regions)

    faces = []

    def face_auto(pts, region, anchor=None, smooth=False, voff=0.0):
        n = newell(pts)
        if abs(n[2]) > 0.999:
            ua, va = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        else:
            ua = _norm((-n[1], n[0], 0.0))
            va = _norm(_cross(n, ua))
        loc = [(_dot(q, ua), _dot(q, va)) for q in pts]
        if anchor is None:
            u0, v0 = min(c[0] for c in loc), min(c[1] for c in loc)
        else:
            u0, v0 = _dot(anchor, ua), _dot(anchor, va)
        loc = [(u - u0, v - v0 + voff) for u, v in loc]
        r = atlas[region]
        eu, ev = max(c[0] for c in loc), max(c[1] for c in loc)
        k = min(1.0, r.world_w / eu if eu > r.world_w else 1.0, r.world_h / ev if ev > r.world_h else 1.0)
        faces.append(Face(list(pts), region, [(u * k, v * k) for u, v in loc], smooth))

    def box(x0, x1, y0, y1, z0, z1, side, top, skip=()):
        quads = {
            "-y": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            "+y": [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
            "-x": [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
            "+x": [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            "top": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        }
        for k, pts in quads.items():
            if k not in skip:
                face_auto(pts, top if k == "top" else side)

    def ring(cx, cy, r, z0, z1, sides, region, per_face=False, smooth=False, phase=0.0):
        ang = [phase + 2 * math.pi * i / sides for i in range(sides + 1)]
        pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in ang]
        seg = 2 * r * math.sin(math.pi / sides)
        reg = atlas[region]
        for i in range(sides):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            h = min(z1 - z0, reg.world_h)
            if per_face:
                s = min(seg, reg.world_w)
                uvs = [(0, 0), (s, 0), (s, h), (0, h)]
            else:
                k = min(1.0, reg.world_w / (seg * sides))
                uvs = [(i * seg * k, 0), ((i + 1) * seg * k, 0), ((i + 1) * seg * k, h), (i * seg * k, h)]
            faces.append(Face([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], region, uvs, smooth))

    def facing(pts, uvs, region, normal, smooth=False):
        """Adds a face, reversing it when its winding does not face `normal`."""
        if _dot(newell(pts), normal) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        faces.append(Face(list(pts), region, list(uvs), smooth))

    def wall(origin, ua, length, height, region, holes, depth=0.18):
        """A wall around its openings (a triangulated polygon with holes, or a grid when the layout
        does not allow it; no T-junctions either way), each opening recessed by
        `depth`: side and sill reveals and a back face that keeps the facade UVs."""
        up = (0.0, 0.0, 1.0)
        out = _cross(ua, up)
        inward = (-out[0], -out[1], -out[2])

        def P(u, v, d=0.0):
            return (origin[0] + ua[0] * u + inward[0] * d, origin[1] + ua[1] * u + inward[1] * d,
                    origin[2] + v)

        tris = wall_triangles(length, height, holes)
        if tris is not None:
            for t in tris:
                facing([P(u, v) for u, v in t], list(t), region, out)
        us = sorted({0.0, length, *[h[0] for h in holes], *[h[2] for h in holes]})
        vs = sorted({0.0, height, *[h[1] for h in holes], *[h[3] for h in holes]})
        for i in range(len(us) - 1) if tris is None else ():
            for j in range(len(vs) - 1):
                cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
                if any(h[0] < cu < h[2] and h[1] < cv < h[3] for h in holes):
                    continue
                q = [(us[i], vs[j]), (us[i + 1], vs[j]), (us[i + 1], vs[j + 1]), (us[i], vs[j + 1])]
                facing([P(u, v) for u, v in q], q, region, out)
        for u0, v0, u1, v1 in holes:
            q = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            facing([P(u, v, depth) for u, v in q], q, region, out)
            w, h = u1 - u0, v1 - v0
            facing([P(u0, v0), P(u0, v0, depth), P(u0, v1, depth), P(u0, v1)],
                   [(0, 0), (depth, 0), (depth, h), (0, h)], "reveal", ua)
            facing([P(u1, v0), P(u1, v0, depth), P(u1, v1, depth), P(u1, v1)],
                   [(0, 0), (depth, 0), (depth, h), (0, h)], "reveal", (-ua[0], -ua[1], -ua[2]))
            if v0 > 1e-6:      # a door's floor is the plinth top: a sill there would z-fight with it
                facing([P(u0, v0), P(u1, v0), P(u1, v0, depth), P(u0, v0, depth)],
                       [(0, 0), (w, 0), (w, depth), (0, depth)], "reveal", up)
            # no top reveal: it faces down, and the game camera looks from above

    # main block
    box(-W / 2 - 0.2, W / 2 + 0.2, -D / 2 - 0.2, D / 2 + 0.2, 0, plinth, "plinth", "stone")
    if medium:
        wall((-W / 2, front_y, plinth), (1.0, 0.0, 0.0), W, wall_h, "front", openings(facades["front"]))
        wall((W / 2, D / 2, plinth), (-1.0, 0.0, 0.0), W, wall_h, "back", openings(facades["back"]))
        wall((-W / 2, D / 2, plinth), (0.0, -1.0, 0.0), D, wall_h, "side", openings(facades["side"]))
        wall((W / 2, -D / 2, plinth), (0.0, 1.0, 0.0), D, wall_h, "side", openings(facades["side"]))
        # profiled cornice: a bed moulding, then the corona showing the trim's dentil band
        box(-W / 2 - 0.12, W / 2 + 0.12, -D / 2 - 0.12, D / 2 + 0.12, wall_top, wall_top + 0.18,
            "trim", "trim", skip=("top",))
        for k, pts in {
            "-y": [(-ex, -ey, wall_top + 0.18), (ex, -ey, wall_top + 0.18), (ex, -ey, eave_z), (-ex, -ey, eave_z)],
            "+y": [(ex, ey, wall_top + 0.18), (-ex, ey, wall_top + 0.18), (-ex, ey, eave_z), (ex, ey, eave_z)],
            "-x": [(-ex, ey, wall_top + 0.18), (-ex, -ey, wall_top + 0.18), (-ex, -ey, eave_z), (-ex, ey, eave_z)],
            "+x": [(ex, -ey, wall_top + 0.18), (ex, ey, wall_top + 0.18), (ex, ey, eave_z), (ex, -ey, eave_z)],
        }.items():
            face_auto(pts, "trim", voff=0.44)
    else:
        face_auto([(-W / 2, front_y, plinth), (W / 2, front_y, plinth), (W / 2, front_y, wall_top),
                   (-W / 2, front_y, wall_top)], "front", anchor=(-W / 2, front_y, plinth))
        face_auto([(W / 2, D / 2, plinth), (-W / 2, D / 2, plinth), (-W / 2, D / 2, wall_top),
                   (W / 2, D / 2, wall_top)], "back", anchor=(W / 2, D / 2, plinth))
        face_auto([(-W / 2, D / 2, plinth), (-W / 2, -D / 2, plinth), (-W / 2, -D / 2, wall_top),
                   (-W / 2, D / 2, wall_top)], "side", anchor=(-W / 2, D / 2, plinth))
        face_auto([(W / 2, -D / 2, plinth), (W / 2, D / 2, plinth), (W / 2, D / 2, wall_top),
                   (W / 2, -D / 2, wall_top)], "side", anchor=(W / 2, -D / 2, plinth))
        box(-ex, ex, -ey, ey, wall_top, eave_z, "trim", "trim", skip=("top",))

    # hipped roof (ridge along the longer side; a pyramid when square)
    if ex >= ey:
        rh = ex - ey
        a, b = (-rh, 0.0, ridge_z), (rh, 0.0, ridge_z)
        face_auto([(-ex, -ey, eave_z), (ex, -ey, eave_z), b, a], "roof")
        face_auto([(ex, ey, eave_z), (-ex, ey, eave_z), a, b], "roof")
        face_auto([(-ex, ey, eave_z), (-ex, -ey, eave_z), a], "roof")
        face_auto([(ex, -ey, eave_z), (ex, ey, eave_z), b], "roof")
    else:
        rh = ey - ex
        a, b = (0.0, -rh, ridge_z), (0.0, rh, ridge_z)
        face_auto([(-ex, -ey, eave_z), (ex, -ey, eave_z), a], "roof")
        face_auto([(ex, ey, eave_z), (-ex, ey, eave_z), b], "roof")
        face_auto([(-ex, ey, eave_z), (-ex, -ey, eave_z), a, b], "roof")
        face_auto([(ex, -ey, eave_z), (ex, ey, eave_z), b, a], "roof")

    # balustrade on the cornice: straight segments that never overlap at the corners (the side
    # ones stop at the inner face of the front and back ones), posts at the corners, at the ends
    # beside the pediment and along the long runs
    if medium:
        PH, IN, TH = 0.75, 0.05, 0.25          # height, inset from the eave, thickness
        o_x, o_y, i_x, i_y = ex - IN, ey - IN, ex - IN - TH, ey - IN - TH
        gap = ped_half + 0.25 if p.portico else 0.0
        runs = [(-o_x, o_x, i_y, o_y)]                                   # back
        runs += [(-o_x, -gap, -o_y, -i_y), (gap, o_x, -o_y, -i_y)] if gap else [(-o_x, o_x, -o_y, -i_y)]
        runs += [(-o_x, -i_x, -i_y, i_y), (i_x, o_x, -i_y, i_y)]        # sides
        for x0, x1, y0, y1 in runs:
            if x1 - x0 > 0.01 and y1 - y0 > 0.01:
                box(x0, x1, y0, y1, eave_z, eave_z + PH, "balus", "white")
        posts = [(-ex + 0.2, -ey + 0.2), (ex - 0.2, -ey + 0.2), (-ex + 0.2, ey - 0.2), (ex - 0.2, ey - 0.2)]
        if gap:
            posts += [(-gap, -ey + 0.2), (gap, -ey + 0.2)]
        n_long = max(0, int((2 * ex - 0.4) / 5.0))
        posts += [(-ex + 0.2 + (2 * ex - 0.4) * (i + 1) / (n_long + 1), ey - 0.2) for i in range(n_long)]
        for px, py in posts:
            box(px - 0.2, px + 0.2, py - 0.2, py + 0.2, eave_z, eave_z + PH + 0.15, "white", "white")

    # portico (the platform stops at the plinth front: an overlap would be coplanar with the
    # plinth top and z-fight)
    if p.portico:
        box(-port_half, port_half, port_y, plinth_y, 0, plinth, "plinth", "stone", skip=("+y",))
        col_top = ent_bottom - 0.3
        for cx in cols:
            if medium:      # square plinth and torus, shaft, echinus and abacus
                box(cx - 0.45, cx + 0.45, col_y - 0.45, col_y + 0.45, plinth, plinth + 0.18, "white", "white")
                oct_ = [2 * math.pi * (i + 0.5) / 8 for i in range(8)]
                ring(cx, col_y, 0.42, plinth + 0.18, plinth + 0.3, 8, "white", per_face=True, phase=math.pi / 8)
                faces.append(Face([(cx + 0.42 * math.cos(a), col_y + 0.42 * math.sin(a), plinth + 0.3) for a in oct_],
                                  "white", [(0.9 + 0.42 * math.cos(a), 0.8 + 0.42 * math.sin(a)) for a in oct_]))
                ring(cx, col_y, col_r, plinth + 0.3, ent_bottom - 0.32, 10, "column", smooth=True)
                ring(cx, col_y, 0.43, ent_bottom - 0.32, ent_bottom - 0.16, 8, "white", per_face=True, phase=math.pi / 8)
                box(cx - 0.5, cx + 0.5, col_y - 0.5, col_y + 0.5, ent_bottom - 0.16, ent_bottom, "white", "white",
                    skip=("top",))
            else:
                box(cx - 0.45, cx + 0.45, col_y - 0.45, col_y + 0.45, plinth, plinth + 0.25, "white", "white")
                ring(cx, col_y, col_r, plinth + 0.25, col_top, 10, "column", smooth=True)
                box(cx - 0.48, cx + 0.48, col_y - 0.48, col_y + 0.48, col_top, ent_bottom, "white", "white", skip=("top",))
        box(-port_half, port_half, port_y, front_y, ent_bottom, eave_z, "trim", "trim", skip=("+y", "top"))
        face_auto([(-ped_half, ped_y, eave_z), (ped_half, ped_y, eave_z), (0, ped_y, ped_apex)], "pedi",
                  anchor=(-ped_half, ped_y, eave_z))
        face_auto([(-ped_half, ped_back_y, eave_z), (-ped_half, ped_y, eave_z), (0, ped_y, ped_apex),
                   (0, ped_back_y, ped_apex)], "roof")
        face_auto([(ped_half, ped_y, eave_z), (ped_half, ped_back_y, eave_z), (0, ped_back_y, ped_apex),
                   (0, ped_y, ped_apex)], "roof")
        box(-ped_half, ped_half, ped_y, port_y, eave_z - 0.12, eave_z, "trim", "trim", skip=("+y", "top"))
    for i in range(n_steps):
        y1 = port_y - step_d * i
        h = plinth * (n_steps - i) / (n_steps + 1)
        box(-step_half, step_half, y1 - step_d, y1, 0, h, "stone", "stone",
            skip=("+y", "-x", "+x") if medium else ("+y",))
    if medium:          # cheek walls beside the steps (they hide the steps' ends)
        for sx0, sx1 in ((-step_half - 0.35, -step_half), (step_half, step_half + 0.35)):
            box(sx0, sx1, steps_front, port_y, 0, plinth, "stone", "stone", skip=("+y",))

    # cupola
    attach = {}
    if p.cupola:
        z0 = ridge_z - 0.6
        z1 = ridge_z + 1.0
        ring(0, 0, drum_r, z0, z1, 8, "cupwin", per_face=True, phase=math.pi / 8)
        ring(0, 0, drum_r * 1.18, z1, z1 + 0.15, 8, "white", per_face=True, phase=math.pi / 8)
        dome_r, dome_h, dome_z = drum_r * 1.1, drum_r, z1 + 0.15
        pts = []
        for ang in (0, 25, 50, 72):
            t = math.radians(ang)
            pts.append((dome_r * math.cos(t) if ang else drum_r * 1.18, dome_z + dome_h * math.sin(t)))
        arc = 0.0
        lead = atlas["lead"]
        for j in range(len(pts) - 1):
            (r0, za), (r1, zb) = pts[j], pts[j + 1]
            arc1 = arc + math.hypot(r1 - r0, zb - za)
            for i in range(8):
                a0 = math.pi / 8 + 2 * math.pi * i / 8
                a1 = a0 + 2 * math.pi / 8
                u0, u1 = i * lead.world_w / 8, (i + 1) * lead.world_w / 8
                faces.append(Face([(r0 * math.cos(a0), r0 * math.sin(a0), za), (r0 * math.cos(a1), r0 * math.sin(a1), za),
                                   (r1 * math.cos(a1), r1 * math.sin(a1), zb), (r1 * math.cos(a0), r1 * math.sin(a0), zb)],
                                  "lead", [(u0, arc), (u1, arc), (u1, arc1), (u0, arc1)], True))
            arc = arc1
        lan_r, lan_z = pts[-1]
        ring(0, 0, lan_r, lan_z, lan_z + 0.45, 8, "white", per_face=True, phase=math.pi / 8)
        top = lan_z + 0.45 + 0.75 * drum_r / 0.95
        for i in range(8):
            a0 = math.pi / 8 + 2 * math.pi * i / 8
            a1 = a0 + 2 * math.pi / 8
            zb = lan_z + 0.45
            faces.append(Face([(lan_r * math.cos(a0), lan_r * math.sin(a0), zb), (lan_r * math.cos(a1), lan_r * math.sin(a1), zb),
                               (0, 0, top)], "lead", [(i * 0.4, 0), ((i + 1) * 0.4, 0), ((i + 0.5) * 0.4, 0.8)]))
        attach["flag_attach"] = (0.0, 0.0, top)
    else:
        attach["flag_attach"] = (0.0, 0.0, ridge_z + 0.1)

    # chimneys (their foot is inside the roof)
    for k in range(p.chimneys):
        sx = -1 if k == 0 else 1
        cx, cy = sx * max(1.0, W / 2 - 2.0), D * 0.18
        foot = roof_z(cx, cy) - 0.4
        top = ridge_z + 1.0
        box(cx - 0.4, cx + 0.4, cy - 0.4, cy + 0.4, foot, top, "brick", "brick", skip=("top",))
        if medium:
            box(cx - 0.46, cx + 0.46, cy - 0.46, cy + 0.46, top - 0.35, top - 0.2, "white", "white")
        box(cx - 0.5, cx + 0.5, cy - 0.5, cy + 0.5, top, top + 0.2, "white", "brick")

    # recentre the footprint on the origin
    xs = [q[0] for f in faces for q in f.pts]
    ys = [q[1] for f in faces for q in f.pts]
    sx, sy = -(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2
    for f in faces:
        f.pts = [(q[0] + sx, q[1] + sy, q[2]) for q in f.pts]
    attach = {k: (v[0] + sx, v[1] + sy, v[2]) for k, v in attach.items()}

    dims = {"footprint": (max(xs) - min(xs), max(ys) - min(ys)),
            "height": max(q[2] for f in faces for q in f.pts),
            "wall_h": wall_h, "storeys": p.storeys, "ped_half": ped_half}
    notes = []
    for attr, label in (("columns", "Columns"), ("column_spacing", "Column spacing")):
        want, got = getattr(params, attr), getattr(p, attr)
        if params.portico and abs(want - got) > 1e-6:
            notes.append(f"{label} {want:g} -> {got:g}: the portico must fit the front and its pediment stay under the roof.")
    return Model(p, faces, attach, atlas, facades, dims, notes)
