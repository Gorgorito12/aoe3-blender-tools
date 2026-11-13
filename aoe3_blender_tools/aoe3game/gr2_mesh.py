# SPDX-License-Identifier: GPL-3.0-or-later
"""The geometry of an uncompressed Granny model, back in Blender's terms: the inverse of
gr2_write.static_model. Pure Python with numpy; core/gr2_import.py makes the objects.

    model = read(data)
    model["meshes"][0]["positions"]     N x 3, metres, Z up, front toward -Y
    model["bones"]                      [(name, parent index, (x, y, z))], the same space

A file says how its axes lie (ArtToolInfo: right, up, back, units per metre) and those are
followed: x = p.right, y = -p.back, z = p.up, over the units per metre. V is stored from the top
row, so v = 1 - V. Compressed files are refused (gr2.Compressed): they need the bridge first.

What it reads is what the reader can read: meshes with a plain Position. A mesh whose vertices
are in a packed stream (more than half of the units, see docs/art-findings.md) is listed in
`skipped` and left out.
"""
import numpy as np

from . import gr2

STOCK_UPM = 0.615157485


def _column(vs, name, width):
    if isinstance(vs, list):
        vals = [v.get(name) for v in vs]
        if not vals or vals[0] is None:
            return None
        return np.array(vals, np.float32).reshape(len(vals), -1)[:, :width]
    try:
        c = vs.column(name)
    except (KeyError, ValueError):
        return None
    if c is None:
        return None
    return np.array(list(c), np.float32).reshape(-1, len(c[0]) if len(c) else width)[:, :width]


def _indices(tt):
    for key in ("Indices", "Indices16"):
        src = tt.get(key)
        n = len(src) if isinstance(src, list) else getattr(src, "count", 0)
        if not n:
            continue
        if isinstance(src, list):
            flat = [e.get("Int16") if e.get("Int16") is not None else e.get("Int32") for e in src]
        else:
            field = src.layout().split(":")[0]
            flat = [x[0] if isinstance(x, (tuple, list)) else x for x in src.column(field)]
        return np.array(flat, np.int64).reshape(-1, 3)
    return np.zeros((0, 3), np.int64)


def basis(root):
    """(right, up, back, units per metre) of a file; the stock buildings' when it does not say."""
    art = root.get("ArtToolInfo")
    if art is None:
        return (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), STOCK_UPM
    upm = float(art.get("UnitsPerMeter") or STOCK_UPM)
    return (tuple(art.get("RightVector") or (-1.0, 0.0, 0.0)), tuple(art.get("UpVector") or (0.0, 1.0, 0.0)),
            tuple(art.get("BackVector") or (0.0, 0.0, 1.0)), upm)


def to_blender(points, right, up, back, upm):
    p = np.asarray(points, np.float32).reshape(-1, 3)
    r, u, b = (np.array(v, np.float32) for v in (right, up, back))
    return np.stack([p @ r, -(p @ b), p @ u], axis=1) / upm


def read(data):
    """{"meshes": [...], "bones": [...], "textures": [...], "skipped": [...], "units_per_meter"}."""
    doc = gr2.load(data)
    root = doc.root()
    right, up, back, upm = basis(root)
    meshes, skipped = [], []
    for m in root.get("Meshes") or []:
        if m is None:
            continue
        vd, tt = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        vs = vd.get("Vertices") if vd is not None else None
        pos = _column(vs, "Position", 3) if vs is not None else None
        if pos is None or tt is None:
            skipped.append(m.get("Name"))
            continue
        tris = _indices(tt)
        tris = tris[(tris < len(pos)).all(1)]
        nor = _column(vs, "Normal", 3)
        uv = _column(vs, "TextureCoordinates0", 2)
        if uv is not None:
            uv = np.stack([uv[:, 0], 1.0 - uv[:, 1]], axis=1)
        meshes.append({
            "name": m.get("Name") or "mesh",
            "positions": to_blender(pos, right, up, back, upm),
            "normals": None if nor is None else to_blender(nor, right, up, back, 1.0),
            "uvs": uv,
            "triangles": tris[:, ::-1].copy(),             # the mirror in x turns the winding
            "bound_to": [b.get("BoneName") for b in (m.get("BoneBindings") or []) if b is not None],
        })
    bones = []
    for sk in root.get("Skeletons") or []:
        rows = [b for b in ((sk.get("Bones") if sk else None) or [])]
        world = []
        for b in rows:
            local = np.array(b.get("Transform")["position"], np.float32)
            parent = b.get("ParentIndex")
            at = local + (world[parent] if 0 <= parent < len(world) else 0.0)   # rotations are not followed
            world.append(at)
            bones.append((b.get("Name"), int(parent), tuple(float(v) for v in to_blender(at, right, up, back, upm)[0])))
    return {"meshes": meshes, "bones": bones, "skipped": skipped, "units_per_meter": upm,
            "textures": [t.get("FromFileName") for t in (root.get("Textures") or []) if t]}
