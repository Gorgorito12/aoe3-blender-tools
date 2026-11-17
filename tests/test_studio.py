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
        cls.studio.jobs.stop_all()
        cls.httpd.shutdown()
        cls.httpd.server_close()
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


class Picker(unittest.TestCase):
    def test_the_picker_script_compiles(self):
        subprocess.run([sys.executable, "-I", "-m", "py_compile", os.path.join(ROOT, "studio", "picker.py")], check=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
