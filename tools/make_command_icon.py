# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws command button icons (the square buttons of the unit command panel) in the style of Wars of Liberty's
own on / off buttons: 64x64 uncompressed BGRA, one level, a mottled blue frame with a light inner edge and a black
line inside it, the picture, and a mark: a green tick at the top right for the "on" button, a red tint and a red
cross at the bottom left for the "off" one.

    venv\\Scripts\\python -I tools/make_command_icon.py --glyph autoscout --all <folder> [--png <sheet.png>] [--check]
    venv\\Scripts\\python -I tools/make_command_icon.py --glyph autoscout --state on --out <file.ddt>

Glyphs (the file names `--all` gives the two states):
- `autoscout` (`uhc_autoscout_start.ddt`, `uhc_autoscout_stop.ddt`): a unit that explores on its own: a parchment
  map, half of it still blank, a dotted route that loops into the blank part, and a brass spyglass across it.

Every pixel is computed here (no image is read): shapes are sampled 4x4 per texel and averaged, the frame's
mottling comes from a fixed pseudo-random sequence, so the output is the same on every run. `--check` exits with
code 1 if a file on disk differs from what would be written. Test: `tests/test_command_icons.py`.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

SIZE = 64
SS = 4
FRAME = 5  # texels of frame on each side (outer blue 0..2, mid 2, light 3, black 4)

NAVY = np.array([0, 12, 57], float)
NAVY_LIGHT = np.array([30, 60, 130], float)
MID = np.array([94, 113, 156], float)
LIGHT = np.array([189, 215, 255], float)
BLACK = np.array([8, 8, 8], float)

PARCHMENT = np.array([206, 176, 118], float)
PARCHMENT_DARK = np.array([150, 116, 66], float)
BLANK = np.array([228, 218, 192], float)
INK = np.array([96, 62, 30], float)
ROUTE = np.array([170, 30, 26], float)
BRASS = np.array([214, 168, 64], float)
BRASS_DARK = np.array([130, 92, 30], float)
LENS = np.array([150, 200, 230], float)
OUTLINE = np.array([20, 14, 8], float)
GREEN = np.array([30, 170, 40], float)
RED = np.array([220, 24, 24], float)

FILES = {("autoscout", "on"): "uhc_autoscout_start.ddt", ("autoscout", "off"): "uhc_autoscout_stop.ddt"}


def samples():
    """Sample coordinates (u, v) in texels, SS x SS per texel: arrays of shape (SIZE*SS, SIZE*SS)."""
    c = (np.arange(SIZE * SS) + 0.5) / SS
    return np.meshgrid(c, c)  # u = x, v = y (top row first)


