# SPDX-License-Identifier: GPL-3.0-or-later
"""Hammer fanning for a unit with a pistol in its right hand (by default Wars of Liberty's European
explorers): the pistol held at the hip, the left palm sweeping back over the hammer at each shot,
and its idle, made from key poses on the unit's own skeleton.

    venv\\Scripts\\python -I tools/make_fanning.py --game <game copy> --out <folder>
        [--model <art path>] [--shots 6] [--granny-helper <exe>] [--no-verify]
        [--sheet <png>] [--reference <png>] [--risks <png>]

The clips (the beat list of the request, approved before any key was set):
1. `attack` (2.2 s): starts and ends in READY (the pistol at the hip, its barrel level toward the
   target, the left palm over the hammer). For each shot the left palm goes up and ahead of the
   cylinder (A), sweeps back and down over the hammer (B: the Attack tag, the shot) and on behind it
   (C) while the pistol kicks up, then comes back over the top (R) to A for the next one. The shots
   are SHOTS evenly spaced tags; with the tactics' reload clip (2.0 s) and ROF (4.5 s) the game plays
   the clip at (2.2 + 2.0) / 4.5 = 0.933, so 0.2613 s of clip between two shots is 0.28 s of game time.
2. `idle` (2.0 s, a loop): READY, breathing (the chest and the left palm rise 1 cm, the muzzle dips
   1 degree, the head turns 5 degrees and back).

The pistol has no hammer and the hand no fingers: the hammer is measured on the pistol's mesh as the
top of its frame at the rear end of the barrel (`hammer_point`), and the sweep is read in the wrist and
forearm, bigger than a real one so that it reads from the game's camera.

What it writes below --out: `art\\<FOLDER>\\<name>.gr2` and its tag file `.gr2.precomp` (sampled from
the clip on the stock attack's tag file) for both clips; `fanning-anims.xml` (the `<anim>` blocks with
the Attack tags, for the unit's anim file); `check\\` (the model and the pistol uncompressed and the job
file of tools/check_anim.py: grips of the left palm on the hammer at each shot, the palm ahead of the
chest, the forearms out of the torso); `fanning-report.txt` (the tags, the times, the checks below).
--sheet draws the key frames of one shot from the game camera's angle, far and close; with --reference,
that image above them. --risks draws the beat list's risk frames (each shot's contact, the forearm at C,
a sweep, the kick, the jump into the reload, the idle's loop, the feet, the game camera far).

Checks (the tool exits 1 when one fails): the first and last frame of each clip equal; every arm and
hand vertex outside the body's mesh (make_pray's ray cast, at most ARM_DEPTH inside); the left palm at
most GRIP from its place over the hammer at each shot; and unless --no-verify each file read back the
same and by the game's granny2.dll through the helper of recompress_models.py.

Compressed game files are expanded by the game's own Granny runtime (`--granny-helper`, default
tools\\granny_recompress.exe); nothing of the game is stored. Refuses a Steam folder as output.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
from aoe3game import gr2, gr2_mesh  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import Animation, Rig, animation_file, matrix_quat  # noqa: E402
from aoe3game.gr2_pose import (Keys, about, axis_matrix, set_frame, transform_branch, translate,  # noqa: E402
                               two_bone_ik, unit)

MODEL = "WoL\\units\\explorers\\europeans\\british\\british_explorer"
PISTOL = "units\\spc\\custer\\spc_custer_pistol"
RELOAD_CLIP = "animation_library\\SPC\\cooper\\reload"   # the tactics' ReloadSharpshoot, for the risk sheet
STANCE = "nuggets\\outlaw_kidnap\\outlaw_pistol_attackA"   # its first frame: the stance; its tag file: the template
FOLDER = "WoL\\units\\explorers\\europeans\\fanning"
NAMES = {"attack": "explorer_fanning_attack", "idle": "explorer_fanning_idle"}
ANIMS = {"attack": "RangedAttackSharpshoot", "idle": "SharpshootIdle"}
FPS = 30
LENGTH = {"attack": 2.2, "idle": 2.0}
RELOAD, ROF = 2.0, 4.5      # the tactics' reload clip and the abilities' ROF
FIRST, STEP = 0.42, 0.2613  # the first shot and the time between two (clip seconds)
SWEEP, THROUGH, TOP = 0.08, 0.06, 0.12   # A -> B takes SWEEP before a shot; C at THROUGH and R at TOP after it
BRUSH = 1.0 / 60.0           # the palm's edge rides over the hammer from BRUSH before the shot to BRUSH after
RECOIL_DEG, RECOIL_PEAK, RECOIL_END = 14.0, 0.03, 0.13
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)

# Places of the left palm's centre, file units, from the hammer (x the unit's right, y up, z ahead).
PLACES = {"ready": (0.0, 0.11, 0.0), "A": (-0.02, 0.24, 0.16), "B": (0.0, 0.05, 0.0),
          "B-": (0.0, 0.05, 0.008), "B+": (0.0, 0.05, -0.008),
          "C": (0.02, 0.12, -0.09), "R": (-0.02, 0.35, 0.03)}
GUN = (0.16, 0.05, 0.47)      # Prop1 from the pelvis at READY: right, up, ahead (file units)
LEFT_ELBOW = (-1.0, -0.3, 0.2)      # the left elbow's pole: out to the left, a little down and ahead (the forearm clear of the belly)
RIGHT_ELBOW = (0.6, -0.7, -0.25)
TWIST = 0.0                   # the chest turned about the vertical (degrees; turning it right brought the belly into the forearm)
CROUCH, LEAN = 0.03, 5.0      # the pelvis lowered (file units) and the chest leant forward (degrees)
ARM_DEPTH = 0.035             # how deep an arm vertex may sit in the body mesh (file units)
GRIP = 0.03                   # how far the palm may be from its place over the hammer at a shot (file units)


# --------------------------------------------------------------------------------------------------
# Timing and tags (no game needed)


def rate(length=None):
    """The game's pace of the attack clip: (attack + reload) / ROF."""
    return ((LENGTH["attack"] if length is None else length) + RELOAD) / ROF


