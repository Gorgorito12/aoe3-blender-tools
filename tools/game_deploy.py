# SPDX-License-Identifier: GPL-3.0-or-later
"""Deploy a game bundle into a TEST COPY of the game, or take it out again.

    python -I tools/game_deploy.py --install <copy> --bundle <folder> [--validate]
    python -I tools/game_deploy.py --install <copy> --undo
    python -I tools/game_deploy.py --install <copy> --validate

Refuses any folder inside a Steam library. Backups are kept as <file>.aoe3bt-orig and the
changes are listed in <copy>/aoe3bt-manifest.json, which --undo reads.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "aoe3_blender_tools"))
from aoe3game import deploy  # noqa: E402


def main(argv):
    def opt(name):
        return argv[argv.index(name) + 1] if name in argv else None

    install = opt("--install")
    if not install or not (opt("--bundle") or "--undo" in argv or "--validate" in argv):
        print(__doc__)
        return 2
    try:
        d = deploy.Deployment(install)
    except deploy.RefusedPath as e:
        print(e)
        return 1
    if "--undo" in argv:
        d.undo()
        print("undone")
    if opt("--bundle"):
        m = d.apply(opt("--bundle"))
        print(f"deployed: unit {m.get('units')} id {m.get('unit_id')}, strings {m.get('strings')}")
    if "--validate" in argv:
        bad = 0
        for script, (code, errors, _lines) in d.validate(log=lambda s: None).items():
            print(f"{script}: exit {code}, {len(errors)} errors")
            for line in errors[:20]:
                print("   ", line.encode("ascii", "replace").decode())
            bad += bool(code or errors)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
