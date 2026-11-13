# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless tests. Run with the bpy module (see README):

    python tests/run_tests.py

or with Blender: blender -b --factory-startup -P tests/run_tests.py
Exits with status 1 when a test fails.
"""
import json
import os
import random
import sys
import tempfile
import traceback

import bpy  # noqa: I001  (bpy first: it makes bmesh and mathutils importable)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import aoe3_blender_tools as addon  # noqa: E402
from aoe3_blender_tools.core import blender_io, building, comfy, paint, validate  # noqa: E402

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
        ref = building.reference(building.PRESETS[key])
        cap = 4000                                 # a sized building: the p90 of its profile class
        if ref is not None:
            from aoe3_blender_tools.core import profile
            cls = profile.load().classes.get(f"{2 * ref[0]:g}x{2 * ref[0]:g}")
            cap = cls["tris"]["p90"] if cls else cap
        floor = 20 if building.PRESETS[key].style == "PROP" else 50   # a map object can be one pole
        assert floor < tris <= cap, (key, tris, cap)


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
        if prm.style != "PROP":                    # a prop's low model only drops its small cargo
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


@test
def icon_and_portrait_render():
    from aoe3_blender_tools.aoe3game import icons
    from aoe3_blender_tools.core import render
    s = bpy.context.scene.aoe3_building
    s.preset = "MANSION"
    assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    obj = bpy.context.view_layer.objects.active
    engine = bpy.context.scene.render.engine
    icon, portrait = render.icon_and_portrait(obj)
    assert icon.shape == (64, 64, 3) and portrait.shape == (128, 128, 3)
    assert tuple(icon[0, 0]) == icons.FRAME_DARK
    centre = portrait[40:88, 40:88].astype(int)
    away = abs(centre - icons.BACK_CENTRE).mean()
    assert away > 15, away                               # the building, not the empty background
    assert bpy.context.scene.render.engine == engine     # the scene's settings are restored
    assert not any(o.name.startswith("aoe3_icon_camera") for o in bpy.data.objects)


@test
def game_variants_lowpoly_and_damaged():
    import dataclasses
    p = dataclasses.replace(building.PRESETS["WHITE_HOUSE"], detail="MEDIUM", texture_size=512,
                            player_colour=True)
    model = building.build(p)
    obj = blender_io.create_object(model, paint.paint_rgba(model))
    before = {o.name for o in bpy.data.objects}
    v = blender_io.game_variants(obj)
    assert {o.name for o in bpy.data.objects} == before          # the temporary object is gone
    tris, _ = blender_io.triangle_count(obj)
    assert len(v["damaged"]["triangles"]) == tris
    assert 200 < len(v["lowpoly"]["triangles"]) < tris / 2, len(v["lowpoly"]["triangles"])
    intact = blender_io.texture_rgba(obj)
    dmg = v["damaged"]["texture_rgba"]
    assert (dmg[..., 3] == intact[..., 3]).all()                 # the player colour mask is kept
    assert (dmg[..., :3] < intact[..., :3]).mean() > 0.02        # soot, slates, cracks
    assert v["lowpoly"]["texture_rgba"][..., 3].min() < 128      # the LOW model keeps its mask
    assert blender_io.game_variants(obj, lowpoly=False, damaged=False) == {}


@test
def deploy_from_blender_and_undo():
    import hashlib
    s = bpy.context.scene.aoe3_building
    s.preset = "MANSION"
    assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    with tempfile.TemporaryDirectory() as tmp:
        inst = os.path.join(tmp, "Game")
        os.makedirs(os.path.join(inst, "art"))
        os.makedirs(os.path.join(inst, "data"))
        proto = ("<Proto>\r\n\t<Unit id=\"1\" name=\"House\">\r\n\t\t<DBID>15</DBID>\r\n"
                 "\t\t<UnitType>Building</UnitType>\r\n\t</Unit>\r\n"
                 "\t<Unit id=\"2\" name=\"Settler\">\r\n\t\t<DBID>16</DBID>\r\n\t</Unit>\r\n</Proto>\r\n")
        with open(os.path.join(inst, "data", "protoy.xml"), "w", encoding="utf-8", newline="") as f:
            f.write(proto)
        with open(os.path.join(inst, "data", "stringtabley.xml"), "wb") as f:
            f.write("<StringTable><Language name='English'>\r\n</Language></StringTable>".encode("utf-16"))
        before = hashlib.sha256(open(os.path.join(inst, "data", "protoy.xml"), "rb").read()).hexdigest()
        s.game_dir, s.game_install, s.use_profile = os.path.join(tmp, "bundle"), inst, False
        s.game_icons = False
        assert bpy.ops.aoe3.export_game() == {"FINISHED"}
        assert bpy.ops.aoe3.deploy_game() == {"FINISHED"}
        text = open(os.path.join(inst, "data", "protoy.xml"), encoding="utf-8").read()
        assert 'name="Mansion"' in text and ">Mansion</Train>" in text, text[-400:]
        assert bpy.ops.aoe3.undo_deploy() == {"FINISHED"}
        after = hashlib.sha256(open(os.path.join(inst, "data", "protoy.xml"), "rb").read()).hexdigest()
        assert after == before
        s.game_install = r"C:\Program Files (x86)\Steam\steamapps\common\Game"
        try:
            bpy.ops.aoe3.deploy_game()
            refused = False
        except RuntimeError:
            refused = True
        assert refused or not os.path.exists(s.game_install)


@test
def square_hipped_roof_builds():
    # a square block and square wings: the hipped roofs become pyramids (no ridge of length 0)
    for detail in ("LOW", "MEDIUM"):
        p = building.BuildingParams(name="Square", width=10.0, depth=10.0, portico=False, cupola=False,
                                    chimneys=2, wings=True, wing_width=5.0, wing_depth=5.0, detail=detail,
                                    texture_size=512)
        model = building.build(p)
        obj = blender_io.create_object(model, paint.paint(model))
        res = validate.check(obj)
        assert not problems(res), (detail, problems(res))


def kit_model(medium):
    """A free Builder with every new piece of the kit, on separate plots."""
    from aoe3_blender_tools.core import kit
    b = kit.Builder(256, medium)
    (rw, rh), (gw, gh) = kit.gable_roof_size(4.0, 3.0, 0.6, "X", overhang=0.3)
    for name, w, h in (("wall", 8.0, 4.0), ("roof", max(rw, 7.0), max(rh, 3.0)), ("gable", gw, gh),
                       ("dormer", 1.2, 1.0), ("brick", 4.0, 3.0), ("white", 2.2, 1.6), ("post", 2.0, 3.0),
                       ("arch", 6.0, kit.arcade_front_h(3.0, 3, 10.0, 16.0, 0.25, "ARCH", medium)),
                       ("slab", 2.0, 0.8), ("rail", 2.0, 0.9), ("soffit", 4.0, 0.4), ("ends", 0.4, 0.4),
                       ("bell", 2.0, 2.7)):
        b.region(name, w, h)
    b.pack()
    # a house: four walls, a gable roof with a ridge cap, a dormer on each slope, a chimney, a balcony
    for origin, ua, length in (((-4.0, -3.0, 0.0), (1.0, 0.0, 0.0), 8.0), ((4.0, 3.0, 0.0), (-1.0, 0.0, 0.0), 8.0),
                               ((-4.0, 3.0, 0.0), (0.0, -1.0, 0.0), 6.0), ((4.0, -3.0, 0.0), (0.0, 1.0, 0.0), 6.0)):
        b.flat_wall(origin, ua, length, 3.0, "wall")
    rz = b.gable_roof(0.0, 0.0, 4.0, 3.0, 3.0, 0.6, "X", "roof", gable_region="gable", overhang=0.3)
    b.ridge_cap((-4.3, 0.0), (4.3, 0.0), rz, "roof")
    for side, x in ((-1, -1.5), (1, 1.5)):
        b.dormer(x, 0.0, 3.0, 3.0, 0.6, side, 0.8, 1.2, 1.0, wall_region="dormer", roof_region="roof",
                 cheek_region="white")
    foot = kit.gable_roof_z(3.0, 1.2, 0.0, 0.0, 4.0, 3.0, 3.0, 0.6) - 0.4
    b.chimney(3.0, 1.2, foot, rz + 0.8)
    b.balcony(-1.0, 1.0, -3.0, 1.5, 0.8, "slab", "rail")
    # an arcade under a lean-to roof against a wall
    b.flat_wall((10.0, -3.0, 0.0), (1.0, 0.0, 0.0), 6.0, 4.0, "wall")
    b.arcade(10.0, 16.0, -5.4, 0.0, 3.0, 3, 0.4, 0.25, "post", "arch")
    b.shed_roof((10.0, -3.0, 0.0), (1.0, 0.0, 0.0), 6.0, 2.6, 3.6, 0.2, "roof")
    # a bell gable, and a jetty on a wall
    apex = b.bell_gable(20.0, 0.0, 0.0, 2.0, 2.0, 0.3, "bell", side_region="white")
    b.attach["flag_attach"] = apex
    b.flat_wall((24.0, 0.0, 0.0), (1.0, 0.0, 0.0), 4.0, 3.0, "wall")
    b.jetty(24.0, 28.0, 0.0, 3.0, 0.4, "soffit", "ends", n_ends=5)
    return b.finish(building.BuildingParams(name="Kit" + ("Medium" if medium else "Low")), {})


@test
def round_roofs_export_smooth_normals():
    """The thatch cones and round walls are smooth: the game mesh shares their normals across
    the sides (fewer split vertices than flat shading) and the flat tops stay flat."""
    import dataclasses
    import numpy as np
    for det in ("LOW", "MEDIUM"):
        p = dataclasses.replace(building.PRESETS["AFRICAN_HOUSE_SUBSAHARAN"], detail=det)
        counts, normals = {}, {}
        for mode in ("smooth", "flat"):
            m = building.build(p)
            assert any(f.smooth for f in m.faces if f.region == "thatch"), det
            if mode == "flat":
                for f in m.faces:
                    f.smooth = False
            obj = blender_io.create_object(m, paint.paint(m))
            pos, nor, _, tris = blender_io.game_mesh(obj)
            counts[mode] = len(pos)
            normals[mode] = np.asarray(nor)
            bpy.data.objects.remove(obj)
        assert counts["smooth"] < counts["flat"] * 0.9, (det, counts)
        up = (np.abs(normals["smooth"][:, 2]) > 0.999).sum()
        assert up > 0, det                                 # flat tops (discs, slabs) still face up


def round_kit_model(medium):
    """A free Builder with every round and earthen piece of the kit, on separate plots."""
    import math
    from aoe3_blender_tools.core import kit
    b = kit.Builder(256, medium)
    for name, (w, h) in (("mud", kit.ring_size(2.6, 2.4, 12)), ("thatch", kit.cone_roof_size(2.6, 3.0, 12, 0.5)),
                         ("dome", kit.dome_size(1.4, 1.6, 10)), ("adobe", (8.0, 3.5)), ("roof", (6.0, 5.0)),
                         ("wood", (4.0, 3.0)), ("cloth", (3.0, 2.0)), ("stone", (10.0, 3.0))):
        b.region(name, w, h)
    b.pack()
    # a round hut with a thatched cone and its finial
    b.ring(0.0, 0.0, 2.6, 0.0, 2.4, 12, "mud")
    b.cone_roof(0.0, 0.0, 2.6, 2.4, 3.0, 12, "thatch", overhang=0.5, finial=0.6, finial_region="wood")
    # a domed granary on a round wall
    b.ring(8.0, 0.0, 1.4, 0.0, 1.2, 10, "mud")
    b.dome(8.0, 0.0, 1.4, 1.2, 1.6, 10, "dome")
    # an adobe block with a parapet, merlons and beam ends
    for origin, ua, length in (((12.0, -2.0, 0.0), (1.0, 0.0, 0.0), 6.0), ((18.0, 2.0, 0.0), (-1.0, 0.0, 0.0), 6.0),
                               ((12.0, 2.0, 0.0), (0.0, -1.0, 0.0), 4.0), ((18.0, -2.0, 0.0), (0.0, 1.0, 0.0), 4.0)):
        b.flat_wall(origin, ua, length, 3.0, "adobe")
    b.flat_roof(12.0, 18.0, -2.0, 2.0, 3.0, "roof", parapet_h=0.5, parapet_region="adobe", merlons=1.0)
    b.beam_ends("-y", -2.0, 12.0, 18.0, 2.5, 7, 0.4, "wood")
    # a palisade ring with an entrance and a rail fence
    pts = [(30.0 + 4.0 * math.cos(2 * math.pi * i / 10), 4.0 * math.sin(2 * math.pi * i / 10)) for i in range(10)]
    b.fence(pts, 2.2, "wood", kind="PALISADE", closed=True, gap=7)
    b.fence([(38.0, -2.0), (42.0, -2.0), (42.0, 2.0)], 1.1, "wood", kind="RAILS")
    # round towers, coned and crenellated, and a stall's canopy
    b.round_tower(48.0, 0.0, 1.5, 0.0, 5.0, 10, "stone", roof="CONE", roof_region="thatch")
    b.round_tower(54.0, 0.0, 1.5, 0.0, 5.0, 10, "stone", roof="CRENEL", top_region="roof")
    b.canopy(58.0, 61.0, -1.5, 1.5, 2.4, 1.9, "cloth", "wood")
    b.attach["flag_attach"] = (0.0, 0.0, 6.0)
    return b.finish(building.BuildingParams(name="RoundKit" + ("Medium" if medium else "Low")), {})


@test
def round_kit_parts_have_no_overlaps():
    import numpy as np
    for medium in (False, True):
        model = round_kit_model(medium)
        obj = blender_io.create_object(model, np.full((256, 256, 3), 128, np.uint8))
        res = validate.check(obj)
        assert not problems(res), (medium, problems(res))
        tris, _ = blender_io.triangle_count(obj)
        assert tris == sum(len(f.pts) - 2 for f in model.faces), tris


@test
def roof_kit_parts_have_no_overlaps():
    import numpy as np
    for medium in (False, True):
        model = kit_model(medium)
        assert model.dims["footprint"][0] > 20, model.dims
        obj = blender_io.create_object(model, np.full((256, 256, 3), 128, np.uint8))
        res = validate.check(obj)
        assert not problems(res), (medium, problems(res))
        tris, _ = blender_io.triangle_count(obj)
        assert tris == sum(len(f.pts) - 2 for f in model.faces), tris


@test
def ui_has_a_property_for_every_param_field():
    import dataclasses
    s = bpy.context.scene.aoe3_building
    for f in dataclasses.fields(building.BuildingParams):
        if f.name == "colors":
            for k in building.COLOR_KEYS:
                assert hasattr(s, "color_" + k), k
            continue
        assert hasattr(s, addon.PROP_NAMES.get(f.name, f.name)), f.name
    # every preset goes through the panel and back unchanged
    for key, p in building.PRESETS.items():
        s.preset = key
        assert bpy.ops.aoe3.load_preset() == {"FINISHED"}
        q = addon.params_from_props(s)
        for f in dataclasses.fields(building.BuildingParams):
            a, b = getattr(p, f.name), getattr(q, f.name)
            if f.name == "colors":
                assert {k: tuple(v) for k, v in {**building.DEFAULT_COLORS, **a}.items()} == b, key
            elif isinstance(a, float):
                assert abs(a - b) < 1e-5, (key, f.name, a, b)
            elif f.name == "side_bays" and p.style != "NEOCLASSICAL":
                pass
            else:
                assert a == b, (key, f.name, a, b)


@test
def ai_repaint_and_revert():
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from fake_comfy import FakeComfy

    def tint(rgb):
        return np.clip(rgb.astype(np.int32) + 30, 0, 255).astype(np.uint8)

    s = bpy.context.scene.aoe3_building
    s.preset = "COLONIAL_HOUSE"
    bpy.ops.aoe3.load_preset()
    s.texture_size, s.detail, s.game_player_colour = "512", "LOW", True
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    obj = bpy.context.active_object
    before = blender_io.texture_rgba(obj)
    with FakeComfy(transform=tint) as fake:
        bpy.context.scene.aoe3_ai.url = fake.url
        assert bpy.ops.aoe3.ai_check() == {"FINISHED"}
        assert bpy.ops.aoe3.ai_repaint() == {"FINISHED"}
        after = blender_io.texture_rgba(obj)
        assert "aoe3_ai" in obj and obj.get("aoe3_ai_orig")
        assert (after[:, :, 3] == before[:, :, 3]).all()                       # alpha kept
        assert (after[:, :, :3] != before[:, :, :3]).any(axis=2).mean() > 0.2  # walls and roof changed
        # again: starts from the original, does not stack on the first repaint
        assert bpy.ops.aoe3.ai_repaint() == {"FINISHED"}
        assert (blender_io.texture_rgba(obj) == after).all()
    with tempfile.TemporaryDirectory() as d:          # the game export takes the repainted texture
        s.game_dir, s.game_icons, s.game_lowpoly, s.game_damaged = d, False, False, False
        assert bpy.ops.aoe3.export_game() == {"FINISHED"}
        from aoe3_blender_tools.aoe3game import ddt
        with open(os.path.join(d, "art", "mod", "buildings", obj.name.lower(), obj.name.lower() + ".ddt"), "rb") as f:
            exported = ddt.decode(f.read())
        assert abs(exported[:, :, :3].astype(int) - after[:, :, :3]).mean() < abs(exported[:, :, :3].astype(int) - before[:, :, :3]).mean()
    assert bpy.ops.aoe3.ai_revert() == {"FINISHED"}
    assert (blender_io.texture_rgba(obj) == before).all()
    assert "aoe3_ai" not in obj and "aoe3_ai_orig" not in obj
    # one region with the user's own prompt: only that region changes, the prompt reaches ComfyUI
    a = bpy.context.scene.aoe3_ai
    a.regions, a.prompt = "ONE", "red mud wall with white zigzags"
    a.region = "roof"
    model = building.build(blender_io.params_of(obj))
    with FakeComfy(transform=tint) as fake:
        a.url = fake.url
        assert bpy.ops.aoe3.ai_repaint() == {"FINISHED"}
        texts = [v["inputs"].get("text", "") for wf in fake.prompts for v in wf.values()]
        assert any("red mud wall with white zigzags" in t for t in texts), texts
    from aoe3_blender_tools.core import airepaint
    after = blender_io.texture_rgba(obj)
    x0, y0, x1, y1 = airepaint.region_rect(model, after, "roof")
    changed = (after[:, :, :3] != before[:, :, :3]).any(axis=2)
    assert changed[y0:y1, x0:x1].mean() > 0.5 and changed.sum() == changed[y0:y1, x0:x1].sum()
    assert bpy.ops.aoe3.ai_revert() == {"FINISHED"}
    a.regions, a.prompt = "ALL", ""
    # the live preview: a texture after every region
    seen = []
    with FakeComfy(transform=tint) as fake:
        airepaint.repaint(before, model, comfy.Client(fake.url), regions=["roof", "front"],
                          on_region=lambda t: seen.append(t))
    assert len(seen) == 2 and (seen[0] != seen[1]).any()


@test
def a_mesh_we_did_not_make_is_repainted_and_exported_as_a_prop():
    """Someone else's model: no aoe3_params, their own UVs and texture. The AI panel repaints it
    from the user's prompt, and the game export writes a prop bundle (no construction stages, no
    rubble, no placement file)."""
    import bmesh
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from fake_comfy import FakeComfy

    def grain(rgb):
        """Grain, as a repaint leaves: it must not move the edges, or the guard keeps the region."""
        rng = np.random.default_rng(7)
        return np.clip(rgb.astype(np.int32) + rng.integers(-10, 11, rgb.shape), 0, 255).astype(np.uint8)

    mesh = bpy.data.meshes.new("barrel")
    obj = bpy.data.objects.new("Barrel", mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 1))
    bm.to_mesh(mesh)
    bm.free()
    mesh.uv_layers.new(name="UVMap")
    uvs = mesh.uv_layers.active.data
    for poly in mesh.polygons:
        for li, c in zip(poly.loop_indices, [(0.02, 0.02), (0.98, 0.02), (0.98, 0.98), (0.02, 0.98)]):
            uvs[li].uv = c
    # staves and hoops: edges for the guard to follow, irregular (a perfectly repeating pattern
    # lines up with itself at several shifts and the guard then reads it as moved)
    tex = np.full((256, 256, 4), 180, np.uint8)
    for x in np.random.default_rng(1).choice(np.arange(4, 250), 18, replace=False):
        tex[:, x:x + 2] = 90
    for y in (40, 41, 42, 190, 191, 192):
        tex[y] = 60
    tex[:, :, 3] = 255
    img = blender_io._image_from_array("barrel_diffuse", tex)
    mesh.materials.append(blender_io._material("barrel_mat", img))
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)

    assert blender_io.params_of(obj) is None
    assert bpy.ops.aoe3.ai_repaint.poll(), "the AI repaint must reach a mesh we did not generate"
    a = bpy.context.scene.aoe3_ai
    a.regions, a.prompt = "ALL", ""
    before = blender_io.texture_rgba(obj)
    with FakeComfy(transform=grain) as fake:
        a.url = fake.url
        try:                                   # without a prompt there is nothing to paint with
            assert bpy.ops.aoe3.ai_repaint() == {"CANCELLED"}
        except RuntimeError as e:
            assert "prompt" in str(e), e
        assert (blender_io.texture_rgba(obj) == before).all()
        a.prompt = "weathered oak barrel staves with iron hoops"
        assert bpy.ops.aoe3.ai_repaint() == {"FINISHED"}
        texts = [v["inputs"].get("text", "") for wf in fake.prompts for v in wf.values()]
        assert any("weathered oak barrel" in t for t in texts), texts
    after = blender_io.texture_rgba(obj)
    assert (after[:, :, :3] != before[:, :, :3]).any(axis=2).mean() > 0.2
    assert (after[:, :, 3] == 255).all()
    assert bpy.ops.aoe3.ai_revert() == {"FINISHED"}
    assert (blender_io.texture_rgba(obj) == before).all()
    a.prompt = ""

    s = bpy.context.scene.aoe3_building
    with tempfile.TemporaryDirectory() as d:
        s.game_dir, s.game_icons, s.game_kind, s.game_folder = d, False, "PROP", ""
        assert bpy.ops.aoe3.export_game() == {"FINISHED"}
        art = os.path.join(d, "art", "mod", "objects", "barrel")
        written = sorted(os.listdir(art))
        assert "barrel.gr2" in written and "barrel.ddt" in written, written
        assert not any(f.endswith("_death.gr2") or f.endswith("_lp.gr2") for f in written), written
        with open(os.path.join(art, "barrel.xml"), encoding="utf-8") as f:
            anim = f.read()
        assert "BuildingCompletion" not in anim and "construction" not in anim
        with open(os.path.join(d, "bundle.json"), encoding="utf-8") as f:
            desc = json.load(f)
        assert desc["kind"] == "PROP" and "DeadReplacement" not in desc["unit"]
    s.game_kind = "BUILDING"
    bpy.data.objects.remove(obj)


@test
def the_texture_maker_makes_a_tileable_swatch_and_keeps_it():
    """The Texture Maker panel: a reference picture without ComfyUI, a prompt with it, the
    library beside the result, and a texture laid under the painting in place of a swatch."""
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from fake_comfy import FakeComfy

    from aoe3_blender_tools.core import materials, texlib, texmaker

    a = bpy.context.scene.aoe3_ai
    with tempfile.TemporaryDirectory() as d:
        rng = np.random.default_rng(0)                 # a photograph: light across it, no tiling
        ramp = np.linspace(40, 215, 256, dtype=np.float32)[None, :, None]
        photo = np.clip(ramp + rng.integers(-12, 13, (256, 256, 3)), 0, 255).astype(np.uint8)
        path = os.path.join(d, "factory.png")
        paint.save_png(photo, path)
        a.tex_source, a.tex_prompt, a.tex_name = path, "", "factory_roof"
        a.tex_licence, a.tex_folder, a.tex_size = "my own photograph", d, "128"
        a.tex_style, a.tex_role = "", ""
        assert bpy.ops.aoe3.make_texture() == {"FINISHED"}      # no ComfyUI for this one
        img = texlib.image("factory_roof", d)
        assert img.shape == (128, 128, 3), img.shape
        assert texmaker.seam(img) < texmaker.SEAM_OK, texmaker.seam(img)
        entry = texlib.read("factory_roof", d)
        assert entry["licence"] == "my own photograph" and entry["mode"] == "photo"
        assert os.path.exists(os.path.join(d, "factory_roof_x3.png"))
        assert bpy.data.images.get("factory_roof") is not None
        a.tex_name, a.tex_licence = "nameless", ""             # the licence is required
        try:
            assert bpy.ops.aoe3.make_texture() == {"CANCELLED"}
        except RuntimeError as e:
            assert "licence" in str(e), e
        assert texlib.read("nameless", d) is None
        with FakeComfy() as fake:                              # from the prompt alone
            a.url = fake.url
            a.tex_source, a.tex_prompt = "", "dry golden grass thatch"
            a.tex_name, a.tex_licence = "thatch_own", "generated locally"
            a.tex_style, a.tex_role, a.tex_tile_m = "COLONIAL", "roof", 1.4
            assert bpy.ops.aoe3.make_texture() == {"FINISHED"}
            texts = [v["inputs"].get("text", "") for wf in fake.prompts for v in wf.values()]
            assert any("dry golden grass thatch" in t for t in texts), texts
        assert texlib.read("thatch_own", d)["mode"] == "prompt"
        plan = materials.plan("COLONIAL")                      # it is what the painter lays now
        assert os.path.basename(plan["roof"][0]) == "thatch_own", plan["roof"]
        assert round(plan["roof"][1], 3) == 1.4 and plan["roof"][2] == "tile", plan["roof"]
        assert bpy.ops.aoe3.use_textures() == {"FINISHED"}     # and back to the add-on's own
        assert materials.plan("COLONIAL")["roof"][0] == "clay"
    a.tex_source, a.tex_prompt, a.tex_name, a.tex_licence, a.tex_folder = "", "", "", "", ""
    a.tex_style, a.tex_role = "", ""


@test
def a_game_model_is_imported_and_exports_again():
    """Import a Game Model: what the game export wrote comes back as a mesh with its UVs and an
    Empty per socket, and goes out again with the same triangles and the same bone."""
    from aoe3_blender_tools.aoe3game import gr2_write
    from aoe3_blender_tools.core import gr2_import
    s = bpy.context.scene.aoe3_building
    s.preset = "MANSION"
    bpy.ops.aoe3.load_preset()
    assert bpy.ops.aoe3.generate_building() == {"FINISHED"}
    src = bpy.context.active_object
    P, N, UV, T = blender_io.game_mesh(src)
    bones = blender_io.game_bones(src)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "mansion.gr2")
        with open(path, "wb") as f:
            f.write(gr2_write.static_model("Mansion", P, N, UV, T, texture="m.ddt", bump="m_b.ddt", bones=bones))
        assert bpy.ops.aoe3.import_gr2(filepath=path) == {"FINISHED"}
        obj = bpy.context.active_object
        assert obj.get("aoe3_imported") and obj.name.startswith("mansion")
        assert blender_io.triangle_count(obj)[0] == len(T)
        for a, b in zip(obj.dimensions, src.dimensions):
            assert abs(a - b) < 0.02, (tuple(obj.dimensions), tuple(src.dimensions))
        back = blender_io.game_bones(obj)
        assert sorted(n for n, _ in back) == sorted(n for n, _ in bones), (back, bones)
        P2, _N2, UV2, T2 = blender_io.game_mesh(obj)                  # and out again
        assert len(T2) == len(T) and len(UV2) > 0
        with open(os.path.join(d, "broken.gr2"), "wb") as f:
            f.write(b"not a model")
        try:
            assert bpy.ops.aoe3.import_gr2(filepath=os.path.join(d, "broken.gr2")) == {"CANCELLED"}
        except RuntimeError as e:
            assert "broken.gr2" in str(e), e
        try:
            gr2_import.load(os.path.join(d, "broken.gr2"))
            raise AssertionError("a broken file was imported")
        except ValueError:
            pass


@test
def three_meshes_are_packed_into_one_texture_and_exported_as_a_set():
    """Three cubes with three textures: one atlas, every UV inside it, no two boxes overlapping,
    each cube's colour found again through its new UVs; then a set bundle of three models on one
    texture. A generated set comes out already on one texture."""
    import tempfile

    import bmesh
    import numpy as np
    colours = {"Crate_a": (200, 40, 40), "Crate_b": (40, 200, 40), "Crate_c": (40, 40, 200)}
    objs = []
    for i, (name, colour) in enumerate(colours.items()):
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0 + i)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, (1.0 + i) / 2))
        bm.to_mesh(mesh)
        bm.free()
        mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            for li, c in zip(poly.loop_indices, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]):
                mesh.uv_layers.active.data[li].uv = c
        tex = np.zeros((64, 64, 4), np.uint8)
        tex[:, :, :3] = colour
        tex[:, :, 3] = 255
        mesh.materials.append(blender_io._material(name + "_mat", blender_io._image_from_array(name + "_img", tex)))
        obj.location.x = 4.0 * i
        objs.append(obj)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    s = bpy.context.scene.aoe3_building
    s.texture_size = "256"
    try:                                                       # three textures: refused
        refused = bpy.ops.aoe3.export_set()
    except RuntimeError:                                       # an operator's error report raises
        refused = {"CANCELLED"}
    assert refused == {"CANCELLED"}, refused
    assert bpy.ops.aoe3.pack_set() == {"FINISHED"}
    atlas = blender_io.texture_rgba(objs[0])
    assert {blender_io._object_image(o) for o in objs} == {blender_io._object_image(objs[0])}
    boxes = []
    for o in objs:
        uv = np.array([d.uv[:] for d in o.data.uv_layers.active.data])
        assert (uv >= 0).all() and (uv <= 1).all(), o.name
        boxes.append((uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()))
        u, v = uv.mean(axis=0)
        px = atlas[int((1 - v) * 256), int(u * 256), :3]
        assert np.abs(px.astype(int) - colours[o.name]).max() < 6, (o.name, px)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)
    widths = sorted(b[2] - b[0] for b in boxes)                # one density: a bigger cube, a bigger box
    assert widths[0] < widths[1] < widths[2], widths
    with tempfile.TemporaryDirectory() as tmp:
        s.game_dir, s.game_prefix, s.game_icons = tmp, "mod", False
        assert bpy.ops.aoe3.export_set() == {"FINISHED"}
        desc = json.load(open(os.path.join(tmp, "bundle.json"), encoding="utf-8"))
        assert desc["set"] == 3 and desc["kind"] == "PROP", desc
        art = os.path.join(tmp, "art", "mod", "objects", desc["name"].lower())
        assert sorted(f for f in os.listdir(art) if f.endswith(".gr2")) == [
            f"{desc['name'].lower()}_{i}.gr2" for i in range(3)]
    # a generated set: its models already share one texture
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    s.style, s.prop_set = "PROP", "GOODS"
    assert bpy.ops.aoe3.generate_set() == {"FINISHED"}
    made = [o for o in bpy.data.objects if o.get("aoe3_set")]
    assert len(made) == 10, len(made)
    assert len({blender_io._object_image(o) for o in made}) == 1
    assert all("aoe3_params" not in o for o in made)


@test
def a_settlement_is_composed_moved_and_written_as_a_grouping():
    """Compose round a socket from a house and a generated set, move one unit by hand, export the
    grouping, read it back; then import it as markers."""
    import bmesh
    from aoe3_blender_tools.aoe3game import grouping
    s = bpy.context.scene.aoe3_building
    s.style, s.prop_set, s.seed = "PROP", "GOODS", 5
    assert bpy.ops.aoe3.generate_set() == {"FINISHED"}
    goods = [o for o in bpy.data.objects if o.get("aoe3_set")]
    mesh = bpy.data.meshes.new("hut")
    hut = bpy.data.objects.new("NativeHut", mesh)
    bpy.context.collection.objects.link(hut)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=6.0)
    bm.to_mesh(mesh)
    bm.free()
    hut["aoe3_proto"], hut["aoe3_class"] = "NativeHut", "building"
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in goods + [hut]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = hut
    s.grouping_socket, s.grouping_obstruction = "SocketNative", "TownObstruction"
    assert bpy.ops.aoe3.compose_settlement() == {"FINISHED"}
    coll = bpy.data.collections[f"Settlement_{s.seed}"]
    placed = list(coll.objects)
    classes = [o["aoe3_class"] for o in placed]
    assert classes.count("socket") == 1 and "building" in classes and "prop" in classes, classes
    assert all(o["aoe3_variation"] < 10 for o in placed if o["aoe3_proto"] == goods[0].get("aoe3_set"))
    mover = next(o for o in placed if o["aoe3_class"] == "building")
    mover.location.x += 2.0
    with tempfile.TemporaryDirectory() as tmp:
        s.grouping_path = os.path.join(tmp, "Native Test 1.xml")
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in placed:
            o.select_set(True)
        assert bpy.ops.aoe3.export_grouping() == {"FINISHED"}
        g = grouping.read(open(s.grouping_path, encoding="utf-8").read())
        assert len(g["units"]) == len(placed), (len(g["units"]), len(placed))
        assert g["units"][0]["proto"] == "SocketNative"
        moved = [u for u in g["units"] if u["proto"] == "NativeHut"]
        want = mover.location.x * bundle_upm()
        assert any(abs(u["x"] - want) < 1e-3 for u in moved), (want, [u["x"] for u in moved])
        before = len(bpy.data.objects)
        assert bpy.ops.aoe3.import_grouping() == {"FINISHED"}
        assert len(bpy.data.objects) == before + len(placed)


def bundle_upm():
    from aoe3_blender_tools.aoe3game import bundle
    return bundle.UNITS_PER_METER


def main():
    addon.register()
    try:
        for t in (presets_generate_and_pass_checks, parameter_sweep_has_no_overlaps_or_errors,
                  medium_detail_presets_pass_checks, wall_triangulation_covers_the_wall_exactly,
                  regenerating_replaces_the_object, export_and_reimport, checks_catch_known_problems,
                  atlas_and_texture_sizes, game_export_writes_the_bundle, check_uses_profile_budget,
                  player_colour_marks_the_string_courses, icon_and_portrait_render,
                  game_variants_lowpoly_and_damaged, deploy_from_blender_and_undo,
                  square_hipped_roof_builds, roof_kit_parts_have_no_overlaps,
                  ui_has_a_property_for_every_param_field, ai_repaint_and_revert,
                  round_kit_parts_have_no_overlaps, round_roofs_export_smooth_normals,
                  a_mesh_we_did_not_make_is_repainted_and_exported_as_a_prop,
                  the_texture_maker_makes_a_tileable_swatch_and_keeps_it,
                  a_game_model_is_imported_and_exports_again,
                  three_meshes_are_packed_into_one_texture_and_exported_as_a_set,
                  a_settlement_is_composed_moved_and_written_as_a_grouping):
            t()
    finally:
        addon.unregister()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all tests passed'}")
    sys.exit(1 if FAILED else 0)


main()
