# SPDX-License-Identifier: GPL-3.0-or-later
"""Bakes the <replacetexture> blocks of anim files into copies of the models they swap textures
on, so that no anim file needs one any more: each copy stores the new texture names itself.

    python -I tools/bake_textures.py --manifest <file.tsv> --art <folder> [--art <folder> ...]
                                     --out <folder> [--prefix <stored prefix>] [--dry-run]
                                     [--granny <bridge.exe> --granny-install <game folder>]
                                     [--cache <folder>] [--building-names <regex on the copies' folder>]

The manifest has one line per anim file: its path below art (as a proto's <AnimFile> names it),
a tab, and the folder below art where its model copies go (`#` starts a comment). Paths named by
the anim files are looked up in the --art folders in the order given, loose files first, then
each folder's .bar archives: give the work tree first, then the mod's art, then the game's.

For each <assetreference type="GrannyModel"> of an anim file:
- the texture names the model stores are read (a compressed model through the bridge);
- a <replacetexture> whose <from> the model does not store changes nothing in game (seen in game,
  docs/game-formats.md): it is removed; so is one whose <to> texture is found nowhere (the game
  then shows the model's own texture, which the copy keeps);
- the other swaps make the copy: the model with those stored names pointing at the <to> textures
  (`C:\\art\\<to>.ddt` unless --prefix says otherwise; the game reads the part below art\\). One
  copy per source model and set of swaps, for the whole run: the same building used twice gets
  one file, in the folder of the first anim file that needs it. Its name is the stem of its new
  colour texture (the first new texture whose name does not end in _b, _bump, _normal), an
  underscore and the source model's stem (post_jesuit_house_05.gr2), with _2, _3
  when that name is taken by a different copy or by a file the --art folders already hold. In a
  folder --building-names matches (below art, lower case), a copy is named as a mod lays out its
  own buildings: `<folder>_<level>[_dmg|_con|_death|_lp]` (`building_name`: the level from the
  number the new texture's name ends in, else the stock model's age; the role from the stock
  model's name), `_v2`, `_v3` for another copy that would take the same name (not `_b`,
  which names a normal map).
- the <file> then names the copy and the <replacetexture> blocks are deleted, line by line, so
  the rest of the anim file stays as it was written.

Written into --out, laid out as art: the edited anim files (plain XML, at their own paths), the
copies (uncompressed: compress them with tools/recompress_models.py), clones.tsv (copy, source,
source SHA-256, the swaps, the anim files using it) and bake.txt (what was removed and why, the
models not found). A model stored in two archives with different bytes is taken from the first
archive in name order and marked in clones.tsv. Nothing is written with --dry-run.
"""
import collections
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import hc_survey  # noqa: E402
from aoe3game import deploy, gr2, gr2_edit, gr2_write  # noqa: E402

ASSET_RE = re.compile(r"<assetreference\b[^>]*\btype\s*=\s*[\"']GrannyModel[\"'][^>]*>(.*?)</assetreference\s*>",
                      re.S | re.I)
FILE_RE = re.compile(r"<file>\s*(.*?)\s*</file>", re.S | re.I)
SWAP_RE = re.compile(r"<replacetexture>\s*<from>\s*(.*?)\s*</from>\s*<to>\s*(.*?)\s*</to>\s*</replacetexture>",
                     re.S | re.I)

BUMP_RE = re.compile(r"(_b|_bump|_normal|_nm|_n)$", re.I)     # a bump map's name, not used to name a copy


ROLES = ((re.compile(r"death", re.I), "_death"), (re.compile(r"damaged|_dmg", re.I), "_dmg"),
         (re.compile(r"_con\d*\b|construction|stage\d|frame", re.I), "_con"),
         (re.compile(r"^lp_|_lp\b", re.I), "_lp"))


