# SPDX-License-Identifier: GPL-3.0-or-later
"""Repaints a generated texture with Stable Diffusion + ControlNet (a local ComfyUI, see
core/comfy.py and docs/ai-textures.md), one atlas region at a time, and puts the result back
exactly where it was.

The generated atlas is the input: each region (a facade, the roof, the plinth...) is cut out with
a margin of its own edge pixels, cut into overlapping tiles no longer than twice their height
(SDXL draws badly far from square), scaled to SDXL's size, repainted at a low denoise under a
ControlNet that follows the region's own edges, scaled back and feathered together. The alpha
(the player-colour mask) and the pixels under it are kept; the region's mean colour is kept too
(SDXL drifts). Regions without a prompt for their role, or thinner than MIN_SIDE pixels, are left
as they are. Pure Python with numpy.
"""
import time

import numpy as np

from . import comfy
from .pngio import encode_png, read_png

MIN_SIDE = 40           # texture pixels: thinner regions (trims, rails) are left alone
MARGIN = 8              # texture pixels of the region's own edge replicated around it
TILE_ASPECT = 2.0       # a tile is at most twice as long as it is high
OVERLAP = 0.2           # of a tile's length, feathered with its neighbour
SD_LONG = 1024          # SDXL size of a tile's long side (multiples of 64)
GUARD_FACTOR = 0.65     # the strength of the second try when a region's edges moved

STYLE_TEXT = ("hand-painted texture for a real-time strategy game, {}, painterly brush strokes, "
              "flat frontal orthographic view, flat even lighting, no shadows, no perspective, "
              "rich detail")
NEGATIVE = ("photo, photograph, 3d render, perspective, cast shadows, dark shadows, vignette, people, "
            "text, letters, watermark, signature, blurry, noise, frame, border")

# style -> region -> what it is (the prompt's material); a region not listed is not repainted
MATERIALS = {
    "NEOCLASSICAL": {
        "front": "light ashlar stone facade with white window frames and dark glass",
        "back": "light ashlar stone facade with white window frames and dark glass",
        "side": "light ashlar stone facade with white window frames and dark glass",
        "bow": "light ashlar stone facade with white window frames and dark glass",
        "wing_long": "light ashlar stone facade with white window frames",
        "wing_short": "light ashlar stone facade with white window frames",
        "roof": "dark grey slate roof tiles in rows",
        "plinth": "large grey stone blocks",
        "stone": "pale grey stone paving",
        "pedi": "white stone pediment",
    },
    "COLONIAL": {
        "front": "whitewashed lime plaster wall of a Spanish colonial house, ochre dado, wooden shutters, iron window grilles",
        "back": "whitewashed lime plaster wall of a Spanish colonial house, ochre dado, wooden shutters",
        "side": "whitewashed lime plaster wall of a Spanish colonial house, ochre dado",
        "gable": "whitewashed lime plaster wall",
        "wing_long": "whitewashed lime plaster wall, ochre dado, small windows",
        "wing_short": "whitewashed lime plaster wall, ochre dado, small windows",
        "roof": "terracotta Spanish clay barrel roof tiles in rows",
        "shed": "terracotta Spanish clay barrel roof tiles in rows",
        "plinth": "ochre rough stone base",
        "arcade": "whitewashed plaster arcade",
        "bell": "whitewashed plaster bell gable with two bronze bells",
    },
    "TIMBER": {
        "front_u": "European half-timbered wall, dark oak beams over cream plaster infill, leaded windows",
        "back_u": "European half-timbered wall, dark oak beams over cream plaster infill, leaded windows",
        "side_u": "European half-timbered wall, dark oak beams over cream plaster infill",
        "gable": "European half-timbered gable, dark oak beams over cream plaster infill",
        "dormer": "half-timbered dormer with a small leaded window",
        "roof": "red clay plain roof tiles in rows",
        "plinth": "grey rubble stone base",
        "brick": "old red brick",
    },
}
GROUND = {"STONE": "grey rubble stone wall with small windows and a plank door",
          "BRICK": "old red brick wall with small windows and a plank door",
          "TIMBER": "European half-timbered wall, dark oak beams over cream plaster infill"}


def material_of(region, params):
    """The prompt material of a region, or None (not repainted)."""
    style = str(getattr(params, "style", "NEOCLASSICAL")).upper()
    if style == "TIMBER" and region in ("front_g", "back_g", "side_g"):
        return GROUND.get(str(getattr(params, "ground_floor", "STONE")).upper())
    return MATERIALS.get(style, {}).get(region)


