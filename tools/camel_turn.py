# SPDX-License-Identifier: GPL-3.0-or-later
"""The deployed camels' turn on the spot: the TURN section of their aim files, its checks and preview.

A deployed camel (the gatling camel's B variant on foot, the zamburak cannon) whose target leaves its gun's
arc is turned by the game at once; the turretArc key of the DLL shows that turn at a walking pace instead,
turning the camel model's root bone back by the difference, and poses the body and the gunner from the
aim file's TURN section, blended over what the deployed clip samples by how far the camel has risen.
This tool writes that section (appended to the shipped aim file, whose bytes before it are kept), bakes
complete turns with a replica of the DLL's sampler, and writes the check_anim job and the preview.

The turn (approved 2026-11-27, revised the same day): the camel rises rump-high, as a camel getting up
(hind legs nearly straight, front legs bent standing on their hooves, the body tipped PITCH degrees, the
neck brought back forward), steps round its origin by diagonal pairs (the pair on the side it turns toward
first, so no hoof crosses another), one cycle every CAMEL_STEP degrees (twice in a TURN step of STEP),
each hoof lifted HOOF_LIFT, and settles back into the kush. As it rises the gunner turns to face his path
(the tangent of his circle about the origin, the way the camel turns) and walks along the circle with the
game's own walk (WALK_CLIP, one full cycle a TURN step, its stride bent onto the circle and scaled so a
planted foot stays put), then turns back to his station as it settles. The gatling gunner lets go of the
long handles to walk and takes them again; the zamburak's hands stay on his hips.

The contract with the DLL (src/features/turretarc.cpp, ReadAim's "TURN"): b"TURN", u32 1, f32 step
(degrees), f32 rise and settle (seconds), f32 rate (degrees a second), u32 points per step, then the
body's part and the gunner's, each u32 bone count, the names (32 B, NUL padded) and float32
[way 2][point][bone][7]: local position and rotation (x, y, z, w) in the parent's frame, as the aim
tables hold the gunner's and the clips' tracks hold the camel's (its sampled scale/shear taken out).
Way 0 turns toward a growing heading (atan2(x, z) of the forward: toward the unit's right), way 1 the
other way. A point p of a step is the pose once the model has turned p * STEP: the planted feet turned
back by that angle about the model's origin (the point the game turns the unit about), so they stay
put on the ground while the root turns on; point 0 equals a whole step later (every foot down).

    python -I tools/camel_turn.py --game <WoL copy> --pack <things-new wol-fixes> --out <folder>

Then the RISE section (read by the DLL since 2026-11-27, version 2 only): b"RISE", u32 2, u32 K, then for
the body's part and the gunner's, with TURN's bones in TURN's order, float32 [way 2][K][bone][7]: the pose
at lift (k + 1) / K for that way (way = the turn's sign, as TURN's), rising from the kush into TURN[way]'s
point 0 (which the last equals), the hooves kept above the ground and the rump leading, the gunner turning
to face his path (which differs by way). A plain blend from the kush to the risen
pose drives the front hooves 22 cm and the hind 9 cm into the ground halfway (the legs unfold faster than the
body rises). Semantics for a lift l < 1: x = l * K, k = floor(x); the pose is blend(k == 0 ? the clip's : RISE[k -
1], RISE[k], x - k); while it settles from point p of a step, each bone also takes l of TURN(p)'s offset from
TURN(0): position + l * (TURN(p) - TURN(0)), rotation nlerp(identity, TURN(p) * conj(TURN(0)), l) * that pose's.

Reads only. Refuses a Steam folder as output.
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))

STEP = 60.0               # degrees of turn per TURN step: the camel's cycle CAMEL_STEP twice, the walk WALK_CYCLES
CAMEL_STEP = 60.0         # degrees of the camel's own cycle (both diagonal pairs once; 30 before the review of
                          # 2026-11-27: "minipasitos")
RISE = 0.45               # seconds (0.3 approved; 0.45 so the gunner's about-face of up to 150 degrees stays under
SETTLE = 0.45             # seconds  1500 deg/s at the feet)
RATE = 90.0               # degrees a second
POINTS = 48               # points per step in the table (24 per camel cycle)
FPS = 30
HOOF_LIFT = 0.22          # metres a swinging hoof rises at mid-swing, as in the camel's walk
HOOF_CURL = 35.0          # degrees a swinging hoof folds back (toe trailing) at mid-swing
FOOT_LIFT = 0.05          # metres a foot lifts as the gunner turns to face his path or back
PITCH = 15.0              # degrees the rump-high body tips nose down (about the pelvis; 32 before 2026-11-27)
HIND_DROP = 0.18          # metres the body is lowered from the standing idle
TURN_VERSION = 1
RISE_VERSION = 2
RISE_POINTS = 16          # the rise's poses, at lift 1/16 .. 16/16
RUMP_FIRST = 12.0         # degrees the rump leads the chest at mid-rise (it rises hind legs first)
HOOF_CLEAR = 0.015        # metres a hoof's lowest point keeps above the ground while it rises or settles
SETTLE_MODE = {"body": "offset", "gunner": "offset"}  # how each part settles from a turn that ends mid-step: the
                                                      # DLL's offset rule ("blend" was tried for the walking gunner)
WALK_CLIP = "range\\march_rifleman"  # the game's walk the tools put on this gunner on foot (arms swinging free);
                                     # the cinematic walks (IGC) fold his body over on this rig
WALK_CYCLES = 1           # the walk's full cycles (two steps) per TURN step
WALK_SAMPLES = 96         # samples of one walk cycle
NEAR_GROUND = 0.03        # metres: a walking foot this near the ground is set flat (heel strike, stance, toe-off)
FLAT_RAMP = 12            # samples over which a foot flattens before touchdown and lifts its heel after

BODY_BONES = ["HS Bone Master", "HS Bone Chest", "HS Bone Stomach", "HS Bone Pelvis",
              "HS Bone Hip Lt", "HS Bone Leg Lt", "HS Bone Shin Lt", "HS Bone Hoof Back Lt",
              "HS Bone Hip Rt", "HS Bone Leg Rt", "HS Bone Shin Rt", "HS Bone Hoof Back Rt",
              "HS Bone Clavicle Lt", "HS Bone Shoulder Lt", "HS Bone Arm Lt", "HS Bone Forearm Lt", "HS Bone Hoof Frnt Lt",
              "HS Bone Clavicle Rt", "HS Bone Shoulder Rt", "HS Bone Arm Rt", "HS Bone Forearm Rt", "HS Bone Hoof Frnt Rt",
              "HS Bone Neck Lower", "HS Bone Neck Upper", "HS Bone Head", "bone attachpoint"]
HELD = {"bone attachpoint"}  # body bones held where the deployed clip's first frame has them on their parent
GUNNER_LEGS = ["Bip01 Root", "Bip01 Pelvis", "Bip01 Spine", "Bip01 R Thigh", "Bip01 R Calf", "Bip01 R Foot", "Bip01 L Thigh", "Bip01 L Calf",
               "Bip01 L Foot"]
GUNNER_ARMS = ["Bip01 Spine1", "Bip01 Neck", "Bip01 L Clavicle", "Bip01 R Clavicle", "Bip01 L UpperArm", "Bip01 L ForeArm", "Bip01 L Hand", "Bip01 R UpperArm", "Bip01 R ForeArm",
               "Bip01 R Hand"]
FRONT = ("hs bone arm", "hs bone forearm", "hs bone hoof frnt")
BACK = ("hs bone leg", "hs bone shin", "hs bone hoof back")


# --------------------------------------------------------------------------------------------------
# The section


def name32(s):
    b = s.encode("ascii")[:31]
    return b + b"\0" * (32 - len(b))


def turn_section(step, rise, settle, rate, body, gunner):
    """The TURN section's bytes. `body` and `gunner`: (bone names, array [2][points][bones][7])."""
    points = np.asarray(body[1]).shape[1]
    out = [b"TURN", struct.pack("<I4fI", TURN_VERSION, step, rise, settle, rate, points)]
    for names, data in (body, gunner):
        data = np.asarray(data, np.float32)
        if data.shape != (2, points, len(names), 7):
            raise ValueError(f"part data {data.shape}, expected (2, {points}, {len(names)}, 7)")
        out += [struct.pack("<I", len(names))] + [name32(n) for n in names] + [data.astype("<f4").tobytes()]
    return b"".join(out)


