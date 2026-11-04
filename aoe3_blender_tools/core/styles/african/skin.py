# SPDX-License-Identifier: GPL-3.0-or-later
"""The logic of the African skins: what each surface of a building is made of and how it ages, in
one table, so a roof never reads as a wall.

Real earthen buildings have a reason for each finish. Walls are thrown by hand and weather: rough,
cracked, stained, dark at the foot where rain splashes. A flat roof is trodden and renewed every
year: smooth, sun-bleached, with few fine cracks. A dome is plastered like a roof. A parapet takes
the same smooth coat as the roof it guards. Each row of SURFACES says that; `coat` lays it."""
from ...painter import _shade

SUN = (228, 214, 190)                   # what the sun bleaches earth towards


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def colours(C):
    """Surface -> colour, from the building's palette."""
    mud, adobe = C["mud"], C["adobe"]
    return {"wall_mud": mud, "wall_adobe": adobe, "roof_flat": mix(adobe, SUN, 0.5), "dome": mix(mud, SUN, 0.32),
            "parapet": mix(adobe, SUN, 0.25), "trim": _shade(adobe, 0.94)}


# surface -> material role (core.materials), cracks (cell m, depth, share kept), stains (per m2,
# strength, size)
SURFACES = {
    "wall_mud": {"role": "wall", "cracks": (0.15, 0.5, 0.75), "stains": (0.3, 0.07, 1.0)},
    "wall_adobe": {"role": "adobe", "cracks": (0.3, 0.22, 0.4), "stains": (0.35, 0.15, 1.6)},
    "roof_flat": {"role": "roofmud", "cracks": (0.5, 0.1, 0.3), "stains": (0.03, 0.05, 2.5)},
    "dome": {"role": "roofmud", "cracks": (0.3, 0.16, 0.45), "stains": (0.08, 0.06, 1.5)},
    "parapet": {"role": "roofmud", "cracks": None, "stains": (0.1, 0.05, 1.0)},
    "trim": {"role": "adobe", "cracks": (0.3, 0.22, 0.4), "stains": None},
}


def stains(pr, region, w, h, n, k=0.12, size=1.0):
    """Soft broad patches a little darker or lighter (weathering): nested rects, each multiplying
    what is there, so the grain stays. `size` scales them."""
    rng = pr.rng
    for _ in range(n):
        cu, cv = float(rng.uniform(0, w)), float(rng.uniform(0, h))
        sw, sh = float(rng.uniform(0.4, 1.6)) * size, float(rng.uniform(0.3, 1.0)) * size
        f = 1 + float(rng.uniform(-k, k * 0.5))
        for j in range(4):
            t = 1 - j / 4
            pr.tone(region, max(0.0, cu - sw * t / 2), max(0.0, cv - sh * t / 2), min(w, cu + sw * t / 2),
                    min(h, cv + sh * t / 2), 1 + (f - 1) / 4)


def coat(pr, region, surface, cols):
    """Lays a surface's finish on a region: its ground, cracks and stains."""
    s = SURFACES[surface]
    r = pr.at[region]
    pr.base(region, cols[surface], role=s["role"])
    if s["cracks"]:
        cell, depth, keep = s["cracks"]
        pr.cracks(region, cell, depth, keep=keep)
    if s["stains"]:
        per_m2, k, size = s["stains"]
        stains(pr, region, r.world_w, r.world_h, int(r.world_w * r.world_h * per_m2) + 1, k, size)
