# What the target mod's art measures

The generators are meant to make art "in the style of the mod's existing art". This page is what
that art is, measured: every texture opened, every model and animation uncompressed and read. It
replaces guesses that were typed in by hand from a few stock textures.

Measured on 2026-11-10 with `tools/texture_survey.py` and `tools/model_survey.py` (their reports
stay private; the numbers are in `aoe3_blender_tools/profiles/textures.json` and `models.json`,
which name no file). **Own** is art the mod made; **stock** is art whose bytes are also in the
original game. Each distinct file counts once.

| | Files | Distinct | Own | Stock | Unread |
|---|---|---|---|---|---|
| Textures | 39,210 | 34,779 | 20,062 | 14,421 (+296 repainted) | 160 |
| Models and animations | 19,428 | 18,164 | 5,993 | 12,165 | 9 |

Unread, and said rather than hidden: 144 textures in a format the decoder does not know (header
format 3, 8 bits a pixel: masks of the interface and the terrain, not painted art), 16 damaged
ones, 9 models the bridge refused.

## Textures

A texture's name says little — icons, ground decals and photographs sit in the same folders — so
a texture counts as a model's skin only when **a model names it** (10,989 do). The table is those,
at mip level 1; grain is the spread of the luminance minus its 9 x 9 blur over its mean; the three
numbers are the quartiles.

| | n | Grain | Saturation | Luminance | Usual sizes | Tiles | Player colour |
|---|---|---|---|---|---|---|---|
| **Own buildings** | 434 | 0.13 / **0.25** / 0.35 | 0.24 / 0.37 / 0.43 | 72 / 104 / 128 | 256, 512, **1024** (26 %) | 6 % | 68 % |
| Stock buildings | 652 | 0.40 / **0.51** / 0.61 | 0.24 / 0.33 / 0.43 | 74 / 92 / 113 | 256 (87 %) | 29 % | 71 % |
| **Own units** | 2,609 | 0.18 / **0.26** / 0.40 | 0.09 / 0.34 / 0.55 | 38 / 59 / 89 | **512** (50 %) | 7 % | 56 % |
| Stock units | 988 | 0.42 / **0.52** / 0.63 | 0.21 / 0.39 / 0.55 | 55 / 77 / 103 | 64, 128 | 22 % | 81 % |
| Own building sets | 157 | 0.33 / 0.38 / 0.47 | 0.21 / 0.33 / 0.44 | 61 / 82 / 100 | 256 | 12 % | 74 % |
| Stock treasures | 24 | 0.32 / 0.42 / 0.59 | 0.24 / 0.37 / 0.40 | 65 / 75 / 98 | 256 | 25 % | 12 % |
| Stock map objects | 49 | 0.35 / 0.43 / 0.46 | 0.05 / 0.29 / 0.40 | 62 / 94 / 105 | 512, 256 | 73 % | 55 % |

What this says:

- **The mod's own hand is half as grainy as the original game's.** 0.25 against 0.51 on
  buildings, 0.26 against 0.52 on units. The target the swatches were fitted to came from stock
  textures: it was the wrong hand.
- **It paints bigger.** A quarter of its building textures are 1024 and half of its unit textures
  512, where the original game used 256 and 64 to 128. With the models (below) that is 45 texture
  pixels per game unit on a building against 37, and **123 on a unit against 44**.
- **Its colours are as saturated as the original's** (0.37, 0.33), its buildings a little lighter,
  its units darker.
- **Almost nothing tiles** (6 %): a building's texture is an atlas of strips, each drawn for its
  wall. A tiling material is the exception, kept for map objects.
- Two thirds of the building and unit textures carry the player colour in their alpha.

### What the sheets show that the numbers do not

