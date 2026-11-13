# SPDX-License-Identifier: GPL-3.0-or-later
"""A labelled grid of presets rendered as scripts/generate.py renders them (same sky, sun, grass
and three-quarter camera): the galleries of the README.

    venv\\Scripts\\python tools\\gallery.py --style AFRICAN --out examples\\african_gallery.jpg
    venv\\Scripts\\python tools\\gallery.py --style PROP --out examples\\props_gallery.jpg --cols 4
        [--cell 480x360] [PRESET ...]

Needs Blender (the bpy module). About ten seconds a cell on a CPU.
"""
import os
import sys
import tempfile

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate  # noqa: E402
from aoe3_blender_tools.core import blender_io, building, paint  # noqa: E402


def label(key, style):
    words = key.split("_")[1:] if style in ("AFRICAN", "PROP") else key.split("_")
    return " ".join(w.title() for w in words)


def cell(key, w, h, tmp):
    """One preset rendered at w x h, its label stamped in a corner, as an RGB array."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    p = building.PRESETS[key]
    model = building.build(p)
    obj = blender_io.create_object(model, paint.paint(model))
    scene = bpy.context.scene
    cam = generate.setup_render(scene)
    scene.render.resolution_x, scene.render.resolution_y = w, h
    r = scene.render
    r.use_stamp = True
    for flag in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_frame",
                 "use_stamp_frame_range", "use_stamp_memory", "use_stamp_hostname", "use_stamp_camera",
                 "use_stamp_lens", "use_stamp_scene", "use_stamp_marker", "use_stamp_filename",
                 "use_stamp_sequencer_strip", "use_stamp_note"):
        if hasattr(r, flag):
            setattr(r, flag, False)
    r.use_stamp_note, r.stamp_note_text = True, label(key, p.style)
    r.stamp_font_size = 12
    r.stamp_background = (0, 0, 0, 0)
    path = os.path.join(tmp, key + ".jpg")
    az, el, clay = generate.VIEWS["front34"]
    generate.shoot(scene, cam, obj, path, az, el, clay)
    return blender_io.image_rgb(path)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    out = opt("--out")
    style = (opt("--style") or "").upper()
    keys = [a for a in argv if a.upper() in building.PRESETS] or \
        [k for k, p in building.PRESETS.items() if p.style == style]
    if not out or not keys:
        print(__doc__)
        return 2
    cols = int(opt("--cols", "6"))
    w, h = (int(v) for v in opt("--cell", "480x360").split("x"))
    rows = (len(keys) + cols - 1) // cols
    sheet = np.full((rows * h, cols * w, 3), 128, np.uint8)
    with tempfile.TemporaryDirectory() as tmp:
        for i, key in enumerate(keys):
            y, x = divmod(i, cols)
            sheet[y * h:(y + 1) * h, x * w:(x + 1) * w] = cell(key, w, h, tmp)[:h, :w]
            print(key, flush=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    img = blender_io._image_from_array("gallery", sheet)
    img.filepath_raw = os.path.abspath(out)
    img.file_format = "JPEG"
    bpy.context.scene.render.image_settings.quality = 88
    img.save()
    print(f"{len(keys)} presets -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
