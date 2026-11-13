# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws coloured ground rings, floating icons, rank marks and range rings for the game's effects folder.

    python -I tools/make_rings.py [--out <folder>] [--folder <name>]          writes every file
    python -I tools/make_rings.py [--out <folder>] [--folder <name>] --check  exit code 1 if a file in <folder>
                                                                              differs from what it would write

--out is where the files are written (default out/rings in the repository). --folder is the folder under
art/effects/ of the game (or of a mod) the files are meant for, and goes into the paths the files name (default
"rings": art/effects/rings/). No pixel and no mesh comes from the game; the only game asset named is the stock
effects\\Chiefpower\\chiefpower model, which the particles hang on.

- ring_<name>.xml, the model: by <logic type="UnitType">, one flat particle on the ground of the size in SHAPES;
- ring_<name>_<size>.particle, that particle, for each size;
- ring_<name>.ddt, the 64x64 DXT3 texture of a unit, a tree or a cavalryman;
- ring_<name>_<size>.ddt, the texture of a building, with lines as thick in metres as those of a unit's ring;
- range_<metres>.xml, its particle and its texture: one thin line of that radius, to show a range on the ground;
- for wood, food, gold and work, aura_<name>.xml, a marker: the ring and, floating over the unit,
  icon_<name>_<height>.particle with the glyph of icon_<name>.ddt, drawn here;
- rank_<1-5>.xml, a rank mark floating over the unit: one to three chevrons, then stars.

