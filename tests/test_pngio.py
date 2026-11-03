# SPDX-License-Identifier: GPL-3.0-or-later
"""The PNG reader against PNGs written here with each of the five row filters.

    venv\\Scripts\\python -I tests\\test_pngio.py
"""
import os
import struct
import sys
import tempfile
import unittest
import zlib

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import paint, pngio  # noqa: E402


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def encode(img, filters):
    """A PNG of `img` (h, w, n uint8) whose row y uses filters[y % len(filters)]."""
    h, w, n = img.shape
    ctype = {1: 0, 3: 2, 4: 6}[n]
    rows = img.reshape(h, w * n).astype(int)
    raw = bytearray()
    prev = [0] * (w * n)
    for y in range(h):
        f = filters[y % len(filters)]
        cur = rows[y].tolist()
        out = []
        for x, v in enumerate(cur):
            a = cur[x - n] if x >= n else 0
            b = prev[x]
            c = prev[x - n] if x >= n else 0
            pred = [0, a, b, (a + b) >> 1, _paeth(a, b, c)][f]
            out.append((v - pred) & 255)
        raw += bytes([f] + out)
        prev = cur

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (pngio.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


class PngRead(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(5)
        self.img = rng.integers(0, 256, (13, 17, 3), dtype=np.uint8)

    def test_each_filter(self):
        for f in range(5):
            with self.subTest(filter=f):
                self.assertTrue((pngio.read_png(encode(self.img, [f])) == self.img).all())

    def test_mixed_filters_and_channels(self):
        for n in (1, 3, 4):
            img = np.random.default_rng(n).integers(0, 256, (9, 11, n), dtype=np.uint8)
            self.assertTrue((pngio.read_png(encode(img, [0, 1, 2, 3, 4])) == img).all())

    def test_reads_what_the_painter_saves(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.png")
            paint.save_png(self.img, path)
            with open(path, "rb") as f:
                self.assertTrue((pngio.read_png(f.read()) == self.img).all())

    def test_palette(self):
        idx = np.random.default_rng(3).integers(0, 4, (6, 7, 1), dtype=np.uint8)
        pal = np.array([[10, 20, 30], [200, 100, 0], [0, 255, 0], [9, 9, 9]], np.uint8)
        png = bytearray(encode(idx, [1, 4]))
        png[25] = 3                                     # colour type: palette
        ihdr = bytes(png[12:29])
        png[29:33] = struct.pack(">I", zlib.crc32(ihdr))
        plte = pal.tobytes()
        chunk = struct.pack(">I", len(plte)) + b"PLTE" + plte + struct.pack(">I", zlib.crc32(b"PLTE" + plte))
        png = bytes(png[:33]) + chunk + bytes(png[33:])
        self.assertTrue((pngio.read_png(png) == pal[idx[:, :, 0]]).all())

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            pngio.read_png(b"GIF89a....")


if __name__ == "__main__":
    unittest.main(verbosity=2)
