# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws small stat icons, the size and format of the game's own stat icons (the 16x16 pictures that rows
of the unit panels put after a value: damage types, range, bonuses): 16x16 texels, DXT3, one mip level,
transparent outside the glyph.

    venv\\Scripts\\python -I tools/make_stat_icon.py [--glyph stopwatch] [--out <file.ddt>] [--png <preview.png>]
                                                  [--check]
    venv\\Scripts\\python -I tools/make_stat_icon.py --all <folder> [--png <sheet.png>] [--check]

Glyphs (the file name `--all` gives each one):
- `stopwatch` (`stat_icon_rof.ddt`): a rate of fire / reload time: a brass case with a crown, a pale face,
  a dark rim and two hands;
- `hourglass` (`stat_icon_traintime.ddt`): a training time: two glass bulbs in a wooden frame, sand below;
- `heart` (`stat_icon_hitpoints.ddt`): hit points: a red heart with a light highlight;
- `shield` (`stat_icon_armor.ddt`): armor / resistance: a steel heater shield with a gold rim;
- `eye` (`stat_icon_los.ddt`): line of sight: an open eye with a blue iris.

Each picture is drawn analytically at 8 samples per texel side and averaged (soft edges, like the stock
icons' anti-aliased outlines), then outlined in a dark brown as the stock stat icons are. No pixel comes from
the game. `--check` exits with code 1 if a file on disk differs from what would be written.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

SIZE = 16
SS = 8  # samples per texel side
OUT = ROOT / "out" / "staticons" / "stat_icon_rof.ddt"

OUTLINE = (40, 26, 14)
BRASS = (214, 168, 64)
BRASS_DARK = (150, 106, 34)
FACE = (240, 232, 205)
RIM = (70, 50, 30)
HAND = (30, 22, 14)
MARK = (120, 96, 70)
WOOD = (150, 96, 48)
WOOD_DARK = (96, 58, 26)
GLASS = (200, 222, 230)
SAND = (230, 196, 110)
RED = (212, 30, 30)
RED_DARK = (140, 14, 18)
PINK = (255, 170, 160)
STEEL = (200, 206, 214)
STEEL_DARK = (120, 128, 140)
GOLD = (224, 182, 70)


def _seg_dist(px, py, ax, ay, bx, by):
    """Distance of the points (px, py) from the segment a-b (arrays)."""
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0.0, 1.0)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy))


class Canvas:
    """Supersampled colour and coverage layers in texel units (0..16); later paints cover earlier ones."""

    def __init__(self):
        n = SIZE * SS
        c = (np.arange(n) + 0.5) / SS
        self.x, self.y = np.meshgrid(c, c)
        self.rgb = np.zeros((n, n, 3), np.float32)
        self.cover = np.zeros((n, n), np.float32)

    def paint(self, mask, colour):
        self.rgb[mask] = colour
        self.cover[mask] = 1.0


def stopwatch():
    k = Canvas()
    x, y = k.x, k.y
    cx, cy, r = 8.0, 9.2, 6.2
    d = np.hypot(x - cx, y - cy)
    k.paint((abs(x - cx) <= 0.9) & (y >= 1.6) & (y <= 3.4), BRASS_DARK)
    k.paint((abs(x - cx) <= 1.9) & (y >= 0.9) & (y <= 2.1), BRASS)
    k.paint(_seg_dist(x, y, cx + 4.6, cy - 4.6, cx + 5.6, cy - 5.6) <= 0.75, BRASS_DARK)
    k.paint(d <= r, BRASS)
    k.paint((d <= r) & (x - cx + y - cy > 3.5), BRASS_DARK)
    k.paint(d <= r - 1.1, RIM)
    k.paint(d <= r - 1.7, FACE)
    for q in range(4):
        a = q * math.pi / 2
        mx, my = cx + math.sin(a) * (r - 2.6), cy - math.cos(a) * (r - 2.6)
        k.paint(np.hypot(x - mx, y - my) <= 0.45, MARK)
    k.paint(_seg_dist(x, y, cx, cy, cx, cy - (r - 2.0)) <= 0.8, HAND)
    a = math.radians(60)
    k.paint(_seg_dist(x, y, cx, cy, cx + math.sin(a) * 3.0, cy - math.cos(a) * 3.0) <= 0.8, HAND)
    k.paint(d <= 1.0, HAND)
    return k