A unit or an aura shows one with <modelattachment>effects\\<folder>\\ring_<name>.xml</modelattachment>.
"""
import functools
import math
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "rings"
FOLDER = "rings"  # set by main: the folder under art/effects/ the files name
SIZE = 64

# One meaning per ring: its main colour, on the outside, and the lighter one it fades to.
RINGS = {
    "wood": ((235, 130, 20), (255, 225, 130)),    # amber: gathering wood
    "food": ((220, 30, 30), (255, 160, 110)),     # red: gathering food, as the food icon of the panel
    "gold": ((255, 205, 0), (255, 250, 170)),     # yellow: gathering gold, as the coin icon of the panel
    "work": ((50, 205, 50), (220, 245, 90)),      # green: gathers or works faster
    "damage": ((225, 20, 180), (255, 160, 235)),  # magenta: damage, kept away from the three colours above
    "heal": ((245, 248, 255), (150, 215, 255)),   # white: hit points, healing
    "speed": ((30, 105, 255), (140, 235, 255)),   # blue: moves faster
}

# Radii as fractions of the half width, as (inner, outer): a wide band and a thin one.
BANDS = ((0.74, 0.97), (0.52, 0.60))
EDGE = 0.035  # the soft edge of a band, in the same fraction
UNIT_RADIUS = 2.2  # metres, the half width of the texture on a unit; its rim is at 0.97 of that
# By logic branch, most specific first: the size in the file names, the half width in metres, and for a building
# the side of its own texture. <none> is everything else, a tree too.
SHAPES = (
    ("none", "unit", UNIT_RADIUS, None),
    ("abstractcavalry", "cavalry", 4.6, None),
    ("abstractartillery", "cavalry", 4.6, None),
    ("abstracttowncenter", "large", 20, 256),
    ("abstracthouse", "small", 9, 128),
    ("building", "medium", 16, 256),
)
# The floating icon of aura_<name>.xml, by logic branch: the same keys as SHAPES, then the kinds of resource. The height
# is in metres above the unit's feet, as the ring lies at them. The side is the half width of the sprite.
ICON_HEIGHTS = (
    ("none", "unit", 3.2),
    ("abstractcavalry", "cavalry", 4.0),
    ("abstractartillery", "cavalry", 4.0),
    ("tree", "tree", 8.0),
    ("abstractmine", "mine", 3.5),
    ("abstracttowncenter", "large", 14.0),
    ("abstracthouse", "small", 9.0),
    ("building", "medium", 11.0),
)
ICON_SIDE = 0.9
ICON_OUTLINE = 0.14  # the dark edge that keeps a glyph readable, in the same fraction of the half width
ICON_DARK = (24, 20, 16)
# Each glyph is a list of (x, y, outer radius, inner radius), in fractions of the half width.
GLYPHS = {
    "wood": ((-0.40, 0.30, 0.38, 0.0), (0.40, 0.30, 0.38, 0.0), (0.0, -0.36, 0.38, 0.0)),  # three log ends
    "food": ((-0.24, -0.24, 0.50, 0.0), (0.0, 0.0, 0.38, 0.0), (0.16, 0.16, 0.26, 0.0)),  # the meat of a drumstick
    "gold": ((0.0, 0.0, 0.76, 0.46), (0.0, 0.0, 0.20, 0.0)),  # a coin
    # a gear: a wheel and eight teeth
    "work": ((0.0, 0.0, 0.60, 0.26),) + tuple((0.72 * math.cos(i * math.pi / 4), 0.72 * math.sin(i * math.pi / 4), 0.17, 0.0)
                                              for i in range(8)),
}
# What a glyph draws over itself in ICON_ACCENT: a block holds one of the two colours, as a DXT3 block has two.
GLYPH_ACCENTS = {
    "food": ((0.30, 0.30, 0.11, 0.0), (0.40, 0.40, 0.11, 0.0), (0.50, 0.50, 0.11, 0.0), (0.58, 0.58, 0.11, 0.0),
             (0.72, 0.54, 0.15, 0.0), (0.54, 0.72, 0.15, 0.0)),  # its bone
}
ICON_ACCENT = (245, 235, 210)
# Rank marks: one, two and three chevrons in bronze, silver and gold, floating over the
# unit with no ring. In the texture a smaller y is higher on screen: every rank starts from the same top chevron
# and grows down, and RANK_LIFT metres over the aura icons keeps the lowest one clear of the HP bar: bar and mark
# scale alike with the camera's zoom. Ranks 4 and 5 are rank 3's gold chevrons, in the same place, with one or
# two white stars over them: their sprite is RANK_SIDE times the scale that fits the stars, around the same centre,
# so the chevrons do not move and the lowest one keeps its gap to the bar.
RANKS = {1: (205, 127, 50), 2: (200, 205, 215), 3: (255, 205, 40), 4: (255, 205, 40), 5: (255, 205, 40)}
RANK_ARMS = {1: (-0.38,), 2: (-0.38, 0.10), 3: (-0.38, 0.10, 0.58), 4: (-0.38, 0.10, 0.58), 5: (-0.38, 0.10, 0.58)}
RANK_STARS = {4: ((0.0, -1.15),), 5: ((-0.40, -1.15), (0.40, -1.15))}
RANK_STAR_RADIUS = 0.30  # from a star's centre to its points
RANK_STAR_COLOUR = (250, 250, 240)
RANK_SIDE = 0.75
RANK_LIFT = 1.15


def star(x, y):
    """Circles of a five-pointed star with a point up: a core and five arms that thin to their points."""
    out = [(x, y, 0.12, 0.0)]
    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        for step in range(1, 6):
            t = step / 5
            out.append((x + math.cos(angle) * RANK_STAR_RADIUS * t, y + math.sin(angle) * RANK_STAR_RADIUS * t,
                        0.10 * (1 - t) + 0.035, 0.0))
    return tuple(out)


def rank_mark(rank):
    """The glyph, the star accent and the scale of rank's sprite against RANK_SIDE (1 for ranks 1 to 3)."""
    glyph = tuple(circle for y in RANK_ARMS[rank] for circle in chevron(y))
    stars = tuple(circle for x, y in RANK_STARS.get(rank, ()) for circle in star(x, y))
    if not stars:
        return glyph, (), 1.0
    reach = max(max(abs(x), abs(y)) + outer for x, y, outer, _ in glyph + stars) + ICON_OUTLINE
    scale = reach / 0.98
    shrink = lambda circles: tuple((x / scale, y / scale, outer / scale, inner / scale) for x, y, outer, inner in circles)
    return shrink(glyph), shrink(stars), scale


def chevron(y):
    """Circles along an upward chevron whose arms end at height y."""
    steps = range(-6, 7)
    return tuple((0.72 * t / 6, y - 0.30 * (1 - abs(t) / 6), 0.13, 0.0) for t in steps)


# Range rings, by radius in metres, a thin line of RANGE_LINE metres in a neutral colour.
RANGES = (4, 6, 8, 10, 12, 14, 16, 20, 24, 30)
RANGE_LINE = 0.30
RANGE_COLOURS = ((245, 245, 235), (255, 255, 255))
OPACITY = 0.70  # the ground shows through
# A DXT3 block holds two colours and two mixes of them. By how much of the main colour: 1, 2/3, 1/3, 0.
SHADES = (0, 2, 3, 1)


