# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws unit type icons (the pictures a stat panel puts after a bonus multiplier, "1.5x against <icon>") in a
painted style: 32x32 uncompressed BGRA, one level, drawn at 8 samples per texel side and averaged, so edges are
soft as in the game's own icons; each part is shaded (light from the upper left) and has a thin dark line, and the
glyph a dark outline about 1.2 texels wide. Parts are at least 3 texels wide where it matters: a panel draws these
icons at about 10 x 14 pixels with no mipmaps, and thinner details vanish there.

The panel squeezes a square icon sideways (about 0.7 of its width), so glyphs are drawn in screen coordinates (u, y)
with u = 16 + (x - 16) * AX: round in (u, y), wider than tall in the texture.

    venv\\Scripts\\python -I tools/make_type_icon.py --out <art folder> [--check]
    venv\\Scripts\\python -I tools/make_type_icon.py --png <preview.png> [--glyph line ...]

Glyphs (FILES: where `--out` writes each, under the art folder):
- `line`: an infantryman from the waist up in a bell-topped shako with a brass plate and a plume, a blue coat with
  red collar and epaulettes, white crossbelts, his musket and bayonet upright at his side
  (ui/ingame/stat_icon_heavy_infantry.ddt);
- `standing`: the same in a red coat with blue facings (WoL/ui/ingame/staticons/stat_icon_standing_unit.ddt);
- `winged_arrow`: an arrow flying to the upper right with a white wing at its back and red fletching
  (WoL/ui/ingame/staticons/stat_icon_ranged.ddt; chosen in review: it reads better at the panel's size);
- `winged_bullet`: the alternative for the same file, a bullet flying upward between two spread white wings, a badge
  shape (written only with `--glyph winged_bullet`).

`--png` writes the glyphs enlarged 8 times. No pixel comes from the game.
"""
import argparse
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

N = 32
SS = 8
AX = 0.72
INK = (24, 16, 12)

SKIN = (234, 186, 140)
HAIR = (70, 44, 26)
SHAKO = (40, 40, 48)
BRASS = (222, 176, 70)
WHITE = (240, 238, 230)
STEEL = (196, 202, 212)
WOOD = (150, 92, 44)
COATS = {"line": ((46, 92, 200), (206, 40, 36)),       # blue coat, red facings
         "standing": ((204, 38, 34), (42, 74, 176))}   # red coat, blue facings


class Canvas:
    """Supersampled colour and coverage in texel units (0..32); later paints cover earlier ones."""

    def __init__(self):
        n = N * SS
        c = (np.arange(n) + 0.5) / SS
        self.x, self.y = np.meshgrid(c, c)
        self.u = 16.0 + (self.x - 16.0) * AX
        self.rgb = np.zeros((n, n, 3), np.float32)
        self.cover = np.zeros((n, n), bool)

    def paint(self, mask, colour):
        colour = np.asarray(colour, np.float32)
        self.rgb[mask] = colour[mask] if colour.ndim == 3 else colour
        self.cover |= mask

    def part(self, mask, colour, shade=0.45, line=0.55):
        """A part: shaded from its upper left (bright) to its lower right (dark), with a dark line inside its edge
        `line` texels wide."""
        self.paint(mask, shaded(self, mask, colour, shade))
        if line > 0:
            self.paint(mask & ~erode(mask, line), INK)


def shaded(k, mask, colour, amount):
    if not mask.any():
        return np.zeros(k.rgb.shape, np.float32)
    uu, yy = k.u[mask], k.y[mask]
    u0, u1, y0, y1 = uu.min(), uu.max(), yy.min(), yy.max()
    t = ((k.u - u0) / max(u1 - u0, 1e-3) + (k.y - y0) / max(y1 - y0, 1e-3)) / 2.0
    f = 1.0 + amount * (0.5 - np.clip(t, 0, 1))
    return np.clip(np.asarray(colour, np.float32)[None, None, :] * f[..., None], 0, 255)


def _disc(r):
    s = int(math.ceil(r * SS))
    return [(dy, dx) for dy in range(-s, s + 1) for dx in range(-s, s + 1) if dx * dx + dy * dy <= (r * SS) ** 2]


def erode(mask, r):
    out = mask.copy()
    for dy, dx in _disc(r):
        out &= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def dilate(mask, r):
    out = mask.copy()
    for dy, dx in _disc(r):
        out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def seg(k, a, b, r):
    """Within r (screen units) of the segment a-b, in (u, y)."""
    (au, ay), (bu, by) = a, b
    vu, vy = bu - au, by - ay
    t = np.clip(((k.u - au) * vu + (k.y - ay) * vy) / (vu * vu + vy * vy), 0.0, 1.0)
    return np.hypot(k.u - (au + t * vu), k.y - (ay + t * vy)) <= r


def taper(k, a, b, r0, r1):
    """A stroke from a (radius r0) to b (radius r1)."""
    (au, ay), (bu, by) = a, b
    vu, vy = bu - au, by - ay
    t = np.clip(((k.u - au) * vu + (k.y - ay) * vy) / (vu * vu + vy * vy), 0.0, 1.0)
    return np.hypot(k.u - (au + t * vu), k.y - (ay + t * vy)) <= r0 + (r1 - r0) * t


def ell(k, cu, cy, ru, ry):
    return ((k.u - cu) / ru) ** 2 + ((k.y - cy) / ry) ** 2 <= 1.0


def poly(k, points):
    inside = np.zeros(k.u.shape, bool)
    for i in range(len(points)):
        (u0, y0), (u1, y1) = points[i], points[(i + 1) % len(points)]
        crosses = (y0 > k.y) != (y1 > k.y)
        at = u0 + (k.y - y0) * (u1 - u0) / (y1 - y0 if y1 != y0 else 1e-9)
        inside ^= crosses & (k.u < at)
    return inside


def soldier(coat):
    k = Canvas()
    main, facing = COATS[coat]
    # the musket, upright at his right side (the picture's left): its wooden stock up to the muzzle, a steel
    # muzzle and the bayonet above the shako
    k.part(seg(k, (8.4, 31.0), (9.4, 7.6), 1.25), WOOD, shade=0.35, line=0.45)
    k.part(seg(k, (9.4, 8.2), (9.6, 5.4), 1.0), STEEL, shade=0.3, line=0.4)
    k.part(taper(k, (9.6, 5.8), (9.9, 1.2), 0.65, 0.2), (226, 230, 238), shade=0.2, line=0.35)
    # the coat: rounded shoulders, a little wider at the bottom
    torso = poly(k, [(9.6, 20.0), (22.4, 20.0), (24.6, 31.8), (7.4, 31.8)]) | ell(k, 10.6, 22.0, 2.6, 2.4) | \
        ell(k, 21.4, 22.0, 2.6, 2.4)
    k.part(torso, main, shade=0.55)
    for a, b in (((11.0, 21.2), (20.6, 31.8)), ((21.0, 21.2), (11.4, 31.8))):  # crossbelts, the plate where they cross
        k.part(torso & seg(k, a, b, 1.05), WHITE, shade=0.2, line=0.4)
    k.part(ell(k, 16.0, 26.6, 1.35, 1.25), BRASS, shade=0.4, line=0.4)
    for cu in (10.4, 21.6):  # epaulettes
        k.part(ell(k, cu, 20.9, 2.3, 1.5), facing, shade=0.4)
    k.part(poly(k, [(13.2, 17.9), (18.8, 17.9), (19.4, 21.0), (12.6, 21.0)]), facing)  # the high collar
    k.part(ell(k, 9.4, 23.4, 1.8, 1.7), SKIN, shade=0.3)  # the hand on the musket
    # the head: face, sideburns, two eyes
    face = ell(k, 16.0, 14.4, 3.4, 3.9)
    k.part(face, SKIN, shade=0.5)
    for cu in (12.9, 19.1):
        k.paint(face & ell(k, cu, 13.4, 0.9, 2.2), HAIR)
    for cu in (14.7, 17.3):
        k.paint(ell(k, cu, 14.0, 0.55, 0.7), INK)
    k.paint(seg(k, (15.2, 16.6), (16.8, 16.6), 0.35), (150, 90, 70))
    # the shako: bell-topped, a brass plate, a plume, a glossy peak
    shako = poly(k, [(12.6, 12.0), (11.6, 4.2), (20.4, 4.2), (19.4, 12.0)])
    k.part(shako, SHAKO, shade=0.6)
    k.paint(shako & (k.y <= 5.4) & ~erode(shako, 0.55), INK)
    k.paint(shako & (k.y > 4.8) & (k.y <= 5.9) & erode(shako, 0.55), (150, 150, 160))  # the top band
    k.part(poly(k, [(16.0, 6.6), (18.0, 8.4), (17.4, 10.6), (14.6, 10.6), (14.0, 8.4)]), BRASS, shade=0.5, line=0.4)
    k.part(ell(k, 16.0, 3.4, 1.7, 2.0), facing, shade=0.4)
    peak = poly(k, [(12.2, 11.2), (19.8, 11.2), (21.0, 12.9), (11.0, 12.9)])
    k.part(peak, (26, 26, 30), shade=0.2, line=0.4)
    k.paint(peak & seg(k, (13.0, 11.9), (17.5, 11.9), 0.3), (120, 120, 132))
    return k


FEATHER = (234, 234, 238)
FEATHER_SHADE = (196, 198, 208)


def wing(k, root, side, feathers):
    """A wing: broad tapered feathers from `root`, (dy, angle up from the horizontal, length) each, painted from the
    lowest up so that each upper one lies over the next; `side` -1 spreads it left, 1 right."""
    for i, (dy, ang, length) in reversed(list(enumerate(feathers))):
        r = (root[0], root[1] + dy)
        tip = (r[0] + side * length * math.cos(math.radians(ang)), r[1] - length * math.sin(math.radians(ang)))
        k.part(taper(k, r, tip, 2.3, 1.1), FEATHER if i % 2 == 0 else FEATHER_SHADE, shade=0.2, line=0.45)
    k.part(ell(k, root[0] + side * 1.6, root[1] + 1.2, 2.2, 2.6), FEATHER, shade=0.2, line=0.45)


def wing_at(k, at, feathers):
    """The same in an arrow's frame: (root along, root across, tip along, tip across) per feather, upper first."""
    for i, (ra, rb, ta, tb) in reversed(list(enumerate(feathers))):
        k.part(taper(k, at(ra, rb), at(ta, tb), 2.2, 1.0), FEATHER if i % 2 == 0 else FEATHER_SHADE, shade=0.2,
               line=0.45)


def winged_bullet():
    """A bullet flying upward between two spread wings."""
    k = Canvas()
    for s in (-1, 1):  # the wings: four broad feathers each, overlapping, fanning out and up from behind the bullet
        wing(k, (16.0 + s * 1.5, 15.0), s, ((0.0, 40.0, 10.4), (1.8, 26.0, 10.0), (3.6, 11.0, 8.8), (5.4, -4.0, 7.0)))
    case = (np.abs(k.u - 16.0) <= 3.4) & (k.y >= 16.0) & (k.y <= 29.6)
    t = np.clip((16.0 - k.y) / 10.5, 0.0, 1.0)
    nose = (k.y < 16.0) & (k.y >= 5.5) & (np.abs(k.u - 16.0) <= 3.4 * np.sqrt(np.clip(1 - t * t, 0, 1)))
    k.part(case, (214, 128, 56), shade=0.7, line=0.5)
    for gy in (24.6, 27.0):  # two grooves
        k.paint(case & (np.abs(k.y - gy) <= 0.45) & erode(case, 0.5), (120, 64, 26))
    k.paint(case & (np.abs(k.u - 14.6) <= 0.6) & (k.y >= 17.0) & (k.y <= 23.5), (250, 190, 120))  # a highlight
    k.part(nose, (176, 180, 192), shade=0.7, line=0.5)
    k.paint(nose & (np.abs(k.u - 14.7) <= 0.55) & (k.y >= 9.0) & (k.y <= 15.0), (236, 238, 244))
    return k


def winged_arrow():
    """An arrow flying to the upper right, a white wing at its back, red fletching."""
    k = Canvas()
    tail, tip = np.array((9.5, 29.0)), np.array((26.0, 4.2))
    d = (tip - tail) / np.linalg.norm(tip - tail)
    p = np.array((d[1], -d[0]))  # across the shaft, toward the upper left

    def at(a, b):
        return tuple(tail + a * d + b * p)

    wing_at(k, at, ((15.2, 0.6, 7.8, 9.4), (13.6, 0.6, 5.4, 7.6), (12.0, 0.6, 3.6, 5.2), (10.4, 0.6, 2.6, 2.8)))
    for sgn in (1, -1):  # the fletching
        k.part(poly(k, [at(0.6, 0.4 * sgn), at(4.6, 0.4 * sgn), at(2.6, 2.6 * sgn), at(-0.8, 2.8 * sgn)]),
               (204, 40, 36), shade=0.4, line=0.45)
    k.part(seg(k, at(0.0, 0.0), at(23.5, 0.0), 0.95), WOOD, shade=0.3, line=0.4)
    head = poly(k, [at(29.6, 0.0), at(22.0, 3.0), at(23.6, 0.0), at(22.0, -3.0)])
    k.part(head, STEEL, shade=0.6, line=0.45)
    return k


GLYPHS = {"line": lambda: soldier("line"), "standing": lambda: soldier("standing"),
          "winged_bullet": winged_bullet, "winged_arrow": winged_arrow}
FILES = {"line": ("ui/ingame/stat_icon_heavy_infantry.ddt",),
         "standing": ("WoL/ui/ingame/staticons/stat_icon_standing_unit.ddt",),
         "winged_arrow": ("WoL/ui/ingame/staticons/stat_icon_ranged.ddt",)}
ALTERNATIVES = {"winged_bullet": "winged_arrow"}  # glyph -> the one whose file it can replace


def render(glyph):
    """32 x 32 x 4 uint8 RGBA: the glyph over a dark outline, averaged down from the samples."""
    k = GLYPHS[glyph]()
    ring = dilate(k.cover, 1.2) & ~k.cover
    rgb = k.rgb.copy()
    rgb[ring] = INK
    cover = (k.cover | ring).astype(np.float32)
    rgb = rgb.reshape(N, SS, N, SS, 3)
    cov = cover.reshape(N, SS, N, SS)
    a = cov.mean(axis=(1, 3))
    colour = (rgb * cov[..., None]).sum(axis=(1, 3)) / np.maximum(cov.sum(axis=(1, 3)), 1e-6)[..., None]
    out = np.zeros((N, N, 4), np.uint8)
    out[..., :3] = np.clip(np.round(colour), 0, 255)
    out[..., 3] = np.clip(np.round(a * 255), 0, 255)
    out[out[..., 3] == 0, :3] = 0
    return out


def encode(glyph):
    """As a mod's own stat icons: BGRA, alpha "transparent" (4), usage 0, one level."""
    return ddt.write_bgra(render(glyph), alpha=4, usage=0, mips=False)


def preview(glyphs, zoom=8, bg=(60, 35, 25)):
    """RGB strip of the glyphs enlarged `zoom` times (nearest) over a flat background."""
    tiles = []
    for glyph in glyphs:
        e = render(glyph).astype(np.float32).repeat(zoom, 0).repeat(zoom, 1)
        a = e[..., 3:4] / 255.0
        tiles += [e[..., :3] * a + np.array(bg, np.float32) * (1 - a), np.full((N * zoom, 8, 3), 30, np.float32)]
    return np.concatenate(tiles[:-1], axis=1).astype(np.uint8)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", metavar="ART", help="write the glyphs into this art folder, at their paths (FILES)")
    ap.add_argument("--glyph", action="append", choices=sorted(GLYPHS), help="only these glyphs (repeatable)")
    ap.add_argument("--check", action="store_true", help="with --out: exit 1 if a file differs from what is drawn")
    ap.add_argument("--png", help="write the glyphs enlarged 8 times on the panel's brown (PNG)")
    a = ap.parse_args(argv)
    glyphs = a.glyph or list(FILES)
    status = 0
    if a.out:
        for glyph in glyphs:
            rel = FILES[ALTERNATIVES.get(glyph, glyph)]
            data = encode(glyph)
            for r in rel:
                out = pathlib.Path(a.out) / r
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
        pathlib.Path(a.png).write_bytes(encode_png(preview(a.glyph or list(GLYPHS))))
        print(f"{a.png}: written")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
