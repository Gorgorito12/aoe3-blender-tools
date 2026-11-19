# SPDX-License-Identifier: GPL-3.0-or-later
"""aoe3game/unitpanel.py: the unit panels filled for one unit, the DLL's rows, and what exists but
the unit does not show, with every reason. A synthetic unit, building, tactics, keys and rows file.
Plain Python.

    python -I tests/test_unitpanel.py
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "aoe3_blender_tools"))
from aoe3game import unitpanel as up  # noqa: E402

UNIT = """<Unit id="5" name="Gunman">
  <DisplayNameID>900</DisplayNameID>
  <MaxVelocity>4.0000</MaxVelocity>
  <InitialHitpoints>150.0000</InitialHitpoints>
  <MaxHitpoints>150.0000</MaxHitpoints>
  <LOS>16.0000</LOS>
  <TrainPoints>30.0000</TrainPoints>
  <Bounty>10.0000</Bounty>
  <PopulationCount>1</PopulationCount>
  <Cost resourcetype="Food">75.0000</Cost>
  <Armor type="Hand" value="0.2000" />
  <UnitType>Unit</UnitType>
  <UnitType>AbstractInfantry</UnitType>
  <Tactics>gun.tactics</Tactics>
  <PortraitIcon>units\\gunman_portrait</PortraitIcon>
  <ProtoAction><Name>VolleyRangedAttack</Name><Damage>23</Damage><DamageType>Ranged</DamageType><MaxRange>12</MaxRange><ROF>3</ROF></ProtoAction>
  <ProtoAction><Name>VolleyHandAttack</Name><Damage>13</Damage><DamageType>Hand</DamageType><ROF>1.5</ROF>
    <DamageBonus type="AbstractLightInfantry">3.0</DamageBonus><DamageBonus type="AbstractCavalry">2.0</DamageBonus></ProtoAction>
  <ProtoAction><Name>BuildingAttack</Name><Damage>20</Damage><DamageType>Siege</DamageType><ROF>3</ROF></ProtoAction>
  <ProtoAction><Name>SpecialAttack</Name><Damage>50</Damage><DamageType>Ranged</DamageType><MaxRange>20</MaxRange></ProtoAction>
  <ProtoAction><Name>ExtraAttack</Name><Damage>5</Damage><DamageType>Hand</DamageType></ProtoAction>
</Unit>"""
BUILDING = """<Unit id="6" name="Hall">
  <DisplayNameID>901</DisplayNameID>
  <MaxHitpoints>2500</MaxHitpoints><InitialHitpoints>2500</InitialHitpoints>
  <LOS>12</LOS><BuildPoints>60</BuildPoints><MaxContained>10</MaxContained>
  <Armor type="Siege" value="0.3" />
  <UnitType>Building</UnitType>
</Unit>"""
TACTICS = """<?xml version="1.0"?>
<tactics>
  <action><name stringid="801">VolleyRangedAttack</name><type>Attack</type><attackaction>1</attackaction><maxrange>12</maxrange></action>
  <action><name stringid="802">VolleyHandAttack</name><type>Attack</type><attackaction>1</attackaction><maxrange>1.75</maxrange></action>
  <action><name stringid="803">BuildingAttack</name><type>Attack</type><attackaction>1</attackaction><maxrange>6</maxrange></action>
  <action><name stringid="804">SpecialAttack</name><type>Attack</type><attackaction>1</attackaction><active>0</active></action>
  <action><name stringid="802">ExtraAttack</name><type>Attack</type><attackaction>1</attackaction></action>
  <action><name stringid="805">Heal</name><type>Heal</type><active>0</active></action>
  <tactic>Volley
    <action priority="100">SpecialAttack</action>
    <action priority="99">VolleyRangedAttack</action>
    <action priority="75">BuildingAttack</action>
    <action priority="25">VolleyHandAttack</action>
    <action priority="10">ExtraAttack</action>
    <action>Heal</action>
  </tactic>
  <tactic>Other<action priority="99">ExtraAttack</action></tactic>
</tactics>"""
STRINGS = {900: ("Gunman", None), 901: ("Hall", None), 801: ("Ranged ATK", None), 802: ("Hand ATK", None),
           803: ("Siege ATK", None), 24320: ("Hitpoints:", None), 35758: ("Resists:", None), 24323: ("Speed:", None)}
CFG = """// test keys
attackTypeIcons AbstractLightInfantry 42089 ui\\ingame\\stat_icon_informers
overhealHitpointBars AbstractInfantry
"""
ROWS = """<?xml version="1.0" encoding="utf-8"?>
<minUIRows>
  <row gadget="unitselectionpanel-uhcRow0" text="LOS: {los}|Garrison: {garrison}|Overheal {overheal}"/>
  <row gadget="unitselectionpanel-uhcRow9" item="speed" label="Speed: "/>
  <row gadget="unitselectionpanel-uhcRowB" item="buildPoints" label="Build: " types="Building"/>
