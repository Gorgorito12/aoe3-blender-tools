# SPDX-License-Identifier: GPL-3.0-or-later
"""The game-ready checks on plain mesh data, without Blender.

core/validate.py hands them Blender's evaluated mesh (validate.check); mesh_of(model) hands them
the generator's own mesh, triangulated as Blender's Triangulate modifier does (core/gamemesh.py),
so a building can be checked where Blender is not installed. The same rules and messages either
way: one copy of each rule lives here.

A mesh is a dict:
    verts      [(x, y, z)]                 the mesh's vertices
    polys      [(i, j, k)]                 its triangles (vertex indices)
    uvs        [[(u, v)] * 3] or None      each triangle's corner UVs (None: no UV map)
    uv_layers  how many UV maps
    materials  how many materials
    images     [(name, width, height)]     the image textures of its materials
    footprint  (width, depth) in metres, or None
    transform_ok  False when the object keeps a rotation or a scale
"""
import math
from collections import defaultdict

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 0 else (0.0, 0.0, 0.0)


def _poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2


def _clip(subject, clip):
    """Sutherland-Hodgman: convex polygon intersection in 2D (both counter-clockwise)."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def inter(p, q, a, b):
        x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
        x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    out = list(subject)
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, out = out, []
        if not inp:
            break
        s = inp[-1]
        for e in inp:
            if inside(e, a, b):
                if not inside(s, a, b):
                    out.append(inter(s, e, a, b))
                out.append(e)
            elif inside(s, a, b):
                out.append(inter(s, e, a, b))
            s = e
    return out


def poly_normal(verts, poly):
    """A polygon's unit normal (Newell's method, as Blender's)."""
    n = [0.0, 0.0, 0.0]
    for i in range(len(poly)):
        a, b = verts[poly[i]], verts[poly[(i + 1) % len(poly)]]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return _unit(n)


def poly_area(verts, poly):
    a = verts[poly[0]]
    s = (0.0, 0.0, 0.0)
    for i in range(1, len(poly) - 1):
        c = _cross(_sub(verts[poly[i]], a), _sub(verts[poly[i + 1]], a))
        s = (s[0] + c[0], s[1] + c[1], s[2] + c[2])
    return math.sqrt(_dot(s, s)) / 2


def coplanar_overlaps(verts, polys, normals=None, min_area=0.005):
    """Pairs of faces that lie in the same plane, face the same way and overlap: they z-fight in
    game. Returns [(face index, face index, overlap area m2)]."""
    normals = normals or [poly_normal(verts, p) for p in polys]
    buckets = defaultdict(list)
    for i, poly in enumerate(polys):
        n = normals[i]
        d = _dot(n, verts[poly[0]])
        key = (round(n[0], 3), round(n[1], 3), round(n[2], 3), round(d, 2))
        buckets[key].append(i)
    found = []
    for key, idx in buckets.items():
        if len(idx) < 2:
            continue
        n = normals[idx[0]]
        ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = _unit(_cross(n, ref))
        v = _unit(_cross(n, u))
        flat = {}
        for i in idx:
            pts = [(_dot(verts[k], u), _dot(verts[k], v)) for k in polys[i]]
            if _poly_area(pts) < 0:
                pts.reverse()
            flat[i] = pts
        for a_i in range(len(idx)):
            for b_i in range(a_i + 1, len(idx)):
                a, b = flat[idx[a_i]], flat[idx[b_i]]
                if (max(p[0] for p in a) < min(p[0] for p in b) or max(p[0] for p in b) < min(p[0] for p in a)
                        or max(p[1] for p in a) < min(p[1] for p in b) or max(p[1] for p in b) < min(p[1] for p in a)):
                    continue
                area = abs(_poly_area(_clip(a, b)))
                if area > min_area:
                    found.append((idx[a_i], idx[b_i], area))
    return found


