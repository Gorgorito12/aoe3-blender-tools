# SPDX-License-Identifier: GPL-3.0-or-later
"""The in-game interface's textures as pieces: which part of which texture each gadget draws, how
large it is on screen and when the game shows it. Pure Python (numpy for the coverage masks).

A *piece* is one rectangle of one texture: a gadget's `textureCoords` (`u1 v1 u2 v2`, normalised,
top-left origin) applied to its `background`, to each of its `stateEntry` textures and to its
`foreground` (as `tools/ui_preview.py` draws them), or the whole texture when the gadget has no
coordinates (a progress bar's background and mask, a tiled background). Gadgets that use the same
rectangle of the same texture share one piece; the piece lists every use.

    m = atlas_map(layouts, size_of, variant="min")   # layouts: [(stem, root node)], parsed by ui_preview
    for atlas in m.atlases.values():
        atlas.pieces, atlas.unused(), atlas.overlaps(), atlas.clusters()

The visibility rules (`Visibility`) are the ones the preview draws with: a gadget with `hidden`
waits for the engine to show it; the resource panel's skins (`...Eur|Asi|Nat` + `Min|Max`) show one
by the player's civ and the interface size; the moments and the choices of
`uidata/hud_scene.json`. They are measured on captures or marked to verify there.

The layout nodes are duck-typed: `.tag`, `.attrs` (lower-case names), `.children`, `.name`,
`.rect` (the `size1024` rectangle or None), as `tools/ui_preview.py`'s parser makes them.
"""
import json
import math
import os
import re

SKIN = re.compile(r"(Eur|Nat|Asi)(Min|Max)$")
CULTURES = ("Eur", "Asi", "Nat")
SCENE_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uidata", "hud_scene.json")
PIECE_NAMES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uidata", "ui_piece_names.json")
SCREEN = (1920, 1080)
STATE_NAMES = ("normal", "pressed", "mouse over", "disabled")
STRETCH_LIMIT = 1.10        # enlarged more than this on an axis: blurred on screen
DISTORT_LIMIT = 1.15        # one axis scaled this much more than the screen scales the layout: distorted


def art_key(path):
    """A texture path as the art folder keys it: lower case, backslashes, no art\\ and no extension."""
    p = path.strip().replace("/", "\\").strip("\\").lower()
    if p.startswith("art\\"):
        p = p[4:]
    return p[:-4] if p.endswith((".ddt", ".png")) else p


def _glob(patterns):
    parts = ["".join(".*" if ch == "*" else re.escape(ch) for ch in p) for p in patterns]
    return re.compile("^(" + "|".join(parts) + ")$", re.I)


def read_rules(path=SCENE_RULES):
    """hud_scene.json as read, or empty lists when it is missing."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {"moments": [], "oneOf": []}


def scene_rules(path=SCENE_RULES):
    """([(id, name pattern, shown)], [(regex, the one shown)]) of hud_scene.json, or empty lists."""
    rules = read_rules(path)
    moments = [(m["id"], _glob(m["names"]), bool(m.get("on"))) for m in rules.get("moments", [])]
    one_of = [(re.compile(o["re"]), o["show"]) for o in rules.get("oneOf", [])]
    return moments, one_of


class Visibility:
    """Whether the game shows a gadget, by its own name and attributes (a hidden parent hides its
    children: the caller walks the tree). `rules`: scene_rules()'s pair, read by default;
    `moments_on`: {moment id: shown} over the rules' defaults."""

    def __init__(self, rules=None, culture="Eur", variant="normal", show_hidden=False, moments_on=None):
        moments, one_of = rules if rules is not None else scene_rules()
        self.moment_rules = list(moments)
        self.moments = [(rx, (moments_on or {}).get(mid, on)) for mid, rx, on in moments]
        self.one_of = list(one_of)
        self.want = (culture, size_of_variant(variant))
        self.show_hidden = show_hidden

    def own_shown(self, n):
        if "hidden" in n.attrs and not self.show_hidden:
            return False
        m = SKIN.search(n.name)
        if m and (m.group(1), m.group(2)) != self.want:
            return False
        if any(rx.match(n.name) and not on for rx, on in self.moments):
            return False
        for rx, show in self.one_of:
            hit = rx.search(n.name)
            if hit and hit.group(1) != show:
                return False
        return True

    def conditions(self, n):
        """What decides whether the gadget shows, whatever the culture and moments chosen:
        [{"kind": "hidden"} | {"kind": "skin", "culture", "size"} | {"kind": "moment", "id", "on"} |
        {"kind": "choice", "value", "default"}]; empty: always (with its parents)."""
        out = []
        if "hidden" in n.attrs:
            out.append({"kind": "hidden"})
        m = SKIN.search(n.name)
        if m:
            out.append({"kind": "skin", "culture": m.group(1), "size": m.group(2)})
        for mid, rx, on in self.moment_rules:
            if rx.match(n.name):
                out.append({"kind": "moment", "id": mid, "on": on})
        for rx, show in self.one_of:
            hit = rx.search(n.name)
            if hit:
                out.append({"kind": "choice", "value": hit.group(1), "default": show})
        return out


