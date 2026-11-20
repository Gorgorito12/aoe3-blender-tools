# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/reencode_textures.py on synthetic textures (numpy): the format rule, the size limit, the
mip chain, blocks carried over exactly, bump maps renormalised, the check, the selection and the
report.

    venv\\Scripts\\python -I tests\\test_reencode_textures.py
"""
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np  # noqa: E402
from aoe3game import ddt  # noqa: E402
import reencode_textures as rt  # noqa: E402

LIMIT = (908, 790)


def picture(h, w, seed=1):
    """A smooth picture with some detail, alpha 255."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 4), np.float32)
    img[..., 0] = 128 + 100 * np.sin(x / 7)
    img[..., 1] = 128 + 90 * np.cos(y / 5)
    img[..., 2] = (x + y) * 255 / (h + w)
    img[..., :3] += rng.normal(0, 2, (h, w, 3))
    img[..., 3] = 255
    return np.clip(img, 0, 255).astype(np.uint8)


def normal_map(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    n = np.stack([np.sin(x / 3) * 0.6, np.cos(y / 4) * 0.6, np.ones_like(x)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    out = np.zeros((h, w, 4), np.uint8)
    out[..., 0] = 40
    out[..., 3] = np.clip(n[..., 0] * 127.5 + 127.5, 0, 255)
    out[..., 1] = np.clip(n[..., 1] * 127.5 + 127.5, 0, 255)
    out[..., 2] = np.clip(n[..., 2] * 127.5 + 127.5, 0, 255)
    return out


class Rules(unittest.TestCase):
    def head(self, usage, alpha, fmt):
        return ddt.Header(usage, alpha, fmt, 1, 8, 8, [])

    def test_format(self):
        opaque = np.full((8, 8, 4), 255, np.uint8)
        masked = opaque.copy()
        masked[0, 0, 3] = 0
        self.assertEqual(rt.choose_format(self.head(6, 0, ddt.DXT5), opaque)[0], ddt.DXT5)
        self.assertEqual(rt.choose_format(self.head(6, 4, ddt.DXT3), opaque)[0], ddt.DXT5)
        self.assertEqual(rt.choose_format(self.head(0, 0, ddt.DXT3), opaque)[0], ddt.DXT1)
        self.assertEqual(rt.choose_format(self.head(0, 0, ddt.DXT3), masked)[0], ddt.DXT3)
        for a in (1, 4, 8):
            self.assertEqual(rt.choose_format(self.head(0, a, ddt.BGRA), opaque)[0], ddt.DXT3)
        self.assertIsNone(rt.choose_format(self.head(0, 0, ddt.GREY), opaque)[0])
        self.assertIsNone(rt.choose_format(self.head(0, 2, ddt.DXT3), opaque)[0])

    def test_size(self):
        self.assertEqual(rt.target_size(1024, 1024, *LIMIT), (512, 512))
        self.assertEqual(rt.target_size(1024, 512, *LIMIT), (512, 256))
        self.assertEqual(rt.target_size(256, 1024, *LIMIT), (128, 512))
        self.assertEqual(rt.target_size(2048, 2048, *LIMIT), (512, 512))
        self.assertEqual(rt.target_size(512, 512, *LIMIT), (512, 512))

    def test_chain(self):
        self.assertEqual(ddt.chain_length(512, 512), 8)
        self.assertEqual(ddt.chain_length(512, 512, 8), 7)
        self.assertEqual(ddt.chain_length(512, 256), 7)
        self.assertEqual(ddt.chain_length(256, 256), 7)
        self.assertEqual(ddt.chain_length(1024, 1024), 9)
        self.assertEqual(ddt.chain_length(64, 8), 2)


class Encoder(unittest.TestCase):
    def test_refined_endpoints_are_closer(self):
        img = picture(64, 64)
        errs = []
        for refine in (False, True):
            back = ddt.decode(ddt.write_dxt(img, ddt.DXT1, alpha=0, mips=False, refine=refine))
            errs.append(np.abs(back[..., :3].astype(int) - img[..., :3]).mean())
        self.assertLess(errs[1], errs[0])
        # an image that came from DXT1 is found again almost exactly
        once = ddt.decode(ddt.write_dxt(img, ddt.DXT1, alpha=0, mips=False, refine=True))
        twice = ddt.decode(ddt.write_dxt(once, ddt.DXT1, alpha=0, mips=False, refine=True))
        self.assertLess(np.abs(twice.astype(int) - once).mean(), 0.2)

    def test_colour_blocks_become_dxt1_exactly(self):
        blocks = [struct.pack("<HHI", 0x001F, 0xF800, 0xE4E4E4E4),   # c0 < c1: swapped
                  struct.pack("<HHI", 0x07E0, 0x07E0, 0xFFFFFFFF),   # one colour, index 3
                  struct.pack("<HHI", 0xF800, 0x001F, 0x1B1B1B1B)]   # already in order
        for b in blocks:
            dxt3 = ddt.pack(0, 1, ddt.DXT3, 4, 4, [b"\xff" * 8 + b])
            dxt1 = ddt.pack(0, 0, ddt.DXT1, 4, 4,
                            [ddt.colour_blocks_as_dxt1(np.frombuffer(b, np.uint8)[None, :]).tobytes()])
            self.assertTrue((ddt.decode(dxt3)[..., :3] == ddt.decode(dxt1)[..., :3]).all())

    def test_fitted_non_square(self):
        img = picture(32, 64)
        self.assertEqual(ddt.fitted(img, 16).shape[:2], (8, 16))
        self.assertIs(ddt.fitted(img, 64), img)

    def test_bump_mips_stay_unit_length(self):
        nm = normal_map(32, 32)
        self.assertTrue(ddt.is_packed_normal_map(nm))
        self.assertFalse(ddt.is_packed_normal_map(picture(32, 32)))
        for bump, ok in ((False, False), (True, True)):
            lv = ddt.mip_chain(nm, bump=bump)[-1].astype(np.float32)
            n = (lv[..., [3, 1, 2]] - 127.5) / 127.5
            length = np.linalg.norm(n, axis=-1).mean()
            self.assertEqual(abs(length - 1) < 0.03, ok, length)

    def test_area_resize(self):
        img = picture(10, 6).astype(np.float32)
        small = ddt.area_resize(img, 5, 3)
        self.assertTrue(np.allclose(small, img.reshape(5, 2, 3, 2, 4).mean(axis=(1, 3)), atol=1e-3))
        self.assertAlmostEqual(float(ddt.area_resize(img, 3, 2).mean()), float(img.mean()), 2)


class Reencode(unittest.TestCase):
    def test_dxt3_without_alpha_becomes_dxt1_unchanged_in_its_pixels(self):
        data = ddt.write_dxt(picture(64, 64), ddt.DXT3, alpha=0, refine=True)
        data = data[:5] + b"\x00" + data[6:]                 # header alpha 0
        new, rec = rt.reencode(data, LIMIT)
        hd = ddt.read_header(new)
        self.assertEqual((hd.usage, hd.alpha, hd.format, hd.mips), (0, 0, ddt.DXT1, 5))
        self.assertEqual(rec["action"], "re-encoded")
        self.assertEqual(rec["levels_carried"], 5)
        for k in range(5):
            self.assertTrue((ddt.decode(new, k)[..., :3] == ddt.decode(data, k)[..., :3]).all())
        self.assertEqual(rec["mean"], 0.0)
        self.assertLess(rec["new_bytes"], rec["bytes"] * 0.6)

    def test_too_large_is_halved_with_a_full_chain(self):
        img = picture(128, 64)
        data = ddt.write_bgra(img, alpha=1, usage=1, mips=False)
        new, rec = rt.reencode(data, (64, 64))
        hd = ddt.read_header(new)
        self.assertEqual((hd.usage, hd.alpha, hd.format, hd.width, hd.height, hd.mips),
                         (1, 1, ddt.DXT3, 32, 64, ddt.chain_length(32, 64)))
        self.assertTrue(rec["resized"])
        self.assertEqual(rec["after"], f"1,1,8,{hd.mips}")
        self.assertEqual(rec["action"], "re-encoded")

    def test_bump_map(self):
        data = ddt.write_normal_map(normal_map(64, 64))       # one level
        new, rec = rt.reencode(data, LIMIT)
        hd = ddt.read_header(new)
        self.assertEqual((hd.usage, hd.alpha, hd.format, hd.mips), (6, 0, ddt.DXT5, 5))
        self.assertTrue(rec["normals_renormalised"])            # the new levels
        lv = ddt.decode(new, 3).astype(np.float32)
        n = (lv[..., [3, 1, 2]] - 127.5) / 127.5
        self.assertLess(abs(np.linalg.norm(n, axis=-1).mean() - 1), 0.06)

    def test_unchanged_and_kept(self):
        data = ddt.write_dxt(picture(32, 32), ddt.DXT1, alpha=0)
        new, rec = rt.reencode(data, LIMIT)
        self.assertIsNone(new)
        self.assertEqual(rec["action"], "unchanged")
        noisy = np.random.default_rng(2).integers(0, 256, (32, 32, 4), np.uint8)
        noisy[..., 3] = 255
        new, rec = rt.reencode(ddt.write_bgra(noisy, alpha=0), LIMIT, max_mean=1.0)
        self.assertIsNone(new)
        self.assertEqual(rec["action"], "kept")
        self.assertIn("the check failed", rec["reason"])
        grey = ddt.pack(0, 0, ddt.GREY, 4, 4, [b"\x80" * 16])
        self.assertEqual(rt.reencode(grey, LIMIT)[1]["action"], "kept")
        odd = ddt.write_bgra(picture(20, 12), alpha=1, mips=False)       # not powers of two
        new, rec = rt.reencode(odd, LIMIT)
        self.assertIsNone(new)
        self.assertIn("powers of two", rec["reason"])

    def test_run_report_and_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in", "a")
            os.makedirs(src)
            with open(os.path.join(src, "x.ddt"), "wb") as fh:
                fh.write(ddt.write_bgra(picture(16, 16), alpha=0, mips=False))
            with open(os.path.join(src, "y.ddt"), "wb") as fh:
                fh.write(ddt.write_dxt(picture(16, 16), ddt.DXT1, alpha=0))
            out = os.path.join(tmp, "out")
            recs = rt.run(rt.inputs(os.path.join(tmp, "in"), os.path.join(tmp, "in")), out, LIMIT,
                          sheets=os.path.join(out, "sheets"), log=lambda *_: None)
            self.assertEqual(sorted(r["action"] for r in recs), ["re-encoded", "unchanged"])
            self.assertTrue(os.path.exists(os.path.join(out, "a", "x.ddt")))
            self.assertFalse(os.path.exists(os.path.join(out, "a", "y.ddt")))
            with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
                rep = json.load(fh)
            self.assertEqual(rep["limit"], list(LIMIT))
            self.assertTrue(os.path.exists(os.path.join(out, "sheets", "index.html")))
            self.assertEqual(len([f for f in os.listdir(os.path.join(out, "sheets")) if f.endswith(".png")]), 1)


class Targets(unittest.TestCase):
    """--rules: exact (usage, alpha, format, mips) tuples per path, with a size cap."""

    def test_unit_colour_from_uncompressed(self):
        src = ddt.write_bgra(picture(256, 256), alpha=1, mips=False)            # (0,1,1,1)
        new, rec = rt.reencode(src, (1024, 1024), target=(0, 1, ddt.DXT3, 6))
        self.assertEqual(rec["action"], "re-encoded", rec.get("reason"))
        self.assertEqual(rt.digits(new), "0,1,8,6")
        self.assertEqual((ddt.read_header(new).width, len(ddt.read_header(new).levels)), (256, 6))

    def test_cap_and_mips_cut(self):
        src = ddt.write_bgra(picture(128, 128), alpha=1, mips=False)
        new, rec = rt.reencode(src, (64, 64), target=(0, 1, ddt.DXT3, 9))       # 64 px holds 7 levels
        self.assertEqual(rt.digits(new), "0,1,8,7")
        self.assertEqual(ddt.read_header(new).width, 64)
        self.assertIn("9 asked, 7", rec["mips_cut"])

    def test_icon_dxt1_and_its_exception(self):
        new, rec = rt.reencode(ddt.write_bgra(picture(64, 64), alpha=1, mips=False), (64, 64),
                               target=(0, 0, ddt.DXT1, 1))
        self.assertEqual(rt.digits(new), "0,0,4,1")
        clear = picture(64, 64)
        clear[:8, :8, 3] = 0                                                   # a transparent corner
        new, rec = rt.reencode(ddt.write_bgra(clear, alpha=4, mips=False), (64, 64), target=(0, 0, ddt.DXT1, 1))
        self.assertEqual(rt.digits(new), "0,4,8,1")
        self.assertTrue(rec["exception"])
        # an alpha 1 channel is the player-colour mask, not a cut-out: the icon drops it
        new, rec = rt.reencode(ddt.write_bgra(clear, alpha=1, mips=False), (64, 64), target=(0, 0, ddt.DXT1, 1))
        self.assertEqual(rt.digits(new), "0,0,4,1")
        self.assertNotIn("exception", rec)

    def test_bump_target_and_unchanged(self):
        nm = ddt.write_normal_map(normal_map(64, 64))                          # (6,0,9,1)
        new, rec = rt.reencode(nm, (1024, 1024), target=(6, 0, ddt.DXT5, 1))
        self.assertIsNone(new)
        self.assertEqual(rec["action"], "unchanged")
        new, rec = rt.reencode(nm, (1024, 1024), target=(6, 0, ddt.DXT5, 7))
        self.assertEqual(rt.digits(new), "6,0,9,7")
        self.assertTrue(rec["normals_renormalised"])

    def test_rules_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = os.path.join(tmp, "r.json")
            with open(rules, "w", encoding="utf-8") as fh:
                json.dump({"rules": [{"name": "icon", "match": r"_icon\.ddt$", "tuple": [0, 0, 4, 1], "max": 64},
                                     {"name": "colour", "match": r"^units\\", "tuple": [0, 1, 8, 6], "max": 512}]}, fh)
            src = os.path.join(tmp, "in", "units", "a")
            os.makedirs(src)
            for name in ("a_icon.ddt", "a.ddt"):
                with open(os.path.join(src, name), "wb") as fh:
                    fh.write(ddt.write_bgra(picture(128, 128), alpha=1, mips=False))
            os.makedirs(os.path.join(tmp, "in", "other"))
            with open(os.path.join(tmp, "in", "other", "b.ddt"), "wb") as fh:
                fh.write(ddt.write_bgra(picture(16, 16), alpha=1, mips=False))
            out = os.path.join(tmp, "out")
            recs = {r["path"].replace("/", "\\"): r for r in
                    rt.run(rt.inputs(os.path.join(tmp, "in"), os.path.join(tmp, "in")), out, (0, 0),
                           log=lambda *_: None, rules=rt.load_rules(rules))}
            self.assertEqual(recs[r"units\a\a_icon.ddt"]["after"], "0,0,4,1")
            self.assertEqual(recs[r"units\a\a_icon.ddt"]["new_width"], 64)
            self.assertEqual(recs[r"units\a\a.ddt"]["after"], "0,1,8,6")
            self.assertEqual(recs[r"other\b.ddt"]["reason"], "no rule matches its path")

    def test_odd_size_with_a_target_becomes_a_power_of_two(self):
        new, rec = rt.reencode(ddt.write_bgra(picture(158, 158), alpha=1, mips=False), (128, 128),
                               target=(0, 1, ddt.DXT3, 6))
        self.assertEqual(rt.digits(new), "0,1,8,6")
        self.assertEqual(ddt.read_header(new).width, 128)
        self.assertEqual(rec["pow2"], "158x158 -> 128x128")

    def test_keep_alpha_test_and_transparency(self):
        hd = ddt.read_header(ddt.write_bgra(picture(16, 16), alpha=8, usage=1, mips=False))
        t, kept = rt.kept_bits((0, 1, ddt.DXT3, 7), {"alpha_test", "transparency"}, hd)
        self.assertEqual(t, (1, 8, ddt.DXT3, 7))
        self.assertEqual(kept, ["alpha test", "alpha 8"])
        self.assertEqual(rt.kept_bits((0, 1, ddt.DXT3, 7), set(), hd)[0], (0, 1, ddt.DXT3, 7))


class Select(unittest.TestCase):
    def test_only_building_only_textures(self):
        class Art:
            def status(self, k):
                return "stock" if k.startswith("stock") else "mod"
        res = {"art": Art(), "homecities": [{"anims": {"hc\\b.xml": {"variants": [("hc\\b.xml", "loose")]}}}],
               "texture_uses": {
                   "a.ddt": {"uses": {"building"}, "users": set()},
                   "b.ddt": {"uses": {"building", "other"}, "users": set()},
                   "c.ddt": {"uses": {"other"}, "users": set()},
                   "d.ddt": {"uses": {"person"}, "users": set()},
                   "e.ddt": {"uses": {"building"}, "users": set()},
                   "stock.ddt": {"uses": {"building"}, "users": set()},
                   "f.ddt": {"uses": {"building", "outside"}, "users": set()}}}
        chosen, others = rt.select(res, {"e.ddt": ["units\\x.xml"], "a.ddt": ["hc\\b.xml"]})
        self.assertEqual(chosen, ["a.ddt"])
        why = dict(others)
        self.assertEqual(sorted(why), ["b.ddt", "d.ddt", "e.ddt", "f.ddt", "stock.ddt"])
        self.assertIn("scene", why["b.ddt"])
        self.assertIn("person", why["d.ddt"])
        self.assertIn("units\\x.xml", why["e.ddt"])
        self.assertIn("outside", why["f.ddt"])
        # an anim file a proto names (a building of the game) that names the texture
        res["homecities"][0]["anims"]["hc\\b.xml"]["refs"] = [
            {"kind": "texture:to", "value": "a", "variant": "hc\\b.xml"}]
        res["files"] = []
        chosen, others = rt.select(res, {}, {"hc\\b.xml": "SomeMill"})
        self.assertNotIn("a.ddt", chosen)
        self.assertIn("SomeMill", dict(others)["a.ddt"])

    def test_proto_anim_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(tmp, "data", "protoy.xml"), "w", encoding="utf-8") as fh:
                fh.write('<proto><Unit id="1" name="Mill"><AnimFile>Buildings\\Mill\\mill.xml</AnimFile>'
                         '</Unit></proto>')
            self.assertEqual(rt.proto_anim_files(tmp), {"buildings\\mill\\mill.xml": "Mill"})


if __name__ == "__main__":
    unittest.main()