def building_shape(radius):
    """The bands and the edge at a building's radius, the same metres as on a unit: only the gap to the rim is kept."""
    scale = UNIT_RADIUS / radius
    wide, gap, thin = (BANDS[0][1] - BANDS[0][0]) * scale, (BANDS[0][0] - BANDS[1][1]) * scale, (BANDS[1][1] - BANDS[1][0]) * scale
    rim = BANDS[0][1]
    return ((rim - wide, rim), (rim - wide - gap - thin, rim - wide - gap)), EDGE * scale


def coverage(r, bands, edge):
    """How opaque a texel at radius r is, from 0 to 1."""
    best = 0.0
    for inner, outer in bands:
        value = min((r - inner) / edge + 0.5, (outer - r) / edge + 0.5)
        best = max(best, min(1.0, max(0.0, value)))
    return best


@functools.lru_cache(maxsize=None)
def alpha_map(size, bands, edge):
    """Alpha by texel, 0 to 15, averaged over four samples per side so small mips stay round."""
    samples = 4
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            total = 0.0
            for sy in range(samples):
                for sx in range(samples):
                    u = (x + (sx + 0.5) / samples) / size * 2 - 1
                    v = (y + (sy + 0.5) / samples) / size * 2 - 1
                    total += coverage(math.hypot(u, v), bands, edge)
            row.append(round(total / samples ** 2 * OPACITY * 15))
        out.append(row)
    return out


def shade(x, y, size, bands):
    """The block index of a texel: the wide band fades from the main colour at its rim, the thin one is light."""
    r = math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1)
    inner, outer = bands[0]
    main = min(1.0, max(0.0, (r - inner) / (outer - inner)))
    return SHADES[min(3, int((1.0 - main) * 4))]


def glyph_cover(u, v, glyph, grow):
    """1 if (u, v) falls in the glyph with its circles grown by grow, else 0."""
    for x, y, outer, inner in glyph:
        r = math.hypot(u - x, v - y)
        if r <= outer + grow and (inner == 0.0 or r >= inner - grow):
            return 1.0
    return 0.0


def icon_block(size, colours, glyph, accent=(), outline=ICON_OUTLINE, accent_colour=ICON_ACCENT):
    """DXT3 blocks of an icon: the glyph in its colour on a dark edge, alpha from four samples per side."""
    samples = 4
    whole = glyph + accent
    alpha, inside, over = [], [], []
    for y in range(size):
        alpha_row, inside_row, over_row = [], [], []
        for x in range(size):
            total = core = bone = 0.0
            for sy in range(samples):
                for sx in range(samples):
                    u = (x + (sx + 0.5) / samples) / size * 2 - 1
                    v = (y + (sy + 0.5) / samples) / size * 2 - 1
                    total += glyph_cover(u, v, whole, outline)
                    core += glyph_cover(u, v, whole, 0.0)
                    bone += glyph_cover(u, v, accent, 0.0)
            alpha_row.append(round(total / samples ** 2 * 15))
            inside_row.append(core / samples ** 2 >= 0.5)
            over_row.append(bone / samples ** 2 >= 0.5)
        alpha.append(alpha_row)
        inside.append(inside_row)
        over.append(over_row)
    dark = rgb565(ICON_DARK)
    out = bytearray()
    for by in range(0, size, 4):
        for bx in range(0, size, 4):
            indices = 0
            bones = sum(over[by + y][bx + x] for y in range(4) for x in range(4))
            solid = sum(inside[by + y][bx + x] for y in range(4) for x in range(4))
            main = rgb565(accent_colour if bones * 2 > solid else colours[0])
            for y in range(4):
                row = 0
                for x in range(4):
                    row |= alpha[by + y][bx + x] << (4 * x)
                    indices |= (0 if inside[by + y][bx + x] else 1) << (2 * (y * 4 + x))
                out += struct.pack("<H", row)
            out += struct.pack("<HHI", main, dark, indices)
    return bytes(out)


@functools.lru_cache(maxsize=None)  # the textures do not depend on --folder
def icon_ddt(colours, glyph, accent=(), size=SIZE, outline=ICON_OUTLINE, accent_colour=ICON_ACCENT):
    mips = int(math.log2(size)) - 1
    levels = [icon_block(size >> i, colours, glyph, accent, outline, accent_colour) for i in range(mips)]
    out = b"RTS3" + bytes((0, 1, 8, mips)) + struct.pack("<II", size, size)
    offset = len(out) + 8 * mips
    for level in levels:
        out += struct.pack("<II", offset, len(level))
        offset += len(level)
    return out + b"".join(levels)