def size_of_variant(variant):
    """The skin size a variant shows: Min for the minimised interface, Max for the normal one."""
    return "Min" if variant == "min" else "Max"


def describe(conds, moment_texts=None):
    """Plain words for a list of conditions (Visibility.conditions of a gadget and its parents)."""
    if not conds:
        return "always"
    words = []
    for c in conds:
        if c["kind"] == "hidden":
            w = "when the game shows it"
        elif c["kind"] == "skin":
            w = {"Eur": "European", "Asi": "Asian", "Nat": "Native"}[c["culture"]] + " resource panel skin"
        elif c["kind"] == "moment":
            w = (moment_texts or {}).get(c["id"], c["id"]).rstrip(".")
            w = w[:1].lower() + w[1:]
            w = ("usually shown: " if c["on"] else "") + w
        else:
            w = f"{c['value'].lower()} only"
        if w not in words:
            words.append(w)
    return "; ".join(words)


# --------------------------------------------------------------------------------------------------
# The layouts walked

def _gadget_walk(root):
    """[(node, [ancestor gadgets, outermost first])] of every gadget, in document order (the
    document's <layout> and other #-nodes are walked through, as ui_preview.gadgets does)."""
    out = []

    def walk(node, chain):
        for c in node.children:
            if c.tag != "gadget":
                if c.tag == "layout" or c.tag.startswith("#"):
                    walk(c, chain)
                continue
            out.append((c, chain))
            walk(c, chain + [c])
    walk(root, [])
    return out


def _uv(attrs):
    v = attrs.get("texturecoords")
    if not v:
        return None
    try:
        t = [float(x) for x in v.split()[:4]]
    except ValueError:
        return None
    return tuple(t) if len(t) == 4 else None


def _tile(attrs):
    return (("x" if "tilebackground" in attrs or "tilebackgroundhoriz" in attrs else "")
            + ("y" if "tilebackground" in attrs or "tilebackgroundvert" in attrs else ""))


def texture_uses(node):
    """[(role, texture path, uv or None, tile axes)] of a gadget: its background, each stateEntry's
    texture, a progress bar's background and mask (whole), its foreground. The gadget's
    textureCoords crop the background, the states and the foreground (a tiled background without
    coordinates repeats the whole texture)."""
    a = node.attrs
    uv, tile = _uv(a), _tile(a)
    tile = "" if uv is not None else tile
    out = []
    if a.get("background"):
        out.append(("background", a["background"], uv, tile))
    states = [c for c in node.children if c.tag == "stateentry"]
    for k, s in enumerate(states):
        p = s.attrs.get("background") or s.attrs.get("foreground")
        if p:
            out.append((f"state {k}", p, uv, tile))
    if (a.get("type") or "").lower() == "progressbar":
        for k, role in (("progressbarbackground", "bar background"), ("progressbarmask", "bar fill")):
            if a.get(k):
                out.append((role, a[k], None, ""))
    if a.get("foreground"):
        out.append(("foreground", a["foreground"], uv, tile))
    return out


