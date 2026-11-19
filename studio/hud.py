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

    def textures(self, q="", limit=240):
        """The art paths (without .ddt) of the copy's textures under ui whose path holds q."""
        art = self.art
        low = q.strip().lower().replace("/", "\\")
        out = set()
        for key in list(art.loose) + list(art.archived):
            if key.endswith(".ddt") and ("ui\\" in key) and (not low or low in key):
                out.add(key[:-4])
        return sorted(out)[:limit]

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


def _num(v):
    return str(int(v)) if abs(v - round(v)) < 1e-6 else f"{v:.2f}".rstrip("0").rstrip(".")


def _outside(g, tolerance=4.0):
    p = g.parent
    if p is None or p.name_lower != "gadget":
        return False
    r, pr = uilayout.rect(g), uilayout.rect(p)
    if not r or not pr:
        return False
    t = tolerance
    return r[0] < pr[0] - t or r[1] < pr[1] - t or r[2] > pr[2] + t or r[3] > pr[3] + t


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
            # the baseline of an edit is the file as read: a compiled .xmb's XML text, not its bytes
            self.files.append({"stem": stem, "where": where, "hidden": hidden, "doc": doc, "original": doc.data(),
                               "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        self.undo_stack, self.redo_stack = [], []
        self.rows_index = None             # the index in self.files of the DLL's rows file, once loaded


    def public(self):
        files, out = [], []
        ids = {}
        for i, f in enumerate(self.files):
            files.append({"stem": f["stem"], "where": f["where"], "hidden": f["hidden"], "size": f["size"],
                          "rows": bool(f.get("rows"))})
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
        changed = sum(1 for f in self.files if f["doc"].data() != f["original"])
        return {"variant": self.variant, "files": files, "gadgets": out, "changed": changed,
                "undo": len(self.undo_stack), "redo": len(self.redo_stack),
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

    EMPTY_ROWS = '<?xml version="1.0" encoding="utf-8"?>\r\n<minUIRows>\r\n</minUIRows>\r\n'

    def rows_doc(self, path=None, create=False):
        """The DLL's rows file in the session (the copy's data\\uhc\\minuirows.xml, or the file
        chosen): its index in self.files, or None. `create`: a new empty one when there is none.
        Chosen again while it holds no edit, it is read again."""
        path = path or os.path.join(self.game.folder, "data", "uhc", "minuirows.xml")
        if self.rows_index is not None:
            f = self.files[self.rows_index]
            if os.path.normcase(f["where"]) == os.path.normcase(path) or f["doc"].data() != f["original"]:
                return self.rows_index
            self.files.pop(self.rows_index)
            self.rows_index = None
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                data = fh.read()
        elif create:
            data = self.EMPTY_ROWS.encode("utf-8")
        else:
            return None
        doc = uilayout.parse(data)
        self.files.append({"stem": "minuirows", "where": path, "hidden": [], "doc": doc, "original": doc.data(),
                           "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "rows": True,
                           "new": not os.path.isfile(path)})
        self.rows_index = len(self.files) - 1
        return self.rows_index

    def gadgets(self):
        """[(file index, element)] of every gadget of the layouts, file by file in document order."""
        return [(i, e) for i, f in enumerate(self.files) if not f.get("rows") for e in f["doc"].gadgets()]

    def simulate(self, unit_name, state=None, keys_on=(), rows_path=None):
        """The panels filled for one unit of the copy (aoe3game/unitpanel.py)."""
        g = self.game
        unit = g.unit(unit_name)
        tactics = g.tactics(unit["tactics"])
        attack_list = unitpanel.attacks(unit, tactics)
        keys, cfg_files = g.keys()
        for k in keys_on:
            keys.setdefault(str(k).lower(), [])
        k = self.rows_doc(rows_path)
        if k is not None:
            try:
                rows = unitpanel.read_rows(self.files[k]["doc"].text())
            except ET.ParseError as e:
                raise HudError(f"minuirows.xml: {e}") from None
            rows_where = self.files[k]["where"]
        else:
            rows, rows_where = None, rows_path or os.path.join(g.folder, "data", "uhc", "minuirows.xml")
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

    # ---- editing: each operation changes only the pieces it is about (aoe3game/uilayout.py)
    def _element(self, n):
        pairs = self.gadgets()
        if not isinstance(n, int) or not 0 <= n < len(pairs):
            raise HudError("no such gadget")
        return pairs[n]

    def _layout_of(self, i):
        doc = self.files[i]["doc"]
        tops = [e for e in doc.root.elements() if e.name_lower == "layout"]
        return tops[0] if tops else doc.root

    def _texts(self):
        return [f["doc"].text() for f in self.files]

    def _restore(self, i, text):
        f = self.files[i]
        f["doc"] = uilayout.Doc(uilayout.parse_text(text), f["doc"].encoding, f["doc"].bom)

    def apply(self, ops, label=""):
        """Applies operations as one step that Undo takes back. Returns the id of the gadget the
        last operation was about (after it), or None.

        {"op": "set", "id", "attrs": {name: value or None}}  an attribute set or removed
        {"op": "text", "id", "text"}                         the gadget's own text
        {"op": "add", "parent": id or None, "file": i, "xml"}  a new gadget (None: top level of file i)
        {"op": "dup", "id"}                                  a copy beside it, named "<name>-copy"
        {"op": "del", "id"}                                  taken out with what it holds
        {"op": "move", "id", "parent": id or None, "file": i}  moved under another parent
        {"op": "shift", "id", "dx", "dy", "children": bool}  size1024 moved, with its children or alone"""
        if not isinstance(ops, list) or not ops:
            raise HudError("ops: a list of operations")
        before = self._texts()
        focus = None
        try:
            for op in ops:
                focus = self._one(op)
        except (HudError, uilayout.LayoutError, KeyError, TypeError, ValueError) as e:
            for i, text in enumerate(before):          # all or nothing
                if self.files[i]["doc"].text() != text:
                    self._restore(i, text)
            raise HudError(f"{e}") from None
        after = self._texts()
        changed = {i: (before[i], after[i]) for i in range(len(before)) if before[i] != after[i]}
        if changed:
            self.undo_stack.append({"label": label, "files": changed})
            self.redo_stack.clear()
            del self.undo_stack[:-200]
        ids = {id(e): k for k, (_i, e) in enumerate(self.gadgets())}
        return ids.get(id(focus)) if focus is not None else None    # a row of the rows file is not a gadget

    def _one(self, op):
        kind = op.get("op")
        if kind == "set":
            _i, e = self._element(op.get("id"))
            for k, v in (op.get("attrs") or {}).items():
                if not re.match(r"^[A-Za-z_][\w.:-]*$", k):
                    raise HudError(f"not an attribute name: {k}")
                uilayout.set_attr(e, k, None if v is None else str(v))
            return e
        if kind == "text":
            _i, e = self._element(op.get("id"))
            uilayout.set_text(e, str(op.get("text") or ""))
            return e
        if kind == "shift":
            _i, e = self._element(op.get("id"))
            dx, dy = float(op.get("dx") or 0), float(op.get("dy") or 0)
            targets = [e] + ([g for g in e.walk() if g.name_lower == "gadget"] if op.get("children", True) else [])
            for g in targets:
                r = g.get("size1024")
                if not r:
                    continue
                nums = r.split()
                try:
                    vals = [float(v) for v in nums[:4]]
                except ValueError:
                    continue
                moved = [vals[0] + dx, vals[1] + dy, vals[2] + dx, vals[3] + dy]
                uilayout.set_attr(g, "size1024", " ".join(_num(v) for v in moved) + ("" if len(nums) <= 4 else " " + " ".join(nums[4:])))
            return e
        if kind == "add":
            parent = self._element(op["parent"])[1] if op.get("parent") is not None else self._layout_of(int(op.get("file") or 0))
            new = uilayout.insert(parent, None, str(op.get("xml") or ""))
            return new[-1]
        if kind == "dup":
            _i, e = self._element(op.get("id"))
            index = e.parent.children.index(e) + 1
            copy = uilayout.insert(e.parent, index, e.text())[0]
            names = {(g.get("name") or "").lower() for _f, g in self.gadgets()}
            base = (e.get("name") or "gadget") + "-copy"
            name, k = base, 2
            while name.lower() in names:
                name, k = f"{base}{k}", k + 1
            uilayout.set_attr(copy, "name", name)
            return copy
        if kind == "del":
            _i, e = self._element(op.get("id"))
            uilayout.remove(e)
            return None
        if kind == "move":
            _i, e = self._element(op.get("id"))
            parent = self._element(op["parent"])[1] if op.get("parent") is not None else self._layout_of(int(op.get("file") or 0))
            p = parent
            while p is not None:
                if p is e:
                    raise HudError("a gadget cannot go inside itself")
                p = p.parent
            text = e.text()
            uilayout.remove(e)
            return uilayout.insert(parent, None, text)[-1]
        if kind == "row":
            # a row of the DLL's rows file: replaced when its gadget has one, else added
            k = self.rows_doc(op.get("rows") or None, create=True)
            root = [e for e in self.files[k]["doc"].root.elements() if e.name_lower == "minuirows"]
            if not root:
                raise HudError("the rows file has no <minUIRows>")
            gadget = str(op.get("gadget") or "")
            if not re.match(r"^[\w.-]+$", gadget):
                raise HudError("a row needs its gadget's name")
            for old in [r for r in root[0].elements() if r.name_lower == "row" and (r.get("gadget") or "").lower() == gadget.lower()]:
                uilayout.remove(old)
            attrs = [f'gadget="{gadget}"']
            if op.get("text"):
                attrs.append('text="' + uilayout._escape(str(op["text"])) + '"')
            else:
                attrs.append('item="' + uilayout._escape(str(op.get("item") or "")) + '"')
                if op.get("label"):
                    attrs.append('label="' + uilayout._escape(str(op["label"])) + '"')
            if op.get("types"):
                attrs.append('types="' + uilayout._escape(str(op["types"])) + '"')
            first_other = next((c for c in root[0].elements() if c.name_lower != "row"), None)
            index = root[0].children.index(first_other) if first_other is not None else None
            return uilayout.insert(root[0], index, "<row " + " ".join(attrs) + "/>")[0]
        if kind == "rowdel":
            k = self.rows_doc(op.get("rows") or None)
            if k is None:
                raise HudError("there is no rows file")
            root = [e for e in self.files[k]["doc"].root.elements() if e.name_lower == "minuirows"]
            for old in [r for r in (root[0].elements() if root else []) if r.name_lower == "row"
                        and (r.get("gadget") or "").lower() == str(op.get("gadget") or "").lower()]:
                uilayout.remove(old)
            return None
        raise HudError(f"unknown operation: {kind}")

    def undo(self):
        if not self.undo_stack:
            return False
        step = self.undo_stack.pop()
        for i, (before, _after) in step["files"].items():
            self._restore(int(i), before)
        self.redo_stack.append(step)
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        step = self.redo_stack.pop()
        for i, (_before, after) in step["files"].items():
            self._restore(int(i), after)
        self.undo_stack.append(step)
        return True

    def changes(self):
        """[{"stem", "lines": unified diff lines}] of every file that differs from the copy's."""
        import difflib
        out = []
        for f in self.files:
            now = f["doc"].data()
            if now == f["original"]:
                continue
            a = uilayout.decode(f["original"])[0].splitlines()
            b = f["doc"].text().splitlines()
            diff = list(difflib.unified_diff(a, b, f["stem"] + " (copy)", f["stem"] + " (edited)", n=1, lineterm=""))
            out.append({"stem": f["stem"], "where": f["where"], "lines": diff[:400], "more": max(0, len(diff) - 400)})
        return out

    def check(self, width=1024):
        """Findings of the edited files against the copy's own: [{"level", "code", "stem", "name",
        ...}]. Only what the edit brought is an error or a warning; what the copy already had is
        not repeated."""
        engine = [re.compile(g["re"], re.I) for g in table("engine_gadgets")["gadgets"]]
        found = []
        for i, f in enumerate(self.files):
            if f["doc"].data() == f["original"] or f.get("rows"):
                continue
            old = uilayout.parse(f["original"])
            old_names = [(g.get("name") or "") for g in old.gadgets()]
            new_gadgets = f["doc"].gadgets()
            new_names = [(g.get("name") or "") for g in new_gadgets]
            low_new = {n.lower() for n in new_names}
            for n in set(old_names):
                if n and any(r.search(n) for r in engine) and n.lower() not in low_new:
                    found.append({"level": "error", "code": "engine_gone", "stem": f["stem"], "name": n})
            counts_old = {}
            for n in old_names:
                counts_old[n.lower()] = counts_old.get(n.lower(), 0) + 1
            seen = {}
            for n in new_names:
                seen[n.lower()] = seen.get(n.lower(), 0) + 1
            for n, c in seen.items():
                if n and c > 1 and c > counts_old.get(n, 0):
                    found.append({"level": "warning", "code": "duplicate", "stem": f["stem"], "name": n})
            old_out = {(g.get("name") or "") for g in old.gadgets() if _outside(g)}
            for g in new_gadgets:
                n = g.get("name") or ""
                if _outside(g) and n not in old_out:
                    found.append({"level": "warning", "code": "outside", "stem": f["stem"], "name": n})
                if g.get("size1024") and uilayout.rect(g) is None:
                    found.append({"level": "error", "code": "bad_rect", "stem": f["stem"], "name": n})
                font = g.get("textfont")
                if font and uifonts.lookup(self.game.fonts, font, g.get("textfontsize") or "12", width) is None:
                    if not any((o.get("textfont") or "").lower() == font.lower() and (o.get("textfontsize") or "") == (g.get("textfontsize") or "")
                               for o in old.gadgets()):
                        found.append({"level": "warning", "code": "font_missing", "stem": f["stem"], "name": n,
                                      "font": f"{font} {g.get('textfontsize') or ''}"})
                for key in ("background", "foreground"):
                    path = g.get(key)
                    if path and self.texture_png(path) is None and not any(o.get(key) == path for o in old.gadgets()):
                        found.append({"level": "warning", "code": "texture_missing", "stem": f["stem"], "name": n, "path": path})
                for m in re.finditer(r"\$\$(\d+)\$\$", g.own_text() + (g.get("mouseovertext") or "")):
                    if int(m.group(1)) not in self.game.strings:
                        found.append({"level": "warning", "code": "string_missing", "stem": f["stem"], "name": n, "id": m.group(1)})
            twin = self.game.loose.get(f"{f['stem']}.xml.xmb".lower())
            if twin:
                found.append({"level": "warning", "code": "xmb_twin", "stem": f["stem"], "path": twin})
        k = self.rows_index
        rows = None
        if k is not None:
            try:
                rows = unitpanel.read_rows(self.files[k]["doc"].text())
            except ET.ParseError as e:
                found.append({"level": "error", "code": "rows_unreadable", "stem": "minuirows", "name": str(e)})
        if rows:
            names = {(e.get("name") or "").lower() for _i, e in self.gadgets()}
            for r in rows["rows"]:
                if r["gadget"].lower() not in names:
                    found.append({"level": "info", "code": "row_without_gadget", "stem": "minuirows", "name": r["gadget"]})
        return found

    def save(self, folder):
        """Writes the edited files into `folder` with the copy's structure (data\\<name>.xml, loose,
        even for a file that came from an archive) and a note of what they came from."""
        written = []
        for f in self.files:
            data = f["doc"].data()
            if data == f["original"]:
                continue
            path = os.path.join(folder, "data", "uhc", "minuirows.xml") if f.get("rows") else \
                os.path.join(folder, "data", f["stem"] + ".xml")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            written.append({"path": path, "from": f["where"], "sha256_copy": f["sha256"],
                            "sha256": hashlib.sha256(data).hexdigest()})
        if written:
            with open(os.path.join(folder, "hud-edits.json"), "w", encoding="utf-8") as fh:
                json.dump({"game": self.game.folder, "variant": self.variant, "files": written}, fh, indent=1)
        return written

    def texture_png(self, path):
        """(png bytes, where) of a texture, kept for the session; None when not found."""
        key = path.strip().replace("/", "\\").lower()
        if key not in self.pngs:
            hit = self.game.texture(path)
            self.pngs[key] = (painter.png_bytes(hit[0], level=1), hit[1]) if hit else None
        return self.pngs[key]


KNOWN_KEYS = _known_keys()
