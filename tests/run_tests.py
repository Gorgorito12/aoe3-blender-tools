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
                  ui_has_a_property_for_every_param_field, ai_repaint_and_revert):
            t()
    finally:
        addon.unregister()
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'all tests passed'}")
    sys.exit(1 if FAILED else 0)


main()
