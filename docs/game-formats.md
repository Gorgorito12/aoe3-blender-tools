# Game formats

What `aoe3_blender_tools/aoe3game/` reads and writes, and how each fact was established. Facts
are marked **measured** (on the game's and a mod's files, or by the Granny runtime the game
loads), **in game** (seen in the game), or **to verify**.

## Models (.gr2)

Granny 2, file versions 6 and 7 (**measured**: both ship; the runtime is 2.5.0.10).

| Offset | Content |
|---|---|
| 0x00 | magic, 16 bytes `b867b0caf86db10f84728c7e5e19001e` |
| 0x10 | u32 end of the section array |
| 0x14 | u32 header format (0), 8 bytes reserved |
| 0x20 | file header: version, total size, CRC, section array offset (relative to 0x20), section count, root type (section, offset), root object (section, offset), type tag, 4 extra tags; version 7 adds 4 words (header 0x38 or 0x48 bytes) |
| then | 44-byte section records: compression (0 none, 1 Oodle0, 2 Oodle1), data offset, data size, expanded size, alignment, first 16-bit stop, first 8-bit stop, relocation offset and count, marshalling offset and count |

- The CRC is zlib's CRC-32 of every byte from 0x20 + header size to the end (**measured**).
- Pointers are 32-bit and exist only as relocations: (offset in the section, target section,
  target offset), 12 bytes each. A slot without one is null.
- The data tree describes its own types: 32-byte member records (kind, name, referenced type,
  array width, 3 extra words, 1 ignored word) ended by kind 0. Kinds: 1 inline, 2 reference,
  3 reference to array, 4 array of references, 5 variant reference, 7 reference to variant
  array, 8 string, 9 transform (68 bytes), 10 real32, 11 to 20 integers.
- Almost every model stores Oodle1-compressed sections. The reader refuses them; the survey
  reads them after an external tool that loads the game's own Granny runtime has rewritten them
  uncompressed (that runtime is never shipped or called by this repository).

**The reader is proven**: its tree dump is identical, line for line, to the dump the Granny
runtime makes of the same file, on 31 models (14 stock, 17 from a mod; versions 6 and 7).

**The writer** (`gr2_write.static_model`) produces a version 6 file with one uncompressed
section, laid out like the game's own single-section building models: header, relocations,
then 32-bit data, 16-bit arrays and 8-bit data (strings), whose starts are the first16 and
first8 fields. Checks passed (**measured**):

1. the Granny runtime reads it, its own CRC check says valid, and its tree dump equals ours;
2. every path of its tree exists in the game's and the mod's models;
3. the runtime's rebuild of it reports it identical;
4. **in game**: the scenario editor loads and draws it, and in a skirmish it stands in the world
   at the right size, lit like the stock objects, textured the right way up, with the
   civilization flag on its `bone_flag_civ` bone; the player colour, the construction stages and
   the rubble work too (see game-test.md).

What a static building model holds (as the stock files):

- `ArtToolInfo`: the stock buildings' basis, "ESPostExport": 0.615157485 units per metre,
  right (-1, 0, 0), up (0, 1, 0), back (0, 0, 1). A Blender point (x, y, z) in metres is stored
  as (-x, z, -y) x 0.615157485.
- One vertex array of 32 bytes: Position f3, Normal f3, TextureCoordinates0 f2 (886 of the
  measured building models; 1,398 add a Tangent, 44 bytes).
- Indices16 when the mesh has at most 65,535 vertices, else Indices (32-bit; 124 of 621
  measured building models use them).
- Triangles counter-clockwise around their normal in the stored coordinates (754 of 754 on a
  stock house); the writer orders each triangle that way.
- Texture coordinates: V counts from the top row of the texture (**measured**: on a stock house,
  102 roof corners land on the roof drawing as stored, 0 if V were flipped). Blender's V counts
  from the bottom, so the writer stores 1 - V.
