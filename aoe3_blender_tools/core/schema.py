# SPDX-License-Identifier: GPL-3.0-or-later
"""What each BuildingParams field is, for a user interface that draws itself: its kind, range,
choices, English label and help, the group it sits in and when it shows.

The Blender panel keeps its own properties; `tests/run_tests.py` holds the two together (every
field described, the same ranges and choices). The studio (`studio/`) draws its forms from here.

A field shows when one of its `show` rules matches: a rule is (styles, conditions), where styles
is a tuple of style names (None: any) and conditions maps another field to the values it must
have. No rule at all: always shown.
"""
from dataclasses import asdict, dataclass, fields

from . import building

N, C, T, A, P = "NEOCLASSICAL", "COLONIAL", "TIMBER", "AFRICAN", "PROP"
HOUSES = (N, C, T)                # the styles drawn from width, depth and storeys


@dataclass(frozen=True)
class Field:
    name: str
    kind: str                     # float, int, bool, choice, text
    label: str
    group: str                    # general, size, style, texture
    help: str = ""
    min: float = None
    max: float = None
    step: float = None
    unit: str = ""                # m: a length in metres
    choices: tuple = ()           # (value, label, help)
    show: tuple = ()              # ((styles or None, {field: (values, ...)}), ...)


def _c(*items):
    """Choices from (value, label[, help]) tuples."""
    return tuple((v[0], v[1], v[2] if len(v) > 2 else "") for v in items)


def _titled(values, helps=None):
    return tuple((v, v.replace("_", " ").title(), (helps or {}).get(v, "")) for v in values)


_AFRICAN = building.STYLES[A]
_PROP = building.STYLES[P]

