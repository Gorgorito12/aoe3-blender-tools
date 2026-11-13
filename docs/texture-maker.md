# The texture maker: a tileable texture from a photograph or a sentence

Making textures is what takes the time. This is the part of the toolkit that makes one: a small
square of material — stone, planks, corrugated iron, thatch — that **repeats without a join**,
from a picture you give it or from the material described in words. The result is an ordinary PNG
in a folder, usable in any program; the add-on can also lay it under its own painting in place of
one of the swatches it ships with.

It is the opposite job to the [AI repaint](ai-textures.md), which must keep every window of a
model's atlas where the geometry put it. A swatch has no geometry to respect, so it may be
redrawn freely — it only has to tile.

## How it is made

`aoe3_blender_tools/core/texmaker.py`, four steps:

1. **An image.** The picture you gave (cropped square), or that picture repainted by Stable
   Diffusion at the strength you choose, or — with no picture — a texture drawn from the prompt
   alone (`comfy.texture_workflow`: an empty latent, no ControlNet).
2. **Tile it** (`wrap_blend`). The image is rolled by half, so its borders become two rows (and
   two columns) that were *neighbours* in the original: it already repeats, with no step at all.
   The old border lands in the middle, and the band across it is blended with its own mirror, so
   the two sides meet exactly. What this leaves is a ghost **in the middle**, never at the border.
3. **Hide the ghost** (`heal`, only with ComfyUI). The texture is repainted, and only the cross
   through the middle is kept. The borders are not touched, so **whatever the AI draws, the
   texture still tiles**. The two ends of each arm of the cross are left as they were, one band's
   length from the border.
4. **De-light and shrink.** The broad light and shade are divided out — a photograph carries the
   light of the day it was taken — and the image is resampled to the swatch size with a wrapping
   resampler, so the join survives the shrink. De-lighting comes *after* the tiling: the broad
   light is measured by a resampler that wraps, and on an image whose two sides do not meet it
   reads that step as light and leaves it in.

## What it costs, measured

On this PC (an RTX 4090, SDXL base, ComfyUI local), at 256 px: **24 to 31 s** from a prompt alone,
**38 s** from a photograph with a prompt (one more pass), **about a second** with `--no-ai`. The
joins measured on those runs: 1.17 and 1.24 from a prompt, 1.13 from a photograph — against 3.97
and 19.32 before the tiling.

## The join, measured

`texmaker.seam(image)` is the step across the wrap over the image's own mean step between
neighbours:

- **about 1.0** — the join is as ordinary as any other pair of pixels. This is what the maker
  produces.
- **above 1.5** (`SEAM_OK`) — it reads as a line; the report says so and suggests another seed or
  a wider band.
- a photograph straight from a camera measures 10 to 40.

Read the number, then look at `<name>_x3.png`: the texture tiled 3 by 3. The metric cannot see a
**landmark that repeats** — one bright stone, one knot in the wood that the eye picks out in every
tile. If you see one, make it again with another seed, or take a flatter part of the photograph.

## In Blender

3D Viewport > Sidebar (N) > AoE3 > **Texture Maker**:

- **Reference**: a picture (JPEG, PNG, anything Blender reads), or empty to work from the words
  alone. With one, **x**, **y** and **part** take a square out of it — *the roof of this factory*
  is a small part somewhere in the picture, not the middle of it.

  **Take a patch of material, not a scene.** A crop that holds a whole building comes back as a
  texture that tiles a whole building: it repeats without a seam, and it is useless. Zoom in until
  the crop is nothing but the stuff — tiles, planks, rust, grass.
- **Material**: the words. With a reference they say what to make of it; without one they are all
  there is, and ComfyUI must be running.
- **Name** and **Licence**. The licence is required and is written beside the texture: a
  photograph carries the rights of whoever took it, and six months later nobody remembers.
- **Size** (128 / 256 / 512), **Metres a tile** (how much of a building one tile covers when the
  painter lays it), **Strength** (how far the AI takes a reference away from the photograph),
  **Seed**.
- **Take the light out** and **Hide the blend**: steps 4 and 3 above.
- **Style** and **Role** (`COLONIAL` + `roof`, `AFRICAN` + `wall`...): with both, the texture is
  laid under the painting in place of that style's own swatch as soon as it is made. **Use the
  Library** does the same for every texture in the library, and puts the add-on's own swatches
  back when pressed again. The style's colour and the grain it expects are kept, so the building
  keeps its colours.
- **Library**: where the textures are kept.

The maker runs in a thread, so Blender stays responsive, and the result is also left as a Blender
image under its own name.

## From the command line

```
venv\Scripts\python -I tools\make_texture.py --name factory_roof --licence "my own photograph" ^
    --image photos\factory.jpg --crop 0.3,0.8,0.25 --prompt "rusted corrugated iron roof" ^
    --size 256 --tile-m 2.0 --style COLONIAL --role roof
venv\Scripts\python -I tools\make_texture.py --name thatch --licence "generated locally" ^
    --prompt "dry golden grass thatch in overlapping courses"
venv\Scripts\python -I tools\make_texture.py --list
```

