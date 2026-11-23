# SPDX-License-Identifier: GPL-3.0-or-later
"""Praying animations for the game's villagers, made from key poses on the villager's own skeleton:
three designs, each an entry (from the idle), a seamless loop and an exit (back to the idle), for
the male and the female villager.

    venv\\Scripts\\python -I tools/make_pray.py --game <game copy> --out <folder>
        [--design 1,2,3] [--sex male,female] [--granny-helper <exe>] [--no-verify]
        [--preview <png>] [--gifs <folder>] [--gif-fps 10] [--frames 6]

The designs:
1. `kneel`: from the idle the villager steps back with the right foot, sets the right knee down,
   then the left, joins the hands before the chest and bows the head; the loop rocks very
   slightly (10 s); the exit stands up the same way back.
2. `standing`: hands joined at the chest, head bowed; once a loop (12 s) the right hand makes the
   sign of the cross (forehead, chest, left shoulder, right shoulder) while the left rests on the
   chest.
3. `bow`: kneels as in 1 and sits back on the heels, hands on the thighs; the loop (10 s) bows down
   to the ground (forehead near it, hands flat in front) and comes back up.

What it writes below --out: `art\\<folder>\\<prefix>pray<N>_in.gr2`, `..._loop.gr2`, `..._out.gr2`
for each sex (the male clips on `units\\villagers\\we_villager_male`, the female ones on
`we_villager_female`: every villager model of a sex shares its skeleton), `pray-anims.xml` (the
`<anim>` blocks, for later), and `pray-report.txt` (the checks below, per clip). --preview draws a
sheet of key frames (each design's entry, loop and exit, both sexes, a 3/4 and a side view);
--gifs one GIF per design (both sexes side by side, entry, loop, exit).

How (aoe3game/gr2_pose.py): every frame is a set of channels (the root's place and pitch, the
spine, neck and head bends, each foot's toe point, heel lift and heading, each hand's palm centre,
finger and palm directions and elbow pole) keyed at times and interpolated without overshoot
(`Keys`); the legs and arms are solved by two-bone IK to the feet and hands, so a planted foot does
not move at all, a foot that rises on its toes turns about its toe tip, and a step lifts the toe
before it travels. A kneeling key puts each knee on the ground in front of its foot and the hips on
the thigh's angle above it (the knee's height measured on the skinned mesh). A hand going elsewhere
swings out in front of the body on the way. The idle's first frame is the entry's first and the
exit's last frame; the loop's first frame is the entry's last, the loop's last and the exit's first.

Checks (pray-report.txt; the tool exits 1 when one fails): every joint frame equal where two clips
meet and at the loop's ends; no contact point of a foot (toe tip, heel) moving along the ground
while on it; no vertex under the ground but the leg's cloth (the female's skirt hem is bound to the
calves and goes under it when she kneels: reported, not checked); no vertex of a hand or forearm
deeper than ARM_DEPTH inside the body, or than the idle's own (a ray cast through the skinned
body's triangles); and, unless --no-verify, each written file read back by
this repository's reader (the same pose at every frame) and by the game's granny2.dll through the
helper of recompress_models.py: its CRC, the runtime reading it, and the runtime compressing it
(Oodle1) and expanding it back to the same bytes.

Compressed game files are expanded by the game's own Granny runtime (`--granny-helper`, default
tools\\granny_recompress.exe; `python -I tools/recompress_models.py --build-helper` makes it);
nothing of the game is stored. Refuses a Steam folder as output.
"""
import argparse
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
from aoe3game import gr2, gr2_mesh, gr2_skin  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import Animation, Rig, animation_file  # noqa: E402
from aoe3game.gr2_pose import (Keys, about, axis_matrix, basis_of, local_axis, set_frame,  # noqa: E402
                               transform_branch, translate, two_bone_ik, unit)

