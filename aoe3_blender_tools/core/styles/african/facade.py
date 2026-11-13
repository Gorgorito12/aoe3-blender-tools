# SPDX-License-Identifier: GPL-3.0-or-later
"""Each wall of a building gets its own face, painted: what a real model would be too dear to model.
The game's buildings do this: their windows, niches and repairs are in the texture, not the mesh.

`plan` decides what goes on one wall, from its size, its name, the building's seed and what the
building is for, so no two walls are the same and the same wall always comes out the same; it keeps
off the openings the geometry has. `draw` paints a plan with a false depth: each hollow has a shadow
under its lintel and a lit sill, so it reads as a hole from the game's camera. Sizes are large
enough to last down the mipmaps."""
import math
import random
import zlib

from ...painter import _shade

DARK = (30, 23, 18)
CREAM = (222, 206, 174)  # the pale lime of frames and steps
# what a wall can show, as themes: a wall takes one, so walls differ in character and not only in place
THEMES = {
    "adobe": (("window", "window", "patch"), ("slit", "slit", "vents"), ("niche", "patch", "niche"),
              ("vents", "bricks", "window"), ("window", "niche", "bricks")),
    "kept": (("window",), ("window", "slit"), ("niche", "window"), ("slit", "window")),
    "mud": (("patch", "bricks"), ("niche", "patch"), ("vents", "patch"), ("bricks", "niche")),
    "round": (("niche", "patch"), ("patch", "bricks"), ("niche", "bricks"), ("patch",)),
}
# what a building's use leaves on its walls
USE = {"ARMORY": ("shield", "soot", "spears"), "WAR_CAMP": ("shield", "spears"), "STOCKADE": ("shield",),
       "MARKET": ("hanging", "hanging"), "CUSTOMS": ("tally", "hanging"), "GRANARY": ("tally", "tally"),
       "HOUSE": ("gourds",), "TOWN_CENTER": ("crest", "hanging"),
       "QUARRY": ("tally", "soot"), "DEPOT": ("tally", "soot"), "DOCK": ("hanging", "gourds")}
SIZES = {"window": (0.6, 0.85), "slit": (0.2, 0.8), "vents": (1.0, 0.25), "niche": (0.6, 0.9), "patch": (1.0, 0.9),
         "bricks": (0.9, 0.7), "shield": (0.55, 0.8), "spears": (0.5, 1.5), "soot": (1.0, 1.2), "hanging": (0.6, 1.0),
         "tally": (0.7, 0.4), "gourds": (0.6, 0.5), "crest": (0.7, 0.8)}
HIGH = ("vents",)        # up under the roof
LOW = ("soot",)          # from the ground


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def plan(seed, region, w, h, kind, use, avoid=()):
    """[(motif, u, v)] for one wall of w x h metres. `kind`: "adobe", "mud" or "round"; `use`: the
    building type; `avoid`: (u0, u1) spans taken by openings."""
    rng = random.Random(zlib.crc32(f"{seed}/{region}".encode()))
    theme = list(rng.choice(THEMES[kind]))
    rng.shuffle(theme)
    if USE.get(use) and rng.random() < 0.8:               # most walls show what the building is for
        theme.insert(0, rng.choice(USE[use]))
    n = max(1, int(w / 1.4))
    slots = [w * (k + 0.5) / n + rng.uniform(-0.15, 0.15) for k in range(n)]
    rng.shuffle(slots)
    out = []
    used = []
    for k, u in enumerate(slots):
        name = theme[k % len(theme)]
        sw, sh = SIZES[name]
        if sh > h - 1.0 or u - sw / 2 < 0.15 or u + sw / 2 > w - 0.15:
            continue
        if any(u + sw / 2 + 0.15 > a and u - sw / 2 - 0.15 < b for a, b in list(avoid) + used):
            continue
        if name in HIGH:
            v = h - sh - 0.55
        elif name in LOW:
            v = 0.15
        else:
            v = min(h - sh - 0.5, rng.uniform(0.9, 1.6))
        out.append((name, round(u, 3), round(v, 3)))
        used.append((u - sw / 2, u + sw / 2))
    return out


