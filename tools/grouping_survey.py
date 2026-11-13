# SPDX-License-Identifier: GPL-3.0-or-later
"""Measures the groupings (RM*/groupings/*.xml) of a game or a mod: what a settlement places
round its socket, how far, which way it faces. The settlement composer (core/settlement.py)
works from the profile this writes.

    python -I tools/grouping_survey.py <game or mod folder> [--proto <data/protoy.xml>]
        [--reference <the original game's folder>] [--out <report.json>] [--profile-out <groupings.json>]

What each placed unit is comes from its proto's <UnitType> list (--proto; without it, from its
name alone): the socket, buildings, nature, embellishments (split into plants and props by name),
people, and the invisible obstructions a settlement keeps clear with. A grouping of the mod whose
text is also in the original game (--reference) is **stock**, the rest **own**.

The report names files and protos: it stays private (survey/ is ignored). The profile holds
numbers only (tests/test_profile.py). Standard library only.
"""
import collections
import glob
import hashlib
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import grouping  # noqa: E402

CLASSES = ("socket", "building", "nature", "plant", "prop", "people", "obstruction", "other")
PLANT = re.compile(r"underbrush|grass|bush|plant|flower|tree|reed|fern|shrub|cact|weed|lily|vine")
PEOPLE = re.compile(r"civilian|villager|settler|peasant|monk|priest|merchant|worker|child|woman|man\b")
OBSTRUCTION = re.compile(r"obstruction|pathblock|blocker")


def proto_types(path):
    """{proto name, lower case: [its UnitType]} from a protoy.xml."""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r"<Unit\s+id\s*=\s*['\"]\d+['\"]\s+name\s*=\s*['\"]([^'\"]+)['\"]\s*>(.*?)</Unit>", text, re.S):
        out[m.group(1).lower()] = re.findall(r"<UnitType>([^<]+)</UnitType>", m.group(2))
    return out


def classify(name, types):
    """The class of a placed unit, from its proto's unit types first and its name second."""
    low, t = name.lower(), set(types or ())
    if t & {"Socket", "NativeSocket", "TradePostSocket"} or "socket" in low:
        return "socket"
    if OBSTRUCTION.search(low):
        return "obstruction"
    if t & {"Building", "NativeBuilding", "BuildingClass"}:
        return "building"
    if t & {"Tree", "Nature", "NatureClass", "Resource"} and "EmbellishmentClass" not in t:
        return "nature"
    if "EmbellishmentClass" in t or "prop" in low or "accessory" in low:
        return "plant" if PLANT.search(low) else "prop"
    if PEOPLE.search(low):
        return "people"
    if "Unit" in t or "UnitClass" in t:
        return "people"
    if PLANT.search(low):
        return "plant"
    return "other"


def measure(g, types):
    """The measures of one grouping (its units in game units, the socket at the centre)."""
    units = [dict(u, cls=classify(u["proto"], types.get(u["proto"].lower()))) for u in g["units"]]
    count = collections.Counter(u["cls"] for u in units)
    out = {"units": len(units), "width": g["width"], "height": g["height"], "classes": dict(count)}
    sockets = [u for u in units if u["cls"] == "socket"]
    if len(sockets) != 1:
        return out
    sx, sz = sockets[0]["x"], sockets[0]["z"]
    out["socket_off"] = round(math.hypot(sx, sz), 2)
    near = []
    for u in units:
        if u is sockets[0]:
            continue
        dx, dz = u["x"] - sx, u["z"] - sz
        d = math.hypot(dx, dz)
        u["d"] = d
        if u["cls"] in ("building", "prop", "people", "nature"):
            near.append(d)
    out["clear"] = round(min(near), 2) if near else None
    out["building_d"] = [round(u["d"], 2) for u in units if u["cls"] == "building"]
    out["prop_d"] = [round(u["d"], 2) for u in units if u["cls"] == "prop"]
    out["plant_d"] = [round(u["d"], 2) for u in units if u["cls"] == "plant"]
    out["obstruction_d"] = [round(u["d"], 2) for u in units if u["cls"] == "obstruction"]
    facing = []
    for u in units:
        if u["cls"] != "building" or u["d"] < 1e-3:
            continue
        a = grouping.angle(u["orient"])
        to_socket = math.atan2(sx - u["x"], sz - u["z"])
        facing.append(round(abs((a - to_socket + math.pi) % (2 * math.pi) - math.pi), 3))
    out["building_facing"] = facing
    return out


