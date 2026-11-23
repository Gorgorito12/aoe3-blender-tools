# SPDX-License-Identifier: GPL-3.0-or-later
"""Cartoon icons for the floating markers of make_rings.py: a tool or a food drawn from simple shapes, with flat
colours, one light tone per part and a thick dark outline, so it reads at a few dozen pixels over a unit.

Standard library only. Every shape is a signed distance (negative inside), in coordinates from -1 to 1 across the
icon, y growing downward. A part is painted as its outline (the shape grown by OUTLINE, dark), then its fill, then
its light tone (the fill's shape cut by a second shape). Parts are painted in order, so a later part's outline
separates it from the parts under it. Nothing is taken from the game: the shapes are drawn here.

    rgba = render("pickaxe", 128)     # a list of rows, each a list of (r, g, b, a)
"""
import math

OUTLINE = 0.075            # the dark edge, in the same units (about 5 texels of a 128-texel icon)
DARK = (28, 22, 18)

WOOD, WOOD_LIGHT = (176, 110, 52), (226, 164, 96)
STEEL, STEEL_LIGHT = (140, 152, 170), (228, 236, 246)
GOLD, GOLD_LIGHT = (246, 192, 30), (255, 242, 150)
MEAT, MEAT_LIGHT = (200, 70, 48), (246, 136, 104)
BONE, BONE_LIGHT = (236, 226, 200), (255, 252, 240)
BERRY, BERRY_LIGHT = (196, 28, 64), (255, 150, 170)
LEAF, LEAF_LIGHT = (70, 158, 52), (156, 216, 96)
WHEAT, WHEAT_LIGHT = (226, 174, 58), (255, 228, 140)
STALK = (190, 150, 60)
FISH, FISH_LIGHT = (72, 140, 196), (170, 214, 240)
WHITE = (250, 250, 250)
STRING = (236, 228, 206)


# -- shapes -----------------------------------------------------------------------------------------------------
class Shape:
    def __init__(self, distance, box):
        self.distance = distance  # (x, y) -> signed distance
        self.box = box            # (x0, y0, x1, y1) that holds every point inside

    def __or__(self, other):
        return Shape(lambda x, y: min(self.distance(x, y), other.distance(x, y)),
                     (min(self.box[0], other.box[0]), min(self.box[1], other.box[1]),
                      max(self.box[2], other.box[2]), max(self.box[3], other.box[3])))

    def __and__(self, other):
        return Shape(lambda x, y: max(self.distance(x, y), other.distance(x, y)),
                     (max(self.box[0], other.box[0]), max(self.box[1], other.box[1]),
                      min(self.box[2], other.box[2]), min(self.box[3], other.box[3])))


def circle(cx, cy, r):
    return Shape(lambda x, y: math.hypot(x - cx, y - cy) - r, (cx - r, cy - r, cx + r, cy + r))


def ellipse(cx, cy, rx, ry, angle=0.0):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def distance(x, y):  # the usual first-order estimate, close to the true distance near the edge
        u, v = (x - cx) * c + (y - cy) * s, -(x - cx) * s + (y - cy) * c
        k0 = math.hypot(u / rx, v / ry)
        k1 = math.hypot(u / (rx * rx), v / (ry * ry))
        if k1 < 1e-9:
            return -min(rx, ry)
        return k0 * (k0 - 1.0) / k1
    r = max(rx, ry)
    return Shape(distance, (cx - r, cy - r, cx + r, cy + r))


def capsule(ax, ay, bx, by, r):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy or 1e-9

    def distance(x, y):
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        return math.hypot(x - ax - t * dx, y - ay - t * dy) - r
    return Shape(distance, (min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r))


def polyline(points, r):
    shape = capsule(*points[0], *points[1], r)
    for a, b in zip(points[1:], points[2:]):
        shape = shape | capsule(*a, *b, r)
    return shape


def polygon(points):
    n = len(points)

    def distance(x, y):
        best, inside = float("inf"), False
        for i in range(n):
            ax, ay = points[i]
            bx, by = points[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1e-9)))
            best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
            if (ay > y) != (by > y) and x < ax + (y - ay) * dx / (by - ay):
                inside = not inside
        return -best if inside else best
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return Shape(distance, (min(xs), min(ys), max(xs), max(ys)))


def rounded(shape, r):
    """The shape grown by r: its corners round."""
    return Shape(lambda x, y: shape.distance(x, y) - r,
                 (shape.box[0] - r, shape.box[1] - r, shape.box[2] + r, shape.box[3] + r))


def rotate(points, angle, cx=0.0, cy=0.0):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


