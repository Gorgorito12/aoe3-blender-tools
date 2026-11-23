# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of aoe3game/gr2_fit.py and tools/fit_borrowed.py on synthetic models only (plain Python).

    python -I tests/test_gr2_fit.py

The fixture is a building model written by gr2_write: a body mesh and two debris meshes, each bound
whole to its own bone, plus a flag bone hanging from a debris bone. The "reference" is the same
model with other rest frames on its debris bones (turned and mirrored, as an export from another
tool stores them); the "borrower" carries a debris mesh renamed with Blender's `.001`.
"""
import contextlib
import io
import math
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_edit, gr2_fit, gr2_write  # noqa: E402
import fit_borrowed  # noqa: E402

TEMPLATE = """<damagetemplate>
  <model name="x">
    <impactpoint name="boneimpact01" bone="boneimpact01" impacttype="stone">
      <part mesh="debris_1a" bone="bone_debris_1a" halfextents="0.25, .5, 1.0"/>
      <part mesh="debris_1b" bone="bone_debris_1b" halfextents="0.25, .5, 1.0"/>
      <part mesh="debris_9z" bone="bone_debris_9z" halfextents="0.25, .5, 1.0"/>
    </impactpoint>
  </model>
</damagetemplate>
"""
PARTS = [("debris_1a", "bone_debris_1a"), ("debris_1b", "bone_debris_1b"), ("debris_9z", "bone_debris_9z")]
# a turn of 180 degrees about (1, -1, 0) / sqrt(2), and the reference's mirror: 180 about X, scale
# (1.1, -1.1, 1.1)
TURN = (math.sqrt(0.5), -math.sqrt(0.5), 0.0, 0.0)
MIRROR_Q = (1.0, 0.0, 0.0, 0.0)
MIRROR_S = (1.1, 0, 0, 0, -1.1, 0, 0, 0, 1.1)


def base_model():
    P = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    T = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
    return gr2_write.static_model("body", P, [(0, 0, 1)] * 4, [(0, 0), (1, 0), (0, 1), (1, 1)], T,
                                  texture="b.ddt", bump="f.ddt",
                                  bones=[("bone_debris_1a", (1.0, 0.0, 1.0)),
                                         ("bone_debris_1b", (-1.0, 0.0, 1.0)),
                                         ("boneimpact01", (0.0, 0.0, 1.5)),
                                         ("bone_flag_civ", (0.5, 0.5, 2.0))])


def building(names=("debris_1a", "debris_1b"), frames=None, flag_parent=True, flag_shift=0.0):
    """The fixture: debris meshes (copies of the body mesh) bound to their bones, named `names`;
    `frames` {bone: (quaternion, scale/shear or None)} sets those bones' rest orientation (the
    inverse kept consistent); the flag hangs from bone_debris_1a."""
    root = gr2_edit.copy_tree(gr2.load(base_model()))
    mesh = root.values["Meshes"][0]
    bones = root.values["Skeletons"][0].values["Bones"]
    index = {b.values["Name"]: i for i, b in enumerate(bones)}
    for name, bone in zip(names, ("bone_debris_1a", "bone_debris_1b")):
        m = gr2_edit.copy_tree(gr2.load(base_model())).values["Meshes"][0]    # objects of its own
        bb = m.values["BoneBindings"][0]
        m.values["Name"] = name
        m.values["BoneBindings"] = [gr2_write.W(bb.spec, **dict(bb.values, BoneName=bone))]
        root.values["Meshes"].append(m)
        root.values["Models"][0].values["MeshBindings"].append(
            gr2_write.W(root.values["Models"][0].values["MeshBindings"][0].spec, Mesh=m))
    world = {}
    for b in bones:                                  # positions of the plain model (root at 0)
        world[b.values["Name"]] = list(b.values["Transform"][1:4])
    for name, (q, ss) in (frames or {}).items():
        b = bones[index[name]]
        tr = list(b.values["Transform"])
        tr[0] = 1 | 2 | (4 if ss else 0)
        tr[4:8] = q
        if ss:
            tr[8:17] = ss
        b.values["Transform"] = tuple(tr)
    flag = bones[index["bone_flag_civ"]]
    if flag_parent:                                  # the flag hangs from bone_debris_1a, in place
        flag.values["ParentIndex"] = index["bone_debris_1a"]
    data = gr2_write.serialize(root, type_tag=gr2.load(base_model()).c.type_tag)
    # local positions and inverses made consistent with the rest frames
    data = bytearray(data)
    doc = gr2.load(bytes(data))
    sk = gr2_fit.bones_of(doc)[0]
    want = dict(world)
    want["bone_flag_civ"] = [want["bone_flag_civ"][0] + flag_shift] + want["bone_flag_civ"][1:]
    for b in sk:
        if b.parent >= 0 and b.name in want:
            p = sk[b.parent]
            inv = gr2_fit._inverse3(p.lin)
            local = gr2_fit._vec(inv, [x - y for x, y in zip(want[b.name], p.pos)])
            struct.pack_into("<3f", data, b.tr_at + 4, *local)
    doc = gr2.load(bytes(data))
    for b in gr2_fit.bones_of(doc)[0]:
        struct.pack_into("<16f", data, b.iw_at, *inverse_rows(b.lin, b.pos))
    struct.pack_into("<I", data, 0x28, gr2.file_crc(data))
    return bytes(data)


def inverse_rows(lin, pos):
    inv = gr2_fit._inverse3(lin)
    t = [-sum(inv[r][k] * pos[k] for k in range(3)) for r in range(3)]
    return [inv[0][0], inv[1][0], inv[2][0], 0, inv[0][1], inv[1][1], inv[2][1], 0,
            inv[0][2], inv[1][2], inv[2][2], 0, t[0], t[1], t[2], 1]


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def names(data):
    return [m.get("Name") for m in gr2.load(data).root().get("Meshes")]


def frames(data):
    return {b.name: b for b in gr2_fit.bones_of(gr2.load(data))[0]}


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fit_borrowed.main(list(argv))
    return code, out.getvalue()


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_consistent(self):
        for data in (building(), building(frames={"bone_debris_1a": (TURN, None)})):
            self.assertTrue(gr2.crc_ok(data))
            for b in frames(data).values():
                self.assertLess(gr2_fit._inverse_error(b.lin, b.pos, b.iw), 1e-5, b.name)
        self.assertEqual(names(building()), ["body", "debris_1a", "debris_1b"])


class TemplateTest(unittest.TestCase):
    def test_parts_are_read_in_any_attribute_order(self):
        self.assertEqual(gr2_fit.template_parts(TEMPLATE), PARTS)
        self.assertEqual(gr2_fit.template_parts('<part bone="b" mesh="m"/>'), [("m", "b")])


class RenameTest(unittest.TestCase):
    def test_a_suffixed_debris_mesh_gets_the_part_name(self):
        data = building(names=("debris_1a.001", "debris_1b"))
        new, lines = gr2_fit.fit(data, PARTS)
        self.assertEqual(len(new), len(data))
        self.assertTrue(gr2.crc_ok(new))
        self.assertEqual(names(new), ["body", "debris_1a", "debris_1b"])
        self.assertIn("  mesh   debris_1a.001 -> debris_1a", lines)
        self.assertTrue(any("still missing" in ln and "debris_9z" in ln for ln in lines))
        # nothing but the name's bytes changed (and the CRC)
        diff = [i for i in range(len(data)) if data[i] != new[i] and not 0x28 <= i < 0x2C]
        self.assertEqual(len(diff), 1)

    def test_a_mesh_on_another_bone_or_a_taken_name_is_left_alone(self):
        data = building(names=("debris_1b.001", "debris_1a"))     # debris_1b.001 is bound to
        new, lines = gr2_fit.fit(data, PARTS)                    # bone_debris_1a, not 1b
        self.assertIsNone(new)
        self.assertTrue(any("bound to bone_debris_1a" in ln for ln in lines), lines)
        data = building(names=("debris_1a.001", "debris_1a"))
        new, lines = gr2_fit.fit(data, PARTS)
        self.assertIsNone(new)
        self.assertTrue(any("already has a mesh debris_1a" in ln for ln in lines), lines)

    def test_a_shared_name_string_is_refused(self):
        data = bytearray(building(names=("debris_1a.001", "debris_1b")))
        doc = gr2.load(bytes(data))
        meshes = doc.root().get("Meshes")
        # point the body mesh's name at the debris mesh's string: one string, two pointers
        src = meshes[1]
        dst = doc.c.relocs[(src.at[0], src.at[1])]
        sec = doc.c.sections[meshes[0].at[0]]
        for k in range(sec.reloc_count):
            off = sec.reloc_offset + k * gr2.RELOCATION
            o, ts, to = struct.unpack_from("<3I", data, off)
            if o == meshes[0].at[1]:
                struct.pack_into("<3I", data, off, o, dst[0], dst[1])
        with self.assertRaises(gr2_fit.Refused):
            gr2_fit.fit(bytes(data), PARTS)


class RestTest(unittest.TestCase):
    def test_bones_take_the_reference_frames_and_nothing_moves(self):
        mine = building(frames={"bone_debris_1a": (TURN, None), "bone_debris_1b": (TURN, None)})
        ref = building(frames={"bone_debris_1a": (MIRROR_Q, MIRROR_S),
                               "bone_debris_1b": (MIRROR_Q, MIRROR_S)}, flag_shift=0.2)
        new, lines = gr2_fit.fit(mine, ref_data=ref)
        self.assertEqual(len(new), len(mine))
        self.assertTrue(gr2.crc_ok(new))
        old, got, want = frames(mine), frames(new), frames(ref)
        for name in ("bone_debris_1a", "bone_debris_1b"):
            for i in range(3):
                for j in range(3):
                    self.assertAlmostEqual(got[name].lin[i][j], want[name].lin[i][j], places=5)
            self.assertEqual(got[name].iw, want[name].iw)
        for name, b in got.items():             # every bone where it was, rest = bind
            for x, y in zip(b.pos, old[name].pos):
                self.assertAlmostEqual(x, y, places=4)
            self.assertLess(gr2_fit._inverse_error(b.lin, b.pos, b.iw), 1e-4, name)
        # the flag stands elsewhere in the reference: kept in its own frame under its new parent
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(got["bone_flag_civ"].lin[i][j], old["bone_flag_civ"].lin[i][j], places=5)
        self.assertEqual(got["bone_flag_civ"].iw, old["bone_flag_civ"].iw)
        self.assertTrue(any("bone_flag_civ" in ln and "recomputed" in ln for ln in lines), lines)

    def test_a_model_already_in_the_reference_frames_is_unchanged(self):
        ref = building(frames={"bone_debris_1a": (MIRROR_Q, MIRROR_S)})
        new, _ = gr2_fit.fit(ref, ref_data=ref)
        self.assertIsNone(new)

    def test_a_bone_whose_rest_is_not_its_bind_is_left_alone(self):
        mine = bytearray(building(frames={"bone_debris_1a": (TURN, None)}))
        b = frames(bytes(mine))["bone_debris_1a"]
        struct.pack_into("<f", mine, b.iw_at + 48, 5.0)     # a bind pose elsewhere
        struct.pack_into("<I", mine, 0x28, gr2.file_crc(mine))
        ref = building(frames={"bone_debris_1a": (MIRROR_Q, MIRROR_S)})
        new, lines = gr2_fit.fit(bytes(mine), ref_data=ref)
        self.assertTrue(any("bone_debris_1a: its rest pose is not its bind pose" in ln for ln in lines), lines)
        self.assertNotIn("bone_debris_1a", [ln.split()[1].rstrip(":") for ln in lines if ln.startswith("  bone ")])


class CliTest(unittest.TestCase):
    def test_dry_run_writes_nothing_and_a_run_writes_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "works_dmg.gr2")
            with open(src, "wb") as fh:
                fh.write(building(names=("debris_1a.001", "debris_1b"),
                                  frames={"bone_debris_1a": (TURN, None)}))
            ref = os.path.join(tmp, "ref.gr2")
            with open(ref, "wb") as fh:
                fh.write(building(frames={"bone_debris_1a": (MIRROR_Q, MIRROR_S)}))
            dmg = os.path.join(tmp, "x.dmg")
            with open(dmg, "w", encoding="utf-8") as fh:
                fh.write(TEMPLATE)
            before = read(src)
            code, out = run_cli(src, "--dmg", dmg, "--rest-from", ref, "--dry-run")
            self.assertEqual(code, 0, out)
            self.assertIn("dry run", out)
            self.assertEqual(read(src), before)
            dst = os.path.join(tmp, "out", "works_dmg.gr2")
            code, out = run_cli(src, "-o", dst, "--dmg", dmg, "--rest-from", ref)
            self.assertEqual(code, 0, out)
            new = read(dst)
            self.assertEqual(names(new), ["body", "debris_1a", "debris_1b"])
            self.assertTrue(gr2.crc_ok(new))
            code, out = run_cli(src)                  # neither --dmg nor --rest-from
            self.assertEqual(code, 2)

    def test_a_compiled_template_is_read(self):
        import xmbedit
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.dmg.xmb")
            with open(path, "wb") as fh:
                fh.write(xmbedit.encode(*xmbedit.from_xml(TEMPLATE.encode("utf-8"))))
            self.assertEqual(fit_borrowed.read_template(path), PARTS)


if __name__ == "__main__":
    unittest.main(verbosity=1)
