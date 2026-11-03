# CLAUDE.md

Guidance for Claude Code in this repository.

## Purpose

A toolkit for making every kind of building and unit for Age of Empires III mods, in the style of
a mod's existing art: an art survey (`tools/art_survey.py`) that learns the conventions of the game
and of a mod, and a Blender add-on (`aoe3_blender_tools/`) whose generators are calibrated on it,
check the result and export it. Done: the survey (run on the game and the target mod, profile
in `aoe3_blender_tools/profiles/`), a first generator (neoclassical buildings), and the game
formats (`aoe3game/`: Granny model, .ddt, anim file, proto and strings, deployment to a test
copy). The game loads a generated building (scenario editor preview). Next: see it placed, built
and destroyed in game (`docs/game-test.md`), then more styles and units (README, "Roadmap").

## Public repository rules

- The repository is **public**. Keep every text neutral: do not name other mods, their teams, or
  the private projects this tool came from, and do not link private documents.
- Never commit survey reports (`report.json`, `summary.md`) of a mod: they name its files. They
  belong to the user's private repository.
- Reference images of a style guide may come from other games: they guide the composition only.
  Never copy a model, texture or layout from them, and never name them in the repository.
- License: GPL-3.0-or-later (Blender's requirement for add-ons). New source files start with
  `# SPDX-License-Identifier: GPL-3.0-or-later`.

## Commands

The `bpy` module is Blender as a Python package (`pip install bpy==5.2.3`, Python 3.13). Use a venv
outside the repository or in an ignored folder (`venv/`).

```
venv/bin/python tests/run_tests.py                 # must print "all tests passed"
python -I tests/test_art_survey.py                 # survey tests, plain Python
venv/bin/python -I tests/test_golden.py            # neoclassical output byte for byte (numpy)
venv/bin/python -I tests/test_pngio.py             # PNG reader
venv/bin/python scripts/generate.py --preset ALL   # regenerates examples/ (about 40 s per view)
venv/bin/python scripts/sweep.py --count 200       # random option sets through the checks: 0 failures
python tools/build_zip.py                          # dist/ zips (extension and legacy)
python -I tests/test_game_formats.py               # game formats, plain Python (venv for numpy parts)
venv/bin/python scripts/game_export.py --out out/wh --preset WHITE_HOUSE --detail MEDIUM
python -I -X utf8 tools/game_deploy.py --install <test copy> --bundle out/wh --validate   # --undo
python -I tools/gr2_tree.py <model.gr2> [--stats|--types|--shape]
```

On Windows the venv interpreter is `venv/Scripts/python`. `-X utf8` matters: the mod's
validators print emoji, and `-I` ignores PYTHONIOENCODING.

- `import bpy` must come before `bmesh` or `mathutils`.
- Never keep a file named like a standard module (`inspect.py`, …) next to a script that imports
  `bpy`: Blender initialises twice and aborts.
- Blender bundles numpy but not Pillow: code inside `aoe3_blender_tools/` uses numpy and the
  standard library only (`core/canvas.py` draws, `paint.save_png` writes PNG).

## Layout

- `aoe3_blender_tools/__init__.py`: properties, operators (`aoe3.load_preset`,
  `aoe3.generate_building`, `aoe3.check_building`, `aoe3.export_building`) and the two sidebar
  panels. `blender_manifest.toml` is the extension manifest (Blender 4.2+); `bl_info` serves older
  versions.
- `aoe3_blender_tools/core/`: `atlas.py`, `canvas.py`, `building.py` (parameters, presets,
  dispatch to the style), `kit.py` (the `Builder`: regions, then `pack()`, then faces from the
  pieces: boxes, rings, walls with recessed openings, hipped roofs, arcs, chimneys; `Face`,
  `Model`, the wall triangulation), `styles/` (one module per style: `NAME`, `clamp`, `build`,
  `opening_tops`, `paint(pr, model)`, `random_params` for the new ones; `neoclassical.py` is the
  original generator, `colonial.py` and `timber.py` the others; `african/` is a package:
  `sizes.py` (type -> reference radius and template), `layouts.py` (the composition of each type
  and architecture, declarative pieces), `parts.py` (declares the regions and emits the pieces),
  `__init__.py` (clamp, build, paint)), `painter.py`
  (the `Painter`: canvas, mask, seeded generator, drawing in region metres; `base()` is the
  material hook), `pngio.py` (PNG reader) and `paint.py` (dispatch, damaged texture) are pure
  Python; `blender_io.py` (object creation, export)
  and `validate.py` (checks) need Blender.
- `aoe3_blender_tools/aoe3game/`: the game formats, pure Python, never importing `core` or bpy
  (tools and tests import it with `sys.path.insert(0, "<repo>/aoe3_blender_tools")`): `gr2.py`
  (container, reader, tree dump in the format of the Granny runtime's dump), `gr2_types.py`
  (the type definitions a static model needs), `gr2_write.py` (serializer, `static_model`),
  `ddt.py` (header, BGRA and DXT1/DXT3 writers, BGRA/DXT decoder; numpy), `icons.py` (icon and
  portrait framing; numpy), `animxml.py`, `proto.py` (unit list
  and string table at the text level), `bundle.py` (the files for one building), `deploy.py`
  (test copy: Steam refused, backups, manifest, undo, validators).
- `aoe3_blender_tools/core/render.py`: Workbench render of a building for its icon and portrait
  (restores the scene's settings).
- `aoe3_blender_tools/core/profile.py`: loads the calibration profile; `validate.check(...,
  profile)` and `bundle.game_size(..., profile)` use it.
- `scripts/generate.py`: headless generation with renders. `scripts/game_export.py`: headless game
  bundle. `tests/run_tests.py`: headless tests. `tests/test_game_formats.py`: format tests.
  `tests/test_golden.py` with `tests/golden/neoclassical.json`: the recorded output of every
  neoclassical preset (faces, atlas, texture, attach points, sizes, facade layout) and their
  triangle counts.
- `tools/`: `art_survey.py` (uses `bar.py` and `xmbedit.py`; standard library only, it runs on the
  user's Windows machine with any Python 3), `bar.py`, `xmbedit.py`, `build_zip.py`;
  `fetch_materials.py` (CC0 swatches into `aoe3_blender_tools/materials/` with `MATERIALS.md`)
  and `palette_survey.py` (stock texture colour and grain), both with numpy.
- `aoe3_blender_tools/core/comfy.py` (ComfyUI client, standard library only, and the repaint
  workflow of core nodes) and `core/airepaint.py` (repaint by regions: tiles, margins, feathering,
  colour kept, player colour kept, edge guard; prompts per style and region);
  `aoe3_blender_tools/ai_panel.py` (the AI Texture panel, `scene.aoe3_ai`; the button runs in a
  thread). `tests/fake_comfy.py` stands in for ComfyUI in the tests. `docs/ai-textures.md`.
- `aoe3_blender_tools/core/materials.py`: swatches under the painting (`MATERIALS[style][role]`,
  `normalise`, `resample`, `tile`); the Painter's `base(region, colour, role)` lays them when
  `params.materials` is on. `aoe3_blender_tools/materials/`: the prepared PNGs and their credits.
- `examples/`: generated presets. `whitehouse/`, `whitehouse_medium/` and `whitehouse1914/` keep
  every export and the .blend (`whitehouse1914/preview_sheet.jpg` is a 2 x 2 sheet of its views);
  the others keep the GLB, a preview and the stats. `whitehouse_medium/ingame_*.jpg` are
  captures from the game (README gallery). `generate.py` writes every export: delete the
  extra files when regenerating the trimmed presets.
- `docs/building-guidelines.md`: requirements, pitfalls, what is still to verify in game.
- `docs/texture-plan.md`: the options to improve the textures without losing their alignment, their
  cost and licences (to verify), and the order to try them.
- `docs/game-formats.md`: the formats as measured, and how the writer was proven.
- `docs/game-test.md`: the test copy, deployment, what to check in game, and the status.

## Working rules

- AI repaint: the tests never need a GPU (they use `tests/fake_comfy.py`); never commit a model
  or an AI-generated image other than the examples; never use a community checkpoint or LoRA
  without reading its licence. ComfyUI is at `C:\ComfyUI\ComfyUI_windows_portable` on the
  user's PC.
- Material swatches come only through `tools/fetch_materials.py`, from a source whose licence page
  states CC0 (it checks before writing); never a texture from the game or a mod. Keep each
  swatch small (256 px; the zip stays under 6 MB, `build_zip.py` checks).
- A new `BuildingParams` field needs a default that changes nothing, a panel property (or an
  entry in `PROP_NAMES`), its style's panel draw, `random_params`, and a preset or a test that
  uses it; `ui_has_a_property_for_every_param_field` fails otherwise.
- Test the add-on in the user's installed Blender too
  (`"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup -P
  tests/run_tests.py`), and reinstall the zip there after a change
  (`blender.exe --command extension install-file -r user_default -e dist/<zip>`).
- The neoclassical presets are golden: a refactor must keep `tests/test_golden.py` green as
  is. Run `--update-golden` only for a deliberate change to that style's output, and say so in
  the commit (then regenerate `examples/`).
- Every geometry change must keep the test suite green; the parameter sweep (both detail levels)
  catches overlapping coplanar faces, faces with repeated corners and UVs outside their regions.
- Count triangles per region after a detail change (`building.build(...)`, then sum per
  `Face.region`); the medium White House must stay near 1,200 (the test allows 1,000 to 1,400).
  Compare every preset's count before and after a change: an unexpected drop is a lost part
  (it caught the side balustrades disappearing).
- Run `scripts/sweep.py` after any geometry change; a new option goes into its `random_params`.
- Look at the renders after a visual change (`scripts/generate.py`, then read the JPEGs).
- Mark game facts as measured, engine limit, or to verify, as `docs/building-guidelines.md` does.
- Regenerate `examples/` when the output of a preset changes, and keep the README gallery in step.
- Never write into the game's Steam folder; deploy only to a test copy with `tools/game_deploy.py`.
  Never leave a compiled `.xmb` next to an edited data XML. Caches of game files (extracted or
  rewritten models) live outside the repository and outside the game copy.
- A change to the `.gr2` writer must keep `tests/test_game_formats.py` green and, when the Granny
  runtime is at hand, its dump of a written file must equal `gr2.dump_tree` and its CRC check
  must pass.
- The profile keeps measurements and stock names only (rubble `BuildingRubbleNxN`, placement
  `buildingsmall/large.xml`); regenerate it with the survey command in the README.
