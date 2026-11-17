# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws a game UI layout file (a `ui*.xml`, or its compiled `.xmb`) as a PNG, to review where its
gadgets sit without opening the game.

    python -I tools/ui_preview.py <layout.xml|.xmb> --out <preview.png>
        [--scale 2] [--region auto|x1,y1,x2,y2] [--hide REGEX] [--mark REGEX] [--title TEXT]
        [--strip PREFIX] [--text]

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

The parser is lenient, as the game's is: comments, attribute names in any case, spaces around
`=`, and stray closing tags are accepted. Text is drawn with the 5 x 7 bitmap font (`bitfont.py`),
upper case. Standard library and numpy.
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
        raw = fh.read()
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
           show_text=False):
    """H x W x 3 uint8 picture of the layout and its legend."""
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


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--region", default="auto", help="auto, or x1,y1,x2,y2 in the 1024 x 768 space")
    ap.add_argument("--hide", help="regex of gadget names to leave out")
    ap.add_argument("--mark", help="regex of gadget names to highlight")
    ap.add_argument("--title")
    ap.add_argument("--strip", help="name prefix to drop in the legend")
    ap.add_argument("--text", action="store_true", help="list each gadget's text in the legend")
    a = ap.parse_args(argv)
    region = "auto" if a.region == "auto" else [float(v) for v in a.region.split(",")]
    if region != "auto" and len(region) != 4:
        ap.error("--region takes auto or four numbers")
    root = load(a.layout)
    img = render(root, a.scale, region, re.compile(a.hide) if a.hide else None,
                 re.compile(a.mark) if a.mark else None, a.title, a.strip, a.text)
    with open(a.out, "wb") as fh:
        fh.write(encode_png(img))
    n = len(gadgets(root))
    out = sum(1 for g, _, _ in gadgets(root) if outside_parent(g))
    print(f"{a.out}: {img.shape[1]}x{img.shape[0]}, {n} gadgets, {out} outside their parent")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
