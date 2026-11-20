# SPDX-License-Identifier: GPL-3.0-or-later
"""Edits of a whole Granny file: its tree read (gr2.load), copied into the writer's terms
(gr2_write.W, Flat, gr2_types.Spec) with every type as the file declares it, changed, and written
again (gr2_write.serialize). Standard library only.

    root = copy_tree(gr2.load(data))     # the file's root as a W, every object and array in it
    data2 = gr2_write.serialize(root, type_tag=...)
    rewrite(data)                        # both steps: the same tree in a new file

An object reached from two places stays one object (cached by its place in the file). A member
whose name the type gives twice is kept by its index (gr2_write.W). Arrays of
pointer-free elements (vertices, indices, the packed stream) are carried as their bytes. What is
not kept: the three extra words of each member record (written as zero) and the order of the data
in the file (the writer lays it out its own way); `gr2.dump_tree` of the copy equals the
original's, which is what the Granny runtime's own dump shows (measured: docs/game-formats.md).
"""
from . import gr2, gr2_write
from .gr2_types import Spec

TREE_KINDS = (gr2.INLINE, gr2.REFERENCE, gr2.REF_TO_ARRAY, gr2.ARRAY_OF_REFS)


class _Copier:
    def __init__(self, doc):
        self.doc = doc
        self.specs = {}             # typedef key -> Spec
        self.objs = {}              # (section, offset, type key) -> W

    def spec(self, t):
        if t is None:
            return None
        s = self.specs.get(t.key)
        if s is not None:
            return s
        s = Spec(f"t{t.key[0]}_{t.key[1]}", [])
        self.specs[t.key] = s                # before the members: a type may reach itself
        for m in t.members:
            ref = self.spec(self.doc.typedef(m.ref)) if (m.ref and m.kind in TREE_KINDS) else None
            s.members.append((m.kind, m.name, ref, m.width))
        return s

    def obj(self, o):
        if o is None:
            return None
        key = (o.at[0], o.at[1], o.type.key)
        w = self.objs.get(key)
        if w is not None:
            return w
        w = gr2_write.W(self.spec(o.type))
        self.objs[key] = w                   # before the members: objects may reach themselves
        names = [m.name for m in o.type.members]
        for i, m in enumerate(o.type.members):
            # by name, as edits find them; by index where the type names two members alike
            w.values[i if names.count(m.name) > 1 else m.name] = self.value(m, self.doc.value(o.type, o.at, m))
        return w

    def array(self, v):
        if isinstance(v, gr2.Blob):
            return gr2_write.Flat(self.spec(v.type), v.raw, v.count)
        return [self.obj(x) for x in v]

    def value(self, m, v):
        k = m.kind
        if k == gr2.INLINE:
            return [self.obj(x) for x in v] if isinstance(v, list) else self.obj(v)
        if k in (gr2.REFERENCE, gr2.VARIANT_REF):
            return self.obj(v)
        if k == gr2.REF_TO_ARRAY:
            return self.array(v) if v else None
        if k == gr2.REF_TO_VARIANT_ARRAY:
            return self.array(v) if v else None
        if k == gr2.ARRAY_OF_REFS:
            return [self.obj(x) for x in v] if v else None
        if k == gr2.TRANSFORM:
            return (v["flags"],) + tuple(v["position"]) + tuple(v["orientation"]) + tuple(v["scale_shear"])
        return v


def copy_tree(doc):
    """The root of a loaded file as a gr2_write.W, everything under it copied."""
    return _Copier(doc).obj(doc.root())


def rewrite(data):
    """A file's bytes written again from its own tree (a version 6, single-section file with the
    original's type tag). gr2.Compressed for a compressed file."""
    doc = gr2.load(data)
    return gr2_write.serialize(copy_tree(doc), type_tag=doc.c.type_tag)


def texture_key(name):
    r"""A stored texture name as the game resolves it: the part below `art\`, lower case, without
    its last extension (C:\src\Art\units\x\x.tga -> units\x\x). docs/game-formats.md, "A model's
    own texture path" and "Moving a home city's models"."""
    p = str(name).replace("/", "\\").lower()
    i = p.rfind("\\art\\")
    p = p[i + 5:] if i >= 0 else (p[4:] if p.startswith("art\\") else p)
    p = p.split(":")[-1].lstrip("\\")
    base = p.rsplit("\\", 1)
    stem = base[-1].rsplit(".", 1)[0] if "." in base[-1] else base[-1]
    return (base[0] + "\\" + stem) if len(base) == 2 else stem


def stored_name(art_path, prefix="C:\\art\\"):
    r"""The name a model stores for a texture at `art_path` (below art, no extension):
    C:\art\<path>.ddt by default."""
    return prefix + art_path.replace("/", "\\").strip("\\") + ".ddt"


def rename_textures(root, renames):
    """Points the textures of a copied tree (copy_tree) at other files: `renames` maps a
    texture_key to the new stored name. Every texture whose key is listed is renamed, and so is
    any string of a material's ExtendedData that held its old name. Returns [(old, new)]."""
    done, olds = [], {}
    for t in root.values.get("Textures") or []:
        if t is None:
            continue
        old = t.values.get("FromFileName")
        new = renames.get(texture_key(old)) if old else None
        if new is not None and new != old:
            t.values["FromFileName"] = new
            olds[old] = new
            done.append((old, new))
    seen = set()

    def walk(w, depth=0):
        if w is None or id(w) in seen or depth > 8 or not isinstance(w, gr2_write.W):
            return
        seen.add(id(w))
        for k, v in list(w.values.items()):
            if isinstance(v, str) and v in olds:
                w.values[k] = olds[v]
            elif isinstance(v, gr2_write.W):
                walk(v, depth + 1)
            elif isinstance(v, list):
                for x in v:
                    walk(x, depth + 1)

    for m in root.values.get("Materials") or []:
        walk(m)
    return done


def find(root, path):
    """A W under `root` by a path of member names and list indices, e.g. ("Meshes", 0)."""
    cur = root
    for step in path:
        cur = cur[step] if isinstance(step, int) else cur.values[step]
    return cur
