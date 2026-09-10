# 02_avoider

Reactive obstacle avoidance on one forward ultrasonic beam, two short-range IR
detectors, and no encoders. The robot drives forward, slows as something
closes, brakes before it hits, turns its whole body to look left and right, and
takes the freer side.

**Nothing here is navigation.** There is no map, no odometry and no memory of
where it has been. It is a reflex loop with a state machine on top.

## Status

| | |
|---|---|
| Written | yes |
| Validated in simulation | yes — 50 rooms × 120 s, see below |
| Dry run on the robot | yes — 35 s, `pg dry`. Found a livelock the simulator never produced. |
| Live run, wheels raised | yes — 45 s. Pre-flight passed, armed, drove both wheels, 287 pings / 0 timeouts, heap flat. |
| **Wheels on the floor** | **not yet.** Speeds and turn durations are still uncalibrated. |

**Motor wiring is verified.** `forward()` drives forwards and channel A is the
left wheel, both confirmed by eye with `tools/motion_id.py`. The IR pots have
been trimmed and both pins now idle HIGH.

**What is still a guess:** `CRUISE`, `SCAN_MS`, `TURN_MS` and the stopping
distance. Nothing has been driven on the floor, so none of them have been
measured against real travel. See `docs/13` §13.8.

The constants in this file are argued for, not measured. Every one of them is a
guess until the wheels have turned.

## Run

```zsh
./pg sim                       # 25 simulated rooms, no board, no risk
./pg dry avoider 60            # on the board, motors deliberately untouched
./pg run avoider 60            # LIVE — wheels off the ground first
```

`pg dry` injects `PG_DRY=1`, and the app then never constructs `Motor.PicoGo`,
so GP16–GP21 are not merely idle — they are never claimed as outputs. Every
sensor, every decision and every pixel still runs. This is how to develop the
behaviour with the robot flat on a desk.

**Before the first live run:** put the robot on a book so the wheels hang free,
confirm the chassis power switch is ON, and keep `./pg stop` within reach.

## The three facts that shape the design

**1. A timed-out ping is not "clear".**

No echo means one of: nothing within range, a surface angled or soft enough to
reflect the pulse away, or a target inside the sensor's ~2 cm dead zone. Two of
those three are directly in front of you. `None` is therefore treated as
*unknown*: the robot drops to `BLIND_SPEED`, leans on the IR pair, and if the
silence lasts it stops and goes to look. Treating a timeout as open road is the
single fastest way to drive an avoider into a wall.

**2. Fast to stop, slow to go.**

One reading below `STOP_CM` brakes immediately. Getting back to full speed
takes `CLEAR_RUN` consecutive open readings. A false brake costs a second; a
false clear costs a collision, so the asymmetry is deliberate.

**3. The blit is not in the control path.**

A full ST7789 frame costs 78 ms. Sensing and deciding run every 45 ms; the
screen is redrawn a few times a second, with a floor so a `CRUISE`↔`SLOW`
flicker at the speed threshold cannot claim the loop. Letting the panel set the
control rate would leave the robot blind for most of its life.

## Reversing is the dangerous move

There is no rear sensor, and no free GPIO to add one to. Every centimetre
backwards is taken on trust.

The only thing the robot knows about the space behind it is that it just drove
forward through it. So it earns a **reverse credit** while driving forward,
spends it while reversing, and **loses all of it the moment it pivots** —
because after a turn, "behind" is somewhere it has never been. It will not back
up further than it has just come.

This is the closest thing to odometry available on a platform with no encoders,
and in simulation it was the difference between 34 collisions and 1.

## States

```
ARMING ─ pre-flight, then ─→ CRUISE ⇄ SLOW ─┐
                               │  ↕         │ obstacle
                               │ BLIND      │
                               └────────────┴─→ BACK ─→ SCAN ─→ TURN ─→ CRUISE
                                                  ↑                │
                            three avoids in 10 s ─┴── ESCAPE ──────┘
```

