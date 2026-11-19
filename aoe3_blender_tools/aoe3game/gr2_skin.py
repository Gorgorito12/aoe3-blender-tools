# SPDX-License-Identifier: GPL-3.0-or-later
"""A Granny skeleton and skin as they are: every bone's local and world frame with its rotation
followed, the bind pose the file stores, and up to four bones and weights per vertex. Pure Python
with numpy; gr2_mesh.read uses it, the Blender import builds an armature from it.

Measured on the uncompressed models of a Wars of Liberty copy (2026-11-19, 129 skinned files of
600 drawn at random): a bone's local frame is translate(Position) x rotate(Orientation, the
quaternion x y z w) x ScaleShear, each part only when its flag is set (1 position, 2 orientation,
4 scale and shear); its world frame is its parent's world frame times its local one; and the stored
InverseWorldTransform (row vectors, translation in the last row) is the inverse of that world
frame, to 1e-3, in 125 of the 129 (97 %). The rest pose of a unit is its bind pose. `matches`
says which skeletons hold to it.
"""
import numpy as np

FLAG_POSITION, FLAG_ORIENTATION, FLAG_SCALE = 1, 2, 4
TOLERANCE = 1e-3


def quat_matrix(q):
    """3 x 3 rotation of a Granny quaternion (x, y, z, w), normalised."""
    x, y, z, w = (float(c) for c in q)
    n = (x * x + y * y + z * z + w * w) ** 0.5 or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def local_matrix(transform):
    """4 x 4 (column vectors) of a bone's Transform {flags, position, orientation, scale_shear}."""
    m = np.eye(4)
    flags = int(transform.get("flags") or 0)
    r = quat_matrix(transform["orientation"]) if flags & FLAG_ORIENTATION else np.eye(3)
    s = np.array(transform["scale_shear"], np.float64).reshape(3, 3) if flags & FLAG_SCALE else np.eye(3)
    m[:3, :3] = r @ s
    if flags & FLAG_POSITION:
        m[:3, 3] = transform["position"]
    return m


def skeletons(root):
    """[{name, bones: [{name, parent, local, world, bind}], matches}] of a file's root, in the
    file's own axes and units; matrices 4 x 4 for column vectors. `bind` is the inverse of the
    stored InverseWorldTransform (None when missing or singular); `matches` is True when every
    bone's world frame equals its bind frame within TOLERANCE."""
    out = []
    for sk in root.get("Skeletons") or []:
        if sk is None:
            continue
        bones, worlds, ok = [], [], True
        for b in sk.get("Bones") or []:
            if b is None:
                continue
            loc = local_matrix(b.get("Transform") or {})
            parent = b.get("ParentIndex")
            parent = int(parent) if parent is not None else -1
            world = worlds[parent] @ loc if 0 <= parent < len(worlds) else loc
            worlds.append(world)
            bind = None
            iwt = b.get("InverseWorldTransform")
            if iwt and len(iwt) == 16:
                try:
                    bind = np.linalg.inv(np.array(iwt, np.float64).reshape(4, 4)).T
                except np.linalg.LinAlgError:
                    bind = None
            if bind is None or np.abs(world - bind).max() > TOLERANCE * max(1.0, np.abs(bind[:3, 3]).max()):
                ok = False
            bones.append({"name": b.get("Name"), "parent": parent, "local": loc, "world": world, "bind": bind})
        out.append({"name": sk.get("Name"), "bones": bones, "matches": ok})
    return out


def basis_matrix(right, up, back, upm):
    """(3 x 3 axes, 1 / units per metre) taking the file's axes to Blender's: x = p.right,
    y = -p.back, z = p.up (gr2_mesh.to_blender)."""
    c = np.array([right, [-v for v in back], up], np.float64)
    return c, 1.0 / float(upm)


def to_blender_frame(m, right, up, back, upm):
    """A 4 x 4 frame (column vectors) of the file in Blender's axes and metres: the axes
    conjugated, the translation converted and scaled. A frame scaled in the file stays scaled."""
    c, k = basis_matrix(right, up, back, upm)
    out = np.eye(4)
    out[:3, :3] = c @ m[:3, :3] @ np.linalg.inv(c)
    out[:3, 3] = (c @ m[:3, 3]) * k
    return out


def vertex_skin(vs, count, packed_raw=None):
    """(bones N x 4, weights N x 4) of a vertex array: the indices into its mesh's bone bindings,
    heaviest first, and their weights adding up to 1; -1 where a slot is empty. `packed_raw`: the
    bytes of a packed FD stream (two bones a vertex, gr2_mesh.packed_skin). None when the array
    has no weights (a rigid mesh, bound whole to its first binding)."""
    from . import gr2_mesh
    if packed_raw is not None:
        b2, w2 = gr2_mesh.packed_skin(packed_raw)
        bones = np.full((len(b2), 4), -1, np.int64)
        weights = np.zeros((len(b2), 4), np.float32)
        bones[:, :2], weights[:, :2] = b2, w2
        return bones, weights
    idx = gr2_mesh._column(vs, "BoneIndices", 4)
    wts = gr2_mesh._column(vs, "BoneWeights", 4)
    if idx is None or wts is None:
        return None
    if idx.shape[1] < 4:
        idx = np.pad(idx, ((0, 0), (0, 4 - idx.shape[1])))
        wts = np.pad(wts, ((0, 0), (0, 4 - wts.shape[1])))
    order = np.argsort(-wts, axis=1, kind="stable")
    bones = np.take_along_axis(idx, order, 1).astype(np.int64)
    weights = np.take_along_axis(wts, order, 1).astype(np.float32)
    total = weights.sum(axis=1, keepdims=True)
    weights = weights / np.where(total > 0, total, 1.0)
    bones[weights <= 0] = -1
    weights[weights <= 0] = 0.0
    return bones[:count], weights[:count]


def deform(positions, bones, weights, skin_names, skeleton, pose=None):
    """The positions (file axes, N x 3) moved from the bind pose to `pose` ({bone name: 4 x 4
    world frame}, default the rest pose): sum of weight x world x inverse bind. At the rest pose
    of a skeleton that `matches`, the positions come back as they were."""
    by_name = {b["name"]: b for b in skeleton["bones"]}
    mats = []
    for name in skin_names:
        b = by_name.get(name)
        if b is None or b["bind"] is None:
            mats.append(np.eye(4))
            continue
        world = (pose or {}).get(name, b["world"])
        mats.append(world @ np.linalg.inv(b["bind"]))
    mats = np.array(mats) if mats else np.eye(4)[None]
    p = np.c_[np.asarray(positions, np.float64), np.ones(len(positions))]
    out = np.zeros((len(p), 3))
    for k in range(bones.shape[1]):
        idx = bones[:, k]
        w = weights[:, k]
        use = (idx >= 0) & (w > 0)
        if not use.any():
            continue
        m = mats[np.clip(idx[use], 0, len(mats) - 1)]
        out[use] += w[use, None] * np.einsum("nij,nj->ni", m, p[use])[:, :3]
    rigid = weights.sum(axis=1) <= 0
    out[rigid] = p[rigid, :3]
    return out
