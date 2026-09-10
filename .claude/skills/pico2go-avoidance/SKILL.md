---
name: pico2go-avoidance
description: Autonomous obstacle avoidance and reactive navigation on the Pico2Go/PicoGo - fusing the forward ultrasonic beam with the two IR obstacle detectors, deciding when to stop, when to reverse, and which way to turn on a robot with no servo, no rear sensor and no encoders. Use when writing or debugging any behaviour where the robot drives itself, when a wander/roam/explore/avoid app is asked for, when the robot hits things or freezes mid-run, and before choosing any distance threshold or speed constant.
---

# Obstacle avoidance

Reference implementation: `projects/02_avoider`. Reasoning in full:
`docs/13-obstacle-avoidance.md`. Motor safety: the `pico2go-motion` skill.

## What the robot can perceive

One ~15° ultrasonic cone dead ahead, **fixed** — there is no servo on this
chassis. Two narrow IR lobes at roughly ±25°, reaching a few centimetres.
**Nothing points sideways or backwards.** Three forward sensors on a robot that
turns and reverses: that is the entire design constraint.

## The rule that matters most

**A timed-out ping is not "clear".**

`sonar.read()` returning `None` means one of three things and they are
indistinguishable: nothing in range, a surface angled or soft enough to reflect
the pulse away, or a target inside the ~2 cm dead zone. Two of the three are
directly in front of you.

Never write `if d is None or d > THRESH: go_forward()`. Treat `None` as
*unknown*: slow down, fall back on the IR pair, and if the silence persists,
stop and scan. This is the fastest way to drive an avoider into a wall and it
is what almost every tutorial on the internet does.

## Patterns that are already solved — reuse, do not re-derive

| Problem | Answer | Where |
|---|---|---|
| Motors keep running if the loop stalls | `Drive.tick()` deadman, 300 ms TTL | `shared/lib/drive.py` |
| Coasting into the obstacle you just detected | `Drive.brake()` — TB6612 short brake. 1.0 cm vs 1.9 cm from 24 cm/s | `drive.py` |
| Developing behaviour without driving | `pg dry <app>` → `PG_DRY=1` → `Drive(dry=True)` never constructs `PicoGo`, so GP16–21 are never claimed | `pg`, `drive.py` |
| Testing behaviour with no board at all | `pg sim` — runs the app on the Mac against a simulated room | `tools/host/sim_avoider.py` |
| Spiky ultrasonic readings | do **not** median in the control loop; be fast to stop, slow to go | `docs/13` §13.6 |
| Choosing a side with no servo | body-scan: pivot, measure, pivot back further, measure | `02_avoider` `SCAN` |
| Corner ping-pong | count avoids in a window → escape with an alternating direction | `02_avoider` `ESCAPE` |
| Reversing blind | the reverse credit, below | `docs/13` §13.4 |

## Reversing is the dangerous move

There is no rear sensor and no free GPIO to add one. In simulation, blind
reversing caused **every single collision** until it was bounded by:

> The robot may reverse for at most as long as it has just been driving
> forward, and any pivot spends that credit entirely.

A pivot destroys the knowledge, because after turning, "behind" is somewhere it
has never been. Cap the credit at about a second — beyond that, with no
encoders, the estimate is fiction.

**Do not "fix" this by never reversing.** That was tried: collisions went from
1 to 34. Without separation the robot re-triggers its avoid immediately, trips
the stuck detector constantly, and escapes — and the escape manoeuvre reverses
furthest of all. Removing the dangerous move made it happen more.

## Latency is stopping distance

| Term | Cost |
|---|---|
| control period | ~45 ms |
| ping that times out | `PING_US`, use **12 ms** (~2 m), not the 30 ms default |
| LCD blit | **78 ms** — keep it out of the sense→act path, redraw a few times a second |
| brake | ~1 cm from 24 cm/s |

Use the full 30 ms timeout only while stationary, where latency is free — the
deliberate scan, and there only.

## Before writing a new driving app

1. Read `pico2go-motion` first. Wheels off the ground; if the user is away, do
   not touch GP16–21 at all.
2. Start from `projects/02_avoider/main.py` — the state machine, the pre-flight
   and the exit path are all there.
3. Use `drive.Drive`, not `Motor.PicoGo` directly. The ceiling, the brake and
   the deadman are the point.
4. Honour `PG_RUN_SECS` **and** `PG_DRY`.
5. `board.estop()` in a `finally:`.
6. **Do not add a restart-on-exception loop.** `01_sensorous` has one because
   it cannot move. A robot on wheels that resurrects itself after an unknown
   fault, unattended, is worse than a stopped one.

## Pre-flight, and why it refuses

An avoider whose only forward sensor is unplugged is far more dangerous than
one that will not start. `02_avoider` refuses to drive when the echo pin is
stuck high, when ten pings in a row time out, when the battery divider reads
below `RAIL_DOWN_V` (**the chassis power switch is off**), or when the pack is
flat.

## The failure nobody can fix in software

Every collision left in simulation was a **sideswipe** — contact at 82–85° off
the nose while the forward beam correctly reported 75–144 cm of open road. A
robot driving nearly parallel to a wall will brush it, and no threshold
changes that.

The fix is hardware, and it is cheap: the TLC2543 line ADC has **six unused
inputs (A5–A10)**, already wired and already driven by PIO. Two analog IR
distance sensors aimed left and right cost **no GPIO at all**. Suggest this
before suggesting more tuning.

## Simulation is evidence, not proof

`pg sim` stubs `machine`, `utime`, `ST7789` and `ws2812`, fakes the TB6612 at
the pin level so the real direction and brake logic runs, and charges the
virtual clock for ping flight time and the 78 ms blit. It caught four genuine
bugs, including a deadman that cut power in the middle of every scan.

But it is a model written from the same assumptions as the app, so it catches
disagreements between the code and that reasoning — never errors in the
reasoning. Never tell the user a behaviour "works" on the strength of a
simulation. It works when the wheels have turned.
