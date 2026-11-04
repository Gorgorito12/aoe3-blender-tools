# AfricanDockSubSaharan

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_DOCK_SUBSAHARAN` |
| Style | AFRICAN |
| Type | DOCK |
| Architecture | SUBSAHARAN |
| Proto template | `Dock` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 13.17 | 8.10 |
| Depth | 13.13 | 8.08 |
| Height, to the highest point | 11.19 | 6.88 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 1,673 |
| Low detail, the game's low-poly model | 332 |
| Faces at medium detail | 803 |
| Target and accepted range | 1,639 (1,393 to 1,885) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| wood | 742 | 44 % |
| thatch | 396 | 24 % |
| barrel | 160 | 10 % |
| plinth | 160 | 10 % |
| crate | 90 | 5 % |
| rw1 | 48 | 3 % |
| rw2 | 32 | 2 % |
| planks | 30 | 2 % |
| hide | 15 | 1 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 73 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 8.00 x 8.00 |
| Model past the obstruction, on each side | 0.05 wide, 0.04 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 9.07 x 9.04 |
| Construction stages | 4x4 |
| Rubble | BuildingRubble4x4 |
| Placement file | buildinglarge.xml |
| Footprint class | 8x8 |

## Shape against the real models (class 8x8)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 6.88 | 6.17 | 8.5 | 10.785 |
| Height over longest side | 0.849 | 0.589 | 0.852 | 1.01 |
| Share of the obstruction covered | 1.0 | 0.575 | 0.712 | 0.811 |
| Share of what stands outside it | 0.036 | 0.017 | 0.119 | 0.278 |
| Share in its largest part | 1.0 | 0.979 | 0.999 | 1.0 |
| Share of the edge lined | 0.447 | 0.28 | 0.661 | 0.851 |
| Flat levels | 2 | 2.0 | 3.0 | 6.5 |
| Triangles in the lower third | 0.75 | 0.334 | 0.477 | 0.622 |
| Triangles in the middle third | 0.188 | 0.207 | 0.349 | 0.466 |
| Triangles in the upper third | 0.062 | 0.085 | 0.156 | 0.215 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -2.64, 3.34, 11.19 |
