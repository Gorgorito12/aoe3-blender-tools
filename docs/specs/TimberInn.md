# TimberInn

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `TIMBER_INN` |
| Style | TIMBER |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 12.70 | 7.81 |
| Depth | 10.20 | 6.27 |
| Height, to the highest point | 14.20 | 8.74 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 725 |
| Low detail, the game's low-poly model | 108 |
| Faces at medium detail | 493 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| reveal | 214 | 30 % |
| back_u | 87 | 12 % |
| front_u | 87 | 12 % |
| ends | 74 | 10 % |
| brick | 56 | 8 % |
| back_g | 47 | 6 % |
| front_g | 44 | 6 % |
| side_u | 38 | 5 % |
| side_g | 22 | 3 % |
| roof | 12 | 2 % |
| plinth | 10 | 1 % |
| ridge | 10 | 1 % |
| sign | 8 | 1 % |
| dormer_side | 6 | 1 % |
| dormer | 4 | 1 % |
| soffit | 4 | 1 % |
| gable | 2 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 67 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.40 x 5.14 |
| Model past the obstruction, on each side | 0.71 wide, 0.57 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.80 x 8.67 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 8.74 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 1.118 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 1.0 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.337 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 1.0 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 1.0 | 0.329 | 0.678 | 0.834 |
| Flat levels | 2 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.517 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.359 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.124 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| chimney_attach | -4.80, 2.17, 14.25 |
| flag_attach | 0.00, 0.05, 13.50 |
