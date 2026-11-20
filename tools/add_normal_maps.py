# SPDX-License-Identifier: GPL-3.0-or-later
"""Gives a normal map to every material whose shader needs one and has none: an art lead's rule,
"si no hay mapa de normales hay que crearlo, de otra manera la textura tendra reflejos buggeados".

    venv\\Scripts\\python -I tools/add_normal_maps.py --manifest <models.txt> --art <folder> [--art ...]
                                         --out <folder> [--strength 6] [--dry-run]
                                         [--granny <bridge.exe> --granny-install <game folder>] [--cache <folder>]

The manifest lists models below art, one per line (`#` starts a comment); they and their textures
are looked up in the --art folders in order (loose files, then each folder's .bar archives).

A material needs one when its shader is a `bumpspec...` one (aoe3game/gr2_material.py) and it has
a "Diffuse Color" map but no "Bump" map. Its normal map is the diffuse texture's own `_b`, `_bump`,
`_normal` or `_n` when the --art folders hold one that is a normal map (usage bit 4), else made
once per diffuse texture as `<diffuse texture>_b.ddt` from the diffuse
texture (ddt.normal_from_texture: its brightness as height; `--strength`) and written as the game's
own bump textures are (DXT5, usage 6, a full chain of mips; re-encode it to an exact tuple
afterwards if a lead asks for one). A diffuse texture of the stock game gets its normal map in the
model's own folder, named after it. The material then gets a "Bump" map naming it (stored as
`C:\\art\\<path>.ddt`). Shaders without bump (trees, alpha test, blend) and materials that have one
are left alone.

Writes into --out, laid out as art: the rewritten models (uncompressed: tools/recompress_models.py
compresses them), the new normal maps, normals.txt (each material given one, and from what).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bake_textures  # noqa: E402
import hc_survey  # noqa: E402
from aoe3game import ddt, deploy, gr2, gr2_edit, gr2_material, gr2_write  # noqa: E402


SUFFIXES = ("_b", "_bump", "_normal", "_n")      # how the game and mods name a texture's normal map


def normal_map_bytes(data, strength):
    rgba = ddt.decode(data, 0)
    return ddt.write_normal_map(ddt.normal_from_texture(rgba, strength=strength), mips=True)


def is_normal_map(data):
    try:
        return bool(ddt.read_header(data).usage & 4)
    except ddt.DdtError:
        return False


def run(models, arts, out, strength, dry, bridge, caches, log):
    made, first, notes, rewritten = {}, {}, [], 0
    for key in models:
        data = arts.read(key)
        if data is None:
            notes.append(f"{key}: not found")
            continue
        raw, how = hc_survey.raw_bytes(data, caches, bridge)
        if raw is None:
            notes.append(f"{key}: {how}")
            continue
        doc = gr2.load(raw)
        root = gr2_edit.copy_tree(doc)
        changed = 0
        for mat in gr2_material.materials(root):
            if not gr2_material.wants_bump(mat):
                continue
            tex = gr2_material.texture_of(gr2_material.maps(mat)["diffuse color"])
            dkey = gr2_edit.texture_key(tex.values.get("FromFileName")) if tex is not None else None
            ddata = arts.read(dkey + ".ddt") if dkey else None
            if ddata is None:
                notes.append(f"{key}: material {mat.values.get('Name')!r}: its diffuse texture {dkey} is not found")
                continue
            found = next((k for k in (dkey + s for s in SUFFIXES)
                          if (b := arts.read(k + ".ddt")) is not None and is_normal_map(b)), None)
            if found:
                bkey, why = found, "its normal map was there"
            elif dkey in first:
                bkey, why = first[dkey], "made for another material"
            else:
                own = any(dkey + ".ddt" in a.loose for a in arts.arts[:1])
                dshown = arts.find(dkey + ".ddt").display(dkey + ".ddt")     # spelled as on disk
                folder = os.path.dirname(dshown) if own else os.path.dirname(arts.find(key).display(key))
                bkey = f"{folder}\\{os.path.splitext(os.path.basename(dshown))[0]}_b"
                made[bkey] = normal_map_bytes(ddata, strength)
                first[dkey] = bkey
                why = f"made from {dkey}"
            gr2_material.add_bump(root, mat, gr2_edit.stored_name(bkey))
            notes.append(f"{key}: material {mat.values.get('Name')!r} ({gr2_material.shader(mat)}): bump {bkey} ({why})")
            changed += 1
        if changed:
            rewritten += 1
            if not dry:
                write(out, arts.find(key).display(key), gr2_write.serialize(root, type_tag=doc.c.type_tag))
    if not dry:
        for bkey, blob in made.items():
            write(out, bkey + ".ddt", blob)
    log(f"{len(models)} models, {rewritten} given normal maps, {len(made)} normal maps made"
        + (" (dry run: nothing written)" if dry else ""))
    return notes


def write(out, rel, data):
    p = os.path.join(out, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".writing", "wb") as fh:
        fh.write(data)
    os.replace(p + ".writing", p)


def main(argv):
    args = {"manifest": None, "art": [], "out": None, "granny": None, "install": None, "cache": [],
            "strength": 6.0, "dry": False}
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("--manifest", "--out", "--granny"):
                args[a[2:]], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
            elif a == "--strength":
                args["strength"], i = float(argv[i + 1]), i + 1
            elif a in ("--art", "--cache"):
                args[a[2:]].append(argv[i + 1])
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
    except deploy.RefusedPath as exc:
        print(f"refused: {exc}")
        return 1
    with open(args["manifest"], encoding="utf-8-sig") as fh:
        models = [hc_survey.norm(line.split("#", 1)[0].split("\t")[0]) for line in fh if line.split("#", 1)[0].strip()]
    bridge = None
    if args["granny"]:
        work = os.path.join(args["cache"][0], "granny") if args["cache"] else os.path.join(args["out"], "_granny_work")
        bridge = (args["granny"], args["install"], work)
    notes = run(models, bake_textures.Arts(args["art"]), args["out"], args["strength"], args["dry"], bridge,
                tuple(args["cache"]), print)
    if not args["dry"]:
        os.makedirs(args["out"], exist_ok=True)
        with open(os.path.join(args["out"], "normals.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(notes) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
