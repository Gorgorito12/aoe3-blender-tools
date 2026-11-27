# SPDX-License-Identifier: GPL-3.0-or-later
"""Photoshop templates of the in-game interface's textures, for artists to restyle per culture, and
the way back from the filled templates to the game's textures.

    venv\\Scripts\\python -I tools/make_ui_templates.py templates --game <copy> --out <dir>
        [--variant min|normal] [--only tex1,tex2 | --all] [--size 1920x1080] [--overview]
    venv\\Scripts\\python -I tools/make_ui_templates.py build --game <copy> --in <dir> --suffix <s> --out <dir>
        [--variant min|normal] [--only tex1,tex2] [--composite]

`templates` maps every `ui\\ingame` texture the chosen interface draws into pieces
(`aoe3game/uiatlas.py`: the gadget, the rectangle, how large it shows at `--size`, when the game
shows it) and writes, per texture of 65 px or more on its longer side (`--all`: the small ones
too: 4x4 outlines, 64 px buttons, health bar bits; the README lists those left out), `<texture>.psd`
(`aoe3game/psd.py`), bottom to top. Pieces are numbered through the big textures first, so the
default set has no gaps and a run with `--all` or `--only` keeps those numbers:

1. "Original": today's art with its alpha, hidden and locked (a reference);
2. the group "Paint": one layer per piece holding the original's pixels at their place, named in
   plain words with its number and gadget ("Minimap frame (minimapPanel)" after its number);
   pieces that share pixels share a layer ("Train and hold row + Command panel (...)");
3. the group "Guides", hidden: each piece's outline, number and name, the areas no piece uses
   hatched in red, the pieces the screen enlarges or stretches unevenly marked in orange;
4. Photoshop guides at the pieces' edges.

The merged image of each file is the Paint group, so the file opens (and previews) as the used
pieces on transparency. Beside them: `reference_sheet.png` (the interface drawn by
`tools/ui_preview.py` with every piece numbered, then each texture with the same numbers, then the
list), `pieces.json` (the map), `README.txt` (for the artists: which textures each culture family
needs, how to export, the names, how to preview). `--overview` adds `<texture>.layers.png` per
file: the layer list and each layer side by side, to check a file without Photoshop.

`build` turns the filled files of `--in` (`<texture>.psd`, `<texture>.png`, a `<texture>.ddt`
recoloured elsewhere, or the same with `_<suffix>`) into `<out>\\ui\\ingame\\<texture>_<suffix>.ddt` in the original's format (size, DXT
format, alpha type, mip levels: `aoe3game/ddt.write_like`; untouched blocks keep the original's
bytes). From a PSD it composes the visible layers itself (normal blend mode, opacity, masks),
leaving out the "Original" layer and the "Guides" group whatever their visibility; `--composite`
takes the file's merged image instead (Photoshop writes it with "Maximize compatibility"). It
refuses a picture of another size and warns when a piece's transparency changes much or when paint
lies outside every piece (that paint is dropped: the original's pixels stay there). A suffix for
the Great War is the family's with `_gw` (`--suffix as_gw`).

The game copy is only read. Output must be outside it. Needs numpy.
Test: `tests/test_make_ui_templates.py`.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import bitfont  # noqa: E402
import ui_preview  # noqa: E402
from aoe3game import ddt, psd, uiatlas  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from core.pngio import encode_png, read_png  # noqa: E402

PREFIX = "ui\\ingame\\"
OUTLINE = (80, 220, 255, 255)
STRETCH = (255, 150, 40, 255)
OVERLAP = (255, 80, 220, 255)
HATCH = (255, 40, 40, 150)
LABEL_BG = (0, 0, 0, 170)
ALPHA_MEAN_LIMIT = 16          # mean change of a piece's alpha (0-255) above which build warns
ALPHA_SHARE_LIMIT = 0.05       # share of a piece's pixels whose alpha moved by 64 or more

# Wars of Liberty's culture families (its Great War technologies, request #104; the Egyptians with the
# Middle East, the mod's choice): suffix, name, civs (the names of data\civs.xml). The resource panel skin
# each civ sees is read from the copy, so a family can need more than one.
FAMILIES = (
    ("eu", "Europeans", ("Austrohungarians", "Belgians", "British", "Danish", "Dutch", "French", "Germans",
                         "Italians", "Portuguese", "Russians", "Spanish", "Swedish", "Ottomans")),
    ("an", "Anglos", ("UnitedStates", "Australians", "Canadians")),
    ("la", "Latin Americans", ("Argentineans", "Bolivians", "Brazilians", "Centralamericans", "Chileans",
                               "Colombians", "Haitians", "Mexicans", "Paraguayans", "Peruvians", "Uruguayans")),
    ("ns", "Nation states", ("Bulgarians", "Greeks", "Romanians", "Serbians")),
    ("af", "Africans", ("Ethiopians", "Zulu")),
    ("as", "Asians", ("Chinese", "Indians", "Japanese", "Koreans")),
    ("me", "Middle East", ("Afghans", "Egyptians", "Persians", "Saudis", "Uzbeks")),
    ("na", "Native Americans", ("XPIroquois", "XPSioux", "WallMapu")),
    ("po", "Polynesians", ("Maori",)),
)
# the engine's own tests before a DLL's lists extend them (docs of the UHC project: the resource
# panel chooser): native first, then Asian, else European
STOCK_NATIVE = ("XPIroquois", "XPSioux", "XPAztec", "Aztecs")
STOCK_ASIAN = ("Chinese", "Japanese", "Indians")
SKIN_WORDS = {"Eur": "European", "Asi": "Asian", "Nat": "Native"}


class TemplateError(ValueError):
    pass


# --------------------------------------------------------------------------------------------------
# The copy

class Copy:
    """The game copy read: its art (loose first, then the archives) and its in-game layouts."""

    def __init__(self, game):
        if not game or not os.path.isdir(os.path.join(game, "art")):
            raise TemplateError(f"not a game copy (no art folder): {game}")
        from fix_hitpointbar_tags import Art
        self.game = game
        self.art = Art(os.path.join(game, "art"))
        self._bytes = {}

    def texture_bytes(self, key):
        """(bytes, where) of a texture by its art key, or None."""
        if key not in self._bytes:
            hit = self.art.find(key + ".ddt")
            self._bytes[key] = (hit[0], hit[1]) if hit is not None and hit[0][:4] == ddt.MAGIC else None
        return self._bytes[key]

    def size_of(self, key):
        hit = self.texture_bytes(key)
        if hit is None:
            return None
        hd = ddt.read_header(hit[0])
        return hd.width, hd.height

    def layouts(self, variant):
        return ui_preview.scene_layouts(self.game, variant)

    def ui_map(self, variant, screen):
        return uiatlas.atlas_map(self.layouts(variant), self.size_of, variant, screen, PREFIX)

    def skins(self):
        """{civ name: "Eur" | "Asi" | "Nat"} for the families' civs, from the copy's Startup\\*.cfg
        lines `asianCivs` and `nativeCivs` (a DLL's lists) and the engine's own."""
        asian, native = {c.lower() for c in STOCK_ASIAN}, {c.lower() for c in STOCK_NATIVE}
        folder = os.path.join(self.game, "Startup")
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith(".cfg"):
                    continue
                with open(os.path.join(folder, name), "rb") as fh:
                    text = fh.read().decode("utf-8", "replace")
                for line in text.splitlines():
                    m = re.match(r"\s*(asianCivs|nativeCivs)\s+(.*)", line, re.I)
                    if m:
                        (asian if m.group(1).lower() == "asiancivs" else native).update(
                            w.lower() for w in m.group(2).split())
        out = {}
        for _s, _n, civs in FAMILIES:
            for c in civs:
                out[c] = "Nat" if c.lower() in native else ("Asi" if c.lower() in asian else "Eur")
        return out


MIN_SIDE = 65          # a texture smaller than this on its longer side is left out unless --all


def is_big(atlas):
    return max(atlas.width, atlas.height) >= MIN_SIDE


def renumber(ui_map, everything=False):
    """Numbers the pieces 1.. through the big textures first (name order), then the small ones, so
    the default set has no gaps and keeps its numbers in a run with --all or --only."""
    atlases = list(ui_map.atlases.values())
    n = 0
    for a in [x for x in atlases if is_big(x)] + [x for x in atlases if not is_big(x)]:
        for p in a.pieces:
            n += 1
            p.number = n


def left_out(ui_map):
    """The small textures a default run leaves out."""
    return [a for a in ui_map.atlases.values() if not is_big(a)]


def selected(ui_map, only, everything=True):
    """The atlases of the map, filtered by `--only` (texture names, without folder or extension);
    without it, every atlas (everything) or only the big ones."""
    atlases = list(ui_map.atlases.values())
    if not only:
        return atlases if everything else [a for a in atlases if is_big(a)]
    want = [w.strip().lower() for w in only.split(",") if w.strip()]
    found = [a for a in atlases if a.base in want or a.key in want]
    missing = sorted(set(want) - {a.base for a in found} - {a.key for a in found})
    if missing:
        raise TemplateError("not a texture of this interface: " + ", ".join(missing)
                            + " (known: " + ", ".join(a.base for a in atlases) + ")")
    return found


def piece_skins(piece):
    """The resource panel skins a piece shows with: a set of "Eur"/"Asi"/"Nat", or None (all)."""
    out = set()
    for u in piece.uses:
        skins = [c["culture"] for c in u.conds if c["kind"] == "skin"]
        if not skins:
            return None
        out.update(skins)
    return out


# --------------------------------------------------------------------------------------------------
# Drawing helpers (RGBA uint8 canvases)

def _text(img, text, x, y, colour, scale=1):
    """Text with a dark box behind it, clipped to the image (RGB or RGBA)."""
    w, h = bitfont.width(text, scale), 7 * scale
    x0, y0 = max(0, x - 1), max(0, y - 1)
    x1, y1 = min(img.shape[1], x + w + 1), min(img.shape[0], y + h + 1)
    if x1 > x0 and y1 > y0:
        region = img[y0:y1, x0:x1].astype(np.float32)
        k = LABEL_BG[3] / 255.0
        region[..., :3] = region[..., :3] * (1 - k) + np.array(LABEL_BG[:3], np.float32) * k
        if img.shape[2] == 4:
            region[..., 3] = np.maximum(region[..., 3], LABEL_BG[3])
        img[y0:y1, x0:x1] = region.astype(np.uint8)
    _draw(img, text, x, y, colour, scale)


def _draw(img, text, x, y, colour, scale=1):
    bitfont.draw(img, text, x, y, tuple(colour[:3]) + (255,), scale)


def _rect(img, x0, y0, x1, y1, colour, width=1, dashed=False):
    """An outline inside [x0, x1) x [y0, y1)."""
    H, W = img.shape[:2]
    for t in range(width):
        for (ax, ay, bx, by) in ((x0, y0 + t, x1, y0 + t + 1), (x0, y1 - 1 - t, x1, y1 - t),
                                 (x0 + t, y0, x0 + t + 1, y1), (x1 - 1 - t, y0, x1 - t, y1)):
            ax, bx = max(0, ax), min(W, bx)
            ay, by = max(0, ay), min(H, by)
            if bx <= ax or by <= ay:
                continue
            if dashed:
                yy, xx = np.mgrid[ay:by, ax:bx]
                keep = ((xx + yy) // 4) % 2 == 0
                img[ay:by, ax:bx][keep] = colour
            else:
                img[ay:by, ax:bx] = colour


def checker(h, w, size=8):
    yy, xx = np.mgrid[0:h, 0:w]
    v = np.where(((yy // size + xx // size) % 2) == 0, 205, 160).astype(np.uint8)
    return np.stack([v, v, v], axis=2)


def over(rgb, rgba):
    """RGBA over an RGB background (uint8)."""
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return (rgba[..., :3].astype(np.float32) * a + rgb.astype(np.float32) * (1 - a) + 0.5).astype(np.uint8)


def label_scale(atlas):
    return 2 if max(atlas.width, atlas.height) >= 512 else 1


def compact(items, most=2):
    items = list(items)
    return ", ".join(items[:most]) + (f" +{len(items) - most}" if len(items) > most else "")


def layer_name(atlas, cluster):
    pieces = [atlas.pieces[i] for i in cluster]
    nums = "+".join(str(p.number) for p in pieces)
    names = []
    for p in pieces:
        if p.name not in names:
            names.append(p.name)
    gadgets = []
    for p in pieces:
        for g in p.gadgets:
            if g not in gadgets:
                gadgets.append(g)
    name = f"{nums} {' + '.join(names)} ({compact(gadgets)})"
    return name if len(name) <= 200 else name[:197] + "..."


def piece_label(p, ui_map):
    st = p.stretch_range()
    marks = []
    if p.tiled:
        marks.append("tiled")
    if p.stretched and st:
        marks.append(f"x{st[0][1]:.2f} y{st[1][1]:.2f}" + (" enlarged" if p.enlarged else "")
                     + (" uneven" if p.uneven else ""))
    return marks


# --------------------------------------------------------------------------------------------------
# The template of one texture

def template_layers(atlas, rgba, ui_map):
    """(items for psd.write, Photoshop guides) of one texture."""
    h, w = atlas.height, atlas.width
    cover = atlas.coverage()
    items = [psd.Layer("Original", rgba, visible=False, locked=True)]
    paint = []
    clusters = atlas.clusters()
    for cluster in clusters:
        x0 = min(atlas.pieces[i].rect[0] for i in cluster)
        y0 = min(atlas.pieces[i].rect[1] for i in cluster)
        x1 = max(atlas.pieces[i].rect[2] for i in cluster)
        y1 = max(atlas.pieces[i].rect[3] for i in cluster)
        if x1 <= x0 or y1 <= y0:
            continue
        mask = np.zeros((y1 - y0, x1 - x0), bool)
        for i in cluster:
            r = atlas.pieces[i].rect
            mask[r[1] - y0:r[3] - y0, r[0] - x0:r[2] - x0] = True
        crop = rgba[y0:y1, x0:x1].copy()
        crop[~mask] = 0
        paint.append(psd.Layer(layer_name(atlas, cluster), crop, left=x0, top=y0))
    paint.reverse()                                     # the first piece at the top of the list
    items.append(psd.Group("Paint", paint))

    scale = label_scale(atlas)
    unused = np.zeros((h, w, 4), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    hatch = (cover == 0) & (((xx + yy) % 12) < 3)
    unused[hatch] = HATCH
    marks = np.zeros((h, w, 4), np.uint8)
    names = np.zeros((h, w, 4), np.uint8)
    overlapped = {i for pair in atlas.overlaps() for i in pair}
    for k, p in enumerate(atlas.pieces):
        x0, y0, x1, y1 = p.rect
        _rect(names, x0, y0, x1, y1, OVERLAP if k in overlapped else OUTLINE, dashed=k in overlapped)
    next_y = {}                                         # labels of pieces with the same corner go one under another
    for k, p in enumerate(atlas.pieces):
        x0, y0, x1, y1 = p.rect
        lines = [f"{p.number} {p.name}", f"({p.gadget_text()})"]
        if k in overlapped:
            others = [atlas.pieces[j].number for i, j in atlas.overlaps() if i == k] + \
                     [atlas.pieces[i].number for i, j in atlas.overlaps() if j == k]
            lines.append("shares pixels with " + ", ".join(str(n) for n in sorted(others)))
        ly = next_y.get((x0, y0), y0 + 3)
        for i, line in enumerate(lines):
            _text(names, line, x0 + 3, ly + i * (9 * scale), OVERLAP[:3] if k in overlapped else (255, 255, 255),
                  scale)
        next_y[(x0, y0)] = ly + len(lines) * 9 * scale + 2 * scale
        extra = piece_label(p, ui_map)
        if p.stretched:
            _rect(marks, x0 + 2, y0 + 2, x1 - 2, y1 - 2, STRETCH, width=2, dashed=True)
            _text(marks, "STRETCHED ON SCREEN " + " ".join(extra), x0 + 3, max(y0 + 3, y1 - 3 - 9 * scale),
                  STRETCH[:3], scale)
    items.append(psd.Group("Guides", [psd.Layer("Unused areas (hatched)", unused),
                                      psd.Layer("Stretched pieces", marks),
                                      psd.Layer("Outlines and names", names)], visible=False))
    xs, ys = set(), set()
    for p in atlas.pieces:
        xs.update((p.rect[0], p.rect[2]))
        ys.update((p.rect[1], p.rect[3]))
    guides = [(x, "v") for x in sorted(xs) if 0 < x < w] + [(y, "h") for y in sorted(ys) if 0 < y < h]
    return items, guides


def overview(f, title=""):
    """A picture of a PsdFile: the layer list (as a layers panel lists it, top first) beside every
    layer drawn on a checker, then the document with its guides and its Guides group shown."""
    rows = []

    def walk(items, depth):
        for it in reversed(items):
            rows.append((it, depth))
            if it.is_group:
                walk(it.children, depth + 1)
    walk(f.items, 0)
    thumb = 256
    sc = min(1.0, thumb / max(f.width, f.height))
    tw, th = max(1, int(round(f.width * sc))), max(1, int(round(f.height * sc)))
    panel_w = 560
    line = 16
    pics = [(it, d) for it, d in rows if not it.is_group]
    cols = 4
    grid_rows = (len(pics) + cols - 1) // cols
    big = 512
    bs = min(1.0, big / max(f.width, f.height)) if max(f.width, f.height) > big else max(1, big // max(f.width, f.height))
    bw, bh = int(round(f.width * bs)), int(round(f.height * bs))
    width = panel_w + max(cols * (tw + 12), bw + 12) + 12
    height = max(len(rows) * line + 40, 30 + grid_rows * (th + 24) + bh + 40)
    img = np.zeros((height, width, 3), np.uint8)
    img[:] = (38, 38, 38)
    img[:, :panel_w] = (50, 50, 50)
    _draw(img, title or "LAYERS", 8, 8, (230, 230, 230))
    y = 28
    for it, depth in rows:
        eye = "O" if it.visible else "-"
        kind = "[GROUP] " if it.is_group else ""
        lock = " (LOCKED)" if not it.is_group and it.locked else ""
        _draw(img, f"{eye} {'   ' * depth}{kind}{it.name}{lock}"[:88], 8, y,
                  (235, 235, 235) if it.visible else (150, 150, 150))
        y += line
    x0 = panel_w + 12
    for k, (it, _d) in enumerate(pics):
        gx, gy = x0 + (k % cols) * (tw + 12), 28 + (k // cols) * (th + 24)
        full = np.zeros((f.height, f.width, 4), np.uint8)
        h, w = it.rgba.shape[:2]
        if h and w:
            full[it.top:it.top + h, it.left:it.left + w] = it.rgba
        small = _resize(full, th, tw)
        img[gy:gy + th, gx:gx + tw] = over(checker(th, tw), small)
        _draw(img, it.name[:max(4, tw // 6)], gx, gy + th + 3, (220, 220, 220))
    # the document: the Paint group with the Guides group shown, and the Photoshop guides
    gy = 28 + grid_rows * (th + 24) + 8
    _draw(img, "THE DOCUMENT WITH THE GUIDES GROUP SHOWN (CYAN LINES: PHOTOSHOP GUIDES)", x0, gy, (230, 230, 230))
    gy += 12

    comp, _ = psd.compose(_all_visible(f.items, keep_hidden=("Original",)), f.width, f.height)
    big_img = _resize(comp, bh, bw)
    doc = over(checker(bh, bw), big_img)
    for pos, d in f.guides:
        if d == "v":
            x = int(round(pos * bw / f.width))
            if 0 <= x < bw:
                doc[:, x] = (0, 255, 255)
        else:
            yv = int(round(pos * bh / f.height))
            if 0 <= yv < bh:
                doc[yv, :] = (0, 255, 255)
    img[gy:gy + bh, x0:x0 + bw] = doc
    return img


def _all_visible(items, keep_hidden=()):
    """A copy of the tree with every item visible except those named in keep_hidden."""
    out = []
    for it in items:
        if it.is_group:
            g = psd.Group(it.name, _all_visible(it.children, keep_hidden), visible=it.name not in keep_hidden,
                          opacity=it.opacity)
            out.append(g)
        else:
            lay = psd.Layer(it.name, it.rgba, it.left, it.top, it.name not in keep_hidden, it.opacity)
            out.append(lay)
    return out


def _resize(rgba, h, w):
    """Nearest-pixel resize (an overview only)."""
    H, W = rgba.shape[:2]
    ys = np.minimum(H - 1, (np.arange(h) * H / h).astype(np.int64))
    xs = np.minimum(W - 1, (np.arange(w) * W / w).astype(np.int64))
    return rgba[ys][:, xs]


# --------------------------------------------------------------------------------------------------
# The reference sheet

def atlas_scale(atlas, many=False):
    """The scale a texture is drawn at on the sheet: large ones at 1024 px at most (512 when the
    sheet holds many), small ones enlarged up to 8 times to about 256 px."""
    m = max(atlas.width, atlas.height)
    top = 512 if many else 1024
    if m >= top:
        return top / m
    if m >= 256:
        return 1.0
    return float(max(1, min(8, 256 // m)))


def draw_atlas(atlas, rgba, s):
    """An atlas on a checker at scale s, its pieces outlined and numbered (RGB)."""
    h, w = max(1, int(round(atlas.height * s))), max(1, int(round(atlas.width * s)))
    img = over(checker(h, w), _resize(rgba, h, w))
    canvas = np.concatenate([img, np.full((h, w, 1), 255, np.uint8)], axis=2)
    overlapped = {i for pair in atlas.overlaps() for i in pair}
    unused = atlas.unused()
    hatch = _resize(np.stack([unused] * 4, axis=2).astype(np.uint8), h, w)[..., 0] > 0
    yy, xx = np.mgrid[0:h, 0:w]
    canvas[hatch & (((xx + yy) % 10) < 2)] = HATCH[:3] + (255,)
    for k, p in enumerate(atlas.pieces):
        x0, y0, x1, y1 = (int(round(v * s)) for v in p.rect)
        _rect(canvas, x0, y0, max(x0 + 1, x1), max(y0 + 1, y1), STRETCH if p.stretched else
              (OVERLAP if k in overlapped else OUTLINE), width=2 if s >= 1 else 1, dashed=k in overlapped)
    for k, p in enumerate(atlas.pieces):
        x0, y0 = int(round(p.rect[0] * s)), int(round(p.rect[1] * s))
        _text(canvas, str(p.number), x0 + 3 + (k in overlapped) * 0, y0 + 3 + 10 * sum(
            1 for j in range(k) if atlas.pieces[j].rect[:2] == p.rect[:2]), (255, 255, 255), 2)
    return canvas[..., :3]


def reference_sheet(copy, ui_map, atlases, screen, culture="Eur"):
    """The sheet (RGB): the interface with the pieces numbered, each texture numbered, the list."""
    layouts = copy.layouts(ui_map.variant)
    tex = ui_preview.Textures(copy.game)
    hud = ui_preview.render_screen([r for _s, r in layouts], screen[0], screen[1], tex, culture, ui_map.variant)
    hud = np.concatenate([hud, np.full(hud.shape[:2] + (1,), 255, np.uint8)], axis=2)
    vis = uiatlas.Visibility(culture=culture, variant=ui_map.variant)
    sx, sy = screen[0] / 1024.0, screen[1] / 768.0
    placed = {}
    for a in atlases:
        for p in a.pieces:
            shown = [u for u in p.uses if all(vis.own_shown(g) for g in u.chain + [u.node])]
            uses = shown or p.uses[:1]
            for u in uses:
                r = u.rect1024
                x0, y0, x1, y1 = (int(round(r[0] * sx)), int(round(r[1] * sy)), int(round(r[2] * sx)),
                                  int(round(r[3] * sy)))
                _rect(hud, x0, y0, x1, y1, STRETCH if p.stretched else OUTLINE, width=2, dashed=not shown)
                k = placed.get((x0, y0), 0)
                placed[(x0, y0)] = k + 1
                _text(hud, str(p.number), max(0, x0) + 4 + 26 * k, max(0, y0) + 4, (255, 255, 255), 2)
    hud = hud[..., :3]
    width = max(screen[0], 1200)
    blocks = []
    for a in atlases:
        hit = copy.texture_bytes(a.key)
        rgba = ddt.decode(hit[0], 0)
        s = atlas_scale(a, many=len(atlases) > 2)
        pic = draw_atlas(a, rgba, s)
        if pic.shape[1] > width - 16:
            k = (width - 16) / pic.shape[1]
            pic = _resize(pic, max(1, int(pic.shape[0] * k)), width - 16)
        blocks.append((a, pic))
    # rows of atlases, left to right
    rows, row, x = [], [], 8
    for a, pic in blocks:
        if row and x + pic.shape[1] + 8 > width:
            rows.append(row)
            row, x = [], 8
        row.append((a, pic, x))
        x += pic.shape[1] + 16
    if row:
        rows.append(row)
    legend = []
    for a in atlases:
        legend.append((f"{a.base}  {a.width}x{a.height}", (255, 220, 120)))
        for p in a.pieces:
            st = p.stretch_range()
            size = f"{p.size[0]}x{p.size[1]} px"
            shown = " / ".join(f"{u.screen_size[0]:.0f}x{u.screen_size[1]:.0f}" for u in
                               {(round(u.screen_size[0]), round(u.screen_size[1])): u for u in p.uses}.values())
            marks = piece_label(p, ui_map)
            legend.append((f"  {p.number:>3}  {p.name} ({p.gadget_text(3)})  AT {p.rect[0]},{p.rect[1]}  {size}"
                           f"  ON SCREEN {shown}" + (f"  {' '.join(marks)}" if marks else "")
                           + f"  SHOWN: {p.when(ui_map.moment_texts)}", (230, 230, 230)))
    line = 11
    title = (f"PIECES OF THE {'MINIMISED' if ui_map.variant == 'min' else 'NORMAL'} INTERFACE AT {screen[0]}x{screen[1]}"
             f" ({SKIN_WORDS[culture].upper()} RESOURCE PANEL). SOLID: SHOWN HERE. DASHED: SHOWN AT ANOTHER MOMENT."
             f" ORANGE: STRETCHED ON SCREEN. MAGENTA: SHARES PIXELS. RED HATCHING: NOT USED")
    heights = [16, hud.shape[0] + 8] + [max(p.shape[0] for _a, p, _x in r) + 24 for r in rows] + [len(legend) * line + 16]
    img = np.zeros((sum(heights), width, 3), np.uint8)
    img[:] = (30, 28, 26)
    _draw(img, title[:width // 6], 8, 4, (255, 255, 255))
    y = 16
    img[y:y + hud.shape[0], :hud.shape[1]] = hud
    y += hud.shape[0] + 8
    for r in rows:
        for a, pic, x in r:
            _draw(img, a.base, x, y, (255, 220, 120))
            img[y + 12:y + 12 + pic.shape[0], x:x + pic.shape[1]] = pic
        y += max(p.shape[0] for _a, p, _x in r) + 24
    y += 4
    for text, colour in legend:
        _draw(img, text[:width // 6], 8, y, colour)
        y += line
    return img


# --------------------------------------------------------------------------------------------------
# README

def readme(copy, ui_map, atlases, screen, omitted=()):
    skins = copy.skins()
    by_skin = {}
    for s, name, civs in FAMILIES:
        fam_skins = {skins[c] for c in civs}
        by_skin[s] = sorted(fam_skins, key=("Eur", "Asi", "Nat").index)
    aspect = (screen[0] / 1024.0) / (screen[1] / 768.0)
    L = []
    L.append("CULTURE UI TEMPLATES")
    L.append("=" * 20)
    L.append("")
    L.append(f"These files restyle the {'minimised' if ui_map.variant == 'min' else 'normal'} in-game interface "
             "per culture family. Each .psd is one texture of the game")
    L.append(r"(art\ui\ingame\<texture>.ddt). Paint over the pieces; the game picks your texture by the player's family.")
    L.append("")
    L.append("WHAT IS IN EACH .PSD (bottom to top)")
    L.append("  Original  today's art, hidden and locked: switch it on to compare, never paint on it.")
    L.append("  Paint     one layer per piece, holding today's art at its place. Paint on these layers")
    L.append("            (or add your own layers inside this group). Layer names: number, what it is, (the")
    L.append("            game's gadget). Pieces that share pixels share one layer.")
    L.append("  Guides    hidden: switch it on to see each piece's outline, number and name, the areas the")
    L.append("            game does not use (red hatching) and the pieces the screen stretches (orange).")
    L.append("  Photoshop guides (View > Show > Guides) run along the pieces' edges.")
    L.append("")
    L.append("RULES")
    L.append("  - Keep the canvas size. Keep each piece inside its outline: the game crops exactly there.")
    L.append("  - Transparency matters: the game draws the alpha you paint (rounded edges, holes, see-through")
    L.append("    parts). Keep the outer shape of each piece unless you mean to change it.")
    L.append("  - Hatched areas are not used by this interface: paint there is dropped. They may still hold")
    L.append("    art (parts of the normal interface, or nothing the game uses): leave them as they are. Only")
    L.append("    the minimised interface is styled, so there is no need to repaint them.")
    if abs(aspect - 1) > 0.02:
        L.append(f"  - The layout is made for a 4:3 screen: at {screen[0]}x{screen[1]} the game widens every piece")
        L.append(f"    {aspect:.2f} times against its height. Draw with the original's proportions, not the")
        L.append("    screen's: the original art is already drawn for that.")
    L.append("  - Orange pieces are enlarged or stretched unevenly on screen: avoid fine detail that would blur,")
    L.append("    and patterns that would look distorted. The reference sheet lists each piece's screen size.")
    L.append("")
    L.append("FILE NAMES")
    L.append("  <texture>_<suffix>.ddt for a family, <texture>_<suffix>_gw.ddt for its Great War look.")
    L.append("  Suffixes: " + ", ".join(f"{s} {n}" for s, n, _c in FAMILIES) + ".")
    L.append("  A family without its own texture shows today's art; a family without a _gw texture keeps its")
    L.append("  own look in the Great War.")
    L.append("")
    L.append("HOW TO HAND THEM IN")
    L.append("  Either save the .psd (keep the Paint group; Original and Guides are ignored), or export a")
    L.append("  flattened PNG with transparency (File > Export > Export As > PNG, with Original and Guides")
    L.append("  hidden). Name it <texture>_<suffix>.psd or .png (for example ingame_ui_small_01_ypack_as.png).")
    L.append("  Blend modes other than Normal, layer styles and clipping masks are not read from a .psd:")
    L.append("  merge them into a normal layer, or hand in the exported PNG.")
    L.append("")
    L.append("WHICH TEXTURES EACH FAMILY NEEDS")
    L.append("  The resource panel has three looks (European, Asian, Native); the game shows each civ one of")
    L.append("  them (read from this copy). Every family restyles the shared pieces, and only the resource")
    L.append("  panel look its civs see.")
    shared = [a for a in atlases if any(piece_skins(p) is None for p in a.pieces)]
    L.append("  Shared by every family (pieces of a resource panel look excepted):")
    for k in range(0, len(shared), 3):
        L.append("    " + ", ".join(x.base for x in shared[k:k + 3]))
    for skin in ("Eur", "Asi", "Nat"):
        own = []
        for a in atlases:
            nums = [p.number for p in a.pieces if piece_skins(p) is not None and skin in piece_skins(p)]
            if nums:
                own.append(f"{a.base} ({'piece' if len(nums) == 1 else 'pieces'} {_ranges(nums)})"
                           if len(nums) < len(a.pieces) else a.base)
        if own:
            L.append(f"  {SKIN_WORDS[skin]} resource panel: " + ", ".join(own))
    for s_, name, civs in FAMILIES:
        L.append(f"  {s_}  {name} ({', '.join(civs)}): the shared ones + the "
                 f"{' and '.join(SKIN_WORDS[k] for k in by_skin[s_])} resource panel")
    L.append("")
    if omitted:
        L.append("LEFT OUT (small textures, under 65 px on their longer side; they keep today's look)")
        for k in range(0, len(omitted), 3):
            L.append("  " + ", ".join(f"{x.base} {x.width}x{x.height}" for x in omitted[k:k + 3]))
        L.append("  (tools/make_ui_templates.py templates --all makes templates for them too.)")
        L.append("")
    L.append("TEXTURES AND PIECES")
    for a in atlases:
        L.append(f"  {a.base}.psd  {a.width}x{a.height}")
        for p in a.pieces:
            marks = piece_label(p, ui_map)
            L.append(f"    {p.number:>3} {p.name} ({p.gadget_text(3)}): {p.size[0]}x{p.size[1]} px at "
                     f"{p.rect[0]},{p.rect[1]}" + (f", {' '.join(marks)}" if marks else "")
                     + f"; shown: {p.when(ui_map.moment_texts)}")
    L.append("")
    L.append("PREVIEW WITHOUT THE GAME (for the person with aoe3-blender-tools)")
    L.append("  python -I tools/make_ui_templates.py build --game <copy> --in <filled files> --suffix as --out <dir>")
    L.append("  python -I tools/ui_preview.py --game <copy> --scene min --size 1920x1080 --culture Asi \\")
    L.append("      --override <dir> --suffix as --out preview.png")
    L.append("  (--culture: the resource panel look of the family, Eur, Asi or Nat.)")
    L.append("")
    L.append("reference_sheet.png shows the interface with every piece numbered and each texture with the same")
    L.append("numbers. pieces.json is the same map for tools.")
    return "\r\n".join(L) + "\r\n"


def _ranges(nums):
    nums = sorted(nums)
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        if n is not None:
            start = prev = n
    return ", ".join(out)


# --------------------------------------------------------------------------------------------------
# Commands

def outside_copy(out, game):
    refuse_steam(out)
    a = os.path.normcase(os.path.abspath(out))
    g = os.path.normcase(os.path.abspath(game))
    if a == g or a.startswith(g.rstrip("\\/") + os.sep):
        raise RefusedPath("the output must be outside the game copy")


def parse_size(text):
    m = re.fullmatch(r"\s*(\d+)\s*[x,]\s*(\d+)\s*", text or "")
    if not m:
        raise TemplateError(f"--size takes WIDTHxHEIGHT (got {text!r})")
    return int(m.group(1)), int(m.group(2))


def cmd_templates(a):
    screen = parse_size(a.size)
    outside_copy(a.out, a.game)
    copy = Copy(a.game)
    m = copy.ui_map(a.variant, screen)
    renumber(m)
    atlases = selected(m, a.only, a.all)
    omitted = [] if a.all or a.only else left_out(m)
    os.makedirs(a.out, exist_ok=True)
    total = 0
    for atlas in atlases:
        data, where = copy.texture_bytes(atlas.key)
        rgba = ddt.decode(data, 0)
        items, guides = template_layers(atlas, rgba, m)
        out = psd.write(atlas.width, atlas.height, items, guides)
        path = os.path.join(a.out, atlas.base + ".psd")
        with open(path, "wb") as fh:
            fh.write(out)
        total += len(out)
        layers = sum(1 for it in items[1].children)
        print(f"{path}: {atlas.width}x{atlas.height}, {len(atlas.pieces)} pieces in {layers} layers, "
              f"{len(guides)} guides, {len(out) / 1048576:.2f} MB (from {where})")
        if a.overview:
            pic = overview(psd.read(out), f"{atlas.base}.psd")
            with open(os.path.join(a.out, atlas.base + ".layers.png"), "wb") as fh:
                fh.write(encode_png(pic))
    sheet = reference_sheet(copy, m, atlases, screen)
    with open(os.path.join(a.out, "reference_sheet.png"), "wb") as fh:
        fh.write(encode_png(sheet))
    doc = m.public()
    keep = {x.key for x in atlases}
    doc["atlases"] = [x for x in doc["atlases"] if x["atlas"] in keep]
    with open(os.path.join(a.out, "pieces.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    with open(os.path.join(a.out, "README.txt"), "w", encoding="utf-8", newline="") as fh:
        fh.write(readme(copy, m, atlases, screen, omitted))
    print(f"{len(atlases)} templates, {total / 1048576:.2f} MB; reference_sheet.png, pieces.json, README.txt"
          + (f"; left out (small): {', '.join(x.base for x in omitted)}" if omitted else "")
          + (f"; textures not found: {', '.join(sorted(m.missing))}" if m.missing else ""))
    return 0


SUFFIX = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")


def find_input(folder, base, suffix):
    """The filled file for a texture in `folder`: <base>_<suffix> first, then <base>; .psd, .png or
    .ddt (a texture recoloured or edited elsewhere)."""
    names = {n.lower(): n for n in os.listdir(folder)}
    for stem in (f"{base}_{suffix}", base):
        for ext in (".psd", ".png", ".ddt"):
            if (stem + ext).lower() in names:
                return os.path.join(folder, names[(stem + ext).lower()])
    return None


def picture_of(path, use_composite=False):
    """(H x W x 4 uint8, [notes]) of a filled template."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] == ddt.MAGIC:
        return ddt.decode(data, 0), []
    if data[:4] == psd.SIGNATURE:
        f = psd.read(data)
        if use_composite or not f.items:
            if f.composite is None:
                raise TemplateError(f"{path}: no merged image in the file")
            return f.composite, ([] if f.items else ["no layers: the merged image is used"])

        def skip(item, path_):
            return (not path_ and item.name == "Original" and not item.is_group) or \
                   item.name == "Guides" or "Guides" in path_
        img, notes = psd.compose(f.items, f.width, f.height, skip=skip)
        return img, notes
    rgba = read_png(data)
    if rgba.ndim == 2:
        rgba = rgba[:, :, None]
    if rgba.shape[2] in (1, 2):
        grey = rgba[:, :, :1]
        alpha = rgba[:, :, 1:2] if rgba.shape[2] == 2 else np.full_like(grey, 255)
        rgba = np.concatenate([grey, grey, grey, alpha], axis=-1)
    elif rgba.shape[2] == 3:
        rgba = np.concatenate([rgba, np.full(rgba.shape[:2] + (1,), 255, np.uint8)], axis=-1)
    return rgba.astype(np.uint8), []


def check_and_merge(atlas, original, painted):
    """(final RGBA, [warnings]): the painted pieces over the original (outside them the original
    stays), with the checks of a build."""
    warnings = []
    if painted.shape[:2] != original.shape[:2]:
        raise TemplateError(f"{atlas.base}: the picture is {painted.shape[1]}x{painted.shape[0]}, "
                            f"the texture {original.shape[1]}x{original.shape[0]}")
    used = ~atlas.unused()
    outside = (~used) & (painted[..., 3] > 0) & (painted != original).any(-1)
    if outside.any():
        ys, xs = np.nonzero(outside)
        warnings.append(f"{atlas.base}: {int(outside.sum())} painted pixels outside every piece "
                        f"(x {xs.min()}-{xs.max()}, y {ys.min()}-{ys.max()}): dropped, the original's stay")
    final = original.copy()
    # a pixel transparent in both keeps the original's colour: a layer (and Photoshop) does not
    # keep the colour under zero alpha, and the texture's filtering still reads it at the edges
    take = used & ~((painted[..., 3] == 0) & (original[..., 3] == 0))
    final[take] = painted[take]
    for p in atlas.pieces:
        x0, y0, x1, y1 = p.rect
        a0 = original[y0:y1, x0:x1, 3].astype(np.int16)
        a1 = final[y0:y1, x0:x1, 3].astype(np.int16)
        if a0.size == 0:
            continue
        d = np.abs(a1 - a0)
        mean, share = float(d.mean()), float((d >= 64).mean())
        if mean > ALPHA_MEAN_LIMIT or share > ALPHA_SHARE_LIMIT:
            warnings.append(f"{atlas.base}: piece {p.number} {p.name}: its transparency changed (mean "
                            f"{mean:.0f}/255, {share:.0%} of its pixels by 64 or more)")
    return final, warnings


def cmd_build(a):
    screen = parse_size(a.size)
    if not SUFFIX.match(a.suffix or ""):
        raise TemplateError("--suffix: lower-case letters and digits, parts joined by _ (eu, as, as_gw)")
    outside_copy(a.out, a.game)
    if not os.path.isdir(a.input):
        raise TemplateError(f"no such folder: {a.input}")
    copy = Copy(a.game)
    m = copy.ui_map(a.variant, screen)
    renumber(m)
    atlases = selected(m, a.only)
    written, warnings = 0, []
    for atlas in atlases:
        src = find_input(a.input, atlas.base, a.suffix)
        if src is None:
            continue
        data, _where = copy.texture_bytes(atlas.key)
        original = ddt.decode(data, 0)
        painted, notes = picture_of(src, a.composite)
        warnings += [f"{os.path.basename(src)}: {n}" for n in notes]
        final, warn = check_and_merge(atlas, original, painted)
        given = None
        if src.lower().endswith(".ddt"):
            with open(src, "rb") as fh:
                given = fh.read()
            if given[4:16] != data[4:16]:
                given = None
        if given is not None:
            # a whole texture already in the original's format (recolour_textures.py keeps every header
            # byte): kept as it is, unused areas included; only the transparency checks apply
            warnings += [w for w in warn if "outside every piece" not in w]
            out, changed = given, -2
        else:
            warnings += warn
            out, changed = ddt.write_like(data, final)
        rel = atlas.key + "_" + a.suffix + ".ddt"
        path = os.path.join(a.out, *rel.split("\\"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(out)
        written += 1
        hd = ddt.read_header(out)
        what = "unchanged" if changed == 0 else (f"{changed} blocks encoded" if changed > 0 else
                                                 "copied as given" if changed == -2 else "written whole")
        print(f"{path}: {hd.describe()}, {what} (from {os.path.basename(src)})")
    for w in warnings:
        print("WARNING: " + w)
    if not written:
        raise TemplateError(f"no filled file found in {a.input} (names: <texture>.psd|.png or "
                            f"<texture>_{a.suffix}.psd|.png)")
    print(f"{written} textures written, {len(warnings)} warnings")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("templates", help="write the Photoshop templates, the reference sheet and the README")
    t.add_argument("--game", required=True, help="a game copy (read only)")
    t.add_argument("--out", required=True, help="the folder to write (outside the copy)")
    t.add_argument("--variant", choices=("min", "normal"), default="min", help="the interface (default min)")
    t.add_argument("--only", help="texture names, comma-separated (default: every ui\\ingame texture it draws "
                                  "of 65 px or more on its longer side)")
    t.add_argument("--all", action="store_true", help="the small textures too (4x4 outlines, small buttons, ...)")
    t.add_argument("--size", default="1920x1080", help="the screen the on-screen sizes are given for")
    t.add_argument("--overview", action="store_true", help="also a picture of each file's layers")
    b = sub.add_parser("build", help="the filled templates to the game's textures")
    b.add_argument("--game", required=True, help="the game copy the templates came from (read only)")
    b.add_argument("--in", dest="input", required=True, help="the folder of filled .psd or .png files")
    b.add_argument("--suffix", required=True, help="the family's suffix (eu, as, as_gw, ...)")
    b.add_argument("--out", required=True, help="the folder to write ui\\ingame\\<texture>_<suffix>.ddt into")
    b.add_argument("--variant", choices=("min", "normal"), default="min")
    b.add_argument("--only", help="texture names, comma-separated")
    b.add_argument("--size", default="1920x1080", help=argparse.SUPPRESS)
    b.add_argument("--composite", action="store_true", help="use a .psd's merged image, not its layers")
    a = ap.parse_args(argv)
    try:
        return cmd_templates(a) if a.command == "templates" else cmd_build(a)
    except (TemplateError, RefusedPath, ddt.DdtError, psd.PsdError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
