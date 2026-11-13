# SPDX-License-Identifier: GPL-3.0-or-later
"""The texture maker: a seamless, tileable texture from a photograph or from a written prompt.

core/airepaint.py repaints a model's own atlas and must never move an edge. This is the other
job: a small square of material - stone, planks, corrugated iron, thatch - that repeats without a
join, for the painter to lay under its drawing (core/materials.py) or for anyone to use in their
own model.

    make(crop, prompt="rusted corrugated iron roof", client=client)   # from a photograph
    make(prompt="dry golden grass thatch", client=client)             # from the words alone
    make(crop)                                                        # no ComfyUI, no GPU

Four steps, each on its own below so each can be read and tested:

1. an image: the photograph, or img2img on it, or the prompt alone (comfy.texture_workflow);
2. tile it: wrap_blend rolls the image by half, so its borders are two rows that were neighbours
   and it repeats with no step at all; the old border lands in the middle, where the band across
   it is blended with its own mirror and the two sides meet exactly. It costs a ghost in the
   middle;
3. hide the ghost (heal, only with ComfyUI): the texture is repainted and only the cross through
   the middle is kept. The borders are never touched, so the tiling survives whatever the AI
   does;
4. de-light and shrink: the broad light and shade divided out (a photograph carries the light of
   the day it was taken), then resampled to the swatch size with wrapping.

seam() measures what is left: the step across the join over the image's own mean step. Pure
Python with numpy.
"""
import time

import numpy as np

from . import airepaint, comfy, materials
from .pngio import read_png

SIZE = 256              # the swatch size the painter and the add-on's zip budget expect
GEN = 1024              # SDXL's size: the texture is made large and shrunk
BAND = 0.18             # of the side, cross-faded at each border to make it tile
SEAM_OK = 1.5           # a join this many times an ordinary step still reads as a line
HEAL_STRENGTH = 0.55    # the denoise of the pass that hides the blend: high, because what it has
HEAL_CONTROL = 0.0      # to redraw is a mirrored band, and the ControlNet would lock that mirror
TRIGGER = "aoe3bt"      # the word tools/lora_dataset.py captions every picture with

# The words follow what the mod's own textures show (docs/art-findings.md): a photographic
# material, softened, in muted earth colours, evenly lit, half as grainy as the original game's.
# "rich detail" and "painterly brush strokes" pulled the other way and are gone.
STYLE_TEXT = ("seamless tileable texture of {}, flat top-down orthographic view, even soft "
              "lighting, no shadows, no perspective, uniform material, soft low-contrast surface, "
              "muted natural colours, texture for a real-time strategy game")
NEGATIVE = ("photograph of a scene, perspective, horizon, sky, cast shadows, dark shadows, "
            "vignette, lighting gradient, border, frame, people, objects, text, letters, "
            "watermark, signature, oversaturated, vivid colours, high contrast, harsh detail")


def prompt_for(material, extra=""):
    text = STYLE_TEXT.format(material)
    return f"{text}, {extra}" if extra else text


def seam(img):
    """How much the join shows when the texture is laid beside itself: the mean step across the
    wrap over the image's own mean step between neighbours. 1.0 is a join as ordinary as any
    other pair of pixels; above SEAM_OK it reads as a line."""
    a = np.asarray(img)[:, :, :3].astype(np.float32)
    inner = (np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean()) / 2
    across = (np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean()) / 2
    return float(across / max(inner, 1e-6))


def delight(rgb):
    """The colour map without its baked light and shade: divided by itself seen at 4 x 4, which
    is the broad variation, and brought back to its own mean colour. The step
    tools/fetch_materials.py applies to a downloaded photograph."""
    a = np.asarray(rgb)[:, :, :3].astype(np.float32)
    broad = materials.resample(materials.resample(a, 4), a.shape[0])
    flat = a / np.maximum(broad, 1.0) * a.reshape(-1, 3).mean(axis=0)
    return np.clip(flat + 0.5, 0, 255).astype(np.uint8)


