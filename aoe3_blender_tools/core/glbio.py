# SPDX-License-Identifier: GPL-3.0-or-later
"""glTF 2.0 (.glb, or .gltf with its buffers) as a static mesh to convert for the game, without
Blender.

Read: the default scene, its node transforms baked in (matrix or translation, rotation, scale);
every primitive of triangles, a strip or a fan, with or without indices, any byteStride; POSITION,
NORMAL (optional) and TEXCOORD_0 as floats or normalised integers (KHR_mesh_quantization); the
base colour picture, the same one for every primitive, with KHR_texture_transform baked into the
texture coordinates. Refused, with the reason: Draco or meshopt compression, KTX/basis pictures,
sparse accessors, more than one base colour picture, no texture coordinates, a skin (a unit
needs its skeleton: core/glbio cannot write one), lines and points. Animations, morph targets and
vertex colours are left out with a warning. The picture is returned as bytes and its type: PNG is
read here (core/pngio.py); JPEG or WebP must be decoded by whoever calls (the studio's page does).

The result is a MeshIn as core/objio.py's, in glTF's axes (Y up, metres, V down already turned
to V up); core/meshprep.py turns it into the game's.
"""
import base64
import json
import math
import os
import struct

import numpy as np

from .objio import MeshError

REFUSED_EXT = {"KHR_draco_mesh_compression": "Draco compression", "EXT_meshopt_compression": "meshopt compression",
               "KHR_texture_basisu": "KTX/basis pictures", "EXT_texture_webp": None}
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
NORMALISE = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def _matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], np.float64).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), np.float64)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), np.float64)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


class _Doc:
    def __init__(self, gltf, buffers):
        self.g, self.buffers = gltf, buffers

    def accessor(self, index):
        a = self.g["accessors"][index]
        if "sparse" in a:
            raise MeshError("a sparse accessor: export the model without sparse data")
        count, kind, ctype = a["count"], a["type"], a["componentType"]
        width = WIDTH[kind]
        dtype = np.dtype(COMPONENT[ctype]).newbyteorder("<")
        if "bufferView" not in a:
            out = np.zeros((count, width), np.float64)
        else:
            view = self.g["bufferViews"][a["bufferView"]]
            data = self.buffers[view["buffer"]]
            start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
            item = dtype.itemsize * width
            stride = view.get("byteStride") or item
            if stride == item:
                out = np.frombuffer(data, dtype, count * width, start).reshape(count, width)
            else:
                rows = np.lib.stride_tricks.as_strided(
                    np.frombuffer(data, np.uint8, len(data) - start, start), (count, item), (stride, 1))
                out = np.frombuffer(rows.copy().tobytes(), dtype).reshape(count, width)
            out = out.astype(np.float64)
        if a.get("normalized") and ctype in NORMALISE:
            out = np.maximum(out / NORMALISE[ctype], -1.0)
        return out


def _read_glb(data):
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise MeshError("not a glTF 2.0 binary file")
    pos, js, binary = 12, None, b""
    while pos + 8 <= len(data):
        size, kind = struct.unpack_from("<II", data, pos)
        chunk = data[pos + 8:pos + 8 + size]
        if kind == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        pos += 8 + size
    if js is None:
        raise MeshError("the file has no JSON chunk")
    return js, binary


def _buffer(uri, folder):
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    path = os.path.normpath(os.path.join(folder, uri.replace("/", os.sep)))
    if folder and os.path.commonpath([os.path.abspath(path), os.path.abspath(folder)]) != os.path.abspath(folder):
        raise MeshError(f"a buffer outside the model's folder: {uri}")
    with open(path, "rb") as fh:
        return fh.read()


