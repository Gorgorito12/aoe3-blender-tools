# SPDX-License-Identifier: GPL-3.0-or-later
"""Survey the art of an Age of Empires III install or mod: what models, textures and anim files it
has, how they reference each other, and the conventions they follow. Read-only; standard library.

    python -I tools/art_survey.py <folder> [<folder> ...] --out <report folder> [--bar] [--label NAME]
                                 [--reference <report.json>] [--proto <protoy.xml>]
                                 [--granny <bridge.exe> --cache <folder> [--granny-install <dir>]]
                                 [--profile-out <profile.json>]

<folder>     a mod folder or the game folder; loose files are read below it.
--bar        also read the .bar archives below the folders, in memory (nothing is extracted).
--reference  another survey's report.json (e.g. of the base game): references found there are
             marked as reused from it, and the report says which of this mod's files are new.
--label      a name for the report (default: the first folder's name).
--proto      the game's unit list: each building (a unit with UnitType Building) is joined to its
             anim file, its models, decal, construction stages and obstruction.
--granny     an external Granny bridge (`<exe> rebake --install <dir> --file <in> --out <out>
             --noop` writes a model uncompressed); with it, the buildings' compressed models are
             written to --cache (outside the game folder) and measured. Uncompressed models are
             measured without it. The game's own Granny runtime is never shipped with this tool.
--profile-out  writes the building profile: measurements only (no file of the mod is named).

Writes <out>/report.json (everything) and <out>/summary.md (the tables). The report holds
measurements and file paths only, never file contents; it still names the scanned mod's files,
so keep it out of public repositories.

What it reads:
- anim files (.xml, or compiled .xml.xmb, below an "art" folder): element and attribute names,
  every referenced file (any element with a <file> child, and any text ending in a known
  extension), attach point and bone names, logic types, anim names;
- .ddt textures: the header (fields to verify: "RTS3", usage, alpha, format, mip levels, width,
  height);
- .gr2 models: the container header (version, sections, compression); triangle and vertex
  counts, vertex layout, size, basis, bones, textures and shader effects of the buildings' models
  when they are uncompressed or the bridge is given.

References in anim files are matched without their extension (the game writes model and texture
paths without one) and a compiled `x.xml.xmb` stands for `x.xml`. A category is the folder below
`art`, or below a mod's own folder there (`art\\<Mod>\\buildings` counts as buildings).
"""
import collections
import json
import os
import re
import statistics
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import xmbedit  # noqa: E402
from aoe3game import gr2  # noqa: E402

MODEL_EXT = (".gr2",)
TEX_EXT = (".ddt",)
REF_EXT = (".gr2", ".ddt", ".xml", ".tga", ".bmp", ".png", ".wav", ".particle", ".lgt")


CATEGORIES = ("buildings", "buildingsets", "units", "effects", "ui", "terrain", "homecity",
              "animation_library", "icons", "objects")
RESOLVE_EXT = (".gr2", ".ddt", ".xml", ".particle", ".dmg")


def norm(path):
    """Comparable path: lowercase, backslashes, no leading separators, no leading 'art\\', and
    a compiled 'x.xml.xmb' as 'x.xml'."""
    p = path.strip().replace("/", "\\").lower().lstrip("\\")
    p = p[4:] if p.startswith("art\\") else p
    return p[:-4] if p.endswith(".xml.xmb") else p


def resolve(ref, known):
    """The known path a reference names, trying the extensions the game leaves out, or None."""
    n = norm(ref)
    if n in known:
        return n
    for ext in RESOLVE_EXT:
        if n + ext in known:
            return n + ext
    return None


def is_anim(path):
    p = path.replace("/", "\\").lower()
    return ("\\art\\" in "\\" + p) and (p.endswith(".xml") or p.endswith(".xml.xmb"))


def kind(path):
    p = path.lower()
    if p.endswith(MODEL_EXT):
        return "model"
    if p.endswith(TEX_EXT):
        return "texture"
    if is_anim(p):
        return "anim"
    return None


