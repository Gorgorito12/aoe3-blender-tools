# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic checks of a unit's animations before anyone is shown a preview
(docs/animation-rules.md, part B; tools/check_anim.py is the command). Pure Python with numpy.

A *job* names the actors of a unit (a model each: the body, a rider, a gun hung on a bone), the
clips (an animation file per actor, the length the game's tactics give, loop or death) and the
rules: which bones are the chest, the head, the knees; which points hold which grips; where a part
is mounted; which props there are and where they may hide. `check(job)` samples every clip at
`fps`, composes the actors as the anim file hangs them, runs every check and returns a `Report`.

Space. Every actor is posed in its own file's axes with the runtime's scales (a track's
scale/shear; the skeleton's rest scale for a bone the clip has no track for; none for an empty
curve: measured on the stock camel's tag files, 2026-11-23, tools/make_gun_camel.py), then brought
to one space: the stock axes (x the unit's left is negative, y up, z the way the unit faces) in
metres as the file declares them (units / UnitsPerMeter, as docs/game-formats.md; a game human is
about 2.7 of them tall). An attached actor's root hangs on its parent's bone with that bone's
scale taken out, as tools/make_gun_camel.py composes the camel, its gun and its rider; with
`from_bone`, that bone's rest frame is put on the parent's bone (an anim file's frombone /
tobone). The ground is the plane y = `ground` of the first (unattached) actor's space.

Checks (each returns PASS, FAIL or SKIP, the worst frame and its value against the limit, and the
worst frames as risk frames):

- `look`: a head or neck turned from the chest, yaw and pitch, measured from the rest pose.
- `hinge`: an elbow or knee bent the wrong way (the bend measured against the limb's front at rest).
- `speed`: the angular speed of every bone's local rotation (no snapping).
- `plant` and `sink`: a foot on the ground and slow must not slide; no foot below the ground.
- `cross`: the legs never cross (the left foot passing to the right of the right one).
- `size`: a prop's length as a share of a man's height stays in its range (props of unreal size).
- `grip`: a hand within reach of its grip during the frames given.
- `mount`: the point of a part that sat on its mount stays on it (the floating gun).
- `prop`: a prop never appears or vanishes in the open from one frame to the next.
- `route`: a prop starts and ends where the clip's script says (the reload that put the same
  magazine back).
- `penetration`: named points not below the ground and not inside named capsules.
- `duration` and `loop`: the clip's length is the tactics' value, every actor's clip is as long,
  and a loop closes.
- `death`: at the end of a death clip no part floats above the ground or what it rests on.
- `inventory` (with a baseline job): no clip and no motion that existed is gone unless the job
  lists it under `removed` (the dismount that went missing).
"""
import copy
import json
import math
import os
import re

import numpy as np

from . import gr2
from .gr2_anim import Basis, Curve, convert_frame, frame, matrix_quat
from .gr2_skin import quat_matrix
from .gr2_write import STOCK_BASIS

# the space every check works in: the stock axes, metres as the files declare them
METRES = Basis(STOCK_BASIS["right"], STOCK_BASIS["up"], STOCK_BASIS["back"], 1.0)
UP = np.array([0.0, 1.0, 0.0])
FORWARD = np.array([0.0, 0.0, 1.0])     # a unit faces +z at rest (tools/make_dismount.py, make_gun_camel.py)

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

# Limits. Angles in degrees, distances in metres (see the note on space), speeds per second.
LIMITS = {
    "look_yaw": 70.0,              # a head or neck turned left or right of the chest
    "look_pitch_up": 40.0,         # tipped back
    "look_pitch_down": 40.0,       # bowed
    "hinge_min_bend": 10.0,        # an elbow or knee bent less than this is straight: not judged
    "hinge_reverse": 100.0,        # bent more than this far from the way it bends: reversed
    "angular_speed": 1500.0,       # any bone's local rotation, degrees per second (50 a frame at 30)
    "plant_height": 0.03,          # a foot point this near the ground ...
    "plant_speed": 0.3,            # ... and this slow (m/s) is planted
    "slide": 0.04,                 # how far a planted foot point may slide
    "sink": 0.05,                  # how far a foot point may go below the ground
    "grip": 0.03,                  # a hand from its grip
    "mount": 0.02,                 # a part's seat from its mount
    "prop_speed": 20.0,            # a prop faster than this (m/s, 0.67 m a frame at 30) jumped
    "prop_scale": 0.05,            # a prop scaled below this share of its rest size is gone
    "swap": 0.03,                  # twin props trade places within this distance
    "penetration": 0.02,           # how deep a point may go into a capsule or below the ground
    "duration": 0.001,             # seconds a clip's length may differ from the tactics'
    "loop_angle": 3.0,             # a loop's seam (last pose to first), every bone's rotation ...
    "loop_position": 0.02,         # ... and position, beyond 1.5 times its largest step inside the clip
    "death_float": 0.05,           # a part's lowest point above the ground or its support
    "cross": 0.02,                 # the left foot this far to the right of the right foot: the legs crossed
    "removed_travel": 0.3,         # a baseline motion this large ...
    "removed_share": 0.5,          # ... that shrank below this share was removed
    "risk_frames": 3,              # the worst frames kept per check
}

# The game's human rigs (Bip01 names, as 3ds Max's Biped exports them). A bone a rig lacks is
# skipped; `chest` takes the first that exists.
HUMAN = {
    "chest": ["bip01 spine2", "bip01 spine1", "bip01 spine"],
    "pelvis": "bip01 pelvis",
    "look": [{"bone": "bip01 head"}, {"bone": "bip01 neck"}],
    "hinges": [
        {"name": "left knee", "upper": "bip01 l thigh", "middle": "bip01 l calf", "end": "bip01 l foot",
         "bends": "back"},
        {"name": "right knee", "upper": "bip01 r thigh", "middle": "bip01 r calf", "end": "bip01 r foot",
         "bends": "back"},
        {"name": "left elbow", "upper": "bip01 l upperarm", "middle": "bip01 l forearm", "end": "bip01 l hand",
         "bends": "front"},
        {"name": "right elbow", "upper": "bip01 r upperarm", "middle": "bip01 r forearm", "end": "bip01 r hand",
         "bends": "front"},
    ],
    "feet": [{"name": "left foot", "bone": "bip01 l foot", "toe": "bip01 l toe0"},
             {"name": "right foot", "bone": "bip01 r foot", "toe": "bip01 r toe0"}],
    "sole": 0.08,                  # the ankle above the sole, when the model has no mesh
    "hands": ["bip01 l hand", "bip01 r hand"],
    "torso": {"a": "bip01 pelvis", "b": "bip01 neck", "radius": 0.12},
    "speed": {"bip01 head": 800.0, "bip01 neck": 800.0},
    "signature": ["bip01 pelvis", "bip01 l foot", "bip01 r foot"],
    "cross": [("bip01 l foot", "bip01 r foot"), ("bip01 l toe0", "bip01 r toe0")],
}
# Any other rig: nothing named; a job adds what it needs ("feet" for hooves, "look", "hinges", ...).
BARE = {"chest": [], "look": [], "hinges": [], "feet": [], "hands": [], "torso": None, "speed": {},
        "signature": [], "sole": 0.08, "cross": []}
PRESETS = {"human": HUMAN, "bare": BARE}

LOOP_NAMES = re.compile(r"(idle|walk|jog|run|trot|canter|gallop|bored)", re.I)
MOVE_NAMES = re.compile(r"(walk|jog|run|trot|canter|gallop)", re.I)


class JobError(ValueError):
    """A job that cannot be run (a missing file, an unknown bone, a bad spec)."""


# --------------------------------------------------------------------------------------------------
# Frames


def rotation(m):
    """The rotation part of a 3 x 3 (or 4 x 4) frame, its scale taken out (nearest rotation)."""
    a = np.asarray(m, np.float64)[:3, :3]
    u, _s, vt = np.linalg.svd(a)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] = -u[:, -1]
        r = u @ vt
    return r


def rigid(m):
    out = np.eye(4)
    out[:3, :3] = rotation(m)
    out[:3, 3] = np.asarray(m)[:3, 3]
    return out


def angle_between_rotations(a, b):
    """Degrees of the turn taking rotation a to rotation b."""
    r = a.T @ b
    c = (np.trace(r) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def unit(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def scale_of(m):
    return abs(np.linalg.det(np.asarray(m, np.float64)[:3, :3])) ** (1.0 / 3.0)


# --------------------------------------------------------------------------------------------------
# Models and clips


class Model:
    """A skeleton: bone names, parents, rest (position, quaternion, scale 3 x 3) in its basis, and
    the meshes when the file has some (gr2_mesh.read) for the pictures and the death check."""

    def __init__(self, names, parents, rest, basis, meshes=None, skeleton=None, name=""):
        self.names, self.parents, self.rest, self.basis = list(names), list(parents), list(rest), basis
        self.index = {n.lower(): i for i, n in enumerate(self.names)}
        self.meshes, self.skeleton, self.name = meshes or [], skeleton, name
        self.children = [[] for _ in self.names]
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[p].append(i)

    @classmethod
    def of_root(cls, root, data=None, name=""):
        sks = root.get("Skeletons") or []
        if not sks:
            raise JobError(f"{name or 'model'}: no skeleton")
        names, parents, rest = [], [], []
        for b in sks[0].get("Bones"):
            t = b.get("Transform")
            flags = int(t.get("flags") or 0)
            pos = np.array(t["position"], np.float64) if flags & 1 else np.zeros(3)
            q = np.array(t["orientation"], np.float64) if flags & 2 else np.array([0, 0, 0, 1.0])
            s = np.array(t["scale_shear"], np.float64).reshape(3, 3) if flags & 4 else np.eye(3)
            names.append(b.get("Name"))
            parents.append(int(b.get("ParentIndex")))
            rest.append((pos, q / np.linalg.norm(q), s))
        meshes, skel = [], None
        if data is not None and root.get("Meshes"):
            from . import gr2_mesh
            try:
                read = gr2_mesh.read(data)
                meshes, skel = read["meshes"], (read["skeletons"] or [None])[0]
            except gr2.Gr2Error:
                meshes, skel = [], None
        return cls(names, parents, rest, Basis.of(root), meshes, skel, name)

    @classmethod
    def of_dict(cls, d, name=""):
        """A rig described in JSON: {"basis": "metres" | "stock", "bones": [{"name", "parent" (name or
        null), "position", "orientation" (x y z w, optional)}]}."""
        basis = METRES if d.get("basis", "metres") == "metres" else Basis(
            STOCK_BASIS["right"], STOCK_BASIS["up"], STOCK_BASIS["back"], STOCK_BASIS["units_per_meter"])
        names = [b["name"] for b in d["bones"]]
        low = {n.lower(): i for i, n in enumerate(names)}
        parents, rest = [], []
        for b in d["bones"]:
            p = b.get("parent")
            if p is not None and p.lower() not in low:
                raise JobError(f"{name}: bone {b['name']}: unknown parent {p}")
            parents.append(-1 if p is None else low[p.lower()])
            q = np.array(b.get("orientation", (0, 0, 0, 1)), np.float64)
            rest.append((np.array(b.get("position", (0, 0, 0)), np.float64), q / np.linalg.norm(q), np.eye(3)))
        return cls(names, parents, rest, basis, name=name)

    @classmethod
    def load(cls, path):
        if path.lower().endswith(".json"):
            with open(path, encoding="utf-8") as f:
                return cls.of_dict(json.load(f), os.path.basename(path))
        with open(path, "rb") as f:
            data = f.read()
        try:
            root = gr2.load(data).root()
        except gr2.Compressed as exc:
            raise JobError(f"{path}: compressed ({exc}); expand it first (tools/uncompress_models.py)") from exc
        return cls.of_root(root, data, os.path.basename(path))

    def has(self, bone):
        return bone.lower() in self.index


class Clip:
    """An animation's tracks: position, orientation and scale/shear curves by bone (lower case)."""

    def __init__(self, duration, tracks, basis, accumulation=0, name=""):
        self.duration, self.tracks, self.basis = float(duration), tracks, basis
        self.accumulation, self.name = int(accumulation), name

    @classmethod
    def of_root(cls, root, name=""):
        anims = root.get("Animations") or []
        groups = root.get("TrackGroups") or []
        if not groups:
            raise JobError(f"{name}: no track group")
        a = anims[0] if anims else None
        g = groups[0]
        tracks = {}
        for tr in g.get("TransformTracks") or []:
            if tr is None:
                continue
            tracks[tr.get("Name").lower()] = tuple(
                Curve.of(tr.get(k)) for k in ("PositionCurve", "OrientationCurve", "ScaleShearCurve"))
        return cls(float(a.get("Duration")) if a is not None else 0.0, tracks, Basis.of(root),
                   int(g.get("AccumulationFlags") or 0), name)

    @classmethod
    def load(cls, path):
        try:
            return cls.of_root(gr2.load(path).root(), os.path.basename(path))
        except gr2.Compressed as exc:
            raise JobError(f"{path}: compressed ({exc}); expand it first (tools/uncompress_models.py)") from exc

    @classmethod
    def of_keys(cls, duration, keyed, basis=METRES, name=""):
        """A clip from sampled values: {bone: (times, positions N x 3 or None, quaternions N x 4 or
        None, scales N x 3 x 3 or None)}; linear between samples (for tests and generators)."""
        tracks = {}
        for bone, (times, pos, quats, scales) in keyed.items():
            times = np.asarray(times, np.float64)

            def curve(values, dim):
                if values is None:
                    return Curve(0, [], [])
                v = np.asarray(values, np.float64).reshape(len(times), dim)
                if dim == 4:
                    v = v.copy()
                    for i in range(1, len(v)):
                        if v[i] @ v[i - 1] < 0:
                            v[i] = -v[i]
                return Curve(1, times, v.ravel())          # as gr2_anim.animation_file writes one
            tracks[bone.lower()] = (curve(pos, 3), curve(quats, 4), curve(scales, 9))
        return cls(duration, tracks, basis, 0, name)


def _sample(curve, t):
    if curve is None or curve.empty():
        return None
    return curve.sample(t)


def pose(model, clip, t):
    """World frames (4 x 4, the model's file axes and units, the runtime's scales) of every bone at
    time t of `clip` (None: the rest pose), in bone order."""
    if clip is not None:
        c, s = clip.basis.to(model.basis)
    out = []
    for i, name in enumerate(model.names):
        rp, rq, rs = model.rest[i]
        p, q, sc = rp, rq, rs
        tr = clip.tracks.get(name.lower()) if clip is not None else None
        if tr is not None:
            pv, qv, sv = (_sample(cv, t) for cv in tr)
            if pv is not None:
                p = s * (c @ pv)
            if qv is not None:
                q = matrix_quat(c @ quat_matrix(qv / (np.linalg.norm(qv) or 1.0)) @ c.T)
            sc = np.eye(3) if sv is None else c @ np.asarray(sv, np.float64).reshape(3, 3) @ c.T
        m = frame(p, q)
        m[:3, :3] = m[:3, :3] @ sc
        par = model.parents[i]
        out.append(out[par] @ m if par >= 0 else m)
    return out


# --------------------------------------------------------------------------------------------------
# Jobs


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = v
    return out


class Actor:
    def __init__(self, name, model, spec):
        self.name, self.model, self.spec = name, model, spec
        attach = spec.get("attach") or None
        self.parent = attach.get("to") if attach else None
        self.to_bone = attach.get("bone") if attach else None
        self.from_bone = attach.get("from_bone") if attach else None
        self.keep_scale = bool(attach.get("scaled")) if attach else False
        rig = spec.get("rig")
        if isinstance(rig, str):
            rig = {"preset": rig}
        if rig:
            preset = PRESETS.get(rig.get("preset", "human"))
            if preset is None:
                raise JobError(f"actor {name}: unknown rig preset {rig.get('preset')}")
            self.rig = _merge(preset, {k: v for k, v in rig.items() if k != "preset"})
        else:
            self.rig = None
        c, s = model.basis.to(METRES)
        self.to_metres = (c, s)

    def bone(self, name):
        i = self.model.index.get(name.lower())
        return i

    def chest(self):
        if not self.rig:
            return None
        for b in self.rig["chest"]:
            if self.model.has(b):
                return b.lower()
        return None


class Job:
    """What to check: actors, clips and rules (see docs/animation-rules.md, "The job file").

    `spec` keys: "actors" {name: {"model": path or Model, "rig": "human" | {...}, "attach":
    {"to", "bone", "from_bone"}}}, "clips" {name: {"anims": {actor: path or Clip}, "duration",
    "loop", "death", "ground_speed", "routes", "allow_jumps"}}, "fps", "ground" (None: no ground),
    "limits", "points", "grips", "ahead", "sizes", "mounts", "capsules", "props", "places",
    "penetration_points", "removed", "speed_exempt"."""

    def __init__(self, spec, base_dir="."):
        self.spec = spec
        self.base = base_dir
        self.fps = float(spec.get("fps", 30))
        self.ground = spec.get("ground", 0.0)
        self.limits = _merge(LIMITS, spec.get("limits"))
        self.actors = {}
        for name, a in (spec.get("actors") or {}).items():
            m = a.get("model")
            model = m if isinstance(m, Model) else Model.load(self.path(m))
            self.actors[name] = Actor(name, model, a)
        if not self.actors:
            raise JobError("no actors")
        for a in self.actors.values():
            if a.parent and a.parent not in self.actors:
                raise JobError(f"actor {a.name}: attached to unknown actor {a.parent}")
            if a.parent and not self.actors[a.parent].model.has(a.to_bone or ""):
                raise JobError(f"actor {a.name}: {a.parent} has no bone {a.to_bone}")
        self.order = self._order()
        self.clips = {}
        for cname, c in (spec.get("clips") or {}).items():
            anims = {}
            for actor, path in (c.get("anims") or {}).items():
                if actor not in self.actors:
                    raise JobError(f"clip {cname}: unknown actor {actor}")
                anims[actor] = path if isinstance(path, Clip) else Clip.load(self.path(path))
            if not anims:
                raise JobError(f"clip {cname}: no animation")
            self.clips[cname] = dict(c, anims=anims)
        self.points = spec.get("points") or {}

    def path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.base, p)

    def _order(self):
        done, out = set(), []

        def visit(n, seen=()):
            if n in done:
                return
            if n in seen:
                raise JobError(f"actor {n}: attachments loop")
            a = self.actors[n]
            if a.parent:
                visit(a.parent, seen + (n,))
            done.add(n)
            out.append(n)
        for n in self.actors:
            visit(n)
        return out

    def first_actor(self):
        return next(n for n in self.order if not self.actors[n].parent)

    # ----- names

    def split(self, ref):
        """(actor, lower-case bone) of "actor:bone" or a bare bone name (looked up in every actor)."""
        if ":" in ref:
            a, b = ref.split(":", 1)
            if a not in self.actors:
                raise JobError(f"{ref}: unknown actor {a}")
            if not self.actors[a].model.has(b):
                raise JobError(f"{ref}: {a} has no bone {b}")
            return a, b.lower()
        hits = [n for n in self.order if self.actors[n].model.has(ref)]
        if not hits:
            raise JobError(f"no actor has a bone {ref}")
        if len(hits) > 1:
            raise JobError(f"bone {ref} is in {', '.join(hits)}: write actor:bone")
        return hits[0], ref.lower()

    def point(self, spec):
        """(actor, bone, offset) of a point spec: a name of `points`, "actor:bone", or {"bone",
        "offset"} (metres, in the bone's frame)."""
        if isinstance(spec, str) and spec in self.points:
            spec = self.points[spec]
        if isinstance(spec, str):
            a, b = self.split(spec)
            return a, b, np.zeros(3)
        a, b = self.split(spec["bone"])
        return a, b, np.asarray(spec.get("offset", (0, 0, 0)), np.float64)

    def has_bone(self, actor, bone):
        return self.actors[actor].model.has(bone)


# --------------------------------------------------------------------------------------------------
# Sampling


class Sampled:
    """A clip sampled: `times`, and per actor its world frames in metres (N x bones x 4 x 4, the
    first actor's space) and its placement per frame (the frame of its root's space)."""

    def __init__(self, job, name, times, worlds, places, rests, raw):
        self.job, self.name, self.times = job, name, times
        self.worlds, self.places, self.rests, self.raw = worlds, places, rests, raw
        self.limits = _merge(job.limits, job.clips[name].get("limits"))

    def frames(self, actor, bone):
        return self.worlds[actor][:, self.job.actors[actor].model.index[bone.lower()]]

    def at(self, actor, bone, offset=None):
        """N x 3 positions of a point fixed in a bone (`offset`, metres in the bone's frame, its
        scale included: a point of the mesh bound to the bone)."""
        w = self.frames(actor, bone)
        if offset is None or not np.any(offset):
            return w[:, :3, 3].copy()
        return w[:, :3, 3] + np.einsum("nij,j->ni", w[:, :3, :3], np.asarray(offset, np.float64))

    def point(self, spec):
        """N x 3 positions of a point spec; {"bone", "at": <point>} is the point fixed in the bone
        where <point> is at the clip's first frame (or "frame")."""
        if isinstance(spec, str) and spec in self.job.points:
            spec = self.job.points[spec]
        a, b, off = self.job.point(spec)
        if isinstance(spec, dict) and spec.get("at"):
            k = int(spec.get("frame", 0))
            target = self.point(spec["at"])[k]
            off = (np.linalg.inv(self.frames(a, b)[k]) @ np.r_[target, 1.0])[:3]
        return self.at(a, b, off)


def _to_metres(m, actor):
    c, s = actor.to_metres
    return convert_frame(m, c, s)


def sample(job, clip_name, fps=None):
    """Every actor's world frames at every frame of the clip (0 to its length inclusive)."""
    clip = job.clips[clip_name]
    fps = fps or job.fps
    length = max(c.duration for c in clip["anims"].values())
    n = max(2, int(round(length * fps)) + 1)
    times = np.linspace(0.0, length, n) if length > 0 else np.zeros(1)
    worlds, places, rests, raw = {}, {}, {}, {}
    for name in job.order:
        a = job.actors[name]
        rest = [_to_metres(w, a) for w in pose(a.model, None, 0.0)]
        rests[name] = np.array(rest)
    for name in job.order:
        a = job.actors[name]
        anim = clip["anims"].get(name)
        frames, pl, fr = [], [], []
        for k, t in enumerate(times):
            own = pose(a.model, anim, min(t, anim.duration) if anim else 0.0)
            fr.append(own)
            local = [_to_metres(w, a) for w in own]
            place = np.eye(4)
            if a.parent:
                pw = worlds[a.parent][k, job.actors[a.parent].model.index[a.to_bone.lower()]]
                place = pw if a.keep_scale else rigid(pw)
                if a.from_bone:
                    place = place @ np.linalg.inv(rests[name][a.model.index[a.from_bone.lower()]])
            frames.append([place @ w for w in local])
            pl.append(place)
        worlds[name] = np.array(frames)
        places[name] = np.array(pl)
        raw[name] = np.array(fr)
    return Sampled(job, clip_name, times, worlds, places, rests, raw)


def mesh_points(job, sampled, actor, k):
    """The actor's mesh vertices at frame k (metres, the first actor's space), one array per mesh;
    [] when the model has none."""
    from .gr2_skin import deform
    a = job.actors[actor]
    if not a.model.meshes or a.model.skeleton is None:
        return []
    exact = {n: w for n, w in zip(a.model.names, sampled.raw[actor][k])}
    c, s = a.to_metres
    place = sampled.places[actor][k]
    out = []
    for m in a.model.meshes:
        p = deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"], m["skin_names"],
                   a.model.skeleton, exact)
        p = s * (p @ c.T)
        out.append(p @ place[:3, :3].T + place[:3, 3])
    return out


def skinned(job, sampled, actor, picks):
    """Vertices (mesh index, vertex index) of an actor followed through the clip as the skin
    moves them: N frames x len(picks) x 3, metres, the first actor's space."""
    from .gr2_skin import deform
    a = job.actors[actor]
    c, s = a.to_metres
    out = np.zeros((len(sampled.times), len(picks), 3))
    for k in range(len(sampled.times)):
        exact = {n: w for n, w in zip(a.model.names, sampled.raw[actor][k])}
        place = sampled.places[actor][k]
        for j, (mi, vi) in enumerate(picks):
            m = a.model.meshes[mi]
            sl = slice(vi, vi + 1)
            p = deform(m["file_positions"][sl], m["vertex_bones4"][sl], m["vertex_weights4"][sl], m["skin_names"],
                       a.model.skeleton, exact)
            p = s * (p @ c.T)
            out[k, j] = (p @ place[:3, :3].T + place[:3, 3])[0]
    return out


# --------------------------------------------------------------------------------------------------
# Results


class Result:
    """One check of one clip: status, the worst value against its limit, where, and the risk
    frames [(frame, time, value, detail, [points to mark])]."""

    def __init__(self, clip, check, item, status, value=None, limit=None, unit="", frame=None, time=None,
                 detail="", risks=None):
        self.clip, self.check, self.item, self.status = clip, check, item, status
        self.value, self.limit, self.unit = value, limit, unit
        self.frame, self.time, self.detail = frame, time, detail
        self.risks = risks or []

    def line(self):
        v = ""
        if self.check == "duration" and self.value is not None and self.limit is not None:
            v = f" {self.value:.3f} s against {self.limit:.3f} s"
        elif self.value is not None:
            lim = f" (limit {self.limit:g}{self.unit})" if self.limit is not None else ""
            v = f" worst {self.value:.3g}{self.unit}{lim}"
        at = f" at {self.time:.3f} s (frame {self.frame})" if self.time is not None else ""
        d = f": {self.detail}" if self.detail else ""
        return f"  {self.status:4s}  {self.check:11s} {self.item}{v}{at}{d}"

    def as_dict(self):
        return {"clip": self.clip, "check": self.check, "item": self.item, "status": self.status,
                "value": self.value, "limit": self.limit, "unit": self.unit, "frame": self.frame,
                "time": self.time, "detail": self.detail,
                "risk_frames": [{"frame": f, "time": t, "value": v, "detail": d,
                                 "points": [list(map(float, p)) for p in pts]}
                                for f, t, v, d, pts in self.risks]}


def _risks(values, times, details, points, n, higher=True, min_gap=2):
    """The worst n frames (by value), at least min_gap frames apart."""
    order = np.argsort(-np.asarray(values) if higher else np.asarray(values), kind="stable")
    out, taken = [], []
    for k in order:
        if len(out) >= n:
            break
        if not np.isfinite(values[k]):
            continue
        if any(abs(int(k) - j) < min_gap for j in taken):
            continue
        taken.append(int(k))
        out.append((int(k), float(times[k]), float(values[k]), details[k] if details else "",
                    points[k] if points else []))
    return out


def _result(s, check, item, values, limit, unit, details=None, points=None, fail_above=True, n=3):
    values = np.asarray(values, np.float64)
    if not len(values) or not np.isfinite(values).any():
        return Result(s.name, check, item, PASS, detail="nothing to judge")
    k = int(np.nanargmax(values)) if fail_above else int(np.nanargmin(values))
    v = float(values[k])
    bad = v > limit if fail_above else v < limit
    return Result(s.name, check, item, FAIL if bad else PASS, v, limit, unit, k, float(s.times[k]),
                  details[k] if details else "", _risks(values, s.times, details, points, n, fail_above))


# --------------------------------------------------------------------------------------------------
# Checks


def check_look(job, s):
    out = []
    L = s.limits
    n = int(L["risk_frames"])
    for name in job.order:
        a = job.actors[name]
        chest = a.chest()
        if not a.rig or chest is None:
            continue
        ci = a.model.index[chest]
        C0 = rotation(s.rests[name][ci])
        up_l, fwd_l = C0.T @ UP, C0.T @ FORWARD
        for spec in a.rig.get("look", []):
            bone = spec["bone"].lower()
            if not a.model.has(bone) or bone == chest:
                continue
            hi = a.model.index[bone]
            face_l = rotation(s.rests[name][hi]).T @ FORWARD
            lim_y = float(spec.get("yaw", L["look_yaw"]))
            lim_u = float(spec.get("pitch_up", L["look_pitch_up"]))
            lim_d = float(spec.get("pitch_down", L["look_pitch_down"]))
            yaws, ups, downs, det, pts = [], [], [], [], []
            for k in range(len(s.times)):
                C = rotation(s.worlds[name][k, ci])
                H = rotation(s.worlds[name][k, hi])
                cu, cf = C @ up_l, C @ fwd_l
                cs = np.cross(cu, cf)
                f = H @ face_l
                yaw = math.degrees(math.atan2(float(f @ cs), float(f @ cf)))
                pitch = math.degrees(math.asin(max(-1.0, min(1.0, float(f @ cu)))))
                yaws.append(abs(yaw))
                ups.append(max(0.0, pitch))
                downs.append(max(0.0, -pitch))
                det.append(f"yaw {yaw:+.0f}, pitch {pitch:+.0f} from the chest")
                pts.append([s.worlds[name][k, hi][:3, 3]])
            item = f"{name}:{bone}"
            out.append(_result(s, "look", f"{item} yaw", yaws, lim_y, " deg", det, pts, n=n))
            out.append(_result(s, "look", f"{item} pitch up", ups, lim_u, " deg", det, pts, n=n))
            out.append(_result(s, "look", f"{item} pitch down", downs, lim_d, " deg", det, pts, n=n))
    return out


def check_hinges(job, s):
    out = []
    L = s.limits
    for name in job.order:
        a = job.actors[name]
        if not a.rig:
            continue
        for h in a.rig.get("hinges", []):
            bones = [h[k].lower() for k in ("upper", "middle", "end")]
            if not all(a.model.has(b) for b in bones):
                continue
            ui, mi, ei = (a.model.index[b] for b in bones)
            ant_l = rotation(s.rests[name][ui]).T @ FORWARD
            sign = 1.0 if h.get("bends", "front") == "front" else -1.0
            lim = float(h.get("reverse", L["hinge_reverse"]))
            vals, det, pts = [], [], []
            for k in range(len(s.times)):
                W = s.worlds[name][k]
                pu, pm, pe = W[ui][:3, 3], W[mi][:3, 3], W[ei][:3, 3]
                u = unit(pm - pu)
                v = pe - pm
                bend = math.degrees(math.acos(max(-1.0, min(1.0, float(unit(v) @ u)))))
                b = v - (v @ u) * u
                ant = rotation(W[ui]) @ ant_l
                want = unit(sign * (ant - (ant @ u) * u))
                off = math.degrees(math.acos(max(-1.0, min(1.0, float(unit(b) @ want))))) \
                    if np.linalg.norm(b) > 1e-9 else 0.0
                judged = bend >= L["hinge_min_bend"]
                vals.append(off if judged else 0.0)
                det.append(f"bent {bend:.0f} deg, {off:.0f} deg from the way it bends")
                pts.append([pm])
            out.append(_result(s, "hinge", f"{name} {h['name']} reversed", vals, lim, " deg", det, pts,
                               n=int(L["risk_frames"])))
    return out


def _local_rotations(s, name):
    a = s.job.actors[name]
    W = s.worlds[name]
    out = np.zeros((len(s.times), len(a.model.names), 3, 3))
    for k in range(len(s.times)):
        for i, p in enumerate(a.model.parents):
            m = np.linalg.inv(s.places[name][k] if p < 0 else W[k, p]) @ W[k, i]
            out[k, i] = rotation(m)
    return out


def check_speed(job, s):
    out = []
    L = s.limits
    exempt = {e.lower() for e in job.spec.get("speed_exempt") or []}
    for p in (job.spec.get("props") or {}).values():
        exempt.add(":".join(job.point(p.get("point", p.get("bone")))[:2]))
    if len(s.times) < 2:
        return out
    dt = np.diff(s.times)
    for name in job.order:
        a = job.actors[name]
        if name not in job.clips[s.name]["anims"]:
            continue
        R = _local_rotations(s, name)
        per_bone = (a.rig or {}).get("speed", {})
        limits = job.spec.get("speed_limits") or {}
        worst_ratio = np.zeros(len(s.times))
        det = [""] * len(s.times)
        pts = [[] for _ in s.times]
        worst = None
        for i, bone in enumerate(a.model.names):
            key = f"{name}:{bone.lower()}"
            if key in exempt or bone.lower() in exempt:
                continue
            lim = float(limits.get(key, limits.get(bone.lower(), per_bone.get(bone.lower(), L["angular_speed"]))))
            for k in range(1, len(s.times)):
                w = angle_between_rotations(R[k - 1, i], R[k, i]) / dt[k - 1]
                r = w / lim
                if r > worst_ratio[k]:
                    worst_ratio[k] = r
                    det[k] = f"{bone} turns {w:.0f} deg/s (limit {lim:g})"
                    pts[k] = [s.worlds[name][k, i][:3, 3]]
                if worst is None or r > worst[0]:
                    worst = (r, w, lim, bone, k)
        if worst is None:
            continue
        r, w, lim, bone, k = worst
        res = Result(s.name, "speed", f"{name} bones (deg/s against each bone's limit)", FAIL if r > 1 else PASS,
                     w, lim, " deg/s", k, float(s.times[k]), f"{bone}",
                     _risks(worst_ratio, s.times, det, pts, int(L["risk_frames"])))
        out.append(res)
    return out


def _ground_speed(job, s, contacts):
    clip = job.clips[s.name]
    gs = clip.get("ground_speed")
    if gs is None:
        gs = "auto" if MOVE_NAMES.search(s.name) else 0.0
    if gs != "auto":
        return float(gs)
    # a clip played in place: the feet on the ground move back at the unit's speed
    vz = []
    dt = np.diff(s.times)
    g = job.ground or 0.0
    for p in contacts.values():
        low = p[:-1, 1] - g < s.limits["plant_height"] * 2
        v = np.diff(p[:, 2]) / dt
        vz += list(v[low])
    return float(-np.median(vz)) if vz else 0.0


def foot_contacts(job, s):
    """{"actor foot heel|toe": N x 3} of every human actor's feet. With a mesh: the lowest vertex of
    the foot at rest nearest the back (the heel) and the most forward of the lowest ones (the toe),
    moved by the skin as the game moves them. Without: the point under the ankle by the rig's
    `sole`, fixed in the foot bone, and the toe bone's point at that height."""
    out = {}
    for name in job.order:
        a = job.actors[name]
        if not a.rig:
            continue
        for f in a.rig.get("feet", []):
            bone = f["bone"].lower()
            if not a.model.has(bone):
                continue
            toe_bone = f["toe"].lower() if f.get("toe") and a.model.has(f["toe"]) else None
            picks = _foot_vertices(job, name, [bone] + ([toe_bone] if toe_bone else []))
            if picks:
                pts = skinned(job, s, name, picks)
                out[f"{name} {f['name']} heel"] = pts[:, 0]
                out[f"{name} {f['name']} toe"] = pts[:, 1]
                continue
            fi = a.model.index[bone]
            F0 = s.rests[name][fi]
            heel = F0[:3, 3] - UP * float(a.rig.get("sole", 0.08))
            heel_l = np.linalg.inv(rigid(F0)) @ np.r_[heel, 1.0]
            out[f"{name} {f['name']} heel"] = np.array([(rigid(m) @ heel_l)[:3] for m in s.worlds[name][:, fi]])
            if toe_bone:
                ti = a.model.index[toe_bone]
                T0 = s.rests[name][ti]
                toe = T0[:3, 3].copy()
                toe[1] = heel[1]
                toe_l = np.linalg.inv(rigid(T0)) @ np.r_[toe, 1.0]
                out[f"{name} {f['name']} toe"] = np.array([(rigid(m) @ toe_l)[:3] for m in s.worlds[name][:, ti]])
    return out


_FOOT = {}


def _foot_vertices(job, actor, bones):
    """[(mesh, vertex) of the heel, (mesh, vertex) of the toe]: of the vertices mostly bound to
    `bones`, those within 2 cm of the lowest at the rest pose, the hindmost and the foremost; None
    without a mesh."""
    a = job.actors[actor]
    if not a.model.meshes or a.model.skeleton is None:
        return None
    key = (id(a.model), tuple(bones))
    if key in _FOOT:
        return _FOOT[key]
    c, s = a.to_metres
    want = set(bones)
    cand = []
    for mi, m in enumerate(a.model.meshes):
        names = [(n or "").lower() for n in m["skin_names"]]
        top = m["vertex_bones4"][:, 0]
        pts = s * (np.asarray(m["file_positions"], np.float64) @ c.T)
        for vi in np.nonzero([0 <= b < len(names) and names[b] in want for b in top])[0]:
            cand.append((pts[vi], mi, int(vi)))
    if not cand:
        _FOOT[key] = None
        return None
    low = min(cand, key=lambda x: x[0][1])
    flat = [x for x in cand if x[0][1] <= low[0][1] + 0.02]
    heel = min(flat, key=lambda x: x[0] @ FORWARD)
    toe = max(flat, key=lambda x: x[0] @ FORWARD)
    _FOOT[key] = [(heel[1], heel[2]), (toe[1], toe[2])]
    return _FOOT[key]


def check_feet(job, s):
    out = []
    L = s.limits
    if job.ground is None:
        return [Result(s.name, "plant", "feet", SKIP, detail="no ground in this job")]
    contacts = foot_contacts(job, s)
    if not contacts:
        return out
    g = float(job.ground)
    gs = _ground_speed(job, s, contacts)
    dt = np.diff(s.times)
    n = int(L["risk_frames"])
    for key, p in contacts.items():
        p = p.copy()
        p[:, 2] += gs * s.times                        # the clip played in place: the ground moves
        h = p[:, 1] - g
        # sinking
        depth = np.maximum(0.0, -h)
        det = [f"{key} {(-hh) * 100:.1f} cm below the ground" if hh < 0 else "" for hh in h]
        out.append(_result(s, "sink", key, depth, L["sink"], " m", det, [[q] for q in p], n=n))
        # sliding while planted
        v = np.r_[0.0, np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1) / dt]
        planted = (h <= L["plant_height"]) & (v <= L["plant_speed"])
        if len(planted) > 1:
            planted[0] = planted[0] and h[0] <= L["plant_height"]
        slide = np.zeros(len(h))
        start = None
        for k in range(len(h)):
            if planted[k]:
                if start is None:
                    start = k
                slide[k] = np.linalg.norm(p[k, [0, 2]] - p[start, [0, 2]])
            else:
                start = None
        det = [f"{key} slid {sl * 100:.1f} cm while planted" + (f" (ground speed {gs:.2f} m/s)" if gs else "")
               for sl in slide]
        out.append(_result(s, "plant", key, slide, L["slide"], " m", det, [[q] for q in p], n=n))
    return out