`--no-ai` never asks ComfyUI: a picture is then only tiled and de-lit, which needs no GPU and no
model. `--crop` is `cx,cy,part` (0..1 of the picture's width and height, and how much of its
shorter side to take).

## The library

```
~/Documents/aoe3-blender-tools/textures/<name>.png      the texture, tileable
                                        <name>.json     what it was made from
                                        <name>_x3.png   it tiled 3 by 3
```

Outside the repository, on purpose: the swatches that ship with the add-on
(`aoe3_blender_tools/materials/`) are CC0 photographs fetched by `tools/fetch_materials.py`, and
nothing generated or photographed belongs there. The sidecar keeps the name, size, metres a tile,
style and role, the mode (`photo`, `photo+ai`, `prompt`), the prompt, seed and strength, the file
the reference came from, the measured join, the licence and the date.

## What the painter takes from it, and what you take from it

Two different things, and it matters:

- **In your own model** the texture is what it looks like: a colour map, tileable, use it in
  Blender or anywhere else.
- **Under the add-on's painting** only its **grain** is used. `core/materials.py` turns a swatch
  into a brightness map around 1.0 (`normalise`), fitted to a contrast measured on the game's own
  textures, and multiplies the colour the style chose by it. So a texture installed as
  `COLONIAL roof` does not make the roof look like that material - it gives the drawn tiles its
  grain, and the colours and every drawn window, course and tile row stay exactly where they
  were. Seen on the colonial house, 2026-11-10: the drawing is untouched, the roof is mottled
  differently.

That is on purpose - the whole point of the atlas is that the drawing lines up with the geometry
([texture-plan.md](texture-plan.md), "The rule") - but it means a swatch is chosen for its
**grain**, not for its picture.

## Against the mod's own textures

Every texture is measured the way the survey measured the mod's (`texmaker.measures`: grain,
saturation and luminance at half size) and compared with the mod's own textures of its **Of**
(wood, stone, roof...) and **For** (buildings, units, nuggets, objects) — or, when the mod has
fewer than eight of that material, of that category, then the original game's. The report and the
sidecar say how far it is, in widths of the middle half of those textures: 0 is their median, 0.5
a quartile, beyond 1 well outside what the mod does.

**Fit to the mod** (on by default; `--no-fit`) then brings the grain and the saturation to their
median: the fine detail is scaled, never the broad shapes or the mean colour, and every step is
per pixel or a blur that wraps, so the texture still tiles. It matters most for a generated
texture: Stable Diffusion's thatch measured 0.69 of saturation where the mod's building textures
sit at 0.37 — 1.4 widths out — and 0.41 after the fit.

## A LoRA of the mod's own hand

The words of a prompt can only say so much. `tools/lora_dataset.py` cuts 512 px pieces out of the
textures the mod itself made and its models wear — never the original game's — and
`tools/train_lora.py` trains a LoRA on them with ComfyUI's own training nodes (0.43 and later; no
custom pack). The LoRA lands in ComfyUI's `models/loras`; **LoRA** in the AI panel, or `--lora
<file>`, draws with it (its trigger word is added to the prompt).

It is the mod's art in another form: the dataset and the LoRA stay on the PC that made them,
outside every repository, and are the team's to share or not. Whether it helps is measured, not
assumed — the same prompts and seeds with and without it, by the distance above
([art-findings.md](art-findings.md)).

Status, 2026-11-10: the dataset is built (900 pieces from 512 of the mod's own textures) and the
whole chain ran on a 20-step trial (a LoRA trained, saved and moved into place in 45 s; 1.5 s a
step at 512 px, two pictures a step, on an RTX 4090). The full training of 1,200 steps and the
comparison are **still to do**: nothing here says yet that the LoRA helps.

Memory is what stops it. The first full run was stopped at step 674: ComfyUI held 15.4 GB and the
PC had 1.5 GB left. A second trial, at batch 1 with two accumulation steps, never reached its
first step: the free memory fell to nothing **while ComfyUI loaded the model and the dataset**,
before any training, and the watchdog stopped it. The batch does not help there: the peak is the
loading. `tools/train_lora.py` therefore trains in resumable chunks (`--chunks`, `--resume`) and
watches the free memory (`--min-free`, 2.5 GB by default), so a run that is stopped loses one
chunk and never freezes the PC. Run it with about 20 GB free (the game, the browser and other
large programs closed).

## Sizes

A swatch is a **material at a distance**, not a close-up. The game shows about 21 pixels per unit
at 1080p, 29 at 1440p and 43 at 4K, and the painter tiles a 256 px swatch over 1.5 to 3 metres of
wall: fine detail under about 5 cm is gone whatever the size. 256 is what the add-on's own
swatches are and what the zip budget expects; 512 is for a material seen close, and 128 for a
plain one.

## What it does not do

- It does not repaint a model's texture — that is [AI repaint](ai-textures.md), and it keeps the
  atlas aligned.
- It makes a **colour** map only. The bump map is still made from the finished building texture
  at export, so the grain of a swatch reaches the relief through the painting.
- It has no idea whether a prompt infringes anyone's rights. SDXL's own licence has use
  restrictions and its model card says "research purposes only"
  ([ai-textures.md](ai-textures.md)): review before publishing anything made with it, and write
  what you know into the licence field.