def category(path):
    """The folder below 'art' (units, buildings, ...), or below a mod's own folder there, or
    '(other)'."""
    parts = [x for x in path.replace("/", "\\").lower().split("\\") if x]
    if "art" in parts:
        i = parts.index("art")
        if i + 3 < len(parts) and parts[i + 1] not in CATEGORIES and parts[i + 2] in CATEGORIES:
            return parts[i + 2]
        if i + 2 < len(parts):
            return parts[i + 1]
    return "(other)"


# --------------------------------------------------------------------------------------------------
# File readers (bytes in, facts out)

def read_ddt(raw):
    info = {"head": raw[:16].hex()}
    if len(raw) >= 16 and raw[:4] == b"RTS3":
        usage, alpha, fmt, mips = raw[4], raw[5], raw[6], raw[7]
        w, h = struct.unpack_from("<II", raw, 8)
        info.update(magic="RTS3", usage=usage, alpha=alpha, format=fmt, mips=mips, width=w, height=h)
    else:
        info["magic"] = raw[:4].decode("latin-1", "replace")
    return info


def read_gr2(raw):
    info = {"head": raw[:16].hex()}
    info.update(gr2.header_facts(raw))
    return info


def model_stats(raw):
    """Statistics of an uncompressed model (see gr2.Doc.stats), or None."""
    try:
        return gr2.load(raw).stats()
    except gr2.Compressed:
        return None


def anim_tree(raw):
    """ElementTree root of an anim file given as XML text or compiled XMB."""
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        raw = xmbedit.to_xml(elems, attrs, root).encode("utf-8")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raw = raw.decode("utf-16").encode("utf-8")
    return ET.fromstring(raw)


def read_anim(raw):
    root = anim_tree(raw)
    tags = collections.Counter()
    attrs = collections.Counter()
    refs = []                       # (element tag, type attribute, file)
    points = collections.Counter()  # attach point / bone names
    logic = collections.Counter()
    anims = collections.Counter()
    decals = []
    for el in root.iter():
        tag = el.tag.lower()
        tags[tag] += 1
        for k in el.attrib:
            attrs[f"{tag}@{k.lower()}"] += 1
        text = (el.text or "").strip()
        f = next((c for c in el if c.tag.lower() == "file"), None)
        if f is not None and (f.text or "").strip():
            refs.append((tag, el.attrib.get("type", el.attrib.get("Type", "")), f.text.strip()))
        elif tag != "file" and text.lower().endswith(REF_EXT) and len(text) < 260:
            refs.append((tag, el.attrib.get("type", ""), text))
        if any(s in tag for s in ("bone", "attach", "point")):
            for v in [text] + [el.attrib[k] for k in el.attrib if k.lower() in ("name", "bone", "frombone", "tobone")]:
                if v and len(v) < 80:
                    points[v] += 1
        if tag == "logic":
            logic[el.attrib.get("type", el.attrib.get("Type", "?"))] += 1
        if tag == "anim" and text:
            anims[text.split()[0]] += 1
        if tag == "decal":
            dims = {c.tag.lower(): (c.text or "").strip() for c in el}
            try:
                decals.append((float(dims["width"]), float(dims["height"])))
            except (KeyError, ValueError):
                pass
    return {"tags": dict(tags), "attrs": dict(attrs), "refs": refs, "points": dict(points),
            "logic": dict(logic), "anims": dict(anims), "decals": decals}


# --------------------------------------------------------------------------------------------------
# Sources: loose files and .bar entries