def check_grips(job, s):
    out = []
    for g in job.spec.get("grips") or []:
        if g.get("clips") and s.name not in g["clips"]:
            continue
        hand, grip = s.point(g["hand"]), s.point(g["grip"])
        d = np.linalg.norm(hand - grip, axis=1)
        ranges = g.get("frames")
        if ranges:
            on = np.zeros(len(d), bool)
            for lo, hi in ranges:
                on |= (s.times >= lo - 1e-9) & (s.times <= hi + 1e-9)
            d = np.where(on, d, np.nan)
        lim = float(g.get("max", s.limits["grip"]))
        det = [f"{d[k] * 100:.1f} cm from the grip" if np.isfinite(d[k]) else "" for k in range(len(d))]
        out.append(_result(s, "grip", g.get("name", f"{g['hand']} on {g['grip']}"), d, lim, " m", det,
                           [[hand[k], grip[k]] for k in range(len(d))], n=int(s.limits["risk_frames"])))
    return out


def check_ahead(job, s):
    """A point (a palm) at least `min` metres in front of another (a shoulder) along an actor's
    facing: the chest's forward at rest carried by the chest, made level. A hand behind the plane of
    its chest reads as an arm pulled back (job `ahead`)."""
    out = []
    for g in job.spec.get("ahead") or []:
        if g.get("clips") and s.name not in g["clips"]:
            continue
        name = g.get("name", f"{g['point']} ahead of {g['of']}")
        p, o = s.point(g["point"]), s.point(g["of"])
        actor = g.get("actor") or job.point(g["of"])[0]
        if actor not in job.actors:
            raise JobError(f"ahead {name}: unknown actor {actor}")
        a = job.actors[actor]
        chest = a.chest()
        if chest is None:
            raise JobError(f"ahead {name}: {actor} has no chest bone")
        ci = a.model.index[chest]
        fwd_l = rotation(s.rests[actor][ci]).T @ FORWARD
        vals = np.zeros(len(s.times))
        for k in range(len(s.times)):
            f = rotation(s.worlds[actor][k, ci]) @ fwd_l
            f = f - (f @ UP) * UP
            f = f / max(float(np.linalg.norm(f)), 1e-9)
            vals[k] = float((p[k] - o[k]) @ f)
        ranges = g.get("frames")
        if ranges:
            on = np.zeros(len(vals), bool)
            for lo, hi in ranges:
                on |= (s.times >= lo - 1e-9) & (s.times <= hi + 1e-9)
            vals = np.where(on, vals, np.nan)
        lim = float(g.get("min", 0.0))
        det = [f"{v * 100:+.1f} cm in front" if np.isfinite(v) else "" for v in vals]
        out.append(_result(s, "ahead", name, vals, lim, " m", det, [[p[k], o[k]] for k in range(len(vals))],
                           fail_above=False, n=int(s.limits["risk_frames"])))
    return out


