# SPDX-License-Identifier: GPL-3.0-or-later
"""A game model into Blender: the mesh, its UVs, and an Empty for every bone. The inverse of the
game export, so a model can be looked at, measured, rendered - and exported again: an Empty
parented to an object is what core/blender_io.game_bones writes as a bone.

A unit (a mesh skinned to several bones) comes in with an Armature instead: a bone at each of the
skeleton's joints, placed with their rotations followed (aoe3game/gr2_skin.py), a vertex group per
bone holding its weights (up to four a vertex), and an Armature modifier, so posing a bone moves
the mesh as the game does. A bone points at its child (at its own X axis when it has none, as
3ds Max's Biped draws them); its frame in the file is kept as the bone's `aoe3_frame` (16 numbers,
Blender axes), and the armature's `aoe3_bind_matches` says whether the rest pose is the bind pose.

Only uncompressed Granny files are read (aoe3game/gr2_mesh.py); almost every file of the game is
compressed and needs an external tool first (tools/model_survey.py --granny keeps uncompressed
copies in its cache). Needs Blender.
"""
import os

import bmesh
import bpy

from ..aoe3game import gr2, gr2_mesh, gr2_skin
from . import blender_io


def is_skinned(model):
    """True when a mesh of the model is bound to more than one bone of a skeleton."""
    return bool(model.get("skeletons")) and any(len(part.get("skin_names") or []) > 1 for part in model["meshes"])


def _armature(model, name, collection):
    """An Armature object for the model's largest skeleton (gr2_skin frames, Blender axes)."""
    import numpy as np
    sk = max(model["skeletons"], key=lambda s: len(s["bones"]))
    right, up, back, upm = model["basis"]
    frames = [gr2_skin.to_blender_frame(b["world"], right, up, back, upm) for b in sk["bones"]]
    heads = [f[:3, 3] for f in frames]
    children = {i: [] for i in range(len(heads))}
    for i, b in enumerate(sk["bones"]):
        if 0 <= b["parent"] < len(heads):
            children[b["parent"]].append(i)
    size = max(float(np.ptp(np.array(heads), axis=0).max()) if len(heads) > 1 else 1.0, 0.5)
    data = bpy.data.armatures.new(name + "_rig")
    rig = bpy.data.objects.new(name + "_rig", data)
    (collection or bpy.context.collection).objects.link(rig)
    rig.show_in_front = True
    view = bpy.context.view_layer
    previous = view.objects.active
    view.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    names = []
    try:
        for i, b in enumerate(sk["bones"]):
            eb = data.edit_bones.new(b["name"] or f"bone{i}")
            names.append(eb.name)
            head = heads[i]
            kids = [heads[c] for c in children[i] if np.linalg.norm(heads[c] - head) > 1e-4]
            if kids:
                tail = np.mean(kids, axis=0) if len(kids) == 1 else kids[int(np.argmax([np.linalg.norm(k - head) for k in kids]))]
            else:
                axis = frames[i][:3, 0]
                axis = axis / (np.linalg.norm(axis) or 1.0)
                tail = head + axis * size * 0.04
            if np.linalg.norm(tail - head) < 1e-4:
                tail = head + np.array([0.0, 0.0, size * 0.04])
            eb.head, eb.tail = tuple(float(c) for c in head), tuple(float(c) for c in tail)
        for i, b in enumerate(sk["bones"]):
            if 0 <= b["parent"] < len(names):
                data.edit_bones[names[i]].parent = data.edit_bones[names[b["parent"]]]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        view.objects.active = previous
    for i, n in enumerate(names):
        data.bones[n]["aoe3_frame"] = [float(c) for c in frames[i].ravel()]
    rig["aoe3_bind_matches"] = bool(sk["matches"])
    return rig


def create(model, name, image=None, collection=None, images=None):
    """An object from what gr2_mesh.read returned: every mesh in one object, one UV map, flat or
    smooth as its normals say, an Empty per bone that is not the root or a mesh's own. `image`: a
    Blender image for its material, or None for a plain one. `images`: {index in model["textures"]:
    Blender image}, a material for each, given to the triangles that show that texture (the
    others get `image`'s)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    slots = {}
    if images:
        for k in sorted(images):
            slots[k] = len(slots) + 1          # slot 0 is `image`'s
    offsets, base = [], 0
    for part in model["meshes"]:
        offsets.append(base)
        base += len(part["positions"])
        verts = [bm.verts.new(tuple(float(c) for c in p)) for p in part["positions"]]
        faces = part.get("face_textures")
        for k, (a, b, c) in enumerate(part["triangles"]):
            if len({int(a), int(b), int(c)}) < 3:
                continue
            try:
                face = bm.faces.new((verts[int(a)], verts[int(b)], verts[int(c)]))
            except ValueError:                      # the same triangle twice: keep the first
                continue
            face.smooth = True
            if slots and faces is not None and k < len(faces):
                face.material_index = slots.get(int(faces[k]), 0)
            if part["uvs"] is not None:
                for loop, i in zip(face.loops, (int(a), int(b), int(c))):
                    loop[uv_layer].uv = (float(part["uvs"][i][0]), float(part["uvs"][i][1]))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.collection).objects.link(obj)
    if image is not None or slots:
        mesh.materials.append(blender_io._material(name + "_mat", image) if image is not None
                              else bpy.data.materials.new(name + "_mat"))
    for k, slot in slots.items():
        mesh.materials.append(blender_io._material(f"{name}_mat{slot}", images[k]))
    if is_skinned(model):
        rig = _armature(model, name, collection)
        for part, at in zip(model["meshes"], offsets):
            names = part.get("skin_names") or []
            bones4, weights4 = part["vertex_bones4"], part["vertex_weights4"]
            for v in range(len(part["positions"])):
                for k in range(bones4.shape[1]):
                    b, w = int(bones4[v, k]), float(weights4[v, k])
                    if b < 0 or w <= 0 or b >= len(names) or not names[b]:
                        continue
                    group = obj.vertex_groups.get(names[b]) or obj.vertex_groups.new(name=names[b])
                    group.add([at + v], w, "ADD")
        obj.parent = rig
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        obj["aoe3_imported"] = True
        obj["aoe3_skinned"] = True
        return obj
    own = {part["name"] for part in model["meshes"]} | {name}
    for i, (bone, _parent, at) in enumerate(model["bones"]):
        if i == 0 or bone in own or (bone or "").lower() == "bone_main":
            continue
        empty = bpy.data.objects.new(bone, None)
        empty.empty_display_size = 0.3
        empty.location = at
        empty.parent = obj
        (collection or bpy.context.collection).objects.link(empty)
    obj["aoe3_imported"] = True
    return obj


def load(path, name=None, image=None):
    """The model at `path` as an object. ValueError when the file is compressed or has no mesh
    this reader can read."""
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        model = gr2_mesh.read(data)
    except gr2.Compressed as exc:
        raise ValueError(f"{os.path.basename(path)} is compressed: it needs to be written "
                         "uncompressed first (see tools/model_survey.py)") from exc
    except gr2.Gr2Error as exc:
        raise ValueError(f"{os.path.basename(path)}: {exc}") from exc
    if not model["meshes"]:
        what = "its vertices are in a packed stream this reader cannot open" if model["skipped"] \
            else "it has no mesh (an animation?)"
        raise ValueError(f"{os.path.basename(path)}: {what}")
    return create(model, name or os.path.splitext(os.path.basename(path))[0], image)
