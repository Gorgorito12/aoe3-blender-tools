# Mansion

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `MANSION` |
| Style | NEOCLASSICAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 12.60 | 7.75 |
| Depth | 10.30 | 6.34 |
| Height, to the highest point | 10.92 | 6.72 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 800 |
| Low detail, the game's low-poly model | 92 |
| Faces at medium detail | 534 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| reveal | 238 | 30 % |
| back | 121 | 15 % |
| front | 119 | 15 % |
| side | 106 | 13 % |
| white | 104 | 13 % |
| balus | 32 | 4 % |
| stone | 30 | 4 % |
| brick | 20 | 2 % |
| trim | 16 | 2 % |
| plinth | 8 | 1 % |
| roof | 6 | 1 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 72 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.34 x 5.18 |
| Model past the obstruction, on each side | 0.71 wide, 0.58 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.71 x 8.76 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.72 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 0.867 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 0.935 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.281 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 1.0 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 0.957 | 0.329 | 0.678 | 0.834 |
| Flat levels | 3 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.374 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.419 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.207 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 0.85, 9.82 |
