# SPDX-License-Identifier: GPL-3.0-or-later
"""One model's animations put on another model's skeleton, with the tag file (`.gr2.precomp`) of
each animation moved with them. Pure Python with numpy; tools/retarget_anims.py uses it.

Why a model's animations play only on that model (**measured** in the game's code, age3y.exe of The
Asian Dynasties, 2026-11-23): the game starts an animation on a model only through
`GrannyFindTrackGroupForModel(animation, model name)` (its two calls, 0x426A5F and 0x4B6F1F, skip
the animation when it returns false). A Granny animation holds one track group per model it was
made for, named after that model (`Models[0].Name`, the name of the skeleton's root in the game's
files). The Aztec Macehualtin's model and its animations are named `bone_master` (a master bone
above the biped), every standard infantry model `Bip01`: on any of them the slinger's animations
find no track group, are not played, and the model stands in its bind pose.

How (`Retarget`): each target bone takes the world rotation of the source bone of the same name
(or of `bone_map`), as a change from the source's rest pose applied to the target's rest pose
(`W_t = W_s R_s^-1 R_t`), so two rigs whose bones point differently at rest still show the same
pose; its position comes from its parent and its own rest offset (the target keeps its bone
lengths). The biped's root (`Bip01`) is placed where the source's is, its motion scaled by the
ratio of the two roots' heights at rest. Three kinds of bones are copied instead of turned:
`markers` (the hit point bar) keep the source's world frame; `held` bones (the props a weapon
hangs on, `Bip01 Prop1`) keep the source's frame relative to their parent, so a weapon hung on
them sits in the hand as it did on the source; a target bone with no source bone keeps its rest
frame relative to its parent. Written: one track group named after the target model, in the
target's basis (`gr2_anim.animation_file`), on evenly sampled times (60 a second by
default in the tool: at 30 the fastest melee swing drifted by up to 0.14 of a frame entry).

The tag file (`retarget_precomp`): a tag that names a target bone (`HEAD` is `Bip01 Head`,
`R HAND` `Bip01 R Hand`, `L TOE` `Bip01 L Toe0`) takes that bone's sampled position; `MASTER`, a
tag of a bone the target lacks (the source's `LAUNCHPOINT`, where the projectile leaves) and
every rotation are kept as the source's. Positions are model space in the game's basis.
"""
import numpy as np

from .gr2_anim import STOCK, animation_file, convert_frame, split
from .gr2_skin import quat_matrix

DEFAULT_HELD = ("bip01 prop1", "bip01 prop2")
DEFAULT_MARKERS = ("bone hitpointbar",)


def _compose(rot, pos):
    m = np.eye(4)
    m[:3, :3] = rot
    m[:3, 3] = pos
    return m


