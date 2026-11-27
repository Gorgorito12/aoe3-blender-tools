# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks an art package (a folder laid out as art, holding only a mod's new files) against the
rules an art lead gives, and counts every breach: a package is ready when every count is zero.

    python -I tools/art_lint.py --package <folder with art\\> --lint <lint.json>
                                [--textures <rules.json>] [--art <game art folder> ...]
                                [--source <source art folder> ...] [--out <lint.txt>]
                                [--granny <bridge.exe> --granny-install <game folder>] [--cache <folder>]

--art names the game the package goes into (its art folder: loose files, then its .bar archives):
what the package's files name may be found there. The lint file (JSON) says the layout:

    {"allowed": ["^wol\\\\units\\\\[a-z_]+\\\\[^\\\\]+\\\\[^\\\\]+$", ...],   the paths a file may have
     "forbidden": ["\\\\cavalry_ranged\\\\"],                               paths no file may have
     "converted": "^wol\\\\units\\\\",            models that must be in the converted basis
     "converted_exempt": ["..."],                  ...but these (raw skinned bodies, listed)
     "buildings": "^wol\\\\buildings\\\\"}          anim files whose static attachments count

Checks (each one a count, with up to 20 examples, in --out and on screen):
- replacetexture: <replacetexture> outside comments in an anim file;
- unresolved: a path an anim or particle file names, or a texture a model stores, found neither in
  the package nor in --art; with --source (the art the package was made from), one the source lacks
  too and that is not one of the package's own paths is counted apart as inherited (a defect of the
  source, or of a stock model a copy was made from), and does not fail the lint;
- banned: a .tga .png .jpg .jpeg .bmp .max .psd .precomp .bak file, and any compiled .xmb (a damage
  template ships as plain .dmg);
