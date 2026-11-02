# SPDX-License-Identifier: GPL-3.0-or-later
"""AoE3 Blender Tools: a low-poly building generator, game-ready checks and exports for Age of
Empires III mods. Panel: 3D Viewport > Sidebar (N) > AoE3."""

bl_info = {      # read only by Blender versions without extensions; 4.2+ reads blender_manifest.toml
    "name": "AoE3 Blender Tools",
    "author": "Gorgorito12",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > AoE3",
    "description": "Low-poly building generator, game-ready checks and exports for Age of Empires III mods",
    "category": "Object",
}

import bpy  # noqa: E402
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,  # noqa: E402
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

from .core import blender_io, building, paint, validate  # noqa: E402

COLOR_KEYS = ("wall", "trim", "roof", "glass", "door", "brick", "lead", "stone", "plinth")
PRESET_ITEMS = [(k, k.replace("_", " ").title(), "") for k in building.PRESETS]


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
    width: FloatProperty(name="Width", default=14.0, min=4.0, max=60.0, unit="LENGTH")
    depth: FloatProperty(name="Depth", default=9.0, min=4.0, max=60.0, unit="LENGTH")
    storeys: IntProperty(name="Storeys", default=2, min=1, max=4)
    plinth: FloatProperty(name="Plinth", default=0.8, min=0.2, max=2.0, unit="LENGTH")
    roof_pitch: FloatProperty(name="Roof pitch", default=0.54, min=0.15, max=1.5,
                              description="Rise over run, the same on all four sides")
    bay_spacing: FloatProperty(name="Window spacing", default=1.8, min=1.3, max=6.0, unit="LENGTH")
    portico: BoolProperty(name="Portico", default=True)
    columns: IntProperty(name="Columns", default=4, min=2, max=8, step=2)
    column_spacing: FloatProperty(name="Column spacing", default=1.8, min=1.2, max=4.0, unit="LENGTH")
    portico_depth: FloatProperty(name="Portico depth", default=3.3, min=1.5, max=8.0, unit="LENGTH")
    cupola: BoolProperty(name="Cupola", default=True)
    chimneys: IntProperty(name="Chimneys", default=1, min=0, max=2)
    texture_size: EnumProperty(name="Texture", items=[("512", "512", ""), ("1024", "1024", ""),
                                                      ("2048", "2048", "")], default="1024")
    seed: IntProperty(name="Seed", default=1870)
    show_colors: BoolProperty(name="Colours", default=False)
    tri_budget: IntProperty(name="Triangle budget", default=6000, min=100)
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



def params_from_props(s):
    p = building.BuildingParams(
        name=s.name.strip() or "Building", width=s.width, depth=s.depth, storeys=s.storeys,
        plinth=s.plinth, roof_pitch=s.roof_pitch, bay_spacing=s.bay_spacing, portico=s.portico,
        columns=s.columns, column_spacing=s.column_spacing, portico_depth=s.portico_depth,
        cupola=s.cupola, chimneys=s.chimneys, texture_size=int(s.texture_size), seed=s.seed)
    p.colors = {k: tuple(int(round(c * 255)) for c in getattr(s, "color_" + k)) for k in COLOR_KEYS}
    return p


def props_from_params(s, p):
    for attr in ("name", "width", "depth", "storeys", "plinth", "roof_pitch", "bay_spacing", "portico",
                 "columns", "column_spacing", "portico_depth", "cupola", "chimneys", "seed"):
        setattr(s, attr, getattr(p, attr))
    s.texture_size = str(p.texture_size)
    for k in COLOR_KEYS:
        setattr(s, "color_" + k, tuple(c / 255.0 for c in p.colors[k]))


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
        texture = paint.paint(model)
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
        res = validate.check(context.active_object, s.tri_budget)
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
        col = lay.column(align=True)
        col.prop(s, "width")
        col.prop(s, "depth")
        col.prop(s, "storeys")
        col.prop(s, "plinth")
        col.prop(s, "bay_spacing")
        col = lay.column(align=True)
        col.prop(s, "roof_pitch")
        col.prop(s, "cupola")
        col.prop(s, "chimneys")
        lay.prop(s, "portico")
        if s.portico:
            col = lay.column(align=True)
            col.prop(s, "columns")
            col.prop(s, "column_spacing")
            col.prop(s, "portico_depth")
        row = lay.row(align=True)
        row.prop(s, "texture_size")
        row.prop(s, "seed")
        lay.prop(s, "show_colors", icon="TRIA_DOWN" if s.show_colors else "TRIA_RIGHT", emboss=False)
        if s.show_colors:
            grid = lay.grid_flow(columns=3, align=True)
            for k in COLOR_KEYS:
                grid.prop(s, "color_" + k, text=k.title())
        lay.operator("aoe3.generate_building", icon="HOME")


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


CLASSES = (AOE3_PG_result, AOE3_PG_building, AOE3_OT_load_preset, AOE3_OT_generate_building,
           AOE3_OT_check_building, AOE3_OT_export_building, AOE3_PT_building, AOE3_PT_check_export)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.aoe3_building = PointerProperty(type=AOE3_PG_building)


def unregister():
    del bpy.types.Scene.aoe3_building
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
