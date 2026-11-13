# SPDX-License-Identifier: GPL-3.0-or-later
"""Places a building's program (program.py) on its plot: a map of the ground, what is taken, what
is kept clear, and for each item the best free spot. Nothing lands on anything else or in front of
a door, big things stand against walls, what belongs together stays together, the side the camera
sees (-Y) is preferred, and placing stops at the triangle target. A building reads as one place,
not as things scattered on a plot: every item goes as close as it can to what already stands
(MAX_REACH is the limit, and a test holds it). The result depends only on the parameters: `seed`
gives another arrangement."""
import math

import numpy as np

from ...kit import Builder
from . import parts, program, sizes

CELL = 0.25
RIM = 0.1                # kept clear at the edge of the plot
MAX_REACH = 0.8          # the farthest an item stands from a structure or another item
# prop -> footprint (m) with a little air round it
SIZE = {"pot": (0.7, 0.7), "basket": (0.7, 0.7), "sack": (0.6, 0.6), "drum": (0.7, 0.7), "crate": (0.75, 0.75),
        "barrel": (0.6, 0.6), "barrow": (1.6, 0.7), "ore": (1.4, 1.1), "anvil": (0.8, 0.5), "bellows": (0.9, 0.6),
        "furnace": (1.3, 1.4), "forge": (1.7, 1.4), "trough": (1.3, 0.6), "shields": (2.0, 0.4), "hide_rack": (1.3, 0.3),
        "dummy": (1.1, 0.4), "weigh": (1.7, 0.7), "boat": (3.1, 0.9), "fish_rack": (1.8, 0.3), "wheel": (0.9, 0.3),
        "rack": (1.8, 0.4), "fire": (1.2, 1.2), "well": (1.6, 1.6), "stones": (2.0, 0.7), "crane": (1.9, 2.0),
        "cart": (4.1, 1.7), "chest": (0.9, 0.7), "rock": (1.8, 1.8), "tent": (2.7, 2.2), "heap": (1.0, 1.0),
        "ruin": (3.0, 3.0), "pole": (1.2, 0.3)}
_costs = {}


def size_of(item):
    kw = item["kw"]
    k = item["kind"]
    if "size" in kw:                                      # its own footprint (a barrel on its side)
        return tuple(kw["size"])
    if k == "logs":
        L, w = kw.get("length", 2.0) + 0.2, 2.2 * kw.get("n", 4) * kw.get("r", 0.12) + 0.2
        return (w, L) if kw.get("along") == "y" else (L, w)
    if k == "frame":
        return kw.get("w", 3.0) + 0.6, kw.get("d", 1.6) + 0.4
    return SIZE[k]


def cost(piece):
    """The triangles of one piece, built once on a scratch builder."""
    key = (piece["kind"], tuple(sorted((k, repr(v)) for k, v in piece.items() if k not in ("x", "y", "id"))))
    if key not in _costs:
        b = Builder(256, True)
        facades = parts.declare(b, [dict(piece)], True)
        b.pack()
        b._african_facades = facades
        parts.emit(b, [dict(piece)], True)
        _costs[key] = sum(len(f.pts) - 2 for f in b.faces)
    return _costs[key]


def total(layout):
    """The triangles of a layout at medium detail."""
    b = Builder(256, True)
    facades = parts.declare(b, layout, True)
    b.pack()
    b._african_facades = facades
    parts.emit(b, layout, True)
    return sum(len(f.pts) - 2 for f in b.faces)


