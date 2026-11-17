# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventories the home-city models of a game copy or a mod, and plans moving one home city's
models into a folder of its own. Nothing in the game copy is written.

    python -I tools\\hc_survey.py --game <copy> --out <report folder>
        [--cache <folder> ...] [--granny <bridge.exe> --work <folder>]
        --target "<Mod>\\homecity" [--plan <civ or file stem> ...]

--target is the tree each home city's files should end in, below art: <target>\\<civ>\\. Its
other reading, homecity\\<Mod>\\<civ>\\, is reported beside it ("option B").

What it reads:

- every home-city file: data\\homecity*.xml and the same names anywhere under Campaign\\ (plain
  or compiled). Their top-level <visual>, <watervisual>, <backgroundvisual>, <pathdata> and a
  building's <visual><file> are relative to art\\homecity\\; a <prop>'s <visual>, the props and
  proto-unit tables and <modelfile> are relative to art\\. A path that is not found from its base
  is tried from the other one, and the report says so;
- the anim files they name, and every anim file those include (<include>), loose first (a loose
  compiled twin `x.xml.xmb` wins over `x.xml`), then the art folder's .bar archives;
- each Granny model and animation those name (<assetreference type="GrannyModel|GrannyAnim">).

A file is the mod's own when it is loose and the archives hold no file of that name ("override"
when they do). For each of the mod's own Granny files it measures, uncompressed: the basis
(ArtToolInfo: tool, units per metre, up axis), the bones' world scale (the root's, and the
largest), the bounding size, and every stored texture name: what it resolves to (the part after
"\\art\\", then the model's folder, then any folder), the resolved .ddt's header digits (usage,
alpha, format, mips: the (u,a,f,m) suffix of a source .tga) and the source images beside it.

Compressed files are read from survey caches (`--cache`, holding raw\\<md5>.gr2, read only), or
expanded by an external bridge into `--work` (`<exe> rebake --install <copy> --file <in> --out
<out> --noop`, the tool of tools/model_survey.py). The game's Granny runtime is never shipped or
called by this repository.

Writes into --out: models.csv (one row per Granny file of the mod's), textures.csv (one row per
stored texture name), refs.csv (every reference followed), summary.md (counts per home city),
report.json; with --plan, plan_<name>.md: the moves, texture renames and XML line changes for that
home city. The reports name the scanned files: keep them out of public repositories.
"""
import collections
import csv
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import fix_bone_scale as fbs  # noqa: E402
import xmbedit  # noqa: E402
from aoe3game import gr2  # noqa: E402

STOCK_UPM = 0.615157485
INCH_UPM = 39.370079
BIG_SCALE = 10.0                      # a bone whose world axes are this far from 1 is "scaled"
USUAL = {"0,1,8,8": "colour", "6,0,9,8": "bump"}
IMAGE_EXT = (".tga", ".png", ".jpg", ".jpeg", ".bmp", ".dds", ".ddt", ".psd", ".tif", ".tiff")
SOURCE_EXT = (".tga", ".png", ".jpg", ".jpeg", ".bmp", ".psd", ".tif", ".tiff")
SUFFIX_RE = re.compile(r"\.\((\d+),(\d+),(\d+),(\d+)\)$")
HC_NAME_RE = re.compile(r"^homecity.*\.xml(\.xmb)?$", re.I)


def norm(path):
    """An art path as a lookup key: lower case, backslashes, no leading separator or 'art\\'."""
    p = str(path).replace("/", "\\").strip().strip("\\").lower()
    while p.startswith(".\\"):
        p = p[2:]
    return p[4:] if p.startswith("art\\") else p


def join_key(base, rel):
    """norm(base\\rel) with '..' resolved; None when it climbs above the art folder."""
    parts = []
    for part in (base + "\\" + norm(rel)).split("\\"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "\\".join(parts)


# --------------------------------------------------------------------------------------------------
# A lenient XML scan: element paths, attributes, direct text and line numbers, even for files an
# XML parser refuses (the game reads some that are not well formed).

TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)((?:\s[^<>]*?)?)(/?)>")
ATTR_RE = re.compile(r"([\w.:-]+)\s*=\s*(\"[^\"]*\"|'[^']*')")
COMMENT_RE = re.compile(r"<!--.*?(-->|$)", re.S)


def blank_comments(text):
    """The text with every comment's characters but its newlines turned to spaces."""
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def scan(text):
    """Yields (stack, text, line) for each element with direct text before its first child or
    end: stack is [(tag in lower case, {attribute: value})] from the root to the element."""
    text = blank_comments(text)
    stack, line, last = [], 1, 0
    for m in TAG_RE.finditer(text):
        line += text.count("\n", last, m.start())
        last = m.start()
        closing, tag, attrs, empty = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    del stack[i:]
                    break
            continue
        at = {k.lower(): v[1:-1] for k, v in ATTR_RE.findall(attrs or "")}
        stack.append((tag, at))
        if empty:
            stack.pop()
            continue
        end = text.find("<", m.end())
        body = text[m.end():end if end >= 0 else len(text)].strip()
        if body:
            yield list(stack), body, line


def decode_text(raw):
    """XML text of a plain (UTF-8 or UTF-16) or compiled (.xmb) file."""
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        return xmbedit.to_xml(elems, attrs, root)
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


# --------------------------------------------------------------------------------------------------
# The files of a game copy

class Art:
    """An art folder: its loose files (key -> full path) and its archives' (key -> entry)."""

    def __init__(self, root):
        self.root = root
        self.loose = {}
        for folder, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(folder, name)
                self.loose.setdefault(norm(os.path.relpath(full, root)), full)
        self.archived = {}
        for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            if name.lower().endswith(".bar"):
                archive = os.path.join(root, name)
                for stored, offset, size in bar.read_entries(archive):
                    self.archived.setdefault(norm(stored), (archive, stored, offset, size))
        self.by_stem = collections.defaultdict(list)
        for key in list(self.loose) + list(self.archived):
            stem, ext = os.path.splitext(os.path.basename(key))
            if ext == ".ddt" and key not in self.by_stem[stem]:
                self.by_stem[stem].append(key)
        self.by_folder = collections.defaultdict(list)
        for key in self.loose:
            self.by_folder[os.path.dirname(key)].append(key)

    def exists(self, key):
        return key in self.loose or key in self.archived

    def status(self, key):
        """mod (loose only), override (loose and archived), stock (archived only) or missing."""
        if key in self.loose:
            return "override" if key in self.archived else "mod"
        return "stock" if key in self.archived else "missing"

    def read(self, key, size=None):
        if key in self.loose:
            with open(self.loose[key], "rb") as fh:
                return fh.read() if size is None else fh.read(size)
        if key in self.archived:
            archive, _stored, offset, length = self.archived[key]
            with open(archive, "rb") as fh:
                fh.seek(offset)
                return fh.read(length if size is None else min(size, length))
        return None

    def display(self, key):
        """The path as it is spelled on disk (loose) or in its archive, below art."""
        if key in self.loose:
            return os.path.relpath(self.loose[key], self.root)
        if key in self.archived:
            stored = self.archived[key][1]
            return stored[4:] if stored.lower().startswith("art\\") else stored
        return key

    def anim_variants(self, key):
        """[(file key, where)] of an anim file, the one the game reads first: a loose compiled
        twin wins over a loose plain file, loose wins over archived."""
        key = key[:-4] if key.endswith(".xmb") else key
        out = []
        for k, where in ((key + ".xmb", "loose"), (key, "loose")):
            if k in self.loose:
                out.append((k, where))
        for k in (key + ".xmb", key):
            if k in self.archived and not out:
                out.append((k, "archived"))
        return out


def homecity_files(game):
    """[(file path relative to the game folder, full path)] of every home-city file."""
    out = []
    for top in ("data", "Campaign", "campaign"):
        base = os.path.join(game, top)
        if not os.path.isdir(base):
            continue
        for folder, _dirs, files in os.walk(base):
            if top.lower() == "data" and os.path.normcase(folder) != os.path.normcase(base):
                continue
            for name in files:
                if HC_NAME_RE.match(name):
                    full = os.path.join(folder, name)
                    rel = os.path.relpath(full, game)
                    if name.lower().endswith(".xmb") and os.path.exists(full[:-4]):
                        continue                         # the plain one is listed instead
                    out.append((rel, full))
    seen, uniq = set(), []
    for rel, full in sorted(out, key=lambda r: r[0].lower()):
        if os.path.normcase(full) not in seen:
            seen.add(os.path.normcase(full))
            uniq.append((rel, full))
    return uniq


# --------------------------------------------------------------------------------------------------
# References

HC_TOP = ("visual", "watervisual", "backgroundvisual", "pathdata")
HC_TABLES = ("homecityprops", "homecityprotounits")


def hc_refs(text):
    """{"civ": name or None, "root": root tag, "refs": [{tag, value, line, base}]} of a home-city
    file. base: 'homecity' (relative to art\\homecity) or 'art'."""
    civ, root, refs = None, None, []
    for stack, value, line in scan(text):
        tags = [t for t, _a in stack]
        root = root or tags[0]
        tag = tags[-1]
        if tags == ["homecity", "civ"] and civ is None:
            civ = value
        if tag not in HC_TOP + ("file", "modelfile"):
            continue
        if tag == "file" and (len(tags) < 2 or tags[-2] != "visual"):
            continue
        parents = tags[:-1] if tag != "file" else tags[:-2]
        if tag == "modelfile" or tags[0] in HC_TABLES or "prop" in parents:
            base = "art"
        elif parents in (["homecity"], ["homecity", "building"]):
            base = "homecity"
        else:
            base = "art"
        refs.append({"tag": tag if tag != "file" else "visual/file", "value": value,
                     "line": line, "base": base})
    if root is None:
        m = re.search(r"<\s*([A-Za-z_][\w]*)", blank_comments(text).split("?>", 1)[-1])
        root = m.group(1).lower() if m else ""
    return {"civ": civ, "root": root, "refs": refs}


def anim_refs(text):
    """[{kind, value, line}] of an anim file: model, anim (Granny), include, texture."""
    out = []
    for stack, value, line in scan(text):
        tag = stack[-1][0]
        if tag == "include":
            out.append({"kind": "include", "value": value, "line": line})
        elif tag == "file" and len(stack) >= 2 and stack[-2][0] == "assetreference":
            typ = stack[-2][1].get("type", "").lower()
            kind = {"grannymodel": "model", "grannyanim": "anim"}.get(typ, "file:" + typ)
            out.append({"kind": kind, "value": value, "line": line})
        elif tag in ("texture", "from", "to") or tag.endswith("texture"):
            out.append({"kind": "texture:" + tag, "value": value, "line": line})
    return out


def resolve_hc(art, ref):
    """(art key, base used) of a home-city reference; base 'homecity' or 'art', with
    '+fallback' when only the other base finds it; (None, why) when neither does."""
    first, second = (("homecity", "art") if ref["base"] == "homecity" else ("art", "homecity"))
    tries = []
    for i, base in enumerate((first, second)):
        key = join_key("homecity" if base == "homecity" else "", ref["value"])
        if key is None:
            tries.append(None)
            continue
        tries.append(key)
        if ref["tag"] == "pathdata" or key.endswith(".gr2"):
            ok = art.exists(key)
        else:
            ok = bool(art.anim_variants(key))
        if ok:
            return key, base + ("+fallback" if i else "")
    return (tries[0], "missing")


def walk(art, start_keys, cache):
    """Follows anim files from `start_keys`: {anim key: {"variants": [...], "refs": [...],
    "depth": n, "error": str}} for every anim file reached (cache: shared between calls)."""
    reached = {}
    queue = [(k, 0) for k in start_keys]
    while queue:
        key, depth = queue.pop(0)
        if key in reached:
            reached[key]["depth"] = min(reached[key]["depth"], depth)
            continue
        if key not in cache:
            info = {"variants": art.anim_variants(key), "refs": [], "error": None}
            for vkey, where in info["variants"]:
                try:
                    text = decode_text(art.read(vkey))
                except Exception as exc:                   # noqa: BLE001 - reported, not fatal
                    info["error"] = f"{vkey}: {type(exc).__name__}: {exc}"[:200]
                    continue
                for r in anim_refs(text):
                    r["variant"] = vkey
                    r["where"] = where
                    info["refs"].append(r)
            cache[key] = info
        info = dict(cache[key])
        info["depth"] = depth
        reached[key] = info
        effective = info["variants"][0][0] if info["variants"] else None
        for r in info["refs"]:
            if r["kind"] == "include" and r["variant"] == effective:
                inc = join_key("", r["value"])
                if inc and inc not in reached:
                    queue.append((inc, depth + 1))
    return reached


def model_key(value):
    k = join_key("", value) or norm(value)
    return k if k.endswith(".gr2") else k + ".gr2"


# --------------------------------------------------------------------------------------------------
# Measuring a Granny file

def raw_bytes(data, caches=(), bridge=None):
    """(uncompressed bytes or None, how): the file itself, a survey cache's raw\\<md5>.gr2, or the
    bridge's output in its work folder."""
    if gr2.header_facts(data).get("raw"):
        return data, "raw"
    md5 = hashlib.md5(data).hexdigest()
    for cache in caches:
        p = os.path.join(cache, "raw", md5 + ".gr2")
        if os.path.exists(p):
            with open(p, "rb") as fh:
                return fh.read(), "cache"
    if bridge is None:
        return None, "compressed, not in a cache"
    exe, install, work = bridge
    out = os.path.join(work, "raw", md5 + ".gr2")
    if not os.path.exists(out):
        os.makedirs(os.path.join(work, "raw"), exist_ok=True)
        os.makedirs(os.path.join(work, "src"), exist_ok=True)
        src = os.path.join(work, "src", md5 + ".gr2")
        with open(src, "wb") as fh:
            fh.write(data)
        tmp = out + f".{os.getpid()}.tmp"
        try:
            r = subprocess.run([exe, "rebake", "--install", install, "--file", src, "--out", tmp,
                                "--noop"], cwd=work, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"bridge failed: {type(exc).__name__}"
        finally:
            if os.path.exists(src):
                os.remove(src)
        if r.returncode != 0 or not os.path.exists(tmp):
            if os.path.exists(tmp):
                os.remove(tmp)
            return None, f"bridge exit {r.returncode}"
        os.replace(tmp, out)
    with open(out, "rb") as fh:
        return fh.read(), "bridge"


def _vec(v):
    return tuple(round(float(x), 4) for x in v) if v is not None else None


def measure(raw):
    """The facts of one uncompressed Granny file."""
    doc = gr2.load(raw)
    st = doc.stats()
    art = st.get("art_tool") or {}
    rec = {"art_tool": art.get("name"), "upm": art.get("units_per_meter"),
           "up": _vec(art.get("up")), "right": _vec(art.get("right")),
           "exporter": st.get("exporter"), "tris": st["tris"],
           "textures": list(dict.fromkeys(str(t) for t in st["textures"] if t)),
           "animations": len(doc.root().get("Animations") or [])}
    if "bbox" in st:
        lo, hi = st["bbox"]
        rec["size"] = [round(hi[k] - lo[k], 3) for k in range(3)]
    try:
        skeletons = fbs.read_skeletons(doc)
        bones = [b for _n, bs in skeletons for b in bs]
        roots = [b for b in bones if b.parent < 0]
        rec["bones"] = len(bones)
        rec["root_scale"] = round(roots[0].scale, 4) if roots else None
        rec["root_name"] = roots[0].name if roots else None
        rec["max_bone_scale"] = round(max((b.scale for b in bones), default=1.0), 4)
        rec["scaled_bones"] = sum(1 for b in bones
                                  if b.scale >= BIG_SCALE or 0 < b.scale <= 1 / BIG_SCALE)
    except fbs.Refused as exc:
        rec["bones_error"] = str(exc)
    rec["placement_scaled"] = fbs.placement_scales(doc)
    return rec


def basis_of(m):
    """stock, max_inches, upm1000, other or unknown."""
    upm = m.get("upm")
    if not upm:
        return "unknown"
    up = m.get("up") or (0, 1, 0)
    if abs(upm - STOCK_UPM) < 1e-3 and abs(up[1] - 1) < 1e-3:
        return "stock"
    if abs(upm - 1000) < 1e-3:
        return "upm1000"
    if abs(upm - INCH_UPM) < 1e-2:
        return "max_inches"
    return "other"


def world_fixes(m):
    """The world-size fixes a file needs: basis (a raw 3ds Max export), upm1000, bone100 (a root
    bone scaled by 10 or more in the stock basis: tools/fix_bone_scale.py's case), root_scaled
    (the same in a raw export, to look at after its conversion), placement; [] for none. Helper
    bones scaled under an unscaled root are counted (scaled_bones) but are not a fix."""
    out = []
    b = basis_of(m)
    if b in ("max_inches", "other"):
        out.append("basis")
    elif b == "upm1000":
        out.append("upm1000")
    if (m.get("root_scale") or 1) >= BIG_SCALE:
        out.append("bone100" if b == "stock" else "root_scaled")
    if m.get("placement_scaled"):
        out.append("placement")
    return out


def stock_extent(m):
    """The largest side in stock units (0.615 per metre): what the engine draws for a file in the
    stock basis or in 3ds Max inches. A file declaring 1000 per metre is drawn as if in inches
    (docs/game-formats.md, "Scale"), so it is scaled like one."""
    size, upm = m.get("size"), m.get("upm")
    if not size or not upm:
        return None
    upm = INCH_UPM if abs(upm - 1000) < 1e-3 else upm
    return round(max(size) * STOCK_UPM / upm, 3)


# --------------------------------------------------------------------------------------------------
# Textures

def split_texture(stored):
    """(art folder key or None, stem without the suffix, extension, suffix digits or None) of a
    stored texture name."""
    p = str(stored).replace("/", "\\")
    base = p.rsplit("\\", 1)[-1]
    stem, ext = os.path.splitext(base)
    if ext.lower() not in IMAGE_EXT:
        stem, ext = base, ""
    m = SUFFIX_RE.search(stem)
    suffix = ",".join(m.groups()) if m else None
    if m:
        stem = stem[:m.start()]
    low = p.lower()
    i = low.rfind("\\art\\")
    folder = None
    if i >= 0:
        folder = norm(os.path.dirname(p[i + 5:]))
    elif low.startswith("art\\"):
        folder = norm(os.path.dirname(p[4:]))
    elif ":" not in p and not p.startswith("\\") and "\\" in p:
        folder = norm(os.path.dirname(p))
    return folder, stem, ext.lower(), suffix


def ddt_digits(head):
    """'usage,alpha,format,mips' of a .ddt's first 8 bytes, or None."""
    if not head or len(head) < 8 or head[:4] != b"RTS3":
        return None
    return ",".join(str(b) for b in head[4:8])


def texture_info(art, stored, model):
    folder, stem, ext, suffix = split_texture(stored)
    home = os.path.dirname(model)
    lstem = stem.lower()
    tries = []
    if folder is not None:
        tries.append((join_key(folder, lstem + ".ddt"), "art path"))
    tries.append((join_key(home, lstem + ".ddt"), "model folder"))
    found, how = None, "missing"
    for key, why in tries:
        if key and art.exists(key):
            found, how = key, why
            break
    if found is None:
        cands = art.by_stem.get(lstem, [])
        loose = [k for k in cands if k in art.loose]
        if cands:
            found = (loose or cands)[0]
            how = f"same name elsewhere ({len(cands)})"
    digits = ddt_digits(art.read(found, 8)) if found else None
    sources = []
    where = os.path.dirname(found) if found else home
    for k in art.by_folder.get(where, []):
        s, e = os.path.splitext(os.path.basename(k))
        if e in SOURCE_EXT and SUFFIX_RE.sub("", s) == lstem:
            sources.append(os.path.basename(art.loose[k]))
    return {"stored": stored, "ext": ext, "suffix": suffix, "stem": stem,
            "art_folder": folder, "resolved": found, "how": how,
            "resolved_status": art.status(found) if found else "missing",
            "header": digits, "usual": USUAL.get(digits or "", ""), "sources": sorted(sources)}


def texture_need(textures):
    """needed (a .tga without the suffix), ask (only .png/.jpg/.ddt/other names without it),
    ok (every name carries it) or none (no texture)."""
    if not textures:
        return "none"
    missing = [t for t in textures if not t["suffix"]]
    if not missing:
        return "ok"
    return "needed" if any(t["ext"] == ".tga" for t in missing) else "ask"


# --------------------------------------------------------------------------------------------------
# The survey

def hc_label(rel, civ):
    stem = os.path.splitext(os.path.basename(rel[:-4] if rel.lower().endswith(".xmb") else rel))[0]
    where = os.path.dirname(rel)
    return (civ or stem[8:] or stem) + ("" if where.lower() == "data" else f" [{where}]")


def survey(game, target, caches=(), bridge=None, world_index=True):
    art = Art(os.path.join(game, "art"))
    cache = {}
    hcs = []
    for rel, full in homecity_files(game):
        with open(full, "rb") as fh:
            text = decode_text(fh.read())
        info = hc_refs(text)
        kind = "civ" if info["civ"] else ("table" if info["root"] in HC_TABLES else "other")
        hc = {"file": rel, "civ": info["civ"], "kind": kind, "label": hc_label(rel, info["civ"]),
              "refs": [], "top": None}
        starts = []
        for r in info["refs"]:
            key, base = resolve_hc(art, r)
            r = dict(r, key=key, resolved=base)
            hc["refs"].append(r)
            if key is None or base == "missing":
                continue
            if r["tag"] == "visual" and r["base"] == "homecity" and hc["top"] is None:
                hc["top"] = key
            if key.endswith(".gr2"):
                continue
            starts.append(key)
        hc["anims"] = walk(art, starts, cache)
        hcs.append(hc)
    labels = collections.Counter(hc["label"] for hc in hcs)
    for hc in hcs:                       # two files of one civ (a revolution, a campaign copy)
        if labels[hc["label"]] > 1:
            stem = os.path.splitext(os.path.basename(hc["file"]))[0]
            hc["label"] += f" ({stem})"

    # every Granny file reached, with who names it
    files = {}
    for hc in hcs:
        for akey, info in hc["anims"].items():
            for r in info["refs"]:
                if r["kind"] not in ("model", "anim"):
                    continue
                k = model_key(r["value"])
                f = files.setdefault(k, {"key": k, "kind": r["kind"], "hcs": set(), "named_by": set(),
                                         "lines": []})
                f["hcs"].add(hc["label"])
                f["named_by"].add(akey)
                f["lines"].append((r["variant"], r["line"], r["value"]))
                f["depth"] = min(f.get("depth", 99), info["depth"])
        for r in hc["refs"]:
            if r["key"] and r["key"].endswith(".gr2"):
                f = files.setdefault(r["key"], {"key": r["key"], "kind": "pathdata", "hcs": set(),
                                                "named_by": set(), "lines": []})
                f["hcs"].add(hc["label"])
                f["named_by"].add(hc["file"])
                f["lines"].append((hc["file"], r["line"], r["value"]))
                f["depth"] = 0
    reached_anims = {a for hc in hcs for a in hc["anims"]}

    # anim files outside the home cities that name the same files
    world = collections.defaultdict(set)
    if world_index:
        pat = re.compile(r"<file>\s*([^<]+?)\s*</file>", re.I)
        for key, full in art.loose.items():
            if not (key.endswith(".xml") or key.endswith(".xml.xmb")):
                continue
            akey = key[:-4] if key.endswith(".xmb") else key
            if akey in reached_anims:
                continue
            try:
                with open(full, "rb") as fh:
                    raw = fh.read()
                text = decode_text(raw) if key.endswith(".xmb") or raw[:2] in (b"\xff\xfe", b"\xfe\xff") \
                    else raw.decode("utf-8", errors="replace")
            except Exception:                                  # noqa: BLE001
                continue
            for value in pat.findall(blank_comments(text)):
                k = model_key(value)
                if k in files:
                    world[k].add(akey)

    rows, texrows = [], []
    for k in sorted(files):
        f = files[k]
        status = art.status(k)
        # an anim file under homecity\ that no home city reaches is a leftover, not a use elsewhere
        others = world.get(k, set())
        outside = sorted(a for a in others if not a.startswith("homecity\\"))
        row = {"path": art.display(k) if status != "missing" else k, "key": k, "kind": f["kind"],
               "status": status, "homecities": sorted(f["hcs"]), "named_by": sorted(f["named_by"]),
               "lines": f["lines"], "depth": f.get("depth", 0), "world_refs": outside,
               "unreached_refs": sorted(others - set(outside)), "hc_only": not outside}
        if status in ("mod", "override"):
            data = art.read(k)
            raw, how = raw_bytes(data, caches, bridge)
            row["compressed"] = how != "raw"
            row["read"] = how
            if raw is not None:
                try:
                    row.update(measure(raw))
                except Exception as exc:                       # noqa: BLE001
                    row["error"] = f"{type(exc).__name__}: {exc}"[:200]
            row["basis"] = basis_of(row)
            row["world_fix"] = world_fixes(row) if "upm" in row else ["not measured"]
            row["stock_extent"] = stock_extent(row)
            tex = [texture_info(art, t, k) for t in row.get("textures", [])]
            row["texture_info"] = tex
            row["texture_fix"] = texture_need(tex) if "textures" in row else "not measured"
            for t in tex:
                texrows.append(dict(t, model=row["path"]))
        rows.append(row)

    for hc in hcs:
        hc["root_folder"] = os.path.dirname(hc["top"]) if hc["top"] else None
        hc["target"] = join_key(norm(target), hc["civ"] or hc["label"]) if hc["kind"] == "civ" else None
    by_label = {hc["label"]: hc for hc in hcs}
    for row in rows:
        if row["status"] not in ("mod", "override"):
            continue
        targets = [by_label[h]["target"] for h in row["homecities"] if by_label[h]["target"]]
        civ_hcs = [h for h in row["homecities"] if by_label[h]["kind"] == "civ"]
        row["under_target"] = any(row["key"].startswith(t + "\\") for t in targets)
        row["under_option_b"] = row["key"].startswith(norm(option_b(target)) + "\\")
        row["shared"] = len({by_label[h]["civ"] for h in civ_hcs}) > 1
        if not row["hc_only"]:
            row["move"] = "no (used outside the home cities)"
        elif row["under_target"]:
            row["move"] = "no (already there)"
        elif not civ_hcs:
            row["move"] = "ask (only a shared table names it)"
        elif row["shared"]:
            row["move"] = "ask (shared by several home cities)"
        else:
            row["move"] = "yes"
    return {"game": game, "target": target, "homecities": hcs, "files": rows,
            "textures": texrows, "art": art}


# --------------------------------------------------------------------------------------------------
# Reports

def _fmt(v):
    if isinstance(v, (list, tuple, set)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, float):
        return f"{v:.6g}"
    return "" if v is None else str(v)


MODEL_COLS = ("path", "kind", "status", "homecities", "hc_only", "world_refs", "unreached_refs",
              "depth", "read",
              "art_tool", "upm", "up", "basis", "root_name", "root_scale", "max_bone_scale",
              "scaled_bones", "placement_scaled", "size", "stock_extent", "tris", "animations",
              "world_fix", "texture_fix", "move", "under_target", "under_option_b", "shared",
              "named_by", "error")
TEX_COLS = ("model", "stored", "ext", "suffix", "resolved", "how", "resolved_status", "header",
            "usual", "sources")


def write_reports(res, out):
    os.makedirs(out, exist_ok=True)
    own = [r for r in res["files"] if r["status"] in ("mod", "override")]
    with open(os.path.join(out, "models.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(MODEL_COLS + ("textures", "resolved", "headers", "references"))
        for r in own:
            tex = r.get("texture_info", [])
            refs = [f"{a}:{n}" for a, n, _v in r["lines"]]
            w.writerow([_fmt(r.get(c)) for c in MODEL_COLS]
                       + [_fmt(t["stored"] for t in tex), _fmt(t["resolved"] for t in tex),
                          _fmt(t["header"] for t in tex), _fmt(refs)])
    with open(os.path.join(out, "textures.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(TEX_COLS)
        for t in res["textures"]:
            w.writerow([_fmt(t.get(c)) for c in TEX_COLS])
    with open(os.path.join(out, "refs.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(("homecity", "file", "line", "tag", "value", "resolves to", "how", "depth"))
        for hc in res["homecities"]:
            for r in hc["refs"]:
                w.writerow((hc["label"], hc["file"], r["line"], r["tag"], r["value"], r["key"],
                            r["resolved"], ""))
            for akey, info in sorted(hc["anims"].items()):
                for r in info["refs"]:
                    w.writerow((hc["label"], r["variant"], r["line"], r["kind"], r["value"],
                                model_key(r["value"]) if r["kind"] in ("model", "anim") else "",
                                r["where"], info["depth"]))
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary(res))
    slim = {"game": res["game"], "target": res["target"],
            "homecities": [{k: v for k, v in hc.items() if k != "anims"} | {
                "anims": {a: {"depth": i["depth"], "variants": i["variants"], "error": i["error"]}
                          for a, i in hc["anims"].items()}} for hc in res["homecities"]],
            "files": res["files"]}
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=1, default=lambda o: sorted(o) if isinstance(o, set) else str(o))


def counts(rows):
    c = collections.Counter()
    for r in rows:
        c["files"] += 1
        c["models"] += r["kind"] != "anim"
        for f in r.get("world_fix", []):
            c["world:" + f] += 1
        if not r.get("world_fix"):
            c["world:none"] += 1
        c["tex:" + r.get("texture_fix", "?")] += 1
        c["move:" + r.get("move", "?").split(" ")[0]] += 1
        c["override"] += r["status"] == "override"
    return c


def summary(res):
    own = [r for r in res["files"] if r["status"] in ("mod", "override")]
    lines = ["# Home-city models", "",
             f"Game copy: `{res['game']}`. Target tree: `art\\{res['target']}\\<civ>\\`.", "",
             f"- home-city files: {len(res['homecities'])} "
             f"({sum(h['kind'] == 'civ' for h in res['homecities'])} with a civ)",
             f"- Granny files reached: {len(res['files'])} "
             f"({sum(r['kind'] != 'anim' for r in res['files'])} models); "
             f"the mod's own: {len(own)} ({sum(r['status'] == 'override' for r in own)} override "
             f"stock names); missing: {sum(r['status'] == 'missing' for r in res['files'])}",
             f"- of the mod's own, used outside the home cities too: "
             f"{sum(not r['hc_only'] for r in own)}", ""]
    c = counts(own)
    lines += ["| fix | files |", "|---|---:|"]
    for k in sorted(c):
        lines.append(f"| {k} | {c[k]} |")
    lines += ["", "## Per home city", "",
              "world: basis = raw 3ds Max export (inches, Z up), upm1000 = declares 1000 units per "
              "metre, bone100 = root bone scaled >= 10 in the stock basis, root_scaled = the same in a raw export. tex needed = a .tga name without the "
              "(u,a,f,m) suffix; ask = only .png/.jpg/.ddt names. move: yes / ask (shared) / no "
              "(already there, or used outside the home cities).", "",
              "| home city | file | own files | basis | upm1000 | bone100 | root_scaled | world ok "
              "| tex needed | tex ask | move yes | move ask | no move | not measured |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for hc in sorted(res["homecities"], key=lambda h: h["label"].lower()):
        rows = [r for r in own if hc["label"] in r["homecities"]]
        if not rows:
            continue
        c = counts(rows)
        lines.append(f"| {hc['label']} | `{hc['file']}` | {len(rows)} | {c['world:basis']} | "
                     f"{c['world:upm1000']} | {c['world:bone100']} | {c['world:root_scaled']} | {c['world:none']} | "
                     f"{c['tex:needed']} | {c['tex:ask']} | {c['move:yes']} | {c['move:ask']} | "
                     f"{c['move:no']} | {c['world:not measured']} |")
    missing = [r for r in res["files"] if r["status"] == "missing"]
    if missing:
        lines += ["", "## Missing files", ""]
        for r in missing:
            lines.append(f"- `{r['key']}` ({r['kind']}), named by "
                         + ", ".join(f"`{a}`" for a in r["named_by"]))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------
# The plan for one home city

def _new_stored(stored, new_key, suffix):
    """The stored texture name for a texture moved to new_key (a .ddt key), keeping the stored
    prefix up to "\\art\\" and naming a .tga with the suffix."""
    p = str(stored).replace("/", "\\")
    i = p.lower().rfind("\\art\\")
    prefix = p[:i + 5] if i >= 0 else "art\\"
    stem = os.path.splitext(new_key)[0]
    return prefix + stem + (f".({suffix})" if suffix else "") + ".tga"


def _with_suffix(stored, suffix):
    """The stored name in its own folder, as a .tga with the (u,a,f,m) suffix."""
    p = str(stored)
    cut = max(p.rfind("\\"), p.rfind("/")) + 1
    stem = split_texture(p)[1]
    return p[:cut] + stem + f".({suffix}).tga"


def option_b(target):
    """The other tree a target can mean: <Mod>\\homecity -> homecity\\<Mod> (below art)."""
    parts = target.replace("/", "\\").strip("\\").split("\\")
    return "homecity\\" + parts[0] if len(parts) == 2 and parts[1].lower() == "homecity" else target


def plan(res, which):
    """Markdown: the proposed changes for one home city (matched on civ, label or file stem)."""
    art = res["art"]
    w = which.lower()
    hcs = [h for h in res["homecities"]
           if h["kind"] == "civ" and w in ((h["civ"] or "").lower(), h["label"].lower(),
                                           os.path.splitext(os.path.basename(h["file"]))[0].lower())]
    if not hcs:
        raise SystemExit(f"no home city named {which}")
    main = next((h for h in hcs if h["file"].lower().startswith("data")), hcs[0])
    civ = main["civ"]
    labels = {h["label"] for h in res["homecities"] if h["civ"] == civ}
    root = main["root_folder"] or ""
    spell_a = res["target"] + "\\" + civ
    spell_b = option_b(res["target"]) + "\\" + civ

    def new_rel(key):
        if root and key.startswith(root + "\\"):
            return art.display(key)[len(root) + 1:] if key in art.loose else key[len(root) + 1:]
        disp = art.display(key) if key in art.loose else key
        parts = disp.replace("/", "\\").split("\\")
        return "_from_" + parts[0].replace(" ", "_") + "\\" + "\\".join(parts[1:])

    rows = [r for r in res["files"] if r["status"] in ("mod", "override") and labels & set(r["homecities"])]
    movers = [r for r in rows if r.get("move") == "yes"]
    moved_files = {}                                  # old key -> new rel (below the civ folder)
    for r in movers:
        moved_files[r["key"]] = new_rel(r["key"])
    # anim files of the home city that live in its own folder
    anims = {}
    for h in res["homecities"]:
        if h["label"] in labels:
            anims.update(h["anims"])
    for akey, info in anims.items():
        for vkey, where in info["variants"]:
            if where == "loose" and root and vkey.startswith(root + "\\"):
                moved_files[vkey] = new_rel(vkey)
    # textures of the movers
    tex_moves, tex_renames, tex_kept = {}, [], []
    users = collections.defaultdict(set)
    for r in res["files"]:
        for t in r.get("texture_info", []):
            if t["resolved"]:
                users[t["resolved"]].add(r["key"])
    for r in movers:
        for t in r.get("texture_info", []):
            k = t["resolved"]
            if k and art.status(k) == "mod" and users[k] <= set(moved_files):
                if k not in tex_moves:
                    tex_moves[k] = new_rel(k)
            elif k:
                tex_kept.append((r["key"], t, "used by files that stay" if art.status(k) == "mod"
                                 else f"{art.status(k)} texture"))
            if k in tex_moves:
                new = _new_stored(t["stored"], spell_a + "\\" + tex_moves[k], t["header"])
            elif t["header"]:
                new = _with_suffix(t["stored"], t["header"]) + "  (stays)"
            else:
                new = "(no texture found: unchanged)"
            tex_renames.append((r, t, k, new))
    out = [f"# Pilot plan: {civ}", "",
           "Proposed, not applied. Option A is the tree as written in the request, "
           f"`art\\{spell_a}\\`; option B is the existing tree `art\\{spell_b}\\`. Below, a new path "
           "is given for A; for B replace the first two folders.", "",
           f"- home-city files: " + ", ".join(f"`{h['file']}`" for h in hcs),
           f"- its folder today: `art\\{root}`" if root else "- no folder of its own",
           f"- the mod's own Granny files it reaches: {len(rows)}; to move: {len(movers)}; "
           f"not moved: {len(rows) - len(movers)}", ""]
    out += ["## 1. Granny files", "",
            "| # | old path (below art) | new path (option A) | world fix | texture names |",
            "|---:|---|---|---|---|"]
    for i, r in enumerate(movers, 1):
        out.append(f"| {i} | `{r['path']}` | `{spell_a}\\{moved_files[r['key']]}` | "
                   f"{', '.join(r['world_fix']) or 'none'} | {r['texture_fix']} |")
    stay = [r for r in rows if r.get("move") != "yes"]
    if stay:
        out += ["", "Not moved:", ""]
        for r in stay:
            out.append(f"- `{r['path']}`: {r.get('move')}"
                       + (f" (also `{'`, `'.join(r['world_refs'][:3])}`)" if r["world_refs"] else ""))
    out += ["", "## 2. Textures (.ddt) moved with them", "",
            "| old path | new path (option A) | header | source images beside it |", "|---|---|---|---|"]
    for k, rel in sorted(tex_moves.items()):
        srcs = []
        for t in (t for r in movers for t in r.get("texture_info", []) if t["resolved"] == k):
            srcs = t["sources"]
            hdr = t["header"]
            break
        out.append(f"| `{art.display(k)}` | `{spell_a}\\{rel}` | ({hdr}) | {', '.join(srcs) or '-'} |")
    if tex_kept:
        out += ["", "Textures not moved (another file still uses them, or they are stock):", ""]
        seen = set()
        for _mk, t, why in tex_kept:
            if t["resolved"] in seen:
                continue
            seen.add(t["resolved"])
            out.append(f"- `{art.display(t['resolved'])}`: {why}")
    out += ["", "## 3. Stored texture names inside the .gr2 (`rebake --rename`, longer names "
            "allowed)", "",
            "The new name keeps the stored prefix up to `\\art\\`, points at the moved .ddt and "
            "carries the .ddt's header as the (u,a,f,m) suffix of a .tga name. Whether the suffix "
            "goes in the stored name is question 1.", "",
            "| model | old stored name | new stored name | resolves today to | how |",
            "|---|---|---|---|---|"]
    for r, t, k, new in tex_renames:
        out.append(f"| `{os.path.basename(r['path'])}` | `{t['stored']}` | `{new}` | "
                   f"`{art.display(k) if k else 'MISSING'}` | {t['how']} |")
    out += ["", "## 4. Anim files moved (the home city's own folder)", ""]
    for k in sorted(x for x in moved_files if not x.endswith(".gr2")):
        out.append(f"- `{art.display(k)}` -> `{spell_a}\\{moved_files[k]}`")
    out += ["", "## 5. XML lines that change", "",
            "Anim files: `<file>` paths are relative to art, without extension. Line numbers are "
            "those of the file today.", ""]
    for akey in sorted(anims):
        for r in anims[akey]["refs"]:
            if r["kind"] not in ("model", "anim", "include"):
                continue
            k = model_key(r["value"]) if r["kind"] != "include" else join_key("", r["value"])
            if k not in moved_files:
                continue
            new = spell_a + "\\" + moved_files[k]
            if r["kind"] != "include":
                new = new[:-4] if new.lower().endswith(".gr2") else new
            out.append(f"- `{r['variant']}` line {r['line']} ({r['kind']}): `{r['value']}` -> `{new}`")
    out += ["", "Home-city files: a top-level visual is relative to art\\homecity\\. Option A needs "
            "`..\\` (to verify in game); option B does not.", ""]
    for h in res["homecities"]:
        for r in h["refs"]:
            if r["key"] and (r["key"] in moved_files or r["key"] + ".xmb" in moved_files):
                rel = moved_files.get(r["key"]) or moved_files[r["key"] + ".xmb"]
                if r["resolved"].startswith("homecity"):
                    a = "..\\" + spell_a + "\\" + rel
                    b = spell_b[len("homecity\\"):] + "\\" + rel if spell_b.lower().startswith(
                        "homecity\\") else "..\\" + spell_b + "\\" + rel
                else:
                    a, b = spell_a + "\\" + rel, spell_b + "\\" + rel
                out.append(f"- `{h['file']}` line {r['line']} `<{r['tag']}>`: `{r['value']}` -> "
                           f"A `{a}` / B `{b}`")
    others = sorted({a for r in movers for a in r["world_refs"] + r["unreached_refs"]})
    if others:
        out += ["", "Other anim files that name a moved file (no home city reaches those under "
                "homecity\\):", ""] + [f"- `{a}`" for a in others]
    if root:
        moved = set(moved_files) | set(tex_moves)
        left = sorted(k for k in art.loose if k.startswith(root + "\\") and k not in moved)
        if left:
            out += ["", "## 6. Files left in the old folder", "",
                    "Loose files under the home city's folder that the plan does not move: shared "
                    "with another home city, or reached by nothing (to delete or move: ask).", ""]
            kept = {r["key"] for r in stay} | {t["resolved"] for r in stay
                                                 for t in r.get("texture_info", [])}
            for k in left:
                why = "used by a file that stays" if k in kept else "reached by nothing"
                out.append(f"- `{art.display(k)}` ({why})")
    out += ["", "## 7. Original paths of the moved files", ""]
    for k in sorted(set(moved_files) | set(tex_moves)):
        out.append(f"- art\\{art.display(k)}")
    return "\n".join(out) + "\n"


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    def opts(name):
        return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]

    game, out = opt("--game"), opt("--out")
    if not game or not out or not opt("--target"):
        print(__doc__)
        return 2
    if os.path.commonpath([os.path.abspath(out), os.path.abspath(game)]) == os.path.abspath(game):
        raise SystemExit("--out must be outside the game copy")
    bridge = None
    if opt("--granny"):
        work = opt("--work")
        if not work or os.path.commonpath([os.path.abspath(work), os.path.abspath(game)]) == \
                os.path.abspath(game):
            raise SystemExit("--granny needs --work, a folder outside the game copy")
        bridge = (opt("--granny"), os.path.abspath(game), os.path.abspath(work))
    res = survey(game, opt("--target"), caches=opts("--cache"), bridge=bridge)
    write_reports(res, out)
    for which in opts("--plan"):
        with open(os.path.join(out, f"plan_{which.lower()}.md"), "w", encoding="utf-8") as fh:
            fh.write(plan(res, which))
    print(summary(res).split("## Per home city")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
