# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/fix_bone_scale.py on synthetic models only (plain Python).

    python -I tests/test_bone_scale.py

The fixture is a model written by gr2_write whose bones are then rewritten the way a centimetre
export stores them: the mesh bone turned and scaled by 100, the attach bones hanging from it with
a unit local scale, so their world axes are 100 long.
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
from aoe3game import gr2, gr2_write  # noqa: E402
import fix_bone_scale as fbs  # noqa: E402

Q90X = (math.sin(math.pi / 4), 0.0, 0.0, math.cos(math.pi / 4))     # 90 degrees about X
ATTACH = ("bone_flag_civ", "boneimpact01", "bone_launchpoint01")


def stock_model():
    P = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    T = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
    N = [(0, 0, 1)] * 4
    UV = [(0, 0), (1, 0), (0, 1), (1, 1)]
    return gr2_write.static_model("box", P, N, UV, T, texture="box.ddt", bump="flat.ddt",
                                  bones=[(n, (0.5 * k, 1.0, 2.0)) for k, n in enumerate(ATTACH)])


def bone_fields(data):
    """{name: (Transform offset, InverseWorld offset, ParentIndex offset)} in the file."""
    doc = gr2.load(data)
    out = {}
    for o in doc.root().get("Skeletons")[0].get("Bones"):
        base = doc.c.sections[o.at[0]].data_offset + o.at[1]
        out[o.get("Name")] = tuple(base + o.type.member(m).offset
                                   for m in ("Transform", "InverseWorldTransform", "ParentIndex"))
    return out


def scaled_model(scale=(100.0, 100.0, 100.0), scaled_bone="box"):
    """The stock model rebuilt as a centimetre export: `scaled_bone` turned by Q90X and scaled by
    `scale`, the attach bones hanging from "box" with a unit local scale and their world
    positions kept. With scaled_bone="bone_main" the root is scaled and "box" undoes it (world
    identity), so the attach bones are unit length and the root carries the mesh bone."""
    data = bytearray(stock_model())
    fields = bone_fields(bytes(data))
    sk = fbs.read_skeletons(gr2.load(bytes(data)))[0][1]
    world_pos = {b.name: list(b.pos) for b in sk}
    rot = fbs.quat_matrix(Q90X)
    s_tr, _, _ = fields[scaled_bone]
    struct.pack_into("<I3f4f9f", data, s_tr, 7, 0.0, 0.0, 0.0, *Q90X,
                     scale[0], 0, 0, 0, scale[1], 0, 0, 0, scale[2])
    if scaled_bone == "bone_main":
        qx, qy, qz, qw = Q90X                           # box = the root's inverse (uniform scale)
        struct.pack_into("<I3f4f9f", data, fields["box"][0], 7, 0.0, 0.0, 0.0, -qx, -qy, -qz, qw,
                         1 / scale[0], 0, 0, 0, 1 / scale[1], 0, 0, 0, 1 / scale[2])
        inv = [[1.0 if r == c else 0.0 for c in range(3)] for r in range(3)]
    else:
        inv = [[rot[c][r] / scale[r] for c in range(3)] for r in range(3)]     # box's world^-1
    for name in ATTACH:
        tr, _, par = fields[name]
        struct.pack_into("<i", data, par, 1)            # parent: "box"
        p = world_pos[name]
        local = [sum(inv[r][k] * p[k] for k in range(3)) for r in range(3)]
        struct.pack_into("<I3f4f", data, tr, 3, *local, 0.0, 0.0, 0.0, 1.0)
    # every inverse made consistent with the new rest pose
    sk = fbs.read_skeletons(gr2.load(bytes(data)))[0][1]
    for b in sk:
        _, iw, _ = fields[b.name]
        struct.pack_into("<16f", data, iw, *inverse_rows(b.lin, b.pos))
    struct.pack_into("<I", data, 0x28, gr2.file_crc(data))
    return bytes(data)


def inverse_rows(lin, pos):
    """The row-vector 4 x 4 inverse (Granny's InverseWorldTransform) of an affine frame."""
    a = lin
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
           - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
             - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det
            for j in range(3)] for i in range(3)]
    t = [-sum(inv[r][k] * pos[k] for k in range(3)) for r in range(3)]
    return [inv[0][0], inv[1][0], inv[2][0], 0, inv[0][1], inv[1][1], inv[2][1], 0,
            inv[0][2], inv[1][2], inv[2][2], 0, t[0], t[1], t[2], 1]


