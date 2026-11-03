# SPDX-License-Identifier: GPL-3.0-or-later
"""Granny 2 (.gr2) files: the container, the data tree, and a writer for static models.

Standard library only. Measured on the game's files (Granny 2.5, file versions 6 and 7):

    0x00  magic, 16 bytes
    0x10  u32  end of the section array (absolute)
    0x14  u32  header format (0)
    0x18  8 bytes reserved
    0x20  file header: version, total size, CRC, section array offset (relative to 0x20),
          section count, root type (section, offset), root object (section, offset), type tag,
          4 extra tags; version 7 adds the string table CRC and 3 reserved words.
          The CRC is zlib's CRC-32 of every byte from 0x20 + header size to the end.
    then  44-byte section records: compression (0 none, 1 Oodle0, 2 Oodle1), data offset, data
          size, expanded size, alignment, first 16-bit and first 8-bit stops, relocation table
          offset and count, marshalling table offset and count.

A relocation is (offset in its section, target section, target offset), 12 bytes. Pointers are
32-bit and are known ONLY through relocations: a slot with no relocation is null.

The data tree is self-describing: the root type is an array of 32-byte member records (kind,
name, referenced type, array width, 3 extra words, 1 ignored word), ended by kind 0.

Compressed sections need the Granny runtime: `Compressed` is raised and the survey hands such a
file to an external tool that rewrites it uncompressed.
"""
import hashlib
import struct
import zlib

MAGIC = bytes.fromhex("b867b0caf86db10f84728c7e5e19001e")
HEADER_SIZE = {6: 0x38, 7: 0x48}
SECTION_RECORD = 44
RELOCATION = 12
MEMBER_RECORD = 32

# Member kinds (granny_member_type in Granny 2.5).
END, INLINE, REFERENCE, REF_TO_ARRAY, ARRAY_OF_REFS = 0, 1, 2, 3, 4
VARIANT_REF, SWITCHABLE, REF_TO_VARIANT_ARRAY, STRING, TRANSFORM = 5, 6, 7, 8, 9
REAL32, INT8, UINT8, BINORMAL_INT8, NORMAL_UINT8 = 10, 11, 12, 13, 14
INT16, UINT16, BINORMAL_INT16, NORMAL_UINT16, INT32, UINT32 = 15, 16, 17, 18, 19, 20

KIND_NAMES = {
    END: "End", INLINE: "Inline", REFERENCE: "Reference", REF_TO_ARRAY: "ReferenceToArray",
    ARRAY_OF_REFS: "ArrayOfReferences", VARIANT_REF: "VariantReference",
    SWITCHABLE: "SwitchableType", REF_TO_VARIANT_ARRAY: "ReferenceToVariantArray",
    STRING: "String", TRANSFORM: "Transform", REAL32: "Real32", INT8: "Int8", UINT8: "UInt8",
    BINORMAL_INT8: "BinormalInt8", NORMAL_UINT8: "NormalUInt8", INT16: "Int16",
    UINT16: "UInt16", BINORMAL_INT16: "BinormalInt16", NORMAL_UINT16: "NormalUInt16",
    INT32: "Int32", UINT32: "UInt32",
}
# Bytes of one value of each scalar kind; the transform is 68 bytes (flags, position, orientation,
# scale/shear 3 x 3).
SCALAR_SIZE = {REAL32: 4, INT8: 1, UINT8: 1, BINORMAL_INT8: 1, NORMAL_UINT8: 1, INT16: 2,
               UINT16: 2, BINORMAL_INT16: 2, NORMAL_UINT16: 2, INT32: 4, UINT32: 4}
SCALAR_FMT = {REAL32: "f", INT8: "b", UINT8: "B", BINORMAL_INT8: "b", NORMAL_UINT8: "B",
              INT16: "h", UINT16: "H", BINORMAL_INT16: "h", NORMAL_UINT16: "H", INT32: "i",
              UINT32: "I"}
