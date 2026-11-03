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

## Status (2026-11-02)

Seen in game, in a copy of the target mod:

- The scenario editor lists the White House and its preview draws the model with its texture.
- In a skirmish, with the copy's Town Center temporarily pointed at the White House's anim file
  (restored afterwards by deploying again): the building stands at the start position, lit like
  the stock objects around it; walls, windows, roof, chimney, cupola and portico textured the
  right way up; the civilization's flag flies from the `bone_flag_civ` bone; the ground decal
  shows; its size next to the villagers is right (a villager is about half a storey).

Not yet seen: construction stages, destruction and rubble, the player colour, and the
obstruction ring next to a placed stock house (placing objects in the editor needs a real
mouse click; posted clicks do not reach the map).

A way to look without the editor, for a test copy only: point the `TownCenter` unit's
`<AnimFile>` at the new anim file, start a skirmish, then deploy again (or `--undo`) to restore
the copy.
