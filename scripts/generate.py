# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a preset headless: mesh, texture, exports, .blend and preview renders.

    python scripts/generate.py [--preset WHITE_HOUSE|COURTHOUSE|CAPITOL|MANSION|ALL]
                               [--detail LOW|MEDIUM] [--out DIR]
                               [--views front34,back34,wire | --no-render]

or with Blender: blender -b --factory-startup -P scripts/generate.py -- [same options]
The default output is examples/<name>/ (examples/<name>_medium/ for --detail MEDIUM).
"""
import dataclasses
import math
import os
import sys

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aoe3_blender_tools.core import blender_io, building, paint  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def setup_render(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    try:
        scene.cycles.use_denoising = True
    except Exception:
        pass
    scene.render.resolution_x, scene.render.resolution_y = 1280, 960
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    world = bpy.data.worlds.new("World")
    scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.65, 0.8, 1)
    bg.inputs["Strength"].default_value = 0.7
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(42), 0, math.radians(-35))
    scene.collection.objects.link(sun)
    mesh = bpy.data.meshes.new("Ground")
    mesh.from_pydata([(-100, -100, 0), (100, -100, 0), (100, 100, 0), (-100, 100, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("Ground", mesh)
    gmat = bpy.data.materials.new("Grass")
    try:
        gmat.use_nodes = True
    except Exception:
        pass
    gb = next(n for n in gmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    gb.inputs["Base Color"].default_value = (0.18, 0.26, 0.08, 1)
    gb.inputs["Roughness"].default_value = 1.0
    mesh.materials.append(gmat)
    scene.collection.objects.link(ground)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def shoot(scene, cam, obj, path, azimuth, elevation, clay=False):
    fp = obj.get("aoe3_footprint") or (15, 15)
    size = max(fp[0], fp[1], max(v.co.z for v in obj.data.vertices))
    cam.data.ortho_scale = size * 1.75
    az, el = math.radians(azimuth), math.radians(elevation)
    target = Vector((0, 0, size * 0.3))
    cam.location = target + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * 80
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    mat = obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    scene.render.use_freestyle = clay
    if clay:
        scene.render.line_thickness = 0.8
        vl = bpy.context.view_layer
        vl.use_freestyle = True
        fs = vl.freestyle_settings
        if len(fs.linesets) == 0:          # an empty factory scene has no line set
            ls = fs.linesets.new("Edges")
            ls.select_by_visibility = True
            ls.select_crease = ls.select_border = ls.select_silhouette = True
        for ls in fs.linesets:
            if ls.linestyle is None:
                ls.linestyle = bpy.data.linestyles.new("Edges")
            ls.linestyle.color = (0, 0, 0)
        for link in list(nt.links):
            if link.to_socket == bsdf.inputs["Base Color"]:
                nt.links.remove(link)
        bsdf.inputs["Base Color"].default_value = (0.75, 0.75, 0.75, 1)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if clay:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])


VIEWS = {"front34": (-35, 42, False), "back34": (145, 42, False), "wire": (-35, 42, True)}


def generate(key, out, views, detail):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    params = building.PRESETS[key]
    if detail == "MEDIUM":
        params = dataclasses.replace(params, detail="MEDIUM", name=params.name + "Medium")
    model = building.build(params)
    obj = blender_io.create_object(model, paint.paint(model))
    folder = out or os.path.join(ROOT, "examples", building.PRESETS[key].name.lower()
                                 + ("_medium" if detail == "MEDIUM" else ""))
    paths = blender_io.export(obj, folder)
    try:
        bpy.context.preferences.filepaths.save_version = 0     # no .blend1 backup
    except Exception:
        pass
    blend = os.path.join(folder, params.name.lower() + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print(open(next(pth for pth in paths if pth.endswith("_stats.txt"))).read().strip())
    if views:
        scene = bpy.context.scene
        cam = setup_render(scene)
        for v in views:
            az, el, clay = VIEWS[v]
            shoot(scene, cam, obj, os.path.join(folder, f"preview_{v}.jpg"), az, el, clay)


def main():
    preset = opt("--preset", "WHITE_HOUSE").upper()
    keys = list(building.PRESETS) if preset == "ALL" else [preset]
    views = [] if "--no-render" in argv else opt("--views", "front34,back34,wire").split(",")
    detail = opt("--detail", "LOW").upper()
    for key in keys:
        generate(key, opt("--out") if len(keys) == 1 else None, views, detail)


main()
