# SPDX-License-Identifier: GPL-3.0-or-later
"""Repaints a unit's texture part by part, from the masks of tools/uv_atlas.py, and writes it as
the game reads it: the .ddt in a chosen format and its bump map. A new uniform on an old model,
without touching its mesh.

    venv\\Scripts\\python -I tools\\retexture.py <recipe.json> [--preview <sheet.png>]
        [--url http://127.0.0.1:8188]

The recipe (paths relative to the recipe's folder):

    {"texture": "orig.ddt",            the texture to start from (.ddt or .png)
     "atlas": "atlas_folder",          what uv_atlas.py wrote for that model (atlas.json)
     "scale": 4,                       upscale first (a 64 px texture painted at 256 px)
     "out": "new.ddt",                 the texture to write (.ddt; .png also accepted)
     "format": "same",                 same | BGRA | DXT1 | DXT3 | DXT5
     "mips": "same",                   same | full | none
     "bump": "new_b.ddt",              optional: a bump map made from the result
     "bump_strength": 6,
     "png": "new.png",                 optional: the result as a PNG (alpha kept)
     "ops": [ {"where": [...], "op": "...", ...}, ... ]}

Each op paints the pixels its "where" selects, in order. "where" is a list of terms, unioned;
a term starting with "-" is taken away:

    "part:torso"   a part or group of the atlas (head, torso, arm_l, arms, legs, feet, body...)
    "island:3"     one island by its number on atlas.png
    "bone:Bip01 Head"  the islands of that bone
    "rect:x0,y0,x1,y1" a box in fractions of the texture (0..1, y down)
    "png:file.png"     a painted mask (white = selected), any size
    "pc"           where the starting texture shows the player colour (alpha below 255)
    "all"          everything

and optionally "near": "#rrggbb", "tol": 60 (only pixels of the starting texture within that
distance of the colour) or "lum": [lo, hi] (their brightness, 0..255); "rows": [[y0, y1], ...]
and "cols": [[x0, x1], ...] (bands in fractions of the selection's own box: stripes, piping,
belts, cuffs across a part); "edge": px (only a rim that wide inside the selection's border: a
hat's binding, a coat's piping); and "feather": px.

The ops:

    recolour   "colour": "#rrggbb", "shading": 1.0 (how much of the old light and folds is kept),
               "amount": 1.0
    tone       "hue": degrees, "sat": factor, "value": factor
    fill       "swatch": file.png (a tileable swatch, e.g. from tools/make_texture.py),
               "tile": px, "tint": "#rrggbb" (optional), "shading": 1.0, "amount": 1.0
    paste      "image": file.png, "box": [x0, y0, x1, y1] (fractions, y down): a design drawn in
               UV space, its own alpha respected, "shading": 0.0..1.0
    blur       "radius": px, "passes": 2: smooths away painted detail (rivets, plates, lace)
               before a recolour
    grain     "amount": 0..1, "cell": px, "kind": "weave" | "noise": the texture of wool or
               cotton over a flat repaint
    player     "amount": 0..1: how much of the player colour shows (sets the alpha: 0 = none,
               1 = all); without this op the starting alpha is kept, so the team colour stays
               where it was
    ai         "prompt": "...", "strength": 0.45, "seed": 1: the selection's box repainted by the
               local ComfyUI (core/meshtex.py, core/airepaint.py: SDXL and ControlNet held by the
               edges, the mean colour and the player colour kept, the edge guard), then laid back
               inside the selection only; "guard": false skips the edge check. Needs ComfyUI
               and the GPU (docs/ai-textures.md); --url.

--preview writes a sheet: the start, the result and the result with a player colour.

    venv\\Scripts\\python -I tools\\retexture.py --own-texture <in.gr2> <out.gr2> OLD=NEW [OLD=NEW ...]

writes a copy of an uncompressed model whose stored texture paths OLD (art paths, no extension)
read NEW instead, at the same length (own_texture_paths): a unit copy that shows its new texture
without a <replacetexture>, for when the game keeps the original's texture on a shared model.
Needs numpy. Recipes, textures and sheets of a mod's art stay outside any repository.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import uv_atlas  # noqa: E402
from aoe3game import ddt  # noqa: E402
from core import airepaint  # noqa: E402
from core.pngio import encode_png, read_png  # noqa: E402

FORMATS = {"BGRA": ddt.BGRA, "DXT1": ddt.DXT1, "DXT3": ddt.DXT3, "DXT5": ddt.DXT5}
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


class RecipeError(ValueError):
    pass


def colour(text):
    t = str(text).lstrip("#")
    if len(t) != 6:
        raise RecipeError(f"a colour is #rrggbb, not {text!r}")
    return np.array([int(t[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def upscale(rgba, k):
    """The texture k times larger: colour resampled linearly, the player-colour alpha by its
    nearest pixel (a soft edge would leave a halo of half team colour)."""
    if k == 1:
        return rgba.copy()
    h, w = rgba.shape[:2]
    rgb = np.clip(airepaint.resize(rgba[:, :, :3], h * k, w * k) + 0.5, 0, 255).astype(np.uint8)
    a = np.repeat(np.repeat(rgba[:, :, 3], k, 0), k, 1)
    return np.concatenate([rgb, a[:, :, None]], axis=2)


def luminance(rgb):
    return np.asarray(rgb, np.float32)[..., :3] @ LUMA


# --------------------------------------------------------------------------------------------------
# Selections

class Masks:
    """The atlas's islands rasterised at the texture's size, on demand."""

    def __init__(self, atlas, w, h):
        self.atlas, self.w, self.h = atlas, w, h
        self._cache = {}

    def island(self, i):
        if i not in self._cache:
            row = next((r for r in self.atlas["islands"] if r["id"] == i), None)
            if row is None:
                raise RecipeError(f"no island {i} in the atlas")
            self._cache[i] = uv_atlas.rasterise(np.array(row["uv"], np.float32), self.w, self.h, grow=1)
        return self._cache[i]

    def ids(self, test):
        return [r["id"] for r in self.atlas["islands"] if test(r)]

    def union(self, ids):
        m = np.zeros((self.h, self.w), bool)
        for i in ids:
            m |= self.island(i)
        return m


def _term(term, masks, start, base):
    w, h = masks.w, masks.h
    kind, _, arg = term.partition(":")
    if term == "all":
        return np.ones((h, w), bool)
    if term == "pc":
        return start[:, :, 3] < 255
    if kind == "part":
        parts = uv_atlas.GROUPS.get(arg, (arg,))
        if arg == "body":
            return masks.union(masks.ids(lambda r: True))
        ids = masks.ids(lambda r: r["part"] in parts)
        if not ids:
            raise RecipeError(f"no island of part {arg!r} (atlas parts: {masks.atlas.get('parts')})")
        return masks.union(ids)
    if kind == "island":
        return masks.union([int(v) for v in arg.split(",")])
    if kind == "bone":
        ids = masks.ids(lambda r: (r.get("bone") or "").lower() == arg.lower())
        if not ids:
            raise RecipeError(f"no island moved by bone {arg!r}")
        return masks.union(ids)
    if kind == "rect":
        x0, y0, x1, y1 = (float(v) for v in arg.split(","))
        m = np.zeros((h, w), bool)
        m[int(round(y0 * h)):int(round(y1 * h)), int(round(x0 * w)):int(round(x1 * w))] = True
        return m
    if kind == "png":
        img = np.asarray(read_png(open(os.path.join(base, arg), "rb").read()), np.float32)
        if img.ndim == 3:
            img = img[:, :, :3].mean(axis=2)
        img = airepaint.resize(img[:, :, None], h, w)[:, :, 0]
        return img > 127
    raise RecipeError(f"unknown selection {term!r}")


def select(op, masks, start, base):
    """A float mask (0..1) of the pixels an op paints."""
    where = op.get("where", ["all"])
    if isinstance(where, str):
        where = [where]
    m = np.zeros((masks.h, masks.w), bool)
    for term in where:
        if term.startswith("-"):
            continue
        m |= _term(term, masks, start, base)
    for term in where:
        if term.startswith("-"):
            m &= ~_term(term[1:], masks, start, base)
    if "near" in op:
        d = np.linalg.norm(start[:, :, :3].astype(np.float32) - colour(op["near"]), axis=2)
        m &= d <= float(op.get("tol", 60))
    if "lum" in op:
        lo, hi = op["lum"]
        y = luminance(start)
        m &= (y >= lo) & (y <= hi)
    if op.get("edge"):
        inner = m.copy()
        for _ in range(int(op["edge"])):
            p = np.pad(inner, 1)                      # beyond the texture counts as outside
            inner = inner & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        m &= ~inner
    if ("rows" in op or "cols" in op) and m.any():
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        keep = np.zeros(m.shape, bool)
        for a0, a1 in op.get("rows", []):
            keep[int(round(y0 + a0 * (y1 - y0))):int(round(y0 + a1 * (y1 - y0))), :] = True
        if "cols" in op:
            ck = np.zeros(m.shape, bool)
            for a0, a1 in op["cols"]:
                ck[:, int(round(x0 + a0 * (x1 - x0))):int(round(x0 + a1 * (x1 - x0)))] = True
            keep = (keep & ck) if "rows" in op else ck
        m &= keep
    f = m.astype(np.float32)
    for _ in range(int(op.get("feather", 0))):
        p = np.pad(f, 1, mode="edge")
        f = (p[1:-1, 1:-1] * 4 + p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 8
    return f


# --------------------------------------------------------------------------------------------------
# Painting

def shaded(target, rgb, m, shading):
    """`target` (an RGB colour or an H x W x 3 image) lit by the selection's own light and folds:
    each pixel's brightness over the selection's mean, raised to `shading`."""
    y = luminance(rgb)
    sel = m > 0.5
    mean = float(y[sel].mean()) if sel.any() else 128.0
    light = (np.maximum(y, 1.0) / max(mean, 1.0)) ** float(shading)
    return np.asarray(target, np.float32) * light[:, :, None]


def _hsv(rgb):
    r, g, b = (rgb[..., i] / 255.0 for i in range(3))
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rr = nz & (mx == r)
    gg = nz & (mx == g) & ~rr
    bb = nz & ~rr & ~gg
    h[rr] = ((g - b)[rr] / d[rr]) % 6
    h[gg] = (b - r)[gg] / d[gg] + 2
    h[bb] = (r - g)[bb] / d[bb] + 4
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h * 60.0, s, mx


def _rgb(h, s, v):
    h = (h % 360.0) / 60.0
    c = v * s
    x = c * (1 - np.abs(h % 2 - 1))
    z = np.zeros_like(h)
    k = np.floor(h).astype(int) % 6
    r = np.choose(k, [c, x, z, z, x, c])
    g = np.choose(k, [x, c, c, x, z, z])
    b = np.choose(k, [z, z, x, c, c, x])
    m = v - c
    return np.stack([r + m, g + m, b + m], axis=-1) * 255.0


def weave(h, w, cell, seed=0):
    """A tileable cloth grain around 1.0: alternating warp and weft ridges and a little noise."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    c = max(1.0, float(cell))
    warp = np.cos(np.pi * x / c) ** 2
    weft = np.cos(np.pi * y / c) ** 2
    check = ((np.floor(x / c) + np.floor(y / c)) % 2).astype(np.float32)
    g = np.where(check > 0, warp, weft) * 0.6 + rng.random((h, w)).astype(np.float32) * 0.4
    return g / max(float(g.mean()), 1e-6)


