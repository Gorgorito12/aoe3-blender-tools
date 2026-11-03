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
        if abs(hx - hy) < 1e-9:          # square: four triangles to the apex (a ridge of length 0
            apex = (cx, cy, rz)          # would repeat a corner)
            self.face_auto([(cx - hx, cy - hy, z), (cx + hx, cy - hy, z), apex], region)
            self.face_auto([(cx + hx, cy + hy, z), (cx - hx, cy + hy, z), apex], region)
            self.face_auto([(cx - hx, cy + hy, z), (cx - hx, cy - hy, z), apex], region)
            self.face_auto([(cx + hx, cy - hy, z), (cx + hx, cy + hy, z), apex], region)
        elif hx >= hy:
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

    # ----------------------------------------------------------------------------------------------
    # Pieces for the other styles: gable and shed roofs, ridge caps, dormers, bell gables,
    # arcades, balconies and jetties. Each face is turned to face its outside.

    def face_out(self, pts, region, normal, anchor=None, smooth=False):
        """face_auto, reversing the corners first when they do not face `normal`."""
        if _dot(newell(pts), normal) < 0:
            pts = pts[::-1]
        self.face_auto(list(pts), region, anchor=anchor, smooth=smooth)

    def gable_roof(self, cx, cy, hx, hy, z, pitch, axis="X", region="roof", gable_region=None,
                   overhang=0.0, gables=(True, True), ends=None):
        """A roof with two slopes over the walls cx +- hx, cy +- hy whose tops are at z, the ridge
        along `axis` ("X" or "Y"). The slopes reach `overhang` beyond the walls on every side
        (eaves and verges, lower by pitch x overhang at the eaves); with `gable_region`, the two
        gable triangles close the ends in the wall planes (`gables`: the low and the high end
        along the ridge). `ends` (low, high): where the slopes stop along the ridge instead of
        the walls plus the overhang (a wing's roof running into the main roof). Returns the
        ridge height."""
        if axis == "X":
            run = hy
        else:
            run = hx
        rz = z + pitch * run
        ze = z - pitch * overhang
        o = overhang
        if axis == "X":
            x0, x1 = ends if ends else (cx - hx - o, cx + hx + o)
            self.face_out([(x0, cy - hy - o, ze), (x1, cy - hy - o, ze), (x1, cy, rz), (x0, cy, rz)],
                          region, (0.0, -1.0, 1.0))
            self.face_out([(x1, cy + hy + o, ze), (x0, cy + hy + o, ze), (x0, cy, rz), (x1, cy, rz)],
                          region, (0.0, 1.0, 1.0))
            if gable_region:
                for sx, keep in zip((-1, 1), gables):
                    if not keep:
                        continue
                    x = cx + sx * hx
                    self.face_out([(x, cy - hy, z), (x, cy + hy, z), (x, cy, rz)], gable_region,
                                  (float(sx), 0.0, 0.0), anchor=(x, cy - sx * hy, z))
        else:
            y0, y1 = ends if ends else (cy - hy - o, cy + hy + o)
            self.face_out([(cx - hx - o, y1, ze), (cx - hx - o, y0, ze), (cx, y0, rz), (cx, y1, rz)],
                          region, (-1.0, 0.0, 1.0))
            self.face_out([(cx + hx + o, y0, ze), (cx + hx + o, y1, ze), (cx, y1, rz), (cx, y0, rz)],
                          region, (1.0, 0.0, 1.0))
            if gable_region:
                for sy, keep in zip((-1, 1), gables):
                    if not keep:
                        continue
                    y = cy + sy * hy
                    self.face_out([(cx - hx, y, z), (cx + hx, y, z), (cx, y, rz)], gable_region,
                                  (0.0, float(sy), 0.0), anchor=(cx + sy * hx, y, z))
        return rz

    def shed_roof(self, origin, ua, length, depth, z_top, pitch, region="roof"):
        """A lean-to roof against a wall: from the wall line (origin, along the unit vector ua,
        `length` long) at z_top, sloping down outward (the wall's outside, as for `wall`) over
        `depth`. Returns the height of its low edge."""
        out = _cross(ua, (0.0, 0.0, 1.0))
        zl = z_top - pitch * depth

        def P(u, d, zz):
            return (origin[0] + ua[0] * u + out[0] * d, origin[1] + ua[1] * u + out[1] * d, zz)

        self.face_out([P(0, 0, z_top), P(0, depth, zl), P(length, depth, zl), P(length, 0, z_top)],
                      region, (out[0] * pitch, out[1] * pitch, 1.0))
        return zl

    def ridge_cap(self, a, b, z, region, width=0.2, height=0.12):
        """A capping along a ridge from a to b ((x, y) at the ridge height z, along X or Y): a low
        box whose foot is inside the roof."""
        (ax, ay), (bx, by) = a, b
        w = width / 2
        if abs(ay - by) < 1e-9:
            self.box(min(ax, bx), max(ax, bx), ay - w, ay + w, z - 0.08, z + height, region, region)
        else:
            self.box(ax - w, ax + w, min(ay, by), max(ay, by), z - 0.08, z + height, region, region)

    def dormer(self, x, cy, hy, z, pitch, side, inset, w, h, dpitch=0.8, wall_region="dormer",
               roof_region="roof", cheek_region=None):
        """A gabled dormer on a gable roof whose ridge runs along X at y = cy (the walls at
        cy +- hy, tops at z, slope `pitch`): on the slope facing `side` (-1: -Y, +1: +Y), its front
        wall `inset` metres in from the eave line, `w` wide and `h` high above the roof, centred
        on x. Front wall (the `wall_region`, `w` x `h`, for a painted window), its gable, two
        cheeks and a small roof whose ridge meets the main roof. Returns the dormer's top."""
        s = float(side)
        cheek_region = cheek_region or roof_region
        r_f = hy - inset                               # distance of the front from the ridge line
        zb = z + pitch * inset                         # the main roof at the front
        zt = zb + h
        rz = zt + dpitch * w / 2
        r_b = r_f - h / pitch                          # where the main roof reaches zt
        r_r = r_f - (rz - zb) / pitch                  # where it reaches the dormer's ridge

        def Q(xx, r, zz):
            return (xx, cy + s * r, zz)

        xl, xr = x - w / 2, x + w / 2
        out = (0.0, s, 0.0)
        self.face_out([Q(xl, r_f, zb), Q(xr, r_f, zb), Q(xr, r_f, zt), Q(xl, r_f, zt)], wall_region, out,
                      anchor=Q(xl if s < 0 else xr, r_f, zb))
        self.face_out([Q(xl, r_f, zt), Q(xr, r_f, zt), Q(x, r_f, rz)], cheek_region, out)
        for xx, nx in ((xl, -1.0), (xr, 1.0)):
            self.face_out([Q(xx, r_f, zb), Q(xx, r_f, zt), Q(xx, r_b, zt)], cheek_region, (nx, 0.0, 0.0))
            self.face_out([Q(xx, r_f, zt), Q(x, r_f, rz), Q(x, r_r, rz), Q(xx, r_b, zt)], roof_region,
                          (nx, 0.0, 1.0))
        return rz

    def bell_gable(self, cx, y, z0, w, h, thickness, region, peak=None, side_region=None):
        """A bell gable (espadana): a slab `w` wide and `thickness` thick standing on z0, its front
        in the plane y (facing -Y), `h` high at the sides and `peak` more at the centre. The bells
        and their arches are painted on the front (`region`, w x h + peak). Returns the apex."""
        peak = w * 0.35 if peak is None else peak
        side_region = side_region or region
        x0, x1 = cx - w / 2, cx + w / 2
        yb = y + thickness
        zh, za = z0 + h, z0 + h + peak
        front = [(x0, y, z0), (x1, y, z0), (x1, y, zh), (cx, y, za), (x0, y, zh)]
        self.face_out(front, region, (0.0, -1.0, 0.0), anchor=(x0, y, z0))
        self.face_out([(q[0], yb, q[2]) for q in front], side_region, (0.0, 1.0, 0.0))
        self.face_out([(x0, y, z0), (x0, y, zh), (x0, yb, zh), (x0, yb, z0)], side_region, (-1.0, 0.0, 0.0))
        self.face_out([(x1, y, z0), (x1, yb, z0), (x1, yb, zh), (x1, y, zh)], side_region, (1.0, 0.0, 0.0))
        self.face_out([(x0, y, zh), (cx, y, za), (cx, yb, za), (x0, yb, zh)], side_region, (-peak, 0.0, w / 2))
        self.face_out([(cx, y, za), (x1, y, zh), (x1, yb, zh), (cx, yb, za)], side_region, (peak, 0.0, w / 2))
        return (cx, y + thickness / 2, za)

    def arcade(self, x0, x1, y, z0, height, n_bays, depth, post_half, post_region, arch_region,
               kind="ARCH", lintel_h=0.5, arch_rise=None, segments=6):
        """An arcade along X from x0 to x1, its front in the plane y (facing -Y), `depth` deep
        toward +Y, standing on z0 and `height` high: n_bays + 1 piers (boxes 2 post_half wide)
        under a band. kind "ARCH" at medium detail: each bay a round arch (a spandrel fanned from
        its upper corners, the intrados under it), the band `lintel_h` above the crowns;
        "POST", or low detail: square openings under a lintel `lintel_h` high, the arches only
        painted. The front of the band and spandrels is one face of `arch_region`, from the
        springing (see arcade_front_h). Returns the top height."""
        top = z0 + height
        span = (x1 - x0 - 2 * post_half * (n_bays + 1)) / n_bays
        arched = kind == "ARCH" and self.medium
        yb = y + depth
        piers = [x0 + post_half + i * (span + 2 * post_half) for i in range(n_bays + 1)]
        if not arched:
            spring = top - lintel_h
            for px in piers:
                self.box(px - post_half, px + post_half, y, yb, z0, spring, post_region, post_region,
                         skip=("top",))
            self.box(x0, x1, y, yb, spring, top, arch_region, post_region)
            return top
        segments = max(2, segments // 2 * 2)          # even: the crown is a corner
        rise = min(span / 2, height - lintel_h - 0.3) if arch_rise is None else arch_rise
        crown = top - lintel_h
        spring = crown - rise
        last = len(piers) - 1
        for i, px in enumerate(piers):
            self.box(px - post_half, px + post_half, y, yb, z0, spring, post_region, post_region,
                     skip=("top",))
            # above the springing the pier is inside the arcade's solid: only its outer ends show
            inner = tuple(k for k, keep in (("-x", i == 0), ("+x", i == last)) if not keep)
            self.box(px - post_half, px + post_half, y, yb, spring, crown, post_region, post_region,
                     skip=("top", "-y") + inner)
        front = (0.0, -1.0, 0.0)
        anchor = (x0, y, spring)
        # the band: its front from the springing's origin, so the painting runs on
        self.box(x0, x1, y, yb, crown, top, arch_region, post_region, skip=("-y",))
        # its lower edge carries every corner on the crown line (pier corners, crowns): no T-junctions
        xs = []
        for xx in sorted([x0, x1, *[px - post_half for px in piers], *[px + post_half for px in piers],
                          *[(piers[i] + piers[i + 1]) / 2 for i in range(n_bays)]]):
            if not xs or xx - xs[-1] > 1e-6:       # the end piers' outer corners are x0 and x1
                xs.append(xx)
        xs[0], xs[-1] = x0, x1
        self.face_out([(xx, y, crown) for xx in xs] + [(x1, y, top), (x0, y, top)], arch_region, front,
                      anchor=anchor)
        for px in piers:                               # the piers' fronts above the springing
            self.face_out([(px - post_half, y, spring), (px + post_half, y, spring),
                           (px + post_half, y, crown), (px - post_half, y, crown)], arch_region, front,
                          anchor=anchor)
        for i in range(n_bays):
            a, b = piers[i] + post_half, piers[i + 1] - post_half
            mx, r = (a + b) / 2, (b - a) / 2
            arc = [(mx - r * math.cos(math.pi * k / segments), spring + rise * math.sin(math.pi * k / segments))
                   for k in range(segments + 1)]                  # from (a, spring) over to (b, spring)
            half = segments // 2
            for corner, part in (((a, crown), arc[:half + 1]), ((b, crown), arc[half:])):
                for (ua, va), (ub, vb) in zip(part, part[1:]):
                    self.face_out([(corner[0], y, corner[1]), (ua, y, va), (ub, y, vb)], arch_region, front,
                                  anchor=anchor)
            for (ua, va), (ub, vb) in zip(arc, arc[1:]):              # the intrados, facing down-in
                nx, nz = -((ua + ub) / 2 - mx), -((va + vb) / 2 - spring)
                self.face_out([(ua, y, va), (ub, y, vb), (ub, yb, vb), (ua, yb, va)], post_region,
                              (nx, 0.0, nz))
        return top

    def balcony(self, x0, x1, y_wall, z, depth, slab_region, rail_region, rail_h=0.9, slab_h=0.12):
        """A balcony on a wall facing -Y at y_wall: a slab from x0 to x1, `depth` out, its top at
        z, and a railing band round its three open sides (`rail_region`, painted)."""
        yf = y_wall - depth
        self.box(x0, x1, yf, y_wall, z - slab_h, z, slab_region, slab_region, skip=("+y",))
        i = 0.04                                         # the railing stands just inside the edge
        self.face_out([(x0 + i, yf + i, z), (x1 - i, yf + i, z), (x1 - i, yf + i, z + rail_h),
                       (x0 + i, yf + i, z + rail_h)], rail_region, (0.0, -1.0, 0.0), anchor=(x0 + i, yf + i, z))
        for xx, nx in ((x0 + i, -1.0), (x1 - i, 1.0)):
            self.face_out([(xx, yf + i, z), (xx, y_wall - 0.02, z), (xx, y_wall - 0.02, z + rail_h),
                           (xx, yf + i, z + rail_h)], rail_region, (nx, 0.0, 0.0))

    def jetty(self, x0, x1, y_wall, z, overhang, soffit_region, end_region, n_ends=0):
        """An upper floor jutting out `overhang` beyond a wall facing -Y at y_wall, from x0 to x1,
        its floor at z: the soffit under it and, at medium detail, `n_ends` joist ends."""
        yf = y_wall - overhang
        self.face_out([(x0, yf, z), (x1, yf, z), (x1, y_wall, z), (x0, y_wall, z)], soffit_region,
                      (0.0, 0.0, -1.0))
        if self.medium and n_ends:
            for k in range(n_ends):
                cx = x0 + (x1 - x0) * (k + 0.5) / n_ends
                self.box(cx - 0.08, cx + 0.08, yf + 0.02, y_wall, z - 0.18, z - 0.01, end_region, end_region,
                         skip=("+y",))


# --------------------------------------------------------------------------------------------------
# Region sizes for the pieces (declare them before pack())

def hipped_roof_size(hx, hy, pitch):
    """(world_w, world_h) a hipped roof over cx +- hx, cy +- hy needs."""
    return max(2 * hx, 2 * hy) + 0.2, math.hypot(min(hx, hy), pitch * min(hx, hy)) + 0.2


def gable_roof_size(hx, hy, pitch, axis="X", overhang=0.0):
    """(roof, gable): the region sizes of `Builder.gable_roof`."""
    along, run = (hx, hy) if axis == "X" else (hy, hx)
    roof = (2 * (along + overhang) + 0.2, math.hypot(run + overhang, pitch * (run + overhang)) + 0.2)
    return roof, (2 * run + 0.1, pitch * run + 0.1)


def gable_roof_z(x, y, cx, cy, hx, hy, z, pitch, axis="X"):
    """The height of a `gable_roof` surface above (x, y)."""
    if axis == "X":
        return z + pitch * (hy - abs(y - cy))
    return z + pitch * (hx - abs(x - cx))


def arcade_front_h(height, n_bays, x0, x1, post_half, kind, medium, lintel_h=0.5, arch_rise=None):
    """The height of an arcade's front region (`arch_region`): the lintel, or with arches the
    band plus the rise."""
    if not (kind == "ARCH" and medium):
        return lintel_h
    span = (x1 - x0 - 2 * post_half * (n_bays + 1)) / n_bays
    rise = min(span / 2, height - lintel_h - 0.3) if arch_rise is None else arch_rise
    return lintel_h + rise


def shed_roof_size(length, depth, pitch):
    return length + 0.1, math.hypot(depth, pitch * depth) + 0.1
