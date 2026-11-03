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
# the model is a little larger than its obstruction, as the stock ones are (measured per class:
# obstruction / half side 0.72 for 2 units, 0.82 for 3, 0.9 for 4 and more)
RATIO = {2.0: 0.72, 3.0: 0.82}


def side_m(building_type):
    """The side of the plan (metres) a building of this type is laid out on."""
    r = REFERENCE[building_type][0]
    return 2 * r / UNITS_PER_METER / RATIO.get(r, 0.9)


def radius(building_type):
    return REFERENCE[building_type][0]


def template(building_type):
    return REFERENCE[building_type][1]
