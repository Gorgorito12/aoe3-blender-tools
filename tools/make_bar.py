# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws a health-bar texture in another colour, shaded like the game's own green, yellow and red bars.

    python -I tools/make_bar.py [--colour RRGGBB] [--out <file.ddt>]          writes it (default FF8C00, an orange,
                                                                             to out/bars/health_bar.ddt)
    python -I tools/make_bar.py [--colour RRGGBB] [--out <file.ddt>] --check  exit code 1 if the file differs

It has the layout of the game's ui\\ingame\\ingame_ui_health_yellow (16x8 texels, DXT1, one mip): a darker top
line, a light band, the colour itself, then two darker lines at the bottom. A UI progress bar or a mod's own bar
can name it as a texture (a path under art, without the extension). No pixel comes from the game: the shades
are worked out from the colour.
"""
import pathlib
import struct
import sys

OUT = pathlib.Path(__file__).resolve().parents[1] / "out" / "bars"
WIDTH, HEIGHT = 16, 8
DEFAULT_COLOUR = (0xFF, 0x8C, 0x00)  # an orange that reads apart from the stock green, yellow and red


def scaled(colour, factor):
    return tuple(min(255, round(c * factor)) for c in colour)


def towards_white(colour, share):
    return tuple(round(c + (255 - c) * share) for c in colour)


def rows(colour):
    """The colour of each of the 8 rows, top to bottom."""
    edge = scaled(colour, 0.76)
    light = towards_white(colour, 0.22)
    dark = scaled(colour, 0.48)
    lower = tuple((2 * c + d) // 3 for c, d in zip(colour, dark))  # a DXT1 interpolant of the colour and dark
    return [edge, light, light, light, colour, colour, lower, dark]


def rgb565(colour):
    r, g, b = colour
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def expand(value):
    r, g, b = value >> 11 & 31, value >> 5 & 63, value & 31
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def block(texels):
    """A DXT1 block of 4x4 texels, given as 4 rows of one colour each: the darkest and the lightest rows are the two
    end colours (in four-colour order, the first above the second), every row takes the nearest of the four."""
    ends = sorted({rgb565(c) for c in texels}, reverse=True)
    first, second = ends[0], ends[-1]
    if first == second:
        return struct.pack("<HHI", first, first, 0)
    a, b = expand(first), expand(second)
    palette = [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]
    indices = 0
    for y, colour in enumerate(texels):
        index = min(range(4), key=lambda i: sum((p - c) ** 2 for p, c in zip(palette[i], colour)))
        for x in range(4):
            indices |= index << (2 * (y * 4 + x))
    return struct.pack("<HHI", first, second, indices)


def ddt(colour):
    """The RTS3 container as the stock bar has it: usage 0, alpha 0, format 4 (DXT1), one mip."""
    shades = rows(colour)
    data = b"".join(block(shades[by:by + 4]) for by in range(0, HEIGHT, 4) for _ in range(0, WIDTH, 4))
    header = b"RTS3" + bytes((0, 0, 4, 1)) + struct.pack("<II", WIDTH, HEIGHT)
    return header + struct.pack("<II", len(header) + 8, len(data)) + data


def parse_colour(text):
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        sys.exit(f"make_bar: {text!r}: expected a colour as RRGGBB (hex)")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def main():
    args = sys.argv[1:]
    check = "--check" in args
    colour, out = DEFAULT_COLOUR, OUT / "health_bar.ddt"
    if "--colour" in args:
        colour = parse_colour(args[args.index("--colour") + 1])
    if "--out" in args:
        out = pathlib.Path(args[args.index("--out") + 1])
    data = ddt(colour)
    if check:
        same = out.exists() and out.read_bytes() == data
        print(f"make_bar: {out.name} {'is current' if same else 'differs'}")
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"make_bar: wrote {out} ({len(data)} bytes, colour {''.join(f'{c:02X}' for c in colour)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
