# SPDX-License-Identifier: GPL-3.0-or-later
"""The pieces of tools/make_zamburak.py that need no game: the barrel's press, the swivel's
solids and the colour patches, on synthetic data.

    venv\\Scripts\\python -I tests\\test_make_zamburak.py
"""
import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import make_zamburak as mz  # noqa: E402
from aoe3game import gr2_parts  # noqa: E402


def barrel_stations():
    """Axial positions of a turned barrel like the field gun's: a breech ring (0 to 0.03), a plain
    chase, a muzzle swell (2.55 to 2.77)."""
    return np.array([0.0, 0.01, 0.02, 0.03, 2.55, 2.56, 2.68, 2.72, 2.77])


class Press(unittest.TestCase):
    def test_the_whole_is_the_share_and_the_swell_keeps_its_length(self):
        z = barrel_stations()
        out, swell, chase = mz.press(z, 2.77, 2.0 / 3.0)
        self.assertAlmostEqual(float(out.max()), 2.77 * 2.0 / 3.0, places=6)
        self.assertAlmostEqual(swell, 2.55)
        # the swell's own length and spacing are kept
        np.testing.assert_allclose(np.diff(out[4:]), np.diff(z[4:]), atol=1e-9)
        # the breech ring is pressed with the chase but stays at the breech
        self.assertEqual(float(out[0]), 0.0)
        self.assertTrue((np.diff(out) >= 0).all())

    def test_share_one_changes_nothing(self):
        z = barrel_stations()
        out, _s, _c = mz.press(z, 2.77, 1.0)
        np.testing.assert_allclose(out, z, atol=1e-9)

    def test_a_barrel_without_a_swell_is_pressed_whole(self):
        z = np.array([0.0, 0.5, 1.0, 1.5, 2.0])          # evenly spaced: the longest gap is the first
        out, _s, _c = mz.press(z, 2.0, 0.5)
        self.assertLessEqual(float(out.max()), 1.0 + 1e-3)


class Turns(unittest.TestCase):
    def test_vslerp_stays_unit_and_never_passes_through_nothing(self):
        a, b = np.array([1.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0])       # opposite: about the vertical
        for w in np.linspace(0.0, 1.0, 11):
            v = mz.vslerp(a, b, w)
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0)
            self.assertAlmostEqual(math.degrees(math.acos(max(-1.0, min(1.0, float(v @ a))))), 180.0 * w, places=5)
        np.testing.assert_allclose(mz.vslerp(a, np.array([0.0, 0.0, 1.0]), 0.5), np.array([1.0, 0.0, 1.0]) / math.sqrt(2),
                                   atol=1e-9)

    def test_span_and_ease(self):
        self.assertEqual(mz.span(0.0, 1.0, 2.0), 0.0)
        self.assertEqual(mz.span(3.0, 1.0, 2.0), 1.0)
        self.assertAlmostEqual(mz.span(1.5, 1.0, 2.0), 0.5)


class Solids(unittest.TestCase):
    def test_cylinder_and_box_are_closed_and_wound_outward(self):
        for part in (mz.cylinder((0, 0, 0), (0, 1, 0), 0.2), mz.cylinder((0, 0, 0), (1, 1, 0.5), 0.05, sides=6),
                     mz.box((1, 2, 3), (0.1, 0.2, 0.3))):
            self.assertEqual(gr2_parts.face_normals_ok(part["positions"], part["normals"], part["triangles"]), 1.0)
            # every edge is shared by two triangles once the positions are welded
            key = {}
            vid = [key.setdefault(tuple(np.round(p, 6)), len(key)) for p in part["positions"]]
            edges = {}
            for t in part["triangles"]:
                for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                    e = tuple(sorted((vid[a], vid[b])))
                    edges[e] = edges.get(e, 0) + 1
            self.assertTrue(all(n == 2 for n in edges.values()), "an open edge")
            self.assertTrue(np.allclose(np.linalg.norm(part["tangents"], axis=1), 1.0))
            self.assertTrue(np.allclose(np.einsum("ij,ij->i", part["tangents"], part["normals"]), 0.0, atol=1e-9))

    def test_cylinder_radius_and_ends(self):
        part = mz.cylinder((0, 0, 0), (0, 2, 0), 0.3, sides=8)
        p = part["positions"]
        self.assertAlmostEqual(float(np.hypot(p[:, 0], p[:, 2]).max()), 0.3)
        self.assertAlmostEqual(float(p[:, 1].min()), 0.0)
        self.assertAlmostEqual(float(p[:, 1].max()), 2.0)

    def test_merge_offsets_the_triangles(self):
        a, b = mz.box((0, 0, 0), (1, 1, 1)), mz.box((5, 0, 0), (1, 1, 1))
        m = mz.merge([a, b])
        self.assertEqual(len(m["positions"]), 48)
        self.assertEqual(int(m["triangles"].max()), 47)
        self.assertTrue((m["positions"][m["triangles"][12:]][:, :, 0] > 3).all())


