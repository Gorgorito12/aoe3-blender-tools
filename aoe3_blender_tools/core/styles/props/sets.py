# SPDX-License-Identifier: GPL-3.0-or-later
"""Prop sets: one unit of the game whose models are its variations, all painted on one texture.

Measured on the original game and the mod (2026-11-10, docs/art-findings.md): 525 anim files
pick a model by a `Variation` logic; a set holds 5 / 9 / 20 models (quartiles), and the stock
colony props are 13 small things - barrels, boxes, goods, baskets - each a model of its own. A
grouping places the unit and its `variation` attribute picks the model.

A set here is a list of variants, each a short list of the African kit's pieces at the origin.
Every variant's regions are declared on one builder, so they are packed into one atlas (a region
of the same name is shared: one "crate" painting serves every crate), and each variant is then
emitted into faces of its own and centred on its own footprint.
"""
import math

from ...kit import Builder, Model
from ..african import parts, sizes
from .recipes import M

SETS = {
    # trade goods, as the stock colony set: things a settlement leaves about
    "GOODS": [[M("crate", stacked=True)], [M("crate", s=0.3)], [M("barrel")],
              [M("barrel", tilt=math.pi / 2, lean=0.4, turn=0.3)], [M("sack")], [M("sack", r=0.22, h=0.45, turn=1.0)],
              [M("basket")], [M("pot", r=0.28, h=0.5)], [M("heap")], [M("logs", length=1.6, n=2, r=0.1)]],
    # a camp: what a native settlement or a treasure camp puts round its fire
    "CAMP": [[M("tent")], [M("fire")], [M("pole", h=3.0)], [M("rack", w=1.4)], [M("hide_rack")],
             [M("drum")], [M("rock", r=0.7, h=0.6, n=7, seed=2)]],
}


def build_set(name, *, texture_size=256, seed=1, colors=None, materials=True):
    """(models, combined): a Model per variant, centred on its own footprint, all sharing one
    atlas; and the Model of all of them together, which the painter paints once."""
    from ...building import AFRICAN_COLORS, BuildingParams   # building.py imports the styles
    words = "".join(w.title() for w in name.split("_"))
    p = BuildingParams(name=f"Set{words}", style="PROP", prop_type="ROCKS", texture_size=texture_size, seed=seed,
                       detail="MEDIUM", colors=dict(colors or AFRICAN_COLORS), materials=materials,
                       portico=False, cupola=False)
    variants = [[dict(pc) for pc in v] for v in SETS[name]]
    b = Builder(texture_size, True, p.poly)
    facades = parts.declare(b, [pc for v in variants for pc in v], True)
    b.pack()
    b._african_facades = facades
    k = sizes.SCALE                                         # a person's size, scaled as the buildings are
    models = []
    for i, v in enumerate(variants):
        start = len(b.faces)
        parts.emit(b, v, True)
        faces = b.faces[start:]
        xs = [q[0] for f in faces for q in f.pts]
        ys = [q[1] for f in faces for q in f.pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        for f in faces:
            f.pts = [((x - cx) * k, (y - cy) * k, z * k) for x, y, z in f.pts]
        w, d = (max(xs) - min(xs)) * k, (max(ys) - min(ys)) * k
        dims = {"footprint": (w, d), "height": max(q[2] for f in faces for q in f.pts), "variant": i}
        models.append(Model(p, faces, {}, b.atlas, facades, dims, [], []))
    combined = Model(p, list(b.faces), {}, b.atlas, facades,
                     {"footprint": max((m.dims["footprint"] for m in models), key=lambda s: s[0] * s[1]),
                      "height": max(m.dims["height"] for m in models)}, [], [])
    return models, combined
