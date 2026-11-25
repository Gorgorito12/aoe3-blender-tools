# SPDX-License-Identifier: GPL-3.0-or-later
"""A zamburak that limbers and unlimbers: a camel unit's body with its own lateral swivel gun cut
out, and a cannon barrel taken from a wheeled gun (by default the zamburak's camel and a mod's
camel-drawn field gun, the "midfa"), shortened, on an iron swivel fork centred on the camel's back.
Limbered, the barrel is swivelled to point down along the camel's neck; unlimbered, the camel lies
down and the artillerist stands beside it with a linstock (the field gun's own staff). Recipe-driven
like make_gun_camel.py, whose camel, rider and drawing it reuses.

    venv\\Scripts\\python -I tools/make_zamburak.py --game <game copy> --out <folder>
        [--recipe <recipe.json>] [--granny-helper <exe>] [--no-verify] [--sheet <png>]
        [--limber-options <png>]

What it writes below --out (`art\\<recipe "folder">\\`):
- `<name>_camel.gr2`: the camel's body without its swivel gun (every piece of it, the post too:
  `cut`), with `bone_turret` at the swivel's pivot and `bone_launchpoint` / `bone_muzzle` at the
  muzzle (aoe3game/gr2_parts.cut_triangles, add_bones).
- `<name>_gun.gr2`: the swivel and the cannon, one rigid mesh per part on its own bone, in the space
  of the camel's rider bone (the anim file hangs it there, as make_gun_camel's gun): `bone_post`
  (the wooden socket on the saddle), `bone_yaw` (the fork, turned about the post's axis by a game
  key that aims the gun without the camel, turretArc), `bone_cannon` (the barrel and its trunnion
  pins, pitched in the fork: down to limber, level to fire), `bone_fuse` (the vent),
  `bone_launchpoint` (the muzzle) and `bone_linstock` (the staff, in its holder on the post
  when limbered, in the artillerist's hand when he fires).
- `<name>-report.txt`: what was cut and made, and the runtime's checks.
- with `--clips <folder>`: every clip of the approved beat-list script (ZUnit: limbered idle, walk,
  jog, run, bored, cheer; unlimber and limber; unlimbered idle, fire, reload, death), the camel's,
  the gun's and the rider's (`<name>_camel_<clip>`, `_gun_<clip>`, `_rider_<clip>`), the limbered
  dead model (`<name>_camel_dead`: the cannon in its limber pose and the linstock built in, playing
  the camel's own deaths), and in the folder the check_anim jobs: the new clips with today's as
  their baseline (every removal named), the limbered deaths, the unlimbered death. `--textured`
  draws every clip, textured, at eight moments from both sides.

The barrel (`barrel` of the recipe): the triangles of one bone of the source model, its axis from
the centre of its breech ring to the centre of its muzzle ring; `length` shortens it (2/3: the chase
between the breech and the muzzle's swell is pressed along the axis, the swell and the breech keep
their shape), `scale` sizes the whole cannon against the source (1: as the field gun has it).

Compressed game files are expanded by the game's own Granny runtime (`--granny-helper`, as
make_gun_camel.py). Refuses a Steam folder as output. Its outputs come from a game's models: keep
them out of the repository.
"""
import argparse
import copy
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import make_gun_camel as mgc  # noqa: E402
from aoe3game import gr2, gr2_mesh, gr2_parts  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import Animation, Rig  # noqa: E402
from aoe3game.gr2_pose import axis_matrix, unit  # noqa: E402

X, Y, Z = mgc.X, mgc.Y, mgc.Z
tr, rot4, point, apply, rigid = mgc.tr, mgc.rot4, mgc.point, mgc.apply, mgc.rigid

MIDFA = "WoL\\units\\artillery\\Midfa\\"
DEFAULT_RECIPE = {
    "name": "zamburak_cannon",
    "folder": "WoL\\units\\cavalry_ranged\\zamburak_cannon",
    "rider_xml": "WoL\\units\\cavalry_ranged\\zamburak\\zamburak_rider.xml",     # his models by rank, his hats
    "camel": dict(mgc.DEFAULT_RECIPE["camel"]),
    # the lateral swivel gun: every piece of it, the post too (the cannon gets its own swivel)
    "cut": {"x_below": -0.18, "y_above": 1.6, "keep_post": False},
    "rider": copy.deepcopy(mgc.DEFAULT_RECIPE["rider"]),
    # the barrel: one bone's triangles of a gun model; its length a share of the source's (the chase
    # pressed, the muzzle's swell and the breech kept); the cannon's size a share of the source's
    "barrel": {"model": MIDFA + "Midfa_stripped", "bone": "bone_cannon", "fuse": "bone_fuse",
               "length": 2.0 / 3.0, "scale": 0.6,
               # the trunnions this share of the (shortened) length from the breech
               "trunnion": 0.30},
    # the artillerist's linstock: a mesh of the same model (the field gun's own staff)
    # (short: the user's choice, 2026-11-26: about a forearm and an arm, held in one hand)
    "linstock": {"plain": True, "length": 0.85, "radius": 0.018, "hot": 0.08},
    # the artillerist on foot as the previews show him (a mesh of the field gun's model)
    "gunner": {"model": MIDFA + "Midfa_stripped", "meshes": ["gunner"]},
    # the swivel: its pivot on the camel's centre line (x = 0) this far along the body (design
    # units, +z ahead) and this high above the saddle's surface there; the fork's prongs hold the
    # trunnions this high above the pivot
    "swivel": {"z": 0.62, "socket": 0.06, "fork": 0.0},
    # limbered: the barrel pitched down this many degrees (positive: muzzle down) and turned this
    # many about the post (positive: toward the unit's right), so it clears the neck
    "limber": {"pitch": 20.0, "yaw": 30.0},
    # killed unlimbered: the game's standing rifleman death B (A flings his arms forward into the lying
    # camel beside him; B falls back away from it)
    "foot_death": mgc.LIB + "range\\death_standing_rifleman_B",
}
FPS = 30


# --------------------------------------------------------------------------------------------------
# Simple solids (the swivel's iron and wood), in design space; one texel each (a patch of the
# source's texture)


def _solid(pos, nrm, tris, uv):
    pos = np.asarray(pos, np.float64)
    nrm = np.asarray(nrm, np.float64)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    # a tangent: any unit vector across the normal
    ref = np.where(np.abs(nrm[:, 1:2]) < 0.9, Y, X)
    tan = np.cross(nrm, ref)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    return {"positions": pos, "normals": nrm, "tangents": tan, "uvs": np.tile(np.asarray(uv, np.float64), (len(pos), 1)),
            "triangles": np.asarray(tris, np.int64)}


def cylinder(p0, p1, radius, sides=8, caps=True, uv=(0.5, 0.5)):
    """A closed cylinder from p0 to p1 (design space), smooth sides, flat caps, counter-clockwise
    from outside."""
    p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
    ax = unit(p1 - p0)
    a = unit(np.cross(ax, X if abs(ax @ X) < 0.9 else Y))
    b = np.cross(ax, a)
    pos, nrm, tris = [], [], []
    ring = [math.cos(2 * math.pi * k / sides) * a + math.sin(2 * math.pi * k / sides) * b for k in range(sides)]
    for k in range(sides):
        pos += [p0 + radius * ring[k], p1 + radius * ring[k]]
        nrm += [ring[k], ring[k]]
    for k in range(sides):
        i, j = 2 * k, 2 * ((k + 1) % sides)
        tris += [(i, j, j + 1), (i, j + 1, i + 1)]
    if caps:
        for end, sign in ((p0, -1.0), (p1, 1.0)):
            c = len(pos)
            pos.append(end)
            nrm.append(sign * ax)
            for k in range(sides):
                pos.append(end + radius * ring[k])
                nrm.append(sign * ax)
            for k in range(sides):
                i, j = c + 1 + k, c + 1 + (k + 1) % sides
                tris.append((c, j, i) if sign < 0 else (c, i, j))
    part = _solid(pos, nrm, tris, uv)
    return _outward(part)


def box(centre, half, axes=(X, Y, Z), uv=(0.5, 0.5)):
    """A box (design space): centre, half sizes along its three axes."""
    c = np.asarray(centre, np.float64)
    ax = [unit(a) for a in axes]
    pos, nrm, tris = [], [], []
    for i in range(3):
        for sign in (-1.0, 1.0):
            n = sign * ax[i]
            u, v = ax[(i + 1) % 3], ax[(i + 2) % 3]
            hu, hv = half[(i + 1) % 3], half[(i + 2) % 3]
            f = c + n * half[i]
            base = len(pos)
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                pos.append(f + du * hu * u + dv * hv * v)
                nrm.append(n)
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return _outward(_solid(pos, nrm, tris, uv))


def _outward(part):
    """Each triangle wound counter-clockwise seen from where its corners' normals point."""
    p, n, t = part["positions"], part["normals"], part["triangles"].copy()
    f = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    flip = np.einsum("ij,ij->i", f, n[t].sum(1)) < 0
    t[flip] = t[flip][:, ::-1]
    part["triangles"] = t
    return part


def sphere(radius, rings=4, sides=8, uv=(0.5, 0.5)):
    """A closed low sphere round the origin, its poles on z."""
    pos, nrm, tris = [], [], []
    pos.append((0.0, 0.0, -radius))
    nrm.append((0.0, 0.0, -1.0))
    for i in range(1, rings):
        a = math.pi * i / rings - math.pi / 2
        for k in range(sides):
            b = 2 * math.pi * k / sides
            n = (math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a))
            pos.append(tuple(radius * v for v in n))
            nrm.append(n)
    pos.append((0.0, 0.0, radius))
    nrm.append((0.0, 0.0, 1.0))
    top = len(pos) - 1
    for k in range(sides):
        tris.append((0, 1 + (k + 1) % sides, 1 + k))
    for i in range(rings - 2):
        a0, a1 = 1 + i * sides, 1 + (i + 1) * sides
        for k in range(sides):
            k1 = (k + 1) % sides
            tris += [(a0 + k, a0 + k1, a1 + k1), (a0 + k, a1 + k1, a1 + k)]
    last = 1 + (rings - 2) * sides
    for k in range(sides):
        tris.append((top, last + k, last + (k + 1) % sides))
    return _outward(_solid(pos, nrm, tris, uv))


def apply_part(part, frame, uv):
    """A solid moved by `frame` (rigid), all its corners on one texel `uv`."""
    out = dict(part)
    out["positions"] = apply(frame, part["positions"])
    out["normals"] = part["normals"] @ frame[:3, :3].T
    out["tangents"] = part["tangents"] @ frame[:3, :3].T
    out["uvs"] = np.tile(np.asarray(uv, np.float64), (len(part["positions"]), 1))
    return out


def merge(parts):
    pos, nrm, tan, uvs, tris = [], [], [], [], []
    base = 0
    for p in parts:
        pos.append(p["positions"])
        nrm.append(p["normals"])
        tan.append(p["tangents"])
        uvs.append(p["uvs"])
        tris.append(p["triangles"] + base)
        base += len(p["positions"])
    return {"positions": np.concatenate(pos), "normals": np.concatenate(nrm), "tangents": np.concatenate(tan),
            "uvs": np.concatenate(uvs), "triangles": np.concatenate(tris)}


# --------------------------------------------------------------------------------------------------
# The source: the barrel and the linstock


def red_texel(img, material):
    """(uv, material): the reddest opaque texel of `img` whose four neighbours are red too, or None."""
    im = np.asarray(img, np.float64)
    hh, ww = im.shape[:2]
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    ok = (r > 140) & (r > g + 60) & (r > b + 60)
    if im.shape[-1] > 3:
        ok &= im[..., 3] > 250
    core = np.zeros_like(ok)
    core[1:-1, 1:-1] = ok[1:-1, 1:-1] & ok[:-2, 1:-1] & ok[2:, 1:-1] & ok[1:-1, :-2] & ok[1:-1, 2:]
    if not core.any():
        return None
    ys, xs = np.nonzero(core)
    k = int(np.argmax((r - 0.5 * g - 0.5 * b)[ys, xs]))
    return np.array([(xs[k] + 0.5) / ww, (ys[k] + 0.5) / hh]), material


def texel_patch(img, part, want, pick="largest"):
    """(uv, triangle index) of the largest triangle of `part` whose texels (corners and middle) all
    pass `want(rgba)`: a flat patch of one colour for the solids made here."""
    uv, tri = part["uvs"], part["triangles"]
    hgt, wid = img.shape[:2]

    def texel(q):
        x = int(min(wid - 1, max(0, (q[0] % 1.0) * wid)))
        y = int(min(hgt - 1, max(0, (q[1] % 1.0) * hgt)))
        return np.asarray(img[y, x], np.float64)
    best, best_area = None, 0.0
    for i, (a, b, c) in enumerate(tri):
        cols = [texel(q) for q in (uv[a], uv[b], uv[c], (uv[a] + uv[b] + uv[c]) / 3.0)]
        if not all(want(col) for col in cols):
            continue
        area = abs((uv[b][0] - uv[a][0]) * (uv[c][1] - uv[a][1]) - (uv[b][1] - uv[a][1]) * (uv[c][0] - uv[a][0]))
        if area > best_area:
            best, best_area = i, area
    if best is None:
        return None
    return uv[tri[best]].mean(0), best


def opaque(c):
    return len(c) < 4 or c[3] >= 250


def is_iron(c):
    lum = c[:3].mean()
    return opaque(c) and 15 <= lum <= 75 and np.ptp(c[:3]) < 22


def is_wood(c):
    r, g, b = c[:3]
    return opaque(c) and 70 <= r <= 190 and r > g + 15 > b + 15


def is_bronze(c):
    r, g, b = c[:3]
    return opaque(c) and r >= 120 and g >= 80 and r > b + 50


def press(z, length, share):
    """A barrel's axial positions `z` (0 at the breech, `length` at the muzzle) pressed so the
    whole is `share` of its length: the chase, the longest stretch of the axis with no vertex (a
    turned barrel is rings joined by plain cones), is pressed; the muzzle's swell, from the ring
    after the chase to the muzzle, and the breech keep their shape. (pressed z, the swell's start
    before, after)."""
    z = np.asarray(z, np.float64)
    zs = np.unique(np.round(z, 4))
    at = int(np.argmax(np.diff(zs)))
    swell = float(zs[at + 1]) if zs[at + 1] > 0.5 * length else length
    swell = min(swell, length - 1e-3)
    tail = length - swell
    chase_new = max(0.2 * swell, share * length - tail)
    f = chase_new / swell
    return np.where(z <= swell, z * f, z - (swell - chase_new)), swell, chase_new


class Source:
    """The barrel (one bone's triangles) and the linstock (one mesh) of the source model, in the
    source's file units: barrel space has its origin at the trunnions on the bore's axis, +z out of
    the muzzle, +y up; the linstock's has its origin at the staff's foot, +y along it."""

    def __init__(self, game, recipe):
        spec = recipe["barrel"]
        self.data = game.granny(spec["model"])
        parts = gr2_parts.mesh_parts(self.data)
        gun = next(p for p in parts if spec["bone"].lower() in [n.lower() for n in p["skin_names"]])
        bones = np.array([(b or "").lower() for b in gr2_parts.triangle_bones(gun)], dtype=object)
        sel = bones == spec["bone"].lower()
        raw = mgc.sub_part(gun, sel)
        tex_name = next(n for n in gr2_mesh.read(self.data)["textures"]
                        if n and "_b." not in n.lower() and "gunner" not in n.lower() and "hat" not in n.lower())
        self.img = game.texture(tex_name)
        self.material = raw["materials"][0]
        # the axis: the breech ring's and the muzzle ring's centres (the rings: vertices within 2 % of
        # the length of each end, their bounding box's middle)
        p = raw["positions"]
        ax0 = unit(p[np.argmax(np.linalg.norm(p - p.mean(0), axis=1))] - p.mean(0))
        t = (p - p.mean(0)) @ ax0
        span = t.max() - t.min()
        lo, hi = p[t < t.min() + 0.02 * span + 0.03], p[t > t.max() - 0.02 * span - 0.03]
        c_lo, c_hi = 0.5 * (lo.min(0) + lo.max(0)), 0.5 * (hi.min(0) + hi.max(0))
        # the muzzle: the end farther from the fuse (the vent sits by the breech)
        rig = Rig.of(gr2.load(self.data).root())
        rest = rig.by_name(rig.rest_worlds())
        fuse = rest[spec["fuse"].lower()][:3, 3]
        if np.linalg.norm(c_lo - fuse) < np.linalg.norm(c_hi - fuse):
            breech, muzzle = c_lo, c_hi
        else:
            breech, muzzle = c_hi, c_lo
        axis = unit(muzzle - breech)
        up = unit(Y - (Y @ axis) * axis)
        side = np.cross(up, axis)
        # source -> barrel frame (rotation rows: side, up, axis), origin at the breech for now
        Rb = np.array([side, up, axis])
        q = (p - breech) @ Rb.T
        length = float(np.linalg.norm(muzzle - breech))
        q2 = q.copy()
        q2[:, 2], swell, chase_new = press(q[:, 2], length, spec.get("length", 1.0))
        self.length = float(q2[:, 2].max())
        self.source_length = length
        self.swell = (float(swell), float(chase_new))
        self.trunnion_z = spec.get("trunnion", 0.3) * self.length
        sh = np.array([0.0, 0.0, self.trunnion_z])
        # normals kept as they are: the chase's slope changes by under a degree (radii 0.16 to 0.23
        # over 1.6 units), too little to see
        nrm = raw["normals"] @ Rb.T
        tan = raw["tangents"] @ Rb.T
        self.barrel = {"positions": q2 - sh, "normals": nrm, "tangents": tan, "uvs": raw["uvs"],
                       "triangles": raw["triangles"], "materials": raw["materials"]}
        # the source's barrel as it is (for the pictures), its breech where the new one's is
        self.barrel_source = dict(self.barrel, positions=q - sh)
        self.radius = float(np.hypot(q2[:, 0], q2[:, 1]).max())
        self.radius_at_trunnion = float(np.median(np.hypot(q2[:, 0], q2[:, 1])[np.abs(q2[:, 2] - self.trunnion_z)
                                                                              < 0.35 * self.length]))
        # the vent: on top of the barrel, `vent` of its length ahead of the breech (the source's fuse
        # bone is a point above the gun, not on it)
        vz = spec.get("vent", 0.10) * self.length
        near = np.abs(q2[:, 2] - vz) < 0.25 * self.length
        vr = float(np.hypot(q2[near, 0], q2[near, 1]).max()) if near.any() else self.radius
        self.fuse = np.array([0.0, vr + 0.005, vz]) - sh
        self.source_fuse = fuse
        self.muzzle = np.array([0.0, 0.0, self.length]) - sh
        self.breech = -sh
        # the colours for the made parts
        mats = {"bronze": (raw, is_bronze)}
        body = mgc.sub_part(gun, bones != spec["bone"].lower())
        self.patches = {}
        for key, (src_part, want) in (("bronze", mats["bronze"]), ("iron", (raw, is_iron)), ("iron2", (body, is_iron)),
                                      ("wood", (body, is_wood))):
            if self.img is None:
                break
            hit = texel_patch(self.img, src_part, want)
            if hit is not None:
                uv, i = hit
                self.patches[key] = (uv, src_part["materials"][i])
        if "iron" not in self.patches and "iron2" in self.patches:
            self.patches["iron"] = self.patches["iron2"]
        for key in ("bronze", "iron", "wood"):
            self.patches.setdefault(key, (raw["uvs"][raw["triangles"][0]].mean(0), self.material))
        # a patch of the field gun's gunner's white cloth (for the powder charge's bag), and of the red
        # on his texture (the linstock's hot tip)
        self.cloth = self.hot = None
        gpart = next((p for p in gr2_parts.mesh_parts(self.data) if p["name"] in recipe["gunner"]["meshes"]), None)
        if gpart is not None:
            gtex = next((n for n in gr2_mesh.read(self.data)["textures"] if n and "gunner" in n.lower()
                         and "_b." not in n.lower()), None)
            gimg = game.texture(gtex) if gtex else None
            if gimg is not None:
                # the material that draws the gunner's texture (not his cap's): both patches are read on it
                names = [str(m.get("Name") if hasattr(m, "get") else getattr(m, "Name", "")) for m in gpart["materials"]]
                gi = next((i for i, n in enumerate(names) if "gunner" in n.lower() and "cap" not in n.lower()), 0)
                body_tris = [k for k, t in enumerate(gpart["tri_material"]) if t == gi]
                gsub = dict(gpart, triangles=np.asarray(gpart["triangles"])[body_tris])
                hit = texel_patch(gimg, gsub, lambda c: opaque(c) and c[:3].mean() > 170 and np.ptp(c[:3]) < 30)
                if hit is not None:
                    self.cloth = (hit[0], gpart["materials"][gi])
                self.hot = red_texel(gimg, gpart["materials"][gi])
        # the linstock
        lspec = recipe["linstock"]
        if lspec.get("plain"):
            # a plain short wooden stick (the user, 2026-11-26): a round shaft, its last `hot` glowing red
            # (in game the fuse fire burns on bone_match at its very tip); its own frame: foot at the
            # origin, +y up the stick
            L, r, hot = lspec["length"], lspec.get("radius", 0.018), lspec.get("hot", 0.08)
            wood = self.patches["wood"]
            red = self.hot or self.patches["bronze"]
            shaft = cylinder((0.0, 0.0, 0.0), (0.0, L - hot, 0.0), r, sides=8, uv=wood[0])
            tip = cylinder((0.0, L - hot, 0.0), (0.0, L, 0.0), r, sides=8, uv=red[0])
            # two meshes of one material each (the tip on the gunner's texture, the shaft on the gun's)
            self.linstock = dict(shaft, materials=[wood[1]] * len(shaft["triangles"]))
            self.linstock_tip = dict(tip, materials=[red[1]] * len(tip["triangles"]))
            self.linstock_length = self.linstock_source_length = float(L)
            self.linstock_in_source = np.eye(4)
            self.linstock_data = self.data
            return
        ldata = game.granny(lspec["model"]) if lspec["model"] != spec["model"] else self.data
        lpart = next(p for p in gr2_parts.mesh_parts(ldata) if p["name"] == lspec["mesh"])
        lp = lpart["positions"]
        foot, top = lp[np.argmin(lp[:, 1])], lp[np.argmax(lp[:, 1])]
        lax = unit(top - foot)
        lside = unit(np.cross(lax, Z))
        lfwd = np.cross(lside, lax)
        Rl = np.array([lside, lax, lfwd])
        base = np.array([lp[:, 0].mean(), lp[:, 1].min(), lp[:, 2].mean()])
        lq = (lp - base) @ Rl.T
        self.linstock_source_length = float(lq[:, 1].max())
        # a short linstock (the user's choice, 2026-11-26): the staff's shaft pressed along its axis to
        # `length` (game units, about a forearm and an arm), its forked head and its foot kept
        want = lspec.get("length")
        if want:
            lq = lq.copy()
            lq[:, 1], _s, _c = press(lq[:, 1], self.linstock_source_length, want / self.linstock_source_length)
        self.linstock = {"positions": lq, "normals": lpart["normals"] @ Rl.T,
                         "tangents": lpart["tangents"] @ Rl.T, "uvs": lpart["uvs"], "triangles": lpart["triangles"],
                         "materials": [lpart["materials"][i] for i in lpart["tri_material"]]}
        self.linstock_length = float(lq[:, 1].max())
        # where the staff stands in the source model (its own frame -> the source's space): beside
        # the source's gunner at rest, as the pictures put it in his hand
        self.linstock_in_source = rot4(Rl.T)
        self.linstock_in_source[:3, 3] = base
        self.linstock_data = ldata


# --------------------------------------------------------------------------------------------------
# The cannon on its swivel


