# SPDX-License-Identifier: GPL-3.0-or-later
"""Adds the missing accented Latin letters to a TrueType font, built from the font's own letters and accents.

    python -I tools/extend_font.py <in.ttf> <out.ttf> [--family NAME | --suffix TEXT] [--proof <sheet.png>]
           [--report <report.json>] [--only <letters>] [--no-kern]

Needs fontTools (and Pillow for --proof): `venv\\Scripts\\pip install fonttools pillow`, or
`pip install -r requirements-fonts.txt`.

What it adds, when the font lacks it: every letter of Latin Extended-A (U+0100 to U+017F), the Romanian
comma-below letters U+0218 to U+021B, and the letters of Latin-1 (U+00C0 to U+00FF). Each one is a composite
glyph: the font's own base letter plus the font's own accent, so the letter matches the rest of the text.

- Placement is learnt from the font's own accented letters (its composites): the height of an accent over
  lower case and over capitals, and where each base letter takes its accents. Without such a letter, an accent
  is centred over the base and kept at the font's accent height (raised over an ascender).
- The advance width is the base letter's, so the text around it keeps its spacing; ď, ľ, ť (and ŀ, ŉ, ĳ) grow
  to hold their apostrophe or second part.
- An accent the font lacks is made from its own shapes: comma below and ģ's turned comma from its comma;
  the apostrophe caron of ď ť ľ Ľ from its right quote; dot above from its period; double acute from two acutes;
  caron from a flipped circumflex (or the reverse); grave from a mirrored acute (or the reverse); dieresis from two
  periods; ring from its degree sign or a small o; ogonek from a mirrored cedilla or comma; macron and the bars
  of Ħ ħ Ŧ ŧ đ from a bar as thick as its hyphen; breve drawn as a cup in the hyphen's weight.
- A letter it cannot make from parts (ĸ, ſ, Ŋ ŋ, æ, ß, ...) is taken from the font when it has a glyph of that
  name, otherwise listed in the report.

It also updates cmap, hmtx, post, maxp, the OS/2 Unicode and code-page bits, kern (the base letter's pairs are
copied), hdmx and LTSH; a DSIG is dropped (the signature no longer matches). The family gets a new name
(--family, or the old one plus a word, --suffix, default "Ext"), so it never clashes with the installed original.
Existing glyphs are left untouched, hinting included; the new composites are hinted through their parts
(ROUND_XY_TO_GRID, as the font's own composites), and the few new simple shapes have no instructions.

Keep the licence of the input font in mind: a modified font may only be shared if its licence allows it.
"""
import argparse
import json
import math
import os
import statistics
import sys
import unicodedata

try:
    from fontTools.agl import UV2AGL
    from fontTools.pens.basePen import BasePen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen, TTGlyphPointPen
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._g_l_y_f import GlyphComponent, Glyph
    from fontTools.ttLib.tables import ttProgram
except ImportError:  # optional dependency: the module still imports, main() says what to install
    TTFont = None
    BasePen = object

ROUND_XY_TO_GRID = 0x0004
USE_MY_METRICS = 0x0200

# Marks by their combining code point: (name used in reports, spacing code points that may hold it, where it goes)
MARKS = {
    0x0300: ("grave", (0x0060, 0x02CB), "above"),
    0x0301: ("acute", (0x00B4, 0x02CA), "above"),
    0x0302: ("circumflex", (0x02C6, 0x005E), "above"),
    0x0303: ("tilde", (0x02DC, 0x007E), "above"),
    0x0304: ("macron", (0x00AF, 0x02C9), "above"),
    0x0306: ("breve", (0x02D8,), "above"),
    0x0307: ("dotaccent", (0x02D9,), "above"),
    0x0308: ("dieresis", (0x00A8,), "above"),
    0x030A: ("ring", (0x02DA,), "above"),
    0x030B: ("hungarumlaut", (0x02DD,), "above"),
    0x030C: ("caron", (0x02C7,), "above"),
    0x0312: ("commaturnedabove", (), "above"),
    0x0326: ("commabelow", (), "below"),
    0x0327: ("cedilla", (0x00B8,), "below"),
    0x0328: ("ogonek", (0x02DB,), "below"),
    0x031B: ("horn", (), "attached"),
}

# Letters whose usual shape differs from their Unicode decomposition.
SPECIAL = {
    0x010F: ("d", "apostrophe"), 0x013D: ("L", "apostrophe"), 0x013E: ("l", "apostrophe"), 0x0165: ("t", "apostrophe"),
    0x0122: ("G", 0x0326), 0x0123: ("g", 0x0312), 0x0136: ("K", 0x0326), 0x0137: ("k", 0x0326),
    0x013B: ("L", 0x0326), 0x013C: ("l", 0x0326), 0x0145: ("N", 0x0326), 0x0146: ("n", 0x0326),
    0x0156: ("R", 0x0326), 0x0157: ("r", 0x0326),
    0x0218: ("S", 0x0326), 0x0219: ("s", 0x0326), 0x021A: ("T", 0x0326), 0x021B: ("t", 0x0326),
    0x0110: ("Eth", "alias"), 0x00D0: ("Dcroat", "alias"),
    0x0111: ("d", "bar"), 0x0126: ("H", "bar"), 0x0127: ("h", "bar"), 0x0166: ("T", "bar"), 0x0167: ("t", "bar"),
    0x013F: ("L", "middot"), 0x0140: ("l", "middot"),
    0x0132: ("I J", "pair"), 0x0133: ("i j", "pair"), 0x0149: ("quoteright n", "pair"),
}
# Built from nothing: taken from the font by name when it has one, otherwise reported.
NOT_BUILT = {
    0x0138: "kra has its own small-capital shape", 0x017F: "long s has its own shape",
    0x014A: "Eng has its own shape", 0x014B: "eng has its own shape",
    0x00C6: "AE ligature", 0x00E6: "ae ligature", 0x00D8: "slashed O has its own shape",
    0x00F8: "slashed o has its own shape", 0x00DE: "thorn has its own shape", 0x00FE: "thorn has its own shape",
    0x00DF: "sharp s has its own shape", 0x00F0: "eth has its own shape", 0x0141: "L with stroke",
    0x0142: "l with stroke", 0x0152: "OE ligature", 0x0153: "oe ligature", 0x0131: "dotless i",
    0x00AA: "ordinal", 0x00BA: "ordinal", 0x00B5: "micro",
}
DEFAULT_SCOPE = list(range(0x00C0, 0x0100)) + list(range(0x0100, 0x0180)) + list(range(0x0218, 0x021C))
CODE_PAGES = {1: "cp1250", 4: "cp1254", 7: "cp1257"}  # ulCodePageRange1 bit -> code page


