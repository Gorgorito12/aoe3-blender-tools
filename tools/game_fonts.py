# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's interface fonts as a whole: which letters each typeface of FONTS\\fonts3.xml lacks, and
the missing ones added to every font that has its own file (tools/extend_font.py), ready to deploy.

    python -I tools/game_fonts.py survey --game <copy> [--json <file>]
    python -I tools/game_fonts.py stage --game <copy> --out <folder> --suffix <Word>
                                        [--families "Formal436 BT,Monotype Corsiva"] [--only <letters>] [--no-kern]

survey (reads only, standard library): every typeface fonts3.xml names, how many entries name it,
where its file is (loose in FONTS\\, inside an archive of FONTS\\, or none: a Windows font such as Arial)
and the letters of extend_font's scope it lacks (Latin-1, Latin Extended-A, the Romanian comma
letters), read from the font's own character map.

stage (needs fontTools, and Pillow for the proof sheets: pip install -r requirements-fonts.txt) writes,
outside the copy:
    <out>\\copy\\FONTS\\<file>_<Word>.ttf   each extended font, family "<typeface> <Word>"
    <out>\\copy\\FONTS\\fonts3.xml          the copy's own, every TypeFace of those typefaces renamed
                                          (nothing else in the file changes: aoe3game/uifonts.retarget)
    <out>\\proof-<file>.png, <out>\\report-<file>.json, <out>\\fonts.json
<out>\\copy is laid out as the game copy: "Deploy edited files to the test copy" (tools/game_deploy.py
--files) puts it in with a backup of fonts3.xml, and undo takes it out. The archives are never changed:
measured in a Wars of Liberty copy (its fonts fix, 2026-11-18), the game loads a loose .ttf of FONTS\\
as it loads those of Fonts.bar, and the new family names never clash with the originals.

The fonts belong to their makers (Bitstream, Monotype, ...): this tool ships none, it changes the
copies you already have; whether a changed font may be shipped is for the font's licence to say.
"""
import hashlib
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "aoe3_blender_tools"))

import bar  # noqa: E402
from aoe3game import uifonts  # noqa: E402

FONT_EXT = (".ttf", ".otf")
LICENCE = ("The fonts belong to their makers: nothing here ships a font; it changes the copies you have. "
           "Whether a changed font may be shipped with a mod is for its licence to say.")


class FontsError(ValueError):
    pass


def fonts_dir(copy):
    """The copy's FONTS folder (any case), or FontsError."""
    for name in os.listdir(copy) if os.path.isdir(copy) else []:
        if name.lower() == "fonts" and os.path.isdir(os.path.join(copy, name)):
            return os.path.join(copy, name)
    raise FontsError(f"{copy} has no FONTS folder: not a game copy")


def font_files(folder):
    """[{"family", "file", "where", "read"}] of a FONTS folder: its loose fonts first (as the game
    reads them, measured), then those of each archive (Fonts.bar first). `read()` gives the bytes."""
    out = []
    names = sorted(os.listdir(folder))
    for name in names:
        path = os.path.join(folder, name)
        if name.lower().endswith(FONT_EXT) and os.path.isfile(path):
            with open(path, "rb") as fh:
                head = fh.read(1 << 20)
            fam = uifonts.ttf_names(head).get("family")
            if fam:
                out.append({"family": fam, "file": name, "where": f"FONTS\\{name}",
                            "read": (lambda p=path: open(p, "rb").read())})
    archives = [n for n in names if n.lower().endswith(".bar")]
    archives.sort(key=lambda n: (n.lower() != "fonts.bar", n.lower()))
    for name in archives:
        archive = os.path.join(folder, name)
        try:
            entries = bar.read_entries(archive)
        except (OSError, ValueError, struct.error):
            continue
        for stored, off, size in entries:
            if not stored.lower().endswith(FONT_EXT):
                continue
            with open(archive, "rb") as fh:
                fh.seek(off)
                head = fh.read(min(size, 1 << 20))
            fam = uifonts.ttf_names(head).get("family")
            if fam:
                def read(a=archive, o=off, s=size):
                    with open(a, "rb") as fh2:
                        fh2.seek(o)
                        return fh2.read(s)
                out.append({"family": fam, "file": stored.replace("/", "\\").split("\\")[-1],
                            "where": f"{name}:{stored}", "read": read})
    return out


def by_family(files):
    """{family lower-case: its first file} (a loose font wins over an archived one)."""
    out = {}
    for f in files:
        out.setdefault(f["family"].lower(), f)
    return out


