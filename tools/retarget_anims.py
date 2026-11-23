# SPDX-License-Identifier: GPL-3.0-or-later
"""A unit's animations put on another model, for a modder who wants them on a unit of their own:
by default the Aztec Macehualtin's slinger animations (idle, walk, jog, run, the sling attack and
its reload, the melee, the torch, cheers, recoils and every death) on the standard infantry
skeleton of Wars of Liberty's models.

    venv\\Scripts\\python -I tools/retarget_anims.py --game <game copy> --out <folder>
        [--recipe NAME|<recipe.json>]... [--granny-helper <exe>] [--only CLIP,...]
        [--preview <png>] [--preview-clips CLIP,...] [--sheets] [--fps 60]

Why they play only on their own model (aoe3game/gr2_retarget.py, measured in the game's code): the
game binds an animation to a model only through a track group named after the model. The
Macehualtin's model and its animations are named `bone_master`; every standard infantry model is
named `Bip01`, so on them the slinger's animations are not played and the model stands in its bind
pose. Both are the same biped (the same bones, axes and lengths; `bone_master` above `Bip01`).

What it writes below --out, per recipe:
- `art\\<recipe "folder">\\<prefix><clip>.gr2`: each clip of the source anim file that lives in
  `clips_from`, put on the target's skeleton (`gr2_retarget.Retarget`: rotations from the source,
  bone lengths from the target, the props and the hit point bar copied) in one track group named
  after the target model, and `<clip>.gr2.precomp`, its tag file with the tags moved to the target's
  bones (the projectile's `LAUNCHPOINT` kept);
- `<recipe name>-anims.xml`: what the target unit's anim file needs: the source's `definebone`
  lines, the recipe's `attachments` (the sling, whose own animations play on its own model through
  `syncanims` and need no change; the torch), the `<attach>` lines for the model's component, and
  every `<anim>` of the source with its files pointed at the new clips and its tags (attack, sound,
  footsteps) as they were;
- `<recipe name>-report.txt`: bones matched, kept at rest and dropped, the root's scale, the tags
  moved and kept per clip.
With --preview, one review sheet: per chosen clip, a few moments of the source model playing the
original clip beside each target playing its clip, and a first row with what the game shows today
(the target in its bind pose). With --sheets, `sheets\\<clip>.png`: twelve moments of each clip on
every model. The sling is drawn on `Bip01 Prop1` with its own animation of the same name.

Recipes: a name of RECIPES (`skirmisher`, `native`) or a JSON file with the same keys; several
--recipe make one preview with every target. Compressed game files are expanded by the game's own
Granny runtime through the 32-bit helper of recompress_models.py; nothing of the game is stored
here. Refuses a Steam folder as output.
"""
import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
import xmbedit  # noqa: E402
from aoe3game import ddt, gr2, gr2_mesh, gr2_skin, precomp  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import Animation, Rig  # noqa: E402
from aoe3game.gr2_retarget import Retarget, retarget_precomp  # noqa: E402

MACEHUALTIN = {
    "source_model": "units\\natives\\aztec\\macehuatlin\\macehuatlin_01",
    "source_animfile": "units\\natives\\aztec\\macehuatlin\\macehuatlin.xml",
    "clips_from": "animation_library\\natives\\macehuatlin",
    "attachments": ["sling", "torch"],
    "component": "ModelComp",
    # drawn in the preview only: the sling hangs on the hand and plays its own clip of each name
    "draw_attach": [{"model": "units\\natives\\aztec\\macehuatlin\\macehuatlin_sling_01",
                     "clips_from": "animation_library\\natives\\macehuatlin\\sling",
                     "frombone": "bone_sling", "tobone": "Bip01 Prop1"}],
    "bone_map": {},
    "held": ["Bip01 Prop1", "Bip01 Prop2"],
    "markers": ["bone hitpointbar"],
    "prefix": "",
}
RECIPES = {
    # a European-style infantry model of Wars of Liberty (its light infantry)
    "skirmisher": dict(MACEHUALTIN, name="skirmisher",
                       target_model="WoL\\units\\infantry_ranged\\skirmisher\\skirmisher_age2",
                       folder="WoL\\units\\infantry_ranged\\slinger\\anims_skirmisher"),
    # the game's native rifleman, the body many native units of the mod use
    "native": dict(MACEHUALTIN, name="native", target_model="units\\natives\\rifleman",
                   folder="WoL\\units\\infantry_ranged\\slinger\\anims_native"),
}
DEFAULT_PREVIEW = ("volley_idle", "walk", "run", "volley_attack1", "volley_reload", "charge_attack1",
                   "torch_throwA", "death_standing_rifleman_A", "havoc_death")
