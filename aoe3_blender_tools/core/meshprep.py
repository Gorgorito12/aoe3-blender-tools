# SPDX-License-Identifier: GPL-3.0-or-later
"""A mesh read from a file (core/objio.py, core/glbio.py) made ready for aoe3game/bundle.write:
Blender's axes (Z up, metres), the size asked for, standing on the ground at the middle of its plot,
cut into triangles, normals for every corner, and a vertex split wherever its texture coordinate
or its normal differs between corners (as blender_io.game_mesh splits them).

- up: "y" (OBJ and glTF's usual axis) or "z" (an OBJ written Z up).
- scale: a factor (a file in centimetres: 0.01), applied first; fit: the plot's longer side made
  this many metres instead (the height follows).
- turn: degrees round the vertical (0, 90, 180, 270), to face the model the way the game expects.
- normals: the file's own where every corner has one; else worked out from the smoothing groups
  (OBJ `s`), angle weighted; a face of group 0 is flat. `flat=True` makes every face flat.

Standard library plus numpy.
"""
import math

import numpy as np

from .gamemesh import triangulate
from .objio import MeshError


def _face_normal(p):
    n = np.cross(p[1] - p[0], p[2] - p[0])
    ln = np.linalg.norm(n)
    return n / ln if ln > 1e-12 else np.array([0.0, 0.0, 1.0])


def prepare(mesh, *, up="y", scale=1.0, fit=None, turn=0, flat=False):
    """Returns {"positions", "normals", "uvs", "triangles", "footprint": (w, d), "height",
    "warnings"}, ready for bundle.write (positions in metres, Z up; UVs with v up)."""
    if up not in ("y", "z"):
        raise MeshError(f"up must be y or z, not {up}")
    if turn % 90:
        raise MeshError("turn must be a multiple of 90 degrees")
    pos = np.asarray(mesh["positions"], np.float64).reshape(-1, 3)
    nrm = np.asarray(mesh["normals"], np.float64).reshape(-1, 3) if mesh.get("normals") else None
    if up == "y":                                    # (x, y, z) Y up -> (x, -z, y) Z up
        axes = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], np.float64)
    else:
        axes = np.eye(3)
    a = math.radians(turn)
    c, s = round(math.cos(a)), round(math.sin(a))
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64) @ axes
    pos = pos @ rot.T * float(scale)
    if nrm is not None:
        nrm = nrm @ rot.T
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    if fit:
        side = max(hi[0] - lo[0], hi[1] - lo[1])
        if side <= 1e-9:
            raise MeshError("the model has no width to fit")
        pos *= float(fit) / side
        lo, hi = pos.min(axis=0), pos.max(axis=0)
    pos -= np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    lo, hi = pos.min(axis=0), pos.max(axis=0)

    # triangles, each corner (vertex, uv, normal or None), and the face it came from
    tris, owner, warnings = [], [], list(mesh.get("warnings", []))
    degenerate = 0
    for fi, face in enumerate(mesh["faces"]):
        pts = [tuple(pos[v]) for v, _t, _n in face]
        for t in (triangulate(pts) if len(face) > 3 else [(0, 1, 2)]):
            corners = [face[i] for i in t]
            p = pos[[k[0] for k in corners]]
            if np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) < 1e-12:
                degenerate += 1
                continue
            tris.append(corners)
            owner.append(fi)
    if degenerate:
        warnings.append(f"{degenerate} triangles without area left out")
    if not tris:
        raise MeshError("no triangle with an area")

    have_normals = nrm is not None and len(nrm) and all(k[2] is not None for tri in tris for k in tri)
    face_n = [_face_normal(pos[[k[0] for k in tri]]) for tri in tris]
    corner_n = []
    if have_normals and not flat:
        for tri in tris:
            row = []
            for k in tri:
                n = nrm[k[2]]
                ln = np.linalg.norm(n)
                row.append(n / ln if ln > 1e-12 else None)
            corner_n.append(row)
    else:
        groups = mesh.get("smooth") or [0] * len(mesh["faces"])
        acc = {}
        for ti, tri in enumerate(tris):
            g = groups[owner[ti]]
            if flat or not g:
                continue
            p = pos[[k[0] for k in tri]]
            for i, k in enumerate(tri):
                u, v = p[(i + 1) % 3] - p[i], p[(i + 2) % 3] - p[i]
                cos = np.dot(u, v) / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-24)
                w = math.acos(max(-1.0, min(1.0, cos)))
                key = (k[0], g)
                acc[key] = acc.get(key, 0) + face_n[ti] * w
        for ti, tri in enumerate(tris):
            g = groups[owner[ti]]
            row = []
            for k in tri:
                n = acc.get((k[0], g)) if (g and not flat) else None
                ln = np.linalg.norm(n) if n is not None else 0
                row.append(n / ln if ln > 1e-12 else None)
            corner_n.append(row)

    uvs_in = mesh["uvs"]
    out_p, out_n, out_t, out_tri, index = [], [], [], [], {}
    for ti, tri in enumerate(tris):
        ids = []
        for i, k in enumerate(tri):
            n = corner_n[ti][i] if corner_n[ti][i] is not None else face_n[ti]
            uv = uvs_in[k[1]] if k[1] is not None else (0.0, 0.0)
            key = (k[0], round(uv[0], 6), round(uv[1], 6), round(n[0], 4), round(n[1], 4), round(n[2], 4))
            j = index.get(key)
            if j is None:
                j = index[key] = len(out_p)
                out_p.append(tuple(float(x) for x in pos[k[0]]))
                out_n.append(tuple(float(x) for x in n))
                out_t.append((float(uv[0]), float(uv[1])))
            ids.append(j)
        out_tri.append(tuple(ids))
    uv = np.asarray(out_t)
    if len(uv) and (uv.min() < -0.001 or uv.max() > 1.001):
        warnings.append("texture coordinates outside 0..1: the texture repeats there (the game "
                        "wraps it; a packed atlas should not)")
    return {"positions": out_p, "normals": out_n, "uvs": out_t, "triangles": out_tri,
            "footprint": (float(hi[0] - lo[0]), float(hi[1] - lo[1])), "height": float(hi[2] - lo[2]),
            "warnings": warnings}