- layout: a file whose path no `allowed` pattern matches, or a `forbidden` one does;
- duplicate: two files of the package with the same bytes;
- overrides: a file at a path the game already serves (the package must only add files);
- textures (with --textures, aoe3-blender-tools' reencode rules): a texture whose header tuple or size
  breaks its rule (an alpha-test bit, a transparent alpha or a player-colour mask kept from the
  source is accepted where the rule says `keep`);
- normals: a material whose shader reads a bump map (`bumpspec...`) and has none, drawing a
  texture of the package's own (tools/add_normal_maps.py gives it one);
- unreadable: a compressed model the lint could not expand (give the bridge: --granny);
- unconverted: a model under `converted` not in the stock basis (ESPostExport, 0.615 units per
  metre), unless exempt;
- attachments: an <attach> of a static model left in a building anim file
  (tools/merge_attachments.py's test of static).
Exit status 1 when a count is not zero.
"""
import collections
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bake_textures  # noqa: E402
import hc_survey  # noqa: E402
import merge_attachments  # noqa: E402
import reencode_textures  # noqa: E402
from aoe3game import ddt, gr2, gr2_edit, gr2_material, gr2_write  # noqa: E402

BANNED = (".tga", ".png", ".jpg", ".jpeg", ".bmp", ".max", ".psd", ".precomp", ".bak", ".xmb")
CHECKS = ("replacetexture", "unresolved", "unreadable", "banned", "layout", "duplicate", "overrides", "textures",
          "normals", "unconverted", "attachments")
INFO = ("inherited",)


def anim_refs(text):
    """[(key below art, role, inside an <attachment>)] of every path an anim or particle file
    names: models (.gr2) for Granny model and animation references and a simulation skeleton,
    textures (.ddt) for decals, splashes, <replacetexture> targets and a particle's <file>,
    includes, damage templates and other files as written. A <from> is skipped: it names the
    texture being replaced."""
    out = []
    for stack, value, _line in hc_survey.scan(text):
        tag = stack[-1][0]
        if tag == "from" or not value.strip() or "\n" in value.strip():
            continue
        v = value.strip()
        names = [t for t, _a in stack]
        att = "attachment" in names
        ext = os.path.splitext(v.replace("\\", "/").rsplit("/", 1)[-1])[1]
        if tag == "file":
            asset = next((a.get("type", "").lower() for t, a in reversed(stack) if t == "assetreference"), None)
            if "particlefile" in names:
                out.append((hc_survey.norm(v) + ("" if ext else ".ddt"), "texture", False))
            elif asset in ("grannymodel", "grannyanim"):
                out.append((hc_survey.norm(v) + ("" if ext.lower() == ".gr2" else ".gr2"),
                            "model" if asset == "grannymodel" else "granny_anim", att))
            elif ext:
                out.append((hc_survey.norm(v), "particle" if ext.lower() == ".particle" else "file", att))
        elif tag == "include":
            out.append((hc_survey.norm(v), "include", att))
        elif tag == "model" and "simskeleton" in names:
            out.append((hc_survey.norm(v) + ("" if ext else ".gr2"), "model", False))
        elif tag == "damagetemplate":
            out.append((hc_survey.norm(v), "dmg", False))
        elif tag in ("texture", "selectedtexture", "noncinematictexture", "bumptexture", "to"):
            out.append((hc_survey.norm(v) + ("" if ext.lower() == ".ddt" else ".ddt"), "texture", att))
    return out


def is_rig(merger, value):
    """Does the model a component draws hold a character rig (a Bip01 bone)?"""
    try:
        raw = merger.raw(hc_survey.model_key(value))
    except bake_textures.Refused:
        return False
    if raw is None:
        return False
    bones = [b.get("Name") or "" for sk in (gr2.load(raw).root().get("Skeletons") or []) for b in (sk.get("Bones") or [])]
    return any(b.lower().startswith("bip01") for b in bones)


def lint(package, spec, rules, game_arts, source_arts=(), bridge=None, caches=()):
    art = os.path.join(package, "art")
    pkg = hc_survey.Art(art, loose=True)
    found = {c: [] for c in CHECKS + INFO}
    tops = {k.split("\\", 1)[0] for k in pkg.loose}

    def exists(key):
        return key in pkg.loose or any(a.exists(k) for a in game_arts for k in (key, key + ".xmb"))

    def missing(where, key):
        """A path found nowhere: the port's fault when it is one of the package's own paths or
        the source has it (it was not carried); inherited when the source lacks it too (a
        defect of the source mod or of the stock model a copy was made from)."""
        ours = key.split("\\", 1)[0] in tops
        in_source = any(a.exists(k) for a in source_arts for k in (key, key + ".xmb"))
        found["unresolved" if ours or in_source or not source_arts else "inherited"].append(f"{where} {key}")

    allowed = [re.compile(p, re.I) for p in spec.get("allowed", [])]
    forbidden = [re.compile(p, re.I) for p in spec.get("forbidden", [])]
    converted = re.compile(spec["converted"], re.I) if spec.get("converted") else None
    exempt = [re.compile(p, re.I) for p in spec.get("converted_exempt", [])]
    buildings = re.compile(spec["buildings"], re.I) if spec.get("buildings") else None
    by_sha = collections.defaultdict(list)
    merger = merge_attachments.Merger(bake_textures.Arts([art] + [a.root for a in game_arts]), None, bridge, caches, True)
    for key, path in sorted(pkg.loose.items()):
        with open(path, "rb") as fh:
            data = fh.read()
        by_sha[hashlib.sha256(data).hexdigest()].append(key)
        low = key.lower()
        if low.endswith(BANNED):
            found["banned"].append(key)
        if (allowed and not any(p.search(low) for p in allowed)) or any(p.search(low) for p in forbidden):
            found["layout"].append(key)
        if any(a.exists(key) for a in game_arts):
            found["overrides"].append(key)
        if low.endswith((".xml", ".particle")):
            text = hc_survey.decode_text(data)
            masked = hc_survey.blank_comments(text)
            if re.search(r"<replacetexture", masked, re.I):
                found["replacetexture"].append(key)
            for ref, _role, _att in anim_refs(text):
                if not exists(ref):
                    missing(f"{key} ->", ref)
            if buildings is not None and buildings.search(low) and low.endswith(".xml"):
                tree = merge_attachments.parse(masked)
                statics = set()
                for e in tree.walk():
                    if e.tag == "attachment":
                        name = e.text(masked)
                        model, _why = merger.static_model(e, masked, key)
                        if model and name:
                            statics.add(name.lower())
                for comp in tree.walk():
                    if comp.tag != "component" or any(a.tag in ("attachment", "anim") for a in comp.ancestors()):
                        continue
                    bodies = merge_attachments.models_in(comp, masked)
                    if any(merge_attachments.CONSTRUCTION.search(v) for _f, v in bodies):
                        continue
                    if any(is_rig(merger, v) for _f, v in bodies):
                        continue                      # a unit's accessories stay attachments
                    for c in comp.children:
                        if c.tag == "attach" and c.attrs.get("a", "").lower() in statics:
                            found["attachments"].append(f"{key}: {c.attrs.get('a')}")
        elif low.endswith(".gr2"):
            try:
                raw, how = hc_survey.raw_bytes(data, caches, bridge)
                if raw is None:
                    found["unreadable"].append(f"{key}: {how} (give --granny and --granny-install)")
                    continue
                root = gr2.load(raw).root()
            except gr2.Gr2Error as exc:
                found["unresolved"].append(f"{key}: unreadable ({exc})")
                continue
            for t in root.get("Textures") or []:
                tk = gr2_edit.texture_key(t.get("FromFileName")) + ".ddt"
                if not exists(tk):
                    missing(f"{key} stores", tk)
            tree = gr2_edit.copy_tree(gr2.load(raw))
            for mat in gr2_material.materials(tree):
                if gr2_material.wants_bump(mat):
                    tex = gr2_material.texture_of(gr2_material.maps(mat)["diffuse color"])
                    tk = gr2_edit.texture_key(tex.values.get("FromFileName")) + ".ddt" if tex is not None else ""
                    if tk in pkg.loose:          # a texture of the package's own: a normal map is owed
                        found["normals"].append(f"{key}: material {mat.values.get('Name')!r} ({tk})")
            if converted is not None and converted.search(low) and not any(p.search(low) for p in exempt) \
                    and (root.get("Meshes") or []):              # a mesh-less bone carries a scale: kept
                a = root.get("ArtToolInfo")
                name = a.get("FromArtToolName") if a is not None else None
                upm = float(a.get("UnitsPerMeter") or 0) if a is not None else 0
                if name != gr2_write.STOCK_BASIS["name"] or abs(upm - gr2_write.STOCK_BASIS["units_per_meter"]) > 1e-4:
                    found["unconverted"].append(f"{key}: {name} {upm:g}")
        elif low.endswith(".ddt") and rules is not None:
            hit = reencode_textures.rule_for(rules, key)
            if hit is None:
                continue
            (u, al, f, m), side, rname, keep, _check = hit
            try:
                hd = ddt.read_header(data)
            except ddt.DdtError as exc:
                found["textures"].append(f"{key}: unreadable ({exc})")
                continue
            want_m = min(m, ddt.chain_length(hd.width, hd.height, 1))
            ok_u = hd.usage == u or ("alpha_test" in keep and hd.usage == (u | 1))
            # a player-colour mask kept over a DXT1 rule: DXT3 with alpha 1
            pc = "player_colour" in keep and f == ddt.DXT1 and hd.format == ddt.DXT3 and hd.alpha == 1
            ok_a = hd.alpha == al or ("transparency" in keep and hd.alpha in (4, 8)) or pc or \
                (f == ddt.DXT1 and hd.format == ddt.DXT3 and hd.alpha in (4, 8))
            ok_f = hd.format == f or pc or (f == ddt.DXT1 and hd.format == ddt.DXT3 and hd.alpha in (4, 8))
            if not (ok_u and ok_a and ok_f and len(hd.levels) == want_m) or max(hd.width, hd.height) > side:
                found["textures"].append(f"{key}: ({hd.usage},{hd.alpha},{hd.format},{len(hd.levels)}) "
                                         f"{hd.width}x{hd.height}, rule {rname} ({u},{al},{f},{want_m}) <= {side}")
    for sha, keys in by_sha.items():
        if len(keys) > 1:
            found["duplicate"].append(" = ".join(keys))
    return found, len(pkg.loose)


def main(argv):
    def opt(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None

    package, lint_file = opt("--package"), opt("--lint")
    if not package or not lint_file:
        print(__doc__)
        return 2
    with open(lint_file, encoding="utf-8") as fh:
        spec = json.load(fh)
    rules = reencode_textures.load_rules(opt("--textures")) if opt("--textures") else None
    game_arts = [hc_survey.Art(argv[i + 1]) for i, a in enumerate(argv) if a == "--art" and i + 1 < len(argv)]
    source_arts = [hc_survey.Art(argv[i + 1]) for i, a in enumerate(argv) if a == "--source" and i + 1 < len(argv)]
    caches = tuple(argv[i + 1] for i, a in enumerate(argv) if a == "--cache" and i + 1 < len(argv))
    bridge = None
    if opt("--granny") and opt("--granny-install"):
        bridge = (opt("--granny"), opt("--granny-install"),
                  os.path.join(caches[0] if caches else os.path.join(package, "_granny_work"), "granny"))
    found, n = lint(package, spec, rules, game_arts, source_arts, bridge, caches)
    lines = [f"{n} files in {package}"]
    for c in CHECKS:
        lines.append(f"{c:15} {len(found[c])}")
    lines.append(f"{'inherited':15} {len(found['inherited'])}  (found nowhere, in the source either: not counted)")
    for c in CHECKS + INFO:
        if found[c]:
            lines.append(f"\n{c}:")
            lines += [f"  {x}" for x in found[c][:20]]
            if len(found[c]) > 20:
                lines.append(f"  ... {len(found[c]) - 20} more")
    text = "\n".join(lines) + "\n"
    print(text)
    out = opt("--out")
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return 1 if any(found[c] for c in CHECKS) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