FPS = 60.0


# --------------------------------------------------------------------------------------------------
# The game's files


class Game:
    """Art files of a game copy, loose first, then the art archives; Granny files expanded by the
    game's runtime (the helper), with their root type reference put back."""

    def __init__(self, folder, helper, work):
        self.folder, self.helper, self.work = folder, helper, work
        self._index = None

    def index(self):
        if self._index is None:
            self._index = {}
            art = os.path.join(self.folder, "art")
            for name in sorted(os.listdir(art)):
                if name.lower().endswith(".bar"):
                    path = os.path.join(art, name)
                    for stored, off, size in bar.read_entries(path):
                        key = stored.lower().replace("/", "\\")
                        if key.startswith("art\\"):
                            key = key[4:]
                        self._index.setdefault(key, (path, off, size))
        return self._index

    def raw(self, rel, ext=".gr2"):
        rel = rel.lower().replace("/", "\\")
        if ext and not rel.endswith(ext):
            rel += ext
        loose = os.path.join(self.folder, "art", rel)
        if os.path.exists(loose):
            with open(loose, "rb") as f:
                return f.read()
        hit = self.index().get(rel)
        if hit is None:
            raise FileNotFoundError(f"art\\{rel} is neither loose nor in an archive")
        path, off, size = hit
        with open(path, "rb") as f:
            f.seek(off)
            return f.read(size)

    def granny(self, rel):
        data = self.raw(rel)
        try:
            compressed = any(s.compression for s in gr2.read_container(data).sections)
        except gr2.Gr2Error:
            compressed = True
        if not compressed:
            return data
        from recompress_models import Runtime, put_root_type
        from uncompress_models import ROOT_TYPE
        rt = Runtime(self.helper, os.path.join(self.folder, "granny2.dll"), self.work)
        flat = rt.recompress(data, 0, 0)
        return put_root_type(flat, data[ROOT_TYPE:ROOT_TYPE + 8])

    def anim_file(self, rel):
        """The text of an anim file: a loose .xml, else the archives' compiled .xml.xmb."""
        rel = rel.lower().replace("/", "\\")
        loose = os.path.join(self.folder, "art", rel)
        if os.path.exists(loose):
            with open(loose, "rb") as f:
                return f.read().decode("utf-8-sig", "replace")
        data = self.raw(rel + ".xmb", "")
        elems, attrs, root = xmbedit.parse(xmbedit.decode(data))
        return xmbedit.to_xml(elems, attrs, root)

    def texture(self, stored):
        low = stored.lower().replace("/", "\\")
        at = low.find("\\art\\")
        rel = low[at + 5:] if at >= 0 else os.path.basename(low)
        rel = os.path.splitext(rel)[0]
        try:
            return ddt.decode(self.raw(rel, ".ddt"))
        except (FileNotFoundError, ValueError, KeyError):
            return None


def model_name(root):
    models = root.get("Models") or []
    return models[0].get("Name") if models and models[0] is not None else None


# --------------------------------------------------------------------------------------------------
# The anim file


def parse_animfile(text):
    """The anim file's root element; names compared lower case."""
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip("﻿"))
    return ET.fromstring(text)


def _low(e):
    return e.tag.lower()


def _head(e):
    return (e.text or "").strip()


def anim_clips(root, clips_from):
    """The clips (base names, the file's own spelling, in order of appearance) of the anim file's
    <anim> blocks that live directly in the folder `clips_from`."""
    folder = clips_from.lower().rstrip("\\") + "\\"
    out = []
    for anim in root.iter():
        if _low(anim) != "file":
            continue
        path = _head(anim).replace("/", "\\")
        low = path.lower()
        if low.startswith(folder) and "\\" not in low[len(folder):]:
            name = path[len(folder):]
            if name.lower() not in [n.lower() for n in out]:
                out.append(name)
    return out


