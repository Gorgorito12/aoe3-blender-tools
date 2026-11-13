# SPDX-License-Identifier: GPL-3.0-or-later
"""How many segments a body that is not a box gets: round walls, cones, domes, arches, arcades.

A box costs five quads whatever you do with it. Everything round costs what you ask of it, and
until now every style asked for a number written at the call site - 24 sides for a round wall,
12 for an arch, 8 for a cupola - which nobody could change without editing the style.

`BuildingParams.poly` is that number's multiplier, and this module is the only place it is
applied. At **1.0 every count is the one the style always used**, exactly, so a building built at
the default is the building that was always built (tests/test_golden.py depends on it). Below 1.0
the round bodies lose segments; above it they gain them.

    b.sides(24)      # a round wall: 24 at poly 1.0, 14 at 0.6, 36 at 1.5
    b.rings(6)       # the courses of a dome
    b.segments(6)    # the intrados of an arch

Two numbers tell you what a choice costs and what it looks like:

    chord_error(r, n)  how far the flat side sags from the true circle, in metres
    sides_for(r, e)    the fewest sides that keep that sag under `e`

At the game's camera (about 21 pixels per unit at 1080p, 43 at 4K, and a unit is 1.63 m) a sag
under about 4 cm is under a pixel: ERROR_SEEN is that, and it is what a sensible lower bound
looks like for a wall seen from the side. It is advice, not a rule - the floors below are what
the code enforces.

Pure Python: no numpy, no Blender.
"""
import math

MIN_SIDES = 6       # a round wall of fewer sides cuts far inside its radius, and core/joints.py
                    # measures the embedding on that polygon: below 6 every joint must be re-proved
MIN_RINGS = 1       # a dome of one ring is a cone, which is still a dome's shape
MIN_SEGMENTS = 2    # an arch of two segments is a triangle over the opening
ERROR_SEEN = 0.04   # metres of sag that is about one pixel at the game's camera


def scale(base, factor, lowest):
    """`base` segments scaled by `factor`, never below `lowest`. At factor 1.0 the base comes
    back untouched, by construction and not by rounding."""
    base = int(base)
    if factor is None or float(factor) == 1.0:
        return base
    return max(int(lowest), int(round(base * float(factor))))


def sides(base, factor=1.0, lowest=MIN_SIDES):
    """The sides of a round body (a wall, a cone, a drum, a disc)."""
    return scale(base, factor, lowest)


def rings(base, factor=1.0):
    """The courses up a dome."""
    return scale(base, factor, MIN_RINGS)


def segments(base, factor=1.0):
    """The segments of an arch or an arcade's intrados (kept even: an arch has a keystone)."""
    n = scale(base, factor, MIN_SEGMENTS)
    return max(MIN_SEGMENTS, n // 2 * 2)


def chord_error(radius, n):
    """How far a polygon of `n` sides sags inside the circle of `radius`, in metres."""
    return float(radius) * (1.0 - math.cos(math.pi / max(3, int(n))))


def sides_for(radius, error=ERROR_SEEN, lowest=MIN_SIDES, highest=64):
    """The fewest sides whose sag stays under `error` metres on a circle of `radius`."""
    if error <= 0:
        return highest
    inner = 1.0 - min(error / max(float(radius), 1e-6), 1.0)
    if inner <= -1.0:
        return lowest
    n = math.pi / math.acos(max(min(inner, 1.0), -1.0)) if inner < 1.0 else highest
    return max(lowest, min(highest, int(math.ceil(n))))
