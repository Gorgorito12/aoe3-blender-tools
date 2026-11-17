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
postgame flag lies on the painting's cloth by a measured warp (WARP; --fit-warp refits it), in a
tone and folds fitted on the copy's sets whose flag shares the postgame flag's name; the pole and
the hem are drawn back from the template. The in-game flag gets procedural folds. Formats are those the sets use (measured on the target):

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
    imgs, designs, hd = [], [], None
    for p in sorted(glob.glob(os.path.join(fdir, "ingame_ui_postgame_flag_*.ddt"))):
        h = header(p)
        if (h.width, h.height) == (128, 32):
            imgs.append(load(p))
            hd = hd or h
            f = os.path.join(fdir, os.path.basename(p)[len("ingame_ui_postgame_flag_"):])
            d = load(f) if os.path.exists(f) else None    # the set's own flag, for the fits
            designs.append(d if d is not None and d.shape[:2] == (128, 128) else None)
    kinds["postgame"] = Kind(imgs, hd)
    alphas = np.stack([i[..., 3] for i in imgs])
    kinds["postgame"].alpha = np.median(alphas, axis=0)
    kinds["postgame"].designs = designs
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


# The cloth of the postgame painting, measured on Wars of Liberty's 40 sets whose flag and postgame
# flag share a name (tools/make_flag.py --fit-warp prints it again for another copy). With s = 1 - x /
# (edge + 1), 1 at the left side of the texture and 0 at the cloth's edge by the pole, and t = y / 32:
#   u = 1 - (u0 + k s + g t)                          the design is not mirrored: its hoist is on the left
#   v = a + b t + c s^2 + d s + e s t                 the cloth sags and narrows toward the pole
WARP = (0.318, 0.603, 0.135, -0.291, -0.007, 0.029, 0.995, -0.100)


class Cloth:
    """Where the cloth is (left of the pole, the pole and the hem's highlight stay the template's),
    and which design texel each of its pixels shows."""

    def __init__(self, kind, warp=WARP):
        h, w = kind.template.shape[:2]
        dev = np.abs(kind.stack[..., :3] - kind.template[None, ..., :3]).mean(axis=3)
        varies = np.median(dev, axis=0) > 12
        self.edge = np.array([np.nonzero(varies[y])[0].max() if varies[y].any() else w - 1
                              for y in range(h)])
        self.mask = np.arange(w)[None, :] <= self.edge[:, None] - 1
        self.uv(warp)

    def uv(self, warp):
        a, b, c, d, e, u0, k, g = warp
        h, w = self.mask.shape
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        s, t = 1 - x / (self.edge[:, None] + 1), y / h
        self.u = np.clip(1 - (u0 + k * s + g * t), 0, 1)
        self.v = np.clip(a + b * t + c * s ** 2 + d * s + e * s * t, 0, 1)
        return self

    def show(self, design):
        small = resize(design[..., :3], 64, 96)          # filtered first: no moire at 32 rows
        return sample(small, self.v * 63, self.u * 95)


def _pairs(kind):
    return [(kind.stack[i, ..., :3], d) for i, d in enumerate(kind.designs) if d is not None]


def fit_tone(kind, cloth, rounds=6):
    """The painting's tone: one colour map M (3 x 4) for every set and a brightness per pixel (its
    folds and light), so that postgame = shade * (M [design, 1]), fitted on the copy's own pairs."""
    ys, xs = np.nonzero(cloth.mask)
    P = np.stack([p[ys, xs] for p, _ in _pairs(kind)])                     # F x N x 3
    S = np.stack([cloth.show(d)[ys, xs] for _, d in _pairs(kind)])
    S1 = np.concatenate([S, np.ones(S.shape[:2] + (1,))], 2)               # F x N x 4
    shade = np.ones(len(ys))
    for _ in range(rounds):
        A = (S1 * shade[None, :, None]).reshape(-1, 4)
        m, *_ = np.linalg.lstsq(A, P.reshape(-1, 3), rcond=None)
        Q = S1 @ m                                                          # F x N x 3
        shade = (P * Q).sum(axis=(0, 2)) / np.maximum((Q * Q).sum(axis=(0, 2)), 1e-6)
        shade = np.clip(shade, 0.3, 2.0)
    full = np.ones(cloth.mask.shape)
    full[ys, xs] = shade
    return m.T, full