def prompt_for(material, extra=""):
    text = STYLE_TEXT.format(material)
    return f"{text}, {extra}" if extra else text


# --------------------------------------------------------------------------------------------------
# Resampling without wrapping (an atlas region is not tileable)

def _weights(n_in, n_out):
    m = np.zeros((n_out, n_in), np.float64)
    scale = n_in / n_out
    if n_out <= n_in:                       # area average
        for i in range(n_out):
            a, b = i * scale, (i + 1) * scale
            j = int(np.floor(a))
            while j < b and j < n_in:
                m[i, j] += min(b, j + 1) - max(a, j)
                j += 1
            m[i] /= m[i].sum()
    else:                                   # linear, edges clamped
        for i in range(n_out):
            x = min(max((i + 0.5) * scale - 0.5, 0.0), n_in - 1.0)
            j = int(np.floor(x))
            t = x - j
            m[i, j] += 1 - t
            m[i, min(j + 1, n_in - 1)] += t
    return m


def resize(img, h, w):
    """An H x W x C image resized to h x w (float32)."""
    a = img.astype(np.float64)
    a = np.einsum("ij,jkc->ikc", _weights(a.shape[0], h), a)
    a = np.einsum("ij,kjc->kic", _weights(a.shape[1], w), a)
    return a.astype(np.float32)


# --------------------------------------------------------------------------------------------------

def region_rect(model, texture, name):
    """(x0, y0, x1, y1) of a region in the texture's pixels."""
    r = model.atlas[name]
    k = model.atlas.size / texture.shape[1]
    return (int(round(r.x / k)), int(round(r.y / k)), int(round((r.x + r.w) / k)), int(round((r.y + r.h) / k)))


def tiles(w, h):
    """Overlapping tiles (x0, y0, x1, y1) covering a w x h image, each at most TILE_ASPECT long."""
    if w >= h:
        n_long, n_short, long_ = w, h, "x"
    else:
        n_long, n_short, long_ = h, w, "y"
    t = int(min(n_long, TILE_ASPECT * n_short))
    if t >= n_long:
        return [(0, 0, w, h)]
    step = max(1, int(t * (1 - OVERLAP)))
    starts = list(range(0, n_long - t, step)) + [n_long - t]
    out = []
    for s in starts:
        out.append((s, 0, s + t, h) if long_ == "x" else (0, s, w, s + t))
    return out


def _sd_size(w, h):
    s = SD_LONG / max(w, h)
    return max(64, int(round(h * s / 64)) * 64), max(64, int(round(w * s / 64)) * 64)


def _feather(w, h, tile, full_w, full_h):
    """Weights of a tile inside its region: ramps where it overlaps a neighbour."""
    x0, y0, x1, y1 = tile
    wx = np.ones(x1 - x0, np.float32)
    wy = np.ones(y1 - y0, np.float32)
    ramp = max(1, int(OVERLAP * max(x1 - x0, y1 - y0)))
    if x0 > 0:
        wx[:ramp] = np.linspace(0.02, 1, ramp)
    if x1 < full_w:
        wx[-ramp:] = np.minimum(wx[-ramp:], np.linspace(1, 0.02, ramp))
    if y0 > 0:
        wy[:ramp] = np.linspace(0.02, 1, ramp)
    if y1 < full_h:
        wy[-ramp:] = np.minimum(wy[-ramp:], np.linspace(1, 0.02, ramp))
    return wy[:, None] * wx[None, :]


def repaint_region(rgb, client, *, prompt, negative=NEGATIVE, strength, seed, name="region",
                   workflow_args=None):
    """A repainted copy of an RGB region (H x W x 3 uint8), same size, mean colour kept."""
    h, w = rgb.shape[:2]
    m = MARGIN
    padded = np.pad(rgb, ((m, m), (m, m), (0, 0)), mode="edge")
    ph, pw = padded.shape[:2]
    acc = np.zeros((ph, pw, 3), np.float32)
    wsum = np.zeros((ph, pw, 1), np.float32)
    for i, (x0, y0, x1, y1) in enumerate(tiles(pw, ph)):
        part = padded[y0:y1, x0:x1]
        sh, sw = _sd_size(x1 - x0, y1 - y0)
        up = np.clip(resize(part, sh, sw) + 0.5, 0, 255).astype(np.uint8)
        stored = client.upload(encode_png(up), f"aoe3bt_{name}_{i}.png")
        wf = comfy.repaint_workflow(stored, prompt=prompt, negative=negative, denoise=strength,
                                    seed=seed + i, **(workflow_args or {}))
        out = read_png(client.run(wf))[:, :, :3]
        back = resize(out, y1 - y0, x1 - x0)
        fw = _feather(pw, ph, (x0, y0, x1, y1), pw, ph)[:, :, None]
        acc[y0:y1, x0:x1] += back * fw
        wsum[y0:y1, x0:x1] += fw
    res = (acc / np.maximum(wsum, 1e-6))[m:m + h, m:m + w]
    res += rgb.reshape(-1, 3).mean(axis=0) - res.reshape(-1, 3).mean(axis=0)     # keep the palette
    return np.clip(res + 0.5, 0, 255).astype(np.uint8)


