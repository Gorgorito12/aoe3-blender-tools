# SPDX-License-Identifier: GPL-3.0-or-later
"""The studio's "Your own model" screen: an .obj, .glb or .gltf read, prepared and checked as
scripts/mesh_to_game.py does it, for the 3D view; then exported by that script as a job.

A picture the repository cannot read (a JPEG) is sent back to the page, which decodes it and
returns a PNG; the PNG is kept in the work folder and handed to the script as --texture-png."""
import base64
import os

from aoe3game import bundle
from core import checks, meshprep, pngio
from core import profile as calibration
from core.objio import MeshError

import numpy as np


class MeshinError(ValueError):
    pass


def _png_b64(rgba):
    from core import paint
    return "data:image/png;base64," + base64.b64encode(paint.png_bytes(rgba)).decode("ascii")


def options(b):
    """The preparation options of a request, checked."""
    up = b.get("up") or "y"
    turn = int(b.get("turn") or 0)
    scale = float(b.get("scale") or 1)
    fit_units = float(b["fit_units"]) if b.get("fit_units") not in (None, "", 0, "0") else None
    if up not in ("y", "z") or turn not in (0, 90, 180, 270) or scale <= 0 or (fit_units is not None and fit_units <= 0):
        raise MeshinError("up y or z; turn 0, 90, 180 or 270; scale and size above 0")
    return {"up": up, "turn": turn, "scale": scale, "fit_units": fit_units, "flat": bool(b.get("flat"))}


def load(path, opts, picture_png=None, kind="BUILDING"):
    """The model for the page: mesh, texture, sizes, warnings and the checks; or what the page
    must decode ({"decode": data URL}) when its picture is not a PNG."""
    if not path or not os.path.isfile(path):
        raise MeshinError("choose a model file (.obj, .glb, .gltf)")
    try:
        mesh = meshprep.load(path)
        rgba = None
        if picture_png:
            data = base64.b64decode(picture_png.split(",", 1)[-1])
            rgba = np.asarray(pngio.read_png(data))
        else:
            pic = mesh.get("picture")
            if pic is None and mesh.get("texture") and os.path.isfile(mesh["texture"]):
                with open(mesh["texture"], "rb") as fh:
                    pic = fh.read()
            if pic is not None and pic[:8] != b"\x89PNG\r\n\x1a\n":
                mime = mesh.get("mime") or ("image/jpeg" if pic[:3] == b"\xff\xd8\xff" else "application/octet-stream")
                return {"decode": f"data:{mime};base64," + base64.b64encode(pic).decode("ascii")}
        texture = meshprep.texture_rgba(mesh, rgba)
        fit = opts["fit_units"] / bundle.UNITS_PER_METER if opts["fit_units"] else None
        prep = meshprep.prepare(mesh, up=opts["up"], scale=opts["scale"], fit=fit, turn=opts["turn"], flat=opts["flat"])
    except (MeshError, OSError, ValueError) as e:
        raise MeshinError(str(e)) from None
    prof = calibration.load()
    prop = calibration.prop_group("objects") if kind == "PROP" and prof is not None else None
    found = checks.check(meshprep.check_mesh(prep, texture.shape), 6000, prof, prop)
    w, d = prep["footprint"]
    size = bundle.game_size(prep["footprint"], profile=prof)
    pos = np.asarray(prep["positions"], np.float32)
    return {
        "mesh": {"positions": [round(float(v), 4) for v in pos.ravel()],
                 "normals": [round(float(v), 3) for v in np.asarray(prep["normals"]).ravel()],
                 "uvs": [round(float(v), 5) for v in np.asarray(prep["uvs"]).ravel()],
                 "indices": [int(i) for t in prep["triangles"] for i in t]},
        "texture": _png_b64(texture), "texture_size": [int(texture.shape[1]), int(texture.shape[0])],
        "triangles": len(prep["triangles"]), "vertices": len(prep["positions"]),
        "footprint": [round(w, 3), round(d, 3)], "height": round(prep["height"], 3),
        "units": [round(w * bundle.UNITS_PER_METER, 2), round(d * bundle.UNITS_PER_METER, 2)],
        "obstruction": list(size["radius"]), "class": size.get("class"),
        "obstruction_m": [round(size["radius"][0] / bundle.UNITS_PER_METER, 3), round(size["radius"][1] / bundle.UNITS_PER_METER, 3)],
        "warnings": prep["warnings"], "checks": [{"level": lv, "message": m} for lv, m in found],
    }


def keep_picture(work, picture_png):
    """The page's decoded picture as a PNG in the work folder, for --texture-png."""
    data = base64.b64decode(picture_png.split(",", 1)[-1])
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise MeshinError("the decoded picture is not a PNG")
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "picture.png")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def command_args(path, out, name, opts, b, picture=None):
    """mesh_to_game.py's arguments for these options."""
    args = ["--in", path, "--out", out, "--name", name, "--up", opts["up"], "--turn", str(opts["turn"]),
            "--scale", repr(opts["scale"])]
    if opts["fit_units"]:
        args += ["--fit-units", repr(opts["fit_units"])]
    if opts["flat"]:
        args.append("--flat")
    if picture:
        args += ["--texture-png", picture]
    for key in ("kind", "template", "prefix", "display", "folder", "texture"):
        if b.get(key):
            args += ["--" + key, str(b[key])]
    return args
