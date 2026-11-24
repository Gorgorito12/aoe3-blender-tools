# Animation rules

How a unit's animations are made and shown for review, so that the person who asked sees a
preview only after the problems a machine can find are gone. Three parts: a script first (A),
automatic checks (B), and a fixed preview format with a checklist (C).

Why: one camel gun needed four review rounds for problems that could have been caught before the
first preview: the mounted gun floated off its post when it turned; the reload put the same
magazine back (an incomplete action); the gunner's head whipped round more than 90 degrees and
tipped far back while he reached to a pocket; and an existing dismount was removed without anyone
saying so. Each of those is now a rule below and a check of `tools/check_anim.py`.

## A. Script first

Before any key pose, write the **beat list** of every clip in plain words and get it approved by
the person who asked. A beat is one thing the figure does, with its start and end time in seconds
(the clip's length is the game's: the tactics file says it).

1. **Each action is complete, as a person would do it.** For every object that moves, say where it
   comes from and where it goes: out of which pocket, onto which ground, into which socket. For
   every beat, say what the hands do (which hand holds what), what the feet do (planted, stepping,
   which one first), and where the eyes look. An object never comes from nowhere or goes nowhere:
   if it must appear or vanish, say where it hides (inside a body, under the ground after it
   falls, behind the hand in a pocket).
2. **Comfortable limits.** A head turns at most about 70 degrees from the chest and tips about 40
   degrees up or down; to look further the shoulders turn too, and say so in the beat. Elbows and
   knees bend one way only. Nothing snaps: a turn takes time.
3. **Anything removed is named on its own line.** If a clip or a motion that exists today goes
   (a dismount, a reload step, an idle fidget), write `REMOVED: <what>, because <why>` as a line
   of its own, so that the person who asked approves the removal explicitly. The same line goes
   into the job file's `removed` (part B).
4. **Contacts are named.** Which hand holds which grip and when; which part is mounted on which
   (a gun on its post, a rider in his saddle); which feet are planted.
5. The beat list is the source of the job file's routes, grips, mounts and removals: what is not
   in the script cannot be checked.

### Example: a reload on a mounted gun (3.0 s)

```
Clip: reload (3.0 s, the tactics' ranged reload). Loop: no. Feet: seated, both in the stirrups.

0.00-0.30  He lets go of the crank; right hand goes to the reins. Eyes on the magazine.
0.30-0.80  Left hand to the magazine on top of the breech; fingers close on it.
0.80-1.40  Left hand lifts the empty magazine up and out (0.3 m), then throws it out to his left,
           away from the camel. Eyes follow it for 0.2 s, then come back to the breech.
           The magazine falls (1.4-1.8), lies on the ground (1.8-2.4) and sinks out of sight (2.4-2.8).
1.40-1.90  Left hand down to the pocket on his left hip; head turns left at most 45 degrees and
           bows at most 30. Shoulders turn 15 degrees with it.
1.90-2.40  Left hand draws the full magazine out of the pocket (it was inside the pocket, hidden
           by the hand) and lifts it to the breech. Eyes on the breech.
2.40-2.70  He seats the full magazine in the well and presses it home (a 2 cm push).
2.70-3.00  Left hand back to the breech's side, right hand from the reins back to the crank.
           Eyes forward along the barrels.
REMOVED: nothing.
Objects: empty magazine: well -> thrown left -> ground -> hidden under the ground.
         full magazine: hidden in the pocket -> hand -> well.
Contacts: right hand on the crank at 0.00 and from 3.00; left palm on the magazine 0.80-1.40
          and 1.90-2.70.
```

## B. Automatic checks

`tools/check_anim.py` checks a unit's clips with the actors put together as the anim file hangs
them. Run it before any preview is made; **when it fails the preview is refused**: fix the clip,
or, when the script says so, raise that limit for that clip in the job file and keep the reason
in the script. Library: `aoe3_blender_tools/aoe3game/anim_check.py` (pure Python and numpy).
Test: `tests/test_check_anim.py`.

```
python -I tools/check_anim.py <job.json> [--baseline <previous job.json>] --json <report.json> --risk-sheet <risk.png>
python -I tools/check_anim.py --model <model.gr2> --anim <clip.gr2> [--anim ...] [--duration 3.0] [--ground none]
```

It prints PASS or FAIL per check with the worst frame and its value against the limit, then the
risk frames (the worst frames of every failed check, then of every check that came within half
of its limit), and exits 1 when a check fails (2 when the job cannot run). Models must be
uncompressed (`tools/uncompress_models.py`, or the helper of `recompress_models.py`).

