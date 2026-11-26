# SPDX-License-Identifier: GPL-3.0-or-later
"""A minimal Photoshop document (.psd) writer and reader: version 1, RGB, 8 bits a channel. Pure
Python and numpy.

    doc = [Layer("Original", rgba, visible=False, locked=True),
           Group("Paint", [Layer("Minimap frame", crop, left=0, top=746), ...]),
           Group("Guides", [...], visible=False)]          # bottom to top, as Photoshop lists them reversed
    data = write(width, height, doc, guides=[(746, "h"), (684, "v")])
    f = read(data)          # f.width, f.height, f.items (the same tree), f.layers(), f.guides, f.composite

What it writes (Adobe's "Photoshop File Formats Specification"):

- the header (8BPS, version 1, 4 channels, RGB);
- image resources: the guides (resource 1032, positions in 1/32 px) when given;
- each layer: its rectangle (the bounding box of its visible pixels), the four channels
  (transparency -1, red, green, blue) compressed with RLE (PackBits), blend mode normal, opacity,
  visible or hidden, the transparency/position lock (`lspf`) when locked, and its name both as a
  Pascal string (ASCII) and as Unicode (`luni`);
- groups as Photoshop stores them: a divider layer ("</Layer group>", `lsct` 3), the
  group's layers, then the folder layer (`lsct` 1 open or 2 closed) carrying the group's name and
  visibility;
- the merged image (RGBA, RLE): the visible layers composed with the normal blend mode, so a
  viewer that reads only the merged image (Pillow, thumbnails) shows the document as opened. As
  Photoshop stores it, its colour is matted against white where it is transparent; `read` takes
  the matte off again (Pillow does not: its colours are the matted ones).

The reader takes what this writer writes and what Photoshop saves for RGB 8-bit documents: raw or
RLE channels, groups (`lsct`/`lsdk`), Unicode names, layer masks skipped, blend modes and layer
effects reported (not drawn: `compose` draws the normal mode only and lists what it could not draw).
"""
import struct

SIGNATURE = b"8BPS"
DIVIDER_NAME = "</Layer group>"


class PsdError(ValueError):
    pass


class Layer:
    """A pixel layer. rgba: H x W x 4 uint8 (straight alpha) placed with its top left corner at
    (left, top) of the canvas."""

    def __init__(self, name, rgba, left=0, top=0, visible=True, opacity=255, locked=False, blend="norm"):
        import numpy as np
        self.name = name
        self.rgba = np.ascontiguousarray(np.asarray(rgba, np.uint8))
        if self.rgba.ndim != 3 or self.rgba.shape[2] != 4:
            raise PsdError(f"{name}: a layer is H x W x 4")
        self.left, self.top = int(left), int(top)
        self.visible, self.opacity, self.locked, self.blend = visible, int(opacity), locked, blend
        self.effects = False            # read: the layer has layer effects (not drawn)
        self.clipping = 0
        self.mask = None                # read: (left, top, H x W uint8) of a layer mask, applied by compose

    @property
    def is_group(self):
        return False


class Group:
    """A group (a folder of layers), its children bottom to top."""

    def __init__(self, name, children=(), visible=True, opacity=255, open=True):
        self.name, self.children = name, list(children)
        self.visible, self.opacity, self.open = visible, int(opacity), open
        self.blend = "pass"

    @property
    def is_group(self):
        return True


# --------------------------------------------------------------------------------------------------
# PackBits

def packbits(row):
    """PackBits (the RLE of PSD and TIFF) of one row of bytes."""
    data = bytes(row)
    n = len(data)
    out = bytearray()
    i = 0
    while i < n:
        j = i + 1
        while j < n and j - i < 128 and data[j] == data[i]:
            j += 1
        if j - i >= 3 or (j - i == 2 and j == n):
            out.append(257 - (j - i) if j - i > 1 else 0)
            out.append(data[i])
            i = j
            continue
        start = i                       # a literal run, until a run of 3 begins or 128 bytes
        while i < n and i - start < 128:
            if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                break
            i += 1
        out.append(i - start - 1)
        out += data[start:i]
    return bytes(out)


def unpackbits(data, length):
    """The row PackBits encoded in `data` (bytes), `length` bytes long."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n and len(out) < length:
        h = data[i]
        i += 1
        if h < 128:
            out += data[i:i + h + 1]
            i += h + 1
        elif h > 128:
            out += bytes([data[i]]) * (257 - h)
            i += 1
    if len(out) < length:
        raise PsdError("an RLE row is short")
    return bytes(out[:length])


def _rle_channels(planes):
    """(compression 1, the byte counts of every row of every plane, then the rows) for planes of
    the same height: the merged image's layout. Planes: list of H x W uint8 arrays."""
    counts, body = [], bytearray()
    for p in planes:
        for row in p:
            packed = packbits(row.tobytes())
            counts.append(len(packed))
            body += packed
    return counts, bytes(body)


