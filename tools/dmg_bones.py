# SPDX-License-Identifier: GPL-3.0-or-later
"""Lists the damage templates whose parts name a bone that the model using them does not have.

    python -I tools/dmg_bones.py <game folder> [--granny-install <game folder>] [--helper <exe>]
                                 [--only <text>] [--csv <out.csv>]

An anim file's <assetreference type="GrannyModel" damagetemplate="X.dmg"> gives the model (its <file>)
the parts of the template X: every <part bone="..."> under its <impactpoint>s. When the model's
skeleton has no bone of that name, the legacy game writes "Invalid bone name ... in part declaration
for model ..." when the damage template is applied (a building or tree dies, a ship is hit), and the
first time that bone name is seen in a session it loads the model again while units still draw
it: the old Granny file is freed under them and the game can crash in its next draw (granny2.dll, or
a model draw in age3y.exe). The fix is in the data: a template made for the model, or no template.

Reads the game folder's art: loose files first, then the art\\*.bar archives (stored .xml and .xmb,
damage templates as .dmg or .dmg.xmb). A compressed model is read by the game's granny2.dll through
tools/recompress_models.py's helper (`--build-helper`; --granny-install defaults to the game folder).
Nothing is written but --csv. Exit status 1 when a template names a missing bone.
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
        self.loose, self.stored = {}, {}
        for folder, _dirs, files in os.walk(self.root):
            for name in files:
                path = os.path.join(folder, name)
                self.loose[os.path.relpath(path, self.root).lower().replace("/", "\\")] = path
        for name in sorted(os.listdir(self.root)):
            if name.lower().endswith(".bar"):
                archive = os.path.join(self.root, name)
                for stored, offset, size in bar.read_entries(archive):
                    key = stored.lower().replace("/", "\\")
                    key = key[4:] if key.startswith("art\\") else key
                    self.stored.setdefault(key, (archive, offset, size))

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
        return ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("﻿")))
    except ET.ParseError:
        return None


class Bones:
    """A model's bone names: this repository's reader, or the game's runtime for a compressed file."""

    def __init__(self, helper, dll):
        self.helper, self.dll, self.cache = helper, dll, {}
        self.work = tempfile.mkdtemp(prefix="dmg_bones_")

    def of(self, art, model):
        key = model.lower().replace("/", "\\")
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


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    game = argv[0]
    opt = {k: argv[argv.index(k) + 1] for k in ("--granny-install", "--helper", "--only", "--csv") if k in argv}
    install = opt.get("--granny-install", game)
    helper = opt.get("--helper", os.path.join(HERE, "granny_recompress.exe"))
    art = Art(game)
    bones = Bones(helper, os.path.join(install, "granny2.dll"))
    anims = sorted(k for k in art.keys() if k.endswith(".xml") or k.endswith(".xml.xmb"))
    if "--only" in opt:
        anims = [k for k in anims if opt["--only"].lower() in k]
    rows, seen, templates = [], set(), {}
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
        for ref in root.iter():
            if ref.tag.lower() != "assetreference":
                continue
            dmg = next((v for k, v in ref.attrib.items() if k.lower() == "damagetemplate"), None)
            files = [c.text.strip() for c in ref if c.tag.lower() == "file" and c.text]
            if not dmg or not files:
                continue
            if dmg.lower() not in templates:
                templates[dmg.lower()] = template_bones(art, dmg)
            dmg_key, wanted = templates[dmg.lower()]
            for model in files:
                have = bones.of(art, model)
                if wanted is None:
                    rows.append((base, model, dmg, "template not found", ""))
                elif have is None:
                    rows.append((base, model, dmg, "model not read", ""))
                else:
                    lower = {h.lower() for h in have}  # the game's bone names ignore case
                    missing = sorted(b for b in wanted if b.lower() not in lower)
                    if missing:
                        rows.append((base, model, dmg, "missing bones", "; ".join(missing)))
    bad = [r for r in rows if r[3] == "missing bones"]
    for r in rows:
        print("\t".join(r))
    print(f"{len(seen)} anim files read; {len(templates)} damage templates; {len(bad)} model and template pairs "
          f"with missing bones; {len(rows) - len(bad)} not checked (template or model not found or not read)")
    if "--csv" in opt:
        with open(opt["--csv"], "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["anim file", "model", "damage template", "result", "bones"])
            w.writerows(rows)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
