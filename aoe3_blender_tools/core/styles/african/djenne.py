# SPDX-License-Identifier: GPL-3.0-or-later
"""The Djenne finish: how the Sudano-Sahelian builders of Djenne and Timbuktu left an earthen
building in the nineteenth century, painted for the game's camera, each part in its own way.

All of it is earth (banco: mud, rice husk and shea butter), but no two parts weather alike:

- the walls of the store are plastered anew each year after the rains (the crepissage): smoothed by
  hand, so they show broad sweeps of the palm and the grooves of the fingers, a little straw;
- the upper room missed a year: older, drier, cracked, its fresh patches paler;
- the pilasters stand out of the wall: their fronts take the rain, so they run with gullies and
  their cones are washed dark;
- the parapets and their cones are worn round and stained by the water they shed;
- the yard's wall is the oldest: eroded to its bricks in places, its top crumbled;
- the powder magazine is built of coiled clay, its rings still under the plaster;
- the roofs are trodden earth, the yard swept sand, the toron split palm wood;
- the door is a Timbuktu door of planks with rows of iron studs, the windows wooden lattice.

Every relief (finger grooves, bricks, the door's frame) is also raised on the painter's height
layer (`Painter.relief`), so the bump map makes it catch the light. Pure numpy."""
import random
import zlib

import numpy as np

from ...painter import _shade

FRESH = (154, 117, 90)          # this year's plaster, warm; darker than it looks right in a render: the game's sun bleaches it
OLD = (132, 107, 88)            # a plaster a few rains old, greyer
RIB = (168, 131, 100)           # the pilasters' fronts, in the sun
COURT = (122, 95, 76)          # the yard's old wall, darkest
CAP = (124, 95, 74)            # parapets and cones, washed by the water they shed
ROOF = (178, 149, 116)          # trodden roofs, sun-bleached
SAND = (168, 141, 110)          # the swept yard
DOME = (142, 107, 82)           # the magazine's dome, a redder earth
PALM = (132, 104, 76)           # split palm trunks, grey-brown with sun
DOOR = (74, 50, 34)             # old hardwood
IRON = (52, 46, 42)
DARK = (28, 21, 17)
# the buildings painted in this finish: (building type, architecture); layouts.py marks their pieces
BUILDINGS = {("ARMORY", "SAHEL")}


def finish(params):
    """True for a building painted in the Djenne finish."""
    return (str(getattr(params, "building_type", "")).upper(), str(getattr(params, "architecture", "")).upper()) in BUILDINGS


# --------------------------------------------------------------------------------------------------
# fields over a region

def _grid(pr, region):
    """(slice of the canvas, u, v) of a region: u and v in metres for every pixel, v up."""
    r = pr.at[region]
    px = pr.px_per_m
    ys, xs = np.mgrid[r.y:r.y + r.h, r.x:r.x + r.w].astype(np.float32)
    return (slice(r.y, r.y + r.h), slice(r.x, r.x + r.w)), (xs - r.x + 0.5) / px, (r.y + r.h - ys - 0.5) / px


def _rng(seed, region, what):
    return np.random.default_rng(zlib.crc32(f"{seed}/{region}/{what}".encode()))


def _noise(rng, u, v, cu, cv):
    """Smooth noise from -1 to 1 over (u, v) metres, blobs `cu` wide and `cv` high: stretched one
    way it reads as strokes."""
    gu, gv = u / cu, v / cv
    nx, ny = int(gu.max()) + 3, int(gv.max()) + 3
    g = rng.uniform(-1.0, 1.0, (ny, nx)).astype(np.float32)
    ix, iy = gu.astype(int), gv.astype(int)
    fx, fy = gu - ix, gv - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    top = g[iy, ix] * (1 - fx) + g[iy, ix + 1] * fx
    bot = g[iy + 1, ix] * (1 - fx) + g[iy + 1, ix + 1] * fx
    return top * (1 - fy) + bot * fy


