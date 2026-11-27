# SPDX-License-Identifier: GPL-3.0-or-later
"""The deployed camels' slow walk: the WALK section of their aim files, its checks and its preview.

JTMaston (2026-11-27): "A slow moving animation is needed for deploy mode. Maybe the gunner pushing against
the camel and barely moving it", for the gatling camel's B variant on foot and the zamburak cannon. Their
Bombard tactic then gets a speed (the speedmodifier, 0.4 as the game's deployed artillery) and keeps playing
its deployed idle as its walk; the turretArc key of the DLL shows the walk over it, as it shows the turn on
the spot (camel_turn.py): while the unit moves, the camel rises rump-high through the aim file's RISE poses
(the turn's), walks on in big unhurried steps by diagonal pairs, each hoof lifted HOOF_LIFT and planted
while the ground runs back under it, and settles back into the kush when the unit stops. The gunner walks
beside it, his trunk turned to it and leaning in, his palms on its flank (the zamburak's left; his right
hand keeps the linstock low at his side as at the gun), his feet planted as the camel's hooves. The gun
stays at rest.

The pose is picked by how far the unit has gone (phase = distance / STRIDE), not by time: whatever the
game's speed, a planted hoof or foot stays put on the ground.

The contract with the DLL (src/features/turretarc.cpp, ReadAim's "WALK", after TURN and RISE): b"WALK",
u32 1, f32 stride (model units a hoof cycle covers), f32 rise and settle (seconds), f32 rate (degrees a second
the model's heading follows a new course while it is deployed), u32 points, u32 clip count and the clips (64 B
each, NUL padded) on which the walk may show (the deployed idle, the shot and the reload of each part: the
walk is shown while one of them plays), then three parts: the body's model, the gunner's, the gun's; each
u32 bone count, the names (32 B, NUL padded) and float32 [point][bone][7]: local position and rotation (x,
y, z, w) in the parent's frame. Point 0 has every hoof at home: the body's equals TURN's point 0 for a turn
toward a growing heading, so the RISE poses lead into it. Semantics, for a lift l (0..1) and a phase p: the
body as TURN's way 0 (RISE's poses, then l of the point's offset from point 0); the gunner and the gun a
straight blend of the clip's pose to the point's by l.

    python -I tools/camel_walk.py --game <WoL copy> --pack <things-new wol-fixes> --out <folder>

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

import camel_turn as ct  # noqa: E402

WALK_VERSION = 1
SPEED = 1.25              # game units a second: the camels' MaxVelocity 5.0 times the Bombard speedmodifier 0.25
STRIDE = 1.0              # how far the ground runs back under the camel in one cycle (both diagonal pairs once)
POINTS = 48               # points of one cycle in the table
RATE = 120.0              # degrees a second the model's heading follows a new course while deployed
LEAN = 18.0               # degrees the gunner leans in, his trunk turned TOWARD degrees to the camel
TOWARD = {"gatling": 30.0, "zamburak": 40.0}
NOD = 3.0                 # degrees the camel's neck nods with each pair's step
REACH = 0.88              # a pushing arm this far stretched at most (of its length)
OFFSET_FROM = 0.6         # rising or settling, the walk's step shows from this lift on (its legs unfolded first)
PUSH_BACK = 0.20          # his walk's root this far behind the camel's chest bone, at its flank
FPS = 30
WALK_CYCLES = 1           # the gunner's walk cycles (two steps) a camel cycle
GUNNER_BONES = ct.GUNNER_LEGS + ct.GUNNER_ARMS
# the diagonal pairs: the front left and the hind right swing in the first half of a cycle, the others after
FIRST_PAIR = {"hs bone hoof frnt lt", "hs bone hoof back rt"}
FWD = np.array([0.0, 0.0, 1.0])  # the way the game moves the unit: its model's +z
# the gun's parts the gunner carries: (gun bone, his bone it rides on as at the gun): the zamburak's linstock in his
# right hand, the gatling's spare magazine at his hip (at the gun it hangs by his side; left where it was it would
# float beside the risen camel)
CARRIED = {"zamburak": (("bone_linstock", "bip01 r hand"),), "gatling": (("bone_ammo2", "bip01 pelvis"),)}


def foot_line(p, stride, lead):
    """(distance along the way in the model's space, height share 0..1) of a hoof over one cycle (p in [0,
    1)): the lead pair swings in the first half (from home to half a stride ahead: the ground runs back under
    it), the other pair in the second; planted, a hoof runs back with the ground. ct.foot_cycle in a line."""
    return ct.foot_cycle(p, 1.0, stride, lead)


class Walk:
    """The walk's poses of one unit: the body's (from camel_turn.Author's rump-high stance), the gunner's
    and the gun's."""

    def __init__(self, key, unit):
        self.key, self.u = key, unit
        self.a = ct.Author(unit)
        self.cycle = STRIDE / SPEED                  # seconds a cycle lasts at the game's speed
        a, u = self.a, unit
        self.camel_side = 1.0 if float(self.a.H0["hs bone chest"][0, 3] - a.R_k["bip01 root"][0, 3]) > 0 else -1.0
        self._gunner_setup()

    # -- the body

    def body(self, p):
        a = self.a
        from aoe3game.gr2_pose import axis_matrix, about, transform_branch
        targets = {}
        for hoof, F in a.home.items():
            d, h = foot_line(p, STRIDE, hoof in FIRST_PAIR)
            G = F.copy()
            G[:3, 3] = G[:3, 3] + d * FWD
            if h > 0.0:
                G = a.curl(G, ct.HOOF_CURL * h)
            targets[hoof] = (G, ct.HOOF_LIFT * h)
        W = a.legs(a.H0, targets)
        nod = NOD * math.sin(4.0 * math.pi * p)        # down as each pair reaches
        if nod:
            neck = W["hs bone neck lower"][:3, 3]
            for sg in (1.0, -1.0):
                Q = transform_branch(W, self.u.camel.rig, "hs bone neck lower", about(neck, axis_matrix(a.side, sg * nod)))
                if (Q["hs bone head"][1, 3] < W["hs bone head"][1, 3]) == (nod > 0):
                    break
            W = Q
        return W

    # -- the gunner

    def _gunner_setup(self):
        """The game's walk (camel_turn.WALK_CLIP) on his rig, facing the way at his station, each foot's
        planted run made linear and scaled so it runs back with the ground; his station moved in to the
        camel's flank as far as his palms need."""
        from aoe3game import gr2
        from aoe3game.gr2_anim import Rig
        a, u = self.a, self.u
        self.foot_rig = Rig.of(gr2.load(u.game.granny(u.mgc.FOOT_MODEL)).root())
        self.anim = u.rider.anim(u.mgc.LIB + ct.WALK_CLIP)
        self.D = float(self.anim.duration)
        n = ct.WALK_SAMPLES
        clip = [u.rider.standing(self.foot_rig, self.anim, self.D * k / n, 0.0, np.zeros(3)) for k in range(n)]
        L = STRIDE / WALK_CYCLES
        self.sole = ct.sole_points(u.rider, a.R_k)
        self.feet, lows = {}, []
        for side in "lr":
            pos = np.array([c[f"bip01 {side} foot"][:3, 3] - np.array([c["bip01 root"][0, 3], 0.0, c["bip01 root"][2, 3]])
                            for c in clip])
            low = pos[:, 1].min()
            planted = pos[:, 1] < low + 0.012
            k0 = next(k for k in range(n) if planted[k] and not planted[k - 1])
            run = 0
            while planted[(k0 + run) % n] and run < n:
                run += 1
            z0, z1 = pos[k0, 2], pos[(k0 + run - 1) % n, 2]
            z = pos[:, 2].copy()
            for j in range(run):
                z[(k0 + j) % n] = z0 + (z1 - z0) * j / max(run - 1, 1)
            travel = z0 - z1
            share = (run - 1) / n
            scale = (L * share) / travel if travel > 1e-6 else 1.0
            flat0 = a.R_k[f"bip01 {side} foot"][:3, :3]
            flat0 = ct.rot_heading(-ct.yaw_of(flat0)) @ flat0
            near = pos[:, 1] < low + ct.NEAR_GROUND
            weight = np.zeros(n)
            for k in range(n):
                d = min([abs(((k - j + n // 2) % n) - n // 2) for j in range(n) if near[j]] or [n])
                weight[k] = 1.0 if near[k] else max(0.0, 1.0 - d / ct.FLAT_RAMP)
            frames = []
            for k, c in enumerate(clip):
                fc = c[f"bip01 {side} foot"][:3, :3]
                ff = ct.rot_heading(ct.yaw_of(fc)) @ flat0
                qa, qb = np.asarray(ct.matrix_quat_of(fc)), np.asarray(ct.matrix_quat_of(ff))
                _p, q = ct.blend_local((np.zeros(3), qa), (np.zeros(3), qb), ct.smooth(weight[k]))
                frames.append(ct.quat_matrix_of(q))
            self.feet[side] = {"x": pos[:, 0], "y": pos[:, 1], "z": z * scale, "frames": frames}
            lows.append(low)
            if side == "l":
                self.phase0 = ((k0 + (run - 1) / 2.0) % n) / n
        stand = 0.5 * (a.R_k["bip01 l foot"][1, 3] + a.R_k["bip01 r foot"][1, 3])
        self.dy = float(stand - 0.5 * (lows[0] + lows[1]))
        # he pushes at the camel's flank, behind its chest (at the gun he stands at its withers)
        r0 = a.R_k["bip01 root"][:3, 3]
        self.C = np.array([r0[0], self.dy, float(a.H0["hs bone chest"][2, 3]) - PUSH_BACK])
        self.drop = 0.0
        # his palms on the camel's flank (fixed on it: its trunk does not move as it walks), and his station
        # moved in toward it until the farther palm is in reach
        self.W0 = self.body(0.0)
        for _ in range(60):
            R = self._legs_pose(0.0)
            self.palms = self._palm_targets(R)
            worst = 0.0
            for s, (palm, _f, _n) in self.palms.items():
                from aoe3game.gr2_pose import ik_reach
                d, length = ik_reach(R, f"bip01 {s} upperarm", f"bip01 {s} forearm", f"bip01 {s} hand", palm)
                worst = max(worst, d - REACH * length)
            if worst <= 1e-3:
                break
            self.C = self.C + np.array([self.camel_side * min(0.02, worst + 1e-3), 0.0, 0.0])
        for k in range(0, n, 4):
            R = u.rider.standing(self.foot_rig, self.anim, self.D * k / n, 0.0, self.C)
            for side in "lr":
                from aoe3game.gr2_pose import ik_reach
                d, length = ik_reach(R, f"bip01 {side} thigh", f"bip01 {side} calf", f"bip01 {side} foot",
                                     self.foot_target(side, k / n)[:3, 3])
                self.drop = max(self.drop, d - 0.985 * length)

    def _sample(self, arr, w):
        n = ct.WALK_SAMPLES
        x = w * n
        k0 = int(x) % n
        f = x - int(x)
        return arr[k0] + f * (arr[(k0 + 1) % n] - arr[k0])

    def foot_target(self, side, w):
        F = self.feet[side]
        x, y, z = (self._sample(F[k], w) for k in ("x", "y", "z"))
        k0 = int(w * ct.WALK_SAMPLES) % ct.WALK_SAMPLES
        pts, low = self.sole[side]
        under = low - float(np.min((F["frames"][k0] @ pts.T)[1] + y + self.dy))
        y = y + max(0.0, under)
        m = np.eye(4)
        m[:3, :3] = F["frames"][k0]
        m[:3, 3] = np.array([self.C[0] + x, y + self.dy, self.C[2] + z])
        return m

    def _legs_pose(self, p):
        """His walk at point `p` of a cycle, his feet on their targets, his trunk turned to the camel and
        leaning in (arms as the walk has them)."""
        from aoe3game.gr2_pose import rotate_about
        u, a = self.u, self.a
        rig = u.rider.rig
        w = (p * WALK_CYCLES + self.phase0) % 1.0
        R = u.rider.standing(self.foot_rig, self.anim, w * self.D, 0.0, self.C - np.array([0.0, self.drop, 0.0]))
        for side in "lr":
            R = a.foot(R, side, self.foot_target(side, w), 0.0)
        toward = TOWARD[self.key] * self.camel_side         # heading grows toward +x: turn to the camel
        # the upper trunk only (spine1: the thighs hang on bip01 spine in this rig, so a turn there would move
        # the legs off their feet)
        R = rotate_about(R, rig, "bip01 spine1", "bip01 spine1", np.array([0.0, 1.0, 0.0]), toward)
        chest = R["bip01 spine1"][:3, :3] @ u.rider.chest_local
        right = np.cross(np.array([0.0, 1.0, 0.0]), chest)
        right = right / np.linalg.norm(right)
        for sg in (1.0, -1.0):
            Q = rotate_about(R, rig, "bip01 spine1", "bip01 spine1", right, sg * LEAN)
            if float((Q["bip01 head"][:3, 3] - R["bip01 head"][:3, 3]) @ chest) > 0:
                break
        return Q

    def _palm_targets(self, R):
        """{side: (palm, finger, normal)} on the camel's flank: the gatling gunner's two palms, the zamburak's
        left, at his chest's height a little ahead of each shoulder, on the surface toward him."""
        cam = self.u.camel
        pts = cam.part_points(self.W0, cam.KUSH_TORSO)
        sides = "lr" if self.key == "gatling" else "l"
        out = {}
        s_out = -self.camel_side                     # from the camel toward him (x)
        for s in sides:
            sh = R[f"bip01 {s} upperarm"][:3, 3]
            ahead = 0.28 if s == ("l" if self.camel_side > 0 else "r") else 0.10
            y0, z0 = sh[1] - 0.12, sh[2] + ahead
            near = pts[(np.abs(pts[:, 1] - y0) < 0.10) & (np.abs(pts[:, 2] - z0) < 0.10)]
            if len(near) == 0:
                near = pts[(np.abs(pts[:, 2] - z0) < 0.15)]
            q = near[np.argmax(near[:, 0] * s_out)]
            palm = q + np.array([0.035 * s_out, 0.0, 0.0])
            palm[1] = min(max(palm[1], y0 - 0.10), y0 + 0.10)
            finger = np.array([0.0, 0.75, 0.66])
            finger = finger / np.linalg.norm(finger)
            normal = np.array([-s_out, 0.0, 0.0])
            out[s] = (palm, finger, normal)
        return out

    def gunner(self, p):
        """His worlds (model space) at point `p` of a cycle: walking, leaning in, his palms on the flank;
        the zamburak's right arm as at the gun (the linstock in his hand, low at his side)."""
        u = self.u
        rig = u.rider.rig
        R = self._legs_pose(p)
        if self.key == "zamburak":
            idle = rig.localise(self.a.R_k)
            mine = rig.localise(R)
            keep = {"bip01 r clavicle", "bip01 r upperarm", "bip01 r forearm", "bip01 r hand"}
            locs = [idle[i] if n.lower() in keep or n.lower().startswith("bip01 r finger") else mine[i]
                    for i, n in enumerate(rig.names)]
            R = rig.by_name(rig.worlds(locs))
        for s, (palm, finger, normal) in self.palms.items():
            pole = np.array([0.0, -1.0, 0.0]) + 0.5 * np.array([-self.camel_side, 0.0, 0.0])
            R = u.rider.hand(R, s, palm, finger, normal, pole / np.linalg.norm(pole))
        return R

    def carried(self, R, bone, by, P=None):
        """A gun part the gunner carries (the gun model's local of `bone` on its parent): its frame on his
        bone `by` kept from the deployed clip's first frame."""
        u, a = self.u, self.a
        G0 = u.gun_on(a.P_k, 0.0)
        O = np.linalg.inv(a.R_k[by]) @ G0[bone.lower()]
        Wl = R[by] @ O
        rig = u.gun_rig
        names = [n.lower() for n in rig.names]
        par = rig.names[rig.parents[names.index(bone.lower())]] if bone.lower() in names else None
        H = u.mgc.rigid((a.P_k if P is None else P)[u.camel.hang])
        parent = H @ u.gun_worlds(0.0)[par.lower()] if par else H
        return np.linalg.inv(parent) @ Wl

    # -- the table

    def table(self):
        """(names, [points][bones][7]) of the three parts."""
        from aoe3game.gr2_anim import matrix_quat
        u = self.u
        body = np.zeros((POINTS, len(ct.BODY_BONES), 7))
        gun_names = [b for b, _by in CARRIED[self.key]]
        gunner = np.zeros((POINTS, len(GUNNER_BONES), 7))
        gun = np.zeros((POINTS, len(gun_names), 7))
        for k in range(POINTS):
            p = k / POINTS
            W = self.body(p)
            body[k] = u.camel_track_locals(W)
            P = self.a.composed(body[k])
            R = self.gunner(p)
            locs = u.rider.to_local(R, u.attach(P))
            gunner[k] = [np.r_[locs[u.rindex[n.lower()]][0], locs[u.rindex[n.lower()]][1]] for n in GUNNER_BONES]
            for j, (bone, by) in enumerate(CARRIED[self.key]):
                m = self.carried(R, bone, by, P)
                uu, _s, vt = np.linalg.svd(m[:3, :3])
                gun[k, j] = np.r_[m[:3, 3], matrix_quat(uu @ vt)]
        return (list(ct.BODY_BONES), body), (list(GUNNER_BONES), gunner), (gun_names, gun)


    def rise_tables(self, parts, body_rise):
        """The [K][bones][7] rise tables of the three parts: the body's the aim file's RISE for a turn toward a
        growing heading (it ends on TURN's point 0, the walk's); the gunner stepping from his station to his
        place at the flank, one foot after the other, each lifted FOOT_LIFT, his trunk turning and leaning in
        as he goes; the linstock in his hand."""
        from aoe3game.gr2_anim import matrix_quat
        u, a = self.u, self.a
        rig = u.rider.rig
        K = body_rise.shape[0]
        (_nb, _ab), (ng, ag), (nu, au) = parts
        rg, ru = np.zeros((K, len(ng), 7)), np.zeros((K, len(nu), 7))
        A, B = a.R_k, self.gunner(0.0)
        la, lb = rig.localise(A), rig.localise(B)
        moved = {s: float(np.linalg.norm(B[f"bip01 {s} foot"][:3, 3] - A[f"bip01 {s} foot"][:3, 3])) for s in "lr"}
        first = max(moved, key=moved.get)
        for k in range(K):
            if k == K - 1:
                rg[k], ru[k] = ag[0], (au[0] if len(nu) else ru[k])
                continue
            kk = ct.smooth((k + 1) / K)
            R = rig.by_name(rig.worlds([ct.blend_local(x, y, kk) for x, y in zip(la, lb)]))
            for side in "lr":
                us = ct.smooth(min(max((kk - (0.0 if side == first else 0.5)) / 0.5, 0.0), 1.0))
                f0, f1 = A[f"bip01 {side} foot"], B[f"bip01 {side} foot"]
                pp, qq = ct.blend_local((f0[:3, 3], np.asarray(ct.matrix_quat_of(f0[:3, :3]))),
                                        (f1[:3, 3], np.asarray(ct.matrix_quat_of(f1[:3, :3]))), us)
                m = np.eye(4)
                m[:3, :3] = ct.quat_matrix_of(qq)
                m[:3, 3] = pp
                kn = R[f"bip01 {side} calf"][:3, 3] - 0.5 * (R[f"bip01 {side} thigh"][:3, 3] + R[f"bip01 {side} foot"][:3, 3])
                R = a.foot(R, side, m, ct.FOOT_LIFT * math.sin(math.pi * us), knee=kn)
            P = a.composed(body_rise[k], 0.0, 1.0)
            locs = u.rider.to_local(R, u.attach(P))
            rg[k] = [np.r_[locs[u.rindex[n.lower()]][0], locs[u.rindex[n.lower()]][1]] for n in ng]
            for j, (bone, by) in enumerate(CARRIED[self.key]):
                m = self.carried(R, bone, by, P)
                uu, _s, vt = np.linalg.svd(m[:3, :3])
                ru[k, j] = np.r_[m[:3, 3], matrix_quat(uu @ vt)]
        return np.asarray(body_rise), rg, ru


def name64(s):
    b = s.encode("ascii")[:63]
    return b + b"\0" * (64 - len(b))


def walk_section(stride, rise, settle, rate, clips, parts, rises):
    """The WALK section's bytes. `clips`: the clip names; `parts`: three (bone names, [points][bones][7]);
    `rises`: their [K][bones][7] tables."""
    points = np.asarray(parts[0][1]).shape[0]
    k = np.asarray(rises[0]).shape[0]
    out = [b"WALK", struct.pack("<I5fIII", WALK_VERSION, stride, rise, settle, rate, OFFSET_FROM, points, k,
                                len(clips))]
    out += [name64(c) for c in clips]
    for (names, data), r in zip(parts, rises):
        data = np.asarray(data, np.float32).reshape(points, len(names), 7)
        r = np.asarray(r, np.float32).reshape(k, len(names), 7)
        out += [struct.pack("<I", len(names))] + [ct.name32(n) for n in names]
        out += [data.astype("<f4").tobytes(), r.astype("<f4").tobytes()]
    return b"".join(out)


def read_walk_section(data, at):
    """(stride, rise, settle, rate, from, clips, [(names, array, rise)] x 3, end) of a WALK section at `at`."""
    if data[at:at + 4] != b"WALK":
        raise ValueError("no WALK section here")
    version, stride, rise, settle, rate, frm, points, k, nclips = struct.unpack_from("<I5fIII", data, at + 4)
    if version != WALK_VERSION:
        raise ValueError(f"WALK version {version}")
    at += 40                                       # the tag and its 36-byte header
    clips = [data[at + 64 * i:at + 64 * i + 64].split(b"\0")[0].decode("ascii") for i in range(nclips)]
    at += 64 * nclips
    parts = []
    for _ in range(3):
        (nb,) = struct.unpack_from("<I", data, at)
        at += 4
        names = [data[at + 32 * i:at + 32 * i + 32].split(b"\0")[0].decode("ascii") for i in range(nb)]
        at += 32 * nb
        n = points * nb * 7
        arr = np.frombuffer(data, "<f4", n, at).reshape(points, nb, 7)
        at += 4 * n
        m = k * nb * 7
        r = np.frombuffer(data, "<f4", m, at).reshape(k, nb, 7)
        at += 4 * m
        parts.append((names, arr, r))
    return stride, rise, settle, rate, frm, clips, parts, at


def with_walk(aim, section):
    """The aim file with `section` (WALK) last, in place of a WALK it had there."""
    _turn, end = ct.aim_sections(aim)
    if aim[end:end + 4] == b"WALK":
        if read_walk_section(aim, end)[-1] != len(aim):
            raise ValueError("bytes after the WALK section")
        aim = aim[:end]
    elif end != len(aim):
        raise ValueError(f"the aim file has {len(aim) - end} bytes after its sections")
    return aim + section


def rise_of(aim):
    """The aim file's RISE body table for way 0 ([K][bones][7]) or None."""
    turn, _end = ct.aim_sections(aim)
    if turn is None:
        return None
    _s, _r, _st, _rt, parts, at = ct.read_turn_section(aim, turn)
    if aim[at:at + 4] != b"RISE":
        return None
    body, _g, _at = ct.read_rise_section(aim, at, len(parts[0][0]), len(parts[1][0]))
    return body[0]


# --------------------------------------------------------------------------------------------------
# The replica of the DLL, for the checks and the preview


def smooth_inverse(y):
    """The u in [0, 1] whose smoothstep is y."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ct.smooth(mid) < y else (lo, mid)
    return 0.5 * (lo + hi)


def timeline(cycles, fps=FPS, before=0.3, after=0.3, rise=ct.RISE, settle=ct.SETTLE):
    """[(t, lift, phase, settling)] of a start, `cycles` walking cycles at SPEED and a stop, as the DLL shows
    them: the unit moves from the rise's start to the settling's, the phase by the distance."""
    walk = cycles * STRIDE / SPEED
    total = before + rise + walk + settle + after
    out = []
    for k in range(int(round(total * fps)) + 1):
        t = k / fps
        moving = min(max(t - before, 0.0), rise + walk)
        if t < before:
            lift = 0.0
        elif t < before + rise:
            lift = ct.smooth((t - before) / rise)
        elif t < before + rise + walk:
            lift = 1.0
        else:
            lift = 1.0 - ct.smooth((t - before - rise - walk) / settle)
        # the step counts the way gone since the rise reached OFFSET_FROM (the legs unfolded): it starts with
        # every hoof at home, as the DLL does
        t_from = before + rise * smooth_inverse(OFFSET_FROM)
        s = max(0.0, (min(t, before + rise + walk) - t_from)) * SPEED / STRIDE
        out.append((t, lift, s - math.floor(s), t >= before + rise + walk))
    return out


def offset_weight(lift, settling=False):
    """How much of the walk's step shows at `lift` (the DLL's rule): rising, none until OFFSET_FROM (the
    legs unfold first), all at 1; settling, `lift` (the stride folds away over the whole settle)."""
    if lift >= 1.0:
        return 1.0
    return lift if settling else ct.smooth((lift - OFFSET_FROM) / (1.0 - OFFSET_FROM))


def pose_part(clip_locs, names, index, arr, rise, phase, lift, settling=False):
    """A part's bones over the clip's locals as the DLL poses them: risen, the point at `phase`; rising or
    settling, the rise table's poses (from the clip's) and offset_weight(lift) of the point's offset from
    point 0."""
    locs = list(clip_locs)
    if lift <= 0.0:
        return locs
    row = ct.sample_track(arr[None], 0, phase)
    zero = np.asarray(arr[0], np.float64)
    K = rise.shape[0]
    x = lift * K
    k = min(int(x), K - 1)
    f = x - k
    ow = offset_weight(lift, settling)
    for j, n in enumerate(names):
        i = index[n.lower()]
        if lift >= 1.0:
            locs[i] = (row[j][:3], row[j][3:] / np.linalg.norm(row[j][3:]))
            continue
        base = locs[i] if k == 0 else (rise[k - 1, j, :3], rise[k - 1, j, 3:])
        p, q = ct.blend_local(base, (rise[k, j, :3], rise[k, j, 3:]), f)
        p = p + ow * (row[j, :3] - zero[j, :3])
        d = ct.qmul(row[j, 3:], zero[j, 3:] * np.array([-1.0, -1.0, -1.0, 1.0]))
        if d[3] < 0:
            d = -d
        dl = np.array([0.0, 0.0, 0.0, 1.0]) + ow * (d - np.array([0.0, 0.0, 0.0, 1.0]))
        q = ct.qmul(dl / np.linalg.norm(dl), q)
        locs[i] = (p, q / np.linalg.norm(q))
    return locs


def replica(w, parts, rises, frames, still=False):
    """Per frame (t, lift, phase, settling): (t, camel worlds, gun worlds, rider worlds, rider locals, gun
    locals), the deployed clips playing on, in place (the game moves the unit), as the DLL shows them."""
    u = w.u
    (nb, ab), (ng, ag), (nu, au) = parts
    rb, rg, ru = rises
    length = u.ca.duration
    grig = u.gun_rig
    gidx = {n.lower(): i for i, n in enumerate(grig.names)}
    out = []
    for t, lift, phase, settling in frames:
        tc = 0.0 if still else t % length       # still: the deployed clip held (a loop to check alone)
        P = u.compose(pose_part(u.camel_locals(tc), nb, u.index, ab, rb, phase, lift, settling))
        rl = pose_part(u.rider_locals(tc), ng, u.rindex, ag, rg, phase, lift, settling)
        R = u.rider_worlds(rl, P)
        gl = grig.localise(u.gun_worlds(tc))
        if nu:
            gl = pose_part(gl, nu, gidx, au, ru, phase, lift, settling)
        Gm = grig.by_name(grig.worlds(gl))
        H = u.mgc.rigid(P[u.camel.hang])
        G = {k: H @ v for k, v in Gm.items()}
        out.append((t, P, G, R, rl, gl))
    return out


def write_clips(w, frames, folder, name):
    from aoe3game.gr2_anim import animation_file
    u = w.u
    times = np.array([f[0] for f in frames])
    cam_bytes = u.camel.track_bytes(name + "_camel", times, [f[1] for f in frames], u.ca, u.scales)
    rider_bytes = u.rider.track_bytes(name + "_rider", times, [f[4] for f in frames], u.ra)
    grig = u.gun_rig
    tracks = [(bone, times, np.array([f[5][i][0] for f in frames]), np.array([f[5][i][1] for f in frames]))
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


def job_for(w, clips, rider_model):
    """The check_anim job of a unit's walk: the loop (planted hooves and feet running back at the game's
    speed, the palms on the flank, the gun on its post), and the start and stop for the preview."""
    u = w.u
    job = ct.job_for(w.a, {}, rider_model)
    from aoe3game import gr2_mesh
    upm = gr2_mesh.read(u.rider.data)["units_per_meter"]
    palm = {s: (np.asarray(u.rider.body.palm_local[s]) / upm).tolist() for s in ("l", "r")}
    hand = {s: {"bone": f"rider:bip01 {s} hand", "offset": palm[s]} for s in ("l", "r")}
    jc = {}
    grips = []
    for name, (paths, length) in clips.items():
        loop = name == "walk"
        jc[name] = {"anims": paths, "duration": round(length, 6), "loop": loop,
                    "ground_speed": "auto" if loop else 0.0, "lying": "never" if loop else "ends"}
        frames = [[0.0, length]] if loop else [[0.0, 0.5 / FPS], [length - 0.5 / FPS, length]]
        if loop:
            for s in w.palms:
                grips.append({"name": f"{'left' if s == 'l' else 'right'} palm on the camel's flank", "clips": [name],
                              "hand": hand[s], "grip": {"bone": "camel:hs bone chest", "at": hand[s]},
                              "frames": [[0.0, length]]})
            if w.key == "zamburak":
                grips.append({"name": "right palm on the linstock", "clips": [name], "hand": hand["r"],
                              "grip": {"bone": "gun:bone_linstock", "at": hand["r"]}, "frames": frames})
        else:
            jc[name]["limits"] = {"plant_slip": 1.0, "sink": 0.15}
    jc["deployed (today)"] = job["clips"]["deployed (today)"]
    job["clips"] = jc
    job["grips"] = grips
    job["reasons"] = dict(job["reasons"])
    job["reasons"]["start and stop: plant_slip 1.0"] = (
        "the start and stop bake the DLL's rise and settle in place while the unit already moves: the step counts "
        "the way gone only once the rise reaches OFFSET_FROM (the legs unfolded first), so the hooves stay home "
        "while the ground runs about 0.3 under them in the first 0.26 s of the rise; the walking loop is checked "
        "with the hooves and feet planted")
    job["reasons"]["start and stop: sink 0.15"] = (
        "the stop settles from mid-stride by the DLL's rule (as a turn that ends mid-step): each bone takes the "
        "lift's share of its stride's offset over the rise's pose, and the gunner's right toe goes 11 to 13 cm "
        "under the ground for 2 frames of the 0.45 s settle as his stride folds into his station's pose")
    return job


def load_units(mgc, game, pack):
    return ct.load_units(mgc, game, pack)


def clips_of(key):
    """The clips (body, gunner, gun) on which the walk may show: the deployed idle, the shot and the reload."""
    if key == "gatling":
        parts = ("gatling_camel_camel_B", "gatling_camel_rider_B55", "gatling_camel_gun_B55")
    else:
        parts = ("zamburak_cannon_camel", "zamburak_cannon_rider", "zamburak_cannon_gun")
    return [f"{p}_{c}" for p in parts for c in ("deployed", "fire", "reload")]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--pack", required=True, help="the folder with gatling-camel and zamburak (things-new wol-fixes)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--preview", action="store_true", help="also check_anim's preview of the loop and the start-stop")
    ap.add_argument("--only", default="", help="gatling or zamburak")
    args = ap.parse_args(argv)
    from aoe3game.deploy import RefusedPath, refuse_steam
    try:
        refuse_steam(args.out)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    import make_gun_camel as mgc
    work = tempfile.mkdtemp(prefix="camelwalk_")
    game = mgc.Game(args.game, args.granny_helper, work)
    os.makedirs(args.out, exist_ok=True)
    report, status = {}, 0
    for key, u in load_units(mgc, game, args.pack).items():
        if args.only and key != args.only:
            continue
        w = Walk(key, u)
        body, gunner, gun = w.table()
        rise = rise_of(u.aim)
        if rise is None:
            raise SystemExit(f"{u.aim_path}: no TURN and RISE sections (camel_turn.py --pack first)")
        rises = w.rise_tables((body, gunner, gun), rise)
        section = walk_section(STRIDE, ct.RISE, ct.SETTLE, RATE, clips_of(key), (body, gunner, gun), rises)
        new_aim = with_walk(u.aim, section)
        aim_dir = os.path.join(args.out, "aim")
        os.makedirs(aim_dir, exist_ok=True)
        with open(os.path.join(aim_dir, os.path.basename(u.aim_path)), "wb") as f:
            f.write(new_aim)
        check = os.path.join(args.out, key)
        os.makedirs(check, exist_ok=True)
        rider_model = os.path.join(check, "rider_model.gr2")
        with open(rider_model, "wb") as f:
            f.write(game.granny(u.rider_model))
        clips = {}
        n = int(round(w.cycle * FPS))
        loop = [(k * w.cycle / n, 1.0, k / n, False) for k in range(n + 1)]
        clips["walk"] = write_clips(w, replica(w, (body, gunner, gun), rises, loop, still=True), check, "walk")
        clips["start_stop"] = write_clips(w, replica(w, (body, gunner, gun), rises, timeline(3)), check, "start_stop")
        job = job_for(w, clips, rider_model.replace("\\", "/"))
        job_path = os.path.join(check, "walk_job.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1)
        report[key] = {"aim": os.path.join(aim_dir, os.path.basename(u.aim_path)), "aim bytes": len(new_aim),
                       "section bytes": len(section), "cycle s": round(w.cycle, 3), "camel side": w.camel_side,
                       "gunner moved in": round(float(w.C[0] - w.a.R_k["bip01 root"][0, 3]), 3),
                       "palms": {s: [round(float(x), 3) for x in v[0]] for s, v in w.palms.items()}, "job": job_path}
        if not args.no_check:
            cmd = [sys.executable, "-I", os.path.join(HERE, "check_anim.py"), job_path,
                   "--json", os.path.join(check, "report.json"), "--risk-sheet", os.path.join(check, "risk.png")]
            r = subprocess.run(cmd, capture_output=True, text=True)
            with open(os.path.join(check, "report.txt"), "w", encoding="utf-8") as f:
                f.write(r.stdout + r.stderr)
            report[key]["check exit"] = r.returncode
            status |= r.returncode
            if args.preview:
                r2 = subprocess.run([sys.executable, "-I", os.path.join(HERE, "check_anim.py"), job_path, "--preview",
                                     os.path.join(check, "preview")], capture_output=True, text=True)
                report[key]["preview exit"] = r2.returncode
                with open(os.path.join(check, "preview.txt"), "w", encoding="utf-8") as f:
                    f.write(r2.stdout + r2.stderr)
    print(json.dumps(report, indent=1))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
