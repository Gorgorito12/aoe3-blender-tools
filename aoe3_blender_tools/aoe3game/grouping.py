# SPDX-License-Identifier: GPL-3.0-or-later
"""A grouping: the XML a map script or the scenario editor places as one - a native settlement,
a camp, a ruin - by placing proto units at offsets from a centre. Pure Python, standard library.

Measured on 2026-11-10 over 1,483 grouping files of the original game and of a mod's copy
(`RM*/groupings/*.xml`); every one is well-formed XML:

    <grouping>
        <width>19</width><height>12</height>
        <ignoreplacementrules>1</ignoreplacementrules>
        <selectassingleunit>0</selectassingleunit>
        <units>
            <unit variation ="109" posx ="7.7374" posz ="-7.9860" orientx ="0.7071" orienty ="0.0000"
                  orientz ="-0.7071">ProtoName</unit>
        </units>
        <tiles><tileGroup type="NonPassableLand" subtype="..."><block startX=".." .../></tileGroup>
               <heights>...</heights></tiles>
    </grouping>

- The tags come in two spellings: lower case (`posx`, `ignoreplacementrules`: 68,571 units and
  1,339 files) and camel case (`posX`, `Variation`, `ignorePlacementRules`: 4,228 units, 140
  files). Both are read; lower case is written.
- `variation` (0 to 255) picks a model of a unit whose anim file has a Variation logic
  (animxml.prop_set); `orient` is a direction on the ground (orienty is 0 in 99.9 %).
- `tiles` (terrain and passability under it) and its `heights` are read and written back as
  they were: this module never generates them.
- A file holds 24 / 43 / 63 units (quartiles), is 15 x 15 at the median, and a settlement comes
  in 3 or 5 numbered variants of one name.

**To verify in game**: how Blender's axes map to posx / posz and which way the orientation turns
(axes_grouping makes an asymmetric one that settles both), and how a variation above a
set's model count is resolved.
"""
import math
import xml.etree.ElementTree as ET

FLAGS = ("ignoreplacementrules", "selectassingleunit")


def _lower(e):
    return {k.lower(): v for k, v in e.attrib.items()}


def read(text):
    """{"width", "height", "flags": {name: int}, "units": [{"proto", "variation", "x", "z",
    "orient": (x, y, z)}], "tiles": the tiles element as XML text or None}."""
    root = ET.fromstring(text)
    if root.tag.lower() != "grouping":
        raise ValueError(f"not a grouping: <{root.tag}>")
    out = {"width": 0.0, "height": 0.0, "flags": {}, "units": [], "tiles": None}
    for child in root:
        tag = child.tag.lower()
        if tag in ("width", "height"):
            out[tag] = float(child.text or 0)
        elif tag in FLAGS:
            out["flags"][tag] = int(float(child.text or 0))
        elif tag == "units":
            for u in child:
                if u.tag.lower() != "unit":
                    continue
                a = _lower(u)
                out["units"].append({
                    "proto": (u.text or "").strip(), "variation": int(float(a.get("variation", 0))),
                    "x": float(a.get("posx", 0)), "z": float(a.get("posz", 0)),
                    "orient": (float(a.get("orientx", 0)), float(a.get("orienty", 0)), float(a.get("orientz", 1)))})
        elif tag == "tiles":
            out["tiles"] = ET.tostring(child, encoding="unicode")
    return out


def _num(v, digits=4):
    return f"{v:.{digits}f}"


def write(g):
    """The text of a grouping from what read() returns (the units' order kept), so a file read
    and written again holds the same units, flags and tiles. For a new grouping: a width or a
    height of 0 is taken from the units' spread, flags None are the usual ones (placement rules
    ignored, units selected one by one), and tiles "" is the usual empty block."""
    units = g.get("units", [])
    w, h = g.get("width") or 0, g.get("height") or 0
    if units and not w:
        w = math.ceil(2 * max(abs(u["x"]) for u in units)) + 2
    if units and not h:
        h = math.ceil(2 * max(abs(u["z"]) for u in units)) + 2
    lines = ['<?xml version="1.0"?>', "", "<grouping>",
             f"\t<width>{w:g}</width>", f"\t<height>{h:g}</height>"]
    flags = g.get("flags")
    if flags is None:
        flags = {"ignoreplacementrules": 1, "selectassingleunit": 0}
    for name in FLAGS:
        if name in flags:
            lines.append(f"\t<{name}>{int(flags[name])}</{name}>")
    lines.append("\t<units>")
    for u in units:
        ox, oy, oz = u.get("orient", (0.0, 0.0, 1.0))
        proto = u["proto"].replace("&", "&amp;").replace("<", "&lt;")
        lines.append(f'\t\t<unit variation ="{int(u.get("variation", 0))}" posx ="{_num(u["x"])}" '
                     f'posz ="{_num(u["z"])}" orientx ="{_num(ox)}" orienty ="{_num(oy)}" '
                     f'orientz ="{_num(oz)}">{proto}</unit>')
    lines.append("\t</units>")
    if g.get("tiles"):
        lines.append("\t" + g["tiles"].strip())
    elif g.get("tiles") == "":
        lines.append("\t<tiles>\n\t</tiles>")
    lines.append("</grouping>")
    return "\n".join(lines) + "\n"


def orient(angle):
    """The orientation vector of a unit turned `angle` radians (0: facing +z). To verify in game."""
    return (round(math.sin(angle), 4), 0.0, round(math.cos(angle), 4))


def angle(o):
    """The angle orient() was given, from an orientation vector."""
    return math.atan2(o[0], o[2])


def from_blender(x, y, turn):
    """(posx, posz, orient) of a point of Blender's ground (metres, front toward -Y) and its turn
    about Z: the game's x is Blender's x, its z is Blender's y, in game units. To verify in game."""
    from .gr2_write import STOCK_BASIS
    k = STOCK_BASIS["units_per_meter"]
    return x * k, y * k, orient(turn)


def to_blender(posx, posz, o):
    """The inverse of from_blender: (x, y, turn) in Blender's metres."""
    from .gr2_write import STOCK_BASIS
    k = STOCK_BASIS["units_per_meter"]
    return posx / k, posz / k, angle(o)


def axes_grouping(proto, count=4):
    """An asymmetric grouping to settle the axes in game: `count` units on a line toward +x, each
    turned a quarter more than the last, and one alone at +z. What the editor shows tells which
    way posx and posz run and which way an orientation turns."""
    units = [{"proto": proto, "variation": i, "x": 2.0 * (i + 1), "z": 0.0, "orient": orient(i * math.pi / 2)}
             for i in range(count)]
    units.append({"proto": proto, "variation": 0, "x": 0.0, "z": 4.0, "orient": orient(0.0)})
    return {"width": 0, "height": 0, "flags": None, "units": units, "tiles": ""}
