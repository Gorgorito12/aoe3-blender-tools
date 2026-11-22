# SPDX-License-Identifier: GPL-3.0-or-later
"""Aura rings made from the game's own: the ring the Indian economic aura (Karni Mata) puts under the villagers, in
the colours of make_rings.py, each colour a model of its own at the sizes of make_rings.py.

    venv\\Scripts\\python -I tools/make_aura_rings.py --game <game copy> --out <folder> [--folder <name>]
                                                    [--granny-install <folder>] [--helper <exe>]
                                                    [--preview <sheet.png>] [--compress] [--anti dash|teeth|hatch]

It reads art\\effects\\ypack_auras\\aura_econ.gr2 and aura_econ.ddt of the copy (a loose file, or else the art\\Art*.bar
archives), so everything it writes is derived from the game's art: keep the output out of public repositories.

- auraring_<colour>.ddt: the stock texture recoloured, its shape and alpha kept texel for texel at every level;
- auraring_<colour>_<size>.gr2: a copy of the stock mesh, scaled to the width of make_rings.SHAPES' <size>, which names
  that texture (its stored texture name rewritten at the same length; no <replacetexture>, which falls back to the stock
  texture in a scene with a Town Center);
- ring_<colour>.xml and aura_<marker>.xml: the models a unit or an aura names, as make_rings.py writes them, with these
  meshes in place of the flat particles (the markers keep make_rings' floating icons, so make_rings' files must be in
  the same folder);
- ring_<effect>_neg.xml (and its texture and meshes) for the non-economic effects of NEGATIVE: the anti-ring of an aura
  whose effect is negative, in the effect's colours with the adverse shape of --anti (ANTI_VARIANTS).

These rings are the defaults: a civ with an aura model of its own keeps it, and these serve every case with nothing of
more personality.

The mesh is uncompressed through the game's own Granny runtime (granny2.dll of --granny-install, default --game, through
recompress_models.py's helper); --compress stores the copies compressed again (Oodle1), as the originals are.
"""
import colorsys
import os
import pathlib
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "aoe3_blender_tools"))

import bar  # noqa: E402
import make_rings  # noqa: E402

STOCK = "effects\\ypack_auras\\aura_econ"
# Stock texture's gradient runs from yellow-green (the light end, hue about 55 degrees) to teal (about 165): each texel's
# place on it picks the place between a ring's main colour (teal end) and its light one (yellow end).
STOCK_HUES = (165.0, 55.0)
STOCK_MEDIAN = (0.72, 0.56)  # the stock texture's median saturation and value: a ring's own colour stands for them


def read_art(game, art_path):
    """The bytes of art\\<art_path> of a game copy: the loose file, or else the first archive that has it."""
    game = pathlib.Path(game)
    loose = game / "art" / art_path
    if loose.exists():
        return loose.read_bytes()
    want = ("art\\" + art_path).lower()
    for archive in sorted((game / "art").glob("*.bar")):
        for name, offset, size in bar.read_entries(str(archive)):
            if name.lower() == want:
                with open(archive, "rb") as fh:
                    fh.seek(offset)
                    return fh.read(size)
    raise FileNotFoundError(f"art\\{art_path} is neither loose nor in an archive of {game}")


def recolour(rgba, colours):
    """The stock texels in a ring's colours: hue from the place on the stock gradient, saturation and value scaled as
    the colour's own against the stock median, alpha untouched."""
    import numpy as np
    main, light = (np.array(c, np.float64) / 255 for c in colours)
    out = np.array(rgba, np.float64)
    lo, hi = STOCK_HUES
    for y in range(out.shape[0]):
        for x in range(out.shape[1]):
            r, g, b, a = out[y, x]
            if a == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            t = min(1.0, max(0.0, (lo - h * 360) / (lo - hi)))
            th, ts, tv = colorsys.rgb_to_hsv(*(main + (light - main) * t))
            nr, ng, nb = colorsys.hsv_to_rgb(th, min(1.0, s * ts / STOCK_MEDIAN[0]), min(1.0, v * tv / STOCK_MEDIAN[1]))
            out[y, x, :3] = (nr * 255, ng * 255, nb * 255)
    return out.round().clip(0, 255).astype(np.uint8)