def _apply(pr, region, sl, f, lift=None, dh=0.0):
    """Multiplies a region by the field `f` (per pixel, or per pixel and channel), and raises it
    by `dh` times `lift`."""
    pr.cv.a[sl] *= f if f.ndim == 3 else f[:, :, None]
    if lift is not None and dh:
        pr.relief_mask(region, lift, dh)


def hand_plaster(pr, region, seed, k=0.1, fingers=0.1, straw=1.0, tilt=0.35):
    """Mud smoothed by hand: a lumpy surface lit from the upper left (each lump a little light
    above and shaded under), short smears where the palm pressed it flat, pores, and straw.
    `fingers` sets how many smears; `tilt` how much they lean."""
    sl, u, v = _grid(pr, region)
    rng = _rng(seed, region, "hand")
    n = (0.45 * _noise(rng, u, v, 0.38, 0.32) + 0.42 * _noise(rng, u, v, 0.14, 0.12)
         + 0.22 * _noise(rng, u, v, 0.06, 0.06))
    d = max(1, int(round(0.03 * pr.px_per_m)))                  # each lump lit from the upper left
    lit = n - np.roll(np.roll(n, d, 0), d, 1)
    broad = _noise(rng, u, v, 1.3, 1.0)
    f = 1.0 + k * 1.3 * n + k * 4.8 * lit + 0.07 * broad
    tint = np.stack([f, f * (1 - 0.02 * broad), f * (1 - 0.05 * broad)], axis=2)  # redder where darker
    _apply(pr, region, sl, tint, n, 0.012)
    r = pr.at[region]
    rr = random.Random(zlib.crc32(f"{seed}/{region}/smears".encode()))
    w, h = r.world_w, r.world_h
    for _ in range(int(w * h * 18 * fingers / 0.1)):           # palm smears: flat facets, a lit edge
        cu, cv = rr.uniform(0, w), rr.uniform(0, h)
        L, W = rr.uniform(0.12, 0.35), rr.uniform(0.05, 0.12)
        ang = rr.uniform(-1.0, 1.0) * tilt + (1.57 if rr.random() < 0.6 else 0.0)
        ca, sa = np.cos(ang), np.sin(ang)
        pts = [(cu - ca * L / 2, cv - sa * L / 2), (cu + ca * L / 2 - sa * W, cv + sa * L / 2 + ca * W),
               (cu + ca * L / 2, cv + sa * L / 2)]
        pr.facet(region, [(min(w, max(0.0, x)), min(h, max(0.0, y))) for x, y in pts], rr.choice((0.93, 0.95, 1.05, 1.07)))
    for _ in range(int(w * h * 10)):                            # pores where air left the mud
        cu, cv = rr.uniform(0, w), rr.uniform(0, h)
        s_ = rr.uniform(0.015, 0.03)
        pr.tone(region, cu, cv, min(w, cu + s_), min(h, cv + s_), 0.8)
    if straw:
        for _ in range(int(w * h * 14 * straw)):                # rice husk and straw in the banco
            a_, b_ = rr.uniform(0, w), rr.uniform(0, h)
            ln = rr.uniform(0.04, 0.11)
            pr.tone(region, a_, b_, min(w, a_ + ln), min(h, b_ + 0.022), rr.choice((1.18, 1.25, 0.82)))


def gullies(pr, region, w, h, seed, n_per_m=0.9, k=0.16, top=None):
    """Rain running down from the top: soft dark runs, washed paler at their edges, deeper where
    the water gathers, sunk a little into the wall."""
    rng = random.Random(zlib.crc32(f"{seed}/{region}/gullies".encode()))
    top = h if top is None else top
    for _ in range(max(1, int(w * n_per_m))):
        u, width = rng.uniform(0, w), rng.uniform(0.05, 0.16)
        length = top * rng.uniform(0.25, 0.75)
        steps = 6
        for j in range(steps):
            t = j / steps
            a, b = top - length * (t + 1 / steps), top - length * t
            pr.tone(region, u, a, min(w, u + width * (1 - 0.5 * t)), b, 1 - k * (1 - t))
        pr.tone(region, u - 0.03, top - length, u, top, 1.06)
        pr.relief(region, u, top - length, min(w, u + width), top, -0.004)


