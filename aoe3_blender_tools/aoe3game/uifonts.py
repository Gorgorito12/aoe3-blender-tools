# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's interface fonts: `FONTS\\fonts3.xml` (UTF-16) names each font a layout uses, as
`textfont` + ` ` + `textfontsize` ("StatText 12"), and gives its typeface, its `AscentHeight`,
its weight and its outline or shadow, with overrides by screen width (`ResolutionOverride
ResX="1280"`). The typefaces are TrueType files of `FONTS\\Fonts.bar` or system fonts (Arial).

Measured on a Wars of Liberty copy: 131 fonts, 5 typefaces; overrides at ResX 640, 800, 1024,
1280 and 1600.
- `AscentHeight` is the text's whole cell (ascent + descent) in screen pixels, as Windows sizes a
  font (measured: "Tactics" in StatAreaText 12 at 1920 x 1080 has 11-pixel capitals and is 53
  pixels wide, as Formal436 BT bold with an 18-pixel cell).
- Which values apply at a width: this reader takes the base values as the 1024 x 768 layout's own
  and an override from its ResX upward (StatAreaText 12's 18 at 1920 fits that capture; other
  widths are **to verify**).
- A layout may name a font that is not there (`StatText 10`, `IngameDialogs 12`): measured on the
  same capture, the game then draws it as `Arial nobold nodrop 12` whatever the size asked
  (regular Arial, a 14-pixel cell: 9-pixel capitals, "Train Points: 30" 87 pixels wide, "LOS: 16"
  as tall); whether it takes that entry or a default of the same values is **to verify**.
  `lookup` returns None for it; `FALLBACK` names that entry.
- `faces` counts the typefaces fonts3.xml names; `retarget` points every entry of some typefaces at
  others (an extended copy of a font under its own family name, tools/game_fonts.py) changing only
  those `TypeFace` values: the encoding, its byte order mark and the line ends stay byte for byte.
Standard library only.
"""
import re
import struct
import xml.etree.ElementTree as ET

FALLBACK = "arial nobold nodrop 12"   # what a missing font is drawn as (measured on one capture)
BASE_WIDTH = 1024      # the layouts' own width: the base values apply there (to verify)
PARAMS = ("TypeFace", "AscentHeight", "Antialiased", "Bold", "Italic", "BackgroundOutline",
          "BackgroundShadow", "BackgroundOffset", "BackgroundAlpha", "SpacingAdjustment")


def _value(v):
    low = v.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v) if re.fullmatch(r"-?\d+", v.strip()) else float(v)
    except ValueError:
        return v


def _params(el):
    out = {}
    for p in el:
        if p.tag.lower() == "param":
            for k, v in p.attrib.items():
                out[k] = _value(v)
    return out


def parse(data):
    """{lower-case font name: {"name", "params": {...}, "overrides": {resx: {...}}}} of
    fonts3.xml's bytes."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig", "replace")
    text = re.sub(r"^<\?xml[^>]*\?>", "", text.lstrip())
    root = ET.fromstring(text)
    out = {}
    for f in root.iter():
        if f.tag.lower() != "font" or not f.get("Name"):
            continue
        overrides = {}
        for o in f:
            if o.tag.lower() == "resolutionoverride":
                try:
                    overrides[int(o.get("ResX"))] = _params(o)
                except (TypeError, ValueError):
                    continue
        out[f.get("Name").lower()] = {"name": f.get("Name"), "params": _params(f), "overrides": overrides}
    return out


def _typefaces(doc):
    """Every element of a parsed fonts3.xml that sets a TypeFace, entries and overrides alike."""
    return [el for el in doc.root.walk() if hasattr(el, "attrs") and el.get("TypeFace") is not None]


def faces(data):
    """{typeface as written: how many entries and overrides name it} of fonts3.xml's bytes."""
    from . import uilayout
    out = {}
    for el in _typefaces(uilayout.parse(data)):
        name = el.get("TypeFace")
        out[name] = out.get(name, 0) + 1
    return out


def retarget(data, mapping):
    """(new bytes, values changed): every TypeFace naming a key of `mapping` (compared without
    case, as Windows does) set to its value; nothing else in the file changes. Run again, it
    changes nothing more; with the mapping turned round it gives the original back."""
    from . import uilayout
    doc = uilayout.parse(data)
    lower = {k.strip().lower(): v for k, v in mapping.items()}
    count = 0
    for el in _typefaces(doc):
        value = el.get("TypeFace")
        new = lower.get(value.strip().lower())
        if new is not None and new != value:
            uilayout.set_attr(el, "TypeFace", new)
            count += 1
    return (doc.data() if count else bytes(data)), count


def lookup(fonts, font, size, width=1024):
    """The parameters of a layout's font at a screen width, or None when fonts3.xml has no
    entry of that name and size."""
    entry = fonts.get(f"{font} {size}".lower()) if font else None
    if entry is None:
        return None
    params = dict(entry["params"])
    chosen = None                         # the base values are the 1024 x 768 layout's own
    for resx in sorted(set(entry["overrides"]) | {BASE_WIDTH}):
        if resx <= width:
            chosen = resx
    if chosen is None:                    # narrower than every entry: the smallest
        chosen = min(set(entry["overrides"]) | {BASE_WIDTH})
    if chosen != BASE_WIDTH and chosen in entry["overrides"]:
        params.update(entry["overrides"][chosen])
    params["Name"] = entry["name"]
    params["ResX"] = chosen
    return params


def ttf_names(data):
    """{"family", "full", "subfamily"} of a TrueType file's name table (Windows Unicode names
    first, then Macintosh Roman)."""
    try:
        num = struct.unpack_from(">H", data, 4)[0]
        tables = {}
        for i in range(num):
            tag, _sum, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            tables[tag] = (off, length)
        off, _length = tables[b"name"]
        _fmt, count, string_off = struct.unpack_from(">HHH", data, off)
    except (struct.error, KeyError):
        return {}
    found = {}
    for i in range(count):
        plat, enc, lang, nid, length, soff = struct.unpack_from(">HHHHHH", data, off + 6 + 12 * i)
        if nid not in (1, 2, 4):
            continue
        raw = data[off + string_off + soff: off + string_off + soff + length]
        if plat == 3:
            text = raw.decode("utf-16-be", "replace")
            rank = 0 if lang == 0x409 else 1
        elif plat == 1 and enc == 0:
            text = raw.decode("mac_roman", "replace")
            rank = 2
        else:
            continue
        key = {1: "family", 2: "subfamily", 4: "full"}[nid]
        if key not in found or rank < found[key][0]:
            found[key] = (rank, text)
    return {k: v for k, (_r, v) in found.items()}
