# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture maker screen's work: a photograph cropped on screen, made tileable and de-lit at
once without ComfyUI (core/texmaker.py's plain path), measured against the mod's own textures,
seen tiled 3 by 3; then kept in the texture library (core/texlib.py) with its licence. With
ComfyUI, the repaint runs as a task (tools/make_texture.py)."""
import base64
import os
import re

from . import use_core

use_core()
import numpy as np  # noqa: E402

from core import materials, pngio, texlib, texmaker  # noqa: E402
from core import paint as painter  # noqa: E402

NAME = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
SIZES = (128, 256, 512)


class TexError(ValueError):
    pass


def _png(rgb):
    return "data:image/png;base64," + base64.b64encode(painter.png_bytes(np.asarray(rgb, np.uint8), level=3)).decode("ascii")


class Source:
    """The photograph a texture is made from, kept in the work folder for the AI task."""

    def __init__(self, data_url, folder):
        head, _, body = (data_url or "").partition(",")
        if head != "data:image/png;base64":
            raise TexError("a PNG picture is expected")
        raw = base64.b64decode(body)
        img = np.asarray(pngio.read_png(raw))
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        self.rgb = np.ascontiguousarray(img[..., :3])
        if min(self.rgb.shape[:2]) < 16:
            raise TexError("the picture is too small")
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, "source.png")
        with open(self.path, "wb") as fh:
            fh.write(raw)
        self.last = None                      # (settings, texture, report) of the last preview


def _settings(b):
    try:
        cx, cy, part = float(b.get("cx", 0.5)), float(b.get("cy", 0.5)), float(b.get("part", 1.0))
        size = int(b.get("size", 256))
    except (TypeError, ValueError):
        raise TexError("crop and size are numbers") from None
    if size not in SIZES:
        raise TexError(f"size: one of {', '.join(map(str, SIZES))}")
    if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0.02 <= part <= 1):
        raise TexError("the crop: a centre inside the picture and a part from 0.02 to 1")
    return {"cx": cx, "cy": cy, "part": part, "size": size, "light": bool(b.get("light", True)),
            "fit": bool(b.get("fit", False)), "material": str(b.get("material") or ""),
            "category": str(b.get("category") or "buildings")}


def preview(src, b):
    """The texture as it would be kept, its 3 x 3 sheet and how it measures against the mod."""
    s = _settings(b)
    tex, report = texmaker.make(texmaker.crop(src.rgb, (s["cx"], s["cy"]), s["part"]), client=None, size=s["size"],
                                light=s["light"], heal_band=False, material=s["material"], category=s["category"],
                                fit=s["fit"])
    src.last = (s, tex, report)
    keep = {k: report[k] for k in ("seam", "seam_before", "style", "note", "seconds", "size") if k in report}
    return {"texture": _png(tex), "sheet": _png(texmaker.sheet(tex)), "report": keep}


def keep(src, b, folder=None):
    """Keeps the last preview in the library (it is made again when the settings changed)."""
    name, licence = str(b.get("name") or "").strip(), str(b.get("licence") or "").strip()
    if not NAME.match(name):
        raise TexError("the texture's name: letters, digits, _ and -")
    if not licence:
        raise TexError("say under what licence it may be used: a photograph carries the rights of whoever took it")
    s = _settings(b)
    if src.last is None or src.last[0] != s:
        preview(src, b)
    _s, tex, report = src.last
    try:
        tile_m = float(b.get("tile_m") or 2.0)
    except ValueError:
        raise TexError("metres per tile: a number") from None
    entry = texlib.save(tex, name, licence=licence, folder=folder, tile_m=tile_m, role=str(b.get("role") or ""),
                        style=str(b.get("style") or ""), report=report, source=os.path.basename(src.path))
    return entry


def ai_command(src, b, python, script, url):
    """The command line of tools/make_texture.py for the same crop, with ComfyUI."""
    s = _settings(b)
    name, licence = str(b.get("name") or "").strip(), str(b.get("licence") or "").strip()
    if not NAME.match(name):
        raise TexError("the texture's name: letters, digits, _ and -")
    if not licence:
        raise TexError("say under what licence it may be used")
    prompt = str(b.get("prompt") or "").strip()
    if not prompt:
        raise TexError("describe the material for ComfyUI (the prompt)")
    cmd = python + [script, "--name", name, "--licence", licence, "--image", src.path,
                    "--crop", f"{s['cx']},{s['cy']},{s['part']}", "--prompt", prompt, "--size", str(s["size"]),
                    "--tile-m", str(float(b.get("tile_m") or 2.0)), "--seed", str(int(b.get("seed") or 1)),
                    "--strength", str(float(b.get("strength") or 0.6)), "--url", url,
                    "--category", s["category"]]
    for flag, key in (("--material", "material"), ("--style", "style"), ("--role", "role"), ("--folder", "folder")):
        if b.get(key):
            cmd += [flag, str(b[key])]
    if not s["fit"]:
        cmd.append("--no-fit")
    if not s["light"]:
        cmd.append("--keep-light")
    return cmd


def library(folder=None):
    """Every texture of the library with a small picture of it."""
    out = []
    for name, entry in texlib.index(folder).items():
        img = texlib.image(name, folder)
        if img is not None and img.shape[0] > 128:
            k = img.shape[0] // 128
            img = img[::k, ::k]
        out.append({"name": name, "entry": entry, "image": _png(img) if img is not None else None})
    return {"folder": texlib.folder_of(folder), "textures": out, "in_use": in_use(), "roles": roles()}


_installed = {}


def use(on, folder=None):
    """Puts the library's textures under the painter (the buildings' previews show them), or the
    add-on's own swatches back."""
    global _installed
    if on:
        _installed = {f"{s} {r}": n for (s, r), n in texlib.install(folder=folder).items()}
    else:
        texlib.uninstall()
        _installed = {}
    return in_use()


def in_use():
    return dict(_installed)


def delete(name, folder=None):
    if not NAME.match(name or ""):
        raise TexError("no such texture")
    if texlib.read(name, folder) is None and texlib.image(name, folder) is None:
        raise TexError("no such texture")
    texlib.delete(name, folder)


def roles():
    """The styles and the roles their swatches play, for the form's choices."""
    return {style: sorted(table) for style, table in materials.MATERIALS.items()}