def hollow(pr, region, u0, v0, u1, v1, wall):
    """A hole in the wall: dark inside, its top in shadow, a lit sill below it."""
    pr.tone(region, u0 - 0.06, v1, u1 + 0.06, v1 + 0.07, 0.72)
    pr.tone(region, u0 - 0.06, v0 - 0.08, u1 + 0.06, v0, 1.16)
    pr.rect(region, u0, v0, u1, v1, DARK)
    pr.tone(region, u0, v0, u1, v0 + (v1 - v0) * 0.3, 1.6)


def draw(pr, region, motifs, wall, wood, band):
    """Paints a plan on a wall of colour `wall`."""
    lw = pr.lw
    rng = random.Random(zlib.crc32(region.encode()))
    for name, u, v in motifs:
        sw, sh = SIZES[name]
        u0, u1, v1 = u - sw / 2, u + sw / 2, v + sh
        if name == "window":
            hollow(pr, region, u0 + 0.1, v, u1 - 0.1, v1 - 0.1, wall)
            pr.rect(region, u0, v1 - 0.1, u1, v1, wood, _shade(wood, 0.6))            # the lintel
            pr.rect(region, u0 + 0.1, v, u0 + 0.2, v1 - 0.1, _shade(wood, 0.85))      # a shutter ajar
        elif name == "slit":
            hollow(pr, region, u0 + 0.04, v, u1 - 0.04, v1, wall)
        elif name == "vents":
            k = max(3, int(sw / 0.24))
            for j in range(k):
                a = u0 + sw * (j + 0.2) / k
                hollow(pr, region, a, v, a + 0.12, v + sh * 0.8, wall)
        elif name == "niche":
            pr.tone(region, u0, v, u1, v1 - sw / 2, 0.74)
            cx, cy = pr.P(region, u, v1 - sw / 2)
            pr.cv.ellipse(cx, cy, sw / 2 * pr.px_per_m, sw / 2 * pr.px_per_m, _shade(wall, 0.74), upper_half=True)
            pr.tone(region, u0 - 0.05, v - 0.07, u1 + 0.05, v, 1.14)
            pr.rect(region, u - 0.09, v, u + 0.09, v + 0.24, (150, 82, 50))          # a pot in it
        elif name == "patch":                                 # a repair of fresher plaster
            k = 1.1 + rng.uniform(0.0, 0.08)
            for j in range(3):
                d = 0.1 * j
                pr.tone(region, u0 + d, v + d, u1 - d, v1 - d, 1 + (k - 1) / 3)
        elif name == "bricks":                                # where the plaster fell off the bricks
            pr.rect(region, u0, v, u1, v1, _shade(wall, 0.64))
            vv, row = v, 0
            while vv < v1:
                uu = u0 - (row % 2) * 0.12
                while uu < u1:
                    a, c = max(u0, uu + 0.015), min(u1, uu + 0.215)
                    if c > a:
                        pr.rect(region, a, vv + 0.015, c, min(v1, vv + 0.105), _shade(wall, rng.uniform(0.74, 0.98)))
                    uu += 0.24
                vv += 0.12
                row += 1
        elif name == "shield":                                # hung on a peg
            cx, cy = pr.P(region, u, v + sh / 2)
            pr.cv.ellipse(cx, cy, sw / 2 * pr.px_per_m, sh / 2 * pr.px_per_m, (44, 32, 24))
            pr.cv.ellipse(cx, cy, (sw / 2 - 0.05) * pr.px_per_m, (sh / 2 - 0.05) * pr.px_per_m, (176, 146, 104))
            pr.rect(region, u - 0.05, v + 0.06, u + 0.05, v1 - 0.06, band)
            pr.mark(region, u - 0.05, v + 0.06, u + 0.05, v1 - 0.06)
        elif name == "spears":
            for j in range(3):
                a = u0 + 0.08 + 0.17 * j
                pr.rect(region, a, v, a + 0.03, v1 - 0.2, wood)
                pr.rect(region, a - 0.02, v1 - 0.2, a + 0.05, v1, (70, 68, 72))
        elif name == "soot":                                  # black from the smoke above a hearth
            for j in range(4):
                d = 0.12 * j
                pr.tone(region, u0 + d, v, u1 - d, v1 + 0.5 - d, 0.84)
        elif name == "hanging":                               # a cloth on a peg
            pr.rect(region, u0, v, u1, v1, _shade(band, 0.92))
            pr.mark(region, u0, v, u1, v1)
            for j in range(3):
                a = u0 + sw * (j + 0.5) / 3
                pr.rect(region, a - 0.03, v, a + 0.03, v1, (196, 176, 138))
            pr.rect(region, u0 - 0.08, v1 - 0.03, u1 + 0.08, v1 + 0.03, wood)
        elif name == "tally":                                 # a keeper's marks in the wet mud
            for j in range(int(sw / 0.09)):
                a = u0 + j * 0.09
                pr.vline(region, a, v, v + sh * (0.7 if j % 5 else 1.0), _shade(wall, 0.55), lw)
        elif name == "gourds":
            for j in range(2):
                cx, cy = pr.P(region, u0 + 0.15 + 0.3 * j, v + 0.2)
                r = 0.13 * pr.px_per_m
                pr.cv.ellipse(cx, cy, r, r * 1.2, (160, 118, 58))
        elif name == "crest":                                 # the owner's sign, in relief
            cx, cy = pr.P(region, u, v + sh / 2)
            a, c = sw / 2 * pr.px_per_m, sh / 2 * pr.px_per_m
            pr.cv.triangle([(cx - a, cy), (cx + a, cy), (cx, cy - c)], band)
            pr.cv.triangle([(cx - a, cy), (cx + a, cy), (cx, cy + c)], band)
            pr.mark(region, u - sw / 4, v + sh / 4, u + sw / 4, v + 3 * sh / 4)


