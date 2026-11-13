# SPDX-License-Identifier: GPL-3.0-or-later
"""Uncompressed copies of the game's archived Granny models (.gr2), as loose files of a game copy.

    python -I tools/uncompress_models.py <game folder>                 (the plan: writes nothing)
    python -I tools/uncompress_models.py <game folder> --install --granny <bridge.exe>
                                         [--granny-install <folder>] [--only-used <list>]
                                         [--workers N] [--work <folder>]
    python -I tools/uncompress_models.py <game folder> --check
    python -I tools/uncompress_models.py <game folder> --undo

Almost every model in the archives (art\\Art*.bar) stores Oodle-compressed sections, and the game
decompresses a model the first time it meets one, on its main thread: a stutter when a new unit
or building shows up, and part of a save's load. A loose file under art\\ overrides the archived
one of the same name, and an uncompressed file skips only the decoder. Measured on a replayed
late game: in the stock game the frames over 50 ms went from 2 to 0, the longest frame from about
95 ms to 42 ms, and the save's load got 1.1 to 1.9 s shorter; in Wars of Liberty the save's load
went from 11.6 to 9.5 s and the frame that loaded a new model mid-game (72 to 80 ms) went away.

What --install does:
- reads every .gr2 of the art\\Art*.bar archives; a name stored in two archives with different
  bytes is left out (which one the game reads is not measured), and so is a model whose sections
  are already all uncompressed (nothing to gain);
- **skips every name that already exists as a loose file**: those are the mod's own models, and
  they are never read, changed or removed;
- has the external Granny bridge rewrite each model with every section uncompressed (`<bridge>
  rebake --install <folder> --file <in> --out <out> --noop --native-crc`: it expands the sections
  through the game's own Granny runtime, reads the original and the copy back through it and
  writes only when their whole data trees are identical, and asks the runtime whether the copy's
  CRC is valid). The runtime is the game's granny2.dll, read from --granny-install (default: the
  game folder); it is never shipped with this tool;
- puts the root type reference (header words 5 and 6) back if the copy lost it (a copy written by
  the runtime's own recompress call has 0:0 there, and a model whose type tag is older than the
  runtime's is then read with the wrong type: the game exits at the main menu), and recomputes
  the CRC;
- checks each copy against its original before writing it: same header (but for total size and
  CRC), same sections (expanded size, alignment, stops), every section stored uncompressed at its
  expanded size, the relocation and marshalling tables byte for byte, the sections the original
  stored uncompressed byte for byte, and the CRC; a copy that fails is not written;
- writes each copy under a temporary name and renames it into place, and records it in the
  manifest `uncompressed-models.jsonl` at the root of the copy (one line per file, with its
  SHA-256 and the archive entry it came from) before the rename; folders it creates are recorded
  too. A second --install brings the set up to date: a copy whose archive entry changed (a patch)
  is rewritten, one whose name left the archives is removed, the rest are kept;
- with --only-used, writes only the models of a list (and removes its own copies of the others):
  a text file of paths, or a game log with one line per file read. The game reads an archived
  model through its archive, so a list of the models one session opens comes from a session
  played with the full set installed (each copy is then a file of its own).

--undo removes exactly the files of the manifest whose content is still what was written (a
file changed since is left and listed), then the folders it created if they are empty, then the
manifest. --check reads the manifest back: every copy present and unchanged, every archive entry
unchanged (else: run --install again). Every mode refuses a folder inside a Steam library.

It reports the count, the MB before (as stored in the archives) and after, and the time taken.
Exit status: 0, 1 when a copy failed or a check found a problem, 2 for a usage error.
"""
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
import bar  # noqa: E402
from aoe3game import gr2  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402

MANIFEST = "uncompressed-models.jsonl"
FORMAT = 1
TEMP_SUFFIX = ".uncompressing"
ROOT_TYPE = 0x34            # header words 5 and 6: the root type reference (section, offset)
MARSHALLING = 16            # bytes per mixed-marshalling fixup
MB = 1024 * 1024


class Refused(Exception):
    """A copy that must not be written; the message says why."""


