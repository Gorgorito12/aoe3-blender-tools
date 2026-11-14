# SPDX-License-Identifier: GPL-3.0-or-later
"""Renders contact sheets of models: a grid of sampled models per origin and category from a model
survey, each with its own texture when the texture survey found it, or a named list of models
from a game copy, each with its caption. To look at how the art of a mod is built - its
proportions, its silhouettes, how its textures sit on its models - and to compare units and
buildings side by side.

    venv\\Scripts\\python tools\\model_sheets.py <models.json> --cache <survey cache> --out <folder>
        [--textures <textures.json>] [--groups own:buildings,stock:nuggets] [--cell 160]
        [--cols 8] [--rows 6] [--seed 3]

    venv\\Scripts\\python tools\\model_sheets.py --models <list.txt> --game <game folder> --out <file.png>
        [--cell 220] [--cols 6] [--title "..."] [--keep-scale]
        [--cache <folder>] [--granny <bridge.exe>] [--granny-install <folder>]

--models    one entry per line, `caption | target`; the target is a proto name (its <AnimFile>,
            then the model that file shows standing), an anim file, or a model, relative to the
            game's art folder (tools/named_models.py, which also checks a list without Blender).
            Riders, weapons and other attachments are not drawn: list them as entries of their
            own (their anim file or model).
--keep-scale  one scale for the whole sheet, every model standing on the same line, so a house
            and a soldier compare fairly (default: each model fills its cell).
--cache, --granny, --granny-install   a compressed model (most of the game's archived ones) is
            read from the cache of uncompressed copies tools/model_survey.py keeps (named by the
            original's MD5), or written there by the external Granny bridge (--granny; its
            runtime from --granny-install, default the game folder). Loose uncompressed copies
            (tools/uncompress_models.py) need neither.

Writes the sheet and, beside it, a .txt naming what each cell shows (model, texture, triangles,
size in metres) or why it is empty. The cells are rendered with an orthographic three-quarter
camera.

The sheets are pictures of the mod's art: they are written outside any repository, like the
reports they come from. Needs Blender (the bpy module) and numpy.
"""
import hashlib
import json
import os
import sys
import tempfile

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import model_survey as ms  # noqa: E402
import named_models as nm  # noqa: E402
import texture_survey as ts  # noqa: E402
from aoe3_blender_tools.aoe3game import ddt, gr2, gr2_mesh  # noqa: E402
from aoe3_blender_tools.core import blender_io, gr2_import, render  # noqa: E402
from aoe3_blender_tools.core.pngio import encode_png  # noqa: E402

BACKGROUND = np.array([70, 80, 70])


def texture_index(textures):
    """{file stem: record} of the diffuse textures, the largest of each name."""
    out = {}
    for t in textures:
        if "error" in t or t.get("role") in ("bump", "spec", "ui", "decal"):
            continue
        stem = os.path.splitext(os.path.basename(ts.norm(t["path"]).replace("\\", "/")))[0]
        if stem not in out or t["w"] > out[stem]["w"]:
            out[stem] = t
    return out


def image_for(record, index):
    for name in record.get("textures", ()):
        stem = os.path.splitext(name)[0]
        if stem.endswith(("_b", "_n", "_spec", "_s")) or stem not in index:
            continue
        try:
            return texture_image(ts._read(*index[stem]["at"]))
        except Exception:
            continue
    return None


def texture_image(data, name="sheet_tex"):
    """A Blender image of a .ddt's diffuse colour, at the first mip level of 256 or less."""
    hd = ddt.read_header(data)
    level = 0
    while level + 1 < len(hd.levels) and max(hd.width, hd.height) >> (level + 1) >= 256:
        level += 1
    rgba = ddt.decode(data, level).copy()
    rgba[:, :, 3] = 255
    return blender_io._image_from_array(name, rgba)


def on_background(rgba):
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return (rgba[:, :, :3] * a + BACKGROUND * (1 - a)).astype(np.uint8)


def render_one(record, cache, index, cell):
    data = ts._read(*record["at"])
    model = gr2_mesh.read(ms.raw_bytes(data, record["md5"], (None, cache, cache)))
    if not model["meshes"]:
        return None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = gr2_import.create(model, "m", image_for(record, index) if index else None)
    return on_background(render.render_rgba(obj, size=cell))


# --------------------------------------------------------------------------------------------------
# A named list