def erode_foot(pr, region, w, seed, height=0.85, bricks=0.5, base=FRESH):
    """The foot of a wall: darker and rougher where the rain splashes, and here and there the
    plaster gone, showing the bricks (cylindrical djenne-ferey laid in rows) under it."""
    n = 7
    for j in range(n):
        t = j / n
        pr.tone(region, 0.0, height * t, w, height * (t + 1 / n), 1 - 0.3 * (1 - t) ** 1.6)
    rng = random.Random(zlib.crc32(f"{seed}/{region}/foot".encode()))
    for _ in range(int(w * bricks) + 1):
        bw, bh = rng.uniform(0.35, 0.9), rng.uniform(0.2, 0.5)
        u0 = rng.uniform(0, max(0.01, w - bw))
        v0 = rng.uniform(0.02, 0.25)
        brick_patch(pr, region, u0, v0, u0 + bw, v0 + bh, rng, base)


def brick_patch(pr, region, u0, v0, u1, v1, rng, base):
    """Where the plaster fell: the bricks in their mortar, a ragged edge of plaster round them."""
    pr.tone(region, u0 - 0.04, v0 - 0.04, u1 + 0.04, v1 + 0.04, 0.82)
    pr.rect(region, u0, v0, u1, v1, _shade(base, 0.62))
    vv, row = v0, 0
    while vv < v1 - 0.02:
        uu = u0 - (row % 2) * 0.1
        while uu < u1:
            a, c = max(u0, uu + 0.012), min(u1, uu + 0.19)
            if c > a:
                pr.rect(region, a, vv + 0.012, c, min(v1, vv + 0.088), _shade(base, rng.uniform(0.78, 1.0)))
                pr.tone(region, a, min(v1, vv + 0.07), c, min(v1, vv + 0.088), 1.12)
            uu += 0.2
        vv += 0.1
        row += 1
    pr.relief(region, u0, v0, u1, v1, -0.02, soft=0.03)


def contact(pr, region, w, h, top=0.5, k=0.8):
    """Shade under the parapet's lip, fading down."""
    n = 6
    for j in range(n):
        t = j / n
        pr.tone(region, 0.0, h - top * (t + 1 / n), w, h - top * t, 1 - (1 - k) * (1 - t) ** 1.5)


def drips(pr, region, w, rows, seed):
    """Under each row of toron, the drips the beams shed: short dark runs."""
    rng = random.Random(zlib.crc32(f"{seed}/{region}/drips".encode()))
    for v in rows:
        u = rng.uniform(0.1, 0.5)
        while u < w - 0.1:
            ln = rng.uniform(0.2, 0.6)
            pr.tone(region, u - 0.04, v - ln, u + 0.04, v - 0.05, 0.88)
            u += rng.uniform(0.6, 1.1)


def vents(pr, region, w, h, seed):
    """The small triangular vents high on a Djenne wall, in a row."""
    rng = random.Random(zlib.crc32(f"{seed}/{region}/vents".encode()))
    if w < 2.0 or rng.random() < 0.4:
        return
    n = int(w / 0.9)
    for k in range(n):
        cu, v0 = w * (k + 0.5) / n, h - 0.95
        (x0, y0), (x1, y1) = pr.P(region, cu - 0.08, v0), pr.P(region, cu + 0.08, v0 + 0.17)
        pr.cv.triangle([(x0, y0), (x1, y0), ((x0 + x1) / 2, y1)], (52, 38, 30))
        pr.tone(region, cu - 0.12, v0 - 0.05, cu + 0.12, v0, 1.12)
        pr.relief(region, cu - 0.09, v0, cu + 0.09, v0 + 0.2, -0.03)


# --------------------------------------------------------------------------------------------------
# openings

