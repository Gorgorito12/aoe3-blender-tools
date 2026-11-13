# SPDX-License-Identifier: GPL-3.0-or-later
"""Opens every texture of a game copy or a mod and measures it: what the art of the mod looks
like in numbers, so the painter and the texture maker aim at it instead of at a guess.

    venv\\Scripts\\python -I tools\\texture_survey.py <folder> [...] --out <report folder>
        [--reference <base game folder> ...] [--workers N] [--limit N]
        [--from <textures.json>] [--profile-out <profile.json>] [--sheets <folder>]

<folder>       a mod's folder (loose files and .bar archives, read in memory; nothing is extracted).
--reference    the original game's folder: a texture whose bytes are also there is tagged `stock`,
               one at the same path with other bytes `changed`, the rest `own`. The style to
               match is the mod's own; the stock art is the reference beside it.
--from         a report this tool wrote: skip the measuring, only write the profile or the sheets.
--models       tools/model_survey.py's report: a texture a model names is `worn`; a diffuse none
               names (an icon, a decal, a photograph kept beside the art) becomes `loose`.
--profile-out  the texture profile: measurements only, no file of the mod is named in it.
--sheets       contact sheets (a grid of sampled textures per group) for a person to look at.
               They are pictures of the mod's art: keep them out of any repository.

Writes <out>/textures.json: one record per texture, with its path. Like the art survey's report it
names the scanned mod's files, so it stays out of public repositories too.

Per texture, from mip level 1 (half size, as tools/palette_survey.py measures):

    mean, palette        its mean colour, and five dominant colours with their shares
    luminance, saturation   quartiles
    grain                the luminance minus its 9 x 9 blur, its spread over the mean: the fine
                         grain once the large shapes are taken away (core/materials.py aims at it)
    grain_fine, grain_broad   the same against a 3 x 3 and a 33 x 33 blur
    seam                 the step across the wrap over the mean step (core/texmaker.py): about 1
                         means it tiles, far more that it is an atlas
    a_part, a_zero       the share of pixels with alpha below 255 (player colour), and at 0
    light, gradient      the broad variation (the image at 4 x 4), and top over bottom brightness:
                         how much shading is painted in
    role, material       from the file's name: diffuse, bump, spec, ui, decal, terrain, effect
                         (and loose, with --models);
                         wood, stone, brick, roof, thatch, metal, cloth, plaster, earth...
"""
import collections
import hashlib
import json
import multiprocessing
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
from aoe3game import ddt  # noqa: E402

LUM = np.array([0.299, 0.587, 0.114], np.float32)
SEAM_OK = 1.5               # core/texmaker.py's: a join under this does not read as a line
MIN_GROUP = 8               # a group smaller than this says nothing and could point at a file
# the folders the original game has below art: the only category names a profile may carry
STOCK_CATEGORIES = ("units", "buildings", "buildingsets", "homecity", "terrain", "effects", "ui",
                    "nuggets", "objects", "animation_library", "shadows_selections", "cinematic",
                    "lightsets", "cursors", "impacts", "lighting")
ROLES = (("bump", ("_b", "_n", "_nm", "_bump", "_normal", "_norm", "normalmap", "_nrm")),
         ("spec", ("_s", "_spec", "_specular", "_sp")),
         ("decal", ("decal", "ground", "selection", "shadow", "_dcl")),
         ("ui", ("icon", "portrait", "_ui", "button", "cursor")))
MATERIALS = (("wood", ("wood", "plank", "timber", "log", "bark", "lumber", "board")),
             ("stone", ("stone", "rock", "cobble", "masonry", "granite", "marble", "boulder")),
             ("brick", ("brick",)),
             ("roof", ("roof", "shingle", "slate", "rooftile", "tiles")),
             ("thatch", ("thatch", "straw", "hay", "reed")),
             ("metal", ("metal", "iron", "steel", "bronze", "copper", "rust", "tin")),
             ("cloth", ("cloth", "fabric", "canvas", "tent", "sail", "flag", "banner", "carpet", "rug")),
             ("plaster", ("plaster", "stucco", "whitewash", "adobe")),
             ("earth", ("mud", "dirt", "earth", "clay", "sand", "soil", "gravel")),
             ("plant", ("grass", "leaf", "leaves", "foliage", "bush", "palm", "tree", "bamboo")),
             ("snow", ("snow", "ice")),
             ("water", ("water", "wave", "foam")))


