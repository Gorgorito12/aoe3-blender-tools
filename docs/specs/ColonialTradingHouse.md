# ColonialTradingHouse

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `COLONIAL_TRADING_HOUSE` |
| Style | COLONIAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 11.90 | 7.32 |
| Depth | 12.60 | 7.75 |
| Height, to the highest point | 8.94 | 5.50 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 646 |
| Low detail, the game's low-poly model | 167 |
| Faces at medium detail | 411 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| reveal | 136 | 21 % |
| post | 104 | 16 % |
| front | 85 | 13 % |
| white | 67 | 10 % |
| arcade | 54 | 8 % |
| back | 53 | 8 % |
| side | 38 | 6 % |
| plinth | 26 | 4 % |
| wing_long | 22 | 3 % |
| ridge | 20 | 3 % |
| wing_short | 11 | 2 % |
| roof | 8 | 1 % |
| slab | 8 | 1 % |
| rail | 6 | 1 % |
| bell | 3 | 0 % |
| gable | 3 | 0 % |
| shed | 2 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 76 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 5.98 x 6.34 |
| Model past the obstruction, on each side | 0.67 wide, 0.71 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.12 x 10.71 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 5.5 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 0.71 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 0.884 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.311 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 1.0 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 0.853 | 0.329 | 0.678 | 0.834 |
| Flat levels | 2 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.585 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.282 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.133 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| chimney_attach | -4.20, 0.53, 8.21 |
| flag_attach | 0.00, -4.00, 8.94 |
