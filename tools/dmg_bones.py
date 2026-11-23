# SPDX-License-Identifier: GPL-3.0-or-later
"""Lists the damage templates whose parts name a bone that the model using them does not have, or that
its anim file does not define (<definebone>).

    python -I tools/dmg_bones.py <game folder> [--granny-install <game folder>] [--helper <exe>]
                                 [--only <text>] [--csv <out.csv>] [--fix <out folder> [--fix-list <out.csv>]]

An anim file's <assetreference type="GrannyModel" damagetemplate="X.dmg"> gives the model (its <file>)
the parts of the template X: every <part bone="..."> under its <impactpoint>s; so does a building's
<simskeleton> with its <model> and <damagetemplate>. The legacy game looks a part's bone up by its
name, which an anim file must have defined with <definebone>. When no anim file loaded so far defined
it, the game writes "Invalid bone name ... in part declaration for model ..., this probably means the
bone was not defined in the unit's anim XML", adds the name and loads the model again while units
still draw it: the old Granny file is freed under them and the game can crash in its next draw
(granny2.dll, or a model draw in age3y.exe). Two cases are listed: "missing bones", a bone the model's
skeleton lacks (the fix: a template made for the model, or no template), and "not defined", a bone the
model has but the anim file does not define (the fix: a <definebone> line). Names are compared
ignoring case. A bone another anim file defines is still listed: the game is safe only when that file
was loaded first.

Reads the game folder's art: loose files first, then the art\\*.bar archives (stored .xml and .xmb,
damage templates as .dmg or .dmg.xmb). A compressed model is read by the game's granny2.dll through
tools/recompress_models.py's helper (`--build-helper`; --granny-install defaults to the game folder).
Nothing is written but --csv, unless --fix is given. Exit status 1 when a pair is listed.

--fix <out folder> writes, for every anim file with a "not defined" bone (in either kind of row), a copy
with a <definebone> line for each bone of its templates that the model HAS and the file does not define;
bones the model lacks get none (no line can fix them). The copies go to <out folder>\\art\\<the anim
file's own path>, in the form the game reads: a loose .xml is edited as text (its encoding, BOM and line
ends kept, nothing else changed: each line copies the indentation and tag spelling of the definebone
line it follows, in name order when the file's lines are in name order, else after the last one); a
loose .xml.xmb next to it is edited too when it lacks the bones; a file only in an archive becomes a
loose .xml.xmb (the archive's entry with the nodes added, everything else byte for byte the same).
--fix-list writes one row per file written. The game folder itself is never changed.
"""
import csv
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import xmbedit  # noqa: E402
from aoe3game import gr2  # noqa: E402


class Art:
    """The game's art folder as the game sees it: loose files over the archives' entries."""

    def __init__(self, game):
        self.root = os.path.join(game, "art")
        self.loose, self.stored, self.names = {}, {}, {}
        for folder, _dirs, files in os.walk(self.root):
            for name in files:
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, self.root).replace("/", "\\")
                self.loose[rel.lower()] = path
                self.names[rel.lower()] = rel
        for name in sorted(os.listdir(self.root)):
            if name.lower().endswith(".bar"):
                archive = os.path.join(self.root, name)
                for stored, offset, size in bar.read_entries(archive):
                    key = stored.lower().replace("/", "\\")
                    real = stored.replace("/", "\\")
                    real = real[4:] if key.startswith("art\\") else real
                    key = key[4:] if key.startswith("art\\") else key
                    self.stored.setdefault(key, (archive, offset, size))
                    self.names.setdefault(key, real)

    def keys(self):
        return set(self.loose) | set(self.stored)

    def read(self, key):
        key = key.lower().replace("/", "\\")
        if key in self.loose:
            with open(self.loose[key], "rb") as fh:
                return fh.read()
        if key in self.stored:
            archive, offset, size = self.stored[key]
            with open(archive, "rb") as fh:
                fh.seek(offset)
                return fh.read(size)
        return None

    def read_xml(self, key):
        """(key found, XML text) of key or key + '.xmb'."""
        for k in (key, key + ".xmb"):
            raw = self.read(k)
            if raw is None:
                continue
            if raw[:4] == b"l33t" or raw[:2] == b"X1":
                return k, xmbedit.to_xml(*xmbedit.parse(xmbedit.decode(raw)))
            for enc in ("utf-8-sig", "utf-16", "cp1252"):
                try:
                    return k, raw.decode(enc)
                except UnicodeError:
                    continue
        return None, None


def parse(text):
    try:
        return ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("\ufeff")))
    except ET.ParseError:
        return None


