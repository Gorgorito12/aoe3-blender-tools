# SPDX-License-Identifier: GPL-3.0-or-later
"""The unit panels as the game fills them for one unit: what each gadget the game fills by name
says and whether it shows, the rows the UHC DLL's minUIStats adds (data\\uhc\\minuirows.xml), and
what exists but this unit does not show, with why.

A model, not the game: it reads the unit's block of protoy.xml, its tactics file, the Startup
.cfg keys and the rows file, and applies the rules measured on the stock exe (the unit panels'
research, 2026-11-17) and those of the DLL's feature. What the game changes as it plays (techs,
auras, snares, a villager's load) is not known offline: such a value is the proto's and is marked
"base", one set by hand is "simulated", one whose rule is not proven "to verify". Standard
library only.
"""
import json
import os
import re
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
YELLOW, CYAN, WHITE = [255, 255, 0], [0, 255, 255], [255, 255, 255]   # measured on a capture
PLAYER_COLOURS = [[45, 45, 245], [210, 40, 40], [240, 220, 40], [60, 200, 220], [170, 60, 210],
                  [250, 140, 40], [60, 200, 60], [255, 120, 180]]       # player 1 measured; the rest stock defaults
LABELS = {"hitpoints": 24320, "speed": 24323, "resists": 35758, "los": 24324, "range": 18417}
DAMAGE_ICON = {"hand": r"ui\ingame\stat_icon_attack", "ranged": r"ui\ingame\stat_icon_ranged",
               "siege": r"ui\ingame\stat_icon_siege"}           # the exe's own, by damage type: to verify
RANGE_ICON = r"ui\ingame\stat_icon_range"
MIN_ATTACK_ROWS = 3                                             # the minimised panel's StackLabel0..2


def icon(path, size=16):
    return f'<icon="({size})({path})">'


def number(v):
    """The panels' numbers: a whole value without decimals, else two decimals."""
    return str(int(v)) if abs(v - round(v)) < 1e-6 else f"{v:.2f}"


