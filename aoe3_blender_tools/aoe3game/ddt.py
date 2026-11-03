# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's textures (.ddt).

    0   "RTS3"
    4   u8 usage    bits: 1 alpha test, 2 low detail, 4 bump (6 = bump normal map)
    5   u8 alpha    0 none, 1 player colour, 4 transparent, 8 blend
    6   u8 format   1 BGRA, 4 DXT1, 7 grey, 8 DXT3, 9 DXT5
    7   u8 mip levels
    8   u32 width, u32 height
    16  (u32 offset, u32 size) per mip level, largest first; then the data

Measured on the game's files: player-coloured textures keep alpha 255 where the texture shows
and lower it where the player colour shows. Header functions use the standard library only;
pixel work (writing, decoding) uses numpy.
"""
import struct

MAGIC = b"RTS3"
FORMATS = {1: "BGRA", 4: "DXT1", 7: "grey", 8: "DXT3", 9: "DXT5"}
ALPHAS = {0: "none", 1: "player colour", 4: "transparent", 8: "blend"}
BGRA, DXT1, GREY, DXT3, DXT5 = 1, 4, 7, 8, 9


class DdtError(ValueError):
    pass


class Header:
    def __init__(self, usage, alpha, fmt, mips, width, height, levels):
        self.usage, self.alpha, self.format = usage, alpha, fmt
        self.mips, self.width, self.height, self.levels = mips, width, height, levels

    def describe(self):
        bits = [n for b, n in ((1, "alpha test"), (2, "low detail"), (4, "bump"))
                if self.usage & b]
        return (f"{self.width}x{self.height} {FORMATS.get(self.format, self.format)} "
                f"alpha={ALPHAS.get(self.alpha, self.alpha)} "
                f"usage={'+'.join(bits) or '0'} mips={self.mips}")


def read_header(data):
    if data[:4] != MAGIC:
        raise DdtError("not a .ddt (no RTS3)")
    usage, alpha, fmt, mips = data[4], data[5], data[6], data[7]
    w, h = struct.unpack_from("<II", data, 8)
    levels = []
    for i in range(mips):
        if 16 + 8 * i + 8 > len(data):
            break
        levels.append(struct.unpack_from("<II", data, 16 + 8 * i))
    return Header(usage, alpha, fmt, mips, w, h, levels)


def _np():
    import numpy
    return numpy


def mip_chain(rgba, smallest=4):
    """The image and its halvings (2 x 2 box filter) down to `smallest` pixels on a side."""
    np = _np()
    levels = [rgba]
    cur = rgba.astype(np.float32)
    while min(cur.shape[0], cur.shape[1]) // 2 >= smallest:
        h, w = cur.shape[0] // 2 * 2, cur.shape[1] // 2 * 2
        cur = cur[:h, :w].reshape(h // 2, 2, w // 2, 2, cur.shape[2]).mean(axis=(1, 3))
        levels.append(np.clip(cur + 0.5, 0, 255).astype(np.uint8))
    return levels


def write_bgra(rgba, *, alpha=1, usage=0, mips=True):
    """Bytes of an uncompressed BGRA texture from an H x W x 3 or 4 uint8 array (top row first).
    Without an alpha channel the alpha is 255 everywhere (no player colour shows)."""
    np = _np()
    a = np.asarray(rgba)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise DdtError("expected an H x W x 3 or 4 array")
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, a.dtype)], axis=2)
    a = a.astype(np.uint8)
    h, w = a.shape[:2]
    levels = mip_chain(a) if mips else [a]
    blobs = [np.ascontiguousarray(lv[:, :, [2, 1, 0, 3]]).tobytes() for lv in levels]
    out = bytearray(MAGIC + bytes([usage, alpha, BGRA, len(blobs)]) + struct.pack("<II", w, h))
    off = 16 + 8 * len(blobs)
    for b in blobs:
        out += struct.pack("<II", off, len(b))
        off += len(b)
    for b in blobs:
        out += b
    return bytes(out)


# --------------------------------------------------------------------------------------------------
# Decoding (for the survey and checks)

def _rgb565(c):
    np = _np()
    r = ((c >> 11) & 31).astype(np.float32) * (255 / 31)
    g = ((c >> 5) & 63).astype(np.float32) * (255 / 63)
    b = (c & 31).astype(np.float32) * (255 / 31)
    return np.stack([r, g, b], axis=-1)


def _colour_blocks(blk, opaque_only):
    """RGB of DXT colour blocks: blk is N x 8 uint8; returns N x 16 x 3 float."""
    np = _np()
    c0 = blk[:, 0].astype(np.uint16) | (blk[:, 1].astype(np.uint16) << 8)
    c1 = blk[:, 2].astype(np.uint16) | (blk[:, 3].astype(np.uint16) << 8)
    bits = (blk[:, 4].astype(np.uint32) | (blk[:, 5].astype(np.uint32) << 8)
            | (blk[:, 6].astype(np.uint32) << 16) | (blk[:, 7].astype(np.uint32) << 24))
    p0, p1 = _rgb565(c0), _rgb565(c1)
    four = (c0 > c1) | opaque_only
    p2 = np.where(four[:, None], (2 * p0 + p1) / 3, (p0 + p1) / 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) / 3, 0)
    pal = np.stack([p0, p1, p2, p3], axis=1)                    # N x 4 x 3
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    return np.take_along_axis(pal, idx[:, :, None].astype(np.int64), axis=1)


def decode(data, level=0):
    """H x W x 4 uint8 RGBA of one mip level (BGRA, grey, DXT1, DXT3, DXT5)."""
    np = _np()
    hd = read_header(data)
    w, h = max(1, hd.width >> level), max(1, hd.height >> level)
    off, size = hd.levels[level]
    raw = np.frombuffer(data, np.uint8, size, off)
    if hd.format == BGRA:
        px = raw[:w * h * 4].reshape(h, w, 4)
        return px[:, :, [2, 1, 0, 3]].copy()
    if hd.format == GREY:
        g = raw[:w * h].reshape(h, w)
        return np.stack([g, g, g, np.full_like(g, 255)], axis=-1)
    if hd.format not in (DXT1, DXT3, DXT5):
        raise DdtError(f"format {hd.format} is not decoded")
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    bsize = 8 if hd.format == DXT1 else 16
    blk = raw[:bw * bh * bsize].reshape(bw * bh, bsize)
    if hd.format == DXT1:
        rgb = _colour_blocks(blk, np.zeros(len(blk), bool))
        alpha = np.full(rgb.shape[:2], 255.0)
    else:
        rgb = _colour_blocks(blk[:, 8:], np.ones(len(blk), bool))
        if hd.format == DXT3:
            nib = np.stack([blk[:, :8] & 15, blk[:, :8] >> 4], axis=-1).reshape(len(blk), 16)
            alpha = nib.astype(np.float32) * 17
        else:
            a0, a1 = blk[:, 0].astype(np.float32), blk[:, 1].astype(np.float32)
            bits = np.zeros(len(blk), np.uint64)
            for k in range(6):
                bits |= blk[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
            idx = (bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & np.uint64(7)
            idx = idx.astype(np.int64)
            eight = (a0 > a1)[:, None]
            lerp8 = [a0, a1] + [((7 - k) * a0 + k * a1) / 7 for k in range(1, 7)]
            lerp6 = [a0, a1] + [((5 - k) * a0 + k * a1) / 5 for k in range(1, 5)] + \
                    [np.zeros_like(a0), np.full_like(a0, 255)]
            pal = np.where(eight[:, :, None], np.stack(lerp8, 1)[:, None, :],
                           np.stack(lerp6, 1)[:, None, :])[:, 0, :]
            alpha = np.take_along_axis(pal, idx, axis=1)
    px = np.concatenate([rgb, alpha[:, :, None]], axis=-1)       # N x 16 x 4
    px = px.reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return np.clip(px[:h, :w] + 0.5, 0, 255).astype(np.uint8)