def rise_section(body, gunner):
    """The RISE section's bytes: `body` and `gunner` arrays [way 2][K][bones][7], TURN's bones in TURN's order."""
    body, gunner = np.asarray(body, np.float32), np.asarray(gunner, np.float32)
    if body.ndim != 4 or gunner.ndim != 4 or body.shape[:2] != gunner.shape[:2] or body.shape[0] != 2 or \
            body.shape[3] != 7 or gunner.shape[3] != 7:
        raise ValueError("rise parts must be [2][K][bones][7] with the same K")
    return b"".join([b"RISE", struct.pack("<II", RISE_VERSION, body.shape[1]), body.astype("<f4").tobytes(),
                     gunner.astype("<f4").tobytes()])


def read_rise_section(data, at, nbody, ngunner):
    if data[at:at + 4] != b"RISE":
        raise ValueError("no RISE section here")
    version, k = struct.unpack_from("<II", data, at + 4)
    if version != RISE_VERSION:
        raise ValueError(f"RISE version {version}")
    at += 12
    out = []
    for nb in (nbody, ngunner):
        n = 2 * k * nb * 7
        out.append(np.frombuffer(data, "<f4", n, at).reshape(2, k, nb, 7))
        at += 4 * n
    return out[0], out[1], at


def read_turn_section(data, at=0):
    """(step, rise, settle, rate, [(names, array)] x 2, end) of a TURN section at `at`, as the DLL reads it."""
    if data[at:at + 4] != b"TURN":
        raise ValueError("no TURN section here")
    version, step, rise, settle, rate, points = struct.unpack_from("<I4fI", data, at + 4)
    if version != TURN_VERSION:
        raise ValueError(f"TURN version {version}")
    at += 28
    parts = []
    for _ in range(2):
        (nb,) = struct.unpack_from("<I", data, at)
        at += 4
        names = [data[at + 32 * i:at + 32 * i + 32].split(b"\0")[0].decode("ascii") for i in range(nb)]
        at += 32 * nb
        n = 2 * points * nb * 7
        arr = np.frombuffer(data, "<f4", n, at).reshape(2, points, nb, 7)
        at += 4 * n
        parts.append((names, arr))
    return step, rise, settle, rate, parts, at


def aim_sections(data):
    """(where a TURN section starts or None, where the known content ends) of a version 1 or 2 aim file:
    after its clips, its BAND, SETL and TURN sections, as the DLL reads them."""
    at = 4
    (version,) = struct.unpack_from("<I", data, at)
    at += 4 + 64 + 24 + (4 if version >= 2 else 0)
    (nyaw,) = struct.unpack_from("<I", data, at)
    at += 4 + 4 * nyaw
    (nb,) = struct.unpack_from("<I", data, at)
    at += 4 + 32 * nb
    (nclips,) = struct.unpack_from("<I", data, at)
    at += 4

    def clip(at):
        _length, frames = struct.unpack_from("<fI", data, at)
        return at + 8 + 4 * frames * nyaw * nb * 7, frames
    for _ in range(nclips):
        at, _f = clip(at + 64)
    turn = None
    while at + 8 <= len(data):
        tag = data[at:at + 4]
        if tag == b"TURN":
            turn = at
            _s, _r, _st, _rt, parts, at = read_turn_section(data, at)
            if data[at:at + 4] == b"RISE":
                at = read_rise_section(data, at, len(parts[0][0]), len(parts[1][0]))[2]
            continue
        if tag not in (b"BAND", b"SETL"):
            break
        (count,) = struct.unpack_from("<I", data, at + 4)
        at += 8
        for _ in range(count):
            if tag == b"BAND":
                at += 8
            else:
                at, frames = clip(at + 64)
                at += 4 * frames * nyaw * nb * 7
    return turn, at


def with_turn(aim, section):
    """The aim file with `section` (TURN, and RISE after it) after its other sections, in place of a TURN
    (and its RISE) it had at its end."""
    turn, end = aim_sections(aim)
    if end != len(aim):
        raise ValueError(f"the aim file has {len(aim) - end} bytes after its sections")
    if turn is not None:
        aim = aim[:turn]
    return aim + section


# --------------------------------------------------------------------------------------------------
# Geometry


def rot_heading(degrees):
    """The 3 x 3 turn about the vertical that adds `degrees` to a heading atan2(x, z) (+z toward +x)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def turned(m, degrees):
    """A world frame (4 x 4) turned about the model's origin's vertical."""
    r = np.eye(4)
    r[:3, :3] = rot_heading(degrees)
    return r @ m


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def swing_reach(u):
    """How far along its swing a hoof has travelled at `u` of the swing: it lifts first, then reaches, then
    sets down (no travel in the first and last tenths)."""
    return smooth(min(max((u - 0.1) / 0.8, 0.0), 1.0))


def swing_height(u):
    """The share of the hoof's lift at `u` of the swing: up early, down at the end."""
    u = min(max(u, 0.0), 1.0)
    return math.sin(math.pi * u ** 0.8)


def foot_cycle(p, s, step, lead):
    """(angle about the origin in the model's space, height share 0..1) of a foot over one cycle (p in
    [0, 1)) of a turn the way `s` (+1 growing heading): the lead foot swings in the first half (from home
    to half a step ahead in the world: the planted ground turns back under it), the other in the second;
    planted, a foot turns back with the ground."""
    if lead:
        if p < 0.5:
            u = p / 0.5
            return s * step * (swing_reach(u) - p), swing_height(u)
        return s * step * (0.5 - (p - 0.5)), 0.0
    if p < 0.5:
        return -s * step * p, 0.0
    u = (p - 0.5) / 0.5
    return s * step * (swing_reach(u) - u / 2.0 - 0.5), swing_height(u)


def lead_of(pos_a, pos_b, s):
    """True when the foot at `pos_a` (model space) is the one ahead along the way the pair travels (a turn
    the way `s` about the origin), so it steps first and the two never cross."""
    mid = 0.5 * (np.asarray(pos_a) + np.asarray(pos_b))
    tangent = s * np.array([mid[2], 0.0, -mid[0]])        # d/da of rot_heading(a) @ mid at a = 0
    return float((np.asarray(pos_a) - np.asarray(pos_b)) @ tangent) > 0.0


# --------------------------------------------------------------------------------------------------
# The units


def rd(p):
    with open(p, "rb") as f:
        return f.read()


