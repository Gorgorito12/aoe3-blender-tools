# SPDX-License-Identifier: GPL-3.0-or-later
"""Paints the diffuse texture of a `building.Model` into its atlas: a `painter.Painter` on the
atlas, handed to the style's `paint(pr, model)` (core/styles/).

Windows, doors, stone courses, slate, dentils and the rest are drawn from the real facade
measurements, so they line up with the geometry. Flat, even colour: no baked lighting, which the
game adds itself. Returns a uint8 RGB array of `texture_size` squared (top-left origin).

With `params.player_colour`, the parts the game tints with the owner's colour (string courses
between storeys and shutters, as the stock buildings mark thin bands) are painted light grey and
`paint_rgba` lowers their alpha to 0; everything else keeps alpha 255.
"""
import numpy as np

from .painter import PLAYER_GREY, Painter, _shade  # noqa: F401  (re-exported)
from .styles import STYLES


def paint(model):
    """The RGB texture."""
    return _paint(model)[0]


def paint_rgba(model):
    """The texture with its alpha: 0 where the player colour shows, 255 elsewhere."""
    rgb, alpha = _paint(model)
    return np.concatenate([rgb, alpha[:, :, None]], axis=2)


def _paint(model):
    pr = Painter(model)
    STYLES[model.params.style].paint(pr, model)
    return pr.finish()


def damaged(model, rgba, seed=None):
    """The texture of the damaged building, from the intact one: soot above some of the
    windows, slates missing from the roof, cracks in the walls. Drawn from the facade
    measurements, so the marks line up with the openings. The alpha (player colour) is kept."""
    p = model.params
    at = model.atlas
    rng = np.random.default_rng(p.seed + 1 if seed is None else seed)
    out = np.asarray(rgba).astype(np.float32).copy()
    h, w = out.shape[:2]
    k = at.size / w                              # the atlas is painted at a larger size
    ppm = at.density / k                         # texture pixels per metre

    def to_px(region, u, v):
        x, y = at.px(region, u, v)
        return x / k, y / k

    def darken(cx, cy, rx, ry, strength):
        x0, x1 = int(max(0, cx - rx)), int(min(w, cx + rx + 1))
        y0, y1 = int(max(0, cy - ry)), int(min(h, cy + ry + 1))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d = ((xx - cx) / max(rx, 1)) ** 2 + ((yy - cy) / max(ry, 1)) ** 2
        grain = rng.uniform(0.75, 1.0, d.shape).astype(np.float32)
        f = 1 - strength * np.clip(1 - d, 0, 1) ** 0.8 * grain
        out[y0:y1, x0:x1, :3] *= f[..., None]

    def crack(region, u, v, length):
        x, y = to_px(region, u, v)
        ang = rng.uniform(-2.2, -0.9)
        for _ in range(int(length * ppm)):
            ang += rng.uniform(-0.5, 0.5)
            x, y = x + np.cos(ang), y + np.sin(ang)
            if 0 <= int(x) < w and 0 <= int(y) < h:
                out[int(y), int(x), :3] *= 0.45

    style = STYLES[p.style]
    for region, spec in model.facades.items():
        tops = style.opening_tops(spec, p)
        for uc in spec["bays"]:
            for top in tops:
                if rng.random() > 0.45:
                    continue
                cx, cy = to_px(region, uc, top + 0.5)
                darken(cx, cy, 0.75 * ppm, 0.9 * ppm, rng.uniform(0.45, 0.7))
            if rng.random() < 0.3:
                crack(region, uc + rng.uniform(-0.8, 0.8), rng.uniform(0.3, 2.0), rng.uniform(1.0, 2.5))
    if "roof" in at:
        r = at["roof"]
        for _ in range(max(4, int(r.world_w * r.world_h / 12))):
            u, v = rng.uniform(0, r.world_w), rng.uniform(0, r.world_h)
            cx, cy = to_px("roof", u, v)
            darken(cx, cy, rng.uniform(0.3, 0.7) * ppm, rng.uniform(0.25, 0.5) * ppm, 0.8)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def save_png(array, path):
    """Writes an RGB uint8 array as PNG with the standard library only (zlib)."""
    import struct
    import zlib

    h, w, _ = array.shape
    raw = b"".join(b"\x00" + array[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)