POINTER_SIZE = {REFERENCE: 4, REF_TO_ARRAY: 8, ARRAY_OF_REFS: 8, VARIANT_REF: 8,
                REF_TO_VARIANT_ARRAY: 12, STRING: 4}
TRANSFORM_SIZE = 68


class Gr2Error(ValueError):
    pass


class Compressed(Gr2Error):
    """The file has compressed sections; `sections` lists their indices."""

    def __init__(self, sections):
        super().__init__(f"sections {sections} are compressed (needs the Granny runtime)")
        self.sections = sections


# --------------------------------------------------------------------------------------------------
# Container

class Section:
    FIELDS = ("compression", "data_offset", "data_size", "expanded_size", "alignment", "first16",
              "first8", "reloc_offset", "reloc_count", "marshal_offset", "marshal_count")

    def __init__(self, *values):
        for k, v in zip(self.FIELDS, values):
            setattr(self, k, v)

    def pack(self):
        return struct.pack("<11I", *(getattr(self, k) for k in self.FIELDS))

    def __repr__(self):
        return "Section(" + ", ".join(f"{k}={getattr(self, k)}" for k in self.FIELDS) + ")"


class Container:
    """The parsed file: header facts, section bytes and the relocation map."""

    def __init__(self):
        self.version = 0
        self.type_tag = 0
        self.extra_tags = (0, 0, 0, 0)
        self.sections = []
        self.data = []          # bytes of each section
        self.relocs = {}        # (section, offset) -> (section, offset)
        self.root_type = None   # (section, offset)
        self.root_obj = None

    @property
    def header_size(self):
        return HEADER_SIZE[self.version]

    def ptr(self, at):
        return self.relocs.get(at)

    def raw(self, at, n):
        s, o = at
        b = self.data[s][o:o + n]
        if len(b) != n:
            raise Gr2Error(f"read of {n} bytes at {at} runs past its section")
        return b

    def unpack(self, fmt, at):
        return struct.unpack_from("<" + fmt, self.data[at[0]], at[1])

    def u32(self, at):
        return struct.unpack_from("<I", self.data[at[0]], at[1])[0]

    def i32(self, at):
        return struct.unpack_from("<i", self.data[at[0]], at[1])[0]

    def cstr(self, at):
        d = self.data[at[0]]
        end = d.find(b"\0", at[1])
        if end < 0:
            raise Gr2Error(f"string at {at} has no terminator")
        return d[at[1]:end].decode("cp1252", "replace")


def file_crc(data):
    version = struct.unpack_from("<I", data, 0x20)[0]
    return zlib.crc32(data[0x20 + HEADER_SIZE.get(version, 0x38):]) & 0xFFFFFFFF


def crc_ok(data):
    return struct.unpack_from("<I", data, 0x28)[0] == file_crc(data)


def header_facts(head):
    """Facts from the first bytes of a file (no section data needed): version, sections, the
    compression of each. `head` should hold at least 0x20 + 0x48 + 8 * 44 bytes."""
    if head[:16] != MAGIC:
        return {"magic": head[:16].hex()}
    version, size, crc, sec_off, n = struct.unpack_from("<5I", head, 0x20)
    info = {"version": version, "size": size, "sections": n,
            "type_tag": "0x%08x" % struct.unpack_from("<I", head, 0x20 + 0x24)[0]}
    comp = []
    for i in range(n):
        at = 0x20 + sec_off + i * SECTION_RECORD
        if at + 4 > len(head):
            break
        comp.append(struct.unpack_from("<I", head, at)[0])
    info["compression"] = comp
    info["raw"] = len(comp) == n and all(c == 0 for c in comp)
    return info