def _emit(e, depth, out):
    tab = "\t" * depth
    attrs = "".join(f' {k}="{v}"' for k, v in e.attrib.items())
    head = _head(e)
    kids = list(e)
    if not kids:
        out.append(f"{tab}<{e.tag}{attrs}>{head}</{e.tag}>" if head else f"{tab}<{e.tag}{attrs}/>")
        return
    out.append(f"{tab}<{e.tag}{attrs}>{head}")
    for k in kids:
        _emit(k, depth + 1, out)
    out.append(f"{tab}</{e.tag}>")


def anim_blocks(root, recipe, produced):
    """The text for the target unit's anim file (see the module's note). `produced`: {clip base
    name lower: new art path without extension}."""
    import copy
    keep = {a.lower() for a in recipe.get("attachments", [])}
    folder = recipe["clips_from"].lower().rstrip("\\") + "\\"
    out = ["<!-- Generated by aoe3-blender-tools tools/retarget_anims.py: the animations of "
           f"{recipe['source_animfile']} on {recipe['target_model']}. -->",
           "<!-- 1. At the top of the unit's anim file: -->"]
    for e in root:
        if _low(e) == "definebone":
            _emit(e, 0, out)
    out.append("<!-- 2. Attachments (beside the unit's own): -->")
    for e in root:
        if _low(e) == "attachment" and _head(e).lower() in keep:
            _emit(e, 0, out)
    out.append("<!-- 3. Inside the model's component (in each LowPoly branch when it has them): -->")
    seen = set()
    for e in root.iter():
        if _low(e) == "attach" and e.attrib.get("a", "").lower() in keep:
            parent_is_anim = False
            key = tuple(sorted(e.attrib.items()))
            for anim in root:
                if _low(anim) == "anim" and e in list(anim):
                    parent_is_anim = True
            if parent_is_anim or key in seen:
                continue
            seen.add(key)
            _emit(e, 0, out)
    out.append("<!-- 4. The animations: -->")
    for e in root:
        if _low(e) != "anim":
            continue
        a = copy.deepcopy(e)
        for f in a.iter():
            if _low(f) == "file":
                path = _head(f).replace("/", "\\")
                low = path.lower()
                if low.startswith(folder) and low[len(folder):] in produced:
                    f.text = produced[low[len(folder):]]
            elif _low(f) == "component" and recipe.get("component"):
                f.text = recipe["component"]
        _emit(a, 0, out)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------
# Drawing (a small rasteriser: orthographic, textured, one light)


class Mesh:
    def __init__(self, mesh, texture):
        self.m, self.tex = mesh, texture

    def place(self, skel, pose_exact):
        m = self.m
        return gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"],
                               m["skin_names"], skel, pose_exact)


class Figure:
    """A model to draw: its meshes, skeleton and textures."""

    def __init__(self, game, rel):
        data = game.granny(rel)
        read = gr2_mesh.read(data)
        self.skel = read["skeletons"][0]
        self.names = [b["name"] for b in self.skel["bones"]]
        self.meshes = []
        for mesh in read["meshes"]:
            tex = None
            ft = mesh["face_textures"]
            order = [int(i) for i in np.unique(ft) if i >= 0] + list(range(len(read["textures"])))
            for i in order:
                name = read["textures"][i]
                if name and "_b." not in name.lower() and not name.lower().endswith("_b.ddt"):
                    tex = game.texture(name)
                    if tex is not None:
                        break
            self.meshes.append(Mesh(mesh, tex))

    def items(self, pose, place=None, colour=(150, 120, 90)):
        exact = {n: pose[n.lower()] for n in self.names if n.lower() in pose}
        out = []
        for m in self.meshes:
            p = m.place(self.skel, exact)
            if place is not None:
                p = (np.c_[p, np.ones(len(p))] @ place.T)[:, :3]
            out.append((p, m.m["triangles"], m.m["uvs"], m.tex, colour))
        return out


