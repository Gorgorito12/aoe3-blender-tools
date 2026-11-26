# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws the frames of a small progress pie for a unit panel row: a square in a thin gold frame, covered in the blue
of a training button's overlay (pure blue at half alpha) except for a clear wedge that opens from 12 o'clock and turns
clockwise, as that overlay does. Frame k of N shows k/N done; frame 0 is all blue.

    venv\\Scripts\\python -I tools/make_pie.py --out <folder> [--frames 32] [--png <sheet.png>] [--check]

Writes pie_00.ddt ... pie_<N-1>.ddt into the folder (for art/ui/uhc/pie/; a row names them ui\\uhc\\pie\\pie_07 in an
inline icon). Each is 32x32 uncompressed BGRA, one level, fully opaque (a square needs no alpha), as the mod's own
stat icons are made. Every line is at least 2 texels wide, since the panel draws the icon at about 14 to 17 screen
pixels; the wedge's edge is supersampled. No pixel comes from a game. `--png` writes a sheet of every frame enlarged,
and the frames at the panel's sizes on its brown. `--check` exits with code 1 if a file on disk differs.
Test: `tests/test_pie.py`.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

SIZE = 32
BORDER = 2
SS = 8  # samples per texel side, for the wedge's edge
FRAMES = 32

GOLD = np.array((176, 138, 64), np.float32)       # the frame, as the gold rims of the panel's portraits
CLEAR = np.array((122, 116, 102), np.float32)     # what is done: a light stone grey
BLUE = np.array((0, 0, 255), np.float32)          # the training overlay's colour (r 0, g 0, b 1) ...
BLUE_ALPHA = 0.5                                  # ... at half alpha
COVERED = CLEAR * (1 - BLUE_ALPHA) + BLUE * BLUE_ALPHA  # what is still to come: the overlay over the clear grey

PANEL_BROWN = (58, 34, 22)


def done_share(frame, frames):
    return frame / frames


def render(frame, frames=FRAMES):
    """SIZE x SIZE x 4 uint8 RGBA of one frame."""
    inner = SIZE - 2 * BORDER
    n = inner * SS
    centre = n / 2.0
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float64) + 0.5
    # clockwise angle from 12 o'clock, 0 .. 1 turn
    turn = (np.arctan2(xs - centre, centre - ys) / (2 * math.pi)) % 1.0
    clear = (turn < done_share(frame, frames)).astype(np.float32)
    share = clear.reshape(inner, SS, inner, SS).mean(axis=(1, 3))[..., None]
    out = np.empty((SIZE, SIZE, 3), np.float32)
    out[:] = GOLD
    out[BORDER:SIZE - BORDER, BORDER:SIZE - BORDER] = CLEAR * share + COVERED * (1 - share)
    rgba = np.empty((SIZE, SIZE, 4), np.uint8)
    rgba[..., :3] = np.clip(np.round(out), 0, 255).astype(np.uint8)
    rgba[..., 3] = 255
    return rgba


def encode(frame, frames=FRAMES):
    return ddt.write_bgra(render(frame, frames), alpha=0, usage=0, mips=False)


def name(frame):
    return f"pie_{frame:02d}.ddt"


def _box(img, size):
    """A box filter down to size x size (the panel's minification, roughly)."""
    src = img.astype(np.float32)
    h = src.shape[0]
    edges = np.linspace(0, h, size + 1)
    out = np.zeros((size, size, src.shape[2]), np.float32)
    for i in range(size):
        for j in range(size):
            y0, y1 = int(edges[i]), max(int(edges[i]) + 1, int(math.ceil(edges[i + 1])))
            x0, x1 = int(edges[j]), max(int(edges[j]) + 1, int(math.ceil(edges[j + 1])))
            out[i, j] = src[y0:y1, x0:x1].reshape(-1, src.shape[2]).mean(axis=0)
    return out


def sheet(frames):
    """Every frame at 3x (8 per row), then a strip of every 4th frame at 17 and 14 pixels on the panel's brown."""
    tiles = [render(k, frames)[..., :3] for k in range(frames)]
    big = [t.repeat(3, 0).repeat(3, 1) for t in tiles]
    cell = SIZE * 3
    gap = 8
    per_row = 8
    rows = (frames + per_row - 1) // per_row
    small = [17, 14]
    strip_h = sum(s * 4 + gap for s in small)
    width = per_row * (cell + gap) + gap
    height = rows * (cell + gap) + gap + strip_h + gap
    out = np.zeros((height, width, 3), np.float32)
    out[:] = PANEL_BROWN
    for k, b in enumerate(big):
        y = gap + (k // per_row) * (cell + gap)
        x = gap + (k % per_row) * (cell + gap)
        out[y:y + cell, x:x + cell] = b
    y = gap + rows * (cell + gap)
    for s in small:
        x = gap
        for k in range(0, frames, 4):
            t = _box(tiles[k], s).repeat(4, 0).repeat(4, 1)  # the panel's size, shown 4x
            out[y:y + t.shape[0], x:x + t.shape[1]] = t
            x += t.shape[1] + gap
        y += s * 4 + gap
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="the folder for pie_00.ddt ...")
    ap.add_argument("--frames", type=int, default=FRAMES)
    ap.add_argument("--png", help="also write a sheet of the frames")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if not 2 <= a.frames <= 100:
        ap.error("--frames is 2 to 100")
    folder = pathlib.Path(a.out)
    status = 0
    for k in range(a.frames):
        data = encode(k, a.frames)
        out = folder / name(k)
        if a.check:
            same = out.exists() and out.read_bytes() == data
            if not same:
                print(f"{out}: differs")
            status |= 0 if same else 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    if a.check:
        print(f"{folder}: {a.frames} frames, {'same' if status == 0 else 'some differ'}")
    else:
        print(f"{folder}: {a.frames} frames, {ddt.read_header(encode(0, a.frames)).describe()}")
    if a.png and not a.check:
        from core.pngio import encode_png
        pathlib.Path(a.png).write_bytes(encode_png(sheet(a.frames)))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