LIB = "animation_library\\"
FOLDER = "WoL\\units\\villagers\\settler\\pray"
SEXES = {
    "male": {"model": "units\\villagers\\we_villager_male", "idle": LIB + "villager\\villager_male_idle",
             "prefix": "villager_male_"},
    "female": {"model": "units\\villagers\\we_villager_female", "idle": LIB + "villager\\villager_female_idle",
               "prefix": "villager_female_"},
}
DESIGNS = {1: "kneel", 2: "standing", 3: "bow"}
FPS = 30
GROUND = 0.012            # a knee's lowest vertex above the ground when it rests on it
X = (1.0, 0.0, 0.0)       # the villager's right (file axes: x right, y up, z the way he faces)
Y = (0.0, 1.0, 0.0)
Z = (0.0, 0.0, 1.0)
SIDES = ("l", "r")
LEG = {s: (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot") for s in SIDES}
ARM = {s: (f"bip01 {s} upperarm", f"bip01 {s} forearm", f"bip01 {s} hand") for s in SIDES}
TORSO = ("bip01", "bip01 pelvis", "bip01 spine", "bip01 spine1", "bip01 neck", "bip01 head",
         "bip01 l clavicle", "bip01 r clavicle", "bip01 ponytail1", "bip01 ponytail11")
ARM_BONES = ("bip01 l forearm", "bip01 r forearm", "bip01 l hand", "bip01 r hand")
MARKERS = ("bone hitpointbar",)


# --------------------------------------------------------------------------------------------------
# The villager's body


class Body:
    """A villager model: skeleton, mesh, the idle's first frame and what the poses need measured on
    the mesh (each foot's toe tip and heel, each hand's palm centre and directions)."""

    def __init__(self, rig, mesh, idle_pose, idle_anim=None):
        self.rig, self.mesh, self.base = rig, mesh, idle_pose
        self.idle_anim = idle_anim
        self.names = {n.lower(): n for n in rig.names}
        self.skel = mesh["skel"]
        m = mesh["mesh"]
        names = [n.lower() for n in m["skin_names"]]
        self.dominant = np.array([names[int(b[int(np.argmax(w))])] for b, w in
                                  zip(m["vertex_bones4"], m["vertex_weights4"])])
        rest = rig.by_name(rig.rest_worlds())
        pts = np.asarray(m["file_positions"], np.float64)
        # feet: toe tip and heel on the sole, in the foot's local frame
        self.toe_local, self.heel_local = {}, {}
        for s in SIDES:
            foot = LEG[s][2]
            sel = pts[self.dominant == foot]
            inv = np.linalg.inv(rest[foot])
            sole = sel[:, 1].min()
            low = sel[sel[:, 1] <= sole + 0.03]
            tip = low[np.argmax(low[:, 2])]
            heel = low[np.argmin(low[:, 2])]
            self.toe_local[s] = (inv @ np.r_[tip[0], sole, tip[2], 1.0])[:3]
            self.heel_local[s] = (inv @ np.r_[heel[0], sole, heel[2], 1.0])[:3]
        # hands: palm centre, finger direction (wrist to centre), palm normal (toward the body at rest)
        self.palm_local, self.finger_local, self.normal_local, self.tip_local = {}, {}, {}, {}
        self.hand_local = {}
        for s in SIDES:
            hand = ARM[s][2]
            sel = pts[self.dominant == hand]
            inv = np.linalg.inv(rest[hand])
            loc = (np.c_[sel, np.ones(len(sel))] @ inv.T)[:, :3]
            centre = loc.mean(0)
            f = unit(centre)
            _u, _s, vt = np.linalg.svd(loc - centre)
            n = vt[-1] - (vt[-1] @ f) * f
            n = unit(n)
            inward = rest[hand][:3, :3].T @ np.array([-1.0 if s == "r" else 1.0, 0.0, 0.0])
            if n @ inward < 0:
                n = -n
            self.palm_local[s], self.finger_local[s], self.normal_local[s] = centre, f, n
            self.tip_local[s] = loc[int(np.argmax(loc @ f))]
            self.hand_local[s] = loc
        self.hinge = {}
        for s in SIDES:
            for b in LEG[s][:2] + ARM[s][:2]:
                self.hinge[b] = local_axis(self.base[b][:3, :3], X)
        self.torso_tris = self._tris(TORSO + tuple(b for s in SIDES for b in LEG[s][:2]))
        self.arm_vertices = np.isin(self.dominant, ARM_BONES)
        self.leg_vertices = {s: np.isin(self.dominant, LEG[s][:2]) for s in SIDES}

    def _tris(self, bones):
        tris = self.mesh["mesh"]["triangles"]
        ok = np.isin(self.dominant, bones)
        return tris[ok[tris].all(1)]

    # -- what the base pose says

    def channels(self):
        """The idle's first frame as channels (the entry's first key and the exit's last)."""
        b = self.base
        c = {"root": b["bip01"][:3, 3].copy(), "pitch": 0.0, "spine": 0.0, "spine1": 0.0,
             "neck": 0.0, "head": 0.0, "roll": 0.0}
        for s in SIDES:
            foot = b[LEG[s][2]]
            c[s + "toe"] = (foot @ np.r_[self.toe_local[s], 1.0])[:3]
            c[s + "lift"] = 0.0
            c[s + "turn"] = 0.0
            hip, knee, ankle = (b[n][:3, 3] for n in LEG[s])
            line = unit(ankle - hip)
            off = (knee - hip) - ((knee - hip) @ line) * line
            c[s + "knee"] = unit(off) if np.linalg.norm(off) > 1e-3 else np.array(Z)
            hand = b[ARM[s][2]]
            c[s + "palm"] = (hand @ np.r_[self.palm_local[s], 1.0])[:3]
            c[s + "finger"] = hand[:3, :3] @ self.finger_local[s]
            c[s + "normal"] = hand[:3, :3] @ self.normal_local[s]
            up, fore = b[ARM[s][0]][:3, 3], b[ARM[s][1]][:3, 3]
            wrist = hand[:3, 3]
            mid = up + ((fore - up) @ unit(wrist - up)) * unit(wrist - up)
            c[s + "elbow"] = unit(fore - mid) if np.linalg.norm(fore - mid) > 1e-3 else np.array([0.3, -0.3, -1.0])
        return c

    def heading(self, s):
        """The base foot's heading, degrees about the vertical (0: toes toward +z, the front)."""
        f = self.base[LEG[s][2]]
        d = (f @ np.r_[self.toe_local[s], 1.0])[:3] - (f @ np.r_[self.heel_local[s], 1.0])[:3]
        return math.degrees(math.atan2(d[0], d[2]))

    # -- a pose from channels

    def pose(self, c):
        rig, P = self.rig, dict(self.base)
        root = np.asarray(c["root"], np.float64)
        P = translate(P, rig, "bip01", root - P["bip01"][:3, 3])
        lean = axis_matrix(X, c["pitch"]) @ axis_matrix(Z, c.get("roll", 0.0))
        P = transform_branch(P, rig, "bip01", about(root, lean))
        for bone, key in (("bip01 spine", "spine"), ("bip01 spine1", "spine1")):
            P = transform_branch(P, rig, bone, about(P[bone][:3, 3], axis_matrix(X, c[key])))
        neck = P["bip01 neck"][:3, 3]
        for bone in ("bip01 neck", "bip01 head"):
            P = transform_branch(P, rig, bone, about(neck, axis_matrix(X, c["neck"])))
        P = transform_branch(P, rig, "bip01 head", about(P["bip01 head"][:3, 3], axis_matrix(X, c["head"])))
        for s in SIDES:
            thigh, calf, foot = LEG[s]
            rot, ankle = self.foot_frame(s, c)
            P = two_bone_ik(P, rig, thigh, calf, foot, ankle, c[s + "knee"], self.hinge[thigh],
                            self.hinge[calf], end_frame=rot)
        chest = P["bip01 spine1"] @ np.linalg.inv(self.base["bip01 spine1"])
        for s in SIDES:
            palm = (chest @ np.r_[c[s + "palm"], 1.0])[:3]
            P = self.place_hand(P, s, palm, chest[:3, :3] @ np.asarray(c[s + "finger"], np.float64),
                                chest[:3, :3] @ np.asarray(c[s + "normal"], np.float64),
                                chest[:3, :3] @ np.asarray(c[s + "elbow"], np.float64))
        for m in MARKERS:
            if m in P:
                P = set_frame(P, rig, m, self.base[m])
        return P

    def place_hand(self, P, s, palm, finger, normal, pole):
        """`P` with the arm of side `s` solved (two-bone IK) so that the hand's palm centre is at
        `palm` with its fingers toward `finger` and its palm facing `normal` (world terms), the
        elbow toward `pole`. tools/make_gun_camel.py uses it for a rider's hands on a gun."""
        up, fore, hand = ARM[s]
        rot = basis_of(finger, normal) @ basis_of(self.finger_local[s], self.normal_local[s]).T
        wrist = np.asarray(palm, np.float64) - rot @ self.palm_local[s]
        return two_bone_ik(P, self.rig, up, fore, hand, wrist, pole, self.hinge[up], self.hinge[fore], end_frame=rot)

    def foot_frame(self, s, c):
        """(world rotation, ankle position) of a foot: its idle frame turned about the vertical by
        `turn` and its heel raised by `lift` degrees about the toe tip at `toe`."""
        base = self.base[LEG[s][2]]
        r = axis_matrix(Y, c[s + "turn"])
        heel_up = axis_matrix(r @ self._lateral(s), c[s + "lift"])
        rot = heel_up @ r @ base[:3, :3]
        ankle = np.asarray(c[s + "toe"], np.float64) - rot @ self.toe_local[s]
        return rot, ankle

    def _lateral(self, s):
        f = self.base[LEG[s][2]]
        d = (f @ np.r_[self.toe_local[s], 1.0])[:3] - (f @ np.r_[self.heel_local[s], 1.0])[:3]
        d[1] = 0.0
        return unit(np.cross(Y, unit(d)))       # the heel goes up for a positive angle about it

    # -- the skinned mesh

    def points(self, pose):
        exact = {self.names[k]: w for k, w in pose.items() if k in self.names}
        m = self.mesh["mesh"]
        return gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"],
                               m["skin_names"], self.skel, exact)

    def contacts(self, pose):
        """{(side, 'toe'|'heel'): world point} of the feet."""
        out = {}
        for s in SIDES:
            f = pose[LEG[s][2]]
            out[(s, "toe")] = (f @ np.r_[self.toe_local[s], 1.0])[:3]
            out[(s, "heel")] = (f @ np.r_[self.heel_local[s], 1.0])[:3]
        return out

    def kneel(self, c, sides=SIDES, thigh=0.0):
        """`c` with the root placed for kneeling on the knees of `sides`: each knee on the ground in
        front of its foot (the shin from the ankle the foot channels give), the thigh `thigh` degrees
        from the vertical (positive: the hips behind the knees, sitting back). The knee's height is
        found on the skinned mesh: its lowest vertex near the joint GROUND above the ground."""
        offsets = {s: self.base[LEG[s][0]][:3, 3] - self.base["bip01"][:3, 3] for s in SIDES}
        lengths = {s: (np.linalg.norm(self.base[LEG[s][1]][:3, 3] - self.base[LEG[s][0]][:3, 3]),
                       np.linalg.norm(self.base[LEG[s][2]][:3, 3] - self.base[LEG[s][1]][:3, 3])) for s in SIDES}
        th = math.radians(thigh)
        lift = {s: 0.06 for s in sides}
        out = dict(c)
        for _ in range(4):
            roots = []
            for s in sides:
                lt, lc = lengths[s]
                _rot, a = self.foot_frame(s, c)
                dy = a[1] - lift[s]
                knee = np.array([a[0], lift[s], a[2] + math.sqrt(max(lc * lc - dy * dy, 0.0))])
                hip = knee + lt * np.array([0.0, math.cos(th), -math.sin(th)])
                roots.append(hip - offsets[s])
            root = np.mean(roots, 0)
            if len(sides) == 2:
                root[0] = c["root"][0]
            out["root"] = root
            p = self.pose(out)
            pts = self.points(p)
            for s in sides:
                k = p[LEG[s][1]][:3, 3]
                near = self.leg_vertices[s] & (np.linalg.norm(pts - k, axis=1) < 0.2)
                lift[s] -= pts[near, 1].min() - GROUND
        return out

    def settle_bow(self, c, floor=0.035):
        """`c` with the body's pitch raised until the head's lowest vertex is `floor` above the
        ground (the forehead near it)."""
        head = np.isin(self.dominant, ("bip01 head",))

        def low(pitch):
            cc = dict(c)
            cc["pitch"] = pitch
            return self.points(self.pose(cc))[head, 1].min()
        lo, hi = 0.0, 140.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if low(mid) > floor:
                lo = mid
            else:
                hi = mid
        out = dict(c)
        out["pitch"] = 0.5 * (lo + hi)
        return out

    def inside(self, pts, pose, depth=0.0):
        """[(index, depth)] of the arm vertices inside the body deeper than `depth`: a ray along the
        chest's front and one along its back both cross the body's triangles an odd number of
        times; the depth is the nearer of the two first crossings."""
        fwd = unit(pose["bip01 spine1"][:3, :3] @ (self.base["bip01 spine1"][:3, :3].T @ np.array(Z)))
        tris = pts[self.torso_tris]
        out = []
        for i in np.nonzero(self.arm_vertices)[0]:
            o = pts[i]
            ahead, behind = _hits(o, fwd, tris), _hits(o, -fwd, tris)
            if len(ahead) % 2 == 1 and len(behind) % 2 == 1:
                d = min(ahead.min(), behind.min())
                if d > depth:
                    out.append((int(i), float(d)))
        return out


def _hits(o, d, tris):
    """The distances t > 0 at which the ray o + t d crosses the triangles (N x 3 x 3)."""
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    p = np.cross(d, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - v0
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(1) * inv
    t = (q * e2).sum(1) * inv
    return t[ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)]


def _first_hit(o, d, tris):
    t = _hits(o, d, tris)
    return float(t.min()) if len(t) else None


# --------------------------------------------------------------------------------------------------
# The designs: channels keyed at times


KNEEL_SPANS = [{}, {"r": 0.10}, {}, {"l": 0.08}, {}]


def kneel_keys(body, sit=False):
    """The entry of designs 1 and 3: [(time, channels)] and the foot lifts per span. The weight
    goes onto the left foot, the right foot steps back onto its toes, the right knee goes down,
    the left foot steps back beside it and its knee goes down; then the hands join and the head
    bows (design 1), or the villager sits back on the heels, hands on the thighs (design 3)."""
    c0 = body.channels()
    lt = c0["ltoe"]
    width = 0.12
    toe_z = -0.58                      # the toes tucked under there: the knees come down near the centre
    tuck = 62.0                        # heel up about the toe tip
    k = [(0.0, dict(c0))]
    # 1. the weight onto the left foot, a slight bend
    c1 = dict(c0, root=np.array([lt[0] * 0.45, c0["root"][1] - 0.03, c0["root"][2] - 0.02]), pitch=4.0,
              spine1=2.0, head=4.0)
    c1.update(low_hands(body, c1))
    k.append((0.6, c1))
    # 2. the right foot stepped back onto its toes, the body lowering over the left leg
    c2 = dict(c1, rtoe=np.array([width, 0.0, toe_z]), rlift=40.0, rturn=-body.heading("r"),
              root=np.array([lt[0] * 0.3, c0["root"][1] - 0.25, -0.12]), pitch=9.0, spine1=3.0,
              lknee=np.array([-0.2, 0.0, 1.0]))
    k.append((1.4, c2))
    # 3. the right knee down: a lunge on the left foot
    c3 = body.kneel(dict(c2, rlift=tuck, pitch=7.0, rknee=np.array([0.05, 0.0, 1.0])), ("r",), thigh=8.0)
    k.append((2.4, c3))
    # 4. the left foot back beside the right, both knees down
    c4 = body.kneel(dict(c3, ltoe=np.array([-width, 0.0, toe_z]), llift=tuck, lturn=-body.heading("l"),
                         pitch=2.0, lknee=np.array([-0.05, 0.0, 1.0]), root=np.array([0.0, 0.6, 0.0])), thigh=4.0)
    k.append((3.3, c4))
    if not sit:
        c5 = dict(c4, **pray_hands(body, c4), pitch=3.0, spine=2.0, spine1=3.0, neck=12.0, head=14.0)
        k.append((4.2, c5))
        return k, KNEEL_SPANS
    # 5. sitting back on the heels (the knees kept on the ground half way), hands on the thighs
    c5 = body.kneel(dict(c4, pitch=-4.0, spine=5.0, spine1=3.0, neck=8.0, head=10.0), thigh=52.0)
    c5.update(thigh_hands(body, c5))
    half = body.kneel(dict(c4, pitch=-1.0, spine=3.0, spine1=2.0, neck=5.0, head=6.0), thigh=28.0)
    half.update({k: 0.5 * (np.asarray(c4[k]) + np.asarray(c5[k])) for k in c5
                 if k[1:] in ("palm", "finger", "normal", "elbow")})
    k.append((3.9, half))
    k.append((4.6, c5))
    return k, KNEEL_SPANS + [{}]


def chest_point(body, y_share, x=0.0, ahead=0.0):
    """A point on the front of the body in the idle's frame: `y_share` between the pelvis (0) and
    the neck (1), `x` to the side, `ahead` in front of the front surface (a ray cast from the front
    onto the skinned body)."""
    b = body.base
    pel, neck = b["bip01 pelvis"][:3, 3], b["bip01 neck"][:3, 3]
    p = pel + y_share * (neck - pel)
    p[0] += x
    tris = body.points(b)[body.torso_tris]
    front = _first_hit(np.array([p[0], p[1], p[2] + 3.0]), np.array([0.0, 0.0, -1.0]), tris)
    z = p[2] + 3.0 - front if front is not None else p[2] + 0.15
    return np.array([p[0], p[1], z + ahead])


def pray_hands(body, c, height=0.80, ahead=0.22, gap=0.012):
    """Channels for the hands joined before the chest: palms together, fingers up and a little
    forward, elbows out and down."""
    centre = chest_point(body, height, 0.0, ahead)
    out = {}
    for s in SIDES:
        side = 1.0 if s == "r" else -1.0
        out[s + "palm"] = centre + np.array([side * gap, 0.0, 0.0])
        out[s + "finger"] = unit((0.0, 1.0, 0.45))
        out[s + "normal"] = np.array([-side, 0.0, 0.0])
        out[s + "elbow"] = unit((side * 1.0, -0.8, 0.35))
    return out


def low_hands(body, c):
    """Channels for the hands brought together loosely before the belly (while kneeling down and
    standing up: off the hips, clear of the thighs)."""
    centre = chest_point(body, 0.55, 0.0, 0.25)
    out = {}
    for s in SIDES:
        side = 1.0 if s == "r" else -1.0
        out[s + "palm"] = centre + np.array([side * 0.07, 0.0, 0.0])
        out[s + "finger"] = unit((-side * 0.3, -0.2, 1.0))
        out[s + "normal"] = unit((-side, 0.3, 0.0))
        out[s + "elbow"] = unit((side * 1.0, -0.8, -0.4))
    return out


def thigh_hands(body, c, clearance=0.015):
    """Channels for the hands resting on the thighs (sitting on the heels), in the idle's frame:
    each palm over the middle of its thigh, its lowest vertex `clearance` above the leg's (or the
    skirt's) surface there (a ray cast from above onto the skinned body)."""
    p = body.pose(c)
    chest = p["bip01 spine1"] @ np.linalg.inv(body.base["bip01 spine1"])
    inv = np.linalg.inv(chest)
    tris = body.points(p)[body.torso_tris]
    out = {}
    for s in SIDES:
        side = 1.0 if s == "r" else -1.0
        thigh, calf, _foot = LEG[s]
        mid = 0.62 * p[calf][:3, 3] + 0.38 * p[thigh][:3, 3] + np.array([side * 0.01, 0.0, 0.0])
        top = np.array([mid[0], mid[1] + 3.0, mid[2]])
        hit = _first_hit(top, np.array([0.0, -1.0, 0.0]), tris)
        surface = top[1] - hit if hit is not None else mid[1] + 0.1
        finger, normal = unit((-side * 0.15, -0.25, 1.0)), np.array([0.0, -1.0, 0.0])
        rot = basis_of(finger, normal) @ basis_of(body.finger_local[s], body.normal_local[s]).T
        under = min((rot @ (v - body.palm_local[s]))[1] for v in body.hand_local[s])
        palm = np.array([mid[0], surface + clearance - under, mid[2]])
        out[s + "palm"] = (inv @ np.r_[palm, 1.0])[:3]
        out[s + "finger"] = inv[:3, :3] @ finger
        out[s + "normal"] = inv[:3, :3] @ normal
        out[s + "elbow"] = unit((side * 0.4, 0.0, -1.0))
    return out


def ground_hands(body, c, reach=0.42, width=0.17, height=0.01):
    """Channels for the hands flat on the ground in front of the knees, in the idle's frame (the
    chest's frame of that pose taken back)."""
    p = body.pose(c)
    chest = p["bip01 spine1"] @ np.linalg.inv(body.base["bip01 spine1"])
    inv = np.linalg.inv(chest)
    knee_z = 0.5 * (p["bip01 l calf"][2, 3] + p["bip01 r calf"][2, 3])
    out = {}
    for s in SIDES:
        side = 1.0 if s == "r" else -1.0
        finger, normal = unit((-side * 0.2, 0.0, 1.0)), np.array([0.0, -1.0, 0.0])
        # the palm raised so that the hand's lowest vertex is `height` above the ground
        rot = basis_of(finger, normal) @ basis_of(body.finger_local[s], body.normal_local[s]).T
        under = min((rot @ (v - body.palm_local[s]))[1] for v in body.hand_local[s])
        palm = np.array([side * width, height - under, knee_z + reach])
        out[s + "palm"] = (inv @ np.r_[palm, 1.0])[:3]
        out[s + "finger"] = inv[:3, :3] @ finger
        out[s + "normal"] = inv[:3, :3] @ normal
        out[s + "elbow"] = inv[:3, :3] @ unit((side * 0.8, 0.5, -0.4))
    return out


class Clip:
    """One animation: channels keyed at times, per-span foot lifts ({side: height} of the span that
    ends at each key), and periodic additions (a function of time giving channel offsets)."""

    def __init__(self, name, keys, lifts=None, waves=None, length=None, arc=0.12):
        self.name, self.arc = name, arc
        self.keys = Keys(keys)
        self.lifts = lifts or []
        self.waves = waves
        self.length = float(length if length is not None else self.keys.times[-1])

    def at(self, t):
        c = self.keys.at(t)
        if self.lifts:
            i, s = self.keys.segment(t)
            span = self.lifts[i][1] if i < len(self.lifts) else {}
            for side, h in span.items():
                # a step: the toe rises first, travels, and comes down where it lands (its path
                # along the ground eased inside the middle of the span, so it never moves on it)
                y = self.keys.channels[side + "toe"][0]
                a, b = y[i], y[min(i + 1, len(y) - 1)]
                u = min(max(s, 0.0), 1.0)
                w = min(max((u - STEP_IN) / (1.0 - 2 * STEP_IN), 0.0), 1.0)
                w = w * w * (3 - 2 * w)
                toe = a + w * (b - a)
                toe[1] += h * math.sin(math.pi * u)
                c[side + "toe"] = toe
        if self.arc and len(self.keys.times) > 1:
            # a hand going somewhere else swings out in front of the body on the way (forward and
            # to its side, in the idle's frame), so it does not pass through the hips or the chest
            i, u = self.keys.segment(t)
            u = min(max(u, 0.0), 1.0)
            for side in SIDES:
                y = self.keys.channels[side + "palm"][0]
                a, b = y[i], y[min(i + 1, len(y) - 1)]
                d = float(np.linalg.norm(b - a))
                if d > 1e-6:
                    out = unit((0.45 if side == "r" else -0.45, 0.0, 1.0))
                    c[side + "palm"] = c[side + "palm"] + out * self.arc * min(1.0, d / 0.25) * math.sin(math.pi * u)
        if self.waves is not None:
            for k, v in self.waves(t).items():
                c[k] = c[k] + v
        return c


STEP_IN = 0.18            # the share of a step's span the toe only rises (and only comes down)


def ease_wave(t, period, amp):
    """A wave that is 0 with no speed at t = 0 and at every whole period: amp (1 - cos) / 2."""
    return amp * 0.5 * (1.0 - math.cos(2 * math.pi * t / period))


def reverse(keys, lifts, total):
    """Keys played backward over the same spans (the exit from the entry), lifts moved with them."""
    out = [(total - t, c) for t, c in reversed(keys)]
    spans = [lifts[i][1] for i in range(len(lifts))]
    # the span that ended at key i now ends at key (n - i), i.e. it is span (n - 1 - i) of the new list
    n = len(keys) - 1
    new_lifts = [(None, spans[n - 1 - j] if 0 <= n - 1 - j < len(spans) else {}) for j in range(n)]
    return out, new_lifts


def retime(keys, scale):
    return [(t * scale, c) for t, c in keys]


def design(body, number):
    """[entry, loop, exit] Clips of a design for this body."""
    if number == 1:
        keys, spans = kneel_keys(body)
        lifts = [(None, sp) for sp in spans[:len(keys) - 1]]
        top = keys[-1][1]
        entry = Clip("pray1_in", keys, lifts)

        def waves(t):
            return {"pitch": ease_wave(t, 5.0, 2.5), "spine1": ease_wave(t, 10.0 / 3, 1.2),
                    "head": ease_wave(t, 5.0, -1.5) + ease_wave(t, 10.0, 2.5)}
        loop = Clip("pray1_loop", [(0.0, top), (10.0, top)], waves=waves, length=10.0)
        out_keys, out_lifts = reverse(keys, lifts, keys[-1][0])
        exit_ = Clip("pray1_out", retime(out_keys, 0.85), out_lifts)
        return [entry, loop, exit_]
    if number == 2:
        c0 = body.channels()
        lt, rt = c0["ltoe"], c0["rtoe"]
        mid = 0.5 * (lt + rt)
        top = dict(c0, **pray_hands(body, c0), root=np.array([mid[0] * 0.6, c0["root"][1] - 0.015, c0["root"][2]]),
                   pitch=3.0, spine=2.0, spine1=3.0, neck=12.0, head=16.0)
        bow = dict(c0, **{k: v for k, v in top.items() if k in ("pitch", "neck", "head")})
        entry = Clip("pray2_in", [(0.0, c0), (1.0, bow), (1.8, top)])
        loop = Clip("pray2_loop", cross_keys(body, top), waves=lambda t: {
            "spine1": ease_wave(t, 4.0, 1.0), "head": ease_wave(t, 6.0, 1.5), "pitch": ease_wave(t, 12.0, 1.0)},
            length=12.0)
        exit_ = Clip("pray2_out", [(0.0, top), (0.8, bow), (1.8, c0)])
        return [entry, loop, exit_]
    if number == 3:
        keys, spans = kneel_keys(body, sit=True)
        lifts = [(None, sp) for sp in spans[:len(keys) - 1]]
        up = keys[-1][1]
        entry = Clip("pray3_in", keys, lifts)
        loop = Clip("pray3_loop", bow_keys(body, up), waves=lambda t: {"spine1": ease_wave(t, 10.0 / 3, 0.8)},
                    length=10.0, arc=0.0)
        out_keys, out_lifts = reverse(keys, lifts, keys[-1][0])
        exit_ = Clip("pray3_out", retime(out_keys, 0.85), out_lifts)
        return [entry, loop, exit_]
    raise ValueError(number)


def cross_keys(body, top):
    """The standing loop: the joined hands held, then the sign of the cross with the right hand
    (forehead, chest, left shoulder, right shoulder) while the left rests on the chest, then the
    hands joined again (12 s)."""
    pose = body.pose(top)
    head = pose["bip01 head"]
    chest = pose["bip01 spine1"] @ np.linalg.inv(body.base["bip01 spine1"])
    inv = np.linalg.inv(chest)
    pts = body.points(pose)
    head_pts = pts[body.dominant == "bip01 head"]
    # the forehead: the head's foremost vertex in its upper part, seen in the idle's frame
    hl = (np.c_[head_pts, np.ones(len(head_pts))] @ np.linalg.inv(head).T)[:, :3]
    top_y = np.percentile(hl @ (head[:3, :3].T @ np.array(Y)), 70)
    upper = head_pts[(hl @ (head[:3, :3].T @ np.array(Y))) >= top_y - 0.02]
    brow = upper[np.argmax(upper[:, 2])]
    forehead = (inv @ np.r_[brow, 1.0])[:3]

    def touch(point, finger, ahead=0.02, elbow=(1.0, -0.8, -0.2)):
        """Right-hand channels with the fingertips (the hand's farthest vertex from the wrist) on
        `point`, `ahead` out of the body, the palm toward it."""
        f, n = unit(finger), np.array([0.0, 0.0, -1.0])
        rot = basis_of(f, n) @ basis_of(body.finger_local["r"], body.normal_local["r"]).T
        palm = point + np.array([0.0, 0.0, ahead]) - rot @ (body.tip_local["r"] - body.palm_local["r"])
        return {"rpalm": palm, "rfinger": f, "rnormal": n, "relbow": unit(elbow)}
    sternum = chest_point(body, 0.70, 0.0, 0.0)
    l_sh = chest_point(body, 0.86, -0.15, 0.0)
    r_sh = chest_point(body, 0.86, 0.15, 0.0)
    left_rest = {"lpalm": chest_point(body, 0.55, -0.02, 0.05), "lfinger": unit((1.0, 0.35, 0.0)),
                 "lnormal": np.array([0.0, 0.0, -1.0]), "lelbow": unit((-1.0, -0.8, -0.3))}
    joined = {k: v for k, v in top.items()}
    k = [(0.0, joined), (5.0, joined)]
    k.append((5.8, dict(joined, **touch(forehead, (0.0, 1.0, -0.25), 0.02), **left_rest, head=10.0)))
    k.append((6.5, dict(joined, **touch(sternum, (0.0, 1.0, -0.3), 0.04), **left_rest, head=14.0)))
    k.append((7.1, dict(joined, **touch(l_sh, (-0.6, 0.8, -0.2), 0.08, (1.0, -0.5, 0.5)), **left_rest, head=14.0)))
    k.append((7.7, dict(joined, **touch(r_sh, (0.3, 1.0, -0.2), 0.04, (1.0, -1.0, -0.1)), **left_rest, head=14.0)))
    k.append((8.7, joined))
    k.append((12.0, joined))
    return k


def bow_keys(body, up):
    """The bow loop: from sitting on the heels the hips rise over the knees, the body bows until
    the forehead is near the ground and the hands go flat on it; held, then back up (10 s)."""
    low = body.kneel(dict(up, spine=12.0, spine1=10.0, neck=12.0, head=10.0, pitch=60.0), thigh=12.0)
    low = body.settle_bow(low)
    low.update(ground_hands(body, low))
    mid = body.kneel(dict(up, pitch=0.45 * low["pitch"], spine=8.0, spine1=6.0, neck=10.0, head=10.0), thigh=30.0)
    # the hands half way: in front of the knees, above the ground
    mid.update(ground_hands(body, mid, reach=0.28, height=0.16))
    return [(0.0, up), (1.3, mid), (2.6, low), (4.4, low), (5.9, mid), (7.4, up), (10.0, up)]


# --------------------------------------------------------------------------------------------------
# Sampling, checks and writing


def sample(body, clip, fps=FPS):
    n = max(2, int(round(clip.length * fps)) + 1)
    times = np.linspace(0.0, clip.length, n)
    return times, [body.pose(clip.at(t)) for t in times]


def pose_gap(a, b):
    return max(float(np.abs(a[k] - b[k]).max()) for k in a)


ARM_DEPTH = 0.035          # how deep a hand or forearm vertex may sit in the body (a hand resting on it)
SLIDE = 0.004              # how far a foot's contact point may move along the ground between frames


def check_clip(body, times, poses):
    """{check: value} of one clip: the foot contacts' slide along the ground; the lowest vertex of
    the body but its leg skin and root-bound cloth (a skirt or coat tail hangs from them and may
    meet the ground), and of the knees (the leg skin near the knee joints); the deepest hand or
    forearm vertex inside the body; the lowest leg-skin vertex (a skirt), for information."""
    slide, lowest, knees, skirt, inside, worst = 0.0, 1e9, 1e9, 1e9, 0.0, None
    cloth = np.isin(body.dominant, [b for s in SIDES for b in LEG[s][:2]] + ["bip01"])
    prev = None
    for t, p in zip(times, poses):
        cs = body.contacts(p)
        if prev is not None:
            for key, q in cs.items():
                a = prev[key]
                if a[1] < 0.02 and q[1] < 0.02:
                    slide = max(slide, float(np.hypot(q[0] - a[0], q[2] - a[2])))
        prev = cs
        pts = body.points(p)
        lowest = min(lowest, float(pts[~cloth, 1].min()))
        skirt = min(skirt, float(pts[cloth, 1].min()))
        for s in SIDES:
            near = body.leg_vertices[s] & (np.linalg.norm(pts - p[LEG[s][1]][:3, 3], axis=1) < 0.2)
            if near.any():
                knees = min(knees, float(pts[near, 1].min()))
        deep = max((d for _i, d in body.inside(pts, p)), default=0.0)
        if deep > inside:
            inside, worst = deep, float(t)
    return {"foot slide": slide, "lowest vertex": lowest, "lowest knee": knees, "lowest cloth": skirt,
            "arm depth inside": inside, "worst frame": worst}


def check_ok(chk, body):
    """Whether a clip passes: the arm depth is allowed up to ARM_DEPTH, or to the idle's own (the
    female villager's idle rests the hands on the hips, a little into the skirt)."""
    pts = body.points(body.base)
    idle = max((d for _i, d in body.inside(pts, body.base)), default=0.0)
    return (chk["foot slide"] <= SLIDE and chk["lowest vertex"] >= -0.015 and chk["lowest knee"] >= -0.015
            and chk["arm depth inside"] <= max(ARM_DEPTH, idle + 0.005))


def clip_bytes(body, name, times, poses, idle):
    frames = [body.rig.localise(p) for p in poses]
    tracks = []
    for i, bone in enumerate(body.rig.names):
        tracks.append((bone, times, np.array([f[i][0] for f in frames]), np.array([f[i][1] for f in frames])))
    return animation_file(name, float(times[-1]), body.rig.names[0], tracks, basis=body.rig.basis,
                          accumulation=idle.accumulation if idle is not None else 2,
                          timestep=idle.timestep if idle is not None else 1 / 60, source=name)


def read_back(body, data, times, poses):
    """The largest difference between the poses and the file's, read with this repository's reader."""
    a = Animation.load(data)
    worst = 0.0
    for t, p in zip(times, poses):
        q = body.rig.by_name(body.rig.pose(a, float(t)))
        worst = max(worst, pose_gap(p, q))
    return worst


def runtime_check(data, runtime, tag):
    """The game's granny2.dll on the file: (crc ok, read, compressed and expanded back). Raises
    on a refusal."""
    import recompress_models as rm
    crc = runtime.crc_ok(data, tag)
    status, lines = runtime.info(data, tag)
    read = status == 0 and not any(line.startswith("refused") for line in lines)
    packed, _targets = rm.recompress(data, runtime, rm.FORMATS["oodle1"], None, tag)
    return crc, read, len(packed)


# --------------------------------------------------------------------------------------------------
# Drawing


def figure(game, rel):
    import retarget_anims as ra
    return ra.Figure(game, rel)


def ground_items(size=2.6, y=0.0):
    pts = np.array([[-size, y, -size], [size, y, -size], [size, y, size], [-size, y, size]], np.float64)
    tris = np.array([[0, 1, 2], [0, 2, 3]])
    return [(pts, tris, None, None, (196, 200, 186))]


def picture(figs, poses, width, height, azimuth, spacing=1.0, span=2.9, centre_y=0.95, elevation=14.0):
    """The figures (with their poses) side by side across the view, on a ground plane."""
    import retarget_anims as ra
    az = math.radians(azimuth)
    view = np.array([math.sin(az), 0.0, math.cos(az)])
    right = unit(np.cross(Y, view))
    items = ground_items()
    n = len(figs)
    for i, (fig, pose) in enumerate(zip(figs, poses)):
        off = (i - (n - 1) / 2) * spacing * right
        place = np.eye(4)
        place[:3, 3] = off
        items += fig.items(pose, place)
    return ra.draw(items, width=width, height=height, azimuth=azimuth, elevation=elevation, span=span,
                   centre=(0.0, centre_y, -0.1))


def caption(img, text, scale=1):
    import bitfont
    out = img.copy()
    band = 9 * scale + 5
    out[-band:, :] = (40, 40, 40)
    bitfont.draw(out, text, 4, out.shape[0] - band + 3, (255, 255, 255), scale=scale)
    return out


def title_band(width, text, scale=2, colour=(255, 255, 255), back=(30, 30, 30)):
    import bitfont
    h = 7 * scale + 10
    band = np.full((h, width, 3), back, np.uint8)
    bitfont.draw(band, text, 6, 5, colour, scale=scale)
    return band


def preview_sheet(path, designs, figs, frames=6):
    """For each design: a row per sex and view, `frames` moments of the entry, of the loop and of
    the exit, captioned with the part and the time."""
    import bitfont
    import retarget_anims as ra
    w, h = 132, 168
    blocks = []
    for number, built in designs.items():
        rows = []
        for sex, parts in built.items():
            for az, view in ((-40.0, "3/4"), (-90.0, "SIDE")):
                tiles = []
                for part, (times, poses) in zip(("IN", "LOOP", "OUT"), parts):
                    n = frames if part != "LOOP" else frames + 2
                    for i in np.linspace(0, len(times) - 1, n).round().astype(int):
                        img = picture([figs[sex]], [poses[i]], w, h, az, span=2.5, centre_y=0.95)
                        tiles.append(caption(img, f"{part} {times[i]:.1f}S"))
                    tiles.append(np.full((h, 6, 3), 255, np.uint8))
                head = np.full((h, 64, 3), 255, np.uint8)
                bitfont.draw(head, sex.upper(), 4, 64, (40, 40, 40))
                bitfont.draw(head, view, 4, 80, (40, 40, 40))
                rows.append(np.concatenate([head] + tiles, 1))
        blocks.append((number, rows))
    width = max(r.shape[1] for _n, rows in blocks for r in rows)
    out = [title_band(width, "VILLAGER PRAYING - PREVIEW (MALE: WE_VILLAGER_MALE, FEMALE: WE_VILLAGER_FEMALE)",
                      back=(70, 40, 20))]
    for number, rows in blocks:
        out.append(title_band(width, f"DESIGN {number} - {DESIGNS[number].upper()}: ENTRY (IN), LOOP, EXIT (OUT)"))
        for r in rows:
            pad = np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)
            out.append(np.concatenate([r, pad], 1))
    ra.save_png(path, np.concatenate(out, 0))


