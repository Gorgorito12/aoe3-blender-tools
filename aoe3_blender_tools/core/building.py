# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric low-poly buildings, as pure data.

`build(params)` returns a `Model`: faces (corner points, UVs, smooth flag), attach points, the atlas
and the facade layout the painter needs. The geometry of each style is in `core/styles/` and is
made of the pieces in `core/kit.py`; this module holds the parameters, the presets and the
dispatch. Nothing here imports Blender, so the geometry can be tested on its own.

Conventions: metres, Z up, the front (portico) faces -Y, origin at the centre of the footprint
(steps included) on the ground.
"""
from dataclasses import dataclass, field, replace

# Re-exported: other modules and the tests use these names from here.
from .kit import Face, Model, _area2, newell, wall_triangles  # noqa: F401
from .styles import STYLES
from .styles.neoclassical import CORNICE_H, FRIEZE_H, STOREY_H  # noqa: F401


# Every colour any style paints with; a style uses the keys it needs. Older objects whose colours
# lack a key get it from here (clamp_params).
DEFAULT_COLORS = {
    "wall": (232, 225, 204), "trim": (243, 240, 231), "roof": (70, 78, 90),
    "glass": (52, 66, 82), "door": (64, 50, 40), "brick": (150, 64, 48),
    "lead": (96, 106, 114), "stone": (206, 202, 192), "plinth": (192, 188, 177),
    "plaster": (236, 230, 214), "tile": (172, 84, 52), "timber": (104, 70, 44), "iron": (44, 42, 40),
    "mud": (132, 96, 66), "thatch": (150, 126, 84), "adobe": (192, 156, 110), "cloth": (176, 62, 44),
}
COLOR_KEYS = tuple(DEFAULT_COLORS)


@dataclass
class BuildingParams:
    name: str = "Building"
    style: str = "NEOCLASSICAL"     # a key of core.styles.STYLES
    width: float = 14.0             # main block, X
    depth: float = 9.0              # main block, Y
    storeys: int = 2
    plinth: float = 0.8             # ground floor level
    roof_pitch: float = 0.54        # rise / run, same on all four sides (hipped roof)
    bay_spacing: float = 1.8        # target distance between window bays
    side_bays: int = 0              # windows per row on the sides; 0 = from bay_spacing
    portico: bool = True
    columns: int = 4                # even, 2..8
    column_spacing: float = 1.8
    portico_depth: float = 3.3
    cupola: bool = True
    flagpole: bool = False          # a mast on the roof (the flag's attach point goes on top)
    chimneys: int = 1               # 0..8 (1 or 2: near the side ends; more: in pairs on the roof)
    back_portico: str = "NONE"      # NONE or BOW: a semicircular colonnade around a bowed bay
    bow_radius: float = 3.2         # radius of the bowed wall
    bow_columns: int = 6
    wings: bool = False             # one-storey pavilions joined to the block by colonnades
    wing_gap: float = 5.0           # colonnade length
    wing_width: float = 6.5
    wing_depth: float = 5.5
    shutters: bool = False          # painted shutters on the back and bow windows
    window_caps: str = "PEDIMENT"   # ground floor window caps: PEDIMENT, or ALTERNATE (with arches)
    detail: str = "LOW"             # LOW (flat walls, ~350 tris) or MEDIUM (~1,200 tris: recessed
                                    # windows, balustrade, profiled cornice, finer columns)
    texture_size: int = 1024        # final size; painted at twice that and filtered down
    seed: int = 1870
    player_colour: bool = False     # string courses and shutters show the owner's colour in game
    materials: bool = False         # photo swatches under the painting (core/materials.py)
    # colonial style
    roof_type: str = "GABLE"        # GABLE or HIPPED
    ridge: str = "ALONG"            # the gable's ridge along the width (ALONG) or the depth (ACROSS)
    arcade: str = "NONE"            # NONE or FRONT: a portal along the front under a lean-to roof
    arcade_posts: str = "WOOD"      # WOOD (posts and a beam) or MASONRY (piers and round arches)
    arcade_depth: float = 2.4
    balcony: bool = False           # a wooden balcony on the front's upper floor
    bell_gable: bool = False        # a bell gable (espadana) over the front; the flag goes on top
    plan: str = "BLOCK"             # BLOCK, or L: a one-storey wing at the back (wing_width, wing_depth)
    rejas: bool = True              # iron grilles on the ground floor windows
    # timber-framed style
    jetty: bool = True              # the upper floors jut out over the front and back
    jetty_depth: float = 0.4
    dormers: int = 1                # on the front slope, 0..4
    ground_floor: str = "STONE"     # STONE, BRICK or TIMBER
    infill: str = "PLASTER"         # PLASTER or BRICK between the timbers
    bracing: str = "CROSS"          # CROSS, CURVED or PLAIN braces (painted)
    signboard: bool = False         # a sign hanging from the front wall (player colour)
    # African style (the shared African buildings' style guide)
    building_type: str = "HOUSE"    # HOUSE, TOWN_CENTER, MARKET, DOCK, WAR_CAMP, DEPOT, STOCKADE, ARMORY,
                                    # GRANARY, PLOT, QUARRY, CUSTOMS, PALACE
    architecture: str = "SUBSAHARAN"  # SUBSAHARAN (round, thatched) or SAHEL (adobe, flat roofs)
    wall_upgrade: str = "WOOD"      # the stockade's fence: WOOD, or STONE once upgraded
    colors: dict = field(default_factory=lambda: dict(DEFAULT_COLORS))


PRESETS = {
    "WHITE_HOUSE": BuildingParams(name="WhiteHouse", side_bays=3),
    "COURTHOUSE": BuildingParams(name="Courthouse", width=11.0, depth=9.0, storeys=1, columns=4,
                                 column_spacing=1.6, portico_depth=2.8, cupola=True, chimneys=2),
    "CAPITOL": BuildingParams(name="Capitol", width=20.0, depth=12.0, storeys=2, columns=6,
                              column_spacing=1.9, portico_depth=3.6, cupola=True, chimneys=0),
    "MANSION": BuildingParams(name="Mansion", width=12.0, depth=8.0, storeys=2, portico=False,
                              cupola=False, chimneys=2),
    "WHITE_HOUSE_1914": BuildingParams(
        name="WhiteHouse1914", width=21.0, depth=10.5, storeys=2, plinth=0.9, roof_pitch=0.32,
        bay_spacing=1.8, side_bays=3, portico=True, columns=4, column_spacing=2.0, portico_depth=3.6,
        cupola=False, flagpole=True, chimneys=8, back_portico="BOW", bow_radius=3.2, bow_columns=6,
        wings=True, wing_gap=5.0, wing_width=6.5, wing_depth=5.5, shutters=True, window_caps="ALTERNATE",
        detail="MEDIUM",
        texture_size=2048),
}

COLONIAL_COLORS = {**DEFAULT_COLORS, "plaster": (238, 231, 214), "plinth": (176, 112, 70),
                   "tile": (170, 84, 52), "timber": (98, 66, 42), "door": (84, 58, 38),
                   "iron": (40, 38, 36), "glass": (46, 54, 60)}
TIMBER_COLORS = {**DEFAULT_COLORS, "timber": (62, 44, 32), "plaster": (230, 220, 194),
                 "stone": (172, 164, 150), "brick": (146, 66, 48), "tile": (154, 72, 50),
                 "door": (92, 60, 38), "glass": (52, 62, 66), "lead": (70, 72, 74)}
AFRICAN_COLORS = {**DEFAULT_COLORS, "timber": (92, 64, 40), "stone": (168, 156, 136), "tile": (160, 84, 52)}


def african(building_type, architecture, **kw):
    words = "".join(w.title() for w in building_type.split("_"))
    arch = "Sahel" if architecture == "SAHEL" else "SubSaharan"
    return BuildingParams(name=f"African{words}{arch}", style="AFRICAN", building_type=building_type,
                          architecture=architecture, portico=False, cupola=False, detail="MEDIUM",
                          colors=dict(AFRICAN_COLORS), **kw)


PRESETS.update({
    "AFRICAN_HOUSE_SUBSAHARAN": african("HOUSE", "SUBSAHARAN"),
    "AFRICAN_HOUSE_SAHEL": african("HOUSE", "SAHEL"),
})
PRESETS.update({
    "TIMBER_HOUSE": BuildingParams(
        name="TimberHouse", style="TIMBER", width=9.0, depth=7.0, storeys=2, plinth=0.3, roof_pitch=1.1,
        bay_spacing=2.0, jetty=True, jetty_depth=0.4, dormers=1, ground_floor="STONE", infill="PLASTER",
        bracing="CROSS", chimneys=1, portico=False, cupola=False, detail="MEDIUM", colors=dict(TIMBER_COLORS)),
    "TIMBER_INN": BuildingParams(
        name="TimberInn", style="TIMBER", width=12.0, depth=8.5, storeys=3, plinth=0.3, roof_pitch=1.0,
        bay_spacing=2.1, jetty=True, jetty_depth=0.45, dormers=2, ground_floor="BRICK", infill="PLASTER",
        bracing="CURVED", signboard=True, chimneys=2, portico=False, cupola=False, detail="MEDIUM",
        colors=dict(TIMBER_COLORS)),
    "COLONIAL_HOUSE": BuildingParams(
        name="ColonialHouse", style="COLONIAL", width=9.0, depth=7.5, storeys=2, plinth=0.3,
        roof_pitch=0.45, bay_spacing=2.4, roof_type="GABLE", ridge="ALONG", balcony=True, rejas=True,
        chimneys=1, portico=False, cupola=False, detail="MEDIUM", colors=dict(COLONIAL_COLORS)),
    "COLONIAL_TRADING_HOUSE": BuildingParams(
        name="ColonialTradingHouse", style="COLONIAL", width=11.0, depth=6.5, storeys=2, plinth=0.3,
        roof_pitch=0.42, bay_spacing=2.4, roof_type="GABLE", ridge="ALONG", arcade="FRONT",
        arcade_posts="MASONRY", arcade_depth=2.0, balcony=True, bell_gable=True, plan="L",
        wing_width=4.5, wing_depth=3.5, rejas=True, chimneys=2, portico=False, cupola=False,
        detail="MEDIUM", colors=dict(COLONIAL_COLORS)),
})


def clamp_params(p):
    """Returns a copy with values the style's geometry can build (an unknown style: neoclassical)."""
    style = STYLES.get(str(p.style).upper(), STYLES["NEOCLASSICAL"])
    p = style.clamp(replace(p, colors={**DEFAULT_COLORS, **p.colors}))
    p.style = style.NAME
    return p


def reference(params):
    """(obstruction radius in game units, proto template) of the building a style guide gives as
    this one's size, or None (the size then comes from the footprint)."""
    p = clamp_params(params)
    fn = getattr(STYLES[p.style], "reference", None)
    return fn(p) if fn else None


def build(params):
    p = clamp_params(params)
    return STYLES[p.style].build(p, params)
