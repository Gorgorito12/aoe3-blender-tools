# SPDX-License-Identifier: GPL-3.0-or-later
"""The parts kit every building style is made of: the face list, the atlas and the pieces
(boxes, rings, walls with recessed openings, hipped roofs, arcs, chimneys), as pure data.

A style builds in two phases, because the faces read their region's size from the packed atlas:

    b = Builder(texture_size, medium)
    b.region("front", w, h) ...       # every region first
    b.pack()
    b.box(...), b.wall(...) ...       # then the faces
    return b.finish(params, facades, dims_extra, notes)

Rule: the order of regions and faces is part of the output (the atlas packing sorts regions with a
stable sort, the painter draws in face and region order). A refactor must not reorder calls or
"simplify" an expression; tests/test_golden.py holds the neoclassical presets byte for byte.

Conventions: metres, Z up, the front faces -Y, origin at the centre of the footprint on the ground.
Nothing here imports Blender.
"""
import math
from dataclasses import dataclass, field

from .atlas import Atlas, Region


@dataclass
class Face:
    pts: list                 # [(x, y, z), ...] counter-clockwise seen from outside
    region: str
    uvs: list                 # [(u, v), ...] world metres inside the region
    smooth: bool = False


@dataclass
class Model:
    params: object           # the style's BuildingParams
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
# The builder


