# SPDX-License-Identifier: GPL-3.0-or-later
"""The static model converter: core/objio.py, core/glbio.py, core/meshprep.py and
scripts/mesh_to_game.py, on models made here (no file of the game or of a mod).

    venv/bin/python -I tests/test_meshfile.py
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import numpy as np  # noqa: E402

from core import glbio, meshprep, objio, paint  # noqa: E402
from core.objio import MeshError  # noqa: E402

CUBE = """# a cube 200 cm wide, Y up
mtllib cube.mtl
v -100 0 -100
v 100 0 -100
v 100 200 -100
v -100 200 -100
v -100 0 100
v 100 0 100
v 100 200 100
v -100 200 100
vt 0 0
vt 1 0
vt 1 1
vt 0 1
usemtl wood
s off
f 1/1 4/4 3/3 2/2
f 5/1 6/2 7/3 8/4
f 1/1 2/2 6/3 5/4
f 4/1 8/4 7/3 3/2
f 2/1 3/2 7/3 6/4
f 1/1 5/2 8/3 4/4
"""
MTL = "newmtl wood\nKd 1 1 1\nmap_Kd tex.png\n"


def png(w=64, h=64):
    a = np.zeros((h, w, 4), np.uint8)
    a[..., 0] = np.arange(w)[None, :] * 255 // max(w - 1, 1)
    a[..., 1] = np.arange(h)[:, None] * 255 // max(h - 1, 1)
    a[..., 3] = 255
    return paint.png_bytes(a)


def glb(positions, indices=None, uvs=None, normals=None, mode=None, node=None, picture=None,
        uv_normalised=False, texture_transform=None, extra_nodes=(), images=1, required=()):
    """A minimal .glb with one mesh of one primitive."""
    blob, views, accessors = bytearray(), [], []

    def add(arr, ctype, kind, normalised=False):
        while len(blob) % 4:
            blob.append(0)
        data = arr.tobytes()
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(arr), "type": kind}
        if normalised:
            acc["normalized"] = True
        if ctype == 5126 and kind == "VEC3":
            acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    attrs = {"POSITION": add(np.asarray(positions, np.float32), 5126, "VEC3")}
    if uvs is not None:
        if uv_normalised:
            attrs["TEXCOORD_0"] = add((np.asarray(uvs) * 65535).round().astype(np.uint16), 5123, "VEC2", True)
        else:
            attrs["TEXCOORD_0"] = add(np.asarray(uvs, np.float32), 5126, "VEC2")
    if normals is not None:
        attrs["NORMAL"] = add(np.asarray(normals, np.float32), 5126, "VEC3")
    prim = {"attributes": attrs, "material": 0}
    if indices is not None:
        prim["indices"] = add(np.asarray(indices, np.uint16), 5123, "SCALAR")
    if mode is not None:
        prim["mode"] = mode
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [dict(node or {}, mesh=0), *extra_nodes], "meshes": [{"primitives": [prim]}],
         "accessors": accessors, "bufferViews": views, "materials": [{"pbrMetallicRoughness": {}}]}
    if required:
        g["extensionsRequired"] = list(required)
    if picture is not None:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(picture)})
        blob.extend(picture)
        g["images"] = [{"bufferView": len(views) - 1, "mimeType": "image/png"}]
        g["textures"] = [{"source": 0}]
        tex = {"index": 0}
        if texture_transform:
            tex["extensions"] = {"KHR_texture_transform": texture_transform}
        g["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = tex
        if images == 2:
            g["images"].append(dict(g["images"][0]))
            g["textures"].append({"source": 1})
            g["materials"].append({"pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}})
            g["meshes"][0]["primitives"].append(dict(prim, material=1))
    while len(blob) % 4:
        blob.append(0)
    g["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(g).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


TRI = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
TRI_UV = [(0, 0), (1, 0), (0, 1)]


class Obj(unittest.TestCase):
    def test_a_cube_in_centimetres_stands_on_the_ground_with_flat_faces(self):
        mesh = objio.read_obj(CUBE, {"cube.mtl": MTL})
        self.assertEqual(mesh["texture"], "tex.png")
        prep = meshprep.prepare(mesh, scale=0.01)
        self.assertEqual(len(prep["triangles"]), 12)
        self.assertEqual(len(prep["positions"]), 24)               # each corner split by its face's normal
        self.assertEqual(prep["footprint"], (2.0, 2.0))
        self.assertAlmostEqual(prep["height"], 2.0)
        p = np.asarray(prep["positions"])
        self.assertAlmostEqual(p[:, 2].min(), 0.0)                  # Y up became Z up, on the ground
        np.testing.assert_allclose(p[:, :2].min(0), [-1, -1])
        for t in prep["triangles"]:                                 # wound outwards: normal agrees with the corners'
            a, b, c = (np.asarray(prep["positions"][i]) for i in t)
            n = np.cross(b - a, c - a)
            self.assertGreater(np.dot(n, prep["normals"][t[0]]), 0)
            self.assertGreater(np.dot(n, (a + b + c) / 3 - [0, 0, 1]), 0)

    def test_fit_turn_and_z_up(self):
        mesh = objio.read_obj(CUBE.replace("v 100 0 -100", "v 300 0 -100").replace("v 100 0 100", "v 300 0 100")
                              .replace("v 100 200 -100", "v 300 200 -100").replace("v 100 200 100", "v 300 200 100"))
        prep = meshprep.prepare(mesh, fit=8)
        self.assertEqual(prep["footprint"], (8.0, 4.0))
        self.assertAlmostEqual(prep["height"], 4.0)                 # the height follows
        turned = meshprep.prepare(mesh, fit=8, turn=90)
        self.assertEqual(turned["footprint"], (4.0, 8.0))
        zup = meshprep.prepare(mesh, up="z", fit=8)
        self.assertAlmostEqual(zup["height"], 4.0)                  # the file's Z (depth) taken as height
        with self.assertRaises(MeshError):
            meshprep.prepare(mesh, turn=45)

    def test_ngons_negative_indices_and_smoothing(self):
        hexagon = "".join(f"v {np.cos(a):.6f} 0 {np.sin(a):.6f}\nvt 0.5 0.5\n" for a in np.linspace(0, 2 * np.pi, 7)[:-1])
        mesh = objio.read_obj(hexagon + "f -6/-6 -5/-5 -4/-4 -3/-3 -2/-2 -1/-1\n")
        self.assertEqual(len(meshprep.prepare(mesh)["triangles"]), 4)
        # a tube of 8 sides: smooth shares one normal per vertex, flat splits them
        rows = []
        for k in range(8):
            a = 2 * np.pi * k / 8
            rows += [f"v {np.cos(a):.6f} 0 {np.sin(a):.6f}", f"v {np.cos(a):.6f} 1 {np.sin(a):.6f}"]
        faces = [f"f {2*k+1}/1 {2*((k+1)%8)+1}/1 {2*((k+1)%8)+2}/1 {2*k+2}/1" for k in range(8)]
        text = "\n".join(rows) + "\nvt 0 0\ns 1\n" + "\n".join(faces) + "\n"
        smooth = meshprep.prepare(objio.read_obj(text))
        flat = meshprep.prepare(objio.read_obj(text), flat=True)
        self.assertEqual(len(smooth["positions"]), 16)
        self.assertEqual(len(flat["positions"]), 32)

    def test_what_it_refuses_says_why(self):
        cases = {
            "texture coordinates": "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
            "does not have": "v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nf 1/1 2/1 4/1\n",
            "free-form": "cstype bspline\n",
            "no face": "v 0 0 0\n",
        }
        for why, text in cases.items():
            with self.assertRaises(MeshError) as e:
                objio.read_obj(text)
            self.assertIn(why, str(e.exception))
        two = CUBE.replace("usemtl wood\ns off\nf 1/1 4/4 3/3 2/2", "usemtl wood\ns off\nf 1/1 4/4 3/3 2/2\nusemtl stone")
        with self.assertRaises(MeshError) as e:
            objio.read_obj(two, {"cube.mtl": MTL + "newmtl stone\nmap_Kd stone.png\n"})
        self.assertIn("pack them", str(e.exception))
        objio.read_obj(two, {"cube.mtl": MTL + "newmtl stone\nmap_Kd tex.png\n"})   # the same picture is fine
        with self.assertRaises(MeshError):
            objio.read_obj(CUBE, {"cube.mtl": "newmtl wood\nmap_Kd -s 2 2 1 tex.png\n"})
        objio.read_obj(CUBE, {"cube.mtl": "newmtl wood\nmap_Kd -s 1 1 1 -bm 0.5 tex.png\n"})

    def test_the_picture_is_read_beside_the_file_and_made_a_power_of_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in (("cube.obj", CUBE.encode()), ("cube.mtl", MTL.encode()), ("tex.png", png(100, 60))):
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(data)
            mesh = meshprep.load(os.path.join(tmp, "cube.obj"))
            rgba = meshprep.texture_rgba(mesh)
            self.assertEqual(rgba.shape, (64, 128, 4))
            self.assertTrue(any("power of two" in w for w in mesh["warnings"]))


class Gltf(unittest.TestCase):
    def test_triangles_with_the_node_transform_and_an_embedded_picture(self):
        data = glb(TRI, [0, 1, 2], TRI_UV, node={"translation": [5, 0, 0], "scale": [2, 2, 2]}, picture=png())
        mesh = glbio.read_gltf(data)
        np.testing.assert_allclose(mesh["positions"], [(5, 0, 0), (7, 0, 0), (5, 2, 0)])
        np.testing.assert_allclose(mesh["uvs"], [(0, 1), (1, 1), (0, 0)])         # V turned up
        self.assertEqual(meshprep.texture_rgba(mesh).shape, (64, 64, 4))
        self.assertEqual(len(meshprep.prepare(mesh)["triangles"]), 1)

    def test_strips_fans_quantised_uvs_and_the_texture_transform(self):
        quad = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]
        uv = [(0, 0), (1, 0), (0, 1), (1, 1)]
        strip = glbio.read_gltf(glb(quad, None, uv, mode=5))
        self.assertEqual(len(strip["faces"]), 2)
        fan = glbio.read_gltf(glb(quad, [0, 1, 3, 2], uv, mode=6))
        self.assertEqual(len(fan["faces"]), 2)
        q = glbio.read_gltf(glb(TRI, None, TRI_UV, uv_normalised=True))
        np.testing.assert_allclose(q["uvs"], [(0, 1), (1, 1), (0, 0)], atol=1e-4)
        t = glbio.read_gltf(glb(TRI, None, TRI_UV, picture=png(), texture_transform={"offset": [0.5, 0], "scale": [0.5, 1]}))
        np.testing.assert_allclose(np.asarray(t["uvs"])[:, 0], [0.5, 1.0, 0.5])
        normals = glbio.read_gltf(glb(TRI, None, TRI_UV, normals=[(0, 0, 1)] * 3, node={"rotation": [-0.7071068, 0, 0, 0.7071068]}))
        np.testing.assert_allclose(normals["normals"][0], (0, 1, 0), atol=1e-6)    # turned with the node

    def test_what_it_refuses_says_why(self):
        with self.assertRaises(MeshError) as e:
            glbio.read_gltf(glb(TRI, None, None))
        self.assertIn("texture coordinates", str(e.exception))
        with self.assertRaises(MeshError) as e:
            glbio.read_gltf(glb(TRI, None, TRI_UV, node={"skin": 0}))
        self.assertIn("skin", str(e.exception))
        self.assertEqual(len(glbio.read_gltf(glb(TRI, None, TRI_UV, node={"skin": 0}), ignore_skin=True)["faces"]), 1)
        with self.assertRaises(MeshError) as e:
            glbio.read_gltf(glb(TRI, None, TRI_UV, required=["KHR_draco_mesh_compression"]))
        self.assertIn("Draco", str(e.exception))
        with self.assertRaises(MeshError) as e:
            glbio.read_gltf(glb(TRI, None, TRI_UV, picture=png(), images=2))
        self.assertIn("pack them", str(e.exception))
        with self.assertRaises(MeshError):
            glbio.read_gltf(glb(TRI, None, TRI_UV, mode=1))
        with self.assertRaises(MeshError):
            glbio.read_gltf(b"glTF\x01\x00\x00\x00\x0c\x00\x00\x00")


class Script(unittest.TestCase):
    def test_a_model_becomes_a_bundle_that_reads_back(self):
        sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
        from aoe3game import gr2_mesh
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in (("cube.obj", CUBE.encode()), ("cube.mtl", MTL.encode()), ("tex.png", png())):
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(data)
            out = os.path.join(tmp, "out")
            cmd = [sys.executable, "-I", os.path.join(ROOT, "scripts", "mesh_to_game.py"), "--in",
                   os.path.join(tmp, "cube.obj"), "--out", out, "--name", "TestCube", "--scale", "0.02", "--no-profile"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("12 triangles", r.stdout)
            gr2s = [os.path.join(b, f) for b, _d, fs in os.walk(out) for f in fs if f.endswith(".gr2") and "death" not in f]
            self.assertTrue(gr2s, r.stdout)
            with open(sorted(gr2s, key=len)[0], "rb") as fh:
                back = gr2_mesh.read(fh.read())
            m = back["meshes"][0]
            self.assertEqual(len(m["triangles"]), 12)
            p = np.asarray(m["positions"])
            np.testing.assert_allclose(p.max(0) - p.min(0), [4, 4, 4], atol=1e-3)
            self.assertTrue(any(f.endswith(".ddt") for _b, _d, fs in os.walk(out) for f in fs))
            r2 = subprocess.run(cmd[:-3] + ["--fit-units", "4", "--check-only", "--no-profile"], capture_output=True, text=True)
            self.assertIn("(4.00 x 4.00 game units)", r2.stdout)
            # --check-only writes nothing; a refused model says why
            r = subprocess.run(cmd[:-5] + ["--name", "TestCube", "--check-only", "--no-profile"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(tmp, "bad.obj"), "w") as fh:
                fh.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
            r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "mesh_to_game.py"), "--in",
                                os.path.join(tmp, "bad.obj"), "--out", out, "--name", "Bad"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("refused", r.stdout)


if __name__ == "__main__":
    unittest.main()
