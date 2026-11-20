# SPDX-License-Identifier: GPL-3.0-or-later
"""Merges the static models a building hangs on itself (trees on a plantation, a canopy, a hut on
a platform) into the building's own models, and takes their <attach> lines out of the anim file:
the game then draws one model where it drew the building and every attachment.

    python -I tools/merge_attachments.py --manifest <anim files.txt> --art <folder> [--art ...]
                                         --out <folder> [--dry-run] [--cache <folder>]
                                         [--granny <bridge.exe> --granny-install <game folder>]

The manifest lists anim files below art, one per line (`#` starts a comment); paths they name are
looked up in the --art folders in order, loose files first, then each folder's .bar archives.

An attachment is merged when it is static: its definition holds one component whose models are
Granny models only (one, or a Variation of several: the first is taken, so every building of that
kind shows the same pick) with no particle and no animation of its own, or an <include> of an anim
file whose idle model is such a model. Flags (a cloth or an animated flag), smoke, fire, units and
construction frames are left as attachments. For each component of the anim file (not one inside
an <attachment> or an <anim>) that attaches static attachments directly, every model the
component draws, in every branch of its logic (normal, damaged, low detail), is merged with them
(aoe3game/gr2_merge.py: placed as the game hangs them, bound to the bone they hung on) into
`<model stem>_merged.gr2` in the anim file's own folder (`_2`, `_3` for another set), the
component's <file> values name those copies, and the merged <attach> lines are deleted.

Writes into --out, laid out as art: the edited anim files, the merged models (uncompressed:
tools/recompress_models.py compresses them) and merge.txt (what was merged where, and what was left
and why). Nothing is written with --dry-run.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bake_textures  # noqa: E402
import hc_survey  # noqa: E402
from aoe3game import deploy, gr2, gr2_merge  # noqa: E402

ATTACH_RE = re.compile(r"<attach\b([^<>]*?)/?>(\s*</attach\s*>)?", re.I)
ATTR_RE = re.compile(r"([\w.:-]+)\s*=\s*\"([^\"]*)\"")
NOT_STATIC = re.compile(r"\.particle|clothflag|<flag|campfire|construction|\\constructions\\|_con\d?\b|frame|stage\d", re.I)
STATIC_REFUSED = re.compile(r"\.particle|flag|campfire|construction|\\constructions\\|_con\d?\b|frame|stage\d", re.I)
CONSTRUCTION = re.compile(r"construction|\\constructions\\|_con\d?\b|frame|stage\d", re.I)


class Element:
    def __init__(self, tag, start, attrs, parent):
        self.tag, self.start, self.attrs, self.parent = tag, start, attrs, parent
        self.end = None
        self.inner_start = None
        self.children = []

    def ancestors(self):
        p = self.parent
        while p is not None:
            yield p
            p = p.parent

    def text(self, src):
        """Its direct text before the first child."""
        end = self.children[0].start if self.children else (self.end_inner or self.inner_start)
        return src[self.inner_start:end].strip()

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def parse(masked):
    """The element tree of a lenient XML text (comments already blanked), with offsets."""
    root = Element("#root", 0, {}, None)
    root.inner_start, root.end_inner, root.end = 0, len(masked), len(masked)
    stack = [root]
    for m in hc_survey.TAG_RE.finditer(masked):
        closing, tag, attrs, empty = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag:
                    for e in stack[i:]:
                        e.end_inner = m.start() if e is stack[i] else m.start()
                        e.end = m.end()
                    del stack[i:]
                    break
            continue
        el = Element(tag, m.start(), {k.lower(): v[1:-1] for k, v in hc_survey.ATTR_RE.findall(attrs or "")}, stack[-1])
        el.inner_start = m.end()
        el.end_inner = None
        stack[-1].children.append(el)
        if empty:
            el.end = el.end_inner = m.end()
        else:
            stack.append(el)
    return root


def models_in(el, src):
    """The Granny model <file> elements inside an element: [(file element, value)]."""
    out = []
    for e in el.walk():
        if e.tag == "assetreference" and e.attrs.get("type", "").lower() == "grannymodel":
            for c in e.children:
                if c.tag == "file":
                    out.append((c, src[c.inner_start:c.end_inner].strip()))
    return out


class Merger:
    def __init__(self, arts, out, bridge, caches, dry):
        self.arts, self.out, self.bridge, self.caches, self.dry = arts, out, bridge, caches, dry
        self.notes, self.made = [], {}
        self.taken = set()

    def raw(self, key):
        data = self.arts.read(key)
        if data is None:
            return None
        raw, how = hc_survey.raw_bytes(data, self.caches, self.bridge)
        if raw is None:
            raise bake_textures.Refused(f"{key}: {how}: give --granny and --granny-install")
        return raw

    def static_model(self, att, src, anim):
        """The model path a static attachment draws, or (None, why)."""
        # what it draws decides, not its name (SoI calls a tree canopy `iro_tc_smoke_00`)
        if any(e.tag == "assetreference" and e.attrs.get("type", "").lower() not in ("grannymodel",)
               for e in att.walk()):
            return None, "it holds an animation, a particle or a cloth flag"
        values = [v for _e, v in models_in(att, src)] + \
                 [src[e.inner_start:e.end_inner] for e in att.walk() if e.tag in ("file", "include")]
        if any(STATIC_REFUSED.search(v) for v in values):
            return None, "a particle, a flag, a campfire or a construction frame"
        if any(e.tag == "attach" for e in att.walk()):
            return None, "it hangs attachments of its own"
        incs = [e for e in att.walk() if e.tag == "include"]
        if incs:
            key = hc_survey.norm(src[incs[0].inner_start:incs[0].end_inner].strip())
            data = self.arts.read(key) or self.arts.read(key + ".xmb")
            if data is None:
                return None, f"its include {key} is not found"
            text = hc_survey.blank_comments(hc_survey.decode_text(data))
            inner = parse(text)
            # what the included file draws: its components outside any <attachment> definition
            # (a definition nothing attaches any more, once merged, draws nothing)
            drawn = [e for e in inner.walk() if e.tag == "component"
                     and not any(a.tag == "attachment" for a in e.ancestors())]
            used = [e for c in drawn for e in c.walk()]
            if any(e.tag == "attach" for e in inner.walk()) or \
                    any(e.tag == "assetreference" and e.attrs.get("type", "").lower() != "grannymodel" for e in used) or \
                    any(e.tag == "anim" for e in inner.walk() if any(x.tag == "assetreference" for x in e.walk())) or \
                    any(NOT_STATIC.search(text[c.inner_start:c.end_inner]) for c in drawn):
                return None, f"its include {key} is not a static model"
            found = [m for c in drawn for m in models_in(c, text)]
            if len({v.lower() for _e, v in found}) > 1 and not any(e.tag == "logic" for e in used):
                return None, f"its include {key} draws several models"
            return (found[0][1], None) if found else (None, f"its include {key} draws no model")
        found = models_in(att, src)
        if not found:
            return None, "no model"
        return found[0][1], None

    def bake_anim(self, anim):
        found = self.arts.find(anim) or self.arts.find(anim + ".xmb")
        if found is None:
            self.notes.append(f"{anim}: not found")
            return 0
        key = anim if found.exists(anim) else anim + ".xmb"
        text = hc_survey.decode_text(found.read(key))
        masked = hc_survey.blank_comments(text)
        tree = parse(masked)
        statics = {}
        for e in tree.walk():
            if e.tag == "attachment":
                name = e.text(masked)
                if not name:
                    continue
                model, why = self.static_model(e, masked, anim)
                if model:
                    statics.setdefault(name.lower(), model)
                elif why:
                    self.notes.append(f"{anim}: attachment {name} left as it is: {why}")
        folder = os.path.dirname(found.display(key))
        edits, merged = [], 0
        for comp in tree.walk():
            if comp.tag != "component" or any(a.tag in ("attachment", "anim") for a in comp.ancestors()):
                continue
            lines = [c for c in comp.children if c.tag == "attach" and c.attrs.get("a", "").lower() in statics]
            if not lines:
                continue
            parts_spec = [(statics[c.attrs["a"].lower()], c.attrs.get("frombone", ""), c.attrs.get("tobone", ""))
                          for c in lines]
            bodies = models_in(comp, masked)
            if not bodies:
                continue
            if any(CONSTRUCTION.search(v) for _f, v in bodies):
                self.notes.append(f"{anim}: a construction stage keeps its attachments (the game's own pattern)")
                continue
            done = True
            for fel, value in bodies:
                new = self.merged(folder, value, parts_spec, anim)
                if new is None:
                    done = False
                    continue
                edits.append((fel.inner_start, fel.end_inner, new))
            if done:
                for c in lines:
                    s, e = bake_textures.line_span(text, c.start, c.end)
                    edits.append((s, e, ""))
                merged += 1
        if edits and not self.dry:
            out = text
            for s, e, rep in sorted(edits, key=lambda t: t[0], reverse=True):
                out = out[:s] + rep + out[e:]
            self.write(found.display(key)[:-4] if key.endswith(".xmb") else found.display(key), out.encode("utf-8"))
        return merged

    def merged(self, folder, body_value, parts_spec, anim):
        """The path (below art, no extension) of the body merged with its parts, made once."""
        ident = (hc_survey.norm(body_value), tuple((hc_survey.norm(m), f, t) for m, f, t in parts_spec))
        if ident in self.made:
            return self.made[ident]
        body_key = hc_survey.model_key(body_value)
        try:
            body = self.raw(body_key)
            if body is None:
                raise bake_textures.Refused(f"{body_key} not found")
            bones = [b.get("Name") or "" for sk in (gr2.load(body).root().get("Skeletons") or [])
                     for b in (sk.get("Bones") or [])]
            if any(b.lower().startswith("bip01") for b in bones):
                raise bake_textures.Refused("a character rig (Bip01): its accessories stay attachments")
            parts = []
            for m, f, t in parts_spec:
                pr = self.raw(hc_survey.model_key(m))
                if pr is None:
                    raise bake_textures.Refused(f"{m} not found")
                parts.append((pr, f, t))
            out, info = gr2_merge.merge(body, parts)
        except (bake_textures.Refused, gr2_merge.Refused, gr2.Gr2Error, KeyError, ValueError) as exc:
            self.notes.append(f"{anim}: {body_value} not merged: {exc}")
            self.made[ident] = None
            return None
        stem = os.path.splitext(os.path.basename(body_key))[0]
        n, rel = 1, None
        while rel is None or rel.lower() in self.taken or self.arts.exists(hc_survey.norm(rel) + ".gr2"):
            rel = f"{folder}\\{stem}_merged" + ("" if n == 1 else f"_{n}")
            n += 1
        self.taken.add(rel.lower())
        if not self.dry:
            self.write(rel + ".gr2", out)
        self.notes.append(f"{anim}: {body_value} + {len(parts)} attachments ({info['meshes']} meshes, "
                          f"{info['triangles']} triangles) -> {rel}")
        self.made[ident] = rel
        return rel

    def write(self, rel, data):
        p = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".merging", "wb") as fh:
            fh.write(data)
        os.replace(p + ".merging", p)


def main(argv):
    args = {"manifest": None, "art": [], "out": None, "granny": None, "install": None, "cache": [], "dry": False}
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("--manifest", "--out", "--granny"):
                args[a[2:]], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
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
        anims = [hc_survey.norm(line.split("#", 1)[0].split("\t")[0]) for line in fh
                 if line.split("#", 1)[0].strip()]
    bridge = None
    if args["granny"]:
        work = os.path.join(args["cache"][0], "granny") if args["cache"] else os.path.join(args["out"], "_granny_work")
        bridge = (args["granny"], args["install"], work)
    m = Merger(bake_textures.Arts(args["art"]), args["out"], bridge, tuple(args["cache"]), args["dry"])
    total = 0
    # Passes until nothing more merges: an attachment that is itself a carrier with attachments
    # (an include of trees on an invisible field) becomes static once its own pass merged it.
    for n in range(1, 5):
        if n > 1:
            if args["dry"]:
                break
            m.arts = bake_textures.Arts([args["out"]] + args["art"])
        this = 0
        for anim in anims:
            try:
                this += m.bake_anim(anim)
            except (bake_textures.Refused, OSError) as exc:
                m.notes.append(f"{anim}: refused: {exc}")
        total += this
        if not this:
            break
    made = sum(1 for v in m.made.values() if v)
    if not args["dry"]:
        os.makedirs(args["out"], exist_ok=True)
        with open(os.path.join(args["out"], "merge.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(m.notes) + "\n")
    print(f"{len(anims)} anim files, {total} components merged, {made} merged models, "
          f"{sum(1 for v in m.made.values() if v is None)} not merged" + (" (dry run)" if args["dry"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
