# AfricanPlotSahel

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_PLOT_SAHEL` |
| Style | AFRICAN |
| Type | PLOT |
| Architecture | SAHEL |
| Proto template | `Farm` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 9.84 | 6.05 |
| Depth | 10.07 | 6.19 |
| Height, to the highest point | 2.51 | 1.54 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 971 |
| Low detail, the game's low-poly model | 112 |
| Faces at medium detail | 642 |
| Target and accepted range | 624 (530 to 1,024) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| crop | 825 | 85 % |
| crop_head | 100 | 10 % |
| field | 46 | 5 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 120 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.00 x 6.00 |
| Model past the obstruction, on each side | 0.03 wide, 0.10 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 8.36 x 8.56 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 1.54 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 0.249 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 0.053 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.0 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 0.035 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 0.011 | 0.329 | 0.678 | 0.834 |
| Flat levels | 0 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.795 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.111 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.094 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -6.31, -6.06, 2.72 |
