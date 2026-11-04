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


def gate(pr, region, u0, u1, v1, wall, wood, band):
    """A great double door in a stepped surround of pale plaster, with iron studs and rings, and a
    banner each side."""
    pale = _mix(wall, CREAM, 0.7)
    cu = (u0 + u1) / 2
    half = (u1 - u0) / 2
    pr.rect(region, cu - half - 0.42, 0.0, cu + half + 0.42, v1 + 0.2, pale)
    for k, (d, a) in enumerate(((0.28, 0.2), (0.1, 0.4), (-0.12, 0.6))):     # it steps up to the middle
        pr.rect(region, cu - half - d, v1 + 0.2, cu + half + d, v1 + a + 0.14, pale)
    n = 4
    for k in range(n):                                        # teeth along its outer edges
        vv = k * 0.62
        pr.rect(region, cu - half - 0.58, vv, cu - half - 0.42, vv + 0.31, pale)
        pr.rect(region, cu + half + 0.42, vv, cu + half + 0.58, vv + 0.31, pale)
    pr.tone(region, u0 - 0.1, v1 + 0.1, u1 + 0.1, v1 + 0.18, 0.76)
    pr.rect(region, u0 - 0.1, 0.0, u1 + 0.1, v1 + 0.1, _shade(wood, 0.55))
    for s in (0, 1):                                          # the two leaves
        a, c = (u0, cu - 0.02) if s == 0 else (cu + 0.02, u1)
        pr.rect(region, a, 0.0, c, v1, _shade(wood, 1.05), _shade(wood, 0.55), pr.lw)
        uu = a + 0.13
        while uu < c - 0.04:
            pr.vline(region, uu, 0.0, v1, _shade(wood, 0.62))
            uu += 0.14
        for vv in (v1 * 0.2, v1 * 0.55, v1 * 0.85):           # iron straps with studs
            pr.rect(region, a + 0.03, vv, c - 0.03, vv + 0.07, (52, 50, 54))
        cx, cy = pr.P(region, (c if s == 0 else a) + (-0.14 if s == 0 else 0.14), v1 * 0.46)
        r = 0.07 * pr.px_per_m
        pr.cv.ellipse(cx, cy, r, r, (52, 50, 54))


def window(pr, region, u0, v0, u1, v1, wall, wood, closed):
    """A window in the plaster, painted: a pale frame stepped at the top, then shutters of planks
    or a dark hollow, with the false depth of a shadow under the head and a lit sill."""
    pale = _mix(wall, CREAM, 0.55)
    pr.rect(region, u0 - 0.16, v0 - 0.14, u1 + 0.16, v1 + 0.14, pale)
    pr.rect(region, u0 - 0.04, v1 + 0.14, u1 + 0.04, v1 + 0.26, pale)
    pr.tone(region, u0 - 0.2, v0 - 0.2, u1 + 0.2, v0 - 0.14, 0.82)            # the sill's shadow
    pr.rect(region, u0 - 0.03, v0 - 0.03, u1 + 0.03, v1 + 0.03, _shade(wall, 0.42))
    if closed:
        cu = (u0 + u1) / 2
        for a, c in ((u0, cu - 0.015), (cu + 0.015, u1)):
            pr.rect(region, a, v0, c, v1, _shade(wood, 1.15))
            uu = a + 0.08
            while uu < c - 0.02:
                pr.vline(region, uu, v0, v1, _shade(wood, 0.62))
                uu += 0.085
            for vv in (v0 + (v1 - v0) * 0.22, v0 + (v1 - v0) * 0.72):         # the battens
                pr.rect(region, a, vv, c, vv + 0.05, _shade(wood, 0.72))
    else:
        pr.rect(region, u0, v0, u1, v1, DARK)
        pr.tone(region, u0, v0, u1, v0 + (v1 - v0) * 0.35, 1.7)               # the far side of the sill
    pr.tone(region, u0, v1 - 0.12, u1, v1, 0.6)                               # the head's shadow


def weather(pr, region, w, h, top, wall, foot):
    """What time does to a kept wall: shade under the parapet, rain streaks down from it, grime
    rising over the foot, the corners worn back to the brick."""
    rng = random.Random(zlib.crc32(region.encode()))
    for _ in range(int(w * h * 1.4)):                         # the trowel's long passes, course on course
        u, v = rng.uniform(-0.5, w), rng.uniform(0, h)
        ln, th = rng.uniform(0.7, 2.4), rng.uniform(0.1, 0.3)
        pr.tone(region, max(0.0, u), v, min(w, u + ln), min(h, v + th), rng.choice((0.93, 0.95, 1.05, 1.08)))
    for j in range(5):                                        # shade under the eaves
        pr.tone(region, 0, top - 0.16 * (j + 1), w, top - 0.16 * j, 0.91 + 0.015 * j)
    u = rng.uniform(0.1, 0.6)
    while u < w:                                              # streaks, each fading as it runs
        ln = rng.uniform(0.6, min(2.2, h * 0.5))
        sw = rng.uniform(0.05, 0.16)
        for j in range(4):
            a = top - ln * (j + 1) / 4
            pr.tone(region, u, max(0.0, a), min(w, u + sw), top - ln * j / 4, 0.97 - 0.015 * (3 - j))
        u += rng.uniform(0.35, 0.95)
    base = 0.62 if foot else 0.0
    for j in range(4):                                        # splashed earth over the foot
        pr.tone(region, 0, base + 0.14 * j, w, base + 0.14 * (j + 1), 0.86 + 0.035 * j)
    for edge in (0.0, w - 0.14):                              # corners rubbed paler
        pr.tone(region, edge, base, edge + 0.14, top, 1.07)
    for _ in range(int(w / 2.5) + 1):                         # plaster fallen off, bricks showing
        cu = rng.choice((rng.uniform(0.1, 0.5), w - rng.uniform(0.3, 0.8), rng.uniform(0.2, max(0.3, w - 0.8))))
        cv = rng.uniform(base + 0.2, max(base + 0.3, h - 1.2))
        pw, ph = rng.uniform(0.3, 0.6), rng.uniform(0.2, 0.42)
        pr.rect(region, cu, cv, min(w, cu + pw), min(h, cv + ph), _shade(wall, 0.62))
        vv, row = cv, 0
        while vv < cv + ph - 0.03:
            uu = cu - (row % 2) * 0.08
            while uu < cu + pw:
                a, c = max(cu, uu + 0.012), min(cu + pw, uu + 0.15)
                if c > a:
                    pr.rect(region, a, vv + 0.012, min(w, c), min(h, vv + 0.075), _shade(wall, rng.uniform(0.74, 0.96)))
                uu += 0.16
            vv += 0.09
            row += 1


def foot_stones(pr, region, w, wall):
    """The course of pale stone at the foot, block by block."""
    rng = random.Random(zlib.crc32(region.encode()) + 1)
    pale = _mix(wall, CREAM, 0.6)
    pr.rect(region, 0, 0, w, 0.62, _shade(pale, 0.72))
    for row, (a, c) in enumerate(((0.02, 0.3), (0.32, 0.6))):
        u = -rng.uniform(0, 0.4) if row else 0.0
        while u < w:
            bw = rng.uniform(0.4, 0.8)
            pr.rect(region, max(0.0, u + 0.015), a, min(w, u + bw - 0.015), c, _shade(pale, rng.uniform(0.9, 1.06)))
            u += bw
    pr.hline(region, 0.63, 0, w, _shade(wall, 0.6), pr.lw)


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