def bones_by_name(data):
    return {b.name: b for b in fbs.read_skeletons(gr2.load(data))[0][1]}


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fbs.main(list(argv))
    return code, out.getvalue()


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_a_centimetre_export(self):
        data = scaled_model()
        self.assertTrue(gr2.crc_ok(data))
        for b in bones_by_name(data).values():
            self.assertLess(fbs.inverse_error(b.lin, b.pos, b.iw), 1e-5, b.name)
        b = bones_by_name(data)
        for name in ATTACH:
            self.assertAlmostEqual(b[name].scale, 100.0, places=3)
        self.assertAlmostEqual(b["bone_main"].scale, 1.0)


class FixTest(unittest.TestCase):
    def test_attach_bones_get_unit_axes_and_keep_their_place(self):
        data = scaled_model()
        new, _ = fbs.fix_bytes(data)
        self.assertEqual(len(new), len(data))
        self.assertTrue(gr2.crc_ok(new))
        old, fixed = bones_by_name(data), bones_by_name(new)
        for name in ATTACH:
            o, n = old[name], fixed[name]
            for v in fbs.axis_lengths(n.lin):
                self.assertAlmostEqual(v, 1.0, places=5)
            for a, c in zip(o.pos, n.pos):
                self.assertAlmostEqual(a, c, places=4)
            for r in range(3):           # same directions
                for c in range(3):
                    self.assertAlmostEqual(o.lin[r][c] / 100.0, n.lin[r][c], places=5)
            self.assertLess(fbs.inverse_error(n.lin, n.pos, n.iw), 1e-5)
            self.assertEqual(n.tr["flags"] & fbs.HAS_SCALE_SHEAR, fbs.HAS_SCALE_SHEAR)
            self.assertEqual(n.tr["position"], o.tr["position"])
            self.assertEqual(n.tr["orientation"], o.tr["orientation"])
        for name in ("bone_main", "box"):        # the root and the mesh bone: untouched
            self.assertEqual(fixed[name].tr, old[name].tr)
            self.assertEqual(fixed[name].iw, old[name].iw)

    def test_only_the_fixed_bones_change_in_the_tree(self):
        data = scaled_model()
        new, _ = fbs.fix_bytes(data)
        before = gr2.dump_tree(gr2.load(data))
        after = gr2.dump_tree(gr2.load(new))
        changed = {a.split(" = ")[0] for a, b in zip(before, after) if a != b}
        self.assertEqual(len(before), len(after))
        expect = {f"Skeletons[0].Bones[{i}].{m}" for i in (2, 3, 4)
                  for m in ("Transform", "InverseWorldTransform")}
        self.assertEqual(changed, expect)

    def test_a_second_run_changes_nothing(self):
        new, _ = fbs.fix_bytes(scaled_model())
        again, skeletons = fbs.fix_bytes(new)
        self.assertIsNone(again)
        self.assertFalse(any(b.chosen for _, bones in skeletons for b in bones))

    def test_a_stock_model_is_left_alone(self):
        new, _ = fbs.fix_bytes(stock_model())
        self.assertIsNone(new)

    def test_a_scale_under_the_factor_is_left_alone(self):
        for k in (0.92, 4.0, 0.25):                         # stock models have such bones
            self.assertIsNone(fbs.fix_bytes(scaled_model(scale=(k, k, k)))[0], k)
        new, _ = fbs.fix_bytes(scaled_model(scale=(4.0, 4.0, 4.0)), factor=2.0)
        self.assertAlmostEqual(bones_by_name(new)["boneimpact01"].scale, 1.0, places=5)

    def test_a_small_scale_is_fixed_too(self):
        new, _ = fbs.fix_bytes(scaled_model(scale=(0.01, 0.01, 0.01)))
        for name in ATTACH:
            self.assertAlmostEqual(bones_by_name(new)[name].scale, 1.0, places=4)

    def test_an_inverse_that_is_a_bind_pose_takes_the_same_change(self):
        data = bytearray(scaled_model())
        _, iw, _ = bone_fields(bytes(data))["boneimpact01"]
        struct.pack_into("<f", data, iw + 48, 0.123)     # translation row: not the rest pose
        struct.pack_into("<I", data, 0x28, gr2.file_crc(data))
        new, skeletons = fbs.fix_bytes(bytes(data))
        b = {x.name: x for x in skeletons[0][1]}["boneimpact01"]
        self.assertTrue(b.chosen and b.bind)
        after = bones_by_name(new)["boneimpact01"].iw
        for k in fbs.IW_AFFINE:
            self.assertAlmostEqual(after[k], b.iw[k] * b.scale, places=3)

    def test_bones_narrows_the_choice(self):
        new, skeletons = fbs.fix_bytes(scaled_model(), bones_re=r"^boneimpact")
        chosen = [b.name for _, bones in skeletons for b in bones if b.chosen]
        self.assertEqual(chosen, ["boneimpact01"])
        b = bones_by_name(new)
        self.assertAlmostEqual(b["boneimpact01"].scale, 1.0, places=5)
        self.assertAlmostEqual(b["bone_flag_civ"].scale, 100.0, places=3)

    def test_a_mesh_bone_is_never_chosen(self):
        _, skeletons = fbs.fix_bytes(scaled_model(), bones_re="box")
        self.assertFalse(any(b.chosen for _, bones in skeletons for b in bones))


