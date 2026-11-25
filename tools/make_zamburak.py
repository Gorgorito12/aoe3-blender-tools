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
    "linstock": {"model": MIDFA + "Midfa_stripped", "mesh": "screw_pole"},
    # the artillerist on foot as the previews show him (a mesh of the field gun's model)
    "gunner": {"model": MIDFA + "Midfa_stripped", "meshes": ["gunner"]},
    # the swivel: its pivot on the camel's centre line (x = 0) this far along the body (design
    # units, +z ahead) and this high above the saddle's surface there; the fork's prongs hold the
    # trunnions this high above the pivot
    "swivel": {"z": 0.62, "socket": 0.06, "fork": 0.0},
    # limbered: the barrel pitched down this many degrees (positive: muzzle down) and turned this
    # many about the post (positive: toward the unit's right), so it clears the neck
    "limber": {"pitch": 20.0, "yaw": 30.0},
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
        # the linstock
        lspec = recipe["linstock"]
        ldata = game.granny(lspec["model"]) if lspec["model"] != spec["model"] else self.data
        lpart = next(p for p in gr2_parts.mesh_parts(ldata) if p["name"] == lspec["mesh"])
        lp = lpart["positions"]
        foot, top = lp[np.argmin(lp[:, 1])], lp[np.argmax(lp[:, 1])]
        lax = unit(top - foot)
        lside = unit(np.cross(lax, Z))
        lfwd = np.cross(lside, lax)
        Rl = np.array([lside, lax, lfwd])
        base = np.array([lp[:, 0].mean(), lp[:, 1].min(), lp[:, 2].mean()])
        self.linstock = {"positions": (lp - base) @ Rl.T, "normals": lpart["normals"] @ Rl.T,
                         "tangents": lpart["tangents"] @ Rl.T, "uvs": lpart["uvs"], "triangles": lpart["triangles"],
                         "materials": [lpart["materials"][i] for i in lpart["tri_material"]]}
        self.linstock_length = float(np.linalg.norm(top - foot))
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

    BONES = ("root", "post", "yaw", "cannon", "fuse", "muzzle", "linstock")
    PARENT = {"root": None, "post": "root", "yaw": "post", "cannon": "yaw", "fuse": "cannon", "muzzle": "cannon",
              "linstock": "root"}
    NAMES = {"post": "bone_post", "yaw": "bone_yaw", "cannon": "bone_cannon", "fuse": "bone_fuse",
             "muzzle": "bone_launchpoint", "linstock": "bone_linstock"}

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
        return out

    def linstock_rest(self):
        """The linstock's frame at rest (design space): upright in a ring on the right of the
        socket, its foot by the saddle's flank, leaning back a little."""
        foot = self.saddle + np.array([0.16, -0.30, -0.05])
        R = axis_matrix(X, -12.0)
        m = rot4(R)
        m[:3, 3] = foot
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
        yaw = state.get("yaw", 0.0)
        if yaw:
            turn = tr(self.pivot) @ rot4(axis_matrix(Y, yaw)) @ tr(-self.pivot)
            for k in ("yaw", "cannon", "fuse", "muzzle"):
                out[k] = turn @ out[k]
        ls = state.get("linstock")
        out["linstock"] = rest["linstock"] if ls is None else ls
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
    args = ap.parse_args(argv)
    try:
        for p in (args.out, args.sheet, args.barrel_sheet, args.limber_options, args.sizes):
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


def barrel_clearance(pic, state, samples=12):
    """The smallest gap (game units) between the barrel (its axis from breech to muzzle, less its
    radius) and the camel's body, the parts within 0.35 of the swivel's pivot left out (the saddle
    it stands on), over the camel's idle, walk, jog and run: [(clip, time, gap)], worst first."""
    d, cam = pic.design, pic.camel
    out = []
    for name, rel in MOVE_CLIPS:
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