def _channel_data(plane):
    """One layer channel: compression, then the data (RLE; raw when RLE would be larger)."""
    h = plane.shape[0]
    if plane.size == 0:
        return struct.pack(">H", 0)
    counts, body = _rle_channels([plane])
    rle = struct.pack(">H", 1) + struct.pack(f">{h}H", *counts) + body
    raw = struct.pack(">H", 0) + plane.tobytes()
    return rle if len(rle) < len(raw) else raw


# --------------------------------------------------------------------------------------------------
# Writing

def _pascal(name, pad):
    raw = name.encode("ascii", "replace")[:255]
    s = bytes([len(raw)]) + raw
    while len(s) % pad:
        s += b"\0"
    return s


def _block(key, data):
    """An additional layer information block, its length even (padded)."""
    if len(data) % 2:
        data += b"\0"
    return b"8BIM" + key + struct.pack(">I", len(data)) + data


def _luni(name):
    enc = name.encode("utf-16-be")
    return _block(b"luni", struct.pack(">I", len(enc) // 2) + enc)


def _flatten(items):
    """[(record kind, object)] bottom to top: ("layer", Layer), ("divider", Group), ("folder", Group)."""
    out = []
    for it in items:
        if it.is_group:
            out.append(("divider", it))
            out += _flatten(it.children)
            out.append(("folder", it))
        else:
            out.append(("layer", it))
    return out


def _trimmed(layer):
    """(left, top, rgba) of a layer cut to the bounding box of its non-transparent pixels (an empty
    layer: 0 x 0)."""
    import numpy as np
    a = layer.rgba[:, :, 3]
    ys, xs = np.nonzero(a)
    if len(ys) == 0:
        return layer.left, layer.top, layer.rgba[:0, :0]
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return layer.left + int(x0), layer.top + int(y0), layer.rgba[y0:y1, x0:x1]


def write(width, height, items, guides=(), composite=None):
    """The bytes of a PSD of the given size with the items (Layers and Groups, bottom to top).
    guides: [(position in px, "v" or "h")]; composite: H x W x 4 uint8 merged image (by default
    the visible layers composed)."""
    import numpy as np
    out = bytearray(SIGNATURE + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 4, height, width, 8, 3))
    out += struct.pack(">I", 0)                                  # colour mode data: none for RGB
    res = bytearray()
    if guides:
        g = struct.pack(">I", 1) + struct.pack(">II", 576, 576) + struct.pack(">I", len(guides))
        for pos, direction in guides:
            g += struct.pack(">iB", int(round(pos * 32)), 0 if direction == "v" else 1)
        res += b"8BIM" + struct.pack(">H", 1032) + b"\0\0" + struct.pack(">I", len(g)) + g
        if len(g) % 2:
            res += b"\0"
    out += struct.pack(">I", len(res)) + res

    records, channels = bytearray(), bytearray()
    flat = _flatten(items)
    for kind, obj in flat:
        if kind == "layer":
            left, top, px = _trimmed(obj)
            h, w = px.shape[:2]
            datas = [_channel_data(np.ascontiguousarray(px[:, :, c])) for c in (3, 0, 1, 2)]
            ids = (-1, 0, 1, 2)
            name, blend = obj.name, obj.blend.encode("ascii")[:4].ljust(4)
            flags = (0x02 if not obj.visible else 0)
            extra_blocks = _luni(name)
            if obj.locked:
                extra_blocks += _block(b"lspf", struct.pack(">I", 0x80000000))
            opacity = obj.opacity
        else:
            left = top = h = w = 0
            datas = [struct.pack(">H", 0)] * 4
            ids = (-1, 0, 1, 2)
            if kind == "divider":
                name, blend = DIVIDER_NAME, b"norm"
                flags = 0x08 | 0x10
                extra_blocks = _luni(name) + _block(b"lsct", struct.pack(">I", 3))
                opacity = 255
            else:
                name, blend = obj.name, b"pass"
                flags = (0x02 if not obj.visible else 0) | 0x08 | 0x10
                extra_blocks = _luni(name) + _block(b"lsct", struct.pack(">I", 1 if obj.open else 2) + b"8BIMpass")
                opacity = obj.opacity
        rec = struct.pack(">iiiiH", top, left, top + h, left + w, len(ids))
        for cid, d in zip(ids, datas):
            rec += struct.pack(">hI", cid, len(d))
        rec += b"8BIM" + blend + struct.pack(">BBBB", opacity, 0, flags, 0)
        ranges = bytes([0, 0, 255, 255]) * 10           # blending ranges: everything blends (as Photoshop writes)
        extra = struct.pack(">I", 0) + struct.pack(">I", len(ranges)) + ranges + _pascal(name, 4) + extra_blocks
        rec += struct.pack(">I", len(extra)) + extra
        records += rec
        for d in datas:
            channels += d
    layer_info = struct.pack(">h", -len(flat)) + records + channels
    if len(layer_info) % 2:
        layer_info += b"\0"
    lmi = struct.pack(">I", len(layer_info)) + layer_info + struct.pack(">I", 0)
    out += struct.pack(">I", len(lmi)) + lmi

    if composite is None:
        composite = compose(items, width, height)[0]
    comp = np.asarray(composite, np.uint8)
    if comp.shape != (height, width, 4):
        raise PsdError("the composite is not H x W x 4 of the document")
    counts, body = _rle_channels([np.ascontiguousarray(c) for c in np.moveaxis(matte(comp), 2, 0)])
    out += struct.pack(">H", 1) + struct.pack(f">{len(counts)}H", *counts) + body
    return bytes(out)


# --------------------------------------------------------------------------------------------------
# Composing

def matte(rgba):
    """The merged image as a PSD stores it: colour matted against white where it is transparent
    (colour * alpha + white * (1 - alpha)), the alpha as is."""
    import numpy as np
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)
    return np.concatenate([np.clip(rgb + 0.5, 0, 255).astype(np.uint8), rgba[:, :, 3:4]], axis=2)