def iter_files(folders, use_bar):
    """Yields (display path, size, reader); reader() returns the bytes, reader(n) the first n."""
    for folder in folders:
        for base, _dirs, names in os.walk(folder):
            for n in names:
                full = os.path.join(base, n)
                rel = os.path.relpath(full, folder)
                if kind(rel):
                    def loose(n=None, p=full):
                        with open(p, "rb") as fh:
                            return fh.read() if n is None else fh.read(n)
                    yield rel, os.path.getsize(full), loose
                elif use_bar and n.lower().endswith(".bar"):
                    try:
                        entries = bar.read_entries(full)
                    except (OSError, ValueError, struct.error) as exc:
                        yield f"{rel} (unreadable archive: {exc})", 0, None
                        continue
                    for stored, offset, size in entries:
                        if kind(stored):
                            def reader(n=None, p=full, o=offset, s=size):
                                with open(p, "rb") as fh:
                                    fh.seek(o)
                                    return fh.read(s if n is None else min(n, s))
                            yield f"{rel}:{stored}", size, reader


def survey(folders, use_bar=False, label=None, reference=None, proto=None, bridge=None):
    files = {"model": {}, "texture": {}, "anim": {}}
    readers = {}                      # model key -> (display path, size, reader)
    errors = []
    for path, size, reader in iter_files(folders, use_bar):
        if reader is None:
            errors.append(path)
            continue
        k = kind(path.split(":")[-1])
        try:
            if k == "texture":
                info = read_ddt(reader(64))
            elif k == "model":
                info = read_gr2(reader(1024))
                readers[norm(path.split(":")[-1])] = (path, size, reader)
            else:
                info = read_anim(reader())
        except Exception as exc:     # a survey reports, it does not stop
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        info["size"] = size
        files[k][path] = info

    own = {norm(p.split(":")[-1]) for k in files for p in files[k]}
    ref_known = set()
    if reference:
        with open(reference, encoding="utf-8") as fh:
            ref = json.load(fh)
        ref_known = {norm(p.split(":")[-1]) for k in ("model", "texture", "anim") for p in ref["files"][k]}

    # cross references
    used_by = collections.defaultdict(set)
    per_anim = {}
    for path, info in files["anim"].items():
        local = remote = missing = 0
        for _tag, _typ, f in info["refs"]:
            n = resolve(f, own) or resolve(f, ref_known) or norm(f)
            used_by[n].add(path)
            if n in own:
                local += 1
            elif n in ref_known:
                remote += 1
            else:
                missing += 1
        per_anim[path] = {"refs": len(info["refs"]), "own": local, "reference": remote, "unresolved": missing,
                          "category": category(path.split(":")[-1])}

    def top(counter, n=40):
        return counter.most_common(n)

    tags, points, logic, anims, reftypes = (collections.Counter() for _ in range(5))
    for info in files["anim"].values():
        tags.update(info["tags"])
        points.update(info["points"])
        logic.update(info["logic"])
        anims.update(info["anims"])
        reftypes.update(f"{t}{'/' + ty if ty else ''}" for t, ty, _ in info["refs"])
    tex_sizes = collections.Counter(f"{i.get('width')}x{i.get('height')}" for i in files["texture"].values())
    tex_formats = collections.Counter(f"format {i.get('format')} alpha {i.get('alpha')}"
                                      for i in files["texture"].values())
    by_cat = collections.Counter(a["category"] for a in per_anim.values())
    reuse = sorted(((len(v), k) for k, v in used_by.items()), reverse=True)[:40]
    new_files = {}
    if reference:
        fresh = collections.Counter()
        for k in files:
            for p in files[k]:
                if norm(p.split(":")[-1]) not in ref_known:
                    fresh[f"{k} {category(p.split(':')[-1])}"] += 1
        new_files = dict(fresh)

    rep = {
        "label": label or os.path.basename(os.path.abspath(folders[0])),
        "folders": [os.path.abspath(f) for f in folders],
        "counts": {k: len(v) for k, v in files.items()},
        "anim_categories": dict(by_cat),
        "anim_tags": top(tags, 60), "ref_types": top(reftypes), "attach_points": top(points, 60),
        "logic_types": top(logic), "anim_names": top(anims, 60),
        "texture_sizes": top(tex_sizes), "texture_formats": top(tex_formats),
        "most_reused": reuse, "per_anim": per_anim, "new_files": new_files,
        "kitbash": {
            "anims_only_reference": sum(1 for a in per_anim.values() if a["refs"] and a["own"] == 0 and a["unresolved"] == 0 and a["reference"] > 0),
            "anims_only_own": sum(1 for a in per_anim.values() if a["refs"] and a["reference"] == 0 and a["unresolved"] == 0),
            "anims_mixed": sum(1 for a in per_anim.values() if a["own"] and (a["reference"] or a["unresolved"])),
            "anims_with_unresolved": sum(1 for a in per_anim.values() if a["unresolved"]),
        },
        "files": files, "errors": errors,
    }
    if proto:
        rep["buildings"] = join_buildings(proto, files, readers, bridge, errors)
    return rep


