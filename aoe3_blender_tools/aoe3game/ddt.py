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


# --------------------------------------------------------------------------------------------------
# Block compression (DXT1, DXT3)

def _blocks(rgba):
    """N x 16 x 4 float32 pixel blocks of an H x W x 4 image (edges repeated to a multiple of 4)."""
    np = _np()
    h, w = rgba.shape[:2]
    ph, pw = -(-h // 4) * 4, -(-w // 4) * 4
    a = np.pad(rgba, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge").astype(np.float32)
    bh, bw = ph // 4, pw // 4
    return a.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * bw, 16, 4)


def _to565(c):
    np = _np()
    q = np.clip(np.rint(c * np.array([31, 63, 31]) / 255.0), 0, [31, 63, 31]).astype(np.uint32)
    return (q[:, 0] << 11) | (q[:, 1] << 5) | q[:, 2]


def _colour_encode(px):
    """8-byte colour blocks (always the 4-colour mode) for N x 16 x 3 float pixels."""
    np = _np()
    lo, hi = px.min(axis=1), px.max(axis=1)
    inset = (hi - lo) / 16.0
    lo, hi = np.clip(lo + inset, 0, 255), np.clip(hi - inset, 0, 255)
    c0, c1 = _to565(hi), _to565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _rgb565(c0.astype(np.uint16)), _rgb565(c1.astype(np.uint16))
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], axis=1)        # N x 4 x 3
    d = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                     # N x 16 x 4
    idx = d.argmin(-1).astype(np.uint32)
    idx[c0 == c1] = 0                       # one colour: index 0 everywhere (no 3-colour mode)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(axis=1).astype(np.uint32)
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0], out[:, 1] = c0 & 255, c0 >> 8
    out[:, 2], out[:, 3] = c1 & 255, c1 >> 8
    for k in range(4):
        out[:, 4 + k] = (bits >> (8 * k)) & 255
    return out


def compress(rgba, fmt):
    """The block-compressed bytes of one level: DXT1 (8 bytes a block, alpha dropped) or DXT3
    (16 bytes: explicit 4-bit alpha, then the colour block)."""
    np = _np()
    b = _blocks(rgba)
    colour = _colour_encode(b[:, :, :3])
    if fmt == DXT1:
        return colour.tobytes()
    if fmt != DXT3:
        raise DdtError(f"format {fmt} is not encoded")
    a4 = np.clip(np.rint(b[:, :, 3] / 17.0), 0, 15).astype(np.uint8)              # N x 16
    alpha = (a4[:, 0::2] | (a4[:, 1::2] << 4)).astype(np.uint8)                   # N x 8
    return np.concatenate([alpha, colour], axis=1).tobytes()


def write_dxt(rgba, fmt=DXT3, *, alpha=1, usage=0, mips=True):
    """Bytes of a DXT1 or DXT3 texture (with its mip levels down to 4 x 4) from an H x W x 3 or 4
    uint8 array, top row first. DXT3 keeps the alpha (player-colour mask); DXT1 drops it."""
    np = _np()
    a = np.asarray(rgba)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise DdtError("expected an H x W x 3 or 4 array")
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, a.dtype)], axis=2)
    a = a.astype(np.uint8)
    h, w = a.shape[:2]
    levels = mip_chain(a) if mips else [a]
    blobs = [compress(lv, fmt) for lv in levels]
    out = bytearray(MAGIC + bytes([usage, alpha if fmt == DXT3 else 0, fmt, len(blobs)])
                    + struct.pack("<II", w, h))
    off = 16 + 8 * len(blobs)
    for b in blobs:
        out += struct.pack("<II", off, len(b))
        off += len(b)
    for b in blobs:
        out += b
    return bytes(out)


def write(rgba, fmt=DXT3, *, alpha=1, usage=0, mips=True):
    """A texture in the given format: BGRA (uncompressed), DXT1 or DXT3."""
    if fmt == BGRA:
        return write_bgra(rgba, alpha=alpha, usage=usage, mips=mips)
    return write_dxt(rgba, fmt, alpha=alpha, usage=usage, mips=mips)


def _alpha_encode(a):
    """8-byte DXT5 alpha blocks for N x 16 float alpha values (the 8-value mode, a0 > a1)."""
    np = _np()
    a0 = np.clip(np.rint(a.max(axis=1)), 0, 255).astype(np.int32)
    a1 = np.clip(np.rint(a.min(axis=1)), 0, 255).astype(np.int32)
    flat = a0 == a1
    a0 = np.where(flat & (a0 < 255), a0 + 1, a0)       # keep a0 > a1 (the 8-value mode)
    a1 = np.where(flat & (a0 == 255) & (a1 == 255), 254, a1)
    f0, f1 = a0.astype(np.float32), a1.astype(np.float32)
    pal = np.stack([f0, f1] + [((7 - k) * f0 + k * f1) / 7 for k in range(1, 7)], axis=1)
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)   # N x 16
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(axis=1).astype(np.uint64)
    out = np.zeros((len(a), 8), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for k in range(6):
        out[:, 2 + k] = ((bits >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
    return out


def compress_dxt5(rgba):
    """DXT5 bytes of one level: interpolated alpha, then the colour block."""
    np = _np()
    b = _blocks(rgba)
    return np.concatenate([_alpha_encode(b[:, :, 3]), _colour_encode(b[:, :, :3])],
                          axis=1).tobytes()


def write_normal_map(rgba, *, mips=False):
    """Bytes of a bump texture as the game's own (DXT5, usage 6 = low detail + bump, alpha 0)
    from an H x W x 4 array packed like them: R specular (0 = none), G the normal's Y, B its Z,
    A its X, each 128 for 0."""
    np = _np()
    a = np.asarray(rgba).astype(np.uint8)
    h, w = a.shape[:2]
    levels = mip_chain(a) if mips else [a]
    blobs = [compress_dxt5(lv) for lv in levels]
    out = bytearray(MAGIC + bytes([6, 0, DXT5, len(blobs)]) + struct.pack("<II", w, h))
    off = 16 + 8 * len(blobs)
    for b in blobs:
        out += struct.pack("<II", off, len(b))
        off += len(b)
    for b in blobs:
        out += b
    return bytes(out)


def normal_from_texture(rgba, strength=6.0, blur=1):
    """A bump map from the diffuse texture: its brightness taken as height (joints, frames and
    openings are darker, so they come out sunk), packed as `write_normal_map` expects."""
    np = _np()
    lum = np.asarray(rgba)[..., :3].astype(np.float32).mean(axis=2) / 255.0
    for _ in range(blur):                                  # a light 3 x 3 box blur
        p = np.pad(lum, 1, mode="edge")
        lum = sum(p[dy:dy + lum.shape[0], dx:dx + lum.shape[1]]
                  for dy in range(3) for dx in range(3)) / 9.0
    p = np.pad(lum, 1, mode="edge")
    dx = (p[1:-1, 2:] - p[1:-1, :-2]) / 2
    dy = (p[2:, 1:-1] - p[:-2, 1:-1]) / 2
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(lum)   # rows go down, V goes up
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / n, ny / n, nz / n
    out = np.zeros(lum.shape + (4,), np.uint8)
    out[..., 1] = np.clip(ny * 127.5 + 127.5, 0, 255)
    out[..., 2] = np.clip(nz * 127.5 + 127.5, 0, 255)
    out[..., 3] = np.clip(nx * 127.5 + 127.5, 0, 255)
    return out
