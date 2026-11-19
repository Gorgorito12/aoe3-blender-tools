# SPDX-License-Identifier: GPL-3.0-or-later
"""Wavefront OBJ (and its MTL) as a static mesh to convert for the game, without Blender.

Read: `v`, `vt`, `vn`, `f` (triangles, quads and n-gons, cut as core/gamemesh.py cuts them;
negative indices; the four corner forms), `s` (smoothing groups), `usemtl`, `mtllib`, `o`/`g`
(merged), a line continued with a backslash. From the MTL: `newmtl` and `map_Kd` (several
materials are fine when they name the same picture). Refused, with the reason: no texture
coordinates, two different pictures (pack them into one first), `map_Kd` options that move or
scale the picture, free-form geometry (`curv`, `surf`, `cstype`). Lines and points (`l`, `p`)
are left out with a warning. Standard library only.

The result (`MeshIn`, a dict) is in the file's own axes and units; core/meshprep.py turns it into
the game's.
"""
import os
import re


class MeshError(ValueError):
    pass


def _index(token, count, what):
    try:
        k = int(token)
    except ValueError:
        raise MeshError(f"a face names a {what} that is not a number: {token}") from None
    k = k - 1 if k > 0 else count + k
    if not 0 <= k < count:
        raise MeshError(f"a face names {what} {token}, which the file does not have ({count})")
    return k


def read_mtl(text):
    """{material: picture path as written (or None)}, and the warnings."""
    out, warnings, current = {}, [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition(" ")
        key = key.lower()
        if key == "newmtl":
            current = rest.strip()
            out[current] = None
        elif key == "map_kd" and current is not None:
            parts = rest.split()
            # options before the file name: -s/-o (scale, offset) other than identity move the picture
            path_parts, i = [], 0
            while i < len(parts):
                p = parts[i]
                if p.startswith("-") and p.lower() in ("-s", "-o", "-t"):
                    vals = parts[i + 1:i + 4]
                    try:
                        nums = [float(v) for v in vals]
                    except ValueError:
                        nums = []
                    identity = [1.0, 1.0, 1.0] if p.lower() == "-s" else [0.0, 0.0, 0.0]
                    if nums[:len(identity)] != identity[:len(nums)]:
                        raise MeshError(f"map_Kd {p} {' '.join(vals)}: the picture is moved or scaled; "
                                        "bake it into the texture coordinates first")
                    i += 4
                    continue
                if p.startswith("-") and i + 1 < len(parts):
                    warnings.append(f"map_Kd option {p} left out")
                    i += 2
                    continue
                path_parts = parts[i:]
                break
            out[current] = " ".join(path_parts) or None
    return out, warnings


def read_obj(text, mtl_texts=None):
    """The mesh of an OBJ's text. `mtl_texts`: {mtllib name: its text} (what the caller found).

    Returns {"positions": [(x, y, z)], "faces": [[(v, vt, vn), ...]], "uvs": [(u, v)],
    "normals": [(x, y, z)], "smooth": [group per face], "material": [name per face],
    "texture": picture path or None, "warnings": [...]}"""
    positions, uvs, normals = [], [], []
    faces, smooth, material = [], [], []
    group, current, libs, warnings = 0, None, [], []
    lines = text.replace("\\\r\n", " ").replace("\\\n", " ").splitlines()
    for n, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, rest = line.partition(" ")
        key = key.lower()
        if key == "v":
            vals = rest.split()
            try:
                positions.append(tuple(float(v) for v in vals[:3]))
            except ValueError:
                raise MeshError(f"line {n}: a vertex that is not three numbers") from None
        elif key == "vt":
            vals = rest.split()
            try:
                uvs.append((float(vals[0]), float(vals[1]) if len(vals) > 1 else 0.0))
            except (ValueError, IndexError):
                raise MeshError(f"line {n}: a texture coordinate that is not numbers") from None
        elif key == "vn":
            try:
                normals.append(tuple(float(v) for v in rest.split()[:3]))
            except ValueError:
                raise MeshError(f"line {n}: a normal that is not three numbers") from None
        elif key == "f":
            corners = []
            for tok in rest.split():
                parts = tok.split("/")
                v = _index(parts[0], len(positions), "vertex")
                vt = _index(parts[1], len(uvs), "texture coordinate") if len(parts) > 1 and parts[1] else None
                vn = _index(parts[2], len(normals), "normal") if len(parts) > 2 and parts[2] else None
                corners.append((v, vt, vn))
            if len(corners) < 3:
                warnings.append(f"line {n}: a face of {len(corners)} corners left out")
                continue
            faces.append(corners)
            smooth.append(group)
            material.append(current)
        elif key == "s":
            g = rest.strip().lower()
            group = 0 if g in ("off", "0", "") else (int(g) if g.isdigit() else 1)
        elif key == "usemtl":
            current = rest.strip()
        elif key == "mtllib":
            libs += rest.split()
        elif key in ("o", "g"):
            continue
        elif key in ("l", "p"):
            warnings.append(f"line {n}: {key} elements (lines, points) left out")
        elif key in ("curv", "curv2", "surf", "cstype", "deg", "bmat", "step", "parm", "trim", "hole"):
            raise MeshError(f"line {n}: free-form geometry ({key}) cannot be converted: make it a mesh first")
    if not faces:
        raise MeshError("the file holds no face")
    if any(vt is None for f in faces for _v, vt, _n in f):
        raise MeshError("some faces have no texture coordinates (vt): unwrap the model first")
    pictures = {}
    for name, text_ in (mtl_texts or {}).items():
        mats, w = read_mtl(text_)
        warnings += w
        pictures.update(mats)
    used = {material[i] for i in range(len(faces))}
    textures = sorted({pictures.get(m) for m in used if pictures.get(m)})
    if len(textures) > 1:
        raise MeshError(f"the model uses {len(textures)} pictures ({', '.join(textures)}): the game takes one; "
                        "pack them into one texture first")
    missing_libs = [lib for lib in libs if lib not in (mtl_texts or {})]
    if missing_libs:
        warnings.append(f"material file not found: {', '.join(missing_libs)}")
    return {"positions": positions, "faces": faces, "uvs": uvs, "normals": normals, "smooth": smooth,
            "material": material, "texture": textures[0] if textures else None, "warnings": warnings,
            "axes": "y-up"}


def load_obj(path):
    """read_obj of a file, its MTL files read from beside it; the texture path made absolute."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    folder = os.path.dirname(os.path.abspath(path))
    mtls = {}
    for m in re.finditer(r"^\s*mtllib\s+(.+)$", text, re.M):
        for name in m.group(1).split():
            p = os.path.join(folder, name)
            if os.path.isfile(p) and os.path.commonpath([os.path.abspath(p), folder]) == folder:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    mtls[name] = fh.read()
    mesh = read_obj(text, mtls)
    if mesh["texture"]:
        tex = os.path.normpath(os.path.join(folder, mesh["texture"].replace("\\", os.sep)))
        mesh["texture"] = tex
    return mesh
