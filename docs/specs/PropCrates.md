# PropCrates

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `PROP_CRATES` |
| Style | PROP |
| Type | CRATES |
| Proto template | a map object or a treasure of the mod (set it on export) |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 3.98 | 2.45 |
| Depth | 4.51 | 2.77 |
| Height, to the highest point | 2.11 | 1.30 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 126 |
| Low detail, the game's low-poly model | 20 |
| Faces at medium detail | 59 |
| Target and accepted range | 105 (30 to 348) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| crate | 56 | 44 % |
| thatch | 38 | 30 % |
| barrel | 32 | 25 % |

## Texture

| Field | Value |
|---|---|
| Size | 256 x 256 |
| Painted at | 256 x 256 |
| Bump map | 256 x 256 |
| All its textures | 0.88 MB |
| Texels per game unit | 61 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 1.14 x 1.30 |
| Model past the obstruction, on each side | 0.65 wide, 0.74 deep |
| Ground decal | 3.35 x 3.80 |
| Kind | a prop: no construction stages, no rubble, no placement file (`objects` art folder) |
