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


def mip_chain(rgba, smallest=4, bump=False):
    """The image and its halvings (2 x 2 box filter) down to `smallest` pixels on the short side.
    bump: the image is a packed normal map (`write_normal_map`): each level's normal is made unit
    length again after the filter, so a small level does not flatten the relief."""
    np = _np()
    levels = [rgba]
    cur = rgba.astype(np.float32)
    while min(cur.shape[0], cur.shape[1]) // 2 >= smallest:
        h, w = cur.shape[0] // 2 * 2, cur.shape[1] // 2 * 2
        cur = cur[:h, :w].reshape(h // 2, 2, w // 2, 2, cur.shape[2]).mean(axis=(1, 3))
        if bump:
            cur = renormalise(cur)
        levels.append(np.clip(cur + 0.5, 0, 255).astype(np.uint8))
    return levels


def chain_length(width, height, smallest=4):
    """The number of levels of a full chain: halvings until the short side would drop below
    `smallest` (the game's own textures stop at 4 px, some at 8: 512 x 512 -> 8 or 7 levels)."""
    n, short = 1, min(width, height)
    while short // 2 >= smallest:
        short //= 2
        n += 1
    return n


def fitted(rgba, size):
    """The image halved until its longer side is at most `size`: the mip level the game would
    show, so a smaller texture is the larger one's own level and not another painting."""
    if max(rgba.shape[0], rgba.shape[1]) <= size:
        return rgba
    np = _np()
    cur = rgba.astype(np.float32)
    while max(cur.shape[0], cur.shape[1]) > size:
        cur = halve(cur)
    return np.clip(cur + 0.5, 0, 255).astype(np.uint8)


def _area_weights(n_in, n_out):
    """n_out x n_in matrix of an area-average resampling (n_out <= n_in): each output pixel is the
    mean of the input pixels it covers, partial pixels weighted by their share."""
    np = _np()
    m = np.zeros((n_out, n_in), np.float64)
    scale = n_in / n_out
    for i in range(n_out):
        a, b = i * scale, (i + 1) * scale
        j = int(np.floor(a))
        while j < b and j < n_in:
            m[i, j] += min(b, j + 1) - max(a, j)
            j += 1
        m[i] /= m[i].sum()
    return m


def area_resize(img, h, w):
    """An H x W x C image reduced to h x w by area averaging (float32), the filter of
    core/airepaint.resize for a reduction; at exactly half it is the 2 x 2 box of mip_chain."""
    np = _np()
    a = np.asarray(img, np.float64)
    if (h, w) == a.shape[:2]:
        return a.astype(np.float32)
    if h > a.shape[0] or w > a.shape[1]:
        raise DdtError("area_resize only reduces")
    a = np.einsum("ij,jkc->ikc", _area_weights(a.shape[0], h), a)
    a = np.einsum("ij,kjc->kic", _area_weights(a.shape[1], w), a)
    return a.astype(np.float32)


def halve(img):
    """One level down: each side halved (at least 1 px), by area averaging."""
    return area_resize(img, max(1, img.shape[0] // 2), max(1, img.shape[1] // 2))


def renormalise(img):
    """A packed normal map (A = X, G = Y, B = Z, 128 for 0; R is specular and kept) with each
    normal scaled back to unit length (float32, 0-255)."""
    np = _np()
    a = np.asarray(img, np.float32).copy()
    n = (a[..., [3, 1, 2]] - 127.5) / 127.5
    length = np.sqrt((n * n).sum(axis=-1, keepdims=True))
    n = np.where(length > 1e-3, n / np.maximum(length, 1e-3), n)
    a[..., [3, 1, 2]] = n * 127.5 + 127.5
    return a


def is_packed_normal_map(rgba, tolerance=0.2):
    """Do the A, G, B channels hold unit normals as `write_normal_map` packs them? (The mean of
    | |n| - 1 | below `tolerance`.) A bump texture packed otherwise is filtered as colour."""
    np = _np()
    a = np.asarray(rgba, np.float32)
    if a.ndim != 3 or a.shape[2] != 4:
        return False
    if float((a[..., 3] >= 254).mean()) > 0.9:      # X saturated nearly everywhere: an alpha mask
        return False
    n = (a[..., [3, 1, 2]] - 127.5) / 127.5
    if float(n[..., 2].mean()) < 0.3:                # normals face out of the surface (Z > 0)
        return False
    return float(np.abs(np.sqrt((n * n).sum(axis=-1)) - 1).mean()) < tolerance


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


def _fit(px, c0, c1):
    """(c0, c1, indices, squared error) of N blocks for 565 endpoints in the 4-colour mode:
    c0 >= c1 after the call (c0 > c1 selects that mode; equal endpoints use index 0 only)."""
    np = _np()
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _rgb565(c0.astype(np.uint16)), _rgb565(c1.astype(np.uint16))
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], axis=1)        # N x 4 x 3
    d = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                     # N x 16 x 4
    idx = d.argmin(-1).astype(np.uint32)
    same = c0 == c1
    idx[same] = 0                           # one colour: index 0 everywhere (no 3-colour mode)
    err = np.take_along_axis(d, idx[:, :, None].astype(np.int64), axis=2)[:, :, 0].sum(axis=1)
    return c0, c1, idx, err


def _least_squares(px, idx):
    """The real-valued endpoints (e0, e1) that best fit the blocks for fixed indices, or None
    where every pixel uses the same weight (no unique solution)."""
    np = _np()
    w0 = np.array([1.0, 0.0, 2 / 3, 1 / 3])[idx]                                   # N x 16
    w1 = 1.0 - w0
    a, b, c = (w0 * w0).sum(1), (w0 * w1).sum(1), (w1 * w1).sum(1)
    x0 = (w0[:, :, None] * px).sum(1)
    x1 = (w1[:, :, None] * px).sum(1)
    det = a * c - b * b
    ok = np.abs(det) > 1e-6
    det = np.where(ok, det, 1.0)
    e0 = (c[:, None] * x0 - b[:, None] * x1) / det[:, None]
    e1 = (a[:, None] * x1 - b[:, None] * x0) / det[:, None]
    return np.clip(e0, 0, 255), np.clip(e1, 0, 255), ok


def _principal_ends(px):
    """Endpoints at the extremes of each block's projection on its principal colour axis."""
    np = _np()
    mean = px.mean(axis=1, keepdims=True)
    d = px - mean
    cov = np.einsum("nki,nkj->nij", d, d)
    v = px.max(axis=1) - px.min(axis=1) + 1e-3                                      # start axis
    for _ in range(8):
        v = np.einsum("nij,nj->ni", cov, v)
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
    t = np.einsum("nki,ni->nk", d, v)
    m = mean[:, 0, :]
    return (np.clip(m + v * t.max(1)[:, None], 0, 255), np.clip(m + v * t.min(1)[:, None], 0, 255))


def _colour_encode(px, refine=False):
    """8-byte colour blocks (always the 4-colour mode) for N x 16 x 3 float pixels.

    refine=False is the fast encoder: the block's bounding box, inset by 1/16. refine=True also
    tries the ends of the block's principal colour axis, refines each start by least squares
    (endpoints solved for the chosen indices, twice), tries the 565 neighbours of the result and
    keeps, per block, whichever gives the smallest error."""
    np = _np()
    lo, hi = px.min(axis=1), px.max(axis=1)
    inset = (hi - lo) / 16.0
    lo, hi = np.clip(lo + inset, 0, 255), np.clip(hi - inset, 0, 255)
    c0, c1, idx, err = _fit(px, _to565(hi), _to565(lo))
    if refine:
        starts = [(c0, c1), tuple(_to565(e) for e in _principal_ends(px))]
        for s0, s1 in starts:
            b0, b1, bidx, berr = _fit(px, s0, s1)
            for _ in range(2):
                e0, e1, ok = _least_squares(px, bidx)
                n0, n1, nidx, nerr = _fit(px, _to565(e0), _to565(e1))
                better = ok & (nerr < berr)
                b0, b1 = np.where(better, n0, b0), np.where(better, n1, b1)
                bidx = np.where(better[:, None], nidx, bidx)
                berr = np.where(better, nerr, berr)
            for d0, d1 in ((1, 0), (-1, 0), (0, 1), (0, -1)):       # one 565 step each way
                for ch, mask in ((11, 31), (5, 63), (0, 31)):
                    t0 = _step565(b0, ch, mask, d0)
                    t1 = _step565(b1, ch, mask, d1)
                    n0, n1, nidx, nerr = _fit(px, t0, t1)
                    better = nerr < berr
                    b0, b1 = np.where(better, n0, b0), np.where(better, n1, b1)
                    bidx = np.where(better[:, None], nidx, bidx)
                    berr = np.where(better, nerr, berr)
            better = berr < err
            c0, c1 = np.where(better, b0, c0), np.where(better, b1, c1)
            idx = np.where(better[:, None], bidx, idx)
            err = np.where(better, berr, err)
    return _pack_colour(c0, c1, idx)


def _step565(c, shift, mask, d):
    """c with one 565 channel moved by d steps (clamped)."""
    np = _np()
    c = c.astype(np.int64)
    v = np.clip(((c >> shift) & mask) + d, 0, mask)
    return ((c & ~(mask << shift)) | (v << shift)).astype(np.uint32)


def _pack_colour(c0, c1, idx):
    np = _np()
    c0, c1 = c0.astype(np.uint32), c1.astype(np.uint32)
    bits = (idx.astype(np.uint32) << (2 * np.arange(16, dtype=np.uint32))).sum(axis=1).astype(np.uint32)
    out = np.zeros((len(idx), 8), np.uint8)
    out[:, 0], out[:, 1] = c0 & 255, c0 >> 8
    out[:, 2], out[:, 3] = c1 & 255, c1 >> 8
    for k in range(4):
        out[:, 4 + k] = (bits >> (8 * k)) & 255
    return out


def colour_blocks_as_dxt1(col):
    """DXT1 blocks that decode exactly as the given colour blocks of a DXT3/DXT5 texture (N x 8
    uint8), which always use the 4-colour mode: endpoints in the wrong order are swapped with
    their indices, and a block of one colour gets index 0 throughout (DXT1 would read c0 == c1 as
    the 3-colour mode, whose index 3 is transparent black)."""
    np = _np()
    col = np.ascontiguousarray(col, np.uint8)
    c0 = col[:, 0].astype(np.uint32) | (col[:, 1].astype(np.uint32) << 8)
    c1 = col[:, 2].astype(np.uint32) | (col[:, 3].astype(np.uint32) << 8)
    bits = (col[:, 4].astype(np.uint32) | (col[:, 5].astype(np.uint32) << 8)
            | (col[:, 6].astype(np.uint32) << 16) | (col[:, 7].astype(np.uint32) << 24))
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    swap = c0 < c1
    idx = np.where(swap[:, None], np.array([1, 0, 3, 2], np.uint32)[idx], idx)
    a, b = np.where(swap, c1, c0), np.where(swap, c0, c1)
    idx[a == b] = 0
    return _pack_colour(a, b, idx)


def level_blocks(data, level=0):
    """(format, N x block-size uint8 array) of one level of a DXT1/DXT3/DXT5 texture."""
    np = _np()
    hd = read_header(data)
    if hd.format not in (DXT1, DXT3, DXT5):
        raise DdtError(f"format {hd.format} has no blocks")
    w, h = max(1, hd.width >> level), max(1, hd.height >> level)
    bsize = 8 if hd.format == DXT1 else 16
    n = max(1, (w + 3) // 4) * max(1, (h + 3) // 4)
    off, size = hd.levels[level]
    if size < n * bsize:
        raise DdtError(f"level {level} is short: {size} bytes for {n} blocks")
    return hd.format, np.frombuffer(data, np.uint8, n * bsize, off).reshape(n, bsize)


def compress(rgba, fmt, refine=False):
    """The block-compressed bytes of one level: DXT1 (8 bytes a block, alpha dropped) or DXT3
    (16 bytes: explicit 4-bit alpha, then the colour block). refine: see _colour_encode."""
    np = _np()
    b = _blocks(rgba)
    colour = _colour_encode(b[:, :, :3], refine)
    if fmt == DXT1:
        return colour.tobytes()
    if fmt != DXT3:
        raise DdtError(f"format {fmt} is not encoded")
    return np.concatenate([_dxt3_alpha(b[:, :, 3]), colour], axis=1).tobytes()


def _dxt3_alpha(a):
    """8-byte DXT3 alpha blocks (explicit 4 bits a pixel) for N x 16 alpha values."""
    np = _np()
    a4 = np.clip(np.rint(a / 17.0), 0, 15).astype(np.uint8)                       # N x 16
    return (a4[:, 0::2] | (a4[:, 1::2] << 4)).astype(np.uint8)                    # N x 8


def alpha_blocks(rgba, fmt):
    """The 8-byte alpha half of each DXT3 or DXT5 block of an H x W x 4 image."""
    b = _blocks(rgba)[:, :, 3]
    if fmt == DXT3:
        return _dxt3_alpha(b)
    if fmt == DXT5:
        return _alpha_encode(b)
    raise DdtError(f"format {fmt} has no alpha blocks")


def write_dxt(rgba, fmt=DXT3, *, alpha=1, usage=0, mips=True, refine=False):
    """Bytes of a DXT1, DXT3 or DXT5 texture (with its mip levels down to 4 x 4) from an H x W x 3
    or 4 uint8 array, top row first. DXT3 (4-bit steps) and DXT5 (interpolated) keep the alpha
    (player-colour mask); DXT1 drops it. refine: the slower, closer encoder (_colour_encode)."""
    np = _np()
    a = np.asarray(rgba)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise DdtError("expected an H x W x 3 or 4 array")
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, a.dtype)], axis=2)
    a = a.astype(np.uint8)
    h, w = a.shape[:2]
    levels = mip_chain(a) if mips else [a]
    blobs = [encode_level(lv, fmt, refine) for lv in levels]
    return pack(usage, alpha if fmt in (DXT3, DXT5) else 0, fmt, w, h, blobs)


