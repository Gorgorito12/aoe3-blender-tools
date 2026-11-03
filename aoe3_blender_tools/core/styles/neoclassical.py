# SPDX-License-Identifier: GPL-3.0-or-later
"""The neoclassical style: a block with a hipped roof, a portico with a pediment, a cupola or a
flagpole, chimneys, and optionally a bowed back bay with a colonnade and two wings. Its output is
golden (tests/test_golden.py): keep the order of regions and faces as it is."""
import math
from dataclasses import replace

from ..atlas import Region
from ..kit import Builder, Face

NAME = "NEOCLASSICAL"
STOREY_H = 3.1          # one storey of wall
FRIEZE_H = 0.4          # band under the cornice (inside the wall height)
CORNICE_H = 0.4


def clamp(p):
    """Returns a copy with values the geometry can build."""
    p = replace(p, colors=dict(p.colors))
    p.width = max(4.0, p.width)
    p.depth = max(4.0, p.depth)
    p.storeys = max(1, min(4, int(p.storeys)))
    p.plinth = max(0.2, min(2.0, p.plinth))
    p.roof_pitch = max(0.15, min(1.5, p.roof_pitch))
    p.bay_spacing = max(1.3, p.bay_spacing)
    p.side_bays = max(0, min(15, int(p.side_bays)))
    p.columns = max(2, min(8, int(p.columns) // 2 * 2))
    p.chimneys = max(0, min(8, int(p.chimneys)))
    p.back_portico = str(p.back_portico).upper() if str(p.back_portico).upper() in ("NONE", "BOW") else "NONE"
    # the bowed bay and its colonnade (radius + 2 m, entablature + 0.45 m) must fit the back
    p.bow_radius = max(1.5, min(p.bow_radius, p.width / 2 + 0.3 - 3.2, p.depth))
    p.bow_columns = max(2, min(10, int(p.bow_columns)))
    # the colonnade arc (radius + 2 m, 0.35 rad kept free at each end) must space the column bases
    # (axis-aligned 1.0 m abaci) at least 1.0 * sqrt 2 apart, whatever the direction along the arc
    p.bow_columns = max(2, min(p.bow_columns, int((math.pi - 0.7) * (p.bow_radius + 2.0) / 1.45) + 1))
    if p.width / 2 + 0.3 - 3.2 < 1.5:
        p.back_portico = "NONE"
    p.wing_gap = max(2.0, p.wing_gap)
    p.wing_width = max(3.0, p.wing_width)
    p.wing_depth = max(3.0, min(p.wing_depth, p.depth))
    p.detail = str(p.detail).upper() if str(p.detail).upper() in ("LOW", "MEDIUM") else "LOW"
    p.texture_size = 1 << int(round(math.log2(max(256, min(4096, p.texture_size)))))
    # the portico must fit the front and stay under the roof (its pediment is buried in the roof)
    eave_x, eave_y = p.width / 2 + 0.3, p.depth / 2 + 0.3
    limit = min(eave_x, eave_y) - 0.15
    while p.columns > 2 and ((p.columns - 1) * p.column_spacing / 2 + 1.05 > limit):
        p.columns -= 2
    max_spacing = 2 * (limit - 1.05) / max(1, p.columns - 1)
    p.column_spacing = max(1.2, min(p.column_spacing, max_spacing))
    return p


def build(p, params):
    """The Model of the clamped parameters `p` (`params`: as given, for the notes)."""
    W, D = p.width, p.depth
    plinth = p.plinth
    wall_h = p.storeys * STOREY_H
    wall_top = plinth + wall_h
    eave_z = wall_top + CORNICE_H
    ex, ey = W / 2 + 0.3, D / 2 + 0.3
    pitch = p.roof_pitch
    ridge_z = eave_z + pitch * min(ex, ey)
    front_y = -D / 2
    plinth_y = -D / 2 - 0.2

    def roof_z(x, y):
        return eave_z + pitch * max(0.0, min(ex - abs(x), ey - abs(y)))

    # portico
    port_half = (p.columns - 1) * p.column_spacing / 2 + 0.9 if p.portico else 0.0
    ped_half = port_half + 0.15
    port_y = plinth_y - p.portico_depth if p.portico else plinth_y
    col_y = port_y + 0.6
    col_r = 0.34
    ent_bottom = wall_top - 0.4
    ped_apex = eave_z + ped_half * pitch
    ped_back_y = -(ey - ped_half)          # main roof reaches the apex height there
    ped_y = port_y - 0.05

    # steps in front of the portico, or of the door
    n_steps = max(1, int(round(plinth / 0.2)) - 1)
    step_d = 0.6
    step_half = port_half - 0.6 if p.portico else 1.2
    steps_front = port_y - n_steps * step_d

    # cupola
    drum_r = min(0.95, 0.12 * min(W, D))
    medium = p.detail == "MEDIUM"
    cols = [(-(p.columns - 1) / 2 + i) * p.column_spacing for i in range(p.columns)] if p.portico else []

    # facade layout for the painter (u from the left as seen from outside)
    MIN_STEP = 1.45                         # a 1.0 m window plus its frame and a little wall

    def bays(length):
        """An odd number of evenly spaced bays (symmetric, one on the axis), 1.2 m from the corners
        (the quoins), at the spacing closest to bay_spacing."""
        usable = length - 2.4
        if usable < MIN_STEP:
            return [length / 2]
        best = (1e9, 1)
        n = 3
        while usable / (n - 1) >= MIN_STEP:
            score = abs(usable / (n - 1) - p.bay_spacing)
            if score < best[0]:
                best = (score, n)
            n += 2
        n = best[1]
        if n == 1:
            return [length / 2]
        return [1.2 + i * usable / (n - 1) for i in range(n)]

    def side_bay_list():
        if not p.side_bays:
            return bays(D)
        usable = D - 2.4
        n = p.side_bays
        while n > 1 and usable / (n - 1) < MIN_STEP:
            n -= 1
        return [D / 2] if n == 1 or usable <= 0 else [1.2 + i * usable / (n - 1) for i in range(n)]

    def flank(a, b):
        """Bays from a to b (distances from the axis), never closer than MIN_STEP."""
        if b - a < 0:
            return []
        n = max(1, min(int(round((b - a) / p.bay_spacing)) + 1, int((b - a) / MIN_STEP) + 1))
        return [a + i * (b - a) / (n - 1) for i in range(n)] if n > 1 else [(a + b) / 2]

    if p.portico:
        # behind the portico: one bay between each pair of columns (the middle one is the door);
        # beside it: bays from the portico edge to 1.2 m from the corner, clear of the last one
        mids = [W / 2 + (cols[i] + cols[i + 1]) / 2 for i in range(len(cols) - 1)]
        last_mid = (cols[-1] + cols[-2]) / 2 if len(cols) > 1 else 0.0
        side = flank(max(port_half + 0.25, last_mid + MIN_STEP), W / 2 - 1.2)
        front_bays = sorted(set(round(u, 3) for u in mids + [W / 2 + s for s in side] + [W / 2 - s for s in side]))
    else:
        front_bays = sorted(set(round(u, 3) for u in bays(W) + [W / 2]))
    bow = p.back_portico == "BOW"
    R_bow = p.bow_radius
    R_col = R_bow + 2.0
    N_BOW = 5                                   # wall segments of the bowed bay
    bow_seg = 2 * R_bow * math.sin(math.pi / (2 * N_BOW))
    if bow:
        side = flank(R_bow + 0.6, W / 2 - 1.2)
        back_bays = sorted(set(round(u, 3) for u in [W / 2 + s for s in side] + [W / 2 - s for s in side]))
    else:
        back_bays = bays(W)
    facades = {
        "front": {"bays": front_bays, "door": W / 2, "alt_caps": str(p.window_caps).upper() == "ALTERNATE"},
        "back": {"bays": back_bays, "door": None, "shutters": p.shutters},
        "side": {"bays": side_bay_list(), "door": None},
    }
    if bow:
        # a window per wall segment only when the segment leaves wall beside it: otherwise the
        # reveals of neighbouring segments would cross at the corners
        facades["bow"] = {"bays": [bow_seg / 2] if bow_seg >= 1.6 else [], "door": None, "quoins": False,
                          "shutters": p.shutters, "height": wall_h + CORNICE_H}
    hw, hd = p.wing_width / 2, p.wing_depth / 2
    WING_P = 0.4                                # wing plinth
    if p.wings:
        facades["wing_long"] = {"bays": bays(p.wing_width), "door": None, "storeys": 1}
        facades["wing_short"] = {"bays": bays(p.wing_depth), "door": None, "storeys": 1}

    # openings (u0, v0, u1, v1) per facade, in the facade's own coordinates; the same rectangles
    # the painter fills with glass and wood, so a recessed opening shows them on its back face
    def openings(spec):
        out = []
        for uc in spec["bays"]:
            for st in range(spec.get("storeys", p.storeys)):
                base = st * STOREY_H
                if st == 0 and spec["door"] is not None and abs(uc - spec["door"]) < 0.01:
                    out.append((uc - 0.7, 0.0, uc + 0.7, 2.75))
                elif st == 0:
                    out.append((uc - 0.5, base + 0.8, uc + 0.5, base + 2.7))
                else:
                    out.append((uc - 0.5, base + 0.55, uc + 0.5, base + 2.2))
        return out


    # --- atlas -----------------------------------------------------------------------------------
    roof_w = max(2 * ex, 2 * ey) + 0.2
    roof_h = math.hypot(min(ex, ey), pitch * min(ex, ey)) + 0.2
    if p.portico:
        roof_h = max(roof_h, math.hypot(ped_half, ped_half * pitch) + 0.2)
        roof_w = max(roof_w, abs(ped_back_y - ped_y) + 0.2)
    regions = [
        Region("front", W, wall_h), Region("back", W, wall_h), Region("side", D, wall_h),
        Region("roof", roof_w, roof_h),
        Region("plinth", max(W, D) + 0.8, plinth), Region("trim", max(W, D) + 1.0, 0.8),
        Region("stone", 8.0, 4.0), Region("brick", 4.0, 3.0),
        Region("white", 2.2, 1.6), Region("cupwin", 0.8, 1.6), Region("lead", 7.0, 2.5),
    ]
    if medium:
        regions += [Region("reveal", 1.6, 2.8), Region("balus", max(W, D) + 1.0, 0.95)]
    if p.portico:
        regions += [Region("pedi", 2 * ped_half, ped_apex - eave_z)]
    if p.portico or bow or p.wings:
        regions += [Region("column", 2 * math.pi * col_r, ent_bottom - 0.3 - plinth)]
    if bow:
        regions += [Region("bow", bow_seg, wall_h + CORNICE_H)]
    if p.wings:
        regions += [Region("wing_long", p.wing_width, STOREY_H), Region("wing_short", p.wing_depth, STOREY_H)]

    b = Builder(p.texture_size, medium)
    for r in regions:
        b.region(r.name, r.world_w, r.world_h)
    b.pack()

    def column(cx, cy, z0, z1):
        """A column from z0 to its abacus top z1, as the portico's."""
        if medium:      # square plinth and torus, shaft, echinus and abacus
            b.box(cx - 0.45, cx + 0.45, cy - 0.45, cy + 0.45, z0, z0 + 0.18, "white", "white")
            oct_ = [2 * math.pi * (i + 0.5) / 8 for i in range(8)]
            b.ring(cx, cy, 0.42, z0 + 0.18, z0 + 0.3, 8, "white", per_face=True, phase=math.pi / 8)
            b.faces.append(Face([(cx + 0.42 * math.cos(a), cy + 0.42 * math.sin(a), z0 + 0.3) for a in oct_],
                              "white", [(0.9 + 0.42 * math.cos(a), 0.8 + 0.42 * math.sin(a)) for a in oct_]))
            b.ring(cx, cy, col_r, z0 + 0.3, z1 - 0.32, 10, "column", smooth=True)
            b.ring(cx, cy, 0.43, z1 - 0.32, z1 - 0.16, 8, "white", per_face=True, phase=math.pi / 8)
            b.box(cx - 0.5, cx + 0.5, cy - 0.5, cy + 0.5, z1 - 0.16, z1, "white", "white", skip=("top",))
        else:
            b.box(cx - 0.45, cx + 0.45, cy - 0.45, cy + 0.45, z0, z0 + 0.25, "white", "white")
            b.ring(cx, cy, col_r, z0 + 0.25, z1 - 0.3, 10, "column", smooth=True)
            b.box(cx - 0.48, cx + 0.48, cy - 0.48, cy + 0.48, z1 - 0.3, z1, "white", "white", skip=("top",))

    def make_wall(origin, ua, length, height, region, spec, uoff=0.0):
        """A facade wall: recessed openings at medium detail, a flat quad at low detail."""
        if medium:
            b.wall(origin, ua, length, height, region, openings(spec), uoff=uoff)
            return
        b.flat_wall(origin, ua, length, height, region, uoff=uoff)

    # main block
    b.box(-W / 2 - 0.2, W / 2 + 0.2, -D / 2 - 0.2, D / 2 + 0.2, 0, plinth, "plinth", "stone")
    make_wall((-W / 2, front_y, plinth), (1.0, 0.0, 0.0), W, wall_h, "front", facades["front"])
    if bow:     # the back wall stops where the bowed bay starts (x = +-R_bow)
        make_wall((W / 2, D / 2, plinth), (-1.0, 0.0, 0.0), W / 2 - R_bow, wall_h, "back", facades["back"])
        make_wall((-R_bow, D / 2, plinth), (-1.0, 0.0, 0.0), W / 2 - R_bow, wall_h, "back", facades["back"],
                  uoff=W / 2 + R_bow)
    else:
        make_wall((W / 2, D / 2, plinth), (-1.0, 0.0, 0.0), W, wall_h, "back", facades["back"])
    make_wall((-W / 2, D / 2, plinth), (0.0, -1.0, 0.0), D, wall_h, "side", facades["side"])
    make_wall((W / 2, -D / 2, plinth), (0.0, 1.0, 0.0), D, wall_h, "side", facades["side"])
    if medium:
        # profiled cornice: a bed moulding, then the corona showing the trim's dentil band
        b.box(-W / 2 - 0.12, W / 2 + 0.12, -D / 2 - 0.12, D / 2 + 0.12, wall_top, wall_top + 0.18,
              "trim", "trim", skip=("top",))
        for k, pts in {
            "-y": [(-ex, -ey, wall_top + 0.18), (ex, -ey, wall_top + 0.18), (ex, -ey, eave_z), (-ex, -ey, eave_z)],
            "+y": [(ex, ey, wall_top + 0.18), (-ex, ey, wall_top + 0.18), (-ex, ey, eave_z), (ex, ey, eave_z)],
            "-x": [(-ex, ey, wall_top + 0.18), (-ex, -ey, wall_top + 0.18), (-ex, -ey, eave_z), (-ex, ey, eave_z)],
            "+x": [(ex, -ey, wall_top + 0.18), (ex, ey, wall_top + 0.18), (ex, ey, eave_z), (ex, -ey, eave_z)],
        }.items():
            b.face_auto(pts, "trim", voff=0.44)
    else:
        b.box(-ex, ex, -ey, ey, wall_top, eave_z, "trim", "trim", skip=("top",))

    # hipped roof (ridge along the longer side; a pyramid when square)
    b.hipped_roof(0.0, 0.0, ex, ey, eave_z, pitch)

    # bowed bay with its semicircular colonnade (the back, +y): bay walls up to the eave, columns on
    # a larger arc, an entablature band, a flat roof beyond the eave line, a platform and steps
    R_ent = R_col + 0.45
    if bow:
        cyb = D / 2
        pts = b.arc_pts(0.0, cyb, R_bow, 0.0, math.pi, N_BOW)
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay)
            make_wall((ax, ay, plinth), ((bx - ax) / seg, (by - ay) / seg, 0.0), seg, wall_h + CORNICE_H, "bow",
                      facades["bow"])
        R_plat = R_col + 0.7
        t_p = b.chord_cap(0.0, cyb, R_plat, D / 2 + 0.2, 12, plinth, "stone")
        b.arc_band(0.0, cyb, R_plat, t_p, math.pi - t_p, 12, 0.0, plinth, "plinth")
        t0 = 0.35
        for i in range(p.bow_columns):
            t = t0 + (math.pi - 2 * t0) * i / max(1, p.bow_columns - 1)
            column(R_col * math.cos(t), cyb + R_col * math.sin(t), plinth, ent_bottom)
        t_r = b.chord_cap(0.0, cyb, R_ent, ey, 12, eave_z, "lead")
        b.arc_band(0.0, cyb, R_ent, t_r, math.pi - t_r, 12, ent_bottom, eave_z, "trim")
        # steps from the platform's arc, with cheek walls at medium detail
        sh2 = 1.6
        y0 = cyb + math.sqrt(R_plat ** 2 - sh2 ** 2)
        for i in range(n_steps):
            h = plinth * (n_steps - i) / (n_steps + 1)
            b.box(-sh2, sh2, y0 + step_d * i, y0 + step_d * (i + 1), 0, h, "stone", "stone",
                  skip=("-y", "-x", "+x") if medium else ("-y",))
        if medium:
            for sx0, sx1 in ((-sh2 - 0.35, -sh2), (sh2, sh2 + 0.35)):
                # from y0: starting inside the platform would overlap its top in the same plane
                b.box(sx0, sx1, y0, y0 + step_d * n_steps, 0, plinth, "stone", "stone", skip=("-y",))

    # wings: a pavilion on each side, joined to the block by a colonnade
    if p.wings:
        for sgn in (-1, 1):
            wx = sgn * (W / 2 + p.wing_gap + hw)
            wtop = WING_P + STOREY_H
            b.box(wx - hw - 0.15, wx + hw + 0.15, -hd - 0.15, hd + 0.15, 0, WING_P, "plinth", "stone")
            make_wall((wx - hw, -hd, WING_P), (1.0, 0.0, 0.0), p.wing_width, STOREY_H, "wing_long", facades["wing_long"])
            make_wall((wx + hw, hd, WING_P), (-1.0, 0.0, 0.0), p.wing_width, STOREY_H, "wing_long", facades["wing_long"])
            make_wall((wx - hw, hd, WING_P), (0.0, -1.0, 0.0), p.wing_depth, STOREY_H, "wing_short", facades["wing_short"])
            make_wall((wx + hw, -hd, WING_P), (0.0, 1.0, 0.0), p.wing_depth, STOREY_H, "wing_short", facades["wing_short"])
            b.box(wx - hw - 0.25, wx + hw + 0.25, -hd - 0.25, hd + 0.25, wtop, wtop + 0.3, "trim", "trim", skip=("top",))
            wridge = b.hipped_roof(wx, 0.0, hw + 0.25, hd + 0.25, wtop + 0.3, 0.5)
            ccx = wx + sgn * hw * 0.35
            b.chimney(ccx, 0.0, wtop + 0.3 + 0.5 * max(0.0, min(hw + 0.25 - abs(ccx - wx), hd + 0.25)) - 0.4,
                      wridge + 0.8)
            # colonnade: a low floor, two rows of slender columns, a flat roof slab
            x_in, x_out = W / 2 + 0.2, wx - hw - 0.15
            if sgn < 0:
                x_in, x_out = wx + hw + 0.15, -W / 2 - 0.2
            b.box(x_in, x_out, -1.4, 1.4, 0, 0.25, "plinth", "stone", skip=("-x", "+x"))
            slab0, slab1 = (W / 2, wx - hw) if sgn > 0 else (wx + hw, -W / 2)
            b.box(slab0, slab1, -1.45, 1.45, 2.75, 3.1, "trim", "lead", skip=("-x", "+x"))
            length = x_out - x_in
            n = max(2, int(round(length / 1.7)) + 1)
            for i in range(n):
                cx = x_in + 0.45 + (length - 0.9) * i / (n - 1)
                for cy in (-1.15, 1.15):
                    b.ring(cx, cy, 0.17, 0.25, 2.75, 8, "column", smooth=True)

    # balustrade on the cornice: straight segments that never overlap at the corners (the side
    # ones stop at the inner face of the front and back ones), posts at the corners, at the ends
    # beside the pediment and along the long runs
    if medium:
        PH, IN, TH = 0.75, 0.05, 0.25          # height, inset from the eave, thickness
        o_x, o_y, i_x, i_y = ex - IN, ey - IN, ex - IN - TH, ey - IN - TH
        gap = ped_half + 0.25 if p.portico else 0.0
        xg = R_ent + 0.1 if bow else 0.0
        runs = [(-o_x, -xg, i_y, o_y), (xg, o_x, i_y, o_y)] if bow else [(-o_x, o_x, i_y, o_y)]   # back
        runs += [(-o_x, -gap, -o_y, -i_y), (gap, o_x, -o_y, -i_y)] if gap else [(-o_x, o_x, -o_y, -i_y)]
        runs += [(-o_x, -i_x, -i_y, i_y), (i_x, o_x, -i_y, i_y)]        # sides
        for x0, x1, y0, y1 in runs:
            # a stub shorter than a post is left out (the length is the longer side)
            if max(x1 - x0, y1 - y0) > 0.45 and min(x1 - x0, y1 - y0) > 0.01:
                b.box(x0, x1, y0, y1, eave_z, eave_z + PH, "balus", "white")
        posts = [(-ex + 0.2, -ey + 0.2), (ex - 0.2, -ey + 0.2), (-ex + 0.2, ey - 0.2), (ex - 0.2, ey - 0.2)]
        if gap:
            posts += [(-gap, -ey + 0.2), (gap, -ey + 0.2)]
        if bow:
            posts += [(-xg, ey - 0.2), (xg, ey - 0.2)]
            # the bow's balustrade, on the colonnade's flat roof
            t_b = math.asin(min(1.0, 0.3 / (R_ent - 0.05)))
            b.arc_band(0.0, D / 2, R_ent - 0.05, t_b, math.pi - t_b, 12, eave_z, eave_z + PH, "balus")
            b.arc_band(0.0, D / 2, R_ent - 0.3, t_b, math.pi - t_b, 12, eave_z, eave_z + PH, "balus", inward=True)
            outer = b.arc_pts(0.0, D / 2, R_ent - 0.05, t_b, math.pi - t_b, 12)
            inner = b.arc_pts(0.0, D / 2, R_ent - 0.3, t_b, math.pi - t_b, 12)
            for (ax, ay), (bx, by), (cx_, cy_), (dx, dy) in zip(outer, outer[1:], inner[1:], inner):
                b.facing([(ax, ay, eave_z + PH), (bx, by, eave_z + PH), (cx_, cy_, eave_z + PH), (dx, dy, eave_z + PH)],
                         [(0, 0), (0.6, 0), (0.6, 0.25), (0, 0.25)], "white", (0.0, 0.0, 1.0))
        else:
            n_long = max(0, int((2 * ex - 0.4) / 5.0))
            posts += [(-ex + 0.2 + (2 * ex - 0.4) * (i + 1) / (n_long + 1), ey - 0.2) for i in range(n_long)]
        kept = []
        for px, py in posts:            # two posts closer than their width would overlap
            if all(abs(px - qx) >= 0.42 or abs(py - qy) >= 0.42 for qx, qy in kept):
                kept.append((px, py))
        for px, py in kept:
            b.box(px - 0.2, px + 0.2, py - 0.2, py + 0.2, eave_z, eave_z + PH + 0.15, "white", "white")

    # portico (the platform stops at the plinth front: an overlap would be coplanar with the
    # plinth top and z-fight)
    if p.portico:
        b.box(-port_half, port_half, port_y, plinth_y, 0, plinth, "plinth", "stone", skip=("+y",))
        for cx in cols:
            column(cx, col_y, plinth, ent_bottom)
        b.box(-port_half, port_half, port_y, front_y, ent_bottom, eave_z, "trim", "trim", skip=("+y", "top"))
        b.face_auto([(-ped_half, ped_y, eave_z), (ped_half, ped_y, eave_z), (0, ped_y, ped_apex)], "pedi",
                    anchor=(-ped_half, ped_y, eave_z))
        b.face_auto([(-ped_half, ped_back_y, eave_z), (-ped_half, ped_y, eave_z), (0, ped_y, ped_apex),
                   (0, ped_back_y, ped_apex)], "roof")
        b.face_auto([(ped_half, ped_y, eave_z), (ped_half, ped_back_y, eave_z), (0, ped_back_y, ped_apex),
                   (0, ped_y, ped_apex)], "roof")
        b.box(-ped_half, ped_half, ped_y, port_y, eave_z - 0.12, eave_z, "trim", "trim", skip=("+y", "top"))
    for i in range(n_steps):
        y1 = port_y - step_d * i
        h = plinth * (n_steps - i) / (n_steps + 1)
        b.box(-step_half, step_half, y1 - step_d, y1, 0, h, "stone", "stone",
              skip=("+y", "-x", "+x") if medium else ("+y",))
    if medium:          # cheek walls beside the steps (they hide the steps' ends)
        for sx0, sx1 in ((-step_half - 0.35, -step_half), (step_half, step_half + 0.35)):
            b.box(sx0, sx1, steps_front, port_y, 0, plinth, "stone", "stone", skip=("+y",))

    # cupola
    attach = b.attach
    if p.cupola:
        z0 = ridge_z - 0.6
        z1 = ridge_z + 1.0
        b.ring(0, 0, drum_r, z0, z1, 8, "cupwin", per_face=True, phase=math.pi / 8)
        b.ring(0, 0, drum_r * 1.18, z1, z1 + 0.15, 8, "white", per_face=True, phase=math.pi / 8)
        dome_r, dome_h, dome_z = drum_r * 1.1, drum_r, z1 + 0.15
        pts = []
        for ang in (0, 25, 50, 72):
            t = math.radians(ang)
            pts.append((dome_r * math.cos(t) if ang else drum_r * 1.18, dome_z + dome_h * math.sin(t)))
        arc = 0.0
        lead = b.atlas["lead"]
        for j in range(len(pts) - 1):
            (r0, za), (r1, zb) = pts[j], pts[j + 1]
            arc1 = arc + math.hypot(r1 - r0, zb - za)
            for i in range(8):
                a0 = math.pi / 8 + 2 * math.pi * i / 8
                a1 = a0 + 2 * math.pi / 8
                u0, u1 = i * lead.world_w / 8, (i + 1) * lead.world_w / 8
                b.faces.append(Face([(r0 * math.cos(a0), r0 * math.sin(a0), za), (r0 * math.cos(a1), r0 * math.sin(a1), za),
                                   (r1 * math.cos(a1), r1 * math.sin(a1), zb), (r1 * math.cos(a0), r1 * math.sin(a0), zb)],
                                  "lead", [(u0, arc), (u1, arc), (u1, arc1), (u0, arc1)], True))
            arc = arc1
        lan_r, lan_z = pts[-1]
        b.ring(0, 0, lan_r, lan_z, lan_z + 0.45, 8, "white", per_face=True, phase=math.pi / 8)
        top = lan_z + 0.45 + 0.75 * drum_r / 0.95
        for i in range(8):
            a0 = math.pi / 8 + 2 * math.pi * i / 8
            a1 = a0 + 2 * math.pi / 8
            zb = lan_z + 0.45
            b.faces.append(Face([(lan_r * math.cos(a0), lan_r * math.sin(a0), zb), (lan_r * math.cos(a1), lan_r * math.sin(a1), zb),
                               (0, 0, top)], "lead", [(i * 0.4, 0), ((i + 1) * 0.4, 0), ((i + 0.5) * 0.4, 0.8)]))
        attach["flag_attach"] = (0.0, 0.0, top)
    elif p.flagpole:
        top = ridge_z + 4.5
        b.box(-0.07, 0.07, -0.07, 0.07, ridge_z - 0.3, top, "white", "white")
        attach["flag_attach"] = (0.0, 0.0, top)
    else:
        attach["flag_attach"] = (0.0, 0.0, ridge_z + 0.1)

    # chimneys (their foot is inside the roof): 1 or 2 near the side ends, more in pairs
    if p.chimneys <= 2:
        spots = [(-max(1.0, W / 2 - 2.0), D * 0.18), (max(1.0, W / 2 - 2.0), D * 0.18)][:p.chimneys]
    else:
        a_, b_, c_ = W * 0.17, W * 0.36, D * 0.25
        spots = [(-a_, -c_), (a_, -c_), (-a_, c_), (a_, c_), (-b_, -c_), (b_, -c_), (-b_, c_), (b_, c_)][:p.chimneys]
    # keep the chimneys whose caps (1.0 m) clear each other and the cupola or flagpole
    centre_r = drum_r * 1.3 + 0.6 if p.cupola else (0.6 if p.flagpole else 0.0)
    kept = []
    for cx, cy in spots:
        if centre_r and abs(cx) < centre_r and abs(cy) < centre_r:
            continue
        if all(max(abs(cx - qx), abs(cy - qy)) >= 1.1 for qx, qy in kept):
            kept.append((cx, cy))
    for cx, cy in kept:
        b.chimney(cx, cy, roof_z(cx, cy) - 0.4, ridge_z + 1.0)
    chimneys_built = len(kept)

    notes = []
    for attr, label in (("columns", "Columns"), ("column_spacing", "Column spacing")):
        want, got = getattr(params, attr), getattr(p, attr)
        if params.portico and abs(want - got) > 1e-6:
            notes.append(f"{label} {want:g} -> {got:g}: the portico must fit the front and its pediment stay under the roof.")
    if chimneys_built < p.chimneys:
        notes.append(f"Chimneys {p.chimneys} -> {chimneys_built}: the others would overlap each other or the roof's centre piece.")
    if bow:
        for attr, label in (("bow_radius", "Bow radius"), ("bow_columns", "Bow columns")):
            want, got = getattr(params, attr), getattr(p, attr)
            if abs(want - got) > 1e-6:
                notes.append(f"{label} {want:g} -> {got:g}: the bow and its colonnade must fit the back.")
    return b.finish(p, facades, {"wall_h": wall_h, "storeys": p.storeys, "ped_half": ped_half},
                    notes)