class Bones:
    """A model's bone names: this repository's reader, or the game's runtime for a compressed file."""

    def __init__(self, helper, dll):
        self.helper, self.dll, self.cache = helper, dll, {}
        self.work = tempfile.mkdtemp(prefix="dmg_bones_")

    def of(self, art, model):
        key = model.lower().replace("/", "\\").lstrip("\\")
        key = key if key.endswith(".gr2") else key + ".gr2"
        if key in self.cache:
            return self.cache[key]
        data = art.read(key)
        names = None
        if data is not None:
            try:
                root = gr2.load(data).root()
                names = {b.get("Name") or "" for sk in (root.get("Skeletons") or []) if sk is not None
                         for b in (sk.get("Bones") or [])}
            except gr2.Compressed:
                names = self.runtime(data)
            except Exception:  # noqa: BLE001 - an unreadable model is reported, not fatal
                names = None
        self.cache[key] = names
        return names

    def runtime(self, data):
        if not (self.helper and os.path.exists(self.helper) and os.path.exists(self.dll)):
            return None
        path = os.path.join(self.work, "info.gr2")
        with open(path, "wb") as fh:
            fh.write(data)
        env = dict(os.environ, TEMP=self.work, TMP=self.work)
        r = subprocess.run([self.helper, self.dll, "info", "info.gr2"], cwd=self.work, env=env,
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            return None
        lines = r.stdout.decode("cp1252", "replace").splitlines()
        return {ln.split("\t")[1] for ln in lines if ln.startswith("bone\t")}


def template_bones(art, dmg):
    """{bone: count} of the parts of a damage template, or None when it is not found."""
    key, text = art.read_xml(dmg)
    root = parse(text) if text else None
    if root is None:
        return key, None
    out = {}
    for part in root.iter():
        if part.tag.lower() == "part":
            bone = next((v for k, v in part.attrib.items() if k.lower() == "bone"), None)
            if bone:
                out[bone] = out.get(bone, 0) + 1
    return key, out


DEFINE_LINE = re.compile(r"^([ \t]*<definebone\b[^>]*>[ \t]*)([^<\r\n]*?)([ \t]*</definebone>[ \t]*)(\r\n|\n|\r)?$",
                         re.I)


def _slot(names, key):
    """Where a new bone name goes among the existing ones (index into names, len(names) = after the
    last): between two names it sorts between, the one sharing the longest prefix with its
    neighbours; after the last when no place fits (the names are not in order)."""
    def common(a, b):
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        return n
    fits = [s for s in range(len(names) + 1)
            if (s == 0 or names[s - 1] < key) and (s == len(names) or names[s] > key)]
    if not fits:
        return len(names)
    return max(fits, key=lambda s: (max(common(key, names[s - 1]) if s else 0,
                                        common(key, names[s]) if s < len(names) else 0), s))


def decode_text(raw):
    """(text, encoding, BOM) of an XML text file, or None when it does not decode and encode back
    to the same bytes."""
    for bom, enc in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"), (b"\xef\xbb\xbf", "utf-8"),
                     (b"", "utf-8"), (b"", "cp1252")):
        if raw.startswith(bom):
            try:
                text = raw[len(bom):].decode(enc)
            except UnicodeError:
                continue
            if bom + text.encode(enc) == raw:
                return text, enc, bom
    return None