def shot_times(shots, first=FIRST, step=STEP):
    return [first + k * step for k in range(shots)]


def schedule(shots, length=None):
    """[(clip time, place)] of the left palm in the attack clip: READY, then per shot A, B (the shot),
    C, R, A; after the last shot C, then READY again."""
    length = LENGTH["attack"] if length is None else length
    times = shot_times(shots)
    out = [(0.0, "ready"), (max(0.0, times[0] - SWEEP - 0.18), "ready"), (times[0] - SWEEP, "A")]
    for k, t in enumerate(times):
        out.append((t - BRUSH, "B-"))
        out.append((t + BRUSH, "B+"))
        out.append((t + THROUGH, "C"))
        if k + 1 < len(times):
            out.append((t + TOP, "R"))
            out.append((times[k + 1] - SWEEP, "A"))
    out.append((min(length - 0.15, times[-1] + THROUGH + 0.26), "ready"))
    out.append((length, "ready"))
    return out


def recoil_keys(shots):
    """[(clip time, degrees)] of the pistol's kick: 0 at each shot, RECOIL_DEG soon after, 0 again."""
    out = [(0.0, 0.0)]
    for t in shot_times(shots):
        out += [(t, 0.0), (t + RECOIL_PEAK, RECOIL_DEG), (t + RECOIL_END, 0.0)]
    out.append((LENGTH["attack"], 0.0))
    return out


def tag_lines(shots, length=None):
    """The `<tag>` lines of the attack clip: per shot Attack, the shot's sound and the muzzle flash,
    as the unit's anim file has them today (fractions of the clip)."""
    length = LENGTH["attack"] if length is None else length
    out = []
    for t in shot_times(shots):
        u = t / length
        out.append(f'\t\t\t<tag type="Attack">{u:.3f}</tag>')
        out.append(f'\t\t\t<tag type="SpecificSoundSet" checkvisible="1" set="PistolShot">{u:.3f}</tag>')
        out.append(f'\t\t\t<tag type="Particles" particlename="musketshot">{u + 0.01:.3f}</tag>')
    return out


def anim_blocks(shots):
    lines = ["<!-- Generated by aoe3-blender-tools tools/make_fanning.py. They replace the unit's "
             "RangedAttackSharpshoot and add SharpshootIdle. PREVIEW: not tested in game. -->"]
    for clip in ("attack", "idle"):
        lines += [f"\t<anim>\n\t\t{ANIMS[clip]}\n\t\t<assetreference type=\"GrannyAnim\">",
                  f"\t\t\t<file>{FOLDER}\\{NAMES[clip]}</file>"]
        if clip == "attack":
            lines += tag_lines(shots)
        lines += ["\t\t</assetreference>", "\t\t<component>ModelComp</component>",
                  "\t\t<attach a=\"pistol\" frombone=\"Bip01_AttachRt\" tobone=\"bip01 Prop1\" syncanims=\"0\"/>",
                  "\t</anim>"]
    return "\n".join(lines) + "\n"