# --------------------------------------------------------------------------------------------------
# The container, as far as the check needs it (compressed or not)

def layout(data):
    """(header words, [section record], [relocation bytes], [marshalling bytes]) of a file."""
    if len(data) < 0x58 or data[:16] != gr2.MAGIC:
        raise Refused("not a Granny file")
    version = struct.unpack_from("<I", data, 0x20)[0]
    if version not in gr2.HEADER_SIZE:
        raise Refused(f"unknown Granny file version {version}")
    size = gr2.HEADER_SIZE[version]
    words = list(struct.unpack_from(f"<{size // 4}I", data, 0x20))
    sec_off, n = words[3], words[4]
    if n > 1024 or 0x20 + sec_off + n * gr2.SECTION_RECORD > len(data):
        raise Refused("the section array runs past the file")
    sections, relocs, marshal = [], [], []
    for i in range(n):
        s = gr2.Section(*struct.unpack_from("<11I", data, 0x20 + sec_off + i * gr2.SECTION_RECORD))
        r_end = s.reloc_offset + s.reloc_count * gr2.RELOCATION
        m_end = s.marshal_offset + s.marshal_count * MARSHALLING
        if (s.data_offset + s.data_size > len(data) or r_end > len(data) or m_end > len(data)):
            raise Refused(f"section {i} runs past the file")
        sections.append(s)
        relocs.append(bytes(data[s.reloc_offset:r_end]))
        marshal.append(bytes(data[s.marshal_offset:m_end]))
    return words, sections, relocs, marshal


def is_raw(data):
    """True when every section with stored bytes is uncompressed."""
    _, sections, _, _ = layout(data)
    return all(s.compression == 0 or s.data_size == 0 for s in sections)


def fix_header(original, copy):
    """The copy with the original's root type reference, its CRC recomputed when that changed it.
    Returns (bytes, whether it was changed)."""
    want = original[ROOT_TYPE:ROOT_TYPE + 8]
    if copy[ROOT_TYPE:ROOT_TYPE + 8] == want:
        return copy, False
    out = bytearray(copy)
    out[ROOT_TYPE:ROOT_TYPE + 8] = want
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out), True


def verify(original, copy):
    """Raises Refused unless the copy is the original with its sections stored uncompressed."""
    w0, s0, r0, m0 = layout(original)
    w1, s1, r1, m1 = layout(copy)
    same = [k for k in range(len(w0)) if k not in (1, 2)]     # all but total size and CRC
    if [w0[k] for k in same] != [w1[k] for k in same]:
        raise Refused("the header differs")
    if w1[1] != len(copy):
        raise Refused("the header's total size is not the file's")
    for i, (a, b) in enumerate(zip(s0, s1)):
        if b.compression != 0:
            raise Refused(f"section {i} is still compressed")
        if (a.expanded_size, a.alignment, a.first16, a.first8, a.reloc_count, a.marshal_count) != \
                (b.expanded_size, b.alignment, b.first16, b.first8, b.reloc_count, b.marshal_count):
            raise Refused(f"section {i}'s record differs")
        if b.data_size != b.expanded_size:
            raise Refused(f"section {i} is not stored at its expanded size")
        if r0[i] != r1[i] or m0[i] != m1[i]:
            raise Refused(f"section {i}'s fixups differ")
        if a.compression == 0 and a.data_size and \
                original[a.data_offset:a.data_offset + a.data_size] != \
                copy[b.data_offset:b.data_offset + b.data_size]:
            raise Refused(f"section {i} was stored uncompressed and its bytes differ")
    if not gr2.crc_ok(copy):
        raise Refused("the CRC is not valid")


# --------------------------------------------------------------------------------------------------
# The bridge

def run_bridge(exe, install, src, out, cwd):
    """Has the external bridge write `out`, `src` with every section uncompressed. Raises Refused."""
    try:
        r = subprocess.run([exe, "rebake", "--install", install, "--file", src, "--out", out,
                            "--noop", "--native-crc"], cwd=cwd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"the bridge failed: {type(exc).__name__}") from exc
    if r.returncode != 0 or not os.path.exists(out):
        last = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        raise Refused(f"the bridge refused (exit {r.returncode}{': ' + last[0] if last else ''})")


