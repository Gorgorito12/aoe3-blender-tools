# SPDX-License-Identifier: GPL-3.0-or-later
"""A survey's results as a table: the groups a texture or model survey measures (by origin,
category, role, material), with their quartiles and shares, instead of the text of its log.

It reads what the surveys write: a report (`textures.json`, `models.json`: the profile is computed
from it with the survey's own `profile()`, as the tool does) or a profile (`--profile-out`, or
`aoe3_blender_tools/profiles/`). A report names the scanned files; the table shows only the groups,
which name none (a group under the surveys' MIN_GROUP is left out by `profile()`)."""
import json
import os

from . import use_core

use_core()


class ResultsError(ValueError):
    pass


def _L(en, es):
    return {"en": en, "es": es}


# kind: text, int, q (quartiles q25/q50/q75), share (0..1), palette, top (most common values)
TEXTURE_COLUMNS = [
    ("origin", "text", _L("Origin", "Origen")),
    ("category", "text", _L("Category", "Categoría")),
    ("role", "text", _L("Role", "Papel")),
    ("material", "text", _L("Material", "Material")),
    ("count", "int", _L("Textures", "Texturas")),
    ("sizes", "top", _L("Sizes", "Tamaños")),
    ("formats", "top", _L("Formats", "Formatos")),
    ("palette", "palette", _L("Palette", "Paleta")),
    ("luminance", "q", _L("Luminance", "Luminancia")),
    ("saturation", "q", _L("Saturation", "Saturación")),
    ("grain", "q", _L("Grain", "Grano")),
    ("tileable", "share", _L("Tileable", "Repetible")),
    ("player_colour", "share", _L("Player colour", "Color del jugador")),
    ("cutout", "share", _L("Cut-out", "Recortada")),
]
MODEL_COLUMNS = [
    ("origin", "text", _L("Origin", "Origen")),
    ("category", "text", _L("Category", "Categoría")),
    ("count", "int", _L("Files", "Archivos")),
    ("models", "int", _L("Models", "Modelos")),
    ("tris", "q", _L("Triangles", "Triángulos")),
    ("verts", "q", _L("Vertices", "Vértices")),
    ("bones", "q", _L("Bones", "Huesos")),
    ("materials", "q", _L("Materials", "Materiales")),
    ("width", "q", _L("Width (units)", "Ancho (unidades)")),
    ("height", "q", _L("Height (units)", "Alto (unidades)")),
    ("skinned", "share", _L("Skinned", "Con piel")),
    ("animations", "int", _L("Animations", "Animaciones")),
]
HELP = {
    "textures": _L("Each row is a group of at least 8 distinct textures. Quartiles: the bar spans the middle half "
                   "(25 % to 75 %), the mark is the median. Grain: the fine detail left once the large shapes "
                   "are blurred away, over the mean brightness. Origin: own (the mod's), changed, stock.",
                   "Cada fila es un grupo de al menos 8 texturas distintas. Cuartiles: la barra abarca la mitad "
                   "central (del 25 % al 75 %), la marca es la mediana. Grano: el detalle fino que queda al "
                   "difuminar las formas grandes, sobre el brillo medio. Origen: own (del mod), changed, stock."),
    "models": _L("Each row is a group of at least 8 distinct Granny files. Quartiles: the bar spans the middle "
                 "half (25 % to 75 %), the mark is the median. Width and height in game units, where the model's "
                 "scale is known.",
                 "Cada fila es un grupo de al menos 8 archivos Granny distintos. Cuartiles: la barra abarca la "
                 "mitad central (del 25 % al 75 %), la marca es la mediana. Ancho y alto en unidades del juego, "
                 "cuando se conoce la escala del modelo."),
}


def _load(path):
    if not path or not os.path.isfile(path):
        raise ResultsError(f"no such file: {path}")
    if not path.lower().endswith(".json"):
        raise ResultsError("a survey's result is a .json file (textures.json, models.json or a profile)")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise ResultsError(f"not a survey's result: {e}") from None


def profile_of(data):
    """(kind, profile) of a report or a profile."""
    if isinstance(data, dict) and isinstance(data.get("groups"), list):
        g = data["groups"][0] if data["groups"] else {}
        return ("textures" if "role" in g or "textures" in data else "models"), data
    if isinstance(data, dict) and isinstance(data.get("textures"), list):
        import texture_survey
        return "textures", texture_survey.profile(data["textures"])
    if isinstance(data, dict) and isinstance(data.get("models"), list):
        import model_survey
        return "models", model_survey.profile(data["models"])
    raise ResultsError("not a texture or model survey's result")


def _row(kind, g):
    r = dict(g)
    if kind == "textures":
        r["formats"] = sorted(([k, v] for k, v in (g.get("formats") or {}).items()), key=lambda x: -x[1])
    else:
        size = g.get("size") or {}
        r["width"], r["height"] = size.get("width"), size.get("height")
        r["animations"] = (g.get("animations") or {}).get("count", 0)
    return r


def table(path):
    """{"kind", "facts", "help", "columns": [{key, kind, label}], "rows": [{key: value}]}."""
    kind, prof = profile_of(_load(path))
    columns = TEXTURE_COLUMNS if kind == "textures" else MODEL_COLUMNS
    keys = [c[0] for c in columns]
    rows = [{k: r.get(k) for k in keys} for r in (_row(kind, g) for g in prof.get("groups", []))]
    facts = {k: prof.get(k) for k in ("textures", "files", "distinct", "unread", "source") if k in prof}
    return {"kind": kind, "path": path, "facts": facts, "help": HELP[kind],
            "columns": [{"key": k, "kind": t, "label": label} for k, t, label in columns], "rows": rows}