def text_strip(text, width, size, fg=(1.0, 1.0, 1.0), bg=(0.12, 0.12, 0.12)):
    """A line of text as an RGB strip `width` wide (Blender's render stamp draws it)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    cam = bpy.data.objects.new("strip_camera", bpy.data.cameras.new("strip_camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, size + 5, 100
    r.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    r.use_stamp = True
    for flag in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_frame",
                 "use_stamp_frame_range", "use_stamp_memory", "use_stamp_hostname", "use_stamp_camera",
                 "use_stamp_lens", "use_stamp_scene", "use_stamp_marker", "use_stamp_filename",
                 "use_stamp_sequencer_strip"):
        if hasattr(r, flag):
            setattr(r, flag, False)
    r.use_stamp_note, r.stamp_note_text = True, text
    r.stamp_font_size = size
    r.stamp_foreground = (*fg, 1.0)
    r.stamp_background = (*bg, 1.0)
    r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
    r.filepath = os.path.join(tempfile.gettempdir(), f"aoe3_strip_{os.getpid()}.png")
    try:
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(r.filepath)
        try:
            rgba = blender_io.image_rgba(img)
        finally:
            bpy.data.images.remove(img)
    finally:
        if os.path.exists(r.filepath):
            os.remove(r.filepath)
    out = np.empty(rgba.shape[:2] + (3,), np.uint8)
    out[:] = (np.array(bg) * 255 + 0.5).astype(np.uint8)
    lit = rgba[:, :, 3] > 0
    out[lit] = rgba[:, :, :3][lit]
    return out


def wrap(text, width, size, lines=2):
    """The text in at most `lines` lines that fit `width` pixels at that font size."""
    per = max(4, int(width / (0.65 * size)))
    out, line = [], ""
    for word in text.split():
        while len(word) > per:
            if line:
                out.append(line)
                line = ""
            out.append(word[:per])
            word = word[per:]
        if line and len(line) + 1 + len(word) > per:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(line)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][:per - 3] + "..."
    return out or [""]


def raw_model(data, cache, granny, install):
    """The model's bytes with every section uncompressed (see the docstring's --cache)."""
    if gr2.header_facts(data).get("raw"):
        return data
    if not cache:
        raise nm.Missing("compressed: no --cache", "compressed: give --cache (and --granny to fill it)")
    md5 = hashlib.md5(data).hexdigest()
    if not granny and not os.path.exists(os.path.join(cache, "raw", md5 + ".gr2")):
        raise nm.Missing("compressed: no --granny", "compressed and not in the cache: give --granny")
    for sub in ("raw", "src"):
        os.makedirs(os.path.join(cache, sub), exist_ok=True)
    return ms.raw_bytes(data, md5, (granny, install, cache))


def load_entry(game, target, cache, granny, install):
    """(model dict, textures, facts) of one entry; textures: {index in model["textures"], or -1
    for the triangles with none: .ddt bytes}. nm.Missing or RuntimeError says why it has none."""
    where = game.resolve(target)
    data, src = game.read(where["model"])
    model = gr2_mesh.read(raw_model(data, cache, granny, install))
    if not model["meshes"]:
        raise nm.Missing("unreadable vertices" if model["skipped"] else "no mesh",
                         "its vertices are stored in a way this reader cannot open"
                         if model["skipped"] else "the model has no mesh")
    textures, names = {}, []
    used = sorted({int(k) for m in model["meshes"] for k in m["face_textures"]})
    for k in used:
        found = game.texture([model["textures"][k]], where["model"]) if k >= 0 else None
        if found is not None:
            textures[k] = found[1]
            names.append(found[0])
    if -1 in used or not textures:
        found = game.texture(model["textures"], where["model"])
        if found is not None:
            textures[-1] = found[1]
            names.append(found[0])
    pts = np.concatenate([m["positions"] for m in model["meshes"]])
    facts = dict(where, source=src, textures=sorted(set(names)),
                 tris=int(sum(len(m["triangles"]) for m in model["meshes"])),
                 size=[round(float(v), 2) for v in pts.max(0) - pts.min(0)])
    return model, textures, facts


def named_sheet(entries, game, out, cell=220, cols=6, title=None, keep_scale=False,
                cache=None, granny=None, install=None):
    """Renders the list into `out` (and its .txt); returns the cells' lines."""
    loaded = []
    for caption, target in entries:
        try:
            loaded.append((caption, target) + load_entry(game, target, cache, granny, install) + (None,))
        except (LookupError, RuntimeError, ValueError, gr2.Gr2Error) as exc:
            loaded.append((caption, target, None, None, None, exc))
    scale = None
    if keep_scale:
        extents = []
        for _c, _t, model, _tex, _f, err in loaded:
            if err is None:
                bpy.ops.wm.read_factory_settings(use_empty=True)
                extents.append(render.view_extent(gr2_import.create(model, "m")))
        scale = max(extents) * 1.02 if extents else None
    size = max(11, min(15, cell // 16))
    line_h = size + 5
    cap_h = 2 * line_h
    rows = max(1, (len(loaded) + cols - 1) // cols)
    sheet = np.full((rows * (cell + cap_h), cols * cell, 3), 40, np.uint8)
    lines = []
    for n, (caption, target, model, tex, facts, err) in enumerate(loaded):
        y, x = divmod(n, cols)
        top, left = y * (cell + cap_h), x * cell
        if err is None:
            try:
                bpy.ops.wm.read_factory_settings(use_empty=True)
                images = {k: texture_image(b, f"sheet_tex{k}") for k, b in tex.items()}
                obj = gr2_import.create(model, "m", images.pop(-1, None), images=images)
                img = on_background(render.render_rgba(obj, size=cell, scale=scale,
                                                       ground=0.04 if keep_scale else None))
                sheet[top:top + cell, left:left + cell] = img
            except Exception as exc:  # noqa: BLE001 - one bad model leaves its cell empty
                err = nm.Missing("render failed", f"render failed ({type(exc).__name__}: {exc})")
        if err is None:
            text = wrap(caption, cell - 6, size, 2)
            colours = [(1.0, 1.0, 1.0)] * 2
            lines.append(f"row {y + 1} col {x + 1}: {caption} | {target} -> {facts['model']}"
                         f" ({facts['source']}), textures {', '.join(facts['textures']) or 'none'},"
                         f" {facts['tris']} tris, size {facts['size']} (metres as the file declares them)"
                         + (f", anim {facts['anim']}" if facts["anim"] else ""))
        else:
            sheet[top:top + cell, left:left + cell] = (90, 50, 50)
            short = getattr(err, "short", None) or str(err)
            text = wrap(caption, cell - 6, size, 1) + wrap(short, cell - 6, size, 1)
            colours = [(1.0, 1.0, 1.0), (1.0, 0.75, 0.6)]
            lines.append(f"row {y + 1} col {x + 1}: {caption} | {target} -> NOT SHOWN: {err}")
        for i, t in enumerate(text[:2]):
            strip = text_strip(t, cell, size, fg=colours[i])
            h = min(line_h, strip.shape[0])
            sheet[top + cell + i * line_h:top + cell + i * line_h + h, left:left + cell] = strip[:h]
        print(lines[-1], flush=True)
    if title:
        sheet = np.concatenate([text_strip(title, cols * cell, size + 4), sheet], axis=0)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(encode_png(sheet))
    with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as fh:
        fh.write((f"{title}\n" if title else "") + f"{len(loaded)} entries, "
                 f"{'one scale' if keep_scale else 'each model fills its cell'}\n"
                 + "\n".join(lines) + "\n")
    return lines


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    if "--models" in argv:
        if not opt("--models") or not opt("--game") or not opt("--out"):
            print(__doc__)
            return 2
        report = os.path.splitext(opt("--out"))[0] + ".txt"
        if os.path.abspath(report).lower() == os.path.abspath(opt("--models")).lower():
            print("--out would write its .txt over the list: name the sheet differently")
            return 2
        with open(opt("--models"), encoding="utf-8-sig") as fh:
            entries = nm.parse_list(fh.read())
        lines = named_sheet(entries, nm.Game(opt("--game")), opt("--out"), int(opt("--cell", "220")),
                            int(opt("--cols", "6")), opt("--title"), "--keep-scale" in argv,
                            opt("--cache"), opt("--granny"), opt("--granny-install", opt("--game")))
        bad = sum("NOT SHOWN" in ln for ln in lines)
        print(f"{len(lines) - bad} of {len(lines)} shown -> {opt('--out')}")
        return 1 if bad else 0
    src = next((a for a in argv if a.lower().endswith(".json") and a != opt("--textures")), None)
    cache, out = opt("--cache"), opt("--out")
    if not src or not cache or not out:
        print(__doc__)
        return 2
    with open(src, encoding="utf-8") as fh:
        models = json.load(fh)["models"]
    index = None
    if opt("--textures"):
        with open(opt("--textures"), encoding="utf-8") as fh:
            index = texture_index(ts.name(json.load(fh)["textures"]))
    wanted = [tuple(g.split(":")) for g in opt("--groups", "own:buildings,own:units,stock:nuggets,stock:objects").split(",")]
    cell, cols, rows = int(opt("--cell", "160")), int(opt("--cols", "8")), int(opt("--rows", "6"))
    rng = np.random.default_rng(int(opt("--seed", "3")))
    os.makedirs(out, exist_ok=True)
    for origin, cat in wanted:
        pool, seen = [], set()
        for r in models:
            if ("error" in r or r["origin"] != origin or r["category"] != cat or not r.get("tris")
                    or r["md5"] in seen):
                continue
            seen.add(r["md5"])
            pool.append(r)
        if not pool:
            print(f"{origin} {cat}: nothing to render")
            continue
        order = rng.permutation(len(pool))
        sheet = np.full((rows * cell, cols * cell, 3), 40, np.uint8)
        lines, n = [], 0
        for i in order:
            if n >= cols * rows:
                break
            r = pool[int(i)]
            try:
                img = render_one(r, cache, index, cell)
            except Exception as exc:
                lines.append(f"skipped ({type(exc).__name__}): {r['path']}")
                continue
            if img is None:
                continue
            y, x = divmod(n, cols)
            sheet[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell] = img
            lines.append(f"row {y + 1} col {x + 1}: {r['tris']} tris, {r['bones']} bones, size {r.get('size')}  {r['path']}")
            n += 1
        path = os.path.join(out, f"models_{origin}_{cat}.png")
        with open(path, "wb") as fh:
            fh.write(encode_png(sheet))
        with open(path[:-4] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(f"{origin} {cat}: {len(pool)} distinct models, {n} shown\n" + "\n".join(lines) + "\n")
        print(f"{origin} {cat}: {n} of {len(pool)} -> {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