Looked at on contact sheets (kept outside the repository, like every picture of the mod's art):

- A building texture is **long strips packed on a flat ground**: bands of wall with their
  openings, bands of roof, planks, each as long as the wall it covers. The unused part is one flat
  colour (grey, black or white), never noise.
- The material is **photographic, softened**: earth, sand, ochre, terracotta, grey stone. The
  original game's atlases are sharper, with darker lines between planks and bricks and a warmer
  orange in the wood.
- Openings are **small dark rectangles with a lighter frame and a soft smudge of shadow under
  them** — a painted occlusion, not an outline. Walls are evenly lit; only towers and pyramids
  carry a gradient from top to bottom.
- The owner's colour is laid as flat, saturated blocks and stripes (awnings, shutters, banners).
- A unit texture follows the original game's layout to the panel — the face in a corner, the
  torso and the limbs as flat panels of cloth with soft folds — in flat uniform colours: navy,
  crimson, olive, buff.

## Our own textures against it

`tools/style_check.py` paints the presets as they ship (the African ones with their swatches) and
measures them the same way, against the mod's own building textures (distance from their median
in widths of their middle half; ±0.5 is a quartile):

| Preset | Grain | Saturation | Luminance | Against the mod |
|---|---|---|---|---|
| White House | 0.13 | 0.08 | 129 | grain −0.5, saturation **−1.5**, luminance +0.4 |
| Colonial house | 0.13 | 0.10 | 128 | grain −0.6, saturation **−1.4**, luminance +0.4 |
| Timber inn | 0.28 | 0.21 | 127 | grain +0.1, saturation −0.8, luminance +0.4 |
| African house, Sub-Saharan | 0.13 → **0.17** | 0.43 | 113 | grain −0.5 → −0.4, saturation +0.3 |
| African house, Sahel | 0.09 → **0.17** | 0.38 | 127 | grain −0.7 → −0.4, saturation +0.1 |
| Sahel palace | 0.10 → **0.16** | 0.59 → **0.41** | 124 | grain −0.7 → −0.4, saturation **+1.2** → +0.3 |

### The African styles, calibrated (2026-11-10)

The owner asked for the African painter to be brought to these numbers, the neoclassical presets
left as they are recorded (they lay no swatch), the colonial and timber styles untouched.

- **Grain, per material.** A swatch now carries a fine band of its own (`core/materials.py`, the
  fifth value of a role): the swatch minus its 17 x 17 blur, which is what the survey's grain sees,
  laid apart from its blotches. `tools/style_check.py --fit` measured each role's regions against
  the mod's own textures and chose it. Raising the old single contrast did not work: it swelled
  the blotches into camouflage before the grain moved. Walls and adobe take 0.22 (at 0.25 the
  plaster turns mottled), flat roofs 0.19 (still smoother than the walls they cover, as the style
  guide wants), thatch, plinths and stone 0.25; timber was already at the mod's 0.33.
- **Colour.** The palace's palette is muted to 0.65 of its colour about the grey of the same
  lightness (saturation 0.59 to 0.41), the plot's soil a little (0.48 to 0.38).
- Every African preset is now within half a quartile width of the mod's own building textures in
  grain and saturation (`tests/test_materials.py` holds it); the furthest is the Sahel palace at
  2048, 0.48 under the median grain.
- **To verify in game**: a stronger grain can glitter in the mipmaps at a distance.

The European styles stay as they are: their saturation (−1.4 to −1.5) is their whitewash, and
changing it is a separate decision.

## What the texture maker does with it

- Every texture it makes is measured against the mod's own textures of its material and category
  (`texmaker.style`, the `against` entry of its sidecar): grain, saturation and luminance, in the
  same widths.
- **Fit** (`--fit`, on by default in the panel) brings grain and saturation to the mod's median
  (`texmaker.match`): the fine detail is scaled, never the broad shapes or the mean colour, and a
  texture that tiles still does.
- Measured on a thatch drawn by Stable Diffusion: saturation **0.69 against the mod's 0.37**,
  1.4 widths out; after the fit 0.41, 0.2 widths, the join unchanged at 1.24. A generated texture
  is far more saturated than a game's: left alone it would stand out on any building of the mod.