def rng_plank(u):
    """A steady tone per plank."""
    return (zlib.crc32(f"{u:.2f}".encode()) % 100) / 100


def gate(pr, region, u0, u1, v1, wall, wood, band):
    """A great double door in a stepped surround of pale plaster, with iron studs and rings, and a
    banner each side."""
    pale = _mix(wall, CREAM, 0.58)
    cu = (u0 + u1) / 2
    half = (u1 - u0) / 2
    pr.rect(region, cu - half - 0.3, 0.0, cu + half + 0.3, v1 + 0.26, pale)
    pr.rect(region, cu - half - 0.12, v1 + 0.26, cu + half + 0.12, v1 + 0.44, pale)
    pr.rect(region, cu - 0.48, v1 + 0.44, cu + 0.48, v1 + 0.62, pale)
    k, vv = 0, 0.1
    while vv < v1 + 0.2:                                      # teeth down its sides, and across the top
        pr.rect(region, cu - half - 0.5, vv, cu - half - 0.3, vv + 0.3, pale)
        pr.rect(region, cu + half + 0.3, vv, cu + half + 0.5, vv + 0.3, pale)
        vv += 0.6
    for sx in (-1, 1):
        pr.rect(region, cu + sx * (half + 0.1) - 0.13, v1 + 0.44, cu + sx * (half + 0.1) + 0.13, v1 + 0.6, pale)
    rng = random.Random(zlib.crc32(region.encode()) + 2)
    worn(pr, region, cu - half - 0.5, 0.0, cu + half + 0.5, v1 + 0.62, rng, dirt=0.22, above=sum(_mix(wall, CREAM, 0.3)) / 3)
    pr.tone(region, u0 - 0.1, v1 + 0.1, u1 + 0.1, v1 + 0.18, 0.76)
    pr.rect(region, u0 - 0.1, 0.0, u1 + 0.1, v1 + 0.1, _shade(wood, 0.55))
    for s in (0, 1):                                          # the two leaves
        a, c = (u0, cu - 0.02) if s == 0 else (cu + 0.02, u1)
        pr.rect(region, a, 0.0, c, v1, _shade(wood, 0.8), _shade(wood, 0.42), pr.lw)
        uu = a + 0.16
        while uu < c - 0.06:                                  # wide planks, each its own tone
            pr.tone(region, uu - 0.16, 0.0, min(c, uu), v1, 0.86 + 0.28 * rng_plank(uu))
            pr.vline(region, uu, 0.0, v1, _shade(wood, 0.4))
            uu += 0.16
        pr.tone(region, a, v1 * 0.62, c, v1, 0.92)            # the head's shadow, fading down
        for vv in (v1 * 0.17, v1 * 0.52, v1 * 0.85):          # iron bands, their edges cut, with studs
            pr.rect(region, a + 0.05, vv - 0.085, c - 0.05, vv + 0.085, (54, 44, 40))
            pr.tone(region, a + 0.05, vv + 0.05, c - 0.05, vv + 0.085, 1.45)
            uu = a + 0.1
            while uu < c - 0.08:
                pr.rect(region, uu, vv - 0.035, uu + 0.055, vv + 0.035, (116, 104, 92))
                uu += 0.15
        cx, cy = pr.P(region, (c if s == 0 else a) + (-0.17 if s == 0 else 0.17), v1 * 0.38)
        for r, col in ((0.13, (40, 34, 32)), (0.1, (118, 104, 90)), (0.07, _shade(wood, 0.62))):  # a ring to knock with
            pr.cv.ellipse(cx, cy, r * pr.px_per_m, r * pr.px_per_m, col)