def unmatte(stored):
    """The merged image's straight colour back from its white matte (0 where fully transparent)."""
    import numpy as np
    a = stored[:, :, 3:4].astype(np.float32) / 255.0
    c = stored[:, :, :3].astype(np.float32) / 255.0
    rgb = np.where(a > 0, (c - (1 - a)) / np.maximum(a, 1e-6), 0)
    return np.concatenate([np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8), stored[:, :, 3:4]], axis=2)


def compose(items, width, height, skip=None):
    """(H x W x 4 uint8, [notes]) of the visible layers composed bottom to top with the normal
    blend mode, layer and group opacity, and layer masks. skip(item, path) -> True leaves an item
    (and a group's children) out; path is the names of the groups above it. A notes entry names
    each layer drawn as normal although it is not (another blend mode, layer effects, clipping)."""
    import numpy as np
    acc = np.zeros((height, width, 4), np.float32)              # premultiplied RGBA, 0..1
    notes = []

    def draw(item, path, k):
        if skip and skip(item, path):
            return
        if not item.visible:
            return
        k = k * item.opacity / 255.0
        if item.is_group:
            for c in item.children:
                draw(c, path + [item.name], k)
            return
        if item.blend not in ("norm", "pass"):
            notes.append(f"{'/'.join(path + [item.name])}: blend mode {item.blend!r} drawn as normal")
        if item.effects:
            notes.append(f"{'/'.join(path + [item.name])}: layer effects not drawn")
        if item.clipping:
            notes.append(f"{'/'.join(path + [item.name])}: clipping mask not applied")
        h, w = item.rgba.shape[:2]
        x0, y0 = max(0, item.left), max(0, item.top)
        x1, y1 = min(width, item.left + w), min(height, item.top + h)
        if x1 <= x0 or y1 <= y0:
            return
        src = item.rgba[y0 - item.top:y1 - item.top, x0 - item.left:x1 - item.left].astype(np.float32) / 255.0
        a = src[:, :, 3:4] * k
        if item.mask is not None:
            ml, mt, mk = item.mask
            m = np.zeros((y1 - y0, x1 - x0), np.float32)
            mx0, my0 = max(x0, ml), max(y0, mt)
            mx1, my1 = min(x1, ml + mk.shape[1]), min(y1, mt + mk.shape[0])
            if mx1 > mx0 and my1 > my0:
                m[my0 - y0:my1 - y0, mx0 - x0:mx1 - x0] = mk[my0 - mt:my1 - mt, mx0 - ml:mx1 - ml] / 255.0
            a = a * m[:, :, None]
        dst = acc[y0:y1, x0:x1]
        dst[:, :, :3] = src[:, :, :3] * a + dst[:, :, :3] * (1 - a)
        dst[:, :, 3:4] = a + dst[:, :, 3:4] * (1 - a)

    for it in items:
        draw(it, [], 1.0)
    alpha = acc[:, :, 3:4]
    rgb = np.where(alpha > 0, acc[:, :, :3] / np.maximum(alpha, 1e-12), 0)
    out = np.concatenate([rgb, alpha], axis=2)
    return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8), notes