class CannonDesign:
    """The swivel and the cannon placed on the camel: parts in design space (the camel's model space
    at its bind pose, as make_gun_camel.GunDesign), the bones that move them, and the map to the gun
    model's space (the hang bone's). `scale` is the size seen in game against the source: the hang
    bone draws its triangles 1/s bigger than its bind (s, the bind's scale), so the design scale is
    scale x s."""

    # `match`: the linstock's hot tip (a game attaches the fuse fire there);
    # `ball` and `charge`: the next round, inside the bore (out of sight) but while he loads it by hand
    # (from the pouch at his left hip). No rammer (the user, 2026-11-26: he loads with his hands only).
    BONES = ("root", "post", "yaw", "cannon", "fuse", "muzzle", "linstock", "match", "ball", "charge")
    PARENT = {"root": None, "post": "root", "yaw": "post", "cannon": "yaw", "fuse": "cannon", "muzzle": "cannon",
              "linstock": "root", "match": "linstock", "ball": "root", "charge": "root"}
    NAMES = {"post": "bone_post", "yaw": "bone_yaw", "cannon": "bone_cannon", "fuse": "bone_fuse",
             "muzzle": "bone_launchpoint", "linstock": "bone_linstock", "match": "bone_match",
             "ball": "bone_ball", "charge": "bone_charge"}
    FLAME = (0.10, 0.024)                   # world units: the game's fuse fire at the tip, as the pictures draw it
    BALL = 0.040                            # the ball's radius (the bore at the muzzle: about 0.05)
    CHARGE = (0.042, 0.10)                  # the powder bag: radius, length

    def __init__(self, src, hang_bind, saddle_y, recipe):
        self.src, self.r = src, recipe
        self.bind = hang_bind
        self.bind_scale = float(np.cbrt(abs(np.linalg.det(hang_bind[:3, :3]))))
        self.R = hang_bind[:3, :3] / self.bind_scale
        self.S = np.linalg.inv(hang_bind)
        self.s = recipe["barrel"].get("scale", 1.0) * self.bind_scale
        self.ls = self.bind_scale                     # the linstock: a man's staff, at the game's size
        sw = recipe["swivel"]
        z = sw["z"]
        self.radius = src.radius_at_trunnion * self.s
        self.saddle = np.array([0.0, saddle_y, z])
        self.pivot = self.saddle + np.array([0.0, sw["socket"], 0.0])          # the fork turns here
        # the barrel pitches here: the prongs reach the bore's axis, the barrel clear of the cross bar
        self.trunnion = self.pivot + np.array([0.0, max(sw["fork"], self.radius + 0.10), 0.0])
        self.made = {}
        self._make()

    # source barrel space -> design space, level, muzzle ahead (+z)
    def bpoint(self, q):
        return self.trunnion + np.asarray(q, np.float64) * self.s

    def _make(self):
        s, src = self.s, self.src
        P = src.patches
        rad = self.radius
        sock_r = 0.07 * max(1.0, s / 0.9)
        half_gap = rad + 0.025                                       # the prongs' inner faces
        prong = (0.03, 0.5 * (self.trunnion[1] - self.pivot[1]) + 0.05, 0.06)
        # the socket: a wooden post from inside the saddle up to the pivot, an iron collar on top
        self.made["socket"] = (merge([
            cylinder(self.saddle - np.array([0.0, 0.10, 0.0]), self.pivot - np.array([0.0, 0.03, 0.0]), sock_r,
                     uv=P["wood"][0]),
            cylinder(self.pivot - np.array([0.0, 0.05, 0.0]), self.pivot, sock_r * 1.15, uv=P["iron"][0])]),
            P["wood"][1], "post")
        # the fork: a stem in the socket, a cross bar under the barrel, two prongs up to the trunnions
        bar_y = self.pivot[1] + 0.04
        fork = [cylinder(self.pivot - np.array([0.0, 0.02, 0.0]), self.pivot + np.array([0.0, 0.06, 0.0]),
                         sock_r * 0.6, uv=P["iron"][0]),
                box((0.0, bar_y, self.trunnion[2]), (half_gap + prong[0] * 2, 0.025, prong[2]), uv=P["iron"][0])]
        for sx in (-1.0, 1.0):
            x = sx * (half_gap + prong[0])
            y0, y1 = bar_y, self.trunnion[1] + 0.05
            fork.append(box((x, 0.5 * (y0 + y1), self.trunnion[2]), (prong[0], 0.5 * (y1 - y0), prong[2]),
                            uv=P["iron"][0]))
        self.made["fork"] = (merge(fork), P["iron"][1], "yaw")
        # the trunnion pins: through the prongs into the barrel
        pins = [cylinder(self.trunnion + np.array([sx * (rad - 0.03), 0.0, 0.0]),
                         self.trunnion + np.array([sx * (half_gap + 2 * prong[0] + 0.02), 0.0, 0.0]), 0.035,
                         uv=P["bronze"][0]) for sx in (-1.0, 1.0)]
        self.made["pins"] = (merge(pins), P["bronze"][1], "cannon")
        # the loading gear, each made in its own frame (design units: world x bind scale) and placed at
        # its rest frame: the ball and the bag round their centres
        bs = self.bind_scale
        rest = self.rest()
        self.made["ball"] = (apply_part(sphere(self.BALL * bs), rest["ball"], P["iron"][0]), P["iron"][1], "ball")
        cr, cl = (v * bs for v in self.CHARGE)
        cloth = src.cloth or P["wood"]
        self.made["charge"] = (apply_part(cylinder((0, 0, -cl / 2), (0, 0, cl / 2), cr, sides=8), rest["charge"],
                                          cloth[0]), cloth[1], "charge")

    def parts(self):
        """{name: (part dict with materials per triangle, bone key)} in design space."""
        src = self.src
        b = src.barrel
        out = {"barrel": ({"positions": self.bpoint(b["positions"]), "normals": b["normals"], "tangents": b["tangents"],
                           "uvs": b["uvs"], "triangles": b["triangles"], "materials": b["materials"]}, "cannon")}
        for name, (part, mat, bone) in self.made.items():
            p = dict(part)
            p["materials"] = [mat] * len(part["triangles"])
            out[name] = (p, bone)
        ls = src.linstock
        holder = self.linstock_rest()
        out["linstock"] = ({"positions": apply(holder, ls["positions"] * self.ls), "normals": ls["normals"] @ holder[:3, :3].T,
                            "tangents": ls["tangents"] @ holder[:3, :3].T, "uvs": ls["uvs"],
                            "triangles": ls["triangles"], "materials": ls["materials"]}, "linstock")
        tp = getattr(src, "linstock_tip", None)
        if tp is not None:
            out["linstock_tip"] = ({"positions": apply(holder, tp["positions"] * self.ls),
                                    "normals": tp["normals"] @ holder[:3, :3].T, "tangents": tp["tangents"] @ holder[:3, :3].T,
                                    "uvs": tp["uvs"], "triangles": tp["triangles"], "materials": tp["materials"]}, "linstock")
        return out

    def linstock_rest(self):
        """The linstock's frame at rest (design space): in a holster ring on the right of the saddle,
        by the rider's right thigh, leaning back and a little out (the short stick: its match by his
        hip)."""
        if self.src.linstock_length < 1.5:
            foot = self.saddle + np.array([0.20, -0.22, -0.16])
            R = axis_matrix(Z, -10.0) @ axis_matrix(X, -18.0)
        else:                                   # the long staff of the first preview
            foot = self.saddle + np.array([0.16, -0.30, -0.15])
            R = axis_matrix(X, -12.0)
        m = rot4(R)
        m[:3, 3] = foot
        if (m[:3, :3] @ Y)[0] < 0 and self.src.linstock_length < 1.5:     # out: toward +x (his right)
            m[:3, :3] = axis_matrix(Z, 10.0) @ axis_matrix(X, -18.0)
        return m

    def rest(self):
        """{bone: design frame at rest} (rigid, axis-aligned with the camel; the barrel level)."""
        out = {"root": rot4(self.R)}
        out["root"][:3, 3] = self.bind[:3, 3]
        out["post"] = tr(self.saddle)
        out["yaw"] = tr(self.pivot)
        out["cannon"] = tr(self.trunnion)
        out["fuse"] = tr(self.bpoint(self.src.fuse))
        out["muzzle"] = tr(self.bpoint(self.src.muzzle))
        out["linstock"] = self.linstock_rest()
        out["match"] = out["linstock"] @ tr((0.0, self.src.linstock_length * self.ls, 0.0))
        mid = self.bpoint(0.55 * self.src.breech + 0.45 * self.src.muzzle)
        out["ball"] = tr(mid)                    # inside the bore, out of sight
        out["charge"] = tr(mid - np.array([0.0, 0.0, 0.12 * self.bind_scale]))
        return out

    def frames(self, state):
        """{bone: design frame} for a state: `yaw` (degrees about the post's axis, positive toward
        the unit's right, +x), `pitch` (degrees about the trunnions, positive muzzle down), `recoil`
        (design units back along the barrel), `linstock` (its frame, None: in its holder)."""
        rest = self.rest()
        pitch = state.get("pitch", 0.0)
        # positive pitch puts the muzzle down: the turn about the side axis that lowers +z
        Rp = axis_matrix(X, pitch)
        if (Rp @ Z)[1] > 0 and pitch:
            Rp = axis_matrix(X, -pitch)
        cannon = tr(self.trunnion) @ rot4(Rp) @ tr((0.0, 0.0, -state.get("recoil", 0.0)))
        rel = cannon @ tr(-self.trunnion)
        out = {"root": rest["root"], "post": rest["post"], "yaw": rest["yaw"], "cannon": cannon,
               "fuse": rel @ rest["fuse"], "muzzle": rel @ rest["muzzle"]}
        for k in ("ball", "charge"):                     # inside the bore unless in his hands
            out[k] = rel @ rest[k]
        yaw = state.get("yaw", 0.0)
        if yaw:
            turn = tr(self.pivot) @ rot4(axis_matrix(Y, yaw)) @ tr(-self.pivot)
            for k in ("yaw", "cannon", "fuse", "muzzle", "ball", "charge"):
                out[k] = turn @ out[k]
        for k in ("ball", "charge"):
            if state.get(k) is not None:
                out[k] = state[k]
        ls = state.get("linstock")
        out["linstock"] = rest["linstock"] if ls is None else ls
        out["match"] = out["linstock"] @ tr((0.0, self.src.linstock_length * self.ls, 0.0))
        return out

    def to_model(self, frame):
        m = np.eye(4)
        m[:3, :3] = self.R.T @ frame[:3, :3]
        m[:3, 3] = point(self.S, frame[:3, 3])
        return m

    def model_bytes(self, name, source_data):
        rest = self.rest()
        bones = [(f"bone_{name}" if b == "root" else self.NAMES[b],
                  -1 if b == "root" else self.BONES.index(self.PARENT[b]),
                  np.eye(4) if b == "root" else self.to_model(rest[b])) for b in self.BONES]
        parts = []
        for key, (p, bone) in self.parts().items():
            parts.append({"name": f"{name}_{key}", "bone": self.NAMES[bone],
                          "positions": apply(self.S, p["positions"]), "normals": p["normals"] @ self.R,
                          "tangents": p["tangents"] @ self.R, "uvs": p["uvs"], "triangles": p["triangles"],
                          "materials": p["materials"]})
        return gr2_parts.rigid_model(source_data, bones[0][0], bones, parts, source_name=name)


# --------------------------------------------------------------------------------------------------
# The camel


def saddle_height(cut_data, mesh_name, x, z):
    """The highest point of the camel's surface (bind pose, file units) over (x, z)."""
    part = next(p for p in gr2_parts.mesh_parts(cut_data) if p["name"] == mesh_name)
    p, t = part["positions"], part["triangles"]
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    w1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
    w2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    w3 = 1.0 - w1 - w2
    hit = ok & (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
    ys = (w1 * a[:, 1] + w2 * b[:, 1] + w3 * c[:, 1])[hit]
    return float(ys.max())


def cut_camel(game, recipe):
    """(the camel's bytes without its swivel gun, the cut's description)."""
    out, info, post = mgc.cut_camel(game, recipe)
    info["post_top"] = np.round(post, 3).tolist()
    return out, info


def launch_bones(cut, camel, design, recipe):
    """The cut camel with `bone_turret` on the chest at the swivel's pivot (axis-aligned with the
    camel) and `bone_launchpoint` / `bone_muzzle` on it at the level muzzle: a game key that turns
    bone_turret about its y carries the shots round with the gun (turretArc)."""
    R = camel.bind[:3, :3] / design.bind_scale
    chest = recipe["camel"]["mount_bone"]
    turret = np.eye(4)
    turret[:3, :3] = R.T
    turret[:3, 3] = point(np.linalg.inv(camel.bind), design.pivot)
    turret_world = camel.bind @ turret
    local = np.eye(4)
    local[:3, 3] = point(np.linalg.inv(turret_world), design.bpoint(design.src.muzzle))
    world = turret_world @ local
    return gr2_parts.add_bones(cut, [("bone_turret", chest, turret, turret_world),
                                     ("bone_launchpoint", "bone_turret", local, world),
                                     ("bone_muzzle", "bone_turret", local, world)])


# --------------------------------------------------------------------------------------------------
# Pictures


class Gunner:
    """The artillerist on foot as the previews show him: the source model's gunner mesh (and only
    it) posed by that model's own rest or a clip, placed on the ground."""

    def __init__(self, game, spec):
        self.data = game.granny(spec["model"])
        self.fig = mgc.Figure(game, self.data)
        self.fig.meshes = [(m, t) for m, t in self.fig.meshes if m.get("name") in spec["meshes"]]
        self.rig = Rig.of(gr2.load(self.data).root())
        # which way he faces at rest: from his ankles to his toes (the feet's vertices ahead of the
        # foot bones), level
        rest = self.rig.by_name(self.rig.rest_worlds())
        mesh = self.fig.meshes[0][0]
        p = np.asarray(mesh["file_positions"], np.float64)
        names = mesh["skin_names"]
        vb = np.asarray(mesh["vertex_bones4"])[np.arange(len(p)), np.argmax(np.asarray(mesh["vertex_weights4"]), 1)]
        fwd = np.zeros(3)
        for s in ("l", "r"):
            k = next(i for i, n in enumerate(names) if n.lower() == f"bip01 {s} foot")
            fwd += p[vb == k].mean(0) - rest[f"bip01 {s} foot"][:3, 3]
        fwd[1] = 0.0
        self.facing = math.degrees(math.atan2(fwd[0], fwd[2]))     # 0: +z

    def items(self, place, anim=None, t=0.0):
        """His meshes and pose with his pelvis over `place`'s origin, facing its +z."""
        pose = self.rig.by_name(self.rig.pose(anim, t)) if anim is not None else self.rig.by_name(self.rig.rest_worlds())
        pel = pose["bip01 pelvis"][:3, 3]
        move = place @ rot4(axis_matrix(Y, -self.facing)) @ tr((-pel[0], 0.0, -pel[2]))
        return self.fig.items(pose, move), {k: move @ v for k, v in pose.items()}, move


class Picture:
    """The unit put together for a still: camel pose, gun state, rider or gunner."""

    def __init__(self, game, recipe, camel, rider, scene, design, gun_bytes, gunner):
        self.game, self.r, self.camel, self.rider, self.scene = game, recipe, camel, rider, scene
        self.design = design
        self.gun_fig = mgc.Figure(game, gun_bytes)
        self.gun_rig = Rig.of(gr2.load(gun_bytes).root())
        self.gunner = gunner

    def gun_items(self, P, state):
        fr = self.design.frames(state)
        hang = rigid(P[self.camel.hang])
        G = {self.design.NAMES.get(k, f"bone_{self.r['name']}_gun").lower(): hang @ self.design.to_model(v)
             for k, v in fr.items()}
        G[self.gun_rig.names[0].lower()] = hang
        return self.gun_fig.items(G), G

    def limbered(self, state=None, anim=None, t=0.0):
        cam = self.camel
        P = cam.fix_hang(cam.pose(cam.anim(anim) if anim else cam.base, t))
        st = dict(self.r["limber"]) if state is None else state
        items, G = self.gun_items(P, st)
        R = self.rider.seated(self.rider.idle, 0.0, P[cam.rider_bone], square=True)
        items += self.scene.camel_fig.items(P) + self.scene.rider_fig.items(R) + self.scene.hat_items(R)
        return items, P, G

    def design_frame(self, P, world):
        """A rigid world frame as a frame of the gun's design space (the inverse of the hang)."""
        C = rigid(P[self.camel.hang]) @ self.design.S
        Cr = C[:3, :3] / np.cbrt(abs(np.linalg.det(C[:3, :3])))
        f = np.eye(4)
        f[:3, :3] = Cr.T @ world[:3, :3]
        f[:3, 3] = point(np.linalg.inv(C), world[:3, 3])
        return f

    def deployed(self, yaw=0.0, side=-1.0, away=0.85, back=0.25):
        """The camel lying (the borrowed lying-down idle), the barrel level, the artillerist on foot
        on `side` (-1: the unit's left) `away` from the vent and `back` behind it, facing it, the
        linstock in his hand as the source's gunner holds his staff."""
        cam = self.camel
        P = cam.grounded(cam.anim(mgc.B_IDLE), [0.0])[0]
        st = {"yaw": yaw, "pitch": 0.0}
        _items, G = self.gun_items(P, st)
        marks = []
        g_items = []
        if self.gunner is not None:
            vent = G["bone_fuse"][:3, 3]
            at = np.array([vent[0] + side * away, 0.0, vent[2] - back])
            d = vent - at
            place = tr(at) @ rot4(axis_matrix(Y, math.degrees(math.atan2(d[0], d[2]))))
            g_items, _gp, move = self.gunner.items(place)
            st["linstock"] = self.design_frame(P, move @ self.design.src.linstock_in_source)
            marks.append((vent, (255, 120, 40), 7))
        items, G = self.gun_items(P, st)
        items += self.scene.camel_fig.items(P) + g_items
        return items, P, G, marks

    def deployed_rider(self, foot_rig, side=-1.0, away=0.85, back=0.25):
        """As `deployed`, the artillerist being the unit's own rider on foot (an infantry stance put
        on his skeleton), the linstock upright in his right hand, its foot on the ground."""
        cam = self.camel
        P = cam.grounded(cam.anim(mgc.B_IDLE), [0.0])[0]
        st = {"yaw": 0.0, "pitch": 0.0}
        _items, G = self.gun_items(P, st)
        vent = G["bone_fuse"][:3, 3]
        at = np.array([vent[0] + side * away, 0.0, vent[2] - back])
        d = vent - at
        heading = math.degrees(math.atan2(d[0], d[2]))
        game = self.game
        R = self.rider.standing(foot_rig, Animation.load(game.granny(mgc.STAND_CLIP)), 0.0, heading, at)
        hand = R["bip01 r hand"][:3, 3]
        W = rot4(axis_matrix(Y, heading))
        W[:3, 3] = (hand[0], 0.0, hand[2])
        st["linstock"] = self.design_frame(P, W)
        items, G = self.gun_items(P, st)
        items += self.scene.camel_fig.items(P) + self.scene.rider_fig.items(R) + self.scene.hat_items(R)
        return items, P, G, [(vent, (255, 120, 40), 7)]


def model_sheet(path, pic, recipe, today=None, midfa=None, foot_rig=None):
    """The new zamburak: limbered from four sides, deployed from four sides, the barrel against the
    source's, and today's unit for reference."""
    from PIL import Image
    w, h = 300, 270
    view = dict(span=4.2, centre=(0.0, 1.7, 0.45))

    def tile(items, az, el, text, marks=None, **kw):
        v = dict(view)
        v.update(kw)
        return mgc.caption(mgc.draw(items, w, h, az, el, marks=marks, **v), text)

    views = [("FRONT 3/4", -40.0, 16.0), ("LEFT", -90.0, 8.0), ("BACK 3/4", -140.0, 16.0), ("RIGHT", 90.0, 8.0)]
    rows = []
    if today is not None:
        rows.append(("REFERENCE: TODAY'S MEZAMBURAK (STOCK ZAMBURAK CAMEL, LATERAL SWIVEL GUN)",
                     [tile(today, az, el, f"TODAY {name}") for name, az, el in views[:2]] +
                     ([tile(midfa, az, el, f"THE MIDFA {name}", span=7.0, centre=(0.0, 1.2, -0.8))
                       for name, az, el in views[1:3]] if midfa is not None else [])))
    lim = recipe["limber"]
    items, _P, _G = pic.limbered()
    rows.append((f"NEW - LIMBERED: BARREL {lim['pitch']:.0f} DEG DOWN" +
                 (f", TURNED {lim['yaw']:.0f} DEG" if lim.get("yaw") else "") + ", RIDER IN THE SADDLE",
                 [tile(items, az, el, f"LIMBERED {name}") for name, az, el in views]))
    items, _P, _G, marks = pic.deployed()
    rows.append(("NEW - UNLIMBERED: CAMEL LYING, BARREL LEVEL, THE ARTILLERIST BESIDE IT WITH THE LINSTOCK "
                 "(STAR: THE VENT)",
                 [tile(items, az, el, f"UNLIMBERED {name}", marks=marks, centre=(-0.3, 1.1, 0.45))
                  for name, az, el in views]))
    lim_items, _P, LG = pic.limbered()
    dep_items, _P, DG, dmarks = pic.deployed()
    lc = LG["bone_cannon"][:3, 3]
    dc = DG["bone_fuse"][:3, 3]
    rows.append(("NEW - FROM ABOVE, AND CLOSE ON THE SWIVEL",
                 [tile(lim_items, -90.0, 80.0, "LIMBERED FROM ABOVE"),
                  tile(dep_items, -90.0, 80.0, "UNLIMBERED FROM ABOVE", centre=(-0.3, 1.1, 0.45)),
                  tile(lim_items, -55.0, 20.0, "LIMBERED, THE SWIVEL CLOSE", span=1.6, centre=tuple(lc)),
                  tile(dep_items, -100.0, 12.0, "UNLIMBERED, THE VENT CLOSE", marks=dmarks, span=2.2,
                       centre=(dc[0] - 0.3, dc[1] - 0.3, dc[2]))]))
    if foot_rig is not None:
        ri, _P, _G, rmarks = pic.deployed_rider(foot_rig)
        rows.append(("THE ARTILLERIST: THE UNIT'S OWN RIDER ON FOOT (LEFT PAIR) OR THE MIDFA'S GUNNER (RIGHT PAIR)",
                     [tile(ri, -60.0, 12.0, "RIDER ON FOOT FRONT 3/4", marks=rmarks, centre=(-0.3, 1.1, 0.45)),
                      tile(ri, -130.0, 12.0, "RIDER ON FOOT BACK 3/4", marks=rmarks, centre=(-0.3, 1.1, 0.45)),
                      tile(dep_items, -60.0, 12.0, "MIDFA GUNNER FRONT 3/4", marks=dmarks, centre=(-0.3, 1.1, 0.45)),
                      tile(dep_items, -130.0, 12.0, "MIDFA GUNNER BACK 3/4", marks=dmarks,
                           centre=(-0.3, 1.1, 0.45))]))
    width = 4 * w
    out = [mgc.title(width, f"{recipe['name'].upper().replace('_', ' ')} - MODEL PREVIEW", back=(70, 40, 20))]
    for text, tl in rows:
        out.append(mgc.title(width, text, scale=1, back=(30, 30, 30)))
        out.append(mgc.grid(tl + [np.full_like(tl[0], 255)] * (4 - len(tl)), 4))
    Image.fromarray(np.concatenate(out, 0)).save(path)


def barrel_sheet(path, game, src, recipe):
    """The source's barrel beside the shortened one, side and top, to scale."""
    from PIL import Image
    w, h = 600, 200
    tex = src.img
    sc = recipe["barrel"].get("scale", 1.0)

    def items(part, s, y):
        uv = part["uvs"].copy()
        uv[:, 1] = 1.0 - uv[:, 1]                       # as stored -> as drawn (Granny's V flipped)
        p = (part["positions"] - src.breech) * s + np.array([0.0, y, 0.0])
        return [(p, part["triangles"], uv, tex, (180, 140, 60))]
    it = (items(src.barrel_source, 1.0, 0.7) + items(src.barrel, 1.0, 0.0) + items(src.barrel, sc, -0.6))
    img = mgc.draw(it, 900, 320, -90.0, 0.0, span=3.4, centre=(0.0, 0.05, 1.3), ground=False)
    img = mgc.caption(img, f"TOP: THE MIDFA'S BARREL ({src.source_length:.2f}). MIDDLE: {recipe['barrel']['length']:.2f} "
                           f"OF ITS LENGTH ({src.length:.2f}). BOTTOM: THAT AT {sc:.2f} OF ITS SIZE "
                           f"({src.length * sc:.2f}). MUZZLE LEFT.")
    Image.fromarray(img).save(path)


def today_items(game, recipe):
    """Today's MEZamburak at rest: the stock zamburak camel with its swivel gun, the WoL rider."""
    camel_data = game.granny(recipe["camel"]["model"])
    rig = Rig.of(gr2.load(camel_data).root())
    P = rig.by_name(rig.pose(Animation.load(game.granny(mgc.ZAMB + "zamburak_camel_idle00")), 0.0))
    items = mgc.Figure(game, camel_data).items(P)
    rdata = game.granny(recipe["rider"]["model"])
    rrig = Rig.of(gr2.load(rdata).root())
    att = rigid(P["bone attachpoint"])
    R = {k: att @ v for k, v in rrig.by_name(rrig.pose(Animation.load(game.granny(mgc.ZAMB + "zamburak_rider_idle00")),
                                                        0.0)).items()}
    return items + mgc.Figure(game, rdata).items(R)


def midfa_items(game, recipe):
    data = game.granny(MIDFA + "Midfa")
    return mgc.Figure(game, data).items()


# --------------------------------------------------------------------------------------------------
# The clips (the beat-list script approved on 2026-11-26, z-script-v1: every beat below names its
# time in that script)

Z_IDLE = mgc.ZAMB + "zamburak_camel_idle00"
LIMBERED = [  # (our name, the anim it plays under, the camel's own clip, the rider's base, gait nod, both on the reins)
    ("idle", "Idle", Z_IDLE, None, 0.0, False),
    ("walk", "Walk", mgc.ZAMB + "zamburak_camel_walk00", None, 1.5, False),
    ("jog", "Jog", mgc.ZAMB + "zamburak_camel_jog", None, 3.0, False),
    ("run", "Run", mgc.LIB + "cavalry\\horse_gallop", None, 4.0, True),
    ("bored_a", "Bored", mgc.ZAMB + "zamburak_camel_idle02", None, 0.0, False),
    ("bored_b", "Bored", mgc.ZAMB + "zamburak_camel_idle03", None, 0.0, False),
    ("bored_c", "Bored", mgc.ZAMB + "zamburak_camel_idle06", None, 0.0, False),
]
# Cheer: today's rider cheers, unchanged, each on one of the camel's idles of the same length (the
# 3.67 s cheer H on idle03 played a little faster); the camel clips written with the rider's bone held
# and its head kept off the barrel
CHEERS = [("cheer_a", mgc.ZAMB + "zamburak_camel_idle02", mgc.LIB + "cavalry\\sword_cheer_F"),
          ("cheer_b", mgc.ZAMB + "zamburak_camel_idle03", mgc.LIB + "cavalry\\sword_cheer_H"),
          ("cheer_c", Z_IDLE, mgc.LIB + "cavalry\\sword_bored_A"),
          ("cheer_d", mgc.ZAMB + "zamburak_camel_idle06", mgc.LIB + "cavalry\\sword_cheer_E")]
UNLIMBER, LIMBER_T, DEPLOYED, FIRE, RELOAD, DEATH_B = 6.3333, 5.1667, 2.0, 2.0, 3.0, 3.0
SHOT = 0.90
RELEASE = 0.10           # killed unlimbered: the linstock leaves his hand as he is hit
STAFF_R = 0.035          # the staff's radius (game units): the palm sits this far from its axis


def ease(u):
    return mgc.smooth(min(1.0, max(0.0, u)))


def span(t, a, b):
    """0 before a, 1 after b, eased between."""
    return ease((t - a) / max(b - a, 1e-9))


def vslerp(a, b, w):
    """Between two directions along the great circle (a hand's fingers or palm turning, never through
    nothing when they are opposite: then about the vertical, or the x axis)."""
    a, b = unit(a), unit(b)
    d = float(max(-1.0, min(1.0, a @ b)))
    ang = math.acos(d)
    if ang < 1e-6:
        return a
    axis = np.cross(a, b)
    if np.linalg.norm(axis) < 1e-6:
        axis = np.cross(a, Y)
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, X)
    return unit(axis_matrix(unit(axis), math.degrees(ang * w)) @ a)


def lerp(a, b, w):
    return np.asarray(a, np.float64) + (np.asarray(b, np.float64) - np.asarray(a, np.float64)) * w


class Built:
    def __init__(self, name, anim, times):
        self.name, self.anim, self.times = name, anim, np.asarray(times, np.float64)
        self.length = float(self.times[-1])
        self.camel, self.gun, self.rider = [], [], []
        self.grips = []          # (name, side, t0, t1): his palm on the staff in that window
        self.reach = 0.0
        self.camel_bytes = self.gun_bytes = self.rider_bytes = None
        self.camel_name = None


