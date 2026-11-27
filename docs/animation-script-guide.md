# How to script a unit's animation

A guide to describing an animation you want, with the zamburak cannon's camel as a worked example. The appendix
at the end gives that camel's full script as built, with every time and size.

A script is a list of beats: what moves, in what order, and what must line up with what. You write it, we build the clips from it, and you approve a preview before anything goes in game.

## What to write for each clip

For each clip (idle, walk, attack, reload, death, ...), write five things:

1. **What moves.** The parts that act in this clip: the animal, the rider or gunner, the weapon, a prop.
2. **The beats, in order.** One line each, for example "the camel pins its ears back", "the gun fires", "the tail flicks up".
3. **What lines up with what.** Beats that must happen together or one after the other. For example: "the ears pin back as the gun fires", "the head turns to watch while he loads".
4. **What must not happen.** For example: a hoof sliding, the head going through the barrel, the weapon sinking into the ground.
5. **What goes away.** Anything today's animation does that the new one should drop.

## Seconds are optional

You don't need to put seconds in a script.
- Words are enough: "early", "as the gun fires", "while he reloads", "slowly", "a quick flick".
- We set the exact times when we build the clip, and you approve them in the preview.

Put a number only when you want a precise rhythm. "The fuse burns for about a second" is a good example.

## What does need a number

Only a few things:
- **Clip lengths tied to the game's data:** the attack and the reload together make the rate of fire (ROF). If you want a different ROF, tell us the number, and we fit the clips to it.
- **Sync points the game reads:** the moment of the shot, which is when the damage, the sound and the muzzle flash happen.
- **Sizes, only if they matter to you.** "A small rock" or "big, unhurried steps" is usually enough. A number like "15 degrees" helps when you have already seen a version and want more or less.

## Template

Copy one block per clip:

| Clip | |
|---|---|
| Name | e.g. Fire |
| Length | only if it matters (ROF), e.g. 2.0 s |
| What moves | |
| Beats, in order | 1. ... 2. ... 3. ... |
| Lines up with | |
| Must not happen | |
| Goes away | |

---

# Worked example: the zamburak cannon's camel

How the camel was scripted.
- **The life layer:** in the kneeling clips, the camel breathes, sways its tail, moves its ears, chews and turns its head. This is mild in the idle, reacts to the shot when firing, and is busiest in the reload.
- **The chest stays still:** it carries the gun.
- **Seamless joins:** each clip starts and ends in the same pose, so the idle, the shot and the reload follow each other without a jump.

Only the sync points have numbers.

## Limbered (on the move)

The camel's own clips play as they are, with its head kept clear of the barrel beside its neck:
- idle, walk, jog and run;
- bored idles and cheers.

## Unlimber

| Camel | Meanwhile |
|---|---|
| Kneels: the front goes down first, then the hindquarters | The rider leans back, then forward, holding the reins |
| Settles lying on its belly, legs folded under it | |
| Turns its neck aside, out of the gun's way | He draws the linstock and swings the gun out over the camel's right side |
| Lies still | He gets off on the left and walks to his station |

## Deployed idle (looped)

| Camel |
|---|
| One slow breath: the belly rises and falls |
| The tail sways lazily, once to each side |
| Chews its cud twice |
| Flicks one ear |

## Fire

Sync points: the linstock touches the vent at 0.70 s, the gun fires at 1.40 s, and the clip is 2.0 s long.

| Camel | Meanwhile |
|---|---|
| Breathes, and its tail sways | |
| Still | The linstock goes to the vent and touches it |
| Still | The fuse burns on the vent: sparks and a thread of smoke |
| **As the gun fires:** pins its ears back and flicks its tail up and back | The muzzle jumps up; flash and smoke at the muzzle |
| **The shot's jolt:** rocks away from the shot on its far knees (the near side lifts, nothing sinks); the neck nods just after | |
| Rebounds a little past rest and settles before the clip ends | The gun settles too |

## Reload

| Camel | Meanwhile |
|---|---|
| Breathes; the tail sways twice | |
| Turns its head toward the gunner and watches | He pushes the gun round until its muzzle points at him |
| Flicks one ear, chews its cud three times | He loads the charge, then shows the ball over the muzzle and pushes it in |
| Flicks the other ear, turns its head back | He swings the gun back to its rest |

## Turn beyond the gun's arc

A target outside the gun's arc turns the whole camel until the target sits square to its side.

| Camel |
|---|
| Gets up with its rump high, hind legs first |
| Turns on the spot in big, unhurried steps; the planted hooves never slide |
| Kneels again. It does not fire until it has knelt |

The only number here is a rate: 90 degrees a second.

## Limber

| Camel | Meanwhile |
|---|---|
| Lies still | He pulls the gun round, gets on, sets the gun in its travel pose and holsters the linstock |
| Turns its neck back to the front | |
| Gets up | The rider on the reins |

## Deaths

- **Unlimbered:** the camel's neck bends down until its head lies on the ground, and its body slumps to one side without rolling over. The gunner falls back and drops the linstock beside him.
- **Limbered:** three of the game's deaths play, on a model with the cannon built in. Gone: the other five, which drove the cannon into the ground.

## The gatling camel

Its kneeling clips (deployed, fire, reload) get the same layer of life:
- at each burst, the tail flicks, the ears stay pinned back through the burst, and the body gives a small shudder at each shot;
- in the reload, the camel turns its head toward the gunner.