**Space.** Every actor is posed with the runtime's scales and brought to one space: the stock axes
(the unit faces +z, y up) in metres as the files declare them (units / UnitsPerMeter: a game human
is about 2.7 of these tall, so a "metre" here is about 0.65 of a real one). The ground is y = 0 of
the first actor (set `ground` to `null` for a lone rider whose space has no ground).

| Check | What it measures | Default limit |
| --- | --- | --- |
| `look` | A head and a neck turned from the chest (the highest spine bone), measured from the rest pose: yaw left or right, pitch up, pitch down | 70 deg yaw, 40 deg up, 40 deg down |
| `hinge` | An elbow or knee bent the wrong way: the bend's direction against the limb's front at rest (the elbow bends to the front of the upper arm, the knee to the back of the thigh); judged when bent more than 10 deg | reversed past 100 deg |
| `speed` | Every bone's local rotation per second (props and the job's `speed_exempt` bones, such as a spinning barrel, excepted; `speed_limits` sets a bone's own) | 1500 deg/s; head and neck 800 deg/s |
| `plant` | A foot point (heel and toe, from the skinned mesh) near the ground (3 cm) and slow (0.3 m/s) is planted; how far it slides while planted, the ground moving under a walk at its `ground_speed` | 4 cm |
| `sink` | A foot point below the ground | 5 cm |
| `grip` | A hand point from its grip during the frames given | 3 cm |
| `mount` | The point of a part that sat on its mount at the first frame, against the mount, every frame | 2 cm |
| `prop` | A prop that jumps (faster than 20 m/s, 0.67 m a frame at 30) or scales to nothing in sight; out of sight is inside a hiding capsule, under the ground by its size, or scaled away; twin props trading places in one frame are not seen | none allowed |
| `route` | Each object of the script starts and ends where it says (`hidden`, `ground` or a named place), followed through swaps | as the script |
| `penetration` | Hands, feet, props and named points below the ground or inside a capsule (a mount's body; every human's torso, pelvis to neck, 0.12 m) | 2 cm |
| `duration` | The clip's length against the tactics' value; every actor's clip as long as the others | 1 ms |
| `loop` | The seam of a loop (last pose to first) for every bone, against the largest step between two frames inside the clip | 1.5 x that step, at least 3 deg and 2 cm |
| `death` | At the end of a death clip each part (an actor's mesh, else its bones, and each prop) rests on the ground or on a part that does | 5 cm |
| `inventory` | With `--baseline`: every clip of the version before is there, and every motion of it (a human's pelvis and feet; every bone of other actors) that travelled 0.3 m still travels half as far, unless `removed` names it | as listed |

Measured on stock clips (2026-11-24), so a limit is not read as a law: the game's own seated rider
tips his head up to 59 deg from his leaning chest when he aims; infantry deaths turn the head 77
deg and bow it 49; stock walks sink their toes 3 to 6 cm and a salute slides a toe 6 cm; a
grenadier's throw turns the head 99 deg. A clip that needs more than a limit says so in its
script and raises the limit in its job (`"limits"` of the clip). A foot that slides faster than
0.3 m/s reads as a step, not a slide: give a walk its `ground_speed` (or leave `auto`, the default
for walk, jog, run and the like).

### The job file

A JSON file beside the outputs (paths relative to it). Only `actors` and `clips` are needed.

```json
{
  "fps": 30,
  "ground": 0.0,
  "actors": {
    "camel": {"model": "camel_nogun.gr2", "rig": {"preset": "bare",
              "feet": [{"name": "hoof front left", "bone": "HS Bone Hoof Frnt Lt"}]}},
    "gun":   {"model": "gun.gr2", "attach": {"to": "camel", "bone": "bone attachpoint"}},
    "rider": {"model": "rider.gr2", "rig": "human", "attach": {"to": "camel", "bone": "bone attachpoint"}}
  },
  "clips": {
    "reload": {"anims": {"camel": "camel_reload.gr2", "gun": "gun_reload.gr2", "rider": "rider_reload.gr2"},
               "duration": 3.0, "loop": false,
               "routes": {"magazine": {"start": "well", "end": "hidden"},
                          "spare": {"start": "hidden", "end": "well"}}},
    "idle":   {"anims": {"camel": "camel_idle.gr2", "gun": "gun_idle.gr2", "rider": "rider_idle.gr2"},
               "duration": 4.333, "loop": true}
  },
  "mounts": [{"name": "turntable on the post", "part": "gun:bone_yaw",
              "mount": {"bone": "camel:hs bone chest", "at": "gun:bone_yaw"}}],
  "grips": [{"name": "right hand on the crank", "clips": ["fire"], "hand": "rider:bip01 r hand",
             "grip": {"bone": "gun:bone_crank", "offset": [0.0, 0.12, 0.0]}, "frames": [[0.0, 1.0]]}],
  "capsules": [{"name": "camel body", "a": "camel:hs bone pelvis", "b": "camel:hs bone chest", "radius": 0.45}],
  "props": {"magazine": {"bone": "gun:bone_ammo", "size": 0.12},
            "spare": {"bone": "gun:bone_ammo2", "size": 0.12, "hide_in": ["camel body"], "twin": "magazine"}},
  "places": {"well": {"point": {"bone": "gun:bone_cannon", "at": "gun:bone_ammo"}, "radius": 0.03}},
  "speed_exempt": ["gun:bone_barrel", "gun:bone_crank"],
  "removed": {"deploy:rider": "REMOVED line of the script, with its reason"},
  "limits": {"look_pitch_up": 45}
}
```

- **Actors.** `model`: an uncompressed `.gr2` with its skeleton (its meshes give the feet's soles
  and the pictures), or a rig `.json` (`{"basis": "metres", "bones": [{"name", "parent",
  "position", "orientation"}]}`). `rig`: `"human"` (the game's Bip01 rigs: chest, head and neck,
  elbows, knees, feet, hands and torso named; override any key) or `"bare"` (nothing named; add
  `feet`, `look`, `hinges` as needed). `attach`: the actor hangs by its root (or `from_bone`) on
  the parent's `bone`, that bone's scale taken out, as the anim file's `<attach>` does.
- **Points** are `"actor:bone"`, `{"bone": "actor:bone", "offset": [x, y, z]}` (metres in the
  bone's frame) or `{"bone": ..., "at": <point>}`: the point fixed in that bone where `<point>` is
  at the clip's first frame. `at` makes the contact of the first frame the reference: a mount
  `{"bone": "camel:hs bone chest", "at": "gun:bone_yaw"}` is the post's top, wherever it is.
  Name points once under `"points"` to reuse them.
- **Mounts.** `part` is the bone that sits on the mount; its seat is the mount point at the first
  frame, carried by the part (or `seat`, in the part's frame). Choose the pivot the real thing
  turns on: a gun turns on its turntable and tips on its trunnion; one mount each.
- **Props and places.** `size` is how far below the ground a prop must go to be out of sight;
  `hide_in` the capsules it may hide in; `twin` the prop it may trade places with in one frame
  (the same object drawn twice). A place is a point with a `radius`. Routes take `start`, `end`
  and `via` (places passed in order). `allow_jumps` in a clip lists times (or `{"prop", "time"}`)
  where a jump is part of the script.
- **Clips.** `duration` (the tactics), `loop` (default: the name says idle, walk, jog, run...),
  `death`, `ground_speed` (m/s, or `auto`), `routes`, `allow_jumps`, `limits`.

## C. The fixed preview

Only after `check_anim` passes. Every preview sent for review has, per clip:

1. **A contact sheet from 4 sides x 2 heights** (front, left, back, right; 10 and 45 degrees up) at
   four moments of the clip: the start, a third, two thirds, the end.
2. **A close GIF**: a 3/4 view framed on the hands and the head, at 15 frames a second, for the
   whole clip.
3. **A risk frames sheet**: the frames nearest each limit, from two sides, the measured points
   ringed (`--risk-sheet`), with the check's value.

`python -I tools/check_anim.py <job.json> --preview <folder>` writes all three from the checked
files (flat-shaded meshes, no textures, so it needs no game copy); a generator may draw its own
textured sheets as well, in the same format. The GIF needs Pillow.

**The author reviews the preview against this checklist before sending it**, and says in the
message that it was done:

- [ ] Every beat of the script happens, at its time, in the order written.
- [ ] Every object comes from where the script says and ends where it says; nothing appears or
      vanishes in the open.
- [ ] Hands are on their grips when the script says (look at the close GIF, not the sheet).
- [ ] Mounted parts stay on their mounts from every side of the sheet, as they turn too.
- [ ] Feet: planted feet do not slide; no foot under the ground; a step lifts before it travels.
- [ ] The head looks where the script says, within the limits; no snap between two frames.
- [ ] Elbows and knees bend the right way in every risk frame.
- [ ] Loops: the last frame runs into the first without a jump (play the GIF twice).
- [ ] Deaths: nothing floats at the end, from both heights.
- [ ] Nothing that existed was removed unless the script has its `REMOVED:` line.
- [ ] The risk sheet's frames were looked at one by one.

**After the game.** Once the files run in a test copy, capture the in-game frames of every state
(idle, walk, run, attack, reload, deploy and the rest, and the death to its end) and check them
before reporting: legs on the ground, no floating parts at death, the right scale beside a stock
unit, attachments where they belong. The game's own drawing (its scales, its attach bones) is the
final judge: `check_anim` composes the actors as the anim file is read here, which is measured
but not proven for every case.
