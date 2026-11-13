# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture library: where the textures core/texmaker.py makes are kept, with what they were
made from.

The swatches that ship with the add-on (aoe3_blender_tools/materials/) are CC0 photographs, and
only tools/fetch_materials.py writes there. A texture made here comes from a prompt, or from a
photograph whose licence is the photographer's, so it is kept outside the repository: by default

    ~/Documents/aoe3-blender-tools/textures/<name>.png     the texture, tileable
                                            <name>.json    what it was made from
                                            <name>_x3.png  it tiled 3 by 3, to judge the join

The sidecar always says where it came from and under what licence (`licence` is required: a
photograph someone hands you carries their rights, and nothing else records that). `install()`
puts a texture into core/materials.py's table, so the painter lays it under its drawing where
that style's own swatch was.

Pure Python: numpy for the images, standard library for the rest.
"""
import json
import os
import time

import numpy as np

from . import materials
from .pngio import encode_png, read_png

FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "aoe3-blender-tools", "textures")
SHEET = "_x3"
FIELDS = ("name", "size", "tile_m", "role", "style", "mode", "prompt", "extra", "seed",
          "strength", "source", "seam", "against", "licence", "created")


def folder_of(path=None):
    return os.path.abspath(os.path.expanduser(path or FOLDER))


def _paths(name, folder=None):
    d = folder_of(folder)
    return os.path.join(d, name + ".png"), os.path.join(d, name + ".json")


def save(rgb, name, *, licence, folder=None, tile_m=2.0, role="", style="", report=None,
         source="", strength=None, extra="", sheet=True):
    """Writes the texture, its sidecar and (by default) the 3 by 3 sheet; returns the entry.

    licence: where it may be used and on whose terms, in your own words ("my own photograph",
        "generated locally from a prompt", "CC0, ambientCG Plaster001"). It is required.
    report: what texmaker.make returned, for the prompt, seed, mode and seam.
    source: the file the reference came from, if any.
    """
    if not str(licence).strip():
        raise ValueError("say under what licence this texture may be used (it is kept in the "
                         "sidecar; a photograph carries the rights of whoever took it)")
    if not name or os.path.basename(name) != name:
        raise ValueError(f"a texture's name is a plain file name, not {name!r}")
    a = np.asarray(rgb)[:, :, :3]
    png, meta = _paths(name, folder)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    with open(png, "wb") as f:
        f.write(encode_png(np.ascontiguousarray(a)))
    r = dict(report or {})
    entry = {"name": name, "size": int(a.shape[0]), "tile_m": float(tile_m), "role": role,
             "style": style.upper(), "mode": r.get("mode", ""), "prompt": r.get("prompt", ""),
             "extra": extra, "seed": r.get("seed"), "strength": strength, "source": source,
             "seam": r.get("seam"), "against": r.get("style"), "licence": str(licence).strip(),
             "created": time.strftime("%Y-%m-%d")}
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({k: entry[k] for k in FIELDS}, f, indent=1)
    if sheet:
        from .texmaker import sheet as tile_sheet
        with open(png[:-4] + SHEET + ".png", "wb") as f:
            f.write(encode_png(np.ascontiguousarray(tile_sheet(a))))
    return entry


def read(name, folder=None):
    """The sidecar of one texture, or None."""
    _png, meta = _paths(name, folder)
    if not os.path.exists(meta):
        return None
    with open(meta, encoding="utf-8") as f:
        return json.load(f)


def image(name, folder=None):
    """The texture as an H x W x 3 uint8 array, or None when it is not there."""
    png, _meta = _paths(name, folder)
    if not os.path.exists(png):
        return None
    with open(png, "rb") as f:
        img = read_png(f.read())
    if img.shape[2] == 1:
        img = np.repeat(img, 3, axis=2)
    return img[:, :, :3]


def index(folder=None):
    """Every texture of the library, newest last: {name: entry}. A PNG without a sidecar is
    listed with what can be seen of it, so a texture dropped in by hand is not lost."""
    d = folder_of(folder)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".png") or f.endswith(SHEET + ".png"):
            continue
        name = f[:-4]
        entry = read(name, d)
        if entry is None:
            entry = {k: "" for k in FIELDS}
            entry.update(name=name, licence="unknown", tile_m=2.0)
        out[name] = entry
    return out


def delete(name, folder=None):
    """Removes a texture, its sidecar and its sheet."""
    png, meta = _paths(name, folder)
    for p in (png, meta, png[:-4] + SHEET + ".png"):
        if os.path.exists(p):
            os.remove(p)


_installed = {}


def install(folder=None, styles=None, names=None):
    """Puts the library's textures into core/materials.py's table, each where its style and role
    say: the painter then lays it under its drawing instead of the swatch that ships with the
    add-on. Only entries with both a style and a role are used. Returns {(style, role): name}.

    The colour key and the grain of the role are kept, so the building keeps its colours."""
    chosen = {}
    for name, e in index(folder).items():
        style, role = (e.get("style") or "").upper(), e.get("role") or ""
        if not style or not role:
            continue
        if styles and style not in {s.upper() for s in styles}:
            continue
        if names and name not in names:
            continue
        png, _meta = _paths(name, folder)
        before = materials.MATERIALS.get(style, {}).get(role)
        key = before[2] if before and len(before) > 2 else role
        contrast = before[3] if before and len(before) > 3 else materials.TARGET_CONTRAST
        _installed.setdefault((style, role), before)
        grain = tuple(before[4:5]) if before and len(before) > 4 else ()   # the role's fine band, kept
        materials.MATERIALS.setdefault(style, {})[role] = (png[:-4], float(e.get("tile_m") or 2.0),
                                                           key, contrast) + grain
        chosen[(style, role)] = name
    return chosen


def uninstall():
    """Puts the add-on's own swatches back."""
    for (style, role), before in _installed.items():
        if before is None:
            materials.MATERIALS.get(style, {}).pop(role, None)
        else:
            materials.MATERIALS[style][role] = before
    _installed.clear()
