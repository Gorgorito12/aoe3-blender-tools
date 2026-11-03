# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads PNG files with the standard library and numpy: 8-bit greyscale, RGB, RGBA and palette
(returned as RGB), not interlaced, all five row filters. Enough for the generator's own textures
and the material swatches; anything else raises ValueError."""
import struct
import zlib

import numpy as np

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}       # colour type -> channels (3: palette indices)


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(data):
    """The image as a uint8 array (height, width, channels)."""
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG file")
    pos, idat, ihdr, plte = 8, [], None, None
    while pos < len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            plte = np.frombuffer(body, np.uint8).reshape(-1, 3)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    if ihdr is None:
        raise ValueError("PNG without IHDR")
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or ctype not in CHANNELS or interlace:
        raise ValueError(f"unsupported PNG: depth {depth}, colour type {ctype}, interlace {interlace}")
    n = CHANNELS[ctype]
    stride = w * n
    raw = zlib.decompress(b"".join(idat))
    if len(raw) != h * (stride + 1):
        raise ValueError("PNG data has the wrong length")
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        row = raw[y * (stride + 1):(y + 1) * (stride + 1)]
        f = row[0]
        cur = np.frombuffer(row, np.uint8, offset=1).astype(np.int32)
        if f == 0:
            pass
        elif f == 1:            # sub: a running sum along the row, per channel, modulo 256
            cur = (np.cumsum(cur.reshape(w, n), axis=0) & 255).reshape(stride)
        elif f == 2:
            cur = (cur + prev) & 255
        elif f == 3:
            cur = cur.copy()
            for x in range(stride):
                left = cur[x - n] if x >= n else 0
                cur[x] = (cur[x] + ((left + prev[x]) >> 1)) & 255
        elif f == 4:
            cur = cur.copy()
            pl = prev.tolist()
            cl = cur.tolist()
            for x in range(stride):
                a = cl[x - n] if x >= n else 0
                c = pl[x - n] if x >= n else 0
                cl[x] = (cl[x] + _paeth(a, pl[x], c)) & 255
            cur = np.array(cl, np.int32)
        else:
            raise ValueError(f"bad PNG filter {f}")
        out[y] = cur
        prev = cur
    img = out.reshape(h, w, n)
    if ctype == 3:
        if plte is None:
            raise ValueError("palette PNG without PLTE")
        return plte[img[:, :, 0]]
    return img


def encode_png(array):
    """PNG bytes of an 8-bit grey, RGB or RGBA array (filter 0, zlib level 6)."""
    a = np.ascontiguousarray(array, dtype=np.uint8)
    if a.ndim == 2:
        a = a[:, :, None]
    h, w, n = a.shape
    ctype = {1: 0, 3: 2, 4: 6}[n]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
