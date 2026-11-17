# SPDX-License-Identifier: GPL-3.0-or-later
"""A Model as a triangle mesh without Blender: positions, normals, UVs and triangles in the form
`blender_io.game_mesh` returns them (object space, metres; UVs in Blender's convention, v up).

It follows what Blender does to the object `blender_io.create_object` makes: corners merged by
position (5 decimals); each face cut into len(pts) - 2 triangles as the Triangulate modifier
cuts it (a quad by its shorter diagonal, 1-3 on a tie; a larger face as a fan when convex, else
by ear clipping on its plane); then the normals worked out on the triangles: a flat face's
triangle keeps its own, a smooth one takes the angle-weighted mean of its smooth fan round the
vertex (Blender's corner normals: the fan stops at a flat face, at an edge more than two faces
share, and between faces wound the same way along their edge).

Measured 2026-11-17 against `blender_io.game_mesh` on every preset at both details: the same
triangle count, area, corner positions and UVs everywhere, and the same vertices and normals in
100 of the 102 cases; the burnt hut differs where a non-planar face of five sides or more is cut
otherwise than Blender's beauty fill (tests/run_tests.py). Whether the game export may use it in
place of Blender is still to verify in game.
"""
import math

from .kit import _ear_clip, newell

KEY = 5                                   # create_object merges corners rounded to 5 decimals


def _basis(n):
    """Two unit axes spanning the plane of normal n."""
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0])
    lu = math.sqrt(sum(c * c for c in u)) or 1.0
    u = tuple(c / lu for c in u)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
    return u, v


def _convex(poly2):
    n = len(poly2)
    for i in range(n):
        a, b, c = poly2[i - 1], poly2[i], poly2[(i + 1) % n]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) < -1e-9:
            return False
    return True


def _flat(poly2, tris, eps=1e-9):
    """Whether one of the triangles has no area."""
    for a, b, c in tris:
        (x0, y0), (x1, y1), (x2, y2) = poly2[a], poly2[b], poly2[c]
        if abs((x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)) <= eps:
            return True
    return False


def triangulate(pts):
    """Index triples into pts: len(pts) - 2 of them for a simple polygon."""
    n = len(pts)
    if n == 3:
        return [(0, 1, 2)]

    def d2(a, b):
        return sum((pts[a][k] - pts[b][k]) ** 2 for k in range(3))

    # the Triangulate modifier's shortest diagonal; on a tie (a rectangle) it takes 1-3
    if n == 4 and not d2(0, 2) < d2(1, 3) - 1e-9:
        fan = [(0, 1, 3), (1, 2, 3)]
    else:
        fan = [(0, i, i + 1) for i in range(1, n - 1)]
    normal = newell(pts)
    u, v = _basis(normal)
    poly2 = [(sum(q[k] * u[k] for k in range(3)), sum(q[k] * v[k] for k in range(3))) for q in pts]
    if _convex(poly2):
        if n > 4 and _flat(poly2, fan):
            # points along one edge (an arcade's lintel): a fan from the first corner leaves flat
            # triangles, which Blender's n-gon triangulation does not; fan from a corner that leaves none
            for k in range(1, n):
                other = [(k, (k + i) % n, (k + i + 1) % n) for i in range(1, n - 1)]
                if not _flat(poly2, other):
                    return other
        return fan
    tris = _ear_clip(poly2)
    if not tris:
        return fan
    return [tuple(t) for t in tris]


def _angle(a, b, c):
    """The angle at b of the corner a-b-c."""
    u = tuple(a[k] - b[k] for k in range(3))
    v = tuple(c[k] - b[k] for k in range(3))
    lu = math.sqrt(sum(x * x for x in u))
    lv = math.sqrt(sum(x * x for x in v))
    if lu < 1e-12 or lv < 1e-12:
        return 0.0
    cos = sum(u[k] * v[k] for k in range(3)) / (lu * lv)
    return math.acos(max(-1.0, min(1.0, cos)))


