# SPDX-License-Identifier: GPL-3.0-or-later
"""The flag designer's work: a game copy's flag sets measured once (tools/make_flag.py: the
frames every set shares, where the flag goes, the colour of each button state, the postgame
painting), then any design shown as every texture of a set while it changes, and the set
written when it is right. The copy is only read."""
import base64
import os
import re

from . import use_core

use_core()
import numpy as np  # noqa: E402

import make_flag  # noqa: E402  (tools/)
from aoe3game import ddt  # noqa: E402
from core import paint as painter  # noqa: E402
from core import pngio  # noqa: E402

NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")
KINDS = ["flag", "postgame"] + [f"button_{s}" for s in make_flag.STATES] + [f"large_{s}" for s in make_flag.STATES]


class FlagError(ValueError):
    pass


class Measured:
    def __init__(self, game, flags_dir, buttons_dir):
        self.game, self.flags_dir, self.buttons_dir = game, flags_dir, buttons_dir
        try:
            self.kinds, self.names = make_flag.survey(game, flags_dir, buttons_dir)
        except (ValueError, KeyError, IndexError, OSError) as e:
            raise FlagError(f"no flag sets to measure there ({e}): check the folders") from None
        if not self.names or self.kinds["postgame"].box is None:
            raise FlagError("no complete flag set in those folders")
        self.fits = make_flag.state_fits(self.kinds)


def _png(rgba):
    return "data:image/png;base64," + base64.b64encode(painter.png_bytes(np.asarray(rgba, np.uint8), level=3)).decode("ascii")


def measure(game, flags_dir, buttons_dir):
    if not game or not os.path.isdir(os.path.join(game, "art")):
        raise FlagError("a game copy (a folder with art) is needed")
    return Measured(game, flags_dir, buttons_dir)


def public(m):
    return {"sets": m.names, "count": len(m.names), "kinds": [k for k in KINDS if k in m.kinds or k == "flag"]}


def design_of(data_url, crop=None):
    """The design as an RGB array, cut to `crop` (x0, y0, x1, y1 in fractions) when given."""
    head, _, body = (data_url or "").partition(",")
    if head != "data:image/png;base64":
        raise FlagError("a PNG picture is expected")
    img = np.asarray(pngio.read_png(base64.b64decode(body)))
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    img = img[..., :3]
    if crop:
        h, w = img.shape[:2]
        x0, y0, x1, y1 = (float(v) for v in crop)
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise FlagError("the crop is a box inside the picture")
        img = img[int(y0 * h):max(int(y0 * h) + 1, int(round(y1 * h))), int(x0 * w):max(int(x0 * w) + 1, int(round(x1 * w)))]
    if min(img.shape[:2]) < 4:
        raise FlagError("the design is too small")
    return img


def preview(m, data_url, crop=None):
    images = make_flag.set_images(design_of(data_url, crop), m.kinds, fits=m.fits)
    return {k: _png(v) for k, v in images.items()}


def existing(m, name):
    """A set already in the copy, to compare with."""
    if name not in m.names:
        raise FlagError(f"no set {name}")
    paths = {"flag": os.path.join(m.flags_dir, name), "postgame": os.path.join(m.flags_dir, f"ingame_ui_postgame_flag_{name}")}
    for s in make_flag.STATES:
        paths["button_" + s] = os.path.join(m.buttons_dir, f"flag_{name}_{s}")
        paths["large_" + s] = os.path.join(m.buttons_dir, f"flag_{name}_large_{s}")
    out = {}
    for k, rel in paths.items():
        p = os.path.join(m.game, "art", rel + ".ddt")
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                out[k] = _png(ddt.decode(fh.read(), 0))
    return out


def write(m, data_url, crop, name, out):
    """Writes the set under `out` (laid out like the copy's art folder) with a preview sheet."""
    if not NAME.match(name or ""):
        raise FlagError("the set's name: letters, digits and _")
    if os.path.normcase(os.path.abspath(out)).startswith(os.path.normcase(os.path.abspath(m.game)) + os.sep):
        raise FlagError("refusing to write into the game copy: the set is written beside it, then deployed")
    files = make_flag.make_set(design_of(data_url, crop), name, m.kinds, out, m.flags_dir, m.buttons_dir, fits=m.fits)
    sheet = os.path.join(out, f"{name}_preview.png")
    make_flag.preview(files, m.game, m.flags_dir, m.buttons_dir, [], sheet)
    return {"files": files, "sheet": sheet, "folder": out}
