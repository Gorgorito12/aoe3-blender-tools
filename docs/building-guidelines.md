# Building guidelines

What a building needs to work in Age of Empires III (a Direct3D 9 engine from 2007), what goes
wrong with the usual shortcuts, and what is still to be verified in the game.

Facts are marked as **measured** (from this repository's models or tests), **engine limit**, or
**to verify** (an assumption until checked against stock files or in game).

## Requirements

| Aspect | Rule |
|---|---|
| Triangles | **Measured** on 621 buildings of the target mod: median 1,016, 90th percentile 2,420. For an 8 x 8 unit footprint (205 buildings): median 1,102, 90th percentile 2,221. The check uses the profile's numbers for the building's footprint class. The generator makes 92 to 3,035. |
| Vertices per mesh | **Measured**: most models use 16-bit indices (497 of 621); 124 use 32-bit ones, so more than 65,535 vertices works. The writer picks 16-bit when it can. |
| Texture | One texture, one UV set. **Measured**: the mod's building textures are mostly 256 x 256 or 512 x 512 DXT3; uncompressed BGRA is also common. The writer makes BGRA with mip levels. V counts from the top row (see game-formats.md). |
| Lighting | Nothing baked in the texture: the game lights and shadows the model itself. |
| Materials | One, or very few: each one is another draw call. |
| Origin | The centre of the footprint, with the base at ground level. Otherwise the building sinks, floats or turns around the wrong point. |
| Scale and facing | **Measured**: the stock buildings declare 0.615157485 units per metre (one game unit is about 1.63 m); the game's distances are in those units. The obstruction radius is about 0.91 of the model's half side (8 x 8 class). Facing: the writer keeps Blender's front (-Y) as the front, as the stock models' front in the editor preview (**in game**). |
| Extras | No ground, grass or fence under the building: the game draws its own ground patch. Flags, smoke and fire are separate models on attach points, not part of the mesh. |
| Construction, damage, destruction | **Measured**: construction stages reuse the stock models `buildings\constructions\<NxN>_stage1..3`, chosen by `BuildingCompletion` in the anim file; destruction leaves the proto's `DeadReplacement` rubble. Details in [game-formats.md](game-formats.md). |

## How real buildings are built

Measured with `tools/shape_survey.py` on 322 models of the game and the target mod (quartiles in the
profile's `shape`; `tests/test_shape.py` holds every African preset to them). In game units:

| Class | Height | Height / side | Obstruction covered | Parts | Flat levels |
|---|---|---|---|---|---|
| 4x4 | 4.2 to 6.5 | 0.69 to 1.13 | 72 to 94 % | 1 | 3 |
| 6x6 | 4.5 to 9.0 | 0.54 to 1.20 | 50 to 84 % | 1 | 2 |
| 8x8 | 6.2 to 10.8 | 0.59 to 1.01 | 58 to 81 % | 1 | 3 |
| 9x9 | 7.8 to 13.4 | 0.77 to 1.41 | 52 to 80 % | 1 to 3 | 4 |
| 10x10 | 6.4 to 11.1 | 0.58 to 1.05 | 52 to 69 % | 1 to 8 | 3 |
| 12x12 | 9.2 to 14.4 | 0.77 to 1.01 | 53 to 71 % | 1 to 2 | 5 |

- One mass: over 95 % of what stands is one connected part; props touch it, or stand on its base.
  Units leave a building, so nothing is scattered round it and its door stays clear.
- As tall as wide, with doors and props out of proportion to a person. Layouts are drawn at human
  size and scaled up (`sizes.SCALE`, `sizes.TALL`) so everything grows together.
- About 3 levels, and the roofs carry things: domes, chimneys, stairs, rooms.
- Triangles: about 48 % in the lower third of the height, 35 % in the middle, 16 % at the top.
- A closed yard is rare: 20 of 322 models, mostly forts and military compounds. Most are solid.
- One mesh, with the building's own texture and a texture of props shared between buildings; bones
  with a job (`bone_smoke`, `bone_sparks`, launch points, the flag), and a ground decal larger than the
  footprint (10 x 10 under an 8x8) that blends the base into the terrain.

## Budgets for a new building

Check a new building against these before calling it done, and against the real models of its
function. Its technical sheet in `docs/specs/` shows each number.

**Triangles.** The stock fort, 12 x 12: 1,589 for the normal model, 961 low-poly, 4,179 damaged. The
Sahel palace, the same class: 1,610, 608, 1,610. Palaces and wonders of real mods run from about 1,300
to 4,400. The normal model is what is always on screen, so it carries the budget.

**Segments of the bodies that are not boxes.** A box costs five quads whatever its size; a round
wall, a cone, a dome, an arch cost what is asked of them. `BuildingParams.poly` is the multiplier
of every one of those counts (`core/resolution.py`, the panel's **Segments**): 1.0 is exactly what
the style always asked for, 0.6 a cheaper building, 1.5 a finer one. Measured 2026-11-10 at
medium detail: the Sub-Saharan house 626 triangles at 1.0, 458 at 0.75, 290 at 0.5; the
Sub-Saharan town center 2,968 / 2,368 / 1,960; the Sahel granary (a dome) 660 / 360 / 204; the
White House 1914 3,035 / 2,587 at 0.6. A building of boxes alone (the colonial house) does not
move at all.

Two things to know before using it:

- it **never takes a round wall below the sides the low-detail model already uses** (8, or 10 for
  a big one), because `core/joints.py` measures an embedding on that polygon: below it a wing
  that sits inside a hut today would poke out, and every layout would have to be proved again.
  So it makes the medium model cheaper - the one that is always on screen - and leaves the low
  one alone;
- on a **composed** building (the African layouts) the budget decides the total: the composer
  fills up to `sizes.tris_target`, so a cheaper shape buys more props rather than fewer
  triangles. Lower the target, not the segments, to spend less there.

What it does not reach: the roofs. `hipped_roof`, `gable_roof`, `shed_roof`, `dormer`,
`bell_gable` and `pyramid` are built from 1 to 7 faces by construction and have no subdivision to
scale. The timber style has no round body at all, so nothing there changes either.

`resolution.chord_error(radius, n)` says how far a polygon of n sides sags inside the circle, and
`sides_for(radius, error)` the fewest sides that keep that sag under a given one. At the game's
camera (about 21 pixels per unit at 1080p, 43 at 4K, a unit being 1.63 m) a sag under about 4 cm
is under a pixel: **to verify** in game, it is geometry, not a measurement of the engine.

**Textures.** Cost is what most often goes unseen: a building of 1,600 triangles can carry 20 MB of
textures. Real wonders use 0.3 to 2.7 MB. A 2048 colour texture with its mips is 5.3 MB, a 1024 one 1.3
MB, a 512 one 0.33 MB; a DXT5 bump without mips is 4, 1 and 0.25 MB.

- Paint large and export small: `sizes.TEXTURE_BUDGET` paints at 2048 and halves to 1024, with a 512
  bump. Halving gives exactly the mip level the game would show. Painting at 1024 instead gives another
  picture (28 dB), because stones and patches come out differently.
- Compare texels with screen pixels: 1024 on this palace is 31 texels per game unit, and the game shows
  about 21 pixels per unit at 1080p, 29 at 1440p and 43 at 4K at its normal zoom. Above 1:1 nothing is
  lost. Seen in game, 2048 against 1024: 34 dB at normal zoom, 31 dB close up, with no visible change.
- With a budget the damaged model shares the main texture. It only shows while the building falls, and
  it was half of all the weight.
- Compress. Uncompressed 256 x 256 BGRA costs as much as 512 x 512 DXT5 and looks worse.
- Fine detail under about 5 cm is gone at the game's camera whatever the size: paint broad.

**Props and treasures** (measured on the original game's own, `profiles/models.json`; the mod made
too few to measure): a map object is one thing at 30 / 106 / 348 triangles (quartiles), a treasure
an accident and its spilled cargo at 266 / 320 / 846, each with two bones and a 256 or 512 texture
at 50 to 70 pixels a unit. A settlement piece of the game is 63 / 95 / 268 triangles and 2.0 / 3.2 /
5.4 units wide. The PROP style fills a prop up to its group's median and never past its upper
quartile; its technical sheet shows the band. Its low model drops the cargo under 40 triangles.

**Collision.** Real models stand past their obstruction: the stock fort's reaches 7.3 from the centre on
a square of 12, and 11.9 % of what stands is outside it. Keep about that share, and measure it
(`outside` in the sheet). A square much larger than the model is as wrong: units stop in empty ground.
See "Collision" in [game-formats.md](game-formats.md).

**Rubble and ground.** Choose rubble by the model's size and not only its class: 6x6 for a palace of 12 x
12, where the class gave 4x4. Stock ground decals bring their own debris: a building that needs clean
ground gets its own.

## Pitfalls

- A buttress is not a wedge stuck on a wall. Over a corner, it touches both walls: its foot wraps the
  corner, it keeps most of its width as it rises while it loses its depth, so it runs out into the
  walls, and a chamfer down the outer corner carries the line that divides it (`parts._pier`).
  Take such forms from several views: one view hides the sections and the sides of a building.
- Texture detail under about 5 cm is gone at the game's camera, and its sun bleaches pale walls.
  Paint stones about 0.5 m long with joints 5 cm wide, and keep walls darker than they look right
  in a render. Check in game, next to a stock building.

- **AI-generated meshes.** Image-to-3D and text-to-3D tools build a sculpted surface. Their
  remeshing at a game budget (measured: 1.4 million faces down to 3,568) leaves wavy walls and
  warped windows and columns. Prompts reduce it but do not remove it. Build the geometry from
  primitives and use such a tool for the texture only (upload the clean mesh to its texturing
  mode), or bake its detailed model onto the clean one.
- **Overlapping coplanar faces.** Two faces in the same plane, facing the same way, that overlap:
  in game they flicker (z-fighting); in a Cycles render they show as a black band (shadow acne).
  Measured on the first White House: the portico platform overlapped the plinth top by 20 cm next
  to the wall. Stop one face where the other begins. The check reports them.
- **Volumes that cross badly.** A tower and a wing can pass every check and still look wrong:
  corners outside the cylinder, parapets and pinnacles running through it, a sliver of air between
  two walls. Measured on the first Sahel town center: wings 5.2 m wide against a tower of radius
  3 m, their corners 0.6 m out of it and 0.1 m between neighbours. Keep volumes at least 0.25 m
  apart, or end one entirely inside a taller one, counting the polygon of the low-detail model and
  not the radius, and declare that side `joined` so it carries nothing. `core/joints.py` checks
  it; the coplanar check does not.
- **Hidden faces.** The bottom of each box is never seen from the game camera: leave it out.
- **Baked light.** A texture with one bright and one dark side looks wrong under the game's
  lighting.
- **Texture atlas and tiling.** An atlas does not repeat: a face larger than its region is scaled
  down to fit (lower texel density) rather than tiled.

## How the generator works

- Geometry is pure data (`core/building.py` dispatches to a style in `core/styles/`, which
  builds with the pieces of `core/kit.py`): faces with their corner points, the atlas region
  each uses, and UVs in metres inside that region. A style declares every region first, packs
  the atlas, then adds the faces (they read their region's size); the order of both is part of
  the output. Nothing there imports Blender, so it can be tested alone.
- `core/atlas.py` shelf-packs the regions (facades, roof, trims, columns, brick, …) into one
  square texture at the largest uniform texel density that fits.
- `core/paint.py` paints each region at twice the final size and filters it down. Facade regions
  map one to one onto their walls, so the windows land where the painter puts them.
- At medium detail, each wall is one polygon with its openings as holes: every stack of
  openings is joined to the bottom edge, and to the opening below it, by a zero-width slit, and
  the result is ear-clipped. That needs far fewer triangles than a grid (91 instead of 160 on the
  White House front) and adds no T-junction: the slits only add points on the wall's bottom edge
  and on the top edges of openings, where no other face has an edge. A layout that cannot be slit
  (an opening wider than the one below it) falls back to a grid, also without T-junctions.
- Openings are recessed by 18 cm, with side and sill reveals and a back face that keeps the
  facade's UVs, so the painted glass and door show on it. There is no top reveal (it faces down,
  away from the game camera) and no sill under a door (the plinth top is its floor; a sill there
  would be coplanar with it).
- `core/blender_io.py` turns the data into a mesh, a material with the packed texture, a
  Triangulate modifier (the .blend keeps quads for editing) and attach empties.
- `core/validate.py` runs the checks above on the evaluated mesh.

## Styles

| Style | Presets (medium detail) | Footprint class | Storey | Roof | Player colour |
|---|---|---|---|---|---|
| Neoclassical | White House 1,235 tris; the others 92 to 413 at low detail | 6x6 (Mansion) to 16x16 (White House 1914) | 3.1 m | hipped, slate | string courses, shutters |
| Timber framing | Timber House 426 (low 63), Timber Inn 725 (low 108) | 4x4 (house), 6x6 (inn) | 2.7 m, ground floor of stone or brick 3.0 m | gable, plain tiles, pitch 0.7 to 1.6, dormers | shutters, door, sign |
| Spanish colonial | Colonial House 362 (low 56), Colonial Trading House 646 | 4x4 (house), 6x6 (trading house) | 2.9 m | gable or hipped, clay tiles, 0.45 m eave | shutters, door leaf |
| African | 30 presets, 602 to 4,776 (table below) | from the reference radius: 4x4 to 12x12 | 1.9 to 4.2 m walls; customs house 2 storeys | thatch cones and hips, flat roofs with parapets, domes | wall bands, awnings, doors |

African types: each takes the obstruction radius and proto template of the stock building the
style guide names as its size (`core/styles/african/sizes.py`); the plan side is
2 r / 0.615 / ratio (0.72 for radius 2, 0.82 for 3, 0.9 above). Medium detail is within 15 % of
the median of the target mod's **own** building models of its class (`sizes.TRIS_TARGET`,
`tests/test_african_budget.py`): 4x4 618, 6x6 624, 8x8 1,639, 9x9 3,627, 10x10 1,880, 12x12
4,174. The mod's own models (127) have a median of 1,639 triangles against 643 for the stock
models it reuses (229), so they, not the stock ones, set the level. Low detail drops the props,
pots, stacks, finials and some fences, and is under half of medium.

| Type | Template | Radius | Class | Medium, Sub-Saharan / Sahel | Low |
|---|---|---|---|---|---|
| House | House | 2.0 | 4x4 | 684 / 697 | 94 / 84 |
| Town center | TownCenter | 4.5 | 9x9 | 3,456 / 3,477 | 542 / 536 |
| Granary | House | 3.0 | 6x6 | 694 / 602 | 114 / 172 |
| Plot | Farm | 3.0 | 6x6 | 660 / 610 | 28 / 28 |
| Market | Market | 5.0 | 10x10 | 1,890 / 2,019 | 184 / 174 |
| War camp | WarHut | 4.0 | 8x8 | 1,532 / 1,701 | 190 / 184 |
| Stockade (stone) | ypVillage | 4.0 | 8x8 | 1,554 / 1,656 (1,618 / 1,672) | 286 / 264 |
| Armory | Arsenal | 4.0 | 8x8 | 1,511 / 1,562 | 144 / 102 |
| Depot | ArtilleryDepot | 4.0 | 8x8 | 1,578 / 1,717 | 130 / 60 |
| Quarry | House | 4.0 | 8x8 | 1,420 / 1,423 | 130 / 102 |
| Dock | Dock | 4.0 | 8x8 | 1,804 / 1,852 | 476 / 430 |
| Customs house (2 storeys) | ypConsulate | 4.0 | 8x8 | 1,625 / 1,741 (1,679 / 1,795) | 220 / 142 |
| Palace | FortFrontier | 6.0 | 12x12 | 3,688 / 4,776 | 550 / 584 |

Class budgets (medium target between them): 8x8 median 1,102, 90th percentile 2,221; 9x9 1,235
and 3,627; 10x10 1,886 and 2,638; 12x12 1,809 and 6,397. In the African style the round walls,
thatch cones (in tiers at medium), adobe blocks, parapets and merlons, projecting beams,
buttresses, palisade logs, posts, decks on piles, ridges of a field and the props are geometry;
mud smears, thatch courses, trowel marks, the openings' reveals, doors, cloth stripes and stone
joints are painted. Pieces that touch never share a face: palisade panels stop short of the
corner logs, stone walls end in piers, and the palace's walls sink into its towers. Round walls, thatch cones, domes, pots and the round props are smooth-shaded (their normals shared
across the sides, also in the game mesh): they light as one surface instead of facets, with no
extra triangles; flat tops and bottoms stay flat. The Dock
template only places on water.

The footprint class is the measured class (10 buildings or more) whose median model side is
closest to the building's longer side; a non-square class also needs a building-like obstruction
ratio (0.8 or more). Matching the obstruction alone let a few long walls (class 6x8, ratio 0.57)
attract every large building, and ties between 6x4 and 6x6 went to whichever came first.

Measured class budgets (the survey): 4x4 median 571 triangles, 90th percentile 1,613; 6x6 median
491, 90th percentile 1,024. Geometry against painting in the colonial style: walls, plinth,
roof, gables, ridge caps, balcony slab and railing, portal piers and arches, the lean-to roof and
the bell gable are geometry; windows, grilles, shutters, the door, beam ends under the eave,
the dado, tiles, bells and the railing's balusters are painted. At medium detail the openings are
recessed; an upper window is never wider than the one below it, so each wall stays one polygon
with holes (a wider one above sends the wall to the grid fallback and doubles its triangles).

In the timber style the walls, the jetty's soffit and joist ends (front only), roof, framed
gables, dormers, chimneys and the sign are geometry; posts, rails, braces, infill, windows with
leaded panes, shutters, the door, rubble stone and bricks are painted. The framing is laid out
from the openings (a post beside every window, an extra one in wide panels), so it always meets
the windows.

Every style builds with `core/kit.py`: the regions first, then `pack()`, then the faces. The order
of both is part of the output, so a refactor keeps them; the neoclassical presets are held byte
for byte by `tests/test_golden.py`.

## To verify in the game

Measured since 0.1 (see [game-formats.md](game-formats.md)): the scale of one unit, the attach
point names (`bone_flag_civ`, `bone_chimney`), how construction and destruction are set up, the
`.ddt` format and the alpha channel, the budgets per footprint class, and that the game loads a
generated model and draws it in the world at the right size and lighting, with the civilization
flag on `bone_flag_civ`. Also seen since: player colour, the building's own icon and portrait,
the construction stages and the rubble. Still to see in game ([game-test.md](game-test.md)):

1. The obstruction ring against neighbouring buildings and walking units.
2. Why 27 of the mod's models declare 1,000 units per metre yet measure about 0.5 m.
