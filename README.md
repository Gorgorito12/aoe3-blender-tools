# AoE3 Blender Tools

A toolkit for making game-ready buildings and units for Age of Empires III mods, in the style of
the art a mod already has. It has two parts:

- **An art survey** (`tools/art_survey.py`): it reads the models, textures and anim files of the
  game and of a mod, and reports their conventions: budgets, texture sizes, attach point names,
  anim file structure, and which stock parts the mod reuses. The generators are calibrated on it.
- **A Blender add-on**: generators that build models from exact primitives (flat walls, straight
  edges), lay out one UV atlas, paint the texture from the real measurements, check that the
  result is game-ready, and export it. The first generator makes neoclassical buildings.

| White House | Courthouse |
|---|---|
| ![White House](examples/whitehouse/preview_front34.jpg) | ![Courthouse](examples/courthouse/preview_front34.jpg) |
| **Capitol** | **Mansion** |
| ![Capitol](examples/capitol/preview_front34.jpg) | ![Mansion](examples/mansion/preview_front34.jpg) |
| **White House, medium detail** | **The same, geometry only** |
| ![White House medium](examples/whitehouse_medium/preview_front34.jpg) | ![White House medium, clay](examples/whitehouse_medium/preview_wire.jpg) |

The four presets at low detail have 92 to 413 triangles; the White House at medium detail has
1,235. Each has one 1024 × 1024 texture.

**White House, 1914** (preset `WHITE_HOUSE_1914`, built from a reference picture): north and south
elevations, then views from the south-west and the north-east. 3,035 triangles at medium detail,
one 2048 × 2048 texture, 44.5 × 23.6 m with the wings. The game's ground is flat, so the basement
that the real site shows on the south is left out.

![White House 1914](examples/whitehouse1914/preview_sheet.jpg)