class RefusalTest(unittest.TestCase):
    def test_compressed_sections(self):
        data = bytearray(scaled_model())
        sec_at = 0x20 + struct.unpack_from("<I", data, 0x2C)[0]
        struct.pack_into("<I", data, sec_at, 2)          # Oodle1
        with self.assertRaises(gr2.Compressed):
            fbs.fix_bytes(bytes(data))
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "m.gr2")
            with open(p, "wb") as fh:
                fh.write(data)
            code, text = run_cli(p)
            self.assertEqual(code, 1)
            self.assertIn("compressed", text)
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), bytes(data))
            self.assertFalse(os.path.exists(p + ".bak"))

    def test_a_bad_factor(self):
        self.assertEqual(run_cli("a.gr2", "--factor", "1")[0], 2)


class LeftAloneTest(unittest.TestCase):
    def test_uneven_scale(self):
        new, skeletons = fbs.fix_bytes(scaled_model(scale=(100.0, 50.0, 100.0)))
        self.assertIsNone(new)
        lines = "\n".join(fbs.report(skeletons))
        self.assertIn("kept   boneimpact01", lines)
        self.assertIn("scaled unevenly", lines)

    def test_a_scaled_root_over_a_mesh_bone_is_left_and_the_rest_judged_alone(self):
        new, skeletons = fbs.fix_bytes(scaled_model(scaled_bone="bone_main"))
        self.assertIsNone(new)                       # the attach bones are unit already
        root = skeletons[0][1][0]
        self.assertFalse(root.chosen)
        self.assertIn("box hangs from it", root.reason)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "art", "b")
        os.makedirs(os.path.join(self.dir, "sub"))
        self.scaled = scaled_model()
        self.stock = stock_model()
        for rel, data in (("a.gr2", self.scaled), (os.path.join("sub", "B.GR2"), self.scaled),
                          ("c.gr2", self.stock)):
            with open(os.path.join(self.dir, rel), "wb") as fh:
                fh.write(data)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *parts):
        with open(os.path.join(*parts), "rb") as fh:
            return fh.read()

    def test_a_dry_run_lists_and_writes_nothing(self):
        code, text = run_cli(self.dir, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("fixed  boneimpact01: axes 100 -> 1", text)
        self.assertIn("3 files: 2 to fix (6 bones), 1 with nothing to change, 0 refused", text)
        self.assertEqual(self.read(self.dir, "a.gr2"), self.scaled)
        self.assertEqual(sorted(os.listdir(self.dir)), ["a.gr2", "c.gr2", "sub"])

    def test_a_folder_to_an_output_folder(self):
        out = os.path.join(self.tmp.name, "out")
        code, text = run_cli(self.dir, "-o", out)
        self.assertEqual(code, 0)
        self.assertEqual(self.read(out, "a.gr2"), fbs.fix_bytes(self.scaled)[0])
        self.assertEqual(self.read(out, "sub", "B.GR2"), fbs.fix_bytes(self.scaled)[0])
        self.assertFalse(os.path.exists(os.path.join(out, "c.gr2")))
        self.assertEqual(self.read(self.dir, "a.gr2"), self.scaled)

    def test_in_place_keeps_a_backup(self):
        p = os.path.join(self.dir, "a.gr2")
        code, _ = run_cli(p)
        self.assertEqual(code, 0)
        self.assertEqual(self.read(p + ".bak"), self.scaled)
        self.assertEqual(self.read(p), fbs.fix_bytes(self.scaled)[0])
        code, text = run_cli(p)                          # nothing left to do, backup kept
        self.assertIn("1 with nothing to change", text)
        self.assertEqual(self.read(p + ".bak"), self.scaled)

    def test_usage(self):
        self.assertEqual(run_cli()[0], 2)
        self.assertEqual(run_cli("a.gr2", "b.gr2", "-o", "x")[0], 2)
        self.assertEqual(run_cli("a.gr2", "--granny", "x.exe")[0], 2)


if __name__ == "__main__":
    unittest.main()
