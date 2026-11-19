# SPDX-License-Identifier: GPL-3.0-or-later
"""Every screen of the studio in a real browser, in English and Spanish: no page error, no key
shown untranslated, nothing wider than the window. A studio is started on a throwaway
configuration; tests/studio_ui.mjs drives a headless Edge or Chrome.

    venv\\Scripts\\python -I tests\\test_studio_ui.py

Skipped without Node 22 or newer, or without Edge or Chrome.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import log, server  # noqa: E402
from studio.__main__ import BROWSERS  # noqa: E402

GAME_ROUTES = ("hud",)                   # drawn again with a synthetic game copy
ROUTES = ("buildings", "textures", "survey", "art", "jobs", "settings", "dev", "welcome", "inspect", "retex", "flags",
          "texmaker", "settlement", "buildtools", "results", "hud", "meshin", "tool/deploy", "tool/make_bar", "tool/fix_bone_scale", "tool/art_survey")


def node():
    exe = shutil.which("node")
    if not exe:
        return None
    try:
        major = int(subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
                    .lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return exe if major >= 22 else None


def browser():
    return next((b for b in BROWSERS if os.path.isfile(b) and "Chrome.app" not in b and "Edge.app" not in b), None)


@unittest.skipUnless(node() and browser(), "needs Node 22+ and Edge or Chrome")
class EveryScreen(unittest.TestCase):
    def run_routes(self, routes, game=False):
        """The routes in both languages through the headless browser; with `game`, a synthetic game
        copy in Settings (tests/hud_copy.py), for the screens that draw one."""
        with tempfile.TemporaryDirectory() as tmp:
            studio, httpd = server.serve(0, os.path.join(tmp, "home", "studio.json"))
            try:
                paths = {"work": os.path.join(tmp, "work")}
                if game:
                    sys.path.insert(0, os.path.join(ROOT, "tests"))
                    import hud_copy
                    paths["game"] = hud_copy.make(os.path.join(tmp, "game"))
                studio.settings.update({"paths": paths})
                r = subprocess.run([node(), os.path.join(ROOT, "tests", "studio_ui.mjs"), f"http://127.0.0.1:{studio.port}/",
                                    browser(), os.path.join(tmp, "profile"), ",".join(routes), "en,es"],
                                   capture_output=True, text=True, encoding="utf-8", timeout=600)
            finally:
                httpd.shutdown()
                httpd.server_close()
                log.close()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:] + r.stdout[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(len(out["report"]), 2 * len(routes))
        bad = []
        for row in out["report"]:
            where = f"{row['route']} ({row['lang_asked']})"
            if row["problems"]:
                bad.append(f"{where}: {row['problems']}")
            if row["untranslated"]:
                bad.append(f"{where}: keys shown untranslated {row['untranslated']}")
            if row["wide"]:
                bad.append(f"{where}: wider than the window")
            if not row["title"]:
                bad.append(f"{where}: no heading: the screen did not draw")
            if row["lang"] != row["lang_asked"]:
                bad.append(f"{where}: the page is in {row['lang']}")
        self.assertEqual(bad, [], chr(10).join(bad))

    def test_every_screen_in_both_languages(self):
        self.run_routes(ROUTES)

    def test_the_game_interface_draws_a_copy(self):
        self.run_routes(GAME_ROUTES, game=True)

if __name__ == "__main__":
    unittest.main(verbosity=1)