def building_name(building, source_stem, texture_stem):
    """A building copy's name as a mod lays out its own buildings: the building, its level and its
    role, `<building>_<level>[_dmg|_con|_death|_lp]`. The level is the number the new texture's
    name ends in (`java_arsenal_4` -> 4: the mod's texture of that level), else the age the stock
    model's name gives (`west_arsenal_age2` -> 2), else none; the role comes from the stock model's
    name (`..._damaged`, `..._deathmodel`, `..._con`, `lp_...`)."""
    level = re.search(r"(?:^|_)(\d)$", texture_stem) or re.search(r"age_?(\d)", source_stem, re.I)
    role = next((r for rx, r in ROLES if rx.search(source_stem)), "")
    return f"{building}_{level.group(1)}{role}" if level else f"{building}{role}"


class Refused(Exception):
    pass


def read_manifest(path):
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for n, line in enumerate(fh, 1):
            line = line.split("#", 1)[0].rstrip("\r\n")
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                raise Refused(f"{path}:{n}: expected <anim file>\\t<folder for its copies>")
            rows.append((hc_survey.norm(parts[0]), parts[1].replace("/", "\\").strip("\\")))
    return rows


class Arts:
    """Several art folders, looked up in order."""

    def __init__(self, roots):
        self.arts = [hc_survey.Art(r) for r in roots]
        self.conflicts = set()              # names two archives hold with different bytes
        for a in self.arts:
            sizes = collections.defaultdict(set)
            for name in sorted(os.listdir(a.root)) if os.path.isdir(a.root) else []:
                if name.lower().endswith(".bar"):
                    for stored, _o, size in bar.read_entries(os.path.join(a.root, name)):
                        sizes[hc_survey.norm(stored)].add(size)
            self.conflicts |= {k for k, s in sizes.items() if len(s) > 1}

    def find(self, key):
        for a in self.arts:
            if a.exists(key):
                return a
        return None

    def read(self, key):
        a = self.find(key)
        return a.read(key) if a else None

    def exists(self, key):
        return self.find(key) is not None


def line_span(text, start, end):
    """The span to delete for a block at start..end: with its line when nothing else is on it."""
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le < 0 else le + 1
    if text[ls:start].strip() == "" and text[end:le].strip() == "":
        return ls, le
    return start, end


