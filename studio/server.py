# SPDX-License-Identifier: GPL-3.0-or-later
"""The studio's local server: the page and a JSON API, on 127.0.0.1 only.

The API writes files and starts programs, so every API call must carry the token given to the
page when it loads (a page from another site cannot read it), and the Host and Origin headers
must name this server (no DNS rebinding)."""
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import VERSION, WEB, blender_bridge, catalog, engine, jobs, sessions, settings
from . import log as studio_log
from . import ROOT

MAX_BODY = 8 * 1024 * 1024
SHOWN = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".txt", ".md", ".json", ".xml", ".csv", ".log"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Studio:
    """Everything the handlers share."""

    def __init__(self, config=None):
        self.token = secrets.token_urlsafe(24)
        self.settings = settings.Settings(config)
        self.jobs = jobs.Jobs()
        self.bridge = blender_bridge.Bridge(self.settings)
        self.port = None
        self.started = time.time()
        self.roots = set()                  # folders whose files the page may show (outputs)
        self.trials = {}                    # a tool's values -> the job of its trial run
        self.last_ping = None               # when the page last called in
        self.bye_at = None                  # when a page said it was closing
        self.sessions = sessions.Sessions()  # what the made-to-measure screens have loaded

    # -- helpers ------------------------------------------------------------------------------
    def work_dir(self, *parts):
        base = self.settings.get("work") or settings.default_work()
        path = os.path.join(base, *parts)
        os.makedirs(path, exist_ok=True)
        self.roots.add(os.path.abspath(base))
        return path

    def output(self, path):
        """An output folder or file the user chose: checked, and shown afterwards."""
        if not path:
            raise ApiError("an output folder is needed")
        try:
            self.settings.check_output(path)
        except Exception as e:                      # deploy.RefusedPath
            raise ApiError(str(e)) from None
        self.roots.add(os.path.abspath(path if os.path.isdir(path) or not os.path.splitext(path)[1]
                                       else os.path.dirname(path)))
        return path

    def may_show(self, path):
        p = os.path.normcase(os.path.abspath(path))
        for r in self.roots:
            r = os.path.normcase(r)
            if p == r or p.startswith(r.rstrip("\\/") + os.sep):
                return True
        return False

    def should_stop(self, now, window_gone=False):
        """Whether a studio with its own window should stop: never while a task runs; soon after
        the page closed (unless a page came back: a reload); when its window's browser ended and
        the page is silent; when the page has been silent for ten minutes (it crashed)."""
        if any(j["status"] in ("queued", "running") for j in self.jobs.all()):
            return False
        # 12 s: longer than a page's ping (10 s), so another window still open keeps the studio
        if self.bye_at and (self.last_ping is None or self.last_ping < self.bye_at) and now - self.bye_at > 12:
            return True
        if window_gone and (self.last_ping is None or now - self.last_ping > 30):
            return True
        return bool(self.last_ping and now - self.last_ping > 600)

    def state(self):
        return {"version": VERSION, "settings": self.settings.public(), "blender": self.bridge.state(),
                "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False)),
                "requirements": catalog.requirements(self)}


