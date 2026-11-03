# SPDX-License-Identifier: GPL-3.0-or-later
"""AI Texture panel: repaints the active building's texture with a local ComfyUI (Stable
Diffusion + ControlNet, see docs/ai-textures.md), keeps the original to go back to, and lets the
game export use the result."""
import json
import os
import subprocess

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty

from .core import airepaint, blender_io, building, comfy

ORIG_SUFFIX = "_ai_orig"
COMFY_DIR = r"C:\ComfyUI\ComfyUI_windows_portable"
_REGIONS = {"key": None, "items": [("NONE", "(no building)", "")]}   # kept alive for Blender's enum


def _region_items(self, context):
    """The active building's regions, those with a built-in prompt first."""
    obj = context.active_object if context else None
    params = obj.get("aoe3_params") if obj is not None else None
    if not params:
        return [("NONE", "(select a building)", "")]
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
        return obj is not None and obj.type == "MESH" and "aoe3_params" in obj

    def _prepare(self, context):
        a = context.scene.aoe3_ai
        obj = context.active_object
        model = building.build(blender_io.params_of(obj))
        orig = _original(obj)
        if orig is None:
            orig = blender_io.image_copy(obj, obj.name + ORIG_SUFFIX)
            obj["aoe3_ai_orig"] = orig.name
        self._obj_name = obj.name
        self._args = dict(texture=blender_io.image_rgba(orig), model=model,
                          client=comfy.Client(a.url, timeout=120), strength=a.strength, seed=a.seed,
                          regions=[a.region] if a.regions == "ONE" else airepaint.group(model, a.regions),
                          extra=a.extra, blend=a.blend, prompt=a.prompt or None)
        self._settings = {"strength": a.strength, "seed": a.seed, "extra": a.extra, "blend": a.blend,
                          "prompt": a.prompt}

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
        self._prepare(context)
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
        self._prepare(context)
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
        col = lay.column(align=True)
        col.prop(a, "strength")
        col.prop(a, "blend")
        col.prop(a, "seed")
        col.prop(a, "regions")
        if a.regions == "ONE":
            col.prop(a, "region", text="")
            obj = context.active_object
            if obj is not None and obj.get("aoe3_params") and a.region not in ("", "NONE"):
                builtin = airepaint.material_of(a.region, blender_io.params_of(obj))
                lay.label(text=f"Built-in: {builtin}" if builtin else "No built-in prompt: write yours",
                          icon="TEXT")
        lay.prop(a, "prompt")
        lay.prop(a, "extra")
        lay.operator("aoe3.ai_repaint", icon="BRUSH_DATA")
        lay.operator("aoe3.ai_revert", icon="LOOP_BACK")
        obj = context.active_object
        if obj is not None and "aoe3_ai" in obj:
            lay.label(text="Repainted: Generate Building would replace it", icon="INFO")
        if a.status:
            lay.label(text=a.status)


CLASSES = (AOE3_PG_ai, AOE3_OT_ai_check, AOE3_OT_ai_start, AOE3_OT_ai_repaint, AOE3_OT_ai_revert, AOE3_PT_ai)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.aoe3_ai = bpy.props.PointerProperty(type=AOE3_PG_ai)


def unregister():
    del bpy.types.Scene.aoe3_ai
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