- Skeleton "bone_main" with the mesh's bone and one bone per attach point (`bone_flag_civ` for
  the flag, `bone_chimney` for smoke), children of the root.
- Materials as the mod's shortest working ones: a diffuse map, a bump map (the stock flat normal
  texture), and the shader `bumpspec_mask_alphatest` with `lighting\specpower16`, or
  `bumpspec_mask_pixelxform` with `pixelxformColor = playerColor` for player colour.
- Texture names: the model stores a full path; the engine uses the part after `\art\`.

**Scale** (**measured**, confirmed in game 2026-11-04): the survey measured 657 building models. 507
in the stock basis and 70 in 3ds Max inches have a size that agrees with their obstruction once
their declared units are applied. The 27 that declare 1,000 units per metre would be about 0.5 m
wide by that rule, and they are not: in game they stand at full size, their stored coordinates
scaled as if they were inches (x 0.015625: 1,280 stored units are 20 game units). A survey must not
trust that declaration. The writer uses the stock basis, so no conversion is involved.

## Textures (.ddt)

| Offset | Content |
|---|---|
| 0 | `RTS3` |
| 4 | u8 usage: 1 alpha test, 2 low detail, 4 bump (6 = bump normal map) |
| 5 | u8 alpha: 0 none, 1 player colour, 4 transparent, 8 blend |
| 6 | u8 format: 1 BGRA, 4 DXT1, 7 grey, 8 DXT3, 9 DXT5 |
| 7 | u8 mip levels |
| 8 | u32 width, u32 height |
| 16 | (u32 offset, u32 size) per level, largest first; then the data |

The code meanings come from community documentation; the sizes and headers of 22,264 textures
agree with them (**measured**). Uncompressed BGRA with one level is common (1,125 textures of
512 x 512 in the mod). Rows are stored top first. Alpha: with the `alphatest` shaders a low
alpha cuts a hole (cresting, arches); with `pixelxform` it shows the player colour; textures
keep 255 where they show (88 to 100 % of the surface of the measured player-colour textures).
The writer makes DXT3 by default (the game's usual building format, a quarter of the size of
BGRA), DXT1 without alpha, or BGRA, each with mip levels down to 4 x 4. Its DXT encoder fits the
inset bounding box of each 4 x 4 block and picks the nearest of the four palette colours; on a
mod's 1024 x 1024 texture the decoded result differs from the source by 1.7 levels out of 255 on
average, and the file has the size of the game's own (**measured**).

**Player colour** (**measured** on the stock textures that use the `pixelxform` shader): about 2 %
of their pixels, in thin bands (trim strips under the windows), have alpha below 128, and those
pixels are light and nearly grey (the shader tints them). The generator's player-colour option
does the same: the string courses between storeys and the shutters are painted light grey and
get alpha 0 (about 1 % of the White House's texture). The bundle then switches the model to the
`pixelxform` shader by itself, whenever the texture's alpha drops below 255.

## Variants

Beside the main model the export writes, as the stock buildings have them:

- `<name>_lp.gr2` and its own texture `<name>_lp.ddt`: the generator's LOW detail (about 350
  triangles for the White House against 1,235), under the `lowpoly` branch of a `LowPoly` logic;
- `<name>_damaged.gr2`: the same mesh with a damaged texture (soot above some windows, slates
  missing, cracks; the alpha mask kept), under `p1` of a `Destruction` logic, the intact model
  under `p99`.

## Icons and portraits

The stock house has a 64 x 64 icon and a 128 x 128 portrait, both DXT1: the building in three
quarters view on a dark, warm background inside a bevelled frame. The export renders the
building the same way (Blender's Workbench, textured, transparent background, composed onto that
background and frame) and writes both as DXT1; the files have the stock ones' sizes (2,072 and
10,984 bytes).

## Anim files

The XML a proto names in `<AnimFile>`, relative to the art folder. The base game ships them
compiled (`.xml.xmb`, plain `X1`, inside the art archives); mods ship plain XML.

- Paths: backslashes, any case, relative to `art\`; models and textures **without** extension;
  particle, XML and damage template files with theirs.
- A building (the stock houses and the mod's buildings): `definebone` for the bones used;
  submodels for construction stages 1 to 3 that reuse the stock models
  `buildings\constructions\<NxN>_stage<k>` (N from 2 to 6) with the stock construction decal;
  a submodel for the finished building (its model, a ground decal sized in game units, its
  `Idle` anim, optionally `Death` and a `Destruction` logic for damage); and a root component
  with `logic type="Variation"` > `logic type="BuildingCompletion"` choosing the submodel by
  build progress (`p0`, `p33`, `p66`, `p100`).
- Logic types measured in the mod: LowPoly, Tech, BuildingCompletion, Destruction, Variation,
  Civ, Culture.

## Collision

A building's hitbox is three things, none of them its visible mesh:

- **Obstruction**, in the proto: `ObstructionRadiusX` and `Z`, half-sides of a rectangle. With the
  flag `SelectWithObstruction` it is also what a click selects. The stock fort's is 12 x 12 while its
  model reaches 7.3 from the centre: real models stand past their obstruction.
- **Collision shape**: `shape="<name>"` on a model reference in the anim file names
  `Data\\PHYSICS\\<name>.shp`. A plain Havok XML file (CRLF, sdk 20300): an `hkListShape` of
  `hkTransformShape`s, each around an `hkBoxShape`, in the model file's coordinates. The stock fort
  has 16 boxes. `aoe3game/collision.py` writes them, into `data\\physics\\` of the copy.
- **Physics body**: the proto's `PhysicsInfo` names `Data\\PHYSICS\\<name>.physics.xmb`, whose blueprint
  gives mass, friction and a shape of its own. Generated buildings inherit `house` from the template.

A generated building without boxes of its own points at the stock outpost's shape, 2 boxes
3.3 x 4.3 x 8.85, because it borrows that building's damage system (`bundle.DAMAGE_SKELETON`).

Seen in game (2026-11-04) with a generated shape of 17 boxes: the game loads it from
`data\\physics\\`, the building takes cannon fire, and it collapses and clears normally. What a shape
does to a shot aimed past a building is still unclear: four cannons firing at a target behind a
wing did no damage to either with these boxes; with the outpost's shape the building lost 2,000 hit
points and the target none. One run each, with the cannons in different places: repeat it before
relying on it.

## Damage

Large buildings do not change with their hit points: they break where they are hit. Measured on the
stock fort; a test building made this way worked in game.

- The anim file's `Idle` has a `<simskeleton>` with the `_damaged` model and a `<damagetemplate>`, and a
  `Destruction` logic swaps models (`p1` the damaged one, `p99` the intact one).
- The template is XML (`.dmg`, plain text or compiled `.dmg.xmb`): `<model name=...>`, then
  `<impactpoint name bone impacttype motionstopfadetime motionstopfadedelay splasheffect>` holding
  `<part mesh bone halfextents effect blueprint>`. The stock fort has 6 impact points and 24 parts.
- The damaged model is the body plus one mesh per part, each bound whole to its own bone
  (`debris_1a` to `bone_debris_1a`), its vertices in the model's coordinates, plus `boneimpactNN` bones.
- A hit near an impact point throws its parts off for good, so the building loses pieces under fire.
  Hand attacks and torches did not show it on the houses tried.

Cost: the stock fort goes from 1,589 triangles to 4,179. Our test cut a palace with boxes (faces clipped
with their UVs, 22 parts) and went from 1,610 to 3,214. It was dropped for that cost. Two things to solve
if it comes back: a hollow building shows the ground through its holes, so it needs a dark core inside;
and a part that rests on another one stays in the air when the lower one goes. Check that every part a
template names exists in its model: real mods ship templates whose models are empty, and nothing breaks.

## Impact effects

What a hit plays (particles, sounds) by the impact type of the surface it lands on. Measured on the
stock files (2026-11-13).

- **Files:** `art\effects\impacts\<weapon>.impacteffect`, compiled to `<weapon>.impacteffect.xmb`.
  The base game ships 14 of them, only compiled, plain `X1` (no `l33t` zlib), inside `Art1.bar`
  (arrow, cannon, dynamite, grenade, gun, hoop, melee, mortar, torch) and `Art5.bar` (chakram,
  crow, melee_no_weapon, sabotage, shuriken).
- **Layout:** a root `<impacteffect metercount=... meterlength=...>`, then one element per impact
  type (`wood`, `stone`, `flesh`, `rooftile`, `terraingrass`, `exitbuilding`, ...), each holding
  `particleset` and `soundset` children (several of each; `weight` and `fireexisttime` occur as
  attributes). The impact type of a surface comes from `impacttype` in a damage template (`.dmg`),
  a proto's `<ImpactType>` or a terrain type.
- **A loose file:** a compiled `.xmb` in the game's `art\effects\impacts\` is read instead of the
  archive's (seen in game with an edited `cannon.impacteffect.xmb`). An edited XML without its
  compiled twin is not enough: compile it.
- **Compile and decompile:** `python -I tools/xmbedit.py from-xml cannon.impacteffect` writes
  `cannon.impacteffect.xmb` next to it (a source saved as `cannon.impacteffect.xml` gives the same
  name); `python -I tools/xmbedit.py to-xml cannon.impacteffect.xmb` writes `cannon.impacteffect`.
  `to-xml` puts each element on the source line stored in the file, so the stored line numbers
  survive the text: for all 14 stock impact effects, `to-xml` then `from-xml` gives the original
  `.xmb` byte for byte, and `xmbedit.py check` proves it for any file.
- **Tested in game (2026-11-13):** the stock `cannon` impact effect, decompiled with `to-xml`, one
  element of an impact type of its own added (a water splash particle set, a metal sound), compiled
  with `from-xml` and put loose in `art\effects\impacts\`; a building whose `.dmg` names that type,
  hit by cannons: each hit threw the splash off its walls. A type outside the game's 15 needs the
  engine to know its name; with one of the 15 (`metal` is one no stock file uses), the data alone
  is enough.
- **Coverage of the text round trip:** over every `.xmb` in the base game's archives and the
  compiled protos and tech tree (about 6,000 files), all but 48 come back byte for byte. Of those, 47
  are anim and terrain files whose stored text keeps tabs after an element's text, before its
  children, which the XML text drops, and one repeats an attribute, which XML forbids. `check`
  reports such a file; its binary round trip still holds.

## Protos and strings

- `data\protoy.xml`: `<Unit id=... name=...>` blocks (both quote styles occur), CRLF line ends.
  A mod may ship it without the compiled twin; the engine prefers a `.xmb` that is newer than
  the XML, so a stale one would hide every edit (the deployment refuses to run then).
- New units: id = DBID, a number used by neither (the deployment takes the lowest free one from
  25,000). The entry is a copy of a template unit (the stock `House` by default) with the name,
  numbers, anim file, obstruction, rubble, placement rule and string numbers replaced, and its
  train, tech and command buttons removed.
- `data\stringtabley.xml`: UTF-16 with a byte order mark, `<String _locID='N'>`. New strings go
  before the comment block that closes the language.
- Sizes in game units: ObstructionRadiusX/Z are half sides; decals are full sides. The stock
  house: radius 2.0, decal 6.0, model 4.76 units wide.

## Calibration profile

`tools/art_survey.py --proto ... --profile-out ...` joins every unit with the Building type to
its anim file and finished model, measures the model, and groups the buildings by obstruction
footprint. `aoe3_blender_tools/profiles/buildings.json` is the profile of the target mod
(measurements and stock names only). Its largest class, 8 x 8 units (205 buildings): median
1,102 triangles, 90th percentile 2,221; obstruction 0.91 of the half side; decal 1.12 times the
side; construction stages 4x4; rubble `BuildingRubble4x4`.
