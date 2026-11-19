# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's own Granny runtime as the judge of a model: what granny2.dll reads in it (meshes,
their vertices, indices and bone bindings; skeletons and their bones), beside what this
repository's reader reads; with --rewrite, also the model written again from its own tree
(aoe3game/gr2_edit.rewrite), which must read the same in the runtime.

    python -I tools/gr2_check.py <model.gr2 | folder> --granny-install <game> [--helper <exe>]
                                 [--rewrite [--save <file.gr2>]] [--limit N] [-v]

The runtime is the game's granny2.dll, loaded by the 32-bit helper of tools/recompress_models.py
(`granny_recompress.exe info`; build it with `recompress_models.py --build-helper`). Nothing is
written beside the models: each file goes through a scratch folder. Only uncompressed models are
compared with the reader (a compressed one is read by the runtime alone). --save keeps the
rewritten copy of one model when the runtime read it alike (for the in-game test T0 of
docs/game-test.md: save it under a folder laid out as the copy, then deploy that folder).

Exit status: 0 every model read alike, 1 some differ or the runtime refused one, 2 usage.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))

from aoe3game import gr2, gr2_edit  # noqa: E402
import recompress_models as rm  # noqa: E402


def reader_lines(doc):
    """This repository's reading in the helper's own lines (without the runtime's version and the
    rigid flag, which the file does not state)."""
    out = []
    root = doc.root()
    for m in root.get("Meshes") or []:
        if m is None:
            continue
        vd, tt = m.get("PrimaryVertexData"), m.get("PrimaryTopology")
        vs = vd.get("Vertices") if vd is not None else None
        vcount = vs.count if isinstance(vs, gr2.Blob) else len(vs or [])
        icount = 0
        for key in ("Indices", "Indices16"):
            src = tt.get(key) if tt is not None else None
            icount += src.count if isinstance(src, gr2.Blob) else len(src or [])
        out.append(f"mesh\t{m.get('Name') or ''}\t{vcount}\t{icount}\t{icount // 3}")
        for b in m.get("BoneBindings") or []:
            out.append(f"binding\t{(b.get('BoneName') if b is not None else '') or ''}")
    for sk in root.get("Skeletons") or []:
        if sk is None:
            continue
        bones = sk.get("Bones") or []
        out.append(f"skeleton\t{sk.get('Name') or ''}\t{len(bones)}")
        for b in bones:
            out.append(f"bone\t{b.get('Name') or ''}\t{b.get('ParentIndex')}")
    return out


def runtime_lines(lines):
    """The helper's lines without its version line, and each mesh line without the rigid flag."""
    out = []
    for line in lines:
        if line.startswith("version\t"):
            continue
        if line.startswith("mesh\t"):
            line = "\t".join(line.split("\t")[:5])
        out.append(line)
    return out


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"line {i + 1}: {x!r} / {y!r}"
    return f"{len(a)} lines / {len(b)} lines" if len(a) != len(b) else None


def check(data, runtime, tag, rewrite=False, save=None):
    """(ok, notes) for one model's bytes; `save`: a path for the rewritten copy, written only
    when the runtime reads it alike."""
    code, lines = runtime.info(data, tag)
    if code != 0:
        return False, [f"the runtime refused it: {' '.join(lines[-1:])}"]
    seen = runtime_lines(lines)
    notes = [f"runtime {next((ln.split(chr(9))[1] for ln in lines if ln.startswith('version')), '?')}: "
             f"{sum(ln.startswith('mesh') for ln in seen)} meshes, {sum(ln.startswith('bone') for ln in seen)} bones"]
    try:
        doc = gr2.load(data)
    except gr2.Compressed:
        return True, notes + ["compressed: read by the runtime alone"]
    diff = first_difference(seen, reader_lines(doc))
    ok = diff is None
    if diff:
        notes.append(f"the reader differs from the runtime at {diff}")
    if rewrite:
        out = gr2_edit.rewrite(data)
        code2, lines2 = runtime.info(out, tag)
        if code2 != 0:
            return False, notes + ["the runtime refused the rewritten file"]
        diff2 = first_difference(seen, runtime_lines(lines2))
        if diff2:
            ok = False
            notes.append(f"rewritten, the runtime reads it otherwise at {diff2}")
        elif not runtime.crc_ok(out, tag):
            ok = False
            notes.append("rewritten, the runtime finds its CRC wrong")
        else:
            notes.append("rewritten from its own tree: the runtime reads it alike, its CRC valid")
            if save and ok:
                os.makedirs(os.path.dirname(os.path.abspath(save)), exist_ok=True)
                with open(save, "wb") as fh:
                    fh.write(out)
                notes.append(f"saved: {save}")
    return ok, notes


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    target, install = (argv[0] if argv and not argv[0].startswith("-") else None), opt("--granny-install")
    if not target or not install:
        print(__doc__)
        return 2
    dll = os.path.join(install, "granny2.dll")
    helper = opt("--helper", rm.DEFAULT_HELPER)
    if not os.path.isfile(dll):
        print(f"refused: no granny2.dll in {install}")
        return 2
    if not os.path.isfile(helper):
        print(f"refused: no helper at {helper} (python -I tools/recompress_models.py --build-helper)")
        return 2
    if os.path.isdir(target):
        files = sorted(os.path.join(b, f) for b, _d, fs in os.walk(target) for f in fs if f.lower().endswith(".gr2"))
    else:
        files = [target]
    save = opt("--save")
    if save and (len(files) != 1 or "--rewrite" not in argv):
        print("refused: --save keeps the rewritten copy of one model (--rewrite and a single file)")
        return 2
    if save and os.path.abspath(save) == os.path.abspath(files[0]):
        print("refused: --save would write over the model itself")
        return 2
    limit = int(opt("--limit", "0") or 0)
    if limit:
        files = files[:limit]
    bad = 0
    with tempfile.TemporaryDirectory(prefix="gr2check") as work:
        runtime = rm.Runtime(helper, dll, work)
        for k, path in enumerate(files):
            with open(path, "rb") as fh:
                data = fh.read()
            try:
                ok, notes = check(data, runtime, k, rewrite="--rewrite" in argv, save=save)
            except (rm.Refused, gr2.Gr2Error) as e:
                ok, notes = False, [str(e)]
            bad += not ok
            if not ok or "-v" in argv or len(files) == 1:
                print(f"{'ok  ' if ok else 'DIFF'} {path}")
                for n in notes:
                    print(f"     {n}")
    print(f"{len(files) - bad} of {len(files)} models read alike")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