def make_copy(original, exe, install, work, tag):
    """(verified uncompressed bytes, header fixed). Raises Refused."""
    src = os.path.join(work, f"s{tag}.gr2")
    out = os.path.join(work, f"o{tag}.gr2")
    try:
        with open(src, "wb") as fh:
            fh.write(original)
        run_bridge(exe, install, src, out, work)
        with open(out, "rb") as fh:
            copy = fh.read()
    finally:
        for p in (src, out):
            if os.path.exists(p):
                os.remove(p)
    copy, fixed = fix_header(original, copy)
    verify(original, copy)
    return copy, fixed


# --------------------------------------------------------------------------------------------------
# The archives, the loose files and the manifest

def key(rel):
    return rel.replace("/", "\\").lower()


def archives(game):
    folder = os.path.join(game, "art")
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if n.lower().startswith("art") and n.lower().endswith(".bar"))


def archived_models(game):
    """{key: entry} for the .gr2 files of the archives, and the names left out as ambiguous.
    entry: {"path", "archive", "offset", "size", "crc32"} (path relative to the game folder)."""
    found = {}
    for path in archives(game):
        name = os.path.basename(path)
        with open(path, "rb") as fh:
            for stored, offset, size in bar.read_entries(path):
                if not stored.lower().endswith(".gr2"):
                    continue
                bar.safe_target(game, stored)                 # refuses '..' and drive letters
                fh.seek(offset)
                crc = zlib.crc32(fh.read(size)) & 0xFFFFFFFF
                found.setdefault(key(stored), []).append(
                    {"path": stored.replace("/", "\\"), "archive": name, "offset": offset,
                     "size": size, "crc32": crc})
    models, ambiguous = {}, []
    for k, entries in found.items():
        if len({(e["size"], e["crc32"]) for e in entries}) > 1:
            ambiguous.append(entries[0]["path"])
        else:
            models[k] = entries[0]
    return models, sorted(ambiguous)


def read_entry(game, entry):
    with open(os.path.join(game, "art", entry["archive"]), "rb") as fh:
        fh.seek(entry["offset"])
        return fh.read(entry["size"])


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(MB), b""):
            h.update(chunk)
    return h.hexdigest()


def source_of(entry):
    return {k: entry[k] for k in ("archive", "offset", "size", "crc32")}


class Manifest:
    """The files and folders this tool created, as JSON lines; the last line about a path wins."""

    def __init__(self, game):
        self.path = os.path.join(game, MANIFEST)
        self.files, self.dirs = {}, {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue                    # a line cut by an interrupted run
                    kind = rec.get("kind")
                    if kind == "file":
                        self.files[key(rec["path"])] = rec
                    elif kind == "gone":
                        self.files.pop(key(rec["path"]), None)
                    elif kind == "dir":
                        self.dirs[key(rec["path"])] = rec["path"]
        self.fh = None

    def exists(self):
        return os.path.exists(self.path)

    def append(self, rec):
        if self.fh is None:
            new = not os.path.exists(self.path)
            self.fh = open(self.path, "a", encoding="utf-8")
            if new:
                self.fh.write(json.dumps({"kind": "header", "tool": "uncompress_models",
                                          "format": FORMAT}) + "\n")
        self.fh.write(json.dumps(rec) + "\n")
        self.fh.flush()

    def compact(self):
        """Rewrites the manifest with one line per file and folder (atomically)."""
        if self.fh is not None:
            self.fh.close()
            self.fh = None
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "header", "tool": "uncompress_models",
                                 "format": FORMAT}) + "\n")
            for d in sorted(self.dirs.values(), key=key):
                fh.write(json.dumps({"kind": "dir", "path": d}) + "\n")
            for rec in sorted(self.files.values(), key=lambda r: key(r["path"])):
                fh.write(json.dumps(rec) + "\n")
        os.replace(tmp, self.path)

    def close(self):
        if self.fh is not None:
            self.fh.close()
            self.fh = None


