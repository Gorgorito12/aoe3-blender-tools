# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a unit's animations before a preview is made (docs/animation-rules.md): joint limits,
contacts, mounted parts, props, interpenetration, lengths, loops, deaths, and (with a baseline)
nothing that existed removed without saying so. Prints PASS or FAIL per check with the worst frame
and its value against the limit, and exits 1 when one fails: the preview is then refused.

    python -I tools/check_anim.py <job.json> [--baseline <old job.json>] [--clips a,b]
        [--json <report.json>] [--risk-sheet <png>] [--preview <folder>] [--verbose]
    python -I tools/check_anim.py --model <model.gr2|rig.json> --anim <clip.gr2> [--anim ...]
        [--rig human|bare] [--ground <y>|none] [--duration <s>] [--loop|--no-loop] [--death]

The job file (docs/animation-rules.md, "The job file") names the actors (a model each, a rig preset,
what they hang on), the clips (an animation per actor, the tactics' length, loop, death, the
props' routes) and the rules (grips, mounts, capsules, props, places, limits, removed). Paths are
relative to the job file. The second form checks one model's clips with the defaults of its rig.

--preview writes the fixed preview of each clip: `<clip>-sheet.png` (4 sides x 2 heights at four
moments), `<clip>-close.gif` (a close 3/4 view, needs Pillow) and `risk-frames.png` (the frames
nearest each limit, the points marked). Models are drawn flat-shaded from their own meshes, bones as
lines when a model has none: no game texture is needed.

Exit status: 0 every check passed, 1 a check failed, 2 the job could not be run.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
from aoe3game import anim_check as ac  # noqa: E402

COLOURS = [(150, 120, 90), (70, 90, 150), (80, 80, 80), (120, 150, 90), (150, 90, 130)]
MARK = (220, 30, 30)
PAIR = (240, 160, 0)


# --------------------------------------------------------------------------------------------------
# Jobs from the command line


def simple_job(args):
    clips = {}
    for path in args.anim:
        name = os.path.splitext(os.path.basename(path))[0]
        c = {"anims": {"unit": os.path.abspath(path)}}
        if args.duration is not None:
            c["duration"] = args.duration
        if args.loop is not None:
            c["loop"] = args.loop
        if args.death:
            c["death"] = True
        clips[name] = c
    ground = None if str(args.ground).lower() == "none" else float(args.ground)
    spec = {"fps": args.fps or 30, "ground": ground,
            "actors": {"unit": {"model": os.path.abspath(args.model),
                                "rig": None if args.rig == "none" else args.rig}},
            "clips": clips}
    return ac.Job(spec)


# --------------------------------------------------------------------------------------------------
# Pictures


def scene(job, s, k):
    """([(points N x 3, triangles, colour)], [(a, b, colour)] bone lines) of every actor at frame k."""
    tris, lines = [], []
    for n, name in enumerate(job.order):
        a = job.actors[name]
        colour = COLOURS[n % len(COLOURS)]
        meshes = ac.mesh_points(job, s, name, k)
        if meshes:
            for m, p in zip(a.model.meshes, meshes):
                tris.append((p, np.asarray(m["triangles"], np.int64), colour))
        else:
            W = s.worlds[name][k]
            for i, par in enumerate(a.model.parents):
                if par >= 0:
                    lines.append((W[par][:3, 3], W[i][:3, 3], colour))
    return tris, lines


def bounds(job, s, frames):
    pts = []
    for k in frames:
        for name in job.order:
            pts.append(s.worlds[name][k][:, :3, 3])
    p = np.concatenate(pts)
    if job.ground is not None:
        p = np.vstack([p, [[p[:, 0].mean(), float(job.ground), p[:, 2].mean()]]])
    lo, hi = p.min(0), p.max(0)
    return (lo + hi) / 2, float(max(hi - lo) * 1.15 + 0.2)


def render(job, s, k, azimuth, elevation, size, centre, span, marks=(), pairs=()):
    import make_dismount as md
    az, el = math.radians(azimuth), math.radians(elevation)
    view = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    right = np.cross([0.0, 1.0, 0.0], view)
    right /= np.linalg.norm(right)
    up = np.cross(view, right)
    right = -right          # the game's left-handed space, as retarget_anims.draw (the unit's right on its right)
    canvas = np.full((size, size, 3), 236.0)
    zbuf = np.full((size, size), np.inf)
    light = view * 0.6 + up * 0.5 + right * 0.2
    light /= np.linalg.norm(light)
    scale = size / span
    c = np.asarray(centre, np.float64)

    def proj(p):
        d = np.atleast_2d(p) - c
        return np.stack([size / 2 + (d @ right) * scale, size / 2 - (d @ up) * scale], 1), -(d @ view)

    if job.ground is not None:                           # a ground grid, metre squares
        g = float(job.ground)
        for t in np.arange(-3, 3.01, 1.0):
            for a, b in (((c[0] + t, g, c[2] - 3), (c[0] + t, g, c[2] + 3)),
                         ((c[0] - 3, g, c[2] + t), (c[0] + 3, g, c[2] + t))):
                _line(canvas, proj(np.array([a, b]))[0], (205, 205, 205))
    tris, lines = scene(job, s, k)
    for p, t, colour in tris:
        p2, depth = proj(p)
        n = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        shade = 0.55 + 0.45 * np.abs(n @ light)
        md.raster(canvas, zbuf, p2, depth, t, None, None, shade, colour)
    for a, b, colour in lines:
        _line(canvas, proj(np.array([a, b]))[0], colour, 2)
    for a, b in pairs:
        _line(canvas, proj(np.array([a, b]))[0], PAIR, 2)
    for p in marks:
        x, y = proj(np.asarray(p))[0][0]
        _ring(canvas, x, y, 6, MARK)
    return canvas.astype(np.uint8)


def _line(canvas, p2, colour, width=1):
    h, w = canvas.shape[:2]
    a, b = p2[0], p2[1]
    for t in np.linspace(0.0, 1.0, int(np.linalg.norm(b - a)) + 2):
        x, y = (a + t * (b - a)).round().astype(int)
        if 0 <= x < w and 0 <= y < h:
            canvas[max(0, y - width + 1):y + width, max(0, x - width + 1):x + width] = colour


def _ring(canvas, x, y, r, colour):
    h, w = canvas.shape[:2]
    for a in np.linspace(0, 2 * math.pi, 48):
        for rr in (r, r - 1):
            xx, yy = int(round(x + rr * math.cos(a))), int(round(y + rr * math.sin(a)))
            if 0 <= xx < w and 0 <= yy < h:
                canvas[yy, xx] = colour


def caption(img, text):
    import make_dismount as md
    return md.label(img, text.upper())


def contact_sheet(job, s, path, size=220, moments=4):
    """4 sides x 2 heights (columns) at `moments` times of the clip (rows)."""
    import make_dismount as md
    n = len(s.times)
    frames = sorted({int(round(i * (n - 1) / (moments - 1))) for i in range(moments)})
    centre, span = bounds(job, s, range(n))
    tiles = []
    for k in frames:
        for el in (10.0, 45.0):
            for az, side in ((0.0, "FRONT"), (90.0, "LEFT"), (180.0, "BACK"), (270.0, "RIGHT")):
                img = render(job, s, k, az, el, size, centre, span)
                tiles.append(caption(img, f"{s.name} {s.times[k]:.2f}S {side} {int(el)}"))
    md.save_png(path, md.sheet(tiles, 8))
    return path


def close_gif(job, s, path, fps=15, size=360):
    try:
        from PIL import Image
    except ImportError:
        return None
    pts = []
    for name in job.order:
        a = job.actors[name]
        bones = [b for b in ((a.rig or {}).get("hands", []) + ["bip01 head"]) if a.model.has(b)]
        for b in bones:
            pts.append(s.at(name, b))
    if pts:
        p = np.concatenate(pts)
        lo, hi = p.min(0), p.max(0)
        centre, span = (lo + hi) / 2, float(max(hi - lo) * 1.4 + 0.4)
    else:
        centre, span = bounds(job, s, range(len(s.times)))
    step = max(1, int(round(job.fps / fps)))
    frames = []
    for k in range(0, len(s.times), step):
        img = caption(render(job, s, k, -40.0, 20.0, size, centre, span), f"{s.name} {s.times[k]:.2f}S")
        frames.append(Image.fromarray(img).quantize(colors=64))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    return path


def risk_sheet(job, report, path, most=12, size=260):
    """Each risk frame from two sides, its points marked, failed checks first."""
    import make_dismount as md
    risks = report.risk_frames()[:most]
    if not risks:
        return None
    tiles = []
    for r in risks:
        s = report.samples[r["clip"]]
        k = r["frame"]
        centre, span = bounds(job, s, [k])
        pts = r["points"]
        if pts:                                          # closer, toward what the check marks
            centre = (centre + np.mean(np.asarray(pts, np.float64), axis=0)) / 2
            span = min(span, 3.5)
        pairs = [(pts[0], pts[1])] if len(pts) == 2 else []
        for az in (-40.0, 50.0):
            img = render(job, s, k, az, 20.0, size, centre, span, marks=pts, pairs=pairs)
            tiles.append(caption(img, f"{r['status']} {r['clip']} {r['time']:.2f}S {r['check']}"))
    md.save_png(path, md.sheet(tiles, 4))
    return path


# --------------------------------------------------------------------------------------------------


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job", nargs="?", help="the job file (JSON)")
    ap.add_argument("--model", help="one model (.gr2, uncompressed, or a rig .json) instead of a job")
    ap.add_argument("--anim", action="append", default=[], help="a clip of --model (repeat)")
    ap.add_argument("--rig", default="human", help="the model's rig preset: human (default), bare or none")
    ap.add_argument("--ground", default="0", help="the ground's height in the model's space, or none")
    ap.add_argument("--duration", type=float, help="the clips' length from the tactics (seconds)")
    ap.add_argument("--loop", dest="loop", action="store_true", default=None, help="the clips loop")
    ap.add_argument("--no-loop", dest="loop", action="store_false", help="the clips do not loop")
    ap.add_argument("--death", action="store_true", help="the clips are deaths")
    ap.add_argument("--fps", type=float, help="frames a second to sample (default the job's, else 30)")
    ap.add_argument("--baseline", help="the job of the version before (adds the inventory check)")
    ap.add_argument("--clips", help="only these clips, comma separated")
    ap.add_argument("--json", help="write the report as JSON (risk frames included)")
    ap.add_argument("--risk-sheet", help="render the risk frames to this PNG")
    ap.add_argument("--preview", help="a folder for the fixed preview: contact sheets, close GIFs, risk frames")
    ap.add_argument("--verbose", action="store_true", help="list the passed checks too")
    args = ap.parse_args(argv)
    try:
        if args.job:
            job = ac.load_job(args.job)
            if args.fps:
                job.fps = args.fps
        elif args.model and args.anim:
            job = simple_job(args)
        else:
            ap.error("give a job file, or --model and --anim")
        baseline = ac.load_job(args.baseline) if args.baseline else None
        clips = args.clips.split(",") if args.clips else None
        for c in clips or []:
            if c not in job.clips:
                raise ac.JobError(f"no clip {c} in the job")
        report = ac.check(job, baseline, clips)
    except (ac.JobError, OSError, KeyError, ValueError) as exc:
        print(f"check_anim: {exc}", file=sys.stderr)
        return 2
    print(report.text(args.verbose))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report.as_dict(), f, indent=1)
    if args.risk_sheet:
        if risk_sheet(job, report, args.risk_sheet):
            print(f"risk frames: {args.risk_sheet}")
    if args.preview:
        if not report.ok:
            print("preview refused: a check failed (fix it, or raise a limit in the job and say why in the script)")
        else:
            os.makedirs(args.preview, exist_ok=True)
            for name, s in report.samples.items():
                contact_sheet(job, s, os.path.join(args.preview, f"{name}-sheet.png"))
                if close_gif(job, s, os.path.join(args.preview, f"{name}-close.gif")) is None:
                    print("close GIFs need Pillow (pip install pillow): skipped")
            risk_sheet(job, report, os.path.join(args.preview, "risk-frames.png"))
            print(f"preview: {args.preview}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
