# SPDX-License-Identifier: GPL-3.0-or-later
"""Bring the attach and impact bones of a Granny model (.gr2) to unit scale, in place.

    python -I tools/fix_bone_scale.py <in.gr2 | folder> [...] [-o <out.gr2 | out folder>]
                                      [--bones REGEX] [--factor F] [--dry-run] [-v]
                                      [--granny <bridge.exe> --granny-install <game folder>]

A folder is walked for every .gr2 below it; with -o, a fixed file is written to the same relative
path below the output folder (files with nothing to change are not copied). --dry-run prints what
would change and writes nothing; -v also lists the bones kept and the files left alone. The last
line counts the files fixed, unchanged and refused; the exit status is 1 when any was refused.

Some exports scale a model's root bone by 100 (centimetres) and give every other bone a unit
local scale, so every bone inherits a world frame whose axes are 100 long. A mesh bound to such a
bone draws right (its InverseWorldTransform takes the scale out again), but the game hangs some
attachments on a bone with the bone's whole frame: an impact effect whose particle set is an .xml
visual, for one, is then drawn 100 times too big.

What it changes, per skeleton:
- the bones chosen are those no mesh is bound to (no BoneBindings entry names them: impact points,
  flags, launch points, dummies) whose world scale is at least --factor times off unit length
  (default 10: 100 and 0.01 are fixed, the 0.24 to 4 of many stock models are not); --bones REGEX
  narrows them further by name (case-insensitive search);
- left alone, and listed: mesh-bound bones (so no mesh moves or deforms), a bone scaled unevenly
  or sheared, and a bone with a bone below it that is not fixed (a mesh bone under a scaled root:
  its frame would move). The bones below such a bone are judged on their own, so the attach bones
  of a model whose scaled root carries its meshes are still fixed;
- a chosen bone's local ScaleShear is divided by its world scale (and its HasScaleShear flag set),
  so its world axes become unit length; its local position, its orientation and so its world
  position and direction stay as they were;
- its InverseWorldTransform takes the same change (it stays the inverse of the rest pose; on a
  skinned model, where it is a bind pose instead, it stays that bind pose at the new scale);
- the values are written over the old ones (the file keeps its size and layout) and the header
  CRC is recomputed. The result is read back and checked before it is written.

It refuses (exit 1, nothing written) a file it cannot handle safely: compressed sections (unless
--granny is given: the bridge writes an uncompressed copy first, and the output is that larger,
uncompressed file), a model whose InitialPlacement scales, a parent listed after its child, a
bone lying outside its section's stored bytes.

Without -o each input is rewritten in place after a copy to <in>.bak (kept if one exists). A file
with nothing to change is not written. An animation that drives a fixed bone overrides its rest
transform while it plays, and a model attached to another by one of its own bones (an anim
file's <attach frombone=...>) may be placed through that bone's frame: check such models in game.
"""
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "aoe3_blender_tools"))
from aoe3game import gr2  # noqa: E402

HAS_POSITION, HAS_ORIENTATION, HAS_SCALE_SHEAR = 1, 2, 4
# granny_transform: u32 flags, f32 position[3], f32 orientation[4] (x, y, z, w), f32 scale_shear[9]
TR_FLAGS, TR_POSITION, TR_ORIENTATION, TR_SCALE_SHEAR = 0, 4, 16, 32
# The 12 entries of a row-vector 4x4 (translation in the last row) that are not (0, 0, 0, 1).
IW_AFFINE = (0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14)
UNIFORM = 1e-3      # relative spread allowed between the three axis lengths of a chosen bone
ORTHO = 1e-3        # cosine allowed between two of its axes
INVERSE = 1e-3      # |W * IW - I| under which a stored inverse matches the rest pose


class Refused(Exception):
    """The file cannot be fixed safely; the message says why. Nothing is written."""


# --------------------------------------------------------------------------------------------------
# Small 3 x 3 algebra (column vectors: world = parent world * local)

