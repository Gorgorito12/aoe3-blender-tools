# SPDX-License-Identifier: GPL-3.0-or-later
"""aoe3game/gr2_edit.py (a model's whole tree copied and written again) and tools/gr2_check.py
(the game's runtime as the judge), on models written here; the runtime is a fake that reads a
file with this repository's reader. Plain Python.

    python -I tests/test_gr2_edit.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from aoe3game import gr2, gr2_edit, gr2_write  # noqa: E402
from aoe3game.gr2_types import Spec  # noqa: E402
import gr2_check  # noqa: E402

P = [(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)]


def model():
    return gr2_write.static_model("box", P, [(0, -1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)],
                                  [(0, 1, 2), (0, 2, 3)], texture=r"C:\x\art\mod\box.ddt",
                                  bump=r"C:\x\art\mod\box_b.ddt", bones=[("bone_flag_civ", (1, 0, 3))])


class Rewrite(unittest.TestCase):
    def test_a_model_written_again_from_its_own_tree_reads_the_same(self):
        data = model()
        out = gr2_edit.rewrite(data)
        self.assertTrue(gr2.crc_ok(out))
        self.assertEqual(gr2.dump_tree(gr2.load(out)), gr2.dump_tree(gr2.load(data)))
        self.assertEqual(gr2_edit.rewrite(out), out)                     # a fixed point

    def test_an_object_reached_twice_stays_one(self):
        root = gr2_edit.copy_tree(gr2.load(model()))
        tex = gr2_edit.find(root, ("Textures", 0))
        mats = gr2_edit.find(root, ("Materials",))
        reached = [m.values.get("Texture") for m in mats] + [mp.values.get("Map").values.get("Texture")
                                                             for m in mats for mp in (m.values.get("Maps") or [])]
        self.assertIn(tex, [r for r in reached if r is not None])
        # an edit by name reaches the file
        gr2_edit.find(root, ("Meshes", 0)).values["Name"] = "renamed"
        back = gr2.load(gr2_write.serialize(root)).root()
        self.assertEqual(back.get("Meshes")[0].get("Name"), "renamed")

    def test_a_type_that_names_two_members_alike_keeps_both(self):
        spec = Spec("Twice", [(gr2.STRING, "Effect", None, 0), (gr2.INT32, "Effect", None, 0)])
        root_spec = Spec("Root", [(gr2.VARIANT_REF, "ExtendedData", None, 0)])
        w = gr2_write.W(spec)
        w.values[0], w.values[1] = "bumpspec_mask_pixelxform", 7
        data = gr2_write.serialize(gr2_write.W(root_spec, ExtendedData=w))
        doc = gr2.load(data)
        ext = doc.root().get("ExtendedData")
        self.assertEqual([doc.value(ext.type, ext.at, m) for m in ext.type.members], ["bumpspec_mask_pixelxform", 7])
        out = gr2_edit.rewrite(data)
        self.assertEqual(gr2.dump_tree(gr2.load(out)), gr2.dump_tree(doc))


class Textures(unittest.TestCase):
    def test_texture_key_is_the_path_below_art(self):
        self.assertEqual(gr2_edit.texture_key(r"E:\AGE3\Source\Age3w\Art\buildings\x\Jesuit_Asian.ddt"),
                         r"buildings\x\jesuit_asian")
        self.assertEqual(gr2_edit.texture_key(r"D:\age3w\art\units\a\b.tga"), r"units\a\b")
        self.assertEqual(gr2_edit.texture_key("art/units/a/b.(0,4,8,8).tga"), r"units\a\b.(0,4,8,8)")
        self.assertEqual(gr2_edit.stored_name(r"buildings\mod\post\post"), r"C:\art\buildings\mod\post\post.ddt")

    def test_renamed_textures_are_written_and_the_rest_kept(self):
        root = gr2_edit.copy_tree(gr2.load(model()))
        new = gr2_edit.stored_name(r"buildings\mod\a_much_longer_folder_name\box_colour")
        done = gr2_edit.rename_textures(root, {r"mod\box": new})
        self.assertEqual(done, [(r"C:\x\art\mod\box.ddt", new)])
        out = gr2_write.serialize(root)
        names = [t.get("FromFileName") for t in gr2.load(out).root().get("Textures")]
        self.assertIn(new, names)                                          # any length
        self.assertIn(r"C:\x\art\mod\box_b.ddt", names)                    # not listed: kept
        self.assertEqual(gr2_edit.rename_textures(root, {r"mod\other": "x"}), [])


class FakeRuntime:
    """Stands in for recompress_models.Runtime: reads a file as the helper's `info` prints it,
    with this repository's reader; `drop` leaves the last bone out, `refuse` refuses."""

    def __init__(self, drop=False, refuse=False):
        self.drop, self.refuse = drop, refuse

    def info(self, data, tag):
        if self.refuse:
            return 1, ["version\t2.5.0.10", "refused\tthe runtime could not read the file"]
        lines = gr2_check.reader_lines(gr2.load(data))
        lines = [ln + "\t1" if ln.startswith("mesh\t") else ln for ln in lines]
        if self.drop:
            lines = lines[:-1]
        return 0, ["version\t2.5.0.10"] + lines

    def crc_ok(self, data, tag):
        return gr2.crc_ok(data)


class Check(unittest.TestCase):
    def test_the_runtime_and_the_reader_agree_and_the_rewrite_too(self):
        ok, notes = gr2_check.check(model(), FakeRuntime(), 0, rewrite=True)
        self.assertTrue(ok, notes)
        self.assertIn("rewritten from its own tree", notes[-1])
        self.assertIn("1 meshes", notes[0])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            kept = os.path.join(tmp, "art", "units", "box.gr2")
            ok, notes = gr2_check.check(model(), FakeRuntime(), 0, rewrite=True, save=kept)
            with open(kept, "rb") as fh:
                self.assertEqual(fh.read(), gr2_edit.rewrite(model()))
            kept2 = os.path.join(tmp, "not.gr2")
            gr2_check.check(model(), FakeRuntime(drop=True), 0, rewrite=True, save=kept2)
            self.assertFalse(os.path.exists(kept2))                       # kept only when read alike

    def test_a_difference_or_a_refusal_is_reported(self):
        ok, notes = gr2_check.check(model(), FakeRuntime(drop=True), 0)
        self.assertFalse(ok)
        self.assertIn("differs", notes[-1])
        ok, notes = gr2_check.check(model(), FakeRuntime(refuse=True), 0)
        self.assertFalse(ok)
        self.assertIn("refused", notes[0])

    def test_without_the_runtime_it_says_how_to_get_it(self):
        import io
        import contextlib
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = gr2_check.main([os.path.join(tmp, "x.gr2"), "--granny-install", tmp])
            self.assertEqual(code, 2)
            self.assertIn("granny2.dll", buf.getvalue())
            open(os.path.join(tmp, "granny2.dll"), "wb").close()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = gr2_check.main([os.path.join(tmp, "x.gr2"), "--granny-install", tmp, "--helper", os.path.join(tmp, "none.exe")])
            self.assertEqual(code, 2)
            self.assertIn("--build-helper", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
