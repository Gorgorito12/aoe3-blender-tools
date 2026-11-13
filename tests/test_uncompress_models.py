# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/uncompress_models.py on a synthetic game folder (plain Python).

    python -I tests/test_uncompress_models.py

The archives are written here in the .bar layout tools/bar.py reads; the models are gr2_write's,
with their section "compressed" by zlib under the Oodle1 code, and a fake bridge expands them the
way the real one does (every section rewritten uncompressed, the rest of the file kept).
"""
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_write  # noqa: E402
import bar  # noqa: E402
import uncompress_models as um  # noqa: E402


def raw_model(name="box", size=1.0):
    P = [(0, 0, 0), (size, 0, 0), (0, size, 0), (0, 0, size)]
    T = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
    return gr2_write.static_model(name, P, [(0, 0, 1)] * 4, [(0, 0), (1, 0), (0, 1), (1, 1)], T,
                                  texture="box.ddt", bump="flat.ddt")


def compress(data):
    """The model with its (single, last) section stored zlib-compressed under code 2."""
    sec_at = 0x20 + struct.unpack_from("<I", data, 0x2C)[0]
    s = list(struct.unpack_from("<11I", data, sec_at))
    assert s[1] + s[2] == len(data)
    packed = zlib.compress(data[s[1]:s[1] + s[2]])
    out = bytearray(data[:s[1]]) + packed
    s[0], s[2] = 2, len(packed)
    struct.pack_into("<11I", out, sec_at, *s)
    struct.pack_into("<I", out, 0x24, len(out))
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


def fake_expand(data, lose_root_type=False, break_relocs=False):
    sec_at = 0x20 + struct.unpack_from("<I", data, 0x2C)[0]
    s = list(struct.unpack_from("<11I", data, sec_at))
    body = zlib.decompress(data[s[1]:s[1] + s[2]]) if s[0] == 2 else data[s[1]:s[1] + s[2]]
    out = bytearray(data[:s[1]]) + body
    s[0], s[2] = 0, len(body)
    struct.pack_into("<11I", out, sec_at, *s)
    struct.pack_into("<I", out, 0x24, len(out))
    if lose_root_type:                       # as the runtime's own recompress call writes it
        struct.pack_into("<2I", out, um.ROOT_TYPE, 7, 7)
    if break_relocs:
        out[s[7]] ^= 1
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


class FakeBridge:
    """Stands in for run_bridge; records the calls."""

    def __init__(self, **kw):
        self.kw, self.calls, self.fail = kw, 0, set()

    def __call__(self, exe, install, src, out, cwd):
        self.calls += 1
        with open(src, "rb") as fh:
            data = fh.read()
        if data in self.fail:
            raise um.Refused("the bridge refused (exit 4)")
        with open(out, "wb") as fh:
            fh.write(fake_expand(data, **self.kw))


def write_bar(path, files):
    """files: [(name below Art\\, bytes)]."""
    body, entries = bytearray(), []
    for name, data in files:
        entries.append((0x124 + len(body), len(data), name))
        body += data
    table = bytearray()
    root = "Art\\"
    table += struct.pack("<I", len(root)) + root.encode("utf-16-le")
    table += struct.pack("<I", len(entries))
    for off, size, name in entries:
        table += struct.pack("<3I", off, size, size) + bytes(16)
        table += struct.pack("<I", len(name)) + name.encode("utf-16-le")
    head = bytearray(0x124)
    head[:4] = b"ESPN"
    struct.pack_into("<2I", head, 0x118, len(entries), 0x124 + len(body))
    with open(path, "wb") as fh:
        fh.write(head + body + table)


def listing(folder):
    out = {}
    for base, dirs, names in os.walk(folder):
        for d in dirs:
            out[os.path.relpath(os.path.join(base, d), folder)] = None
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, folder)] = zlib.crc32(fh.read())
    return out


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = um.main(list(argv))
    return code, buf.getvalue()


class GameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = os.path.join(self.tmp.name, "game")
        art = os.path.join(self.game, "art")
        os.makedirs(os.path.join(art, "units", "own"))
        os.makedirs(os.path.join(self.game, "data"))
        self.a = compress(raw_model("a", 1.0))
        self.b = compress(raw_model("b", 2.0))
        self.own_stored = compress(raw_model("own", 3.0))
        self.mod_file = raw_model("mod", 4.0)
        self.raw = raw_model("raw", 5.0)
        write_bar(os.path.join(art, "Art1.bar"), [
            ("units\\new\\a.gr2", self.a), ("units\\own\\own.gr2", self.own_stored),
            ("units\\raw.gr2", self.raw), ("units\\twice.gr2", self.a),
            ("units\\same.gr2", self.b), ("units\\tex.ddt", b"not a model")])
        write_bar(os.path.join(art, "Art4.bar"), [
            ("units\\twice.gr2", self.b), ("units\\same.gr2", self.b),
            ("effects\\b.gr2", self.b)])
        with open(os.path.join(art, "units", "own", "own.gr2"), "wb") as fh:
            fh.write(self.mod_file)                       # the mod's own loose model
        self.before = listing(self.game)
        self.bridge = FakeBridge(lose_root_type=True)
        self.saved, um.run_bridge = um.run_bridge, self.bridge

    def tearDown(self):
        um.run_bridge = self.saved
        self.tmp.cleanup()

    def path(self, rel):
        return os.path.join(self.game, "art", *rel.split("\\"))

    def read(self, rel):
        with open(self.path(rel), "rb") as fh:
            return fh.read()

    def install(self, *extra):
        return run(self.game, "--install", "--granny", "bridge.exe", "--workers", "2", *extra)

    def test_plan_writes_nothing(self):
        code, out = run(self.game)
        self.assertEqual(code, 0)
        self.assertIn("3 to write", out)
        self.assertEqual(listing(self.game), self.before)

    def test_install_check_undo(self):
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertIn("3 written", out)
        self.assertIn("1 loose", out)
        self.assertIn("1 already uncompressed", out)
        self.assertIn("1 stored differently", out)
        self.assertIn("3 had their root type reference put back", out)
        for rel, src in (("units\\new\\a.gr2", self.a), ("units\\same.gr2", self.b),
                         ("effects\\b.gr2", self.b)):
            copy = self.read(rel)
            self.assertTrue(um.is_raw(copy))
            self.assertTrue(gr2.crc_ok(copy))
            self.assertEqual(copy[um.ROOT_TYPE:um.ROOT_TYPE + 8], src[um.ROOT_TYPE:um.ROOT_TYPE + 8])
            self.assertEqual(copy, fake_expand(src))
            gr2.load(copy).root()
        self.assertEqual(self.read("units\\own\\own.gr2"), self.mod_file)
        self.assertFalse(os.path.exists(self.path("units\\raw.gr2")))
        self.assertFalse(os.path.exists(self.path("units\\twice.gr2")))
        with open(os.path.join(self.game, um.MANIFEST), encoding="utf-8") as fh:
            recs = [json.loads(line) for line in fh]
        self.assertEqual(sorted(r["kind"] for r in recs), ["dir", "dir", "file", "file", "file",
                                                           "header"])
        self.assertEqual(run(self.game, "--check")[0], 0)

        calls = self.bridge.calls
        code, out = self.install()                       # nothing changed: nothing to do
        self.assertEqual(code, 0, out)
        self.assertIn("0 written", out)
        self.assertIn("3 kept", out)
        self.assertEqual(self.bridge.calls, calls)

        code, out = run(self.game, "--undo")
        self.assertEqual(code, 0, out)
        self.assertIn("removed 3 copies", out)
        self.assertEqual(listing(self.game), self.before)

    def test_check_finds_a_changed_copy_and_undo_leaves_it(self):
        self.install()
        with open(self.path("effects\\b.gr2"), "ab") as fh:
            fh.write(b"x")
        code, out = run(self.game, "--check")
        self.assertEqual(code, 1)
        self.assertIn("changed: Art\\effects\\b.gr2", out)
        code, out = run(self.game, "--undo")
        self.assertIn("1 changed since and left in place", out)
        self.assertTrue(os.path.exists(self.path("effects\\b.gr2")))
        self.assertFalse(os.path.exists(self.path("units\\new\\a.gr2")))
        self.assertFalse(os.path.exists(os.path.join(self.game, um.MANIFEST)))

    def test_a_replaced_copy_becomes_the_mods(self):
        self.install()
        with open(self.path("units\\same.gr2"), "wb") as fh:
            fh.write(self.mod_file)
        code, out = self.install()
        self.assertIn("1 of our copies were replaced", out)
        run(self.game, "--undo")
        self.assertEqual(self.read("units\\same.gr2"), self.mod_file)

    def test_a_patched_archive_is_followed(self):
        self.install()
        c = compress(raw_model("c", 6.0))
        write_bar(os.path.join(self.game, "art", "Art4.bar"), [
            ("units\\twice.gr2", self.b), ("units\\same.gr2", self.b), ("effects\\b.gr2", c)])
        self.assertEqual(run(self.game, "--check")[0], 1)
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertIn("1 written", out)
        self.assertEqual(self.read("effects\\b.gr2"), fake_expand(c))
        self.assertEqual(run(self.game, "--check")[0], 0)

    def test_only_used(self):
        log = os.path.join(self.tmp.name, "game.log")
        with open(log, "w", encoding="utf-16") as fh:
            fh.write("perfFileLog: 3 reads (1 of 16 B or less), 900 B, 2 ReadFile calls, 0.1 ms "
                     "reading; opened at t=1.000 s, for 0.2 ms: Art\\Units\\New\\a.gr2\n"
                     "perfFileLog: 1 reads ...: data\\protoy.xml\n"
                     f"{self.game}\\art\\units\\own\\own.gr2\n")
        self.assertEqual(um.used_list(log, self.game),
                         {"art\\units\\new\\a.gr2", "art\\units\\own\\own.gr2"})
        self.install()
        code, out = self.install("--only-used", log)
        self.assertEqual(code, 0, out)
        self.assertIn("removed 2 of our copies", out)
        self.assertTrue(os.path.exists(self.path("units\\new\\a.gr2")))
        self.assertFalse(os.path.exists(self.path("units\\same.gr2")))
        self.assertFalse(os.path.exists(self.path("effects")))  # its folder went with the undo below
        run(self.game, "--undo")
        self.assertEqual(listing(self.game), self.before)

    def test_a_refused_copy_is_not_written(self):
        self.bridge.fail.add(self.b)
        code, out = self.install()
        self.assertEqual(code, 1)
        self.assertIn("2 failed", out)
        self.assertFalse(os.path.exists(self.path("units\\same.gr2")))
        self.assertTrue(os.path.exists(self.path("units\\new\\a.gr2")))
        run(self.game, "--undo")
        self.assertEqual(listing(self.game), self.before)

    def test_refusals(self):
        steam = os.path.join(self.tmp.name, "Steam", "steamapps", "common", "game")
        os.makedirs(steam)
        self.assertEqual(run(steam, "--check")[0], 2)
        self.assertEqual(run(self.tmp.name, "--check")[0], 2)        # no archives
        self.assertEqual(run(self.game, "--install")[0], 2)          # no bridge
        self.assertEqual(run(self.game, "--install", "--undo")[0], 2)


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.src = compress(raw_model())

    def test_good_copy(self):
        um.verify(self.src, fake_expand(self.src))

    def test_header_fix(self):
        lost = fake_expand(self.src, lose_root_type=True)
        with self.assertRaises(um.Refused):
            um.verify(self.src, lost)
        fixed, changed = um.fix_header(self.src, lost)
        self.assertTrue(changed)
        um.verify(self.src, fixed)
        self.assertEqual(fixed, fake_expand(self.src))

    def test_refusals(self):
        with self.assertRaises(um.Refused):
            um.verify(self.src, fake_expand(self.src, break_relocs=True))
        bad_crc = bytearray(fake_expand(self.src))
        bad_crc[-1] ^= 1
        with self.assertRaises(um.Refused):
            um.verify(self.src, bytes(bad_crc))
        with self.assertRaises(um.Refused):
            um.verify(self.src, self.src)                            # still compressed
        raw = raw_model()
        changed = bytearray(raw)
        changed[-2] ^= 1
        struct.pack_into("<I", changed, 0x28, gr2.file_crc(changed))
        with self.assertRaises(um.Refused):
            um.verify(raw, bytes(changed))                           # a raw section changed
        with self.assertRaises(um.Refused):
            um.verify(self.src, b"not a model" * 10)

    def test_bar_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "Art9.bar")
            write_bar(p, [("x\\y.gr2", b"abc")])
            self.assertEqual(bar.read_entries(p), [("Art\\x\\y.gr2", 0x124, 3)])


if __name__ == "__main__":
    unittest.main()
