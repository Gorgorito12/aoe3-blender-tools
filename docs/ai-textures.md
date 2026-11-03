# AI textures: Stable Diffusion + ControlNet, local

The add-on can repaint a generated building's texture with a local
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) running Stable Diffusion XL and a ControlNet:
the painted look of a hand-made texture, with every window, door and course where the geometry
needs it. Nothing leaves the PC; the add-on talks to ComfyUI on `127.0.0.1`.

## How it works

The generated atlas is the input. For each region with a prompt (facades, gables, roofs, the
plinth, the bell gable...):

1. the region is cut out of the texture with an 8 px margin of its own edge pixels, and cut into
   overlapping tiles at most twice as long as they are high (SDXL draws badly far from square);
2. each tile is scaled to SDXL's size (long side 1024 px) and sent to ComfyUI: img2img at the
   chosen strength (denoise), held by ControlNet Union (canny mode) on the tile's own edges;
3. the result is scaled back, the tiles are feathered together, the region's mean colour is put
   back (SDXL drifts), and the pixels under the player colour and the alpha are kept;
4. **guard**: if the region's edges moved (a window redrawn, tile rows changed), it is repainted
   again at 0.65 of the strength, and left as it was if they still move.

Regions without a prompt (glass, trims, rails, timber details) or thinner than 40 px are left as
they are. The prompts are in `core/airepaint.py` (`MATERIALS`, one per style and region). The
African style names its walls per piece (`rw0`, `bk1_front`...): round walls get a mud prompt,
blocks mud or adobe by the architecture (`AFRICAN_WALLS`); thatch, flat roofs, domes, parapets,
plinths, stone and fields have their own. **Walls only** and **Roofs only** pick them by
`airepaint.group`.

Measured on the RTX 4090 (texture 1024): about 6 s a region; the colonial house 60 to 90 s, the
timber inn about 2 minutes. Strength 0.35 to 0.5 keeps the drawing (edges moved 0 px on every
region); at 0.65 SDXL starts inventing (lead lattices, tile rows turned to planks), which the
guard catches.

## Install (done on this PC on 2026-11-03)

| What | Where | Size | Licence |
|---|---|---|---|
| ComfyUI portable for Nvidia (`ComfyUI_windows_portable_nvidia.7z`, releases/latest) | `C:\ComfyUI\ComfyUI_windows_portable` | 2.0 GB (4.5 GB extracted) | GPL-3.0 |
| SDXL base 1.0 (`sd_xl_base_1.0.safetensors`) | `...\ComfyUI\models\checkpoints` | 6.9 GB | CreativeML Open RAIL++-M |
| ControlNet Union SDXL ProMax, xinsir (`diffusion_pytorch_model_promax.safetensors`, stored as `controlnet-union-sdxl-promax.safetensors`) | `...\ComfyUI\models\controlnet` | 2.5 GB | Apache-2.0 |

Licences, read on each model's page when downloading: SDXL base is royalty-free with use
restrictions (its Attachment A); its model card also says "research purposes only", which the
licence itself does not: **review before any commercial use**. The ControlNet is Apache-2.0.
`C:\ComfyUI\LICENSES-aoe3bt.txt` keeps the URLs and file sizes. Only core ComfyUI nodes are used
(no custom node packs). Do not swap in a community checkpoint or LoRA without reading its
licence: many forbid commercial use.

Start ComfyUI before repainting (it stays on the local machine):

```
cd C:\ComfyUI\ComfyUI_windows_portable
python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --listen 127.0.0.1 --port 8188 --disable-auto-launch
```

(`run_nvidia_gpu.bat` does the same and opens its web page.) It takes about 20 s to start and
uses about 12 GB of video memory while repainting.

## In Blender

3D Viewport > Sidebar (N) > AoE3 > **AI Texture**:

- the address (`http://127.0.0.1:8188`) and **✓**: is ComfyUI there, with its nodes and models?
- **Start ComfyUI**: starts the portable ComfyUI (folder in **ComfyUI folder**, by default
  `C:\ComfyUI\ComfyUI_windows_portable`) in its own console window; about 20 s later the **✓**
  says "ComfyUI ready". Closing that console stops it. Do not start it twice (one port).
- **Strength** (0.45): how much is repainted; **Blend** (1.0): the repaint over the original;
  **Seed**; **Regions**: all, walls only, roofs only, or **One region** (a list of the active
  building's regions, with the built-in prompt of the chosen one shown under it);
- **Your prompt**: your own description of the material ("red mud wall with white painted
  zigzags"), in place of the built-in one for every region repainted; empty keeps the built-in
  prompts. **Extra prompt**: words added to the prompt ("weathered, mossy", "sun-bleached");
- **AI Repaint**: runs in the background (Blender stays responsive, Esc cancels) and puts each
  region on the model as soon as it is done, so you watch it come; set the viewport to Material
  Preview or Solid with Texture colour to see it. It always starts from the original texture, so
  trying another seed or prompt does not stack repaints;
- **Back to the Original**: the texture as it was, byte for byte.

The repainted texture is what Game Export writes (and what the damaged texture is made from).
**Generate Building** builds the texture again and loses the repaint, like any hand touch-up.
The low-poly model keeps its drawn texture (its atlas is laid out differently).

From the command line: `scripts/game_export.py ... --ai 0.45 [--ai-seed N]`, and
`tools/ai_sweep.py` repaints presets at several strengths and measures each result (edge
shift, colour drift, local contrast).

## In the game (2026-11-03)

The colonial house repainted at 0.45 (`scripts/game_export.py --ai 0.45`) beside the drawn one,
in the test copy: it loads and draws like any texture, player colour and all
(`examples/colonialhouse/ingame_ai.jpg`, repainted on the right). At the game's default camera
distance the difference is small (the 1024 px texture is seen far reduced): the tiles are more
varied, the walls barely change. Close up (`examples/ai_before_after.jpg`, the timber inn) it
shows: varied tiles, stained plaster, softer brick. A stronger look needs a higher strength
(0.5 to 0.55, the guard keeps what moves) or an extra prompt ("weathered, stained, mossy").

## Troubleshooting

- "ComfyUI does not answer at ...": start it (above), or fix the address.
- "checkpoint ... is not in ComfyUI's models/checkpoints": the file name must be the one above.
- A region keeps its drawing ("kept" in the status): its edges moved even at the lower
  strength; lower the strength or change the seed.
- Colours look washed or too dark: Blend below 1.0, or a lower strength.
