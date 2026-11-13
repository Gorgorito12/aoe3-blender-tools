# SPDX-License-Identifier: GPL-3.0-or-later
"""Props and treasures: map objects (one thing) and treasures (a small accident and its spilled
cargo), built from the African kit's pieces (african/parts.py) and painted by its painter, with
the recipes of recipes.py and the budgets measured on the original game's own props
(`profiles/models.json`, docs/art-findings.md).

Placement reuses the African composer (african/compose.py): a ground map, the main piece solid in
it, every item at the best free spot close to what already stands. The cargo is turned at random,
laid on its side or tipped as its recipe says, and placed until the triangle count reaches the
median of its group, never past the upper quartile. `seed` gives another arrangement.

The low detail model is the same prop without its smaller cargo: a prop has no round wall whose
sides `poly` could lower, and the game draws the low model only with "High Poly Models" off.
"""
import math
from dataclasses import replace

import numpy as np

from ...kit import Builder
from ...painter import _shade
from .. import african
from ..african import compose, parts, program, sizes
from . import recipes

NAME = "PROP"
CHOICES = {"prop_type": recipes.TYPES}
# the median, lowest and highest triangles of a group when no model profile is installed (the
# original game's map objects and treasures, measured 2026-11-10)
FALLBACK = {"objects": (30, 106, 348), "nuggets": (266, 320, 846)}
SMALL = 40              # cargo of fewer triangles is left out of the low detail model


def clamp(p):
    p = replace(p, colors=dict(p.colors))
    v = str(p.prop_type).upper()
    p.prop_type = v if v in recipes.TYPES else recipes.TYPES[0]
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "MEDIUM"
    p.texture_size = 1 << int(round(math.log2(max(128, min(1024, p.texture_size)))))
    p.storeys = 1
    p.portico = p.cupola = p.flagpole = p.wings = p.balcony = p.bell_gable = False
    side = recipes.RECIPES[p.prop_type]["plot"] * sizes.SCALE
    p.width = p.depth = side
    return p


def budget(prop_type):
    """(lowest, target, highest) triangles of a prop: the quartiles of its group."""
    group = recipes.RECIPES[prop_type]["group"]
    try:
        from ... import profile
        g = profile.prop_group(group)
    except Exception:                                     # no model profile: the measured fallback
        g = None
    if g and g.get("tris"):
        q25, q50, q75 = g["tris"]
        return int(q25), int(q50), int(q75)
    return FALLBACK[group]


def game(p):
    """(kind, art folder) its game export uses: treasures go where the game keeps its own."""
    return "PROP", ("nuggets" if p.prop_type in recipes.TREASURES else "objects")


def opening_tops(spec, p):
    return []


def _posed(item, rng, piece):
    """The cargo's pose: a random turn, on its side or tipped as the recipe says."""
    pose = item["kw"].get("pose")
    piece.pop("pose", None)
    piece["turn"] = float(rng.uniform(0.0, 2 * math.pi))
    if pose == "spill":
        pose = "lie" if rng.random() < 0.5 else "lean"
    if pose == "lie":
        piece["tilt"] = math.pi / 2
        piece["lean"] = math.pi / 2 if item["kind"] == "wheel" else float(rng.uniform(0.0, 2 * math.pi))
    elif pose == "lean":
        piece["tilt"] = float(rng.uniform(0.12, 0.3))
        piece["lean"] = float(rng.uniform(0.0, 2 * math.pi))
    return piece


LYING = {"barrel": (0.85, 0.65), "wheel": (0.95, 0.95), "pot": (0.7, 0.7), "sack": (0.7, 0.6)}


def layout(p, medium=True):
    """The pieces of the prop: its main pieces as the recipe gives them, then the cargo placed."""
    r = recipes.RECIPES[p.prop_type]
    out = [dict(m) for m in r["main"]]
    lo, target, hi = budget(p.prop_type)
    g = compose.Ground(r["plot"])
    for m in out:                                          # the main pieces are solid ground
        w, d = compose.size_of({"kind": m["kind"], "kw": m})
        t = m.get("turn", 0.0)
        u = (g.X - m["x"]) * math.cos(t) + (g.Y - m["y"]) * math.sin(t)
        v = (g.Y - m["y"]) * math.cos(t) - (g.X - m["x"]) * math.sin(t)
        g.solid |= (np.abs(u) <= w / 2 + 0.1) & (np.abs(v) <= d / 2 + 0.1)
    g.named["main"] = (out[0]["x"], out[0]["y"])
    rng = np.random.default_rng(int(p.seed) + 104729 * recipes.TYPES.index(p.prop_type))
    count = sum(compose.cost(m) for m in out)

    def add(item):
        nonlocal count
        last = None
        for _ in range(item["count"]):
            kw = dict(item["kw"])
            if kw.get("pose") == "lie" and item["kind"] in LYING and "size" not in kw:
                kw["size"] = LYING[item["kind"]]
            placing = dict(item, kw=kw)
            at = compose.place(g, placing, rng, last)
            if at is None:
                return False
            piece = _posed(placing, rng, compose.piece_of(placing, at[0], at[1], g))
            c = compose.cost(piece)
            if not item["need"] and count + c > hi:
                return False
            out.append(piece)
            count += c
            if item["name"]:
                g.named[item["name"]] = at
            last = at
        return True

    for item in r["cargo"]:
        if item["need"] or count < target:
            add(item)
    more, failed, k = list(r["more"]), 0, 0
    while more and count < target and failed < len(more) and k < 60:
        item = dict(more[k % len(more)], count=1, name=None, near=None, need=False)
        k += 1
        failed = 0 if add(item) else failed + 1
    if not medium:                                         # the low model: its main pieces and big cargo
        out = out[:len(r["main"])] + [pc for pc in out[len(r["main"]):] if compose.cost(pc) >= SMALL]
    return out


