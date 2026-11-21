# SPDX-License-Identifier: GPL-3.0-or-later
"""Dismount and mount animations for a cavalry unit whose rider is an attachment of its horse (the
horse is the unit's model, the rider hangs on a horse bone with syncanims), and the rider's
animations on foot beside the horse, from the game's own infantry animations.

    venv\\Scripts\\python -I tools/make_dismount.py --game <game copy> --out <folder>
        [--recipe <recipe.json>] [--granny-helper <exe>] [--sheets] [--clips] [--only NAME,...]

What it writes below --out:
- `art\\<recipe "folder">\\<name>.gr2`: one rider animation per entry of the recipe: the
  `foot` entries (an infantry animation on the rider, standing on the ground beside the horse,
  turned and timed to the horse animation the anim file pairs with it) and the two transitions
  `dismount` and `mount` (from the rider's seat to that place and back);
- `anims-horse.xml`, `anims-rider.xml`: the `<anim>` blocks to add to the horse's and the rider's
  anim files (the horse's carry the tags; the rider follows through syncanims);
- with --sheets, `sheets\\<name>.png`: each animation drawn frame by frame with the horse, from the
  side the rider gets off; with --clips, `sheets\\<name>.mp4` (needs ffmpeg).

How (aoe3game/gr2_anim.py): the infantry animation is posed on the infantry skeleton of the recipe
(`foot_model`), its world frames are put on the rider's bones of the same name (the rider's rig
differs in hierarchy: the bones are not copied, their places are), moved to the ground beside the
horse (`side`, `forward`), and then expressed in the frame of the horse bone the rider hangs on,
at each moment of the horse animation played with it, so the rider stands still on the ground
while the horse breathes or walks. The transitions are made from key poses: the rider's seat
(`mounted` animation), rising in the stirrups, the right leg over the croup, hanging on the
saddle's side, and the standing pose; the root follows a smooth path between them, every bone is
turned by slerp, and the weapon stays in the right hand.

Compressed game models and animations are expanded by the game's own Granny runtime through the
32-bit helper of recompress_models.py (`--granny-helper`, default tools\\granny_recompress.exe;
`python -I tools/recompress_models.py --build-helper` makes it); nothing of the game is stored.
Refuses a Steam folder as output.
"""
import argparse
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
from aoe3game import ddt, gr2, gr2_mesh, gr2_skin  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import (Animation, Rig, axis_quat, frame, matrix_quat, slerp, split,  # noqa: E402
                               animation_file)
from aoe3game.gr2_skin import quat_matrix  # noqa: E402