# --------------------------------------------------------------------------------------------------
# Buildings: the unit list joined to anim files and models

UNIT_BLOCK = re.compile(r"<Unit\s+id\s*=\s*['\"](\d+)['\"]\s+name\s*=\s*['\"]([^'\"]+)['\"]\s*>(.*?)</Unit>",
                        re.S)
SECONDARY = ("damage", "death", "_con", "lp_", "collapse", "rubble", "_dmg", "constructions\\",
             "\\props", "flag", "debris", "scaffold")
STAGE_RE = re.compile(r"constructions\\(\d+x\d+)_stage", re.I)
STOCK_UNITS_PER_METER = 0.615157485      # the game's own buildings; distances are in these units
# Profiles name only the base game's rubble and placement rules, never a mod's own.
STOCK_RUBBLE = re.compile(r"^BuildingRubble\d+x\d+$")
STOCK_PLACEMENT = ("buildingsmall.xml", "buildinglarge.xml")


def _tag(block, tag):
    m = re.search(rf"<{tag}>\s*([^<]*?)\s*</{tag}>", block, re.I)
    return m.group(1) if m else None


def _num(block, tag):
    try:
        return float(_tag(block, tag))
    except (TypeError, ValueError):
        return None


def read_buildings(path):
    """Units of the unit list that carry the Building unit type."""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    out = []
    for m in UNIT_BLOCK.finditer(text):
        block = m.group(3)
        types = {t.strip().lower() for t in re.findall(r"<UnitType>([^<]*)</UnitType>", block, re.I)}
        if "building" not in types:
            continue
        out.append({"name": m.group(2), "anim": _tag(block, "AnimFile"),
                    "radius": (_num(block, "ObstructionRadiusX"), _num(block, "ObstructionRadiusZ")),
                    "rubble": _tag(block, "DeadReplacement"), "placement": _tag(block, "PlacementFile"),
                    "wall": "abstractwall" in types})
    return out


def main_models(anim_info, models):
    """The finished building's models an anim file names (not construction stages, damaged,
    death, low-poly or prop models), as keys of `models`."""
    found = []
    for _tag_, typ, f in anim_info["refs"]:
        if (typ or "").lower() != "grannymodel":
            continue
        if any(s in norm(f) for s in SECONDARY):
            continue
        k = resolve(f, models)
        if k and k not in found:
            found.append(k)
    return found