def table(name):
    with open(os.path.join(HERE, "uidata", name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------------------------------
# Reading

def _f(el, tag, default=0.0):
    t = el.findtext(tag) if el is not None else None
    try:
        return float(t) if t is not None else default
    except ValueError:
        return default


def read_unit(block):
    """The data the panels show of one <Unit> block of protoy.xml (its text)."""
    root = ET.fromstring(block)
    u = {"name": root.get("name") or root.get("Name") or "", "id": root.get("id"),
         "display": int(_f(root, "DisplayNameID", -1)), "types": [t.text for t in root.findall("UnitType") if t.text],
         "flags": [t.text for t in root.findall("Flag") if t.text],
         "hp": _f(root, "MaxHitpoints"), "hp_initial": _f(root, "InitialHitpoints"), "los": _f(root, "LOS"),
         "speed": _f(root, "MaxVelocity"), "train": _f(root, "TrainPoints"), "build": _f(root, "BuildPoints"),
         "work_rate": _f(root, "BuildingWorkRate"), "bounty": _f(root, "Bounty"), "pop": _f(root, "PopulationCount"),
         "limit": int(_f(root, "BuildLimit")), "contain": int(_f(root, "MaxContained")), "lifespan": _f(root, "Lifespan"),
         "tactics": (root.findtext("Tactics") or "").strip(), "portrait": (root.findtext("PortraitIcon") or "").strip(),
         "icon": (root.findtext("Icon") or "").strip()}
    u["cost"] = [[c.get("resourcetype") or "", float(c.text or 0)] for c in root.findall("Cost")]
    armor = root.find("Armor")
    u["armor"] = [(a.get("type") or "Hand", float(a.get("value") or 0)) for a in root.findall("Armor")]
    u["armor_value"] = float(armor.get("value") or 0) if armor is not None else 0.0
    u["armor_type"] = (armor.get("type") or "Hand").lower() if armor is not None else "hand"
    res = root.find("InitialResource")
    u["resource"] = [res.get("type") or "", float(res.text or 0)] if res is not None else None
    u["actions"] = {}
    for a in root.findall("ProtoAction"):
        name = (a.findtext("Name") or "").strip()
        u["actions"][name.lower()] = {
            "name": name, "damage": _f(a, "Damage", None), "type": (a.findtext("DamageType") or "").strip().lower(),
            "maxrange": _f(a, "MaxRange", None), "minrange": _f(a, "MinRange", None), "rof": _f(a, "ROF", None),
            "area": _f(a, "DamageArea", None),
            "bonuses": [[b.get("type") or "", float(b.text or 0)] for b in a.findall("DamageBonus")],
            "rates": [[r.get("type") or "", float(r.text or 0)] for r in a.findall("Rate")]}
    return u


def read_tactics(text):
    """{"tactics": [{"name", "actions": [name]}], "actions": {lower name: {...}}} of a tactics file."""
    root = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", text.strip()))
    actions = {}
    for a in root.findall("action"):
        n = a.find("name")
        if n is None or not (n.text or "").strip():
            continue
        name = n.text.strip()
        actions[name.lower()] = {
            "name": name, "label": int(n.get("stringid")) if (n.get("stringid") or "").isdigit() else None,
            "type": (a.findtext("type") or "").strip().lower(), "attack": (a.findtext("attackaction") or "").strip() == "1",
            "active": (a.findtext("active") or "").strip() != "0", "damage": _f(a, "damage", None),
            "maxrange": _f(a, "maxrange", None), "minrange": _f(a, "minrange", None), "rof": _f(a, "rof", None)}
    tactics = []
    for t in root.findall("tactic"):
        listed = []
        for a in t.findall("action"):
            prio = a.get("priority")
            listed.append(((a.text or "").strip(), float(prio) if prio else None))
        tactics.append({"name": (t.text or "").strip(), "actions": listed})
    return {"tactics": tactics, "actions": actions}


def read_cfg(texts):
    """{lower key: [arguments]} of Startup .cfg files' text (a line: key followed by its arguments;
    // comments and lines starting with + or - are read as the key itself)."""
    keys = {}
    for text in texts:
        for line in text.splitlines():
            line = line.split("//", 1)[0].strip()
            if not line or line.startswith(("#", ";")):
                continue
            parts = line.lstrip("+").split()
            if parts:
                keys[parts[0].lower()] = parts[1:]
    return keys


def read_rows(text):
    """The rows of a minuirows.xml: [{"gadget", "items": [[label, item]], "parts": [...], "types"}]
    and the bigPanelRows entry."""
    root = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", text.strip()))
    rows, big = [], None
    for r in root:
        tag = r.tag.lower()
        if tag == "row":
            types = [t.strip() for t in (r.get("types") or "").split(",") if t.strip()]
            if r.get("text"):
                parts = r.get("text").split("|")
            else:
                parts = [(r.get("label") or "") + "{" + (r.get("item") or "") + "}"]
            rows.append({"gadget": r.get("gadget") or "", "parts": parts, "types": types,
                         "items": sorted({m for p in parts for m in re.findall(r"\{(\w+)\}", p)})})
        elif tag == "bigpanelrows":
            big = {"gadget": r.get("gadget") or "", "first": int(r.get("first") or 0),
                   "skip": [s.strip() for s in (r.get("skip") or "").split(",") if s.strip()]}
    return {"rows": rows, "big": big}


# --------------------------------------------------------------------------------------------------
# The unit's attacks, as the panels list them

def attacks(unit, tactics):
    """The attacks of the unit's first tactic (the one a unit starts in; to verify for units whose
    first tactic is not their default), in priority order, without the actions the tactics file
    switches off (active 0); only those with damage are kept, as the stat panel's fill does.
    Damage, range and rate of fire are the proto's (its ProtoAction of the same name), else the
    tactic's."""
    if not tactics or not tactics["tactics"]:
        listed = [(a["name"], None) for a in unit["actions"].values()]
        acts = {}
    else:
        listed = tactics["tactics"][0]["actions"]
        acts = tactics["actions"]
    order = sorted(enumerate(listed), key=lambda x: (-(x[1][1] if x[1][1] is not None else -1e9), x[0]))
    out = []
    for _i, (name, _p) in order:
        t = acts.get(name.lower(), {})
        p = unit["actions"].get(name.lower(), {})
        if t and (not t.get("attack") or not t.get("active", True)):
            continue
        damage = p.get("damage") if p.get("damage") is not None else t.get("damage")
        if not damage:
            continue
        out.append({"name": name, "label": t.get("label"), "damage": damage, "type": p.get("type") or "hand",
                    "maxrange": p.get("maxrange") if p.get("maxrange") is not None else t.get("maxrange"),
                    "minrange": p.get("minrange") if p.get("minrange") is not None else t.get("minrange"),
                    "rof": p.get("rof") if p.get("rof") is not None else t.get("rof"),
                    "area": p.get("area"), "bonuses": p.get("bonuses") or []})
    return out


def attack_row(a, strings, type_icons):
    """'Ranged ATK: 23 (icon), 12 (range icon), 3x (target icon)' as the panels write it."""
    label = strings.get(a["label"], (a["name"], None))[0] if a.get("label") else a["name"]
    text = f"{label}: {number(a['damage'])} {icon(DAMAGE_ICON.get(a['type'], DAMAGE_ICON['hand']))}"
    if a["type"] != "hand" and a.get("maxrange"):
        text += f", {number(a['maxrange'])} {icon(RANGE_ICON)}"
    if a["bonuses"]:
        target, mult = a["bonuses"][0]
        path = type_icons.get(target.lower())
        text += f", {number(mult)}x" + (f" {icon(path)}" if path else f" ({target})")
    return text


# --------------------------------------------------------------------------------------------------
# The simulation

STATE_DEFAULTS = {"hp": None, "hp_bonus": 0, "overheal": 0, "garrison": 0, "poison": False, "construction": None,
                  "building": False, "gathering": False, "lifespan": None, "veterancy": False, "aura": False,
                  "regen": 0, "player": 1, "civ": ""}


def simulate(unit, attack_list, *, variant, gadgets, strings, keys, rows=None, dll=True, state=None,
             types_index=None):
    """What the panels show for this unit. `gadgets`: {lower name: {"parent": lower name or None,
    "hidden": bool}} of the scene's layouts; `strings`: {id: (text, symbol)}; `keys`: read_cfg's
    (with any switched on by hand); `rows`: read_rows' or None; `dll`: whether uhc.dll is there.

    Returns {"gadgets": {lower name: {...}}, "live": {fn: text}, "rows": [...], "absent": [...]}."""
    st = dict(STATE_DEFAULTS, **(state or {}))
    s = lambda k, fb="": strings.get(k, (fb, None))[0]                 # noqa: E731
    types = {t.lower() for t in unit["types"]}
    is_unit = "unit" in types
    hp_max = unit["hp"] + float(st["hp_bonus"] or 0)
    hp_now = float(st["hp"]) if st["hp"] not in (None, "") else hp_max + float(st["overheal"] or 0)
    type_icons = {}
    args = keys.get("attacktypeicons", [])
    for k in range(0, len(args) - 2, 3):
        type_icons[args[k].lower()] = args[k + 2]
    out, absent, rows_out = {}, [], []

    def put(name, text=None, show=True, colour=None, exact="exact", background=None, why=None, fraction=None):
        if name.lower() in gadgets:
            out[name.lower()] = {"text": text, "show": show, "colour": colour, "exact": exact,
                                 "background": background, "why": why, "fraction": fraction}

    def lack(item, kind, code, enable=None, **vars):
        absent.append({"item": item, "kind": kind, "code": code, "vars": vars, "enable": enable})

    # -- the selection panel (both variants: the game fills these by name)
    name = s(unit["display"], unit["name"]) if unit["display"] >= 0 else unit["name"]
    put("unitselectionpanel-unitTypeName", name, colour=WHITE)
    player = int(st["player"] or 1)
    put("unitselectionpanel-unitPlayerName", f"Player {player}" + (f" ({st['civ']})" if st["civ"] else ""),
        colour=PLAYER_COLOURS[(player - 1) % len(PLAYER_COLOURS)])
    put("unitselectionpanel-unitHitPointsLabel", s(LABELS["hitpoints"], "Hitpoints:"), colour=YELLOW)
    hp_text = f"{int(hp_now)}/{int(hp_max)}"
    if st["hp_bonus"]:
        hp_text += f" ({int(unit['hp'])}+{int(st['hp_bonus'])})"
    put("unitselectionpanel-unitHitPointsValue", hp_text, colour=WHITE,
        exact="simulated" if st["hp"] not in (None, "") or st["hp_bonus"] or st["overheal"] else "exact")
    resists = is_unit and unit["armor_value"] > 0
    if resists:
        put("unitselectionpanel-unitResistsLabel", s(LABELS["resists"], "Resists:"), colour=YELLOW)
        put("unitselectionpanel-unitResistsValue",
            f"{number(unit['armor_value'])} {icon(DAMAGE_ICON.get(unit['armor_type'], DAMAGE_ICON['hand']))}", colour=WHITE)
    else:
        why = "not_unit" if not is_unit else "no_data"
        for g in ("unitselectionpanel-unitResistsLabel", "unitselectionpanel-unitResistsValue"):
            put(g, show=False, why=why)
        lack("resists", "stock", why, armor=number(unit["armor_value"]))
    holds = unit["resource"] is not None and unit["resource"][1] > 0
    if holds:
        put("unitselectionpanel-unitResourceLabel", f"{unit['resource'][0]}:", colour=YELLOW)
        put("unitselectionpanel-unitResourceValue", f"{int(unit['resource'][1])}/{int(unit['resource'][1])}", colour=WHITE)
    else:
        for g in ("unitselectionpanel-unitResourceLabel", "unitselectionpanel-unitResourceValue"):
            put(g, show=False, why="no_data")
    for g in ("unitselectionpanel-unitResourceRateLabel", "unitselectionpanel-unitResourceRateValue"):
        put(g, show=False, why="no_data")
    share = hp_now / hp_max if hp_max else 1
    bar = "Green" if share > 2 / 3 else "Yellow" if share > 1 / 3 else "Red"     # thresholds: to verify
    for colour in ("Red", "Yellow", "Green"):
        put(f"unitselectionpanel-unitHealthBar{colour}", show=colour == bar, why=None if colour == bar else "one_of",
            exact="toverify", fraction=max(0.0, min(1.0, share)))
    if unit["portrait"]:
        put("unitselectionpanel-unitPortrait", background=unit["portrait"])

    # -- attack rows: the minimised panel's StackLabel0..2, the big panel's rows
    rows_text = [attack_row(a, strings, type_icons) for a in attack_list]
    if variant == "min":
        room = MIN_ATTACK_ROWS - (1 if holds else 0)
        for k in range(MIN_ATTACK_ROWS):
            if k < min(room, len(rows_text)):
                put(f"unitselectionpanel-StackLabel{k}", rows_text[k], colour=CYAN)
            else:
                put(f"unitselectionpanel-StackLabel{k}", show=False, why="no_data")
        for k, text in enumerate(rows_text[room:]):
            lack(f"attack {room + k + 1}", "stock", "no_room", row=text.split(":")[0], MIN=room)
        lack("speed", "stock", "ui_variant")
        lack("gatherers", "stock", "ui_variant")
    else:
        big = [(f"{name}", f"Player {player}" + (f" ({st['civ']})" if st["civ"] else ""))]
        big.append((s(LABELS["hitpoints"], "Hitpoints:"), hp_text))
        if is_unit and unit["speed"] > 0:
            big.append((s(LABELS["speed"], "Speed:"), f"{unit['speed']:.2f}"))
        else:
            lack("speed", "stock", "not_unit" if not is_unit else "no_data")
        if resists:
            big.append((s(LABELS["resists"], "Resists:"), number(unit["armor_value"])))
        for text in rows_text:
            label, _, value = text.partition(": ")
            big.append((label + ":", value))
        for k in range(9):
            if k < len(big):
                put(f"unitstatpanel3-StackLabel{k}", big[k][0], colour=YELLOW if k else WHITE)
                put(f"unitstatpanel3-StackValue{k}", big[k][1], colour=WHITE)
            else:
                put(f"unitstatpanel3-StackLabel{k}", show=False, why="no_data")
                put(f"unitstatpanel3-StackValue{k}", show=False, why="no_data")
        for k in range(9, len(big)):
            lack(f"row {k + 1}", "stock", "no_room", row=big[k][0])

    # -- the live texts a layout may hold
    live = {"currentunithp": str(int(hp_now)), "currentunitmaximumhp": str(int(hp_max)),
            "currentunitlos": str(int(unit["los"])), "currentunittrainpoints": number(unit["train"]),
            "currentunitbuildpoints": number(unit["build"]), "currentunitbuildingworkrate": number(unit["work_rate"]),
            "currentunitmaxvelocity": str(int(unit["speed"])), "currentunitmaxvelocityfloat": f"{unit['speed']:.2f}",
            "currentunitcapacity": f"{int(st['garrison'] or 0)} / {unit['contain']}", "currentunitname": name,
            "currentunitattack": number(attack_list[0]["damage"]) if attack_list else "0"}
    for fn in table("ui_functions")["functions"]:
        if not fn["works"]:
            live[fn["name"].lower()] = ""

    # -- the DLL's rows
    catalog = {i["item"].lower(): i for i in table("uhc_minui_items")["items"]}
    key_on = dll and "minuistats" in keys
    values = {}

    def value(item):
        """(text or None, code when None)."""
        it = catalog.get(item.lower())
        if it is None:
            return None, "unknown_item"
        for need in it.get("needs", []):
            if need.lower() not in keys and not it.get("needsAny"):
                return None, "key_off"
        if it.get("needsAny") and not any(n.lower() in keys for n in it["needs"]):
            return None, "key_off"
        if it.get("typesInKey"):
            listed = {a.lower() for a in keys.get(it["typesInKey"].lower(), []) if "=" not in a}
            if listed and not (listed & types) and unit["name"].lower() not in listed:
                return None, "type_not_in_key"
        i = item.lower()
        attacks_ = attack_list
        if i == "hitpoints":
            return f"{int(hp_now)}/{int(hp_max)}", None
        if i in ("speed", "basespeed"):
            return (number(unit["speed"]), None) if unit["speed"] > 0 else (None, "no_data")
        if i == "los":
            return (str(int(unit["los"])), None) if unit["los"] > 0 else (None, "no_data")
        if i in ("armor", "armorvalue"):
            if unit["armor_value"] <= 0:
                return None, "no_data"
            t = number(unit["armor_value"])
            return (t + (" " + icon(DAMAGE_ICON.get(unit["armor_type"], DAMAGE_ICON["hand"])) if i == "armor" else "")), None
        if i == "garrison":
            return (f"{int(st['garrison'] or 0)} / {unit['contain']}", None) if unit["contain"] > 0 else (None, "no_data")
        if i == "trainpoints":
            return (number(unit["train"]), None) if unit["train"] > 0 else (None, "no_data")
        if i == "buildpoints":
            return (number(unit["build"]), None) if unit["build"] > 0 else (None, "no_data")
        if i in ("rof", "range", "minrange", "area"):
            seen, parts = [], []
            for a in attacks_:
                v = {"rof": a.get("rof"), "range": a.get("maxrange") if a["type"] != "hand" else None,
                     "minrange": a.get("minrange"), "area": a.get("area")}[i]
                if v and not any(abs(v - x) < 0.01 for x in seen):
                    seen.append(v)
                    parts.append(f"{number(v)} {icon(DAMAGE_ICON.get(a['type'], DAMAGE_ICON['hand']))}")
            return ("  ".join(parts), None) if parts else (None, "no_data")
        if i == "cost":
            parts = [f"{int(v + 0.5)} {icon('ui' + chr(92) + 'ingame' + chr(92) + 'resource_' + r.lower())}"
                     for r, v in unit["cost"] if v > 0]
            return ("  ".join(parts), None) if parts else (None, "no_data")
        if i == "population":
            return (number(unit["pop"]), None) if unit["pop"] > 0 else (None, "no_data")
        if i == "bounty":
            return (number(unit["bounty"]), None) if unit["bounty"] > 0 else (None, "no_data")
        if i == "buildlimit":
            return (str(unit["limit"]), None) if unit["limit"] > 0 else (None, "no_data")
        if i == "inventory":
            return (f"{int(unit['resource'][1])}/{int(unit['resource'][1])}", None) if holds else (None, "no_data")
        if i == "lifespan":
            if unit["lifespan"] <= 0 and not st["lifespan"]:
                return None, "no_data"
            return (f"{int(st['lifespan'] or unit['lifespan'])} s", None)
        if i == "overheal":
            above = hp_now - unit["hp_initial"]
            return (f"+{int(above)}", None) if above >= 1 else (None, "needs_state")
        if i in ("veterancy", "poison", "gatherrate", "auras"):
            flag = {"veterancy": "veterancy", "poison": "poison", "gatherrate": "gathering", "auras": "aura"}[i]
            return (("Rank 1" if i == "veterancy" else "5/s, 10 s" if i == "poison" else "0.84/s" if i == "gatherrate"
                     else "+25% work"), None) if st[flag] else (None, "needs_state")
        if i in ("randomcost", "shipments"):
            return None, "live_only"
        if i in ("buildtime", "buildprogress"):
            if st["construction"] in (None, "") or unit["build"] <= 0:
                return None, "needs_state" if unit["build"] > 0 else "no_data"
            done = float(st["construction"])
            left = unit["build"] * (1 - done / 100)
            return ((f"{int(left) // 60}:{int(left) % 60:02d}", None) if i == "buildtime" else (f"{int(done)}%", None))
        if i == "buildrate":
            return ("1.00", None) if st["building"] else (None, "needs_state")
        if i == "regen":
            return (number(float(st["regen"])), None) if st["regen"] else (None, "needs_state")
        return None, "unknown_item"

    for item in catalog:
        values[item] = value(item)
    # every row of the rows file: what it shows, or why not
    placed = {}                                  # item -> [row gadget] that place it
    shown_items = set()
    for r in (rows or {"rows": []})["rows"]:
        g = r["gadget"].lower()
        for i in r["items"]:
            placed.setdefault(i.lower(), []).append(r["gadget"])
        why = None
        if g not in gadgets:
            why = "gadget_missing"
        elif not dll:
            why = "dll_absent"
        elif not key_on:
            why = "key_off"
        elif r["types"] and not ({t.lower() for t in r["types"]} & (types | {unit["name"].lower()})):
            why = "type_filter"
        if why:
            if g in gadgets:
                put(r["gadget"], show=False, why=why)
            rows_out.append({"gadget": r["gadget"], "text": None, "why": why, "types": r["types"]})
            continue
        shown = []
        for part in r["parts"]:
            items = re.findall(r"\{(\w+)\}", part)
            vals = [values.get(i.lower(), (None, "unknown_item")) for i in items]
            if all(v[0] for v in vals):
                text = part
                for i, v in zip(items, vals):
                    text = text.replace("{" + i + "}", v[0])
                shown.append(text)
                shown_items.update(i.lower() for i in items)
        text = "   ".join(shown)
        put(r["gadget"], text or None, show=bool(text), colour=WHITE, exact="simulated",
            why=None if text else "no_data")
        rows_out.append({"gadget": r["gadget"], "text": text, "why": None if text else "no_data", "types": r["types"]})
    # each item of the DLL this unit does not show, with every reason, each with a way to see it
    rows_by_gadget = {x["gadget"].lower(): x for x in rows_out}
    for key, it in catalog.items():
        if key in shown_items:
            continue
        reasons = []
        if not dll:
            reasons.append({"code": "dll_absent"})
        elif not key_on:
            reasons.append({"code": "key_off", "key": catalog_key(), "enable": {"keys": [catalog_key()]}})
        if rows is None:
            reasons.append({"code": "no_rows_file"})
        elif key not in placed:
            reasons.append({"code": "not_placed", "ref": it["ref"], "enable": {"row": it["item"]}})
        else:
            for gname in placed[key]:
                row = rows_by_gadget.get(gname.lower(), {})
                if row.get("why") == "gadget_missing":
                    reasons.append({"code": "gadget_missing", "gadget": gname, "enable": {"gadget": gname}})
                elif row.get("why") == "type_filter":
                    reasons.append({"code": "type_filter", "gadget": gname, "types": ", ".join(row.get("types") or [])})
                else:
                    parent = (gadgets.get(gname.lower()) or {}).get("parent")
                    if parent and (gadgets.get(parent) or {}).get("hidden"):
                        reasons.append({"code": "parent_hidden", "gadget": gname, "parent": parent})
        text, code = values[key]
        if code == "key_off":
            reasons.append({"code": "needs_key", "keys": ", ".join(it.get("needs", [])),
                            "enable": {"keys": it.get("needs", [])[:1] if it.get("needsAny") else it.get("needs", [])}})
        elif code == "type_not_in_key":
            reasons.append({"code": "type_not_in_key", "key": it["typesInKey"],
                            "enable": {"keys": [it["typesInKey"]], "addType": unit["name"]}})
        elif code == "needs_state":
            reasons.append({"code": "needs_state", "state": it.get("state"), "enable": {"state": it.get("state")}})
        elif code in ("no_data", "live_only"):
            reasons.append({"code": code})
        if reasons:
            absent.append({"item": it["item"], "kind": "dll", "ref": it["ref"], "reasons": reasons,
                           "value": text, "en": it["en"], "es": it["es"]})
    for g, v in out.items():
        if v["text"] is not None and v["show"] is None:
            v["show"] = True
    # the stock items gathered the same way: one entry per item, its reasons in a list
    stock = []
    for a in absent:
        if "reasons" not in a:
            reason = dict(a["vars"], code=a["code"])
            if a["code"] == "ui_variant":
                reason["enable"] = {"variant": "normal"}
            stock.append({"item": a["item"], "kind": a["kind"], "reasons": [reason]})
    absent = stock + [a for a in absent if "reasons" in a and a["kind"] == "dll"]
    return {"gadgets": out, "live": live, "rows": rows_out, "absent": absent,
            "unit": {k: unit[k] for k in ("name", "display", "types", "hp", "hp_initial", "los", "speed", "train",
                                          "armor_value", "armor_type", "contain", "portrait")},
            "attacks": [a["name"] for a in attack_list], "dll": dll, "key": key_on}


def catalog_key():
    return table("uhc_minui_items")["key"]
