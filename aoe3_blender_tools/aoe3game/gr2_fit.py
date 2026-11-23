# SPDX-License-Identifier: GPL-3.0-or-later
"""A model fitted to what it borrows from another model, in place: the damage template
(`.dmg`) that names its debris meshes, and the animations that drive its bones. Standard library
only; uncompressed files (gr2.load), same size out, CRC recomputed.

    renames = plan_renames(doc, parts)       # parts: [(mesh, bone)] of a damage template
    rests = plan_rest(doc, gr2.load(ref))    # the reference model the animation was made on
    new = apply(data, renames, rests)        # then check(data, new, renames, rests)

Mesh names. A mod's building often borrows the damage template of a stock building and ships a
damage model rebuilt from the stock one. When a tool renamed some of its debris meshes on export
(Blender's duplicate suffix: `debris_1a.001`), the template's parts no longer find them and those
pieces never break off. A mesh is renamed to a part's name when its own name is that name plus a
`.NNN` suffix (any case), no other mesh has that name, and the mesh is bound to that part's bone
alone. The suffix is cut where the string is stored (a NUL written over its dot), so nothing else in
the file moves; a string another pointer also reaches is refused.

Rest frames. A Granny animation sets each bone's local transform by name. A model whose bones keep
the reference's places but were exported with other rest orientations (a quarter turn, a mirror, a
scale) is drawn by that animation with each piece turned about its bone, since its meshes are bound
through its own rest frames. Each bone found in the reference under the same name, with the same
parent and the same world position, gets the reference's local transform and inverse world
transform. The meshes do not move: a rigid model's vertices are stored in model space and drawn
through world x inverse, which is the identity at rest before and after (both models must have
their rest pose equal to their bind pose; a bone where it is not is left alone and listed).
"""
import math
import re
import struct

from . import gr2

HAS_POSITION, HAS_ORIENTATION, HAS_SCALE_SHEAR = 1, 2, 4
TRANSFORM_BYTES, INVERSE_BYTES = 68, 64
POSITION_TOL = 1e-3        # world position agreement, times max(1, distance from the origin)
INVERSE_TOL = 1e-3         # |W * IW - I| allowed for "rest pose = bind pose"
SAME_TOL = 1e-5            # frames this close are already the reference's
SUFFIX = re.compile(r"(.+)\.(\d{3})")


class Refused(ValueError):
    """The file cannot be fitted safely; the message says why. Nothing is written."""


# --------------------------------------------------------------------------------------------------
# Damage templates

def template_parts(text):
    """[(mesh, bone)] of a damage template's text (`<part mesh=... bone=...>`, any order)."""
    out = []
    for tag in re.findall(r"<part\b[^>]*>", text, flags=re.IGNORECASE):
        mesh = re.search(r'\bmesh\s*=\s*"([^"]*)"', tag, flags=re.IGNORECASE)
        bone = re.search(r'\bbone\s*=\s*"([^"]*)"', tag, flags=re.IGNORECASE)
        if mesh and bone:
            out.append((mesh.group(1).strip(), bone.group(1).strip()))
    return out


def missing_parts(doc, parts):
    """The parts of a template whose mesh the model does not have (names compared in any case)."""
    names = {(m.get("Name") or "").lower() for m in doc.root().get("Meshes") or [] if m}
    return [(mesh, bone) for mesh, bone in parts if mesh.lower() not in names]


# --------------------------------------------------------------------------------------------------
# Small algebra (column vectors; a frame is (3 x 3 linear part, position))

