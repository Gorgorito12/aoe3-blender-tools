# SPDX-License-Identifier: GPL-3.0-or-later
"""Find the animations of a unit that lack the HITPOINTBAR tag, and add it.

    python -I tools/fix_hitpointbar_tags.py <anim file or folder> [...] [--art <art folder>]
           [--proto <protoy.xml or .xmb>] [--units <Name,...>] [--out <folder>] [--dry-run]

A unit's floating health bar sits on the HITPOINTBAR tag of the animation it is playing. The
tags of an animation are the tracks of its `<animation>.gr2.precomp` file (see
docs/game-formats.md, "Animation tags"). When some of a unit's animations have the tag and
others do not, the game puts the bar at a height of its own during the others, and the bar jumps
each time the unit changes animation (standing, walking, fighting).

For each anim file (the art XML a proto names in <AnimFile>, plain or compiled .xmb), the tool
reads every animation of the unit's own model (not those of its attachments, nor Death*), finds
the tag file of each Granny animation (a loose file in the art folder first, then the .bar
archives of that folder), and adds a constant HITPOINTBAR to those without it, at the height the
unit's other animations use: the median of the tag over the Idle animations that have it, or
over all of them when no Idle has it. Nothing else of the file changes; the anim file itself is
not touched.

Inputs: anim files, folders (searched for anim files), or --proto with the art folder: every
unit of the protos (or of --units) with its anim file, loose or in an archive.
--art      the game's or mod's art folder (default: the folder named "art" above the input).
--out      write the fixed tag files below this folder, at their art paths (default: into the
           art folder itself, keeping a loose file that is replaced as <name>.orig).
--dry-run  report only.

An animation several anim files share gets the height most of them want (the others are named
in the report); a tie is refused. Also refused, with the reason in the report: an animation with
no tag file (the tags must then come from the .gr2 itself, which this tool does not edit), a
tag file with no tracks or with tracks of different lengths, one sampled on several models, and
one it cannot re-encode byte for byte.
"""
import collections
import os
import statistics
import struct
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
sys.path.insert(0, HERE)
from aoe3game import precomp  # noqa: E402
import bar  # noqa: E402
import xmbedit  # noqa: E402

TAG = precomp.HITPOINTBAR
SUFFIX = ".gr2.precomp"
HEIGHT_TOLERANCE = 0.05     # model units: two units may agree on a shared animation within this


def norm(path):
    """An art path as a lookup key: lowercase, backslashes, no leading 'art\\'."""
    p = path.replace("/", "\\").strip().strip("\\").lower()
    return p[4:] if p.startswith("art\\") else p


class Art:
    """The files of an art folder: loose ones first, then those of its .bar archives."""

    def __init__(self, root):
        self.root = root
        self.loose = {}
        for folder, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(folder, name)
                self.loose.setdefault(norm(os.path.relpath(full, root)), full)
        self.archived = {}
        for name in sorted(os.listdir(root)):
            if name.lower().endswith(".bar"):
                archive = os.path.join(root, name)
                for stored, offset, size in bar.read_entries(archive):
                    self.archived.setdefault(norm(stored), (archive, stored, offset, size))

    def find(self, path):
        """(bytes, where, stored art path) of a file, loose first, or None."""
        key = norm(path)
        if key in self.loose:
            full = self.loose[key]
            with open(full, "rb") as f:
                return f.read(), full, os.path.relpath(full, self.root)
        if key in self.archived:
            archive, stored, offset, size = self.archived[key]
            with open(archive, "rb") as f:
                f.seek(offset)
                return f.read(size), f"{os.path.basename(archive)}:{stored}", stored
        return None

    def anim_file(self, path):
        """An anim file by its proto path: the plain XML if loose, else the compiled one."""
        return self.find(path) or self.find(path + ".xmb")


def anim_tree(raw):
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        raw = xmbedit.to_xml(elems, attrs, root).encode("utf-8")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raw = raw.decode("utf-16").encode("utf-8")
    root = ET.fromstring(raw)
    for el in root.iter():
        el.tag = el.tag.lower()
    return root


def unit_animations(root):
    """[(anim name, [Granny animation art path, ...])] of the model's own animations."""
    out = []

    def walk(el):
        for child in el:
            if child.tag == "attachment":
                continue
            if child.tag == "anim":
                name = (child.text or "").strip()
                files = [(f.text or "").strip()
                         for ref in child.iter("assetreference")
                         if (ref.get("type") or "").lower() == "grannyanim"
                         for f in ref.iter("file") if (f.text or "").strip()]
                out.append((name, files))
            else:
                walk(child)
    walk(root)
    return out


def median_point(points):
    return tuple(statistics.median(p[i] for p in points) for i in range(3))


def rotation_of(doc):
    """The first rotation key of the tag's first track (the bar ignores it; kept plausible)."""
    for index, tracks in doc.mapping:
        if 0 <= index < len(doc.names) and doc.names[index].upper() == TAG:
            for t in tracks:
                if 0 <= t < len(doc.rotations) and doc.rotations[t]:
                    return doc.rotations[t][0]
    return struct.pack("<4f", 0.0, 0.0, 0.0, 1.0)


