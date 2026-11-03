# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawing surface a style paints its texture on: the atlas canvas at twice the final size,
the player-colour mask, the seeded random generator, and drawing calls in region coordinates
(metres, u right, v up). Pure Python with numpy; imports no style."""
import numpy as np

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
        """The ground of a region: its colour (the material layer will tile a swatch here)."""
        self.fill(region, color)

    def finish(self):
        """Noise, the filter down to the final size: (rgb, alpha)."""
        p = self.p
        self.cv.noise(5, seed=p.seed)
        k = self.at.size // p.texture_size
        rgb = self.cv.downsample(k)
        alpha = self.mk.downsample(k)[:, :, 0] if self.mk is not None else np.full(rgb.shape[:2], 255, np.uint8)
        return rgb, alpha
