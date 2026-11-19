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

from . import use_core

use_core()
import bar  # noqa: E402  (tools/)
from aoe3game import ddt, proto, uifonts, uilayout  # noqa: E402
from core import paint as painter  # noqa: E402
from fix_hitpointbar_tags import Art  # noqa: E402

MAIN = "uimainnew"
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


def scene_rules():
    with open(SCENE_RULES, encoding="utf-8") as fh:
        return json.load(fh)


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

    def font_file(self, face):
        """The bytes of a typeface's TrueType file of Fonts.bar, or None (a system font)."""
        self.fonts
        hit = self._ttf.get((face or "").lower())
        return _read(*hit) if hit else None

    def faces(self):
        self.fonts
        return sorted(name for name in self._ttf)

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

    def texture_png(self, path):
        """(png bytes, where) of a texture, kept for the session; None when not found."""
        key = path.strip().replace("/", "\\").lower()
        if key not in self.pngs:
            hit = self.game.texture(path)
            self.pngs[key] = (painter.png_bytes(hit[0], level=1), hit[1]) if hit else None
        return self.pngs[key]
