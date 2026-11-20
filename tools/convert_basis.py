# SPDX-License-Identifier: GPL-3.0-or-later
"""Puts rigid accessory models (hats, weapons, cannon barrels, ship rigging: one bone, every mesh
bound to it whole) exported raw from 3ds Max into the form of a converted model: the stock basis
("ESPostExport", 0.615157485 units per metre, Y up), the object at the origin, one bone with no
scale, no animation of its own. A raw export keeps the scene it was cut from (the object metres
away from the origin, the node's scale on its bone, a track holding that placement), which is what
modders call an "object world too large".

    python -I tools/convert_basis.py <model.gr2 | folder> ... -o <out>
                                     [--frombone <bone>] [--all] [--dry-run]
                                     [--granny <bridge.exe> --granny-install <game folder>]

-o is a file for one input file, else a folder: every .gr2 below an input folder is written at
the same relative path below it. Without -o the files are changed in place (a .bak copy is kept).
A file is rewritten only when it needs it: its art tool is not "ESPostExport", or its units per
metre are not the stock ones (--all rewrites every rigid file). --frombone names the bone the
anim file lays on the unit (`<attach frombone=...>`); without it, the file's only bone.

A skinned body or a part of several bones is converted, with --granny, by the bridge's `rebake
--convert` (the game's own runtime transforms vertices, bones, inverses, boxes and animation
curves) and then named `ESPostExport`, so the game does not convert it again. Checked offline on a
23-bone body: every vertex and bone where it was, its rest pose its bind pose.

What is kept: names, materials, textures and their stored names, the vertex layout, the type
tag. Each vertex is taken into the bone's rest frame without the bone's scale, as the game hangs
an accessory (checked in game, docs/game-formats.md, "Attachments at rest"), so the part stands
on the unit where it stood before. Refused: a file with more than one bone, skinned vertices, a
packed vertex stream (those are converted models already). Compressed input needs the external
bridge (--granny), whose uncompressed copy is the one rewritten; compress the results again with
tools/recompress_models.py. Needs numpy (the venv's Python).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import fix_bone_scale as fbs  # noqa: E402
from aoe3game import deploy, gr2, gr2_basis, gr2_write  # noqa: E402

STOCK = gr2_write.STOCK_BASIS


def needs_it(root):
    """Why a file needs the rewrite ('' when it does not)."""
    art = root.get("ArtToolInfo")
    if art is None:
        return "no art tool information"
    name = art.get("FromArtToolName") or ""
    upm = float(art.get("UnitsPerMeter") or 0)
    if name != STOCK["name"]:
        return f"art tool {name!r}"
    if abs(upm - STOCK["units_per_meter"]) > 1e-4:
        return f"{upm:g} units per metre"
    return ""


def bridge_convert(path, exe, install):
    """The file put into the stock basis by the external bridge (`rebake --convert`: the game's own
    granny2.dll, GrannyComputeBasisConversion and GrannyTransformFile), uncompressed."""
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp(prefix="convert_basis_")
    try:
        out = os.path.join(tmp, "converted.gr2")
        try:
            r = subprocess.run([exe, "rebake", "--install", install, "--file", os.path.abspath(path),
                                "--out", out, "--convert"], cwd=tmp, capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise gr2_basis.Refused(f"the bridge failed: {type(exc).__name__}") from exc
        if r.returncode != 0 or not os.path.exists(out):
            raise gr2_basis.Refused(f"the bridge could not convert it (exit {r.returncode})")
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_one(path, out_path, args):
    """('converted' | 'dry' | 'same', message). Raises gr2_basis.Refused, fbs.Refused."""
    with open(path, "rb") as fh:
        data = fh.read()
    facts = gr2.header_facts(data[:4096])
    if "magic" in facts:
        raise gr2_basis.Refused("not a Granny file")
    if not facts.get("raw"):
        if not args["granny"]:
            raise gr2_basis.Refused("its sections are compressed: give --granny <bridge> "
                                    "--granny-install <game folder>")
        data = fbs.expand(path, args["granny"], args["install"])
    why = needs_it(gr2.load(data).root())
    if not why and not args["all"]:
        return "same", "already in the stock basis"
    try:
        new, info = gr2_basis.normalise_rigid(data, frombone=args["frombone"])
        msg = (f"{why or 'forced'}; bone {info['bone']!r}, scale {info['scale_dropped']:g} dropped, "
               f"size {info['size_before']} -> {info['size_after']} (stock units)")
    except gr2_basis.Refused as exc:
        if "no mesh" in str(exc) or not args["granny"]:
            raise
        # a skinned body or a part of several bones: the game's runtime converts it whole
        # (vertices, bones, inverses, boxes, animation curves), then it is named as converted
        new = gr2_basis.name_stock(bridge_convert(path, args["granny"], args["install"]))
        msg = f"{why or 'forced'}; {exc}: converted by the game's runtime and named {gr2_write.STOCK_BASIS['name']}"
    if args["dry_run"]:
        return "dry", msg
    if out_path is None:
        out_path = path
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(new)
    return "converted", f"{msg}; wrote {out_path} ({len(new)} B, uncompressed)"


def main(argv):
    args = {"frombone": None, "all": False, "dry_run": False, "granny": None, "install": None}
    out_path, inputs, i = None, [], 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("-o", "--out"):
                out_path, i = argv[i + 1], i + 1
            elif a == "--frombone":
                args["frombone"], i = argv[i + 1], i + 1
            elif a == "--granny":
                args["granny"], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
            elif a == "--all":
                args["all"] = True
            elif a == "--dry-run":
                args["dry_run"] = True
            elif a.startswith("-"):
                raise ValueError(a)
            else:
                inputs.append(a)
            i += 1
    except (IndexError, ValueError):
        inputs = []
    if not inputs or bool(args["granny"]) != bool(args["install"]):
        print(__doc__)
        return 2
    jobs = []
    for item in inputs:
        if os.path.isdir(item):
            for full, rel in fbs.gr2_files(item):
                jobs.append((full, os.path.join(out_path, rel) if out_path else None))
        elif out_path and len(inputs) == 1 and not os.path.isdir(out_path):
            jobs.append((item, out_path))
        else:
            jobs.append((item, os.path.join(out_path, os.path.basename(item)) if out_path else None))
    counts = {"converted": 0, "dry": 0, "same": 0, "refused": 0}
    for path, out in jobs:
        try:
            if not args["dry_run"]:
                deploy.refuse_steam(out or path)
            status, msg = run_one(path, out, args)
        except (gr2_basis.Refused, fbs.Refused, deploy.RefusedPath, gr2.Gr2Error, OSError,
                struct.error) as exc:
            print(f"{path}: refused: {exc}")
            counts["refused"] += 1
            continue
        counts[status] += 1
        print(f"{path}: {status}: {msg}")
    verb = "to convert" if args["dry_run"] else "converted"
    print(f"{len(jobs)} files: {counts['converted'] + counts['dry']} {verb}, {counts['same']} already "
          f"converted, {counts['refused']} refused" + (" (dry run: nothing written)" if args["dry_run"] else ""))
    return 1 if counts["refused"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