## Models

| | Models | Triangles | Bones | Width | Height | Texture px per unit |
|---|---|---|---|---|---|---|
| **Own buildings** | 1,293 | 312 / **1,020** / 2,015 | 3 | 5.0 / 7.8 / 9.5 | 4.0 / 6.1 / 8.5 | 22 / 45 / 75 |
| Stock buildings | 2,705 | 228 / **576** / 1,125 | 4 | 4.9 / 8.2 / 10.3 | 4.4 / 6.2 / 10.3 | 31 / 37 / 49 |
| **Own units** | 2,885 | 194 / 226 / 658 | 22 | — | 2.1 | 63 / **123** / 255 |
| Stock units | 2,329 | 140 / 232 / 305 | 22 | — | 1.9 | 32 / 44 / 69 |
| Stock treasures | 65 | 266 / **320** / 846 | 2 | 4.3 / 4.7 / 7.7 | 1.9 / 2.2 / 4.3 | 48 / 71 / 89 |
| Stock map objects | 154 | 30 / **106** / 348 | 2 | 1.2 / 3.1 / 6.8 | 0.7 / 1.7 / 2.8 | 33 / 52 / 92 |

Sizes in game units, of the models that declare the stock scale. The mod's own buildings carry
almost twice the triangles of the original game's (1,020 against 576); its units the same count
with three times the texture.