# --------------------------------------------------------------------------------------------------
# Where the textures are

def norm(path):
    """A comparable art path: lowercase, backslashes, from the folder below art."""
    p = path.replace("/", "\\").lower()
    p = p.split(":", 1)[1] if ".bar:" in p else p
    p = p.lstrip(".\\")
    i = p.find("art\\")
    return p[i + 4:] if i >= 0 else p


def category(path):
    """The original game's folder a texture sits in, however deep a mod put it; else "other"."""
    parts = norm(path).split("\\")[:-1]
    for part in parts[:6]:
        if part in STOCK_CATEGORIES:
            return part
    return "other"


def locate(folders, use_bar=True, ext=".ddt"):
    """(display path, container, offset, size) of every file ending in `ext` below the folders,
    loose or in an archive. Nothing is read but the archives' tables."""
    for folder in folders:
        for base, _dirs, names in os.walk(folder):
            for n in names:
                full = os.path.join(base, n)
                low = n.lower()
                if low.endswith(ext):
                    yield os.path.relpath(full, folder), full, 0, os.path.getsize(full)
                elif use_bar and low.endswith(".bar"):
                    try:
                        entries = bar.read_entries(full)
                    except (OSError, ValueError):
                        continue
                    rel = os.path.relpath(full, folder)
                    for stored, offset, size in entries:
                        if stored.lower().endswith(ext):
                            yield f"{rel}:{stored}", full, offset, size


def _read(container, offset, size):
    with open(container, "rb") as fh:
        fh.seek(offset)
        return fh.read(size)


# --------------------------------------------------------------------------------------------------
# What a texture is, from its name

def role_of(path, cat="", mean=None):
    """diffuse, bump, spec, decal, ui, terrain or effect. The name decides; a texture that is
    the blue of a normal map is a bump map whatever it is called."""
    stem = os.path.splitext(os.path.basename(norm(path)))[0]
    for role, marks in ROLES:
        for m in marks:
            if stem.endswith(m) if m.startswith("_") else m in stem:
                return role
    if mean is not None and mean[2] > 170 and mean[2] - mean[1] > 50:
        return "bump"            # the blue (or the pink) of a normal map, whichever way it is packed
    if cat in ("ui", "cursors"):
        return "ui"
    if cat in ("terrain", "effects"):
        return cat.rstrip("s")
    return "diffuse"


def material_of(path):
    """The material a texture's name says it is, or "" (an atlas of a unit or a building does not
    say)."""
    words = re.split(r"[^a-z]+", norm(path).rsplit("\\", 1)[-1])
    for material, marks in MATERIALS:
        if any(w.startswith(m) for w in words for m in marks):
            return material
    return ""


# --------------------------------------------------------------------------------------------------
# The measures (arrays in, numbers out)