def hammer_point(vertices):
    """The pistol's 'hammer' in its model space: the top of the frame at the rear end of the barrel.
    The barrel runs along +y (the muzzle) with the grip below it (-z): the top is the highest z, the
    rear the lowest y among the top's vertices."""
    v = np.asarray(vertices, np.float64)
    top = v[:, 2].max()
    strip = v[v[:, 2] > top - 0.03]
    barrel = strip[strip[:, 1] > v[:, 1].min() + 0.25 * (v[:, 1].max() - v[:, 1].min())]
    if len(barrel) == 0:
        barrel = strip
    return np.array([barrel[:, 0].mean(), barrel[:, 1].min(), top])


# --------------------------------------------------------------------------------------------------
# The unit


class Unit:
    """The unit's skeleton and mesh (make_pray's Body: palms, feet), the stance, the pistol on Prop1
    and its hammer."""

    def __init__(self, model_data, stance_anim, pistol_vertices, hand_to_prop):
        import make_pray as mp
        self.mp = mp
        self.rig = Rig.of(gr2.load(model_data).root())
        read = gr2_mesh.read(model_data)
        self.units_per_meter = float(read.get("units_per_meter") or 1.0)
        base = self.rig.by_name(self.rig.pose(stance_anim, 0.0))
        self.stance = stance_anim
        self.body = mp.Body(self.rig, {"mesh": read["meshes"][0], "skel": read["skeletons"][0]}, base)
        self.base = base
        self.hand_to_prop = hand_to_prop
        self.hammer_local = hammer_point(pistol_vertices)
        self.pelvis = base["bip01 pelvis"][:3, 3].copy()
        self.rest = self.rig.by_name(self.rig.rest_worlds())

    @classmethod
    def from_game(cls, game, model=MODEL):
        data = game.granny(model)
        stance = Animation.load(game.granny(STANCE))
        rig = Rig.of(gr2.load(data).root())
        base = rig.by_name(rig.pose(stance, 0.0))
        h2p = np.linalg.inv(rigid(base["bip01 r hand"])) @ rigid(base["bip01 prop1"])
        pis = gr2_mesh.read(game.granny(PISTOL))
        verts = mesh_points(pis)
        u = cls(data, stance, verts, h2p)
        u.model_data, u.pistol_data = data, game.granny(PISTOL)
        return u

    def gun_frame(self, recoil=0.0, kick=0.0, dip=0.0):
        """Prop1's world frame: the barrel (the pistol's +y) toward +z, its top (+z) up, at GUN from the
        pelvis; `recoil` degrees muzzle up, `kick` file units back, `dip` degrees muzzle down."""
        rot = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
        rot = axis_matrix(X, -(recoil - dip)) @ rot
        m = np.eye(4)
        m[:3, :3] = rot
        m[:3, 3] = self.pelvis + np.array(GUN) + np.array([0.0, -CROUCH, -kick])
        return m

    def hammer(self, frame):
        return (frame @ np.r_[self.hammer_local, 1.0])[:3]

    def ready_hammer(self):
        return self.hammer(self.gun_frame())

    def palm_place(self, name):
        return self.ready_hammer() + np.array(PLACES[name])

    def pose(self, c):
        """A pose from the channels: crouch, lean and twist of the chest, the legs in the stance, the
        right hand holding the pistol at `gun` (its frame), the left palm at `lpalm` (world)."""
        b, rig, mp = self.body, self.rig, self.mp
        P = dict(self.base)
        P = translate(P, rig, "bip01", np.array([0.0, -c["crouch"], 0.0]))
        spine = P["bip01 spine"][:3, 3]
        turn = axis_matrix(Y, c["twist"]) @ axis_matrix(X, c["lean"])
        P = transform_branch(P, rig, "bip01 spine", about(spine, turn))
        # the neck and the head as at rest on the chest (the stance's head is turned 32 degrees to one
        # side), then the chest's turn and lean taken back, so the eyes are on the target, plus its own turn
        chest = P["bip01 spine1"] @ np.linalg.inv(self.rest["bip01 spine1"])
        for bone in ("bip01 neck", "bip01 head"):
            want = chest @ self.rest[bone]
            frame = P[bone].copy()
            frame[:3, :3] = want[:3, :3]
            P = set_frame(P, rig, bone, frame)
        neck = P["bip01 neck"][:3, 3]
        back = axis_matrix(Y, -c["twist"] + c["head"]) @ axis_matrix(X, -c["lean"])
        P = transform_branch(P, rig, "bip01 neck", about(neck, back))
        for s in mp.SIDES:
            thigh, calf, foot = mp.LEG[s]
            P = two_bone_ik(P, rig, thigh, calf, foot, self.base[foot][:3, 3], self._knee(s), b.hinge[thigh],
                            b.hinge[calf], end_frame=self.base[foot][:3, :3])
        hw = c["gun"] @ np.linalg.inv(self.hand_to_prop)
        rot = hw[:3, :3]
        palm = (hw @ np.r_[b.palm_local["r"], 1.0])[:3]
        P = b.place_hand(P, "r", palm, rot @ b.finger_local["r"], rot @ b.normal_local["r"], unit(RIGHT_ELBOW))
        P = b.place_hand(P, "l", c["lpalm"], unit((1.0, -0.15, 0.35)), np.array([0.0, -1.0, 0.0]),
                         unit(LEFT_ELBOW))
        for m in mp.MARKERS:
            if m in P:
                P = set_frame(P, rig, m, self.base[m])
        return P

    def _knee(self, s):
        hip, knee, ankle = (self.base[n][:3, 3] for n in self.mp.LEG[s])
        line = unit(ankle - hip)
        off = (knee - hip) - ((knee - hip) @ line) * line
        return unit(off) if np.linalg.norm(off) > 1e-3 else np.array(Z)

    # -- the clips

    def channels_at(self, keys, t):
        c = keys.at(t)
        gun = self.gun_frame(c["recoil"], c["kick"], c["dip"])
        return {"crouch": CROUCH, "lean": LEAN + c["breath"] * 1.5, "twist": TWIST,
                "head": c["head"], "gun": gun, "lpalm": np.asarray(c["lpalm"], np.float64)}

    def attack_keys(self, shots):
        palm = {}
        for t, place in schedule(shots):
            palm[round(t, 6)] = self.palm_place(place)
        rec = dict(recoil_keys(shots))
        times = sorted(set(palm) | set(rec))
        keys = []
        for t in times:
            keys.append((t, {"lpalm": palm.get(t, None), "recoil": rec.get(t, None)}))
        # fill the missing values by linear interpolation of their own keys: Keys wants every channel
        # at every key time
        kick_of = {t: v / RECOIL_DEG * 0.02 for t, v in rec.items()}
        return Keys(_complete(keys, {"kick": kick_of}, {"breath": 0.0, "head": 0.0, "dip": 0.0}))

    def idle_keys(self):
        ready = self.palm_place("ready")
        length = LENGTH["idle"]
        up = ready + np.array([0.0, 0.01, 0.0])
        return Keys([(0.0, {"lpalm": ready, "recoil": 0.0, "kick": 0.0, "breath": 0.0, "head": 0.0, "dip": 0.0}),
                     (length / 2, {"lpalm": up, "recoil": 0.0, "kick": 0.0, "breath": 1.0, "head": 5.0,
                                   "dip": 1.0}),
                     (length, {"lpalm": ready, "recoil": 0.0, "kick": 0.0, "breath": 0.0, "head": 0.0,
                               "dip": 0.0})])

    def sample(self, keys, length, fps=FPS):
        n = max(2, int(round(length * fps)) + 1)
        times = np.linspace(0.0, length, n)
        return times, [self.pose(self.channels_at(keys, float(t))) for t in times]

    def clip_bytes(self, name, times, poses):
        frames = [self.rig.localise(p) for p in poses]
        tracks = []
        for i, bone in enumerate(self.rig.names):
            tracks.append((bone, times, np.array([f[i][0] for f in frames]), np.array([f[i][1] for f in frames])))
        return animation_file(name, float(times[-1]), self.rig.names[0], tracks, basis=self.rig.basis,
                              accumulation=self.stance.accumulation, timestep=self.stance.timestep, source=name)

    def palm_world(self, P, side="l"):
        return (P[f"bip01 {side} hand"] @ np.r_[self.body.palm_local[side], 1.0])[:3]


