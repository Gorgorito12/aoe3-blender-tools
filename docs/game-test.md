# Testing a building in the game

Never write into the game's Steam folder. Work in a copy, and let `tools/game_deploy.py` change
it: it refuses any Steam folder, keeps the first backup of each file it edits
(`<file>.aoe3bt-orig`) and lists everything in `aoe3bt-manifest.json`, which `--undo` reads.

## 1. Make a test copy (once)

```
robocopy "<Steam>\steamapps\common\Age Of Empires 3\<mod folder>" C:\AoE3-BT-Test /E /XD avi .git
```

`avi` holds only the intro videos; start the game with `+noIntroCinematics`. Check that the copy
has no compiled twins of the data files it will edit (`data\protoy.xml.xmb`,
`stringtabley.xml.xmb`): the engine would read those instead.

If the copy has the mod's validators at its root (`validate_proto.py`, ...), run them once on
the clean copy to know which warnings were already there:

```
python -I -X utf8 tools/game_deploy.py --install C:\AoE3-BT-Test --validate
```

## 2. Export and deploy

```
venv\Scripts\python scripts\game_export.py --out out\wh --preset WHITE_HOUSE --detail MEDIUM --prefix <mod folder> --display "White House"
python -I -X utf8 tools\game_deploy.py --install C:\AoE3-BT-Test --bundle out\wh --validate
```

Or, in Blender: Sidebar > AoE3 > Game Export, then the second command. Deploying again replaces
the earlier deployment; `--undo` restores the copy.

## 3. Look at it

The data is read once, at start: close the game before deploying again.

1. Start `C:\AoE3-BT-Test\age3y.exe +noIntroCinematics`.
2. Help and Tools > Scenario Editor > the Objects button (place objects); the list is in
   alphabetical order of the name shown in the editor ("White House").
3. Select it (the preview shows the model), click on the map to place it, and place a stock
   `House` and `Town Center` next to it.

Check, in this order:

| What | Expected | If not |
|---|---|---|
| It loads | the preview and the placed building show the model | the model file: `tools/gr2_tree.py` and the Granny runtime's own check |
| Facing | the portico toward the bottom of the screen, as the stock buildings' fronts | flip the front in the writer |
| Scale | about the size of a Town Center (obstruction radius 4.07 against 4.5) | the profile's class or the units per metre |
| Texture | windows on the walls, upright | the V flip |
| Lighting | lit like the stock buildings around it | normals or winding |
| Obstruction | the selection square and the ground decal fit the walls | the profile's ratios |
| Construction | stages 1 to 3 of the 4x4 set, then the building | the anim file |
| Destruction | rubble (`BuildingRubble4x4`) | the proto's DeadReplacement |
| Player colour | the string courses (and shutters) in the owner's colour | the alpha mask or the shader |

## Status (2026-11-03)

Seen in game, in a copy of the target mod (White House, medium detail, DXT3 texture with the
player-colour mask, rendered icon and portrait):

- The scenario editor lists it and its preview draws the model.
- On the map it stands at the right size next to a stock house and the villagers, lit like the
  stock objects, textured the right way up, the civilization flag on `bone_flag_civ`, the ground
  decal under it.
- Player colour: its string courses show blue for player 1 and red for player 2.
- Selected, the interface shows its own icon, portrait and name.
- Built by a villager (cost paid, +10 population): the stock 4x4 construction stages, then the
  finished building.
- Damaged to 40 % and killed by triggers: it goes, and `BuildingRubble4x4` takes its place.

Obstruction (2026-11-03): a stock house fits 2 units from it, and musketeers sent straight
across walked round its south side, 0.3 to 2 units outside the obstruction square, and reached the target. Three of the six never moved in two runs: to look into, not tied to the building so far.

Low-poly and damaged variants (2026-11-03): the game loads the anim file with the `LowPoly` and
`Destruction` logic and the three models without an error. The damaged model did not show, at
70 % nor at 2 % of the hit points: the `Destruction` logic is not driven by the hit points alone.
The stock houses pair their damaged model with a damage template (`.dmg`, impact points and
debris bones) in the Idle anim's `simskeleton`; that is the next thing to try. The low-poly
model needs the game's low model detail setting (not tried).

Death animation (2026-11-03): when the building is killed it sinks and fades in about 2 seconds
while the stock collapse dust rises, then the rubble takes its place.

## Driving a test without clicks

The game's own triggers can place and drive everything:

- a test map script places the building, a stock house and villagers for each player;
- trigger effects at given seconds: `Grant Resources` (the build cost), `Unforbid and Enable Unit`
  (a new building is not enabled for any player until something enables it, as the
  civilization techs do for stock buildings), `Unit Build Building` (a villager builds it at a
  point), `Damage Unit Percent` and `Kill`.

The villager must have the building in its build list: deploy with `--builder Settler` (test copy
only). Selection calls typed on the console (`trUnitSelectByID`, `trUnitBuildUnit`) did nothing
outside a trigger. The console camera commands (`uiLookAtUnit`,
`uiLookAtAndSelectUnit`) centre the view only when the game window sits at the top-left corner of
the screen (0, 0); elsewhere the unit ends up off centre by the window's offset. The game draws only while its window has the foreground: a screenshot of a copy that runs behind another game's window shows an old frame (the simulation goes on, so unit positions stay right). An engine extension DLL with a console command file option lets a script run
the console commands that load the map and point the camera, and one with a multiple-instances
option lets the test copy run beside another copy of the game.

A way to look without the editor, for a test copy only: deploy with `--show-as TownCenter`.
The copy's Town Center then takes the new building's model, icon and portrait, so the building
stands at the start of any skirmish (press T to select it and see the portrait, Delete to
destroy it). Deploy again without the option, or `--undo`, to restore the copy.

```
python -I -X utf8 tools\game_deploy.py --install C:\AoE3-BT-Test --bundle out\wh --show-as TownCenter
```
