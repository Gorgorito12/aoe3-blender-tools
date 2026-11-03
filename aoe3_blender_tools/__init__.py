# SPDX-License-Identifier: GPL-3.0-or-later
"""AoE3 Blender Tools: a low-poly building generator, game-ready checks and exports for Age of
Empires III mods. Panel: 3D Viewport > Sidebar (N) > AoE3."""

bl_info = {      # read only by Blender versions without extensions; 4.2+ reads blender_manifest.toml
    "name": "AoE3 Blender Tools",
    "author": "Gorgorito12",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > AoE3",
    "description": "Low-poly building generator, game-ready checks and exports for Age of Empires III mods",
    "category": "Object",
}

import os  # noqa: E402

import bpy  # noqa: E402
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,  # noqa: E402
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

from . import ai_panel  # noqa: E402
from .aoe3game import bundle  # noqa: E402
from .core import blender_io, building, paint, validate  # noqa: E402
from .core import profile as calibration  # noqa: E402
from .core import render  # noqa: E402

COLOR_KEYS = building.COLOR_KEYS
PRESET_ITEMS = [(k, k.replace("_", " ").title(), "") for k in building.PRESETS]
STYLE_ITEMS = [(k, k.title(), "") for k in building.STYLES]
# BuildingParams fields the panel holds under another name (the colours have one property each)
PROP_NAMES = {"player_colour": "game_player_colour"}


def _color_prop(key):
    default = tuple(c / 255.0 for c in building.BuildingParams().colors[key])
    return FloatVectorProperty(name=key.title(), subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0,
                               default=default)


class AOE3_PG_result(bpy.types.PropertyGroup):
    level: StringProperty()
    message: StringProperty()