def window(pr, region, u0, v0, u1, v1, wall, wood, closed):
    """A window in the plaster, painted: a pale frame stepped at the top, then shutters of planks
    or a dark hollow, with the false depth of a shadow under the head and a lit sill."""
    if closed == "shade":                                     # the side of a recess, darkest at its foot
        n = 4
        for k in range(n):
            a, c = v0 + (v1 - v0) * k / n, v0 + (v1 - v0) * (k + 1) / n
            pr.tone(region, u0, a, u1, c, 0.46 + 0.09 * k)
        return
    if closed == "recess":                                    # a loggia: plaster in shade, darkest at the top
        n = 5
        for k in range(n):
            a, c = v0 + (v1 - v0) * k / n, v0 + (v1 - v0) * (k + 1) / n
            pr.tone(region, u0, a, u1, c, 0.62 - 0.07 * k)
        for cu in (u0 + (u1 - u0) * 0.2, u0 + (u1 - u0) * 0.72):  # two small windows on its back wall
            pr.rect(region, cu - 0.26, v0 + 0.72, cu + 0.26, v0 + 1.4, _shade(DARK, 1.15))
        return
    pale = _mix(wall, CREAM, 0.34)
    if not closed:                                            # a plain hole in the wall
        rim = _mix(wall, CREAM, 0.26)                         # plaster turned into the hole, its edge rubbed pale
        pr.tone(region, u0 - 0.1, v1 + 0.05, u1 + 0.1, v1 + 0.11, 0.86)
        pr.rect(region, u0 - 0.05, v0 - 0.09, u1 + 0.05, v1 + 0.05, rim)
        n = 6
        for k in range(n):                                    # the dark inside, a little lit from the sill up
            a, c = v0 + (v1 - v0) * k / n, v0 + (v1 - v0) * (k + 1) / n
            f = (n - 1 - k) / (n - 1)
            pr.rect(region, u0, a, u1, c, (int(20 + 34 * f * f), int(19 + 21 * f * f), int(17 + 12 * f * f)))
        pr.rect(region, u0, v0 - 0.02, u1, v0 + 0.05, _shade(wall, 0.66))     # the sill, going in
        pr.tone(region, u0 - 0.05, v0 - 0.09, u1 + 0.05, v0 - 0.03, 1.12)     # and its lit lip
        return
    pr.rect(region, u0 - 0.26, v0 - 0.2, u1 + 0.26, v1 + 0.24, pale)          # a stepped pale surround
    pr.rect(region, (u0 + u1) / 2 - 0.3, v1 + 0.24, (u0 + u1) / 2 + 0.3, v1 + 0.38, pale)
    worn(pr, region, u0 - 0.26, v0 - 0.2, u1 + 0.26, v1 + 0.38, random.Random(zlib.crc32(f"{region}{u0}".encode())))
    pr.rect(region, u0 - 0.13, v0 - 0.1, u1 + 0.13, v1 + 0.14, _shade(wood, 0.9), _shade(wood, 0.55), pr.lw)  # the frame
    pr.tone(region, u0 - 0.13, v1 + 0.08, u1 + 0.13, v1 + 0.14, 1.16)         # the light on its head
    pr.tone(region, u0 - 0.13, v0 - 0.1, u0 - 0.07, v1 + 0.08, 1.1)
    pr.rect(region, u0 - 0.02, v0 - 0.02, u1 + 0.02, v1 + 0.02, (38, 25, 18))
    cu, mid = (u0 + u1) / 2, (v0 + v1) / 2 - 0.02
    for a, c in ((u0, cu - 0.015), (cu + 0.015, u1)):                         # the two leaves
        pr.rect(region, a, v0, c, v1, _shade(wood, 0.78))                     # stiles and rails
        for lo, hi in ((v0 + 0.09, mid - 0.05), (mid + 0.05, v1 - 0.09)):     # a louvred panel over a louvred panel
            pr.rect(region, a + 0.07, lo, c - 0.07, hi, _shade(wood, 0.36))
            vv = lo + 0.03
            while vv < hi - 0.04:
                pr.rect(region, a + 0.07, vv, c - 0.07, vv + 0.05, _shade(wood, 0.68))
                vv += 0.1
        pr.tone(region, a, mid - 0.05, c, mid + 0.05, 1.14)                   # the rail catches the light
    pr.rect(region, cu - 0.05, mid - 0.03, cu + 0.05, mid + 0.04, (34, 28, 26))     # the latch
    pr.tone(region, u0, v1 - 0.1, u1, v1, 0.62)                               # the head's shadow
    pr.tone(region, u0 - 0.13, v0 - 0.17, u1 + 0.13, v0 - 0.1, 0.84)          # the sill's


