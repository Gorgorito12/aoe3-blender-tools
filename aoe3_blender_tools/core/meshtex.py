# SPDX-License-Identifier: GPL-3.0-or-later
"""Repainting the texture of a mesh the generator did not make: someone else's model, with their
own UVs and their own material slots.

core/airepaint.py repaints a Model's atlas regions. A mesh authored elsewhere has no regions, so
this module builds a stand-in of the same shape: one zone per material slot (the bounding box of
that slot's UVs) or one zone over the whole image, each with its own prompt. Everything below it
is unchanged - the tiles, the ControlNet, the edge guard, the mean colour, the player-colour mask.

    zones = [("roof", 0.0, 0.5, 1.0, 1.0), ("walls", 0.0, 0.0, 1.0, 0.5)]
    model = model_for(zones, 1024, prompts={"roof": "rusted corrugated iron"})
    out, report = airepaint.repaint(texture, model, client, prompt=None)

Pure Python with numpy: no Blender import (core/blender_io.py reads the zones off the mesh).
"""
from dataclasses import dataclass, field

from .airepaint import MIN_SIDE
from .atlas import Region

WHOLE = "all"


@dataclass
class MeshParams:
    """What airepaint reads off a Model's params. `prompts` gives each zone its own text;
    material_of() prefers it over the built-in tables, so a style name is never guessed."""
    style: str = "MESH"
    prompts: dict = field(default_factory=dict)
    player_colour: bool = False


class ZoneAtlas:
    """An atlas whose regions are pixel rectangles of an existing texture, not packed by us."""

    def __init__(self, size, zones):
        self.size = size
        self.regions = {z.name: z for z in zones}
        self.density = 1.0

    def __getitem__(self, name):
        return self.regions[name]

    def __contains__(self, name):
        return name in self.regions


@dataclass
class MeshModel:
    """The little of a Model that repainting needs."""
    params: MeshParams
    atlas: ZoneAtlas
    faces: tuple = ()
    attach: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def zone_regions(zones, size, *, margin=2, min_side=MIN_SIDE):
    """[(name, u0, v0, u1, v1)] in 0..1 (v up, as a UV map) -> pixel Regions of a `size` square
    texture, top row first, grown by `margin` px and clamped. Zones thinner than `min_side` are
    dropped: the repaint would skip them anyway, and a stray one-pixel region only confuses the
    list. Returns (regions, dropped)."""
    out, dropped = [], []
    for name, u0, v0, u1, v1 in zones:
        x0 = int(max(0, round(min(u0, u1) * size) - margin))
        x1 = int(min(size, round(max(u0, u1) * size) + margin))
        y0 = int(max(0, round((1.0 - max(v0, v1)) * size) - margin))
        y1 = int(min(size, round((1.0 - min(v0, v1)) * size) + margin))
        w, h = x1 - x0, y1 - y0
        if min(w, h) < min_side:
            dropped.append((name, w, h))
            continue
        out.append(Region(name, float(w), float(h), x0, y0, w, h))
    return out, dropped


def model_for(zones, size, *, prompts=None, player_colour=False, margin=2):
    """A stand-in Model for `airepaint.repaint` over someone else's texture. `zones` as in
    zone_regions, or None for one zone over the whole square. Raises when nothing is left to
    repaint, with the sizes that were dropped."""
    if zones is None:
        zones = [(WHOLE, 0.0, 0.0, 1.0, 1.0)]
    regions, dropped = zone_regions(zones, size, margin=margin)
    if not regions:
        sizes = ", ".join(f"{n} {w} x {h}" for n, w, h in dropped)
        raise ValueError(f"no UV zone is at least {MIN_SIDE} px ({sizes or 'none found'})")
    params = MeshParams(prompts=dict(prompts or {}), player_colour=player_colour)
    return MeshModel(params=params, atlas=ZoneAtlas(size, regions))


def is_mesh_model(model):
    """True for a stand-in built here (the panel and the export treat it differently)."""
    return isinstance(getattr(model, "params", None), MeshParams)
