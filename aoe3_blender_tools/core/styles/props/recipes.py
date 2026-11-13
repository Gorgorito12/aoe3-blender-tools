# SPDX-License-Identifier: GPL-3.0-or-later
"""What each prop is made of: a main piece and the cargo spilled round it, in layout metres (a
person's size; the style scales the whole as the African buildings are scaled).

Measured on the original game's own props (docs/art-findings.md, `profiles/models.json`):

- a **map object** is one thing - a rock, a pole with a flag, a stack of crates - at about 100
  triangles (30 / 106 / 348, the quartiles);
- a **treasure** is a small accident, never an object: one main thing tilted or broken (a cart
  with a wheel off, a burnt hut, a tent left behind) and its cargo spilled round it within about
  five units, at about 320 triangles (266 / 320 / 846). The cargo carries the colour (fruit,
  cloth, painted chests) so it reads from the game's camera; the wood stays brown. Never
  symmetrical, never upright.

A recipe: `group`, the profile group whose triangles it is held to ("objects" or "nuggets");
`plot`, the side of the square the cargo stays in; `main`, the pieces placed as given (a pose:
`turn`, `tilt`, `lean`, see african/parts._pose); `cargo`, items placed by the composer in order
(african/program.I; `pose` "lie" puts it on its side, "lean" tips it a little, "spill" either);
`more`, items repeated until the group's median is reached. The composer never goes past the
group's upper quartile.
"""
import math

from ..african.program import I


def M(kind, x=0.0, y=0.0, **kw):
    """A main piece, placed as given."""
    return {"kind": kind, "x": x, "y": y, **kw}


RECIPES = {
    # map objects: one thing
    "ROCKS": {"group": "objects", "plot": 4.6, "main": [M("rock", r=0.95, h=0.85, n=7, seed=1)],
              "cargo": [I("rock", at="wall", need=True, r=0.5, h=0.42, n=6, seed=2, size=(1.0, 1.0)),
                        I("rock", at="wall", r=0.35, h=0.3, n=5, seed=4, size=(0.7, 0.7))],
              "more": [I("rock", at="wall", r=0.3, h=0.25, n=5, seed=6, size=(0.6, 0.6))]},
    "CRATES": {"group": "objects", "plot": 3.8, "main": [M("crate", s=0.36, stacked=True)],
               "cargo": [I("crate", at="wall", need=True), I("barrel", at="wall", pose="lie")],
               "more": [I("crate", at="wall", stacked=True), I("sack", at="wall", pose="lean")]},
    "BARRELS": {"group": "objects", "plot": 3.8, "main": [M("barrel", r=0.3, h=0.8)],
                "cargo": [I("barrel", at="wall", need=True), I("barrel", at="wall", pose="lie")], "more": []},
    "LOGS": {"group": "objects", "plot": 3.4, "main": [M("logs", length=2.2, n=3, r=0.14)],
             "cargo": [], "more": []},
    "WELL": {"group": "objects", "plot": 4.0, "main": [M("well")], "cargo": [I("pot", at="wall", r=0.24, h=0.42)],
             "more": []},
    "CAMPFIRE": {"group": "objects", "plot": 3.6, "main": [M("fire")],
                 "cargo": [I("pot", at="wall", r=0.22, h=0.4, pose="lean")], "more": []},
    "FLAG_POLE": {"group": "objects", "plot": 3.2, "main": [M("pole", h=3.4)],
                  "cargo": [I("rock", at="wall", need=True, r=0.35, h=0.3, n=5, seed=3, size=(0.7, 0.7))],
                  "more": []},
    # treasures: an accident and what it spilled
    "BROKEN_CART": {"group": "nuggets", "plot": 5.4,
                    "main": [M("cart", broken=True, turn=0.35, tilt=0.24, lean=math.pi / 2)],
                    "cargo": [I("wheel", at="wall", need=True, pose="lie"), I("barrel", at="wall", need=True, pose="lie"),
                              I("heap", near="main", need=True), I("crate", at="wall", need=True, pose="lean"),
                              I("sack", at="wall", pose="lean"), I("barrel", at="wall")],
                    "more": [I("sack", at="wall", pose="lean"), I("crate", at="wall"), I("heap", at="wall")]},
    "ABANDONED_CAMP": {"group": "nuggets", "plot": 5.4, "main": [M("tent", turn=-0.3)],
                       "cargo": [I("fire", at="yard", name="fire", need=True), I("pot", near="fire", need=True, pose="lie"),
                                 I("sack", at="wall", need=True, pose="lean"), I("basket", at="wall"),
                                 I("logs", near="fire", length=1.4, n=2, r=0.1)],
                       "more": [I("sack", at="wall", pose="lean"), I("pot", at="wall", pose="spill"),
                                I("basket", at="wall")]},
    "BURNT_HUT": {"group": "nuggets", "plot": 5.0, "main": [M("ruin", r=1.4, h=1.3, seed=3, turn=-1.2)],
                  "cargo": [I("pot", at="wall", need=True, pose="lie"), I("basket", at="wall", need=True, pose="lean"),
                            I("sack", at="wall", pose="lean"), I("logs", at="wall", length=1.6, n=2, r=0.1)],
                  "more": [I("pot", at="wall", pose="spill"), I("heap", at="wall")]},
    "WRECKED_BOAT": {"group": "nuggets", "plot": 5.4, "main": [M("boat", length=3.4, w=0.8, turn=0.4, tilt=0.18)],
                     "cargo": [I("barrel", at="wall", need=True, pose="lie"), I("crate", at="wall", need=True, pose="lean"),
                               I("sack", at="wall", pose="lean"), I("barrel", at="wall")],
                     "more": [I("logs", at="wall", length=1.4, n=2, r=0.08), I("sack", at="wall", pose="lean"),
                              I("heap", at="wall"), I("pot", at="wall", pose="lie")]},
    "LOST_CHEST": {"group": "nuggets", "plot": 4.4, "main": [M("chest", w=1.0, d=0.6, h=0.5, turn=0.5, tilt=0.12,
                                                               lean=0.6)],
                   "cargo": [I("rock", at="wall", need=True, r=0.6, h=0.55, n=7, seed=5, size=(1.2, 1.2)),
                             I("heap", near="main", need=True), I("barrel", at="wall", pose="lie"),
                             I("rock", at="wall", r=0.4, h=0.35, n=6, seed=6, size=(0.8, 0.8))],
                   "more": [I("rock", at="wall", r=0.3, h=0.25, n=5, seed=7, size=(0.6, 0.6)),
                            I("pot", at="wall", pose="spill"), I("heap", at="wall"), I("basket", at="wall", pose="lean")]},
}
TYPES = tuple(RECIPES)
TREASURES = tuple(k for k, r in RECIPES.items() if r["group"] == "nuggets")
