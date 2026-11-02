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
    h, w, _ = arr.shape
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = arr[::-1].astype(np.float32) / 255.0      # Blender rows go bottom-up
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
