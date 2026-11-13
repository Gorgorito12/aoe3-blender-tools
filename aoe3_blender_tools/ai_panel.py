# SPDX-License-Identifier: GPL-3.0-or-later
"""Two panels that talk to a local ComfyUI (Stable Diffusion + ControlNet, see
docs/ai-textures.md).

AI Texture repaints the active model's own texture - a generated building, or a mesh someone else
made (core/meshtex.py) - keeps the original to go back to, and lets the game export use the
result.

Texture Maker makes a seamless, tileable swatch from a picture or from a description
(core/texmaker.py) and keeps it in the library with its licence and what it was made from
(core/texlib.py); it can then be laid under the painting in place of a swatch that ships with
the add-on. See docs/texture-maker.md."""
import json
import os
import subprocess

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from .core import airepaint, blender_io, building, comfy, meshtex, texlib, texmaker

ORIG_SUFFIX = "_ai_orig"
COMFY_DIR = r"C:\ComfyUI\ComfyUI_windows_portable"
_REGIONS = {"key": None, "items": [("NONE", "(no building)", "")]}   # kept alive for Blender's enum


def _is_mesh(obj):
    """A mesh we can repaint that the generator did not make."""
    return (obj is not None and obj.type == "MESH" and "aoe3_params" not in obj
            and obj.data.uv_layers and blender_io._object_image(obj) is not None)


def _region_items(self, context):
    """The regions of the active building, those with a built-in prompt first; or, for a mesh we
    did not generate, one zone per material slot."""
    obj = context.active_object if context else None
    params = obj.get("aoe3_params") if obj is not None else None
    if not params:
        if not _is_mesh(obj):
            return [("NONE", "(select a building or a textured mesh)", "")]
        try:
            zones = blender_io.uv_zones(obj)
        except ValueError as e:
            return [("NONE", f"({e})", "")]
        key = (obj.name, tuple(z[0] for z in zones))
        if _REGIONS["key"] != key:
            _REGIONS["items"] = [(z[0], z[0], "The UVs of a material slot: write your own prompt")
                                 for z in zones]
            _REGIONS["key"] = key
        return _REGIONS["items"]
    if _REGIONS["key"] != params:
        p = blender_io.params_of(obj)
        model = building.build(p)
        names = sorted(model.atlas.regions, key=lambda n: (airepaint.material_of(n, p) is None, n))
        _REGIONS["items"] = [(n, n + ("" if airepaint.material_of(n, p) else "  (no built-in prompt)"),
                              airepaint.material_of(n, p) or "No built-in prompt: write one") for n in names]
        _REGIONS["key"] = params
    return _REGIONS["items"]


