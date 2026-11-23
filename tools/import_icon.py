# SPDX-License-Identifier: GPL-3.0-or-later
"""Imports an icon drawn elsewhere (a PNG with a transparent background) into a game icon texture: a square,
uncompressed BGRA .ddt with one level, as a mod's own stat and unit type icons.

    venv\\Scripts\\python -I tools/import_icon.py --png <icon.png> --out <icon.ddt> [--aspect 0.65] [--size 32]
        [--set-height 890 --valign bottom]
        [--tint "#C75A21" --tint-seed X,Y [--tint-mid 177] [--tint-lighten 0.15]]
        [--sides 321,769 [--sides-cut 186,904] [--sides-scale 0.75] [--sides-tuck 30]] [--preview <x8.png>]

What it does, in order (nothing is redrawn):
- `--tint`: recolours one region of the picture, the pixels connected to the seed (X,Y in the PNG's pixels) that are
  brighter than its outline (`--tint-floor`, a 0-255 luminance between the outline's and the region's darkest part).
  Their grey ramp is mapped onto a ramp around the colour: the region's median luminance (or `--tint-mid`, the grey of
  its main face) becomes the colour itself, darker greys the colour darkened in proportion, lighter greys the colour
  mixed toward white, so shading, highlights and dark bands stay. `--tint-lighten f` mixes the colour toward white by
  f first. The outline and every other region keep their pixels.
- `--sides L,R`: the picture as a middle (columns L..R-1) between two sides (a winged bullet: the bullet between its
  wings), to make a wide picture narrower without redrawing it: `--sides-cut A,B` takes out the columns A..L-1 and
  R..B-1 (where the sides run straight, so their tips stay as drawn), `--sides-scale s` scales the sides (nearest),
  `--sides-tuck t` slides each side t pixels behind the middle; the sides keep their vertical centre and the middle
  is drawn over them;
- crops the picture to its visible pixels;
- `--aspect`: the share of its width a panel keeps when it draws a square icon (the minimized unit panel draws a
  type icon of an attack row in 11 x 17 pixels at 1920 x 1080: 0.65; the default 0.72 is make_type_icon's). The
  picture is widened by 1 / aspect so it shows with its own proportions in game; 1 keeps it as drawn;
- fits it in the square (`--size`), the longer side filling it, or at the scale where `--set-height` source pixels
  fill it (one scale for the pictures of a set), and reduces it by area averaging with premultiplied alpha: each texel
  is the mean of the picture's pixels it covers, so a pixel-art picture whose grid does not divide the size keeps
  every outline as a soft edge rather than losing rows or columns (a picture smaller than that, such as an icon
  .ddt whose content fills 28 of its 32 rows, is enlarged by linear interpolation instead);
- centres it, both sides of the same parity as the square so the margins are equal (a mark centred on its line);
  `--valign bottom` sets it on the bottom edge instead (busts cut at the waist).

`--preview` writes the result enlarged 8 times (nearest) on the panel's brown.
"""
import argparse
import collections
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402
from core.pngio import encode_png, read_png  # noqa: E402

PANEL_BROWN = (60, 35, 25)


def rgba_of(a):
    """Any 8-bit grey, grey+alpha, RGB or RGBA array as H x W x 4."""
    a = np.asarray(a, np.uint8)
    if a.ndim == 2:
        a = a[:, :, None]
    n = a.shape[2]
    if n == 1:
        a = np.concatenate([a, a, a], axis=2)
    elif n == 2:
        a = np.concatenate([a[:, :, :1]] * 3 + [a[:, :, 1:]], axis=2)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, np.uint8)], axis=2)
    return a