def check_cross(job, s):
    """The legs crossed: the left foot (and toe) passing to the right of the right one, along the
    pelvis's right made level (the shuffle of a turn on the spot that crosses the feet). A rig's
    `cross` pairs (left, right); the limit `cross`."""
    out = []
    right = np.array([1.0, 0.0, 0.0])           # the stock axes: the unit's left is -x
    for name in job.order:
        a = job.actors[name]
        pairs = [(l_, r_) for l_, r_ in (a.rig or {}).get("cross", []) if a.model.has(l_) and a.model.has(r_)]
        pelvis = (a.rig or {}).get("pelvis")
        if not pairs or not pelvis or not a.model.has(pelvis):
            continue
        pi = a.model.index[pelvis.lower()]
        right_l = rotation(s.rests[name][pi]).T @ right
        vals = np.full(len(s.times), -np.inf)
        det = [""] * len(s.times)
        pts = [[] for _ in s.times]
        for l_, r_ in pairs:
            pl, pr = s.at(name, l_), s.at(name, r_)
            for k in range(len(s.times)):
                rv = rotation(s.worlds[name][k, pi]) @ right_l
                rv = rv - (rv @ UP) * UP
                rv = rv / max(float(np.linalg.norm(rv)), 1e-9)
                v = float((pl[k] - pr[k]) @ rv)
                if v > vals[k]:
                    vals[k] = v
                    det[k] = f"{l_} {v * 100:+.1f} cm right of {r_}"
                    pts[k] = [pl[k], pr[k]]
        out.append(_result(s, "cross", f"{name} feet", vals, s.limits["cross"], " m", det, pts,
                           n=int(s.limits["risk_frames"])))
    return out


