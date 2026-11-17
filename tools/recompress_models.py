# SPDX-License-Identifier: GPL-3.0-or-later
"""Compress Granny models (.gr2) again through the game's own Granny runtime: the reverse of
tools/uncompress_models.py, for models a tool wrote uncompressed (fix_bone_scale.py, retexture.py
--own-texture, a rebake) that should ship at the size of the originals.

    python -I tools/recompress_models.py <in.gr2 | folder> -o <out.gr2 | out folder>
                                         --granny-install <game folder> [--like <original | folder>]
                                         [--format oodle1|oodle0|none] [--helper <exe>]
                                         [--workers N] [-v]
    python -I tools/recompress_models.py --build-helper [<out.exe>]

A folder is walked for every .gr2 below it, and each result is written to the same relative path
below the output folder; --like then names a folder of originals at the same relative paths (the
names are compared without case). The output never overwrites an input, and a Steam library is
refused as the output.

Which format each section gets:
- with --like, the format the original stores that section in (the file must have the original's
  sections: same count, expanded sizes and alignment), so a section the original kept uncompressed
  stays uncompressed;
- else --format (default oodle1, the format of almost every model of the game) for every section,
  except a section whose compressed bytes would not be fewer than its expanded size, which stays
  uncompressed (the game's own models do the same; an empty section takes the format).

How: the runtime is granny2.dll, the game's copy in --granny-install (never shipped with this tool).
It is a 32-bit DLL, so a small x86 program, tools/granny_recompress.c, hosts it:
`granny_recompress <dll> recompress <in> <out> <map>` calls GrannyRecompressFile, which rewrites a
file with each section's format mapped (0 none, 1 Oodle0, 2 Oodle1) and keeps the sections' order,
records, bytes and fixup tables; `crc` calls GrannyFileCRCIsValid. --build-helper compiles it with
the Visual Studio C compiler for x86 (found by vswhere) or zig, by default to
tools/granny_recompress.exe (ignored by git), which is also where --helper looks by default.

Per file:
- the runtime writes the file once in each target format (with the mapping "every format to F");
  for one target format that file is the result, for several the sections are put together from
  them in the runtime's own layout (per section: pointer fixups, marshalling fixups, data, packed);
- the runtime writes the root object's type reference (header words 5 and 6, at 0x34) as 0:0, and
  the game then reads a model whose type tag is older than the runtime's with the wrong type (it
  exits at its main menu): the input's two words are put back (or the original's, with --like,
  when the input lost them) and the CRC is recomputed, as uncompress_models.py does;
- checked before it is written: the header is the input's but for the total size and the CRC;
  every section has its target format and the input's record (expanded size, alignment, Oodle
  stops, fixup counts) and fixup tables byte for byte, an uncompressed section its bytes; the CRC
  is valid by the bytes and by the runtime; and the runtime expands the result back to exactly
  what it expands the input to (byte for byte, both written uncompressed by the runtime);
- written under a temporary name and renamed into place.

It prints one line per file with -v, then the count, the MB in and out (and the originals' MB with
--like). Exit status: 0, 1 when a file was refused (nothing written for it), 2 for a usage error.
"""
import concurrent.futures
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
from aoe3game import gr2  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402
from uncompress_models import ROOT_TYPE, Refused, layout  # noqa: E402

FORMATS = {"none": 0, "oodle0": 1, "oodle1": 2}
NAMES = {v: k for k, v in FORMATS.items()}
HELPER_SOURCE = os.path.join(HERE, "granny_recompress.c")
DEFAULT_HELPER = os.path.join(HERE, "granny_recompress.exe")
TEMP_SUFFIX = ".recompressing"
MB = 1024 * 1024


# --------------------------------------------------------------------------------------------------
# The runtime, through the 32-bit helper

