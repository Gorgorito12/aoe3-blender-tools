# SPDX-License-Identifier: GPL-3.0-or-later
"""Edits of the game's unit list (data/protoy.xml) and string table (data/stringtabley.xml) at
the text level, so the rest of these large files stays byte for byte as it was.

protoy.xml: `<Unit id=... name=...>` blocks (both quote styles occur), CRLF line ends, tabs; new
units go before `</Proto>`. Mods number new units with id == DBID. stringtabley.xml: UTF-16 with
a byte order mark, `<String _locID='N'>text</String>`; new strings go before the block of
"DON'T WRITE STRINGS DOWN HERE" comments that closes the language, else before `</Language>`.

The engine prefers a compiled `<file>.xmb` when it is newer than the XML: `xmb_twins` finds them.
"""
import os
import re
from xml.sax.saxutils import escape

UNIT_RE = re.compile(r"<Unit\s+id\s*=\s*['\"](\d+)['\"]\s+name\s*=\s*['\"]([^'\"]+)['\"]\s*>")
DBID_RE = re.compile(r"<DBID>\s*(\d+)\s*</DBID>")
LOCID_RE = re.compile(r"_locID\s*=\s*['\"](\d+)['\"]")
STRING_STOP = "<!-- DON'T WRITE STRINGS DOWN HERE -->"


class ProtoError(ValueError):
    pass


# --------------------------------------------------------------------------------------------------
# Units

class Index:
    def __init__(self, text):
        self.ids, self.names, self.dbids, self.spans = set(), {}, set(), {}
        starts = [(m.start(), int(m.group(1)), m.group(2)) for m in UNIT_RE.finditer(text)]
        for k, (s, uid, name) in enumerate(starts):
            end = text.find("</Unit>", s)
            if end < 0:
                raise ProtoError(f"unit {name} has no </Unit>")
            end += len("</Unit>")
            self.ids.add(uid)
            self.names[name.lower()] = name
            self.spans[name.lower()] = (s, end)
            m = DBID_RE.search(text, s, end)
            if m:
                self.dbids.add(int(m.group(1)))

    def free_id(self, lo=25000, hi=29999):
        """The lowest number in [lo, hi] used neither as an id nor as a DBID."""
        for n in range(lo, hi + 1):
            if n not in self.ids and n not in self.dbids:
                return n
        raise ProtoError(f"no free unit number in {lo}..{hi}")


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def write_text(path, text, encoding):
    with open(path, "wb") as f:
        f.write(text.encode(encoding))


def unit_text(text, name, index=None):
    index = index or Index(text)
    span = index.spans.get(name.lower())
    if span is None:
        raise ProtoError(f"no unit named {name}")
    return text[span[0]:span[1]]


def _set(block, tag, value):
    """Sets <tag>value</tag> in a unit block: replaces the first one, else adds it before the
    first <UnitType> (the order the game's files use for scalar fields)."""
    if value is None:
        return block
    pat = re.compile(rf"(<{tag}>)[^<]*(</{tag}>)", re.I)
    v = escape(str(value))
    if pat.search(block):
        return pat.sub(lambda m: m.group(1) + v + m.group(2), block, count=1)
    nl = "\r\n" if "\r\n" in block else "\n"
    at = block.find("<UnitType>")
    if at < 0:
        at = block.rfind("</Unit>")
    line_start = block.rfind("\n", 0, at) + 1
    return block[:line_start] + f"\t\t<{tag}>{v}</{tag}>{nl}" + block[line_start:]


def _drop(block, tag):
    """Removes every line holding a <tag ...> element."""
    lines = block.splitlines(keepends=True)
    return "".join(l for l in lines if not re.match(rf"\s*<{tag}[\s>]", l, re.I))


def clone_unit(template, *, name, uid, fields, drop=("Train", "Tech", "Command")):
    """A new unit block from a template block: the name, id = DBID = uid, the given fields set
    (None leaves one as it is), and the lines of the `drop` elements removed."""
    m = UNIT_RE.match(template.lstrip())
    if not m:
        raise ProtoError("the template does not start with <Unit id=... name=...>")
    head = template[:template.find(">") + 1]
    body = template[len(head):]
    q = '"' if '"' in head else "'"
    block = f"<Unit id={q}{uid}{q} name={q}{name}{q}>" + body
    block = _set(block, "DBID", uid)
    for tag, value in fields.items():
        block = _set(block, tag, value)
    for tag in drop:
        block = _drop(block, tag)
    return block


