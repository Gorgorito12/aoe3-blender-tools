# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/extend_font.py on a tiny font built here with fontTools (no game or third-party font):

    venv\\Scripts\\python -I tests/test_extend_font.py

Skipped when fontTools is not installed (pip install -r requirements-fonts.txt).
"""
import io
import contextlib
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

try:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent
except ImportError:
    FontBuilder = None

import extend_font  # noqa: E402

UPM = 1000
XH, CAP, ASC = 500, 700, 750


def rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x0, y1))
    pen.lineTo((x1, y1))
    pen.lineTo((x1, y0))
    pen.closePath()


def shapes():
    """Block letters: enough of them for every recipe of the tool. name -> (advance, [rects])"""
    stem = 80
    return {
        ".notdef": (500, [(50, 0, 450, 700)]),
        "space": (250, []),
        "A": (600, [(40, 0, 40 + stem, CAP), (480, 0, 560, CAP), (40, 300, 560, 380), (40, CAP - 80, 560, CAP)]),
        "H": (600, [(40, 0, 40 + stem, CAP), (480, 0, 560, CAP), (40, 300, 560, 380)]),
        "I": (240, [(80, 0, 160, CAP)]),
        "J": (400, [(260, 0, 340, CAP), (40, 0, 340, 80)]),
        "L": (500, [(40, 0, 120, CAP), (40, 0, 460, 80)]),
        "S": (560, [(40, 0, 520, 80), (40, 310, 520, 390), (40, 620, 520, 700), (40, 310, 120, 700), (440, 0, 520, 390)]),
        "T": (560, [(240, 0, 320, CAP), (20, 620, 540, 700)]),
        "a": (520, [(40, 0, 480, 80), (400, 0, 480, XH), (40, 0, 120, 260), (40, 420, 480, XH)]),
        "d": (520, [(40, 0, 480, 80), (400, 0, 480, ASC), (40, 0, 120, XH), (40, 420, 480, XH)]),
        "e": (520, [(40, 0, 480, 80), (40, 0, 120, XH), (40, 420, 480, XH), (40, 210, 480, 290)]),
        "h": (520, [(40, 0, 120, ASC), (400, 0, 480, XH), (40, 420, 480, XH)]),
        "i": (200, [(60, 0, 140, XH), (60, 580, 140, 660)]),
        "j": (200, [(60, -200, 140, XH), (60, 580, 140, 660)]),
        "l": (200, [(60, 0, 140, ASC)]),
        "n": (520, [(40, 0, 120, XH), (400, 0, 480, XH), (40, 420, 480, XH)]),
        "s": (480, [(40, 0, 440, 70), (40, 215, 440, 285), (40, 430, 440, XH), (40, 215, 110, XH), (370, 0, 440, 285)]),
        "t": (360, [(120, 0, 200, 650), (20, 420, 340, XH)]),
        "x": (480, [(40, 0, 440, XH)]),
        "o": (520, [(40, 0, 480, 80), (40, 420, 480, XH), (40, 0, 120, XH), (400, 0, 480, XH)]),
        "u": (520, [(40, 0, 480, 80), (40, 0, 120, XH), (400, 0, 480, XH)]),
        "g": (520, [(40, -200, 480, -120), (400, -200, 480, XH), (40, 420, 480, XH)]),
        "dotlessi": (200, [(60, 0, 140, XH)]),
        "comma": (250, [(80, -150, 150, 90)]),
        "period": (250, [(80, 0, 160, 80)]),
        "hyphen": (300, [(40, 210, 260, 290)]),
        "quoteright": (250, [(80, 520, 150, 740)]),
        "periodcentered": (250, [(80, 260, 160, 340)]),
        "acute": (300, [(110, 560, 190, 680)]),
        "grave": (300, [(110, 560, 190, 680)]),
        "circumflex": (300, [(60, 560, 240, 640)]),
        "cedilla": (300, [(110, -180, 190, 0)]),
        "breve": (300, [(60, 560, 240, 620)]),
    }


UNICODES = {".notdef": None, "space": 0x20, "comma": 0x2C, "period": 0x2E, "hyphen": 0x2D, "quoteright": 0x2019,
            "periodcentered": 0xB7, "acute": 0xB4, "grave": 0x60, "circumflex": 0x2C6, "cedilla": 0xB8,
            "breve": 0x2D8, "dotlessi": 0x131}


def build_font(path, with_composites=True, with_kern=True, with_hdmx=True, family="Tiny Test"):
    glyphs, metrics, cmap, order = {}, {}, {}, []
    for name, (adv, rects) in shapes().items():
        pen = TTGlyphPen(None)
        for r in rects:
            rect(pen, *r)
        glyphs[name] = pen.glyph()
        metrics[name] = (adv, min((r[0] for r in rects), default=0))
        order.append(name)
        cp = UNICODES.get(name, ord(name) if len(name) == 1 else None)
        if cp:
            cmap[cp] = name
    if with_composites:  # Á and á: what the tool learns the accent height from (capitals 200 higher)
        for name, base, cp, dy in (("Aacute", "A", 0xC1, 200), ("aacute", "a", 0xE1, 0), ("Scedilla", "S", 0x15E, 0)):
            g = Glyph()
            g.numberOfContours = -1
            mark = "cedilla" if cp == 0x15E else "acute"
            c0, c1 = GlyphComponent(), GlyphComponent()
            c0.glyphName, c0.x, c0.y, c0.flags = base, 0, 0, 0x4
            c1.glyphName, c1.x, c1.y, c1.flags = mark, 150, dy, 0x4
            g.components = [c0, c1]
            glyphs[name] = g
            metrics[name] = (shapes()[base][0], 40)
            order.append(name)
            cmap[cp] = name
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=900, descent=-250)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(usWinAscent=900, usWinDescent=250, sTypoAscender=750, sTypoDescender=-250)
    fb.setupPost()
    if with_kern:
        kern = newTable("kern")
        kern.version = 0
        from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0
        sub = KernTable_format_0()
        sub.version, sub.coverage, sub.format = 0, 1, 0
        sub.kernTable = {("T", "a"): -60, ("L", "T"): -80, ("a", "T"): -40}
        kern.kernTables = [sub]
        fb.font["kern"] = kern
    fb.save(path)
    if with_hdmx:  # device widths, one per glyph and size: the tool must extend them
        font = TTFont(path)
        hdmx = newTable("hdmx")
        hdmx.hdmx = {12: {n: round(font["hmtx"][n][0] * 12 / UPM) for n in font.getGlyphOrder()}}
        font["hdmx"] = hdmx
        font.save(path)


def bounds(font, name):
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


@unittest.skipIf(FontBuilder is None, "fontTools is not installed")
class ExtendFont(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "tiny.ttf")
        self.out = os.path.join(self.tmp.name, "tiny-ext.ttf")
        build_font(self.src)
        with contextlib.redirect_stdout(io.StringIO()):
            self.report = extend_font.extend(self.src, self.out, family="Tiny Test Plus")
        self.font = TTFont(self.out)
        self.cmap = self.font.getBestCmap()

    def tearDown(self):
        self.tmp.cleanup()

    def comps(self, cp):
        g = self.font["glyf"][self.cmap[cp]]
        self.assertTrue(g.isComposite(), chr(cp))
        return [(c.glyphName, c.x, c.y) for c in g.components]

    def test_romanian_letters_are_composites_of_the_fonts_own_parts(self):
        for cp in (0x102, 0x103, 0x218, 0x219, 0x21A, 0x21B):
            self.assertIn(cp, self.cmap, chr(cp))
        self.assertEqual(self.comps(0x103)[0][0], "a")
        self.assertEqual(self.comps(0x103)[1][0], "breve")
        self.assertEqual(self.comps(0x219)[0][0], "s")

    def test_capital_accent_height_is_learnt_from_the_font(self):
        # Á puts its acute 200 higher than á: Ă and Ŭ... get their breve as high
        self.assertEqual(self.comps(0x102)[1][2], 200)
        self.assertEqual(self.comps(0x103)[1][2], 0)

    def test_accent_over_an_ascender_is_raised(self):
        y_l = bounds(self.font, self.cmap[0x13A])[3]  # ĺ
        self.assertGreater(y_l, ASC)

    def test_comma_below_hangs_under_the_baseline(self):
        mark = self.comps(0x219)[1][0]
        b = bounds(self.font, mark)
        self.assertLess(b[3], 0)
        self.assertGreaterEqual(b[1], -250)

    def test_advance_is_the_base_letters(self):
        hmtx = self.font["hmtx"]
        for cp, base in ((0x103, "a"), (0x218, "S"), (0x21B, "t"), (0x102, "A")):
            self.assertEqual(hmtx[self.cmap[cp]][0], hmtx[base][0], chr(cp))

    def test_apostrophe_caron_sits_right_of_the_stem_and_widens_the_letter(self):
        hmtx = self.font["hmtx"]
        d_caron = self.comps(0x10F)
        self.assertEqual(d_caron[0][0], "d")
        mark_box = bounds(self.font, d_caron[1][0])
        self.assertGreater(d_caron[1][1] + mark_box[0], 480)  # right of d's stem
        self.assertGreater(hmtx[self.cmap[0x10F]][0], hmtx["d"][0])

    def test_existing_glyphs_are_untouched(self):
        before = TTFont(self.src)
        for name in before.getGlyphOrder():
            self.assertEqual(before["glyf"][name].compile(before["glyf"]),
                             self.font["glyf"][name].compile(self.font["glyf"]), name)
            self.assertEqual(before["hmtx"][name], self.font["hmtx"][name], name)
            self.assertEqual(before["hdmx"].hdmx[12][name], self.font["hdmx"].hdmx[12][name], name)

    def test_family_is_renamed(self):
        self.assertEqual(self.font["name"].getDebugName(1), "Tiny Test Plus")
        self.assertNotIn("Tiny Test Regular", [r.toUnicode() for r in self.font["name"].names if r.nameID == 4])

    def test_os2_reports_the_new_ranges(self):
        os2 = self.font["OS/2"]
        self.assertTrue(os2.ulUnicodeRange1 & (1 << 2))  # Latin Extended-A
        self.assertTrue(os2.ulUnicodeRange1 & (1 << 3))  # Latin Extended-B (U+0218)
        self.assertGreaterEqual(os2.usLastCharIndex, 0x21B)

    def test_kerning_follows_the_base_letter(self):
        kt = self.font["kern"].kernTables[0].kernTable
        self.assertEqual(kt.get((self.cmap[0x21A], "a")), -60)  # Ț a, like T a
        self.assertEqual(kt.get(("a", self.cmap[0x21A])), -40)
        self.assertNotIn((self.cmap[0x13D], "T"), kt)  # Ľ keeps no L-T pair: its apostrophe would collide

    def test_hdmx_covers_every_glyph(self):
        widths = self.font["hdmx"].hdmx[12]
        for name in self.font.getGlyphOrder():
            self.assertIn(name, widths)

    def test_missing_marks_are_made_and_reported(self):
        made = self.report["marks_made"]
        for mark in ("commabelow", "ogonek", "hungarumlaut", "caron", "dieresis", "dotaccent", "ring", "macron"):
            self.assertIn(mark, made)
        self.assertIn("ő", self.report["added"])

    def test_letters_without_parts_are_listed(self):
        for ch in "ĸŋſ":
            self.assertIn(ch, self.report["not_built"])

    def test_dotless_j_is_made_for_j_circumflex(self):
        parts = self.comps(0x135)
        base = parts[0][0]
        self.assertLess(bounds(self.font, base)[3], 580)  # the dot is gone

    def test_bars_and_pairs(self):
        self.assertEqual(len(self.comps(0x126)), 2)  # Ħ: H and a bar
        hmtx = self.font["hmtx"]
        self.assertEqual(hmtx[self.cmap[0x133]][0], hmtx["i"][0] + hmtx["j"][0])  # ĳ

    def test_second_run_adds_nothing(self):
        again = os.path.join(self.tmp.name, "again.ttf")
        with contextlib.redirect_stdout(io.StringIO()):
            report = extend_font.extend(self.out, again, family="Tiny Test Plus")
        self.assertEqual(report["added"], "")

    def test_only_limits_the_scope(self):
        out = os.path.join(self.tmp.name, "only.ttf")
        with contextlib.redirect_stdout(io.StringIO()):
            report = extend_font.extend(self.src, out, only=extend_font.parse_letters("ăș,U+021A-U+021B"))
        self.assertEqual(report["added"], "ășȚț")
        self.assertEqual(TTFont(out)["name"].getDebugName(1), "Tiny Test Ext")

    def test_identical_letter_is_shared(self):
        # Ş exists as S + cedilla at the place the tool would choose for Ţ's base S: building Ş again
        # would give the same parts, so a code point asking for it maps to the existing glyph
        ex = extend_font.Extender(TTFont(self.src), {})
        name, why = ex.build_marked(0x15E, ord("S"), 0x0327)
        self.assertEqual(name, "Scedilla")

    def test_proof_sheet(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")
        sheet = os.path.join(self.tmp.name, "proof.png")
        extend_font.proof(self.out, sheet, self.report["added"])
        self.assertGreater(os.path.getsize(sheet), 1000)

    def test_command_line_refuses_to_overwrite_its_input(self):
        with self.assertRaises(SystemExit):
            extend_font.main([self.src, self.src])

    def test_command_line_refuses_a_steam_library(self):
        steam = os.path.join(self.tmp.name, "steamapps", "common", "game", "FONTS", "x.ttf")
        with self.assertRaises(SystemExit) as caught:
            extend_font.main([self.src, steam])
        self.assertIn("Steam", str(caught.exception))
        self.assertFalse(os.path.exists(steam))

    def test_command_line_prints_the_report(self):
        out = os.path.join(self.tmp.name, "cli.ttf")
        report = os.path.join(self.tmp.name, "cli.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            extend_font.main([self.src, out, "--suffix", "Plus", "--report", report, "--only", "ș"])
        self.assertIn("added 1: ș", buf.getvalue())
        self.assertEqual(TTFont(out)["name"].getDebugName(1), "Tiny Test Plus")
        self.assertTrue(os.path.exists(report))


if __name__ == "__main__":
    unittest.main(verbosity=2)