def codepoints(data):
    """The characters a TrueType font maps to a glyph (cmap formats 4 and 12), standard library."""
    try:
        num = struct.unpack_from(">H", data, 4)[0]
        tables = {}
        for i in range(num):
            tag, _s, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            tables[tag] = off
        cmap = tables[b"cmap"]
        _v, count = struct.unpack_from(">HH", data, cmap)
        subs = [struct.unpack_from(">HHI", data, cmap + 4 + 8 * i) for i in range(count)]
    except (struct.error, KeyError):
        return set()
    order = {(3, 10): 0, (0, 4): 1, (3, 1): 2, (0, 3): 3}
    subs.sort(key=lambda s: order.get((s[0], s[1]), 9))
    for plat, enc, off in subs:
        if order.get((plat, enc), 9) == 9:
            continue
        at = cmap + off
        fmt = struct.unpack_from(">H", data, at)[0]
        out = set()
        if fmt == 12:
            n = struct.unpack_from(">I", data, at + 12)[0]
            for k in range(n):
                start, end, glyph = struct.unpack_from(">III", data, at + 16 + 12 * k)
                out.update(range(start, end + 1) if glyph or start else range(start + 1, end + 1))
            return out
        if fmt == 4:
            seg = struct.unpack_from(">H", data, at + 6)[0] // 2
            ends = struct.unpack_from(f">{seg}H", data, at + 14)
            starts = struct.unpack_from(f">{seg}H", data, at + 16 + 2 * seg)
            deltas = struct.unpack_from(f">{seg}h", data, at + 16 + 4 * seg)
            ro_at = at + 16 + 6 * seg
            ranges = struct.unpack_from(f">{seg}H", data, ro_at)
            for k in range(seg):
                for cp in range(starts[k], ends[k] + 1):
                    if cp == 0xFFFF:
                        continue
                    if ranges[k] == 0:
                        glyph = (cp + deltas[k]) & 0xFFFF
                    else:
                        g_at = ro_at + 2 * k + ranges[k] + 2 * (cp - starts[k])
                        glyph = struct.unpack_from(">H", data, g_at)[0] if g_at + 2 <= len(data) else 0
                        glyph = (glyph + deltas[k]) & 0xFFFF if glyph else 0
                    if glyph:
                        out.add(cp)
            return out
    return set()


def scope(only=None):
    """The letters extend_font adds by default (or those of --only), as code points."""
    import extend_font
    letters = extend_font.parse_letters(only) if only else extend_font.DEFAULT_SCOPE
    return [cp for cp in letters if chr(cp).isalpha()]


def survey(copy, only=None):
    """{"fonts3": path, "typefaces": [{"typeface", "entries", "where", "file", "missing"}]}: the
    typefaces of fonts3.xml, most used first; `missing` is None for a font with no file here."""
    folder = fonts_dir(copy)
    xml = os.path.join(folder, "fonts3.xml")
    if not os.path.isfile(xml):
        raise FontsError(f"{folder} has no fonts3.xml")
    with open(xml, "rb") as fh:
        written = uifonts.faces(fh.read())
    counts, spelling = {}, {}                 # one typeface whatever its case (Windows ignores it)
    for face, n in written.items():
        key = face.strip().lower()
        counts[key] = counts.get(key, 0) + n
        if n > written.get(spelling.get(key), 0):
            spelling[key] = face
    found = by_family(font_files(folder))
    want = scope(only)
    rows = []
    for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        f = found.get(key)
        missing = None
        if f is not None:
            have = codepoints(f["read"]())
            missing = "".join(chr(cp) for cp in want if cp not in have)
        rows.append({"typeface": f["family"] if f else spelling[key], "entries": n, "where": f["where"] if f else None,
                     "file": f["file"] if f else None, "missing": missing})
    return {"fonts3": xml, "typefaces": rows}


def _inside(path, folder):
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return a == b or a.startswith(b + os.sep)


def _refuse_steam(path):
    p = os.path.abspath(path).replace("/", "\\").lower() + "\\"
    if "\\steamapps\\" in p or "\\steam\\" in p:
        raise FontsError(f"refusing to write inside a Steam library: {path}")


def new_name(file, suffix):
    stem, ext = os.path.splitext(file)
    return f"{stem.rstrip('_')}_{suffix}{ext}"