class TurnUnit:
    """A deployed camel unit from its pack: the camel, its gun and its gunner, the deployed clips, the
    aim file, and what its gunner does with his hands."""

    def __init__(self, mgc, game, label, folder, camel, gun, gun_bone, clips, aim, arms):
        from aoe3game import gr2
        from aoe3game.gr2_anim import Animation, Rig
        self.mgc, self.label, self.folder, self.game = mgc, label, folder, game
        recipe = dict(mgc.DEFAULT_RECIPE)
        self.camel_path = os.path.join(folder, camel + ".gr2")
        self.gun_path = os.path.join(folder, gun + ".gr2")
        self.gun_bone = gun_bone
        self.camel = mgc.Camel(game, recipe["camel"], rd(self.camel_path))
        self.rider = mgc.Rider(game, recipe["rider"])
        self.rider_model = recipe["rider"]["model"]
        self.scene = mgc.Scene(game, recipe, self.camel, self.rider)
        g = rd(self.gun_path)
        self.gun_rig = Rig.of(gr2.load(g).root())
        self.gun_fig = mgc.Figure(game, g)
        self.clip_paths = [os.path.join(folder, n + ".gr2").replace("\\", "/") for n in clips]
        c, gg, r = (rd(os.path.join(folder, n + ".gr2")) for n in clips)
        self.ca = self.camel.load(c)
        self.ga, self.ra = Animation.load(gg), Animation.load(r)
        self.aim_path = os.path.join(folder, aim)
        self.aim = rd(self.aim_path)
        self.arms = arms
        self.scales = self.camel._scales[id(self.ca)]
        self.index = {n.lower(): i for i, n in enumerate(self.camel.rig.names)}
        self.rindex = {n.lower(): i for i, n in enumerate(self.rider.rig.names)}

    # -- the deployed pose (what the DLL blends over)

    def camel_locals(self, t):
        return self.camel.locals_(self.ca, t)

    def rider_locals(self, t):
        rig = self.rider.rig
        return rig.localise(rig.by_name(rig.pose(self.ra, t)))

    def gun_worlds(self, t):
        return self.gun_rig.by_name(self.gun_rig.pose(self.ga, t))

    def compose(self, locs):
        return self.camel.worlds(locs, self.scales)

    def attach(self, P):
        return self.mgc.rigid(P[self.camel.rider_bone])

    def rider_worlds(self, locs, P):
        A = self.attach(P)
        return {k: A @ v for k, v in self.rider.rig.by_name(self.rider.rig.worlds(locs)).items()}

    def gun_on(self, P, t):
        H = self.mgc.rigid(P[self.camel.hang])
        return {k: H @ v for k, v in self.gun_worlds(t).items()}

    def items(self, P, G, R):
        s = self.scene
        return s.camel_fig.items(P) + self.gun_fig.items(G) + s.rider_fig.items(R) + s.hat_items(R)

    # -- the track's poses

    def camel_track_locals(self, W):
        """The body part's locals of a target pose `W` (world frames by name): each listed bone's frame
        on its parent's (the parent as the DLL composes it: listed, from `W`; else the deployed clip's),
        its scale/shear taken out as Camel.track_bytes does."""
        from aoe3game.gr2_anim import matrix_quat
        rig = self.camel.rig
        base = self.compose(self.camel_locals(0.0))
        listed = {n.lower() for n in BODY_BONES}
        out = []
        for n in BODY_BONES:
            i = self.index[n.lower()]
            par = rig.parents[i]
            if par < 0 or n.lower() in HELD:  # held at the deployed clip's first frame (it breathes)
                m = base[n.lower()].copy() if par < 0 else np.linalg.inv(base[rig.names[par].lower()]) @ base[n.lower()]
            else:
                pn = rig.names[par].lower()
                Wp = W[pn] if (pn in listed and rig.parents[par] >= 0) else base[pn]
                m = np.linalg.inv(Wp) @ W[n.lower()]
            r = m[:3, :3] @ np.linalg.inv(self.scales[i])
            u, _sv, vt = np.linalg.svd(r)
            r = u @ vt
            if np.linalg.det(r) < 0:
                u[:, -1] *= -1
                r = u @ vt
            out.append(np.r_[m[:3, 3], matrix_quat(r)])
        return np.array(out)


# --------------------------------------------------------------------------------------------------
# Authoring


