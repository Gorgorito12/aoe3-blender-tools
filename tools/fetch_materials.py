# SPDX-License-Identifier: GPL-3.0-or-later
"""Downloads the material swatches (CC0 photos), prepares them and writes them with their credits
into aoe3_blender_tools/materials/. Development tool: the add-on ships the prepared PNGs and never
downloads anything.

    venv\\Scripts\\python -I tools\\fetch_materials.py [name ...] [--cache <folder>]

Every asset's licence is checked on its site before anything is written: a source whose licence
page does not state CC0 is refused. Downloads are kept in the cache folder (default:
~/.cache/aoe3bt-materials) and read without being unpacked.

Preparing a swatch: the colour map is read from the archive, its baked lighting (broad light and
shade) is divided out, it is resized to the swatch size with wrapping (no seam) and written as an
8-bit RGB PNG. The painter later scales its grain (core/materials.py).
"""
import datetime
import io
import os
import sys
import urllib.request
import zipfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import materials, paint, pngio  # noqa: E402

OUT = os.path.join(ROOT, "aoe3_blender_tools", "materials")
AGENT = "aoe3-blender-tools-dev"

SOURCES = {
    "ambientCG": {
        "licence_page": "https://docs.ambientcg.com/license/",
        "licence_text": "Creative Commons CC0 1.0 Universal",
        "archive": "https://ambientcg.com/get?file={id}_1K-PNG.zip",
        "page": "https://ambientcg.com/a/{id}",
        "member": "{id}_1K-PNG_Color.png",
    },
}

# name -> source, asset id, metres per tile (as the painter uses it), swatch size in pixels
ASSETS = {
    "plaster": {"source": "ambientCG", "id": "Plaster001", "tile_m": 2.0, "size": 256},
    "ashlar": {"source": "ambientCG", "id": "Concrete012", "tile_m": 2.5, "size": 256},
    "stone_rough": {"source": "ambientCG", "id": "Rock030", "tile_m": 2.0, "size": 256},
    "clay": {"source": "ambientCG", "id": "Clay009", "tile_m": 1.5, "size": 256},
    "timber": {"source": "ambientCG", "id": "Wood026", "tile_m": 1.0, "size": 256},
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def licence_ok(source):
    """True when the source's licence page states CC0 (fetched now)."""
    s = SOURCES[source]
    text = get(s["licence_page"]).decode("utf-8", "replace")
    return s["licence_text"].lower() in " ".join(text.split()).lower()


def fetch(name, cache):
    a = ASSETS[name]
    s = SOURCES[a["source"]]
    os.makedirs(cache, exist_ok=True)
    url = s["archive"].format(id=a["id"])
    path = os.path.join(cache, os.path.basename(url.split("file=")[-1]))
    if not os.path.exists(path):
        data = get(url)
        with open(path, "wb") as f:
            f.write(data)
    with zipfile.ZipFile(path) as z:
        return pngio.read_png(z.read(s["member"].format(id=a["id"]))), url


def prepare(img, size):
    """The colour map without its baked lighting, resized to size x size (wrapping)."""
    rgb = img[:, :, :3].astype(np.float32)
    broad = materials.resample(materials.resample(rgb, 4), rgb.shape[0])
    flat = rgb / np.maximum(broad, 1.0) * rgb.reshape(-1, 3).mean(axis=0)
    out = materials.resample(flat, size)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def write_credits(rows):
    lines = ["# Material swatches", "",
             "Small tileable photos under the painted textures (core/materials.py). Every one is",
             "CC0 1.0 Universal (public domain): no attribution is required; the sources are listed",
             "here anyway. Prepared by tools/fetch_materials.py (baked lighting removed, resized).", "",
             "| Swatch | Source | Asset | Licence | Fetched |", "|---|---|---|---|---|"]
    for name, a, page, day in rows:
        lines.append(f"| `{name}.png` | {a['source']} | [{a['id']}]({page}) | CC0 1.0 | {day} |")
    with open(os.path.join(OUT, "MATERIALS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(argv):
    cache = argv[argv.index("--cache") + 1] if "--cache" in argv else \
        os.path.join(os.path.expanduser("~"), ".cache", "aoe3bt-materials")
    names = [a for a in argv if not a.startswith("--") and a in ASSETS] or list(ASSETS)
    checked = {}
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        src = ASSETS[name]["source"]
        if src not in checked:
            checked[src] = licence_ok(src)
        if not checked[src]:
            raise SystemExit(f"{src}: its licence page does not state CC0; nothing written")
        img, url = fetch(name, cache)
        sw = prepare(img, ASSETS[name]["size"])
        paint.save_png(sw, os.path.join(OUT, name + ".png"))
        print(f"{name}.png  {sw.shape[1]} x {sw.shape[0]}  from {url}")
    day = datetime.date.today().isoformat()
    rows = []
    for name, a in ASSETS.items():
        if os.path.exists(os.path.join(OUT, name + ".png")):
            rows.append((name, a, SOURCES[a["source"]]["page"].format(id=a["id"]), day))
    write_credits(rows)


if __name__ == "__main__":
    main(sys.argv[1:])
