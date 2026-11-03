# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender side: turns a `building.Model` and its painted texture into an object, and exports it."""
import json
import os
from dataclasses import asdict

import bmesh
import bpy
import numpy as np

from .paint import save_png


def _remove_previous(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    for child in list(obj.children):
        bpy.data.objects.remove(child, do_unlink=True)
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _image_from_array(name, arr):
    """A packed image from an RGB or RGBA uint8 array (top row first); the alpha, if any, is the
    player-colour mask the game export writes into the texture."""
    h, w, c = arr.shape
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=c == 4)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :c] = arr[::-1].astype(np.float32) / 255.0      # Blender rows go bottom-up
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    img.pack()
    return img


def _material(name, img):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        mat.use_nodes = True        # deprecated in Blender 5 (always on), required before
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None) or nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = (bsdf.location.x - 320, bsdf.location.y)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    for key in ("Specular IOR Level", "Specular"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.0
    return mat


def create_object(model, texture, collection=None):
    """Builds the mesh, material, packed texture and attach empties. Replaces an object of the
    same name. Returns the object."""
    p = model.params
    name = p.name
    _remove_previous(name)

    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    cache = {}

    def vert(q):
        key = (round(q[0], 5), round(q[1], 5), round(q[2], 5))
        v = cache.get(key)
        if v is None:
            v = bm.verts.new(key)
            cache[key] = v
        return v

    for f in model.faces:
        bf = bm.faces.new([vert(q) for q in f.pts])
        bf.smooth = f.smooth
        for loop, (u, v) in zip(bf.loops, f.uvs):
            loop[uv].uv = model.atlas.uv(f.region, u, v)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)

    img = _image_from_array(f"{name}_diffuse", texture)
    mesh.materials.append(_material(f"{name}_mat", img))
    obj.modifiers.new("Triangulate", "TRIANGULATE")

    for aname, loc in model.attach.items():
        e = bpy.data.objects.new(aname, None)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.5
        e.location = loc
        e.parent = obj
        (collection or bpy.context.scene.collection).objects.link(e)

    params = asdict(p)
    params["colors"] = {k: list(v) for k, v in p.colors.items()}
    obj["aoe3_params"] = json.dumps(params)
    obj["aoe3_footprint"] = list(model.dims["footprint"])
    return obj


def triangle_count(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    m = ev.to_mesh()
    m.calc_loop_triangles()
    tris, verts = len(m.loop_triangles), len(m.vertices)
    ev.to_mesh_clear()
    return tris, verts


def _object_image(obj):
    for mat in obj.data.materials:
        if mat and mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    return n.image
    return None


def export(obj, folder, glb=True, fbx=True, obj_file=True):
    """Exports the object and its attach empties. Returns the written paths."""
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, obj.name.lower())
    written = []

    img = _object_image(obj)
    if img is not None:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        arr = (px.reshape(h, w, 4)[::-1, :, :3] * 255.0).round().clip(0, 255).astype(np.uint8)
        tex_path = base + "_diffuse.png"
        save_png(arr, tex_path)
        written.append(tex_path)

    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    obj.select_set(True)
    for c in obj.children:
        c.select_set(True)
    bpy.context.view_layer.objects.active = obj

    if glb:
        bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True,
                                  export_apply=True)
        written.append(base + ".glb")
    if fbx:
        bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, use_mesh_modifiers=True,
                                 path_mode="COPY", embed_textures=True, axis_forward="-Z", axis_up="Y")
        written.append(base + ".fbx")
    if obj_file:
        bpy.ops.wm.obj_export(filepath=base + ".obj", export_selected_objects=True, apply_modifiers=True,
                              export_triangulated_mesh=True, path_mode="STRIP",
                              forward_axis="NEGATIVE_Z", up_axis="Y")
        written += [base + ".obj", base + ".mtl"]

    tris, verts = triangle_count(obj)
    fp = obj.get("aoe3_footprint")
    stats = f"{obj.name}: {tris} triangles, {verts} vertices"
    if fp:
        stats += f"; footprint {fp[0]:.1f} x {fp[1]:.1f} m"
    if img is not None:
        stats += f"; texture {img.size[0]} x {img.size[1]}"
    with open(base + "_stats.txt", "w") as fh:
        fh.write(stats + "\n")
    written.append(base + "_stats.txt")
    return written


# --------------------------------------------------------------------------------------------------
# Game export: what the game format writers (`aoe3game`) need from an object

# Attach empties of the generator, by the bone name the game's building files use.
ATTACH_BONES = {"flag_attach": "bone_flag_civ", "chimney_attach": "bone_chimney"}