class Builder:
    """Regions, atlas, faces and attach points of one building, and the pieces that make it."""

    def __init__(self, texture_size, medium=False):
        self.texture_size = texture_size
        self.medium = medium
        self.regions = []
        self.atlas = None
        self.faces = []
        self.attach = {}

    def region(self, name, world_w, world_h):
        """Declares an atlas region (phase 1). Order matters: see the module's rule."""
        if self.atlas is not None:
            raise RuntimeError("region() after pack()")
        if any(r.name == name for r in self.regions):
            raise ValueError(f"region {name!r} declared twice")
        self.regions.append(Region(name, world_w, world_h))

    def pack(self):
        """Packs the atlas at twice the final texture size (the painter filters it down)."""
        self.atlas = Atlas(2 * self.texture_size, self.regions)
        return self.atlas

    def face_auto(self, pts, region, anchor=None, smooth=False, voff=0.0):
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
        r = self.atlas[region]
        eu, ev = max(c[0] for c in loc), max(c[1] for c in loc)
        k = min(1.0, r.world_w / eu if eu > r.world_w else 1.0, r.world_h / ev if ev > r.world_h else 1.0)
        self.faces.append(Face(list(pts), region, [(u * k, v * k) for u, v in loc], smooth))

    def box(self, x0, x1, y0, y1, z0, z1, side, top, skip=()):
        quads = {
            "-y": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            "+y": [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
            "-x": [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
            "+x": [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            "top": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        }
        for k, pts in quads.items():
            if k not in skip:
                self.face_auto(pts, top if k == "top" else side)

    def ring(self, cx, cy, r, z0, z1, sides, region, per_face=False, smooth=False, phase=0.0):
        ang = [phase + 2 * math.pi * i / sides for i in range(sides + 1)]
        pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in ang]
        seg = 2 * r * math.sin(math.pi / sides)
        reg = self.atlas[region]
        for i in range(sides):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            h = min(z1 - z0, reg.world_h)
            if per_face:
                s = min(seg, reg.world_w)
                uvs = [(0, 0), (s, 0), (s, h), (0, h)]
            else:
                k = min(1.0, reg.world_w / (seg * sides))
                uvs = [(i * seg * k, 0), ((i + 1) * seg * k, 0), ((i + 1) * seg * k, h), (i * seg * k, h)]
            self.faces.append(Face([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], region, uvs, smooth))

    def facing(self, pts, uvs, region, normal, smooth=False):
        """Adds a face, reversing it when its winding does not face `normal`."""
        if _dot(newell(pts), normal) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        self.faces.append(Face(list(pts), region, list(uvs), smooth))

    def wall(self, origin, ua, length, height, region, holes, depth=0.18, uoff=0.0, reveal="reveal"):
        """A wall around its openings (a triangulated polygon with holes, or a grid when the layout
        does not allow it; no T-junctions either way), each opening recessed by
        `depth`: side and sill reveals and a back face that keeps the facade UVs."""
        up = (0.0, 0.0, 1.0)
        out = _cross(ua, up)
        inward = (-out[0], -out[1], -out[2])

        def P(u, v, d=0.0):
            u -= uoff                     # u in the region's coordinates; the wall starts at uoff
            return (origin[0] + ua[0] * u + inward[0] * d, origin[1] + ua[1] * u + inward[1] * d,
                    origin[2] + v)

        holes = [h for h in holes if h[0] >= uoff - 1e-6 and h[2] <= uoff + length + 1e-6]
        tris = wall_triangles(length, height, [(h[0] - uoff, h[1], h[2] - uoff, h[3]) for h in holes])
        if tris is not None:
            for t in tris:
                t = [(u + uoff, v) for u, v in t]
                self.facing([P(u, v) for u, v in t], t, region, out)
        us = sorted({uoff, uoff + length, *[h[0] for h in holes], *[h[2] for h in holes]})
        vs = sorted({0.0, height, *[h[1] for h in holes], *[h[3] for h in holes]})
        for i in range(len(us) - 1) if tris is None else ():
            for j in range(len(vs) - 1):
                cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
                if any(h[0] < cu < h[2] and h[1] < cv < h[3] for h in holes):
                    continue
                q = [(us[i], vs[j]), (us[i + 1], vs[j]), (us[i + 1], vs[j + 1]), (us[i], vs[j + 1])]
                self.facing([P(u, v) for u, v in q], q, region, out)
        for u0, v0, u1, v1 in holes:
            q = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            self.facing([P(u, v, depth) for u, v in q], q, region, out)
            w, h = u1 - u0, v1 - v0
            self.facing([P(u0, v0), P(u0, v0, depth), P(u0, v1, depth), P(u0, v1)],
                        [(0, 0), (depth, 0), (depth, h), (0, h)], reveal, ua)
            self.facing([P(u1, v0), P(u1, v0, depth), P(u1, v1, depth), P(u1, v1)],
                        [(0, 0), (depth, 0), (depth, h), (0, h)], reveal, (-ua[0], -ua[1], -ua[2]))
            if v0 > 1e-6:      # a door's floor is the plinth top: a sill there would z-fight with it
                self.facing([P(u0, v0), P(u1, v0), P(u1, v0, depth), P(u0, v0, depth)],
                            [(0, 0), (w, 0), (w, depth), (0, depth)], reveal, up)
            # no top reveal: it faces down, and the game camera looks from above

    def flat_wall(self, origin, ua, length, height, region, uoff=0.0):
        """A wall as one flat quad (low detail: the openings are only painted)."""
        out = _cross(ua, (0.0, 0.0, 1.0))
        pts = [(origin[0], origin[1], origin[2]), (origin[0] + ua[0] * length, origin[1] + ua[1] * length, origin[2]),
               (origin[0] + ua[0] * length, origin[1] + ua[1] * length, origin[2] + height),
               (origin[0], origin[1], origin[2] + height)]
        self.facing(pts, [(uoff, 0), (uoff + length, 0), (uoff + length, height), (uoff, height)], region, out)

    def hipped_roof(self, cx, cy, hx, hy, z, rp, region="roof"):
        """A hipped roof over the rectangle cx +- hx, cy +- hy at height z (a pyramid if square)."""
        rz = z + rp * min(hx, hy)
        if hx >= hy:
            rh = hx - hy
            a, b = (cx - rh, cy, rz), (cx + rh, cy, rz)
            self.face_auto([(cx - hx, cy - hy, z), (cx + hx, cy - hy, z), b, a], region)
            self.face_auto([(cx + hx, cy + hy, z), (cx - hx, cy + hy, z), a, b], region)
            self.face_auto([(cx - hx, cy + hy, z), (cx - hx, cy - hy, z), a], region)
            self.face_auto([(cx + hx, cy - hy, z), (cx + hx, cy + hy, z), b], region)
        else:
            rh = hy - hx
            a, b = (cx, cy - rh, rz), (cx, cy + rh, rz)
            self.face_auto([(cx - hx, cy - hy, z), (cx + hx, cy - hy, z), a], region)
            self.face_auto([(cx + hx, cy + hy, z), (cx - hx, cy + hy, z), b], region)
            self.face_auto([(cx - hx, cy + hy, z), (cx - hx, cy - hy, z), a, b], region)
            self.face_auto([(cx + hx, cy - hy, z), (cx + hx, cy + hy, z), b, a], region)
        return rz

    @staticmethod
    def arc_pts(cx, cy, r, t0, t1, n):
        return [(cx + r * math.cos(t0 + (t1 - t0) * i / n), cy + r * math.sin(t0 + (t1 - t0) * i / n)) for i in range(n + 1)]

    def arc_band(self, cx, cy, r, t0, t1, n, z0, z1, region, inward=False):
        """Vertical quads along an arc, facing out (or in)."""
        pts = self.arc_pts(cx, cy, r, t0, t1, n)
        reg = self.atlas[region]
        u = 0.0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay)
            u0 = 0.0 if u + seg > reg.world_w else u          # restart along the region when full
            mx, my = (ax + bx) / 2 - cx, (ay + by) / 2 - cy
            nrm = (-mx, -my, 0.0) if inward else (mx, my, 0.0)
            h = min(z1 - z0, reg.world_h)
            self.facing([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)],
                        [(u0, 0), (min(u0 + seg, reg.world_w), 0), (min(u0 + seg, reg.world_w), h), (u0, h)], region, nrm)
            u = u0 + seg

    def chord_cap(self, cx, cy, r, ychord, n, z, region):
        """The part of a half disc (centre cx, cy, bulging to +y) beyond y = ychord, as one face."""
        t = math.asin(max(-1.0, min(1.0, (ychord - cy) / r)))
        pts = self.arc_pts(cx, cy, r, t, math.pi - t, n)
        self.face_auto([(x, y, z) for x, y in pts], region)
        return t

    def chimney(self, cx, cy, foot, top, side="brick", band="white", cap_top="brick"):
        """A chimney stack from `foot` (inside the roof) to `top`, with a band at medium detail
        and a cap."""
        self.box(cx - 0.4, cx + 0.4, cy - 0.4, cy + 0.4, foot, top, side, side, skip=("top",))
        if self.medium:
            self.box(cx - 0.46, cx + 0.46, cy - 0.46, cy + 0.46, top - 0.35, top - 0.2, band, band)
        self.box(cx - 0.5, cx + 0.5, cy - 0.5, cy + 0.5, top, top + 0.2, band, cap_top)

    def finish(self, params, facades, dims_extra=None, notes=None):
        """Recentres the footprint on the origin and returns the Model; dims gets footprint and
        height, then `dims_extra` in its order."""
        faces = self.faces
        attach = self.attach
        xs = [q[0] for f in faces for q in f.pts]
        ys = [q[1] for f in faces for q in f.pts]
        sx, sy = -(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2
        for f in faces:
            f.pts = [(q[0] + sx, q[1] + sy, q[2]) for q in f.pts]
        self.attach = {k: (v[0] + sx, v[1] + sy, v[2]) for k, v in attach.items()}
        dims = {"footprint": (max(xs) - min(xs), max(ys) - min(ys)),
                "height": max(q[2] for f in faces for q in f.pts)}
        dims.update(dims_extra or {})
        return Model(params, faces, self.attach, self.atlas, facades, dims, list(notes or []))
