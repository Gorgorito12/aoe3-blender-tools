# SPDX-License-Identifier: GPL-3.0-or-later
"""Moves one home city's own models into a folder of their own, as tools/hc_survey.py plans it:
writes the result as a stage folder in the game's layout, then installs it into a test copy and
takes it back out.

    python -I tools\\hc_move.py stage --game <copy> --civ <civ> --target "<Mod>\\homecity"
        --out <stage folder> --granny <bridge.exe> [--form A|B] [--shared _shared]
        [--cache <survey cache> ...] [--work <folder>] [--recompress <tools/recompress_models.py>]
        [--convert] [--suffix] [--reencoded <tools/reencode_textures.py report.json>]
    python -I tools\\hc_move.py install --bed <test copy> --stage <stage folder>
    python -I tools\\hc_move.py undo --bed <test copy>

What `stage` does, for the home city of <civ> (its data and campaign files):

- **Which files move.** The mod's own Granny models that only home cities use. One that a single
  civ's home cities use goes to <tree>\\<Civ>\\; one that several civs' home cities use goes to
  <tree>\\<shared>\\. The tree is <target> (form A: art\\<Mod>\\homecity, the home-city files then
  name it with ..\\, which the game accepts: in game 2026-11-17) or its other reading (form B:
  art\\homecity\\<Mod>). A model that replaces a stock one, or that anything outside the home
  cities uses, stays. Each keeps its path below the home city's own folder. The anim files of
  that folder move the same way, and a .ddt moves with the models when every model that uses it
  moves, or with the anim files that name it (<replacetexture>), to the shared folder if any of
  them goes there.
- **The models.** Each moved model is rebuilt by the bridge (`rebake --rename --grow`): every
  stored texture name that points at a moved .ddt follows it, keeping its form; a name that
  resolves to nothing is left as it is and listed. A model with nothing to change is copied as it
  is. Each result is read back: its names, and that every new name resolves in the moved layout.
  With --recompress, each rebuilt model is compressed again (tools/recompress_models.py), with
  each section in its original's format when the sections kept their sizes, else Oodle1.
- **--suffix** renames each moved .ddt that only .tga/.png/.jpg stored names reach to
  <name>.(u,a,f,m).ddt, the digits the header it ships with (see --reencoded), and writes those stored
  names <name>.(u,a,f,m).tga: the game drops only the last extension of a stored name, so it
  reads them as that .ddt (in game, 2026-11-17). A .ddt that a stored .ddt name or an anim file
  (<replacetexture>, a decal) names keeps its name, and the report lists it.
- **--reencoded** takes the textures tools/reencode_textures.py re-encoded (its report.json,
  made from this game copy): a moved .ddt that is still the file it was made from ships as its
  re-encoded copy, and its suffix states the new header. Re-encoding comes before the suffix, so
  a name never states an old header. A re-encoded texture that does not move, or whose name
  already carries a suffix, is left as it was and the report lists it.
- **Run "_tables" as the civ** to move the models that only the shared tables name (props,
  proto units) to the shared folder. Files already below the tree are never moved again.
- **--convert** (off) also puts a raw 3ds Max export into the stock basis (`rebake --convert`).
  In game (2026-11-17) the converted models of a home city were drawn misplaced and out of
  scale: conversion does not keep what the game draws there.
- **The references.** Every home-city file and every loose anim file (plain or compiled) that
  names a moved file is edited on that line only: visuals, includes, models, animations and
  textures. A home-city path relative to art\\homecity\\ gets ..\\ in form A.

The stage holds files\\ (the new and edited files at their game paths), originals.zip (every
file it replaces or moves, at its game path), moved-files.txt (old -> new, one per line),
stage.json (what install does) and report.md. Nothing in the game copy is written.

`install` checks that every file the stage replaces or moves is the one the stage was made
from (SHA-256), keeps a copy of each under <bed>\\hc-move-backup\\<stamp>\\ with a manifest,
copies the stage in and deletes the moved originals. `undo` puts the last install back and
checks every file by hash. Both refuse a Steam folder.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hc_survey as hs  # noqa: E402
import xmbedit  # noqa: E402

DEFAULT_PREFIX = "C:\\Program Files (x86)\\Microsoft Games\\Age of Empires 3\\art\\"
BACKUP = "hc-move-backup"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def refuse_steam(folder):
    if "steamapps" in os.path.abspath(folder).lower():
        raise SystemExit(f"refused: {folder} is a Steam folder; use a test copy")


# --------------------------------------------------------------------------------------------------
# The plan

def trees(target, form):
    """(tree spelled below art) for form A (the target) or B (its other reading)."""
    t = target.replace("/", "\\").strip("\\")
    return t if form == "A" else hs.option_b(t)


def civ_homecities(res, civ):
    w = civ.lower()
    hcs = [h for h in res["homecities"] if h["kind"] == "civ" and (h["civ"] or "").lower() == w]
    if not hcs:
        raise SystemExit(f"no home city of civ {civ}")
    return hcs


TABLES = "_tables"
SUFFIXABLE = (".tga", ".png", ".jpg", ".jpeg")


def anim_texture_refs(art):
    """{ddt key: [anim files]} of every texture any loose anim file names (<texture>,
    <replacetexture>), read cheaply: such a .ddt keeps its name."""
    import re
    pat = re.compile(r"<(?:texture|to|from)>\s*([^<]+?)\s*</", re.I)
    out = {}
    for key, full in art.loose.items():
        if not (key.endswith(".xml") or key.endswith(".xml.xmb")):
            continue
        try:
            with open(full, "rb") as fh:
                raw = fh.read()
            text = hs.decode_text(raw) if key.endswith(".xmb") else raw.decode("utf-8", "replace")
        except Exception:                                  # noqa: BLE001
            continue
        for value in pat.findall(text):
            k = hs.join_key("", value)
            if k:
                out.setdefault(k if k.endswith(".ddt") else k + ".ddt", []).append(key)
    return out


def load_reencoded(report, game):
    """{art key: {"sha256", "path", "digits"}} of the textures a tools/reencode_textures.py report
    re-encoded, keyed by their place in the game copy's art folder."""
    with open(report, encoding="utf-8") as fh:
        rep = json.load(fh)
    art = os.path.join(os.path.abspath(game), "art")
    out = {}
    for r in rep["textures"]:
        if r.get("action") == "re-encoded" and r.get("output"):
            key = hs.norm(os.path.relpath(os.path.abspath(r["source"]), art))
            out[key] = {"sha256": r["sha256"], "path": r["output"], "digits": r["after"]}
    return out


