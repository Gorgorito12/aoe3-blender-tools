# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of tools/recompress_models.py on synthetic files (plain Python).

    python -I tests/test_recompress_models.py

The Granny runtime is replaced by a fake that rewrites a file the way GrannyRecompressFile does
(sections, records and fixups kept, each section stored in the mapped format, the runtime's packed
layout, the root type reference written as 0:0), with zlib standing in for Oodle. The real runtime
is never needed.
"""
import contextlib
import io
import os
import random
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import gr2, gr2_write  # noqa: E402
import recompress_models as rm  # noqa: E402

ROOT_TYPE_WORDS = struct.pack("<2I", 0, 0x40)


def expanded(data):
    """[(record values, relocs, marshal, expanded bytes)] of a file (zlib for formats 1 and 2)."""
    _, sections, relocs, marshal = rm.layout(data)
    out = []
    sec_off = struct.unpack_from("<I", data, 0x2C)[0]
    for i, s in enumerate(sections):
        body = data[s.data_offset:s.data_offset + s.data_size]
        if s.compression and s.data_size:
            body = zlib.decompress(body)
        values = list(struct.unpack_from("<11I", data, 0x20 + sec_off + i * gr2.SECTION_RECORD))
        out.append((values, relocs[i], marshal[i], body))
    return out


def build(data, parts, fmt_of, root):
    """The file `data` rebuilt from `parts` with section i stored as fmt_of(i, bytes)."""
    sec_off, n = struct.unpack_from("<2I", data, 0x2C)
    head = 0x20 + sec_off + n * gr2.SECTION_RECORD
    out = bytearray(data[:head])
    for i, (values, relocs, marshal, body) in enumerate(parts):
        fmt = fmt_of(i, body)
        stored = body if fmt == 0 or not body else zlib.compress(body, 1 if fmt == 1 else 9)
        values = list(values)
        values[0], values[2] = fmt, len(stored)
        values[7] = len(out)
        out += relocs
        values[9] = len(out)
        out += marshal
        values[1] = len(out)
        out += stored
        struct.pack_into("<11I", out, 0x20 + sec_off + i * gr2.SECTION_RECORD, *values)
    struct.pack_into("<I", out, 0x24, len(out))
    out[rm.ROOT_TYPE:rm.ROOT_TYPE + 8] = root
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


class FakeRuntime:
    """Stands in for rm.Runtime (granny2.dll through the helper)."""

    def __init__(self, *args, break_expand=False, bad_crc=False, zero_object=False):
        self.calls, self.break_expand, self.bad_crc = [], break_expand, bad_crc
        self.zero_object = zero_object      # the real runtime writes the root object as 0:0 too

    def recompress(self, data, fmt, tag):
        self.calls.append(fmt)
        parts = expanded(data)
        if self.break_expand and fmt == 0 and self.calls.count(0) > 1:
            values, relocs, marshal, body = parts[0]
            parts[0] = (values, relocs, marshal, body[:-1] + bytes([body[-1] ^ 1]))
        out = build(data, parts, lambda i, b: fmt, bytes(8))
        if self.zero_object:
            out = rm.put_ref(out, rm.ROOT_OBJECT, bytes(8))
        return out

    def crc_ok(self, data, tag):
        return gr2.crc_ok(data) and not self.bad_crc


def model(sections=1, noise=None):
    """A synthetic Granny file: a static model's header, `sections` sections of compressible
    bytes with fixups (section `noise` holds random bytes, which do not compress), stored raw and
    in the bridge's layout (data aligned to the section's alignment), root type at 0:0x40."""
    base = gr2_write.static_model("box", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 1)] * 3,
                                  [(0, 0), (1, 0), (0, 1)], [(0, 1, 2)], texture="a.ddt",
                                  bump="b.ddt")
    rnd = random.Random(7)
    sec_off = struct.unpack_from("<I", base, 0x2C)[0]
    head = bytearray(base[:0x20 + sec_off]) + bytes(sections * gr2.SECTION_RECORD)
    struct.pack_into("<I", head, 0x30, sections)
    out = bytearray(head)
    for i in range(sections):
        size = 0 if i == sections - 1 and sections > 2 else 400 + 64 * i
        body = bytes(rnd.randrange(256) for _ in range(size)) if i == noise else \
            ((b"granny section %d " % i) * size)[:size]
        relocs = b"".join(struct.pack("<3I", 4 * k, i, 8 * k) for k in range(3 + i))
        align = 16 if i == 0 else 4
        reloc_at = len(out)
        out += relocs
        while len(out) % align:
            out += b"\0"
        data_at = len(out)
        out += body
        struct.pack_into("<11I", out, 0x20 + sec_off + i * gr2.SECTION_RECORD, 0, data_at, size,
                         size, align, size // 2, size, reloc_at, len(relocs) // 12, data_at, 0)
    struct.pack_into("<I", out, 0x24, len(out))
    out[rm.ROOT_TYPE:rm.ROOT_TYPE + 8] = ROOT_TYPE_WORDS
    struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
    return bytes(out)


def formats(data):
    return [s.compression for s in rm.layout(data)[1]]


class RecompressTests(unittest.TestCase):
    def test_one_section_to_oodle1(self):
        raw = model()
        out, targets = rm.recompress(raw, FakeRuntime(), 2, None, 0)
        self.assertEqual(targets, [2])
        self.assertEqual(formats(out), [2])
        self.assertLess(len(out), len(raw))
        self.assertEqual(out[rm.ROOT_TYPE:rm.ROOT_TYPE + 8], ROOT_TYPE_WORDS)   # put back
        self.assertTrue(gr2.crc_ok(out))
        self.assertEqual([p[3] for p in expanded(out)], [p[3] for p in expanded(raw)])

    def test_the_root_object_is_put_back(self):
        # a model gr2_write laid out keeps its root object after its types; the runtime writes
        # that reference as 0:0, and the game exits on such a file (in game, 2026-11-20)
        raw = model()
        obj = raw[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8]
        self.assertNotEqual(obj, bytes(8))
        out, _ = rm.recompress(raw, FakeRuntime(zero_object=True), 2, None, 0)
        self.assertEqual(out[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8], obj)
        self.assertEqual(out[rm.ROOT_TYPE:rm.ROOT_TYPE + 8], ROOT_TYPE_WORDS)
        self.assertTrue(gr2.crc_ok(out))
        # a written gr2_write file goes through the same way
        real = gr2_write.static_model("box", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 1)] * 3,
                                      [(0, 0), (1, 0), (0, 1)], [(0, 1, 2)], texture="a.ddt", bump="b.ddt")
        real = bytearray(real)
        struct.pack_into("<I", real, rm.TYPE_TAG, 0x80000013)
        struct.pack_into("<I", real, 0x28, gr2.file_crc(real))
        out, _ = rm.recompress(bytes(real), FakeRuntime(zero_object=True), 2, None, 0)
        self.assertEqual(out[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8], real[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8])

    def test_strings_moved_to_four_bytes_keep_the_root_object(self):
        # what the runtime does to a gr2_write file whose strings start on 2: two bytes before them
        def shifted(data):
            sec_off = struct.unpack_from("<I", data, 0x2C)[0]
            rec = list(struct.unpack_from("<11I", data, 0x20 + sec_off))
            body = bytearray(data[rec[1]:rec[1] + rec[2]])
            f8 = rec[6]
            body[f8:f8] = b"\0\0"
            body += b"\0\0"
            out = bytearray(data[:rec[1]]) + body
            n = rec[8]
            for k in range(n):                                  # fixups into the strings move with them
                at = rec[7] + 12 * k
                src, s, tgt = struct.unpack_from("<3I", out, at)
                struct.pack_into("<3I", out, at, src + (2 if src >= f8 else 0), s, tgt + (2 if tgt >= f8 else 0))
            rec[2] = rec[3] = len(body)
            rec[6] = f8 + 2
            struct.pack_into("<11I", out, 0x20 + sec_off, *rec)
            struct.pack_into("<I", out, 0x24, len(out))
            out[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8] = bytes(8)
            struct.pack_into("<I", out, 0x28, gr2.file_crc(out))
            return bytes(out)

        real = bytearray(gr2_write.static_model("box", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 1)] * 3,
                                                [(0, 0), (1, 0), (0, 1)], [(0, 1, 2)], texture="a.ddt", bump="b.ddt"))
        sec_off = struct.unpack_from("<I", real, 0x2C)[0]
        f8 = struct.unpack_from("<11I", real, 0x20 + sec_off)[6]
        if f8 % 4 == 0:
            self.skipTest("this writer's strings start on 4 already")
        obj = bytes(real[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8])
        rm.same_data(bytes(real), shifted(bytes(real)), obj)                       # accepted
        with self.assertRaises(rm.Refused):                                          # an object past the strings
            rm.same_data(bytes(real), shifted(bytes(real)), struct.pack("<2I", 0, f8 + 4))
        bad = bytearray(shifted(bytes(real)))
        bad[struct.unpack_from("<11I", bad, 0x20 + sec_off)[1] + 8] ^= 1          # anything else changed
        with self.assertRaises(rm.Refused):
            rm.same_data(bytes(real), bytes(bad), obj)

    def test_the_root_object_is_not_guessed_when_the_runtime_moved_the_data(self):
        raw = model()

        class Moving(FakeRuntime):
            def recompress(self, data, fmt, tag):
                out = super().recompress(data, fmt, tag)
                if fmt == 0:                                   # its own layout: the bytes differ
                    parts = expanded(out)
                    values, relocs, marshal, body = parts[0]
                    parts[0] = (values, relocs, marshal, body[4:] + body[:4])
                    out = rm.put_ref(build(out, parts, lambda i, b: 0, bytes(8)), rm.ROOT_OBJECT, bytes(8))
                return out

        with self.assertRaises(rm.Refused):
            rm.recompress(raw, Moving(zero_object=True), 2, None, 0)

    def test_incompressible_section_stays_raw_and_empty_takes_the_format(self):
        raw = model(sections=4, noise=1)
        out, targets = rm.recompress(raw, FakeRuntime(), 2, None, 0)
        self.assertEqual(targets, [2, 0, 2, 2])
        self.assertEqual(formats(out), [2, 0, 2, 2])
        s = rm.layout(out)[1][1]
        r = rm.layout(raw)[1][1]
        self.assertEqual(out[s.data_offset:s.data_offset + s.data_size],
                         raw[r.data_offset:r.data_offset + r.data_size])
        self.assertTrue(gr2.crc_ok(out))

    def test_like_keeps_the_originals_formats(self):
        raw = model(sections=3)
        original = build(raw, expanded(raw), lambda i, b: [2, 0, 1][i], ROOT_TYPE_WORDS)
        rt = FakeRuntime()
        out, targets = rm.recompress(raw, rt, 2, (original, rm.layout(original)[1]), 0)
        self.assertEqual(targets, [2, 0, 1])
        self.assertEqual(formats(out), [2, 0, 1])
        self.assertEqual(sorted(set(rt.calls)), [0, 1, 2])
        self.assertEqual([p[3] for p in expanded(out)], [p[3] for p in expanded(raw)])
        self.assertEqual(out, original)      # same compressor, same layout: the same bytes

    def test_like_takes_the_root_type_when_the_input_lost_it(self):
        raw = model()
        lost = bytearray(raw)
        lost[rm.ROOT_TYPE:rm.ROOT_TYPE + 8] = bytes(8)
        struct.pack_into("<I", lost, 0x28, gr2.file_crc(lost))
        out, _ = rm.recompress(bytes(lost), FakeRuntime(), 2, (raw, rm.layout(raw)[1]), 0)
        self.assertEqual(out[rm.ROOT_TYPE:rm.ROOT_TYPE + 8], ROOT_TYPE_WORDS)

    def test_like_refuses_other_sections(self):
        raw, other = model(sections=1), model(sections=3)
        with self.assertRaises(rm.Refused):
            rm.recompress(raw, FakeRuntime(), 2, (other, rm.layout(other)[1]), 0)

    def test_refuses_a_result_that_does_not_expand_back(self):
        with self.assertRaisesRegex(rm.Refused, "expand"):
            rm.recompress(model(), FakeRuntime(break_expand=True), 2, None, 0)

    def test_refuses_when_the_runtime_rejects_the_crc(self):
        with self.assertRaisesRegex(rm.Refused, "CRC"):
            rm.recompress(model(), FakeRuntime(bad_crc=True), 2, None, 0)

    def test_an_old_type_tag_is_taken_and_read_back(self):
        old = bytearray(model())
        struct.pack_into("<I", old, rm.TYPE_TAG, 0x80000010)
        struct.pack_into("<I", old, 0x28, gr2.file_crc(old))

        class Reading(FakeRuntime):
            def __init__(self, differ=False, **kw):
                super().__init__(**kw)
                self.differ = differ

            def info(self, data, tag):
                reads = data[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8] != bytes(8)
                compressed = any(s.compression for s in rm.layout(data)[1])
                return (0, ["mesh box"] if reads and not (self.differ and compressed) else ["?"])

        out, _ = rm.recompress(bytes(old), Reading(zero_object=True), 2, None, 0)
        self.assertEqual(out[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8], old[rm.ROOT_OBJECT:rm.ROOT_OBJECT + 8])
        with self.assertRaisesRegex(rm.Refused, "does not read the result"):
            rm.recompress(bytes(old), Reading(differ=True, zero_object=True), 2, None, 0)

    def test_verify_refuses_changed_fixups(self):
        raw = FakeRuntime().recompress(model(), 0, 0)
        out, targets = rm.recompress(model(), FakeRuntime(), 2, None, 0)
        bad = bytearray(out)
        bad[rm.layout(out)[1][0].reloc_offset] ^= 1
        struct.pack_into("<I", bad, 0x28, gr2.file_crc(bad))
        with self.assertRaisesRegex(rm.Refused, "fixups"):
            rm.verify(raw, bytes(bad), targets, ROOT_TYPE_WORDS)

    def test_assemble_of_one_format_is_the_runtimes_file(self):
        raw = model(sections=3)
        c = FakeRuntime().recompress(raw, 2, 0)
        a = rm.assemble({2: c}, [2, 2, 2])
        self.assertEqual(a[:0x28] + a[0x2C:], c[:0x28] + c[0x2C:])     # all but the stale CRC


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.game = os.path.join(self.dir, "game")
        os.makedirs(self.game)
        open(os.path.join(self.game, "granny2.dll"), "wb").close()
        self.helper = os.path.join(self.dir, "helper.exe")
        open(self.helper, "wb").close()
        self.saved = rm.Runtime
        rm.Runtime = FakeRuntime

    def tearDown(self):
        rm.Runtime = self.saved
        self.tmp.cleanup()

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rm.main(list(argv) + ["--granny-install", self.game, "--helper", self.helper])
        return code, buf.getvalue()

    def write(self, rel, data):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_folder_with_like(self):
        raw = model(sections=3)
        original = build(raw, expanded(raw), lambda i, b: [2, 0, 2][i], ROOT_TYPE_WORDS)
        self.write("in/art/a/House.gr2", raw)
        self.write("in/art/b/x_Model.GR2", model())
        self.write("orig/art/A/house.gr2", original)
        self.write("orig/art/b/x_model.gr2", build(model(), expanded(model()),
                                                   lambda i, b: 2, ROOT_TYPE_WORDS))
        self.write("in/art/readme.txt", b"not a model")
        code, text = self.run_main(os.path.join(self.dir, "in"), "-o",
                                   os.path.join(self.dir, "out"), "--like",
                                   os.path.join(self.dir, "orig"))
        self.assertEqual(code, 0, text)
        self.assertIn("2 written, 0 refused", text)
        with open(os.path.join(self.dir, "out", "art", "a", "House.gr2"), "rb") as fh:
            self.assertEqual(formats(fh.read()), [2, 0, 2])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out", "art", "readme.txt")))

    def test_missing_original_is_refused(self):
        self.write("in/m.gr2", model())
        os.makedirs(os.path.join(self.dir, "orig"))
        code, text = self.run_main(os.path.join(self.dir, "in"), "-o",
                                   os.path.join(self.dir, "out"), "--like",
                                   os.path.join(self.dir, "orig"))
        self.assertEqual(code, 1)
        self.assertIn("no original", text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out", "m.gr2")))

    def test_refuses_overwriting_the_input(self):
        path = self.write("in/m.gr2", model())
        code, text = self.run_main(path, "-o", path)
        self.assertEqual(code, 2)
        self.assertIn("overwrite", text)

    def test_refuses_a_steam_output(self):
        path = self.write("in/m.gr2", model())
        code, text = self.run_main(path, "-o", os.path.join(self.dir, "steamapps", "m.gr2"))
        self.assertEqual(code, 2)
        self.assertIn("Steam", text)

    def test_usage(self):
        code, text = self.run_main()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
