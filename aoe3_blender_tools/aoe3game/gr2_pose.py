# SPDX-License-Identifier: GPL-3.0-or-later
"""Poses of a skeleton edited as world frames: branches turned and moved, two poses blended, a
limb solved to a target (two-bone IK), and smooth key interpolation. Pure Python with numpy;
tools/make_dismount.py and tools/make_pray.py use it.

A pose here is {lower-case bone name: 4 x 4 world frame} of a `gr2_anim.Rig` (`Rig.by_name`);
turning a bone's branch moves every bone below it rigidly, as an animator's FK does.

- **Two-bone IK** (`two_bone_ik`): the upper bone keeps its origin, the middle joint goes in the
  plane of the target and a pole direction (the knee forward, the elbow out and down), each of the
  two bones turned so that its direction and its hinge (the normal of the limb's plane, or the
  bone's own hinge axis when the limb is straight) land on the new ones: the bone does not twist
  about its length, and a limb solved to where it already is stays exactly as it was. The end bone's world frame
  is the caller's. A target out of reach is clamped to the limb's length (`ik_reach` tells).
- **Keys** (`Keys`): named channels (numbers or vectors) keyed at times, each component interpolated
  by a monotone cubic (Fritsch and Carlson): no overshoot past a key, a value equal in two keys
  stays exactly constant between them (a planted foot does not drift), the motion eases in and out
  at the first and last key, and passes through the inner keys without stopping when they continue
  the same way.
"""
import math

import numpy as np

from .gr2_anim import axis_quat, slerp
from .gr2_skin import quat_matrix


# --------------------------------------------------------------------------------------------------
# Branches


def descendants(rig, bone):
    """`bone` (lower case) and every bone below it, lower-case names."""
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


def transform_branch(pose, rig, bone, m):
    """`pose` with `bone` and everything below it moved by the world transform `m` (4 x 4)."""
    below = descendants(rig, bone)
    return {k: (m @ w if k in below else w) for k, w in pose.items()}


def about(point, rot):
    """The 4 x 4 transform turning by `rot` (3 x 3) about `point`."""
    m = np.eye(4)
    m[:3, :3] = rot
    m[:3, 3] = np.asarray(point, np.float64) - rot @ np.asarray(point, np.float64)
    return m


def axis_matrix(axis, degrees):
    return quat_matrix(axis_quat(axis, degrees))


def rotate_about(pose, rig, bone, pivot_bone, axis, degrees):
    """`pose` with `bone` and everything below it turned about the world axis through the
    position of `pivot_bone` (both lower-case names)."""
    return transform_branch(pose, rig, bone, about(pose[pivot_bone][:3, 3], axis_matrix(axis, degrees)))


def translate(pose, rig, bone, offset):
    m = np.eye(4)
    m[:3, 3] = offset
    return transform_branch(pose, rig, bone, m)


def set_frame(pose, rig, bone, world):
    """`pose` with `bone` on the world frame `world`, its branch carried along rigidly."""
    return transform_branch(pose, rig, bone, world @ np.linalg.inv(pose[bone]))


def blend(rig, a, b, u):
    """Bone by bone between two poses (world frames): every local frame slerped, the root's
    position interpolated; the result as world frames."""
    la, lb = rig.localise(a), rig.localise(b)
    locs = []
    for (pa, qa), (pb, qb) in zip(la, lb):
        locs.append((pa + u * (pb - pa), slerp(qa, qb, u)))
    return rig.by_name(rig.worlds(locs))


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


# --------------------------------------------------------------------------------------------------
# Frames from directions


