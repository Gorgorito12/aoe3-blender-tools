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
| `gr2_tree.py` | Reads an uncompressed Granny model: the data tree, `--stats`, `--types` or `--shape`. |