LIB = "animation_library\\"
DEFAULT_RECIPE = {
    "folder": "WoL\\units\\cavalry\\chasseur_a_cheval\\dismount",
    "prefix": "chasseur_",
    "rider_model": "WoL\\units\\cavalry\\chasseur_a_cheval\\chasseur_a_cheval_1age",
    "horse_model": "WoL\\units\\cavalry\\chasseur_a_cheval\\chasseur_a_cheval_horse",
    "foot_model": "WoL\\units\\infantry_ranged\\skirmisher\\skirmisher_age2",
    "weapon": {"model": "units\\natives\\lakota\\rifle_rider\\rifle_rider_1_gun",
               "frombone": "Bip 01 Master", "tobone": "Bip01 Prop1"},
    "hat": {"model": "WoL\\units\\cavalry\\chasseur_a_cheval\\hat_1", "frombone": "bone_hat",
            "tobone": "Bip01 Head"},
    "horse_bone": "bone attachpoint",
    "mounted": LIB + "natives\\apache_cavalry\\idle1",
    "side": -0.85,
    "forward": -0.15,
    "foot": [
        {"name": "idle", "rider": LIB + "range\\volley\\volley_standing_idle",
         "horse": LIB + "cavalry\\horse_idle_A"},
        {"name": "bored", "rider": LIB + "range\\bored_rifleman_A",
         "horse": LIB + "cavalry\\horse_idle_I"},
        {"name": "walk", "rider": LIB + "range\\march_rifleman",
         "horse": LIB + "cavalry\\horse_walk_A"},
        {"name": "jog", "rider": LIB + "range\\jog_rifleman_A",
         "horse": LIB + "cavalry\\horse_trot"},
        {"name": "run", "rider": LIB + "range\\run_rifleman_A",
         "horse": LIB + "cavalry\\horse_jog"},
        {"name": "attack", "rider": LIB + "range\\volley\\volley_standing_fire",
         "horse": LIB + "cavalry\\horse_idle_A", "time": "rider", "launch": True,
         "tags": [{"type": "Attack", "at": 0.46},
                  {"type": "SpecificSoundSet", "checkvisible": "1", "set": "RifleShot", "at": 0.46},
                  {"type": "Particles", "particlename": "musketshot", "at": 0.46}]},
        {"name": "reload", "rider": LIB + "range\\volley\\volley_standing_reload",
         "horse": LIB + "cavalry\\horse_idle_A", "time": "rider"},
        {"name": "melee", "rider": LIB + "range\\melee_rifleman_standing_A",
         "horse": LIB + "cavalry\\horse_idle_A", "time": "rider",
         "tags": [{"type": "Attack", "at": 0.51},
                  {"type": "SpecificSoundSet", "checkvisible": "1", "set": "Swoosh", "at": 0.45}]},
        {"name": "death", "rider": LIB + "range\\death_standing_rifleman_A",
         "horse": LIB + "cavalry\\horse_deathA",
         "tags": [{"type": "SpecificSoundSet", "checkvisible": "1", "set": "RagdollImpact", "at": 0.51}]},
    ],
    "dismount": {"name": "dismount", "length": 2.0, "horse": LIB + "cavalry\\horse_idle_A"},
    "mount": {"name": "mount", "length": 2.0, "horse": LIB + "cavalry\\horse_idle_A"},
}
FPS = 30


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
        if not rel.endswith(ext):
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
            gr2.read_container(data)
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

    def texture(self, stored):
        """RGBA of a texture a model names (its path after `art\\`), or None."""
        low = stored.lower().replace("/", "\\")
        at = low.find("\\art\\")
        rel = low[at + 5:] if at >= 0 else os.path.basename(low)
        rel = os.path.splitext(rel)[0]
        try:
            return ddt.decode(self.raw(rel, ".ddt"))
        except (FileNotFoundError, ValueError, KeyError):
            return None


# --------------------------------------------------------------------------------------------------
# Poses


def lower(d):
    return {k.lower(): v for k, v in d.items()}


def ground_pose(rig, anim, t, place):
    """World frames (by lower-case name) of `rig` at time t of `anim`, moved by `place`."""
    return {k: place @ w for k, w in rig.by_name(rig.pose(anim, t)).items()}


def put_on(rider, src, root_from="bip01"):
    """The infantry pose `src` (world frames by name) as the rider's: each rider bone on the frame
    of the bone of the same name; the rider's root on the infantry's root."""
    out = dict(src)
    root = rider.names[0].lower()
    if root not in out and root_from in src:
        out[root] = src[root_from]
    return {k: v for k, v in out.items() if rider.has(k)}


def to_track_frames(rider, worlds_by_t, attach_by_t):
    """Rider locals per frame: each pose (ground space) seen from the horse bone at that moment."""
    frames = []
    for pose, attach in zip(worlds_by_t, attach_by_t):
        inv = np.linalg.inv(attach)
        local_world = {k: inv @ w for k, w in pose.items()}
        frames.append(rider.localise(local_world))
    return frames


def tracks_of(rider, frames, times, bones=None):
    out = []
    for i, name in enumerate(rider.names):
        if bones is not None and name.lower() not in bones:
            continue
        pos = np.array([f[i][0] for f in frames])
        quat = np.array([f[i][1] for f in frames])
        out.append((name, times, pos, quat))
    return out


