# AfricanDockSahel

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_DOCK_SAHEL` |
| Style | AFRICAN |
| Type | DOCK |
| Architecture | SAHEL |
| Proto template | `Dock` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 13.91 | 8.55 |
| Depth | 15.30 | 9.41 |
| Height, to the highest point | 10.93 | 6.72 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,584 |
| Low detail, the game's low-poly model | 256 |
| Faces at medium detail | 818 |
| Target and accepted range | 1,639 (1,393 to 1,885) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| wood | 552 | 35 % |
| crate | 280 | 18 % |
| thatch | 182 | 11 % |
| trim | 170 | 11 % |
| barrel | 160 | 10 % |
| parapet | 124 | 8 % |
| walls | 55 | 3 % |
| reveal | 26 | 2 % |
| planks | 16 | 1 % |
| hide | 15 | 1 % |
| roof_flat | 4 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 60 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 8.00 x 8.00 |
| Model past the obstruction, on each side | 0.28 wide, 0.71 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 9.57 x 10.53 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.72 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.714 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 0.954 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.051 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.645 | 0.28 | 0.661 | 0.851 |
| Flat levels | 6 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.55 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.21 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.24 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -2.77, 3.80, 9.74 |