def read_gltf(data, folder="", ignore_skin=False):
    """The mesh of a .glb's bytes, or of a .gltf's (its buffers read from `folder`)."""
    if data[:4] == b"glTF":
        g, binary = _read_glb(data)
    else:
        g, binary = json.loads(data.decode("utf-8-sig")), b""
    for ext in g.get("extensionsRequired", []):
        if ext in REFUSED_EXT and REFUSED_EXT[ext]:
            raise MeshError(f"{REFUSED_EXT[ext]} ({ext}): export the model without it")
    buffers = []
    for b in g.get("buffers", []):
        buffers.append(_buffer(b["uri"], folder) if "uri" in b else binary)
    doc = _Doc(g, buffers)
    warnings = []
    if g.get("animations"):
        warnings.append("animations left out (a static model)")
    scenes = g.get("scenes") or [{"nodes": list(range(len(g.get("nodes", []))))}]
    roots = scenes[g.get("scene", 0)].get("nodes", [])
    positions, normals, uvs, faces = [], [], [], []
    images = set()
    has_normals = True

    def visit(index, parent):
        nonlocal has_normals
        node = g["nodes"][index]
        m = parent @ _matrix(node)
        if "skin" in node and not ignore_skin:
            raise MeshError("the model has a skin (a unit with bones): this converter writes static models; "
                            "a unit goes through the unit tools")
        if "mesh" in node:
            normal_m = np.linalg.inv(m[:3, :3]).T
            for prim in g["meshes"][node["mesh"]]["primitives"]:
                mode = prim.get("mode", 4)
                if mode not in (4, 5, 6):
                    raise MeshError("lines or points in the model: only triangles are converted")
                attrs = prim["attributes"]
                if "TEXCOORD_0" not in attrs:
                    raise MeshError("a part of the model has no texture coordinates: unwrap it first")
                if prim.get("targets"):
                    warnings.append("morph targets left out")
                if "COLOR_0" in attrs:
                    warnings.append("vertex colours left out")
                p = doc.accessor(attrs["POSITION"])[:, :3]
                p = (np.c_[p, np.ones(len(p))] @ m.T)[:, :3]
                t = doc.accessor(attrs["TEXCOORD_0"])[:, :2].copy()
                mat = g.get("materials", [{}])[prim["material"]] if "material" in prim else {}
                base = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
                if base is not None:
                    images.add(g["textures"][base["index"]].get("source"))
                    tr = base.get("extensions", {}).get("KHR_texture_transform")
                    if tr:
                        ox, oy = tr.get("offset", [0, 0])
                        rot = tr.get("rotation", 0.0)
                        sx, sy = tr.get("scale", [1, 1])
                        c, s = math.cos(rot), math.sin(rot)
                        u, v = t[:, 0] * sx, t[:, 1] * sy
                        t = np.c_[c * u + s * v + ox, -s * u + c * v + oy]
                t[:, 1] = 1.0 - t[:, 1]                         # glTF's V runs down
                if "NORMAL" in attrs:
                    n = doc.accessor(attrs["NORMAL"])[:, :3] @ normal_m.T
                    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
                else:
                    has_normals = False
                    n = np.zeros_like(p)
                idx = doc.accessor(prim["indices"])[:, 0].astype(np.int64) if "indices" in prim else np.arange(len(p))
                if mode == 4:
                    tris = idx.reshape(-1, 3)
                elif mode == 5:
                    tris = np.array([(idx[k], idx[k + 1], idx[k + 2]) if k % 2 == 0 else (idx[k + 1], idx[k], idx[k + 2])
                                     for k in range(len(idx) - 2)], np.int64).reshape(-1, 3)
                else:
                    tris = np.array([(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)], np.int64).reshape(-1, 3)
                base_index = len(positions)
                positions.extend(map(tuple, p))
                normals.extend(map(tuple, n))
                uvs.extend(map(tuple, t))
                for a, b, c in tris:
                    faces.append([(base_index + int(a), base_index + int(a), base_index + int(a)),
                                  (base_index + int(b), base_index + int(b), base_index + int(b)),
                                  (base_index + int(c), base_index + int(c), base_index + int(c))])
        for child in node.get("children", []):
            visit(child, m)

    for r in roots:
        visit(r, np.eye(4))
    if not faces:
        raise MeshError("the model holds no triangle")
    images.discard(None)
    if len(images) > 1:
        raise MeshError(f"the model uses {len(images)} base colour pictures: the game takes one; pack them first")
    picture = mime = None
    if images:
        img = g["images"][images.pop()]
        if "bufferView" in img:
            view = g["bufferViews"][img["bufferView"]]
            buf = buffers[view["buffer"]]
            picture = buf[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
        elif "uri" in img:
            picture = _buffer(img["uri"], folder)
        mime = img.get("mimeType") or ("image/png" if picture[:8] == b"\x89PNG\r\n\x1a\n" else
                                       "image/jpeg" if picture[:3] == b"\xff\xd8\xff" else "image/unknown")
    return {"positions": positions, "faces": faces, "uvs": uvs, "normals": normals if has_normals else [],
            "smooth": [1] * len(faces), "material": [None] * len(faces), "texture": None,
            "picture": picture, "mime": mime, "warnings": warnings, "axes": "y-up"}


def load_gltf(path, ignore_skin=False):
    with open(path, "rb") as fh:
        data = fh.read()
    return read_gltf(data, os.path.dirname(os.path.abspath(path)), ignore_skin)
