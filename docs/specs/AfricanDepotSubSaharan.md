# AfricanDepotSubSaharan

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_DEPOT_SUBSAHARAN` |
| Style | AFRICAN |
| Type | DEPOT |
| Architecture | SUBSAHARAN |
| Proto template | `ArtilleryDepot` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 14.70 | 9.05 |
| Depth | 14.62 | 8.99 |
| Height, to the highest point | 10.74 | 6.61 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,570 |
| Low detail, the game's low-poly model | 172 |
| Faces at medium detail | 648 |
| Target and accepted range | 1,639 (1,393 to 1,885) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| wood | 1144 | 73 % |
| barrel | 96 | 6 % |
| crate | 88 | 6 % |
| walls | 86 | 5 % |
| reveal | 52 | 3 % |
| stone | 40 | 3 % |
| thatch | 40 | 3 % |
| yard | 22 | 1 % |
| planks | 2 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Painted at | 1024 x 1024 |
| Bump map | 1024 x 1024 |
| All its textures | 5.25 MB |
| Texels per game unit | 50 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 8.00 x 8.00 |
| Model past the obstruction, on each side | 0.52 wide, 0.50 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.12 x 10.06 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.61 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.731 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 1.0 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.221 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.91 | 0.28 | 0.661 | 0.851 |
| Flat levels | 3 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.878 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.118 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.004 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 3.80, 8.62 |
