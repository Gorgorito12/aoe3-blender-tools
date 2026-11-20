# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws coloured ground rings, floating icons, rank marks and range rings for the game's effects folder.

    python -I tools/make_rings.py [--out <folder>] [--folder <name>]          writes every file
    python -I tools/make_rings.py [--out <folder>] [--folder <name>] --check  exit code 1 if a file in <folder>
                                                                              differs from what it would write
    python -I tools/make_rings.py ... --rank-shapes <folder>  the rank marks from drawn images instead of the knots:
                                                              rank_1.png .. rank_5.png (RGBA) and shapes.json
                                                              {"pixels_per_unit": N}, placed by the same rules (needs
                                                              numpy)
    python -I tools/make_rings.py ... --sheet <marks.png>     also a picture of the five rank marks, enlarged 4 times,
                                                              on grass and on dark (needs numpy)

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
- rank_<1-5>.xml, a rank mark floating over the unit: a soutache knot (one loop; a stem with a top loop and two or
  four eye-shaped loops over a tail bar), shaded as polished metal, centred on the unit's HP bar.

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
    ("abstractelephant", "elephant", 7.0),  # a mod's type (Wars of Liberty): elephants carry their bar far higher
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
# Rank marks: soutache knots, the braid of a hussar's uniform, floating over the unit with no ring, drawn after the
# reference sheet the Wars of Liberty team approved (2026-11-20): rank 1 one tall loop like a cursive "l", the cord
# crossing itself near the bottom and both tails sweeping out left and right, in copper-bronze; rank 2 a round top loop
# on a straight central stem, two horizontal eye-shaped (almond) loops on the stem and a tail bar under them whose ends
# curve up, in silver; rank 3 the same with a pointed (flame) top loop, in gold; rank 4 the round top loop and four eye
# loops in two tiers on the stem, in gold; rank 5 the same with the pointed top loop, in gold. A thick cord with a dark
# border, shaded as polished metal: its light tone along the top-left side of each strand, its dark tone underneath.
# Coordinates are in glyph units (RANK_SIDE metres each, about 150 pixels of the reference sheet); y grows downward.
# In the texture a smaller y is higher on screen.
#
# Rule: a mark over a unit is horizontally CENTRED on the unit's HP bar, symmetric over it, never nearer one end. The
# glyph is symmetric and centred on the texture's vertical centre line (tested). The game draws the bar at the unit's
# HITPOINTBAR tag, and a particle hangs at the unit's position, at a height over the ground; seen in perspective, a
# point higher than the bar drifts sideways from it, away from the middle of the screen (measured: about 1 % of the
# unit's distance from the screen's centre per 2 m, so 5 to 7 px at the screen's sides). So the sprite's centre is put
# at the bar's own height (RANK_BAR_HEIGHTS, by kind of unit), where nothing drifts, and the knot is drawn high in the
# sprite: a sprite faces the camera, so a shift inside it moves the knot straight up on screen. Every knot's tails sit
# RANK_TAIL_LIFT above the sprite's centre, so all ranks keep the same gap to the bar; bar and mark scale alike with the
# camera's zoom. A rank whose knot is larger gets a larger sprite.
# The tones (dark, base, light) of each metal, sampled from the reference sheet.
RANK_TONES = {
    "bronze": ((172, 93, 22), (218, 130, 40), (250, 200, 150)),
    "silver": ((122, 134, 160), (179, 185, 203), (240, 242, 250)),
    "gold": ((190, 128, 18), (250, 178, 29), (255, 236, 160)),
}
RANK_METALS = {1: "bronze", 2: "silver", 3: "gold", 4: "gold", 5: "gold"}
RANKS = {rank: RANK_TONES[metal][1] for rank, metal in RANK_METALS.items()}  # each rank's base colour
RANK_KNOTS = {1: "loop", 2: "trefoil", 3: "eyes", 4: "five", 5: "fiveeyes"}
RANK_OUTLINE_COLOUR = (27, 13, 0)
KNOT_WIDTH = 0.096  # the cord's half width, in glyph units (the reference's thick cord)
KNOT_OUTLINE = 0.055  # its dark border
KNOT_REACH = 0.98  # how far from the sprite's centre a mark may reach, its border included
SHINE = (1.5, 0.15)  # how much the place across a strand (top left light) and on the whole mark pick the tone
RANK_SIDE = 0.75  # metres of a glyph unit
RANK_TAIL_LIFT = 1.2  # glyph units from the sprite's centre (the bar) up to the tails: about 0.9 m
RANK_TEXTURE = 256
RANK_MIPS = 3  # 256, 128 and 64 texels: smaller levels blur the thin cord and border into the ground
RANK_SHAPE_TEXTURE = 512  # a drawn mark (--rank-shapes) keeps more of its drawing: 512 to 64 texels, four levels
# The HP bar's height over the ground, by ICON_HEIGHTS' kinds (the game's HITPOINTBAR tags: a Hussar's idle tag is at
# 4.07..4.15 m; infantry measured at about 2.9 m); the kinds a unit with a rank never is keep the aura icons' heights.
RANK_BAR_HEIGHTS = {"unit": 2.9, "cavalry": 4.1, "elephant": 5.1}


