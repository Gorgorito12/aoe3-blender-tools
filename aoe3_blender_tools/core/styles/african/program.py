# SPDX-License-Identifier: GPL-3.0-or-later
"""What each African building holds, by what it is for and who built it. A building is believable
when its yard explains it: an armory has a forge, an anvil and bellows beside it, a quarry cut
stone, crates and barrels. The structure lives in layouts.py; this is the program compose.py
places around it.

An item: its kind (a prop of parts.py), how many, where it goes and the keywords of the prop.
`at`: "wall" against a building, "yard" wherever it fits next to the rest, "shade" under an awning
or a shed, "edge" the same as "yard". `near`: the name of an item to stay close to, and
`name`: the name others use. `on`: "deck", on a dock's boards. `need`: placed whatever the triangle
budget says. Order is priority: what a building cannot do without comes first; `more` is repeated
until the budget is reached."""


def I(kind, count=1, at="yard", near=None, name=None, need=False, on=None, **kw):
    return {"kind": kind, "count": count, "at": at, "near": near, "name": name, "need": need, "on": on, "kw": kw}


# a smith's essentials, shared
SMITHY = [I("anvil", at="shade", name="anvil", need=True), I("trough", near="anvil", need=True, w=0.55)]

PROGRAM = {
    "HOUSE": {
        "SUBSAHARAN": [I("pot", at="wall", need=True), I("basket", at="wall")],
        "SAHEL": [I("pot", at="wall", need=True), I("basket", at="wall")],
        "more": [I("sack", at="wall"), I("basket", on="roof"), I("pot", on="roof"), I("sack", on="roof"), I("crate", on="roof")],
    },
    "TOWN_CENTER": {
        "SUBSAHARAN": [I("fire", at="yard", name="hearth", need=True), I("drum", 2, near="hearth", need=True),
                       I("rack", at="wall"), I("pot", 2, at="wall"), I("hide_rack", at="yard"), I("basket", 3, at="wall")],
        "SAHEL": [I("well", at="yard", name="well", need=True), I("rack", at="wall"), I("pot", 2, near="well"),
                  I("crate", 2, at="wall", stacked=True), I("barrel", 2, at="wall"), I("logs", at="edge", length=1.8, n=3)],
        "more": [I("basket", 2, at="wall"), I("sack", 2, at="wall"), I("barrel", at="wall"), I("crate", on="roof", stacked=True),
                 I("sack", on="roof"), I("pot", on="roof"), I("basket", on="roof")],
    },
    "GRANARY": {
        "SUBSAHARAN": [I("sack", 2, at="wall"), I("basket", 2, at="wall")],
        "SAHEL": [I("sack", 3, at="wall", need=True), I("pot", at="wall")],
        "more": [I("basket", at="wall")],
    },
    "MARKET": {
        "SUBSAHARAN": [I("well", name="well", need=True), I("crate", 3, at="shade", stacked=True, need=True),
                       I("barrel", 2, at="shade", need=True), I("sack", 3, at="shade"), I("basket", 4, at="shade"),
                       I("pot", 3, at="shade")],
        "SAHEL": [I("well", name="well", need=True), I("crate", 3, at="shade", stacked=True, need=True),
                  I("barrel", 3, at="shade", need=True), I("sack", 3, at="shade"), I("basket", 4, at="shade"),
                  I("logs", at="edge", length=1.8, n=3), I("pot", 2, at="shade")],
        "more": [I("basket", 2, at="shade"), I("crate", at="yard")],
    },
    "WAR_CAMP": {
        "SUBSAHARAN": [I("fire", name="fire", need=True), I("rack", 2, at="wall", need=True), I("dummy", 2, need=True),
                       I("shields", at="wall"), I("drum", 2, near="fire"), I("hide_rack", at="edge")],
        "SAHEL": [I("fire", name="fire", need=True), I("rack", 2, at="wall", need=True), I("dummy", 2, need=True),
                  I("shields", at="wall", a=0.34, c=0.34), I("drum", 2, near="fire"), I("barrel", at="wall")],
        "more": [I("basket", at="wall"), I("dummy", at="yard")],
    },
    "STOCKADE": {
        "SUBSAHARAN": [I("pot", 2, at="wall", need=True), I("fire", at="yard"), I("rack", at="wall"), I("drum", at="wall")],
        "SAHEL": [I("well", need=True), I("pot", at="wall"), I("rack", at="wall"), I("crate", at="wall", stacked=True)],
        "more": [I("basket", at="wall"), I("sack", at="wall"), I("crate", on="roof", stacked=True)],
    },
    "ARMORY": {
        # a clay shaft furnace and skin bellows, the way iron was worked south of the Sahara
        "SUBSAHARAN": [I("furnace", at="shade", name="furnace", need=True),
                       I("bellows", near="furnace", need=True, to=(0.0, 0.6)), *SMITHY,
                       I("rack", 2, at="wall", need=True), I("shields", at="wall", need=True),
                       I("logs", at="edge", length=1.8, n=4), I("crate", 2, at="wall", stacked=True), I("barrel", at="wall")],
        # an adobe hearth with its chimney, round shields of the Sahel
        "SAHEL": [I("forge", at="wall", name="forge", need=True), I("anvil", near="forge", name="anvil", need=True),
                  I("trough", near="anvil", need=True, w=0.55),
                  I("bellows", near="forge", need=True, to=(0.0, 0.5)),
                  I("rack", 2, at="wall", need=True), I("shields", at="wall", need=True, a=0.34, c=0.34),
                  I("crate", 2, at="wall", stacked=True), I("barrel", 2, at="wall"), I("logs", at="edge", length=1.8, n=3)],
        "more": [I("barrel", at="wall"), I("crate", at="wall"), I("crate", on="roof"), I("barrel", on="roof")],
    },
    "DEPOT": {
        "SUBSAHARAN": [I("frame", at="shade", name="engine", need=True, w=3.0, d=1.6, h=2.2),
                       I("wheel", 2, near="engine", need=True), I("logs", 2, at="edge", need=True, length=2.4, n=5),
                       I("crate", 2, at="wall", stacked=True), I("barrel", 2, at="wall"), I("stones", at="yard", n=4)],
        "SAHEL": [I("frame", at="shade", name="engine", need=True, w=3.0, d=1.6, h=2.2),
                  I("wheel", 2, near="engine", need=True), I("logs", 2, at="edge", need=True, length=2.4, n=5),
                  I("crate", 2, at="wall", stacked=True), I("barrel", 2, at="wall"), I("stones", at="yard", n=4)],
        "more": [I("wheel", at="wall"), I("crate", at="wall"), I("rack", at="wall"), I("crate", on="roof", stacked=True)],
    },
    "QUARRY": {
        "SUBSAHARAN": [I("crane", name="crane", need=True, h=4.2), I("stones", 3, near="crane", need=True, n=6),
                       I("crate", 3, at="shade", need=True, stacked=True), I("barrel", 3, at="shade", need=True),
                       I("barrow", near="crane"), I("ore", 2, at="yard"), I("sack", 2, at="shade"),
                       I("logs", at="edge", length=1.6, n=3)],
        "SAHEL": [I("crane", name="crane", need=True, h=4.2), I("stones", 3, near="crane", need=True, n=6),
                  I("crate", 3, at="shade", need=True, stacked=True), I("barrel", 3, at="shade", need=True),
                  I("barrow", near="crane"), I("ore", 2, at="yard"), I("sack", 2, at="shade"),
                  I("logs", at="edge", length=1.6, n=3)],
        "more": [I("stones", at="yard", n=6), I("ore", at="yard"), I("barrel", at="wall"), I("sack", on="roof"), I("crate", on="roof")],
    },
    "CUSTOMS": {
        "SUBSAHARAN": [I("weigh", at="shade", name="scale", need=True), I("crate", 3, near="scale", need=True, stacked=True),
                       I("sack", 3, near="scale"), I("barrel", 2, at="wall"), I("rack", at="wall", w=1.4)],
        "SAHEL": [I("weigh", at="shade", name="scale", need=True), I("crate", 3, near="scale", need=True, stacked=True),
                  I("sack", 3, near="scale"), I("barrel", 2, at="wall"), I("logs", at="edge", length=1.8, n=3)],
        "more": [I("basket", at="wall"), I("barrel", at="wall"), I("sack", on="roof"), I("crate", on="roof", stacked=True),
                 I("barrel", on="roof"), I("basket", on="roof")],
    },
    "DOCK": {
        "SUBSAHARAN": [I("boat", on="deck", need=True), I("fish_rack", 2, on="deck", need=True),
                       I("crate", 2, on="deck", stacked=True), I("barrel", 2, on="deck"), I("logs", on="deck", length=2.0, n=3)],
        "SAHEL": [I("crane", on="deck", need=True, h=4.2), I("boat", on="deck", need=True), I("fish_rack", on="deck"),
                  I("crate", 2, on="deck", stacked=True), I("barrel", 2, on="deck"), I("sack", 2, on="deck")],
        "more": [I("basket", on="deck"), I("barrel", on="deck"), I("crate", on="roof")],
    },
    "PALACE": {
        "SUBSAHARAN": [I("fire", name="court", need=True), I("rack", 2, at="wall", need=True), I("drum", 2, near="court", need=True),
                       I("shields", at="wall"), I("hide_rack", at="wall"), I("pot", 3, at="wall"), I("basket", 3, at="wall")],
        "SAHEL": [I("well", name="court", need=True), I("rack", 2, at="wall", need=True), I("shields", at="wall", a=0.34, c=0.34),
                  I("crate", 3, at="wall", stacked=True), I("barrel", 3, at="wall"), I("sack", 3, at="wall"), I("pot", 2, at="wall")],
        "more": [I("basket", at="wall"), I("barrel", at="wall"), I("sack", at="wall"), I("crate", on="roof")],
    },
    "PLOT": {"SUBSAHARAN": [], "SAHEL": [], "more": []},
}


def items(p):
    """(the items of this building in order of priority, the ones to repeat)."""
    if p.building_type == "PALACE" and p.architecture == "SAHEL":
        return [], []                                     # all of it is built in: nothing stands round it
    prog = PROGRAM[p.building_type]
    return prog[p.architecture], prog["more"]
