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
    return {"wall_mud": mud, "wall_adobe": adobe, "wall_kept": adobe, "trim_kept": _shade(adobe, 0.96), "pier_kept": _shade(adobe, 1.05),
            "roof_kept": mix(adobe, SUN, 0.1), "parapet_kept": mix(adobe, SUN, 0.1), "roof_flat": mix(adobe, SUN, 0.5),
            "dome": mix(mud, SUN, 0.32),
            "parapet": mix(adobe, SUN, 0.25), "trim": _shade(adobe, 0.94), "yard": _shade(mix(mud, SUN, 0.1), 0.86)}


# surface -> material role (core.materials), cracks (cell m, depth, share kept), stains (per m2,
# strength, size)
SURFACES = {
    "wall_mud": {"role": "wall", "cracks": (0.15, 0.5, 0.75), "stains": (0.3, 0.07, 1.0)},
    "wall_adobe": {"role": "adobe", "cracks": (0.3, 0.22, 0.4), "stains": (0.35, 0.15, 1.6)},
    "wall_kept": {"role": "roofmud", "cracks": (0.6, 0.12, 0.2), "stains": None,
                  "mottle": ((1.6, 0.05), (0.07, 0.08)), "patches": ((0.46, 0.07), (0.2, 0.06)), "courses": 0.5, "stones": (0.55, 0.12)},
    "trim_kept": {"role": "roofmud", "cracks": (0.6, 0.12, 0.2), "stains": None,
                  "mottle": ((1.2, 0.04), (0.3, 0.05), (0.07, 0.09)), "courses": 2.6},
    "pier_kept": {"role": "roofmud", "cracks": None, "stains": None,
                  "mottle": ((1.2, 0.04), (0.07, 0.07)), "patches": ((0.4, 0.07), (0.18, 0.06)), "streaks": 1.2, "stones": (0.55, 0.08)},
    "roof_kept": {"role": "roofmud", "cracks": (0.7, 0.1, 0.25), "stains": None,
                  "mottle": ((1.4, 0.05), (0.07, 0.08)), "patches": ((0.26, 0.13), (0.12, 0.1))},
    "parapet_kept": {"role": "roofmud", "cracks": None, "stains": None, "mottle": ((0.8, 0.04), (0.07, 0.08)),
                     "courses": 2.0},
    "roof_flat": {"role": "roofmud", "cracks": (0.5, 0.1, 0.3), "stains": (0.03, 0.05, 2.5)},
    "dome": {"role": "roofmud", "cracks": (0.3, 0.16, 0.45), "stains": (0.08, 0.06, 1.5)},
    "parapet": {"role": "roofmud", "cracks": None, "stains": (0.1, 0.05, 1.0)},
    "yard": {"role": "plinth", "cracks": None, "stains": (0.12, 0.12, 2.0)},
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
    for cell, k in s.get("mottle", ()):
        pr.mottle(region, cell, k)
    for cell, k in s.get("patches", ()):
        pr.mottle(region, cell, k, hard=True)
    if s.get("stones"):                                   # stones under the plaster, only just showing
        course, k = s["stones"]
        v = 0.0
        while v < r.world_h:
            ch = course * float(pr.rng.uniform(0.75, 1.25))
            u = -float(pr.rng.uniform(0.0, 0.6))
            while u < r.world_w:
                bw = course * float(pr.rng.uniform(1.3, 2.9))
                pr.tone(region, max(0.0, u), v, min(r.world_w, u + bw), min(r.world_h, v + ch),
                        1.0 + float(pr.rng.uniform(-k, k)))
                if pr.rng.random() < 0.7 and u > 0.0:     # the joints are mostly lost
                    pr.tone(region, u, v, u + 0.06, min(r.world_h, v + ch), 1.0 - k * 1.5)
                if pr.rng.random() < 0.7:
                    pr.tone(region, max(0.0, u), v, min(r.world_w, u + bw), min(r.world_h, v + 0.055), 1.0 - k * 1.5)
                u += bw
            v += ch
        for _ in range(int(r.world_w * r.world_h * 12)):  # flat chips and trowel marks
            u, v, d = float(pr.rng.uniform(0, r.world_w)), float(pr.rng.uniform(0, r.world_h)), float(pr.rng.uniform(0.16, 0.46))
            pts = [(u + float(pr.rng.uniform(-d, d)), v + float(pr.rng.uniform(-d, d))) for _ in range(3)]
            pr.facet(region, [(min(r.world_w, max(0.0, a)), min(r.world_h, max(0.0, c))) for a, c in pts],
                     1.0 + float(pr.rng.choice([-1.0, -0.6, 0.6, 1.0])) * k)
    if s.get("streaks"):                                  # rain down a smooth face, in long thin runs
        for _ in range(int(r.world_w * r.world_h * s["streaks"])):
            u, v = float(pr.rng.uniform(0, r.world_w)), float(pr.rng.uniform(-0.8, r.world_h))
            wd, ln = float(pr.rng.uniform(0.04, 0.14)), float(pr.rng.uniform(0.6, 2.4))
            f = float(pr.rng.choice([0.94, 0.96, 0.98, 1.03, 1.05]))
            pr.tone(region, u, max(0.0, v), min(r.world_w, u + wd), min(r.world_h, v + ln), f)
    if s.get("courses"):                                  # long passes of the trowel, course on course
        for _ in range(int(r.world_w * r.world_h * s["courses"])):
            u, v = float(pr.rng.uniform(-0.6, r.world_w)), float(pr.rng.uniform(0, r.world_h))
            ln, th = float(pr.rng.uniform(0.5, 1.9)), float(pr.rng.uniform(0.05, 0.17))
            f = float(pr.rng.choice([0.84, 0.9, 0.95, 1.06, 1.12]))
            pr.tone(region, max(0.0, u), v, min(r.world_w, u + ln), min(r.world_h, v + th), f)
    if s["stains"]:
        per_m2, k, size = s["stains"]
        stains(pr, region, r.world_w, r.world_h, int(r.world_w * r.world_h * per_m2) + 1, k, size)
