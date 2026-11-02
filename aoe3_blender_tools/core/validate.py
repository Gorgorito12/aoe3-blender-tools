# SPDX-License-Identifier: GPL-3.0-or-later
"""Game-ready checks for a low-poly building object.

Each check returns (level, message) with level ERROR, WARNING or INFO. The limits are the ones that
matter for a 2007 Direct3D 9 engine; the triangle budget is a project choice and can be changed.
"""
import math
from collections import defaultdict

import bpy

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


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


def coplanar_overlaps(mesh, min_area=0.005):
    """Pairs of faces that lie in the same plane, face the same way and overlap: they z-fight in
    game. Returns [(face index, face index, overlap area m2)]."""
    buckets = defaultdict(list)
    for poly in mesh.polygons:
        n = poly.normal
        d = n.dot(mesh.vertices[poly.vertices[0]].co)
        key = (round(n.x, 3), round(n.y, 3), round(n.z, 3), round(d, 2))
        buckets[key].append(poly.index)
    found = []
    for key, idx in buckets.items():
        if len(idx) < 2:
            continue
        n = mesh.polygons[idx[0]].normal
        ref = (1.0, 0.0, 0.0) if abs(n.x) < 0.9 else (0.0, 1.0, 0.0)
        u = n.cross(ref).normalized()
        v = n.cross(u).normalized()
        flat = {}
        for i in idx:
            pts = [(mesh.vertices[k].co.dot(u), mesh.vertices[k].co.dot(v)) for k in mesh.polygons[i].vertices]
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


def check(obj, tri_budget=6000):
    res = []
    if obj is None or obj.type != "MESH":
        return [(ERROR, "Select the building's mesh object.")]
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    m = ev.to_mesh()
    m.calc_loop_triangles()
    tris, verts = len(m.loop_triangles), len(m.vertices)

    # budget and index limits
    res.append((INFO, f"{tris} triangles, {verts} vertices."))
    if tris > tri_budget:
        res.append((WARNING, f"{tris} triangles is above the budget of {tri_budget}."))
    corner_verts = len({(l.vertex_index, tuple(round(c, 4) for c in m.uv_layers.active.data[l.index].uv))
                        for l in m.loops}) if m.uv_layers.active else verts
    if corner_verts > 65535:
        res.append((ERROR, f"About {corner_verts} vertices once split by UV: above the 16-bit index limit (65,535)."))
    elif corner_verts > 30000:
        res.append((WARNING, f"About {corner_verts} vertices once split by UV: heavy for a building."))

    # UVs
    if len(m.uv_layers) == 0:
        res.append((ERROR, "No UV map."))
    else:
        if len(m.uv_layers) > 1:
            res.append((WARNING, f"{len(m.uv_layers)} UV maps: the game uses one."))
        uvs = m.uv_layers.active.data
        out = sum(1 for d in uvs if not (-1e-4 <= d.uv.x <= 1.0001 and -1e-4 <= d.uv.y <= 1.0001))
        if out:
            res.append((WARNING, f"{out} UV corners outside 0..1: a texture atlas does not repeat."))

    # materials and texture
    mats = [mt for mt in obj.data.materials if mt]
    if not mats:
        res.append((ERROR, "No material."))
    elif len(mats) > 2:
        res.append((WARNING, f"{len(mats)} materials: each one is another draw call."))
    imgs = [n.image for mt in mats if mt.node_tree for n in mt.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    if mats and not imgs:
        res.append((ERROR, "No image texture in the material."))
    for img in imgs:
        w, h = img.size
        if w == 0 or h == 0:
            res.append((ERROR, f"Texture {img.name} has no pixels."))
            continue
        if w & (w - 1) or h & (h - 1):
            res.append((ERROR, f"Texture {img.name} is {w} x {h}: use powers of two."))
        if max(w, h) > 2048:
            res.append((WARNING, f"Texture {img.name} is {w} x {h}: large for one building."))

    # placement
    xs = [v.co.x for v in m.vertices]
    ys = [v.co.y for v in m.vertices]
    zs = [v.co.z for v in m.vertices]
    if xs:
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        size = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        if math.hypot(cx, cy) > 0.02 * size:
            res.append((WARNING, f"Footprint centre at ({cx:.2f}, {cy:.2f}): the origin should be at its centre."))
        if abs(min(zs)) > 0.01:
            res.append((WARNING, f"Lowest point at z = {min(zs):.2f}: the base should be on the ground (z = 0)."))
        if any(abs(s - 1.0) > 1e-6 for s in obj.scale) or any(abs(r) > 1e-6 for r in obj.rotation_euler):
            res.append((WARNING, "Unapplied rotation or scale on the object."))

    # geometry hygiene
    tiny = sum(1 for p in m.polygons if p.area < 1e-6)
    if tiny:
        res.append((WARNING, f"{tiny} degenerate faces (no area)."))
    bottom = sum(1 for p in m.polygons if p.normal.z < -0.99 and p.center.z < 0.05)
    if bottom:
        res.append((INFO, f"{bottom} faces under the building, never seen: they can be deleted."))
    overlaps = coplanar_overlaps(m)
    if overlaps:
        a, b, area = max(overlaps, key=lambda t: t[2])
        res.append((ERROR, f"{len(overlaps)} pairs of overlapping coplanar faces (they flicker in game); "
                           f"largest: faces {a} and {b}, {area:.2f} m2."))
    ev.to_mesh_clear()

    if not [r for r in res if r[0] in (ERROR, WARNING)]:
        res.append((INFO, "No problems found."))
    return res
