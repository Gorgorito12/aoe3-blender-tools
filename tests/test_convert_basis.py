# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of aoe3game/gr2_basis.py and tools/convert_basis.py on synthetic files (numpy, no Granny
runtime).

    venv\\Scripts\\python -I tests/test_convert_basis.py

A raw 3ds Max accessory is made from a static model: inches with Z up, its one bone scaled by 16
and placed away from the origin (the scene it was cut from), with an animation track. Rewritten,
it must stand on a unit's bone exactly where the original stood, in the stock basis, with an
identity bone, no animation, and its triangles still facing out.
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
from aoe3game import gr2, gr2_basis, gr2_edit, gr2_mesh, gr2_write  # noqa: E402
import convert_basis  # noqa: E402

INCH = 39.370079
MAX_BASIS = {"FromArtToolName": "3D Studio MAX", "UnitsPerMeter": INCH, "Origin": (0.0, 0.0, 0.0),
             "RightVector": (1.0, 0.0, 0.0), "UpVector": (0.0, 0.0, 1.0), "BackVector": (0.0, -1.0, 0.0)}


def box():
    """A closed box 0.4 x 0.3 x 0.2 m (Blender space), its faces facing out."""
    p = np.array([(x, y, z) for x in (-0.2, 0.2) for y in (-0.15, 0.15) for z in (0.0, 0.2)])
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    pos, nor, tris = [], [], []
    for f in faces:
        q = p[list(f)]
        n = np.cross(q[1] - q[0], q[2] - q[0])
        n = n / np.linalg.norm(n)
        if np.dot(n, q.mean(0)) < 0:
            n = -n
        k = len(pos)
        pos += [tuple(v) for v in q]
        nor += [tuple(n)] * 4
        tris += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
    return pos, nor, tris


def raw_max_hat(scale=16.0, offset=(3.0, -1.0, 2.0)):
    """A one-bone accessory as 3ds Max exports it: model-space vertices at `offset` metres from
    the origin, its bone there too with `scale`, the same placement in an animation."""
    pos, nor, tris = box()
    data = gr2_write.static_model("hat", pos, nor, [(0.0, 0.0)] * len(pos), tris,
                                  texture=r"C:\x\art\units\a\hat.ddt", bump=r"C:\x\art\units\a\hat_b.ddt")
    root = gr2_edit.copy_tree(gr2.load(data))
    art = root.values["ArtToolInfo"]
    art.values.update(MAX_BASIS)
    off = np.array(offset) * INCH
    for vd in root.values["VertexDatas"]:
        vs = vd.values["Vertices"]
        a = np.frombuffer(vs.raw, np.float32).reshape(vs.count, 8).copy()
        stock = a[:, :3].astype(np.float64)
        u = gr2_write.STOCK_BASIS["units_per_meter"]
        blender = np.stack([-stock[:, 0], -stock[:, 2], stock[:, 1]], 1) / u
        a[:, :3] = blender * INCH + off                   # Max axes are Blender's, in inches
        n = a[:, 3:6].astype(np.float64)
        a[:, 3:6] = np.stack([-n[:, 0], -n[:, 2], n[:, 1]], 1)
        vd.values["Vertices"] = gr2_write.Flat(vs.spec, a.tobytes(), vs.count)
    sk = root.values["Skeletons"][0]
    hat_bone = sk.values["Bones"][1]
    hat_bone.values["ParentIndex"] = -1
    sk.values["Bones"] = [hat_bone]
    world = np.eye(4)
    world[:3, :3] *= scale
    world[3, :3] = off
    hat_bone.values["Transform"] = (7, *off, 0.0, 0.0, 0.0, 1.0,
                                    scale, 0.0, 0.0, 0.0, scale, 0.0, 0.0, 0.0, scale)
    hat_bone.values["InverseWorldTransform"] = tuple(float(v) for v in np.linalg.inv(world).reshape(-1))
    for tris_ in root.values["TriTopologies"]:                # Max keeps Blender's winding
        ix = tris_.values["Indices16"]
        t = np.frombuffer(ix.raw, np.uint16).reshape(-1, 3)[:, ::-1].copy()
        tris_.values["Indices16"] = gr2_write.Flat(ix.spec, t.tobytes(), ix.count)
    model = root.values["Models"][0]
    model.values["InitialPlacement"] = (3, *off, 0.0, 0.0, 0.0, 1.0, 1, 0, 0, 0, 1, 0, 0, 0, 1)
    specs = {name: ref for _k, name, ref, _w in root.spec.members}
    group = gr2_write.W(specs["TrackGroups"], Name="hat", InitialPlacement=model.values["InitialPlacement"])
    root.values["TrackGroups"] = [group]
    anim_spec = specs["Animations"]
    groups_ref = next(ref for _k, name, ref, _w in anim_spec.members if name == "TrackGroups")
    assert groups_ref is specs["TrackGroups"]
    root.values["Animations"] = [gr2_write.W(anim_spec, Name="scene.max", Duration=3.33, TimeStep=0.033,
                                             Oversampling=1.0, TrackGroups=[group])]
    return gr2_write.serialize(root, type_tag=0x80000015), np.array(offset)


def unit_body():
    """A stock-basis body with a HEAD bone 1.6 m up, turned 90 degrees about the vertical."""
    pos, nor, tris = box()
    data = gr2_write.static_model("body", pos, nor, [(0.0, 0.0)] * len(pos), tris,
                                  texture=r"C:\x\art\b.ddt", bump=r"C:\x\art\b_b.ddt",
                                  bones=[("Bip01 Head", (0.0, 0.0, 1.6))])
    return gr2_mesh.read(data)