def actor_height(job, s, actor):
    """An actor's height in its rest pose: from its lowest foot or toe bone to its head bone (a rig's
    `look` bones, else its highest bone), metres."""
    a = job.actors[actor]
    rest = s.rests[actor][:, :3, 3]
    feet = [b for f in (a.rig or {}).get("feet", []) for b in (f.get("bone"), f.get("toe")) if b and a.model.has(b)]
    low = min(rest[a.model.index[b.lower()], 1] for b in feet) if feet else float(rest[:, 1].min())
    heads = [g["bone"] for g in (a.rig or {}).get("look", []) if a.model.has(g["bone"])]
    high = float(rest[a.model.index[heads[0].lower()], 1]) if heads else float(rest[:, 1].max())
    return high - low


def check_sizes(job, s):
    """A prop's size against a man: the distance between two points (a prop's ends) at a frame of the
    clip, as a share of an actor's height, within [min, max] (job `sizes`): props of unreal size."""
    out = []
    for g in job.spec.get("sizes") or []:
        if g.get("clips") and s.name not in g["clips"]:
            continue
        name = g.get("name", f"{g['a']} to {g['b']}")
        k = min(int(g.get("frame", 0)), len(s.times) - 1)
        d = float(np.linalg.norm(s.point(g["a"])[k] - s.point(g["b"])[k]))
        h = actor_height(job, s, g["of"])
        share = d / max(h, 1e-9)
        lo, hi = float(g.get("min", 0.0)), float(g.get("max", math.inf))
        ok = lo <= share <= hi
        out.append(Result(s.name, "size", name, PASS if ok else FAIL, share, hi if share > hi else lo, " of his height",
                          k, float(s.times[k]), f"{d:.3f} m, {100 * share:.1f}% of {g['of']}'s {h:.2f} m "
                                                f"(range {100 * lo:.0f}-{100 * hi:.0f}%)"))
    return out