def timbuktu_door(pr, region, u0, u1, v1, band):
    """A Timbuktu door: a deep stepped earthen frame, two leaves of dark planks, rows of iron studs
    and plates across them, a ring to knock with, a small iron grille."""
    cu, half = (u0 + u1) / 2, (u1 - u0) / 2
    for step, k, dh in ((0.34, 0.86, 0.02), (0.2, 0.74, 0.035), (0.08, 0.6, 0.05)):   # the frame, stepping in
        pr.tone(region, cu - half - step, 0.0, cu + half + step, v1 + step, k)
        pr.relief(region, cu - half - step, 0.0, cu + half + step, v1 + step, -dh)
    pr.tone(region, cu - half - 0.36, v1 + 0.34, cu + half + 0.36, v1 + 0.42, 1.14)      # its lit lintel
    rng = random.Random(zlib.crc32(f"{region}/door".encode()))
    for s in (0, 1):
        a, c = (u0, cu - 0.015) if s == 0 else (cu + 0.015, u1)
        pr.rect(region, a, 0.0, c, v1, DOOR)
        uu = a
        while uu < c - 0.02:                                    # planks, each its own tone and grain
            pw = rng.uniform(0.11, 0.17)
            pr.tone(region, uu, 0.0, min(c, uu + pw), v1, rng.uniform(0.82, 1.18))
            pr.vline(region, uu, 0.0, v1, _shade(DOOR, 0.5))
            for _ in range(5):
                gv = rng.uniform(0.1, v1 - 0.1)
                pr.tone(region, uu + 0.02, gv, min(c, uu + pw - 0.02), gv + rng.uniform(0.15, 0.4), rng.choice((0.9, 1.08)))
            uu += pw
        for vv in (v1 * 0.14, v1 * 0.45, v1 * 0.78):            # iron plates across, studs along them
            pr.rect(region, a + 0.04, vv - 0.06, c - 0.04, vv + 0.06, IRON)
            pr.tone(region, a + 0.04, vv + 0.035, c - 0.04, vv + 0.06, 1.5)
            uu = a + 0.08
            while uu < c - 0.06:
                pr.rect(region, uu, vv - 0.025, uu + 0.045, vv + 0.025, (128, 116, 100))
                uu += 0.11
        sv = v1 * 0.62                                          # a column of studs down each leaf
        while sv < v1 - 0.12:
            pr.rect(region, (a + c) / 2 - 0.022, sv, (a + c) / 2 + 0.022, sv + 0.045, (122, 110, 96))
            sv += 0.16
    cx, cy = pr.P(region, cu + 0.16, v1 * 0.32)
    for r, col in ((0.11, (36, 30, 28)), (0.085, (120, 104, 86)), (0.06, DOOR)):
        pr.cv.ellipse(cx, cy, r * pr.px_per_m, r * pr.px_per_m, col)
    pr.relief(region, u0, 0.0, u1, v1, 0.01)


def lattice_window(pr, region, u0, v0, u1, v1, wood):
    """A small window shut by a wooden lattice in a recessed earthen frame."""
    pr.tone(region, u0 - 0.12, v0 - 0.1, u1 + 0.12, v1 + 0.12, 0.84)
    pr.relief(region, u0 - 0.12, v0 - 0.1, u1 + 0.12, v1 + 0.12, -0.02)
    pr.rect(region, u0, v0, u1, v1, DARK)
    grid = 0.07
    uu = u0 + grid / 2
    while uu < u1:                                              # the lattice, lit on its upper edges
        pr.rect(region, uu - 0.013, v0, uu + 0.013, v1, _shade(wood, 0.95))
        uu += grid
    vv = v0 + grid / 2
    while vv < v1:
        pr.rect(region, u0, vv - 0.013, u1, vv + 0.013, _shade(wood, 1.1))
        vv += grid
    pr.rect(region, u0 - 0.05, v0 - 0.06, u1 + 0.05, v0, _shade(wood, 0.8))        # a sill of palm
    pr.tone(region, u0 - 0.12, v1 + 0.12, u1 + 0.12, v1 + 0.18, 1.12)
    pr.relief(region, u0, v0, u1, v1, 0.008)


