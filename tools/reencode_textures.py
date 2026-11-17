# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-encodes textures (.ddt) for older graphics cards: the format follows the texture's own
header and pixels, a texture larger than a limit is halved, the mip chain is made complete, and
each result is compared with its original; a result that strays too far is not used.

    python -I tools\\reencode_textures.py run --in <list file or folder> --out <folder>
        [--root <folder the list is relative to>] (--limit WxH | --tad <tad.json>)
        [--smallest 4] [--max-mean 3.0] [--max-block 24] [--sheets <folder>] [--fast]
    python -I tools\\reencode_textures.py tad --game <copy> --out <tad.json>
        [--cache <survey cache> ...] [--granny <bridge.exe> --work <folder>]
    python -I tools\\reencode_textures.py select --game <copy> --out <list file>
        [--cache ...] [--granny <bridge.exe> --work <folder>]

**run.** Each .ddt in, one result: re-encoded (written below --out at its path relative to
--root, or to the folder given), unchanged (it already follows the rules; nothing written) or kept
(it breaks a rule or the check; nothing written, the reason in the report). The rules:

- **Format** (the header's alpha value is kept as it is):
  - usage bit 4 (a bump map): DXT5;
  - alpha 0: DXT1, half the size of DXT3. When the alpha channel is not opaque everywhere
    (something may test it), DXT3 instead, and the report says so;
  - alpha 1 (player colour), 4 (transparent) or 8 (blend): DXT3, as the game's own;
  - BGRA (uncompressed) follows the same rule; grey and other formats are kept;
  - a texture whose sides are not powers of two is kept (the stock game has none; two such
    textures were among those whose re-encoding broke other scenes in game: docs/game-formats.md).
- **Size:** a texture with a side above the limit is halved, both sides at once, until both
  fit (area average; a bump map's normals are made unit length again). The limit is given
  (--limit) or is twice the mean width and height of the stock game's home-city building
  textures (`tad`).
- **Mips:** a full chain down to 4 px on the short side (--smallest; 8 stops one level earlier),
  the stock game's convention. A longer chain that is already there is kept.
- **Levels that do not change size are not re-encoded when their blocks can be carried over:**
  DXT3/DXT5 colour blocks become DXT1 blocks that decode to the same pixels; a DXT3 or DXT5
  alpha is re-quantised from its decoded values. Everything else is encoded from pixels with the
  least-squares encoder (ddt._colour_encode, refine=True; --fast for the plain one). A halved
  texture's level takes the original's own level of that size instead, carried over, when that
  one is closer to the area average.
- **Check:** the new top level, decoded, against the original top level (area averaged to the
  new size when halved): the mean absolute difference per channel (RGB, and A when the format
  keeps it), and the worst 4 x 4 block's mean. Above --max-mean or --max-block the texture is
  kept as it was.

Writes into --out: the .ddt files, report.json, report.csv; with --sheets, one PNG per texture
(original | new | difference x4, each at 100 %) and index.html.

**tad.** The stock game's home-city building textures, measured: the home-city files in
data\\Data*.bar (the latest archive holding each), each <building><visual>, its anim files and
models in art\\*.bar (compressed models read from survey caches or the bridge, as
tools/hc_survey.py does), the .ddt each model stores. Writes their mean width and height.

**select.** The home-city building textures of a game copy (tools/hc_survey.py's use "building")
that only home-city building models and anim files use, the mod's own loose files; and the
others, with why (shared with a scene, a background, a prop or a model outside the home cities,
named by an anim file outside them, reached by an anim file that protoy.xml gives a unit or
building of the game, stock).
"""
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
from aoe3game import ddt  # noqa: E402

FORMAT_NAMES = {ddt.BGRA: "BGRA", ddt.DXT1: "DXT1", ddt.GREY: "grey", ddt.DXT3: "DXT3", ddt.DXT5: "DXT5"}
# The check. Measured on the home-city building textures of a mod: a sound DXT1 encoding of a
# detailed texture (roof tiles, thatch, stone) differs from its source by 2 to 6 levels on average
# and up to about 21 in its worst 4 x 4 block; a lost alpha, a swapped channel or a broken block
# is far above both.
MAX_MEAN = 6.0          # mean absolute difference per channel, 0-255
MAX_BLOCK = 32.0        # the worst 4 x 4 block's mean absolute difference


# --------------------------------------------------------------------------------------------------
# The rules

def choose_format(hd, rgba):
    """(format, why) for a texture's header and decoded top level; (None, why) to keep it."""
    if hd.format not in (ddt.BGRA, ddt.DXT1, ddt.DXT3, ddt.DXT5):
        return None, f"format {FORMAT_NAMES.get(hd.format, hd.format)} is not re-encoded"
    if hd.usage & 4:
        return ddt.DXT5, "bump map (usage 4): DXT5"
    if hd.alpha == 0:
        if (rgba[..., 3] < 255).any():
            return ddt.DXT3, "alpha 0 but the alpha channel is not opaque: DXT3"
        return ddt.DXT1, "no alpha (alpha 0): DXT1"
    if hd.alpha in (1, 4, 8):
        return ddt.DXT3, f"alpha {hd.alpha} ({ddt.ALPHAS[hd.alpha]}): DXT3"
    return None, f"alpha value {hd.alpha} is unknown"


def power_of_two(n):
    return n > 0 and n & (n - 1) == 0


def target_size(width, height, limit_w, limit_h):
    """The size after halving both sides until each fits its limit (never below 4 px)."""
    w, h = width, height
    while (w > limit_w or h > limit_h) and min(w, h) >= 8:
        w, h = w // 2, h // 2
    return w, h


def level_bytes(fmt, w, h):
    if fmt == ddt.BGRA:
        return w * h * 4
    if fmt == ddt.GREY:
        return w * h
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == ddt.DXT1 else 16)


def texel_bytes(data):
    """The bytes of every level: what the card holds (the estimate of video memory)."""
    return sum(size for _off, size in ddt.read_header(data).levels)


def digits(data):
    return ",".join(str(b) for b in data[4:8])


# --------------------------------------------------------------------------------------------------
# Carrying blocks over

def transcode(data, level, fmt):
    """The bytes of one level in `fmt` taken from the source's blocks, or None when they cannot
    be carried over (then the level is encoded from pixels)."""
    np = ddt._np()
    hd = ddt.read_header(data)
    if hd.format not in (ddt.DXT1, ddt.DXT3, ddt.DXT5):
        return None
    src, blk = ddt.level_blocks(data, level)
    if src == fmt:
        return blk.tobytes()
    if fmt == ddt.DXT1 and src in (ddt.DXT3, ddt.DXT5):
        return ddt.colour_blocks_as_dxt1(blk[:, 8:]).tobytes()
    if fmt in (ddt.DXT3, ddt.DXT5) and src in (ddt.DXT3, ddt.DXT5):
        alpha = ddt.alpha_blocks(ddt.decode(data, level), fmt)
        return np.concatenate([alpha, blk[:, 8:]], axis=1).tobytes()
    return None


# --------------------------------------------------------------------------------------------------
# One texture

def _err(new_px, ref_px, channels):
    """(mean, worst 4 x 4 block mean) of the absolute difference over the given channels."""
    np = ddt._np()
    d = np.abs(new_px[..., channels].astype(np.float32) - ref_px[..., channels].astype(np.float32))
    h, w = d.shape[:2]
    ph, pw = -(-h // 4) * 4, -(-w // 4) * 4
    p = np.pad(d, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    blocks = p.reshape(ph // 4, 4, pw // 4, 4, len(channels)).mean(axis=(1, 3, 4))
    return float(d.mean()), float(blocks.max())


def reencode(data, limit, smallest=4, refine=True, max_mean=MAX_MEAN, max_block=MAX_BLOCK):
    """(new bytes or None, record) for one texture's bytes. record: action (re-encoded,
    unchanged, kept), reason, before/after header digits, sizes and bytes, the errors."""
    np = ddt._np()
    hd = ddt.read_header(data)
    rec = {"before": digits(data), "width": hd.width, "height": hd.height, "bytes": len(data),
           "texels": texel_bytes(data)}
    rgba0 = ddt.decode(data, 0) if hd.format in (ddt.BGRA, ddt.DXT1, ddt.DXT3, ddt.DXT5, ddt.GREY) \
        else None
    fmt, why = choose_format(hd, rgba0) if rgba0 is not None else (None, "not decoded")
    rec["rule"] = why
    rec["alpha_opaque"] = bool(rgba0 is not None and (rgba0[..., 3] == 255).all())
    if fmt is None:
        return None, dict(rec, action="kept", reason=why)
    if not (power_of_two(hd.width) and power_of_two(hd.height)):
        # a precaution: the stock game has none, and two such textures were among those whose
        # re-encoding broke other scenes in game (docs/game-formats.md, "Re-encoding")
        return None, dict(rec, action="kept", reason=f"{hd.width}x{hd.height}: sides that are not "
                          "powers of two are left as they are (DXT and mips need them)")
    w, h = target_size(hd.width, hd.height, *limit)
    resized = (w, h) != (hd.width, hd.height)
    full = ddt.chain_length(w, h, smallest)
    have = len(hd.levels)
    n = have if (not resized and have >= full) else full
    if fmt == hd.format and not resized and n == have:
        return None, dict(rec, action="unchanged", reason="already " + FORMAT_NAMES[fmt]
                          + f", {have} levels", after=rec["before"], new_width=w, new_height=h,
                          new_bytes=len(data), new_texels=rec["texels"], mean=0.0, block=0.0)
    bump = bool(hd.usage & 4)
    renorm = bump and ddt.is_packed_normal_map(rgba0)
    top = ddt.area_resize(rgba0, h, w) if resized else rgba0.astype(np.float32)
    if resized and renorm:
        top = ddt.renormalise(top)
    chain, cur = [top], top
    for _ in range(1, n):
        cur = ddt.halve(cur)
        if renorm:
            cur = ddt.renormalise(cur)
        chain.append(cur)
    as_u8 = [np.clip(c + 0.5, 0, 255).astype(np.uint8) for c in chain]
    shift = 0
    while (hd.width >> shift, hd.height >> shift) != (w, h) and shift < 16:
        shift += 1
    channels = [0, 1, 2] + ([3] if fmt != ddt.DXT1 else [])
    blobs, carried = [], 0
    for k in range(n):
        blob = None
        if not resized and k < have:
            blob = transcode(data, k, fmt)
            if blob is not None:
                carried += 1
            else:
                blob = ddt.encode_level(ddt.decode(data, k), fmt, refine)
        if blob is None:
            blob = ddt.encode_level(as_u8[k], fmt, refine)
            if resized and k + shift < have:
                # the original's own smaller level, carried over, when it is the closer of the two
                own = transcode(data, k + shift, fmt)
                if own is not None:
                    lw, lh = max(1, w >> k), max(1, h >> k)
                    a = ddt.decode(ddt.pack(hd.usage, hd.alpha, fmt, lw, lh, [blob]))
                    b = ddt.decode(ddt.pack(hd.usage, hd.alpha, fmt, lw, lh, [own]))
                    if _err(b, as_u8[k], channels)[0] < _err(a, as_u8[k], channels)[0]:
                        blob = own
                        carried += 1
        if len(blob) != level_bytes(fmt, max(1, w >> k), max(1, h >> k)):
            raise ddt.DdtError(f"level {k}: {len(blob)} bytes")
        blobs.append(blob)
    new = ddt.pack(hd.usage, hd.alpha, fmt, w, h, blobs)
    back = ddt.decode(new, 0)
    mean, block = _err(back, as_u8[0], channels)
    rec.update(after=digits(new), new_width=w, new_height=h, new_bytes=len(new),
               new_texels=texel_bytes(new), mean=round(mean, 3), block=round(block, 2),
               resized=resized, levels_carried=carried, normals_renormalised=renorm)
    if mean > max_mean or block > max_block:
        reason = (f"the check failed: mean {mean:.2f} (max {max_mean}), worst block {block:.1f} "
                  f"(max {max_block})")
        return None, dict(rec, action="kept", reason=reason, _new=new, _ref=as_u8[0])
    parts = [FORMAT_NAMES[hd.format] + " -> " + FORMAT_NAMES[fmt] if fmt != hd.format else None,
             f"{hd.width}x{hd.height} -> {w}x{h}" if resized else None,
             f"{have} -> {n} levels" if n != have else None]
    return new, dict(rec, action="re-encoded", reason="; ".join(p for p in parts if p),
                     _ref=as_u8[0])


# --------------------------------------------------------------------------------------------------
# Comparison sheets

def sheet(old, new, ref, alpha):
    """An RGB image: the original's top level | the new top level | |new - reference| x 4, each at
    100 %; with alpha, a second row with the alpha channels in grey."""
    np = ddt._np()
    gap = 8
    diff = np.clip(np.abs(new.astype(np.int32) - ref.astype(np.int32)) * 4, 0, 255).astype(np.uint8)
    panels = [old, new, diff]
    rows = [[p[..., :3] for p in panels]]
    if alpha:
        rows.append([np.repeat(p[..., 3:4], 3, axis=2) for p in panels])
    width = sum(p.shape[1] for p in rows[0]) + gap * 4
    height = sum(max(p.shape[0] for p in r) for r in rows) + gap * (len(rows) + 1)
    out = np.full((height, width, 3), 40, np.uint8)
    y = gap
    for r in rows:
        x = gap
        for p in r:
            out[y:y + p.shape[0], x:x + p.shape[1]] = p
            x += p.shape[1] + gap
        y += max(p.shape[0] for p in r) + gap
    return out


def write_png(path, rgb):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))
    from core.pngio import encode_png
    with open(path, "wb") as fh:
        fh.write(encode_png(rgb))


# --------------------------------------------------------------------------------------------------
# The stock game's mean (tad)

def stock_homecity_files(game):
    """{name: (archive, stored, offset, size)} of the home-city files in data\\Data*.bar, each from
    the last archive (by name) that holds it."""
    import bar
    out = {}
    data = os.path.join(game, "data")
    for name in sorted(os.listdir(data), key=str.lower):
        if not (name.lower().startswith("data") and name.lower().endswith(".bar")):
            continue
        for stored, offset, size in bar.read_entries(os.path.join(data, name)):
            base = stored.replace("/", "\\").rsplit("\\", 1)[-1]
            if base.lower().startswith("homecity") and ".xml" in base.lower():
                out[base.lower().replace(".xmb", "")] = (os.path.join(data, name), stored, offset, size)
    return out


def tad_mean(game, caches=(), bridge=None, log=print):
    """{"textures": [{key, width, height, header}], "mean_width", "mean_height", "missing"}: the
    stock game's home-city building textures (see the module's doc)."""
    import hc_survey as hs
    art = hs.Art(os.path.join(game, "art"), loose=False)
    files = stock_homecity_files(game)
    cache, starts = {}, []
    for name, (archive, _stored, offset, size) in sorted(files.items()):
        with open(archive, "rb") as fh:
            fh.seek(offset)
            text = hs.decode_text(fh.read(size))
        for r in hs.hc_refs(text)["refs"]:
            if r["use"] != "building":
                continue
            key, base = hs.resolve_hc(art, r)
            if key and base != "missing" and not key.endswith(".gr2"):
                starts.append(key)
    anims = hs.walk(art, sorted(set(starts)), cache)
    ctx = hs.building_contexts(art, sorted(set(starts)), cache, hs.Bipeds(art, caches, bridge))
    models = set()
    for akey, info in anims.items():
        if ctx.get(akey) != {"building"}:          # people standing for a building are left out
            continue
        effective = info["variants"][0][0] if info["variants"] else None
        for r in info["refs"]:
            if r["kind"] == "model" and r["variant"] == effective:
                models.add(hs.model_key(r["value"]))
    textures, missing = {}, []
    for k in sorted(models):
        data = art.read(k)
        if data is None:
            missing.append((k, "no such model"))
            continue
        raw, how = hs.raw_bytes(data, caches, bridge)
        if raw is None:
            missing.append((k, how))
            continue
        for stored in hs.measure(raw)["textures"]:
            t = hs.texture_info(art, stored, k)
            if t["resolved"] and t["width"]:
                textures[t["resolved"]] = {"key": t["resolved"], "width": t["width"],
                                           "height": t["height"], "header": t["header"]}
    rows = sorted(textures.values(), key=lambda t: t["key"])
    n = len(rows) or 1
    res = {"homecity_files": len(files), "anim_files": len(anims), "models": len(models),
           "textures": rows, "missing": missing,
           "mean_width": round(sum(t["width"] for t in rows) / n, 1),
           "mean_height": round(sum(t["height"] for t in rows) / n, 1)}
    res["limit"] = [int(2 * res["mean_width"]), int(2 * res["mean_height"])]
    log(f"tad: {len(rows)} textures of {len(models)} models; mean {res['mean_width']} x "
        f"{res['mean_height']}; limit {res['limit'][0]} x {res['limit'][1]}; "
        f"{len(missing)} models not read")
    return res


# --------------------------------------------------------------------------------------------------
# Which textures (select)

def proto_anim_files(game):
    """{anim key: proto name} of every <AnimFile> in the game copy's data\\protoy.xml (loose, plain
    or compiled): anim files the game's units and buildings use outside the home cities."""
    import re
    import hc_survey as hs
    out = {}
    pat = re.compile(r"<unit\b[^>]*\bname\s*=\s*['\"]([^'\"]+)['\"]|<animfile>\s*([^<]+?)\s*</animfile>",
                     re.I)
    for name in ("protoy.xml", "protoy.xml.xmb"):
        path = os.path.join(game, "data", name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            text = hs.decode_text(fh.read())
        unit = "?"
        for m in pat.finditer(text):
            if m.group(1):
                unit = m.group(1)
                continue
            k = hs.join_key("", m.group(2))
            if k:
                out.setdefault(k, unit)
        break
    return out


def select(res, tex_refs=None, proto_anims=None):
    """(chosen, others): the .ddt keys of res (hc_survey.survey) that only home-city building
    models and anim files use, the mod's own loose files; others: [(key, why)] of every other
    texture a building uses. tex_refs: hc_move.anim_texture_refs(art), every loose anim file's
    texture names (one outside the home cities makes the texture shared). proto_anims:
    proto_anim_files(game); a texture that a model or texture name of such an anim file reaches
    is used in the game too."""
    import hc_survey as hs
    hs_join, hs_model_key = (lambda v: hs.join_key("", v)), hs.model_key
    art = res["art"]
    hc_anims = {v for h in res["homecities"] for info in h["anims"].values()
                for v, _w in info["variants"][:1]}
    tex_refs = tex_refs or {}
    in_game = {}                      # texture key -> proto anim file reaching it
    for h in res["homecities"]:
        for akey, info in h["anims"].items():
            if akey not in (proto_anims or {}):
                continue
            effective = info["variants"][0][0] if info["variants"] else None
            for r in info["refs"]:
                if r["variant"] != effective:
                    continue
                if r["kind"].startswith("texture"):
                    k = hs_join(r["value"])
                    if k:
                        in_game.setdefault(k if k.endswith(".ddt") else k + ".ddt", akey)
                elif r["kind"] == "model":
                    mk = hs_model_key(r["value"])
                    for row in res["files"]:
                        if row["key"] == mk:
                            for t in row.get("texture_info", []):
                                if t["resolved"]:
                                    in_game.setdefault(t["resolved"], akey)
    chosen, others = [], []
    for key, e in sorted(res["texture_uses"].items()):
        uses = e["uses"]
        if not uses & {"building", "person"}:
            continue
        if key in in_game and "building" in uses:
            others.append((key, f"a unit or building of the game uses it too ({in_game[key]}, "
                           f"protoy.xml {proto_anims[in_game[key]]})"))
            continue
        if "building" not in uses:
            others.append((key, "a person or animal standing for a building (an anim file with a "
                           "rigged model), not a building"))
            continue
        if uses != {"building"}:
            what = sorted(u for u in uses if u != "building")
            others.append((key, "shared with " + ", ".join(
                {"other": "a scene, background, water, path or prop", "outside":
                 "a model used outside the home cities",
                 "person": "a person or animal (an anim file with a rigged model)"}.get(u, u)
                for u in what)))
        elif any(a not in hc_anims for a in tex_refs.get(key, ())):
            others.append((key, "an anim file that no home city reaches names it (it stays where it "
                           "is): "
                           + next(a for a in tex_refs[key] if a not in hc_anims)))
        elif art.status(key) != "mod":
            others.append((key, f"{art.status(key)} file (not the mod's own loose file)"))
        else:
            chosen.append(key)
    return chosen, others


# --------------------------------------------------------------------------------------------------
# Running

def inputs(spec, root):
    """[(source path, path relative to the output)] from a list file or a folder."""
    if os.path.isdir(spec):
        out = []
        for folder, _d, files in os.walk(spec):
            for name in files:
                if name.lower().endswith(".ddt"):
                    full = os.path.join(folder, name)
                    out.append((full, os.path.relpath(full, root or spec)))
        return sorted(out)
    out = []
    with open(spec, encoding="utf-8-sig") as fh:
        for line in fh:
            p = line.strip().split("\t")[0]
            if not p or p.startswith("#"):
                continue
            full = p if os.path.isabs(p) else os.path.join(root or os.path.dirname(spec), p)
            out.append((full, os.path.relpath(full, root) if root else os.path.basename(full)))
    return out


REPORT_COLS = ("path", "action", "reason", "rule", "alpha_opaque", "before", "after", "width", "height",
               "new_width", "new_height", "bytes", "new_bytes", "texels", "new_texels", "mean",
               "block", "levels_carried", "normals_renormalised", "sha256")


def run(items, out, limit, smallest=4, refine=True, max_mean=MAX_MEAN, max_block=MAX_BLOCK,
        sheets=None, log=print):
    os.makedirs(out, exist_ok=True)
    if sheets:
        os.makedirs(sheets, exist_ok=True)
    records = []
    for src, rel in items:
        with open(src, "rb") as fh:
            data = fh.read()
        try:
            new, rec = reencode(data, limit, smallest, refine, max_mean, max_block)
        except ddt.DdtError as exc:
            new, rec = None, {"action": "kept", "reason": f"not readable: {exc}"}
        rec["path"] = rel
        rec["source"] = src
        rec["sha256"] = hashlib.sha256(data).hexdigest()
        if new is not None:
            dst = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(new)
            rec["output"] = dst
        if sheets and "_ref" in rec:
            candidate = new if new is not None else rec.get("_new")
            hd = ddt.read_header(candidate)
            img = sheet(ddt.decode(data, 0), ddt.decode(candidate, 0), rec["_ref"],
                        alpha=hd.format != ddt.DXT1)
            name = rel.replace("\\", "__").replace("/", "__") + ".png"
            write_png(os.path.join(sheets, name), img)
            rec["sheet"] = name
        rec.pop("_ref", None)
        rec.pop("_new", None)
        records.append(rec)
        log(f"{rec['action']:10} {rel}: {rec.get('reason', '')}")
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"limit": list(limit), "smallest": smallest, "max_mean": max_mean,
                   "max_block": max_block, "textures": records}, fh, indent=1)
    with open(os.path.join(out, "report.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(REPORT_COLS)
        for r in records:
            w.writerow([r.get(c, "") for c in REPORT_COLS])
    if sheets:
        write_index(sheets, records)
    return records


def write_index(folder, records):
    rows = []
    for r in records:
        if not r.get("sheet"):
            continue
        rows.append(f"<h3>{r['path']}</h3><p>{r['action']}: {r.get('reason', '')} &mdash; "
                    f"({r['before']}) {r['width']}x{r['height']} &rarr; ({r.get('after', '')}) "
                    f"{r.get('new_width', '')}x{r.get('new_height', '')}, mean {r.get('mean')}, "
                    f"worst block {r.get('block')}</p><img src=\"{r['sheet']}\">")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Texture comparison</title>"
                 "<style>body{background:#222;color:#ddd;font:14px sans-serif}"
                 "img{image-rendering:pixelated}</style>"
                 "<p>Each sheet: the original's top level | the new top level | the difference "
                 "x4 against the original (area averaged to the new size), all at 100 %. "
                 "A second row shows the alpha channels.</p>" + "\n".join(rows))


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    def opts(name):
        return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]

    cmd = argv[0] if argv else None
    bridge = None
    if opt("--granny"):
        if not opt("--work"):
            raise SystemExit("--granny needs --work")
        bridge = (opt("--granny"), os.path.abspath(opt("--game")), os.path.abspath(opt("--work")))
    if cmd == "run" and opt("--in") and opt("--out"):
        if opt("--limit"):
            lw, lh = (int(x) for x in opt("--limit").lower().split("x"))
        elif opt("--tad"):
            with open(opt("--tad"), encoding="utf-8") as fh:
                lw, lh = json.load(fh)["limit"]
        else:
            raise SystemExit("run needs --limit WxH or --tad <tad.json>")
        recs = run(inputs(opt("--in"), opt("--root")), opt("--out"), (lw, lh),
                   smallest=int(opt("--smallest", 4)), refine="--fast" not in argv,
                   max_mean=float(opt("--max-mean", MAX_MEAN)),
                   max_block=float(opt("--max-block", MAX_BLOCK)), sheets=opt("--sheets"))
        counts = {}
        for r in recs:
            counts[r["action"]] = counts.get(r["action"], 0) + 1
        print(counts)
        return 0
    if cmd == "tad" and opt("--game") and opt("--out"):
        res = tad_mean(opt("--game"), opts("--cache"), bridge)
        with open(opt("--out"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
        return 0
    if cmd == "select" and opt("--game") and opt("--out"):
        import hc_move as hm
        import hc_survey as hs
        res = hs.survey(opt("--game"), opt("--target", "x\\homecity"), caches=opts("--cache"),
                        bridge=bridge)
        chosen, others = select(res, hm.anim_texture_refs(res["art"]), proto_anim_files(opt("--game")))
        art = res["art"]
        with open(opt("--out"), "w", encoding="utf-8") as fh:
            for k in chosen:
                fh.write(art.loose[k] + "\n")
            for k, why in others:
                fh.write(f"# not chosen\t{art.display(k)}\t{why}\n")
        print(f"select: {len(chosen)} building textures, {len(others)} left out")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
