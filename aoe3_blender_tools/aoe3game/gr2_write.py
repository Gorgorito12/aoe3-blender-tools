# SPDX-License-Identifier: GPL-3.0-or-later
"""Writes Granny 2 files: a generic serializer for a data tree, and `static_model` for a building.

The output is a version 6 file with one uncompressed section, laid out as the game's own
1-section models: the file header and section record, the relocation table, then the section
data in three runs (32-bit data, then 16-bit arrays, then 8-bit data such as strings) whose
starts are the section's first16 and first8 fields. Pointers are written as 0; each one is a
relocation (slot offset, section 0, target offset). The CRC covers every byte after 0x58.

Coordinates: the model comes in metres in Blender's basis (X right, Z up, front toward -Y) and is
written in the basis of the game's stock buildings ("ESPostExport": 0.615157485 units per metre,
right -X, up +Y, back +Z), so a Blender point (x, y, z) is stored as (-x, z, -y) * units.
"""
import math
import struct
import zlib

from . import gr2
from .gr2_types import Spec, schema

STOCK_BASIS = {"name": "ESPostExport", "major": 1, "minor": 2,
               "units_per_meter": 0.615157485, "right": (-1.0, 0.0, 0.0),
               "up": (0.0, 1.0, 0.0), "back": (0.0, 0.0, 1.0)}