def raster(canvas, zbuf, pts2, depth, tris, uvs, tex, shade, colour):
    h, w = zbuf.shape
    for t, tri in enumerate(tris):
        a, b, c = pts2[tri]
        x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])))), int(min(w - 1, math.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])))), int(min(h - 1, math.ceil(max(a[1], b[1], c[1]))))
        if x0 > x1 or y0 > y1:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any():
            continue
        z = l0 * depth[tri[0]] + l1 * depth[tri[1]] + l2 * depth[tri[2]]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        win = inside & (z < sub)
        if not win.any():
            continue
        sub[win] = z[win]
        if tex is not None and uvs is not None:
            uv = (l0[..., None] * uvs[tri[0]] + l1[..., None] * uvs[tri[1]] + l2[..., None] * uvs[tri[2]])
            th, tw = tex.shape[:2]
            tx = np.clip((np.mod(uv[..., 0], 1.0) * tw).astype(int), 0, tw - 1)
            ty = np.clip(((1.0 - np.mod(uv[..., 1], 1.0)) * th).astype(int), 0, th - 1)
            col = tex[ty, tx, :3].astype(np.float64)
        else:
            col = np.broadcast_to(np.array(colour, np.float64), xs.shape + (3,))
        canvas[y0:y1 + 1, x0:x1 + 1][win] = np.clip(col[win] * shade[t], 0, 255)


def draw(items, width=200, height=240, azimuth=-60.0, elevation=15.0, span=3.4, centre=(0.0, 1.0, 0.5),
         marks=None):
    """The items seen from `azimuth` (degrees about the vertical; file axes: y up, z the unit's
    front); `marks` [(point, colour)] drawn as small crosses over them."""
    az, el = math.radians(azimuth), math.radians(elevation)
    view = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    right = np.cross([0.0, 1.0, 0.0], view)
    right /= np.linalg.norm(right)
    up = np.cross(view, right)
    canvas = np.full((height, width, 3), 236.0)
    zbuf = np.full((height, width), np.inf)
    light = view * 0.6 + up * 0.5 + right * 0.2
    light /= np.linalg.norm(light)
    scale = height / span
    c = np.asarray(centre)
    # the ground: a line under the figure
    for pts, tris, uvs, tex, colour in items:
        d = pts - c
        sx = width / 2 + (d @ right) * scale
        sy = height / 2 - (d @ up) * scale
        depth = -(d @ view)
        n = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        shade = 0.55 + 0.45 * np.abs(n @ light)
        raster(canvas, zbuf, np.stack([sx, sy], 1), depth, tris, uvs, tex, shade, colour)
    for p, colour in marks or []:
        d = np.asarray(p, np.float64) - c
        x, y = int(round(width / 2 + (d @ right) * scale)), int(round(height / 2 - (d @ up) * scale))
        for k in range(-4, 5):
            for (u, v) in ((x + k, y), (x, y + k)):
                if 0 <= u < width and 0 <= v < height:
                    canvas[v, u] = colour
    return canvas.astype(np.uint8)


