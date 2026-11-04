# AfricanGranarySahel

Computed from the model by `tools/spec_sheets.py`. Do not edit: regenerate it.

| Field | Value |
|---|---|
| Preset | `AFRICAN_GRANARY_SAHEL` |
| Style | AFRICAN |
| Type | GRANARY |
| Architecture | SAHEL |
| Proto template | `House` |

## Size

| Measure | Metres in Blender | Game units |
|---|---|---|
| Width, with everything on it | 9.75 | 6.00 |
| Depth | 9.92 | 6.10 |
| Height, to the highest point | 9.03 | 5.55 |

One game unit is 1.626 m in Blender.

## Triangles

| Model | Count |
|---|---|
| Medium detail | 660 |
| Low detail, the game's low-poly model | 156 |
| Faces at medium detail | 354 |
| Target and accepted range | 624 (530 to 718) |

Where they go, at medium detail:

| Part | Triangles | Share |
|---|---|---|
| dome | 528 | 80 % |
| rw1 | 32 | 5 % |
| rw2 | 32 | 5 % |
| rw3 | 32 | 5 % |
| trim | 26 | 4 % |
| plinth | 10 | 2 % |

## Texture

| Field | Value |
|---|---|
| Size | 1024 x 1024 |
| Texels per game unit | 84 |
| Swatches under the paint | yes |

## Collision and footprint

| Field | Value |
|---|---|
| Obstruction: units path around it, buildings place against it | 6.00 x 6.00 |
| Model past the obstruction, on each side | 0.00 wide, 0.05 deep |
| Collision shape | `outpost_generic`, a stock shape shared by every generated building, not fitted to this model |
| Ground decal | 8.29 x 8.44 |
| Construction stages | 3x3 |
| Rubble | BuildingRubble3x3 |
| Placement file | buildinglarge.xml |
| Footprint class | 6x6 |

## Shape against the real models (class 6x6)

| Measure | This building | Low | Median | High |
|---|---|---|---|---|
| Height, game units | 5.55 | 4.485 | 6.78 | 8.963 |
| Height over longest side | 0.91 | 0.538 | 0.678 | 1.199 |
| Share of the obstruction covered | 0.924 | 0.499 | 0.732 | 0.837 |
| Share of what stands outside it | 0.028 | 0.055 | 0.132 | 0.314 |
| Share in its largest part | 1.0 | 0.735 | 1.0 | 1.0 |
| Share of the edge lined | 0.183 | 0.329 | 0.678 | 0.834 |
| Flat levels | 1 | 1.0 | 2.0 | 4.0 |
| Triangles in the lower third | 0.127 | 0.253 | 0.473 | 0.615 |
| Triangles in the middle third | 0.242 | 0.253 | 0.351 | 0.437 |
| Triangles in the upper third | 0.63 | 0.112 | 0.207 | 0.287 |

## Attach points

| Name | x, y, z in metres |
|---|---|
| flag_attach | -2.38, -1.10, 8.36 |