class AOE3_PG_ai(bpy.types.PropertyGroup):
    url: StringProperty(name="ComfyUI", default=comfy.DEFAULT_URL,
                        description="Address of the local ComfyUI server")
    strength: FloatProperty(name="Strength", default=0.45, min=0.1, max=0.85,
                            description="How much the AI repaints (denoise): low keeps the drawing, "
                                        "high invents more")
    seed: IntProperty(name="Seed", default=1, min=0)
    extra: StringProperty(name="Extra prompt", default="",
                          description="Words added to every region's prompt (e.g. 'weathered, mossy')")
    prompt: StringProperty(name="Your prompt", default="",
                           description="Your own description of the material (e.g. 'red mud wall with "
                                       "white painted zigzags'); replaces the built-in one. Empty: "
                                       "the built-in prompt of each region")
    regions: EnumProperty(name="Regions", items=[
        ("ALL", "All", "Every region that has a prompt"),
        ("WALLS", "Walls", "Facades and gables only"),
        ("ROOFS", "Roofs", "Roofs only"),
        ("ONE", "One region", "Only the region chosen below")], default="ALL")
    region: EnumProperty(name="Region", items=_region_items,
                         description="The part of the texture to repaint")
    comfy_dir: StringProperty(name="ComfyUI folder", default=COMFY_DIR, subtype="DIR_PATH",
                              description="The portable ComfyUI folder (it has python_embeded)")
    blend: FloatProperty(name="Blend", default=1.0, min=0.0, max=1.0, subtype="FACTOR",
                         description="Mix of the repaint over the original")
    status: StringProperty(default="")
    lora: StringProperty(name="LoRA", default="",
                         description="A LoRA of ComfyUI's models/loras to paint with, e.g. one trained "
                                     "on the mod's own textures (tools/train_lora.py); empty: none")
    lora_strength: FloatProperty(name="LoRA strength", default=0.8, min=0.0, max=1.5)
    # -- the texture maker (a tileable swatch, not a model's atlas) --
    tex_source: StringProperty(name="Reference", default="", subtype="FILE_PATH",
                               description="A picture to make the texture from (JPEG, PNG...); "
                                           "empty: from the prompt alone")
    tex_prompt: StringProperty(name="Material", default="",
                               description="The material in your own words ('rusted corrugated "
                                           "iron roof'); with a reference it says what to make of it")
    tex_name: StringProperty(name="Name", default="",
                             description="The file name in the library (no folder, no extension)")
    tex_size: EnumProperty(name="Size", items=[("128", "128", "A small swatch"),
                                               ("256", "256", "What the add-on's own swatches are"),
                                               ("512", "512", "Twice that, for a close material")],
                           default="256")
    tex_strength: FloatProperty(name="Strength", default=0.6, min=0.1, max=0.95,
                                description="How far the AI takes the reference away from the "
                                            "photograph (denoise); it is not used without one")
    tex_seed: IntProperty(name="Seed", default=1, min=0)
    tex_tile_m: FloatProperty(name="Metres a tile", default=2.0, min=0.1, max=20.0,
                              description="How many metres of a building one tile of this texture "
                                          "covers, when the painter lays it")
    tex_style: StringProperty(name="Style", default="",
                              description="The style whose swatch this texture replaces "
                                          "(NEOCLASSICAL, COLONIAL, TIMBER, AFRICAN); empty: none")
    tex_role: StringProperty(name="Role", default="",
                             description="What it is for in that style (wall, roof, plinth, "
                                         "timber, stone...); empty: none")
    tex_licence: StringProperty(name="Licence", default="",
                                description="Where this texture may be used and on whose terms "
                                            "('my own photograph', 'generated locally'). Required: "
                                            "it is written beside the texture")
    tex_folder: StringProperty(name="Library", default="", subtype="DIR_PATH",
                               description="Where the textures are kept (empty: Documents/"
                                           "aoe3-blender-tools/textures)")
    tex_light: BoolProperty(name="Take the light out", default=True,
                            description="Divide out the broad light and shade a photograph carries")
    tex_heal: BoolProperty(name="Hide the blend", default=True,
                           description="Let the AI redraw the band that makes the texture tile "
                                       "(it never touches the borders)")
    tex_material: StringProperty(name="Of", default="",
                                 description="What it is a texture of (wood, stone, brick, roof, "
                                             "thatch, metal, cloth, plaster, earth): the mod's own "
                                             "textures of that material are what it is measured against")
    tex_category: StringProperty(name="For", default="buildings",
                                 description="What it is for (buildings, units, nuggets, objects)")
    tex_fit: BoolProperty(name="Fit to the mod", default=True,
                          description="Bring its grain and saturation to the median of the mod's own "
                                      "textures of that kind (Stable Diffusion paints far more "
                                      "saturated than a game does)")
    tex_crop_x: FloatProperty(name="Centre x", default=0.5, min=0.0, max=1.0, subtype="FACTOR")
    tex_crop_y: FloatProperty(name="Centre y", default=0.5, min=0.0, max=1.0, subtype="FACTOR")
    tex_crop: FloatProperty(name="Part", default=1.0, min=0.02, max=1.0, subtype="FACTOR",
                            description="How much of the picture's shorter side to take")
    tex_status: StringProperty(default="")


def _original(obj):
    name = obj.get("aoe3_ai_orig")
    return bpy.data.images.get(name) if name else None