# Anti-rings: the ring of an aura whose effect is negative (less damage, a slower fire, fewer hit points, slower, a
# harm over time), ring_<effect>_neg.xml, in its effect's colour family with a shape that reads as adverse. Three
# variants for the owner to pick (--anti): "dash", the outer band and the inner line broken into segments; "teeth",
# triangles pointing inward from the outer band; "hatch", a darker, greyer colour with the outer band cross-hatched.
# The stock texture's outer band lies at 0.80 to 0.97 of its half width, the inner line at 0.55 to 0.65.
NEGATIVE = ("damage", "rof", "hp", "speed", "heal")
ANTI_VARIANTS = ("dash", "teeth", "hatch")
ANTI = "dash"
ANTI_SEGMENTS = 12   # dashes and teeth around the ring
ANTI_GAP = 0.35      # the share of each dash period left empty
HATCH_PERIOD = 0.16  # in fractions of the half width
HATCH_LINE = 0.35    # the share of each period cut out
HATCH_DARK = (0.6, 0.55)  # the hatch variant's value and saturation, as a share of the ring's own


def anti_level(rgba, colours, variant):
    """One level of a ring's texture (already recoloured) made adverse by `variant`."""
    import numpy as np
    out = np.array(rgba, np.float64)
    n = out.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    u, v = (xx + 0.5) / n * 2 - 1, (yy + 0.5) / n * 2 - 1
    r = np.hypot(u, v)
    turn = (np.arctan2(v, u) / (2 * np.pi)) % 1.0
    a = out[..., 3]
    if variant == "dash":
        outer = ((turn * ANTI_SEGMENTS) % 1.0) < ANTI_GAP
        inner = ((turn * 2 * ANTI_SEGMENTS) % 1.0) < ANTI_GAP
        a[(r > 0.72) & outer] = 0
        a[(r <= 0.72) & inner] = 0
    elif variant == "teeth":
        phase = (turn * ANTI_SEGMENTS) % 1.0
        half = 0.32 * (r - 0.62) / (0.81 - 0.62)  # the tooth's half width, in periods: 0 at its tip, 0.32 at its base
        tooth = (r > 0.62) & (r < 0.81) & (np.abs(phase - 0.5) < half)
        main = np.array(colours[0], np.float64) * 0.85
        out[tooth, :3] = main
        a[tooth] = 255
    elif variant == "hatch":
        cut = (((u + v) / HATCH_PERIOD) % 1.0 < HATCH_LINE) | (((u - v) / HATCH_PERIOD) % 1.0 < HATCH_LINE)
        a[(r > 0.72) & cut] = 0
        shown = a > 0
        for y, x in zip(*np.nonzero(shown)):
            h, s, val = colorsys.rgb_to_hsv(*(out[y, x, :3] / 255))
            out[y, x, :3] = np.array(colorsys.hsv_to_rgb(h, s * HATCH_DARK[1], val * HATCH_DARK[0])) * 255
    else:
        raise ValueError(f"unknown anti-ring variant {variant!r}")
    out[..., 3] = a
    return out.round().clip(0, 255).astype(np.uint8)


def ring_texture(stock_ddt, colours, anti=None):
    """The stock .ddt recoloured level by level, in the stock header's usage, alpha, format and level count; with
    `anti`, made adverse by that variant (anti_level)."""
    from aoe3game import ddt
    hd = ddt.read_header(stock_ddt)
    blobs = []
    for level in range(hd.mips):
        texels = recolour(ddt.decode(stock_ddt, level), colours)
        if anti is not None:
            texels = anti_level(texels, colours, anti)
        blobs.append(ddt.encode_level(texels, hd.format, refine=True))
    return ddt.pack(stock_ddt[4], stock_ddt[5], hd.format, hd.width, hd.height, blobs)