def hourglass():
    k = Canvas()
    x, y = k.x, k.y
    # the glass: two bulbs meeting at a neck, |x - 8| below a curve of y
    t = np.abs(y - 8.0)
    half = 0.7 + 0.62 * np.clip(t - 0.4, 0, None) ** 1.1
    inside = (np.abs(x - 8.0) <= half) & (y >= 2.6) & (y <= 13.4)
    k.paint(inside, GLASS)
    # sand: a heap in the bottom bulb and a little left in the top one, and the falling thread
    k.paint(inside & (y >= 10.0) & (np.abs(x - 8.0) <= 3.6 - 0.55 * (13.4 - y)) | inside & (y >= 11.6), SAND)
    k.paint(inside & (y <= 6.2) & (y >= 4.6), SAND)
    k.paint((np.abs(x - 8.0) <= 0.35) & (y >= 7.0) & (y <= 11.0), SAND)
    # the frame: top and bottom boards, two posts
    for top in (1.0, 13.4):
        k.paint((x >= 2.6) & (x <= 13.4) & (y >= top) & (y <= top + 1.6), WOOD)
        k.paint((x >= 2.6) & (x <= 13.4) & (y >= top + 1.1) & (y <= top + 1.6), WOOD_DARK)
    k.paint((np.abs(x - 3.6) <= 0.6) & (y >= 2.6) & (y <= 13.4), WOOD_DARK)
    k.paint((np.abs(x - 12.4) <= 0.6) & (y >= 2.6) & (y <= 13.4), WOOD_DARK)
    return k


def heart():
    k = Canvas()
    x, y = k.x, k.y
    # two circles and a triangle: the classic heart
    lobes = (np.hypot(x - 5.4, y - 5.8) <= 3.4) | (np.hypot(x - 10.6, y - 5.8) <= 3.4)
    tip = (y >= 5.8) & (y <= 14.2) & (np.abs(x - 8.0) <= (14.2 - y) * 0.86)
    shape = lobes | tip
    k.paint(shape, RED)
    k.paint(shape & (x + 0.4 * y > 15.5), RED_DARK)
    k.paint(np.hypot(x - 4.9, y - 4.9) <= 1.1, PINK)
    return k


def shield():
    k = Canvas()
    x, y = k.x, k.y
    # a heater shield: a flat top, straight sides, then two arcs to the point
    def heater(top, bottom, w):
        """Straight sides down to y 6.5, then sides that close in to a point at `bottom`."""
        t = np.clip((y - 6.5) / (bottom - 6.5), 0.0, 1.0)
        half = w * np.cos(t * math.pi / 2) ** 0.7
        return (y >= top) & (y <= bottom) & (np.abs(x - 8.0) <= half)

    outer = heater(1.4, 15.0, 6.2)
    k.paint(outer, GOLD)
    inner = heater(2.7, 13.4, 4.9)
    k.paint(inner, STEEL)
    k.paint(inner & (x > 8.0), STEEL_DARK)
    k.paint(inner & (np.abs(x - 6.0) <= 0.5) & (y <= 9.0), (236, 240, 244))  # a highlight
    return k


def eye():
    k = Canvas()
    x, y = k.x, k.y
    # an almond: the area between two arcs, white, with a blue iris, a dark pupil and a highlight
    u = (x - 8.0) / 7.2
    lid = 4.4 * np.clip(1 - u * u, 0, None)
    almond = (np.abs(u) <= 1.0) & (y >= 8.0 - lid) & (y <= 8.0 + lid * 0.85)
    k.paint(almond, (244, 240, 230))
    d = np.hypot(x - 8.0, y - 8.0)
    k.paint(almond & (d <= 3.3), (60, 110, 190))
    k.paint(almond & (d <= 3.3) & (y > 8.4), (40, 80, 150))
    k.paint(d <= 1.5, (14, 14, 18))
    k.paint(np.hypot(x - 6.9, y - 6.9) <= 0.7, (255, 255, 255))
    # the upper lid, a darker line over the almond
    k.paint((np.abs(u) <= 1.0) & (np.abs(y - (8.0 - lid)) <= 0.55), (70, 40, 20))
    return k


LEATHER = (176, 104, 48)
LEATHER_DARK = (118, 64, 26)
SOLE = (70, 44, 24)
WING = (246, 246, 240)
WING_SHADE = (180, 186, 196)
SPEED_BLUE = (70, 150, 235)


def _boot(k, dx=0.0):
    """A riding boot seen from the side, toe to the right: shaft, foot, a cuff, heel and sole. `dx` shifts it right."""
    x, y = k.x - dx, k.y
    shaft = (x >= 5.4) & (x <= 9.0) & (y >= 2.0) & (y <= 11.0)
    foot = ((x >= 5.4) & (x <= 11.6) & (y >= 9.4) & (y <= 13.0)) | (np.hypot(x - 11.6, y - 11.4) <= 1.7)
    k.paint(shaft | foot, LEATHER)
    k.paint(shaft & (x >= 7.6) & (y <= 9.6), LEATHER_DARK)
    k.paint((x >= 5.0) & (x <= 9.4) & (y >= 2.0) & (y <= 3.4), LEATHER_DARK)  # the cuff
    k.paint((x >= 5.4) & (x <= 13.3) & (y >= 12.6) & (y <= 13.8), SOLE)
    k.paint((x >= 5.4) & (x <= 7.0) & (y >= 12.0) & (y <= 14.2), SOLE)  # the heel


