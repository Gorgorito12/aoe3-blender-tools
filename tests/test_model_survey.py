# SPDX-License-Identifier: GPL-3.0-or-later
"""The model survey on Granny files written here (no game, no mod, no bridge): what is measured
of a model and of an animation, and that the profile names no file.

    venv\\Scripts\\python -I tests\\test_model_survey.py
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import model_survey as ms  # noqa: E402
from aoe3game import gr2, gr2_write  # noqa: E402
from test_game_formats import box  # noqa: E402

TEX = "C:\\x\\art\\mod\\objects\\crate\\crate.ddt"


def model(w=4.0, bones=()):
    P, N, UV, T = box(w=w)
    return gr2_write.static_model("Crate", P, N, UV, T, texture=TEX, bump=TEX[:-4] + "_b.ddt",
                                  bones=bones)


def animation():
    return gr2_write.sink_animation("Crate", [("bone_flag_civ", (0.0, 0.0, 2.0))], 2.0)


def put(folder, rel, data):
    path = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class Measure(unittest.TestCase):
    def test_a_static_model(self):
        m = ms.measure(model(bones=[("bone_smoke", (0.0, 0.0, 1.0))]))
        self.assertEqual(m["kind"], "model")
        self.assertEqual((m["tris"], m["meshes"]), (10, 1))
        self.assertFalse(m["skinned"])
        self.assertEqual(m["bones"], 3)                    # bone_main, the mesh's, the socket
        self.assertEqual(m["bone_depth"], 1)
        self.assertIn("bone_smoke", m["bone_names"])
        self.assertEqual(m["textures"], ["crate.ddt", "crate_b.ddt"])
        self.assertEqual(m["index_bits"], [16])
        self.assertGreater(m["texel"], 0)
        self.assertLessEqual(m["uv_max"], 1.0)
        self.assertEqual(m["animations"], [])

    def test_the_size_follows_the_model(self):
        small, large = ms.measure(model(w=2.0)), ms.measure(model(w=8.0))
        self.assertGreater(max(large["size"][:2]), max(small["size"][:2]))
        self.assertGreater(small["texel"], large["texel"])      # the same UVs over more surface

    def test_an_animation(self):
        a = ms.measure(animation())
        self.assertEqual(a["kind"], "animation")
        self.assertEqual(a["tris"], 0)
        an = a["animations"][0]
        self.assertAlmostEqual(an["duration"], 4.0, 3)
        self.assertEqual(round(1 / an["timestep"]), 60)
        self.assertGreaterEqual(an["tracks"], 2)
        self.assertEqual((an["flags"], an["loop_translation"], an["periodic"]), ([0], False, False))

    def test_the_depth_of_a_hierarchy(self):
        self.assertEqual(ms._depth([-1, 0, 1, 2, 0]), 3)
        self.assertEqual(ms._depth([]), 0)


class Cache(unittest.TestCase):
    def test_an_uncompressed_file_needs_no_bridge(self):
        data = model()
        self.assertIs(ms.raw_bytes(data, "x", None), data)

    def test_a_compressed_file_without_a_bridge_is_an_error_and_with_a_cached_copy_is_read(self):
        data, facts = model(), gr2.header_facts
        try:
            gr2.header_facts = lambda head: {"raw": False}
            with self.assertRaises(RuntimeError):
                ms.raw_bytes(data, "abc", None)
            with tempfile.TemporaryDirectory() as cache:
                os.makedirs(os.path.join(cache, "raw"))
                with open(os.path.join(cache, "raw", "abc.gr2"), "wb") as fh:
                    fh.write(b"cached")
                self.assertEqual(ms.raw_bytes(data, "abc", ("no.exe", cache, cache)), b"cached")
        finally:
            gr2.header_facts = facts


class Survey(unittest.TestCase):
    def test_files_are_found_measured_and_told_own_from_stock(self):
        with tempfile.TemporaryDirectory() as mod, tempfile.TemporaryDirectory() as game:
            put(game, "art/objects/crate/crate.gr2", model())
            put(mod, "art/objects/crate/crate.gr2", model())                  # untouched
            put(mod, "art/SomeMod/units/guard/guard.gr2", model(w=1.0))       # new
            put(mod, "art/SomeMod/units/guard/guard_idle.gr2", animation())
            put(mod, "art/units/broken.gr2", b"not a granny file at all")
            recs = {os.path.basename(r["path"]): r for r in ms.survey([mod], reference=[game])}
        self.assertEqual(recs["crate.gr2"]["origin"], "stock")
        self.assertEqual((recs["guard.gr2"]["origin"], recs["guard.gr2"]["category"]), ("own", "units"))
        self.assertEqual(recs["guard_idle.gr2"]["kind"], "animation")
        self.assertIn("error", recs["broken.gr2"])
        self.assertFalse(recs["guard.gr2"]["compressed"])


def rows(n, category="objects", origin="own"):
    out = []
    for i in range(n):
        r = {"path": f"art\\SecretMod\\{category}\\thing{i}\\thing{i}.gr2", "md5": f"{category}{i}",
             "origin": origin, "category": category, "bytes": 100}
        r.update(ms.measure(model(w=2.0 + i)))
        out.append(r)
    return out


class Profile(unittest.TestCase):
    def test_it_names_no_file_no_folder_and_no_bone(self):
        prof = ms.profile(rows(10))
        text = json.dumps(prof)
        for leak in ("SecretMod", "thing", ".gr2", "crate", "bone_main", "Crate", "\\\\"):
            self.assertNotIn(leak, text, leak)
        g = next(g for g in prof["groups"] if g["category"] == "objects")
        self.assertEqual((g["count"], g["models"]), (10, 10))
        self.assertEqual(g["tris"], [10.0, 10.0, 10.0])
        self.assertEqual(g["skinned"], 0.0)

    def test_small_groups_are_left_out_and_copies_count_once(self):
        a = rows(10)
        prof = ms.profile(a + [dict(r) for r in a] + rows(3, category="nuggets"))
        self.assertEqual(prof["distinct"], 13)
        self.assertNotIn("nuggets", {g["category"] for g in prof["groups"]})

    def test_the_pixels_per_unit_come_from_the_textures_measured(self):
        textures = [{"path": "art\\x\\crate.ddt", "w": 512, "h": 512}]
        g = next(g for g in ms.profile(rows(10), textures)["groups"] if g["category"] == "objects")
        self.assertIn("pixels_per_unit", g)
        self.assertGreater(g["pixels_per_unit"][1], 0)

    def test_animations_are_summarised(self):
        anims = []
        for i in range(9):
            r = {"path": f"a{i}", "md5": f"a{i}", "origin": "own", "category": "animation_library"}
            r.update(ms.measure(animation()))
            anims.append(r)
        g = next(g for g in ms.profile(anims)["groups"] if g["category"] == "animation_library")
        self.assertEqual(g["animations"]["count"], 9)
        self.assertEqual(g["animations"]["periodic"], 0.0)
        self.assertEqual(g["animations"]["timestep"][0], [60, 9])


if __name__ == "__main__":
    unittest.main(verbosity=2)