def check(m, tri_budget=6000, profile=None, prop=None):
    """Problems of a building's mesh, as (level, message): see core/validate.check."""
    res = []
    verts, polys = m["verts"], m["polys"]
    tris = len(polys)
    res.append((INFO, f"{tris} triangles, {len(verts)} vertices."))
    budget = None
    if prop is not None and prop.get("tris"):
        q25, q50, q75 = prop["tris"]
        res.append((INFO, f"A prop: the {prop['models']} measured have {q25:.0f} to {q75:.0f} triangles "
                          f"(the middle half), {q50:.0f} at the median."))
        if tris > 2 * q75:
            res.append((WARNING, f"{tris} triangles is over twice the upper quartile of the measured "
                                 f"props ({q75:.0f})."))
        elif tris > q75:
            res.append((INFO, f"{tris} triangles is above three quarters of the measured props ({q75:.0f})."))
    elif profile is not None and m.get("footprint"):
        w, d = m["footprint"][0], m["footprint"][1]
        cls = profile.footprint_class(w, d)
        budget = profile.tri_budget(cls) if cls else None
    if budget:
        p90, top = budget
        res.append((INFO, f"Footprint class {cls}: the measured buildings have up to {p90} triangles "
                          f"(90th percentile), {top} at most."))
        if tris > top:
            res.append((ERROR, f"{tris} triangles is above every measured building of class {cls} ({top})."))
        elif tris > p90:
            res.append((WARNING, f"{tris} triangles is above 90% of the measured buildings of class {cls} ({p90})."))
    elif tris > tri_budget:
        res.append((WARNING, f"{tris} triangles is above the budget of {tri_budget}."))
    uvs = m.get("uvs")
    corner_verts = len({(k, round(uv[0], 4), round(uv[1], 4)) for poly, corners in zip(polys, uvs)
                        for k, uv in zip(poly, corners)}) if uvs else len(verts)
    if corner_verts > 65535:
        res.append((WARNING, f"About {corner_verts} vertices once split by UV: above 65,535, so the model "
                             "needs 32-bit indices (the game exporter writes them; few stock models use them)."))
    elif corner_verts > 30000:
        res.append((WARNING, f"About {corner_verts} vertices once split by UV: heavy for a building."))

    # UVs
    if not m.get("uv_layers"):
        res.append((ERROR, "No UV map."))
    else:
        if m["uv_layers"] > 1:
            res.append((WARNING, f"{m['uv_layers']} UV maps: the game uses one."))
        out = sum(1 for corners in uvs for u, v in corners
                  if not (-1e-4 <= u <= 1.0001 and -1e-4 <= v <= 1.0001))
        if out:
            res.append((WARNING, f"{out} UV corners outside 0..1: a texture atlas does not repeat."))

    # materials and texture
    mats, images = m.get("materials", 0), m.get("images", [])
    if not mats:
        res.append((ERROR, "No material."))
    elif mats > 2:
        res.append((WARNING, f"{mats} materials: each one is another draw call."))
    if mats and not images:
        res.append((ERROR, "No image texture in the material."))
    for name, w, h in images:
        if w == 0 or h == 0:
            res.append((ERROR, f"Texture {name} has no pixels."))
            continue
        if w & (w - 1) or h & (h - 1):
            res.append((ERROR, f"Texture {name} is {w} x {h}: use powers of two."))
        if max(w, h) > 2048:
            res.append((WARNING, f"Texture {name} is {w} x {h}: large for one building."))

    # placement
    if verts:
        xs, ys, zs = [v[0] for v in verts], [v[1] for v in verts], [v[2] for v in verts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        size = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        if math.hypot(cx, cy) > 0.02 * size:
            res.append((WARNING, f"Footprint centre at ({cx:.2f}, {cy:.2f}): the origin should be at its centre."))
        if abs(min(zs)) > 0.01:
            res.append((WARNING, f"Lowest point at z = {min(zs):.2f}: the base should be on the ground (z = 0)."))
        if not m.get("transform_ok", True):
            res.append((WARNING, "Unapplied rotation or scale on the object."))

    # geometry hygiene
    normals = [poly_normal(verts, p) for p in polys]
    tiny = sum(1 for p in polys if poly_area(verts, p) < 1e-6)
    if tiny:
        res.append((WARNING, f"{tiny} degenerate faces (no area)."))
    bottom = sum(1 for p, n in zip(polys, normals)
                 if n[2] < -0.99 and sum(verts[k][2] for k in p) / len(p) < 0.05)
    if bottom:
        res.append((INFO, f"{bottom} faces under the building, never seen: they can be deleted."))
    overlaps = coplanar_overlaps(verts, polys, normals)
    if overlaps:
        a, b, area = max(overlaps, key=lambda t: t[2])
        res.append((ERROR, f"{len(overlaps)} pairs of overlapping coplanar faces (they flicker in game); "
                           f"largest: faces {a} and {b}, {area:.2f} m2."))

    if not [r for r in res if r[0] in (ERROR, WARNING)]:
        res.append((INFO, "No problems found."))
    return res


def mesh_of(model, texture_shape=None):
    """The mesh dict of a generated model as Blender would hold it after create_object and its
    Triangulate modifier: vertices merged at 5 decimals, each face cut as gamemesh.triangulate
    cuts it. texture_shape: the painted texture's (height, width), default the model's."""
    from . import gamemesh
    verts, index, polys, uvs = [], {}, [], []

    def vert(q):
        key = (round(q[0], 5), round(q[1], 5), round(q[2], 5))
        i = index.get(key)
        if i is None:
            i = index[key] = len(verts)
            verts.append(key)
        return i

    for f in model.faces:
        ids = [vert(q) for q in f.pts]
        face_uvs = [model.atlas.uv(f.region, *f.uvs[i]) for i in range(len(f.pts))]
        for t in gamemesh.triangulate(f.pts):
            polys.append(tuple(ids[i] for i in t))
            uvs.append([face_uvs[i] for i in t])
    if texture_shape is None:
        side = model.atlas.size if hasattr(model.atlas, "size") else model.params.texture_size
        texture_shape = (side, side) if isinstance(side, int) else side
    h, w = texture_shape[:2]
    name = f"{model.params.name}_diffuse"
    return {"verts": verts, "polys": polys, "uvs": uvs, "uv_layers": 1, "materials": 1,
            "images": [(name, int(w), int(h))], "footprint": tuple(model.dims["footprint"]),
            "transform_ok": True}