def build(p, params):
    medium = p.detail == "MEDIUM"
    pieces = layout(p, medium)
    b = Builder(p.texture_size, True, p.poly)
    facades = parts.declare(b, pieces, True)
    b.pack()
    b._african_facades = facades
    parts.emit(b, pieces, True)                            # a prop carries no flag: no attach point
    k = sizes.SCALE                                        # drawn at a person's size, scaled as the buildings are
    for f in b.faces:
        f.pts = [(x * k, y * k, z * k) for x, y, z in f.pts]
    b.attach = {name: tuple(c * k for c in at) for name, at in b.attach.items()}
    notes = []
    if str(params.prop_type).upper() != p.prop_type:
        notes.append(f"Prop {params.prop_type} -> {p.prop_type}: not a prop this style knows.")
    return b.finish(p, facades, {"type": p.prop_type, "group": recipes.RECIPES[p.prop_type]["group"]}, notes)


def random_params(rng, i, BuildingParams):
    from ...building import AFRICAN_COLORS               # building.py imports the styles: not at the top
    return BuildingParams(
        name=f"Prop{i}", style=NAME, prop_type=rng.choice(recipes.TYPES), detail=rng.choice(["LOW", "MEDIUM"]),
        texture_size=rng.choice([256, 512]), seed=rng.randint(1, 9999), materials=rng.random() < 0.3,
        player_colour=rng.random() < 0.2, colors=dict(AFRICAN_COLORS))


def paint(pr, model):
    african.paint(pr, model)
    at, rng = pr.at, pr.rng
    if "chest" in at:                                      # painted boards, dark joints
        rc = at["chest"]
        red = (128, 46, 34)
        pr.base("chest", red, role="timber")
        v = 0.0
        while v < rc.world_h:
            pr.hline("chest", v, 0, rc.world_w, _shade(red, 0.6))
            v += 0.16
        pr.blotch("chest", 0, 0, rc.world_w, rc.world_h, 0.25, 0.08)
    if "canvas" in at:                                     # weathered canvas, darker along the foot
        rv = at["canvas"]
        cloth = (196, 178, 140)
        pr.fill("canvas", cloth)
        pr.blotch("canvas", 0, 0, rv.world_w, rv.world_h, 0.5, 0.07)
        pr.paint_on("canvas", 0, 0, rv.world_w, 0.3, _shade(cloth, 0.78))
        u = 0.0
        while u < rv.world_w:                              # seams
            pr.vline("canvas", u, 0, rv.world_h, _shade(cloth, 0.85))
            u += 0.6
    if "fruit" in at:                                      # a heap: red, yellow and green, round and bright
        rf = at["fruit"]
        pr.fill("fruit", (104, 70, 40))
        colours = [(186, 46, 34), (214, 168, 44), (98, 140, 46), (200, 92, 30)]
        for _ in range(int(rf.world_w * rf.world_h * 220)):
            u, v = float(rng.uniform(0, rf.world_w)), float(rng.uniform(0, rf.world_h))
            c = colours[int(rng.integers(len(colours)))]
            d = float(rng.uniform(0.05, 0.09))
            pr.rect("fruit", u, v, min(rf.world_w, u + d), min(rf.world_h, v + d), c, _shade(c, 0.6))
    if "char" in at:                                       # burnt mud and timber: soot over earth
        rh = at["char"]
        base = (70, 58, 48)
        pr.base("char", base, role="wall")
        pr.blotch("char", 0, 0, rh.world_w, rh.world_h, 0.35, 0.3)          # soot, unevenly
        pr.blotch("char", 0, 0, rh.world_w, rh.world_h, 0.12, 0.15)         # and ash in it
        pr.cracks("char", 0.25, 0.5, keep=0.6)