| State | What it does |
|---|---|
| `ARMING` | Countdown, then pre-flight. Refuses to drive on a failed check. |
| `CRUISE` | Forward, duty scaled to the headroom ahead. |
| `SLOW` | Same loop, below full speed because something is closing. |
| `BLIND` | The beam has gone quiet. Creep, watch the IR pair, and time out into a scan. |
| `BACK` | Reverse, but only if too close to rotate, and only on earned credit. |
| `SCAN` | Body-scan: pivot left, measure, pivot right, measure, pick the freer side. No servo, so the chassis is the gimbal. |
| `TURN` | Timed pivot. Abandons and flips if the leading IR fires; twice, then escalates. |
| `ESCAPE` | Three avoids inside ten seconds means trapped. Long reverse, big pivot, alternating direction. |
| `HALT` | Flat battery or a dead 5 V rail. |
| `FAULT` | Pre-flight failed. The motors never start. |

## Pre-flight

The app refuses to drive if:

- the echo pin is stuck high — a disconnected or dead module;
- ten pings in a row all time out;
- the battery divider reads below `RAIL_DOWN_V`, which on this board means the
  **chassis power switch is off**;
- the pack is below `BAT_HALT_V`.

An avoider whose only forward sensor is unplugged is far more dangerous than
one that will not start.

## What the simulator found

`./pg sim` runs this exact file on the Mac against a differential-drive
chassis in a 220 × 180 cm box with four obstacles. It stubs `machine`, `utime`,
`ST7789` and `ws2812`, and fakes the TB6612 at the **pin level**, so the real
direction and brake logic in `shared/lib/drive.py` is what gets exercised. The
virtual clock is charged for a ping's flight time and for the 78 ms blit, so
the simulated control loop runs at the rate the real one will.

It found four things that were genuinely wrong:

1. `SCAN`'s second leg is 520 ms long and never re-issued its command, so the
   deadman in `drive.py` cut power in the middle of every scan.
2. Reversing blind was causing every collision. Hence the credit scheme above.
3. Preferring pivots over reversing — the obvious fix — made it **much** worse
   (34 collisions), because without separation the robot re-triggered
   immediately and escaped constantly, and escapes reverse furthest.
4. `brake()` really is worth having: 1.0 cm to stop from 24 cm/s versus 1.9 cm
   coasting, and 2.2 cm/s residual versus 10.4.

**Result: 50 rooms × 120 s, 5 contacts.** Every one of them was a sideswipe —
contact at 82–85° off the nose while the forward beam correctly reported 75–144
cm of open road. That is not a bug in this code. Everything on this robot
points forward; nothing looks sideways. A robot driving nearly parallel to a
wall will brush it, and no threshold in this file changes that.

**Two honest caveats.** The physics are crude — a first-order lag standing in
for inertia, no wheel slip, no motor mismatch. And the whole thing is a model I
wrote from the same assumptions as the app, so it can only catch disagreements
between the code and my reasoning, never errors in the reasoning itself. It
proves the *logic*. The constants still have to be earned on the floor.

## Fixing the sideswipe, properly

There are no free GPIO — but the TLC2543 line-sensor ADC has **six unused
inputs** (A5–A10), already wired and already driven by PIO. Two analog IR
distance sensors on A5 and A6, aimed left and right, would cost no GPIO at all
and would close the only gap this design cannot reason its way out of. See
`docs/09-extending-the-platform.md`.

## Files

| | |
|---|---|
| `main.py` | the app |
| `../../shared/lib/drive.py` | speed ceiling, brake, deadman, dry-run |
| `../../tools/sonar_check.py` | on-board sensor characterisation, no motors |
| `../../tools/host/sim_avoider.py` | the Mac-side simulator behind `pg sim` |
| `../../docs/13-obstacle-avoidance.md` | the reasoning in full |