---

# Appendix: the zamburak camel's full script, as built

The same clips with every time and size, as built on 2026-11-26.
- **You don't need this much detail to ask for an animation.** It is here for reference, and to compare against a video of the game.
- **Clip sources:**
  - the limbered clips are the camel's own;
  - the lying-down ones are borrowed from the game's bighorn sheep (lie down, lying idle, get up), fitted to a camel's kush.
- **Life layer:** the kneeling clips carry the layer of life described above. It is zero at each clip's first and last frames, and it never moves the chest.

## Limbered (on the move)

The camel's own clips:
- idle, walk, jog and run (the horse's gallop);
- three bored idles;
- four cheers.

The only change is that the head is kept clear of the barrel beside its neck.

## Unlimber (6.67 s)

| Time (s) | Camel | Meanwhile |
|---|---|---|
| 0.00–0.30 | Standing, starts to lie down | The rider on the reins |
| 0.30–1.60 | Kneels: the front goes down | The rider leans back 15° |
| 1.60–3.00 | The hindquarters go down | The rider leans forward |
| 3.00–3.33 | Settles in the kush | |
| 3.33–4.73 | Turns its neck aside | He draws the linstock; the gun swings from 30° to its rest at 90° (3.83–4.63) |
| 4.73–6.67 | Lies still | He gets off on the left (4.73–5.63) and walks to his station |

## Deployed idle (2.0 s, looped)

| Time (s) | Camel |
|---|---|
| 0.00–2.00 | One breath: the belly rises 0.8°, at its fullest at 1.0 s |
| 0.00–2.00 | The tail sways once, ±14° (one side at 0.5 s, the other at 1.5 s) |
| 0.60–1.40 | Chews its cud twice: the jaw opens 7° and moves 4° sideways |
| 1.10–1.40 | Flicks its right ear 25° |

## Fire (2.0 s)

| Time (s) | Camel | Meanwhile |
|---|---|---|
| 0.00–2.00 | Breath and tail sway, as in the idle | |
| 0.00–0.70 | Still | The linstock goes to the vent and touches it at 0.70 |
| 0.70–1.40 | Still | The fuse burns on the vent: sparks and a thread of smoke |
| 1.38–1.46 | Pins its ears back 40° (held to 1.66, eased off by 2.00) | |
| **1.40** | **The shot** | The muzzle jumps 15° in 0.08 s; flash and smoke at the muzzle |
| 1.40–1.50 | Rocks 4° away from the shot, about its far knees on the ground: the near side lifts, nothing sinks | |
| 1.45 | The neck nods 5°, 0.05 s behind the rock; the head tips back by a third of it | |
| 1.40–1.65 | Flicks its tail 35° up and back | |
| 1.50–1.95 | Rebounds 30% past rest and settles | The gun rebounds and settles by 2.00 |

## Reload (3.0 s)

| Time (s) | Camel | Meanwhile |
|---|---|---|
| 0.00–3.00 | One breath (fullest at 1.5 s); the tail sways twice | |
| 0.45–0.90 | Turns its head 15° toward the gunner, held to 2.30 | He pushes the gun to 105° (0.40–0.55); it swings on to 255° (0.55–1.15) |
| 0.80–1.10 | Flicks its left ear | |
| 1.00–2.20 | Chews its cud three times | He loads the charge (1.27–1.52) and the ball, shown over the muzzle (1.52–1.87) |
| 2.20–2.50 | Flicks its right ear | He swings the gun back to its rest |
| 2.30–2.75 | The head turns back | |

## Turn beyond the arc (90° in 1.9 s, 180° in 2.9 s)

A target outside +30° to +150° turns the whole camel until the target sits at +90°.

| Phase | Camel |
|---|---|
| Rise (0.45 s) | Gets up with its rump high: the hindquarters lead the chest by 12° at mid-rise; the body tips 15° nose down |
| Turn (90° a second) | Big, unhurried steps on the spot: both diagonal pairs once every 60°. Each swinging hoof lifts 22 cm and folds back 35°; the planted hooves never slide |
| Settle (0.45 s) | Kneels again. It does not fire until it has knelt |

## Limber (5.5 s)

| Time (s) | Camel | Meanwhile |
|---|---|---|
| 0.00–3.10 | Lies still | He pulls the gun to 60°, gets on (0.90–1.80), sets the gun to its travel pose and holsters the linstock |
| 3.10–3.33 | The neck turns back to the front | |
| 3.33–5.50 | Gets up | The rider on the reins |

## Deaths

- **Unlimbered (3.0 s):** over 1.4 s the camel's neck bends down at its base until its head lies on the ground, and its body slumps 12° to one side without rolling over. The gunner falls back; the linstock leaves his hand at 0.10 s and lies beside him.
- **Limbered:** three of the game's camel and cavalry deaths (two melee deaths and the fall to the right) play on a model with the cannon built in. The other five drove the cannon into the ground and are not played.

## The gatling camel

The gatling camel's kneeling clips (deployed, fire, reload) get the same layer of life:
- breath and a tail sway;
- at each burst, the tail flicked and the ears pinned back, held through the burst;
- a 0.6° shudder at each shot;
- in the reload, a head turn toward the gunner, chewing and ear flicks.
