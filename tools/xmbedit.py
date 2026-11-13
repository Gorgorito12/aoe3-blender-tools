# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and edit legacy AoE3 compiled XML (.xmb), e.g. data\\protoy.xml.XMB.

Usage:
    python -I tools/xmbedit.py check <file.xmb>
    python -I tools/xmbedit.py to-xml <file.xmb> [<out.xml>]
    python -I tools/xmbedit.py from-xml <in.xml> [<out.xmb>] [--compress]
    python -I tools/xmbedit.py add-unittype <in.xmb> <out.xmb> <Unit> <UnitType> [<Unit> <UnitType> ...]

check         decodes and re-encodes the file and confirms the result is byte-identical, so an
              edit cannot change anything else; then does the same through the XML text that
              to-xml writes (to-xml, then from-xml gives the file back byte for byte).
to-xml        writes a readable XML copy (element names as stored, which is lowercase). Use it
              to read files extracted from the BAR archives with tools/bar.py. Each element
              starts on the source line stored in the file (blank lines fill the gaps), so
              from-xml compiles the copy back to the same bytes. Without <out.xml> it writes
              next to the input, without its ".xmb" (cannon.impacteffect.xmb ->
              cannon.impacteffect).
from-xml      compiles an XML file (e.g. an edited protoy.xml, a new .tactics file or an
              .impacteffect) the way the stock files are stored: element and attribute names
              lowercase, whitespace-only text dropped, leading whitespace dropped (trailing
              spaces of a leaf's text are kept), the XML's line numbers kept. Without <out.xmb>
              it writes next to the input with ".xmb" added (protoy.xml -> protoy.xml.xmb,
              cannon.impacteffect -> cannon.impacteffect.xmb; an .impacteffect, .tactics or
              .dmg saved with ".xml" after it loses that ".xml"). --compress writes the "l33t" zlib form (stock
              protoy.xml.XMB); without it the file is plain X1 (stock .tactics and
              .impacteffect files). Both load.
add-unittype  adds <unittype>UnitType</unittype> after the last unittype of each named
              <unit name='Unit'> (a protoy XMB). It reports units that are missing or already
              have the type. The output keeps the input's compression.

Format (legacy TAD, as read from the stock files):
    optional "l33t" + uint32 inflated size + zlib stream, then
    "X1" uint32 size, "XR" uint32 4, uint32 8 (version),
    uint32 n + n UTF-16 element names, uint32 n + n UTF-16 attribute names, root node.
    node: "XN" uint32 size, UTF-16 text, uint32 element index, uint32 source line,
          uint32 n + n (uint32 attribute index, UTF-16 value), uint32 n + n child nodes.
    UTF-16 strings are uint32 length (in characters) + characters, no terminator.
"""
import struct
import sys
import zlib
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr


class Node:
    __slots__ = ("text", "name", "line", "attrs", "children")


def is_compressed(raw):
    return raw[:4] == b"l33t"


def decode(raw):
    """Returns the inner X1 document of a compressed or uncompressed .xmb file."""
    if is_compressed(raw):
        size = struct.unpack_from("<I", raw, 4)[0]
        inner = zlib.decompress(raw[8:])
        if len(inner) != size:
            raise ValueError(f"inflated {len(inner)} bytes, header says {size}")
        return inner
    if raw[:2] != b"X1":
        raise ValueError(f"not an XMB file (starts with {raw[:4]!r})")
    return raw


def parse(x):
    """Returns (element names, attribute names, root node) of an X1 document."""
    pos = 0

    def u32():
        nonlocal pos
        value = struct.unpack_from("<I", x, pos)[0]
        pos += 4
        return value

    def wstr():
        nonlocal pos
        n = u32()
        text = x[pos:pos + 2 * n].decode("utf-16-le", "surrogatepass")
        pos += 2 * n
        return text

    def expect(tag):
        nonlocal pos
        if x[pos:pos + 2] != tag:
            raise ValueError(f"expected {tag!r} at {pos:#x}")
        pos += 2

    expect(b"X1")
    total = u32()
    expect(b"XR")
    if (u32(), u32()) != (4, 8):
        raise ValueError("unsupported XMB version (expected XR 4, 8)")
    elems = [wstr() for _ in range(u32())]
    attrs = [wstr() for _ in range(u32())]

    def node():
        expect(b"XN")
        end = u32()
        end += pos
        nd = Node()
        nd.text = wstr()
        nd.name = u32()
        nd.line = u32()
        nd.attrs = [(u32(), wstr()) for _ in range(u32())]
        nd.children = [node() for _ in range(u32())]
        if pos != end:
            raise ValueError(f"node size mismatch at {pos:#x}")
        return nd

    root = node()
    if pos != len(x) or total != len(x) - 6:
        raise ValueError("trailing data or bad document size")
    return elems, attrs, root


def _wstr(s):
    """Length in UTF-16 code units (a character outside the BMP counts 2), then the text."""
    data = s.encode("utf-16-le", "surrogatepass")
    return struct.pack("<I", len(data) // 2) + data


def encode(elems, attrs, root):
    def node(nd):
        body = _wstr(nd.text) + struct.pack("<II", nd.name, nd.line)
        body += struct.pack("<I", len(nd.attrs))
        body += b"".join(struct.pack("<I", k) + _wstr(v) for k, v in nd.attrs)
        body += struct.pack("<I", len(nd.children))
        body += b"".join(node(c) for c in nd.children)
        return b"XN" + struct.pack("<I", len(body)) + body

    body = b"XR" + struct.pack("<II", 4, 8)
    body += struct.pack("<I", len(elems)) + b"".join(_wstr(s) for s in elems)
    body += struct.pack("<I", len(attrs)) + b"".join(_wstr(s) for s in attrs)
    body += node(root)
    return b"X1" + struct.pack("<I", len(body)) + body


def wrap(inner, compressed):
    return b"l33t" + struct.pack("<I", len(inner)) + zlib.compress(inner, 9) if compressed else inner


def load_checked(path):
    raw = open(path, "rb").read()
    inner = decode(raw)
    elems, attrs, root = parse(inner)
    if encode(elems, attrs, root) != inner:
        raise ValueError(f"{path}: re-encoding does not reproduce the file; refusing to edit it")
    return raw, inner, elems, attrs, root


# Line breaks inside a text are written as character references: a raw one would move every later
# element to another source line. (quoteattr already does this for attribute values.)
_TEXT_ENTITIES = {"\n": "&#10;", "\r": "&#13;"}


def to_xml(elems, attrs, root):
    """The document as XML text. Each start tag is put on the source line stored for it (the
    declaration is line 1, blank lines fill the gaps); a tag whose line is already passed goes on
    the current line. So from_xml(to_xml(...)) stores the same line numbers."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>']

    def open_on(line, depth, text):
        if line > len(lines):
            lines.extend([""] * (line - len(lines) - 1))
            lines.append("  " * depth + text)
        else:
            lines[-1] += text

    def node(nd, depth, next_line):
        """next_line: the stored line of the next start tag after this element (None at the end)."""
        tag = elems[nd.name]
        attr_text = "".join(f" {attrs[k]}={quoteattr(v)}" for k, v in nd.attrs)
        # A leaf's text is written as stored: stock strings can end in a space ("Mejora en: ").
        text = escape(nd.text if not nd.children else nd.text.strip(), _TEXT_ENTITIES)
        if not nd.children:
            open_on(nd.line, depth, f"<{tag}{attr_text}>{text}</{tag}>" if text else f"<{tag}{attr_text}/>")
            return
        open_on(nd.line, depth, f"<{tag}{attr_text}>{text}")
        for i, child in enumerate(nd.children):
            later = nd.children[i + 1].line if i + 1 < len(nd.children) else next_line
            node(child, depth + 1, later)
        # The end tag gets a line of its own when the next start tag leaves one free.
        if next_line is None or next_line > len(lines) + 1:
            lines.append("  " * depth + f"</{tag}>")
        else:
            lines[-1] += f"</{tag}>"

    node(root, 0, None)
    return "\n".join(lines) + "\n"


def xml_round_trip(elems, attrs, root):
    """The X1 document compiled back from to_xml's text."""
    return encode(*from_xml(to_xml(elems, attrs, root).encode("utf-8")))


# Data kinds whose source is not named .xml: an editor may still save one as cannon.impacteffect.xml.
_OWN_EXTENSIONS = (".impacteffect", ".tactics", ".dmg")


def default_xml_name(path):
    """cannon.impacteffect.xmb -> cannon.impacteffect; anything else gets ".xml"."""
    return path[:-4] if path.lower().endswith(".xmb") else path + ".xml"


def default_xmb_name(path):
    """The name the game loads: protoy.xml -> protoy.xml.xmb, cannon.impacteffect ->
    cannon.impacteffect.xmb, and cannon.impacteffect.xml -> cannon.impacteffect.xmb too."""
    lower = path.lower()
    if lower.endswith(".xml") and lower[:-4].endswith(_OWN_EXTENSIONS):
        path = path[:-4]
    return path + ".xmb"


def from_xml(data):
    """Returns (element names, attribute names, root node) of an XML document (bytes). Names are
    numbered in order of first use, as in the stock files."""
    elems, attrs = [], []
    elem_ids, attr_ids = {}, {}

    def index(table, ids, name):
        name = name.lower()
        if name not in ids:
            ids[name] = len(table)
            table.append(name)
        return ids[name]

    parser = expat.ParserCreate()
    parser.ordered_attributes = True
    stack, texts, done = [], [], []

    def start(name, attr_list):
        nd = Node()
        nd.name = index(elems, elem_ids, name)
        nd.line = parser.CurrentLineNumber
        nd.attrs = [(index(attrs, attr_ids, attr_list[i]), attr_list[i + 1]) for i in range(0, len(attr_list), 2)]
        nd.children = []
        if stack:
            stack[-1].children.append(nd)
        stack.append(nd)
        texts.append([])

    def end(_name):
        nd = stack.pop()
        text = "".join(texts.pop())
        # As the stock files store it: an element with children keeps its trimmed text (a tactic's
        # name); a leaf drops leading whitespace but keeps trailing spaces ("Mejora en: ").
        nd.text = text.strip() if nd.children else (text.lstrip() if text.strip() else "")
        if not stack:
            done.append(nd)

    def chars(text):
        if texts:
            texts[-1].append(text)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.Parse(data, True)
    return elems, attrs, done[0]


def add_unittypes(elems, attrs, root, pairs):
    """pairs: [(unit name, unittype)]. Returns (added, already, missing) unit name lists."""
    if "unit" not in elems or "unittype" not in elems or "name" not in attrs:
        raise ValueError("this file has no <unit name=...> / <unittype> elements (not a protoy XMB?)")
    unit_e, type_e, name_a = elems.index("unit"), elems.index("unittype"), attrs.index("name")
    wanted = {}
    for unit, utype in pairs:
        wanted.setdefault(unit, []).append(utype)
    added, already, found = [], [], set()
    for unit in root.children:
        if unit.name != unit_e:
            continue
        name = next((v for k, v in unit.attrs if k == name_a), None)
        if name not in wanted:
            continue
        found.add(name)
        for utype in wanted[name]:
            types = [c for c in unit.children if c.name == type_e]
            if any(c.text == utype for c in types):
                already.append(f"{name}:{utype}")
                continue
            last = types[-1] if types else (unit.children[-1] if unit.children else None)
            new = Node()
            new.text, new.name, new.attrs, new.children = utype, type_e, [], []
            new.line = last.line if last else unit.line
            unit.children.insert(unit.children.index(last) + 1 if last else 0, new)
            added.append(f"{name}:{utype}")
    missing = [u for u in wanted if u not in found]
    return added, already, missing


def main(argv):
    if not argv or argv[0] not in ("check", "to-xml", "from-xml", "add-unittype"):
        sys.exit(__doc__)
    command, args = argv[0], argv[1:]
    if command == "check" and len(args) == 1:
        raw, inner, elems, attrs, root = load_checked(args[0])
        kind = "compressed" if is_compressed(raw) else "uncompressed"
        through_xml = "identical" if xml_round_trip(elems, attrs, root) == inner else "DIFFERS"
        print(f"{args[0]}: round trip ok ({kind}, {len(inner)} bytes, {len(elems)} element names, "
              f"{len(attrs)} attribute names); through to-xml and from-xml: {through_xml}")
        if through_xml != "identical":
            sys.exit(1)
    elif command == "to-xml" and len(args) in (1, 2):
        _, _, elems, attrs, root = load_checked(args[0])
        out = args[1] if len(args) == 2 else default_xml_name(args[0])
        with open(out, "w", encoding="utf-8") as f:
            f.write(to_xml(elems, attrs, root))
        print(f"wrote {out}")
    elif command == "from-xml" and args and not args[0].startswith("--"):
        compress = "--compress" in args
        rest = [a for a in args[1:] if a != "--compress"]
        if len(rest) > 1 or any(a.startswith("--") for a in rest):
            sys.exit(__doc__)
        out = rest[0] if rest else default_xmb_name(args[0])
        with open(args[0], "rb") as f:
            elems, attrs, root = from_xml(f.read())
        inner = encode(elems, attrs, root)
        if encode(*parse(inner)) != inner:
            raise ValueError("the compiled document does not decode to itself")
        with open(out, "wb") as f:
            f.write(wrap(inner, compressed=compress))
        print(f"wrote {out} ({'compressed' if compress else 'uncompressed'}, {len(elems)} element names, "
              f"{len(attrs)} attribute names)")
    elif command == "add-unittype" and len(args) >= 4 and len(args) % 2 == 0:
        raw, _, elems, attrs, root = load_checked(args[0])
        added, already, missing = add_unittypes(elems, attrs, root, list(zip(args[2::2], args[3::2])))
        with open(args[1], "wb") as f:
            f.write(wrap(encode(elems, attrs, root), is_compressed(raw)))
        print(f"added: {added or 'nothing'}")
        if already:
            print(f"already present: {already}")
        if missing:
            print(f"WARNING: no <unit> with these names: {missing}")
        print(f"wrote {args[1]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