def parse_colour(text):
    t = text.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError(f"colour {text!r}: expected #RRGGBB")
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    rgb = np.asarray(rgb, np.float64)
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def region(rgba, seed, floor=35):
    """Boolean mask of the visible pixels connected (4-neighbours) to `seed` (x, y) whose luminance is above
    `floor`: a part of the picture bounded by its dark outline."""
    h, w = rgba.shape[:2]
    ok = (rgba[..., 3] > 127) & (luminance(rgba[..., :3]) > floor)
    x0, y0 = seed
    if not (0 <= x0 < w and 0 <= y0 < h) or not ok[y0, x0]:
        raise ValueError(f"seed {seed} is not inside a region brighter than {floor}")
    mask = np.zeros((h, w), bool)
    mask[y0, x0] = True
    todo = collections.deque([(y0, x0)])
    while todo:
        y, x = todo.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and ok[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True
                todo.append((ny, nx))
    return mask


def tint(rgba, mask, colour, lighten=0.0, white=0.8, mid=None):
    """`rgba` with the pixels of `mask` recoloured: the grey ramp onto a ramp around `colour` (see the module)."""
    out = np.array(rgba, np.uint8)
    base = np.array(colour, np.float64)
    base = base + (255 - base) * lighten
    lum = luminance(out[..., :3])[mask]
    mid = max(float(np.median(lum) if mid is None else mid), 1.0)
    hi = base + (255 - base) * white
    t = lum[:, None]
    dark = base * (t / mid)
    light = base + (hi - base) * ((t - mid) / max(255 - mid, 1))
    new = np.where(t <= mid, dark, light)
    out[..., :3][mask] = np.clip(np.round(new), 0, 255).astype(np.uint8)
    return out


def _over(dst, layer, x, y):
    """`layer` pasted at (x, y) over `dst`, where its alpha is above half."""
    h, w = layer.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, dst.shape[1]), min(y + h, dst.shape[0])
    if x1 > x0 and y1 > y0:
        part = layer[y0 - y:y1 - y, x0 - x:x1 - x]
        dst[y0:y1, x0:x1] = np.where(part[..., 3:4] > 127, part, dst[y0:y1, x0:x1])