class ZUnit:
    """The zamburak cannon's clips: the camel's (its own, the borrowed lying-down ones laid on the
    ground), the gun's (the swivel's turn and tilt, the linstock's frame) and the rider's, from the
    script's beats; written as the game's files."""

    def __init__(self, game, recipe, camel, rider, design, foot_rig):
        self.game, self.r, self.camel, self.rider, self.d = game, recipe, camel, rider, design
        self.foot = foot_rig
        self.limber = dict(recipe["limber"])
        self.src = design.src
        self.L = self.src.linstock_length            # the staff's length (game units)
        self._lie = None
        self._stand = None
        self.stand_anim = rider.anim(mgc.STAND_CLIP)
        self.gun_name = f"{recipe['name']}_gun"
        self._fwd_sign = None

    # -- frames

    def C(self, P):
        return rigid(P[self.camel.hang]) @ self.d.S

    def lie(self):
        if self._lie is None:
            cam = self.camel
            self._lie = cam.fix_hang(cam.grounded(cam.anim(mgc.B_IDLE), [0.0])[0])
        return self._lie

    def staff_world(self, P, frame):
        """The staff's world frame (x, y along the staff, z; origin its foot) of a design frame."""
        C = self.C(P)
        s = np.cbrt(abs(np.linalg.det(C[:3, :3])))
        W = np.eye(4)
        W[:3, :3] = (C[:3, :3] / s) @ frame[:3, :3]
        W[:3, 3] = point(C, frame[:3, 3])
        return W

    def staff_design(self, P, W):
        C = self.C(P)
        Cr = C[:3, :3] / np.cbrt(abs(np.linalg.det(C[:3, :3])))
        f = np.eye(4)
        f[:3, :3] = Cr.T @ W[:3, :3]
        f[:3, 3] = point(np.linalg.inv(C), W[:3, 3])
        return f

    @staticmethod
    def staff(foot, axis, side=None):
        """A staff frame: its foot, +y along `axis`; x level where it can be."""
        y = unit(axis)
        x = np.cross(y, Z if side is None else side)
        if np.linalg.norm(x) < 1e-6:
            x = np.cross(y, X)
        x = unit(x)
        z = np.cross(x, y)
        W = np.eye(4)
        W[:3, 0], W[:3, 1], W[:3, 2], W[:3, 3] = x, y, z, foot
        return W

    def staff_mix(self, A, B, w, arc=None):
        """Between two staff frames: the foot moved (out along `arc` at mid-way, so a staff passed
        across him stays clear of his body), the axis and the facing of its head turned."""
        foot = lerp(A[:3, 3], B[:3, 3], w)
        if arc is not None:
            foot = foot + np.asarray(arc, np.float64) * math.sin(math.pi * min(1.0, max(0.0, w)))
        axis = unit(lerp(A[:3, 1], B[:3, 1], w))
        side = lerp(A[:3, 2], B[:3, 2], w)
        return self.staff(foot, axis, side=side if np.linalg.norm(side) > 1e-6 else None)

    def ring(self, P):
        return self.staff_world(P, self.d.linstock_rest())

    def gun_frames(self, state):
        return self.d.frames(state)

    def cascabel(self, P, fr):
        """(palm, finger, normal) world: the left palm on top of the knob behind the breech."""
        C = self.C(P)
        to_w = C @ fr["cannon"] @ tr(-self.d.trunnion)
        b = point(to_w, self.d.bpoint(self.src.breech))
        m = point(to_w, self.d.bpoint(self.src.muzzle))
        ax = unit(m - b)
        upv = unit(np.cross(np.cross(ax, Y), ax)) if abs(ax @ Y) < 0.99 else Z
        if upv @ Y < 0:
            upv = -upv
        rad = self.d.radius / self.d.bind_scale
        palm = b - 0.04 * ax + (0.6 * rad + 0.03) * upv
        return palm, ax, -upv

    # -- the rider

    def fwd_lean(self, R, deg):
        """The trunk leaned forward by `deg` (back if negative) about his side axis at the spine."""
        if not deg:
            return R
        if self._fwd_sign is None:
            h0 = R["bip01 head"][:3, 3]
            T = self.rider.turn(R, "bip01 spine", self.side_axis(R), 10.0)
            self._fwd_sign = 1.0 if (T["bip01 head"][:3, 3] - h0) @ self.facing(R) > 0 else -1.0
        return self.rider.turn(R, "bip01 spine", self.side_axis(R), self._fwd_sign * deg)

    def facing(self, R):
        f = R["bip01 pelvis"][:3, :3] @ (self.rider.body.base["bip01 pelvis"][:3, :3].T @ Z)
        f = np.array([f[0], 0.0, f[2]])
        return unit(f)

    def side_axis(self, R):
        return unit(np.cross(Y, self.facing(R)))          # +: his left... the turn's sign is measured

    def right_of(self, R):
        f = self.facing(R)
        return unit(np.array([f[2], 0.0, -f[0]]))          # the unit's right when he faces +z: +x

    def seated(self, P, t=0.0, length=None):
        anim = self.rider.idle
        tb = (t * anim.duration / length) % anim.duration if length else 0.0
        return self.rider.seated(anim, tb, rigid(P[self.camel.rider_bone]), square=True)

    def reins(self, R, P, s):
        A = rigid(P[self.camel.rider_bone])[:3, :3]
        side = 0.07 if s == "r" else -0.07
        palm = R["bip01 pelvis"][:3, 3] + A @ np.array([side, 0.05, 0.27])
        return palm, A @ np.array([-3.0 * side, -0.3, 1.0]), A @ np.array([0.0, -1.0, 0.25])

    def grip_on(self, R, W, dist, s, normal_hint=None, lock=None):
        """(palm, finger, normal): his palm on the staff `dist` from its foot, on the side toward his
        shoulder, the fingers round it toward where he faces."""
        ax = W[:3, 1]
        p = point(W, (0.0, dist, 0.0))
        key = (s, round(float(dist if lock is None else lock), 2))
        locks = getattr(self, "_locks", None)
        if locks is not None and key in locks:
            # the palm keeps its side of the staff and its fingers' way round it while it holds it (it
            # neither slides round the staff nor turns over on it)
            to_l, fin_l = locks[key]
            to = unit(W[:3, :3] @ to_l)
            to = unit(to - (to @ ax) * ax)
            fin = unit(W[:3, :3] @ fin_l)
        else:
            sh = R[f"bip01 {s} upperarm"][:3, 3]
            to = sh - p
            if normal_hint is None and np.linalg.norm(to - (to @ ax) * ax) < 0.08:
                to = to + 0.10 * Y        # the staff points at his shoulder: his palm on its top side
            to = unit(to - (to @ ax) * ax) if normal_hint is None else unit(normal_hint - (normal_hint @ ax) * ax)
            fin = np.cross(ax, -to)
            if fin @ self.facing(R) < 0:
                fin = -fin
            if locks is not None:
                locks[key] = (W[:3, :3].T @ to, W[:3, :3].T @ unit(fin))
        if locks is not None:
            self._used.add(s)
        nrm = -to
        fin = unit(fin - (fin @ nrm) * nrm)
        return p + STAFF_R * to, fin, nrm

    def left_grip(self, S, staffs, g_r, reach=0.50):
        """Where on the staff his left palm holds it while both hands work it (the grip never slides):
        the place whose farthest distance from his left shoulder over the key frames `staffs` is the
        least, at least 0.22 from the right hand's."""
        sh = S["bip01 l upperarm"][:3, 3]
        best = None
        for g in np.arange(0.2, self.L - 0.1, 0.02):
            if abs(g - g_r) < 0.22:
                continue
            far = max(float(np.linalg.norm(point(W, (0.0, g, 0.0)) - sh)) for W in staffs)
            if best is None or far < best[0]:
                best = (far, float(g))
        return best[1]

    def hang_hand(self, R, s):
        """A hand hanging at his side: below the shoulder, a little ahead."""
        sh = R[f"bip01 {s} upperarm"][:3, 3]
        f, rt = self.facing(R), self.right_of(R)
        out = rt if s == "r" else -rt
        palm = sh - 0.52 * Y + 0.06 * f + 0.07 * out
        return palm, -Y, -out

    def poles(self, R, seated):
        f, rt = self.facing(R), self.right_of(R)
        if seated:
            return {"r": unit(1.0 * rt - 0.6 * Y - 0.4 * f), "l": unit(-1.0 * rt - 0.6 * Y - 0.4 * f)}
        # out to his sides and back, nearly level: never along an arm that hangs or reaches forward
        return {"r": unit(0.8 * rt - 0.5 * Y - 0.3 * f), "l": unit(-0.8 * rt - 0.5 * Y - 0.3 * f)}

    def hands(self, R, goals, b, seated):
        # a hand that holds no staff this frame lets go of its places on it
        used = getattr(self, "_used", set())
        for s in ("l", "r"):
            if s not in used and getattr(self, "_locks", None):
                self._locks = {k: v for k, v in self._locks.items() if k[0] != s}
        self._used = set()
        poles = self.poles(R, seated)
        base = R
        from aoe3game.gr2_pose import about, descendants
        if getattr(self, "_chest_set", None) is None:
            self._chest_set = descendants(self.rider.rig, "bip01 spine1")
        for _k in range(4):
            Q = base
            for s, g in goals.items():
                if g is None:
                    continue
                palm, fin, nor = g
                Q = self.rider.hand(Q, s, palm, unit(fin), unit(nor), poles[s])
            miss = {s: float(np.linalg.norm(self.rider.palm_of(Q, s) - g[0])) for s, g in goals.items() if g is not None}
            worst = max(miss.values(), default=0.0)
            if worst < 0.008 or not getattr(self, "lean_to_reach", True):
                break
            # out of reach: the chest leans toward that hand's goal (about the spine's top), as a man
            # reaches; the legs stay
            s = max(miss, key=miss.get)
            pivot = base["bip01 spine1"][:3, 3]
            a_, g_ = base[f"bip01 {s} upperarm"][:3, 3] - pivot, goals[s][0] - pivot
            axis = np.cross(a_, g_)
            if np.linalg.norm(axis) < 1e-9:
                break
            ang = math.degrees(math.asin(min(0.45, 1.15 * worst / max(float(np.linalg.norm(g_)), 1e-6))))
            turn = about(pivot, axis_matrix(unit(axis), ang))
            base = {k: (turn @ v if k in self._chest_set else v) for k, v in base.items()}
        for s, g in goals.items():
            if g is not None:
                b.reach = max(b.reach, float(np.linalg.norm(self.rider.palm_of(Q, s) - g[0])))
        return Q

    @staticmethod
    def blend_goal(a, z, w, lift=0.0, arc=None):
        """Between two hand goals; the palm rises `lift` at mid-way, and swings out along `arc` (a
        vector) so a hand crossing in front of him clears his body."""
        if w <= 0.0:
            return a
        if w >= 1.0:
            return z
        palm = lerp(a[0], z[0], w) + np.array([0.0, lift * math.sin(math.pi * w), 0.0])
        if arc is not None:
            palm = palm + np.asarray(arc, np.float64) * math.sin(math.pi * w)
        return palm, vslerp(a[1], z[1], w), vslerp(a[2], z[2], w)

    # standing

    def standing(self, at, heading, t=0.0):
        anim = self.stand_anim
        return self.rider.standing(self.foot, anim, t % anim.duration, heading, np.asarray(at, np.float64))

    def station(self):
        """(where he stands, his heading): on the camel's left, beside the vent of the level cannon on
        the lying camel, facing it."""
        if self._stand is None:
            P = self.lie()
            fr = self.gun_frames({})
            vent = point(self.C(P), fr["fuse"][:3, 3])
            at = np.array([vent[0] - self.r.get("station", {}).get("out", 0.80), 0.0,
                           vent[2] - self.r.get("station", {}).get("back", 0.25)])
            d = vent - at
            self._stand = (at, math.degrees(math.atan2(d[0], d[2])), vent)
        return self._stand

    def plant(self, R, feet):
        """`R` with each leg solved onto its foot frame in `feet` ({side: 4 x 4})."""
        from aoe3game.gr2_pose import two_bone_ik
        rig, hinge = self.rider.rig, self.rider.body.hinge
        f = self.facing(R)
        for s, F in feet.items():
            th, ca, fo = (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot")
            R = two_bone_ik(R, rig, th, ca, fo, F[:3, 3], f, hinge[th], hinge[ca], end_frame=F[:3, :3])
        return R

    def walk(self, A, B, u, lead):
        """From stand pose A to stand pose B in two steps: `lead` foot first (u 0-0.5), the other
        (0.5-1); the planted foot never moves, the stepping one lifts 0.08 at mid-step."""
        from aoe3game.gr2_pose import blend
        body = blend(self.rider.rig, A, B, ease(u))
        other = "l" if lead == "r" else "r"
        feet = {}
        for s, (a, z) in ((lead, (0.0, 0.5)), (other, (0.5, 1.0))):
            w = span(u, a, z)
            Fa, Fb = A[f"bip01 {s} foot"], B[f"bip01 {s} foot"]
            F = np.eye(4)
            from aoe3game.gr2_pose import slerp
            from aoe3game.gr2_anim import matrix_quat
            from aoe3game.gr2_skin import quat_matrix
            F[:3, :3] = quat_matrix(slerp(matrix_quat(Fa[:3, :3]), matrix_quat(Fb[:3, :3]), w))
            F[:3, 3] = lerp(Fa[:3, 3], Fb[:3, 3], w) + np.array([0.0, 0.08 * math.sin(math.pi * w), 0.0])
            feet[s] = F
        return self.plant(body, feet)

    # -- a clip's camel poses

    def camel_own(self, rel, times):
        cam = self.camel
        anim = cam.anim(rel)
        poses = [cam.fix_hang(cam.pose(anim, float(t))) for t in times]
        scales = cam.hang_scale(poses[0], cam._scales[id(anim)])
        return poses, anim, scales

    def camel_borrow(self, rel, times, start):
        """The borrowed lying-down clip from `start` (held before and after it)."""
        cam = self.camel
        anim = cam.anim(rel)
        cache, poses = {}, []
        for t in times:
            tt = min(max(float(t) - start, 0.0), anim.duration)
            if tt not in cache:
                cache[tt] = cam.fix_hang(cam.grounded(anim, [tt])[0])
            poses.append(cache[tt])
        return poses, anim, cam.hang_scale(poses[0], cam.borrowed_scales(anim))

    # -- the clips

    def times(self, length):
        """A clip's frames (and a fresh start for the grips and the gaze, which carry from frame to
        frame within a clip)."""
        self._locks, self._used, self._gaze, self._saddle_fin = {}, set(), None, None
        n = max(2, int(round(length * FPS)) + 1)
        return np.linspace(0.0, length, n)

    GAZE_SPEED = 300.0        # degrees a second the gaze may swing (the head then stays under its limit)

    def look(self, R, target, **kw):
        """The head turned toward `target`, the gaze swinging at most GAZE_SPEED from the last frame
        of this clip (no snap when what he looks at changes)."""
        head = R["bip01 head"][:3, 3]
        d = unit(np.asarray(target, np.float64) - head)
        last = getattr(self, "_gaze", None)
        if last is not None:
            step = math.radians(self.GAZE_SPEED / FPS)
            ang = math.acos(max(-1.0, min(1.0, float(last @ d))))
            if ang > step:
                axis = np.cross(last, d)
                if np.linalg.norm(axis) < 1e-9:
                    axis = Y
                d = axis_matrix(unit(axis), math.degrees(step)) @ last
        self._gaze = unit(d)
        return self.rider.look(R, head + 6.0 * self._gaze, **kw)

    def barrel_gap(self, P, fr):
        """The least gap between the barrel and the camel's body at pose P (the saddle under the
        swivel left out), game units."""
        d, cam = self.d, self.camel
        C = self.C(P)
        to_w = C @ fr["cannon"] @ tr(-d.trunnion)
        a, b = point(to_w, d.bpoint(self.src.breech)), point(to_w, d.bpoint(self.src.muzzle))
        pivot = point(C, d.pivot)
        pts = cam.mesh_points(P)[used_vertices(cam)]
        pts = pts[np.linalg.norm(pts - pivot, axis=1) > 0.35]
        ab = b - a
        u = np.clip(((pts - a) @ ab) / (ab @ ab), 0.0, 1.0)
        return float((np.linalg.norm(pts - (a + u[:, None] * ab), axis=1) - d.radius / d.bind_scale).min())

    CLEAR = 0.015         # the gap the camel's head keeps from the barrel

    def keep_head_clear(self, poses, times, fr):
        """Where the camel's own clip swings its head into the barrel (the bored idles turn it to
        the right, where pose B puts the muzzle), the neck bent down just enough, eased in and out
        over half a second either side: (poses, the largest bend in degrees)."""
        cam = self.camel
        need = np.zeros(len(poses))
        for i, P in enumerate(poses):
            if self.barrel_gap(P, fr) >= self.CLEAR:
                continue
            for deg in range(4, 61, 4):
                if self.barrel_gap(cam.lower_head(P, deg), fr) >= self.CLEAR:
                    break
            need[i] = deg
        if not need.any():
            return poses, 0.0
        half = int(round(0.5 * FPS))
        kernel = [ease((k + 1) / (half + 1)) for k in range(half)] + [1.0] + \
                 [ease((half - k) / (half + 1)) for k in range(half)]
        bend = np.array([max(need[j] * kernel[j - i + half] for j in range(max(0, i - half), min(len(need), i + half + 1)))
                         for i in range(len(need))])
        return [cam.lower_head(P, float(a)) if a > 0 else P for P, a in zip(poses, bend)], float(bend.max())

    def limbered(self, name, anim_name, rel, gait, reins_only, look=None):
        cam = self.camel
        length = cam.anim(rel).duration
        times = self.times(length)
        b = Built(name, anim_name, times)
        poses, anim, scales = self.camel_own(rel, times)
        fr = self.gun_frames(self.limber)
        poses, b.head_bend = self.keep_head_clear(poses, times, fr)
        for t, P in zip(times, poses):
            u = t / length
            R = self.seated(P, t if not gait else 0.0, length if not gait else None)
            if gait:
                R = self.fwd_lean(R, gait * math.sin(4 * math.pi * u))
            goals = {"r": self.reins(R, P, "r"),
                     "l": self.reins(R, P, "l") if reins_only else self.cascabel(P, fr)}
            R = self.hands(R, goals, b, True)
            R = self.look(R, self.gaze_limbered(R, P, fr, t, look))
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=self.d.linstock_rest()))
            b.rider.append(R)
        b.camel_src = (anim, scales)
        return b

    def gaze_limbered(self, R, P, fr, t, look):
        A = rigid(P[self.camel.rider_bone])[:3, :3]
        ahead = R["bip01 head"][:3, 3] + 12.0 * (A @ Z)
        if look is None:
            return ahead
        a, b_, deg = look
        w = math.sin(math.pi * min(1.0, max(0.0, (t - a) / (b_ - a)))) if a < t < b_ else 0.0
        d = axis_matrix(Y, deg * w) @ (A @ Z)
        return R["bip01 head"][:3, 3] + 12.0 * d

    def stand_pose(self, t=0.0):
        at, h, _v = self.station()
        return self.standing(at, h, t)

    def staff_at_station(self, S):
        """The staff upright at the station: its foot on the ground by his right foot, a little out."""
        foot = S["bip01 r foot"][:3, 3]
        rt = self.right_of(S)
        base = np.array([foot[0], 0.0, foot[2]]) + 0.22 * rt + 0.14 * self.facing(S)
        return self.staff(base, unit(Y + 0.04 * rt))

    def station_grip(self, S):
        """How far up the staff his right palm holds it standing: at his chest, below the shoulder."""
        return float(S["bip01 r upperarm"][1, 3] - 0.42)

    def deployed_idle(self):
        times = self.times(DEPLOYED)
        b = Built("deployed", "Bombard_ranged_idle", times)
        poses, anim, scales = self.camel_borrow(mgc.B_IDLE, times, 0.0)
        fr0 = self.gun_frames({})
        S0 = self.stand_pose()
        W = self.staff_at_station(S0)
        g = self.station_grip(S0)
        _at, _h, vent = self.station()
        for t, P in zip(times, poses):
            u = t / DEPLOYED
            R = self.stand_pose(u * self.stand_anim.duration)
            R = self.plant(R, {s: S0[f"bip01 {s} foot"] for s in ("l", "r")})
            R = self.hands(R, {"r": self.grip_on(R, W, g, "r"), "l": self.hang_hand(R, "l")}, b, False)
            down = self.downrange(P, fr0)
            w = math.sin(math.pi * min(1.0, max(0.0, (t - 0.8) / 0.6))) if 0.8 < t < 1.4 else 0.0
            look = lerp(down, point(W, (0.0, self.L, 0.0)), w)
            R = self.look(R, look, max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr0, linstock=self.staff_design(P, W)))
            b.rider.append(R)
        b.grips.append(("right palm on the staff", "r", 0.0, DEPLOYED))
        b.camel_src = (anim, scales)
        return b

    def downrange(self, P, fr):
        C = self.C(P)
        m = point(C, fr["muzzle"][:3, 3])
        d = unit(C[:3, :3] @ (fr["muzzle"][:3, :3] @ Z))
        return m + 12.0 * d

    def fire(self):
        times = self.times(FIRE)
        b = Built("fire", "Bombard_ranged_attack", times)
        P = self.lie()
        poses = [P] * len(times)
        S0 = self.stand_pose()
        W0 = self.staff_at_station(S0)
        g_r = self.station_grip(S0)
        _at, _h, vent = self.station()
        fr0 = self.gun_frames({})
        hip = S0["bip01 r thigh"][:3, 3]
        rt, f = self.right_of(S0), self.facing(S0)
        # the staff's tip on the vent, its foot back past his right hip
        tail = hip + 0.25 * rt - 0.45 * f - 0.05 * Y
        ax = unit(vent - tail)
        W_touch = self.staff(vent - (self.L - 0.01) * ax, ax)
        W_near = self.staff(vent + 0.10 * Y - (self.L - 0.01) * ax + 0.06 * f, ax)
        # back up after the shot: upright again, held out in front of him, before its foot goes down
        up = self.staff(W0[:3, 3] + 0.10 * Y + 0.22 * f, W0[:3, 1])
        g_l = self.left_grip(S0, [W0, self.staff_mix(W0, W_near, 0.5), W_near, W_touch, up], g_r)
        for t, _P in zip(times, poses):
            # the staff: upright -> over the vent (0.0-0.5) -> on it (0.5-0.9) -> held (0.9-0.95) -> back
            # up (0.92-1.40) -> its foot down (1.40-1.80)
            if t <= 0.50:
                W = self.staff_mix(W0, W_near, span(t, 0.0, 0.50))
                W[:3, 3] += np.array([0.0, 0.10 * span(t, 0.0, 0.10), 0.0]) * (1.0 - span(t, 0.0, 0.5))
            elif t <= 0.95:
                W = self.staff_mix(W_near, W_touch, span(t, 0.50, 0.80))
            elif t <= 1.40:
                W = self.staff_mix(W_touch, up, span(t, 0.92, 1.40))
            else:
                W = self.staff_mix(up, W0, span(t, 1.40, 1.80))
            kick = 6.0 * (span(t, SHOT, 1.00) - span(t, 1.00, 1.50))
            fr = self.gun_frames({"pitch": -kick})
            R = self.stand_pose(0.0)
            R = self.fwd_lean(R, -5.0 * span(t, 0.0, 0.5) * (1.0 - span(t, 1.4, 2.0)))
            R = self.plant(R, {s: S0[f"bip01 {s} foot"] for s in ("l", "r")})
            wl = span(t, 0.0, 0.35) * (1.0 - span(t, 1.60, 2.00))
            left = self.blend_goal(self.hang_hand(R, "l"), self.grip_on(R, W, g_l, "l"), wl,
                                   arc=0.22 * self.facing(R))
            R = self.hands(R, {"r": self.grip_on(R, W, g_r, "r"), "l": left}, b, False)
            away = math.sin(math.pi * min(1.0, max(0.0, (t - 0.92) / 0.48))) if 0.92 < t < 1.40 else 0.0
            look = vent if t < 1.40 else self.downrange(P, fr)
            if away > 0:
                h = R["bip01 head"][:3, 3]
                look = h + axis_matrix(Y, -45.0 * away) @ (look - h)
            R = self.look(R, look, max_yaw=60.0, max_pitch=35.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=self.staff_design(P, W)))
            b.rider.append(R)
        b.grips += [("right palm on the staff", "r", 0.0, FIRE), ("left palm on the staff", "l", 0.35, 1.60)]
        cam = self.camel
        anim = cam.anim(mgc.B_IDLE)
        b.camel_src = (anim, cam.hang_scale(P, cam.borrowed_scales(anim)))
        b.flash = [SHOT]
        return b

    def reload(self):
        times = self.times(RELOAD)
        b = Built("reload", "Bombard_reload", times)
        P = self.lie()
        S0 = self.stand_pose()
        W0 = self.staff_at_station(S0)
        g_r = self.station_grip(S0)
        fr = self.gun_frames({})
        head = S0["bip01 head"][:3, 3]
        rt, f = self.right_of(S0), self.facing(S0)
        tip = head + 0.30 * f + 0.05 * Y + 0.05 * rt
        tail = S0["bip01 r thigh"][:3, 3] + 0.35 * rt - 0.30 * f - 0.25 * Y
        ax = unit(tip - tail)
        W_face = self.staff(tip - self.L * ax, ax)
        g_l = self.left_grip(S0, [W0, self.staff_mix(W0, W_face, 0.5), W_face], g_r)
        for t in times:
            if t <= 0.60:
                W = self.staff_mix(W0, W_face, span(t, 0.05, 0.60))
            elif t <= 1.40:
                W = W_face
            else:
                W = self.staff_mix(W_face, W0, span(t, 1.40, 1.90))
            R = self.stand_pose(0.0)
            # two small pushes of the head and chest toward the match (he blows on it at 1.0 and 1.3)
            push = math.exp(-((t - 1.0) / 0.06) ** 2) + math.exp(-((t - 1.3) / 0.06) ** 2)
            R = self.fwd_lean(R, 3.0 * push)
            R = self.plant(R, {s: S0[f"bip01 {s} foot"] for s in ("l", "r")})
            wl = span(t, 0.0, 0.35) * (1.0 - span(t, 1.60, 2.00))
            left = self.blend_goal(self.hang_hand(R, "l"), self.grip_on(R, W, g_l, "l"), wl,
                                   arc=0.22 * self.facing(R))
            R = self.hands(R, {"r": self.grip_on(R, W, g_r, "r"), "l": left}, b, False)
            match = point(W, (0.0, self.L, 0.0))
            if 0.60 <= t < 1.40:
                R = self.look(R, match, max_pitch=30.0)
            elif t < 2.0:
                R = self.look(R, match, max_pitch=30.0)
            else:
                R = self.look(R, self.downrange(P, fr), max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=self.staff_design(P, W)))
            b.rider.append(R)
        b.grips += [("right palm on the staff", "r", 0.0, RELOAD), ("left palm on the staff", "l", 0.35, 1.60)]
        cam = self.camel
        anim = cam.anim(mgc.B_IDLE)
        b.camel_src = (anim, cam.hang_scale(P, cam.borrowed_scales(anim)))
        return b

    # getting off and on

    def climb_keys(self, P):
        """Getting off the lying camel to its left, the right leg back over the rump, as (share,
        pose) keys from seated (0) to standing beside the saddle facing it (1); his hands are set by
        the clip (the left holds the staff out, the right on the saddle behind his hip)."""
        ck = getattr(self, "_ck", None)
        if ck is not None and ck[0] is P:
            return ck[1]
        keys = self._climb_keys(P)
        self._ck = (P, keys)
        return keys

    def _climb_keys(self, P):
        from aoe3game.gr2_pose import rotate_about, translate
        rider, rig = self.rider, self.rider.rig
        root = rig.names[0].lower()
        attach = rigid(P[self.camel.rider_bone])
        A = attach[:3, :3]
        fwd, up, right = A @ Z, A @ Y, A @ X
        left = -right
        seat_at = attach[:3, 3]
        k0 = self.seated(P)
        k1 = translate(self.seated(P), rig, root, 0.06 * up + 0.04 * left)
        k1 = self.fwd_lean(k1, 15.0)
        # the right thigh lifted backward (its knee goes back) and swung toward the left over the rump
        k2 = translate(self.seated(P), rig, root, 0.12 * up + 0.16 * left)
        k2 = self.fwd_lean(k2, 25.0)
        knee0 = k2["bip01 r calf"][:3, 3].copy()
        for sign in (1.0, -1.0):
            T = rotate_about(k2, rig, "bip01 r thigh", "bip01 r thigh", left, sign * 60.0)
            if (T["bip01 r calf"][:3, 3] - knee0) @ fwd < 0:
                break
        k2 = rotate_about(T, rig, "bip01 r thigh", "bip01 r thigh", fwd, 0.0)
        k2b = translate(k2, rig, root, 0.06 * left)
        S = self.standing(np.zeros(3), math.degrees(math.atan2(right[0], right[2])))
        cur = S[root][:3, 3]
        k3 = translate(S, rig, root, seat_at + 0.40 * left - 0.55 * up - 0.10 * fwd - cur)
        k4 = translate(S, rig, root, np.array([seat_at[0] - 0.72 - cur[0], 0.0, seat_at[2] - 0.12 - cur[2]]))
        # the turn to face the camel (k2b to k3) takes the longest share: his hand on the saddle has let go
        keys = [(0.0, k0), (0.12, k1), (0.30, k2), (0.42, k2b), (0.80, k3), (1.0, k4)]
        return [(s_, self.above_ground(k_)) for s_, k_ in keys]

    def above_ground(self, R):
        from aoe3game.gr2_pose import translate
        low = min(float(R[b][1, 3]) for b in R if b.endswith(" foot") or b.endswith(" toe0"))
        S = self.stand_pose()
        sole = min(float(S[b][1, 3]) for b in S if b.endswith(" foot") or b.endswith(" toe0"))
        if sole - low > 1e-4:
            return translate(R, self.rider.rig, self.rider.rig.names[0].lower(), np.array([0.0, sole - low, 0.0]))
        return R

    def climb(self, keys, share):
        from aoe3game.gr2_pose import blend
        share = min(max(share, 0.0), 1.0)
        i = min(max(j for j, (k, _p) in enumerate(keys) if k <= share + 1e-9), len(keys) - 2)
        (s0, p0), (s1, p1) = keys[i], keys[i + 1]
        return blend(self.rider.rig, p0, p1, ease((share - s0) / (s1 - s0)))

    def saddle_palm(self, P, R=None):
        """His right palm flat on the saddle as he gets off or on: one fixed point at its right rear,
        behind his right hip (he pushes on it as his right leg swings over the rump), the palm down."""
        attach = rigid(P[self.camel.rider_bone])
        A = attach[:3, :3]
        p = attach[:3, 3] + A @ np.array([0.10, 0.04, -0.14])
        # the fingers point the way his arm reaches to it (level), so the wrist stays in reach; as he
        # swings round, the hand turns with him at most HAND_TURN degrees a second
        want = A @ np.array([0.0, 0.0, -1.0])
        if R is not None:
            d = p - R["bip01 r upperarm"][:3, 3]
            d[1] = 0.0
            if np.linalg.norm(d) > 0.05:
                want = unit(d)
        fin = getattr(self, "_saddle_fin", None)
        if fin is None:
            fin = want
        else:
            step = self.HAND_TURN / FPS
            ang = math.degrees(math.acos(max(-1.0, min(1.0, float(fin @ want)))))
            fin = want if ang <= step else vslerp(fin, want, step / ang)
        self._saddle_fin = fin
        return p, fin, A @ np.array([0.0, -1.0, 0.0])

    HAND_TURN = 300.0

    def _carry(self, R, g):
        """The staff upright in his right hand at his side as he walks, its grip `g` up from its foot."""
        p = R["bip01 r upperarm"][:3, 3] - 0.32 * Y + 0.12 * self.right_of(R) + 0.10 * self.facing(R)
        return self.staff(p - g * Y - STAFF_R * self.right_of(R), Y, side=self.facing(R))

    def transition(self, mount):
        """Bombard_unlimber (mount False) or Bombard_limber (mount True), as the script times them."""
        length = LIMBER_T if mount else UNLIMBER
        times = self.times(length)
        b = Built("limber" if mount else "unlimber", "Bombard_limber" if mount else "Bombard_unlimber", times)
        cam = self.camel
        if mount:
            poses, anim, scales = self.camel_borrow(mgc.B_UP, times, 3.0)
        else:
            poses, anim, scales = self.camel_borrow(mgc.B_DOWN, times, 0.0)
        P_lie = poses[-1] if not mount else poses[0]
        keys = self.climb_keys(P_lie)
        S_beside = keys[-1][1]
        S0 = self.stand_pose()
        W_station = self.staff_at_station(S0)
        g_st = self.station_grip(S0)
        for t, P in zip(times, poses):
            fr = self.gun_frames(self.beat_state(t, mount))
            ring = self.ring(P)
            R, goals, W = self.transition_pose(t, mount, P, P_lie, fr, keys, S_beside, S0, W_station, g_st, ring, b)
            R = self.hands(R, goals, b, seated=self._seated_now(t, mount))
            R = self.look(R, self._look_now(t, mount, R, P, fr, W), max_yaw=45.0, max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=self.staff_design(P, W)))
            b.rider.append(R)
        b.grips += self._transition_grips(mount)
        b.camel_src = (anim, scales)
        return b

    # The unlimber's beats (z-script-v1): 0-3.33 lying down, reins; 3.33-3.53 right hand to the ring,
    # 3.53-3.83 lifts it 0.35; 3.83-3.93 left hand to the cascabel, 3.93-4.38 the swing, 4.43 lets go;
    # 4.43-4.73 the staff passed right to left (both hands 4.53-4.63); 4.73-5.43 getting off; 5.43-5.73
    # back to the right hand (both 5.53-5.63); 5.73-6.33 two steps to the station, foot down at 6.33.
    # The limber (5.17 s): 0-0.50 two steps back to the saddle (the staff's foot up at 0.0-0.1);
    # 0.50-0.80 right to left (both 0.60-0.70); 0.80-1.60 getting on; 1.60-1.90 left to right (both
    # 1.70-1.80); 1.90-2.40 the swing back (2.00-2.35); 2.40-2.90 into the ring (2.55-2.80);
    # 2.90-3.00 reins; 3.00-5.17 the camel rises.

    def beat_state(self, t, mount):
        lim = self.limber
        if mount:
            w = span(t, 2.08, 2.40)
        else:
            w = 1.0 - span(t, 3.93, 4.38)
        return {"pitch": lim["pitch"] * w, "yaw": lim["yaw"] * w}

    def _seated_now(self, t, mount):
        return t >= 1.30 if mount else t < 4.90

    def _look_now(self, t, mount, R, P, fr, W):
        A = rigid(P[self.camel.rider_bone])[:3, :3]
        ahead = R["bip01 head"][:3, 3] + 12.0 * (A @ Z)
        if not mount:
            if 3.33 <= t < 3.83:
                return point(W, (0.0, 0.3, 0.0))
            if 3.83 <= t < 4.43:
                return self.cascabel(P, fr)[0]
            if 4.73 <= t < 5.13:          # where he gets down, on his left
                return R["bip01 head"][:3, 3] + 2.0 * (-(A @ X)) + 1.0 * (A @ Z) - 2.0 * Y
            if 5.13 <= t < 5.73:          # turned to the camel: the saddle
                return rigid(P[self.camel.rider_bone])[:3, 3]
            if t >= 5.73:
                return self.station()[2]
            return ahead
        if t < 0.80:
            return R["bip01 head"][:3, 3] + 6.0 * (A @ Z)
        if t < 1.30:                      # getting on: the saddle
            return rigid(P[self.camel.rider_bone])[:3, 3]
        if 1.90 <= t < 2.40:
            return self.cascabel(P, fr)[0]
        if 2.40 <= t < 2.90:
            return point(self.ring(P), (0.0, 0.3, 0.0))
        return ahead

    def _transition_grips(self, mount):
        if not mount:
            return [("right palm on the staff (drawn, held)", "r", 3.53, 4.63),
                    ("left palm on the staff (passed, getting off)", "l", 4.53, 5.68),
                    ("right palm on the staff (to the station)", "r", 5.66, 6.13)]
        return [("right palm on the staff (back to the saddle)", "r", 0.10, 0.70),
                ("left palm on the staff (getting on)", "l", 0.62, 1.90),
                ("right palm on the staff (into the ring)", "r", 1.90, 2.80)]

    def transition_pose(self, t, mount, P, P_lie, fr, keys, S_beside, S0, W_station, g_st, ring, b):
        """(rider pose, hand goals, staff world frame) at t of the unlimber or the limber."""
        if not mount:
            return self._unlimber_pose(t, P, fr, keys, S_beside, S0, W_station, g_st, ring)
        return self._limber_pose(t, P, fr, keys, S_beside, S0, W_station, g_st, ring)

    def _ring_grip(self, P, ring):
        """How far up the staff in its ring his right palm closes on it (by his right hip)."""
        R = self.seated(P)
        hip = R["bip01 pelvis"][:3, 3]
        return float((hip[1] + 0.30) - ring[1, 3]) / max(ring[1, 1], 0.5)

    def _held_seated(self, R, P, ring, g):
        """The staff drawn 0.35 up out of its ring, held in the right hand (seated)."""
        return self.staff(ring[:3, 3] + 0.35 * ring[:3, 1], ring[:3, 1])

    def _front(self, R, g_hold, standing=False):
        """The staff upright in front of his chest (both hands on it): its palm point there."""
        # seated, well out in front (over the cannon's breech); standing beside the camel, nearer,
        # so the staff stays clear of the camel's flank
        # seated, the cannon's breech is right in front of him: the staff passes to his right of it
        ahead, up, side = (0.26, -0.05, 0.0) if standing else (0.22, 0.10, 0.14)
        c = R["bip01 spine1"][:3, 3] + ahead * self.facing(R) + up * Y + side * self.right_of(R)
        return self.staff(c - g_hold * Y, Y, side=self.facing(R))

    def _out_left(self, R, g_hold):
        """The staff upright in his left hand held out from the camel's flank."""
        rt, f = self.right_of(R), self.facing(R)
        p = R["bip01 l upperarm"][:3, 3] - 0.30 * Y - 0.30 * rt + 0.05 * f
        return self.staff(p - g_hold * Y, Y, side=f)

    def _unlimber_pose(self, t, P, fr, keys, S_beside, S0, W_station, g_st, ring):
        g_ring = self._ring_grip(P, ring)
        seat = self.seated(P)
        lean = (-15.0 * span(t, 0.3, 1.6) + 25.0 * span(t, 1.6, 3.0) - 10.0 * span(t, 3.0, 3.33)) if t < 3.33 else 0.0
        if t < 4.73:
            R = self.fwd_lean(seat, lean)
        elif t < 5.43:
            R = self.climb(keys, (t - 4.73) / 0.70)
        elif t < 5.73:
            R = S_beside
        else:
            R = self.walk(S_beside, S0, (t - 5.73) / 0.60, "l")
            R = self.plant(R, {s: R[f"bip01 {s} foot"] for s in ("l", "r")})
        # the staff
        drawn = self.staff(ring[:3, 3] + 0.35 * ring[:3, 1] * span(t, 3.53, 3.83), ring[:3, 1])
        g_hold = g_ring
        if t < 4.43:
            W = drawn if t >= 3.53 else ring
        elif t < 4.73:
            front = self._front(R, g_hold)
            W = self.staff_mix(drawn, front, span(t, 4.43, 4.58))
            W = self.staff_mix(W, self._out_left(R, g_hold), span(t, 4.63, 4.90), arc=0.22 * self.facing(R))
        elif t < 5.43:
            W = self.staff_mix(self._front(R, g_hold), self._out_left(R, g_hold), span(t, 4.63, 4.90),
                               arc=0.22 * self.facing(R))
        else:
            front = self._front(R, g_hold, standing=True)
            out = self._out_left(R, g_hold)
            if t < 5.68:
                W = self.staff_mix(out, front, span(t, 5.43, 5.68))
            elif t < 6.13:
                W = self.staff_mix(front, self._carry(R, g_hold), span(t, 5.68, 5.95), arc=0.12 * self.facing(R))
            else:
                # at the station he lets the staff slide down through his hand onto the ground
                W = self.staff_mix(self._carry(R, g_hold), W_station, span(t, 6.13, 6.33))
        # the hands
        reins_r, reins_l = self.reins(R, P, "r"), self.reins(R, P, "l")
        goals = {}
        if t < 3.33:
            goals = {"r": reins_r, "l": reins_l}
        elif t < 4.43:
            grip_r = self.grip_on(R, W, g_hold, "r")
            goals["r"] = self.blend_goal(reins_r, grip_r, span(t, 3.33, 3.53), 0.05)
            casc = self.cascabel(P, fr)
            goals["l"] = self.blend_goal(reins_l, casc, span(t, 3.83, 3.93), 0.04)
        elif t < 4.73:
            goals["r"] = self.grip_on(R, W, g_hold, "r") if t < 4.63 else self.blend_goal(
                self.grip_on(R, W, g_hold, "r"), self.saddle_palm(P, R), span(t, 4.63, 4.83))
            goals["l"] = self.blend_goal(self.cascabel(P, fr), self.grip_on(R, W, g_hold + 0.12, "l"),
                                         span(t, 4.43, 4.53), 0.04)
        elif t < 5.43:
            goals["r"] = self.blend_goal(self.grip_on(R, W, g_hold, "r"), self.saddle_palm(P, R), span(t, 4.63, 4.83)) \
                if t < 4.83 else self.saddle_palm(P, R) if t < 5.02 else self.blend_goal(
                self.saddle_palm(P, R), self.hang_hand(R, "r"), span(t, 5.02, 5.50))
            goals["l"] = self.grip_on(R, W, g_hold + 0.12, "l")
        else:
            g_new = g_hold + (g_st - g_hold) * span(t, 6.13, 6.33)
            goals["r"] = self.blend_goal(self.hang_hand(R, "r"), self.grip_on(R, W, g_hold, "r"),
                                         span(t, 5.43, 5.66), arc=0.15 * self.facing(R)) if t < 5.66 else self.grip_on(R, W, g_new, "r", lock=g_hold)
            let_go = self.grip_on(R, self._front(R, g_hold, standing=True), g_hold + 0.12, "l")
            goals["l"] = self.grip_on(R, W, g_hold + 0.12, "l") if t < 5.68 else self.blend_goal(
                let_go, self.hang_hand(R, "l"), span(t, 5.68, 5.95), arc=0.15 * self.facing(R))
        return R, goals, W

    def _limber_pose(self, t, P, fr, keys, S_beside, S0, W_station, g_st, ring):
        g_ring = self._ring_grip(P, ring)
        g_hold = g_ring
        seat = self.seated(P)
        if t < 0.50:
            R = self.walk(S0, S_beside, t / 0.50, "r")
            R = self.plant(R, {s: R[f"bip01 {s} foot"] for s in ("l", "r")})
        elif t < 0.80:
            R = S_beside
        elif t < 1.60:
            R = self.climb(keys, 1.0 - (t - 0.80) / 0.80)
        else:
            lean = (15.0 * span(t, 3.0, 4.1) - 25.0 * span(t, 4.1, 5.0) + 10.0 * span(t, 5.0, 5.17)) if t >= 3.0 else 0.0
            R = self.fwd_lean(seat, lean)
        # the staff
        drawn = self.staff(ring[:3, 3] + 0.35 * ring[:3, 1] * (1.0 - span(t, 2.55, 2.80)), ring[:3, 1])
        if t < 0.50:
            # the staff slides up through his hand off the ground (0.0-0.10), then he carries it
            W = self.staff_mix(W_station, self._carry(R, g_hold), span(t, 0.0, 0.10))
        elif t < 0.80:
            W = self.staff_mix(self._carry(R, g_hold), self._front(R, g_hold, standing=True), span(t, 0.50, 0.65),
                               arc=0.12 * self.facing(R))
            W = self.staff_mix(W, self._out_left(R, g_hold), span(t, 0.68, 0.88), arc=0.10 * self.facing(R))
        elif t < 1.60:
            W = self.staff_mix(self._front(R, g_hold, standing=True), self._out_left(R, g_hold), span(t, 0.68, 0.88),
                               arc=0.10 * self.facing(R))
        elif t < 2.40:
            W = self.staff_mix(self._out_left(R, g_hold), self._front(R, g_hold), span(t, 1.60, 1.75),
                               arc=0.12 * self.facing(R))
            W = self.staff_mix(W, drawn, span(t, 1.90, 2.12)) if t >= 1.90 else W
        else:
            W = drawn
        reins_r, reins_l = self.reins(R, P, "r"), self.reins(R, P, "l")
        goals = {}
        if t < 0.70:
            g = g_st + (g_hold - g_st) * span(t, 0.0, 0.10)
            goals["r"] = self.grip_on(R, W, g, "r", lock=g_hold)
            goals["l"] = self.blend_goal(self.hang_hand(R, "l"), self.grip_on(R, W, g_hold + 0.12, "l"),
                                         span(t, 0.48, 0.62), arc=0.15 * self.facing(R))
        elif t < 1.90:
            # the left holds the staff out while he gets on; the right goes to the saddle (0.70-0.80),
            # stays there and, seated, comes to the staff in front of his chest (1.60-1.75)
            goals["l"] = self.grip_on(R, W, g_hold + 0.12, "l")
            let_go = self.grip_on(R, self._front(R, g_hold, standing=True), g_hold, "r")
            goals["r"] = self.blend_goal(let_go, self.saddle_palm(P, R), span(t, 0.70, 1.25), arc=0.10 * self.facing(R)) \
                if t < 1.45 else self.blend_goal(self.saddle_palm(P, R), self.grip_on(R, W, g_hold, "r"), span(t, 1.45, 1.90),
                                                 arc=0.15 * self.right_of(R) + 0.12 * self.facing(R) + 0.05 * Y)
        elif t < 2.90:
            goals["r"] = self.grip_on(R, W, g_hold, "r") if t < 2.80 else self.blend_goal(
                self.grip_on(R, W, g_hold, "r"), reins_r, span(t, 2.80, 2.95))
            casc = self.cascabel(P, fr)
            let_go = self.grip_on(R, self._front(R, g_hold), g_hold + 0.12, "l")
            goals["l"] = (let_go if t < 1.90 else self.blend_goal(let_go, casc, span(t, 1.90, 2.08), 0.04)) \
                if t < 2.40 else self.blend_goal(casc, reins_l, span(t, 2.40, 2.55))
        else:
            goals = {"r": self.blend_goal(self.grip_on(R, W, g_hold, "r"), reins_r, span(t, 2.80, 2.95)) if t < 2.95
                     else reins_r, "l": reins_l}
        return R, goals, W

    def death_b(self):
        times = self.times(DEATH_B)
        b = Built("death", "Bombard_death", times)
        cam = self.camel
        still = self.lie()
        # the gun stays on the rolling camel (the rider's bone kept on its chest): the artillerist's own
        # clip places him on the ground whatever that bone does
        poses = [cam.fix_hang(cam.roll_over(still, float(t))) for t in times]
        anim = cam.anim(mgc.B_IDLE)
        scales = cam.hang_scale(poses[0], cam.borrowed_scales(anim))
        at, h, _v = self.station()
        S0 = self.stand_pose()
        W0 = self.staff_at_station(S0)
        g = self.station_grip(S0)
        fr = self.gun_frames({})
        dies = self.rider.anim(self.r.get("foot_death", mgc.FOOT_DEATH))
        R0 = self.rider.standing(self.foot, dies, 0.0, h, at)
        # the staff in his right hand as the death's first frame holds it (its grip at his palm,
        # upright), carried by that hand until he lets go at 0.35; then it tips over outward (away
        # from the camel) about its foot onto the ground
        palm0 = self.rider.palm_of(R0, "r")
        W_hand0 = self.staff(np.array([palm0[0], 0.0, palm0[2]]) + STAFF_R * self.right_of(R0), Y,
                             side=self.facing(R0))
        out = unit(-self.right_of(S0) - 0.3 * self.facing(S0))
        released = None
        for t, P in zip(times, poses):
            R = self.rider.standing(self.foot, dies, min(float(t), dies.duration), h, at)
            if t < RELEASE:
                # carried by his hand, upright (the hand's turns are not passed to the long staff)
                palm = self.rider.palm_of(R, "r")
                foot = palm - (palm0 - W_hand0[:3, 3])
                foot[1] = max(0.0, foot[1])          # as he drops, its foot stays on the ground
                W = self.staff(foot, W_hand0[:3, 1], side=W_hand0[:3, 2])
                released = W
            else:
                foot = released[:3, 3].copy()
                foot[1] = max(STAFF_R, foot[1] - 0.6 * (t - RELEASE))     # its foot comes down to the ground
                lying = self.staff(np.array([foot[0], STAFF_R, foot[2]]), out)
                w = min(1.0, (t - RELEASE) / 0.40) ** 1.3               # it falls as he does, faster as it goes
                W = self.staff_mix(self.staff(foot, released[:3, 1], side=released[:3, 2]), lying, w)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=self.staff_design(P, W)))
            b.rider.append(R)
        b.camel_src = (anim, scales)
        b.death = True
        return b

    def cheer(self, name, camel_rel, rel):
        """Today's rider cheer (his clip unchanged) on a camel idle played over the cheer's length."""
        cam = self.camel
        anim = self.rider.anim(rel)
        times = self.times(anim.duration)
        b = Built(name, "Cheer", times)
        canim = cam.anim(camel_rel)
        k = canim.duration / anim.duration
        poses = [cam.fix_hang(cam.pose(canim, float(t) * k)) for t in times]
        fr = self.gun_frames(self.limber)
        b.camel, b.head_bend = self.keep_head_clear(poses, times, fr)
        b.gun = [dict(fr, linstock=self.d.linstock_rest())] * len(times)
        b.rider = [self.rider.seated(anim, float(t), rigid(P[cam.rider_bone]), square=False)
                   for t, P in zip(times, b.camel)]
        b.rider, b.chest_back = self.keep_chest_clear(b.rider, b.camel, fr)
        b.rider, b.arm_moved = self.keep_arms_clear(b.rider, b.camel, fr)
        moved = b.arm_moved or b.chest_back
        b.camel_src = (canim, cam.hang_scale(b.camel[0], cam._scales[id(canim)]))
        b.stock_rider = None if moved else rel     # moved: written as a clip of ours
        return b

    def rider_gap(self, R, P, fr):
        """The least gap between the rider's mesh and the barrel (game units)."""
        if getattr(self, "_rfig", None) is None:
            self._rfig = mgc.Figure(self.game, self.rider.data)
        d = self.d
        to_w = self.C(P) @ fr["cannon"] @ tr(-d.trunnion)
        a, b_ = point(to_w, d.bpoint(self.src.breech)), point(to_w, d.bpoint(self.src.muzzle))
        pts = np.concatenate([it[0] for it in self._rfig.items(R)])
        ab = b_ - a
        u = np.clip(((pts - a) @ ab) / (ab @ ab), 0.0, 1.0)
        return float((np.linalg.norm(pts - (a + u[:, None] * ab), axis=1) - d.radius / d.bind_scale).min())

    CHEST_CLEAR = 0.02

    def lean_chest(self, R, deg):
        """The chest (spine1 up: arms and head with it, not the legs) leaned back by `deg`."""
        if not deg:
            return R
        if getattr(self, "_chest_sign", None) is None:
            h0 = R["bip01 head"][:3, 3]
            T = self.rider.turn(R, "bip01 spine1", self.side_axis(R), 10.0)
            self._chest_sign = -1.0 if (T["bip01 head"][:3, 3] - h0) @ self.facing(R) > 0 else 1.0
        return self.rider.turn(R, "bip01 spine1", self.side_axis(R), self._chest_sign * deg)

    def keep_chest_clear(self, poses, camel, fr):
        """Where today's cheer leans his chest or shoulder into the cannon's breech: the chest leaned
        back just enough (the script's rule for a cheer that meets the cannon), eased in and out
        over half a second. (poses, the largest lean in degrees)."""
        # the breech of pose B is at his left front: the chest turns right (its left shoulder back)
        # and leans back a little, the least of the two that clears it
        need = np.zeros((len(poses), 2))
        tries = sorted(((lean, turn) for lean in range(0, 25, 4) for turn in range(0, 41, 5) if lean or turn),
                       key=lambda x: x[0] + x[1])
        for i, (R, P) in enumerate(zip(poses, camel)):
            if self.rider_gap(R, P, fr) >= self.CHEST_CLEAR:
                continue
            best = tries[-1]
            for lean, turn in tries:
                if self.rider_gap(self.turn_chest(self.lean_chest(R, lean), turn), P, fr) >= self.CHEST_CLEAR:
                    best = (lean, turn)
                    break
            need[i] = best
        if not need.any():
            return poses, 0.0
        half = int(round(0.5 * FPS))
        kernel = np.array([ease((k + 1) / (half + 1)) for k in range(half)] + [1.0] +
                          [ease((half - k) / (half + 1)) for k in range(half)])
        amt = np.array([np.max(need[max(0, i - half):i + half + 1] *
                               kernel[max(0, i - half) - i + half:min(len(need), i + half + 1) - i + half, None], axis=0)
                        for i in range(len(need))])
        return ([self.turn_chest(self.lean_chest(R, a[0]), a[1]) for R, a in zip(poses, amt)],
                float(amt.max()))

    def turn_chest(self, R, deg):
        """The chest turned to his right by `deg` about the vertical (its left shoulder goes back)."""
        if not deg:
            return R
        if getattr(self, "_turn_sign", None) is None:
            s0 = R["bip01 l upperarm"][:3, 3]
            T = self.rider.turn(R, "bip01 spine1", Y, 10.0)
            self._turn_sign = 1.0 if (T["bip01 l upperarm"][:3, 3] - s0) @ self.facing(R) < 0 else -1.0
        return self.rider.turn(R, "bip01 spine1", Y, self._turn_sign * deg)

    ARM_CLEAR = 0.13      # a palm's centre this far from the barrel's surface (the hand's own thickness)

    def keep_arms_clear(self, poses, camel, fr):
        """Where today's cheer swings a hand into the cannon's breech (the script's rule: the arm moved
        clear and said so): that palm moved straight out from the barrel just enough, eased in and out
        over half a second, the arm solved to it, the hand turned as it was. (poses, the largest move)."""
        d = self.d
        need = {s: np.zeros(len(poses)) for s in ("l", "r")}
        away = {s: [None] * len(poses) for s in ("l", "r")}
        rad = d.radius / d.bind_scale
        for i, (R, P) in enumerate(zip(poses, camel)):
            C = self.C(P)
            to_w = C @ fr["cannon"] @ tr(-d.trunnion)
            a, b_ = point(to_w, d.bpoint(self.src.breech)), point(to_w, d.bpoint(self.src.muzzle))
            ab = b_ - a
            for s in ("l", "r"):
                p = self.rider.palm_of(R, s)
                u = float(np.clip((p - a) @ ab / (ab @ ab), 0.0, 1.0))
                q = a + u * ab
                gap = float(np.linalg.norm(p - q)) - rad
                if gap < self.ARM_CLEAR:
                    need[s][i] = self.ARM_CLEAR - gap
                    away[s][i] = unit(p - q)
        if not any(v.any() for v in need.values()):
            return poses, 0.0
        half = int(round(0.5 * FPS))
        kernel = [ease((k + 1) / (half + 1)) for k in range(half)] + [1.0] + \
                 [ease((half - k) / (half + 1)) for k in range(half)]
        out, most = [], 0.0
        body = self.rider.body
        for i, (R, P) in enumerate(zip(poses, camel)):
            Q = R
            for s in ("l", "r"):
                lo, hi = max(0, i - half), min(len(poses), i + half + 1)
                cand = [(need[s][j] * kernel[j - i + half], away[s][j]) for j in range(lo, hi) if away[s][j] is not None]
                if not cand:
                    continue
                amount, direction = max(cand, key=lambda x: x[0])
                if amount <= 1e-4:
                    continue
                most = max(most, amount)
                hand = Q[f"bip01 {s} hand"][:3, :3]
                palm = self.rider.palm_of(Q, s) + amount * direction
                Q = self.rider.hand(Q, s, palm, unit(hand @ body.finger_local[s]), unit(hand @ body.normal_local[s]),
                                    self.poles(Q, True)[s])
            out.append(Q)
        return out, most

    def build_all(self):
        """Round 2 (script v2, approved 2026-11-26): the limbered clips as before, the unlimbered unit
        as the gatling camel's round 6 (V2)."""
        out = self.build_v1_limbered()
        v2 = V2(self)
        out["unlimber"] = v2.unlimber()
        out["limber"] = v2.limber()
        out["deployed"] = v2.deployed()
        out["fire"] = v2.fire()
        out["reload"] = v2.reload()
        out["death"] = v2.death()
        return out

    def build_v1_limbered(self):
        out = {}
        for name, anim_name, rel, _r, gait, reins_only in LIMBERED:
            look = {"idle": (1.5, 3.0, 25.0), "bored_b": (1.0, 3.0, -35.0)}.get(name)
            out[name] = self.limbered(name, anim_name, rel, gait, reins_only, look)
        for name, camel_rel, rel in CHEERS:
            out[name] = self.cheer(name, camel_rel, rel)
        return out

    def build_all_v1(self):
        out = {}
        for name, anim_name, rel, _r, gait, reins_only in LIMBERED:
            look = {"idle": (1.5, 3.0, 25.0), "bored_b": (1.0, 3.0, -35.0)}.get(name)
            out[name] = self.limbered(name, anim_name, rel, gait, reins_only, look)
        for name, camel_rel, rel in CHEERS:
            out[name] = self.cheer(name, camel_rel, rel)
        out["unlimber"] = self.transition(False)
        out["limber"] = self.transition(True)
        out["deployed"] = self.deployed_idle()
        out["fire"] = self.fire()
        out["reload"] = self.reload()
        out["death"] = self.death_b()
        return out

    # -- the files

    def gun_yaw(self, fr):
        """The gun's yaw (degrees, toward the unit's right +) in a frame set, from its yaw bone."""
        rest = self.d.rest()["yaw"][:3, :3]
        z = (rest.T @ fr["yaw"][:3, :3]) @ Z
        a = math.degrees(math.atan2(z[0], z[2]))
        return a if (axis_matrix(Y, a) @ Z) @ z > 0.999 else -a

    def write(self, b):
        cam, d = self.camel, self.d
        name = self.r["name"]
        tag = FILE_TAGS.get(b.name, b.name)
        if b.name in UNLIMBERED:
            # the camel's bone_turret (the launch point and the muzzle flash on it) turned with the gun:
            # turretArc turns it by the aim less the rest yaw, so the clips show it where the gun is
            b.camel = [mgc.Unit.turret_turned(P, self.gun_yaw(fr)) for P, fr in zip(b.camel, b.gun)]
        if b.camel_name is None:
            b.camel_name = f"{name}_camel_{tag}"
            anim, scales = b.camel_src
            b.camel_bytes = cam.track_bytes(b.camel_name, b.times, b.camel, anim, scales)
        bones = d.BONES
        locs = []
        for fr in b.gun:
            # the match burns at the linstock's tip, wherever a clip put the linstock
            fr = dict(fr, match=fr["linstock"] @ tr((0.0, d.src.linstock_length * d.ls, 0.0)))
            worlds = {"root": np.eye(4)}
            for k in bones[1:]:
                worlds[k] = d.to_model(fr[k])
            loc = []
            for k in bones:
                par = d.PARENT[k]
                m = worlds[k] if par is None else np.linalg.inv(worlds[par]) @ worlds[k]
                loc.append(split(m))
            locs.append(loc)
        names = [f"bone_{self.gun_name}" if k == "root" else d.NAMES[k] for k in bones]
        tracks = [(nm, b.times, np.array([f[i][0] for f in locs]), np.array([f[i][1] for f in locs]))
                  for i, nm in enumerate(names)]
        like = self.rider.idle
        b.gun_name = f"{name}_gun_{tag}"
        b.gun_bytes = animation_file(b.gun_name, float(b.times[-1]), names[0], tracks, basis=self.rider.rig.basis,
                                     accumulation=like.accumulation, timestep=like.timestep, source=b.gun_name)
        if getattr(b, "stock_rider", None):
            b.rider_name = None                 # today's clip, unchanged
        else:
            b.rider_name = f"{name}_rider_{tag}"
            rl = [self.rider.to_local(R, rigid(P[cam.rider_bone])) for R, P in zip(b.rider, b.camel)]
            b.rider_bytes = self.rider.track_bytes(b.rider_name, b.times, rl, like)
        return b