def fit_warp(kind, samples=1500, seed=0):
    """Searches the cloth's warp that best explains the copy's postgame flags from their own flags
    (a per-set colour map, the best 70 % of sets). About a minute; prints the numbers for WARP."""
    cloth = Cloth(kind)
    ys, xs = np.nonzero(cloth.mask)
    pairs = [(p[ys, xs], resize(d[..., :3], 64, 96)) for p, d in _pairs(kind)]

    def err(w):
        cloth.uv(w)
        out = []
        for P, D in pairs:
            S = sample(D, cloth.v * 63, cloth.u * 95)[ys, xs]
            A = np.concatenate([S, np.ones((len(S), 1))], 1)
            m, *_ = np.linalg.lstsq(A, P, rcond=None)
            out.append(((P - A @ m) ** 2).mean())
        return np.sort(out)[: max(1, int(len(out) * 0.7))].mean()

    rng = np.random.default_rng(seed)
    lo = np.array([-0.3, 0.2, -0.6, -0.6, -0.6, -0.4, 0.4, -0.3])
    hi = np.array([0.5, 1.4, 0.6, 0.6, 0.6, 0.4, 1.6, 0.3])
    best = np.array(WARP)
    best_e = err(best)
    for _ in range(samples):
        w = lo + (hi - lo) * rng.random(8)
        e = err(w)
        if e < best_e:
            best_e, best = e, w
    steps = (hi - lo) / 8
    while steps.max() > 0.005:
        better = False
        for i in range(8):
            for sg in (-1, 1):
                w = best.copy()
                w[i] += sg * steps[i]
                e = err(w)
                if e < best_e:
                    best_e, best, better = e, w, True
        if not better:
            steps /= 2
    return tuple(round(float(v), 3) for v in best), best_e


def postgame(kind, design, warp=WARP):
    """The flag in the painting by the pole: the design laid on the measured cloth, in the
    painting's tone and folds; the pole, the hem and the backdrop are the template's."""
    cloth = Cloth(kind, warp)
    t = kind.template
    if any(d is not None for d in kind.designs):
        m, shade = fit_tone(kind, cloth)
        rgb = cloth.show(design)
        toned = shade[..., None] * (np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,))], 2) @ m.T)
    else:                                    # no pairs to learn from: the painting's mean light
        toned = cloth.show(design) * (t[..., :3].mean(axis=2, keepdims=True) / 128.0)
    out = t.copy()
    out[..., :3] = np.where(cloth.mask[..., None], toned, t[..., :3])
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


def state_fits(kinds):
    """The colour change of each button state from the normal one, measured set by set."""
    normal = kinds["button_normal"]
    return {s: state_fit(normal.stack, kinds["button_" + s].stack, normal.box) for s in STATES[1:]}


def set_images(design, kinds, warp=WARP, fits=None):
    """Every texture of the set as RGBA arrays, by kind ("flag", "postgame", "button_<state>",
    "large_<state>"): what make_set writes, in memory (the studio previews them live)."""
    images = {}
    fl = ingame_flag(design)
    images["flag"] = fl
    flag_rgb = fl[..., :3].astype(np.float32)
    fits = fits if fits is not None else state_fits(kinds)
    for prefix in ("button_", "large_"):
        if prefix + "normal" not in kinds:
            continue
        for s in STATES:
            k = kinds.get(prefix + s) or kinds[prefix + "normal"]
            images[prefix + s] = button(k, flag_rgb, fits.get(s))
    images["postgame"] = postgame(kinds["postgame"], design, warp)
    return images


def make_set(design, name, kinds, out, flags_dir, buttons_dir, warp=WARP, fits=None):
    images = set_images(design, kinds, warp, fits)
    files = {"flag": write(os.path.join(out, "art", flags_dir, name + ".ddt"), images["flag"],
                           ddt.Header(0, 0, ddt.BGRA, 1, 128, 128, []))}
    for prefix, sub in (("button_", ""), ("large_", "_large")):
        if prefix + "normal" not in kinds:
            continue
        for s in STATES:
            k = kinds.get(prefix + s) or kinds[prefix + "normal"]
            files[prefix + s] = write(os.path.join(out, "art", buttons_dir, f"flag_{name}{sub}_{s}.ddt"),
                                      images[prefix + s], k.header)
    files["postgame"] = write(os.path.join(out, "art", flags_dir, f"ingame_ui_postgame_flag_{name}.ddt"),
                              images["postgame"], kinds["postgame"].header)
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
    ap.add_argument("--fit-warp", action="store_true",
                    help="fit the postgame cloth's warp on this copy and use it (about a minute)")
    a = ap.parse_args(argv)
    if os.path.abspath(a.out).lower().startswith(os.path.abspath(a.game).lower()):
        sys.exit("refusing to write into the game copy; --out elsewhere")
    with open(a.design, "rb") as f:
        design = pngio.read_png(f.read())
    if design.shape[2] == 4:
        design = design[..., :3]
    kinds, names = survey(a.game, a.flags_dir, a.buttons_dir)
    print(f"measured {len(names)} button sets, {kinds['postgame'].stack.shape[0]} postgame flags")
    warp = WARP
    if a.fit_warp:
        warp, e = fit_warp(kinds["postgame"])
        print(f"fitted postgame warp {warp} (mean square error {e:.0f})")
    files = make_set(design, a.name, kinds, a.out, a.flags_dir, a.buttons_dir, warp)
    for k, p in files.items():
        print(f"{k:16s} {ddt.read_header(open(p, 'rb').read(64)).describe():50s} {p}")
    if a.preview:
        preview(files, a.game, a.flags_dir, a.buttons_dir,
                [c for c in a.compare.split(",") if c], a.preview)
        print("preview", a.preview)


if __name__ == "__main__":
    main()
