# SPDX-License-Identifier: GPL-3.0-or-later
"""Opens every Granny file of a game copy or a mod - models and animations, of units, props,
treasures and buildings alike - and measures it. tools/art_survey.py does this for the buildings;
this is the same look at everything else, which nobody had measured.

    venv\\Scripts\\python -I tools\\model_survey.py <folder> [...] --out <report folder>
        --granny <bridge.exe> --cache <folder> [--granny-install <dir>]
        [--reference <base game folder> ...] [--workers N] [--limit N] [--only units]
        [--from <models.json>] [--textures <textures.json>] [--profile-out <folder>]

Almost every model stores compressed sections. `--granny` is an external bridge (`<exe> rebake
--install <dir> --file <in> --out <out> --noop` writes a file uncompressed); the uncompressed
copies go to --cache, outside the game folder, named by their content so a file kept in several
places is written once and a second run only reads. The game's own Granny runtime is never
shipped with this tool.

Writes <out>/models.json: one record per file, with its path - like every survey report it names
the scanned mod's files and stays out of public repositories. `--profile-out` writes the profiles
(props.json, units.json): measurements only.

Per file:

    kind                  model, animation, or both
    tris, verts, meshes   and the vertex layouts (a layout with bone weights is a skinned mesh)
    bones, bone_depth     how many, and how deep the hierarchy goes
    bindings              how many bones the meshes are bound to
    size                  width, depth, height, in the file's own units and declared units/metre
    materials, effects, textures
    uv_max, texel         how far the UVs run, and UV length per model unit (with a texture's
                          size: its pixels per unit)
    animations            name, duration, tracks, and how a loop is written
"""
import collections
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import shape_survey  # noqa: E402
import texture_survey as ts  # noqa: E402
from aoe3game import gr2  # noqa: E402

MIN_GROUP = ts.MIN_GROUP
SKIN_FIELDS = ("BoneWeights", "BoneIndices")


# --------------------------------------------------------------------------------------------------
# Uncompressed bytes, through the cache

def raw_bytes(data, md5, bridge):
    """The file with every section uncompressed: itself when it already is, else the cached copy,
    else what the bridge writes into the cache. bridge: (exe, install, cache) or None."""
    if gr2.header_facts(data).get("raw"):
        return data
    if bridge is None:
        raise RuntimeError("compressed, and no bridge was given")
    exe, install, cache = bridge
    out = os.path.join(cache, "raw", md5 + ".gr2")
    if not os.path.exists(out):
        src = os.path.join(cache, "src", md5 + ".gr2")
        with open(src, "wb") as fh:
            fh.write(data)
        tmp = out + f".{os.getpid()}.tmp"
        try:
            r = subprocess.run([exe, "rebake", "--install", install, "--file", src, "--out", tmp,
                                "--noop"], cwd=cache, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"bridge failed: {type(exc).__name__}") from exc
        finally:
            if os.path.exists(src):
                os.remove(src)
        if r.returncode != 0 or not os.path.exists(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError(f"bridge exit {r.returncode}")
        os.replace(tmp, out)
    with open(out, "rb") as fh:
        return fh.read()


# --------------------------------------------------------------------------------------------------
# The measures

def _depth(parents):
    best = 0
    for i in range(len(parents)):
        d, j = 0, i
        while 0 <= parents[j] < len(parents) and d < 256:
            j = parents[j]
            d += 1
        best = max(best, d)
    return best


def _geometry(root):
    """(uv_max, texel, area) over the meshes with plain positions: how far the UVs run, the UV
    length per unit of surface length (sqrt of the areas' ratio), and the surface area."""
    uv_hi, a_uv, a_3d = 0.0, 0.0, 0.0
    for m in root.get("Meshes") or []:
        if m is None:
            continue
        vd, tt = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        if vd is None or tt is None:
            continue
        vs = vd.get("Vertices")
        pos = shape_survey.column(vs, "Position")
        uv = shape_survey.column(vs, "TextureCoordinates0")
        if pos is None or uv is None or len(pos) == 0:
            continue
        i32, i16 = tt.get("Indices"), tt.get("Indices16")
        src = i32 if (len(i32) if isinstance(i32, list) else getattr(i32, "count", 0)) else i16
        try:
            idx = shape_survey.indices(src).reshape(-1, 3)
        except (ValueError, AttributeError):
            continue
        idx = idx[(idx < len(pos)).all(1)]
        if len(idx) == 0:
            continue
        p, t = pos[idx][:, :, :3], uv[idx][:, :, :2]
        a_3d += float(np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum() / 2)
        e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        a_uv += float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2)
        uv_hi = max(uv_hi, float(np.abs(uv[:, :2]).max()))
    texel = (a_uv / a_3d) ** 0.5 if a_3d > 1e-9 and a_uv > 0 else 0.0
    return round(uv_hi, 3), round(texel, 5), round(a_3d, 3)


