# SPDX-License-Identifier: GPL-3.0-or-later
"""Where each function of the Blender add-on is in the studio: the rule that every function of
this repository can be used from the studio (CLAUDE.md, "Every function reaches the studio").

Each operator the add-on registers maps to its place: "screen:<route>" (a screen of the page:
studio/web/js/app.js), "tool:<id>" (a form of studio/catalog.py), or "pending:<why>" while it is
not there yet. tests/run_tests.py fails on an operator missing from this map, and
tests/test_studio.py on a place that does not exist; docs/studio.md lists what is pending.

The command-line tools need no entry: every script of tools/ and scripts/ has its form, which
tests/test_studio.py checks, and every BuildingParams field its place in core/schema.py.
Standard library only: Blender's tests import it.
"""

OPERATORS = {
    "aoe3.load_preset": ("screen:buildings", "the presets of the building screen"),
    "aoe3.generate_building": ("screen:buildings", "the live preview: every change rebuilds the model"),
    "aoe3.check_building": ("screen:buildings", "Check, in the Export card (scripts/check.py)"),
    "aoe3.export_building": ("screen:buildings", "GLB, FBX, OBJ in the Export card"),
    "aoe3.export_game": ("screen:buildings", "Export for the game"),
    "aoe3.deploy_game": ("tool:deploy", "Deploy in the building screen, or the deploy form"),
    "aoe3.undo_deploy": ("tool:deploy_undo", "Undo in the building screen, or the undo form"),
    "aoe3.import_gr2": ("screen:inspect", "a game model in 3D with its bones and texture"),
    "aoe3.generate_set": ("screen:buildings", "the prop set's preview, with the PROP style"),
    "aoe3.pack_set": ("pending:packs meshes modelled in Blender: the studio has no meshes of its own to pack yet",
                      "core/group.pack_objects needs Blender objects"),
    "aoe3.export_set": ("tool:game_export_set", "the prop set's export, in the building screen or its form"),
    "aoe3.compose_settlement": ("pending:the settlement composer on a map is in the next round", ""),
    "aoe3.export_grouping": ("pending:comes with the settlement composer", ""),
    "aoe3.import_grouping": ("pending:comes with the settlement composer", ""),
    "aoe3.ai_check": ("screen:settings", "Check ComfyUI: which nodes and models it lacks"),
    "aoe3.ai_repaint": ("screen:buildings", "AI repaint, region by region (generated buildings; a mesh made "
                                            "elsewhere is pending)"),
    "aoe3.ai_start": ("screen:settings", "Start ComfyUI"),
    "aoe3.ai_revert": ("screen:buildings", "Back to the painted texture, in the AI card"),
    "aoe3.make_texture": ("screen:texmaker", "Make a tileable texture"),
    "aoe3.use_textures": ("screen:texmaker", "Use it in the buildings"),
}

# the routes of the page (studio/web/js/app.js): areas and screens made for their task
SCREENS = ("buildings", "textures", "survey", "art", "jobs", "settings", "dev", "inspect", "retex", "flags",
           "texmaker")


def place(operator):
    """(kind, target, note) of an operator: kind is screen, tool or pending."""
    where, note = OPERATORS[operator]
    kind, _, target = where.partition(":")
    return kind, target, note


def pending():
    """{operator: why} of what the studio does not do yet."""
    return {op: place(op)[1] for op in OPERATORS if place(op)[0] == "pending"}