def game_mesh(obj):
    """(positions, normals, uvs, triangles) of the evaluated, triangulated mesh in object space
    (metres). A vertex is split wherever its UV or its normal differs between corners, so flat
    faces keep flat shading."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    m = ev.to_mesh()
    try:
        m.calc_loop_triangles()
        if not m.uv_layers:
            raise ValueError(f"{obj.name} has no UV map")
        uv_data = m.uv_layers.active.data
        if hasattr(m, "corner_normals"):
            corner_normals = [tuple(cn.vector) for cn in m.corner_normals]
        else:                                       # Blender before 4.1
            m.calc_normals_split()
            corner_normals = [tuple(lp.normal) for lp in m.loops]
        positions, normals, uvs, triangles, index = [], [], [], [], {}
        for tri in m.loop_triangles:
            corners = []
            for li in tri.loops:
                vi = m.loops[li].vertex_index
                uv = tuple(uv_data[li].uv)
                n = corner_normals[li]
                key = (vi, round(uv[0], 6), round(uv[1], 6),
                       round(n[0], 4), round(n[1], 4), round(n[2], 4))
                k = index.get(key)
                if k is None:
                    k = index[key] = len(positions)
                    positions.append(tuple(m.vertices[vi].co))
                    normals.append(n)
                    uvs.append(uv)
                corners.append(k)
            triangles.append(tuple(corners))
        return positions, normals, uvs, triangles
    finally:
        ev.to_mesh_clear()


def game_bones(obj):
    """(bone name, (x, y, z)) for each attach empty parented to the object, in object space."""
    inv = obj.matrix_world.inverted()
    out = []
    for child in obj.children:
        if child.type != "EMPTY":
            continue
        name = ATTACH_BONES.get(child.name.split(".")[0], child.name)
        out.append((name, tuple((inv @ child.matrix_world).translation)))
    return out


def texture_rgba(obj):
    """The object's image as an H x W x 4 uint8 array, top row first."""
    img = _object_image(obj)
    if img is None:
        raise ValueError(f"{obj.name} has no image texture")
    return image_rgba(img)


def image_rgba(img):
    """A Blender image as an H x W x 4 uint8 array, top row first."""
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    arr = (np.clip(px.reshape(h, w, 4), 0, 1) * 255 + 0.5).astype(np.uint8)
    return arr[::-1].copy()                    # Blender rows go bottom-up


def set_texture_rgba(obj, rgba):
    """Writes an H x W x 4 uint8 array (top row first) into the object's image, in place (the
    material keeps pointing at it), and packs it."""
    img = _object_image(obj)
    if img is None:
        raise ValueError(f"{obj.name} has no image texture")
    h, w = rgba.shape[:2]
    if tuple(img.size) != (w, h):
        img.scale(w, h)
    px = (np.asarray(rgba)[::-1].astype(np.float32) / 255.0).ravel()
    img.pixels.foreach_set(px)
    img.update()
    img.pack()
    return img


def image_copy(obj, name):
    """A packed copy of the object's image under `name` (replacing one of that name)."""
    return _image_from_array(name, texture_rgba(obj))


def params_of(obj):
    """The generator parameters stored on a generated object, or None."""
    from .building import BuildingParams
    raw = obj.get("aoe3_params")
    if not raw:
        return None
    d = json.loads(raw)
    d["colors"] = {k: tuple(v) for k, v in d.get("colors", {}).items()}
    known = {f for f in BuildingParams.__dataclass_fields__}
    return BuildingParams(**{k: v for k, v in d.items() if k in known})


def game_variants(obj, lowpoly=True, damaged=True, lowpoly_texture=512):
    """The variants the game export writes beside a generated building: a low-poly model (the
    generator's LOW detail, for the game's low model detail setting; only when the building is
    more detailed than that) and a damaged texture on the same mesh. {} for an object the
    generator did not make."""
    from dataclasses import replace
    from . import building, paint
    p = params_of(obj)
    if p is None:
        return {}
    out = {}
    if damaged:
        model = building.build(p)
        positions, normals, uvs, tris = game_mesh(obj)
        out["damaged"] = {"positions": positions, "normals": normals, "uvs": uvs,
                          "triangles": tris,
                          "texture_rgba": paint.damaged(model, texture_rgba(obj))}
    if lowpoly and p.detail != "LOW":
        lp = replace(p, detail="LOW", name=p.name + "_LowPolyTemp",
                     texture_size=min(lowpoly_texture, p.texture_size))
        lp_model = building.build(lp)
        tex = paint.paint_rgba(lp_model) if lp.player_colour else paint.paint(lp_model)
        tmp = create_object(lp_model, tex, collection=None)
        try:
            positions, normals, uvs, tris = game_mesh(tmp)
            out["lowpoly"] = {"positions": positions, "normals": normals, "uvs": uvs,
                              "triangles": tris, "texture_rgba": texture_rgba(tmp)}
        finally:
            _remove_previous(tmp.name)
    return out
