# SPDX-License-Identifier: GPL-3.0-or-later
"""The building generator inside the studio's process: core imported as a top-level package, so
Blender never loads. A preview is the model, its texture and its numbers, in a fraction of a
second (`building.build` then `paint.paint`)."""
import base64
import dataclasses
import random
import threading
import time

from . import use_core

use_core()
from core import building, gamemesh, paint, profile, schema, specs  # noqa: E402

import spec_sheets  # noqa: E402  (tools/: the technical sheet of any building)

_profile = None
_lock = threading.Lock()          # the painter's material library is global state: one at a time


def calibration():
    global _profile
    if _profile is None:
        _profile = profile.load()
    return _profile


def presets():
    out = []
    for key, p in building.PRESETS.items():
        out.append({"key": key, "name": p.name, "style": p.style, "detail": p.detail,
                    "type": p.building_type if p.style == "AFRICAN" else p.prop_type if p.style == "PROP" else None,
                    "architecture": p.architecture if p.style == "AFRICAN" else None})
    return out


def preset(key):
    if key not in building.PRESETS:
        raise KeyError(f"no preset {key}")
    return schema.params_to_dict(building.PRESETS[key])


def styles():
    return [{"key": k, "random": hasattr(s, "random_params")} for k, s in building.STYLES.items()]


def random_params(style, seed):
    s = building.STYLES.get(style)
    if s is None or not hasattr(s, "random_params"):
        raise ValueError(f"the {style} style has no random options")
    p = s.random_params(random.Random(seed), seed % 1000, building.BuildingParams)
    return schema.params_to_dict(p)


def _flat(rows, digits):
    return [round(float(c), digits) for r in rows for c in r]


def preview(data, texture=None, damaged=False, parts=True):
    """The model of these parameters as data for the page: mesh, texture (PNG, base64), atlas
    regions, attach points, collision boxes and the numbers. `texture`: a size to paint at in place
    of the parameters' own (a quick preview while a control moves)."""
    p = schema.params_from_dict(data)
    clamped = building.clamp_params(p)
    started = time.perf_counter()
    with _lock:
        # the atlas is laid out for the texture size: a quick preview builds at its own size (the
        # same faces; the regions move by a few pixels at most)
        model = building.build(dataclasses.replace(p, texture_size=texture) if texture else p)
        rgba = paint.paint_rgba(model) if p.player_colour else paint.paint(model)
        dmg = paint.damaged(model, rgba) if damaged else None
    seconds = time.perf_counter() - started
    positions, normals, uvs, tris = gamemesh.mesh(model)
    size = model.atlas.size
    out = {
        "mesh": {"positions": _flat(positions, 4), "normals": _flat(normals, 3), "uvs": _flat(uvs, 5),
                 "indices": [i for t in tris for i in t]},
        "texture": _png(rgba), "texture_size": int(rgba.shape[0]),
        "damaged": _png(dmg) if dmg is not None else None,
        "atlas": {"size": size, "regions": [{"name": n, "box": [round(c, 5) for c in b]}
                                            for n, *b in gamemesh.regions(model)]},
        "attach": {k: [round(c, 3) for c in v] for k, v in model.attach.items()},
        "boxes": [[round(c, 3) for c in b] for b in model.boxes],
        "notes": list(model.notes), "seconds": round(seconds, 2),
        "triangles": len(tris), "vertices": len(positions), "faces": len(model.faces),
        "extent": [round(v, 3) for v in specs.extent(model)],
        "footprint": [round(v, 3) for v in model.dims.get("footprint", (0, 0))],
        "params": schema.params_to_dict(p),
        "clamped": {k: v for k, v in schema.params_to_dict(clamped).items()
                    if k != "colors" and v != getattr(p, k)},
    }
    if parts:
        out["parts"] = specs.tris_by_part(model)
    return out


def _png(array):
    return "data:image/png;base64," + base64.b64encode(paint.png_bytes(array, level=3)).decode("ascii")


def sheet(data):
    """The technical sheet (Markdown) and its facts."""
    p = schema.params_from_dict(data)
    key = next((k for k, v in building.PRESETS.items() if v == p), None)
    with _lock:
        facts = spec_sheets.facts_for(p, calibration(), key)
        text = specs.render(facts)
    cls = (facts.get("game") or {}).get("class")
    measured = calibration().tri_budget(cls) if cls and calibration() else None
    budget = {"class": cls, "band": facts.get("band"),
              "p90": measured[0] if measured else None, "max": measured[1] if measured else None}
    return {"markdown": text, "facts": _plain(facts), "budget": _plain(budget)}


def _plain(v):
    """Data JSON can hold (numpy numbers and tuples included)."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except (ValueError, TypeError):
            return _plain(v.tolist())
    return v