# --------------------------------------------------------------------------------------------------
# the parts

def block_wall(pr, region, spec, w, h, seed, wood):
    """A wall of a block: the store's fresh plaster, or an upper room's older one."""
    old = spec.get("z", 0.0) > 0.5
    pr.base(region, OLD if old else FRESH)
    hand_plaster(pr, region, seed, k=0.22 if old else 0.18, fingers=0.07 if old else 0.11)
    pr.cracks(region, 0.22, 0.1, keep=0.3)                      # hairline shrinkage cracks, even when fresh
    if old:                                                     # dry, cracked, freshly patched here and there
        pr.cracks(region, 0.3, 0.22, keep=0.45)
        rng = random.Random(zlib.crc32(f"{seed}/{region}/patch".encode()))
        for _ in range(int(w * h * 0.5) + 1):
            a, b = rng.uniform(0, w - 0.4), rng.uniform(0.3, h - 0.6)
            sw, sh = rng.uniform(0.4, 1.0), rng.uniform(0.3, 0.7)
            for j in range(3):
                d = 0.06 * j
                pr.tone(region, a + d, b + d, min(w, a + sw - d), min(h, b + sh - d), 1.035)
    contact(pr, region, w, h)
    gullies(pr, region, w, h, seed, n_per_m=1.1 if old else 0.9)
    rows = [h * f for f in spec.get("beam_rows", ())] or [h - 0.45]
    drips(pr, region, w, rows, seed)
    erode_foot(pr, region, w, seed, height=0.9 if not old else 0.4, bricks=0.35 if not old else 0.1,
               base=OLD if old else FRESH)
    if not spec["openings"] or not old:
        vents(pr, region, w, h, seed)
    for (u0, v0, u1, v1) in spec["openings"]:
        if v0 == 0.0:
            timbuktu_door(pr, region, u0, u1, v1, None)
        else:
            lattice_window(pr, region, u0, v0, u1, v1, wood)


def round_wall(pr, region, w, h, seed):
    """The powder magazine: coiled clay, its rings still showing under the plaster."""
    pr.base(region, _shade(FRESH, 0.96))
    sl, u, v = _grid(pr, region)
    rng = _rng(seed, region, "coils")
    ring = 0.16
    wob = _noise(rng, u, v, 0.8, 0.5) * 0.035
    fv = np.mod(v + wob, ring) / ring
    ridge = np.clip(1.0 - np.abs(fv - 0.42) / 0.5, 0.0, 1.0) ** 1.3      # each coil swells, lit above
    f = 0.84 + 0.26 * ridge + 0.05 * _noise(rng, u, v, 0.3, 0.12)
    _apply(pr, region, sl, f, ridge, 0.01)
    hand_plaster(pr, region, seed, k=0.11, fingers=0.03, straw=0.6, tilt=0.15)
    contact(pr, region, w, h, top=0.3, k=0.86)
    gullies(pr, region, w, h, seed, n_per_m=0.6, k=0.12)
    erode_foot(pr, region, w, seed, height=0.6, bricks=0.08)


