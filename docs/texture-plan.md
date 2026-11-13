# Texture plan: options to try

The generated textures line up exactly with the geometry (each window is painted where its
opening is), but they look flat and vector-like. This page lists the ways to give them a
hand-painted look without losing that alignment, what each costs, and the order to try them.

Status (2026-11-10): relief baking is done (a bump map from each finished texture) and material
swatches are done (five CC0 photos from ambientCG under the painting, `core/materials.py`, credits
in `aoe3_blender_tools/materials/MATERIALS.md`; their grain is fitted to a contrast measured on
the stock textures by `tools/palette_survey.py`). Stable Diffusion + ControlNet is done, local,
with a button in the add-on: [ai-textures.md](ai-textures.md). **Making a swatch is done too**:
the texture maker turns a photograph or a sentence into a tileable texture, keeps it in a library
with its licence, and can lay it under the painting in place of one of the add-on's own
([texture-maker.md](texture-maker.md)). The rest is not tried yet. Licence and price
facts are as known on 2026-11-02 and are marked **to verify**: check each model's or service's
page before publishing anything made with it.

## The rule

Any method must keep the atlas layout: a window that moves by a few pixels no longer matches its
opening. The generated atlas is therefore the input (the "map"), not something to replace.

One output is exempt, and only one: a **standalone tileable swatch**. It carries no geometry to
line up with, because the add-on is what places it — it is tiled under the painting at a chosen
number of metres per tile, and every drawn window and course is put on top afterwards. That is
what the texture maker makes.

## Options

| Option | What it is good for | Keeps the alignment | Cost | Runs where |
|---|---|---|---|---|
| **Relief baking** | Depth: a dense version of the building (stone blocks, mouldings, frames in relief) baked onto the low-poly texture as cavity shading | Yes (same UVs) | Free | Blender, headless; can be built and tested in this repository |
| **Stable Diffusion + ControlNet, local** | The final hand-painted look: the atlas repainted in a painterly style, ControlNet locking the structure to the pixel | Yes, at low denoise with structure control | Free (electricity) | The user's PC (an RTX 4090 runs SDXL with ControlNet in seconds) |
| **A tileable swatch made here** (texture maker) | The material itself - stone, planks, rusted iron, thatch - from a photograph or from a sentence, repeating with no join | Yes: the add-on tiles and places it, and the drawing goes on top | Free (electricity), or free and no GPU at all for a photograph | The user's PC |
| **ChatGPT image generation** | Concept art and references; icons and portraits | No for whole textures (it reinterprets layouts) | Subscription or per-image API, **to verify** | Web or API |
| **Meshy, texture mode on our mesh** | A quick textured look on the clean mesh, the shape kept | Partly: it may move windows and bake light | Paid per generation, **to verify** | Web |
| **CC0 material libraries** (Poly Haven, ambientCG) | Real stone, slate and brick, blended with the drawing and softened to the game's style | Yes (the add-on places them) | Free, CC0, **to verify per asset** | Download |
| **Claude Design** | Ornaments with exact shapes as SVG (friezes, pediment reliefs, coats of arms, hieroglyph bands) stamped into the atlas; building icons and portraits; a style sheet per civilization | Yes for stamped elements | Included with Claude | claude.ai |
| **Hand touch-up** (Blender texture paint, Krita) | Final details | Yes | Free | The user's PC |

## Stable Diffusion + ControlNet: what to install

All free and local (**to verify** current versions and licences):

- **ComfyUI** (open source): the node-based interface; a workflow file can be shipped with this
  repository so the user only loads it and runs it.
- **SDXL base** (Stability AI, CreativeML Open RAIL++-M: commercial use allowed, with use
  restrictions). The newer Stability models use a community licence, free under 1 million dollars
  of yearly revenue.
- **ControlNet models for SDXL**: lineart or canny (locks the drawing's edges), tile (repaints
  detail while keeping the image), optionally depth (from a render of the model).
- Community checkpoints and style models (for example from Civitai) each carry their own licence;
  some forbid commercial use. Read it before using one.

Workflow to build: atlas PNG in, one region at a time (facades, roof, trims), ControlNet lineart +
tile at low denoise, a prompt per material ("hand-painted stone facade, RTS game texture, flat even
lighting, no shadows"), the result written back at the same size, then the add-on's checks.

## Order

1. **Relief baking**: no external tool, testable here, adds the most depth.
2. **Material swatches** tiled and blended by the add-on under its own windows and trims: the
   biggest jump in look. Done on both halves - CC0 photographs downloaded by
   `tools/fetch_materials.py`, and swatches made here from a photograph or a prompt
   ([texture-maker.md](texture-maker.md)).
3. **Stable Diffusion + ControlNet** on the user's PC, with a ComfyUI workflow and scripts
   prepared in this repository.
4. **Claude Design** ornaments and the building's icon and portrait.
5. Meshy texture mode as a comparison, and hand touch-up last.

The art survey of the target mod (README, "Art survey") should come before steps 2 and 3: it gives
the palette, contrast and level of painted shading the textures must match.