def pier_side(pr, region, u, w, a, c, h, pale):
    """A painted side of a pier from `u`: a trapezium `w` wide at the foot and from `a` to `c` at
    the top of height `h`. Its edges rubbed paler, a worn lip of `pale` round its head and earth up
    its foot. No baked shade: the game's sun does that, and the chamfer divides it."""
    rng = random.Random(zlib.crc32(f"{region}{u}".encode()))
    n = 40
    for j in range(n):
        f = j / n
        v0, v1 = h * f, h * (f + 1 / n)
        left, right = u + a * f, u + w + (c - w) * f
        for inset, wide, k in ((0.0, 0.06, 1.12), (0.06, 0.1, 1.06)):
            d = wide * rng.uniform(0.7, 1.3)                  # worn unevenly
            pr.tone(region, left + inset, v0, left + inset + d, v1, k)
            pr.tone(region, right - inset - d, v0, right - inset, v1, k)
    for v, k in ((0.0, 0.95), (0.14, 0.96), (0.3, 0.97), (0.5, 0.98), (0.7, 0.99)):
        pr.tone(region, u, v, u + w, v + 0.2, k)              # the ground's earth, splashed up
    x = u
    while x < u + w:                                          # the lip, its lower edge uneven
        step = rng.uniform(0.05, 0.14)
        pr.rect(region, x, h - rng.uniform(0.1, 0.2), min(u + w, x + step), h, pale)
        x += step
    pr.rough_stone(region, u, h - 0.22, u + w, h, 0.16, 0.06, 0.12)


