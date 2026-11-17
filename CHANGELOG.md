# Changelog

One version for the Blender add-on and AoE3 Mod Studio: `aoe3_blender_tools/blender_manifest.toml`
says it, the add-on's `bl_info` repeats it and the studio reads it (`tests/test_studio.py` holds the
three together).

## 0.3.0 (2026-11-17)

**AoE3 Mod Studio** (`studio/`, `docs/studio.md`): every tool of the repository in one window, in
English and Spanish, for modders who use neither Blender nor a terminal.

- Buildings: a form drawn from `core/schema.py`, the model in 3D as it changes, its texture, the
  triangle budget, the technical sheet, the add-on's checks (`scripts/check.py`), prop sets, the AI
  repaint region by region, exports, deployment to a test copy and undo.
- Screens made for their task: repaint a unit by its UV islands, design a civ flag set, make
  tileable textures from photographs, look inside `.ddt`, `.gr2`, `.xmb` and `.bar` files.
- Every command-line tool as a form with its live log; a trial before any change in place.
- A program without Python (`tools/build_app.py`), which uses an installed Blender for the exports.
- The rule that every new function reaches the studio, held by its tests (`studio/coverage.py`).

The add-on:

- `core/schema.py`: every `BuildingParams` field described for forms (held to the panel).
- `core/gamemesh.py`: the game mesh without Blender (as Blender's in 100 of 102 cases).
- `scripts/generate.py` and `scripts/game_export.py --params`: any building, not only a preset;
  `game_export.py --texture-png`: a texture made elsewhere in place of the painted one.
- `tools/fix_bone_scale.py`, `fix_hitpointbar_tags.py` and `make_icons.py --install` refuse a
  Steam library.

## 0.2.0

The add-on and the tools before the studio: the generators (neoclassical, colonial, timber,
African, props), the game formats and the deployment to a test copy, the surveys, the AI repaint and
texture maker, the unit retexturing, the art utilities.
