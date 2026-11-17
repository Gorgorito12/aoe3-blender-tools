# SPDX-License-Identifier: GPL-3.0-or-later
"""A native file or folder dialog in its own process (Tk wants the main thread): reads
{"mode", "title", "initial", "filters": [[label, "*.ext *.ext"], ...]} on stdin and prints
{"path": ...} (or {"paths": [...]}; null when cancelled)."""
import json
import os
import sys


def main():
    req = json.loads(sys.stdin.read() or "{}")
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    mode = req.get("mode", "file")
    initial = req.get("initial") or ""
    kw = {"title": req.get("title") or "", "parent": root}
    if initial:
        kw["initialdir"] = initial if os.path.isdir(initial) else os.path.dirname(initial) or None
    filters = [tuple(f) for f in req.get("filters") or []] + [("All files", "*.*")]
    if mode == "folder":
        path = filedialog.askdirectory(mustexist=False, **kw)
    elif mode == "save":
        path = filedialog.asksaveasfilename(filetypes=filters, initialfile=os.path.basename(initial)
                                            if initial and not os.path.isdir(initial) else "", **kw)
    elif mode == "files":
        paths = filedialog.askopenfilenames(filetypes=filters, **kw)
        root.destroy()
        print(json.dumps({"paths": [os.path.normpath(p) for p in paths] or None}))
        return 0
    else:
        path = filedialog.askopenfilename(filetypes=filters, **kw)
    root.destroy()
    print(json.dumps({"path": os.path.normpath(path) if path else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