def plan_moves(res, civ, target, form="A", shared="_shared", suffix=False, tex_refs=None,
               reencoded=None):
    """{"civ", "tree", "root", "moves": {old key: new art path (spelled)}, "groups": {key: civ|
    shared}, "stay": [(key, why)], "left": [keys under the root that nothing reaches],
    "suffixed": {ddt key: digits}, "unsuffixed": [(ddt key, why)]}.

    civ "_tables": the models only the shared tables (props, proto units) name, to the shared
    folder. Files already below the tree are left where they are. With `suffix`, a moved .ddt
    that only .tga/.png/.jpg stored names reach is renamed <name>.(u,a,f,m).ddt (its real
    header); tex_refs: anim_texture_refs(art), the textures anim files name (they keep theirs)."""
    art = res["art"]
    tree = trees(target, form)
    tree_key = hs.norm(tree) + "\\"
    civ_of = {h["label"]: h["civ"] for h in res["homecities"] if h["kind"] == "civ"}
    if civ == TABLES:
        labels = {h["label"] for h in res["homecities"] if h["kind"] != "civ"}
        root = None
        civ_name = TABLES
    else:
        hcs = civ_homecities(res, civ)
        civ_name = hcs[0]["civ"]
        main = next((h for h in hcs if h["file"].lower().startswith("data")), hcs[0])
        root = main["root_folder"]
        labels = {h["label"] for h in hcs}
    dest = {"civ": tree + "\\" + civ_name, "shared": tree + "\\" + shared}

    def rel(key):
        disp = art.display(key)
        if root and key.startswith(root + "\\"):
            return disp[len(root) + 1:]
        return disp[len("homecity\\"):] if key.startswith("homecity\\") else disp

    groups, stay = {}, []
    rows = [r for r in res["files"] if r["status"] in ("mod", "override")
            and labels & set(r["homecities"]) and not r["key"].startswith(tree_key)]
    for r in rows:
        civs = {civ_of[h] for h in r["homecities"] if h in civ_of}
        if r["status"] == "override":
            stay.append((r["key"], "replaces a stock model"))
        elif not r["hc_only"]:
            stay.append((r["key"], "used outside the home cities: " + ", ".join(r["world_refs"][:3])))
        elif r["kind"] == "pathdata":
            stay.append((r["key"], "path data"))
        elif civ == TABLES:
            if not civs:
                groups[r["key"]] = "shared"
        elif not civs:
            stay.append((r["key"], "only a shared table names it (moved with the tables)"))
        else:
            groups[r["key"]] = "shared" if len(civs) > 1 else "civ"
    # anim files of the home city's folder, and which civs reach them
    if root:
        reach = {}
        for h in res["homecities"]:
            if h["kind"] != "civ":
                continue
            for info in h["anims"].values():
                for vkey, where in info["variants"][:1]:     # the twin the game reads
                    if where == "loose" and vkey.startswith(root + "\\"):
                        reach.setdefault(vkey, set()).add(h["civ"])
        for vkey, civs in reach.items():
            if civ_name in civs:
                groups[vkey] = "shared" if len(civs) > 1 else "civ"
    # textures that every user takes along: below the home city's folder, or in a folder whose
    # every loose model moves; never one an anim file outside these home cities names
    users = {}
    for r in res["files"]:
        for t in r.get("texture_info", []):
            if t["resolved"]:
                users.setdefault(t["resolved"], set()).add(r["key"])
    tex_refs = tex_refs or {}
    hc_anims = {v for h in res["homecities"] for info in h["anims"].values() for v, _w in info["variants"][:1]}

    def folder_moves(k):
        d = os.path.dirname(k)
        models = [x for x in art.by_folder.get(d, []) if x.endswith(".gr2")]
        return bool(models) and all(x in groups for x in models)

    def movable(k):
        if not k or art.status(k) != "mod" or k.startswith(tree_key):
            return False
        if any(a not in hc_anims for a in tex_refs.get(k, ())):
            return False
        return (root and k.startswith(root + "\\")) or folder_moves(k)

    for r in rows:
        if r["key"] not in groups:
            continue
        for t in r.get("texture_info", []):
            k = t["resolved"]
            if movable(k) and all(u in groups for u in users[k]):
                groups[k] = "shared" if any(groups[u] == "shared" for u in users[k]) else "civ"
    # textures of the folder that anim files name (<replacetexture>, decals)
    if root:
        named = {}
        for h in res["homecities"]:
            if h["kind"] != "civ":
                continue
            for info in h["anims"].values():
                for r in info["refs"]:
                    if r["kind"].startswith("texture"):
                        k = ref_key(r)
                        if k and k.startswith(root + "\\") and movable(k):
                            named.setdefault(k, set()).add(h["civ"])
        for k, civs in named.items():
            if civ_name not in civs or any(u not in groups for u in users.get(k, ())):
                continue
            groups[k] = "shared" if (len(civs) > 1 or groups.get(k) == "shared") else "civ"
    moves = {k: dest[g] + "\\" + rel(k) for k, g in groups.items()}
    # re-encoded textures: taken when the texture moves and is still the file it was made from
    applied, refused = {}, []
    mine = {t["resolved"] for r in rows for t in r.get("texture_info", [])} | set(moves)
    for k, e in sorted((reencoded or {}).items()):
        if k not in mine:
            continue
        if k not in moves:
            refused.append((k, "it does not move (left as it was)"))
        elif sha256(art.read(k)) != e["sha256"]:
            refused.append((k, "the file changed since it was re-encoded"))
        elif hs.SUFFIX_RE.search(os.path.splitext(os.path.basename(k))[0]):
            refused.append((k, "its name already carries a suffix, which would no longer be true"))
        else:
            applied[k] = e
    # the suffix: a moved .ddt that only .tga/.png/.jpg stored names of moved models reach; its
    # digits are the header it ships with (the re-encoded one when it was re-encoded)
    suffixed, unsuffixed = {}, []
    if suffix:
        exts, header = {}, {}
        for r in res["files"]:
            for t in r.get("texture_info", []):
                if t["resolved"] in moves:
                    exts.setdefault(t["resolved"], set()).add(t["ext"])
                    header[t["resolved"]] = applied[t["resolved"]]["digits"] \
                        if t["resolved"] in applied else t["header"]
        for k in sorted(moves):
            if not k.endswith(".ddt"):
                continue
            why = None
            if k not in exts:
                why = "no model stores its name (an anim file names it)"
            elif tex_refs.get(k):
                why = "an anim file names it: " + tex_refs[k][0]
            elif not exts[k] <= set(SUFFIXABLE):
                why = "a model stores it as " + "/".join(sorted(exts[k] - set(SUFFIXABLE)) or ["?"])
            elif not header.get(k):
                why = "no readable header"
            elif hs.SUFFIX_RE.search(os.path.splitext(os.path.basename(k))[0]):
                why = "already suffixed"
            if why:
                unsuffixed.append((k, why))
                continue
            new = moves[k]
            moves[k] = new[:-4] + f".({header[k]})" + new[-4:]
            suffixed[k] = header[k]
    taken = {}
    for k, new in moves.items():
        low = hs.norm(new)
        if low in taken or art.exists(low):
            raise SystemExit(f"two files would land on {new}: {art.display(k)} and "
                             f"{art.display(taken.get(low, low))}")
        taken[low] = k
    reached = set(moves) | {r["key"] for r in res["files"]} | hc_anims | set(users) | set(tex_refs)
    left = sorted(k for k in art.loose
                  if k.startswith(root + "\\") and k not in reached) if root else []
    return {"civ": civ_name, "form": form, "tree": tree, "root": root, "moves": moves,
            "groups": groups, "stay": stay, "left": left, "labels": sorted(labels),
            "suffixed": suffixed, "unsuffixed": unsuffixed, "reencoded": applied,
            "not_reencoded": refused}


