# SPDX-License-Identifier: GPL-3.0-or-later
"""List or extract the files inside a legacy AoE3 .bar archive (header "ESPN").

Usage:
    python -I tools/bar.py <archive.bar> [filter]
    python -I tools/bar.py <archive.bar> [filter] --extract <output folder>

The filter is a case-insensitive substring of the stored path, e.g. "tactics/explorer" or
"rev_banner" (either slash works). Extracted files keep their stored path below the output
folder. Files are written
as stored: compiled XML (.xmb) usually starts with "l33t" (zlib); read it with
tools/xmbedit.py.

Format (as read from the TAD archives Data*.bar and Art*.bar; nothing else is assumed):
    0x000  "ESPN"
    0x118  uint32  number of files
    0x11C  uint32  offset of the file table
    table: uint32 root length (UTF-16 chars), root name (e.g. "Data\\"),
           uint32 entry count, then per entry:
           uint32 offset, uint32 size, uint32 size again, 16 bytes of timestamp,
           uint32 name length (UTF-16 chars), name.
"""
import os
import struct
import sys


def read_entries(path):
    """Returns [(stored path, offset, size)] for every file in the archive."""
    with open(path, "rb") as f:
        head = f.read(0x124)
        if head[:4] != b"ESPN":
            raise ValueError(f"{path}: not a legacy AoE3 archive (header {head[:4]!r})")
        table = struct.unpack_from("<I", head, 0x11C)[0]
        f.seek(table)
        raw = f.read()
    pos = 0

    def u32():
        nonlocal pos
        value = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        return value

    def utf16(chars):
        nonlocal pos
        text = raw[pos:pos + 2 * chars].decode("utf-16-le")
        pos += 2 * chars
        return text

    root = utf16(u32())
    entries = []
    for _ in range(u32()):
        offset, size, _size2 = u32(), u32(), u32()
        pos += 16  # timestamp
        entries.append((root + utf16(u32()), offset, size))
    return entries


def safe_target(folder, stored):
    """Maps a stored path below folder; refuses absolute paths and '..' components."""
    parts = [p for p in stored.replace("/", "\\").split("\\") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        raise ValueError(f"refusing unsafe stored path {stored!r}")
    return os.path.join(folder, *parts)


def main(argv):
    args = [a for a in argv if a != "--extract"]
    out = None
    if "--extract" in argv:
        i = argv.index("--extract")
        if i + 1 >= len(argv):
            sys.exit("--extract needs an output folder")
        out = argv[i + 1]
        args.remove(out)
    if not args or len(args) > 2:
        sys.exit(__doc__)
    archive = args[0]
    needle = args[1].lower().replace("/", "\\") if len(args) == 2 else ""
    entries = read_entries(archive)
    hits = [e for e in entries if needle in e[0].lower()]
    print(f"{archive}: {len(entries)} files, {len(hits)} match")
    for name, _offset, size in hits:
        print(f"{size:10} {name}")
    if out is None:
        return
    with open(archive, "rb") as f:
        for name, offset, size in hits:
            target = safe_target(out, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            f.seek(offset)
            with open(target, "wb") as g:
                g.write(f.read(size))
    print(f"extracted {len(hits)} files to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