def rotate_about(pose, rig, bone, pivot_bone, axis, degrees):
    """`pose` with `bone` and everything below it turned about the world axis through the
    position of `pivot_bone` (both lower-case names)."""
    r = np.eye(4)
    r[:3, :3] = quat_matrix(axis_quat(axis, degrees))
    c = pose[pivot_bone][:3, 3]
    t1, t2 = np.eye(4), np.eye(4)
    t1[:3, 3], t2[:3, 3] = -c, c
    m = t2 @ r @ t1
    below = descendants(rig, bone)
    return {k: (m @ w if k in below else w) for k, w in pose.items()}


def descendants(rig, bone):
    idx = rig.index[bone]
    out = {bone}
    for i, name in enumerate(rig.names):
        j = i
        while j >= 0:
            if j == idx:
                out.add(name.lower())
                break
            j = rig.parents[j]
    return out


def translate(pose, rig, bone, offset):
    m = np.eye(4)
    m[:3, 3] = offset
    below = descendants(rig, bone)
    return {k: (m @ w if k in below else w) for k, w in pose.items()}


def blend(rig, a, b, u):
    """Bone by bone between two poses (world frames): every local frame slerped, the root's
    position interpolated; the result as world frames."""
    la, lb = rig.localise(a), rig.localise(b)
    locs = []
    for (pa, qa), (pb, qb) in zip(la, lb):
        locs.append((pa + u * (pb - pa), slerp(qa, qb, u)))
    return rig.by_name(rig.worlds(locs))


def loop_length(horse, rider, most=6, close=0.04):
    """(length, rider cycles): a whole number of horse cycles holding a whole number of rider
    cycles to within `close` (the rider's animation is stretched by that much), the fewest."""
    best = None
    for h in range(1, most + 1):
        r = max(1, round(h * horse / rider))
        err = abs(h * horse - r * rider) / (r * rider)
        if best is None or err < best[0] - 1e-9:
            best = (err, h * horse, r)
        if err <= close:
            break
    return best[1], best[2]


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


# --------------------------------------------------------------------------------------------------
# The maker


