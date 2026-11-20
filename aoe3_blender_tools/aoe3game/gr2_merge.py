# SPDX-License-Identifier: GPL-3.0-or-later
"""Merges models hung on a building (trees on a plantation, a canopy on a town centre) into the
building's own model, so the game draws one model instead of the building and every attachment.

    out, info = merge(body_raw, [(part_raw, "ATTACHPOINT", "bone_corn01"), ...])

Every input is an uncompressed Granny file. Each part's meshes are copied into the body:

- placed as the game hangs the part (`gr2_mesh.attach_matrix`: its `frombone` laid on the body's
  `tobone` at rest, the part's bone without its scale), every vertex position, normal, tangent and
  binormal taken into the body's file; triangles turned over when that mirrors them;
- bound whole to the body's `tobone` (or, when the body has none, to the bone the body's first
  mesh is bound to), so they follow it as an attachment would;
- with their own materials, textures (and their stored names), vertex layout and shader data.

The copied objects are rebuilt in the body's own types, member by member (a file lays every object
out by its parent's type, so an object pasted with the part's type could be read wrong); variant
members (the vertices, the materials' extended data) carry their own type and stay as they are.
Refused (`Refused`): a part with skinned vertices or a packed vertex stream, an array whose layout
differs between the two files.
"""
import numpy as np

from . import gr2, gr2_basis, gr2_edit, gr2_mesh, gr2_write

VECTOR_MEMBERS = gr2_basis.VECTOR_MEMBERS


class Refused(ValueError):
    pass


def _flat_layout(spec):
    return [(k, n, w) for k, n, _r, w in spec.members]


def respec(w, spec, memo):
    """A copy of the object `w` laid out by `spec`, member by member (recursively)."""
    if w is None:
        return None
    key = (id(w), id(spec))
    if key in memo:
        return memo[key]
    out = gr2_write.W(spec)
    memo[key] = out
    for kind, name, ref, _width in spec.members:
        v = w.values.get(name)
        if v is None:
            continue
        if kind in (gr2.REFERENCE,) and ref is not None:
            out.values[name] = respec(v, ref, memo)
        elif kind == gr2.INLINE and ref is not None:
            out.values[name] = [respec(x, ref, memo) for x in v] if isinstance(v, list) else respec(v, ref, memo)
        elif kind == gr2.ARRAY_OF_REFS and ref is not None:
            out.values[name] = [respec(x, ref, memo) for x in v]
        elif kind == gr2.REF_TO_ARRAY and ref is not None:
            if isinstance(v, gr2_write.Flat):
                if _flat_layout(v.spec) != _flat_layout(ref):
                    raise Refused(f"{spec.name}.{name}: the array's layout differs between the files")
                out.values[name] = gr2_write.Flat(ref, v.raw, v.count)
            else:
                out.values[name] = [respec(x, ref, memo) for x in v]
        else:
            out.values[name] = v                 # scalars, strings, transforms, variants
    return out


def _member_spec(spec, name):
    return next(ref for _k, n, ref, _w in spec.members if n == name)


