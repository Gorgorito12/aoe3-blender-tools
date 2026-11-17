# SPDX-License-Identifier: GPL-3.0-or-later
"""The tools that write in place, or into a game copy, refuse a Steam library (a dry run only
reads, so it may look there). Plain Python.

    python -I tests/test_tools_refuse_steam.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ToolsRefuseSteam(unittest.TestCase):
    """The tools a form runs with one click and that write in place refuse a Steam library."""

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=ROOT, timeout=120)

    def test_in_place_fixes_and_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            steam = os.path.join(tmp, "SteamLibrary", "steamapps", "common", "AoE3")
            art = os.path.join(steam, "art", "units")
            os.makedirs(art)
            model = os.path.join(art, "x.gr2")
            with open(model, "wb") as fh:
                fh.write(b"\0" * 64)
            r = self.run_tool("tools/fix_bone_scale.py", model)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("Steam", r.stdout + r.stderr)
            anim = os.path.join(art, "x.xml")
            with open(anim, "w") as fh:
                fh.write("<animfile/>")
            r = self.run_tool("tools/fix_hitpointbar_tags.py", anim)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("Steam", r.stdout + r.stderr)
            r = self.run_tool("tools/fix_hitpointbar_tags.py", anim, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)              # a dry run only reads
            self.assertNotIn("refusing", r.stdout + r.stderr)
            r = self.run_tool("tools/make_icons.py", "--out", os.path.join(tmp, "icons"), "--install", steam)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(steam, "data")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
