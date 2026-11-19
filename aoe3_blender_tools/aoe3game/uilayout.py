# SPDX-License-Identifier: GPL-3.0-or-later
"""The game's interface layout files (`data\\ui*.xml`, or their compiled `.xmb`) as a tree that
keeps every byte: an untouched file is written back identical, and an edit changes only the
characters it is about.

The game's files are written by hand and its parser is lenient: attribute names in any case,
spaces around `=`, comments holding whole gadgets, stray closing tags, elements left open. This
reader follows it as `tools/ui_preview.py` always has (a closing tag closes up to the element it
names; one that names nothing open is kept as it is and ignored), and keeps each piece of the
source as it was written:

- text, comments, processing instructions, CDATA and stray closing tags are raw slices;
- an element is its opening tag (cut into its name, each attribute's spacing, name, `=`, quote
  and value, and the rest), its children, and its closing tag ('' when it was self-closing or
  never closed: the next closing tag of an enclosing element closed it).

`Doc.text()` joins the pieces again; `Doc.data()` encodes them as the file was (its byte-order
mark, UTF-8 or UTF-16). Standard library only.
"""
import re

_TOKEN = re.compile(
    r"<!--.*?-->|<\?.*?\?>|<!\[CDATA\[.*?\]\]>|<![^>]*>"
    r"|<(?P<close>/)?(?P<tag>[A-Za-z_][\w.:-]*)(?P<attrs>(?:\s+[^\s=/>]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'))?)*)"
    r"(?P<tail>\s*/?>)",
    re.S)
_ATTR = re.compile(r"(\s+)([^\s=/>]+)(?:(\s*=\s*)(?:\"([^\"]*)\"|'([^']*)'))?")
BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


class LayoutError(ValueError):
    pass


class Raw:
    """A piece kept as written: text, a comment, a stray closing tag."""
    __slots__ = ("kind", "raw", "parent")

    def __init__(self, kind, raw, parent=None):
        self.kind, self.raw, self.parent = kind, raw, parent

    def text(self):
        return self.raw


class Attr:
    __slots__ = ("space", "name", "eq", "quote", "value")

    def __init__(self, space, name, eq, quote, value):
        self.space, self.name, self.eq, self.quote, self.value = space, name, eq, quote, value

    def text(self):
        if self.eq is None:                       # a bare attribute: <gadget hidden>
            return self.space + self.name
        return f"{self.space}{self.name}{self.eq}{self.quote}{self.value}{self.quote}"


class Element:
    """An element: `tag` as written, `attrs` in order, `children` (Raw and Element), `close` as
    written ('' when there is none)."""

    def __init__(self, tag, attrs, tail, parent=None):
        self.tag, self.attrs, self.tail, self.parent = tag, attrs, tail, parent
        self.children = []
        self.close = ""
        self.line = 0

    kind = "element"

    @property
    def name_lower(self):
        return self.tag.lower()

    def get(self, name, default=None):
        """An attribute's value by its name in any case (the last one wins, as a dict would)."""
        found = default
        low = name.lower()
        for a in self.attrs:
            if a.name.lower() == low:
                found = a.value if a.eq is not None else ""
        return found

    def has(self, name):
        low = name.lower()
        return any(a.name.lower() == low for a in self.attrs)

    def attributes(self):
        """{lower-case name: value} in order."""
        return {a.name.lower(): (a.value if a.eq is not None else "") for a in self.attrs}

    @property
    def self_closing(self):
        return self.tail.rstrip().endswith("/>")

    def open_text(self):
        return "<" + self.tag + "".join(a.text() for a in self.attrs) + self.tail

    def text(self):
        return self.open_text() + "".join(c.text() for c in self.children) + self.close

    def elements(self):
        return [c for c in self.children if isinstance(c, Element)]

    def own_text(self):
        """The text directly inside the element (not inside its children), as written."""
        return "".join(c.raw for c in self.children if isinstance(c, Raw) and c.kind in ("text", "cdata"))

    def walk(self):
        """Every element below this one, in document order."""
        for c in self.children:
            if isinstance(c, Element):
                yield c
                yield from c.walk()

    def index_in_parent(self):
        return self.parent.children.index(self) if self.parent is not None else -1