class Ground:
    """A grid over the plot, centred on the origin."""

    def __init__(self, S):
        self.n = int(math.ceil(S / CELL))
        self.S = self.n * CELL
        c = -self.S / 2 + CELL * (np.arange(self.n) + 0.5)
        self.X, self.Y = np.meshgrid(c, c)
        self.solid = np.zeros((self.n, self.n), bool)         # buildings, posts, fences
        self.clear = np.zeros((self.n, self.n), bool)         # kept free: the way to a door
        self.taken = np.zeros((self.n, self.n), bool)         # props
        self.shade = np.zeros((self.n, self.n), bool)         # under an awning
        self.deck = np.zeros((self.n, self.n), bool)
        self.out = (np.abs(self.X) > S / 2 - RIM) | (np.abs(self.Y) > S / 2 - RIM)
        self.deck_z = 0.0
        self.roofs = []                                       # (mask, level) of each flat roof
        self.base = 0.0                                       # the height of the common ground
        self.named = {}

    def rect(self, x0, y0, x1, y1):
        return (self.X >= x0) & (self.X <= x1) & (self.Y >= y0) & (self.Y <= y1)

    def disc(self, x, y, r):
        return np.hypot(self.X - x, self.Y - y) <= r


def roofs_of(g, layout):
    """The flat roofs one can stand things on, without what stands on them."""
    uppers = [p for p in layout if p["kind"] in ("block", "shed") and p.get("z", 0.0) > 0.7]
    for p in layout:
        if p["kind"] != "block" or p.get("roof") == "thatch":
            continue
        t = 0.35 if p.get("parapet") else 0.15
        z = p.get("z", 0.0) + p["h"]
        mask = g.rect(p["x0"] + t, p["y0"] + t, p["x1"] - t, p["y1"] - t)
        for q in uppers:
            if q is not p and q.get("z", 0.0) >= z - 0.01:
                mask &= ~g.rect(q["x0"] - 0.25, q["y0"] - 0.25, q["x1"] + 0.25, q["y1"] + 0.25)
        g.roofs.append((mask, z))


def survey(layout, S):
    """The ground of a plot from the layout's structure."""
    g = Ground(S)
    roofs_of(g, layout)
    for p in layout:
        k = p["kind"]
        if p.get("z", 0.0) > 0.7:                             # on a roof, not on the ground
            continue
        if k in ("hut", "granary", "tower"):
            g.solid |= g.disc(p["x"], p["y"], p["r"] + 0.3)
            if p.get("door"):
                w = p.get("door_w", 1.0) / 2 + 0.3
                depth = S if p.get("flag") else 1.0           # units leave by the main door
                g.clear |= g.rect(p["x"] - w, p["y"] - p["r"] - depth, p["x"] + w, p["y"] - p["r"])
        elif k == "block":
            x0, y0, x1, y1 = p["x0"], p["y0"], p["x1"], p["y1"]
            g.solid |= g.rect(x0 - 0.3, y0 - 0.3, x1 + 0.3, y1 + 0.3)
            door = p.get("door")
            if door in (True, "front"):
                depth = S if p.get("flag") else 1.0           # units leave by the main door
                g.clear |= g.rect((x0 + x1) / 2 - 0.7, y0 - depth, (x0 + x1) / 2 + 0.7, y0)
            elif door == "back":
                g.clear |= g.rect((x0 + x1) / 2 - 0.7, y1, (x0 + x1) / 2 + 0.7, y1 + 1.0)
            elif door == "left":
                g.clear |= g.rect(x0 - 1.0, (y0 + y1) / 2 - 0.7, x0, (y0 + y1) / 2 + 0.7)
            elif door == "right":
                g.clear |= g.rect(x1, (y0 + y1) / 2 - 0.7, x1 + 1.0, (y0 + y1) / 2 + 0.7)
        elif k == "fence":
            pts = p["points"] + ([p["points"][0]] if p.get("closed") else [])
            for a, c in zip(pts, pts[1:]):
                L = math.hypot(c[0] - a[0], c[1] - a[1])
                for j in range(int(L / (CELL / 2)) + 1):
                    f = j / max(1, int(L / (CELL / 2)))
                    g.solid |= g.disc(a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f, 0.4)
        elif k in ("canopy", "shed"):
            g.shade |= g.rect(p["x0"] + 0.1, p["y0"] + 0.1, p["x1"] - 0.1, p["y1"] - 0.1)
            for x in (p["x0"] + 0.1, p["x1"] - 0.1):
                for y in (p["y0"] + 0.1, p["y1"] - 0.1):
                    g.solid |= g.disc(x, y, 0.3)
        elif k in ("stack", "plinth", "field"):
            g.solid |= g.rect(p["x0"] - 0.15, p["y0"] - 0.15, p["x1"] + 0.15, p["y1"] + 0.15)
        elif k == "deck":
            g.solid |= g.rect(p["x0"], p["y0"], p["x1"], p["y1"])
            g.deck |= g.rect(p["x0"] + 0.4, p["y0"] + 0.4, p["x1"] - 0.4, p["y1"] - 0.4)
            g.deck_z = p["z"]
        elif k == "stairs":
            d = p.get("run", 2.8)
            w = p["w"] / 2 + 0.2
            x, y = p["x"], p["y"]
            box = {"+x": (x, y - w, x + d, y + w), "-x": (x - d, y - w, x, y + w),
                   "+y": (x - w, y, x + w, y + d), "-y": (x - w, y - d, x + w, y)}[p.get("dir", "+x")]
            g.solid |= g.rect(*box)
            g.clear |= g.rect(box[0] - 0.3, box[1] - 0.5, box[2] + 0.3, box[3] + 0.3)
        elif k == "lookout":
            g.solid |= g.rect(p["x"] - p["w"] / 2 - 0.3, p["y"] - p["w"] / 2 - 0.5, p["x"] + p["w"] / 2 + 0.3,
                              p["y"] + p["w"] / 2 + 0.3)
        elif k == "ground":
            g.base = p["h"]
        elif k == "yard":                                     # props stay inside this
            if "r" in p:
                g.out |= ~g.disc(p.get("x", 0.0), p.get("y", 0.0), p["r"])
            else:
                g.out |= ~g.rect(p["x0"], p["y0"], p["x1"], p["y1"])
    return g