class Author:
    """The rump-high stance and the stepping cycle of one unit."""

    def __init__(self, unit):
        self.u = unit
        mgc = unit.mgc
        cam = unit.camel
        from aoe3game.gr2_pose import about, axis_matrix, transform_branch
        self.P_k = unit.compose(unit.camel_locals(0.0))
        self.R_k = unit.rider_worlds(unit.rider_locals(0.0), self.P_k)
        # the standing idle over the kush body (its chest-pelvis middle and its heading)
        S = cam.pose(cam.base, 0.0)
        fs, _ss, cs = cam.body_frame(S)
        fk, _sk, ck = cam.body_frame(self.P_k)
        yaw = math.degrees(math.atan2(fk[0], fk[2]) - math.atan2(fs[0], fs[2]))
        m = mgc.tr((ck[0], 0.0, ck[2])) @ mgc.rot4(axis_matrix(mgc.Y, yaw)) @ mgc.tr((-cs[0], 0.0, -cs[2]))
        S = {k: m @ v for k, v in S.items()}
        self.S = S
        f, s, _c = cam.body_frame(S)
        self.fwd, self.side = f, s
        pel = S["hs bone pelvis"][:3, 3]
        for sg in (1.0, -1.0):                       # nose down about the pelvis
            turn = about(pel, axis_matrix(s, sg * PITCH))
            if (turn[:3, :3] @ f)[1] < 0:
                break
        P = transform_branch(S, cam.rig, "hs bone chest", mgc.tr((0.0, -HIND_DROP, 0.0)) @ turn)
        neck = P["hs bone neck lower"][:3, 3]
        for sg in (1.0, -1.0):                       # the neck brought back up by as much: the head level
            Q = transform_branch(P, cam.rig, "hs bone neck lower", about(neck, axis_matrix(s, sg * PITCH)))
            if Q["hs bone head"][1, 3] > P["hs bone head"][1, 3]:
                break
        self.H0 = Q
        self.home = {}                                 # each hoof's home frame (the standing footprint)
        for side in (" lt", " rt"):
            for chain in (FRONT, BACK):
                self.home[chain[2] + side] = S[chain[2] + side].copy()
        self.H = self.legs(self.H0, {k: (v, 0.0) for k, v in self.home.items()})
        # the gunner's feet at home, and his station's arms
        self.R_home = {s_: self.R_k[f"bip01 {s_} foot"].copy() for s_ in "lr"}

    def curl(self, frame, degrees):
        """A hoof's frame folded back about the body's side axis by `degrees`, its toe trailing (down and
        back), about the hoof's own point."""
        from aoe3game.gr2_pose import axis_matrix
        for sg in (1.0, -1.0):
            m = axis_matrix(self.side, sg * degrees)
            if degrees == 0.0 or (m @ self.fwd)[1] < 0.0:
                break
        out = frame.copy()
        out[:3, :3] = m @ frame[:3, :3]
        return out

    def legs(self, P, targets):
        """`P` with each leg solved to its hoof's target frame (frame, lift in metres): two-bone IK, the
        carpus forward and the hock back."""
        from aoe3game.gr2_pose import local_axis, two_bone_ik
        cam = self.u.camel
        for side in (" lt", " rt"):
            for chain, pole in ((FRONT, self.fwd), (BACK, -self.fwd)):
                upper, middle, end = (b + side for b in chain)
                frame, lift = targets[end]
                tgt = frame[:3, 3] + np.array([0.0, lift, 0.0])
                P = two_bone_ik(P, cam.rig, upper, middle, end, tgt, pole, local_axis(P[upper][:3, :3], self.side),
                                None, end_frame=frame[:3, :3])
        return P

    def body(self, way, p):
        """The body's target pose at point `p` of a step, the way `way` (0: growing heading)."""
        s = 1.0 if way == 0 else -1.0
        fl, fr = self.home["hs bone hoof frnt lt"][:3, 3], self.home["hs bone hoof frnt rt"][:3, 3]
        bl, br = self.home["hs bone hoof back lt"][:3, 3], self.home["hs bone hoof back rt"][:3, 3]
        front_lead = "hs bone hoof frnt lt" if lead_of(fl, fr, s) else "hs bone hoof frnt rt"
        back_lead = "hs bone hoof back lt" if lead_of(bl, br, s) else "hs bone hoof back rt"
        targets = {}
        pc = (p * STEP / CAMEL_STEP) % 1.0
        for hoof, F in self.home.items():
            a, h = foot_cycle(pc, s, CAMEL_STEP, hoof in (front_lead, back_lead))
            G = turned(F, a)
            if h > 0.0:
                G = self.curl(G, HOOF_CURL * h)
            targets[hoof] = (G, HOOF_LIFT * h)
        return self.legs(self.H0, targets), (front_lead, back_lead)

    def walker(self):
        if getattr(self, "_walker", None) is None:
            self._walker = Walker(self)
        return self._walker

    def gunner(self, way, p, P_risen=None):
        """The gunner's target worlds at point `p` of a step: walking along his circle about the origin,
        facing along it the way the camel turns (Walker)."""
        return self.walker().pose(way, p), None

    def table(self):
        """The two parts' arrays [way][point][bone][7], and notes."""
        u = self.u
        gunner_bones = gunner_bones_of(u)
        body = np.zeros((2, POINTS, len(BODY_BONES), 7))
        gun = np.zeros((2, POINTS, len(gunner_bones), 7))
        notes = {}
        for way in (0, 1):
            for k in range(POINTS):
                p = k / POINTS
                W, leads = self.body(way, p)
                body[way, k] = u.camel_track_locals(W)
                # the camel as the DLL composes it, then the gunner on its attach bone
                P = self.composed(body[way, k])
                R, lead = self.gunner(way, p, P)
                A = u.attach(P)
                locs = u.rider.to_local(R, A)
                gun[way, k] = [np.r_[locs[u.rindex[n.lower()]][0], locs[u.rindex[n.lower()]][1]] for n in gunner_bones]
                notes[way] = {"camel leads": leads}
        return (BODY_BONES, body), (gunner_bones, gun), notes

    def rise_table(self, body, gunner, k_points=RISE_POINTS):
        """The RISE poses [way][K][bones][7] of both parts: at lift (k + 1) / K, the camel's plain blend from the
        kush to TURN's point 0 with the rump leading (the torso tipped nose down about the chest by RUMP_FIRST at
        mid-rise) and each leg solved so its hoof rests HOOF_CLEAR above the ground (where the blend puts it
        across, and the body lifted if a knee would go under), the same both ways; the gunner turning from his
        station to face his path (his walk's first pose, which differs by way), one foot after the other."""
        from aoe3game.gr2_pose import about, axis_matrix, transform_branch
        u = self.u
        cam = u.camel
        _names_b, arr_b = body
        names_g, arr_g = gunner
        out_b, out_g = np.zeros((2, k_points) + arr_b.shape[2:]), np.zeros((2, k_points) + arr_g.shape[2:])
        for k in range(k_points):
            lift = (k + 1) / k_points
            if k == k_points - 1:
                for way in (0, 1):
                    out_b[way, k] = arr_b[way, 0]
                    out_g[way, k] = arr_g[way, 0]
                continue
            W = self.composed(arr_b[0, 0], 0.0, lift)
            ch = W["hs bone chest"][:3, 3]
            extra = RUMP_FIRST * math.sin(math.pi * lift)
            for sg in (1.0, -1.0):                    # nose down about the chest: the rump up
                turn = about(ch, axis_matrix(self.side, sg * extra))
                if (turn[:3, :3] @ self.fwd)[1] <= 0:
                    break
            W = transform_branch(W, cam.rig, "hs bone chest", turn)
            # each hoof unfolds about the body's side axis, the way a hoof flexes, `lift` of the way from its
            # frame in the kush to its frame risen (a hind hoof turns nearly 180 degrees: a plain blend of the
            # two flips it in one step)
            frames = {}
            for s in (" lt", " rt"):
                for c in (FRONT, BACK):
                    h = c[2] + s
                    frames[h] = W[h].copy()
                    frames[h][:3, :3] = flex(self.P_k[h][:3, :3], self.H[h][:3, :3], self.side, lift)
            for _ in range(3):
                targets = {h: (f, HOOF_CLEAR - float(cam.part_points(W, [h])[:, 1].min())) for h, f in frames.items()}
                W = self.legs(W, targets)
                frames = {h: W[h].copy() for h in frames}
                knees = min(float(cam.part_points(W, [b + s])[:, 1].min()) for s in (" lt", " rt")
                            for b in ("hs bone forearm", "hs bone shin"))
                if knees >= HOOF_CLEAR - 1e-3:
                    break
                up = np.eye(4)
                up[1, 3] = HOOF_CLEAR - knees
                W = transform_branch(W, cam.rig, "hs bone chest", up)
            row = u.camel_track_locals(W)
            P = self.composed(row, 0.0, 1.0)
            for way in (0, 1):
                out_b[way, k] = row
                R = self.walker().turn_to_path(way, lift)
                locs = u.rider.to_local(R, u.attach(P))
                out_g[way, k] = [np.r_[locs[u.rindex[n.lower()]][0], locs[u.rindex[n.lower()]][1]] for n in names_g]
        return out_b, out_g

    def gunner_at(self, P, feet=True):
        """The gunner standing at his station: his root where it stood, or moved in toward the handles as
        far as he must to reach them (gatling: the risen gun lifts them out of his reach), his feet at home,
        his hands on the handles of the gun on the camel posed `P`."""
        from aoe3game.gr2_pose import ik_reach, transform_branch, two_bone_ik, unit as unit_
        u = self.u
        rig = u.rider.rig
        R = dict(self.R_k)
        if u.arms:
            move = u.attach(P) @ np.linalg.inv(u.attach(self.P_k))
            hands = {s: move @ self.R_k[f"bip01 {s} hand"] for s in "lr"}
            for _ in range(40):
                worst, d = 0.0, None
                for s in "lr":
                    dist, length = ik_reach(R, f"bip01 {s} upperarm", f"bip01 {s} forearm", f"bip01 {s} hand",
                                            hands[s][:3, 3])
                    if dist - ARM_REACH * length > worst:
                        worst = dist - ARM_REACH * length
                        d = hands[s][:3, 3] - R[f"bip01 {s} upperarm"][:3, 3]
                if d is None:
                    break
                d[1] = 0.0
                shift = np.eye(4)
                shift[:3, 3] = unit_(d) * min(0.01, worst + 1e-3)
                R = transform_branch(R, rig, "bip01 root", shift)
            for s in "lr":
                up, fa, ha = f"bip01 {s} upperarm", f"bip01 {s} forearm", f"bip01 {s} hand"
                pole = R[fa][:3, 3] - 0.5 * (R[up][:3, 3] + R[ha][:3, 3])
                R = two_bone_ik(R, rig, up, fa, ha, hands[s][:3, 3], unit_(pole), np.array([0.0, 0.0, 1.0]), None,
                                end_frame=hands[s][:3, :3], bend_normal=u.rider.elbow_normal[s])
        if feet:
            for s in "lr":
                R = self.foot(R, s, self.R_home[s], 0.0)
        return R

    def foot(self, R, side, frame, lift, knee=None):
        """`R` with the leg solved so the foot sits on `frame` raised `lift` metres, the knee toward `knee` (a
        world direction), or by default toward where his chest faces (a pole from the knee itself flips a
        nearly straight leg backward)."""
        from aoe3game.gr2_pose import two_bone_ik, unit as unit_
        th, ca, fo = f"bip01 {side} thigh", f"bip01 {side} calf", f"bip01 {side} foot"
        if knee is None:
            chest = R["bip01 spine1"][:3, :3] @ self.u.rider.chest_local
            knee = np.array([chest[0], 0.0, chest[2]])
        pole = unit_(np.asarray(knee, np.float64))
        return two_bone_ik(R, self.u.rider.rig, th, ca, fo, frame[:3, 3] + np.array([0.0, lift, 0.0]), pole,
                           np.array([0.0, 0.0, 1.0]), None, end_frame=frame[:3, :3],
                           bend_normal=self.knee_normal()[side])

    def knee_normal(self):
        """How each knee bends: the normal of the leg's plane in the thigh's frame, from his stand at the gun
        (knees a little bent); given to the IK so a nearly straight leg never flips its twist."""
        if getattr(self, "_knee_normal", None) is None:
            from aoe3game.gr2_pose import unit as unit_
            R = self.R_k
            self._knee_normal = {}
            for s in "lr":
                th, ca, fo = (R[f"bip01 {s} {b}"] for b in ("thigh", "calf", "foot"))
                n = np.cross(ca[:3, 3] - th[:3, 3], fo[:3, 3] - ca[:3, 3])
                self._knee_normal[s] = unit_(th[:3, :3].T @ unit_(n))
        return self._knee_normal

    def composed(self, body_row, t=0.0, lift=1.0):
        """The camel's worlds with the body part's row blended over the deployed clip at `t` by `lift`."""
        u = self.u
        locs = list(u.camel_locals(t))
        for j, n in enumerate(BODY_BONES):
            i = u.index[n.lower()]
            locs[i] = blend_local(locs[i], (body_row[j][:3], body_row[j][3:]), lift)
        return u.compose(locs)


