# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for ComfyUI's HTTP API, for tests without a GPU: it stores uploads, "runs" a
workflow by applying `transform` to the image its LoadImage node names, and serves the result
through /history and /view.

    with FakeComfy(transform=lambda rgb: 255 - rgb) as fake:
        client = comfy.Client(fake.url)
"""
import io
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import comfy, paint, pngio  # noqa: E402


def _png(rgb):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.png")
        paint.save_png(rgb, p)
        with open(p, "rb") as f:
            return f.read()


class FakeComfy:
    def __init__(self, transform=None, missing_nodes=(), models=True):
        self.transform = transform or (lambda rgb: rgb)
        self.inputs, self.outputs, self.history, self.prompts = {}, {}, {}, []
        self.missing_nodes = set(missing_nodes)
        self.models = models

    def object_info(self):
        info = {n: {"input": {"required": {}}} for n in comfy.NODES if n not in self.missing_nodes}
        if "CheckpointLoaderSimple" in info:
            info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[comfy.CHECKPOINT] if self.models else []]
        if "ControlNetLoader" in info:
            info["ControlNetLoader"]["input"]["required"]["control_net_name"] = [[comfy.CONTROLNET] if self.models else []]
        return info

    def handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                u = urlparse(self.path)
                if u.path == "/system_stats":
                    return self.send(200, {"system": {}})
                if u.path == "/object_info":
                    return self.send(200, fake.object_info())
                if u.path.startswith("/history/"):
                    pid = u.path.split("/")[-1]
                    return self.send(200, {pid: fake.history[pid]} if pid in fake.history else {})
                if u.path == "/view":
                    q = parse_qs(u.query)
                    return self.send(200, fake.outputs[q["filename"][0]], "image/png")
                self.send(404, {"error": "no"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n)
                if self.path == "/upload/image":
                    ctype = self.headers["Content-Type"]
                    boundary = ctype.split("boundary=")[1].encode()
                    for part in body.split(b"--" + boundary):
                        if b'name="image"' in part:
                            head, _, data = part.partition(b"\r\n\r\n")
                            name = head.split(b'filename="')[1].split(b'"')[0].decode()
                            fake.inputs[name] = data[:-2]
                            return self.send(200, {"name": name, "subfolder": "", "type": "input"})
                    return self.send(400, {"error": "no image"})
                if self.path == "/prompt":
                    wf = json.loads(body)["prompt"]
                    fake.prompts.append(wf)
                    load = next(v for v in wf.values() if v["class_type"] == "LoadImage")
                    rgb = pngio.read_png(fake.inputs[load["inputs"]["image"]])[:, :, :3]
                    out = fake.transform(rgb)
                    name = f"aoe3bt_{uuid.uuid4().hex[:8]}.png"
                    fake.outputs[name] = _png(out)
                    pid = uuid.uuid4().hex
                    save = next(k for k, v in wf.items() if v["class_type"] == "SaveImage")
                    fake.history[pid] = {"outputs": {save: {"images": [{"filename": name, "subfolder": "",
                                                                         "type": "output"}]}},
                                         "status": {"status_str": "success"}}
                    return self.send(200, {"prompt_id": pid, "node_errors": {}})
                self.send(404, {"error": "no"})
        return H

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
