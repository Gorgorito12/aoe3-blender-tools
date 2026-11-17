# SPDX-License-Identifier: GPL-3.0-or-later
"""AoE3 Mod Studio: every tool of aoe3-blender-tools behind one window.

    python -m studio [--port N] [--no-window] [--config <settings.json>]

A local web application: `server.py` serves the page (`web/`) and a JSON API on 127.0.0.1 only;
building previews run in this process (`engine.py`), every longer task in a subprocess
(`jobs.py`); what needs Blender goes through `blender_bridge.py`.
"""
import os
import sys

VERSION = "0.1.0"
FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(__file__))
# the repository's root (in a frozen build: the folder the build put the tree in)
ROOT = os.path.join(sys._MEIPASS, "app") if FROZEN and hasattr(sys, "_MEIPASS") else os.path.dirname(HERE)
ADDON = os.path.join(ROOT, "aoe3_blender_tools")
WEB = os.path.join(HERE, "web") if not FROZEN else os.path.join(ROOT, "studio", "web")


def use_core():
    """Makes `core` and `aoe3game` importable as top-level packages (as the tools import them),
    which keeps Blender out of this process."""
    for p in (ADDON, os.path.join(ROOT, "tools")):
        if p not in sys.path:
            sys.path.insert(0, p)