class Handler(BaseHTTPRequestHandler):
    server_version = "AoE3Studio/" + VERSION
    studio = None                                   # set by serve()

    def log_message(self, fmt, *args):              # quiet: the window is the log
        pass

    # -- plumbing -----------------------------------------------------------------------------
    def _send(self, status, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        port = self.studio.port
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _auth(self):
        if not self._host_ok():
            raise ApiError("refused: unknown host or origin", 403)
        if not secrets.compare_digest(self.headers.get("X-Studio-Token", ""), self.studio.token):
            raise ApiError("refused: missing or wrong token", 403)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ApiError("request too large", 413)
        if not n:
            return {}
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ApiError("JSON expected", 415)
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            raise ApiError("bad JSON") from None

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        url = urlparse(self.path)
        path = url.path
        try:
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            if method == "POST" and path == "/api/bye":
                return self._bye()
            self._auth()
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            body = self._body() if method == "POST" else {}
            for route_method, prefix, fn in ROUTES:
                if route_method == method and (path == prefix or prefix.endswith("/") and path.startswith(prefix)):
                    result = fn(self.studio, path[len(prefix):] if prefix.endswith("/") else "", query, body)
                    if isinstance(result, tuple):           # (bytes, content type)
                        return self._send(200, result[0], result[1])
                    return self._send(200, result if result is not None else {"ok": True})
            raise ApiError("not found", 404)
        except ApiError as e:
            self._send(e.status, {"error": str(e)})
        except (ValueError, KeyError, OSError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:                              # a bug: say so, log it, keep serving
            traceback.print_exc()
            studio_log.log.exception("error answering %s %s", method, path)
            self._send(500, {"error": f"{type(e).__name__}: {e} (the details are in the log: Settings)"})

    def _bye(self):
        """The page is closing (navigator.sendBeacon: no headers of its own, so the token comes
        in the body). The studio stops if no page calls in again soon: a reload does."""
        if not self._host_ok():
            raise ApiError("refused: unknown host or origin", 403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 4096:
            raise ApiError("request too large", 413)
        try:
            token = json.loads(self.rfile.read(n).decode("utf-8") or "{}").get("token") or ""
        except (ValueError, AttributeError):
            token = ""
        if not secrets.compare_digest(str(token), self.studio.token):
            raise ApiError("refused: missing or wrong token", 403)
        self.studio.bye_at = time.time()
        self._send(200, {"ok": True})

    def _static(self, path):
        if not self._host_ok():
            return self._send(403, "refused", "text/plain")
        rel = unquote(path).lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(os.path.normpath(WEB) + os.sep) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".js"):
            ctype = "text/javascript"
        with open(full, "rb") as fh:
            data = fh.read()
        if rel == "index.html":
            data = data.replace(b"{{TOKEN}}", self.studio.token.encode()).replace(b"{{VERSION}}", VERSION.encode())
            ctype = "text/html; charset=utf-8"
        csp = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self._send(200, data, ctype, {"Content-Security-Policy": csp})


# -- routes ------------------------------------------------------------------------------------

def r_state(st, rest, q, b):
    return st.state()


def r_log(st, rest, q, b):
    return {"path": studio_log.path(), "text": studio_log.tail()}


def r_ping(st, rest, q, b):
    st.last_ping = time.time()
    return {"jobs": sum(1 for j in st.jobs.all() if j["status"] == "running")}


def r_settings(st, rest, q, b):
    try:
        st.settings.update(b)
    except settings.SettingsError as e:
        raise ApiError(str(e)) from None
    st.bridge.refresh()
    return st.state()


def r_refresh(st, rest, q, b):
    st.bridge.refresh()
    return st.state()


def r_schema(st, rest, q, b):
    from core import schema
    return schema.to_json() | {"styles": engine.styles(), "presets": engine.presets(), "sets": engine.prop_sets()}


def r_preset(st, rest, q, b):
    try:
        return engine.preset(rest)
    except KeyError as e:
        raise ApiError(str(e), 404) from None


def r_random(st, rest, q, b):
    return engine.random_params(b.get("style"), int(b.get("seed", 1)))


def r_preview(st, rest, q, b):
    size = b.get("texture")
    if size is not None and int(size) not in (128, 256, 512, 1024, 2048):
        raise ApiError("texture: 128 to 2048")
    return engine.preview(b.get("params") or {}, texture=int(size) if size else None,
                          damaged=bool(b.get("damaged")))


def r_sheet(st, rest, q, b):
    return engine.sheet(b.get("params") or {})


def r_building_export(st, rest, q, b):
    """Runs a building's export as a job: the game bundle (`game`), the GLB/FBX/OBJ files with
    renders (`files`)."""
    from core import schema
    params = schema.params_from_dict(b.get("params") or {})
    kind = b.get("kind")
    out = st.output(b.get("out") or os.path.join(st.work_dir("buildings"), params.name, kind or ""))
    os.makedirs(out, exist_ok=True)
    spec = os.path.join(st.work_dir("jobs"), f"{params.name}-{int(time.time() * 1000)}.json")
    with open(spec, "w", encoding="utf-8") as fh:
        json.dump(schema.params_to_dict(params), fh, indent=1)
    opts = b.get("options") or {}
    if kind == "game":
        args = ["--params", spec, "--out", out, "--prefix", opts.get("prefix") or "mod",
                "--texture", opts.get("texture_format") or "DXT3"]
        for flag in ("display", "template", "kind", "folder"):
            if opts.get(flag):
                args += ["--" + flag, str(opts[flag])]
        if opts.get("texture_png"):         # the texture the AI repaint tab made, as it was seen
            if not os.path.isfile(opts["texture_png"]):
                raise ApiError("the repainted texture is no longer there: repaint again")
            args += ["--texture-png", opts["texture_png"]]
        elif opts.get("ai"):                # repainted by the local ComfyUI (docs/ai-textures.md)
            strength = float(opts.get("ai_strength") or 0.45)
            if not 0.05 <= strength <= 0.95:
                raise ApiError("AI strength: 0.05 to 0.95")
            args += ["--ai", str(strength), "--ai-seed", str(int(opts.get("ai_seed") or 1)),
                     "--ai-url", st.settings.get("comfy_url") or "http://127.0.0.1:8188"]
        for flag, key in (("--no-icons", "no_icons"), ("--no-lowpoly", "no_lowpoly"),
                          ("--no-damaged", "no_damaged"), ("--player-colour", "player_colour"),
                          ("--materials", "materials")):
            if opts.get(key):
                args.append(flag)
        script = os.path.join(ROOT, "scripts", "game_export.py")
        title = f"Game export: {params.name}"
        if opts.get("no_blender"):          # experimental: scripts/game_export_noblender.py
            cmd = jobs.python_command() + [os.path.join(ROOT, "scripts", "game_export_noblender.py")] + args
            job = st.jobs.start(title + " (without Blender)", cmd, cwd=ROOT, outputs=[out], tool="building_game")
            return {"job": job.id, "out": out}
    elif kind == "files":
        args = ["--params", spec, "--out", out]
        views = opts.get("views")
        args += ["--views", ",".join(views)] if views else ["--no-render"]
        script = os.path.join(ROOT, "scripts", "generate.py")
        title = f"Export files: {params.name}"
    else:
        raise ApiError("kind: game or files")
    try:
        cmd = st.bridge.command(script, args)
    except RuntimeError as e:
        raise ApiError(str(e)) from None
    job = st.jobs.start(title, cmd, cwd=ROOT, outputs=[out], tool="building_" + kind)
    return {"job": job.id, "out": out}


def r_inspect(st, rest, q, b):
    from . import inspector
    try:
        return inspector.inspect(b.get("path") or "", b.get("entry"), st.settings.get("cache") or None)
    except inspector.InspectError as e:
        raise ApiError(str(e)) from None


def _retex():
    from . import retex
    return retex


def r_retex_load(st, rest, q, b):
    """A unit (of the game copy) or a model file, with its texture and its UV islands."""
    rx = _retex()
    work = st.work_dir("retexture")
    s = st.settings
    common = {"scale": int(b.get("scale") or 1), "by": b.get("by") or "bone",
              "cache": s.get("cache") or None, "granny": s.get("granny") or None}
    try:
        if b.get("source") == "game":
            game = b.get("game") or s.get("game")
            if not game:
                raise ApiError("set the game's folder in Settings, or load a model file")
            prefer = [x.strip() for x in (b.get("prefer") or "").split(",") if x.strip()]
            session = rx.load_game(work, game, (b.get("target") or "").strip(), prefer=prefer,
                                   overlay=b.get("overlay") or None, **common)
        else:
            if not b.get("model"):
                raise ApiError("a model file (.gr2) is needed")
            session = rx.load_files(work, b["model"], b.get("texture") or None, **common)
    except rx.RetexError as e:
        raise ApiError(str(e)) from None
    st.roots.add(os.path.abspath(session.folder))
    return dict(rx.public(session), session=st.sessions.add(session))


def r_retex_paint(st, rest, q, b):
    rx = _retex()
    try:
        return rx.paint(st.sessions.get(b.get("session")), b.get("ops") or [])
    except rx.RetexError as e:
        raise ApiError(str(e)) from None


def r_retex_picture(st, rest, q, b):
    rx = _retex()
    try:
        return {"name": rx.add_picture(st.sessions.get(b.get("session")), b.get("name"), b.get("data"))}
    except rx.RetexError as e:
        raise ApiError(str(e)) from None


def r_retex_save(st, rest, q, b):
    """Writes the recipe, then the retexture tool writes the texture, its bump map and a sheet."""
    rx = _retex()
    session = st.sessions.get(b.get("session"))
    try:
        recipe = rx.save(session, b.get("ops") or [], out=b.get("out") or "new", fmt=b.get("format") or "same",
                         mips=b.get("mips") or "same", bump=bool(b.get("bump", True)),
                         bump_strength=float(b.get("bump_strength") or 6.0))
    except rx.RetexError as e:
        raise ApiError(str(e)) from None
    cmd = jobs.python_command() + [os.path.join(ROOT, "tools", "retexture.py"), recipe,
                                   "--preview", os.path.join(session.folder, "sheet.png"),
                                   "--url", st.settings.get("comfy_url") or "http://127.0.0.1:8188"]
    job = st.jobs.start(f"Repaint: {session.name}", cmd, cwd=ROOT, outputs=[session.folder], tool="retexture")
    return {"job": job.id, "recipe": recipe, "folder": session.folder}


def _flags():
    from . import flags
    return flags


DEFAULT_FLAGS = ("War of the Triple Alliance\\Flags", "War of the Triple Alliance\\Buttons")   # make_flag.py's


def r_flags_measure(st, rest, q, b):
    """A game copy's flag sets, measured once for the designer."""
    fl = _flags()
    try:
        m = fl.measure(b.get("game") or st.settings.get("game"), b.get("flags_dir") or DEFAULT_FLAGS[0],
                       b.get("buttons_dir") or DEFAULT_FLAGS[1])
    except fl.FlagError as e:
        raise ApiError(str(e)) from None
    return dict(fl.public(m), session=st.sessions.add(m))


def r_flags_preview(st, rest, q, b):
    fl = _flags()
    try:
        m = st.sessions.get(b.get("session"))
        if b.get("existing"):
            return fl.existing(m, b["existing"])
        return fl.preview(m, b.get("design"), b.get("crop"))
    except fl.FlagError as e:
        raise ApiError(str(e)) from None


def r_flags_write(st, rest, q, b):
    fl = _flags()
    m = st.sessions.get(b.get("session"))
    name = b.get("name") or ""
    out = st.output(b.get("out") or os.path.join(st.work_dir("flags"), name or "flag"))
    try:
        return fl.write(m, b.get("design"), b.get("crop"), name, out)
    except fl.FlagError as e:
        raise ApiError(str(e)) from None


def _tex():
    from . import texmaker_ui
    return texmaker_ui


def r_results(st, rest, q, b):
    """A survey's result (a report or a profile) as a table; `profile`: one of this program's."""
    from . import results
    from . import ADDON
    name = b.get("profile")
    if name:
        if name not in ("textures", "models"):
            raise ApiError("profile: textures or models")
        path = os.path.join(ADDON, "profiles", name + ".json")
    else:
        path = b.get("path") or ""
    try:
        return results.table(path)
    except results.ResultsError as e:
        raise ApiError(str(e)) from None


def _settle():
    from . import settlement_ui
    return settlement_ui


def r_settlement_measured(st, rest, q, b):
    """What the composer lays out by: the mod's settlements as measured."""
    return _settle().measured()


def r_settlement_compose(st, rest, q, b):
    se = _settle()
    try:
        units = se.compose(b.get("units"), socket=b.get("socket") or "", obstruction=b.get("obstruction") or "",
                           seed=int(b.get("seed") or 1), counts=b.get("counts"))
    except (se.SettlementError, TypeError, ValueError) as e:
        raise ApiError(str(e)) from None
    return {"units": units, "meta": None}


def r_settlement_open(st, rest, q, b):
    se = _settle()
    path = b.get("path") or ""
    if not os.path.isfile(path):
        raise ApiError(f"no such file: {path}")
    try:
        return dict(se.read(path), path=path)
    except se.SettlementError as e:
        raise ApiError(str(e)) from None


def r_settlement_save(st, rest, q, b):
    """Writes the grouping file: into the work folder unless a path is given (never the game's)."""
    se = _settle()
    name = (b.get("name") or "").strip()
    if not b.get("path") and not re.match(r"^[A-Za-z0-9_ .-]{1,80}$", name):
        raise ApiError("the grouping's name: letters, digits, spaces, _ . -")
    path = b.get("path") or os.path.join(st.work_dir("settlements"),
                                         name if name.lower().endswith(".xml") else name + ".xml")
    st.output(path)
    try:
        return {"path": se.write(path, b.get("units") or [], b.get("meta"))}
    except se.SettlementError as e:
        raise ApiError(str(e)) from None


def r_tex_source(st, rest, q, b):
    """The photograph a texture is made from (the page decodes it and sends it as a PNG)."""
    tx = _tex()
    folder = os.path.join(st.work_dir("textures"), time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3))
    try:
        src = tx.Source(b.get("data"), folder)
    except tx.TexError as e:
        raise ApiError(str(e)) from None
    h, w = src.rgb.shape[:2]
    return {"session": st.sessions.add(src), "width": w, "height": h}


def r_tex_preview(st, rest, q, b):
    tx = _tex()
    try:
        return tx.preview(st.sessions.get(b.get("session")), b)
    except tx.TexError as e:
        raise ApiError(str(e)) from None


def r_tex_keep(st, rest, q, b):
    tx = _tex()
    try:
        entry = tx.keep(st.sessions.get(b.get("session")), b, b.get("folder") or None)
    except tx.TexError as e:
        raise ApiError(str(e)) from None
    return {"entry": entry, "library": tx.library(b.get("folder") or None)}


def r_tex_ai(st, rest, q, b):
    """The same crop repainted by ComfyUI, as a task (tools/make_texture.py)."""
    tx = _tex()
    src = st.sessions.get(b.get("session"))
    try:
        cmd = tx.ai_command(src, b, jobs.python_command(), os.path.join(ROOT, "tools", "make_texture.py"),
                            st.settings.get("comfy_url") or "http://127.0.0.1:8188")
    except tx.TexError as e:
        raise ApiError(str(e)) from None
    job = st.jobs.start(f"Texture with AI: {b.get('name')}", cmd, cwd=ROOT, tool="make_texture")
    return {"job": job.id}


def r_tex_library(st, rest, q, b):
    return _tex().library(b.get("folder") or None)


def r_tex_use(st, rest, q, b):
    """The library under the painter, or the add-on's swatches back: the building previews and
    exports of this studio then show it."""
    tx = _tex()
    with engine._lock:                    # the painter's table must not change under a preview
        return {"in_use": tx.use(bool(b.get("on")), b.get("folder") or None)}


def r_tex_delete(st, rest, q, b):
    tx = _tex()
    try:
        tx.delete(b.get("name"), b.get("folder") or None)
    except tx.TexError as e:
        raise ApiError(str(e)) from None
    return tx.library(b.get("folder") or None)


def _ai():
    from . import airepaint_ui
    return airepaint_ui


def r_ai_regions(st, rest, q, b):
    return _ai().regions(b.get("params") or {})


def r_ai_start(st, rest, q, b):
    """The building's texture repainted by ComfyUI region by region, in a thread of the studio."""
    ai = _ai()
    which = b.get("regions")
    if which is not None and not isinstance(which, list):
        raise ApiError("regions: a list of names, or nothing for all")
    try:
        run = ai.Run(b.get("params") or {}, st.settings.get("comfy_url") or "http://127.0.0.1:8188",
                     strength=b.get("strength", 0.45), seed=b.get("seed", 1), regions=which,
                     blend=b.get("blend", 1.0), prompt=b.get("prompt") or "", extra=b.get("extra") or "",
                     guard=b.get("guard", True))
    except ai.AiError as e:
        raise ApiError(str(e)) from None
    return {"session": st.sessions.add(run)}


def r_ai_state(st, rest, q, b):
    return st.sessions.get(b.get("session")).state(int(b.get("since", -1)))


def r_ai_cancel(st, rest, q, b):
    st.sessions.get(b.get("session")).cancel()
    return {"ok": True}


def r_ai_save(st, rest, q, b):
    ai = _ai()
    try:
        path = st.sessions.get(b.get("session")).save(st.work_dir("ai"))
    except ai.AiError as e:
        raise ApiError(str(e)) from None
    return {"path": path}


def r_building_set(st, rest, q, b):
    """A prop set's preview: its variations side by side, on their one texture."""
    try:
        return engine.set_preview(b.get("set") or "", b.get("texture") or 256, b.get("seed") or 1)
    except KeyError as e:
        raise ApiError(str(e)) from None


def r_building_check(st, rest, q, b):
    """The add-on's game-ready checks on the building on screen, as a task (they need Blender);
    the page reads its lines as JSON."""
    from core import schema
    params = schema.params_from_dict(b.get("params") or {})
    spec = os.path.join(st.work_dir("jobs"), f"{params.name}-check-{int(time.time() * 1000)}.json")
    with open(spec, "w", encoding="utf-8") as fh:
        json.dump(schema.params_to_dict(params), fh)
    script, args = os.path.join(ROOT, "scripts", "check.py"), ["--params", spec, "--json"]
    if st.bridge.available or st.bridge.module:
        cmd = st.bridge.command(script, args)
    else:                                   # the same rules without Blender (core/checks.py)
        cmd = jobs.python_command() + [script] + args + ["--no-blender"]
    job = st.jobs.start(f"Check: {params.name}", cmd, cwd=ROOT, tool="check")
    return {"job": job.id}


def _comfy_url(st):
    return st.settings.get("comfy_url") or "http://127.0.0.1:8188"


def r_comfy_check(st, rest, q, b):
    """Is ComfyUI running, with the nodes and models the repaint needs? (the add-on's Check)"""
    from core import comfy
    try:
        problems = comfy.Client(_comfy_url(st), timeout=5).check()
    except comfy.ComfyError as e:
        return {"running": False, "problems": [str(e)]}
    return {"running": True, "problems": problems}


def r_comfy_start(st, rest, q, b):
    """Starts the portable ComfyUI of Settings in its own console window (the add-on's Start)."""
    from core import comfy
    url = _comfy_url(st)
    if comfy.Client(url, timeout=3).alive():
        return {"started": False, "already": True}
    root = st.settings.get("comfy_dir")
    exe = os.path.join(root or "", "python_embeded", "python.exe")
    main = os.path.join(root or "", "ComfyUI", "main.py")
    if not root or not (os.path.isfile(exe) and os.path.isfile(main)):
        raise ApiError("set the ComfyUI folder (ComfyUI_windows_portable) in Settings")
    port = url.rstrip("/").rsplit(":", 1)[-1]
    port = port if port.isdigit() else "8188"
    subprocess.Popen([exe, "-s", main, "--windows-standalone-build", "--listen", "127.0.0.1", "--port", port,
                      "--disable-auto-launch"], cwd=root, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return {"started": True, "already": False}


def r_check_path(st, rest, q, b):
    """What a path given in Settings or the welcome is, at once: [(level, note)] and whether it
    can be saved. Nothing is written."""
    from aoe3game import deploy
    key, path = b.get("key"), (b.get("path") or "").strip().strip('"')
    if key not in settings.PATHS:
        raise ApiError("unknown setting")
    notes, ok = [], True
    if not path:
        return {"ok": True, "notes": [["info", "empty"]]}
    kind = settings.PATHS[key][0]
    if kind == "url":
        return {"ok": path.startswith(("http://", "https://")), "notes": [["info", "address"]]}
    exists = os.path.isfile(path) if kind == "file" else os.path.isdir(path)
    if not exists and key != "work":
        return {"ok": False, "notes": [["bad", "missing"]]}
    try:
        deploy.refuse_steam(path)
        steam = False
    except deploy.RefusedPath:
        steam = True
    if key in ("game", "test_copy", "mod"):
        has_art = os.path.isdir(os.path.join(path, "art"))
        has_data = os.path.isdir(os.path.join(path, "data"))
        notes.append(["ok" if has_art else "bad", "art" if has_art else "no_art"])
        if key != "mod":
            notes.append(["ok" if has_data else "bad", "data" if has_data else "no_data"])
            ok = ok and has_art and has_data
        else:
            ok = ok and has_art
    if steam:
        if key in ("test_copy", "work", "cache"):
            notes.append(["bad", "steam_refused"])
            ok = False
        elif key == "game":
            notes.append(["info", "steam_read_only"])
    if key == "comfy_dir":
        portable = (os.path.isfile(os.path.join(path, "python_embeded", "python.exe"))
                    and os.path.isfile(os.path.join(path, "ComfyUI", "main.py")))
        notes.append(["ok" if portable else "bad", "comfy_portable" if portable else "comfy_not_portable"])
        ok = ok and portable
    if key == "test_copy" and ok and st.settings.get("game") and \
            os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(st.settings.get("game"))):
        notes.append(["bad", "same_as_game"])
        ok = False
    if ok and not notes:
        notes.append(["ok", "found"])
    return {"ok": ok, "notes": notes}


def _game(st):
    """The game copy of Settings, read on demand and kept (tools/named_models.py)."""
    import named_models
    folder = st.settings.get("game")
    if not folder or not os.path.isdir(folder):
        raise ApiError("set the game's folder in Settings")
    cached = getattr(st, "_game", None)
    if cached is None or cached.folder != folder:
        cached = st._game = named_models.Game(folder)
    return cached


def r_game_units(st, rest, q, b):
    """The game's units whose name holds the words typed, for the unit repaint's search."""
    game = _game(st)
    try:
        protos = game.protos()
    except (OSError, LookupError, ValueError) as e:
        raise ApiError(f"the game's unit list could not be read: {e}") from None
    words = [w for w in str(b.get("q") or "").lower().split() if w]
    found = [{"name": name, "anim": anim} for key, (name, anim) in sorted(protos.items())
             if anim and all(w in key for w in words)]
    return {"units": found[:60], "more": len(found) > 60, "count": len(found)}


def r_game_flagdirs(st, rest, q, b):
    """The folders of a game copy's art that hold flag sets (buttons, and the flags beside them)."""
    game = b.get("game") or st.settings.get("game")
    art = os.path.join(game or "", "art")
    if not os.path.isdir(art):
        raise ApiError("a game copy (a folder with art) is needed")
    buttons, flags = {}, {}
    for base, dirs, files in os.walk(art):
        depth = os.path.relpath(base, art).count(os.sep)
        if depth >= 4:
            dirs[:] = []
        low = [f.lower() for f in files]
        rel = os.path.relpath(base, art)
        n = sum(1 for f in low if f.startswith("flag_") and f.endswith("_normal.ddt") and "_large_" not in f)
        if n:
            buttons[rel] = n
        m = sum(1 for f in low if f.startswith("ingame_ui_postgame_flag_") and f.endswith(".ddt"))
        if m:
            flags[rel] = m
    pairs = []
    for b_rel, n in sorted(buttons.items(), key=lambda kv: -kv[1]):
        sibling = os.path.join(os.path.dirname(b_rel), "Flags")
        f_rel = next((f for f in flags if f.lower() == sibling.lower()), None) or \
            (max(flags, key=lambda f: flags[f]) if flags else None)
        if f_rel:
            pairs.append({"buttons": b_rel, "flags": f_rel, "sets": n})
    return {"pairs": pairs}


def r_deploy_state(st, rest, q, b):
    """What a test copy has deployed (its manifest), read only: the page decides from it whether a
    new building is added, updated or replaces everything."""
    from aoe3game import deploy
    install = b.get("install") or st.settings.get("test_copy")
    try:
        d = deploy.Deployment(install or "")
    except deploy.RefusedPath as e:
        raise ApiError(str(e)) from None
    m = d.manifest()

    def name_of(path):
        try:
            with open(os.path.join(path, "bundle.json"), encoding="utf-8") as fh:
                return json.load(fh).get("name")
        except (OSError, ValueError):
            return None
    bundles = [{"path": path, "name": name_of(path), "exists": name_of(path) is not None}
               for path in m.get("bundles") or ([m["bundle"]] if m.get("bundle") else [])]
    return {"units": m.get("units", []), "bundles": bundles, "builder": m.get("builder"),
            "groupings": m.get("groupings", []), "files": len(m.get("created", [])) + len(m.get("modified", {})),
            "new": name_of(b["bundle"]) if b.get("bundle") else None}


def r_jobs(st, rest, q, b):
    return st.jobs.all()


def r_job(st, rest, q, b):
    job = st.jobs.get(rest)
    if not job:
        raise ApiError("no such job", 404)
    return job.public(int(q.get("since", 0)))


def r_cancel(st, rest, q, b):
    return {"cancelled": st.jobs.cancel(rest)}


def r_catalog(st, rest, q, b):
    return catalog.to_json(st)


def r_run_tool(st, rest, q, b):
    try:
        cmd, title, outputs, cwd, trial = catalog.command(st, rest, b.get("values") or {}, bool(b.get("apply")))
    except catalog.ToolError as e:
        raise ApiError(str(e)) from None
    for o in outputs:
        st.output(o)
    job = st.jobs.start(title, cmd, cwd=cwd, outputs=outputs, tool=rest)
    if trial:
        st.trials[trial] = job.id
    return {"job": job.id, "trial": bool(trial)}


def r_pick(st, rest, q, b):
    """A native file or folder dialog, run in its own process (Tk wants its own main thread)."""
    mode = b.get("mode", "file")
    if mode not in ("file", "files", "folder", "save"):
        raise ApiError("mode: file, files, folder or save")
    cmd = [sys.executable, "--pick"] if getattr(sys, "frozen", False) else \
        jobs.python_command() + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "picker.py")]
    payload = json.dumps({"mode": mode, "title": b.get("title") or "", "initial": b.get("initial") or "",
                          "filters": b.get("filters") or []})
    try:
        out = subprocess.run(cmd, input=payload.encode("utf-8"), capture_output=True, cwd=ROOT, timeout=3600,
                             creationflags=jobs.NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"path": None}
    try:
        return json.loads(out.stdout.decode("utf-8") or "{}")
    except ValueError:
        raise ApiError("the file dialog failed: " + out.stderr.decode("utf-8", "replace")[-300:]) from None