def boot_wings():
    """Speed: the boot with a small white wing at its back, swept back."""
    k = Canvas()
    x, y = k.x, k.y
    for i, (cy, length) in enumerate(((3.6, 6.4), (5.6, 5.6), (7.6, 4.6))):  # behind the boot: painted first
        feather = _seg_dist(x, y, 8.4, cy + 1.0, 8.4 - length, cy - 1.6) <= 1.0
        k.paint(feather, WING if i != 1 else WING_SHADE)
    _boot(k, dx=2.0)
    return k


def boot_arrows():
    """Speed (variant): the boot with three blue motion strokes behind it."""
    k = Canvas()
    _boot(k, dx=2.4)
    x, y = k.x, k.y
    for cy, x0 in ((4.0, 1.2), (7.0, 0.4), (10.0, 1.2)):
        k.paint(_seg_dist(x, y, x0, cy, x0 + 5.0, cy) <= 0.6, SPEED_BLUE)
    return k


def boot_lines():
    """Speed (variant): the boot with white speed lines behind it."""
    k = Canvas()
    _boot(k, dx=2.4)
    x, y = k.x, k.y
    for cy, x0, x1 in ((4.0, 2.0, 7.0), (6.6, 0.6, 7.0), (9.2, 2.0, 7.0)):
        k.paint(_seg_dist(x, y, x0, cy, x1, cy) <= 0.45, WING)
    return k


GLYPHS = {"stopwatch": stopwatch, "hourglass": hourglass, "heart": heart, "shield": shield, "eye": eye,
          "boot_wings": boot_wings, "boot_arrows": boot_arrows, "boot_lines": boot_lines}
FILES = {"stopwatch": "stat_icon_rof.ddt", "hourglass": "stat_icon_traintime.ddt",
         "heart": "stat_icon_hitpoints.ddt", "shield": "stat_icon_armor.ddt", "eye": "stat_icon_los.ddt",
         "boot_wings": "stat_icon_speed.ddt", "boot_arrows": "stat_icon_speed_arrows.ddt",
         "boot_lines": "stat_icon_speed_lines.ddt"}


def render(glyph):
    """16 x 16 x 4 uint8 RGBA of the glyph, with a one-texel dark outline around it."""
    k = GLYPHS[glyph]()
    n = SIZE
    rgb = k.rgb.reshape(n, SS, n, SS, 3)
    cov = k.cover.reshape(n, SS, n, SS)
    a = cov.mean(axis=(1, 3))
    weight = cov[..., None]
    colour = (rgb * weight).sum(axis=(1, 3)) / np.maximum(weight.sum(axis=(1, 3)), 1e-6)
    out = np.zeros((n, n, 4), np.float32)
    out[..., :3] = colour
    out[..., 3] = a
    solid = a > 0.35
    near = np.zeros_like(solid)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            near |= np.roll(np.roll(solid, dy, 0), dx, 1)
    ring = near & (a < 0.5)
    out[ring, :3] = OUTLINE
    out[ring, 3] = np.maximum(out[ring, 3], 0.85)
    part = (a >= 0.5) & (a < 0.999)
    out[part, :3] = out[part, :3] * a[part, None] + np.array(OUTLINE, np.float32) * (1 - a[part, None])
    out[part, 3] = 1.0
    return np.clip(np.round(out * np.array([1, 1, 1, 255], np.float32)), 0, 255).astype(np.uint8)


def encode(glyph):
    return ddt.write_dxt(render(glyph), ddt.DXT3, alpha=1, usage=0, mips=False)


def preview(datas):
    """An 8x enlarged strip of the decoded icons, each on the panel's brown and on grey."""
    tiles = []
    for data in datas:
        dec = np.asarray(ddt.decode(data)).astype(np.float32)
        big = dec.repeat(8, 0).repeat(8, 1)
        al = big[..., 3:4] / 255.0
        pair = [big[..., :3] * al + np.array(bg, np.float32) * (1 - al) for bg in ((60, 35, 25), (200, 200, 200))]
        tiles.append(np.concatenate([pair[0], np.full((big.shape[0], 4, 3), 40, np.float32), pair[1]], axis=1))
        tiles.append(np.full((big.shape[0], 16, 3), 40, np.float32))
    return np.concatenate(tiles[:-1], axis=1).astype(np.uint8)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--glyph", default="stopwatch", choices=sorted(GLYPHS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--all", metavar="FOLDER", help="write every glyph into this folder, under its file name")
    ap.add_argument("--png", help="also write an 8x enlarged preview on the panel's brown and on grey")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    jobs = ([(g, pathlib.Path(a.all) / FILES[g]) for g in GLYPHS] if a.all else [(a.glyph, pathlib.Path(a.out))])
    status = 0
    datas = []
    for glyph, out in jobs:
        data = encode(glyph)
        datas.append(data)
        if a.check:
            same = out.exists() and out.read_bytes() == data
            print(f"{out}: {'same' if same else 'differs'}")
            status |= 0 if same else 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"{out}: {len(data)} bytes, {ddt.read_header(data).describe()}")
    if a.png and not a.check:
        from core.pngio import encode_png
        pathlib.Path(a.png).write_bytes(encode_png(preview(datas)))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