def read_container(data):
    data = bytes(data)
    if data[:16] != MAGIC:
        raise Gr2Error("not a Granny file (bad magic)")
    c = Container()
    c.version = struct.unpack_from("<I", data, 0x20)[0]
    if c.version not in HEADER_SIZE:
        raise Gr2Error(f"unsupported Granny file version {c.version}")
    (_, size, _crc, sec_off, n, rts, rto, ros, roo, tag) = struct.unpack_from("<10I", data, 0x20)
    c.extra_tags = struct.unpack_from("<4I", data, 0x20 + 40)
    c.type_tag = tag
    c.root_type, c.root_obj = (rts, rto), (ros, roo)
    compressed = []
    for i in range(n):
        sec = Section(*struct.unpack_from("<11I", data, 0x20 + sec_off + i * SECTION_RECORD))
        c.sections.append(sec)
        if sec.compression != 0 and sec.data_size:
            compressed.append(i)
    if compressed:
        raise Compressed(compressed)
    for sec in c.sections:
        b = data[sec.data_offset:sec.data_offset + sec.data_size]
        if len(b) < sec.expanded_size:
            b += bytes(sec.expanded_size - len(b))
        c.data.append(b)
    for i, sec in enumerate(c.sections):
        for k in range(sec.reloc_count):
            off, ts, to = struct.unpack_from("<3I", data, sec.reloc_offset + k * RELOCATION)
            c.relocs[(i, off)] = (ts, to)
    return c


# --------------------------------------------------------------------------------------------------
# Types

class Member:
    __slots__ = ("kind", "name", "ref", "width", "extra", "size", "offset")

    def __repr__(self):
        return f"Member({KIND_NAMES.get(self.kind, self.kind)} {self.name!r} w={self.width})"


class TypeDef:
    __slots__ = ("key", "members", "size", "flat")

    def member(self, name):
        return next((m for m in self.members if m.name == name), None)

    def __repr__(self):
        return f"TypeDef({self.key}, {[m.name for m in self.members]})"


class Blob:
    """An array of pointer-free elements, kept as bytes."""

    def __init__(self, count, typedef, raw):
        self.count, self.type, self.raw = count, typedef, raw

    @property
    def stride(self):
        return self.type.size if self.type else 0

    def layout(self):
        """'Name:f3,...' for an array of scalar members, for reports."""
        out = []
        for m in self.type.members:
            code = {REAL32: "f", INT8: "i8", UINT8: "u8", BINORMAL_INT8: "bi8",
                    NORMAL_UINT8: "nu8", INT16: "i16", UINT16: "u16", BINORMAL_INT16: "bi16",
                    NORMAL_UINT16: "nu16", INT32: "i32", UINT32: "u32"}.get(m.kind, str(m.kind))
            out.append(f"{m.name}:{code}{max(1, m.width)}")
        return ",".join(out)

    def column(self, name):
        """Values of one scalar member for every element, as tuples."""
        m = self.type.member(name)
        if m is None or m.kind not in SCALAR_FMT:
            return None
        fmt = "<" + SCALAR_FMT[m.kind] * max(1, m.width)
        return [struct.unpack_from(fmt, self.raw, i * self.stride + m.offset)
                for i in range(self.count)]