def rgb565(colour):
    r, g, b = colour
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def dxt3(size, colours, bands, edge):
    """DXT3 blocks: explicit alpha in 4 bits, then the two colours and a 2-bit index per texel."""
    alpha = alpha_map(size, bands, edge)
    main, light = rgb565(colours[0]), rgb565(colours[1])
    out = bytearray()
    for by in range(0, size, 4):
        for bx in range(0, size, 4):
            indices = 0
            for y in range(4):
                row = 0
                for x in range(4):
                    row |= alpha[by + y][bx + x] << (4 * x)
                    indices |= shade(bx + x, by + y, size, bands) << (2 * (y * 4 + x))
                out += struct.pack("<H", row)
            out += struct.pack("<HHI", main, light, indices)
    return bytes(out)


@functools.lru_cache(maxsize=None)
def ddt(colour, size=SIZE, bands=BANDS, edge=EDGE):
    """The RTS3 container: usage 0, alpha 1, format 8, then an (offset, size) pair per mip, down to 4x4."""
    mips = int(math.log2(size)) - 1
    levels = [dxt3(size >> i, colour, bands, edge) for i in range(mips)]
    out = b"RTS3" + bytes((0, 1, 8, mips)) + struct.pack("<II", size, size)
    offset = len(out) + 8 * mips
    for level in levels:
        out += struct.pack("<II", offset, len(level))
        offset += len(level)
    return out + b"".join(levels)


def branches(name):
    out = ""
    for branch, size, _, _ in SHAPES:
        out += f"""\t\t\t\t<{branch}>
\t\t\t\t\t<assetreference type="ParticleSystem">
\t\t\t\t\t\t<file>effects\\{FOLDER}\\ring_{name}_{size}.particle</file>
\t\t\t\t\t</assetreference>
\t\t\t\t</{branch}>
"""
    return out


def icon_logic(name):
    out = ""
    for branch, height, _ in ICON_HEIGHTS:
        out += f"""\t\t\t\t<{branch}>
\t\t\t\t\t<assetreference type="ParticleSystem">
\t\t\t\t\t\t<file>effects\\{FOLDER}\\icon_{name}_{height}.particle</file>
\t\t\t\t\t</assetreference>
\t\t\t\t</{branch}>
"""
    return out


def icon_attachment(name):
    """The icon, in an attachment of its own: a logic branch shows only one of two particle systems."""
    out = icon_logic(name)
    return f"""\t<attachment>
\t\ticon_a
\t\t<component>
\t\t\ticon_a
\t\t\t<notshadowcaster/>
\t\t\t<logic type="UnitType">
{out}\t\t\t</logic>
\t\t</component>
\t\t<anim>
\t\t\tIdle
\t\t\t<component>icon_a</component>
\t\t</anim>
\t</attachment>
"""


def range_shape(radius):
    """One band at the rim, RANGE_LINE metres wide: the particle's half width is radius / rim."""
    rim = BANDS[0][1]
    half = radius / rim
    return ((rim - RANGE_LINE / half, rim),), EDGE * UNIT_RADIUS / half


def range_logic(radius):
    return f"""\t\t\t\t<none>
\t\t\t\t\t<assetreference type="ParticleSystem">
\t\t\t\t\t\t<file>effects\\{FOLDER}\\range_{radius}.particle</file>
\t\t\t\t\t</assetreference>
\t\t\t\t</none>
"""


def xml(name, marker=False, logic=None):
    return f"""<?xml version="1.0" encoding="utf-8"?>

<animfile>
\t<definebone>bone_main</definebone>
\t<attachment>
\t\tchiefpower_a
\t\t<component>
\t\t\tchiefpower_a
\t\t\t<notshadowcaster/>
\t\t\t<logic type="UnitType">
{logic or branches(name)}\t\t\t</logic>
\t\t</component>
\t\t<anim>
\t\t\tIdle
\t\t\t<component>chiefpower_a</component>
\t\t</anim>
\t</attachment>
{icon_attachment(name) if marker else ""}\t<component>
\t\tchiefpower_a
\t\t<assetreference type="GrannyModel">
\t\t\t<file>effects\\Chiefpower\\chiefpower</file>
\t\t</assetreference>
\t\t<decal>
\t\t\t<effecttype>default</effecttype>
\t\t\t<width>0.00</width>
\t\t\t<height>0.00</height>
\t\t\t<zoffset>0.00</zoffset>
\t\t</decal>
\t</component>
\t<anim>
\t\tIdle
\t\t<component>chiefpower_a</component>
\t\t<attach a="chiefpower_a" frombone="HITPOINTBAR" tobone="HITPOINTBAR" syncanims="0"/>
{'''\t\t<attach a="icon_a" frombone="HITPOINTBAR" tobone="HITPOINTBAR" syncanims="0"/>
''' if marker else ""}\t</anim>
</animfile>
"""