def need_fonttools():
    if TTFont is None:
        sys.exit("extend_font: fontTools is not installed: venv\\Scripts\\pip install fonttools pillow")


def glyph_name(cp):
    return UV2AGL.get(cp) or f"uni{cp:04X}"


class SpanPen(BasePen):
    """Flattens the outline into line segments, to find where it has ink along a horizontal line."""

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.segments, self.start, self.cur = [], None, None

    def _moveTo(self, pt):
        self.start = self.cur = pt

    def _lineTo(self, pt):
        self.segments.append((self.cur, pt))
        self.cur = pt

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur
        for i in range(1, 9):
            t = i / 8
            u = 1 - t
            pt = (u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                  u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1])
            self._lineTo(pt)

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur
        for i in range(1, 9):
            t = i / 8
            u = 1 - t
            self._lineTo((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))

    def _closePath(self):
        if self.cur != self.start:
            self._lineTo(self.start)

    def spans(self, y):
        """[(x0, x1)] where the outline has ink at height y (non-zero winding)."""
        hits = []
        for (x0, y0), (x1, y1) in self.segments:
            if y0 == y1 or not (min(y0, y1) <= y < max(y0, y1)):
                continue
            hits.append((x0 + (y - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
        hits.sort()
        out, wind, start = [], 0, None
        for x, d in hits:
            before = wind
            wind += d
            if before == 0 and wind != 0:
                start = x
            elif before != 0 and wind == 0:
                out.append((start, x))
        return out


class Extender:
    def __init__(self, font, report):
        self.font = font
        self.report = report
        self.glyf = font["glyf"]
        self.hmtx = font["hmtx"]
        self.order = list(font.getGlyphOrder())
        self.cmap = dict(font.getBestCmap())
        self.names = set(self.order)
        self.upm = font["head"].unitsPerEm
        self.new_glyphs = []          # (name, base glyph or None) in the order added
        self.mapping = {}             # code point -> glyph name added to cmap
        self.mark_glyphs = {}         # combining cp -> glyph name of the mark
        self.drawn_marks = {}         # combining cp -> how it was made (report)
        self.lowered = []             # letters whose accent was lowered under the Windows ascent
        self.shared = {}              # new letter -> the font's identical glyph it maps to
        self.metrics()
        self.learn()

    # ---- geometry --------------------------------------------------------------------------------------
    def gs(self):
        return self.font.getGlyphSet()

    def bounds(self, name):
        pen = BoundsPen(self.gs())
        self.gs()[name].draw(pen)
        return pen.bounds or (0, 0, 0, 0)

    def spans(self, name, y):
        pen = SpanPen(self.gs())
        self.gs()[name].draw(pen)
        return pen.spans(y)

    def g(self, cp):
        return self.cmap.get(cp)

    def metrics(self):
        def top(chars, default):
            for c in chars:
                if self.g(ord(c)):
                    return self.bounds(self.g(ord(c)))[3]
            return default
        self.xh = top("xzvwn", 0.5 * self.upm)
        self.caph = top("HIEFTZ", 0.7 * self.upm)
        lows = [self.bounds(self.g(ord(c)))[1] for c in "pqgjy" if self.g(ord(c))]
        self.desc = min(lows) if lows else -0.2 * self.upm
        hy = self.g(0x2D) or self.g(0x2212)
        self.stroke = (self.bounds(hy)[3] - self.bounds(hy)[1]) if hy else 0.08 * self.upm
        stem = None
        for c in "lI":
            if self.g(ord(c)):
                b = self.bounds(self.g(ord(c)))
                sp = self.spans(self.g(ord(c)), (b[1] + b[3]) / 2)
                if sp:
                    stem = max(x1 - x0 for x0, x1 in sp)
                    break
        self.stem = stem or self.stroke
        self.slant = -math.tan(math.radians(self.font["post"].italicAngle or 0.0))

    def is_upper(self, base):
        cp = next((c for c, n in self.cmap.items() if n == base), None)
        if cp is not None:
            return chr(cp).isupper()
        return base[:1].isupper()

    # ---- learning from the font's own accented letters --------------------------------------------------
    def learn(self):
        """dy per case and above/below, and the x anchor of each base, from the font's composites."""
        dys = {("above", True): [], ("above", False): [], ("below", True): [], ("below", False): []}
        self.anchor = {}  # (base, where) -> [x centre of the placed mark]
        self.mark_dy = {}  # (mark glyph, capital) -> [dy] in the font's own letters
        self.mark_centre = {"above": [], "below": []}
        self.zone = {"above": [], "below": []}  # lower-case mark yMin above x-height (above), mark yMax (below)
        flags = []
        self.existing = {}  # (base, mark, dx, dy) -> the font's own composite
        rev = {}
        for cp, name in self.cmap.items():
            rev.setdefault(name, cp)
        for name in self.order:
            gl = self.glyf[name]
            if not gl.isComposite() or len(gl.components) != 2 or name not in rev:
                continue
            decomp = unicodedata.decomposition(chr(rev[name])).split()
            if len(decomp) != 2 or decomp[0].startswith("<"):
                continue
            base_cp, mark_cp = int(decomp[0], 16), int(decomp[1], 16)
            if isinstance(SPECIAL.get(rev[name], (0, None))[1], int):
                mark_cp = SPECIAL[rev[name]][1]  # Ķ, ģ, ...: a comma, whatever Unicode's decomposition says
            if mark_cp not in MARKS or self.g(base_cp) is None:
                continue
            c0, c1 = gl.components
            if c0.glyphName != self.g(base_cp) and c1.glyphName == self.g(base_cp):
                c0, c1 = c1, c0
            base_glyph = c0.glyphName
            if base_glyph not in (self.g(base_cp), "dotlessi", "dotlessj"):
                continue
            where = MARKS[mark_cp][2]
            if where not in ("above", "below"):
                continue
            mb = self.bounds(c1.glyphName)
            dx, dy = c1.x - c0.x, c1.y - c0.y
            upper = chr(base_cp).isupper()
            bb = self.bounds(base_glyph)
            ref = self.caph if upper else self.xh
            if where == "above" and bb[3] > ref * 1.08:
                continue  # over an ascender: not the plain accent height
            dys[(where, upper)].append(dy)
            self.mark_dy.setdefault((c1.glyphName, upper), []).append(dy)
            self.anchor.setdefault((base_glyph, where), []).append(dx + (mb[0] + mb[2]) / 2)
            self.mark_glyphs.setdefault(mark_cp, c1.glyphName)
            self.mark_centre[where].append((mb[0] + mb[2]) / 2)
            if not upper:
                self.zone[where].append(mb[1] + dy - ref if where == "above" else mb[3] + dy)
            flags.append((c0.flags & (ROUND_XY_TO_GRID | USE_MY_METRICS), c1.flags & ROUND_XY_TO_GRID))
            self.existing[(c0.glyphName, c1.glyphName, dx, dy)] = name
        med = lambda v, d: statistics.median(v) if v else d  # noqa: E731
        self.dy = {k: med(v, None) for k, v in dys.items()}
        if self.dy[("above", False)] is None:
            self.dy[("above", False)] = 0
        if self.dy[("above", True)] is None:
            self.dy[("above", True)] = self.caph - self.xh
        for side in (True, False):
            if self.dy[("below", side)] is None:
                self.dy[("below", side)] = 0
        self.zone_above = med(self.zone["above"], 0.08 * self.upm)
        self.zone_below = med(self.zone["below"], 0)
        self.mark_cx = {k: med(v, None) for k, v in self.mark_centre.items()}
        # the component flags of the font's own accented letters (rounding, the base's metrics)
        self.base_flags, self.mark_flags = statistics.mode(flags) if flags else (ROUND_XY_TO_GRID, ROUND_XY_TO_GRID)
        self.report["learnt"] = {
            "x_height": round(self.xh), "cap_height": round(self.caph), "descender": round(self.desc),
            "stroke": round(self.stroke), "stem": round(self.stem),
            "accent_dy_lower": self.dy[("above", False)], "accent_dy_capital": self.dy[("above", True)],
            "composites_learnt_from": len(flags)}

    # ---- glyphs ----------------------------------------------------------------------------------------
    def unique(self, name):
        base, k = name, 1
        while name in self.names:
            name = f"{base}.{k}"
            k += 1
        self.names.add(name)
        return name

    def add_glyph(self, name, glyph, advance, base=None):
        self.glyf.glyphs[name] = glyph
        self.order.append(name)
        self.font.setGlyphOrder(self.order)
        glyph.recalcBounds(self.glyf)
        self.hmtx.metrics[name] = (int(round(advance)), getattr(glyph, "xMin", 0) or 0)
        self.new_glyphs.append((name, base))
        return name

    def simple_from(self, draw, name, advance=0):
        """A new simple glyph from a drawing function(pen); it has no instructions."""
        pen = TTGlyphPen(self.gs())
        draw(pen)
        glyph = pen.glyph()
        glyph.program = ttProgram.Program()
        glyph.program.fromBytecode(b"")
        return self.add_glyph(self.unique(name), glyph, advance)

    def transformed(self, src, matrix, name, reverse=False):
        def draw(pen):
            target = ReverseContourPen(pen) if reverse else pen
            self.gs()[src].draw(TransformPen(target, matrix))
        return self.simple_from(draw, name)

    def placed(self, name, cx=None, y0=None, y1=None):
        """A copy of mark glyph name moved so that its centre is cx and its bottom y0 (or its top y1)."""
        b = self.bounds(name)
        dx = 0 if cx is None else cx - (b[0] + b[2]) / 2
        dy = 0 if y0 is None and y1 is None else (y0 - b[1] if y0 is not None else y1 - b[3])
        return self.transformed(name, (1, 0, 0, 1, dx, dy), name + ".moved")

    def bar(self, x0, x1, y_mid, name):
        h = self.stroke
        y0, y1 = round(y_mid - h / 2), round(y_mid + h / 2)
        x0, x1 = round(x0), round(x1)

        def draw(pen):  # clockwise: an outer TrueType contour
            pen.moveTo((x0, y0))
            pen.lineTo((x0, y1))
            pen.lineTo((x1, y1))
            pen.lineTo((x1, y0))
            pen.closePath()
        return self.simple_from(draw, name)

    def composite(self, name, parts, advance, base):
        if len(parts) == 2 and parts[0][1:] == (0, 0):
            same = self.existing.get((parts[0][0], parts[1][0], int(round(parts[1][1])), int(round(parts[1][2]))))
            if same and self.hmtx[same][0] == int(round(advance)):
                self.shared[name] = same  # the font already has this very letter under another code point
                return same
        glyph = Glyph()
        glyph.numberOfContours = -1
        glyph.components = []
        for k, (part, x, y) in enumerate(parts):
            c = GlyphComponent()
            flags = self.base_flags if k == 0 else self.mark_flags
            if k > 0 or int(round(advance)) != self.hmtx[part][0]:
                flags &= ~USE_MY_METRICS  # only a base whose advance the letter keeps lends its metrics
            c.glyphName, c.x, c.y, c.flags = part, int(round(x)), int(round(y)), flags
            glyph.components.append(c)
        return self.add_glyph(name, glyph, advance, base)

    # ---- marks -----------------------------------------------------------------------------------------
    def above_zone_y(self):
        return self.xh + self.zone_above  # bottom of a lower-case accent

    def mark(self, mcp):
        """The glyph of a mark, made from the font's shapes when it has none."""
        if mcp in self.mark_glyphs:
            return self.mark_glyphs[mcp]
        name, spacing, where = MARKS[mcp]
        glyph = next((self.g(cp) for cp in spacing if self.g(cp)), None)
        if glyph is None and name in self.names and not self.glyf[name].isComposite():
            glyph = name
        if glyph is None:
            glyph = self.make_mark(mcp)
        if glyph:
            self.mark_glyphs[mcp] = glyph
        return glyph

    def at_accent_height(self, src, name, scale=1.0, matrix=None, reverse=False):
        """A transformed copy of src sitting in the lower-case accent zone, centred like the font's accents."""
        tmp = self.transformed(src, matrix or (scale, 0, 0, scale, 0, 0), name + ".tmp", reverse)
        cx = self.mark_cx["above"]
        b = self.bounds(tmp)
        cx = (b[0] + b[2]) / 2 if cx is None else cx
        out = self.transformed(tmp, (1, 0, 0, 1, cx - (b[0] + b[2]) / 2, self.above_zone_y() - b[1]), name)
        self.drop(tmp)
        return out

    def drop(self, name):
        del self.glyf.glyphs[name]
        del self.hmtx.metrics[name]
        self.order.remove(name)
        self.font.setGlyphOrder(self.order)
        self.new_glyphs = [(n, b) for n, b in self.new_glyphs if n != name]
        self.names.discard(name)

    def make_mark(self, mcp):
        name = MARKS[mcp][0]
        comma, quote = self.g(0x2C), self.g(0x2019) or self.g(0x27)
        period = self.g(0x2E)
        how = None
        out = None
        if mcp == 0x0326 and comma:  # comma below: the font's comma, smaller, under the baseline
            b = self.bounds(comma)
            gap = 0.03 * self.upm
            room = abs(self.desc) - gap
            s = min(0.75, 0.9 * room / max(1, b[3] - b[1]))
            tmp = self.transformed(comma, (s, 0, 0, s, 0, 0), "commabelow.tmp")
            tb = self.bounds(tmp)
            out = self.transformed(tmp, (1, 0, 0, 1, -(tb[0] + tb[2]) / 2, -gap - tb[3]), "commaaccent")
            self.drop(tmp)
            how = f"the comma at {s:.2f}"
        elif mcp == 0x0312 and comma:  # turned comma above (ģ)
            b = self.bounds(comma)
            s = min(0.75, 0.9 * (self.caph - self.xh) / max(1, b[3] - b[1]))
            out = self.at_accent_height(comma, "commaturnedabove", matrix=(-s, 0, 0, -s, 0, 0))
            how = f"the comma turned, at {s:.2f}"
        elif mcp == 0x0307 and period:
            out = self.at_accent_height(period, "dotaccent")
            how = "the period"
        elif mcp == 0x030B and self.mark(0x0301):
            ac = self.mark(0x0301)
            b = self.bounds(ac)
            w = b[2] - b[0]

            def draw(pen):
                self.gs()[ac].draw(TransformPen(pen, (0.85, 0, 0, 1, -0.45 * w, 0)))
                self.gs()[ac].draw(TransformPen(pen, (0.85, 0, 0, 1, 0.45 * w, 0)))
            tmp = self.simple_from(draw, "hungarumlaut.tmp")
            out = self.at_accent_height(tmp, "hungarumlaut")
            self.drop(tmp)
            how = "two acutes"
        elif mcp == 0x030C and self.g(0x02C6):
            out = self.at_accent_height(self.g(0x02C6), "caron", matrix=(1, 0, 0, -1, 0, 0), reverse=True)
            how = "the circumflex flipped"
        elif mcp == 0x0302 and self.g(0x02C7):
            out = self.at_accent_height(self.g(0x02C7), "circumflex", matrix=(1, 0, 0, -1, 0, 0), reverse=True)
            how = "the caron flipped"
        elif mcp == 0x0300 and (self.g(0xB4) or self.g(0x2CA)):
            out = self.at_accent_height(self.g(0xB4) or self.g(0x2CA), "grave", matrix=(-1, 0, 0, 1, 0, 0), reverse=True)
            how = "the acute mirrored"
        elif mcp == 0x0301 and self.g(0x60):
            out = self.at_accent_height(self.g(0x60), "acute", matrix=(-1, 0, 0, 1, 0, 0), reverse=True)
            how = "the grave mirrored"
        elif mcp == 0x0308 and period:
            b = self.bounds(period)
            w = b[2] - b[0]

            def draw(pen):
                self.gs()[period].draw(TransformPen(pen, (1, 0, 0, 1, -0.9 * w, 0)))
                self.gs()[period].draw(TransformPen(pen, (1, 0, 0, 1, 0.9 * w, 0)))
            tmp = self.simple_from(draw, "dieresis.tmp")
            out = self.at_accent_height(tmp, "dieresis")
            self.drop(tmp)
            how = "two periods"
        elif mcp == 0x030A and (self.g(0xB0) or self.g(ord("o"))):
            src = self.g(0xB0) or self.g(ord("o"))
            b = self.bounds(src)
            s = 1.0 if self.g(0xB0) else 0.4
            s = min(s, 0.8 * (self.caph - self.xh) / max(1, b[3] - b[1]))
            out = self.at_accent_height(src, "ring", scale=s)
            how = ("the degree sign" if self.g(0xB0) else "a small o") + f" at {s:.2f}"
        elif mcp == 0x0328 and (self.g(0xB8) or comma):
            src = self.g(0xB8) or comma
            b = self.bounds(src)
            tmp = self.transformed(src, (-1, 0, 0, 1, 0, 0), "ogonek.tmp", reverse=True)
            tb = self.bounds(tmp)
            out = self.transformed(tmp, (1, 0, 0, 1, -(tb[0] + tb[2]) / 2, self.stroke * 0.4 - tb[3]), "ogonek")
            self.drop(tmp)
            how = "the cedilla mirrored" if self.g(0xB8) else "the comma mirrored"
        elif mcp == 0x0304:
            w = 0.45 * (self.bounds(self.g(ord("x")))[2] - self.bounds(self.g(ord("x")))[0]) if self.g(ord("x")) else 0.25 * self.upm
            tmp = self.bar(-w / 2, w / 2, 0, "macron.tmp")
            out = self.at_accent_height(tmp, "macron")
            self.drop(tmp)
            how = "a bar in the hyphen's weight"
        elif mcp == 0x0306:
            out = self.draw_breve()
            how = "a cup in the hyphen's weight"
        elif mcp == 0x0327 and comma:
            tmp = self.transformed(comma, (0.8, 0, 0, 0.8, 0, 0), "cedilla.tmp")
            tb = self.bounds(tmp)
            out = self.transformed(tmp, (1, 0, 0, 1, -(tb[0] + tb[2]) / 2, self.stroke * 0.4 - tb[3]), "cedilla")
            self.drop(tmp)
            how = "the comma"
        if out:
            self.drawn_marks[mcp] = how
        return out

    def draw_breve(self):
        w = 0.42 * (self.bounds(self.g(ord("x")))[2] - self.bounds(self.g(ord("x")))[0]) if self.g(ord("x")) else 0.22 * self.upm
        h = 0.45 * w
        t = self.stroke * 0.9
        r_out, r_in = w / 2, w / 2 - t

        def draw(pen):  # outer arc left to right below, then inner arc back: clockwise in y-up
            pen.moveTo((-r_out, h))
            pen.qCurveTo((-r_out, 0), (0, 0))
            pen.qCurveTo((r_out, 0), (r_out, h))
            pen.lineTo((r_in, h))
            pen.qCurveTo((r_in, t), (0, t))
            pen.qCurveTo((-r_in, t), (-r_in, h))
            pen.closePath()
        tmp = self.simple_from(lambda pen: draw(ReverseContourPen(pen)), "breve.tmp")
        out = self.at_accent_height(tmp, "breve")
        self.drop(tmp)
        return out

    # ---- placing a mark on a base ------------------------------------------------------------------------
    def base_glyph(self, base_cp, where):
        """The glyph a mark goes on: dotless i and j under an accent above."""
        if where == "above" and base_cp in (ord("i"), ord("j")):
            dotless = self.g(0x131 if base_cp == ord("i") else 0x237)
            if dotless:
                return dotless
            return self.make_dotless(base_cp)
        return self.g(base_cp)

    def make_dotless(self, base_cp):
        src = self.g(base_cp)
        if not src:
            return None
        name = "dotlessi" if base_cp == ord("i") else "dotlessj"
        if name in self.names and not self.glyf[name].isComposite():
            return name
        gl = self.glyf[src]
        if gl.isComposite():
            return None
        coords, ends = gl.getCoordinates(self.glyf)[0], gl.endPtsOfContours
        keep, start = [], 0
        for end in ends:
            ys = [coords[i][1] for i in range(start, end + 1)]
            if min(ys) < self.xh * 0.9:
                keep.append((start, end))
            start = end + 1
        if len(keep) == len(ends):
            return None
        flags = gl.flags
        pen = TTGlyphPointPen(self.gs())  # point by point: the outline of the kept contours is exact
        for s, e in keep:
            pen.beginPath()
            for i in range(s, e + 1):
                pen.addPoint(tuple(coords[i]), "line" if flags[i] & 1 else None)
            pen.endPath()
        glyph = pen.glyph()
        glyph.program = ttProgram.Program()
        glyph.program.fromBytecode(b"")
        self.drawn_marks[f"dotless {chr(base_cp)}"] = f"{chr(base_cp)} without its dot"
        out = self.add_glyph(self.unique(name), glyph, self.hmtx[src][0], src)
        if base_cp == ord("j") and 0x237 not in self.cmap:
            self.mapping[0x237] = out
        return out

    def anchor_x(self, base, where, mark_bounds, base_bounds, upper):
        known = self.anchor.get((base, where))
        if known:
            return statistics.median(known)
        if where == "above":
            cx = (base_bounds[0] + base_bounds[2]) / 2
            return cx + self.slant * ((self.caph if upper else self.xh) - (base_bounds[1] + base_bounds[3]) / 2)
        # below: the middle of the ink just above the baseline
        sp = self.spans(base, max(base_bounds[1], 0) + 0.06 * (self.caph if upper else self.xh))
        if sp:
            return (sp[0][0] + sp[-1][1]) / 2
        return (base_bounds[0] + base_bounds[2]) / 2

    def dy_of(self, mark, where, upper):
        """The mark's own height in the font's letters of that case, else the usual one."""
        own = self.mark_dy.get((mark, upper))
        return statistics.median(own) if own else self.dy[(where, upper)]

    def build_marked(self, cp, base_cp, mcp):
        where = MARKS[mcp][2]
        base = self.base_glyph(base_cp, where)
        if not base:
            return None, f"no base letter {chr(base_cp)}"
        mark = self.mark(mcp)
        if not mark:
            return None, f"no {MARKS[mcp][0]} and nothing to make it from"
        upper = chr(base_cp).isupper()
        bb, mb = self.bounds(base), self.bounds(mark)
        if mcp == 0x0328:
            # ogonek: at the right foot (the font's own ogonek letters, when it has some, win)
            known = self.anchor.get((base, "below"))
            sp = self.spans(base, max(bb[1], 0) + 0.06 * (self.caph if upper else self.xh))
            if known and mcp in self.mark_glyphs and self.mark_glyphs[mcp] == mark:
                x = statistics.median(known) - (mb[0] + mb[2]) / 2
            elif base_cp in (ord("e"), ord("E")) or not sp:
                x = (bb[0] + bb[2]) / 2 + 0.15 * (bb[2] - bb[0]) - (mb[0] + mb[2]) / 2
            else:
                x = sp[-1][1] - mb[2] + 0.1 * (mb[2] - mb[0])
            y = self.dy_of(mark, "below", upper)
            return self.composite(glyph_name(cp), [(base, 0, 0), (mark, x, y)], self.hmtx[base][0], base), None
        ax = self.anchor_x(base, where, mb, bb, upper)
        x = ax - (mb[0] + mb[2]) / 2
        if where == "above":
            y = self.dy_of(mark, "above", upper)
            ref = self.caph if upper else self.xh
            if bb[3] > ref * 1.08:  # over an ascender
                y += bb[3] - ref
            top = self.font["OS/2"].usWinAscent
            if y + mb[3] > top:  # Windows clips above the ascent: lower the accent to fit
                y = top - mb[3]
                self.lowered.append(chr(cp))
        else:
            y = self.dy_of(mark, "below", upper)
        return self.composite(glyph_name(cp), [(base, 0, 0), (mark, x, y)], self.hmtx[base][0], base), None

    # ---- special letters -----------------------------------------------------------------------------
    def build_special(self, cp, spec):
        what, how = spec
        if isinstance(how, int):
            return self.build_marked(cp, ord(what), how)
        if how == "alias":
            src = self.cmap.get(0x00D0 if cp == 0x0110 else 0x0110)
            if src:
                self.mapping[cp] = src
                return src, None
            return None, "no Eth (U+00D0) or D with stroke (U+0110) to share"
        if how == "pair":
            parts = what.split()
            names = [self.g(0x2019) if p == "quoteright" else self.g(ord(p)) for p in parts]
            if not all(names):
                return None, "missing " + " or ".join(p for p, n in zip(parts, names) if not n)
            first, second = names
            adv1 = self.hmtx[first][0]
            if parts[0] == "quoteright":  # ŉ: the apostrophe close to the n
                b = self.bounds(first)
                adv1 = b[2] + 0.06 * self.upm
            return self.composite(glyph_name(cp), [(first, 0, 0), (second, adv1, 0)],
                                  adv1 + self.hmtx[second][0], first), None
        base = self.g(ord(what))
        if not base:
            return None, f"no base letter {what}"
        bb = self.bounds(base)
        upper = what.isupper()
        ref = self.caph if upper else self.xh
        adv = self.hmtx[base][0]
        if how == "apostrophe":
            quote = self.g(0x2019) or self.g(0x27)
            if not quote:
                return None, "no right quote or apostrophe to make the caron from"
            qb = self.bounds(quote)
            s = min(0.85, 0.32 * ref / max(1, qb[3] - qb[1])) if upper else 0.85
            tmp = self.transformed(quote, (s, 0, 0, s, 0, 0), "caronvertical.tmp")
            name = self.mark_glyphs.get("apostrophe")
            sp = self.spans(base, bb[3] - 0.12 * (bb[3] - bb[1]))
            stem_right = sp[0][1] if sp else bb[2]
            if upper:
                stem_right = sp[0][1] if sp else bb[0] + self.stem
            tb = self.bounds(tmp)
            if name is None:
                name = self.transformed(tmp, (1, 0, 0, 1, -tb[0], -tb[3]), "caronvertical")
                self.mark_glyphs["apostrophe"] = name
                self.drawn_marks["apostrophe"] = f"the right quote at {s:.2f}"
            self.drop(tmp)
            nb = self.bounds(name)
            gap = 0.5 * self.stem
            x, y = stem_right + gap - nb[0], bb[3] - nb[3]
            right = x + nb[2]
            rsb = max(0, adv - bb[2])
            new_adv = adv if upper and right + rsb * 0.5 <= adv else max(adv, right + rsb)
            return self.composite(glyph_name(cp), [(base, 0, 0), (name, x, y)], new_adv, base), None
        if how == "middot":
            dot = self.g(0xB7)
            if not dot:
                return None, "no middle dot (U+00B7)"
            db = self.bounds(dot)
            sp = self.spans(base, ref * 0.5)
            stem_right = sp[0][1] if sp else bb[0] + self.stem
            y = ref * 0.55 - (db[1] + db[3]) / 2
            x = stem_right + 0.6 * self.stem - db[0]
            right = x + db[2]
            new_adv = max(adv, right + max(0, adv - bb[2])) if not upper else max(adv, right + 0.3 * self.stem)
            return self.composite(glyph_name(cp), [(base, 0, 0), (dot, x, y)], new_adv, base), None
        if how == "bar":
            if what in "HT":
                if what == "H":
                    y = bb[1] + 0.75 * (bb[3] - bb[1])
                    x0, x1 = bb[0] - 0.4 * self.stem, bb[2] + 0.4 * self.stem
                else:
                    y = ref * 0.45
                    sp = self.spans(base, y)
                    s0, s1 = (sp[0] if sp else ((bb[0] + bb[2]) / 2 - self.stem / 2, (bb[0] + bb[2]) / 2 + self.stem / 2))
                    x0, x1 = s0 - 1.5 * self.stem, s1 + 1.5 * self.stem
            else:  # d, h, t: across the stem that rises over the x-height (t: under its crossbar)
                y = self.xh * 0.45 if what == "t" else self.xh + 0.55 * (bb[3] - self.xh)
                sp = self.spans(base, y)
                if not sp:
                    return None, "could not find the stem for the bar"
                s0, s1 = (sp[-1] if what == "d" else sp[0])
                x0, x1 = s0 - 1.2 * self.stem, s1 + 1.2 * self.stem
                if what == "t":
                    x0, x1 = s0 - 1.0 * self.stem, s1 + 1.0 * self.stem
            bar = self.bar(x0, x1, y, glyph_name(cp) + ".bar")
            self.drawn_marks.setdefault("bar", "a bar in the hyphen's weight")
            return self.composite(glyph_name(cp), [(base, 0, 0), (bar, 0, 0)], adv, base), None
        return None, "unknown recipe"

    # ---- one letter ------------------------------------------------------------------------------------
    def build(self, cp):
        name = glyph_name(cp)
        if name in self.names and name not in [n for n, _ in self.new_glyphs]:
            self.mapping[cp] = name  # the font has the glyph, only unencoded
            return name, "taken from the font (unencoded glyph)"
        if cp in SPECIAL:
            return self.build_special(cp, SPECIAL[cp])
        if cp in NOT_BUILT:
            return None, NOT_BUILT[cp]
        decomp = unicodedata.decomposition(chr(cp)).split()
        if len(decomp) != 2 or decomp[0].startswith("<"):
            return None, "no decomposition into a letter and an accent"
        base_cp, mcp = int(decomp[0], 16), int(decomp[1], 16)
        if mcp not in MARKS or MARKS[mcp][2] == "attached":
            return None, f"accent U+{mcp:04X} not supported"
        return self.build_marked(cp, base_cp, mcp)


def set_bits(font, added):
    os2 = font["OS/2"]
    cmap = font.getBestCmap()
    have = set(cmap)
    if any(0xA0 <= c <= 0xFF for c in have):
        os2.ulUnicodeRange1 |= 1 << 1
    if any(0x100 <= c <= 0x17F for c in have):
        os2.ulUnicodeRange1 |= 1 << 2
    if any(0x180 <= c <= 0x24F for c in have):
        os2.ulUnicodeRange1 |= 1 << 3
    for bit, codec in CODE_PAGES.items():
        letters = {ord(ch) for ch in bytes(range(0x80, 0x100)).decode(codec, "ignore") if ch.isalpha()}
        if letters <= have:
            os2.ulCodePageRange1 |= 1 << bit
    os2.usFirstCharIndex = min(min(have), 0xFFFF)
    os2.usLastCharIndex = min(max(have), 0xFFFF)


def rename(font, family=None, suffix="Ext"):
    name = font["name"]
    old = name.getDebugName(1) or "Font"
    new = family or f"{old} {suffix.strip()}"
    ps_old = name.getDebugName(6) or old.replace(" ", "")
    ps_new = new.replace(" ", "") + ps_old[len(ps_old.split("-")[0]):] if "-" in ps_old else new.replace(" ", "")
    for rec in name.names:
        if rec.nameID in (1, 3, 4, 16, 18, 21):
            text = rec.toUnicode()
            if old in text:
                rec.string = text.replace(old, new)
            elif rec.nameID in (1, 16, 21):
                rec.string = new
            elif rec.nameID == 3:
                rec.string = new + "; " + text
        elif rec.nameID in (6, 20):
            rec.string = ps_new
    if len(new) > 31:
        print(f"extend_font: warning: the family name {new!r} is longer than Windows' 31 characters")
    return old, new


def copy_kerning(font, pairs_from, limit=10920):
    """Each new glyph kerns like its base letter. pairs_from: [(new, base, as_left, as_right)]."""
    if "kern" not in font:
        return 0
    added = 0
    for table in font["kern"].kernTables:
        if getattr(table, "format", None) != 0:
            continue
        kt = table.kernTable
        left, right = {}, {}
        for (a, b), v in kt.items():
            left.setdefault(a, []).append((b, v))
            right.setdefault(b, []).append((a, v))
        for new, base, as_left, as_right in pairs_from:
            if as_left:
                for b, v in left.get(base, []):
                    if len(kt) < limit and (new, b) not in kt:
                        kt[(new, b)] = v
                        added += 1
            if as_right:
                for a, v in right.get(base, []):
                    if len(kt) < limit and (a, new) not in kt:
                        kt[(a, new)] = v
                        added += 1
    return added


def device_tables(font, new_glyphs):
    """hdmx and LTSH hold one entry per glyph: give the new ones their base letter's values."""
    upm = font["head"].unitsPerEm
    hmtx = font["hmtx"]
    if "hdmx" in font:
        table = font["hdmx"]
        for ppem, widths in list(table.hdmx.items()):
            widths = {k: widths[k] for k in widths.keys()}  # a plain dict that takes new names
            for name, base in new_glyphs:
                same = base and hmtx[name][0] == hmtx[base][0]
                widths[name] = widths[base] if same else min(255, int(round(hmtx[name][0] * ppem / upm)))
            table.hdmx[ppem] = widths
    if "LTSH" in font:
        y = font["LTSH"].yPels
        top = max(y.values()) if y else 1
        for name, base in new_glyphs:
            y[name] = y.get(base, top) if base else top


def extend(path_in, path_out, family=None, suffix="Ext", only=None, kern=True):
    need_fonttools()
    font = TTFont(path_in)
    if "glyf" not in font:
        sys.exit("extend_font: only TrueType outlines (glyf) are supported")
    for tag in font.keys():  # decompile every table now, while the glyph order is still the input's
        if tag != "GlyphOrder":
            font[tag]
    report = {"input": os.path.basename(path_in), "output": os.path.basename(path_out)}
    head_top, head_bottom = font["head"].yMax, font["head"].yMin  # the font's own tallest and deepest glyphs
    ex = Extender(font, report)
    scope = only if only is not None else DEFAULT_SCOPE
    added, failed, had = [], {}, []
    for cp in scope:
        if cp in ex.cmap or cp in ex.mapping:
            had.append(cp)
            continue
        if not chr(cp).isalpha():
            continue
        try:
            glyph, why = ex.build(cp)
        except Exception as exc:  # one letter must not stop the others
            glyph, why = None, f"error: {exc}"
        if glyph:
            ex.mapping.setdefault(cp, glyph)
            added.append(cp)
        else:
            failed[cp] = why
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in ex.mapping.items():
                if cp <= 0xFFFF or table.format in (12, 13):
                    table.cmap[cp] = name
    set_bits(font, added)
    old, new = rename(font, family, suffix)
    kerned = 0
    if kern:
        pairs = []
        for cp, name in ex.mapping.items():
            g = font["glyf"][name]
            if not g.isComposite() or name not in [n for n, _ in ex.new_glyphs]:
                continue
            base = g.components[0].glyphName
            special = SPECIAL.get(cp, (None, None))[1]
            pairs.append((name, base, special not in ("apostrophe", "middot", "pair"), True))
        kerned = copy_kerning(font, pairs)
    device_tables(font, ex.new_glyphs)
    if "DSIG" in font:
        del font["DSIG"]
    font.save(path_out)
    out = TTFont(path_out)
    # Windows clips at the ascent and descent; a letter no taller or deeper than the font's own is no worse
    win_top = max(out["OS/2"].usWinAscent, head_top)
    win_bottom = min(-out["OS/2"].usWinDescent, head_bottom)
    gs = out.getGlyphSet()
    clipped = []
    for cp in added:
        pen = BoundsPen(gs)
        gs[ex.mapping[cp]].draw(pen)
        if pen.bounds and (pen.bounds[3] > win_top or pen.bounds[1] < win_bottom):
            clipped.append(chr(cp))
    report.update({
        "family": {"old": old, "new": new},
        "had": "".join(chr(c) for c in had),
        "added": "".join(chr(c) for c in added),
        "added_count": len(added),
        "not_built": {chr(c): why for c, why in failed.items()},
        "marks_made": {(MARKS[k][0] if isinstance(k, int) and k in MARKS else str(k)): v for k, v in ex.drawn_marks.items()},
        "accent_lowered_to_fit": "".join(ex.lowered),
        "shared_with_existing": {chr(c): n for c, n in ex.mapping.items() if glyph_name(c) in ex.shared},
        "kern_pairs_added": kerned,
        "outside_win_ascent_descent": "".join(clipped),
        "glyphs": len(out.getGlyphOrder()),
    })
    return report


def proof(path, sheet, letters, sizes=(14, 20, 40), sample=None):
    """A PNG with the letters at each size, rendered from the font with Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    label_font = ImageFont.load_default()
    lines = []
    width = 1400
    for size in sizes:
        f = ImageFont.truetype(path, size)
        per = max(8, int(width / (size * 0.9)))
        rows = [letters[i:i + per] for i in range(0, len(letters), per)] or [""]
        if sample:
            rows.append(sample)
        lines.append((f"{size} px", None))
        for r in rows:
            lines.append((r, f))
    height = 20 + sum((int(f.size * 1.6) if f else 16) for _, f in lines)
    img = Image.new("RGB", (width + 40, height), "white")
    d = ImageDraw.Draw(img)
    y = 10
    d.text((20, y), os.path.basename(path), fill="black", font=label_font)
    y += 16
    for text, f in lines:
        if f is None:
            d.text((20, y), text, fill=(120, 0, 0), font=label_font)
            y += 16
        else:
            d.text((20, y), text, fill="black", font=f)
            y += int(f.size * 1.6)
    img.save(sheet)


def parse_letters(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if part.upper().startswith("U+"):
            lo, _, hi = part[2:].partition("-")
            hi = hi[2:] if hi.upper().startswith("U+") else hi
            out += list(range(int(lo, 16), int(hi or lo, 16) + 1))
        else:
            out += [ord(c) for c in part]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--family", help="the new family name (default: the old one plus --suffix)")
    ap.add_argument("--suffix", default="Ext", help="a word added after the family name when --family is not given")
    ap.add_argument("--only", help="letters or ranges to add instead of the default scope (e.g. ăș,U+0218-U+021B)")
    ap.add_argument("--proof", help="write a proof sheet PNG of the added letters (needs Pillow)")
    ap.add_argument("--report", help="write the report as JSON")
    ap.add_argument("--no-kern", action="store_true", help="do not copy the base letters' kerning pairs")
    a = ap.parse_args(argv)
    need_fonttools()
    if os.path.abspath(a.input) == os.path.abspath(a.output):
        sys.exit("extend_font: the output must be another file")
    for out in (a.output, a.proof, a.report):
        if out and "steamapps" in os.path.abspath(out).lower().replace("/", "\\").split("\\"):
            sys.exit(f"extend_font: refusing to write into a Steam library: {out}; use a copy of the game")
    only = parse_letters(a.only) if a.only else None
    report = extend(a.input, a.output, a.family, a.suffix, only, not a.no_kern)
    if a.proof:
        letters = report["added"]
        sample = "Ăă Ââ Îî Șș Țț Şş Ţţ  Sarja Roșior · Călărași · Racoviță"
        proof(a.output, a.proof, letters, sample=sample)
        report["proof"] = os.path.basename(a.proof)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"{report['input']} -> {report['output']}: family {report['family']['old']!r} -> {report['family']['new']!r}")
    print(f"  added {report['added_count']}: {report['added']}")
    for ch, why in report["not_built"].items():
        print(f"  not built: {ch} U+{ord(ch):04X}: {why}")
    for ch, glyph in report["shared_with_existing"].items():
        print(f"  {ch} shares the font's own glyph {glyph} (same parts, same place)")
    for mark, how in report["marks_made"].items():
        print(f"  made {mark} from {how}")
    if report["accent_lowered_to_fit"]:
        print(f"  accent lowered to stay under the Windows ascent: {report['accent_lowered_to_fit']}")
    if report["outside_win_ascent_descent"]:
        print(f"  warning: outside the font's Windows ascent/descent (may be clipped): {report['outside_win_ascent_descent']}")
    print(f"  kern pairs added: {report['kern_pairs_added']}")


if __name__ == "__main__":
    main()
