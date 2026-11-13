# SPDX-License-Identifier: GPL-3.0-or-later
"""Animation tag files (`<animation>.gr2.precomp`): the game's sampled positions of the named
bones of one Granny animation, such as `HITPOINTBAR`, where a unit's floating health bar sits.

Standard library only. Measured on the 6,211 `.gr2.precomp` files of the game's archives (every one
parses and re-encodes byte for byte), and on the game's reader of the "MS" block:

    "SX" u32 size {                     a chunk is a 2-byte tag, a u32 size, then that many bytes
        "SV" u32 4 { u32 version }      4
        u32                             0
        "LT" u32 size { u32 1, u32 n, n x name }      the tag names (UTF-16: u32 length, chars)
        8 bytes                         0, 0
        u32 b                           blocks: 1 in 6,175 of the 6,211 files, up to 10
        b x {                           the tags as sampled on one model (only the first block
                                        is parsed; the others stay as read)
            "MS" u32 size {
                "SV" u32 4 { u32 version }      3
                u32 t                           tracks
                t x { u32 k, k x 16 bytes }     a rotation (4 floats) per key
                t x "PF" u32 size { u32 k, k x 3 floats }   the position in model space per key
                u32 m, m x { u32 name index, "DO" u32 size { u32 j, j x u32 track } }
                version >= 2: u32 q, q x 16 bytes, "EP" u32 size { ... }
                f32 duration                    seconds
            }
            name                        the model of that block (an art path)
        }
    }

The keys of a track are spread evenly over the duration (every file with tracks has the same
number of keys in all of them). A name can map to several tracks. The game reads the names and
position tracks of this file as the tags of the animation, and a loose file in the art folder
wins over the one in an archive (seen in game). When the animation a unit plays has no
`HITPOINTBAR`, the game puts the floating health bar at a height of its own, so the bar jumps
each time the unit changes to or from such an animation; the base game's own horse idles
(`animation_library\\cavalry\\horse_idle_a` to `_g`, but not `_h` and `_i`) are such files.
"""
import struct

HITPOINTBAR = "HITPOINTBAR"


class PrecompError(ValueError):
    pass


class _Reader:
    def __init__(self, data, pos=0, end=None):
        self.data, self.pos = data, pos
        self.end = len(data) if end is None else end

    def take(self, n):
        if n < 0 or self.pos + n > self.end:
            raise PrecompError(f"truncated at {self.pos:#x}")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def chunk(self, tag):
        if self.data[self.pos:self.pos + 2] != tag:
            raise PrecompError(f"expected {tag.decode()} at {self.pos:#x}, "
                               f"found {self.data[self.pos:self.pos + 2]!r}")
        self.pos += 2
        size = self.u32()
        body = _Reader(self.data, self.pos, self.pos + size)
        self.take(size)
        return body

    def name(self):
        n = self.u32()
        return self.take(2 * n).decode("utf-16-le")

    def rest(self):
        return self.take(self.end - self.pos)

    def done(self):
        if self.pos != self.end:
            raise PrecompError(f"{self.end - self.pos} unread bytes at {self.pos:#x}")


def _chunk(tag, body):
    return tag + struct.pack("<I", len(body)) + body