FIELDS = (
    # general
    Field("name", "text", "Name", "general", "The object's name, and the unit's name in the game"),
    Field("style", "choice", "Style", "general", "The architecture the building is drawn in",
          choices=_titled(building.STYLES)),
    Field("detail", "choice", "Detail", "general", choices=_c(
        ("LOW", "Low", "Flat walls with painted windows (about 350 triangles)"),
        ("MEDIUM", "Medium", "Recessed windows and doors, balustrade, profiled cornice, finer columns "
                             "(about 1,200 triangles)"))),
    Field("poly", "float", "Segments", "general",
          "How many segments every body that is not a box gets (round walls, cones, domes, arches), as a "
          "multiplier of what the style asks for: 1.0 is the style's own numbers, 0.6 a cheaper building, "
          "1.5 a finer one", min=0.3, max=2.0, step=0.05),
    # props and African buildings: what they are
    Field("prop_type", "choice", "Prop", "style", "A map object (one thing) or a treasure (an accident and "
          "its spilled cargo)", choices=_titled(_PROP.recipes.TYPES, {
              t: "A treasure: an accident and its spilled cargo" if t in _PROP.recipes.TREASURES
              else "A map object: one thing" for t in _PROP.recipes.TYPES}), show=(((P,), {}),)),
    Field("building_type", "choice", "Building", "style", "What the building is for: it decides its parts "
          "and its size", choices=_titled(_AFRICAN.sizes.TYPES), show=(((A,), {}),)),
    Field("architecture", "choice", "Architecture", "style", choices=_c(
        ("SUBSAHARAN", "Sub-Saharan", "Round mud huts with thatched cones, log fences"),
        ("SAHEL", "Sahel / Horn", "Adobe blocks with flat roofs, parapets and beam ends")), show=(((A,), {}),)),
    Field("wall_upgrade", "choice", "Stockade wall", "style", choices=_c(
        ("WOOD", "Wood", "A palisade"), ("STONE", "Stone", "The upgraded stone wall")),
        show=(((A,), {"building_type": ("STOCKADE",)}),)),
    # size
    Field("width", "float", "Width", "size", "The main block along X", min=4.0, max=60.0, step=0.1, unit="m",
          show=((HOUSES, {}),)),
    Field("depth", "float", "Depth", "size", "The main block along Y", min=4.0, max=60.0, step=0.1, unit="m",
          show=((HOUSES, {}),)),
    Field("storeys", "int", "Storeys", "size", min=1, max=4, step=1,
          show=((HOUSES, {}), ((A,), {"building_type": ("CUSTOMS",)}))),
    Field("plinth", "float", "Plinth", "size", "The ground floor's level above the ground", min=0.2, max=2.0,
          step=0.05, unit="m", show=((HOUSES, {}),)),
    Field("bay_spacing", "float", "Window spacing", "size", "The target distance between window bays",
          min=1.3, max=6.0, step=0.1, unit="m", show=((HOUSES, {}),)),
    # what the three house styles share
    Field("roof_pitch", "float", "Roof pitch", "style", "Rise over run, the same on all sides", min=0.15,
          max=1.5, step=0.01, show=((HOUSES, {}),)),
    Field("chimneys", "int", "Chimneys", "style", min=0, max=8, step=1, show=((HOUSES, {}),)),
    # neoclassical
    Field("side_bays", "int", "Side windows", "style", "Windows per row on each side; 0 = from the window "
          "spacing", min=0, max=15, step=1, show=(((N,), {}),)),
    Field("cupola", "bool", "Cupola", "style", show=(((N,), {}),)),
    Field("flagpole", "bool", "Flagpole", "style", "A mast on the roof (used when there is no cupola)",
          show=(((N,), {}),)),
    Field("shutters", "bool", "Shutters", "style", "Painted shutters on the back and bow windows",
          show=(((N,), {}),)),
    Field("window_caps", "choice", "Window caps", "style", choices=_c(
        ("PEDIMENT", "Pediments", "Triangular pediments over the ground floor windows"),
        ("ALTERNATE", "Alternate", "Triangular and arched caps in turn on the front")), show=(((N,), {}),)),
    Field("portico", "bool", "Portico", "style", "A columned porch on the front", show=(((N,), {}),)),
    Field("columns", "int", "Columns", "style", "Even, 2 to 8", min=2, max=8, step=2,
          show=(((N,), {"portico": (True,)}),)),
    Field("column_spacing", "float", "Column spacing", "style", min=1.2, max=4.0, step=0.05, unit="m",
          show=(((N,), {"portico": (True,)}),)),
    Field("portico_depth", "float", "Portico depth", "style", min=1.5, max=8.0, step=0.1, unit="m",
          show=(((N,), {"portico": (True,)}),)),
    Field("back_portico", "choice", "Back portico", "style", choices=_c(
        ("NONE", "None", "A flat back facade"),
        ("BOW", "Bow", "A semicircular colonnade around a bowed bay, with a balustraded flat roof")),
        show=(((N,), {}),)),
    Field("bow_radius", "float", "Bow radius", "style", min=1.5, max=12.0, step=0.1, unit="m",
          show=(((N,), {"back_portico": ("BOW",)}),)),
    Field("bow_columns", "int", "Bow columns", "style", min=2, max=10, step=1,
          show=(((N,), {"back_portico": ("BOW",)}),)),
    Field("wings", "bool", "Wings", "style", "One-storey pavilions joined by colonnades", show=(((N,), {}),)),
    Field("wing_gap", "float", "Colonnade length", "style", min=2.0, max=30.0, step=0.1, unit="m",
          show=(((N,), {"wings": (True,)}),)),
    Field("wing_width", "float", "Wing width", "style", min=3.0, max=30.0, step=0.1, unit="m",
          show=(((N,), {"wings": (True,)}), ((C,), {"plan": ("L",)}))),
    Field("wing_depth", "float", "Wing depth", "style", min=3.0, max=30.0, step=0.1, unit="m",
          show=(((N,), {"wings": (True,)}), ((C,), {"plan": ("L",)}))),
    # colonial
    Field("roof_type", "choice", "Roof", "style", choices=_c(("GABLE", "Gable", "Two slopes"),
                                                             ("HIPPED", "Hipped", "Four slopes")),
          show=(((C,), {}),)),
    Field("ridge", "choice", "Ridge", "style", choices=_c(
        ("ALONG", "Along", "The ridge along the width (eaves front and back)"),
        ("ACROSS", "Across", "The ridge along the depth (a gable on the front)")),
        show=(((C,), {"roof_type": ("GABLE",)}),)),
    Field("rejas", "bool", "Window grilles", "style", "Iron grilles on the ground floor windows",
          show=(((C,), {}),)),
    Field("balcony", "bool", "Balcony", "style", "A wooden balcony on the upper floor", show=(((C,), {}),)),
    Field("bell_gable", "bool", "Bell gable", "style", "A bell gable over the front", show=(((C,), {}),)),
    Field("arcade", "choice", "Portal", "style", choices=_c(
        ("NONE", "None"), ("FRONT", "Front", "An arcade along the front under a lean-to roof")),
        show=(((C,), {}),)),
    Field("arcade_posts", "choice", "Posts", "style", choices=_c(("WOOD", "Wood", "Posts and a beam"),
                                                                 ("MASONRY", "Masonry", "Piers and arches")),
          show=(((C,), {"arcade": ("FRONT",)}),)),
    Field("arcade_depth", "float", "Portal depth", "style", min=1.6, max=3.5, step=0.1, unit="m",
          show=(((C,), {"arcade": ("FRONT",)}),)),
    Field("plan", "choice", "Plan", "style", choices=_c(("BLOCK", "Block"),
                                                        ("L", "L", "A one-storey wing at the back")),
          show=(((C,), {}),)),
    # timber-framed
    Field("dormers", "int", "Dormers", "style", "On the front slope", min=0, max=4, step=1, show=(((T,), {}),)),
    Field("ground_floor", "choice", "Ground", "style", choices=_c(
        ("STONE", "Stone", "Rubble stone"), ("BRICK", "Brick"), ("TIMBER", "Timber", "Framed like the upper floors")),
        show=(((T,), {}),)),
    Field("infill", "choice", "Infill", "style", choices=_c(("PLASTER", "Plaster"), ("BRICK", "Brick")),
          show=(((T,), {}),)),
    Field("bracing", "choice", "Braces", "style", choices=_c(("CROSS", "Cross"), ("CURVED", "Curved"),
                                                            ("PLAIN", "Plain", "Posts and rails only")),
          show=(((T,), {}),)),
    Field("signboard", "bool", "Sign", "style", "A sign hanging from the front wall", show=(((T,), {}),)),
    Field("jetty", "bool", "Jetty", "style", "The upper floors jut out over the front and back",
          show=(((T,), {}),)),
    Field("jetty_depth", "float", "Jetty depth", "style", min=0.2, max=0.8, step=0.05, unit="m",
          show=(((T,), {"jetty": (True,)}),)),
    # texture
    Field("texture_size", "choice", "Texture", "texture", "The final size; painted at twice that and "
          "filtered down", choices=tuple((s, str(s), "") for s in (256, 512, 1024, 2048))),
    Field("seed", "int", "Seed", "texture", "Another number gives another painting of the same building",
          min=0, max=2 ** 31 - 1, step=1),
    Field("player_colour", "bool", "Player colour", "texture", "Paint the string courses and shutters for "
          "the owner's colour (texture alpha 0 there); the game export then uses the player-colour shader"),
    Field("materials", "bool", "Material swatches", "texture", "Photo swatches (CC0) under the painting give "
          "the walls their grain"),
)
BY_NAME = {f.name: f for f in FIELDS}
NOT_DESCRIBED = ("colors",)        # a dict of colours: drawn as one colour picker per key