def insert_unit(text, block):
    """The file text with a unit block added before </Proto>."""
    index = Index(text)
    m = UNIT_RE.match(block)
    if not m:
        raise ProtoError("not a unit block")
    if m.group(2).lower() in index.names:
        raise ProtoError(f"a unit named {m.group(2)} already exists")
    if int(m.group(1)) in index.ids or int(m.group(1)) in index.dbids:
        raise ProtoError(f"unit number {m.group(1)} is taken")
    end = text.rfind("</Proto>")
    if end < 0:
        raise ProtoError("no </Proto>")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text[:end] + "\t" + block.strip() + nl + text[end:]


def show_as(text, name, fields, tags=("AnimFile", "Icon", "PortraitIcon")):
    """The text with unit `name`'s model, icon and portrait replaced by the given fields (the
    ones present in `fields`), for looking at a new building in place of an existing one."""
    index = Index(text)
    span = index.spans.get(name.lower())
    if span is None:
        raise ProtoError(f"no unit named {name}")
    s, e = span
    block = text[s:e]
    for tag in tags:
        if fields.get(tag) and re.search(rf"<{tag}>", block, re.I):
            block = _set(block, tag, fields[tag])
    return text[:s] + block + text[e:]


def add_train(text, unit, proto_name, column=1, page=6, row=0):
    """The text with `proto_name` added to what `unit` can build or train (a <Train> line after
    its last one; villagers list their buildings this way)."""
    index = Index(text)
    span = index.spans.get(unit.lower())
    if span is None:
        raise ProtoError(f"no unit named {unit}")
    s, e = span
    block = text[s:e]
    if re.search(rf"<Train[^>]*>\s*{re.escape(proto_name)}\s*</Train>", block, re.I):
        return text
    nl = "\r\n" if "\r\n" in block else "\n"
    line = f'\t\t<Train column="{column}" page="{page}" row="{row}">{escape(proto_name)}</Train>{nl}'
    last = block.rfind("</Train>")
    if last >= 0:
        at = block.find("\n", last) + 1
    else:
        at = block.rfind("\n", 0, block.rfind("</Unit>")) + 1
    return text[:s] + block[:at] + line + block[at:] + text[e:]


def remove_unit(text, name):
    index = Index(text)
    span = index.spans.get(name.lower())
    if span is None:
        return text
    s, e = span
    s = text.rfind("\n", 0, s) + 1
    if text[e:e + 2] == "\r\n":
        e += 2
    elif text[e:e + 1] == "\n":
        e += 1
    return text[:s] + text[e:]


# --------------------------------------------------------------------------------------------------
# Strings

def locids(text):
    return {int(x) for x in LOCID_RE.findall(text)}


def free_locids(text, count, start=9_000_000):
    """`count` consecutive unused string numbers from `start` on."""
    used = locids(text)
    n = start
    while any(n + k in used for k in range(count)):
        n += 1
    return list(range(n, n + count))


def add_strings(text, strings):
    """The string table text with {locid: text} added."""
    used = locids(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = []
    for lid, s in strings.items():
        if lid in used:
            raise ProtoError(f"string {lid} already exists")
        lines.append(f"\t\t<String _locID='{lid}'>{escape(s)}</String>{nl}")
    at = text.find(STRING_STOP)
    if at >= 0:
        at = text.rfind("\n", 0, at) + 1
    else:
        at = text.rfind("</Language>")
        if at < 0:
            raise ProtoError("no </Language>")
        at = text.rfind("\n", 0, at) + 1
    return text[:at] + "".join(lines) + text[at:]


def remove_strings(text, ids):
    ids = {int(i) for i in ids}
    out = []
    for line in text.splitlines(keepends=True):
        m = LOCID_RE.search(line)
        if m and int(m.group(1)) in ids and "<String" in line:
            continue
        out.append(line)
    return "".join(out)


def xmb_twins(data_dir, names=("protoy.xml", "techtreey.xml", "stringtabley.xml")):
    """Compiled twins of the given data files that exist (any case)."""
    found = []
    try:
        present = {f.lower(): f for f in os.listdir(data_dir)}
    except OSError:
        return found
    for n in names:
        f = present.get((n + ".xmb").lower())
        if f:
            found.append(os.path.join(data_dir, f))
    return found
