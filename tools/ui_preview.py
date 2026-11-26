# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws a game UI layout file (a `ui*.xml`, or its compiled `.xmb`) as a PNG, to review where its
gadgets sit without opening the game.

    python -I tools/ui_preview.py <layout.xml|.xmb> --out <preview.png>
        [--scale 2] [--region auto|x1,y1,x2,y2] [--hide REGEX] [--mark REGEX] [--title TEXT]
        [--strip PREFIX] [--text] [--vline X[,X...]]

Each gadget with a `size1024` rectangle (the game's 1024 x 768 layout space) is drawn as a box:
its outline coloured by how deep it is nested, a number in its top left corner, and the legend on
the right lists every gadget by number, indented by nesting, with its type and, with `--text`,
the text it holds (a `formatText` gadget's `{...}` placeholders, for instance). A gadget that lies
outside its parent's rectangle is drawn in red and flagged `OUT` in the legend: the game still
draws it, but it shows and hides with that parent. `hidden` gadgets are drawn dashed.

- `--region`: the part of the 1024 x 768 space to draw; `auto` (default) fits every box.
- `--hide REGEX`: leave out the gadgets whose name matches (e.g. `StackButton`); their children
  too.
- `--mark REGEX`: draw the matching gadgets filled in yellow (new rows of a proposal).
- `--strip PREFIX`: drop that prefix from the names in the legend (default: the root's name
  followed by `-`).
- `--vline X[,X...]`: draw a dashed vertical guide at each x of the layout space (a centre line,
  to check that a layout is symmetric), with its x written at the top.

The parser is lenient, as the game's is: comments, attribute names in any case, spaces around
`=`, and stray closing tags are accepted. Text is drawn with the 5 x 7 bitmap font (`bitfont.py`),
upper case. Standard library and numpy.

With textures: the screen as the game draws its art, to judge a style without the game.

    python -I tools/ui_preview.py [<layout> ...] --out <screen.png> --game <copy> [--scene normal|min]
        [--size 1920x1080] [--culture Eur|Asi|Nat] [--override <folder>]... [--suffix S]
        [--moment ID=on|off]... [--boxes] [--show-hidden]

`--game` (or `--override` alone) switches to this mode. Each gadget's `size1024` rectangle is scaled
to the screen (x * width / 1024, y * height / 768), then drawn as the studio's interface screen draws
it (`studio/web/js/hud_render.js`; its assumptions are to verify in game): its `backgroundColor`
(and `backgroundAlpha`), its `background` texture (or its first `stateEntry`'s) cropped by
`textureCoords` or tiled (`tileBackground`, at the texture's own size times width / 1024), a
`progressBar`'s background and mask, then its `foreground`; children over their parent, siblings
and the top-level gadgets of every file by `z`, then in file order. Text, and what the engine draws
into the gadgets (the minimap, portraits, the buttons it fills), is not drawn.

- `--scene normal|min`: the layouts the game loads for its in-game screen, from the copy (the main
  screen and the panels beside it, the normal or the minimised files, found as `studio/hud.py`
  finds them); layout files named on the line are drawn over them.
- `--culture`: which of the resource panel's skins shows (gadgets named `...Eur|Asi|Nat` then
  `Max|Min`: Max for `normal`, Min for `min`); the engine picks it by the player's civ.
- `--override <folder>` (repeatable): textures looked up before the copy's, by their art path
  (`ui\\ingame\\x` is `<folder>\\ui\\ingame\\x.png` or `.ddt`).
- `--suffix S`: for each texture `x`, `x_S` is used where it exists (in an override folder or the
  copy), else `x`: a culture's own art beside the shared one.
- `--boxes`: the gadget outlines over the picture; `--show-hidden`: draw `hidden` gadgets too.
- `--moment ID=on|off` (repeatable): the gadgets the engine keeps hidden until a moment of the game
  (`selected`: a unit selected, `stats`: its tab, `clock`, `ageup`, ...) follow
  `aoe3game/uidata/hud_scene.json`'s defaults unless switched here.

The textures it drew, where each came from, and the ones it did not find are printed.
"""
import argparse
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
import bitfont  # noqa: E402
from core.pngio import encode_png  # noqa: E402

DEPTH_COLOURS = [(90, 170, 255), (110, 220, 120), (240, 170, 60), (200, 120, 240), (90, 220, 220),
                 (240, 110, 160)]
OUT_COLOUR = (255, 60, 60)
MARK_COLOUR = (255, 230, 60)
GUIDE_COLOUR = (255, 80, 220)
BACKGROUND = (28, 26, 24)
GRID = (44, 41, 38)
LEGEND_BG = (18, 17, 16)
TEXT = (225, 225, 225)
DIM = (140, 140, 140)

_TOKEN = re.compile(
    r"<!--.*?-->|<\?.*?\?>|<!\[CDATA\[(?P<cdata>.*?)\]\]>"
    r"|<(?P<close>/)?(?P<tag>[A-Za-z_][\w.:-]*)(?P<attrs>(?:\s+[^\s=/>]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'))?)*)\s*(?P<empty>/)?>",
    re.S)
_ATTR = re.compile(r"([^\s=/>]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'))?")


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children = []
        self.text = ""

    @property
    def name(self):
        return self.attrs.get("name", "")

    @property
    def rect(self):
        v = self.attrs.get("size1024")
        if not v:
            return None
        try:
            x1, y1, x2, y2 = (float(t) for t in v.split()[:4])
        except ValueError:
            return None
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def parse(text):
    """The root Node of a layout's text. Unmatched closing tags are ignored; elements left open
    at the end are closed."""
    root = Node("#document", {}, None)
    stack = [root]
    pos = 0
    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            stack[-1].text += text[pos:m.start()]
        pos = m.end()
        if m.group("cdata") is not None:
            stack[-1].text += m.group("cdata")
            continue
        tag = m.group("tag")
        if not tag:
            continue
        tag = tag.lower()
        if m.group("close"):
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag:
                    del stack[i:]
                    break
            continue
        attrs = {}
        for a in _ATTR.finditer(m.group("attrs") or ""):
            val = a.group(2) if a.group(2) is not None else (a.group(3) or "")
            attrs[a.group(1).lower()] = val
        node = Node(tag, attrs, stack[-1])
        stack[-1].children.append(node)
        if not m.group("empty"):
            stack.append(node)
    if pos < len(text):
        stack[-1].text += text[pos:]
    return root


def load(path):
    """The root Node of a layout file: text XML, or a compiled .xmb through xmbedit.py."""
    with open(path, "rb") as fh:
        return load_bytes(fh.read())


def load_bytes(raw):
    """The root Node of a layout's bytes: text XML, or a compiled .xmb."""
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        import xmbedit
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        raw = xmbedit.to_xml(elems, attrs, root)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if raw.startswith(bom):
            return parse(raw[len(bom):].decode(enc, "replace"))
    return parse(raw.decode("utf-8", "replace"))


def gadgets(root, hide=None):
    """[(node, depth, index)] of every gadget in document order; depth 0 = a top-level gadget."""
    out = []

    def walk(node, depth):
        for c in node.children:
            if c.tag != "gadget":
                if c.tag == "layout" or c.tag.startswith("#"):
                    walk(c, depth)                 # the document's <layout> holds the gadgets
                continue
            if hide and hide.search(c.name):
                continue
            out.append((c, depth, len(out) + 1))
            walk(c, depth + 1)
    walk(root, 0)
    return out


def gadget_parent(node):
    p = node.parent
    while p is not None and p.tag != "gadget":
        p = p.parent
    return p


TOLERANCE = 4.0     # layout units a child may overhang its parent before it is flagged (stock does)


def outside_parent(node, tolerance=TOLERANCE):
    """True when the gadget's rectangle overhangs its parent gadget's by more than `tolerance`."""
    p = gadget_parent(node)
    if p is None or node.rect is None or p.rect is None:
        return False
    x1, y1, x2, y2 = node.rect
    px1, py1, px2, py2 = p.rect
    t = tolerance
    return x1 < px1 - t or y1 < py1 - t or x2 > px2 + t or y2 > py2 + t


def _hline(img, x1, x2, y, colour, dashed=False):
    if 0 <= y < img.shape[0]:
        x1, x2 = max(0, x1), min(img.shape[1] - 1, x2)
        for x in range(x1, x2 + 1):
            if not dashed or (x // 4) % 2 == 0:
                img[y, x] = colour


def _vline(img, x, y1, y2, colour, dashed=False):
    if 0 <= x < img.shape[1]:
        y1, y2 = max(0, y1), min(img.shape[0] - 1, y2)
        for y in range(y1, y2 + 1):
            if not dashed or (y // 4) % 2 == 0:
                img[y, x] = colour


def box(img, x1, y1, x2, y2, colour, dashed=False, fill=None, alpha=0.18):
    if fill is not None:
        ya, yb = max(0, y1), min(img.shape[0], y2 + 1)
        xa, xb = max(0, x1), min(img.shape[1], x2 + 1)
        if ya < yb and xa < xb:
            region = img[ya:yb, xa:xb].astype(np.float32)
            img[ya:yb, xa:xb] = (region * (1 - alpha) + np.array(fill, np.float32) * alpha).astype(np.uint8)
    for t in range(2):
        _hline(img, x1, x2, y1 + t, colour, dashed)
        _hline(img, x1, x2, y2 - t, colour, dashed)
        _vline(img, x1 + t, y1, y2, colour, dashed)
        _vline(img, x2 - t, y1, y2, colour, dashed)


def render(root, scale=2.0, region="auto", hide=None, mark=None, title=None, strip=None,
           show_text=False, vlines=()):
    """H x W x 3 uint8 picture of the layout and its legend; `vlines`: x of dashed vertical guides."""
    items = gadgets(root, hide)
    rects = [n.rect for n, _, _ in items if n.rect is not None]
    if region == "auto" or region is None:
        if rects:
            rx1 = min(r[0] for r in rects) - 8
            ry1 = min(r[1] for r in rects) - 8
            rx2 = max(r[2] for r in rects) + 8
            ry2 = max(r[3] for r in rects) + 8
        else:
            rx1, ry1, rx2, ry2 = 0, 0, 1024, 768
    else:
        rx1, ry1, rx2, ry2 = (float(v) for v in region)
    if strip is None:
        tops = [n.name for n, d, _ in items if d == 0 and n.name]
        strip = (tops[0] + "-") if tops else ""

    pw = int(round((rx2 - rx1) * scale))
    ph = int(round((ry2 - ry1) * scale))
    line_h = 11
    legend_lines = []
    for node, depth, idx in items:
        label = node.name[len(strip):] if strip and node.name.startswith(strip) else node.name
        typ = node.attrs.get("type", "")
        flags = []
        if node.rect is None:
            flags.append("NO SIZE")
        if outside_parent(node):
            flags.append("OUT")
        if "hidden" in node.attrs:
            flags.append("HIDDEN")
        text = " ".join(node.text.split())
        line = f"{idx:>3} {'  ' * depth}{label or '(no name)'} [{typ}]"
        if flags:
            line += " " + " ".join(flags)
        legend_lines.append((line, node, depth, idx, flags))
        if show_text and text:
            legend_lines.append((f"      {'  ' * depth}= {text[:70]}", None, depth, idx, []))
    lw = max([bitfont.width(t) for t, *_ in legend_lines] + [200]) + 16
    head = 16 if title else 0
    h = max(ph, len(legend_lines) * line_h + 8) + head
    img = np.zeros((h, pw + lw, 3), np.uint8)
    img[:] = BACKGROUND
    img[:, pw:] = LEGEND_BG
    # a 64-unit grid of the layout space
    for gx in range(0, 1025, 64):
        x = int(round((gx - rx1) * scale))
        if 0 <= x < pw:
            _vline(img, x, head, head + ph - 1, GRID)
    for gy in range(0, 769, 64):
        y = int(round((gy - ry1) * scale)) + head
        if head <= y < head + ph:
            _hline(img, 0, pw - 1, y, GRID)
    if title:
        bitfont.draw(img, title, 4, 4, TEXT)

    def to_px(r):
        return (int(round((r[0] - rx1) * scale)), int(round((r[1] - ry1) * scale)) + head,
                int(round((r[2] - rx1) * scale)) - 1, int(round((r[3] - ry1) * scale)) + head - 1)

    # parents first, so children are drawn on top
    for node, depth, idx in items:
        r = node.rect
        if r is None:
            continue
        x1, y1, x2, y2 = to_px(r)
        out = outside_parent(node)
        marked = bool(mark and mark.search(node.name))
        colour = OUT_COLOUR if out else (MARK_COLOUR if marked else DEPTH_COLOURS[depth % len(DEPTH_COLOURS)])
        fill = MARK_COLOUR if marked else colour
        box(img, x1, y1, x2, y2, colour, dashed="hidden" in node.attrs, fill=fill,
            alpha=0.35 if marked else 0.10)
    for node, depth, idx in items:
        r = node.rect
        if r is None:
            continue
        x1, y1, _, _ = to_px(r)
        bitfont.draw(img, str(idx), x1 + 3, y1 + 3, TEXT, shadow=(0, 0, 0))
    for i, gx in enumerate(vlines):
        x = int(round((gx - rx1) * scale))
        if 0 <= x < pw:
            _vline(img, x, head, head + ph - 1, GUIDE_COLOUR, dashed=True)
            label = f"{gx:g}"
            # one label per text line from the bottom up, so close guides keep readable labels
            bitfont.draw(img, label, min(x + 3, pw - bitfont.width(label) - 2), head + ph - 10 - 10 * i,
                         GUIDE_COLOUR, shadow=(0, 0, 0))
    y = head + 4
    for line, node, depth, idx, flags in legend_lines:
        colour = TEXT if node is not None else DIM
        if "OUT" in flags:
            colour = OUT_COLOUR
        elif node is not None and mark and mark.search(node.name):
            colour = MARK_COLOUR
        elif node is not None:
            colour = DEPTH_COLOURS[depth % len(DEPTH_COLOURS)]
        bitfont.draw(img, line, pw + 8, y, colour)
        y += line_h
    return img


# --------------------------------------------------------------------------------------------------
# The screen with its textures

# the visibility rules and the art path keys are shared with aoe3game/uiatlas.py (the pieces of the
# interface's textures), so the preview and the piece map agree
from aoe3game.uiatlas import SCENE_RULES, SKIN, Visibility, art_key, scene_rules  # noqa: E402,F401


class Textures:
    """A layout's texture paths to pictures: each override folder first, then the copy's art (its
    loose files, then its archives); with a suffix, `<path>_<suffix>` before `<path>`."""

    def __init__(self, game=None, overrides=(), suffix=None):
        self.art = None
        if game:
            from fix_hitpointbar_tags import Art
            self.art = Art(os.path.join(game, "art"))
        self.overrides = []
        for folder in overrides:
            index = {}
            for top, _dirs, files in os.walk(folder):
                for name in sorted(files):
                    if name.lower().endswith((".ddt", ".png")):
                        full = os.path.join(top, name)
                        index.setdefault(art_key(os.path.relpath(full, folder)), []).append(full)
            self.overrides.append(index)
        self.suffix = suffix
        self.cache, self.used, self.missing = {}, {}, set()

    @staticmethod
    def decode(data):
        """H x W x 4 float RGBA (0..1) of a .ddt's top level or a PNG."""
        from aoe3game import ddt
        if data[:4] == ddt.MAGIC:
            rgba = ddt.decode(data, 0)
        else:
            from core.pngio import read_png
            rgba = read_png(data)
            if rgba.ndim == 2:
                rgba = rgba[:, :, None]
            if rgba.shape[2] in (1, 2):
                grey = rgba[:, :, :1]
                alpha = rgba[:, :, 1:2] if rgba.shape[2] == 2 else np.full_like(grey, 255)
                rgba = np.concatenate([grey, grey, grey, alpha], axis=-1)
            elif rgba.shape[2] == 3:
                rgba = np.concatenate([rgba, np.full(rgba.shape[:2] + (1,), 255, np.uint8)], axis=-1)
        return rgba.astype(np.float32) / 255.0

    def _one(self, key):
        for index in self.overrides:
            files = index.get(key)
            if files:
                first = sorted(files, key=lambda f: not f.lower().endswith(".png"))[0]   # a PNG first
                with open(first, "rb") as fh:
                    return self.decode(fh.read()), first
        if self.art is not None:
            hit = self.art.find(key + ".ddt")
            if hit is not None:
                return self.decode(hit[0]), hit[1]
        return None

    def get(self, path):
        """H x W x 4 float RGBA (0..1) of a texture path, or None when it is not found."""
        key = art_key(path)
        if not key:
            return None
        if key not in self.cache:
            hit = self._one(f"{key}_{self.suffix.lower()}") if self.suffix else None
            hit = hit or self._one(key)
            self.cache[key] = hit
            if hit is None:
                self.missing.add(key)
            else:
                self.used[key] = hit[1]
        hit = self.cache[key]
        return None if hit is None else hit[0]


def scene_layouts(game, variant="normal"):
    """[(stem, root Node)] of the in-game screen's layouts in the copy, found as studio/hud.py finds
    them: the main screen, then the panels (their minimised files for `min`, else the normal ones)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from studio import hud
    g = hud.Game(game)
    out = []
    for stem in [hud.MAIN] + [p + ("min" if variant == "min" else "") for p in hud.PANELS]:
        hit = g.layout(stem)
        if hit is None and variant == "min":
            stem = stem[:-3]
            hit = g.layout(stem)
        if hit is not None:
            out.append((stem, load_bytes(hit[0])))
    return out


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _colour(v, default):
    try:
        rgb = [float(t) for t in re.split(r"[\s,]+", str(v or "").strip())[:3]]
    except ValueError:
        return default
    return rgb if len(rgb) == 3 else default


def blit(canvas, img, uv, x, y, w, h, tile="", scale=1.0):
    """Draws img (float RGBA) over canvas (float RGB) in the screen rectangle x, y, w, h: its texture
    rectangle uv = (u1, v1, u2, v2) stretched to it (bilinear), or repeated at its own texel size
    times `scale` along the axes in `tile` ("x", "y", "xy")."""
    H, W = canvas.shape[:2]
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(W, int(round(x + w))), min(H, int(round(y + h)))
    if x1 <= x0 or y1 <= y0 or w <= 0 or h <= 0:
        return
    th, tw = img.shape[:2]
    px = np.arange(x0, x1, dtype=np.float64) + 0.5
    py = np.arange(y0, y1, dtype=np.float64) + 0.5
    u1, v1, u2, v2 = uv
    k = scale if scale > 0 else 1.0
    sx = (px - x) / k if "x" in tile else (u1 + (px - x) / w * (u2 - u1)) * tw
    sy = (py - y) / k if "y" in tile else (v1 + (py - y) / h * (v2 - v1)) * th
    sx, sy = sx - 0.5, sy - 0.5
    ix, iy = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    fx = (sx - ix)[None, :, None].astype(np.float32)
    fy = (sy - iy)[:, None, None].astype(np.float32)
    xa, xb = (ix % tw, (ix + 1) % tw) if "x" in tile else (np.clip(ix, 0, tw - 1), np.clip(ix + 1, 0, tw - 1))
    ya, yb = (iy % th, (iy + 1) % th) if "y" in tile else (np.clip(iy, 0, th - 1), np.clip(iy + 1, 0, th - 1))
    top = img[ya][:, xa] * (1 - fx) + img[ya][:, xb] * fx
    bottom = img[yb][:, xa] * (1 - fx) + img[yb][:, xb] * fx
    px_ = top * (1 - fy) + bottom * fy
    a = px_[:, :, 3:4]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + px_[:, :, :3] * a


def render_screen(roots, width=1024, height=768, textures=None, culture="Eur", variant="normal",
                  show_hidden=False, hide=None, boxes=False, rules=None, backdrop=(0, 0, 0), moments_on=None):
    """H x W x 3 uint8 picture of the layouts (root Nodes, in file order) at the screen's own
    pixels, with their textures (a Textures). `rules`: scene_rules()'s pair, read by default;
    `moments_on`: {moment id: shown} over the rules' defaults."""
    textures = textures or Textures()
    vis = Visibility(rules, culture, variant, show_hidden, moments_on)
    order, tops, children = {}, [], {}
    for fi, root in enumerate(roots):
        for node, _depth, _idx in gadgets(root, hide):
            order[id(node)] = (fi, len(order))
            parent = gadget_parent(node)
            if parent is None or id(parent) not in order:
                tops.append(node)
            else:
                children.setdefault(id(parent), []).append(node)

    def by_z(n):
        fi, k = order[id(n)]
        return (_num(n.attrs.get("z")), fi, k)

    canvas = np.empty((height, width, 3), np.float32)
    canvas[:] = np.array(backdrop, np.float32) / 255.0
    sx, sy = width / 1024.0, height / 768.0
    drawn = []

    def texture(path, attrs, x, y, w, h):
        img = textures.get(path)
        if img is None:
            return
        uv = (0.0, 0.0, 1.0, 1.0)
        if attrs.get("texturecoords"):
            try:
                t = [float(v) for v in attrs["texturecoords"].split()[:4]]
            except ValueError:
                t = []
            if len(t) == 4:
                uv = tuple(t)
        tile = ("x" if "tilebackground" in attrs or "tilebackgroundhoriz" in attrs else "") + \
               ("y" if "tilebackground" in attrs or "tilebackgroundvert" in attrs else "")
        if tile and not attrs.get("texturecoords"):
            blit(canvas, img, uv, x, y, w, h, tile, width / 1024.0)
        else:
            blit(canvas, img, uv, x, y, w, h)

    def visit(n):
        if not vis.own_shown(n):
            return
        r = n.rect
        if r is not None:
            a = n.attrs
            x, y, w, h = r[0] * sx, r[1] * sy, (r[2] - r[0]) * sx, (r[3] - r[1]) * sy
            drawn.append((n, x, y, w, h))
            if "backgroundcolor" in a:
                rgb = np.array(_colour(a["backgroundcolor"], [0, 0, 0]), np.float32) / 255.0
                alpha = min(1.0, max(0.0, _num(a.get("backgroundalpha"), 1.0)))
                x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
                x1, y1 = min(width, int(round(x + w))), min(height, int(round(y + h)))
                if x1 > x0 and y1 > y0:
                    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - alpha) + rgb * alpha
            bg = a.get("background")
            if not bg:
                states = [c.attrs.get("background") or c.attrs.get("foreground") for c in n.children
                          if c.tag == "stateentry"]
                bg = next((st for st in states if st), "")
            if bg:
                texture(bg, a, x, y, w, h)
            if (a.get("type") or "").lower() == "progressbar":
                for k in ("progressbarbackground", "progressbarmask"):
                    if a.get(k):
                        texture(a[k], {}, x, y, w, h)
            if a.get("foreground"):
                texture(a["foreground"], a, x, y, w, h)
        for c in sorted(children.get(id(n), []), key=by_z):
            visit(c)

    for n in sorted(tops, key=by_z):
        visit(n)
    img = np.clip(canvas * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if boxes:
        for n, x, y, w, h in drawn:
            box(img, int(round(x)), int(round(y)), int(round(x + w)) - 1, int(round(y + h)) - 1,
                OUT_COLOUR if outside_parent(n) else DEPTH_COLOURS[0])
    return img


def parse_size(text):
    m = re.fullmatch(r"\s*(\d+)\s*[x,]\s*(\d+)\s*", text or "")
    if not m or int(m.group(1)) < 16 or int(m.group(2)) < 16:
        raise ValueError(f"--size takes WIDTHxHEIGHT, e.g. 1920x1080 (got {text!r})")
    return int(m.group(1)), int(m.group(2))


def main_textured(a, ap):
    try:
        width, height = parse_size(a.size)
    except ValueError as e:
        ap.error(str(e))
    if a.scene and not a.game:
        ap.error("--scene needs --game")
    roots = []
    if a.scene:
        found = scene_layouts(a.game, a.scene)
        if not found:
            ap.error(f"no in-game layouts found in {a.game}")
        roots += [r for _stem, r in found]
    roots += [load(p) for p in a.layout]
    if not roots:
        ap.error("give a layout file or --scene")
    moments_on = {}
    for item in a.moment or ():
        mid, _, val = item.partition("=")
        if val.lower() not in ("on", "off"):
            ap.error(f"--moment takes ID=on or ID=off (got {item!r})")
        moments_on[mid] = val.lower() == "on"
    known = {mid for mid, _rx, _on in scene_rules()[0]}
    for mid in moments_on:
        if mid not in known:
            ap.error(f"--moment: no moment {mid!r} (known: {', '.join(sorted(known))})")
    tex = Textures(a.game, a.override or (), a.suffix)
    img = render_screen(roots, width, height, tex, a.culture, a.scene or "normal", a.show_hidden,
                        re.compile(a.hide) if a.hide else None, a.boxes, moments_on=moments_on)
    if a.title:
        bitfont.draw(img, a.title, 4, 4, TEXT, shadow=(0, 0, 0))
    with open(a.out, "wb") as fh:
        fh.write(encode_png(img))
    print(f"{a.out}: {width}x{height}, {sum(len(gadgets(r)) for r in roots)} gadgets in {len(roots)} files, "
          f"{len(tex.used)} textures drawn, {len(tex.missing)} not found")
    for key, where in sorted(tex.used.items()):
        print(f"  {key}  <- {where}")
    for key in sorted(tex.missing):
        print(f"  {key}  NOT FOUND")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("layout", nargs="*")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--region", default="auto", help="auto, or x1,y1,x2,y2 in the 1024 x 768 space")
    ap.add_argument("--hide", help="regex of gadget names to leave out")
    ap.add_argument("--mark", help="regex of gadget names to highlight")
    ap.add_argument("--title")
    ap.add_argument("--strip", help="name prefix to drop in the legend")
    ap.add_argument("--text", action="store_true", help="list each gadget's text in the legend")
    ap.add_argument("--vline", help="x of dashed vertical guides in the 1024 x 768 space, comma-separated")
    ap.add_argument("--game", help="a game copy: draw the gadgets' textures from its art")
    ap.add_argument("--scene", choices=("normal", "min"), help="the copy's in-game layouts, normal or minimised")
    ap.add_argument("--size", default="1024x768", help="the screen, WIDTHxHEIGHT (textured mode)")
    ap.add_argument("--culture", choices=("Eur", "Asi", "Nat"), default="Eur",
                    help="which resource panel skin shows (textured mode)")
    ap.add_argument("--override", action="append", help="a folder of textures by art path, looked up first")
    ap.add_argument("--suffix", help="use <texture>_<suffix> where it exists")
    ap.add_argument("--boxes", action="store_true", help="draw the gadget outlines over the textures")
    ap.add_argument("--show-hidden", action="store_true", help="draw hidden gadgets too (textured mode)")
    ap.add_argument("--moment", action="append",
                    help="ID=on|off: a moment of aoe3game/uidata/hud_scene.json shown or not (textured mode)")
    a = ap.parse_args(argv)
    if a.game or a.override:
        return main_textured(a, ap)
    if len(a.layout) != 1:
        ap.error("give one layout file (or --game for the textured screen)")
    a.layout = a.layout[0]
    region = "auto" if a.region == "auto" else [float(v) for v in a.region.split(",")]
    if region != "auto" and len(region) != 4:
        ap.error("--region takes auto or four numbers")
    try:
        vlines = [float(v) for v in a.vline.split(",")] if a.vline else []
    except ValueError:
        ap.error("--vline takes numbers separated by commas")
    root = load(a.layout)
    img = render(root, a.scale, region, re.compile(a.hide) if a.hide else None,
                 re.compile(a.mark) if a.mark else None, a.title, a.strip, a.text, vlines)
    with open(a.out, "wb") as fh:
        fh.write(encode_png(img))
    n = len(gadgets(root))
    out = sum(1 for g, _, _ in gadgets(root) if outside_parent(g))
    print(f"{a.out}: {img.shape[1]}x{img.shape[0]}, {n} gadgets, {out} outside their parent")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
