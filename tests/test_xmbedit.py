# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/xmbedit.py on synthetic files (no game data). Plain Python:

    python -I tests/test_xmbedit.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import xmbedit  # noqa: E402

# An impact effect laid out as the stock ones are: blank lines and comments between the types, so
# the stored line numbers have gaps, and a custom type at the end.
IMPACT = b"""<?xml version="1.0" encoding="utf-8"?>
<!-- comment -->

<ImpactEffect meterCount="5" meterLength="1.0">

   <Wood fireExistTime="4500">
      <ParticleSet>cannonball_impact_wood</ParticleSet>
      <SoundSet>CannonImpactWood</SoundSet>
   </Wood>


   <Stone><ParticleSet weight="2">cannonball_impact_stone</ParticleSet><SoundSet>Explosion</SoundSet></Stone>
   <ShipMetal>
      <ParticleSet>cannonball_impact_water</ParticleSet>
      <SoundSet>MeleeImpactMetal</SoundSet>
   </ShipMetal>
</ImpactEffect>
"""


def compile_xml(data):
    return xmbedit.encode(*xmbedit.from_xml(data))


def read(path):
    with open(path, "rb") as f:
        return f.read()


def lines_of(root):
    out = [root.line]
    for child in root.children:
        out += lines_of(child)
    return out


class XmbTextRoundTrip(unittest.TestCase):
    def test_impact_effect_round_trip_is_byte_identical(self):
        inner = compile_xml(IMPACT)
        elems, attrs, root = xmbedit.parse(inner)
        self.assertEqual(elems[:3], ["impacteffect", "wood", "particleset"])
        self.assertIn("shipmetal", elems)
        self.assertEqual(xmbedit.xml_round_trip(elems, attrs, root), inner)

    def test_line_numbers_survive_the_text(self):
        elems, attrs, root = xmbedit.parse(compile_xml(IMPACT))
        self.assertEqual(lines_of(root)[:5], [4, 6, 7, 8, 12])
        text = xmbedit.to_xml(elems, attrs, root)
        _, _, again = xmbedit.from_xml(text.encode("utf-8"))
        self.assertEqual(lines_of(again), lines_of(root))
        # Three elements stored on line 12 come back on one line.
        self.assertEqual(text.splitlines()[11].count("<particleset"), 1)
        self.assertIn("<soundset>Explosion</soundset>", text.splitlines()[11])

    def test_line_break_in_a_text_keeps_later_lines(self):
        elems, attrs, root = xmbedit.parse(compile_xml(b"<a>\n<b>x</b>\n<c>y</c>\n</a>"))
        root.children[0].text = "two\nlines"
        inner = xmbedit.encode(elems, attrs, root)
        self.assertEqual(xmbedit.xml_round_trip(elems, attrs, root), inner)

    def test_root_on_the_first_line(self):
        inner = compile_xml(b"<a><b>1</b><c>2</c></a>")
        self.assertEqual(xmbedit.xml_round_trip(*xmbedit.parse(inner)), inner)

    def test_default_names(self):
        self.assertEqual(xmbedit.default_xmb_name("cannon.impacteffect"), "cannon.impacteffect.xmb")
        self.assertEqual(xmbedit.default_xmb_name("cannon.impacteffect.xml"), "cannon.impacteffect.xmb")
        self.assertEqual(xmbedit.default_xmb_name("protoy.xml"), "protoy.xml.xmb")
        self.assertEqual(xmbedit.default_xmb_name("explorer.tactics"), "explorer.tactics.xmb")
        self.assertEqual(xmbedit.default_xml_name("cannon.impacteffect.xmb"), "cannon.impacteffect")
        self.assertEqual(xmbedit.default_xml_name("protoy.xml.XMB"), "protoy.xml")


class XmbCommandLine(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "xmbedit.py"), *args],
                              capture_output=True, text=True)

    def test_compile_decompile_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "cannon.impacteffect")
            with open(src, "wb") as f:
                f.write(IMPACT)
            self.assertEqual(self.run_tool("from-xml", src).returncode, 0)
            xmb = src + ".xmb"
            first = read(xmb)
            self.assertEqual(first[:2], b"X1")          # plain, as the stock impact effects
            os.remove(src)
            self.assertEqual(self.run_tool("to-xml", xmb).returncode, 0)
            self.assertTrue(os.path.exists(src))
            os.remove(xmb)
            self.assertEqual(self.run_tool("from-xml", src).returncode, 0)
            self.assertEqual(read(xmb), first)
            check = self.run_tool("check", xmb)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("through to-xml and from-xml: identical", check.stdout)

    def test_compressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.xml")
            with open(src, "wb") as f:
                f.write(IMPACT)
            out = os.path.join(tmp, "b.xmb")
            self.assertEqual(self.run_tool("from-xml", src, out, "--compress").returncode, 0)
            self.assertEqual(read(out)[:4], b"l33t")
            self.assertEqual(self.run_tool("check", out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
