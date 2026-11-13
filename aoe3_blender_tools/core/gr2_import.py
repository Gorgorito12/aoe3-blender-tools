# SPDX-License-Identifier: GPL-3.0-or-later
"""A game model into Blender: the mesh, its UVs, and an Empty for every bone. The inverse of the
game export, so a model can be looked at, measured, rendered - and exported again: an Empty
parented to an object is what core/blender_io.game_bones writes as a bone.

Only uncompressed Granny files are read (aoe3game/gr2_mesh.py); almost every file of the game is
compressed and needs an external tool first (tools/model_survey.py --granny keeps uncompressed
copies in its cache). Needs Blender.
"""
import os

import bmesh
import bpy

from ..aoe3game import gr2, gr2_mesh
from . import blender_io


def create(model, name, image=None, collection=None):
    """An object from what gr2_mesh.read returned: every mesh in one object, one UV map, flat or
    smooth as its normals say, an Empty per bone that is not the root or a mesh's own. `image`: a
    Blender image for its material, or None for a plain one."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for part in model["meshes"]:
        verts = [bm.verts.new(tuple(float(c) for c in p)) for p in part["positions"]]
        for a, b, c in part["triangles"]:
            if len({int(a), int(b), int(c)}) < 3:
                continue
            try:
                face = bm.faces.new((verts[int(a)], verts[int(b)], verts[int(c)]))
            except ValueError:                      # the same triangle twice: keep the first
                continue
            face.smooth = True
            if part["uvs"] is not None:
                for loop, i in zip(face.loops, (int(a), int(b), int(c))):
                    loop[uv_layer].uv = (float(part["uvs"][i][0]), float(part["uvs"][i][1]))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.collection).objects.link(obj)
    if image is not None:
        mesh.materials.append(blender_io._material(name + "_mat", image))
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