def mesh_width(raw):
    """The mesh's full width in metres (its vertices' x extent through the file's units per metre)."""
    from aoe3game import gr2
    doc = gr2.load(raw)
    stats = doc.stats()
    (x0, _, _), (x1, _, _) = stats["bbox_m"]
    return x1 - x0


def scaled_copy(raw, factor, texture):
    """The uncompressed stock mesh with its vertices and bone binding box scaled by `factor` across the ground (x and
    z), and its stored texture name naming art\\<texture>.ddt at the same length (the drive and folders before it
    are what give way), its CRC recomputed."""
    from aoe3game import gr2
    root = gr2.load(raw).root()
    out = bytearray(raw)
    mesh = root.get("Meshes")[0]
    verts = mesh.get("PrimaryVertexData").get("Vertices")
    at = out.find(verts.raw)
    if at < 0 or out.find(verts.raw, at + 1) >= 0:
        raise ValueError("the vertices are not stored once as they are read")
    stride = verts.stride
    for i in range(verts.count):
        p = at + i * stride
        x, y, z = struct.unpack_from("<3f", out, p)
        struct.pack_into("<3f", out, p, x * factor, y, z * factor)
    for binding in mesh.get("BoneBindings"):
        for key in ("OBBMin", "OBBMax"):
            box = struct.pack("<3f", *binding.get(key))
            p = out.find(box)
            if p < 0:
                raise ValueError(f"{key} is not stored as it is read")
            x, y, z = binding.get(key)
            out[p:p + 12] = struct.pack("<3f", x * factor, y, z * factor)
    old = root.get("Textures")[0].get("FromFileName")
    suffix = f"Art\\{texture}.ddt"
    room = len(old) - len(suffix)
    if room < 4:
        raise ValueError(f"{texture!r} is too long for the stored name {old!r}")
    new = "E:\\" + "_" * (room - 4) + "\\" + suffix
    old_b, new_b = old.encode("cp1252") + b"\0", new.encode("cp1252") + b"\0"
    if out.count(old_b) != 1:
        raise ValueError(f"{old!r} is not stored once as a plain string")
    out = bytearray(bytes(out).replace(old_b, new_b))
    struct.pack_into("<I", out, 0x28, gr2.file_crc(bytes(out)))
    return bytes(out)


def mesh_logic(colour):
    out = ""
    for branch, size, _, _ in make_rings.SHAPES:
        out += f"""\t\t\t\t<{branch}>
\t\t\t\t\t<assetreference type="GrannyModel">
\t\t\t\t\t\t<file>effects\\{make_rings.FOLDER}\\auraring_{colour}_{size}</file>
\t\t\t\t\t</assetreference>
\t\t\t\t</{branch}>
"""
    return out


def wanted_files(game, folder, runtime, compress=False):
    """Every file name and its bytes, for art/effects/<folder>/."""
    import recompress_models as rm
    make_rings.FOLDER = folder
    stock_gr2 = read_art(game, STOCK + ".gr2")
    stock_ddt = read_art(game, STOCK + ".ddt")
    raw, _ = rm.recompress(stock_gr2, runtime, 0, None, "stock")
    width = mesh_width(raw)
    wanted = {}
    rings = [(c, colours, None) for c, colours in make_rings.RINGS.items()]
    rings += [(f"{c}_neg", make_rings.RINGS[c], ANTI) for c in NEGATIVE]
    for colour, colours, anti in rings:
        wanted[f"auraring_{colour}.ddt"] = ring_texture(stock_ddt, colours, anti)
        for _, size, ring_width, _ in make_rings.SHAPES:
            name = f"auraring_{colour}_{size}"
            if name + ".gr2" in wanted:
                continue
            mesh = scaled_copy(raw, ring_width / width, f"effects\\{folder}\\auraring_{colour}")
            if compress:
                mesh, _ = rm.recompress(mesh, runtime, 2, None, name)
            wanted[name + ".gr2"] = mesh
        wanted[f"ring_{colour}.xml"] = make_rings.text(make_rings.xml(colour, logic=mesh_logic(colour)))
    for marker, (ring, icon) in make_rings.MARKERS.items():
        wanted[f"aura_{marker}.xml"] = make_rings.text(make_rings.xml(ring, marker=True, logic=mesh_logic(ring),
                                                                     icon=marker))
    return wanted, width