class AOE3_OT_ai_check(bpy.types.Operator):
    bl_idname = "aoe3.ai_check"
    bl_label = "Check ComfyUI"
    bl_description = "Is the local ComfyUI running, with the nodes and the models the repaint needs?"

    def execute(self, context):
        a = context.scene.aoe3_ai
        try:
            problems = comfy.Client(a.url, timeout=5).check()
        except comfy.ComfyError as e:
            a.status = str(e)
            self.report({"ERROR"}, a.status)
            return {"CANCELLED"}
        a.status = "; ".join(problems) if problems else "ComfyUI ready"
        self.report({"ERROR" if problems else "INFO"}, a.status)
        return {"FINISHED"} if not problems else {"CANCELLED"}


class AOE3_OT_ai_repaint(bpy.types.Operator):
    bl_idname = "aoe3.ai_repaint"
    bl_label = "AI Repaint"
    bl_description = ("Repaint the building's texture region by region with the local ComfyUI; the drawing, "
                      "the alpha and the player colour stay in place. Always starts from the original")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return False
        return "aoe3_params" in obj or _is_mesh(obj)

    def _prepare(self, context):
        """Fills in the repaint arguments, or returns why it cannot."""
        a = context.scene.aoe3_ai
        obj = context.active_object
        orig = _original(obj)
        if orig is None:
            orig = blender_io.image_copy(obj, obj.name + ORIG_SUFFIX)
            obj["aoe3_ai_orig"] = orig.name
        texture = blender_io.image_rgba(orig)
        params = blender_io.params_of(obj)
        if params is not None:
            model = building.build(params)
            regions = [a.region] if a.regions == "ONE" else airepaint.group(model, a.regions)
        else:                                   # a mesh someone else modelled: its own UV zones
            h, w = texture.shape[:2]
            if w != h:
                return f"the texture is {w} x {h}: a square texture is needed to repaint a mesh"
            prompt = (a.prompt or "").strip()
            if not prompt:
                return "write a prompt: a mesh we did not generate has no built-in materials"
            try:
                zones = blender_io.uv_zones(obj)
                model = meshtex.model_for(zones, w, prompts={z[0]: prompt for z in zones})
            except ValueError as e:
                return str(e)
            regions = [a.region] if a.regions == "ONE" else None
        self._obj_name = obj.name
        self._args = dict(texture=texture, model=model,
                          client=comfy.Client(a.url, timeout=120), strength=a.strength, seed=a.seed,
                          regions=regions, extra=a.extra, blend=a.blend, prompt=a.prompt or None)
        if (a.lora or "").strip():
            self._args["workflow_args"] = {"lora": a.lora.strip(), "lora_strength": a.lora_strength}
            self._args["extra"] = ", ".join(x for x in (a.extra, texmaker.TRIGGER) if x)
        self._settings = {"strength": a.strength, "seed": a.seed, "extra": a.extra, "blend": a.blend,
                          "prompt": a.prompt}
        return None

    def _finish(self, context, out, report):
        a = context.scene.aoe3_ai
        obj = bpy.data.objects.get(self._obj_name)
        blender_io.set_texture_rgba(obj, out)
        done = [r for r in report if "skipped" not in r]
        obj["aoe3_ai"] = json.dumps({**self._settings, "regions": [r["region"] for r in done]})
        secs = sum(r["seconds"] for r in done)
        kept = [r["region"] for r in report if "kept" in r.get("skipped", "")]
        a.status = f"{len(done)} regions repainted in {secs:.0f} s" + (f"; kept {', '.join(kept)}" if kept else "")
        self.report({"INFO"}, a.status)

    def execute(self, context):
        """Blocking: scripts and tests."""
        problem = self._prepare(context)
        if problem:
            context.scene.aoe3_ai.status = problem
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        try:
            out, report = airepaint.repaint(**self._args)
        except comfy.ComfyError as e:
            context.scene.aoe3_ai.status = str(e)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self._finish(context, out, report)
        return {"FINISHED"}

    # -- the button: the repaint runs in a thread (HTTP and numpy only), Blender stays responsive
    def invoke(self, context, event):
        import threading
        problem = self._prepare(context)
        if problem:
            context.scene.aoe3_ai.status = problem
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        self._state = {"progress": "starting", "result": None, "error": None, "cancel": False,
                       "preview": None}
        state = self._state

        def progress(i, n, name):
            if state["cancel"]:
                raise comfy.ComfyError("cancelled")
            state["progress"] = f"repainting {name} ({i + 1}/{n}), Esc cancels"

        def work():
            try:
                state["result"] = airepaint.repaint(**self._args, on_progress=progress,
                                                    on_region=lambda t: state.__setitem__("preview", t))
            except Exception as e:            # reported in the panel, never lost in the thread
                state["error"] = str(e)

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        a = context.scene.aoe3_ai
        if event.type == "ESC":
            self._state["cancel"] = True
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        a.status = self._state["progress"]
        preview, self._state["preview"] = self._state["preview"], None
        obj = bpy.data.objects.get(self._obj_name)
        if preview is not None and obj is not None:          # live: each region as it is done
            blender_io.set_texture_rgba(obj, preview)
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
        if self._thread.is_alive():
            return {"PASS_THROUGH"}
        context.window_manager.event_timer_remove(self._timer)
        if self._state["error"]:
            a.status = self._state["error"]
            self.report({"ERROR"}, a.status)
            return {"CANCELLED"}
        self._finish(context, *self._state["result"])
        return {"FINISHED"}


