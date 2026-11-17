# SPDX-License-Identifier: GPL-3.0-or-later
"""Quick renders of a building for its icon and portrait (Workbench, textured, transparent
background). Needs Blender; leaves the scene's settings as they were."""
import math
import os
import tempfile

import bpy
import numpy as np
from mathutils import Vector


def _view(azimuth, elevation):
    az, el = math.radians(azimuth), math.radians(elevation)
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))


def view_extent(obj, azimuth=-35.0, elevation=30.0):
    """The larger side of the object's bounding box seen from that direction (an orthographic
    view), in scene units: what render_rgba fits into its frame."""
    rot = (-_view(azimuth, elevation)).to_track_quat("-Z", "Y").to_matrix().inverted()
    pts = [rot @ (obj.matrix_world @ Vector(c)) for c in obj.bound_box]
    return max(max(p.x for p in pts) - min(p.x for p in pts),
               max(p.y for p in pts) - min(p.y for p in pts))


def render_rgba(obj, size=512, azimuth=-35.0, elevation=30.0, margin=0.98, scale=None, ground=None):
    """A size x size RGBA uint8 render of the object, top row first, from the front three
    quarters (azimuth 0 looks from -Y, the front). `scale`: the frame's side in scene units
    (default: the object's own view_extent times `margin`), so several renders share one scale.
    `ground`: put the object's lowest point this share of the frame above its bottom edge
    instead of centring it."""
    scene = bpy.context.scene
    r, disp = scene.render, scene.display
    saved = (scene.camera, r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage,
             r.film_transparent, r.filepath, r.image_settings.file_format,
             r.image_settings.color_mode, disp.shading.light, disp.shading.color_type,
             scene.view_settings.view_transform)
    cam = bpy.data.objects.new("aoe3_icon_camera", bpy.data.cameras.new("aoe3_icon_camera"))
    scene.collection.objects.link(cam)
    path = os.path.join(tempfile.gettempdir(), f"aoe3_icon_{os.getpid()}.png")
    try:
        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        lo = Vector([min(c[i] for c in corners) for i in range(3)])
        hi = Vector([max(c[i] for c in corners) for i in range(3)])
        target = (lo + hi) / 2
        view = _view(azimuth, elevation)
        cam.location = target + view * 200
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.type = "ORTHO"
        cam.data.clip_end = 1000
        bpy.context.view_layer.update()
        inv = cam.matrix_world.inverted()
        pts = [inv @ c for c in corners]
        extent = max(max(p.x for p in pts) - min(p.x for p in pts),
                     max(p.y for p in pts) - min(p.y for p in pts))
        cam.data.ortho_scale = extent * margin if scale is None else scale
        if ground is not None:
            low = min(p.y for p in pts)              # camera space: the camera sits at y = 0
            up = cam.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))
            cam.location += up * (low + cam.data.ortho_scale * (0.5 - ground))
        scene.camera = cam
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x = r.resolution_y = size
        r.resolution_percentage = 100
        r.film_transparent = True
        disp.shading.light = "STUDIO"
        disp.shading.color_type = "TEXTURE"
        scene.view_settings.view_transform = "Standard"
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        try:
            w, h = img.size
            px = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
        finally:
            bpy.data.images.remove(img)
        return (np.clip(px.reshape(h, w, 4), 0, 1) * 255 + 0.5).astype(np.uint8)[::-1].copy()
    finally:
        (scene.camera, r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage,
         r.film_transparent, r.filepath, r.image_settings.file_format, r.image_settings.color_mode,
         disp.shading.light, disp.shading.color_type, scene.view_settings.view_transform) = saved
        bpy.data.objects.remove(cam, do_unlink=True)
        if os.path.exists(path):
            os.remove(path)


def icon_and_portrait(obj):
    """(64 x 64 icon, 128 x 128 portrait) RGB arrays, framed as the game's own."""
    from ..aoe3game import icons
    shot = render_rgba(obj, 512)
    return icons.compose(shot, 64), icons.compose(shot, 128)