def split(m):
    from aoe3game.gr2_anim import split as _split
    return _split(m)


def animation_file(*a, **k):
    from aoe3game.gr2_anim import animation_file as _af
    return _af(*a, **k)


# --------------------------------------------------------------------------------------------------
# The checks (tools/check_anim.py): the job of the new clips, today's clips as its baseline, and the
# deaths (the dead model) with theirs

BASELINE = [  # today's MEZamburak anim file: (clip, camel clip, rider clip)
    ("idle", Z_IDLE, mgc.ZAMB + "zamburak_rider_idle00"),
    ("walk", mgc.ZAMB + "zamburak_camel_walk00", mgc.ZAMB + "zamburak_rider_walk"),
    ("jog", mgc.ZAMB + "zamburak_camel_jog", mgc.LIB + "cavalry\\sword_jog"),
    ("run", mgc.LIB + "cavalry\\horse_gallop", mgc.LIB + "cavalry\\sword_gallop"),
    ("bored_a", mgc.ZAMB + "zamburak_camel_idle02", mgc.ZAMB + "zamburak_rider_idle01"),
    ("bored_b", mgc.ZAMB + "zamburak_camel_idle03", mgc.ZAMB + "zamburak_rider_idle00"),
    ("bored_c", mgc.ZAMB + "zamburak_camel_idle06", mgc.ZAMB + "zamburak_rider_idle01"),
    # today's file picks the camel's and the rider's cheer variants apart: paired here as the new clips pair them
    ("cheer_a", mgc.ZAMB + "zamburak_camel_idle02", mgc.LIB + "cavalry\\sword_cheer_F"),
    ("cheer_b", mgc.ZAMB + "zamburak_camel_idle03", mgc.LIB + "cavalry\\sword_cheer_H"),
    ("cheer_c", Z_IDLE, mgc.LIB + "cavalry\\sword_bored_A"),
    ("cheer_d", mgc.ZAMB + "zamburak_camel_idle06", mgc.LIB + "cavalry\\sword_cheer_E"),
    ("attack_ranged", mgc.ZAMB + "zamburak_camel_attackRanged01", mgc.ZAMB + "zamburak_rider_attackRanged00"),
    ("attack_ranged_reload", mgc.ZAMB + "zamburak_camel_reload", mgc.ZAMB + "zamburak_rider_reload"),
    ("attack_melee_a", mgc.ZAMB + "Zamburak_Melee_Attack_1", mgc.LIB + "cavalry\\sword_attack_A"),
    ("attack_melee_b", mgc.ZAMB + "Zamburak_Melee_Attack_2", mgc.LIB + "cavalry\\sword_attack_B"),
    ("attack_melee_c", mgc.ZAMB + "Zamburak_Melee_Attack_3", mgc.LIB + "cavalry\\sword_attack_C"),
    ("raze_idle_a", Z_IDLE, mgc.LIB + "cavalry\\raze_idle_A"),
    ("raze_idle_b", mgc.ZAMB + "zamburak_camel_idle02", mgc.LIB + "cavalry\\raze_idle_C"),
    ("raze_idle_c", mgc.ZAMB + "zamburak_camel_idle03", mgc.LIB + "cavalry\\raze_idle_D"),
    ("raze_idle_d", mgc.ZAMB + "zamburak_camel_idle06", mgc.LIB + "cavalry\\raze_idle_G"),
    ("raze_attack", mgc.ZAMB + "zamburak_camel_razeAttack00", "units\\asians\\indians\\sowar\\sowarRider_razeAttack00"),
]
SOWAR = "units\\asians\\indians\\sowar\\"
DEATHS = [  # the limbered deaths, as today's anim file plays them: (clip, camel clip, rider clip)
    ("death_melee_a", SOWAR + "sowarCamel_death00", mgc.LIB + "cavalry\\sword_deathA"),
    ("death_melee_b", SOWAR + "sowarCamel_death01", mgc.LIB + "cavalry\\sword_deathB"),
    ("death_melee_c", SOWAR + "sowarCamel_death02", mgc.LIB + "cavalry\\sword_deathC"),
    ("death_havoc_a", mgc.LIB + "cavalry\\horse_death_front", mgc.LIB + "cavalry\\rider_death_havoc_a"),
    ("death_havoc_b", mgc.LIB + "cavalry\\horse_death_behind", mgc.LIB + "cavalry\\rider_death_havoc_b"),
    ("death_havoc_c", mgc.LIB + "cavalry\\horse_death_left", mgc.LIB + "cavalry\\rider_death_havoc_a"),
    ("death_havoc_d", mgc.LIB + "cavalry\\horse_death_right", mgc.LIB + "cavalry\\rider_death_havoc_b"),
    ("death_havoc_e", mgc.LIB + "cavalry\\horse_death_run", mgc.LIB + "cavalry\\rider_death_havoc_a"),
]
# the limbered deaths that drive the cannon on the camel's back into the ground (check_anim, 2026-11-26:
# breech or muzzle 13-101 cm under it): not played by the limbered unit (script v3 delta)
DEATHS_DROPPED = {
    "death_melee_c": "REMOVED: the camel's death02 rolls it onto its back: the muzzle goes 25 cm into the ground",
    "death_havoc_a": "REMOVED: horse_death_front: the breech goes 101 cm and the muzzle 46 cm into the ground",
    "death_havoc_b": "REMOVED: horse_death_behind: the muzzle goes 39 cm into the ground",
    "death_havoc_c": "REMOVED: horse_death_left: the muzzle goes 30 cm into the ground",
    "death_havoc_e": "REMOVED: horse_death_run: the muzzle goes 13 cm into the ground",
}
DEATHS_KEPT = [d for d in DEATHS if d[0] not in DEATHS_DROPPED]
REMOVED = {
    "attack_ranged": "REMOVED: Attack_ranged from the saddle, because limbered cannot fire (the working plan; "
                     "JTMaston question 2)",
    "attack_ranged_reload": "REMOVED: Attack_ranged_reload from the saddle, because limbered cannot fire",
    "attack_melee_a": "REMOVED: Attack_melee, because MEZamburak's tactics have no hand attack (never played today)",
    "attack_melee_b": "REMOVED: Attack_melee, because MEZamburak's tactics have no hand attack (never played today)",
    "attack_melee_c": "REMOVED: Attack_melee, because MEZamburak's tactics have no hand attack (never played today)",
    "raze_idle_a": "REMOVED: Raze_idle, because MEZamburak's tactics have no building attack (never played today)",
    "raze_idle_b": "REMOVED: Raze_idle, because MEZamburak's tactics have no building attack (never played today)",
    "raze_idle_c": "REMOVED: Raze_idle, because MEZamburak's tactics have no building attack (never played today)",
    "raze_idle_d": "REMOVED: Raze_idle, because MEZamburak's tactics have no building attack (never played today)",
    "raze_attack": "REMOVED: Raze_attack, because MEZamburak's tactics have no building attack (never played today)",
    "walk:rider": "REMOVED: the stock rider walk (hips and shoulders sway), because his left hand stays on the cascabel; "
                  "replaced by the upright seat with a nod",
    "jog:rider": "REMOVED: the stock sword jog (hips and shoulders sway), because his left hand stays on the cascabel; "
                 "replaced by the upright seat with a nod",
    "run:rider": "REMOVED: the stock sword gallop (his legs swing with it), replaced by the upright seat with a nod and "
                 "both fists on the reins",
}
HOOVES = [{"name": "hoof front left", "bone": "HS Bone Hoof Frnt Lt"}, {"name": "hoof front right", "bone": "HS Bone Hoof Frnt Rt"},
          {"name": "hoof back left", "bone": "HS Bone Hoof Back Lt"}, {"name": "hoof back right", "bone": "HS Bone Hoof Back Rt"}]