def extras(pr, seed):
    """Every other surface in its own way."""
    at = pr.at
    if "rib" in at:                                             # pilasters: run with rain, dark at the foot
        r = at["rib"]
        pr.base("rib", RIB)
        hand_plaster(pr, "rib", seed + 1, k=0.15, fingers=0.06, tilt=0.05)
        gullies(pr, "rib", r.world_w, r.world_h, seed + 1, n_per_m=2.5, k=0.2)
        erode_foot(pr, "rib", r.world_w, seed + 1, height=0.9, bricks=0.0)
        n = 6
        for j in range(n):                                      # the cones' tips, washed darkest
            t = j / n
            pr.tone("rib", 0.0, r.world_h - 0.8 * (t + 1 / n), r.world_w, r.world_h - 0.8 * t, 1 - 0.18 * (1 - t))
    if "coping" in at:                                          # parapets and cones: worn round, stained
        r = at["coping"]
        pr.base("coping", CAP)
        hand_plaster(pr, "coping", seed + 2, k=0.18, fingers=0.04, straw=0.5)
        pr.blotch("coping", 0.0, 0.0, r.world_w, r.world_h, 0.35, 0.09)
        gullies(pr, "coping", r.world_w, r.world_h, seed + 2, n_per_m=2.0, k=0.14)
        pr.tone("coping", 0.0, r.world_h - 0.12, r.world_w, r.world_h, 1.1)   # the sun on the top
    if "court" in at:                                           # the yard's wall: old, eroded to its bricks
        r = at["court"]
        pr.base("court", COURT)
        hand_plaster(pr, "court", seed + 3, k=0.26, fingers=0.05, tilt=0.5)
        pr.cracks("court", 0.25, 0.28, keep=0.55)
        pr.blotch("court", 0.0, 0.0, r.world_w, r.world_h, 0.6, 0.1)
        rng = random.Random(zlib.crc32(f"{seed}/court/bricks".encode()))
        for _ in range(int(r.world_w * 0.3) + 1):               # a few bites of fallen plaster, low down
            bw, bh = rng.uniform(0.3, 0.7), rng.uniform(0.2, 0.4)
            u0, v0 = rng.uniform(0, max(0.01, r.world_w - bw)), rng.uniform(0.05, 0.6)
            brick_patch(pr, "court", u0, v0, u0 + bw, v0 + bh, rng, COURT)
        for _ in range(int(r.world_w * 2)):                     # the top worn into soft dips
            a, ln = rng.uniform(0, r.world_w), rng.uniform(0.3, 0.9)
            pr.tone("court", a, 1.6, min(r.world_w, a + ln), r.world_h, rng.uniform(0.86, 0.94))
        gullies(pr, "court", r.world_w, r.world_h, seed + 3, n_per_m=1.0, k=0.2)
        erode_foot(pr, "court", r.world_w, seed + 3, height=0.6, bricks=0.0, base=COURT)
    if "trim" in at:                                            # the smith's hearth: earth, black with soot
        r = at["trim"]
        pr.base("trim", _shade(OLD, 0.92))
        hand_plaster(pr, "trim", seed + 4, k=0.1, fingers=0.05)
        n = 8
        for j in range(n):
            t = j / n
            pr.tone("trim", 0.0, r.world_h * (0.35 + 0.65 * t), r.world_w, r.world_h * (0.35 + 0.65 * (t + 1 / n)), 1 - 0.45 * t)
    if "palm" in at:                                            # toron: split palm trunks, fibrous, grey
        r = at["palm"]
        sl, u, v = _grid(pr, "palm")
        rng = _rng(seed, "palm", "fibre")
        pr.base("palm", PALM)
        fib = _noise(rng, u, v, 0.012, 0.35)
        f = 1.0 + 0.22 * fib + 0.1 * _noise(rng, u, v, 0.15, 0.6)
        _apply(pr, "palm", sl, f, fib, 0.003)
        pr.tone("palm", 0.0, 0.0, r.world_w, 0.08, 0.7)
    if "roof_flat" in at:                                       # trodden earth, cracks, the paths of feet
        r = at["roof_flat"]
        pr.base("roof_flat", ROOF)
        hand_plaster(pr, "roof_flat", seed + 5, k=0.12, fingers=0.03, tilt=1.0, straw=1.0)
        pr.cracks("roof_flat", 0.3, 0.26, keep=0.55)
        pr.blotch("roof_flat", 0.0, 0.0, r.world_w, r.world_h, 0.9, 0.07)
    if "dome" in at:                                            # the dome: plastered in long downward sweeps
        r = at["dome"]
        pr.base("dome", DOME)
        hand_plaster(pr, "dome", seed + 6, k=0.15, fingers=0.08, tilt=0.05)
        gullies(pr, "dome", r.world_w, r.world_h, seed + 6, n_per_m=1.2, k=0.12)
    if "yard" in at:                                            # swept sand, pebbles, darker where trodden
        r = at["yard"]
        sl, u, v = _grid(pr, "yard")
        rng = _rng(seed, "yard", "sand")
        pr.base("yard", SAND)
        f = 1.0 + 0.1 * _noise(rng, u, v, 1.4, 1.4) + 0.09 * _noise(rng, u, v, 0.12, 0.12) + 0.07 * _noise(rng, u, v, 0.05, 0.05)
        swept = np.sin((u * 0.8 + v * 0.3 + 0.4 * _noise(rng, u, v, 0.6, 0.6)) * 9.0)   # the broom's arcs
        f = f + 0.035 * swept
        _apply(pr, "yard", sl, f, f - 1.0, 0.01)
        rg = _rng(seed, "yard", "gravel")
        grit = np.clip(_noise(rg, u, v, 0.05, 0.05) * 1.6, -1.0, 1.0)      # gravel, its stones lit on top
        clods = np.clip(_noise(rg, u, v, 0.16, 0.14) * 1.4, -1.0, 1.0)      # and clods of earth among it
        d = max(1, int(round(0.025 * pr.px_per_m)))
        lit = grit - np.roll(grit, d, 0) + 0.8 * (clods - np.roll(clods, 2 * d, 0))
        _apply(pr, "yard", sl, 1.0 + 0.14 * grit + 0.1 * clods + 0.3 * lit, grit + clods, 0.008)
        rr = random.Random(zlib.crc32(f"{seed}/yard/stones".encode()))
        for _ in range(int(r.world_w * r.world_h * 3)):
            a, b = rr.uniform(0, r.world_w), rr.uniform(0, r.world_h)
            s = rr.uniform(0.05, 0.14)
            pr.tone("yard", a, b - s * 0.25, min(r.world_w, a + s), b, 0.72)
            pr.tone("yard", a, b, min(r.world_w, a + s), min(r.world_h, b + s * 0.7), rr.choice((1.16, 1.24, 0.9)))
    if "thatch" in at:                                          # palm-leaf mats and baskets: a diagonal weave
        r = at["thatch"]
        sl, u, v = _grid(pr, "thatch")
        rng = _rng(seed, "thatch", "weave")
        pr.base("thatch", (184, 154, 104))
        pr.blotch("thatch", 0.0, 0.0, r.world_w, r.world_h, 0.8, 0.12)      # faded by the sun, unevenly
        u_m = 0.0
        while u_m < r.world_w:                                  # mats sewn side by side
            pr.tone("thatch", u_m, 0.0, min(r.world_w, u_m + 0.05), r.world_h, 0.72)
            u_m += rng.uniform(0.7, 1.0)
        s = 0.045
        a, b = np.floor((u + v) / s), np.floor((u - v) / s)
        over = np.mod(a + b, 2.0)
        fa, fb = np.mod((u + v) / s, 1.0), np.mod((u - v) / s, 1.0)
        edge = np.minimum(np.minimum(fa, 1 - fa), np.minimum(fb, 1 - fb))
        f = (0.88 + 0.2 * over) * (0.8 + 0.2 * np.clip(edge / 0.25, 0.0, 1.0)) + 0.08 * _noise(rng, u, v, 0.4, 0.4)
        _apply(pr, "thatch", sl, f, over, 0.004)
    if "pot" in at:                                             # clay jars: fired red, a pale slip, a band
        r = at["pot"]
        sl, u, v = _grid(pr, "pot")
        rng = _rng(seed, "pot", "clay")
        pr.base("pot", (150, 86, 56))
        f = 1.0 + 0.1 * _noise(rng, u, v, 0.08, 0.08) + 0.12 * _noise(rng, u, v, 0.5, 0.5)
        _apply(pr, "pot", sl, f)
        for vb in (0.3, 0.55):
            pr.rect("pot", 0.0, vb, r.world_w, vb + 0.035, (96, 56, 40))
        pr.tone("pot", 0.0, 0.62, r.world_w, r.world_h, 1.18)