def box_blur(a, r):
    """Mean over a (2r+1) square, edges wrapped: the roll-and-add of tools/palette_survey.py from
    a summed table, so a wide blur costs what a narrow one does."""
    h, w = a.shape
    r = max(1, min(r, (min(h, w) - 1) // 2)) if min(h, w) > 2 else 0
    if r == 0:
        return a.astype(np.float32)
    p = np.pad(a.astype(np.float64), r, mode="wrap")
    c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    n = 2 * r + 1
    s = c[n:n + h, n:n + w] - c[:h, n:n + w] - c[n:n + h, :w] + c[:h, :w]
    return (s / (n * n)).astype(np.float32)


def grain(lum, opaque, r=4):
    """The spread of the luminance minus its blur over the mean: tools/palette_survey.py's
    local contrast at r = 4."""
    fine = lum - box_blur(lum, r)
    mean = float(lum[opaque].mean())
    return float(fine[opaque].std()) / max(mean, 1.0)


def seam(rgb):
    """core/texmaker.py's: the step across the wrap over the mean step between neighbours."""
    a = rgb.astype(np.float32)
    if min(a.shape[:2]) < 2:
        return 0.0
    inner = (np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean()) / 2
    across = (np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean()) / 2
    return float(across / max(inner, 1e-6))


def palette(px, k=5, seed=0, iters=8):
    """[[r, g, b, share]] of k dominant colours, the largest first. Seeded and deterministic."""
    px = px.reshape(-1, 3).astype(np.float32)
    if len(px) > 4096:
        px = px[np.random.default_rng(seed).choice(len(px), 4096, replace=False)]
    if len(px) == 0:
        return []
    k = min(k, len(px))
    order = np.argsort(px @ LUM, kind="stable")
    c = px[order[((np.arange(k) + 0.5) * len(px) / k).astype(int)]].copy()
    lab = np.zeros(len(px), int)
    for _ in range(iters):
        lab = ((px[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (lab == j).any():
                c[j] = px[lab == j].mean(0)
    share = np.bincount(lab, minlength=k) / len(px)
    rows = [[round(float(v), 1) for v in c[j]] + [round(float(share[j]), 3)]
            for j in np.argsort(-share, kind="stable") if share[j] > 0]
    return rows


def _q(values):
    v = np.percentile(np.asarray(values, np.float64), (25, 50, 75))
    return [round(float(x), 4) for x in v]


def measure(rgba, seed=0):
    """The numbers of one decoded texture (H x W x 4 uint8). See the module's list."""
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3]
    lum = rgb @ LUM
    opaque = alpha > 250
    if opaque.sum() < 64:
        opaque = np.ones_like(opaque)
    px = rgb[opaque]
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    h, w = lum.shape
    bh, bw = max(1, h // 4), max(1, w // 4)
    coarse = lum[:bh * 4, :bw * 4].reshape(4, bh, 4, bw).mean((1, 3)) if min(h, w) >= 4 else lum
    third = max(1, h // 3)
    top, bottom = float(lum[:third].mean()), float(lum[-third:].mean())
    return {
        "mean": [round(float(c), 1) for c in px.mean(0)],
        "luminance": _q(px @ LUM),
        "saturation": _q(sat),
        "palette": palette(px, seed=seed),
        "grain": round(grain(lum, opaque, 4), 4),
        "grain_fine": round(grain(lum, opaque, 1), 4),
        "grain_broad": round(grain(lum, opaque, 16), 4),
        "seam": round(seam(rgb), 2),
        "a_part": round(float((alpha < 255).mean()), 4),
        "a_zero": round(float((alpha == 0).mean()), 4),
        "light": round(float(np.ptp(coarse)) / max(float(lum.mean()), 1.0), 4),
        "gradient": round(top / max(bottom, 1.0), 3),
    }


def measure_one(task):
    """A worker: one texture read, decoded at mip 1 and measured. Never raises."""
    path, container, offset, size = task
    rec = {"path": path, "at": [container, offset, size]}
    try:
        data = _read(container, offset, size)
        rec["md5"] = hashlib.md5(data).hexdigest()
        hd = ddt.read_header(data)
        rec.update(w=hd.width, h=hd.height, format=hd.format, alpha=hd.alpha, mips=hd.mips,
                   bytes=size)
        rgba = ddt.decode(data, 1 if len(hd.levels) > 1 and min(hd.width, hd.height) >= 8 else 0)
        rec.update(measure(rgba, seed=int(rec["md5"][:8], 16)))
    except Exception as exc:                       # a file this reader cannot open: say which
        rec["error"] = f"{type(exc).__name__}: {exc}"[:160]
    return rec


def hash_one(task):
    path, container, offset, size = task
    try:
        return norm(path), hashlib.md5(_read(container, offset, size)).hexdigest()
    except OSError:
        return norm(path), None


# --------------------------------------------------------------------------------------------------
# The survey

def _pool_map(fn, tasks, workers, what):
    out, t0 = [], time.time()
    if workers <= 1:
        for i, t in enumerate(tasks):
            out.append(fn(t))
        return out
    with multiprocessing.Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(fn, tasks, chunksize=32), 1):
            out.append(r)
            if i % 2000 == 0:
                rate = i / max(time.time() - t0, 1e-6)
                print(f"  {what}: {i} of {len(tasks)} ({rate:.0f} a second)", flush=True)
    return out


def tag(records, reference):
    """Sets `origin` on each record: stock (the same bytes are in the reference), changed (the
    same path, other bytes) or own. Without a reference everything is "unknown"."""
    if reference is None:
        for r in records:
            r["origin"] = "unknown"
        return records
    by_path, hashes = reference
    for r in records:
        if r.get("md5") in hashes:
            r["origin"] = "stock"
        elif norm(r["path"]) in by_path:
            r["origin"] = "changed"
        else:
            r["origin"] = "own"
    return records


def survey(folders, reference=(), workers=1, limit=None):
    tasks = list(locate(folders))
    if limit:
        tasks = tasks[:: max(1, len(tasks) // limit)][:limit]
    print(f"{len(tasks)} textures to measure", flush=True)
    records = _pool_map(measure_one, tasks, workers, "measured")
    ref = None
    if reference:
        rtasks = list(locate(reference))
        print(f"{len(rtasks)} reference textures to hash", flush=True)
        pairs = _pool_map(hash_one, rtasks, workers, "hashed")
        ref = ({p for p, _ in pairs}, {h for _, h in pairs if h})
    tag(records, ref)
    name(records)
    records.sort(key=lambda r: r["path"].lower())
    return records


def name(records):
    """Sets category, role and material on each record, from its path and its mean colour."""
    for r in records:
        if "error" in r:
            continue
        r["category"] = category(r["path"])
        r["role"] = role_of(r["path"], r["category"], r.get("mean"))
        r["material"] = material_of(r["path"])
    return records


def mark_use(records, models):
    """Tells the textures a model wears from the rest. A texture's name says little - icons,
    ground decals and photographs sit in the same folders under any name - but a model names
    every texture it uses. A `diffuse` no model names becomes `loose`. models: the records of
    tools/model_survey.py. Returns how many textures are worn."""
    worn = set()
    for m in models:
        if m.get("tris"):
            worn.update(os.path.splitext(t)[0] for t in m.get("textures", ()))
    n = 0
    for r in records:
        if "error" in r:
            continue
        stem = os.path.splitext(os.path.basename(norm(r["path"]).replace("\\", "/")))[0]
        r["worn"] = stem in worn
        n += r["worn"]
        if r["role"] == "diffuse" and not r["worn"]:
            r["role"] = "loose"
    return n


# --------------------------------------------------------------------------------------------------
# The profile: measurements only

def _group_stats(rows):
    def col(name):
        return [r[name] for r in rows]

    sizes = collections.Counter(f"{r['w']}x{r['h']}" for r in rows).most_common(6)
    formats = collections.Counter(ddt.FORMATS.get(r["format"], str(r["format"])) for r in rows)
    centres = np.array([c[:3] for r in rows for c in r["palette"][:3]], np.float32)
    weights = np.array([c[3] for r in rows for c in r["palette"][:3]], np.float32)
    pal = []
    if len(centres):
        rep = np.repeat(centres, np.maximum(1, (weights * 20).astype(int)), axis=0)
        pal = palette(rep, k=6, seed=len(rows))
    return {
        "count": len(rows),
        "sizes": [[s, n] for s, n in sizes],
        "formats": dict(formats.most_common()),
        "mean_rgb": [round(float(v), 1) for v in np.median(np.array(col("mean")), axis=0)],
        "palette": pal,
        "luminance": _q([r["luminance"][1] for r in rows]),
        "saturation": _q([r["saturation"][1] for r in rows]),
        "grain": _q(col("grain")),
        "grain_fine": _q(col("grain_fine")),
        "grain_broad": _q(col("grain_broad")),
        "light": _q(col("light")),
        "gradient": _q(col("gradient")),
        "tileable": round(sum(1 for r in rows if r["seam"] <= SEAM_OK and min(r["w"], r["h"]) >= 64) / len(rows), 3),
        "player_colour": round(sum(1 for r in rows if r["alpha"] == 1 and r["a_part"] > 0.002) / len(rows), 3),
        "cutout": round(sum(1 for r in rows if r["a_zero"] > 0.02) / len(rows), 3),
    }


def profile(records, label="target mod"):
    """The texture profile: per origin, category, role and material, what the textures measure.
    Each distinct texture counts once (a mod keeps copies). No path, no file name: a group of
    fewer than MIN_GROUP textures is left out, so a number never points at one file."""
    good, seen = [], set()
    errors = collections.Counter()
    for r in records:
        if "error" in r:
            errors[r["error"].split(":")[0] + (": " + r["error"].split(":", 1)[1].strip()
                                               if "format" in r["error"] else "")] += 1
            continue
        if r["md5"] in seen:
            continue
        seen.add(r["md5"])
        good.append(r)
    groups = collections.defaultdict(list)
    for r in good:
        o, c, ro, m = r["origin"], r["category"], r["role"], r["material"]
        for key in ((o, c, ro, m), (o, c, ro, "*"), (o, "*", ro, m), (o, "*", ro, "*")):
            if key[3] == "" and key != (o, c, ro, m):
                continue
            groups[key].append(r)
    out = []
    for (o, c, ro, m), rows in sorted(groups.items()):
        if len(rows) < MIN_GROUP:
            continue
        out.append({"origin": o, "category": c, "role": ro, "material": m, **_group_stats(rows)})
    return {"schema": 1, "source": label, "textures": len(records), "distinct": len(good),
            "unread": dict(errors.most_common()), "seam_ok": SEAM_OK,
            "measured": "mip level 1; grain = spread of luminance minus its 9x9 blur over the mean",
            "groups": out}


# --------------------------------------------------------------------------------------------------
# Contact sheets: to look at, never to commit

def _thumb(rgba, cell):
    a = rgba[:, :, :3].astype(np.float32)
    h, w = a.shape[:2]
    ys = (np.arange(cell) * h / cell).astype(int)
    xs = (np.arange(cell) * w / cell).astype(int)
    if h >= 2 * cell and w >= 2 * cell:                       # shrink by averaging blocks
        fy, fx = h // cell, w // cell
        a = a[:fy * cell, :fx * cell].reshape(cell, fy, cell, fx, 3).mean((1, 3))
        return a.astype(np.uint8)
    return a[ys][:, xs].astype(np.uint8)


def sheets(records, folder, cell=128, cols=8, rows=6, seed=7, groups=None):
    """Writes one PNG grid per (origin, category, role, material) of at least MIN_GROUP distinct
    textures, sampled, with a .txt beside it listing each cell's numbers. Returns the paths."""
    from core.pngio import encode_png
    os.makedirs(folder, exist_ok=True)
    pick, seen = collections.defaultdict(list), set()
    for r in records:
        if "error" in r or r["md5"] in seen:
            continue
        seen.add(r["md5"])
        key = (r["origin"], r["category"], r["role"], r["material"] or "atlas")
        pick[key].append(r)
    written = []
    rng = np.random.default_rng(seed)
    for key, rws in sorted(pick.items()):
        if len(rws) < MIN_GROUP or (groups and key not in groups):
            continue
        rws = [r for r in rws if min(r["w"], r["h"]) >= 64] or rws
        chosen = [rws[i] for i in sorted(rng.choice(len(rws), min(len(rws), cols * rows), replace=False))]
        sheet = np.full((rows * cell, cols * cell, 3), 60, np.uint8)
        lines = []
        for i, r in enumerate(chosen):
            try:
                data = _read(*r["at"])
                hd = ddt.read_header(data)
                level = 0
                while level + 1 < len(hd.levels) and max(hd.width, hd.height) >> (level + 1) >= 2 * cell:
                    level += 1
                t = _thumb(ddt.decode(data, level), cell)
            except Exception:
                continue
            y, x = divmod(i, cols)
            sheet[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell] = t
            lines.append(f"row {y + 1} col {x + 1}: {r['w']}x{r['h']} grain {r['grain']} seam {r['seam']} "
                         f"sat {r['saturation'][1]} lum {r['luminance'][1]:.0f}  {r['path']}")
        name = "_".join(key).replace("*", "all")
        path = os.path.join(folder, name + ".png")
        with open(path, "wb") as fh:
            fh.write(encode_png(sheet))
        with open(path[:-4] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(f"{key}: {len(rws)} distinct textures, {len(chosen)} shown\n" + "\n".join(lines) + "\n")
        written.append(path)
    return written


# --------------------------------------------------------------------------------------------------

def summary(prof, top=40):
    lines = [f"{prof['textures']} textures, {prof['distinct']} distinct; unread: {prof['unread'] or 'none'}", "",
             f"{'origin':8} {'category':18} {'role':8} {'material':8} {'n':>6}  {'grain q25/50/75':24} "
             f"{'sat':6} {'lum':5} {'tile':5} {'pc':5}"]
    rows = sorted(prof["groups"], key=lambda g: -g["count"])[:top]
    for g in rows:
        lines.append(f"{g['origin']:8} {g['category']:18} {g['role']:8} {g['material']:8} {g['count']:6}  "
                     f"{'/'.join(f'{v:.3f}' for v in g['grain']):24} {g['saturation'][1]:<6.3f} "
                     f"{g['luminance'][1]:<5.0f} {g['tileable']:<5.2f} {g['player_colour']:<5.2f}")
    return "\n".join(lines)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    flags = ("--out", "--workers", "--limit", "--from", "--profile-out", "--sheets", "--models")
    folders, reference = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            i += 2
            continue
        if a == "--reference":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                reference.append(argv[i])
                i += 1
            continue
        if not a.startswith("--"):
            folders.append(a)
        i += 1
    out = opt("--out")
    if opt("--from"):
        with open(opt("--from"), encoding="utf-8") as fh:
            records = name(json.load(fh)["textures"])       # named again: the rules may be newer
    else:
        if not folders or not out:
            print(__doc__)
            return 2
        t0 = time.time()
        workers = int(opt("--workers", max(1, (os.cpu_count() or 2) - 2)))
        records = survey(folders, reference, workers, int(opt("--limit")) if opt("--limit") else None)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "textures.json"), "w", encoding="utf-8") as fh:
            json.dump({"folders": folders, "reference": reference, "textures": records}, fh)
        print(f"measured in {time.time() - t0:.0f} s -> {os.path.join(out, 'textures.json')}")
    if opt("--models"):
        with open(opt("--models"), encoding="utf-8") as fh:
            worn = mark_use(records, json.load(fh)["models"])
        print(f"{worn} textures are worn by a model; a diffuse that is not becomes `loose`")
    prof = profile(records)
    print(summary(prof))
    if opt("--profile-out"):
        with open(opt("--profile-out"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(prof, fh, indent=1)
            fh.write("\n")
        print("profile ->", opt("--profile-out"))
    if opt("--sheets"):
        written = sheets(records, opt("--sheets"))
        print(f"{len(written)} sheets -> {opt('--sheets')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
