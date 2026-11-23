# SPDX-License-Identifier: GPL-3.0-or-later
"""A game model taken apart by bone, triangles cut out of a model, and a model of rigid parts
written again. Pure Python with numpy; tools/make_gun_camel.py uses it.

- **Parts by bone** (`mesh_parts`): every mesh of an uncompressed model with, per vertex, its
  position, normal and UV as stored (file axes and units, Granny's V) and the bone it is bound to
  (its heaviest), and per triangle its material. In the game's packed vertex stream (gr2_mesh:
  "Packed vertices" in docs/game-formats.md) a rigid group is a run of vertices on one bone, so a
  gun whose parts each hang on a bone (barrels, casing, crank) comes apart by bone exactly.
  **Measured** (2026-11-24, the stock Gatling gun, 772 rigid and 5 skinned vertices): each packed
  normal is three bytes x, y, z biased by 64 out of 127 (127 is +1, 0 is -1) and a fourth byte
  255; decoded, they agree with the faces' normals (the axis-aligned faces of the carriage give
  exactly (1, 0, 0), (0, -0.25, 0.97), ...). `packed_normals` decodes them.
- **Components** (`components`): triangles joined through shared corners, positions welded (a
  packed mesh repeats a corner on each UV seam), so the swivel gun modelled into a camel's body
  (three pieces bound to its chest) is found as its own pieces.
- **A cut** (`cut_triangles`): a model written again from its own tree (gr2_edit) with some
  triangles of one mesh left out. Nothing else changes: the vertices (packed or not), skin,
  skeleton, materials and every other mesh stay byte for byte; the topology's material groups
  are recounted and the per-triangle maps a topology or a bone binding may carry are remapped.
- **A model of rigid parts** (`rigid_model`): a skeleton of the caller's bones and one rigid mesh
  per part (plain vertices: position, normal, UV, as `gr2_write.static_model` writes a building),
  each bound whole to its bone, so an animation turning that bone turns the part; the materials
  (their maps, textures and shader settings) copied from the source model the parts came from.
"""
import struct

import numpy as np

from . import gr2, gr2_edit, gr2_mesh
from .gr2_types import schema
from .gr2_write import IDENTITY_TRANSFORM, Flat, W, serialize

NORMAL_BIAS = 63.5          # a packed normal byte b stands for (b - 63.5) / 63.5


# --------------------------------------------------------------------------------------------------
# Reading


def packed_normals(raw):
    """Unit normals (N x 3, file axes) of a packed vertex stream: per rigid block of four, four
    4-byte words after the positions; per skinned vertex, the word after its weights."""
    gr2_mesh.packed(raw)                                   # the header's checks
    (_m, _s, _h, count, _g, table, blocks, rigid_bytes, skinned, _sb, rigid,
     _n) = struct.unpack_from("<12I", raw, 0)
    at = gr2_mesh.FD_HEADER + table
    a = np.frombuffer(raw, np.uint8, rigid_bytes, at).reshape(blocks, gr2_mesh.FD_BLOCK)
    b = np.frombuffer(raw, np.uint8, skinned * gr2_mesh.FD_SKINNED,
                      at + rigid_bytes).reshape(skinned, gr2_mesh.FD_SKINNED)
    words = np.empty((count, 4), np.float64)
    words[:rigid] = a[:, 48:64].reshape(blocks * 4, 4)
    words[rigid:] = b[:, 16:20]
    n = (words[:, :3] - NORMAL_BIAS) / NORMAL_BIAS
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def _raw_uvs(vs, count):
    """UVs as stored (Granny's V, not flipped) of a packed or plain vertex array."""
    if gr2_mesh.is_packed(vs):
        return gr2_mesh.packed(vs.raw)[1].astype(np.float64)
    uv = gr2_mesh._column(vs, "TextureCoordinates0", 2)
    return np.zeros((count, 2)) if uv is None else uv.astype(np.float64)


def _triangles(topo):
    """Triangle corners of a topology in the file's order and winding (N x 3)."""
    for key in ("Indices16", "Indices"):
        src = topo.get(key)
        if src is None or not getattr(src, "count", 0):
            continue
        fmt = "<%dH" if key == "Indices16" else "<%di"
        flat = struct.unpack(fmt % src.count, src.raw)
        return np.array(flat, np.int64).reshape(-1, 3)
    return np.zeros((0, 3), np.int64)


def _groups(topo):
    """[(material binding index, first triangle, count)] of a topology."""
    g = topo.get("Groups")
    if g is None or not getattr(g, "count", 0):
        return []
    return [struct.unpack_from("<3i", g.raw, 12 * i) for i in range(g.count)]


