# SPDX-License-Identifier: GPL-3.0-or-later
"""Studies how the buildings of a game or a mod are built: not what they contain but how they are
made, so the generators can follow it. Development tool; it reads models a survey cached (see
art_survey.py --granny) and writes numbers only.

    venv\\Scripts\\python -I tools\\shape_survey.py <report.json> <cache>/raw --out shapes.json [--limit N]

For each building, in game units, from its model's triangles:

    size, height, slender   its extent, and height over its longer side
    cover                   the share of the obstruction's square under something that stands
    outside                 the share of what stands that is out of that square
    main                    the share of what stands in its largest connected part
    parts                   how many separate parts stand on the ground
    rim                     the share of the square's edge lined by something tall
    court                   the share of the square that is open ground shut in by what stands
    levels                  how many flat levels of roof or terrace it has
    tris_low/mid/high       the triangles in each third of its height
    uv_max                  how far its UVs run (over 1: textures repeat)
    textures, materials     how many of each
    faces_down              the share of triangles facing the ground
"""
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import gr2  # noqa: E402

UNITS_PER_METER = 0.615157485
GRID = 120


def indices(src):
    if isinstance(src, list):                            # an array of one-field records
        return np.array([e.get("Int16") if e.get("Int16") is not None else e.get("Int32") for e in src], np.int64)
    field = src.layout().split(":")[0]
    return np.array([x[0] if isinstance(x, (tuple, list)) else x for x in src.column(field)], np.int64)


def column(vs, name):
    """A vertex column as an array, from a flat blob or a list of records."""
    if isinstance(vs, list):
        vals = [v.get(name) for v in vs]
        return None if vals and vals[0] is None else np.array(vals, np.float32)
    try:
        c = vs.column(name)
    except (KeyError, ValueError):
        return None
    return None if c is None else np.array(list(c), np.float32)


def load(path):
    """(positions, uvs or None, triangles, facts of the file)."""
    with open(path, "rb") as fh:
        doc = gr2.load(fh.read())
    r = doc.root()
    V, UV, T, n0 = [], [], [], 0
    for m in r.get("Meshes") or []:
        if m is None:
            continue
        vd, tt = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        vs = vd.get("Vertices")
        pos = column(vs, "Position")
        if pos is None:
            continue
        i32, i16 = tt.get("Indices"), tt.get("Indices16")
        src = i32 if (len(i32) if isinstance(i32, list) else getattr(i32, "count", 0)) else i16
        idx = indices(src)
        V.append(pos)
        uv = column(vs, "TextureCoordinates0")
        UV.append(uv if uv is not None else np.zeros((len(pos), 2), np.float32))
        T.append(idx.reshape(-1, 3) + n0)
        n0 += len(pos)
    if not V:
        raise ValueError("no plain positions")
    art = r.get("ArtToolInfo")
    return np.concatenate(V), np.concatenate(UV), np.concatenate(T), {
        "upm": (art.get("UnitsPerMeter") if art else 0) or UNITS_PER_METER,
        "up": tuple(art.get("UpVector")) if art else (0.0, 1.0, 0.0),
        "textures": len(r.get("Textures") or []), "materials": len(r.get("Materials") or [])}