class Retarget:
    """Puts poses of `src` (a Rig) on `tgt` (a Rig). `bone_map`: {target bone: source bone} for
    bones whose names differ (any case); `root`: the target's biped root (default `Bip01`, else
    the first target bone the source has); `root_scale`: the root's motion scale (default the
    ratio of the roots' heights at rest)."""

    def __init__(self, src, tgt, bone_map=None, held=DEFAULT_HELD, markers=DEFAULT_MARKERS,
                 root=None, root_scale=None):
        self.src, self.tgt = src, tgt
        bm = {k.lower(): v.lower() for k, v in (bone_map or {}).items()}
        self.source_of = {}
        for name in tgt.names:
            low = name.lower()
            s = bm.get(low, low)
            if src.has(s):
                self.source_of[low] = s
        self.held = {h.lower() for h in held}
        self.markers = {m.lower() for m in markers}
        if root is None:
            root = "bip01" if "bip01" in self.source_of else next(
                (n.lower() for n in tgt.names if n.lower() in self.source_of), None)
        self.root = root.lower() if root else None
        # rest frames of both rigs in the target's basis
        self.c, self.s = src.basis.to(tgt.basis)
        self.src_rest = {k: convert_frame(w, self.c, self.s) for k, w in src.by_name(src.rest_worlds()).items()}
        self.tgt_rest = tgt.by_name(tgt.rest_worlds())
        up = tgt.basis.up / (np.linalg.norm(tgt.basis.up) or 1.0)
        self.up = up
        if root_scale is None and self.root:
            ht = float(self.tgt_rest[self.root][:3, 3] @ up)
            hs = float(self.src_rest[self.source_of[self.root]][:3, 3] @ up)
            root_scale = ht / hs if hs > 1e-6 and ht > 1e-6 else 1.0
        self.root_scale = 1.0 if root_scale is None else float(root_scale)

    def report(self):
        """(matched, target only, source only, root, root scale) for a run's report."""
        matched = [n for n in self.tgt.names if n.lower() in self.source_of]
        tgt_only = [n for n in self.tgt.names if n.lower() not in self.source_of]
        used = set(self.source_of.values())
        src_only = [n for n in self.src.names if n.lower() not in used]
        return matched, tgt_only, src_only, self.root, self.root_scale

    def source_pose(self, anim, t):
        """The source's world frames at time t of `anim`, in the target's basis, by lower name."""
        return self.src.by_name(self.src.pose(anim, t, basis=self.tgt.basis))

    def worlds(self, src_pose):
        """The target's world frames (bone order) for a source pose (world frames by lower name,
        in the target's basis)."""
        tgt, out = self.tgt, []
        for i, name in enumerate(tgt.names):
            low = name.lower()
            par = tgt.parents[i]
            pw = out[par] if par >= 0 else np.eye(4)
            rest_local = np.eye(4)
            rest_local[:3, :3] = quat_matrix(tgt.rest[i][1])
            rest_local[:3, 3] = tgt.rest[i][0]
            s = self.source_of.get(low)
            w_src = src_pose.get(s) if s else None
            if w_src is None:
                w = pw @ rest_local
            elif low in self.markers:
                w = w_src.copy()
            elif low in self.held and self._parent_source(i) in src_pose:
                sp = src_pose[self._parent_source(i)]
                w = pw @ (np.linalg.inv(sp) @ w_src)
            else:
                rot = w_src[:3, :3] @ self.src_rest[s][:3, :3].T @ self.tgt_rest[low][:3, :3]
                if low == self.root:
                    pos = self.tgt_rest[low][:3, 3] + self.root_scale * (w_src[:3, 3] - self.src_rest[s][:3, 3])
                else:
                    pos = (pw @ np.append(tgt.rest[i][0], 1.0))[:3]
                w = _compose(rot, pos)
            out.append(w)
        return out

    def _parent_source(self, i):
        par = self.tgt.parents[i]
        if par < 0:
            return None
        src_bone = self.source_of.get(self.tgt.names[i].lower())
        if src_bone is None:
            return None
        j = self.src.index[src_bone]
        sp = self.src.parents[j]
        return self.src.names[sp].lower() if sp >= 0 else None

    def locals(self, worlds):
        """(position, quaternion) per target bone for its world frames."""
        out = []
        for i, w in enumerate(worlds):
            par = self.tgt.parents[i]
            loc = np.linalg.inv(worlds[par]) @ w if par >= 0 else w
            out.append(split(loc))
        return out

    def sample(self, anim, times):
        """[target world frames] at each time."""
        return [self.worlds(self.source_pose(anim, t)) for t in times]

    def animation(self, anim, model_name, fps=30.0, name=None):
        """(bytes of the retargeted .gr2 animation, times, target world frames per time). One track
        group named `model_name`, a track per target bone, in the target's basis."""
        dur = max(anim.duration, 1e-6)
        n = max(2, int(round(dur * fps)) + 1)
        times = np.linspace(0.0, dur, n)
        frames = self.sample(anim, times)
        locs = [self.locals(w) for w in frames]
        tracks = []
        for i, bone in enumerate(self.tgt.names):
            pos = np.array([f[i][0] for f in locs])
            quat = np.array([f[i][1] for f in locs])
            tracks.append((bone, times, pos, quat))
        data = animation_file(name or anim.name, dur, model_name, tracks, basis=self.tgt.basis,
                              accumulation=anim.accumulation, timestep=anim.timestep,
                              source=name or anim.name)
        return data, times, frames


# --------------------------------------------------------------------------------------------------
# Tag files


def tag_bone(tag, rig):
    """The lower-case name of the bone of `rig` a tag names (`HEAD` -> `bip01 head`, `L TOE` ->
    `bip01 l toe0`, `HITPOINTBAR` -> `bone hitpointbar`), or None; `MASTER` names no bone (it is the
    unit's own frame)."""
    t = tag.strip().lower()
    if t == "master":
        return None
    for cand in (t, "bip01 " + t, "bip01 " + t + "0", "bone " + t, "bone_" + t):
        if rig.has(cand):
            return cand
    return None


def retarget_precomp(pre, rig, pose_at, game_basis=STOCK):
    """A copy of the tag file `pre` (a precomp.Precomp) for the retargeted animation: each tag that
    names a bone of `rig` takes that bone's position from `pose_at(t)` (world frames by lower
    name, in the rig's basis), at the file's keys spread evenly over its duration; the others and
    every rotation stay as they were. Returns (Precomp, [tags moved], [tags kept])."""
    import copy
    out = copy.deepcopy(pre)
    c, s = rig.basis.to(game_basis)
    moved, kept = [], []
    keys = pre.key_count() or 0
    times = np.linspace(0.0, pre.duration, keys) if keys > 1 else np.zeros(keys)
    poses = [pose_at(float(t)) for t in times]
    for index, tracks in pre.mapping:
        tag = pre.names[index] if 0 <= index < len(pre.names) else ""
        bone = tag_bone(tag, rig)
        if bone is None or not poses or bone not in poses[0]:
            kept.append(tag)
            continue
        for tr in tracks:
            if not 0 <= tr < len(out.positions):
                continue
            out.positions[tr] = [tuple(float(v) for v in s * (c @ p[bone][:3, 3])) for p in poses]
        moved.append(tag)
    return out, moved, kept
