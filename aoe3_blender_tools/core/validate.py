# SPDX-License-Identifier: GPL-3.0-or-later
"""Game-ready checks for a low-poly building object.

Each check returns (level, message) with level ERROR, WARNING or INFO. The limits are the ones that
matter for a 2007 Direct3D 9 engine; the triangle budget is a project choice and can be changed.
"""
import bpy

from .checks import ERROR, INFO, WARNING, check as _check  # noqa: F401  (the levels, as before)


def mesh_data(obj):
    """The mesh dict of core/checks.py from a Blender object: its evaluated mesh (after the
    Triangulate modifier), UVs, materials and images."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    m = ev.to_mesh()
    try:
        verts = [tuple(v.co) for v in m.vertices]
        polys = [tuple(p.vertices) for p in m.polygons]
        uvs = None
        if m.uv_layers.active:
            data = m.uv_layers.active.data
            uvs = [[tuple(data[li].uv) for li in p.loop_indices] for p in m.polygons]
        mats = [mt for mt in obj.data.materials if mt]
        images = [(n.image.name, n.image.size[0], n.image.size[1]) for mt in mats if mt.node_tree
                  for n in mt.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        fp = obj.get("aoe3_footprint")
        return {"verts": verts, "polys": polys, "uvs": uvs, "uv_layers": len(m.uv_layers),
                "materials": len(mats), "images": images,
                "footprint": (fp[0], fp[1]) if fp is not None else None,
                "transform_ok": not (any(abs(s - 1.0) > 1e-6 for s in obj.scale)
                                     or any(abs(r) > 1e-6 for r in obj.rotation_euler))}
    finally:
        ev.to_mesh_clear()


def check(obj, tri_budget=6000, profile=None, prop=None):
    """Problems of a building object, as (level, message). With a calibration profile
    (core.profile) and the object's footprint, the budget is the one measured for buildings of
    its footprint class: a warning above their 90th percentile, an error above their maximum.

    prop: the group of the model profile a prop is held to (profile.prop_group(): the original
    game's map objects or treasures); the object is then a prop, not a building: a warning above
    their upper quartile of triangles, and a note of what they measure.

    The rules live in core/checks.py, which also checks a generated model without Blender."""
    if obj is None or obj.type != "MESH":
        return [(ERROR, "Select the building's mesh object.")]
    return _check(mesh_data(obj), tri_budget, profile, prop)
