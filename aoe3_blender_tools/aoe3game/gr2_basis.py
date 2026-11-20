# SPDX-License-Identifier: GPL-3.0-or-later
"""Puts a rigid accessory model (a hat, a weapon, a cannon barrel: one bone, every mesh bound to
it whole) into the form a converted model has, the form the game's own converted accessories
take: the stock basis ("ESPostExport", 0.615157485 units per metre, right -X, up +Y, back +Z),
its object at the origin, one bone with no scale, and no animation of its own.

    out, info = normalise_rigid(raw, frombone="bone_hat")

`raw` is an uncompressed Granny file (the bridge's `rebake --noop` output for a compressed one).
A raw 3ds Max export keeps the scene it was cut from: the object's placement in that scene (often
metres from the origin), the node's scale on its bone (16.6, 117, 147,732 are common), an
animation track holding the same placement, and inches with Z up. The game hangs an accessory by
laying its bone on the unit's bone without the bone's scale (`gr2_mesh.attach`); this rewrite
keeps that result and drops the rest:

- every vertex is taken into the attach bone's frame at rest (the bone's rest matrix without its
  scale), then into the stock basis; normals, tangents and binormals turn with it;
- the bone's transform and its inverse become the identity, the model's placement too;
- each bone binding's box is measured again from the vertices it binds;
- the file's animations and track groups are removed (a one-bone accessory's track only holds
  its placement in the scene);
- triangles are turned over when the change of basis mirrors them, so they keep facing out.

What is kept: names, materials, textures and their stored names, the vertex layout, the type tag.
`info` gives the bone used, the scale dropped and the before/after sizes. Refused
(`Refused`): a file with no mesh (a bone and its animation that a mod uses to scale the model it
hangs on it: that scale is its purpose), more than one bone, a packed vertex stream, a skinned mesh.
"""
import numpy as np

from . import gr2, gr2_edit, gr2_mesh, gr2_write

STOCK = gr2_write.STOCK_BASIS
IDENTITY4 = tuple(float(v) for v in np.eye(4).reshape(-1))
VECTOR_MEMBERS = ("Normal", "Tangent", "Binormal")
NUMPY = {"f": "f4", "b": "i1", "B": "u1", "h": "i2", "H": "u2", "i": "i4", "I": "u4"}


class Refused(ValueError):
    pass


def _blender_to_stock():
    """4 x 4 (row vectors) from Blender space (metres, Z up) to the stock basis."""
    u = STOCK["units_per_meter"]
    s = np.eye(4)
    s[:3, :3] = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]) * u
    return s


def _dtype(spec):
    """A numpy dtype for a flat vertex or index spec (scalars only)."""
    fields = []
    for kind, name, _ref, width in spec.members:
        if kind not in gr2.SCALAR_FMT:
            raise Refused(f"{spec.name}: member {name!r} is not a scalar")
        fields.append((name, "<" + NUMPY[gr2.SCALAR_FMT[kind]], (max(1, width),)))
    return np.dtype(fields)


def _vertices(vd):
    vs = vd.values.get("Vertices")
    if not isinstance(vs, gr2_write.Flat):
        raise Refused("vertices are not a flat array")
    names = [m[1] for m in vs.spec.members]
    if names == ["FD"]:
        raise Refused("packed vertex stream")
    if "BoneWeights" in names or "BoneIndices" in names:
        raise Refused("skinned vertices")
    arr = np.frombuffer(vs.raw, _dtype(vs.spec), vs.count).copy()
    return vs, arr


def _flip_winding(tt):
    for key in ("Indices16", "Indices"):
        ix = tt.values.get(key)
        if isinstance(ix, gr2_write.Flat) and ix.count:
            dt = _dtype(ix.spec)
            a = np.frombuffer(ix.raw, dt, ix.count).copy()
            field = dt.names[0]
            tri = a[field].reshape(-1, 3).copy()
            a[field] = tri[:, ::-1].reshape(a[field].shape)
            tt.values[key] = gr2_write.Flat(ix.spec, a.tobytes(), ix.count)


def name_stock(raw):
    """A file the Granny runtime already converted to the stock basis (the bridge's `rebake
    --convert`: GrannyTransformFile over every vertex, bone, inverse, box and curve) named as
    converted: its art tool `ESPostExport`. Without that name the game takes the file for a raw
    export and converts it a second time (in game, docs/game-formats.md). Refused when the basis
    is not the stock one."""
    doc = gr2.load(raw)
    root = gr2_edit.copy_tree(doc)
    art = root.values.get("ArtToolInfo")
    if art is None or abs(float(art.values.get("UnitsPerMeter") or 0) - STOCK["units_per_meter"]) > 1e-4 \
            or tuple(art.values.get("UpVector") or ()) != STOCK["up"]:
        raise Refused("not in the stock basis: convert it first")
    art.values["FromArtToolName"] = STOCK["name"]
    return gr2_write.serialize(root, type_tag=doc.c.type_tag)


