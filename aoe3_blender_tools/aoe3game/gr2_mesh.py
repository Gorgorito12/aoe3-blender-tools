# SPDX-License-Identifier: GPL-3.0-or-later
"""The geometry of an uncompressed Granny model, back in Blender's terms: the inverse of
gr2_write.static_model. Pure Python with numpy; core/gr2_import.py makes the objects.

    model = read(data)
    model["meshes"][0]["positions"]     N x 3, metres, Z up, front toward -Y
    model["bones"]                      [(name, parent index, (x, y, z))], the same space

A file says how its axes lie (ArtToolInfo: right, up, back, units per metre) and those are
followed: x = p.right, y = -p.back, z = p.up, over the units per metre. V is stored from the top
row, so v = 1 - V. Compressed files are refused (gr2.Compressed): they need the bridge first.

What it reads: meshes with a plain Position, and meshes whose vertices are in the game's packed
stream (a single one-byte member named FD; more than half of the units, see "Packed vertices"
in docs/game-formats.md), of which it takes the positions and the UVs. Any other mesh is listed
in `skipped` and left out.
"""
import struct

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


FD_MAGIC = 0xFDABCD01
FD_HEADER = 64
FD_BLOCK = 112          # four rigid vertices: x[4], y[4], z[4], normal[4], tangent[4], uv[4][2]
FD_SKINNED = 32         # one skinned vertex: xyz, bone weights and indices, normal, tangent, uv


def is_packed(vs):
    """True for a vertex array in the packed FD stream."""
    t = getattr(vs, "type", None)
    return (t is not None and [m.name for m in t.members] == ["FD"]
            and len(vs.raw) >= FD_HEADER and struct.unpack_from("<I", vs.raw, 0)[0] == FD_MAGIC)


def packed(raw):
    """(positions N x 3, uvs N x 2) of a packed FD stream, in the file's own axes. The rigid
    vertices (bound to one bone) come first, in blocks of four stored a coordinate at a time,
    then the skinned ones one by one; both in model space. Gr2Error when the header does not
    add up."""
    if len(raw) < FD_HEADER:
        raise gr2.Gr2Error("packed vertices: shorter than their header")
    (magic, size, _hash, count, _groups, table, blocks, rigid_bytes, skinned, skinned_bytes,
     rigid, _bones) = struct.unpack_from("<12I", raw, 0)
    if (magic != FD_MAGIC or size != len(raw) - 12 or rigid_bytes != blocks * FD_BLOCK
            or skinned_bytes != skinned * FD_SKINNED or rigid != 4 * blocks
            or count != rigid + skinned
            or FD_HEADER + table + rigid_bytes + skinned_bytes != len(raw)):
        raise gr2.Gr2Error("packed vertices: a layout this reader does not know")
    at = FD_HEADER + table
    a = np.frombuffer(raw, np.uint8, rigid_bytes, at).reshape(blocks, FD_BLOCK)
    b = np.frombuffer(raw, np.uint8, skinned_bytes, at + rigid_bytes).reshape(skinned, FD_SKINNED)
    pos = np.empty((count, 3), np.float32)
    uv = np.empty((count, 2), np.float32)
    pos[:rigid] = a[:, :48].copy().view("<f4").reshape(blocks, 3, 4).transpose(0, 2, 1).reshape(rigid, 3)
    uv[:rigid] = a[:, 80:].copy().view("<f4").reshape(rigid, 2)
    pos[rigid:] = b[:, :12].copy().view("<f4").reshape(skinned, 3)
    uv[rigid:] = b[:, 24:].copy().view("<f4").reshape(skinned, 2)
    return pos, uv


def _diffuse(mat, depth=0):
    """The texture a material shows: its Diffuse Color map's, else its own."""
    if mat is None or depth > 4:
        return None
    for mp in mat.get("Maps") or []:
        if mp is not None and (mp.get("Usage") or "").lower().startswith("diffuse"):
            return _diffuse(mp.get("Map"), depth + 1)
    return mat.get("Texture")


def _face_textures(m, tt, count, texture_at):
    """For each triangle of a mesh, the index of its diffuse texture in the file's Textures, or
    -1: through the topology's groups and the mesh's material bindings."""
    out = np.full(count, -1, np.int64)
    groups = tt.get("Groups")
    if isinstance(groups, list):
        rows = [(g.get("MaterialIndex"), g.get("TriFirst"), g.get("TriCount")) for g in groups if g]
    elif groups is not None and getattr(groups, "count", 0):
        cols = [groups.column(n) for n in ("MaterialIndex", "TriFirst", "TriCount")]
        rows = [(a[0], b[0], c[0]) for a, b, c in zip(*cols)] if all(cols) else []
    else:
        rows = []
    bindings = [b.get("Material") if b is not None else None for b in (m.get("MaterialBindings") or [])]
    for mat, first, n in rows:
        if mat is None or not 0 <= mat < len(bindings):
            continue
        tex = _diffuse(bindings[mat])
        if tex is not None and tex.at in texture_at:
            out[max(0, first):max(0, first + n)] = texture_at[tex.at]
    return out


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
    textures = root.get("Textures") or []
    texture_at = {t.at: i for i, t in enumerate(textures) if t is not None}
    for m in root.get("Meshes") or []:
        if m is None:
            continue
        vd, tt = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        vs = vd.get("Vertices") if vd is not None else None
        pos = _column(vs, "Position", 3) if vs is not None else None
        nor = uv = None
        if pos is None and vs is not None and is_packed(vs):
            try:
                pos, uv = packed(vs.raw)
            except gr2.Gr2Error:
                pos = None
        elif pos is not None:
            nor = _column(vs, "Normal", 3)
            uv = _column(vs, "TextureCoordinates0", 2)
        if pos is None or tt is None:
            skipped.append(m.get("Name"))
            continue
        tris = _indices(tt)
        faces = _face_textures(m, tt, len(tris), texture_at)
        keep = (tris < len(pos)).all(1)
        tris, faces = tris[keep], faces[keep]
        if uv is not None:
            uv = np.stack([uv[:, 0], 1.0 - uv[:, 1]], axis=1)
        meshes.append({
            "name": m.get("Name") or "mesh",
            "positions": to_blender(pos, right, up, back, upm),
            "normals": None if nor is None else to_blender(nor, right, up, back, 1.0),
            "uvs": uv,
            "triangles": tris[:, ::-1].copy(),             # the mirror in x turns the winding
            "face_textures": faces,                         # index in "textures", or -1
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
            "textures": [t.get("FromFileName") if t is not None else None for t in textures]}
