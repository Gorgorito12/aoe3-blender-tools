# TimberHouse

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `TIMBER_HOUSE` |
| Style | TIMBER |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 9.70 | 5.97 |
| Depth | 8.50 | 5.23 |
| Height, to the highest point | 11.09 | 6.82 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 426 |
| Low detail, the game's low-poly model | 63 |
| Faces at medium detail | 292 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| reveal | 118 | 28 % |
| ends | 48 | 11 % |
| front_u | 47 | 11 % |
| front_g | 44 | 10 % |
| back_g | 29 | 7 % |
| back_u | 29 | 7 % |
| brick | 28 | 7 % |
| side_g | 22 | 5 % |
| side_u | 22 | 5 % |
| plinth | 10 | 2 % |
| ridge | 10 | 2 % |
| roof | 8 | 2 % |
| soffit | 4 | 1 % |
| dormer_side | 3 | 1 % |
| dormer | 2 | 0 % |
| gable | 2 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 87 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 4.30 x 3.78 |
| Model past the obstruction, on each side | 0.83 wide, 0.72 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 7.72 x 6.76 |
| Construction stages | 2x2 |
| Rubble | BuildingRubble2x2 |
| Placement file | buildingsmall.xml |
| Footprint class | 4x4 |

## Shape against the real models (class 4x4)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.82 | 4.188 | 5.26 | 6.505 |
| Height over longest side | 1.143 | 0.692 | 0.918 | 1.134 |
| Share of the obstruction covered | 1.0 | 0.717 | 0.869 | 0.941 |
| Share of what stands outside it | 0.493 | 0.085 | 0.207 | 0.43 |
| Share in its largest part | 1.0 | 0.971 | 1.0 | 1.0 |
| Share of the edge lined | 1.0 | 0.606 | 0.83 | 0.985 |
| Flat levels | 3 | 1.75 | 3.0 | 5.0 |
| Triangles in the lower third | 0.528 | 0.303 | 0.473 | 0.6 |
| Triangles in the middle third | 0.354 | 0.244 | 0.273 | 0.368 |
| Triangles in the upper third | 0.117 | 0.115 | 0.226 | 0.324 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| chimney_attach | -3.30, 1.75, 11.14 |
| flag_attach | 0.00, 0.00, 10.39 |