def make_dirs(game, rel_dir, manifest):
    """Creates the folders of a relative path that are missing, recording each one first."""
    parts = [p for p in rel_dir.split("\\") if p]
    for i in range(1, len(parts) + 1):
        rel = "\\".join(parts[:i])
        full = os.path.join(game, rel)
        if not os.path.isdir(full):
            manifest.dirs[key(rel)] = rel
            manifest.append({"kind": "dir", "path": rel})
            os.mkdir(full)


def remove_copy(game, rec, manifest):
    """Removes one of our copies if it is unchanged. Returns 'removed', 'changed' or 'missing'."""
    full = os.path.join(game, rec["path"])
    status = "missing"
    if os.path.exists(full):
        if sha256_file(full) != rec["sha256"]:
            status = "changed"
        else:
            os.remove(full)
            status = "removed"
    manifest.files.pop(key(rec["path"]), None)
    manifest.append({"kind": "gone", "path": rec["path"]})
    return status


def remove_dirs(game, manifest):
    left = []
    for k in sorted(manifest.dirs, key=lambda k: -k.count("\\")):
        full = os.path.join(game, manifest.dirs[k])
        try:
            os.rmdir(full)
        except FileNotFoundError:
            pass
        except OSError:
            left.append(manifest.dirs[k])
            continue
        del manifest.dirs[k]
    return left


def stray_temporaries(game):
    """Copies an interrupted run left under their temporary names (only this tool uses it)."""
    out = []
    for base, _, names in os.walk(os.path.join(game, "art")):
        out += [os.path.join(base, n) for n in names if n.endswith(TEMP_SUFFIX)]
    return out


def used_list(path, game):
    """The keys of the .gr2 paths a list names: plain paths, or a log with a path per line."""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\0" in raw[:200] \
        else raw.decode("utf-8", "replace")
    root = key(os.path.abspath(game)) + "\\"
    out = set()
    for line in text.splitlines():
        m = re.search(r"(?:[A-Za-z]:[\\/])?[^\r\n:*?\"<>|]*\.gr2\b", line, re.IGNORECASE)
        if not m:
            continue
        p = key(m.group(0).strip())
        if p.startswith(root):
            p = p[len(root):]
        a = re.search(r"(^|\\)art\\", p)
        if a:
            out.add(p[a.start() + len(a.group(1)):])
    return out


# --------------------------------------------------------------------------------------------------
# The modes

def plan(game, manifest, only):
    """Decides every archived model. Returns (jobs, keep, drop, counts, ambiguous): jobs and keep
    are archive entries, drop are manifest records to remove."""
    models, ambiguous = archived_models(game)
    jobs, keep, drop = [], [], []
    counts = {"archived": len(models) + len(ambiguous), "loose": 0, "raw": 0, "unlisted": 0,
              "changed by someone": 0}
    for k, entry in sorted(models.items()):
        rec = manifest.files.get(k)
        full = os.path.join(game, entry["path"])
        if only is not None and k not in only:
            counts["unlisted"] += 1
            if rec is not None:
                drop.append(rec)
            continue
        if rec is None:
            if os.path.exists(full):
                counts["loose"] += 1                # the mod's own file: never touched
                continue
        elif os.path.exists(full):
            if sha256_file(full) != rec["sha256"]:
                counts["changed by someone"] += 1   # no longer ours: forget it, leave it
                manifest.files.pop(k)
                manifest.append({"kind": "gone", "path": rec["path"]})
                continue
            if rec.get("source") == source_of(entry):
                keep.append(entry)
                continue
        if is_raw(read_entry(game, entry)):
            counts["raw"] += 1
            if rec is not None:
                drop.append(rec)
            continue
        jobs.append(entry)
    for k, rec in list(manifest.files.items()):
        if k not in models:
            drop.append(rec)                        # its name left the archives
    return jobs, keep, drop, counts, ambiguous


