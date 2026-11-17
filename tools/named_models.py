# SPDX-License-Identifier: GPL-3.0-or-later
"""Finds the models of a list in a game copy or a mod: what tools/model_sheets.py --models renders.
Run alone, it prints what each entry resolves to (no Blender needed), to check a list first.

    python -I tools\\named_models.py <list.txt> --game <game folder> [--prefer a,b]

The list holds one entry per line, `caption | target` (a line without `|` is its own caption;
blank lines and lines starting with # are skipped). A target is:

    a proto name       ypThuggee: its <AnimFile> in the game's protoy.xml, then the model that
                       anim file shows standing (aoe3game/animxml.idle_model)
    an anim file       units\\...\\x.xml: the same, from the anim file
    a model            units\\...\\x.gr2, or a path with no extension

A proto or an anim file may end in @branch[,branch...]: the branches of its logics to show
first (a culture, a civ, an age's tech: Stable@mediterranean, House@brazilian,industrialize),
before those of --prefer, which apply to every entry. Without one, a logic shows its first
branch. When the model a branch names is missing, the next candidate is shown and the report
says so.

--overlay: a folder laid out like a game copy (art\\, data\\) whose loose files win over the
game's, to look at new art or anim files before they are installed.

Paths are relative to the game's art folder. Files are read loose first, then from the .bar
archives (art\\*.bar; data\\*.bar for protoy.xml), plain or compiled (.xmb). Nothing is written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import fix_hitpointbar_tags as fh  # noqa: E402
from aoe3game import animxml  # noqa: E402

NOT_DIFFUSE = ("_b", "_n", "_nm", "_spec", "_s", "_bump", "_normal")


class Missing(LookupError):
    """An entry with no model to show: `short` for a sheet's cell, the message for its report."""

    def __init__(self, short, message):
        super().__init__(message)
        self.short = short


def parse_list(text):
    """[(caption, target)] of a list's text."""
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        caption, sep, target = line.partition("|")
        caption, target = caption.strip(), target.strip()
        if not sep:
            target = caption
        if not target:
            raise ValueError(f"no model in the line {line!r}")
        out.append((caption or target, target))
    return out


def split_prefer(target):
    """(target, [branch names in lower case]) of `name@a,b`."""
    base, sep, rest = target.rpartition("@")
    if not sep or not base or "\\" in rest or "/" in rest:
        return target, []
    return base.strip(), [b.strip().lower() for b in rest.split(",") if b.strip()]


def kind(target):
    """proto, anim or model."""
    low = split_prefer(target)[0].lower()
    if low.endswith((".xml", ".xml.xmb")):
        return "anim"
    if low.endswith(".gr2") or "\\" in target or "/" in target:
        return "model"
    return "proto"


