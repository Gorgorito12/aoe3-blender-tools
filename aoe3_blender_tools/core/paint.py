# SPDX-License-Identifier: GPL-3.0-or-later
"""Paints the diffuse texture of a `building.Model` into its atlas.

Windows, doors, stone courses, slate, dentils and the rest are drawn from the real facade
measurements, so they line up with the geometry. Flat, even colour: no baked lighting, which the
game adds itself. Returns a uint8 RGB array of `texture_size` squared (top-left origin).
"""
import numpy as np

from .building import STOREY_H
from .canvas import Canvas


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def paint(model):
    p = model.params
    at = model.atlas
    cv = Canvas(at.size, (128, 128, 128))
    rng = np.random.default_rng(p.seed)
    C = p.colors
    WALL, WHITE, GLASS, WOOD = C["wall"], C["trim"], C["glass"], C["door"]
    WALL_LINE = _shade(WALL, 0.92)
    BAND = _shade(WALL, 1.035)
    SHADOW = _shade(WHITE, 0.7)
    GLASS_HI = tuple(min(255, int(v * 1.6)) for v in GLASS)

    def P(region, u, v):
        return at.px(region, u, v)

    def rect(region, u0, v0, u1, v1, fill=None, outline=None, width=1):
        (x0, y0), (x1, y1) = P(region, u0, v1), P(region, u1, v0)
        cv.rect(x0, y0, x1, y1, fill, outline, width)

    def hline(region, v, u0, u1, color, width=1):
        (x0, y), (x1, _) = P(region, u0, v), P(region, u1, v)
        cv.line(x0, y, x1, y, color, width)

    def vline(region, u, v0, v1, color, width=1):
        (x, y0), (_, y1) = P(region, u, v0), P(region, u, v1)
        cv.line(x, y0, x, y1, color, width)

    def fill(region, color):
        r = at[region]
        cv.rect(r.x, r.y, r.x + r.w, r.y + r.h, color)

    px_per_m = at.density
    lw = max(1, int(round(px_per_m * 0.035)))      # thick line ~3.5 cm

    # --- facades -----------------------------------------------------------------------------------
    def window(region, uc, v0, h, w=1.0, cap="flat"):
        rect(region, uc - w / 2 - 0.12, v0 - 0.08, uc + w / 2 + 0.12, v0 + h + 0.1, WHITE, SHADOW)
        rect(region, uc - w / 2 - 0.2, v0 - 0.16, uc + w / 2 + 0.2, v0 - 0.04, WHITE, SHADOW)
        rect(region, uc - w / 2, v0, uc + w / 2, v0 + h, GLASS)
        rect(region, uc - w / 2, v0 + h * 0.62, uc + w / 2, v0 + h, GLASS_HI)
        vline(region, uc, v0, v0 + h, WHITE, lw)
        for k in (1, 2):
            hline(region, v0 + h * k / 3, uc - w / 2, uc + w / 2, WHITE, lw)
        top = v0 + h + 0.1
        if cap == "pediment":
            cv.triangle([P(region, uc - w / 2 - 0.3, top), P(region, uc + w / 2 + 0.3, top),
                         P(region, uc, top + 0.45)], WHITE)
            hline(region, top, uc - w / 2 - 0.3, uc + w / 2 + 0.3, SHADOW)
        else:
            rect(region, uc - w / 2 - 0.25, top, uc + w / 2 + 0.25, top + 0.16, WHITE, SHADOW)

    def door(region, uc):
        w, h = 1.4, 2.6
        rect(region, uc - w / 2 - 0.18, 0, uc + w / 2 + 0.18, h + 0.15, WHITE, SHADOW)
        rect(region, uc - w / 2, 0, uc + w / 2, h - 0.55, WOOD)
        vline(region, uc, 0, h - 0.55, _shade(WOOD, 0.65), lw)
        for k in (0.35, 1.15):
            rect(region, uc - w / 2 + 0.12, k, uc - 0.08, k + 0.6, None, _shade(WOOD, 1.3), 2)
            rect(region, uc + 0.08, k, uc + w / 2 - 0.12, k + 0.6, None, _shade(WOOD, 1.3), 2)
        cx, cy = P(region, uc, h - 0.55)
        rx = w / 2 * px_per_m
        cv.ellipse(cx, cy, rx + lw, rx + lw, WHITE, upper_half=True)
        cv.ellipse(cx, cy, rx, rx, GLASS_HI, upper_half=True)
        rect(region, uc - w / 2, h - 0.62, uc + w / 2, h - 0.55, WHITE)

    def facade(region, spec):
        r = at[region]
        sw, sh = r.world_w, r.world_h
        fill(region, WALL)
        course, joint, n, v = 0.42, 1.15, 0, 0.42
        while v < sh - 0.4:                                  # stone courses
            hline(region, v, 0, sw, WALL_LINE)
            u = (n % 2) * joint / 2
            while u < sw:
                vline(region, u, v - course, v, WALL_LINE)
                u += joint
            v += course
            n += 1
        for side in (0, 1):                                  # quoins
            v, k = 0.0, 0
            while v < sh - 0.4:
                w = 0.45 if k % 2 == 0 else 0.3
                a, b = (0, w) if side == 0 else (sw - w, sw)
                rect(region, a, v, b, v + 0.42, _shade(WALL, 1.025), WALL_LINE)
                v += 0.42
                k += 1
        for s in range(1, p.storeys):                        # string courses, frieze
            vs = s * STOREY_H
            rect(region, 0, vs - 0.05, sw, vs + 0.2, BAND, WALL_LINE)
        rect(region, 0, sh - 0.4, sw, sh, BAND, WALL_LINE)
        for uc in spec["bays"]:
            for s in range(p.storeys):
                base = s * STOREY_H
                if s == 0:
                    if spec["door"] is not None and abs(uc - spec["door"]) < 0.01:
                        door(region, uc)
                    else:
                        window(region, uc, base + 0.8, 1.9, cap="pediment")
                else:
                    window(region, uc, base + 0.55, 1.65, cap="flat")

    for region, spec in model.facades.items():
        facade(region, spec)

    # --- pediment ----------------------------------------------------------------------------------
    if "pedi" in at:
        r = at["pedi"]
        pw, ph = r.world_w, r.world_h
        fill("pedi", WHITE)
        cv.line(*P("pedi", 0, 0.05), *P("pedi", pw, 0.05), SHADOW, 2 * lw)
        cv.line(*P("pedi", 0.05, 0.02), *P("pedi", pw / 2, ph - 0.02), SHADOW, 2 * lw)
        cv.line(*P("pedi", pw - 0.05, 0.02), *P("pedi", pw / 2, ph - 0.02), SHADOW, 2 * lw)
        if ph > 1.2:
            cx, cy = P("pedi", pw / 2, ph * 0.38)
            rr = 0.32 * px_per_m
            cv.ellipse(cx, cy, rr + lw * 1.5, rr + lw * 1.5, SHADOW)
            cv.ellipse(cx, cy, rr + lw * 0.5, rr + lw * 0.5, WHITE)
            cv.ellipse(cx, cy, rr, rr, GLASS)

    # --- roof slate --------------------------------------------------------------------------------
    ROOF = C["roof"]
    fill("roof", _shade(ROOF, 0.75))
    r = at["roof"]
    row, v, k = 0.24, 0.0, 0
    while v < r.world_h:
        u = -(k % 2) * 0.15
        while u < r.world_w:
            t = int(rng.integers(-9, 10))
            tile = tuple(max(0, min(255, c + t)) for c in ROOF)
            rect("roof", max(u, 0), v, min(u + 0.3, r.world_w), min(v + row, r.world_h), tile, _shade(ROOF, 0.75))
            u += 0.3
        v += row
        k += 1

    # --- small materials ---------------------------------------------------------------------------
    PL = C["plinth"]
    fill("plinth", PL)
    rp = at["plinth"]
    for vv in (0.0, rp.world_h / 2):
        hline("plinth", vv, 0, rp.world_w, _shade(PL, 0.78), lw)
        u = (vv / max(rp.world_h / 2, 1e-6)) * 0.5
        while u < rp.world_w:
            vline("plinth", u, vv, vv + rp.world_h / 2, _shade(PL, 0.78), lw)
            u += 1.0

    rt = at["trim"]
    fill("trim", WHITE)
    hline("trim", 0.02, 0, rt.world_w, SHADOW, lw)
    hline("trim", 0.3, 0, rt.world_w, _shade(WHITE, 0.93), lw)
    u = 0.05
    while u < rt.world_w - 0.1:
        rect("trim", u, 0.48, u + 0.1, 0.62, _shade(WHITE, 1.02), _shade(WHITE, 0.85))
        u += 0.2
    hline("trim", 0.7, 0, rt.world_w, _shade(WHITE, 0.93), lw)

    ST = C["stone"]
    fill("stone", ST)
    for i, vv in enumerate(np.arange(0, 4.0, 0.4)):
        hline("stone", vv, 0, 8, _shade(ST, 0.86))
        for uu in np.arange((i % 2) * 0.4, 8, 0.8):
            vline("stone", uu, vv, vv + 0.4, _shade(ST, 0.86))

    if "column" in at:
        rc = at["column"]
        fill("column", _shade(WHITE, 0.995))
        for i in range(20):
            vline("column", rc.world_w * (i + 0.5) / 20, 0, rc.world_h, _shade(WHITE, 0.92), lw)

    BR = C["brick"]
    fill("brick", (190, 180, 170))
    for j, vv in enumerate(np.arange(0, 3.0, 0.09)):
        off = (j % 2) * 0.12
        for uu in np.arange(-off, 4.0, 0.25):
            t = int(rng.integers(-12, 12))
            rect("brick", max(uu + 0.01, 0), vv + 0.012, min(uu + 0.24, 4.0), min(vv + 0.08, 3.0),
                 tuple(max(0, min(255, c + t)) for c in BR))

    fill("cupwin", WHITE)
    rect("cupwin", 0.2, 0.25, 0.6, 1.05, GLASS)
    cx, cy = P("cupwin", 0.4, 1.05)
    cv.ellipse(cx, cy, 0.2 * px_per_m, 0.2 * px_per_m, GLASS, upper_half=True)
    rect("cupwin", 0.0, 0.0, 0.8, 0.12, _shade(WHITE, 0.94))

    fill("white", WHITE)

    if "reveal" in at:                       # inside of the recessed openings: wall stone, darker
        rr = at["reveal"]
        fill("reveal", _shade(WALL, 0.86))
        for vv in np.arange(0.42, rr.world_h, 0.42):
            hline("reveal", vv, 0, rr.world_w, _shade(WALL, 0.8))
    if "balus" in at:                        # balustrade: base and rail with turned balusters
        rb = at["balus"]
        GAP = _shade(WHITE, 0.55)
        fill("balus", GAP)
        rect("balus", 0, 0, rb.world_w, 0.15, WHITE, SHADOW)
        rect("balus", 0, 0.6, rb.world_w, rb.world_h, WHITE, SHADOW)
        u = 0.06
        while u < rb.world_w - 0.12:
            cxp, _ = P("balus", u + 0.06, 0)
            for (v0, v1, half) in ((0.15, 0.22, 0.05), (0.22, 0.42, 0.065), (0.42, 0.52, 0.04), (0.52, 0.6, 0.055)):
                rect("balus", u + 0.06 - half, v0, u + 0.06 + half, v1, WHITE)
            u += 0.22
    LE = C["lead"]
    fill("lead", LE)
    for uu in np.arange(0, 7.0, 7.0 / 16):
        vline("lead", uu, 0, 2.5, _shade(LE, 0.83), lw)

    cv.noise(5, seed=p.seed)
    return cv.downsample(at.size // p.texture_size)


def save_png(array, path):
    """Writes an RGB uint8 array as PNG with the standard library only (zlib)."""
    import struct
    import zlib

    h, w, _ = array.shape
    raw = b"".join(b"\x00" + array[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)

