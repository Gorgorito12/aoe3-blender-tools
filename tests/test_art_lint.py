# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/art_lint.py on a synthetic package (numpy, no Granny runtime).

    venv\\Scripts\\python -I tests/test_art_lint.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np  # noqa: E402
from aoe3game import ddt, gr2_write  # noqa: E402
import art_lint  # noqa: E402

QUAD = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]


def model(texture):
    return gr2_write.static_model("m", QUAD, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                  [(0, 1, 2), (0, 2, 3)], texture=texture, bump=texture)


def put(root, rel, data):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


LINT = {"allowed": [r"^mod\\units\\[a-z]+\\[^\\]+$"], "forbidden": [r"\\cavalry_ranged\\"],
        "converted": r"^mod\\units\\", "buildings": r"^mod\\buildings\\"}
RULES = {"rules": [{"name": "colour", "match": r"^mod\\units\\", "tuple": [0, 1, 8, 6], "max": 64}]}


class Lint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.pkg = os.path.join(t, "pkg")
        art = os.path.join(self.pkg, "art")
        pic = np.full((64, 64, 4), 128, np.uint8)
        good = ddt.write_dxt(pic, ddt.DXT3, alpha=1)        # (0,1,8,5): a chain to 4 px, 6 levels asked
        put(art, r"mod\units\a\a.ddt", good)
        put(art, r"mod\units\a\a.gr2", model(r"C:\art\mod\units\a\a.ddt"))
        put(art, r"mod\units\a\a.xml", "<animfile><component><assetreference type=\"GrannyModel\">"
                                       "<file>mod\\units\\a\\a</file><replacetexture><from>x</from><to>mod\\units\\a\\a</to>"
                                       "</replacetexture></assetreference></component>"
                                       "<!-- <replacetexture> in a comment is fine --></animfile>")
        put(art, r"mod\units\a\copy.ddt", good)                              # a duplicate
        put(art, r"mod\units\a\old.tga", b"x")                              # banned
        put(art, r"mod\cavalry_ranged\b\b.ddt", good)                        # layout
        put(art, r"mod\units\a\lost.xml", "<animfile><include>mod\\units\\a\\gone.xml</include></animfile>")
        self.lint = os.path.join(t, "lint.json")
        self.rules = os.path.join(t, "rules.json")
        put(t, "lint.json", json.dumps(LINT))
        put(t, "rules.json", json.dumps(RULES))

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = art_lint.main(["--package", self.pkg, "--lint", self.lint, "--textures", self.rules,
                                  "--out", os.path.join(self.tmp.name, "lint.txt")])
        text = buf.getvalue()
        self.assertEqual(code, 1)
        counts = {line.split()[0]: int(line.split()[1]) for line in text.splitlines()[1:11]
                  if line.split() and line.split()[0] in art_lint.CHECKS}
        self.assertEqual(counts["replacetexture"], 1)
        self.assertEqual(counts["banned"], 1)
        self.assertEqual(counts["layout"], 1)                              # the file under cavalry_ranged
        self.assertEqual(counts["duplicate"], 1)
        self.assertEqual(counts["unresolved"], 1)                          # the include found nowhere
        self.assertEqual(counts["unconverted"], 0)                         # written in the stock basis
        self.assertEqual(counts["textures"], 2)                            # 5 levels for 6 asked (two under its rule)

    def test_every_decal_texture_is_named(self):
        # a decal's <noncinematictexture> (the ring drawn outside cinematics) is a texture too: one
        # left on the source mod's path drew as a black square under a hero
        refs = art_lint.anim_refs("<animfile><component><decal><texture>a\\shadow</texture>"
                                  "<selectedtexture>a\\ring</selectedtexture>"
                                  "<noncinematictexture>a\\aura</noncinematictexture>"
                                  "</decal></component></animfile>")
        self.assertEqual({(k, role) for k, role, _att in refs},
                         {(r"a\shadow.ddt", "texture"), (r"a\ring.ddt", "texture"),
                          (r"a\aura.ddt", "texture")})

    def test_inherited_with_a_source(self):
        src = os.path.join(self.tmp.name, "source")
        os.makedirs(src)
        found, _n = art_lint.lint(self.pkg, LINT, None, [], [art_lint.hc_survey.Art(src)])
        self.assertEqual(len(found["unresolved"]), 1)                      # one of the package's own paths
        put(os.path.join(self.pkg, "art"), r"mod\units\a\lost.xml",
            "<animfile><include>stock\\gone.xml</include></animfile>")
        found, _n = art_lint.lint(self.pkg, LINT, None, [], [art_lint.hc_survey.Art(src)])
        self.assertEqual(len(found["unresolved"]), 0)
        self.assertEqual(len(found["inherited"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
