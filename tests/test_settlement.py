# SPDX-License-Identifier: GPL-3.0-or-later
"""The settlement composer (core/settlement.py) against what the mod's own groupings measure, and
the grouping it writes read back (aoe3game/grouping.py):

    python -I tests/test_settlement.py
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import grouping  # noqa: E402
from core import settlement  # noqa: E402

CATALOG = {"socket": [("NativeSocket", 1, 3.0)],
           "building": [("NativeHouse", 4, 2.2), ("NativeLonghouse", 2, 3.0)],
           "prop": [("SetGoods", 10, 0.5), ("SetCamp", 7, 0.9)],
           "plant": [("Underbrush", 8, 0.6)], "nature": [("Tree", 6, 0.8)],
           "obstruction": [("TownObstruction", 1, 1.0)]}


class Compose(unittest.TestCase):
    def setUp(self):
        self.group = settlement.measured()
        self.out = settlement.compose(CATALOG, seed=3)

    def test_the_socket_is_alone_at_the_centre(self):
        socket = self.out[0]
        self.assertEqual((socket["class"], socket["x"], socket["z"]), ("socket", 0.0, 0.0))
        self.assertEqual(sum(p["class"] == "socket" for p in self.out), 1)
        clear = self.group["clear"][1]
        for p in self.out[1:]:
            if p["class"] != "obstruction":
                self.assertGreaterEqual(math.hypot(p["x"], p["z"]), clear, p)

    def test_nothing_overlaps(self):
        placed = [p for p in self.out[1:] if p["class"] != "obstruction"]
        for i, a in enumerate(placed):
            for b in placed[i + 1:]:
                self.assertGreaterEqual(math.hypot(a["x"] - b["x"], a["z"] - b["z"]), a["r"] + b["r"], (a, b))

    def test_a_lane_to_the_socket_is_left_free(self):
        lane = self.out[0]["turn"]
        for p in self.out[1:]:
            along = p["x"] * math.sin(lane) + p["z"] * math.cos(lane)
            across = p["x"] * math.cos(lane) - p["z"] * math.sin(lane)
            if p["class"] != "obstruction":
                self.assertFalse(along > 0 and abs(across) < settlement.LANE / 2, p)

    def test_the_counts_and_distances_follow_the_measured_settlements(self):
        per = self.group["per_file"]
        n = {c: sum(p["class"] == c for p in self.out) for c in ("building", "prop")}
        self.assertGreaterEqual(n["building"], per["building"][0])
        self.assertLessEqual(n["building"], per["building"][2])
        bd = self.group["building_d"]
        for p in self.out:
            if p["class"] == "building":
                self.assertTrue(bd[0] - 1e-6 <= math.hypot(p["x"], p["z"]) <= bd[2] + 1e-6)

    def test_not_every_building_faces_the_socket(self):
        turns = []
        for seed in range(1, 9):
            for p in settlement.compose(CATALOG, seed=seed):
                if p["class"] == "building":
                    to_socket = math.atan2(-p["x"], -p["z"])
                    turns.append(abs((p["turn"] - to_socket + math.pi) % (2 * math.pi) - math.pi))
        facing = sum(t < math.pi / 4 for t in turns) / len(turns)
        self.assertTrue(0.2 < facing < 0.7, facing)        # the mod's own: 37 %

    def test_the_seed_gives_the_numbered_variants(self):
        self.assertEqual(settlement.compose(CATALOG, seed=3), self.out)
        self.assertNotEqual(settlement.compose(CATALOG, seed=4), self.out)

    def test_a_variation_stays_below_its_sets_count(self):
        counts = {proto: n for entries in CATALOG.values() for proto, n, _ in entries}
        for p in self.out:
            self.assertLess(p["variation"], max(1, counts[p["proto"]]))

    def test_it_writes_a_grouping_that_reads_back_the_same(self):
        g = settlement.to_grouping(self.out)
        back = grouping.read(grouping.write(g))
        self.assertEqual(len(back["units"]), len(self.out))
        for u, p in zip(back["units"], self.out):
            self.assertEqual((u["proto"], u["variation"]), (p["proto"], p["variation"]))
            self.assertAlmostEqual(u["x"], p["x"], places=3)
            self.assertAlmostEqual(grouping.angle(u["orient"]) % (2 * math.pi), p["turn"] % (2 * math.pi), places=2)
        self.assertGreater(back["width"], 2 * max(abs(p["x"]) for p in self.out))


class Format(unittest.TestCase):
    SAMPLE = """<?xml version="1.0"?>
<grouping>
\t<width>20</width>
\t<height>15</height>
\t<ignorePlacementRules>0</ignorePlacementRules>
\t<selectAsSingleUnit>1</selectAsSingleUnit>
\t<units>
\t\t<unit Variation ="8" posX ="0.0544" posZ ="6.6628" orientX ="-1.0000" orientY ="0.0000" orientZ ="0.0000">PropsNative</unit>
\t\t<unit variation ="2" posx ="-1.5" posz ="2" orientx ="0" orienty ="0" orientz ="1">Campfire</unit>
\t</units>
\t<tiles>
\t\t<tileGroup type ="NonPassableLand" subtype ="terrain\\texas\\river1_tex">
\t\t\t<block startX ="-6" startZ ="0" endX ="-6" endZ ="0"></block>
\t\t</tileGroup>
\t</tiles>
</grouping>
"""

    def test_both_spellings_are_read(self):
        g = grouping.read(self.SAMPLE)
        self.assertEqual([u["proto"] for u in g["units"]], ["PropsNative", "Campfire"])
        self.assertEqual(g["units"][0]["variation"], 8)
        self.assertAlmostEqual(g["units"][0]["z"], 6.6628)
        self.assertEqual(g["flags"], {"ignoreplacementrules": 0, "selectassingleunit": 1})
        self.assertEqual((g["width"], g["height"]), (20.0, 15.0))

    def test_a_file_read_and_written_again_keeps_its_units_flags_and_tiles(self):
        g = grouping.read(self.SAMPLE)
        text = grouping.write(g)
        self.assertEqual(grouping.read(text), g)
        self.assertIn("<block", text)
        self.assertIn("posx =", text)                       # written in the usual lower case

    def test_a_file_without_tiles_or_flags_stays_without(self):
        g = grouping.read("<grouping><width>4</width><height>4</height><units/></grouping>")
        text = grouping.write(g)
        self.assertNotIn("tiles", text)
        self.assertNotIn("ignoreplacementrules", text)

    def test_blender_and_the_game_round_trip(self):
        x, y, t = grouping.to_blender(*grouping.from_blender(3.0, -2.0, 1.2))
        self.assertAlmostEqual(x, 3.0)
        self.assertAlmostEqual(y, -2.0)
        self.assertAlmostEqual(t, 1.2, places=3)

    def test_the_axes_grouping_is_asymmetric(self):
        g = grouping.axes_grouping("PropsColony", 4)
        xs = {round(u["x"], 3) for u in g["units"]}
        self.assertGreater(len(xs), 3)
        self.assertEqual(len({u["orient"] for u in g["units"][:4]}), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
