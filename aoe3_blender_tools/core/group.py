# SPDX-License-Identifier: GPL-3.0-or-later
"""Several meshes on one texture: what a prop set needs (one unit, many models, one texture) when
the meshes were modelled and textured one by one.

Each mesh's texture is cut to the box its UVs use, the boxes are packed into one square atlas at
**one texel density** (texture pixels per metre of surface, as tools/model_survey.py measures a
model: the square root of its UV area over its surface area), the pixels are copied in, the
gutters between them filled from their edges (so the mipmaps do not bleed grey into them), and
every mesh's UVs are moved onto its box. The pure parts (plan, cut, composite, remap) need numpy
only; pack_objects does it to Blender objects.

The repaint then works on the whole set in one go: the boxes become its zones.
"""
import math

import numpy as np

from .atlas import Atlas, Region

GUTTER = 4              # pixels each box's edge is repeated into the gutter


def texel(uvs, triangles, positions):
    """UV length per metre of surface: sqrt(UV area / surface area); 0 for a flat or empty mesh."""
    uv, p, t = np.asarray(uvs, np.float64), np.asarray(positions, np.float64), np.asarray(triangles, np.int64)
    if len(t) == 0:
        return 0.0
    a, b, c = uv[t[:, 0]], uv[t[:, 1]], uv[t[:, 2]]
    a_uv = float(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])).sum() / 2)
    a3, b3, c3 = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    a_3d = float(np.linalg.norm(np.cross(b3 - a3, c3 - a3), axis=1).sum() / 2)
    return math.sqrt(a_uv / a_3d) if a_3d > 1e-12 and a_uv > 0 else 0.0


def snap(box, shape):
    """The UV box (u0, v0, u1, v1) grown to whole pixels of an image of `shape` (H, W, ...):
    (pixel rect (x0, y0, x1, y1), top row first; the UV box it covers exactly)."""
    h, w = shape[0], shape[1]
    u0, v0, u1, v1 = (min(max(c, 0.0), 1.0) for c in box)
    x0, x1 = int(math.floor(u0 * w)), max(int(math.floor(u0 * w)) + 1, int(math.ceil(u1 * w)))
    y0, y1 = int(math.floor((1 - v1) * h)), max(int(math.floor((1 - v1) * h)) + 1, int(math.ceil((1 - v0) * h)))
    x1, y1 = min(x1, w), min(y1, h)
    return (x0, y0, x1, y1), (x0 / w, 1 - y1 / h, x1 / w, 1 - y0 / h)


def plan(items, size):
    """An Atlas of `size` px with a region per item [(name, texel, uv box)], each sized so every
    item lands at the same density: a box of UV width fu covers fu / texel metres."""
    regions = []
    for name, tx, (u0, v0, u1, v1) in items:
        tx = tx if tx > 1e-9 else 1.0
        regions.append(Region(name, max(u1 - u0, 1e-4) / tx, max(v1 - v0, 1e-4) / tx))
    return Atlas(size, regions)


def resize(img, w, h):
    """An H x W x C uint8 image resized to h x w (bilinear, the edges clamped)."""
    src = np.asarray(img, np.float32)
    sh, sw = src.shape[:2]
    ys = np.clip((np.arange(h) + 0.5) * sh / h - 0.5, 0, sh - 1)
    xs = np.clip((np.arange(w) + 0.5) * sw / w - 0.5, 0, sw - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, sh - 1), np.minimum(x0 + 1, sw - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = src[y0][:, x0] * (1 - fx) + src[y0][:, x1] * fx
    low = src[y1][:, x0] * (1 - fx) + src[y1][:, x1] * fx
    return np.clip(top * (1 - fy) + low * fy + 0.5, 0, 255).astype(np.uint8)


def composite(atlas, crops, channels=4):
    """The atlas image (top row first): each crop {name: H x W x C} resized into its region, the
    gutters filled from the nearest edge GUTTER pixels out, the rest grey."""
    size = atlas.size
    out = np.zeros((size, size, channels), np.uint8)
    filled = np.zeros((size, size), bool)
    for name, img in crops.items():
        r = atlas[name]
        out[r.y:r.y + r.h, r.x:r.x + r.w] = resize(img[:, :, :channels], r.w, r.h)
        filled[r.y:r.y + r.h, r.x:r.x + r.w] = True
    for _ in range(GUTTER):                                # grow every box by a pixel into the gutter
        grown = out.copy()
        mask = filled.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = np.roll(np.roll(filled, dy, 0), dx, 1) & ~mask
            if dy == 1:
                src[0] = False
            if dy == -1:
                src[-1] = False
            if dx == 1:
                src[:, 0] = False
            if dx == -1:
                src[:, -1] = False
            grown[src] = np.roll(np.roll(out, dy, 0), dx, 1)[src]
            mask |= src
        out, filled = grown, mask
    out[~filled] = (128, 128, 128, 255)[:channels]
    return out


def remap(uvs, box, region, size):
    """UVs inside `box` (u0, v0, u1, v1) moved onto `region` of an atlas of `size` px (V up)."""
    uv = np.asarray(uvs, np.float64)
    u0, v0, u1, v1 = box
    fu = (uv[:, 0] - u0) / max(u1 - u0, 1e-12)
    fv = (uv[:, 1] - v0) / max(v1 - v0, 1e-12)
    u = (region.x + fu * region.w) / size
    v = 1.0 - (region.y + region.h - fv * region.h) / size
    return np.stack([u, v], axis=1)


def pack_objects(objects, size=1024, name="set"):
    """Puts the textures of mesh `objects` into one atlas of `size` px and points every object at
    it: their UVs moved, their materials replaced by one. Returns (the atlas RGBA, the Atlas).
    Each object must have one UV map and an image (the first one found, as the game export
    reads it). Needs Blender."""
    import bpy  # noqa: F401  (Blender first: blender_io needs it)
    from . import blender_io
    items, crops, boxes = [], {}, {}
    for obj in objects:
        rgba = blender_io.texture_rgba(obj)
        m = obj.data
        if not m.uv_layers:
            raise ValueError(f"{obj.name} has no UV map")
        uv = np.array([d.uv[:] for d in m.uv_layers.active.data], np.float64)
        m.calc_loop_triangles()
        tri_loops = np.array([t.loops[:] for t in m.loop_triangles], np.int64).reshape(-1, 3)
        pos = np.array([m.vertices[m.loops[i].vertex_index].co[:] for i in range(len(m.loops))], np.float64)
        pos = pos * np.array(obj.scale[:], np.float64)
        box = (float(uv[:, 0].min()), float(uv[:, 1].min()), float(uv[:, 0].max()), float(uv[:, 1].max()))
        rect, snapped = snap(box, rgba.shape)
        x0, y0, x1, y1 = rect
        crops[obj.name] = rgba[y0:y1, x0:x1]
        boxes[obj.name] = snapped
        items.append((obj.name, texel(uv, tri_loops, pos), snapped))
    atlas = plan(items, size)
    image = composite(atlas, crops)
    img = blender_io._image_from_array(name + "_atlas", image)
    mat = blender_io._material(name + "_atlas", img)
    for obj in objects:
        m = obj.data
        layer = m.uv_layers.active.data
        uv = np.array([d.uv[:] for d in layer], np.float64)
        new = remap(uv, boxes[obj.name], atlas[obj.name], size)
        layer.foreach_set("uv", new.astype(np.float32).ravel())
        m.materials.clear()
        m.materials.append(mat)
        for poly in m.polygons:
            poly.material_index = 0
    return image, atlas
