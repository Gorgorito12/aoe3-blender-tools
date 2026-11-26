# SPDX-License-Identifier: GPL-3.0-or-later
"""A camel gun from two of the game's models: a camel unit's body with its own swivel gun cut
out, and the rotating barrels, the casing with its trunnion and the crank of a wheeled gun (by
default the zamburak's camel and the stock Gatling gun), placed where the swivel gun was and
animated with a rider who cranks it. Recipe-driven like make_dismount.py.

    venv\\Scripts\\python -I tools/make_gun_camel.py --game <game copy> --out <folder>
        [--recipe <recipe.json>] [--scales 0.55,0.7] [--granny-helper <exe>] [--no-verify]
        [--sheet <png>] [--gifs <folder>] [--gif-fps 15] [--gaze <png>]
        [--aim-sheet <png>] [--aim-gifs <folder>]

`--aim-sheet` and `--aim-gifs` preview the gun turned on its mount (a yaw about the post's axis, so
the casing stays seated on the post, -90 to 90 degrees) with the camel still: A's rider keeps his
chest square behind the grips, leans in, looks along the barrels and keeps both hands on the gun
(past AIM_SWAP his left hand moves to the breech box's side, or to the reins); B is shown two
ways: the gunner staying in the saddle of the lying camel (A's rider), and the gunner on foot
stepping round the mount (Traverse: a station per yaw, feet planted, one foot stepping at a time).
What a game key that aims the gun, not the camel, would show.

What it writes below --out (`art\\<recipe "folder">\\`):
- `<camel>_nogun.gr2`: the camel's body without the swivel gun's triangles (`cut`: the pieces bound to
  the mount bone beyond `x_below` and above `y_above`; `keep_post` keeps its forked post as the new
  gun's mount). Nothing else of the model changes (aoe3game/gr2_parts.cut_triangles).
- `<name>_gun_<variant>_<scale>.gr2`: the gun for each variant and scale: one rigid mesh per part
  (casing with its trunnion, barrel cluster, crank, magazine), each on its own bone, the gun's own
  texture and shader settings (aoe3game/gr2_parts.rigid_model). Its space is the mount bone's (the
  anim file hangs it with `frombone` the gun's root and `tobone` the mount bone, so it follows
  that bone exactly as the swivel gun's triangles did). Variant B mirrors the gun so that its crank
  faces out, where the gunner on foot stands.
- the clips (below), each as long as the camel's clip of the same anim name, so `syncanims` keeps
  camel, gun and rider together; `<name>-anims.xml` with the anim file blocks to paste;
  `<name>-report.txt` with what was cut and placed and the checks.

The variants (`variants` of the recipe):
- A, from the saddle: the camel plays its own clips (idle, walk, jog, run, ranged attack, reload),
  its head and neck lowered out of the line of fire at the gun, in the jog and the run (`lower`);
  the rider sits squared (`Rider.square`: the stock rider's turn to his right undone, back nearly
  upright, shoulders and head level) and looks where he should (`Rider.look`: ahead on the move,
  along the barrels at the gun, at the magazine in a reload); on the move his left palm rests on
  the breech box and his right fist on the reins; at the gun his right hand turns the crank (two-bone IK on the handle at every frame), the left hand
  rests on the breech; the barrels spin while firing (three whole turns a clip, so repeated shots
  join; see BARREL_TURNS), the crank turns a third as fast, as on the stock gun, with six shots
  and a small recoil; on reload (recipe "reload": "toss", the default) the left hand lifts the
  empty magazine out and throws it aside (it falls, lies and sinks out of sight), then pulls a
  full one from the pocket at his left hip and seats it (`Unit.reload_plan`; with "reload" None
  he puts the same magazine down at the saddle and seats it again). The full one, `bone_ammo2`
  on the gun's root, lies inside the camel's body out of a reload (`Unit.stash_spare`). A hand
  whose target is out of reach leans the trunk toward it.
- B, deployed: the camel lies down (the game's own lying-down clips of the same rig, turned back
  to the camel's heading, upright, and laid on the ground), is held down 2 s while the gunner
  gets off step by step (`Unit.climb_keys`) and he cranks the gun on foot (the gun mirrored, its
  crank outside); as the gun turns on its post he steps round it (`Traverse.stair`: his feet
  planted, one foot stepping at a time), and he reloads on foot from the pocket on his thigh. With
  the long handles "v5" (recipe "handles", the default) he stands behind the turret with both hands
  in front of his chest, and walks in to the hopper to reload and back (`Traverse.reload_body`). To
  undeploy he gets back on and the camel rises (the default again since round 4, 2026-11-24;
  recipe "b_mounted" true: the gunner stays in the saddle and works the gun as A does).
- The gun's `bone_yaw` (on the post's top, the casing's parent) and the camel's `bone_turret`
  (the launch bones' parent, same place) let a game turn the gun on its post; `<name>_<A|B><scale>
  .aim` (aim_table) holds the gunner's bones at every yaw for the clips he works the gun in.

Compressed game files are expanded by the game's own Granny runtime (`--granny-helper`, default
tools\\granny_recompress.exe; `python -I tools/recompress_models.py --build-helper` makes it);
nothing of the game is stored. Refuses a Steam folder as output. Its outputs come from a game's
models: keep them out of the repository.
"""
import argparse
import copy
import json
import math
import os
import shutil
import struct
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
from aoe3game import ddt, gr2, gr2_mesh, gr2_parts, gr2_skin  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from aoe3game.gr2_anim import Animation, Rig, animation_file, matrix_quat, split  # noqa: E402
from aoe3game.gr2_pose import Keys, axis_matrix, blend, smooth, unit  # noqa: E402

LIB = "animation_library\\"
ZAMB = "units\\asians\\indians\\zamburak\\"
DEFAULT_RECIPE = {
    "name": "gatling_camel",
    "folder": "WoL\\units\\cavalry_ranged\\gatling_camel",
    "camel": {"model": ZAMB + "zamburak_camel_basic", "mesh": "zamburakCamel_2",
              "mount_bone": "HS Bone Chest", "rider_bone": "bone attachpoint",
              # the bone the gun hangs on in game: the rider's (tag ATTACHPOINT). Hung on the chest
              # itself (tobone="HS Bone Chest", with a definebone) the game drew it turned up about 60
              # degrees (seen 2026-11-23); the rider's bone is placed as we place it. Every camel clip
              # the tool writes keeps that bone where the camel's idle has it against the chest.
              "hang_bone": "bone attachpoint", "hang_tag": "ATTACHPOINT"},
    # the swivel gun: the mount bone's triangles wholly beyond x_below (its side) and above y_above;
    # its forked post (the piece that reaches lowest) is kept as the gun's mount unless keep_post is false
    "cut": {"x_below": -0.18, "y_above": 1.6, "keep_post": True},
    # the gun's post centred over the camel's spine at the saddle's front (the user's references,
    # 2026-11-26: a tall post rising from the front of the saddle, over the withers, the rider right
    # behind it): the zamburak's own forked post stood at the saddle's front-left edge, 0.24 off the
    # spine. A made iron post at x 0 under the same top (`radius`, design units); false keeps the old one
    "post": {"centre": True, "radius": 0.032},
    "rider": {"model": "WoL\\units\\cavalry_ranged\\zamburak\\zamburak_rider_1",
              "hat": {"model": "units\\infantry_ranged\\grenadier\\grenadier_age4_hat", "frombone": "bone_hat",
                      "tobone": "Bip01 Head",
                      "texture": "WoL\\units\\cavalry_ranged\\zamburak\\zamburak_rider_2_hat"}},
    "gun": {"model": "units\\artillery\\gatling_gun\\gatling_gun",
            "magazine": "units\\artillery\\gatling_gun\\ammo_magazine",
            "cannon": "bone_cannon", "barrel": "bone_barrel", "crank": "bone_crank", "muzzle": "bone_launchpoint",
            "ammo": "bone_ammo"},
    # the gun's size as seen in game, a share of the stock gun's; one model per scale
    "scales": [0.55, 0.7],
    # how far the gun sits ahead of its trunnion on the post's top, in the stock gun's own units: the
    # casing then rests on the fork behind the trunnion and its breech clears the rider's knee
    "forward": 0.45,
    "variants": ["A", "B"],
    # the seated gunner's reload: "toss" (the empty magazine thrown aside, a full one pulled from the
    # pocket at his hip) or None (the same magazine lifted and seated again)
    "reload": "toss",
}
FPS = 30
X = np.array([1.0, 0.0, 0.0])
Y = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])


# --------------------------------------------------------------------------------------------------
# The game's files


class Game:
    """Art files of a game copy: loose first, then the art archives, a later archive winning over an
    earlier one (Art5 over Art4 over Art1: the stock Gatling gun of Art1 is an older model than its
    animations); Granny files expanded by the game's runtime through make_dismount.Game."""

    def __init__(self, folder, helper, work):
        import make_dismount as md
        self._g = md.Game(folder, helper, work)
        self.folder = folder
        idx = {}
        art = os.path.join(folder, "art")
        for name in sorted(os.listdir(art), key=str.lower):
            if name.lower().endswith(".bar"):
                path = os.path.join(art, name)
                for stored, off, size in bar.read_entries(path):
                    key = stored.lower().replace("/", "\\")
                    if key.startswith("art\\"):
                        key = key[4:]
                    idx[key] = (path, off, size)
        self._g._index = idx

    def granny(self, rel):
        return self._g.granny(rel)

    def texture(self, stored):
        return self._g.texture(stored)


# --------------------------------------------------------------------------------------------------
# Small helpers


def tr(p):
    m = np.eye(4)
    m[:3, 3] = p
    return m


def rot4(r):
    m = np.eye(4)
    m[:3, :3] = r
    return m


def apply(m, pts):
    pts = np.asarray(pts, np.float64)
    return (np.c_[pts, np.ones(len(pts))] @ m.T)[:, :3]


def point(m, p):
    return (m @ np.r_[np.asarray(p, np.float64), 1.0])[:3]