def check_mounts(job, s):
    out = []
    for m in job.spec.get("mounts") or []:
        if m.get("clips") and s.name not in m["clips"]:
            continue
        pa, pb, _ = job.point(m["part"])
        mount = s.point(m["mount"])
        part = s.frames(pa, pb)
        if "seat" in m:
            seat_l = np.r_[np.asarray(m["seat"], np.float64), 1.0]
        else:
            ref = 0 if m.get("reference", "first") == "first" else None
            if ref is None:
                raise JobError(f"mount {m.get('name')}: reference must be 'first' or a seat must be given")
            seat_l = np.linalg.inv(rigid(part[ref])) @ np.r_[mount[ref], 1.0]
        seat = np.array([(rigid(f) @ seat_l)[:3] for f in part])
        d = np.linalg.norm(seat - mount, axis=1)
        lim = float(m.get("max", s.limits["mount"]))
        det = [f"the seat {x * 100:.1f} cm off its mount" for x in d]
        out.append(_result(s, "mount", m.get("name", f"{m['part']} on {m['mount']}"), d, lim, " m", det,
                           [[seat[k], mount[k]] for k in range(len(d))], n=int(s.limits["risk_frames"])))
    return out


def capsule_depth(p, a, b, r):
    """How deep the points p (N x 3) are inside the capsule a-b (N x 3 each) of radius r; < 0 outside."""
    ab = b - a
    L2 = np.maximum((ab * ab).sum(1), 1e-12)
    u = np.clip(((p - a) * ab).sum(1) / L2, 0.0, 1.0)
    c = a + u[:, None] * ab
    return r - np.linalg.norm(p - c, axis=1)