class Maker:
    def __init__(self, game, recipe):
        self.game, self.r = game, recipe
        g = game.granny
        self.rider_root = gr2.load(g(recipe["rider_model"])).root()
        self.horse_root = gr2.load(g(recipe["horse_model"])).root()
        self.rider = Rig.of(self.rider_root)
        self.horse = Rig.of(self.horse_root)
        self.foot = Rig.of(gr2.load(g(recipe["foot_model"])).root())
        self.anims = {}
        self.hb = recipe["horse_bone"].lower()
        self._muzzle = None
        self.place = np.eye(4)
        self.place[:3, 3] = (recipe["side"], 0.0, recipe["forward"])

    def anim(self, rel):
        if rel not in self.anims:
            self.anims[rel] = Animation.load(self.game.granny(rel))
        return self.anims[rel]

    def horse_time(self, horse_anim, t):
        """The horse animation's own time at t: looped, except a death, which holds its end."""
        h = self.anim(horse_anim)
        if not h.duration:
            return 0.0
        if "death" in horse_anim.lower():
            return min(t, h.duration)
        if abs(t - h.duration) < 1e-6:
            return h.duration
        return math.fmod(t, h.duration)

    def horse_attach(self, horse_anim, t):
        return self.horse_pose(horse_anim, t)[self.hb]

    def horse_pose(self, horse_anim, t):
        h = self.anim(horse_anim)
        return self.horse.by_name(self.horse.pose(h, self.horse_time(horse_anim, t)))

    def muzzle(self, rider_pose):
        """The weapon's far end (the muzzle) in ground space, or None without a weapon."""
        if self._muzzle is None:
            spec = self.r.get("weapon")
            read = gr2_mesh.read(self.game.granny(spec["model"]))
            skel = read["skeletons"][0]
            fb = {b["name"].lower(): b for b in skel["bones"]}.get(spec["frombone"].lower())
            base = fb["world"] if fb is not None else np.eye(4)
            pts = np.concatenate([m["file_positions"] for m in read["meshes"]]).astype(np.float64)
            local = (np.c_[pts, np.ones(len(pts))] @ np.linalg.inv(base).T)[:, :3]
            self._muzzle = local[np.argmax(np.linalg.norm(local, axis=1))]
        on = rider_pose[self.r["weapon"]["tobone"].lower()]
        return (on @ np.r_[self._muzzle, 1.0])[:3]

    def horse_clip(self, entry, dur, times, poses):
        """Bytes of the horse animation of `entry` played over [0, dur], with the horse's launch
        bone on the rider's muzzle when the entry says `launch`."""
        h = self.anim(entry["horse"])
        frames = []
        lp = self.r.get("launch_bone", "bone_launchpoint").lower()
        for t, rider_pose in zip(times, poses):
            w = self.horse_pose(entry["horse"], t)
            if entry.get("launch") and lp in w:
                m = w[lp].copy()
                m[:3, 3] = self.muzzle(rider_pose)
                w = dict(w)
                w[lp] = m
            frames.append(self.horse.localise(w))
        name = self.r["prefix"] + "horse_" + entry["name"]
        return animation_file(name, dur, h.group_name, tracks_of(self.horse, frames, times),
                              basis=self.horse.basis, accumulation=h.accumulation, source=name)

    def standing(self, rel, t):
        """The infantry pose at time t, on the ground beside the horse, as the rider's bones."""
        return put_on(self.rider, ground_pose(self.foot, self.anim(rel), t, self.place))

    def mounted(self, t, horse_anim, ht):
        """The rider's seat at time t of the mounted animation, on the horse at time ht."""
        a = self.anim(self.r["mounted"])
        seat = self.rider.by_name(self.rider.pose(a, min(t, a.duration)))
        attach = self.horse_attach(horse_anim, ht)
        return {k: attach @ w for k, w in seat.items()}

    # -- the animations --

    def foot_anim(self, entry):
        """(duration, times, ground poses, attach frames) of a foot entry: the infantry animation
        played a whole number of times over the horse animation's length (a death once)."""
        ia, ha = self.anim(entry["rider"]), self.anim(entry["horse"])
        hd = ha.duration or ia.duration
        if entry.get("time") == "rider" or hd <= 0:
            dur, cycles = ia.duration, 1               # a horse clip of that length goes with it
        elif entry["name"] == "death":
            dur, cycles = max(ia.duration, hd), 1
        else:
            dur, cycles = loop_length(hd, ia.duration)
        n = max(2, int(round(dur * FPS)) + 1)
        times = np.linspace(0.0, dur, n)
        poses, attach = [], []
        for t in times:
            u = (t / dur) * cycles * ia.duration
            if entry["name"] != "death":
                u = math.fmod(u, ia.duration) if u < cycles * ia.duration - 1e-6 else ia.duration
            poses.append(self.standing(entry["rider"], min(u, ia.duration)))
            attach.append(self.horse_attach(entry["horse"], t))
        return dur, times, poses, attach

    def key_poses(self, horse_anim):
        """The dismount's key poses in ground space: (time share, pose)."""
        rig = self.rider
        root = rig.names[0].lower()
        m0 = self.mounted(0.0, horse_anim, 0.0)
        s = self.standing(self.r["foot"][0]["rider"], 0.0)
        side = math.copysign(1.0, self.r["side"])          # -1: the rider's left (the horse's left)
        seat = self.horse_attach(horse_anim, 0.0)[:3, 3]
        k = self.r.get("keys", {})
        # file axes: x the unit's right (side < 0 is its left), y up, z forward
        # 1. up in the left stirrup, leaning forward over the neck
        k1 = translate(m0, rig, root, (0.06 * side, k.get("rise", 0.22), 0.04))
        k1 = rotate_about(k1, rig, "bip01 spine", "bip01 spine", (1, 0, 0), 18)
        # 2. the right leg swung back and up over the croup, the body over the left stirrup
        k2 = translate(m0, rig, root, (0.16 * side, k.get("rise", 0.22) + 0.04, 0.02))
        k2 = rotate_about(k2, rig, "bip01 spine", "bip01 spine", (1, 0, 0), 32)
        k2 = rotate_about(k2, rig, "bip01 r thigh", "bip01 r thigh", (1, 0, 0), k.get("swing", 105))
        k2 = rotate_about(k2, rig, "bip01 r thigh", "bip01 r thigh", (0, 0, 1), -20 * side)
        # 3. both legs on the left side, facing the horse, the belly against the saddle
        st = rotate_about(s, rig, root, root, (0, 1, 0), -90 * side)
        cur = st[root][:3, 3]
        k3 = translate(st, rig, root, (seat[0] + side * 0.42 - cur[0], seat[1] - 0.55 - cur[1],
                                       seat[2] - 0.05 - cur[2]))
        for arm in ("bip01 l upperarm", "bip01 r upperarm"):
            k3 = rotate_about(k3, rig, arm, arm, (0, 0, 1), -k.get("arms_on_saddle", 60) * side)
        # 4. slid down the side, the feet just above the ground, the hands still on the saddle
        cur = st[root][:3, 3]
        k4 = translate(st, rig, root, (seat[0] + side * 0.62 - cur[0], 0.06, seat[2] - 0.05 - cur[2]))
        for arm in ("bip01 l upperarm", "bip01 r upperarm"):
            k4 = rotate_about(k4, rig, arm, arm, (0, 0, 1), -k.get("arms_reaching", 75) * side)
        return [(0.0, m0), (0.18, k1), (0.38, k2), (0.56, k3), (0.76, k4), (1.0, s)]

    def transition(self, entry, reverse):
        dur = float(entry["length"])
        horse_anim = entry["horse"]
        keys = self.key_poses(horse_anim)
        n = int(round(dur * FPS)) + 1
        times = np.linspace(0.0, dur, n)
        poses, attach = [], []
        hand, prop = "bip01 r hand", self.r["weapon"]["tobone"].lower()
        for t in times:
            u = t / dur
            if reverse:
                u = 1.0 - u
            k = max(i for i, (share, _p) in enumerate(keys) if share <= u + 1e-9)
            k = min(k, len(keys) - 2)
            (s0, p0), (s1, p1) = keys[k], keys[k + 1]
            w = smooth((u - s0) / (s1 - s0))
            # the seat moves with the horse in the first and last key (keyed at time 0)
            if k == 0:
                p0 = self.mounted(0.0, horse_anim, t)
            pose = blend(self.rider, p0, p1, w)
            # the weapon stays in the right hand: its frame relative to the hand, slerped
            ra = np.linalg.inv(p0[hand]) @ p0[prop]
            rb = np.linalg.inv(p1[hand]) @ p1[prop]
            pa, qa = split(ra)
            pb, qb = split(rb)
            pose[prop] = pose[hand] @ frame(pa + w * (pb - pa), slerp(qa, qb, w))
            poses.append(pose)
            attach.append(self.horse_attach(horse_anim, t))
        return dur, times, poses, attach

    def build(self, only=None):
        """{name: (bytes, duration, times, poses, horse anim, horse clip bytes or None)}."""
        out = {}
        jobs = [(e["name"], e, None) for e in self.r["foot"]]
        jobs += [(self.r["dismount"]["name"], self.r["dismount"], False),
                 (self.r["mount"]["name"], self.r["mount"], True)]
        for name, entry, reverse in jobs:
            if only and name not in only:
                continue
            if reverse is None:
                dur, times, poses, attach = self.foot_anim(entry)
            else:
                dur, times, poses, attach = self.transition(entry, reverse)
            frames = to_track_frames(self.rider, poses, attach)
            full = self.r["prefix"] + name
            data = animation_file(full, dur, self.rider.names[0], tracks_of(self.rider, frames, times),
                                  basis=self.rider.basis, source=full)
            hd = self.anim(entry["horse"]).duration
            clip = None
            if abs(dur - hd) > 1e-3 or entry.get("launch"):
                clip = self.horse_clip(entry, dur, times, poses)
            out[name] = (data, dur, times, poses, entry["horse"], clip)
        return out


