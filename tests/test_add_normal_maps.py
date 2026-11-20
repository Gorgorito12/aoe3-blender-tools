# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of aoe3game/gr2_material.py and tools/add_normal_maps.py on a synthetic model (numpy).

    venv\\Scripts\\python -I tests/test_add_normal_maps.py
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
from aoe3game import ddt, gr2, gr2_edit, gr2_material, gr2_write  # noqa: E402
import add_normal_maps as anm  # noqa: E402

QUAD = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]


def without_bump(texture=r"C:\x\art\mod\hut\hut.ddt"):
    data = gr2_write.static_model("hut", QUAD, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                  [(0, 1, 2), (0, 2, 3)], texture=texture, bump=r"C:\x\art\flat.ddt")
    root = gr2_edit.copy_tree(gr2.load(data))
    for mat in gr2_material.materials(root):
        mat.values["Maps"] = [mp for mp in mat.values["Maps"] if mp.values["Usage"] != "Bump"]
    root.values["Textures"] = [t for t in root.values["Textures"] if "flat" not in t.values["FromFileName"]]
    root.values["Materials"] = [m for m in root.values["Materials"]
                                if not (m.values.get("Texture") is not None and "flat" in m.values["Texture"].values["FromFileName"])]
    return gr2_write.serialize(root)


def put(root, rel, data):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data)


class Material(unittest.TestCase):
    def test_add_bump(self):
        root = gr2_edit.copy_tree(gr2.load(without_bump()))
        mat = gr2_material.materials(root)[0]
        self.assertTrue(gr2_material.wants_bump(mat))
        gr2_material.add_bump(root, mat, r"C:\art\mod\hut\hut_b.ddt")
        self.assertFalse(gr2_material.wants_bump(mat))
        out = gr2.load(gr2_write.serialize(root)).root()
        maps = {mp.get("Usage"): mp.get("Map").get("Texture").get("FromFileName")
                for mp in out.get("Meshes")[0].get("MaterialBindings")[0].get("Material").get("Maps")}
        self.assertEqual(maps["Bump"], r"C:\art\mod\hut\hut_b.ddt")
        self.assertEqual(maps["Diffuse Color"], r"C:\x\art\mod\hut\hut.ddt")
        self.assertIn(r"C:\art\mod\hut\hut_b.ddt", [t.get("FromFileName") for t in out.get("Textures")])


class Tool(unittest.TestCase):
    def test_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = os.path.join(tmp, "art")
            put(art, r"mod\hut\hut.gr2", without_bump())
            rgba = np.zeros((32, 32, 4), np.uint8)
            rgba[..., :3] = (np.arange(32)[None, :, None] * 8).astype(np.uint8)
            rgba[..., 3] = 255
            put(art, r"mod\hut\hut.ddt", ddt.write_bgra(rgba, mips=False))
            put(tmp, "m.txt", b"mod\\hut\\hut.gr2\n")
            out = os.path.join(tmp, "out")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(anm.main(["--manifest", os.path.join(tmp, "m.txt"), "--art", art, "--out", out]), 0)
            with open(os.path.join(out, r"mod\hut\hut_b.ddt"), "rb") as fh:
                hd = ddt.read_header(fh.read())
            self.assertEqual((hd.usage, hd.alpha, hd.format), (6, 0, ddt.DXT5))
            with open(os.path.join(out, r"mod\hut\hut.gr2"), "rb") as fh:
                root = gr2_edit.copy_tree(gr2.load(fh.read()))
            self.assertFalse(gr2_material.wants_bump(gr2_material.materials(root)[0]))
            # a second run over the result changes nothing
            put(tmp, "m2.txt", b"mod\\hut\\hut.gr2\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                anm.main(["--manifest", os.path.join(tmp, "m2.txt"), "--art", out, "--art", art,
                          "--out", os.path.join(tmp, "out2")])
            self.assertIn("0 given normal maps", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=1)
