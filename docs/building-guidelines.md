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

- Geometry is pure data (`core/building.py`): faces with their corner points, the atlas region
  each uses, and UVs in metres inside that region. Nothing there imports Blender, so it can be
  tested alone.
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

## To verify in the game

Measured since 0.1 (see [game-formats.md](game-formats.md)): the scale of one unit, the attach
point names (`bone_flag_civ`, `bone_chimney`), how construction and destruction are set up, the
`.ddt` format and the alpha channel, the budgets per footprint class, and that the game loads a
generated model and draws it in the world at the right size and lighting, with the civilization
flag on `bone_flag_civ`. Still to see in game ([game-test.md](game-test.md)):

1. The obstruction ring next to a placed stock house.
2. The construction stages and the rubble.
3. The player colour (texture alpha below 255 with the `pixelxform` shader).
4. Why 27 of the mod's models declare 1,000 units per metre yet measure about 0.5 m.
