# SPDX-License-Identifier: GPL-3.0-or-later
"""Recolours textures (.ddt) in a perceptual colour space, and measures how far they are from given
colours (player colours) before and after.

    venv\\Scripts\\python -I tools/recolor_textures.py <file.ddt or folder> [...] --out <folder>
        [--hue DEG] [--chroma F] [--lightness F] [--hue-window CENTRE,HALF[,FEATHER]]
        [--mix <mix.xml>] [--player-colors <playercolors.xml or .xmb>] [--against NAME=R,G,B ...]
        [--mapcolor R,G,B] [--near DE] [--report <file.json>] [--preview <file.png>] [--dry-run]

The transform works in OKLCH (Björn Ottosson's OKLab, in polar form) on every pixel:

    hue        h + DEG             (--hue, degrees; from red, + goes towards orange and yellow,
                                    - towards crimson, magenta and purple)
    chroma     C x F               (--chroma; 0.6 = 40 % less saturated)
    lightness  L x F               (--lightness; 0.8 = darker)

`--hue-window CENTRE,HALF[,FEATHER]` limits it to the pixels whose hue lies within HALF degrees of
CENTRE, fading out over FEATHER more degrees (default 20): a red marsh can change while its brown
soil and yellow stems stay as they are. A colour the change takes out of sRGB keeps its lightness
and hue and loses chroma until it fits.

What it writes. Each texture keeps its header byte for byte (usage, alpha mode, format, size, mip
count, level offsets): every stored mip level is decoded, recoloured and encoded again in its own
format, so the mip chain is the original's own (same levels, same filtering), and in DXT3/DXT5 the
alpha blocks are copied unchanged. BGRA keeps its alpha bytes exactly. Bump maps (usage bit 4, or a
name ending in _b, _bump or _n) are left untouched and listed as skipped. DXT1 with cut-out alpha
and grey textures are refused. Files go to --out under their own names; a folder given as input is
read without its subfolders. The output folder may not be an input folder, nor a Steam library.

What it measures (printed, and in --report as JSON). For each texture before and after: its mean
colour (sRGB, over the top level, alpha above 128 only) and CIEDE2000 between that mean and each
colour named by --against or read from --player-colors (their color1, the colour units wear), and
the share of its pixels within --near (default 20) CIEDE2000 of each one (--against may be repeated, or
take several NAME=R,G,B separated by semicolons). With --mix, the mean of
the textures that mix file paints, weighted as it weights them (matched by file name), and the
same distances. --mapcolor takes the minimap colour of the terrain (terraintypes.xml): it is
recoloured the same way, and both are compared with the players' minimap colours.

Without a transform option it only measures (no --out needed). --dry-run measures the result
without writing any texture. --preview writes a PNG of each texture before and after, side by side.
"""
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np  # noqa: E402

from aoe3game import ddt  # noqa: E402
from aoe3game.deploy import RefusedPath, refuse_steam  # noqa: E402

BUMP_NAMES = re.compile(r"(_b|_bump|_n|_normal)$", re.I)


# --------------------------------------------------------------------------------------------------
# Colour spaces

