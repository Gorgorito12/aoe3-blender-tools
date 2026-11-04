# ColonialHouse

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `COLONIAL_HOUSE` |
| Style | COLONIAL |
| Type | HOUSE |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 9.90 | 6.09 |
| Depth | 8.75 | 5.38 |
| Height, to the highest point | 8.49 | 5.22 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 362 |
| Low detail, the game's low-poly model | 56 |
| Faces at medium detail | 250 |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| reveal | 118 | 33 % |
| front | 85 | 23 % |
| back | 53 | 15 % |
| side | 38 | 10 % |
| white | 28 | 8 % |
| plinth | 10 | 3 % |
| ridge | 10 | 3 % |
| slab | 8 | 2 % |
| rail | 6 | 2 % |
| roof | 4 | 1 % |
| gable | 2 | 1 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Painted at | 1024 x 1024 |
| Bump map | 1024 x 1024 |
| All its textures | 5.25 MB |
| Texels per game unit | 92 |
| Swatches under the paint | no |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 4.40 x 3.88 |
| Model past the obstruction, on each side | 0.85 wide, 0.75 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 7.87 x 6.96 |
| Construction stages | 2x2 |
| Rubble | BuildingRubble2x2 |
| Placement file | buildingsmall.xml |
| Footprint class | 4x4 |

## Shape against the real models (class 4x4)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 5.22 | 4.188 | 5.26 | 6.505 |
| Height over longest side | 0.857 | 0.692 | 0.918 | 1.134 |
| Share of the obstruction covered | 1.0 | 0.717 | 0.869 | 0.941 |
| Share of what stands outside it | 0.485 | 0.085 | 0.207 | 0.43 |
| Share in its largest part | 1.0 | 0.971 | 1.0 | 1.0 |
| Share of the edge lined | 1.0 | 0.606 | 0.83 | 0.985 |
| Flat levels | 3 | 1.75 | 3.0 | 5.0 |
| Triangles in the lower third | 0.395 | 0.303 | 0.473 | 0.6 |
| Triangles in the middle third | 0.472 | 0.244 | 0.273 | 0.368 |
| Triangles in the upper third | 0.133 | 0.115 | 0.226 | 0.324 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| chimney_attach | -3.20, 1.82, 8.54 |
| flag_attach | 0.00, 0.17, 7.89 |
