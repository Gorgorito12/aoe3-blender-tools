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

## Pitfalls

- **AI-generated meshes.** Image-to-3D and text-to-3D tools build a sculpted surface. Their
  remeshing at a game budget (measured: 1.4 million faces down to 3,568) leaves wavy walls and
  warped windows and columns. Prompts reduce it but do not remove it. Build the geometry from
  primitives and use such a tool for the texture only (upload the clean mesh to its texturing
  mode), or bake its detailed model onto the clean one.
- **Overlapping coplanar faces.** Two faces in the same plane, facing the same way, that overlap:
  in game they flicker (z-fighting); in a Cycles render they show as a black band (shadow acne).
  Measured on the first White House: the portico platform overlapped the plinth top by 20 cm next
  to the wall. Stop one face where the other begins. The check reports them.
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
| African | 30 presets, 602 to 5,118 (table below) | from the reference radius: 4x4 to 12x12 | 1.9 to 4.2 m walls; customs house 2 storeys | thatch cones and hips, flat roofs with parapets, domes | wall bands, awnings, doors |

African types: each takes the obstruction radius and proto template of the stock building the
style guide names as its size (`core/styles/african/sizes.py`); the plan side is
2 r / 0.615 / ratio (0.72 for radius 2, 0.82 for 3, 0.9 above). Medium detail sits between the
class median and 90th percentile; low detail drops the props, pots, stacks, finials and some
fences, and is under half of medium.

| Type | Template | Radius | Class | Medium, Sub-Saharan / Sahel | Low |
|---|---|---|---|---|---|
| House | House | 2.0 | 4x4 | 684 / 839 | 94 / 84 |
| Town center | TownCenter | 4.5 | 9x9 | 2,008 / 2,361 | 294 / 256 |
| Granary | House | 3.0 | 6x6 | 886 / 602 | 170 / 172 |
| Plot | Farm | 3.0 | 6x6 | 996 / 946 | 28 / 28 |
| Market | Market | 5.0 | 10x10 | 1,890 / 2,019 | 184 / 174 |
| War camp | WarHut | 4.0 | 8x8 | 1,532 / 1,701 | 190 / 184 |
| Stockade (stone) | ypVillage | 4.0 | 8x8 | 1,554 / 1,656 (1,202 / 1,258) | 286 / 264 |
| Armory | Arsenal | 4.0 | 8x8 | 1,367 / 1,562 | 144 / 102 |
| Depot | ArtilleryDepot | 4.0 | 8x8 | 1,330 / 1,359 | 130 / 60 |
| Quarry | House | 4.0 | 8x8 | 1,244 / 1,113 | 130 / 60 |
| Dock | Dock | 4.0 | 8x8 | 1,804 / 1,958 | 476 / 430 |
| Customs house (2 storeys) | ypConsulate | 4.0 | 8x8 | 1,625 / 1,229 (1,679 / 1,283) | 220 / 60 |
| Palace | FortFrontier | 6.0 | 12x12 | 3,688 / 5,118 | 550 / 584 |

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