def mesh_parts(data):
    """Every mesh of an uncompressed model, as dicts: name; positions, normals (unit) and uvs (as
    stored) per vertex in the file's axes and units; triangles (file winding); vertex_bone (index
    into skin_names of each vertex's heaviest bone); skin_names; tri_material (index into the
    mesh's materials); materials (the source's Material objects, gr2.Obj); mesh (the gr2.Obj).
    gr2.Compressed for a compressed file."""
    doc = gr2.load(data)
    root = doc.root()
    out = []
    for m in root.get("Meshes") or []:
        if m is None:
            continue
        vd, topo = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        vs = vd.get("Vertices") if vd is not None else None
        if vs is None or topo is None:
            continue
        if gr2_mesh.is_packed(vs):
            pos = gr2_mesh.packed(vs.raw)[0].astype(np.float64)
            nrm = packed_normals(vs.raw)
            skin = gr2_mesh.packed_skin(vs.raw)
        else:
            pos = gr2_mesh._column(vs, "Position", 3)
            if pos is None:
                continue
            pos = pos.astype(np.float64)
            nrm = gr2_mesh._column(vs, "Normal", 3)
            nrm = np.zeros_like(pos) if nrm is None else nrm.astype(np.float64)
            skin = gr2_mesh._skin_columns(vs)
        n = len(pos)
        if skin is None:
            vb = np.zeros(n, np.int64)
        else:
            vb = skin[0][:, 0].copy()
            vb[vb < 0] = 0
        tris = _triangles(topo)
        tri_mat = np.zeros(len(tris), np.int64)
        for mat, first, cnt in _groups(topo):
            tri_mat[max(0, first):max(0, first + cnt)] = mat
        names = [b.get("BoneName") for b in (m.get("BoneBindings") or []) if b is not None]
        mats = [b.get("Material") if b is not None else None for b in (m.get("MaterialBindings") or [])]
        out.append({"name": m.get("Name"), "positions": pos, "normals": nrm, "uvs": _raw_uvs(vs, n),
                    "triangles": tris, "vertex_bone": vb, "skin_names": names, "tri_material": tri_mat,
                    "materials": mats, "mesh": m, "doc": doc})
    return out


def triangle_bones(part):
    """The bone name of each triangle of a mesh_parts entry: the bone its first corner hangs on
    (in a rigid part every corner hangs on the same one)."""
    names = part["skin_names"]
    vb = part["vertex_bone"][part["triangles"][:, 0]]
    return [names[i] if 0 <= i < len(names) else None for i in vb]