# --------------------------------------------------------------------------------------------------
# Texture names

def new_texture_name(stored, info, moves, art, prefix, suffixed=None):
    """The stored name a moved model gets for one texture, or (None, why) to leave it. A name
    follows its moved .ddt and keeps its extension; a .tga/.png/.jpg name of a .ddt the plan
    renamed with its suffix (`suffixed`: {ddt key: digits}) becomes <name>.(u,a,f,m).tga, which
    the game reads as <name>.(u,a,f,m).ddt (it drops only the last extension)."""
    k = info["resolved"]
    if not k:
        return None, "resolves to nothing"
    if k not in moves:
        return None, "its .ddt stays where it is"
    p = str(stored).replace("/", "\\")
    i = p.lower().rfind("\\art\\")
    head = p[:i + 5] if i >= 0 else prefix
    folder = os.path.dirname(moves[k])
    stem = info["stem"]
    if suffixed and k in suffixed and info["ext"] in SUFFIXABLE:
        new = head + folder + "\\" + stem + f".({suffixed[k]}).tga"
    else:
        stem += f".({info['suffix']})" if info["suffix"] else ""
        new = head + folder + "\\" + stem + (p[p.rfind("."):] if info["ext"] else "")
    return (new, "") if new != p else (None, "unchanged")