def rank_mark(rank):
    """The glyph in its texture's coordinates and the sprite's size in glyph units (RANK_SIDE m each): the knot moved
    up so that its tails sit RANK_TAIL_LIFT over the sprite's centre, the sprite just large enough to hold it."""
    glyph = knot(RANK_KNOTS[rank])
    shift = max(y + outer for _, y, outer, _ in glyph) + RANK_TAIL_LIFT  # the tails' lowest point to -RANK_TAIL_LIFT
    reach = max(max(abs(x), abs(y - shift)) + outer for x, y, outer, _ in glyph) + KNOT_OUTLINE
    scale = reach / KNOT_REACH
    return tuple((x / scale, (y - shift) / scale, outer / scale, inner / scale) for x, y, outer, inner in glyph), scale


def bezier(p0, p1, p2, p3, step=0.02):
    """Points along a cubic Bezier curve, about `step` apart (the last point is left to the next piece)."""
    length = sum(math.dist(a, b) for a, b in ((p0, p1), (p1, p2), (p2, p3)))
    n = max(4, math.ceil(length / step))
    out = []
    for i in range(n):
        t = i / n
        s = 1 - t
        out.append(tuple(s ** 3 * a + 3 * s * s * t * b + 3 * s * t * t * c + t ** 3 * d
                         for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def mirrored(points):
    """The same points, mirrored left to right: every knot is symmetric."""
    return [(-x, y) for x, y in points]


def knot_loop(root, angle, length, width, eye, lean=0.0):
    """A loop of the cord that leaves `root` and comes back to it, its far end `length` away at `angle` (radians,
    0 to the right, -pi/2 up); about 0.82 `width` is half its breadth. A round loop has a round far end; an eye-shaped
    one is two arcs that meet in a point at both ends, like the outline of an eye. `lean` makes the half on the
    `angle` + 90 degrees side that much flatter and the other that much fuller (a horizontal eye fuller on top)."""
    d = (math.cos(angle), math.sin(angle))
    n = (-d[1], d[0])
    at = lambda a, b: (root[0] + a * d[0] + b * n[0], root[1] + a * d[1] + b * n[1])
    tip = at(length, 0.0)
    if eye:
        controls = [(0.28 * length, 1.15 * width), (0.72 * length, 1.05 * width)]
    else:
        controls = [(0.30 * length, 1.25 * width), (length, 0.95 * width)]
    (a1, b1), (a2, b2) = controls
    points = bezier(root, at(a1, b1 * (1 - lean)), at(a2, b2 * (1 - lean)), tip)
    points += bezier(tip, at(a2, -b2 * (1 + lean)), at(a1, -b1 * (1 + lean)), root)
    return points


def _back(point, root, d, n):
    """The (along, across) of a control point mirrored across the loop's axis: the loop's other half."""
    vx, vy = point[0] - root[0], point[1] - root[1]
    return vx * d[0] + vy * d[1], -(vx * n[0] + vy * n[1])


# Every knot's shape, in glyph units (y down, from the tail bar's centre line). "loop": the crossing's height, the
# loop's length and width, the tail's end (x, y) and its two control points. The others: the top loop (its root's
# height, length, width, eye-shaped or round), the tiers of side loops (height, length, width, rise in degrees), and
# the tail bar (half length, how far its ends curve up, the height of its two control points). Fitted to the reference
# sheet the Wars of Liberty team approved, by the overlap of the silhouettes.
KNOT_SHAPES = {
    "loop": {"cross": -0.201, "length": 1.142, "width": 0.403, "end": (0.699, -0.124), "c1": (0.024, -0.168),
             "c2": (0.472, 0.049)},
    "trefoil": {"top": (-0.855, 0.53, 0.29, False), "tiers": ((-0.452, 0.82, 0.256, -9.25, 0.25),),
                "bar": (0.753, 0.055, 0.003)},
    "eyes": {"top": (-0.772, 0.625, 0.28, True), "tiers": ((-0.479, 0.81, 0.25, -13.5, 0.25),),
             "bar": (0.716, 0.055, -0.002)},
    "five": {"top": (-1.39, 0.5, 0.3, False), "tiers": ((-1.032, 0.79, 0.236, -6.0, 0.25), (-0.409, 0.79, 0.239, -7.5, 0.25)),
             "bar": (0.756, 0.126, 0.001)},
    "fiveeyes": {"top": (-1.295, 0.605, 0.271, True),
                 "tiers": ((-1.045, 0.81, 0.212, -7.625, 0.25), (-0.425, 0.82, 0.232, -11.0, 0.25)),
                 "bar": (0.763, 0.105, 0.007)},
}


def tail_bar(half, rise, sag):
    """The tail bar under the stem: flat, its ends curving up."""
    piece = bezier((0.0, 0.0), (0.53 * half, sag), (0.85 * half, sag + 0.01), (half, -rise))
    piece.append((half, -rise))
    return piece + mirrored(piece)


def stem(top):
    return bezier((0.0, top), (0.0, top), (0.0, 0.0), (0.0, 0.0), 0.03)


def side_pair(y, length, width, rise, lean=0.0, eye=True):
    """Two side loops on the stem at height y, pointing out left and right, their axis `rise` degrees up (below the
    horizontal when negative), their upper half `lean` fuller than the lower; eye-shaped (pointed) or round-ended."""
    right = knot_loop((0.0, y), math.radians(-rise), length, width, eye, lean)
    return right + mirrored(right)


def ring_loop(root, diameter):
    """A full round ring standing on `root`: the cord leaves the stem's top and goes round."""
    r = diameter / 2
    n = max(24, math.ceil(2 * math.pi * r / 0.02))
    return [(r * math.sin(2 * math.pi * i / n), root - r + r * math.cos(2 * math.pi * i / n)) for i in range(n)]


def knot_points(kind, shape):
    """The cord's centre line of a knot of `kind` drawn from `shape` (an entry of KNOT_SHAPES)."""
    if kind == "loop":
        cross = (0.0, shape["cross"])
        points = knot_loop(cross, -math.pi / 2, shape["length"], shape["width"], False)
        (ex, ey), (ax, ay), (bx, by) = shape["end"], shape["c1"], shape["c2"]
        tail = bezier(cross, (-ax, ay), (-bx, by), (-ex, ey))  # down to the left, then out
        tail.append((-ex, ey))
        return points + tail + mirrored(tail)
    root, length, width, eye = shape["top"]
    top = knot_loop((0.0, root), -math.pi / 2, length, width, True) if eye else ring_loop(root, length)
    points = top + stem(root)
    for tier in shape["tiers"]:  # (y, length, width, rise[, lean]): eye-shaped beside a pointed top, round beside a ring
        points += side_pair(*tier, eye=eye)
    return points + tail_bar(*shape["bar"])


@functools.lru_cache(maxsize=None)
def knot(kind):
    """The circles of a rank's soutache knot: "loop" (rank 1), "trefoil" (2), "eyes" (3), "five" (4), "fiveeyes" (5)."""
    return tuple((x, y, KNOT_WIDTH, 0.0) for x, y in knot_points(kind, KNOT_SHAPES[kind]))


def _grid(glyph, grow, cell=0.25):
    """The circles of a glyph by grid cell (any cell their grown disc reaches), to test a point against few."""
    cells = {}
    for c in glyph:
        x, y, outer, _ = c
        r = outer + grow
        for gx in range(math.floor((x - r) / cell), math.floor((x + r) / cell) + 1):
            for gy in range(math.floor((y - r) / cell), math.floor((y + r) / cell) + 1):
                cells.setdefault((gx, gy), []).append(c)
    return lambda u, v: cells.get((math.floor(u / cell), math.floor(v / cell)), ())


def rank_texels(size, tones, glyph, outline):
    """RGBA rows of a rank mark: alpha from four samples per texel side (the cord grown by its border), and inside the
    cord the colour shaded as polished metal; the border dark."""
    near = _grid(glyph, outline)
    samples = 4
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            total = core = 0
            pool = set()
            for sy in range(samples):
                for sx in range(samples):
                    u = (x + (sx + 0.5) / samples) / size * 2 - 1
                    v = (y + (sy + 0.5) / samples) / size * 2 - 1
                    cand = near(u, v)
                    total += glyph_cover(u, v, cand, outline) > 0
                    hit = glyph_cover(u, v, cand, 0.0) > 0
                    core += hit
                    if hit:
                        pool.update(cand)
            alpha = round(total / samples ** 2 * 15)
            if core == 0:
                row.append((RANK_OUTLINE_COLOUR, alpha))
                continue
            share = core / samples ** 2  # how much of the texel is cord: the rest is its dark border
            u, v = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
            # across the strand: from the line through the two nearest centres (the strand's direction there), so
            # that the shading follows the cord, not each circle
            ranked = sorted(pool, key=lambda c: math.hypot(u - c[0], v - c[1]))
            first, second = ranked[0], ranked[min(1, len(ranked) - 1)]
            tx, ty = second[0] - first[0], second[1] - first[1]
            length = math.hypot(tx, ty) or 1.0
            tx, ty = tx / length, ty / length
            ox, oy = u - first[0], v - first[1]
            along = ox * tx + oy * ty
            nx, ny = (ox - along * tx) / first[2], (oy - along * ty) / first[2]
            across = max(-1.0, min(1.0, -(0.3 * nx + ny) / 1.044))  # 1 on the strand's upper edge (a little left)
            whole = -(u + v) / 2  # 1 at the sprite's top left
            s = max(-1.0, min(1.0, SHINE[0] * across + SHINE[1] * whole))
            dark, base, light = tones
            if s >= 0:  # toward the light tone, its brightest only near the top-left edge
                rgb = [b + (l - b) * s for b, l in zip(base, light)]
            else:
                rgb = [b + (d - b) * -s for b, d in zip(base, dark)]
            rgb = [c * share + o * (1 - share) for c, o in zip(rgb, RANK_OUTLINE_COLOUR)]
            row.append((tuple(round(c) for c in rgb), alpha))
        out.append(row)
    return out


def _unpack565(c):
    r, g, b = c >> 11 & 31, c >> 5 & 63, c & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def rank_block(texels):
    """One DXT3 block from 16 (rgb, alpha) texels: the lightest and darkest shown colours as its two ends, every texel
    the nearest of the four colours between them (DXT3 always has four)."""
    shown = [rgb for rgb, a in texels if a > 0] or [RANK_OUTLINE_COLOUR]
    luma = lambda c: 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    c0, c1 = rgb565(max(shown, key=luma)), rgb565(min(shown, key=luma))
    if c0 < c1:
        c0, c1 = c1, c0
    p0, p1 = _unpack565(c0), _unpack565(c1)
    palette = [p0, p1, tuple((2 * a + b) / 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) / 3 for a, b in zip(p0, p1))]
    out = bytearray()
    indices = 0
    for i, (rgb, a) in enumerate(texels):
        if i % 4 == 0:
            row = 0
        row |= a << (4 * (i % 4))
        if i % 4 == 3:
            out += struct.pack("<H", row)
        best = min(range(4), key=lambda j: sum((p - q) ** 2 for p, q in zip(palette[j], rgb)))
        indices |= best << (2 * i)
    return bytes(out) + struct.pack("<HHI", c0, c1, indices)


def _rank_level(texels):
    """The DXT3 bytes of one level: with numpy, the toolkit's encoder, which fits each block's two colours to all its
    texels (smooth shading, no stray light texels); without it, rank_block's lightest-and-darkest fit."""
    try:
        import numpy as np
        sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
        from aoe3game import ddt as ddtfile
    except ImportError:
        out = bytearray()
        side = len(texels)
        for by in range(0, side, 4):
            for bx in range(0, side, 4):
                out += rank_block([texels[by + y][bx + x] for y in range(4) for x in range(4)])
        return bytes(out)
    rgba = np.array([[(*rgb, round(a * 255 / 15)) for rgb, a in row] for row in texels], np.uint8)
    return ddtfile.compress(rgba, ddtfile.DXT3, refine=True)


RANK_SHAPES = None  # set by --rank-shapes: a folder of drawn marks, rank_1.png .. rank_5.png and shapes.json


def _rank_image(rank):
    """A drawn mark (--rank-shapes): its RGBA pixels, premultiplied as floats, and its pixels per glyph unit."""
    import json
    import numpy as np
    sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
    from core.pngio import read_png
    folder = pathlib.Path(RANK_SHAPES)
    unit = json.loads((folder / "shapes.json").read_text(encoding="utf-8"))["pixels_per_unit"]
    px = read_png((folder / f"rank_{rank}.png").read_bytes()).astype(np.float64)
    if px.shape[2] != 4:
        raise ValueError(f"rank_{rank}.png: RGBA expected")
    a = px[..., 3:4] / 255
    return np.concatenate([px[..., :3] * a, a], axis=2), float(unit)


def rank_scale(rank):
    """The size of rank's sprite against RANK_SIDE, from its knot or its drawn mark."""
    if RANK_SHAPES is None:
        return rank_mark(rank)[1]
    return _image_placement(rank)[0]


@functools.lru_cache(maxsize=None)
def _image_placement(rank):
    """A drawn mark's sprite scale and where it goes: the same rules as the knots (its lowest shown pixel
    RANK_TAIL_LIFT glyph units over the sprite's centre, its bounding box centred, the sprite just large enough)."""
    import numpy as np
    img, unit = _rank_image(rank)
    alpha = img[..., 3]
    rows = np.nonzero(alpha.max(axis=1) > 0)[0]
    cols = np.nonzero(alpha.max(axis=0) > 0)[0]
    width = (cols[-1] + 1 - cols[0]) / unit
    height = (rows[-1] + 1 - rows[0]) / unit
    reach = max(width / 2, RANK_TAIL_LIFT + height)
    return reach / KNOT_REACH, rows[0], rows[-1] + 1, cols[0], cols[-1] + 1, unit


def _image_level(rank, side):
    """One level of a drawn mark's texture: the mark area-resampled into a side x side sprite."""
    import numpy as np
    img, _ = _rank_image(rank)
    scale, top, bottom, left, right, unit = _image_placement(rank)
    mark = img[top:bottom, left:right]
    texel = 2 * scale / side  # glyph units a texel
    # where the mark lands, in texels: centred, its bottom RANK_TAIL_LIFT over the centre
    x0 = side / 2 - (right - left) / unit / texel / 2
    y1 = side / 2 - RANK_TAIL_LIFT / texel
    y0 = y1 - (bottom - top) / unit / texel
    out = np.zeros((side, side, 4))
    k = (bottom - top) / (y1 - y0)  # mark pixels a texel
    ys = (np.arange(side + 1) - y0) * k
    xs = (np.arange(side + 1) - x0) * k
    # box filter: the sum of the mark over each texel's footprint, from a summed-area table
    sat = np.zeros((mark.shape[0] + 1, mark.shape[1] + 1, 4))
    sat[1:, 1:] = mark.cumsum(0).cumsum(1)

    def area(yy, xx):
        yy = np.clip(yy, 0, mark.shape[0])
        xx = np.clip(xx, 0, mark.shape[1])
        y_lo, x_lo = np.floor(yy).astype(int), np.floor(xx).astype(int)
        y_hi, x_hi = np.minimum(y_lo + 1, mark.shape[0]), np.minimum(x_lo + 1, mark.shape[1])
        fy, fx = (yy - y_lo)[:, None, None], (xx - x_lo)[None, :, None]
        s = sat
        top_ = s[y_lo][:, x_lo] * (1 - fx) + s[y_lo][:, x_hi] * fx
        bot_ = s[y_hi][:, x_lo] * (1 - fx) + s[y_hi][:, x_hi] * fx
        return top_ * (1 - fy) + bot_ * fy
    total = area(ys, xs)
    cell = total[1:, 1:] - total[:-1, 1:] - total[1:, :-1] + total[:-1, :-1]
    out = cell / (k * k)
    a = np.clip(out[..., 3], 0, 1)
    rgb = np.where(a[..., None] > 0, out[..., :3] / np.maximum(a[..., None], 1e-6), 0)
    return np.dstack([np.clip(rgb, 0, 255), a * 255]).round().astype(np.uint8)


@functools.lru_cache(maxsize=None)  # the textures do not depend on --folder
def rank_ddt(rank):
    """The DXT3 texture of a rank's mark, with its mips down to 4x4 (ranks 4 and 5 at twice the texels, so their
    cord keeps as many texels as the others')."""
    size = RANK_TEXTURE
    mips = RANK_MIPS
    if RANK_SHAPES is not None:
        size, mips = RANK_SHAPE_TEXTURE, 4
        sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
        from aoe3game import ddt as ddtfile
        levels = [ddtfile.compress(_image_level(rank, size >> i), ddtfile.DXT3, refine=True) for i in range(mips)]
        out = b"RTS3" + bytes((0, 1, 8, mips)) + struct.pack("<II", size, size)
        offset = len(out) + 8 * mips
        for level in levels:
            out += struct.pack("<II", offset, len(level))
            offset += len(level)
        return out + b"".join(levels)
    glyph, scale = rank_mark(rank)
    levels = []
    for i in range(mips):
        side = size >> i
        texels = rank_texels(side, RANK_TONES[RANK_METALS[rank]], glyph, KNOT_OUTLINE / scale)
        levels.append(_rank_level(texels))
    out = b"RTS3" + bytes((0, 1, 8, mips)) + struct.pack("<II", size, size)
    offset = len(out) + 8 * mips
    for level in levels:
        out += struct.pack("<II", offset, len(level))
        offset += len(level)
    return out + b"".join(levels)


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
        scale = rank_scale(rank)
        wanted[f"{name}.xml"] = text(xml("", logic=icon_logic(name)))
        wanted[f"icon_{name}.ddt"] = rank_ddt(rank)
        for _, size, height in ICON_HEIGHTS:
            wanted[f"icon_{name}_{size}.particle"] = text(particle(f"icon_{name}", RANK_SIDE * scale,
                                                                   RANK_BAR_HEIGHTS.get(size, height), 0))
    for radius in RANGES:
        side = 256 if radius <= 16 else 512
        wanted[f"range_{radius}.ddt"] = ddt(RANGE_COLOURS, side, *range_shape(radius))
        wanted[f"range_{radius}.xml"] = text(xml("", logic=range_logic(radius)))
        wanted[f"range_{radius}.particle"] = text(particle(f"range_{radius}", radius / BANDS[0][1]))
    return wanted


SHEET_GROUNDS = ((96, 112, 58), (40, 32, 24))  # grass, and the dark of the panel


def rank_sheet(wanted, zoom=4):
    """RGB rows (numpy) of the five rank marks at `zoom` times the size of rank 1's first 64-texel knot (SIZE / 2
    texels a glyph unit), each cut to its knot and standing on the same baseline (their tails), as their sizes are in
    the game, on grass and on a dark ground."""
    import numpy as np
    sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
    from aoe3game import ddt as ddtfile

    unit = SIZE // 2 * zoom  # pixels a glyph unit
    cells, height = [], 0
    for rank in RANKS:
        px = np.asarray(ddtfile.decode(wanted[f"icon_rank_{rank}.ddt"])).astype(np.float32)
        scale = rank_scale(rank)
        side = round(unit * 2 * scale)
        pos = np.clip((np.arange(side) + 0.5) * px.shape[0] / side - 0.5, 0, px.shape[0] - 1)
        lo = np.floor(pos).astype(int)
        hi = np.minimum(lo + 1, px.shape[0] - 1)
        f = (pos - lo)[:, None, None]
        rows = px[lo] * (1 - f) + px[hi] * f
        g = (pos - lo)[None, :, None]
        big = rows[:, lo] * (1 - g) + rows[:, hi] * g
        shown = np.nonzero(big[..., 3].max(axis=1) > 0)[0]
        cols = np.nonzero(big[..., 3].max(axis=0) > 0)[0]
        cut = big[shown.min():shown.max() + 1, cols.min():cols.max() + 1]
        cells.append(cut)
        height = max(height, cut.shape[0])
    width = max(c.shape[1] for c in cells) + unit // 2
    rows = []
    for ground in SHEET_GROUNDS:
        row = np.zeros((height + unit // 2, width * len(cells), 3), np.float32) + np.array(ground, np.float32)
        for i, cut in enumerate(cells):
            h, w = cut.shape[:2]
            top, left = height + unit // 4 - h, i * width + (width - w) // 2
            a = cut[..., 3:4] / 255.0
            area = row[top:top + h, left:left + w]
            row[top:top + h, left:left + w] = cut[..., :3] * a + area * (1 - a)
        rows.append(row)
    return np.concatenate(rows, axis=0).astype(np.uint8)


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
    global RANK_SHAPES
    RANK_SHAPES = option(argv, "--rank-shapes", None)
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
    sheet = option(argv, "--sheet", None)
    if sheet:
        sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
        from core.pngio import encode_png
        pathlib.Path(sheet).write_bytes(encode_png(rank_sheet(wanted)))
        print(f"make_rings: rank marks x4 in {sheet}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