class Doc:
    """A loaded file: the container plus typed access to its data tree."""

    def __init__(self, container):
        self.c = container
        self._types = {}

    # -- types --
    def typedef(self, key):
        if key is None:
            return None
        t = self._types.get(key)
        if t is not None:
            return t
        t = TypeDef()
        t.key, t.members, t.size, t.flat = key, [], 0, None
        self._types[key] = t        # registered first: a type may reach itself
        s, o = key
        offset = 0
        for i in range(4096):
            at = (s, o + i * MEMBER_RECORD)
            kind, _n, _r, width, e0, e1, e2, _ign = self.c.unpack("8I", at)
            if kind == END:
                break
            m = Member()
            m.kind = kind
            name_at = self.c.ptr((s, at[1] + 4))
            m.name = self.c.cstr(name_at) if name_at else ""
            m.ref = self.c.ptr((s, at[1] + 8))
            m.width = width
            m.extra = (e0, e1, e2)
            m.offset = offset
            m.size = None
            t.members.append(m)
        else:
            raise Gr2Error(f"type at {key} has no end member")
        for m in t.members:
            m.offset = offset
            m.size = self.member_size(m)
            offset += m.size
        t.size = offset
        return t

    def member_size(self, m):
        w = max(1, m.width)
        if m.kind == INLINE:
            return self.typedef(m.ref).size * w if m.ref else 0
        if m.kind in POINTER_SIZE:
            return POINTER_SIZE[m.kind]
        if m.kind == TRANSFORM:
            return TRANSFORM_SIZE * w
        if m.kind in SCALAR_SIZE:
            return SCALAR_SIZE[m.kind] * w
        raise Gr2Error(f"member {m.name!r} has kind {m.kind}, which this reader does not know")

    def is_flat(self, t):
        if t.flat is None:
            t.flat = False
            t.flat = all(m.kind in SCALAR_SIZE or m.kind == TRANSFORM
                         or (m.kind == INLINE and m.ref and self.is_flat(self.typedef(m.ref)))
                         for m in t.members)
        return t.flat

    # -- values --
    def root(self):
        return Obj(self, self.typedef(self.c.root_type), self.c.root_obj)

    def value(self, t, at, m):
        """The Python value of member m of the object of type t at `at`."""
        c = self.c
        a = (at[0], at[1] + m.offset)
        if m.kind == INLINE:
            sub = self.typedef(m.ref)
            if max(1, m.width) == 1:
                return Obj(self, sub, a)
            return [Obj(self, sub, (a[0], a[1] + k * sub.size)) for k in range(m.width)]
        if m.kind == REFERENCE:
            p = c.ptr(a)
            return Obj(self, self.typedef(m.ref), p) if p else None
        if m.kind == STRING:
            p = c.ptr(a)
            return c.cstr(p) if p else None
        if m.kind == VARIANT_REF:
            tp, p = c.ptr(a), c.ptr((a[0], a[1] + 4))
            return Obj(self, self.typedef(tp), p) if p and tp else None
        if m.kind == REF_TO_ARRAY:
            return self.array(self.typedef(m.ref), c.i32(a), c.ptr((a[0], a[1] + 4)))
        if m.kind == REF_TO_VARIANT_ARRAY:
            tp = c.ptr(a)
            return self.array(self.typedef(tp), c.i32((a[0], a[1] + 4)),
                              c.ptr((a[0], a[1] + 8)))
        if m.kind == ARRAY_OF_REFS:
            n, p = c.i32(a), c.ptr((a[0], a[1] + 4))
            if n <= 0 or not p:
                return []
            t2 = self.typedef(m.ref)
            out = []
            for i in range(n):
                q = c.ptr((p[0], p[1] + 4 * i))
                out.append(Obj(self, t2, q) if q else None)
            return out
        if m.kind == TRANSFORM:
            v = c.unpack("I16f", a)
            return {"flags": v[0], "position": v[1:4], "orientation": v[4:8],
                    "scale_shear": v[8:17]}
        if m.kind in SCALAR_FMT:
            v = c.unpack(SCALAR_FMT[m.kind] * max(1, m.width), a)
            return v[0] if max(1, m.width) == 1 else v
        raise Gr2Error(f"member {m.name!r}: kind {m.kind} is not readable")

    def array(self, t, n, p):
        if n <= 0 or not p or t is None:
            return []
        if self.is_flat(t):
            return Blob(n, t, self.c.raw(p, n * t.size))
        return [Obj(self, t, (p[0], p[1] + i * t.size)) for i in range(n)]

    # -- statistics --
    def stats(self):
        r = self.root()
        out = {"version": self.c.version, "type_tag": "0x%08x" % self.c.type_tag}
        art = r.get("ArtToolInfo")
        if art is not None:
            out["art_tool"] = {"name": art.get("FromArtToolName"),
                               "units_per_meter": art.get("UnitsPerMeter"),
                               "right": art.get("RightVector"), "up": art.get("UpVector"),
                               "back": art.get("BackVector")}
        exp = r.get("ExporterInfo")
        if exp is not None:
            out["exporter"] = exp.get("ExporterName")
        out["textures"] = [t.get("FromFileName") for t in (r.get("Textures") or []) if t]
        mats = []
        for mt in r.get("Materials") or []:
            if mt is None:
                continue
            ed = mt.get("ExtendedData")
            effect = None
            if ed is not None:
                effect = ed.get("ESeffectName") or ed.get("ESEffectName")
            mats.append({"name": mt.get("Name"), "effect": effect})
        out["materials"] = mats
        bones = []
        for sk in r.get("Skeletons") or []:
            for b in (sk.get("Bones") if sk else None) or []:
                bones.append({"name": b.get("Name"), "parent": b.get("ParentIndex"),
                              "position": b.get("Transform")["position"]})
        out["bones"] = bones
        tris = verts = 0
        layouts, index_bits = [], set()
        lo, hi = [float("inf")] * 3, [float("-inf")] * 3
        for vd in r.get("VertexDatas") or []:
            vs = vd.get("Vertices") if vd else None
            if isinstance(vs, Blob):
                verts += vs.count
                layouts.append(f"{vs.layout()} ({vs.stride} B)")
                for p in vs.column("Position") or []:
                    for k in range(3):
                        lo[k] = min(lo[k], p[k])
                        hi[k] = max(hi[k], p[k])
        for tt in r.get("TriTopologies") or []:
            if tt is None:
                continue
            i32, i16 = tt.get("Indices"), tt.get("Indices16")
            n32 = i32.count if isinstance(i32, Blob) else 0
            n16 = i16.count if isinstance(i16, Blob) else 0
            if n32:
                index_bits.add(32)
            if n16:
                index_bits.add(16)
            tris += (n32 + n16) // 3
        out["tris"], out["verts"] = tris, verts
        out["vertex_layouts"] = layouts
        out["index_bits"] = sorted(index_bits)
        if lo[0] <= hi[0]:                  # some vertex format had a plain Position
            out["bbox"] = [lo, hi]
            upm = (out.get("art_tool") or {}).get("units_per_meter") or 0
            if upm:
                out["bbox_m"] = [[v / upm for v in lo], [v / upm for v in hi]]
        out["meshes"] = [m.get("Name") for m in r.get("Meshes") or [] if m]
        return out