def _animations(root):
    out = []
    for an in root.get("Animations") or []:
        if an is None:
            continue
        groups = [g for g in (an.get("TrackGroups") or []) if g is not None]
        tracks = sum(len(g.get("TransformTracks") or []) for g in groups)
        flags = sorted({int(g.get("AccumulationFlags") or 0) for g in groups})
        loop = any(any(abs(v) > 1e-6 for v in (g.get("LoopTranslation") or (0, 0, 0))) for g in groups)
        periodic = any(g.get("PeriodicLoop") is not None for g in groups)
        out.append({"name": an.get("Name"), "duration": round(float(an.get("Duration") or 0), 4),
                    "timestep": round(float(an.get("TimeStep") or 0), 5), "groups": len(groups),
                    "tracks": tracks, "flags": flags, "loop_translation": loop, "periodic": periodic})
    return out


def measure(data):
    """The facts of one uncompressed Granny file."""
    doc = gr2.load(data)
    st, root = doc.stats(), doc.root()
    parents = [b["parent"] for b in st["bones"]]
    layouts = sorted(set(st["vertex_layouts"]))
    bind = [len(m.get("BoneBindings") or []) for m in root.get("Meshes") or [] if m is not None]
    anims = _animations(root)
    rec = {"tris": st["tris"], "verts": st["verts"], "meshes": len(st["meshes"]),
           "layouts": layouts, "skinned": any(f in lay for lay in layouts for f in SKIN_FIELDS),
           "index_bits": st["index_bits"], "bones": len(parents), "bone_depth": _depth(parents),
           "bone_names": [b["name"] for b in st["bones"]][:80],
           "bindings": sum(bind), "bindings_max": max(bind) if bind else 0,
           "materials": len(st["materials"]),
           "effects": sorted({m["effect"] for m in st["materials"] if m["effect"]}),
           "textures": sorted({os.path.basename(str(t).replace("\\", "/")).lower()
                               for t in st["textures"] if t}),
           "upm": (st.get("art_tool") or {}).get("units_per_meter"),
           "up": (st.get("art_tool") or {}).get("up"),
           "animations": anims}
    if "bbox" in st:
        lo, hi = st["bbox"]
        up = max(range(3), key=lambda i: abs((rec["up"] or (0, 1, 0))[i]))
        h = [i for i in range(3) if i != up]
        rec["size"] = [round(hi[h[0]] - lo[h[0]], 3), round(hi[h[1]] - lo[h[1]], 3), round(hi[up] - lo[up], 3)]
    if st["tris"]:
        rec["uv_max"], rec["texel"], rec["area"] = _geometry(root)
    rec["kind"] = ("model+animation" if st["tris"] and anims else "model" if st["tris"]
                   else "animation" if anims else "other")
    return rec


def measure_one(task):
    """A worker: one file read, uncompressed through the cache and measured. Never raises."""
    path, container, offset, size, bridge = task
    rec = {"path": path, "at": [container, offset, size], "bytes": size}
    try:
        data = ts._read(container, offset, size)
        rec["md5"] = hashlib.md5(data).hexdigest()
        rec["compressed"] = not gr2.header_facts(data).get("raw")
        rec.update(measure(raw_bytes(data, rec["md5"], bridge)))
    except Exception as exc:                       # a file this reader cannot open: say which
        rec["error"] = f"{type(exc).__name__}: {exc}"[:160]
    return rec