class Bridge:
    """Writes compressed models uncompressed into a cache through an external Granny tool:
    `<exe> rebake --install <install> --file <in> --out <out> --noop`, run from the cache."""

    def __init__(self, exe, install, cache):
        cache, install = os.path.abspath(cache), os.path.abspath(install)
        if os.path.commonpath([cache, install]) == install:
            raise ValueError("the cache must be outside the game folder")
        self.exe, self.install, self.cache = exe, install, cache
        for sub in ("src", "raw"):
            os.makedirs(os.path.join(cache, sub), exist_ok=True)

    def raw(self, key, size, reader):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[-150:] + f"_{size}.gr2"
        src, out = (os.path.join(self.cache, d, safe) for d in ("src", "raw"))
        if not os.path.exists(out):
            if not os.path.exists(src):
                with open(src, "wb") as fh:
                    fh.write(reader())
            try:
                r = subprocess.run([self.exe, "rebake", "--install", self.install, "--file", src,
                                    "--out", out, "--noop"], cwd=self.cache, capture_output=True,
                                   timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(f"bridge failed: {exc}") from exc
            if r.returncode != 0 or not os.path.exists(out):
                raise RuntimeError(f"bridge exit {r.returncode}")
        with open(out, "rb") as fh:
            return fh.read()


def _up_axis(stats):
    up = (stats.get("art_tool") or {}).get("up") or (0, 0, 1)
    return max(range(3), key=lambda i: abs(up[i]))


def _extent(stats):
    """(width, depth, height) in metres from a model's box and its declared up axis."""
    lo, hi = stats["bbox_m"]
    v = _up_axis(stats)
    h = [i for i in range(3) if i != v]
    return hi[h[0]] - lo[h[0]], hi[h[1]] - lo[h[1]], hi[v] - lo[v]


def join_buildings(proto, files, readers, bridge, errors):
    anims = {norm(p.split(":")[-1]): (p, info) for p, info in files["anim"].items()}
    textures = {norm(p.split(":")[-1]): info for p, info in files["texture"].items()}
    stats_cache = {}

    def stats_of(key):
        if key in stats_cache:
            return stats_cache[key]
        st = None
        display, size, reader = readers[key]
        try:
            st = model_stats(reader())
            if st is None and bridge is not None:
                st = model_stats(bridge.raw(display, size, reader))
        except Exception as exc:
            errors.append(f"{display}: {type(exc).__name__}: {exc}")
        stats_cache[key] = st
        return st

    out = []
    for b in read_buildings(proto):
        rec = {"name": b["name"], "radius": b["radius"], "rubble": b["rubble"],
               "placement": b["placement"], "wall": b["wall"]}
        a = resolve(b["anim"] or "", anims)
        if a:
            path, info = anims[a]
            rec["anim"] = path
            rec["stages"] = sorted({m.group(1).lower() for _t, _y, f in info["refs"]
                                    for m in [STAGE_RE.search(f)] if m})
            decals = info.get("decals") or []
            rec["decal"] = max(decals, key=lambda d: d[0] * d[1]) if decals else None
            best = None
            for k in main_models(info, readers):
                st = stats_of(k)
                if st and st.get("verts") and "bbox_m" in st and (best is None or st["tris"] > best[1]["tris"]):
                    best = (k, st)
            if best:
                k, st = best
                w, d, h = _extent(st)
                tex = None
                for t in st.get("textures") or []:
                    tail = t.replace("/", "\\").lower().split("\\art\\")[-1]
                    tk = resolve(tail, textures)
                    if tk and not any(s in tk for s in ("_normal", "_bump", "_b.ddt", "_spec")):
                        ti = textures[tk]
                        tex = {"size": f"{ti.get('width')}x{ti.get('height')}",
                               "format": ti.get("format"), "alpha": ti.get("alpha")}
                        break
                at = st.get("art_tool") or {}
                rec.update({"model": readers[k][0], "tris": st["tris"], "verts": st["verts"],
                            "size_m": (round(w, 3), round(d, 3), round(h, 3)),
                            "basis": f"{at.get('name')} {at.get('units_per_meter') or 0:.6g} "
                                     f"up {'XYZ'[_up_axis(st)]}",
                            "layouts": st.get("vertex_layouts"), "index_bits": st.get("index_bits"),
                            "effects": [m["effect"] for m in st.get("materials", []) if m.get("effect")],
                            "bones": [x["name"] for x in st.get("bones", [])], "texture": tex})
        out.append(rec)
    return out


def _q(values):
    v = sorted(values)
    if not v:
        return None
    p90 = v[min(len(v) - 1, int(round(0.9 * (len(v) - 1))))]
    return {"min": v[0], "median": statistics.median(v), "p90": p90, "max": v[-1]}


def profile(rep):
    """Measurements only, for the generators: budgets and sizes per footprint class, formats,
    bases, bones. No file of the scanned mod is named."""
    bs = [b for b in rep.get("buildings", []) if b.get("tris") and all(b["radius"]) and not b["wall"]]
    classes = collections.defaultdict(list)
    for b in bs:
        rx, rz = b["radius"]
        classes[f"{round(2 * rx)}x{round(2 * rz)}"].append(b)
    out = {"schema": 1, "source": rep["label"], "buildings_measured": len(bs),
           "units_per_meter_game": STOCK_UNITS_PER_METER, "classes": {}}
    def plausible(b, s):
        """The declared size agrees with the obstruction (within 4 times either way). Some
        models declare a scale that contradicts it; they are left out of the size ratios."""
        return s > 0 and 0.25 <= s / (2 * max(b["radius"])) <= 4

    out["size_outliers"] = collections.Counter(
        b["basis"] for b in bs
        if not plausible(b, max(b["size_m"][0], b["size_m"][1]) * STOCK_UNITS_PER_METER)).most_common()
    for key, group in sorted(classes.items(), key=lambda kv: -len(kv[1])):
        sized = [(b, max(b["size_m"][0], b["size_m"][1]) * STOCK_UNITS_PER_METER) for b in group]
        sized = [(b, s) for b, s in sized if plausible(b, s)]
        side = [s for _b, s in sized]
        ratio = [max(b["radius"]) / (s / 2) for b, s in sized]
        decal = [max(b["decal"]) / s for b, s in sized if b.get("decal")]
        out["classes"][key] = {
            "count": len(group), "tris": _q([b["tris"] for b in group]),
            "verts": _q([b["verts"] for b in group]),
            "side_units": _q([round(s, 2) for s in side]),
            "height_m": _q([round(b["size_m"][2], 2) for b, _s in sized]),
            "obstruction_over_half_side": _q([round(r, 3) for r in ratio]),
            "decal_over_side": _q([round(r, 3) for r in decal]),
            "stages": collections.Counter(s for b in group for s in b.get("stages", [])).most_common(3),
            "rubble": collections.Counter(b["rubble"] for b in group
                                          if b["rubble"] and STOCK_RUBBLE.match(b["rubble"])).most_common(3),
            "placement": collections.Counter(b["placement"].lower() for b in group if b["placement"]
                                             and b["placement"].lower() in STOCK_PLACEMENT).most_common(3),
        }
    count = collections.Counter
    out["tris_all"] = _q([b["tris"] for b in bs])
    out["bases"] = count(b["basis"] for b in bs).most_common(10)
    out["vertex_layouts"] = count(l for b in bs for l in b.get("layouts") or []).most_common(10)
    out["index_bits"] = count(str(b.get("index_bits")) for b in bs).most_common()
    out["effects"] = count(e for b in bs for e in b.get("effects") or []).most_common(10)
    out["bones"] = count(n for b in bs for n in {x.lower() for x in b.get("bones") or []}
                         if n.startswith("bone_") and not n.startswith("bone_debris")).most_common(20)
    out["textures"] = count(f"{b['texture']['size']} format {b['texture']['format']} alpha {b['texture']['alpha']}"
                            for b in bs if b.get("texture")).most_common(10)
    return out


def summary_md(rep):
    out = [f"# Art survey: {rep['label']}", "", "Folders: " + ", ".join(f"`{f}`" for f in rep["folders"]), ""]
    c = rep["counts"]
    out += ["| Models (.gr2) | Textures (.ddt) | Anim files | Read errors |", "|---|---|---|---|",
            f"| {c['model']} | {c['texture']} | {c['anim']} | {len(rep['errors'])} |", ""]

    def table(title, rows, head=("Value", "Count")):
        if not rows:
            return
        out.extend([f"## {title}", "", f"| {head[0]} | {head[1]} |", "|---|---|"])
        out.extend(f"| `{k}` | {v} |" for k, v in rows)
        out.append("")

    table("Anim files by folder below art", sorted(rep["anim_categories"].items(), key=lambda t: -t[1]))
    k = rep["kitbash"]
    out += ["## Reuse", "",
            "References are resolved against the scanned files (own) and the --reference survey.", "",
            "| Anim files that use | Count |", "|---|---|",
            f"| only reference files | {k['anims_only_reference']} |",
            f"| only their own files | {k['anims_only_own']} |",
            f"| both | {k['anims_mixed']} |",
            f"| a file found nowhere | {k['anims_with_unresolved']} |", ""]
    table("Most referenced files", [(f, n) for n, f in rep["most_reused"]], ("File", "Anim files"))
    table("Reference kinds (element/type)", rep["ref_types"])
    table("Attach points and bones", rep["attach_points"])
    table("Logic types", rep["logic_types"])
    table("Anim names", rep["anim_names"])
    table("Texture sizes (header, to verify)", rep["texture_sizes"])
    table("Texture formats (header, to verify)", rep["texture_formats"])
    table("Anim file elements", rep["anim_tags"])
    if rep.get("new_files"):
        table("Files not in the reference survey (kind, category)",
              sorted(rep["new_files"].items(), key=lambda t: -t[1]))
    if "buildings" in rep:
        bs = rep["buildings"]
        out += ["## Buildings", "",
                f"{len(bs)} units with the Building type; {sum(1 for b in bs if b.get('anim'))} anim files "
                f"found; {sum(1 for b in bs if b.get('tris'))} models measured.", ""]
    if rep.get("profile"):
        pr = rep["profile"]
        out += ["## Building profile (by obstruction footprint, game units)", "",
                "| Class | Count | Triangles median / p90 / max | Side (units) median | "
                "Obstruction / half side | Decal / side | Stages |",
                "|---|---|---|---|---|---|---|"]
        for key, c in pr["classes"].items():
            t, s = c["tris"], c["side_units"]
            o, dc = c["obstruction_over_half_side"], c["decal_over_side"]
            out.append(f"| {key} | {c['count']} | {t['median']} / {t['p90']} / {t['max']} | "
                       f"{s['median'] if s else ''} | {o['median'] if o else ''} | "
                       f"{dc['median'] if dc else ''} | {', '.join(f'{a} ({n})' for a, n in c['stages'])} |")
        out.append("")
        table("Model bases", pr["bases"])
        table("Declared scale contradicts the obstruction (basis)", pr.get("size_outliers", []))
        table("Vertex layouts", pr["vertex_layouts"])
        table("Shader effects", pr["effects"])
        table("Bones (not debris)", pr["bones"])
        table("Diffuse textures (size, format, alpha)", pr["textures"])
    if rep["errors"]:
        out += ["## Read errors", ""] + [f"- {e}" for e in rep["errors"][:100]] + [""]
    return "\n".join(out)


def main(argv):
    if "--out" not in argv or argv.index("--out") + 1 >= len(argv):
        print(__doc__)
        return 2
    def opt(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None

    out, label, reference, proto = opt("--out"), opt("--label"), opt("--reference"), opt("--proto")
    granny, cache, profile_out = opt("--granny"), opt("--cache"), opt("--profile-out")
    values = {out, label, reference, proto, granny, cache, profile_out, opt("--granny-install")}
    folders = [a for a in argv if not a.startswith("--") and a not in values]
    if not folders or (granny and not cache):
        print(__doc__)
        return 2
    bridge = Bridge(granny, opt("--granny-install") or folders[0], cache) if granny else None
    rep = survey(folders, "--bar" in argv, label, reference, proto, bridge)
    if proto:
        rep["profile"] = profile(rep)
        if profile_out:
            os.makedirs(os.path.dirname(os.path.abspath(profile_out)), exist_ok=True)
            with open(profile_out, "w", encoding="utf-8") as fh:
                json.dump(rep["profile"], fh, indent=1)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary_md(rep))
    c = rep["counts"]
    print(f"{rep['label']}: {c['model']} models, {c['texture']} textures, {c['anim']} anim files, "
          f"{len(rep['errors'])} read errors -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