def _capsules(job, s):
    """{name: (a N x 3, b N x 3, radius, spec)}: the job's capsules and each human actor's torso."""
    out = {}
    for c in job.spec.get("capsules") or []:
        out[c["name"]] = (s.point(c["a"]), s.point(c["b"]), float(c["radius"]), c)
    for name in job.order:
        a = job.actors[name]
        t = (a.rig or {}).get("torso")
        if t and a.model.has(t["a"]) and a.model.has(t["b"]):
            out[f"{name} torso"] = (s.at(name, t["a"]), s.at(name, t["b"]), float(t["radius"]),
                                    {"name": f"{name} torso", "allow": t.get("allow", [])})
    return out


def _hidden(job, s, prop, p, scale, caps):
    """Per frame: is the prop out of sight (scaled away, under the ground, in a hiding capsule)."""
    hid = scale < s.limits["prop_scale"]
    size = float(prop.get("size", 0.1))
    if job.ground is not None:
        hid |= p[:, 1] + size < float(job.ground)
    for cname in prop.get("hide_in", []):
        if cname not in caps:
            raise JobError(f"prop hides in unknown capsule {cname}")
        a, b, r, _ = caps[cname]
        hid |= capsule_depth(p, a, b, r) >= 0
    return hid


def _prop_track(job, s, prop):
    a, b, off = job.point(prop.get("point", prop.get("bone")))
    p = s.at(a, b, off)
    i = job.actors[a].model.index[b]
    rest = scale_of(s.rests[a][i]) or 1.0
    scale = np.array([scale_of(m) for m in s.worlds[a][:, i]]) / rest
    return p, scale


def _props(job, s, caps):
    """{prop: (positions N x 3, scale share N, hidden N)} and the swaps [(frame, a, b)]: twin props
    (`"twin"`: the same object drawn twice, a magazine and its spare) trading places in one frame,
    one taking the place the other had while that one goes out of sight (or both trading places). A
    swap is not seen: each object carries on in the other bone."""
    props = job.spec.get("props") or {}
    tracks = {}
    for pname, prop in props.items():
        p, scale = _prop_track(job, s, prop)
        tracks[pname] = (p, scale, _hidden(job, s, prop, p, scale, caps))
    tol = s.limits["swap"]
    swaps = []
    pairs = set()
    for a, prop in props.items():
        b = prop.get("twin")
        if b:
            if b not in props:
                raise JobError(f"prop {a}: unknown twin {b}")
            pairs.add(tuple(sorted((a, b))))
    for a, b in sorted(pairs):
        pa, _sa, ha = tracks[a]
        pb, _sb, hb = tracks[b]
        for k in range(1, len(pa)):
            for x, px, hx, y, py, hy in ((a, pa, ha, b, pb, hb), (b, pb, hb, a, pa, ha)):
                takes = np.linalg.norm(px[k] - py[k - 1]) <= tol
                gives = hy[k] or np.linalg.norm(py[k] - px[k - 1]) <= tol
                if takes and gives and (hx[k - 1] or np.linalg.norm(py[k] - px[k - 1]) <= tol):
                    swaps.append((k, x, y))
                    break
    return tracks, swaps


def check_props(job, s):
    out = []
    props = job.spec.get("props") or {}
    if not props:
        return out
    caps = _capsules(job, s)
    tracks, swaps = _props(job, s, caps)
    swapped = {(k, n) for k, a, b in swaps for n in (a, b)}
    clip = job.clips[s.name]
    allowed = clip.get("allow_jumps") or []
    half = 0.5 / job.fps + 1e-6
    dt = np.diff(s.times)
    for pname, prop in props.items():
        p, scale, hid = tracks[pname]
        speed = np.r_[0.0, np.linalg.norm(np.diff(p, axis=0), axis=1) / np.maximum(dt, 1e-9)]
        gone = scale < s.limits["prop_scale"]
        vals, det = np.zeros(len(p)), [""] * len(p)
        for k in range(1, len(p)):
            jumped = speed[k] > s.limits["prop_speed"]
            popped = gone[k - 1] != gone[k]
            if not (jumped or popped) or (hid[k - 1] and hid[k]) or (k, pname) in swapped:
                continue                                       # still, out of sight, or a swap
            t = s.times[k]
            if any((a.get("prop") in (None, pname) and abs(float(a["time"]) - t) <= half) if isinstance(a, dict)
                   else abs(float(a) - t) <= half for a in allowed):
                continue
            vals[k] = speed[k] if jumped else 1e9
            what = "jumped" if jumped else ("appeared" if scale[k] > scale[k - 1] else "vanished")
            if jumped and hid[k - 1] != hid[k]:
                what = "appeared" if hid[k - 1] else "vanished"
            det[k] = (f"{pname} {what} in sight between {s.times[k - 1]:.3f} and {t:.3f} s"
                      + (f" ({speed[k]:.1f} m/s)" if jumped else ""))
        res = _result(s, "prop", pname, vals, s.limits["prop_speed"], " m/s", det,
                      [[p[k - 1], p[k]] if k else [p[k]] for k in range(len(p))], n=int(s.limits["risk_frames"]))
        if res.value is not None and res.value >= 1e9:
            res.value, res.unit = None, ""
        if swaps and res.status == PASS:
            res.detail = "; ".join(f"swapped with {b if a == pname else a} at {s.times[k]:.3f} s"
                                   for k, a, b in swaps if pname in (a, b))
        out.append(res)
    return out


def _in_place(job, s, prop, p, hid, k, place, caps):
    if place == "hidden":
        return bool(hid[k]), "out of sight" if hid[k] else "in sight"
    if place == "ground":
        if job.ground is None:
            return True, "no ground"
        h = p[k, 1] - float(job.ground)
        size = float(prop.get("size", 0.1))
        ok = -size <= h <= size + s.limits["death_float"]
        return ok, f"{h * 100:.0f} cm above the ground"
    places = job.spec.get("places") or {}
    if place not in places:
        raise JobError(f"unknown place {place}")
    pl = places[place]
    q = s.point(pl["point"])[k]
    d = float(np.linalg.norm(p[k] - q))
    return d <= float(pl.get("radius", 0.05)), f"{d * 100:.1f} cm from {place}"


