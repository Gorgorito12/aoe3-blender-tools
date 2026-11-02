# Tools

Standalone Python scripts (standard library only); run them with `python -I` from the repository
root.

| Script | What it does |
|---|---|
| `bar.py` | Lists or extracts the files of the game's `.bar` archives, to get stock models, textures and anim XML as references on your own machine. `python -I tools/bar.py <archive.bar> [filter] [--extract <folder>]` |
| `xmbedit.py` | Reads and writes the game's compiled XML (`.xmb`): `check`, `to-xml`, `from-xml` (with `--compress`), and `add-unittype` to add a unit type to protos. Run it without arguments for the full usage. |
| `art_survey.py` | Surveys the art of the game or a mod (models, textures, anim files, `.bar` archives in memory) and writes `report.json` and `summary.md`. See the main README. The reports name the scanned files: keep them out of public repositories. |
| `build_zip.py` | Builds the installable add-on zips into `dist/`. |

Extracted game files are for reference on your machine only: never commit them.
