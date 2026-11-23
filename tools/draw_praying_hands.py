# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws a "praying hands" icon (two hands pressed together, fingers up) as an RGBA PNG, in the style of
the painted resource icons of the game's resource panel: rounded, lit from the top left, a soft dark rim,
no hard black outline. It is drawn from shapes only (no game art).

    venv\\Scripts\\python -I tools/draw_praying_hands.py --out <icon.png> [--size 128] [--halo 0.35]
                                                         [--tilt 6] [--width 1.15] [--sheet <preview.png>]

How it is drawn (all in a 1024-pixel square, then reduced with a box filter):
- the parts are masks: the far hand (behind, right), the near hand (left), its four fingers, the two thumbs
  laid over the palms, a white cuff on each wrist and the sleeve below them;
- each part's height is its mask blurred (a rounded bump); the normal of that height lit by a light from the
  top left gives the shading (diffuse, a little specular, an ambient term), and where a part lies over another
  the lower one is darkened (contact shadow), so the fingers and thumbs read as separate;
- a dark brown rim (the shape grown by a few pixels, blurred) and an optional pale gold halo behind.

`--sheet` writes the icon at its size, at 64, 34 and 24 pixels (the panel draws it about 34 texels tall in its
texture, 17 to 24 pixels on screen) on the panel's dark wood colour.
"""
import argparse
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

N = 1024                     # drawing size
LIGHT = np.array([-0.55, -0.65, 0.52])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def _mask(polys=(), ellipses=(), blur=0.0):
    im = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon([(x * N, y * N) for x, y in p], fill=255)
    for (x0, y0, x1, y1) in ellipses:
        d.ellipse([x0 * N, y0 * N, x1 * N, y1 * N], fill=255)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * N))
    return np.asarray(im, np.float32) / 255.0


def _smooth_poly(points, steps=12):
    """A closed Catmull-Rom curve through the points (unit coordinates)."""
    out = []
    n = len(points)
    for i in range(n):
        p0, p1, p2, p3 = (np.array(points[(i + k) % n], float) for k in (-1, 0, 1, 2))
        for t in np.linspace(0, 1, steps, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)))
    return out


def _height(mask, r):
    im = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r * N))
    h = np.asarray(im, np.float32) / 255.0
    return np.sqrt(np.clip(h, 0, 1)) * mask


def _shade(h, base, dark, light, strength=10.0, spec=0.35, ambient=0.32):
    gy, gx = np.gradient(h * strength * N / 100.0)
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    lam = np.clip((nrm * LIGHT).sum(-1), 0, 1)
    half = LIGHT + np.array([0, 0, 1.0])
    half /= np.linalg.norm(half)
    sp = np.clip((nrm * half).sum(-1), 0, 1) ** 24 * spec
    t = np.clip(ambient + (1 - ambient) * lam, 0, 1)[..., None]
    base, dark, light = (np.array(c, np.float32) for c in (base, dark, light))
    col = np.where(t < 0.62, dark + (base - dark) * (t / 0.62), base + (light - base) * ((t - 0.62) / 0.38))
    return np.clip(col + sp[..., None] * 255, 0, 255)


def _rot(points, deg, cx=0.5, cy=0.55):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


def draw(size=128, halo=0.35, tilt=6.0, width=1.15):
    T = lambda pts: _rot([(0.5 + (x - 0.5) * width, y) for x, y in pts], tilt)  # noqa: E731
    SKIN, SKIN_D, SKIN_L = (208, 146, 100), (96, 50, 28), (255, 216, 172)
    FAR, FAR_D, FAR_L = (150, 96, 62), (70, 36, 20), (200, 146, 104)

    # far hand: its fingertips show above and right of the near hand's
    far = _mask([T(_smooth_poly([(0.545, 0.085), (0.585, 0.11), (0.625, 0.20), (0.665, 0.33), (0.69, 0.47),
                                 (0.685, 0.60), (0.655, 0.71), (0.60, 0.77), (0.53, 0.74), (0.525, 0.30)]))])
    # near hand: back of the hand on the left, four fingertips stepping down from the middle one
    near = _mask([T(_smooth_poly([(0.515, 0.06), (0.49, 0.075), (0.47, 0.105), (0.445, 0.135), (0.425, 0.17),
                                  (0.40, 0.215), (0.385, 0.25), (0.36, 0.33), (0.335, 0.44), (0.325, 0.55),
                                  (0.345, 0.66), (0.39, 0.745), (0.47, 0.785), (0.545, 0.75), (0.56, 0.55),
                                  (0.555, 0.30), (0.545, 0.12)]))])
    # the two thumbs, side by side along the front, tips up
    thumbs = _mask([T(_smooth_poly([(0.505, 0.375), (0.535, 0.39), (0.555, 0.45), (0.565, 0.58), (0.555, 0.69),
                                    (0.51, 0.72), (0.47, 0.69), (0.465, 0.56), (0.475, 0.43)]))])
    cuff = _mask([T(_smooth_poly([(0.37, 0.735), (0.47, 0.77), (0.60, 0.755), (0.665, 0.715), (0.69, 0.775),
                                  (0.675, 0.835), (0.56, 0.865), (0.43, 0.86), (0.355, 0.82), (0.345, 0.77)], 10))])
    sleeve = _mask([T(_smooth_poly([(0.36, 0.81), (0.50, 0.845), (0.68, 0.81), (0.71, 0.93), (0.52, 0.965),
                                    (0.33, 0.93)], 10))])
    sleeve *= np.clip((0.985 - np.arange(N)[:, None] / N) / 0.09, 0, 1)      # fades out at the bottom

    rgb = np.zeros((N, N, 3), np.float32)
    a = np.zeros((N, N), np.float32)

    def over(col, m):
        nonlocal rgb, a
        rgb = rgb * (1 - m[..., None]) + col * m[..., None]
        a = a + m * (1 - a)

    def contact(m, r=0.018, k=0.45):
        sh = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(r * N)), np.float32) / 255.0
        return 1 - k * sh

    # sleeve (brown wool, like a monk's habit), then the far hand, the near hand, its fingers' creases, the thumbs, the cuffs
    over(_shade(_height(sleeve, 0.05), (104, 62, 44), (40, 22, 14), (156, 102, 74), strength=6), sleeve)
    far_col = _shade(_height(far, 0.06), FAR, FAR_D, FAR_L)
    far_col *= contact(near, 0.02, 0.55)[..., None]
    over(far_col, far)
    near_col = _shade(_height(near, 0.055), SKIN, SKIN_D, SKIN_L)
    # finger creases on the near hand: three dark curves from the tips down to the knuckles
    crease = Image.new("L", (N, N), 0)
    cd = ImageDraw.Draw(crease)
    for k, (x0, y0, x1, y1) in enumerate([(0.493, 0.095, 0.478, 0.36), (0.452, 0.145, 0.432, 0.38),
                                          (0.412, 0.215, 0.392, 0.41)]):
        pts = T([(x0, y0), ((x0 + x1) / 2 - 0.006, (y0 + y1) / 2), (x1, y1)])
        cd.line([(x * N, y * N) for x, y in pts], fill=230, width=int(0.016 * N), joint="curve")
    crease = np.asarray(crease.filter(ImageFilter.GaussianBlur(0.004 * N)), np.float32) / 255.0 * near
    near_col *= (1 - 0.7 * crease)[..., None]
    # knuckle highlights: short pale strokes on the back of the hand
    near_col *= contact(thumbs, 0.022, 0.40)[..., None]
    over(near_col, near)
    th = _shade(_height(thumbs, 0.04), SKIN, SKIN_D, SKIN_L, strength=12)
    # the line between the two thumbs and a nail on the front one
    tl = Image.new("L", (N, N), 0)
    td = ImageDraw.Draw(tl)
    p = T([(0.522, 0.40), (0.518, 0.55), (0.512, 0.71)])
    td.line([(x * N, y * N) for x, y in p], fill=220, width=int(0.009 * N), joint="curve")
    tl = np.asarray(tl.filter(ImageFilter.GaussianBlur(0.004 * N)), np.float32) / 255.0 * thumbs
    th *= (1 - 0.5 * tl)[..., None]
    nail = _mask([T(_smooth_poly([(0.502, 0.395), (0.52, 0.392), (0.525, 0.43), (0.505, 0.44)], 8))], blur=0.003)
    th = th * (1 - 0.6 * nail[..., None]) + np.array([255, 226, 200], np.float32) * 0.6 * nail[..., None]
    over(th, thumbs)
    over(_shade(_height(cuff, 0.03), (236, 232, 222), (130, 124, 116), (255, 255, 250), strength=8), cuff)

    # soft dark rim around the whole figure (like the painted icons' edges)
    grown = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(17))
    grown = np.asarray(grown.filter(ImageFilter.GaussianBlur(0.006 * N)), np.float32) / 255.0
    rim_a = np.clip(grown - a, 0, 1)
    out_rgb = rgb * a[..., None] + np.array([34, 18, 10], np.float32) * rim_a[..., None]
    out_a = a + rim_a
    if halo > 0:
        hm = _mask(ellipses=[(0.24, 0.03, 0.80, 0.62)], blur=0.07) * halo
        hcol = np.array([255, 236, 176], np.float32)
        out_rgb = out_rgb + hcol * (hm * (1 - out_a))[..., None]
        out_a = out_a + hm * (1 - out_a)
    rgba = np.dstack([np.where(out_a[..., None] > 1e-4, out_rgb / np.maximum(out_a, 1e-4)[..., None], 0),
                      out_a * 255])
    im = Image.fromarray(np.clip(rgba + 0.5, 0, 255).astype(np.uint8), "RGBA")
    return im.resize((size, size), Image.BOX)


def sheet(icon, path):
    bg = (40, 20, 16, 255)
    sizes = [icon.width, 64, 34, 24]
    w = sum(sizes) + 20 * (len(sizes) + 1)
    out = Image.new("RGBA", (w, icon.height + 40), bg)
    x = 20
    for s in sizes:
        im = icon.resize((s, s), Image.LANCZOS)
        out.alpha_composite(im, (x, 20 + (icon.height - s) // 2))
        x += s + 20
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--halo", type=float, default=0.35)
    ap.add_argument("--tilt", type=float, default=6.0)
    ap.add_argument("--width", type=float, default=1.15, help="horizontal stretch of the figure")
    ap.add_argument("--sheet")
    a = ap.parse_args()
    icon = draw(a.size, a.halo, a.tilt, a.width)
    icon.save(a.out)
    if a.sheet:
        sheet(icon, a.sheet)
    print(f"praying hands: {a.out} ({a.size} x {a.size})")


if __name__ == "__main__":
    main()