def components(positions, triangles, decimals=4):
    """A component number per triangle: triangles sharing a corner (positions welded to
    `decimals`) are in one component; numbers count from 0 in order of first triangle."""
    key, vid = {}, np.zeros(len(positions), np.int64)
    for i, p in enumerate(np.round(np.asarray(positions, np.float64), decimals)):
        vid[i] = key.setdefault(tuple(p), len(key))
    parent = list(range(len(key)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for t in triangles:
        a, b, c = (find(vid[x]) for x in t)
        parent[b] = a
        parent[find(c)] = a
    roots = [find(vid[t[0]]) for t in triangles]
    number = {}
    return np.array([number.setdefault(r, len(number)) for r in roots], np.int64)


# --------------------------------------------------------------------------------------------------
# A cut


def cut_triangles(data, mesh_name, keep):
    """The bytes of `data` (an uncompressed model) written again with only the triangles of mesh
    `mesh_name` where `keep` (a bool per triangle, file order) is true. Raises KeyError for a
    missing mesh, ValueError for a mask of the wrong length."""
    doc = gr2.load(data)
    root = gr2_edit.copy_tree(doc)
    mesh = next((m for m in root.values.get("Meshes") or [] if m is not None and m.values.get("Name") == mesh_name),
                None)
    if mesh is None:
        raise KeyError(f"no mesh {mesh_name!r}")
    topo = mesh.values["PrimaryTopology"]
    keep = np.asarray(keep, bool)
    key = "Indices16" if isinstance(topo.values.get("Indices16"), Flat) and topo.values["Indices16"].count else "Indices"
    idx = topo.values[key]
    fmt = "<%dH" if key == "Indices16" else "<%di"
    tris = np.array(struct.unpack(fmt % idx.count, idx.raw), np.int64).reshape(-1, 3)
    if len(keep) != len(tris):
        raise ValueError(f"{len(keep)} flags for {len(tris)} triangles")
    new_index = np.cumsum(keep) - 1                      # old triangle -> new, where kept
    kept = tris[keep]
    flat = kept.ravel().tolist()
    topo.values[key] = Flat(idx.spec, struct.pack(fmt % len(flat), *flat), len(flat))
    groups = topo.values.get("Groups")
    if isinstance(groups, Flat) and groups.count:
        rows = []
        for i in range(groups.count):
            mat, first, cnt = struct.unpack_from("<3i", groups.raw, 12 * i)
            n = int(keep[first:first + cnt].sum())
            start = int(keep[:first].sum())
            rows.append((mat, start, n))
        topo.values["Groups"] = Flat(groups.spec, b"".join(struct.pack("<3i", *r) for r in rows), len(rows))
    # per-triangle maps: dropped (the runtime rebuilds what it needs; none in the game's units)
    for name in ("SideToNeighborMap", "BonesForTriangle", "TriangleToBoneIndices"):
        v = topo.values.get(name)
        if isinstance(v, Flat) and v.count:
            topo.values[name] = None
    for b in mesh.values.get("BoneBindings") or []:
        ti = b.values.get("TriangleIndices")
        if isinstance(ti, Flat) and ti.count:
            old = np.array(struct.unpack(f"<{ti.count}i", ti.raw), np.int64)
            ok = old[(old >= 0) & (old < len(keep))]
            new = [int(new_index[i]) for i in ok if keep[i]]
            b.values["TriangleIndices"] = Flat(ti.spec, struct.pack(f"<{len(new)}i", *new), len(new)) if new else None
    return gr2_write_serialize(root, doc)


def gr2_write_serialize(root, doc):
    return serialize(root, type_tag=doc.c.type_tag)


# --------------------------------------------------------------------------------------------------
# A model of rigid parts


def _texture(S, obj, cache):
    if obj is None:
        return None
    name = obj.get("FromFileName")
    if name not in cache:
        cache[name] = W(S["Texture"], FromFileName=name, TextureType=0, Width=0, Height=0, Encoding=1,
                        SubFormat=0,
                        Layout=W(S["PixelLayout"], BytesPerPixel=4, ShiftForComponent=(0, 8, 16, 24),
                                 BitsForComponent=(8, 8, 8, 8)),
                        Images=[])
    return cache[name]


def _material(S, obj, cache, depth=0):
    """A Material (gr2.Obj, of any loaded file) in the writer's terms: its name, maps (each a
    material with its texture), texture and shader settings (ExtendedData, copied whole)."""
    if obj is None or depth > 4:
        return None
    key = (id(obj.doc), obj.at)
    if key in cache["materials"]:
        return cache["materials"][key]
    w = W(S["Material"], Name=obj.get("Name"))
    cache["materials"][key] = w
    maps = []
    for mp in obj.get("Maps") or []:
        if mp is not None:
            maps.append(W(S["MaterialMap"], Usage=mp.get("Usage"),
                          Map=_material(S, mp.get("Map"), cache, depth + 1)))
    w.values["Maps"] = maps
    w.values["Texture"] = _texture(S, obj.get("Texture"), cache["textures"])
    ext = obj.get("ExtendedData")
    if ext is not None:
        copier = cache["copiers"].setdefault(id(obj.doc), gr2_edit._Copier(obj.doc))
        w.values["ExtendedData"] = copier.obj(ext)
    return w


def _iwt(world):
    """A bone's InverseWorldTransform (16 floats, Granny's row vectors) from its world frame
    (4 x 4, column vectors)."""
    return tuple(float(v) for v in np.linalg.inv(world).T.ravel())


def _transform(local):
    """Granny Transform (flags, position, orientation x y z w, scale/shear) of a rigid local frame."""
    from .gr2_anim import matrix_quat
    q = matrix_quat(local[:3, :3])
    p = local[:3, 3]
    return (3, float(p[0]), float(p[1]), float(p[2]), float(q[0]), float(q[1]), float(q[2]), float(q[3]),
            1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def rigid_model(source, name, bones, parts, *, source_name=""):
    """The bytes of a model of rigid parts.

    source: the uncompressed model the parts' materials come from (bytes); its axes and units
    (ArtToolInfo) are kept. bones: [(name, parent index or -1, 4 x 4 world frame at rest, rigid,
    column vectors, file units)], the first the root (the model is named after it). parts: dicts
    with name, bone (a name of `bones`), positions and normals (N x 3, model space, file axes),
    uvs (N x 2 as stored), triangles (file winding: counter-clockwise seen from outside), and
    materials (per triangle, a Material object, gr2.Obj, of any loaded file). Each part becomes one
    mesh, its triangles grouped by material, bound whole to its bone."""
    S = schema()
    doc = gr2.load(source)
    src = doc.root()
    copier = gr2_edit._Copier(doc)
    cache = {"materials": {}, "textures": {}, "copiers": {id(doc): copier}}
    names = [b[0] for b in bones]
    worlds = [np.asarray(b[2], np.float64) for b in bones]
    bone_objs = []
    empty = W(S["UserProperties"], UserDefinedProperties="")
    for i, (bname, parent, world) in enumerate(bones):
        local = world if parent < 0 else np.linalg.inv(worlds[parent]) @ world
        bone_objs.append(W(S["Bone"], Name=bname, ParentIndex=parent, Transform=_transform(local),
                           InverseWorldTransform=_iwt(world), ExtendedData=empty))
    skeleton = W(S["Skeleton"], Name=names[0], Bones=bone_objs)
    meshes, vdatas, topos, used = [], [], [], []
    for part in parts:
        pos = np.asarray(part["positions"], np.float64)
        nrm = np.asarray(part["normals"], np.float64)
        uvs = np.asarray(part["uvs"], np.float64)
        tris = np.asarray(part["triangles"], np.int64)
        mats = list(part["materials"])
        order, groups, bindings = [], [], []
        distinct = []
        for m in mats:
            if all(m is not d for d in distinct):
                distinct.append(m)
        for k, m in enumerate(distinct):
            sel = [i for i, x in enumerate(mats) if x is m]
            groups.append((k, len(order), len(sel)))
            order += sel
            mw = _material(S, m, cache)
            bindings.append(W(S["MaterialBinding"], Material=mw))
            if all(mw is not u for u in used):
                used.append(mw)
        tris = tris[order]
        raw = b"".join(struct.pack("<8f", *pos[i], *nrm[i], *uvs[i]) for i in range(len(pos)))
        vdata = W(S["VertexData"], Vertices=Flat(S["VertexPNT"], raw, len(pos)), VertexAnnotationSets=[])
        flat = tris.ravel().tolist()
        if len(pos) <= 0xFFFF:
            i16, i32 = Flat(S["Int16"], struct.pack(f"<{len(flat)}H", *flat), len(flat)), []
        else:
            i16, i32 = [], Flat(S["Int32"], struct.pack(f"<{len(flat)}i", *flat), len(flat))
        topo = W(S["TriTopology"], Groups=Flat(S["TriMaterialGroup"],
                                               b"".join(struct.pack("<3i", *g) for g in groups), len(groups)),
                 Indices=i32, Indices16=i16)
        bi = names.index(part["bone"])
        inv = np.linalg.inv(worlds[bi])
        local = (np.c_[pos, np.ones(len(pos))] @ inv.T)[:, :3] if len(pos) else np.zeros((1, 3))
        mesh = W(S["Mesh"], Name=part["name"], PrimaryVertexData=vdata, MorphTargets=[], PrimaryTopology=topo,
                 MaterialBindings=bindings,
                 BoneBindings=[W(S["BoneBinding"], BoneName=part["bone"], OBBMin=tuple(local.min(0)),
                                 OBBMax=tuple(local.max(0)), TriangleIndices=[])],
                 ExtendedData=empty)
        meshes.append(mesh)
        vdatas.append(vdata)
        topos.append(topo)
    model = W(S["Model"], Name=names[0], Skeleton=skeleton, InitialPlacement=IDENTITY_TRANSFORM,
              MeshBindings=[W(S["ModelMeshBinding"], Mesh=m) for m in meshes])
    art = src.get("ArtToolInfo")
    exp = src.get("ExporterInfo")
    textures = list(cache["textures"].values())
    maps = []
    for m in used:
        for mm in m.values.get("Maps") or []:
            if mm.values.get("Map") is not None and all(mm.values["Map"] is not x for x in maps):
                maps.append(mm.values["Map"])
    root = W(S["FileInfo"], ArtToolInfo=copier.obj(art) if art is not None else None,
             ExporterInfo=copier.obj(exp) if exp is not None else None,
             FromFileName=source_name or name, Textures=textures, Materials=maps + used,
             Skeletons=[skeleton], VertexDatas=vdatas, TriTopologies=topos, Meshes=meshes, Models=[model],
             TrackGroups=[], Animations=[])
    return serialize(root, type_tag=doc.c.type_tag)


def face_normals_ok(positions, normals, triangles):
    """The share of triangles whose corners' normals point to the side their winding faces
    (counter-clockwise from outside): a check of a part's winding after a mirror."""
    p, n = np.asarray(positions, np.float64), np.asarray(normals, np.float64)
    t = np.asarray(triangles, np.int64)
    if not len(t):
        return 1.0
    f = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    avg = n[t].sum(1)
    return float(np.mean(np.einsum("ij,ij->i", f, avg) > 0))