def survey(art, anim_path, raw, owners, plan, report):
    """Adds the fixes of one anim file to `plan` {precomp key: entry}; returns its summary."""
    try:
        root = anim_tree(raw)
    except Exception as exc:  # noqa: BLE001 - any parse error is a refusal
        report.append(f"  REFUSED {anim_path}: not readable as an anim file ({exc})")
        return None
    anims = [(n, fs) for n, fs in unit_animations(root) if fs and not n.lower().startswith("death")]
    tagged = collections.defaultdict(list)     # anim name -> [(position, rotation)]
    missing, untagged_files = [], []
    for name, files in anims:
        for path in files:
            found = art.find(path + SUFFIX)
            if found is None:
                model = art.find(path + ".gr2")
                where = "missing" if model is None else (
                    "in an archive" if ":" in os.path.basename(model[1]) else "loose")
                untagged_files.append((name, path, f"no tag file (the .gr2 is {where})"))
                continue
            data, where, stored = found
            try:
                doc = precomp.load(data)
            except precomp.PrecompError as exc:
                untagged_files.append((name, path, f"tag file not handled ({exc})"))
                continue
            tracks = doc.tracks_of(TAG)
            if tracks:
                keys = [k for t in tracks for k in t]
                tagged[name].append((median_point(keys), rotation_of(doc)))
            else:
                missing.append((name, path, doc, data, where, stored))
    if not tagged:
        return {"anim": anim_path, "owners": owners, "tagged": 0, "missing": len(missing),
                "refused": untagged_files, "height": None}
    idle = [p for n, ps in tagged.items() if n.lower() == "idle" for p in ps]
    source = idle or [p for ps in tagged.values() for p in ps]
    position = median_point([p for p, _r in source])
    rotation = source[0][1]
    for name, path, doc, data, where, stored in missing:
        key = norm(path + SUFFIX)
        entry = plan.setdefault(key, {"path": path, "stored": stored, "where": where, "data": data,
                                      "doc": doc, "heights": [], "units": [], "anims": set()})
        entry["heights"].append((position, rotation, anim_path))
        entry["units"] += owners
        entry["anims"].add(name)
    return {"anim": anim_path, "owners": owners, "tagged": sum(len(v) for v in tagged.values()),
            "missing": len(missing), "missing_names": sorted({m[0] for m in missing}),
            "refused": untagged_files, "height": position}


def anim_inputs(args, art):
    """[(anim art path, raw bytes, owner names)] from files, folders or protos."""
    out = []
    for path in args.paths:
        files = []
        if os.path.isdir(path):
            for folder, _dirs, names in os.walk(path):
                files += [os.path.join(folder, n) for n in names
                          if n.lower().endswith((".xml", ".xml.xmb"))]
        else:
            files.append(path)
        for f in sorted(files):
            with open(f, "rb") as fh:
                raw = fh.read()
            try:
                if anim_tree(raw).tag != "animfile":
                    continue
            except Exception:  # noqa: BLE001 - not XML: not an anim file
                continue
            out.append((os.path.relpath(f, art.root), raw, []))
    if args.proto:
        with open(args.proto, "rb") as fh:
            proto = anim_tree(fh.read())
        wanted = {u.lower() for u in args.units} if args.units else None
        by_file = collections.OrderedDict()
        for unit in proto.iter("unit"):
            name = unit.get("name") or ""
            if wanted is not None and name.lower() not in wanted:
                continue
            anim = unit.find("animfile")
            if anim is None or not (anim.text or "").strip():
                continue
            by_file.setdefault(norm(anim.text), (anim.text.strip(), []))[1].append(name)
        for path, owners in by_file.values():
            found = art.anim_file(path)
            if found is None:
                print(f"  (no anim file {path} for {', '.join(owners)})")
                continue
            out.append((path, found[0], owners))
    return out


def fmt(p):
    return "(" + ", ".join(f"{v:.3f}" for v in p) + ")"


def agreeing_groups(heights):
    """The heights several anim files want for one shared animation, as groups that agree within
    HEIGHT_TOLERANCE, one entry per anim file, the largest group first."""
    seen, groups = set(), []
    for h in heights:
        if h[2] in seen:
            continue
        seen.add(h[2])
        for g in groups:
            if all(abs(a - b) <= HEIGHT_TOLERANCE for a, b in zip(g[0][0], h[0])):
                g.append(h)
                break
        else:
            groups.append([h])
    return sorted(groups, key=len, reverse=True)


def describe(groups):
    return "; ".join(f"{fmt(median_point([h[0] for h in g]))} for "
                     f"{', '.join(sorted(h[2] for h in g)[:3])}{', ...' if len(g) > 3 else ''}"
                     for g in groups)