# Every field of a .particle file, in the order the game writes them. <appearancetype>2 lies flat on the
# ground, 0 faces the camera; <materialtype>0 with <material>0 honours the alpha of the texture, and the
# one particle lives for an hour, is back at once, and <startfull> has it there from the first frame.
PARTICLE = (
    ("emitter", """tiedtoemitter=1 ignorerotation=0 emitbymotion=0 loop=1 inheritvelocity=0 useminvelocity=0
        usemaxvelocity=0 alwaysactive=1 syncwithattackanim=0 maxparticles=1 appearancetype={appearance} updateradius=0.000
        maxparticlesvar=0.000 particlelife=2.000 particlelifevar=0.000 globalfadein=0.000 globalfadeinvar=0.000
        globalfadeout=0.000 globalfadeoutvar=0.000 emitdistance=1.000 emitdistancevar=0.000 emissionrate=100.000
        emissionratevar=0.000 initialdormancy=0.000 initialdormancyvar=0.000 initialupdate=0.000
        initialupdatevar=0.000 emissiontime=0.000 emissiontimevar=0.000 dormanttime=0.000 dormanttimevar=0.000
        initialdistance=0.000 initialdistancevar=0.000 initialvelocity=0.000 initialvelocityvar=0.000
        acceleration=0.000 accelerationvar=0.000 inheritinfluence=0.000 inheritinfluencevar=0.000 minvelocity=0.000
        minvelocityvar=0.000 maxvelocity=0.000 maxvelocityvar=0.000"""),
    ("shape", """startfull=1 emitawayfrombias=0 usespreader=0 shapetype=0 outerxradius=0.000 innerxradius=0.000
        outeryradius=0.000 inneryradius=0.000 outerzradius=0.000 innerzradius=0.000 centerheight={height:.3f} offaxis=0.000
        offaxisspread=0.000 offplane=0.000 offplanespread=0.000 biaspointheight=0.000"""),
    ("appearance", """orientbymotion=0 numfiles=1 numframes=0 framewidth=0 frameheight=0 materialtype=0
        emissive=16777215 specular=16777215 specularexponent=2.000 framespersecond=0.000 animationrate=1.000
        animationratevar=0.000"""),
    ("appearanceweights", None),
    ("opacity", """loopingcycle=0 numstages=0 opacity=1.000 opacityvar=0.000 cycletime=0.000 cycletimevar=0.000"""),
    ("opacitystages", ""),
    ("scale", """loopingcycle=0 numstages=0 scale={radius:.3f} scalevar=0.000 xscale=1.000 xscalevar=0.000 yscale=1.000
        yscalevar=0.000 zscale=1.000 zscalevar=0.000 cycletime=0.000 cycletimevar=0.000"""),
    ("scalestages", ""),
    ("speed", """loopingcycle=0 numstages=0 speed=1.000 speedvar=0.000 xspeed=1.000 xspeedvar=0.000 yspeed=1.000
        yspeedvar=0.000 zspeed=1.000 zspeedvar=0.000 cycletime=0.000 cycletimevar=0.000"""),
    ("speedstages", ""),
    ("color", """usepalette=0 loopingcycle=0 numpalettecolors=0 numstages=0 cycletime=0.000 cycletimevar=0.000
        fworldlightinginfluence=0.000 color=16777215"""),
    ("palettecolors", ""),
    ("colorstages", ""),
    ("forces", """randomorientation=0 tumble=0 tumblebothdirections=0 randomaxis=0 internalgravity=0.000
        internalgravityvar=0.000 internalwinddirection=0.000 internalwinddirectionvar=0.000 internalwindspeed=0.000
        internalwindspeedvar=0.000 internalwinddelay=0.000 internalwinddelayvar=0.000 externalwindinfluence=0.000
        externalwindinfluencevar=0.000 externalwinddelay=0.000 externalwinddelayvar=0.000 riverflowinfluence=0.000
        riverflowinfluencevar=0.000 minangularvelocity=0.000 maxangularvelocity=0.000 xaxis=0.000 xaxisvar=0.000
        yaxis=0.000 yaxisvar=0.000 zaxis=0.000 zaxisvar=0.000"""),
    ("collision", "numtypes=0 terraininteractiontype={terrain} terrainheight={terrainheight} terrainheightvar=0.000"),
    ("collisionstages", ""),
)