Status: version 0.1. The survey and the first building generator are done; nothing has been
tested in the game yet (see [Getting a building into the game](#getting-a-building-into-the-game)),
and the survey has only run on synthetic files so far.

## Why

AI 3D generators make a building as a sculpted surface: decimated to a game budget, its walls come
out wavy and its windows warped. The buildings of a 2007 RTS are the opposite: a few hundred to a
few thousand triangles of simple, straight geometry, with the detail painted in the texture. This
add-on builds them that way. The details are in [docs/building-guidelines.md](docs/building-guidelines.md).

## Art survey

Read-only, standard library only, so it runs with any Python 3 on the machine that has the game:

```
python -I tools/art_survey.py "<game folder>" --bar --out survey/stock --label Stock
python -I tools/art_survey.py "<mod folder>" --bar --out survey/mod --reference survey/stock/report.json
```

`--bar` reads the `.bar` archives in memory; nothing is extracted. Each run writes `report.json`
and `summary.md`: counts, anim files per folder, how many of the mod's anim files reuse stock
files, own files or both, the most referenced files, reference kinds, attach point and bone names,
logic types, anim names, texture sizes and formats from the `.ddt` headers, and the elements of
the anim files. The reports hold measurements and paths, never file contents, but they name the
mod's files: keep them out of public repositories.

Not read yet: the meshes inside `.gr2` files (triangle and bone counts need a Granny reader).

## Features

- **Building generator** (neoclassical for now): width, depth, 1 to 4 storeys, plinth, window
  spacing and side windows, a portico with 2 to 8 columns and a pediment, a hipped roof of any
  pitch, a cupola or a flagpole, up to 8 chimneys, a semicircular back portico (columns on an arc
  around a bowed bay, with a balustraded flat roof), wings (one-storey pavilions joined by
  colonnades), shutters, and alternating window caps. Presets: White House, Courthouse, Capitol,
  Mansion, White House 1914.
- **Values that cannot be built are reduced, with a warning**: more columns than the front holds,
  a bow too large for the back, chimneys that would overlap. A random sweep of 1,200 option sets
  passes the checks.
- **Two detail levels.** Low: flat walls with painted windows (about 350 triangles). Medium
  (about 1,200): windows and doors recessed into the walls, a balustrade with posts on the roof
  edge, a profiled cornice, columns with a base and a capital, cheek walls beside the steps and
  banded chimneys. The walls stay one polygon with holes, triangulated without T-junctions.
- **Painted texture**: stone courses, quoins, windows with sash bars and caps, the door with its
  fanlight, slate rows, dentils, brick, all aligned with the geometry. Colours are settings. Flat
  colour, no baked lighting. Painted with numpy only, so nothing extra is installed in Blender.
- **Game-ready check**: triangle budget, the 16-bit vertex limit, one UV map inside 0..1,
  power-of-two textures, material count, origin at the footprint centre and base on the ground,
  degenerate faces, hidden bottom faces, and overlapping coplanar faces (they flicker in game).
- **Export**: GLB and FBX with the texture embedded, OBJ + MTL, the texture as PNG, and a stats
  file. Attach points (`flag_attach` on the cupola) are exported as empties.

## Install

Download or build the zip (`python tools/build_zip.py` writes `dist/`), then:

- **Blender 4.2 or later:** Edit > Preferences > Get Extensions > Install from Disk, and pick
  `aoe3_blender_tools-0.1.0.zip`.
- **Blender 3.6 to 4.1:** Edit > Preferences > Add-ons > Install, and pick
  `aoe3_blender_tools-0.1.0-legacy.zip`.

Tested with Blender 5.2 (as the `bpy` module, headless): install from the zip, generate, check and
export all work. The Blender 3.6 to 4.1 path is untested.

## Use

3D Viewport > Sidebar (N) > **AoE3**.

1. **Building Generator**: pick a preset and load it, change the settings, then **Generate
   Building**. Generating again replaces the object of the same name. When a setting cannot be
   built (for example more columns than the front allows), it is reduced and a warning says so.
2. **Check and Export**: **Check** lists the problems of the active object; **Export** writes the
   files to the chosen folder (default `//aoe3_export`, next to the .blend).

Conventions: 1 unit = 1 m, Z up, the front (portico) faces −Y, the origin is the centre of the
footprint (steps included) on the ground. GLB, FBX and OBJ are written Y-up.

## Command line

Everything also runs headless, with Blender or with the `bpy` module:

```
python -m venv venv
venv/bin/pip install bpy==5.2.3                       # Blender 5.2 as a module (Python 3.13)
venv/bin/python tests/run_tests.py                     # the test suite
venv/bin/python scripts/generate.py --preset ALL       # examples/<name>/ with exports and renders
venv/bin/python scripts/generate.py --preset WHITE_HOUSE --detail MEDIUM
venv/bin/python scripts/generate.py --preset WHITE_HOUSE_1914 --views front,back,front34,back34
venv/bin/python scripts/sweep.py --count 200                # random options through the checks
venv/bin/python scripts/generate.py --preset CAPITOL --out out --no-render
```

With a Blender install: `blender -b --factory-startup -P scripts/generate.py -- --preset ALL`.

## Getting a building into the game

None of these steps is done or tested yet. Each one copies from a stock building rather than
guessing.

1. **Scale and orientation.** Import a stock building of similar size with a Granny (`.gr2`)
   importer for Blender, and match this model's scale and facing to it. 1 unit = 1 m is an
   assumption.
2. **Export** the mesh to `.gr2` with the same community add-on.
3. **Texture**: convert the PNG to `.ddt`. Stock textures may carry a player-colour mask in their
   alpha; the generated one has none yet.
4. **Anim XML**: copy the anim file of a stock building of similar size and swap only the model.
   It keeps its construction stages, damage states and destruction. Rename `flag_attach` to the
   attach point name that file uses.
5. **Proto**: give the unit its entry in `protoy.xml` (and its compiled `.xmb`), with an
   obstruction matching the footprint after scaling.

`tools/bar.py` lists and extracts the game's `.bar` archives, and `tools/xmbedit.py` reads and
writes its compiled XML (`.xmb`): see [tools/README.md](tools/README.md).

## Roadmap

1. **Survey** (tool done): run it on the game and on the target mod, and turn the report into
   per-category profiles: triangle and texture budgets, scale, facing, attach point names, anim
   file templates, and the stock parts most reused.
2. **Calibration and game formats:** fit the generators to those profiles; read `.gr2` meshes for
   the budgets; call the community `.gr2` exporter when it is installed; write `.ddt`; write anim
   files and proto entries from templates.
3. **Buildings:** a kit of parts per architectural style found in the survey (colonial, European,
   Asian, native, forts, walls and gates), and baking the texture of a detailed model onto a clean
   mesh. The neoclassical generator here is the first one (phase 1, done).
   Textures: relief baking, material swatches, Stable Diffusion with ControlNet and the other
   options in [docs/texture-plan.md](docs/texture-plan.md).
4. **Units:** reuse the stock skeletons and animations; build the body from parts or fit a
   detailed mesh to a stock skeleton; textures with the player-colour mask.

## Game files and other mods

Do not commit files from the game or from other mods to this repository: models, textures and
data belong to their owners. Calibration profiles keep measurements only.

## License

GPL-3.0-or-later ([LICENSE](LICENSE)), as Blender requires for add-ons. Age of Empires is a
trademark of Microsoft; this project is not affiliated with Microsoft.