def pier_chamfer(pr, region, u, w, h, pale):
    """The strip down a pier's corner, `w` wide: pale stone worn by hands and weather, in runs
    rubbed bright here and dull there, with its edge chipped, never one clean line."""
    rng = random.Random(zlib.crc32(f"{region}chamfer".encode()))
    pr.rect(region, u, 0.0, u + w, h, pale)
    pr.rough_stone(region, u, 0.0, u + w, h, 0.18, 0.08, 0.08)
    v = 0.0
    while v < h:
        ln = rng.uniform(0.2, 0.6)
        pr.tone(region, u, v, u + w, min(h, v + ln), rng.choice((0.9, 0.95, 1.0, 1.04, 1.08)))
        v += ln
    for _ in range(int(h * 6)):                               # chips off its edges
        v = rng.uniform(0.0, h)
        side = rng.choice((0.0, w * 0.75))
        pr.tone(region, u + side, v, u + side + w * 0.25, min(h, v + rng.uniform(0.04, 0.14)), rng.uniform(0.92, 0.97))


def weather(pr, region, w, h, top, foot):
    """What time does to a kept wall: shade under the parapet, grime rising over the foot, the
    corners rubbed paler."""
    for j in range(5):                                        # shade under the eaves
        pr.tone(region, 0, top - 0.16 * (j + 1), w, top - 0.16 * j, 0.91 + 0.015 * j)
    base = 0.62 if foot else 0.0
    for j in range(4):                                        # splashed earth over the foot
        pr.tone(region, 0, base + 0.14 * j, w, base + 0.14 * (j + 1), 0.86 + 0.035 * j)
    for edge in (0.0, w - 0.14):                              # corners rubbed paler
        pr.tone(region, edge, base, edge + 0.14, top, 1.07)


def worn(pr, region, u0, v0, u1, v1, rng, dirt=0.0, above=None, strength=1.0):
    """Pale stone with years on it, inside a box: broad soft clouds of earth rubbed into it, scuffs,
    a few hair cracks and, with `dirt` (a height in metres), earth blotched up it from the ground.
    `above`: the brightness a pixel needs to wear, so a pale shape keeps its crisp edge. `strength`
    below 1 keeps it quiet, for a long thin shape where blotches read as stains."""
    du, dv = u1 - u0, v1 - v0

    def tri(u, v, d, a=1.0):
        """Three corners round (u, v), never out of the box."""
        return [(min(u1, max(u0, u + rng.uniform(-d, d))), min(v1, max(v0, v + rng.uniform(-d * a, d * a)))) for _ in range(3)]

    pr.blotch(region, u0, v0, u1, v1, 0.42, 0.13 * strength, above)
    pr.blotch(region, u0, v0, u1, v1, 0.16, 0.1 * strength, above)
    for _ in range(int(du * dv * 26 * strength) + 3):         # scuffs, long and thin, earth in them
        u, v, d = rng.uniform(u0, u1), rng.uniform(v0, v1), rng.uniform(0.05, 0.2)
        pr.facet(region, tri(u, v, d, rng.uniform(0.2, 0.8)), rng.choice(((0.88, 0.83, 0.76), (0.92, 0.88, 0.82), (1.08, 1.07, 1.05))), above)
    for _ in range(int(du * dv * 5) + 1):                     # hair cracks
        u, v, ln = rng.uniform(u0, u1), rng.uniform(v0, v1), rng.uniform(0.12, 0.42)
        c, e = rng.uniform(-1, 1), rng.uniform(-1, 1)
        pts = [(u, v), (u + c * ln, v + e * ln), (u + c * ln + 0.018, v + e * ln + 0.018)]
        pr.facet(region, [(min(u1, max(u0, a)), min(v1, max(v0, b))) for a, b in pts], 0.8, above)
    if dirt:
        for layer, count, k in ((1.0, 16, (0.92, 0.87, 0.78)), (0.7, 18, (0.92, 0.86, 0.77)), (0.4, 18, (0.9, 0.84, 0.74))):
            for _ in range(int(du * count)):
                top = dirt * layer * rng.uniform(0.55, 1.15)
                pr.facet(region, tri(rng.uniform(u0, u1), v0 + rng.uniform(0.0, top), rng.uniform(0.12, 0.34), 0.7), k, above)