def apply(op, img, start, masks, base, client=None):
    """Paints one op into `img` (H x W x 4 float32) in place."""
    m = select(op, masks, start, base)
    if not m.any():
        raise RecipeError(f"op {op.get('op')} selects nothing ({op.get('where')})")
    kind = op.get("op")
    rgb = img[:, :, :3]
    amount = float(op.get("amount", 1.0))
    new = None
    if kind == "recolour":
        new = shaded(colour(op["colour"]), rgb, m, op.get("shading", 1.0))
    elif kind == "tone":
        h, s, v = _hsv(np.clip(rgb, 0, 255))
        new = _rgb(h + float(op.get("hue", 0)), np.clip(s * float(op.get("sat", 1)), 0, 1),
                   np.clip(v * float(op.get("value", 1)), 0, 1))
    elif kind == "fill":
        sw = np.asarray(read_png(open(os.path.join(base, op["swatch"]), "rb").read()), np.float32)
        if sw.ndim == 2:
            sw = np.stack([sw] * 3, axis=-1)
        sw = sw[:, :, :3]
        t = int(op.get("tile", sw.shape[0]))
        sw = airepaint.resize(sw, t, int(round(t * sw.shape[1] / sw.shape[0])))
        reps = (-(-img.shape[0] // sw.shape[0]), -(-img.shape[1] // sw.shape[1]), 1)
        tiled = np.tile(sw, reps)[:img.shape[0], :img.shape[1]]
        if "tint" in op:
            tiled = tiled / max(float(luminance(tiled).mean()), 1.0) * colour(op["tint"])
        new = shaded(tiled, rgb, m, op.get("shading", 1.0))
    elif kind == "paste":
        x0, y0, x1, y1 = op["box"]
        H, W = img.shape[:2]
        bx0, by0 = int(round(x0 * W)), int(round(y0 * H))
        bx1, by1 = max(bx0 + 1, int(round(x1 * W))), max(by0 + 1, int(round(y1 * H)))
        design = np.asarray(read_png(open(os.path.join(base, op["image"]), "rb").read()), np.float32)
        if design.ndim == 2:
            design = np.stack([design] * 3, axis=-1)
        if design.shape[2] == 3:
            design = np.concatenate([design, np.full(design.shape[:2] + (1,), 255, np.float32)], axis=2)
        d = airepaint.resize(design, by1 - by0, bx1 - bx0)
        new = rgb.copy()
        a = np.zeros(m.shape, np.float32)
        new[by0:by1, bx0:bx1] = d[:, :, :3]
        a[by0:by1, bx0:bx1] = d[:, :, 3] / 255.0
        if op.get("shading", 0):
            new = new * (shaded((1.0, 1.0, 1.0), rgb, m, op["shading"]))
        m = m * a
    elif kind == "blur":
        new = rgb.copy()
        for _ in range(int(op.get("passes", 2))):
            r = int(op.get("radius", 2))
            p = np.pad(new, ((r, r), (r, r), (0, 0)), mode="edge")
            acc = np.zeros_like(new)
            for dy in range(2 * r + 1):
                for dx in range(2 * r + 1):
                    acc += p[dy:dy + new.shape[0], dx:dx + new.shape[1]]
            new = acc / (2 * r + 1) ** 2
    elif kind == "grain":
        g = (weave if op.get("kind", "weave") == "weave" else
             lambda h, w, c, seed=0: 1 + (np.random.default_rng(seed).random((h, w)) - 0.5))(
            img.shape[0], img.shape[1], op.get("cell", 2), int(op.get("seed", 0)))
        new = rgb * (1 + (g - 1) * amount)[:, :, None]
        amount = 1.0
    elif kind == "player":
        a = 255.0 * (1.0 - float(op.get("amount", 1.0)))
        img[:, :, 3] = img[:, :, 3] * (1 - m) + a * m
        return
    elif kind == "ai":
        new = ai_repaint(img, m, op, client)
    else:
        raise RecipeError(f"unknown op {kind!r}")
    k = (m * amount)[:, :, None]
    img[:, :, :3] = rgb * (1 - k) + np.clip(new, 0, 255) * k


def ai_repaint(img, m, op, client):
    """The selection's box repainted through core/meshtex.py and core/airepaint.py (a square
    texture is what they take: a non-square one is padded and cropped back)."""
    from core import comfy, meshtex
    if client is None:
        client = comfy.Client()
    h, w = img.shape[:2]
    side = max(h, w)
    sq = np.zeros((side, side, 4), np.uint8)
    sq[:h, :w] = np.clip(img + 0.5, 0, 255).astype(np.uint8)
    ys, xs = np.nonzero(m > 0.5)
    zone = ("sel", xs.min() / side, 1 - (ys.max() + 1) / side, (xs.max() + 1) / side, 1 - ys.min() / side)
    try:
        model = meshtex.model_for([zone], side, prompts={"sel": op["prompt"]})
    except ValueError as exc:
        raise RecipeError(f"ai: {exc}") from exc
    out, report = airepaint.repaint(sq, model, client, strength=float(op.get("strength", 0.45)),
                                    seed=int(op.get("seed", 1)), prompt=op["prompt"],
                                    guard=bool(op.get("guard", True)))
    op["_report"] = report
    return out[:h, :w, :3].astype(np.float32)


# --------------------------------------------------------------------------------------------------
# Writing

def write_ddt(rgba, fmt, like, mips):
    """The .ddt bytes: `like` (the start's header) gives the alpha mode and usage, `fmt` and
    `mips` ("same", "full", "none") the rest."""
    use_mips = like.mips > 1 if mips == "same" else mips == "full"
    if fmt == ddt.DXT5:
        return ddt.write_dxt(rgba, ddt.DXT5, alpha=like.alpha, usage=like.usage, mips=use_mips)
    return ddt.write(rgba, fmt, alpha=like.alpha, usage=like.usage, mips=use_mips)


def run(recipe, base, client=None):
    """Paints a recipe; returns (start RGBA scaled, result RGBA, written paths)."""
    src = os.path.join(base, recipe["texture"])
    with open(src, "rb") as fh:
        data = fh.read()
    if data[:4] == ddt.MAGIC:
        like = ddt.read_header(data)
        start = ddt.decode(data, 0)
    else:
        like = ddt.Header(0, 1, ddt.BGRA, 1, 0, 0, [])
        start = uv_atlas.read_image(src)
    k = int(recipe.get("scale", 1))
    start = upscale(start, k)
    with open(os.path.join(base, recipe["atlas"], "atlas.json"), encoding="utf-8") as fh:
        atlas = json.load(fh)
    h, w = start.shape[:2]
    masks = Masks(atlas, w, h)
    img = start.astype(np.float32)
    for op in recipe.get("ops", []):
        apply(op, img, start, masks, base, client)
    result = np.clip(img + 0.5, 0, 255).astype(np.uint8)
    written = []
    out = os.path.join(base, recipe["out"])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if out.lower().endswith(".png"):
        blob = encode_png(result)
    else:
        name = str(recipe.get("format", "same")).upper()
        fmt = like.format if name == "SAME" else FORMATS.get(name)
        if fmt is None:
            raise RecipeError(f"format {recipe.get('format')!r}: one of same, {', '.join(FORMATS)}")
        blob = write_ddt(result, fmt, like, recipe.get("mips", "same"))
    with open(out, "wb") as fh:
        fh.write(blob)
    written.append(out)
    if recipe.get("bump"):
        bump = ddt.write_normal_map(ddt.normal_from_texture(result, float(recipe.get("bump_strength", 6.0))))
        path = os.path.join(base, recipe["bump"])
        with open(path, "wb") as fh:
            fh.write(bump)
        written.append(path)
    if recipe.get("png"):
        path = os.path.join(base, recipe["png"])
        with open(path, "wb") as fh:
            fh.write(encode_png(result))
        written.append(path)
    return start, result, written


def preview(start, result, path, team=(40, 90, 220)):
    """Start, result, and the result over a player colour, side by side (at least 256 px each)."""
    def flat(img):
        a = img[:, :, 3:4].astype(np.float32) / 255.0
        return (img[:, :, :3] * a + np.array(team, np.float32) * (1 - a)).astype(np.uint8)
    k = max(1, -(-256 // max(start.shape[:2])))
    big = lambda im: np.repeat(np.repeat(im, k, 0), k, 1)  # noqa: E731
    gap = np.full((start.shape[0] * k, 8, 3), 30, np.uint8)
    sheet = np.concatenate([big(start[:, :, :3]), gap, big(result[:, :, :3]), gap, big(flat(result))], axis=1)
    with open(path, "wb") as fh:
        fh.write(encode_png(sheet))


# --------------------------------------------------------------------------------------------------
# A model of its own texture (--own-texture)

def own_texture_paths(data, renames):
    """The bytes of an uncompressed Granny model whose stored texture paths are renamed, in place
    and at the same length, with the file's CRC recomputed. `renames`: {old art path: new art path}
    (no extension, as <replacetexture> writes them, any case). Every stored texture name whose art
    path matches is renamed: the part before it (the artist's drive and folders) and the extension
    are kept. Returns (new bytes, [(old name, new name)]). ValueError when a model is compressed,
    when a new path has another length than the one it replaces, or when nothing matches.

    Why: a <replacetexture> in an anim file asks the game to show another texture on a shared
    model, and in some scenarios the game shows the model's own texture instead (seen in WoL's
    Laguna, 2026-11-14: the copy of a unit kept the original's texture there and showed its own
    on a test map; the cause is not known). A copy of the model that names its own texture needs
    no swap."""
    import named_models as nm
    from aoe3game import gr2
    if not gr2.header_facts(data).get("raw"):
        raise ValueError("the model is compressed: write it uncompressed first (the Granny bridge)")
    want = {k.lower().replace("/", "\\"): v.replace("/", "\\") for k, v in renames.items()}
    root = gr2.load(data).root()
    out = bytearray(data)
    done = []
    for t in root.get("Textures") or []:
        name = t.get("FromFileName") if t is not None else None
        if not name:
            continue
        key = nm.art_key(name)
        if key not in want:
            continue
        low = name.lower().replace("/", "\\")
        at = low.rfind(key)
        new_key = want[key]
        if len(new_key) != len(key):
            raise ValueError(f"{new_key!r} has {len(new_key)} characters; it replaces {key!r} in the "
                             f"model, so it needs {len(key)}")
        new = name[:at] + new_key + name[at + len(key):]
        old_b, new_b = name.encode("cp1252") + b"\0", new.encode("cp1252") + b"\0"
        hits = out.count(old_b)
        if not hits:
            raise ValueError(f"{name!r} is not stored as a plain string in the file")
        out = bytearray(bytes(out).replace(old_b, new_b))
        done.append((name, new))
    if not done:
        raise ValueError(f"no stored texture matches {sorted(want)}")
    import struct
    struct.pack_into("<I", out, 0x28, gr2.file_crc(bytes(out)))
    return bytes(out), done


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    if "--own-texture" in argv:     # --own-texture <in.gr2> <out.gr2> OLD=NEW [OLD=NEW ...]
        i = argv.index("--own-texture")
        src, dst, pairs = argv[i + 1], argv[i + 2], argv[i + 3:]
        with open(src, "rb") as fh:
            data = fh.read()
        try:
            new, done = own_texture_paths(data, dict(p.split("=", 1) for p in pairs))
        except ValueError as exc:
            print(f"{src}: {exc}")
            return 1
        with open(dst, "wb") as fh:
            fh.write(new)
        for a, b in done:
            print(f"{a} -> {b}")
        return 0
    values = {opt("--preview"), opt("--url")}
    recipe_path = next((a for a in argv if not a.startswith("--") and a not in values), None)
    if not recipe_path:
        print(__doc__)
        return 2
    with open(recipe_path, encoding="utf-8") as fh:
        recipe = json.load(fh)
    client = None
    if opt("--url") or any(op.get("op") == "ai" for op in recipe.get("ops", [])):
        from core import comfy
        client = comfy.Client(opt("--url", comfy.DEFAULT_URL))
    try:
        start, result, written = run(recipe, os.path.dirname(os.path.abspath(recipe_path)), client)
    except RecipeError as exc:
        print(f"{recipe_path}: {exc}")
        return 1
    for op in recipe.get("ops", []):
        if "_report" in op:
            print(f"ai: {op['_report']}")
    if opt("--preview"):
        preview(start, result, opt("--preview"))
        written.append(opt("--preview"))
    print("wrote " + ", ".join(written))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