def check_routes(job, s):
    """Each object of a route starts and ends where the script says, followed through swaps."""
    out = []
    routes = job.clips[s.name].get("routes") or {}
    props = job.spec.get("props") or {}
    if not routes:
        return out
    caps = _capsules(job, s)
    tracks, swaps = _props(job, s, caps)
    for pname in routes:
        if pname not in props:
            raise JobError(f"clip {s.name}: route of unknown prop {pname}")
    n = len(s.times)
    carrier = {name: [name] * n for name in props}        # which bone carries each object
    now = {name: name for name in props}
    by_frame = {}
    for k, a, b in swaps:
        by_frame.setdefault(k, []).append((a, b))
    for k in range(n):
        for a, b in by_frame.get(k, []):
            for obj, bone in list(now.items()):
                if bone == a:
                    now[obj] = b
                elif bone == b:
                    now[obj] = a
        for obj in props:
            carrier[obj][k] = now[obj]
    for pname, r in routes.items():
        p = np.array([tracks[carrier[pname][k]][0][k] for k in range(n)])
        hid = np.array([tracks[carrier[pname][k]][2][k] for k in range(n)])
        prop = props[pname]
        bad = []
        for when, k in (("start", 0), ("end", n - 1)):
            if when in r:
                ok, why = _in_place(job, s, prop, p, hid, k, r[when], caps)
                if not ok:
                    bad.append((k, f"{when}s {why}, the script says {r[when]}"))
        k0 = 0
        for place in r.get("via", []):
            hit = next((k for k in range(k0, n) if _in_place(job, s, prop, p, hid, k, place, caps)[0]), None)
            if hit is None:
                bad.append((n - 1, f"never passes {place}"))
                break
            k0 = hit
        moved = sorted({carrier[pname][k] for k in range(n)} - {pname})
        via = f" (carried on by {', '.join(moved)} after a swap)" if moved else ""
        if bad:
            k, why = bad[0]
            out.append(Result(s.name, "route", pname, FAIL, frame=k, time=float(s.times[k]),
                              detail="; ".join(b[1] for b in bad) + via,
                              risks=[(kk, float(s.times[kk]), 1.0, w, [p[kk]]) for kk, w in bad]))
        else:
            out.append(Result(s.name, "route", pname, PASS,
                              detail=" -> ".join([r.get("start", "?")] + r.get("via", []) + [r.get("end", "?")]) + via))
    return out


def check_penetration(job, s):
    out = []
    caps = _capsules(job, s)
    pts = {}
    for name in job.order:
        a = job.actors[name]
        for h in (a.rig or {}).get("hands", []):
            if a.model.has(h):
                pts[f"{name}:{h.lower()}"] = (s.at(name, h), None)
    own = {}                                  # a named point's own limit ("max", metres)
    for key in job.spec.get("penetration_points") or []:
        k_ = key if isinstance(key, str) else key.get("name", key["bone"])
        pts[k_] = (s.point(key), None)
        if isinstance(key, dict) and key.get("max") is not None:
            own[k_] = float(key["max"])
    props = job.spec.get("props") or {}
    for pname, prop in props.items():
        p, scale = _prop_track(job, s, prop)
        pts[f"prop {pname}"] = (p, prop)
    contacts = foot_contacts(job, s)
    n = int(s.limits["risk_frames"])
    lim = s.limits["penetration"]
    for key, (p, prop) in pts.items():
        depth = np.full(len(p), -np.inf)
        det = [""] * len(p)
        for cname, (a, b, r, spec) in caps.items():
            if key in (spec.get("allow") or []) or (prop and cname in prop.get("hide_in", [])):
                continue
            d = capsule_depth(p, a, b, r)
            for k in np.nonzero(d > depth)[0]:
                depth[k] = d[k]
                det[k] = f"{key} {d[k] * 100:.1f} cm inside {cname}"
        if job.ground is not None and prop is None:
            below = float(job.ground) - p[:, 1]
            for k in np.nonzero(below > depth)[0]:
                depth[k] = below[k]
                det[k] = f"{key} {below[k] * 100:.1f} cm below the ground"
        depth = np.where(np.isfinite(depth), np.maximum(depth, 0.0), 0.0)
        out.append(_result(s, "penetration", key, depth, own.get(key, lim), " m", det, [[q] for q in p], n=n))
    for key, p in contacts.items():
        depth = np.zeros(len(p))
        det = [""] * len(p)
        for cname, (a, b, r, spec) in caps.items():
            if key in (spec.get("allow") or []):
                continue
            d = capsule_depth(p, a, b, r)
            for k in np.nonzero(d > depth)[0]:
                depth[k] = d[k]
                det[k] = f"{key} {d[k] * 100:.1f} cm inside {cname}"
        if caps:
            out.append(_result(s, "penetration", key, depth, lim, " m", det, [[q] for q in p], n=n))
    return out


def check_lengths(job, s):
    out = []
    clip = job.clips[s.name]
    L = s.limits
    lengths = {a: c.duration for a, c in clip["anims"].items()}
    want = clip.get("duration")
    if want is not None:
        worst = max(lengths, key=lambda a: abs(lengths[a] - float(want)))
        d = abs(lengths[worst] - float(want))
        out.append(Result(s.name, "duration", "the tactics' length", FAIL if d > L["duration"] else PASS,
                          lengths[worst], float(want), " s",
                          detail=", ".join(f"{a} {v:.3f} s" for a, v in lengths.items())))
    elif len(lengths) > 1:
        spread = max(lengths.values()) - min(lengths.values())
        out.append(Result(s.name, "duration", "every actor as long", FAIL if spread > L["duration"] else PASS,
                          spread, L["duration"], " s", detail=", ".join(f"{a} {v:.3f} s" for a, v in lengths.items())))
    else:
        out.append(Result(s.name, "duration", "the tactics' length", SKIP, detail="no length given in the job"))
    loop = clip.get("loop")
    if loop is None:
        loop = bool(LOOP_NAMES.search(s.name)) and not clip.get("death")
    if not loop:
        return out
    # The seam (the last pose to the first) of every bone's local frame, against the largest step
    # between two frames inside the clip: a loop may move at its seam as fast as it moves anywhere,
    # but not jump. A clip whose ends meet has a seam of 0.
    worst, where = (0.0, 0.0, 0.0, 1.0, 1.0), ""
    for name in job.order:
        if name not in clip["anims"]:
            continue
        a = job.actors[name]
        W = s.worlds[name]
        for i, par in enumerate(a.model.parents):
            loc = [np.linalg.inv(s.places[name][k] if par < 0 else W[k, par]) @ W[k, i] for k in range(len(W))]
            rots = [rotation(m) for m in loc]
            pos = np.array([m[:3, 3] for m in loc])
            if par < 0 and clip.get("root_motion", True):
                pos[:, 2] = 0.0                          # the root may travel the way the unit faces
            steps_a = [angle_between_rotations(rots[k - 1], rots[k]) for k in range(1, len(rots))] or [0.0]
            steps_p = list(np.linalg.norm(np.diff(pos, axis=0), axis=1)) or [0.0]
            seam_a = angle_between_rotations(rots[-1], rots[0])
            seam_p = float(np.linalg.norm(pos[-1] - pos[0]))
            allow_a = max(L["loop_angle"], 1.5 * max(steps_a))
            allow_p = max(L["loop_position"], 1.5 * max(steps_p))
            ratio = max(seam_a / allow_a, seam_p / allow_p)
            if ratio > worst[0]:
                worst = (ratio, seam_a, seam_p, allow_a, allow_p)
                where = f"{name}:{a.model.names[i]}"
    ratio, seam_a, seam_p, allow_a, allow_p = worst
    last = len(s.times) - 1
    det = (f"worst {where or 'bone'}: the seam turns it {seam_a:.1f} deg (allowed {allow_a:.1f}) and moves it "
           f"{seam_p * 100:.1f} cm (allowed {allow_p * 100:.1f})")
    out.append(Result(s.name, "loop", "the seam (last pose to first)", FAIL if ratio > 1 else PASS, ratio, 1.0,
                      " of allowed", last, float(s.times[-1]), det,
                      [(0, 0.0, ratio, "first frame", []), (last, float(s.times[-1]), ratio, "last frame", [])]))
    return out


def _part_points(job, s, k):
    """{part name: points N x 3} at frame k: each actor (its mesh, else its bones) and each prop."""
    parts = {}
    props = job.spec.get("props") or {}
    prop_bones = {}
    for pname, prop in props.items():
        a, b, _ = job.point(prop.get("point", prop.get("bone")))
        prop_bones.setdefault(a, set()).add(b)
    for name in job.order:
        mesh = mesh_points(job, s, name, k)
        if mesh:
            parts[name] = np.concatenate(mesh)
        else:
            a = job.actors[name]
            keep = [i for i, n in enumerate(a.model.names) if n.lower() not in prop_bones.get(name, set())]
            parts[name] = s.worlds[name][k, keep, :3, 3]
    for pname, prop in props.items():
        p, _scale = _prop_track(job, s, prop)
        parts[f"prop {pname}"] = p[k:k + 1]
    return parts