class Game:
    """The art and the protos of a game copy or a mod, read on demand."""

    def __init__(self, folder, overlays=()):
        """`overlays`: folders laid out like a game copy (their art and data folders) whose
        loose files win over the game's: new art and a changed protoy.xml seen before they are
        installed."""
        self.folder = folder
        self.overlays = [o for o in overlays if o]
        self.art = fh.Art(os.path.join(folder, "art"))
        for extra in self.overlays:
            art = os.path.join(extra, "art")
            for top, _dirs, files in os.walk(art):
                for name in files:
                    full = os.path.join(top, name)
                    self.art.loose[fh.norm(os.path.relpath(full, art))] = full
        self._protos = None
        self._ddt = None

    def proto_source(self):
        """(bytes, where) of protoy.xml: loose (plain, then .xmb), then in data\\*.bar."""
        for extra in reversed(self.overlays):
            for name in ("protoy.xml", "protoy.xml.xmb"):
                path = os.path.join(extra, "data", name)
                if os.path.isfile(path):
                    with open(path, "rb") as fh_:
                        return fh_.read(), path
        data = os.path.join(self.folder, "data")
        for name in ("protoy.xml", "protoy.xml.xmb"):
            path = os.path.join(data, name)
            if os.path.isfile(path):
                with open(path, "rb") as fh_:
                    return fh_.read(), path
        if os.path.isdir(data):
            for name in sorted(os.listdir(data)):
                if not name.lower().endswith(".bar"):
                    continue
                archive = os.path.join(data, name)
                for stored, offset, size in bar.read_entries(archive):
                    if os.path.basename(stored.replace("\\", "/")).lower() in ("protoy.xml", "protoy.xml.xmb"):
                        with open(archive, "rb") as fh_:
                            fh_.seek(offset)
                            return fh_.read(size), f"{name}:{stored}"
        raise LookupError(f"no protoy.xml in {data}")

    def protos(self):
        """{proto name in lower case: (name, AnimFile or None)}."""
        if self._protos is None:
            raw, _where = self.proto_source()
            self._protos = {}
            for unit in fh.anim_tree(raw).iter("unit"):
                name = (unit.get("name") or "").strip()
                anim = unit.find("animfile")
                text = (anim.text or "").strip() if anim is not None else ""
                self._protos.setdefault(name.lower(), (name, text or None))
        return self._protos

    def resolve(self, target, prefer=()):
        """{"model": art path of the .gr2, "anim": anim file or None, "proto": name or None,
        "skipped": [models the anim file names first that are missing], "replace": {texture:
        texture} its <replacetexture> asks (art paths in lower case, no extension),
        "attachments": what hangs on that model standing (animxml.idle_attachments)}. Missing
        says why an entry has no model. `prefer`: branch names, after the target's own @branches."""
        target, own = split_prefer(target)
        prefer = own + [b.lower() for b in prefer]
        what = kind(target)
        out = {"proto": None, "anim": None, "skipped": [], "replace": {}, "attachments": []}
        if what == "proto":
            found = self.protos().get(target.lower())
            if found is None:
                raise Missing("no such proto", f"no proto named {target}")
            out["proto"], out["anim"] = found[0], found[1]
            if not out["anim"]:
                raise Missing("no AnimFile", f"{found[0]} has no <AnimFile>")
        elif what == "anim":
            out["anim"] = target[:-4] if target.lower().endswith(".xmb") else target
        if out["anim"]:
            raw = self.art.anim_file(out["anim"])
            if raw is None:
                raise Missing("anim file missing",
                              f"anim file {out['anim']} is not in the art folder (loose or archived)")
            tree = fh.anim_tree(raw[0])
            candidates = list(animxml.idle_assets(tree, prefer))
            out["attachments"] = animxml.idle_attachments(tree, prefer)
            if not candidates:
                raise Missing("no model in anim file", f"anim file {out['anim']} names no Granny model")
        else:
            candidates = [(target, ())]
        for model, swaps in candidates:
            model = fh.norm(model)
            if not model.endswith(".gr2"):
                model += ".gr2"
            if self.art.find(model) is not None:
                out["model"] = model
                out["replace"] = {fh.norm(a): fh.norm(b) for a, b in swaps}
                return out
            out["skipped"].append(model)
        raise Missing("model file missing", f"model {out['skipped'][0]} is not in the art folder "
                      "(loose or archived)" + (f", nor the {len(candidates) - 1} other models of "
                                               "its anim file" if len(candidates) > 1 else ""))

    def read(self, path):
        """(bytes, where) of an art file, loose first."""
        found = self.art.find(path)
        if found is None:
            raise Missing("file missing", f"{path} is not in the art folder")
        return found[0], found[1]

    def texture(self, names, model, replace=None):
        """(art path of the .ddt, bytes) of the first diffuse texture of `names` (as a model
        stores them: a path or a bare name) found in the art folder, or None. A name found in
        several folders: the model's own folder first, then a loose file, then an archived one.
        `replace`: resolve()'s, the anim file's texture swaps, matched on the art path (or, for
        a bare name, the file name)."""
        if self._ddt is None:
            self._ddt = {}
            for key in list(self.art.loose) + list(self.art.archived):
                if key.endswith(".ddt"):
                    stem = os.path.splitext(os.path.basename(key))[0]
                    keys = self._ddt.setdefault(stem, [])
                    if key not in keys:
                        keys.append(key)
        home = os.path.dirname(fh.norm(model))
        for name in names:
            if not name:
                continue
            plain = str(name).replace("/", "\\")
            stem = os.path.splitext(os.path.basename(plain))[0].lower()
            if stem.endswith(NOT_DIFFUSE):
                continue
            keys = []
            to = _swap(plain, replace or {})
            if to:
                keys.append(to + ".ddt")
            if ":" not in plain:
                keys.append(os.path.splitext(fh.norm(plain))[0] + ".ddt")
            cands = self._ddt.get(stem, [])
            keys += [k for k in cands if os.path.dirname(k) == home] + cands
            for key in keys:
                found = self.art.find(key)
                if found is not None:
                    return key, found[0]
        return None


def art_key(name):
    r"""A texture name as a model stores it, as an art path: lower case, no extension, from the
    folder below art (C:\src\Art\units\x\x.ddt -> units\x\x)."""
    p = str(name).replace("/", "\\").lower()
    i = p.rfind("\\art\\")
    p = p[i + 5:] if i >= 0 else (p[4:] if p.startswith("art\\") else p)
    return os.path.splitext(p.split(":")[-1].lstrip("\\"))[0]


def _swap(name, replace):
    key = art_key(name)
    if key in replace:
        return replace[key]
    stem = key.rsplit("\\", 1)[-1]
    if "\\" not in key:
        for frm, to in replace.items():
            if frm.rsplit("\\", 1)[-1] == stem:
                return to
    return None


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    lst = next((a for a in argv if not a.startswith("--") and a not in (opt("--game"), opt("--prefer"),
                                                                       opt("--overlay"))), None)
    game = opt("--game")
    if not lst or not game:
        print(__doc__)
        return 2
    with open(lst, encoding="utf-8-sig") as fh_:
        entries = parse_list(fh_.read())
    g = Game(game, [opt("--overlay")])
    prefer = [b for b in (opt("--prefer") or "").split(",") if b]
    bad = 0
    for caption, target in entries:
        try:
            r = g.resolve(target, prefer)
            via = f" (anim {r['anim']})" if r["anim"] else ""
            miss = f"; missing first: {', '.join(r['skipped'])}" if r["skipped"] else ""
            hung = [f"{a['name']} {a['model'] or a['include']} on {a['tobone']}" for a in r["attachments"]]
            print(f"{caption}: {r['model']}{via}{miss}" + (f"; hangs: {', '.join(hung)}" if hung else ""))
        except LookupError as exc:
            bad += 1
            print(f"{caption}: NOT FOUND - {exc}")
    print(f"{len(entries) - bad} of {len(entries)} resolved")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