def survey(folder, types, reference=None):
    files = sorted(set(glob.glob(os.path.join(folder, "RM*", "groupings", "*.xml"))))
    stock = set()
    if reference:
        for f in glob.glob(os.path.join(reference, "RM*", "groupings", "*.xml")):
            stock.add(hashlib.md5(open(f, "rb").read()).hexdigest())
    seen, out = set(), []
    for f in files:
        data = open(f, "rb").read()
        h = hashlib.md5(data).hexdigest()
        if h in seen:                                      # the RM folders repeat each other
            continue
        seen.add(h)
        g = grouping.read(data.decode("utf-8", "replace"))
        m = measure(g, types)
        m.update(path=os.path.relpath(f, folder), origin="stock" if h in stock else "own",
                 name=re.sub(r"\s*\d+$", "", os.path.splitext(os.path.basename(f))[0]).lower())
        out.append(m)
    return out


def _q(values):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return [v[len(v) // 4], v[len(v) // 2], v[(3 * len(v)) // 4]]


def profile(records, least=8):
    """Numbers only: per origin, the settlements (one socket) and every grouping."""
    out = {"measured": "with tools/grouping_survey.py", "groups": []}
    for origin in ("own", "stock", "*"):
        for kind in ("settlement", "*"):
            rs = [r for r in records if (origin == "*" or r["origin"] == origin)
                  and (kind == "*" or "clear" in r)]
            if len(rs) < least:
                continue
            totals = collections.Counter()
            for r in rs:
                totals.update(r["classes"])
            n = sum(totals.values()) or 1
            g = {"origin": origin, "kind": kind, "files": len(rs),
                 "units": _q([r["units"] for r in rs]), "width": _q([r["width"] for r in rs]),
                 "height": _q([r["height"] for r in rs]),
                 "share": {c: round(totals[c] / n, 3) for c in CLASSES if totals[c]},
                 "per_file": {c: _q([r["classes"].get(c, 0) for r in rs]) for c in CLASSES if totals[c]}}
            if kind == "settlement":
                facing = [a for r in rs for a in r["building_facing"]]
                g.update(clear=_q([r["clear"] for r in rs]),
                         building_d=_q([d for r in rs for d in r["building_d"]]),
                         prop_d=_q([d for r in rs for d in r["prop_d"]]),
                         plant_d=_q([d for r in rs for d in r["plant_d"]]),
                         obstruction_d=_q([d for r in rs for d in r["obstruction_d"]]),
                         facing_socket=round(sum(a < math.pi / 4 for a in facing) / max(1, len(facing)), 3),
                         facing_away=round(sum(a > 3 * math.pi / 4 for a in facing) / max(1, len(facing)), 3))
            names = collections.Counter(r["name"] for r in rs)
            g["variants"] = _q(list(names.values()))
            out["groups"].append(g)
    return out


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    folder = next((a for a in argv if not a.startswith("--") and os.path.isdir(a)
                   and a not in (opt("--reference"),)), None)
    if not folder:
        print(__doc__)
        return 2
    types = proto_types(opt("--proto")) if opt("--proto") else {}
    records = survey(folder, types, opt("--reference"))
    print(f"{len(records)} distinct groupings, {sum(1 for r in records if 'clear' in r)} round a socket")
    if opt("--out"):
        os.makedirs(os.path.dirname(os.path.abspath(opt("--out"))), exist_ok=True)
        with open(opt("--out"), "w", encoding="utf-8") as fh:
            json.dump({"groupings": records}, fh, indent=1)
    if opt("--profile-out"):
        with open(opt("--profile-out"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(profile(records), fh, indent=1)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