PREVIEW_GROUNDS = ((96, 112, 58), (150, 128, 92), (40, 32, 24))  # grass, dirt, dark


def preview(game, wanted, zoom=4):
    """RGB rows (numpy): the stock texture and every colour's, enlarged `zoom` times, alpha-tested as the game's
    material draws them, on each of PREVIEW_GROUNDS."""
    import numpy as np
    from aoe3game import ddt
    textures = [("stock", read_art(game, STOCK + ".ddt"))] + \
               [(c, wanted[f"auraring_{c}.ddt"]) for c in make_rings.RINGS]
    side = 64 * zoom
    gap = 16
    rows = []
    for ground in PREVIEW_GROUNDS:
        row = np.zeros((side + gap, len(textures) * (side + gap) + gap, 3)) + np.array(ground, np.float64)
        for i, (_, data) in enumerate(textures):
            px = np.asarray(ddt.decode(data)).astype(np.float64)
            idx = np.arange(side) * px.shape[0] // side
            px = px[idx][:, idx]
            a = (px[..., 3:4] >= 128).astype(np.float64)
            left, top = gap + i * (side + gap), gap // 2
            area = row[top:top + side, left:left + side]
            row[top:top + side, left:left + side] = px[..., :3] * a + area * (1 - a)
        rows.append(row)
    return np.concatenate(rows, axis=0).clip(0, 255).astype(np.uint8), [n for n, _ in textures]


def option(args, name, default):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            sys.exit(f"make_aura_rings: {name} needs a value")
        return args[i + 1]
    return default


def main(argv):
    import recompress_models as rm
    from aoe3game.deploy import RefusedPath, refuse_steam
    game = option(argv, "--game", None)
    out = option(argv, "--out", None)
    folder = option(argv, "--folder", "rings")
    if not game or not out:
        print(__doc__)
        return 2
    if not folder or any(c in folder for c in "\\/:."):
        sys.exit("make_aura_rings: --folder is one folder name under art/effects/")
    try:
        refuse_steam(out)
    except RefusedPath as exc:
        sys.exit(f"make_aura_rings: refused: {exc}")
    global ANTI
    ANTI = option(argv, "--anti", ANTI)
    if ANTI not in ANTI_VARIANTS:
        sys.exit(f"make_aura_rings: --anti is one of {', '.join(ANTI_VARIANTS)}")
    install = option(argv, "--granny-install", game)
    helper = option(argv, "--helper", rm.DEFAULT_HELPER)
    dll = os.path.join(install, "granny2.dll")
    if not os.path.exists(dll) or not os.path.exists(helper):
        sys.exit(f"make_aura_rings: needs {dll} and the helper {helper} (recompress_models.py --build-helper)")
    with tempfile.TemporaryDirectory(prefix="make_aura_rings_") as work:
        runtime = rm.Runtime(os.path.abspath(helper), os.path.abspath(dll), work)
        wanted, width = wanted_files(game, folder, runtime, "--compress" in argv)
    target = pathlib.Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in wanted.items():
        (target / name).write_bytes(data)
    print(f"make_aura_rings: the stock ring is {width:.2f} m wide; wrote {len(wanted)} files to {target}")
    sheet = option(argv, "--preview", None)
    if sheet:
        from core.pngio import encode_png
        rows, names = preview(game, wanted)
        pathlib.Path(sheet).write_bytes(encode_png(rows))
        print(f"make_aura_rings: preview in {sheet}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
