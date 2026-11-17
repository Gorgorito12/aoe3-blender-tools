# SPDX-License-Identifier: GPL-3.0-or-later
"""Starts the studio: the local server, then a window on it.

    python -m studio [--port N] [--no-window] [--config <settings.json>]

The window is Edge or Chrome in application mode with a profile of its own; without either, the
default browser. The studio stops a few seconds after its page closes (a reload keeps it), never
while a task runs, and closes the browser it started.
In a frozen build the same executable also runs a tool (`--run-tool <script> [args]`) and the
file dialog (`--pick`).
"""
import os
import subprocess
import sys
import time
import webbrowser


def _streams():
    """A windowed build starts without stdout and stderr: write to the pipes a parent gave, else
    nowhere."""
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", encoding="utf-8", errors="replace", closefd=False))
            except OSError:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _frozen_modes(argv):
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()     # a tool's worker process: runs its task and exits here
        _streams()
    if argv[:1] == ["--run-tool"]:          # a tool's script, as `python <script> args` would run it
        import runpy
        script = os.path.abspath(argv[1])
        folder, name = os.path.split(script)
        sys.argv = [script] + argv[2:]
        sys.path.insert(0, folder)
        # run as a module by its name, not by its path: a frozen program's process pool then
        # loads the script again in each worker (multiprocessing skips a path on frozen Windows),
        # so the functions the tool hands its workers are found there
        runpy.run_module(os.path.splitext(name)[0], run_name="__main__", alter_sys=True)
        sys.exit(0)
    if argv[:1] == ["--pick"]:
        from studio import picker
        sys.exit(picker.main())


BROWSERS = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/microsoft-edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")


def app_window(url, home):
    """Opens the page as an application window. Returns its process, or None (a browser tab)."""
    for exe in BROWSERS:
        if os.path.isfile(exe):
            profile = os.path.join(home, "window")
            os.makedirs(profile, exist_ok=True)
            return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                                     "--no-default-browser-check", "--window-size=1440,900"])
    webbrowser.open(url)
    return None


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    from studio import server, settings
    port = int(opt("--port", "0"))
    studio, httpd = server.serve(port, opt("--config"))
    url = f"http://127.0.0.1:{studio.port}/"
    print(f"AoE3 Mod Studio on {url}  (Ctrl+C stops it)", flush=True)
    alone = "--no-window" in argv              # served only: it runs until Ctrl+C
    window = None if alone else app_window(url, os.path.dirname(studio.settings.path) or settings.default_home())
    try:
        while True:
            time.sleep(1)
            # Edge keeps its processes after the window closes: the page saying goodbye is
            # what tells the studio its window is gone
            if not alone and studio.should_stop(time.time(), window is not None and window.poll() is not None):
                break
    except KeyboardInterrupt:
        pass
    studio.jobs.stop_all()
    httpd.shutdown()
    if window is not None and window.poll() is None:
        from studio.jobs import kill_tree
        kill_tree(window)                     # the browser started with the studio's own profile
    return 0


if __name__ == "__main__":
    _frozen_modes(sys.argv[1:])
    sys.exit(main(sys.argv[1:]))
