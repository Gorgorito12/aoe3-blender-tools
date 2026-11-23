# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/dmg_bones.py's fix mode (the <definebone> lines it adds), on synthetic anim files only. Plain
Python:

    python -I tests/test_dmg_bones.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dmg_bones  # noqa: E402
import xmbedit  # noqa: E402

SORTED = ("<animfile>\r\n"
          "\t<definebone>bone_debris_1A</definebone>\r\n"
          "\t<definebone>bone_debris_1B</definebone>\r\n"
          "\t<definebone>bone_debris_2A</definebone>\r\n"
          "\t<!-- <definebone>bone_debris_9z</definebone> -->\r\n"
          "\t<component>x</component>\r\n"
          "</animfile>\r\n")


class TextFix(unittest.TestCase):
    def test_sorted_places_and_copies_the_line(self):
        text, added = dmg_bones.add_definebones_text(SORTED, ["bone_debris_1c", "bone_debris_0a", "bone_debris_3a"])
        self.assertEqual(added, ["bone_debris_0a", "bone_debris_1c", "bone_debris_3a"])
        self.assertEqual(text.splitlines(), [
            "<animfile>",
            "\t<definebone>bone_debris_0a</definebone>",
            "\t<definebone>bone_debris_1A</definebone>",
            "\t<definebone>bone_debris_1B</definebone>",
            "\t<definebone>bone_debris_1c</definebone>",
            "\t<definebone>bone_debris_2A</definebone>",
            "\t<definebone>bone_debris_3a</definebone>",
            "\t<!-- <definebone>bone_debris_9z</definebone> -->",
            "\t<component>x</component>",
            "</animfile>"])
        self.assertNotIn("\n", text.replace("\r\n", ""))  # CRLF kept

    def test_defined_names_ignore_case_and_comments_do_not_count(self):
        text, added = dmg_bones.add_definebones_text(SORTED, ["BONE_DEBRIS_1a", "bone_debris_9z"])
        self.assertEqual(added, ["bone_debris_9z"])
        self.assertEqual(text.count("bone_debris_9z"), 2)

    def test_nothing_to_add_leaves_the_text(self):
        self.assertEqual(dmg_bones.add_definebones_text(SORTED, ["bone_debris_2a"]), (SORTED, []))

    def test_unsorted_goes_after_the_last(self):
        src = "<animfile>\n  <definebone>zeta</definebone>\n  <definebone>alpha</definebone>\n  <x/>\n</animfile>\n"
        text, _ = dmg_bones.add_definebones_text(src, ["mid"])
        self.assertEqual(text.splitlines()[1:4], ["  <definebone>zeta</definebone>",
                                                  "  <definebone>alpha</definebone>",
                                                  "  <definebone>mid</definebone>"])

    def test_no_definebone_yet(self):
        src = "<!-- c -->\n\n<animfile>\n\t<submodel>a</submodel>\n</animfile>\n"
        text, added = dmg_bones.add_definebones_text(src, ["b2", "b1"])
        self.assertEqual(added, ["b1", "b2"])
        self.assertEqual(text, "<!-- c -->\n\n<animfile>\n\t<definebone>b1</definebone>\n"
                               "\t<definebone>b2</definebone>\n\t<submodel>a</submodel>\n</animfile>\n")

    def test_encoding_round_trip(self):
        for raw in (b"\xef\xbb\xbf<a/>\r\n", "<a>é</a>".encode("cp1252"), "﻿<a/>".encode("utf-16-le")):
            text, enc, bom = dmg_bones.decode_text(raw)
            self.assertEqual(bom + text.encode(enc), raw)


class XmbFix(unittest.TestCase):
    def xmb(self, text, compress):
        inner = xmbedit.encode(*xmbedit.from_xml(text.encode("utf-8")))
        return xmbedit.wrap(inner, compress)

    def test_nodes_added_in_order_rest_unchanged(self):
        src = ("<animfile>\n<definebone>b_1a</definebone>\n<definebone>b_2a</definebone>\n"
               "<component>x</component>\n</animfile>\n")
        for compress in (False, True):
            raw = self.xmb(src, compress)
            out, added = dmg_bones.add_definebones_xmb(raw, ["b_3a", "b_1b", "b_1c", "b_0a"])
            self.assertEqual(added, ["b_0a", "b_1b", "b_1c", "b_3a"])
            self.assertEqual(xmbedit.is_compressed(out), compress)
            elems, _attrs, root = xmbedit.parse(xmbedit.decode(out))
            self.assertEqual([(elems[c.name], c.text) for c in root.children],
                             [("definebone", "b_0a"), ("definebone", "b_1a"), ("definebone", "b_1b"),
                              ("definebone", "b_1c"), ("definebone", "b_2a"), ("definebone", "b_3a"),
                              ("component", "x")])

    def test_no_definebone_yet(self):
        raw = self.xmb("<animfile>\n<component>x</component>\n</animfile>\n", False)
        out, added = dmg_bones.add_definebones_xmb(raw, ["b"])
        elems, _attrs, root = xmbedit.parse(xmbedit.decode(out))
        self.assertEqual([(elems[c.name], c.text) for c in root.children], [("definebone", "b"), ("component", "x")])


if __name__ == "__main__":
    unittest.main(verbosity=1)