LOOPS = ("idle", "walk", "jog", "run", "deployed")
MOVES = ("walk", "jog", "run")
AHEAD_MIN = -0.10         # a palm at most this far behind its shoulder (metres; the deaths aside)
# the unlimbered clips (the gun's bone_turret follows its yaw in them), and the names their files and
# animations take: turretArc keeps the gun at its rest while a clip whose name holds "deploy", "reload"
# or "death" plays, so the unlimber and the limber are named as a deploy and an undeploy
UNLIMBERED = ("unlimber", "limber", "deployed", "fire", "reload", "death")
FILE_TAGS = {"unlimber": "deploy", "limber": "undeploy"}


def write_checks(folder, check, game, unit, built, gun_path, camel_path, dead_path, recipe):
    """The three jobs (new clips, today's as the baseline, the deaths and theirs) and every file
    they read (the stock clips and models expanded), below `check`."""
    os.makedirs(check, exist_ok=True)
    stock = os.path.join(check, "stock")
    os.makedirs(stock, exist_ok=True)

    def expand(rel):
        dst = os.path.join(stock, rel.replace("\\", "_") + ".gr2")
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(game.granny(rel))
        return dst.replace("\\", "/")
    rider_model = expand(recipe["rider"]["model"])
    upm = gr2_mesh.read(unit.rider.data)["units_per_meter"]
    palm = {s: (np.asarray(unit.rider.body.palm_local[s]) / upm).tolist() for s in ("l", "r")}
    hand = {s: {"bone": f"rider:bip01 {s} hand", "offset": palm[s]} for s in ("l", "r")}
    staff_m = unit.L / gr2_mesh.read(unit.src.linstock_data)["units_per_meter"]
    actors = {"camel": {"model": camel_path, "rig": {"preset": "bare", "feet": HOOVES}},
              "gun": {"model": gun_path, "attach": {"to": "camel", "bone": "bone attachpoint",
                                                     "from_bone": f"bone_{unit.gun_name}"}},
              "rider": {"model": rider_model, "rig": "human", "attach": {"to": "camel", "bone": "bone attachpoint"}}}
    clips, grips = {}, []
    path = lambda n: os.path.join(folder, n + ".gr2").replace("\\", "/")  # noqa: E731
    for name, b in built.items():
        anims = {"camel": path(b.camel_name), "gun": path(b.gun_name),
                 "rider": path(b.rider_name) if b.rider_name else expand(b.stock_rider)}
        c = {"anims": anims, "duration": round(b.length, 6), "loop": name in LOOPS, "death": name == "death",
             "ground_speed": "auto" if name in MOVES else 0.0}
        if name in MOVES:
            c["limits"] = {"sink": 0.12}
        if name.startswith("cheer"):
            c["limits"] = {"look_yaw": 85.0, "penetration": 0.10}
        if name == "death":
            c["limits"] = {"look_yaw": 115.0, "look_pitch_down": 80.0, "look_pitch_up": 80.0,
                           "angular_speed": 2000.0, "sink": 0.30, "slide": 0.30, "penetration": 0.30, "cross": 0.40}
        if name not in ("unlimber", "limber", "deployed", "fire", "reload", "death"):
            c["routes"] = {"linstock": {"start": "ring", "end": "ring"}}
        if name == "reload":
            c["routes"] = {"charge": {"start": "hidden", "end": "hidden"}, "ball": {"start": "hidden", "end": "hidden"}}
        clips[name] = c
        for g in b.grips:
            gname, s, t0, t1 = g[:4]
            bone = g[4] if len(g) > 4 else "linstock"
            k0 = int(round(t0 * FPS))
            grips.append({"name": gname, "clips": [name], "hand": hand[s], "frames": [[t0, t1]],
                          "grip": {"bone": f"gun:bone_{bone}", "at": hand[s], "frame": k0}})
    casc = {"idle": (0.0, None), "walk": (0.0, None), "jog": (0.0, None), "bored_a": (0.0, None),
            "bored_b": (0.0, None), "bored_c": (0.0, None)}
    for name, (t0, t1) in casc.items():
        g = {"name": "left palm on the cascabel", "clips": [name], "hand": hand["l"],
             "grip": {"bone": "gun:bone_cannon", "at": hand["l"], "frame": int(round(t0 * FPS))}}
        if t1 is not None:
            g["frames"] = [[t0, t1]]
        grips.append(g)
    grips.append({"name": "the match on the vent", "clips": ["fire"], "frames": [[0.80, 0.95]], "max": 0.03,
                  "hand": "gun:bone_match", "grip": "gun:bone_fuse"})
    del staff_m
    # the ring: where the staff's foot sits on the camel's chest (metres, in the chest's frame)
    P = unit.camel.fix_hang(unit.camel.pose(unit.camel.base, 0.0))
    ring = unit.ring(P)
    upm_c = gr2_mesh.read(unit.camel.cut)["units_per_meter"]
    chest = P[unit.camel.mount].copy()
    chest[:3, 3] /= upm_c
    off = (np.linalg.inv(chest) @ np.r_[ring[:3, 3] / upm_c, 1.0])[:3]
    # the bore: from the breech to the muzzle in the cannon bone's frame (metres)
    d = unit.d
    upm_g = gr2_mesh.read(unit.src.data)["units_per_meter"]
    bore = [((d.bpoint(q) - d.trunnion) / d.bind_scale / upm_g).tolist() for q in (d.src.breech, d.src.muzzle)]
    # the barrel as points (breech to muzzle) and the linstock's hot tip: never in the camel's head or
    # neck, his body, or the ground (a death that drives the weapon into it)
    b0, b1 = np.asarray(bore[0]), np.asarray(bore[1])
    barrel_pts = [{"name": f"barrel {k}/4", "bone": "gun:bone_cannon", "offset": (b0 + (b1 - b0) * k / 4.0).tolist()}
                  for k in range(5)]
    tip_pt = {"name": "linstock tip", "bone": "gun:bone_match"}
    barrel_names = [p["name"] for p in barrel_pts]
    # the props against the man, as shares of his height (lowest foot bone to head bone): the approved
    # sizes (stop 0, 2026-11-26: linstock 50%, barrel 66%) within a fifth either way
    sizes = [{"name": "the linstock against him", "a": "gun:bone_linstock", "b": "gun:bone_match", "of": "rider",
              "min": 0.40, "max": 0.60},
             {"name": "the barrel against him", "a": {"bone": "gun:bone_cannon", "offset": bore[0]},
              "b": {"bone": "gun:bone_cannon", "offset": bore[1]}, "of": "rider", "min": 0.53, "max": 0.80}]
    # his palms not behind his shoulders (the deaths aside)
    living = [n for n in clips if n != "death"]
    ahead = [{"name": f"{'right' if s == 'r' else 'left'} palm not behind his shoulder", "clips": living,
              "point": hand[s], "of": f"rider:bip01 {s} upperarm", "min": AHEAD_MIN} for s in ("r", "l")]
    job = {"fps": FPS, "ground": 0.0, "actors": actors, "clips": clips,
           "mounts": [{"name": "the fork in its socket", "part": "gun:bone_yaw",
                       "mount": {"bone": "camel:hs bone chest", "at": "gun:bone_yaw"}},
                      {"name": "the trunnions in the fork", "part": "gun:bone_cannon",
                       "mount": {"bone": "gun:bone_yaw", "at": "gun:bone_cannon"}}],
           "grips": grips,
           "ahead": [{"name": "right palm in front of his chest", "clips": ["fire"], "frames": [[0.5, 1.4]],
                      "point": hand["r"], "of": "rider:bip01 r upperarm", "min": 0.15}] + ahead,
           "sizes": sizes,
           "penetration_points": barrel_pts + [tip_pt],
           "capsules": [{"name": "camel body", "a": "camel:hs bone pelvis", "b": "camel:hs bone chest", "radius": 0.45,
                         "allow": barrel_names},
                        {"name": "camel neck", "a": "camel:hs bone neck upper", "b": "camel:hs bone head", "radius": 0.13},
                        {"name": "camel head", "a": "camel:hs bone head", "b": "camel:hs bone jaw", "radius": 0.13},
                        {"name": "bore", "a": {"bone": "gun:bone_cannon", "offset": bore[0]},
                         "b": {"bone": "gun:bone_cannon", "offset": bore[1]}, "radius": 0.10,
                         "allow": barrel_names}],
           "props": {"linstock": {"bone": "gun:bone_linstock", "size": 0.08},
                     "charge": {"bone": "gun:bone_charge", "size": 0.06, "hide_in": ["rider torso", "bore"]},
                     "ball": {"bone": "gun:bone_ball", "size": 0.05, "hide_in": ["rider torso", "bore"]}},
           "speed_exempt": ["rider:bip01 prop1", "rider:bip01 prop2"],
           "places": {"ring": {"point": {"bone": "camel:hs bone chest", "offset": off.tolist()}, "radius": 0.08}},
           "speed_limits": {f"camel:{h['bone'].lower()}": 2000.0 for h in HOOVES} |
                           {"camel:hs bone tail_01": 2000.0, "camel:hs bone ear left": 2100.0,
                            "camel:hs bone ear right": 2100.0},
           "reasons": {"walk/jog/run sink 0.12": "the camel's walk, jog and run are the game's own clips, whose hoof "
                                                 "toes sink 6-11 cm; the legs are copied unchanged",
                       "hoof and tail speed 2000": "the game's own camel clips and lying idle flick the hooves and tail "
                                                   "up to 1890 deg/s",
                       "prop bones exempt": "the rider's Prop1 and Prop2 bones hold nothing in this unit; the "
                                            "seated and standing stances give them different turns",
                       "ear speed 2100": "the camel's own idles (idle02, idle03) flick its ears at 2013 deg/s",
                       "cheer look 85, penetration 0.10": "today's rider cheers, unchanged: they turn his head 84 deg "
                                                           "and swing a heel 9 cm into the crude capsule round the "
                                                           "camel's body as the stock rider does",
                       "death look/speed/sink/slide/penetration/cross": "the artillerist's death is the game's "
                                                                        "defend_death (the gatling camel's deployed "
                                                                        "gunner's), unchanged: it throws the head back "
                                                                        "fast, its toes go through the ground (26 cm at "
                                                                        "0.13 s, 23 cm at 1.40 s) and its legs cross "
                                                                        "(30 cm at 0.77 s) as the body drops",
                       "palms -0.10": "a palm at most 10 cm behind its shoulder: today's rider cheer H holds one "
                                      "6.5 cm behind"},
           "removed": dict(REMOVED)}
    base_actors = {"camel": {"model": expand(recipe["camel"]["model"]), "rig": {"preset": "bare", "feet": HOOVES}},
                   "rider": actors["rider"]}
    base = {"fps": FPS, "ground": 0.0, "actors": base_actors,
            "clips": {n: {"anims": {"camel": expand(c), "rider": expand(r)}, "loop": n in LOOPS}
                      for n, c, r in BASELINE}}
    dead = {"fps": FPS, "ground": 0.0,
            "actors": {"camel": {"model": dead_path, "rig": {"preset": "bare", "feet": HOOVES}}, "rider": actors["rider"]},
            "clips": {n: {"anims": {"camel": expand(c), "rider": expand(r)}, "death": True,
                          "limits": {"look_yaw": 95.0, "look_pitch_down": 90.0, "look_pitch_up": 90.0,
                                     "angular_speed": 2000.0, "sink": 0.65, "slide": 0.60, "penetration": 0.50,
                                     "duration": 2.0, "cross": 0.40}}
                      for n, c, r in DEATHS_KEPT},
            "removed": dict(DEATHS_DROPPED),
            "reasons": {"all": "today's death clips of the camel and the rider, unchanged (their hooves and feet sink "
                               "up to 61 cm, heads turn 92 deg, the havoc riders' clips are shorter than the camel's, "
                               "as today); only the camel's model changes (the cannon built in), so these clips are "
                               "checked for what rests at the end",
                        "cross 0.40": "the stock riders' deaths cross their legs as they fall (rider_death_havoc_b: "
                                      "36 cm); unchanged"}}
    # the cannon built into the dead model (its limber pose): its breech and muzzle, held by the bone it
    # is bound to, must not go into the ground as the camel falls
    Pl = P
    fr_l = unit.gun_frames(dict(recipe["limber"]))
    to_w = unit.C(Pl) @ fr_l["cannon"] @ tr(-d.trunnion)
    holder = Pl[unit.camel.mount].copy()
    holder[:3, 3] /= upm_c
    dead["penetration_points"] = [
        {"name": f"cannon {nm}", "bone": f"camel:{unit.camel.mount}", "max": 0.05,
         "offset": (np.linalg.inv(holder) @ np.r_[point(to_w, d.bpoint(q)) / upm_c, 1.0])[:3].tolist()}
        for nm, q in (("breech", d.src.breech), ("muzzle", d.src.muzzle))]
    dead["reasons"]["cannon into the ground 0.05"] = ("the cannon on the dead camel's back: its breech and muzzle "
                                                      "may not go more than 5 cm into the ground as it falls")
    dead_base = dict(dead, actors={"camel": base_actors["camel"], "rider": actors["rider"]},
                     clips={n: {"anims": {"camel": expand(c), "rider": expand(r)}, "death": True} for n, c, r in DEATHS})
    dead_base.pop("penetration_points", None)
    dead_base.pop("removed", None)
    dead["speed_limits"] = {"rider:bip01 head": 2000.0, "rider:bip01 neck": 2000.0}
    # killed unlimbered: its own job (the stock rifleman death turns his head faster than a living
    # man's limit allows the other clips)
    death_b = json.loads(json.dumps(job))
    death_b["clips"] = {"death": job["clips"].pop("death")}
    death_b["speed_limits"].update({"rider:bip01 head": 1500.0, "rider:bip01 neck": 1500.0})
    death_b["removed"] = {}
    out = {}
    for fname, spec in (("job.json", job), ("baseline.json", base), ("job-deaths.json", dead),
                        ("baseline-deaths.json", dead_base), ("job-death-unlimbered.json", death_b)):
        p = os.path.join(check, fname)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=1)
        out[fname] = p
    return out


# --------------------------------------------------------------------------------------------------
# Round 2 (2026-11-26, the user's corrections): a short linstock, a muzzle-loading reload, and the
# unlimbered unit laid out as the deployed gatling camel's round 6 (the gun resting square to the
# camel's spine, +90, turning +30..+150, the artillerist on the camel's left behind the breech).
# These are the key poses of the script delta, for the stills.

REST_YAW = 90.0
ARC = (30.0, 150.0)
WALK = mgc.LIB + "range\\march_rifleman"


class Round2:
    """The key poses of round 2 on the lying camel: his station at a gun yaw, the fire, and the
    reload's walk round the camel's front to the muzzle on its right."""

    GRIP = 0.50           # his hand this far up the short linstock from its foot (the match 0.35 above)
    OUT = 0.15            # his station this far outside the camel's left side (in reach of the breech)

    def __init__(self, unit):
        self.u = unit
        self.P = neck_turned(unit, unit.lie(), 1.0)
        self.walk_anim = unit.rider.anim(WALK)
        pts = unit.camel.mesh_points(self.P)[used_vertices(unit.camel)]
        self.body = pts
        self.front = float(pts[:, 2].max())
        self.back = float(pts[:, 2].min())

    def frames(self, yaw, **state):
        st = {"yaw": yaw}
        st.update(state)
        return self.u.gun_frames(st)

    def world(self, fr, key, local=None):
        C = self.u.C(self.P)
        if local is None:
            return point(C, fr[key][:3, 3])
        return point(C, point(fr[key], local))

    def barrel_points(self, fr):
        d = self.u.d
        C = self.u.C(self.P)
        to_w = C @ fr["cannon"] @ tr(-d.trunnion)
        return point(to_w, d.bpoint(d.src.breech)), point(to_w, d.bpoint(d.src.muzzle))

    def flank_x(self, z, half=0.25):
        """The camel's left side (its least x) about z."""
        band = self.body[np.abs(self.body[:, 2] - z) < half]
        return float(band[:, 0].min()) if len(band) else float(self.body[:, 0].min())

    def station(self, yaw):
        """(at, heading): behind the breech along the barrel, never nearer the camel than OUT outside
        its left side, facing the vent."""
        fr = self.frames(yaw)
        b, m = self.barrel_points(fr)
        ax = unit(np.array([m[0] - b[0], 0.0, m[2] - b[2]]))
        at = b - 0.55 * ax
        at[1] = 0.0
        at[0] = min(at[0], self.flank_x(at[2]) - self.OUT)
        vent = self.world(fr, "fuse")
        dvec = vent - at
        return at, math.degrees(math.atan2(dvec[0], dvec[2])), vent

    def at_station(self, yaw, holding=True):
        """His pose at the station of `yaw`, the linstock in his right hand (match up)."""
        u = self.u
        at, h, vent = self.station(yaw)
        R = u.standing(at, h)
        W = u._carry(R, self.GRIP) if holding else None
        goals = {"l": u.hang_hand(R, "l")}
        if holding:
            goals["r"] = u.grip_on(R, W, self.GRIP, "r")
        b = Built("still", "", [0.0, 1.0])
        R = u.hands(R, goals, b, False)
        R = u.look(R, vent, max_pitch=30.0)
        return R, W

    def touch(self, yaw, stand_yaw=None):
        """The shot: his right arm reaches up, the match at the vent (one hand); with `stand_yaw`, he
        stays at that yaw's station and reaches the vent of the gun turned to `yaw` (the aim table)."""
        u = self.u
        at, h, vent = self.station(yaw)
        if stand_yaw is not None:
            at, h, _v = self.station(stand_yaw)
        R = u.standing(at, h)
        sh = R["bip01 r upperarm"][:3, 3]
        reach = u.src.linstock_length - self.GRIP
        d = unit(vent - sh)
        hand = vent - reach * d
        W = u.staff(hand - self.GRIP * d, d, side=u.facing(R))
        b = Built("still", "", [0.0, 1.0])
        R = u.hands(R, {"r": u.grip_on(R, W, self.GRIP, "r"), "l": u.hang_hand(R, "l")}, b, False)
        R = u.look(R, vent, max_pitch=35.0)
        return R, W, b.reach

    def planted(self, yaw=REST_YAW):
        """The linstock stuck in the ground at his station, beside his right foot, its spike 0.06 in."""
        at, h, _v = self.station(yaw)
        S = self.u.standing(at, h)
        foot = S["bip01 r foot"][:3, 3]
        return self.u.staff(np.array([foot[0], -0.06, foot[2]]) + 0.15 * self.u.right_of(S) + 0.18 * self.u.facing(S), Y)

    def reload_path(self, yaw=REST_YAW):
        """His way to the muzzle and back: from the station along the left side, round the camel's
        front, along its right to the spot beside the muzzle: [(x, z)]."""
        at, _h, _v = self.station(yaw)
        fr = self.frames(yaw)
        _b, m = self.barrel_points(fr)
        fx = self.flank_x(self.front - 0.2) - 0.35
        front = self.front + 0.35
        right = float(self.body[:, 0].max()) + 0.35
        spot = np.array([m[0] + 0.55, m[2] + 0.38])
        pts = [np.array([at[0], at[2]]), np.array([fx, front]), np.array([right, front]),
               np.array([max(right, spot[0]), spot[1]])]
        return pts, m

    def path_length(self, pts):
        return float(sum(np.linalg.norm(b - a) for a, b in zip(pts, pts[1:])))

    def load_pose(self, what, yaw=REST_YAW):
        """At the muzzle: 'pouch' (his right hand at the pouch on his left hip), 'charge' or 'ball'
        (his right hand pushing it into the muzzle). (pose, gun state)."""
        u = self.u
        pts, m = self.reload_path(yaw)
        fr = self.frames(yaw)
        b_, mz_ = self.barrel_points(fr)
        ax = unit(mz_ - b_)
        spot = pts[-1]
        at = np.array([spot[0], 0.0, spot[1]])
        aim = mz_ + 0.45 * ax
        dvec = aim - at
        R = u.standing(at, math.degrees(math.atan2(dvec[0], dvec[2])))
        st = {"yaw": yaw, "linstock": u.staff_design(self.P, self.planted(yaw))}
        b = Built("still", "", [0.0, 1.0])
        C = u.C(self.P)
        Ci = np.linalg.inv(C)
        rt, f = u.right_of(R), u.facing(R)
        if what == "pouch":
            pal = R["bip01 pelvis"][:3, 3] - 0.13 * rt + 0.10 * f - 0.02 * Y
            R = u.hands(R, {"r": (pal, -Y, rt), "l": u.hang_hand(R, "l")}, b, False)
            prop = tr(pal)
            st["charge"] = u.staff_design(self.P, prop)
            look = pal
        else:
            pal = mz_ + 0.07 * ax
            R = u.hands(R, {"r": (pal, -ax, -Y), "l": u.hang_hand(R, "l")}, b, False)
            st[what] = u.staff_design(self.P, tr(mz_ - 0.02 * ax))
            look = mz_
        R = u.look(R, look, max_pitch=35.0)
        return R, st, b.reach