class Baker:
    def __init__(self, arts, out, prefix, bridge, caches, dry, buildings=None):
        self.arts, self.out, self.prefix, self.bridge, self.caches, self.dry = arts, out, prefix, bridge, caches, dry
        self.buildings = re.compile(buildings, re.I) if buildings else None
        self.clones = {}            # (sha, swaps) -> {"path", "source", "sha", "swaps", "users", "conflict"}
        self.taken = {}             # clone key (lower, below art) -> clone id
        self.notes = []
        self.stored = {}            # model key -> (bytes sha, [stored names], raw bytes, type tag)

    def note(self, anim, msg):
        self.notes.append(f"{anim}: {msg}")

    def model(self, key):
        if key in self.stored:
            return self.stored[key]
        data = self.arts.read(key)
        if data is None:
            self.stored[key] = None
            return None
        raw, how = hc_survey.raw_bytes(data, self.caches, self.bridge)
        if raw is None:
            raise Refused(f"{key}: {how}: give --granny and --granny-install")
        doc = gr2.load(raw)
        names = [t.get("FromFileName") for t in (doc.root().get("Textures") or []) if t is not None]
        self.stored[key] = (hashlib.sha256(data).hexdigest(), names, raw, doc.c.type_tag)
        return self.stored[key]

    def clone_name(self, folder, source_key, swaps, ident):
        stems = [t.rsplit("\\", 1)[-1] for _f, t in swaps]
        colour = [s for s in stems if not BUMP_RE.search(s)]
        first = (colour or stems)[0]
        stem = os.path.splitext(os.path.basename(source_key))[0]
        if self.buildings is not None and self.buildings.search(folder.lower()):
            base = building_name(os.path.basename(folder), stem, first)
            n = 1
            while True:
                name = base if n == 1 else f"{base}_v{n}"     # not _b: that is a normal map's name
                rel = f"{folder}\\{name}"
                key = hc_survey.norm(rel) + ".gr2"
                owner = self.taken.get(key)
                if owner == ident or (owner is None and not self.arts.exists(key)):
                    self.taken[key] = ident
                    return rel
                n += 1
        base = f"{first}_{stem}"
        n = 1
        while True:
            name = base if n == 1 else f"{base}_{n}"
            rel = f"{folder}\\{name}"
            key = hc_survey.norm(rel) + ".gr2"
            owner = self.taken.get(key)
            if owner == ident or (owner is None and not self.arts.exists(key)):
                self.taken[key] = ident
                return rel
            n += 1

    def bake_block(self, anim, folder, file_value, swaps):
        """The new <file> value (or None: keep it) for one model reference with its swaps."""
        mkey = hc_survey.model_key(file_value)
        info = self.model(mkey)
        if info is None:
            self.note(anim, f"model {file_value} not found: its <replacetexture> blocks are kept")
            return "keep"
        sha, names, raw, tag = info
        stored = {gr2_edit.texture_key(n) for n in names}
        live = []
        for frm, to in swaps:
            fk, tk = gr2_edit.texture_key(frm), gr2_edit.texture_key(to)
            if fk not in stored:
                self.note(anim, f"{file_value}: <from> {frm} is not stored in the model: removed")
            elif not self.arts.exists(tk + ".ddt"):
                self.note(anim, f"{file_value}: <to> {to} found nowhere: removed (the model's own texture shows)")
            elif fk != tk:
                live.append((fk, tk))
        live = sorted(dict(live).items())
        if not live:
            return None
        ident = (sha, tuple(live))
        c = self.clones.get(ident)
        if c is None:
            path = self.clone_name(folder, mkey, live, ident)
            c = {"path": path, "source": mkey, "sha": sha, "swaps": live, "users": [],
                 "conflict": mkey in self.arts.conflicts}
            self.clones[ident] = c
            if not self.dry:
                root = gr2_edit.copy_tree(gr2.load(raw))
                renamed = gr2_edit.rename_textures(root, {f: gr2_edit.stored_name(t, self.prefix) for f, t in live})
                if not renamed:
                    raise Refused(f"{mkey}: nothing renamed")
                self.write(path + ".gr2", gr2_write.serialize(root, type_tag=tag))
        if anim not in c["users"]:
            c["users"].append(anim)
        return c["path"]

    def write(self, rel, data):
        p = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".baking"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)

    def bake_anim(self, anim, folder):
        found = self.arts.find(anim) or self.arts.find(anim + ".xmb")
        if found is None:
            self.note(anim, "anim file not found")
            return 0, 0
        key = anim if found.exists(anim) else anim + ".xmb"
        text = hc_survey.decode_text(found.read(key))
        masked = hc_survey.blank_comments(text)
        edits = []                                          # (start, end, replacement)
        n_swaps = n_clones = 0
        for m in ASSET_RE.finditer(masked):
            inner_at = m.start(1)
            inner = masked[m.start(1):m.end(1)]
            swaps = [(s, t) for s, t in ((x.group(1), x.group(2)) for x in SWAP_RE.finditer(inner))]
            if not swaps:
                continue
            f = FILE_RE.search(inner)
            if f is None:
                self.note(anim, f"line {masked.count(chr(10), 0, m.start()) + 1}: a model reference without <file>")
                continue
            n_swaps += len(swaps)
            new = self.bake_block(anim, folder, text[inner_at + f.start(1):inner_at + f.end(1)], swaps)
            if new == "keep":
                continue
            if new is not None:
                edits.append((inner_at + f.start(1), inner_at + f.end(1), new))
                n_clones += 1
            for x in SWAP_RE.finditer(inner):
                s, e = line_span(text, inner_at + x.start(), inner_at + x.end())
                edits.append((s, e, ""))
        if edits:
            out = text
            for s, e, rep in sorted(edits, key=lambda t: t[0], reverse=True):
                out = out[:s] + rep + out[e:]
            if not self.dry:
                rel = found.display(key)
                rel = rel[:-4] if rel.lower().endswith(".xmb") else rel
                self.write(rel, out.encode("utf-8"))
        return n_swaps, n_clones

    def report(self):
        rows = ["copy\tsource\tsource_sha256\tswaps\tanim_files\tnote"]
        for c in sorted(self.clones.values(), key=lambda c: c["path"].lower()):
            rows.append("\t".join([c["path"], c["source"], c["sha"],
                                   "; ".join(f"{f} -> {t}" for f, t in c["swaps"]),
                                   "; ".join(c["users"]),
                                   "stored in two archives with different bytes: the first was taken"
                                   if c["conflict"] else ""]))
        return "\n".join(rows) + "\n", "\n".join(self.notes) + ("\n" if self.notes else "")


