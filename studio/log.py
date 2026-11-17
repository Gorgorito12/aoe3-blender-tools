# SPDX-License-Identifier: GPL-3.0-or-later
"""The studio's log: what it started, how its tasks ended, and every error with its trace, in
studio.log beside the settings (%APPDATA%\\aoe3-blender-tools). A built program has no console:
without this file an error would be lost. Kept small: three files of 1 MB at most."""
import logging
import logging.handlers
import os
import sys
import threading

NAME = "studio.log"
log = logging.getLogger("studio")
_path = None


def setup(home):
    """Starts logging into `home`/studio.log (once per process); returns its path."""
    global _path
    path = os.path.join(home, NAME)
    if _path == path:
        return path
    os.makedirs(home, exist_ok=True)
    for h in list(log.handlers):
        log.removeHandler(h)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1 << 20, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    _path = path

    def thread_error(args):                 # an error in a worker thread is never lost either
        log.error("error in a thread", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thread_error
    previous = sys.excepthook

    def process_error(kind, value, tb):
        log.critical("the studio stopped on an error", exc_info=(kind, value, tb))
        previous(kind, value, tb)
    sys.excepthook = process_error
    return path


def close():
    """Closes the file (Windows keeps an open file's folder from being removed)."""
    global _path
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    _path = None


def path():
    return _path


def tail(lines=400):
    """The last lines of the log, for the page."""
    if not _path or not os.path.isfile(_path):
        return ""
    with open(_path, encoding="utf-8", errors="replace") as fh:
        return "".join(fh.readlines()[-lines:])
