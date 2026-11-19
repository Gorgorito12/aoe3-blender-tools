# SPDX-License-Identifier: GPL-3.0-or-later
"""A tiny synthetic game copy for the interface screen's tests: two layouts (one loose, one compiled
inside data\\Data3.bar with an older twin in data\\Data.bar), a string table and fonts3.xml in
UTF-16, a 4 x 4 texture, and a Fonts.bar holding a TrueType file reduced to its name table.
Nothing of a game: every byte is made here."""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

MAIN = """<?xml version="1.0" encoding="utf-8"?>\r
<layout>\r
\t<gadget name="titleBar" type="gadget" size1024="0 0 1024 30" background="ui\\ingame\\bar" z="5">\r
\t\t<gadget name="titleBar-age" type="formatText" size1024="10 2 200 28" textfont="Test" textfontsize="12" textcolor="255 255 0">$$101$$Age</gadget>\r
\t\t<gadget name="pausePanel" type="gadget" size1024="300 300 700 400" background="ui\\ingame\\nothere"/>\r
\t</gadget>\r
\t<gadget name="SettlerCountDialog-defaultPanelEurMin" size1024="220 630 345 768" background="ui\\ingame\\bar"/>\r
\t<gadget name="SettlerCountDialog-defaultPanelNatMin" size1024="220 630 345 768" background="ui\\ingame\\bar"/>\r
\t<gadget name="hiddenDialog" size1024="0 0 10 10" hidden=""/>\r
</layout>\r
"""
SELECTION = """<?xml version="1.0" encoding="utf-8"?>
<layout>
\t<gadget name="unitselectionpanel" type="unitselectionpanel" size1024="342 629 700 768" z="105">
\t\t<gadget name="unitselectionpanel-unitHitPointsLabel" type="formatText" size1024="410 680 578 734" textfont="Missing" textfontsize="10"/>
\t\t<gadget name="TrainTime" type="formatText" size1024="338 656 408 726" textfont="Test" textfontsize="12">Train Points: {currentUnitTrainPoints}</gadget>
\t</gadget>
</layout>
"""
STRINGS = """<?xml version="1.0" encoding="UTF-16"?>\r
<StringTable version="8"><Language name="English">\r
<String _locID='101' symbol='cStringAge'>Colonial Age</String>\r
<String _locID='102'>Unused &amp; kept</String>\r
</Language></StringTable>\r
"""
FONTS = """<?xml version="1.0" encoding="UTF-16"?>\r
<Fonts>\r
\t<Font Name="Test 12">\r
\t\t<param TypeFace="Test Face"/>\r
\t\t<param AscentHeight="12"/>\r
\t\t<param Bold="true"/>\r
\t\t<ResolutionOverride ResX="800"><param AscentHeight="10"/></ResolutionOverride>\r
\t\t<ResolutionOverride ResX="1280"><param AscentHeight="16"/></ResolutionOverride>\r
\t</Font>\r
\t<Font Name="Arial nobold nodrop 12">\r
\t\t<param TypeFace="Arial"/>\r
\t\t<param AscentHeight="12"/>\r
\t\t<ResolutionOverride ResX="1280"><param AscentHeight="14"/></ResolutionOverride>\r
\t</Font>\r
</Fonts>\r
"""


def write_bar(path, root, files):
    """A .bar archive: files [(name below root, bytes)]."""
    body, entries = bytearray(), []
    for name, data in files:
        entries.append((0x124 + len(body), len(data), name))
        body += data
    table = struct.pack("<I", len(root)) + root.encode("utf-16-le") + struct.pack("<I", len(entries))
    for off, size, name in entries:
        table += struct.pack("<3I", off, size, size) + bytes(16)
        table += struct.pack("<I", len(name)) + name.encode("utf-16-le")
    head = bytearray(0x124)
    head[:4] = b"ESPN"
    struct.pack_into("<2I", head, 0x118, len(entries), 0x124 + len(body))
    with open(path, "wb") as fh:
        fh.write(bytes(head) + bytes(body) + table)


def ttf_with_name(family):
    """A TrueType file holding only a name table that names this family (enough to be found by
    its family name; no browser would draw with it)."""
    names = [(3, 1, 0x409, 1, family.encode("utf-16-be")), (3, 1, 0x409, 2, "Regular".encode("utf-16-be"))]
    strings, records = b"", b""
    for plat, enc, lang, nid, raw in names:
        records += struct.pack(">HHHHHH", plat, enc, lang, nid, len(raw), len(strings))
        strings += raw
    name = struct.pack(">HHH", 0, len(names), 6 + 12 * len(names)) + records + strings
    offset = 12 + 16
    head = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    return head + struct.pack(">4sIII", b"name", 0, offset, len(name)) + name


def make(folder):
    """Writes the copy into `folder` (which must exist) and returns it."""
    import numpy as np
    import xmbedit
    from aoe3game import ddt
    for sub in ("data", os.path.join("art", "ui", "ingame"), "FONTS"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    with open(os.path.join(folder, "data", "uimainnew.xml"), "wb") as fh:
        fh.write(MAIN.encode("utf-8"))
    compiled = xmbedit.wrap(xmbedit.encode(*xmbedit.from_xml(SELECTION.encode("utf-8"))), True)
    older = xmbedit.wrap(xmbedit.encode(*xmbedit.from_xml(SELECTION.replace("TrainTime", "Old").encode())), True)
    write_bar(os.path.join(folder, "data", "Data3.bar"), "Data\\", [("uiunitselectionmin.xml.xmb", compiled)])
    write_bar(os.path.join(folder, "data", "Data.bar"), "Data\\", [("uiunitselectionmin.xml.xmb", older)])
    with open(os.path.join(folder, "data", "stringtabley.xml"), "wb") as fh:
        fh.write(STRINGS.encode("utf-16"))
    with open(os.path.join(folder, "FONTS", "fonts3.xml"), "wb") as fh:
        fh.write(FONTS.encode("utf-16"))
    write_bar(os.path.join(folder, "FONTS", "Fonts.bar"), "Fonts\\", [("Fonts\\test.ttf", ttf_with_name("Test Face"))])
    img = np.zeros((4, 4, 4), np.uint8)
    img[...] = (200, 120, 40, 255)
    with open(os.path.join(folder, "art", "ui", "ingame", "bar.ddt"), "wb") as fh:
        fh.write(ddt.write(img, ddt.DXT1))
    return folder