def main(argv):
    args = {"manifest": None, "art": [], "out": None, "prefix": "C:\\art\\", "granny": None,
            "install": None, "cache": [], "dry": False, "buildings": None}
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a == "--manifest":
                args["manifest"], i = argv[i + 1], i + 1
            elif a == "--art":
                args["art"].append(argv[i + 1])
                i += 1
            elif a == "--out":
                args["out"], i = argv[i + 1], i + 1
            elif a == "--prefix":
                args["prefix"], i = argv[i + 1], i + 1
            elif a == "--building-names":
                args["buildings"], i = argv[i + 1], i + 1
            elif a == "--granny":
                args["granny"], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
            elif a == "--cache":
                args["cache"].append(argv[i + 1])
                i += 1
            elif a == "--dry-run":
                args["dry"] = True
            else:
                raise ValueError(a)
            i += 1
    except (IndexError, ValueError):
        args["manifest"] = None
    if not args["manifest"] or not args["art"] or not args["out"] or bool(args["granny"]) != bool(args["install"]):
        print(__doc__)
        return 2
    try:
        deploy.refuse_steam(args["out"])
        for a in args["art"]:
            if os.path.abspath(args["out"]).lower().startswith(os.path.abspath(a).lower() + os.sep):
                raise Refused(f"--out is inside the art folder {a}: write the baked files elsewhere")
        rows = read_manifest(args["manifest"])
    except (Refused, deploy.RefusedPath, OSError) as exc:
        print(f"refused: {exc}")
        return 1
    bridge = None
    if args["granny"]:
        work = os.path.join(args["out"], "_granny_work") if not args["cache"] else os.path.join(args["cache"][0], "granny")
        bridge = (args["granny"], args["install"], work)
    baker = Baker(Arts(args["art"]), args["out"], args["prefix"], bridge, tuple(args["cache"]), args["dry"],
                  args["buildings"])
    total_swaps = total_refs = 0
    refused = 0
    for anim, folder in rows:
        try:
            s, c = baker.bake_anim(anim, folder)
        except (Refused, gr2.Gr2Error, OSError) as exc:
            print(f"{anim}: refused: {exc}")
            refused += 1
            continue
        total_swaps += s
        total_refs += c
        print(f"{anim}: {s} <replacetexture>, {c} model references now name a copy")
    tsv, notes = baker.report()
    if not args["dry"]:
        os.makedirs(args["out"], exist_ok=True)
        with open(os.path.join(args["out"], "clones.tsv"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(tsv)
        with open(os.path.join(args["out"], "bake.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(notes)
    print(f"{len(rows)} anim files, {total_swaps} <replacetexture> blocks, {len(baker.clones)} copies "
          f"for {total_refs} model references, {len(baker.notes)} notes, {refused} refused"
          + (" (dry run: nothing written)" if args["dry"] else ""))
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
