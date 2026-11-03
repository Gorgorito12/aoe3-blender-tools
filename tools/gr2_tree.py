# SPDX-License-Identifier: GPL-3.0-or-later
"""Read an uncompressed Granny model (.gr2): its data tree, its statistics or its types.

    python -I tools/gr2_tree.py <model.gr2> [--stats | --types | --shape]

Default: the whole tree, one `path = value` line per value (arrays of plain values as their
count and a hash). --stats: triangles, vertices, layout, basis, size, bones, textures, shader
effects. --types: the type definitions under the root. --shape: the sorted set of paths with
array indices removed, to compare the structure of two files with `diff`.

Most of the game's models store compressed sections; they need the Granny runtime, which this
tool does not have: read them after an external tool has rewritten them uncompressed.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "aoe3_blender_tools"))
from aoe3game import gr2  # noqa: E402


def main(argv):
    files = [a for a in argv if not a.startswith("--")]
    if len(files) != 1:
        print(__doc__)
        return 2
    try:
        doc = gr2.load(files[0])
    except gr2.Compressed as exc:
        print(f"{files[0]}: {exc}")
        return 1
    if "--stats" in argv:
        print(json.dumps(doc.stats(), indent=1))
    elif "--types" in argv:
        print("\n".join(gr2.type_listing(doc)))
    elif "--shape" in argv:
        print("\n".join(sorted({re.sub(r"\[\d+\]", "[]", l.split(" = ")[0]) for l in gr2.dump_tree(doc)})))
    else:
        print("\n".join(gr2.dump_tree(doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
