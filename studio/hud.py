# SPDX-License-Identifier: GPL-3.0-or-later
"""The game interface screen's work: the in-game HUD of a game copy as the game loads it (read
only), for the page to draw, inspect and, later, edit.

A scene is the main screen (`uimainnew.xml`) and the panels the game loads beside it by name, in
the normal or the minimised variant (the profile option `OptionMinimizedUI`; the minimised files
end in `min`). They all share the 1024 x 768 layout space. Each file is found as the game finds
it: a loose `data\\<name>.xml` first (a compiled twin `<name>.xml.xmb` beside it is noted), then
`data\\Data3.bar`, `Data2.bar`, `Data.bar` (which archive wins is **to verify**; this order is the
assumption). The copies a file hides are listed with it.

Textures are `art\\<path>.ddt` (loose first, then the art archives: `tools/fix_hitpointbar_tags.Art`),
sent as PNG; fonts are `FONTS\\fonts3.xml` (`aoe3game/uifonts.py`) and the TrueType files of
`FONTS\\Fonts.bar`, sent as they are to the page (never copied anywhere); texts are
`data\\stringtabley.xml`. Nothing of the copy is written."""
import hashlib
import json
import os
import re
import threading
import xml.etree.ElementTree as ET

from . import use_core

use_core()
import bar  # noqa: E402  (tools/)
from aoe3game import ddt, proto, uifonts, uilayout, unitpanel  # noqa: E402
from core import paint as painter  # noqa: E402
from fix_hitpointbar_tags import Art  # noqa: E402

MAIN = "uimainnew"
KNOWN_KEYS = None       # filled below: the DLL keys the simulation knows
# the panels the game loads by name beside the main screen (age3y.exe's strings), each with a
# minimised twin "<name>min"
PANELS = ("uiunitselection", "uiunitstatpanel3", "uicommandpanelnew", "uiminimappanelnew",
          "uiwonderpowerpanel", "uiunittrainingpanel", "uitrainsandcontains", "uitraderoutepanel2",
          "uinativecommandpanel2")
DATA_BARS = ("Data3.bar", "Data2.bar", "Data.bar")       # the order a file is looked for: to verify
CULTURES = ("Eur", "Nat", "Asi")
# gadgets the game shows one of: the main screen's panel skins, by culture and UI size
SKIN = re.compile(r"(Eur|Nat|Asi)(Min|Max)$")


SCENE_RULES = os.path.join(os.path.dirname(os.path.abspath(uilayout.__file__)), "uidata", "hud_scene.json")


UIDATA = os.path.dirname(SCENE_RULES)


def scene_rules():
    with open(SCENE_RULES, encoding="utf-8") as fh:
        return json.load(fh)


