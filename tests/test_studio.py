# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the studio (studio/): its API and its safety, the forms drawn from core/schema.py and
studio/catalog.py, the two languages, and the jobs. No Blender, no browser, no network.

    venv\\Scripts\\python -I tests\\test_studio.py        (numpy: the building previews)
"""
import ast
import dataclasses
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import catalog, engine, jobs, server, settings  # noqa: E402
from core import building, schema  # noqa: E402  (studio puts core on the path, as the tools do)

WEB = os.path.join(ROOT, "studio", "web")


def load_json(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as fh:
        return json.load(fh)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = os.path.join(cls.tmp.name, "home", "studio.json")
        cls.studio, cls.httpd = server.serve(0, cls.config)
        cls.studio.settings.update({"paths": {"work": os.path.join(cls.tmp.name, "work")}})
        cls.base = f"http://127.0.0.1:{cls.studio.port}"

    @classmethod
    def tearDownClass(cls):
        from studio import log
        cls.studio.jobs.stop_all()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        log.close()
        cls.tmp.cleanup()

    def call(self, path, body=None, token=None, headers=None):
        h = {"X-Studio-Token": self.studio.token if token is None else token, "Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                return r.status, (json.loads(data) if "json" in r.headers.get("Content-Type", "") else data)
        except urllib.error.HTTPError as e:
            data = e.read()
            try:
                return e.code, json.loads(data)
            except ValueError:
                return e.code, data

    def wait(self, jid, seconds=60):
        end = time.time() + seconds
        while time.time() < end:
            _, j = self.call(f"/api/jobs/{jid}")
            if j["status"] not in ("queued", "running"):
                return j
            time.sleep(0.2)
        self.fail(f"job {jid} still running")

    # -- safety ----------------------------------------------------------------------------
    def test_the_api_needs_the_token_and_this_host(self):
        self.assertEqual(self.call("/api/state", token="wrong")[0], 403)
        self.assertEqual(self.call("/api/state", token="")[0], 403)
        self.assertEqual(self.call("/api/state", headers={"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.call("/api/state", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/state")[0], 200)

    def test_the_page_carries_the_token_and_a_strict_policy(self):
        with urllib.request.urlopen(self.base + "/") as r:
            html = r.read().decode()
            csp = r.headers["Content-Security-Policy"]
        self.assertIn(self.studio.token, html)
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("{{TOKEN}}", html)
        for bad in ("/../studio/server.py", "/%2e%2e/studio/server.py", "/..%5cserver.py"):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(self.base + bad)

    def test_settings_refuse_steam_and_missing_folders(self):
        steam = os.path.join(self.tmp.name, "Steam", "steamapps", "common", "AoE3")
        os.makedirs(steam)
        status, err = self.call("/api/settings", {"paths": {"test_copy": steam}})
        self.assertEqual(status, 400, err)
        self.assertIn("Steam", err["error"])
        status, err = self.call("/api/settings", {"paths": {"game": os.path.join(self.tmp.name, "nope")}})
        self.assertEqual(status, 400)
        status, err = self.call("/api/settings", {"paths": {"nonsense": "x"}})
        self.assertEqual(status, 400)
        status, st = self.call("/api/settings", {"language": "es"})
        self.assertEqual((status, st["settings"]["language"]), (200, "es"))
        with open(self.config, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["language"], "es")

    def test_outputs_are_refused_inside_the_game(self):
        game = os.path.join(self.tmp.name, "game")
        os.makedirs(game, exist_ok=True)
        self.studio.settings.update({"paths": {"game": game}})
        try:
            status, err = self.call("/api/tools/make_rings", {"values": {"out": os.path.join(game, "rings")}})
            self.assertEqual(status, 400, err)
            self.assertIn("game", err["error"])
        finally:
            self.studio.settings.update({"paths": {"game": ""}})

    def test_files_outside_the_outputs_are_not_shown(self):
        status, _ = self.call("/api/file?path=" + urllib.request.quote(os.path.join(ROOT, "README.md")))
        self.assertEqual(status, 403)
        status, _ = self.call("/api/list?path=" + urllib.request.quote(ROOT))
        self.assertEqual(status, 403)

    def test_a_trial_comes_before_apply(self):
        values = {"inputs": [os.path.join(self.tmp.name, "none.gr2")]}
        status, err = self.call("/api/tools/fix_bone_scale", {"values": values, "apply": True})
        self.assertEqual(status, 400)
        self.assertIn("trial", err["error"])
        status, r = self.call("/api/tools/fix_bone_scale", {"values": values})
        self.assertEqual(status, 200, r)
        self.assertTrue(r["trial"])
        j = self.wait(r["job"])
        self.assertIn("--dry-run", j["command"])
        if j["code"] != 0:                   # a failed trial does not open Apply
            status, err = self.call("/api/tools/fix_bone_scale", {"values": values, "apply": True})
            self.assertEqual(status, 400)

    # -- building ---------------------------------------------------------------------------
    def test_every_preset_previews(self):
        for key in building.PRESETS:
            status, p = self.call("/api/preset/" + key)
            self.assertEqual(status, 200)
            for detail in ("LOW", "MEDIUM"):
                p["detail"] = detail
                status, d = self.call("/api/building/preview", {"params": p, "texture": 128})
                self.assertEqual(status, 200, (key, d))
                self.assertEqual(d["triangles"] * 3, len(d["mesh"]["indices"]), key)
                want = sum(len(f.pts) - 2 for f in building.build(schema.params_from_dict(p)).faces)
                self.assertEqual(d["triangles"], want, key)
                self.assertTrue(d["texture"].startswith("data:image/png;base64,"))

    def test_bad_parameters_are_refused(self):
        p = engine.preset("WHITE_HOUSE")
        for bad in ({"style": "GOTHIC"}, {"nonsense": 1}, {"detail": "HIGH"}, {"colors": {"wall": [300, 0, 0]}}):
            status, err = self.call("/api/building/preview", {"params": {**p, **bad}, "texture": 128})
            self.assertEqual(status, 400, bad)
        status, d = self.call("/api/building/preview", {"params": {**p, "width": 999}, "texture": 128})
        self.assertEqual(status, 200)
        self.assertEqual(d["params"]["width"], 60.0)              # held to the schema's range

    def test_the_sheet_and_the_budget(self):
        status, s = self.call("/api/building/sheet", {"params": engine.preset("AFRICAN_HOUSE_SAHEL")})
        self.assertEqual(status, 200, s)
        self.assertTrue(s["markdown"].startswith("# "))
        self.assertIsNotNone(s["budget"]["band"])
        status, s = self.call("/api/building/sheet", {"params": engine.preset("WHITE_HOUSE")})
        self.assertEqual(status, 200, s)
        medium = dataclasses.replace(building.PRESETS["WHITE_HOUSE"], detail="MEDIUM")
        self.assertEqual(s["facts"]["tris"], sum(len(f.pts) - 2 for f in building.build(medium).faces))

    # -- jobs -------------------------------------------------------------------------------
    def test_a_tool_runs_and_its_outputs_show(self):
        out = os.path.join(self.tmp.name, "bars")
        status, r = self.call("/api/tools/make_bar", {"values": {"colour": "3366CC", "out": os.path.join(out, "bar.ddt")}})
        self.assertEqual(status, 200, r)
        j = self.wait(r["job"])
        self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"])
        self.assertTrue(os.path.isfile(os.path.join(out, "bar.ddt")))
        status, listing = self.call("/api/list?path=" + urllib.request.quote(out))
        self.assertEqual(status, 200)
        self.assertEqual([f["rel"] for f in listing["files"]], ["bar.ddt"])

    def test_deploy_and_undo_through_the_forms(self):
        """The building screen's Deploy and Undo: the copy changed, then back byte for byte."""
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_game_formats as tgf
        maker = tgf.DeployTest()
        with tempfile.TemporaryDirectory() as tmp:
            inst, bundle = maker.make_copy(tmp)
            before = maker.digest(inst)
            status, r = self.call("/api/tools/deploy", {"values": {"install": inst, "bundle": [bundle]}})
            self.assertEqual(status, 200, r)
            j = self.wait(r["job"])
            self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"])
            with open(os.path.join(inst, "data", "protoy.xml"), encoding="utf-8") as fh:
                self.assertIn('name="Tower"', fh.read())
            status, r = self.call("/api/tools/deploy_undo", {"values": {"install": inst}})
            j = self.wait(r["job"])
            self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"])
            self.assertEqual(maker.digest(inst), before)

    def test_a_new_deployment_never_replaces_the_others_without_saying(self):
        """What the copy has is read before deploying; Add keeps the others, a building already
        there is refused for Add, Update deploys them all again, Replace leaves only the new one."""
        import shutil
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_game_formats as tgf
        maker = tgf.DeployTest()
        with tempfile.TemporaryDirectory() as tmp:
            inst, tower = maker.make_copy(tmp)
            before = maker.digest(inst)
            hall = os.path.join(tmp, "hall")
            shutil.copytree(tower, hall)
            with open(os.path.join(hall, "bundle.json"), encoding="utf-8") as fh:
                b = json.load(fh)
            b["name"] = "Hall"
            with open(os.path.join(hall, "bundle.json"), "w", encoding="utf-8") as fh:
                json.dump(b, fh)

            def deploy(values):
                status, r = self.call("/api/tools/deploy", {"values": dict({"install": inst}, **values)})
                self.assertEqual(status, 200, r)
                return self.wait(r["job"])

            def state(bundle=None):
                return self.call("/api/deploy/state", {"install": inst, "bundle": bundle})[1]

            self.assertEqual(state(tower)["units"], [])
            self.assertEqual(deploy({"bundle": [tower]})["code"], 0)
            s = state(hall)
            self.assertEqual((s["units"], s["new"]), (["Tower"], "Hall"))
            self.assertEqual(deploy({"bundle": [hall], "keep": True})["code"], 0)       # Add
            self.assertEqual(state()["units"], ["Tower", "Hall"])
            j = deploy({"bundle": [hall], "keep": True})                                 # already there
            self.assertEqual(j["code"], 1)
            self.assertIn("already deployed", " ".join(j["lines"]))
            self.assertEqual(state()["units"], ["Tower", "Hall"])
            self.assertEqual(deploy({"bundle": [tower, hall]})["code"], 0)               # Update
            self.assertEqual(state()["units"], ["Tower", "Hall"])
            with open(os.path.join(inst, "data", "protoy.xml"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual((text.count('name="Tower"'), text.count('name="Hall"')), (1, 1))
            self.assertEqual(deploy({"bundle": [hall]})["code"], 0)                      # Replace
            self.assertEqual(state()["units"], ["Hall"])
            status, r = self.call("/api/tools/deploy_undo", {"values": {"install": inst}})
            self.wait(r["job"])
            self.assertEqual(maker.digest(inst), before)                                  # as it was
            self.assertEqual(self.call("/api/deploy/state", {"install": os.path.join(tmp, "nothing")})[0], 400)

    def test_the_ai_repaint_option_reaches_the_export(self):
        """Export for the game with the AI repaint, against the ComfyUI stand-in (needs the bpy
        module, as every export: skipped without it)."""
        if not self.studio.bridge.module:
            self.skipTest("no bpy module in this Python")
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from fake_comfy import FakeComfy
        with FakeComfy(transform=lambda rgb: 255 - rgb) as fake, tempfile.TemporaryDirectory() as tmp:
            self.studio.settings.update({"paths": {"comfy_url": fake.url}})
            try:
                p = engine.preset("COLONIAL_HOUSE")
                p["texture_size"] = 256
                status, r = self.call("/api/building/export", {"kind": "game", "params": p, "out": tmp,
                                                               "options": {"ai": True, "ai_strength": 0.4,
                                                                           "no_icons": True}})
                self.assertEqual(status, 200, r)
                j = self.wait(r["job"], 300)
                self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"][-20:])
                self.assertIn("--ai", j["command"])
                self.assertTrue(any(line.startswith("AI repaint:") for line in j["lines"]), j["lines"][-20:])
                self.assertTrue(fake.prompts, "ComfyUI was never asked")
            finally:
                self.studio.settings.update({"paths": {"comfy_url": "http://127.0.0.1:8188"}})
            status, err = self.call("/api/building/export", {"kind": "game", "params": p, "out": tmp,
                                                             "options": {"ai": True, "ai_strength": 2}})
            self.assertEqual(status, 400)

    def test_a_surveys_results_as_a_table(self):
        """The program's own profiles, and a texture survey's report (its profile computed as the
        tool does), as groups with their columns; anything else refused."""
        for name, kind, col in (("textures", "textures", "grain"), ("models", "models", "tris")):
            status, r = self.call("/api/results", {"profile": name})
            self.assertEqual(status, 200, r)
            self.assertEqual(r["kind"], kind)
            self.assertGreater(len(r["rows"]), 5)
            self.assertIn(col, [c["key"] for c in r["columns"]])
            self.assertTrue(all(c["label"]["en"] and c["label"]["es"] for c in r["columns"]))
            self.assertTrue(r["help"]["en"] and r["help"]["es"])
            q = next(x[col] for x in r["rows"] if x[col])
            self.assertEqual(len(q), 3)
            self.assertLessEqual(q[0], q[1])
        import numpy as np
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import texture_survey
        rng = np.random.default_rng(1)
        records = []
        for i in range(10):
            rec = texture_survey.measure(rng.integers(0, 255, (64, 64, 4), dtype=np.uint8))
            rec.update({"path": f"art/units/u{i}.ddt", "md5": str(i), "w": 64, "h": 64, "format": 1, "alpha": 0,
                        "origin": "own", "category": "units", "role": "diffuse", "material": ""})
            records.append(rec)
        report = os.path.join(self.tmp.name, "textures.json")
        with open(report, "w", encoding="utf-8") as fh:
            json.dump({"folders": [], "reference": [], "textures": records}, fh)
        status, r = self.call("/api/results", {"path": report})
        self.assertEqual(status, 200, r)
        self.assertEqual(r["facts"]["textures"], 10)
        self.assertTrue(any(x["category"] == "units" and x["count"] == 10 for x in r["rows"]))
        self.assertNotIn("u0.ddt", json.dumps(r))                     # groups only: no file named
        for bad in ({"path": os.path.join(self.tmp.name, "none.json")}, {"path": self.config}, {"profile": "x"}):
            status, err = self.call("/api/results", bad)
            self.assertEqual(status, 400, bad)

    def test_compose_a_settlement(self):
        """Laid out as measured, written as a grouping in the work folder, read back unit for unit;
        a read file's own orientation kept while a unit is not turned; never into the game."""
        status, m = self.call("/api/settlement/measured", {})
        self.assertEqual(status, 200, m)
        self.assertGreater(m["counts"]["building"], 0)
        rows = [{"class": "building", "proto": "TestHut", "variations": 3, "radius": 3.5},
                {"class": "prop", "proto": "TestCrate", "variations": 2, "radius": 0.8}]
        status, r = self.call("/api/settlement/compose", {"units": rows, "socket": "SocketTradeRoute",
                                                          "obstruction": "TestObstruction", "seed": 3,
                                                          "counts": {"building": 4, "prop": 5}})
        self.assertEqual(status, 200, r)
        units = r["units"]
        self.assertEqual(units[0]["class"], "socket")
        self.assertEqual(sum(u["class"] == "building" for u in units), 4)
        self.assertEqual(sum(u["class"] == "obstruction" for u in units), 8)
        status, again = self.call("/api/settlement/compose", {"units": rows, "seed": 3, "counts": {"building": 4, "prop": 5},
                                                              "socket": "SocketTradeRoute", "obstruction": "TestObstruction"})
        self.assertEqual(again["units"], units)                       # a seed gives its arrangement
        status, err = self.call("/api/settlement/compose", {"units": [{"class": "castle", "proto": "X"}]})
        self.assertEqual(status, 400)
        status, err = self.call("/api/settlement/compose", {"units": []})
        self.assertEqual(status, 400)

        status, w = self.call("/api/settlement/save", {"name": "Test Settlement", "units": units})
        self.assertEqual(status, 200, w)
        self.assertTrue(w["path"].startswith(self.studio.settings.get("work")))
        status, back = self.call("/api/settlement/open", {"path": w["path"]})
        self.assertEqual(status, 200, back)
        self.assertEqual([(u["proto"], u["variation"], round(u["x"], 4), round(u["z"], 4)) for u in back["units"]],
                         [(u["proto"], u["variation"], round(u["x"], 4), round(u["z"], 4)) for u in units])
        self.assertEqual(back["units"][0]["class"], "socket")
        # written again unchanged: the same file; one unit turned: only its line changes
        with open(w["path"], encoding="utf-8") as fh:
            first = fh.read()
        status, w2 = self.call("/api/settlement/save", {"name": "Test Settlement", "units": back["units"], "meta": back["meta"]})
        with open(w2["path"], encoding="utf-8") as fh:
            self.assertEqual(fh.read(), first)
        back["units"][1]["turn"] += 0.5
        self.call("/api/settlement/save", {"name": "Test Settlement", "units": back["units"], "meta": back["meta"]})
        with open(w2["path"], encoding="utf-8") as fh:
            changed = [a for a, b in zip(first.splitlines(), fh.read().splitlines()) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertIn(units[1]["proto"], changed[0])

        status, err = self.call("/api/settlement/save", {"name": "../escape", "units": units})
        self.assertEqual(status, 400)
        status, err = self.call("/api/settlement/open", {"path": os.path.join(self.tmp.name, "none.xml")})
        self.assertEqual(status, 400)
        game = os.path.join(self.tmp.name, "game")
        os.makedirs(game, exist_ok=True)
        self.studio.settings.update({"paths": {"work": self.studio.settings.get("work"), "game": game}})
        try:
            status, err = self.call("/api/settlement/save", {"path": os.path.join(game, "x.xml"), "units": units})
            self.assertEqual(status, 400)
        finally:
            self.studio.settings.update({"paths": {"work": self.studio.settings.get("work"), "game": ""}})

    def test_repaint_a_unit(self):
        """The unit repaint screen: load a model and its texture, paint live, add a picture, write."""
        import base64

        import numpy as np
        from aoe3game import ddt, gr2_write
        from core import paint as painter
        with tempfile.TemporaryDirectory() as tmp:
            # a 'unit' of two islands: a head high up (UV top left), a leg low down (UV bottom right)
            P = [(-.2, 0, 1.6), (.2, 0, 1.6), (.2, 0, 1.9), (-.2, 0, 1.9), (-.2, 0, .1), (.2, 0, .1), (.2, 0, .8), (-.2, 0, .8)]
            UV = [(0, .5), (.5, .5), (.5, 1), (0, 1), (.5, 0), (1, 0), (1, .5), (.5, .5)]
            with open(os.path.join(tmp, "unit.gr2"), "wb") as fh:
                fh.write(gr2_write.static_model("unit", P, [(0, -1, 0)] * 8, UV, [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)],
                                                texture="unit.ddt", bump="unit_b.ddt"))
            tex = np.full((64, 64, 4), 200, np.uint8)
            tex[..., 3] = 255
            tex[48:, 48:, 3] = 0                                    # player colour on the leg
            with open(os.path.join(tmp, "unit.ddt"), "wb") as fh:
                fh.write(ddt.write_bgra(tex, alpha=1, mips=False))
            status, r = self.call("/api/retex/load", {"source": "file", "model": os.path.join(tmp, "unit.gr2"),
                                                      "texture": os.path.join(tmp, "unit.ddt"), "by": "position"})
            self.assertEqual(status, 200, r)
            self.assertEqual((r["width"], r["height"], r["triangles"]), (64, 64, 4))
            self.assertEqual(sorted(i["part"] for i in r["islands"]), ["head", "leg_r"])
            sid = r["session"]
            head = [{"op": "recolour", "where": ["part:head"], "colour": "#204080", "shading": 0}]
            status, p = self.call("/api/retex/paint", {"session": sid, "ops": head + [{"op": "tone", "where": []},
                                                                                     {"op": "ai", "where": ["all"]}]})
            self.assertEqual(status, 200, p)
            self.assertEqual((p["empty"], p["ai_skipped"]), ([1], [2]))   # neither paints in the preview
            from core import pngio
            img = np.asarray(pngio.read_png(base64.b64decode(p["image"].split(",", 1)[1])))
            self.assertEqual(img[8, 8, :3].tolist(), [32, 64, 128])       # the head, recoloured
            self.assertEqual(img[56, 56, :3].tolist(), [200, 200, 200])   # the leg, untouched
            status, err = self.call("/api/retex/paint", {"session": sid, "ops": [{"op": "melt", "where": ["all"]}]})
            self.assertEqual(status, 400)
            # a part this unit has not: skipped with a note while painting, refused when writing
            torso = [{"op": "recolour", "where": ["part:torso"], "colour": "#204080"}]
            status, p2 = self.call("/api/retex/paint", {"session": sid, "ops": torso + head})
            self.assertEqual(status, 200, p2)
            self.assertEqual([m[0] for m in p2["missing"]], [0])
            status, err = self.call("/api/retex/save", {"session": sid, "ops": torso})
            self.assertEqual(status, 400)
            self.assertIn("torso", err["error"])
            # a swatch the page sends, then a fill with it
            swatch = np.zeros((8, 8, 3), np.uint8)
            swatch[..., 1] = 180
            data = "data:image/png;base64," + base64.b64encode(painter.png_bytes(swatch)).decode()
            status, got = self.call("/api/retex/picture", {"session": sid, "name": "green.png", "data": data})
            self.assertEqual((status, got.get("name")), (200, "green.png"), got)
            for bad in ("../x.png", "start.png", "x.exe"):
                status, _ = self.call("/api/retex/picture", {"session": sid, "name": bad, "data": data})
                self.assertEqual(status, 400, bad)
            ops = head + [{"op": "fill", "where": ["part:legs"], "swatch": "green.png", "tile": 8, "shading": 0}]
            status, err = self.call("/api/retex/save", {"session": sid, "ops": [{"op": "tone", "where": []}]})
            self.assertEqual(status, 400)                                  # a step that paints nowhere
            status, w = self.call("/api/retex/save", {"session": sid, "ops": ops, "out": "blue", "format": "DXT3"})
            self.assertEqual(status, 200, w)
            j = self.wait(w["job"], 120)
            self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"])
            with open(os.path.join(w["folder"], "blue.ddt"), "rb") as fh:
                out = ddt.decode(fh.read(), 0)
            self.assertLess(abs(int(out[8, 8, 2]) - 128), 12)              # DXT3: near, not exact
            self.assertGreater(int(out[56, 56, 1]), int(out[56, 56, 0]) + 60)  # the leg filled green
            self.assertEqual(int(out[60, 60, 3]), 0)                       # the player colour kept
            for name in ("blue_b.ddt", "blue.png", "sheet.png", "recipe.json", os.path.join("atlas", "atlas.json")):
                self.assertTrue(os.path.isfile(os.path.join(w["folder"], name)), name)
        status, err = self.call("/api/retex/paint", {"session": "gone", "ops": []})
        self.assertEqual(status, 400)

    def test_design_a_flag(self):
        """The flag designer on a made-up copy (tests/test_make_flag.py): measure, preview every
        texture of the set, compare, write beside the copy and never into it."""
        import base64

        import numpy as np
        from core import paint as painter
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_make_flag as tmf
        with tempfile.TemporaryDirectory() as tmp:
            game = os.path.join(tmp, "game")
            tmf.fake_copy(game, n=6)
            status, m = self.call("/api/flags/measure", {"game": game, "flags_dir": tmf.FL, "buttons_dir": tmf.BT})
            self.assertEqual(status, 200, m)
            self.assertEqual(m["count"], 6)
            design = np.zeros((40, 60, 3), np.uint8)
            design[:, :30] = (200, 20, 20)
            design[:, 30:] = (20, 20, 200)
            url = "data:image/png;base64," + base64.b64encode(painter.png_bytes(design)).decode()
            status, p = self.call("/api/flags/preview", {"session": m["session"], "design": url})
            self.assertEqual(status, 200, p)
            self.assertEqual(sorted(p), sorted(["flag", "postgame"] + [f"{k}_{s}" for k in ("button", "large")
                                                                         for s in ("normal", "click", "high", "disable")]))
            # a crop of the left half only: the in-game flag is red all across
            status, p = self.call("/api/flags/preview", {"session": m["session"], "design": url, "crop": [0, 0, 0.5, 1]})
            from core import pngio
            flag = np.asarray(pngio.read_png(base64.b64decode(p["flag"].split(",", 1)[1])))
            self.assertGreater(int(flag[64, 120, 0]), int(flag[64, 120, 2]) + 80)
            status, e = self.call("/api/flags/preview", {"session": m["session"], "existing": "s2"})
            self.assertEqual((status, len(e)), (200, 10))
            for bad in ({"name": "bad name"}, {"name": "ok", "out": os.path.join(game, "art", "x")}):
                status, err = self.call("/api/flags/write", dict({"session": m["session"], "design": url}, **bad))
                self.assertEqual(status, 400, bad)
            out = os.path.join(tmp, "out")
            status, w = self.call("/api/flags/write", {"session": m["session"], "design": url, "name": "duo", "out": out})
            self.assertEqual(status, 200, w)
            self.assertEqual(len(w["files"]), 10)
            self.assertTrue(all(os.path.isfile(f) for f in w["files"].values()))
            self.assertTrue(os.path.isfile(w["sheet"]))
            status, _ = self.call("/api/flags/measure", {"game": os.path.join(tmp, "nothing")})
            self.assertEqual(status, 400)

    def test_make_a_texture(self):
        """The texture maker: a photograph, a crop made tileable without ComfyUI, kept in a
        library with its licence, used by the painter, deleted."""
        import base64

        import numpy as np
        from core import paint as painter
        rng = np.random.default_rng(0)
        img = (rng.random((120, 160, 3)) * 60 + np.linspace(60, 200, 160)[None, :, None]).astype(np.uint8)
        url = "data:image/png;base64," + base64.b64encode(painter.png_bytes(img)).decode()
        with tempfile.TemporaryDirectory() as lib:
            status, s = self.call("/api/tex/source", {"data": url})
            self.assertEqual(status, 200, s)
            self.assertEqual((s["width"], s["height"]), (160, 120))
            o = {"session": s["session"], "cx": 0.5, "cy": 0.5, "part": 0.8, "size": 128, "material": "plaster"}
            status, p = self.call("/api/tex/preview", o)
            self.assertEqual(status, 200, p)
            self.assertLess(p["report"]["seam"], p["report"]["seam_before"])     # it tiles better than the photograph
            for bad in ({"size": 300}, {"part": 0}, {"cx": 2}):
                self.assertEqual(self.call("/api/tex/preview", dict(o, **bad))[0], 400, bad)
            keep = dict(o, name="wall_test", licence="made in a test", style="COLONIAL", role="wall", folder=lib)
            for bad in ({"licence": ""}, {"name": "../x"}):
                self.assertEqual(self.call("/api/tex/keep", dict(keep, **bad))[0], 400, bad)
            status, k = self.call("/api/tex/keep", keep)
            self.assertEqual(status, 200, k)
            self.assertEqual([x["name"] for x in k["library"]["textures"]], ["wall_test"])
            self.assertIn("COLONIAL", k["library"]["roles"])
            with open(os.path.join(lib, "wall_test.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["licence"], "made in a test")
            status, u = self.call("/api/tex/use", {"on": True, "folder": lib})
            try:
                self.assertEqual(u["in_use"], {"COLONIAL wall": "wall_test"})
                from core import materials
                self.assertEqual(os.path.basename(materials.MATERIALS["COLONIAL"]["wall"][0]), "wall_test")
            finally:
                status, u = self.call("/api/tex/use", {"on": False})
            self.assertEqual(u["in_use"], {})
            self.assertEqual(materials.MATERIALS["COLONIAL"]["wall"][0], "plaster")   # the add-on's own again
            # the AI repaint needs a prompt (and runs as a task)
            self.assertEqual(self.call("/api/tex/ai", dict(keep, prompt=""))[0], 400)
            status, d = self.call("/api/tex/delete", {"name": "wall_test", "folder": lib})
            self.assertEqual((status, d["textures"]), (200, []))
            self.assertEqual(self.call("/api/tex/delete", {"name": "wall_test", "folder": lib})[0], 400)

    def test_ai_repaint_by_regions(self):
        """The building screen's AI repaint against the ComfyUI stand-in: the regions and their
        materials, a run region by region with its texture as it goes, a stop, the result kept and
        used by the game export (that part needs the bpy module)."""
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from fake_comfy import FakeComfy
        p = engine.preset("COLONIAL_HOUSE")
        p["texture_size"] = 256
        status, r = self.call("/api/ai/regions", {"params": p})
        self.assertEqual(status, 200, r)
        names = {x["name"]: x for x in r["regions"]}
        self.assertTrue(names["roof"]["material"])
        self.assertIn("roof", r["roofs"])
        usable = [x["name"] for x in r["regions"] if x["material"] and not x["small"]]
        self.assertGreater(len(usable), 3)

        def slow_invert(rgb):                 # a region takes a while, so a stop lands between two
            time.sleep(0.2)
            return 255 - rgb
        with FakeComfy(transform=slow_invert) as fake:
            self.studio.settings.update({"paths": {"comfy_url": fake.url}})
            try:
                self.assertEqual(self.call("/api/ai/start", {"params": p, "regions": ["nowhere"]})[0], 400)
                self.assertEqual(self.call("/api/ai/start", {"params": p, "strength": 3})[0], 400)
                status, s = self.call("/api/ai/start", {"params": p, "regions": usable[:2], "strength": 0.4, "guard": False})
                self.assertEqual(status, 200, s)
                for _ in range(200):
                    status, st = self.call("/api/ai/state", {"session": s["session"]})
                    if st["status"] != "running":
                        break
                    time.sleep(0.1)
                self.assertEqual(st["status"], "done", st)
                self.assertEqual(st["version"], 3)                        # each region, then the result
                self.assertTrue(st["image"].startswith("data:image/png"))
                self.assertEqual(len([x for x in st["report"] if "skipped" not in x]), 2)
                status, saved = self.call("/api/ai/save", {"session": s["session"]})
                self.assertEqual(status, 200, saved)
                self.assertTrue(os.path.isfile(saved["path"]))
                # a stop between regions keeps what was done
                status, s2 = self.call("/api/ai/start", {"params": p, "strength": 0.4, "guard": False})
                self.call("/api/ai/cancel", {"session": s2["session"]})
                for _ in range(200):
                    status, st2 = self.call("/api/ai/state", {"session": s2["session"]})
                    if st2["status"] != "running":
                        break
                    time.sleep(0.1)
                self.assertEqual(st2["status"], "cancelled", st2)
            finally:
                self.studio.settings.update({"paths": {"comfy_url": "http://127.0.0.1:8188"}})
        status, err = self.call("/api/ai/start", {"params": p})                 # nothing answers there
        self.assertEqual(status, 400)
        if not self.studio.bridge.module:
            return
        with tempfile.TemporaryDirectory() as tmp:
            status, r = self.call("/api/building/export", {"kind": "game", "params": p, "out": tmp,
                                                           "options": {"texture_png": saved["path"], "no_icons": True}})
            j = self.wait(r["job"], 300)
            self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"][-20:])
            self.assertIn("--texture-png", j["command"])
            self.assertTrue(any(line.startswith("texture:") for line in j["lines"]))

    def test_check_a_building(self):
        """The add-on's Check from the building screen: a task in Blender whose lines the page reads
        as JSON (needs the bpy module: skipped without it)."""
        if not self.studio.bridge.module:
            self.skipTest("no bpy module in this Python")
        p = engine.preset("WHITE_HOUSE")
        status, r = self.call("/api/building/check", {"params": p})
        self.assertEqual(status, 200, r)
        j = self.wait(r["job"], 300)
        self.assertEqual((j["status"], j["code"]), ("done", 0), j["lines"][-10:])
        found = [json.loads(line) for line in j["lines"] if line.startswith("{")]
        self.assertTrue(any(f["level"] == "INFO" and "triangles" in f["message"] for f in found), found)
        self.assertFalse([f for f in found if f["level"] == "ERROR"], found)

    def test_a_prop_set_previews(self):
        status, schema_ = self.call("/api/schema")
        self.assertEqual(sorted(schema_["sets"]), ["CAMP", "GOODS"])
        for name in schema_["sets"]:
            status, d = self.call("/api/building/set", {"set": name, "texture": 128})
            self.assertEqual(status, 200, d)
            self.assertEqual(d["triangles"], sum(v["triangles"] for v in d["variations"]))
            self.assertEqual(len(d["mesh"]["indices"]), 3 * d["triangles"])
        self.assertEqual(self.call("/api/building/set", {"set": "NOPE"})[0], 400)
        self.assertEqual(self.call("/api/building/set", {"set": "GOODS", "texture": 3000})[0], 400)

    def test_comfyui_check_and_start(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from fake_comfy import FakeComfy
        from core import comfy
        status, r = self.call("/api/comfy/check", {})
        self.assertEqual((status, r["running"]), (200, False))          # nothing answers at the default
        self.assertEqual(self.call("/api/comfy/start", {})[0], 400)     # and there is no ComfyUI folder
        with FakeComfy(missing_nodes=(comfy.NODES[0],)) as fake:
            self.studio.settings.update({"paths": {"comfy_url": fake.url}})
            try:
                status, r = self.call("/api/comfy/check", {})
                self.assertTrue(r["running"])
                self.assertTrue(any(comfy.NODES[0] in x for x in r["problems"]), r)
                status, r = self.call("/api/comfy/start", {})
                self.assertEqual((status, r["already"]), (200, True))    # running: nothing to start
            finally:
                self.studio.settings.update({"paths": {"comfy_url": "http://127.0.0.1:8188"}})

    def test_an_error_is_logged(self):
        """A bug answers 500 and leaves its trace in the log the Settings screen shows."""
        from unittest import mock
        from studio import engine
        with mock.patch.object(engine, "preview", side_effect=ZeroDivisionError("a bug")):
            status, err = self.call("/api/building/preview", {"params": {}, "texture": 128})
        self.assertEqual(status, 500)
        self.assertIn("log", err["error"])
        status, log = self.call("/api/log")
        self.assertEqual(status, 200)
        self.assertIn("error answering POST /api/building/preview", log["text"])
        self.assertIn("Traceback", log["text"])
        # a malformed parameter is the user's error, answered 400 with what is wrong
        status, err = self.call("/api/building/preview", {"params": {"colors": "not a table"}, "texture": 128})
        self.assertEqual(status, 400)
        self.assertIn("colors", err["error"])

    def test_when_the_studio_stops(self):
        st = server.Studio(os.path.join(self.tmp.name, "stop", "s.json"))
        now = 1000.0
        self.assertFalse(st.should_stop(now))                      # no page yet
        st.last_ping = now
        st.bye_at = now + 1                                        # its page closed...
        self.assertFalse(st.should_stop(now + 5))                  # ...another page may still call in
        self.assertTrue(st.should_stop(now + 14))
        st.last_ping = now + 9                                     # a reload, or a second window
        self.assertFalse(st.should_stop(now + 20))
        st.bye_at, st.last_ping = None, now
        self.assertTrue(st.should_stop(now + 40, window_gone=True))
        self.assertTrue(st.should_stop(now + 700))                 # a page silent for ten minutes
        job = st.jobs.start("sleep", [sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(0.5)
            self.assertFalse(st.should_stop(now + 700))            # never while a task runs
        finally:
            st.jobs.cancel(job.id)

    def test_one_studio_at_a_time(self):
        """The lock file names the running studio; a second start finds it (and only a live one)."""
        import importlib
        launcher = importlib.import_module("studio.__main__")
        home = os.path.join(self.tmp.name, "single")
        self.assertIsNone(launcher.running(home))
        launcher.claim(home, self.base + "/")
        self.assertEqual(launcher.running(home), self.base + "/")
        launcher.release(home, "http://127.0.0.1:1/")              # not ours: kept
        self.assertTrue(os.path.isfile(os.path.join(home, launcher.LOCK)))
        launcher.release(home, self.base + "/")
        self.assertIsNone(launcher.running(home))
        launcher.claim(home, "http://127.0.0.1:1/")                # a studio that is gone
        self.assertIsNone(launcher.running(home))

    def test_the_welcome_checks_each_folder(self):
        def check(key, path):
            status, r = self.call("/api/check-path", {"key": key, "path": path})
            self.assertEqual(status, 200, r)
            return r["ok"], [code for _level, code in r["notes"]]
        game = os.path.join(self.tmp.name, "w_game")
        os.makedirs(os.path.join(game, "art"))
        self.assertEqual(check("game", game), (False, ["art", "no_data"]))
        os.makedirs(os.path.join(game, "data"))
        self.assertEqual(check("game", game), (True, ["art", "data"]))
        self.assertEqual(check("game", os.path.join(self.tmp.name, "nowhere")), (False, ["missing"]))
        steam = os.path.join(self.tmp.name, "SteamLibrary", "steamapps", "common", "AoE3")
        for sub in ("art", "data"):
            os.makedirs(os.path.join(steam, sub))
        self.assertIn("steam_read_only", check("game", steam)[1])            # the game: only read
        ok, notes = check("test_copy", steam)
        self.assertFalse(ok)
        self.assertIn("steam_refused", notes)                                 # a test copy: refused
        self.assertEqual(check("comfy_dir", game), (False, ["comfy_not_portable"]))
        self.assertEqual(self.call("/api/check-path", {"key": "nonsense", "path": game})[0], 400)

    def test_find_units_and_flag_folders_in_the_game(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_make_flag as tmf
        game = os.path.join(self.tmp.name, "f_game")
        tmf.fake_copy(game, n=3)
        os.makedirs(os.path.join(game, "data"))
        with open(os.path.join(game, "data", "protoy.xml"), "w", encoding="utf-8") as fh:
            fh.write('<proto><unit name="Musketeer"><animfile>units\\infantry\\musketeer.xml</animfile></unit>'
                     '<unit name="Pikeman"><animfile>units\\infantry\\pikeman.xml</animfile></unit>'
                     '<unit name="NoArt"></unit></proto>')
        self.assertEqual(self.call("/api/game/units", {"q": "musk"})[0], 400)    # no game set yet
        self.studio.settings.update({"paths": {"game": game}})
        try:
            status, r = self.call("/api/game/units", {"q": "musk"})
            self.assertEqual((status, [u["name"] for u in r["units"]]), (200, ["Musketeer"]))
            status, r = self.call("/api/game/units", {"q": ""})
            self.assertEqual([u["name"] for u in r["units"]], ["Musketeer", "Pikeman"])  # units with art only
            status, r = self.call("/api/game/flagdirs", {})
            self.assertEqual(status, 200, r)
            self.assertEqual(r["pairs"], [{"buttons": tmf.BT, "flags": tmf.FL, "sets": 3}])
        finally:
            self.studio.settings.update({"paths": {"game": ""}})

    def test_a_job_can_be_cancelled(self):
        job = self.studio.jobs.start("sleep", [sys.executable, "-c", "import time\nprint('1/4', flush=True)\ntime.sleep(60)"])
        time.sleep(1.0)
        status, r = self.call(f"/api/cancel/{job.id}", {})
        self.assertTrue(r["cancelled"])
        j = self.wait(job.id, 20)
        self.assertEqual(j["status"], "cancelled")
        self.assertEqual(j["progress"], 0.25)


class Forms(unittest.TestCase):
    def test_the_schema_describes_every_field(self):
        from dataclasses import fields
        names = {f.name for f in fields(building.BuildingParams)} - set(schema.NOT_DESCRIBED)
        self.assertEqual(names, set(schema.BY_NAME))
        data = json.loads(json.dumps(schema.to_json()))
        self.assertEqual(len(data["fields"]), len(schema.FIELDS))
        for f in schema.FIELDS:
            if f.kind in ("int", "float"):
                self.assertLess(f.min, f.max, f.name)
                default = getattr(building.BuildingParams(), f.name)
                self.assertTrue(f.min <= default <= f.max or f.name == "side_bays", f.name)
            for styles, cond in f.show:
                for k in cond:
                    self.assertIn(k, schema.BY_NAME, (f.name, k))

    def test_every_preset_shows_only_what_it_uses(self):
        for key, p in building.PRESETS.items():
            shown = [f.name for f in schema.FIELDS if schema.visible(f, p)]
            self.assertIn("style", shown)
            if p.style == "AFRICAN":
                self.assertIn("building_type", shown)
                self.assertNotIn("width", shown)
            if p.style == "NEOCLASSICAL":
                self.assertIn("portico", shown)
                self.assertEqual("columns" in shown, p.portico, key)

    def test_the_catalog_holds_to_each_script(self):
        """Every option a form passes is one its script reads: the scripts parse sys.argv by hand
        and would skip an unknown option silently."""
        for tool in catalog.TOOLS:
            path = os.path.join(ROOT, tool.script)
            self.assertTrue(os.path.isfile(path), tool.id)
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            ast.parse(source)
            for flag in [a.flag for a in tool.args if a.flag] + [f for f in tool.fixed + (tool.trial or []) + tool.commit
                                                                  if f.startswith("-")]:
                self.assertRegex(source, re.escape(f'"{flag}"') + "|" + re.escape(f"'{flag}'"),
                                 f"{tool.id}: {flag} is not read by {tool.script}")
            for f in tool.fixed:
                if not f.startswith("-"):
                    self.assertIn(f'"{f}"', source, (tool.id, f))

    def test_the_catalog_is_complete_and_in_both_languages(self):
        scripts = {t.script for t in catalog.TOOLS}
        for name in os.listdir(os.path.join(ROOT, "tools")) + ["../scripts/" + n for n in os.listdir(os.path.join(ROOT, "scripts"))]:
            if not name.endswith(".py") or name in ("bitfont.py", "build_app.py"):
                continue                   # a library, and the build of the studio itself
            rel = ("tools/" + name) if not name.startswith("..") else name[3:]
            self.assertIn(rel, scripts, f"{rel} has no form in studio/catalog.py")
        ids = [t.id for t in catalog.TOOLS]
        self.assertEqual(len(ids), len(set(ids)))

        def pairs(obj, where):
            if isinstance(obj, dict) and set(obj) == {"en", "es"}:
                if obj["en"]:
                    self.assertTrue(obj["es"], where)
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    pairs(v, f"{where}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    pairs(v, f"{where}[{i}]")
        for t in catalog.TOOLS:
            p = t.public()
            self.assertTrue(p["title"]["en"] and p["title"]["es"] and p["desc"]["es"], t.id)
            self.assertIn(t.area, catalog.AREAS)
            self.assertIn(t.writes, catalog.WRITES)
            for n in t.needs:
                self.assertIn(n, catalog.NEEDS)
            pairs(p, t.id)
            for a in t.args:
                self.assertIn(a.kind, ("text", "int", "float", "bool", "choice", "color", "file", "files", "folder",
                                       "folders", "save", "outdir"), (t.id, a.key))
                if a.setting:
                    self.assertIn(a.setting, settings.PATHS, (t.id, a.key))
            if t.writes in ("copy", "in_place") and t.trial is None:
                self.assertIsNotNone(t.confirm, f"{t.id} changes files: it needs a trial or a confirmation")

    def test_command_lines(self):
        class St:                            # what catalog.command needs of the server
            trials, roots = {}, set()

            def __init__(self, tmp):
                self.settings = settings.Settings(os.path.join(tmp, "s.json"))
                self.jobs = jobs.Jobs()
                self.bridge = type("B", (), {"command": lambda self, s, a: ["blender", s] + list(a)})()
                self.tmp = tmp

            def work_dir(self, *parts):
                return os.path.join(self.tmp, *parts)

        with tempfile.TemporaryDirectory() as tmp:
            st = St(tmp)
            cmd, title, outs, _, trial = catalog.command(st, "xmb_add_unittype", {
                "file": "a.xmb", "out": "b.xmb", "pairs": "House AbstractHouse Mill AbstractMill"})
            self.assertEqual(cmd[-7:], ["add-unittype", "a.xmb", "b.xmb", "House", "AbstractHouse", "Mill", "AbstractMill"])
            cmd, *_ = catalog.command(st, "deploy", {"install": tmp, "bundle": ["x", "y"], "validate": True})
            self.assertEqual(cmd[cmd.index("--bundle"):cmd.index("--bundle") + 4], ["--bundle", "x", "--bundle", "y"])
            self.assertIn("--validate", cmd)
            cmd, *_ = catalog.command(st, "texture_survey", {"folders": ["m1", "m2"], "reference": ["g1", "g2"]})
            self.assertEqual(cmd[cmd.index("--reference"):cmd.index("--reference") + 3], ["--reference", "g1", "g2"])
            self.assertIn("--out", cmd)                     # a required output defaults to the work folder
            cmd, *_ = catalog.command(st, "spec_sheets", {"out": tmp, "only": "WHITE_HOUSE CAPITOL"})
            self.assertEqual(cmd[-3:], ["--only", "WHITE_HOUSE", "CAPITOL"])
            cmd, *_ = catalog.command(st, "gr2_tree", {"model": "m.gr2", "mode": "--types"})
            self.assertEqual(cmd[-2:], ["m.gr2", "--types"])
            cmd, *_ = catalog.command(st, "gallery", {"out": os.path.join(tmp, "g.jpg"), "presets": "CAPITOL"})
            self.assertEqual(cmd[0], "blender")
            cmd, *_ = catalog.command(st, "make_bar", {"colour": "#11aa22"})
            self.assertEqual(cmd[cmd.index("--colour") + 1], "11AA22")
            # an output left empty goes to the work folder, never the tool's default in this program
            self.assertEqual(cmd[cmd.index("--out") + 1], os.path.join(tmp, "make_bar", "health_bar.ddt"))
            for tid in ("make_rings", "make_icons", "generate"):
                cmd, *_ = catalog.command(st, tid, {})
                self.assertEqual(cmd[cmd.index("--out") + 1], os.path.join(tmp, tid), tid)
            _, _, _, _, trial = catalog.command(st, "uncompress_models", {"copy": tmp})
            self.assertTrue(trial)
            for bad in ({"inputs": []}, {"inputs": ["a"], "factor": "x"}, {"inputs": ["a"], "nonsense": 1}):
                with self.assertRaises(catalog.ToolError):
                    catalog.command(st, "fix_bone_scale", bad)
            with self.assertRaises(catalog.ToolError):
                catalog.command(st, "make_rings", {"out": os.path.join(tmp, "steamapps", "x")})


class EveryFunctionReachesTheStudio(unittest.TestCase):
    """The rule of CLAUDE.md, without Blender: every operator in the add-on's sources has its
    place in studio/coverage.py, and every place named there exists."""

    def test_every_operator_has_a_place(self):
        from studio import coverage
        found = set()
        for name in ("__init__.py", "ai_panel.py"):
            with open(os.path.join(ROOT, "aoe3_blender_tools", name), encoding="utf-8") as fh:
                found |= set(re.findall(r'bl_idname = "(aoe3\.\w+)"', fh.read()))
        self.assertEqual(sorted(found - set(coverage.OPERATORS)), [],
                         "operators with no place in the studio: add them to studio/coverage.py")
        self.assertEqual(sorted(set(coverage.OPERATORS) - found), [])

    def test_every_place_exists(self):
        from studio import coverage
        with open(os.path.join(WEB, "js", "app.js"), encoding="utf-8") as fh:
            app = fh.read()
        for screen in coverage.SCREENS:
            self.assertTrue(f"head === '{screen}'" in app or f"id: '{screen}'" in app, screen)
        for op in coverage.OPERATORS:
            kind, target, note = coverage.place(op)
            self.assertIn(kind, ("screen", "tool", "pending"), op)
            if kind == "screen":
                self.assertIn(target, coverage.SCREENS, op)
            elif kind == "tool":
                self.assertIn(target, catalog.BY_ID, op)
            else:
                self.assertTrue(target, f"{op}: say why it is pending")

    def test_the_pending_list_is_in_the_documentation(self):
        from studio import coverage
        with open(os.path.join(ROOT, "docs", "studio.md"), encoding="utf-8") as fh:
            doc = fh.read()
        for op in coverage.pending():
            self.assertTrue(f"`{op}`" in doc, f"{op} is pending: docs/studio.md must say so")


class OneVersion(unittest.TestCase):
    def test_the_addon_the_studio_and_the_changelog_agree(self):
        import studio
        with open(os.path.join(ROOT, "aoe3_blender_tools", "blender_manifest.toml"), encoding="utf-8") as fh:
            manifest = re.search(r'^version = "([^"]+)"', fh.read(), re.M).group(1)
        with open(os.path.join(ROOT, "aoe3_blender_tools", "__init__.py"), encoding="utf-8") as fh:
            info = ".".join(re.search(r'"version": \((\d+), (\d+), (\d+)\)', fh.read()).groups())
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
            newest = re.search(r"^## (\d+\.\d+\.\d+)", fh.read(), re.M).group(1)
        self.assertEqual({manifest, info, studio.VERSION, newest}, {manifest})


class Languages(unittest.TestCase):
    def test_spanish_has_every_key(self):
        en, es = load_json("i18n", "en.json"), load_json("i18n", "es.json")
        self.assertEqual(sorted(set(en) - set(es)), [])
        for k in en:
            for var in re.findall(r"\{\w+\}", en[k]):
                self.assertIn(var, es[k], k)
        for f in schema.FIELDS:
            self.assertIn("param." + f.name, es, f.name)
            if f.help:
                self.assertIn(f"param.{f.name}.help", es, f.name)
            for value, _label, _help in f.choices:
                if f.name != "texture_size":
                    self.assertIn(f"choice.{f.name}.{value}", es, (f.name, value))
        for k in building.COLOR_KEYS:
            self.assertIn("color." + k, en)
            self.assertIn("color." + k, es)
        for k in settings.PATHS:
            self.assertIn(f"set.{k}", es)
            self.assertIn(f"set.{k}.help", es)

    def test_every_key_the_page_asks_for_exists(self):
        en = load_json("i18n", "en.json")
        dynamic = ("area.", "b.cam.", "color.", "group.", "nav.", "param.", "set.", "status.", "style.", "theme.",
                   "choice.")
        for name in os.listdir(os.path.join(WEB, "js")):
            with open(os.path.join(WEB, "js", name), encoding="utf-8") as fh:
                source = fh.read()
            for key in re.findall(r"(?<![\w.])t\('([^']+)'\s*[,)]", source):
                if not key.startswith(dynamic) or key in ("group.colors",):
                    self.assertIn(key, en, f"{name}: {key}")


class Settings(unittest.TestCase):
    def test_a_broken_file_starts_from_the_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "studio.json")
            with open(p, "w") as fh:
                fh.write("{ not json")
            s = settings.Settings(p)
            self.assertEqual(s.data["language"], "auto")
            s.update({"language": "en"})
            self.assertEqual(settings.Settings(p).data["language"], "en")


class Inspector(unittest.TestCase):
    """A model, its texture, a compiled XML and an archive, made here, looked inside."""

    def test_files_of_each_kind(self):
        import struct

        import numpy as np
        from aoe3game import ddt, gr2_write
        from studio import inspector
        import xmbedit
        with tempfile.TemporaryDirectory() as tmp:
            rgba = np.zeros((64, 64, 4), np.uint8)
            rgba[:, :, 0], rgba[:, :, 3] = 200, 255
            rgba[:8, :8, 3] = 0
            with open(os.path.join(tmp, "box.ddt"), "wb") as fh:
                fh.write(ddt.write(rgba))
            r = inspector.inspect(os.path.join(tmp, "box.ddt"))
            self.assertEqual((r["kind"], r["width"], r["height"]), ("ddt", 64, 64))
            self.assertGreater(r["alpha_zero"], 0)
            P = [(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)]
            data = gr2_write.static_model("box", P, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                          [(0, 1, 2), (0, 2, 3)], texture=r"C:\x\art\mod\box.ddt",
                                          bump=r"C:\x\art\mod\box_b.ddt", bones=[("bone_flag_civ", (1, 0, 3))])
            with open(os.path.join(tmp, "box.gr2"), "wb") as fh:
                fh.write(data)
            r = inspector.inspect(os.path.join(tmp, "box.gr2"))
            self.assertEqual((r["kind"], r["triangles"], r["vertices"]), ("gr2", 2, 4), r.get("error"))
            self.assertEqual(r["texture_name"], "box.ddt")           # its own texture, found beside it
            self.assertAlmostEqual(r["size"][2], 3.0, places=3)
            xml = b'<?xml version="1.0" encoding="utf-8"?>\n<root>\n  <unit name="House">x</unit>\n</root>\n'
            with open(os.path.join(tmp, "a.xml.xmb"), "wb") as fh:
                fh.write(xmbedit.wrap(xmbedit.encode(*xmbedit.from_xml(xml)), True))
            r = inspector.inspect(os.path.join(tmp, "a.xml.xmb"))
            self.assertEqual(r["kind"], "text")
            self.assertIn('name="House"', r["text"])
            # a .bar holding the texture: header, table at 0x11C, one entry
            with open(os.path.join(tmp, "box.ddt"), "rb") as fh:
                payload = fh.read()
            root, name = "Art\\", "units\\box.ddt"
            table = (struct.pack("<I", len(root)) + root.encode("utf-16-le") + struct.pack("<I", 1)
                     + struct.pack("<III", 0x124, len(payload), len(payload)) + b"\0" * 16
                     + struct.pack("<I", len(name)) + name.encode("utf-16-le"))
            head = bytearray(b"ESPN" + b"\0" * 0x120)
            struct.pack_into("<II", head, 0x118, 1, 0x124 + len(payload))
            with open(os.path.join(tmp, "Art1.bar"), "wb") as fh:
                fh.write(bytes(head) + payload + table)
            r = inspector.inspect(os.path.join(tmp, "Art1.bar"))
            self.assertEqual(r["entries"], [["Art\\units\\box.ddt", len(payload)]])
            r = inspector.inspect(os.path.join(tmp, "Art1.bar"), "Art\\units\\box.ddt")
            self.assertEqual((r["kind"], r["width"]), ("ddt", 64))
            with self.assertRaises(inspector.InspectError):
                inspector.inspect(os.path.join(tmp, "Art1.bar"), "nothing")


class FormHelp(unittest.TestCase):
    def test_every_option_has_its_help_in_both_languages(self):
        from studio import catalog_help
        missing = [f"{t.id}.{a.key}" for t in catalog.TOOLS for a in t.args
                   if not (a.help["en"].strip() and a.help["es"].strip())]
        self.assertEqual(missing, [], "options without help: add them to studio/catalog_help.py")
        known = {(t.id, a.key) for t in catalog.TOOLS for a in t.args}
        stale = [f"{t}.{k}" for t, opts in catalog_help.HELP.items() for k in opts if (t, k) not in known]
        self.assertEqual(stale, [], "help for options that no longer exist")

    def test_several_swatch_names_are_passed_one_by_one(self):
        cmd = catalog.command(None, "fetch_materials", {"names": "plaster clay"})[0]
        self.assertEqual(cmd[-2:], ["plaster", "clay"])


class InspectorCache(unittest.TestCase):
    def test_a_compressed_model_is_read_from_the_cache(self):
        """A model the game stores compressed is shown from its uncompressed copy in the cache,
        found by the original's MD5 (as tools/model_survey.py names them)."""
        import hashlib
        from unittest import mock
        from aoe3game import gr2
        from studio import inspector
        compressed = b"stands for a compressed model"
        with tempfile.TemporaryDirectory() as cache:
            os.makedirs(os.path.join(cache, "raw"))
            with open(os.path.join(cache, "raw", hashlib.md5(compressed).hexdigest() + ".gr2"), "wb") as fh:
                fh.write(b"the uncompressed copy")
            with mock.patch.object(gr2, "header_facts", return_value={"raw": False}):
                self.assertEqual(inspector._uncompressed(compressed, cache), b"the uncompressed copy")
                self.assertEqual(inspector._uncompressed(b"not in the cache", cache), b"not in the cache")
                self.assertEqual(inspector._uncompressed(compressed, None), compressed)


class Picker(unittest.TestCase):
    def test_the_picker_script_compiles(self):
        subprocess.run([sys.executable, "-I", "-m", "py_compile", os.path.join(ROOT, "studio", "picker.py")], check=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