def _name(text):
    raw = text.encode("utf-16-le")
    return struct.pack("<I", len(raw) // 2) + raw


class Precomp:
    """One parsed file. `names`, `rotations` (per track, 16-byte keys), `positions` (per track,
    (x, y, z) keys) and `mapping` ([(name index, [track, ...])]) can be edited; `encode()` writes
    the file back, the other fields as they were read."""

    @classmethod
    def parse(cls, data):
        self = cls()
        top = _Reader(data)
        sx = top.chunk(b"SX")
        top.done()
        sv = sx.chunk(b"SV")
        self.version = sv.u32()
        sv.done()
        self.head = sx.take(4)
        lt = sx.chunk(b"LT")
        self.names_head = lt.take(4)
        self.names = [lt.name() for _ in range(lt.u32())]
        lt.done()
        self.middle = sx.take(8)
        self.blocks = sx.u32()
        ms = sx.chunk(b"MS")
        sv = ms.chunk(b"SV")
        self.ms_version = sv.u32()
        sv.done()
        tracks = ms.u32()
        self.rotations = [[ms.take(16) for _ in range(ms.u32())] for _ in range(tracks)]
        self.positions = []
        for _ in range(tracks):
            pf = ms.chunk(b"PF")
            self.positions.append([struct.unpack("<3f", pf.take(12)) for _ in range(pf.u32())])
            pf.done()
        self.mapping = []
        for _ in range(ms.u32()):
            index = ms.u32()
            do = ms.chunk(b"DO")
            self.mapping.append((index, [do.u32() for _ in range(do.u32())]))
            do.done()
        self.extra = b""
        if self.ms_version >= 2:
            start = ms.pos
            ms.take(16 * ms.u32())
            ms.chunk(b"EP")
            self.extra = data[start:ms.pos]
        self.duration = struct.unpack("<f", ms.take(4))[0]
        ms.done()
        tail_start = sx.pos
        self.model = sx.name()
        if self.blocks == 1:
            sx.done()
        sx.pos = tail_start
        self.tail = sx.rest()
        return self

    def encode(self):
        lt = self.names_head + struct.pack("<I", len(self.names)) + b"".join(map(_name, self.names))
        ms = _chunk(b"SV", struct.pack("<I", self.ms_version))
        ms += struct.pack("<I", len(self.positions))
        for keys in self.rotations:
            ms += struct.pack("<I", len(keys)) + b"".join(keys)
        for keys in self.positions:
            ms += _chunk(b"PF", struct.pack("<I", len(keys)) + b"".join(struct.pack("<3f", *k) for k in keys))
        ms += struct.pack("<I", len(self.mapping))
        for index, tracks in self.mapping:
            ms += struct.pack("<I", index)
            ms += _chunk(b"DO", struct.pack("<I", len(tracks)) + b"".join(struct.pack("<I", t) for t in tracks))
        ms += self.extra + struct.pack("<f", self.duration)
        sx = _chunk(b"SV", struct.pack("<I", self.version)) + self.head + _chunk(b"LT", lt)
        sx += self.middle + struct.pack("<I", self.blocks) + _chunk(b"MS", ms) + self.tail
        return _chunk(b"SX", sx)

    def tracks_of(self, name):
        """The position tracks of a tag name (case-insensitive), [] when the file has none."""
        wanted = name.upper()
        out = []
        for index, tracks in self.mapping:
            if 0 <= index < len(self.names) and self.names[index].upper() == wanted:
                out += [self.positions[t] for t in tracks if 0 <= t < len(self.positions)]
        return out

    def has(self, name):
        return bool(self.tracks_of(name))

    def key_count(self):
        """The number of keys of the file's tracks, or None when there are no tracks or they
        disagree (such a file is refused by add_constant)."""
        counts = {len(k) for k in self.positions} | {len(k) for k in self.rotations}
        return counts.pop() if len(counts) == 1 else None

    def add_constant(self, name, position, rotation):
        """Adds a tag that stays at `position` (x, y, z) with `rotation` (16 bytes) for the whole
        animation, as a new track with the file's number of keys."""
        if self.has(name):
            raise PrecompError(f"the file already has {name}")
        if self.blocks != 1:
            raise PrecompError(f"the file holds the tags sampled on {self.blocks} models; "
                               "only files with one are handled")
        keys = self.key_count()
        if not keys:
            raise PrecompError("the file has no tracks to take the number of keys from")
        if len(rotation) != 16:
            raise PrecompError("a rotation is 16 bytes")
        track = len(self.positions)
        self.rotations.append([bytes(rotation)] * keys)
        self.positions.append([tuple(float(v) for v in position)] * keys)
        self.names.append(name)
        self.mapping.append((len(self.names) - 1, [track]))


def load(data):
    """A Precomp from bytes; refuses a file that does not re-encode to the same bytes."""
    doc = Precomp.parse(data)
    if doc.encode() != data:
        raise PrecompError("re-encoding does not reproduce the file; refusing to edit it")
    return doc
