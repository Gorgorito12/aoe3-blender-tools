# Tools

Standalone Python scripts (standard library only); run them with `python -I` from the repository
root.

| Script | What it does |
|---|---|
| `bar.py` | Lists or extracts the files of the game's `.bar` archives, to get stock models, textures and anim XML as references on your own machine. `python -I tools/bar.py <archive.bar> [filter] [--extract <folder>]` |
| `xmbedit.py` | Reads and writes the game's compiled XML (`.xmb`): `check`, `to-xml`, `from-xml` (with `--compress`), and `add-unittype` to add a unit type to protos. Run it without arguments for the full usage. |
| `art_survey.py` | Surveys the art of the game or a mod (models, textures, anim files, `.bar` archives in memory) and writes `report.json` and `summary.md`; with `--proto`, joins the buildings to their models and measures them, and `--profile-out` writes the calibration profile. See the main README. The reports name the scanned files: keep them out of public repositories (the profile does not). |
| `build_zip.py` | Builds the installable add-on zips into `dist/`. |
| `game_deploy.py` | Puts a game bundle (`scripts/game_export.py` or the add-on's Game Export) into a test copy of the game, runs the mod's validators, or undoes it: `python -I -X utf8 tools/game_deploy.py --install <copy> --bundle <folder> [--validate]`, `--grouping <file.xml>` (into every `RM*/groupings`), `--undo`. Refuses any Steam folder. |
| `fetch_materials.py` | Downloads the material swatches (CC0 photos), checks each source's licence page states CC0 before writing anything, removes their baked lighting, resizes them and writes them with `MATERIALS.md` into `aoe3_blender_tools/materials/`. Needs numpy (the venv). `venv\Scripts\python -I tools/fetch_materials.py [name ...] [--cache <folder>]` |
| `make_texture.py` | Makes a seamless, tileable texture from a picture or from a description, and keeps it in the texture library with its licence and what it was made from (the Texture Maker panel, from the command line). `--no-ai` needs no ComfyUI and no GPU; `--list` prints the library. Needs numpy. See [docs/texture-maker.md](../docs/texture-maker.md) |
| `texture_survey.py` | Opens every texture of a game copy or a mod and measures it (palette, grain, the join, alpha, painted light), tells the mod's own from the original game's with `--reference`, and writes the texture profile (`--profile-out`, measurements only) and contact sheets (`--sheets`, outside any repository). Needs numpy. |
| `model_survey.py` | The same for every Granny file: triangles, bones, vertex layouts, sizes, texture pixels per unit, and how animations are written. Compressed files go through an external bridge into a cache (`--granny`, `--cache`). Writes the model profile. |
| `model_sheets.py` | Renders contact sheets of the surveyed models with their textures, through the importer. Needs Blender (bpy). |
| `style_check.py` | Paints the presets and says how far each texture is from the mod's own building textures; `--fit` measures each material role apart and prints the fine grain band that brings it to the mod's median (`core/materials.py`). |
| `lora_dataset.py`, `train_lora.py` | Pieces of the mod's own textures with captions, and the training of a LoRA on them with the local ComfyUI's own nodes, in resumable chunks and with a watchdog on the PC's free memory. Dataset and LoRA stay outside the repository. |
| `grouping_survey.py` | Reads every grouping (`RM*/groupings/*.xml`) of a game copy or a mod, classes each placed unit by its proto's unit types, measures how settlements are laid out round their socket, and writes `profiles/groupings.json` (numbers only). Standard library only. |
| `gallery.py` | A labelled grid of presets rendered as `scripts/generate.py` renders them: the README galleries (`--style AFRICAN`, `--style PROP --cols 4`). Needs Blender (bpy). |
| `palette_survey.py` | Measures the mean colour and local contrast of the stock building textures in `.bar` archives (the target the swatches' grain is fitted to); prints, writes nothing. Needs numpy. |
| `shape_survey.py` | Studies how buildings are built: mass, levels, parts, where the triangles go, in numbers per class that the generators are held to. |
| `spec_sheets.py` | Writes the technical sheet of every preset into `docs/specs/`: sizes, triangles, texture, collision, shape against the real models. `--proto` adds the game's data (only with `--out` outside the repository). |
| `gr2_tree.py` | Reads an uncompressed Granny model: the data tree, `--stats`, `--types` or `--shape`. |