# --------------------------------------------------------------------------------------------------

def survey(folders, bridge=None, reference=(), workers=1, limit=None, only=None):
    tasks = [t for t in ts.locate(folders, ext=".gr2")]
    if only:
        tasks = [t for t in tasks if ts.category(t[0]) == only]
    if limit:
        tasks = tasks[:: max(1, len(tasks) // limit)][:limit]
    print(f"{len(tasks)} Granny files to measure", flush=True)
    records = ts._pool_map(measure_one, [t + (bridge,) for t in tasks], workers, "measured")
    ref = None
    if reference:
        rtasks = list(ts.locate(reference, ext=".gr2"))
        print(f"{len(rtasks)} reference files to hash", flush=True)
        pairs = ts._pool_map(ts.hash_one, rtasks, workers, "hashed")
        ref = ({p for p, _ in pairs}, {h for _, h in pairs if h})
    ts.tag(records, ref)
    for r in records:
        r["category"] = ts.category(r["path"])
    records.sort(key=lambda r: r["path"].lower())
    return records


# --------------------------------------------------------------------------------------------------
# Profiles: measurements only

def _q(values):
    v = np.percentile(np.asarray(values, np.float64), (25, 50, 75))
    return [round(float(x), 4) for x in v]


def _top(counter, n=8):
    return [[k, v] for k, v in counter.most_common(n)]


def _texture_px(rows, tex_by_name):
    """Pixels per model unit of each model that names a texture the texture survey measured."""
    out = []
    for r in rows:
        if not r.get("texel"):
            continue
        sides = [tex_by_name[t] for t in r["textures"] if t in tex_by_name]
        if sides:
            out.append(r["texel"] * max(sides))
    return out


def group_stats(rows, tex_by_name=None):
    models = [r for r in rows if r["kind"].startswith("model")]
    g = {"count": len(rows), "models": len(models)}
    if models:
        g.update(
            tris=_q([r["tris"] for r in models]), verts=_q([r["verts"] for r in models]),
            meshes=_q([r["meshes"] for r in models]), bones=_q([r["bones"] for r in models]),
            bone_depth=_q([r["bone_depth"] for r in models]),
            materials=_q([r["materials"] for r in models]),
            skinned=round(sum(1 for r in models if r["skinned"]) / len(models), 3),
            bound_to_many=round(sum(1 for r in models if r["bindings_max"] > 1) / len(models), 3),
            index_32=round(sum(1 for r in models if 32 in r["index_bits"]) / len(models), 3),
            uv_repeats=round(sum(1 for r in models if r.get("uv_max", 0) > 1.05) / len(models), 3),
            layouts=_top(collections.Counter(lay for r in models for lay in r["layouts"])),
            effects=_top(collections.Counter(e for r in models for e in r["effects"])))
        sized = [r["size"] for r in models if r.get("size") and r.get("upm") and 0.3 < r["upm"] < 1.0]
        if len(sized) >= MIN_GROUP:
            g["size"] = {"width": _q([max(s[0], s[1]) for s in sized]),
                         "height": _q([s[2] for s in sized])}
        if tex_by_name:
            px = _texture_px(models, tex_by_name)
            if len(px) >= MIN_GROUP:
                g["pixels_per_unit"] = _q(px)
    anims = [a for r in rows for a in r["animations"]]
    if anims:
        g["animations"] = {
            "count": len(anims), "duration": _q([a["duration"] for a in anims]),
            "tracks": _q([a["tracks"] for a in anims]),
            "timestep": _top(collections.Counter(round(1 / a["timestep"]) if a["timestep"] else 0
                                                 for a in anims), 4),
            "flags": _top(collections.Counter(str(a["flags"]) for a in anims), 6),
            "loop_translation": round(sum(1 for a in anims if a["loop_translation"]) / len(anims), 3),
            "periodic": round(sum(1 for a in anims if a["periodic"]) / len(anims), 3)}
    return g


def profile(records, textures=None, label="target mod"):
    """Per origin and category (the original game's folder names only), what the Granny files
    measure. Each distinct file counts once; a group under MIN_GROUP files is left out."""
    tex_by_name = None
    if textures:
        tex_by_name = {}
        for t in textures:
            if "error" not in t:
                name = os.path.basename(ts.norm(t["path"]).replace("\\", "/"))
                tex_by_name[name] = max(tex_by_name.get(name, 0), t["w"])
    good, seen, errors = [], set(), collections.Counter()
    for r in records:
        if "error" in r:
            errors[r["error"].split(":")[0]] += 1
            continue
        if r["md5"] in seen:
            continue
        seen.add(r["md5"])
        good.append(r)
    groups = collections.defaultdict(list)
    for r in good:
        for key in ((r["origin"], r["category"]), (r["origin"], "*")):
            groups[key].append(r)
    out = [{"origin": o, "category": c, **group_stats(rows, tex_by_name)}
           for (o, c), rows in sorted(groups.items()) if len(rows) >= MIN_GROUP]
    return {"schema": 1, "source": label, "files": len(records), "distinct": len(good),
            "unread": dict(errors.most_common()), "groups": out}


def summary(prof):
    lines = [f"{prof['files']} files, {prof['distinct']} distinct; unread: {prof['unread'] or 'none'}", "",
             f"{'origin':8} {'category':18} {'n':>6} {'models':>6}  {'tris q25/50/75':22} {'bones':6} "
             f"{'skin':5} {'anims':>6}"]
    for g in sorted(prof["groups"], key=lambda g: -g["count"]):
        tris = "/".join(f"{v:.0f}" for v in g["tris"]) if "tris" in g else "-"
        lines.append(f"{g['origin']:8} {g['category']:18} {g['count']:6} {g['models']:6}  {tris:22} "
                     f"{g.get('bones', [0, 0, 0])[1]:<6.0f} {g.get('skinned', 0):<5.2f} "
                     f"{g.get('animations', {}).get('count', 0):6}")
    return "\n".join(lines)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    flags = ("--out", "--workers", "--limit", "--from", "--profile-out", "--granny", "--cache",
             "--granny-install", "--only", "--textures")
    folders, reference, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            i += 2
        elif a == "--reference":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                reference.append(argv[i])
                i += 1
        else:
            if not a.startswith("--"):
                folders.append(a)
            i += 1
    out = opt("--out")
    if opt("--from"):
        with open(opt("--from"), encoding="utf-8") as fh:
            records = json.load(fh)["models"]
    else:
        if not folders or not out:
            print(__doc__)
            return 2
        bridge = None
        if opt("--granny"):
            cache = os.path.abspath(opt("--cache"))
            install = os.path.abspath(opt("--granny-install") or folders[0])
            if os.path.commonpath([cache, install]) == install:
                raise SystemExit("the cache must be outside the game folder")
            for sub in ("src", "raw"):
                os.makedirs(os.path.join(cache, sub), exist_ok=True)
            bridge = (opt("--granny"), install, cache)
        t0 = time.time()
        workers = int(opt("--workers", max(1, (os.cpu_count() or 2) - 2)))
        records = survey(folders, bridge, reference, workers,
                         int(opt("--limit")) if opt("--limit") else None, opt("--only"))
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "models.json"), "w", encoding="utf-8") as fh:
            json.dump({"folders": folders, "reference": reference, "models": records}, fh)
        print(f"measured in {time.time() - t0:.0f} s -> {os.path.join(out, 'models.json')}")
    textures = None
    if opt("--textures"):
        with open(opt("--textures"), encoding="utf-8") as fh:
            textures = json.load(fh)["textures"]
    prof = profile(records, textures)
    print(summary(prof))
    if opt("--profile-out"):
        with open(opt("--profile-out"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(prof, fh, indent=1)
            fh.write("\n")
        print("profile ->", opt("--profile-out"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