def free_spots(mask, w, d):
    """Where a w x d rect fits, centred on each cell, with no cell of `mask` under it."""
    hx, hy = max(0, int(math.ceil((w / CELL - 1) / 2))), max(0, int(math.ceil((d / CELL - 1) / 2)))
    n = mask.shape[0]
    sat = np.zeros((n + 1, n + 1), np.int32)
    sat[1:, 1:] = mask.cumsum(0).cumsum(1)
    ix = np.arange(n)
    x0, x1 = np.clip(ix - hx, 0, n), np.clip(ix + hx + 1, 0, n)
    y0, y1 = np.clip(ix - hy, 0, n), np.clip(ix + hy + 1, 0, n)
    count = sat[y1][:, x1] - sat[y0][:, x1] - sat[y1][:, x0] + sat[y0][:, x0]
    fits = (x1 - x0 == 2 * hx + 1)[None, :] & (y1 - y0 == 2 * hy + 1)[:, None]
    return (count == 0) & fits


def dilate(a, k=1):
    out = a.copy()
    for _ in range(k):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def reach(mask, limit=40):
    """Metres from each cell to the nearest cell of `mask`."""
    out = np.full(mask.shape, limit * CELL, np.float32)
    seen = mask.copy()
    out[seen] = 0.0
    for k in range(1, limit):
        grown = dilate(seen)
        out[grown & ~seen] = k * CELL
        seen = grown
    return out