class Patches(unittest.TestCase):
    def test_the_largest_triangle_of_the_wanted_colour(self):
        img = np.zeros((64, 64, 4), np.uint8)
        img[..., 3] = 255
        img[:32, :, :3] = (40, 40, 42)        # dark iron in the top half (rows 0-31)
        img[32:, :, :3] = (150, 100, 40)      # wood below
        uv = np.array([[0.1, 0.1], [0.9, 0.1], [0.1, 0.4], [0.1, 0.6], [0.9, 0.6], [0.1, 0.95], [0.2, 0.2],
                       [0.25, 0.2], [0.2, 0.25]])
        part = {"uvs": uv, "triangles": np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])}
        uv_iron, i = mz.texel_patch(img, part, mz.is_iron)
        self.assertEqual(i, 0)                 # the big iron triangle, not the small one
        uv_wood, j = mz.texel_patch(img, part, mz.is_wood)
        self.assertEqual(j, 1)
        self.assertTrue(mz.is_bronze(np.array([200, 150, 60, 255.0])))
        self.assertFalse(mz.is_bronze(np.array([40, 40, 42, 255.0])))
        img[..., 3] = 0                        # transparent (alpha test, or player colour): never taken
        self.assertIsNone(mz.texel_patch(img, part, mz.is_iron))


class Pitch(unittest.TestCase):
    def test_positive_pitch_lowers_the_muzzle_and_yaw_turns_right(self):
        class Src:
            radius_at_trunnion = 0.2
            radius = 0.23
            breech = np.array([0.0, 0.0, -0.3])
            muzzle = np.array([0.0, 0.0, 1.0])
            fuse = np.array([0.0, 0.24, -0.2])
            barrel = {}
            linstock = {}
            linstock_length = 0.85
            cloth = None
            ember = None
            patches = {k: ((0.5, 0.5), None) for k in ("bronze", "iron", "wood")}
        bind = np.eye(4)
        bind[:3, :3] *= 0.9
        bind[1, 3] = 2.0
        d = mz.CannonDesign(Src(), bind, 2.0, mz.DEFAULT_RECIPE)
        level = d.frames({"pitch": 0.0})["muzzle"][:3, 3]
        down = d.frames({"pitch": 30.0})["muzzle"][:3, 3]
        right = d.frames({"yaw": 30.0})["muzzle"][:3, 3]
        self.assertLess(down[1], level[1])
        self.assertAlmostEqual(math.degrees(math.atan2(level[1] - down[1], down[2] - d.trunnion[2])) +
                               math.degrees(math.asin(0)), 30.0, places=4)
        self.assertGreater(right[0], 0.0)      # +x: the unit's right
        # negative pitch puts it up as far (the shot's kick: it used to dip the muzzle as well)
        up = d.frames({"pitch": -30.0})["muzzle"][:3, 3]
        self.assertGreater(up[1], level[1])
        self.assertAlmostEqual(up[1] - level[1], level[1] - down[1], places=6)
        # the pivot and the post never move
        for st in ({"pitch": 40.0, "yaw": 60.0}, {}):
            f = d.frames(st)
            np.testing.assert_allclose(f["post"][:3, 3], d.saddle)
            np.testing.assert_allclose(f["yaw"][:3, 3], d.pivot)


class Shot(unittest.TestCase):
    """The z-fuse script's timing: the touch, the burning fuse, the shot and its jolt in the 2.0 s clip."""

    def test_the_fuse_burns_from_the_touch_to_the_shot(self):
        self.assertLess(mz.TOUCH, mz.TOUCH_END)
        self.assertLess(mz.TOUCH_END, mz.SHOT)
        self.assertAlmostEqual(mz.SHOT, mz.TOUCH + mz.FUSE)
        self.assertGreaterEqual(mz.FUSE, 0.5)          # the artist asked for a slower fuse (0.10 s before)
        self.assertAlmostEqual(round(mz.SHOT / mz.FIRE, 2), 0.70)

    def test_the_jolt_rises_and_settles_inside_the_clip(self):
        for f in (mz.recoil, lambda t: mz.recoil(t, 0.05), mz.kick):
            self.assertEqual(f(0.0), 0.0)
            self.assertEqual(f(mz.SHOT), 0.0)
            self.assertAlmostEqual(f(mz.FIRE), 0.0, places=9)   # the last frame is the first (the reload follows)
        self.assertAlmostEqual(mz.recoil(mz.SHOT + 0.10), 1.0)
        self.assertAlmostEqual(mz.kick(mz.SHOT + 0.08), mz.KICK)
        self.assertLess(min(mz.kick(mz.SHOT + k / 100.0) for k in range(60)), 0.0)   # the rebound past rest
        self.assertLess(mz.recoil(mz.SHOT + 0.35), 0.0)


