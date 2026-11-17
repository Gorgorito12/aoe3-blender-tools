# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender, for what still needs it (the game export's mesh and icons, the checks, GLB/FBX/OBJ,
renders): the `bpy` module when this Python has it, else an installed Blender run in the
background (`blender -b --factory-startup -P <script> -- <args>`); every such script reads its
own options after `--`."""
import glob
import os
import re
import subprocess
import sys

from .jobs import python_command

SEARCH = (r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
          r"C:\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
          os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\Blender*\blender.exe"),
          "/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender", "/usr/local/bin/blender")
MIN_VERSION = (4, 2)                     # the add-on's manifest asks for 4.2


def _version_of_path(path):
    m = re.search(r"Blender[ _-]?(\d+)\.(\d+)", path)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_app(configured=""):
    """The newest Blender found (path, (major, minor)), or (None, None). A configured path wins."""
    if configured and os.path.isfile(configured):
        return configured, _version_of_path(configured)
    found = []
    for pattern in SEARCH:
        for p in glob.glob(pattern):
            if os.path.isfile(p):
                found.append((_version_of_path(p), p))
    if not found:
        return None, None
    version, path = max(found)
    return path, version


def has_module():
    """Whether this Python can import bpy (looked up, not imported: that takes seconds)."""
    if getattr(sys, "frozen", False):
        return False
    try:
        out = subprocess.run([sys.executable, "-I", "-c",
                              "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('bpy') else 1)"],
                             capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return out.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class Bridge:
    def __init__(self, settings):
        self.settings = settings
        self.refresh()

    def refresh(self):
        self.module = has_module()
        self.app, self.version = find_app(self.settings.get("blender"))
        return self.state()

    @property
    def available(self):
        if self.module:
            return True
        # a path that does not say its version (a configured one): let it try
        return self.app is not None and (self.version >= MIN_VERSION or self.version == (0, 0))

    def state(self):
        if self.module:
            return {"available": True, "mode": "module", "detail": "bpy module of this Python"}
        if self.app:
            v = ".".join(map(str, self.version)) if self.version != (0, 0) else "?"
            ok = self.available
            return {"available": ok, "mode": "app", "path": self.app, "version": v,
                    "detail": f"Blender {v}" + ("" if ok else f" (needs {MIN_VERSION[0]}.{MIN_VERSION[1]} or newer)")}
        return {"available": False, "mode": None, "detail": "Blender not found: install it, or set its path"}

    def command(self, script, args):
        """The command line that runs a Blender script with its options."""
        if self.module:
            return python_command() + [script] + list(args)
        if self.available:
            return [self.app, "-b", "--factory-startup", "--python-exit-code", "1", "-P", script, "--"] + list(args)
        raise RuntimeError("Blender is not available: install Blender 4.2 or newer, or set its path in Settings")
