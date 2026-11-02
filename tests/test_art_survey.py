# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/art_survey.py on synthetic files (no game data). Plain Python:

    python -I tests/test_art_survey.py
"""
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import art_survey  # noqa: E402
import xmbedit  # noqa: E402

ANIM = b"""<?xml version="1.0" encoding="utf-8"?>
<animfile>
  <definebone>bone_flag</definebone>
  <attachment>
    <component>
      <assetreference type="GrannyModel"><file>units\\foo\\foo.gr2</file></assetreference>
    </component>
  </attachment>
  <anim>Idle
    <assetreference type="GrannyAnim"><file>units\\shared\\idle.gr2</file></assetreference>
  </anim>
  <logic type="Variation"><component>Default</component></logic>
</animfile>
"""

BUILDING = b"""<animfile><anim>Bored<assetreference type="GrannyModel"><file>buildings\\bar\\bar.gr2</file>
</assetreference></anim><attachpoint name="hotspot_flag"/></animfile>"""


def ddt(width, height, fmt=1, alpha=8):
    return b"RTS3" + bytes([0, alpha, fmt, 5]) + struct.pack("<II", width, height) + b"\0" * 32


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def make_bar(path, files):
    """A minimal legacy archive in the layout tools/bar.py reads."""
    head = bytearray(0x124)
    head[:4] = b"ESPN"
    body = b""
    entries = []
    for name, data in files:
        entries.append((name, 0x124 + len(body), len(data)))
        body += data
    table = struct.pack("<I", 4) + "Art\\".encode("utf-16-le") + struct.pack("<I", len(entries))
    for name, off, size in entries:
        table += struct.pack("<III", off, size, size) + b"\0" * 16
        table += struct.pack("<I", len(name)) + name.encode("utf-16-le")
    struct.pack_into("<II", head, 0x118, len(entries), 0x124 + len(body))
    write(path, bytes(head) + body + table)


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.base = os.path.join(t, "base")
        self.mod = os.path.join(t, "mod")
        write(os.path.join(self.base, "art", "units", "shared", "idle.gr2"), b"GR2FAKE" * 4)
        make_bar(os.path.join(self.base, "art", "art.bar"),
                 [("units\\stock\\stock.xml", BUILDING), ("units\\stock\\stock.ddt", ddt(1024, 1024))])
        write(os.path.join(self.mod, "art", "units", "foo", "foo.xml"), ANIM)
        write(os.path.join(self.mod, "art", "units", "foo", "foo.gr2"), b"GR2FAKE" * 4)
        write(os.path.join(self.mod, "art", "units", "foo", "foo.ddt"), ddt(512, 256))
        elems, attrs, root = xmbedit.from_xml(BUILDING)
        xmb = xmbedit.wrap(xmbedit.encode(elems, attrs, root), True)
        write(os.path.join(self.mod, "art", "buildings", "bar", "bar.xml.xmb"), xmb)
        write(os.path.join(self.mod, "art", "buildings", "bar", "broken.xml"), b"<animfile><oops></animfile>")

    def tearDown(self):
        self.tmp.cleanup()

    def test_base_with_bar(self):
        rep = art_survey.survey([self.base], use_bar=True)
        self.assertEqual(rep["counts"], {"model": 1, "texture": 1, "anim": 1})
        tex = next(iter(rep["files"]["texture"].values()))
        self.assertEqual((tex["width"], tex["height"], tex["magic"]), (1024, 1024, "RTS3"))
        self.assertIn(("hotspot_flag", 1), [tuple(x) for x in rep["attach_points"]])

    def test_mod_against_reference(self):
        out = os.path.join(self.tmp.name, "out")
        self.assertEqual(art_survey.main([self.base, "--bar", "--out", out + "_base"]), 0)
        code = art_survey.main([self.mod, "--out", out, "--reference", os.path.join(out + "_base", "report.json"),
                                "--label", "TestMod"])
        self.assertEqual(code, 0)
        with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["label"], "TestMod")
        self.assertEqual(rep["counts"]["anim"], 2)               # the XML and the compressed XMB
        self.assertEqual(len(rep["errors"]), 1)                  # broken.xml is reported, not fatal
        foo = next(v for k, v in rep["per_anim"].items() if k.endswith("foo.xml"))
        self.assertEqual((foo["own"], foo["reference"], foo["unresolved"]), (1, 1, 0))
        self.assertEqual(foo["category"], "units")
        bar_anim = next(v for k, v in rep["per_anim"].items() if k.endswith("bar.xml.xmb"))
        self.assertEqual(bar_anim["unresolved"], 1)              # bar.gr2 exists nowhere
        self.assertEqual(rep["anim_categories"], {"units": 1, "buildings": 1})
        self.assertIn(["Idle", 1], rep["anim_names"])
        self.assertIn(["bone_flag", 1], rep["attach_points"])
        self.assertIn(["Variation", 1], rep["logic_types"])
        tex = next(iter(rep["files"]["texture"].values()))
        self.assertEqual((tex["width"], tex["height"]), (512, 256))
        with open(os.path.join(out, "summary.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("| only their own files | 0 |", md)
        self.assertIn("| both | 1 |", md)

    def test_usage_without_out(self):
        self.assertEqual(art_survey.main([self.mod]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