def encode_level(rgba, fmt, refine=False):
    """The bytes of one level in BGRA, DXT1, DXT3 or DXT5 from an H x W x 4 uint8 array."""
    np = _np()
    if fmt == BGRA:
        return np.ascontiguousarray(np.asarray(rgba, np.uint8)[:, :, [2, 1, 0, 3]]).tobytes()
    if fmt == DXT5:
        return compress_dxt5(rgba, refine)
    return compress(rgba, fmt, refine)


def pack(usage, alpha, fmt, width, height, blobs):
    """A .ddt from its header values and its levels' bytes, largest first."""
    out = bytearray(MAGIC + bytes([usage, alpha, fmt, len(blobs)]) + struct.pack("<II", width, height))
    off = 16 + 8 * len(blobs)
    for b in blobs:
        out += struct.pack("<II", off, len(b))
        off += len(b)
    for b in blobs:
        out += b
    return bytes(out)


def write(rgba, fmt=DXT3, *, alpha=1, usage=0, mips=True):
    """A texture in the given format: BGRA (uncompressed), DXT1, DXT3 or DXT5."""
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


def compress_dxt5(rgba, refine=False):
    """DXT5 bytes of one level: interpolated alpha, then the colour block."""
    np = _np()
    b = _blocks(rgba)
    return np.concatenate([_alpha_encode(b[:, :, 3]), _colour_encode(b[:, :, :3], refine)],
                          axis=1).tobytes()