# --------------------------------------------------------------------------------------------------
# Plain names

_NAMES = None


def piece_names(path=PIECE_NAMES):
    """[(regex, English words)] of uidata/ui_piece_names.json, read once."""
    global _NAMES
    if _NAMES is None or path != PIECE_NAMES:
        try:
            with open(path, encoding="utf-8") as fh:
                table = json.load(fh)
        except OSError:
            table = {"names": []}
        names = [(re.compile(e["re"], re.I), e["en"]) for e in table.get("names", [])]
        if path != PIECE_NAMES:
            return names
        _NAMES = names
    return _NAMES


def plain_name(gadget, role="background"):
    """A gadget's part in plain words ("Minimap frame"), with the state or bar part it draws."""
    name = None
    for rx, words in piece_names():
        m = rx.search(gadget)
        if m:
            name = m.expand(words) if "\\" in words else words
            break
    if name is None:
        base = gadget.split("-")[-1] if "-" in gadget else gadget
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).strip() or gadget
        name = name[:1].upper() + name[1:]
    if role.startswith("state "):
        k = int(role.split()[1])
        name += ", " + (STATE_NAMES[k] if k < len(STATE_NAMES) else f"state {k}")
    elif role in ("bar background", "bar fill"):
        name += ", " + ("frame" if role == "bar background" else "fill")
    elif role == "foreground":
        name += ", front"
    return name


# --------------------------------------------------------------------------------------------------
# The map

class Use:
    """One gadget drawing one piece."""

    def __init__(self, stem, gadget, role, rect1024, screen_size, stretch, conds, tile, aspect=1.0):
        self.stem, self.gadget, self.role = stem, gadget, role
        self.rect1024 = rect1024                  # (x1, y1, x2, y2) in the 1024 x 768 layout space
        self.screen_size = screen_size            # (w, h) in pixels at the map's screen size
        self.stretch = stretch                    # (sx, sy): screen pixels per texture pixel
        self.conds = conds
        self.tile = tile
        self.aspect = aspect                      # how much wider than high the screen scales the layout

    @property
    def name(self):
        return plain_name(self.gadget, self.role)


