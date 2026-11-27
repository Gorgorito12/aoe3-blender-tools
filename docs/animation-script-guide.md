# How to script a unit's animation

A guide to describing an animation you want, with the zamburak cannon's camel as a worked example.

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
