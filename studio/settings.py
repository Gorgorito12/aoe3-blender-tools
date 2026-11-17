# SPDX-License-Identifier: GPL-3.0-or-later
"""The studio's settings: the folders and programs it works with, kept between sessions in
%APPDATA%\\aoe3-blender-tools\\studio.json (~/.config/aoe3-blender-tools elsewhere).

Nothing here is ever sent anywhere: the file stays on this computer.
"""
import json
import os
import threading

from . import use_core

use_core()
from aoe3game import deploy  # noqa: E402

LANGUAGES = ("auto", "en", "es")

# key -> (kind, what it is). kind: dir, file, url, text
PATHS = {
    "game": ("dir", "The game's installation (read only: the studio never writes into it)"),
    "mod": ("dir", "The mod's own folder, to survey its art"),
    "test_copy": ("dir", "A copy of the game to deploy into and test; a Steam folder is refused"),
    "work": ("dir", "Where the studio writes what it makes, unless a task says otherwise"),
    "cache": ("dir", "Caches of game files (extracted or rewritten models), outside the game and the repository"),
    "blender": ("file", "blender.exe, for the tasks that need Blender (found by itself when installed)"),
    "granny": ("file", "The Granny bridge (.exe) that reads compressed models through the game's granny2.dll"),
    "comfy_url": ("url", "The address of ComfyUI, for the AI tasks"),
    "comfy_dir": ("dir", "The ComfyUI folder (ComfyUI_windows_portable), to start it and train LoRAs"),
}
# folders the studio must never write into, whatever a task asks
NEVER_WRITE = ("game",)


def default_home():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "aoe3-blender-tools")


def default_work():
    return os.path.join(os.path.expanduser("~"), "Documents", "aoe3-studio")


def defaults():
    return {"language": "auto", "paths": {k: "" for k in PATHS} | {
        "comfy_url": "http://127.0.0.1:8188", "work": default_work()}, "recent": {}}


class SettingsError(ValueError):
    pass


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(default_home(), "studio.json")
        self.lock = threading.Lock()
        self.data = defaults()
        if os.path.isfile(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    saved = json.load(fh)
                self.data["language"] = saved.get("language", "auto") if saved.get("language") in LANGUAGES \
                    else "auto"
                for k, v in (saved.get("paths") or {}).items():
                    if k in PATHS and isinstance(v, str):
                        self.data["paths"][k] = v
                if isinstance(saved.get("recent"), dict):
                    self.data["recent"] = saved["recent"]
            except (OSError, ValueError):
                pass                                   # a broken file: start from the defaults

    def get(self, key):
        return self.data["paths"].get(key, "")

    def public(self):
        return {"language": self.data["language"], "paths": dict(self.data["paths"]),
                "recent": dict(self.data["recent"]), "file": self.path,
                "describe": {k: {"kind": v[0], "help": v[1]} for k, v in PATHS.items()}}

    def update(self, changes):
        """Checks and saves. Raises SettingsError naming the first bad value."""
        with self.lock:
            new = json.loads(json.dumps(self.data))
            if "language" in changes:
                if changes["language"] not in LANGUAGES:
                    raise SettingsError("language: one of " + ", ".join(LANGUAGES))
                new["language"] = changes["language"]
            for k, v in (changes.get("paths") or {}).items():
                if k not in PATHS:
                    raise SettingsError(f"unknown setting: {k}")
                v = (v or "").strip().strip('"')
                kind = PATHS[k][0]
                if v and kind == "dir" and k != "work" and not os.path.isdir(v):
                    raise SettingsError(f"{k}: no such folder: {v}")
                if v and kind == "file" and not os.path.isfile(v):
                    raise SettingsError(f"{k}: no such file: {v}")
                if v and kind == "url" and not v.startswith(("http://", "https://")):
                    raise SettingsError(f"{k}: an address starting with http://")
                if v and k in ("test_copy", "work", "cache"):
                    try:
                        deploy.refuse_steam(v)
                    except deploy.RefusedPath as e:
                        raise SettingsError(f"{k}: {e}") from None
                new["paths"][k] = v
            for k, v in (changes.get("recent") or {}).items():
                if isinstance(k, str) and isinstance(v, (str, int, float, bool, list, dict)):
                    new["recent"][k] = v
            self.data = new
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def check_output(self, path):
        """Refuses an output path inside the game's installation or a Steam library."""
        deploy.refuse_steam(path)
        game = self.get("game")
        if game:
            a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(game))
            if a == b or a.startswith(b + os.sep):
                raise deploy.RefusedPath(f"refusing to write inside the game's installation: {path}")
