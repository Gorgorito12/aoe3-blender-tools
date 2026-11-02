# Building guidelines

What a building needs to work in Age of Empires III (a Direct3D 9 engine from 2007), what goes
wrong with the usual shortcuts, and what is still to be verified in the game.

Facts are marked as **measured** (from this repository's models or tests), **engine limit**, or
**to verify** (an assumption until checked against stock files or in game).

## Requirements

| Aspect | Rule |
|---|---|
| Triangles | A few thousand at most for a large building (to verify against stock models). The generator makes 92 to 413. Many buildings on screen add up: render time is more than half of a late-game frame. |
| Vertices per mesh | Below 65,535 once split by UV and normals: Direct3D 9 meshes usually use 16-bit indices (engine limit). |
| Texture | One power-of-two texture (512 or 1024), one UV set, diffuse colour only, converted to `.ddt`. |
| Lighting | Nothing baked in the texture: the game lights and shadows the model itself. |
| Materials | One, or very few: each one is another draw call. |
| Origin | The centre of the footprint, with the base at ground level. Otherwise the building sinks, floats or turns around the wrong point. |
| Scale and facing | As the stock buildings (to verify). The footprint has to match the obstruction in the unit's proto. |
| Extras | No ground, grass or fence under the building: the game draws its own ground patch. Flags, smoke and fire are separate models on attach points, not part of the mesh. |
| Construction, damage, destruction | Copy them from a stock building's anim XML (to verify how they are built). |

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
- `core/blender_io.py` turns the data into a mesh, a material with the packed texture, a
  Triangulate modifier (the .blend keeps quads for editing) and attach empties.
- `core/validate.py` runs the checks above on the evaluated mesh.

## To verify in the game

1. The scale of 1 unit, against a stock building imported with a `.gr2` importer.
2. Which way stock buildings face.
3. The attach point names that the anim XML expects (the flag first).
4. How construction stages, damage states and destruction are set up in a stock anim XML.
5. The `.ddt` format and whether building textures use the alpha channel for player colour.
6. Triangle and texture budgets of stock buildings of each size.
