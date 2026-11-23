# SPDX-License-Identifier: GPL-3.0-or-later
"""Fit Granny models (.gr2) to the damage template and the animations they borrow from another
model, in place: debris meshes renamed to the template's part names, bones given the reference
model's rest frames.

    python -I tools/fit_borrowed.py <in.gr2 | folder> [...] [-o <out.gr2 | out folder>]
                                    [--dmg <template.dmg | .dmg.xmb>] [--rest-from <reference.gr2>]
                                    [--dry-run] [-v]
                                    [--granny <bridge.exe> --granny-install <game folder>]

At least one of --dmg and --rest-from. A folder is walked for every .gr2 below it; with -o, a
changed file is written to the same relative path below the output folder (files with nothing to
change are not copied). Without -o each input is rewritten in place after a copy to <in>.bak.
--dry-run prints what would change and writes nothing. The last line counts the files changed,
unchanged and refused; the exit status is 1 when any was refused.

A mod building often reuses a stock building's damage template and death animation on models
rebuilt from the stock ones. Two things then break in game, silently:

--dmg: the template's parts find their meshes by name. A debris mesh renamed on export
  (Blender's duplicate suffix, `debris_1a.001`) is not found and that piece never breaks off. A
  mesh whose name is a part's name plus `.NNN`, bound to that part's bone alone, gets the part's
  name (the suffix is cut where the name is stored). The parts still missing are listed.
--rest-from: the animation sets each bone's local transform by name, as made on the reference
  model. Bones exported with other rest orientations (a turn, a mirror, a scale) are drawn by it
  with every piece turned about its bone. Each bone the reference has under the same name, with
  the same parent and the same world position, gets the reference's local transform and inverse
  world transform; the meshes stay where they are (rest pose = bind pose is required of both, and
  checked after). The reference is the model the animation was made on (its death model for a
  death animation, its damage model for a damage template); it must be uncompressed (or given
  through --granny like the inputs).

The values are written over the old ones (the file keeps its size) and the CRC is recomputed; the
result is read back and checked before it is written. Compressed inputs need --granny (the
external bridge writes an uncompressed copy first) and are written uncompressed; compress them
again with tools/recompress_models.py --like <originals>.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
sys.path.insert(0, HERE)
from aoe3game import deploy, gr2, gr2_fit  # noqa: E402
import fix_bone_scale as fbs  # noqa: E402  (the bridge and the folder walk)
import xmbedit  # noqa: E402


def read_template(path):
    """[(mesh, bone)] of a damage template, plain XML or compiled (.xmb)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:2] in (b"X1", b"l3") or raw[:4] == b"l33t":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        text = xmbedit.to_xml(elems, attrs, root)
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
    else:
        text = raw.decode("utf-8-sig", "replace")
    parts = gr2_fit.template_parts(text)
    if not parts:
        raise gr2_fit.Refused(f"{path}: no <part mesh=... bone=...> in it")
    return parts


def load_raw(path, args):
    """(uncompressed bytes, expanded): through the bridge for a compressed file."""
    with open(path, "rb") as fh:
        data = fh.read()
    facts = gr2.header_facts(data[:4096])
    if "magic" in facts:
        raise gr2_fit.Refused("not a Granny file")
    if facts.get("raw"):
        return data, False
    if not args["granny"]:
        raise gr2_fit.Refused("its sections are compressed: give --granny <bridge> --granny-install "
                              "<game folder>, or write it uncompressed first")
    try:
        return fbs.expand(path, args["granny"], args["install"]), True
    except fbs.Refused as exc:
        raise gr2_fit.Refused(str(exc)) from exc


def run_one(path, out_path, args):
    """Returns (status, changes): status 'changed', 'same' or 'dry'. Raises Refused."""
    data, expanded = load_raw(path, args)
    new, lines = gr2_fit.fit(data, args["parts"], args["ref"])
    changes = sum(1 for ln in lines if ln.startswith(("  mesh ", "  bone ")))
    if new is None:
        if args["verbose"] or any("missing" in ln for ln in lines):
            print(f"{path}: nothing to change")
            print("\n".join(lines))
        return "same", 0
    print(f"{path}:")
    shown = lines if args["verbose"] else [ln for ln in lines if not ln.startswith("  bone ")]
    if shown:
        print("\n".join(shown))
    bones = sum(1 for ln in lines if ln.startswith("  bone "))
    if bones and not args["verbose"]:
        print(f"  {bones} bones: rest frames from the reference")
    if args["dry_run"]:
        return "dry", changes
    if out_path is None:
        out_path = path
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
            print(f"  backup {bak}")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(new)
    size = (f"{len(new)} B, written uncompressed" if expanded
            else f"{len(new)} B, same size, CRC updated")
    print(f"  wrote {out_path} ({size})")
    return "changed", changes


def main(argv):
    args = {"dmg": None, "rest": None, "dry_run": False, "granny": None, "install": None,
            "verbose": False, "parts": None, "ref": None}
    out_path, inputs, i = None, [], 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("-o", "--out"):
                out_path, i = argv[i + 1], i + 1
            elif a == "--dmg":
                args["dmg"], i = argv[i + 1], i + 1
            elif a == "--rest-from":
                args["rest"], i = argv[i + 1], i + 1
            elif a == "--granny":
                args["granny"], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
            elif a == "--dry-run":
                args["dry_run"] = True
            elif a in ("-v", "--verbose"):
                args["verbose"] = True
            elif a.startswith("-"):
                raise ValueError(a)
            else:
                inputs.append(a)
            i += 1
    except (IndexError, ValueError):
        inputs = []
    if (not inputs or (out_path and len(inputs) != 1) or bool(args["granny"]) != bool(args["install"])
            or not (args["dmg"] or args["rest"])):
        print(__doc__)
        return 2
    try:
        if args["dmg"]:
            args["parts"] = read_template(args["dmg"])
        if args["rest"]:
            args["ref"], _ = load_raw(args["rest"], args)
            gr2.load(args["ref"])
    except (gr2_fit.Refused, gr2.Gr2Error, OSError, ValueError) as exc:
        print(f"refused: {exc}")
        return 1
    jobs = []
    for item in inputs:
        if os.path.isdir(item):
            for full, rel in fbs.gr2_files(item):
                jobs.append((full, os.path.join(out_path, rel) if out_path else None))
        else:
            jobs.append((item, out_path))
    counts = {"changed": 0, "dry": 0, "same": 0, "refused": 0}
    total = 0
    for path, out in jobs:
        try:
            if not args["dry_run"]:
                deploy.refuse_steam(out or path)
            status, n = run_one(path, out, args)
        except (gr2_fit.Refused, deploy.RefusedPath, gr2.Gr2Error, OSError, struct.error) as exc:
            print(f"{path}: refused: {exc}")
            counts["refused"] += 1
            continue
        counts[status] += 1
        total += n
    verb = "to change" if args["dry_run"] else "changed"
    print(f"{len(jobs)} files: {counts['changed'] + counts['dry']} {verb} ({total} meshes and bones), "
          f"{counts['same']} with nothing to change, {counts['refused']} refused"
          + (" (dry run: nothing written)" if args["dry_run"] else ""))
    return 1 if counts["refused"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
