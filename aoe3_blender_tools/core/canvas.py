# SPDX-License-Identifier: GPL-3.0-or-later
"""A small raster canvas on numpy (Blender bundles numpy, not Pillow).

Coordinates are pixels with a top-left origin, like an image. Colours are RGB tuples 0..255.
"""
import numpy as np


class Canvas:
    def __init__(self, size, color=(128, 128, 128)):
        self.size = size
        self.a = np.empty((size, size, 3), dtype=np.float32)
        self.a[:] = color

    # -- helpers -------------------------------------------------------------------------------
    def _box(self, x0, y0, x1, y1):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        xa = max(0, int(round(xa)))
        ya = max(0, int(round(ya)))
        xb = min(self.size, int(round(xb)))
        yb = min(self.size, int(round(yb)))
        return xa, ya, xb, yb

    # -- primitives ----------------------------------------------------------------------------
    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1):
        xa, ya, xb, yb = self._box(x0, y0, x1, y1)
        if xb <= xa or yb <= ya:
            return
        if fill is not None:
            self.a[ya:yb, xa:xb] = fill
        if outline is not None:
            w = max(1, int(width))
            self.a[ya:min(ya + w, yb), xa:xb] = outline
            self.a[max(yb - w, ya):yb, xa:xb] = outline
            self.a[ya:yb, xa:min(xa + w, xb)] = outline
            self.a[ya:yb, max(xb - w, xa):xb] = outline

    def line(self, x0, y0, x1, y1, color, width=1):
        w = max(1.0, float(width))
        if abs(y1 - y0) < 0.5:                       # horizontal
            self.rect(min(x0, x1), y0 - w / 2, max(x0, x1) + 1, y0 + w / 2, color)
            return
        if abs(x1 - x0) < 0.5:                       # vertical
            self.rect(x0 - w / 2, min(y0, y1), x0 + w / 2, max(y0, y1) + 1, color)
            return
        n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for t in np.linspace(0.0, 1.0, n):
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            self.rect(x - w / 2, y - w / 2, x + w / 2, y + w / 2, color)

    def triangle(self, pts, fill):
        (ax, ay), (bx, by), (cx, cy) = pts
        xa, ya, xb, yb = self._box(min(ax, bx, cx), min(ay, by, cy), max(ax, bx, cx) + 1, max(ay, by, cy) + 1)
        if xb <= xa or yb <= ya:
            return
        ys, xs = np.mgrid[ya:yb, xa:xb].astype(np.float32) + 0.5

        def edge(px, py, qx, qy):
            return (qx - px) * (ys - py) - (qy - py) * (xs - px)

        e0, e1, e2 = edge(ax, ay, bx, by), edge(bx, by, cx, cy), edge(cx, cy, ax, ay)
        m = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        self.a[ya:yb, xa:xb][m] = fill

    def ellipse(self, cx, cy, rx, ry, fill, upper_half=False):
        xa, ya, xb, yb = self._box(cx - rx, cy - ry, cx + rx + 1, (cy if upper_half else cy + ry) + 1)
        if xb <= xa or yb <= ya:
            return
        ys, xs = np.mgrid[ya:yb, xa:xb].astype(np.float32) + 0.5
        m = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1.0
        if upper_half:
            m &= ys <= cy
        self.a[ya:yb, xa:xb][m] = fill

    # -- finishing -----------------------------------------------------------------------------
    def noise(self, amount, seed=0):
        rng = np.random.default_rng(seed)
        self.a += rng.integers(-amount, amount + 1, size=self.a.shape[:2])[..., None].astype(np.float32)

    def downsample(self, factor):
        """Box filter by an integer factor; returns a uint8 RGB array."""
        a = np.clip(self.a, 0, 255)
        if factor > 1:
            s = self.size // factor
            a = a[: s * factor, : s * factor].reshape(s, factor, s, factor, 3).mean(axis=(1, 3))
        return a.round().astype(np.uint8)
