# SPDX-License-Identifier: GPL-3.0-or-later
"""A small renderer in numpy for a building's icon and portrait where Blender is not at hand:
the camera of core/render.py (orthographic, from the front three quarters, framed on the
bounding box), the texture sampled per pixel, a soft studio light, a transparent background.

It is not Workbench: its light is fitted to Blender's studio light, close but not the same, so an
icon made here differs a little from Blender's in its shading (to verify in game whether it shows)."""
import math

import numpy as np

# fitted to Blender's own renders (core/render.py, Workbench studio light) of three presets: 4.7 / 255
# mean difference per channel where both are opaque; camera space, from the upper left
LIGHT = np.array([-0.25, 0.25, 0.45])
AMBIENT, DIFFUSE = 0.36, 0.36


def _camera(azimuth, elevation):
    """(right, up, forward) unit vectors of core/render.py's camera: it looks along `forward`
    toward the target, its up as close to world +Z as the view allows."""
    az, el = math.radians(azimuth), math.radians(elevation)
    view = np.array([math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)])
    forward = -view
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def render_rgba(positions, normals, uvs, triangles, texture, size=512, azimuth=-35.0, elevation=30.0,
                margin=0.98, supersample=2):
    """A size x size RGBA uint8 picture, top row first, of a mesh (metres, Z up; UVs with v up,
    as the game mesh holds them) and its texture (H x W x 3 or 4 uint8, top row first)."""
    pos = np.asarray(positions, np.float64)
    nrm = np.asarray(normals, np.float64)
    uv = np.asarray(uvs, np.float64)
    tri = np.asarray(triangles, np.int64)
    tex = np.asarray(texture)[..., :3].astype(np.float32)
    th, tw = tex.shape[:2]
    right, up, forward = _camera(azimuth, elevation)
    lo, hi = pos.min(0), pos.max(0)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    cx, cy = corners @ right, corners @ up
    extent = max(cx.max() - cx.min(), cy.max() - cy.min()) * margin
    centre = (lo + hi) / 2
    n = size * supersample
    k = n / extent
    sx = ((pos - centre) @ right) * k + n / 2                    # pixels, x to the right
    sy = n / 2 - ((pos - centre) @ up) * k                       # pixels, y down
    depth = (pos - centre) @ forward                             # larger: farther
    cam = np.stack([nrm @ right, nrm @ up, -(nrm @ forward)], 1)
    light = LIGHT / np.linalg.norm(LIGHT)
    shade = AMBIENT + DIFFUSE * np.abs(cam @ light)              # both sides lit: a wall seen from inside too

    zbuf = np.full((n, n), np.inf)
    colour = np.zeros((n, n, 3), np.float32)
    for a, b, c in tri:
        xs, ys = sx[[a, b, c]], sy[[a, b, c]]
        x0, x1 = max(int(math.floor(xs.min())), 0), min(int(math.ceil(xs.max())), n - 1)
        y0, y1 = max(int(math.floor(ys.min())), 0), min(int(math.ceil(ys.max())), n - 1)
        if x0 > x1 or y0 > y1:
            continue
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        z = w0 * depth[a] + w1 * depth[b] + w2 * depth[c]
        region = zbuf[y0:y1 + 1, x0:x1 + 1]
        near = inside & (z < region)
        if not near.any():
            continue
        u = w0 * uv[a, 0] + w1 * uv[b, 0] + w2 * uv[c, 0]
        v = w0 * uv[a, 1] + w1 * uv[b, 1] + w2 * uv[c, 1]
        px = np.clip((u * tw).astype(np.int64), 0, tw - 1)
        py = np.clip(((1 - v) * th).astype(np.int64), 0, th - 1)
        s = w0 * shade[a] + w1 * shade[b] + w2 * shade[c]
        rgb = tex[py, px] * s[..., None]
        region[near] = z[near]
        colour[y0:y1 + 1, x0:x1 + 1][near] = rgb[near]
    alpha = np.isfinite(zbuf).astype(np.float32)
    rgba = np.concatenate([colour * alpha[..., None], alpha[..., None] * 255], axis=2)
    if supersample > 1:
        rgba = rgba.reshape(size, supersample, size, supersample, 4).mean((1, 3))
        a = rgba[..., 3:4]
        rgba[..., :3] = np.where(a > 0, rgba[..., :3] * 255 / np.maximum(a, 1e-6), 0)   # straight alpha
    return np.clip(rgba + 0.5, 0, 255).astype(np.uint8)


def icon_and_portrait(positions, normals, uvs, triangles, texture):
    """(64 x 64 icon, 128 x 128 portrait) RGB arrays, framed as the game's own (aoe3game/icons)."""
    try:
        from ..aoe3game import icons
    except ImportError:                         # core imported as a top-level package (the studio)
        from aoe3game import icons
    shot = render_rgba(positions, normals, uvs, triangles, texture, 512)
    return icons.compose(shot, 64), icons.compose(shot, 128)