class Piece:
    def __init__(self, atlas, uv, size):
        self.atlas = atlas                        # art key of the texture
        self.uv = uv                              # (u1, v1, u2, v2) as written (a flip has u1 > u2)
        w, h = size
        u1, v1, u2, v2 = uv
        self.flip = (u1 > u2, v1 > v2)
        lo_u, hi_u, lo_v, hi_v = min(u1, u2), max(u1, u2), min(v1, v2), max(v1, v2)
        self.rect_f = (lo_u * w, lo_v * h, hi_u * w, hi_v * h)          # texture pixels, exact
        x0 = max(0, min(w, int(math.floor(lo_u * w + 1e-6))))
        y0 = max(0, min(h, int(math.floor(lo_v * h + 1e-6))))
        x1 = max(0, min(w, int(math.ceil(hi_u * w - 1e-6))))
        y1 = max(0, min(h, int(math.ceil(hi_v * h - 1e-6))))
        self.rect = (x0, y0, max(x1, x0), max(y1, y0))                  # the pixels it touches
        self.uses = []
        self.number = 0

    @property
    def size(self):
        return self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]

    @property
    def name(self):
        return self.uses[0].name if self.uses else self.atlas

    @property
    def gadgets(self):
        out = []
        for u in self.uses:
            if u.gadget not in out:
                out.append(u.gadget)
        return out

    def gadget_text(self, most=2):
        g = self.gadgets
        text = ", ".join(g[:most])
        return text + (f" +{len(g) - most}" if len(g) > most else "")

    @property
    def tiled(self):
        return any(u.tile for u in self.uses)

    def stretch_range(self):
        """((min sx, max sx), (min sy, max sy)) over its stretched (not tiled) uses, or None."""
        st = [u.stretch for u in self.uses if not u.tile and u.stretch]
        if not st:
            return None
        return (min(s[0] for s in st), max(s[0] for s in st)), (min(s[1] for s in st), max(s[1] for s in st))

    @property
    def enlarged(self):
        """Drawn larger than its pixels by more than STRETCH_LIMIT on an axis: blurred on screen."""
        return any(max(u.stretch) > STRETCH_LIMIT for u in self.uses if u.stretch and not u.tile)

    @property
    def uneven(self):
        """Scaled on one axis more than DISTORT_LIMIT times the other, beyond what the screen does
        to the whole 1024 x 768 layout (a 16:9 screen widens every gadget by 4:3)."""
        for u in self.uses:
            if u.tile or not u.stretch:
                continue
            k = (u.stretch[0] / max(1e-6, u.stretch[1])) / u.aspect
            if max(k, 1 / max(k, 1e-6)) > DISTORT_LIMIT:
                return True
        return False

    @property
    def stretched(self):
        return self.enlarged or self.uneven

    def when(self, moment_texts=None):
        """Plain words for when the game shows it: the most shown of its uses."""
        texts = []
        for u in self.uses:
            t = describe(u.conds, moment_texts)
            if t == "always":
                return t
            if t not in texts:
                texts.append(t)
        return " | ".join(texts)

    def public(self, moment_texts=None):
        st = self.stretch_range()
        return {"number": self.number, "name": self.name, "atlas": self.atlas, "uv": list(self.uv),
                "rect": list(self.rect), "rect_exact": [round(v, 3) for v in self.rect_f], "flip": list(self.flip),
                "tiled": self.tiled, "stretched": self.stretched, "enlarged": self.enlarged, "uneven": self.uneven,
                "stretch": None if st is None else [[round(v, 3) for v in st[0]], [round(v, 3) for v in st[1]]],
                "when": self.when(moment_texts),
                "uses": [{"file": u.stem, "gadget": u.gadget, "role": u.role, "name": u.name,
                          "rect1024": list(u.rect1024), "screen": [round(v, 1) for v in u.screen_size],
                          "stretch": [round(v, 3) for v in u.stretch] if u.stretch else None,
                          "tile": u.tile, "when": describe(u.conds, moment_texts)} for u in self.uses]}


