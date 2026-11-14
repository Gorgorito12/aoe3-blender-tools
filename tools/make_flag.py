# SPDX-License-Identifier: GPL-3.0-or-later
"""Writes a whole civ flag set (in-game flag, small and large button sets, postgame flag) from one
design image, in the layout of a game copy's own flag sets.

    venv/Scripts/python -I tools/make_flag.py --design <flag.png> --name <set> --game <game copy> --out <folder>
        [--flags-dir "War of the Triple Alliance\\Flags"] [--buttons-dir "War of the Triple Alliance\\Buttons"]
        [--preview <sheet.png>] [--compare japan,piratini]

The design is any RGB(A) PNG of the flat flag (the whole cloth, hoist on the left). What the game
shows is measured from the copy's own sets at run time, never stored here: for each texture kind,
the pixels that are the same in every set are the template (button frames, the postgame painting
round the pole), the pixels that change are where the flag goes; the colour change of each button
state (click, highlight, disabled) is a linear fit from the normal state over every set. The
in-game flag gets procedural folds. Formats are those the sets use (measured on the target):

    <flags>\\<name>.ddt                          128x128 BGRA, no alpha, 1 level
    <flags>\\ingame_ui_postgame_flag_<name>.ddt  128x32 BGRA, alpha = player colour mask, 1 level
    <buttons>\\flag_<name>_{normal,click,high,disable}.ddt        128x64 BGRA, 1 level
    <buttons>\\flag_<name>_large_{normal,click,high,disable}.ddt  128x128 BGRA, player colour, 6 levels

Nothing written comes from the game except the template pixels that every set shares (frame,
pole, backdrop), taken from the user's own copy. Needs numpy.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "aoe3_blender_tools"))

import numpy as np  # noqa: E402

from aoe3game import ddt  # noqa: E402
from core import pngio  # noqa: E402

STATES = ("normal", "click", "high", "disable")


def load(path):
    with open(path, "rb") as f:
        return ddt.decode(f.read())


def header(path):
    with open(path, "rb") as f:
        return ddt.read_header(f.read(64))


def resize(img, h, w):
    """Bilinear resize of an H x W x C array."""
    img = img.astype(np.float32)
    ys = (np.arange(h) + 0.5) * img.shape[0] / h - 0.5
    xs = (np.arange(w) + 0.5) * img.shape[1] / w - 0.5
    return sample(img, ys[:, None] + 0 * xs[None, :], xs[None, :] + 0 * ys[:, None])


def sample(img, y, x):
    """Bilinear sample of img at float coordinates (pixel centres at integers), edges clamped."""
    h, w = img.shape[:2]
    y = np.clip(y, 0, h - 1)
    x = np.clip(x, 0, w - 1)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (y - y0)[..., None], (x - x0)[..., None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy)
            + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy)


# --------------------------------------------------------------------------------------------------
# Measuring the copy's own sets

class Kind:
    """One texture kind measured over every set: the shared template, where the flag varies, the
    bounding box of that region, and the header to copy."""

    def __init__(self, images, hd):
        stack = np.stack([i.astype(np.float32) for i in images])
        self.template = np.median(stack, axis=0)
        dev = np.abs(stack[..., :3] - self.template[None, ..., :3]).mean(axis=3)
        self.mask = np.median(dev, axis=0) > 12      # varies in most sets (an odd set or two do not count)
        ys, xs = np.nonzero(self.mask)
        self.box = (ys.min(), xs.min(), ys.max() + 1, xs.max() + 1) if len(ys) else None
        self.stack = stack
        self.header = hd


def survey(game, flags_dir, buttons_dir, compare=()):
    fdir = os.path.join(game, "art", flags_dir)
    bdir = os.path.join(game, "art", buttons_dir)
    names = []
    for p in sorted(glob.glob(os.path.join(bdir, "flag_*_normal.ddt"))):
        n = os.path.basename(p)[5:-11]
        if n.endswith("_large"):
            continue
        if all(os.path.exists(os.path.join(bdir, f"flag_{n}_{s}.ddt")) for s in STATES):
            names.append(n)
    kinds = {}
    for s in STATES:
        imgs, hd = [], None
        for n in names:
            p = os.path.join(bdir, f"flag_{n}_{s}.ddt")
            h = header(p)
            if (h.width, h.height) == (128, 64):
                imgs.append(load(p))
                hd = hd or h
        kinds["button_" + s] = Kind(imgs, hd)
    for s in STATES:
        imgs, hd = [], None
        for p in sorted(glob.glob(os.path.join(bdir, f"flag_*_large_{s}.ddt"))):
            h = header(p)
            if (h.width, h.height) == (128, 128) and h.mips == 6:
                imgs.append(load(p))
                hd = hd or h
        if imgs:
            kinds["large_" + s] = Kind(imgs, hd)
    imgs, hd = [], None
    for p in sorted(glob.glob(os.path.join(fdir, "ingame_ui_postgame_flag_*.ddt"))):
        h = header(p)
        if (h.width, h.height) == (128, 32):
            imgs.append(load(p))
            hd = hd or h
    kinds["postgame"] = Kind(imgs, hd)
    alphas = np.stack([i[..., 3] for i in imgs])
    kinds["postgame"].alpha = np.median(alphas, axis=0)
    return kinds, names


def state_fit(normal, state, box):
    """A 3 x 4 affine colour map from the normal button to a state, over every set's flag area."""
    y0, x0, y1, x1 = box
    a = normal[:, y0 + 2:y1 - 2, x0 + 2:x1 - 2, :3].reshape(-1, 3)
    b = state[:, y0 + 2:y1 - 2, x0 + 2:x1 - 2, :3].reshape(-1, 3)
    if len(a) != len(b):
        return np.eye(4)[:, :3].T
    A = np.concatenate([a, np.ones((len(a), 1))], 1)
    m, *_ = np.linalg.lstsq(A, b, rcond=None)
    return m.T