def parse_args(argv):
    class A:
        pass
    args = A()
    args.paths, args.art, args.proto, args.units, args.out, args.dry_run = [], None, None, [], None, False
    it = iter(argv)
    for a in it:
        if a == "--dry-run":
            args.dry_run = True
        elif a in ("--art", "--proto", "--out", "--units"):
            value = next(it, None)
            if value is None:
                sys.exit(f"{a} needs a value")
            if a == "--units":
                args.units = [u.strip() for u in value.split(",") if u.strip()]
            else:
                setattr(args, a[2:], value)
        elif a.startswith("--"):
            sys.exit(f"unknown option {a}\n{__doc__}")
        else:
            args.paths.append(a)
    if not args.paths and not args.proto:
        sys.exit(__doc__)
    if args.art is None:
        start = os.path.abspath(args.paths[0] if args.paths else args.proto)
        probe = start
        while probe and os.path.basename(probe).lower() != "art":
            parent = os.path.dirname(probe)
            if parent == probe:
                probe = None
                break
            probe = parent
        if probe is None and args.proto:
            guess = os.path.join(os.path.dirname(os.path.dirname(start)), "art")
            probe = guess if os.path.isdir(guess) else None
        if probe is None:
            sys.exit("cannot tell the art folder: pass --art")
        args.art = probe
    return args


def main(argv):
    args = parse_args(argv)
    art = Art(args.art)
    inputs = anim_inputs(args, art)
    plan, report, summaries = {}, [], []
    for anim_path, raw, owners in inputs:
        s = survey(art, anim_path, raw, owners, plan, report)
        if s:
            summaries.append(s)
    print(f"art folder: {args.art}")
    print(f"anim files read: {len(summaries)}")
    jumping = [s for s in summaries if s["tagged"] and s["missing"]]
    never = [s for s in summaries if not s["tagged"]]
    print(f"anim files whose animations all have {TAG} (or have none to fix): "
          f"{len(summaries) - len(jumping) - len(never)}")
    print(f"anim files with no {TAG} in any animation (the bar never moves, left alone): {len(never)}")
    print(f"anim files where some animations lack it (the bar jumps): {len(jumping)}")
    for s in jumping:
        owners = f" [{', '.join(s['owners'][:4])}{', ...' if len(s['owners']) > 4 else ''}]" if s["owners"] else ""
        print(f"  {s['anim']}{owners}: {s['missing']} animation files lack it in "
              f"{', '.join(s['missing_names'])}; height {fmt(s['height'])}")
    refused = [(s["anim"], r) for s in summaries if s["tagged"] for r in s["refused"]]
    for line in report:
        print(line)
    if refused:
        reasons = collections.Counter(r[2] for _a, r in refused)
        print(f"animations without the tag that the tool cannot fix ({len(refused)}: "
              + ", ".join(f"{n} {why}" for why, n in reasons.most_common()) + "):")
        for anim, (name, path, why) in refused[:40]:
            print(f"  {anim}: {name} {path}: {why}")
        if len(refused) > 40:
            print(f"  ... and {len(refused) - 40} more")
    written = skipped = disagreed = 0
    for key, entry in sorted(plan.items()):
        groups = agreeing_groups(entry["heights"])
        note = ""
        if len(groups) > 1:
            if len(groups[0]) == len(groups[1]):
                print(f"  REFUSED {entry['path']}: as many anim files give it one height as another: "
                      + describe(groups))
                skipped += 1
                continue
            note = f"; the other anim files that use it wanted another height: {describe(groups[1:])}"
            disagreed += 1
        heights = groups[0]
        position = median_point([h[0] for h in heights])
        doc = entry["doc"]
        try:
            doc.add_constant(TAG, position, heights[0][1])
        except precomp.PrecompError as exc:
            print(f"  REFUSED {entry['path']}: {exc}")
            skipped += 1
            continue
        out_bytes = doc.encode()
        check = precomp.load(out_bytes)
        assert check.has(TAG) and check.names[:-1] == precomp.load(entry["data"]).names
        rel = entry["stored"]
        if rel.lower().startswith("art\\") or rel.lower().startswith("art/"):
            rel = rel[4:]
        target = os.path.join(args.out or args.art, *rel.replace("/", "\\").split("\\"))
        action = "would write" if args.dry_run else "wrote"
        print(f"  {action} {target}: {TAG} at {fmt(position)} for {', '.join(sorted(entry['anims']))} "
              f"(from {entry['where']}){note}")
        if args.dry_run:
            written += 1
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target) and not args.out:
            backup = target + ".orig"
            if not os.path.exists(backup):
                os.replace(target, backup)
        with open(target, "wb") as f:
            f.write(out_bytes)
        written += 1
    total_missing = sum(len(e["anims"]) for e in plan.values())
    print(f"tag files to fix: {len(plan)} ({written} {'to write' if args.dry_run else 'written'}, "
          f"{skipped} refused; {disagreed} shared by anim files that wanted different heights, "
          f"given the height most of them use), {total_missing} animation names involved")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