def particle(texture, radius, height=0.2, appearance=2, ground=True):
    out = "<particlefile>\n"
    for section, fields in PARTICLE:
        if fields is None:
            out += (f"\t<{section}>\n\t\t<stage>\n\t\t\t<file>effects\\{FOLDER}\\{texture}</file>\n"
                    f"\t\t\t<material>0</material>\n\t\t\t<weight>1.000</weight>\n\t\t</stage>\n\t</{section}>\n")
        elif fields:
            out += f"\t<{section}>\n"
            for field in fields.format(radius=radius, height=height, appearance=appearance, terrain=1 if ground else -1,
                                       terrainheight="0.200" if ground else "0.000").split():
                key, value = field.split("=")
                out += f"\t\t<{key}>{value}</{key}>\n"
            out += f"\t</{section}>\n"
        else:
            out += f"\t<{section}/>\n"
    return out + "</particlefile>\n"


def text(body):
    return body.replace("\n", "\r\n").encode("utf-8")


def wanted_files(folder="rings"):
    """Every file name and its bytes, for the game folder art/effects/<folder>/."""
    global FOLDER
    FOLDER = folder
    wanted = {}
    for name, colour in RINGS.items():
        wanted[f"ring_{name}.ddt"] = ddt(colour)
        wanted[f"ring_{name}.xml"] = text(xml(name))
        for _, size, radius, side in SHAPES:
            texture = f"ring_{name}_{size}" if side else f"ring_{name}"
            wanted[f"ring_{name}_{size}.particle"] = text(particle(texture, radius))
            if side:
                wanted[f"{texture}.ddt"] = ddt(colour, side, *building_shape(radius))
        if name in GLYPHS:
            wanted[f"aura_{name}.xml"] = text(xml(name, marker=True))
            wanted[f"icon_{name}.ddt"] = icon_ddt(colour, GLYPHS[name], GLYPH_ACCENTS.get(name, ()))
            for _, size, height in ICON_HEIGHTS:
                wanted[f"icon_{name}_{size}.particle"] = text(particle(f"icon_{name}", ICON_SIDE, height, 0, ground=False))
    for rank, colour in RANKS.items():
        name = f"rank_{rank}"
        glyph, stars, scale = rank_mark(rank)
        wanted[f"{name}.xml"] = text(xml("", logic=icon_logic(name)))
        if stars:
            # A larger sprite: twice the texels, so they stay as dense as the others', and an edge as thick.
            wanted[f"icon_{name}.ddt"] = icon_ddt((colour, colour), glyph, stars, SIZE * 2, ICON_OUTLINE / scale,
                                                  RANK_STAR_COLOUR)
        else:
            wanted[f"icon_{name}.ddt"] = icon_ddt((colour, colour), glyph)
        for _, size, height in ICON_HEIGHTS:
            wanted[f"icon_{name}_{size}.particle"] = text(particle(f"icon_{name}", RANK_SIDE * scale, height + RANK_LIFT, 0))
    for radius in RANGES:
        side = 256 if radius <= 16 else 512
        wanted[f"range_{radius}.ddt"] = ddt(RANGE_COLOURS, side, *range_shape(radius))
        wanted[f"range_{radius}.xml"] = text(xml("", logic=range_logic(radius)))
        wanted[f"range_{radius}.particle"] = text(particle(f"range_{radius}", radius / BANDS[0][1]))
    return wanted


def option(args, name, default):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            sys.exit(f"make_rings: {name} needs a value")
        return args[i + 1]
    return default


def main(argv):
    check = "--check" in argv
    out = pathlib.Path(option(argv, "--out", OUT))
    folder = option(argv, "--folder", "rings")
    if not folder or any(c in folder for c in "\\/:."):
        sys.exit("make_rings: --folder is one folder name under art/effects/")
    wanted = wanted_files(folder)
    bad = 0
    out.mkdir(parents=True, exist_ok=True)
    for name, data in wanted.items():
        path = out / name
        if check:
            if not path.exists() or path.read_bytes() != data:
                print(f"make_rings: {name} differs")
                bad += 1
        else:
            path.write_bytes(data)
    print(f"make_rings: {len(wanted)} files, {bad} differ" if check else f"make_rings: wrote {len(wanted)} files to {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