**A budget for a prop**, from the original game's own (the mod added too few to measure): a map
object about 100 triangles and seldom over 350, a treasure about 320 and seldom over 850, two
bones (the root and the mesh's), a 256 or 512 texture at 50 to 70 pixels per unit.

### What the model sheets show

Rendered through the importer (`tools/model_sheets.py`), each model with its own texture:

- **A treasure is a small accident, not an object.** The recipe repeats: one main thing — a cart
  with a wheel off, a collapsed cabin, a burnt hut, a tent — tilted or broken, and its cargo
  spilled around it within about five units: barrels, crates, sacks, a heap of fruit. The cargo
  is where the colour is (saturated red, green, yellow), so it reads from the game's camera;
  the wood stays brown. Never symmetrical, never upright.
- **A map object is one thing**: a rock, a pole with a flag, a stack of crates, at a hundred
  triangles.
- **The mod's own buildings are one mass each**, as the shape survey measured, but of every kind:
  flat-roofed adobe compounds, timber frontier fronts, domes, pyramids, round tents, silos,
  bridges. Their textures are atlases worn tightly: little of a texture is left unused.

## Prop sets

A unit whose anim file holds a `logic type="Variation"` is a set: one proto, many models, and a
grouping's `variation` (0 to 255) picks one. 525 anim files of the game and the mod have one.

| | |
|---|---|
| Models a set (431 sets with three or more found) | 5 / 9 / 20 |
| Sets on one diffuse texture | 82 (19 %) |
| On two | 107 (25 %) |
| On more | 242 |

The stock colony props are such a set: 13 small things (barrels, boxes, goods, baskets), one
component, one `Idle` anim with an empty GrannyAnim, no decal. The toolkit writes the same
(`animxml.prop_set`, `bundle.write_set`) on **one** texture: the generator paints all the variants
into one atlas, and `core/group.py` packs meshes made elsewhere into one.

## Settlements

A native settlement is not a model: it is a **grouping**, `RM*/groupings/<name>.xml`, which places
proto units at offsets from a centre (format in `docs/game-formats.md`). Measured with
`tools/grouping_survey.py` over the mod's copy (583 distinct files) and the original game (267),
each placed unit classed by its proto's unit types (`profiles/groupings.json`):

| | Own (246 round a socket) | Stock (189) |
|---|---|---|
| Units a file | 50 / 60 / 72 | 33 / 39 / 49 |
| Nothing stands nearer the socket than | 5.3 / 5.6 / 6.3 | 4.6 / 5.1 / 6.1 |
| Buildings from the socket | 11.6 / 16.2 / 19.7 | 7.5 / 11.7 / 14.3 |
| Buildings facing the socket (within 45°) | 37 % | 37 % |
| Buildings with their back to it | 16 % | 15 % |
| Share: nature, props, obstructions, buildings, plants | 33, 24, 21, 14, 7 % | 24, 32, 15, 14, 13 % |
| Variants of one settlement | 3 / 3 / 5 | |

What this says:

- **A settlement is not a ring of doors round a square.** Barely more buildings face the socket
  than chance would give (a quarter); one in six turns its back on it.
- **A fifth of the units are invisible**: obstructions that keep the ground round the socket and
  between the houses clear, so units walk where the settlement wants.
- The mod's settlements are a half larger and denser than the original game's.

`core/settlement.py` composes from these numbers: a socket with its clear radius, a lane left
open to it, buildings in their band of distance and facing as measured, props beside them, plants
and trees at the rim, and a ring of obstructions when one is named.

## Units and animations

Of 5,218 unit models:

| How the vertices are stored | Models | |
|---|---|---|
| A packed stream the reader cannot open (one 1-byte field, `FD`), bound to about 18 bones | 2,867 (55 %) | **to decode**: the layout inside it is not known |
| Plain, bound whole to one bone | 1,699 (33 %) | what `gr2_write.static_model` writes |
| Plain and skinned: `Position, BoneWeights (4 x u8, normalised), BoneIndices (4 x u8), Normal, [Tangent,] TextureCoordinates0`, 52 or 40 bytes | 652 (12 %) | **measured**: the layout a skinned writer needs |

A unit's skeleton has 22 bones at the median (30 at the upper quartile), 7 deep.

**A unit is a body and what it carries.** The models bound whole to one bone are not small
units: seen on the sheets they are hats, drums, packs, capes, weapons, each a model of its own
that the anim file attaches to a bone of the body (`Bip01 Prop1`, `bone_gun`, `bone_hat` are
among the most used attach points of the survey). The bodies are the skinned and the packed
ones. So a new civilian is a body on an existing skeleton plus attachments, and the attachments
are static models the writer already makes.

Of 6,045 animations:

- **A cyclic animation is not marked as one.** `PeriodicLoop` is set in 3 files and
  `LoopTranslation` in 1. Idle, walk, bored and death alike carry `AccumulationFlags = 2` (93 %);
  the loop is the game's doing, from the anim file. The writer's own death animation writes 0,
  as 62 files do.
- 60 samples a second in 86 %, 30 in 12 %.
- Durations: an idle or a bored 3.0 s, a walk 1.0 s, a run 0.67 s, an attack 1.5 s, a death
  3.3 s.

So a prop unit with a cyclic animation needs **no loop flag at all** — an animation of the right
length, its last pose equal to its first, named as `Idle` in the anim file — and a skeleton far
smaller than a soldier's. What it still needs from the writer is a hierarchy of bones and either
the skinned layout above or one mesh per bone.

## Where the numbers live

| | |
|---|---|
| `profiles/textures.json` | per origin, category, role and material: counts, sizes, formats, the quartiles of grain, saturation, luminance and painted light, the palette, the shares that tile and that carry the player colour |
| `profiles/groupings.json` | per origin, the settlements round a socket and every grouping: units, size, the share of each class, the clear radius, the distances of buildings, props, plants and obstructions, which way the buildings face, the variants of one name |
| `profiles/models.json` | per origin and category: triangles, vertices, bones, vertex layouts, shader effects, sizes, texture pixels per unit, and the animations' durations, rates and flags |
| `profiles/buildings.json` | the buildings by footprint class (the first survey) |
| `core/profile.py` | `art("textures")`, `art("models")`: `group(...)` and `nearest(...)` |

A group of fewer than 8 files is left out of a profile, so no number points at one file.
