# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws small stat icons for the unit panels (the pictures that rows of the panels put after a value: damage
types, range, bonuses), in two styles:

- `--style bold` (the one to ship): 32x32 uncompressed BGRA, alpha "transparent", one level, as a mod's own stat
  icons are made; solid shapes, strokes of 3 to 7 texels, alpha only 0 or 255 (one sample per texel, no
  supersampling), each part with its own black contour and the glyph with a black outline 2 texels wide. The
  panel draws icons at about 10 x 14 screen pixels (narrower than tall), so round parts are drawn wider than tall
  (`AX`) to look round there;
- `--style soft` (the first set, kept for comparison): 16x16 DXT3, one level, drawn at 8 samples per texel side
  and averaged (soft edges), outlined in a dark brown. Drawn 10 pixels wide, its 1-texel strokes come out thin
  and blurred.

    venv\\Scripts\\python -I tools/make_stat_icon.py [--style bold] [--glyph stopwatch] [--out <file.ddt>]
                                                  [--png <preview.png>] [--check]
    venv\\Scripts\\python -I tools/make_stat_icon.py --style bold --all <folder> [--png <sheet.png>] [--check]

Bold glyphs (the file name `--all` gives each one):
- `stopwatch` (`stat_icon_rof.ddt`): a rate of fire: a brass case with a crown, a cream face, two hands;
- `hourglass` (`stat_icon_traintime.ddt`): a training time: two glass bulbs between wooden boards and posts;
- `eye` (`stat_icon_los.ddt`): line of sight: an open eye with a blue iris and a dark upper lid;
- `boot_wings` (`stat_icon_speed.ddt`): speed: a riding boot with a white wing and two motion lines;
- `shield` (`stat_icon_armor.ddt`): armor / resistance: a steel heater shield with a gold rim;
- `cylinder` (`stat_icon_projectiles.ddt`): projectiles per reload: a revolver's cylinder seen from the
  chambers' side, six chambers around the centre pin.

