# SPDX-License-Identifier: GPL-3.0-or-later
"""Puts a building bundle into a TEST COPY of the game, and takes it out again.

A bundle is a folder with `bundle.json` and the art files at their game paths (art/...):

    {"name": "WhiteHouse", "template": "House",
     "unit": {"AnimFile": "...", "ObstructionRadiusX": 4.5, ...},
     "strings": {"DisplayNameID": "White House", "EditorNameID": "...", ...}}

Rules: any path inside a Steam library is refused; the first backup of a file the deployment
changes is kept as <file>.aoe3bt-orig and never overwritten; every created file is listed in
`aoe3bt-manifest.json` at the root of the copy, which `undo` reads to restore the copy; a
compiled .xmb next to an edited data file is an error (the engine would read it instead).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

from . import proto

MANIFEST = "aoe3bt-manifest.json"
BACKUP = ".aoe3bt-orig"
VALIDATORS = ("validate_proto.py", "validate_techtree.py", "validate_stringtable.py")


class RefusedPath(ValueError):
    pass


def refuse_steam(path):
    p = os.path.abspath(path).replace("/", "\\").lower()
    if "\\steamapps\\" in p + "\\" or "\\steam\\" in p + "\\":
        raise RefusedPath(f"refusing to write inside a Steam library: {path}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Deployment:
    def __init__(self, install):
        refuse_steam(install)
        if not os.path.isdir(os.path.join(install, "data")) or \
                not os.path.isdir(os.path.join(install, "art")):
            raise RefusedPath(f"{install} has no data and art folders: not a game copy")
        self.install = os.path.abspath(install)
        self.manifest_path = os.path.join(self.install, MANIFEST)

    # -- manifest --
    def manifest(self):
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        return {"created": [], "modified": {}, "units": [], "strings": []}

    def save_manifest(self, m):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1)

    def _backup(self, m, path):
        rel = os.path.relpath(path, self.install)
        if rel in m["modified"] or rel in m["created"] or not os.path.exists(path):
            return
        b = path + BACKUP
        if not os.path.exists(b):
            shutil.copy2(path, b)
        m["modified"][rel] = {"backup": rel + BACKUP, "sha256": sha256(b)}

    # -- checks --
    def stale_xmb(self):
        return proto.xmb_twins(os.path.join(self.install, "data"))

    # -- apply / undo --
    def apply(self, bundle_dir, log=print):
        """Copies the bundle's art, adds its unit and strings. Undoes an earlier deployment
        first, so applying again replaces it."""
        if os.path.exists(self.manifest_path):
            self.undo(log=log)
        with open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8") as f:
            b = json.load(f)
        twins = self.stale_xmb()
        if twins:
            raise RefusedPath("compiled data files would shadow the edits: " + ", ".join(twins))
        m = self.manifest()
        m["bundle"] = os.path.abspath(bundle_dir)
        try:
            for dp, _dn, fn in os.walk(os.path.join(bundle_dir, "art")):
                for f in fn:
                    src = os.path.join(dp, f)
                    rel = os.path.relpath(src, bundle_dir)
                    dst = os.path.join(self.install, rel)
                    refuse_steam(dst)
                    if os.path.exists(dst):
                        self._backup(m, dst)
                    else:
                        m["created"].append(rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    log(f"art   {rel}")
            data = os.path.join(self.install, "data")
            spath = os.path.join(data, "stringtabley.xml")
            stext, senc = proto.read_text(spath)
            keys = list(b.get("strings", {}))
            ids = proto.free_locids(stext, len(keys))
            fields = dict(b.get("unit", {}))
            for key, lid in zip(keys, ids):
                fields[key] = lid
            self._backup(m, spath)
            proto.write_text(spath, proto.add_strings(stext, dict(zip(ids, b["strings"].values()))),
                             senc)
            m["strings"] = ids
            log(f"data  stringtabley.xml: strings {ids}")
            ppath = os.path.join(data, "protoy.xml")
            ptext, penc = proto.read_text(ppath)
            index = proto.Index(ptext)
            uid = index.free_id()
            block = proto.clone_unit(proto.unit_text(ptext, b.get("template", "House"), index),
                                     name=b["name"], uid=uid, fields=fields)
            self._backup(m, ppath)
            proto.write_text(ppath, proto.insert_unit(ptext, block), penc)
            m["units"] = [b["name"]]
            m["unit_id"] = uid
            log(f"data  protoy.xml: unit {b['name']} id = DBID = {uid}")
        finally:
            self.save_manifest(m)
        return m

    def undo(self, log=print):
        m = self.manifest()
        for rel in reversed(m.get("created", [])):
            p = os.path.join(self.install, rel)
            if os.path.exists(p):
                os.remove(p)
                log(f"removed  {rel}")
            d = os.path.dirname(p)
            while d.startswith(os.path.join(self.install, "art")) and os.path.isdir(d) \
                    and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
        for rel, info in m.get("modified", {}).items():
            p = os.path.join(self.install, rel)
            b = os.path.join(self.install, info["backup"])
            if os.path.exists(b):
                shutil.copy2(b, p)
                os.remove(b)
                log(f"restored {rel}")
        if os.path.exists(self.manifest_path):
            os.remove(self.manifest_path)

    # -- the game's own validators --
    def validate(self, log=print):
        """Runs the mod's validators found at the root of the copy (cwd = the copy), keeping
        all_paths.txt as it was. Returns {script: (exit code, error lines)}."""
        out = {}
        ap = os.path.join(self.install, "all_paths.txt")
        keep = None
        if os.path.exists(ap):
            with open(ap, "rb") as f:
                keep = f.read()
        env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1")
        try:
            for v in VALIDATORS:
                if not os.path.exists(os.path.join(self.install, v)):
                    continue
                r = subprocess.run([sys.executable, "-I", "-X", "utf8", v], cwd=self.install, env=env,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace")
                lines = (r.stdout + r.stderr).splitlines()
                errors = [l for l in lines if "ERROR" in l]
                out[v] = (r.returncode, errors, lines)
                log(f"{v}: exit {r.returncode}, {len(errors)} error lines")
        finally:
            if keep is not None:
                with open(ap, "wb") as f:
                    f.write(keep)
        return out
