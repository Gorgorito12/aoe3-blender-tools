# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawing surface a style paints its texture on: the atlas canvas at twice the final size,
the player-colour mask, the seeded random generator, and drawing calls in region coordinates
(metres, u right, v up). Pure Python with numpy; imports no style."""
import numpy as np

from . import materials
from .canvas import Canvas

PLAYER_GREY = (206, 206, 206)       # what the stock textures hold under their player-colour mask


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


class Painter:
    def __init__(self, model):
        p = model.params
        self.model = model
        self.p = p
        self.at = model.atlas
        self.cv = Canvas(self.at.size, (128, 128, 128))
        self.rng = np.random.default_rng(p.seed)
        self.C = p.colors
        self.pc = getattr(p, "player_colour", False)
        self.mk = Canvas(self.at.size, (255, 255, 255)) if self.pc else None
        self.px_per_m = self.at.density
        self.lw = max(1, int(round(self.px_per_m * 0.035)))      # thick line ~3.5 cm
        self.use_materials = bool(getattr(p, "materials", False))
        self.layers = []            # (x, y, block) of each swatch laid: the coverage at the end
        self.swatched = {}          # region -> the colour its swatch was tinted with
        self.bleeds = False         # spread the regions over the empty atlas at the end
        self._factors = {}

    def P(self, region, u, v):
        return self.at.px(region, u, v)

    def rect(self, region, u0, v0, u1, v1, fill=None, outline=None, width=1):
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        self.cv.rect(x0, y0, x1, y1, fill, outline, width)

    def hline(self, region, v, u0, u1, color, width=1):
        (x0, y), (x1, _) = self.P(region, u0, v), self.P(region, u1, v)
        self.cv.line(x0, y, x1, y, color, width)

    def vline(self, region, u, v0, v1, color, width=1):
        (x, y0), (_, y1) = self.P(region, u, v0), self.P(region, u, v1)
        self.cv.line(x, y0, x, y1, color, width)

    def mark(self, region, u0, v0, u1, v1):
        """A player-colour part: black on the mask."""
        if self.mk is not None:
            (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
            self.mk.rect(x0, y0, x1, y1, (0, 0, 0))

    def fill(self, region, color):
        r = self.at[region]
        self.cv.rect(r.x, r.y, r.x + r.w, r.y + r.h, color)

    def base(self, region, color, role=None):
        """The ground of a region: its colour, and with `params.materials` the swatch of `role`
        (core.materials) tinted with that colour, so the mean stays the colour. Everything drawn
        afterwards covers the swatch as usual."""
        self.fill(region, color)
        if not self.use_materials or role is None:
            return
        entry = materials.plan(self.p.style).get(role)
        sw = materials.load(entry[0]) if entry else None
        if sw is None:
            return
        name, tile_m, _, contrast = entry
        px = max(4, int(round(tile_m * self.px_per_m)))
        if (name, px, contrast) not in self._factors:
            self._factors[(name, px, contrast)] = materials.normalise(sw, px, contrast)
        r = self.at[region]
        block = materials.tile(self.cv.a, (r.x, r.y, r.x + r.w, r.y + r.h), self._factors[(name, px, contrast)],
                               color, offset=(r.x, r.y))
        if block is not None:
            self.layers.append((max(0, r.x), max(0, r.y), block.copy()))
            self.swatched[region] = (tuple(float(c) for c in color), len(self.layers) - 1)

    def paint_on(self, region, u0, v0, u1, v1, color, outline=None, width=1):
        """A rect of `color`; on a region with a swatch, the colour is laid by multiplying the
        ground (so the grain shows through), and the outline stays flat. Without a swatch it is
        exactly `rect`."""
        entry = self.swatched.get(region)
        if entry is None:
            self.rect(region, u0, v0, u1, v1, color, outline, width)
            return
        base, layer = entry
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        xa, ya, xb, yb = self.cv._box(x0, y0, x1, y1)
        r = self.at[region]                          # never beyond the region's own pixels
        xa, ya, xb, yb = max(xa, r.x), max(ya, r.y), min(xb, r.x + r.w), min(yb, r.y + r.h)
        if xb > xa and yb > ya:
            k = np.array([c / max(b, 1.0) for c, b in zip(color, base)], np.float32)
            self.cv.a[ya:yb, xa:xb] *= k
            lx, ly, block = self.layers[layer]       # the reference follows, for the coverage
            block[max(0, ya - ly):max(0, yb - ly), max(0, xa - lx):max(0, xb - lx)] *= k
        if outline is not None:
            self.rect(region, u0, v0, u1, v1, None, outline, width)

    def tone(self, region, u0, v0, u1, v1, k):
        """Darkens (k < 1) or lightens a rect of a region, keeping any grain under it."""
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        xa, ya, xb, yb = self.cv._box(x0, y0, x1, y1)
        materials.multiply(self.cv.a, (xa, ya, xb, yb), k)

    def facet(self, region, pts, k, above=None):
        """Multiplies a triangle by `k`, its corners in metres on the region: the flat chips and
        trowel marks a rectangle cannot draw. `above`: only on pixels brighter than this."""
        (ax, ay), (bx, by), (cx, cy) = (self.P(region, u, v) for u, v in pts)
        h, w = self.cv.a.shape[:2]
        x0, x1 = max(0, int(min(ax, bx, cx))), min(w, int(max(ax, bx, cx)) + 1)
        y0, y1 = max(0, int(min(ay, by, cy))), min(h, int(max(ay, by, cy)) + 1)
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if x1 <= x0 or y1 <= y0 or abs(area) < 1e-6:
            return
        ys, xs = np.mgrid[y0:y1, x0:x1]
        e0 = ((bx - ax) * (ys - ay) - (by - ay) * (xs - ax)) / area
        e1 = ((cx - bx) * (ys - by) - (cy - by) * (xs - bx)) / area
        e2 = ((ax - cx) * (ys - cy) - (ay - cy) * (xs - cx)) / area
        inside = (e0 >= 0) & (e1 >= 0) & (e2 >= 0)
        if above is not None:
            inside &= self.cv.a[y0:y1, x0:x1].mean(axis=2) > above
        self.cv.a[y0:y1, x0:x1][inside] *= k

    def _noise(self, h, w, cell_m):
        """Smooth noise from -1 to 1 for an area of h x w pixels, blobs about `cell_m` across."""
        c = max(2.0, cell_m * self.px_per_m)
        ny, nx = int(h / c) + 3, int(w / c) + 3
        g = self.rng.uniform(-1.0, 1.0, (ny, nx)).astype(np.float32)
        ys, xs = np.arange(h, dtype=np.float32) / c, np.arange(w, dtype=np.float32) / c
        iy, ix = ys.astype(int), xs.astype(int)
        fy, fx = ys - iy, xs - ix
        fy, fx = (fy * fy * (3 - 2 * fy))[:, None], (fx * fx * (3 - 2 * fx))[None, :]
        top = g[iy][:, ix] * (1 - fx) + g[iy][:, ix + 1] * fx
        bot = g[iy + 1][:, ix] * (1 - fx) + g[iy + 1][:, ix + 1] * fx
        return top * (1 - fy) + bot * fy

    def blotch(self, region, u0, v0, u1, v1, cell_m, k, above=None):
        """Soft clouds of wear inside a box: up to `k` lighter, or that much darker and browner, as
        earth rubbed into pale stone. `above`: only on pixels brighter than this, so a pale shape
        wears inside its own edges."""
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        xa, ya, xb, yb = self.cv._box(x0, y0, x1, y1)
        if xb - xa < 2 or yb - ya < 2:
            return
        m = self._noise(yb - ya, xb - xa, cell_m)
        dark = np.clip(-m, 0.0, 1.0)
        f = np.stack([1.0 + k * m, (1.0 + k * m) * (1 - 0.05 * dark), (1.0 + k * m) * (1 - 0.13 * dark)], axis=2)
        area = self.cv.a[ya:yb, xa:xb]
        if above is None:
            area *= f
        else:
            area[:] = np.where(area.mean(axis=2, keepdims=True) > above, area * f, area)

    def mottle(self, region, cell_m, k, hard=False):
        """A soft uneven tone over a region, blobs about `cell_m` across, up to `k` either way: the
        life of hand-laid plaster. `hard`: patches with an edge, lighter by `k`, as worn or
        re-laid earth. Multiplies what is there."""
        r = self.at[region]
        x0, y0, w, h = int(r.x), int(r.y), int(r.w), int(r.h)
        if w < 2 or h < 2:
            return
        m = self._noise(h, w, cell_m)
        if hard:
            m = np.clip((m - 0.12) * 9.0, 0.0, 1.0)
        self.cv.a[y0:y0 + h, x0:x0 + w] *= (1.0 + k * m)[:, :, None]

    def _cells(self, w, h, c, warp=None):
        """Jittered cells about `c` pixels across over w x h pixels. `warp` (an (x, y) pair of arrays)
        moves each pixel first, so the edges bend. Returns the distances to the nearest two centres,
        the nearest one as (index, x from it, y from it), the grid cell of each pixel and the size
        of the grid."""
        nx, ny = int(w / c) + 3, int(h / c) + 3
        pts = (np.stack(np.meshgrid(np.arange(nx), np.arange(ny)), -1) + self.rng.uniform(0.1, 0.9, (ny, nx, 2))) * c
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        if warp is not None:
            xx, yy = xx + warp[0], yy + warp[1]
        ix, iy = (xx / c).astype(int), (yy / c).astype(int)
        d1 = np.full((h, w), 1e9, np.float32)
        d2 = np.full((h, w), 1e9, np.float32)
        near = np.zeros((h, w), np.int32)
        for dy in (-1, 0, 1, 2):
            for dx in (-1, 0, 1, 2):
                jx, jy = np.clip(ix + dx, 0, nx - 1), np.clip(iy + dy, 0, ny - 1)
                p = pts[jy, jx]
                d = np.hypot(xx - p[..., 0], yy - p[..., 1])
                closer = d < d1
                d2 = np.where(closer, d1, np.minimum(d2, d))
                d1 = np.where(closer, d, d1)
                near = np.where(closer, jy * nx + jx, near)
        return d1, d2, (near, xx - pts[..., 0].ravel()[near], yy - pts[..., 1].ravel()[near]), ix, iy, nx, ny

    def rough_stone(self, region, u0, v0, u1, v1, cell_m, k, joint=0.18, width_m=0.028):
        """Rough stone inside a box: small rounded stones about `cell_m` across, in no order, each
        with a tone of its own and its upper side catching the light, about `k` either way. Thin
        joints, darkened by up to `joint` and `width_m` wide, with a worn pale rim beside them, come
        and go. Chips a third the size lie over all, a few of them pale flecks with a clear edge.
        Warmest where pale. Multiplies what is there."""
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        xa, ya, xb, yb = self.cv._box(x0, y0, x1, y1)
        w, h = xb - xa, yb - ya
        if w < 4 or h < 4:
            return
        c = max(3.0, cell_m * self.px_per_m)
        warp = (self._noise(h, w, cell_m * 0.8) * c * 0.3, self._noise(h, w, cell_m * 0.8) * c * 0.3)
        d1, d2, (near, _, oy), ix, iy, nx, ny = self._cells(w, h, c, warp)
        tone = self.rng.uniform(-1.0, 1.0, nx * ny).astype(np.float32)
        t = max(1.2, width_m * self.px_per_m) * (1.0 + 0.5 * self._noise(h, w, cell_m * 0.5))
        gap = (d2 - d1) / t
        gate = np.clip(0.45 + 1.2 * self._noise(h, w, cell_m * 1.2), 0.0, 1.0)
        _, _, (small, _, _), _, _, sx, sy = self._cells(w, h, max(3.0, c / 3), warp)
        chips = self.rng.uniform(-1.0, 1.0, sx * sy).astype(np.float32)
        a = (k * (0.7 * tone[near] - 0.7 * np.clip(oy / c, -0.7, 0.7) + 0.6 * self._noise(h, w, cell_m * 3.0)
                  + 0.45 * chips[small] + 0.7 * (chips[small] > 0.72))
             + 0.7 * joint * np.clip(1.0 - np.abs(gap - 2.2) / 1.2, 0.0, 1.0) * gate
             + 0.05 * self._noise(h, w, cell_m * 0.3))
        dim = 1.0 - joint * np.clip(1.0 - gap, 0.0, 1.0) * gate
        self.cv.a[ya:yb, xa:xb] *= np.stack([(1.0 + a) * dim, (1.0 + 1.1 * a) * dim, (1.0 + 1.3 * a) * dim], axis=2)

    def cracks(self, region, cell_m=0.16, depth=0.4, width_m=0.012, keep=0.75):
        """A network of fine cracks over a region, as dried mud or old plaster shows: the edges of
        jittered cells (`cell_m` across), darkened by `depth`, `width_m` wide; about `keep` of the
        edges are drawn (a smooth noise leaves some cells open). Multiplies what is there."""
        r = self.at[region]
        x0, y0, w, h = int(r.x), int(r.y), int(r.w), int(r.h)
        if w < 4 or h < 4:
            return
        c = max(3.0, cell_m * self.px_per_m)
        rng = self.rng
        d1, d2, _, ix, iy, nx, ny = self._cells(w, h, c)
        t = max(0.8, width_m * self.px_per_m)
        edge = np.clip(1.0 - (d2 - d1) / t, 0.0, 1.0)
        n = rng.uniform(0, 1, (ny // 2 + 2, nx // 2 + 2)).astype(np.float32)   # open some cells
        gate = n[np.clip(iy // 2, 0, n.shape[0] - 1), np.clip(ix // 2, 0, n.shape[1] - 1)] < keep
        k = 1.0 - depth * edge * gate
        self.cv.a[y0:y0 + h, x0:x0 + w] *= k[:, :, None]

    def bleed(self, reach=32):
        """Spreads the edge of each region over the empty atlas round it, picture and mask, so
        that halving the texture and its mipmaps never brings the background into a seam."""
        full = np.zeros(self.cv.a.shape[:2], bool)
        for r in self.at.regions.values():
            full[r.y:r.y + r.h, r.x:r.x + r.w] = True
        for _ in range(reach):
            for axis, step in ((0, 1), (0, -1), (1, 1), (1, -1)):
                new = np.roll(full, step, axis) & ~full
                self.cv.a[new] = np.roll(self.cv.a, step, axis)[new]
                if self.mk is not None:
                    self.mk.a[new] = np.roll(self.mk.a, step, axis)[new]
                full |= new

    def coverage(self):
        """Where a swatch still shows (1.0) at the painting size, before the noise."""
        cm = np.zeros(self.cv.a.shape[:2], np.float32)
        for x, y, block in self.layers:
            h, w = block.shape[:2]
            cm[y:y + h, x:x + w] = (np.abs(self.cv.a[y:y + h, x:x + w] - block).max(axis=2) < 0.5)
        return cm

    def finish(self):
        """Noise, the filter down to the final size: (rgb, alpha, coverage), coverage 0..255 where
        a swatch shows (all 0 without materials)."""
        p = self.p
        k = self.at.size // p.texture_size
        cover = self.coverage() if self.layers else None
        if self.bleeds:
            self.bleed()
        self.cv.noise(5, seed=p.seed)
        rgb = self.cv.downsample(k)
        alpha = self.mk.downsample(k)[:, :, 0] if self.mk is not None else np.full(rgb.shape[:2], 255, np.uint8)
        if cover is None:
            cov = np.zeros(rgb.shape[:2], np.uint8)
        else:
            n = cover.shape[0] // k
            cov = (cover[:n * k, :n * k].reshape(n, k, n, k).mean(axis=(1, 3)) * 255 + 0.5).astype(np.uint8)
        return rgb, alpha, cov
