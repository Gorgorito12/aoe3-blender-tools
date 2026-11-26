# Changelog

One version for the Blender add-on and AoE3 Mod Studio: `aoe3_blender_tools/blender_manifest.toml`
says it, the add-on's `bl_info` repeats it and the studio reads it (`tests/test_studio.py` holds the
three together).

## Unreleased

- `tools/make_ui_templates.py` (two forms in Art utilities): Photoshop templates of the in-game interface's
  textures, for artists to restyle the interface per culture, and the way back. `templates` writes one `.psd` per
  texture of 65 px or more (`--all`: the small ones too; the README lists those left out) (the original hidden and locked; one layer per piece named in plain words with its number and gadget; a
  hidden Guides group with outlines, names, unused areas hatched and stretched pieces marked; Photoshop guides at the
  pieces' edges), a reference sheet, the map as JSON and a README for artists. `build` turns the filled `.psd`, an
  exported PNG or a whole `.ddt` recoloured elsewhere into `<texture>_<suffix>.ddt` in the original's format, with checks. New: `aoe3game/uiatlas.py` (the
  interface's textures as pieces; the visibility rules `ui_preview.py` draws with, moved there unchanged),
  `aoe3game/psd.py` (a minimal PSD writer and reader, pure Python and numpy), `ddt.write_like` (new pixels in an
  original's format; `panel_rows.encode_like` uses it). Test: `tests/test_make_ui_templates.py`.
- `docs/animation-rules.md`: how a unit's animations are made and reviewed: a beat list of every clip
  approved first (where every object comes from and goes to, anything removed on its own line), automatic
  checks before any preview, a fixed preview format (4 sides x 2 heights, a close GIF, the risk frames)
  with a checklist, and the in-game frames after. `tools/check_anim.py` (`aoe3game/anim_check.py`, a form
  in Art utilities) runs the checks: head and neck turns, reversed elbows and knees, snapping bones, feet
  that slide or sink, grips, mounted parts, props that pop or end in the wrong place, interpenetration,
  lengths, loop seams, floating parts at the end of a death, and clips or motions removed without saying
  so; exits 1 when one fails. Test: `tests/test_check_anim.py`.
- `tools/make_pray.py` (`aoe3game/gr2_pose.py`, a form in Art utilities): three praying animations for the
  villagers (kneeling with joined hands, standing with the sign of the cross, bowing down to the ground),
  each an entry from the idle, a seamless loop and an exit, for the male and the female villager, made
  from key poses with two-bone IK; checked for seams, foot sliding, the ground and hands inside the body,
  and through the game's granny2.dll; review sheet and GIFs. `make_dismount.py`'s pose helpers moved to
  `gr2_pose.py`. Test: `tests/test_make_pray.py`.
- `tools/panel_rows.py` (a form in Art utilities): a resource panel's painted rows re-laid in the interface textures, with new rows that carry an icon of your own (a new resource row), from a JSON spec; only the panel's DXT blocks are encoded again. `tools/draw_praying_hands.py`: a praying hands icon as a PNG. Test: `tests/test_panel_rows.py`.
- Studio forms in Art utilities for `tools/make_type_icon.py`, `tools/import_icon.py`,
  `tools/make_command_icon.py` and `tools/dmg_bones.py`, which had none (`tests/test_studio.py` failed on
  them).
- `tools/dmg_bones.py`: the damage templates whose parts name a bone the model using them lacks, or one its
  anim file does not define with `<definebone>` (the game then reloads the model while units still draw it
  and can crash), from the loose files and the `art\*.bar` archives, buildings' `<simskeleton>` included;
  `--fix <folder>` writes copies of the anim files with the missing `<definebone>` lines (a loose `.xml`
  edited as text, an archived one as a loose `.xml.xmb`), never in the game folder. Test:
  `tests/test_dmg_bones.py`.
- `tools/fit_borrowed.py` (`aoe3game/gr2_fit.py`, a form in Art utilities): a model fitted in place to a
  borrowed damage template or animation: debris meshes renamed on export get the template part's name, and
  bones take a reference model's rest frames, so a borrowed collapse animation places every piece as on the
  reference. Test: `tests/test_gr2_fit.py`.
- `tools/make_dismount.py` (`aoe3game/gr2_anim.py`, a form in Art utilities): dismount and mount
  animations for a cavalry unit whose rider hangs on its horse, the rider's animations on foot made from
  the infantry's, the horse kept beside him or hidden under the ground with the rider on the unit's centre,
  the melee on foot only when asked, test animations for heal and build, contact and review sheets.
  `gr2_anim.py` reads, poses and writes animations (tracks sorted by name, as the runtime looks them up).
  Test: `tests/test_gr2_anim.py`.
- `tools/make_type_icon.py`: unit type icons in a painted style (two infantrymen in shakos, a winged
  arrow, a winged bullet as the alternative), 32x32 BGRA under their game paths. `tools/import_icon.py`:
  an icon drawn elsewhere (a PNG) into a game icon `.ddt`, widened for panels that squeeze square icons
  (`--aspect`), reduced by area averaging, recoloured by region (`--tint`), narrowed between its sides
  (`--sides`). `tools/make_stat_icon.py --aspect`. Tests: `tests/test_import_icon.py`,
  `tests/test_stat_icons.py`.
- `tools/make_rings.py`: veterancy rank marks as soutache knots centred on the hit point bar, or from
  drawn images (`--rank-shapes`); marker icons cut from a drawn sheet (`--icon-sheet`) with new markers
  (ship, xp, oil); range rings as flat meshes in the owner's colour (`--range-particles` keeps the
  particle rings). `tools/make_aura_rings.py` (a form in Art utilities): the game's own aura ring
  recoloured per ring colour, with anti-rings for negative effects; its output derives from the game's
  art and stays out of public repositories.
- `tools/make_rings.py`: range rings for attacks that reach only ships, `range_<metres>_ships` (the same line in 48
  dashes), and fills, `rangefill_<metres>_p<player>`: a disc under the ring on the game's `alphablend` shader, clear at
  the centre and rising to 30-38 % at the edge, one texture per player colour (that shader has no player colour).
  `--no-range-fills` and `--no-ship-rings` leave them out.
- `aoe3game.gr2_write.static_model`: `colour_effect`, the effect of a player-coloured material (the units' shader by
  default).
- `tools/make_rings.py`: range rings without the white edges, the whole line in the owner's colour like a selection
  circle, and thinner (0.5 m, +0.008 m per metre of radius). Their flat bump map had a shine of 128 in its red channel
  and a normal tilted along the ring in its alpha: the sun's shine added white and the colour looked pale. It is now
  flat with no shine (R 0, A 128, as the game's own flat bump).
- `tools/make_rings.py`: range rings at their true size. The game draws a flat particle `<scale>` metres wide in all,
  not twice that, so every `range_<metres>` ring showed half its radius (measured in game: the 12 m ring at 6 m).
  `range_scale` writes twice the old scale (the textures are unchanged); after the fix the 4, 12 and 30 m rings pass
  between markers just inside and outside their radius. The aura rings and icons, sized by eye in game, keep their
  files; their comments now call the number the particle's scale (a unit's ring is 2.2 m across).
- `tools/make_rings.py`: range rings up to 100 m (18, 22, 26, 28, 32, 36, 40, 45, 50, 60, 70, 80 and 100 added; the
  line widens a little on the large ones), and the markers' floating icons redrawn as cartoons by the new
  `tools/cartoon_icons.py` (shapes as signed distances, flat colours, a light tone per part, a thick dark outline):
  a pickaxe over a nugget for gold, an axe for wood, a leg of meat for food, and `aura_hunt`, `aura_berry`,
  `aura_farm`, `aura_fish` with a bow, berries, an ear of wheat and a fish; 128-texel BGRA so the colours stay flat.

- `tools/make_command_icon.py`: command button icons in the style of Wars of Liberty's own on / off buttons
  (64x64 BGRA, a mottled blue frame, a green tick for "on", a red tint and cross for "off"), drawn from
  code; the first glyph, `autoscout`, a map half explored with a dotted route and a spyglass, for the
  auto scout buttons. Test: `tests/test_command_icons.py`.
- **A unit's animations on another model** (`tools/retarget_anims.py`, a form in Art utilities;
  `aoe3game/gr2_retarget.py`): the game plays an animation on a model only through a track group named
  after the model (measured in its code), so the Aztec Macehualtin's slinger animations (`bone_master`)
  do nothing on a standard infantry model (`Bip01`). The tool puts each clip on the target's skeleton,
  writes it with its tag file, the anim file blocks to paste and a review sheet; recipes for a Wars of
  Liberty light infantry model and the game's native rifleman. `aoe3game/gr2_anim.py` comes from the
  dismount work (unchanged).

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
