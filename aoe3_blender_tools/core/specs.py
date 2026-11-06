# SPDX-License-Identifier: GPL-3.0-or-later
"""The technical sheet of a building: what it measures, what it costs to draw and how the game
treats it, as Markdown. Pure Python: no Blender import.

Every sheet is computed from the model, so it cannot drift from it: `tools/spec_sheets.py` writes
one per preset into docs/specs/, a game export writes one beside its bundle (SPECS.md), and
tests/test_specs.py fails when a preset has none or an old one.

The numbers of a game's own data (hit points, cost) stay out of the shipped sheets: they exist only
when a sheet is made with `--proto`, on the user's machine."""
import re
from dataclasses import replace

from . import building

WALLS = re.compile(r"^(bk|rw|wall|hut|tw|gr)\d*_")
FLAGS_SHOWN = ("CollidesWithProjectiles", "SelectWithObstruction", "ObscuresUnits", "FlattenGround")


def tris_of(model):
    return sum(len(f.pts) - 2 for f in model.faces)


def tris_by_part(model):
    """Triangles per painted part, most first; each wall's own region counts as `walls`."""
    parts = {}
    for f in model.faces:
        name = "walls" if WALLS.match(f.region) else f.region
        parts[name] = parts.get(name, 0) + len(f.pts) - 2
    return sorted(parts.items(), key=lambda kv: (-kv[1], kv[0]))


def extent(model):
    pts = [q for f in model.faces for q in f.pts]
    return [max(q[i] for q in pts) - min(q[i] for q in pts) for i in range(3)]


def texture_mb(main, bump, damaged_own, ground, lowpoly=512):
    """Megabytes of a building's textures: DXT3 with its mips, DXT5 bumps, as a bundle writes them."""
    def colour(side):
        return side * side * 4 / 3

    total = colour(main) + bump * bump + colour(lowpoly) + lowpoly * lowpoly
    if damaged_own:
        total += colour(main) + main * main
    if ground:
        total += colour(512)
    return total / 1048576


def facts(params, size, template, upm, key=None, collision=None, shape=None, band=None, scale=1.0, budget=None):
    """Everything a sheet shows. `size`: bundle.game_size's dict, `upm`: game units per metre,
    `scale`: how much larger than its plan a style builds it (the texture is laid on the plan),
    `budget`: (largest side of the texture, of its bump) the export halves them to,
    `collision`: the name of the collision shape the model's anim file points at, `shape`: the
    numbers of tools/shape_survey.py with `shape_class`, (name, the class's table), `band`: the
    triangle target (target, lowest, highest)."""
    medium = building.build(replace(params, detail="MEDIUM"))
    low = building.build(replace(params, detail="LOW"))
    w, d, h = extent(medium)
    p = medium.params
    at = medium.atlas
    main, bump = budget or (p.texture_size, p.texture_size)
    return {
        "name": p.name, "preset": key, "style": p.style,
        "type": medium.dims.get("type") or getattr(p, "building_type", None),
        "architecture": medium.dims.get("architecture"), "template": template, "upm": upm,
        "size_m": (w, d, h), "storeys": medium.dims.get("storeys"),
        "tris": tris_of(medium), "tris_low": tris_of(low), "faces": len(medium.faces), "band": band,
        "parts": tris_by_part(medium), "texture": main, "painted": p.texture_size, "bump": bump,
        "texture_mb": texture_mb(main, bump, budget is None, bool(medium.boxes)),
        "density": at.density * main / at.size / scale / upm, "materials": bool(getattr(p, "materials", False)),
        "game": dict(size), "collision": collision, "shape": shape, "attach": dict(medium.attach),
        "notes": list(medium.notes), "boxes": list(medium.boxes),
    }


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def _n(v, digits=2):
    return f"{v:,.{digits}f}"


def proto_of(xml, unit, template=None):
    """What the game's proto says of a unit (or of its template, when it has no entry of its own):
    a dict for `render`. `xml`: the text of protoy.xml, read on the user's machine."""
    for name in (unit, template):
        if not name:
            continue
        m = re.search(r"<unit\b[^>]*\bname\s*=\s*['\"]" + re.escape(name) + r"['\"].*?</unit>", xml, re.S | re.I)
        if m:
            b = m.group(0)

            def one(tag):
                found = re.search(rf"<{tag}\b[^>]*>([^<]*)<", b)
                return found.group(1).strip() if found else None

            return {"source": name, "hit points": one("MaxHitpoints"), "line of sight": one("LOS"),
                    "build points": one("BuildPoints"), "build limit": one("BuildLimit"),
                    "cost": re.findall(r"<Cost\s+resourcetype=['\"](\w+)['\"][^>]*>([^<]*)<", b),
                    "garrison": one("MaxContained"), "physics": one("PhysicsInfo"), "rubble": one("DeadReplacement"),
                    "trains": len(re.findall(r"<Train\b", b)), "flags": re.findall(r"<Flag>([^<]*)<", b)}
    return None