# --------------------------------------------------------------------------------------------------
# Reading

class PsdFile:
    def __init__(self):
        self.width = self.height = 0
        self.channels = 0
        self.items = []             # the tree, bottom to top
        self.guides = []            # [(position in px, "v" | "h")]
        self.composite = None       # H x W x 4 uint8, or None when not read
        self.resources = {}

    def layers(self):
        """[(path of group names, Layer)] of every pixel layer, bottom to top."""
        out = []

        def walk(items, path):
            for it in items:
                if it.is_group:
                    walk(it.children, path + [it.name])
                else:
                    out.append((path, it))
        walk(self.items, [])
        return out

    def find(self, name):
        """The first item (layer or group) of that name, depth first, or None."""
        def walk(items):
            for it in items:
                if it.name == name:
                    return it
                if it.is_group:
                    hit = walk(it.children)
                    if hit is not None:
                        return hit
            return None
        return walk(self.items)


class _Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def take(self, n):
        if self.i + n > len(self.d):
            raise PsdError("the file is short")
        b = self.d[self.i:self.i + n]
        self.i += n
        return b

    def u(self, fmt):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size))


def _read_channel(r, length, h, w):
    import numpy as np
    start = r.i
    comp = r.u(">H")[0]
    if h == 0 or w == 0:
        r.i = start + length
        return np.zeros((h, w), np.uint8)
    if comp == 0:
        plane = np.frombuffer(r.take(h * w), np.uint8).reshape(h, w)
    elif comp == 1:
        counts = r.u(f">{h}H")
        rows = [unpackbits(r.take(c), w) for c in counts]
        plane = np.frombuffer(b"".join(rows), np.uint8).reshape(h, w)
    else:
        raise PsdError(f"channel compression {comp} (ZIP) is not read: save without it")
    r.i = start + length
    return plane