def place(g, item, rng, last=None):
    """The best free spot for one item, or None."""
    w, d = size_of(item)
    deck = item["on"] == "deck"
    if item["on"] == "roof":                                  # the emptiest roof that has room
        for mask, z in sorted(g.roofs, key=lambda r: ((r[0] & g.taken).sum(), -r[1])):
            spots = free_spots(~mask | g.taken, w, d)
            if spots.any():
                score = rng.uniform(0, 0.3, spots.shape) - 1.5 * reach(~mask | g.taken)
                score = np.where(spots, score, -1e9)
                iy, ix = np.unravel_index(int(score.argmax()), score.shape)
                x, y = float(g.X[iy, ix]), float(g.Y[iy, ix])
                g.taken |= g.rect(x - w / 2, y - d / 2, x + w / 2, y + d / 2)
                g.level = z
                return x, y
        return None
    if deck:                                                  # a wharf: the way out runs along it
        blocked = ~g.deck | g.taken
    else:
        blocked = g.solid | g.clear | g.taken | g.out
    spots = free_spots(blocked, w, d)
    if not spots.any():
        return None
    at = item["at"]
    front = 0.4 if at == "shade" else 1.0                     # the camera's side first
    score = rng.uniform(0, 0.3, spots.shape) - g.Y / g.S * front
    built = g.solid | g.taken
    if deck:
        built = g.taken | ~g.deck
    away = reach(built)
    score = score - 2.5 * away                                # close to what stands
    if not item["need"]:                                      # what it cannot do without goes anyway
        spots = spots & (away <= MAX_REACH + min(w, d) / 2)
    if not spots.any():
        return None
    if at == "wall":
        score = score - 1.5 * reach(g.solid)
    elif at == "shade":
        # the emptiest shade: every awning and shed has something under it
        score = score + 5.0 * g.shade - 3.0 * dilate(g.taken & g.shade, 8)
    target = g.named.get(item["near"]) if item["near"] else None
    target = last if last is not None else target
    if target is not None:
        score = score - 2.5 * np.hypot(g.X - target[0], g.Y - target[1])
    score = np.where(spots, score, -1e9)
    i = int(score.argmax())
    iy, ix = np.unravel_index(i, score.shape)
    x, y = float(g.X[iy, ix]), float(g.Y[iy, ix])
    g.taken |= g.rect(x - w / 2, y - d / 2, x + w / 2, y + d / 2)
    return x, y


def piece_of(item, x, y, g):
    kw = dict(item["kw"])
    if item["kind"] == "bellows" and "to" in kw:
        kw["to"] = tuple(kw["to"])
    p = {"kind": item["kind"], "x": x, "y": y, **kw}
    if item["kind"] == "pot":
        p.setdefault("r", 0.28)
        p.setdefault("h", 0.5)
    if item["on"] == "deck":
        p["z"] = g.deck_z
    elif item["on"] == "roof":
        p["z"] = g.level
    elif g.base:
        p["z"] = g.base                                   # on the building's ground
    return p


def compose(layout, p, S):
    """The layout with the building's program placed on it, up to its triangle target (medium
    detail: the low model carries no props, so it needs none of this)."""
    structure = [pc for pc in layout if pc["kind"] != "yard"]
    must, more = program.items(p)
    if not must and not more:                             # all of it is built in
        return structure
    target, _, hi = sizes.tris_target(p.building_type)
    g = survey(layout, S)
    rng = np.random.default_rng(int(p.seed) + 7919 * sizes.TYPES.index(p.building_type))
    out = list(structure)
    count = total(out)

    def add(item):
        nonlocal count
        last = None
        for _ in range(item["count"]):
            at = place(g, item, rng, last)
            if at is None:
                return False
            piece = piece_of(item, at[0], at[1], g)
            c = cost(piece)
            if not item["need"] and count + c > hi:
                return False
            out.append(piece)
            count += c
            if item["name"]:
                g.named[item["name"]] = at
            last = at
        return True

    for item in [i for i in must if i["need"]]:              # what the building cannot do without
        add(item)
    for item in [i for i in must if not i["need"]]:
        if count >= target:
            break
        add(item)
    # up to the budget: what does not fit is passed over, until nothing on the list does
    small = more + must + [program.I("basket", at="wall"), program.I("sack", at="wall"), program.I("pot", at="wall")]
    failed, k = 0, 0
    while count < target and small and failed < len(small) and k < 200:
        item = dict(small[k % len(small)], count=1, name=None, near=None, need=False)
        k += 1
        failed = 0 if add(item) else failed + 1
    return out
