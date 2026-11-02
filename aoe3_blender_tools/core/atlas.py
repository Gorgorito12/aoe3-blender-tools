# SPDX-License-Identifier: GPL-3.0-or-later
"""UV atlas: named regions, each covering a rectangle of world space (metres), packed into one
square texture at a uniform texel density. Pure Python: no Blender import."""
from dataclasses import dataclass


@dataclass
class Region:
    name: str
    world_w: float      # metres covered horizontally
    world_h: float      # metres covered vertically
    x: int = 0          # pixel rect in the atlas (top-left origin, like an image)
    y: int = 0
    w: int = 0
    h: int = 0


class Atlas:
    """Shelf-packs the regions at the largest density that fits `size` pixels."""

    PAD = 4

    def __init__(self, size, regions):
        self.size = size
        self.regions = {r.name: r for r in regions}
        self.density = self._pack()

    def _try(self, density):
        x = y = shelf = 0
        order = sorted(self.regions.values(), key=lambda r: -r.world_h)
        for r in order:
            w = max(8, int(r.world_w * density))
            h = max(8, int(r.world_h * density))
            if w > self.size:
                return False
            if x + w > self.size:
                x, y, shelf = 0, y + shelf + self.PAD, 0
            if y + h > self.size:
                return False
            r.x, r.y, r.w, r.h = x, y, w, h
            x += w + self.PAD
            shelf = max(shelf, h)
        return True

    def _pack(self):
        lo, hi = 1.0, float(self.size)
        for _ in range(40):
            mid = (lo + hi) / 2
            if self._try(mid):
                lo = mid
            else:
                hi = mid
        if not self._try(lo):
            raise ValueError("atlas: the regions do not fit")
        return lo

    def __getitem__(self, name):
        return self.regions[name]

    def __contains__(self, name):
        return name in self.regions

    def uv(self, name, u, v):
        """World coordinates inside a region (u right, v up, metres) -> texture UV (0..1, v up)."""
        r = self.regions[name]
        if u < -1e-4 or v < -1e-4 or u > r.world_w + 1e-4 or v > r.world_h + 1e-4:
            raise ValueError(f"{name}: local ({u:.2f}, {v:.2f}) outside {r.world_w:.2f} x {r.world_h:.2f}")
        px = r.x + u / r.world_w * r.w
        py = r.y + r.h - v / r.world_h * r.h
        return (px / self.size, 1.0 - py / self.size)

    def px(self, name, u, v, scale=1.0):
        """World coordinates inside a region -> pixel coordinates in an image `scale` times the atlas."""
        r = self.regions[name]
        return ((r.x + u / r.world_w * r.w) * scale, (r.y + r.h - v / r.world_h * r.h) * scale)
