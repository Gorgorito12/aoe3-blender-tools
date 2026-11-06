# SPDX-License-Identifier: GPL-3.0-or-later
"""A building's collision shape: the game's Data\\PHYSICS\\<name>.shp, a plain Havok XML file.

The game's buildings use a list of boxes, each a shape and a transform around it, in the model
file's coordinates: `shape="<name>"` on a model reference in the anim file names one. The text
below follows the stock files to the line, down to the CRLFs and the space in a parameter's name.

Boxes come in metres in Blender's basis, (x0, x1, y0, y1, z0, z1), and are stored as the model is:
a point (x, y, z) goes to (-x, z, -y) * units (see gr2_write)."""

SDK = 'xmlversion="0.1" sdkversion="20300" buildnumber="20040517"'
RADIUS = 0.05       # the skin every stock box has


def stored(box, units_per_meter):
    """((half x, half y, half z), (centre x, y, z)) of a box in the model file's coordinates."""
    x0, x1, y0, y1, z0, z1 = (c * units_per_meter for c in box)
    half = ((x1 - x0) / 2, (z1 - z0) / 2, (y1 - y0) / 2)
    return half, (0.0 - (x0 + x1) / 2, (z0 + z1) / 2, 0.0 - (y0 + y1) / 2)


def _param(name, kind, value):
    return f'\t\t<hkparam name="{name}" type="{kind}">{value}</hkparam>\r\n'


def shape_xml(boxes, units_per_meter):
    """The text of a .shp holding these boxes. Raises ValueError on a box with no size."""
    if not boxes:
        raise ValueError("a collision shape needs at least one box")
    out = ['<?xml version="1.0" encoding="UTF-8" ?>\r\n', f"<hke {SDK}>\r\n"]
    names = []
    for i, box in enumerate(boxes, 1):
        (hx, hy, hz), (cx, cy, cz) = stored(box, units_per_meter)
        if min(hx, hy, hz) <= 0.0:
            raise ValueError(f"box {i} has no size: {box}")
        name = f"Box{i:02d}"
        out += [f'\t<hkobject name="{name}" type="hkBoxShape">\r\n',
                _param("userData", "hkTypeInt32", 1), _param("radius", "hkTypeReal", f"{RADIUS:.5f}"),
                _param("halfExtents", "hkTypeVector4", f"{hx:.6g} {hy:.6g} {hz:.6g} 0"), "\t</hkobject>\r\n",
                f'\t<hkobject name="unnamed_{name}" type="hkTransformShape">\r\n',
                _param("userData", "hkTypeInt32", 0), _param("childShape", "hkTypePointer", name),
                _param("transform", "hkTypeTransform",
                       f"(1.0 0.0 0.0)(0.0 1.0 0.0)(0.0 0.0 1.0)({cx:.6g} {cy:.6g} {cz:.6g})"),
                "\t</hkobject>\r\n"]
        names.append(f"unnamed_{name}")
    out += ['\t<hkobject name="unnamed_shapeList" type="hkListShape">\r\n', _param("userData", "hkTypeInt32", 6),
            _param("childShapes", "hkTypeArray", "( " + " ".join(names) + " )"),
            _param("childShapeFilterInfo ", "hkTypeArray", "(" + "0 " * len(names) + ")"),
            "\t</hkobject>\r\n", "</hke>\r\n"]
    return "".join(out)


def extent(boxes, units_per_meter):
    """(width, depth, height) in game units of what the boxes cover."""
    w = max(b[1] for b in boxes) - min(b[0] for b in boxes)
    d = max(b[3] for b in boxes) - min(b[2] for b in boxes)
    h = max(b[5] for b in boxes) - min(b[4] for b in boxes)
    return w * units_per_meter, d * units_per_meter, h * units_per_meter