def add_definebones_text(text, names):
    """(text with a <definebone> line for each of names it does not define, names added), or None when
    the file has no <definebone> line to copy. A line copies the one it follows (indentation, tag
    spelling, line end); comments are skipped."""
    comments = [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", text, re.S)]
    lines = text.splitlines(keepends=True)
    defs, offset = [], 0  # (line index, lowercase name, match)
    for i, line in enumerate(lines):
        m = DEFINE_LINE.match(line)
        if m and not any(a <= offset + m.start(2) < b for a, b in comments):
            defs.append((i, m.group(2).strip().lower(), m))
        offset += len(line)
    if not defs:  # none yet: first lines of the root element, as the stock files have them
        root = next((i for i, line in enumerate(lines)
                     if re.fullmatch(r"[ \t]*<animfile\b[^>]*>[ \t]*(\r\n|\n|\r)?", line, re.I)), None)
        if root is None or any(a <= sum(map(len, lines[:root])) < b for a, b in comments):
            return None
        nl = re.search(r"(\r\n|\n|\r)?$", lines[root]).group(0) or "\r\n"
        nxt = next((line for line in lines[root + 1:] if line.strip()), "\t")
        indent = re.match(r"[ \t]*", nxt).group(0) or "\t"
        new = sorted({n.lower(): n for n in names}.values(), key=str.lower)
        add = [f"{indent}<definebone>{n}</definebone>{nl}" for n in new]
        return "".join(lines[:root + 1] + add + lines[root + 1:]), new
    have = {d[1] for d in defs}
    new = sorted({n.lower(): n for n in names if n.lower() not in have}.values(), key=str.lower)
    if not new:
        return text, []
    order = [d[1] for d in defs]
    after = {}  # line index -> new lines after it (index -1: before the first definebone)
    nl = next((d[2].group(4) for d in defs if d[2].group(4)), "\r\n")
    for name in new:
        s = _slot(order, name.lower())
        like = defs[s - 1] if s else defs[0]
        m = like[2]
        after.setdefault(like[0] if s else -1, []).append(m.group(1) + name + m.group(3) + (m.group(4) or nl))
    out = []
    for i, line in enumerate(lines):
        if i == defs[0][0] and -1 in after:
            out.extend(after[-1])
        if i in after and not line.endswith(("\n", "\r")):
            line += nl
        out.append(line)
        out.extend(after.get(i, []))
    return "".join(out), new


def add_definebones_xmb(raw, names):
    """(the .xmb with a definebone node for each of names it does not define, names added), or None
    when it has no definebone node to copy or does not encode back to the same bytes. The nodes sit
    beside the existing ones (same order rule as the text), on the source line of the one before."""
    inner = xmbedit.decode(raw)
    elems, attrs, root = xmbedit.parse(inner)
    if xmbedit.encode(elems, attrs, root) != inner:
        return None
    parent = None
    for nd in [root] + [c for c in root.children]:
        kids = [c for c in nd.children if elems[c.name].lower() == "definebone"]
        if kids:
            parent = nd
            break
    if parent is None:  # none yet: first children of the root, as the stock files have them
        if elems[root.name].lower() != "animfile":
            return None
        if "definebone" not in elems:
            elems.append("definebone")
        line = root.children[0].line if root.children else root.line
        new = sorted({n.lower(): n for n in names}.values(), key=str.lower)
        for i, name in enumerate(new):
            nd = xmbedit.Node()
            nd.text, nd.name, nd.line, nd.attrs, nd.children = name, elems.index("definebone"), line, [], []
            root.children.insert(i, nd)
        return xmbedit.wrap(xmbedit.encode(elems, attrs, root), xmbedit.is_compressed(raw)), new
    kids = [c for c in parent.children if elems[c.name].lower() == "definebone"]
    have = {(c.text or "").strip().lower() for c in kids}
    new = sorted({n.lower(): n for n in names if n.lower() not in have}.values(), key=str.lower)
    if not new:
        return raw, []
    order = [(c.text or "").strip().lower() for c in kids]
    slots = {}
    for name in new:  # sorted
        slots.setdefault(_slot(order, name.lower()), []).append(name)
    for s, group in slots.items():
        like = kids[s - 1] if s else kids[0]
        at = parent.children.index(like) + (1 if s else 0)
        for i, name in enumerate(group):
            nd = xmbedit.Node()
            nd.text, nd.name, nd.line, nd.attrs, nd.children = name, like.name, like.line, [], []
            parent.children.insert(at + i, nd)
    return xmbedit.wrap(xmbedit.encode(elems, attrs, root), xmbedit.is_compressed(raw)), new


def write_fixes(art, out, to_define):
    """Writes the fixed anim files (see --fix); returns the rows of --fix-list."""
    rows = []
    for base in sorted(to_define):
        names = list(to_define[base].values())
        # The file this scan read: a loose .xml (a stale .xmb beside it is left alone: the game read the
        # .xml, and a newer .xmb could take its place), else a loose .xmb, else the archive's entry,
        # written as a loose file of the same name.
        forms = [k for k in (base, base + ".xmb") if k in art.loose][:1]
        if not forms:
            forms = [k for k in (base + ".xmb", base) if k in art.stored][:1]
        for key in forms:
            raw = art.read(key)
            where = "loose" if key in art.loose else os.path.basename(art.stored[key][0])
            if key.endswith(".xmb") or raw[:4] == b"l33t" or raw[:2] == b"X1":
                done = add_definebones_xmb(raw, names)
                data, added = (done[0], done[1]) if done else (None, None)
            else:
                decoded = decode_text(raw)
                done = add_definebones_text(decoded[0], names) if decoded else None
                if done:
                    text, enc, bom = decoded
                    data, added = bom + done[0].encode(enc), done[1]
                else:
                    data, added = None, None
            if data is None:
                rows.append((art.names[key], where, "not fixed: no <definebone> to copy or not read back", ""))
                continue
            if not added:
                continue
            path = os.path.join(out, "art", art.names[key])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            rows.append((art.names[key], where, "fixed", "; ".join(added)))
    return rows


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    game = argv[0]
    opt = {k: argv[argv.index(k) + 1] for k in ("--granny-install", "--helper", "--only", "--csv", "--fix",
                                                "--fix-list") if k in argv}
    install = opt.get("--granny-install", game)
    helper = opt.get("--helper", os.path.join(HERE, "granny_recompress.exe"))
    art = Art(game)
    bones = Bones(helper, os.path.join(install, "granny2.dll"))
    anims = sorted(k for k in art.keys() if k.endswith(".xml") or k.endswith(".xml.xmb"))
    if "--only" in opt:
        anims = [k for k in anims if opt["--only"].lower() in k]
    rows, seen, templates, done, to_define = [], set(), {}, set(), {}
    for key in anims:
        base = key[:-4] if key.endswith(".xmb") else key
        if base in seen:
            continue
        seen.add(base)
        _k, text = art.read_xml(base)
        if not text or "damagetemplate" not in text.lower():
            continue
        root = parse(text)
        if root is None:
            continue
        defined = {(d.text or "").strip().lower() for d in root.iter() if d.tag.lower() == "definebone"}
        for ref in root.iter():
            tag = ref.tag.lower()
            if tag == "assetreference":  # <assetreference damagetemplate="X"><file>model</file>
                dmg = next((v for k, v in ref.attrib.items() if k.lower() == "damagetemplate"), None)
                files = [c.text.strip() for c in ref if c.tag.lower() == "file" and c.text]
            elif tag == "simskeleton":  # a building's <simskeleton><model>m</model><damagetemplate>X</damagetemplate>
                dmg = next((c.text.strip() for c in ref if c.tag.lower() == "damagetemplate" and c.text), None)
                files = [c.text.strip() for c in ref if c.tag.lower() == "model" and c.text]
            else:
                continue
            if not dmg or not files:
                continue
            if dmg.lower() not in templates:
                templates[dmg.lower()] = template_bones(art, dmg)
            dmg_key, wanted = templates[dmg.lower()]
            for model in files:
                if (base, model.lower(), dmg.lower()) in done:
                    continue
                done.add((base, model.lower(), dmg.lower()))
                have = bones.of(art, model)
                undefined = sorted(b for b in (wanted or {}) if b.lower() not in defined)
                if wanted is None:
                    rows.append((base, model, dmg, "template not found", "", ""))
                elif have is None:
                    rows.append((base, model, dmg, "model not read", "", "; ".join(undefined)))
                else:
                    lower = {h.lower() for h in have}  # the game's bone names ignore case
                    missing = sorted(b for b in wanted if b.lower() not in lower)
                    spelled = {h.lower(): h for h in have}
                    for b in undefined:  # --fix: bones the model has and the file does not define, as the model spells them
                        if b.lower() in lower:
                            to_define.setdefault(base, {}).setdefault(b.lower(), spelled[b.lower()])
                    if missing:
                        rows.append((base, model, dmg, "missing bones", "; ".join(missing), "; ".join(undefined)))
                    elif undefined:
                        rows.append((base, model, dmg, "not defined", "", "; ".join(undefined)))
    missing_rows = [r for r in rows if r[3] == "missing bones"]
    undefined_rows = [r for r in rows if r[3] == "not defined"]
    for r in rows:
        print("\t".join(r))
    print(f"{len(seen)} anim files read; {len(templates)} damage templates; {len(missing_rows)} model and template "
          f"pairs with bones the model lacks; {len(undefined_rows)} more with bones the anim file does not define; "
          f"{len(rows) - len(missing_rows) - len(undefined_rows)} not checked (template or model not found or not read)")
    if "--csv" in opt:
        with open(opt["--csv"], "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["anim file", "model", "damage template", "result", "bones the model lacks",
                        "bones the anim file does not define"])
            w.writerows(rows)
    if "--fix" in opt:
        fixed = write_fixes(art, opt["--fix"], to_define)
        for r in fixed:
            print("fix\t" + "\t".join(r))
        ok = [r for r in fixed if r[2] == "fixed"]
        print(f"--fix: {len(ok)} files written to {opt['--fix']} ({sum(len(r[3].split('; ')) for r in ok)} "
              f"<definebone> lines), {len(fixed) - len(ok)} not fixed")
        if "--fix-list" in opt:
            with open(opt["--fix-list"], "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["file written", "taken from", "result", "bones defined"])
                w.writerows(fixed)
    return 1 if missing_rows or undefined_rows else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
