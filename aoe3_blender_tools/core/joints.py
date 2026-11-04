# SPDX-License-Identifier: GPL-3.0-or-later
"""How the solid volumes of a composed building meet. Pure Python.

`validate.check` only sees coplanar faces, so a tower and a wing that cross badly pass it: corners
stick out of the cylinder, parapets run through it, slivers of air stay between two walls. Two
volumes of a building must either be clearly apart or properly joined:

    apart     a gap of MIN_GAP or more in plan, or one standing on top of the other;
    embedded  the end of one is entirely inside the other (on the low-detail polygon too: a round
              wall with few sides cuts well inside its radius), and the other is at least as tall.

Everything else is a bad joint. A shape is a dict: {"shape": "circle", "x", "y", "r", "sides",
"z0", "z1", "name"} or {"shape": "rect", "x0", "y0", "x1", "y1", "z0", "z1", "name"}; a flat-roofed
one may give "roof", the level of its roof inside the parapet, for what stands on it."""
import math

MIN_GAP = 0.25          # metres of air between two volumes that are not joined
EPS = 1e-6


def plan_gap(a, b):
    """The distance between two shapes in plan (negative or zero when they touch or overlap)."""
    if a["shape"] == "circle" and b["shape"] == "circle":
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - a["r"] - b["r"]
    if a["shape"] == "rect" and b["shape"] == "rect":
        gx = max(a["x0"] - b["x1"], b["x0"] - a["x1"])
        gy = max(a["y0"] - b["y1"], b["y0"] - a["y1"])
        if gx > 0 and gy > 0:
            return math.hypot(gx, gy)
        return max(gx, gy)
    c, r = (a, b) if a["shape"] == "circle" else (b, a)
    dx = max(r["x0"] - c["x"], 0.0, c["x"] - r["x1"])
    dy = max(r["y0"] - c["y"], 0.0, c["y"] - r["y1"])
    return math.hypot(dx, dy) - c["r"]


def inside(px, py, s):
    """True when the point is strictly inside the shape; a circle counts as the polygon inscribed
    at its fewest sides."""
    if s["shape"] == "rect":
        return s["x0"] + EPS < px < s["x1"] - EPS and s["y0"] + EPS < py < s["y1"] - EPS
    return math.hypot(px - s["x"], py - s["y"]) < s["r"] * math.cos(math.pi / s.get("sides", 8)) - EPS


def rect_ends(s):
    """The four sides of a rect as pairs of corners."""
    x0, y0, x1, y1 = s["x0"], s["y0"], s["x1"], s["y1"]
    return (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))


def embedded(a, b):
    """True when a ends inside b: a side of rect a (or all of a circle) lies within b, and b rises
    at least as high, so nothing of a pokes out of b."""
    if b["z1"] < a["z1"] - EPS:
        return False
    if a["shape"] == "rect":
        return any(inside(*p, b) and inside(*q, b) for p, q in rect_ends(a))
    n = 16
    return all(inside(a["x"] + a["r"] * math.cos(2 * math.pi * k / n),
                      a["y"] + a["r"] * math.sin(2 * math.pi * k / n), b) for k in range(n))


def on_roof(top, base):
    """True when `top` stands on the flat roof of `base`, inside its walls."""
    if "roof" not in base or top["z0"] < base["roof"] - EPS or top["shape"] != "rect":
        return False
    return all(inside(px, py, base) for side in rect_ends(top) for px, py in side)


def classify(a, b):
    """"apart", "embedded" or "bad" for two shapes. Pieces drawn as one stepped mass say so with
    the same "mass": they are one volume (the coplanar check still holds them)."""
    if a.get("mass") and a.get("mass") == b.get("mass"):
        return "embedded"
    if a["z0"] >= b["z1"] - EPS or b["z0"] >= a["z1"] - EPS or on_roof(a, b) or on_roof(b, a):
        return "apart"
    if plan_gap(a, b) >= MIN_GAP - EPS:
        return "apart"
    if embedded(a, b) or embedded(b, a):
        return "embedded"
    return "bad"


def problems(shapes):
    """[(i, j, message)] for every pair of shapes that meet badly."""
    out = []
    for i, a in enumerate(shapes):
        for j in range(i + 1, len(shapes)):
            b = shapes[j]
            if classify(a, b) == "bad":
                g = plan_gap(a, b)
                what = f"{g:.2f} m apart" if g > 0 else "crossing"
                out.append((i, j, f"{a.get('name', i)} and {b.get('name', j)}: {what}, neither apart "
                                  f"(>= {MIN_GAP} m) nor embedded"))
    return out
