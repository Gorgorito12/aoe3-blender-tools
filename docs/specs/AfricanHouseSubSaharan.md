# AfricanHouseSubSaharan

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_HOUSE_SUBSAHARAN` |
| Style | AFRICAN |
| Type | HOUSE |
| Architecture | SUBSAHARAN |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 8.03 | 4.94 |
| Depth | 8.03 | 4.94 |
| Height, to the highest point | 11.10 | 6.83 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 626 |
| Low detail, the game's low-poly model | 92 |
| Faces at medium detail | 322 |
| Target and accepted range | 618 (525 to 711) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| thatch | 288 | 46 % |
| plinth | 128 | 20 % |
| pot | 82 | 13 % |
| rw1 | 64 | 10 % |
| wood | 42 | 7 % |
| yard | 22 | 4 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Painted at | 1024 x 1024 |
| Bump map | 1024 x 1024 |
| All its textures | 5.25 MB |
| Texels per game unit | 76 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 4.00 x 4.00 |
| Model past the obstruction, on each side | 0.47 wide, 0.47 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 6.39 x 6.39 |
| Construction stages | 2x2 |
| Rubble | BuildingRubble2x2 |
| Placement file | buildingsmall.xml |
| Footprint class | 4x4 |

## Shape against the real models (class 4x4)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.83 | 4.188 | 5.26 | 6.505 |
| Height over longest side | 1.382 | 0.692 | 0.918 | 1.134 |
| Share of the obstruction covered | 1.0 | 0.717 | 0.869 | 0.941 |
| Share of what stands outside it | 0.337 | 0.085 | 0.207 | 0.43 |
| Share in its largest part | 1.0 | 0.971 | 1.0 | 1.0 |
| Share of the edge lined | 0.786 | 0.606 | 0.83 | 0.985 |
| Flat levels | 0 | 1.75 | 3.0 | 5.0 |
| Triangles in the lower third | 0.514 | 0.303 | 0.473 | 0.6 |
| Triangles in the middle third | 0.307 | 0.244 | 0.273 | 0.368 |
| Triangles in the upper third | 0.179 | 0.115 | 0.226 | 0.324 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -0.34, 0.17, 11.10 |
