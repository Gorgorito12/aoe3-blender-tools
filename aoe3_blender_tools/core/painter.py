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
        name, tile_m, _ = entry
        px = max(4, int(round(tile_m * self.px_per_m)))
        if (name, px) not in self._factors:
            self._factors[(name, px)] = materials.normalise(sw, px)
        r = self.at[region]
        block = materials.tile(self.cv.a, (r.x, r.y, r.x + r.w, r.y + r.h), self._factors[(name, px)],
                               color, offset=(r.x, r.y))
        if block is not None:
            self.layers.append((max(0, r.x), max(0, r.y), block.copy()))

    def tone(self, region, u0, v0, u1, v1, k):
        """Darkens (k < 1) or lightens a rect of a region, keeping any grain under it."""
        (x0, y0), (x1, y1) = self.P(region, u0, v1), self.P(region, u1, v0)
        xa, ya, xb, yb = self.cv._box(x0, y0, x1, y1)
        materials.multiply(self.cv.a, (xa, ya, xb, yb), k)

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
        self.cv.noise(5, seed=p.seed)
        rgb = self.cv.downsample(k)
        alpha = self.mk.downsample(k)[:, :, 0] if self.mk is not None else np.full(rgb.shape[:2], 255, np.uint8)
        if cover is None:
            cov = np.zeros(rgb.shape[:2], np.uint8)
        else:
            n = cover.shape[0] // k
            cov = (cover[:n * k, :n * k].reshape(n, k, n, k).mean(axis=(1, 3)) * 255 + 0.5).astype(np.uint8)
        return rgb, alpha, cov
