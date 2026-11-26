# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-lays the painted rows of a resource panel (the column of resource icons the game paints into its in-game
interface textures: a dark plank ending in an arrow, a coloured smear behind the icon, the icon, rope bars
between the rows) and inserts new rows with an icon of your own, so a new resource gets a row that looks like
the others. Every row of the panel is moved, and scaled when the rows get closer, from the original texture:
re-run it on the originals with another icon to swap the icon in one step.

    python -I tools/panel_rows.py --spec <spec.json> --in <folder> --out <folder> [--png <folder>]
        [--positions <rows.json>]

`--in` holds the original textures at the paths the spec names (a game copy's root, for instance); `--out`
gets the rebuilt `.ddt` files at the same relative paths (same format, alpha mode and usage as the original;
only the 4 x 4 blocks that changed are encoded again, the others keep their bytes); `--png` also writes each texture as a PNG to look at; `--positions` writes, for every panel, the
texture rows (bar tops) of the new layout, which a layout file's gadgets are then placed on.

The spec (JSON; paths relative to the spec's folder):

    {"icons": {"faith": {"file": "faith-icon.png", "height": 0.86, "smear": [70, 105, 170]}},
     "textures": [{"file": "art/ui/ingame/eur_max_ui.ddt", "panels": [{
         "id": "EurMax", "x": [440, 684], "dx": 0,
         "rows": [["oil", 784, 834], ["food", 834, 880], ...], "bottom": 1018,
         "order": ["oil", "faith", "food", ...], "blank_from": "gold",
         "header": {"top": 745, "keep_top": 22}}]}]}

- `x`: the panel's columns (left post to right post); `dx`: its offset from the reference geometry below (a
  panel painted further right in its texture);
- `rows`: each painted row from the top of its rope bar to the top of the next one; `bottom`: the top of the
  bar under the last row (it stays where it is);
- `order`: the new rows, top to bottom: a painted row by name or an icon of `icons`. They share the space from
  the first row's top (or `header.top` + the new header height) to `bottom` evenly;
- `blank_from`: the painted row the new rows are made from (its plank and wood, its icon and smear removed);
- `header` (optional): a header box above the rows (a minimized panel's population box) is made shorter: its
  top `keep_top` texels stay, then its bottom part, so the rows start `shrink` texels higher;
- `keep_bars` (optional, false by default): a moved row keeps its rope bar at its own height (`BAR` texels) and
  only its body is resampled, its icon zone by the body's factor. Use it when rows get taller (a row left out
  of `order`, the others spread over its space), so the bars do not get thicker than the panel's other bars;
- `icon_scale_max` (optional): the most a moved row's icon zone is scaled up. A taller row's body is still
  stretched to its height, but its icon (with the plank's arrow and the smear around it) is scaled by at most
  this factor and centred in the body, feathered on all sides, so the icons do not grow into the numbers that
  the layout puts to their right.

A row left out of `order` is dropped: the remaining rows share its space. A texture may name `out`, the path
(relative to `--out`) to write it to instead of `file`, so a variant of a texture (a panel without a row) can sit
beside the original; `--positions` then names that path as the panel's texture.

How a row is moved: its strip is resampled to the new height; its icon zone (the plank's arrow, the smear and
the icon) is scaled by the same factor in both directions and laid over it around the icon's centre, with
feathered sides, so icons keep their shape. A new row: the blank strip, a smear in the icon's colour shaped as
the others (a chevron band following the plank's arrow, textured, fading to the right), the icon scaled to
`height` x the strip's height, centred on the row; then moved like the others.

Reference geometry (texels, the Asian full panel `ASI_UI_MAX`; `dx` shifts it): icon zone x 495..592, icon
centre x 536, the plank's arrow from x 498 (at the body's top and bottom) to its tip at x 513 (middle), the
bar's rope 9 texels high.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from aoe3_blender_tools.aoe3game import ddt  # noqa: E402

ZONE = (495, 592)
ICON_CX = 536
ARROW = (498, 513)
BAR = 9
FEATHER = 5
WOOD_FROM = (612, 668)       # plain wood right of the icons (and of their smears), copied over a removed icon


def _resize(a, w, h):
    """Float RGBA array resampled to w x h (Lanczos, per channel, alpha premultiplied)."""
    a = np.asarray(a, np.float32)
    if a.shape[1] == w and a.shape[0] == h:
        return a.copy()
    al = a[..., 3:4] / 255.0
    pre = np.concatenate([a[..., :3] * al, a[..., 3:4]], -1)
    chans = [np.asarray(Image.fromarray(pre[..., c]).resize((w, h), Image.LANCZOS), np.float32)
             for c in range(4)]
    out = np.stack(chans, -1)
    out[..., 3] = np.clip(out[..., 3], 0, 255)
    alo = np.maximum(out[..., 3:4] / 255.0, 1e-4)
    out[..., :3] = np.where(out[..., 3:4] > 0.5, out[..., :3] / alo, 0)
    return np.clip(out, 0, 255)


def _ramp(w, f):
    r = np.ones(w, np.float32)
    f = max(1, min(f, w // 2))
    r[:f] = (np.arange(f) + 0.5) / f
    r[-f:] = r[:f][::-1]
    return r


def arrow_x(h, dx=0):
    """The plank's arrow edge per row of a body h texels high (x of the first non-plank texel)."""
    t = (np.arange(h) + 0.5) / h
    return ARROW[0] + dx + (ARROW[1] - ARROW[0]) * (1 - np.abs(2 * t - 1))


def blank_strip(strip, x0, dx=0):
    """A row strip with its smear and icon replaced by the plain wood right of them: the plank and its
    arrow stay, so the strip can take another icon."""
    s = strip.copy()
    h = s.shape[0]
    body = np.arange(h) >= BAR
    ax = np.full(h, ARROW[0] + dx, np.float32)
    ax[body] = arrow_x(int(body.sum()), dx)
    w0, w1 = WOOD_FROM[0] + dx - x0, WOOD_FROM[1] + dx - x0
    wood = strip[:, w0:w1]
    zl, zr = ZONE[0] + dx - x0, ZONE[1] + dx - x0
    fade = 16                                    # texels over which the copy meets the wood right of it
    for y in range(BAR, h):
        a = ax[y] - x0 - 1.5                     # keep the plank's edge texel
        for x in range(int(a), zr):
            # the same shift on every row, so the wood's grain stays straight
            ww = wood.shape[1]
            i = (x - zl) % (2 * ww)
            src = wood[y, i if i < ww else 2 * ww - 1 - i]      # mirrored: no seam where it repeats
            k = float(np.clip(x - a, 0, 1))      # one texel of blend at the arrow
            k *= float(np.clip((zr - x) / fade, 0, 1)) if x > zr - fade else 1.0
            s[y, x] = s[y, x] * (1 - k) + src * k
    # the icon may reach into the bar above: put back a clean bar over the zone, from the bar's own left part
    zl, zr = ZONE[0] + dx - x0, ZONE[1] + dx - x0
    clean = strip[:BAR, zl - (zr - zl) - 4:zl - 4]
    if clean.shape[1] == zr - zl:
        s[:BAR, zl:zr] = clean
    return s


def _noise(h, w, seed):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    for k, amp in ((4, 0.5), (8, 0.3), (16, 0.2)):
        g = rng.random((max(2, h // k + 2), max(2, w // k + 2))).astype(np.float32)
        acc += amp * np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), np.float32)
    return (acc - acc.min()) / max(1e-6, acc.max() - acc.min())


def paint_new_row(strip, x0, dx, icon, height, smear):
    """A blank strip with a smear in the icon's colour and the icon."""
    s = strip.copy()
    h, w = s.shape[:2]
    bh = h - BAR
    ax = arrow_x(bh, dx) - x0
    width = 1.05 * bh + 4                        # the band's width, like the painted smears
    xs = np.arange(w, dtype=np.float32)[None, :]
    tex = _noise(bh, w, 101)
    edge = _noise(bh, 8, 7)[:, :1] * 0.2 * width     # a ragged right edge, as a brush leaves it
    d = xs - ax[:, None]                         # distance right of the arrow
    reach = width - edge
    m = np.clip(d / 1.5, 0, 1) * np.clip(1 - d / reach, 0, 1) ** 0.8
    # soft top and bottom of the band
    ty = (np.arange(bh, dtype=np.float32) + 0.5) / bh
    m *= np.clip(np.minimum(ty, 1 - ty) / 0.10, 0, 1)[:, None]
    col = np.array(smear, np.float32)
    shade = (0.35 + 0.95 * tex ** 1.4)[..., None]
    paint = np.clip(col * shade, 0, 255)
    a = (0.95 * m)[..., None]
    s[BAR:, :, :3] = s[BAR:, :, :3] * (1 - a) + paint * a
    # the icon
    ih = max(4, int(round(height * h)))
    ic = np.asarray(icon.resize((ih, ih), Image.LANCZOS), np.float32)
    cy = BAR + bh / 2.0
    top = int(round(cy - ih / 2.0))
    left = int(round(ICON_CX + dx - x0 - ih / 2.0))
    y0, y1 = max(0, top), min(h, top + ih)
    xa, xb = max(0, left), min(w, left + ih)
    piece = ic[y0 - top:y1 - top, xa - left:xb - left]
    al = piece[..., 3:4] / 255.0
    s[y0:y1, xa:xb, :3] = s[y0:y1, xa:xb, :3] * (1 - al) + piece[..., :3] * al
    return s


def move_row(strip, h_t, x0, dx, keep_bar=False, icon_max=None, blank=None):
    """A row strip at a new height: resampled, its icon zone scaled the same in both directions. keep_bar: the
    rope bar (the first BAR rows) stays as it is and only the body under it is moved. icon_max: the icon zone is
    scaled up by at most this factor, centred in the row and feathered on every side, over the row without its
    icon (blank: that row, else blank_strip's)."""
    h_s, w = strip.shape[:2]
    if keep_bar and h_t != h_s:
        bl = blank_strip(strip, x0, dx)[BAR:] if icon_max is not None else None
        body = move_row(strip[BAR:], h_t - BAR, x0, dx, icon_max=icon_max, blank=bl)
        return np.concatenate([np.asarray(strip[:BAR], np.float32), body], 0)
    if icon_max is not None and h_t > icon_max * h_s:
        bg = _resize(blank_strip(strip, x0, dx) if blank is None else blank, w, h_t)
        c = icon_max
        zl, zr = ZONE[0] + dx - x0, ZONE[1] + dx - x0
        cx = ICON_CX + dx - x0
        zw, zh = max(2, int(round(c * (zr - zl)))), max(2, int(round(c * h_s)))
        patch = _resize(strip[:, zl:zr], zw, zh)
        px, py = int(round(cx - c * (cx - zl))), int(round((h_t - zh) / 2))
        ramp = (_ramp(zh, FEATHER)[:, None] * _ramp(zw, FEATHER)[None, :])[..., None]
        bg[py:py + zh, px:px + zw] = bg[py:py + zh, px:px + zw] * (1 - ramp) + patch * ramp
        return bg
    bg = _resize(strip, w, h_t)
    if h_t == h_s:
        return bg
    s = h_t / h_s
    zl, zr = ZONE[0] + dx - x0, ZONE[1] + dx - x0
    cx = ICON_CX + dx - x0
    zw = max(2, int(round(s * (zr - zl))))
    patch = _resize(strip[:, zl:zr], zw, h_t)
    px = int(round(cx - s * (cx - zl)))
    ramp = _ramp(zw, FEATHER)[None, :, None]
    bg[:, px:px + zw] = bg[:, px:px + zw] * (1 - ramp) + patch * ramp
    return bg


def shrink_header(img, top, old_bottom, new_bottom, keep_top, x0, x1, blend=4):
    """The header box img[top:old_bottom] made new_bottom - top high: its first keep_top rows, then its last
    rows, blended over a few rows."""
    h_new = new_bottom - top
    first = img[top:top + keep_top, x0:x1]
    rest = h_new - keep_top
    last = img[old_bottom - rest - blend:old_bottom, x0:x1]
    out = np.zeros((h_new, x1 - x0, 4), np.float32)
    out[:keep_top] = first
    out[keep_top:] = last[blend:]
    # blend: the rows just after keep_top mix the top part's continuation into the bottom part
    cont = img[top + keep_top:top + keep_top + blend, x0:x1]
    for i in range(blend):
        k = (i + 1) / (blend + 1)
        out[keep_top + i] = cont[i] * (1 - k) + last[blend + i] * k
    return out


def build_panel(img, panel, icons, base):
    x0, x1 = panel["x"]
    dx = panel.get("dx", 0)
    rows = {n: (a, b) for n, a, b in panel["rows"]}
    first_top = panel["rows"][0][1]
    bottom = panel["bottom"]
    out = img.copy()
    top = first_top
    hdr = panel.get("header")
    if hdr:
        top = first_top - hdr["shrink"]
        out[hdr["top"]:top, x0:x1] = shrink_header(img, hdr["top"], first_top, top, hdr["keep_top"], x0, x1)
    order = panel["order"]
    n = len(order)
    tops = [int(round(top + k * (bottom - top) / n)) for k in range(n + 1)]
    blank_src = rows[panel["blank_from"]]
    # the first row keeps the panel's own top bar (a minimized panel's is wider and decorated); a row that had
    # it and is now lower takes an inner bar (the blank row's)
    first_bar = img[first_top:first_top + BAR, x0:x1]
    inner_bar = img[blank_src[0]:blank_src[0] + BAR, x0:x1]
    for k, name in enumerate(order):
        if name in rows:
            a, b = rows[name]
            strip = img[a:b, x0:x1].copy()
        else:
            ic = icons[name]
            a, b = blank_src
            strip = blank_strip(img[a:b, x0:x1], x0, dx)
            strip = paint_new_row(strip, x0, dx, ic["image"], ic.get("height", 0.86), ic.get("smear", [90, 90, 90]))
        had_first = name in rows and a == first_top
        if k == 0 and not had_first:
            strip[:BAR] = first_bar
        elif k > 0 and had_first:
            strip[:BAR] = inner_bar
        out[tops[k]:tops[k + 1], x0:x1] = move_row(strip, tops[k + 1] - tops[k], x0, dx,
                                                   panel.get("keep_bars", False), panel.get("icon_scale_max"))
    return out, tops


def encode_like(data, hd, rgba):
    """The texture in the original's format with the new pixels (aoe3game/ddt.write_like): for a one-level
    DXT1/DXT3/DXT5 texture only the 4 x 4 blocks whose pixels changed are encoded again (the refined encoder);
    every other block keeps the original's bytes, so the rest of the texture is byte for byte the same. Other
    formats are written whole (changed -1)."""
    return ddt.write_like(data, rgba)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--png")
    ap.add_argument("--positions")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.spec))
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    icons = {}
    for name, ic in spec.get("icons", {}).items():
        ic = dict(ic)
        ic["image"] = Image.open(os.path.join(base, ic["file"])).convert("RGBA")
        icons[name] = ic
    positions = {}
    for t in spec["textures"]:
        path = os.path.join(a.src, t["file"])
        with open(path, "rb") as f:
            data = f.read()
        hd = ddt.read_header(data)
        img = ddt.decode(data).astype(np.float32)
        for panel in t["panels"]:
            img, tops = build_panel(img, panel, icons, base)
            positions[panel["id"]] = {"texture": t.get("out", t["file"]), "row_tops": tops, "order": panel["order"],
                                      "header_top": panel.get("header", {}).get("top"),
                                      "x": panel["x"]}
        rgba = np.clip(img + 0.5, 0, 255).astype(np.uint8)
        out_data, changed = encode_like(data, hd, rgba)
        dst = os.path.join(a.out, t.get("out", t["file"]))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(out_data)
        if a.png:
            p = os.path.join(a.png, os.path.splitext(os.path.basename(t.get("out", t["file"])))[0] + ".png")
            os.makedirs(a.png, exist_ok=True)
            Image.fromarray(ddt.decode(out_data), "RGBA").save(p)
        print(f"panel_rows: {t.get('out', t['file'])}: {', '.join(p['id'] for p in t['panels'])} ({changed} blocks re-encoded)")
    if a.positions:
        with open(a.positions, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=1)


if __name__ == "__main__":
    main()
