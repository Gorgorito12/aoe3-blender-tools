# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the animation tag files (aoe3game/precomp.py) and tools/fix_hitpointbar_tags.py, on
synthetic files only. Plain Python:

    python -I tests/test_hitpointbar_tags.py
"""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from aoe3game import precomp  # noqa: E402
import fix_hitpointbar_tags  # noqa: E402

ROT = struct.pack("<4f", 0.5, 0.5, -0.5, 0.5)


def tag_file(tags, keys=4, duration=1.0, blocks=1, model="units\\foo\\foo"):
    """The bytes of a tag file: tags is [(name, (x, y, z))], each a constant track."""
    doc = precomp.Precomp()
    doc.version, doc.head, doc.names_head = 4, b"\0" * 4, struct.pack("<I", 1)
    doc.middle, doc.blocks, doc.ms_version = b"\0" * 8, blocks, 3
    doc.names = [n for n, _p in tags]
    doc.rotations = [[ROT] * keys for _ in tags]
    doc.positions = [[p] * keys for _n, p in tags]
    doc.mapping = [(i, [i]) for i in range(len(tags))]
    doc.extra = struct.pack("<I", 0) + b"EP" + struct.pack("<II", 4, 0)
    doc.duration = duration
    raw = model.encode("utf-16-le")
    doc.tail = struct.pack("<I", len(raw) // 2) + raw
    if blocks > 1:
        doc.tail += b"MS" + struct.pack("<I", 0)
    return doc.encode()


BODY = [("MASTER", (0.0, 1.0, 0.0)), ("HEAD", (0.0, 2.6, 0.2))]
ANIM = """<?xml version="1.0" encoding="utf-8"?>
<animfile>
  <attachment>Rider
    <anim>Idle<assetreference type="GrannyAnim"><file>anims\\rider_idle</file></assetreference></anim>
  </attachment>
  <component>Body<assetreference type="GrannyModel"><file>units\\foo\\foo</file></assetreference></component>
  <anim>Idle
    <assetreference type="GrannyAnim"><file>anims\\idle_a</file><weight>40</weight></assetreference>
    <assetreference type="GrannyAnim"><file>anims\\idle_b</file><weight>10</weight></assetreference>
    <component>Body</component>
  </anim>
  <anim>Walk
    <assetreference type="GrannyAnim"><file>anims\\walk</file></assetreference>
    <component>Body</component>
  </anim>
  <anim>Run
    <assetreference type="GrannyAnim"><file>anims\\run</file></assetreference>
    <component>Body</component>
  </anim>
  <anim>Death
    <assetreference type="GrannyAnim"><file>anims\\death</file></assetreference>
    <component>Body</component>
  </anim>