def foot_stones(pr, region, w, wall):
    """The course of pale stone at the foot, gone dull and earthy with the years."""
    rng = random.Random(zlib.crc32(region.encode()) + 1)
    pale = _mix(wall, CREAM, 0.6)
    pr.rect(region, 0, 0, w, 0.72, pale)
    pr.rough_stone(region, 0.0, 0.0, w, 0.72, 0.3, 0.05, 0.12)
    worn(pr, region, 0.0, 0.0, w, 0.72, rng, strength=0.6)
    pr.tone(region, 0, 0.67, w, 0.72, 1.1)                    # its top edge, rubbed pale
    pr.hline(region, 0.73, 0, w, _shade(wall, 0.72), pr.lw)


def pale_frieze(pr, region, u0, u1, v, wall):
    """The band of pale triangles over the gate, between two pale lines."""
    pale = _mix(wall, CREAM, 0.6)
    H, step = 0.36, 0.5
    pr.rect(region, u0, v - 0.1, u1, v, pale)
    pr.rect(region, u0, v + H, u1, v + H + 0.08, pale)
    u = u0 + 0.05
    while u + step <= u1:
        (x0, y0), (x1, y1) = pr.P(region, u, v), pr.P(region, u + step, v + H)
        pr.cv.triangle([(x0, y0), (x1, y0), ((x0 + x1) / 2, y1)], pale)
        u += step
    worn(pr, region, u0, v - 0.1, u1, v + H + 0.08, random.Random(zlib.crc32(region.encode()) + 3), above=sum(_mix(wall, CREAM, 0.3)) / 3)


def frieze(pr, region, w, v, wall, seed, style=None):
    """A band of relief round a wall, one of a few patterns by the wall's name."""
    rng = random.Random(zlib.crc32(f"{seed}/{region}/frieze".encode()))
    style = rng.randrange(3) if style is None else style
    light, dark = _shade(wall, 1.28), _shade(wall, 0.58)
    step = rng.choice((0.3, 0.4, 0.5))
    u, k = 0.0, 0
    H = 0.26
    while u < w - 0.02:
        (x0, y0), (x1, y1) = pr.P(region, u, v), pr.P(region, min(w, u + step), v + H)
        xm = (x0 + x1) / 2
        if style == 0:                                        # zigzag
            pr.cv.triangle([(x0, y0), (x1, y0), (xm, y1)], light)
        elif style == 1:                                      # diamonds
            ym = (y0 + y1) / 2
            pr.cv.triangle([(x0, ym), (xm, y0), (x1, ym)], dark)
            pr.cv.triangle([(x0, ym), (xm, y1), (x1, ym)], light)
        elif k % 2 == 0:                                      # blocks
            pr.rect(region, u, v, min(w, u + step / 2), v + H, dark)
        u += step
        k += 1
    pr.hline(region, v - 0.02, 0, w, dark, pr.lw)
    pr.hline(region, v + H + 0.02, 0, w, light, pr.lw)