def stage(copy, out, suffix, families=None, only=None, kern=True, log=print):
    """Builds the extended fonts and fonts3.xml under <out>\\copy\\FONTS (never in the copy) and
    returns the summary written to <out>\\fonts.json."""
    import extend_font
    if not suffix or not suffix.replace("_", "").isalnum():
        raise FontsError("--suffix: letters, digits and _ (it ends every new family name, e.g. WoL)")
    folder = fonts_dir(copy)
    if _inside(out, copy):
        raise FontsError("the output must be outside the game copy")
    _refuse_steam(out)
    xml = os.path.join(folder, "fonts3.xml")
    if not os.path.isfile(xml):
        raise FontsError(f"{folder} has no fonts3.xml")
    extend_font.need_fonttools()
    with open(xml, "rb") as fh:
        original = fh.read()
    report = survey(copy, only)
    wanted = {f.strip().lower() for f in families.split(",")} if families else None
    found = by_family(font_files(folder))
    target = os.path.join(out, "copy", "FONTS")
    os.makedirs(target, exist_ok=True)
    mapping, done, skipped = {}, [], []
    with tempfile.TemporaryDirectory(prefix="gamefonts") as tmp:
        for row in report["typefaces"]:
            face = row["typeface"]
            if wanted is not None and face.strip().lower() not in wanted:
                continue
            if row["file"] is None:
                skipped.append({"typeface": face, "why": "no file in the copy (a Windows font): left as it is"})
                continue
            if face.strip().lower().endswith(" " + suffix.lower()):
                skipped.append({"typeface": face, "why": "already an extended font"})
                continue
            if not row["missing"]:
                skipped.append({"typeface": face, "why": "lacks no letter"})
                continue
            src = os.path.join(tmp, row["file"])
            with open(src, "wb") as fh:
                fh.write(found[face.strip().lower()]["read"]())
            name = new_name(row["file"], suffix)
            dst = os.path.join(target, name)
            family = f"{face} {suffix}"
            try:
                rep = extend_font.extend(src, dst, family=family,
                                         only=extend_font.parse_letters(only) if only else None, kern=kern)
            except SystemExit as e:                   # extend_font says why and exits
                skipped.append({"typeface": face, "why": str(e)})
                continue
            if not rep["added_count"]:
                os.remove(dst)
                skipped.append({"typeface": face, "why": "none of its missing letters could be built: "
                                + "".join(rep["not_built"])})
                continue
            stem = os.path.splitext(name)[0]
            try:
                extend_font.proof(dst, os.path.join(out, f"proof-{stem}.png"), rep["added"],
                                  sample="Ăă Ââ Îî Șș Țț Şş Ţţ  Sarja Roșior · Călărași · Racoviță")
            except ImportError:
                log("  (no Pillow: no proof sheet)")
            with open(os.path.join(out, f"report-{stem}.json"), "w", encoding="utf-8") as fh:
                json.dump(rep, fh, ensure_ascii=False, indent=1)
            with open(dst, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            mapping[face] = family
            done.append({"typeface": face, "family": family, "from": row["where"], "file": f"FONTS\\{name}",
                         "added": rep["added"], "added_count": rep["added_count"],
                         "not_built": "".join(rep["not_built"]), "sha256": digest})
            log(f"{face}: {rep['added_count']} letters added -> FONTS\\{name} ({family!r})"
                + (f"; not built: {''.join(rep['not_built'])}" if rep["not_built"] else ""))
    new, changed = uifonts.retarget(original, mapping)
    if done:
        with open(os.path.join(target, "fonts3.xml"), "wb") as fh:
            fh.write(new)
    summary = {"copy": os.path.abspath(copy), "suffix": suffix, "fonts": done, "skipped": skipped,
               "fonts3_changed": changed, "deploy": os.path.join(out, "copy"), "licence": LICENCE}
    with open(os.path.join(out, "fonts.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    return summary


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    verb, copy = (argv[0] if argv else None), opt("--game")
    if verb not in ("survey", "stage") or not copy:
        print(__doc__)
        return 2
    try:
        if verb == "survey":
            r = survey(copy, opt("--only"))
            print(f"{r['fonts3']}: {len(r['typefaces'])} typefaces")
            for row in r["typefaces"]:
                where = row["where"] or "no file here (a Windows font)"
                missing = ("lacks no letter" if row["missing"] == "" else f"lacks {len(row['missing'])}: {row['missing']}"
                           ) if row["missing"] is not None else "-"
                print(f"  {row['entries']:4d}  {row['typeface']!r}  {where}  {missing}")
            if opt("--json"):
                with open(opt("--json"), "w", encoding="utf-8") as fh:
                    json.dump(r, fh, ensure_ascii=False, indent=1)
            return 0
        out = opt("--out")
        if not out:
            print("stage: --out is needed")
            return 2
        s = stage(copy, out, opt("--suffix"), opt("--families"), opt("--only"), kern="--no-kern" not in argv)
    except FontsError as e:
        print(f"refused: {e}")
        return 1
    for k in s["skipped"]:
        print(f"{k['typeface']}: {k['why']}")
    if s["fonts"]:
        print(f"fonts3.xml: {s['fonts3_changed']} TypeFace values changed")
        print(f"ready to deploy: {s['deploy']} (Deploy edited files to the test copy; undo takes it out)")
    else:
        print("nothing to add: no font with a file here lacks a letter")
    print(LICENCE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