def _corner_normals(faces, keys, normals):
    """Blender's corner normals: a flat face's corners take its own normal; a smooth face's
    corner takes the angle-weighted mean of the smooth faces of its fan round that vertex, the
    faces reached across edges that two smooth faces share and run the opposite ways along (an
    edge of a flat face, one that more than two faces share, or one between faces wound the same
    way along it is sharp)."""
    edges, directed = {}, set()
    for fi, ks in enumerate(keys):
        for i in range(len(ks)):
            a, b = ks[i], ks[(i + 1) % len(ks)]
            edges.setdefault(frozenset((a, b)), []).append(fi)
            directed.add((fi, a, b))
    angles = [[_angle(f.pts[i - 1], f.pts[i], f.pts[(i + 1) % len(f.pts)]) for i in range(len(f.pts))]
              for f in faces]
    out = []
    for fi, (f, ks) in enumerate(zip(faces, keys)):
        if not f.smooth:
            out.append([normals[fi]] * len(ks))
            continue
        row = []
        for i, v in enumerate(ks):
            fan, todo = {fi}, [fi]
            while todo:
                g = todo.pop()
                gk = keys[g]
                j = gk.index(v)
                for other in (gk[j - 1], gk[(j + 1) % len(gk)]):
                    users = edges.get(frozenset((v, other)), [])
                    if len(users) != 2:
                        continue
                    h = users[0] if users[1] == g else users[1]
                    same_way = ((g, v, other) in directed) == ((h, v, other) in directed)
                    if h not in fan and faces[h].smooth and not same_way:
                        fan.add(h)
                        todo.append(h)
            s = [0.0, 0.0, 0.0]
            for g in fan:
                w = angles[g][keys[g].index(v)]
                for k in range(3):
                    s[k] += normals[g][k] * w
            ls = math.sqrt(sum(c * c for c in s))
            row.append(tuple(c / ls for c in s) if ls > 1e-12 else normals[fi])
        out.append(row)
    return out


def mesh(model):
    """(positions, normals, uvs, triangles), a vertex split wherever its UV or normal differs."""
    def key(q):
        return (round(q[0], KEY), round(q[1], KEY), round(q[2], KEY))

    # Blender triangulates first (the Triangulate modifier), then works the normals out on the
    # triangles: a face that is not quite planar shades as its two triangles
    tris = []
    for f in model.faces:
        for t in triangulate(f.pts):
            tris.append(_Tri([f.pts[i] for i in t], [model.atlas.uv(f.region, *f.uvs[i]) for i in t], f.smooth))
    normals = [_tri_normal(t.pts) for t in tris]
    keys = [[key(q) for q in t.pts] for t in tris]
    corner_normals = _corner_normals(tris, keys, normals)

    positions, out_n, uvs, triangles, index = [], [], [], [], {}
    for t, ks, cn in zip(tris, keys, corner_normals):
        corners = []
        for kq, nrm, uv in zip(ks, cn, t.uvs):
            k = (kq, round(uv[0], 6), round(uv[1], 6), round(nrm[0], 4), round(nrm[1], 4), round(nrm[2], 4))
            i = index.get(k)
            if i is None:
                i = index[k] = len(positions)
                positions.append(kq)
                out_n.append(tuple(nrm))
                uvs.append(uv)
            corners.append(i)
        triangles.append(tuple(corners))
    return positions, out_n, uvs, triangles


class _Tri:
    __slots__ = ("pts", "uvs", "smooth")

    def __init__(self, pts, uvs, smooth):
        self.pts, self.uvs, self.smooth = pts, uvs, smooth


def _tri_normal(p):
    u = tuple(p[1][k] - p[0][k] for k in range(3))
    v = tuple(p[2][k] - p[0][k] for k in range(3))
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    ln = math.sqrt(sum(c * c for c in n))
    return tuple(c / ln for c in n) if ln > 1e-15 else (0.0, 0.0, 1.0)


def regions(model):
    """Each atlas region as (name, u0, v0, u1, v1) in UV space, for drawing the atlas."""
    at = model.atlas
    out = []
    for name, r in at.regions.items():
        out.append((name, r.x / at.size, 1.0 - (r.y + r.h) / at.size, (r.x + r.w) / at.size, 1.0 - r.y / at.size))
    return out
