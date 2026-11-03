# SPDX-License-Identifier: GPL-3.0-or-later
"""Material swatches under the painted drawing: small tileable photos (CC0, see
materials/MATERIALS.md) that give a region its grain while the painter keeps its colour and every
drawn detail. Pure Python with numpy.

A swatch is a PNG in `aoe3_blender_tools/materials/` (written by tools/fetch_materials.py, its
baked lighting removed). At paint time it becomes a brightness factor around 1.0 (`normalise`),
is resampled to the texture's density (`resample`, wrapping so the tiles meet without a seam)
and multiplies the region's colour (`tile`).

TARGET_CONTRAST is the fine grain a swatch keeps, measured as tools/palette_survey.py measures
textures (the luminance minus its 9 x 9 blur, its standard deviation over the mean). Measured on
2026-11-03: the stock building textures 0.34 / 0.50 / 0.62 (quartiles, with every drawn detail);
the generator's flat painting 0.12; a raw plaster photo at the texture's density 0.008. 0.045
(the grain's spread) adds a visible grain under the drawing without blotches at 1:1: to verify in
game (the mipmaps must not glitter).
"""
import os

import numpy as np

from .pngio import read_png

TARGET_CONTRAST = 0.045
FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "materials")

# style -> role -> (swatch, metres per tile, colour key)
MATERIALS = {
    "NEOCLASSICAL": {"wall": ("plaster", 2.0, "wall")},
}

_cache = {}


def plan(style):
    """The roles of a style that have a swatch: {role: (swatch, tile_m, colour key)}."""
    return MATERIALS.get(style, {})


def load(name, folder=None):
    """The swatch `name` as a float32 RGB array, or None when its file is missing (the painter
    then keeps the flat colour)."""
    path = os.path.join(folder or FOLDER, name + ".png")
    key = os.path.normcase(os.path.abspath(path))
    if key not in _cache:
        if not os.path.exists(path):
            _cache[key] = None
        else:
            with open(path, "rb") as f:
                img = read_png(f.read())
            if img.shape[2] == 1:
                img = np.repeat(img, 3, axis=2)
            _cache[key] = img[:, :, :3].astype(np.float32)
    return _cache[key]


def _blur(a, r=1):
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += np.roll(np.roll(a, dy, 0), dx, 1)
    return out / (2 * r + 1) ** 2


def fine_contrast(factor):
    """The local contrast of a brightness map (std of the map minus its 9 x 9 blur, over its mean)."""
    return float((factor - _blur(factor, 4)).std() / max(float(factor.mean()), 1e-6))


LOW_MAX = 0.04          # the largest broad variation (std) kept: stronger blotches show the tiling


def normalise(sw, px, target_contrast=TARGET_CONTRAST):
    """A brightness factor (px x px, mean 1.0) from a swatch at `px` pixels per tile: its grain
    (what the 8 x 8 view leaves) scaled to a standard deviation of `target_contrast` (smoothed
    3 x 3 first, so no pixel noise glitters; the 9 x 9 measure then reads a little less), its
    broad variation (the swatch seen at 8 x 8) kept up to LOW_MAX, clipped to 0.7 .. 1.3."""
    lum = sw @ np.array([0.299, 0.587, 0.114], np.float32)
    f = lum / max(float(lum.mean()), 1e-6)
    f = resample(f[:, :, None], px)[:, :, 0]
    f = _blur(f, 1)
    f = f / max(float(f.mean()), 1e-6)
    low = resample(resample(f[:, :, None], 8), px)[:, :, 0]
    fine = f - low
    c = float(fine.std())
    s_fine = target_contrast / c if c > 1e-6 else 0.0
    sd = float((low - 1.0).std())
    s_low = min(1.0, LOW_MAX / sd) if sd > 1e-6 else 0.0
    out = 1.0 + fine * s_fine + (low - 1.0) * s_low
    return np.clip(out, 0.7, 1.3).astype(np.float32)


def _weights(n_in, n_out):
    """An n_out x n_in matrix resampling one axis of a tileable image (wrapping): the area each
    output pixel covers when shrinking, linear interpolation when enlarging."""
    m = np.zeros((n_out, n_in), np.float64)
    scale = n_in / n_out
    if n_out <= n_in:
        for i in range(n_out):
            a, b = i * scale, (i + 1) * scale
            j = int(np.floor(a))
            while j < b:
                lo, hi = max(a, j), min(b, j + 1)
                m[i, j % n_in] += hi - lo
                j += 1
            m[i] /= scale
    else:
        for i in range(n_out):
            x = (i + 0.5) * scale - 0.5
            j = int(np.floor(x))
            t = x - j
            m[i, j % n_in] += 1 - t
            m[i, (j + 1) % n_in] += t
    return m


def resample(img, px):
    """An H x W x C tileable image resized to px x px, wrapping at the edges (no seam)."""
    h, w = img.shape[:2]
    my, mx = _weights(h, px), _weights(w, px)
    a = img.astype(np.float64)
    out = np.einsum("ij,jkc->ikc", my, a)
    out = np.einsum("ij,kjc->kic", mx, out)
    return out.astype(np.float32)


def tile(canvas_a, rect, factor, tint, offset=(0, 0)):
    """Fills rect (x0, y0, x1, y1 in canvas pixels) of an H x W x 3 float array with `tint`
    times the brightness map `factor`, repeated; `offset` is the pixel of the region where the
    first tile starts, so neighbouring faces of one region continue the pattern."""
    x0, y0, x1, y1 = (int(v) for v in rect)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(canvas_a.shape[1], x1), min(canvas_a.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return None
    th, tw = factor.shape
    ys = (np.arange(y0, y1) - offset[1]) % th
    xs = (np.arange(x0, x1) - offset[0]) % tw
    block = factor[np.ix_(ys, xs)][:, :, None] * np.asarray(tint, np.float32)[None, None, :]
    canvas_a[y0:y1, x0:x1] = block
    return block


def multiply(canvas_a, rect, k):
    """Darkens or lightens a rect by k, keeping the grain under it."""
    x0, y0, x1, y1 = (int(v) for v in rect)
    canvas_a[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] *= k
