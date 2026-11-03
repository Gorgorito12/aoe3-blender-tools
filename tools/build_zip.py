# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the installable zips of the add-on into dist/.

    python tools/build_zip.py

- dist/aoe3_blender_tools-<version>.zip: the extension (Blender 4.2+: Edit > Preferences >
  Get Extensions > Install from Disk). The manifest sits at the root of the zip.
- dist/aoe3_blender_tools-<version>-legacy.zip: the same files in a folder, for Blender 3.6-4.1
  (Edit > Preferences > Add-ons > Install).
"""
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "aoe3_blender_tools")


def version():
    text = open(os.path.join(PKG, "blender_manifest.toml"), encoding="utf-8").read()
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def files():
    for base, dirs, names in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in sorted(names):
            if not n.endswith((".pyc", ".blend1")):
                full = os.path.join(base, n)
                yield full, os.path.relpath(full, PKG)


def main():
    v = version()
    out = os.path.join(ROOT, "dist")
    os.makedirs(out, exist_ok=True)
    ext = os.path.join(out, f"aoe3_blender_tools-{v}.zip")
    legacy = os.path.join(out, f"aoe3_blender_tools-{v}-legacy.zip")
    with zipfile.ZipFile(ext, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in files():
            z.write(full, rel)
    with zipfile.ZipFile(legacy, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in files():
            z.write(full, os.path.join("aoe3_blender_tools", rel))
    mats = os.path.join(PKG, "materials")
    if os.path.isdir(mats):
        n = sum(os.path.getsize(os.path.join(mats, f)) for f in os.listdir(mats))
        print(f"materials/: {len(os.listdir(mats))} files, {n} bytes")
    for path in (ext, legacy):
        size = os.path.getsize(path)
        print(f"{path} ({size} bytes)")
        if size > 6 * 1024 * 1024:
            raise SystemExit(f"{path} is above 6 MB: keep the material swatches small")


main()
