# SPDX-License-Identifier: GPL-3.0-or-later
"""The unit repaint screen's work: a unit's model and texture loaded with its UV islands
(tools/uv_atlas.py), painted again and again in memory as the recipe changes (tools/retexture.py),
then saved as a recipe that the retexture tool writes as the game reads it.

A session lives in its own folder of the work folder: the starting texture, the atlas, the
pictures the recipe names, the recipe. Nothing of it goes anywhere else."""
import base64
import json
import os
import re
import time

from . import use_core

use_core()
import numpy as np  # noqa: E402

import retexture  # noqa: E402  (tools/)
import uv_atlas  # noqa: E402
from aoe3game import ddt, gr2_mesh  # noqa: E402
from core import paint as painter  # noqa: E402

from . import inspector  # noqa: E402

OPS = ("recolour", "tone", "fill", "paste", "blur", "grain", "player", "ai")
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
MAX_SIDE = 4096                       # the largest texture a session paints (after its scale)


class RetexError(ValueError):
    pass


class Session:
    def __init__(self, folder, name, model, texture, start_file, scale, by, facts):
        self.folder, self.name, self.model = folder, name, model
        self.start_file, self.scale, self.by, self.facts = start_file, scale, by, facts
        isl = uv_atlas.write_atlas(model, texture, os.path.join(folder, "atlas"), by=by, facts=facts)
        with open(os.path.join(folder, "atlas", "atlas.json"), encoding="utf-8") as fh:
            self.atlas = json.load(fh)
        self.start = retexture.upscale(texture, scale)
        h, w = self.start.shape[:2]
        if max(h, w) > MAX_SIDE:
            raise RetexError(f"{w} x {h} after the scale: at most {MAX_SIDE} pixels a side")
        self.masks = retexture.Masks(self.atlas, w, h)
        _found, self.labels = uv_atlas.masks(isl, w, h)


def _png(rgba):
    return "data:image/png;base64," + base64.b64encode(painter.png_bytes(rgba, level=3)).decode("ascii")


def _labels_png(labels):
    """Each pixel's island (id + 1; 0 for none) as red + 256 green: the page reads it back."""
    v = labels.astype(np.int64)
    img = np.zeros(labels.shape + (3,), np.uint8)
    img[..., 0] = v & 255
    img[..., 1] = (v >> 8) & 255
    return _png(img)


def _folder(work, name):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(work, f"{_safe(name)}-{stamp}")
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(work, f"{_safe(name)}-{stamp}-{n}")
    os.makedirs(folder)
    return folder


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "unit"


def open_model(work, name, model, texture, texture_bytes=None, *, scale=1, by="bone", facts=None):
    """A session from a model read by gr2_mesh.read and its texture (H x W x 4 uint8, or None:
    a grey square). `texture_bytes`: the texture's own file (.ddt), kept so the result can be
    written in its format."""
    if by not in ("bone", "position"):
        raise RetexError("parts by: bone or position")
    scale = int(scale)
    if not 1 <= scale <= 8:
        raise RetexError("scale: 1 to 8")
    if not model["meshes"]:
        raise RetexError("the model holds no mesh this reader can open")
    folder = _folder(work, name)
    if texture is None:
        texture = np.full((256, 256, 4), 160, np.uint8)
    if texture_bytes is not None and texture_bytes[:4] == ddt.MAGIC:
        start_file = "start.ddt"
        data = texture_bytes
    else:
        start_file = "start.png"
        data = painter.png_bytes(np.asarray(texture, np.uint8))
    with open(os.path.join(folder, start_file), "wb") as fh:
        fh.write(data)
    return Session(folder, name, model, np.asarray(texture, np.uint8), start_file, scale, by, facts or {})


def load_files(work, model_path, texture_path=None, *, cache=None, granny=None, install=None, scale=1, by="bone"):
    """A session from a model file and, when given, its texture (.ddt or .png)."""
    with open(model_path, "rb") as fh:
        data = fh.read()
    try:
        model = gr2_mesh.read(uv_atlas.raw_model(data, cache, granny, install or os.path.dirname(model_path)))
    except LookupError as e:
        raise RetexError(f"{e}: set the cache folder and the Granny bridge in Settings") from None
    tex = raw = None
    if texture_path:
        with open(texture_path, "rb") as fh:
            raw = fh.read()
        tex = uv_atlas.read_image(texture_path)
    name = os.path.splitext(os.path.basename(model_path))[0]
    return open_model(work, name, model, tex, raw, scale=scale, by=by,
                      facts={"model": model_path, "texture": texture_path})


def load_game(work, game_folder, target, *, prefer=(), overlay=None, cache=None, granny=None, scale=1, by="bone"):
    """A session from a unit, anim file or model of a game copy, as tools/uv_atlas.py finds it
    (the model the unit shows standing, the texture its anim file gives it)."""
    import named_models
    game = named_models.Game(game_folder, overlays=[overlay] if overlay else [])
    try:
        where = game.resolve(target, list(prefer))
        data, src = game.read(where["model"])
        model = gr2_mesh.read(uv_atlas.raw_model(data, cache, granny, game_folder))
    except LookupError as e:
        raise RetexError(str(e)) from None
    found = game.texture(model["textures"], where["model"], where["replace"])
    tex = ddt.decode(found[1], 0) if found else None
    facts = {"target": target, "model": where["model"], "anim": where["anim"], "source": src,
             "texture": found[0] if found else None}
    return open_model(work, target, model, tex, found[1] if found else None, scale=scale, by=by, facts=facts)