def outward(model):
    """Every triangle of every mesh faces away from its mesh's centre (Blender space)."""
    for m in model["meshes"]:
        p = m["positions"]
        c = p.mean(0)
        for a, b, d in m["triangles"]:
            n = np.cross(p[b] - p[a], p[d] - p[a])
            if np.dot(n, (p[a] + p[b] + p[d]) / 3 - c) <= 0:
                return False
    return True


class NormaliseRigid(unittest.TestCase):
    def test_stands_where_it_stood(self):
        raw, offset = raw_max_hat()
        new, info = gr2_basis.normalise_rigid(raw)
        self.assertEqual(info["bone"], "hat")
        self.assertAlmostEqual(info["scale_dropped"], 16.0, 3)
        body = unit_body()
        before = gr2_mesh.attach(body, gr2_mesh.read(raw), "bone_hat", "HEAD")
        after = gr2_mesh.attach(body, gr2_mesh.read(new), "bone_hat", "HEAD")
        for x, y in zip(before, after):
            np.testing.assert_allclose(x["positions"], y["positions"], atol=1e-5)
        # the object is now at the origin: the box spans its own 0.4 x 0.3 x 0.2 m around it
        m = gr2_mesh.read(new)
        p = m["meshes"][0]["positions"]
        np.testing.assert_allclose(p.min(0), [-0.2, -0.15, 0.0], atol=1e-5)
        np.testing.assert_allclose(p.max(0), [0.2, 0.15, 0.2], atol=1e-5)
        self.assertTrue(outward(m))

    def test_stock_form(self):
        raw, _ = raw_max_hat()
        new, _ = gr2_basis.normalise_rigid(raw)
        root = gr2.load(new).root()
        art = root.get("ArtToolInfo")
        self.assertEqual(art.get("FromArtToolName"), "ESPostExport")
        self.assertAlmostEqual(art.get("UnitsPerMeter"), 0.615157485, 6)
        self.assertEqual(tuple(art.get("UpVector")), (0.0, 1.0, 0.0))
        bone = root.get("Skeletons")[0].get("Bones")[0]
        np.testing.assert_allclose(bone.get("InverseWorldTransform"), np.eye(4).reshape(-1))
        self.assertEqual(bone.get("Transform")["scale_shear"], (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
        self.assertEqual(len(root.get("Animations") or []), 0)
        self.assertEqual(root.get("Models")[0].get("InitialPlacement")["position"], (0.0, 0.0, 0.0))
        self.assertEqual(gr2.load(new).c.type_tag, 0x80000015)
        # the stored texture names are untouched
        self.assertIn(r"C:\x\art\units\a\hat.ddt", [t.get("FromFileName") for t in root.get("Textures")])
        # each binding's box holds the vertices it binds
        mesh = root.get("Meshes")[0]
        bb = mesh.get("BoneBindings")[0]
        p = gr2_mesh.read(new)["meshes"][0]["file_positions"]
        np.testing.assert_allclose(bb.get("OBBMin"), p.min(0), atol=1e-6)
        np.testing.assert_allclose(bb.get("OBBMax"), p.max(0), atol=1e-6)

    def test_refuses_a_scale_carrier_without_mesh(self):
        raw, _ = raw_max_hat()
        root = gr2_edit.copy_tree(gr2.load(raw))
        root.values["Meshes"] = None
        root.values["Models"][0].values["MeshBindings"] = None
        with self.assertRaises(gr2_basis.Refused):
            gr2_basis.normalise_rigid(gr2_write.serialize(root, type_tag=0x80000015))

    def test_refuses_more_than_one_bone(self):
        pos, nor, tris = box()
        data = gr2_write.static_model("b", pos, nor, [(0.0, 0.0)] * len(pos), tris,
                                      texture="t.ddt", bump="b.ddt")
        with self.assertRaises(gr2_basis.Refused):
            gr2_basis.normalise_rigid(data)


class CommandLine(unittest.TestCase):
    def run_tool(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = convert_basis.main(list(argv))
        return code, out.getvalue()

    def test_folder_dry_run_and_write(self):
        raw, _ = raw_max_hat()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in", "units", "a")
            os.makedirs(src)
            with open(os.path.join(src, "hat.gr2"), "wb") as fh:
                fh.write(raw)
            code, text = self.run_tool(os.path.join(tmp, "in"), "-o", os.path.join(tmp, "out"), "--dry-run")
            self.assertEqual(code, 0, text)
            self.assertIn("1 to convert", text)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out")))
            code, text = self.run_tool(os.path.join(tmp, "in"), "-o", os.path.join(tmp, "out"))
            self.assertEqual(code, 0, text)
            written = os.path.join(tmp, "out", "units", "a", "hat.gr2")
            with open(written, "rb") as fh:
                self.assertEqual(gr2.load(fh.read()).root().get("ArtToolInfo").get("FromArtToolName"),
                                 "ESPostExport")
            # a converted file is left alone, unless --all
            code, text = self.run_tool(written, "-o", os.path.join(tmp, "again.gr2"))
            self.assertIn("1 already converted", text)
            self.assertFalse(os.path.exists(os.path.join(tmp, "again.gr2")))

    def test_in_place_keeps_a_backup(self):
        raw, _ = raw_max_hat()
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "hat.gr2")
            with open(p, "wb") as fh:
                fh.write(raw)
            code, text = self.run_tool(p)
            self.assertEqual(code, 0, text)
            with open(p + ".bak", "rb") as fh:
                self.assertEqual(fh.read(), raw)

    def test_bad_arguments(self):
        code, text = self.run_tool("--granny", "b.exe", "x.gr2")       # bridge without its game
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