def rigid(m):
    """A 4 x 4 frame without its scale and shear (the nearest rotation, same translation)."""
    u, _s, vt = np.linalg.svd(np.asarray(m, np.float64)[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    out = np.array(m, np.float64)
    out[:3, :3] = r
    return out


def lower_keys(d):
    return {k.lower(): v for k, v in d.items()}


def column(m_row):
    """A matrix of Granny's row-vector convention as a column-vector one."""
    return np.asarray(m_row, np.float64).T


# --------------------------------------------------------------------------------------------------
# The camel without its swivel gun


def swivel_pieces(part, mount_bone, x_below, y_above):
    """(cut mask over the mesh's triangles, [(component, triangle indices, is_post)]): the pieces
    bound to `mount_bone` whose every corner lies beyond x_below and above y_above. The post is the
    piece that reaches lowest."""
    pos, tris = part["positions"], part["triangles"]
    bones = np.array(gr2_parts.triangle_bones(part), dtype=object)
    comp = gr2_parts.components(pos, tris)
    pieces = []
    for c in np.unique(comp):
        sel = np.nonzero(comp == c)[0]
        v = np.unique(tris[sel])
        if all(b == mount_bone for b in bones[sel]) and (pos[v, 0] < x_below).all() and (pos[v, 1] > y_above).all():
            pieces.append([int(c), sel, False])
    if pieces:
        low = min(range(len(pieces)), key=lambda i: pos[np.unique(tris[pieces[i][1]]), 1].min())
        pieces[low][2] = True
    mask = np.zeros(len(tris), bool)
    for _c, sel, _post in pieces:
        mask[sel] = True
    return mask, pieces


def post_top(part, pieces):
    """The centre of the post's top: x and z of its corners within 0.05 of its highest, that height."""
    pos, tris = part["positions"], part["triangles"]
    for _c, sel, is_post in pieces:
        if is_post:
            v = pos[np.unique(tris[sel])]
            top = v[v[:, 1] >= v[:, 1].max() - 0.05]
            return np.array([top[:, 0].mean(), v[:, 1].max(), top[:, 2].mean()])
    raise ValueError("no post among the swivel gun's pieces")


# --------------------------------------------------------------------------------------------------
# The gun


class GunSource:
    """The stock gun taken apart by bone, in its own model space (file units)."""

    def __init__(self, game, spec):
        self.spec = spec
        self.data = game.granny(spec["model"])
        self.mag_data = game.granny(spec["magazine"])
        root = gr2.load(self.data).root()
        self.rig = Rig.of(root)
        self.rest = self.rig.by_name(self.rig.rest_worlds())
        parts = gr2_parts.mesh_parts(self.data)
        gun = next(p for p in parts if any(n.lower() == spec["cannon"].lower() for n in p["skin_names"]))
        self.parts = {}
        bones = gr2_parts.triangle_bones(gun)
        for key in ("cannon", "barrel", "crank"):
            want = spec[key].lower()
            sel = np.array([(b or "").lower() == want for b in bones])
            self.parts[key] = sub_part(gun, sel)
        mag = gr2_parts.mesh_parts(self.mag_data)[0]
        self.parts["magazine"] = sub_part(mag, np.ones(len(mag["triangles"]), bool))
        mrig = Rig.of(gr2.load(self.mag_data).root())
        self.ammo_rest = mrig.by_name(mrig.rest_worlds())[spec["ammo"].lower()]
        self.trunnion = self.rest[spec["cannon"].lower()][:3, 3].copy()
        self.barrel_at = self.rest[spec["barrel"].lower()][:3, 3].copy()
        self.crank_at = self.rest[spec["crank"].lower()][:3, 3].copy()
        self.muzzle_at = self.rest[spec["muzzle"].lower()][:3, 3].copy()
        cp = self.parts["crank"]["positions"]
        r = np.linalg.norm((cp - self.crank_at)[:, 1:], axis=1)       # about the crank's axis (x)
        far = cp[r >= r.max() - 0.03]
        self.handle = far.mean(0)                                       # the crank's handle
        c = self.parts["cannon"]["positions"]
        self.seat = self.trunnion[1] - c[:, 1].min()                    # trunnion above the casing's foot
        rear = c[c[:, 2] <= c[:, 2].min() + 0.25]
        self.breech_top = np.array([self.trunnion[0], rear[:, 1].max(), rear[:, 2].mean()])
        m = self.parts["magazine"]["positions"]
        self.mag_top = np.array([m[:, 0].mean(), m[:, 1].max(), m[:, 2].mean()])
        self.mag_base = np.array([m[:, 0].mean(), m[:, 1].min(), m[:, 2].mean()])
        self.iron_uv, self.iron_material = self._iron(game)

    def _iron(self, game):
        """(uv, material) of an even patch of the casing's dark iron: its largest triangle whose
        texels (corners and middle) are mid-dark grey with no colour, for parts made here (the
        long handles) to be one colour with the gun."""
        part = self.parts["cannon"]
        uv, tri = part["uvs"], part["triangles"]
        area = np.array([abs((uv[b][0] - uv[a][0]) * (uv[c][1] - uv[a][1]) - (uv[b][1] - uv[a][1]) *
                             (uv[c][0] - uv[a][0])) for a, b, c in tri])
        img = None
        for name in gr2_mesh.read(self.data)["textures"]:
            if name and "_b." not in name.lower() and "bump" not in name.lower():
                img = game.texture(name)
                if img is not None:
                    break
        if img is not None:
            hgt, wid = img.shape[:2]

            def texel(q):
                x = int(min(wid - 1, max(0, (q[0] % 1.0) * wid)))
                y = int(min(hgt - 1, max(0, (q[1] % 1.0) * hgt)))
                return np.asarray(img[y, x, :3], np.float64)
            for i, (a, b, c) in enumerate(tri):
                cols = np.array([texel(q) for q in (uv[a], uv[b], uv[c], (uv[a] + uv[b] + uv[c]) / 3.0)])
                lum = cols.mean(1)
                if not ((lum > 40).all() and (lum < 110).all() and np.ptp(cols, axis=0).max() < 25 and
                        (cols.max(1) - cols.min(1) < 25).all()):
                    area[i] = 0.0
        k = int(np.argmax(area))
        return uv[tri[k]].mean(0), part["materials"][k]


def sub_part(part, sel):
    """The triangles `sel` of a mesh_parts entry with only the vertices they use."""
    tris = part["triangles"][sel]
    used = np.unique(tris)
    remap = -np.ones(len(part["positions"]), np.int64)
    remap[used] = np.arange(len(used))
    return {"positions": part["positions"][used].copy(), "normals": part["normals"][used].copy(),
            "tangents": part["tangents"][used].copy(), "uvs": part["uvs"][used].copy(), "triangles": remap[tris],
            "materials": [part["materials"][i] for i in part["tri_material"][sel]]}


class GunDesign:
    """One gun placed on the camel: the parts in the camel's model space at its bind pose ("design
    space"), the bones that move them, and the map to the gun model's own space (the mount bone's).

    `scale` is the size seen in game, a share of the stock gun's: the mount bone draws its triangles
    1/s bigger than its bind pose (s, the bind's scale: 0.918 for the zamburak's chest), so the
    design scale is scale x s. `mirror` turns the gun about its own middle plane (the crank on the
    other side)."""

    # `yaw`: on the post's top, the casing's parent: a game turns it about its own y (the post's
    # vertical axis) to aim the gun without the camel (the DLL key turretArc); still in our clips
    # `ammo2`: a second magazine, the full one the gunner pulls from the pocket at his left hip in a
    # reload (recipe "reload": "toss") while the empty one goes away. On the root, not the casing, so
    # the gun's yaw never swings it out of hiding: out of a reload it lies inside the camel's body
    # (`stash`, under the saddle), and the same mesh as `ammo`
    # `crank2`: B on foot's drop crank (Unit.long_handles), turned with the gun's crank, on its own
    # axle below it; A has the bone with nothing on it
    BONES = ("root", "yaw", "cannon", "barrel", "crank", "ammo", "ammo2", "muzzle", "crank2")

    def __init__(self, src, mount_bind, post, scale, mirror=False, forward=0.0):
        self.src, self.mirror = src, mirror
        self.bind = mount_bind                                  # column vectors, with its scale
        self.bind_scale = float(np.cbrt(abs(np.linalg.det(mount_bind[:3, :3]))))
        self.R = mount_bind[:3, :3] / self.bind_scale           # the bind's rotation
        self.S = np.linalg.inv(mount_bind)                      # design -> gun model space
        self.scale = scale
        self.s = scale * self.bind_scale
        self.mx = -1.0 if mirror else 1.0
        self.pivot = np.asarray(post, np.float64) + np.array([0.0, self.s * src.seat, self.s * forward])
        self.post = np.asarray(post, np.float64)      # the post's top: the gun turns about its axis
        self.post_axis = Y.copy()
        f = self.design_point
        self.at = {"cannon": self.pivot.copy(), "barrel": f(src.barrel_at), "crank": f(src.crank_at),
                   "ammo": f(src.ammo_rest[:3, 3]), "muzzle": f(src.muzzle_at)}
        self.handle = f(src.handle)
        self.breech_top = f(src.breech_top)
        self.mag_top = f(src.mag_top)
        self.mag_base = f(src.mag_base)
        self.parent = {"root": None, "yaw": "root", "cannon": "yaw", "barrel": "cannon", "crank": "cannon",
                       "ammo": "cannon", "ammo2": "root", "muzzle": "cannon", "crank2": "cannon"}
        self.at["crank2"] = self.at["crank"].copy()
        self.made = {}          # parts made here (design space): {name: (part tuple, bone)}
        self.stash = None       # the spare's design frame out of a reload (Unit.stash_spare)
        self.part_bone = {"cannon": "cannon", "barrel": "barrel", "crank": "crank", "magazine": "ammo",
                          "magazine2": "ammo2"}

    def add_post(self, base_y, radius):
        """The gun's post made of the casing's dark iron, on the root (it does not turn): a round
        shaft from just under the saddle's surface (`base_y`) up to the post's top, a flange on the
        saddle and a collar under the top (recipe "post": centred over the spine)."""
        src = self.src
        width = src.parts["cannon"]["tangents"].shape[1]
        top = self.post

        def cylinder(a, b, r, n=12):
            ax = unit(b - a)
            u_ = unit(np.cross(ax, X if abs(ax @ X) < 0.9 else Z))
            v_ = np.cross(ax, u_)
            pos, nrm, tris = [], [], []
            for k in range(n):
                ang = 2 * math.pi * k / n
                d = math.cos(ang) * u_ + math.sin(ang) * v_
                pos += [a + r * d, b + r * d]
                nrm += [d, d]
            for k in range(n):
                i0, i1, j0, j1 = 2 * k, 2 * k + 1, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1
                tris += [(i0, j0, i1), (i1, j0, j1)]
            for end, sgn in ((a, -1.0), (b, 1.0)):
                c0 = len(pos)
                pos.append(end)
                nrm.append(sgn * ax)
                for k in range(n):
                    ang = 2 * math.pi * k / n
                    pos.append(end + r * (math.cos(ang) * u_ + math.sin(ang) * v_))
                    nrm.append(sgn * ax)
                for k in range(n):
                    p0, p1 = c0 + 1 + k, c0 + 1 + (k + 1) % n
                    tris.append((c0, p1, p0) if sgn > 0 else (c0, p0, p1))
            return pos, nrm, tris

        pieces = [cylinder(np.array([top[0], base_y - 0.06, top[2]]), top - np.array([0.0, 0.002, 0.0]), radius),
                  cylinder(np.array([top[0], base_y - 0.01, top[2]]), np.array([top[0], base_y + 0.015, top[2]]),
                           2.2 * radius),
                  cylinder(top - np.array([0.0, 0.035, 0.0]), top - np.array([0.0, 0.002, 0.0]), 1.5 * radius)]
        pos, nrm, tris = [], [], []
        for p_, n_, t_ in pieces:
            base = len(pos)
            pos += list(p_)
            nrm += list(n_)
            tris += [(a + base, b + base, c + base) for a, b, c in t_]
        pos, nrm = np.array(pos), np.array(nrm)
        tan = np.array([np.r_[unit(np.cross(n, Y) if abs(n @ Y) < 0.9 else np.cross(n, X)), 1.0] for n in nrm])
        part = (pos, nrm, np.array([src.iron_uv] * len(pos)), np.asarray(tris, np.int64),
                [src.iron_material] * len(tris), tan[:, :width])
        self.made["post"] = (part, "root")
        self.post_base = float(base_y)

    def design_point(self, p):
        d = (np.asarray(p, np.float64) - self.src.trunnion) * self.s
        d[..., 0] *= self.mx
        return self.pivot + d

    def parts(self):
        """{part: (positions, normals, uvs, triangles, materials, tangents)} in design space."""
        out = {}
        for key, p in self.src.parts.items():
            pos = self.design_point(p["positions"])
            nrm = p["normals"].copy()
            tan = p["tangents"].copy()
            tris = p["triangles"].copy()
            if self.mirror:
                nrm[:, 0] *= -1.0
                tan[:, 0] *= -1.0
                tris = tris[:, ::-1].copy()
            out[key] = (pos, nrm, p["uvs"], tris, p["materials"], tan)
        out["magazine2"] = out["magazine"]                 # the spare: the same mesh on its own bone
        for name, (part, bone) in self.made.items():       # the long handles (Unit.long_handles)
            out[name] = part
            self.part_bone[name] = bone
        return out

    def rest(self):
        """{bone: design frame at rest} (rigid, axis-aligned with the camel)."""
        out = {"root": rot4(self.R)}
        out["root"][:3, 3] = self.bind[:3, 3]
        for k, v in self.at.items():
            out[k] = tr(v)
        out["yaw"] = tr(self.post)
        out["ammo2"] = tr(self.at["ammo"])
        return out

    def to_model(self, frame):
        """A rigid design frame in the gun model's space (the mount bone's local space)."""
        m = np.eye(4)
        m[:3, :3] = self.R.T @ frame[:3, :3]
        m[:3, 3] = point(self.S, frame[:3, 3])
        return m

    def model_bytes(self, name):
        """The gun model: its root (identity, the frombone) and one rigid mesh per part."""
        rest = self.rest()
        bones = [(f"bone_{name}" if b == "root" else self.bone_name(b), -1 if b == "root" else
                  self.BONES.index(self.parent[b]), np.eye(4) if b == "root" else self.to_model(rest[b]))
                 for b in self.BONES]
        parts = []
        for key, (pos, nrm, uvs, tris, mats, tan) in self.parts().items():
            bone = bones[0][0] if self.part_bone[key] == "root" else self.bone_name(self.part_bone[key])
            parts.append({"name": f"{name}_{key}", "bone": bone,
                          "positions": apply(self.S, pos), "normals": nrm @ self.R, "tangents": tan @ self.R,
                          "uvs": uvs, "triangles": tris, "materials": mats})
        return gr2_parts.rigid_model(self.src.data, bones[0][0], bones, parts, source_name=name)

    @staticmethod
    def bone_name(b):
        return {"yaw": "bone_yaw", "cannon": "bone_cannon", "barrel": "bone_barrel", "crank": "bone_crank",
                "ammo": "bone_ammo", "ammo2": "bone_ammo2", "muzzle": "bone_launchpoint",
                "crank2": "bone_crank2"}[b]

    def frames(self, state):
        """{bone: design frame} for a state: barrel and crank angles (degrees), the casing's recoil
        (design units along -z), the magazine's frame (None: seated) and `yaw`, the whole gun
        turned about the vertical through its trunnion (degrees, positive toward the unit's right;
        the turn a game would give the trunnion bone to aim the gun without turning the camel)."""
        cannon = tr(self.pivot + np.array([0.0, 0.0, -state.get("recoil", 0.0)]))
        rel = cannon @ tr(-self.pivot)
        spin = self.mx
        out = {"cannon": cannon,
               "barrel": rel @ tr(self.at["barrel"]) @ rot4(axis_matrix(Z, spin * state.get("barrel", 0.0))),
               "crank": rel @ tr(self.at["crank"]) @ rot4(axis_matrix(X, state.get("crank", 0.0))),
               "crank2": rel @ tr(self.at["crank2"]) @ rot4(axis_matrix(X, state.get("crank", 0.0))),
               "muzzle": rel @ tr(self.at["muzzle"])}
        mag = state.get("magazine")
        out["ammo"] = rel @ tr(self.at["ammo"]) if mag is None else mag
        mag2 = state.get("magazine2")
        if mag2 is None:
            mag2 = self.stash if self.stash is not None else tr(self.at["ammo"])
        out["yaw"] = tr(self.post)
        yaw = state.get("yaw", 0.0)
        if yaw:
            turn = self.yaw_matrix(yaw)
            out = {k: turn @ v for k, v in out.items()}
        out["ammo2"] = mag2              # on the root: the yaw does not turn it
        return out

    def yaw_matrix(self, yaw):
        """The design-space turn of the gun by `yaw` degrees about its mount's vertical axis: the
        post's axis (`post_axis`, through the post's top), so the casing stays seated on the post."""
        return tr(self.post) @ rot4(axis_matrix(self.post_axis, yaw)) @ tr(-self.post)

    def handle_at(self, frames):
        return point(frames["crank"], self.handle - self.at["crank"])


# --------------------------------------------------------------------------------------------------
# Drawing (the game's model space is left-handed: drawn mirrored in x so a picture shows the unit as
# the game does, its right side on its right)


class Figure:
    """A model to draw from its bytes: meshes, skeleton, textures (a texture name may be replaced)."""

    def __init__(self, game, data, replace=None):
        read = gr2_mesh.read(data)
        self.skel = read["skeletons"][0]
        self.names = [b["name"] for b in self.skel["bones"]]
        self.meshes = []
        for mesh in read["meshes"]:
            tex = None
            ft = mesh["face_textures"]
            order = [int(i) for i in np.unique(ft) if i >= 0] + list(range(len(read["textures"])))
            for i in order:
                name = read["textures"][i]
                if name and "_b." not in name.lower() and "bump" not in name.lower():
                    tex = game.texture(replace) if replace else game.texture(name)
                    if tex is not None:
                        break
            self.meshes.append((mesh, tex))

    def items(self, pose=None, place=None):
        exact = None if pose is None else {n: pose[n.lower()] for n in self.names if n.lower() in pose}
        out = []
        for m, tex in self.meshes:
            p = gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"], m["skin_names"],
                                self.skel, exact)
            if place is not None:
                p = apply(place, p)
            out.append((p, m["triangles"], m["uvs"], tex, (150, 120, 90)))
        return out


def draw(items, width=360, height=300, azimuth=-40.0, elevation=18.0, span=4.0, centre=(0.0, 1.6, 0.2),
         marks=None, ground=True):
    """The items seen from `azimuth` (degrees about the vertical: 0 in front of the unit, 90 on its
    right, -90 on its left, as the game shows it), `marks` [(point, colour, size)] drawn as stars."""
    import retarget_anims as ra
    flip = np.diag([-1.0, 1.0, 1.0])
    out = []
    if ground:
        g = np.array([[-6, 0.0, -6], [6, 0.0, -6], [6, 0.0, 6], [-6, 0.0, 6]], np.float64)
        out.append((g, np.array([[0, 1, 2], [0, 2, 3]]), None, None, (205, 200, 184)))
    for p, t, uv, tex, col in items:
        out.append((np.asarray(p) @ flip, t, uv, tex, col))
    c = np.asarray(centre, np.float64) @ flip
    img = ra.draw(out, width=width, height=height, azimuth=-azimuth, elevation=elevation, span=span, centre=c)
    if marks:
        az, el = math.radians(-azimuth), math.radians(elevation)
        view = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
        right = np.cross(Y, view)
        right /= np.linalg.norm(right)
        up = np.cross(view, right)
        scale = height / span
        img = img.copy()
        for p, col, size in marks:
            d = np.asarray(p, np.float64) @ flip - c
            x, y = width / 2 + (d @ right) * scale, height / 2 - (d @ up) * scale
            for k in range(8):
                a = k * math.pi / 4
                rr = size * (1.0 if k % 2 == 0 else 0.45)
                for s in np.linspace(0, 1, int(rr) + 2):
                    u, v = int(round(x + s * rr * math.cos(a))), int(round(y + s * rr * math.sin(a)))
                    if 0 <= u < width and 0 <= v < height:
                        img[v, u] = col
    return img


def caption(img, text, scale=1, band=(40, 40, 40)):
    import bitfont
    out = img.copy()
    h = 7 * scale + 6
    out[-h:, :] = band
    bitfont.draw(out, text, 4, out.shape[0] - h + 3, (255, 255, 255), scale=scale)
    return out


def title(width, text, scale=2, back=(30, 30, 30)):
    import bitfont
    band = np.full((7 * scale + 10, width, 3), back, np.uint8)
    bitfont.draw(band, text, 6, 5, (255, 255, 255), scale=scale)
    return band


def grid(tiles, cols, pad=255):
    h, w = tiles[0].shape[:2]
    rows = []
    for i in range(0, len(tiles), cols):
        row = tiles[i:i + cols]
        row += [np.full_like(tiles[0], pad)] * (cols - len(row))
        rows.append(np.concatenate(row, 1))
    return np.concatenate(rows, 0)


# --------------------------------------------------------------------------------------------------
# The camel and its clips


class Camel:
    """The camel unit's model: its skeleton, the mount bone's bind, its own clips, and clips of the
    same rig (the lying-down ones) laid on the ground."""

    def __init__(self, game, spec, cut_data):
        self.game = game
        self.data = game.granny(spec["model"])
        root = gr2.load(self.data).root()
        self.rig = Rig.of(gr2.load(cut_data).root())          # the cut model's: its launch bone too
        self.mount = spec["mount_bone"].lower()
        self.rider_bone = spec["rider_bone"].lower()
        self.bind = column(gr2_mesh.bind_matrices(root)[spec["mount_bone"]])
        self.hang = spec.get("hang_bone", spec["mount_bone"]).lower()
        self.cut = cut_data
        read = gr2_mesh.read(cut_data)
        self.mesh, self.skel = read["meshes"][0], read["skeletons"][0]
        self._anims, self._scales = {}, {}
        croot = gr2.load(cut_data).root()
        self.rest_scales = []
        for b in croot.get("Skeletons")[0].get("Bones"):
            t = b.get("Transform")
            self.rest_scales.append(np.array(t["scale_shear"], np.float64).reshape(3, 3)
                                    if int(t["flags"]) & 4 else np.eye(3))
        self.base = self.anim(spec.get("idle", ZAMB + "zamburak_camel_idle00"))
        P0 = self.pose(self.base, 0.0)
        hang0 = rigid(P0[self.hang])
        # the rider's seat risen with the hump under it (HUMP; the gun hung on the same bone is placed
        # in the camel's space, so it does not move with it)
        self.seat_rise = 0.0
        if spec.get("hump", True) and self.hang == self.rider_bone:
            s = hang0[:3, 3]
            self.seat_rise = hump_rise(HUMP, s[0], s[2])
            hang0 = tr((0.0, self.seat_rise, 0.0)) @ hang0
        self.hang_local = np.linalg.inv(rigid(P0[self.mount])) @ hang0   # the hang bone on the chest
        self.seat_local = rigid(P0[self.mount])[:3, :3].T @ np.array([0.0, self.seat_rise, 0.0])
        self.hang_bind = self.bind @ self.hang_local      # the hang bone at the bind pose (the chest's scale)

    def seat_frame(self, pose):
        """The rider's bone in `pose` as the clip has it, risen with the hump (on the chest's up)."""
        m = rigid(pose[self.rider_bone])
        m[:3, 3] += rigid(pose[self.mount])[:3, :3] @ self.seat_local
        return m

    def fix_hang(self, pose):
        """The pose with the hang bone (and the rider on it) where the idle has it on the chest."""
        if self.hang == self.mount:
            return pose
        from aoe3game.gr2_pose import set_frame
        return set_frame(pose, self.rig, self.hang, rigid(pose[self.mount]) @ self.hang_local)

    def pin_hang(self, pose, first):
        """The pose with the hang bone (and the rider on it) kept at its world frame in `first`."""
        from aoe3game.gr2_pose import set_frame
        return set_frame(pose, self.rig, self.hang, first[self.hang])

    def anim(self, rel):
        if rel not in self._anims:
            data = self.game.granny(rel)
            a = Animation.load(data)
            self._scales[id(a)] = self.effective_scales(gr2.load(data).root())
            self._anims[rel] = a
        return self._anims[rel]

    def load(self, data):
        """An animation of our own (bytes), registered with its scales."""
        a = Animation.load(data)
        self._scales[id(a)] = self.effective_scales(gr2.load(data).root())
        return a

    def effective_scales(self, root):
        """The scale/shear (3 x 3, model axes) the runtime gives each bone in a clip: its track's
        constant curve turned into the model's axes; none (identity) when its track has an empty
        curve; the skeleton's rest scale when the clip has no track for it (measured on the stock
        camel's tag files, 2026-11-23: the idle's tags fit identity, not the rest scales)."""
        from aoe3game.gr2_anim import Basis, Curve
        C, _s = Basis.of(root).to(self.rig.basis)
        curves = {}
        for tr in (root.get("TrackGroups") or [None])[0].get("TransformTracks") or []:
            curves[tr.get("Name").lower()] = Curve.of(tr.get("ScaleShearCurve"))
        out = []
        for i, n in enumerate(self.rig.names):
            c = curves.get(n.lower())
            if c is None:
                out.append(self.rest_scales[i])
            elif c.empty():
                out.append(np.eye(3))
            else:
                out.append(C @ np.asarray(c.controls[0], np.float64).reshape(3, 3) @ C.T)
        return out

    def locals_(self, anim, t):
        """[(position, quaternion)] per bone at t: the track's (in the model's axes and units) or
        the rest's."""
        from aoe3game.gr2_anim import matrix_quat
        from aoe3game.gr2_skin import quat_matrix
        c, sc = anim.basis.to(self.rig.basis)
        out = []
        for i, n in enumerate(self.rig.names):
            tr = anim.tracks.get(n.lower())
            rp, rq = self.rig.rest[i]
            if tr is None:
                out.append((rp, rq))
                continue
            p, q = tr.local(t, (None, None))
            p = rp if p is None else sc * (c @ p)
            q = rq if q is None else matrix_quat(c @ quat_matrix(q) @ c.T)
            out.append((p, q))
        return out

    def worlds(self, locs, scales):
        from aoe3game.gr2_anim import frame
        out = []
        for i, ((p, q), S) in enumerate(zip(locs, scales)):
            m = frame(p, q)
            m[:3, :3] = m[:3, :3] @ S
            par = self.rig.parents[i]
            out.append(out[par] @ m if par >= 0 else m)
        return self.rig.by_name(out)

    def mesh_points(self, P):
        """The cut camel's vertices posed at P (world frames by bone name), one array."""
        if getattr(self, "_mesh", None) is None:
            read = gr2_mesh.read(self.cut)
            self._mesh = (read["meshes"], read["skeletons"][0])
        meshes, skel = self._mesh
        names = [b["name"] for b in skel["bones"]]
        exact = {n: P[n.lower()] for n in names if n.lower() in P}
        return np.concatenate([gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"],
                                               m["skin_names"], skel, exact) for m in meshes])

    def surface_heights(self, P, x, z):
        """The heights where the vertical line through (x, z) (world) meets the cut camel's
        surface posed at P, sorted."""
        self.mesh_points(P)
        meshes, skel = self._mesh
        names = [b["name"] for b in skel["bones"]]
        exact = {n: P[n.lower()] for n in names if n.lower() in P}
        out = []
        for m in meshes:
            p = gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"], m["skin_names"],
                                skel, exact)
            t = np.asarray(m["triangles"], np.int64)
            a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
            # barycentric weights of (x, z) in each triangle's top view
            d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
            ok = np.abs(d) > 1e-12
            d = np.where(ok, d, 1.0)
            w1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
            w2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
            w3 = 1.0 - w1 - w2
            hit = ok & (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
            out += list((w1 * a[:, 1] + w2 * b[:, 1] + w3 * c[:, 1])[hit])
        return np.sort(np.array(out))

    def pose(self, anim, t, scales=None):
        """World frames by name at t as the runtime draws them (scales included)."""
        return self.worlds(self.locals_(anim, t), scales or self._scales[id(anim)])

    # the bones a borrowed clip does not scale (the camel keeps its own idle's): the sheep's clips
    # scale the master to 0.58, which shrinks the whole camel
    OWN_SCALE = ("hs bone master", "hs bone chest", "bone attachpoint", "bone hitpointbar")

    def borrowed_scales(self, anim):
        own, theirs = self._scales[id(self.base)], self._scales[id(anim)]
        return [theirs[i] if (n.lower() in anim.tracks and n.lower() not in self.OWN_SCALE) else own[i]
                for i, n in enumerate(self.rig.names)]

    def borrowed(self, anim, t):
        """The pose at t of a clip of the same rig made for another animal: its tracks where it has
        them, the camel's idle (first frame) for the bones it lacks (the rider's bone above all)."""
        own = self.locals_(self.base, 0.0)
        theirs = self.locals_(anim, t)
        locs = [theirs[i] if n.lower() in anim.tracks else own[i] for i, n in enumerate(self.rig.names)]
        return self.worlds(locs, self.borrowed_scales(anim))

    def lowest(self, pose):
        exact = {n: pose[n.lower()] for n in (b["name"] for b in self.skel["bones"]) if n.lower() in pose}
        m = self.mesh
        p = gr2_skin.deform(m["file_positions"], m["vertex_bones4"], m["vertex_weights4"], m["skin_names"],
                            self.skel, exact)
        return float(p[:, 1].min())

    def lower_head(self, pose, degrees):
        """The pose with the neck bent down by `degrees` at its base and the head lifted back by a
        third of it (the muzzle stays near level, the head drops below the line of fire)."""
        from aoe3game.gr2_pose import rotate_about
        side = unit(pose[self.mount][:3, :3] @ (self.pose(self.base, 0.0)[self.mount][:3, :3].T @ X))
        p = rotate_about(pose, self.rig, "hs bone neck lower", "hs bone neck lower", side, degrees)
        return rotate_about(p, self.rig, "hs bone head", "hs bone head", side, -degrees / 3.0)

    def roll_over(self, pose, t, most=80.0, time=1.2):
        """The lying pose rolled onto the camel's right side over `time` seconds (about its length,
        through its chest) and laid on the ground: how it dies lying down."""
        from aoe3game.gr2_pose import smooth as ease
        c = pose[self.mount][:3, 3]
        fwd = unit(pose[self.mount][:3, :3] @ (self.pose(self.base, 0.0)[self.mount][:3, :3].T @ Z))
        fwd[1] = 0.0
        fwd = unit(fwd)
        a = most * ease(t / time)
        # its left side (-x) goes up: the turn about the forward axis that lifts -x
        for sign in (1.0, -1.0):
            m = tr(c) @ rot4(axis_matrix(fwd, sign * a)) @ tr(-c)
            if a == 0 or (m[:3, :3] @ -X)[1] > 0:
                break
        p = {k: m @ v for k, v in pose.items()}
        dy = -self.lowest(p)
        return {k: tr((0.0, dy, 0.0)) @ v for k, v in p.items()}

    def slump(self, pose, t, roll=12.0, time=1.4):
        """Round 6 (B's gun at rest across its back, pointing out over its right side): the lying camel
        dies without rolling over: its neck bends down at its base until its head lies on the ground,
        and its body slumps `roll` degrees onto its right side, over `time` seconds, laid on the ground
        (a roll onto its right side would drive the gun's barrels into the ground; onto its left, the
        camel would fall on the gunner)."""
        from aoe3game.gr2_pose import rotate_about
        from aoe3game.gr2_pose import smooth as ease
        a = ease(min(1.0, max(0.0, t / time)))
        if getattr(self, "_slump_neck", None) is None:
            self._slump_neck = {}
        key = id(pose)
        if key not in self._slump_neck:
            # the neck's bend that lays the head on the ground (its lowest point at the body's)
            n, h = pose["hs bone neck lower"][:3, 3], pose["hs bone head"][:3, 3]
            d = h - n
            d[1] = 0.0
            side = unit(np.cross(Y, unit(d)))
            base = self.lowest(pose)
            best = 0.0
            for deg in np.arange(0.0, 95.0, 2.5):
                for sgn in (1.0, -1.0):
                    p = rotate_about(pose, self.rig, "hs bone neck lower", "hs bone neck lower", side, sgn * deg)
                    if p["hs bone head"][1, 3] < h[1] - 1e-6:
                        if self.lowest(p) >= base - 0.01:
                            best = sgn * deg
                        break
            self._slump_neck[key] = (side, best)
        side, best = self._slump_neck[key]
        p = rotate_about(pose, self.rig, "hs bone neck lower", "hs bone neck lower", side, best * a)
        c = p[self.mount][:3, 3]
        fwd = unit(p[self.mount][:3, :3] @ (self.pose(self.base, 0.0)[self.mount][:3, :3].T @ Z))
        fwd[1] = 0.0
        fwd = unit(fwd)
        r = roll * a
        for sign in (1.0, -1.0):                     # its left side (-x) goes up
            m = tr(c) @ rot4(axis_matrix(fwd, sign * r)) @ tr(-c)
            if r == 0 or (m[:3, :3] @ -X)[1] > 0:
                break
        p = {k: m @ v for k, v in p.items()}
        dy = -self.lowest(p)
        return {k: tr((0.0, dy, 0.0)) @ v for k, v in p.items()}

    def heading(self, pose):
        """The body's heading (degrees about the vertical, 0 toward +z): pelvis to chest."""
        d = pose[self.mount][:3, 3] - pose["hs bone pelvis"][:3, 3]
        return math.degrees(math.atan2(d[0], d[2]))

    # The kush (2026-11-26). The sheep's lying clips fold a sheep's legs at a sheep's angles: on the
    # camel's long legs they stay struts, and the body lying on them is 0.32 m off the ground (the
    # hump at 75% of its standing height; the user: "the camel isn't properly lying on the ground").
    # A camel lies as the reference shows it: the belly and the chest's pad on the ground, the
    # forelegs folded under the chest on their carpal knees (the cannon folded back under the
    # forearm), the hind legs folded beside the belly (the stifle forward, the hock back on the
    # ground, the cannon folded forward under the shin). So grounded() lowers the lying body until
    # its torso is KUSH_BELLY above the ground and places each leg's joints explicitly in the body's
    # frame: (height, distance from the body's midline, forward or back of the joint above).
    KUSH_BELLY = 0.02
    KUSH_TORSO = ("hs bone pelvis", "hs bone stomach", "hs bone chest")
    KUSH_LEGS = (
        # the shoulders level (the sheep lies with one 15 cm higher), the elbow tucked back under the
        # chest (ahead of it, the knees stood 0.4 m in front of the chest)
        (("hs bone clavicle", "hs bone shoulder", "hs bone arm", "hs bone forearm", "hs bone hoof frnt"),
         ((0.52, 0.17, 0.0), (0.26, 0.21, -1.0), (0.10, 0.20, 1.0), (0.08, 0.18, -1.0))),   # shoulder, elbow, carpus, fetlock
        # the stifle at 0.35 (not on the ground): a lower one puts the hock 0.3 m behind the rump, the
        # shin being longer than the thigh in this rig; the hock at 0.13, where the point of its
        # mesh touches the ground
        (("hs bone hip", "hs bone leg", "hs bone shin", "hs bone hoof back"),            # stifle, hock, fetlock
         ((0.35, 0.30, 1.0), (0.13, 0.28, -1.0), (0.08, 0.24, 1.0))),
    )
    KUSH_HOOF_CLEAR = 0.015          # a foot turned about its fetlock until it is this far above the ground
    KUSH_HOOVES = ("hs bone hoof frnt lt", "hs bone hoof frnt rt", "hs bone hoof back lt", "hs bone hoof back rt")

    def _dominated(self, bones):
        """Per mesh of the cut camel: the vertices whose heaviest bone is one of `bones` (sliced
        arrays for gr2_skin.deform)."""
        if getattr(self, "_dom", None) is None:
            self._dom = {}
        key = tuple(bones)
        if key not in self._dom:
            self.mesh_points(self.pose(self.base, 0.0))
            meshes, _skel = self._mesh
            out = []
            for m in meshes:
                vb, vw = np.asarray(m["vertex_bones4"]), np.asarray(m["vertex_weights4"])
                dom = vb[np.arange(len(vb)), np.argmax(vw, 1)]
                names = np.array([str(m["skin_names"][int(i)]).lower() for i in dom])
                mask = np.isin(names, [b.lower() for b in bones])
                if mask.any():
                    out.append((np.asarray(m["file_positions"])[mask], vb[mask], vw[mask], m["skin_names"]))
            self._dom[key] = out
        return self._dom[key]

    def part_points(self, P, bones):
        """The posed vertices whose heaviest bone is one of `bones`."""
        parts = self._dominated(bones)              # (reads the mesh first)
        skel = self._mesh[1]
        exact = {b["name"]: P[b["name"].lower()] for b in skel["bones"] if b["name"].lower() in P}
        pts = [gr2_skin.deform(p, vb, vw, sn, skel, exact) for p, vb, vw, sn in parts]
        return np.concatenate(pts) if pts else np.zeros((0, 3))

    def body_frame(self, P):
        """The body's level forward, its right, and the point between chest and pelvis."""
        c, p = P[self.mount][:3, 3], P["hs bone pelvis"][:3, 3]
        f = c - p
        f[1] = 0.0
        f = unit(f)
        return f, unit(np.cross(Y, f)), 0.5 * (c + p)

    def lying_share(self, P):
        """How far a grounded pose is from standing (0) to lying (1): its pelvis height between the
        camel's standing one and the sheep's lying clip's, eased."""
        from aoe3game.gr2_pose import smooth as ease
        if getattr(self, "_lie_ref", None) is None:
            stand = self.pose(self.base, 0.0)
            lie = self.grounded(self.anim(B_IDLE), [0.0], kush=False)[0]
            self._lie_ref = (stand["hs bone pelvis"][1, 3] - self.lowest(stand), lie["hs bone pelvis"][1, 3])
        hs, hl = self._lie_ref
        return ease((hs - P["hs bone pelvis"][1, 3]) / (hs - hl))

    def kush(self, P, share=1.0):
        """The grounded lying pose `P` taken `share` of the way to the kush (see KUSH_LEGS): the body
        levelled and lowered, each leg bone turned toward its frame in the kush (on the body: found
        once, on the lying idle's first frame, so every lying frame folds its legs the same way and
        the lie-down ends where the lying clips begin), and the whole laid back on the ground."""
        from aoe3game.gr2_anim import matrix_quat
        from aoe3game.gr2_pose import about, transform_branch
        if share <= 0.0:
            return P
        P = self._kush_body(P, share)
        ref = self._kush_reference()
        side_axis = self.body_frame(P)[1]
        for side in (" lt", " rt"):
            for chain, _places in self.KUSH_LEGS:
                for b in chain:
                    bone = b + side
                    anchor, rel = ref[bone]
                    # the turn in the world, from the whole 3 x 3s: the camel's left legs are mirrored
                    # (determinant -1), whose nearest rotation is not one frame to the next
                    M = rigid(P[anchor][:3, :3] @ rel @ np.linalg.inv(P[bone][:3, :3]))[:3, :3]
                    if share < 1.0:
                        # `share` of the turn, the shorter way round; a foot (which flexes about the
                        # body's side axis), the way round that turns one way about it: a hind foot
                        # nearly 180 degrees from its kush frame flipped from one frame to the next
                        q = np.asarray(matrix_quat(M), np.float64)
                        v = q[:3]
                        if bone in self.KUSH_HOOVES:
                            if float(v @ side_axis) < 0.0:
                                q, v = -q, -v
                        elif q[3] < 0.0:
                            q, v = -q, -v
                        sn = float(np.linalg.norm(v))
                        if sn > 1e-9:
                            deg = 2.0 * math.degrees(math.atan2(sn, float(q[3])))
                            M = axis_matrix(v / sn, deg * share)
                        else:
                            M = np.eye(3)
                    P = transform_branch(P, self.rig, bone, about(P[bone][:3, 3], M))
        dy = -self.lowest(P)
        return {k: tr((0.0, dy, 0.0)) @ v for k, v in P.items()}

    def _kush_reference(self):
        """{leg bone: (the body bone its leg hangs from, its rotation on that bone's)} in the kush of
        the lying idle's first frame: each joint placed (KUSH_LEGS), each foot turned about its
        fetlock until it is off the ground."""
        from aoe3game.gr2_pose import about, transform_branch, rotate_about
        if getattr(self, "_kush_ref", None) is not None:
            return self._kush_ref
        P = self._kush_body(self.grounded(self.anim(B_IDLE), [0.0], kush=False)[0], 1.0)
        f, s, c = self.body_frame(P)

        def turn_to(P, bone, child, height, lat, sign):
            o = P[bone][:3, 3]
            a = P[child][:3, 3] - o
            ln = float(np.linalg.norm(a))
            dy, dl = height - o[1], lat - (o - c) @ s
            fw = math.sqrt(max(ln * ln - dy * dy - dl * dl, 0.0))
            if sign == 0.0:                            # forward or back as it is
                sign = 1.0 if a @ f >= 0.0 else -1.0
            b = unit(dy * Y + dl * s + sign * fw * f)
            a = unit(a)
            v = np.cross(a, b)
            sn = float(np.linalg.norm(v))
            if sn < 1e-9:
                return P
            deg = math.degrees(math.atan2(sn, float(a @ b)))
            return transform_branch(P, self.rig, bone, about(o, axis_matrix(v / sn, deg)))

        for side, sg in ((" lt", -1.0), (" rt", 1.0)):
            for chain, places in self.KUSH_LEGS:
                for i, (h, la, sign) in enumerate(places):
                    P = turn_to(P, chain[i] + side, chain[i + 1] + side, h, sg * la, sign)
        for hoof in self.KUSH_HOOVES:
            if self.part_points(P, [hoof])[:, 1].min() >= self.KUSH_HOOF_CLEAR:
                continue
            for deg in sorted(np.arange(-150.0, 151.0, 5.0), key=abs):
                R = rotate_about(P, self.rig, hoof, hoof, s, float(deg))
                if self.part_points(R, [hoof])[:, 1].min() >= self.KUSH_HOOF_CLEAR:
                    P = R
                    break
        ref = {}
        for side in (" lt", " rt"):
            for chain, _places in self.KUSH_LEGS:
                anchor = self.rig.names[self.rig.parents[self.rig.index[chain[0] + side]]].lower()
                for b in chain:
                    ref[b + side] = (anchor, np.linalg.inv(P[anchor][:3, :3]) @ P[b + side][:3, :3])
        self._kush_ref = ref
        return ref

    def _kush_body(self, P, share):
        """The lying body levelled and lowered `share` of the way (KUSH_BELLY)."""
        from aoe3game.gr2_pose import about
        # levelled: the sheep lies with its chest 5 degrees up, so its rump was the lowest point, the
        # chest's pad 15 cm off the ground, and the gun (level on the chest) tipped up 5 degrees when
        # turned ahead
        f, s, c = self.body_frame(P)
        if getattr(self, "_mount_rest_rot", None) is None:
            self._mount_rest_rot = self.pose(self.base, 0.0)[self.mount][:3, :3].copy()
        ahead = unit(P[self.mount][:3, :3] @ (self._mount_rest_rot.T @ Z))
        up = math.degrees(math.asin(max(-1.0, min(1.0, float(ahead[1])))))
        for sign in (1.0, -1.0):
            m = about(c, axis_matrix(s, sign * up * share))
            if up == 0.0 or abs((m[:3, :3] @ ahead)[1]) < abs(ahead[1]):
                break
        P = {k: m @ v for k, v in P.items()}
        d = self.part_points(P, self.KUSH_TORSO)[:, 1].min() - self.KUSH_BELLY
        return {k: tr((0.0, -share * d, 0.0)) @ v for k, v in P.items()}

    KUSH = True                      # False: the sheep's lying pose as it was before 2026-11-26 (pictures)

    def grounded(self, anim, times, kush=None):
        """Poses of a borrowed clip at `times`, each turned back to the camel's own heading over the
        same spot (the sheep the lying-down clips were made for turns, slides and rolls onto its
        flank as it lies down), upright, and lifted or lowered so the body's lowest point is on the ground (it sits at another
        height); with `kush`, taken toward the kush as far as the pose is lying (lying_share)."""
        ref = self.pose(self.base, 0.0)
        h0 = self.heading(ref)
        root = self.rig.names[0].lower()
        out = []
        for t in times:
            p = self.borrowed(anim, t)
            turn = rot4(axis_matrix(Y, h0 - self.heading(p)))
            m = p[root][:3, 3]
            move = tr((ref[root][0, 3], 0.0, ref[root][2, 3])) @ turn @ tr((-m[0], 0.0, -m[2]))
            p = {k: move @ v for k, v in p.items()}
            # and rolled back upright (the sheep lies on its flank; the gun must stand on the back)
            lat = p[self.mount][:3, :3] @ (ref[self.mount][:3, :3].T @ X)
            roll = math.degrees(math.atan2(lat[1], math.hypot(lat[0], lat[2])))
            c = p[self.mount][:3, 3]
            fwd = unit(np.array([math.sin(math.radians(h0)), 0.0, math.cos(math.radians(h0))]))
            p = {k: tr(c) @ rot4(axis_matrix(fwd, -roll)) @ tr(-c) @ v for k, v in p.items()}
            dy = -self.lowest(p)
            p = {k: tr((0.0, dy, 0.0)) @ v for k, v in p.items()}
            if self.KUSH if kush is None else kush:
                p = self.kush(p, self.lying_share(p))
            out.append(p)
        return out

    def track_bytes(self, name, times, poses, like, scales):
        """A clip of our own from world frames drawn with `scales` (one 3 x 3 per bone): each bone's
        local rotation with its scale taken out, and that scale written as its constant curve, so
        the runtime draws exactly these frames."""
        from aoe3game.gr2_anim import matrix_quat
        inv_s = [np.linalg.inv(S) for S in scales]
        frames = []
        for P in poses:
            w = [P[n.lower()] for n in self.rig.names]
            loc = []
            for i in range(len(w)):
                par = self.rig.parents[i]
                m = np.linalg.inv(w[par]) @ w[i] if par >= 0 else w[i]
                r = m[:3, :3] @ inv_s[i]
                u, _sv, vt = np.linalg.svd(r)
                r = u @ vt
                loc.append((m[:3, 3].copy(), matrix_quat(r)))
            frames.append(loc)
        tracks = [(bone, times, np.array([f[i][0] for f in frames]), np.array([f[i][1] for f in frames]))
                  for i, bone in enumerate(self.rig.names)]
        sc = {n.lower(): [float(v) for v in S.ravel()] for n, S in zip(self.rig.names, scales)}
        return animation_file(name, float(times[-1]), self.rig.names[0], tracks, basis=self.rig.basis,
                              accumulation=like.accumulation, timestep=like.timestep, source=name, scales=sc)

    def hang_scale(self, pose, scales):
        """`scales` with the hang bone's replaced by the one that keeps it rigid under its parent
        (after fix_hang)."""
        if self.hang == self.mount:
            return scales
        i = self.rig.index[self.hang]
        par = self.rig.parents[i]
        m = np.linalg.inv(pose[self.rig.names[par].lower()]) @ pose[self.hang]
        r = rigid(m)[:3, :3]
        out = list(scales)
        out[i] = r.T @ m[:3, :3]
        return out


# --------------------------------------------------------------------------------------------------
# The rider


class Rider:
    """The rider: skeleton, mesh measures of the hands (make_pray.Body), base clips."""

    def __init__(self, game, spec):
        import make_pray as mp
        self.mp = mp
        self.game = game
        self.data = game.granny(spec["model"])
        self.rig = Rig.of(gr2.load(self.data).root())
        read = gr2_mesh.read(self.data)
        self.idle = Animation.load(game.granny(ZAMB + "zamburak_rider_idle00"))
        base = self.rig.by_name(self.rig.pose(self.idle, 0.0))
        self.body = mp.Body(self.rig, {"mesh": read["meshes"][0], "skel": read["skeletons"][0]}, base, self.idle)
        self._anims = {}
        # at rest the rider faces +z: the head's and the chest's forward axes in their own frames
        rest = self.rig.by_name(self.rig.rest_worlds())
        self.face_local = rest["bip01 head"][:3, :3].T @ Z
        self.chest_local = rest["bip01 spine1"][:3, :3].T @ Z
        # how each elbow bends: the normal of the arm's plane in the upper arm's frame, from the idle
        # (both elbows bent, the fists on the reins)
        self.elbow_normal = {}
        for s in ("l", "r"):
            up, fo, ha = (base[f"bip01 {s} {b}"] for b in ("upperarm", "forearm", "hand"))
            n = np.cross(fo[:3, 3] - up[:3, 3], ha[:3, 3] - fo[:3, 3])
            self.elbow_normal[s] = unit(up[:3, :3].T @ unit(n))

    def anim(self, rel):
        if rel not in self._anims:
            self._anims[rel] = Animation.load(self.game.granny(rel))
        return self._anims[rel]

    def seated(self, anim, t, attach, square=True):
        """World frames (camel space) of a rider clip at t, hung on the camel's rider bone; with
        `square`, the trunk and head set square (see `square`)."""
        P = {k: attach @ v for k, v in self.rig.by_name(self.rig.pose(anim, t)).items()}
        return self.square(P, attach) if square else P

    def square(self, P, attach):
        """A firm seat: the stock zamburak rider leans about 35 degrees forward, turns his chest 35
        degrees and his face 50 to his right and tilts his head (measured on its idle); here the
        back is set nearly upright (LEAN), the chest turned back to the camel's way, the shoulders
        level and the head level (where he looks is `look`'s)."""
        from aoe3game.gr2_pose import rotate_about
        A = attach[:3, :3]
        side, up, fwd = A @ X, A @ Y, A @ Z
        sh = lambda Q: Q["bip01 r upperarm"][:3, 3] - Q["bip01 l upperarm"][:3, 3]  # noqa: E731
        ear = lambda Q: Q["bip01 head"][:3, :3] @ (self.body.base["bip01 head"][:3, :3].T @ X)  # noqa: E731
        back = lambda Q: Q["bip01 neck"][:3, 3] - Q["bip01 spine"][:3, 3]  # noqa: E731
        chest = lambda Q: Q["bip01 spine1"][:3, :3] @ self.chest_local  # noqa: E731
        crown = lambda Q: Q["bip01 head"][:3, :3] @ (self.body.base["bip01 head"][:3, :3].T @ Y)  # noqa: E731
        lean = math.sin(math.radians(self.LEAN))
        for bone, pivot, vec, axis, comp, want in (("bip01 spine1", "bip01 spine", back, side, fwd, lean),
                                                   ("bip01 spine1", "bip01 spine", chest, up, side, 0.0),
                                                   ("bip01 spine1", "bip01 spine", sh, fwd, up, 0.0),
                                                   ("bip01 head", "bip01 head", ear, fwd, up, 0.0),
                                                   ("bip01 head", "bip01 head", crown, side, fwd, 0.05)):
            asin = lambda x: math.degrees(math.asin(max(-1.0, min(1.0, x))))  # noqa: E731
            ang = abs(asin(float(unit(vec(P)) @ comp)) - asin(want))
            best = P
            for sign in (1.0, -1.0):
                Q = rotate_about(P, self.rig, bone, pivot, axis, sign * ang)
                if abs(float(unit(vec(Q)) @ comp) - want) < abs(float(unit(vec(best)) @ comp) - want):
                    best = Q
            P = best
        return P

    LEAN = 10.0               # degrees the seated trunk leans forward (the stock rider: about 35)

    def face(self, P):
        return unit(P["bip01 head"][:3, :3] @ self.face_local)

    # a man's head on his shoulders: how far it turns from where his chest carries it (degrees)
    HEAD_YAW, HEAD_UP, HEAD_DOWN = 65.0, 25.0, 35.0

    def crown(self, P):
        return unit(P["bip01 head"][:3, :3] @ (self.body.base["bip01 head"][:3, :3].T @ Y))

    def look(self, P, target, max_yaw=None, max_pitch=None):
        """`P` with the head turned to look at the world point `target`, in the head's own frame as
        the chest carries it (its face and its crown before the turn): about its crown, then up or
        down about its ear-to-ear axis, each within a man's limits (HEAD_YAW, HEAD_UP,
        HEAD_DOWN; `max_yaw` / `max_pitch` lower them). No roll: the hat stays square on the head.
        Only the head turns (the arms hang from the neck): a turn of the shoulders is
        `turn_trunk_to`'s, before the hands are placed."""
        from aoe3game.gr2_pose import rotate_about
        lim_yaw = self.HEAD_YAW if max_yaw is None else min(self.HEAD_YAW, max_yaw)
        lim_up = self.HEAD_UP if max_pitch is None else min(self.HEAD_UP, max_pitch)
        lim_down = self.HEAD_DOWN if max_pitch is None else min(self.HEAD_DOWN, max_pitch)
        head = P["bip01 head"][:3, 3]
        d = unit(np.asarray(target, np.float64) - head)
        f0, up = self.face(P), self.crown(P)
        f0 = unit(f0 - (f0 @ up) * up)
        yaw = math.degrees(math.atan2(float(d @ np.cross(up, f0)), float(d @ f0)))
        yaw = max(-lim_yaw, min(lim_yaw, yaw))

        def turned(Q0, axis, deg, want):
            """The turn about `axis` by +-deg whose face is nearer `want`."""
            best, err = Q0, None
            for sign in (1.0, -1.0):
                Q = rotate_about(Q0, self.rig, "bip01 head", "bip01 head", axis, sign * deg)
                e = float(np.linalg.norm(self.face(Q) - want))
                if err is None or e < err:
                    best, err = Q, e
            return best
        f1 = math.cos(math.radians(yaw)) * f0 + math.sin(math.radians(yaw)) * unit(np.cross(up, f0))
        P = turned(P, up, abs(yaw), f1)
        side = unit(np.cross(f1, up))
        pitch = math.degrees(math.atan2(float(d @ up), float(d @ f1)))
        pitch = max(-lim_down, min(lim_up, pitch))
        if getattr(self, "looks", None) is not None:         # a check's record of the turns
            self.looks.append((yaw, pitch))
        f2 = math.cos(math.radians(pitch)) * f1 + math.sin(math.radians(pitch)) * up
        return turned(P, side, abs(pitch), f2)

    def turn_trunk_to(self, P, target, share, most):
        """The chest turned about the vertical (at the spine's base) by `share` of the angle to
        `target`, at most `most` degrees: a man who looks far aside turns his shoulders too."""
        from aoe3game.gr2_pose import rotate_about
        c = unit(P["bip01 spine1"][:3, :3] @ self.chest_local)
        d = np.asarray(target, np.float64) - P["bip01 spine1"][:3, 3]
        a = math.degrees(math.atan2(c[2] * d[0] - c[0] * d[2], c[0] * d[0] + c[2] * d[2]))
        return rotate_about(P, self.rig, "bip01 spine1", "bip01 spine", Y, max(-most, min(most, share * a)))

    def standing(self, foot_rig, anim, t, heading, at):
        """An infantry clip's pose at t put on the rider (bones placed by name), turned by `heading`
        degrees about the vertical (90: facing the unit's right) and moved to `at` on the ground."""
        import make_dismount as md
        src = foot_rig.by_name(foot_rig.pose(anim, t))
        worlds = self.rig.by_name(self.rig.worlds(self.rig.localise(md.put_on(self.rig, src))))
        place = tr(at) @ rot4(axis_matrix(Y, heading))
        return {k: place @ v for k, v in worlds.items()}

    def turn(self, P, bone, axis, degrees):
        """The branch of `bone` turned about the world `axis` through the bone."""
        from aoe3game.gr2_pose import rotate_about
        return rotate_about(P, self.rig, bone, bone, axis, degrees)

    def hand(self, P, side, palm, finger, normal, pole):
        """The arm solved to the palm, bending the way an elbow bends (Rider.elbow_normal): its
        twist never flips between two frames and the elbow never bends backward."""
        return self.body.place_hand(P, side, palm, finger, normal, pole, bend_normal=self.elbow_normal[side])

    def palm_of(self, P, side):
        hand = P[f"bip01 {side} hand"]
        return point(hand, self.body.palm_local[side])

    def to_local(self, worlds, attach):
        inv = np.linalg.inv(attach)
        return self.rig.localise({k: inv @ v for k, v in worlds.items()})

    def track_bytes(self, name, times, locals_, like):
        tracks = [(bone, times, np.array([f[i][0] for f in locals_]), np.array([f[i][1] for f in locals_]))
                  for i, bone in enumerate(self.rig.names)]
        return animation_file(name, float(times[-1]), self.rig.names[0], tracks, basis=self.rig.basis,
                              accumulation=like.accumulation, timestep=like.timestep, source=name)


# --------------------------------------------------------------------------------------------------
# The clips


SHOTS = 6                 # shots a firing clip (the stock gun's six Attack tags)
# The gun turned on its mount (yaw about the post's axis): A's chest turns by AIM_TRUNK's share of
# how far the grips moved about his spine (at most its limit, degrees) and he leans in up to
# AIM_LEAN degrees at 90; past AIM_SWAP (within AIM_BLEND) his left hand moves from the breech's
# top down to the breech box's near side. AIM_ANGLES: the preview's yaws.
AIM_TRUNK = {"A": (1.6, 45.0), "B": (0.4, 30.0)}
AIM_LEAN = 18.0
# the reload's reach to the pocket at his left hip: the chest turned toward it (share of the angle,
# at most degrees) and leaned over to his left (degrees about the unit's forward axis)
POCKET_TRUNK = (0.45, 28.0)
# B on foot's long handles (round 4): the drop crank this far below the gun's crank (metres, in the
# world at the lying camel's fire pose), the traverse bar's grip this far back and down from the
# breech's top
HANDLE_DROP = 0.25
HANDLE_BAR = (0.25, 0.45)
# the handles' versions (recipe "handles"): v4, the drop crank's axle straight under the gun's crank
# and the bar 25 cm back, his stations beside the gun (his right palm ended 31-40 cm behind his
# shoulder); v5, the drop crank's axle also HANDLE_SETS["v5"]["crank_back"] back and "crank_out"
# outboard (a slanted shaft, a gear box at each end) and the bar 15 cm back, so both grips sit side
# by side behind the breech, like handlebars, and he stands behind the turret with both hands in front
# of his chest (Traverse, "palms_ahead")
HANDLE_SETS = {"v4": {"crank_back": 0.0, "crank_out": 0.0, "bar": (0.25, 0.45)},
               "v5": {"crank_back": 0.30, "crank_out": 0.18, "bar": (0.15, 0.45), "bar_side": 0.18}}
HANDLES = "v5"
# B on foot, deployed (round 6, 2026-11-26): the gun rests across the lying camel, its arc's bisector
# square to the camel's spine, B_HOME degrees toward the unit's right (the side away from the gunner),
# and turns over B_ARC (degrees, the unit's right positive) about it; the gunner works it from the
# other side. B_SEGMENTS stations each side of home. The deploy swings the gun from ahead to home and
# the undeploy back; every clip he works the gun in has it at home, so the game's yaw is the clip's
# plus the turn from home (the aim file's home yaw). Recipe "b_home", "b_arc", "b_segments".
B_HOME = 90.0
B_ARC = (30.0, 150.0)
B_SEGMENTS = 2
# v5 stations: each palm at least PALM_AHEAD metres in front of its shoulder along his facing, the
# elbows bent ELBOW_BEND degrees (from straight), preferably the middle
PALM_AHEAD = 0.15
ELBOW_BEND = (20.0, 60.0)
ELBOW_SEARCH = (15.0, 60.0)     # the band the station search aims for: room for his lean and chest turn
B_CARRY_END = 0.76        # B's carry to the hopper ends here (share of the reload); seated by B_SEAT
B_SEAT = 0.84             # B: the new magazine seated (A: 0.82), pressed home by B_SEAT + 0.04
B_HAND_ARC = 0.28         # B's hand swings this far in front of him on its way down to the pocket
B_HAND_CLEAR = 0.50       # B's reloading hand stays this far from his shoulder
B_CARRY_ARC = 0.45        # metres in front of his left shoulder B's hand passes on its way to the hopper
B_RELOAD_LEAN_BACK = -24.0  # degrees B leans (- forward, in toward the hopper) to seat the new magazine
LONG_ARM = 0.42          # shoulder to palm on the long handles (metres): elbows bent
POCKET_LEAN = 12.0
# in a death where the camel rolls over: when the spare magazine leaves the camel's body for the
# gun's hopper (seconds; the camel's body still hides it until about 0.6 s)
DEATH_SPARE_AT = 0.45
AIM_SWAP = 45.0
AIM_BLEND = 30.0
B_LEFT = 90.0
STEP_LIMIT = 0.0
AIM_ANGLES = (-90.0, -45.0, 0.0, 45.0, 90.0)
# Whole turns a firing clip (so repeated shots join); the crank turns a third as fast as the barrels,
# as on the stock gun. The stock gun peaks near 7 turns a second, but its six barrels then step
# 44 degrees a frame at 60 frames a second and seem to turn backward; at 3 a second they step 18
# degrees at 60 frames and 12 at the GIFs' 15 (60-degree symmetry): they read as turning forward.
BARREL_TURNS = 3
CRANK_TURNS = 1
FOOT_MODEL = "WoL\\units\\infantry_ranged\\skirmisher\\skirmisher_age2"
STAND_CLIP = LIB + "range\\volley\\volley_standing_idle"
B_DOWN = LIB + "quads\\bighorn_sheep_laydownA"
B_IDLE = LIB + "quads\\bighorn_sheep_laydown_idleA"
B_UP = LIB + "quads\\bighorn_sheep_laydown_getup"
FOOT_DEATH = LIB + "range\\death_standing_rifleman_A"
# round 6: facing the camel at his station across it, he falls backward, away from it (the rifleman's A falls
# forward, into the camel; its B starts in the air)
FOOT_DEATH_BACK = LIB + "range\\defend\\defend_death"
CAMEL_DEATH = "units\\asians\\indians\\sowar\\sowarCamel_death00"
RIDER_DEATH = LIB + "cavalry\\sword_deathA"       # 3.0 s, as long as the camel's

# The clips of each variant: our name, the anim name it plays under, where the camel's motion comes
# from (a stock clip of the camel, a borrowed lying-down clip of the same rig laid on the ground, or
# still at a borrowed clip's first frame), the rider's base clip, and what the gun and hands do.
CLIPS = {
    # A: at the gun (idle, fire, reload) the camel keeps its head and neck lowered (`lower` degrees,
    # `dip` more in the middle of a burst), out of the line of fire; on the move it carries them as
    # its own clips do, but for the jog (lowered 26) and the gallop (12), which lift it into the barrel.
    # The rider moves on an upright seat (`gait`: a small nod of the trunk with the
    # steps, no sway) instead of the stock rider walk and sword jog, whose hips and shoulders sway.
    "A": [
        {"name": "idle", "anim": "Idle", "camel": ZAMB + "zamburak_camel_idle00",
         "rider": ZAMB + "zamburak_rider_idle00", "lower": 22.0},
        {"name": "walk", "anim": "Walk", "camel": ZAMB + "zamburak_camel_walk00", "gait": 1.5},
        {"name": "jog", "anim": "Jog", "camel": ZAMB + "zamburak_camel_jog", "gait": 3.0, "lower": 26.0},
        # the gallop moves the rider's bone against the chest (the gun rises and falls 0.13 against him
        # each stride, and a hand on it flipped its elbow): both fists on the reins there
        {"name": "run", "anim": "Run", "camel": LIB + "cavalry\\horse_gallop", "gait": 4.0, "lower": 12.0,
         "reins_only": True},
        {"name": "fire", "anim": "Attack_ranged", "camel": ZAMB + "zamburak_camel_attackRanged01", "do": "fire",
         "lower": 22.0, "dip": 6.0},
        {"name": "reload", "anim": "Attack_ranged_reload", "camel": ZAMB + "zamburak_camel_reload",
         "do": "reload", "lower": 22.0},
    ],
    "B": [
        {"name": "idle", "anim": "Idle", "camel": ZAMB + "zamburak_camel_idle00",
         "rider": ZAMB + "zamburak_rider_idle00", "seat": True},
        {"name": "walk", "anim": "Walk", "camel": ZAMB + "zamburak_camel_walk00", "gait": 1.5, "seat": True},
        {"name": "jog", "anim": "Jog", "camel": ZAMB + "zamburak_camel_jog", "gait": 3.0, "lower": 26.0,
         "seat": True},
        {"name": "run", "anim": "Run", "camel": LIB + "cavalry\\horse_gallop", "gait": 4.0, "lower": 12.0,
         "reins_only": True, "seat": True},
        # the lying-down clip, then the camel held down while he gets off step by step (2 s)
        {"name": "deploy", "anim": "Bombard_unlimber", "borrow": B_DOWN, "do": "dismount", "hold_after": 2.0},
        {"name": "deployed", "anim": "Bombard_ranged_idle", "borrow": B_IDLE, "do": "stand"},
        {"name": "fire", "anim": "Bombard_ranged_attack", "still": B_IDLE, "length": 1.0, "do": "fire"},
        {"name": "reload", "anim": "Bombard_reload", "still": B_IDLE, "length": 3.0, "do": "reload"},
        # the camel held down while he gets on step by step (2 s), then its getting-up clip
        {"name": "undeploy", "anim": "Bombard_limber", "borrow": B_UP, "do": "mount", "hold_before": 2.0},
        # killed while deployed: the lying camel rolls onto its right side, the gunner falls at the gun
        {"name": "death", "anim": "Bombard_death", "still": B_IDLE, "length": 3.0, "do": "foot_death"},
    ],
}
# the reload: (share of the clip, where the magazine is) - the left hand leaves the casing for the
# magazine, lifts it out, puts it down at the bag, takes it up again, seats it and goes back
RELOAD = [(0.00, "rest"), (0.12, "seated"), (0.28, "lifted"), (0.45, "bag"), (0.50, "bag low"), (0.55, "bag"),
          (0.72, "lifted"), (0.85, "seated"), (1.00, "rest")]
# B when the gunner stays mounted (the default since 2026-11-24, the user's choice): mounted it is A
# (A's clips), deployed the camel lies down and he fires from the saddle, as A does, the gun turning
# on its post a full 90 degrees each way; to lie down and to rise he holds the reins.
CLIPS["B_mounted"] = [dict(c) for c in CLIPS["A"] if c["name"] in ("idle", "walk", "jog", "run")] + [
    {"name": "deploy", "anim": "Bombard_unlimber", "borrow": B_DOWN, "reins": True},
    {"name": "deployed", "anim": "Bombard_ranged_idle", "borrow": B_IDLE, "at_gun": True},
    {"name": "fire", "anim": "Bombard_ranged_attack", "still": B_IDLE, "length": 1.0, "do": "fire"},
    {"name": "reload", "anim": "Bombard_reload", "still": B_IDLE, "length": 3.0, "do": "reload"},
    {"name": "undeploy", "anim": "Bombard_limber", "borrow": B_UP, "reins": True},
    # killed while deployed: the lying camel rolls onto its right side, the gunner falls off the saddle
    {"name": "death", "anim": "Bombard_death", "still": B_IDLE, "length": 3.0, "do": "fall", "roll": True},
]


def clips_of(variant, recipe):
    """The clips a variant is made of (B: mounted by default, on foot with recipe "b_mounted" false)."""
    if variant == "B" and recipe.get("b_mounted", False):
        return CLIPS["B_mounted"]
    return CLIPS[variant]


class Built:
    def __init__(self, clip, times):
        self.clip, self.times = clip, np.asarray(times, np.float64)
        self.camel, self.gun, self.rider, self.flash = [], [], [], []
        self.camel_bytes = self.gun_bytes = self.rider_bytes = None
        self.reach = 0.0              # the largest distance from a hand's palm to its target


class Unit:
    """One variant at one gun scale: the camel, the gun design, the rider, and their clips."""

    def __init__(self, recipe, camel, rider, src, variant, scale, foot=None):
        self.r, self.camel, self.rider, self.variant = recipe, camel, rider, variant
        # how the gunner works the gun: "A" seated behind it (A, and B when it stays mounted: the
        # camel lies down and he fires from the saddle, recipe "b_mounted"), "B" on foot beside it
        # (the gun mirrored, its crank outside)
        self.style = "A" if variant == "A" or recipe.get("b_mounted", False) else "B"
        self.clips = clips_of(variant, recipe)
        self.gun = GunDesign(src, camel.hang_bind, recipe["_post"], scale, mirror=(self.style == "B"),
                             forward=recipe.get("forward", 0.0))
        if recipe.get("_post_base") is not None:
            self.gun.add_post(recipe["_post_base"], (recipe.get("post") or {}).get("radius", 0.032))
        self.scale = scale
        self.tag = f"{variant}{int(round(scale * 100)):02d}"
        self.gun_name = f"{recipe['name']}_gun_{self.tag}"
        self.foot = foot
        g = self.gun
        c = src.parts["cannon"]["positions"]
        rear = c[c[:, 2] < src.trunnion[2] + 0.3]                     # the casing, not the front ring
        back = rear[rear[:, 2] < rear[:, 2].min() + 0.35]               # its rear box, by the breech
        inner = back[:, 0].max() if self.style == "A" else back[:, 0].min()   # the rider's side
        self.casing_side = g.design_point(np.array([inner, 0.5 * (back[:, 1].min() + back[:, 1].max()),
                                                    back[:, 2].mean()]))
        outer = back[:, 0].min() if self.style == "A" else back[:, 0].max()   # the other side of the box
        self.casing_outer = g.design_point(np.array([outer, 0.5 * (back[:, 1].min() + back[:, 1].max()),
                                                     back[:, 2].mean()]))
        self.casing_top = g.design_point(np.array([src.trunnion[0], rear[:, 1].max(), src.trunnion[2]]))
        # the hand takes the magazine low, just above the hopper (its top is out of a man's reach
        # on foot)
        self.mag_grip = (g.mag_base - g.at["ammo"]) + np.array([0.0, 0.22 * (g.mag_top[1] - g.mag_base[1]), 0.0])
        self.stash_spare()
        # B on foot: the long handles (round 4, the user's choice): his left hand on a drop crank,
        # his right on a traverse bar, both at his chest
        self.long = self.style == "B" and recipe.get("long_handles", True)
        self.handle_set = recipe.get("handles", HANDLES)
        if self.long:
            self.long_handles(recipe.get("handle_drop", HANDLE_DROP))
        # round 6: B on foot's gun at rest across the camel (B_HOME), its arc about it; else ahead (0)
        if self.long and self.handle_set != "v4" and recipe.get("b_home", B_HOME):
            self.home = float(recipe.get("b_home", B_HOME))
            self.arc = tuple(float(v) for v in recipe.get("b_arc", B_ARC))
            self.segments_per_side = int(recipe.get("b_segments", B_SEGMENTS))
        else:
            self.home = 0.0
            self.arc = (-30.0, 90.0) if self.style == "B" else (-90.0, 90.0)
            self.segments_per_side = 0

    def home_frames(self, state=None):
        """The gun's frames for a state with the gun at its rest yaw (B on foot: across the camel)."""
        s = dict(state or {})
        s.setdefault("yaw", self.home)
        return self.gun.frames(s)

    def home_turn(self):
        """The design-space turn from the gun ahead to its rest yaw (identity when it rests ahead)."""
        return self.gun.yaw_matrix(self.home) if self.home else np.eye(4)

    # the deploy's last part (round 6): his hands go from the saddle to the grips with the gun still
    # ahead (SWING[0] of the climb, the rest of the window after he stands at the saddle), then he
    # swings the gun round to its rest yaw while he steps to his station (SWING[1]); the undeploy is
    # the same backward
    SWING = (0.25, 1.0)

    def clip_yaw(self, clip, t, length, b):
        """The gun's yaw in our own clip at time t (degrees): its rest yaw while he works it on foot,
        swung from ahead to it at the end of the deploy and back at the start of the undeploy."""
        if not self.home:
            return 0.0
        do = clip.get("do")
        if do in ("stand", "fire", "reload", "foot_death"):
            return self.home
        if do in ("dismount", "mount"):
            t0, t1 = getattr(b, "window", (0.0, length))
            k = (t - t0) / max(t1 - t0, 1e-9)
            k = k if do == "dismount" else 1.0 - k
            return self.home * self.swing_share(k)
        return 0.0

    def swing_share(self, k):
        """How far (0..1) the gun has swung from ahead to its rest yaw at share k of the climb."""
        s4 = self.CLIMB_SHARES_HOME[4]
        a = s4 + (1.0 - s4) * self.SWING[0]
        b_ = s4 + (1.0 - s4) * self.SWING[1]
        return smooth(min(1.0, max(0.0, (k - a) / max(b_ - a, 1e-9))))

    # -- the gun in the world (camel space) at a camel pose

    def C(self, P):
        return rigid(P[self.camel.hang]) @ self.gun.S

    @staticmethod
    def world_dir(C, v):
        return unit(C[:3, :3] @ np.asarray(v, np.float64))

    # -- the hands' targets: (palm in design space, finger, normal), design directions

    def target(self, what, fr):
        """(palm, finger, normal) in design space; the directions turn with the gun's yaw (the
        casing's frame is the trunnion turned, unrotated at rest)."""
        palm, fin, nor = self._target(what, fr)
        turn = fr["cannon"][:3, :3]
        return palm, turn @ np.asarray(fin, np.float64), turn @ np.asarray(nor, np.float64)

    def _target(self, what, fr):
        g, side = self.gun, (1.0 if self.style == "A" else -1.0)
        if what == "crank":
            palm = g.handle_at(fr) + point(fr["cannon"] @ tr(-g.pivot), np.array([side * 0.07 * g.s, 0.0, 0.0])) \
                - point(fr["cannon"] @ tr(-g.pivot), np.zeros(3))
            return palm, (0.0, -0.55, 1.0), (0.0, -1.0, -0.35)
        if what == "crank_l":                # the crank's handle in the left hand (the gun turned far right)
            palm = g.handle_at(fr) + point(fr["cannon"] @ tr(-g.pivot), np.array([side * 0.07 * g.s, 0.0, 0.0])) \
                - point(fr["cannon"] @ tr(-g.pivot), np.zeros(3))
            return palm, (0.0, -0.55, -1.0), (0.0, -1.0, 0.35)
        if what == "breech":
            return point(fr["cannon"] @ tr(-g.pivot), g.breech_top) + np.array([0.0, 0.03, 0.02]), \
                (0.0, -0.1, 1.0), (0.0, -1.0, 0.0)
        if what == "casing":
            return point(fr["cannon"] @ tr(-g.pivot), self.casing_top) + np.array([0.0, 0.03, 0.0]), \
                (1.0, -0.2, 0.3), (0.0, -1.0, 0.0)
        if what == "casing_side":           # the palm flat on the breech box's inner side
            # (the offset turns with the gun: the casing's frame is rigid)
            return point(fr["cannon"] @ tr(-g.pivot), self.casing_side + np.array([0.035, 0.0, 0.0])), \
                (0.0, -0.25, 1.0), (-1.0, 0.0, 0.0)
        if what == "casing_outer":          # the palm flat on the breech box's outer side
            return point(fr["cannon"] @ tr(-g.pivot), self.casing_outer + np.array([-0.035, 0.0, 0.0])), \
                (0.0, -0.25, 1.0), (1.0, 0.0, 0.0)
        if what == "magazine":
            return point(fr["ammo"], self.mag_grip) + np.array([side * 0.045, 0.0, 0.0]), \
                (0.0, 0.2, 1.0), (-side, 0.0, 0.0)
        if what == "dropcrank":             # the drop crank's handle in the left hand (B, long handles)
            out = self.handles["out_d"]
            palm = point(fr["crank2"], g.handle - g.at["crank"]) + point(fr["cannon"] @ tr(-g.pivot), out * 0.06) \
                - point(fr["cannon"] @ tr(-g.pivot), np.zeros(3))
            return palm, (0.0, -0.55, 1.0), (-out[0], -1.0, -0.35)
        if what == "bar":                   # the traverse bar's grip in the right hand, from behind
            palm = point(fr["cannon"] @ tr(-g.pivot), self.handles["grip_d"] - 0.03 * self.handles["fwd_d"])
            return palm, (0.0, -1.0, 0.25), (0.0, -0.2, 1.0)
        raise KeyError(what)

    def long_handles(self, drop):
        """B on foot's long handles, made in design space at the lying camel's fire pose: a drop
        crank (a copy of the gun's crank, `drop` metres lower and a little outboard, on the bone
        crank2, which turns with the gun's crank), an iron shaft between two small gear boxes joining
        the two axles, and a traverse bar from the middle of the breech's rear face back HANDLE_BAR[0]
        and down HANDLE_BAR[1] metres to a crosswise grip. All but the drop crank hang on the casing."""
        g, cam, src = self.gun, self.camel, self.gun.src
        P = cam.fix_hang(cam.grounded(cam.anim(B_IDLE), [0.0])[0])
        C = self.C(P)
        inv = np.linalg.inv(C)
        A = C[:3, :3]
        down_w = np.array([0.0, -1.0, 0.0])
        out_d = np.array([math.copysign(1.0, g.at["crank"][0] - g.pivot[0]), 0.0, 0.0])   # the crank's side
        out_w = unit(A @ out_d)
        fwd_w = unit(A @ Z)
        fwd_w = unit(fwd_w - (fwd_w @ Y) * Y)
        axle_w = point(C, g.at["crank"])
        hs = HANDLE_SETS[self.handle_set]
        low_w = axle_w + drop * down_w + (0.03 + hs["crank_out"]) * out_w - hs["crank_back"] * fwd_w
        g.at["crank2"] = point(inv, low_w)
        parts = g.parts()
        cpos, cnrm, cuv, ctri, cmat, ctan = parts["crank"]
        made = {"dropcrank": ((cpos + (g.at["crank2"] - g.at["crank"]), cnrm, cuv, ctri, cmat, ctan), "crank2")}
        width = src.parts["cannon"]["tangents"].shape[1]

        def mesh(pos_w, nrm_w, tris):
            pos = apply(inv, np.asarray(pos_w))
            nrm = np.array([unit(inv[:3, :3] @ n) for n in nrm_w])
            tan = np.array([np.r_[unit(np.cross(n, Y) if abs(n @ Y) < 0.9 else np.cross(n, X)), 1.0] for n in nrm])
            uvs = np.array([src.iron_uv] * len(pos))
            return (pos, nrm, uvs, np.asarray(tris, np.int64), [src.iron_material] * len(tris), tan[:, :width])

        def merge(*ms):
            pos, nrm, tris = [], [], []
            for p_, n_, t_ in ms:
                base = len(pos)
                pos += list(p_)
                nrm += list(n_)
                tris += [(a + base, b + base, c + base) for a, b, c in t_]
            return pos, nrm, tris

        def cylinder(a, b, r, n=10):
            ax = unit(b - a)
            u_ = unit(np.cross(ax, X if abs(ax @ X) < 0.9 else Z))
            v_ = np.cross(ax, u_)
            pos, nrm, tris = [], [], []
            for k in range(n):
                ang = 2 * math.pi * k / n
                d = math.cos(ang) * u_ + math.sin(ang) * v_
                pos += [a + r * d, b + r * d]
                nrm += [d, d]
            for k in range(n):
                i0, i1, j0, j1 = 2 * k, 2 * k + 1, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1
                tris += [(i0, j0, i1), (i1, j0, j1)]
            for end, sgn in ((a, -1.0), (b, 1.0)):         # caps
                c0 = len(pos)
                pos.append(end)
                nrm.append(sgn * ax)
                ring = []
                for k in range(n):
                    ang = 2 * math.pi * k / n
                    pos.append(end + r * (math.cos(ang) * u_ + math.sin(ang) * v_))
                    nrm.append(sgn * ax)
                    ring.append(c0 + 1 + k)
                for k in range(n):
                    p0, p1 = ring[k], ring[(k + 1) % n]
                    tris.append((c0, p1, p0) if sgn > 0 else (c0, p0, p1))
            return pos, nrm, tris

        def box(c, ax_x, ax_y, ax_z, h):
            pos, nrm, tris = [], [], []
            axes = [unit(ax_x), unit(ax_y), unit(ax_z)]
            for i in range(3):
                for sgn in (1.0, -1.0):
                    n_ = sgn * axes[i]
                    j, k = axes[(i + 1) % 3], axes[(i + 2) % 3]
                    hj, hk = h[(i + 1) % 3], h[(i + 2) % 3]
                    base = len(pos)
                    f = c + n_ * h[i]
                    for sj, sk in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                        pos.append(f + sj * hj * j + sk * hk * k)
                        nrm.append(n_)
                    tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)] if sgn > 0 else \
                        [(base, base + 2, base + 1), (base, base + 3, base + 2)]
            return pos, nrm, tris
        # the shaft and its gear boxes, inboard of the two crank arms
        inb = -0.035 * out_w
        top_box = axle_w + inb + 0.01 * out_w
        low_box = low_w + inb
        shaft = cylinder(top_box + 0.03 * down_w, low_box - 0.03 * down_w, 0.012)
        boxes = merge(box(top_box, out_w, Y, fwd_w, (0.022, 0.035, 0.035)),
                      box(low_box, out_w, Y, fwd_w, (0.022, 0.035, 0.035)))
        made["dropshaft"] = (mesh(*merge(shaft, boxes)), "cannon")
        # the traverse bar
        bt_w = point(C, g.breech_top)
        back, down = hs["bar"]
        start = bt_w - 0.02 * fwd_w + 0.04 * down_w
        grip = bt_w - back * fwd_w + down * down_w + hs.get("bar_side", 0.0) * out_w
        side_w = unit(np.cross(Y, fwd_w))
        bar = merge(cylinder(start + 0.03 * fwd_w, grip, 0.012), cylinder(grip - 0.06 * side_w, grip + 0.06 * side_w, 0.016),
                    box(start + 0.01 * fwd_w, side_w, Y, fwd_w, (0.03, 0.025, 0.012)))
        made["traversebar"] = (mesh(*bar), "cannon")
        g.made.update(made)
        self.handles = {"out_d": out_d, "grip_d": point(inv, grip), "fwd_d": unit(inv[:3, :3] @ fwd_w),
                        "low_w": low_w, "grip_w": grip, "C": C, "P": P}
        return made

    def poles(self):
        if self.style == "A":              # elbows out to the sides: a firm grip, not tucked in
            # the right one level and back (2026-11-26): with the post centred the crank's handle goes
            # round below his right shoulder, and an elbow aimed down turned over for a frame of the
            # fire (his hand at 3840 deg/s)
            return {"r": np.array([1.0, 0.0, -0.6]), "l": np.array([-1.0, -0.6, -0.4])}
        return {"r": np.array([-0.4, -1.0, -1.0]), "l": np.array([-0.4, -1.0, 1.0])}

    def solve_hands(self, P, C, fr, want, built=None):
        """`P` with each side's hand on its target: want {side: a target name, or (palm, finger,
        normal) in design space}; how far a palm stays from its target is kept in `built.reach`."""
        poles = self.poles()
        for s, w in want.items():
            if w is None:
                continue
            palm_d, fin, nor = self.target(w, fr) if isinstance(w, str) else w
            palm = point(C, palm_d)
            P = self.rider.hand(P, s, palm, self.world_dir(C, fin), self.world_dir(C, nor),
                                self.world_dir(C, poles[s]))
            if built is not None:
                built.reach = max(built.reach, float(np.linalg.norm(self.rider.palm_of(P, s) - palm)))
        return P

    # -- the gun's states

    def fire_state(self, t, length):
        u = t / length
        shot = length / SHOTS
        k = (t + 0.5 * shot) % shot                      # time since the last shot (at the half steps)
        recoil = 0.018 * self.gun.s * math.exp(-k / 0.035) if 0.25 * shot <= t <= length - 0.25 * shot else 0.0
        return {"barrel": 360.0 * BARREL_TURNS * u, "crank": -360.0 * CRANK_TURNS * u, "recoil": recoil}

    @staticmethod
    def shots(length):
        return [(k + 0.5) * length / SHOTS for k in range(SHOTS)]

    def magazine_keys(self, bag_design):
        g = self.gun
        seat = g.at["ammo"]
        share = 0.40 if self.style == "A" else 0.10         # on foot the gunner reaches less high
        lift = seat + np.array([0.0, share * (g.mag_top[1] - g.mag_base[1]), 0.0])
        where = {"rest": (seat, 0.0), "seated": (seat, 0.0), "lifted": (lift, 0.0), "bag": (bag_design, 35.0),
                 "bag low": (bag_design + np.array([0.0, -0.03, 0.0]), 35.0)}
        return Keys([(share, {"p": where[w][0], "tilt": where[w][1]}) for share, w in RELOAD])

    def magazine_frame(self, keys, u):
        c = keys.at(u)
        side = 1.0 if self.style == "A" else -1.0
        # tipped outward (away from the rider) about the forward axis while it is away
        return tr(c["p"]) @ rot4(axis_matrix(Z, -side * c["tilt"]))

    def reload_hand(self, u, fr):
        """The left hand during a reload: at its rest place, on the magazine, or between the two."""
        rest = "breech" if self.style == "A" else "casing"
        if RELOAD[1][0] < u < RELOAD[-2][0]:
            return "magazine"
        if u <= RELOAD[1][0]:
            a, b, w = rest, "magazine", u / RELOAD[1][0]
        else:
            a, b, w = "magazine", rest, (u - RELOAD[-2][0]) / (1.0 - RELOAD[-2][0])
        pa, fa, na = self.target(a, fr)
        pb, fb, nb = self.target(b, fr)
        w = smooth(w)
        arc = np.array([0.0, 0.06, 0.0]) * math.sin(math.pi * w)
        return (pa + w * (pb - pa) + arc, unit((1 - w) * np.array(fa) + w * np.array(fb)),
                unit((1 - w) * np.array(na) + w * np.array(nb)))

    # -- the reload with a new magazine (recipe "reload": "toss"; seated gunner)

    # the pocket at his left hip: the full magazine stands in it, its top POCKET_TOP above his left
    # hip joint and POCKET_OUT outside it, POCKET_FWD forward, its top leaning POCKET_LEAN_OUT
    # degrees out to his left and its foot tipped POCKET_TILT forward: the foot reaches in under his
    # hip into the saddle, hidden in his hip, the saddle and the camel. He draws it out along its
    # own length (POCKET_DRAW), up and out to his left, clear of his side
    POCKET_OUT, POCKET_TOP, POCKET_FWD, POCKET_TILT = 0.06, 0.02, 0.0, 10.0
    POCKET_LEAN_OUT, POCKET_DRAW = 30.0, 0.50

    def stash_spare(self):
        """The spare magazine's place out of a reload (GunDesign.stash): lying along the camel
        inside its body, under the saddle (the middle of the body's depth below the gunner's
        pelvis), so no clip shows it and the gun's yaw does not move it (it hangs on the root)."""
        cam, g = self.camel, self.gun
        # the rider's bone where the clips keep it (fix_hang: on the chest, risen with the hump)
        P0 = cam.fix_hang(cam.pose(cam.anim(CLIPS["A"][0]["camel"]), 0.0))
        C0 = self.C(P0)
        inv0 = np.linalg.inv(C0)
        R = self.rider.seated(self.rider.idle, 0.0, rigid(P0[cam.rider_bone]))
        pel = R["bip01 pelvis"][:3, 3]
        # the vertical through the body under him: the saddle's top, then the belly (the highest
        # surface well below it)
        ys = cam.surface_heights(P0, pel[0], pel[2] + 0.10)
        ys = ys[ys < pel[1]]
        hi = float(ys.max())
        below = ys[ys < hi - 0.25]
        lo = float(below.max()) if len(below) else hi - 0.6
        # 0.27 above the spine's line (chest to pelvis), inside the body under the saddle: with the hump
        # (2026-11-26) the surfaces under him no longer gave the middle of its depth (it came out under the
        # belly), and the pocket it moves to as the reload begins rose with his seat (the move, out of
        # sight, stays one frame's worth under the props' speed)
        spine_y = 0.5 * (P0[cam.mount][1, 3] + P0["hs bone pelvis"][1, 3])
        centre = point(inv0, np.array([pel[0], spine_y + 0.27, pel[2]]))
        mid = 0.5 * (g.mag_top + g.mag_base)
        seat = g.at["ammo"]
        g.stash = tr(centre) @ rot4(axis_matrix(X, 90.0)) @ tr(seat - mid)
        self.stash_info = {"saddle": hi, "belly": lo, "centre": centre}
        return g.stash

    # on foot (B): the pocket runs down the outside of his left thigh, POCKET_FOOT_OUT off its axis,
    # its top POCKET_FOOT_TOP above the hip joint (under his coat); standing, straight up the thigh would run into his
    # side, so he draws it up and out to his left, POCKET_FOOT_DRAW_OUT degrees from the thigh's
    # line, and it leans out that way as it comes
    POCKET_FOOT_OUT, POCKET_FOOT_TOP = 0.04, 0.10
    POCKET_FOOT_DRAW_OUT = 40.0
    POCKET_FOOT_DRAW = 0.25          # standing, drawn this far: out of the pocket, at his waist

    def base_body(self, P):
        """The gunner's body a reload starts from, before his hands are placed: seated on the camel
        (A, and B mounted) or standing at the gun (B on foot)."""
        if self.style == "A":
            return self.rider.seated(self.rider.idle, 0.0, rigid(P[self.camel.rider_bone]))
        if getattr(self, "_reload_t", None) is not None and self.steps_in():
            return self.traverse.reload_body(self._reload_t)     # v5: stepped in to the hopper
        return self.station_body()

    def body_axes(self, R):
        """His (right, up, forward) in the world, level: from his hips."""
        right = R["bip01 r thigh"][:3, 3] - R["bip01 l thigh"][:3, 3]
        right[1] = 0.0
        right = unit(right)
        return right, Y.copy(), unit(np.cross(right, Y))

    def pocket(self, P, R=None):
        """The full magazine in the pocket at the gunner's left hip, at the camel pose P and his
        body R (default: the body a reload starts from): (design frame, his (right, up, forward)
        in the world, the pocket's top in the world, the way it is drawn out (world, along its
        length toward its top))."""
        g = self.gun
        C = self.C(P)
        R = self.base_body(P) if R is None else R
        hip = R["bip01 l thigh"][:3, 3]
        right, up, fwd = self.body_axes(R)
        if self.style == "A":
            top = hip - self.POCKET_OUT * right + self.POCKET_TOP * Y + self.POCKET_FWD * fwd
            Rw = np.c_[right, Y, fwd] @ axis_matrix(Z, self.POCKET_LEAN_OUT) @ axis_matrix(X, -self.POCKET_TILT)
        else:
            along = unit(R["bip01 l thigh"][:3, 3] - R["bip01 l calf"][:3, 3])     # up the thigh
            side = unit(right - (right @ along) * along)
            front = unit(np.cross(side, along))
            if float(front @ fwd) < 0:
                front = -front
            top = hip - self.POCKET_FOOT_OUT * side + self.POCKET_FOOT_TOP * along
            Rw = np.c_[side, along, front]
            if np.linalg.det(Rw) < 0:
                Rw = np.c_[side, along, -front]
            out = math.radians(self.POCKET_FOOT_DRAW_OUT)
            seat = g.at["ammo"]
            W = tr(top - Rw @ (g.mag_top - seat)) @ rot4(Rw)
            return np.linalg.inv(C) @ W, (right, up, fwd), top, unit(math.cos(out) * along - math.sin(out) * side)
        seat = g.at["ammo"]
        o = top - Rw @ (g.mag_top - seat)
        W = tr(o) @ rot4(Rw)
        return np.linalg.inv(C) @ W, (right, up, fwd), top, unit(Rw @ Y)

    def reload_times(self):
        """The reload's beats as shares of its 3.00 s: the left hand takes the empty magazine (take),
        it is lifted (lifted) and let go (rel), the hand is at the pocket (pocket) and closed on the
        full one (closed), drawn (drawn), changes its grip on the way (regrip), the carry ends over the
        hopper (carry_end), seated (seat), pressed home (press, a share of its own), the hand back on
        its grip (back); the chest turned to the pocket (turn) and leaning in to the hopper (hop).
        B with the v5 handles walks in to the hopper first and back at the end (Traverse.RELOAD_*):
        the beats between are the same, closer together."""
        if self.style == "A":
            return {"take": 0.10, "lifted": 0.22, "rel": 0.34, "pocket": 0.48, "closed": 0.52, "drawn": 0.62,
                    "regrip": 0.74, "carry_end": 0.76, "seat": 0.82, "press": 0.04, "back": 1.0,
                    "turn": (0.36, 0.66), "hop": (0.62, 0.95)}
        if not self.steps_in():
            return {"take": 0.10, "lifted": 0.22, "rel": 0.34, "pocket": 0.48, "closed": 0.52, "drawn": 0.62,
                    "regrip": 0.74, "carry_end": B_CARRY_END, "seat": B_SEAT, "press": 0.04, "back": 1.0,
                    "turn": (0.36, 0.66), "hop": (0.62, 0.95)}
        s = lambda t: t / 3.0
        return {"take": s(0.45), "lifted": s(0.66), "rel": s(1.02), "pocket": s(1.42), "closed": s(1.52),
                "drawn": s(1.80), "regrip": s(2.22), "carry_end": s(2.22), "seat": s(2.36), "press": s(0.10),
                "back": 1.0, "turn": (s(1.05), s(1.86)), "hop": (s(1.80), s(2.50))}

    def reload_plan(self, poses, times, length):
        """The reload, frame by frame: (the old magazine's frames, the new one's, the left hand's
        targets ((palm, finger, normal) in design space), how much the chest turns to the pocket
        (0..1), where he looks (world)), and the magazines' instant moves (out of sight) as extra keys.
        He lifts the empty magazine out and throws it aside (it falls, lies, sinks out of sight),
        reaches to the pocket at his left hip, pulls a full one out upward, seats it, presses it home
        and goes back to the gun. The full one waits in the camel's body (GunDesign.stash) out of
        the reload and moves to the pocket, both out of sight, as the reload begins."""
        g = self.gun
        seat = g.at["ammo"]
        height = float(g.mag_top[1] - g.mag_base[1])
        side = 1.0 if self.style == "A" else -1.0        # the gunner's side of the hopper (B: the mirrored gun's)
        # clear of the hopper; on foot (B) he cannot reach as high: lifted less, held low
        lift = seat + np.array([0.0, (0.32 if self.style == "A" else 0.12) * height, 0.0])
        # every frame below is where the thing is in the camel's frame (design space) with the gun at
        # its rest yaw (round 6, B: across the camel); the empty magazine's bone turns with the gun, so
        # its frames are taken back by that turn at the end (GunDesign.frames turns them again)
        TH = self.home_turn()
        seated = TH @ tr(seat)
        lifted = TH @ tr(lift)
        lift = point(TH, lift)
        stash = g.stash
        # held near its top (over the gun, the end he pulls up and pushes down); on foot, low, just
        # above the hopper
        hand_off = ((g.mag_top - seat) + np.array([side * 0.045, -0.06, 0.0]) if self.style == "A" else
                    self.mag_grip + np.array([side * 0.045, 0.0, 0.0]))

        def grip(M):
            Rm = M[:3, :3]
            return point(M, hand_off), Rm @ np.array([0.0, 0.2, 1.0]), Rm @ np.array([-side, 0.0, 0.0])

        def top_grip(M):
            """The palm over its top edge from above and outside, fingers forward: the hand that
            draws it from the pocket."""
            Rm = M[:3, :3]
            return (point(M, (g.mag_top - seat) + np.array([-0.01, 0.035, 0.0])), Rm @ np.array([0.0, -0.25, 1.0]),
                    Rm @ unit(np.array([0.35, -1.0, 0.0])))
        rest = self.target("breech" if self.style == "A" else "dropcrank" if self.long else "casing", self.home_frames())

        def mix(a, b, w):
            w = smooth(min(1.0, max(0.0, w)))
            return (np.asarray(a[0]) + w * (np.asarray(b[0]) - np.asarray(a[0])),
                    unit((1 - w) * np.asarray(a[1]) + w * np.asarray(b[1])),
                    unit((1 - w) * np.asarray(a[2]) + w * np.asarray(b[2])))

        def lerp_frame(A, B, w, ease=True):
            w = min(1.0, max(0.0, w))
            w = smooth(w) if ease else w
            qa, qb = matrix_quat(A[:3, :3]), matrix_quat(B[:3, :3])
            if float(np.dot(qa, qb)) < 0:
                qb = -np.asarray(qb)
            q = unit((1 - w) * np.asarray(qa) + w * np.asarray(qb))
            from aoe3game.gr2_skin import quat_matrix
            out = rot4(quat_matrix(q))
            out[:3, 3] = (1 - w) * A[:3, 3] + w * B[:3, 3]
            return out

        def seg(u, a, b):
            return (u - a) / (b - a)
        # the beats (shares of the clip, Unit.reload_times); the toss: released at U_REL from the hand,
        # a throw to his left and up, in the world
        T = self.reload_times()
        U_REL = T["rel"]
        i_rel = int(np.argmin(np.abs(np.asarray(times) / length - U_REL)))
        Crel = self.C(poses[i_rel])
        # his left and his forward in design space (A: the camel's left and forward)
        self._reload_t = times[i_rel]
        b_right, _b_up, b_fwd = self.body_axes(self.base_body(poses[i_rel]))
        inv_rel = np.linalg.inv(Crel)[:3, :3]
        left_d, fwd_d = unit(inv_rel @ -b_right), unit(inv_rel @ b_fwd)
        tip = -35.0 * float(np.cross(fwd_d, left_d) @ Y)        # the top tipped out to his left
        throw = tr(lift + 0.17 * left_d + np.array([0.0, -0.10, 0.0]) + 0.04 * fwd_d) @ rot4(axis_matrix(fwd_d, tip)) \
            @ rot4(TH[:3, :3])
        p0 = point(Crel, throw[:3, 3])
        v0 = Crel[:3, :3] @ (1.3 * left_d + 0.8 * Y + 0.2 * fwd_d)
        g_acc = 9.8
        ground = 0.06
        # landing time: p0.y + v0.y t - g t^2 / 2 = ground
        a, b_, c = -0.5 * g_acc, v0[1], p0[1] - ground
        t_land = (-b_ - math.sqrt(b_ * b_ - 4 * a * c)) / (2 * a)
        flight = (times[i_rel], p0, v0, g_acc, t_land, Crel[:3, :3] @ throw[:3, :3])
        old, new, hand, turn, look = [], [], [], [], []
        seat_at = T["seat"]
        toward = None
        for t, P in zip(times, poses):
            u = t / length
            self._reload_t = t                     # base_body: where he stands at t (v5 steps in)
            C = self.C(P)
            invC = np.linalg.inv(C)
            inpocket, _axes, top_w, along = self.pocket(P)
            # drawn: slid out of the pocket along its own length, its foot clear of his hip
            drawn = invC @ tr(self.POCKET_DRAW * along) @ C @ inpocket
            if self.style == "B":
                # it leans out with the draw: turned about its top until its length lies along the draw
                from aoe3game.gr2_pose import about
                Wp = C @ inpocket
                cur = unit(Wp[:3, :3] @ Y)
                ax = np.cross(cur, along)
                if float(np.linalg.norm(ax)) > 1e-6:
                    ang = math.degrees(math.atan2(float(np.linalg.norm(ax)), float(cur @ along)))
                    best = None
                    for sgn in (1.0, -1.0):
                        T_ = about(top_w, axis_matrix(unit(ax), sgn * ang))
                        e = float(np.linalg.norm(unit(T_[:3, :3] @ cur) - along))
                        if best is None or e < best[0]:
                            best = (e, T_)
                    drawn = invC @ tr(self.POCKET_FOOT_DRAW * along) @ best[1] @ Wp
            toward = top_w
            # the new magazine: in the camel's body, in the pocket, drawn, carried over, seated
            if self.style == "B" and (u < T["closed"] or u >= 0.95):
                N = inpocket                       # B: refined from his own body in build()
            elif u < 0.01 or u >= 0.95:
                N = stash
            elif u < T["closed"]:
                N = inpocket
            elif u < T["drawn"]:
                N = lerp_frame(inpocket, drawn, seg(u, T["closed"], T["drawn"]))
            elif u < T["carry_end"] and self.style == "B":
                # standing, the straight way from his hip to the hopper passes his shoulder: he brings
                # the magazine in front of his chest first, then up into the hopper
                body = self.base_body(P)
                lift_w = point(C, lifted[:3, 3])
                # the hand passes well in front of his left shoulder (the grip point there)
                way_w = body["bip01 l upperarm"][:3, 3] + B_CARRY_ARC * _axes[2] + (
                    lift_w - point(C, point(lifted, hand_off)))
                front = invC @ tr(way_w - lift_w) @ C @ lifted
                d1 = float(np.linalg.norm(way_w - point(C, drawn[:3, 3])))
                d2 = float(np.linalg.norm(lift_w - way_w))
                # one even stroke through the waypoint, each part in time as long as it is
                split = T["drawn"] + (T["carry_end"] - T["drawn"]) * d1 / max(d1 + d2, 1e-6)
                w_all = smooth(seg(u, T["drawn"], T["carry_end"]))
                w_at = smooth(seg(split, T["drawn"], T["carry_end"]))
                if w_all < w_at:
                    N = lerp_frame(drawn, front, w_all / max(w_at, 1e-6), ease=False)
                else:
                    N = lerp_frame(front, lifted, (w_all - w_at) / max(1.0 - w_at, 1e-6), ease=False)
                # it turns upright over the whole carry, not only on the way to the waypoint (a
                # waypoint near the draw's end would turn it, and the hand on it, in a few frames)
                N = N.copy()
                N[:3, :3] = lerp_frame(drawn, lifted, w_all, ease=False)[:3, :3]
            elif u < T["carry_end"]:
                N = lerp_frame(drawn, lifted, seg(u, T["drawn"], T["carry_end"]))
            elif u < seat_at:
                N = lerp_frame(lifted, seated, seg(u, T["carry_end"], seat_at))
            else:
                N = seated
            if self.style == "B" and T["closed"] <= u < T["carry_end"]:
                # his hand never comes within B_HAND_CLEAR of his own shoulder (the elbow folded flat
                # turns over): the magazine is pushed out from it
                sh_w = self.base_body(P)["bip01 l upperarm"][:3, 3]
                gp = point(C, point(N, g.mag_top - seat))
                dvec = gp - sh_w
                dist_ = float(np.linalg.norm(dvec))
                ramp = smooth(min(1.0, max(0.0, min((u - T["closed"]) / 0.06, (T["carry_end"] - u) / 0.06))))
                if dist_ < B_HAND_CLEAR and ramp > 0.0:
                    N = invC @ tr(ramp * (B_HAND_CLEAR - dist_) * unit(dvec)) @ C @ N
            # the old one
            if u < T["take"]:
                O = seated
            elif u < T["lifted"]:
                O = lerp_frame(seated, lifted, seg(u, T["take"], T["lifted"]))
            elif u < U_REL:
                O = lerp_frame(lifted, throw, seg(u, T["lifted"], U_REL))
            elif u < 0.95:
                t0, p0, v0, g_acc, t_land, R0 = flight
                dt = min(t - t0, t_land)
                pos = p0 + v0 * dt + np.array([0.0, -0.5 * g_acc * dt * dt, 0.0])
                # it turns over once in the air and lands on its side (lying along the camel's
                # side), then sinks out of sight
                s = min(1.0, max(0.0, dt / t_land))
                lying_w = rot4(axis_matrix(np.array([0.0, 0.0, 1.0]), 90.0))
                W = lerp_frame(rot4(R0), lying_w, s)
                W = rot4(axis_matrix(np.array([0.0, 0.0, 1.0]), -360.0 * smooth(s)) @ W[:3, :3])
                if t - t0 >= t_land:
                    sink = min(1.0, max(0.0, seg(u, 0.80, 0.90)))
                    pos = pos + np.array([0.0, -0.6 * smooth(sink), 0.0])
                W[:3, 3] = pos
                O = rigid(invC @ W)
            else:
                O = seated
            # the left hand
            if u < T["take"]:
                H = mix(rest, grip(seated), seg(u, 0.0, T["take"]))
            elif u < U_REL:
                H = grip(O)
            elif u < T["pocket"]:
                H = mix(grip(throw), top_grip(inpocket), seg(u, U_REL, T["pocket"]))
                if self.style == "B":
                    # standing, his hand comes down to the thigh in front of him, clear of his shoulder
                    bulge = B_HAND_ARC * math.sin(math.pi * smooth(seg(u, U_REL, T["pocket"])))
                    H = (H[0] + invC[:3, :3] @ (bulge * _axes[2]), H[1], H[2])
            elif u < T["drawn"]:
                H = top_grip(N)
            elif u < T["regrip"]:
                H = mix(top_grip(N), grip(N), seg(u, T["drawn"], T["regrip"]))
            elif u < seat_at:
                H = grip(N)
            elif u < seat_at + T["press"]:                                  # pressed home
                p, f, n = grip(seated)
                H = (p + np.array([0.0, -0.015 * math.sin(math.pi * seg(u, seat_at, seat_at + T["press"])), 0.0]), f, n)
            else:
                H = mix(grip(seated), rest, seg(u, seat_at + T["press"], T["back"]))
            # the chest turned a little toward the pocket while he reaches down to it
            a_, b_ = T["turn"]
            w = 0.0 if u < a_ or u > b_ else math.sin(math.pi * seg(u, a_, b_))
            old.append(O)
            new.append(N)
            hand.append(H)
            turn.append(w)
            look.append(point(C, H[0]))
        self._reload_t = None
        if self.home:
            back = np.linalg.inv(TH)
            old = [back @ O for O in old]
        look = self.calm_gaze(poses, times, length, look)
        # the instant moves, out of sight: the new one from the camel's body to the pocket (u 0.01)
        # and back (0.95, seated inside the old one), the old one back in the gun (0.95, inside the
        # new one): a key 1 ms before the first frame at or after each, holding the frame before
        # it (write())
        extra = {"ammo2": (0.01, 0.95), "ammo": (0.95,)} if self.style == "A" else {"ammo2": (0.95,), "ammo": (0.95,)}
        return {"old": old, "new": new, "hand": hand, "turn": turn, "look": look, "extra": extra,
                "toward": toward, "times": np.asarray(times)}

    # how his head may turn from his body's forward while he watches his hands in a reload (degrees),
    # and how smooth the turns are (seconds, the gaze's Gaussian smoothing)
    GAZE_YAW, GAZE_UP, GAZE_DOWN, GAZE_SMOOTH = 60.0, 15.0, 30.0, 0.22

    def calm_gaze(self, poses, times, length, points):
        """Where he looks in a reload, frame by frame (world points): at his left hand (`points`)
        from about 0.04 to 0.92 of the clip, along the barrels before and after (as in the fire
        clip), as a yaw and a pitch from his body's forward, each kept to a man's limits
        (GAZE_YAW, GAZE_UP, GAZE_DOWN), the yaw faded out when the hand is nearly straight below or
        above his eyes (its direction there means nothing), then smoothed over GAZE_SMOOTH s: small
        smooth glances, never a snap. The chest turns too (the plan's `turn`), so the head turns
        less than the gaze."""
        n = len(times)
        yaw, pitch = np.zeros(n), np.zeros(n)
        heads, axes = [], []
        for i, (t, P) in enumerate(zip(times, poses)):
            u = t / length
            C = self.C(P)
            R = self.base_body(P)
            head = R["bip01 head"][:3, 3]
            right, _up, fwd = self.body_axes(R)
            heads.append(head)
            axes.append((right, fwd))

            def angles(p):
                d = np.asarray(p, np.float64) - head
                hz = math.hypot(float(d @ fwd), float(d @ right))
                return (math.degrees(math.atan2(float(d @ right), float(d @ fwd))),
                        math.degrees(math.atan2(float(d[1]), hz)), hz)
            yd, pd, _h = angles(self.downrange(C, self.home_frames()))
            yh, ph, hz = angles(points[i])
            wy = smooth(min(1.0, max(0.0, (hz - 0.10) / 0.25)))         # the hand far enough aside
            yh = wy * max(-self.GAZE_YAW, min(self.GAZE_YAW, yh)) + (1.0 - wy) * yd
            ph = max(-self.GAZE_DOWN, min(self.GAZE_UP, ph))
            w = smooth(min(1.0, max(0.0, (u - 0.03) / 0.09))) * smooth(min(1.0, max(0.0, (0.92 - u) / 0.08)))
            yaw[i] = (1.0 - w) * yd + w * yh
            pitch[i] = (1.0 - w) * pd + w * ph
        dt = float(times[1] - times[0]) if n > 1 else 1.0
        sigma = max(1e-6, self.GAZE_SMOOTH / dt)
        k = np.arange(-int(3 * sigma) - 1, int(3 * sigma) + 2)
        ker = np.exp(-0.5 * (k / sigma) ** 2)
        ker /= ker.sum()
        pad = len(k) // 2

        def smoothed(a):
            return np.convolve(np.pad(a, pad, mode="edge"), ker, mode="valid")
        yaw, pitch = smoothed(yaw), smoothed(pitch)
        out = []
        for i in range(n):
            right, fwd = axes[i]
            y, p = math.radians(yaw[i]), math.radians(pitch[i])
            d = math.cos(p) * (math.cos(y) * fwd + math.sin(y) * right) + math.sin(p) * Y
            out.append(heads[i] + 3.0 * d)
        self.last_gaze = (yaw, pitch)
        return out

    # -- the rider on foot (variant B)

    def couched(self):
        cam = self.camel
        return cam.grounded(cam.anim(B_IDLE), [0.0])[0]

    def stand_pose(self):
        """The gunner on foot at the gun of the couched camel: an infantry idle put on the rider,
        facing the gun's side, placed so the right hand reaches the crank with the elbow bent, and
        crouched (feet kept where they are, the knees bent by two-bone IK) when the crank is low."""
        if getattr(self, "_stand", None) is not None:
            return self._stand
        P0 = self.couched()
        C0 = self.C(P0)
        handle = point(C0, self.target("crank", self.gun.frames({}))[0])
        rig = self.rider.rig
        anim = self.rider.anim(STAND_CLIP)
        base = self.rider.standing(self.foot, anim, 0.0, 90.0, np.zeros(3))
        sh = base["bip01 r upperarm"][:3, 3]
        lo = base["bip01 l upperarm"][:3, 3]
        mid = 0.5 * (sh + lo)
        reach = float(np.linalg.norm(base["bip01 r forearm"][:3, 3] - sh) +
                      np.linalg.norm(base["bip01 r hand"][:3, 3] - base["bip01 r forearm"][:3, 3]))
        drop = max(0.0, (mid[1] - handle[1]) - 0.42 * reach)
        # the shoulders' middle 0.42 of an arm back from the crank (toward -x, his back), level with it in z
        at = np.array([handle[0] - 0.42 * reach - (mid[0] - 0.0), 0.0, handle[2] - (mid[2] - 0.0) - 0.08])
        P = {k: tr(at) @ v for k, v in base.items()}
        if drop > 0:
            P = self.crouch(P, drop)
        self._stand = P
        self.stand_info = {"handle height": float(handle[1]), "shoulder height": float(mid[1]),
                           "crouch": float(drop), "at": at}
        return P

    def crouch(self, P, drop, lean=8.0):
        """The pose lowered by `drop` at the hips, the feet kept, the knees forward, the trunk
        leaning `lean` degrees toward the way he faces."""
        from aoe3game.gr2_pose import local_axis, rotate_about, translate, two_bone_ik
        rig, body = self.rider.rig, self.rider.body
        feet = {s: P[f"bip01 {s} foot"].copy() for s in ("l", "r")}
        root = rig.names[0].lower()
        Q = translate(P, rig, root, np.array([0.0, -drop, 0.0]))
        fwd = unit(Q["bip01 pelvis"][:3, :3] @ (body.base["bip01 pelvis"][:3, :3].T @ Z))
        fwd[1] = 0.0
        fwd = unit(fwd)
        side = unit(np.cross(Y, fwd))
        Q = rotate_about(Q, rig, "bip01 spine1", "bip01 spine1", side, lean)
        for s in ("l", "r"):
            th, ca, fo = (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot")
            Q = two_bone_ik(Q, rig, th, ca, fo, feet[s][:3, 3], fwd, body.hinge[th], body.hinge[ca],
                            end_frame=feet[s][:3, :3])
        return Q

    def thigh_rest(self, P, s="r"):
        """A palm resting on the thigh: (\"world\", palm, finger, normal)."""
        a, b = P[f"bip01 {s} thigh"][:3, 3], P[f"bip01 {s} calf"][:3, 3]
        fin = unit(b - a)
        return ("world", 0.55 * a + 0.45 * b + np.array([0.0, 0.075, 0.0]), fin, np.array([0.0, -1.0, 0.0]))

    def hands(self, P, C, fr, want, built=None, tries=4):
        """`P` with the hands on their targets (want: {side: a target name, (palm, finger, normal)
        in design space, or ("world", palm, finger, normal)}). A target out of the arms' reach
        leans the trunk toward it (the spine turned about its base) and the arms are solved again;
        what is still missing is kept in `built.reach`."""
        poles = self.poles()
        goals = {}
        for s, w in want.items():
            if w is None:
                continue
            if isinstance(w, tuple) and len(w) == 4 and w[0] == "world":
                _w, palm, fin, nor = w
                goals[s] = (np.asarray(palm, np.float64), unit(fin), unit(nor))
            else:
                palm_d, fin, nor = self.target(w, fr) if isinstance(w, str) else w
                goals[s] = (point(C, palm_d), self.world_dir(C, fin), self.world_dir(C, nor))
        base, rig = P, self.rider.rig
        pole_w = {s: self.world_dir(C, v) for s, v in poles.items()}
        if getattr(self, "long", False) and self.style == "B":
            right, _up, fwd = self.body_axes(P)
            # elbows out to his sides, a little down and back: across every reach he makes (the grips
            # in front of him, the thigh pocket down and out, the hopper up and across) the elbow has a
            # clear side, so the arm never turns over between two frames
            pole_w = {"r": unit(0.9 * right - 0.2 * Y - 0.3 * fwd), "l": unit(-0.9 * right - 0.2 * Y - 0.3 * fwd)}
        for _k in range(tries):
            Q = base
            for s, (palm, fin, nor) in goals.items():
                Q = self.rider.hand(Q, s, palm, fin, nor, pole_w[s])
            miss = {s: float(np.linalg.norm(self.rider.palm_of(Q, s) - g[0])) for s, g in goals.items()}
            worst = max(miss.values(), default=0.0)
            if worst < 0.004:
                break
            s = max(miss, key=miss.get)
            pivot = base["bip01 spine"][:3, 3]
            sh = base[f"bip01 {s} upperarm"][:3, 3]
            a, b = sh - pivot, goals[s][0] - pivot
            axis = np.cross(a, b)
            if np.linalg.norm(axis) < 1e-9:
                break
            ang = math.degrees(math.asin(min(0.5, 1.15 * worst / max(np.linalg.norm(b), 1e-6))))
            from aoe3game.gr2_pose import about
            base = {k: (about(pivot, axis_matrix(unit(axis), ang)) @ v if k in self._trunk() else v)
                    for k, v in base.items()}
        if built is not None:
            built.reach = max(built.reach, worst)
        return Q

    def _trunk(self):
        if getattr(self, "_trunk_set", None) is None:
            from aoe3game.gr2_pose import descendants
            self._trunk_set = descendants(self.rider.rig, "bip01 spine1")
        return self._trunk_set

    # -- one clip

    def build(self, clip, fps=FPS):
        cam, rider, g = self.camel, self.rider, self.gun
        if "camel" in clip:
            anim = cam.anim(clip["camel"])
            length = anim.duration
        elif "borrow" in clip:
            anim = cam.anim(clip["borrow"])
            length = anim.duration + clip.get("hold_before", 0.0) + clip.get("hold_after", 0.0)
        else:
            anim = cam.anim(clip["still"])
            length = float(clip["length"])
        n = max(2, int(round(length * fps)) + 1)
        times = np.linspace(0.0, length, n)
        b = Built(clip, times)
        cname = f"{self.r['name']}_camel_{self.variant}_{clip['name']}"
        scales = cam._scales[id(anim)] if "camel" in clip else cam.borrowed_scales(anim)
        if "camel" in clip:
            # written as our own clip even when unchanged (every bone with the scale the runtime
            # gives it in the stock clip, so it draws the same)
            poses = [cam.pose(anim, t) for t in times]
            if clip.get("lower"):
                poses = [cam.lower_head(P, clip["lower"] + clip.get("dip", 0.0) * math.sin(math.pi * t / length) ** 2)
                         for t, P in zip(times, poses)]
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        elif "borrow" in clip:
            before = clip.get("hold_before", 0.0)
            src_t = [min(max(t - before, 0.0), anim.duration) for t in times]
            uniq = {}
            for tt in src_t:                     # a held pose is one object, so the climb's keys are made once
                if tt not in uniq:
                    uniq[tt] = cam.grounded(anim, [tt])[0]
            poses = [uniq[tt] for tt in src_t]
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
            # the rider climbs while the camel is held down: after it lies down, or before it gets up
            b.window = (0.0, before) if before else (anim.duration, length)
        elif clip.get("do") == "foot_death" and self.home:
            # round 6: it lies at the gun with its neck turned (NECK_TURN), then slumps (Camel.slump)
            still = self.neck_turned(cam.fix_hang(cam.grounded(anim, [0.0])[0]), 1.0)
            poses = [cam.slump(still, t) for t in times]
            b.necked = True
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        elif clip.get("do") == "foot_death" or clip.get("roll"):
            still = cam.grounded(anim, [0.0])[0]
            poses = [cam.roll_over(still, t) for t in times]
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        else:
            still = cam.grounded(anim, [0.0])[0]
            poses = [still] * n
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        stock_attach = None
        if clip.get("do") == "fall":
            stock_attach = [cam.seat_frame(P) for P in poses]
        if clip.get("do") == "foot_death" or clip.get("roll"):
            poses = [cam.pin_hang(P, poses[0]) for P in poses]
            scales = cam.hang_scale(poses[0], scales)
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        else:   # the rider's bone (the gun's attach bone) kept on the chest in every clip
            poses = [cam.fix_hang(P) for P in poses]
            scales = cam.hang_scale(poses[0], scales)
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        b.scales = scales
        do = clip.get("do")
        base = rider.anim(clip["rider"]) if clip.get("rider") else rider.idle
        bag = None
        plan = None
        if do == "reload" and self.r.get("reload") == "toss":
            plan = self.reload_plan(poses, times, length)
        elif do == "reload":
            bag = self.bag_point(poses[0])
            keys = self.magazine_keys(bag)
        b.plan = plan
        b.extra = plan["extra"] if plan is not None else {}
        rolls = clip.get("roll") or do == "foot_death"
        if rolls:
            # the camel rolls over while its chest bone (the gun's) is held: the spare would leave its
            # body, so it moves into the gun's hopper, inside the seated magazine, once a game has
            # brought the gun home (turretArc: at once in a death clip, home within DEATH_SPARE_AT)
            b.extra = {"ammo2": (DEATH_SPARE_AT / length,)}
        for i, (t, P) in enumerate(zip(times, poses)):
            u = t / length
            state = {}
            if rolls and t >= DEATH_SPARE_AT - 1e-9:
                state["magazine2"] = self.home_turn() @ tr(g.at["ammo"])
            if do == "fire":
                state = self.fire_state(t, length)
                for s in self.shots(length):
                    if 0.0 <= t - s < 0.045:
                        b.flash.append(t)
            yaw_t = self.clip_yaw(clip, t, length, b)
            if yaw_t:
                state["yaw"] = yaw_t
            if plan is not None:
                state["magazine"], state["magazine2"] = plan["old"][i], plan["new"][i]
                self._plan_at = (plan, i)
            elif do == "reload":
                state["magazine"] = self.magazine_frame(keys, u)
            fr = g.frames(state)
            C = self.C(P)
            attach = rigid(P[cam.rider_bone])
            if do == "fall":
                # the stock rider death, played where the stock clip had his bone
                k = len(b.camel)
                anim = rider.anim(RIDER_DEATH)
                R = rider.seated(anim, min(t, anim.duration), stock_attach[k], square=False)
            else:
                R = self.rider_pose(clip, do, t, length, u, P, C, fr, base, attach, b)
            if self.style == "B" and self.r.get("reload") == "toss" and not rolls:
                in_pocket = plan is None or u < self.reload_times()["closed"] or u >= 0.95
                if in_pocket:
                    fr = dict(fr)
                    fr["ammo2"] = self.pocket(P, R)[0]
            b.camel.append(P)
            b.gun.append(fr)
            b.rider.append(R)
        self._plan_at = None
        if self.style == "B" and do == "reload":
            # the kush (2026-11-26) lowered the hopper 0.31 m: the left hand's carry up from the pocket
            # turned it at 1515 deg/s; held to 1450
            b.rider = limit_rates(rider.rig, b.rider, 1450.0, bones=("bip01 l hand",))
        if self.style == "A" and do == "reload":
            # the hump's higher seat (2026-11-26): his left forearm turned 1620 deg/s on its way to the pocket
            b.rider = limit_rates(rider.rig, b.rider, 1450.0, bones=("bip01 l upperarm", "bip01 l forearm"))
        b.length = length
        if self.home:
            # the camel's bone_turret (the launch point and the muzzle flash, and the dead model's
            # gun) turned with the gun, so the clip shows them where the gun points; lying down, its
            # neck turned to its right, its head out of the gunner's way (NECK_TURN)
            yaws = [self.clip_yaw(clip, t, length, b) for t in times]
            necks = [0.0 if getattr(b, "necked", False) else self.neck_share(clip, t, length, b) for t in times]
            if any(yaws) or any(necks):
                def done(P, y, k):
                    return self.turret_turned(self.neck_turned(P, k), y)
                b.camel_bytes = cam.track_bytes(cname, times, [done(*a) for a in zip(poses, yaws, necks)], anim, scales)
                b.camel = [done(*a) for a in zip(b.camel, yaws, necks)]
        return b

    # round 6: the lying camel turns its neck this far to its right (degrees about its up), so its head
    # is out of the way of the gunner's arms when the gun points back over its right side
    NECK_TURN = 60.0

    def neck_share(self, clip, t, length, b):
        """How much of NECK_TURN the camel shows at t: all of it lying at the gun, eased in while it
        lies down (the deploy) and out while it rises (the undeploy)."""
        if not self.home:
            return 0.0
        do = clip.get("do")
        if do in ("stand", "fire", "reload", "foot_death"):
            return 1.0
        if do == "dismount":                  # the lying-down clip plays before the window
            t1 = getattr(b, "window", (length, length))[0]
            return smooth(min(1.0, max(0.0, (t - 0.45 * t1) / (0.5 * t1))))
        if do == "mount":                     # the getting-up clip plays after the window
            t0 = getattr(b, "window", (0.0, 0.0))[1]
            return 1.0 - smooth(min(1.0, max(0.0, (t - t0) / (0.4 * (length - t0)))))
        return 0.0

    def neck_turned(self, P, share):
        if not self.home or share <= 0.0:
            return P
        from aoe3game.gr2_pose import rotate_about
        cam = self.camel
        if getattr(self, "_mount_rest", None) is None:
            self._mount_rest = cam.pose(cam.base, 0.0)[cam.mount][:3, :3].copy()
        up = unit(P[cam.mount][:3, :3] @ (self._mount_rest.T @ Y))
        return rotate_about(P, cam.rig, "hs bone neck lower", "hs bone neck lower", up, self.NECK_TURN * share)

    @staticmethod
    def turret_turned(P, yaw):
        """The camel pose with bone_turret and the bones on it turned by `yaw` degrees about the
        turret's own vertical (as turretArc turns it)."""
        if not yaw or "bone_turret" not in P:
            return P
        from aoe3game.gr2_pose import about
        T = P["bone_turret"]
        M = about(T[:3, 3], axis_matrix(unit(T[:3, :3] @ Y), yaw))
        out = dict(P)
        for k in ("bone_turret", "bone_launchpoint", "bone_muzzle"):
            if k in out:
                out[k] = M @ out[k]
        return out

    def bag_point(self, P):
        """Where the magazine is put down, in design space: A, at the saddle beside the rider's left
        knee; B, beside the gunner's left hip."""
        if self.style == "A":
            S = self.rider.seated(self.rider.idle, 0.0, rigid(P[self.camel.rider_bone]))
            knee = 0.4 * S["bip01 l thigh"][:3, 3] + 0.6 * S["bip01 l calf"][:3, 3]
            out = 0.14 * unit(S["bip01 l thigh"][:3, 3] - S["bip01 r thigh"][:3, 3])
            spot = knee + out + np.array([0.0, 0.40, 0.0])
        else:
            S = self.stand_pose()
            spot = S["bip01 l thigh"][:3, 3] + np.array([0.0, 0.16, 0.0]) + 0.12 * unit(
                S["bip01 l thigh"][:3, 3] - S["bip01 r thigh"][:3, 3])
        return point(np.linalg.inv(self.C(P)), spot)

    def seated_hands(self, clip):
        """Mounted: on the move, the right fist on the reins and the left palm resting on the
        breech box's side (the trunk turned a little toward the gun), but at the gallop
        (`reins_only`) both fists on the reins; B at rest (its crank outside,
        out of reach), both fists on the reins; A at the gun, the right hand on the crank and the
        left on the breech."""
        if clip.get("gait"):
            return {"r": "reins", "l": "reins" if clip.get("reins_only") else "casing_side"}
        if self.style == "B" or clip.get("reins"):      # B on foot's mounted rest; lying down, rising
            return {"r": "reins", "l": "reins"}
        return {"r": "crank", "l": "breech"}

    def reins(self, R, attach, s):
        """A fist on the reins above the pommel, in front of the rider's pelvis, in the frame of the
        bone he sits on: ("world", palm, finger, normal)."""
        A = attach[:3, :3]
        side = 0.07 if s == "r" else -0.07
        palm = R["bip01 pelvis"][:3, 3] + A @ np.array([side, 0.05, 0.27])
        return ("world", palm, A @ np.array([-3.0 * side, -0.3, 1.0]), A @ np.array([0.0, -1.0, 0.25]))

    def rider_pose(self, clip, do, t, length, u, P, C, fr, base, attach, b):
        rider = self.rider
        if do == "fall":
            return rider.seated(rider.idle, 0.0, attach)
        if do in (None, "fire", "reload") and self.style == "A" or do is None:
            tb = t * base.duration / length if do is None and clip.get("rider") else 0.0
            R = rider.seated(base, tb, attach)
            if clip.get("gait"):
                # upright, shoulders square: only a small nod of the trunk with each of the two
                # steps, the chest turned a little toward the gun his left hand rests on
                R = rider.turn(R, "bip01 spine", X, clip["gait"] * math.sin(4 * math.pi * u))
                if not clip.get("reins_only"):
                    R = rider.turn(R, "bip01 spine", Y, -6.0)
            if do == "fire":
                R = rider.turn(R, "bip01 spine", X, 5.0 + 0.8 * math.sin(2 * math.pi * SHOTS * u))
            if do in ("fire", "reload", None) and abs(self.yaw_of(fr)) > 0.5:
                # the gun turned on its mount: his chest stays square behind the grips (it turns by
                # AIM_TRUNK's share of how far their middle moved about his spine), the hands stay on
                # them (two-bone IK below) and the head looks along the barrels
                R = self.square_to_grips(R, C, fr, *AIM_TRUNK["A"])
                # the gun across his front is farther away: he leans in toward it
                R = rider.turn(R, "bip01 spine", X, AIM_LEAN * (abs(self.yaw_of(fr)) / 90.0) ** 1.5)
            plan_at = getattr(self, "_plan_at", None) if do == "reload" else None
            if plan_at is not None:
                # the new reload: the chest turns a little toward the pocket at his left hip and
                # leans over to it while he reaches down and draws the full magazine
                plan, i = plan_at
                w = plan["turn"][i]
                if w > 0.0:
                    R = rider.turn_trunk_to(R, plan["toward"], POCKET_TRUNK[0] * w, POCKET_TRUNK[1] * w)
                    R = rider.turn(R, "bip01 spine", Z, POCKET_LEAN * w)
                    R = rider.turn(R, "bip01 spine", X, 6.0 * w)
            elif do == "reload":
                w = math.sin(math.pi * min(1.0, max(0.0, (u - 0.2) / 0.6)))
                R = rider.turn(R, "bip01 spine", Y, -16.0 * w)
                R = rider.turn(R, "bip01 spine", X, 6.0 * w)
            want = dict(self.seated_hands(clip))
            yaw = self.yaw_of(fr)
            swap = None
            if want.get("l") == "breech":
                # turned far, the breech's top moves off from his left shoulder: the left hand
                # moves down to the breech box's near side (AIM_SWAP -+ AIM_BLEND/2 degrees)
                # (turned left, its outer side faces him); turned right, the box is beyond his left
                # arm once his chest turns to the crank: the left hand takes the reins
                swap = {"r": "crank", "l": "reins" if yaw > 0 else "casing_outer"}
            w = smooth(min(1.0, max(0.0, (abs(yaw) - AIM_SWAP + 0.5 * AIM_BLEND) / AIM_BLEND))) if swap else 0.0
            if w > 0.0:
                # the hands move over between AIM_SWAP -+ AIM_BLEND/2 degrees (no jump in a sweep)
                for side in ("l", "r"):
                    if swap[side] != want.get(side):
                        a = self.world_goal(want.get(side), R, C, fr, attach, side)
                        z = self.world_goal(swap[side], R, C, fr, attach, side)
                        palm = (1 - w) * a[0] + w * z[0] + np.array([0.0, 0.08, 0.0]) * math.sin(math.pi * w)
                        want[side] = ("world", palm, unit((1 - w) * a[1] + w * z[1]), unit((1 - w) * a[2] + w * z[2]))
            if plan_at is not None:
                want["l"] = plan_at[0]["hand"][plan_at[1]]
            elif do == "reload":
                want["l"] = self.reload_hand(u, fr)
            if want.get("r") == "thigh":
                want["r"] = self.thigh_rest(R)
            for side in ("l", "r"):
                if want.get(side) == "reins":
                    want[side] = self.reins(R, attach, side)
            R = self.hands(R, C, fr, want, b)
            if plan_at is not None and plan_at[0]["look"][plan_at[1]] is not None:
                return rider.look(R, plan_at[0]["look"][plan_at[1]])       # at what his left hand works
            return rider.look(R, self.gaze(do, clip, R, C, fr, attach))
        # variant B on foot (facing +x: he leans toward the gun about the world's z)
        stand = self.station_body()
        if do == "fall":                     # the rider's own death clips play (anim file)
            return rider.seated(rider.idle, 0.0, attach)
        if do in ("stand", "fire", "reload"):
            yaw = self.yaw_of(fr)
            if do == "reload" and self.steps_in():
                stand = self.traverse.reload_body(t)   # v5: he steps in to the hopper and back
            elif getattr(self, "_stand_at", None) is not None:
                stand = self._stand_at                 # placed on his feet by a Traverse (preview)
            elif self.long and getattr(self, "traverse", None) is not None:
                if abs(yaw - self.home) > 0.5:
                    stand = self.traverse.stair(yaw)   # stepped round the post with the gun
            elif abs(yaw) > 0.5:
                stand = self.step_around(stand, C, fr, yaw)
            R = self.at_gun(stand, C, fr, do, u, b, trunk=(0.1 if do == "reload" else 0.35, 22.0)
                            if getattr(self, "_stand_at", None) is not None else None, t=t)
            plan_at = getattr(self, "_plan_at", None) if do == "reload" else None
            if plan_at is not None:
                return rider.look(R, plan_at[0]["look"][plan_at[1]])
            return rider.look(R, self.gaze(do, clip, R, C, fr, attach))
        if do == "foot_death":
            anim = rider.anim(FOOT_DEATH_BACK if self.home else FOOT_DEATH)
            return self.at_station(rider.standing(self.foot, anim, min(t, anim.duration), 90.0, self.stand_info["at"]))
        # dismount / mount: seated while the camel moves, the climb (keys) while it is held down
        t0, t1 = getattr(b, "window", (0.0, length))
        if t < t0 - 1e-9 or t > t1 + 1e-9:
            seat = rider.seated(rider.idle, 0.0, attach)
            seat = self.hands(seat, C, fr, {"l": self.reins(seat, attach, "l"), "r": self.reins(seat, attach, "r")}, b)
            return rider.look(seat, self.gaze(None, {}, seat, C, fr, attach))
        k = (t - t0) / max(t1 - t0, 1e-9)
        return self.climb(P, C, fr, attach, k if do == "dismount" else 1.0 - k)

    def steps_in(self):
        """B on foot with the v5 handles: he reloads from a spot nearer the hopper (Traverse.reload_spot)."""
        return (self.style == "B" and getattr(self, "long", False) and self.handle_set != "v4"
                and getattr(self, "traverse", None) is not None)

    def right_reload_goal(self, C, fr, t):
        """v5 reload: the right hand from the traverse bar to the flat of the breech box's near side
        while he steps in, and back while he steps out (a small arc up between)."""
        w = self.traverse.reload_share(t)
        if w <= 0.0:
            return "bar"
        if w >= 1.0:
            return "casing_side"
        goals = []
        for name in ("bar", "casing_side"):
            palm_d, fin, nor = self.target(name, fr)
            goals.append((point(C, palm_d), self.world_dir(C, fin), self.world_dir(C, nor)))
        (pa, fa, na), (pb, fb, nb) = goals
        return ("world", pa + w * (pb - pa) + np.array([0.0, 0.06 * math.sin(math.pi * w), 0.0]),
                unit((1 - w) * fa + w * fb), unit((1 - w) * na + w * nb))

    def at_gun(self, stand, C, fr, do, u, b, trunk=None, t=None):
        """The gunner on foot at the gun (B): leaning toward it, his chest turned partly toward
        where it fires, the right hand on the crank and the left on the casing or the magazine."""
        rider = self.rider
        lean = {"stand": -1.5 * math.sin(2 * math.pi * u), "fire": -3.0 - 0.8 * math.sin(2 * math.pi * SHOTS * u),
                "reload": -6.0 * math.sin(math.pi * min(1.0, max(0.0, (u - 0.2) / 0.6)))}[do]
        fwd = unit(stand["bip01 pelvis"][:3, :3] @ (self.rider.body.base["bip01 pelvis"][:3, :3].T @ Z))
        fwd[1] = 0.0
        # lean toward the gun: about his side axis (Z at rest, facing +x)
        R = rider.turn(stand, "bip01 spine", unit(np.cross(unit(fwd), Y)) if trunk else Z, lean)
        share, most = trunk if trunk else (0.1 if do == "reload" else 0.35, 22.0)
        R = rider.turn_trunk_to(R, self.downrange(C, fr), share, most)
        plan_at = getattr(self, "_plan_at", None) if do == "reload" else None
        if plan_at is not None:
            # the new reload: the chest turns toward the pocket on his thigh and he bends to it
            plan, i = plan_at
            w = plan["turn"][i]
            if w > 0.0:
                R = rider.turn_trunk_to(R, plan["toward"], POCKET_TRUNK[0] * w, POCKET_TRUNK[1] * w)
                R = rider.turn(R, "bip01 spine", unit(np.cross(unit(fwd), Y)), -3.0 * w)
            # standing, the hopper is at his shoulder's height and close: he turns his chest to it and
            # leans back a little while he carries the new magazine over and seats it, so his hand comes
            # to it from in front of him, not through his shoulder
            hop = point(C, point(self.gun.yaw_matrix(self.yaw_of(fr)), self.gun.at["ammo"]))
            a_, b_ = self.reload_times()["hop"]
            w2 = math.sin(math.pi * min(1.0, max(0.0, (u - a_) / (b_ - a_)))) if a_ < u < b_ else 0.0
            if w2 > 0.0:
                R = rider.turn_trunk_to(R, hop, 0.8 * w2, 40.0 * w2)
                R = rider.turn(R, "bip01 spine", unit(np.cross(unit(fwd), Y)), B_RELOAD_LEAN_BACK * w2)
            left = plan["hand"][i]
        else:
            left = self.reload_hand(u, fr) if do == "reload" else self.b_left_grip(fr)
        R = self.plant(R, stand)
        if self.long:
            if plan_at is None and do != "reload":
                left = "dropcrank"
            right = self.right_reload_goal(C, fr, t) if do == "reload" and t is not None and self.steps_in() else "bar"
            return self.hands(R, C, fr, {"r": right, "l": left}, b)
        return self.hands(R, C, fr, {"r": "crank", "l": left}, b)

    def station_body(self):
        """B on foot at the gun with the gun at 0: his station (Traverse, with the long handles), else
        the rest place of stand_pose."""
        trav = getattr(self, "traverse", None)
        if getattr(self, "long", False) and trav is not None:
            return trav.settled(self.home)
        return self.stand_pose()

    def at_station(self, P):
        """A pose made at stand_pose's place carried to his station (station_body)."""
        trav = getattr(self, "traverse", None)
        if getattr(self, "long", False) and trav is not None:
            M = trav.M(*trav.station(self.home))
            return {k: M @ v for k, v in P.items()}
        return P

    def plant(self, R, stand):
        """`R` with both legs solved back onto the feet of `stand` (a lean turns the spine, which
        carries the thighs: the feet must not slide)."""
        from aoe3game.gr2_pose import two_bone_ik
        rig, hinge = self.rider.rig, self.rider.body.hinge
        right, _up, fwd = self.body_axes(stand)
        for s in ("l", "r"):
            th, ca, fo = (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot")
            knee = unit(stand[ca][:3, 3] - 0.5 * (stand[th][:3, 3] + stand[fo][:3, 3]))
            if float(np.linalg.norm(knee)) < 1e-6 or float(knee @ fwd) < 0.05:
                knee = fwd
            R = two_bone_ik(R, rig, th, ca, fo, stand[fo][:3, 3], knee, hinge[th], hinge[ca],
                            end_frame=stand[fo][:3, :3])
        return R

    def b_left_grip(self, fr):
        """B's left hand: on the casing's top over the trunnion; with the gun turned to the right
        that point swings off over the camel's back, so it moves to the breech's top (nearer the
        post, by him) by 45 degrees: (palm, finger, normal) in design space, "casing" at rest."""
        w = smooth(min(1.0, max(0.0, self.yaw_of(fr) / 45.0)))
        if w <= 0.0:
            return "casing"
        a, z = self.target("casing", fr), self.target("breech", fr)
        return tuple((1 - w) * np.asarray(a[i]) + w * np.asarray(z[i]) for i in range(3))

    # -- the gun turned on its trunnion (a yaw the game would give it to aim without the camel)

    def world_goal(self, w, R, C, fr, attach, side):
        """A hand's target as (palm, finger, normal) in the world: a target name, "reins",
        (palm, finger, normal) in design space, or ("world", palm, finger, normal)."""
        if w == "reins":
            w = self.reins(R, attach, side)
        if isinstance(w, tuple) and len(w) == 4 and w[0] == "world":
            return np.asarray(w[1], np.float64), unit(w[2]), unit(w[3])
        palm, fin, nor = self.target(w, fr) if isinstance(w, str) else w
        return point(C, palm), self.world_dir(C, fin), self.world_dir(C, nor)

    def grips_mid(self, C, fr):
        """The middle of the crank's handle and the breech's top in the world."""
        return 0.5 * (point(C, self.target("crank", fr)[0]) + point(C, self.target("breech", fr)[0]))

    def square_to_grips(self, R, C, fr, share, most):
        """The chest turned about the vertical at the spine's base by `share` of the angle the
        grips' middle moved about it from the gun's rest (so nothing changes at yaw 0)."""
        from aoe3game.gr2_pose import rotate_about
        base = R["bip01 spine"][:3, 3]

        def heading(p):
            d = p - base
            return math.degrees(math.atan2(d[0], d[2]))
        rest = self.gun.frames({})
        a = heading(self.grips_mid(C, fr)) - heading(self.grips_mid(C, rest))
        a = (a + 180.0) % 360.0 - 180.0
        return rotate_about(R, self.rider.rig, "bip01 spine1", "bip01 spine", Y, max(-most, min(most, share * a)))

    @staticmethod
    def yaw_of(fr):
        """The gun's yaw in a set of frames (degrees, positive toward the unit's right)."""
        z = fr["cannon"][:3, :3] @ Z
        return math.degrees(math.atan2(z[0], z[2]))

    def step_around(self, stand, C, fr, yaw):
        """The gunner on foot when the gun is turned (B): he walks around the trunnion with the
        crank (his rest place turned with the gun), but never nearer the camel's middle than at
        rest (STEP_LIMIT: his own flank), and turns to face the crank again."""
        from aoe3game.gr2_pose import about
        rig = self.rider.rig
        root = rig.names[0].lower()
        pivot = point(C, self.gun.pivot)
        up = self.world_dir(C, Y)
        P = {k: about(pivot, axis_matrix(up, yaw)) @ v for k, v in stand.items()}
        x0, x1 = stand[root][0, 3], P[root][0, 3]
        if x1 > x0 - STEP_LIMIT:              # his flank: x below the rest place (he stands on the left)
            P = {k: tr((x0 - STEP_LIMIT - x1, 0.0, 0.0)) @ v for k, v in P.items()}
        # face the crank: his pelvis forward turned about his root toward the handle
        handle = point(C, self.target("crank", fr)[0])
        at = P[root][:3, 3]
        f = unit(P["bip01 pelvis"][:3, :3] @ (self.rider.body.base["bip01 pelvis"][:3, :3].T @ Z))
        d = handle - at
        a = math.degrees(math.atan2(f[2] * d[0] - f[0] * d[2], f[0] * d[0] + f[2] * d[2]))
        return {k: about(at, axis_matrix(Y, a)) @ v for k, v in P.items()}

    def downrange(self, C, fr):
        """A point far along the barrels, where the gun fires (they turn with the gun's yaw)."""
        return point(C, fr["muzzle"][:3, 3]) + 12.0 * self.world_dir(C, fr["muzzle"][:3, :3] @ Z)

    def gaze(self, do, clip, R, C, fr, attach):
        """Where the rider looks: along the barrels toward the target at the gun, at the magazine
        while he swaps it, and ahead along the camel's way when mounted at rest or on the move."""
        if do == "reload":
            return point(C, fr["ammo"][:3, 3])
        if do in ("fire", "stand") or (self.style == "A" and not clip.get("gait") and do is None
                                        and (clip.get("name") == "idle" or clip.get("at_gun"))):
            return self.downrange(C, fr)
        return R["bip01 head"][:3, 3] + 12.0 * unit(attach[:3, :3] @ Z)

    def climb_keys(self, P, C, fr):
        """The key poses of getting off the couched camel on its left side (the gun's side), as
        (share, pose): seated; the weight on the hands at the pommel; the right leg swung over the
        saddle; both legs down the flank, facing the saddle, hands on it; standing beside it; a step
        forward along the camel; at the gun. The mount is the same keys played backward."""
        cache = getattr(self, "_climb", None)
        if cache is not None and cache[0] is P:
            return cache[1]
        from aoe3game.gr2_pose import rotate_about, translate
        import make_dismount as md
        rider, rig = self.rider, self.rider.rig
        root = rig.names[0].lower()
        attach = P[self.camel.rider_bone]
        A = attach[:3, :3]
        fwd, up, right = A @ Z, A @ Y, A @ X
        left = -right
        seat_at = attach[:3, 3]
        way = rider.face(rider.seated(rider.idle, 0.0, attach))
        k0 = rider.seated(rider.idle, 0.0, attach)
        k0 = self.hands(k0, C, fr, {"l": self.reins(k0, attach, "l"), "r": self.reins(k0, attach, "r")})
        # 1. up off the seat on the hands, leaning over the pommel
        k1 = translate(rider.seated(rider.idle, 0.0, attach), rig, root, 0.07 * up + 0.05 * left)
        k1 = rider.turn(k1, "bip01 spine", right, 20.0)
        k1 = self.hands(k1, C, fr, {"l": self.reins(k1, attach, "l"), "r": self.reins(k1, attach, "r")})
        # 2. the right leg swung up and over the saddle toward the left, the body over the left flank
        k2 = translate(rider.seated(rider.idle, 0.0, attach), rig, root, 0.12 * up + 0.17 * left)
        k2 = rider.turn(k2, "bip01 spine", right, 28.0)
        k2 = rotate_about(k2, rig, "bip01 r thigh", "bip01 r thigh", right, 50.0)
        k2 = rotate_about(k2, rig, "bip01 r thigh", "bip01 r thigh", fwd, 25.0)
        k2 = self.hands(k2, C, fr, {"l": self.reins(k2, attach, "l"), "r": self.reins(k2, attach, "r")})
        # 3. both legs down the left flank, facing the saddle (+x), the belly against it
        S = rider.standing(self.foot, rider.anim(STAND_CLIP), 0.0, 90.0, np.zeros(3))
        cur = S[root][:3, 3]
        k3 = translate(S, rig, root, seat_at + 0.40 * left - 0.50 * up - 0.05 * fwd - cur)
        k3 = self.above_ground(k3)               # his feet hang down the flank, never under the ground
        on_saddle = {s: ("world", seat_at + 0.16 * left + 0.02 * up + (0.16 if s == "l" else -0.16) * fwd,
                         right, -up) for s in ("l", "r")}
        k3 = self.hands(k3, C, fr, on_saddle)
        # 4. standing on the ground beside the saddle, the hands still on it
        k4 = translate(S, rig, root, np.array([seat_at[0] - 0.62 - cur[0], 0.0, seat_at[2] - 0.05 - cur[2]]))
        k4 = self.hands(k4, C, fr, {s: ("world", seat_at + 0.24 * left - 0.06 * up +
                                        (0.16 if s == "l" else -0.16) * fwd, right, -up) for s in ("l", "r")})
        k4 = rider.look(k4, seat_at, max_pitch=25.0)
        k3 = rider.look(k3, seat_at, max_pitch=25.0)
        # 5. a step forward along the flank (an infantry walk's mid-stride, facing forward)
        stand = self.station_body()
        a, c = k4[root][:3, 3], stand[root][:3, 3]
        walk = rider.anim(LIB + "range\\march_rifleman")
        mid = 0.5 * (a + c)
        k5 = rider.standing(self.foot, walk, 0.3 * walk.duration, 45.0, np.zeros(3))
        k5 = translate(k5, rig, root, np.array([mid[0] - k5[root][0, 3], 0.0, mid[2] - k5[root][2, 3]]))
        k5 = rider.look(k5, k5["bip01 head"][:3, 3] + 5.0 * unit(fwd + right))
        # 6. at the gun (round 6: the gun at its rest yaw, across the camel)
        fr6 = self.home_frames() if self.home else fr
        k6 = self.at_gun(stand, C, fr6, "stand", 0.0, None)
        k6 = rider.look(k6, self.downrange(C, fr6))
        k0 = rider.look(k0, k0["bip01 head"][:3, 3] + 12.0 * fwd)
        k1 = rider.look(k1, seat_at + 0.6 * left - up * 0.6 + 0.4 * fwd, max_pitch=25.0)
        k2 = rider.look(k2, seat_at + 1.0 * left - up * 1.2, max_pitch=25.0)
        s = self.CLIMB_SHARES_HOME if self.home else self.CLIMB_SHARES
        keys = list(zip(s, (k0, k1, k2, k3, k4, k5, k6)))
        keys = [(s_, self.above_ground(k_)) for s_, k_ in keys]
        self._climb = (P, keys)
        return keys

    def above_ground(self, R, clear=0.0):
        """`R` lifted so that no foot (its sole: the foot and toe bones, less the sole's depth) is
        under the ground."""
        from aoe3game.gr2_pose import translate
        low = min(float(R[b][1, 3]) for b in R if b.endswith(" foot") or b.endswith(" toe0"))
        sole = getattr(self, "_sole", None)
        if sole is None:
            st = self.stand_pose()
            sole = self._sole = min(float(st[b][1, 3]) for b in st if b.endswith(" foot") or b.endswith(" toe0"))
        lift = (sole + clear) - low
        if lift > 1e-4:
            return translate(R, self.rider.rig, self.rider.rig.names[0].lower(), np.array([0.0, lift, 0.0]))
        return R

    SIDESTEP = 0.45     # v5: the longest side step (metres) from the saddle back to his station
    TO_STATION_TURN = 0.5   # share of the way from the saddle to the station spent turning to the gun
    # the climb's key poses as shares of the window the camel is held down in (seated, up on the hands,
    # the leg over, down the flank, standing at the saddle, a step, at the gun); round 6: the climb a
    # little quicker, so the swing of the gun to its rest yaw has the rest
    CLIMB_SHARES = (0.0, 0.14, 0.30, 0.48, 0.64, 0.82, 1.0)
    CLIMB_SHARES_HOME = (0.0, 0.11, 0.24, 0.38, 0.50, 0.75, 1.0)

    def to_station_swing(self, keys, share, C, fr):
        """Round 6 (the gun rests across the camel): from standing at the saddle (key 4) he turns on the
        spot toward the two grips (the gun still ahead) while his hands go to them (the first SWING[0]
        of the rest), then pushes the gun round to its rest yaw while he steps round the post to his
        station, by way of the station of half the turn (two legs of two steps, the leading foot the
        one that keeps his feet apart), his hands on the grips, looking along the barrels. Played
        backward for the mount; the gun's yaw at each share is clip_yaw's."""
        from aoe3game.gr2_pose import blend
        trav, rig, rider = self.traverse, self.rider.rig, self.rider
        root = rig.names[0].lower()
        (s4, k4) = keys[4]
        f = (share - s4) / max(1.0 - s4, 1e-9)
        if getattr(self, "_swing_path", None) is None:
            a = k4[root][:3, 3] - trav.stand[root][:3, 3]
            sa = trav.s0 + a[[0, 2]]
            # a station for the gun ahead (both hands on the grips in front of his chest, clear of the
            # camel) a step or two from where he stands at the saddle
            st0, _c, _i = trav._search(0.0, (sa, trav.h0, (trav.STATION_STEP, 60.0)))
            MA, MB = trav.M(sa, trav.h0), trav.M(*st0)
            st1 = trav.station(self.home)
            mid, _c, _i = trav._search(0.5 * self.home, (st1[0], st1[1], (trav.STATION_STEP, trav.STATION_TURN)))
            MW, M1 = trav.M(*mid), trav.M(*st1)
            self._swing_path = [(MA, MB, trav.best_lead(MA, MB)), (MB, MW, trav.best_lead(MB, MW)),
                                (MW, M1, trav.best_lead(MW, M1))]
        (MA, MB, la), (_mb, MW, lb), (_mw, M1, lc) = self._swing_path
        if f < self.SWING[0]:                    # he turns to the grips; his hands leave the saddle for them
            body = trav.walk(MA, MB, f / self.SWING[0], la, (0.0, 0.5), (0.5, 1.0))
        else:
            g = min(1.0, (f - self.SWING[0]) / (self.SWING[1] - self.SWING[0]))
            body = (trav.walk(MB, MW, g / 0.5, lb, (0.0, 0.5), (0.5, 1.0)) if g < 0.5 else
                    trav.walk(MW, M1, (g - 0.5) / 0.5, lc, (0.0, 0.5), (0.5, 1.0)))
        R = self.at_gun(body, C, fr, "stand", 0.0, None)
        R = rider.look(R, self.downrange(C, fr))
        if f < self.SWING[0]:
            R = blend(rig, k4, R, smooth(f / self.SWING[0]))
        return self.above_ground(R)

    def to_station(self, keys, share, C=None, fr=None):
        """v5 (the station behind the turret): from standing at the saddle (the climb's key 4) he
        side-steps back along the flank, still facing the saddle, in as many pairs of steps as keep
        each step under SIDESTEP, then turns on the spot to face along the barrels while his hands go
        to the grips (key 6). Played backward for the mount."""
        from aoe3game.gr2_pose import blend
        if self.home:
            return self.to_station_swing(keys, share, C, fr)
        trav, rig = self.traverse, self.rider.rig
        root = rig.names[0].lower()
        (s4, k4), (_s6, k6) = keys[4], keys[6]
        a = k4[root][:3, 3] - trav.stand[root][:3, 3]
        sa = trav.s0 + a[[0, 2]]
        sb, hb = trav.station(0.0)
        n = max(1, int(math.ceil(float(np.linalg.norm(sb - sa)) / self.SIDESTEP)))
        mid = s4 + (1.0 - s4) * (1.0 - self.TO_STATION_TURN)

        def lead_of(M0, M1):
            way = point(M1, trav.stand[root][:3, 3]) - point(M0, trav.stand[root][:3, 3])
            if float(np.linalg.norm(way)) < 1e-6:           # turning on the spot: the foot that moves more
                d = {s: float(np.linalg.norm(point(M1, trav.feet0[s][:3, 3]) - point(M0, trav.feet0[s][:3, 3])))
                     for s in ("l", "r")}
                return max(d, key=d.get)
            return max(("l", "r"), key=lambda s: float(point(M0, trav.feet0[s][:3, 3]) @ way))
        if share <= mid:
            g = (share - s4) / (mid - s4) * n
            i = min(int(g), n - 1)
            M0 = trav.M(sa + (sb - sa) * i / n, trav.h0)
            M1 = trav.M(sa + (sb - sa) * (i + 1) / n, trav.h0)
            body = trav.walk(M0, M1, g - i, lead_of(M0, M1), (0.0, 0.5), (0.5, 1.0))
            w = smooth(min(1.0, 2.0 * g / n))                 # his hands leave the saddle (first half)
            return self.above_ground(blend(rig, k4, body, w))
        f = (share - mid) / (1.0 - mid)
        M0, M1 = trav.M(sb, trav.h0), trav.M(sb, hb)
        body = trav.walk(M0, M1, f, lead_of(M0, M1), (0.0, 0.5), (0.5, 1.0))
        w = smooth(min(1.0, max(0.0, (f - 0.3) / 0.7)))       # his hands go to the grips
        return self.above_ground(blend(rig, body, k6, w))

    def climb(self, P, C, fr, attach, share):
        """The rider at `share` (0 seated, 1 at the gun) of getting off the couched camel."""
        from aoe3game.gr2_pose import blend
        keys = self.climb_keys(P, C, fr)
        share = min(max(share, 0.0), 1.0)
        if self.steps_in() and share > keys[4][0]:
            return self.to_station(keys, share, C, fr)
        i = max(j for j, (k, _p) in enumerate(keys) if k <= share + 1e-9)
        i = min(i, len(keys) - 2)
        (s0, p0), (s1, p1) = keys[i], keys[i + 1]
        return blend(self.rider.rig, p0, p1, smooth((share - s0) / (s1 - s0)))

    # -- the files

    def write(self, b):
        """The gun's and the rider's clips of a built clip (bytes), names after the recipe."""
        g, name = self.gun, self.r["name"]
        bones = GunDesign.BONES
        locs = []
        shifts = getattr(b, "gun_shift", None) or [np.eye(4)] * len(b.gun)
        for fr, shift in zip(b.gun, shifts):
            worlds = {"root": np.eye(4)}
            for k in bones[1:]:
                worlds[k] = shift @ g.to_model(fr[k])
            loc = []
            for k in bones:
                par = g.parent[k]
                m = worlds[k] if par is None else np.linalg.inv(worlds[par]) @ worlds[k]
                loc.append(split(m))
            locs.append(loc)
        names = [f"bone_{self.gun_name}" if k == "root" else GunDesign.bone_name(k) for k in bones]
        tracks = []
        extra = getattr(b, "extra", None) or {}
        for i, nm in enumerate(names):
            times = np.asarray(b.times, np.float64)
            pos = np.array([f[i][0] for f in locs])
            rot = np.array([f[i][1] for f in locs])
            # an instant move (out of sight): a key 1 ms before the first frame at or after it,
            # holding the frame before, so the move takes 1 ms, not a frame's time (the latest
            # first, so the earlier frames keep their places)
            for at in sorted(extra.get(bones[i], ()), reverse=True):
                j = int(np.searchsorted(times, at * b.length - 1e-9))
                if 0 < j < len(times):
                    times = np.insert(times, j, times[j] - 1e-3)
                    pos = np.insert(pos, j, pos[j - 1], axis=0)
                    rot = np.insert(rot, j, rot[j - 1], axis=0)
            tracks.append((nm, times, pos, rot))
        like = self.rider.idle
        b.gun_bytes = animation_file(self.clip_name("gun", b), float(b.times[-1]), names[0], tracks,
                                     basis=self.rider.rig.basis, accumulation=like.accumulation,
                                     timestep=like.timestep, source=self.clip_name("gun", b))
        rl = [self.rider.to_local(R, rigid(P[self.camel.rider_bone])) for R, P in zip(b.rider, b.camel)]
        b.rider_bytes = self.rider.track_bytes(self.clip_name("rider", b), b.times, rl, like)
        return b

    def clip_name(self, who, b):
        if who == "camel":
            return f"{self.r['name']}_camel_{self.variant}_{b.clip['name']}"
        return f"{self.r['name']}_{who}_{self.tag}_{b.clip['name']}"


# --------------------------------------------------------------------------------------------------
# Playing the written files back (the pictures are drawn from them, so they check them too)


class Playback:
    """One unit drawn from its written files: the cut camel, the gun model and the clips (read
    back), the rider and his hat, hung on each other as the anim files hang them."""

    def __init__(self, game, scene, unit, model_bytes, built):
        self.scene, self.unit = scene, unit
        self.gun_rig = Rig.of(gr2.load(model_bytes).root())
        self.gun_fig = Figure(game, model_bytes)
        self.clips = {}
        for name, b in built.items():
            camel = unit.camel.load(b.camel_bytes) if b.camel_bytes else unit.camel.anim(b.clip["camel"])
            self.clips[name] = (camel, Animation.load(b.gun_bytes), Animation.load(b.rider_bytes), b)

    def poses(self, name, t):
        camel, gun, rider, _b = self.clips[name]
        cam, rr = self.unit.camel, self.unit.rider
        P = cam.pose(camel, t)
        chest = rigid(P[cam.hang])
        G = {k: chest @ v for k, v in self.gun_rig.by_name(self.gun_rig.pose(gun, t)).items()}
        attach = rigid(P[cam.rider_bone])
        R = {k: attach @ v for k, v in rr.rig.by_name(rr.rig.pose(rider, t)).items()}
        return P, G, R

    def items(self, name, t, place=None):
        P, G, R = self.poses(name, t)
        s = self.scene
        out = s.camel_fig.items(P, place) + self.gun_fig.items(G, place) + s.rider_fig.items(R, place)
        out += s.hat_items(R, place)
        b = self.clips[name][3]
        marks = []
        if any(0.0 <= t - f < 0.045 for f in self.flash_times(b)):
            mz = G["bone_launchpoint"][:3, 3]
            ahead = unit(G["bone_launchpoint"][:3, :3] @ Z)
            p = mz + 0.06 * ahead
            marks.append((p if place is None else point(place, p), (255, 200, 40), 9))
        return out, marks

    @staticmethod
    def flash_times(b):
        return Unit.shots(b.length) if b.clip.get("do") == "fire" else []

    def gap(self, name):
        """The largest distance between a built frame's bone and the read-back one (gun and rider)."""
        _c, _g, _r, b = self.clips[name]
        worst = 0.0
        shifts = getattr(b, "gun_shift", None) or [np.eye(4)] * len(b.gun)
        for t, P, fr, R, shift in zip(b.times, b.camel, b.gun, b.rider, shifts):
            P2, G2, R2 = self.poses(name, t)
            chest = rigid(P2[self.unit.camel.hang])
            for k in GunDesign.BONES[1:]:
                want = chest @ shift @ self.unit.gun.to_model(fr[k])
                worst = max(worst, float(np.abs(want[:3, 3] - G2[GunDesign.bone_name(k)][:3, 3]).max()))
            for k, v in R.items():
                worst = max(worst, float(np.abs(v[:3, 3] - R2[k][:3, 3]).max()))
            for k, v in P.items():
                worst = max(worst, float(np.abs(v[:3, 3] - P2[k][:3, 3]).max()))
        return worst


class Scene:
    """The figures every unit shares: the cut camel, the rider and his hat."""

    def __init__(self, game, recipe, camel, rider):
        self.camel_fig = Figure(game, camel.cut)
        self.rider_fig = Figure(game, rider.data)
        self.hat = None
        spec = recipe["rider"].get("hat")
        if spec:
            try:
                data = game.granny(spec["model"])
                fig = Figure(game, data, replace=spec.get("texture"))
                rig = Rig.of(gr2.load(data).root())
                fb = rig.by_name(rig.rest_worlds()).get(spec["frombone"].lower(), np.eye(4))
                self.hat = (fig, np.linalg.inv(fb), spec["tobone"].lower())
            except (FileNotFoundError, gr2.Gr2Error, KeyError):
                self.hat = None

    def hat_items(self, R, place=None):
        if self.hat is None:
            return []
        fig, inv_from, to = self.hat
        if to not in R:
            return []
        m = R[to] @ inv_from
        return fig.items(None, m if place is None else place @ m)


# --------------------------------------------------------------------------------------------------
# Pictures: the model sheet and the GIFs


TODAY = {"folder": "KingsReturn\\Units\\Persian\\GatlingCamel\\", "camel": "Gatling_Camel",
         "camel_clip": "units\\asians\\indians\\sowar\\sowarCamel_idle00",
         "parts": ["GunWeapon_Limber", "WoodAttachment"], "guy": "Gatling_Guy",
         "guy_clip": LIB + "range\\volley\\crossbow_volley_idle"}


def to_file_points(p, basis):
    """Blender-space metres (gr2_mesh) back to a file's axes and units."""
    right, up, back, upm = basis
    m = gr2_mesh._to_blender_matrix(basis)
    h = np.c_[np.asarray(p, np.float64), np.ones(len(p))] @ np.linalg.inv(m)
    return h[:, :3]


def today_items(game, cache=None):
    """Today's gatling camel of the mod, as its anim files hang it at rest (a camel with a static gun
    and a wood frame on its back, the gunner on foot beside it): best effort, None when its files
    do not read."""
    t = TODAY

    def load(rel):
        data = game.granny(t["folder"] + rel)
        if not (gr2.load(data).root().get("Meshes") or []) and cache:
            import hashlib
            raw = game._g.raw(t["folder"] + rel)
            alt = os.path.join(cache, hashlib.md5(raw).hexdigest() + ".gr2")
            if os.path.exists(alt):
                with open(alt, "rb") as f:
                    data = f.read()
        return data

    try:
        cdata = load(t["camel"])
        croot = gr2.load(cdata).root()
        if not (croot.get("Meshes") or []):
            return None
        rig = Rig.of(croot)
        P = rig.by_name(rig.pose(Animation.load(game.granny(t["camel_clip"])), 0.0))
        items = Figure(game, cdata).items(P)
        body = gr2_mesh.read(cdata)
        att = P["bone attachpoint"] @ np.linalg.inv(column(body["bind"]["bone attachpoint"]))
        for rel in t["parts"]:
            pdata = load(rel)
            part = gr2_mesh.read(pdata)
            tex = Figure(game, pdata).meshes[0][1]
            for m in gr2_mesh.attach(body, part, "attachpoint", "attachpoint"):
                pts = apply(att, to_file_points(m["positions"], body["basis"]))
                items.append((pts, m["triangles"][:, ::-1], m["uvs"], tex, (90, 90, 90)))
        gdata = load(t["guy"])
        grig = Rig.of(gr2.load(gdata).root())
        gp = grig.by_name(grig.pose(Animation.load(game.granny(t["guy_clip"])), 0.0))
        items += Figure(game, gdata).items(gp, tr((-1.0, 0.0, -0.2)))
        return items
    except (FileNotFoundError, gr2.Gr2Error, KeyError, IndexError, ValueError):
        return None


def zamburak_items(game, recipe, camel, rider, scene):
    P = camel.pose(camel.base, 0.0)
    R = rider.seated(rider.idle, 0.0, P[camel.rider_bone], square=False)       # as the stock unit sits
    return Figure(game, camel.data).items(P) + scene.rider_fig.items(R) + scene.hat_items(R)


VIEWS = [("FRONT 3/4", -40.0, 16.0), ("SIDE", -90.0, 8.0), ("BACK 3/4", -140.0, 16.0), ("TOP", -90.0, 78.0)]


def model_sheet(path, game, recipe, camel, rider, scene, plays, cache=None):
    """The new unit from four angles for each gun scale (variant A in the saddle; variant B
    deployed), beside the original zamburak and today's gatling camel."""
    w, h = 300, 270
    view = dict(span=3.9, centre=(0.0, 1.75, 0.15))

    def tile(items, az, el, text, marks=None):
        return caption(draw(items, w, h, az, el, marks=marks, **view), text)

    rows = []
    ref = [tile(zamburak_items(game, recipe, camel, rider, scene), az, el, f"ZAMBURAK (STOCK) {name}")
           for name, az, el in VIEWS[:2]]
    today = today_items(game, cache)
    if today is not None:
        ref += [tile(today, az, el, f"GATLING CAMEL TODAY {name}") for name, az, el in VIEWS[:2]]
    else:
        ref += [caption(np.full((h, w, 3), 236, np.uint8), "TODAY'S MODEL DID NOT READ")] * 2
    rows.append(("REFERENCES: THE ORIGINAL ZAMBURAK AND TODAY'S GATLING CAMEL", ref))
    for (variant, scale), pb in sorted(plays.items()):
        if variant != "A":
            continue
        items, _m = pb.items("idle", 0.0)
        rows.append((f"NEW - A, FROM THE SADDLE - GUN AT {scale:.2f} OF THE STOCK GATLING",
                     [tile(items, az, el, f"A {scale:.2f} {name}") for name, az, el in VIEWS]))
    tiles = []
    for (variant, scale), pb in sorted(plays.items()):
        if variant == "B":
            items, _m = pb.items("deployed", 0.0)
            tiles += [tile(items, az, el, f"B {scale:.2f} DEPLOYED {name}") for name, az, el in
                      (VIEWS[0], ("LEFT 3/4 BACK", -120.0, 16.0))]
    if tiles:
        rows.append(("NEW - B, DEPLOYED (THE CAMEL LYING, THE GUNNER IN THE SADDLE)", tiles[:4]))
    width = 4 * w
    out = [title(width, f"{recipe['name'].upper().replace('_', ' ')} - PREVIEW", back=(70, 40, 20))]
    for text, tl in rows:
        out.append(title(width, text, scale=1, back=(30, 30, 30)))
        out.append(grid(tl + [np.full_like(tl[0], 255)] * (4 - len(tl)), 4))
    from PIL import Image
    Image.fromarray(np.concatenate(out, 0)).save(path)


SEQUENCES = {
    "A": [("idle", 0.0, 1.2), ("fire", None, None), ("fire", None, None), ("reload", None, None),
          ("fire", None, None), ("idle", 0.0, 1.2)],
    "B": [("idle", 0.0, 1.0), ("deploy", None, None), ("deployed", 0.0, 1.0), ("fire", None, None),
          ("fire", None, None), ("reload", None, None), ("fire", None, None), ("undeploy", None, None),
          ("idle", 0.0, 1.0)],
    "move": [("walk", 0.0, None, 3), ("jog", 0.0, None, 4), ("run", 0.0, None, 4)],
}
CAPTIONS = {"idle": "IDLE", "fire": "FIRE", "reload": "RELOAD", "deploy": "DEPLOY (LIE DOWN, GET OFF)",
            "deployed": "DEPLOYED IDLE", "undeploy": "UNDEPLOY (GET ON, STAND UP)", "walk": "WALK", "jog": "JOG", "run": "RUN"}


def gif(path, pb, seq, label, fps=15, width=520, height=420, azimuth=-50.0, span=3.6, centre=(-0.1, 1.55, 0.25),
        in_place=False):
    """A GIF of a sequence of clips [(clip, start, end[, repeats])] of one unit, captioned."""
    from PIL import Image
    frames = []
    root = pb.unit.camel.rig.names[0].lower()
    for entry in seq:
        name, a, b = entry[:3]
        reps = entry[3] if len(entry) > 3 else 1
        length = pb.clips[name][3].length
        a = 0.0 if a is None else a
        b = length if b is None else min(b, length)
        for _r in range(reps):
            for t in np.arange(a, b - 1e-6, 1.0 / fps):
                place = None
                if in_place:
                    P, _G, _R = pb.poses(name, t)
                    P0, _G0, _R0 = pb.poses(name, 0.0)
                    d = P[root][:3, 3] - P0[root][:3, 3]
                    place = tr((-d[0], 0.0, -d[2]))
                items, marks = pb.items(name, t, place)
                img = draw(items, width, height, azimuth, 16.0, span, centre, marks=marks)
                frames.append(caption(img, f"{label}  {CAPTIONS.get(name, name.upper())}  {t:.2f} S", scale=1))
    pics = [Image.fromarray(f).quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            for f in frames]
    pics[0].save(path, save_all=True, append_images=pics[1:], duration=int(round(1000 / fps)), loop=0,
                 optimize=True)
    return os.path.getsize(path), len(frames)


GAZE_ROWS = [(("A", "idle", 0.0), "A IDLE AT THE GUN: ALONG THE BARRELS"),
             (("A", "fire", 0.5), "A FIRING: ALONG THE BARRELS"),
             (("A", "walk", 0.2), "A ON THE MOVE: AHEAD, LEFT HAND ON THE GUN"),
             (("B", "fire", 0.5), "B FIRING ON FOOT: DOWNRANGE")]


def gaze_sheet(path, plays, scale):
    """Where the rider looks, without doubt: each pose from the front, the unit's left and its
    right, close on the rider."""
    w, h = 300, 280
    out = []
    for (variant, clip, t), text in GAZE_ROWS:
        pb = plays.get((variant, scale))
        if pb is None:
            continue
        items, _m = pb.items(clip, t)
        _P, _G, R = pb.poses(clip, t)
        head = R["bip01 head"][:3, 3]
        centre = (head[0], head[1] - 0.45, head[2])
        tiles = [caption(draw(items, w, h, az, 8.0, 2.0, centre), f"{name}") for name, az in
                 (("FRONT", 0.0), ("UNIT'S LEFT", -90.0), ("UNIT'S RIGHT", 90.0))]
        out.append(title(3 * w, f"{text} ({scale:.2f})", scale=1))
        out.append(np.concatenate(tiles, 1))
    from PIL import Image
    Image.fromarray(np.concatenate([title(3 * w, "WHERE THE RIDER LOOKS", back=(70, 40, 20))] + out, 0)).save(path)


# --------------------------------------------------------------------------------------------------
# The gun turned on its trunnion (aim preview): what a game key that turns the gun, not the camel,
# would show, drawn from the poses (not from written clips)


class Aim:
    """One unit's firing pose at a gun yaw: the camel as its fire clip has it, the gun turned on
    its trunnion, the rider or gunner following (chest, head, both hands on the gun)."""

    def __init__(self, scene, unit, model_bytes, couched=False):
        """`couched`: A's gun and seated rider on the camel lying down (B's lying pose): the gunner
        stays in the saddle and fires from there (an alternative to B on foot)."""
        self.scene, self.unit = scene, unit
        self.model_bytes = model_bytes
        self.couched = couched
        self.clip = next(c for c in unit.clips if c.get("do") == "fire")
        cam = unit.camel
        if "camel" in self.clip:
            self.anim = cam.anim(self.clip["camel"])
            self.length = self.anim.duration
        else:
            self.anim = cam.anim(self.clip["still"])
            self.length = float(self.clip["length"])
            self.still = cam.fix_hang(cam.grounded(self.anim, [0.0])[0])
        if couched:
            self.still = cam.fix_hang(cam.grounded(cam.anim(B_IDLE), [0.0])[0])
        elif getattr(unit, "home", 0.0) and "camel" not in self.clip:
            self.still = unit.neck_turned(self.still, 1.0)        # round 6: its head out of his way

    def camel_pose(self, t):
        cam, clip = self.unit.camel, self.clip
        if self.couched:
            return self.still
        if "camel" in clip:
            P = cam.pose(self.anim, t)
            if clip.get("lower"):
                P = cam.lower_head(P, clip["lower"] + clip.get("dip", 0.0) * math.sin(math.pi * t / self.length) ** 2)
            return P
        return self.still

    def poses(self, t, yaw, stand=None):
        """(camel, gun, rider) world frames by bone name, and how far a palm stays from its target.
        B: `stand` is the gunner's body on his feet (a Traverse pose); None: settled at the yaw's
        station."""
        u = self.unit
        P = self.camel_pose(t)
        state = u.fire_state(t % self.length, self.length)
        state["yaw"] = yaw
        fr = u.gun.frames(state)
        C = u.C(P)
        attach = rigid(P[u.camel.rider_bone])
        b = Built(self.clip, [t])
        base = u.rider.anim(self.clip["rider"]) if self.clip.get("rider") else u.rider.idle
        if u.style == "B":
            if getattr(self, "traverse", None) is None:
                self.traverse = Traverse(self)
            u._stand_at = stand if stand is not None else self.traverse.settled(yaw)
        try:
            R = u.rider_pose(self.clip, "fire", t % self.length, self.length, (t % self.length) / self.length, P, C,
                             fr, base, attach, b)
        finally:
            u._stand_at = None
        chest = rigid(P[u.camel.hang])
        G = {f"bone_{u.gun_name}".lower(): chest}
        for k in GunDesign.BONES[1:]:
            G[GunDesign.bone_name(k).lower()] = chest @ u.gun.to_model(fr[k])
        return P, G, R, b.reach

    @staticmethod
    def stretch(R):
        """{side: shoulder-to-wrist distance / the arm's length}: 1.0 is a locked straight arm."""
        out = {}
        for s in ("l", "r"):
            a, b, c = (R[f"bip01 {s} {k}"][:3, 3] for k in ("upperarm", "forearm", "hand"))
            out[s] = float(np.linalg.norm(c - a) / (np.linalg.norm(b - a) + np.linalg.norm(c - b)))
        return out

    def items(self, gun_fig, t, yaw, stand=None):
        P, G, R, reach = self.poses(t, yaw, stand)
        s = self.scene
        out = s.camel_fig.items(P) + gun_fig.items(G) + s.rider_fig.items(R) + s.hat_items(R)
        marks = []
        if any(0.0 <= (t % self.length) - f < 0.045 for f in Unit.shots(self.length)):
            mz = G["bone_launchpoint"][:3, 3]
            marks.append((mz + 0.06 * unit(G["bone_launchpoint"][:3, :3] @ Z), (255, 200, 40), 9))
        return out, marks, reach


class Traverse:
    """B's gunner traversing the gun on foot, as a man walks a pintle gun round: for each yaw a
    station (where his feet stand on the ground, which way he faces) chosen so that his hands reach
    the crank and the casing as they do at rest, his body and feet stay clear of the lying camel
    and his head out of the barrels' line, near the last station; between stations he steps, one
    foot lifted and set down at a time while the other stays planted, his body carried between his
    feet (no sliding)."""

    STEP_TIME = 0.30          # seconds a step takes
    STEP_LIFT = 0.10          # how high the foot rises
    STEP_DIST = 0.08          # a foot steps when its place is this far (metres) ...
    STEP_TURN = 12.0          # ... or this many degrees from where it should be
    BODY_R = 0.24             # the gunner's body seen from above (metres) kept off the camel
    FOOT_R = 0.09
    HEAD_CLEAR = 0.40         # his head this far at least from the barrels' line

    def __init__(self, aim):
        u = self.u = aim.unit
        self.rig = u.rider.rig
        self.root = self.rig.names[0].lower()
        self.P0 = aim.camel_pose(0.0)
        self.C = u.C(self.P0)
        self.stand = u.stand_pose()
        r = self.stand[self.root][:3, 3]
        self.s0 = np.array([r[0], r[2]])
        self.h0 = 90.0
        sh = 0.5 * (self.stand["bip01 r upperarm"][:3, 3] + self.stand["bip01 l upperarm"][:3, 3])
        self.sh0 = sh
        pts = np.concatenate([np.asarray(it[0]) for it in aim.scene.camel_fig.items(self.P0)])
        self.body_pts = pts[pts[:, 1] < 1.55][:, [0, 2]]
        self.low_pts = pts[pts[:, 1] < 0.45][:, [0, 2]]
        self.feet0 = {s: self.stand[f"bip01 {s} foot"] for s in ("l", "r")}
        self.d0 = self._reach(self.s0, self.h0, u.gun.frames({}))
        # at rest he does not face the grips' middle exactly: keep that offset
        g0 = self.grips(u.gun.frames({}))
        self.hoff = self.h0 - math.degrees(math.atan2(g0[0] - self.sh0[0], g0[2] - self.sh0[2]))
        # as close to the camel as he stands at rest (the approved pose), no closer
        self.body_r = min(self.BODY_R, float(np.sqrt(((self.body_pts - self.s0) ** 2).sum(1)).min()) - 0.01)
        fr0 = [self.feet0[s][:3, 3][[0, 2]] for s in ("l", "r")]
        self.foot_r = min(self.FOOT_R, min(float(np.sqrt(((self.low_pts - f) ** 2).sum(1)).min()) for f in fr0) - 0.01)
        # upper arm, and elbow to palm (metres)
        st = self.stand
        self.arm_len = {s: (float(np.linalg.norm(st[f"bip01 {s} forearm"][:3, 3] - st[f"bip01 {s} upperarm"][:3, 3])),
                            float(np.linalg.norm(st[f"bip01 {s} hand"][:3, 3] - st[f"bip01 {s} forearm"][:3, 3])))
                        for s in ("l", "r")}
        self._cache = {}

    # round 6: the lying camel seen from above as the height of its top at each spot (FIELD_STEP metres
    # apart), so a place inside its body, or a head under its neck, is never read as clear (a distance
    # to its vertices alone found the middle of its back clear: the hull has no vertex there)
    FIELD_STEP = 0.03
    FIELD_X = (-1.9, 0.9)
    FIELD_Z = (-1.6, 2.4)

    def _tops(self):
        if getattr(self, "_top", None) is not None:
            return self._top
        cam = self.u.camel
        cam.mesh_points(self.P0)
        meshes, skel = cam._mesh
        names = [b["name"] for b in skel["bones"]]
        exact = {n: self.P0[n.lower()] for n in names if n.lower() in self.P0}
        xs = np.arange(self.FIELD_X[0], self.FIELD_X[1] + 1e-9, self.FIELD_STEP)
        zs = np.arange(self.FIELD_Z[0], self.FIELD_Z[1] + 1e-9, self.FIELD_STEP)
        X_, Z_ = np.meshgrid(xs, zs, indexing="ij")
        x, z = X_.ravel(), Z_.ravel()
        top = np.full(len(x), -np.inf)
        for msh in meshes:
            p = gr2_skin.deform(msh["file_positions"], msh["vertex_bones4"], msh["vertex_weights4"], msh["skin_names"],
                                skel, exact)
            for a, b, c in p[np.asarray(msh["triangles"], np.int64)]:
                d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                if abs(d) < 1e-12:
                    continue
                lo_x, hi_x = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
                lo_z, hi_z = min(a[2], b[2], c[2]), max(a[2], b[2], c[2])
                sel = np.nonzero((x >= lo_x) & (x <= hi_x) & (z >= lo_z) & (z <= hi_z))[0]
                if not len(sel):
                    continue
                w1 = ((b[2] - c[2]) * (x[sel] - c[0]) + (c[0] - b[0]) * (z[sel] - c[2])) / d
                w2 = ((c[2] - a[2]) * (x[sel] - c[0]) + (a[0] - c[0]) * (z[sel] - c[2])) / d
                w3 = 1.0 - w1 - w2
                hit = (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
                h = w1 * a[1] + w2 * b[1] + w3 * c[1]
                top[sel[hit]] = np.maximum(top[sel[hit]], h[hit])
        self._top = (xs, zs, top.reshape(len(xs), len(zs)))
        self._clear_fields = {}
        return self._top

    def clear(self, x, z, height):
        """How far (metres, seen from above) the spots (x, z) are from any part of the lying camel
        that reaches `height` or higher (0 inside it)."""
        xs, zs, top = self._tops()
        key = round(float(height), 2)
        field = self._clear_fields.get(key)
        if field is None:
            occ = top >= height
            idx = np.argwhere(occ)
            if not len(idx):
                field = np.full(top.shape, 9.0)
            else:
                P = np.c_[xs[idx[:, 0]], zs[idx[:, 1]]]
                X_, Z_ = np.meshgrid(xs, zs, indexing="ij")
                Q = np.c_[X_.ravel(), Z_.ravel()]
                best = np.full(len(Q), 9.0)
                for i in range(0, len(P), 300):
                    p = P[i:i + 300]
                    best = np.minimum(best, np.sqrt(((Q[:, None, :] - p[None, :, :]) ** 2).sum(-1)).min(1))
                field = best.reshape(top.shape)
            self._clear_fields[key] = field
        x, z = np.asarray(x, np.float64), np.asarray(z, np.float64)
        ix = np.clip(np.round((x - xs[0]) / self.FIELD_STEP).astype(int), 0, len(xs) - 1)
        iz = np.clip(np.round((z - zs[0]) / self.FIELD_STEP).astype(int), 0, len(zs) - 1)
        out = field[ix, iz]
        far = (x < xs[0]) | (x > xs[-1]) | (z < zs[0]) | (z > zs[-1])
        return np.where(far, 9.0, out)

    # his parts kept clear of the camel (round 6): (bone, how far, the camel's height that counts below
    # the bone's own)
    CLEAR_PARTS = (("bip01 pelvis", 0.20, 0.35), ("bip01 spine1", 0.16, 0.25), ("bip01 l upperarm", 0.10, 0.15),
                   ("bip01 r upperarm", 0.10, 0.15), ("bip01 head", 0.14, 0.15))

    def body_clearance_cost(self, place, weight):
        """The cost of his body's parts nearer the camel than CLEAR_PARTS allows, for `place` (a rest
        point -> (x, y, z) arrays at every candidate)."""
        cost = 0.0
        for bone, need, below in self.CLEAR_PARTS:
            x, y, z = place(self.stand[bone][:3, 3])
            cost = cost + weight * np.maximum(0.0, need - self.clear(x, z, float(np.mean(y)) - below))
        for s in ("l", "r"):
            x, _y, z = place(self.feet0[s][:3, 3])
            cost = cost + weight * np.maximum(0.0, self.FOOT_R - self.clear(x, z, 0.02))
        return cost

    # a station: (x, z) of his root on the ground and his heading (degrees about +y, 90: facing +x)
    def M(self, s, h):
        return tr((s[0], 0.0, s[1])) @ rot4(axis_matrix(Y, h - self.h0)) @ tr((-self.s0[0], 0.0, -self.s0[1]))

    def grips(self, fr):
        u = self.u
        if getattr(u, "long", False):
            r, l_ = self.hand_goals(fr)
            return 0.5 * (r + l_)
        left = u.b_left_grip(fr)
        left = u.target(left, fr) if isinstance(left, str) else left
        return 0.5 * (point(self.C, u.target("crank", fr)[0]) + point(self.C, left[0]))

    def _reach(self, s, h, fr):
        sh = point(self.M(s, h), self.sh0)
        d = self.grips(fr) - sh
        return math.hypot(d[0], d[2])

    def hand_goals(self, fr):
        """(the right hand's grip, the left hand's) in the world: the crank's handle and the casing,
        or with the long handles the traverse bar and the drop crank."""
        u = self.u
        if getattr(u, "long", False):
            return point(self.C, u.target("bar", fr)[0]), point(self.C, u.target("dropcrank", fr)[0])
        left = u.b_left_grip(fr)
        left = u.target(left, fr) if isinstance(left, str) else left
        return point(self.C, u.target("crank", fr)[0]), point(self.C, left[0])

    def wrist_goals(self, fr):
        """{side: wrist} in the world for the long handles' grips: the wrist where the hand holds
        its grip (palm on it, fingers and palm turned as the grip asks), so a reach is measured to
        what the arm's two bones must reach."""
        from aoe3game.gr2_pose import basis_of
        u, body = self.u, self.u.rider.body
        out = {}
        for s, name in (("r", "bar"), ("l", "dropcrank")):
            palm_d, fin, nor = u.target(name, fr)
            palm = point(self.C, palm_d)
            rot = basis_of(u.world_dir(self.C, fin), u.world_dir(self.C, nor)) @ \
                basis_of(body.finger_local[s], body.normal_local[s]).T
            out[s] = palm - rot @ body.palm_local[s]
        return out

    def _search(self, yaw, prev):
        u = self.u
        fr = u.gun.frames({"yaw": yaw})
        if not hasattr(self, "_grid"):
            xs = np.arange(-1.7, 0.5, 0.03)
            zs = np.arange(-1.0, 1.9, 0.03)
            X_, Z_ = np.meshgrid(xs, zs)
            S = np.c_[X_.ravel(), Z_.ravel()]

            def mind(P, Q):
                best = np.full(len(P), 9.0)
                for i in range(0, len(Q), 400):
                    q = Q[i:i + 400]
                    best = np.minimum(best, np.sqrt(((P[:, None, :] - q[None, :, :]) ** 2).sum(-1)).min(1))
                return best
            self._mind = mind
            self._grid = (S, mind(S, self.body_pts))
            r0, l0 = self.hand_goals(u.gun.frames({}))
            self._arm0 = {"r": float(np.linalg.norm(r0 - self.stand["bip01 r upperarm"][:3, 3])),
                          "l": float(np.linalg.norm(l0 - self.stand["bip01 l upperarm"][:3, 3]))}
            if getattr(u, "long", False):             # elbows bent, at his chest: about half a metre
                self._arm0 = {"r": LONG_ARM, "l": LONG_ARM}
        S, body_clear = self._grid
        n = len(S)
        hr, hl = self.hand_goals(fr)
        wrists = self.wrist_goals(fr) if getattr(u, "long", False) else None
        g = 0.5 * (hr + hl)
        # headings: facing the grips' middle (as at rest), then turned -30..30 degrees from it
        base = np.degrees(np.arctan2(g[0] - (S[:, 0]), g[2] - (S[:, 1]))) + self.hoff
        if getattr(u, "long", False):                 # behind the breech: facing along the barrels
            bd = point(self.C, fr["muzzle"][:3, 3]) - point(self.C, fr["cannon"][:3, 3])
            base = np.full(n, math.degrees(math.atan2(bd[0], bd[2])) - 90.0 + self.h0)
        best = (np.inf, None)
        p0 = point(self.C, fr["cannon"][:3, 3])
        p1 = point(self.C, fr["muzzle"][:3, 3])
        p1 = p1 + 1.5 * (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-6)
        seg = np.array([p1[0] - p0[0], p1[2] - p0[2]])
        L2 = max(seg @ seg, 1e-9)
        hard = 8000.0 if getattr(u, "long", False) and u.handle_set != "v4" else 400.0   # v5: clearances first
        camel = hard * np.maximum(0.0, self.body_r - body_clear)
        wide = 42.0 if getattr(u, "long", False) and u.handle_set != "v4" else 30.0
        for dh in np.arange(-wide, wide + 0.1, 6.0):
            h = base + dh
            a = np.radians(h - self.h0)
            cos, sin = np.cos(a), np.sin(a)

            def place(p):            # a rest-pose point carried to each candidate station (x, y, z)
                x0, z0 = p[0] - self.s0[0], p[2] - self.s0[1]
                return S[:, 0] + x0 * cos + z0 * sin, np.full(n, p[1]), S[:, 1] - x0 * sin + z0 * cos
            cost = camel.copy()
            reach = np.zeros(n)
            ahead_v5 = getattr(u, "long", False) and u.handle_set != "v4"
            for s, goal in (("r", hr), ("l", hl)):
                x, y, z = place(self.stand[f"bip01 {s} upperarm"][:3, 3])
                d = np.sqrt((goal[0] - x) ** 2 + (goal[1] - y) ** 2 + (goal[2] - z) ** 2)
                if ahead_v5:
                    # v5: the palm in front of his chest (PALM_AHEAD along his facing), the elbow bent
                    # ELBOW_BEND (the middle preferred): hard limits, then the preference
                    La, Lb = self.arm_len[s]
                    wr = wrists[s]
                    d = np.sqrt((wr[0] - x) ** 2 + (wr[1] - y) ** 2 + (wr[2] - z) ** 2)
                    bend = np.degrees(np.arccos(np.clip((d * d - La * La - Lb * Lb) / (2 * La * Lb), -1.0, 1.0)))
                    hr_ = np.radians(h)
                    ahead = (goal[0] - x) * np.sin(hr_) + (goal[2] - z) * np.cos(hr_)
                    lo, hi = ELBOW_SEARCH
                    cost += 2.0 * np.maximum(0.0, lo - bend) ** 2 + 2.0 * np.maximum(0.0, bend - hi) ** 2
                    cost += 1e3 * (d > La + Lb)
                    cost += 400.0 * np.maximum(0.0, PALM_AHEAD - ahead)
                    cost += 0.002 * (bend - 0.5 * (lo + hi)) ** 2
                    reach = np.maximum(reach, d - (La + Lb))
                    continue
                # as far from the grip as at rest; farther (a straighter arm) costs much more
                cost += 40.0 * (d - self._arm0[s]) ** 2 + 800.0 * np.maximum(0.0, d - self._arm0[s]) ** 2
                reach = np.maximum(reach, d - self._arm0[s])
            if ahead_v5:
                # facing the barrels, and behind the turret (on the side away from the muzzle) as far
                # as the camel lets him
                cost += 0.002 * dh ** 2
                cx, _cy, cz = place(self.sh0)
                rx, rz = cx - p0[0], cz - p0[2]
                bx, bz = -seg[0] / math.sqrt(L2), -seg[1] / math.sqrt(L2)
                behind = np.degrees(np.arccos(np.clip((rx * bx + rz * bz) / np.maximum(np.hypot(rx, rz), 1e-6), -1, 1)))
                cost += 0.0003 * behind ** 2
            for s in ("l", "r"):
                fx, _fy, fz = place(self.feet0[s][:3, 3])
                cost += hard * np.maximum(0.0, self.foot_r - self._mind(np.c_[fx, fz], self.low_pts))
            if self.home:                       # round 6: his body clear of the camel at every height
                cost += self.body_clearance_cost(place, hard)
            # his head out of the barrels' line (pivot to well past the muzzle, near his head's height)
            hx, _hy, hz = place(self.stand["bip01 head"][:3, 3])
            w = np.clip(((hx - p0[0]) * seg[0] + (hz - p0[2]) * seg[1]) / L2, 0.0, 1.0)
            dl = np.hypot(hx - (p0[0] + w * seg[0]), hz - (p0[2] + w * seg[1]))
            cost += 200.0 * np.maximum(0.0, self.HEAD_CLEAR - dl)
            if prev is not None:
                # stay near where he was (few steps), a little near his rest place
                dturn = (h - prev[1] + 180.0) % 360.0 - 180.0
                cost += 3.0 * ((S - prev[0]) ** 2).sum(1) + 0.0004 * dturn ** 2
                # stations change little from one yaw step to the next (short steps, feet never crossed)
                far, turn = prev[2] if len(prev) > 2 else (0.10, 9.0)
                cost += 1e4 * ((np.sqrt(((S - prev[0]) ** 2).sum(1)) > far) | (np.abs(dturn) > turn))
            if not getattr(u, "long", False):
                cost += 0.3 * ((S - self.s0) ** 2).sum(1)
            i = int(np.argmin(cost))
            if cost[i] < best[0]:
                best = (float(cost[i]), ((S[i].copy(), float(h[i])), {"reach": float(reach[i]), "line": float(dl[i])}))
        c, (st, info) = best
        return st, c, info

    def table(self, step=5):
        """{yaw: (station, cost, info)} from 0 out to +90 and to -90, each from its neighbour. v5
        (long handles, handles "v5"): only the stations the steps go between (Traverse.stair: 0, the
        ends of the 45-degree segments to his right and the arc's end to his left), each from the one
        before it within two steps' reach (STATION_STEP metres, STATION_TURN degrees); the stations
        between are not stood at."""
        if not self._cache:
            u = self.u
            if getattr(u, "long", False) and u.handle_set != "v4":
                home = self.home
                self._cache[home] = self._search(home, None)
                for sign in (1, -1):
                    step_, count = self.segments(sign)
                    prev = self._cache[home][0]
                    for k in range(1, count + 1):
                        y = home + sign * k * step_
                        st, c, info = self._search(y, (prev[0], prev[1], (self.STATION_STEP, self.STATION_TURN)))
                        self._cache[y] = (st, c, info)
                        prev = st
                return self._cache
            if getattr(self.u, "long", False):        # his station at 0 found like the others
                st, c, info = self._search(0.0, None)
                self._cache[0] = (st, c, info)
            else:
                self._cache[0] = ((self.s0.copy(), self.h0), 0.0, {"reach": 0.0, "line": 9.0})
            for sign in (1, -1):
                prev = self._cache[0][0]
                for y in range(step, 91, step):
                    st, c, info = self._search(sign * y, prev)
                    self._cache[sign * y] = (st, c, info)
                    prev = st
        return self._cache

    def station(self, yaw):
        tab = self.table()
        keys = sorted(tab)
        yaw = max(keys[0], min(keys[-1], yaw))
        lo = max(k for k in keys if k <= yaw)
        hi = min(k for k in keys if k >= yaw)
        (sa, ha), _c, _i = tab[lo]
        (sb, hb), _c, _i = tab[hi]
        w = 0.0 if hi == lo else (yaw - lo) / (hi - lo)
        dh = (hb - ha + 180.0) % 360.0 - 180.0
        return sa + w * (sb - sa), ha + w * dh

    # stepping as a function of the gun's yaw (what a game can show from the yaw alone, Traverse.stair):
    # both feet set at the stations every STAIR_STEP degrees (to his right: across the camel) and at
    # the arc's end to his left (STAIR_LEFT: 0 and -30); going out from a station, the leading foot
    # steps while the yaw crosses STAIR_LEAD of the segment (a share of it), the other while it
    # crosses STAIR_TRAIL; between those bands both feet stand still. A game lets a step under way
    # finish when the gun comes to rest (the aim file lists the bands), so no foot is left in the air.
    STAIR_STEP = 45.0
    STAIR_LEFT = 30.0           # B's arc toward his own side ends here (round 4: -30)
    STATION_STEP = 0.55         # v5: a station at most this far (metres) from the one before (two steps)
    STATION_TURN = 50.0         # ... and turned at most this much (degrees)
    STAIR_LEAD = (1.0 / 45.0, 21.0 / 45.0)
    STAIR_TRAIL = (24.0 / 45.0, 44.0 / 45.0)

    @property
    def home(self):
        """The gun's rest yaw (degrees): the middle station (round 6: across the camel, B_HOME)."""
        return float(getattr(self.u, "home", 0.0))

    def spans(self):
        """How far the gun turns from home toward a shrinking yaw and toward a growing one (degrees)."""
        u = self.u
        if getattr(u, "segments_per_side", 0):
            lo, hi = u.arc
            return self.home - lo, hi - self.home
        return self.STAIR_LEFT, 90.0

    def segments(self, sign):
        """The segment length and count on one side of home (sign +1: the yaw growing, -1: shrinking)."""
        u = self.u
        if getattr(u, "segments_per_side", 0):
            n = u.segments_per_side
            span = self.spans()[1 if sign > 0 else 0]
            return span / n, n
        return (self.STAIR_STEP, int(round(90.0 / self.STAIR_STEP))) if sign > 0 else (self.STAIR_LEFT, 1)

    def stair_bands(self):
        """The yaw bands in which a foot is stepping, (from, to) degrees, for the aim file."""
        out = []
        h = self.home
        for sign in (1.0, -1.0):
            step, count = self.segments(sign)
            for k in range(count):
                for lo, hi in (self.STAIR_LEAD, self.STAIR_TRAIL):
                    a, b = (k + lo) * step, (k + hi) * step
                    out.append((h + a, h + b) if sign > 0 else (h - b, h - a))
        return sorted(out)

    def lead_foot(self, sign):
        """The foot that leads when the gun turns toward `sign` (+1 right): the one farther along
        his way from the station at home to the next."""
        if not hasattr(self, "_lead"):
            self._lead = {}
        if sign not in self._lead:
            M0 = self.M(*self.station(self.home))
            M1 = self.M(*self.station(self.home + sign * self.segments(sign)[0]))
            way = (M1 @ np.r_[self.s0[0], 0.0, self.s0[1], 1.0])[:3] - (M0 @ np.r_[self.s0[0], 0.0, self.s0[1], 1.0])[:3]
            score = {s: float(point(M0, self.feet0[s][:3, 3]) @ way) for s in ("l", "r")}
            self._lead[sign] = max(score, key=score.get)
        return self._lead[sign]

    def clamp_yaw(self, yaw):
        left, right = self.spans()
        return max(self.home - left, min(self.home + right, float(yaw)))

    def stair(self, yaw):
        """His body on his feet at the gun's yaw (Traverse.STAIR_*): each foot planted at its station
        or, inside its band, lifted and carried to the next one; his body between his feet, the
        legs solved to them."""
        yaw = self.clamp_yaw(yaw)
        rel = yaw - self.home
        sign = 1.0 if rel >= 0 else -1.0
        step, count = self.segments(sign)
        a = abs(rel)
        k = min(int(a // step), count - 1)
        f = (a - k * step) / step                      # the share of the segment crossed
        y0, y1 = self.home + sign * k * step, self.home + sign * (k + 1) * step
        M0, M1 = self.M(*self.station(y0)), self.M(*self.station(y1))
        return self.walk(M0, M1, f, self.lead_foot(sign), self.STAIR_LEAD, self.STAIR_TRAIL)

    def walk(self, M0, M1, f, lead, lead_band, trail_band):
        """His body on his feet going from the place M0 to M1 (Traverse.M), `f` (0..1) of the way:
        the leading foot lifted and carried while f crosses `lead_band`, the other in `trail_band`,
        planted otherwise; his body between his feet, the legs solved to them."""
        from aoe3game.gr2_pose import translate, two_bone_ik
        cur, lift = {}, 0.0
        for s in ("l", "r"):
            lo, hi = lead_band if s == lead else trail_band
            r = min(1.0, max(0.0, (f - lo) / (hi - lo)))
            A, Bm = M0 @ self.feet0[s], M1 @ self.feet0[s]
            kk = smooth(r)
            F = np.eye(4)
            F[:3, :3] = rigid(rot4((1 - kk) * A[:3, :3] + kk * Bm[:3, :3]))[:3, :3]
            up = self.STEP_LIFT * math.sin(math.pi * r)
            F[:3, 3] = (1 - kk) * A[:3, 3] + kk * Bm[:3, 3] + np.array([0.0, up, 0.0])
            cur[s] = F
            lift = max(lift, math.sin(math.pi * r))
        ang, pos = [], []
        for s in ("l", "r"):
            Mf = cur[s] @ np.linalg.inv(self.feet0[s])
            z = Mf[:3, :3] @ Z
            ang.append(math.degrees(math.atan2(z[0], z[2])))
            pos.append(Mf[:3, 3])
        da = (ang[1] - ang[0] + 180.0) % 360.0 - 180.0
        Mb = tr((0.5 * (pos[0][0] + pos[1][0]), 0.0, 0.5 * (pos[0][2] + pos[1][2]))) @ rot4(axis_matrix(Y, ang[0] + 0.5 * da))
        body = {kk_: Mb @ v for kk_, v in self.stand.items()}
        if lift:
            body = translate(body, self.rig, self.root, np.array([0.0, -0.02 * lift, 0.0]))
        fwd = unit(Mb[:3, :3] @ np.array([1.0, 0.0, 0.0]))     # he faces +x at rest
        body_h = self.u.rider.body.hinge
        for s in ("l", "r"):
            th, ca, fo = (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot")
            body = two_bone_ik(body, self.rig, th, ca, fo, cur[s][:3, 3], fwd, body_h[th], body_h[ca],
                               end_frame=cur[s][:3, :3])
        return body

    # v5 reload: from his station behind the turret the hopper is out of reach, so he steps in to
    # RELOAD_SPOT (two steps, RELOAD_STEP_IN of the clip) and back (RELOAD_STEP_OUT)
    RELOAD_STEP_IN = (0.0, 0.50)      # seconds: two steps of 0.25 s (about 0.8 m, a brisk walk)
    RELOAD_STEP_OUT = (2.50, 3.00)
    # round 6: at the reload spot his right palm on the breech box this far in front of his shoulder
    # (metres, standing square): his chest turns to the pocket and to the hopper during the reload
    RELOAD_PALM_AHEAD = 0.30

    def reload_spot(self):
        """(x, z), heading: where he stands to reload with the gun at rest (v5): his left hand as near
        the magazine in the hopper as the lying camel lets him stand, his right hand reaching the
        breech box's near side, few steps from his station, facing within 40 degrees of the hopper."""
        if getattr(self, "_reload_spot", None) is not None:
            return self._reload_spot
        u = self.u
        self.table()
        fr = u.home_frames()
        S, body_clear = self._grid
        n = len(S)
        mag = point(self.C, u.target("magazine", fr)[0])
        box = point(self.C, u.target("casing_side", fr)[0])
        s0_, _h0 = self.station(self.home)
        camel = 400.0 * np.maximum(0.0, self.body_r - body_clear)
        base = np.degrees(np.arctan2(mag[0] - S[:, 0], mag[2] - S[:, 1]))
        best = (np.inf, None)
        for dh in np.arange(-40.0, 40.1, 5.0):
            h = base + dh
            a = np.radians(h - self.h0)
            cos, sin = np.cos(a), np.sin(a)

            def place(p):
                x0, z0 = p[0] - self.s0[0], p[2] - self.s0[1]
                return np.c_[S[:, 0] + x0 * cos + z0 * sin, np.full(n, p[1]), S[:, 1] - x0 * sin + z0 * cos]
            cost = camel.copy()
            dl = np.linalg.norm(mag - place(self.stand["bip01 l upperarm"][:3, 3]), axis=1)
            dr = np.linalg.norm(box - place(self.stand["bip01 r upperarm"][:3, 3]), axis=1)
            cost += 40.0 * dl ** 2 + 400.0 * np.maximum(0.0, dr - sum(self.arm_len["r"]) - 0.12)
            for s in ("l", "r"):
                f_ = place(self.feet0[s][:3, 3])
                cost += 400.0 * np.maximum(0.0, self.foot_r - self._mind(f_[:, [0, 2]], self.low_pts))
            if self.home:                       # round 6: his body clear of the camel at every height
                cost += self.body_clearance_cost(lambda p: tuple(place(p).T), 4000.0)
                # the right palm in front of his chest on the breech box (check_anim's "ahead")
                hr_ = np.radians(h)
                sx, _sy, sz = place(self.stand["bip01 r upperarm"][:3, 3]).T
                ahead_r = (box[0] - sx) * np.sin(hr_) + (box[2] - sz) * np.cos(hr_)
                cost += 400.0 * np.maximum(0.0, self.RELOAD_PALM_AHEAD - ahead_r)
            cost += 0.5 * ((S - s0_) ** 2).sum(1) + 0.0005 * dh ** 2
            i = int(np.argmin(cost))
            if cost[i] < best[0]:
                best = (float(cost[i]), (S[i].copy(), float(h[i])))
        self._reload_spot = best[1]
        return self._reload_spot

    def reload_body(self, t):
        """His body at time t of the reload (v5): at his station 0, stepping in to the reload spot,
        there, stepping back."""
        (a, b), (c, d) = self.RELOAD_STEP_IN, self.RELOAD_STEP_OUT
        M0, M1 = self.M(*self.station(self.home)), self.M(*self.reload_spot())
        if t <= a or t >= d:
            return {k: M0 @ v for k, v in self.stand.items()}
        if b <= t <= c:
            return {k: M1 @ v for k, v in self.stand.items()}
        if not hasattr(self, "_reload_lead"):
            self._reload_lead = (self.best_lead(M0, M1), self.best_lead(M1, M0))
        lead_in, lead_out = self._reload_lead
        if t < b:                                   # in
            return self.walk(M0, M1, (t - a) / (b - a), lead_in, (0.0, 0.5), (0.5, 1.0))
        return self.walk(M1, M0, (t - c) / (d - c), lead_out, (0.0, 0.5), (0.5, 1.0))

    def feet_apart(self, body):
        """How far the right foot is to the right of the left, across his hips (< 0: crossed)."""
        right = body["bip01 r thigh"][:3, 3] - body["bip01 l thigh"][:3, 3]
        right[1] = 0.0
        return float((body["bip01 r foot"][:3, 3] - body["bip01 l foot"][:3, 3]) @ unit(right))

    def best_lead(self, M0, M1, bands=((0.0, 0.5), (0.5, 1.0))):
        """The foot to lead a walk from M0 to M1 with: the one whose steps keep the feet farther
        apart (a step that turns him may otherwise carry the leading foot across the other)."""
        score = {s: min(self.feet_apart(self.walk(M0, M1, f, s, *bands)) for f in np.linspace(0.0, 1.0, 21))
                 for s in ("l", "r")}
        return max(score, key=score.get)

    def reload_share(self, t):
        """How far he is from his station toward the reload spot at time t (0..1)."""
        (a, b), (c, d) = self.RELOAD_STEP_IN, self.RELOAD_STEP_OUT
        if t <= a or t >= d:
            return 0.0
        if b <= t <= c:
            return 1.0
        return smooth((t - a) / (b - a)) if t < b else 1.0 - smooth((t - c) / (d - c))

    def settle_yaw(self, yaw, direction):
        """The yaw at which the step under way at `yaw` ends, the gun having turned toward
        `direction` (+1: the yaw growing, -1: shrinking): the end of the band it is in, else the yaw
        itself (both feet down). Traverse.stair at that yaw is his body once the step has finished."""
        rel = self.clamp_yaw(yaw) - self.home
        sign = 1.0 if rel >= 0 else -1.0
        step, count = self.segments(sign)
        a = abs(rel)
        k = min(int(a // step), count - 1)
        f = (a - k * step) / step
        outward = (direction > 0) == (sign > 0)
        for lo, hi in (self.STAIR_LEAD, self.STAIR_TRAIL):
            if lo < f < hi:
                f = hi if outward else lo
                break
        return self.home + sign * (k + f) * step

    def settled(self, yaw):
        """His body standing at the yaw's station, both feet set."""
        s, h = self.station(yaw)
        M = self.M(s, h)
        return {k: M @ v for k, v in self.stand.items()}

    def sweep(self, times, yaws):
        """His body (on his feet, legs solved to them) at each time while the gun follows `yaws`:
        a foot steps when its place has moved off, one foot at a time."""
        from aoe3game.gr2_pose import translate, two_bone_ik
        body_h = self.u.rider.body.hinge
        M = self.M(*self.station(yaws[0]))
        feet = {s: M @ self.feet0[s] for s in ("l", "r")}
        step, last, out, steps = None, "l", [], []
        for t, yaw in zip(times, yaws):
            M = self.M(*self.station(yaw))
            ideal = {s: M @ self.feet0[s] for s in ("l", "r")}
            if step is None:
                err = {}
                for s in ("l", "r"):
                    dp = np.linalg.norm((ideal[s][:3, 3] - feet[s][:3, 3])[[0, 2]])
                    fa, fb = feet[s][:3, :3] @ Z, ideal[s][:3, :3] @ Z
                    dang = abs(math.degrees(math.atan2(fa[0] * fb[2] - fa[2] * fb[0], fa[0] * fb[0] + fa[2] * fb[2])))
                    err[s] = (dp / self.STEP_DIST, dang / self.STEP_TURN)
                due = [s for s in ("l", "r") if max(err[s]) > 1.0]
                if due:
                    # the foot that keeps them apart: stepping it to its place must leave the right
                    # foot on the right of the left one (no crossed feet); else the other one first
                    lr = self.feet0["r"][:3, 3] - self.feet0["l"][:3, 3]
                    lr[1] = 0.0
                    lr = unit(lr)

                    def apart(s):
                        """How far his right foot is on his right of the left one once `s` has stepped,
                        in the frame of his body then (no crossed feet: well above 0)."""
                        after = {s: ideal[s], ("l" if s == "r" else "r"): feet["l" if s == "r" else "r"]}
                        yaws_ = []
                        for k in ("l", "r"):
                            z = (after[k] @ np.linalg.inv(self.feet0[k]))[:3, :3] @ Z
                            yaws_.append(math.degrees(math.atan2(z[0], z[2])))
                        yb_ = yaws_[0] + 0.5 * ((yaws_[1] - yaws_[0] + 180.0) % 360.0 - 180.0)
                        side = axis_matrix(Y, yb_) @ lr
                        return float((after["r"][:3, 3] - after["l"][:3, 3]) @ side)
                    cand = [s for s in ("l", "r")]
                    ok = [s for s in due if apart(s) > 0.08]
                    if ok:
                        s = max(ok, key=lambda k: max(err[k]))
                    else:                                     # the foot that leaves them most apart
                        s = max(cand, key=apart)
                    step = (s, t, feet[s].copy())
                    steps.append((t, s))
            cur = dict(feet)
            lift = 0.0
            if step is not None:
                s, t0, frm = step
                k = (t - t0) / self.STEP_TIME
                if k >= 1.0:
                    feet[s] = ideal[s]
                    cur[s] = ideal[s]
                    last, step = s, None
                else:
                    kk = smooth(k)
                    f = np.eye(4)
                    f[:3, :3] = rigid(rot4((1 - kk) * frm[:3, :3] + kk * ideal[s][:3, :3]))[:3, :3]
                    f[:3, 3] = (1 - kk) * frm[:3, 3] + kk * ideal[s][:3, 3] + np.array([0.0, self.STEP_LIFT * math.sin(math.pi * k), 0.0])
                    cur[s] = f
                    lift = math.sin(math.pi * k)
            # his body between his feet: each foot says where the body would be; the mean of the two
            ang, pos = [], []
            for s in ("l", "r"):
                Mf = cur[s] @ np.linalg.inv(self.feet0[s])
                z = Mf[:3, :3] @ Z
                ang.append(math.degrees(math.atan2(z[0], z[2])))
                pos.append(Mf[:3, 3])
            da = (ang[1] - ang[0] + 180.0) % 360.0 - 180.0
            yb = ang[0] + 0.5 * da
            pb = 0.5 * (pos[0] + pos[1])
            Mb = tr((pb[0], 0.0, pb[2])) @ rot4(axis_matrix(Y, yb))
            body = {k: Mb @ v for k, v in self.stand.items()}
            if lift:
                body = translate(body, self.rig, self.root, np.array([0.0, -0.02 * lift, 0.0]))
            fwd = unit(Mb[:3, :3] @ np.array([1.0, 0.0, 0.0]))     # he faces +x at rest
            for s in ("l", "r"):
                th, ca, fo = (f"bip01 {s} thigh", f"bip01 {s} calf", f"bip01 {s} foot")
                body = two_bone_ik(body, self.rig, th, ca, fo, cur[s][:3, 3], fwd, body_h[th], body_h[ca],
                                   end_frame=cur[s][:3, :3])
            out.append(body)
        return out, steps


# The aim preview's units: (key, title, the arc it can serve naturally (left, right), where to look)
AIM_UNITS = {
    "A": ("A, FROM THE SADDLE", (90.0, 90.0), (-0.1, 2.05, 0.05)),
    "C": ("B, OPTION 1 (RECOMMENDED): THE CAMEL LIES DOWN, THE GUNNER STAYS IN THE SADDLE", (90.0, 90.0),
          (0.2, 1.75, 0.3)),
    "B": ("B, OPTION 2: THE CAMEL LIES DOWN, THE GUNNER ON FOOT STEPS ROUND", (75.0, 75.0), (-0.2, 1.25, 0.45)),
}
AIM_VIEWS = [("FROM ABOVE (CAMEL'S HEAD UP)", 180.0, 89.0, 3.2), ("BEHIND, LEFT", -150.0, 18.0, 2.3),
             ("FRONT, RIGHT", 35.0, 12.0, 2.3)]


def _tint(img):
    img = img.copy()
    img[:, :, 0] = np.minimum(255, img[:, :, 0].astype(np.int32) + 45).astype(np.uint8)
    return img


def aim_sheet(path, game, aims, angles=AIM_ANGLES):
    """The gun turned on its mount at each yaw (columns): first the mount alone, close (the gun
    stays seated on its post), then each unit from above, from behind on the left and from the
    front on the right: the camel keeps still, the rider or gunner follows. A yaw the unit cannot
    serve naturally is tinted red (there the camel turns instead)."""
    from PIL import Image
    w, h = 250, 240
    width = w * len(angles)
    out = [title(width, "GATLING CAMEL - THE GUN TURNS ON ITS MOUNT, NOT THE CAMEL (PREVIEW 2)", back=(70, 40, 20))]
    notes = []
    first = aims.get("A") or next(iter(aims.values()))
    aim, fig = first
    for vname, az, el in (("THE MOUNT, CLOSE, FROM THE LEFT (NO RIDER)", -90.0, 4.0),
                          ("THE MOUNT, CLOSE, FROM ABOVE (NO RIDER)", 180.0, 85.0)):
        tiles = []
        for yaw in angles:
            P, G, _R, _r = aim.poses(aim.length * 0.5, yaw)
            pw = point(aim.unit.C(P), aim.unit.gun.post)
            img = draw(aim.scene.camel_fig.items(P) + fig.items(G), w, h, az, el, 1.1, tuple(pw), ground=False)
            tiles.append(caption(img, f"MOUNT {yaw:+.0f}"))
        out.append(title(width, vname + ": THE GUN TURNS ABOUT THE POST'S AXIS AND STAYS SEATED ON IT", scale=1))
        out.append(np.concatenate(tiles, 1))
    for key in ("A", "C", "B"):
        if key not in aims:
            continue
        aim, gun_fig = aims[key]
        what, (left, right), centre = AIM_UNITS[key]
        t = aim.length * (0.5 + 0.5 / SHOTS)                 # just after a shot: a flash shows
        for vname, az, el, span in AIM_VIEWS:
            tiles = []
            for yaw in angles:
                items, marks, reach = aim.items(gun_fig, t, yaw)
                P, G, R, _r = aim.poses(t, yaw)
                st = Aim.stretch(R)
                img = draw(items, w, h, az, el, span, (0.0, 1.0, 0.25) if el > 80 else centre, marks=marks)
                side = "RIGHT" if yaw > 0 else "LEFT" if yaw < 0 else "AHEAD"
                text = f"{yaw:+.0f} {side}"
                if yaw < -left or yaw > right:
                    text += " - CAMEL TURNS"
                    img = _tint(img)
                tiles.append(caption(img, text + (f" GAP {reach * 100:.0f}CM" if reach > 0.02 else "")))
                if vname == AIM_VIEWS[0][0]:
                    notes.append(f"{key} yaw {yaw:+.0f}: palm gap {reach * 100:.1f} cm, arms (shoulder to wrist / "
                                 f"length) l {st['l']:.2f} r {st['r']:.2f}")
            out.append(title(width, f"{what} - {vname}", scale=1))
            out.append(np.concatenate(tiles, 1))
    Image.fromarray(np.concatenate(out, 0)).save(path)
    return notes


# B's gun turns at a walking man's pace (its tactics' <turret maxTurnAnglePerSecond>): he steps round
B_TURN_RATE = 100.0


def shown_yaws(targets, fps, rate, bands):
    """The gun's shown yaw frame by frame as a game turns it (turretArc): toward each target in
    turn at `rate` degrees a second, each target held its seconds; a target inside a stepping band
    is taken to the band's nearer edge (no foot left in the air). targets: [(yaw, seconds)]."""
    def out_of_band(y):
        for a, b in bands:
            if a < y < b:
                return a if y - a < b - y else b
        return y
    cur, out = 0.0, []
    for tgt, secs in targets:
        tgt = out_of_band(tgt)
        for _k in range(int(round(secs * fps))):
            step = rate / fps
            cur = tgt if abs(tgt - cur) <= step else cur + math.copysign(step, tgt - cur)
            out.append(cur)
    return out


def palms_ahead(rider, R):
    """{side: metres} each palm in front of its shoulder along his facing (his chest's forward, level)."""
    f = unit(R["bip01 spine1"][:3, :3] @ rider.chest_local)
    f[1] = 0.0
    f = unit(f)
    return {s: float((rider.palm_of(R, s) - R[f"bip01 {s} upperarm"][:3, 3]) @ f) for s in ("l", "r")}


STILL_ANGLES = (-30.0, 0.0, 30.0, 60.0, 90.0)


def still_angles(u):
    """The five yaws the stills show: B's arc in four equal parts (round 6: 30 60 90 120 150)."""
    if getattr(u, "home", 0.0):
        lo, hi = u.arc
        return tuple(float(v) for v in np.linspace(lo, hi, 5))
    return STILL_ANGLES
STILL_RELOAD = (0.0, 0.25, 0.50, 0.66, 1.02, 1.42, 1.80, 2.22, 2.36, 2.46, 2.75, 3.0)


def stills(folder, pb, scene, label):
    """Stills of B on foot (no clip rendering): the gun at STILL_ANGLES while it fires, from behind him
    on the left, from above and from his side, each captioned with how far each palm is in front of
    its shoulder; and the reload at STILL_RELOAD seconds from two views. Returns report lines."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    u = pb.unit
    aim = Aim(scene, u, None)
    trav = getattr(pb, "traverse", None) or Traverse(aim)
    aim.traverse = trav
    fig = pb.gun_fig
    stem = os.path.join(folder, label)
    t_fire = aim.length * (0.5 + 0.5 / SHOTS)
    lines = []
    views = [("BEHIND HIM, LEFT", -150.0, 15.0, 2.6, (-0.3, 1.1, 0.2)),
             ("FROM ABOVE (CAMEL'S HEAD UP)", 180.0, 89.0, 3.2, (-0.1, 1.0, 0.2)),
             ("FROM HIS SIDE (THE CAMEL'S LEFT)", -90.0, 8.0, 2.8, (-0.3, 1.0, 0.2))]
    w, h = 300, 280
    angles = still_angles(u)
    rows = [title(w * len(angles), f"{label.upper()}: B ON FOOT FIRING, THE GUN AT "
                                   + " ".join(f"{a:.0f}" for a in angles) +
                                   ", L/R: EACH PALM IN FRONT OF ITS SHOULDER", back=(70, 40, 20))]
    for vname, az, el, span, cen in views:
        tiles = []
        for yaw in angles:
            stand = trav.stair(yaw)
            items, marks, reach = aim.items(fig, t_fire, yaw, stand)
            _P, _G, R, _r = aim.poses(t_fire, yaw, stand)
            ah = palms_ahead(u.rider, R)
            img = draw(items, w, h, az, el, span, cen, marks=marks)
            tiles.append(caption(img, f"{yaw:+.0f}  L {ah['l'] * 100:+.0f} R {ah['r'] * 100:+.0f} CM"))
            if vname == views[0][0]:
                lines.append(f"gun {yaw:+.0f}: palms in front of the shoulders l {ah['l'] * 100:+.0f} cm, "
                             f"r {ah['r'] * 100:+.0f} cm; grips missed by {reach * 100:.1f} cm")
        rows.append(title(w * len(angles), vname, scale=1))
        rows.append(np.concatenate(tiles, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(stem + "-angles.png")
    os.makedirs(os.path.join(folder, "parts"), exist_ok=True)
    for k in range(len(views)):                 # each view's row alone, to set two versions side by side
        Image.fromarray(rows[2 + 2 * k]).save(os.path.join(folder, "parts", f"{label}-angles-{k}.png"))
    if "reload" in pb.clips:
        length = pb.clips["reload"][3].length
        P0, _G0, R0 = pb.poses("reload", 0.0)
        chest = R0["bip01 spine1"][:3, 3]
        Pm, _Gm, Rm = pb.poses("reload", 0.5 * length)
        chest = 0.5 * (chest + Rm["bip01 spine1"][:3, 3])
        centre = (chest[0] + 0.1, chest[1] - 0.1, chest[2] + 0.2)
        tiles = []
        for t in STILL_RELOAD:
            t = min(t, length - 1e-3)
            items, marks = pb.items("reload", t)
            _P, _G, R = pb.poses("reload", t)
            ah = palms_ahead(u.rider, R)
            for az, el, name in ((-150.0, 15.0, "BEHIND LEFT"), (-40.0, 15.0, "FRONT LEFT")):
                img = draw(items, 250, 230, az, el, 2.8, centre, marks=marks)
                tiles.append(caption(img, f"{t:.2f} S {name} L {ah['l'] * 100:+.0f} R {ah['r'] * 100:+.0f}"))
        sheet = grid(tiles, 6)
        Image.fromarray(sheet).save(os.path.join(folder, "parts", f"{label}-reload.png"))
        Image.fromarray(np.concatenate([title(sheet.shape[1], f"{label.upper()}: THE RELOAD'S KEY POSES "
                                              f"({length:.2f} S), TWO VIEWS EACH, L/R: PALMS IN FRONT OF THE "
                                              "SHOULDERS (CM)", back=(70, 40, 20)), sheet], 0)).save(stem + "-reload.png")
    # round 6: the deploy's end and the undeploy's start (the gun swung between ahead and its rest
    # yaw), and the death, two views each
    seqs = []
    if "deploy" in pb.clips:
        L = pb.clips["deploy"][3].length
        seqs.append(("deploy", [L - 2.0 + d for d in (0.0, 0.6, 1.0, 1.2, 1.35, 1.5, 1.65, 1.8, 2.0)]))
    if "undeploy" in pb.clips:
        seqs.append(("undeploy", [0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0, 1.6, 2.0]))
    if "death" in pb.clips:
        seqs.append(("death", [0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 2.5, 3.0]))
    for name, ts in seqs:
        length = pb.clips[name][3].length
        tiles = []
        for t in ts:
            t = min(max(t, 0.0), length - 1e-3)
            items, marks = pb.items(name, t)
            if name == "death" and getattr(pb, "dead_fig", None) is not None:
                # the game plays it on the dead model (the gun built in, on the turret bone), the
                # gunner attached; the gun's own clip is not played
                P, _G, R = pb.poses(name, t)
                items = pb.dead_fig.items(P) + scene.rider_fig.items(R) + scene.hat_items(R)
            views = ((-150.0, 15.0, "BEHIND LEFT"), (180.0, 80.0, "ABOVE"))
            if name == "death":
                views += ((60.0, 6.0, "FRONT RIGHT, LOW"),)
            for az, el, vname in views:
                img = draw(items, 250, 230, az, el, 3.2, (-0.3, 1.0, 0.5), marks=marks)
                tiles.append(caption(img, f"{name.upper()} {t:.2f} S {vname}"))
        tiles += [np.zeros_like(tiles[0])] * ((-len(tiles)) % 6)
        sheet = grid(tiles, 6)
        Image.fromarray(np.concatenate([title(sheet.shape[1], f"{label.upper()}: {name.upper()} ({length:.2f} S), "
                                              "TWO VIEWS PER MOMENT", back=(70, 40, 20)), sheet], 0)
                        ).save(f"{stem}-{name}.png")
    return lines


def round4_preview(folder, pb, scene, label, fps=15):
    """B on foot with the turning gun (round 4): the gunner at -90, -45, 0, 45 and 90 degrees
    (a sheet, four views), stepping round the post as a game turns the gun (GIFs, and a sheet of
    the feet every 2 degrees from 0 to 60), and the dismount and the remount (a GIF and a sheet).
    Returns report lines: the palms' gaps, how far a planted foot moves (it should not), how high
    the feet are."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    u = pb.unit
    aim = Aim(scene, u, None)
    trav = getattr(pb, "traverse", None) or Traverse(aim)
    aim.traverse = trav
    fig = pb.gun_fig
    lines = []
    stem = os.path.join(folder, label)
    t_fire = aim.length * (0.5 + 0.5 / SHOTS)
    # 1. the five angles
    views = [("FROM ABOVE (CAMEL'S HEAD UP)", 180.0, 89.0, 3.4, (0.0, 1.0, 0.25)),
             ("BEHIND HIM, LEFT", -150.0, 18.0, 2.6, (-0.3, 1.1, 0.4)),
             ("FRONT, RIGHT", 35.0, 12.0, 2.8, (-0.3, 1.1, 0.4)),
             ("HIS FEET, LOW", -100.0, 6.0, 2.4, (-0.4, 0.6, 0.4))]
    angles = (-30.0, 0.0, 30.0, 60.0, 90.0)
    w, h = 300, 280
    rows = [title(w * len(angles), f"{label.upper()}: B ON FOOT, THE GUN AT -30 0 30 60 90 (FIRING; HIS ARC -30..+90)", back=(70, 40, 20))]
    for vname, az, el, span, cen in views:
        tiles = []
        for yaw in angles:
            stand = trav.stair(yaw)
            items, marks, reach = aim.items(fig, t_fire, yaw, stand)
            img = draw(items, w, h, az, el, span, cen, marks=marks)
            tiles.append(caption(img, f"{yaw:+.0f}" + (f" GAP {reach * 100:.0f}CM" if reach > 0.02 else "")))
            if vname == views[0][0]:
                lines.append(f"B on foot at {yaw:+.0f}: palms within {reach * 100:.1f} cm of the crank and the casing")
        rows.append(title(w * len(angles), vname, scale=1))
        rows.append(np.concatenate(tiles, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(stem + "-B-angles.png")
    # 2. the feet every 2 degrees from 0 to 60: planted outside the bands, a step inside
    bands = trav.stair_bands()
    feet = {}
    for y in range(-30, 91, 1):
        S = trav.stair(float(y))
        feet[y] = {s: S[f"bip01 {s} foot"][:3, 3].copy() for s in ("l", "r")}
    slide = 0.0
    for y in range(-30, 90, 1):
        sign = 1.0 if y >= 0 else -1.0
        step, _count = trav.segments(sign)
        for s in ("l", "r"):
            lead = trav.lead_foot(sign) == s
            lo, hi = trav.STAIR_LEAD if lead else trav.STAIR_TRAIL
            a0, a1 = sorted((abs(y), abs(y + 1)))
            f0, f1 = (a0 % step) / step, (a1 % step) / step if a1 % step else 1.0
            if f1 <= lo + 1e-9 or f0 >= hi - 1e-9:            # the foot is planted over this degree
                slide = max(slide, float(np.linalg.norm(feet[y + 1][s] - feet[y][s])))
    lines.append(f"stepping: a planted foot moves at most {slide * 1000:.1f} mm per degree of the gun "
                 f"(bands {[(round(a, 1), round(b, 1)) for a, b in bands]})")
    tiles = []
    for y in list(range(-30, 1, 6)) + list(range(6, 91, 6)):
        items, marks, _r = aim.items(fig, 0.0, float(y), trav.stair(float(y)))
        img = draw(items, 240, 220, -100.0, 6.0, 2.2, (-0.4, 0.55, 0.4))
        tiles.append(caption(img, f"GUN {y:+d}"))
    tiles += [np.zeros_like(tiles[0])] * ((-len(tiles)) % 8)
    sheet = grid(tiles, 8)
    Image.fromarray(np.concatenate([title(sheet.shape[1], f"{label.upper()}: HIS FEET AS THE GUN TURNS -30 TO 90, "
                                          "EVERY 6 DEGREES: ONE FOOT STEPS AT A TIME, THE OTHER STAYS PLANTED",
                                          back=(70, 40, 20)), sheet], 0)).save(stem + "-B-steps.png")
    # 3. the gun turned as a game turns it, he steps round (two views)
    targets = [(0.0, 0.8), (45.0, 1.0), (90.0, 1.2), (45.0, 1.0), (0.0, 1.0), (-30.0, 1.2), (0.0, 1.0),
               (90.0, 1.6), (0.0, 1.6)]
    yaws = shown_yaws(targets, fps, B_TURN_RATE, bands)
    for vname, az, el, span, cen in (("close", -125.0, 14.0, 3.0, (-0.3, 0.9, 0.4)),
                                     ("from-above", 180.0, 70.0, 3.4, (0.0, 1.0, 0.25))):
        frames = []
        for k, yaw in enumerate(yaws):
            t = k / fps
            items, marks, _r = aim.items(fig, t, yaw, trav.stair(yaw))
            img = draw(items, 480, 400, az, el, span, cen, marks=marks)
            frames.append(caption(img, f"B ON FOOT  GUN {yaw:+.0f}  {t:.2f} S", scale=1))
        pics = [Image.fromarray(f).quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
                for f in frames]
        pics[0].save(f"{stem}-B-step-around-{vname}.gif", save_all=True, append_images=pics[1:],
                     duration=int(round(1000 / fps)), loop=0, optimize=True)
    # 4. the dismount and the remount
    seq = [("deploy", None, None), ("deployed", 0.0, 1.0), ("undeploy", None, None)]
    gif(stem + "-B-dismount-remount.gif", pb, seq, "B", fps, width=480, height=400, azimuth=-110.0,
        span=3.4, centre=(-0.3, 1.1, 0.3))
    tiles = []
    for name in ("deploy", "undeploy"):
        length = pb.clips[name][3].length
        for t in np.linspace(0.0, length - 1e-3, 12):
            items, marks = pb.items(name, t)
            for az in (-110.0, -30.0):
                img = draw(items, 230, 210, az, 14.0, 3.4, (-0.3, 1.1, 0.3), marks=marks)
                tiles.append(caption(img, f"{name.upper()} {t:.2f} S"))
    sheet = grid(tiles, 8)
    Image.fromarray(np.concatenate([title(sheet.shape[1], f"{label.upper()}: B GETS OFF (DEPLOY) AND BACK ON "
                                          "(UNDEPLOY), TWO VIEWS PER MOMENT", back=(70, 40, 20)), sheet], 0)
                    ).save(stem + "-B-dismount-remount.png")
    for name in ("deploy", "undeploy"):
        b = pb.clips[name][3]
        low = min(min(R[f"bip01 {s} foot"][1, 3] for s in ("l", "r")) for R in b.rider)
        lines.append(f"{name}: {b.length:.3f} s, the feet's lowest bone height {low:.3f} m")
    return lines


def round4_handles(folder, pb, scene, label):
    """The long handles' picture (round 4, B on foot): the gun with the drop crank, its shaft and
    gear boxes and the traverse bar from four sides at two heights (alone and on the lying camel);
    the gunner holding both grips at -90, -45, 0, 45, 90; the tightest clearances (the drop crank's
    circle over the hump). Returns report lines (clearances, the palms' gaps)."""
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    u = pb.unit
    g = u.gun
    aim = Aim(scene, u, None)
    trav = getattr(pb, "traverse", None) or Traverse(aim)
    aim.traverse = trav
    fig = pb.gun_fig
    stem = os.path.join(folder, label)
    lines = []
    P = aim.camel_pose(0.0)
    chest = rigid(P[u.camel.hang])
    names = {i: (m_.get("name") or "") for i, (m_, _t) in enumerate(fig.meshes)}
    made_idx = [i for i, n in names.items() if any(k in n for k in ("dropcrank", "dropshaft", "traversebar"))]

    def gun_pose(yaw, crank=0.0):
        fr = g.frames({"yaw": yaw, "crank": crank})
        G = {f"bone_{u.gun_name}".lower(): chest}
        for k in GunDesign.BONES[1:]:
            G[GunDesign.bone_name(k).lower()] = chest @ g.to_model(fr[k])
        return fr, G
    # 1. the gun, four sides x two heights, alone and on the lying camel
    w, h = 300, 280
    pivot_w = point(u.C(P), g.pivot)
    low = 0.5 * (pivot_w + u.handles["low_w"])
    rows = [title(w * 8, f"{label.upper()}: B'S GUN WITH THE LONG HANDLES (DROP CRANK, SHAFT AND GEAR BOXES, "
                         "TRAVERSE BAR); THE GUN AT 0, CRANK AT 0", back=(70, 40, 20))]
    _fr, G = gun_pose(0.0)
    for what, items_of, span in (("THE GUN ALONE", lambda: fig.items(G), 1.2),
                                 ("ON THE LYING CAMEL", lambda: scene.camel_fig.items(P) + fig.items(G), 1.8)):
        tiles = []
        for el in (8.0, 45.0):
            for az in (-90.0, 0.0, 90.0, 180.0):
                side = {-90.0: "HIS SIDE (LEFT)", 0.0: "FRONT", 90.0: "RIGHT", 180.0: "BEHIND"}[az]
                img = draw(items_of(), w, h, az, el, span, tuple(low), ground=what != "THE GUN ALONE")
                tiles.append(caption(img, f"{side} EL {el:.0f}"))
        rows.append(title(w * 8, what, scale=1))
        rows.append(np.concatenate(tiles, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(stem + "-gun.png")
    # 2. the gunner at the five angles
    angles = (-30.0, 0.0, 30.0, 60.0, 90.0)
    views = [("FROM ABOVE (CAMEL'S HEAD UP)", 180.0, 89.0, 3.0, (0.0, 1.0, 0.25)),
             ("BEHIND HIM, LEFT", -150.0, 15.0, 2.4, None),
             ("FRONT, LEFT", -40.0, 15.0, 2.4, None),
             ("HIS RIGHT SIDE, LOW", 120.0, 5.0, 2.4, None)]
    rows = [title(w * 5, f"{label.upper()}: B ON FOOT HOLDING BOTH GRIPS (LEFT HAND THE DROP CRANK, RIGHT THE "
                         "TRAVERSE BAR) AT -30 0 30 60 90", back=(70, 40, 20))]
    t_fire = 0.0
    for vname, az, el, span, cen in views:
        tiles = []
        for yaw in angles:
            stand = trav.stair(yaw)
            items, marks, reach = aim.items(fig, t_fire, yaw, stand)
            c = cen
            if c is None:
                r0 = stand[trav.root][:3, 3]
                c = (r0[0], 1.2, r0[2])
            img = draw(items, w, h, az, el, span, c, marks=marks)
            tiles.append(caption(img, f"{yaw:+.0f}" + (f" GAP {reach * 100:.1f}CM" if reach > 0.005 else "")))
            if vname == views[0][0]:
                _P, _G, R, _r = aim.poses(t_fire, yaw, stand)
                sh = {s: float(np.linalg.norm(R[f"bip01 {s} hand"][:3, 3] - R[f"bip01 {s} upperarm"][:3, 3]))
                      for s in ("l", "r")}
                lines.append(f"gun {yaw:+.0f}: palms within {reach * 100:.1f} cm of the grips; shoulder to wrist "
                             f"l {sh['l']:.2f} r {sh['r']:.2f} m")
        rows.append(title(w * 5, vname, scale=1))
        rows.append(np.concatenate(tiles, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(stem + "-gunner.png")
    # 3. the clearances: the made parts above the camel's surface, every 15 degrees and every 30 of
    # the crank; the gunner's body off the bar and the crank (his hands excluded)
    cam = u.camel
    worst = []
    for yaw in range(-90, 91, 15):
        for crank in range(0, 360, 30):
            _fr, G = gun_pose(float(yaw), float(crank))
            items = fig.items(G)
            gap, part = 9.0, ""
            for i in made_idx:
                for q in np.asarray(items[i][0])[::2]:
                    ys = cam.surface_heights(P, q[0], q[2])
                    ys = ys[ys < q[1] + 0.5]
                    if len(ys):
                        top = ys.max()
                        d = float(q[1] - top) if top <= q[1] else -float(top - q[1])
                        if d < gap:
                            gap, part = d, names[i].split("_")[-1]
            worst.append((gap, yaw, crank, part))
    worst.sort()
    for lo, hi in ((-90, 90), (-30, 90)):
        sel = [w_ for w_ in worst if lo <= w_[1] <= hi]
        lines.append(f"handles above the camel's surface, gun {lo:+d}..{hi:+d} (worst): " +
                     ", ".join(f"{gp * 100:.1f} cm ({pt}) at gun {y:+d} crank {c}" for gp, y, c, pt in sel[:4]))
    worst = [w_[:3] for w_ in worst]
    body = []
    for yaw in range(-90, 91, 15):
        stand = trav.stair(float(yaw))
        _P, G, R, _r = aim.poses(0.0, float(yaw), stand)
        rp = np.concatenate([np.asarray(it[0]) for it in scene.rider_fig.items(R)])
        hands = np.r_[R["bip01 l hand"][:3, 3], R["bip01 r hand"][:3, 3]].reshape(2, 3)
        far = rp[np.min(np.linalg.norm(rp[:, None, :] - hands[None, :, :], axis=2), axis=1) > 0.16]
        items = fig.items(G)
        pts = np.concatenate([np.asarray(items[i][0]) for i in made_idx])
        d = float(np.min(np.linalg.norm(pts[::3, None, :] - far[None, ::4, :], axis=2)))
        body.append((d, yaw))
    body.sort()
    lines.append("handles off his body away from his hands (worst): " +
                 ", ".join(f"{d * 100:.1f} cm at gun {y:+d}" for d, y in body[:3]))
    # the close-up of the tightest
    tiles = []
    for gp, yaw, crank in worst[:4]:
        _fr, G = gun_pose(float(yaw), float(crank))
        c = tuple(point(u.C(P), g.at["crank2"]) + np.array([0.0, -0.05, 0.0]))
        for az, el in ((-90.0, 4.0), (-150.0, 20.0)):
            img = draw(scene.camel_fig.items(P) + fig.items(G), 360, 320, az, el, 0.8, c)
            tiles.append(caption(img, f"GUN {yaw:+d} CRANK {crank}: {gp * 100:.1f} CM ABOVE THE CAMEL"))
    Image.fromarray(np.concatenate([title(360 * len(tiles), f"{label.upper()}: THE TIGHTEST CLEARANCES, THE DROP "
                                          "CRANK'S CIRCLE OVER THE HUMP", back=(70, 40, 20)),
                                    np.concatenate(tiles, 1)], 0)).save(stem + "-clearance.png")
    return lines


def aim_gif(path, aim, gun_fig, label, fps=15, sweep=4.0, width=480, height=400, azimuth=180.0, elevation=40.0,
            span=3.8, centre=(0.0, 1.2, 0.3), left=90.0, right=90.0, hold=0.6):
    """The gun swept from straight ahead to `right` degrees right, back across to `left` left and
    ahead again while it fires (the barrels spin, the flashes show), the camel still; it rests
    `hold` seconds at each end. B on foot steps round with it (Traverse.sweep)."""
    from PIL import Image
    frames = []
    n = int(round(sweep * fps))
    times, yaws = [], []
    for k in range(n):
        s = math.sin(2 * math.pi * k / n)
        times.append(k / fps)
        yaws.append(s * (right if s > 0 else left))
    # rests at the ends: repeat the extreme frames' yaw
    full_t, full_y = [], []
    for k, (t, y) in enumerate(zip(times, yaws)):
        full_y.append(y)
        if k in (n // 4, 3 * n // 4):
            full_y += [y] * int(hold * fps)
    full_t = [k / fps for k in range(len(full_y))]
    stands = [None] * len(full_t)
    if aim.unit.style == "B" and not aim.couched:
        if getattr(aim, "traverse", None) is None:
            aim.traverse = Traverse(aim)
        stands, _steps = aim.traverse.sweep(full_t, full_y)
    for t, yaw, stand in zip(full_t, full_y, stands):
        items, marks, _r = aim.items(gun_fig, t, yaw, stand)
        img = draw(items, width, height, azimuth, elevation, span, centre, marks=marks)
        frames.append(caption(img, f"{label}  GUN YAW {yaw:+.0f}  {t:.2f} S", scale=1))
    pics = [Image.fromarray(f).quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            for f in frames]
    pics[0].save(path, save_all=True, append_images=pics[1:], duration=int(round(1000 / fps)), loop=0, optimize=True)
    return os.path.getsize(path), len(frames)


# --------------------------------------------------------------------------------------------------
# The aim table: what a game key that turns the gun on its post (turretArc in the UHC DLL) needs to
# keep the gunner on the gun: his bones at every gun yaw, frame by frame, for the clips he works
# the gun in (the gun's own turn is one bone, bone_yaw, which the key turns itself)


AIM_TABLE_YAWS = tuple(float(y) for y in range(-90, 91, 15))
AIM_TABLE_FPS = 15.0
AIM_TABLE_CLIPS = ("idle", "deployed", "fire", "reload")
# B on foot steps round the post: his feet change within a few degrees (Traverse.STAIR_*), so his
# table is sampled finer, and only for the clips he works the gun in on foot
AIM_TABLE_YAWS_FOOT = tuple(float(y) for y in range(-30, 91, 2))      # B's arc: -30 .. +90
AIM_TABLE_CLIPS_FOOT = ("deployed", "fire", "reload")
AIM_TABLE_SETTLE = ("deployed", "fire")     # B: the clips with his feet settled at rest too (aim_table)


def aim_table(unit, built, traverse=None):
    """The bytes of a unit's aim table (little endian):
    "UHCA", version 1, the gun's yaw bone (32 B, zero padded), the camel's turret bone (32 B), the
    pivot (3 floats: the post's top in the camel's model space, as the fire clip's first frame has
    it), the muzzle at yaw 0 (3 floats, same space and frame: where the shots leave), the yaws
    (count, floats, degrees,
    positive toward the unit's right), the rider's bones (count, 32 B names), then the clips (count;
    each: the rider clip's animation name (64 B), its length (float, seconds), frame count (evenly
    from 0 to the length, both ends), then for
    each frame, each yaw, each bone: position (3 floats) and rotation (x, y, z, w) local to its
    parent, as the clip's own tracks hold them). At yaw 0 the values are the clip's own, so a game
    blending the two nearest yaws and frames starts from what it plays. Only bones that move with
    the yaw are listed. B on foot (`traverse`): every 2 degrees, his feet stepping round the post
    (Traverse.stair), and after the clips "BAND", a count and the (from, to) yaw bands in which a
    foot is in the air; then "SETL", a count and, for the clips he stands at the gun in (deployed,
    fire), the clip's name (64 B), length and frame count and two tables laid out as above: his
    pose at each yaw once the step under way has finished, the gun having turned toward a growing
    yaw, then toward a shrinking one (Traverse.settle_yaw: his feet down, his hands on the grips at
    that yaw). A game blends to them when the gun comes to rest, so no foot is left in the air."""
    import struct as st
    cam, rider, g = unit.camel, unit.rider, unit.gun
    names = rider.rig.names
    foot = unit.style == "B" and traverse is not None
    yaws_t = AIM_TABLE_YAWS_FOOT if foot else AIM_TABLE_YAWS
    if foot and unit.home:              # round 6: the arc about the gun's rest yaw, every 2 degrees
        lo, hi = unit.arc
        yaws_t = tuple(float(y) for y in np.arange(lo, hi + 1e-6, 2.0))
    clips_t = AIM_TABLE_CLIPS_FOOT if foot else AIM_TABLE_CLIPS
    stairs = {y: traverse.stair(y) for y in yaws_t} if foot else {}
    settled = {d: {y: traverse.stair(traverse.settle_yaw(y, d)) for y in yaws_t} for d in (1, -1)} if foot else {}

    def table(b, stand_of):
        clip = b.clip
        do = clip.get("do")
        length = b.length
        count = max(2, int(round(length * AIM_TABLE_FPS)) + 1)     # evenly over the clip, both ends
        idx = [int(round(k * (len(b.times) - 1) / (count - 1))) for k in range(count)]
        base = rider.anim(clip["rider"]) if clip.get("rider") else rider.idle
        plan = getattr(b, "plan", None)
        keys = unit.magazine_keys(unit.bag_point(b.camel[0])) if do == "reload" and plan is None else None
        frames = []
        for i in idx:
            t, P = float(b.times[i]), b.camel[i]
            u = t / length
            row = []
            for yaw in yaws_t:
                state = unit.fire_state(t, length) if do == "fire" else {}
                if keys is not None:
                    state["magazine"] = unit.magazine_frame(keys, u)
                if plan is not None:
                    state["magazine"], state["magazine2"] = plan["old"][i], plan["new"][i]
                    unit._plan_at = (plan, i)
                state["yaw"] = yaw
                fr = g.frames(state)
                attach = rigid(P[cam.rider_bone])
                unit._stand_at = stand_of.get(yaw)
                try:
                    R = unit.rider_pose(clip, do, t, length, u, P, unit.C(P), fr, base, attach, Built(clip, [t]))
                finally:
                    unit._plan_at = None
                    unit._stand_at = None
                row.append(rider.to_local(R, attach))
            frames.append(row)
        return frames, len(idx)

    tables, settles = [], []
    length_of = {}
    for b in built.values():
        clip = b.clip
        if clip["name"] not in clips_t:
            continue
        name = unit.clip_name("rider", b)
        frames, count = table(b, stairs)
        tables.append((name, frames, count))
        length_of[name] = float(length_of.get(name, b.length))
        if foot and clip["name"] in AIM_TABLE_SETTLE:
            settles.append((name, [table(b, settled[d])[0] for d in (1, -1)], count))
    # the bones that move with the yaw (or settle)
    zero = yaws_t.index(unit.home if unit.home in yaws_t else 0.0)
    moving = set()
    every = [frames for _n, frames, _c in tables] + [fr for _n, both, _c in settles for fr in both]
    for frames in every:
        for row in frames:
            for y, loc in enumerate(row):
                for k, (p, q) in enumerate(loc):
                    p0, q0 = row[zero][k]
                    if np.abs(np.asarray(p) - np.asarray(p0)).max() > 1e-5 or \
                            min(np.abs(np.asarray(q) - np.asarray(q0)).max(), np.abs(np.asarray(q) + np.asarray(q0)).max()) > 1e-5:
                        moving.add(k)
    bones = sorted(moving)

    def name32(s, n=32):
        b = s.encode("ascii")[: n - 1]
        return b + b"\0" * (n - len(b))

    def data(frames):
        return [st.pack("<7f", *[float(v) for v in loc[k][0]], *[float(v) for v in loc[k][1]])
                for row in frames for loc in row for k in bones]
    # the pivot and the muzzle where the unit fires: at the first frame of its fire clip (B: the camel
    # lying down, its post much lower than at the bind pose), in the camel's model space
    fire = built.get("fire")
    Cf = unit.C(fire.camel[0]) if fire is not None else np.eye(4)
    mz = point(unit.home_turn(), g.at["muzzle"])          # the muzzle with the gun at its rest yaw
    pivot, muzzle = (point(Cf, g.post), point(Cf, mz)) if fire is not None else (g.post, mz)
    # version 2 (round 6): the gun's rest yaw follows the muzzle (its clips show the gun there, so a
    # game turns the bones by the aim less that yaw); version 1 rests ahead
    head = [b"UHCA", st.pack("<I", 2 if unit.home else 1), name32(GunDesign.bone_name("yaw")), name32("bone_turret"),
            st.pack("<3f", *[float(v) for v in pivot]), st.pack("<3f", *[float(v) for v in muzzle])]
    if unit.home:
        head.append(st.pack("<f", float(unit.home)))
    out = head + [
           st.pack("<I", len(yaws_t)),
           st.pack(f"<{len(yaws_t)}f", *yaws_t), st.pack("<I", len(bones))]
    out += [name32(names[k]) for k in bones]
    out.append(st.pack("<I", len(tables)))
    for name, frames, count in tables:
        out += [name32(name, 64), st.pack("<fI", length_of[name], count)] + data(frames)
    if foot:
        bands = traverse.stair_bands()
        out += [b"BAND", st.pack("<I", len(bands))] + [st.pack("<2f", a, b_) for a, b_ in bands]
        out += [b"SETL", st.pack("<I", len(settles))]
        for name, both, count in settles:
            out += [name32(name, 64), st.pack("<fI", length_of[name], count)] + data(both[0]) + data(both[1])
    return b"".join(out), len(bones), [(n, c) for n, _f, c in tables]


# --------------------------------------------------------------------------------------------------
# The anim file blocks


def _tags(clip, length):
    if clip.get("do") != "fire":
        return ""
    out = []
    for k, t in enumerate(Unit.shots(length)):
        u = t / length
        out.append(f'\t\t\t<tag type="Attack">{u:.2f}</tag>')
        out.append(f'\t\t\t<tag type="Particles" particlename="organgunmuzzle01">{u:.2f}</tag>')
        if k == 0:
            out.append(f'\t\t\t<tag type="SpecificSoundSet" checkvisible="1" set="GatlingGunShoot">{u:.2f}</tag>')
    return "\n".join(out) + "\n"


def anim_blocks(recipe, unit, built):
    """What the three anim files need for one variant and scale: the camel's (its model, the gun
    hung on the mount bone, its anims with the attack tags), the gun's and the rider's."""
    folder, name = recipe["folder"], recipe["name"]
    cam, gun_model = recipe["camel"], unit.gun_name
    lines = [f"<!-- Generated by aoe3-blender-tools tools/make_gun_camel.py: variant {unit.variant}, gun at "
             f"{unit.scale:.2f}. PREVIEW: not tested in game. -->",
             "<!-- 1. The camel's anim file: the model without its swivel gun, the gun and the rider -->",
             f"<attachment>gun<include>{folder}\\{name}_gun_{unit.tag}.xml</include></attachment>",
             f"<attachment>rider<include>{folder}\\{name}_rider_{unit.tag}.xml</include></attachment>",
             f"\t\t<assetreference type=\"GrannyModel\"><file>{folder}\\{name}_camel_nogun</file></assetreference>",
             f"\t\t<attach a=\"gun\" frombone=\"bone_{gun_model}\" tobone=\"{cam.get('hang_tag', cam['mount_bone'])}\" "
             "syncanims=\"1\"/>",
             "\t\t<attach a=\"rider\" frombone=\"hotspot\" tobone=\"ATTACHPOINT\" syncanims=\"1\"/>"]
    for b in built.values():
        c = b.clip
        cfile = f"{folder}\\{unit.clip_name('camel', b)}" if b.camel_bytes else c["camel"]
        lines.append(f"\t<anim>{c['anim']}\n\t\t<assetreference type=\"GrannyAnim\">\n\t\t\t<file>{cfile}</file>\n"
                     f"{_tags(c, b.length)}\t\t</assetreference>\n\t\t<component>ModelComp</component>\n\t</anim>")
    for who in ("gun", "rider"):
        lines.append(f"<!-- 2. {name}_{who}_{unit.tag}.xml: its component"
                     + (f" ({folder}\\{gun_model})" if who == "gun" else " (the rider's model, his hat)")
                     + " and these anims -->")
        for b in built.values():
            lines.append(f"\t<anim>{b.clip['anim']}\n\t\t<assetreference type=\"GrannyAnim\">\n"
                         f"\t\t\t<file>{folder}\\{unit.clip_name(who, b)}</file>\n\t\t</assetreference>\n"
                         f"\t\t<component>ModelComp</component>\n\t</anim>")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------
# The work


def cut_camel(game, recipe):
    """(the camel's bytes without the swivel gun, the cut's description, the post's top)."""
    spec, cut = recipe["camel"], recipe["cut"]
    data = game.granny(spec["model"])
    part = next(p for p in gr2_parts.mesh_parts(data) if p["name"] == spec["mesh"])
    mask, pieces = swivel_pieces(part, spec["mount_bone"], cut["x_below"], cut["y_above"])
    if not pieces:
        raise ValueError("no swivel gun found on the mount bone with the recipe's cut")
    keep = ~mask
    centre = (recipe.get("post") or {}).get("centre", False)
    if cut.get("keep_post", True) and not centre:
        for _c, sel, is_post in pieces:
            if is_post:
                keep[sel] = True
    out = gr2_parts.cut_triangles(data, spec["mesh"], keep)
    info = {"triangles": int(len(part["triangles"])), "cut": int((~keep).sum()),
            "pieces": [(int(len(sel)), bool(post)) for _c, sel, post in pieces]}
    hump = HUMP if spec.get("hump", True) else None
    if hump:
        out, info["hump"] = hump_camel(out, spec["mesh"], hump)
    top = post_top(part, pieces)
    info["old_post_top"] = top.copy()
    if centre:
        # the made post (GunDesign.add_post) on the spine: from the highest surface of the kept mesh
        # there (the saddle, on the hump) up to the old post's top, risen with the rider's seat (the
        # gun keeps its place in front of him)
        top = np.array([0.0, top[1], top[2]])
        hp = next(p for p in gr2_parts.mesh_parts(out) if p["name"] == spec["mesh"])
        info["post_base"] = surface_y(hp["positions"], hp["triangles"], top[0], top[2])
        if hump:
            info["seat_rise"] = Camel(game, spec, out).seat_rise
            top[1] += info["seat_rise"]
    return out, info, top


# The hump (2026-11-26, the user: "make the camels at least have a bit of a hump"). The stock zamburak
# camel's back is flat from the rump to the withers (its midline at 2.11 to 2.14 over 1.1 of its length,
# under the saddle cloth): a dromedary's single hump is made by lifting the back's vertices skinned to
# the spine bones (so the existing skin deforms it): `height` at (x 0, z `z`), falling off as a gaussian
# along the body (`length`) and across it (`width`), and from nothing at `from_y` to all of it at
# `to_y` up the flanks (the belly and legs stay). No vertex, triangle or bone is added. The rider's
# seat (bone attachpoint) rises with the back under it (Camel.seat_rise).
HUMP = {"height": 0.28, "z": 0.0, "length": 0.30, "width": 0.25, "from_y": 1.5, "to_y": 2.1,
        "bones": ("hs bone chest", "hs bone stomach", "hs bone pelvis")}


def hump_rise(spec, x, z, y=None):
    """How far the hump lifts the camel's surface at (x, z) (and height y, when given)."""
    if not spec:
        return 0.0
    r = spec["height"] * math.exp(-((z - spec["z"]) ** 2) / (2 * spec["length"] ** 2)) \
        * math.exp(-(x ** 2) / (2 * spec["width"] ** 2))
    if y is not None:
        u = min(1.0, max(0.0, (y - spec["from_y"]) / (spec["to_y"] - spec["from_y"])))
        r *= u * u * (3 - 2 * u)
    return r


def hump_camel(data, mesh_name, spec):
    """The camel model's bytes with its back lifted into a hump (HUMP): the positions, and each
    moved vertex's normal turned as its faces turn. The game's packed vertex stream edited in place
    was not drawn at all (seen 2026-11-26: its header's unknown word must check the data), so the
    mesh is written again in the plain skinned layout of the game's other unit meshes: Position,
    BoneWeights (4 x u8, adding up to 255), BoneIndices (4 x u8), Normal, Tangent, UV; the same
    vertices in the same order, the same triangles, bindings and texture."""
    from aoe3game import gr2_edit
    from aoe3game.gr2 import NORMAL_UINT8, REAL32, UINT8
    from aoe3game.gr2_types import Spec
    from aoe3game.gr2_write import Flat, serialize
    part = next(p for p in gr2_parts.mesh_parts(data) if p["name"] == mesh_name)
    doc = gr2.load(data)
    src_vs = next(m for m in doc.root().get("Meshes") if m is not None and m.get("Name") == mesh_name) \
        .get("PrimaryVertexData").get("Vertices")
    root = gr2_edit.copy_tree(doc)
    mesh = next(m for m in root.values["Meshes"] if m is not None and m.values.get("Name") == mesh_name)
    pos = part["positions"].copy()
    names = [str(n).lower() for n in part["skin_names"]]
    spine = np.array([names[b] in spec["bones"] for b in part["vertex_bone"]])
    new = pos.copy()
    for i in np.nonzero(spine)[0]:
        new[i, 1] += hump_rise(spec, pos[i, 0], pos[i, 2], pos[i, 1])
    moved = np.nonzero(np.abs(new[:, 1] - pos[:, 1]) > 1e-6)[0]
    tris = part["triangles"]

    def vnormals(p):
        out = np.zeros_like(p)
        fn = np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]])
        for k in range(3):
            np.add.at(out, tris[:, k], fn)
        return out
    n0, n1 = vnormals(pos), vnormals(new)
    nrm = part["normals"].copy()
    for i in moved:
        a, c = n0[i], n1[i]
        if np.linalg.norm(a) > 1e-9 and np.linalg.norm(c) > 1e-9:
            a, c = unit(a), unit(c)
            v = np.cross(a, c)
            sn = float(np.linalg.norm(v))
            if sn > 1e-9:
                nrm[i] = axis_matrix(v / sn, math.degrees(math.atan2(sn, float(a @ c)))) @ nrm[i]
    tan, uvs = part["tangents"], part["uvs"]
    if gr2_mesh.is_packed(src_vs):
        bones, weights = gr2_mesh.packed_skin(src_vs.raw)
    else:
        bones, weights = gr2_mesh._skin_columns(src_vs)
    count = len(new)
    out_raw = bytearray()
    for i in range(count):
        ws = [int(round(255 * float(w))) if b >= 0 else 0 for b, w in zip(bones[i], weights[i])]
        bs = [int(b) if b >= 0 else 0 for b in bones[i]]
        if sum(ws) <= 0:
            ws, bs = [255, 0], [bs[0], 0]
        ws[0] += 255 - sum(ws)                       # they add up to 255
        out_raw += struct.pack("<3f8B3f3f2f", *new[i], ws[0], ws[1], 0, 0, bs[0], bs[1], 0, 0,
                               *nrm[i], *tan[i][:3], *uvs[i])
    vspec = Spec("VertexPWNTT", [(REAL32, "Position", None, 3), (NORMAL_UINT8, "BoneWeights", None, 4),
                                 (UINT8, "BoneIndices", None, 4), (REAL32, "Normal", None, 3),
                                 (REAL32, "Tangent", None, 3), (REAL32, "TextureCoordinates0", None, 2)])
    mesh.values["PrimaryVertexData"].values["Vertices"] = Flat(vspec, bytes(out_raw), count)
    # the bones' bounding boxes grown by the lift (the spine bones' only)
    for bb in mesh.values.get("BoneBindings") or []:
        if str(bb.values.get("BoneName")).lower() in spec["bones"]:
            lo, hi = bb.values.get("OBBMin"), bb.values.get("OBBMax")
            if lo is not None and hi is not None:
                bb.values["OBBMin"] = tuple(float(v) - spec["height"] for v in lo)
                bb.values["OBBMax"] = tuple(float(v) + spec["height"] for v in hi)
    out = serialize(root, type_tag=doc.c.type_tag)
    check = gr2_parts.mesh_parts(out)
    got = next(p for p in check if p["name"] == mesh_name)["positions"]
    if np.abs(got - new).max() > 1e-4:
        raise ValueError("the hump's vertices do not read back")
    return out, {"moved": int(len(moved)), "lift": float((new[:, 1] - pos[:, 1]).max())}


def surface_y(pos, tris, x, z):
    """The highest point where the vertical line through (x, z) meets the triangles (bind pose)."""
    a, b, c = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1.0)
    w1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
    w2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    w3 = 1.0 - w1 - w2
    hit = ok & (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
    if not hit.any():
        raise ValueError(f"no surface under ({x:.3f}, {z:.3f})")
    return float((w1 * a[:, 1] + w2 * b[:, 1] + w3 * c[:, 1])[hit].max())


def launch_bones(cut, camel, src, recipe):
    """The cut camel with `bone_launchpoint` and `bone_muzzle` on its chest at the gun's muzzle
    (of the first scale: one camel model serves one gun size), where the game starts the shots and
    the muzzle flashes (the stock Gatling's own names: the anim files define them)."""
    g = GunDesign(src, camel.hang_bind, recipe["_post"], recipe["scales"][0])
    R = camel.bind[:3, :3] / g.bind_scale
    chest = recipe["camel"]["mount_bone"]
    # `bone_turret` on the post's top, axis-aligned with the camel: the two launch bones hang on it,
    # so a game that turns it about its own y (the post's axis, as the gun's bone_yaw) carries the
    # muzzle flash and the launch point round with the gun (the DLL key turretArc)
    turret = np.eye(4)
    turret[:3, :3] = R.T
    turret[:3, 3] = point(np.linalg.inv(camel.bind), g.post)
    turret_world = camel.bind @ turret
    local = np.eye(4)                                # facing the camel's way, in the turret's frame
    local[:3, 3] = point(np.linalg.inv(turret_world), g.at["muzzle"])
    world = turret_world @ local
    return gr2_parts.add_bones(cut, [("bone_turret", chest, turret, turret_world),
                                     ("bone_launchpoint", "bone_turret", local, world),
                                     ("bone_muzzle", "bone_turret", local, world)])


LEG_WORDS = ("hip", "leg", "shin", "hoof", "arm", "clavicle", "shoulder", "pelvis", "stomach")


def leg_gap(camel, b):
    """For a clip made from a stock camel clip: the largest distance between a leg bone as the
    runtime draws our written clip (read back with its scales) and as it draws the stock clip, or
    None. The legs are never edited, so anything above float noise is a bug (a mirrored leg drawn
    lifted, seen in game 2026-11-23, came from a scale copied in the clip's own axes)."""
    if "camel" not in b.clip or b.camel_bytes is None:
        return None
    stock = camel.anim(b.clip["camel"])
    mine = camel.load(b.camel_bytes)
    bones = [n.lower() for n in camel.rig.names if any(w in n.lower() for w in LEG_WORDS)]
    worst = 0.0
    for t in b.times[::5]:
        a, c = camel.pose(stock, t), camel.pose(mine, t)
        worst = max(worst, max(float(np.abs(a[k][:3, 3] - c[k][:3, 3]).max()) for k in bones))
    return worst


TAG_BONES = {"ATTACHPOINT": "bone attachpoint", "MASTER": "hs bone master", "HEAD": "hs bone head",
             "PELVIS": "hs bone pelvis", "R HAND": "bip01 r hand", "HITPOINTBAR": "bone hitpointbar"}
NECK_BONES = ("hs bone neck lower", "hs bone neck upper")


def limit_rates(rig, poses, limit, fps=30.0, bones=()):
    """The poses (world frames by lower-case name) with each of `bones`' turn against its parent held
    to `limit` degrees a second (a hand that would whip round between two frames eases there
    instead); the rest of the body untouched."""
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


def camel_precomp(camel, template, length, pose_at):
    """The tag file (.gr2.precomp) of a camel clip of ours: the stock idle's tags (ATTACHPOINT, the
    rider's and the gun's tag, MASTER, HEAD, NECK, R HAND, PELVIS), sampled from our clip (ten keys
    a second as the stock files). The game reads an animation's tags from this file; a clip
    without one left the gun to jump off the corpse when it began to fade (seen in game)."""
    from aoe3game import precomp
    from aoe3game.gr2_anim import matrix_quat
    import struct as st
    pre = precomp.load(template)
    keys = max(2, int(round(length * 10)) + 1)
    times = np.linspace(0.0, length, keys)
    poses = [pose_at(float(t)) for t in times]
    neck = 0
    for index, tracks in pre.mapping:
        tag = pre.names[index].upper()
        for k, tr in enumerate(tracks):
            bone = NECK_BONES[min(k, 1)] if tag == "NECK" else TAG_BONES.get(tag)
            if bone is None or bone not in poses[0]:
                continue
            pre.positions[tr] = [tuple(float(v) for v in P[bone][:3, 3]) for P in poses]
            pre.rotations[tr] = [st.pack("<4f", *matrix_quat(rigid(P[bone])[:3, :3])) for P in poses]
    for tr in range(len(pre.positions)):          # every track to the new number of keys
        if len(pre.positions[tr]) != keys:
            pre.positions[tr] = [pre.positions[tr][0]] * keys
            pre.rotations[tr] = [pre.rotations[tr][0]] * keys
    pre.duration = float(length)
    return pre.encode()


def dead_model(camel_bytes, gun_bytes, hang_bind, bone, mesh_bones=None):
    """The camel model with the gun's parts added as rigid meshes bound to the camel's `bone` (its
    chest), at rest: the model of the dead unit, which plays the stock camel deaths. Seen in game
    (2026-11-23): a gun attached to the rider's bone turned in the air during the corpse's last
    half second of fading out, whatever clips, tag files or held anims it was given (inferred: the
    game places attachments differently while a corpse fades); a gun inside the camel's own model
    falls and fades with it. The stock death clips give the chest no scale, so a gun vertex q
    (gun model space) goes to hang_bind @ q in the camel's bind space. `mesh_bones`: {a gun mesh's
    name: another camel bone} for meshes bound elsewhere (a prop lying on the ground)."""
    from aoe3game import gr2_edit
    from aoe3game.gr2_write import Flat, W, serialize
    cdoc = gr2.load(camel_bytes)
    croot = gr2_edit.copy_tree(cdoc)
    groot = gr2_edit.copy_tree(gr2.load(gun_bytes))
    R = hang_bind[:3, :3] / np.cbrt(abs(np.linalg.det(hang_bind[:3, :3])))
    camel_binding = croot.values["Models"][0].values["MeshBindings"][0]
    binds = {}
    for bw in croot.values["Skeletons"][0].values["Bones"]:
        iwt = np.array(bw.values["InverseWorldTransform"], np.float64).reshape(4, 4)
        binds[bw.values.get("Name")] = np.linalg.inv(iwt).T
    for b_ in [bone] + list((mesh_bones or {}).values()):
        if b_ not in binds:
            raise KeyError(b_)
    for gm in groot.values["Meshes"]:
        mesh_bone = (mesh_bones or {}).get(gm.values.get("Name"), bone)
        bind_world = binds[mesh_bone]
        vd = gm.values["PrimaryVertexData"]
        flat = vd.values["Vertices"]
        n = flat.count
        width = len(flat.raw) // (4 * n)
        a = np.frombuffer(flat.raw, "<f4").reshape(n, width).astype(np.float64).copy()
        a[:, 0:3] = (np.c_[a[:, 0:3], np.ones(n)] @ hang_bind.T)[:, :3]
        a[:, 3:6] = a[:, 3:6] @ R.T
        if width >= 11:
            a[:, 6:9] = a[:, 6:9] @ R.T
        vd.values["Vertices"] = Flat(flat.spec, a.astype("<f4").tobytes(), n)
        local = (np.c_[a[:, 0:3], np.ones(n)] @ np.linalg.inv(bind_world).T)[:, :3]
        bb = gm.values["BoneBindings"][0]
        bb.values["BoneName"] = mesh_bone
        bb.values["OBBMin"] = tuple(float(v) for v in local.min(0))
        bb.values["OBBMax"] = tuple(float(v) for v in local.max(0))
        croot.values["Meshes"].append(gm)
        croot.values["VertexDatas"].append(vd)
        croot.values["TriTopologies"].append(gm.values["PrimaryTopology"])
        mb = W(camel_binding.spec, **dict(camel_binding.values))
        mb.values["Mesh"] = gm
        croot.values["Models"][0].values["MeshBindings"].append(mb)
    croot.values["Textures"] = list(croot.values.get("Textures") or []) + list(groot.values.get("Textures") or [])
    croot.values["Materials"] = list(croot.values.get("Materials") or []) + list(groot.values.get("Materials") or [])
    return serialize(croot, type_tag=cdoc.c.type_tag)


def runtime_check(data, runtime, tag):
    import make_pray as mp
    return mp.runtime_check(data, runtime, tag)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--recipe")
    ap.add_argument("--scales", help="gun scales, e.g. 0.55,0.7 (default: the recipe's)")
    ap.add_argument("--variants", help="A,B (default: the recipe's)")
    ap.add_argument("--granny-helper", default=os.path.join(HERE, "granny_recompress.exe"))
    ap.add_argument("--cache", default=r"C:\aoe3bt-cache\all\raw",
                    help="a folder of expanded models by MD5, for models the helper does not expand")
    ap.add_argument("--no-verify", action="store_true", help="skip the game runtime's checks")
    ap.add_argument("--sheet", help="the model sheet (PNG)")
    ap.add_argument("--gifs", help="a folder for the GIFs")
    ap.add_argument("--gif-fps", type=int, default=15)
    ap.add_argument("--gif-scale", type=float, help="the gun scale the GIFs show (default: the first)")
    ap.add_argument("--gaze", help="a sheet of where the rider looks (PNG): front, left and right views")
    ap.add_argument("--aim-sheet", help="a sheet of the gun turned on its trunnion (PNG): -90 to 90 degrees, the "
                                        "rider following")
    ap.add_argument("--aim-gifs", help="a folder for GIFs of the gun swept from 90 left to 90 right while it fires")
    ap.add_argument("--reload", choices=("keep", "toss"),
                    help="the reload (seated gunner): keep (lift the magazine and seat it again) or toss (throw the "
                         "empty one aside, pull a full one from the pocket at his hip); default: the recipe's")
    ap.add_argument("--reload-preview", help="a folder for a close GIF and a contact sheet of each variant's reload")
    ap.add_argument("--round4-handles", help="a folder for the picture of B's long handles (round 4)")
    ap.add_argument("--handle-drop", type=float, help="the drop crank this many metres below the gun's crank "
                                                      "(default %.2f)" % HANDLE_DROP)
    ap.add_argument("--round4-preview", help="a folder for B on foot with the turning gun: the angles, the stepping, "
                                             "the dismount and the remount (round 4)")
    ap.add_argument("--handles", choices=sorted(HANDLE_SETS), help="B's long handles (default %s)" % HANDLES)
    ap.add_argument("--stills", help="a folder for stills of B on foot: the five angles from three views, the "
                                     "reload's key poses")
    args = ap.parse_args(argv)
    try:
        for p in (args.out, args.sheet, args.gifs, args.aim_sheet, args.aim_gifs, args.reload_preview,
                  args.round4_preview, args.round4_handles, args.stills):
            if p:
                refuse_steam(p)
    except RefusedPath as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    recipe = copy.deepcopy(DEFAULT_RECIPE)
    if args.recipe:
        with open(args.recipe, encoding="utf-8") as f:
            recipe.update(json.load(f))
    if args.reload:
        recipe["reload"] = None if args.reload == "keep" else args.reload
    if args.handle_drop is not None:
        recipe["handle_drop"] = args.handle_drop
    if args.handles:
        recipe["handles"] = args.handles
    if args.scales:
        recipe["scales"] = [float(x) for x in args.scales.split(",")]
    if args.variants:
        recipe["variants"] = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    if any(v not in CLIPS for v in recipe["variants"]):
        print("variants: A and/or B", file=sys.stderr)
        return 2
    work = tempfile.mkdtemp(prefix="guncamel_")
    failed = False
    report = []
    try:
        game = Game(args.game, args.granny_helper, work)
        runtime = None
        if not args.no_verify:
            import recompress_models as rm
            runtime = rm.Runtime(args.granny_helper, os.path.join(args.game, "granny2.dll"), work)
        folder = os.path.join(args.out, "art", recipe["folder"])
        os.makedirs(folder, exist_ok=True)
        cut, info, post = cut_camel(game, recipe)
        recipe["_post"] = post
        recipe["_post_base"] = info.get("post_base")
        files = {f"{recipe['name']}_camel_nogun": cut}
        report.append(f"camel {recipe['camel']['model']}: {info['triangles']} triangles, {info['cut']} cut "
                      f"(swivel gun pieces {info['pieces']}: (triangles, kept as the post)); post top "
                      f"{np.round(post, 3).tolist()}")
        src = GunSource(game, recipe["gun"])
        cut = launch_bones(cut, Camel(game, recipe["camel"], cut), src, recipe)
        files[f"{recipe['name']}_camel_nogun"] = cut
        camel = Camel(game, recipe["camel"], cut)
        rider = Rider(game, recipe["rider"])
        foot = Rig.of(gr2.load(game.granny(FOOT_MODEL)).root())
        scene = Scene(game, recipe, camel, rider)
        camel_tags = game._g.raw(ZAMB + "zamburak_camel_idle00.gr2.precomp", "")
        tags = {}
        plays, units = {}, {}
        for variant in recipe["variants"]:
            for scale in recipe["scales"]:
                unit = Unit(recipe, camel, rider, src, variant, scale, foot)
                if unit.style == "B" and unit.long:        # his stations round the gun, before the clips
                    unit.traverse = Traverse(Aim(scene, unit, None))
                model = unit.gun.model_bytes(unit.gun_name)
                files[unit.gun_name] = model
                # round 6 (B's gun at rest across the camel): the dead model's gun on bone_turret, which
                # the deployed death clip turns with it; the stock deaths leave it ahead
                files[f"{recipe['name']}_camel_dead_{unit.tag}"] = dead_model(
                    camel.cut, model, camel.hang_bind, "bone_turret" if unit.home else recipe["camel"]["mount_bone"])
                built = {}
                for clip in unit.clips:
                    b = unit.write(unit.build(clip))
                    built[clip["name"]] = b
                    files[unit.clip_name("gun", b)] = b.gun_bytes
                    files[unit.clip_name("rider", b)] = b.rider_bytes
                    if b.camel_bytes:
                        files[unit.clip_name("camel", b)] = b.camel_bytes
                        mine = camel.load(b.camel_bytes)
                        tags[unit.clip_name("camel", b) + ".gr2.precomp"] = camel_precomp(
                            camel, camel_tags, b.length, lambda t, a=mine: camel.pose(a, t))
                pb = Playback(game, scene, unit, model, built)
                pb.dead_fig = Figure(game, files[f"{recipe['name']}_camel_dead_{unit.tag}"])
                plays[(variant, scale)] = pb
                units[(variant, scale)] = (unit, built)
                g = unit.gun
                report.append(f"variant {variant} scale {scale:.2f}: gun {unit.gun_name}, design scale {g.s:.3f} "
                              f"(mount bind scale {g.bind_scale:.3f}), trunnion at {np.round(g.pivot, 3).tolist()}"
                              + (", mirrored (crank outside)" if g.mirror else ""))
                if unit.style == "B":
                    si = unit.stand_info
                    report.append(f"  gunner on foot: crank at {si['handle height']:.2f}, his shoulders at "
                                  f"{si['shoulder height']:.2f}, crouch {si['crouch']:.2f}")
                for name, b in built.items():
                    legs = leg_gap(unit.camel, b)
                    if legs is not None:
                        report.append(f"  {name:9} legs against the stock clip {b.clip['camel'].split(chr(92))[-1]}: {legs:.1e}")
                        failed |= legs > 1e-3
                    gap = pb.gap(name)
                    ok = gap < 1e-3 and b.reach < 0.03
                    report.append(f"  {name:9} {b.clip['anim']:22} {b.length:.3f} s {len(b.times)} frames; "
                                  f"read back {gap:.1e}; hands off target {b.reach:.3f}" + ("" if ok else "  FAIL"))
                    failed |= not ok
                with open(os.path.join(args.out, f"{recipe['name']}-anims-{unit.tag}.xml"), "w", encoding="utf-8",
                          newline="\r\n") as f:
                    f.write(anim_blocks(recipe, unit, built))
                # the gunner's pose at every yaw of the gun (B on foot: stepping round the post)
                trav = Traverse(Aim(scene, unit, None)) if unit.style == "B" else None
                pb.traverse = trav
                data, nb, clips = aim_table(unit, built, trav)
                aim_path = os.path.join(folder, f"{recipe['name']}_{unit.tag}.aim")
                with open(aim_path, "wb") as f:
                    f.write(data)
                report.append(f"  aim table {os.path.basename(aim_path)}: {len(data)} B, {nb} rider bones, "
                              f"{'every 2 degrees, stepping' if trav else 'every 15 degrees'}, clips "
                              + ", ".join(f"{n} ({c} frames)" for n, c in clips))
        for fname, data in files.items():
            with open(os.path.join(folder, fname + ".gr2"), "wb") as f:
                f.write(data)
            if runtime is not None:
                crc, read, packed = runtime_check(data, runtime, fname[-24:].replace("_", ""))
                ok = crc and read
                report.append(f"runtime {fname}.gr2 {len(data)} B: crc {crc}, read {read}, oodle1 {packed} B"
                              + ("" if ok else "  FAIL"))
                failed |= not ok
        for fname, data in tags.items():
            with open(os.path.join(folder, fname), "wb") as f:
                f.write(data)
        report.append(f"tag files: {len(tags)} (.gr2.precomp of the camel clips)")
        with open(os.path.join(args.out, f"{recipe['name']}-report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print("\n".join(report))
        if args.sheet:
            model_sheet(args.sheet, game, recipe, camel, rider, scene, plays,
                        args.cache if os.path.isdir(args.cache or "") else None)
            print(args.sheet)
        if args.gaze:
            gaze_sheet(args.gaze, plays, args.gif_scale if args.gif_scale else recipe["scales"][0])
            print(args.gaze)
        if args.gifs:
            os.makedirs(args.gifs, exist_ok=True)
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            for variant, fname, az, span, centre in (("A", "A-saddle", -50.0, 3.0, (-0.1, 1.8, 0.3)),
                                                     ("B", "B-deployed", -60.0, 3.2, (-0.3, 1.4, 0.3))):
                pb = plays.get((variant, scale))
                if pb is None:
                    continue
                path = os.path.join(args.gifs, f"{recipe['name'].replace('_', '-')}-{fname}.gif")
                fps = args.gif_fps if variant == "A" else max(8, args.gif_fps - 3)   # B is long: under 6 MB
                size, n = gif(path, pb, SEQUENCES[variant], f"{variant} {scale:.2f}", fps, azimuth=az,
                              span=span, centre=centre)
                print(f"{path} {n} frames {size / 1e6:.1f} MB")
            pb = plays.get(("A", scale))
            if pb is not None:
                path = os.path.join(args.gifs, f"{recipe['name'].replace('_', '-')}-move.gif")
                size, n = gif(path, pb, SEQUENCES["move"], f"A {scale:.2f}", args.gif_fps, azimuth=-60.0,
                              in_place=True)
                print(f"{path} {n} frames {size / 1e6:.1f} MB")
        if args.reload_preview:
            os.makedirs(args.reload_preview, exist_ok=True)
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            mode = recipe.get("reload") or "keep"
            label = {"toss": "TOSS, NEW FROM THE POCKET", "keep": "KEEP"}.get(mode, mode.upper())
            for (variant, sc), pb in sorted(plays.items()):
                if sc != scale or "reload" not in pb.clips:
                    continue
                stem = os.path.join(args.reload_preview, f"{recipe['name'].replace('_', '-')}-reload-{mode}-{variant}")
                P0, _G0, R0 = pb.poses("reload", 0.0)
                chest = R0["bip01 spine1"][:3, 3]
                centre = (chest[0] - 0.25, chest[1] - (0.55 if pb.unit.style == "A" else 0.2), chest[2] - 0.1)
                size, n = gif(stem + ".gif", pb, [("reload", None, None)], f"{variant} {sc:.2f} RELOAD ({label})",
                              args.gif_fps, width=440, height=380, azimuth=-125.0, span=2.6, centre=centre)
                print(f"{stem}.gif {n} frames {size / 1e6:.1f} MB")
                length = pb.clips["reload"][3].length
                from PIL import Image
                tiles = []
                for t in np.linspace(0.0, length, 16):
                    items, marks = pb.items("reload", min(t, length - 1e-3))
                    for az in (-125.0, -60.0):
                        img = draw(items, 230, 210, az, 16.0, 2.6 if az < -100 else 3.4, centre, marks=marks)
                        tiles.append(caption(img, f"{t:.2f} S  {'BEHIND' if az < -100 else 'LEFT FRONT'}"))
                sheet = grid(tiles, 8)
                Image.fromarray(np.concatenate([title(sheet.shape[1], f"{variant} {sc:.2f} RELOAD ({label}): "
                                                f"{length:.2f} S, TWO VIEWS PER MOMENT", back=(70, 40, 20)), sheet],
                                               0)).save(stem + ".png")
                print(stem + ".png")
        if args.round4_handles:
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            pb = plays.get(("B", scale))
            if pb is not None and getattr(pb.unit, "long", False):
                drop = recipe.get("handle_drop", HANDLE_DROP)
                for line in round4_handles(args.round4_handles, pb, scene,
                                           f"{recipe['name'].replace('_', '-')}-round4-handles-drop{int(round(drop * 100))}"):
                    print(line)
        if args.stills:
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            pb = plays.get(("B", scale))
            if pb is not None and pb.unit.style == "B":
                hs = recipe.get("handles", HANDLES)
                for line in stills(args.stills, pb, scene, f"{recipe['name'].replace('_', '-')}-handles-{hs}"):
                    print(line)
        if args.round4_preview:
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            pb = plays.get(("B", scale))
            if pb is not None and pb.unit.style == "B":
                for line in round4_preview(args.round4_preview, pb, scene, f"{recipe['name'].replace('_', '-')}-round4",
                                           args.gif_fps):
                    print(line)
        if args.aim_sheet or args.aim_gifs:
            scale = args.gif_scale if args.gif_scale else recipe["scales"][0]
            aims = {}
            for (variant, sc), pb in plays.items():
                if sc == scale:
                    aims[variant] = (Aim(scene, pb.unit, None), pb.gun_fig)
                    if variant == "A":           # B, option 1: A's gun and rider on the camel lying down
                        aims["C"] = (Aim(scene, pb.unit, None, couched=True), pb.gun_fig)
            if args.aim_sheet:
                for line in aim_sheet(args.aim_sheet, game, aims):
                    print(line)
                print(args.aim_sheet)
            if args.aim_gifs:
                os.makedirs(args.aim_gifs, exist_ok=True)
                names = {"A": "A-saddle", "C": "B1-couched-saddle", "B": "B2-on-foot"}
                for key, (aim, fig) in sorted(aims.items()):
                    _what, (left, right), centre = AIM_UNITS[key]
                    views = [("close", -150.0 if key != "B" else -125.0, 16.0, 2.3, centre),
                             # about as the game's camera sees a unit (from high, the whole unit)
                             ("game-camera", -45.0, 50.0, 4.6, (0.0, 1.0, 0.2))]
                    if key == "B":
                        views.append(("feet", -100.0, 10.0, 2.0, (-0.3, 0.55, 0.45)))
                    for view, az, el, span, cen in views:
                        path = os.path.join(args.aim_gifs, f"{recipe['name'].replace('_', '-')}-aim-{names[key]}-{view}.gif")
                        size, n = aim_gif(path, aim, fig, f"{names[key]} {sc:.2f}", fps=args.gif_fps, sweep=6.0,
                                          azimuth=az, elevation=el, span=span, centre=cen, left=left, right=right,
                                          width=440, height=380)
                        print(f"{path} {n} frames {size / 1e6:.1f} MB")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