def gif(path, number, built, figs, fps=10, width=420, height=330):
    """Both sexes side by side, 3/4 view: the entry, the loop and the exit, captioned."""
    from PIL import Image
    seq = []
    male, female = built["male"], built["female"]
    for part, (mt, mp), (_ft, fp) in zip(("ENTRY", "LOOP", "EXIT"), male, female):
        step = max(1, int(round(FPS / fps)))
        for i in range(0, len(mt), step):
            j = min(i, len(fp) - 1)
            img = picture([figs["male"], figs["female"]], [mp[i], fp[j]], width, height, -38.0, spacing=1.25,
                          span=2.6, centre_y=0.95)
            seq.append(caption(img, f"DESIGN {number} {DESIGNS[number].upper()}  {part} {mt[i]:.1f}S", 1))
    frames = [Image.fromarray(f).quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
              for f in seq]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    return os.path.getsize(path)


# --------------------------------------------------------------------------------------------------


def anim_blocks(numbers, sexes):
    """The `<anim>` blocks for the villager's anim file (names proposed: PrayIn, Pray, PrayOut)."""
    out = []
    for number in numbers:
        for sex in sexes:
            pre = SEXES[sex]["prefix"]
            out.append(f"<!-- design {number} ({DESIGNS[number]}), {sex} -->")
            for anim, part in (("PrayIn", "in"), ("Pray", "loop"), ("PrayOut", "out")):
                out.append(f"\t<anim>{anim}\n\t\t<assetreference type=\"GrannyAnim\">\n"
                           f"\t\t\t<file>{FOLDER}\\{pre}pray{number}_{part}</file>\n\t\t</assetreference>\n"
                           f"\t\t<component>ModelComp</component>\n\t</anim>")
    return "\n".join(out) + "\n"