def _complete(keys, derived, constants):
    """Keys with every channel at every time: a channel missing at a time takes the value interpolated
    linearly between its neighbours; `derived` {channel: {time: value}} likewise; `constants` as is."""
    times = [t for t, _ in keys]
    chans = {}
    for name in keys[0][1]:
        known = [(t, v[name]) for t, v in keys if v[name] is not None]
        chans[name] = known
    for name, d in derived.items():
        chans[name] = sorted(d.items())
    out = []
    for t in times:
        c = {}
        for name, known in chans.items():
            c[name] = _lerp(known, t)
        c.update(constants)
        out.append((t, c))
    return out


def _lerp(known, t):
    ts = [k for k, _ in known]
    if t <= ts[0]:
        return known[0][1]
    if t >= ts[-1]:
        return known[-1][1]
    for (t0, v0), (t1, v1) in zip(known, known[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return np.asarray(v0) * (1 - u) + np.asarray(v1) * u if not np.isscalar(v0) else v0 + (v1 - v0) * u
    return known[-1][1]


def rigid(m):
    m = np.array(m, np.float64)
    u, _s, vt = np.linalg.svd(m[:3, :3])
    m[:3, :3] = u @ vt
    return m


def mesh_points(read):
    pts = [np.asarray(m["file_positions"], np.float64) for m in read["meshes"]]
    return np.concatenate(pts, 0)


# --------------------------------------------------------------------------------------------------
# Checks, tag files, the job of check_anim


def seam(a, b):
    return max(float(np.abs(a[k] - b[k]).max()) for k in a)


def check(unit, clip, times, poses, shots, keys=None):
    """{check: (value, limit, ok)} of one clip; the palm at the shots is posed at their exact times."""
    out = {"first and last frame": (seam(poses[0], poses[-1]), 1e-4, None)}
    worst, at = 0.0, 0.0
    b = unit.body
    for t, p in zip(times, poses):
        pts = b.points(p)
        deep = max((d for _i, d in b.inside(pts, p)), default=0.0)
        if deep > worst:
            worst, at = deep, float(t)
    out[f"arm vertex inside the body (worst at {at:.3f} s)"] = (worst, ARM_DEPTH, None)
    if clip == "attack":
        far = 0.0
        for t in shot_times(shots):
            P = unit.pose(unit.channels_at(keys, t)) if keys is not None else poses[int(round(t * FPS))]
            far = max(far, float(np.linalg.norm(unit.palm_world(P) - unit.palm_place("B"))))
        out["left palm from its place over the hammer at the shots"] = (far, GRIP, None)
    return {k: (v, lim, v <= lim) for k, (v, lim, _o) in out.items()}


def precomp_bytes(template, length, pose_at):
    """The tag file of a clip: the template's tags (the stock attack's: HEAD, the clavicles, arms,
    hands, PELVIS, SPINE, SPINE1, the legs, PROP1, PROP2) sampled from the clip, ten keys a second."""
    from aoe3game import precomp
    import struct as st
    pre = precomp.load(template)
    keys = max(2, int(round(length * 10)) + 1)
    times = np.linspace(0.0, length, keys)
    poses = [pose_at(float(t)) for t in times]
    for index, tracks in pre.mapping:
        bone = "bip01 " + pre.names[index].lower()
        if bone not in poses[0]:
            continue
        for tr in tracks:
            pre.positions[tr] = [tuple(float(v) for v in P[bone][:3, 3]) for P in poses]
            pre.rotations[tr] = [st.pack("<4f", *matrix_quat(rigid(P[bone])[:3, :3])) for P in poses]
    for tr in range(len(pre.positions)):
        if len(pre.positions[tr]) != keys:
            pre.positions[tr] = [pre.positions[tr][0]] * keys
            pre.rotations[tr] = [pre.rotations[tr][0]] * keys
    pre.duration = float(length)
    return pre.encode()


def job_spec(unit, shots, model_file, pistol_file, clip_files):
    """The job of tools/check_anim.py (its space: metres, units / UnitsPerMeter)."""
    m = 1.0 / unit.units_per_meter
    b = unit.body
    rest = unit.base
    hammer_in_prop = unit.hammer_local
    over = (np.linalg.inv(unit.gun_frame()) @ np.r_[unit.palm_place("B"), 1.0])[:3]
    fore = {}
    for s in ("l", "r"):
        a, h = rest[f"bip01 {s} forearm"], rest[f"bip01 {s} hand"]
        fore[s] = (np.linalg.inv(a) @ np.r_[h[:3, 3], 1.0])[:3]
    pen = []
    for s, side in (("l", "left"), ("r", "right")):
        for share in (0.0, 0.25, 0.5, 0.75):
            pen.append({"name": f"{side} forearm {int(share * 100)} %", "bone": f"explorer:bip01 {s} forearm",
                        "offset": [float(v * share * m) for v in fore[s]]})
    pen.append({"name": "left palm", "bone": "explorer:bip01 l hand", "offset": [float(v * m) for v in b.palm_local["l"]]})
    belly = belly_radius(unit) * m
    tag_frames = [[round(t - BRUSH, 4), round(t + BRUSH, 4)] for t in shot_times(shots)]
    return {
        "fps": FPS, "ground": 0.0,
        "actors": {"explorer": {"model": model_file, "rig": "human"},
                   "pistol": {"model": pistol_file, "attach": {"to": "explorer", "bone": "bip01 prop1"}}},
        "clips": {"attack": {"anims": {"explorer": clip_files["attack"]}, "duration": LENGTH["attack"], "loop": False},
                  "idle": {"anims": {"explorer": clip_files["idle"]}, "duration": LENGTH["idle"], "loop": True}},
        "grips": [{"name": "left palm on the hammer at each shot", "clips": ["attack"],
                   "hand": {"bone": "explorer:bip01 l hand", "offset": [float(v * m) for v in b.palm_local["l"]]},
                   "grip": {"bone": "explorer:bip01 prop1", "offset": [float(v * m) for v in over]},
                   "frames": tag_frames}],
        "ahead": [{"name": "left palm ahead of the chest", "point": {"bone": "explorer:bip01 l hand",
                                                                    "offset": [float(v * m) for v in b.palm_local["l"]]},
                   "of": "explorer:bip01 spine1", "min": round(0.12 * m, 4)}],
        "capsules": [{"name": "belly", "a": "explorer:bip01 pelvis", "b": "explorer:bip01 spine1",
                      "radius": round(belly, 4)}],
        "penetration_points": pen,
        "removed": {"attack:explorer": "REMOVED: the outlaw's borrowed clip (outlaw_pistol_attackA) is no longer the "
                                       "explorer's RangedAttackSharpshoot; the arm held out at shoulder height; the "
                                       "tags at 0.35 / 0.50 / 0.65. Replaced by this clip, as the script says."},
        "hammer_in_prop1": [float(v * m) for v in hammer_in_prop],
    }


def belly_radius(unit):
    """The torso's half depth in front of its axis (pelvis to the top of the spine), from the mesh at
    rest: the 70th percentile of the torso vertices' distance from that axis (file units)."""
    b = unit.body
    rest = unit.rig.by_name(unit.rig.rest_worlds())
    pts = np.asarray(b.mesh["mesh"]["file_positions"], np.float64)
    torso = np.isin(b.dominant, ["bip01 pelvis", "bip01 spine", "bip01 spine1"])
    a, c = rest["bip01 pelvis"][:3, 3], rest["bip01 spine1"][:3, 3]
    axis = (c - a) / np.linalg.norm(c - a)
    rel = pts[torso] - a
    off = rel - np.outer(rel @ axis, axis)
    return float(np.percentile(np.linalg.norm(off, axis=1), 70))


# --------------------------------------------------------------------------------------------------
# Pictures


def _items(figs, P):
    exp, pis = figs
    return exp.items(P) + pis.items({}, rigid(P["bip01 prop1"]))


def _tile(img, label, width):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, width, 14], fill=(30, 30, 30))
    d.text((4, 2), label, fill=(255, 255, 255))
    return np.asarray(im)


