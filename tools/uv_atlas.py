# SPDX-License-Identifier: GPL-3.0-or-later
"""The UV layout of a unit's model drawn over its texture, each island labelled with the body part
that moves it, and one mask per part: the map tools/retexture.py paints by.

    venv\\Scripts\\python -I tools\\uv_atlas.py <target> --game <game folder> --out <folder>
        [--prefer a,b] [--texture <file.ddt or .png>] [--size WxH] [--by bone|position]
        [--overlay <folder>] [--cache <folder>] [--granny <bridge.exe>] [--granny-install <folder>]

<target>    a proto name, an anim file or a model, as tools/named_models.py resolves them (the
            model the anim file shows standing, its <replacetexture> applied to find the texture)
--texture   paint over this texture instead of the model's own
--size      the masks' size (default the texture's): masks are drawn from the UV triangles, so
            they can be made for an upscaled texture
--by        bone (default): an island's part is that of the bone with the most skin weight over
            its vertices (`Bip01 L UpperArm` -> arm_l); a model without skin weights falls back to
            position. position: by where the island's vertices stand on the model (height and
            side), for models whose bones say nothing useful.

Writes into --out:
    atlas.png       the texture (enlarged to at least 512 px), dimmed, with every UV triangle's
                    edges in its part's colour, each island's number at its centre, and a legend
    atlas.json      the model, texture and size, and per island: number, part, bone, the bone's
                    share of the weight, pixel box, area, and its UV triangles (what retexture.py
                    rasterises at any size)
    islands.png     grey image, each pixel the number of its island plus one (0: no island)
    masks\\<part>.png one white-on-black mask per part, plus the groups arms, hands, legs, feet
                    and body (everything)

Parts: head, torso, arm_l, arm_r, hand_l, hand_r, leg_l, leg_r, foot_l, foot_r, tail (ponytail
and coat-tail bones), prop, other. Left and right are the model's own (Biped L is its left).
Needs numpy; no Blender. The pictures show a game's or a mod's art: write them outside any
repository.
"""
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import bitfont  # noqa: E402
from aoe3game import ddt, gr2, gr2_mesh  # noqa: E402
from core.pngio import encode_png, read_png  # noqa: E402

PARTS = ("head", "torso", "arm_l", "arm_r", "hand_l", "hand_r", "leg_l", "leg_r", "foot_l",
         "foot_r", "tail", "prop", "other")
GROUPS = {"arms": ("arm_l", "arm_r"), "hands": ("hand_l", "hand_r"), "legs": ("leg_l", "leg_r"),
          "feet": ("foot_l", "foot_r")}
COLOURS = {"head": (255, 220, 60), "torso": (255, 70, 70), "arm_l": (70, 160, 255),
           "arm_r": (40, 220, 255), "hand_l": (170, 120, 255), "hand_r": (255, 120, 230),
           "leg_l": (60, 230, 90), "leg_r": (170, 255, 60), "foot_l": (255, 160, 40),
           "foot_r": (200, 120, 60), "tail": (255, 255, 255), "prop": (150, 150, 150),
           "other": (120, 120, 120)}


# --------------------------------------------------------------------------------------------------
# Parts

def part_of_bone(name):
    """The part a bone name moves, from the Biped names the game's units use (Bip01 Head, Bip01 L
    UpperArm...); None for a name that says nothing (a root, a hitpoint bar)."""
    n = (name or "").lower().replace("_", " ")
    words = n.split()
    side = "_l" if " l " in f" {n} " else "_r" if " r " in f" {n} " else ""
    if any(k in n for k in ("head", "neck", "hair", "jaw", "eye")):
        return "head"
    if "ponytail" in n or "tail" in words or "cape" in n or "coat" in n:
        return "tail"
    if any(k in n for k in ("hand", "finger")):
        return "hand" + (side or "_r")
    if any(k in n for k in ("clavicle", "upperarm", "forearm", "arm")):
        return "arm" + (side or "_r")
    if any(k in n for k in ("foot", "toe")):
        return "foot" + (side or "_r")
    if any(k in n for k in ("thigh", "calf", "leg")):
        return "leg" + (side or "_r")
    if any(k in n for k in ("spine", "pelvis", "chest", "torso")):
        return "torso"
    if "prop" in n:
        return "prop"
    return None