class AOE3_OT_ai_start(bpy.types.Operator):
    bl_idname = "aoe3.ai_start"
    bl_label = "Start ComfyUI"
    bl_description = ("Start the local ComfyUI in its own window (about 20 s); close that window to "
                      "stop it")

    def execute(self, context):
        a = context.scene.aoe3_ai
        if comfy.Client(a.url, timeout=3).alive():
            a.status = "ComfyUI is already running"
            return {"FINISHED"}
        root = bpy.path.abspath(a.comfy_dir)
        exe = os.path.join(root, "python_embeded", "python.exe")
        main = os.path.join(root, "ComfyUI", "main.py")
        if not (os.path.isfile(exe) and os.path.isfile(main)):
            a.status = f"no portable ComfyUI in {root}"
            self.report({"ERROR"}, a.status)
            return {"CANCELLED"}
        port = a.url.rstrip("/").rsplit(":", 1)[-1]
        port = port if port.isdigit() else "8188"
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen([exe, "-s", main, "--windows-standalone-build", "--listen", "127.0.0.1", "--port", port,
                          "--disable-auto-launch"], cwd=root, creationflags=flags)
        a.status = "ComfyUI starting: press the check mark in about 20 s"
        self.report({"INFO"}, a.status)
        return {"FINISHED"}


class AOE3_OT_ai_revert(bpy.types.Operator):
    bl_idname = "aoe3.ai_revert"
    bl_label = "Back to the Original"
    bl_description = "Put the texture back as it was before the AI repaint"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and _original(obj) is not None

    def execute(self, context):
        obj = context.active_object
        orig = _original(obj)
        blender_io.set_texture_rgba(obj, blender_io.image_rgba(orig))
        bpy.data.images.remove(orig)
        del obj["aoe3_ai_orig"]
        if "aoe3_ai" in obj:
            del obj["aoe3_ai"]
        context.scene.aoe3_ai.status = "original texture back"
        return {"FINISHED"}


class AOE3_PT_ai(bpy.types.Panel):
    bl_label = "AI Texture"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AoE3"

    def draw(self, context):
        a = context.scene.aoe3_ai
        lay = self.layout
        row = lay.row(align=True)
        row.prop(a, "url", text="")
        row.operator("aoe3.ai_check", text="", icon="CHECKMARK")
        lay.operator("aoe3.ai_start", icon="PLAY")
        row = lay.row(align=True)
        row.prop(a, "lora")
        if a.lora:
            row.prop(a, "lora_strength", text="")
        col = lay.column(align=True)
        col.prop(a, "strength")
        col.prop(a, "blend")
        col.prop(a, "seed")
        col.prop(a, "regions")
        obj = context.active_object
        if a.regions == "ONE":
            col.prop(a, "region", text="")
            if obj is not None and obj.get("aoe3_params") and a.region not in ("", "NONE"):
                builtin = airepaint.material_of(a.region, blender_io.params_of(obj))
                lay.label(text=f"Built-in: {builtin}" if builtin else "No built-in prompt: write yours",
                          icon="TEXT")
        if _is_mesh(obj):
            lay.label(text="A mesh we did not generate: your prompt is required", icon="INFO")
        lay.prop(a, "prompt")
        lay.prop(a, "extra")
        lay.operator("aoe3.ai_repaint", icon="BRUSH_DATA")
        lay.operator("aoe3.ai_revert", icon="LOOP_BACK")
        if obj is not None and "aoe3_ai" in obj:
            lay.label(text="Repainted: Generate Building would replace it", icon="INFO")
        if a.status:
            lay.label(text=a.status)