def unit(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def basis_of(a, b):
    """An orthonormal 3 x 3 (columns a, b', a x b') from two directions; b is made normal to a."""
    a = unit(a)
    b = unit(np.asarray(b, np.float64) - (np.asarray(b, np.float64) @ a) * a)
    return np.stack([a, b, np.cross(a, b)], axis=1)


def align(a_old, b_old, a_new, b_new):
    """The rotation taking direction a_old to a_new and (the part of) b_old normal to it to b_new."""
    return basis_of(a_new, b_new) @ basis_of(a_old, b_old).T


def local_axis(rot, world_dir):
    """The axis of a frame (one of +-x, +-y, +-z of the 3 x 3 `rot`, in local terms) closest to
    `world_dir`."""
    best, out = -2.0, None
    for i in range(3):
        for s in (1.0, -1.0):
            d = s * rot[:, i] @ unit(world_dir)
            if d > best:
                best, out = d, s * np.eye(3)[i]
    return out


# --------------------------------------------------------------------------------------------------
# Two-bone IK


def ik_reach(pose, upper, middle, end, target):
    """(distance to the target, the limb's length) for the chain upper -> middle -> end."""
    a, b, c = (pose[n][:3, 3] for n in (upper, middle, end))
    return float(np.linalg.norm(np.asarray(target) - a)), float(np.linalg.norm(b - a) + np.linalg.norm(c - b))


def two_bone_ik(pose, rig, upper, middle, end, target, pole, hinge_upper, hinge_middle, end_frame=None):
    """`pose` with the chain upper -> middle -> end solved so that `end` reaches `target` (world
    point), the middle joint toward `pole` (a world direction). `hinge_upper`: the upper bone's
    hinge axis in its local frame (`local_axis`), used when the limb is straight; `hinge_middle` is
    kept for symmetry (the middle bone bends in the limb's plane). `end_frame`: the end bone's world rotation
    (3 x 3), else it keeps its frame relative to the middle bone. Branches below the end bone follow
    it. Returns the new pose."""
    out = dict(pose)
    a, b, c = (pose[n][:3, 3] for n in (upper, middle, end))
    la, lb = np.linalg.norm(b - a), np.linalg.norm(c - b)
    d = np.asarray(target, np.float64) - a
    dist = np.linalg.norm(d)
    dirn = unit(d) if dist > 1e-9 else unit(c - a)
    dist = min(max(dist, abs(la - lb) + 1e-6), la + lb - 1e-6)
    p = np.asarray(pole, np.float64) - (np.asarray(pole, np.float64) @ dirn) * dirn
    if np.linalg.norm(p) < 1e-9:
        p = unit(b - a) - (unit(b - a) @ dirn) * dirn
    p = unit(p)
    cos_a = (la * la + dist * dist - lb * lb) / (2 * la * dist)
    sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
    b_new = a + la * (cos_a * dirn + sin_a * p)
    c_new = a + dist * dirn
    plane = unit(np.cross(dirn, p))                   # the new hinge, normal to the limb's plane
    # the old hinge: the normal of the limb's plane as it is (the bones keep their twist about it,
    # and a limb solved to where it already is does not change at all), or the bone's own hinge
    # axis when the limb is straight
    d_old = unit(c - a)
    bend = (b - a) - ((b - a) @ d_old) * d_old
    if np.linalg.norm(bend) > 1e-3 * la:
        old = unit(np.cross(d_old, bend))
    else:
        old = pose[upper][:3, :3] @ hinge_upper
    if plane @ old < 0:
        plane = -plane
    r_upper = align(unit(b - a), old, unit(b_new - a), plane)
    m_upper = about(a, r_upper)
    r_mid = align(r_upper @ unit(c - b), plane, unit(c_new - b_new), plane)
    below_u = descendants(rig, upper)
    below_m = descendants(rig, middle)
    below_e = descendants(rig, end)
    m_mid = np.eye(4)
    m_mid[:3, :3] = r_mid
    m_mid[:3, 3] = b_new - r_mid @ b_new
    for k in below_u:
        w = m_upper @ pose[k]
        if k in below_m:
            w = m_mid @ w
        out[k] = w
    if end_frame is not None:
        e = out[end].copy()
        e[:3, :3] = end_frame
        e[:3, 3] = c_new
        m_end = e @ np.linalg.inv(out[end])
        for k in below_e:
            out[k] = m_end @ out[k]
    return out


# --------------------------------------------------------------------------------------------------
# Keys


def _monotone_slopes(t, y):
    """Fritsch-Carlson slopes of the points (t, y) (1-D), zero at the ends."""
    n = len(t)
    m = np.zeros(n)
    if n < 2:
        return m
    h = np.diff(t)
    s = np.diff(y) / h
    for i in range(1, n - 1):
        if s[i - 1] * s[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / s[i - 1] + w2 / s[i])
    return m


class Keys:
    """Channels keyed at times: `Keys([(t0, {name: value}), (t1, {...}), ...])`. A key that leaves a
    channel out holds its previous value. `at(t)` gives every channel at time t (clamped to the
    keys' span); a vector channel is interpolated per component."""

    def __init__(self, keys):
        keys = sorted(keys, key=lambda k: k[0])
        self.times = np.array([float(k[0]) for k in keys])
        names = []
        for _t, c in keys:
            names += [n for n in c if n not in names]
        self.channels = {}
        for name in names:
            vals, last, nd = [], None, None
            for _t, c in keys:
                if name in c:
                    if nd is None:
                        nd = np.ndim(c[name])
                    last = np.atleast_1d(np.asarray(c[name], np.float64))
                vals.append(last)
            first = next(v for v in vals if v is not None)   # a key before the first holds that one
            vals = [first if v is None else v for v in vals]
            y = np.stack(vals)
            slopes = np.stack([_monotone_slopes(self.times, y[:, j]) for j in range(y.shape[1])], 1)
            self.channels[name] = (y, slopes, nd)

    @property
    def length(self):
        return float(self.times[-1] - self.times[0])

    def at(self, t):
        ts = self.times
        t = min(max(float(t), ts[0]), ts[-1])
        i = min(max(int(np.searchsorted(ts, t, side="right")) - 1, 0), max(len(ts) - 2, 0))
        out = {}
        for name, (y, m, nd) in self.channels.items():
            if len(ts) == 1:
                v = y[0]
            else:
                h = ts[i + 1] - ts[i]
                s = (t - ts[i]) / h
                h00, h10 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s
                h01, h11 = -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
                v = h00 * y[i] + h10 * h * m[i] + h01 * y[i + 1] + h11 * h * m[i + 1]
            out[name] = float(v[0]) if nd == 0 else v.copy()
        return out

    def segment(self, t):
        """(index of the key span holding t, its share 0..1 eased) for per-span effects."""
        ts = self.times
        t = min(max(float(t), ts[0]), ts[-1])
        i = min(max(int(np.searchsorted(ts, t, side="right")) - 1, 0), max(len(ts) - 2, 0))
        h = ts[i + 1] - ts[i] if len(ts) > 1 else 1.0
        return i, (t - ts[i]) / h if h > 0 else 0.0