def visible(field, params):
    """Whether a field shows for these parameters (a dict or a BuildingParams)."""
    get = params.get if isinstance(params, dict) else (lambda k: getattr(params, k))
    if not field.show:
        return True
    for styles, conditions in field.show:
        if styles is not None and get("style") not in styles:
            continue
        if all(get(k) in values for k, values in conditions.items()):
            return True
    return False


def to_json():
    """The schema as plain data for a web page."""
    defaults = asdict(building.BuildingParams())
    out = []
    for f in FIELDS:
        d = {k: v for k, v in asdict(f).items() if v not in (None, "", ())}
        d["default"] = defaults[f.name]
        if f.choices:
            d["choices"] = [{"value": v, "label": label, "help": h} for v, label, h in f.choices]
        if f.show:
            d["show"] = [{"styles": list(styles) if styles else None,
                          "if": {k: list(vals) for k, vals in cond.items()}} for styles, cond in f.show]
        out.append(d)
    return {"fields": out, "colors": [{"key": k, "default": list(building.DEFAULT_COLORS[k])}
                                       for k in building.COLOR_KEYS]}


def params_to_dict(p):
    """A BuildingParams as JSON-ready data."""
    d = asdict(p)
    d["colors"] = {k: list(v) for k, v in p.colors.items()}
    return d


def params_from_dict(d):
    """A BuildingParams from data such as params_to_dict gives (or a page sends): unknown keys are
    refused, missing ones take their default, numbers are coerced to the field's kind and held to
    its range, a choice must be one of its values."""
    names = {f.name for f in fields(building.BuildingParams)}
    unknown = set(d) - names
    if unknown:
        raise ValueError("unknown parameters: " + ", ".join(sorted(unknown)))
    p = building.BuildingParams()
    for k, v in d.items():
        if k == "colors":
            colors = dict(building.DEFAULT_COLORS)
            if not isinstance(v or {}, dict):
                raise ValueError("colors: a mapping of colour names to three numbers")
            for ck, cv in (v or {}).items():
                if ck not in colors:
                    raise ValueError(f"unknown colour: {ck}")
                rgb = tuple(int(c) for c in cv)
                if len(rgb) != 3 or not all(0 <= c <= 255 for c in rgb):
                    raise ValueError(f"colour {ck} must be three numbers 0 to 255")
                colors[ck] = rgb
            p.colors = colors
            continue
        setattr(p, k, _coerce(BY_NAME.get(k), k, v))
    return p


def _coerce(f, name, v):
    if f is None:
        return v
    if f.kind == "text":
        v = str(v).strip()
        return v or "Building"
    if f.kind == "bool":
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return bool(v)
    if f.kind == "choice":
        values = [c[0] for c in f.choices]
        if isinstance(values[0], int):
            v = int(v)
        if v not in values:
            raise ValueError(f"{name} must be one of {', '.join(str(x) for x in values)}")
        return v
    v = float(v) if f.kind == "float" else int(round(float(v)))
    if f.min is not None:
        v = max(v, type(v)(f.min))
    if f.max is not None:
        v = min(v, type(v)(f.max))
    return v