def sheet(path, unit, figs, pose_at, reference=None, w=240):
    """The key frames of one shot (READY, A, B, C, R) seen from the game camera's angle (about 50
    degrees down) far (as the game shows the unit) and nearer, and close on the hands from two sides;
    with `reference`, that image above them."""
    import retarget_anims as ra
    from PIL import Image
    t1 = FIRST + STEP
    picks = [("READY", 0.0), ("A", t1 - SWEEP), ("B: the shot", t1), ("C", t1 + THROUGH), ("R", t1 + TOP)]
    hammer = tuple(unit.ready_hammer() + np.array([-0.08, 0.05, 0.0]))
    tiles = []
    for label, t in picks:
        items = _items(figs, pose_at(t))
        col = []
        for name, az, el, span, ctr in (("game camera, far", -35, 50, 7.0, (0.0, 0.9, 0.3)),
                                        ("game camera", -35, 50, 3.0, (0.0, 1.0, 0.3)),
                                        ("close, front left", -20, 40, 1.0, hammer),
                                        ("close, right", 70, 15, 1.0, hammer)):
            img = ra.draw(items, width=w, height=w, azimuth=az, elevation=el, span=span, centre=ctr).astype(np.uint8)
            col.append(_tile(img, f"{label}  {t:.3f} s  {name}", w))
        tiles.append(np.concatenate(col, 0))
    out = Image.fromarray(np.concatenate(tiles, 1))
    if reference:
        ref = Image.open(reference).convert("RGB")
        ref = ref.resize((out.width, int(ref.height * out.width / ref.width)))
        both = Image.new("RGB", (out.width, ref.height + out.height), (255, 255, 255))
        both.paste(ref, (0, 0))
        both.paste(out, (0, ref.height))
        out = both
    out.save(path)


