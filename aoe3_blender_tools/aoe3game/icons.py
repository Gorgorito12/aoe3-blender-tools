# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit icons and portraits from a render of the building: the building on a dark, warm
background inside a bevelled frame, as the game's own building icons (64 x 64 icon, 128 x 128
portrait, both DXT1 for the stock house). numpy only."""
BACK_CENTRE = (74, 62, 44)
BACK_EDGE = (22, 18, 13)
FRAME_DARK = (18, 14, 10)
FRAME_LIGHT = (150, 128, 92)


def _np():
    import numpy
    return numpy


def downsample(rgba, size):
    """Box filter of a square image to `size` (the side must be a multiple of it)."""
    np = _np()
    k = rgba.shape[0] // size
    a = rgba[:size * k, :size * k].astype(np.float32)
    return a.reshape(size, k, size, k, a.shape[2]).mean(axis=(1, 3))


def compose(render_rgba, size):
    """An opaque size x size RGB icon from a transparent render (straight alpha, top row first)."""
    np = _np()
    src = downsample(np.asarray(render_rgba), size)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    r = np.clip(np.hypot(x - c, y - c) / (size * 0.72), 0, 1)[..., None]
    back = np.array(BACK_CENTRE, np.float32) * (1 - r) + np.array(BACK_EDGE, np.float32) * r
    a = src[..., 3:4] / 255.0
    out = back * (1 - a) + src[..., :3] * a
    b = max(1, size // 32)                            # frame: dark rim, light bevel inside
    out[:b], out[-b:], out[:, :b], out[:, -b:] = FRAME_DARK, FRAME_DARK, FRAME_DARK, FRAME_DARK
    out[b:2 * b, b:-b] = FRAME_LIGHT
    out[b:-b, b:2 * b] = FRAME_LIGHT
    out[-2 * b:-b, b:-b] = np.array(FRAME_LIGHT, np.float32) * 0.55
    out[b:-b, -2 * b:-b] = np.array(FRAME_LIGHT, np.float32) * 0.55
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)
