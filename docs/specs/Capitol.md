# Capitol

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `CAPITOL` |
| Style | NEOCLASSICAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 20.60 | 12.67 |
| Depth | 17.90 | 11.01 |
| Height, to the highest point | 14.06 | 8.65 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,843 |
| Low detail, the game's low-poly model | 413 |
| Faces at medium detail | 1,152 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| white | 478 | 26 % |
| reveal | 430 | 23 % |
| side | 242 | 13 % |
| back | 189 | 10 % |
| front | 187 | 10 % |
| column | 120 | 7 % |
| lead | 56 | 3 % |
| balus | 40 | 2 % |
| stone | 32 | 2 % |
| trim | 28 | 2 % |
| cupwin | 16 | 1 % |
| plinth | 14 | 1 % |
| roof | 10 | 1 % |
| pedi | 1 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 52 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 11.76 x 10.22 |
| Model past the obstruction, on each side | 0.46 wide, 0.40 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 15.89 x 13.81 |
| Construction stages | 6x6 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 12x8 |

## Shape against the real models (class all)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 8.65 | 3.7 | 6.64 | 9.98 |
| Height over longest side | 0.682 | 0.496 | 0.792 | 1.034 |
| Share of the obstruction covered | 0.873 | 0.445 | 0.699 | 0.852 |
| Share of what stands outside it | 0.117 | 0.016 | 0.126 | 0.394 |
| Share in its largest part | 1.0 | 0.916 | 1.0 | 1.0 |
| Share of the edge lined | 0.722 | 0.255 | 0.612 | 0.851 |
| Flat levels | 2 | 1.0 | 3.0 | 5.0 |
| Triangles in the lower third | 0.584 | 0.282 | 0.449 | 0.623 |
| Triangles in the middle third | 0.358 | 0.231 | 0.315 | 0.454 |
| Triangles in the upper third | 0.059 | 0.083 | 0.167 | 0.261 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 2.65, 14.06 |