def render(f, export=None, proto=None):
    """The sheet of `facts` as Markdown. `export`: what a game export wrote (vertices, files as
    (name, bytes)); `proto`: what `proto_of` read."""
    upm = f["upm"]
    w, d, h = f["size_m"]
    g = f["game"]
    rx, rz = g["radius"]
    out = [f"# {f['name']}", "",
           "Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.", ""]
    rows = [("Preset", f"`{f['preset']}`" if f["preset"] else "custom"), ("Style", f["style"])]
    if f["type"]:
        rows.append(("Type", f["type"]))
    if f["architecture"]:
        rows.append(("Architecture", f["architecture"]))
    rows.append(("Proto template", f"`{f['template']}`"))
    if f["notes"]:
        rows.append(("Notes", "; ".join(f["notes"])))
    out += _table(("Field", "Value"), rows)

    out += ["", "## Size", ""]
    rows = [("Width, with everything on it", _n(w), _n(w * upm)), ("Depth", _n(d), _n(d * upm)),
            ("Height, to the highest point", _n(h), _n(h * upm))]
    out += _table(("Measure", "Metres in Blender", "Game units"), rows)
    out += ["", f"One game unit is {_n(1 / upm, 3)} m in Blender."]

    out += ["", "## Triangles", ""]
    rows = [("Medium detail", f"{f['tris']:,}"), ("Low detail, the game's low-poly model", f"{f['tris_low']:,}"),
            ("Faces at medium detail", f"{f['faces']:,}")]
    if f["band"]:
        rows.append(("Target and accepted range", f"{f['band'][0]:,} ({f['band'][1]:,} to {f['band'][2]:,})"))
    out += _table(("Model", "Count"), rows)
    out += ["", "Where they go, at medium detail:", ""]
    out += _table(("Part", "Triangles", "Share"), [(n, c, f"{100 * c / f['tris']:.0f} %") for n, c in f["parts"]])

    out += ["", "## Texture", ""]
    rows = [("Size", f"{f['texture']} x {f['texture']}"), ("Painted at", f"{f['painted']} x {f['painted']}"),
            ("Bump map", f"{f['bump']} x {f['bump']}"), ("All its textures", f"{_n(f['texture_mb'])} MB"),
            ("Texels per game unit", _n(f["density"], 0)),
            ("Swatches under the paint", "yes" if f["materials"] else "no")]
    out += _table(("Field", "Value"), rows)

    out += ["", "## Collision and footprint", ""]
    over_x, over_z = w * upm / 2 - rx, d * upm / 2 - rz
    rows = [("Obstruction: units path around it, buildings place against it", f"{_n(2 * rx)} x {_n(2 * rz)}"),
            ("Model past the obstruction, on each side", f"{_n(over_x)} wide, {_n(over_z)} deep")]
    if f["boxes"]:
        bw = max(b[1] for b in f["boxes"]) - min(b[0] for b in f["boxes"])
        bd = max(b[3] for b in f["boxes"]) - min(b[2] for b in f["boxes"])
        bh = max(b[5] for b in f["boxes"]) - min(b[4] for b in f["boxes"])
        rows.append(("Collision shape", f"`{f['name'].lower()}`, its own: {len(f['boxes'])} boxes covering "
                     f"{_n(bw * upm)} x {_n(bd * upm)} x {_n(bh * upm)}"))
    elif f["collision"]:
        rows.append(("Collision shape", f"`{f['collision']}`, a stock shape shared by every generated "
                     "building, not fitted to this model"))
    rows += [("Ground decal", f"{_n(g['decal'][0])} x {_n(g['decal'][1])}"),
             ("Construction stages", g.get("stages")), ("Rubble", g.get("rubble")),
             ("Placement file", g.get("placement") or "the template's"), ("Footprint class", g.get("class") or "none")]
    out += _table(("Field", "Value"), rows)

    if f["shape"]:
        s, (cls, table) = f["shape"]
        out += ["", f"## Shape against the real models (class {cls})", ""]
        labels = (("height", "Height, game units"), ("slender", "Height over longest side"),
                  ("cover", "Share of the obstruction covered"), ("outside", "Share of what stands outside it"),
                  ("main", "Share in its largest part"), ("rim", "Share of the edge lined"),
                  ("levels", "Flat levels"), ("tris_low", "Triangles in the lower third"),
                  ("tris_mid", "Triangles in the middle third"), ("tris_high", "Triangles in the upper third"))
        rows = []
        for k, label in labels:
            q = table.get(k)
            rows.append((label, s[k], *(q if q else ("", "", ""))))
        out += _table(("Measure", "This building", "Low", "Median", "High"), rows)

    if f["attach"]:
        out += ["", "## Attach points", ""]
        out += _table(("Name", "x, y, z in metres"),
                      [(n, ", ".join(_n(c) for c in at)) for n, at in sorted(f["attach"].items())])

    if proto:
        out += ["", "## Game data", "", f"Read from the game's proto, entry `{proto['source']}`.", ""]
        cost = ", ".join(f"{float(v):g} {k}" for k, v in proto["cost"]) or "none"
        rows = [(k.capitalize(), proto[k]) for k in ("hit points", "line of sight", "build points", "build limit",
                                                     "garrison", "physics", "rubble", "trains") if proto[k] is not None]
        rows.insert(1, ("Cost", cost))
        rows.append(("Collision flags", ", ".join(x for x in proto["flags"] if x in FLAGS_SHOWN) or "none"))
        out += _table(("Field", "Value"), rows)

    if export:
        out += ["", "## This export", ""]
        out += [f"{export['vertices']:,} vertices, {export['triangles']:,} triangles, texture {export['format']}.", ""]
        total = sum(b for _, b in export["files"])
        out += _table(("File", "Bytes"), [(n, f"{b:,}") for n, b in export["files"]] + [("Total", f"{total:,}")])
    return "\n".join(out) + "\n"
