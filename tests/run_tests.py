# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless tests. Run with the bpy module (see README):

    python tests/run_tests.py

or with Blender: blender -b --factory-startup -P tests/run_tests.py
Exits with status 1 when a test fails.
"""
import os
import random
import sys
import tempfile
import traceback

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import aoe3_blender_tools as addon  # noqa: E402
from aoe3_blender_tools.core import blender_io, building, paint, validate  # noqa: E402

FAILED = []


def test(fn):
    def run():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            fn()
            print(f"ok    {fn.__name__}")
        except Exception:
            FAILED.append(fn.__name__)
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    run.__name__ = fn.__name__
    return run


def problems(res):
    return [(lv, m) for lv, m in res if lv in (validate.ERROR, validate.WARNING)]


@test
def presets_generate_and_pass_checks():
    s = bpy.context.scene.aoe3_building
    for key in building.PRESETS:
        s.preset = key
        assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
        assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
        obj = bpy.context.active_object
        assert obj is not None and obj.name == building.PRESETS[key].name, obj
        res = validate.check(obj)
        assert not problems(res), (key, problems(res))
        tris, _ = blender_io.triangle_count(obj)
        assert 50 < tris < 4000, (key, tris)


@test
def parameter_sweep_has_no_overlaps_or_errors():
    rng = random.Random(7)
    for i in range(40):
        p = building.BuildingParams(
            name=f"Sweep{i}", width=rng.uniform(6, 24), depth=rng.uniform(5, 16), storeys=rng.randint(1, 3),
            plinth=rng.choice([0.4, 0.8, 1.2]), roof_pitch=rng.uniform(0.3, 0.9),
            portico=rng.random() < 0.7, columns=rng.choice([2, 4, 6, 8]),
            column_spacing=rng.uniform(1.4, 2.4), cupola=rng.random() < 0.5, chimneys=rng.randint(0, 2),
            side_bays=rng.choice([0, 0, 2, 3, 5]), detail=rng.choice(["LOW", "MEDIUM"]), texture_size=512,
            back_portico=rng.choice(["NONE", "BOW"]), bow_radius=rng.uniform(1.5, 5.0),
            bow_columns=rng.randint(2, 8), wings=rng.random() < 0.4, wing_gap=rng.uniform(2.0, 7.0),
            wing_width=rng.uniform(3.0, 9.0), wing_depth=rng.uniform(3.0, 8.0), flagpole=rng.random() < 0.3,
            shutters=rng.random() < 0.5)
        model = building.build(p)
        obj = blender_io.create_object(model, paint.paint(model))
        res = validate.check(obj)
        assert not problems(res), (i, p, problems(res))


@test
def medium_detail_presets_pass_checks():
    for key, prm in building.PRESETS.items():
        p = building.BuildingParams(**{**prm.__dict__, "detail": "MEDIUM"})
        model = building.build(p)
        obj = blender_io.create_object(model, paint.paint(model))
        res = validate.check(obj)
        assert not problems(res), (key, problems(res))
        low = sum(len(f.pts) - 2 for f in building.build(building.BuildingParams(**{**prm.__dict__, "detail": "LOW"})).faces)
        tris, _ = blender_io.triangle_count(obj)
        assert tris > 2 * low, (key, low, tris)
    wh = building.build(building.BuildingParams(**{**building.PRESETS["WHITE_HOUSE"].__dict__, "detail": "MEDIUM"}))
    tris = sum(len(f.pts) - 2 for f in wh.faces)
    assert 1000 <= tris <= 1400, tris
    # the balustrade runs on all four sides (the side runs are long in y and thin in x)
    for axis in (0, 1):
        sides = [f for f in wh.faces if f.region == "balus" and abs(building.newell(f.pts)[axis]) > 0.9]
        assert len(sides) >= 4, (axis, len(sides))


@test
def wall_triangulation_covers_the_wall_exactly():
    holes = [(1.0, 0.8, 2.0, 2.7), (1.0, 3.65, 2.0, 5.3), (4.3, 0.0, 5.7, 2.75), (4.5, 3.65, 5.5, 5.3)]
    tris = building.wall_triangles(8.0, 6.2, holes)
    assert tris is not None
    area = sum(abs(building._area2(*t)) / 2 for t in tris)
    assert abs(area - (8.0 * 6.2 - sum((h[2] - h[0]) * (h[3] - h[1]) for h in holes))) < 1e-6
    for t in tris:                       # no triangle inside an opening
        cx, cy = sum(q[0] for q in t) / 3, sum(q[1] for q in t) / 3
        assert not any(h[0] < cx < h[2] and h[1] < cy < h[3] for h in holes), t
    # an opening wider than the one below it cannot be slit: the caller falls back to a grid
    assert building.wall_triangles(8.0, 6.2, [(1.0, 0.8, 2.0, 2.7), (0.5, 3.65, 2.5, 5.3)]) is None


@test
def regenerating_replaces_the_object():
    s = bpy.context.scene.aoe3_building
    bpy.ops.aoe3.generate_building()
    bpy.ops.aoe3.generate_building()
    names = [o.name for o in bpy.data.objects if o.type == "MESH"]
    assert names == [s.name], names
    assert len([o for o in bpy.data.objects if o.name.startswith("flag_attach")]) == 1


@test
def export_and_reimport():
    bpy.ops.aoe3.generate_building()
    obj = bpy.context.active_object
    tris, _ = blender_io.triangle_count(obj)
    with tempfile.TemporaryDirectory() as tmp:
        paths = blender_io.export(obj, tmp)
        for ext in (".glb", ".fbx", ".obj", ".mtl", "_diffuse.png", "_stats.txt"):
            assert any(pth.endswith(ext) and os.path.getsize(pth) > 0 for pth in paths), ext
        png = next(pth for pth in paths if pth.endswith(".png"))
        fbx = next(pth for pth in paths if pth.endswith(".fbx"))
        assert os.path.getsize(fbx) > 0.5 * os.path.getsize(png), "FBX has no embedded texture"
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=next(pth for pth in paths if pth.endswith(".glb")))
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        assert len(meshes) == 1
        m = meshes[0].data
        m.calc_loop_triangles()
        assert len(m.loop_triangles) == tris, (len(m.loop_triangles), tris)
        assert len(m.uv_layers) == 1
        assert any(o.name.startswith("flag_attach") for o in bpy.data.objects)
        assert any(img.size[0] == 1024 for img in bpy.data.images)


@test
def checks_catch_known_problems():
    import bmesh
    # two overlapping coplanar quads, an off-centre object and a non power-of-two texture
    bm = bmesh.new()
    for x0 in (0.0, 0.5):
        vs = [bm.verts.new(c) for c in ((x0, 0, 1), (x0 + 1, 0, 1), (x0 + 1, 1, 1), (x0, 1, 1))]
        bm.faces.new(vs)
    bm.loops.layers.uv.new("UVMap")
    mesh = bpy.data.meshes.new("Bad")
    bm.to_mesh(mesh)
    obj = bpy.data.objects.new("Bad", mesh)
    bpy.context.scene.collection.objects.link(obj)
    img = bpy.data.images.new("bad", 300, 200)
    mat = bpy.data.materials.new("bad")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    mat.node_tree.nodes.new("ShaderNodeTexImage").image = img
    mesh.materials.append(mat)
    res = validate.check(obj)
    text = " | ".join(m for _, m in res)
    assert any(lv == validate.ERROR and "coplanar" in m for lv, m in res), text
    assert any(lv == validate.ERROR and "powers of two" in m for lv, m in res), text
    assert any(lv == validate.WARNING and "Footprint centre" in m for lv, m in res), text
    assert any(lv == validate.WARNING and "z = 1.00" in m for lv, m in res), text


@test
def atlas_and_texture_sizes():
    for size in (512, 1024, 2048):
        model = building.build(building.BuildingParams(texture_size=size))
        assert model.atlas.size == 2 * size
        img = paint.paint(model)
        assert img.shape == (size, size, 3), img.shape
        for f in model.faces:                      # every UV lands inside its region
            for u, v in f.uvs:
                model.atlas.uv(f.region, u, v)


@test
def game_export_writes_the_bundle():
    import json
    import xml.etree.ElementTree as ET
    from aoe3_blender_tools.aoe3game import ddt, gr2
    s = bpy.context.scene.aoe3_building
    s.preset = "MANSION"
    assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    tris, _ = blender_io.triangle_count(obj)
    with tempfile.TemporaryDirectory() as tmp:
        s.game_dir, s.game_prefix, s.use_profile = tmp, "mod", False
        assert bpy.ops.aoe3.export_game() == {"FINISHED"}
        with open(os.path.join(tmp, "bundle.json"), encoding="utf-8") as f:
            desc = json.load(f)
        low = obj.name.lower()
        base = os.path.join(tmp, "art", "mod", "buildings", low, low)
        st = gr2.load(base + ".gr2").stats()
        assert st["tris"] == tris, (st["tris"], tris)
        names = [b["name"] for b in st["bones"]]
        assert names[:2] == ["bone_main", obj.name], names
        with open(base + ".ddt", "rb") as f:
            h = ddt.read_header(f.read())
        assert (h.width, h.height) == (int(s.texture_size), int(s.texture_size))
        root = ET.parse(base + ".xml").getroot()
        assert root.tag == "animfile"
        assert desc["unit"]["AnimFile"] == "\\".join(["mod", "buildings", low, low + ".xml"]), desc["unit"]
        assert float(desc["unit"]["ObstructionRadiusX"]) > 0


@test
def check_uses_profile_budget():
    from aoe3_blender_tools.core import profile
    prof = profile.Profile({"classes": {"8x8": {
        "count": 5, "tris": {"min": 50, "median": 100, "p90": 200, "max": 300},
        "obstruction_over_half_side": {"median": 0.85}}}})
    s = bpy.context.scene.aoe3_building
    s.preset = "WHITE_HOUSE"
    assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    res = validate.check(obj, profile=prof)
    assert any(lv == validate.ERROR and "class 8x8" in m for lv, m in res), res
    assert not any("class 8x8" in m for lv, m in validate.check(obj) if lv != validate.INFO)


@test
def player_colour_marks_the_string_courses():
    import dataclasses
    p = dataclasses.replace(building.PRESETS["WHITE_HOUSE"], texture_size=512)
    plain = paint.paint_rgba(building.build(p))
    assert plain.shape == (512, 512, 4) and plain[..., 3].min() == 255
    p = dataclasses.replace(p, player_colour=True, shutters=True)
    model = building.build(p)
    rgba = paint.paint_rgba(model)
    share = (rgba[..., 3] < 128).mean()
    assert 0.005 < share < 0.06, share          # thin bands, as the game's own textures
    assert (rgba[..., :3] == paint.paint(model)).all()
    obj = blender_io.create_object(model, rgba)
    assert blender_io.texture_rgba(obj)[..., 3].min() < 128     # the mask survives in Blender


def main():
    addon.register()
    try:
        for t in (presets_generate_and_pass_checks, parameter_sweep_has_no_overlaps_or_errors,
                  medium_detail_presets_pass_checks, wall_triangulation_covers_the_wall_exactly,
                  regenerating_replaces_the_object, export_and_reimport, checks_catch_known_problems,
                  atlas_and_texture_sizes, game_export_writes_the_bundle, check_uses_profile_budget,
                  player_colour_marks_the_string_courses):
            t()
    finally:
        addon.unregister()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all tests passed'}")
    sys.exit(1 if FAILED else 0)


main()
