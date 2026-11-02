# CLAUDE.md

Guidance for Claude Code in this repository.

## Purpose

A Blender add-on (`aoe3_blender_tools/`) that generates low-poly buildings for Age of Empires III
mods, checks that they are game-ready and exports them. Phase 1 (generator, painted texture,
checks, GLB/FBX/OBJ export) is done; phase 2 (calibration against stock models, `.gr2` and `.ddt`
export, anim XML and proto entries) is in the README's roadmap.

## Public repository rules

- The repository is **public**. Keep every text neutral: do not name other mods, their teams, or
  the private projects this tool came from, and do not link private documents.
- Never commit game or mod assets (models, textures, data, extracted files). Calibration profiles
  keep measurements only.
- License: GPL-3.0-or-later (Blender's requirement for add-ons). New source files start with
  `# SPDX-License-Identifier: GPL-3.0-or-later`.

## Commands

The `bpy` module is Blender as a Python package (`pip install bpy==5.2.3`, Python 3.13). Use a venv
outside the repository or in an ignored folder (`venv/`).

```
venv/bin/python tests/run_tests.py                 # must print "all tests passed"
venv/bin/python scripts/generate.py --preset ALL   # regenerates examples/ (about 2 min per view)
python tools/build_zip.py                          # dist/ zips (extension and legacy)
```

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
  geometry as pure data) and `paint.py` are pure Python; `blender_io.py` (object creation, export)
  and `validate.py` (checks) need Blender.
- `scripts/generate.py`: headless generation with renders. `tests/run_tests.py`: headless tests.
- `tools/`: `bar.py`, `xmbedit.py` (game data, standard library only), `build_zip.py`.
- `examples/`: generated presets. `whitehouse/` keeps every export and the .blend; the others keep
  the GLB, a preview and the stats.
- `docs/building-guidelines.md`: requirements, pitfalls, what is still to verify in game.

## Working rules

- Every geometry change must keep the test suite green; the parameter sweep catches overlapping
  coplanar faces and UVs outside their regions.
- Look at the renders after a visual change (`scripts/generate.py`, then read the JPEGs).
- Mark game facts as measured, engine limit, or to verify, as `docs/building-guidelines.md` does.
- Regenerate `examples/` when the output of a preset changes, and keep the README gallery in step.