NECK_TURN = 60.0          # the lying camel turns its neck this far to its right (the gatling camel's round 6)


def neck_turned(unit, P, share):
    """The pose with the camel's neck turned `share` of NECK_TURN to its right about the vertical."""
    from aoe3game.gr2_pose import rotate_about
    if share <= 0.0:
        return P
    return rotate_about(P, unit.camel.rig, "hs bone neck lower", "hs bone neck lower", Y, NECK_TURN * share)


# The unlimbered clips of script v2 (approved 2026-11-26), at the gun's rest yaw (+90); a game key
# (turretArc, aim file version 2) turns the gun from there. Times are the script's.
UNLIMBER2, LIMBER2, RELOAD2 = 6.6667, 5.5, 3.0
LOAD_YAW = 270.0          # the reload swings the gun round through its back until its muzzle points at him


class V2:
    """The unlimbered clips of script v2: the unlimber and the limber, the idle, the one-handed shot,
    the reload with the gun swung round to him, and the death (the camel slumps)."""

    G = Round2.GRIP

    def __init__(self, unit):
        self.u = unit
        self.r2 = Round2(unit)
        self.P = self.r2.P                                   # lying, the neck turned
        at, h, vent = self.r2.station(REST_YAW)
        self.at, self.h, self.vent = at, h, vent
        self.S0 = unit.standing(at, h)
        self.W0 = unit._carry(self.S0, self.G)

    # -- small pieces

    def keep(self, b, t0, t1, side, bone="linstock", name=None):
        b.grips.append((name or f"{'right' if side == 'r' else 'left'} palm on the {bone}", side, t0, t1, bone))

    def planted(self):
        return self.r2.planted(REST_YAW)

    def held_high(self, R):
        """The linstock upright in his right hand held up by his shoulder, clear of the camel."""
        u = self.u
        p = R["bip01 r upperarm"][:3, 3] - 0.25 * Y + 0.22 * u.right_of(R) + 0.12 * u.facing(R)
        return u.staff(p - self.G * Y - STAFF_R * u.right_of(R), Y, side=u.facing(R))

    def drawn(self, ring, lift):
        return self.u.staff(ring[:3, 3] + lift * ring[:3, 1], ring[:3, 1], side=ring[:3, 2])

    def left_saddle(self, P, R):
        """His left palm flat on the saddle's front left as he gets off or on."""
        attach = rigid(P[self.u.camel.rider_bone])
        A = attach[:3, :3]
        p = attach[:3, 3] + A @ np.array([-0.16, 0.05, 0.10])
        return p, A @ Z, A @ np.array([0.0, -1.0, 0.0])

    def barrel_at(self, P, fr, from_muzzle):
        """(palm, finger, normal): a palm on top of the barrel `from_muzzle` back from the muzzle."""
        u = self.u
        a, m = self.r2.barrel_points(fr) if P is self.P else self.points(P, fr)
        ax = unit(m - a)
        upv = unit(Y - (Y @ ax) * ax)
        rad = u.d.radius / u.d.bind_scale
        return m - from_muzzle * ax + (rad + 0.03) * upv, ax, -upv

    def points(self, P, fr):
        d = self.u.d
        to_w = self.u.C(P) @ fr["cannon"] @ tr(-d.trunnion)
        return point(to_w, d.bpoint(d.src.breech)), point(to_w, d.bpoint(d.src.muzzle))

    def cascabel2(self, P, fr, side_off=0.0):
        palm, fin, nor = self.u.cascabel(P, fr)
        a, m = self.points(P, fr)
        ax = unit(m - a)
        across = unit(np.cross(Y, ax))
        return palm + side_off * across, fin, nor

    def lean_seated(self, R, t, t0):
        """The lean as the camel lies down (from t0) or rises: back 15 as the front drops, forward 10."""
        if t < t0 or t > t0 + 3.33:
            return R
        k = t - t0
        return self.u.fwd_lean(R, -15.0 * span(k, 0.3, 1.6) + 25.0 * span(k, 1.6, 3.0) - 10.0 * span(k, 3.0, 3.33))

    # -- the unlimber (6.67 s) and the limber (5.5 s)

    def unlimber(self):
        u, cam = self.u, self.u.camel
        times = u.times(UNLIMBER2)
        b = Built("unlimber", "Bombard_unlimber", times)
        poses, anim, scales = u.camel_borrow(mgc.B_DOWN, times, 0.0)
        poses = [neck_turned(u, P, span(t, 3.33, 4.73)) for t, P in zip(times, poses)]
        P_lie = poses[-1]
        keys = u.climb_keys(P_lie)
        S_beside = keys[-1][1]
        lim = u.limber
        for t, P in zip(times, poses):
            # he pushes it from pose B to 60 (3.83-4.25), it swings on to its rest at +90 (4.25-4.63)
            yaw = lim["yaw"] + (60.0 - lim["yaw"]) * span(t, 3.83, 4.25) + (REST_YAW - 60.0) * span(t, 4.25, 4.63)
            fr = u.gun_frames({"yaw": yaw, "pitch": lim["pitch"] * (1 - span(t, 3.83, 4.40))})
            ring = u.ring(P)
            if t < 4.73:
                R = self.lean_seated(u.seated(P), t, 0.0)
            elif t < 5.63:
                R = u.climb(keys, (t - 4.73) / 0.90)
            else:
                R = u.walk(S_beside, self.S0, (t - 5.63) / 1.04, "l")
            # the linstock: in its holster, drawn up 0.30 and held by his thigh, held high as he gets off,
            # then at his side
            if t < 3.43:
                W = ring
            elif t < 4.73:
                W = self.drawn(ring, 0.30 * span(t, 3.43, 3.73))
            elif t < 5.63:
                W = u.staff_mix(self.drawn(ring, 0.30), self.held_high(R), span(t, 4.73, 4.95))
            else:
                W = u.staff_mix(self.held_high(R), u._carry(R, self.G), span(t, 5.63, 5.95))
            reins_r, reins_l = u.reins(R, P, "r"), u.reins(R, P, "l")
            goals = {}
            goals["r"] = reins_r if t < 3.33 else u.blend_goal(reins_r, u.grip_on(R, W, self.G, "r"), span(t, 3.33, 3.43), 0.04)
            if t < 3.73:
                goals["l"] = reins_l
            elif t < 4.25:
                goals["l"] = u.blend_goal(reins_l, u.cascabel(P, fr), span(t, 3.73, 3.83), 0.04)
            elif t < 4.83:
                let_go = u.cascabel(P, u.gun_frames({"yaw": 60.0, "pitch": lim["pitch"] * (1 - span(4.25, 3.83, 4.40))}))
                goals["l"] = u.blend_goal(let_go, self.left_saddle(P, R), span(t, 4.25, 4.50), 0.04)
            elif t < 5.40:
                goals["l"] = self.left_saddle(P, R)
            else:
                goals["l"] = u.blend_goal(self.left_saddle(P, R), u.hang_hand(R, "l"), span(t, 5.40, 5.70))
            R = u.hands(R, goals, b, seated=t < 5.0)
            A = rigid(P[cam.rider_bone])[:3, :3]
            if t < 3.33:
                look = R["bip01 head"][:3, 3] + 12.0 * (A @ Z)
            elif t < 3.73:
                look = point(ring, (0.0, 0.3, 0.0))
            elif t < 4.73:
                look = u.cascabel(P, fr)[0]
            elif t < 5.40:
                look = R["bip01 head"][:3, 3] + 2.0 * (-(A @ X)) + 1.0 * (A @ Z) - 2.0 * Y
            elif t < 5.63:
                look = rigid(P[cam.rider_bone])[:3, 3]
            else:
                look = self.vent
            R = u.look(R, look, max_yaw=45.0, max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=u.staff_design(P, W)))
            b.rider.append(R)
        self.keep(b, 3.43, UNLIMBER2, "r")
        self.keep(b, 3.85, 4.25, "l", "cannon", "left palm on the cascabel")
        b.camel_src = (anim, scales)
        return b

    def limber(self):
        u, cam = self.u, self.u.camel
        times = u.times(LIMBER2)
        b = Built("limber", "Bombard_limber", times)
        poses, anim, scales = u.camel_borrow(mgc.B_UP, times, 3.33)
        poses = [neck_turned(u, P, 1.0 - span(t, 3.10, 3.33)) for t, P in zip(times, poses)]
        P_lie = poses[0]
        keys = u.climb_keys(P_lie)
        S_beside = keys[-1][1]
        lim = u.limber
        for t, P in zip(times, poses):
            # at his station he pulls the gun round from its rest to 60 (0.10-0.40); seated, he sets it to
            # pose B (1.90-2.60)
            w = span(t, 1.90, 2.60)
            yaw = REST_YAW + (60.0 - REST_YAW) * span(t, 0.22, 0.42) + (lim["yaw"] - 60.0) * w
            fr = u.gun_frames({"yaw": yaw, "pitch": lim["pitch"] * w})
            ring = u.ring(P)
            if t < 0.40:
                R = self.S0
            elif t < 0.90:
                R = u.walk(self.S0, S_beside, (t - 0.40) / 0.50, "r")
            elif t < 1.80:
                R = u.climb(keys, 1.0 - (t - 0.90) / 0.90)
            else:
                R = self.lean_seated(u.seated(P), t, 3.33)
            if t < 0.90:
                W = u.staff_mix(u._carry(R, self.G), self.held_high(R), span(t, 0.70, 0.90))
            elif t < 1.80:
                W = self.held_high(R)
            elif t < 2.80:
                W = u.staff_mix(self.held_high(R), self.drawn(ring, 0.30), span(t, 1.80, 2.10))
            else:
                W = self.drawn(ring, 0.30 * (1.0 - span(t, 2.80, 3.05)))
            reins_r, reins_l = u.reins(R, P, "r"), u.reins(R, P, "l")
            goals = {"r": u.grip_on(R, W, self.G, "r") if t < 3.05 else
                     u.blend_goal(u.grip_on(R, ring, self.G, "r"), reins_r, span(t, 3.05, 3.25), 0.04)}
            if t < 0.22:
                goals["l"] = u.blend_goal(u.hang_hand(R, "l"), u.cascabel(P, fr), span(t, 0.0, 0.22))
            elif t < 0.42:
                goals["l"] = u.cascabel(P, fr)
            elif t < 0.90:
                goals["l"] = u.blend_goal(u.cascabel(P, u.gun_frames({"yaw": 60.0})), u.hang_hand(R, "l"),
                                          span(t, 0.42, 0.74))
            elif t < 1.60:
                goals["l"] = u.blend_goal(u.hang_hand(R, "l"), self.left_saddle(P, R), span(t, 0.90, 1.05))
            elif t < 1.90:
                goals["l"] = u.blend_goal(self.left_saddle(P, R), u.cascabel(P, fr), span(t, 1.60, 1.90), 0.04)
            elif t < 2.60:
                goals["l"] = u.cascabel(P, fr)
            else:
                goals["l"] = u.blend_goal(u.cascabel(P, fr), reins_l, span(t, 2.60, 2.75))
            R = u.hands(R, goals, b, seated=t >= 1.40)
            A = rigid(P[cam.rider_bone])[:3, :3]
            if t < 0.90:
                look = R["bip01 head"][:3, 3] + 6.0 * (A @ Z)
            elif t < 1.80:
                look = point(rigid(P[cam.rider_bone]), (-0.45, -0.20, 0.60))
            elif t < 2.70:
                look = u.cascabel(P, fr)[0]
            elif t < 3.10:
                look = point(ring, (0.0, 0.3, 0.0))
            else:
                look = R["bip01 head"][:3, 3] + 12.0 * (A @ Z)
            R = u.look(R, look, max_yaw=45.0, max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=u.staff_design(P, W)))
            b.rider.append(R)
        self.keep(b, 0.0, 3.05, "r")
        self.keep(b, 0.24, 0.42, "l", "cannon", "left palm on the cascabel (at his station)")
        self.keep(b, 1.92, 2.60, "l", "cannon", "left palm on the cascabel")
        b.camel_src = (anim, scales)
        return b

    # -- at the gun

    def lying(self, times, borrow=True):
        u = self.u
        if borrow:
            poses, anim, scales = u.camel_borrow(mgc.B_IDLE, times, 0.0)
            return [neck_turned(u, P, 1.0) for P in poses], anim, scales
        anim = u.camel.anim(mgc.B_IDLE)
        return [self.P] * len(times), anim, u.camel.hang_scale(self.P, u.camel.borrowed_scales(anim))

    def stand(self, t=0.0, lean=0.0):
        u = self.u
        R = u.standing(self.at, self.h, t)
        if lean:
            R = u.fwd_lean(R, lean)
        return u.plant(R, {s: self.S0[f"bip01 {s} foot"] for s in ("l", "r")})

    def downrange(self, P, fr):
        return self.u.downrange(P, fr)

    def deployed(self, yaw=REST_YAW):
        """The idle at the gun; with `yaw`, the gun turned there (he looks down its line: a row of the
        aim table)."""
        u = self.u
        times = u.times(DEPLOYED)
        b = Built("deployed", "Bombard_ranged_idle", times)
        poses, anim, scales = self.lying(times)
        fr = u.gun_frames({"yaw": yaw})
        for t, P in zip(times, poses):
            R = self.stand(t / DEPLOYED * u.stand_anim.duration)
            R = u.hands(R, {"r": u.grip_on(R, self.W0, self.G, "r"), "l": u.hang_hand(R, "l")}, b, False)
            w = math.sin(math.pi * min(1.0, max(0.0, (t - 0.8) / 0.6))) if 0.8 < t < 1.4 else 0.0
            look = lerp(self.downrange(P, fr), point(self.W0, (0.0, u.src.linstock_length, 0.0)), w)
            R = u.look(R, look, max_pitch=30.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=u.staff_design(P, self.W0)))
            b.rider.append(R)
        self.keep(b, 0.0, DEPLOYED, "r")
        b.camel_src = (anim, scales)
        return b

    def fire(self, yaw=REST_YAW):
        """The one-handed shot; with `yaw`, the gun turned there and he, still at his rest station,
        reaching its vent (a row of the aim table: turretArc blends these by the gun's yaw)."""
        u = self.u
        times = u.times(FIRE)
        b = Built("fire", "Bombard_ranged_attack", times)
        poses, anim, scales = self.lying(times, borrow=False)
        P = self.P
        _Rt, W_touch, _m = self.r2.touch(yaw, stand_yaw=REST_YAW)
        vent = self.r2.station(yaw)[2]
        d = W_touch[:3, 1]
        W_near = u.staff(W_touch[:3, 3] - 0.08 * d + 0.06 * Y, d, side=W_touch[:3, 2])
        W_up = u.staff(self.W0[:3, 3] + 0.08 * Y + 0.10 * u.facing(self.S0), self.W0[:3, 1], side=self.W0[:3, 2])
        for t in times:
            if t <= 0.50:
                W = u.staff_mix(self.W0, W_near, span(t, 0.0, 0.50))
            elif t <= 0.95:
                W = u.staff_mix(W_near, W_touch, span(t, 0.50, 0.80))
            elif t <= 1.40:
                W = u.staff_mix(W_touch, W_up, span(t, 0.95, 1.40))
            else:
                W = u.staff_mix(W_up, self.W0, span(t, 1.40, 1.80))
            kick = 6.0 * (span(t, SHOT, 1.00) - span(t, 1.00, 1.50))
            fr = u.gun_frames({"yaw": yaw, "pitch": -kick})
            R = self.stand(0.0, lean=-4.0 * span(t, 0.0, 0.5) * (1.0 - span(t, 1.4, 2.0)))
            R = u.hands(R, {"r": u.grip_on(R, W, self.G, "r"), "l": u.hang_hand(R, "l")}, b, False)
            away = math.sin(math.pi * min(1.0, max(0.0, (t - 0.92) / 0.48))) if 0.92 < t < 1.40 else 0.0
            look = vent if t < 1.40 else self.downrange(P, fr)
            if away > 0:
                hpos = R["bip01 head"][:3, 3]
                look = hpos + axis_matrix(Y, -45.0 * away) @ (look - hpos)
            R = u.look(R, look, max_yaw=60.0, max_pitch=35.0)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=u.staff_design(P, W)))
            b.rider.append(R)
        self.keep(b, 0.0, FIRE, "r")
        b.camel_src = (anim, scales)
        b.flash = [SHOT]
        return b

    # the reload (3.0 s): the gun swung round to him through its back until its muzzle points at the place
    # he stood, loaded by hand at the muzzle (charge, then ball: no rammer, the user, 2026-11-26), swung back.
    # He steps a pace forward out of the barrel's way as it comes round and back again as it leaves.
    PUSH, CATCH = 105.0, 255.0        # he pushes the gun to PUSH; it swings on to CATCH, where he takes it
    # the beats: (start, end) of each
    B_PLANT = (0.00, 0.30)            # crouch, the linstock stuck in the ground (planted by 0.15), up
    B_PUSH = (0.24, 0.55)             # hands to the cascabel (0.24-0.40), the push to PUSH (0.40-0.55)
    B_SWING = (0.55, 1.15)            # it swings on to CATCH; he steps forward out of its way (0.60-0.90)
                                      # and reaches for the chase (0.95-1.15)
    B_CATCH = (1.15, 1.27)            # he catches the chase and pulls the muzzle to him (LOAD_YAW)
    B_CHARGE = (1.27, 1.57)           # pouch (1.37), at the muzzle (1.49), pushed in (1.57)
    B_BALL = (1.57, 1.87)             # pouch (1.67), at the muzzle (1.79), pushed in (1.87)
    B_BACK = (1.87, 2.70)             # both hands on the chase (1.87-2.00), pushed off (2.00-2.08); it swings
                                      # back to PUSH (2.08-2.50) as he steps back to his station (2.12-2.40);
                                      # he catches the cascabel (2.42-2.56) and sets it at the rest (2.58-2.70)
    B_PICK = (2.70, 3.00)             # crouch (2.70-2.85), the linstock pulled up as he rises (2.85-3.00)

    def spots(self):
        """His place to load (S_load: a pace ahead of his station, beside the muzzle of the gun swung
        round to LOAD_YAW, on its front side, facing it) and the muzzle and the barrel's axis there."""
        u = self.u
        fr = u.gun_frames({"yaw": LOAD_YAW})
        b_, m = self.r2.barrel_points(fr)
        ax = unit(np.array([m[0] - b_[0], 0.0, m[2] - b_[2]]))
        side = np.cross(Y, ax)
        if side @ Z < 0:
            side = -side                                   # the front side: the barrel comes from the rear
        at = m + 0.15 * ax + 0.34 * side
        tgt = m - 0.20 * ax
        dv = tgt - at
        S_load = u.standing(np.array([at[0], 0.0, at[2]]), math.degrees(math.atan2(dv[0], dv[2])))
        return S_load, m, ax

    def reload(self):
        u = self.u
        times = u.times(RELOAD2)
        b = Built("reload", "Bombard_reload", times)
        P = self.P
        anim = u.camel.anim(mgc.B_IDLE)
        scales = u.camel.hang_scale(P, u.camel.borrowed_scales(anim))
        S_load, _m, _ax = self.spots()
        S_sq = mgc.Unit.crouch(u, self.S0, 0.45, 35.0)
        feet0 = {s: self.S0[f"bip01 {s} foot"] for s in ("l", "r")}
        Wp = self.planted()
        C = u.C(P)
        PU, CA = self.PUSH, self.CATCH

        def bar(frx, from_muzzle):
            """His palm on top of the chase, the fingers away from him along it (toward the breech)."""
            p, fin, nor = self.barrel_at(P, frx, from_muzzle)
            return p, -fin, nor

        def yaw_at(t):
            if t < 0.40:
                return REST_YAW
            if t < 0.55:
                return REST_YAW + (PU - REST_YAW) * span(t, 0.40, 0.55)
            if t < 1.15:
                return PU + (CA - PU) * span(t, 0.55, 1.15)
            if t < 2.00:
                return CA + (LOAD_YAW - CA) * span(t, 1.15, 1.27)
            if t < 2.08:
                return LOAD_YAW - (LOAD_YAW - CA) * span(t, 2.00, 2.08)
            if t < 2.58:
                return CA - (CA - PU) * span(t, 2.08, 2.50)
            return PU - (PU - REST_YAW) * span(t, 2.58, 2.70)

        def crouched(A, S, feet, w):
            return u.plant(blend_pose(u, A, S, w), feet)

        def body(t):
            if t < 0.15:
                return crouched(self.S0, S_sq, feet0, span(t, 0.0, 0.15))
            if t < 0.30:
                return crouched(self.S0, S_sq, feet0, 1.0 - span(t, 0.15, 0.30))
            if t < 0.60:
                return self.S0
            if t < 0.90:
                return u.walk(self.S0, S_load, (t - 0.60) / 0.30, "l")
            if t < 2.12:
                return S_load
            if t < 2.40:
                return u.walk(S_load, self.S0, (t - 2.12) / 0.28, "r")
            if t < 2.70:
                return self.S0
            if t < 2.85:
                return crouched(self.S0, S_sq, feet0, span(t, 2.70, 2.85))
            return crouched(self.S0, S_sq, feet0, 1.0 - span(t, 2.85, 3.00))

        for t in times:
            yaw = yaw_at(t)
            fr0 = u.gun_frames({"yaw": yaw})
            a, m = self.r2.barrel_points(fr0)
            ax = unit(m - a)
            st = {"yaw": yaw}
            R = body(t)
            # the linstock: from his hand to the ground (0.0-0.15), stuck there, back in his hand (2.85-3.00)
            if t < 0.15:
                W = u.staff_mix(self.W0, Wp, span(t, 0.0, 0.15))
            elif t < 2.85:
                W = Wp
            else:
                W = u.staff_mix(Wp, self.W0, span(t, 2.85, 3.00))
            st["linstock"] = u.staff_design(P, W)
            fr = u.gun_frames(st)
            # his hands
            rt = u.right_of(R)
            hang_l, hang_r = u.hang_hand(R, "l"), u.hang_hand(R, "r")
            goals = {"l": hang_l}
            mouth = (m + 0.10 * ax, -ax, -Y)
            inside_mouth = (m - 0.04 * ax, -ax, -Y)            # fingers pushing it in
            if t < 0.15:
                goals["r"] = u.grip_on(R, W, self.G, "r")
            elif t < 0.24:
                goals["r"] = u.blend_goal(u.grip_on(R, Wp, self.G, "r"), hang_r, span(t, 0.15, 0.24))
            elif t < 0.55:
                rel = u.blend_goal(u.grip_on(R, Wp, self.G, "r"), hang_r, 1.0)
                goals["r"] = u.blend_goal(rel, self.cascabel2(P, fr, 0.04), span(t, 0.24, 0.40))
                goals["l"] = u.blend_goal(hang_l, self.cascabel2(P, fr, -0.04), span(t, 0.24, 0.40))
            elif t < 0.95:                                 # he lets go and steps out of its way
                push = u.gun_frames({"yaw": PU})
                goals["r"] = u.blend_goal(self.cascabel2(P, push, 0.04), hang_r, span(t, 0.55, 0.70))
                goals["l"] = u.blend_goal(self.cascabel2(P, push, -0.04), hang_l, span(t, 0.55, 0.70),
                                          arc=-0.10 * rt)
            elif t < 1.15:                                 # and reaches for the chase coming to him
                catch = u.gun_frames({"yaw": CA})
                goals["r"] = u.blend_goal(hang_r, bar(catch, 0.04), span(t, 0.95, 1.15))
                goals["l"] = u.blend_goal(hang_l, bar(catch, 0.15), span(t, 0.95, 1.15))
            elif t < 1.27:
                goals["r"], goals["l"] = bar(fr, 0.04), bar(fr, 0.15)
            elif t < 1.87:
                goals["l"] = u.blend_goal(bar(fr, 0.15), hang_l, span(t, 1.27, 1.47), arc=0.05 * u.facing(R) - 0.16 * rt)
                f_ = u.facing(R)
                pel = R["bip01 pelvis"][:3, 3]
                pouch = (pel - 0.13 * rt + 0.12 * f_ - 0.02 * Y, f_, -Y)
                front = (pel + 0.32 * f_ + 0.18 * Y + 0.04 * rt, f_, -Y)     # his hand passes in front of him
                goals["r"] = keyed([(1.27, bar(fr, 0.04)), (1.32, front), (1.37, pouch), (1.39, pouch),
                                    (1.49, mouth), (1.54, inside_mouth), (1.57, mouth), (1.62, front),
                                    (1.67, pouch), (1.69, pouch), (1.79, mouth), (1.84, inside_mouth),
                                    (1.87, mouth)], t, u)
            elif t < 2.08:
                goals["r"] = u.blend_goal(mouth, bar(fr, 0.04), span(t, 1.87, 2.00))
                goals["l"] = u.blend_goal(hang_l, bar(fr, 0.15), span(t, 1.87, 2.00), arc=-0.10 * rt)
            elif t < 2.42:                                 # he lets it go and steps back
                at_ca = u.gun_frames({"yaw": CA})
                goals["r"] = u.blend_goal(bar(at_ca, 0.04), hang_r, span(t, 2.08, 2.22))
                goals["l"] = u.blend_goal(bar(at_ca, 0.15), hang_l, span(t, 2.08, 2.22), arc=-0.10 * rt)
            elif t < 2.58:                                 # and reaches for the cascabel coming back
                at_pu = u.gun_frames({"yaw": PU})
                goals["r"] = u.blend_goal(hang_r, self.cascabel2(P, at_pu, 0.04), span(t, 2.42, 2.56))
                goals["l"] = u.blend_goal(hang_l, self.cascabel2(P, at_pu, -0.04), span(t, 2.42, 2.56))
            elif t < 2.70:
                goals["r"], goals["l"] = self.cascabel2(P, fr, 0.04), self.cascabel2(P, fr, -0.04)
            else:
                goals["r"] = u.blend_goal(self.cascabel2(P, fr, 0.04), u.grip_on(R, W, self.G, "r"), span(t, 2.70, 2.84))
                goals["l"] = u.blend_goal(self.cascabel2(P, fr, -0.04), hang_l, span(t, 2.70, 2.90))
            R = u.hands(R, goals, b, False)
            # the charge and the ball: hidden inside him (the pouch at his left hip), in his right hand,
            # into the muzzle and down the bore (out of sight there)
            inside = R["bip01 pelvis"][:3, 3] + 0.12 * Y - 0.03 * u.right_of(R)
            palm = u.rider.palm_of(R, "r")
            for prop, (t_draw, t_in, t_gone) in (("charge", (1.37, 1.49, 1.57)), ("ball", (1.67, 1.79, 1.87))):
                if t < t_draw:
                    pos = inside
                elif t < t_in:
                    pos = lerp(inside, palm, span(t, t_draw, t_draw + 0.03))
                elif t < t_gone:
                    pos = lerp(palm, m - 0.25 * ax, span(t, t_in, t_gone))
                else:
                    pos = None
                if pos is not None:
                    st[prop] = u.staff_design(P, tr(pos))
            fr = u.gun_frames(st)
            if t < 0.24 or t >= 2.70:
                look = point(Wp, (0, 0.8, 0))
            elif 0.55 <= t < 0.95 or 2.08 <= t < 2.42:
                look = point(C, fr["cannon"][:3, 3])
            elif t < 1.27 or 2.42 <= t < 2.70:
                look = point(C, fr["cannon"][:3, 3])
            else:
                look = m
            R = u.look(R, look, max_yaw=60.0, max_pitch=28.0)
            b.camel.append(P)
            b.gun.append(fr)
            b.rider.append(R)
        self.keep(b, 0.0, 0.10, "r")
        self.keep(b, 0.42, 0.55, "r", "cannon", "right palm on the cascabel (push)")
        self.keep(b, 1.19, 1.27, "r", "cannon", "right palm on the chase (catch)")
        self.keep(b, 2.02, 2.08, "r", "cannon", "right palm on the chase (push off)")
        self.keep(b, 2.60, 2.70, "r", "cannon", "right palm on the cascabel (settle)")
        self.keep(b, 2.96, RELOAD2, "r")
        b.rider = limit_arm_rates(u.rider.rig, b.rider)
        b.rider = limit_arm_rates(u.rider.rig, b.rider, 720.0, bones=("bip01 neck", "bip01 head"))
        b.camel_src = (anim, scales)
        return b

    def death(self):
        u, cam = self.u, self.u.camel
        times = u.times(DEATH_B)
        b = Built("death", "Bombard_death", times)
        still = self.P
        poses = [cam.fix_hang(cam.slump(still, float(t))) for t in times]
        anim = cam.anim(mgc.B_IDLE)
        scales = cam.hang_scale(poses[0], cam.borrowed_scales(anim))
        fr = u.gun_frames({"yaw": REST_YAW})
        dies = u.rider.anim(mgc.FOOT_DEATH_BACK)
        R0 = u.rider.standing(u.foot, dies, 0.0, self.h, self.at)
        palm0 = u.rider.palm_of(R0, "r")
        W_hand0 = u._carry(R0, self.G)
        off = palm0 - point(W_hand0, (0.0, self.G, 0.0))
        out = unit(-u.right_of(self.S0) - 0.3 * u.facing(self.S0))
        released = None
        for t, P in zip(times, poses):
            R = u.rider.standing(u.foot, dies, min(float(t), dies.duration), self.h, self.at)
            if t < RELEASE:
                palm = u.rider.palm_of(R, "r")
                W = u.staff(W_hand0[:3, 3] + (palm - palm0), W_hand0[:3, 1], side=W_hand0[:3, 2])
                released = W
            else:
                foot = released[:3, 3].copy()
                foot[1] = max(STAFF_R, foot[1] - 0.6 * (t - RELEASE))
                lying = u.staff(np.array([foot[0], STAFF_R, foot[2]]), out)
                w = min(1.0, (t - RELEASE) / 0.40) ** 1.3
                W = u.staff_mix(u.staff(foot, released[:3, 1], side=released[:3, 2]), lying, w)
            b.camel.append(P)
            b.gun.append(dict(fr, linstock=u.staff_design(P, W)))
            b.rider.append(R)
        del off
        b.camel_src = (anim, scales)
        b.death = True
        return b