def normalise_rigid(raw, frombone=None):
    """(new file bytes, info). The bone's scale is dropped, not kept in the vertices: in game a
    hat whose bone is scaled by 16.6 draws as its copy rewritten this way, and not as the copy
    that kept the scale (2026-11-20, docs/game-formats.md, "Attachments at rest")."""
    doc = gr2.load(raw)
    src = doc.root()
    model = gr2_mesh.read(raw)
    bones = [b.get("Name") for sk in (src.get("Skeletons") or []) for b in (sk.get("Bones") or [])]
    if not (src.get("Meshes") or []):
        # a bone and its animation with no mesh: a mod hangs the real model on that bone (synced)
        # so that the bone's scale sizes it; that scale is the file's whole purpose
        raise Refused("no mesh: a bone that carries a scale, kept as it is")
    if len(bones) != 1:
        raise Refused(f"{len(bones)} bones (one expected)")
    from .animxml import find_bone
    fb = find_bone(list(model["bind"]), frombone) if frombone else None
    fb = fb or bones[0]
    if fb not in model["bind"]:
        raise Refused(f"no rest matrix for bone {fb!r}")
    cp = gr2_mesh._to_blender_matrix(model["basis"])
    w_from = np.linalg.inv(cp) @ model["bind"][fb] @ cp
    rigid = gr2_mesh._rigid(w_from)
    scale = float(np.cbrt(abs(np.linalg.det(w_from[:3, :3]))))
    total = cp @ np.linalg.inv(rigid) @ _blender_to_stock()     # file point -> stock point
    lin = total[:3, :3]
    rot = lin / np.cbrt(abs(np.linalg.det(lin)))
    mirror = np.linalg.det(lin) < 0

    root = gr2_edit.copy_tree(doc)
    seen = set()
    before, after = [], []
    for mesh in root.values.get("Meshes") or []:
        vd = mesh.values.get("PrimaryVertexData")
        if vd is None or id(vd) in seen:
            continue
        seen.add(id(vd))
        vs, arr = _vertices(vd)
        p = arr["Position"].astype(np.float64)
        before.append(p)
        h = np.concatenate([p, np.ones((len(p), 1))], axis=1) @ total
        arr["Position"] = h[:, :3].astype(np.float32)
        after.append(h[:, :3])
        for name in VECTOR_MEMBERS:
            if name in arr.dtype.names and arr[name].shape[1] >= 3:
                v = arr[name][:, :3].astype(np.float64) @ rot
                n = np.linalg.norm(v, axis=1, keepdims=True)
                arr[name][:, :3] = (v / np.where(n > 0, n, 1.0)).astype(np.float32)
        vd.values["Vertices"] = gr2_write.Flat(vs.spec, arr.tobytes(), vs.count)
        if mirror:
            tt = mesh.values.get("PrimaryTopology")
            if tt is not None:
                _flip_winding(tt)
        lo, hi = h[:, :3].min(0), h[:, :3].max(0)
        for bb in mesh.values.get("BoneBindings") or []:
            bb.values["OBBMin"] = tuple(float(x) for x in lo)
            bb.values["OBBMax"] = tuple(float(x) for x in hi)
    for sk in root.values.get("Skeletons") or []:
        for b in sk.values.get("Bones") or []:
            b.values["Transform"] = gr2_write.IDENTITY_TRANSFORM
            b.values["InverseWorldTransform"] = IDENTITY4
    for mo in root.values.get("Models") or []:
        mo.values["InitialPlacement"] = gr2_write.IDENTITY_TRANSFORM
    root.values["Animations"] = None
    root.values["TrackGroups"] = None
    art = root.values.get("ArtToolInfo")
    if art is not None:
        art.values.update({"FromArtToolName": STOCK["name"], "UnitsPerMeter": STOCK["units_per_meter"],
                           "Origin": (0.0, 0.0, 0.0), "RightVector": STOCK["right"],
                           "UpVector": STOCK["up"], "BackVector": STOCK["back"]})
    out = gr2_write.serialize(root, type_tag=doc.c.type_tag)
    def size(ps):
        return [round(float(x), 4) for x in (np.ptp(np.concatenate(ps), axis=0) if ps else [])]
    return out, {"bone": fb, "scale_dropped": round(scale, 4), "mirror": bool(mirror),
                 "size_before": size(before), "size_after": size(after)}