def srgb_to_linear(c):
    c = np.asarray(c, np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    return 255.0 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M2_INV = np.linalg.inv(_M2)
_M1_INV = np.linalg.inv(_M1)


def linear_to_oklab(rgb):
    lms = np.cbrt(rgb @ _M1.T)
    return lms @ _M2.T


def oklab_to_linear(lab):
    lms = lab @ _M2_INV.T
    return (lms ** 3) @ _M1_INV.T


def srgb_to_oklch(rgb):
    lab = linear_to_oklab(srgb_to_linear(rgb))
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    return np.stack([lab[..., 0], c, h], axis=-1)


def oklch_to_linear(lch):
    h = np.radians(lch[..., 2])
    lab = np.stack([lch[..., 0], lch[..., 1] * np.cos(h), lch[..., 1] * np.sin(h)], axis=-1)
    return oklab_to_linear(lab)


def oklch_to_srgb(lch):
    """sRGB 0-255 floats; a colour outside sRGB keeps its L and h and loses chroma until it fits."""
    lch = np.array(lch, np.float64)
    lin = oklch_to_linear(lch)
    out = np.any((lin < -1e-6) | (lin > 1 + 1e-6), axis=-1)
    if out.any():
        sub = lch[out]
        lo, hi = np.zeros(len(sub)), np.ones(len(sub))
        for _ in range(20):
            mid = (lo + hi) / 2
            trial = sub.copy()
            trial[:, 1] *= mid
            t = oklch_to_linear(trial)
            ok = np.all((t >= -1e-6) & (t <= 1 + 1e-6), axis=-1)
            lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
        sub[:, 1] *= lo
        lin[out] = oklch_to_linear(sub)
    return linear_to_srgb(lin)


_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                 [0.2126729, 0.7151522, 0.0721750],
                 [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(rgb):
    """CIE L*a*b* (D65) of sRGB 0-255 values."""
    xyz = srgb_to_linear(rgb) @ _XYZ.T / _WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def ciede2000(lab1, lab2):
    """CIEDE2000 between two arrays of CIE Lab colours (broadcast), kL = kC = kH = 1."""
    lab1, lab2 = np.asarray(lab1, np.float64), np.asarray(lab2, np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    hsum = h1p + h2p
    hpm = np.where(np.abs(h1p - h2p) > 180, np.where(hsum < 360, hsum + 360, hsum - 360), hsum) / 2
    hpm = np.where(C1p * C2p == 0, hsum, hpm)
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    d_theta = 30 * np.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -np.sin(np.radians(2 * d_theta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(rgb1, rgb2):
    return ciede2000(srgb_to_lab(rgb1), srgb_to_lab(rgb2))


# --------------------------------------------------------------------------------------------------
# The transform

class Transform:
    def __init__(self, hue=0.0, chroma=1.0, lightness=1.0, window=None):
        self.hue, self.chroma, self.lightness = float(hue), float(chroma), float(lightness)
        self.window = window            # (centre, half, feather) in degrees, or None

    def identity(self):
        return self.hue == 0 and self.chroma == 1 and self.lightness == 1

    def weight(self, h):
        if not self.window:
            return np.ones_like(h)
        centre, half, feather = self.window
        d = np.abs((h - centre + 180) % 360 - 180)
        if feather <= 0:
            return (d <= half).astype(np.float64)
        t = np.clip((d - half) / feather, 0, 1)
        return 0.5 + 0.5 * np.cos(np.pi * t)

    def apply(self, rgb):
        """N x 3 (or any ... x 3) sRGB 0-255 values in, recoloured uint8 out."""
        rgb = np.asarray(rgb)
        shape = rgb.shape
        lch = srgb_to_oklch(rgb.reshape(-1, 3).astype(np.float64))
        w = self.weight(lch[:, 2])
        lch[:, 0] *= 1 + w * (self.lightness - 1)
        lch[:, 1] *= 1 + w * (self.chroma - 1)
        lch[:, 2] = (lch[:, 2] + w * self.hue) % 360
        out = oklch_to_srgb(lch)
        return np.clip(np.rint(out), 0, 255).astype(np.uint8).reshape(shape)

    def describe(self):
        text = f"hue {self.hue:+g} deg, chroma x{self.chroma:g}, lightness x{self.lightness:g}"
        if self.window:
            text += " on hues {:g} +/- {:g} (feather {:g})".format(*self.window)
        return text


# --------------------------------------------------------------------------------------------------
# Textures

def is_bump(path, header):
    return bool(header.usage & 4) or bool(BUMP_NAMES.search(os.path.splitext(os.path.basename(path))[0]))


def level_size(header, level):
    return max(1, header.width >> level), max(1, header.height >> level)


def recolor_ddt(data, transform):
    """The texture's bytes with every stored level recoloured; the header and the layout are kept."""
    hd = ddt.read_header(data)
    if hd.format not in (ddt.BGRA, ddt.DXT1, ddt.DXT3, ddt.DXT5):
        raise ddt.DdtError(f"format {ddt.FORMATS.get(hd.format, hd.format)} is not recoloured")
    if len(hd.levels) != hd.mips:
        raise ddt.DdtError("the level table is cut short")
    out = bytearray(data)
    for level, (off, size) in enumerate(hd.levels):
        px = ddt.decode(data, level)
        w, h = level_size(hd, level)
        if hd.format == ddt.DXT1 and (px[..., 3] < 255).any():
            raise ddt.DdtError("DXT1 with cut-out alpha is not recoloured")
        new = px.copy()
        new[..., :3] = transform.apply(px[..., :3])
        if hd.format == ddt.BGRA:
            raw = np.frombuffer(data, np.uint8, w * h * 4, off).reshape(h, w, 4).copy()
            raw[..., 0], raw[..., 1], raw[..., 2] = new[..., 2], new[..., 1], new[..., 0]
            blob = raw.tobytes()
        elif hd.format == ddt.DXT1:
            blob = ddt.compress(new, ddt.DXT1)
        else:
            colour = np.frombuffer(ddt.compress(new, ddt.DXT1), np.uint8).reshape(-1, 8)
            old = np.frombuffer(data, np.uint8, len(colour) * 16, off).reshape(-1, 16).copy()
            old[:, 8:] = colour                      # the alpha half of each block is kept as it was
            blob = old.tobytes()
        if len(blob) > size:
            raise ddt.DdtError(f"level {level}: {len(blob)} bytes do not fit the stored {size}")
        out[off:off + len(blob)] = blob
    return bytes(out)


def top_pixels(data):
    """The top level's RGB pixels that show (alpha above 128), N x 3 uint8."""
    px = ddt.decode(data, 0)
    shown = px[..., 3] > 128
    if shown.sum() < 16:
        shown = np.ones_like(shown)
    return px[..., :3][shown]


# --------------------------------------------------------------------------------------------------
# References: player colours, the mix

def parse_rgb(text):
    parts = [p for p in re.split(r"[ ,;]+", text.strip()) if p]
    if len(parts) != 3:
        raise ValueError(f"{text!r}: expected R,G,B")
    rgb = tuple(int(p) for p in parts)
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError(f"{text!r}: each value goes from 0 to 255")
    return rgb


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def read_xml_or_xmb(path):
    raw = read_bytes(path)
    if raw[:4] == b"l33t" or raw[:2] == b"X1":
        import xmbedit
        elems, attrs, root = xmbedit.parse(xmbedit.decode(raw))
        raw = xmbedit.to_xml(elems, attrs, root).encode("utf-8")
    text = raw.decode("utf-8-sig", errors="replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return ET.fromstring(text)


def read_player_colors(path, players=range(1, 9)):
    """{'player N': (unit colour, minimap colour)} from playercolors.xml (or its .xmb)."""
    root = read_xml_or_xmb(path)
    found = {}
    for el in root.iter():
        if el.tag.lower() != "player":
            continue
        num = int(el.get("num", "-1"))
        if num in players:
            found[f"player {num}"] = (parse_rgb(el.get("color1")), parse_rgb(el.get("minimap") or el.get("color1")))
    return dict(sorted(found.items(), key=lambda kv: int(kv[0].split()[1])))


def read_mix(path):
    """{texture file name (lower case, no extension): weight} of a terrain mix file."""
    root = read_xml_or_xmb(path)
    weights = {}
    for el in root.iter():
        if el.tag.lower() == "texture" and el.text:
            name = el.text.strip().replace("/", "\\").split("\\")[-1].lower()
            weights[name] = weights.get(name, 0.0) + float(el.get("weight", "1"))
    return weights


# --------------------------------------------------------------------------------------------------
# Measuring

def measure(pixels, refs, near):
    """Mean colour, CIEDE2000 from it to each reference, and the share of pixels near each one."""
    pixels = np.asarray(pixels).reshape(-1, 3)
    mean = pixels.astype(np.float64).mean(axis=0)
    lab_mean = srgb_to_lab(mean)
    sample = pixels
    if len(sample) > 65536:              # a fixed, even sample keeps the shares exact enough and fast
        sample = sample[np.linspace(0, len(sample) - 1, 65536).astype(np.int64)]
    lab_px = srgb_to_lab(sample.astype(np.float64))
    result = {"mean": [round(float(c), 1) for c in mean], "delta_e": {}, "near": {}}
    for name, rgb in refs.items():
        lab_ref = srgb_to_lab(np.array(rgb, np.float64))
        result["delta_e"][name] = round(float(ciede2000(lab_mean, lab_ref)), 2)
        result["near"][name] = round(float((ciede2000(lab_px, lab_ref) < near).mean()), 4)
    return result


def median_others(delta, focus):
    others = [v for k, v in delta.items() if k != focus]
    return float(np.median(others)) if others else None


def collect_inputs(items):
    files = []
    for item in items:
        if os.path.isdir(item):
            files += [os.path.join(item, n) for n in sorted(os.listdir(item)) if n.lower().endswith(".ddt")]
        elif os.path.isfile(item):
            files.append(item)
        else:
            raise FileNotFoundError(item)
    return files


def save_png(rgb, path):
    """An RGB uint8 array as a PNG file, with zlib only."""
    import zlib
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def preview_png(before, after, path):
    """Each texture before (left) and after (right), one row each."""
    rows = []
    for b, a in zip(before, after):
        b, a = b[..., :3], a[..., :3]
        h = max(b.shape[0], a.shape[0])
        pad = lambda x: np.pad(x, ((0, h - x.shape[0]), (0, 0), (0, 0)))   # noqa: E731
        rows.append(np.concatenate([pad(b), np.zeros((h, 8, 3), np.uint8), pad(a)], axis=1))
    width = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 8), (0, width - r.shape[1]), (0, 0))) for r in rows]
    save_png(np.ascontiguousarray(np.concatenate(rows, axis=0)), path)


# --------------------------------------------------------------------------------------------------

def option(argv, flag, default=None, many=False):
    values = []
    while flag in argv:
        i = argv.index(flag)
        if i + 1 >= len(argv):
            sys.exit(f"recolor_textures: {flag} needs a value")
        values.append(argv[i + 1])
        del argv[i:i + 2]
    if many:
        return values
    return values[-1] if values else default


def main(argv):
    argv = list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    out = option(argv, "--out")
    report_path = option(argv, "--report")
    preview = option(argv, "--preview")
    mix = option(argv, "--mix")
    colors = option(argv, "--player-colors")
    against = option(argv, "--against", many=True)
    mapcolor = option(argv, "--mapcolor")
    near = float(option(argv, "--near", "20"))
    window = option(argv, "--hue-window")
    try:
        transform = Transform(float(option(argv, "--hue", "0")), float(option(argv, "--chroma", "1")),
                              float(option(argv, "--lightness", "1")))
        if window:
            parts = [float(p) for p in window.split(",")]
            if len(parts) not in (2, 3):
                raise ValueError("--hue-window takes CENTRE,HALF[,FEATHER]")
            transform.window = (parts[0], parts[1], parts[2] if len(parts) == 3 else 20.0)
    except ValueError as exc:
        sys.exit(f"recolor_textures: {exc}")
    unknown = [a for a in argv if a.startswith("-")]
    if unknown:
        sys.exit(f"recolor_textures: unknown option {unknown[0]}")
    try:
        inputs = collect_inputs(argv)
    except FileNotFoundError as exc:
        sys.exit(f"recolor_textures: no such file or folder: {exc}")
    if not inputs:
        sys.exit("recolor_textures: no texture given")
    writes = not transform.identity() and not dry
    if writes and not out:
        sys.exit("recolor_textures: --out is needed to write the recoloured textures (or --dry-run)")
    try:
        for target in [p for p in (out, report_path, preview) if p]:
            refuse_steam(target)
    except RefusedPath as exc:
        sys.exit(f"recolor_textures: {exc}")
    if writes:
        in_dirs = {os.path.normcase(os.path.abspath(os.path.dirname(f))) for f in inputs}
        if os.path.normcase(os.path.abspath(out)) in in_dirs:
            sys.exit("recolor_textures: --out is an input folder: it would overwrite the originals")

    refs, minimap = {}, {}
    try:
        if colors:
            for name, (unit, mini) in read_player_colors(colors).items():
                refs[name], minimap[name] = unit, mini
        for item in [p.strip() for a in against for p in a.split(";") if p.strip()]:
            name, _, rgb = item.partition("=")
            refs[name.strip() if rgb else item] = parse_rgb(rgb or name)
        mapcolor_rgb = parse_rgb(mapcolor) if mapcolor else None
        weights = read_mix(mix) if mix else {}
    except (ValueError, OSError, ET.ParseError) as exc:
        sys.exit(f"recolor_textures: {exc}")

    report = {"transform": transform.describe(), "near": near, "references": refs, "textures": [],
              "skipped": []}
    before_px, after_px, previews = {}, {}, ([], [])
    if writes:
        os.makedirs(out, exist_ok=True)
    for path in inputs:
        name = os.path.basename(path)
        data = read_bytes(path)
        try:
            hd = ddt.read_header(data)
        except ddt.DdtError as exc:
            report["skipped"].append({"file": name, "why": str(exc)})
            continue
        if is_bump(path, hd):
            report["skipped"].append({"file": name, "why": "bump map: left untouched"})
            continue
        entry = {"file": name, "header": hd.describe()}
        try:
            new = data if transform.identity() else recolor_ddt(data, transform)
        except ddt.DdtError as exc:
            report["skipped"].append({"file": name, "why": str(exc)})
            continue
        stem = os.path.splitext(name)[0].lower()
        before_px[stem], after_px[stem] = top_pixels(data), top_pixels(new)
        entry["before"] = measure(before_px[stem], refs, near)
        if not transform.identity():
            entry["after"] = measure(after_px[stem], refs, near)
        if writes:
            with open(os.path.join(out, name), "wb") as fh:
                fh.write(new)
            entry["written"] = os.path.join(out, name)
        if preview:
            previews[0].append(ddt.decode(data, 0))
            previews[1].append(ddt.decode(new, 0))
        report["textures"].append(entry)

    if weights:
        used = {k: w for k, w in weights.items() if k in before_px}
        report["mix"] = {"weights": weights, "missing": sorted(set(weights) - set(used))}
        if used:
            for when, pix in (("before", before_px), ("after", after_px)):
                if when == "after" and transform.identity():
                    continue
                total = sum(used.values())
                mean = sum(pix[k].astype(np.float64).mean(axis=0) * w for k, w in used.items()) / total
                # the shares: each texture's pixels count as much as its weight
                near_share = {}
                for ref, rgb in refs.items():
                    lab_ref = srgb_to_lab(np.array(rgb, np.float64))
                    near_share[ref] = 0.0
                    for k, w in used.items():
                        sample = pix[k][::max(1, len(pix[k]) // 65536)]
                        near_share[ref] += w / total * float((ciede2000(srgb_to_lab(sample.astype(np.float64)),
                                                                        lab_ref) < near).mean())
                report["mix"][when] = {
                    "mean": [round(float(c), 1) for c in mean],
                    "delta_e": {r: round(float(delta_e(mean, rgb)), 2) for r, rgb in refs.items()},
                    "near": {r: round(v, 4) for r, v in near_share.items()}}
    if mapcolor_rgb:
        new_map = tuple(int(c) for c in transform.apply(np.array([mapcolor_rgb], np.uint8))[0])
        report["mapcolor"] = {"before": list(mapcolor_rgb), "after": list(new_map)}
        if minimap:
            report["mapcolor"]["delta_e_before"] = {r: round(float(delta_e(mapcolor_rgb, c)), 2)
                                                    for r, c in minimap.items()}
            report["mapcolor"]["delta_e_after"] = {r: round(float(delta_e(new_map, c)), 2)
                                                   for r, c in minimap.items()}
            report["minimap_colors"] = minimap

    print_summary(report)
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
    if preview and previews[0]:
        preview_png(previews[0], previews[1], preview)
    return 0


def print_summary(report):
    print(f"transform: {report['transform']}")
    refs = list(report["references"])

    def line(label, m):
        de = " ".join(f"{r}={m['delta_e'][r]:.1f}" for r in refs)
        return f"  {label:7s} mean {tuple(m['mean'])}  dE2000 {de}"
    for t in report["textures"]:
        print(f"{t['file']}: {t['header']}")
        print(line("before", t["before"]))
        if "after" in t:
            print(line("after", t["after"]))
    for s in report["skipped"]:
        print(f"{s['file']}: skipped: {s['why']}")
    mix = report.get("mix")
    if mix:
        if mix["missing"]:
            print(f"mix: no texture given for {', '.join(mix['missing'])}")
        for when in ("before", "after"):
            if when in mix:
                print("mix" + line(when, mix[when]))
                near = " ".join(f"{r}={100 * v:.1f}%" for r, v in mix[when]["near"].items())
                print(f"          pixels within dE {report['near']:g}: {near}")
    mc = report.get("mapcolor")
    if mc:
        print(f"minimap colour {tuple(mc['before'])} -> {tuple(mc['after'])}")
        for when in ("before", "after"):
            key = f"delta_e_{when}"
            if key in mc:
                print(f"  {when:7s} dE2000 to minimap colours "
                      + " ".join(f"{r}={v:.1f}" for r, v in mc[key].items()))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