class Atlas:
    def __init__(self, key, width, height):
        self.key, self.width, self.height = key, width, height
        self.pieces = []

    @property
    def base(self):
        return self.key.split("\\")[-1]

    def coverage(self):
        """H x W uint16: how many pieces cover each pixel."""
        import numpy as np
        c = np.zeros((self.height, self.width), np.uint16)
        for p in self.pieces:
            x0, y0, x1, y1 = p.rect
            c[y0:y1, x0:x1] += 1
        return c

    def unused(self):
        """H x W bool: the pixels no piece uses (in the map's interface variant)."""
        return self.coverage() == 0

    def overlaps(self):
        """[(i, j)] of the pieces (indices in self.pieces) whose pixels overlap."""
        out = []
        for i, a in enumerate(self.pieces):
            for j in range(i + 1, len(self.pieces)):
                b = self.pieces[j]
                if (min(a.rect[2], b.rect[2]) > max(a.rect[0], b.rect[0])
                        and min(a.rect[3], b.rect[3]) > max(a.rect[1], b.rect[1])):
                    out.append((i, j))
        return out

    def clusters(self):
        """[[piece indices]] of pieces that overlap, directly or through others (each piece alone
        when it overlaps none), in the order of their first piece."""
        parent = list(range(len(self.pieces)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, j in self.overlaps():
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)
        groups = {}
        for i in range(len(self.pieces)):
            groups.setdefault(find(i), []).append(i)
        return [groups[k] for k in sorted(groups)]

    def public(self, moment_texts=None):
        unused = self.unused()
        return {"atlas": self.key, "size": [self.width, self.height],
                "unused_fraction": round(float(unused.mean()), 4) if unused.size else 0.0,
                "overlaps": [[self.pieces[i].number, self.pieces[j].number] for i, j in self.overlaps()],
                "pieces": [p.public(moment_texts) for p in self.pieces]}


class UiMap:
    def __init__(self, variant, screen):
        self.variant, self.screen = variant, screen
        self.atlases = {}
        self.missing = set()          # textures named under the prefix that were not found
        self.moment_texts = {}

    def pieces(self):
        return [p for a in self.atlases.values() for p in a.pieces]

    def public(self):
        return {"variant": self.variant, "screen": list(self.screen), "missing": sorted(self.missing),
                "atlases": [a.public(self.moment_texts) for a in self.atlases.values()]}


def atlas_map(layouts, size_of, variant="min", screen=SCREEN, prefix="ui\\ingame\\", rules_path=SCENE_RULES):
    """The textures under `prefix` that the layouts draw, as pieces (UiMap).

    layouts: [(stem, root node)] in the game's order; size_of(art key) -> (width, height) or None;
    variant: "min" or "normal" (a resource panel skin of the other size never shows, so it is left
    out); screen: the screen size the on-screen sizes and stretch factors are given for.

    Atlases are in name order, pieces in each from top to bottom then left to right, numbered
    through all the atlases from 1."""
    rules = read_rules(rules_path)
    vis = Visibility(scene_rules(rules_path), variant=variant)
    want = size_of_variant(variant)
    m = UiMap(variant, screen)
    m.moment_texts = {mm["id"]: mm.get("en", mm["id"]) for mm in rules.get("moments", [])}
    sx, sy = screen[0] / 1024.0, screen[1] / 768.0
    aspect = sx / sy
    found = {}
    prefix = art_key(prefix + "x")[:-1]
    for stem, root in layouts:
        for node, chain in _gadget_walk(root):
            uses = [u for u in texture_uses(node) if art_key(u[1]).startswith(prefix)]
            if not uses or node.rect is None:
                continue
            conds = [c for g in chain + [node] for c in vis.conditions(g)]
            if any(c["kind"] == "skin" and c["size"] != want for c in conds):
                continue
            r = node.rect
            sw, sh = (r[2] - r[0]) * sx, (r[3] - r[1]) * sy
            for role, path, uv, tile in uses:
                key = art_key(path)
                if key not in found:
                    found[key] = size_of(key)
                size = found[key]
                if size is None:
                    m.missing.add(key)
                    continue
                if key not in m.atlases:
                    m.atlases[key] = Atlas(key, size[0], size[1])
                atlas = m.atlases[key]
                uv_ = uv if uv is not None else (0.0, 0.0, 1.0, 1.0)
                ident = tuple(round(v, 5) for v in uv_)
                piece = next((p for p in atlas.pieces if tuple(round(v, 5) for v in p.uv) == ident), None)
                if piece is None:
                    piece = Piece(key, uv_, size)
                    atlas.pieces.append(piece)
                pw, ph = piece.rect_f[2] - piece.rect_f[0], piece.rect_f[3] - piece.rect_f[1]
                stretch = (sw / pw, sh / ph) if pw > 0 and ph > 0 and not tile else None
                use = Use(stem, node.name, role, r, (sw, sh), stretch, conds, tile, aspect)
                use.node, use.chain = node, chain          # the layout nodes, for a caller that draws them
                piece.uses.append(use)
    m.atlases = {k: m.atlases[k] for k in sorted(m.atlases)}
    n = 0
    for a in m.atlases.values():
        a.pieces.sort(key=lambda p: (p.rect[1], p.rect[0], p.rect[3], p.rect[2]))
        for p in a.pieces:
            n += 1
            p.number = n
    return m
