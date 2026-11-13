# PropBarrels

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `PROP_BARRELS` |
| Style | PROP |
| Type | BARRELS |
| Proto template | a map object or a treasure of the mod (set it on export) |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 1.58 | 0.97 |
| Depth | 4.59 | 2.83 |
| Height, to the highest point | 1.36 | 0.84 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 114 |
| Low detail, the game's low-poly model | 38 |
| Faces at medium detail | 51 |
| Target and accepted range | 105 (30 to 348) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| barrel | 96 | 84 % |
| crate | 18 | 16 % |

## Texture

| Field | Value |
|---|---|
| Size | 256 x 256 |
| Painted at | 256 x 256 |
| Bump map | 256 x 256 |
| All its textures | 0.88 MB |
| Texels per game unit | 64 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 0.46 x 1.32 |
| Model past the obstruction, on each side | 0.26 wide, 0.75 deep |
| Ground decal | 1.33 x 3.87 |
| Kind | a prop: no construction stages, no rubble, no placement file (`objects` art folder) |
