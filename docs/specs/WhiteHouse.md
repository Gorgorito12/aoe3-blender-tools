# WhiteHouse

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `WHITE_HOUSE` |
| Style | NEOCLASSICAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 14.60 | 8.98 |
| Depth | 14.60 | 8.98 |
| Height, to the highest point | 13.25 | 8.15 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,235 |
| Low detail, the game's low-poly model | 355 |
| Faces at medium detail | 748 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| white | 364 | 29 % |
| reveal | 238 | 19 % |
| back | 121 | 10 % |
| front | 119 | 10 % |
| side | 106 | 9 % |
| column | 80 | 6 % |
| lead | 56 | 5 % |
| balus | 40 | 3 % |
| stone | 32 | 3 % |
| trim | 28 | 2 % |
| cupwin | 16 | 1 % |
| plinth | 14 | 1 % |
| brick | 10 | 1 % |
| roof | 10 | 1 % |
| pedi | 1 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Painted at | 1024 x 1024 |
| Bump map | 1024 x 1024 |
| All its textures | 5.25 MB |
| Texels per game unit | 67 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 8.14 x 8.14 |
| Model past the obstruction, on each side | 0.42 wide, 0.42 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.05 x 10.05 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 8.15 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.907 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 0.851 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.156 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.701 | 0.28 | 0.661 | 0.851 |
| Flat levels | 2 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.449 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.443 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.109 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 2.50, 13.25 |
