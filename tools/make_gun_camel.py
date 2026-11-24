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
  planted, one foot stepping at a time), and he reloads on foot from the pocket on his thigh. To
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
    BONES = ("root", "yaw", "cannon", "barrel", "crank", "ammo", "ammo2", "muzzle")

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
                       "ammo": "cannon", "ammo2": "root", "muzzle": "cannon"}
        self.stash = None       # the spare's design frame out of a reload (Unit.stash_spare)
        self.part_bone = {"cannon": "cannon", "barrel": "barrel", "crank": "crank", "magazine": "ammo",
                          "magazine2": "ammo2"}

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
            bone = self.bone_name(self.part_bone[key])
            parts.append({"name": f"{name}_{key}", "bone": bone,
                          "positions": apply(self.S, pos), "normals": nrm @ self.R, "tangents": tan @ self.R,
                          "uvs": uvs, "triangles": tris, "materials": mats})
        return gr2_parts.rigid_model(self.src.data, bones[0][0], bones, parts, source_name=name)

    @staticmethod
    def bone_name(b):
        return {"yaw": "bone_yaw", "cannon": "bone_cannon", "barrel": "bone_barrel", "crank": "bone_crank",
                "ammo": "bone_ammo", "ammo2": "bone_ammo2", "muzzle": "bone_launchpoint"}[b]

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
        self.hang_local = np.linalg.inv(rigid(P0[self.mount])) @ rigid(P0[self.hang])   # the hang bone on the chest
        self.hang_bind = self.bind @ self.hang_local      # the hang bone at the bind pose (the chest's scale)

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

    def heading(self, pose):
        """The body's heading (degrees about the vertical, 0 toward +z): pelvis to chest."""
        d = pose[self.mount][:3, 3] - pose["hs bone pelvis"][:3, 3]
        return math.degrees(math.atan2(d[0], d[2]))

    def grounded(self, anim, times):
        """Poses of a borrowed clip at `times`, each turned back to the camel's own heading over the
        same spot (the sheep the lying-down clips were made for turns, slides and rolls onto its
        flank as it lies down), upright, and lifted or lowered so the body's lowest point is on the ground (it sits at another
        height)."""
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
            out.append({k: tr((0.0, dy, 0.0)) @ v for k, v in p.items()})
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
    HEAD_YAW, HEAD_UP, HEAD_DOWN = 65.0, 25.0, 40.0

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
        return self.body.place_hand(P, side, palm, finger, normal, pole)

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
            palm = g.handle_at(fr) + np.array([side * 0.07 * g.s, 0.02, -0.02])
            return palm, (0.0, -0.55, 1.0), (0.0, -1.0, -0.35)
        if what == "crank_l":                # the crank's handle in the left hand (the gun turned far right)
            palm = g.handle_at(fr) + np.array([side * 0.07 * g.s, 0.02, 0.02])
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
        raise KeyError(what)

    def poles(self):
        if self.style == "A":              # elbows out to the sides: a firm grip, not tucked in
            return {"r": np.array([1.0, -0.6, -0.4]), "l": np.array([-1.0, -0.6, -0.4])}
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
        P0 = cam.pose(cam.anim(CLIPS["A"][0]["camel"]), 0.0)
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
        centre = point(inv0, np.array([pel[0], 0.5 * (hi + lo), pel[2] + 0.10]))
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

    def base_body(self, P):
        """The gunner's body a reload starts from, before his hands are placed: seated on the camel
        (A, and B mounted) or standing at the gun (B on foot)."""
        if self.style == "A":
            return self.rider.seated(self.rider.idle, 0.0, rigid(P[self.camel.rider_bone]))
        return self.stand_pose()

    def body_axes(self, R):
        """His (right, up, forward) in the world, level: from his hips."""
        right = R["bip01 r thigh"][:3, 3] - R["bip01 l thigh"][:3, 3]
        right[1] = 0.0
        right = unit(right)
        return right, Y.copy(), unit(np.cross(right, Y))

    def pocket(self, P):
        """The full magazine in the pocket at the gunner's left hip, at the camel pose P: (design
        frame, his (right, up, forward) in the world, the pocket's top in the world, the way it is
        drawn out (world, along its length toward its top))."""
        g = self.gun
        C = self.C(P)
        R = self.base_body(P)
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
        seated = tr(seat)
        lifted = tr(lift)
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
        rest = self.target("breech" if self.style == "A" else "casing", g.frames({}))

        def mix(a, b, w):
            w = smooth(min(1.0, max(0.0, w)))
            return (np.asarray(a[0]) + w * (np.asarray(b[0]) - np.asarray(a[0])),
                    unit((1 - w) * np.asarray(a[1]) + w * np.asarray(b[1])),
                    unit((1 - w) * np.asarray(a[2]) + w * np.asarray(b[2])))

        def lerp_frame(A, B, w):
            w = smooth(min(1.0, max(0.0, w)))
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
        # the toss: released at U_REL from the hand, a throw to his left and up, in the world
        U_REL = 0.34
        i_rel = int(np.argmin(np.abs(np.asarray(times) / length - U_REL)))
        Crel = self.C(poses[i_rel])
        # his left and his forward in design space (A: the camel's left and forward)
        b_right, _b_up, b_fwd = self.body_axes(self.base_body(poses[i_rel]))
        inv_rel = np.linalg.inv(Crel)[:3, :3]
        left_d, fwd_d = unit(inv_rel @ -b_right), unit(inv_rel @ b_fwd)
        tip = -35.0 * float(np.cross(fwd_d, left_d) @ Y)        # the top tipped out to his left
        throw = tr(lift + 0.17 * left_d + np.array([0.0, -0.10, 0.0]) + 0.04 * fwd_d) @ rot4(axis_matrix(fwd_d, tip))
        p0 = point(Crel, throw[:3, 3])
        v0 = Crel[:3, :3] @ (1.3 * left_d + 0.8 * Y + 0.2 * fwd_d)
        g_acc = 9.8
        ground = 0.06
        # landing time: p0.y + v0.y t - g t^2 / 2 = ground
        a, b_, c = -0.5 * g_acc, v0[1], p0[1] - ground
        t_land = (-b_ - math.sqrt(b_ * b_ - 4 * a * c)) / (2 * a)
        flight = (times[i_rel], p0, v0, g_acc, t_land, Crel[:3, :3] @ throw[:3, :3])
        old, new, hand, turn, look = [], [], [], [], []
        toward = None
        for t, P in zip(times, poses):
            u = t / length
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
                    drawn = invC @ tr(self.POCKET_DRAW * along) @ best[1] @ Wp
            toward = top_w
            # the new magazine: in the camel's body, in the pocket, drawn, carried over, seated
            if u < 0.01 or u >= 0.95:
                N = stash
            elif u < 0.52:
                N = inpocket
            elif u < 0.62:
                N = lerp_frame(inpocket, drawn, seg(u, 0.52, 0.62))
            elif u < 0.76:
                N = lerp_frame(drawn, lifted, seg(u, 0.62, 0.76))
            elif u < 0.82:
                N = lerp_frame(lifted, seated, seg(u, 0.76, 0.82))
            else:
                N = seated
            # the old one
            if u < 0.10:
                O = seated
            elif u < 0.22:
                O = lerp_frame(seated, lifted, seg(u, 0.10, 0.22))
            elif u < U_REL:
                O = lerp_frame(lifted, throw, seg(u, 0.22, U_REL))
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
            if u < 0.10:
                H = mix(rest, grip(seated), seg(u, 0.0, 0.10))
            elif u < U_REL:
                H = grip(O)
            elif u < 0.48:
                H = mix(grip(throw), top_grip(inpocket), seg(u, U_REL, 0.48))
            elif u < 0.62:
                H = top_grip(N)
            elif u < 0.74:
                H = mix(top_grip(N), grip(N), seg(u, 0.62, 0.74))
            elif u < 0.82:
                H = grip(N)
            elif u < 0.86:                                        # pressed home
                p, f, n = grip(seated)
                H = (p + np.array([0.0, -0.015 * math.sin(math.pi * seg(u, 0.82, 0.86)), 0.0]), f, n)
            else:
                H = mix(grip(seated), rest, seg(u, 0.86, 1.0))
            # the chest turned a little toward the pocket while he reaches down to it
            w = 0.0 if u < 0.36 or u > 0.66 else math.sin(math.pi * seg(u, 0.36, 0.66))
            old.append(O)
            new.append(N)
            hand.append(H)
            turn.append(w)
            look.append(point(C, H[0]))
        look = self.calm_gaze(poses, times, length, look)
        # the instant moves, out of sight: the new one from the camel's body to the pocket (u 0.01)
        # and back (0.95, seated inside the old one), the old one back in the gun (0.95, inside the
        # new one): a key 1 ms before the first frame at or after each, holding the frame before
        # it (write())
        extra = {"ammo2": (0.01, 0.95), "ammo": (0.95,)}
        return {"old": old, "new": new, "hand": hand, "turn": turn, "look": look, "extra": extra,
                "toward": toward, "times": np.asarray(times)}

    # how his head may turn from his body's forward while he watches his hands in a reload (degrees),
    # and how smooth the turns are (seconds, the gaze's Gaussian smoothing)
    GAZE_YAW, GAZE_UP, GAZE_DOWN, GAZE_SMOOTH = 60.0, 15.0, 35.0, 0.22

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
            yd, pd, _h = angles(self.downrange(C, self.gun.frames({})))
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
        for _k in range(tries):
            Q = base
            for s, (palm, fin, nor) in goals.items():
                Q = self.rider.hand(Q, s, palm, fin, nor, self.world_dir(C, poles[s]))
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
            stock_attach = [rigid(P[cam.rider_bone]) for P in poses]
        if clip.get("do") == "foot_death" or clip.get("roll"):
            poses = [cam.pin_hang(P, poses[0]) for P in poses]
            scales = cam.hang_scale(poses[0], scales)
            b.camel_bytes = cam.track_bytes(cname, times, poses, anim, scales)
        elif "camel" not in clip or clip.get("do") == "fall":   # the rider's bone kept on the chest
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
                state["magazine2"] = tr(g.at["ammo"])
            if do == "fire":
                state = self.fire_state(t, length)
                for s in self.shots(length):
                    if 0.0 <= t - s < 0.045:
                        b.flash.append(t)
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
            b.camel.append(P)
            b.gun.append(fr)
            b.rider.append(R)
        self._plan_at = None
        b.length = length
        return b

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
        stand = self.stand_pose()
        if do == "fall":                     # the rider's own death clips play (anim file)
            return rider.seated(rider.idle, 0.0, attach)
        if do in ("stand", "fire", "reload"):
            yaw = self.yaw_of(fr)
            if getattr(self, "_stand_at", None) is not None:
                stand = self._stand_at                 # placed on his feet by a Traverse (preview)
            elif abs(yaw) > 0.5:
                stand = self.step_around(stand, C, fr, yaw)
            R = self.at_gun(stand, C, fr, do, u, b, trunk=(0.1 if do == "reload" else 0.35, 22.0)
                            if getattr(self, "_stand_at", None) is not None else None)
            plan_at = getattr(self, "_plan_at", None) if do == "reload" else None
            if plan_at is not None:
                return rider.look(R, plan_at[0]["look"][plan_at[1]])
            return rider.look(R, self.gaze(do, clip, R, C, fr, attach))
        if do == "foot_death":
            anim = rider.anim(FOOT_DEATH)
            return rider.standing(self.foot, anim, min(t, anim.duration), 90.0, self.stand_info["at"])
        # dismount / mount: seated while the camel moves, the climb (keys) while it is held down
        t0, t1 = getattr(b, "window", (0.0, length))
        if t < t0 - 1e-9 or t > t1 + 1e-9:
            seat = rider.seated(rider.idle, 0.0, attach)
            seat = self.hands(seat, C, fr, {"l": self.reins(seat, attach, "l"), "r": self.reins(seat, attach, "r")}, b)
            return rider.look(seat, self.gaze(None, {}, seat, C, fr, attach))
        k = (t - t0) / max(t1 - t0, 1e-9)
        return self.climb(P, C, fr, attach, k if do == "dismount" else 1.0 - k)

    def at_gun(self, stand, C, fr, do, u, b, trunk=None):
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
            left = plan["hand"][i]
        else:
            left = self.reload_hand(u, fr) if do == "reload" else self.b_left_grip(fr)
        return self.hands(R, C, fr, {"r": "crank", "l": left}, b)

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
        on_saddle = {s: ("world", seat_at + 0.16 * left + 0.02 * up + (0.16 if s == "l" else -0.16) * fwd,
                         right, -up) for s in ("l", "r")}
        k3 = self.hands(k3, C, fr, on_saddle)
        # 4. standing on the ground beside the saddle, the hands still on it
        k4 = translate(S, rig, root, np.array([seat_at[0] - 0.62 - cur[0], 0.0, seat_at[2] - 0.05 - cur[2]]))
        k4 = self.hands(k4, C, fr, {s: ("world", seat_at + 0.24 * left - 0.06 * up +
                                        (0.16 if s == "l" else -0.16) * fwd, right, -up) for s in ("l", "r")})
        k4 = rider.look(k4, seat_at)
        k3 = rider.look(k3, seat_at)
        # 5. a step forward along the flank (an infantry walk's mid-stride, facing forward)
        stand = self.stand_pose()
        a, c = k4[root][:3, 3], stand[root][:3, 3]
        walk = rider.anim(LIB + "range\\march_rifleman")
        mid = 0.5 * (a + c)
        k5 = rider.standing(self.foot, walk, 0.3 * walk.duration, 45.0, np.zeros(3))
        k5 = translate(k5, rig, root, np.array([mid[0] - k5[root][0, 3], 0.0, mid[2] - k5[root][2, 3]]))
        k5 = rider.look(k5, k5["bip01 head"][:3, 3] + 5.0 * unit(fwd + right))
        # 6. at the gun
        k6 = self.at_gun(stand, C, fr, "stand", 0.0, None)
        k6 = rider.look(k6, self.downrange(C, fr))
        k0 = rider.look(k0, k0["bip01 head"][:3, 3] + 12.0 * fwd)
        k1 = rider.look(k1, seat_at + 0.6 * left - up * 0.6 + 0.4 * fwd)
        k2 = rider.look(k2, seat_at + 1.0 * left - up * 1.2)
        keys = [(0.0, k0), (0.14, k1), (0.30, k2), (0.48, k3), (0.64, k4), (0.82, k5), (1.0, k6)]
        self._climb = (P, keys)
        return keys

    def climb(self, P, C, fr, attach, share):
        """The rider at `share` (0 seated, 1 at the gun) of getting off the couched camel."""
        from aoe3game.gr2_pose import blend
        keys = self.climb_keys(P, C, fr)
        share = min(max(share, 0.0), 1.0)
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
        self._cache = {}

    # a station: (x, z) of his root on the ground and his heading (degrees about +y, 90: facing +x)
    def M(self, s, h):
        return tr((s[0], 0.0, s[1])) @ rot4(axis_matrix(Y, h - self.h0)) @ tr((-self.s0[0], 0.0, -self.s0[1]))

    def grips(self, fr):
        u = self.u
        left = u.b_left_grip(fr)
        left = u.target(left, fr) if isinstance(left, str) else left
        return 0.5 * (point(self.C, u.target("crank", fr)[0]) + point(self.C, left[0]))

    def _reach(self, s, h, fr):
        sh = point(self.M(s, h), self.sh0)
        d = self.grips(fr) - sh
        return math.hypot(d[0], d[2])

    def hand_goals(self, fr):
        """(the crank's handle, the left hand's grip) in the world."""
        u = self.u
        left = u.b_left_grip(fr)
        left = u.target(left, fr) if isinstance(left, str) else left
        return point(self.C, u.target("crank", fr)[0]), point(self.C, left[0])

    def _search(self, yaw, prev):
        u = self.u
        fr = u.gun.frames({"yaw": yaw})
        if not hasattr(self, "_grid"):
            xs = np.arange(-1.3, 0.5, 0.03)
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
        S, body_clear = self._grid
        n = len(S)
        hr, hl = self.hand_goals(fr)
        g = 0.5 * (hr + hl)
        # headings: facing the grips' middle (as at rest), then turned -30..30 degrees from it
        base = np.degrees(np.arctan2(g[0] - (S[:, 0]), g[2] - (S[:, 1]))) + self.hoff
        best = (np.inf, None)
        p0 = point(self.C, fr["cannon"][:3, 3])
        p1 = point(self.C, fr["muzzle"][:3, 3])
        p1 = p1 + 1.5 * (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-6)
        seg = np.array([p1[0] - p0[0], p1[2] - p0[2]])
        L2 = max(seg @ seg, 1e-9)
        camel = 400.0 * np.maximum(0.0, self.body_r - body_clear)
        for dh in np.arange(-30.0, 30.1, 6.0):
            h = base + dh
            a = np.radians(h - self.h0)
            cos, sin = np.cos(a), np.sin(a)

            def place(p):            # a rest-pose point carried to each candidate station (x, y, z)
                x0, z0 = p[0] - self.s0[0], p[2] - self.s0[1]
                return S[:, 0] + x0 * cos + z0 * sin, np.full(n, p[1]), S[:, 1] - x0 * sin + z0 * cos
            cost = camel.copy()
            reach = np.zeros(n)
            for s, goal in (("r", hr), ("l", hl)):
                x, y, z = place(self.stand[f"bip01 {s} upperarm"][:3, 3])
                d = np.sqrt((goal[0] - x) ** 2 + (goal[1] - y) ** 2 + (goal[2] - z) ** 2)
                # as far from the grip as at rest; farther (a straighter arm) costs much more
                cost += 40.0 * (d - self._arm0[s]) ** 2 + 800.0 * np.maximum(0.0, d - self._arm0[s]) ** 2
                reach = np.maximum(reach, d - self._arm0[s])
            for s in ("l", "r"):
                fx, _fy, fz = place(self.feet0[s][:3, 3])
                cost += 400.0 * np.maximum(0.0, self.foot_r - self._mind(np.c_[fx, fz], self.low_pts))
            # his head out of the barrels' line (pivot to well past the muzzle, near his head's height)
            hx, _hy, hz = place(self.stand["bip01 head"][:3, 3])
            w = np.clip(((hx - p0[0]) * seg[0] + (hz - p0[2]) * seg[1]) / L2, 0.0, 1.0)
            dl = np.hypot(hx - (p0[0] + w * seg[0]), hz - (p0[2] + w * seg[1]))
            cost += 200.0 * np.maximum(0.0, self.HEAD_CLEAR - dl)
            # stay near where he was (few steps), a little near his rest place
            dturn = (h - prev[1] + 180.0) % 360.0 - 180.0
            cost += 3.0 * ((S - prev[0]) ** 2).sum(1) + 0.0004 * dturn ** 2
            # stations change little from one yaw step to the next (short steps, feet never crossed)
            cost += 1e4 * ((np.sqrt(((S - prev[0]) ** 2).sum(1)) > 0.10) | (np.abs(dturn) > 9.0))
            cost += 0.3 * ((S - self.s0) ** 2).sum(1)
            i = int(np.argmin(cost))
            if cost[i] < best[0]:
                best = (float(cost[i]), ((S[i].copy(), float(h[i])), {"reach": float(reach[i]), "line": float(dl[i])}))
        c, (st, info) = best
        return st, c, info

    def table(self, step=5):
        """{yaw: (station, cost, info)} from 0 out to +90 and to -90, each from its neighbour."""
        if not self._cache:
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
    # both feet set at the stations every STAIR_STEP degrees; going out from 0, the leading foot
    # steps while the yaw crosses STAIR_LEAD of the next 30 degrees, the other while it crosses
    # STAIR_TRAIL; between those bands both feet stand still. A game keeps the shown yaw out of the
    # bands when the gun comes to rest (the aim file lists them), so no foot is left in the air.
    STAIR_STEP = 30.0
    STAIR_LEAD = (6.0, 14.0)
    STAIR_TRAIL = (16.0, 24.0)

    def stair_bands(self):
        """The yaw bands in which a foot is stepping, (from, to) degrees, for the aim file."""
        out = []
        for k in range(int(round(90.0 / self.STAIR_STEP))):
            for lo, hi in (self.STAIR_LEAD, self.STAIR_TRAIL):
                a, b = k * self.STAIR_STEP + lo, k * self.STAIR_STEP + hi
                out += [(a, b), (-b, -a)]
        return sorted(out)

    def lead_foot(self, sign):
        """The foot that leads when the gun turns toward `sign` (+1 right): the one farther along
        his way from the station at 0 to the next."""
        if not hasattr(self, "_lead"):
            self._lead = {}
        if sign not in self._lead:
            M0, M1 = self.M(*self.station(0.0)), self.M(*self.station(sign * self.STAIR_STEP))
            way = (M1 @ np.r_[self.s0[0], 0.0, self.s0[1], 1.0])[:3] - (M0 @ np.r_[self.s0[0], 0.0, self.s0[1], 1.0])[:3]
            score = {s: float(point(M0, self.feet0[s][:3, 3]) @ way) for s in ("l", "r")}
            self._lead[sign] = max(score, key=score.get)
        return self._lead[sign]

    def stair(self, yaw):
        """His body on his feet at the gun's yaw (Traverse.STAIR_*): each foot planted at its station
        or, inside its band, lifted and carried to the next one; his body between his feet, the
        legs solved to them."""
        from aoe3game.gr2_pose import translate, two_bone_ik
        yaw = max(-90.0, min(90.0, float(yaw)))
        sign = 1.0 if yaw >= 0 else -1.0
        a = abs(yaw)
        k = min(int(a // self.STAIR_STEP), int(round(90.0 / self.STAIR_STEP)) - 1)
        f = a - k * self.STAIR_STEP
        y0, y1 = sign * k * self.STAIR_STEP, sign * (k + 1) * self.STAIR_STEP
        M0, M1 = self.M(*self.station(y0)), self.M(*self.station(y1))
        lead = self.lead_foot(sign)
        cur, lift = {}, 0.0
        for s in ("l", "r"):
            lo, hi = self.STAIR_LEAD if s == lead else self.STAIR_TRAIL
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
B_TURN_RATE = 60.0


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
    angles = (-90.0, -45.0, 0.0, 45.0, 90.0)
    w, h = 300, 280
    rows = [title(w * len(angles), f"{label.upper()}: B ON FOOT, THE GUN AT -90 -45 0 45 90 (FIRING)", back=(70, 40, 20))]
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
    for y in range(0, 61, 2):
        S = trav.stair(float(y))
        feet[y] = {s: S[f"bip01 {s} foot"][:3, 3].copy() for s in ("l", "r")}
    slide = 0.0
    for y in range(0, 60, 2):
        for s in ("l", "r"):
            lead = trav.lead_foot(1.0) == s
            lo, hi = trav.STAIR_LEAD if lead else trav.STAIR_TRAIL
            f0, f1 = (y % 30), (y % 30) + 2
            if f1 <= lo or f0 >= hi:                          # the foot is planted over this step
                slide = max(slide, float(np.linalg.norm(feet[y + 2][s] - feet[y][s])))
    lines.append(f"stepping: a planted foot moves at most {slide * 1000:.1f} mm between 2-degree samples "
                 f"(bands {bands[len(bands) // 2:]})")
    tiles = []
    for y in range(0, 61, 4):
        items, marks, _r = aim.items(fig, 0.0, float(y), trav.stair(float(y)))
        img = draw(items, 240, 220, -100.0, 6.0, 2.2, (-0.4, 0.55, 0.4))
        tiles.append(caption(img, f"GUN {y:+d}"))
    tiles += [np.zeros_like(tiles[0])] * ((-len(tiles)) % 8)
    sheet = grid(tiles, 8)
    Image.fromarray(np.concatenate([title(sheet.shape[1], f"{label.upper()}: HIS FEET AS THE GUN TURNS 0 TO 60, "
                                          "EVERY 4 DEGREES: ONE FOOT STEPS AT A TIME, THE OTHER STAYS PLANTED",
                                          back=(70, 40, 20)), sheet], 0)).save(stem + "-B-steps.png")
    # 3. the gun turned as a game turns it, he steps round (two views)
    targets = [(0.0, 0.8), (45.0, 1.4), (90.0, 1.4), (45.0, 1.2), (0.0, 1.2), (-45.0, 1.4), (-90.0, 1.4),
               (-45.0, 1.2), (0.0, 1.6)]
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
AIM_TABLE_YAWS_FOOT = tuple(float(y) for y in range(-90, 91, 2))
AIM_TABLE_CLIPS_FOOT = ("deployed", "fire", "reload")


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
    foot is in the air: a game keeps the gun from coming to rest inside one."""
    import struct as st
    cam, rider, g = unit.camel, unit.rider, unit.gun
    names = rider.rig.names
    foot = unit.style == "B" and traverse is not None
    yaws_t = AIM_TABLE_YAWS_FOOT if foot else AIM_TABLE_YAWS
    clips_t = AIM_TABLE_CLIPS_FOOT if foot else AIM_TABLE_CLIPS
    stairs = {y: traverse.stair(y) for y in yaws_t} if foot else {}
    tables = []
    length_of = {}
    for b in built.values():
        clip = b.clip
        if clip["name"] not in clips_t:
            continue
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
                unit._stand_at = stairs.get(yaw)
                try:
                    R = unit.rider_pose(clip, do, t, length, u, P, unit.C(P), fr, base, attach, Built(clip, [t]))
                finally:
                    unit._plan_at = None
                    unit._stand_at = None
                row.append(rider.to_local(R, attach))
            frames.append(row)
        tables.append((unit.clip_name("rider", b), frames, len(idx)))
        length_of[unit.clip_name("rider", b)] = float(length)
    # the bones that move with the yaw
    zero = yaws_t.index(0.0)
    moving = set()
    for _n, frames, _c in tables:
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
    # the pivot and the muzzle where the unit fires: at the first frame of its fire clip (B: the camel
    # lying down, its post much lower than at the bind pose), in the camel's model space
    fire = built.get("fire")
    Cf = unit.C(fire.camel[0]) if fire is not None else np.eye(4)
    pivot, muzzle = (point(Cf, g.post), point(Cf, g.at["muzzle"])) if fire is not None else (g.post, g.at["muzzle"])
    out = [b"UHCA", st.pack("<I", 1), name32(GunDesign.bone_name("yaw")), name32("bone_turret"),
           st.pack("<3f", *[float(v) for v in pivot]), st.pack("<3f", *[float(v) for v in muzzle]),
           st.pack("<I", len(yaws_t)),
           st.pack(f"<{len(yaws_t)}f", *yaws_t), st.pack("<I", len(bones))]
    out += [name32(names[k]) for k in bones]
    out.append(st.pack("<I", len(tables)))
    for name, frames, count in tables:
        out += [name32(name, 64), st.pack("<fI", length_of[name], count)]
        for row in frames:
            for loc in row:
                for k in bones:
                    p, q = loc[k]
                    out.append(st.pack("<7f", *[float(v) for v in p], *[float(v) for v in q]))
    if foot:
        bands = traverse.stair_bands()
        out += [b"BAND", st.pack("<I", len(bands))] + [st.pack("<2f", a, b_) for a, b_ in bands]
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
    if cut.get("keep_post", True):
        for _c, sel, is_post in pieces:
            if is_post:
                keep[sel] = True
    out = gr2_parts.cut_triangles(data, spec["mesh"], keep)
    info = {"triangles": int(len(part["triangles"])), "cut": int((~keep).sum()),
            "pieces": [(int(len(sel)), bool(post)) for _c, sel, post in pieces]}
    return out, info, post_top(part, pieces)


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


def dead_model(camel_bytes, gun_bytes, hang_bind, bone):
    """The camel model with the gun's parts added as rigid meshes bound to the camel's `bone` (its
    chest), at rest: the model of the dead unit, which plays the stock camel deaths. Seen in game
    (2026-11-23): a gun attached to the rider's bone turned in the air during the corpse's last
    half second of fading out, whatever clips, tag files or held anims it was given (inferred: the
    game places attachments differently while a corpse fades); a gun inside the camel's own model
    falls and fades with it. The stock death clips give the chest no scale, so a gun vertex q
    (gun model space) goes to hang_bind @ q in the camel's bind space."""
    from aoe3game import gr2_edit
    from aoe3game.gr2_write import Flat, W, serialize
    cdoc = gr2.load(camel_bytes)
    croot = gr2_edit.copy_tree(cdoc)
    groot = gr2_edit.copy_tree(gr2.load(gun_bytes))
    R = hang_bind[:3, :3] / np.cbrt(abs(np.linalg.det(hang_bind[:3, :3])))
    camel_binding = croot.values["Models"][0].values["MeshBindings"][0]
    bind_world = None
    for bw in croot.values["Skeletons"][0].values["Bones"]:
        if bw.values.get("Name") == bone:
            iwt = np.array(bw.values["InverseWorldTransform"], np.float64).reshape(4, 4)
            bind_world = np.linalg.inv(iwt).T
    if bind_world is None:
        raise KeyError(bone)
    for gm in groot.values["Meshes"]:
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
        bb.values["BoneName"] = bone
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
    ap.add_argument("--round4-preview", help="a folder for B on foot with the turning gun: the angles, the stepping, "
                                             "the dismount and the remount (round 4)")
    args = ap.parse_args(argv)
    try:
        for p in (args.out, args.sheet, args.gifs, args.aim_sheet, args.aim_gifs, args.reload_preview,
                  args.round4_preview):
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
                model = unit.gun.model_bytes(unit.gun_name)
                files[unit.gun_name] = model
                files[f"{recipe['name']}_camel_dead_{unit.tag}"] = dead_model(
                    camel.cut, model, camel.hang_bind, recipe["camel"]["mount_bone"])
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