def part_by_position(centre, lo, hi):
    """The part of a point by where it stands on the model's box (Z up, the model's left at +X as
    the reader turns it): the top eighth is the head, below 45 % the legs (the lowest 6 % the
    feet), out to the side beyond 22 % of the width the arms, the rest the torso."""
    x, _y, z = centre
    h = max(hi[2] - lo[2], 1e-6)
    t = (z - lo[2]) / h
    mid = (lo[0] + hi[0]) / 2
    side = "_l" if x > mid else "_r"
    if t > 0.87:
        return "head"
    if t < 0.06:
        return "foot" + side
    if t < 0.45:
        return "leg" + side
    if abs(x - mid) > 0.22 * max(hi[0] - lo[0], 1e-6) * 1.0 and t < 0.85:
        return "arm" + side
    return "torso"


# --------------------------------------------------------------------------------------------------
# Islands

class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def islands(model, by="bone"):
    """[{id, mesh, part, bone, share, uv (K x 3 x 2, v up), centre}] of a model read by
    gr2_mesh.read: the triangles joined through shared vertices and through vertices that share
    both their UV and their place (a packed stream splits the rigid and skinned parts of one
    surface), largest first."""
    out = []
    pts = [m["positions"] for m in model["meshes"] if len(m["positions"])]
    allp = np.concatenate(pts) if pts else np.zeros((1, 3))
    lo, hi = allp.min(0), allp.max(0)
    for mi, mesh in enumerate(model["meshes"]):
        tris = np.asarray(mesh["triangles"], np.int64)
        uv = mesh["uvs"]
        if uv is None or not len(tris):
            continue
        nv = len(mesh["positions"])
        u = _Union(nv)
        key = {}
        for v in range(nv):
            k = (tuple(np.round(uv[v], 4)), tuple(np.round(mesh["positions"][v], 3)))
            if k in key:
                u.join(key[k], v)
            else:
                key[k] = v
        for a, b, c in tris:
            u.join(int(a), int(b))
            u.join(int(a), int(c))
        groups = {}
        for t, (a, _b, _c) in enumerate(tris):
            groups.setdefault(u.find(int(a)), []).append(t)
        names = mesh.get("skin_names") or []
        vb, vw = mesh.get("vertex_bones"), mesh.get("vertex_weights")
        for tlist in groups.values():
            tl = tris[tlist]
            verts = np.unique(tl)
            centre = mesh["positions"][verts].mean(0)
            bone, share, part = None, 0.0, None
            if by == "bone" and vb is not None and names:
                weight = {}
                for v in verts:
                    for k in range(vb.shape[1]):
                        b = int(vb[v, k])
                        if 0 <= b < len(names) and vw[v, k] > 0:
                            weight[names[b]] = weight.get(names[b], 0.0) + float(vw[v, k])
                ranked = sorted(weight.items(), key=lambda kv: -kv[1])
                for name, w in ranked:            # the heaviest bone that names a part
                    p = part_of_bone(name)
                    if p is not None:
                        bone, part = name, p
                        share = w / max(sum(weight.values()), 1e-9)
                        break
            if part is None:
                part = part_by_position(centre, lo, hi)
            tuv = uv[tl].astype(np.float32)
            # a triangle stretched over more than the whole texture (a degenerate UV, seen on some
            # stock models) cannot be painted: it is left out of the island's layout
            span = tuv.max(axis=1) - tuv.min(axis=1)
            fit = (span <= 1.0).all(axis=1)
            if not fit.any():
                continue
            out.append({"mesh": mi, "part": part, "bone": bone, "share": round(share, 3),
                        "uv": tuv[fit], "centre": centre, "triangles": int(fit.sum()),
                        "stretched": int((~fit).sum())})
    out.sort(key=lambda i: -_uv_area(i["uv"]))
    for n, isl in enumerate(out):
        isl["id"] = n
    return out


def _uv_area(uv):
    a, b, c = uv[:, 0], uv[:, 1], uv[:, 2]
    return float(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])).sum() / 2)


# --------------------------------------------------------------------------------------------------
# Rasterising in texture space

def to_pixels(uv, w, h):
    """UV (v up, as gr2_mesh gives them) -> pixel coordinates (x right, y down), each triangle moved
    by whole tiles so that its centre lies in the texture (a UV of 1.25 wraps to 0.25)."""
    p = np.empty_like(uv, dtype=np.float64)
    p[..., 0] = uv[..., 0]
    p[..., 1] = 1.0 - uv[..., 1]
    shift = np.floor(p.mean(axis=1, keepdims=True))
    p = p - shift
    p[..., 0] *= w
    p[..., 1] *= h
    return p