class AOE3_OT_make_texture(bpy.types.Operator):
    bl_idname = "aoe3.make_texture"
    bl_label = "Make the Texture"
    bl_description = ("Make a seamless, tileable texture from a reference picture or from the "
                      "material you describe, and keep it in the library with what it was made from")

    def _prepare(self, context):
        a = context.scene.aoe3_ai
        name = (a.tex_name or "").strip()
        if not name:
            return "give the texture a name"
        if not (a.tex_licence or "").strip():
            return ("say under what licence it may be used (a photograph carries the rights of "
                    "whoever took it)")
        prompt = (a.tex_prompt or "").strip()
        source = None
        if (a.tex_source or "").strip():
            try:
                source = texmaker.crop(blender_io.image_rgb(a.tex_source),
                                       (a.tex_crop_x, a.tex_crop_y), a.tex_crop)
            except (RuntimeError, ValueError, OSError) as e:
                return str(e)
        elif not prompt:
            return "give a reference picture, or describe the material"
        client = comfy.Client(a.url, timeout=180)
        if source is None or prompt:
            if not client.alive():
                if source is None:
                    return f"ComfyUI does not answer at {a.url}: a prompt alone needs it"
                client = None                  # a reference and no ComfyUI: the plain path
        else:
            client = None                      # a reference and no words: nothing to ask the AI
        self._name = name
        self._args = dict(source=source, prompt=prompt, client=client, size=int(a.tex_size),
                          seed=a.tex_seed, strength=a.tex_strength, light=a.tex_light,
                          heal_band=a.tex_heal, material=(a.tex_material or "").strip().lower(),
                          category=(a.tex_category or "buildings").strip().lower(), fit=a.tex_fit,
                          lora=(a.lora or "").strip() or None, lora_strength=a.lora_strength)
        self._save = dict(licence=a.tex_licence, folder=a.tex_folder or None, tile_m=a.tex_tile_m,
                          role=(a.tex_role or "").strip(), style=(a.tex_style or "").strip(),
                          source=os.path.basename(bpy.path.abspath(a.tex_source)) if a.tex_source else "",
                          strength=a.tex_strength if source is not None else None)
        return None

    def _finish(self, context, out, report):
        a = context.scene.aoe3_ai
        entry = texlib.save(out, self._name, report=report, **self._save)
        blender_io._image_from_array(self._name, np.dstack(
            [out, np.full(out.shape[:2] + (1,), 255, np.uint8)]))
        where = texlib.folder_of(a.tex_folder or None)
        used = ""
        if entry["style"] and entry["role"]:
            texlib.install(folder=a.tex_folder or None, names=[self._name])
            used = f"; it replaces {entry['style']} {entry['role']} when painting"
        note = f"; {report['note']}" if report.get("note") else ""
        st = report.get("style")
        if st:
            note = f"; {st['off']} widths from {st['against']}" + note
        a.tex_status = (f"{self._name}: {entry['size']} px, join {report['seam']}, "
                        f"{report['seconds']} s, in {where}{used}{note}")
        self.report({"INFO"}, a.tex_status)

    def execute(self, context):
        """Blocking: scripts and tests."""
        problem = self._prepare(context)
        if problem:
            context.scene.aoe3_ai.tex_status = problem
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        try:
            out, report = texmaker.make(**self._args)
        except (comfy.ComfyError, ValueError, OSError) as e:
            context.scene.aoe3_ai.tex_status = str(e)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self._finish(context, out, report)
        return {"FINISHED"}

    # -- the button: the work runs in a thread (HTTP and numpy only), Blender stays responsive
    def invoke(self, context, event):
        import threading
        problem = self._prepare(context)
        if problem:
            context.scene.aoe3_ai.tex_status = problem
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        self._state = {"progress": "starting", "result": None, "error": None}
        state = self._state

        def work():
            try:
                state["result"] = texmaker.make(
                    **self._args, on_progress=lambda s: state.__setitem__("progress", s))
            except Exception as e:                  # reported in the panel, never lost in the thread
                state["error"] = str(e)

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        a = context.scene.aoe3_ai
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        a.tex_status = self._state["progress"]
        for area in context.screen.areas:
            if area.type in ("VIEW_3D", "IMAGE_EDITOR"):
                area.tag_redraw()
        if self._thread.is_alive():
            return {"PASS_THROUGH"}
        context.window_manager.event_timer_remove(self._timer)
        if self._state["error"]:
            a.tex_status = self._state["error"]
            self.report({"ERROR"}, a.tex_status)
            return {"CANCELLED"}
        self._finish(context, *self._state["result"])
        return {"FINISHED"}