def r_open(st, rest, q, b):
    """Shows a folder (or the folder of a file) in the file manager. Never runs a file."""
    path = b.get("path") or ""
    if not os.path.exists(path):
        raise ApiError("no such file or folder")
    if os.name == "nt":
        if os.path.isdir(path):
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open",
                          path if os.path.isdir(path) else os.path.dirname(path)])
    return {"ok": True}


def r_file(st, rest, q, b):
    """An output's image or text, for the page to show."""
    path = q.get("path") or ""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SHOWN or not os.path.isfile(path) or not st.may_show(path):
        raise ApiError("not an output this studio may show", 403)
    if os.path.getsize(path) > 64 * 1024 * 1024:
        raise ApiError("too large to show", 413)
    with open(path, "rb") as fh:
        data = fh.read()
    ctype = mimetypes.guess_type(path)[0] or "text/plain"
    if ctype.startswith("text/") or ext in (".md", ".json", ".log", ".xml"):
        ctype = "text/plain; charset=utf-8"
    return data, ctype


def r_list(st, rest, q, b):
    """The files of an output folder (one level, or every level with deep=1)."""
    path = q.get("path") or ""
    if not os.path.isdir(path) or not st.may_show(path):
        raise ApiError("not an output folder", 403)
    out = []
    deep = q.get("deep") == "1"
    for base, dirs, files in os.walk(path):
        for f in files:
            full = os.path.join(base, f)
            out.append({"path": full, "rel": os.path.relpath(full, path), "size": os.path.getsize(full)})
            if len(out) >= 2000:
                return {"files": out, "more": True}
        if not deep:
            break
    return {"files": out, "more": False}