Unit type icons (bold style; the pictures after a bonus multiplier, "1.5x against <icon>"), written by
`--types <art folder>` at the mod's own paths so that no data changes (TYPE_FILES), with `--png <sheet> --compare
<game copy>` a before / after sheet enlarged 4 times:
- `standing` (ui/ingame/stat_icon_infantry, WoL/.../stat_icon_standing_unit) and `line`
  (ui/ingame/stat_icon_heavy_infantry): the game's infantryman, in a shako, red coat and blue coat;
- `winged_bullet` (WoL/.../stat_icon_ranged, the maneuver unit), `helmet` (hand cavalry), `bolt_wings` (shock
  unit), `cannon` (siege), `cannons` (artillery), `sabre` (mercenary), `star` (hero), `dove` (light infantry),
  `dog` (pet), `bow` (light cavalry), `arrowhead` (native warrior; a new file name, stat_icon_native_warrior).

Soft glyphs: `stopwatch`, `hourglass`, `heart` (`stat_icon_hitpoints.ddt`), `shield`, `eye`, `boot_wings`,
`boot_arrows`, `boot_lines` (speed variants) and `house` (`stat_icon_pop.ddt`).

No pixel comes from the game. `--check` exits with code 1 if a file on disk differs from what would be written.
Test: `tests/test_stat_icons.py`.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

SIZE = 16
SS = 8  # samples per texel side
OUT = ROOT / "out" / "staticons" / "stat_icon_rof.ddt"

OUTLINE = (40, 26, 14)
BRASS = (214, 168, 64)
BRASS_DARK = (150, 106, 34)
FACE = (240, 232, 205)
RIM = (70, 50, 30)
HAND = (30, 22, 14)
MARK = (120, 96, 70)
WOOD = (150, 96, 48)
WOOD_DARK = (96, 58, 26)
GLASS = (200, 222, 230)
SAND = (230, 196, 110)
RED = (212, 30, 30)
RED_DARK = (140, 14, 18)
PINK = (255, 170, 160)
STEEL = (200, 206, 214)
STEEL_DARK = (120, 128, 140)
GOLD = (224, 182, 70)


def _seg_dist(px, py, ax, ay, bx, by):
    """Distance of the points (px, py) from the segment a-b (arrays)."""
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0.0, 1.0)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy))


class Canvas:
    """Supersampled colour and coverage layers in texel units (0..16); later paints cover earlier ones."""

    def __init__(self):
        n = SIZE * SS
        c = (np.arange(n) + 0.5) / SS
        self.x, self.y = np.meshgrid(c, c)
        self.rgb = np.zeros((n, n, 3), np.float32)
        self.cover = np.zeros((n, n), np.float32)

    def paint(self, mask, colour):
        self.rgb[mask] = colour
        self.cover[mask] = 1.0


def stopwatch():
    k = Canvas()
    x, y = k.x, k.y
    cx, cy, r = 8.0, 9.2, 6.2
    d = np.hypot(x - cx, y - cy)
    k.paint((abs(x - cx) <= 0.9) & (y >= 1.6) & (y <= 3.4), BRASS_DARK)
    k.paint((abs(x - cx) <= 1.9) & (y >= 0.9) & (y <= 2.1), BRASS)
    k.paint(_seg_dist(x, y, cx + 4.6, cy - 4.6, cx + 5.6, cy - 5.6) <= 0.75, BRASS_DARK)
    k.paint(d <= r, BRASS)
    k.paint((d <= r) & (x - cx + y - cy > 3.5), BRASS_DARK)
    k.paint(d <= r - 1.1, RIM)
    k.paint(d <= r - 1.7, FACE)
    for q in range(4):
        a = q * math.pi / 2
        mx, my = cx + math.sin(a) * (r - 2.6), cy - math.cos(a) * (r - 2.6)
        k.paint(np.hypot(x - mx, y - my) <= 0.45, MARK)
    k.paint(_seg_dist(x, y, cx, cy, cx, cy - (r - 2.0)) <= 0.8, HAND)
    a = math.radians(60)
    k.paint(_seg_dist(x, y, cx, cy, cx + math.sin(a) * 3.0, cy - math.cos(a) * 3.0) <= 0.8, HAND)
    k.paint(d <= 1.0, HAND)
    return k


def hourglass():
    k = Canvas()
    x, y = k.x, k.y
    # the glass: two bulbs meeting at a neck, |x - 8| below a curve of y
    t = np.abs(y - 8.0)
    half = 0.7 + 0.62 * np.clip(t - 0.4, 0, None) ** 1.1
    inside = (np.abs(x - 8.0) <= half) & (y >= 2.6) & (y <= 13.4)
    k.paint(inside, GLASS)
    # sand: a heap in the bottom bulb and a little left in the top one, and the falling thread
    k.paint(inside & (y >= 10.0) & (np.abs(x - 8.0) <= 3.6 - 0.55 * (13.4 - y)) | inside & (y >= 11.6), SAND)
    k.paint(inside & (y <= 6.2) & (y >= 4.6), SAND)
    k.paint((np.abs(x - 8.0) <= 0.35) & (y >= 7.0) & (y <= 11.0), SAND)
    # the frame: top and bottom boards, two posts
    for top in (1.0, 13.4):
        k.paint((x >= 2.6) & (x <= 13.4) & (y >= top) & (y <= top + 1.6), WOOD)
        k.paint((x >= 2.6) & (x <= 13.4) & (y >= top + 1.1) & (y <= top + 1.6), WOOD_DARK)
    k.paint((np.abs(x - 3.6) <= 0.6) & (y >= 2.6) & (y <= 13.4), WOOD_DARK)
    k.paint((np.abs(x - 12.4) <= 0.6) & (y >= 2.6) & (y <= 13.4), WOOD_DARK)
    return k


def heart():
    k = Canvas()
    x, y = k.x, k.y
    # two circles and a triangle: the classic heart
    lobes = (np.hypot(x - 5.4, y - 5.8) <= 3.4) | (np.hypot(x - 10.6, y - 5.8) <= 3.4)
    tip = (y >= 5.8) & (y <= 14.2) & (np.abs(x - 8.0) <= (14.2 - y) * 0.86)
    shape = lobes | tip
    k.paint(shape, RED)
    k.paint(shape & (x + 0.4 * y > 15.5), RED_DARK)
    k.paint(np.hypot(x - 4.9, y - 4.9) <= 1.1, PINK)
    return k


def shield():
    k = Canvas()
    x, y = k.x, k.y
    # a heater shield: a flat top, straight sides, then two arcs to the point
    def heater(top, bottom, w):
        """Straight sides down to y 6.5, then sides that close in to a point at `bottom`."""
        t = np.clip((y - 6.5) / (bottom - 6.5), 0.0, 1.0)
        half = w * np.cos(t * math.pi / 2) ** 0.7
        return (y >= top) & (y <= bottom) & (np.abs(x - 8.0) <= half)

    outer = heater(1.4, 15.0, 6.2)
    k.paint(outer, GOLD)
    inner = heater(2.7, 13.4, 4.9)
    k.paint(inner, STEEL)
    k.paint(inner & (x > 8.0), STEEL_DARK)
    k.paint(inner & (np.abs(x - 6.0) <= 0.5) & (y <= 9.0), (236, 240, 244))  # a highlight
    return k


def eye():
    k = Canvas()
    x, y = k.x, k.y
    # an almond: the area between two arcs, white, with a blue iris, a dark pupil and a highlight
    u = (x - 8.0) / 7.2
    lid = 4.4 * np.clip(1 - u * u, 0, None)
    almond = (np.abs(u) <= 1.0) & (y >= 8.0 - lid) & (y <= 8.0 + lid * 0.85)
    k.paint(almond, (244, 240, 230))
    d = np.hypot(x - 8.0, y - 8.0)
    k.paint(almond & (d <= 3.3), (60, 110, 190))
    k.paint(almond & (d <= 3.3) & (y > 8.4), (40, 80, 150))
    k.paint(d <= 1.5, (14, 14, 18))
    k.paint(np.hypot(x - 6.9, y - 6.9) <= 0.7, (255, 255, 255))
    # the upper lid, a darker line over the almond
    k.paint((np.abs(u) <= 1.0) & (np.abs(y - (8.0 - lid)) <= 0.55), (70, 40, 20))
    return k


LEATHER = (176, 104, 48)
LEATHER_DARK = (118, 64, 26)
SOLE = (70, 44, 24)
WING = (246, 246, 240)
WING_SHADE = (180, 186, 196)
SPEED_BLUE = (70, 150, 235)


def _boot(k, dx=0.0):
    """A riding boot seen from the side, toe to the right: shaft, foot, a cuff, heel and sole. `dx` shifts it right."""
    x, y = k.x - dx, k.y
    shaft = (x >= 5.4) & (x <= 9.0) & (y >= 2.0) & (y <= 11.0)
    foot = ((x >= 5.4) & (x <= 11.6) & (y >= 9.4) & (y <= 13.0)) | (np.hypot(x - 11.6, y - 11.4) <= 1.7)
    k.paint(shaft | foot, LEATHER)
    k.paint(shaft & (x >= 7.6) & (y <= 9.6), LEATHER_DARK)
    k.paint((x >= 5.0) & (x <= 9.4) & (y >= 2.0) & (y <= 3.4), LEATHER_DARK)  # the cuff
    k.paint((x >= 5.4) & (x <= 13.3) & (y >= 12.6) & (y <= 13.8), SOLE)
    k.paint((x >= 5.4) & (x <= 7.0) & (y >= 12.0) & (y <= 14.2), SOLE)  # the heel


def boot_wings():
    """Speed: the boot with a small white wing at its back, swept back."""
    k = Canvas()
    x, y = k.x, k.y
    for i, (cy, length) in enumerate(((3.6, 6.4), (5.6, 5.6), (7.6, 4.6))):  # behind the boot: painted first
        feather = _seg_dist(x, y, 8.4, cy + 1.0, 8.4 - length, cy - 1.6) <= 1.0
        k.paint(feather, WING if i != 1 else WING_SHADE)
    _boot(k, dx=2.0)
    return k


def boot_arrows():
    """Speed (variant): the boot with three blue motion strokes behind it."""
    k = Canvas()
    _boot(k, dx=2.4)
    x, y = k.x, k.y
    for cy, x0 in ((4.0, 1.2), (7.0, 0.4), (10.0, 1.2)):
        k.paint(_seg_dist(x, y, x0, cy, x0 + 5.0, cy) <= 0.6, SPEED_BLUE)
    return k


def boot_lines():
    """Speed (variant): the boot with white speed lines behind it."""
    k = Canvas()
    _boot(k, dx=2.4)
    x, y = k.x, k.y
    for cy, x0, x1 in ((4.0, 2.0, 7.0), (6.6, 0.6, 7.0), (9.2, 2.0, 7.0)):
        k.paint(_seg_dist(x, y, x0, cy, x1, cy) <= 0.45, WING)
    return k


ROOF = (190, 64, 40)
ROOF_DARK = (128, 38, 24)
WALL = (236, 220, 178)
WALL_DARK = (190, 168, 124)
STONE = (164, 158, 150)
BRICK = (170, 92, 64)


def house():
    """Population: a house seen from the front, a red gabled roof over plaster walls, a door and a chimney.
    Wide and low on purpose: the minimized panel draws its icons narrower than tall, and a steep roof then
    reads as a spike."""
    k = Canvas()
    x, y = k.x, k.y
    # the chimney, behind the roof, in a brick close to the roof's red (one 4x4 DXT block holds both)
    k.paint((x >= 10.6) & (x <= 12.6) & (y >= 2.6) & (y <= 6.0), BRICK)
    walls = (x >= 2.4) & (x <= 13.6) & (y >= 7.6) & (y <= 14.8)
    k.paint(walls, WALL)
    k.paint(walls & (x >= 11.0), WALL_DARK)
    # the roof: a low gable whose eaves overhang the walls, its right slope in shade
    roof = (y >= 1.8) & (y <= 8.6) & (np.abs(x - 8.0) <= (y - 1.8) * 1.0)
    k.paint(roof, ROOF)
    k.paint(roof & (x > 8.0), ROOF_DARK)
    k.paint(roof & (y >= 7.6), ROOF_DARK)  # the eaves' edge
    k.paint((x >= 6.4) & (x <= 9.6) & (y >= 10.0) & (y <= 14.8), WOOD_DARK)  # the door
    k.paint((x >= 2.4) & (x <= 13.6) & (y >= 14.2) & (y <= 14.8), STONE)  # the sill
    return k


# ---- The bold style: 32x32 BGRA, hard edges, a black outline ----
#
# Measured on a mod's own stat icons that the panel shows next to ours (ui\ingame\stat_icon_ranged, _range, _attack,
# _building): 32x32 uncompressed BGRA, alpha "transparent", one level (no mips), solid shapes with strokes of 4 to 7
# texels and a pure black outline 1 to 2 texels wide. The panel draws an icon at about 10 x 14 screen pixels, so a
# 16x16 picture with 1-texel strokes, soft edges and a grey outline comes out thin and blurred. The bold glyphs are
# sampled once per texel (no supersampling), so the alpha is only 0 or 255, every part has its own black contour,
# and the whole glyph a black outline 2 texels wide.

BOLD = 32
BLACK = (0, 0, 0)
# The panel draws icons narrower than tall (about 10 x 14 pixels for a square texture): round parts are drawn
# wider than tall by this factor so that they look round on screen.
AX = 0.72


class Bold:
    """32x32 colour and coverage, one sample per texel centre (coordinates 0..32); later paints cover earlier ones."""

    def __init__(self):
        c = np.arange(BOLD) + 0.5
        self.x, self.y = np.meshgrid(c, c)
        self.rgb = np.zeros((BOLD, BOLD, 3), np.uint8)
        self.cover = np.zeros((BOLD, BOLD), bool)

    def paint(self, mask, colour):
        self.rgb[mask] = colour
        self.cover |= mask

    def contour(self, mask, colour=BLACK):
        """The texels of `mask` next to a texel outside it (4-neighbours): the part's own black line."""
        inner = mask & np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1)
        self.paint(mask & ~inner, colour)

    def part(self, mask, colour):
        self.paint(mask, colour)
        self.contour(mask)

    def cut(self, mask):
        self.cover &= ~mask

    def round(self, cx, cy):
        """The on-screen distance from (cx, cy): x counts AX as much as y."""
        return np.hypot((self.x - cx) * AX, self.y - cy)


def bold_stopwatch():
    """Rate of fire: a brass stopwatch, its crown on top, a cream face with two thick hands."""
    k = Bold()
    x, y = k.x, k.y
    cx, cy = 16.0, 19.5
    k.part((np.abs(x - cx) <= 2.5) & (y >= 5.0) & (y <= 10.0), BRASS_DARK)  # the stem
    k.part((np.abs(x - cx) <= 5.0) & (y >= 2.5) & (y <= 6.5), BRASS)  # the crown
    d = k.round(cx, cy)
    body = d <= 10.0
    k.paint(body, BRASS)
    k.paint(body & ((x - cx) * AX + (y - cy) > 6.0), BRASS_DARK)
    k.paint(d <= 7.8, BLACK)
    k.paint(d <= 6.7, FACE)
    for mx in (cx - 5.2 / AX, cx + 5.2 / AX):  # the 9 and 3 o'clock marks
        k.paint((np.abs(x - mx) <= 1.0) & (np.abs(y - cy) <= 1.0), MARK)
    k.paint((np.abs(x - cx) <= 1.0) & (np.abs(y - (cy + 5.2)) <= 1.0), MARK)
    k.paint((np.abs(x - cx) <= 1.5) & (y >= cy - 5.6) & (y <= cy), HAND)  # the minute hand, to 12
    a = math.radians(60)
    k.paint(_seg_dist(x, y, cx, cy, cx + 4.6 * math.sin(a) / AX, cy - 4.6 * math.cos(a)) <= 1.6, HAND)
    k.paint(k.round(cx, cy) <= 2.2, HAND)
    return k


def bold_hourglass():
    """Train time: an hourglass, two wooden boards and posts around two glass bulbs, sand running down."""
    k = Bold()
    x, y = k.x, k.y
    for post in (7.5, 24.5):
        k.part((np.abs(x - post) <= 2.0) & (y >= 6.0) & (y <= 26.0), WOOD_DARK)
    t = np.abs(y - 16.0)
    half = np.minimum(1.6 + 0.85 * np.clip(t - 1.0, 0, None), 7.0)
    glass = (np.abs(x - 16.0) <= half) & (y >= 7.5) & (y <= 24.5)
    k.paint(glass, GLASS)
    k.paint(glass & (y >= 21.0), SAND)  # the heap below
    k.paint(glass & (y >= 18.0) & (np.abs(x - 16.0) <= (y - 17.5) * 1.1), SAND)
    k.paint(glass & (y >= 10.0) & (y <= 13.0), SAND)  # what is left above
    k.paint((np.abs(x - 16.0) <= 1.0) & (y >= 13.0) & (y <= 21.0), SAND)  # the thread
    k.contour(glass)
    for top in (2.5, 24.5):
        board = (x >= 3.5) & (x <= 28.5) & (y >= top) & (y <= top + 5.0)
        k.paint(board, WOOD)
        k.paint(board & (y >= top + 3.0), WOOD_DARK)
        k.contour(board)
    return k


def bold_eye():
    """Line of sight: an open eye, white with a blue iris, a black pupil, a highlight and a dark upper lid."""
    k = Bold()
    x, y = k.x, k.y
    # flat on purpose: the panel squeezes an icon to about 0.7 of its width, and a taller almond then reads as a ring
    u = (x - 16.0) / 13.5
    lid = 6.8 * np.clip(1 - u * u, 0, None)
    almond = (np.abs(u) <= 1.0) & (y >= 16.0 - lid) & (y <= 16.0 + lid * 0.85)
    k.part(almond, (244, 240, 230))
    d = k.round(16.0, 16.0)
    k.paint(almond & (d <= 4.9), (60, 120, 210))
    k.paint(almond & (d <= 4.9) & (y > 17.0), (36, 82, 160))
    k.paint(d <= 2.3, BLACK)
    k.paint(k.round(13.6, 14.0) <= 1.1, (255, 255, 255))
    k.paint((np.abs(u) <= 1.0) & (y >= 16.0 - lid - 1.5) & (y <= 16.0 - lid + 1.5), (90, 50, 20))  # the upper lid
    return k


def bold_boot_wings():
    """Speed: a riding boot with a white wing at its back and two motion lines behind its foot."""
    k = Bold()
    x, y = k.x, k.y
    # the wing: three feathers fanning back from the shaft, wide at the root, painted lowest first so that each
    # upper one lies over the next
    for i, (x1, y1) in enumerate(((7.0, 17.0), (4.5, 10.5), (5.0, 4.5))):
        vx, vy = x1 - 15.0, y1 - 9.0
        t = np.clip(((x - 15.0) * vx + (y - 9.0) * vy) / (vx * vx + vy * vy), 0.0, 1.0)
        feather = np.hypot(x - (15.0 + t * vx), y - (9.0 + t * vy)) <= 3.8 - 1.6 * t
        k.part(feather, WING_SHADE if i == 1 else WING)
    for ly, x0 in ((21.5, 4.0), (25.5, 6.0)):  # two motion lines behind the foot
        k.part(_seg_dist(x, y, x0, ly, 10.0, ly) <= 1.5, WING)
    shaft = (x >= 13.0) & (x <= 21.0) & (y >= 3.0) & (y <= 22.0)
    foot = ((x >= 13.0) & (x <= 25.5) & (y >= 18.0) & (y <= 26.0)) | (np.hypot(x - 25.5, y - 22.5) <= 3.6)
    sole = ((x >= 12.0) & (x <= 29.0) & (y >= 25.5) & (y <= 28.5)) | ((x >= 12.0) & (x <= 17.0) & (y >= 25.5) &
                                                                      (y <= 30.0))
    boot = shaft | foot | sole
    k.paint(boot, LEATHER)
    k.paint(shaft & (x >= 18.5) & (y <= 18.5), LEATHER_DARK)
    k.paint(sole, SOLE)
    k.contour(boot)
    k.part((x >= 12.0) & (x <= 22.0) & (y >= 2.5) & (y <= 7.0), LEATHER_DARK)  # the cuff
    return k


def bold_shield():
    """Resists: a heater shield, a gold rim around steel, its right half in shade, a highlight on the left."""
    k = Bold()
    x, y = k.x, k.y

    def heater(top, bottom, w):
        t = np.clip((y - 13.0) / (bottom - 13.0), 0.0, 1.0)
        half = w * np.cos(t * math.pi / 2) ** 0.7
        return (y >= top) & (y <= bottom) & (np.abs(x - 16.0) <= half)

    outer = heater(2.0, 30.0, 12.5)
    k.part(outer, GOLD)
    inner = heater(5.5, 26.0, 8.5)
    k.paint(inner, STEEL)
    k.paint(inner & (x > 16.0), STEEL_DARK)
    k.paint(inner & (np.abs(x - 11.5) <= 1.5) & (y >= 8.0) & (y <= 17.0), (236, 240, 244))
    k.contour(inner)
    return k


GUN = (168, 174, 186)
GUN_DARK = (104, 110, 124)
GUN_LIGHT = (214, 220, 230)


def bold_cylinder():
    """Projectiles per reload: a revolver's cylinder seen from the chambers' side: a steel disc, six round chambers
    around the centre pin."""
    k = Bold()
    x, y = k.x, k.y
    cx, cy = 16.0, 16.0
    d = k.round(cx, cy)
    body = d <= 10.0
    k.paint(body, GUN)
    k.paint(body & ((x - cx) * AX + (y - cy) > 4.5), GUN_DARK)
    k.paint(body & ((x - cx) * AX + (y - cy) < -8.0), GUN_LIGHT)
    for q in range(6):  # the chambers
        a = math.radians(60 * q)
        k.paint(k.round(cx + 6.0 * math.sin(a) / AX, cy - 6.0 * math.cos(a)) <= 1.9, BLACK)
    k.paint(d <= 1.4, BLACK)  # the centre pin
    return k


# ---- The unit type icons (the multipliers' "against <icon>" of the attack rows) in the bold style ----
#
# The same recipe as the six above, for the icons a mod's attack rows show after a bonus multiplier, which came at
# 16x16 or smaller. Each glyph is drawn in "screen" coordinates (u, y): u = 16 + (x - 16) * AX, so a shape drawn
# round in (u, y) is wider than tall in the texture and looks round once the panel squeezes it; the drawable u runs
# from about 6.3 to 25.7, y from 2 to 29.5.

def _screen(k):
    return 16.0 + (k.x - 16.0) * AX, k.y


def _poly(u, y, points):
    """Inside the polygon (even-odd rule), in (u, y)."""
    inside = np.zeros(u.shape, bool)
    n = len(points)
    for i in range(n):
        (u0, y0), (u1, y1) = points[i], points[(i + 1) % n]
        crosses = (y0 > y) != (y1 > y)
        at = u0 + (y - y0) * (u1 - u0) / np.where(y1 == y0, 1e-9, y1 - y0)
        inside ^= crosses & (u < at)
    return inside


def _ell(u, y, cu, cy, ru, ry):
    return ((u - cu) / ru) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def _bar(u, y, u0, y0, u1, y1, r):
    return _seg_dist(u, y, u0, y0, u1, y1) <= r


SKIN = (236, 188, 142)
SKIN_SHADE = (190, 136, 96)
SHAKO = (34, 32, 38)
SHAKO_BAND = (110, 108, 118)
BELT = (244, 242, 232)
MUSKET_WOOD = (140, 82, 36)
COATS = {"standing": ((206, 34, 30), (140, 18, 20), (40, 70, 170)),  # red coat, blue collar and cuffs
         "line": ((44, 92, 196), (26, 56, 132), (214, 40, 36))}     # blue coat, red collar and cuffs


def _soldier(coat):
    """An infantryman as the game's infantry icon has him, from the waist up, his musket upright at his right side,
    in a shako (a tall peaked cap with a plate and a pompom) instead of the tricorne, and a coat of `coat`."""
    k = Bold()
    u, y = _screen(k)
    main, shade, facing = COATS[coat]
    k.part(_bar(u, y, 9.0, 6.0, 9.0, 21.0, 0.9) | _bar(u, y, 9.0, 3.0, 9.0, 6.5, 0.45), STEEL)  # barrel, bayonet
    k.part(_poly(u, y, [(8.0, 20.0), (10.0, 20.0), (10.6, 29.5), (7.4, 29.5)]), MUSKET_WOOD)  # the stock
    torso = _poly(u, y, [(11.0, 18.5), (21.0, 18.5), (23.4, 29.5), (8.6, 29.5)])
    k.paint(torso, main)
    k.paint(torso & (u > 18.0), shade)
    for a, b in (((11.6, 19.5), (19.8, 29.5)), ((20.4, 19.5), (12.2, 29.5))):  # the white crossbelts
        k.paint(torso & _bar(u, y, *a, *b, 0.75), BELT)
    k.paint(_ell(u, y, 16.0, 24.4, 1.0, 1.0), BRASS)  # the belt plate
    k.contour(torso)
    for cu in (10.6, 21.4):  # epaulettes
        k.part(_ell(u, y, cu, 19.6, 1.9, 1.4), facing)
    k.part(_poly(u, y, [(13.6, 16.2), (18.4, 16.2), (18.8, 19.4), (13.2, 19.4)]), facing)  # the collar
    k.part(_ell(u, y, 16.0, 13.4, 2.7, 3.0), SKIN)  # the face
    k.paint(_ell(u, y, 17.6, 13.8, 1.1, 2.4) & _ell(u, y, 16.0, 13.4, 2.7, 3.0), SKIN_SHADE)
    k.paint(_ell(u, y, 15.0, 13.0, 0.45, 0.6) | _ell(u, y, 17.0, 13.0, 0.45, 0.6), BLACK)  # the eyes
    k.part(_ell(u, y, 9.6, 21.6, 1.7, 1.6), SKIN)  # the hand on the musket
    shako = _poly(u, y, [(12.6, 10.6), (12.0, 3.6), (20.0, 3.6), (19.4, 10.6)])
    k.paint(shako, SHAKO)
    k.paint(shako & (y <= 5.0), SHAKO_BAND)
    k.contour(shako)
    k.part(_poly(u, y, [(16.0, 6.0), (17.6, 7.7), (16.0, 9.4), (14.4, 7.7)]), BRASS)  # the plate
    k.part(_poly(u, y, [(11.6, 10.2), (20.4, 10.2), (21.4, 11.6), (10.6, 11.6)]), BLACK)  # the peak
    k.part(_ell(u, y, 16.0, 2.9, 1.5, 1.0), main)  # the pompom
    return k


def bold_standing():
    """Standing unit (AbstractInfantry): the infantryman in a red coat."""
    return _soldier("standing")


def bold_line():
    """Line unit (AbstractHeavyInfantry): the infantryman in a blue coat."""
    return _soldier("line")


COPPER = (206, 118, 52)
LEAD = (150, 156, 170)


def bold_winged_bullet():
    """Maneuver unit (AbstractRangedCavalry): a bullet in flight, a white wing on its back and two motion lines."""
    k = Bold()
    u, y = _screen(k)
    root = (13.0, 18.6)
    for i, (tu, ty) in enumerate(((8.6, 14.0), (9.6, 8.0), (13.2, 4.2))):  # three feathers, the lowest first
        r = np.clip(((u - root[0]) * (tu - root[0]) + (y - root[1]) * (ty - root[1])) /
                    ((tu - root[0]) ** 2 + (ty - root[1]) ** 2), 0.0, 1.0)
        feather = np.hypot(u - (root[0] + r * (tu - root[0])), y - (root[1] + r * (ty - root[1]))) <= 3.3 - 1.4 * r
        k.part(feather, WING_SHADE if i == 1 else WING)
    # the bullet, flying to the right: a along its flight from the base, b across it
    a, b = u - 8.4, y - 22.2
    case = (a >= 0.0) & (a <= 8.6) & (np.abs(b) <= 3.6)
    nose = (a > 8.6) & (np.abs(b) <= 3.6 * np.sqrt(np.clip(1 - ((a - 8.6) / 8.4) ** 2, 0, None)))
    k.paint(case, COPPER)
    k.paint(case & (b < -1.6), (240, 168, 96))
    k.contour(case)
    k.paint(nose, LEAD)
    k.paint(nose & (b < -1.4), (206, 212, 224))
    k.contour(nose)
    return k


HELM = (150, 166, 196)
HELM_DARK = (84, 98, 128)
HELM_LIGHT = (222, 230, 244)


def bold_helmet():
    """Hand cavalry: a closed steel helmet seen from the front-left, a comb on top, the visor with its eye slit."""
    k = Bold()
    u, y = _screen(k)
    k.part(_poly(u, y, [(14.6, 2.6), (17.4, 2.6), (17.0, 9.0), (15.0, 9.0)]), HELM_DARK)  # the comb
    dome = _ell(u, y, 16.0, 14.0, 9.4, 10.6) & (y <= 21.0)
    chin = _poly(u, y, [(7.0, 19.0), (25.0, 19.0), (22.6, 28.6), (9.4, 28.6)])
    helmet = dome | chin
    k.paint(helmet, HELM)
    k.paint(helmet & (u > 19.0), HELM_DARK)
    k.paint(_ell(u, y, 12.0, 9.6, 2.2, 3.4) & dome, HELM_LIGHT)
    k.contour(helmet)
    k.paint(helmet & (np.abs(y - 15.8) <= 1.0) & (np.abs(u - 16.0) <= 8.0), BLACK)  # the eye slit
    for vu in (13.0, 16.0, 19.0):  # breathing holes
        k.paint(_ell(u, y, vu, 23.6, 0.7, 0.8), BLACK)
    k.paint(helmet & (np.abs(y - 19.6) <= 0.5), BLACK)  # the visor's edge
    return k


BOLT = (250, 200, 36)
BOLT_DARK = (196, 128, 16)


def bold_bolt_wings():
    """Shock unit (cavalry): a golden lightning bolt between two white wings, as the game's icon has it."""
    k = Bold()
    u, y = _screen(k)
    for side in (-1, 1):  # each wing: three feathers fanning out and up from the bolt
        for i, (tu, ty) in enumerate(((10.8, 22.0), (8.0, 13.8), (8.6, 5.0))):
            ru, ry = 13.6, 20.0
            tu2 = 16.0 + side * (tu - 16.0)
            ru2 = 16.0 + side * (ru - 16.0)
            r = np.clip(((u - ru2) * (tu2 - ru2) + (y - ry) * (ty - ry)) / ((tu2 - ru2) ** 2 + (ty - ry) ** 2), 0, 1)
            feather = np.hypot(u - (ru2 + r * (tu2 - ru2)), y - (ry + r * (ty - ry))) <= 2.6 - 1.0 * r
            k.part(feather, WING_SHADE if i == 1 else WING)
    bolt = _poly(u, y, [(18.4, 2.6), (12.2, 16.4), (16.0, 16.4), (13.4, 29.4), (20.4, 13.2), (16.6, 13.2),
                        (20.6, 2.6)])
    k.paint(bolt, BOLT)
    k.paint(bolt & (u > 17.0) & (y > 12.0), BOLT_DARK)
    k.contour(bolt)
    return k


BRONZE = (196, 140, 60)
BRONZE_DARK = (130, 86, 30)
CARRIAGE = (130, 80, 38)
CARRIAGE_DARK = (86, 50, 22)


def bold_cannon():
    """Siege: a field gun from the side, its bronze barrel raised to the right on a wooden carriage with a wheel."""
    k = Bold()
    u, y = _screen(k)
    k.part(_poly(u, y, [(7.0, 26.0), (17.0, 15.6), (20.0, 18.0), (11.0, 28.4), (7.0, 28.4)]), CARRIAGE)  # trail
    ang = math.radians(32)
    a = (u - 9.0) * math.cos(ang) - (y - 18.6) * math.sin(ang)
    b = (u - 9.0) * math.sin(ang) + (y - 18.6) * math.cos(ang)
    barrel = (a >= 0.0) & (a <= 17.0) & (np.abs(b) <= 3.5 - 0.06 * a)
    k.paint(barrel, BRONZE)
    k.paint(barrel & (b > 0.6), BRONZE_DARK)
    k.contour(barrel)
    k.part((a >= 15.8) & (a <= 17.6) & (np.abs(b) <= 2.6), BRONZE)  # the muzzle ring
    k.part(_ell(u, y, 7.8, 19.6, 1.6, 1.6), BRONZE)  # the cascabel
    d = np.hypot(u - 17.0, y - 22.6)
    wheel = d <= 6.2
    k.paint(wheel, CARRIAGE)
    k.paint(wheel & (d >= 4.4), CARRIAGE_DARK)
    for q in range(4):  # spokes
        t = math.radians(45 * q)
        k.paint(_bar(u, y, 17.0 - 4.6 * math.cos(t), 22.6 - 4.6 * math.sin(t), 17.0 + 4.6 * math.cos(t),
                     22.6 + 4.6 * math.sin(t), 0.6) & wheel, CARRIAGE_DARK)
    k.contour(wheel)
    k.paint(_ell(u, y, 17.0, 22.6, 1.3, 1.3), BLACK)
    return k


def bold_cannons():
    """Artillery: two cannon barrels crossed, muzzles up, the breech knobs below."""
    k = Bold()
    u, y = _screen(k)
    for side in (1, -1):  # the one from bottom right drawn last, over the other
        base = (16.0 - side * 7.6, 26.4)
        top = (16.0 + side * 7.4, 4.6)
        length = math.dist(base, top)
        du, dy = (top[0] - base[0]) / length, (top[1] - base[1]) / length
        a = (u - base[0]) * du + (y - base[1]) * dy
        b = -(u - base[0]) * dy + (y - base[1]) * du
        barrel = (a >= 0) & (a <= length) & (np.abs(b) <= 2.6 - 0.05 * a)
        k.paint(barrel, STEEL)
        k.paint(barrel & (b * side > 0.5), STEEL_DARK)
        k.contour(barrel)
        k.part((a >= length - 1.6) & (a <= length + 0.4) & (np.abs(b) <= 2.4), STEEL)  # the muzzle
        k.part(_ell(u, y, base[0] - du * 1.2, base[1] - dy * 1.2, 1.5, 1.5), STEEL_DARK)  # the knob
    return k


BLADE = (232, 236, 242)
BLADE_DARK = (150, 158, 172)


def bold_sabre():
    """Mercenary: a curved sabre, its blade rising to the right, a gold guard and a dark grip."""
    k = Bold()
    u, y = _screen(k)
    # the blade: between two arcs of a circle centred lower right, from the guard up to the point
    d = np.hypot(u - 26.0, y - 24.0)
    ang = np.degrees(np.arctan2(y - 24.0, u - 26.0))  # -180..180; the blade runs from about 196 (left) to 268 (up)
    ang = np.where(ang < 0, ang + 360, ang)
    t = (ang - 200.0) / (268.0 - 200.0)
    width = 6.0 * (1 - 0.6 * np.clip(t, 0, 1))
    blade = (t >= 0) & (t <= 1) & (d >= 15.4 - width) & (d <= 15.4 + 0.4)
    k.paint(blade, BLADE)
    k.paint(blade & (d < 17.0 - width), BLADE_DARK)
    k.contour(blade)
    k.part(_bar(u, y, 8.6, 20.4, 15.4, 25.6, 1.3), BRASS)  # the guard, across the blade
    k.part(_bar(u, y, 11.0, 24.4, 8.2, 28.0, 1.4), (70, 40, 20))  # the grip
    k.part(_ell(u, y, 7.6, 28.6, 1.4, 1.1), BRASS)  # the pommel
    return k


STAR = (255, 222, 30)
STAR_DARK = (214, 160, 10)


def bold_star():
    """Hero: a five-pointed golden star."""
    k = Bold()
    u, y = _screen(k)
    pts = []
    for i in range(10):
        r = 14.2 if i % 2 == 0 else 5.8
        t = math.radians(-90 + 36 * i)
        pts.append((16.0 + r * math.cos(t) * 0.70, 16.9 + r * math.sin(t)))
    star = _poly(u, y, pts)
    k.paint(star, STAR)
    k.paint(star & (u > 16.0) & (y > 14.0), STAR_DARK)
    k.contour(star)
    return k


DOVE = (248, 248, 244)
DOVE_SHADE = (176, 184, 196)


def bold_dove():
    """Scout unit (light infantry): a white dove in flight, its wings raised."""
    k = Bold()
    u, y = _screen(k)
    body = _ell(u, y, 14.6, 21.0, 7.4, 3.8)
    tail = _poly(u, y, [(9.0, 20.0), (6.4, 16.4), (6.6, 25.6), (9.6, 23.0)])
    head = _ell(u, y, 21.4, 17.8, 2.8, 2.6)
    k.paint(body | tail | head, DOVE)
    k.paint(body & (y > 22.6), DOVE_SHADE)
    k.contour(body | tail | head)
    k.part(_poly(u, y, [(23.8, 16.8), (25.8, 18.2), (23.8, 19.2)]), (230, 150, 40))  # the beak
    k.paint(_ell(u, y, 21.8, 17.2, 0.5, 0.6), BLACK)  # the eye
    root = (15.2, 19.4)
    for i, (tu, ty) in enumerate(((8.4, 7.6), (11.6, 4.4), (16.2, 4.0))):  # the raised wing: three feathers
        r = np.clip(((u - root[0]) * (tu - root[0]) + (y - root[1]) * (ty - root[1])) /
                    ((tu - root[0]) ** 2 + (ty - root[1]) ** 2), 0.0, 1.0)
        feather = np.hypot(u - (root[0] + r * (tu - root[0])), y - (root[1] + r * (ty - root[1]))) <= 3.2 - 1.6 * r
        k.part(feather, DOVE_SHADE if i == 1 else DOVE)
    return k


FUR = (198, 150, 92)
FUR_DARK = (92, 62, 36)


def bold_dog():
    """Pet: a dog's head, pointed ears, a dark muzzle and saddle, looking left."""
    k = Bold()
    u, y = _screen(k)
    head = _ell(u, y, 17.6, 16.4, 6.6, 7.4) | _poly(u, y, [(13.0, 16.0), (7.0, 21.4), (8.6, 25.6), (16.0, 24.4)])
    neck = _poly(u, y, [(16.0, 20.0), (24.6, 16.0), (25.4, 29.4), (14.6, 29.4)])
    for eu in (13.6, 20.6):  # the ears
        k.part(_poly(u, y, [(eu - 2.8, 12.0), (eu - 0.6, 2.6), (eu + 2.6, 11.0)]), FUR_DARK)
    k.paint(neck, FUR)
    k.paint(neck & (u > 21.0), FUR_DARK)
    k.contour(neck)
    k.paint(head, FUR)
    k.paint(head & (u < 12.0), FUR_DARK)  # the muzzle
    k.contour(head)
    k.paint(_ell(u, y, 7.8, 22.0, 1.4, 1.3), BLACK)  # the nose
    k.paint(_ell(u, y, 15.0, 15.0, 0.9, 1.0), BLACK)  # the eye
    k.paint(_bar(u, y, 8.6, 25.0, 14.0, 24.0, 0.5), BLACK)  # the mouth
    return k


BOW = (176, 182, 192)
SHAFT = (150, 92, 44)


def bold_bow():
    """Light cavalry: a recurved bow, its string drawn, with an arrow nocked, the gold head to the lower right."""
    k = Bold()
    u, y = _screen(k)
    d = np.hypot(u - 22.0, y - 16.0)
    ang = np.degrees(np.arctan2(y - 16.0, u - 22.0))
    ang = np.where(ang < 0, ang + 360, ang)
    bow = (ang >= 102) & (ang <= 258) & (np.abs(d - 11.4) <= 2.4)  # the arc, from below round the left to the top
    k.paint(bow, BOW)
    k.paint(bow & (d > 13.0), STEEL_DARK)
    k.contour(bow)
    k.paint(_bar(u, y, 22.0 + 11.4 * math.cos(math.radians(102)), 16.0 + 11.4 * math.sin(math.radians(102)),
                 22.0 + 11.4 * math.cos(math.radians(258)), 16.0 + 11.4 * math.sin(math.radians(258)), 0.5),
            (236, 232, 216))  # the string
    k.part(_bar(u, y, 11.0, 4.6, 21.4, 23.6, 1.1), SHAFT)  # the arrow
    k.part(_poly(u, y, [(25.0, 29.4), (19.0, 25.0), (22.8, 22.2)]), BOLT)  # its head
    k.part(_poly(u, y, [(9.4, 2.6), (13.6, 3.0), (12.0, 7.6)]), (220, 40, 30))  # the fletching
    return k


FLINT = (214, 220, 228)
FLINT_DARK = (132, 140, 156)


def bold_arrowhead():
    """Native warrior: a chipped stone arrowhead, point up, notched at its base."""
    k = Bold()
    u, y = _screen(k)
    head = _poly(u, y, [(16.0, 2.6), (24.6, 22.0), (21.0, 27.0), (18.0, 23.6), (16.0, 29.4), (14.0, 23.6),
                        (11.0, 27.0), (7.4, 22.0)])
    k.paint(head, FLINT)
    k.paint(head & (u > 16.0), FLINT_DARK)
    for cu, cy in ((14.0, 12.0), (18.6, 15.6), (12.4, 19.4), (19.6, 21.6)):  # chips
        k.paint(head & _ell(u, y, cu, cy, 1.0, 1.0), (100, 108, 124) if cu > 16 else (176, 184, 196))
    k.contour(head)
    return k


# The unit type icons: the glyph and every file it is written to, relative to the art folder of the mod. The file
# names are the mod's own (the stock chain's and its attackTypeIcons line's), so no data changes; the arrowhead
# alone goes to a new name, since ui\minimap\native_settlement_16x16 is also the minimap's native village.
TYPE_GLYPHS = {"standing": bold_standing, "line": bold_line, "winged_bullet": bold_winged_bullet,
               "helmet": bold_helmet, "bolt_wings": bold_bolt_wings, "cannon": bold_cannon, "cannons": bold_cannons,
               "sabre": bold_sabre, "star": bold_star, "dove": bold_dove, "dog": bold_dog, "bow": bold_bow,
               "arrowhead": bold_arrowhead}
TYPE_FILES = {
    "standing": ("ui/ingame/stat_icon_infantry.ddt", "WoL/ui/ingame/staticons/stat_icon_standing_unit.ddt"),
    "line": ("ui/ingame/stat_icon_heavy_infantry.ddt",),
    "winged_bullet": ("WoL/ui/ingame/staticons/stat_icon_ranged.ddt",),
    "helmet": ("WoL/ui/ingame/staticons/stat_icon_hand_cavalry.ddt",),
    "bolt_wings": ("ui/ingame/stat_icon_cavalry.ddt",),
    "cannon": ("ui/ingame/stat_icon_siege.ddt",),
    "cannons": ("ui/ingame/stat_icon_artillery.ddt",),
    "sabre": ("ui/ingame/stat_mercenary.ddt",),
    "star": ("ui/ingame/stat_hero.ddt",),
    "dove": ("ui/ingame/stat_light_infantry.ddt",),
    "dog": ("ui/ingame/stat_icon_pet.ddt",),
    "bow": ("ui/ingame/stat_light_cav.ddt",),
    "arrowhead": ("WoL/ui/ingame/staticons/stat_icon_native_warrior.ddt",),
}
# The icon a new file name replaces, for the before / after sheet.
TYPE_BEFORE = {"WoL/ui/ingame/staticons/stat_icon_native_warrior.ddt": "ui/minimap/native_settlement_16x16.ddt"}


def render_type(glyph):
    """32 x 32 x 4 uint8 RGBA of a unit type glyph, as render_bold."""
    return _outlined(TYPE_GLYPHS[glyph]())


def encode_type(glyph):
    return ddt.write_bgra(render_type(glyph), alpha=4, usage=0, mips=False)


def compare_sheet(game, zoom=4):
    """RGB of the mod's icon (left, as found in `game`'s art: loose file, else its .bar archives) and the new one
    (right) for each unit type file, enlarged `zoom` times on the panel's brown, a 32-texel cell each; a file the
    game lacks or cannot decode shows as a grey cell."""
    sys.path.insert(0, str(ROOT / "tools"))
    import bar
    art = pathlib.Path(game) / "art"
    archives = {}
    for path in sorted(art.glob("*.bar")):
        for stored, offset, size in bar.read_entries(str(path)):
            archives.setdefault(stored.lower().replace("/", "\\"), (path, offset, size))
    cell = 32 * zoom
    rows = []
    for glyph, files in TYPE_FILES.items():
        for rel in files:
            rel = TYPE_BEFORE.get(rel, rel)
            loose = art / rel
            data = loose.read_bytes() if loose.exists() else None
            if data is None:
                key = next((k for k in archives if k.endswith(rel.lower().replace("/", "\\"))), None)
                if key:
                    path, offset, size = archives[key]
                    with open(path, "rb") as f:
                        f.seek(offset)
                        data = f.read(size)
            row = np.zeros((cell, cell * 2 + 8, 3), np.float32) + np.array((60, 35, 25), np.float32)
            row[:, cell:cell + 8] = 40
            for i, d in enumerate((data, encode_type(glyph))):
                try:
                    px = np.asarray(ddt.decode(d)).astype(np.float32)
                except Exception:  # noqa: BLE001  (missing, or a header with no pixels)
                    row[:, i * (cell + 8):i * (cell + 8) + cell] = 90
                    continue
                h, w = px.shape[:2]
                scale = cell // max(h, w)
                big = px.repeat(scale, 0).repeat(scale, 1)
                top, left = (cell - big.shape[0]) // 2, i * (cell + 8) + (cell - big.shape[1]) // 2
                a = big[..., 3:4] / 255.0
                area = row[top:top + big.shape[0], left:left + big.shape[1]]
                row[top:top + big.shape[0], left:left + big.shape[1]] = big[..., :3] * a + area * (1 - a)
            rows.append(np.pad(row, ((6, 6), (6, 6), (0, 0)), constant_values=30))
    cols = 4  # pairs per line of the sheet
    while len(rows) % cols:
        rows.append(np.full_like(rows[0], 30))
    lines = [np.concatenate(rows[i:i + cols], axis=1) for i in range(0, len(rows), cols)]
    return np.concatenate(lines, axis=0).astype(np.uint8)


BOLD_GLYPHS = {"stopwatch": bold_stopwatch, "hourglass": bold_hourglass, "eye": bold_eye,
               "boot_wings": bold_boot_wings, "shield": bold_shield, "cylinder": bold_cylinder}
BOLD_FILES = {"stopwatch": "stat_icon_rof.ddt", "hourglass": "stat_icon_traintime.ddt", "eye": "stat_icon_los.ddt",
              "boot_wings": "stat_icon_speed.ddt", "shield": "stat_icon_armor.ddt",
              "cylinder": "stat_icon_projectiles.ddt"}


def render_bold(glyph):
    """32 x 32 x 4 uint8 RGBA of a bold glyph: alpha 0 or 255, a black outline 2 texels wide around it."""
    return _outlined(BOLD_GLYPHS[glyph]())


def _outlined(k):
    solid = k.cover
    padded = np.pad(solid, 2)
    near = np.zeros_like(padded)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if abs(dx) + abs(dy) <= 3:  # a round 2-texel ring, corners cut
                near |= np.roll(np.roll(padded, dy, 0), dx, 1)
    near = near[2:-2, 2:-2]
    out = np.zeros((BOLD, BOLD, 4), np.uint8)
    out[solid, :3] = k.rgb[solid]
    ring = near & ~solid
    out[ring, :3] = BLACK
    out[solid | ring, 3] = 255
    return out


def encode_bold(glyph):
    """As the mod's own stat icons: BGRA, alpha "transparent" (4), usage 0, one level."""
    return ddt.write_bgra(render_bold(glyph), alpha=4, usage=0, mips=False)


GLYPHS = {"stopwatch": stopwatch, "hourglass": hourglass, "heart": heart, "shield": shield, "eye": eye,
          "boot_wings": boot_wings, "boot_arrows": boot_arrows, "boot_lines": boot_lines, "house": house}
FILES = {"stopwatch": "stat_icon_rof.ddt", "hourglass": "stat_icon_traintime.ddt",
         "heart": "stat_icon_hitpoints.ddt", "shield": "stat_icon_armor.ddt", "eye": "stat_icon_los.ddt",
         "boot_wings": "stat_icon_speed.ddt", "boot_arrows": "stat_icon_speed_arrows.ddt",
         "boot_lines": "stat_icon_speed_lines.ddt", "house": "stat_icon_pop.ddt"}


def render(glyph):
    """16 x 16 x 4 uint8 RGBA of the glyph, with a one-texel dark outline around it."""
    k = GLYPHS[glyph]()
    n = SIZE
    rgb = k.rgb.reshape(n, SS, n, SS, 3)
    cov = k.cover.reshape(n, SS, n, SS)
    a = cov.mean(axis=(1, 3))
    weight = cov[..., None]
    colour = (rgb * weight).sum(axis=(1, 3)) / np.maximum(weight.sum(axis=(1, 3)), 1e-6)
    out = np.zeros((n, n, 4), np.float32)
    out[..., :3] = colour
    out[..., 3] = a
    solid = a > 0.35
    near = np.zeros_like(solid)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            near |= np.roll(np.roll(solid, dy, 0), dx, 1)
    ring = near & (a < 0.5)
    out[ring, :3] = OUTLINE
    out[ring, 3] = np.maximum(out[ring, 3], 0.85)
    part = (a >= 0.5) & (a < 0.999)
    out[part, :3] = out[part, :3] * a[part, None] + np.array(OUTLINE, np.float32) * (1 - a[part, None])
    out[part, 3] = 1.0
    return np.clip(np.round(out * np.array([1, 1, 1, 255], np.float32)), 0, 255).astype(np.uint8)


def encode(glyph):
    return ddt.write_dxt(render(glyph), ddt.DXT3, alpha=1, usage=0, mips=False)


def preview(datas):
    """A strip of the decoded icons enlarged to 128 pixels (8x for 16x16, 4x for 32x32), each on the panel's brown
    and on grey."""
    tiles = []
    for data in datas:
        dec = np.asarray(ddt.decode(data)).astype(np.float32)
        scale = max(1, 128 // dec.shape[0])
        big = dec.repeat(scale, 0).repeat(scale, 1)
        al = big[..., 3:4] / 255.0
        pair = [big[..., :3] * al + np.array(bg, np.float32) * (1 - al) for bg in ((60, 35, 25), (200, 200, 200))]
        tiles.append(np.concatenate([pair[0], np.full((big.shape[0], 4, 3), 40, np.float32), pair[1]], axis=1))
        tiles.append(np.full((big.shape[0], 16, 3), 40, np.float32))
    return np.concatenate(tiles[:-1], axis=1).astype(np.uint8)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--glyph", default="stopwatch", choices=sorted(set(GLYPHS) | set(BOLD_GLYPHS)))
    ap.add_argument("--style", choices=("soft", "bold"), default="soft",
                    help="soft: 16x16 DXT3 with soft edges (the first set); bold: 32x32 BGRA, hard edges, black outline")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--all", metavar="FOLDER", help="write every glyph of the style into this folder, under its file name")
    ap.add_argument("--png", help="also write an 8x enlarged preview on the panel's brown and on grey")
    ap.add_argument("--types", metavar="ART", help="write the unit type icons (bold style) into this art folder, at "
                    "their paths under it (ui/ingame/..., WoL/ui/ingame/staticons/...)")
    ap.add_argument("--compare", metavar="GAME", help="with --types and --png: the preview is a sheet of each "
                    "file as this game copy has it (left) and the new one (right), enlarged 4 times")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.types:
        status = 0
        for glyph, rels in TYPE_FILES.items():
            data = encode_type(glyph)
            for rel in rels:
                out = pathlib.Path(a.types) / rel
                if a.check:
                    same = out.exists() and out.read_bytes() == data
                    print(f"{out}: {'same' if same else 'differs'}")
                    status |= 0 if same else 1
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                print(f"{out}: {len(data)} bytes, {ddt.read_header(data).describe()}")
        if a.png and not a.check:
            from core.pngio import encode_png
            sheet = compare_sheet(a.compare) if a.compare else preview([encode_type(g) for g in TYPE_GLYPHS])
            pathlib.Path(a.png).write_bytes(encode_png(sheet))
        return status
    glyphs, files, enc = ((BOLD_GLYPHS, BOLD_FILES, encode_bold) if a.style == "bold" else (GLYPHS, FILES, encode))
    if not a.all and a.glyph not in glyphs:
        ap.error(f"no {a.style} glyph {a.glyph} (choices: {', '.join(sorted(glyphs))})")
    jobs = ([(g, pathlib.Path(a.all) / files[g]) for g in glyphs] if a.all else [(a.glyph, pathlib.Path(a.out))])
    status = 0
    datas = []
    for glyph, out in jobs:
        data = enc(glyph)
        datas.append(data)
        if a.check:
            same = out.exists() and out.read_bytes() == data
            print(f"{out}: {'same' if same else 'differs'}")
            status |= 0 if same else 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"{out}: {len(data)} bytes, {ddt.read_header(data).describe()}")
    if a.png and not a.check:
        from core.pngio import encode_png
        pathlib.Path(a.png).write_bytes(encode_png(preview(datas)))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
