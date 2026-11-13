# A model someone else made

The add-on can texture and export a mesh it did not generate: a prop, a building or a decoration
modelled in Blender (or brought in from another program). Two things work on it — the **AI
repaint** and the **game export** — and a few do not, because they are computed from the
generator's own parameters.

## The checklist

Open the model in Blender, select it, and press **Check** (AoE3 sidebar > Check and Export):
every point below is one of its messages. The export refuses a mesh that fails the first one and warns on the
rest.

| | Why |
|---|---|
| **One UV map**, active, with every corner **inside 0 .. 1** | The game draws one material per model and a texture atlas does not repeat: a UV outside the square shows the wrong part of the image |
| **One image texture**, reachable from a material's node tree | The export reads the first image it finds and writes it as the `.ddt` |
| The texture's sides are **powers of two** (512, 1024, 2048) | The game's format and its mipmaps |
| **Metres**, Z up, the front toward **−Y** | The export converts to the game's basis from there |
| Origin at the **centre of the footprint**, the lowest point at **z = 0** | The game places a model by its origin and stands it on the ground |
| **Rotation and scale applied** (Ctrl+A) | They are not written to the model file |
| At most **65,535** vertices after splitting by UV and normal | Above it the model needs 32-bit indices (the writer switches, 124 of 621 surveyed models use them) |
| No faces pointing down under the model, no two faces in the same plane | Hidden triangles cost the same as visible ones; coplanar faces flicker in game |

A square texture is also needed to repaint a mesh (the zones are read in square pixels).

## Repainting it

AoE3 sidebar > **AI Texture**. With a mesh the generator did not make, the panel has no built-in
materials to work from, so:

- **Your prompt is required.** It describes the material of the whole model, or of the chosen
  zone ("weathered oak staves with iron hoops", "red mud wall, fine cracks").
- The **zones** are the mesh's **material slots**: the bounding box of each slot's UVs becomes a
  region, and **Regions > One region** lists them. A mesh with a single material is repainted as
  one image. A zone thinner than 40 px is left alone.
- Everything else is as it is for a generated building (`docs/ai-textures.md`): the strength, the
  seed, the blend, the edge guard, the player-colour pixels, **Back to the Original**.

The guard compares the edges before and after and keeps the region as it was when they move. A
**perfectly repeating** pattern (an exact grid of identical staves or tiles) lines up with itself
at several shifts, and the guard can read that as movement and keep the region; vary the drawing,
or lower the strength.

## Exporting it as a prop

AoE3 sidebar > **Game Export** > **Kind: Prop**, then **Export for the Game**. A prop bundle is a building bundle without the
building:

| | Building | Prop |
|---|---|---|
| Art folder | `art\<mod>\buildings\<name>\` | `art\<mod>\objects\<name>\` (**Art folder** changes it; the game keeps treasures in `nuggets`) |
| Anim file | construction stages, ground decal, the completion logic | one component, one `Idle` anim, a selection square |
| Death | sinks into the ground, leaves rubble | nothing |
| Proto fields | obstruction, `DeadReplacement`, `PlacementFile` | obstruction only |

Measured on the game's own files (2026-11-10): a prop has no submodel and no `BuildingCompletion`
logic — `nuggets\bear_campsite\nugget_bear_campsite.xml` is five bones, one component with the
model and a ground decal, and one `Idle` anim; `objects\el_dorado\el_dorado.xml` is the same with
only a selection square. `nuggets\abandoned_cabin\abandoned_cabin.xml` adds a death model and a
`Death` anim with the collapse smoke, which `animxml.prop` writes when it is given both.

The proto entry a prop copies is **not** a house: set **Proto template** to a map object or a
treasure of the mod, and `tools/game_deploy.py` clones that one.

An **Empty parented to the object becomes a bone** with its own name, so a socket costs nothing:
name it (`bone_flag_civ` for the civilization flag, or your own) and it is written into the model
and declared in the anim file.

## Several meshes as one set, on one texture

The game keeps small props as **sets**: one unit whose models are its variations, often on one
texture (docs/art-findings.md, "Prop sets"). For a handful of meshes modelled and textured one by
one:

1. Select them all, AoE3 sidebar > **Game Export** > **Pack into One Texture**. Each mesh's
   texture is cut to the box its UVs use, the boxes are packed into one atlas of the panel's
   **Texture** size at **one texel density** (a mesh twice as large gets a box twice as wide), the
   gutters are filled from their edges, and every mesh's UVs are moved onto its box. The meshes
   now share one material.
2. Optional: **AI Texture** repaints them in one go - the boxes are its zones.
3. **Export Prop Set**: one bundle, the meshes in name order as `<name>_0.gr2`, `<name>_1.gr2`...,
   one texture, an anim file with a Variation of them. Its proto entry copies a stock prop set
   (`PropsColony` unless **Proto template** says otherwise).

The generator makes sets too: Building Generator > Style **Prop** > a set > **Generate Set**
lays its models in a row, already on one texture.

## A settlement round a socket

A native settlement is a **grouping**, not a model: an XML that places units round a socket. To
make one from your buildings and sets:

1. Give each mesh the proto name the mod registers it under: a custom property `aoe3_proto` (a
   generated set's objects use the set's name). Optionally `aoe3_class`: `building`, `prop`,
   `plant` or `nature`; without it, a mesh wider than about 5 m is a building.
2. Select them, set **Socket proto** (and an **Obstruction proto** if the mod has an invisible
   one), and press **Compose Settlement**. Copies of the meshes (they share their data) are laid
   out as the mod's own settlements are (distances, counts, a lane left free to the socket,
   buildings facing it about as often as the real ones: a third of the time) in a new collection.
   **Seed** gives the numbered variants.
3. Move and turn them by hand, then **Export Grouping** writes the file where they stand.
   **Import Grouping** brings an existing one in as named markers.
4. `tools/game_deploy.py --install <test copy> --grouping "<file>"` puts it into every
   `RM*/groupings` folder of the copy (`--undo` takes it out).

Which way the game's axes and turns run against Blender's is **to verify** in game; until then a
settlement may come out mirrored or its units turned. `aoe3game/grouping.axes_grouping` writes a
test grouping that settles it.

## What the toolkit cannot do for it

All of these are computed from the generator's parameters, and a mesh that has none gets none:

- the **low-poly** and **damaged** variants (they are the same building rebuilt at LOW detail);
- the **technical sheet** (`docs/specs/`) and the **measured triangle budget** of its footprint
  class. With **Kind: Prop** the check holds it to the original game's props instead: map objects
  have 30 to 350 triangles (the middle half), 106 at the median; treasures 266 to 846, 320 at the
  median ([art-findings.md](art-findings.md));
- its own **collision boxes** (the bundle then names the stock shape);
- the painted texture, the atlas and the region prompts.