</animfile>
"""


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def run_tool(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fix_hitpointbar_tags.main(list(args))
    return out.getvalue()


class PrecompTest(unittest.TestCase):
    def test_round_trip_and_lookup(self):
        data = tag_file(BODY + [("HITPOINTBAR", (0.0, 3.0, 0.0))])
        doc = precomp.load(data)
        self.assertEqual(doc.encode(), data)
        self.assertEqual(doc.names, ["MASTER", "HEAD", "HITPOINTBAR"])
        self.assertTrue(doc.has("hitpointbar"))
        self.assertEqual(doc.tracks_of("HITPOINTBAR")[0][0], (0.0, 3.0, 0.0))
        self.assertEqual(doc.key_count(), 4)
        self.assertAlmostEqual(doc.duration, 1.0)
        self.assertEqual(doc.model, "units\\foo\\foo")

    def test_add_constant_changes_only_what_it_adds(self):
        data = tag_file(BODY, keys=6)
        doc = precomp.load(data)
        doc.add_constant("HITPOINTBAR", (0.0, 2.5, -0.25), ROT)
        out = precomp.load(doc.encode())
        self.assertEqual(out.tracks_of("HITPOINTBAR"), [[(0.0, 2.5, -0.25)] * 6])
        old = precomp.load(data)
        self.assertEqual(out.names[:2], old.names)
        self.assertEqual(out.positions[:2], old.positions)
        self.assertEqual(out.rotations[:2], old.rotations)
        self.assertEqual(out.mapping[:2], old.mapping)
        self.assertEqual((out.tail, out.extra, out.duration), (old.tail, old.extra, old.duration))
        self.assertEqual(out.mapping[2], (2, [2]))
        self.assertEqual(out.rotations[2], [ROT] * 6)

    def test_refusals(self):
        with self.assertRaises(precomp.PrecompError):
            precomp.load(b"SX" + struct.pack("<I", 2) + b"SV")
        with self.assertRaises(precomp.PrecompError):
            precomp.load(tag_file(BODY) + b"\0")
        doc = precomp.load(tag_file([("HITPOINTBAR", (0.0, 3.0, 0.0))]))
        with self.assertRaises(precomp.PrecompError):
            doc.add_constant("HITPOINTBAR", (0.0, 3.0, 0.0), ROT)
        with self.assertRaises(precomp.PrecompError):
            precomp.load(tag_file([])).add_constant("HITPOINTBAR", (0.0, 3.0, 0.0), ROT)
        with self.assertRaises(precomp.PrecompError):
            precomp.load(tag_file(BODY, blocks=2)).add_constant("HITPOINTBAR", (0.0, 3.0, 0.0), ROT)


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.art = os.path.join(self.tmp.name, "art")
        write(os.path.join(self.art, "units", "foo", "foo.xml"), ANIM.encode())
        tagged = lambda y: tag_file(BODY + [("HITPOINTBAR", (0.0, y, 0.0))])  # noqa: E731
        files = {"idle_a": tag_file(BODY), "idle_b": tagged(3.0), "walk": tagged(3.2),
                 "run": tag_file(BODY, keys=7), "death": tag_file(BODY),
                 "rider_idle": tag_file(BODY)}
        self.original = {}
        for name, data in files.items():
            write(os.path.join(self.art, "anims", name + ".gr2.precomp"), data)
            self.original[name] = data

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, root, name):
        return os.path.join(root, "anims", name + ".gr2.precomp")

    def test_dry_run_writes_nothing(self):
        before = sorted(os.listdir(os.path.join(self.art, "anims")))
        report = run_tool(os.path.join(self.art, "units"), "--dry-run")
        self.assertIn("some animations lack it (the bar jumps): 1", report)
        self.assertIn("would write", report)
        self.assertEqual(sorted(os.listdir(os.path.join(self.art, "anims"))), before)
        for name, data in self.original.items():
            with open(self.path(self.art, name), "rb") as f:
                self.assertEqual(f.read(), data)

    def test_fix_into_out_folder(self):
        out = os.path.join(self.tmp.name, "out")
        report = run_tool(os.path.join(self.art, "units", "foo", "foo.xml"), "--art", self.art,
                          "--out", out)
        written = sorted(os.listdir(os.path.join(out, "anims")))
        # the idle without the tag and the run; not the death, nor the rider's (an attachment)
        self.assertEqual(written, ["idle_a.gr2.precomp", "run.gr2.precomp"], report)
        for name in ("idle_a", "run"):
            with open(self.path(out, name), "rb") as f:
                doc = precomp.load(f.read())
            old = precomp.load(self.original[name])
            track = doc.tracks_of("HITPOINTBAR")[0]
            self.assertEqual(len(track), old.key_count())
            self.assertEqual(track[0], (0.0, 3.0, 0.0))      # the tagged idle's height
            self.assertEqual(doc.positions[:-1], old.positions)
            self.assertEqual(doc.names[:-1], old.names)
        for name, data in self.original.items():               # the art folder is untouched
            with open(self.path(self.art, name), "rb") as f:
                self.assertEqual(f.read(), data)

    def test_fix_in_place_keeps_the_original(self):
        run_tool(os.path.join(self.art, "units"))
        with open(self.path(self.art, "idle_a") + ".orig", "rb") as f:
            self.assertEqual(f.read(), self.original["idle_a"])
        with open(self.path(self.art, "idle_a"), "rb") as f:
            self.assertTrue(precomp.load(f.read()).has("HITPOINTBAR"))
        # a second run finds nothing left to fix
        report = run_tool(os.path.join(self.art, "units"), "--dry-run")
        self.assertIn("tag files to fix: 0", report)

    def test_shared_animation_takes_the_majority_height(self):
        for k, y in enumerate((5.0, 5.0)):
            other = ANIM.replace("anims\\idle_b", f"anims\\tall{k}")
            write(os.path.join(self.art, "units", f"tall{k}", f"tall{k}.xml"), other.encode())
            write(self.path(self.art, f"tall{k}"), tag_file(BODY + [("HITPOINTBAR", (0.0, y, 0.0))]))
        report = run_tool(os.path.join(self.art, "units"), "--dry-run")
        line = next(l for l in report.splitlines() if "idle_a.gr2.precomp" in l)
        self.assertIn("(0.000, 5.000, 0.000)", line)
        self.assertIn("wanted another height", line)

    def test_missing_tag_file_is_reported(self):
        os.remove(self.path(self.art, "idle_a"))
        write(os.path.join(self.art, "anims", "idle_a.gr2"), b"model")
        report = run_tool(os.path.join(self.art, "units"), "--dry-run")
        self.assertIn("anims\\idle_a: no tag file (the .gr2 is loose)", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