def check_death(job, s):
    clip = job.clips[s.name]
    if not clip.get("death"):
        return []
    if job.ground is None:
        return [Result(s.name, "death", "parts on the ground", SKIP, detail="no ground in this job")]
    g = float(job.ground)
    k = len(s.times) - 1
    parts = _part_points(job, s, k)
    tol = s.limits["death_float"]
    props = job.spec.get("props") or {}
    caps = _capsules(job, s)
    hidden = set()
    for pname, prop in props.items():
        p, scale = _prop_track(job, s, prop)
        if _hidden(job, s, prop, p, scale, caps)[k]:
            hidden.add(f"prop {pname}")
    supported = {n for n, p in parts.items() if n in hidden or p[:, 1].min() - g <= tol}
    changed = True
    while changed:
        changed = False
        for n, p in parts.items():
            if n in supported:
                continue
            low = p[np.argmin(p[:, 1])]
            for m in list(supported):
                if np.min(np.linalg.norm(parts[m] - low, axis=1)) <= tol + float(props.get(n[5:], {}).get("size", 0.0)):
                    supported.add(n)
                    changed = True
                    break
    out = []
    for n, p in parts.items():
        h = float(p[:, 1].min() - g)
        lowest = p[np.argmin(p[:, 1])]
        ok = n in supported
        out.append(Result(s.name, "death", f"{n} rests", PASS if ok else FAIL, max(h, 0.0), tol, " m", k,
                          float(s.times[k]), "" if ok else f"its lowest point floats {h * 100:.0f} cm up, on nothing",
                          [] if ok else [(k, float(s.times[k]), h, f"{n} floats", [lowest])]))
    return out


def signature(job, s):
    """{actor: {bone: farthest distance from its place at the first frame}} of the bones that say
    what a clip does (a human's pelvis and feet; every bone of another actor), in the actor's own
    space: a rider's motion is measured against the bone he hangs on (getting off the saddle, not
    being carried by a camel that lies down)."""
    out = {}
    for name in job.order:
        a = job.actors[name]
        if name not in job.clips[s.name]["anims"]:
            continue
        bones = [b.lower() for b in (a.rig or {}).get("signature", []) if a.model.has(b)] or \
            [n.lower() for n in a.model.names]
        sig = {}
        inv = np.linalg.inv(s.places[name])
        for b in bones:
            w = s.at(name, b)
            p = np.einsum("nij,nj->ni", inv[:, :3, :3], w) + inv[:, :3, 3]
            sig[b] = float(np.linalg.norm(p - p[0], axis=1).max())
        out[name] = sig
    return out


def check_inventory(job, baseline, samples, base_samples):
    """Every clip of the baseline is still there, and every motion of it still happens, unless the
    job's `removed` names it ("clip" or "clip:actor", with the reason)."""
    removed = job.spec.get("removed") or {}
    L = job.limits
    out = []
    for cname in baseline.clips:
        if cname not in job.clips:
            ok = cname in removed
            out.append(Result(cname, "inventory", "clip present", PASS if ok else FAIL,
                              detail=(f"removed: {removed[cname]}" if ok else
                                      "the baseline has this clip and the job does not; name it under removed")))
            continue
        old = signature(baseline, base_samples[cname])
        new = signature(job, samples[cname])
        for actor, sig in old.items():
            key = f"{cname}:{actor}"
            if actor not in new:
                ok = key in removed or cname in removed
                out.append(Result(cname, "inventory", f"{actor} animated", PASS if ok else FAIL,
                                  detail=f"removed: {removed.get(key, removed.get(cname))}" if ok else
                                  f"{actor} had an animation in the baseline and has none now"))
                continue
            worst = None
            for bone, travel in sig.items():
                if travel < L["removed_travel"] or bone not in new[actor]:
                    continue
                share = new[actor][bone] / travel
                if worst is None or share < worst[0]:
                    worst = (share, bone, travel, new[actor][bone])
            if worst is None:
                continue
            share, bone, travel, now = worst
            gone = share < L["removed_share"]
            listed = key in removed or cname in removed
            status = PASS if (not gone or listed) else FAIL
            det = f"{actor}:{bone} travelled {travel:.2f} m in the baseline, {now:.2f} m now"
            if gone and listed:
                det += f"; removed: {removed.get(key, removed.get(cname))}"
            elif gone:
                det += "; a motion that existed is gone: name it under removed"
            out.append(Result(cname, "inventory", f"{actor} motion kept", status, share, L["removed_share"], "",
                              detail=det))
    return out


# --------------------------------------------------------------------------------------------------
# Running


LOWER_LIMITS = ("ahead",)      # checks whose limit is a least value (fail below it)

CHECKS = (check_lengths, check_look, check_hinges, check_speed, check_feet, check_cross, check_grips, check_ahead,
          check_sizes, check_mounts, check_props, check_routes, check_penetration, check_death)


class Report:
    def __init__(self, job, results, notes):
        self.job, self.results, self.notes = job, results, notes

    @property
    def failed(self):
        return [r for r in self.results if r.status == FAIL]

    @property
    def ok(self):
        return not self.failed

    def text(self, verbose=False):
        lines = [f"check_anim: {len(self.job.clips)} clip(s), actors {', '.join(self.job.order)}, "
                 f"{self.job.fps:g} frames a second"]
        lines += [f"note: {n}" for n in self.notes]
        by_clip = {}
        for r in self.results:
            by_clip.setdefault(r.clip, []).append(r)
        for clip, rs in by_clip.items():
            c = self.job.clips.get(clip)
            length = max(a.duration for a in c["anims"].values()) if c else None
            lines.append(f"clip {clip}" + (f" ({length:.3f} s)" if length is not None else ""))
            for r in rs:
                if verbose or r.status != PASS or r.check in ("duration", "loop", "route", "inventory", "death"):
                    lines.append(r.line())
            passed = sum(r.status == PASS for r in rs)
            if not verbose and passed:
                lines.append(f"  ({passed} checks passed" + ("" if verbose else "; --verbose lists them") + ")")
        risks = self.risk_frames()
        if risks:
            lines.append("risk frames (the worst frames of each failed check, then of each passed one):")
            for r in risks:
                lines.append(f"  {r['clip']:12s} {r['time']:7.3f} s  frame {r['frame']:4d}  {r['status']:4s} "
                             f"{r['check']} {r['item']}: {r['detail']}")
        nf = len(self.failed)
        lines.append(f"result: {nf} FAIL, {sum(r.status == PASS for r in self.results)} PASS, "
                     f"{sum(r.status == SKIP for r in self.results)} SKIP"
                     + (" -> the preview is refused" if nf else " -> the preview may be made"))
        return "\n".join(lines)

    def risk_frames(self, per_check=None, passed=True):
        """[{clip, frame, time, check, item, status, value, detail, points}] failed checks first."""
        out = []
        n = per_check or int(self.job.limits["risk_frames"])
        for status in (FAIL, PASS) if passed else (FAIL,):
            for r in self.results:
                if r.status != status:
                    continue
                if status == PASS and (r.value is None or r.limit in (None, 0) or
                                       (r.value > 2.0 * r.limit if r.check in LOWER_LIMITS else r.value < 0.5 * r.limit)):
                    continue                                 # passed far from its limit: no risk
                for f, t, v, d, pts in r.risks[:n]:
                    out.append({"clip": r.clip, "frame": f, "time": t, "check": r.check, "item": r.item,
                                "status": r.status, "value": v, "detail": d,
                                "points": [list(map(float, p)) for p in pts]})
        return out

    def as_dict(self):
        return {"ok": self.ok, "notes": self.notes, "results": [r.as_dict() for r in self.results],
                "risk_frames": self.risk_frames()}


def _notes(job):
    notes = []
    for name in job.order:
        a = job.actors[name]
        if not a.rig:
            continue
        missing = []
        for h in a.rig.get("hinges", []):
            missing += [h[k] for k in ("upper", "middle", "end") if not a.model.has(h[k])]
        for f in a.rig.get("look", []):
            if not a.model.has(f["bone"]):
                missing.append(f["bone"])
        for f in a.rig.get("feet", []):
            if not a.model.has(f["bone"]):
                missing.append(f["bone"])
        if a.chest() is None:
            notes.append(f"{name}: no chest bone ({', '.join(a.rig['chest'])}): look not judged")
        if missing:
            notes.append(f"{name}: the rig lacks {', '.join(sorted(set(missing)))}: their checks are skipped")
    return notes


def check(job, baseline=None, clips=None):
    """Run every check on every clip (or `clips`); `baseline` (a Job) adds the inventory check."""
    results, samples = [], {}
    for cname in job.clips:
        if clips and cname not in clips:
            continue
        s = sample(job, cname)
        samples[cname] = s
        for fn in CHECKS:
            results += fn(job, s)
    if baseline is not None:
        base_samples = {c: sample(baseline, c) for c in baseline.clips}
        results += check_inventory(job, baseline, samples, base_samples)
    rep = Report(job, results, _notes(job))
    rep.samples = samples
    return rep


def load_job(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    return Job(spec, os.path.dirname(os.path.abspath(path)))