def write_normal_map(rgba, *, mips=False):
    """Bytes of a bump texture as the game's own (DXT5, usage 6 = low detail + bump, alpha 0)
    from an H x W x 4 array packed like them: R specular (0 = none), G the normal's Y, B its Z,
    A its X, each 128 for 0. With mips, each level's normals are unit length again."""
    np = _np()
    a = np.asarray(rgba).astype(np.uint8)
    h, w = a.shape[:2]
    levels = mip_chain(a, bump=True) if mips else [a]
    return pack(6, 0, DXT5, w, h, [compress_dxt5(lv) for lv in levels])


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


def levels_like(rgba, count):
    """The image and `count - 1` halvings of it (2 x 2 box filter, at least 1 px a side): a mip
    chain as long as an original's, whatever size its smallest level has."""
    np = _np()
    levels = [np.asarray(rgba, np.uint8)]
    cur = levels[0].astype(np.float32)
    while len(levels) < count:
        cur = halve(cur)
        levels.append(np.clip(cur + 0.5, 0, 255).astype(np.uint8))
    return levels


def write_like(original, rgba, refine=True):
    """(bytes, changed) of a texture with new pixels in the original's format: the same size,
    format (BGRA, DXT1, DXT3, DXT5), alpha type, usage bits and number of mip levels.

    Pixels equal to the original's decoded top level give the original's bytes back (changed 0).
    For a one-level DXT texture only the 4 x 4 blocks whose pixels changed are encoded again (the
    refined encoder); every other block keeps the original's bytes (changed: the blocks encoded).
    Otherwise every level is written again from the new pixels (changed -1)."""
    np = _np()
    hd = read_header(original)
    a = np.asarray(rgba)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise DdtError("expected an H x W x 3 or 4 array")
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, a.dtype)], axis=2)
    a = a.astype(np.uint8)
    if a.shape[:2] != (hd.height, hd.width):
        raise DdtError(f"the picture is {a.shape[1]}x{a.shape[0]}, the original {hd.width}x{hd.height}")
    if hd.format not in (BGRA, DXT1, DXT3, DXT5):
        raise DdtError(f"format {FORMATS.get(hd.format, hd.format)} is not written")
    old = decode(original, 0)
    if hd.format == DXT1:
        same = (old[..., :3] == a[..., :3]).all()
    else:
        same = (old == a).all()
    if same:
        return bytes(original), 0
    count = max(1, hd.mips)
    if hd.format in (DXT1, DXT3, DXT5) and count == 1:
        fmt, blocks = level_blocks(original, 0)
        h, w = a.shape[:2]
        bh, bw = (h + 3) // 4, (w + 3) // 4
        diff = (old[..., :3] != a[..., :3]).any(-1) if fmt == DXT1 else (old != a).any(-1)
        pad = np.zeros((bh * 4, bw * 4), bool)
        pad[:h, :w] = diff
        changed = pad.reshape(bh, 4, bw, 4).any(axis=(1, 3)).reshape(-1)
        new_blocks = np.frombuffer(encode_level(a, fmt, refine=refine), np.uint8).reshape(blocks.shape)
        out_blocks = np.where(changed[:, None], new_blocks, blocks)
        off = hd.levels[0][0]
        body = bytearray(original)
        body[off:off + out_blocks.size] = out_blocks.tobytes()
        return bytes(body), int(changed.sum())
    blobs = [encode_level(lv, hd.format, refine=refine) for lv in levels_like(a, count)]
    return pack(hd.usage, hd.alpha, hd.format, hd.width, hd.height, blobs), -1