def check_mesh(prep, texture_shape):
    """The mesh dict core/checks.check reads, for a prepared mesh."""
    h, w = texture_shape[:2]
    return {"verts": prep["positions"], "polys": prep["triangles"],
            "uvs": [[prep["uvs"][i] for i in t] for t in prep["triangles"]], "uv_layers": 1, "materials": 1,
            "images": [("imported_diffuse", int(w), int(h))], "footprint": prep["footprint"], "transform_ok": True}


def texture_rgba(mesh, rgba=None):
    """The model's picture as an RGBA array: `rgba` when the caller decoded it (a JPEG), else the
    PNG the file names or carries; a grey square when it has none (with a warning)."""
    from . import pngio
    if rgba is not None:
        arr = np.asarray(rgba, np.uint8)
    else:
        data = mesh.get("picture")
        if data is None and mesh.get("texture"):
            try:
                with open(mesh["texture"], "rb") as fh:
                    data = fh.read()
            except OSError:
                raise MeshError(f"the texture the model names is not there: {mesh['texture']}") from None
        if data is None:
            mesh.setdefault("warnings", []).append("the model names no texture: a grey one is used")
            return np.full((256, 256, 4), (128, 128, 128, 255), np.uint8)
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise MeshError("the texture is not a PNG: convert it to PNG (the studio's screen decodes a JPEG itself)")
        arr = np.asarray(pngio.read_png(data))
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.full(arr.shape[:2] + (1,), 255, np.uint8)], axis=2)
    elif arr.shape[2] == 2:
        arr = np.concatenate([np.repeat(arr[..., :1], 3, axis=2), arr[..., 1:]], axis=2)
    h, w = arr.shape[:2]
    if h & (h - 1) or w & (w - 1):
        mesh.setdefault("warnings", []).append(f"the texture is {w} x {h}, not a power of two: resampled")
        side = lambda n: 1 << max(2, min(11, round(math.log2(n))))      # noqa: E731
        arr = _resample(arr, side(h), side(w))
    return arr.astype(np.uint8)


def _resample(a, h, w):
    """Bilinear resampling to h x w."""
    H, W = a.shape[:2]
    ys = (np.arange(h) + 0.5) * H / h - 0.5
    xs = (np.arange(w) + 0.5) * W / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 1)
    y1, x1 = np.clip(y0 + 1, 0, H - 1), np.clip(x0 + 1, 0, W - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    a = a.astype(np.float32)
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return np.clip(top * (1 - fy) + bot * fy + 0.5, 0, 255).astype(np.uint8)


def load(path, ignore_skin=False):
    """A MeshIn from an .obj, .glb or .gltf, by its extension."""
    low = path.lower()
    if low.endswith(".obj"):
        from .objio import load_obj
        return load_obj(path)
    if low.endswith((".glb", ".gltf")):
        from .glbio import load_gltf
        return load_gltf(path, ignore_skin)
    raise MeshError("only .obj, .glb and .gltf are read")