def script_risks(path, unit, figs, pose_at, idle_at, reload_first=None, w=220):
    """The risk frames of the beat list, two sides each: 1 the first shot (the palm on the hammer),
    2 C of the third shot (the forearm clear of the belly), 3 the middle of a sweep, 4 the kick's
    peak, 5 the clip's last frame beside the reload's first (the jump into the reload), 6 the idle's
    first, middle and last frame, 7 the whole body (feet), 8 the game camera, far, at a shot and at R.
    Each tile says its time and the left palm's distance from its place over the hammer."""
    import retarget_anims as ra
    from PIL import Image
    t = shot_times(6)
    hammer = tuple(unit.ready_hammer() + np.array([-0.08, 0.05, 0.0]))
    near = ((-20, 40, 1.0, hammer), (70, 15, 1.0, hammer))
    top = ((-75, 55, 1.3, hammer), (-90, 10, 1.3, hammer))   # the gap between the forearm and the belly
    body = ((-35, 12, 3.0, (0.0, 1.0, 0.3)), (-110, 12, 3.0, (0.0, 1.0, 0.3)))
    far = ((-35, 50, 7.0, (0.0, 0.9, 0.3)), (-35, 50, 4.0, (0.0, 1.0, 0.3)))

    def panel(n, label, P, views):
        palm = float(np.linalg.norm(unit.palm_world(P) - unit.palm_place("B")))
        ims = [_tile(ra.draw(_items(figs, P), width=w, height=w, azimuth=az, elevation=el, span=sp,
                             centre=ct).astype(np.uint8), f"{n} {label}" if i == 0 else f"palm-hammer {palm * 100:.1f} cm",
                     w) for i, (az, el, sp, ct) in enumerate(views)]
        return np.concatenate(ims, 0)

    rows = [[panel(1, f"shot 1 {t[0]:.3f}s", pose_at(t[0]), near),
             panel(2, f"C shot 3 {t[2] + THROUGH:.3f}s, left side", pose_at(t[2] + THROUGH), top),
             panel(3, f"mid sweep {t[1] - SWEEP / 2:.3f}s", pose_at(t[1] - SWEEP / 2), near),
             panel(4, f"kick peak {t[3] + RECOIL_PEAK:.3f}s", pose_at(t[3] + RECOIL_PEAK), near),
             panel(5, "last frame 2.200s", pose_at(LENGTH["attack"]), body)]]
    second = []
    if reload_first is not None:
        second.append(panel(5, "reload frame 0", reload_first, body))
    second += [panel(6, "idle 0.0s", idle_at(0.0), body), panel(6, "idle 1.0s", idle_at(1.0), body),
               panel(6, "idle 2.0s", idle_at(LENGTH["idle"]), body),
               panel(7, "feet 1.204s", pose_at(t[3]), ((0, 5, 3.0, (0.0, 0.6, 0.3)), (-90, 5, 3.0, (0.0, 0.6, 0.3)))),
               panel(8, "far: shot 2", pose_at(t[1]), far), panel(8, "far: R", pose_at(t[1] + TOP), far)]
    width = max(len(rows[0]), len(second)) * w
    lines = []
    for r in (rows[0], second):
        img = np.concatenate(r, 1)
        pad = np.full((img.shape[0], width - img.shape[1], 3), 255, np.uint8)
        lines.append(np.concatenate([img, pad], 1))
    Image.fromarray(np.concatenate(lines, 0)).save(path)


