# AfricanDepotSahel

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_DEPOT_SAHEL` |
| Style | AFRICAN |
| Type | DEPOT |
| Architecture | SAHEL |
| Proto template | `ArtilleryDepot` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 14.53 | 8.94 |
| Depth | 14.79 | 9.10 |
| Height, to the highest point | 12.48 | 7.68 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,639 |
| Low detail, the game's low-poly model | 224 |
| Faces at medium detail | 801 |
| Target and accepted range | 1,639 (1,393 to 1,885) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| wood | 832 | 51 % |
| trim | 230 | 14 % |
| parapet | 184 | 11 % |
| walls | 94 | 6 % |
| crate | 82 | 5 % |
| barrel | 64 | 4 % |
| reveal | 52 | 3 % |
| stone | 40 | 2 % |
| cloth | 35 | 2 % |
| yard | 22 | 1 % |
| roof_flat | 4 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Painted at | 1024 x 1024 |
| Bump map | 1024 x 1024 |
| All its textures | 5.25 MB |
| Texels per game unit | 49 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 8.00 x 8.00 |
| Model past the obstruction, on each side | 0.47 wide, 0.55 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 10.01 x 10.18 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 7.68 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.844 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 1.0 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.204 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.967 | 0.28 | 0.661 | 0.851 |
| Flat levels | 8 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.665 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.175 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.16 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 0.00, 3.72, 8.64 |
