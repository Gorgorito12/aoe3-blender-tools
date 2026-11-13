# SPDX-License-Identifier: GPL-3.0-or-later
"""Paints the presets and says how far each texture is from the mod's own building textures (the
texture profile, docs/art-findings.md): grain, saturation and luminance, measured as the texture
survey measures them. Prints; writes nothing.

    venv\\Scripts\\python -I tools\\style_check.py [PRESET ...] [--materials] [--origin own|stock]
                                                 [--category buildings] [--size 1024]

The distance is from the group's median in widths of its middle half: 0 is the median, 0.5 a
quartile, beyond 1 well outside what the mod does.

    venv\\Scripts\\python -I tools\\style_check.py --fit [--style AFRICAN] [PRESET ...]

measures each **material role** apart: the grain of every region a role's swatch was laid on
(core/materials.py), against the mod's own building textures of that material, and prints the
fine grain band (core/materials.py) that brings each role's median region to the group's median. A whole texture
also holds drawn openings, frames and trims that carry no swatch, so its own grain stays lower
than any one surface's: the surfaces are what the fit aims at.
"""
import dataclasses
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building, materials, profile, texmaker  # noqa: E402
from core.painter import Painter  # noqa: E402
from core.styles import STYLES  # noqa: E402


# the material each role's swatch stands for, as the texture profile names materials
ROLE_MATERIAL = {"roof": "thatch", "stone": "stone", "timber": "wood", "cloth": "cloth"}
FIT_PRESETS = ("AFRICAN_HOUSE_SUBSAHARAN", "AFRICAN_HOUSE_SAHEL", "AFRICAN_TOWN_CENTER_SAHEL",
               "AFRICAN_MARKET_SUBSAHARAN", "AFRICAN_ARMORY_SAHEL", "AFRICAN_PALACE_SUBSAHARAN")
MIN_SIDE = 48          # a smaller region is mostly its border: its grain says little


def painted(params):
    """(rgb, region -> role) of a preset's texture, as the game export paints it."""
    pr = Painter(building.build(params))
    STYLES[pr.p.style].paint(pr, pr.model)
    rgb = pr.finish()[0]
    return np.asarray(rgb)[:, :, :3], dict(pr.roles)


def check(key, group, materials=None, size=1024):
    """(measures, distance) of one preset's painted texture against a profile group; `materials`
    None paints it as the preset does (the African presets lay swatches, the others do not)."""
    p = building.PRESETS[key]
    p = dataclasses.replace(p, materials=p.materials if materials is None else materials, texture_size=size)
    rgb = painted(p)[0]
    return texmaker.measures(rgb), texmaker.distance(rgb, group)


def role_grains(keys, grains=None, style="AFRICAN"):
    """{role: [grain of each region it covers]} over the presets `keys` (as they are, swatches on),
    with `grains` {role: fine band} put in place of the style's own for the run."""
    saved = materials.MATERIALS[style]
    if grains:
        materials.MATERIALS[style] = {r: e[:4] + ((grains[r],) if r in grains else e[4:5])
                                      for r, e in ((r, tuple(e) + (materials.TARGET_CONTRAST,) * (4 - len(e)))
                                                   for r, e in saved.items())}
    out = {}
    try:
        for key in keys:
            rgb, roles = painted(dataclasses.replace(building.PRESETS[key], materials=True))
            model_atlas = building.build(building.PRESETS[key]).atlas
            k = rgb.shape[0] / model_atlas.size
            for region, role in roles.items():
                r = model_atlas[region]
                if min(r.w, r.h) * k < MIN_SIDE:
                    continue
                crop = rgb[int(r.y * k):int((r.y + r.h) * k), int(r.x * k):int((r.x + r.w) * k)]
                out.setdefault(role, []).append(texmaker.measures(crop)["grain"])
    finally:
        materials.MATERIALS[style] = saved
    return out


def target(role, art):
    """The mod's own building textures of the role's material: (group, what it is)."""
    return art.nearest("buildings", "diffuse", ROLE_MATERIAL.get(role))


def fit(keys=FIT_PRESETS, style="AFRICAN", grid=(0.02, 0.04, 0.06, 0.08, 0.1, 0.13, 0.16, 0.2, 0.25)):
    """{role: (grain, its median region grain, the group's median, what the group is)}: the fine
    band of the grid that brings the median region of each role closest to its material's
    median. A role whose regions already sit within a tenth of a quartile width keeps no band."""
    art = profile.art("textures")
    runs = {c: role_grains(keys, {r: c for r in materials.MATERIALS[style]}, style) for c in grid}
    out = {}
    for role in materials.MATERIALS[style]:
        group, what = target(role, art)
        seen = {c: float(np.median(g[role])) for c, g in runs.items() if g.get(role)}
        if group is None or not seen:
            continue
        best = min(seen, key=lambda c: abs(seen[c] - group["grain"][1]))
        out[role] = (best, seen[best], group["grain"][1], what)
    return out


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    art = profile.art("textures")
    if art is None:
        raise SystemExit("no texture profile: run tools/texture_survey.py --profile-out first")
    if "--fit" in argv:
        style = opt("--style", "AFRICAN")
        keys = [a for a in argv if not a.startswith("--") and a != style] or list(FIT_PRESETS)
        now = role_grains(keys, None, style)
        for role, (c, got, want, what) in sorted(fit(keys, style).items()):
            have = materials.plan(style)[role][4]
            med = float(np.median(now[role])) if now.get(role) else float("nan")
            print(f"{role:8} grain band {have if have is not None else '-'} -> {c:.3f}: "
                  f"region grain {med:.3f} -> {got:.3f} "
                  f"(the mod's {what}: {want:.3f}; {len(now.get(role, []))} regions)")
        return 0
    origin, category = opt("--origin", "own"), opt("--category", "buildings")
    group = art.group(origin, category, "diffuse", "*")
    if group is None:
        raise SystemExit(f"the profile has no group for {origin} {category}")
    values = {origin, category, opt("--size")}
    keys = [a for a in argv if not a.startswith("--") and a not in values] or \
        ["WHITE_HOUSE", "COLONIAL_HOUSE", "TIMBER_INN", "AFRICAN_HOUSE_SUBSAHARAN", "AFRICAN_PALACE_SAHEL"]
    q = "  ".join(f"{k} {group[k][0]:.2f}/{group[k][1]:.2f}/{group[k][2]:.2f}" if k != "luminance"
                  else f"{k} {group[k][0]:.0f}/{group[k][1]:.0f}/{group[k][2]:.0f}" for k in texmaker.MEASURES)
    print(f"against {origin} {category}, {group['count']} textures: {q}")
    worst = 0.0
    for key in keys:
        m, d = check(key, group, True if "--materials" in argv else None, int(opt("--size", "1024")))
        worst = max(worst, d["off"])
        print(f"{key:28} grain {m['grain']:.3f} ({d['grain']:+.2f})  saturation {m['saturation']:.3f} "
              f"({d['saturation']:+.2f})  luminance {m['luminance']:5.1f} ({d['luminance']:+.2f})")
    print(f"the furthest is {worst:.2f} widths out")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