def repaint(texture, model, client, *, strength=0.45, seed=1, regions=None, extra="", blend=1.0,
            on_progress=None, workflow_args=None, guard=True):
    """(new texture, report): every region with a prompt repainted (or only `regions`), the alpha
    and the pixels under the player colour kept, blended with the original by `blend`.

    guard: a region whose edges moved (`edge_shift` not (0, 0): SDXL redrew a window or the tile
    rows) is repainted again at GUARD_FACTOR of the strength, and kept as it was if they still
    move; the report says which."""
    tex = np.asarray(texture)
    if tex.shape[2] == 3:
        tex = np.concatenate([tex, np.full(tex.shape[:2] + (1,), 255, np.uint8)], axis=2)
    out = tex.copy()
    p = model.params
    todo = [n for n in model.atlas.regions if (regions is None or n in regions)]
    report = []
    for idx, name in enumerate(todo):
        material = material_of(name, p)
        x0, y0, x1, y1 = region_rect(model, tex, name)
        w, h = x1 - x0, y1 - y0
        if material is None:
            report.append({"region": name, "skipped": "no prompt for it"})
            continue
        if min(w, h) < MIN_SIDE:
            report.append({"region": name, "skipped": f"thinner than {MIN_SIDE} px ({w} x {h})"})
            continue
        t0 = time.time()
        if on_progress:
            on_progress(idx, len(todo), name)
        src = tex[y0:y1, x0:x1, :3]
        used, note = strength, None
        new = repaint_region(src, client, prompt=prompt_for(material, extra), strength=used,
                             seed=seed + 101 * idx, name=name, workflow_args=workflow_args)
        if guard and edge_shift(src, new) != (0, 0):
            used = round(strength * GUARD_FACTOR, 3)
            new = repaint_region(src, client, prompt=prompt_for(material, extra), strength=used,
                                 seed=seed + 101 * idx, name=name, workflow_args=workflow_args)
            note = f"edges moved: repainted at {used}"
            if edge_shift(src, new) != (0, 0):
                report.append({"region": name, "skipped": "edges moved even at a lower strength: kept",
                               "seconds": round(time.time() - t0, 1)})
                continue
        mix = (src.astype(np.float32) * (1 - blend) + new.astype(np.float32) * blend + 0.5).astype(np.uint8)
        keep = tex[y0:y1, x0:x1, 3] < 255                         # the player colour's pixels
        mix[keep] = src[keep]
        out[y0:y1, x0:x1, :3] = mix
        entry = {"region": name, "size": (w, h), "tiles": len(tiles(w + 2 * MARGIN, h + 2 * MARGIN)),
                 "strength": used, "seconds": round(time.time() - t0, 1)}
        if note:
            entry["note"] = note
        report.append(entry)
    return out, report


def edge_shift(a, b, max_shift=3):
    """The (dx, dy) that best lines up the edges of image b with those of a (0, 0: nothing
    moved), from the gradient magnitude of their luminance."""
    def edges(img):
        lum = img[:, :, :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
        gx = np.abs(np.diff(lum, axis=1, prepend=lum[:, :1]))
        gy = np.abs(np.diff(lum, axis=0, prepend=lum[:1]))
        g = gx + gy
        return (g > np.percentile(g, 90)).astype(np.float32)
    ea, eb = edges(a), edges(b)
    m = max_shift
    best = None
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            s = (ea[m:-m, m:-m] * eb[m + dy:eb.shape[0] - m + dy, m + dx:eb.shape[1] - m + dx]).sum()
            if best is None or s > best[0]:
                best = (s, dx, dy)
    return best[1], best[2]
