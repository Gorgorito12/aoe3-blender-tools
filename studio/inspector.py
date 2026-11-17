# SPDX-License-Identifier: GPL-3.0-or-later
"""Looks inside a game file, read only: a texture (.ddt) as a picture with its header, a Granny
model (.gr2, uncompressed) as a mesh with its bones and textures, a compiled XML (.xmb) as text, a
.bar archive as the list of what it holds (and any file inside it the same way)."""
import base64
import os

from . import use_core

use_core()
import bar  # noqa: E402  (tools/)
import xmbedit  # noqa: E402
from aoe3game import ddt, gr2, gr2_mesh  # noqa: E402
from core import paint  # noqa: E402

TEXT = (".xml", ".txt", ".particle", ".tactics", ".impacteffect", ".dmg", ".cfg", ".con", ".xs", ".anim",
        ".lgt", ".md", ".json", ".csv", ".ini", ".ui", ".log")
MAX_TEXT = 2 * 1024 * 1024
MAX_FILE = 256 * 1024 * 1024


class InspectError(ValueError):
    pass


def _data(path, entry):
    if entry is None:
        if not os.path.isfile(path):
            raise InspectError(f"no such file: {path}")
        if os.path.getsize(path) > MAX_FILE:
            raise InspectError("the file is too large to look inside")
        with open(path, "rb") as fh:
            return os.path.basename(path), fh.read()
    for name, offset, size in bar.read_entries(path):
        if name == entry:
            if size > MAX_FILE:
                raise InspectError("the file is too large to look inside")
            with open(path, "rb") as fh:
                fh.seek(offset)
                return name, fh.read(size)
    raise InspectError(f"{entry} is not in {os.path.basename(path)}")


def inspect(path, entry=None):
    if entry is None and path.lower().endswith(".bar"):
        try:
            entries = bar.read_entries(path)
        except (ValueError, OSError) as e:
            raise InspectError(str(e)) from None
        return {"kind": "bar", "name": os.path.basename(path), "entries": [[n, s] for n, _o, s in entries]}
    name, data = _data(path, entry)
    low = name.lower()
    if data[:4] == ddt.MAGIC:
        return _ddt(name, data)
    if low.endswith(".gr2") or data[:16] == gr2.MAGIC:
        return _gr2(name, data, os.path.dirname(path) if entry is None else None)
    if xmbedit.is_compressed(data) or data[:2] == b"X1":
        elems, attrs, root = xmbedit.parse(xmbedit.decode(data))
        return {"kind": "text", "name": name, "format": "xmb", "text": xmbedit.to_xml(elems, attrs, root)[:MAX_TEXT]}
    if low.endswith(TEXT) or _looks_like_text(data):
        return {"kind": "text", "name": name, "format": os.path.splitext(low)[1].lstrip("."),
                "text": data[:MAX_TEXT].decode("utf-8", "replace").lstrip("﻿")}
    return {"kind": "binary", "name": name, "size": len(data), "head": data[:256].hex(" ")}


def _looks_like_text(data):
    head = data[:4096]
    if not head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return head[:2] in (b"\xff\xfe", b"\xfe\xff")
    return b"\0" not in head


def _png(rgba):
    return "data:image/png;base64," + base64.b64encode(paint.png_bytes(rgba, level=3)).decode("ascii")


def _ddt(name, data):
    h = ddt.read_header(data)
    try:
        rgba = ddt.decode(data, 0)
    except Exception as e:                    # a format the decoder does not know
        return {"kind": "ddt", "name": name, "header": h.describe(), "error": str(e)}
    import numpy as np
    alpha = rgba[:, :, 3]
    out = {"kind": "ddt", "name": name, "header": h.describe(), "width": h.width, "height": h.height,
           "levels": len(h.levels), "image": _png(rgba),
           "alpha_partial": float((alpha < 255).mean()), "alpha_zero": float((alpha == 0).mean())}
    if out["alpha_partial"] > 0:
        out["alpha"] = _png(np.repeat(alpha[:, :, None], 3, axis=2))
    return out


def _texture_beside(folder, names):
    """The model's diffuse texture when it lies beside the model (not its bump map)."""
    for n in names:
        if not n:
            continue
        base = os.path.splitext(os.path.basename(n.replace("\\", "/")))[0]
        if base.lower().endswith("_b"):
            continue
        p = os.path.join(folder, base + ".ddt")
        if os.path.isfile(p):
            try:
                with open(p, "rb") as fh:
                    return os.path.basename(p), _png(ddt.decode(fh.read(), 0))
            except Exception:
                return None
    return None


def mesh_of(model):
    """A model read by gr2_mesh.read as one mesh for the page's 3D view, with its numbers; None
    when it holds no mesh this reader can show."""
    import numpy as np
    pos, uvs, idx, base = [], [], [], 0
    meshes = []
    for m in model["meshes"]:
        p = np.asarray(m["positions"], np.float32).reshape(-1, 3)
        u = m["uvs"] if m["uvs"] is not None else np.zeros((len(p), 2), np.float32)
        t = np.asarray(m["triangles"], np.int64).reshape(-1, 3) + base
        pos.append(p)
        uvs.append(np.asarray(u, np.float32))
        idx.append(t)
        base += len(p)
        meshes.append({"name": m["name"], "vertices": int(len(p)), "triangles": int(len(t)),
                       "bones": list(m["bound_to"][:20])})
    if not pos:
        return None
    P, U, T = np.concatenate(pos), np.concatenate(uvs), np.concatenate(idx)
    lo, hi = P.min(0), P.max(0)
    return {"mesh": {"positions": [round(float(c), 4) for c in P.ravel()],
                     "uvs": [round(float(c), 5) for c in U.ravel()], "indices": [int(i) for i in T.ravel()]},
            "attach": {b[0]: list(b[2]) for b in model["bones"][:400]},
            "meshes": meshes, "triangles": int(len(T)), "vertices": int(len(P)), "bones": len(model["bones"]),
            "size": [round(float(v), 3) for v in hi - lo]}


def _gr2(name, data, folder=None):
    try:
        model = gr2_mesh.read(data)
    except gr2.Compressed as e:
        return {"kind": "gr2", "name": name, "error": f"{e}. Use Uncompressed models, or give the Granny bridge "
                "in Settings to the tools that read compressed models."}
    except (gr2.Gr2Error, ValueError) as e:
        return {"kind": "gr2", "name": name, "error": str(e)}
    shown = mesh_of(model)
    if shown is None:
        return {"kind": "gr2", "name": name, "error": "no mesh this reader can show (an animation?)",
                "bones": len(model["bones"]), "skipped": model["skipped"]}
    beside = _texture_beside(folder, model["textures"]) if folder else None
    return dict(shown, kind="gr2", name=name, texture=beside[1] if beside else None,
                texture_name=beside[0] if beside else None, textures=model["textures"],
                skipped=model["skipped"], units_per_meter=model["units_per_meter"])