def merge(body_raw, parts):
    """(merged file bytes, info). parts: [(part file bytes, frombone, tobone)]."""
    body_doc = gr2.load(body_raw)
    body = gr2_mesh.read(body_raw)
    root = gr2_edit.copy_tree(body_doc)
    rs = root.spec
    specs = {n: _member_spec(rs, n) for n in ("Textures", "Materials", "VertexDatas", "TriTopologies", "Meshes", "Models")}
    model = root.values["Models"][0]
    mmb_spec = _member_spec(model.spec, "MeshBindings")
    first_bone = None
    for m in root.values.get("Meshes") or []:
        for bb in m.values.get("BoneBindings") or []:
            first_bone = first_bone or bb.values.get("BoneName")
    info = {"parts": [], "meshes": 0, "triangles": 0}
    for n, (raw, frombone, tobone) in enumerate(parts):
        part = gr2_mesh.read(raw)
        mat, bone = gr2_mesh.attach_matrix(body, part, frombone, tobone)
        bind_to = bone or first_bone
        lin = mat[:3, :3]
        det = np.linalg.det(lin)
        rot = lin / np.cbrt(abs(det)) if det else lin
        pdoc = gr2.load(raw)
        proot = gr2_edit.copy_tree(pdoc)
        memo = {}
        seen_vd = set()
        for pm in proot.values.get("Meshes") or []:
            vd = pm.values.get("PrimaryVertexData")
            vs = vd.values.get("Vertices") if vd is not None else None
            if not isinstance(vs, gr2_write.Flat):
                raise Refused("a part's vertices are not a flat array")
            names = [x[1] for x in vs.spec.members]
            if names == ["FD"]:
                raise Refused("a part stores its vertices in a packed stream")
            if "BoneWeights" in names or "BoneIndices" in names:
                raise Refused("a part has skinned vertices")
            if id(vd) not in seen_vd:
                seen_vd.add(id(vd))
                arr = np.frombuffer(vs.raw, gr2_basis._dtype(vs.spec), vs.count).copy()
                p = arr["Position"].astype(np.float64)
                h = np.concatenate([p, np.ones((len(p), 1))], axis=1) @ mat
                arr["Position"] = h[:, :3].astype(np.float32)
                for name in VECTOR_MEMBERS:
                    if name in arr.dtype.names and arr[name].shape[1] >= 3:
                        v = arr[name][:, :3].astype(np.float64) @ rot
                        ln = np.linalg.norm(v, axis=1, keepdims=True)
                        arr[name][:, :3] = (v / np.where(ln > 0, ln, 1.0)).astype(np.float32)
                vd.values["Vertices"] = gr2_write.Flat(vs.spec, arr.tobytes(), vs.count)
            if det < 0 and pm.values.get("PrimaryTopology") is not None:
                gr2_basis._flip_winding(pm.values["PrimaryTopology"])
            arr = np.frombuffer(vd.values["Vertices"].raw, gr2_basis._dtype(vd.values["Vertices"].spec),
                                vd.values["Vertices"].count)
            lo = [float(x) for x in arr["Position"].min(0)]
            hi = [float(x) for x in arr["Position"].max(0)]
            mesh = respec(pm, specs["Meshes"], memo)
            bb_spec = _member_spec(specs["Meshes"], "BoneBindings")
            mesh.values["BoneBindings"] = [gr2_write.W(bb_spec, BoneName=bind_to, OBBMin=tuple(lo), OBBMax=tuple(hi),
                                                       TriangleIndices=None)]
            mesh.values["Name"] = f"{pm.values.get('Name') or 'part'}_{n}"
            root.values["Meshes"] = list(root.values.get("Meshes") or []) + [mesh]
            model.values["MeshBindings"] = list(model.values.get("MeshBindings") or []) + \
                [gr2_write.W(mmb_spec, Mesh=mesh)]
            for name, getter in (("VertexDatas", lambda m: [m.values.get("PrimaryVertexData")]),
                                 ("TriTopologies", lambda m: [m.values.get("PrimaryTopology")])):
                have = root.values.get(name) or []
                for obj in getter(mesh):
                    if obj is not None and all(obj is not x for x in have):
                        have = list(have) + [obj]
                root.values[name] = have
            for mb in mesh.values.get("MaterialBindings") or []:
                _add_material(root, mb.values.get("Material"))
            info["meshes"] += 1
            tt = mesh.values.get("PrimaryTopology")
            for key in ("Indices16", "Indices"):
                ix = tt.values.get(key) if tt is not None else None
                if isinstance(ix, gr2_write.Flat) and ix.count:
                    info["triangles"] += ix.count // 3
                    break
        info["parts"].append({"tobone": tobone, "bound_to": bind_to, "mirror": bool(det < 0)})
    out = gr2_write.serialize(root, type_tag=body_doc.c.type_tag)
    return out, info


def _add_material(root, mat, depth=0):
    """Puts a copied material, the materials its maps use and their textures into the file's
    lists (each once)."""
    if mat is None or depth > 6:
        return
    mats = list(root.values.get("Materials") or [])
    if all(mat is not x for x in mats):
        root.values["Materials"] = mats + [mat]
    tex = mat.values.get("Texture")
    texs = list(root.values.get("Textures") or [])
    if tex is not None and all(tex is not x for x in texs):
        root.values["Textures"] = texs + [tex]
    for mp in mat.values.get("Maps") or []:
        if mp is not None:
            _add_material(root, mp.values.get("Map"), depth + 1)
