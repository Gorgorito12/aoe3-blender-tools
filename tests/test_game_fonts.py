# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/game_fonts.py and aoe3game/uifonts.retarget: a game copy's fonts surveyed, extended and
deployed, on a copy made here (a synthetic font, no font of the game). The parts that build a font
need fontTools (pip install -r requirements-fonts.txt) and skip without it.

    venv/bin/python -I tests/test_game_fonts.py
"""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

from aoe3game import deploy, uifonts  # noqa: E402
import game_fonts  # noqa: E402
import hud_copy  # noqa: E402
import test_extend_font as tef  # noqa: E402

FONTS3 = ("﻿<?xml version=\"1.0\" encoding=\"UTF-16\"?>\r\n<Fonts>\r\n"
          "\t<Font Name=\"Menu 12\">\r\n\t\t<param TypeFace=\"Tiny Test\"/>\r\n\t\t<param AscentHeight=\"12\"/>\r\n"
          "\t\t<ResolutionOverride ResX=\"1280\"><param TypeFace='tiny test'/></ResolutionOverride>\r\n\t</Font>\r\n"
          "\t<Font Name=\"Plain 10\">\r\n\t\t<param TypeFace=\"Arial\"/>\r\n\t</Font>\r\n</Fonts>\r\n").encode("utf-16-le")


def digest(folder):
    out = {}
    for base, _d, files in os.walk(folder):
        for f in files:
            with open(os.path.join(base, f), "rb") as fh:
                out[os.path.relpath(os.path.join(base, f), folder)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def make_copy(folder, font_bytes):
    for sub in ("data", "art", "FONTS"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    with open(os.path.join(folder, "FONTS", "fonts3.xml"), "wb") as fh:
        fh.write(FONTS3)
    hud_copy.write_bar(os.path.join(folder, "FONTS", "Fonts.bar"), "Fonts\\", [("TINY_.TTF", font_bytes)])
    return folder


class Retarget(unittest.TestCase):
    def test_only_the_typefaces_asked_change_and_it_comes_back(self):
        data = FONTS3
        self.assertEqual(uifonts.faces(data), {"Tiny Test": 1, "tiny test": 1, "Arial": 1})
        new, n = uifonts.retarget(data, {"Tiny Test": "Tiny Test Mod"})
        self.assertEqual(n, 2)                                   # both cases, the override too
        self.assertEqual(uifonts.faces(new), {"Tiny Test Mod": 2, "Arial": 1})
        self.assertEqual(new[:2], data[:2])                      # the byte order mark kept
        text = new.decode("utf-16")
        self.assertEqual(text.count("\r\n"), data.decode("utf-16").count("\r\n"))
        self.assertIn("TypeFace='Tiny Test Mod'", text)          # its own quotes kept
        self.assertEqual(text.replace("Tiny Test Mod", "X"), data.decode("utf-16").replace("Tiny Test", "X").replace("tiny test", "X"))
        again, n2 = uifonts.retarget(new, {"Tiny Test": "Tiny Test Mod"})
        self.assertEqual((again, n2), (new, 0))
        back, _ = uifonts.retarget(new, {"Tiny Test Mod": "Tiny Test"})
        self.assertEqual(back.decode("utf-16").replace("'Tiny Test'", "'tiny test'"), data.decode("utf-16"))


class Survey(unittest.TestCase):
    def test_each_typeface_where_its_file_is_and_what_it_lacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_copy(tmp, hud_copy.ttf_with_name("Tiny Test"))  # no character map: it lacks every letter
            r = game_fonts.survey(tmp)
            rows = {row["typeface"].lower(): row for row in r["typefaces"]}
            self.assertEqual(rows["tiny test"]["where"], "Fonts.bar:Fonts\\TINY_.TTF")
            self.assertEqual(len(rows["tiny test"]["missing"]), len(game_fonts.scope()))
            self.assertIsNone(rows["arial"]["where"])           # a Windows font
            self.assertIsNone(rows["arial"]["missing"])
            # a loose font of the same family is found first, as the game reads it
            with open(os.path.join(tmp, "FONTS", "tiny_Mod.ttf"), "wb") as fh:
                fh.write(hud_copy.ttf_with_name("Tiny Test"))
            self.assertEqual(game_fonts.by_family(game_fonts.font_files(os.path.join(tmp, "FONTS")))["tiny test"]["where"],
                             "FONTS\\tiny_Mod.ttf")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(game_fonts.main(["survey", "--game", tmp]), 0)
            self.assertIn("a Windows font", buf.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(game_fonts.main(["survey", "--game", os.path.join(tmp, "data")]), 1)
                self.assertEqual(game_fonts.main(["nothing"]), 2)

    def test_the_names_of_the_new_files(self):
        self.assertEqual(game_fonts.new_name("TT1141M_.TTF", "WoL"), "TT1141M_WoL.TTF")
        self.assertEqual(game_fonts.new_name("framd.ttf", "WoL"), "framd_WoL.ttf")


@unittest.skipIf(tef.FontBuilder is None, "needs fontTools")
class Stage(unittest.TestCase):
    def font(self, tmp):
        path = os.path.join(tmp, "tiny.ttf")
        tef.build_font(path, family="Tiny Test")
        with open(path, "rb") as fh:
            return fh.read()

    def test_the_character_map_is_read_as_fonttools_reads_it(self):
        from fontTools.ttLib import TTFont
        with tempfile.TemporaryDirectory() as tmp:
            data = self.font(tmp)
            self.assertEqual(game_fonts.codepoints(data), set(TTFont(os.path.join(tmp, "tiny.ttf")).getBestCmap()))

    def test_staged_outside_the_copy_deployed_and_undone(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = make_copy(os.path.join(tmp, "copy"), self.font(tmp))
            before = digest(copy)
            out = os.path.join(tmp, "out")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = game_fonts.main(["stage", "--game", copy, "--out", out, "--suffix", "Mod", "--only", "ăășțȘȚ"])
            self.assertEqual(code, 0, buf.getvalue())
            self.assertEqual(digest(copy), before)                       # nothing written in the copy
            staged = os.path.join(out, "copy", "FONTS")
            with open(os.path.join(staged, "TINY_Mod.TTF"), "rb") as fh:
                font = fh.read()
            self.assertEqual(uifonts.ttf_names(font)["family"], "Tiny Test Mod")
            self.assertTrue({ord(c) for c in "ășțȘȚ"} <= game_fonts.codepoints(font))
            with open(os.path.join(staged, "fonts3.xml"), "rb") as fh:
                self.assertEqual(uifonts.faces(fh.read()), {"Tiny Test Mod": 2, "Arial": 1})
            self.assertTrue(os.path.isfile(os.path.join(out, "report-TINY_Mod.json")))
            self.assertIn("Arial: no file in the copy", buf.getvalue())
            # deployed as any folder laid out as the copy, then undone byte for byte
            d = deploy.Deployment(copy)
            written = d.add_files(os.path.join(out, "copy"), log=lambda s: None)
            self.assertEqual(sorted(written), [os.path.join("FONTS", "TINY_Mod.TTF"), os.path.join("FONTS", "fonts3.xml")])
            r = game_fonts.survey(copy)
            self.assertEqual([row["typeface"] for row in r["typefaces"]][:1], ["Tiny Test Mod"])
            self.assertEqual(r["typefaces"][0]["where"], "FONTS\\TINY_Mod.TTF")
            # staged again with the extended font in: it is already extended, nothing to add
            s = game_fonts.stage(copy, os.path.join(tmp, "out2"), "Mod", only="ăășțȘȚ", log=lambda m: None)
            self.assertEqual(s["fonts"], [])
            self.assertIn("already an extended font", [k["why"] for k in s["skipped"]])
            d.undo(log=lambda s: None)
            self.assertEqual(digest(copy), before)

    def test_what_it_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = make_copy(os.path.join(tmp, "copy"), self.font(tmp))
            for args, why in ((["--out", os.path.join(copy, "x"), "--suffix", "Mod"], "outside the game copy"),
                              (["--out", os.path.join(tmp, "o"), "--suffix", "bad word"], "--suffix"),
                              (["--out", os.path.join(tmp, "steamapps", "o"), "--suffix", "Mod"], "Steam")):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(game_fonts.main(["stage", "--game", copy] + args), 1)
                self.assertIn(why, buf.getvalue())


try:
    import numpy  # noqa: F401  (the interface screen draws textures with it)
except ImportError:
    numpy = None


@unittest.skipIf(numpy is None, "needs numpy")
class Screen(unittest.TestCase):
    def test_the_interface_screen_finds_a_loose_font_first(self):
        from studio import hud
        with tempfile.TemporaryDirectory() as tmp:
            hud_copy.make(tmp)
            loose = hud_copy.ttf_with_name("Test Face")
            with open(os.path.join(tmp, "FONTS", "test_Mod.ttf"), "wb") as fh:
                fh.write(loose)
            g = hud.Game(tmp)
            self.assertEqual(g.font_where("Test Face"), "FONTS\\test_Mod.ttf")
            self.assertEqual(g.font_file("test face"), loose)
            self.assertIsNone(g.font_where("Arial"))


if __name__ == "__main__":
    unittest.main()
