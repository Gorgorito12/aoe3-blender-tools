# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibration profiles: measurements of a game's or mod's buildings (`tools/art_survey.py
--profile-out`), used to size, budget and check generated buildings. Pure Python.

A profile groups the measured buildings by their obstruction footprint in game units (class
"8x8" = an obstruction square of 8 units, ObstructionRadius 4). Game units: the stock buildings
declare 0.615157485 model units per metre, and obstructions and decals are in those units.
"""
import json
import math
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "profiles", "buildings.json")
UNITS_PER_METER = 0.615157485
FALLBACK = {"obstruction_over_half_side": 0.85, "decal_over_side": 1.25}
MIN_CLASS_COUNT = 3
SELECT_MIN = 10        # buildings a class needs to be chosen by its model size


def load(path=None):
    """The profile at `path` (default: the one shipped with the add-on), or None."""
    p = path or DEFAULT_PATH
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return Profile(json.load(f))


def _side(key):
    a, b = key.split("x")
    return max(float(a), float(b))


class Profile:
    def __init__(self, data):
        self.data = data
        self.units_per_meter = data.get("units_per_meter_game", UNITS_PER_METER)
        self.classes = {k: v for k, v in data.get("classes", {}).items()
                        if v.get("count", 0) >= MIN_CLASS_COUNT and "x" in k}

    def _median(self, cls, key):
        c = self.classes.get(cls) or {}
        q = c.get(key)
        return q["median"] if q else FALLBACK.get(key)

    def footprint_class(self, width_m, depth_m):
        """The measured class for a building of this footprint (metres): among the classes
        measured on SELECT_MIN buildings or more, the one whose median model side is closest
        (in ratio) to this building's longer side. Without those measurements, the class whose
        obstruction side is closest to what this footprint would get.

        Matching the model's own size keeps a class with few, odd members from attracting every
        large building; a non-square class also needs a building's obstruction ratio (0.8 or
        more: long walls and gates have far less)."""
        if not self.classes:
            return None
        side = max(width_m, depth_m) * self.units_per_meter
        def candidate(k, v):
            a, b = k.split("x")
            square = a == b
            ratio = self._median(k, "obstruction_over_half_side") or 0
            return (v.get("count", 0) >= SELECT_MIN and (v.get("side_units") or {}).get("median")
                    and (square or ratio >= 0.8))
        pool = [k for k, v in self.classes.items() if candidate(k, v)]
        if pool and side > 0:
            return min(pool, key=lambda k: abs(math.log(side / self.classes[k]["side_units"]["median"])))

        def obstruction_side(key):
            ratio = self._median(key, "obstruction_over_half_side")
            return side * ratio

        return min(self.classes, key=lambda k: abs(_side(k) - obstruction_side(k)))

    def obstruction_ratio(self, cls):
        return self._median(cls, "obstruction_over_half_side")

    def decal_ratio(self, cls):
        return self._median(cls, "decal_over_side")

    def tri_budget(self, cls):
        """(p90, max) triangles of the class's buildings, or None."""
        c = self.classes.get(cls)
        if not c or not c.get("tris"):
            return None
        return int(c["tris"]["p90"]), int(c["tris"]["max"])

    def stages(self, cls):
        c = self.classes.get(cls) or {}
        st = c.get("stages") or []
        return st[0][0] if st else None

    def rubble(self, cls):
        c = self.classes.get(cls) or {}
        r = c.get("rubble") or []
        return r[0][0] if r else None


# --------------------------------------------------------------------------------------------------
# What the textures and the models of the mod measure (tools/texture_survey.py, model_survey.py)

FOLDER = os.path.dirname(DEFAULT_PATH)
_art = {}


def art(name):
    """The profile `name` ("textures", "props", "units", "models") shipped with the add-on, as
    an Art, or None when it is not there. Read once."""
    if name not in _art:
        p = os.path.join(FOLDER, name + ".json")
        _art[name] = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _art[name] = Art(json.load(f))
    return _art[name]


def prop_group(folder="objects"):
    """The group of the model profile a prop is held to: the original game's map objects, or
    its treasures for "nuggets" (the mod added too few of either to measure). None without the
    profile."""
    models = art("models")
    if models is None:
        return None
    wanted = models.group("stock", "nuggets" if folder == "nuggets" else "objects")
    return wanted or models.group("stock", "objects")


class Art:
    """A profile made of groups of measurements. A group is found by what it is - its origin
    (own: made by the mod; stock: the original game's), its category (the original game's folder
    names, or "*" for all), and for textures its role and material - never by a file."""

    def __init__(self, data):
        self.data = data
        self.groups = data.get("groups", [])

    def group(self, origin="own", category="*", role=None, material=None, least=8):
        """The group that matches, or None. A missing role or material is not compared."""
        for g in self.groups:
            if g.get("origin") != origin or g.get("category") != category:
                continue
            if role is not None and g.get("role") != role:
                continue
            if material is not None and g.get("material") != material:
                continue
            if g.get("count", 0) >= least:
                return g
        return None

    def nearest(self, category="*", role=None, material=None, least=8):
        """The best group there is for this: the mod's own art of that material and category
        first, then of the material anywhere, then of the category, then the original game's
        in the same order. (group, how it was found), or (None, None)."""
        tries = []
        for origin in ("own", "stock"):
            if material not in (None, "", "*"):
                tries += [(origin, category, material), (origin, "*", material)]
            tries += [(origin, category, "*" if role is not None else None), (origin, "*", "*" if role is not None else None)]
        for origin, cat, mat in tries:
            g = self.group(origin, cat, role, mat, least)
            if g is not None:
                what = f"{origin} {cat if cat != '*' else 'art'}" + (f", {mat}" if mat not in (None, "*") else "")
                return g, what
        return None, None