class Doc:
    """A layout file: `root` holds the top-level pieces (the declaration, `<layout>`, ...)."""

    def __init__(self, root, encoding, bom):
        self.root, self.encoding, self.bom = root, encoding, bom

    def text(self):
        return "".join(c.text() for c in self.root.children)

    def data(self):
        errors = "surrogateescape" if self.encoding == "utf-8" else "surrogatepass"
        return self.bom + self.text().encode(self.encoding, errors)

    def elements(self):
        return list(self.root.walk())

    def gadgets(self):
        return [e for e in self.root.walk() if e.name_lower == "gadget"]


def _attrs(text):
    """The attributes of an opening tag's middle, or None when they cannot all be accounted for."""
    out, pos = [], 0
    for m in _ATTR.finditer(text):
        if m.start() != pos:
            return None
        if m.group(3) is None:
            out.append(Attr(m.group(1), m.group(2), None, "", ""))
        else:
            quote = '"' if m.group(4) is not None else "'"
            value = m.group(4) if m.group(4) is not None else m.group(5)
            out.append(Attr(m.group(1), m.group(2), m.group(3), quote, value))
        pos = m.end()
    return out if pos == len(text) else None


def parse_text(text):
    """The tree of a layout's text."""
    root = Element("#document", [], "")
    stack = [root]
    pos = 0

    def add_raw(kind, raw):
        if raw:
            stack[-1].children.append(Raw(kind, raw, stack[-1]))

    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            add_raw("text", text[pos:m.start()])
        raw = m.group(0)
        tag = m.group("tag")
        pos = m.end()
        if raw.startswith("<!--"):
            add_raw("comment", raw)
            continue
        if raw.startswith("<![CDATA["):
            add_raw("cdata", raw)
            continue
        if raw.startswith("<?") or raw.startswith("<!"):
            add_raw("pi", raw)
            continue
        if m.group("close"):
            low = tag.lower()
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].name_lower == low:
                    stack[i].close = raw
                    del stack[i:]
                    break
            else:
                add_raw("stray", raw)              # closes nothing open: kept, ignored
            continue
        attrs = _attrs(m.group("attrs") or "")
        if attrs is None:
            raise LayoutError(f"an opening tag this reader cannot cut: {raw[:80]}")
        el = Element(tag, attrs, m.group("tail"), stack[-1])
        el.line = text.count("\n", 0, m.start()) + 1
        stack[-1].children.append(el)
        if not el.self_closing:
            stack.append(el)
    if pos < len(text):
        add_raw("text", text[pos:])
    return root


def decode(data):
    """(text, encoding, bom) of a file's bytes; anything that is not UTF-8 survives as escapes."""
    for bom, enc in BOMS:
        if data.startswith(bom):
            errors = "surrogateescape" if enc == "utf-8" else "surrogatepass"
            return data[len(bom):].decode(enc, errors), enc, bom
    return data.decode("utf-8", "surrogateescape"), "utf-8", b""


def parse(data):
    """A Doc from a file's bytes: text XML, or a compiled .xmb through tools/xmbedit.py (the
    result is then the XML text xmbedit gives, as it would be written loose)."""
    if data[:4] == b"l33t" or data[:2] == b"X1":
        import xmbedit
        elems, attrs, root = xmbedit.parse(xmbedit.decode(data))
        xml = xmbedit.to_xml(elems, attrs, root)
        data = xml.encode("utf-8") if isinstance(xml, str) else xml
    text, enc, bom = decode(data)
    return Doc(parse_text(text), enc, bom)


# --------------------------------------------------------------------------------------------------
# Edits: each changes only the pieces it is about

