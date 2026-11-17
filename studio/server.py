# SPDX-License-Identifier: GPL-3.0-or-later
"""The studio's local server: the page and a JSON API, on 127.0.0.1 only.

The API writes files and starts programs, so every API call must carry the token given to the
page when it loads (a page from another site cannot read it), and the Host and Origin headers
must name this server (no DNS rebinding)."""
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import VERSION, WEB, blender_bridge, catalog, engine, jobs, settings
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
        if self.bye_at and (self.last_ping is None or self.last_ping < self.bye_at) and now - self.bye_at > 5:
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
        except Exception as e:                              # a bug: say so, keep serving
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

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
    return schema.to_json() | {"styles": engine.styles(), "presets": engine.presets()}


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
        if opts.get("ai"):                  # repainted by the local ComfyUI (docs/ai-textures.md)
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
        return inspector.inspect(b.get("path") or "", b.get("entry"))
    except inspector.InspectError as e:
        raise ApiError(str(e)) from None


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
    ("POST", "/api/settings", r_settings),
    ("POST", "/api/refresh", r_refresh),
    ("GET", "/api/schema", r_schema),
    ("GET", "/api/preset/", r_preset),
    ("POST", "/api/building/random", r_random),
    ("POST", "/api/building/preview", r_preview),
    ("POST", "/api/building/sheet", r_sheet),
    ("POST", "/api/building/export", r_building_export),
    ("POST", "/api/inspect", r_inspect),
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
    handler = type("BoundHandler", (Handler,), {"studio": studio})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    studio.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return studio, httpd