def wrap_blend(rgb, band=BAND):
    """A tileable copy, by construction: the image is rolled by half, so its borders become two
    rows (and columns) that were neighbours in the original and it already repeats without a
    step. The old border lands in the middle as a cross, and that join is closed by blending the
    band across it with its own mirror: both sides of the middle then hold the same mix, so they
    meet exactly. What it leaves is a ghost in the middle, never at the border, and `heal`
    redraws that ghost. `band` is a fraction of the side."""
    a = np.asarray(rgb)[:, :, :3].astype(np.float32)
    h, w = a.shape[:2]
    a = np.roll(np.roll(a, h // 2, 0), w // 2, 1)
    for axis in (0, 1):
        a = np.swapaxes(a, 0, axis)
        n = a.shape[0]
        b = max(1, int(round(band * n / 2)))
        lo, hi = max(0, n // 2 - b), min(n, n // 2 + b)
        strip = a[lo:hi].copy()
        t = np.linspace(1.0, 0.0, hi - lo, dtype=np.float32)[:, None, None]
        a[lo:hi] = strip * t + strip[::-1] * (1 - t)
        a = np.swapaxes(a, 0, axis)
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def _cross_mask(h, w, band):
    """1 on the cross through the middle, falling to 0 over `band` pixels, and held to 0 along
    every border: what a healing pass is allowed to change. The borders carry the tiling, so they
    are never touched - which leaves the two ends of each arm of the cross unhealed, a band's
    length of the blend near the border."""
    def ramp(n):
        d = np.abs(np.arange(n) - (n - 1) / 2.0)
        return np.clip(1.0 - d / max(band, 1), 0.0, 1.0)

    def window(n):
        i = np.arange(n)
        return np.clip(np.minimum(i, n - 1 - i) / max(band, 1), 0.0, 1.0)
    cross = np.maximum(ramp(h)[:, None], ramp(w)[None, :])
    edge = np.minimum(window(h)[:, None], window(w)[None, :])
    return (cross * edge).astype(np.float32)[:, :, None]


def heal(rgb, client, *, prompt, negative=NEGATIVE, strength=HEAL_STRENGTH, seed=1,
         band=BAND, name="texture", workflow_args=None):
    """Redraws the mirrored band wrap_blend leaves in the middle, without touching the borders:
    the whole texture is repainted and only the cross through the middle is kept. The borders
    come through untouched, so the result tiles exactly as the input did, whatever the AI drew."""
    a = np.asarray(rgb)[:, :, :3]
    h, w = a.shape[:2]
    args = {"control_strength": HEAL_CONTROL}
    args.update(workflow_args or {})
    new = airepaint.repaint_region(a, client, prompt=prompt, negative=negative,
                                   strength=strength, seed=seed, name=name, workflow_args=args)
    m = _cross_mask(h, w, max(2, int(round(band * min(h, w)))))
    mix = a.astype(np.float32) * (1 - m) + new.astype(np.float32) * m
    return np.clip(mix + 0.5, 0, 255).astype(np.uint8)


def crop(rgb, centre=(0.5, 0.5), part=1.0):
    """The square part of a picture a texture is made from: `part` of its shorter side, around
    `centre` (0..1 of the width and of the height, the top row first). The default is the whole
    middle square - "the roof of this factory" is a smaller part somewhere else."""
    a = np.asarray(rgb)[:, :, :3]
    h, w = a.shape[:2]
    n = max(8, int(round(min(h, w) * min(max(part, 0.02), 1.0))))
    cx = int(round(min(max(centre[0], 0.0), 1.0) * w))
    cy = int(round(min(max(centre[1], 0.0), 1.0) * h))
    x0 = min(max(cx - n // 2, 0), w - n)
    y0 = min(max(cy - n // 2, 0), h - n)
    return np.ascontiguousarray(a[y0:y0 + n, x0:x0 + n])


def square(rgb, side):
    """The image as a `side` x `side` RGB array: the long way cropped to the middle first, so
    nothing is squashed."""
    a = np.asarray(rgb)[:, :, :3]
    h, w = a.shape[:2]
    n = min(h, w)
    a = a[(h - n) // 2:(h - n) // 2 + n, (w - n) // 2:(w - n) // 2 + n]
    if n == side:
        return np.ascontiguousarray(a)
    return np.clip(airepaint.resize(a, side, side) + 0.5, 0, 255).astype(np.uint8)


def make(source=None, *, prompt="", client=None, size=SIZE, gen=GEN, seed=1, strength=0.6,
         extra="", light=True, heal_band=True, band=BAND, on_progress=None, workflow_args=None,
         material="", category="buildings", fit=False, profile=None, lora=None,
         lora_strength=0.8, trigger=TRIGGER):
    """(texture, report): a seamless `size` x `size` RGB texture.

    source: an RGB array (a crop of a photograph), or None to work from the prompt alone (which
        then needs a client). With a client the crop is repainted at `strength`, so it leaves the
        light and the look of a photograph behind; without one it is used as it is.
    prompt: the material in your own words ("rusted corrugated iron roof"); it is wrapped in
        STYLE_TEXT, and `extra` is added to it.
    client: a comfy.Client, or None for the plain path: no ComfyUI, no GPU, no model.
    light: divide out the broad light and shade (leave it on for a photograph).
    heal_band: let the AI redraw the blended bands (step 3 above).
    material, category: what the texture is of ("wood", "stone", "roof"...) and what it is for
        ("buildings", "units", "nuggets"...): the mod's own textures of that kind are what it
        is measured against (`report["style"]`, see `distance`).
    lora: a LoRA of ComfyUI's models/loras to draw with (tools/train_lora.py makes one of the
        mod's own textures); its `trigger` word is put in front of the prompt.
    fit: bring its grain and saturation to the median of those textures (`match`). A generated
        texture usually needs it: Stable Diffusion paints far more saturated than a game does.

    The report says which steps ran, the seam before and after, how far the result is from the
    mod's own textures, and how long it took.
    """
    t0 = time.time()
    report = {"mode": None, "seed": int(seed), "prompt": prompt, "steps": []}

    def step(name):
        report["steps"].append(name)
        if on_progress:
            on_progress(name)

    has_prompt = bool(str(prompt).strip())
    if lora and client is not None:
        workflow_args = {**(workflow_args or {}), "lora": lora, "lora_strength": float(lora_strength)}
        extra = f"{extra}, {trigger}" if extra else trigger
        report["lora"] = lora
    if source is None:
        if client is None:
            raise ValueError("a prompt alone needs ComfyUI: give a reference image, or a client")
        if not has_prompt:
            raise ValueError("write a prompt, or give a reference image")
        step("drawing it from the prompt")
        wf = comfy.texture_workflow(prompt=prompt_for(prompt, extra), negative=NEGATIVE,
                                    seed=int(seed), width=gen, height=gen, **(workflow_args or {}))
        img = square(read_png(client.run(wf)), gen)
        report["mode"] = "prompt"
    else:
        img = square(source, gen)
        report["mode"] = "photo"
        if client is not None and has_prompt:
            step("repainting the reference")
            img = airepaint.repaint_region(img, client, prompt=prompt_for(prompt, extra),
                                           negative=NEGATIVE, strength=strength, seed=int(seed),
                                           name="texture", workflow_args=workflow_args)
            report["mode"] = "photo+ai"
    report["seam_before"] = round(seam(img), 2)
    step("making it tile")
    img = wrap_blend(img, band)
    if light:
        # after the tiling, not before: the broad light is measured by a resampler that wraps, and
        # on an image whose two sides do not meet it reads the step as light and leaves it in
        step("taking the light out")
        img = delight(img)
    if client is not None and heal_band and has_prompt:
        step("hiding the blend")
        healed = heal(img, client, prompt=prompt_for(prompt, extra), seed=int(seed) + 7, band=band,
                      workflow_args=workflow_args)
        if seam(healed) <= max(SEAM_OK, seam(img) * 1.05):
            img = healed
        else:
            report["note"] = "the healing pass left a worse join: kept the blended one"
    step("down to the swatch size")
    out = np.clip(materials.resample(img.astype(np.float32), size) + 0.5, 0, 255).astype(np.uint8)
    group, what, before = style(out, material, category, profile)
    if group is not None:
        report["style"] = {"against": what, "textures": group["count"], **before}
        if fit:
            step("fitting it to the mod's own textures")
            out = match(out, group)
            report["style"] = {"against": what, "textures": group["count"], "before_fit": before["off"],
                               **distance(out, group)}
    report["seam"] = round(seam(out), 2)
    report["size"] = int(size)
    report["seconds"] = round(time.time() - t0, 1)
    if report["seam"] > SEAM_OK:
        report["note"] = f"the join still shows ({report['seam']}): try another seed or a wider band"
    return out, report


def sheet(rgb, times=3):
    """The texture repeated `times` by `times`: what a tiled wall looks like, to judge the join
    and any landmark that repeats."""
    a = np.asarray(rgb)[:, :, :3]
    return np.tile(a, (times, times, 1))


# --------------------------------------------------------------------------------------------------
# How close to the mod's own textures (profiles/textures.json, written by tools/texture_survey.py)

LUM = np.array([0.299, 0.587, 0.114], np.float32)
MEASURES = ("grain", "saturation", "luminance")


def _half(a):
    """Mip level 1: the survey measures every texture at half size, so a swatch is too."""
    h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
    if h < 2 or w < 2:
        return a
    return a[:h, :w].reshape(h // 2, 2, w // 2, 2, -1).mean((1, 3))


def measures(rgb):
    """grain, saturation and luminance of a texture, exactly as tools/texture_survey.py takes
    them: at half size, the grain the spread of the luminance minus its 9 x 9 blur over its
    mean, the other two the medians."""
    a = _half(np.asarray(rgb)[:, :, :3].astype(np.float32))
    lum = a @ LUM
    fine = lum - materials._blur(lum, 4)
    mx, mn = a.max(2), a.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    return {"grain": float(fine.std()) / max(float(lum.mean()), 1.0),
            "saturation": float(np.median(sat)), "luminance": float(np.median(lum))}


def distance(rgb, group):
    """How far a texture is from a group of the mod's textures (an entry of the texture profile):
    per measure, its distance from the group's median in widths of the group's middle half (0 at
    the median, 0.5 at a quartile, beyond 1 well outside what the mod does), signed; and `off`,
    the largest of them."""
    m = measures(rgb)
    out = {}
    for k in MEASURES:
        q25, q50, q75 = group[k]
        out[k] = round((m[k] - q50) / max(q75 - q25, 1e-6), 2)
    out["off"] = max(abs(out[k]) for k in MEASURES)
    out["measured"] = {k: round(m[k], 4) for k in MEASURES}
    return out


def match(rgb, group, grain=True, saturation=True, rounds=3):
    """The texture brought to the group's median grain and saturation: its fine detail scaled
    (never its broad shapes, never its mean colour) and its colour pushed toward or away from
    grey. Every step is per pixel or a blur that wraps, so a texture that tiles still does."""
    a = np.asarray(rgb)[:, :, :3].astype(np.float32)
    for _ in range(rounds if grain else 0):
        now = measures(a)["grain"]
        if now < 1e-4:
            break
        k = min(max(group["grain"][1] / now, 0.25), 4.0)
        if abs(k - 1) < 0.03:
            break
        lum = a @ LUM
        fine = lum - materials._blur(lum, 8)             # 9 x 9 at half size is 17 x 17 here
        a = np.clip(a + (k - 1) * fine[:, :, None], 0, 255)
    for _ in range(rounds if saturation else 0):          # clipping makes one pass fall short
        now = measures(a)["saturation"]
        if now < 1e-3:
            break
        k = min(max(group["saturation"][1] / now, 0.5), 2.0)
        if abs(k - 1) < 0.03:
            break
        lum = (a @ LUM)[:, :, None]
        a = np.clip(lum + (a - lum) * k, 0, 255)
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def style(rgb, material="", category="buildings", profile=None):
    """(group, what it is, distance) of a texture against the mod's own textures of its material
    and category - or (None, None, None) without a texture profile."""
    if profile is None:
        from . import profile as profiles
        profile = profiles.art("textures")
    if profile is None:
        return None, None, None
    group, what = profile.nearest(category, "diffuse", material or None)
    if group is None:
        return None, None, None
    return group, what, distance(rgb, group)
