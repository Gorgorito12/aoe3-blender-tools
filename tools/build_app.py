# SPDX-License-Identifier: GPL-3.0-or-later
"""Build AoE3 Mod Studio as a program for people without Python: a folder with the studio's
executable, Python, numpy and Tk, and the repository's own files beside them (the add-on's core
and game formats, the tools, the Blender scripts, the page). No Blender inside: the studio finds
an installed one for the tasks that need it.

    python -I tools/build_app.py [--out dist] [--zip] [--console]

Run it with a Python that has PyInstaller and numpy (pip install pyinstaller numpy), not the venv
with bpy: Blender as a module is 650 MB and the studio never imports it. Writes
<out>/AoE3ModStudio/AoE3ModStudio.exe (and with --zip, <out>/AoE3ModStudio-<version>-<platform>.zip).

The tools are not frozen: the executable runs their scripts as Python files (`--run-tool`), so
every standard library module they import is handed to PyInstaller, read from their sources at
build time. The build then runs one tool through the executable to check it.
"""
import ast
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "AoE3ModStudio"
# what goes into the build beside the executable, under app/ (the studio's ROOT when frozen)
DATA = ("aoe3_blender_tools", "tools", "scripts", os.path.join("studio", "web"), "LICENSE", "README.md")
SKIP_DIRS = {"__pycache__", ".git", "venv", "dist", "out", "survey", "examples", "tests", "docs"}
# modules the frozen interpreter must hold although the studio itself never imports them
THIRD_PARTY = ("numpy",)


def _is_module(name):
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def stdlib_imports(folders=("tools", "scripts", "aoe3_blender_tools")):
    """Every standard library module a script of these folders imports (top-level names)."""
    names = set()
    std = set(sys.stdlib_module_names)
    for folder in folders:
        for base, dirs, files in os.walk(os.path.join(ROOT, folder)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(base, f), encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        # `from xml.etree import ElementTree` imports a module; `from os import path` a name
                        mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names
                                                if _is_module(f"{node.module}.{a.name}")]
                    else:
                        continue
                    for m in mods:
                        if m.split(".")[0] in std:
                            names.add(m)
    return sorted(names)


def version():
    sys.path.insert(0, ROOT)
    import studio
    return studio.VERSION


def copy_data(dest):
    for item in DATA:
        src = os.path.join(ROOT, item)
        dst = os.path.join(dest, item)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            continue
        for base, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith((".pyc", ".blend1")):
                    continue
                s = os.path.join(base, f)
                d = os.path.join(dst, os.path.relpath(s, src))
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller is needed: pip install pyinstaller numpy (in a Python without bpy)")
        return 2
    out = os.path.abspath(opt("--out", os.path.join(ROOT, "dist")))
    work = os.path.join(out, "build-studio")
    hidden = stdlib_imports() + list(THIRD_PARTY) + ["tkinter", "tkinter.filedialog"]
    args = [os.path.join(ROOT, "studio", "__main__.py"), "--name", NAME, "--noconfirm", "--clean",
            "--distpath", out, "--workpath", work, "--specpath", work, "--paths", ROOT,
            "--icon", os.path.join(ROOT, "studio", "web", "icon.ico"),
            "--exclude-module", "bpy", "--exclude-module", "matplotlib", "--exclude-module", "PIL"]
    args += [] if "--console" in argv else ["--noconsole"]
    for m in hidden:
        args += ["--hidden-import", m]
    if not os.path.isfile(os.path.join(ROOT, "studio", "web", "icon.ico")):
        args = [a for i, a in enumerate(args) if a != "--icon" and (i == 0 or args[i - 1] != "--icon")]
    pyinstaller.run(args)
    app = os.path.join(out, NAME)
    internal = os.path.join(app, "_internal")
    copy_data(os.path.join(internal if os.path.isdir(internal) else app, "app"))
    exe = os.path.join(app, NAME + (".exe" if os.name == "nt" else ""))
    # the build checks itself: the executable runs a tool as the studio would
    r = subprocess.run([exe, "--run-tool", os.path.join(internal if os.path.isdir(internal) else app, "app", "tools",
                                                         "make_bar.py"), "--out", os.path.join(work, "check.ddt")],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not os.path.isfile(os.path.join(work, "check.ddt")):
        print("the built program could not run a tool:", r.stdout, r.stderr)
        return 1
    size = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(app) for f in fs)
    print(f"{exe}: {size / 1048576:.0f} MB in all")
    if "--zip" in argv:
        z = os.path.join(out, f"{NAME}-{version()}-{sys.platform}.zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for b, _, fs in os.walk(app):
                for f in fs:
                    full = os.path.join(b, f)
                    zf.write(full, os.path.join(NAME, os.path.relpath(full, app)))
        print(f"{z}: {os.path.getsize(z) / 1048576:.0f} MB")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