class Obj:
    """One object of the tree. `get(name)` reads a member."""

    __slots__ = ("doc", "type", "at")

    def __init__(self, doc, t, at):
        self.doc, self.type, self.at = doc, t, at

    def get(self, name, default=None):
        m = self.type.member(name) if self.type else None
        if m is None:
            return default
        return self.doc.value(self.type, self.at, m)

    def names(self):
        return [m.name for m in self.type.members]

    def __repr__(self):
        return f"Obj({self.at}, {self.names()})"


def load(source):
    """A Doc from a path or bytes. Raises Compressed for files that need the runtime."""
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        with open(source, "rb") as f:
            data = f.read()
    return Doc(read_container(data))


# --------------------------------------------------------------------------------------------------
# Tree dump, line for line in the format of the external Granny bridge's `info --tree`, so the two
# can be compared to prove this reader.

def _g9(x):
    s = format(x, ".9g")
    if "e" in s:
        mant, exp = s.split("e")
        sign = exp[0]
        digits = exp[1:].lstrip("0").rjust(2, "0")
        s = f"{mant}E{sign}{digits}"
    return s


def _quote(text):
    out = ['"']
    for ch in text:
        if ch == '"' or ch < " ":
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dump_tree(doc):
    lines = []
    seen = {}
    c = doc.c

    def scalar(m, at):
        n = m.size
        raw = c.raw(at, n)
        w = max(1, m.width)
        es = SCALAR_SIZE.get(m.kind, 0)
        if es == 0 or es * w != n:
            return "0x" + raw.hex().upper()
        vals = struct.unpack("<" + SCALAR_FMT[m.kind] * w, raw)
        if m.kind == REAL32:
            return " ".join(_g9(v) for v in vals)
        return " ".join(str(v) for v in vals)

    def walk(path, t, at):
        for m in t.members:
            p = m.name if not path else path + "." + m.name
            a = (at[0], at[1] + m.offset)
            k = m.kind
            if k == INLINE:
                sub = doc.typedef(m.ref)
                w = max(1, m.width)
                if w == 1:
                    walk(p, sub, a)
                else:
                    for i in range(w):
                        walk(f"{p}[{i}]", sub, (a[0], a[1] + i * sub.size))
            elif k == REFERENCE:
                reference(p, doc.typedef(m.ref), c.ptr(a))
            elif k == REF_TO_ARRAY:
                by_value(p, doc.typedef(m.ref), c.i32(a), c.ptr((a[0], a[1] + 4)))
            elif k == ARRAY_OF_REFS:
                n, arr = c.i32(a), c.ptr((a[0], a[1] + 4))
                lines.append(f"{p} = [{n}]")
                if n > 0 and arr:
                    t2 = doc.typedef(m.ref)
                    for i in range(n):
                        reference(f"{p}[{i}]", t2, c.ptr((arr[0], arr[1] + 4 * i)))
            elif k == VARIANT_REF:
                reference(p, doc.typedef(c.ptr(a)), c.ptr((a[0], a[1] + 4)))
            elif k == REF_TO_VARIANT_ARRAY:
                by_value(p, doc.typedef(c.ptr(a)), c.i32((a[0], a[1] + 4)),
                         c.ptr((a[0], a[1] + 8)))
            elif k == STRING:
                s = c.ptr(a)
                lines.append(f"{p} = {'null' if not s else _quote(c.cstr(s))}")
            elif k in SCALAR_SIZE or k == TRANSFORM:
                lines.append(f"{p} = {scalar(m, a)}")
            else:
                raise Gr2Error(f"{p!r} has kind {k}, which the dump does not know")

    def reference(path, t, target):
        if not target:
            lines.append(f"{path} = null")
            return
        if t is None:
            lines.append(f"{path} = (untyped)")
            return
        key = (target, t.key)
        if key in seen:
            lines.append(f"{path} = -> {seen[key]}")
            return
        seen[key] = path
        walk(path, t, target)

    def by_value(path, t, n, arr):
        if n <= 0 or not arr or t is None:
            lines.append(f"{path} = [{n}]{' null' if n > 0 and not arr else ''}")
            return
        if doc.is_flat(t):
            raw = c.raw(arr, n * t.size)
            h = hashlib.sha256(raw).hexdigest()[:16]
            lines.append(f"{path} = [{n}] x {t.size} B sha256 {h}")
            return
        lines.append(f"{path} = [{n}]")
        for i in range(n):
            el = (arr[0], arr[1] + i * t.size)
            p = f"{path}[{i}]"
            key = (el, t.key)
            if key in seen:
                lines.append(f"{p} = -> {seen[key]}")
                continue
            seen[key] = p
            walk(p, t, el)

    t = doc.typedef(c.root_type)
    if t is None or not c.root_obj:
        return ["(root) = null"]
    seen[(c.root_obj, t.key)] = "(root)"
    walk("", t, c.root_obj)
    return lines


def type_listing(doc, t=None, indent="", done=None):
    """The type definitions under the root, for reading: one member per line."""
    done = set() if done is None else done
    t = t or doc.typedef(doc.c.root_type)
    out = []
    if t.key in done:
        return out
    done.add(t.key)
    for m in t.members:
        out.append(f"{indent}{m.name}: {KIND_NAMES.get(m.kind, m.kind)}"
                   f"{'[' + str(m.width) + ']' if m.width > 1 else ''} @{m.offset} {m.size} B")
        if m.ref and m.kind in (INLINE, REFERENCE, REF_TO_ARRAY, ARRAY_OF_REFS):
            out += type_listing(doc, doc.typedef(m.ref), indent + "  ", done)
    return out
