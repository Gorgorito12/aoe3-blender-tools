# SPDX-License-Identifier: GPL-3.0-or-later
"""Long tasks, each in its own process: the tools print, call sys.exit, change module globals and
some start process pools, so a subprocess per task gives a live log, a real cancel and no harm
to the studio when one fails."""
import itertools
import os
import re
import subprocess
import sys
import threading
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # no console window for a task (Blender's)
MAX_LINES = 20000                      # a log keeps its last lines
# "12/200", "12 of 200", "40%": the last one a line shows is the job's progress
PROGRESS = re.compile(r"(?:(\d+)\s*(?:/|of)\s*(\d+)\b)|(?:(\d{1,3}(?:\.\d+)?)\s*%)")


class Job:
    def __init__(self, jid, title, cmd, cwd, outputs, tool=None, env=None):
        self.id = jid
        self.title = title
        self.cmd = cmd
        self.cwd = cwd
        self.outputs = list(outputs or [])
        self.tool = tool
        self.env = env
        self.status = "queued"
        self.code = None
        self.lines = []
        self.dropped = 0
        self.progress = None
        self.started = self.ended = None
        self.proc = None
        self.lock = threading.Lock()

    def add(self, line):
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > MAX_LINES:
                cut = len(self.lines) - MAX_LINES
                del self.lines[:cut]
                self.dropped += cut
            for m in PROGRESS.finditer(line):
                if m.group(1):
                    a, b = int(m.group(1)), int(m.group(2))
                    if 0 < b and a <= b:
                        self.progress = a / b
                else:
                    v = float(m.group(3))
                    if v <= 100:
                        self.progress = v / 100

    def public(self, since=0):
        with self.lock:
            start = max(0, since - self.dropped)
            return {"id": self.id, "title": self.title, "tool": self.tool, "status": self.status,
                    "code": self.code, "progress": self.progress, "outputs": self.outputs,
                    "started": self.started, "ended": self.ended, "command": _shown(self.cmd),
                    "lines": self.lines[start:], "next": self.dropped + len(self.lines)}


def _shown(cmd):
    return " ".join(f'"{a}"' if " " in a else a for a in cmd)


class Jobs:
    def __init__(self, keep=50):
        self.jobs = {}
        self.keep = keep
        self.ids = itertools.count(1)
        self.lock = threading.Lock()

    def start(self, title, cmd, cwd=None, outputs=(), tool=None, env=None):
        job = Job(str(next(self.ids)), title, [str(a) for a in cmd], cwd, outputs, tool, env)
        with self.lock:
            self.jobs[job.id] = job
            self._trim()
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _trim(self):
        done = [j for j in self.jobs.values() if j.status not in ("queued", "running")]
        for j in done[:max(0, len(self.jobs) - self.keep)]:
            del self.jobs[j.id]

    def _run(self, job):
        job.started = time.time()
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | NO_WINDOW) if os.name == "nt" else 0
        env = dict(os.environ)
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        env.update(job.env or {})
        try:
            job.proc = subprocess.Popen(job.cmd, cwd=job.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, creationflags=flags)
        except OSError as e:
            job.add(f"could not start: {e}")
            job.status, job.code, job.ended = "failed", -1, time.time()
            return
        job.status = "running"
        for raw in iter(job.proc.stdout.readline, b""):
            job.add(raw.decode("utf-8", "replace").rstrip("\r\n"))
        job.proc.wait()
        job.code = job.proc.returncode
        job.ended = time.time()
        if job.status != "cancelled":
            job.status = "done" if job.code == 0 else "failed"

    def get(self, jid):
        return self.jobs.get(jid)

    def all(self):
        with self.lock:
            return [{k: v for k, v in j.public(since=10 ** 12).items() if k != "lines"}
                    for j in reversed(list(self.jobs.values()))]

    def cancel(self, jid):
        job = self.jobs.get(jid)
        if not job or job.status not in ("queued", "running") or job.proc is None:
            return False
        job.status = "cancelled"
        job.add("cancelled")
        kill_tree(job.proc)
        return True

    def stop_all(self):
        for j in list(self.jobs.values()):
            if j.status == "running":
                self.cancel(j.id)


def kill_tree(proc):
    """Stops a process and the processes it started (a tool's worker pool)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    else:
        proc.kill()


def python_command():
    """How to run a tool's script with this Python: the interpreter itself, or in a frozen build
    the studio's own executable in its tool mode."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-tool"]
    return [sys.executable, "-I", "-X", "utf8"]
