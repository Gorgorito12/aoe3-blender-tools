# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of aoe3game/gr2_merge.py and tools/merge_attachments.py on a synthetic building (numpy,
no Granny runtime).

    venv\\Scripts\\python -I tests/test_merge_attachments.py
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_merge, gr2_mesh, gr2_write  # noqa: E402
import merge_attachments as ma  # noqa: E402

QUAD = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]


def model(name, offset=(0, 0, 0), bones=(), scale=1.0, texture="x"):
    pos = [tuple(scale * c + o for c, o in zip(p, offset)) for p in QUAD]
    return gr2_write.static_model(name, pos, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                  [(0, 1, 2), (0, 2, 3)], texture=rf"C:\a\art\{texture}.ddt",
                                  bump=rf"C:\a\art\{texture}_b.ddt", bones=bones)


ANIM = """<animfile>
\t<attachment>
\t\ttree_1
\t\t<component>
\t\t\ttree
\t\t\t<logic type="Variation">
\t\t\t\t<data><assetreference type="GrannyModel"><file>trees\\tree_a</file></assetreference></data>
\t\t\t\t<data><assetreference type="GrannyModel"><file>trees\\tree_b</file></assetreference></data>
\t\t\t</logic>
\t\t</component>
\t\t<anim>Idle<component>tree</component></anim>
\t</attachment>
\t<attachment>
\t\tsmoke
\t\t<component>
\t\t\tsmoke
\t\t\t<assetreference type="ParticleSystem"><file>effects\\smoke.particle</file></assetreference>
\t\t</component>
\t</attachment>
\t<component>
\t\tbuilding
\t\t<logic type="Destruction">
\t\t\t<p1><assetreference type="GrannyModel"><file>mod\\farm\\farm_damaged</file></assetreference></p1>
\t\t\t<p99><assetreference type="GrannyModel"><file>mod\\farm\\farm</file></assetreference></p99>
\t\t</logic>
\t\t<attach a="tree_1" frombone="ATTACHPOINT" tobone="bone_corn01" syncanims="0"/>
\t\t<attach a="smoke" frombone="ATTACHPOINT" tobone="bone_corn01" syncanims="0"/>
\t</component>
</animfile>
"""


def put(root, rel, data):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


class Merge(unittest.TestCase):
    def test_parts_stand_where_they_hung(self):
        body = model("farm", bones=[("bone_corn01", (3.0, 0.0, 0.0))], scale=4.0)
        tree = model("tree", texture="tree")
        out, info = gr2_merge.merge(body, [(tree, "ATTACHPOINT", "bone_corn01")])
        self.assertEqual(info["meshes"], 1)
        self.assertEqual(info["parts"][0]["bound_to"], "bone_corn01")
        merged = gr2_mesh.read(out)
        self.assertEqual(len(merged["meshes"]), 2)
        expected = gr2_mesh.attach(gr2_mesh.read(body), gr2_mesh.read(tree), "ATTACHPOINT", "bone_corn01")
        np.testing.assert_allclose(merged["meshes"][1]["positions"], expected[0]["positions"], atol=1e-5)
        self.assertIn(r"C:\a\art\tree.ddt", merged["textures"])               # the part's texture
        self.assertIn(r"C:\a\art\x.ddt", merged["textures"])                  # the body's, kept
        root = gr2.load(out).root()
        self.assertEqual(len(root.get("Models")[0].get("MeshBindings")), 2)
        self.assertTrue(gr2.crc_ok(out))


class Tool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.art = os.path.join(t, "art")
        for rel in (r"mod\farm\farm.gr2", r"mod\farm\farm_damaged.gr2"):
            put(self.art, rel, model("farm", bones=[("bone_corn01", (3.0, 0.0, 0.0))], scale=4.0))
        put(self.art, r"trees\tree_a.gr2", model("tree_a", texture="tree"))
        put(self.art, r"trees\tree_b.gr2", model("tree_b", texture="tree"))
        put(self.art, r"mod\farm\farm.xml", ANIM)
        self.manifest = os.path.join(t, "m.txt")
        put(t, "m.txt", "mod\\farm\\farm.xml\n")
        self.out = os.path.join(t, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ma.main(["--manifest", self.manifest, "--art", self.art, "--out", self.out, *extra])
        return code, buf.getvalue()

    def test_merge(self):
        code, text = self.run_tool()
        self.assertEqual(code, 0, text)
        self.assertIn("2 merged models", text)
        with open(os.path.join(self.out, r"mod\farm\farm.xml"), encoding="utf-8") as fh:
            xml = fh.read()
        self.assertNotIn('a="tree_1"', xml)                                   # merged: its line gone
        self.assertIn('a="smoke"', xml)                                       # a particle stays
        self.assertIn(r"<file>mod\farm\farm_merged</file>", xml)
        self.assertIn(r"<file>mod\farm\farm_damaged_merged</file>", xml)
        with open(os.path.join(self.out, r"mod\farm\farm_merged.gr2"), "rb") as fh:
            merged = gr2_mesh.read(fh.read())
        self.assertEqual([m["name"] for m in merged["meshes"]][1], "tree_a_0")  # the first pick
        with open(os.path.join(self.out, "merge.txt"), encoding="utf-8") as fh:
            self.assertIn("smoke left as it is", fh.read())

    def test_dry_run(self):
        code, text = self.run_tool("--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main(verbosity=1)