</minUIRows>"""
SEL = ["unitselectionpanel", "unitselectionpanel-unitTypeName", "unitselectionpanel-unitPlayerName",
       "unitselectionpanel-unitHitPointsLabel", "unitselectionpanel-unitHitPointsValue",
       "unitselectionpanel-unitResistsLabel", "unitselectionpanel-unitResistsValue",
       "unitselectionpanel-StackLabel0", "unitselectionpanel-StackLabel1", "unitselectionpanel-StackLabel2",
       "unitselectionpanel-unitHealthBarGreen", "unitselectionpanel-unitHealthBarRed", "unitselectionpanel-unitPortrait",
       "unitselectionpanel-uhcRow0", "unitselectionpanel-uhcRowB"]
GADGETS = {n.lower(): {"parent": None if n == "unitselectionpanel" else "unitselectionpanel", "hidden": False} for n in SEL}


def run(unit=UNIT, variant="min", keys=(), state=None, rows=ROWS, dll=True):
    u = up.read_unit(unit)
    a = up.attacks(u, up.read_tactics(TACTICS) if "Tactics" in unit else None)
    k = up.read_cfg([CFG])
    for key in keys:
        k[key.lower()] = []
    return up.simulate(u, a, variant=variant, gadgets=GADGETS, strings=STRINGS, keys=k,
                       rows=up.read_rows(rows) if rows else None, dll=dll, state=state)


def reasons(r, item):
    for a in r["absent"]:
        if a["item"] == item and a["kind"] == "dll":
            return [x["code"] for x in a["reasons"]]
    return None


class Reading(unittest.TestCase):
    def test_a_unit_block(self):
        u = up.read_unit(UNIT)
        self.assertEqual((u["name"], u["hp"], u["los"], u["train"], u["armor_value"], u["armor_type"]),
                         ("Gunman", 150, 16, 30, 0.2, "hand"))
        self.assertIn("unit", [t.lower() for t in u["types"]])
        self.assertEqual(u["actions"]["volleyhandattack"]["bonuses"][0], ["AbstractLightInfantry", 3.0])

    def test_the_attacks_of_the_first_tactic(self):
        u = up.read_unit(UNIT)
        a = up.attacks(u, up.read_tactics(TACTICS))
        # by priority; SpecialAttack is switched off (active 0); Heal is not an attack
        self.assertEqual([x["name"] for x in a], ["VolleyRangedAttack", "BuildingAttack", "VolleyHandAttack", "ExtraAttack"])
        self.assertEqual(a[1]["maxrange"], 6)                     # the tactic's when the proto has none
        row = up.attack_row(a[0], STRINGS, {})
        self.assertTrue(row.startswith("Ranged ATK: 23 <icon=") and ", 12 <icon=" in row)
        hand = up.attack_row(a[2], STRINGS, {"abstractlightinfantry": "ui\\ingame\\stat_icon_informers"})
        self.assertIn(", 3x <icon=\"(16)(ui\\ingame\\stat_icon_informers)\">", hand)   # the first bonus, its icon
        self.assertNotIn("1.75", hand)                            # a hand attack shows no range

    def test_keys_and_rows(self):
        k = up.read_cfg([CFG, "+minUIStats\n"])
        self.assertEqual(k["overhealhitpointbars"], ["AbstractInfantry"])
        self.assertIn("minuistats", k)
        rows = up.read_rows(ROWS)
        self.assertEqual(rows["rows"][0]["items"], ["garrison", "los", "overheal"])
        self.assertEqual(rows["rows"][2]["types"], ["Building"])


class Panels(unittest.TestCase):
    def test_the_minimised_panel(self):
        r = run()
        g = r["gadgets"]
        self.assertEqual(g["unitselectionpanel-unittypename"]["text"], "Gunman")
        self.assertEqual(g["unitselectionpanel-unithitpointsvalue"]["text"], "150/150")
        self.assertTrue(g["unitselectionpanel-unitresistsvalue"]["text"].startswith("0.20 <icon="))
        self.assertEqual(g["unitselectionpanel-unitresistslabel"]["colour"], up.YELLOW)
        self.assertEqual([g[f"unitselectionpanel-stacklabel{k}"]["text"].split(":")[0] for k in range(3)],
                         ["Ranged ATK", "Siege ATK", "Hand ATK"])
        self.assertEqual(g["unitselectionpanel-stacklabel0"]["colour"], up.CYAN)
        no_room = [a for a in r["absent"] if a["reasons"][0]["code"] == "no_room"]
        self.assertEqual(len(no_room), 1)                          # the 4th attack is left out
        self.assertEqual(g["unitselectionpanel-unitportrait"]["background"], "units\\gunman_portrait")
        self.assertTrue(g["unitselectionpanel-unithealthbargreen"]["show"])
        self.assertFalse(g["unitselectionpanel-unithealthbarred"]["show"])
        self.assertEqual(r["live"]["currentunitlos"], "16")
        self.assertEqual(r["live"]["currentunitattackrange"], "")   # a stub of the stock game

    def test_a_building_shows_no_resists(self):
        r = run(BUILDING)
        g = r["gadgets"]
        self.assertFalse(g["unitselectionpanel-unitresistslabel"]["show"])
        self.assertEqual(g["unitselectionpanel-unitresistslabel"]["why"], "not_unit")
        self.assertIn("resists", [a["item"] for a in r["absent"]])

    def test_the_normal_ui_has_a_speed_row(self):
        r = run(variant="normal")
        self.assertNotIn("speed", [a["item"] for a in r["absent"] if a["kind"] == "stock"])
        r = run(variant="min")
        self.assertIn("ui_variant", [x["code"] for a in r["absent"] if a["item"] == "speed" and a["kind"] == "stock"
                                     for x in a["reasons"]])

    def test_health_bar_by_share(self):
        r = run(state={"hp": 30})
        self.assertTrue(r["gadgets"]["unitselectionpanel-unithealthbarred"]["show"])
        self.assertAlmostEqual(r["gadgets"]["unitselectionpanel-unithealthbarred"]["fraction"], 0.2)


class DllRows(unittest.TestCase):
    def test_every_reason_an_item_does_not_show(self):
        r = run()                                                   # minUIStats is off
        self.assertEqual(reasons(r, "overheal")[0], "key_off")
        self.assertIn("needs_state", reasons(r, "overheal"))       # no hit points above the start
        self.assertIn("gadget_missing", reasons(r, "speed"))       # its row names a gadget not in the layout
        self.assertIn("not_placed", reasons(r, "cost"))            # no row places it
        self.assertFalse(r["gadgets"]["unitselectionpanel-uhcrow0"]["show"])
        r = run(dll=False)
        self.assertEqual(reasons(r, "los")[0], "dll_absent")
        r = run(rows=None, keys=["minUIStats"])
        self.assertIn("no_rows_file", reasons(r, "los"))

    def test_overheal_shows_with_its_key_its_type_and_its_state(self):
        r = run(keys=["minUIStats"], state={"overheal": 30})
        row = r["gadgets"]["unitselectionpanel-uhcrow0"]
        self.assertTrue(row["show"])
        self.assertEqual(row["text"], "LOS: 16   Overheal +30")       # garrison has no room: its part is left out
        self.assertIsNone(reasons(r, "overheal"))
        # its type not listed by the key
        k = up.read_cfg(["overhealHitpointBars AbstractCavalry\nminUIStats\n"])
        u = up.read_unit(UNIT)
        r = up.simulate(u, up.attacks(u, up.read_tactics(TACTICS)), variant="min", gadgets=GADGETS, strings=STRINGS,
                        keys=k, rows=up.read_rows(ROWS), dll=True, state={"overheal": 30})
        self.assertIn("type_not_in_key", reasons(r, "overheal"))
        # without its key
        k = up.read_cfg(["minUIStats\n"])
        r = up.simulate(u, up.attacks(u, up.read_tactics(TACTICS)), variant="min", gadgets=GADGETS, strings=STRINGS,
                        keys=k, rows=up.read_rows(ROWS), dll=True, state={"overheal": 30})
        self.assertIn("needs_key", reasons(r, "overheal"))
        en = [x for a in r["absent"] if a["item"] == "overheal" for x in a["reasons"] if x["code"] == "needs_key"][0]["enable"]
        self.assertEqual(en, {"keys": ["overhealHitpointBars"]})

    def test_a_row_for_buildings_only(self):
        r = run(keys=["minUIStats"])
        self.assertEqual(r["gadgets"]["unitselectionpanel-uhcrowb"]["why"], "type_filter")
        r = run(BUILDING, keys=["minUIStats"])
        self.assertEqual(r["gadgets"]["unitselectionpanel-uhcrowb"]["text"], "Build: 60")

    def test_the_catalog(self):
        items = up.table("uhc_minui_items")
        self.assertEqual(len(items["items"]), 30)
        for it in items["items"]:
            self.assertTrue(it["en"] and it["es"] and it["ref"].startswith("uhc"), it["item"])


if __name__ == "__main__":
    unittest.main()