def seg_dist(u, v, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = np.clip(((u - ax) * dx + (v - ay) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
    return np.hypot(u - (ax + t * dx), v - (ay + t * dy))


def noise(seed, n):
    """A fixed pseudo-random sequence in [0, 1) (a linear congruential generator)."""
    out = np.empty(n)
    x = seed
    for i in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out[i] = x / 0x80000000
    return out


class Canvas:
    def __init__(self):
        self.rgb = np.zeros((SIZE * SS, SIZE * SS, 3), float)

    def paint(self, mask, colour):
        self.rgb[mask] = colour

    def texels(self):
        return self.rgb.reshape(SIZE, SS, SIZE, SS, 3).mean(axis=(1, 3))


def picture_autoscout(c, u, v):
    inside = (u >= FRAME) & (u < SIZE - FRAME) & (v >= FRAME) & (v < SIZE - FRAME)
    # the map: parchment, darker towards the edges; the right part still blank (unexplored)
    r = np.hypot(u - SIZE / 2, v - SIZE / 2) / (SIZE / 2)
    shade = np.clip((r - 0.55) / 0.6, 0.0, 1.0)[..., None]
    c.rgb[inside] = (PARCHMENT * (1 - shade) + PARCHMENT_DARK * shade)[inside]
    edge = 34 + 6 * np.sin(v / 5.0)  # a ragged border between the mapped and the blank part
    blank = inside & (u > edge)
    c.rgb[blank] = BLANK
    # coast lines and a river on the mapped part
    coast = inside & (u <= edge) & (np.abs(np.hypot(u - 14, v - 46) - 11) < 0.7)
    river = inside & (u <= edge) & (np.abs(v - (22 + 5 * np.sin(u / 4.0))) < 0.6)
    c.paint(coast | river, INK)
    # the dotted route: a loop from the mapped part into the blank part
    t = np.arctan2(v - 30, u - 34)
    loop = np.abs(np.hypot((u - 34) / 1.25, v - 30) - 13) < 1.1
    dots = (np.mod(t * 13 / math.pi, 2.0) < 1.0)
    c.paint(inside & loop & dots, ROUTE)
    # the spyglass, from lower left to upper right: three tubes, eyepiece to lens
    ax, ay, bx, by = 11, 54, 40, 25
    d = seg_dist(u, v, ax, ay, bx, by)
    t = np.clip(((u - ax) * (bx - ax) + (v - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2), 0, 1)
    radius = np.where(t < 0.3, 3.0, np.where(t < 0.65, 3.8, 4.6))
    body = inside & (d < radius)
    outline = inside & (d < radius + 1.1) & ~body
    c.paint(outline, OUTLINE)
    c.paint(body, BRASS)
    rings = body & (np.abs(t - 0.3) < 0.025) | body & (np.abs(t - 0.65) < 0.025)
    c.paint(rings, BRASS_DARK)
    shine = body & (np.abs(d - radius * 0.45) < 0.6) & (((u - ax) * (by - ay) - (v - ay) * (bx - ax)) > 0)
    c.paint(shine, np.minimum(BRASS + 40, 255))
    lens = inside & (np.hypot(u - bx, v - by) < 3.6)
    c.paint(inside & (np.hypot(u - bx, v - by) < 4.6) & ~lens, OUTLINE)
    c.paint(lens, LENS)


def frame(c, u, v):
    x, y = np.floor(u).astype(int), np.floor(v).astype(int)
    ring = np.minimum(np.minimum(x, y), np.minimum(SIZE - 1 - x, SIZE - 1 - y))
    mottle = noise(64064, SIZE * SIZE).reshape(SIZE, SIZE)
    m = mottle[np.clip(y, 0, SIZE - 1), np.clip(x, 0, SIZE - 1)][..., None]
    outer = ring <= 1
    c.rgb[outer] = (NAVY * (1 - m) + NAVY_LIGHT * m)[outer]
    c.paint(ring == 2, MID)
    c.paint(ring == 3, LIGHT)
    c.paint(ring == 4, BLACK)


def tick(c, u, v):
    d = np.minimum(seg_dist(u, v, 38, 15, 44, 22), seg_dist(u, v, 44, 22, 56, 8))
    c.paint(d < 4.2, OUTLINE)
    c.paint(d < 2.8, GREEN)


def cross(c, u, v):
    d = np.minimum(seg_dist(u, v, 9, 42, 25, 58), seg_dist(u, v, 25, 42, 9, 58))
    d = np.where((u > FRAME) & (v < SIZE - FRAME), d, 99)
    c.paint(d < 4.0, OUTLINE)
    c.paint(d < 2.6, RED)


def draw(glyph, state):
    if glyph != "autoscout":
        raise ValueError(glyph)
    u, v = samples()
    c = Canvas()
    picture_autoscout(c, u, v)
    if state == "off":  # the picture tinted red, as the game's "off" buttons are
        inside = (u >= FRAME) & (u < SIZE - FRAME) & (v >= FRAME) & (v < SIZE - FRAME)
        grey = c.rgb[inside].mean(axis=1, keepdims=True)
        c.rgb[inside] = grey * np.array([0.78, 0.20, 0.17]) + np.array([24, 0, 0])
        cross(c, u, v)
    else:
        tick(c, u, v)
    frame(c, u, v)
    return np.clip(np.rint(c.texels()), 0, 255).astype(np.uint8)


def encode(glyph, state):
    return ddt.write_bgra(draw(glyph, state), alpha=0, usage=0, mips=False)


def preview(images):
    big = [np.repeat(np.repeat(i, 4, axis=0), 4, axis=1) for i in images]
    gap = np.full((SIZE * 4, 8, 3), 60, np.uint8)
    row = [big[0]]
    for b in big[1:]:
        row += [gap, b]
    return np.concatenate(row, axis=1)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--glyph", default="autoscout", choices=sorted({g for g, _ in FILES}))
    ap.add_argument("--state", choices=("on", "off"), default="on")
    ap.add_argument("--out")
    ap.add_argument("--all", metavar="FOLDER", help="write both states of the glyph into this folder")
    ap.add_argument("--png", help="also write a 4x enlarged preview of what is written")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.all:
        jobs = [(s, pathlib.Path(a.all) / FILES[(a.glyph, s)]) for s in ("on", "off")]
    elif a.out:
        jobs = [(a.state, pathlib.Path(a.out))]
    else:
        ap.error("give --out or --all")
    status = 0
    images = []
    for state, out in jobs:
        data = encode(a.glyph, state)
        images.append(draw(a.glyph, state))
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
        pathlib.Path(a.png).write_bytes(encode_png(preview(images)))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
