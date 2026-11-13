# PropWell

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `PROP_WELL` |
| Style | PROP |
| Type | WELL |
| Proto template | a map object or a treasure of the mod (set it on export) |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 2.55 | 1.57 |
| Depth | 4.01 | 2.47 |
| Height, to the highest point | 3.23 | 1.99 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 168 |
| Low detail, the game's low-poly model | 168 |
| Faces at medium detail | 72 |
| Target and accepted range | 105 (30 to 348) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| pot | 82 | 49 % |
| stone | 46 | 27 % |
| wood | 40 | 24 % |

## Texture

| Field | Value |
|---|---|
| Size | 256 x 256 |
| Painted at | 256 x 256 |
| Bump map | 256 x 256 |
| All its textures | 0.88 MB |
| Texels per game unit | 49 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 0.74 x 1.16 |
| Model past the obstruction, on each side | 0.41 wide, 0.65 deep |
| Ground decal | 2.15 x 3.38 |
| Kind | a prop: no construction stages, no rubble, no placement file (`objects` art folder) |