class AOE3_PG_building(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Preset", items=PRESET_ITEMS, default="WHITE_HOUSE")
    name: StringProperty(name="Name", default="WhiteHouse")
    style: EnumProperty(name="Style", items=STYLE_ITEMS, default="NEOCLASSICAL")
    roof_type: EnumProperty(name="Roof", items=[("GABLE", "Gable", "Two slopes"),
                                                ("HIPPED", "Hipped", "Four slopes")], default="GABLE")
    ridge: EnumProperty(name="Ridge", items=[("ALONG", "Along", "The ridge along the width (eaves front and back)"),
                                             ("ACROSS", "Across", "The ridge along the depth (a gable on the front)")],
                        default="ALONG")
    arcade: EnumProperty(name="Portal", items=[("NONE", "None", ""),
                                               ("FRONT", "Front", "An arcade along the front under a lean-to roof")],
                         default="NONE")
    arcade_posts: EnumProperty(name="Posts", items=[("WOOD", "Wood", "Posts and a beam"),
                                                           ("MASONRY", "Masonry", "Piers and arches")],
                               default="WOOD")
    arcade_depth: FloatProperty(name="Portal depth", default=2.4, min=1.6, max=3.5, unit="LENGTH")
    balcony: BoolProperty(name="Balcony", default=False, description="A wooden balcony on the upper floor")
    bell_gable: BoolProperty(name="Bell gable", default=False, description="A bell gable over the front")
    plan: EnumProperty(name="Plan", items=[("BLOCK", "Block", ""),
                                           ("L", "L", "A one-storey wing at the back")], default="BLOCK")
    rejas: BoolProperty(name="Window grilles", default=True, description="Iron grilles on the ground floor windows")
    jetty: BoolProperty(name="Jetty", default=True, description="The upper floors jut out over the front and back")
    jetty_depth: FloatProperty(name="Jetty depth", default=0.4, min=0.2, max=0.8, unit="LENGTH")
    dormers: IntProperty(name="Dormers", default=1, min=0, max=4)
    ground_floor: EnumProperty(name="Ground", items=[("STONE", "Stone", "Rubble stone"),
                                                           ("BRICK", "Brick", ""),
                                                           ("TIMBER", "Timber", "Framed like the upper floors")],
                               default="STONE")
    infill: EnumProperty(name="Infill", items=[("PLASTER", "Plaster", ""), ("BRICK", "Brick", "")],
                         default="PLASTER")
    bracing: EnumProperty(name="Braces", items=[("CROSS", "Cross", ""), ("CURVED", "Curved", ""),
                                                ("PLAIN", "Plain", "Posts and rails only")], default="CROSS")
    signboard: BoolProperty(name="Sign", default=False, description="A sign hanging from the front wall")
    materials: BoolProperty(name="Material swatches", default=False,
                            description="Photo swatches (CC0) under the painting give the walls their grain")
    width: FloatProperty(name="Width", default=14.0, min=4.0, max=60.0, unit="LENGTH")
    depth: FloatProperty(name="Depth", default=9.0, min=4.0, max=60.0, unit="LENGTH")
    storeys: IntProperty(name="Storeys", default=2, min=1, max=4)
    plinth: FloatProperty(name="Plinth", default=0.8, min=0.2, max=2.0, unit="LENGTH")
    roof_pitch: FloatProperty(name="Roof pitch", default=0.54, min=0.15, max=1.5,
                              description="Rise over run, the same on all four sides")
    bay_spacing: FloatProperty(name="Window spacing", default=1.8, min=1.3, max=6.0, unit="LENGTH")
    side_bays: IntProperty(name="Side windows", default=3, min=0, max=15,
                           description="Windows per row on each side; 0 = from the window spacing")
    detail: EnumProperty(name="Detail", items=[
        ("LOW", "Low", "Flat walls with painted windows (about 350 triangles)"),
        ("MEDIUM", "Medium", "Recessed windows and doors, balustrade, profiled cornice, finer columns "
                             "(about 1,200 triangles)")], default="LOW")
    portico: BoolProperty(name="Portico", default=True)
    columns: IntProperty(name="Columns", default=4, min=2, max=8, step=2)
    column_spacing: FloatProperty(name="Column spacing", default=1.8, min=1.2, max=4.0, unit="LENGTH")
    portico_depth: FloatProperty(name="Portico depth", default=3.3, min=1.5, max=8.0, unit="LENGTH")
    cupola: BoolProperty(name="Cupola", default=True)
    chimneys: IntProperty(name="Chimneys", default=1, min=0, max=8)
    flagpole: BoolProperty(name="Flagpole", default=False, description="A mast on the roof (used when there is no cupola)")
    back_portico: EnumProperty(name="Back portico", items=[
        ("NONE", "None", "A flat back facade"),
        ("BOW", "Bow", "A semicircular colonnade around a bowed bay, with a balustraded flat roof")], default="NONE")
    bow_radius: FloatProperty(name="Bow radius", default=3.2, min=1.5, max=12.0, unit="LENGTH")
    bow_columns: IntProperty(name="Bow columns", default=6, min=2, max=10)
    wings: BoolProperty(name="Wings", default=False, description="One-storey pavilions joined by colonnades")
    wing_gap: FloatProperty(name="Colonnade length", default=5.0, min=2.0, max=30.0, unit="LENGTH")
    wing_width: FloatProperty(name="Wing width", default=6.5, min=3.0, max=30.0, unit="LENGTH")
    wing_depth: FloatProperty(name="Wing depth", default=5.5, min=3.0, max=30.0, unit="LENGTH")
    shutters: BoolProperty(name="Shutters", default=False, description="Painted shutters on the back and bow windows")
    window_caps: EnumProperty(name="Window caps", items=[
        ("PEDIMENT", "Pediments", "Triangular pediments over the ground floor windows"),
        ("ALTERNATE", "Alternate", "Triangular and arched caps in turn on the front")], default="PEDIMENT")
    texture_size: EnumProperty(name="Texture", items=[("512", "512", ""), ("1024", "1024", ""),
                                                      ("2048", "2048", "")], default="1024")
    seed: IntProperty(name="Seed", default=1870)
    show_colors: BoolProperty(name="Colours", default=False)
    tri_budget: IntProperty(name="Triangle budget", default=6000, min=100)
    use_profile: BoolProperty(name="Measured budget", default=True,
                              description="Use the budget measured for buildings of the same footprint "
                                          "(calibration profile), when one is installed")
    game_dir: StringProperty(name="Folder", subtype="DIR_PATH", default="//aoe3_game")
    game_prefix: StringProperty(name="Mod folder", default="mod",
                                description="The mod's own folder under art (the model goes to "
                                            "art/<mod folder>/buildings/<name>/)")
    game_display: StringProperty(name="Name in game", default="",
                                 description="The name players see (empty: the object's name)")
    game_texture: EnumProperty(name="Texture format", items=[
        ("DXT3", "DXT3", "Compressed with alpha, as most of the game's buildings (a quarter of BGRA)"),
        ("DXT1", "DXT1", "Compressed, no alpha (no player colour)"),
        ("BGRA", "BGRA", "Uncompressed")], default="DXT3")
    game_icons: BoolProperty(name="Icon and portrait", default=True,
                             description="Render the building's icon (64 x 64) and portrait (128 x 128)")
    game_lowpoly: BoolProperty(name="Low-poly model", default=True,
                               description="Also write the LOW detail version, which the game draws at "
                                           "its low model detail setting")
    game_damaged: BoolProperty(name="Damaged model", default=True,
                               description="Also write a damaged texture (soot, missing slates, cracks) "
                                           "that the game shows once the building has lost hit points")
    game_install: StringProperty(name="Test copy", subtype="DIR_PATH", default="",
                                 description="A copy of the game (or of the mod's folder) to deploy into; "
                                             "a Steam folder is refused")
    game_builder: StringProperty(name="Builder", default="Settler",
                                 description="The unit that gets the building in its build list (empty: none)")
    game_template: StringProperty(name="Proto template", default="House",
                                  description="The unit whose proto entry the new building copies")
    game_player_colour: BoolProperty(name="Player colour", default=False,
                                     description="Paint the string courses and shutters for the owner's "
                                                 "colour (texture alpha 0 there); the game export then "
                                                 "uses the player-colour shader")
    export_dir: StringProperty(name="Folder", subtype="DIR_PATH", default="//aoe3_export")
    export_glb: BoolProperty(name="GLB", default=True)
    export_fbx: BoolProperty(name="FBX", default=True)
    export_obj: BoolProperty(name="OBJ", default=True)
    results: CollectionProperty(type=AOE3_PG_result)
    color_wall: _color_prop("wall")
    color_trim: _color_prop("trim")
    color_roof: _color_prop("roof")
    color_glass: _color_prop("glass")
    color_door: _color_prop("door")
    color_brick: _color_prop("brick")
    color_lead: _color_prop("lead")
    color_stone: _color_prop("stone")
    color_plinth: _color_prop("plinth")
    color_plaster: _color_prop("plaster")
    color_tile: _color_prop("tile")
    color_timber: _color_prop("timber")
    color_iron: _color_prop("iron")



def params_from_props(s):
    p = building.BuildingParams(
        name=s.name.strip() or "Building", width=s.width, depth=s.depth, storeys=s.storeys,
        plinth=s.plinth, roof_pitch=s.roof_pitch, bay_spacing=s.bay_spacing, side_bays=s.side_bays,
        detail=s.detail, portico=s.portico,
        columns=s.columns, column_spacing=s.column_spacing, portico_depth=s.portico_depth,
        cupola=s.cupola, chimneys=s.chimneys, texture_size=int(s.texture_size), seed=s.seed,
        flagpole=s.flagpole, back_portico=s.back_portico, bow_radius=s.bow_radius, bow_columns=s.bow_columns,
        wings=s.wings, wing_gap=s.wing_gap, wing_width=s.wing_width, wing_depth=s.wing_depth, shutters=s.shutters,
        window_caps=s.window_caps, player_colour=s.game_player_colour, style=s.style,
        roof_type=s.roof_type, ridge=s.ridge, arcade=s.arcade, arcade_posts=s.arcade_posts,
        arcade_depth=s.arcade_depth, balcony=s.balcony, bell_gable=s.bell_gable, plan=s.plan,
        rejas=s.rejas, materials=s.materials, jetty=s.jetty, jetty_depth=s.jetty_depth,
        dormers=s.dormers, ground_floor=s.ground_floor, infill=s.infill, bracing=s.bracing,
        signboard=s.signboard)
    p.colors = {k: tuple(int(round(c * 255)) for c in getattr(s, "color_" + k)) for k in COLOR_KEYS}
    return p


def props_from_params(s, p):
    for attr in ("name", "width", "depth", "storeys", "plinth", "roof_pitch", "bay_spacing", "side_bays",
                 "detail", "portico",
                 "columns", "column_spacing", "portico_depth", "cupola", "chimneys", "seed", "flagpole",
                 "back_portico", "bow_radius", "bow_columns", "wings", "wing_gap", "wing_width", "wing_depth",
                 "shutters", "window_caps", "style", "roof_type", "ridge", "arcade", "arcade_posts",
                 "arcade_depth", "balcony", "bell_gable", "plan", "rejas", "materials", "jetty",
                 "jetty_depth", "dormers", "ground_floor", "infill", "bracing", "signboard"):
        setattr(s, attr, getattr(p, attr))
    s.game_player_colour = p.player_colour
    s.texture_size = str(p.texture_size)
    colors = {**building.DEFAULT_COLORS, **p.colors}
    for k in COLOR_KEYS:
        setattr(s, "color_" + k, tuple(c / 255.0 for c in colors[k]))


class AOE3_OT_load_preset(bpy.types.Operator):
    bl_idname = "aoe3.load_preset"
    bl_label = "Load Preset"
    bl_description = "Fill the settings from the chosen preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.aoe3_building
        props_from_params(s, building.PRESETS[s.preset])
        return {"FINISHED"}


class AOE3_OT_generate_building(bpy.types.Operator):
    bl_idname = "aoe3.generate_building"
    bl_label = "Generate Building"
    bl_description = "Build the mesh, its UVs and its painted texture (replaces an object of the same name)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.aoe3_building
        model = building.build(params_from_props(s))
        texture = paint.paint_rgba(model) if model.params.player_colour else paint.paint(model)
        for o in context.view_layer.objects:     # before create_object removes the previous one
            o.select_set(False)
        obj = blender_io.create_object(model, texture, context.collection)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        tris, _ = blender_io.triangle_count(obj)
        fp = model.dims["footprint"]
        for note in model.notes:
            self.report({"WARNING"}, note)
        self.report({"INFO"}, f"{obj.name}: {tris} triangles, {fp[0]:.1f} x {fp[1]:.1f} m footprint")
        return {"FINISHED"}


class AOE3_OT_check_building(bpy.types.Operator):
    bl_idname = "aoe3.check_building"
    bl_label = "Check"
    bl_description = "Run the game-ready checks on the active object"

    def execute(self, context):
        s = context.scene.aoe3_building
        prof = calibration.load() if s.use_profile else None
        res = validate.check(context.active_object, s.tri_budget, prof)
        s.results.clear()
        for level, msg in res:
            item = s.results.add()
            item.level, item.message = level, msg
        errors = sum(1 for lv, _ in res if lv == validate.ERROR)
        warnings = sum(1 for lv, _ in res if lv == validate.WARNING)
        self.report({"ERROR" if errors else "WARNING" if warnings else "INFO"},
                    f"Check: {errors} errors, {warnings} warnings")
        return {"FINISHED"}


class AOE3_OT_export_building(bpy.types.Operator):
    bl_idname = "aoe3.export_building"
    bl_label = "Export"
    bl_description = "Export the active building, its attach points and its texture"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        s = context.scene.aoe3_building
        folder = bpy.path.abspath(s.export_dir)
        paths = blender_io.export(context.active_object, folder, s.export_glb, s.export_fbx, s.export_obj)
        self.report({"INFO"}, f"Exported {len(paths)} files to {folder}")
        return {"FINISHED"}


class AOE3_OT_export_game(bpy.types.Operator):
    bl_idname = "aoe3.export_game"
    bl_label = "Export for the Game"
    bl_description = ("Write the active building in the game's formats: model (.gr2), texture (.ddt), "
                      "anim file and the proto fields and strings (bundle.json), for tools/game_deploy.py")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        s = context.scene.aoe3_building
        obj = context.active_object
        if "aoe3_footprint" in obj:
            footprint = tuple(obj["aoe3_footprint"])[:2]
        else:
            footprint = (obj.dimensions.x, obj.dimensions.y)
        try:
            positions, normals, uvs, tris = blender_io.game_mesh(obj)
            icon, portrait = render.icon_and_portrait(obj) if s.game_icons else (None, None)
            variants = blender_io.game_variants(obj, lowpoly=s.game_lowpoly, damaged=s.game_damaged)
            desc = bundle.write(
                bpy.path.abspath(s.game_dir), name=obj.name, prefix=s.game_prefix or "mod",
                positions=positions, normals=normals, uvs=uvs, triangles=tris,
                texture_rgba=blender_io.texture_rgba(obj), bones=blender_io.game_bones(obj),
                footprint_m=footprint, display_name=s.game_display or None,
                icon_rgba=icon, portrait_rgba=portrait, variants=variants,
                template=s.game_template or "House", texture_format=s.game_texture,
                profile=calibration.load() if s.use_profile else None)
        except (ValueError, OSError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        size = desc["size"]
        self.report({"INFO"}, f"{obj.name}: {len(tris)} triangles; obstruction {size['radius'][0]} x "
                              f"{size['radius'][1]}, stages {size['stages']}; {len(desc['files'])} files")
        return {"FINISHED"}


class AOE3_PT_building(bpy.types.Panel):
    bl_label = "Building Generator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AoE3"

    def draw(self, context):
        s = context.scene.aoe3_building
        lay = self.layout
        row = lay.row(align=True)
        row.prop(s, "preset", text="")
        row.operator("aoe3.load_preset", text="", icon="IMPORT")
        lay.prop(s, "name")
        lay.prop(s, "style")
        lay.prop(s, "detail", expand=True)
        col = lay.column(align=True)
        col.prop(s, "width")
        col.prop(s, "depth")
        col.prop(s, "storeys")
        col.prop(s, "plinth")
        col.prop(s, "bay_spacing")
        if s.style == "COLONIAL":
            self.draw_colonial(s, lay)
        elif s.style == "TIMBER":
            self.draw_timber(s, lay)
        else:
            self.draw_neoclassical(s, lay)
        row = lay.row(align=True)
        row.prop(s, "texture_size")
        row.prop(s, "seed")
        lay.prop(s, "game_player_colour")
        lay.prop(s, "materials")
        lay.prop(s, "show_colors", icon="TRIA_DOWN" if s.show_colors else "TRIA_RIGHT", emboss=False)
        if s.show_colors:
            grid = lay.grid_flow(columns=3, align=True)
            for k in COLOR_KEYS:
                grid.prop(s, "color_" + k, text=k.title())
        lay.operator("aoe3.generate_building", icon="HOME")

    @staticmethod
    def draw_timber(s, lay):
        col = lay.column(align=True)
        col.prop(s, "roof_pitch")
        col.prop(s, "dormers")
        col.prop(s, "chimneys")
        col.prop(s, "ground_floor")
        col.prop(s, "infill")
        col.prop(s, "bracing")
        col.prop(s, "signboard")
        lay.prop(s, "jetty")
        if s.jetty:
            lay.prop(s, "jetty_depth")

    @staticmethod
    def draw_colonial(s, lay):
        col = lay.column(align=True)
        col.prop(s, "roof_pitch")
        col.prop(s, "roof_type")
        if s.roof_type == "GABLE":
            col.prop(s, "ridge")
        col.prop(s, "chimneys")
        col.prop(s, "rejas")
        col.prop(s, "balcony")
        col.prop(s, "bell_gable")
        lay.prop(s, "arcade")
        if s.arcade != "NONE":
            col = lay.column(align=True)
            col.prop(s, "arcade_posts")
            col.prop(s, "arcade_depth")
        lay.prop(s, "plan")
        if s.plan == "L":
            col = lay.column(align=True)
            col.prop(s, "wing_width")
            col.prop(s, "wing_depth")

    @staticmethod
    def draw_neoclassical(s, lay):
        lay.prop(s, "side_bays")
        col = lay.column(align=True)
        col.prop(s, "roof_pitch")
        col.prop(s, "cupola")
        col.prop(s, "flagpole")
        col.prop(s, "chimneys")
        col.prop(s, "shutters")
        col.prop(s, "window_caps")
        lay.prop(s, "portico")
        if s.portico:
            col = lay.column(align=True)
            col.prop(s, "columns")
            col.prop(s, "column_spacing")
            col.prop(s, "portico_depth")
        lay.prop(s, "back_portico")
        if s.back_portico == "BOW":
            col = lay.column(align=True)
            col.prop(s, "bow_radius")
            col.prop(s, "bow_columns")
        lay.prop(s, "wings")
        if s.wings:
            col = lay.column(align=True)
            col.prop(s, "wing_gap")
            col.prop(s, "wing_width")
            col.prop(s, "wing_depth")


class AOE3_PT_check_export(bpy.types.Panel):
    bl_label = "Check and Export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AoE3"

    def draw(self, context):
        s = context.scene.aoe3_building
        lay = self.layout
        row = lay.row(align=True)
        row.prop(s, "tri_budget")
        row.operator("aoe3.check_building", icon="CHECKMARK")
        lay.prop(s, "use_profile")
        icons = {"ERROR": "CANCEL", "WARNING": "ERROR", "INFO": "INFO"}
        for r in s.results:
            lay.label(text=r.message, icon=icons.get(r.level, "DOT"))
        lay.separator()
        lay.prop(s, "export_dir")
        row = lay.row(align=True)
        row.prop(s, "export_glb", toggle=True)
        row.prop(s, "export_fbx", toggle=True)
        row.prop(s, "export_obj", toggle=True)
        lay.operator("aoe3.export_building", icon="EXPORT")


class AOE3_PT_game_export(bpy.types.Panel):
    bl_label = "Game Export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AoE3"

    def draw(self, context):
        s = context.scene.aoe3_building
        lay = self.layout
        lay.prop(s, "game_dir")
        lay.prop(s, "game_prefix")
        lay.prop(s, "game_display")
        lay.prop(s, "game_template")
        lay.prop(s, "game_texture")
        lay.prop(s, "game_icons")
        row = lay.row(align=True)
        row.prop(s, "game_lowpoly", toggle=True)
        row.prop(s, "game_damaged", toggle=True)
        lay.operator("aoe3.export_game", icon="EXPORT")
        lay.separator()
        lay.prop(s, "game_install")
        lay.prop(s, "game_builder")
        row = lay.row(align=True)
        row.operator("aoe3.deploy_game", icon="PLAY")
        row.operator("aoe3.undo_deploy", icon="LOOP_BACK")


class AOE3_OT_deploy_game(bpy.types.Operator):
    bl_idname = "aoe3.deploy_game"
    bl_label = "Deploy to Test Copy"
    bl_description = ("Put the exported bundle into a test copy of the game (never a Steam folder): "
                      "art files, the unit and its strings; backups are kept for Undo")

    def execute(self, context):
        from .aoe3game import deploy
        s = context.scene.aoe3_building
        folder = bpy.path.abspath(s.game_dir)
        if not os.path.exists(os.path.join(folder, "bundle.json")):
            self.report({"ERROR"}, "No bundle there: run Export for the Game first")
            return {"CANCELLED"}
        try:
            d = deploy.Deployment(bpy.path.abspath(s.game_install))
            lines = []
            m = d.apply(folder, log=lines.append, builder=s.game_builder.strip() or None)
        except (deploy.RefusedPath, ValueError, OSError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Deployed {m.get('units')} as unit {m.get('unit_id')}; restart the game")
        return {"FINISHED"}


class AOE3_OT_undo_deploy(bpy.types.Operator):
    bl_idname = "aoe3.undo_deploy"
    bl_label = "Undo"
    bl_description = "Take the deployed building out of the test copy and restore its files"

    def execute(self, context):
        from .aoe3game import deploy
        s = context.scene.aoe3_building
        try:
            deploy.Deployment(bpy.path.abspath(s.game_install)).undo(log=lambda line: None)
        except (deploy.RefusedPath, OSError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Test copy restored")
        return {"FINISHED"}


CLASSES = (AOE3_PG_result, AOE3_PG_building, AOE3_OT_load_preset, AOE3_OT_generate_building,
           AOE3_OT_check_building, AOE3_OT_export_building, AOE3_OT_export_game,
           AOE3_OT_deploy_game, AOE3_OT_undo_deploy, AOE3_PT_building, AOE3_PT_check_export,
           AOE3_PT_game_export)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.aoe3_building = PointerProperty(type=AOE3_PG_building)
    ai_panel.register()


def unregister():
    ai_panel.unregister()
    del bpy.types.Scene.aoe3_building
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
