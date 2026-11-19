# SPDX-License-Identifier: GPL-3.0-or-later
"""The settlement composer's work: a settlement laid round a socket as the mod's own are
(core/settlement.py: distances, counts and a free lane measured on its groupings), moved by hand on
the page, and read from or written to a grouping file (aoe3game/grouping.py).

Positions are game units, x and z as the grouping file stores them; a unit's turn is the angle of
its orientation vector (grouping.orient / angle). Which way the game's x and z run on screen, and
the facing, are still to verify in game."""
import math
import os

from . import use_core

use_core()
from aoe3game import grouping  # noqa: E402
from core import settlement  # noqa: E402

CLASSES = ("building", "prop", "plant", "nature")


class SettlementError(ValueError):
    pass


def measured():
    """What the mod's settlements measure: the bands and the counts the composer uses."""
    g = settlement.measured()
    per = g.get("per_file", settlement.FALLBACK["per_file"])
    return {"clear": (g.get("clear") or settlement.FALLBACK["clear"])[1],
            "building_d": g.get("building_d") or settlement.FALLBACK["building_d"],
            "counts": {c: (per.get(c) or [0, 0, 0])[1] for c in CLASSES},
            "lane": settlement.LANE}


def _catalog(rows, socket, obstruction):
    catalog = {"socket": [(socket or "SocketTradeRoute", 1, 3.0)]}
    for r in rows or []:
        cls, proto = r.get("class"), str(r.get("proto") or "").strip()
        if cls not in CLASSES:
            raise SettlementError(f"a unit's class: one of {', '.join(CLASSES)}")
        if not proto:
            raise SettlementError("every unit needs its proto name")
        try:
            variations, radius = int(r.get("variations") or 1), float(r.get("radius") or 1.5)
        except (TypeError, ValueError):
            raise SettlementError("variations and radius are numbers") from None
        if not (1 <= variations <= 50 and 0.1 <= radius <= 30):
            raise SettlementError("variations 1 to 50, radius 0.1 to 30 game units")
        catalog.setdefault(cls, []).append((proto, variations, radius))
    if obstruction:
        catalog["obstruction"] = [(obstruction, 1, 1.0)]
    return catalog


def compose(rows, *, socket="", obstruction="", seed=1, counts=None):
    """Placements [{"class", "proto", "variation", "x", "z", "turn", "r"}], the socket first."""
    catalog = _catalog(rows, socket, obstruction)
    if not any(catalog.get(c) for c in CLASSES):
        raise SettlementError("give at least one building, prop, plant or nature unit to lay out")
    clean = {}
    for c, n in (counts or {}).items():
        if c in CLASSES and n not in (None, ""):
            clean[c] = max(0, min(60, int(n)))
    return settlement.compose(catalog, seed=int(seed), counts=clean or None)


def read(path):
    """A grouping file as placements (a unit's class guessed from its name: the socket, the
    rest kept as they are), with the file's own width, height, flags and tiles."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            g = grouping.read(fh.read())
    except (OSError, ValueError) as e:
        raise SettlementError(f"not a grouping file: {e}") from None
    units = []
    for u in g["units"]:
        name = u["proto"]
        cls = "socket" if "socket" in name.lower() else "obstruction" if "obstruction" in name.lower() else "unit"
        units.append({"class": cls, "proto": name, "variation": u["variation"], "x": u["x"], "z": u["z"],
                      "turn": round(grouping.angle(u["orient"]), 6), "orient": list(u["orient"]),
                      "r": 3.0 if cls == "socket" else 1.5})
    meta = {"width": g["width"], "height": g["height"], "flags": g["flags"], "tiles": g["tiles"]}
    return {"units": units, "meta": meta}


def text(units, meta=None):
    """The grouping file's text for these placements (the file's own width, height, flags and
    tiles when it was read from one; a new one otherwise)."""
    out = []
    for u in units:
        try:
            x, z, turn = float(u["x"]), float(u["z"]), float(u.get("turn") or 0)
        except (KeyError, TypeError, ValueError):
            raise SettlementError("every unit needs x, z and a turn") from None
        if not (math.isfinite(x) and math.isfinite(z)):
            raise SettlementError("a unit stands nowhere")
        proto = str(u.get("proto") or "").strip()
        if not proto:
            raise SettlementError("every unit needs its proto name")
        o = u.get("orient")                 # the file's own vector, while the unit was not turned
        keep = isinstance(o, (list, tuple)) and len(o) == 3 and abs(grouping.angle(o) - turn) < 1e-4
        out.append({"proto": proto, "variation": int(u.get("variation") or 0), "x": x, "z": z,
                    "orient": tuple(float(v) for v in o) if keep else grouping.orient(turn)})
    m = meta or {}
    g = {"width": m.get("width") or 0, "height": m.get("height") or 0,
         "flags": m.get("flags") if m.get("flags") else None, "tiles": m.get("tiles") if m.get("tiles") else "",
         "units": out}
    return grouping.write(g)


def write(path, units, meta=None):
    if not path.lower().endswith(".xml"):
        raise SettlementError("a grouping is an .xml file")
    data = text(units, meta)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:   # as the game's own files
        fh.write(data)
    return path
