# SPDX-License-Identifier: GPL-3.0-or-later
"""Granny animations of the game read, posed, moved to another skeleton and written again. Pure
Python with numpy; tools/make_dismount.py uses it.

- **Curves.** The game's animation files (Granny 2.5) keep each track as the old curve type
  {Degree, Knots, Controls}: a B-spline whose control i belongs to knot i. Read from granny2.dll
  (`GrannySampleBSpline1x1` and `2x1`, disassembled, 2026-11-21): on the span k[i-1] <= t <= k[i],
  degree 1 is (1 - u) P[i-1] + u P[i] with u = (t - k[i-1]) / (k[i] - k[i-1]); degree 2 weighs
  P[i-2], P[i-1], P[i] with the de Boor weights of the knots k[i-2] .. k[i+1]. That is a standard
  B-spline whose control m is P[m + 1]; `sample` evaluates it for any degree (ends clamped: the
  runtime's own padding of the ends is not read, and the stock files put a knot a hair after the
  first, so the ends are the first and last controls to within float noise). Orientations are
  quaternions (x, y, z, w), normalised after sampling.
- **Bases.** Each file says its axes and units (ArtToolInfo); `Basis.convert_*` brings positions and
  frames from one to another as Granny's basis conversion does (a similarity: positions scaled and
  turned, frames conjugated; a mirror between the two is allowed).
- **Poses.** A bone's local frame is translate(position) x rotate(orientation) (gr2_skin); a track
  replaces both for its bone, a bone with no track keeps its rest frame; a world frame is its
  parent's times its own.
- **Retargeting** puts one skeleton's world frames on another's bones of the same name
  (`localise`): two bipeds of one rig convention that differ in hierarchy (a rider whose thighs hang
  from the spine, a footman whose hang from the pelvis) then show the same pose.
- **Writing** (`animation_file`): one track group, every track as degree-1 curves on its sampled
  times (degree 0 when it never moves), in the basis given.
"""
import bisect
import math
import struct

import numpy as np

from . import gr2
from .gr2_skin import quat_matrix
from .gr2_types import schema
from .gr2_write import EXPORTER, IDENTITY_TRANSFORM, STOCK_BASIS, W, Flat, serialize

# --------------------------------------------------------------------------------------------------
# Quaternions (x, y, z, w) and frames (4 x 4, column vectors)


def matrix_quat(m):
    """The quaternion (x, y, z, w) of a 3 x 3 rotation."""
    m = np.asarray(m, np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = (0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s)
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s)
    q = np.array(q)
    return q / np.linalg.norm(q)