def rasterize(p2, tris, lo, cell, shape):
    """The cells of a grid under any of the triangles."""
    img = np.zeros(shape, bool)
    a, b, c = p2[tris[:, 0]], p2[tris[:, 1]], p2[tris[:, 2]]
    x0 = np.clip(np.floor((np.minimum(np.minimum(a, b), c) - lo) / cell).astype(int), 0, None)
    x1 = np.ceil((np.maximum(np.maximum(a, b), c) - lo) / cell).astype(int)
    for k in range(len(tris)):
        ix0, iy0, ix1, iy1 = x0[k, 0], x0[k, 1], min(x1[k, 0], shape[1] - 1), min(x1[k, 1], shape[0] - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        xs = lo[0] + (np.arange(ix0, ix1 + 1) + 0.5) * cell
        ys = lo[1] + (np.arange(iy0, iy1 + 1) + 0.5) * cell
        X, Y = np.meshgrid(xs, ys)
        d = (b[k, 0] - a[k, 0]) * (c[k, 1] - a[k, 1]) - (b[k, 1] - a[k, 1]) * (c[k, 0] - a[k, 0])
        if abs(d) < 1e-9:
            continue
        u = ((b[k, 0] - X) * (c[k, 1] - Y) - (b[k, 1] - Y) * (c[k, 0] - X)) / d
        v = ((c[k, 0] - X) * (a[k, 1] - Y) - (c[k, 1] - Y) * (a[k, 0] - X)) / d
        img[iy0:iy1 + 1, ix0:ix1 + 1] |= (u >= -0.02) & (v >= -0.02) & (u + v <= 1.02)
    return img


def flood(mask, seeds):
    """The cells of `mask` reached from the seed cells."""
    seen = seeds & mask
    while True:
        grown = seen.copy()
        grown[1:, :] |= seen[:-1, :]
        grown[:-1, :] |= seen[1:, :]
        grown[:, 1:] |= seen[:, :-1]
        grown[:, :-1] |= seen[:, 1:]
        grown &= mask
        if (grown == seen).all():
            return seen
        seen = grown


def parts_of(mask):
    """Sizes of the connected parts of a mask, largest first."""
    left = mask.copy()
    out = []
    while left.any():
        y, x = np.unravel_index(int(left.argmax()), left.shape)
        s = np.zeros(left.shape, bool)
        s[y, x] = True
        part = flood(left, s)
        out.append(int(part.sum()))
        left &= ~part
    return sorted(out, reverse=True)


def measure(V, UV, T, facts, rx, rz):
    """The numbers of one building; `V` in game units with Y or Z up, as `facts` says."""
    ui = int(np.argmax(np.abs(facts["up"])))
    h = [i for i in range(3) if i != ui]
    V = V * (UNITS_PER_METER / facts["upm"])
    p2, H = V[:, h], V[:, ui] - V[:, ui].min()
    top = float(H.max())
    if top <= 0.01:
        raise ValueError("flat")
    side = max(float(np.ptp(p2[:, 0])), float(np.ptp(p2[:, 1])), 2 * rx, 2 * rz)
    cell = side * 1.1 / GRID
    lo = np.array([-side * 0.55, -side * 0.55]) + (p2.min(0) + p2.max(0)) * 0.0
    shape = (GRID, GRID)
    tH = H[T]
    stands = rasterize(p2, T[tH.max(1) > 0.25], lo, cell, shape)
    tall = rasterize(p2, T[tH.max(1) > min(1.5, top * 0.4)], lo, cell, shape)
    c = lo[0] + (np.arange(GRID) + 0.5) * cell
    X, Y = np.meshgrid(c, lo[1] + (np.arange(GRID) + 0.5) * cell)
    inside = (np.abs(X) <= rx) & (np.abs(Y) <= rz)
    edge = inside & ~((np.abs(X) <= rx - 0.5) & (np.abs(Y) <= rz - 0.5))
    near = tall.copy()
    for _ in range(max(1, int(0.4 / cell))):               # what stands within 0.4 of the edge counts
        g = near.copy()
        g[1:, :] |= near[:-1, :]
        g[:-1, :] |= near[1:, :]
        g[:, 1:] |= near[:, :-1]
        g[:, :-1] |= near[:, 1:]
        near = g
    border = np.zeros(shape, bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    reached = flood(~tall, border)                         # the ground a unit reaches from outside
    court = ~tall & ~reached & inside
    parts = parts_of(stands)
    # flat levels: the area of faces looking up, by height
    a, b, cc = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(b - a, cc - a)
    area = np.linalg.norm(n, axis=1) / 2
    up = np.abs(n[:, ui]) / np.maximum(2 * area, 1e-9)
    flat = (up > 0.97) & (tH.min(1) > 0.5)
    levels = 0
    if flat.any():
        hist, _ = np.histogram(tH[flat].mean(1), bins=np.arange(0, top + 0.6, 0.5), weights=area[flat])
        levels = int((hist > 0.03 * max(1.0, float(inside.sum()) * cell * cell)).sum())
    mid = tH.mean(1)
    n_tris = max(1, len(T))
    return {"tris": len(T), "size": [round(float(np.ptp(p2[:, 0])), 2), round(float(np.ptp(p2[:, 1])), 2)],
            "height": round(top, 2), "slender": round(top / side, 3),
            "cover": round(float((stands & inside).sum() / max(1, inside.sum())), 3),
            "outside": round(float((stands & ~inside).sum() / max(1, stands.sum())), 3),
            "main": round(parts[0] / max(1, sum(parts)), 3) if parts else 0.0,
            "parts": len([q for q in parts if q * cell * cell > 0.05]),
            "rim": round(float((near & edge).sum() / max(1, edge.sum())), 3),
            "court": round(float(court.sum() / max(1, inside.sum())), 3), "levels": levels,
            "tris_low": round(float((mid < top / 3).sum() / n_tris), 3),
            "tris_mid": round(float(((mid >= top / 3) & (mid < 2 * top / 3)).sum() / n_tris), 3),
            "tris_high": round(float((mid >= 2 * top / 3).sum() / n_tris), 3),
            "uv_max": round(float(np.abs(UV).max()), 2), "textures": facts["textures"], "materials": facts["materials"],
            "faces_down": round(float(((n[:, ui] * np.sign(facts["up"][ui])) < 0).mean()), 3)}


def summary(shapes):
    """Quartiles per class (10 buildings or more) of the numbers the generators are held to."""
    out = {}
    rows = [s for s in shapes.values() if s["tris"] > 200]
    classes = sorted({s["class"] for s in rows})
    keys = ("height", "slender", "cover", "outside", "main", "parts", "rim", "levels", "tris_low", "tris_mid", "tris_high")
    for c in classes + ["all"]:
        v = [s for s in rows if c in (s["class"], "all")]
        if len(v) < 4:
            continue
        out[c] = {"count": len(v)}
        for k in keys:
            a = np.array([s[k] for s in v], float)
            out[c][k] = [round(float(np.percentile(a, q)), 3) for q in (25, 50, 75)]
    return out


def main(argv):
    if "--summary" in argv:                               # shapes.json into the profile
        with open(argv[argv.index("--summary") + 1], encoding="utf-8") as fh:
            shapes = json.load(fh)
        path = argv[argv.index("--profile") + 1]
        with open(path, encoding="utf-8") as fh:
            prof = json.load(fh)
        prof["shape"] = summary(shapes)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(prof, fh, indent=1)
        print("shape of", len(prof["shape"]), "classes written")
        return
    args = [a for a in argv if not a.startswith("--")]
    opt = lambda name, d=None: argv[argv.index(name) + 1] if name in argv else d   # noqa: E731
    out_path = opt("--out", "shapes.json")
    limit = int(opt("--limit", 100000))
    args = [a for a in args if a not in (out_path, str(limit))]
    with open(args[0], encoding="utf-8") as fh:
        rep = json.load(fh)
    raw = args[1]
    names = os.listdir(raw)
    index = {}
    for f in names:
        index.setdefault(f.rsplit("_", 1)[0], f)
    res, seen = {}, {}
    for b in rep["buildings"]:
        if len(res) >= limit:
            break
        m = b.get("model")
        rad = b.get("radius") or [0, 0]
        if not m or not rad[0] or not rad[1] or b.get("wall"):
            continue
        key = re.sub(r"[^A-Za-z0-9_.-]+", "_", m)[-150:]
        f = index.get(key)
        if not f:
            continue
        own = ".bar:" not in m
        if (key, tuple(rad)) in seen:
            continue
        seen[(key, tuple(rad))] = True
        try:
            V, UV, T, facts = load(os.path.join(raw, f))
            s = measure(V, UV, T, facts, rad[0], rad[1])
        except Exception as e:                             # a format this reader does not follow
            print(f"{b['name']}: skipped ({e!r})"[:100], flush=True)
            continue
        s.update({"name": b["name"], "radius": rad, "own": own, "class": f"{2 * rad[0]:g}x{2 * rad[1]:g}"})
        res[b["name"]] = s
        if len(res) % 25 == 0:
            print(len(res), "measured", flush=True)
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(res, fh)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh)
    print("done:", len(res), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