def install(game, args):
    t0 = time.perf_counter()
    exe, gr_install = args["granny"], args["granny_install"] or game
    manifest = Manifest(game)
    for p in stray_temporaries(game):
        os.remove(p)
    jobs, keep, drop, counts, ambiguous = plan(game, manifest, args["only"])
    removed = {"removed": 0, "changed": 0, "missing": 0}
    for rec in drop:
        removed[remove_copy(game, rec, manifest)] += 1
    work = tempfile.mkdtemp(prefix="uncompress_models_", dir=args["work"])
    written, failed, header_fixed, mb_in, mb_out = 0, [], 0, 0, 0

    def job(i, entry):
        original = read_entry(game, entry)
        copy, fixed = make_copy(original, exe, gr_install, work, i)
        return original, copy, fixed

    try:
        with concurrent.futures.ThreadPoolExecutor(args["workers"]) as pool:
            pending = {}
            it = iter(enumerate(jobs))
            for i, entry in it:
                pending[pool.submit(job, i, entry)] = entry
                if len(pending) >= 4 * args["workers"]:
                    break
            while pending:
                done, _ = concurrent.futures.wait(pending, return_when="FIRST_COMPLETED")
                for fut in done:
                    entry = pending.pop(fut)
                    try:
                        original, copy, fixed = fut.result()
                    except (Refused, OSError, struct.error) as exc:
                        failed.append(f"{entry['path']}: {exc}")
                        continue
                    full = os.path.join(game, entry["path"])
                    make_dirs(game, os.path.dirname(entry["path"]), manifest)
                    tmp = full + TEMP_SUFFIX
                    with open(tmp, "wb") as fh:
                        fh.write(copy)
                    digest = hashlib.sha256(copy).hexdigest()
                    if sha256_file(tmp) != digest:
                        os.remove(tmp)
                        failed.append(f"{entry['path']}: did not read back")
                        continue
                    manifest.files[key(entry["path"])] = rec = {
                        "kind": "file", "path": entry["path"], "size": len(copy),
                        "sha256": digest, "source": source_of(entry)}
                    manifest.append(rec)
                    os.replace(tmp, full)
                    written += 1
                    header_fixed += fixed
                    mb_in += len(original)
                    mb_out += len(copy)
                    if written % 500 == 0:
                        print(f"  {written} written ({time.perf_counter() - t0:.0f} s)", flush=True)
                for i, entry in it:
                    pending[pool.submit(job, i, entry)] = entry
                    if len(pending) >= 4 * args["workers"]:
                        break
    finally:
        shutil.rmtree(work, ignore_errors=True)
        remove_dirs(game, manifest)                 # only folders of ours left empty
        manifest.compact()
    total = sum(r["size"] for r in manifest.files.values())
    total_src = sum(r["source"]["size"] for r in manifest.files.values())
    print(f"{counts['archived']} models in the archives: {written} written "
          f"({mb_in / MB:.1f} MB as stored -> {mb_out / MB:.1f} MB uncompressed; "
          f"{header_fixed} had their root type reference put back), {len(keep)} kept, "
          f"{len(failed)} failed; left out: {counts['loose']} loose (the mod's own), "
          f"{counts['raw']} already uncompressed, {len(ambiguous)} stored differently in two "
          f"archives" + (f", {counts['unlisted']} not in the list" if args["only"] is not None
                         else ""))
    if any(removed.values()):
        print(f"removed {removed['removed']} of our copies no longer wanted"
              + (f"; {removed['changed']} changed since and left in place" if removed["changed"]
                 else ""))
    if counts["changed by someone"]:
        print(f"{counts['changed by someone']} of our copies were replaced by someone: forgotten, "
              "left in place")
    print(f"installed: {len(manifest.files)} copies, {total_src / MB:.1f} MB as stored -> "
          f"{total / MB:.1f} MB; {time.perf_counter() - t0:.1f} s")
    for line in failed[:40]:
        print("  FAILED " + line)
    return 1 if failed else 0


def undo(game):
    t0 = time.perf_counter()
    manifest = Manifest(game)
    if not manifest.exists():
        print("nothing installed (no manifest)")
        return 0
    counts = {"removed": 0, "changed": 0, "missing": 0}
    changed = []
    size = 0
    for rec in list(manifest.files.values()):
        status = remove_copy(game, rec, manifest)
        counts[status] += 1
        if status == "removed":
            size += rec["size"]
        elif status == "changed":
            changed.append(rec["path"])
    for p in stray_temporaries(game):
        os.remove(p)
    left = remove_dirs(game, manifest)
    manifest.close()
    os.remove(manifest.path)
    print(f"removed {counts['removed']} copies ({size / MB:.1f} MB), {counts['missing']} were "
          f"already gone, {counts['changed']} changed since and left in place; "
          f"{len(left)} folders not empty and left; {time.perf_counter() - t0:.1f} s")
    for p in changed[:40]:
        print("  LEFT " + p)
    return 0


