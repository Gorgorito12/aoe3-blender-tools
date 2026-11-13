# SPDX-License-Identifier: GPL-3.0-or-later
"""Composes a settlement round a socket, as the mod's own groupings do, measured by
tools/grouping_survey.py (`profiles/groupings.json`, docs/art-findings.md). Pure Python.

What the 246 settlements the mod made measure (game units, quartiles):

- 50 / 60 / 72 units a file; nothing stands nearer the socket than 5.3 / 5.6 / 6.3;
- buildings 11.6 / 16.2 / 19.7 from it, 6 of them at the median; props 13, plants and nature
  further out; a fifth of the units are invisible obstructions that keep ground clear;
- only 37 % of the buildings face the socket (within 45 degrees) and 16 % turn their back on it:
  a settlement is not a ring of doors round a square.

The composer places each class in its band of distance, keeps a lane from the socket to the edge
free (units walk to the socket to build on it), never lets two footprints overlap, and gives
`seed` another arrangement: a settlement's numbered variants (3 or 5 of one name, as measured).
It returns placements; aoe3game/grouping.py writes them.
"""
import math
import random

# used when no grouping profile is installed: the mod's own settlements (2026-11-10)
FALLBACK = {"clear": [5.25, 5.61, 6.33], "building_d": [11.62, 16.15, 19.67], "prop_d": [9.61, 13.22, 17.16],
            "plant_d": [9.73, 13.25, 17.5], "facing_socket": 0.367, "facing_away": 0.162,
            "per_file": {"building": [3, 6, 11], "prop": [2, 13, 23], "plant": [1, 2, 7], "nature": [7, 13, 21]}}
LANE = 3.0              # game units: the width kept free from the socket outward
SPACING = 0.4           # game units between two footprints


def measured(origin="own"):
    """The settlement group of the grouping profile, or the fallback."""
    try:
        from . import profile
        art = profile.art("groupings")
        if art is not None:
            for g in art.groups:
                if g.get("origin") == origin and g.get("kind") == "settlement":
                    return g
    except Exception:
        pass
    return FALLBACK


def _in_lane(x, z, lane, half):
    """Whether a point is inside the lane (a strip from the socket toward the angle `lane`)."""
    along = x * math.sin(lane) + z * math.cos(lane)
    across = x * math.cos(lane) - z * math.sin(lane)
    return along > 0 and abs(across) < half


def compose(catalog, seed=1, counts=None, group=None):
    """Placements [{"class", "proto", "variation", "x", "z", "turn", "r"}] in game units, the
    socket first at the origin.

    catalog: {class: [(proto, variations, radius)]} for "socket" (one), "building", "prop",
    "plant", "nature", "obstruction"; a class without entries is not placed. variations: how many
    models its set has (the variation is drawn below it). radius: its footprint's, game units.
    counts: {class: n} to override the measured medians. group: a profile group (measured())."""
    g = group or measured()
    rng = random.Random(seed)
    per = g.get("per_file", FALLBACK["per_file"])
    want = {c: int((counts or {}).get(c, (per.get(c) or [0, 0, 0])[1])) for c in ("building", "prop", "plant", "nature")}
    lane = rng.uniform(0, 2 * math.pi)
    socket = (catalog.get("socket") or [("Socket", 1, 3.0)])[0]
    out = [{"class": "socket", "proto": socket[0], "variation": 0, "x": 0.0, "z": 0.0, "turn": lane, "r": socket[2]}]
    clear = (g.get("clear") or FALLBACK["clear"])[1]

    def free(x, z, r):
        if math.hypot(x, z) < clear + r or _in_lane(x, z, lane, LANE / 2 + r):
            return False
        return all(math.hypot(x - p["x"], z - p["z"]) >= r + p["r"] + SPACING for p in out[1:])

    def place(cls, band, near=None, tries=200):
        entries = catalog.get(cls) or []
        if not entries:
            return None
        proto, variations, r = entries[rng.randrange(len(entries))]
        for _ in range(tries):
            if near is not None:                           # props: beside a building
                b = near[rng.randrange(len(near))]
                a = rng.uniform(0, 2 * math.pi)
                d = b["r"] + r + rng.uniform(SPACING, 2.5)
                x, z = b["x"] + d * math.sin(a), b["z"] + d * math.cos(a)
            else:
                d, a = rng.uniform(band[0], band[1]), rng.uniform(0, 2 * math.pi)
                x, z = d * math.sin(a), d * math.cos(a)
            if free(x, z, r):
                to_socket = math.atan2(-x, -z)
                roll = rng.random()
                if cls == "building" and roll < g.get("facing_socket", 0.37):
                    turn = to_socket + rng.uniform(-0.3, 0.3)
                elif cls == "building" and roll < g.get("facing_socket", 0.37) + g.get("facing_away", 0.16):
                    turn = to_socket + math.pi + rng.uniform(-0.3, 0.3)
                else:
                    turn = rng.uniform(0, 2 * math.pi)
                p = {"class": cls, "proto": proto, "variation": rng.randrange(max(1, variations)),
                     "x": round(x, 4), "z": round(z, 4), "turn": round(turn, 4), "r": r}
                out.append(p)
                return p
        return None

    bd = g.get("building_d") or FALLBACK["building_d"]
    for _ in range(want["building"]):
        place("building", (bd[0], bd[2]))
    buildings = [p for p in out if p["class"] == "building"]
    for _ in range(want["prop"]):
        place("prop", None, near=buildings) if buildings else place("prop", tuple((g.get("prop_d") or FALLBACK["prop_d"])[::2]))
    for cls, key in (("plant", "plant_d"), ("nature", "plant_d")):
        q = g.get(key) or FALLBACK[key]
        for _ in range(want[cls]):
            place(cls, (q[1], q[2] + 3.0))                 # at the rim
    for proto, variations, r in catalog.get("obstruction") or []:   # the clear ground kept, as the real ones do
        ring = clear + r
        for k in range(8):
            a = lane + math.pi / 8 + k * 2 * math.pi / 8
            out.append({"class": "obstruction", "proto": proto, "variation": 0, "x": round(ring * math.sin(a), 4),
                        "z": round(ring * math.cos(a), 4), "turn": 0.0, "r": r})
    return out


def to_grouping(placements):
    """The grouping dict aoe3game/grouping.write takes."""
    try:
        from ..aoe3game import grouping
    except ImportError:                                    # imported as `core`, beside aoe3game
        from aoe3game import grouping
    return {"width": 0, "height": 0, "flags": None, "tiles": "",
            "units": [{"proto": p["proto"], "variation": p["variation"], "x": p["x"], "z": p["z"],
                       "orient": grouping.orient(p["turn"])} for p in placements]}