class AOE3_OT_use_textures(bpy.types.Operator):
    bl_idname = "aoe3.use_textures"
    bl_label = "Use the Library"
    bl_description = ("Lay the library's textures under the painting wherever their style and role "
                      "say, in place of the swatches that ship with the add-on; press again to put "
                      "those back. Generate Building then paints with them")

    def execute(self, context):
        a = context.scene.aoe3_ai
        if texlib._installed:
            texlib.uninstall()
            a.tex_status = "the add-on's own swatches are back"
        else:
            chosen = texlib.install(folder=a.tex_folder or None)
            a.tex_status = (", ".join(f"{s} {r}: {n}" for (s, r), n in sorted(chosen.items()))
                            or "no texture in the library names a style and a role")
        self.report({"INFO"}, a.tex_status)
        return {"FINISHED"}


class AOE3_PT_texture_maker(bpy.types.Panel):
    bl_label = "Texture Maker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AoE3"

    def draw(self, context):
        a = context.scene.aoe3_ai
        lay = self.layout
        lay.prop(a, "tex_source")
        if a.tex_source:
            row = lay.row(align=True)
            row.prop(a, "tex_crop_x", text="x")
            row.prop(a, "tex_crop_y", text="y")
            row.prop(a, "tex_crop", text="part")
        lay.prop(a, "tex_prompt")
        col = lay.column(align=True)
        col.prop(a, "tex_name")
        col.prop(a, "tex_licence")
        row = lay.row(align=True)
        row.prop(a, "tex_size")
        lay.prop(a, "tex_tile_m")
        if a.tex_source:
            lay.prop(a, "tex_strength")
        lay.prop(a, "tex_seed")
        row = lay.row(align=True)
        row.prop(a, "tex_light", toggle=True)
        row.prop(a, "tex_heal", toggle=True)
        row = lay.row(align=True)
        row.prop(a, "tex_material")
        row.prop(a, "tex_category")
        lay.prop(a, "tex_fit")
        row = lay.row(align=True)
        row.prop(a, "tex_style")
        row.prop(a, "tex_role")
        lay.prop(a, "tex_folder")
        lay.operator("aoe3.make_texture", icon="TEXTURE")
        lay.operator("aoe3.use_textures",
                     text="Back to the Add-on's Swatches" if texlib._installed else "Use the Library",
                     icon="CHECKMARK" if texlib._installed else "IMPORT")
        if a.tex_status:
            lay.label(text=a.tex_status)


CLASSES = (AOE3_PG_ai, AOE3_OT_ai_check, AOE3_OT_ai_start, AOE3_OT_ai_repaint, AOE3_OT_ai_revert,
           AOE3_PT_ai, AOE3_OT_make_texture, AOE3_OT_use_textures, AOE3_PT_texture_maker)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.aoe3_ai = bpy.props.PointerProperty(type=AOE3_PG_ai)


def unregister():
    del bpy.types.Scene.aoe3_ai
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