def check(game, only):
    t0 = time.perf_counter()
    manifest = Manifest(game)
    if not manifest.exists():
        jobs, keep, drop, counts, ambiguous = plan(game, manifest, only)
        stored = sum(e["size"] for e in jobs)
        print(f"nothing installed. {counts['archived']} models in the archives: {len(jobs)} to "
              f"write ({stored / MB:.1f} MB as stored, about {2.2 * stored / MB:.0f} MB "
              f"uncompressed); left out: {counts['loose']} loose (the mod's own), {counts['raw']} "
              f"already uncompressed, {len(ambiguous)} stored differently in two archives"
              + (f", {counts['unlisted']} not in the list" if only is not None else ""))
        return 0
    models, _ = archived_models(game)
    problems = []
    for k, rec in sorted(manifest.files.items()):
        full = os.path.join(game, rec["path"])
        if not os.path.exists(full):
            problems.append(f"missing: {rec['path']}")
        elif sha256_file(full) != rec["sha256"]:
            problems.append(f"changed: {rec['path']}")
        elif k not in models:
            problems.append(f"no longer in the archives: {rec['path']}")
        elif source_of(models[k]) != rec["source"]:
            problems.append(f"its archive entry changed: {rec['path']}")
    stray = stray_temporaries(game)
    problems += [f"temporary file left: {p}" for p in stray]
    total = sum(r["size"] for r in manifest.files.values())
    total_src = sum(r["source"]["size"] for r in manifest.files.values())
    print(f"{len(manifest.files)} copies ({total_src / MB:.1f} MB as stored -> {total / MB:.1f} MB), "
          f"{len(manifest.dirs)} folders created; {len(problems)} problems; "
          f"{time.perf_counter() - t0:.1f} s")
    for p in problems[:40]:
        print("  " + p)
    if problems:
        print("run --install again to bring the copies up to date, or --undo")
    return 1 if problems else 0


def main(argv):
    args = {"install": False, "undo": False, "check": False, "granny": None,
            "granny_install": None, "only": None, "workers": max(1, (os.cpu_count() or 2) // 2),
            "work": None}
    games, only_path, i = [], None, 0
    try:
        while i < len(argv):
            a = argv[i]
            if a in ("--install", "--undo", "--check"):
                args[a[2:]] = True
            elif a == "--granny":
                args["granny"], i = argv[i + 1], i + 1
            elif a == "--granny-install":
                args["granny_install"], i = argv[i + 1], i + 1
            elif a == "--only-used":
                only_path, i = argv[i + 1], i + 1
            elif a == "--workers":
                args["workers"], i = int(argv[i + 1]), i + 1
            elif a == "--work":
                args["work"], i = argv[i + 1], i + 1
            elif a.startswith("-"):
                raise ValueError(a)
            else:
                games.append(a)
            i += 1
    except (IndexError, ValueError):
        games = []
    modes = args["install"] + args["undo"] + args["check"]
    if len(games) != 1 or modes > 1 or args["workers"] < 1 or \
            (args["install"] and not args["granny"]):
        print(__doc__)
        return 2
    game = os.path.abspath(games[0])
    try:
        refuse_steam(game)
    except RefusedPath as exc:
        print(f"refused: {exc}")
        return 2
    if not os.path.isdir(os.path.join(game, "art")) or not archives(game):
        print(f"refused: {game} has no art\\Art*.bar: not a game folder")
        return 2
    if only_path is not None:
        args["only"] = used_list(only_path, game)
        print(f"{only_path}: {len(args['only'])} models listed")
    if args["undo"]:
        return undo(game)
    if args["install"]:
        return install(game, args)
    return check(game, args["only"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
