# SPDX-License-Identifier: GPL-3.0-or-later
"""Survey the art of an Age of Empires III install or mod: what models, textures and anim files it
has, how they reference each other, and the conventions they follow. Read-only; standard library.

    python -I tools/art_survey.py <folder> [<folder> ...] --out <report folder> [--bar] [--label NAME]
                                 [--reference <report.json>]

<folder>     a mod folder or the game folder; loose files are read below it.
--bar        also read the .bar archives below the folders, in memory (nothing is extracted).
--reference  another survey's report.json (e.g. of the base game): references found there are
             marked as reused from it, and the report says which of this mod's files are new.
--label      a name for the report (default: the first folder's name).

Writes <out>/report.json (everything) and <out>/summary.md (the tables). The report holds
measurements and file paths only, never file contents; it still names the scanned mod's files,
so keep it out of public repositories.

What it reads:
- anim files (.xml, or compiled .xml.xmb, below an "art" folder): element and attribute names,
  every referenced file (any element with a <file> child, and any text ending in a known
  extension), attach point and bone names, logic types, anim names;
- .ddt textures: the header (fields to verify: "RTS3", usage, alpha, format, mip levels, width,
  height);
- .gr2 models: size and the first 16 bytes (mesh statistics need a Granny reader: next step).
"""
import collections
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bar  # noqa: E402
import xmbedit  # noqa: E402

MODEL_EXT = (".gr2",)
TEX_EXT = (".ddt",)
REF_EXT = (".gr2", ".ddt", ".xml", ".tga", ".bmp", ".png", ".wav", ".particle", ".lgt")


def norm(path):
    """Comparable path: lowercase, backslashes, no leading separators, no leading 'art\\'."""
    p = path.strip().replace("/", "\\").lower().lstrip("\\")
    return p[4:] if p.startswith("art\\") else p


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
    """The folder below 'art' (units, buildings, ...), or '(other)'."""
    parts = [x for x in path.replace("/", "\\").lower().split("\\") if x]
    if "art" in parts:
        i = parts.index("art")
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
    return {"head": raw[:16].hex()}


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
    return {"tags": dict(tags), "attrs": dict(attrs), "refs": refs, "points": dict(points),
            "logic": dict(logic), "anims": dict(anims)}


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


def survey(folders, use_bar=False, label=None, reference=None):
    files = {"model": {}, "texture": {}, "anim": {}}
    errors = []
    for path, size, reader in iter_files(folders, use_bar):
        if reader is None:
            errors.append(path)
            continue
        k = kind(path.split(":")[-1])
        try:
            raw = reader() if k == "anim" else reader(64)      # textures and models: header only
            if k == "texture":
                info = read_ddt(raw)
            elif k == "model":
                info = read_gr2(raw)
            else:
                info = read_anim(raw)
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
            n = norm(f)
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

    return {
        "label": label or os.path.basename(os.path.abspath(folders[0])),
        "folders": [os.path.abspath(f) for f in folders],
        "counts": {k: len(v) for k, v in files.items()},
        "anim_categories": dict(by_cat),
        "anim_tags": top(tags, 60), "ref_types": top(reftypes), "attach_points": top(points, 60),
        "logic_types": top(logic), "anim_names": top(anims, 60),
        "texture_sizes": top(tex_sizes), "texture_formats": top(tex_formats),
        "most_reused": reuse, "per_anim": per_anim,
        "kitbash": {
            "anims_only_reference": sum(1 for a in per_anim.values() if a["refs"] and a["own"] == 0 and a["unresolved"] == 0 and a["reference"] > 0),
            "anims_only_own": sum(1 for a in per_anim.values() if a["refs"] and a["reference"] == 0 and a["unresolved"] == 0),
            "anims_mixed": sum(1 for a in per_anim.values() if a["own"] and (a["reference"] or a["unresolved"])),
            "anims_with_unresolved": sum(1 for a in per_anim.values() if a["unresolved"]),
        },
        "files": files, "errors": errors,
    }


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
    if rep["errors"]:
        out += ["## Read errors", ""] + [f"- {e}" for e in rep["errors"][:100]] + [""]
    return "\n".join(out)


def main(argv):
    if "--out" not in argv or argv.index("--out") + 1 >= len(argv):
        print(__doc__)
        return 2
    out = argv[argv.index("--out") + 1]
    label = argv[argv.index("--label") + 1] if "--label" in argv else None
    reference = argv[argv.index("--reference") + 1] if "--reference" in argv else None
    skip = {out, label, reference}
    folders = [a for a in argv if not a.startswith("--") and a not in skip]
    if not folders:
        print(__doc__)
        return 2
    rep = survey(folders, "--bar" in argv, label, reference)
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