def model_prefix(textures):
    for t in textures:
        p = str(t).replace("/", "\\")
        i = p.lower().rfind("\\art\\")
        if i >= 0:
            return p[:i + 5]
    return DEFAULT_PREFIX


def resolves_after(name, moved_layout_keys, art_exists):
    """Does a stored name resolve in the layout after the move, as the game reads it: the part
    after \\art\\, its last extension dropped, .ddt added?"""
    p = str(name).replace("/", "\\")
    i = p.lower().rfind("\\art\\")
    if i < 0:
        return False
    below = p[i + 5:]
    base = below.rsplit("\\", 1)[-1]
    stem = base[:base.rfind(".")] if "." in base else base
    key = hs.join_key(hs.norm(os.path.dirname(below)), stem.lower() + ".ddt")
    return key in moved_layout_keys or (art_exists(key) and key not in moved_layout_keys.removed)


class Layout(set):
    """The art keys present after the move: the new paths; `removed` holds the moved originals."""

    def __init__(self, new_keys, removed):
        super().__init__(new_keys)
        self.removed = set(removed)


# --------------------------------------------------------------------------------------------------
# Reference edits

def _decode(raw):
    """(text, how) of a plain XML file; how re-encodes it."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), ("utf-16", raw[:2])
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8"), ("utf-8", b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8"), ("utf-8", b"")
    except UnicodeDecodeError:              # an ANSI file (a mod's): latin-1 keeps every byte
        return raw.decode("latin-1"), ("latin-1", b"")


def _encode(text, how):
    enc, bom = how
    if enc == "utf-16":
        return text.encode("utf-16")
    return bom + text.encode(enc)


def edit_lines(text, changes):
    """text with each (line, old, new) applied: the first `old` on that line becomes `new`.
    Raises if a line does not hold its old value."""
    lines = text.split("\n")
    for line, old, new in changes:
        s = lines[line - 1]
        at = s.find(old)
        if at < 0:
            raise ValueError(f"line {line} does not hold {old!r}")
        lines[line - 1] = s[:at] + new + s[at + len(old):]
    return "\n".join(lines)


def _value(old_value, new_path):
    """new_path written as old_value was: with or without its extension."""
    ext = os.path.splitext(new_path)[1]
    if ext and not os.path.splitext(old_value.replace("\\", "/").rsplit("/", 1)[-1])[1]:
        return new_path[:-len(ext)]
    return new_path


def hc_value(ref, new_path):
    """A home-city reference to new_path, relative to the base it resolved from."""
    if ref["resolved"].startswith("homecity"):
        low = new_path.lower()
        return new_path[len("homecity\\"):] if low.startswith("homecity\\") else "..\\" + new_path
    return new_path


def ref_key(r):
    """The art key an anim file reference names."""
    if r["kind"] in ("model", "anim"):
        return hs.model_key(r["value"])
    if r["kind"] == "include":
        return hs.join_key("", r["value"])
    if r["kind"].startswith("texture"):
        k = hs.join_key("", r["value"])
        return k if k and k.endswith(".ddt") else (k + ".ddt" if k else None)
    return None


def anim_edits(text, moves):
    out = []
    for r in hs.anim_refs(text):
        k = ref_key(r)
        if k and k in moves:
            out.append((r["line"], r["value"], _value(r["value"], moves[k])))
    return out


def hc_edits(art, text, moves):
    out = []
    for r in hs.hc_refs(text)["refs"]:
        key, base = hs.resolve_hc(art, r)
        if base == "missing" or not key:
            continue
        r = dict(r, resolved=base)
        target = moves.get(key) or (moves.get(key + ".xmb", "")[:-4] or None)
        if target:
            out.append((r["line"], r["value"], hc_value(r, target)))
    return out


def edited_anim(raw, moves):
    """(new bytes, changes) of a loose anim file, plain or compiled; (None, []) if untouched."""
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        text = xmbedit.to_xml(elems, attrs, root)
        changes = anim_edits(text, moves)
        if not changes:
            return None, []
        new = edit_lines(text, changes)
        inner = xmbedit.encode(*xmbedit.from_xml(new.encode("utf-8")))
        return xmbedit.wrap(inner, xmbedit.is_compressed(raw)), changes
    text, how = _decode(raw)
    changes = anim_edits(hs.blank_comments(text), moves)
    if not changes:
        return None, []
    return _encode(edit_lines(text, changes), how), changes


# --------------------------------------------------------------------------------------------------
# The stage

def run_bridge(exe, install, src, out, convert, renames):
    args = [exe, "rebake", "--install", install, "--file", src, "--out", out, "--native-crc"]
    if convert:
        args.append("--convert")
    if renames:
        args.append("--grow")
        for old, new in renames:
            args += ["--rename", old, new]
    elif not convert:
        args.append("--noop")
    r = subprocess.run(args, cwd=os.path.dirname(out), capture_output=True, text=True,
                       timeout=300)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"bridge exit {r.returncode} on {src}: {r.stdout[-400:]} {r.stderr[-200:]}")
    return last


def runtime_opens(exe, install, path):
    """Does the game's Granny runtime open the file (bridge `info`)? A valid CRC is not enough:
    a recompressed model can pass it and still be unreadable."""
    try:
        r = subprocess.run([exe, "info", "--install", install, "--file", path], capture_output=True,
                           text=True, timeout=120, cwd=os.path.dirname(path))
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "Fatal error" not in r.stdout + r.stderr


def run_recompress(tool, install, src, out, like):
    """Compresses a rebuilt model again (tools/recompress_models.py): each section in the format
    the original stores it in (--like), or, when the rebuild changed the sections' sizes (a grown
    name), Oodle1 for every section that gets smaller. Returns how."""
    base = [sys.executable, "-I", tool, src, "-o", out, "--granny-install", install]
    r = subprocess.run(base + ["--like", like], capture_output=True, text=True, timeout=600)
    if r.returncode == 0 and os.path.exists(out):
        return "like the original"
    r = subprocess.run(base + ["--format", "oodle1"], capture_output=True, text=True, timeout=600)
    if "keep it uncompressed" in r.stdout + r.stderr and not os.path.exists(out):
        return None                       # the tool refuses an older type tag: ship it as it is
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"recompress failed on {src}: {r.stdout[-400:]} {r.stderr[-200:]}")
    return "oodle1 (the sections changed size)"


def stage(game, civ, target, out, bridge_exe, form="A", shared="_shared", caches=(),
          convert=False, suffix=False, recompress=None, rebake=None, work=None, reencoded=None,
          log=print):
    """Writes the stage folder. rebake(src, dst, convert, renames) -> record line replaces the
    bridge (tests); recompress: the path of tools/recompress_models.py, to compress each rebuilt
    model again; reencoded: load_reencoded(...), the re-encoded textures to ship in place of the
    moved originals."""
    if os.path.commonpath([os.path.abspath(out), os.path.abspath(game)]) == os.path.abspath(game):
        raise SystemExit("--out must be outside the game copy")
    bridge = (bridge_exe, os.path.abspath(game), os.path.abspath(work)) if work and bridge_exe else None
    res = hs.survey(game, target, caches=caches, bridge=bridge)
    art = res["art"]
    p = plan_moves(res, civ, target, form, shared, suffix=suffix,
                   tex_refs=anim_texture_refs(art) if suffix else None, reencoded=reencoded)
    moves = p["moves"]
    files = os.path.join(out, "files")
    work = os.path.join(out, "work")
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; give a new folder")
    os.makedirs(work)
    rows = {r["key"]: r for r in res["files"]}
    new_keys = {hs.norm(v) for v in moves.values()}
    layout = Layout(new_keys, moves)
    written, edited, notes = {}, {}, []

    def put(rel_game, data):
        path = os.path.join(files, rel_game)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        written[rel_game] = sha256(data)

    if rebake is None:
        def rebake(src, dst, conv, renames):
            return run_bridge(bridge_exe, os.path.abspath(game), src, dst, conv, renames)

    model_report = []
    for k, new in sorted(moves.items()):
        data = art.read(k)
        rel_new = "art\\" + new
        if k.endswith(".gr2") and k in rows:
            r = rows[k]
            prefix = model_prefix(r.get("textures", []))
            renames, kept = [], []
            for t in r.get("texture_info", []):
                name, why = new_texture_name(t["stored"], t, moves, art, prefix, p["suffixed"])
                if name:
                    if not resolves_after(name, layout, art.exists):
                        raise SystemExit(f"{art.display(k)}: {name} would resolve to nothing")
                    renames.append((t["stored"], name))
                else:
                    kept.append((t["stored"], why))
            conv = convert and r.get("basis") == "max_inches" and r["kind"] != "anim"
            if r.get("basis") in ("upm1000", "other", "unknown") and convert:
                notes.append(f"{art.display(k)}: basis {r.get('basis')} left as it is")
            if renames or conv:
                src = os.path.join(work, "in_" + os.path.basename(k))
                dst = os.path.join(work, "out_" + os.path.basename(k))
                with open(src, "wb") as fh:
                    fh.write(data)
                record = rebake(src, dst, conv, renames)
                with open(dst, "rb") as fh:
                    data = fh.read()
                check_model(data, renames, conv, r, caches)
                if recompress:
                    packed = dst + ".packed.gr2"
                    how = run_recompress(recompress, os.path.abspath(game), dst, packed, src)
                    if how is None:
                        record += " | recompressed: refused, the runtime cannot open the result"
                        notes.append(f"{art.display(k)}: left uncompressed (an older type tag: "
                                     "recompress_models.py refuses it, the runtime could not "
                                     "open it recompressed)")
                    elif bridge_exe and not runtime_opens(bridge_exe, os.path.abspath(game), packed):
                        # measured: models of type tag 0x80000010 came out unreadable (the
                        # game exits when it meets one); such a model ships uncompressed
                        record += " | recompressed: refused, the runtime cannot open the result"
                        notes.append(f"{art.display(k)}: left uncompressed (its recompressed "
                                     "copy does not open in the Granny runtime)")
                    else:
                        record += " | recompressed: " + how
                        with open(packed, "rb") as fh:
                            data = fh.read()
            else:
                record = "copied"
            model_report.append((art.display(k), new, conv, renames, kept, record))
            put(rel_new, data)
        else:
            if k.endswith(".xml") or k.endswith(".xmb"):
                new_data, changes = edited_anim(data, moves)
                if new_data is not None:
                    data = new_data
                    edited["art\\" + art.display(k)] = changes
            elif k in p["reencoded"]:
                with open(p["reencoded"][k]["path"], "rb") as fh:
                    data = fh.read()
                if hs.ddt_digits(data[:8]) != p["reencoded"][k]["digits"]:
                    raise SystemExit(f"{p['reencoded'][k]['path']} is not the re-encoded texture")
            put(rel_new, data)
    # files that stay but name a moved file
    stems = {os.path.basename(k).split(".")[0] for k in moves}
    for key, full in sorted(art.loose.items()):
        if key in moves or not (key.endswith(".xml") or key.endswith(".xml.xmb")):
            continue
        with open(full, "rb") as fh:
            raw = fh.read()
        low = raw.lower()
        if not any(s.encode() in low or s.encode("utf-16-le") in low for s in stems) \
                and not raw[:4] == b"l33t":
            continue
        new_data, changes = edited_anim(raw, moves)
        if new_data is not None:
            rel = "art\\" + os.path.relpath(full, art.root)
            put(rel, new_data)
            edited[rel] = changes
    for rel, full in hs.homecity_files(game):
        with open(full, "rb") as fh:
            raw = fh.read()
        if full.lower().endswith(".xmb"):
            continue
        text, how = _decode(raw)
        changes = hc_edits(art, text, moves)
        if changes:
            put(rel, _encode(edit_lines(text, changes), how))
            edited[rel] = changes
    # what install needs
    replaced = {}
    for rel in written:
        full = os.path.join(game, rel)
        if os.path.exists(full):
            with open(full, "rb") as fh:
                replaced[rel] = sha256(fh.read())
    removed = {}
    for k in moves:
        rel = "art\\" + art.display(k)
        with open(art.loose[k], "rb") as fh:
            removed[rel] = sha256(fh.read())
    with zipfile.ZipFile(os.path.join(out, "originals.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(set(replaced) | set(removed)):
            z.write(os.path.join(game, rel), rel)
    with open(os.path.join(out, "moved-files.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
        for k, new in sorted(moves.items(), key=lambda kv: art.display(kv[0]).lower()):
            fh.write(f"art\\{art.display(k)} -> art\\{new}\n")
    meta = {"civ": p["civ"], "form": form, "tree": p["tree"], "game": os.path.abspath(game),
            "written": written, "replaced": replaced, "removed": removed,
            "moves": {"art\\" + art.display(k): "art\\" + v for k, v in moves.items()},
            "reencoded": {"art\\" + art.display(k): e["digits"] for k, e in p["reencoded"].items()},
            "not_reencoded": {"art\\" + art.display(k): why for k, why in p["not_reencoded"]}}
    with open(os.path.join(out, "stage.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report(p, art, model_report, edited, notes))
    shutil.rmtree(work)
    log(f"stage: {len(moves)} files moved, {len(edited)} files edited, {len(written)} written "
        f"to {out}")
    return meta


def check_model(data, renames, converted, row, caches):
    """The rebuilt model: uncompressed, its names as asked, the stock basis when converted, and
    its size the old one scaled by the units ratio."""
    m = hs.measure(data)
    names = set(m["textures"])
    for old, new in renames:
        if new not in names or old in names:
            raise SystemExit(f"rebuilt model does not hold {new}")
    if converted:
        if hs.basis_of(m) != "stock":
            raise SystemExit(f"rebuilt model is not in the stock basis: {m.get('upm')}")
        a, b = hs.stock_extent(row), hs.stock_extent(m)
        if a and b and abs(a - b) > 1e-3 * max(a, 1):
            raise SystemExit(f"drawn size changed: {a} -> {b}")


def report(p, art, models, edited, notes):
    root = next((art.display(k)[:len(p["root"])] for k in art.loose
                 if k.startswith(p["root"] + "\\")), p["root"]) if p["root"] else "-"
    out = [f"# {p['civ']}: home-city models moved", "",
           f"Tree: `art\\{p['tree']}\\` (form {p['form']}). Old folder: `art\\{root}`.",
           "", "## Models", "", "| old | new | converted | names renamed | names left | written |",
           "|---|---|---|---:|---|---|"]
    for old, new, conv, ren, kept, rec in models:
        how = "copied as it was" if rec == "copied" else (
            "rebuilt" + (", recompressed " + rec.split("recompressed: ", 1)[1]
                         if "recompressed: " in rec else ", uncompressed"))
        out.append(f"| `{old}` | `{new}` | {'yes' if conv else 'no'} | {len(ren)} | "
                   + ("; ".join(f"`{n.rsplit(chr(92), 1)[-1]}` ({w})" for n, w in kept) or "-")
                   + f" | {how} |")
    out += ["", "## Stored texture names", ""]
    for old, _new, _c, ren, _k, _r in models:
        for a, b in ren:
            out.append(f"- `{old.rsplit(chr(92), 1)[-1]}`: `{a}` -> `{b}`")
    out += ["", "## Edited files", ""]
    for rel, changes in sorted(edited.items()):
        out.append(f"- `{rel}`: " + "; ".join(f"line {n}: `{a}` -> `{b}`" for n, a, b in changes))
    if p.get("reencoded") or p.get("not_reencoded"):
        out += ["", "## Re-encoded textures", "",
                f"{len(p['reencoded'])} moved textures ship re-encoded (tools/reencode_textures.py); "
                "their suffix states the new header.", ""]
        out += [f"- `{art.display(k)}`: ({e['digits']})" for k, e in sorted(p["reencoded"].items())]
        if p.get("not_reencoded"):
            out += ["", "Re-encoded but not used:", ""]
            out += [f"- `{art.display(k)}`: {why}" for k, why in p["not_reencoded"]]
    if p.get("suffixed") or p.get("unsuffixed"):
        out += ["", "## Suffix", "", f"{len(p['suffixed'])} textures renamed with their header; "
                f"{len(p['unsuffixed'])} keep their name:", ""]
        out += [f"- `{art.display(k)}`: {why}" for k, why in p["unsuffixed"]]
    out += ["", "## Not moved", ""]
    for k, why in p["stay"]:
        out.append(f"- `{art.display(k)}`: {why}")
    out += ["", "## Left in the old folder (no home city reaches them; kept, not deleted)", ""]
    out += [f"- `{art.display(k)}`" for k in p["left"]]
    if notes:
        out += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------
# Install and undo

def _hash_file(path):
    with open(path, "rb") as fh:
        return sha256(fh.read())


def install(bed, stage_dir, log=print):
    refuse_steam(bed)
    with open(os.path.join(stage_dir, "stage.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    for rel, h in list(meta["replaced"].items()) + list(meta["removed"].items()):
        full = os.path.join(bed, rel)
        if not os.path.exists(full) or _hash_file(full) != h:
            raise SystemExit(f"refused: {rel} in {bed} is not the file the stage was made from")
    for rel in meta["written"]:
        if rel not in meta["replaced"] and os.path.exists(os.path.join(bed, rel)):
            raise SystemExit(f"refused: {rel} already exists in {bed}")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    back = os.path.join(bed, BACKUP, stamp)
    n = 1
    while os.path.exists(back):         # two installs in one second: never share a backup
        back = os.path.join(bed, BACKUP, f"{stamp}-{n:02d}")
        n += 1
    manifest = {"stage": os.path.abspath(stage_dir), "backed_up": {}, "created": [], "dirs": []}
    for rel in sorted(set(meta["replaced"]) | set(meta["removed"])):
        dst = os.path.join(back, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(bed, rel), dst)
        manifest["backed_up"][rel] = _hash_file(dst)
    with open(os.path.join(back, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    for rel in sorted(meta["written"]):
        dst = os.path.join(bed, rel)
        d = os.path.dirname(dst)
        missing = []
        while not os.path.isdir(d):
            missing.append(d)
            d = os.path.dirname(d)
        for d in reversed(missing):
            os.makedirs(d)
            manifest["dirs"].append(os.path.relpath(d, bed))
        if rel not in meta["replaced"]:
            manifest["created"].append(rel)
        shutil.copyfile(os.path.join(stage_dir, "files", rel), dst)
        with open(os.path.join(back, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)
    for rel in meta["removed"]:
        if rel not in meta["written"]:
            os.remove(os.path.join(bed, rel))
    for rel, h in meta["written"].items():
        if _hash_file(os.path.join(bed, rel)) != h:
            raise SystemExit(f"{rel} did not copy right")
    log(f"install: {len(meta['written'])} written, {len(meta['removed'])} moved away; backup {back}")
    return back


def undo(bed, log=print):
    refuse_steam(bed)
    root = os.path.join(bed, BACKUP)
    stamps = sorted(os.listdir(root)) if os.path.isdir(root) else []
    if not stamps:
        raise SystemExit(f"nothing to undo in {bed}")
    back = os.path.join(root, stamps[-1])
    with open(os.path.join(back, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    for rel in manifest["created"]:
        full = os.path.join(bed, rel)
        if os.path.exists(full):
            os.remove(full)
    for rel, h in manifest["backed_up"].items():
        dst = os.path.join(bed, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(back, rel), dst)
        if _hash_file(dst) != h:
            raise SystemExit(f"{rel} did not come back right")
    for d in sorted(manifest["dirs"], key=len, reverse=True):
        full = os.path.join(bed, d)
        if os.path.isdir(full) and not os.listdir(full):
            os.rmdir(full)
    shutil.rmtree(back)
    if not os.listdir(root):
        os.rmdir(root)
    log(f"undo: {len(manifest['backed_up'])} restored and checked, {len(manifest['created'])} removed")


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    def opts(name):
        return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]

    cmd = argv[0] if argv else None
    if cmd == "stage" and opt("--game") and opt("--civ") and opt("--target") and opt("--out"):
        if not opt("--granny"):
            raise SystemExit("stage needs --granny <bridge.exe>")
        stage(opt("--game"), opt("--civ"), opt("--target"), opt("--out"), opt("--granny"),
              form=opt("--form", "A").upper(), shared=opt("--shared", "_shared"),
              caches=opts("--cache"), convert="--convert" in argv, work=opt("--work"),
              suffix="--suffix" in argv, recompress=opt("--recompress"),
              reencoded=load_reencoded(opt("--reencoded"), opt("--game")) if opt("--reencoded") else None)
        return 0
    if cmd == "install" and opt("--bed") and opt("--stage"):
        install(opt("--bed"), opt("--stage"))
        return 0
    if cmd == "undo" and opt("--bed"):
        undo(opt("--bed"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
