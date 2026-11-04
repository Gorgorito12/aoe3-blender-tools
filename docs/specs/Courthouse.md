# Courthouse

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `COURTHOUSE` |
| Style | NEOCLASSICAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 11.60 | 7.14 |
| Depth | 14.10 | 8.67 |
| Height, to the highest point | 10.15 | 6.24 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 982 |
| Low detail, the game's low-poly model | 373 |
| Faces at medium detail | 561 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| white | 382 | 39 % |
| reveal | 118 | 12 % |
| side | 94 | 10 % |
| column | 80 | 8 % |
| lead | 56 | 6 % |
| back | 47 | 5 % |
| front | 44 | 4 % |
| balus | 40 | 4 % |
| stone | 32 | 3 % |
| trim | 28 | 3 % |
| brick | 20 | 2 % |
| cupwin | 16 | 2 % |
| plinth | 14 | 1 % |
| roof | 10 | 1 % |
| pedi | 1 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 83 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.46 x 7.86 |
| Model past the obstruction, on each side | 0.34 wide, 0.41 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 7.98 x 9.71 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.24 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.72 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 0.873 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.147 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.766 | 0.28 | 0.661 | 0.851 |
| Flat levels | 2 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.592 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.254 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.155 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 2.25, 10.15 |
