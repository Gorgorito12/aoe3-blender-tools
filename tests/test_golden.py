# SPDX-License-Identifier: GPL-3.0-or-later
"""Golden tests: the neoclassical presets must come out byte for byte as recorded in
tests/golden/neoclassical.json (faces, atlas, texture, attach points, sizes, facade layout).
Plain Python with numpy, no Blender:

    venv\\Scripts\\python -I tests\\test_golden.py                    check
    venv\\Scripts\\python -I tests\\test_golden.py --update-golden    record the current output

Update the record only on purpose (a deliberate change to the neoclassical style), and say so
in the commit. On a difference the test names the first face block or atlas region that moved.
"""
import dataclasses
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from core import building, paint, pngio  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "golden", "neoclassical.json")
UPDATE = "--update-golden" in sys.argv
BLOCK = 8                      # faces per hash in the face list

# Triangles per preset as the generator makes them (the README's numbers).
TRIANGLES = {"MANSION": 92, "WHITE_HOUSE": 355, "COURTHOUSE": 373, "CAPITOL": 413,
             "WHITE_HOUSE_MEDIUM": 1235, "WHITE_HOUSE_1914": 3035}


def cases():
    """Preset key -> params: the presets plus the White House at medium detail."""
    out = dict(building.PRESETS)
    out["WHITE_HOUSE_MEDIUM"] = dataclasses.replace(building.PRESETS["WHITE_HOUSE"],
                                                    detail="MEDIUM", name="WhiteHouseMedium")
    return out


def _f(v):
    return "%.6f" % (round(v, 6) + 0.0)        # + 0.0: no "-0.000000"


def _face(f):
    pts = ";".join(",".join(_f(c) for c in p) for p in f.pts)
    uvs = ";".join(",".join(_f(c) for c in uv) for uv in f.uvs)
    return f"{f.region}|{int(bool(f.smooth))}|{pts}|{uvs}"


def _h(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()[:16]


def fingerprint(model):
    faces = [_face(f) for f in model.faces]
    blocks = [_h("\n".join(faces[i:i + BLOCK])) for i in range(0, len(faces), BLOCK)]
    regions = [f"{r.name},{r.x},{r.y},{r.w},{r.h},{_f(r.world_w)},{_f(r.world_h)}"
               for r in model.atlas.regions.values()]
    attach = {k: [_f(c) for c in v] for k, v in sorted(model.attach.items())}
    return {"faces": len(faces), "face_blocks": blocks,
            "density": _f(model.atlas.density), "regions": regions,
            "texture": _h(paint.paint(model).tobytes()),
            "attach": attach, "dims": _h(repr(model.dims)), "facades": _h(repr(model.facades))}


def triangles(model):
    return sum(len(f.pts) - 2 for f in model.faces)


class Golden(unittest.TestCase):
    record = {}

    @classmethod
    def setUpClass(cls):
        cls.models = {k: building.build(p) for k, p in cases().items()}
        cls.current = {k: fingerprint(m) for k, m in cls.models.items()}
        if UPDATE:
            os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
            with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
                json.dump(cls.current, f, indent=1, sort_keys=True)
                f.write("\n")
            print(f"recorded {GOLDEN}")
        with open(GOLDEN, encoding="utf-8") as f:
            cls.record = json.load(f)

    def test_presets_match_the_record(self):
        self.assertEqual(sorted(self.record), sorted(self.current), "preset list changed")
        for key, want in self.record.items():
            got = self.current[key]
            with self.subTest(preset=key):
                self.assertEqual(got["faces"], want["faces"], f"{key}: face count")
                for i, (a, b) in enumerate(zip(got["face_blocks"], want["face_blocks"])):
                    self.assertEqual(a, b, f"{key}: faces {i * BLOCK}..{i * BLOCK + BLOCK - 1} differ")
                self.assertEqual(got["density"], want["density"], f"{key}: atlas density")
                for a, b in zip(got["regions"], want["regions"]):
                    self.assertEqual(a, b, f"{key}: atlas region")
                self.assertEqual(len(got["regions"]), len(want["regions"]), f"{key}: region count")
                for part in ("attach", "dims", "facades", "texture"):
                    self.assertEqual(got[part], want[part], f"{key}: {part}")

    def test_triangle_baselines(self):
        for key, n in TRIANGLES.items():
            with self.subTest(preset=key):
                self.assertEqual(triangles(self.models[key]), n)

    def test_whitehouse_texture_matches_the_example(self):
        """The shipped example texture is what the generator paints today."""
        path = os.path.join(ROOT, "examples", "whitehouse", "whitehouse_diffuse.png")
        with open(path, "rb") as f:
            png = pngio.read_png(f.read())
        rgb = paint.paint(self.models["WHITE_HOUSE"])
        self.assertEqual(png.shape[:2], rgb.shape[:2])
        self.assertTrue((png[:, :, :3] == rgb).all(),
                        f"{int((png[:, :, :3] != rgb).any(axis=2).sum())} pixels differ")


if __name__ == "__main__":
    unittest.main(argv=[a for a in sys.argv if a != "--update-golden"], verbosity=2)