def along(a, b, t, side=0.0):
    """The point at t of the way from a to b, moved `side` to the left of that direction."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return (a[0] + dx * t - dy / n * side, a[1] + dy * t + dx / n * side)


# -- the icons ----------------------------------------------------------------------------------------------------
def pickaxe():
    """A pickaxe over a gold nugget: coin."""
    low, top = (-0.66, 0.72), (0.40, -0.40)
    d = (top[0] - low[0], top[1] - low[1])
    n = math.hypot(*d)
    d = (d[0] / n, d[1] / n)
    head_centre = (top[0] - d[0] * 0.04, top[1] - d[1] * 0.04)
    perp = (-d[1], d[0])
    upper, lower = [], []
    for i in range(21):
        t = -1.0 + i / 10.0
        cx = head_centre[0] + perp[0] * t * 0.80 - d[0] * 0.30 * t * t
        cy = head_centre[1] + perp[1] * t * 0.80 - d[1] * 0.30 * t * t
        w = 0.15 * (1.0 - t * t) ** 0.55 + 0.015
        upper.append((cx + d[0] * w, cy + d[1] * w))
        lower.append((cx - d[0] * w, cy - d[1] * w))
    head = polygon(upper + lower[::-1])
    shine = polygon(upper + [(p[0] - d[0] * 0.05, p[1] - d[1] * 0.05) for p in upper[::-1]])
    nugget = rounded(polygon([(0.20, 0.50), (0.44, 0.30), (0.74, 0.40), (0.80, 0.66), (0.56, 0.82), (0.28, 0.74)]), 0.05)
    return [
        (nugget, GOLD, circle(0.46, 0.46, 0.13)),
        (capsule(*low, *top, 0.085), WOOD, capsule(low[0] - 0.03, low[1] - 0.03, top[0] - 0.03, top[1] - 0.03, 0.03)),
        (head, STEEL, shine),
        (capsule(*along(head_centre, low, 0.05), *along(head_centre, low, 0.14), 0.11), STEEL, None),
    ]


def axe():
    """A felling axe: wood."""
    low, top = (-0.50, 0.78), (0.42, -0.62)
    h = along(top, low, 0.16)                       # where the head sits on the handle
    d = (top[0] - low[0], top[1] - low[1])
    n = math.hypot(*d)
    d = (d[0] / n, d[1] / n)
    left = (d[1], -d[0])                            # the blade's side
    def p(a, b):
        return (h[0] + d[0] * a + left[0] * b, h[1] + d[1] * a + left[1] * b)
    edge = [p(0.44 - 0.88 * i / 12, 0.80 + 0.10 * math.sin(math.pi * i / 12)) for i in range(13)]
    blade = polygon([p(0.14, 0.02), p(0.18, 0.34)] + edge + [p(-0.18, 0.34), p(-0.14, 0.02), p(-0.14, -0.16),
                                                            p(0.14, -0.16)])
    shine = polygon(edge + [p(-0.40, 0.66), p(0.40, 0.66)])
    return [
        (capsule(*low, *top, 0.09), WOOD, capsule(low[0] - 0.035, low[1] - 0.025, top[0] - 0.035, top[1] - 0.025, 0.03)),
        (rounded(blade, 0.03), STEEL, shine),
    ]


def drumstick():
    """A leg of meat on the bone: food."""
    return [
        (capsule(0.20, 0.20, 0.60, 0.60, 0.10) | circle(0.56, 0.76, 0.13) | circle(0.76, 0.56, 0.13), BONE,
         circle(0.52, 0.70, 0.05)),
        (ellipse(-0.16, -0.16, 0.66, 0.48, 45), MEAT, ellipse(-0.30, -0.34, 0.34, 0.16, 45)),
    ]


def bow():
    """A bow with an arrow on its string: hunting."""
    parts = []
    arc = [(-0.30 - 0.42 * math.cos(math.radians(a)), 0.86 * math.sin(math.radians(a))) for a in range(-90, 91, 10)]
    arc = rotate(arc, 45)
    string = rotate([(-0.30, -0.86), (-0.30, 0.86)], 45)
    shaft = rotate([(-0.42, 0.0), (0.56, 0.0)], 45)
    tip = rotate([(0.50, -0.17), (0.88, 0.0), (0.50, 0.17)], 45)
    feather = rotate([(-0.66, -0.15), (-0.40, -0.15), (-0.28, 0.0), (-0.40, 0.15), (-0.66, 0.15), (-0.56, 0.0)], 45)
    parts.append((polyline(arc, 0.085), WOOD, polyline([(x - 0.03, y - 0.03) for x, y in arc], 0.025)))
    parts.append((capsule(*string[0], *string[1], 0.022), STRING, None))
    parts.append((capsule(*shaft[0], *shaft[1], 0.045), WOOD, None))
    parts.append((rounded(polygon(feather), 0.02), (220, 60, 50), None))
    parts.append((rounded(polygon(tip), 0.02), STEEL, None))
    return parts


def berries():
    """A bunch of berries under two leaves: foraging."""
    leaves = [(ellipse(-0.22, -0.56, 0.36, 0.17, -25), LEAF, ellipse(-0.26, -0.62, 0.20, 0.06, -25)),
              (ellipse(0.24, -0.58, 0.36, 0.17, 30), LEAF, ellipse(0.22, -0.64, 0.20, 0.06, 30))]
    stem = [(capsule(0.0, -0.66, 0.0, -0.30, 0.05), STALK, None)]
    bunch = []
    for cx, cy in ((0.0, -0.12), (-0.36, 0.14), (0.36, 0.14), (0.0, 0.44), (-0.30, 0.56), (0.30, 0.56)):
        bunch.append((circle(cx, cy, 0.25), BERRY, circle(cx - 0.08, cy - 0.09, 0.07)))
    return stem + leaves + bunch


def wheat():
    """An ear of wheat on its stalk, with a leaf: farming."""
    base, tip = (0.52, 0.86), (-0.50, -0.70)
    parts = [(capsule(*base, *along(base, tip, 0.45), 0.05), STALK, None),
             (ellipse(*along(base, tip, 0.30, 0.20), 0.30, 0.08, -10), LEAF, None)]
    angle = math.degrees(math.atan2(tip[1] - base[1], tip[0] - base[0]))
    for i in range(5):
        t = 0.48 + i * 0.105
        for side in (-1, 1):
            cx, cy = along(base, tip, t, 0.13 * side)
            parts.append((ellipse(cx, cy, 0.16, 0.09, angle + 35 * side), WHEAT,
                          ellipse(cx - 0.02, cy - 0.03, 0.07, 0.03, angle + 35 * side)))
    cx, cy = along(base, tip, 1.02)
    parts.append((ellipse(cx, cy, 0.15, 0.09, angle), WHEAT, None))
    return parts


def fish():
    """A fish: fishing."""
    body = ellipse(-0.10, 0.02, 0.62, 0.36, -12)
    tail = rounded(polygon(rotate([(0.40, 0.0), (0.86, -0.38), (0.76, 0.0), (0.86, 0.38)], -12)), 0.03)
    fin = rounded(polygon(rotate([(-0.30, -0.30), (0.10, -0.52), (0.14, -0.28)], -12)), 0.02)
    return [
        (fin, FISH, None),
        (tail, FISH, None),
        (body, FISH, ellipse(-0.14, -0.14, 0.44, 0.10, -12)),
        (circle(-0.44, -0.08, 0.11), WHITE, None, 0.035),
        (circle(-0.46, -0.08, 0.055), DARK, None, 0.0),
    ]


ICONS = {"pickaxe": pickaxe, "axe": axe, "drumstick": drumstick, "bow": bow, "berries": berries, "wheat": wheat,
         "fish": fish}


FIT = 0.90  # the drawing, outline included, fills this much of the half width


def render(name, size=128):
    """The icon as size x size RGBA rows, its drawing scaled and centred to fill FIT of the texture. A transparent
    texel keeps the outline's colour, so the mip levels the game makes from it darken the edge rather than lighten
    it."""
    parts = ICONS[name]()
    canvas = [[[DARK[0], DARK[1], DARK[2], 0.0] for _ in range(size)] for _ in range(size)]
    boxes = [part[0].box for part in parts]
    x0, y0 = min(b[0] for b in boxes) - OUTLINE, min(b[1] for b in boxes) - OUTLINE
    x1, y1 = max(b[2] for b in boxes) + OUTLINE, max(b[3] for b in boxes) + OUTLINE
    scale = FIT * 2.0 / max(x1 - x0, y1 - y0)       # texture units per drawing unit
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    pixel = 2.0 / size / scale                      # one texel in drawing units

    def paint(shape, colour, grow=0.0):
        bx0, by0, bx1, by1 = shape.box
        margin = grow + pixel * 2
        half = size / 2.0
        i0 = max(0, int((bx0 - margin - mx) / pixel + half))
        i1 = min(size, int((bx1 + margin - mx) / pixel + half) + 1)
        j0 = max(0, int((by0 - margin - my) / pixel + half))
        j1 = min(size, int((by1 + margin - my) / pixel + half) + 1)
        for j in range(j0, j1):
            y = my + (j + 0.5 - half) * pixel
            row = canvas[j]
            for i in range(i0, i1):
                x = mx + (i + 0.5 - half) * pixel
                cover = 0.5 - (shape.distance(x, y) - grow) / pixel
                if cover <= 0.0:
                    continue
                cover = min(1.0, cover)
                texel = row[i]
                a = texel[3]
                out = cover + a * (1.0 - cover)
                for c in range(3):
                    texel[c] = (colour[c] * cover + texel[c] * a * (1.0 - cover)) / out
                texel[3] = out

    for part in parts:
        shape, colour, light = part[:3]
        outline = part[3] if len(part) > 3 else OUTLINE
        if outline > 0.0:
            paint(shape, DARK, outline)
        paint(shape, colour)
        if light is not None:
            paint(shape & light, tuple(min(255, int(c * 0.35 + l * 0.65)) for c, l in zip(colour, _light(colour))))
    return [[(round(t[0]), round(t[1]), round(t[2]), round(t[3] * 255)) for t in row] for row in canvas]


def _light(colour):
    for base, light in ((WOOD, WOOD_LIGHT), (STEEL, STEEL_LIGHT), (GOLD, GOLD_LIGHT), (MEAT, MEAT_LIGHT),
                        (BONE, BONE_LIGHT), (BERRY, BERRY_LIGHT), (LEAF, LEAF_LIGHT), (WHEAT, WHEAT_LIGHT),
                        (FISH, FISH_LIGHT)):
        if colour == base:
            return light
    return tuple(min(255, c + 60) for c in colour)
