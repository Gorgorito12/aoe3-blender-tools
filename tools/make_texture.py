# SPDX-License-Identifier: GPL-3.0-or-later
"""Makes a seamless, tileable texture from a picture or from a description, and keeps it in the
texture library with its licence and what it was made from (core/texmaker.py, core/texlib.py).
The same work the Texture Maker panel does, from the command line.

    venv\\Scripts\\python -I tools\\make_texture.py --name factory_roof --licence "my own photo"
        [--image photos\\factory.jpg] [--crop 0.3,0.8,0.25] [--prompt "rusted corrugated iron"]
        [--size 256] [--tile-m 2.0] [--seed 1] [--strength 0.6]
        [--style COLONIAL --role roof] [--folder <library>] [--url http://127.0.0.1:8188]
        [--material wood] [--category buildings] [--no-fit]
        [--lora aoe3bt_own.safetensors] [--lora-strength 0.8]
        [--no-ai] [--keep-light] [--no-heal] [--list]

--material and --category say what the texture is of and for: it is then measured against the
mod's own textures of that kind (the texture profile), and its grain and saturation are brought
to theirs unless --no-fit says to leave them. --image, --prompt, or both: a picture alone is only tiled and de-lit; words alone are drawn by
ComfyUI; together, the picture is repainted first. --crop is cx,cy,part of the picture (0..1 of
its width and height, and how much of its shorter side to take). --no-ai never asks ComfyUI, so
it needs no GPU and no model. --list prints the library instead of making anything.

JPEG (and anything else Blender reads) is decoded through bpy when it is installed; a PNG needs
nothing. The library lives outside this repository: generated textures and photographs are not
committed.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import comfy, texlib, texmaker  # noqa: E402
from core.pngio import read_png  # noqa: E402


def picture(path):
    """A picture file as an H x W x 3 uint8 array. PNG is read here; anything else goes through
    Blender when the bpy module is installed."""
    if path.lower().endswith(".png"):
        with open(path, "rb") as f:
            img = read_png(f.read())
        if img.shape[2] == 1:
            img = np.repeat(img, 3, axis=2)
        return img[:, :, :3]
    try:
        import bpy
    except ImportError:
        raise SystemExit(f"{os.path.basename(path)}: only PNG can be read without Blender "
                         "(pip install bpy, or save the picture as a PNG)")
    im = bpy.data.images.load(os.path.abspath(path), check_existing=False)
    w, h = im.size
    if not (w and h and im.has_data):
        raise SystemExit(f"{path}: Blender could not read this picture")
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    arr = (np.clip(px.reshape(h, w, 4), 0, 1) * 255 + 0.5).astype(np.uint8)
    bpy.data.images.remove(im)
    return arr[::-1, :, :3].copy()


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    folder = opt("--folder")
    if "--list" in argv:
        rows = texlib.index(folder)
        print(f"{texlib.folder_of(folder)}: {len(rows)} textures")
        for name, e in rows.items():
            where = f"{e['style']} {e['role']}" if e.get("style") and e.get("role") else "-"
            print(f"  {name:24} {e.get('size', '?')} px  {e.get('tile_m', '?')} m  {where:20} "
                  f"join {e.get('seam', '?')}  {e.get('mode') or '?'}  {e.get('licence', '?')}")
        return 0

    name = opt("--name")
    licence = opt("--licence")
    if not name or not licence:
        raise SystemExit("--name and --licence are both needed (run with --list to see the library)")
    image, prompt = opt("--image"), opt("--prompt", "")
    if not image and not prompt:
        raise SystemExit("give --image, --prompt, or both")
    source = None
    if image:
        source = picture(image)
        if "--crop" in argv:
            cx, cy, part = (float(v) for v in opt("--crop").split(","))
            source = texmaker.crop(source, (cx, cy), part)
        else:
            source = texmaker.crop(source)
    client = None
    if "--no-ai" not in argv and (prompt or source is None):
        client = comfy.Client(opt("--url", comfy.DEFAULT_URL), timeout=300)
        problems = client.check()
        if problems:
            raise SystemExit("; ".join(problems))
    if client is None and source is None:
        raise SystemExit("a prompt alone needs ComfyUI: give --image, or drop --no-ai")
    out, report = texmaker.make(source, prompt=prompt, client=client, size=int(opt("--size", "256")),
                                seed=int(opt("--seed", "1")),
                                strength=float(opt("--strength", "0.6")),
                                light="--keep-light" not in argv,
                                heal_band="--no-heal" not in argv,
                                material=opt("--material", ""),
                                category=opt("--category", "buildings"), fit="--no-fit" not in argv,
                                lora=opt("--lora"), lora_strength=float(opt("--lora-strength", "0.8")),
                                on_progress=lambda s: print("  " + s, flush=True))
    entry = texlib.save(out, name, licence=licence, folder=folder,
                        tile_m=float(opt("--tile-m", "2.0")), role=opt("--role", ""),
                        style=opt("--style", ""), report=report,
                        source=os.path.basename(image) if image else "",
                        strength=float(opt("--strength", "0.6")) if source is not None else None)
    print(f"{name}: {entry['size']} px, {report['mode']}, join {report['seam']} "
          f"(was {report['seam_before']}), {report['seconds']} s")
    st = report.get("style")
    if st:
        was = f" (was {st['before_fit']} before fitting)" if "before_fit" in st else ""
        print(f"  against {st['against']} ({st['textures']} textures): grain {st['grain']:+}, "
              f"saturation {st['saturation']:+}, luminance {st['luminance']:+} widths; off {st['off']}{was}")
    if report.get("note"):
        print("  " + report["note"])
    print(f"  {os.path.join(texlib.folder_of(folder), name)}.png, .json and _x3.png (tiled 3 by 3)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
