# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/make_command_icon.py. Needs numpy (the venv):

    venv/Scripts/python -I tests/test_command_icons.py
"""
import os
import pathlib
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))

import make_command_icon as mci  # noqa: E402
from aoe3game import ddt  # noqa: E402


class CommandIcons(unittest.TestCase):
    def test_format_as_the_mod_buttons(self):
        for state in ("on", "off"):
            data = mci.encode("autoscout", state)
            h = ddt.read_header(data)
            self.assertEqual((h.width, h.height, h.format, h.alpha, h.usage, h.mips), (64, 64, ddt.BGRA, 0, 0, 1), state)
            self.assertEqual(len(data), 16 + 8 + 64 * 64 * 4, state)

    def test_frame_and_marks(self):
        on = np.asarray(ddt.decode(mci.encode("autoscout", "on")))[..., :3].astype(int)
        off = np.asarray(ddt.decode(mci.encode("autoscout", "off")))[..., :3].astype(int)
        for img in (on, off):
            self.assertTrue((img[0, :, 2] > img[0, :, 0]).all())       # the outer frame is blue
            self.assertTrue((img[4, 5:-5] < 20).all())                  # the black line inside it
        green = (on[..., 1] > 140) & (on[..., 0] < 80)
        self.assertGreater(green[5:30, 32:60].sum(), 40)                # the tick, top right
        red = (off[..., 0] > 180) & (off[..., 1] < 60)
        self.assertGreater(red[38:60, 5:30].sum(), 40)                  # the cross, bottom left
        inside = off[5:-5, 5:-5]
        self.assertTrue((inside[..., 0] >= inside[..., 1]).mean() > 0.95)  # the "off" picture is tinted red

    def test_deterministic_and_check(self):
        self.assertEqual(mci.encode("autoscout", "on"), mci.encode("autoscout", "on"))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mci.main(["--all", tmp]), 0)
            names = sorted(p.name for p in pathlib.Path(tmp).iterdir())
            self.assertEqual(names, ["uhc_autoscout_start.ddt", "uhc_autoscout_stop.ddt"])
            self.assertEqual(mci.main(["--all", tmp, "--check"]), 0)
            (pathlib.Path(tmp) / "uhc_autoscout_stop.ddt").write_bytes(b"x")
            self.assertEqual(mci.main(["--all", tmp, "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