TYPE_TAG = 0x80000011          # the tag of the game's single-section building files
IDENTITY_TRANSFORM = (0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0,
                      1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
EXPORTER = "AoE3 Blender Tools"


class W:
    """An object to write: its spec and member values (missing members are zero / null)."""

    def __init__(self, spec, **values):
        self.spec, self.values = spec, values


class Flat:
    """An array of pointer-free elements given as bytes."""

    def __init__(self, spec, raw, count):
        if spec_size(spec) * count != len(raw):
            raise ValueError(f"{spec.name}: {count} elements do not fill {len(raw)} bytes")
        self.spec, self.raw, self.count = spec, bytes(raw), count


def member_size(kind, ref, width):
    w = max(1, width)
    if kind == gr2.INLINE:
        return spec_size(ref) * w
    if kind in gr2.POINTER_SIZE:
        return gr2.POINTER_SIZE[kind]
    if kind == gr2.TRANSFORM:
        return gr2.TRANSFORM_SIZE * w
    return gr2.SCALAR_SIZE[kind] * w


def spec_size(spec):
    return sum(member_size(k, r, w) for k, _n, r, w in spec.members)


def element_bits(spec):
    """32, 16 or 8: the widest scalar of a flat spec (decides which run its arrays go to)."""
    widest = 0
    for k, _n, r, _w in spec.members:
        if k == gr2.INLINE:
            widest = max(widest, element_bits(r))
        elif k == gr2.TRANSFORM:
            widest = 32
        else:
            widest = max(widest, 8 * gr2.SCALAR_SIZE.get(k, 4))
    return widest or 32


# --------------------------------------------------------------------------------------------------
# Serializer

class _Writer:
    RUNS = (32, 16, 8)

    def __init__(self):
        self.runs = {32: bytearray(), 16: bytearray(), 8: bytearray()}
        self.relocs = []            # ((run, off), (run, off))
        self.types = {}             # id(spec) -> loc
        self.objects = {}           # id(W) -> loc
        self.strings = {}

    def alloc(self, run, size, align=4):
        b = self.runs[run]
        while len(b) % align:
            b.append(0)
        off = len(b)
        b.extend(bytes(size))
        return (run, off)

    def put(self, loc, fmt, *values):
        struct.pack_into("<" + fmt, self.runs[loc[0]], loc[1], *values)

    def pointer(self, slot, target):
        if target is not None:
            self.relocs.append((slot, target))

    def string(self, text):
        if text is None:
            return None
        loc = self.strings.get(text)
        if loc is None:
            raw = text.encode("cp1252") + b"\0"
            loc = self.alloc(8, len(raw), 1)
            self.runs[8][loc[1]:loc[1] + len(raw)] = raw
            self.strings[text] = loc
        return loc

    def typedef(self, spec):
        loc = self.types.get(id(spec))
        if loc is not None:
            return loc
        n = len(spec.members)
        loc = self.alloc(32, gr2.MEMBER_RECORD * (n + 1))
        self.types[id(spec)] = loc      # before the members: types may reach themselves
        for i, (kind, name, ref, width) in enumerate(spec.members):
            at = (32, loc[1] + i * gr2.MEMBER_RECORD)
            self.put(at, "I", kind)
            self.pointer((32, at[1] + 4), self.string(name))
            if ref is not None:
                self.pointer((32, at[1] + 8), self.typedef(ref))
            self.put((32, at[1] + 12), "I", width)
        return loc

    def obj(self, w):
        if w is None:
            return None
        loc = self.objects.get(id(w))
        if loc is None:
            loc = self.alloc(32, spec_size(w.spec))
            self.objects[id(w)] = loc
            self.fill(w.spec, loc, w.values)
        return loc

    def array(self, spec, value):
        """Location of an array: Flat bytes, or a list of W laid out one after another."""
        if isinstance(value, Flat):
            if not value.count:
                return None, 0
            run = element_bits(value.spec)
            loc = self.alloc(run, len(value.raw), max(1, run // 8))
            self.runs[run][loc[1]:loc[1] + len(value.raw)] = value.raw
            return loc, value.count
        items = list(value or [])
        if not items:
            return None, 0
        size = spec_size(spec)
        loc = self.alloc(32, size * len(items))
        for i, it in enumerate(items):
            if id(it) in self.objects:
                raise ValueError(f"{spec.name}: an object in an array was already written")
            at = (32, loc[1] + i * size)
            self.objects[id(it)] = at
        for i, it in enumerate(items):
            self.fill(it.spec, (32, loc[1] + i * size), it.values)
        return loc, len(items)

    def fill(self, spec, loc, values):
        off = 0
        for kind, name, ref, width in spec.members:
            at = (loc[0], loc[1] + off)
            v = values.get(name)
            if kind == gr2.INLINE:
                subs = v if isinstance(v, list) else [v]
                size = spec_size(ref)
                for k, sub in enumerate(subs):
                    if sub is not None:
                        sv = sub.values if isinstance(sub, W) else sub
                        self.fill(ref, (at[0], at[1] + k * size), sv)
            elif kind == gr2.REFERENCE:
                self.pointer(at, self.obj(v))
            elif kind == gr2.STRING:
                self.pointer(at, self.string(v))
            elif kind == gr2.REF_TO_ARRAY:
                a, n = self.array(ref, v)
                self.put(at, "i", n)
                self.pointer((at[0], at[1] + 4), a)
            elif kind == gr2.ARRAY_OF_REFS:
                items = list(v or [])
                self.put(at, "i", len(items))
                if items:
                    table = self.alloc(32, 4 * len(items))
                    for i, it in enumerate(items):
                        self.pointer((32, table[1] + 4 * i), self.obj(it))
                    self.pointer((at[0], at[1] + 4), table)
            elif kind == gr2.VARIANT_REF:
                if v is not None:
                    self.pointer(at, self.typedef(v.spec))
                    self.pointer((at[0], at[1] + 4), self.obj(v))
            elif kind == gr2.REF_TO_VARIANT_ARRAY:
                if v is not None:
                    vspec = v.spec if isinstance(v, Flat) else v[0].spec
                    self.pointer(at, self.typedef(vspec))
                    a, n = self.array(vspec, v)
                    self.put((at[0], at[1] + 4), "i", n)
                    self.pointer((at[0], at[1] + 8), a)
            elif kind == gr2.TRANSFORM:
                self.put(at, "I16f", *(v if v is not None else IDENTITY_TRANSFORM))
            else:
                w = max(1, width)
                if v is None:
                    v = (0,) * w
                elif not isinstance(v, (tuple, list)):
                    v = (v,)
                if len(v) != w:
                    raise ValueError(f"{spec.name}.{name}: {len(v)} values for width {w}")
                self.put(at, gr2.SCALAR_FMT[kind] * w, *v)
            off += member_size(kind, ref, width)


def serialize(root, *, type_tag=TYPE_TAG):
    """The bytes of a version 6, single-section file whose root object is `root` (a W)."""
    w = _Writer()
    root_type = w.typedef(root.spec)
    root_obj = w.obj(root)
    r32, r16, r8 = w.runs[32], w.runs[16], w.runs[8]
    while len(r32) % 4:
        r32.append(0)
    while len(r16) % 2:
        r16.append(0)
    base = {32: 0, 16: len(r32), 8: len(r32) + len(r16)}
    data = bytearray(r32 + r16 + r8)
    while len(data) % 4:
        data.append(0)

    def flat(loc):
        return base[loc[0]] + loc[1]

    relocs = sorted((flat(s), flat(t)) for s, t in w.relocs)
    header_end = 0x20 + gr2.HEADER_SIZE[6] + gr2.SECTION_RECORD     # 132
    reloc_off = header_end
    data_off = reloc_off + gr2.RELOCATION * len(relocs)
    total = data_off + len(data)
    sec = gr2.Section(0, data_off, len(data), len(data), 4, base[16], base[8],
                      reloc_off, len(relocs), data_off, 0)
    out = bytearray()
    out += gr2.MAGIC
    out += struct.pack("<II8x", header_end, 0)
    out += struct.pack("<10I", 6, total, 0, gr2.HEADER_SIZE[6], 1, 0, flat(root_type), 0,
                       flat(root_obj), type_tag)
    out += struct.pack("<4I", 0, 0, 0, 0)
    out += sec.pack()
    for s, t in relocs:
        out += struct.pack("<3I", s, 0, t)
    out += data
    assert len(out) == total
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


# --------------------------------------------------------------------------------------------------
# A static model

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def to_file(p, units):
    """A Blender-basis point or vector (metres) in the stock basis (units)."""
    return (-p[0] * units, p[2] * units, -p[1] * units)


def static_model(name, positions, normals, uvs, triangles, *, texture, bump,
                 bones=(), effect="bumpspec_mask_alphatest", player_colour=False,
                 units_per_meter=STOCK_BASIS["units_per_meter"], v_flip=True, source=""):
    """Bytes of a .gr2 holding one static, textured mesh.

    positions, normals: per vertex, metres, Blender basis. uvs: per vertex (Blender, V up).
    triangles: vertex index triples, any winding (each one is put in the game's order, counter
    clockwise around its normal in the stored coordinates). texture, bump: the stored texture
    names (the engine matches the part after "\\art\\"). bones: (name, (x, y, z) metres) attach
    points, children of the root as the game's buildings have them.
    """
    S = schema()
    n = len(positions)
    if not (len(normals) == len(uvs) == n):
        raise ValueError("positions, normals and uvs must have one entry per vertex")
    P = [to_file(p, units_per_meter) for p in positions]
    N = []
    for v in normals:
        q = to_file(v, 1.0)
        l = math.sqrt(_dot(q, q)) or 1.0
        N.append((q[0] / l, q[1] / l, q[2] / l))
    T = [(u, 1.0 - v) if v_flip else (u, v) for u, v in uvs]
    tris = []
    for a, b, c in triangles:
        g = _cross(_sub(P[b], P[a]), _sub(P[c], P[a]))
        nn = (N[a][0] + N[b][0] + N[c][0], N[a][1] + N[b][1] + N[c][1],
              N[a][2] + N[b][2] + N[c][2])
        tris.append((a, c, b) if _dot(g, nn) < 0 else (a, b, c))

    vert_raw = b"".join(struct.pack("<8f", *P[i], *N[i], *T[i]) for i in range(n))
    vertices = Flat(S["VertexPNT"], vert_raw, n)
    flat_idx = [i for t in tris for i in t]
    if n <= 0xFFFF:
        indices16 = Flat(S["Int16"], struct.pack(f"<{len(flat_idx)}H", *flat_idx), len(flat_idx))
        indices32 = []
    else:
        indices16 = []
        indices32 = Flat(S["Int32"], struct.pack(f"<{len(flat_idx)}i", *flat_idx), len(flat_idx))
    lo = tuple(min(p[k] for p in P) for k in range(3)) if P else (0.0,) * 3
    hi = tuple(max(p[k] for p in P) for k in range(3)) if P else (0.0,) * 3

    def texture_obj(path):
        return W(S["Texture"], FromFileName=path, TextureType=0, Width=0, Height=0, Encoding=1,
                 SubFormat=0,
                 Layout=W(S["PixelLayout"], BytesPerPixel=4, ShiftForComponent=(0, 8, 16, 24),
                          BitsForComponent=(8, 8, 8, 8)),
                 Images=[])

    tex_diffuse, tex_bump = texture_obj(texture), texture_obj(bump)
    map_diffuse = W(S["Material"], Name="Map #0", Maps=[], Texture=tex_diffuse)
    map_bump = W(S["Material"], Name="Map #1", Maps=[], Texture=tex_bump)
    if player_colour:
        params = W(S["ShaderParamsColour"], ESEffectName="bumpspec_mask_pixelxform",
                   ESEffectParamName1="lighting", ESEffectParamValue1="lighting\\specpower16",
                   ESEffectParamLookup1=0, ESEffectParamName2="pixelxformColor",
                   ESEffectParamValue2="playerColor", ESEffectParamLookup2=2)
    else:
        params = W(S["ShaderParams"], ESEffectName=effect, ESEffectParamName1="lighting",
                   ESEffectParamValue1="lighting\\specpower16", ESEffectParamLookup1=0)
    surface = W(S["Material"], Name=name,
                Maps=[W(S["MaterialMap"], Usage="Diffuse Color", Map=map_diffuse),
                      W(S["MaterialMap"], Usage="Bump", Map=map_bump)],
                ExtendedData=params)

    def bone(bname, parent, pos=None):
        if pos is None:
            tr, inv = IDENTITY_TRANSFORM, (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        else:
            x, y, z = to_file(pos, units_per_meter)
            tr = (1, x, y, z) + IDENTITY_TRANSFORM[4:]
            inv = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1)
        return W(S["Bone"], Name=bname, ParentIndex=parent, Transform=tr,
                 InverseWorldTransform=inv,
                 ExtendedData=W(S["UserProperties"], UserDefinedProperties=""))

    bone_list = [bone("bone_main", -1), bone(name, 0)]
    bone_list += [bone(bn, 0, pos) for bn, pos in bones]
    skeleton = W(S["Skeleton"], Name="bone_main", Bones=bone_list)
    vdata = W(S["VertexData"], Vertices=vertices, VertexAnnotationSets=[])
    topo = W(S["TriTopology"],
             Groups=Flat(S["TriMaterialGroup"], struct.pack("<3i", 0, 0, len(tris)), 1),
             Indices=indices32, Indices16=indices16)
    mesh = W(S["Mesh"], Name=name, PrimaryVertexData=vdata, MorphTargets=[],
             PrimaryTopology=topo,
             MaterialBindings=[W(S["MaterialBinding"], Material=surface)],
             BoneBindings=[W(S["BoneBinding"], BoneName=name, OBBMin=lo, OBBMax=hi,
                             TriangleIndices=[])],
             ExtendedData=W(S["UserProperties"], UserDefinedProperties=""))
    model = W(S["Model"], Name="bone_main", Skeleton=skeleton,
              InitialPlacement=IDENTITY_TRANSFORM,
              MeshBindings=[W(S["ModelMeshBinding"], Mesh=mesh)])
    b = STOCK_BASIS
    root = W(S["FileInfo"],
             ArtToolInfo=W(S["ArtToolInfo"], FromArtToolName=b["name"],
                           ArtToolMajorRevision=b["major"], ArtToolMinorRevision=b["minor"],
                           UnitsPerMeter=units_per_meter, Origin=(0.0, 0.0, 0.0),
                           RightVector=b["right"], UpVector=b["up"], BackVector=b["back"]),
             ExporterInfo=W(S["ExporterInfo"], ExporterName=EXPORTER, ExporterMajorRevision=2,
                            ExporterMinorRevision=5, ExporterCustomization=0,
                            ExporterBuildNumber=1),
             FromFileName=source or name,
             Textures=[tex_bump, tex_diffuse],
             Materials=[map_bump, map_diffuse, surface],
             Skeletons=[skeleton], VertexDatas=[vdata], TriTopologies=[topo], Meshes=[mesh],
             Models=[model], TrackGroups=[], Animations=[])
    return serialize(root)


def _curve(S, degree, knots, controls):
    return {"Degree": degree,
            "Knots": Flat(S["Real32"], struct.pack(f"<{len(knots)}f", *knots), len(knots)),
            "Controls": Flat(S["Real32"], struct.pack(f"<{len(controls)}f", *controls),
                             len(controls))}


def sink_animation(name, bones, height_m, *, duration=4.0, tilt_deg=4.0, steps=8,
                   units_per_meter=STOCK_BASIS["units_per_meter"], source=""):
    """Bytes of a .gr2 animation that sinks a static building into the ground: the mesh bone
    (named like the building, as `static_model` writes it) and every attach bone go down by
    `height_m` metres, faster and faster, while the building leans a few degrees. The tracks
    are named after those bones, children of "bone_main", as in the game's building death
    animations (one track group named after the model, curves of degree 1)."""
    S = schema()
    drop = height_m * units_per_meter
    times = [duration * k / steps for k in range(steps + 1)]
    ease = [(t / duration) ** 2 for t in times]
    lean = math.radians(tilt_deg)
    tracks = []
    for bone_name, pos in [(name, (0.0, 0.0, 0.0))] + list(bones):
        x, y, z = to_file(pos, units_per_meter)
        position = []
        for e in ease:
            position += [x, y - drop * e, z]
        orientation = []
        for e in ease:                   # a turn about the file's X axis (the building's side)
            a = lean * e / 2
            orientation += [math.sin(a), 0.0, 0.0, math.cos(a)]
        tracks.append(W(S["TransformTrack"], Name=bone_name,
                        PositionCurve=_curve(S, 1, times, position),
                        OrientationCurve=_curve(S, 1, times, orientation),
                        ScaleShearCurve=_curve(S, 0, [0.0],
                                               [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])))
    group = W(S["TrackGroup"], Name="bone_main", VectorTracks=[], TransformTracks=tracks,
              TransformLODErrors=[], TextTracks=[], InitialPlacement=IDENTITY_TRANSFORM,
              AccumulationFlags=0, LoopTranslation=(0.0, 0.0, 0.0))
    anim = W(S["Animation"], Name=source or f"{name}_death", Duration=duration,
             TimeStep=1.0 / 60, Oversampling=0.0, TrackGroups=[group])
    b = STOCK_BASIS
    root = W(S["FileInfo"],
             ArtToolInfo=W(S["ArtToolInfo"], FromArtToolName=b["name"],
                           ArtToolMajorRevision=b["major"], ArtToolMinorRevision=b["minor"],
                           UnitsPerMeter=units_per_meter, Origin=(0.0, 0.0, 0.0),
                           RightVector=b["right"], UpVector=b["up"], BackVector=b["back"]),
             ExporterInfo=W(S["ExporterInfo"], ExporterName=EXPORTER, ExporterMajorRevision=2,
                            ExporterMinorRevision=5, ExporterCustomization=0,
                            ExporterBuildNumber=1),
             FromFileName=source or f"{name}_death", Textures=[], Materials=[], Skeletons=[],
             VertexDatas=[], TriTopologies=[], Meshes=[], Models=[], TrackGroups=[group],
             Animations=[anim])
    return serialize(root)