def load_body(game, sex):
    spec = SEXES[sex]
    data = game.granny(spec["model"])
    rig = Rig.of(gr2.load(data).root())
    read = gr2_mesh.read(data)
    idle = Animation.load(game.granny(spec["idle"]))
    base = rig.by_name(rig.pose(idle, 0.0))
    return Body(rig, {"mesh": read["meshes"][0], "skel": read["skeletons"][0]}, base, idle)


def build(body, numbers):
    """{design: [(times, poses) of entry, loop, exit]}, {design: [Clip]}"""
    out, clips = {}, {}
    for n in numbers:
        cl = design(body, n)
        clips[n] = cl
        out[n] = [sample(body, c) for c in cl]
    return out, clips


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--design", default="1,2,3")
    ap.add_argument("--sex", default="male,female")
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--no-verify", action="store_true", help="skip the read-back and the runtime checks")
    ap.add_argument("--preview")
    ap.add_argument("--gifs")
    ap.add_argument("--gif-fps", type=int, default=10)
    ap.add_argument("--frames", type=int, default=6)
    args = ap.parse_args(argv)
    try:
        refuse_steam(args.out)
        for p in (args.preview, args.gifs):
            if p:
                refuse_steam(p)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    numbers = [int(x) for x in args.design.split(",")]
    sexes = [s for s in args.sex.split(",") if s]
    if any(n not in DESIGNS for n in numbers) or any(s not in SEXES for s in sexes):
        print("--design takes 1,2,3 and --sex male,female", file=sys.stderr)
        return 2
    import make_dismount as md
    work = tempfile.mkdtemp(prefix="pray_work_")
    failed = False
    report = []
    try:
        game = md.Game(args.game, args.granny_helper, work)
        runtime = None
        if not args.no_verify:
            import recompress_models as rm
            runtime = rm.Runtime(args.granny_helper, os.path.join(args.game, "granny2.dll"), work)
        folder = os.path.join(args.out, "art", FOLDER)
        os.makedirs(folder, exist_ok=True)
        built, figs = {}, {}
        for sex in sexes:
            body = load_body(game, sex)
            figs[sex] = figure(game, SEXES[sex]["model"])
            samples, clips = build(body, numbers)
            idle_pose = body.base
            for n in numbers:
                built.setdefault(n, {})[sex] = samples[n]
                (it, ip), (lt, lp), (ot, op) = samples[n]
                seams = {"idle to entry": pose_gap(idle_pose, ip[0]), "entry to loop": pose_gap(ip[-1], lp[0]),
                         "loop ends": pose_gap(lp[0], lp[-1]), "loop to exit": pose_gap(lp[-1], op[0]),
                         "exit to idle": pose_gap(op[-1], idle_pose)}
                bad = {k: v for k, v in seams.items() if v > 1e-4}
                report.append(f"design {n} {DESIGNS[n]} {sex}: seams " +
                              ", ".join(f"{k} {v:.1e}" for k, v in seams.items()) + (" FAIL" if bad else " ok"))
                failed |= bool(bad)
                for clip, (times, poses) in zip(clips[n], samples[n]):
                    name = SEXES[sex]["prefix"] + clip.name
                    data = clip_bytes(body, name, times, poses, body.idle_anim)
                    with open(os.path.join(folder, name + ".gr2"), "wb") as f:
                        f.write(data)
                    chk = check_clip(body, times, poses)
                    ok = check_ok(chk, body)
                    line = (f"  {name}.gr2 {times[-1]:.2f} s {len(times)} frames {len(data)} B: foot slide "
                            f"{chk['foot slide']:.4f}, lowest vertex {chk['lowest vertex']:.3f}, lowest knee "
                            f"{chk['lowest knee']:.3f}, arm depth in body {chk['arm depth inside']:.3f}"
                            + (f" (at {chk['worst frame']:.2f} s)" if chk["worst frame"] is not None else "")
                            + f", lowest leg cloth {chk['lowest cloth']:.3f}")
                    if runtime is not None:
                        back = read_back(body, data, times, poses)
                        crc, read, packed = runtime_check(data, runtime, f"{sex[0]}{n}{clip.name[-2:]}")
                        line += f"; read back {back:.1e}; runtime crc {crc}, read {read}, oodle1 {packed} B and back"
                        ok &= back < 1e-3 and crc and read
                    report.append(line + ("" if ok else "  FAIL"))
                    failed |= not ok
                    print(report[-1])
        with open(os.path.join(args.out, "pray-report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        with open(os.path.join(args.out, "pray-anims.xml"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(anim_blocks(numbers, sexes))
        if args.preview and len(sexes) == 2:
            preview_sheet(args.preview, built, figs, args.frames)
            print(args.preview)
        if args.gifs and len(sexes) == 2:
            os.makedirs(args.gifs, exist_ok=True)
            for n in numbers:
                path = os.path.join(args.gifs, f"p-pray-{n}-{DESIGNS[n]}.gif")
                size = gif(path, n, built[n], figs, args.gif_fps)
                print(f"{path} {size / 1e6:.1f} MB")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