def rasterise(uv, w, h, grow=0):
    """An h x w bool mask of the triangles (pixel centres inside, edges included), grown by `grow`
    pixels so the texture's filtering at the island's border reads painted pixels too."""
    mask = np.zeros((h, w), bool)
    for tri in to_pixels(np.asarray(uv), w, h):
        x0, y0 = np.floor(tri.min(0)).astype(int)
        x1, y1 = np.ceil(tri.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        px, py = xs + 0.5, ys + 0.5
        (ax, ay), (bx, by_), (cx, cy) = tri
        d = (by_ - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by_ - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
        l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
        l3 = 1 - l1 - l2
        eps = 1e-6
        inside = (l1 >= -eps) & (l2 >= -eps) & (l3 >= -eps)
        mask[y0:y1, x0:x1] |= inside
        # thin triangles that cover no pixel centre still mark the pixels of their corners
        for vx, vy in tri:
            ix, iy = int(min(max(vx, 0), w - 1)), int(min(max(vy, 0), h - 1))
            mask[iy, ix] = True
    for _ in range(grow):
        g = mask.copy()
        g[1:] |= mask[:-1]
        g[:-1] |= mask[1:]
        g[:, 1:] |= mask[:, :-1]
        g[:, :-1] |= mask[:, 1:]
        mask = g
    return mask


def line(img, a, b, colour):
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
    xs = np.clip(np.rint(np.linspace(a[0], b[0], n)).astype(int), 0, img.shape[1] - 1)
    ys = np.clip(np.rint(np.linspace(a[1], b[1], n)).astype(int), 0, img.shape[0] - 1)
    img[ys, xs] = colour


# --------------------------------------------------------------------------------------------------
# Building the atlas

def masks(isl, w, h, grow=1):
    """({part or group: h x w bool}, h x w int labels: island id + 1, 0 for none)."""
    out = {}
    labels = np.zeros((h, w), np.int32)
    for i in sorted(isl, key=lambda i: _uv_area(i["uv"])):        # small islands drawn last
        m = rasterise(i["uv"], w, h, grow)
        labels[m & (labels == 0)] = i["id"] + 1
        core = rasterise(i["uv"], w, h, 0)
        labels[core] = i["id"] + 1
        out[i["part"]] = out.get(i["part"], np.zeros((h, w), bool)) | m
    for name, parts in GROUPS.items():
        got = [out[p] for p in parts if p in out]
        if got:
            out[name] = np.logical_or.reduce(got)
    out["body"] = labels > 0
    return out, labels


def picture(texture, isl, scale):
    """The atlas picture: the texture enlarged by `scale` and dimmed, the UV edges in each part's
    colour, island numbers, and a legend strip under it."""
    tex = np.asarray(texture)[:, :, :3]
    h, w = tex.shape[:2]
    big = np.repeat(np.repeat(tex, scale, 0), scale, 1).astype(np.float32) * 0.55
    img = np.clip(big, 0, 255).astype(np.uint8)
    W, H = w * scale, h * scale
    for i in isl:
        col = COLOURS.get(i["part"], (255, 255, 255))
        for tri in to_pixels(i["uv"], W, H):
            for a, b in ((0, 1), (1, 2), (2, 0)):
                line(img, tri[a], tri[b], col)
    fs = 2 if W >= 512 else 1
    for i in isl:
        p = to_pixels(i["uv"], W, H).reshape(-1, 2)
        cx, cy = p.mean(0)
        t = str(i["id"])
        bitfont.draw(img, t, int(cx - bitfont.width(t, fs) / 2), int(cy - 3.5 * fs),
                     (255, 255, 255), fs, shadow=(0, 0, 0))
    used = [p for p in PARTS if any(i["part"] == p for i in isl)]
    rows = (len(used) + 3) // 4
    legend = np.full((rows * 10 * fs + 4 * fs, W, 3), 25, np.uint8)
    cw = W // 4
    for k, p in enumerate(used):
        r, c = divmod(k, 4)
        x, y = c * cw + 4, r * 10 * fs + 2 * fs
        legend[y:y + 7 * fs, x:x + 7 * fs] = COLOURS[p]
        bitfont.draw(legend, p.replace("_", " "), x + 10 * fs, y, (230, 230, 230), fs)
    return np.concatenate([img, legend], axis=0)


def write_atlas(model, texture, out, *, size=None, by="bone", facts=None):
    """Writes atlas.png, atlas.json, islands.png and masks\\*.png into `out`; returns the islands.
    `texture`: H x W x 4 uint8 (or None: a grey square of `size`); `size`: (w, h) of the masks."""
    isl = islands(model, by)
    if texture is None:
        sw, sh = size or (256, 256)
        texture = np.full((sh, sw, 4), 128, np.uint8)
    th, tw = texture.shape[:2]
    w, h = size or (tw, th)
    os.makedirs(os.path.join(out, "masks"), exist_ok=True)
    found, labels = masks(isl, w, h)
    for name, m in found.items():
        with open(os.path.join(out, "masks", name + ".png"), "wb") as fh:
            fh.write(encode_png((m * 255).astype(np.uint8)))
    with open(os.path.join(out, "islands.png"), "wb") as fh:
        fh.write(encode_png(np.clip(labels, 0, 255).astype(np.uint8)))
    scale = max(1, -(-512 // max(tw, th)))
    with open(os.path.join(out, "atlas.png"), "wb") as fh:
        fh.write(encode_png(picture(texture, isl, scale)))
    rows = []
    for i in isl:
        px = to_pixels(i["uv"], w, h).reshape(-1, 2)
        m = rasterise(i["uv"], w, h)
        rows.append({"id": i["id"], "part": i["part"], "bone": i["bone"], "share": i["share"],
                     "mesh": i["mesh"], "triangles": i["triangles"], "stretched": i.get("stretched", 0),
                     "box": [int(px[:, 0].min()), int(px[:, 1].min()), int(np.ceil(px[:, 0].max())),
                             int(np.ceil(px[:, 1].max()))],
                     "pixels": int(m.sum()),
                     "uv": np.round(i["uv"], 6).tolist()})
    doc = dict(facts or {}, size=[w, h], texture_size=[tw, th], by=by, parts=sorted(found),
               islands=rows)
    with open(os.path.join(out, "atlas.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return isl


# --------------------------------------------------------------------------------------------------
# Loading a model of a game copy

def raw_model(data, cache, granny, install):
    """The model's bytes with every section uncompressed (compressed ones through the model
    survey's cache and the external Granny bridge, as tools/model_sheets.py)."""
    if gr2.header_facts(data).get("raw"):
        return data
    import model_survey as ms
    if not cache:
        raise LookupError("the model is compressed: give --cache (and --granny to fill it)")
    md5 = hashlib.md5(data).hexdigest()
    if not granny and not os.path.exists(os.path.join(cache, "raw", md5 + ".gr2")):
        raise LookupError("the model is compressed and not in the cache: give --granny")
    for sub in ("raw", "src"):
        os.makedirs(os.path.join(cache, sub), exist_ok=True)
    return ms.raw_bytes(data, md5, (granny, install, cache))


def read_image(path):
    """H x W x 4 uint8 of a .ddt (its first level) or a .png."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] == ddt.MAGIC:
        return ddt.decode(data, 0)
    img = np.asarray(read_png(data))
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    if img.shape[2] == 3:
        img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.uint8)], axis=2)
    return img.astype(np.uint8)


def load(game, target, prefer=(), cache=None, granny=None, install=None):
    """(model, texture RGBA or None, facts) of a target in a game copy (named_models.Game)."""
    import named_models as nm
    where = game.resolve(target, prefer)
    data, src = game.read(where["model"])
    model = gr2_mesh.read(raw_model(data, cache, granny, install or game.folder))
    if not model["meshes"]:
        raise LookupError(f"{where['model']} has no mesh this reader can open")
    found = game.texture(model["textures"], where["model"], where["replace"])
    tex = ddt.decode(found[1], 0) if found else None
    facts = {"target": target, "model": where["model"], "anim": where["anim"], "source": src,
             "texture": found[0] if found else None,
             "texture_format": ddt.read_header(found[1]).describe() if found else None}
    del nm
    return model, tex, facts


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    values = {opt(k) for k in ("--game", "--out", "--prefer", "--texture", "--size", "--by", "--cache", "--overlay",
                               "--granny", "--granny-install")}
    target = next((a for a in argv if not a.startswith("--") and a not in values), None)
    if not target or not opt("--game") or not opt("--out"):
        print(__doc__)
        return 2
    import named_models as nm
    game = nm.Game(opt("--game"), [opt("--overlay")])
    prefer = [b.lower() for b in (opt("--prefer") or "").split(",") if b]
    try:
        model, tex, facts = load(game, target, prefer, opt("--cache"), opt("--granny"),
                                 opt("--granny-install", opt("--game")))
    except (LookupError, RuntimeError, gr2.Gr2Error) as exc:
        print(f"{target}: {exc}")
        return 1
    if opt("--texture"):
        tex = read_image(opt("--texture"))
        facts["texture"] = opt("--texture")
    size = tuple(int(v) for v in opt("--size").lower().split("x")) if opt("--size") else None
    isl = write_atlas(model, tex, opt("--out"), size=size, by=opt("--by", "bone"), facts=facts)
    counts = {}
    for i in isl:
        counts[i["part"]] = counts.get(i["part"], 0) + 1
    print(f"{facts['model']}: {len(isl)} islands ({', '.join(f'{p} {n}' for p, n in counts.items())}),"
          f" texture {facts['texture']} -> {opt('--out')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