def table(name):
    """One of aoe3game/uidata's tables."""
    with open(os.path.join(UIDATA, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _known_keys():
    items = table("uhc_minui_items")
    out = {items["key"].lower(), "attacktypeicons"}
    for it in items["items"]:
        out.update(n.lower() for n in it.get("needs", []))
    return out


class HudError(ValueError):
    pass


class Game:
    """What a game copy holds for the HUD, indexed once."""

    def __init__(self, folder):
        if not folder or not os.path.isdir(os.path.join(folder, "data")):
            raise HudError(f"not a game copy (no data folder): {folder}")
        self.folder = folder
        data = os.path.join(folder, "data")
        self.loose = {n.lower(): os.path.join(data, n) for n in os.listdir(data)
                      if os.path.isfile(os.path.join(data, n))}
        self.bars = []
        for name in DATA_BARS:
            path = os.path.join(data, name)
            if os.path.isfile(path):
                entries = {}
                for stored, off, size in bar.read_entries(path):
                    entries.setdefault(os.path.basename(stored.replace("\\", "/")).lower(), (stored, off, size))
                self.bars.append((path, entries))
        self._art = self._fonts = self._ttf = self._strings = None
        self._lock = threading.Lock()

    # ---- files
    def layout(self, stem):
        """(bytes, where, [hidden copies]) of a layout by its name without extension, or None."""
        found = []
        xml, xmb = f"{stem}.xml".lower(), f"{stem}.xml.xmb".lower()
        if xml in self.loose:
            found.append(("loose", self.loose[xml], None))
        if xmb in self.loose:
            found.append(("loose xmb", self.loose[xmb], None))
        for path, entries in self.bars:
            if xmb in entries:
                found.append((os.path.basename(path), path, entries[xmb]))
        if not found:
            return None
        kind, path, entry = found[0]
        data = _read(path, entry)
        where = path if entry is None else f"{os.path.basename(path)}:{entry[0]}"
        hidden = [p if e is None else f"{os.path.basename(p)}:{e[0]}" for _k, p, e in found[1:]]
        return data, where, hidden

    @property
    def art(self):
        with self._lock:
            if self._art is None:
                self._art = Art(os.path.join(self.folder, "art"))
            return self._art

    def texture(self, path):
        """(rgba, where) of a layout's texture path (art-relative, with or without .ddt), or None."""
        p = path.strip().replace("/", "\\")
        if not p:
            return None
        names = [p] if p.lower().endswith((".ddt", ".tga", ".png")) else [p + ".ddt", p]
        for n in names:
            hit = self.art.find(n)
            if hit is not None and hit[0][:4] == ddt.MAGIC:
                return ddt.decode(hit[0], 0), hit[1]
        return None

    @property
    def fonts(self):
        with self._lock:
            if self._fonts is None:
                path = os.path.join(self.folder, "FONTS", "fonts3.xml")
                self._fonts = {}
                if os.path.isfile(path):
                    with open(path, "rb") as fh:
                        self._fonts = uifonts.parse(fh.read())
                self._ttf = {}
                archive = os.path.join(self.folder, "FONTS", "Fonts.bar")
                if os.path.isfile(archive):
                    for stored, off, size in bar.read_entries(archive):
                        if stored.lower().endswith((".ttf", ".otf")):
                            head = _read(archive, (stored, off, min(size, 1 << 20)))
                            fam = uifonts.ttf_names(head).get("family")
                            if fam:
                                self._ttf.setdefault(fam.lower(), (archive, (stored, off, size)))
            return self._fonts

    def art_copies(self, path):
        """Every place an art file of that path is found, in the order the game looks: the loose
        file, then each archive of the art folder that holds it."""
        from fix_hitpointbar_tags import norm
        key = norm(path)
        out = []
        art = self.art
        if key in art.loose:
            out.append(art.loose[key])
        with self._lock:
            if getattr(self, "_art_all", None) is None:
                self._art_all = {}
                for name in sorted(os.listdir(art.root)):
                    if name.lower().endswith(".bar"):
                        archive = os.path.join(art.root, name)
                        for stored, _off, _size in bar.read_entries(archive):
                            self._art_all.setdefault(norm(stored), []).append(f"{name}:{stored}")
        return out + self._art_all.get(key, [])

    def font_where(self, face):
        """Where a typeface's file is: Fonts.bar's entry, or None (a system font)."""
        self.fonts
        hit = self._ttf.get((face or "").lower())
        return f"{os.path.basename(hit[0])}:{hit[1][0]}" if hit else None

    def font_file(self, face):
        """The bytes of a typeface's TrueType file of Fonts.bar, or None (a system font)."""
        self.fonts
        hit = self._ttf.get((face or "").lower())
        return _read(*hit) if hit else None

    def faces(self):
        self.fonts
        return sorted(name for name in self._ttf)

    # ---- the units, their tactics, the DLL's keys and rows
    @property
    def protos(self):
        """(protoy.xml's text, its index), read once."""
        with self._lock:
            if getattr(self, "_protos", None) is None:
                path = self.loose.get("protoy.xml")
                if path is None:
                    raise HudError("this copy has no loose data\\protoy.xml")
                text = proto.read_text(path)[0]
                self._protos = (text, proto.Index(text))
            return self._protos

    def units(self, q="", limit=60):
        """[{"name", "display"}] of the units whose name or shown name holds q."""
        text, index = self.protos
        st = self.strings
        low = q.strip().lower()
        out = []
        for key, name in sorted(index.names.items()):
            s, e = index.spans[key]
            m = re.search(r"<DisplayNameID>(\d+)</DisplayNameID>", text[s:min(e, s + 4000)])
            shown = st.get(int(m.group(1)), ("", None))[0] if m else ""
            if not low or low in key or low in shown.lower():
                out.append({"name": name, "display": shown})
                if len(out) >= limit:
                    break
        return out

    def unit(self, name):
        text, index = self.protos
        try:
            return unitpanel.read_unit(proto.unit_text(text, name, index))
        except proto.ProtoError as e:
            raise HudError(str(e)) from None

    def tactics(self, filename):
        """A tactics file of data\\tactics (loose, then the data archives), read, or None."""
        if not filename:
            return None
        path = os.path.join(self.folder, "data", "tactics", filename)
        data = None
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                data = fh.read()
        else:
            for archive, entries in self.bars:
                for key in (filename.lower(), filename.lower() + ".xmb"):
                    if key in entries:
                        data = _read(archive, entries[key])
                        break
                if data:
                    break
        if not data:
            return None
        if data[:4] == b"l33t" or data[:2] == b"X1":
            import xmbedit
            xml = xmbedit.to_xml(*xmbedit.parse(xmbedit.decode(data)))
            data = xml.encode("utf-8") if isinstance(xml, str) else xml
        text = uilayout.decode(data)[0]
        try:
            return unitpanel.read_tactics(text)
        except ET.ParseError:
            return None

    def keys(self):
        """The DLL's keys in Startup\\*.cfg ({lower key: [arguments]}) and the files read."""
        folder = os.path.join(self.folder, "Startup")
        texts, files = [], []
        if os.path.isdir(folder):
            for n in sorted(os.listdir(folder)):
                if n.lower().endswith(".cfg"):
                    with open(os.path.join(folder, n), "rb") as fh:
                        texts.append(uilayout.decode(fh.read())[0])
                    files.append(n)
        return unitpanel.read_cfg(texts), files

    def rows_file(self, path=None):
        """(read_rows of a minuirows.xml, where) — the copy's data\\uhc\\minuirows.xml by default."""
        path = path or os.path.join(self.folder, "data", "uhc", "minuirows.xml")
        if not os.path.isfile(path):
            return None, path
        with open(path, "rb") as fh:
            text = uilayout.decode(fh.read())[0]
        try:
            return unitpanel.read_rows(text), path
        except ET.ParseError as e:
            raise HudError(f"{path}: {e}") from None

    @property
    def strings(self):
        with self._lock:
            if self._strings is None:
                path = self.loose.get("stringtabley.xml")
                self._strings = proto.strings_index(proto.read_text(path)[0]) if path else {}
            return self._strings


def _read(path, entry):
    with open(path, "rb") as fh:
        if entry is None:
            return fh.read()
        fh.seek(entry[1])
        return fh.read(entry[2])


_GAMES = {}


def game(folder):
    """The indexed copy (kept while the studio runs; read again when its data folder changed)."""
    key = os.path.normcase(os.path.abspath(folder or ""))
    stamp = os.path.getmtime(os.path.join(folder, "data")) if folder and os.path.isdir(os.path.join(folder, "data")) else 0
    g = _GAMES.get(key)
    if g is None or g[0] != stamp:
        g = _GAMES[key] = (stamp, Game(folder))
    return g[1]


# --------------------------------------------------------------------------------------------------
# A scene

class Scene:
    def __init__(self, g, variant):
        if variant not in ("normal", "min"):
            raise HudError("variant: normal or min")
        self.game, self.variant = g, variant
        self.files = []
        self.pngs = {}
        stems = [MAIN] + [p + ("min" if variant == "min" else "") for p in PANELS]
        for stem in stems:
            hit = g.layout(stem)
            if hit is None and variant == "min":
                stem_normal = stem[:-3]
                hit = g.layout(stem_normal)            # a panel with no minimised file: the game's
                stem = stem_normal if hit else stem    # behaviour then is to verify
            if hit is None:
                continue
            data, where, hidden = hit
            try:
                doc = uilayout.parse(data)
            except uilayout.LayoutError as e:
                raise HudError(f"{stem}: {e}") from None
            self.files.append({"stem": stem, "where": where, "hidden": hidden, "doc": doc,
                               "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})

    def gadgets(self):
        """[(file index, element)] of every gadget, file by file in document order."""
        return [(i, e) for i, f in enumerate(self.files) for e in f["doc"].gadgets()]

    def public(self):
        files, out = [], []
        ids = {}
        for i, f in enumerate(self.files):
            files.append({"stem": f["stem"], "where": f["where"], "hidden": f["hidden"], "size": f["size"]})
        for n, (i, e) in enumerate(self.gadgets()):
            ids[id(e)] = n
        textures, strings = set(), set()
        for n, (i, e) in enumerate(self.gadgets()):
            parent = e.parent
            while parent is not None and parent.name_lower != "gadget":
                parent = parent.parent
            attrs = e.attributes()
            states = [s.get("background") or s.get("foreground") or "" for s in e.elements()
                      if s.name_lower == "stateentry"]
            for key in ("background", "foreground"):
                if attrs.get(key):
                    textures.add(attrs[key])
            textures.update(s for s in states if s)
            text = e.own_text().strip()
            for m in re.finditer(r"\$\$(\d+)\$\$", " ".join([text, attrs.get("mouseovertext", ""),
                                                              attrs.get("tooltiptext", "")])):
                strings.add(int(m.group(1)))
            out.append({"id": n, "file": i, "parent": ids.get(id(parent)) if parent is not None else None,
                        "name": attrs.get("name", ""), "type": (attrs.get("type") or "gadget").lower(),
                        "rect": list(uilayout.rect(e) or ()), "attrs": attrs, "text": text,
                        "states": states, "line": e.line,
                        "commands": [c.own_text().strip() for c in e.elements() if c.name_lower == "command"]})
        st = self.game.strings
        return {"variant": self.variant, "files": files, "gadgets": out,
                "textures": sorted(textures, key=str.lower),
                "strings": {n: list(st[n]) for n in sorted(strings) if n in st},
                "fonts": self.game.fonts, "faces": self.game.faces(),
                "skin": SKIN.pattern, "cultures": list(CULTURES), "rules": scene_rules()}

    def refs(self, n, width=1024):
        """Where each thing a gadget names leads: its texts in the string table, its textures and
        the copies they hide, its font and the file of its typeface, its live texts and what they
        read, what the game writes into it, its file, its parents, its commands."""
        pairs = self.gadgets()
        if not 0 <= n < len(pairs):
            raise HudError("no such gadget")
        i, e = pairs[n]
        attrs = e.attributes()
        f = self.files[i]
        out = {"file": {"stem": f["stem"], "where": f["where"], "hidden": f["hidden"], "line": e.line}}
        st = self.game.strings
        texts = []
        for where, value in (("text", e.own_text()), ("mouseovertext", attrs.get("mouseovertext", "")),
                             ("tooltiptext", attrs.get("tooltiptext", ""))):
            for m in re.finditer(r"\$\$(\d+)\$\$([^\n<{$]*)", value or ""):
                k = int(m.group(1))
                hit = st.get(k)
                texts.append({"in": where, "id": k, "fallback": m.group(2).strip(), "found": hit is not None,
                              "text": hit[0] if hit else None, "symbol": hit[1] if hit else None})
        out["strings"] = texts
        tex = []
        names = [("background", attrs.get("background")), ("foreground", attrs.get("foreground"))]
        names += [(f"state {k}", s.get("background") or s.get("foreground"))
                  for k, s in enumerate(c for c in e.elements() if c.name_lower == "stateentry")]
        for role, path in names:
            if not path:
                continue
            p = path.strip().replace("/", "\\")
            candidates = self.game.art_copies(p if p.lower().endswith((".ddt", ".tga", ".png")) else p + ".ddt")
            hit = self.game.texture(path)
            tex.append({"role": role, "path": path, "found": candidates[:1], "hidden": candidates[1:],
                        "size": list(hit[0].shape[1::-1]) if hit else None,
                        "crop": attrs.get("texturecoords") if role == "background" else None})
        out["textures"] = tex
        if attrs.get("textfont"):
            size = attrs.get("textfontsize", "12")
            found = uifonts.lookup(self.game.fonts, attrs["textfont"], size, width)
            used = found or uifonts.lookup(self.game.fonts, *uifonts.FALLBACK.rsplit(" ", 1), width)
            face = used.get("TypeFace") if used else "Arial"
            out["font"] = {"asked": f"{attrs['textfont']} {size}", "found": found is not None,
                           "entry": used.get("Name") if used else None, "typeface": face,
                           "cell": used.get("AscentHeight") if used else None, "resx": used.get("ResX") if used else None,
                           "bold": bool(used and used.get("Bold")), "file": self.game.font_where(face)}
        funcs = {fn["name"].lower(): fn for fn in table("ui_functions")["functions"]}
        live = []
        for value in (e.own_text(), attrs.get("mouseovertext", "")):
            for m in re.finditer(r"\{([A-Za-z_]\w*)(\(([^)]*)\))?\}", value or ""):
                fn = funcs.get(m.group(1).lower())
                live.append({"text": m.group(0), "name": m.group(1), "args": m.group(3) or "", "known": fn is not None,
                             "works": fn["works"] if fn else None, "proto": fn.get("proto") if fn else None,
                             "en": fn["en"] if fn else None, "es": fn["es"] if fn else None})
        out["live"] = live
        name = attrs.get("name", "")
        out["engine"] = [{"en": g["en"], "es": g["es"], "when": g["when"]} for g in table("engine_gadgets")["gadgets"]
                         if re.search(g["re"], name, re.I)]
        chain, p = [], e.parent
        while p is not None and p.name_lower == "gadget":
            chain.append({"name": p.get("name") or "", "hidden": p.has("hidden")})
            p = p.parent
        out["parents"] = chain
        r = uilayout.rect(e)
        pr = uilayout.rect(e.parent) if e.parent is not None and e.parent.name_lower == "gadget" else None
        out["outside"] = bool(r and pr and (r[0] < pr[0] - 4 or r[1] < pr[1] - 4 or r[2] > pr[2] + 4 or r[3] > pr[3] + 4))
        out["commands"] = [c.own_text().strip() for c in e.elements() if c.name_lower == "command"]
        return out

    def simulate(self, unit_name, state=None, keys_on=(), rows_path=None):
        """The panels filled for one unit of the copy (aoe3game/unitpanel.py)."""
        g = self.game
        unit = g.unit(unit_name)
        tactics = g.tactics(unit["tactics"])
        attack_list = unitpanel.attacks(unit, tactics)
        keys, cfg_files = g.keys()
        for k in keys_on:
            keys.setdefault(str(k).lower(), [])
        rows, rows_where = g.rows_file(rows_path)
        gadgets = {}
        for _i, e in self.gadgets():
            name = (e.get("name") or "").lower()
            parent = e.parent
            gadgets[name] = {"parent": (parent.get("name") or "").lower()
                             if parent is not None and parent.name_lower == "gadget" else None,
                             "hidden": e.has("hidden")}
        dll = os.path.isfile(os.path.join(g.folder, "uhc.dll"))
        r = unitpanel.simulate(unit, attack_list, variant=self.variant, gadgets=gadgets, strings=g.strings,
                               keys=keys, rows=rows, dll=dll, state=state)
        r["files"] = {"cfg": cfg_files, "rows": rows_where if rows is not None else None, "rows_asked": rows_where,
                      "tactics": unit["tactics"] if tactics else None}
        r["keys"] = {k: v for k, v in keys.items() if k in KNOWN_KEYS}
        return r

    def texture_png(self, path):
        """(png bytes, where) of a texture, kept for the session; None when not found."""
        key = path.strip().replace("/", "\\").lower()
        if key not in self.pngs:
            hit = self.game.texture(path)
            self.pngs[key] = (painter.png_bytes(hit[0], level=1), hit[1]) if hit else None
        return self.pngs[key]


KNOWN_KEYS = _known_keys()
