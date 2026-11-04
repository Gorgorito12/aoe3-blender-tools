# AfricanGranarySubSaharan

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_GRANARY_SUBSAHARAN` |
| Style | AFRICAN |
| Type | GRANARY |
| Architecture | SUBSAHARAN |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 9.75 | 6.00 |
| Depth | 9.75 | 6.00 |
| Height, to the highest point | 7.67 | 4.72 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 550 |
| Low detail, the game's low-poly model | 190 |
| Faces at medium detail | 299 |
| Target and accepted range | 624 (530 to 718) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| thatch | 336 | 61 % |
| wood | 118 | 21 % |
| rw1 | 32 | 6 % |
| rw2 | 32 | 6 % |
| rw3 | 32 | 6 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 100 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.00 x 6.00 |
| Model past the obstruction, on each side | 0.00 wide, 0.00 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 8.29 x 8.29 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 4.72 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 0.786 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 1.0 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.018 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 1.0 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 0.303 | 0.329 | 0.678 | 0.834 |
| Flat levels | 0 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.331 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.436 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.233 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -2.38, -1.87, 7.22 |
