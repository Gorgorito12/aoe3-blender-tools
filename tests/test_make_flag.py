# SPDX-License-Identifier: GPL-3.0-or-later
"""make_flag.py on a made-up game copy: a few synthetic flag sets in the layout and formats of the
target's own (nothing from the game). Checks every file of the set is written with the formats the
copy uses, the frame is kept and the design lands inside it. Needs numpy (the venv)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import numpy as np  # noqa: E402

from aoe3game import ddt  # noqa: E402
from core import pngio  # noqa: E402
import make_flag  # noqa: E402

FL, BT = "Mod\\Flags", "Mod\\Buttons"


def frame(h, w, box, colour, rng):
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 3] = 255
    y0, x0, y1, x1 = box
    img[:y1 + 3, :x1 + 3, :3] = (90, 80, 50)
    img[y0:y1, x0:x1, :3] = colour + rng.integers(0, 10, (y1 - y0, x1 - x0, 3))
    return img


def fake_copy(root, n=24):
    rng = np.random.default_rng(1)
    fdir, bdir = os.path.join(root, "art", FL), os.path.join(root, "art", BT)
    os.makedirs(fdir), os.makedirs(bdir)
    for i in range(n):
        col = rng.integers(20, 200, 3)
        for s, k in zip(make_flag.STATES, (1.0, 0.9, 1.2, 0.8)):
            c = np.clip(col * k, 0, 255)
            with open(os.path.join(bdir, f"flag_s{i}_{s}.ddt"), "wb") as f:
                f.write(ddt.write_bgra(frame(64, 128, (4, 4, 44, 71), c, rng), alpha=0, mips=False))
            big = frame(128, 128, (6, 6, 90, 122), c, rng)
            big[96:, :, 3] = 0
            with open(os.path.join(bdir, f"flag_s{i}_large_{s}.ddt"), "wb") as f:
                f.write(ddt.write_bgra(big, alpha=1, mips=True))
        pg = np.zeros((32, 128, 4), np.uint8)
        pg[..., :3] = (120, 100, 60)
        pg[:, :90, :3] = col
        pg[..., 3] = np.clip(np.arange(128) * -4 + 500, 0, 255)[None, :]
        with open(os.path.join(fdir, f"ingame_ui_postgame_flag_s{i}.ddt"), "wb") as f:
            f.write(ddt.write_bgra(pg, alpha=1, mips=False))


def test_set():
    with tempfile.TemporaryDirectory() as tmp:
        game, out = os.path.join(tmp, "game"), os.path.join(tmp, "out")
        fake_copy(game)
        design = np.zeros((40, 60, 3), np.uint8)
        design[:] = (200, 20, 20)
        design[12:28, 22:38] = (240, 200, 60)
        dpath = os.path.join(tmp, "d.png")
        with open(dpath, "wb") as f:
            f.write(pngio.encode_png(design))
        make_flag.main(["--design", dpath, "--name", "t", "--game", game, "--out", out,
                        "--flags-dir", FL, "--buttons-dir", BT,
                        "--preview", os.path.join(tmp, "p.png"), "--compare", "s0"])
        want = {
            (FL, "t"): (128, 128, 0, 1),
            (FL, "ingame_ui_postgame_flag_t"): (128, 32, 1, 1),
        }
        for s in make_flag.STATES:
            want[(BT, f"flag_t_{s}")] = (128, 64, 0, 1)
            want[(BT, f"flag_t_large_{s}")] = (128, 128, 1, 6)
        for (d, n), (w, h, alpha, mips) in want.items():
            data = open(os.path.join(out, "art", d, n + ".ddt"), "rb").read()
            hd = ddt.read_header(data)
            assert (hd.width, hd.height, hd.format, hd.alpha, hd.mips) == (w, h, ddt.BGRA, alpha, mips), (n, hd.describe())
        btn = ddt.decode(open(os.path.join(out, "art", BT, "flag_t_normal.ddt"), "rb").read())
        assert tuple(btn[1, 1, :3]) == (90, 80, 50)                 # the frame is the template's
        assert btn[24, 37, 0] > 200 and btn[24, 37, 2] < 120        # the disc's gold in the middle
        assert btn[8, 8, 0] > 150 and btn[8, 8, 1] < 60             # the red field
        hi = ddt.decode(open(os.path.join(out, "art", BT, "flag_t_high.ddt"), "rb").read())
        assert hi[8, 8, :3].astype(int).sum() > btn[8, 8, :3].astype(int).sum()   # brighter
        pg = ddt.decode(open(os.path.join(out, "art", FL, "ingame_ui_postgame_flag_t.ddt"), "rb").read())
        assert pg[16, 127, 3] == 0 and pg[16, 10, 3] == 255         # the player colour mask kept
        assert tuple(pg[16, 127, :3]) == (120, 100, 60)             # the backdrop kept


if __name__ == "__main__":
    test_set()
    print("all tests passed")