class _BuiltStub:
    """The least of a built clip anim_files reads: its file names."""

    def __init__(self, name):
        self.camel_name = self.gun_name = self.rider_name = name
        self.stock_rider = name

    @staticmethod
    def all():
        names = {c for _an, clips in mz.ANIMS for c in clips}
        return {c: _BuiltStub(c) for c in names}


class FuseParticles(unittest.TestCase):
    """fuse_particles changes only the named fields of the game's particle files."""

    STOCK = ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<particlefile>\n<emitter>\n"
             "<particlelife>0.950</particlelife>\n<initialdormancy>0.900</initialdormancy>\n"
             "<emissiontime>0.100</emissiontime>\n</emitter>\n<appearance>\n<framespersecond>15.000</framespersecond>\n"
             "</appearance>\n<scale>\n<loopingcycle>0</loopingcycle>\n<numstages>2</numstages>\n<scale>1.000</scale>\n"
             "</scale>\n<scalestages>\n<stage>\n<scale>0.200</scale>\n</stage>\n</scalestages>\n</particlefile>\n")

    def test_the_fields_change_and_nothing_else(self):
        import xmbedit
        raw = xmbedit.encode(*xmbedit.from_xml(self.STOCK.encode("utf-8")))
        out = mz.fuse_particles(lambda stored: raw, mz.FUSE_FX)
        self.assertEqual(sorted(out), ["fuse_smoke.particle", "fuse_sparks.particle"])
        sparks, smoke = out["fuse_sparks.particle"], out["fuse_smoke.particle"]
        self.assertIn(f"<initialdormancy>{mz.TOUCH:.3f}</initialdormancy>", sparks)
        self.assertIn(f"<particlelife>{mz.FUSE:.3f}</particlelife>", sparks)
        self.assertIn("<emissiontime>0.100</emissiontime>", sparks)
        self.assertIn("<scale>0.700</scale>", sparks)
        self.assertIn("<scale>0.200</scale>", sparks)              # a stage's scale is not the base's
        self.assertIn(f"<initialdormancy>{mz.TOUCH + 0.10:.3f}</initialdormancy>", smoke)
        self.assertIn(f"<emissiontime>{mz.FUSE - 0.10:.3f}</emissiontime>", smoke)
        self.assertIn("<particlelife>0.950</particlelife>", smoke)

    def test_the_muzzle_smoke_is_delayed_to_the_shot(self):
        # the game's six smallCannonMuzzle particles, each starting SHOT later than the game's own start
        import xmbedit
        raw = xmbedit.encode(*xmbedit.from_xml(self.STOCK.encode("utf-8")))
        out = mz.fuse_particles(lambda stored: raw, mz.MUZZLE_FX)
        self.assertEqual(len(out), 6)
        for text in out.values():
            self.assertIn(f"<initialdormancy>{0.9 + mz.SHOT:.3f}</initialdormancy>", text)
            self.assertIn("<emissiontime>0.100</emissiontime>", text)
        self.assertEqual(sorted(mz.fuse_particles(lambda stored: raw)),
                         sorted([f"{n}.particle" for n, _s, _f in mz.FUSE_FX + mz.MUZZLE_FX]))

    def test_the_muzzle_smoke_is_attached_on_the_gun_not_tagged(self):
        files = mz.anim_files({"folder": "f", "name": "z"}, _BuiltStub.all(), "")
        self.assertNotIn("particlename=\"smallcannonmuzzle\"", files["z.xml"])
        gun = files["z_gun.xml"]
        for n, _s, _f in mz.MUZZLE_FX:
            self.assertIn(f"<attach a=\"{n}\" frombone=\"bone_launchpoint\" tobone=\"bone_launchpoint\"", gun)

    def test_a_missing_field_is_refused(self):
        import xmbedit
        bare = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<particlefile>\n<emitter/>\n</particlefile>\n"
        raw = xmbedit.encode(*xmbedit.from_xml(bare.encode("utf-8")))
        with self.assertRaises(ValueError):
            mz.fuse_particles(lambda stored: raw)


if __name__ == "__main__":
    unittest.main()
