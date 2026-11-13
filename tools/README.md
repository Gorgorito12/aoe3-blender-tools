# Tools

Standalone Python scripts (standard library only); run them with `python -I` from the repository
root.

| Script | What it does |
|---|---|
| `bar.py` | Lists or extracts the files of the game's `.bar` archives, to get stock models, textures and anim XML as references on your own machine. `python -I tools/bar.py <archive.bar> [filter] [--extract <folder>]` |
| `xmbedit.py` | Reads and writes the game's compiled XML (`.xmb`): `check`, `to-xml`, `from-xml` (with `--compress`), and `add-unittype` to add a unit type to protos. Run it without arguments for the full usage. |
| `art_survey.py` | Surveys the art of the game or a mod (models, textures, anim files, `.bar` archives in memory) and writes `report.json` and `summary.md`; with `--proto`, joins the buildings to their models and measures them, and `--profile-out` writes the calibration profile. See the main README. The reports name the scanned files: keep them out of public repositories (the profile does not). |
| `build_zip.py` | Builds the installable add-on zips into `dist/`. |
| `game_deploy.py` | Puts a game bundle (`scripts/game_export.py` or the add-on's Game Export) into a test copy of the game, runs the mod's validators, or undoes it: `python -I -X utf8 tools/game_deploy.py --install <copy> --bundle <folder> [--validate]`, `--undo`. Refuses any Steam folder. |
| `fetch_materials.py` | Downloads the material swatches (CC0 photos), checks each source's licence page states CC0 before writing anything, removes their baked lighting, resizes them and writes them with `MATERIALS.md` into `aoe3_blender_tools/materials/`. Needs numpy (the venv). `venv\Scripts\python -I tools/fetch_materials.py [name ...] [--cache <folder>]` |
| `palette_survey.py` | Measures the mean colour and local contrast of the stock building textures in `.bar` archives (the target the swatches' grain is fitted to); prints, writes nothing. Needs numpy. |
| `shape_survey.py` | Studies how buildings are built: mass, levels, parts, where the triangles go, in numbers per class that the generators are held to. |
| `spec_sheets.py` | Writes the technical sheet of every preset into `docs/specs/`: sizes, triangles, texture, collision, shape against the real models. `--proto` adds the game's data (only with `--out` outside the repository). |
| `gr2_tree.py` | Reads an uncompressed Granny model: the data tree, `--stats`, `--types` or `--shape`. |
| `fix_bone_scale.py` | Brings the attach and impact bones of Granny models to unit scale when an export left them scaled (a root scaled by 100 for centimetres makes the game draw the `.xml` impact visuals hung on them 100 times too big). It changes only bones no mesh is bound to, whose world scale is at least `--factor` (10) off, keeping their place and direction; it patches in place (same size, CRC recomputed), checks the result, and refuses what it cannot handle. A file or a folder: `python -I tools/fix_bone_scale.py <in.gr2 or folder> [-o <out>] [--bones REGEX] [--dry-run] [-v]`; without `-o` it writes in place after a `.bak` copy. Compressed files need `--granny <bridge.exe> --granny-install <game copy>` (the external bridge of `art_survey.py`), and are then written uncompressed. See "Bone scale" in `docs/game-formats.md`. |