def _quat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        raise Refused("a bone has a zero orientation quaternion")
    s = 2.0 / n
    return [[1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
            [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
            [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _vec(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


_ID = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _local(tr):
    f = tr["flags"]
    pos = list(tr["position"]) if f & HAS_POSITION else [0.0, 0.0, 0.0]
    rot = _quat(tr["orientation"]) if f & HAS_ORIENTATION else _ID
    ss = tr["scale_shear"]
    scale = [list(ss[0:3]), list(ss[3:6]), list(ss[6:9])] if f & HAS_SCALE_SHEAR else _ID
    return _mul(rot, scale), pos


def _inverse_error(lin, pos, iw):
    """max |W * IW - I| for a world frame and a stored row-vector InverseWorldTransform."""
    w = [lin[0] + [pos[0]], lin[1] + [pos[1]], lin[2] + [pos[2]], [0.0, 0.0, 0.0, 1.0]]
    inv = [[iw[4 * j + i] for j in range(4)] for i in range(4)]
    return max(abs(sum(w[i][k] * inv[k][j] for k in range(4)) - (1.0 if i == j else 0.0))
               for i in range(4) for j in range(4))


def _size(lin):
    return max(1.0, max(math.sqrt(sum(lin[r][c] ** 2 for r in range(3))) for c in range(3)))


# --------------------------------------------------------------------------------------------------
# Reading

class Bone:
    __slots__ = ("index", "name", "parent", "tr", "iw", "tr_at", "iw_at", "lin", "pos")


def _frames(bones):
    for b in bones:
        lin, pos = _local(b.tr)
        if b.parent < 0:
            b.lin, b.pos = lin, pos
        else:
            p = bones[b.parent]
            b.lin = _mul(p.lin, lin)
            b.pos = [a + c for a, c in zip(_vec(p.lin, pos), p.pos)]


def bones_of(doc):
    """[[Bone]] per skeleton, with the file offsets of each Transform and InverseWorldTransform."""
    secs = doc.c.sections
    out = []
    for sk in doc.root().get("Skeletons") or []:
        if sk is None:
            continue
        bones = []
        for i, o in enumerate(sk.get("Bones") or []):
            mt, mi = o.type.member("Transform"), o.type.member("InverseWorldTransform")
            if (mt is None or mt.kind != gr2.TRANSFORM or mi is None or mi.kind != gr2.REAL32
                    or mi.width != 16):
                raise Refused("a bone type has no Transform or no 16-float InverseWorldTransform")
            b = Bone()
            b.index, b.name, b.parent = i, o.get("Name") or "", o.get("ParentIndex")
            if b.parent >= i:
                raise Refused(f"bone {b.name!r} comes before its parent")
            b.tr, b.iw = o.get("Transform"), list(o.get("InverseWorldTransform"))
            s, off = o.at
            if off + mi.offset + INVERSE_BYTES > secs[s].data_size or \
                    off + mt.offset + TRANSFORM_BYTES > secs[s].data_size:
                raise Refused(f"bone {b.name!r} lies in the section's zero padding")
            b.tr_at = secs[s].data_offset + off + mt.offset
            b.iw_at = secs[s].data_offset + off + mi.offset
            bones.append(b)
        _frames(bones)
        out.append(bones)
    return out


# --------------------------------------------------------------------------------------------------
# Plans

def plan_renames(doc, parts):
    """([(old name, new name, file offset of the string)], [lines about meshes left alone])."""
    want = {}
    for mesh, bone in parts:
        want.setdefault(mesh.lower(), (mesh, bone))
    c = doc.c
    meshes = [m for m in doc.root().get("Meshes") or [] if m]
    names = [(m.get("Name") or "") for m in meshes]
    lower = [n.lower() for n in names]
    # every pointer target, to refuse a string another pointer also reaches
    targets = {}
    for src, dst in c.relocs.items():
        targets.setdefault(dst[0], []).append((dst[1], src))
    out, notes, claimed = [], [], set()
    for m, name in zip(meshes, names):
        if name.lower() in want:
            continue
        hit = SUFFIX.fullmatch(name)
        if not hit or hit.group(1).lower() not in want:
            continue
        base = hit.group(1)
        key = base.lower()
        part_mesh, part_bone = want[key]
        if key in lower:
            notes.append(f"kept   {name}: the model already has a mesh {part_mesh}")
            continue
        if key in claimed:
            notes.append(f"kept   {name}: another mesh is renamed {part_mesh}")
            continue
        bound = [(bb.get("BoneName") or "").lower() for bb in m.get("BoneBindings") or []]
        if bound != [part_bone.lower()]:
            notes.append(f"kept   {name}: bound to {', '.join(bound) or 'no bone'}, the template's "
                         f"part is on {part_bone}")
            continue
        mo = m.type.member("Name")
        at = (m.at[0], m.at[1] + mo.offset)
        dst = c.relocs.get(at)
        if dst is None:
            raise Refused(f"mesh {name!r}: its name has no pointer")
        start, end = dst[1], dst[1] + len(name.encode("latin-1"))
        if c.data[dst[0]][start:end] != name.encode("latin-1"):
            raise Refused(f"mesh {name!r}: its name is not where its pointer says")
        others = [s for t, s in targets.get(dst[0], []) if start <= t <= end and s != at]
        if others:
            raise Refused(f"mesh {name!r}: another pointer reaches its name's bytes")
        claimed.add(key)
        out.append((name, base, c.sections[dst[0]].data_offset + start))
    return out, notes


def plan_rest(doc, ref):
    """(pairs, rebased, notes): `pairs` [(bone of the model, bone of the reference)], the bones
    whose rest frames become the reference's; `rebased` [(bone, new Transform)], bones left alone
    under a changed parent, whose local transform is recomputed so that they stay where they are;
    `notes` lines about the bones left alone."""
    mine, theirs = bones_of(doc), bones_of(ref)
    if not mine or not theirs:
        raise Refused("a model without a skeleton")
    by_name = {}
    for b in [b for sk in theirs for b in sk]:
        by_name.setdefault(b.name.lower(), []).append(b)
    pairs, notes = [], []
    for sk in mine:
        for b in sk:
            found = by_name.get(b.name.lower(), [])
            if len(found) != 1:
                if len(found) > 1:
                    notes.append(f"kept   {b.name}: the reference has it {len(found)} times")
                continue
            r = found[0]
            ref_bones = next(s for s in theirs if r in s)
            bp = sk[b.parent].name.lower() if b.parent >= 0 else None
            rp = ref_bones[r.parent].name.lower() if r.parent >= 0 else None
            if bp != rp:
                notes.append(f"kept   {b.name}: its parent differs from the reference's")
                continue
            tol = POSITION_TOL * max(1.0, math.sqrt(sum(v * v for v in r.pos)))
            if max(abs(a - c) for a, c in zip(b.pos, r.pos)) > tol:
                notes.append(f"kept   {b.name}: it stands elsewhere in the reference")
                continue
            if (_same(b.tr, r.tr) and all(abs(x - y) <= SAME_TOL for x, y in zip(b.iw, r.iw))):
                continue
            if _inverse_error(b.lin, b.pos, b.iw) > INVERSE_TOL * _size(b.lin):
                notes.append(f"kept   {b.name}: its rest pose is not its bind pose")
                continue
            if _inverse_error(r.lin, r.pos, r.iw) > INVERSE_TOL * _size(r.lin):
                notes.append(f"kept   {b.name}: the reference's rest pose is not its bind pose")
                continue
            pairs.append((b, r))
    # A bone left alone under a changed parent keeps its world frame: its local transform becomes
    # inverse(new parent world) x its world, the orientation folded into the scale/shear matrix.
    taken = {id(b): r for b, r in pairs}
    rebased = []
    for sk in mine:
        new = []
        for b in sk:
            r = taken.get(id(b))
            if r is not None and b.parent >= 0:     # its parent must end in the reference's frame
                plin, ppos = new[b.parent]
                ref_bones = next(s for s in theirs if r in s)
                rp = ref_bones[r.parent]
                if (max(abs(plin[i][j] - rp.lin[i][j]) for i in range(3) for j in range(3))
                        > 1e-4 * _size(rp.lin)
                        or max(abs(x - y) for x, y in zip(ppos, rp.pos)) > POSITION_TOL * _size(rp.lin)):
                    del taken[id(b)]
                    pairs = [(x, y) for x, y in pairs if x is not b]
                    notes.append(f"kept   {b.name}: its parent keeps a frame of its own")
                    r = None
            if r is not None:
                lin, pos = _local(r.tr)
                if b.parent >= 0:
                    plin, ppos = new[b.parent]
                    lin, pos = _mul(plin, lin), [a + c for a, c in zip(_vec(plin, pos), ppos)]
                new.append((lin, pos))
                continue
            if b.parent < 0:
                new.append((b.lin, b.pos))
                continue
            plin, ppos = new[b.parent]
            old = sk[b.parent]
            if (max(abs(plin[i][j] - old.lin[i][j]) for i in range(3) for j in range(3)) <= SAME_TOL
                    and max(abs(x - y) for x, y in zip(ppos, old.pos)) <= SAME_TOL):
                new.append((b.lin, b.pos))
                continue
            inv = _inverse3(plin)
            lin = _mul(inv, b.lin)
            pos = _vec(inv, [x - y for x, y in zip(b.pos, ppos)])
            tr = {"flags": HAS_POSITION | HAS_SCALE_SHEAR, "position": tuple(pos),
                  "orientation": (0.0, 0.0, 0.0, 1.0),
                  "scale_shear": tuple(lin[0] + lin[1] + lin[2])}
            rebased.append((b, tr))
            new.append((b.lin, b.pos))
            notes.append(f"kept   {b.name}: in its place under its changed parent (local transform "
                         f"recomputed)")
    return pairs, rebased, notes


def _inverse3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise Refused("a bone frame cannot be inverted")
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def _same(a, b):
    if a["flags"] != b["flags"]:
        return False
    vals = lambda t: list(t["position"]) + list(t["orientation"]) + list(t["scale_shear"])  # noqa: E731
    return all(abs(x - y) <= SAME_TOL for x, y in zip(vals(a), vals(b)))


# --------------------------------------------------------------------------------------------------
# The patch and its check

def apply(data, renames, rests, ref_data=None, rebased=()):
    """The new bytes: names cut, frames copied from the reference's bytes, the rebased bones'
    local transforms written, CRC recomputed."""
    out = bytearray(data)
    for old, new, at in renames:
        n = len(new.encode("latin-1"))
        out[at + n] = 0
    for b, r in rests:
        out[b.tr_at:b.tr_at + TRANSFORM_BYTES] = ref_data[r.tr_at:r.tr_at + TRANSFORM_BYTES]
        out[b.iw_at:b.iw_at + INVERSE_BYTES] = ref_data[r.iw_at:r.iw_at + INVERSE_BYTES]
    for b, tr in rebased:
        struct.pack_into("<I3f4f9f", out, b.tr_at, tr["flags"], *tr["position"], *tr["orientation"],
                         *tr["scale_shear"])
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


def check(before, after, renames, rests, rebased=()):
    """Reads the new bytes back: the meshes renamed and nothing else; every bone in its place,
    the changed ones in the reference's frames, the rebased ones in their own frames as before,
    every rest pose still its bind pose; the CRC."""
    if len(before) != len(after):
        raise Refused("verification: the size changed")
    a, b = gr2.load(before), gr2.load(after)
    want = {old: new for old, new, _ in renames}
    old_names = [m.get("Name") for m in a.root().get("Meshes") or [] if m]
    new_names = [m.get("Name") for m in b.root().get("Meshes") or [] if m]
    if [want.get(n, n) for n in old_names] != new_names:
        raise Refused("verification: the mesh names are not the ones planned")
    ref_of = {r_b.name: r for r_b, r in rests}
    moved = {b_.name for b_, _ in rebased}
    for sk_a, sk_b in zip(bones_of(a), bones_of(b)):
        for x, y in zip(sk_a, sk_b):
            size = _size(x.lin)
            if max(abs(p - q) for p, q in zip(x.pos, y.pos)) > POSITION_TOL * max(1.0, size):
                raise Refused(f"verification: bone {x.name!r} moved")
            r = ref_of.get(x.name)
            if r is not None:
                if max(abs(y.lin[i][j] - r.lin[i][j]) for i in range(3) for j in range(3)) > 1e-4 * size:
                    raise Refused(f"verification: bone {x.name!r} is not in the reference's frame")
            elif x.name in moved:
                if (y.iw != x.iw or max(abs(y.lin[i][j] - x.lin[i][j]) for i in range(3)
                                        for j in range(3)) > 1e-4 * size):
                    raise Refused(f"verification: bone {x.name!r} turned")
            elif y.tr != x.tr or y.iw != x.iw:
                raise Refused(f"verification: bone {x.name!r} was changed")
            if (_inverse_error(x.lin, x.pos, x.iw) <= INVERSE_TOL * size
                    and _inverse_error(y.lin, y.pos, y.iw) > INVERSE_TOL * _size(y.lin)):
                raise Refused(f"verification: bone {x.name!r}'s rest pose is no longer its bind pose")
    if not gr2.crc_ok(after):
        raise Refused("verification: CRC")


def fit(data, parts=None, ref_data=None):
    """(new bytes or None when nothing changes, report lines). Raises Refused or gr2.Gr2Error."""
    doc = gr2.load(data)
    renames, rests, rebased, lines = [], [], [], []
    if parts is not None:
        renames, notes = plan_renames(doc, parts)
        for old, new, _ in renames:
            lines.append(f"  mesh   {old} -> {new}")
        lines += ["  " + n for n in notes]
        renamed = {new.lower() for _, new, _ in renames}
        left = [(m, bn) for m, bn in missing_parts(doc, parts) if m.lower() not in renamed]
        if left:
            lines.append(f"  still missing from the model: {', '.join(m for m, _ in left)}")
    if ref_data is not None:
        rests, rebased, notes = plan_rest(doc, gr2.load(ref_data))
        for b, r in rests:
            lines.append(f"  bone   {b.name}: rest frame from the reference")
        lines += ["  " + n for n in notes]
    if not renames and not rests:
        return None, lines
    new = apply(data, renames, rests, ref_data, rebased)
    check(data, new, renames, rests, rebased)
    return new, lines