# --------------------------------------------------------------------------------------------------
# Drawing (a small rasteriser: orthographic, textured, one light)


class Mesh:
    def __init__(self, mesh, texture):
        self.m, self.tex = mesh, texture

    def place(self, rig_skel, pose_exact):
        m = self.m
        return gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"],
                               m["skin_names"], rig_skel, pose_exact)


def model_meshes(game, root, data):
    read = gr2_mesh.read(data)
    skel = read["skeletons"][0]
    out = []
    for mesh in read["meshes"]:
        tex = None
        ft = mesh["face_textures"]
        idx = [int(i) for i in np.unique(ft) if i >= 0]
        for i in idx:
            name = read["textures"][i]
            if name and not name.lower().endswith("_b.ddt"):
                tex = game.texture(name)
                if tex is not None:
                    break
        if tex is None:
            for name in read["textures"]:
                if name and "_b." not in name.lower():
                    tex = game.texture(name)
                    if tex is not None:
                        break
        out.append(Mesh(mesh, tex))
    return out, skel


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


class Scene:
    def __init__(self, game, maker, recipe):
        g = game.granny
        self.maker = maker
        self.rider_meshes, self.rider_skel = model_meshes(game, None, g(recipe["rider_model"]))
        self.horse_meshes, self.horse_skel = model_meshes(game, None, g(recipe["horse_model"]))
        self.parts = []
        for key in ("weapon", "hat"):
            spec = recipe.get(key)
            if not spec:
                continue
            try:
                meshes, skel = model_meshes(game, None, g(spec["model"]))
            except (FileNotFoundError, gr2.Gr2Error):
                continue
            names = {b["name"].lower(): b for b in skel["bones"]}
            fb = names.get(spec["frombone"].lower())
            frm = fb["world"] if fb is not None else np.eye(4)
            self.parts.append((meshes, skel, np.linalg.inv(frm), spec["tobone"].lower()))

    def triangles(self, rider_pose, horse_pose, attach):
        """[(points N x 3 in the horse's model space, triangles, uvs, texture, colour)]."""
        rider_exact = {n: rider_pose[n.lower()] for n in self.maker.rider.names if n.lower() in rider_pose}
        horse_exact = {n: horse_pose[n.lower()] for n in self.maker.horse.names if n.lower() in horse_pose}
        out = []
        for m in self.horse_meshes:
            out.append((m.place(self.horse_skel, horse_exact), m.m["triangles"], m.m["uvs"], m.tex, (120, 80, 50)))
        for m in self.rider_meshes:
            p = m.place(self.rider_skel, rider_exact)
            out.append((p, m.m["triangles"], m.m["uvs"], m.tex, (60, 80, 160)))
        for meshes, skel, inv_from, tobone in self.parts:
            on = rider_pose.get(tobone)
            if on is None:
                continue
            place = on @ inv_from
            for m in meshes:
                p = m.place(skel, None)
                h = np.c_[p, np.ones(len(p))] @ place.T
                out.append((h[:, :3], m.m["triangles"], m.m["uvs"], m.tex, (40, 40, 40)))
        return out

    def draw(self, items, size=360, azimuth=-60.0, elevation=20.0, span=3.8, centre=(-0.3, 1.25, 0.0)):
        az, el = math.radians(azimuth), math.radians(elevation)
        # file axes: x left/right (x negative = the unit's left), y up, z forward
        view = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
        right = np.cross([0.0, 1.0, 0.0], view)
        right /= np.linalg.norm(right)
        up = np.cross(view, right)
        canvas = np.full((size, size, 3), 236.0)
        zbuf = np.full((size, size), np.inf)
        light = view * 0.6 + up * 0.5 + right * 0.2
        light /= np.linalg.norm(light)
        scale = size / span
        c = np.asarray(centre)
        for pts, tris, uvs, tex, colour in items:
            d = pts - c
            sx = size / 2 + (d @ right) * scale
            sy = size / 2 - (d @ up) * scale
            depth = -(d @ view)
            n = np.cross(pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]])
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            shade = 0.55 + 0.45 * np.abs(n @ light)
            raster(canvas, zbuf, np.stack([sx, sy], 1), depth, tris, uvs, tex, shade, colour)
        # the ground line under the horse
        return canvas.astype(np.uint8)