def public(s):
    """What the page needs of a session."""
    h, w = s.start.shape[:2]
    shown = inspector.mesh_of(s.model)
    return {"name": s.name, "width": w, "height": h, "scale": s.scale, "start": _png(s.start),
            "labels": _labels_png(s.labels), "parts": s.atlas.get("parts", []),
            "islands": [{"id": r["id"], "part": r["part"], "bone": r["bone"], "pixels": r["pixels"],
                         "box": [v * s.scale for v in r["box"]]} for r in s.atlas["islands"]],
            "colours": {k: list(v) for k, v in uv_atlas.COLOURS.items()},
            "mesh": shown["mesh"] if shown else None, "triangles": shown["triangles"] if shown else 0,
            "facts": {k: v for k, v in (s.facts or {}).items() if isinstance(v, (str, int, float)) or v is None},
            "folder": s.folder}


def clean_ops(ops):
    """The ops as a recipe holds them: known ones, plain values, no switched-off ones."""
    if not isinstance(ops, list):
        raise RetexError("ops: a list")
    out = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or op.get("op") not in OPS:
            raise RetexError(f"op {i + 1}: one of {', '.join(OPS)}")
        if op.get("off"):
            continue
        out.append({k: v for k, v in op.items() if not k.startswith("_") and k != "off"
                    and isinstance(v, (str, int, float, bool, list))})
    return out


def paint(s, ops):
    """(result RGBA as a PNG data URL, report): every op but the AI ones, which need ComfyUI and
    run when the texture is written."""
    ops = clean_ops(ops)
    img = s.start.astype(np.float32)
    skipped, empty, missing, started = [], [], [], time.perf_counter()
    for i, op in enumerate(ops):
        if not op.get("where"):              # a step still being set up: nothing chosen yet
            empty.append(i)
            continue
        if op["op"] == "ai":
            skipped.append(i)
            continue
        try:
            retexture.apply(op, img, s.start, s.masks, s.folder)
        except retexture.RecipeError as e:
            if "selects nothing" in str(e):  # e.g. only islands taken out: nothing left to paint
                empty.append(i)
                continue
            if "no island of part" in str(e) or "no island moved by bone" in str(e):
                missing.append([i, str(e).split(" (atlas parts")[0]])   # a part this unit has not
                continue
            raise RetexError(f"op {i + 1} ({op['op']}): {e}") from None
        except (KeyError, ValueError, OSError) as e:
            raise RetexError(f"op {i + 1} ({op['op']}): {e}") from None
    result = np.clip(img + 0.5, 0, 255).astype(np.uint8)
    return {"image": _png(result), "seconds": round(time.perf_counter() - started, 3), "ai_skipped": skipped,
            "empty": empty, "missing": missing}


def add_picture(s, name, data_url):
    """A picture the recipe names (a swatch, a design, a mask), sent by the page as a PNG."""
    if not NAME.match(name or "") or not name.lower().endswith(".png") or name.startswith("start."):
        raise RetexError("a picture's name: letters, digits, _ . - and .png at the end")
    head, _, body = (data_url or "").partition(",")
    if head != "data:image/png;base64":
        raise RetexError("a PNG picture is expected")
    data = base64.b64decode(body)
    from core import pngio
    pngio.read_png(data)                   # it must read back
    with open(os.path.join(s.folder, name), "wb") as fh:
        fh.write(data)
    return name


def save(s, ops, *, out="new", fmt="same", mips="same", bump=True, bump_strength=6.0):
    """Writes the recipe beside the session's files; returns its path. The retexture tool then
    writes the texture (and runs the AI ops)."""
    if not NAME.match(out or "") or "." in out:
        raise RetexError("the texture's name: letters, digits, _ and -")
    if str(fmt).upper() not in ("SAME", *retexture.FORMATS):
        raise RetexError(f"format: same, {', '.join(retexture.FORMATS)}")
    if mips not in ("same", "full", "none"):
        raise RetexError("mips: same, full or none")
    ops = clean_ops(ops)
    parts = set(s.atlas.get("parts", []))
    for i, op in enumerate(ops):
        if not op.get("where"):
            raise RetexError(f"step {i + 1} ({op['op']}) paints nowhere yet: choose where, or switch it off")
        lacking = [w.split(":", 1)[1] for w in op["where"] if w.lstrip("-").startswith("part:")
                   and w.lstrip("-").split(":", 1)[1] not in parts]
        if lacking:
            raise RetexError(f"step {i + 1} names a part this unit has not ({', '.join(lacking)}): take it out")
    recipe = {"texture": s.start_file, "atlas": "atlas", "scale": s.scale, "out": out + ".ddt",
              "format": str(fmt).lower(), "mips": mips, "png": out + ".png", "ops": ops}
    if bump:
        recipe.update({"bump": out + "_b.ddt", "bump_strength": float(bump_strength)})
    path = os.path.join(s.folder, "recipe.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(recipe, fh, indent=1)
    return path
