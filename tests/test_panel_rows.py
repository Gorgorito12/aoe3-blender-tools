# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/panel_rows.py and tools/draw_praying_hands.py on synthetic data (numpy and Pillow):

    venv\\Scripts\\python -I tests/test_panel_rows.py
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import draw_praying_hands  # noqa: E402
import panel_rows as pr  # noqa: E402
from aoe3_blender_tools.aoe3game import ddt  # noqa: E402


def synthetic_panel():
    """A 1024 x 1024 texture with a 5-row panel at x 440..688, y 784..1018: rope bars, a blue-grey plank with
    an arrow, red wood, a coloured square 'icon' per row."""
    rng = np.random.default_rng(3)
    img = np.zeros((1024, 1024, 4), np.uint8)
    img[..., 3] = 255
    img[..., :3] = rng.integers(20, 40, (1024, 1024, 3))
    tops = [784, 830, 876, 922, 968, 1018]
    cols = [(220, 120, 20), (180, 30, 30), (200, 200, 160), (230, 190, 40), (60, 90, 200)]
    for i in range(5):
        a, b = tops[i], tops[i + 1]
        img[a:b, 440:688, :3] = (70, 25, 20)                                 # wood
        ax = pr.arrow_x(b - a - pr.BAR)
        for y in range(a + pr.BAR, b):
            img[y, 450:int(ax[y - a - pr.BAR]), :3] = (45, 45, 60)           # plank and arrow
        img[a:a + pr.BAR, 440:688, :3] = (90, 90, 100)                       # rope bar
        img[a + 15:b - 6, 524:548, :3] = cols[i]                             # the icon
    return img, tops


class PanelRows(unittest.TestCase):
    def test_blank_strip_removes_the_icon_and_keeps_the_plank(self):
        img, tops = synthetic_panel()
        strip = img[tops[3]:tops[4], 440:688].astype(np.float32)
        blank = pr.blank_strip(strip, 440)
        self.assertLess(blank[20, 536 - 440, :3].max(), 120)           # the icon is gone
        self.assertEqual(tuple(blank[20, 460 - 440, :3]), (45, 45, 60))  # the plank stays

    def test_move_row_keeps_the_icon_square(self):
        img, tops = synthetic_panel()
        strip = img[tops[3]:tops[4], 440:688].astype(np.float32)          # 46 rows, icon 24 x 25
        moved = pr.move_row(strip, 39, 440, 0)
        self.assertEqual(moved.shape[:2], (39, 248))
        gold = (np.abs(moved[..., :3] - (230, 190, 40)).sum(-1) < 60)
        ys, xs = np.nonzero(gold)
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        self.assertAlmostEqual(w / h, 24 / 25, delta=0.15)             # scaled the same both ways

    def test_build_and_encode_keep_the_rest_byte_for_byte(self):
        img, tops = synthetic_panel()
        data = ddt.write(img, ddt.DXT3, alpha=4, mips=False)
        hd = ddt.read_header(data)
        dec = ddt.decode(data).astype(np.float32)
        icon = Image.new("RGBA", (32, 32), (250, 250, 250, 255))
        panel = {"id": "T", "x": [440, 688], "bottom": 1018, "blank_from": "gold",
                 "rows": [["oil", 784, 830], ["food", 830, 876], ["wood", 876, 922], ["gold", 922, 968],
                          ["vill", 968, 1018]],
                 "order": ["oil", "new", "food", "wood", "gold", "vill"]}
        out, new_tops = pr.build_panel(dec, panel, {"new": {"image": icon, "height": 0.8, "smear": [60, 90, 150]}}, ".")
        self.assertEqual(new_tops, [784, 823, 862, 901, 940, 979, 1018])
        rgba = np.clip(out + 0.5, 0, 255).astype(np.uint8)
        enc, changed = pr.encode_like(data, hd, rgba)
        self.assertEqual(len(enc), len(data))
        self.assertGreater(changed, 0)
        _, a = ddt.level_blocks(data)
        _, b = ddt.level_blocks(enc)
        # blocks wholly outside the panel (x < 440 or y < 784) keep their bytes
        bw = 1024 // 4
        idx = np.arange(a.shape[0])
        outside = ((idx % bw) * 4 + 3 < 440) | ((idx // bw) * 4 + 3 < 784)
        self.assertTrue((a[outside] == b[outside]).all())
        # the new row has the icon's white in its middle
        dec2 = ddt.decode(enc)
        row = dec2[823:862, 440:688]
        self.assertGreater(row[..., :3].min(-1).max(), 200)

    def test_spec_run_writes_textures_and_positions(self):
        img, _ = synthetic_panel()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "in", "art"))
            with open(os.path.join(tmp, "in", "art", "t.ddt"), "wb") as f:
                f.write(ddt.write(img, ddt.DXT3, alpha=4, mips=False))
            draw_praying_hands.draw(64).save(os.path.join(tmp, "icon.png"))
            spec = {"icons": {"faith": {"file": "icon.png", "height": 0.9, "smear": [60, 90, 150]}},
                    "textures": [{"file": "art/t.ddt", "panels": [
                        {"id": "T", "x": [440, 688], "bottom": 1018, "blank_from": "gold",
                         "rows": [["oil", 784, 830], ["food", 830, 876], ["wood", 876, 922], ["gold", 922, 968],
                                  ["vill", 968, 1018]],
                         "order": ["oil", "faith", "food", "wood", "gold", "vill"]}]}]}
            with open(os.path.join(tmp, "spec.json"), "w", encoding="utf-8") as f:
                json.dump(spec, f)
            sys.argv = ["panel_rows", "--spec", os.path.join(tmp, "spec.json"), "--in", os.path.join(tmp, "in"),
                        "--out", os.path.join(tmp, "out"), "--positions", os.path.join(tmp, "rows.json")]
            pr.main()
            self.assertTrue(os.path.exists(os.path.join(tmp, "out", "art", "t.ddt")))
            with open(os.path.join(tmp, "rows.json"), encoding="utf-8") as f:
                rows = json.load(f)
            self.assertEqual(rows["T"]["order"][1], "faith")

    def test_praying_hands_is_an_rgba_icon(self):
        im = draw_praying_hands.draw(64)
        self.assertEqual(im.size, (64, 64))
        a = np.asarray(im)[..., 3]
        self.assertEqual(a[0, 0], 0)                  # transparent corner
        self.assertGreater(a[32, 32], 200)            # the hands in the middle


if __name__ == "__main__":
    unittest.main()