ROUTES = [
    ("GET", "/api/state", r_state),
    ("POST", "/api/ping", r_ping),
    ("GET", "/api/log", r_log),
    ("POST", "/api/settings", r_settings),
    ("POST", "/api/refresh", r_refresh),
    ("GET", "/api/schema", r_schema),
    ("GET", "/api/preset/", r_preset),
    ("POST", "/api/building/random", r_random),
    ("POST", "/api/building/preview", r_preview),
    ("POST", "/api/building/sheet", r_sheet),
    ("POST", "/api/building/export", r_building_export),
    ("POST", "/api/building/check", r_building_check),
    ("POST", "/api/building/set", r_building_set),
    ("POST", "/api/comfy/check", r_comfy_check),
    ("POST", "/api/comfy/start", r_comfy_start),
    ("POST", "/api/check-path", r_check_path),
    ("POST", "/api/deploy/state", r_deploy_state),
    ("POST", "/api/game/units", r_game_units),
    ("POST", "/api/game/flagdirs", r_game_flagdirs),
    ("POST", "/api/inspect", r_inspect),
    ("POST", "/api/retex/load", r_retex_load),
    ("POST", "/api/retex/paint", r_retex_paint),
    ("POST", "/api/retex/picture", r_retex_picture),
    ("POST", "/api/retex/save", r_retex_save),
    ("POST", "/api/results", r_results),
    ("POST", "/api/settlement/measured", r_settlement_measured),
    ("POST", "/api/settlement/compose", r_settlement_compose),
    ("POST", "/api/settlement/open", r_settlement_open),
    ("POST", "/api/settlement/save", r_settlement_save),
    ("POST", "/api/flags/measure", r_flags_measure),
    ("POST", "/api/flags/preview", r_flags_preview),
    ("POST", "/api/flags/write", r_flags_write),
    ("POST", "/api/tex/source", r_tex_source),
    ("POST", "/api/tex/preview", r_tex_preview),
    ("POST", "/api/tex/keep", r_tex_keep),
    ("POST", "/api/tex/ai", r_tex_ai),
    ("POST", "/api/tex/library", r_tex_library),
    ("POST", "/api/tex/use", r_tex_use),
    ("POST", "/api/tex/delete", r_tex_delete),
    ("POST", "/api/ai/regions", r_ai_regions),
    ("POST", "/api/ai/start", r_ai_start),
    ("POST", "/api/ai/state", r_ai_state),
    ("POST", "/api/ai/cancel", r_ai_cancel),
    ("POST", "/api/ai/save", r_ai_save),
    ("GET", "/api/jobs", r_jobs),
    ("GET", "/api/jobs/", r_job),
    ("POST", "/api/cancel/", r_cancel),
    ("GET", "/api/catalog", r_catalog),
    ("POST", "/api/tools/", r_run_tool),
    ("POST", "/api/pick", r_pick),
    ("POST", "/api/open", r_open),
    ("GET", "/api/file", r_file),
    ("GET", "/api/list", r_list),
]


def serve(port=0, config=None):
    """Starts the server in a thread; returns (studio, httpd)."""
    studio = Studio(config)
    studio_log.setup(os.path.dirname(studio.settings.path))
    handler = type("BoundHandler", (Handler,), {"studio": studio})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    studio.port = httpd.server_address[1]
    studio_log.log.info("studio %s on port %s (%s, Python %s)", VERSION, studio.port,
                        "built program" if getattr(sys, "frozen", False) else "from the repository",
                        sys.version.split()[0])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return studio, httpd
