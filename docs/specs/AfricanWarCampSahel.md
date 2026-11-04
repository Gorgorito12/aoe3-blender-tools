# AfricanWarCampSahel

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_WAR_CAMP_SAHEL` |
| Style | AFRICAN |
| Type | WAR_CAMP |
| Architecture | SAHEL |
| Proto template | `WarHut` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 14.53 | 8.94 |
| Depth | 14.79 | 9.10 |
| Height, to the highest point | 11.63 | 7.15 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,659 |
| Low detail, the game's low-poly model | 234 |
| Faces at medium detail | 843 |
| Target and accepted range | 1,639 (1,393 to 1,885) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| wood | 646 | 39 % |
| trim | 190 | 11 % |
| stone | 160 | 10 % |
| thatch | 146 | 9 % |
| rw2 | 96 | 6 % |
| parapet | 92 | 6 % |
| pot | 80 | 5 % |
| walls | 59 | 4 % |
| hide | 48 | 3 % |
| roof_flat | 48 | 3 % |
| reveal | 34 | 2 % |
| barrel | 32 | 2 % |
| yard | 22 | 1 % |
| crate | 6 | 0 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 53 |
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
| Height, game units | 7.15 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.786 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 1.0 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.204 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.955 | 0.28 | 0.661 | 0.851 |
| Flat levels | 4 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.762 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.143 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.095 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | 4.42, 4.29, 11.63 |