ARM_BONES = ("bip01 l clavicle", "bip01 l upperarm", "bip01 l forearm", "bip01 l hand",
             "bip01 r clavicle", "bip01 r upperarm", "bip01 r forearm", "bip01 r hand")


def limit_arm_rates(rig, poses, limit=1350.0, fps=30.0, bones=ARM_BONES):
    """The poses with each arm bone's turn against its parent held to `limit` degrees a second (a hand
    that would whip round between two frames eases there instead); the rest of the body untouched."""
    names = [n.lower() for n in rig.names]
    step = math.radians(limit / fps)

    def angle(A, B):
        return math.acos(max(-1.0, min(1.0, (np.trace(A.T @ B) - 1.0) / 2.0)))

    out, prev = [], None
    for R in poses:
        W = dict(R)
        loc = {}
        for i, n in enumerate(names):
            p = rig.parents[i]
            if n not in R or p is None or p < 0 or names[p] not in R:
                continue
            Lc = np.linalg.inv(R[names[p]]) @ R[n]
            if n in bones and prev is not None and n in prev:
                s = np.cbrt(abs(np.linalg.det(Lc[:3, :3])))
                A, B = prev[n][:3, :3] / s, Lc[:3, :3] / s
                if angle(A, B) > step:
                    rel = A.T @ B
                    axis = np.array([rel[2, 1] - rel[1, 2], rel[0, 2] - rel[2, 0], rel[1, 0] - rel[0, 1]])
                    if np.linalg.norm(axis) > 1e-9:
                        cands = [A @ axis_matrix(unit(axis), sgn * math.degrees(step)) for sgn in (1.0, -1.0)]
                        Lc = Lc.copy()
                        Lc[:3, :3] = s * min(cands, key=lambda M: angle(M, B))
            loc[n] = Lc
            W[n] = W[names[p]] @ Lc
        out.append(W)
        prev = loc
    return out


def keyed(keys, t, u):
    """A hand goal between timed keys [(time, goal)], eased."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, g0), (t1, g1) in zip(keys, keys[1:]):
        if t <= t1:
            return u.blend_goal(g0, g1, span(t, t0, t1))
    return keys[-1][1]


def blend_pose(u, A, B, w):
    from aoe3game.gr2_pose import blend
    return blend(u.rider.rig, A, B, ease(w))


def round2_stills(folder, game, recipe, unit, gun_bytes):
    """The stills of the script delta: the short linstock and its holster, the unlimbered unit at
    +90 with his station and the arc, the one-handed touch, and the reload's key poses with its walk."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    u = unit
    r2 = Round2(u)
    scene = mgc.Scene(game, recipe, u.camel, u.rider)
    pic = Picture(game, recipe, u.camel, u.rider, scene, u.d, gun_bytes, None)
    report = []

    def items(P, R, state, extra=None):
        fr = u.d.frames(state)
        hang = rigid(P[u.camel.hang])
        G = {u.d.NAMES.get(k, f"bone_{u.gun_name}").lower(): hang @ u.d.to_model(v) for k, v in fr.items()}
        G[pic.gun_rig.names[0].lower()] = hang
        out = pic.gun_fig.items(G) + scene.camel_fig.items(P)
        if R is not None:
            out += scene.rider_fig.items(R) + scene.hat_items(R)
        return out, G

    def tile(it, az, el, text, span=3.6, centre=(0.0, 1.2, 0.6), marks=None, w=330, h=300):
        return mgc.caption(mgc.draw(it, w, h, az, el, span=span, centre=tuple(centre), marks=marks), text)

    P = r2.P
    # 1. the linstock
    tiles = []
    Pm = u.camel.fix_hang(u.camel.pose(u.camel.base, 0.0))
    Rm = u.seated(Pm)
    Rm = u.hands(Rm, {"r": u.reins(Rm, Pm, "r"), "l": u.cascabel(Pm, u.gun_frames(u.limber))}, Built("s", "", [0, 1]), True)
    it, G = items(Pm, Rm, dict(u.limber))
    tip = G["bone_match"][:3, 3]
    marks = [(tip, (255, 120, 40), 7)]
    hol = G["bone_linstock"][:3, 3]
    tiles += [tile(it, 70.0, 12.0, "LIMBERED: IN ITS HOLSTER, RIGHT", span=2.6, centre=hol + np.array([0, 0.4, 0]), marks=marks),
              tile(it, 140.0, 20.0, "IN ITS HOLSTER, RIGHT REAR", span=2.6, centre=hol + np.array([0, 0.4, 0]), marks=marks)]
    R0, W0 = r2.at_station(REST_YAW)
    it, G = items(P, R0, {"yaw": REST_YAW, "linstock": u.staff_design(P, W0)})
    sh = R0["bip01 spine1"][:3, 3]
    tiles += [tile(it, -110.0, 8.0, "IN HIS RIGHT HAND, MATCH UP", span=2.4, centre=sh - np.array([0, 0.3, 0]),
                   marks=[(G["bone_match"][:3, 3], (255, 120, 40), 7)])]
    # the long staff of preview v1 beside the short one, to scale
    long_len = u.src.linstock_source_length
    if not u.r["linstock"].get("plain"):
        tiles += [linstock_compare(game, u, R0, long_len)]
    sheet1 = np.concatenate([mgc.title(4 * 330, f"SHORT LINSTOCK: {u.src.linstock_length:.2f} LONG (THE MIDFA STAFF "
                                                 f"{long_len:.2f}), MATCH (STAR) AT ITS TIP", back=(70, 40, 20)),
                             mgc.grid(tiles, 4)], 0)
    # 2. unlimbered at +90: views, and the arc from above
    tiles = []
    it, G = items(P, R0, {"yaw": REST_YAW, "linstock": u.staff_design(P, W0)})
    vent = G["bone_fuse"][:3, 3]
    vm = [(vent, (255, 120, 40), 6)]
    for az, el, name in ((-90.0, 75.0, "FROM ABOVE"), (-60.0, 15.0, "LEFT FRONT"), (-130.0, 15.0, "LEFT REAR"),
                         (60.0, 15.0, "RIGHT FRONT")):
        tiles.append(tile(it, az, el, f"AT REST +90: {name}", marks=vm, centre=(0.2, 1.0, 0.6)))
    for yaw in (ARC[0], REST_YAW, ARC[1]):
        Ry, Wy = r2.at_station(yaw)
        it2, G2 = items(P, Ry, {"yaw": yaw, "linstock": u.staff_design(P, Wy)})
        tiles.append(tile(it2, -90.0, 80.0, f"GUN AT +{yaw:.0f}: HIS STATION", centre=(0.2, 1.0, 0.6),
                          marks=[(G2["bone_fuse"][:3, 3], (255, 120, 40), 6)]))
    Rt, Wt, miss = r2.touch(REST_YAW)
    it3, G3 = items(P, Rt, {"yaw": REST_YAW, "linstock": u.staff_design(P, Wt)})
    report.append(f"touch: hand off its goal {miss:.3f}")
    tiles.append(tile(it3, -70.0, 15.0, "THE SHOT: ONE HAND, MATCH ON THE VENT", span=2.6,
                      centre=0.5 * (G3["bone_fuse"][:3, 3] + Rt["bip01 spine1"][:3, 3]),
                      marks=[(G3["bone_fuse"][:3, 3], (255, 120, 40), 7)]))
    sheet2 = np.concatenate([mgc.title(4 * 330, "UNLIMBERED AS THE GATLING CAMEL'S ROUND 6: THE GUN AT +90 (SQUARE TO THE "
                                                "SPINE), ARC +30..+150, HE ON THE LEFT BEHIND THE BREECH (STAR: THE VENT)",
                                       back=(70, 40, 20)), mgc.grid(tiles, 4)], 0)
    # 3. the reload's key poses
    pts, mz_ = r2.reload_path()
    length = r2.path_length(pts)
    report.append(f"reload walk: {length:.2f} game units each way ({len(pts) - 1} legs); front of the camel at "
                  f"z {r2.front:.2f}; the muzzle at {np.round(mz_, 2).tolist()}")
    tiles = []
    path_marks = [(np.array([x, 0.02, z]), (40, 120, 255), 6) for x, z in pts]
    Rp = u.standing(np.array([pts[0][0], 0.0, pts[0][1]]), r2.station(REST_YAW)[1])
    Rp = mgc.Unit.crouch(u, Rp, 0.30, 25.0)
    Wplant = u.staff(np.array([Rp["bip01 r foot"][0, 3], -0.06, Rp["bip01 r foot"][2, 3]]) + 0.25 * u.right_of(Rp), Y)
    Rp = u.hands(Rp, {"r": u.grip_on(Rp, Wplant, u.src.linstock_length - 0.08, "r")}, Built("s", "", [0, 1]), False)
    it4, _G = items(P, Rp, {"yaw": REST_YAW, "linstock": u.staff_design(P, Wplant)})
    tiles.append(tile(it4, -90.0, 15.0, "1 THE LINSTOCK STUCK IN THE GROUND", centre=(-0.5, 0.8, 0.6)))
    mid = 0.5 * (pts[1] + pts[2])
    mid_at = np.array([mid[0], 0.0, mid[1]])
    Rw = u.rider.standing(u.foot, r2.walk_anim, 0.3 * r2.walk_anim.duration, 90.0, mid_at)
    it5, _G = items(P, Rw, {"yaw": REST_YAW, "linstock": u.staff_design(P, r2.planted())})
    tiles.append(tile(it5, -90.0, 75.0, f"2 ROUND THE CAMEL'S FRONT ({length:.1f} EACH WAY)", centre=(0.3, 0.8, 0.8),
                      marks=path_marks))
    for k, (what, text) in enumerate((("pouch", "3 POWDER FROM THE POUCH AT HIS LEFT HIP"),
                                      ("charge", "4 THE CHARGE INTO THE MUZZLE"),
                                      ("ball", "5 THE BALL INTO THE MUZZLE"))):
        Rl, st, miss = r2.load_pose(what)
        report.append(f"reload {what}: hands off their goals {miss:.3f}")
        it6, G6 = items(P, Rl, st)
        tiles.append(tile(it6, 140.0, 15.0, text, span=2.6, centre=0.5 * (mz_ + Rl["bip01 spine1"][:3, 3]),
                          marks=[(G6["bone_launchpoint"][:3, 3], (255, 120, 40), 6)]))
    sheet3 = np.concatenate([mgc.title(4 * 330, "RELOAD (THE WALK TO THE MUZZLE, AS ASKED): KEY POSES", back=(70, 40, 20)),
                             mgc.grid(tiles, 4)], 0)
    paths = []
    for name, sheet in (("z2-linstock.png", sheet1), ("z2-unlimbered.png", sheet2), ("z2-reload-keys.png", sheet3)):
        p = os.path.join(folder, name)
        Image.fromarray(sheet).save(p)
        paths.append(p)
    return paths, report


def linstock_compare(game, u, R, long_len):
    """The short linstock and the long staff standing beside him on the ground, to scale."""
    from PIL import Image  # noqa: F401
    src = u.src
    tex = mgc.Figure(game, src.linstock_data)
    m = next(mm for mm, t in tex.meshes if mm.get("name") == u.r["linstock"]["mesh"])
    texture = next(t for mm, t in tex.meshes if mm.get("name") == u.r["linstock"]["mesh"])
    at = R["bip01 pelvis"][:3, 3]
    rt = u.right_of(R)
    out = mgc.Scene(game, u.r, u.camel, u.rider).rider_fig.items(R)
    uv = src.linstock["uvs"].copy()
    uv[:, 1] = 1.0 - uv[:, 1]
    short = src.linstock["positions"] + np.array([at[0], 0.0, at[2]]) + 0.45 * rt
    out.append((short, src.linstock["triangles"], uv, texture, (180, 140, 60)))
    full = np.asarray(m["file_positions"], np.float64)
    full = full - np.array([full[:, 0].mean(), full[:, 1].min(), full[:, 2].mean()]) + np.array([at[0], 0, at[2]]) + 0.85 * rt
    out.append((full, m["triangles"], m["uvs"], texture, (180, 140, 60)))
    c = np.array([at[0], 1.1, at[2]]) + 0.4 * rt
    return mgc.caption(mgc.draw(out, 330, 300, -100.0, 5.0, span=2.8, centre=tuple(c)),
                       f"SHORT {src.linstock_length:.2f} AND LONG {long_len:.2f} BESIDE HIM")


def textured_sheets(folder, game, recipe, unit, built, gun_bytes, moments=8):
    """For each clip, `moments` frames from the unit's left and right (3/4, a little above), drawn
    with the textures as the game would (the check's own sheets are flat-shaded): one PNG per clip."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    scene = mgc.Scene(game, recipe, unit.camel, unit.rider)
    pic = Picture(game, recipe, unit.camel, unit.rider, scene, unit.d, gun_bytes, None)
    out = []
    for name, b in built.items():
        tiles = []
        n = len(b.times)
        for i in range(moments):
            k = round(i * (n - 1) / (moments - 1))
            P, R = b.camel[k], b.rider[k]
            hang = rigid(P[unit.camel.hang])
            G = {unit.d.NAMES.get(key, f"bone_{unit.gun_name}").lower(): hang @ unit.d.to_model(v)
                 for key, v in b.gun[k].items()}
            G[pic.gun_rig.names[0].lower()] = hang
            items = pic.gun_fig.items(G) + scene.camel_fig.items(P) + scene.rider_fig.items(R) + scene.hat_items(R)
            centre = tuple(0.5 * (P["hs bone chest"][:3, 3] + R["bip01 spine1"][:3, 3]))
            for az, side in ((-55.0, "LEFT"), (55.0, "RIGHT")):
                img = mgc.draw(items, 300, 280, az, 14.0, span=3.6, centre=centre)
                tiles.append(mgc.caption(img, f"{name.upper()} {b.times[k]:.2f}S {side} 3/4"))
        sheet = mgc.grid(tiles, 8)
        head = mgc.title(sheet.shape[1], f"ZAMBURAK CANNON - {name.upper()} ({b.anim}, {b.length:.2f} S): {moments} "
                                          f"MOMENTS, THE UNIT'S LEFT AND RIGHT, TEXTURED", back=(70, 40, 20))
        path = os.path.join(folder, f"{name}-textured.png")
        Image.fromarray(np.concatenate([head, sheet], 0)).save(path)
        out.append(path)
    return out


def round3_stills(folder, game, recipe, unit, gun_bytes, reload=True):
    """Stop 0 of the no-rammer reload (the user, 2026-11-26): its key poses as built and the swing from
    above (unless not `reload`); the plain linstock with its hot tip (holster, hand, on the vent, beside
    him for scale) and the props' sizes against him."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    u = unit
    v2 = V2(u)
    scene = mgc.Scene(game, recipe, u.camel, u.rider)
    pic = Picture(game, recipe, u.camel, u.rider, scene, u.d, gun_bytes, None)
    report = []
    ORANGE = (255, 120, 40)
    BLUE = (60, 200, 255)

    def items(P, R, fr):
        hang = rigid(P[u.camel.hang])
        fr = dict(fr, match=fr["linstock"] @ tr((0.0, u.src.linstock_length * u.d.ls, 0.0)))
        G = {u.d.NAMES.get(k, f"bone_{u.gun_name}").lower(): hang @ u.d.to_model(v) for k, v in fr.items()}
        G[pic.gun_rig.names[0].lower()] = hang
        out = pic.gun_fig.items(G) + scene.camel_fig.items(P)
        if R is not None:
            out += scene.rider_fig.items(R) + scene.hat_items(R)
        return out, G

    def flame(G):
        """The game's small fuse fire on bone_match as these pictures draw it: a yellow drop rising from
        the stick's tip (flat colour; a particle in game, not part of the model)."""
        el, fr_ = CannonDesign.FLAME
        drop = sphere(fr_)
        Rf = np.array([X, -Z, Y]).T                         # its long axis up
        dp = (drop["positions"] * np.array([1.0, 1.0, el / (2.0 * fr_)])) @ Rf.T + G["bone_match"][:3, 3] + 0.5 * el * Y
        return [(dp, drop["triangles"], None, None, (255, 200, 40))]

    def tile(it, az, el, text, span=3.0, centre=(0.0, 1.2, 0.6), marks=None, w=330, h=300):
        return mgc.caption(mgc.draw(it, w, h, az, el, span=span, centre=tuple(centre), marks=marks), text)

    def at(bb, t):
        k = min(len(bb.times) - 1, int(round(t * FPS)))
        return bb.camel[k], bb.rider[k], bb.gun[k]

    sheets = reload_sheets(v2, items, tile, at, report) if reload else []
    tiles = []
    Pm = u.camel.fix_hang(u.camel.pose(u.camel.base, 0.0))
    Rm = u.seated(Pm)
    Rm = u.hands(Rm, {"r": u.reins(Rm, Pm, "r"), "l": u.cascabel(Pm, u.gun_frames(u.limber))}, Built("s", "", [0, 1]), True)
    it, G = items(Pm, Rm, u.gun_frames(u.limber))
    tip = G["bone_match"][:3, 3]
    tiles.append(tile(it, 70.0, 12.0, "IN ITS HOLSTER: THE HOT RED TIP", span=1.3, centre=tip - np.array([0, 0.25, 0])))
    tiles.append(tile(it, 70.0, 12.0, "IN ITS HOLSTER: THE TIP CLOSE UP", span=0.45, centre=tip))
    d = v2.deployed()
    P, R, fr = at(d, 0.0)
    it, G = items(P, R, fr)
    tip = G["bone_match"][:3, 3]
    tiles.append(tile(it + flame(G), 150.0, 10.0, "IN HIS HAND (FLAME: THE GAME'S FUSE FIRE)", span=1.0,
                      centre=tip - np.array([0, 0.25, 0])))
    tiles.append(tile(it, -100.0, 5.0, "IN HIS HAND, THE WHOLE MAN FOR SCALE", span=2.6,
                      centre=R["bip01 spine1"][:3, 3] - np.array([0, 0.25, 0])))
    f = v2.fire()
    P, R, fr = at(f, 0.85)
    it, G = items(P, R, fr)
    tip, vent = G["bone_match"][:3, 3], G["bone_fuse"][:3, 3]
    report.append(f"fire 0.85 s: the tip {np.linalg.norm(tip - vent):.3f} from the vent")
    for az, el, name, fl, sp in ((30.0, 45.0, "FROM THE FRONT, ABOVE", False, 1.0),
                                 (30.0, 45.0, "CLOSE UP", False, 0.4),
                                 (30.0, 45.0, "WITH THE GAME'S FUSE FIRE", True, 1.0)):
        tiles.append(tile(it + (flame(G) if fl else []), az, el, f"FIRE 0.85 S: TIP ON THE VENT, {name}", span=sp,
                          centre=vent))
    tiles.append(tile(it, -70.0, 15.0, "FIRE 0.85 S: THE WHOLE MAN", span=2.6,
                      centre=0.5 * (vent + R["bip01 spine1"][:3, 3])))
    sheets.append(("z4-linstock.png", np.concatenate([
        mgc.title(4 * 330, f"THE LINSTOCK: A PLAIN WOODEN STICK {u.src.linstock_length:.2f} LONG, ITS TIP HOT RED, "
                           "TOUCHES THE VENT", back=(70, 40, 20)), mgc.grid(tiles, 4)], 0)))
    S = v2.S0
    height = float(S["bip01 head"][1, 3]) + 0.18
    lsp = recipe["linstock"]
    sizes = [("linstock", u.src.linstock_length), ("its thickness", 2 * lsp.get("radius", 0.018)),
             ("hot tip", lsp.get("hot", 0.06)), ("ball across", 2 * CannonDesign.BALL),
             ("charge bag", CannonDesign.CHARGE[1]), ("barrel", u.src.length * u.d.s / u.d.bind_scale)]
    report.append(f"sizes against the man ({height:.2f} game units tall): "
                  + ", ".join(f"{n} {v:.3f} ({100 * v / height:.1f}%)" for n, v in sizes))
    paths = []
    for name, sheet in sheets:
        p = os.path.join(folder, name)
        Image.fromarray(sheet).save(p)
        paths.append(p)
    return paths, report


def reload_sheets(v2, items, tile, at, report):
    """The no-rammer reload's key poses and its swing from above (round3_stills)."""
    BLUE, ORANGE = (60, 200, 255), (255, 120, 40)
    b = v2.reload()
    report.append(f"reload {RELOAD2:.2f} s: hands off their goals at most {b.reach:.3f}")

    keys = ((0.15, -55.0, "1 LINSTOCK STUCK IN THE GROUND"), (0.50, -55.0, "2 HE PUSHES THE GUN ROUND"),
            (0.85, -140.0, "3 IT SWINGS, HE STEPS ASIDE"), (1.20, -140.0, "4 CAUGHT: MUZZLE TO HIM"),
            (1.38, -140.0, "5 CHARGE FROM THE POUCH"), (1.53, -140.0, "6 CHARGE PUSHED IN BY HAND"),
            (1.83, -140.0, "7 BALL PUSHED IN BY HAND"), (2.04, -140.0, "8 HE PUSHES IT BACK ROUND"),
            (2.30, -140.0, "9 IT SWINGS BACK, HE STEPS BACK"), (2.64, -55.0, "10 SET AT ITS REST (+90)"),
            (2.86, -55.0, "11 HE TAKES THE LINSTOCK UP"), (RELOAD2, -55.0, "12 END: READY TO FIRE"))
    tiles = []
    for t, az, text in keys:
        P, R, fr = at(b, t)
        it, G = items(P, R, fr)
        mz_ = G["bone_launchpoint"][:3, 3]
        c = 0.5 * (mz_ + R["bip01 spine1"][:3, 3])
        tiles.append(tile(it, az, 15.0, f"{t:.2f} S {text}", span=3.0, centre=c,
                          marks=[(mz_, BLUE, 6), (G["bone_match"][:3, 3], ORANGE, 7)]))
    sheet1 = np.concatenate([mgc.title(4 * 330, f"RELOAD WITHOUT A RAMMER ({RELOAD2:.1f} S, ROF {RELOAD2 + FIRE:.1f} S): "
                                                "KEY POSES (BLUE DOT: MUZZLE, ORANGE STAR: THE MATCH)", back=(70, 40, 20)),
                             mgc.grid(tiles, 4)], 0)
    tiles = []
    for t, text in ((0.30, "AT REST +90"), (0.80, "THROUGH ITS BACK"), (1.25, "AT 270, MUZZLE AT HIM"),
                    (2.30, "SWINGING BACK")):
        P, R, fr = at(b, t)
        it, G = items(P, R, fr)
        tiles.append(tile(it, -90.0, 80.0, f"{t:.2f} S FROM ABOVE: {text}", span=3.4, centre=(0.0, 1.0, 0.5),
                          marks=[(G["bone_launchpoint"][:3, 3], BLUE, 6)]))
    sheet2 = np.concatenate([mgc.title(4 * 330, "FROM ABOVE: +90, PUSHED TO 105, FREE TO 255, PULLED TO 270, AND BACK. "
                                                "HE STEPS 0.26 FORWARD AND BACK", back=(70, 40, 20)),
                             mgc.grid(tiles, 4)], 0)
    return [("z3-reload-keys.png", sheet1), ("z3-reload-swing.png", sheet2)]


AIM_YAWS = tuple(float(y) for y in np.arange(ARC[0], ARC[1] + 1e-6, 2.0))   # the arc, every 2 degrees

GAITS = {  # today's footstep tags of the zamburak camel's gaits (its anim file)
    "Walk": (("FootstepLeft", "FRNT LT", 1.00), ("FootstepLeft", "BACK LT", 0.83),
             ("FootstepRight", "FRNT RT", 0.70), ("FootstepRight", "BACK RT", 0.50)),
    "Jog": (("FootstepLeft", "FRNT LT", 0.80), ("FootstepLeft", "BACK LT", 0.50),
            ("FootstepRight", "FRNT RT", 0.95), ("FootstepRight", "BACK RT", 0.75)),
    "Run": (("FootstepLeft", "FRNT LT", 0.73), ("FootstepLeft", "BACK LT", 0.50),
            ("FootstepRight", "FRNT RT", 1.00), ("FootstepRight", "BACK RT", 0.70)),
}
DECAL = ("\t\t<decal>\n\t\t\t<effecttype>default</effecttype>\n"
         "\t\t\t<texture isfakeshadow=\"1\">shadows_selections\\shadow_circle_128x128</texture>\n"
         "\t\t\t<selectedtexture>shadows_selections\\selection_oval_32x64</selectedtexture>\n"
         "\t\t\t<width>2.00</width>\n\t\t\t<height>3.00</height>\n\t\t\t<zoffset>-0.10</zoffset>\n\t\t</decal>\n")
# the anims of the unit's two modes: (anim name, our clips (variants), component)
ANIMS = (("Idle", ("idle",)), ("Walk", ("walk",)), ("Jog", ("jog",)), ("Run", ("run",)),
         ("Bored", ("bored_a", "bored_b", "bored_c")), ("Cheer", ("cheer_a", "cheer_b", "cheer_c", "cheer_d")),
         ("Bombard_unlimber", ("unlimber",)), ("Bombard_limber", ("limber",)),
         ("Bombard_ranged_idle", ("deployed",)), ("Bombard_bored", ("deployed",)), ("Bombard_aim", ("deployed",)),
         ("Bombard_ranged_attack", ("fire",)), ("Bombard_reload", ("reload",)), ("Bombard_death", ("death",)))


