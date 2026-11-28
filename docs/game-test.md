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
the earlier deployment (`--keep` adds to it instead); `--undo` restores the copy.

**A bundle made without Blender: seen in game (2026-11-19).** `scripts/game_export_noblender.py` (same options;
the studio's "Without Blender, experimental") writes the same bundle from the generator's own mesh
(`core/gamemesh.py`) and its own icon renderer (`core/softrender.py`). Measured against Blender's
bundle of the same building (2026-11-17, four presets): the textures, bump maps, anim file, proto
and strings byte for byte; the models with the same vertices, normals and UVs, some quads cut
along the other diagonal (rendered alike, under 0.3 % of the pixels differ); the icons framed the
same, within 4 / 255 on average. **In game** (the WoL test copy, a scripted scene, no clicks): the
medium White House made with Blender and its twin made without stood side by side alike, with the
flag on its bone, the shadow and the ground mark; at 60 % damage both showed the damaged roof
alike; killed, both sank into the stock rubble and fire. Not looked at yet: the icon and portrait
when selected, the low model detail. Whether the export without Blender becomes the default is the
owner's choice.

**Your own model in game (2026-11-19).** `examples/timberinn/timberinn.glb` (written by Blender's
glTF exporter) through `scripts/mesh_to_game.py` with its own scale: placed in the same scene it
stood upright, the right way round, to scale beside the White House, its texture and shadow right;
killed, it went down as the others. A building made of an OBJ or a glTF of another program is not
yet seen.

**A copy's fonts in game (2026-11-19).** `tools/game_fonts.py stage` on the WoL copy, deployed with
`--files`: a building named "Sarja Roșior · Călărași ĂăȘșȚț őł" showed in the selection panel as
"Sarja Ro?ior · Călăra?i Ăă???? őł" before and with every letter in the game's own typeface after.
Each test was taken out afterwards: the copy came back identical to a snapshot taken before.

**A portrait's player colour in game (2026-11-27).** The same Struggle of Indonesia portrait as the
Musketeer's (DXT3, its alpha the player-colour mask) and as the Crossbowman's (DXT1), each selected
as player 1 and player 2 in a scripted scene: the masked clothes showed blue and red, the DXT1 ones
grey for both (`tools/reencode_textures.py` `keep: player_colour`, `docs/game-formats.md`).

**The Djenne armoury in game (2026-11-27).** `AFRICAN_ARMORY_SAHEL` exported with player colour and
its files deployed over the earlier armoury (`--files`), placed beside the stock arsenal: to scale,
its gate tower, cones, toron, the owner's cloth over the door, the yard and its gun as drawn; at
60 % damage it stands as before (with a texture budget the damaged model shares the main texture);
killed, it went. Seen there: the game's sun bleached the first plaster, so every earth colour was
darkened about 12 % (`djenne.py`). Not looked at yet: the bump map's reliefs up close, the low
detail model, player 2's colour on it.

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

A unit a test map creates does not take the heading of a placed building. For the front toward
the camera use the trigger effect `Unit Heading` with `Heading=225`; console `tr*` calls do nothing.

### Filming

For a sharp clip: set the zoom by console before the scenario loads (`configSetFloat("minZoom", 15)`,
`configSetFloat("normalZoom", 38)`), keep the camera still, crop at the window's own pixels, and make
the GIF from a lossless master, never from the MP4, at its native size:

```
ffmpeg -t 12 -i master.mkv -vf "fps=12,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" -loop 0 clip.gif
```

Do not move the game window once the camera is set: with the cursor left at its edge the camera
scrolls away. A rollover label shows while the cursor rests on the building: centre the camera on a
unit beside it instead, so the cursor falls on open ground.

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
Borrowing the stock outpost's damage system, as the mod's own large buildings do (`simskeleton`
with `outpost_generic_damaged` and its `.dmg`, and `shape="outpost_generic"` on the model
references), did not change that at 60 %.

Real hits (2026-11-03): three falconets and four musketeers (torches) took it from 1,200 hit
points to nothing in about 35 seconds of game time. It kept the intact model down to 80 hit
points (7 %), with flames on the roof; when it died it caught fire, faded while sinking, and
a pile of burnt debris and the rubble took its place. A stock `House` under the same attack
does the same: intact model with flames while it loses hit points, burnt debris when it dies.
So the `Destruction` logic is not a state between full health and death: in this game a
building looks intact until it is destroyed, and the damaged model only belongs to the
destruction. The damaged texture is kept for that and for mods that switch models by other
means; nothing more to do here. Frames from the recording:
`examples/whitehouse_medium/ingame_destruction.jpg`.

The low-poly model needs the game's low model detail setting (not tried).

Colonial house (2026-11-03): exported at medium detail with the player-colour mask (362
triangles, footprint class 4x4, the stock 2x2 construction stages and rubble), deployed with
`--builder Settler` (the three validators of the mod: 0 errors) and placed for two players beside
a stock house: the right size, lit like the stock buildings, the flag on the ridge, shutters and
door in each owner's colour, its own icon and portrait
(`examples/colonialhouse/ingame_player_colour.jpg`). A deployment replaces the previous one in
the copy (the White House was taken out).

Timber house (2026-11-03): medium detail with the material swatches and the player-colour mask
(426 triangles, class 4x4, stages 2x2), deployed the same way (validators: 0 errors) and placed
for two players beside a stock house: the right size, the flag on the ridge, shutters and door in
each owner's colour (`examples/timberhouse/ingame_player_colour.jpg`). The swatches' grain
showed no glitter in a still at the default zoom; to watch while the camera moves.

Several buildings at once (2026-11-03): `tools/game_deploy.py` takes several `--bundle`; the
four new presets went in together (ids 25000 to 25003, validators 0 errors;
`examples/ingame_styles.jpg`). Units of the player seen through a building show as their
silhouette in the player's colour: the game's own behaviour.

Material grain while the camera moves (2026-11-03): the four presets with swatches, the camera
panned by posted arrow keys (`pan.py` in the cache's scripts: key-down messages to the window, no
real input) and recorded at 10 frames a second. Each pair of frames was aligned on its shift and
compared: what is left on the buildings (median 7.6 grey levels, 90th percentile 10.1) is what is
left on the game's own terrain (7.4, 10.1). The swatches do not glitter more than the stock
textures.

Low model detail (2026-11-03): seen. The option is `optiongrfxhighmodels` ("High Poly Models", a
check box in `data/options.xml`), a `<Setting>` in the player profile (`Users3/<name>.xml` in
My Games, shared by every copy of the game); the profile here already had it off. With the
low-poly texture tinted magenta (in the copy only) the building still showed its normal model:
the low-poly reference lacked the `shape` attribute that every stock model reference carries.
With it the house turned magenta (`examples/colonialhouse/ingame_lowpoly_test.jpg`). The writer
now gives the low-poly reference the same shape, and a bundle with a low-poly model borrows the
damage skeleton that provides it even without a damaged model. The console command
`setGraphicDetail(0)` closes the game (the log ends on it): do not use it.

Death animation (2026-11-03): when the building is killed it sinks and fades in about 2 seconds
while the stock collapse dust rises, then the rubble takes its place.

## Units: T0, a unit written again unchanged

The first in-game test of the unit transplant (`aoe3game/gr2_edit.py`): the Musketeer's model
written again from its own tree, nothing changed. If the game draws and animates it as the
original, the writer can carry a unit; then T1 changes its mesh.

**Done (2026-11-19), passed**, in the WoL test copy, driven with no clicks (a test map of 7
Musketeers against 3 Hussars that charge them at 22 s, loaded through the editor and filmed from a
copy running behind the other windows, `multipleInstances background`; WoL's Musketeer draws
`musketeer_2age` before any age tech). Three runs of the same scene:
- **A**, the original (from `Art1.bar`): idle, the charge, firing, the bayonet, deaths on both sides.
- **B**, a control: the same file written again with its vertices 1.5 times larger. The Musketeers
  stood visibly taller and fought and died as before, so the game reads the loose file and our
  writer's tree; their hats and muskets were hidden inside the bodies, since only the vertices grew
  and those attachments ride the bones, which kept their place.
- **C**, T0: the identical rewrite. Drawn as in A: the plumed hat and the musket on their bones, the
  player colour, the shadow, the health bar, firing smoke, the bayonet, death; selected, its circle,
  portrait and panel rows. Not looked at: low model detail (`lp_musketeer_2age`, untouched) and the
  edges of the screen.
The test files were then taken out one by one, leaving the copy's other deployment in place.

1. Its uncompressed copy: the model cache of `tools/model_survey.py` (named by the original's
   MD5), or **Uncompressed models** in the studio.
2. Written again and checked by the game's runtime, kept in a folder laid out as the copy:
   `python -I tools/gr2_check.py <musketeer_2age, uncompressed>.gr2 --granny-install <copy>
   --rewrite --save <folder>\art\units\infantry_ranged\musketeer\musketeer_2age.gr2`
   (the studio: Art utilities, **Check models with the game's runtime**, *Keep the rewritten copy*).
3. Into the test copy: `python -I tools/game_deploy.py --install <copy> --files <folder>`
   (the studio: **Deploy edited files to the test copy**). A loose file is read before the one in
   `Art1.bar` (as for the buildings).
4. In game, a Musketeer of any civ that uses the stock model, beside one of a civ whose own model
   is not this file, if the mod has one: standing, walking, the ranged and the melee attack, dying;
   the hat and the musket on their bones; the player colour; the health bar; its shadow; selection;
   at the edges of the screen (cut off too early means a wrong bounding box); at low model detail
   (that is `lp_musketeer_2age.gr2`, untouched: it should look the same as before).
5. Undo: `python -I tools/game_deploy.py --install <copy> --undo`.

What a failure would mean: drawn but not animated, the skeleton is read otherwise than written;
not drawn at all, the game refuses the file (compare it with `tools/gr2_check.py` again, then
with the file recompressed by **Compress models again**, the form the original ships in).

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