def save_png(path, rgb):
    import zlib
    import struct as st
    h, w = rgb.shape[:2]
    raw = b"".join(b"\0" + rgb[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(kind, data):
        return st.pack(">I", len(data)) + kind + data + st.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", st.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def label(img, text):
    """A dark band with the frame's text (5 x 7 dots), at the bottom of `img`."""
    import bitfont  # tools/bitfont.py
    out = img.copy()
    out[-16:, :] = (40, 40, 40)
    bitfont.draw(out, text, 4, out.shape[0] - 12, (255, 255, 255))
    return out


def sheet(frames, cols):
    h, w = frames[0].shape[:2]
    rows = (len(frames) + cols - 1) // cols
    out = np.full((rows * h, cols * w, 3), 255, np.uint8)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        out[r * h:(r + 1) * h, c * w:(c + 1) * w] = f
    return out


def ffmpeg():
    for cand in (os.environ.get("UHC_FFMPEG"), shutil.which("ffmpeg"), r"C:\Tools\ffmpeg\ffmpeg.exe"):
        if cand and os.path.exists(cand):
            return cand
    return None


def render(scene, maker, name, built, out_dir, clips, views):
    data, dur, times, poses, horse_anim, _clip = built
    picks = np.linspace(0, len(times) - 1, 12).round().astype(int)
    tiles = []
    for azim in views:
        for i in picks:
            hp = maker.horse_pose(horse_anim, times[i])
            img = scene.draw(scene.triangles(poses[i], hp, None), azimuth=azim)
            tiles.append(label(img, f"{name} {times[i]:.2f}s"))
    save_png(os.path.join(out_dir, f"{name}.png"), sheet(tiles, 6))
    if clips and ffmpeg():
        tmp = tempfile.mkdtemp(prefix="dismount_")
        try:
            for k, t in enumerate(times):
                hp = maker.horse_pose(horse_anim, t)
                img = scene.draw(scene.triangles(poses[k], hp, None), size=480, azimuth=views[0])
                save_png(os.path.join(tmp, f"f{k:04d}.png"), label(img, f"{name} {t:.2f}s"))
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                            os.path.join(tmp, "f%04d.png"), "-pix_fmt", "yuv420p", "-vf",
                            "scale=480:480", os.path.join(out_dir, f"{name}.mp4")], check=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------------------------------


ANIM_NAMES = {"dismount": "Dismount", "mount": "Mount"}


def anim_name(name):
    return ANIM_NAMES.get(name, "Dismounted_" + name.capitalize())


def _tag(t):
    attrs = "".join(f' {k}="{v}"' for k, v in t.items() if k not in ("type", "at"))
    return f'\t\t\t<tag type="{t["type"]}"{attrs}>{float(t["at"]):.2f}</tag>\n'


def anim_blocks(recipe, built):
    """The <anim> blocks for the two anim files: the horse's (its own animation or the clip made
    for it, with the entry's tags: the base model's animation carries them) and the rider's (the
    new files, played through syncanims)."""
    folder, prefix = recipe["folder"], recipe["prefix"]
    entries = {e["name"]: e for e in recipe["foot"]}
    entries.update({recipe["dismount"]["name"]: recipe["dismount"], recipe["mount"]["name"]: recipe["mount"]})
    horse, rider = [], []
    for name, (_d, _dur, _t, _p, horse_anim, clip) in built.items():
        tags = "".join(_tag(t) for t in entries.get(name, {}).get("tags", []))
        hfile = f"{folder}\\{prefix}horse_{name}" if clip is not None else horse_anim
        horse.append(f"\t<anim>{anim_name(name)}\n\t\t<assetreference type=\"GrannyAnim\">\n"
                     f"\t\t\t<file>{hfile}</file>\n{tags}\t\t</assetreference>\n"
                     f"\t\t<component>ModelComp</component>\n\t</anim>")
        rider.append(f"\t<anim>{anim_name(name)}\n\t\t<assetreference type=\"GrannyAnim\">\n"
                     f"\t\t\t<file>{folder}\\{prefix}{name}</file>\n\t\t</assetreference>\n"
                     f"\t\t<component>ModelComp</component>\n\t</anim>")
    return "\n".join(horse) + "\n", "\n".join(rider) + "\n"

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--recipe")
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--clips", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--views", default="-70")
    ap.add_argument("--keys", action="store_true", help="draw the dismount's key poses only")
    args = ap.parse_args(argv)
    try:
        refuse_steam(args.out)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    recipe = copy.deepcopy(DEFAULT_RECIPE)
    if args.recipe:
        with open(args.recipe, encoding="utf-8") as f:
            recipe.update(json.load(f))
    work = tempfile.mkdtemp(prefix="dismount_work_")
    try:
        game = Game(args.game, args.granny_helper, work)
        maker = Maker(game, recipe)
        only = set(args.only.split(",")) if args.only else None
        built = maker.build(only)
        folder = os.path.join(args.out, "art", recipe["folder"])
        os.makedirs(folder, exist_ok=True)
        for name, b in built.items():
            with open(os.path.join(folder, recipe["prefix"] + name + ".gr2"), "wb") as f:
                f.write(b[0])
            print(f"{recipe['prefix']}{name}.gr2  {b[1]:.2f} s  {len(b[2])} frames  {len(b[0])} B")
            if b[5] is not None:
                with open(os.path.join(folder, recipe["prefix"] + "horse_" + name + ".gr2"), "wb") as f:
                    f.write(b[5])
                print(f"{recipe['prefix']}horse_{name}.gr2  {len(b[5])} B")
        horse_xml, rider_xml = anim_blocks(recipe, built)
        for fname, text in (("anims-horse.xml", horse_xml), ("anims-rider.xml", rider_xml)):
            with open(os.path.join(args.out, fname), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(text)
        if args.keys:
            scene = Scene(game, maker, recipe)
            keys = maker.key_poses(recipe["dismount"]["horse"])
            hp = maker.horse_pose(recipe["dismount"]["horse"], 0.0)
            tiles = [label(scene.draw(scene.triangles(p, hp, None), size=420, azimuth=float(v)),
                           f"key {share:.2f} view {v}") for v in args.views.split(",") for share, p in keys]
            os.makedirs(os.path.join(args.out, "sheets"), exist_ok=True)
            save_png(os.path.join(args.out, "sheets", "keys.png"), sheet(tiles, len(keys)))
        if args.sheets or args.clips:
            scene = Scene(game, maker, recipe)
            sheets = os.path.join(args.out, "sheets")
            os.makedirs(sheets, exist_ok=True)
            views = [float(v) for v in args.views.split(",")]
            for name, b in built.items():
                render(scene, maker, name, b, sheets, args.clips, views)
                print(f"sheets\\{name}.png")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