def anim_files(recipe, built, rider_head):
    """{file name: text} of the unit's three anim files (the camel's, the gun's, the rider's): one unit
    with both modes. Limbered: idle, gaits, bored, cheer, the stock camel deaths on the dead model (the
    cannon built in; the three that keep it out of the ground). Unlimbered: the unlimber and limber,
    the idle at the gun, the shot (its attack, sound and smoke at SHOT), the reload, the death.
    `rider_head`: today's rider anim file up to its first <anim> (his model by rank, his hats)."""
    folder, name = recipe["folder"], recipe["name"]
    gun_name = f"{name}_gun"

    def anim(an, files, comp="ModelComp", tags=""):
        out = []
        for f in files:
            out.append(f"\t<anim>\n\t\t{an}\n\t\t<assetreference type=\"GrannyAnim\">\n\t\t\t<file>{f}</file>\n"
                       f"{tags}\t\t</assetreference>\n\t\t<component>{comp}</component>\n\t</anim>\n")
        return "".join(out)

    def ours(kind, clip):
        b = built[clip]
        nm = {"camel": b.camel_name, "gun": b.gun_name, "rider": b.rider_name}[kind]
        if nm is None:                       # today's rider clip, unchanged
            return b.stock_rider
        return f"{folder}\\{nm}"
    head = ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!-- Wars of Liberty's zamburak cannon (MEZamburak): the "
            "zamburak's camel without its swivel gun, a bronze cannon on a swivel on its withers, its rider, who "
            "limbers and unlimbers it. Made with aoe3-blender-tools tools/make_zamburak.py. -->\n")
    shot = SHOT / FIRE
    fire_tags = (f"\t\t\t<tag type=\"Attack\">{shot:.2f}</tag>\n"
                 f"\t\t\t<tag type=\"SpecificSoundSet\" checkvisible=\"1\" set=\"FalconetShoot\">{shot:.2f}</tag>\n"
                 f"\t\t\t<tag type=\"Particles\" particlename=\"smallcannonmuzzle\">{shot:.2f}</tag>\n")
    camel = [head, "<animfile>\n"]
    camel += [f"\t<definebone>HS Bone Hoof {w}</definebone>\n" for w in ("Frnt Lt", "Frnt Rt", "Back Lt", "Back Rt")]
    camel += ["\t<definebone>bone_launchpoint</definebone>\n\t<definebone>bone_muzzle</definebone>\n",
              f"\t<attachment>\n\t\trider\n\t\t<include>{folder}\\{name}_rider.xml</include>\n\t</attachment>\n",
              f"\t<attachment>\n\t\tcannon\n\t\t<include>{folder}\\{name}_gun.xml</include>\n\t</attachment>\n",
              f"\t<component>\n\t\tModelComp\n\t\t<assetreference type=\"GrannyModel\">\n\t\t\t<file>{folder}\\{name}_camel"
              f"</file>\n\t\t</assetreference>\n{DECAL}"
              "\t\t<attach a=\"rider\" frombone=\"hotspot\" tobone=\"ATTACHPOINT\" syncanims=\"1\"/>\n"
              f"\t\t<attach a=\"cannon\" frombone=\"bone_{gun_name}\" tobone=\"ATTACHPOINT\" syncanims=\"1\"/>\n"
              "\t</component>\n",
              f"\t<component>\n\t\tDeadComp\n\t\t<assetreference type=\"GrannyModel\">\n\t\t\t<file>{folder}\\{name}"
              f"_camel_dead</file>\n\t\t</assetreference>\n{DECAL}"
              "\t\t<attach a=\"rider\" frombone=\"hotspot\" tobone=\"ATTACHPOINT\" syncanims=\"1\"/>\n\t</component>\n"]
    gun = [head, "<animfile>\n",
           f"\t<component>\n\t\tModelComp\n\t\t<assetreference type=\"GrannyModel\">\n\t\t\t<file>{folder}\\{gun_name}"
           "</file>\n\t\t</assetreference>\n\t</component>\n"]
    rider = [rider_head]
    for an, clips in ANIMS:
        gait = "".join(f"\t\t\t<tag type=\"{k}\" footprinttype=\"Horse\" footprintbone=\"HS BONE HOOF {b_}\">{v:.2f}</tag>\n"
                       for k, b_, v in GAITS.get(an, ()))
        camel.append(anim(an, [ours("camel", c) for c in clips], tags=gait + (fire_tags if an == "Bombard_ranged_attack"
                                                                                else "")))
        gun.append(anim(an, [ours("gun", c) for c in clips]))
        rider.append(anim(an, [ours("rider", c) for c in clips]))
    impact = "\t\t\t<tag type=\"SpecificSoundSet\" checkvisible=\"1\" set=\"RagdollImpact\">0.62</tag>\n"
    melee = [d for d in DEATHS_KEPT if d[0].startswith("death_melee")]
    havoc = [d for d in DEATHS_KEPT if d[0].startswith("death_havoc")]
    for an, group in (("Death_by_melee", melee), ("Death_by_range", melee), ("Death_by_havoc", havoc)):
        camel.append(anim(an, [c for _n, c, _r in group], "DeadComp", impact if an != "Death_by_havoc" else ""))
        rider.append(anim(an, [r for _n, _c, r in group]))
    camel.append("</animfile>\n")
    gun.append("</animfile>\n")
    rider.append("</animfile>\n")
    return {f"{name}.xml": "".join(camel), f"{name}_gun.xml": "".join(gun), f"{name}_rider.xml": "".join(rider)}


def rider_head(game_folder, recipe):
    """Today's rider anim file up to its first <anim>: his model by rank and his hats (kept as they are);
    our anims follow it."""
    path = os.path.join(game_folder, "art", recipe["rider_xml"])
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    i = text.find("\t<anim>")
    if i < 0:
        i = text.find("<anim>")
    return "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + text[:i].replace("<!-- converted from XMB to XML -->\n", "")


def aim_table(unit, built):
    """The bytes of the unlimbered unit's aim table for turretArc (version 2, little endian, as
    make_gun_camel.aim_table writes it): "UHCA", 2, the gun's yaw bone and the camel's turret bone
    (32 B each), the pivot and the muzzle (the gun at its rest yaw, the camel lying as the fire clip
    has it, the camel's model space), the rest yaw, the yaws (+30..+150 every 2), the rider's bones
    that move with the yaw, then per clip (the deployed idle and the fire, as their rider animations
    are named) its length, frame count and, per frame, per yaw, per bone, the position and rotation
    local to its parent. He stays at his rest station (no step): his arm reaches the vent of the
    turned gun and his head follows it. No BAND or SETL (a gunner who steps only)."""
    import struct as st
    v2 = V2(unit)
    rider, cam, d = unit.rider, unit.camel, unit.d
    names = rider.rig.names
    rows = {"deployed": v2.deployed, "fire": v2.fire}
    tables = []
    for key, make in rows.items():
        b0 = built[key]
        length = float(b0.times[-1])
        count = max(2, int(round(length * mgc.AIM_TABLE_FPS)) + 1)
        idx = [int(round(k * (len(b0.times) - 1) / (count - 1))) for k in range(count)]
        per_yaw = []
        for yaw in AIM_YAWS:
            b = make(yaw)
            per_yaw.append([rider.to_local(b.rider[i], rigid(b.camel[i][cam.rider_bone])) for i in idx])
        frames = [[per_yaw[y][f] for y in range(len(AIM_YAWS))] for f in range(count)]
        tables.append((b0.rider_name, length, count, frames))
    zero = AIM_YAWS.index(REST_YAW)
    moving = set()
    for _n, _l, _c, frames in tables:
        for row in frames:
            for loc in row:
                for k, (p, q) in enumerate(loc):
                    p0, q0 = row[zero][k]
                    if np.abs(np.asarray(p) - np.asarray(p0)).max() > 1e-5 or min(
                            np.abs(np.asarray(q) - np.asarray(q0)).max(), np.abs(np.asarray(q) + np.asarray(q0)).max()) > 1e-5:
                        moving.add(k)
    bones = sorted(moving)

    def name32(s, n=32):
        raw = s.encode("ascii")[: n - 1]
        return raw + b"\0" * (n - len(raw))
    fire = built["fire"]
    Cf = unit.C(fire.camel[0])
    rest = unit.gun_frames({"yaw": REST_YAW})
    pivot = point(Cf, d.pivot)
    muzzle = point(Cf, rest["muzzle"][:3, 3])
    out = [b"UHCA", st.pack("<I", 2), name32(d.NAMES["yaw"]), name32("bone_turret"),
           st.pack("<3f", *[float(v) for v in pivot]), st.pack("<3f", *[float(v) for v in muzzle]),
           st.pack("<f", REST_YAW), st.pack("<I", len(AIM_YAWS)), st.pack(f"<{len(AIM_YAWS)}f", *AIM_YAWS),
           st.pack("<I", len(bones))]
    out += [name32(names[k]) for k in bones]
    out.append(st.pack("<I", len(tables)))
    for name, length, count, frames in tables:
        out += [name32(name, 64), st.pack("<fI", length, count)]
        out += [st.pack("<7f", *[float(v) for v in loc[k][0]], *[float(v) for v in loc[k][1]])
                for row in frames for loc in row for k in bones]
    return b"".join(out), [names[k] for k in bones], [(n, c) for n, _l, c, _f in tables]


def posed_gun_bytes(design, name, source_data, state):
    """The gun model with every part moved to `state` (its bones at that state, rest = the state):
    the cannon as the dead model carries it."""
    rest, fr = design.rest(), design.frames(state)
    keep_rest = design.rest
    keep_parts = design.parts

    def parts():
        out = {}
        for key, (p, bone) in keep_parts().items():
            m = fr[bone] @ np.linalg.inv(rest[bone])
            q = dict(p)
            q["positions"] = apply(m, p["positions"])
            q["normals"] = p["normals"] @ m[:3, :3].T
            q["tangents"] = p["tangents"] @ m[:3, :3].T
            out[key] = (q, bone)
        return out
    design.rest = lambda: dict(fr)
    design.parts = parts
    try:
        return design.model_bytes(name, source_data)
    finally:
        design.rest, design.parts = keep_rest, keep_parts


# --------------------------------------------------------------------------------------------------
# The work


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--recipe")
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--no-verify", action="store_true", help="skip the game runtime's checks")
    ap.add_argument("--sheet", help="the model sheet (PNG)")
    ap.add_argument("--barrel-sheet", help="the barrel against the source's (PNG)")
    ap.add_argument("--limber-options", help="a sheet of limber poses to choose from (PNG)")
    ap.add_argument("--sizes", help="a sheet of the cannon at several sizes (PNG)")
    ap.add_argument("--size-list", default="1.0,0.75,0.6,0.5", help="the sizes the sizes sheet shows")
    ap.add_argument("--scale", type=float, help="the cannon's size against the source's (default: the recipe's)")
    ap.add_argument("--clips", help="also make every clip of the script and write the check_anim jobs (the new "
                                    "clips, today's as their baseline, the deaths) into this folder")
    ap.add_argument("--textured", help="with --clips: a folder for textured sheets of every clip (8 moments, the "
                                       "unit's left and right)")
    ap.add_argument("--pack", action="store_true", help="with --clips: also the game's files beside them (the camel "
                                                        "clips' tag files, the turretArc aim table, the three anim files)")
    ap.add_argument("--round2-stills", help="a folder for the stills of round 2 (the short linstock, the gun at +90, "
                                            "the reload's key poses)")
    ap.add_argument("--linstock-stills", help="a folder for the linstock's stills only (stop 0: holster, hand, "
                                              "vent, scale)")
    ap.add_argument("--round3-stills", help="a folder for stop 0 of the no-rammer reload (its key poses, the swing "
                                            "from above, the linstock's burning tip, the props' sizes)")
    args = ap.parse_args(argv)
    try:
        for p in (args.out, args.sheet, args.barrel_sheet, args.limber_options, args.sizes, args.clips, args.textured,
                  args.round2_stills, args.round3_stills, args.linstock_stills):
            if p:
                refuse_steam(p)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    recipe = copy.deepcopy(DEFAULT_RECIPE)
    if args.recipe:
        with open(args.recipe, encoding="utf-8") as f:
            extra = json.load(f)
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(recipe.get(k), dict):
                recipe[k].update(v)
            else:
                recipe[k] = v
    if args.scale:
        recipe["barrel"]["scale"] = args.scale
    work = tempfile.mkdtemp(prefix="zamburak_")
    failed = False
    report = []
    try:
        game = mgc.Game(args.game, args.granny_helper, work)
        runtime = None
        if not args.no_verify:
            import recompress_models as rm
            runtime = rm.Runtime(args.granny_helper, os.path.join(args.game, "granny2.dll"), work)
        folder = os.path.join(args.out, "art", recipe["folder"])
        os.makedirs(folder, exist_ok=True)
        cut, info = cut_camel(game, recipe)
        report.append(f"camel {recipe['camel']['model']}: {info['triangles']} triangles, {info['cut']} cut "
                      f"(swivel gun pieces {info['pieces']}: (triangles, is the post)); old post top {info['post_top']}")
        src = Source(game, recipe)
        report.append(f"barrel {recipe['barrel']['model']} {recipe['barrel']['bone']}: {len(src.barrel['triangles'])} "
                      f"triangles, {src.source_length:.3f} long -> {src.length:.3f} ({recipe['barrel']['length']:.3f}); "
                      f"chase {src.swell[0]:.3f} -> {src.swell[1]:.3f}, the muzzle's swell kept; widest radius "
                      f"{src.radius:.3f}; patches " + ", ".join(f"{k} {np.round(v[0], 3).tolist()}"
                                                               for k, v in src.patches.items()))
        camel0 = mgc.Camel(game, recipe["camel"], cut)
        y = saddle_height(cut, recipe["camel"]["mesh"], 0.0, recipe["swivel"]["z"])
        design = CannonDesign(src, camel0.hang_bind, y, recipe)
        report.append(f"swivel: saddle at {np.round(design.saddle, 3).tolist()}, pivot {np.round(design.pivot, 3).tolist()}, "
                      f"trunnions {np.round(design.trunnion, 3).tolist()}, design scale {design.s:.3f}; muzzle (level) "
                      f"{np.round(design.bpoint(src.muzzle), 3).tolist()}")
        cut = launch_bones(cut, camel0, design, recipe)
        camel = mgc.Camel(game, recipe["camel"], cut)
        gun = design.model_bytes(f"{recipe['name']}_gun", src.data)
        files = {f"{recipe['name']}_camel": cut, f"{recipe['name']}_gun": gun}
        for fname, data in files.items():
            with open(os.path.join(folder, fname + ".gr2"), "wb") as f:
                f.write(data)
            if runtime is not None:
                crc, read, packed = mgc.runtime_check(data, runtime, fname[-24:].replace("_", ""))
                ok = crc and read
                report.append(f"runtime {fname}.gr2 {len(data)} B: crc {crc}, read {read}, oodle1 {packed} B"
                              + ("" if ok else "  FAIL"))
                failed |= not ok
        if args.round3_stills or args.linstock_stills:
            rider = mgc.Rider(game, recipe["rider"])
            foot_rig = Rig.of(gr2.load(game.granny(mgc.FOOT_MODEL)).root())
            unit3 = ZUnit(game, recipe, camel, rider, design, foot_rig)
            paths3, rep3 = round3_stills(args.round3_stills or args.linstock_stills, game, recipe, unit3, gun,
                                         reload=bool(args.round3_stills))
            report += rep3
            for p in paths3:
                print(p)
        if args.round2_stills:
            rider = mgc.Rider(game, recipe["rider"])
            foot_rig = Rig.of(gr2.load(game.granny(mgc.FOOT_MODEL)).root())
            unit2 = ZUnit(game, recipe, camel, rider, design, foot_rig)
            paths2, rep2 = round2_stills(args.round2_stills, game, recipe, unit2, gun)
            report += rep2
            for p in paths2:
                print(p)
        if args.clips:
            rider = mgc.Rider(game, recipe["rider"])
            foot_rig = Rig.of(gr2.load(game.granny(mgc.FOOT_MODEL)).root())
            unit_ = ZUnit(game, recipe, camel, rider, design, foot_rig)
            built = unit_.build_all()
            clip_files = {}
            for name, b in built.items():
                unit_.write(b)
                if b.camel_bytes is not None:
                    clip_files[b.camel_name] = b.camel_bytes
                clip_files[b.gun_name] = b.gun_bytes
                if b.rider_bytes is not None:
                    clip_files[b.rider_name] = b.rider_bytes
                report.append(f"clip {name:9} ({b.anim}) {b.length:.3f} s, {len(b.times)} frames; hands off their "
                              f"targets at most {b.reach:.3f}" + (f"; the camel's neck bent down up to "
                                                                  f"{b.head_bend:.0f} deg to keep its head off the barrel"
                                                                  if getattr(b, "head_bend", 0.0) else "") +
                              (f"; a hand moved out from the breech up to {b.arm_moved:.2f}" if getattr(b, "arm_moved", 0.0)
                               else "") +
                              (f"; his chest turned right / leaned back up to {b.chest_back:.0f} deg to keep it off the "
                               f"breech" if getattr(b, "chest_back", 0.0) else ""))
            # the limbered unit's dead model: the camel with the cannon (in its limber pose, the
            # linstock in its ring) built in, playing today's camel deaths
            lim_gun = posed_gun_bytes(design, f"{recipe['name']}_gun", src.data, dict(recipe["limber"]))
            files[f"{recipe['name']}_camel_dead"] = mgc.dead_model(cut, lim_gun, camel.hang_bind,
                                                                    recipe["camel"]["mount_bone"])
            for fname, data in list(clip_files.items()) + [(f"{recipe['name']}_camel_dead",
                                                           files[f"{recipe['name']}_camel_dead"])]:
                with open(os.path.join(folder, fname + ".gr2"), "wb") as f:
                    f.write(data)
                if runtime is not None:
                    crc, read, packed = mgc.runtime_check(data, runtime, fname[-24:].replace("_", ""))
                    if not (crc and read):
                        report.append(f"runtime {fname}.gr2: crc {crc}, read {read}  FAIL")
                        failed = True
            if runtime is not None:
                report.append(f"runtime: {len(clip_files) + 1} clip and model files checked")
            fr_lim = unit_.gun_frames(dict(recipe["limber"]))
            report.append("barrel to the camel in the clips written (limbered, pose B), least gap: " +
                          ", ".join(f"{n} {min(unit_.barrel_gap(P, fr_lim) for P in built[n].camel):+.3f}"
                                    for n, *_x in LIMBERED))
            paths = write_checks(folder, args.clips, game, unit_, built,
                                 os.path.join(folder, f"{recipe['name']}_gun.gr2").replace("\\", "/"),
                                 os.path.join(folder, f"{recipe['name']}_camel.gr2").replace("\\", "/"),
                                 os.path.join(folder, f"{recipe['name']}_camel_dead.gr2").replace("\\", "/"), recipe)
            report.append("check jobs: " + ", ".join(paths.values()))
            if args.pack:
                # the game's files beside the models and clips: the camel clips' tag files, the aim
                # table, the three anim files
                template = game._g.raw(mgc.ZAMB + "zamburak_camel_idle00.gr2.precomp", "")
                n_tags = 0
                for b in built.values():
                    if b.camel_bytes is None:
                        continue
                    frames = b.camel

                    def pose_at(t, b=b, frames=frames):
                        return frames[min(len(frames) - 1, int(round(t / max(b.length, 1e-9) * (len(frames) - 1))))]
                    with open(os.path.join(folder, b.camel_name + ".gr2.precomp"), "wb") as f:
                        f.write(mgc.camel_precomp(camel, template, b.length, pose_at))
                    n_tags += 1
                data, bones, tabs = aim_table(unit_, built)
                aim_path = os.path.join(folder, f"{recipe['name']}.aim")
                with open(aim_path, "wb") as f:
                    f.write(data)
                for fname, text in anim_files(recipe, built, rider_head(args.game, recipe)).items():
                    with open(os.path.join(folder, fname), "w", encoding="utf-8", newline="\r\n") as f:
                        f.write(text)
                report.append(f"pack: {n_tags} tag files; aim table {os.path.basename(aim_path)} {len(data)} B, "
                              f"yaws {AIM_YAWS[0]:.0f}..{AIM_YAWS[-1]:.0f} every 2, rest {REST_YAW:.0f}, "
                              f"{len(bones)} rider bones, clips " + ", ".join(f"{n} ({c} frames)" for n, c in tabs)
                              + "; anim files written")
            if args.textured:
                for p in textured_sheets(args.textured, game, recipe, unit_, built, gun):
                    print(p)
        with open(os.path.join(args.out, f"{recipe['name']}-report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print("\n".join(report))
        if args.sheet or args.limber_options or args.sizes:
            rider = mgc.Rider(game, recipe["rider"])
            scene = mgc.Scene(game, recipe, camel, rider)
            gunner = Gunner(game, recipe["gunner"]) if recipe.get("gunner") else None
            pic = Picture(game, recipe, camel, rider, scene, design, gun, gunner)
            if args.sheet:
                try:
                    today = today_items(game, recipe)
                    midfa = midfa_items(game, recipe)
                except (FileNotFoundError, gr2.Gr2Error, KeyError):
                    today = midfa = None
                foot_rig = Rig.of(gr2.load(game.granny(mgc.FOOT_MODEL)).root())
                model_sheet(args.sheet, pic, recipe, today, midfa, foot_rig)
                print(args.sheet)
            if args.limber_options:
                limber_options(args.limber_options, pic, recipe)
                print(args.limber_options)
            if args.sizes:
                sizes_sheet(args.sizes, game, recipe, camel, rider, scene, src, gunner,
                            [float(x) for x in args.size_list.split(",")])
                print(args.sizes)
        if args.barrel_sheet:
            barrel_sheet(args.barrel_sheet, game, src, recipe)
            print(args.barrel_sheet)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failed else 0


def sizes_sheet(path, game, recipe, camel, rider, scene, src, gunner, scales):
    """The cannon at several sizes (a share of the source's), limbered and unlimbered, from the left."""
    from PIL import Image
    w, h = 300, 270
    rows = []
    for sc in scales:
        r = copy.deepcopy(recipe)
        r["barrel"]["scale"] = sc
        y = saddle_height(camel.cut, r["camel"]["mesh"], 0.0, r["swivel"]["z"])
        d = CannonDesign(src, camel.hang_bind, y, r)
        pic = Picture(game, r, camel, rider, scene, d, d.model_bytes(f"{r['name']}_gun", src.data), gunner)
        lim = pic.limbered()[0]
        dep = pic.deployed()[0]
        tiles = [mgc.caption(mgc.draw(lim, w, h, -90.0, 6.0, span=4.2, centre=(0.0, 1.7, 0.45)), "LIMBERED LEFT"),
                 mgc.caption(mgc.draw(lim, w, h, -40.0, 16.0, span=4.2, centre=(0.0, 1.7, 0.45)), "LIMBERED FRONT 3/4"),
                 mgc.caption(mgc.draw(dep, w, h, -90.0, 6.0, span=4.2, centre=(-0.3, 1.2, 0.45)), "UNLIMBERED LEFT"),
                 mgc.caption(mgc.draw(dep, w, h, -140.0, 16.0, span=4.2, centre=(-0.3, 1.2, 0.45)),
                             "UNLIMBERED BACK 3/4")]
        length = src.length * sc
        rows.append(np.concatenate([mgc.title(4 * w, f"CANNON AT {sc:.2f} OF THE MIDFA'S SIZE: BARREL {length:.2f} LONG, "
                                                     f"{2 * src.radius * sc:.2f} WIDE AT THE MUZZLE (GAME UNITS)", scale=1),
                                    mgc.grid(tiles, 4)], 0))
    out = [mgc.title(4 * w, "ZAMBURAK CANNON - SIZES (THE BARREL AT 2/3 OF THE MIDFA'S LENGTH IN EVERY ROW)",
                     back=(70, 40, 20))] + rows
    Image.fromarray(np.concatenate(out, 0)).save(path)


# the limber poses offered (2026-11-26): over the neck the camel's own clips swing its head into
# the barrel (A would need the head held lower in every clip, as the gatling camel's jog and run);
# turned 30 degrees or more off the neck it clears the camel in its idle, walk, jog and run
LIMBER_OPTIONS = [("A: OVER THE NECK, 20 DOWN", {"pitch": 20.0, "yaw": 0.0}),
                  ("B: 20 DOWN, 30 OFF THE NECK (RIGHT)", {"pitch": 20.0, "yaw": 30.0}),
                  ("C: 30 DOWN, 45 OFF THE NECK (RIGHT)", {"pitch": 30.0, "yaw": 45.0}),
                  ("D: 40 DOWN, 60 OFF THE NECK (RIGHT)", {"pitch": 40.0, "yaw": 60.0})]


MOVE_CLIPS = [("idle", mgc.ZAMB + "zamburak_camel_idle00"), ("walk", mgc.ZAMB + "zamburak_camel_walk00"),
              ("jog", mgc.ZAMB + "zamburak_camel_jog"), ("run", mgc.LIB + "cavalry\\horse_gallop")]


def used_vertices(cam):
    """The indices (into Camel.mesh_points) of the vertices some triangle uses: a cut leaves the
    cut pieces' vertices in the vertex buffer."""
    if getattr(cam, "_used", None) is None:
        read = gr2_mesh.read(cam.cut)
        idx, base = [], 0
        for m in read["meshes"]:
            idx.append(np.unique(np.asarray(m["triangles"], np.int64)) + base)
            base += len(m["file_positions"])
        cam._used = np.concatenate(idx)
    return cam._used


def barrel_clearance(pic, state, samples=12, clips=None):
    """The smallest gap (game units) between the barrel (its axis from breech to muzzle, less its
    radius) and the camel's body, the parts within 0.35 of the swivel's pivot left out (the saddle
    it stands on), over the camel's idle, walk, jog and run: [(clip, time, gap)], worst first."""
    d, cam = pic.design, pic.camel
    out = []
    for name, rel in (clips or MOVE_CLIPS):
        anim = cam.anim(rel)
        length = anim.duration
        worst = (None, 1e9, None, None)
        for t in np.linspace(0.0, length, samples, endpoint=False):
            # the rider's bone (the gun's hang) where the idle has it on the chest, as the clips the
            # tool writes keep it (make_gun_camel.Camel.fix_hang): the stock clips move it
            P = cam.fix_hang(cam.pose(anim, float(t)))
            fr = d.frames(state)
            C = rigid(P[cam.hang]) @ d.S
            to_w = C @ fr["cannon"] @ tr(-d.trunnion)
            a = point(to_w, d.bpoint(d.src.breech))
            b = point(to_w, d.bpoint(d.src.muzzle))
            pivot = point(C, d.pivot)
            pts = cam.mesh_points(P)[used_vertices(cam)]          # not the cut gun's left-over vertices
            pts = pts[np.linalg.norm(pts - pivot, axis=1) > 0.35]
            ab = b - a
            u = np.clip(((pts - a) @ ab) / (ab @ ab), 0.0, 1.0)
            dist = np.linalg.norm(pts - (a + u[:, None] * ab), axis=1) - d.radius / d.bind_scale
            k = int(np.argmin(dist))
            if dist[k] < worst[1]:
                worst = (float(t), float(dist[k]), float(u[k]), np.round(pts[k] - pivot, 2))
        out.append((name,) + worst)
    return sorted(out, key=lambda x: x[2])


def rider_clearance(pic, state):
    """The smallest gap between the barrel and the seated rider (his idle, first frame)."""
    d, cam = pic.design, pic.camel
    P = cam.fix_hang(cam.pose(cam.base, 0.0))
    R = pic.rider.seated(pic.rider.idle, 0.0, P[cam.rider_bone], square=True)
    pts = np.concatenate([it[0] for it in pic.scene.rider_fig.items(R)])
    C = rigid(P[cam.hang]) @ d.S
    to_w = C @ d.frames(state)["cannon"] @ tr(-d.trunnion)
    a, b = point(to_w, d.bpoint(d.src.breech)), point(to_w, d.bpoint(d.src.muzzle))
    ab = b - a
    u = np.clip(((pts - a) @ ab) / (ab @ ab), 0.0, 1.0)
    return float((np.linalg.norm(pts - (a + u[:, None] * ab), axis=1) - d.radius / d.bind_scale).min())


def limber_options(path, pic, recipe):
    from PIL import Image
    w, h = 300, 270
    rows = []
    for text, state in LIMBER_OPTIONS:
        gaps = barrel_clearance(pic, state)
        order = [c[0] for c in MOVE_CLIPS]
        text = (text + " - GAP TO THE CAMEL (- IS INSIDE): " +
                ", ".join(f"{n} {g:+.2f}" for n, _t, g, *_r in sorted(gaps, key=lambda x: order.index(x[0]))) +
                f". TO THE RIDER AT REST {rider_clearance(pic, state):+.2f}")
        items, _P, _G = pic.limbered(state)
        rows.append(mgc.grid([mgc.caption(mgc.draw(items, w, h, az, el, span=4.2, centre=(0.0, 1.7, 0.45)), f"{name}")
                              for name, az, el in (("FRONT 3/4", -40.0, 16.0), ("LEFT", -90.0, 6.0),
                                                   ("RIGHT 3/4", 50.0, 16.0), ("ABOVE", -90.0, 75.0))], 4))
        rows[-1] = np.concatenate([mgc.title(4 * w, text, scale=1), rows[-1]], 0)
    out = [mgc.title(4 * w, "ZAMBURAK CANNON - LIMBER POSES TO CHOOSE FROM", back=(70, 40, 20))] + rows
    Image.fromarray(np.concatenate(out, 0)).save(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
