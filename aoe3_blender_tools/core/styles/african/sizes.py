# SPDX-License-Identifier: GPL-3.0-or-later
"""The size of each African building: the obstruction radius (game units) of the building its
style guide names as the reference, measured in the target mod's proto on 2026-11-03, and the stock
unit whose proto entry a test deployment copies so it behaves like that reference."""

UNITS_PER_METER = 0.615157485

# type -> (obstruction radius, proto template, what the guide compares it to)
REFERENCE = {
    "HOUSE": (2.0, "House", "a house"),
    "TOWN_CENTER": (4.5, "TownCenter", "a town center"),
    "MARKET": (5.0, "Market", "other cultures' markets"),
    "DOCK": (4.0, "Dock", "other cultures' docks"),
    "WAR_CAMP": (4.0, "WarHut", "a native war hut (no attack)"),
    "DEPOT": (4.0, "ArtilleryDepot", "a siege workshop"),
    "STOCKADE": (4.0, "ypVillage", "a village"),
    "ARMORY": (4.0, "Arsenal", "a European or Latin arsenal"),
    "GRANARY": (3.0, "House", "an estate / hunting lodge"),
    "PLOT": (3.0, "Farm", "the crop fields"),
    "QUARRY": (4.0, "House", "the current quarry"),
    "CUSTOMS": (4.0, "ypConsulate", "the Asian consulate"),
    "PALACE": (6.0, "FortFrontier", "a European or Latin fort"),
}
TYPES = tuple(REFERENCE)
# medium-detail triangles per obstruction class: the median of the target mod's own building models
# (not the stock ones it reuses, which are about 2.5 times lighter), measured 2026-11-03; each
# preset stays within TOLERANCE of its class's figure
TRIS_TARGET = {"4x4": 618, "6x6": 624, "8x8": 1639, "9x9": 3627, "10x10": 1880, "12x12": 4174}
TOLERANCE = 0.15
# a plot is nothing but its crop: it may go up to the 90th percentile of its class
TOP = {"PLOT": 1024}
# the Sahel palace keeps the level of the real forts it stands for (1,458 to 1,719), not of its class:
# its windows are painted and its detail is in the texture (the owner's choice)
EXACT = {("PALACE", "SAHEL"): (1600, 1450, 1720)}
# the model is a little larger than its obstruction, as the stock ones are (measured per class:
# obstruction / half side 0.72 for 2 units, 0.82 for 3, 0.9 for 4 and more)
RATIO = {2.0: 0.72, 3.0: 0.82}


# The game's models are about this much larger than a person's measures: a building of 8 x 8 units
# stands 6 to 11 units high with doors to match (measured on the stock and the mod's models), against
# 3 of a plan drawn at human size. Layouts are drawn at human size and all of it is scaled up.
SCALE = 1.7
RUBBLES = {("PALACE", "SAHEL"): "BuildingRubble6x6"}   # as the stock fort of its size, not its class's 4x4
OBSTRUCTIONS = {("PALACE", "SAHEL"): (6.5, 6.0)}   # leaves out of it what the stock fort leaves out of its own
SCALES = {("PALACE", "SAHEL"): 1.95}   # it stood at the lowest height of its class (median 11.1 units)
TALL = 1.3               # walls and roofs a little taller still, as tall as the real ones
GROUND = 0.26            # the terrace every building stands on, in layout metres


def obstruction(building_type, architecture=None):
    """(radius x, radius z) in game units: the square of its reference, or its own."""
    r = radius(building_type)
    return OBSTRUCTIONS.get((building_type, architecture), (r, r))


def scale(building_type, architecture=None):
    """How much larger than the plan a building is built."""
    return SCALES.get((building_type, architecture), SCALE)


def court_half(building_type):
    """Half the side of the plan a layout is drawn on, walls on the obstruction's square."""
    return REFERENCE[building_type][0] / UNITS_PER_METER / SCALE


def side_m(building_type):
    """The side of the plan (metres) a building of this type is laid out on."""
    r = REFERENCE[building_type][0]
    return 2 * r / UNITS_PER_METER / RATIO.get(r, 0.9)


def radius(building_type):
    return REFERENCE[building_type][0]


def template(building_type):
    return REFERENCE[building_type][1]


def tris_target(building_type, architecture=None):
    """(target, lowest, highest) medium-detail triangles for this type."""
    if (building_type, architecture) in EXACT:
        return EXACT[(building_type, architecture)]
    r = REFERENCE[building_type][0]
    t = TRIS_TARGET[f"{2 * r:g}x{2 * r:g}"]
    return t, round(t * (1 - TOLERANCE)), TOP.get(building_type, round(t * (1 + TOLERANCE)))