# --------------------------------------------------------------------------------------------------
# Drawing

def folds(h, w, seed=7, strength=0.10):
    """A multiplicative shading of cloth folds: soft diagonal ripples, darker at the bottom hem."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = x / w, y / h
    s = np.zeros((h, w), np.float32)
    for _ in range(6):
        a = rng.uniform(-0.6, 0.6)
        f = rng.uniform(2.0, 5.0)
        ph = rng.uniform(0, 6.28)
        s += np.sin((u * f + v * f * a) * 6.28 + ph + 0.8 * np.sin(v * 4 + ph)) / 6
    s = 1 + strength * s / (np.abs(s).max() + 1e-6)
    s *= 1 - 0.18 * np.clip((v - 0.88) / 0.12, 0, 1)
    return s


def ingame_flag(design):
    rgb = resize(design[..., :3], 128, 128)
    out = np.clip(rgb * folds(128, 128)[..., None], 0, 255)
    return np.concatenate([out, np.full((128, 128, 1), 255.0)], 2).astype(np.uint8)


def button(kind, flag_rgb, fit=None):
    out = kind.template.copy()
    y0, x0, y1, x1 = kind.box
    patch = resize(flag_rgb, y1 - y0, x1 - x0)
    if fit is not None:
        p = patch.reshape(-1, 3)
        patch = (np.concatenate([p, np.ones((len(p), 1))], 1) @ fit.T).reshape(patch.shape)
    out[y0:y1, x0:x1, :3] = patch           # the whole box: the flag is a rectangle in its frame
    out[..., :3] = np.clip(out[..., :3], 0, 255)
    return out.astype(np.uint8)


def postgame(kind, design):
    """The flag on the painted pole: the design flows left from the pole, sagging, under the
    shared folds of the painting (the median brightness of every set's cloth), toned like them."""
    t = kind.template
    h, w = t.shape[:2]
    lum_all = kind.stack[..., :3].mean(axis=3)
    shade = np.median(lum_all, axis=0)
    pole = np.array([np.nonzero(kind.mask[y])[0].max() if kind.mask[y].any() else w - 1
                     for y in range(h)])
    mask = np.arange(w)[None, :] <= pole[:, None]  # everything left of the pole is cloth
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = 1 - x / (pole[:, None] + 1)                  # 0 at the pole (hoist) ... 1 at the left edge
    v = 0.12 + 0.76 * (y / h) + 0.10 * u ** 2         # the fly sags
    small = resize(design[..., :3], 2 * h, int(pole.max()) + 1)    # filtered first: no moire
    dh, dw = small.shape[:2]
    rgb = sample(small, np.clip(v, 0, 1) * (dh - 1), np.clip(u, 0, 1) * (dw - 1))
    # tone as the stock ones: the cloth's own brightness from the folds, warmed and a little muted
    folds_ = 1 + 0.55 * (shade / (shade[mask].mean() + 1e-6) - 1)   # half the painting's folds
    grey = rgb.mean(axis=2, keepdims=True)
    toned = (0.80 * rgb + 0.20 * grey) * np.array([0.95, 0.85, 0.70]) * folds_[..., None]
    cloth = kind.stack[:, mask, :3].reshape(-1, 3)
    lo = np.percentile(cloth, 2, axis=0)
    toned = np.maximum(toned, lo * 0.5)
    out = t.copy()
    out[..., :3] = np.where(mask[..., None], toned, t[..., :3])
    out[..., 3] = kind.alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def write(path, rgba, hd):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = ddt.write_bgra(rgba, alpha=hd.alpha, usage=hd.usage, mips=hd.mips > 1)
    got = ddt.read_header(data)
    if got.mips != hd.mips:  # cut or keep the chain to the measured count
        levels = ddt.mip_chain(rgba.astype(np.uint8), smallest=1)[:hd.mips]
        data = _bgra_levels(levels, hd)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _bgra_levels(levels, hd):
    import struct
    blobs = [np.ascontiguousarray(lv[:, :, [2, 1, 0, 3]]).tobytes() for lv in levels]
    out = bytearray(ddt.MAGIC + bytes([hd.usage, hd.alpha, ddt.BGRA, len(blobs)])
                    + struct.pack("<II", levels[0].shape[1], levels[0].shape[0]))
    off = 16 + 8 * len(blobs)
    for b in blobs:
        out += struct.pack("<II", off, len(b))
        off += len(b)
    for b in blobs:
        out += b
    return bytes(out)


def make_set(design, name, kinds, out, flags_dir, buttons_dir):
    files = {}
    fl = ingame_flag(design)
    files["flag"] = write(os.path.join(out, "art", flags_dir, name + ".ddt"), fl,
                          ddt.Header(0, 0, ddt.BGRA, 1, 128, 128, []))
    flag_rgb = fl[..., :3].astype(np.float32)
    normal = kinds["button_normal"]
    fits = {s: state_fit(normal.stack, kinds["button_" + s].stack, normal.box)
            for s in STATES[1:]}           # the small sets, measured set by set
    for prefix, sub in (("button_", ""), ("large_", "_large")):
        if prefix + "normal" not in kinds:
            continue
        for s in STATES:
            k = kinds.get(prefix + s) or kinds[prefix + "normal"]
            img = button(k, flag_rgb, fits.get(s))
            files[prefix + s] = write(os.path.join(out, "art", buttons_dir, f"flag_{name}{sub}_{s}.ddt"),
                                      img, k.header)
    files["postgame"] = write(os.path.join(out, "art", flags_dir, f"ingame_ui_postgame_flag_{name}.ddt"),
                              postgame(kinds["postgame"], design), kinds["postgame"].header)
    return files


def preview(files, game, flags_dir, buttons_dir, compare, path):
    """One row per texture kind: the new set, then the sets named in `compare`, alpha beside."""
    rows = []
    kinds = [("flag", "{f}\\{n}"), ("postgame", "{f}\\ingame_ui_postgame_flag_{n}")]
    kinds += [("button_" + s, "{b}\\flag_{n}_" + s) for s in STATES]
    kinds += [("large_" + s, "{b}\\flag_{n}_large_" + s) for s in STATES]
    for key, pat in kinds:
        if key not in files:
            continue
        cells = [load(files[key])]
        for c in compare:
            p = os.path.join(game, "art", pat.format(f=flags_dir, b=buttons_dir, n=c) + ".ddt")
            cells.append(load(p) if os.path.exists(p) else np.zeros_like(cells[0]))
        row = []
        for c in cells:
            c = c.repeat(2, 0).repeat(2, 1)
            a = np.repeat(c[..., 3:4], 3, 2)
            row += [c[..., :3], np.full((c.shape[0], 4, 3), 40, np.uint8), a,
                    np.full((c.shape[0], 16, 3), 0, np.uint8)]
        rows.append(np.concatenate(row, 1))
        rows.append(np.zeros((8, rows[-1].shape[1], 3), np.uint8))
    wmax = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0))) for r in rows]
    with open(path, "wb") as f:
        f.write(pngio.encode_png(np.concatenate(rows, 0)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--design", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--game", required=True, help="a game copy to measure (read only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--flags-dir", default="War of the Triple Alliance\\Flags")
    ap.add_argument("--buttons-dir", default="War of the Triple Alliance\\Buttons")
    ap.add_argument("--preview")
    ap.add_argument("--compare", default="")
    a = ap.parse_args(argv)
    if os.path.abspath(a.out).lower().startswith(os.path.abspath(a.game).lower()):
        sys.exit("refusing to write into the game copy; --out elsewhere")
    with open(a.design, "rb") as f:
        design = pngio.read_png(f.read())
    if design.shape[2] == 4:
        design = design[..., :3]
    kinds, names = survey(a.game, a.flags_dir, a.buttons_dir)
    print(f"measured {len(names)} button sets, {kinds['postgame'].stack.shape[0]} postgame flags")
    files = make_set(design, a.name, kinds, a.out, a.flags_dir, a.buttons_dir)
    for k, p in files.items():
        print(f"{k:16s} {ddt.read_header(open(p, 'rb').read(64)).describe():50s} {p}")
    if a.preview:
        preview(files, a.game, a.flags_dir, a.buttons_dir,
                [c for c in a.compare.split(",") if c], a.preview)
        print("preview", a.preview)


if __name__ == "__main__":
    main()