def slerp(a, b, u):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    d = float(a @ b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + u * (b - a)
        return q / np.linalg.norm(q)
    th = math.acos(min(1.0, d))
    s = math.sin(th)
    return (math.sin((1 - u) * th) * a + math.sin(u * th) * b) / s


def axis_quat(axis, degrees):
    axis = np.asarray(axis, np.float64)
    axis = axis / np.linalg.norm(axis)
    h = math.radians(degrees) / 2
    return np.array([*(axis * math.sin(h)), math.cos(h)])


def frame(position, quat):
    m = np.eye(4)
    m[:3, :3] = quat_matrix(quat)
    m[:3, 3] = position
    return m


def split(m):
    """(position, quaternion) of a rigid 4 x 4 frame."""
    return np.array(m[:3, 3]), matrix_quat(m[:3, :3])


# --------------------------------------------------------------------------------------------------
# Bases


class Basis:
    """A file's axes and units: right, up and back vectors and units per metre."""

    def __init__(self, right, up, back, upm):
        self.right, self.up, self.back = (np.asarray(v, np.float64) for v in (right, up, back))
        self.upm = float(upm)

    @classmethod
    def of(cls, root):
        art = root.get("ArtToolInfo")
        if art is None:
            b = STOCK_BASIS
            return cls(b["right"], b["up"], b["back"], b["units_per_meter"])
        return cls(art.get("RightVector"), art.get("UpVector"), art.get("BackVector"),
                   art.get("UnitsPerMeter"))

    def to(self, other):
        """(3 x 3 axes C, scale s): a point p of this basis is s * C @ p in `other`."""
        mine = np.stack([self.right, self.up, self.back])          # rows: physical axes in file terms
        theirs = np.stack([other.right, other.up, other.back])
        return theirs.T @ mine, other.upm / self.upm


STOCK = Basis(STOCK_BASIS["right"], STOCK_BASIS["up"], STOCK_BASIS["back"],
              STOCK_BASIS["units_per_meter"])


def convert_frame(m, c, s):
    out = np.eye(4)
    out[:3, :3] = c @ m[:3, :3] @ c.T
    out[:3, 3] = s * (c @ m[:3, 3])
    return out


# --------------------------------------------------------------------------------------------------
# Curves


def _floats(blob):
    raw = getattr(blob, "raw", b"") if blob not in (None, []) else b""
    return np.frombuffer(raw, "<f4").astype(np.float64) if raw else np.zeros(0)


class Curve:
    def __init__(self, degree, knots, controls):
        self.degree = int(degree or 0)
        self.knots = np.asarray(knots, np.float64)
        n = len(self.knots)
        self.dim = len(controls) // n if n else 0
        self.controls = np.asarray(controls, np.float64).reshape(n, self.dim) if n else np.zeros((0, 0))

    @classmethod
    def of(cls, obj):
        return cls(obj.get("Degree"), _floats(obj.get("Knots")), _floats(obj.get("Controls")))

    def empty(self):
        return len(self.knots) == 0

    def sample(self, t):
        """The curve's value at time t (see the module's note)."""
        k, p, n, d = self.knots, self.controls, len(self.knots), self.degree
        if n == 0:
            return None
        if n == 1:
            return p[0].copy()
        j = bisect.bisect_right(k, t) - 1
        j = min(max(j, 0), n - 1)
        if d == 0:
            return p[min(j + 1, n - 1) if t > k[j] else j].copy()

        def kn(i):
            return k[min(max(i, 0), n - 1)]

        def pt(m):                      # standard control m is the file's control m + 1
            return p[min(max(m + 1, 0), n - 1)]

        dd = [pt(j - d + r).copy() for r in range(d + 1)]
        for r in range(1, d + 1):
            for i in range(d, r - 1, -1):
                lo = kn(j - d + i)
                hi = kn(j + 1 + i - r)
                a = 0.0 if hi - lo <= 1e-12 else (t - lo) / (hi - lo)
                dd[i] = (1 - a) * dd[i - 1] + a * dd[i]
        return dd[d]


class Track:
    def __init__(self, name, position, orientation):
        self.name, self.position, self.orientation = name, position, orientation

    def local(self, t, rest):
        """(position, quaternion) at time t; a missing part is the rest frame's."""
        rp, rq = rest
        p = self.position.sample(t) if self.position is not None else None
        q = self.orientation.sample(t) if self.orientation is not None else None
        if q is not None:
            q = q / (np.linalg.norm(q) or 1.0)
        return (rp if p is None else p), (rq if q is None else q)


class Animation:
    """The first animation of a file: its duration and its tracks by bone name (lower case)."""

    def __init__(self, root):
        self.basis = Basis.of(root)
        anims = root.get("Animations") or []
        groups = root.get("TrackGroups") or []
        if not groups:
            raise gr2.Gr2Error("no track group")
        a = anims[0] if anims else None
        self.name = a.get("Name") if a is not None else ""
        self.duration = float(a.get("Duration")) if a is not None else 0.0
        self.timestep = float(a.get("TimeStep") or 1 / 60) if a is not None else 1 / 60
        g = groups[0]
        self.group_name = g.get("Name")
        self.accumulation = int(g.get("AccumulationFlags") or 0)
        self.tracks = {}
        for tr in g.get("TransformTracks") or []:
            if tr is None:
                continue
            self.tracks[tr.get("Name").lower()] = Track(
                tr.get("Name"), Curve.of(tr.get("PositionCurve")), Curve.of(tr.get("OrientationCurve")))

    @classmethod
    def load(cls, data):
        return cls(gr2.load(data).root())


# --------------------------------------------------------------------------------------------------
# Skeletons and poses


class Rig:
    """A skeleton: names, parents and rest frames (position, quaternion) per bone, in its basis."""

    def __init__(self, names, parents, rest, basis):
        self.names, self.parents, self.rest, self.basis = list(names), list(parents), list(rest), basis
        self.index = {n.lower(): i for i, n in enumerate(self.names)}

    @classmethod
    def of(cls, root, skeleton=0):
        sk = (root.get("Skeletons") or [])[skeleton]
        names, parents, rest = [], [], []
        for b in sk.get("Bones"):
            t = b.get("Transform")
            flags = int(t.get("flags") or 0)
            pos = np.array(t["position"], np.float64) if flags & 1 else np.zeros(3)
            q = np.array(t["orientation"], np.float64) if flags & 2 else np.array([0, 0, 0, 1.0])
            names.append(b.get("Name"))
            parents.append(int(b.get("ParentIndex")))
            rest.append((pos, q / np.linalg.norm(q)))
        return cls(names, parents, rest, Basis.of(root))

    def has(self, name):
        return name.lower() in self.index

    def worlds(self, locals_):
        """World frames from a list of local (position, quaternion), in bone order."""
        out = []
        for i, (p, q) in enumerate(locals_):
            m = frame(p, q)
            par = self.parents[i]
            out.append(out[par] @ m if par >= 0 else m)
        return out

    def rest_worlds(self):
        return self.worlds(self.rest)

    def pose(self, anim, t, basis=None):
        """World frames of every bone at time t of `anim`, in `basis` (default the rig's).
        The animation is brought to the rig's basis first (positions scaled and turned)."""
        c, s = anim.basis.to(self.basis)
        locs = []
        for i, name in enumerate(self.names):
            tr = anim.tracks.get(name.lower())
            if tr is None:
                locs.append(self.rest[i])
                continue
            p, q = tr.local(t, (None, None))
            rp, rq = self.rest[i]
            if p is None:
                p = rp
            else:
                p = s * (c @ p)
            if q is None:
                q = rq
            else:
                q = matrix_quat(c @ quat_matrix(q) @ c.T)
            locs.append((p, q))
        worlds = self.worlds(locs)
        if basis is not None and basis is not self.basis:
            c2, s2 = self.basis.to(basis)
            worlds = [convert_frame(w, c2, s2) for w in worlds]
        return worlds

    def by_name(self, worlds):
        return {n.lower(): w for n, w in zip(self.names, worlds)}

    def localise(self, world_by_name, fallback=None):
        """Local (position, quaternion) per bone that put each bone of this rig on the world frame of
        the bone of the same name (lower case keys); a bone with none keeps its frame relative to
        its parent from `fallback` (world frames of this rig by name) or its rest."""
        worlds, locs = [], []
        for i, name in enumerate(self.names):
            par = self.parents[i]
            w = world_by_name.get(name.lower())
            if w is None:
                if fallback is not None and name.lower() in fallback:
                    w = fallback[name.lower()]
                else:
                    w = (worlds[par] if par >= 0 else np.eye(4)) @ frame(*self.rest[i])
            worlds.append(w)
            loc = np.linalg.inv(worlds[par]) @ w if par >= 0 else w
            p, q = split(loc)
            locs.append((p, q))
        return locs


# --------------------------------------------------------------------------------------------------
# Writing


def _constant(values, eps):
    return np.abs(values - values[0]).max() <= eps if len(values) else True


def animation_file(name, duration, group_name, tracks, *, basis=STOCK, accumulation=2,
                   timestep=1 / 60, source=""):
    """Bytes of a .gr2 animation. `tracks`: [(bone name, times, positions N x 3, quaternions N x 4)]
    in `basis`; each part becomes a degree-1 curve on those times, or degree 0 when it never moves."""
    S = schema()

    def curve(deg, knots, controls):
        knots = [float(k) for k in knots]
        controls = [float(v) for v in np.asarray(controls).ravel()]
        return {"Degree": deg,
                "Knots": Flat(S["Real32"], struct.pack(f"<{len(knots)}f", *knots), len(knots)),
                "Controls": Flat(S["Real32"], struct.pack(f"<{len(controls)}f", *controls),
                                 len(controls))}

    out = []
    for bone, times, pos, quats in tracks:
        pos = np.asarray(pos, np.float64)
        quats = np.array(quats, np.float64)
        for i in range(1, len(quats)):                 # one hemisphere, so each span is the short way
            if quats[i] @ quats[i - 1] < 0:
                quats[i] = -quats[i]
        pc = curve(0, [0.0], pos[:1]) if _constant(pos, 1e-5) else curve(1, times, pos)
        oc = curve(0, [0.0], quats[:1]) if _constant(quats, 1e-6) else curve(1, times, quats)
        out.append(W(S["TransformTrack"], Name=bone, PositionCurve=pc, OrientationCurve=oc,
                     ScaleShearCurve=curve(0, [], [])))
    group = W(S["TrackGroup"], Name=group_name, VectorTracks=[], TransformTracks=out,
              TransformLODErrors=[], TextTracks=[], InitialPlacement=IDENTITY_TRANSFORM,
              AccumulationFlags=accumulation, LoopTranslation=(0.0, 0.0, 0.0))
    anim = W(S["Animation"], Name=source or name, Duration=float(duration), TimeStep=float(timestep),
             Oversampling=1.0, TrackGroups=[group])
    root = W(S["FileInfo"],
             ArtToolInfo=W(S["ArtToolInfo"], FromArtToolName=STOCK_BASIS["name"],
                           ArtToolMajorRevision=STOCK_BASIS["major"],
                           ArtToolMinorRevision=STOCK_BASIS["minor"],
                           UnitsPerMeter=basis.upm, Origin=(0.0, 0.0, 0.0),
                           RightVector=tuple(basis.right), UpVector=tuple(basis.up),
                           BackVector=tuple(basis.back)),
             ExporterInfo=W(S["ExporterInfo"], ExporterName=EXPORTER, ExporterMajorRevision=2,
                            ExporterMinorRevision=5, ExporterCustomization=0,
                            ExporterBuildNumber=1),
             FromFileName=source or name, Textures=[], Materials=[], Skeletons=[],
             VertexDatas=[], TriTopologies=[], Meshes=[], Models=[], TrackGroups=[group],
             Animations=[anim])
    return serialize(root)