def quat_matrix(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        raise Refused("a bone has a zero orientation quaternion")
    s = 2.0 / n
    return [[1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
            [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
            [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)]]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def local_parts(tr):
    """(linear 3 x 3, position) of a transform dict as gr2.Doc reads it, honouring its flags."""
    f = tr["flags"]
    pos = list(tr["position"]) if f & HAS_POSITION else [0.0, 0.0, 0.0]
    rot = quat_matrix(tr["orientation"]) if f & HAS_ORIENTATION else IDENTITY
    ss = tr["scale_shear"]
    scale = [list(ss[0:3]), list(ss[3:6]), list(ss[6:9])] if f & HAS_SCALE_SHEAR else IDENTITY
    return mat_mul(rot, scale), pos


def axis_lengths(lin):
    return [math.sqrt(sum(lin[r][c] ** 2 for r in range(3))) for c in range(3)]


def inverse_error(lin, pos, iw):
    """max |W * IW - I| for a world frame and a stored row-vector InverseWorldTransform."""
    w = [lin[0] + [pos[0]], lin[1] + [pos[1]], lin[2] + [pos[2]], [0.0, 0.0, 0.0, 1.0]]
    inv = [[iw[4 * j + i] for j in range(4)] for i in range(4)]       # to column-vector form
    return max(abs(sum(w[i][k] * inv[k][j] for k in range(4)) - (1.0 if i == j else 0.0))
               for i in range(4) for j in range(4))


# --------------------------------------------------------------------------------------------------
# Reading the bones

class Bone:
    __slots__ = ("index", "name", "parent", "tr", "iw", "tr_at", "iw_at", "lin", "pos",
                 "mesh", "chosen", "scale", "reason", "bind")


def world_frames(bones):
    for b in bones:
        lin, pos = local_parts(b.tr)
        if b.parent < 0:
            b.lin, b.pos = lin, pos
        else:
            p = bones[b.parent]
            b.lin = mat_mul(p.lin, lin)
            b.pos = [a + c for a, c in zip(mat_vec(p.lin, pos), p.pos)]
        b.scale = sum(axis_lengths(b.lin)) / 3.0


def read_skeletons(doc):
    """[(skeleton name, [Bone])] with file offsets of each bone's Transform and inverse."""
    root = doc.root()
    secs = doc.c.sections
    out = []
    for sk in root.get("Skeletons") or []:
        if sk is None:
            continue
        objs = sk.get("Bones") or []
        bones = []
        for i, o in enumerate(objs):
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
            sec = secs[s]
            b.tr_at = sec.data_offset + off + mt.offset
            b.iw_at = sec.data_offset + off + mi.offset
            if off + mi.offset + 64 > sec.data_size or off + mt.offset + 68 > sec.data_size:
                raise Refused(f"bone {b.name!r} lies in the section's zero padding")
            bones.append(b)
        world_frames(bones)
        out.append((sk.get("Name") or "", bones))
    return out


def mesh_bones(doc):
    names = set()
    for mesh in doc.root().get("Meshes") or []:
        for bb in (mesh.get("BoneBindings") if mesh else None) or []:
            names.add(bb.get("BoneName"))
    return names


def placement_scales(doc):
    for model in doc.root().get("Models") or []:
        tr = model.get("InitialPlacement") if model else None
        if tr and tr["flags"] & HAS_SCALE_SHEAR and any(
                abs(v - (1.0 if k in (0, 4, 8) else 0.0)) > 1e-6
                for k, v in enumerate(tr["scale_shear"])):
            return model.get("Name")
    return None


# --------------------------------------------------------------------------------------------------
# The plan and the patch

def plan(data, bones_re=None, factor=10.0):
    """Reads uncompressed bytes and decides. Returns [(skeleton name, [Bone])] with each bone's
    `chosen`, `scale` (its uniform world scale), `reason` and `bind` (its stored inverse is not
    the inverse of its rest pose) set. Raises Refused or gr2.Compressed."""
    doc = gr2.load(data)
    bound = mesh_bones(doc)
    skeletons = read_skeletons(doc)
    rx = re.compile(bones_re, re.IGNORECASE) if bones_re else None
    for _, bones in skeletons:
        for b in bones:
            lengths = axis_lengths(b.lin)
            b.scale = sum(lengths) / 3.0
            b.mesh = b.name in bound
            b.chosen, b.bind = False, False
            if b.mesh:
                b.reason = "mesh-bound"
            elif rx is not None and not rx.search(b.name):
                b.reason = "not matched"
            elif 1.0 / factor < min(lengths) and max(lengths) < factor:
                b.reason = "near unit"
            elif max(lengths) - min(lengths) > UNIFORM * max(lengths):
                b.reason = "LEFT: scaled unevenly (" + ", ".join(f"{v:.4g}" for v in lengths) + ")"
            elif any(abs(sum(b.lin[r][i] * b.lin[r][j] for r in range(3)))
                     > ORTHO * lengths[i] * lengths[j] for i, j in ((0, 1), (0, 2), (1, 2))):
                b.reason = "LEFT: sheared"
            else:
                b.chosen, b.reason = True, "fixed"
                b.bind = inverse_error(b.lin, b.pos, b.iw) / max(1.0, b.scale) > INVERSE
        for b in reversed(bones):                   # children come after their parent
            if b.parent >= 0 and not b.chosen and bones[b.parent].chosen:
                p = bones[b.parent]
                p.chosen = False
                p.reason = f"LEFT: {b.name} hangs from it and is not fixed ({b.reason.lower()})"
    if any(b.chosen for _, bones in skeletons for b in bones):
        model = placement_scales(doc)
        if model is not None:
            raise Refused(f"model {model!r} has a scaled InitialPlacement")
    return skeletons


def patch(data, skeletons):
    """The new bytes: every chosen bone's local scale and inverse rewritten, CRC recomputed."""
    out = bytearray(data)
    for _, bones in skeletons:
        factor = {}                                 # 1 / world scale of each fixed bone
        for b in bones:
            if not b.chosen:
                continue
            f = 1.0 / b.scale
            fp = factor.get(b.parent, 1.0)           # a fixed parent is fixed first
            factor[b.index] = f
            tr = b.tr
            flags = tr["flags"]
            ss = list(tr["scale_shear"]) if flags & HAS_SCALE_SHEAR else [1, 0, 0, 0, 1, 0, 0, 0, 1]
            ss = [v * f / fp for v in ss]
            struct.pack_into("<I", out, b.tr_at + TR_FLAGS, flags | HAS_SCALE_SHEAR)
            struct.pack_into("<9f", out, b.tr_at + TR_SCALE_SHEAR, *ss)
            if fp != 1.0 and flags & HAS_POSITION:
                struct.pack_into("<3f", out, b.tr_at + TR_POSITION,
                                 *[v / fp for v in tr["position"]])
            iw = list(b.iw)
            for k in IW_AFFINE:
                iw[k] /= f
            struct.pack_into("<16f", out, b.iw_at, *iw)
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


def verify(before, after_data):
    """Reads the patched bytes back: fixed bones have unit axes and keep their place and
    direction, their inverse took the same change, every other bone is byte for byte as it was."""
    after = read_skeletons(gr2.load(after_data))
    if len(after) != len(before):
        raise Refused("verification: the skeletons changed")
    for (_, old), (_, new) in zip(before, after):
        for o, n in zip(old, new):
            size = max(1.0, o.scale)
            if max(abs(a - c) for a, c in zip(o.pos, n.pos)) > 1e-5 * size:
                raise Refused(f"verification: bone {o.name!r} moved")
            if not o.chosen:
                if n.iw != o.iw or n.tr != o.tr:
                    raise Refused(f"verification: bone {o.name!r} was changed")
                continue
            if max(abs(v - 1.0) for v in axis_lengths(n.lin)) > 1e-4:
                raise Refused(f"verification: bone {o.name!r} is not unit length")
            ref = [[v / o.scale for v in row] for row in o.lin]
            if max(abs(ref[r][c] - n.lin[r][c]) for r in range(3) for c in range(3)) > 1e-5:
                raise Refused(f"verification: bone {o.name!r} turned")
            if o.bind:
                if any(abs(n.iw[k] - o.iw[k] * o.scale) > 1e-5 * max(1.0, abs(o.iw[k] * o.scale))
                       for k in IW_AFFINE):
                    raise Refused(f"verification: bone {o.name!r}'s inverse is wrong")
            elif inverse_error(n.lin, n.pos, n.iw) > INVERSE:
                raise Refused(f"verification: bone {o.name!r}'s inverse is wrong")
    if not gr2.crc_ok(after_data):
        raise Refused("verification: CRC")


def fix_bytes(data, bones_re=None, factor=10.0):
    """(new bytes or None when nothing changes, skeletons as planned). Raises Refused."""
    skeletons = plan(data, bones_re, factor)
    if not any(b.chosen for _, bones in skeletons for b in bones):
        return None, skeletons
    new = patch(data, skeletons)
    verify(skeletons, new)
    return new, skeletons


def report(skeletons, verbose=False):
    """Lines for the bones fixed and the off-scale bones left alone (all bones with verbose)."""
    lines = []
    for name, bones in skeletons:
        n_mesh = sum(b.mesh for b in bones)
        n_fix = sum(b.chosen for b in bones)
        lines.append(f'  skeleton "{name}": {len(bones)} bones, {n_mesh} mesh-bound, {n_fix} to fix')
        for b in bones:
            if b.chosen:
                lines.append(f"    fixed  {b.name}: axes {b.scale:.4g} -> 1 (local scale x "
                             f"{1.0 / b.scale:.4g}), world position kept"
                             + ("; its inverse is a bind pose, scaled with it" if b.bind else ""))
            elif b.reason.startswith("LEFT") or (verbose and abs(b.scale - 1.0) > 1e-3):
                lines.append(f"    kept   {b.name}: axes {b.scale:.4g} ({b.reason[6:] if b.reason.startswith('LEFT') else b.reason})")
    return lines


# --------------------------------------------------------------------------------------------------
# Command line

def expand(path, exe, install):
    """An uncompressed copy of a compressed file, written by the external bridge in a temporary
    folder (its working directory too)."""
    tmp = tempfile.mkdtemp(prefix="fix_bone_scale_")
    try:
        out = os.path.join(tmp, "raw.gr2")
        try:
            r = subprocess.run([exe, "rebake", "--install", install, "--file",
                                os.path.abspath(path), "--out", out, "--noop"],
                               cwd=tmp, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Refused(f"the bridge failed: {type(exc).__name__}") from exc
        if r.returncode != 0 or not os.path.exists(out):
            raise Refused(f"the bridge failed (exit {r.returncode})")
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def gr2_files(folder):
    """Every .gr2 below a folder, sorted, as (path, path relative to the folder)."""
    out = []
    for base, dirs, names in os.walk(folder):
        dirs.sort()
        for n in sorted(names):
            if n.lower().endswith(".gr2"):
                full = os.path.join(base, n)
                out.append((full, os.path.relpath(full, folder)))
    return out


def run_one(path, out_path, args):
    """Fixes one file. Returns (status, bones fixed): status 'fixed', 'same' or 'dry'.
    Raises Refused."""
    with open(path, "rb") as fh:
        data = fh.read()
    facts = gr2.header_facts(data[:4096])
    if "magic" in facts:
        raise Refused("not a Granny file")
    expanded = False
    if not facts.get("raw"):
        if not args["granny"]:
            raise Refused("its sections are compressed: give --granny <bridge> --granny-install "
                          "<game folder>, or write it uncompressed first")
        data = expand(path, args["granny"], args["install"])
        expanded = True
    new, skeletons = fix_bytes(data, args["bones"], args["factor"])
    fixed = sum(b.chosen for _, bones in skeletons for b in bones)
    if new is None:
        if args["verbose"]:
            print(f"{path}: nothing to change")
            print("\n".join(report(skeletons, True)))
        return "same", 0
    print(f"{path}:")
    print("\n".join(report(skeletons, args["verbose"])))
    if args["dry_run"]:
        return "dry", fixed
    if out_path is None:
        out_path = path
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
            print(f"  backup {bak}")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(new)
    size = (f"{len(new)} B, written uncompressed" if expanded
            else f"{len(new)} B, same size, CRC updated")
    print(f"  wrote {out_path} ({size})")
    return "fixed", fixed


def main(argv):
    args = {"bones": None, "factor": 10.0, "dry_run": False, "granny": None, "install": None,
            "verbose": False}
    out_path, inputs, i = None, [], 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("-o", "--out"):
                out_path, i = argv[i + 1], i + 1
            elif a == "--bones":
                args["bones"], i = argv[i + 1], i + 1
                re.compile(args["bones"])
            elif a == "--factor":
                args["factor"], i = float(argv[i + 1]), i + 1
            elif a == "--granny":
                args["granny"], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["install"], i = argv[i + 1], i + 1
            elif a == "--dry-run":
                args["dry_run"] = True
            elif a in ("-v", "--verbose"):
                args["verbose"] = True
            elif a.startswith("-"):
                raise ValueError(a)
            else:
                inputs.append(a)
            i += 1
    except (IndexError, ValueError, re.error):
        inputs = []
    if args["factor"] <= 1.0:
        inputs = []
    if not inputs or (out_path and len(inputs) != 1) or bool(args["granny"]) != bool(args["install"]):
        print(__doc__)
        return 2
    jobs = []                                   # (input file, output file or None)
    for item in inputs:
        if os.path.isdir(item):
            for full, rel in gr2_files(item):
                jobs.append((full, os.path.join(out_path, rel) if out_path else None))
        else:
            jobs.append((item, out_path))
    counts = {"fixed": 0, "dry": 0, "same": 0, "refused": 0}
    bones = 0
    for path, out in jobs:
        try:
            status, n = run_one(path, out, args)
        except (Refused, gr2.Gr2Error, OSError, struct.error) as exc:
            print(f"{path}: refused: {exc}")
            counts["refused"] += 1
            continue
        counts[status] += 1
        bones += n
    verb = "to fix" if args["dry_run"] else "fixed"
    print(f"{len(jobs)} files: {counts['fixed'] + counts['dry']} {verb} ({bones} bones), "
          f"{counts['same']} with nothing to change, {counts['refused']} refused"
          + (" (dry run: nothing written)" if args["dry_run"] else ""))
    return 1 if counts["refused"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