def compose_sides(rgba, sides, cut=None, scale=1.0, tuck=0):
    """The picture with its two sides (columns before sides[0], from sides[1] on) shortened (`cut`: the columns
    cut[0]..sides[0]-1 and sides[1]..cut[1]-1 go), scaled (nearest) and slid `tuck` pixels behind the middle."""
    a = rgba_of(rgba)
    l, r = sides
    lc, rc = cut if cut else (l, r)
    left, middle, right = a[:, :lc], a[:, l:r], a[:, rc:]
    if scale != 1.0:
        def nearest(part):
            h, w = part.shape[:2]
            nh, nw = max(1, round(h * scale)), max(1, round(w * scale))
            return part[(np.arange(nh) * h // nh)[:, None], (np.arange(nw) * w // nw)[None, :]]
        left, right = nearest(left), nearest(right)
    ys = np.nonzero(a[:, :l, 3] > 127)[0]
    cy = (ys.min() + ys.max()) / 2 if len(ys) else a.shape[0] / 2
    lv, rv = left.shape[1] - tuck, right.shape[1] - tuck
    out = np.zeros((a.shape[0], lv + middle.shape[1] + rv, 4), np.uint8)
    y = int(round(cy - left.shape[0] / 2)) if scale != 1.0 else 0
    _over(out, left, 0, y)
    _over(out, right, out.shape[1] - right.shape[1], y)
    _over(out, middle, lv, 0)
    return out


def _even_to(n, size):
    """`n` rounded to the nearest whole number of the parity of `size` (equal margins), within 1..size."""
    lo = int(np.floor(n))
    cands = [c for c in (lo - 1, lo, lo + 1, lo + 2) if 1 <= c <= size and (size - c) % 2 == 0]
    return min(cands, key=lambda c: abs(c - n))


def _linear_resize(img, h, w):
    """H x W x C float image resampled to h x w by linear interpolation between pixel centres."""
    def axis(n_in, n_out):
        c = np.clip((np.arange(n_out) + 0.5) * n_in / n_out - 0.5, 0, n_in - 1)
        i0 = np.floor(c).astype(int)
        return i0, np.minimum(i0 + 1, n_in - 1), c - i0
    y0, y1, fy = axis(img.shape[0], h)
    x0, x1, fx = axis(img.shape[1], w)
    rows = img[y0] * (1 - fy)[:, None, None] + img[y1] * fy[:, None, None]
    return rows[:, x0] * (1 - fx)[None, :, None] + rows[:, x1] * fx[None, :, None]


def fit(rgba, size=32, aspect=0.72, set_height=None, valign="centre"):
    """The picture cropped to its visible pixels, widened by 1 / aspect, reduced by area averaging into a
    size x size square and centred (uint8 RGBA; colour 0 where alpha is 0). `set_height`: the source height that
    fills the square, so the pictures of one set keep one scale; `valign` "bottom" sets the picture on the
    square's bottom edge (busts cut at the waist)."""
    a = rgba_of(rgba)
    ys, xs = np.nonzero(a[..., 3])
    if not len(xs):
        raise ValueError("the picture has no visible pixel")
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float64)
    h, w = a.shape[:2]
    wide = w / aspect
    scale = size / max(h, wide) if set_height is None else size / set_height
    if max(h, wide) * scale > size + 0.5:
        raise ValueError(f"at that scale the picture ({w / aspect:.0f} x {h} widened) is larger than the square")
    tw = _even_to(wide * scale, size)
    th = _even_to(h * scale, size) if valign == "centre" else max(1, min(size, int(round(h * scale))))
    prem = a.copy()
    prem[..., :3] *= a[..., 3:4] / 255.0
    if th > h or tw > w:  # a small picture enlarged (a 28-texel icon to 32): linear, not area
        small = _linear_resize(prem, th, tw)
    else:
        small = ddt.area_resize(prem, th, tw).astype(np.float64)
    alpha = small[..., 3:4]
    small[..., :3] = np.where(alpha > 0, small[..., :3] * 255.0 / np.maximum(alpha, 1e-9), 0)
    out = np.zeros((size, size, 4), np.uint8)
    y0, x0 = ((size - th) // 2 if valign == "centre" else size - th), (size - tw) // 2
    out[y0:y0 + th, x0:x0 + tw] = np.clip(np.round(small), 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out


def encode(icon):
    """As a mod's own stat icons: BGRA, alpha "transparent" (4), usage 0, one level."""
    return ddt.write_bgra(icon, alpha=4, usage=0, mips=False)


def enlarged(icon, zoom=8, bg=PANEL_BROWN):
    e = icon.astype(np.float32).repeat(zoom, 0).repeat(zoom, 1)
    a = e[..., 3:4] / 255.0
    return (e[..., :3] * a + np.array(bg, np.float32) * (1 - a)).astype(np.uint8)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--png", required=True, help="the drawn icon, transparent background (a .ddt is read too)")
    ap.add_argument("--out", help="the .ddt to write")
    ap.add_argument("--size", type=int, default=32, help="the square's side in texels (32)")
    ap.add_argument("--aspect", type=float, default=0.72,
                    help="the share of its width the panel keeps (0.72; 1 = drawn as is)")
    ap.add_argument("--set-height", type=float,
                    help="the source height (pixels) that fills the square: one scale for a set (this picture's)")
    ap.add_argument("--valign", choices=("centre", "bottom"), default="centre", help="vertical place (centre)")
    ap.add_argument("--tint", help="recolour a region toward this #RRGGBB")
    ap.add_argument("--tint-seed", help="X,Y: a pixel of that region in the PNG")
    ap.add_argument("--tint-floor", type=float, default=35,
                    help="a luminance between the outline's and the region's darkest part (35)")
    ap.add_argument("--tint-mid", type=float, help="the grey (0-255 luminance) that becomes the colour (the median)")
    ap.add_argument("--tint-lighten", type=float, default=0.0, help="mix the colour toward white first (0..1)")
    ap.add_argument("--sides", help="L,R: the middle's first column and the right side's first column")
    ap.add_argument("--sides-cut", help="A,B: the columns A..L-1 and R..B-1 go (the sides shortened)")
    ap.add_argument("--sides-scale", type=float, default=1.0, help="scale of the sides (nearest)")
    ap.add_argument("--sides-tuck", type=int, default=0, help="pixels each side slides behind the middle")
    ap.add_argument("--preview", help="write the icon enlarged 8 times on the panel's brown (PNG)")
    a = ap.parse_args(argv)
    raw = pathlib.Path(a.png).read_bytes()
    src = rgba_of(ddt.decode(raw) if a.png.lower().endswith(".ddt") else read_png(raw))
    if a.tint:
        if not a.tint_seed:
            ap.error("--tint needs --tint-seed")
        seed = tuple(int(v) for v in a.tint_seed.split(","))
        src = tint(src, region(src, seed, a.tint_floor), parse_colour(a.tint), a.tint_lighten, mid=a.tint_mid)
    if a.sides:
        pair = lambda v: tuple(int(x) for x in v.split(","))  # noqa: E731
        src = compose_sides(src, pair(a.sides), pair(a.sides_cut) if a.sides_cut else None, a.sides_scale,
                            a.sides_tuck)
    icon = fit(src, a.size, a.aspect, a.set_height, a.valign)
    if a.out:
        data = encode(icon)
        out = pathlib.Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"{out}: {len(data)} bytes, {ddt.read_header(data).describe()}")
    if a.preview:
        pathlib.Path(a.preview).write_bytes(encode_png(enlarged(icon)))
        print(f"{a.preview}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