class Runtime:
    """Calls into granny2.dll through the helper; every file goes through a scratch folder under
    short ASCII names (the helper passes ANSI paths to the runtime)."""

    def __init__(self, helper, dll, work):
        self.helper, self.dll, self.work = helper, dll, work

    def folder(self, tag):
        """A folder per job, so that no two helpers ever share one."""
        path = os.path.join(self.work, f"j{tag}")
        os.makedirs(path, exist_ok=True)
        return path

    def _run(self, args, tag):
        work = self.folder(tag)
        env = dict(os.environ, TEMP=work, TMP=work)
        try:
            r = subprocess.run([self.helper, self.dll] + args, cwd=work, env=env,
                               capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Refused(f"the helper failed: {type(exc).__name__}") from exc
        if r.returncode in (2, 3):
            msg = (r.stderr or b"").decode("utf-8", "replace").strip()
            raise Refused(f"the helper could not run (exit {r.returncode})" +
                          (f": {msg}" if msg else ""))
        return r.returncode

    def recompress(self, data, fmt, tag):
        """The runtime's rewrite of `data` with every section stored in format `fmt`."""
        work = self.folder(tag)
        src, out = os.path.join(work, "in.gr2"), os.path.join(work, "out.gr2")
        try:
            with open(src, "wb") as fh:
                fh.write(data)
            if self._run(["recompress", "in.gr2", "out.gr2", str(fmt), str(fmt), str(fmt)],
                         tag) != 0:
                raise Refused(f"the runtime refused to write the file as {NAMES[fmt]}")
            with open(out, "rb") as fh:
                return fh.read()
        finally:
            for p in (src, out):
                if os.path.exists(p):
                    os.remove(p)

    def crc_ok(self, data, tag):
        path = os.path.join(self.folder(tag), "crc.gr2")
        try:
            with open(path, "wb") as fh:
                fh.write(data)
            return self._run(["crc", "crc.gr2"], tag) == 0
        finally:
            if os.path.exists(path):
                os.remove(path)


# --------------------------------------------------------------------------------------------------
# The container

def assemble(sources, targets):
    """A file whose section i is section i of sources[targets[i]], in the runtime's layout: the
    header and section array, then per section its pointer fixups, its marshalling fixups and its
    data, packed. Every source must be the same file in another format. The CRC is left stale."""
    first = sources[targets[0]]
    words = layout(first)[0]
    sec_off, n = words[3], words[4]
    head = 0x20 + sec_off + n * gr2.SECTION_RECORD
    out = bytearray(first[:head])
    for i, fmt in enumerate(targets):
        data = sources[fmt]
        _, sections, relocs, marshal = layout(data)
        s = sections[i]
        values = list(struct.unpack_from("<11I", data, 0x20 + sec_off + i * gr2.SECTION_RECORD))
        values[7] = len(out)                            # reloc_offset
        out += relocs[i]
        values[9] = len(out)                            # marshal_offset
        out += marshal[i]
        values[1] = len(out)                            # data_offset
        out += data[s.data_offset:s.data_offset + s.data_size]
        struct.pack_into("<11I", out, 0x20 + sec_off + i * gr2.SECTION_RECORD, *values)
    struct.pack_into("<I", out, 0x24, len(out))
    return bytes(out)


def put_root_type(data, root):
    """`data` with the root type reference `root` (8 bytes) and its CRC recomputed."""
    out = bytearray(data)
    out[ROOT_TYPE:ROOT_TYPE + 8] = root
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


def targets_for(expanded, compressed, fmt, like):
    """The format of each section: the original's with --like (`like`, its section records), else
    `fmt` where the compressed bytes are fewer than the expanded ones (none elsewhere).
    `expanded` and `compressed` are the section records of the two runtime rewrites."""
    if like is not None:
        if len(like) != len(expanded):
            raise Refused(f"{len(expanded)} sections, the original has {len(like)}")
        for i, (a, b) in enumerate(zip(like, expanded)):
            if (a.expanded_size, a.alignment) != (b.expanded_size, b.alignment):
                raise Refused(f"section {i} is not the original's (expanded size or alignment)")
            if a.compression not in NAMES:
                raise Refused(f"the original's section {i} has an unknown format {a.compression}")
        return [a.compression for a in like]
    if fmt == 0:
        return [0] * len(expanded)
    return [fmt if c.data_size < e.expanded_size or e.expanded_size == 0 else 0
            for e, c in zip(expanded, compressed)]


def verify(raw, out, targets, root):
    """Raises Refused unless `out` is `raw` (the runtime's uncompressed rewrite of the input) with
    section i stored in format targets[i] and the root type reference `root`."""
    w0, s0, r0, m0 = layout(raw)
    w1, s1, r1, m1 = layout(out)
    same = [k for k in range(len(w0)) if k not in (1, 2, 5, 6)]   # but size, CRC, root type
    if [w0[k] for k in same] != [w1[k] for k in same]:
        raise Refused("the header differs")
    if out[ROOT_TYPE:ROOT_TYPE + 8] != root:
        raise Refused("the root type reference was not put back")
    if w1[1] != len(out):
        raise Refused("the header's total size is not the file's")
    for i, (a, b) in enumerate(zip(s0, s1)):
        if b.compression != targets[i]:
            raise Refused(f"section {i} is stored as {b.compression}, not {targets[i]}")
        if (a.expanded_size, a.alignment, a.first16, a.first8, a.reloc_count, a.marshal_count) != \
                (b.expanded_size, b.alignment, b.first16, b.first8, b.reloc_count, b.marshal_count):
            raise Refused(f"section {i}'s record differs")
        if r0[i] != r1[i] or m0[i] != m1[i]:
            raise Refused(f"section {i}'s fixups differ")
        if b.compression == 0 and (b.data_size != a.expanded_size or
                                   raw[a.data_offset:a.data_offset + a.data_size] !=
                                   out[b.data_offset:b.data_offset + b.data_size]):
            raise Refused(f"section {i} is stored uncompressed and its bytes differ")
    if not gr2.crc_ok(out):
        raise Refused("the CRC is not valid")


def recompress(data, runtime, fmt, like, tag):
    """(the recompressed file, its section formats). Raises Refused."""
    words, sections, _, _ = layout(data)
    root = data[ROOT_TYPE:ROOT_TYPE + 8]
    if root == bytes(8) and like is not None:
        root = like[0][ROOT_TYPE:ROOT_TYPE + 8]        # the input lost it: the original's
    raw = runtime.recompress(data, 0, tag)
    sources = {0: raw}
    for f in sorted({fmt} | ({s.compression for s in like[1]} if like is not None else set())):
        if f not in sources:
            sources[f] = runtime.recompress(data, f, tag)
    targets = targets_for(layout(raw)[1], layout(sources[fmt])[1], fmt,
                          like[1] if like is not None else None)
    out = sources[targets[0]] if len(set(targets)) == 1 else assemble(sources, targets)
    out = put_root_type(out, root)
    verify(raw, out, targets, root)
    if not runtime.crc_ok(out, tag):
        raise Refused("the runtime says the CRC is not valid")
    if runtime.recompress(out, 0, tag) != raw:
        raise Refused("the runtime does not expand the result back to the input")
    return out, targets


# --------------------------------------------------------------------------------------------------
# The helper

def build_helper(out):
    """Compiles tools/granny_recompress.c for x86 with MSVC (vswhere) or zig. Returns 0 or 1."""
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    work = tempfile.mkdtemp(prefix="granny_recompress_")
    try:
        vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                               "Microsoft Visual Studio", "Installer", "vswhere.exe")
        vcvars = None
        if os.path.exists(vswhere):
            r = subprocess.run([vswhere, "-latest", "-prerelease", "-products", "*", "-find",
                                r"VC\Auxiliary\Build\vcvars32.bat"], capture_output=True, text=True)
            found = [line.strip() for line in r.stdout.splitlines() if line.strip()]
            vcvars = found[0] if found else None
        if vcvars:
            bat = os.path.join(work, "build.bat")
            with open(bat, "w") as fh:
                fh.write(f'@call "{vcvars}" >nul\r\n'
                         f'@cl /nologo /O2 /W4 "{HELPER_SOURCE}" /Fe:"{out}"\r\n')
            r = subprocess.run(["cmd", "/c", bat], cwd=work, capture_output=True, text=True)
        elif shutil.which("zig"):
            r = subprocess.run(["zig", "cc", "-target", "x86-windows-gnu", "-O2", HELPER_SOURCE,
                                "-o", out], cwd=work, capture_output=True, text=True)
        else:
            print("no x86 C compiler: install Visual Studio's C++ tools or zig")
            return 1
        if r.returncode != 0 or not os.path.exists(out):
            print((r.stdout or "") + (r.stderr or ""))
            print("the build failed")
            return 1
        print(f"built {out}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------------------------------
# Files and folders

def collect(src, dst, like):
    """[(input, output, original or None)]."""
    if os.path.isfile(src):
        return [(src, dst, like)]
    originals = {}
    if like is not None:
        for base, _, names in os.walk(like):
            for n in names:
                p = os.path.join(base, n)
                originals[os.path.relpath(p, like).lower()] = p
    jobs = []
    for base, _, names in os.walk(src):
        for n in sorted(names):
            if not n.lower().endswith(".gr2"):
                continue
            p = os.path.join(base, n)
            rel = os.path.relpath(p, src)
            jobs.append((p, os.path.join(dst, rel),
                         originals.get(rel.lower(), "") if like is not None else None))
    return sorted(jobs)


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def main(argv):
    args = {"out": None, "granny_install": None, "like": None, "format": "oodle1",
            "helper": DEFAULT_HELPER, "workers": max(1, (os.cpu_count() or 2) // 2),
            "verbose": False}
    inputs, i, build = [], 0, None
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("-o", "--out"):
                args["out"], i = argv[i + 1], i + 1
            elif a in ("--granny-install", "--like", "--format", "--helper"):
                args[a[2:].replace("-", "_")], i = argv[i + 1], i + 1
            elif a == "--workers":
                args["workers"], i = int(argv[i + 1]), i + 1
            elif a == "-v":
                args["verbose"] = True
            elif a == "--build-helper":
                build = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") \
                    else DEFAULT_HELPER
                i += build is not DEFAULT_HELPER
            elif a.startswith("-"):
                raise ValueError(a)
            else:
                inputs.append(a)
            i += 1
    except (IndexError, ValueError):
        inputs = None
    if build is not None and inputs == []:
        return build_helper(build)
    if not inputs or len(inputs) != 1 or not args["out"] or not args["granny_install"] or \
            args["format"] not in FORMATS or args["workers"] < 1:
        print(__doc__)
        return 2
    src, dst, like = inputs[0], args["out"], args["like"]
    if not os.path.exists(src) or like is not None and (
            not os.path.exists(like) or os.path.isdir(src) != os.path.isdir(like)):
        print("refused: the input (and --like) must both be files or both be folders")
        return 2
    dll = os.path.join(args["granny_install"], "granny2.dll")
    if not os.path.exists(dll):
        print(f"refused: no granny2.dll in {args['granny_install']}")
        return 2
    if not os.path.exists(args["helper"]):
        print(f"refused: no helper at {args['helper']} (build it with --build-helper)")
        return 2
    try:
        refuse_steam(dst)
    except RefusedPath as exc:
        print(f"refused: {exc}")
        return 2
    jobs = collect(src, dst, like)
    if any(same_path(a, b) for a, b, _ in jobs):
        print("refused: the output would overwrite an input")
        return 2
    fmt = FORMATS[args["format"]]
    work = tempfile.mkdtemp(prefix="recompress_models_")
    runtime = Runtime(os.path.abspath(args["helper"]), os.path.abspath(dll), work)

    def job(k, path, out, original):
        with open(path, "rb") as fh:
            data = fh.read()
        ref = None
        if original is not None:
            if not original:
                raise Refused("no original of this name under --like")
            with open(original, "rb") as fh:
                orig = fh.read()
            ref = (orig, layout(orig)[1])
        result, targets = recompress(data, runtime, fmt, ref, k)
        return data, result, targets, (len(ref[0]) if ref else 0)

    done, failed, size_in, size_out, size_orig = 0, [], 0, 0, 0
    try:
        with concurrent.futures.ThreadPoolExecutor(args["workers"]) as pool:
            futures = {pool.submit(job, k, *j): j for k, j in enumerate(jobs)}
            for fut in concurrent.futures.as_completed(futures):
                path, out, _ = futures[fut]
                try:
                    data, result, targets, orig = fut.result()
                except (Refused, OSError, struct.error) as exc:
                    failed.append(f"{path}: {exc}")
                    continue
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                with open(out + TEMP_SUFFIX, "wb") as fh:
                    fh.write(result)
                os.replace(out + TEMP_SUFFIX, out)
                done += 1
                size_in += len(data)
                size_out += len(result)
                size_orig += orig
                if args["verbose"]:
                    print(f"  {path}: {len(data)} -> {len(result)} bytes, sections "
                          f"{','.join(NAMES[t] for t in targets)}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"{done} written, {len(failed)} refused: {size_in / MB:.2f} MB -> {size_out / MB:.2f} MB"
          + (f" (the originals: {size_orig / MB:.2f} MB)" if like is not None else ""))
    for line in failed[:40]:
        print("  REFUSED " + line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
