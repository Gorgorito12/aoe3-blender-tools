# Changelog

One version for the Blender add-on and AoE3 Mod Studio: `aoe3_blender_tools/blender_manifest.toml`
says it, the add-on's `bl_info` repeats it and the studio reads it (`tests/test_studio.py` holds the
three together).

## Unreleased

- `tools/make_rings.py`: range rings up to 100 m (18, 22, 26, 28, 32, 36, 40, 45, 50, 60, 70, 80 and 100 added; the
  line widens a little on the large ones), and the markers' floating icons redrawn as cartoons by the new
  `tools/cartoon_icons.py` (shapes as signed distances, flat colours, a light tone per part, a thick dark outline):
  a pickaxe over a nugget for gold, an axe for wood, a leg of meat for food, and `aura_hunt`, `aura_berry`,
  `aura_farm`, `aura_fish` with a bow, berries, an ear of wheat and a fish; 128-texel BGRA so the colours stay flat.

- `tools/make_command_icon.py`: command button icons in the style of Wars of Liberty's own on / off buttons
  (64x64 BGRA, a mottled blue frame, a green tick for "on", a red tint and cross for "off"), drawn from
  code; the first glyph, `autoscout`, a map half explored with a dotted route and a spyglass, for the
  auto scout buttons. Test: `tests/test_command_icons.py`.

- **A copy's fonts** (`tools/game_fonts.py`, two forms in Art utilities): which letters each typeface of
  `fonts3.xml` lacks, and every font with a file extended at once (`extend_font.py`) under a new family
  name, with `fonts3.xml` pointed at them, ready to deploy to the test copy and undo. What the Wars of
  Liberty fonts fix did by hand, for any mod: on a WoL copy it gives the same 108 + 4 + 4 letters and 113
  changed entries. The game interface screen finds loose fonts of `FONTS\` first, so it draws with
  them; deploying a folder accepts `FONTS` beside `data` and `art`.

- `aoe3game/gr2_edit.py`: a model's whole tree copied and written again (all 16,294 models of a
  WoL copy's cache come back with the same tree and a valid CRC), the start of a unit transplant.
  `tools/gr2_check.py` (a form in Art utilities): the game's own granny2.dll reads a model and its
  rewrite, beside the studio's reader (the helper's new `info` verb); alike on 400 of 400.

- `aoe3game/gr2_skin.py`: a unit's skeleton with its rotations followed (every bone's local, world
  and bind frame), four bones and weights a vertex, skinning to a pose. The model reader places
  the bones with it (they were placed by their positions alone). Measured: a unit's rest pose is
  its bind pose in 96.9 % of the skinned models (`docs/game-formats.md` said otherwise).
- Import a Game Model (Blender): a unit comes in with an Armature (its bones where the game has
  them), a vertex group per bone with its weights and an Armature modifier, so posing a bone moves
  the mesh as the game does; each bone keeps its frame in the file (`aoe3_frame`).

- **Your own model** (`scripts/mesh_to_game.py`, a studio screen and form): a static `.obj`, `.glb`
  or `.gltf` as a game building or prop without Blender: read (`core/objio.py`, `core/glbio.py`),
  sized in metres or game units, set on the ground, checked, seen in 3D beside a person, exported
  by the same bundle writer.

- `tools/recolor_textures.py` (and its studio form, Textures and units): recolours textures in OKLCH,
  only the hues you choose, keeping each file's header, alpha and mip levels, and reports CIEDE2000 to the
  player colours before and after. Made for a terrain whose red hid player 2.

## 0.3.0 (2026-11-17)

**AoE3 Mod Studio** (`studio/`, `docs/studio.md`): every tool of the repository in one window, in
English and Spanish, for modders who use neither Blender nor a terminal.

- Buildings: a form drawn from `core/schema.py`, the model in 3D as it changes, its texture, the
  triangle budget, the technical sheet, the add-on's checks (`scripts/check.py`), prop sets, the AI
  repaint region by region, exports, deployment to a test copy and undo.
- Screens made for their task: repaint a unit by its UV islands, design a civ flag set, make
  tileable textures from photographs, compose a settlement and write its grouping, a survey's
  results as a sortable table, look inside `.ddt`, `.gr2`, `.xmb` and `.bar` files.
- Every command-line tool as a form with its live log, every option with its help in both
  languages; a trial before any change in place.
- **Game interface**: the in-game HUD of a game copy drawn as the game draws it (normal or
  minimised, any screen size, culture and moment), each gadget with everything it points to, and
  a unit of the copy to fill the panels with: what it shows, and what exists but it does not show,
  with why (the game's rows and the UHC DLL's 30 items); edited by dragging and in its properties,
  with undo, the changes, a check and saving into the work folder; design tools (arrange, snap,
  grid, colour, font and texture pickers) and a DLL row added with one click; deployed to the test
  copy and undone (`tools/game_deploy.py --files`).
- Without Blender: the checks (the same findings as Blender's on every preset), and an
  experimental game export (`scripts/game_export_noblender.py`) to be seen in game before it
  replaces Blender's.
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
