# AoE3 Mod Studio

Every tool of this repository behind one window, as forms instead of command lines, in English or
Spanish. It is meant for modders who use neither Blender nor a terminal.

![The studio's building screen](../examples/studio.jpg)

## Start it

- **From the repository** (Python 3.10 or newer with numpy; the venv works):
  `venv\Scripts\python -m studio`. It opens its own window (Edge or Chrome in application mode)
  and stops when that window closes. `--no-window` serves it only, `--port N` picks the port.
- **As a program**: `python -I tools/build_app.py --zip` (with a Python that has `pyinstaller`
  and `numpy`, not the venv with `bpy`) writes `dist/AoE3ModStudio/AoE3ModStudio.exe` and a zip of
  about 60 MB. Unzip it anywhere and run the executable: no Python needed. Windows shows a
  SmartScreen warning the first time, as for any program that is not signed.

The settings (the game, the mod, the test copy, Blender, the Granny bridge, ComfyUI, the work
folder) are kept in `%APPDATA%\aoe3-blender-tools\studio.json`. Nothing leaves the computer.

## What it does

| Screen | What is there |
|---|---|
| Buildings | Every preset; a form drawn from `core/schema.py` that shows only what the chosen style uses; the model in 3D with its texture, in clay, with its wires, attach points and collision boxes; the texture with its atlas regions, and the damaged texture; triangles against the style's target or the game's buildings of the same class; the technical sheet; export for the game (with the AI repaint when ComfyUI runs), GLB/FBX/OBJ with renders; deploy to the test copy and undo |
| Textures and units | Texture maker and library, UV atlas of a unit, repaint by body part, LoRA dataset and training |
| Survey and inspection | The art, texture, model, grouping, shape and palette surveys; style check; contact sheets; a file inspector (`.ddt` as a picture with its header and alpha, `.gr2` in 3D with its bones and the texture beside it, `.xmb` as XML, `.bar` as a searchable list whose files open the same way); `.xmb` to XML and back |
| Art utilities | Civ flags, avatar icons, ground rings, health bars, the HITPOINTBAR fix, bone scale fix, uncompressed models |
| Tasks | Every task of the session with its live log, progress, cancel and outputs (pictures shown, text files opened, folders shown) |
| Developer tools | Technical sheets, sweep, galleries, AI sweep, the painter's fit, swatch download, add-on zips |

Every command-line tool has its form (`studio/catalog.py`; `tests/test_studio.py` fails when a
script has none, or when a form passes an option its script does not read).

## How it is built

- `studio/server.py`: a standard-library HTTP server on 127.0.0.1 only. The API writes files and
  starts programs, so each call carries a token the page gets when it loads, and the Host and
  Origin headers must name the server (no other site, no DNS rebinding). The page's content
  security policy allows its own scripts only.
- `studio/engine.py`: the generator in the studio's own process, `core` imported as a top-level
  package as the tools do, so Blender never loads. A preview is `building.build`, `paint.paint`
  and `core/gamemesh.py`'s mesh: 0.01 to 0.03 s of geometry, 0.03 s (White House) to 1 s (African
  town centre) of painting at 256 px, the size used while a control moves.
- `studio/jobs.py`: each tool runs in its own process (they print, call `sys.exit`, change module
  globals, some start process pools): a live log, a real cancel (the whole process tree).
- `studio/blender_bridge.py`: what needs Blender (the game export's mesh and icons, GLB/FBX/OBJ,
  renders, `model_sheets`, `gallery`, `sweep`) runs with the `bpy` module when this Python has
  it, else with an installed Blender 4.2 or newer in the background
  (`blender -b --factory-startup -P <script> -- <options>`). Without either, those buttons say
  what is missing.
- `studio/web/`: the page, plain ES modules with no build step; three.js 0.160 (MIT) for the 3D
  view, vendored in `studio/web/vendor/`. Texts in `studio/web/i18n/en.json` and `es.json`; the
  catalog carries its own strings in both languages.

## Safety

- The studio never writes into the game's installation or a Steam library: every output path is
  checked (`settings.check_output`), and `tools/fix_hitpointbar_tags.py`,
  `tools/fix_bone_scale.py` and `tools/make_icons.py --install` now refuse a Steam library
  themselves, as `game_deploy.py` and `uncompress_models.py` already did.
- A tool that changes files in place has a trial (`--dry-run`, or the plan of
  `uncompress_models.py`); **Apply** is refused by the server until a trial of the same values has
  passed. A tool that changes the test copy without a trial asks first. Running the mod's own
  validators (`deploy --validate`) asks first: they are scripts inside the copy.
- An output the form leaves empty goes to the work folder, never to a tool's default inside this
  program.

## Measured (2026-11-17)

- The game export of WHITE_HOUSE at medium detail from the studio (venv, `bpy` module) is byte for
  byte the export of `scripts/game_export.py`.
- The built program (59 MB, no `bpy`) exported AFRICAN_HOUSE_SAHEL through the installed Blender
  5.2 in 12 s: the same 17 files; the model, texture, anim file and proto are byte for byte the
  same, the bump maps and the portrait differ on 0.01 % of their pixels (Blender's numpy 2.3
  against the venv's 2.5, and its renderer).
- A tool with a process pool (`texture_survey.py`) runs inside the built program: the executable
  runs a tool's script as a module by its name (`--run-tool`), so its workers load it again.
- `core/gamemesh.py` against Blender's game mesh, every preset at both details: the same
  triangles count, area, corner positions and UVs everywhere; the same vertices and normals in
  100 of the 102 cases.

## Still to do

- The game export without Blender: `core/gamemesh.py` gives Blender's mesh (above); the icon and
  portrait, the checks and the GLB writer still need Blender, and the result must be seen in game
  before Blender leaves that path.
- Screens made for their task where a form is not enough: the retexture recipe as a painting tool
  over the atlas, the flag designer with its preview, the settlement composer on a map.
- A signed installer, and a first-run assistant beyond the welcome note.