def gunner_bones_of(u):
    """The gunner part's bones: his root, pelvis, spine and legs; the gatling gunner's arms too (they swing as
    he walks, off the handles); the zamburak's arms stay his idle's (hands on his hips)."""
    return GUNNER_LEGS + (GUNNER_ARMS if u.arms else [])


class Walker:
    """The gunner walking along his circle about the origin while the camel turns: the game's own walk
    (WALK_CLIP, put on his rig as the tools put infantry clips on him: Rider.standing) at his station, facing
    along the circle the way he goes, retimed to WALK_CYCLES cycles a TURN step; each foot's place along the
    clip's line bent onto the circle (its forward offset over his station's radius is an angle about the
    origin) and its stride scaled so that, planted, it turns back exactly with the ground: it stays put while
    the camel turns on."""

    def __init__(self, author):
        from aoe3game import gr2
        from aoe3game.gr2_anim import Rig
        self.a = author
        u = author.u
        self.foot_rig = Rig.of(gr2.load(u.game.granny(u.mgc.FOOT_MODEL)).root())
        self.anim = u.rider.anim(u.mgc.LIB + WALK_CLIP)
        self.D = float(self.anim.duration)
        n = WALK_SAMPLES
        self.clip = [u.rider.standing(self.foot_rig, self.anim, self.D * k / n, 0.0, np.zeros(3)) for k in range(n)]
        # his station: where his root stands in the kush, on the ground
        r0 = author.R_k["bip01 root"][:3, 3]
        self.C = np.array([r0[0], 0.0, r0[2]])
        self.r = float(np.hypot(r0[0], r0[2]))
        self.L = self.r * math.radians(STEP) / WALK_CYCLES      # the distance one walk cycle covers on the circle
        self.feet = {}
        lows = []
        self.sole = sole_points(u.rider, author.R_k)        # {side: (points in the foot's frame, their low at the gun)}
        for side in "lr":
            pos = np.array([c[f"bip01 {side} foot"][:3, 3] - np.array([c["bip01 root"][0, 3], 0.0, c["bip01 root"][2, 3]])
                            for c in self.clip])
            low = pos[:, 1].min()
            planted = pos[:, 1] < low + 0.012
            # the planted run (cyclic): from touchdown to lift-off, its forward offset made linear in time
            k0 = next(k for k in range(n) if planted[k] and not planted[k - 1])
            run = 0
            while planted[(k0 + run) % n] and run < n:
                run += 1
            z0, z1 = pos[k0, 2], pos[(k0 + run - 1) % n, 2]
            z = pos[:, 2].copy()
            for j in range(run):
                z[(k0 + j) % n] = z0 + (z1 - z0) * j / max(run - 1, 1)
            travel = z0 - z1                                    # forward to back while planted
            share = (run - 1) / n
            scale = (self.L * share) / travel if travel > 1e-6 else 1.0
            # flat while planted: the station's foot frame (flat on the ground) turned to the clip's foot's yaw,
            # weighed in over FLAT_RAMP samples either side of the planted run
            flat0 = author.R_k[f"bip01 {side} foot"][:3, :3]
            flat0 = rot_heading(-yaw_of(flat0)) @ flat0
            weight = np.zeros(n)
            near = pos[:, 1] < low + NEAR_GROUND           # heel strike and toe-off too: flat on the ground
            for k in range(n):
                d = min([abs(((k - j + n // 2) % n) - n // 2) for j in range(n) if near[j]] or [n])
                weight[k] = 1.0 if near[k] else max(0.0, 1.0 - d / FLAT_RAMP)
            frames = []
            for k, c in enumerate(self.clip):
                fc = c[f"bip01 {side} foot"][:3, :3]
                ff = rot_heading(yaw_of(fc)) @ flat0
                qa, qb = np.asarray(matrix_quat_of(fc)), np.asarray(matrix_quat_of(ff))
                _p, q = blend_local((np.zeros(3), qa), (np.zeros(3), qb), smooth(weight[k]))
                frames.append(quat_matrix_of(q))
            self.feet[side] = {"x": pos[:, 0], "y": pos[:, 1], "z": z * scale, "scale": scale, "share": share,
                               "frames": frames}
            lows.append(low)
            if side == "l":                                     # the walk starts with his left foot mid-stance
                self.phase0 = ((k0 + (run - 1) / 2.0) % n) / n
        # the walk set at his feet's height: its planted foot where his stand at the gun has it
        stand = 0.5 * (author.R_k["bip01 l foot"][1, 3] + author.R_k["bip01 r foot"][1, 3])
        self.dy = float(stand - 0.5 * (lows[0] + lows[1]))
        self.C = self.C + np.array([0.0, self.dy, 0.0])
        # his hips lowered as far as the longest stride needs to keep both legs bent a little (the clip's steps
        # are short; on the circle a step is r * STEP / 2 / WALK_CYCLES)
        self.drop = 0.0
        hT, _s = self.heading(0)
        self.phase0 = getattr(self, "phase0", 0.0)
        for k in range(0, WALK_SAMPLES, 4):
            R = u.rider.standing(self.foot_rig, self.anim, self.D * k / WALK_SAMPLES, hT, self.C)
            for side in "lr":
                from aoe3game.gr2_pose import ik_reach
                d, L = ik_reach(R, f"bip01 {side} thigh", f"bip01 {side} calf", f"bip01 {side} foot",
                                self.foot_target(0, side, k / WALK_SAMPLES)[:3, 3])
                self.drop = max(self.drop, d - 0.985 * L)

    def heading(self, way):
        """The heading (degrees) he faces walking the way `way`: the tangent of his circle at his station."""
        s = 1.0 if way == 0 else -1.0
        T = s * np.array([self.C[2], 0.0, -self.C[0]])
        return math.degrees(math.atan2(T[0], T[2])), s

    def _sample(self, arr, w):
        x = w * WALK_SAMPLES
        k0 = int(x) % WALK_SAMPLES
        f = x - int(x)
        return arr[k0] + f * (arr[(k0 + 1) % WALK_SAMPLES] - arr[k0])

    def foot_target(self, way, side, w):
        """The foot's frame (model space) at walk phase `w`, lifted as far as its own sole needs to stay on the
        ground (this rider's foot is longer than the clip's: its toe would dig in as the heel rises)."""
        hT, s = self.heading(way)
        F = self.feet[side]
        x, y, z = (self._sample(F[k], w) for k in ("x", "y", "z"))
        k0 = int(w * WALK_SAMPLES) % WALK_SAMPLES
        pts, low = self.sole[side]
        under = low - float(np.min((F["frames"][k0] @ pts.T)[1] + y + self.dy))
        y = y + max(0.0, under)
        base = np.array([self.C[0], 0.0, self.C[2]]) + rot_heading(hT) @ np.array([x, 0.0, 0.0])
        ang = s * math.degrees(z / self.r)
        k0 = int(w * WALK_SAMPLES) % WALK_SAMPLES
        m = np.eye(4)
        m[:3, :3] = rot_heading(ang) @ rot_heading(hT) @ F["frames"][k0]
        m[:3, 3] = rot_heading(ang) @ base + np.array([0.0, y + self.dy, 0.0])
        return m

    def pose(self, way, p):
        """His worlds (model space) at point `p` of a TURN step."""
        u = self.a.u
        hT, _s = self.heading(way)
        w = (p * WALK_CYCLES + self.phase0) % 1.0
        R = u.rider.standing(self.foot_rig, self.anim, w * self.D, hT, self.C - np.array([0.0, self.drop, 0.0]))
        for side in "lr":
            R = self.a.foot(R, side, self.foot_target(way, side, w), 0.0)
        return self.keep_arms(R)

    def keep_arms(self, R):
        """The zamburak gunner's arms as his idle has them on his trunk (hands on his hips)."""
        u = self.a.u
        if u.arms:
            return R
        rig = u.rider.rig
        idle = rig.localise(self.a.R_k)
        mine = rig.localise(R)
        keep = {n.lower() for n in rig.names} - {n.lower() for n in gunner_bones_of(u)}
        locs = [idle[i] if n.lower() in keep else mine[i] for i, n in enumerate(rig.names)]
        return rig.by_name(rig.worlds(locs))

    def turn_to_path(self, way, lift):
        """His worlds at `lift` of the rise: from his station (the deployed clip's first frame: at the gun) to
        his walk's first pose, facing his path. He turns about his own vertical by the angle between his chest
        at the gun and his chest walking (up to about 150 degrees), the rest of his pose blended in the frame
        turned with him; each foot is carried in its half of the turn (the foot nearer his path first), lifted
        FOOT_LIFT, turning with the body only while it is in the air."""
        u = self.a.u
        rig = u.rider.rig
        k = smooth(lift)
        A, B = self.a.R_k, self.pose(way, 0.0)
        face = lambda R: R["bip01 spine1"][:3, :3] @ u.rider.chest_local  # noqa: E731
        fa, fb = face(A), face(B)
        delta = math.degrees(math.atan2(fb[0], fb[2]) - math.atan2(fa[0], fa[2]))
        delta = (delta + 180.0) % 360.0 - 180.0
        c = A["bip01 root"][:3, 3].copy()
        c[1] = 0.0

        def about(deg):
            m = np.eye(4)
            m[:3, :3] = rot_heading(deg)
            m[:3, 3] = c - rot_heading(deg) @ c
            return m
        back = about(-delta)
        Bs = {n: back @ v for n, v in B.items()}            # his walk's pose turned back to face the gun
        la, lb = rig.localise(A), rig.localise(Bs)
        R = rig.by_name(rig.worlds([blend_local(x, y, k) for x, y in zip(la, lb)]))
        turn = about(delta * k)
        R = {n: turn @ v for n, v in R.items()}
        hT, _s = self.heading(way)
        T = rot_heading(hT) @ np.array([0.0, 0.0, 1.0])
        first = "l" if float((B["bip01 l foot"][:3, 3] - B["bip01 r foot"][:3, 3]) @ T) > 0 else "r"
        for side in "lr":
            u_ = smooth(min(max((k - (0.0 if side == first else 0.5)) / 0.5, 0.0), 1.0))
            f0, f1 = A[f"bip01 {side} foot"], Bs[f"bip01 {side} foot"]
            pp, qq = blend_local((f0[:3, 3], np.asarray(matrix_quat_of(f0[:3, :3]))),
                                 (f1[:3, 3], np.asarray(matrix_quat_of(f1[:3, :3]))), u_)
            m = np.eye(4)
            m[:3, :3] = quat_matrix_of(qq)
            m[:3, 3] = pp
            m = about(delta * u_) @ m
            kn = R[f"bip01 {side} calf"][:3, 3] - 0.5 * (R[f"bip01 {side} thigh"][:3, 3] + R[f"bip01 {side} foot"][:3, 3])
            R = self.a.foot(R, side, m, FOOT_LIFT * math.sin(math.pi * u_), knee=kn)
        return self.keep_arms(R)


def sole_points(rider, R):
    """{side: (the points of the foot's mesh in its bone's frame, the lowest of them in pose R)}."""
    from aoe3game import gr2_mesh, gr2_skin
    read = gr2_mesh.read(rider.data)
    m, skel = read["meshes"][0], read["skeletons"][0]
    exact = {b["name"]: R[b["name"].lower()] for b in skel["bones"] if b["name"].lower() in R}
    world = gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"], m["skin_names"], skel, exact)
    vb, vw = np.asarray(m["vertex_bones4"]), np.asarray(m["vertex_weights4"])
    dom = np.array([str(m["skin_names"][int(i)]).lower() for i in vb[np.arange(len(vb)), np.argmax(vw, 1)]])
    out = {}
    for side in "lr":
        F = R[f"bip01 {side} foot"]
        pts = world[dom == f"bip01 {side} foot"]
        local = (np.linalg.inv(F[:3, :3]) @ (pts - F[:3, 3]).T).T
        out[side] = (local, float(pts[:, 1].min()))
    return out


def yaw_of(m):
    """The heading (degrees) of a frame's local z axis about the vertical."""
    v = np.asarray(m) @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.atan2(v[0], v[2]))


def matrix_quat_of(m):
    from aoe3game.gr2_anim import matrix_quat
    u_, _s, vt = np.linalg.svd(m)
    return matrix_quat(u_ @ vt)


def quat_matrix_of(q):
    from aoe3game.gr2_skin import quat_matrix
    return quat_matrix(q)


def flex(a, b, axis, u):
    """The 3 x 3 frame `u` of the way from `a` to `b`, turning the way round whose axis lies along `axis`
    (a hoof flexes about the body's side axis: the shorter way can be the wrong one near 180 degrees)."""
    from aoe3game.gr2_anim import matrix_quat
    from aoe3game.gr2_pose import axis_matrix
    m = b @ np.linalg.inv(a)
    u_, _s, vt = np.linalg.svd(m)
    q = np.asarray(matrix_quat(u_ @ vt), np.float64)
    v = q[:3]
    if float(v @ axis) < 0.0:
        q, v = -q, -v
    sn = float(np.linalg.norm(v))
    if sn < 1e-9:
        return b.copy()
    deg = 2.0 * math.degrees(math.atan2(sn, float(q[3])))
    return axis_matrix(v / sn, deg * u) @ a


def blend_local(a, b, w):
    """(position, quaternion) blended as the DLL does: positions lerped, quaternions nlerped on the near side."""
    pa, qa = np.asarray(a[0], np.float64), np.asarray(a[1], np.float64)
    pb, qb = np.asarray(b[0], np.float64), np.asarray(b[1], np.float64)
    if w <= 0.0:
        return pa, qa
    if float(qa @ qb) < 0:
        qb = -qb
    q = qa + w * (qb - qa)
    return pa + w * (pb - pa), q / np.linalg.norm(q)


def sample_track(arr, way, phase):
    """A part's row at `phase` (0..1), between the two nearest points, the last running into the first."""
    n = arr.shape[1]
    fp = phase * n
    p0 = int(fp) % n
    w = fp - int(fp)
    p1 = (p0 + 1) % n
    a, c = arr[way, p0].astype(np.float64), arr[way, p1].astype(np.float64)
    out = a.copy()
    out[:, :3] = a[:, :3] + w * (c[:, :3] - a[:, :3])
    sign = np.where(np.sum(a[:, 3:] * c[:, 3:], 1) < 0, -1.0, 1.0)[:, None]
    out[:, 3:] = a[:, 3:] + w * (sign * c[:, 3:] - a[:, 3:])
    return out


# --------------------------------------------------------------------------------------------------
# The replica of the DLL's turn, for the checks and the preview


def turn_timeline(by, step=STEP, rise=RISE, settle=SETTLE, rate=RATE, fps=FPS):
    """[(t, shown heading less the start, lift, phase)] of a turn of `by` degrees, as ShownHeading."""
    ms_rise, ms_settle = int(rise * 1000 + 0.5), int(settle * 1000 + 0.5)
    total = ms_rise + ms_settle + int(abs(by) * 1000.0 / rate + 0.5)
    middle = total - ms_rise - ms_settle
    out = []
    n = int(round(total / 1000.0 * fps))
    for k in range(n + 1):
        t = min(k / fps * 1000.0, float(total))
        if t >= total:
            lift, kk = 0.0, 1.0
        elif t < ms_rise:
            lift, kk = smooth(t / ms_rise), 0.0
        elif t < ms_rise + middle:
            lift, kk = 1.0, (t - ms_rise) / middle if middle > 0 else 1.0
        else:
            lift, kk = (1.0 - smooth((t - ms_rise - middle) / ms_settle)) if ms_settle else 0.0, 1.0
        s = abs(by) * kk / step
        out.append((t / 1000.0, by * kk, lift, s - math.floor(s)))
    return out


def qmul(a, b):
    """Quaternions (x, y, z, w): a then b in a's frame, as the DLL's QuatMul."""
    ax, ay, az, aw = a
    bx, by_, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by_, aw * by_ - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by_ - ay * bx + az * bw, aw * bw - ax * bx - ay * by_ - az * bz])


def part_pose(clip_locs, names, index, arr, way, phase, lift, rise=None, settling=False, mode="offset"):
    """A part's bones over the clip's locals as the DLL (with the RISE proposal when `rise` is given) poses
    them: the step's point at `phase` when risen, else the rise's poses, plus, while it settles, `lift` of
    the step's offset from its point 0."""
    locs = list(clip_locs)
    row = sample_track(arr, way, phase)
    if rise is None or lift >= 1.0:
        for j, n in enumerate(names):
            i = index[n.lower()]
            locs[i] = blend_local(locs[i], (row[j][:3], row[j][3:]), lift)
        return locs
    K = rise.shape[0]
    x = lift * K
    k = min(int(x), K - 1)
    f = x - k
    zero = arr[way, 0].astype(np.float64)
    for j, n in enumerate(names):
        i = index[n.lower()]
        base = locs[i] if k == 0 else (rise[k - 1, j, :3], rise[k - 1, j, 3:])
        p, q = blend_local(base, (rise[k, j, :3], rise[k, j, 3:]), f)
        if settling and lift > 0.0 and mode == "blend":
            p, q = blend_local((p, q), (row[j, :3], row[j, 3:]), lift)
        elif settling and lift > 0.0:
            p = p + lift * (row[j, :3] - zero[j, :3])
            q0 = zero[j, 3:] * np.array([-1.0, -1.0, -1.0, 1.0])
            d = qmul(row[j, 3:], q0)
            if d[3] < 0:
                d = -d
            dl = np.array([0.0, 0.0, 0.0, 1.0]) + lift * (d - np.array([0.0, 0.0, 0.0, 1.0]))
            q = qmul(dl / np.linalg.norm(dl), q)
            q = q / np.linalg.norm(q)
        locs[i] = (p, q)
    return locs


def replica(author, body, gunner, by, rise=None):
    """Per frame of a turn of `by` degrees: (t, camel worlds, gun worlds, rider worlds, rider locals), each
    turned by the shown heading about the origin, as the DLL draws it (the deployed clips playing on); with
    `rise` ((body, gunner) arrays), as the RISE proposal would."""
    u = author.u
    names_b, arr_b = body
    names_g, arr_g = gunner
    way = 0 if by > 0 else 1
    length = u.ca.duration
    frames = []
    timeline = turn_timeline(by)
    for t, shown, lift, phase in timeline:
        tc = t % length
        settling = t > timeline[-1][0] / 2.0
        locs = part_pose(u.camel_locals(tc), names_b, u.index, arr_b, way, phase, lift,
                         None if rise is None else rise[0][way], settling, SETTLE_MODE["body"])
        P = u.compose(locs)
        rl = part_pose(u.rider_locals(tc), names_g, u.rindex, arr_g, way, phase, lift,
                       None if rise is None else rise[1][way], settling, SETTLE_MODE["gunner"])
        R = u.rider_worlds(rl, P)
        G = u.gun_on(P, tc)
        frames.append((t, {k: turned(v, shown) for k, v in P.items()}, {k: turned(v, shown) for k, v in G.items()},
                       {k: turned(v, shown) for k, v in R.items()}, rl))
    return frames


def write_clips(author, frames, folder, name):
    """The camel's, the gun's and the rider's clip of a baked turn (.gr2), for check_anim."""
    from aoe3game.gr2_anim import animation_file
    u = author.u
    times = np.array([f[0] for f in frames])
    cam_bytes = u.camel.track_bytes(name + "_camel", times, [f[1] for f in frames], u.ca, u.scales)
    rider_bytes = u.rider.track_bytes(name + "_rider", times, [f[4] for f in frames], u.ra)
    grig = u.gun_rig
    glocs = [grig.localise(u.gun_worlds(t % u.ga.duration)) for t in times]
    tracks = [(bone, times, np.array([f[i][0] for f in glocs]), np.array([f[i][1] for f in glocs]))
              for i, bone in enumerate(grig.names)]
    gun_bytes = animation_file(name + "_gun", float(times[-1]), grig.names[0], tracks, basis=grig.basis,
                               accumulation=u.ga.accumulation, timestep=u.ga.timestep, source=name + "_gun")
    paths = {}
    for who, data in (("camel", cam_bytes), ("gun", gun_bytes), ("rider", rider_bytes)):
        p = os.path.join(folder, f"{name}_{who}.gr2")
        with open(p, "wb") as f:
            f.write(data)
        paths[who] = p.replace("\\", "/")
    return paths, float(times[-1])


HOOVES = [{"name": "hoof front left", "bone": "HS Bone Hoof Frnt Lt"}, {"name": "hoof front right", "bone": "HS Bone Hoof Frnt Rt"},
          {"name": "hoof back left", "bone": "HS Bone Hoof Back Lt"}, {"name": "hoof back right", "bone": "HS Bone Hoof Back Rt"}]


def job_for(author, clips, rider_model):
    """The check_anim job of a unit's baked turns."""
    u = author.u
    from aoe3game import gr2_mesh
    upm = gr2_mesh.read(u.rider.data)["units_per_meter"]
    palm = {s: (np.asarray(u.rider.body.palm_local[s]) / upm).tolist() for s in ("l", "r")}
    hand = {s: {"bone": f"rider:bip01 {s} hand", "offset": palm[s]} for s in ("l", "r")}
    actors = {"camel": {"model": u.camel_path.replace("\\", "/"), "rig": {"preset": "bare", "feet": HOOVES}},
              "gun": {"model": u.gun_path.replace("\\", "/"),
                      "attach": {"to": "camel", "bone": "bone attachpoint", "from_bone": u.gun_bone}},
              "rider": {"model": rider_model, "rig": "human", "attach": {"to": "camel", "bone": "bone attachpoint"}}}
    jc = {}
    for name, (paths, length) in clips.items():
        jc[name] = {"anims": paths, "duration": round(length, 6), "loop": False, "lying": "ends", "ground_speed": 0.0}
        deg = int(name.split("_")[1])
        if deg % int(STEP):     # it ends mid-stride: the DLL's settle rule (see the RISE notes)
            jc[name]["limits"] = {"sink": 0.10}
    # today's deployed clips, which the turn plays over: what of theirs a turn shows is theirs
    jc["deployed (today)"] = {"anims": {"camel": u.clip_paths[0], "gun": u.clip_paths[1], "rider": u.clip_paths[2]},
                              "loop": True, "ground_speed": 0.0}
    grips = []
    if u.arms:          # he lets go of the long handles to walk, and takes them again: judged at the ends only
        for name, (_paths, length) in clips.items():
            for s in "lr":
                grips.append({"name": f"{'left' if s == 'l' else 'right'} hand on its long handle (the ends)",
                              "clips": [name], "hand": hand[s], "grip": {"bone": "gun:bone_yaw", "at": hand[s]},
                              "frames": [[0.0, 0.5 / FPS], [length - 0.5 / FPS, length]]})
    return {"fps": FPS, "ground": 0.0, "actors": actors, "clips": jc,
            "mounts": [{"name": "the gun on its post", "part": "gun:bone_yaw",
                        "mount": {"bone": "camel:hs bone chest", "at": "gun:bone_yaw"}}],
            "grips": grips,
            "capsules": [{"name": "camel body", "a": "camel:hs bone pelvis", "b": "camel:hs bone chest", "radius": 0.45},
                         {"name": "camel neck", "a": "camel:hs bone neck upper", "b": "camel:hs bone head", "radius": 0.13}],
            "speed_exempt": ["rider:bip01 prop1", "rider:bip01 prop2"],
            "speed_limits": {"camel:hs bone tail_01": 2000.0} | {
                f"camel:hs bone {b}": 2000.0 for b in ("forearm lt", "forearm rt", "hoof back lt", "hoof back rt")},
            "reasons": {"tail speed 2000": "the tail is not in the turn's poses: the deployed clip plays on under the "
                                           "turn, and its own tail flick turns 1817 deg/s at 0.27 s of its 2 s loop "
                                           "(the clip 'deployed (today)' in this job shows it)",
                        "forearm and hind hoof speed 2000": "a turn that ends mid-swing (75 degrees) settles with "
                                                    "a diagonal pair still lifted 22 cm: those legs come down and "
                                                    "fold into the kush in the 0.45 s settle, the front forearm and "
                                                    "the hind hoof turning 1540 deg/s; every whole-step turn stays "
                                                    "under 1500",
                        "settle sink 0.10 (turns not a multiple of STEP)": "a turn that does not end on a whole step "
                            "(75, 90 degrees) settles from mid-stride by the DLL's rule: each of the gunner's bones "
                            "takes the lift's share of its offset from the step's first point over the rise's pose; "
                            "the striding legs' offset over the pose turning back to the gun puts a heel or toe up to "
                            "10 cm under the ground for about 3 frames (0.1 s) of the settle. Turns of 60 and 180 "
                            "degrees end on a whole step and pass at 0.05",
                        "prop bones exempt": "the rider's Prop1 and Prop2 bones hold nothing in these units"},
            "removed": {}}


def load_units(mgc, game, pack):
    gat = os.path.join(pack, r"gatling-camel\files\art\WoL\units\cavalry_ranged\gatling_camel")
    zam = os.path.join(pack, r"zamburak\files\art\WoL\units\cavalry_ranged\zamburak_cannon")
    g = TurnUnit(mgc, game, "gatling camel B", gat, "gatling_camel_camel_nogun", "gatling_camel_gun_B55",
                 "bone_gatling_camel_gun_B55",
                 ("gatling_camel_camel_B_deployed", "gatling_camel_gun_B55_deployed", "gatling_camel_rider_B55_deployed"),
                 "gatling_camel_B55.aim", arms=True)
    z = TurnUnit(mgc, game, "zamburak cannon", zam, "zamburak_cannon_camel", "zamburak_cannon_gun",
                 "bone_zamburak_cannon_gun",
                 ("zamburak_cannon_camel_deployed", "zamburak_cannon_gun_deployed", "zamburak_cannon_rider_deployed"),
                 "zamburak_cannon.aim", arms=False)
    return {"gatling": g, "zamburak": z}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--pack", required=True, help="the folder with gatling-camel and zamburak (things-new wol-fixes)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--turns", default="60,90,180", help="the baked turns, degrees (each way)")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--preview", action="store_true", help="also check_anim's preview of the 90 and 180 degree turns")
    args = ap.parse_args(argv)
    from aoe3game.deploy import RefusedPath, refuse_steam
    try:
        refuse_steam(args.out)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    import make_gun_camel as mgc
    work = tempfile.mkdtemp(prefix="camelturn_")
    game = mgc.Game(args.game, args.granny_helper, work)
    os.makedirs(args.out, exist_ok=True)
    report = {}
    status = 0
    for key, u in load_units(mgc, game, args.pack).items():
        author = Author(u)
        body, gunner, notes = author.table()
        rise = author.rise_table(body, gunner)
        section = turn_section(STEP, RISE, SETTLE, RATE, body, gunner) + rise_section(*rise)
        new_aim = with_turn(u.aim, section)
        aim_dir = os.path.join(args.out, "aim")
        os.makedirs(aim_dir, exist_ok=True)
        with open(os.path.join(aim_dir, os.path.basename(u.aim_path)), "wb") as f:
            f.write(new_aim)
        assert new_aim.startswith(u.aim if aim_sections(u.aim)[0] is None else u.aim[:aim_sections(u.aim)[0]])
        check = os.path.join(args.out, key)
        os.makedirs(check, exist_ok=True)
        rider_model = os.path.join(check, "rider_model.gr2")
        with open(rider_model, "wb") as f:
            f.write(game.granny(u.rider_model))
        clips = {}
        plain = {}
        for deg in [float(x) for x in args.turns.split(",")]:
            for sgn, tag in ((1.0, "right"), (-1.0, "left")):
                name = f"turn_{int(deg)}_{tag}"
                frames = replica(author, body, gunner, sgn * deg, rise)
                clips[name] = write_clips(author, frames, check, name)
                low = [min(float(u.camel.part_points(f[1], [b + s])[:, 1].min()) for s in (" lt", " rt")
                           for b in ("hs bone forearm", "hs bone hoof frnt", "hs bone shin", "hs bone hoof back"))
                       for f in replica(author, body, gunner, sgn * deg)]
                plain[name] = round(min(low), 3)
        job = job_for(author, clips, rider_model.replace("\\", "/"))
        job_path = os.path.join(check, "turn_job.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1)
        H = author.H
        tp = u.camel.part_points(H, u.camel.KUSH_TORSO)
        report[key] = {"aim": os.path.join(aim_dir, os.path.basename(u.aim_path)), "aim bytes": len(new_aim),
                       "section bytes": len(section), "body bones": body[0], "gunner bones": gunner[0],
                       "leads": {str(k): v for k, v in notes.items()},
                       "risen belly": round(float(tp[:, 1].min()), 3), "risen top": round(float(tp[:, 1].max()), 3),
                       "pelvis": round(float(H["hs bone pelvis"][1, 3]), 3), "chest": round(float(H["hs bone chest"][1, 3]), 3),
                       "job": job_path, "lowest leg point with the plain blend (today's DLL)": plain}
        if not args.no_check:
            cmd = [sys.executable, "-I", os.path.join(HERE, "check_anim.py"), job_path,
                   "--json", os.path.join(check, "report.json"), "--risk-sheet", os.path.join(check, "risk.png")]
            r = subprocess.run(cmd, capture_output=True, text=True)
            with open(os.path.join(check, "report.txt"), "w", encoding="utf-8") as f:
                f.write(r.stdout + r.stderr)
            report[key]["check exit"] = r.returncode
            status |= r.returncode
            if args.preview and r.returncode == 0:
                sub = dict(job)
                sub["clips"] = {k: v for k, v in job["clips"].items() if k.startswith(("turn_90", "turn_180"))}
                sp = os.path.join(check, "preview_job.json")
                with open(sp, "w", encoding="utf-8") as f:
                    json.dump(sub, f, indent=1)
                r2 = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check_anim.py"), sp, "--preview",
                                     os.path.join(check, "preview")], capture_output=True, text=True)
                report[key]["preview exit"] = r2.returncode
                with open(os.path.join(check, "preview.txt"), "w", encoding="utf-8") as f:
                    f.write(r2.stdout + r2.stderr)
    print(json.dumps(report, indent=1))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