def save_png(path, rgb):
    import struct as st
    import zlib
    h, w = rgb.shape[:2]
    raw = b"".join(b"\0" + rgb[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(kind, data):
        return st.pack(">I", len(data)) + kind + data + st.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", st.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def label(img, text, colour=(255, 255, 255), band=(40, 40, 40)):
    import bitfont
    out = img.copy()
    out[-14:, :] = band
    bitfont.draw(out, text, 3, out.shape[0] - 11, colour)
    return out


# --------------------------------------------------------------------------------------------------
# The work


def load_recipe(spec):
    if spec in RECIPES:
        return dict(RECIPES[spec])
    with open(spec, encoding="utf-8") as f:
        r = json.load(f)
    base = dict(MACEHUALTIN)
    base.update(r)
    base.setdefault("name", os.path.splitext(os.path.basename(spec))[0])
    for key in ("target_model", "folder"):
        if not base.get(key):
            raise ValueError(f"the recipe {spec} has no {key}")
    return base


class Job:
    """One recipe: the source and target rigs, the clips, what was made."""

    def __init__(self, game, recipe):
        self.game, self.r = game, recipe
        src_root = gr2.load(game.granny(recipe["source_model"])).root()
        tgt_root = gr2.load(game.granny(recipe["target_model"])).root()
        self.src_name, self.tgt_name = model_name(src_root), model_name(tgt_root)
        self.src, self.tgt = Rig.of(src_root), Rig.of(tgt_root)
        self.rt = Retarget(self.src, self.tgt, bone_map=recipe.get("bone_map"), held=recipe.get("held", ()),
                           markers=recipe.get("markers", ()), root=recipe.get("root"),
                           root_scale=recipe.get("root_scale"))
        self.animfile = parse_animfile(game.anim_file(recipe["source_animfile"]))
        self.clips = anim_clips(self.animfile, recipe["clips_from"])
        self.made = {}             # clip lower -> (times, target worlds, source Animation)
        self.lines = []

    def clip_rel(self, clip):
        return self.r["clips_from"].rstrip("\\") + "\\" + clip

    def new_rel(self, clip):
        return self.r["folder"].rstrip("\\") + "\\" + self.r.get("prefix", "") + clip

    def run(self, out, only=None, fps=None):
        matched, tgt_only, src_only, root, scale = self.rt.report()
        self.lines += [f"recipe {self.r['name']}: {self.r['source_model']} ({self.src_name!r}) -> "
                       f"{self.r['target_model']} ({self.tgt_name!r})",
                       f"track group: {self.tgt_name!r} (the source's: {self.src_name!r})",
                       f"root {root!r}, its motion scaled by {scale:.4f}",
                       f"bones matched ({len(matched)}): {', '.join(matched)}",
                       f"target bones kept at rest ({len(tgt_only)}): {', '.join(tgt_only)}",
                       f"source bones dropped ({len(src_only)}): {', '.join(src_only)}", ""]
        produced = {}
        for clip in self.clips:
            if only and clip.lower() not in only:
                continue
            anim = Animation.load(self.game.granny(self.clip_rel(clip)))
            name = self.new_rel(clip)
            data, times, frames = self.rt.animation(anim, self.tgt_name, fps=fps or FPS,
                                                    name=name.rsplit("\\", 1)[-1])
            dst = os.path.join(out, "art", name + ".gr2")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            note = f"{clip}: {anim.duration:.3f} s, {len(times)} samples, group {anim.group_name!r} -> {self.tgt_name!r}"
            try:
                pre = precomp.Precomp.parse(self.game.raw(self.clip_rel(clip), ".gr2.precomp"))
            except FileNotFoundError:
                pre = None
            if pre is not None and pre.blocks == 1:
                def pose_at(t, anim=anim):
                    return self.tgt.by_name(self.rt.worlds(self.rt.source_pose(anim, t)))
                newpre, moved, kept = retarget_precomp(pre, self.tgt, pose_at)
                with open(dst + ".precomp", "wb") as f:
                    f.write(newpre.encode())
                note += f"; tags moved {len(moved)}, kept {', '.join(kept) or '-'}"
            else:
                note += "; no tag file" if pre is None else f"; tag file of {pre.blocks} blocks not copied"
            self.lines.append(note)
            produced[clip.lower()] = name
            self.made[clip.lower()] = (times, frames, anim)
        with open(os.path.join(out, f"{self.r['name']}-anims.xml"), "w", encoding="utf-8") as f:
            f.write(anim_blocks(self.animfile, self.r, produced))
        with open(os.path.join(out, f"{self.r['name']}-report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")
        return produced


class Preview:
    """The source model and each recipe's target drawn at chosen moments, with the sling."""

    def __init__(self, game, jobs):
        self.game, self.jobs = game, jobs
        r = jobs[0].r
        self.src_fig = Figure(game, r["source_model"])
        self.tgt_figs = [Figure(game, j.r["target_model"]) for j in jobs]
        self.attach = []
        for spec in r.get("draw_attach", []):
            try:
                fig = Figure(game, spec["model"])
                root = gr2.load(game.granny(spec["model"])).root()
                self.attach.append((spec, fig, Rig.of(root)))
            except (FileNotFoundError, gr2.Gr2Error):
                continue
        self._attach_anims = {}

    def attach_items(self, clip, t, pose):
        out = []
        for spec, fig, rig in self.attach:
            key = (spec["clips_from"], clip.lower())
            if key not in self._attach_anims:
                try:
                    self._attach_anims[key] = Animation.load(
                        self.game.granny(spec["clips_from"].rstrip("\\") + "\\" + clip))
                except (FileNotFoundError, gr2.Gr2Error):
                    self._attach_anims[key] = None
            anim = self._attach_anims[key]
            apose = rig.by_name(rig.pose(anim, t) if anim is not None else rig.rest_worlds())
            on = pose.get(spec["tobone"].lower())
            frm = apose.get(spec["frombone"].lower())
            if on is None or frm is None:
                continue
            out += fig.items(apose, place=on @ np.linalg.inv(frm), colour=(90, 70, 40))
        return out

    def anim_names(self, clip):
        """The <anim> names of the source anim file that play `clip`."""
        job0 = self.jobs[0]
        want = (job0.r["clips_from"].rstrip("\\") + "\\" + clip).lower()
        out = []
        for anim in job0.animfile:
            if _low(anim) == "anim" and any(_low(f) == "file" and _head(f).replace("/", "\\").lower() == want
                                            for f in anim.iter()):
                out.append(_head(anim))
        return out

    def tiles(self, clip, t, w=180, h=230, marks=None):
        """[source tile, target tiles...] at time t of `clip`."""
        job0 = self.jobs[0]
        times, frames, anim = job0.made[clip.lower()]
        spose = job0.src.by_name(job0.src.pose(anim, t))
        out = [draw(self.src_fig.items(spose) + self.attach_items(clip, t, spose), w, h, marks=marks)]
        for job, fig in zip(self.jobs, self.tgt_figs):
            tpose = job.tgt.by_name(job.rt.worlds(job.rt.source_pose(anim, t)))
            out.append(draw(fig.items(tpose) + self.attach_items(clip, t, tpose), w, h, marks=marks))
        return out

    def today(self, w=180, h=230):
        """What the game shows now: the source playing its idle, each target in its bind pose."""
        job0 = self.jobs[0]
        clip = next((c for c in job0.made if c.startswith("volley_idle")), next(iter(job0.made)))
        _times, _frames, anim = job0.made[clip]
        spose = job0.src.by_name(job0.src.pose(anim, 0.0))
        out = [label(draw(self.src_fig.items(spose) + self.attach_items(clip, 0.0, spose), w, h),
                     "MACEHUALTIN NOW")]
        for job, fig in zip(self.jobs, self.tgt_figs):
            rest = job.tgt.by_name(job.tgt.rest_worlds())
            out.append(label(draw(fig.items(rest) + self.attach_items(clip, 0.0, rest), w, h),
                             f"{job.r['name'].upper()} NOW", band=(150, 30, 30)))
        return out

    def sheet(self, clips, path, frames=4, w=180, h=230):
        import bitfont
        names = ["MACEHUALTIN (ORIGINAL)"] + [f"{j.r['name'].upper()} (RETARGETED)" for j in self.jobs]
        per = len(names)
        gap = 6
        cell_w = per * w + gap
        rows = []
        today = self.today(w, h)
        row = np.full((h, cell_w * frames, 3), 255, np.uint8)
        x = 0
        for tile in today:
            row[:, x:x + w] = tile
            x += w
        txt = np.full((h, cell_w * frames - x, 3), 255, np.uint8)
        for k, line in enumerate(["TODAY IN GAME: THE CLIPS FIND NO TRACK GROUP NAMED",
                                  "AFTER THESE MODELS (BIP01), SO THEY STAND IN THEIR",
                                  "BIND POSE. BELOW: EACH CLIP ON THE MACEHUALTIN AND",
                                  "RETARGETED ON EACH MODEL, THE SLING ON PROP1."]):
            bitfont.draw(txt, line, 10, 20 + 22 * k, (30, 30, 30), scale=2)
        row[:, x:] = txt
        rows.append(row)
        for clip in clips:
            low = clip.lower()
            if low not in self.jobs[0].made:
                continue
            times, _f, anim = self.jobs[0].made[low]
            ts = np.linspace(0.0, anim.duration, frames + 1)[:-1] if "death" not in low and "havoc" not in low \
                else np.linspace(0.0, anim.duration, frames)
            band = np.full((18, cell_w * frames, 3), (70, 90, 120), np.uint8)
            uses = self.anim_names(clip)
            bitfont.draw(band, f"{clip.upper()} ({anim.duration:.2f} S)" + (f"  PLAYED AS: {', '.join(uses).upper()}"
                                                                            if uses else ""),
                         6, 5, (255, 255, 255))
            row = np.full((h, cell_w * frames, 3), 255, np.uint8)
            for f, t in enumerate(ts):
                tiles = self.tiles(clip, float(t))
                for k, tile in enumerate(tiles):
                    tag = f"{t:.2f}S {names[k].split(' ')[0]}"
                    row[:, f * cell_w + k * w:f * cell_w + (k + 1) * w] = label(tile, tag)
            rows.append(np.concatenate([band, row]))
        body = np.concatenate([np.concatenate([r, np.full((gap, r.shape[1], 3), 255, np.uint8)]) for r in rows])
        head = np.full((34, body.shape[1], 3), 40, np.uint8)
        bitfont.draw(head, "SLINGER ANIMATIONS ON OTHER MODELS. EACH MOMENT: " + " / ".join(names), 8, 10,
                     (255, 255, 255), scale=2)
        save_png(path, np.concatenate([head, body]))

    def clip_sheet(self, clip, path, frames=12, w=150, h=200):
        low = clip.lower()
        _t, _f, anim = self.jobs[0].made[low]
        ts = np.linspace(0.0, anim.duration, frames)
        rows = []
        for t in ts:
            tiles = self.tiles(clip, float(t), w, h)
            rows.append(np.concatenate([label(tiles[0], f"{t:.2f}S")] + tiles[1:], axis=1))
        cols = 3
        rows += [np.full_like(rows[0], 255)] * (-len(rows) % cols)
        grid = np.concatenate([np.concatenate(rows[i:i + cols], axis=1) for i in range(0, len(rows), cols)])
        import bitfont
        head = np.full((20, grid.shape[1], 3), 40, np.uint8)
        models = ["MACEHUALTIN"] + [j.r["name"].upper() for j in self.jobs]
        bitfont.draw(head, f"{clip.upper()} ({anim.duration:.2f} S). EACH MOMENT: " + " / ".join(models), 6, 6,
                     (255, 255, 255))
        save_png(path, np.concatenate([head, grid]))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--recipe", action="append",
                    help=f"a recipe name ({', '.join(RECIPES)}) or a JSON file; repeat for several targets")
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--only", help="clip names, comma separated")
    ap.add_argument("--preview", help="the review sheet (PNG)")
    ap.add_argument("--preview-clips", default=",".join(DEFAULT_PREVIEW))
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--fps", type=float, default=FPS, help="samples a second of the written clips")
    a = ap.parse_args(argv)
    try:
        refuse_steam(a.out)
    except RefusedPath as e:
        print(f"refused: {e}")
        return 2
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, "_work")
    os.makedirs(work, exist_ok=True)
    game = Game(a.game, a.granny_helper, work)
    recipes = [load_recipe(r) for r in (a.recipe or ["skirmisher"])]
    only = {c.strip().lower() for c in a.only.split(",")} if a.only else None
    if a.preview:
        only = None if only is None else only | {c.strip().lower() for c in a.preview_clips.split(",")}
    jobs = []
    for r in recipes:
        job = Job(game, r)
        made = job.run(a.out, only, a.fps)
        print(f"{r['name']}: {len(made)} clips -> art\\{r['folder']} (track group {job.tgt_name!r}); "
              f"{r['name']}-anims.xml, {r['name']}-report.txt")
        jobs.append(job)
    if a.preview or a.sheets:
        pv = Preview(game, jobs)
        if a.preview:
            pv.sheet([c.strip() for c in a.preview_clips.split(",") if c.strip()], a.preview)
            print("preview:", a.preview)
        if a.sheets:
            for clip in jobs[0].clips:
                if clip.lower() in jobs[0].made:
                    pv.clip_sheet(clip, os.path.join(a.out, "sheets", clip + ".png"))
            print("sheets:", os.path.join(a.out, "sheets"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