def _escape(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def set_attr(el, name, value):
    """Sets (value a string) or removes (None) an attribute, found by its name in any case; a new
    one goes after the others, written ` name="value"`."""
    low = name.lower()
    found = [a for a in el.attrs if a.name.lower() == low]
    if value is None:
        el.attrs = [a for a in el.attrs if a.name.lower() != low]
        return
    if found:
        a = found[-1]
        if a.eq is None:
            a.eq, a.quote = "=", '"'
        a.value = _escape(value) if a.quote == '"' else value.replace("'", "&apos;")
        return
    el.attrs.append(Attr(" ", name, "=", '"', _escape(value)))


def _indent_of(el):
    """The whitespace before an element on its line, and the file's line end."""
    parent = el.parent
    i = parent.children.index(el)
    before = parent.children[i - 1] if i > 0 else None
    nl = "\r\n" if before is not None and isinstance(before, Raw) and "\r\n" in before.raw else "\n"
    if isinstance(before, Raw) and before.kind == "text" and "\n" in before.raw:
        return before.raw.rsplit("\n", 1)[1], nl
    return "", nl


def _open_up(el):
    """A self-closing element made able to hold children: `<a/>` becomes `<a></a>`."""
    if el.self_closing:
        el.tail = el.tail.rstrip()[:-2].rstrip() + ">"
        el.close = f"</{el.tag}>"
    elif not el.close:
        el.close = f"</{el.tag}>"


def set_text(el, value):
    """The element's own text (around its children) becomes `value`, keeping the whitespace that
    surrounded the old text."""
    texts = [c for c in el.children if isinstance(c, Raw) and c.kind == "text" and c.raw.strip()]
    if texts:
        first = texts[0]
        lead = first.raw[:len(first.raw) - len(first.raw.lstrip())]
        trail = first.raw[len(first.raw.rstrip()):]
        first.raw = lead + value + trail if value else lead + trail
        for other in texts[1:]:
            other.raw = other.raw[:len(other.raw) - len(other.raw.lstrip())]
        return
    if not value:
        return
    _open_up(el)
    el.children.insert(0, Raw("text", value, el))


def insert(parent, index, fragment):
    """Inserts the elements of an XML fragment (text) into `parent` before child `index` (None:
    at the end), on lines of their own, indented one step deeper than the parent. Returns them."""
    _open_up(parent)
    indent, nl = _indent_of(parent) if parent.parent is not None else ("", "\n")
    step = "\t"
    new = parse_text(fragment.strip())
    els = [c for c in new.children if isinstance(c, Element)]
    if not els:
        raise LayoutError("the fragment holds no element")
    pieces = []
    for e in els:
        e.parent = parent
        pieces += [Raw("text", nl + indent + step, parent), e]
    kids = parent.children
    if index is None or index >= len(kids):
        # before the closing tag: keep the parent's own last line break where it was
        if kids and isinstance(kids[-1], Raw) and kids[-1].kind == "text" and not kids[-1].raw.strip():
            kids[-1:-1] = pieces
        else:
            kids.extend(pieces + [Raw("text", nl + indent, parent)])
    else:
        kids[index:index] = pieces
    return els


def remove(el):
    """Takes an element out, with the whitespace that put it on a line of its own."""
    parent = el.parent
    kids = parent.children
    i = kids.index(el)
    del kids[i]
    if i > 0 and isinstance(kids[i - 1], Raw) and kids[i - 1].kind == "text" and not kids[i - 1].raw.strip() \
            and "\n" in kids[i - 1].raw and (i >= len(kids) or isinstance(kids[i], Raw)):
        prev = kids[i - 1]
        cut = prev.raw.rfind("\n")
        if cut > 0 and prev.raw[cut - 1] == "\r":
            cut -= 1
        prev.raw = prev.raw[:cut]
        if not prev.raw:
            del kids[i - 1]
    el.parent = None


def find(doc, name):
    """The gadgets of that name (any case), in document order."""
    low = name.lower()
    return [g for g in doc.gadgets() if (g.get("name") or "").lower() == low]


def rect(el):
    """(x1, y1, x2, y2) of a gadget's `size1024`, ordered, or None."""
    v = el.get("size1024")
    if not v:
        return None
    try:
        x1, y1, x2, y2 = (float(t) for t in v.split()[:4])
    except ValueError:
        return None
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