def read(data, composite=True):
    """A PsdFile of a PSD's bytes (RGB, 8 bits, version 1)."""
    import numpy as np
    r = _Reader(data)
    if r.take(4) != SIGNATURE:
        raise PsdError("not a Photoshop document (no 8BPS)")
    version = r.u(">H")[0]
    if version != 1:
        raise PsdError("a large document (PSB) is not read")
    r.take(6)
    channels, height, width, depth, mode = r.u(">HIIHH")
    if depth != 8 or mode != 3:
        raise PsdError(f"only RGB 8-bit documents are read (this one: depth {depth}, mode {mode})")
    f = PsdFile()
    f.width, f.height, f.channels = width, height, channels
    r.take(r.u(">I")[0])                                        # colour mode data
    end = r.u(">I")[0] + r.i
    while r.i < end:
        if r.take(4) != b"8BIM":
            raise PsdError("a bad image resource")
        rid = r.u(">H")[0]
        n = r.u(">B")[0]
        r.take(n + ((n + 1) % 2))
        size = r.u(">I")[0]
        body = r.take(size)
        if size % 2:
            r.take(1)
        f.resources[rid] = body
        if rid == 1032 and len(body) >= 16:
            count = struct.unpack_from(">I", body, 12)[0]
            for k in range(count):
                pos, direction = struct.unpack_from(">iB", body, 16 + 5 * k)
                f.guides.append((pos / 32.0, "v" if direction == 0 else "h"))
    r.i = end
    lmi_len = r.u(">I")[0]
    lmi_end = r.i + lmi_len
    flat = []
    if lmi_len:
        li_len = r.u(">I")[0]
        li_end = r.i + li_len
        if li_len:
            count = abs(r.u(">h")[0])
            recs = []
            for _ in range(count):
                top, left, bottom, right, nch = r.u(">iiiiH")
                chans = [r.u(">hI") for _ in range(nch)]
                if r.take(4) != b"8BIM":
                    raise PsdError("a bad layer record")
                blend = r.take(4).decode("ascii", "replace")
                opacity, clipping, flags, _filler = r.u(">BBBB")
                extra_len = r.u(">I")[0]
                extra_end = r.i + extra_len
                mask_len = r.u(">I")[0]
                mask = None
                if mask_len >= 20:
                    mt, ml, mb, mr = r.u(">iiii")
                    default = r.u(">B")[0]
                    mflags = r.u(">B")[0]
                    mask = (mt, ml, mb, mr, default, mflags)
                    r.i += mask_len - 18
                else:
                    r.i += mask_len
                ranges_len = r.u(">I")[0]                        # blending ranges
                r.i += ranges_len
                n = r.u(">B")[0]
                name = r.take(n).decode("latin-1")
                r.i += (4 - (n + 1) % 4) % 4
                info = {}
                while r.i + 12 <= extra_end:
                    sig = r.take(4)
                    if sig not in (b"8BIM", b"8B64"):
                        break
                    key = r.take(4)
                    size = r.u(">I")[0]
                    info[key] = r.take(size)
                r.i = extra_end
                if b"luni" in info:
                    k = struct.unpack_from(">I", info[b"luni"], 0)[0]
                    name = info[b"luni"][4:4 + 2 * k].decode("utf-16-be")
                recs.append({"rect": (top, left, bottom, right), "chans": chans, "blend": blend, "opacity": opacity,
                             "clipping": clipping, "flags": flags, "name": name, "info": info, "mask": mask})
            for rec in recs:
                top, left, bottom, right = rec["rect"]
                h, w = max(0, bottom - top), max(0, right - left)
                planes = {}
                for cid, length in rec["chans"]:
                    if cid == -2 and rec["mask"] is not None:
                        mt, ml, mb, mr = rec["mask"][:4]
                        planes[cid] = _read_channel(r, length, max(0, mb - mt), max(0, mr - ml))
                    elif cid in (-1, 0, 1, 2):
                        planes[cid] = _read_channel(r, length, h, w)
                    else:
                        r.i += length
                rec["planes"] = planes
                rec["size"] = (h, w)
            r.i = li_end
            for rec in recs:
                info = rec["info"]
                kind = None
                for key in (b"lsct", b"lsdk"):
                    if key in info and len(info[key]) >= 4:
                        kind = struct.unpack_from(">I", info[key], 0)[0]
                visible = not (rec["flags"] & 0x02)
                if kind == 3:
                    flat.append(("divider", None))
                elif kind in (1, 2):
                    g = Group(rec["name"], visible=visible, opacity=rec["opacity"], open=kind == 1)
                    flat.append(("folder", g))
                else:
                    h, w = rec["size"]
                    p = rec["planes"]
                    alpha = p.get(-1, np.full((h, w), 255, np.uint8))
                    zero = np.zeros((h, w), np.uint8)
                    rgba = np.stack([p.get(0, zero), p.get(1, zero), p.get(2, zero), alpha], axis=2)
                    lay = Layer(rec["name"], rgba, rec["rect"][1], rec["rect"][0], visible, rec["opacity"],
                                locked=b"lspf" in info and struct.unpack_from(">I", info[b"lspf"], 0)[0] != 0,
                                blend=rec["blend"])
                    lay.effects = any(k in info for k in (b"lrFX", b"lfx2", b"lmfx"))
                    lay.clipping = rec["clipping"]
                    if rec["mask"] is not None and -2 in p and not (rec["mask"][5] & 0x02):
                        mt, ml = rec["mask"][0], rec["mask"][1]
                        lay.mask = (ml, mt, p[-2])
                    flat.append(("layer", lay))
    r.i = lmi_end
    # the tree: a divider opens a group that its folder record closes
    stack = [[]]
    for kind, obj in flat:
        if kind == "divider":
            stack.append([])
        elif kind == "folder":
            children = stack.pop() if len(stack) > 1 else []
            obj.children = children
            stack[-1].append(obj)
        else:
            stack[-1].append(obj)
    while len(stack) > 1:
        children = stack.pop()
        stack[-1].extend(children)
    f.items = stack[0]
    if composite and r.i + 2 <= len(data):
        comp = r.u(">H")[0]
        planes = []
        if comp == 1:
            counts = r.u(f">{channels * height}H")
            k = 0
            for _c in range(channels):
                rows = []
                for _y in range(height):
                    rows.append(unpackbits(r.take(counts[k]), width))
                    k += 1
                planes.append(np.frombuffer(b"".join(rows), np.uint8).reshape(height, width))
        elif comp == 0:
            for _c in range(channels):
                planes.append(np.frombuffer(r.take(width * height), np.uint8).reshape(height, width))
        else:
            planes = None
        if planes:
            if len(planes) > 3:
                f.composite = unmatte(np.stack(planes[:4], axis=2))
            else:
                f.composite = np.stack(planes[:3] + [np.full((height, width), 255, np.uint8)], axis=2)
    return f