# --------------------------------------------------------------------------------------------------


def build(unit, shots):
    """{clip: (times, poses)}"""
    return {"attack": unit.sample(unit.attack_keys(shots), LENGTH["attack"]),
            "idle": unit.sample(unit.idle_keys(), LENGTH["idle"])}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--shots", type=int, default=6)
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--no-verify", action="store_true", help="skip the read-back and the runtime checks")
    ap.add_argument("--sheet")
    ap.add_argument("--reference")
    ap.add_argument("--risks")
    args = ap.parse_args(argv)
    try:
        refuse_steam(args.out)
        for p in (args.sheet, args.risks):
            if p:
                refuse_steam(p)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if not 1 <= args.shots <= 7 or shot_times(args.shots)[-1] + THROUGH + 0.26 > LENGTH["attack"] - 0.05:
        print("--shots takes 1 to 6 (the clip is 2.2 s)", file=sys.stderr)
        return 2
    import make_dismount as md
    work = tempfile.mkdtemp(prefix="fanning_work_")
    failed, report = False, []
    try:
        game = md.Game(args.game, args.granny_helper, work)
        unit = Unit.from_game(game, args.model)
        clips = build(unit, args.shots)
        folder = os.path.join(args.out, "art", FOLDER)
        check_dir = os.path.join(args.out, "check")
        os.makedirs(folder, exist_ok=True)
        os.makedirs(check_dir, exist_ok=True)
        template = game.raw(STANCE, ".gr2.precomp")
        runtime = None
        if not args.no_verify:
            import recompress_models as rm
            runtime = rm.Runtime(args.granny_helper, os.path.join(args.game, "granny2.dll"), work)
        clip_files = {}
        report.append(f"rate (2.2 + {RELOAD}) / {ROF} = {rate():.4f}: 1 s of clip = {1 / rate():.4f} s of game time")
        for t in shot_times(args.shots):
            report.append(f"shot at {t:.4f} s of clip = {t / LENGTH['attack']:.3f} of it = {t / rate():.3f} s real")
        for clip in ("attack", "idle"):
            times, poses = clips[clip]
            data = unit.clip_bytes(NAMES[clip], times, poses)
            with open(os.path.join(folder, NAMES[clip] + ".gr2"), "wb") as f:
                f.write(data)
            keys = unit.attack_keys(args.shots) if clip == "attack" else unit.idle_keys()
            pre = precomp_bytes(template, LENGTH[clip], lambda t, k=keys: unit.pose(unit.channels_at(k, t)))
            with open(os.path.join(folder, NAMES[clip] + ".gr2.precomp"), "wb") as f:
                f.write(pre)
            shutil.copyfile(os.path.join(folder, NAMES[clip] + ".gr2"), os.path.join(check_dir, NAMES[clip] + ".gr2"))
            clip_files[clip] = NAMES[clip] + ".gr2"
            for name, (v, lim, ok) in check(unit, clip, times, poses, args.shots, keys).items():
                report.append(f"{clip}: {name}: {v:.4f} (limit {lim}) {'ok' if ok else 'FAIL'}")
                failed |= not ok
            if runtime is not None:
                a = Animation.load(data)
                worst = max(seam(p, unit.rig.by_name(unit.rig.pose(a, float(t)))) for t, p in zip(times, poses))
                import make_pray as mp
                crc, read, packed = mp.runtime_check(data, runtime, NAMES[clip])
                ok = worst < 1e-3 and crc and read
                report.append(f"{clip}: read back {worst:.1e}, runtime crc {crc}, read {read}, oodle1 {packed} B "
                              f"{'ok' if ok else 'FAIL'}")
                failed |= not ok
        with open(os.path.join(check_dir, "explorer.gr2"), "wb") as f:
            f.write(unit.model_data)
        with open(os.path.join(check_dir, "pistol.gr2"), "wb") as f:
            f.write(unit.pistol_data)
        with open(os.path.join(check_dir, "fanning-job.json"), "w", encoding="utf-8") as f:
            json.dump(job_spec(unit, args.shots, "explorer.gr2", "pistol.gr2", clip_files), f, indent=1)
        with open(os.path.join(args.out, "fanning-anims.xml"), "w", encoding="utf-8") as f:
            f.write(anim_blocks(args.shots))
        if args.sheet or args.risks:
            import retarget_anims as ra
            figs = (ra.Figure(game, args.model), ra.Figure(game, PISTOL))
            ak, ik = unit.attack_keys(args.shots), unit.idle_keys()

            def pose_at(t):
                return unit.pose(unit.channels_at(ak, t))

            def idle_at(t):
                return unit.pose(unit.channels_at(ik, t))
            if args.sheet:
                sheet(args.sheet, unit, figs, pose_at, args.reference)
            if args.risks:
                reload_anim = Animation.load(game.granny(RELOAD_CLIP))
                first = unit.rig.by_name(unit.rig.pose(reload_anim, 0.0))
                script_risks(args.risks, unit, figs, pose_at, idle_at, first)
        with open(os.path.join(args.out, "fanning-report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print("\n".join(report))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("FAIL" if failed else "all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
