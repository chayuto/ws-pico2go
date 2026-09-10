# 13 — Obstacle avoidance

Reference for `projects/02_avoider`. `docs/06` covers the sensors themselves;
this covers what to do with them when the robot is moving.

## 13.1 What the robot can actually perceive

| Sensor | Coverage | Range | Blind to |
|---|---|---|---|
| HC-SR04 (GP14/GP15) | one ~15° cone, dead ahead, fixed | ~2–400 cm | everything off-axis; anything angled more than ~60° from the beam |
| ST188 ×2 (GP2/GP3) | two narrow lobes, ~±25° | a few cm, pot-adjustable | everything else |
| — | **nothing points sideways or backwards** | | |

That table is the whole design constraint. Three forward-pointing sensors on a
robot that turns and reverses.

There is **no servo** on the Pico2Go. The ultrasonic module is bolted facing
forward. To look left and right, the chassis itself has to turn — which costs
about 1.4 s per scan, cannot be done while moving, and is why the avoider
scans only after it has already stopped.

## 13.2 The ambiguity of silence

A timed-out ping has three causes and they are indistinguishable:

1. nothing within range — genuinely clear;
2. a surface at high incidence, or soft, reflecting the pulse away — could be
   5 cm ahead;
3. a target inside the ~2 cm dead zone — is touching.

Two of the three mean *stop*. So no code in this repo may treat `None` as
clear. `02_avoider` treats it as **unknown**: reduce speed to `BLIND_SPEED`,
fall back on the IR pair, and if the silence outlasts `BLIND_MS`, stop and
scan on the assumption that it is a wall square-on.

The same ambiguity is why `sonar.read()` returns `None` rather than the vendor
sentinel `-1`. A number invites arithmetic; `None` forces a decision.

## 13.3 Latency budget

Stopping distance is decided long before the brake. It is the sum of:

| Term | Cost | At 25 cm/s |
|---|---|---|
| control period | 45 ms | 1.1 cm |
| ping, echo returned | **3.0 ms measured** | 0.1 cm |
| ping, timed out at `PING_US` | 12 ms | 0.3 cm |
| LCD blit, on render ticks only | 78 ms | 2.0 cm |
| `brake()`, blocking | 120 ms | — |
| brake to a stop | ~1.0 cm in simulation | 1.0 cm |

Worst case — a timed-out ping on a render tick — is about **4.4 cm**. Coasting
instead of braking nearly doubles the last term.

**Measured on the board, 2026-09-11.** `sonar_check` against a flat surface:
**100 % answer rate** at both the 12 ms and the 30 ms timeout, **3.0 ms per
ping**, and a standard deviation of **0.09 cm** over 60 samples. Two dry runs
logged **233 and 701 pings with zero timeouts**. This beam is far steadier than
the design assumed, which strengthens rather than weakens §13.6: there is no
spike noise worth paying detection latency to filter out.

Tick times, measured with the IR pair disabled so the robot could actually
reach a steady cruise:

| Tick | Measured |
|---|---|
| sense only — ping, pins, ADC, decide | **5 ms** |
| render tick — draw + blit + LEDs | **102–113 ms** |
| effective loop rate at `TICK_MS = 45` | **19.5 Hz** |

Sensing is cheap; drawing is not. The earlier figure of 123–229 ms per tick was
the **livelock** (§13.7a), which forced a brake and a redraw on nearly every
iteration. The design assumption was pessimistic about sensing by an order of
magnitude and roughly right about the render.

The heap slid **252 KB → 107 KB in four seconds** of that steady cruise —
around 14 KB/s, almost all of it text formatting for the panel and telemetry.
No leak, but an unscheduled collection is an unpredictable pause. `gc.collect()`
on the render tick holds it flat at ~390 KB and costs nothing, because that
tick already costs 100 ms. Collecting *only while stopped* — the first attempt —
did nothing at all, because a working robot is never stopped.

Two consequences, both of which shaped the code:

- **Cut the timeout.** `PING_US` is 12 ms (~2 m), not the 30 ms the sonar
  module defaults to. Anything past 2 m is "clear" for avoidance purposes, and
  halving the timeout halves the worst-case ping cost. The full 30 ms is kept
  for the stationary scan, where latency is free.
- **Keep the blit out of the loop.** Redraw a few times a second, with a floor
  on state-change redraws so a flickering state cannot own the control loop.

`STOP_CM` of 20 leaves roughly 15 cm of margin over that budget. That is
generous on purpose: none of the speed figures above have been measured on the
real chassis.

## 13.4 Reversing, and the credit that pays for it

No rear sensor exists and no GPIO is free to add one. Reversing is therefore
always blind, and in simulation it caused **every single collision** until it
was bounded.

The rule the avoider uses:

> The robot may reverse for at most as long as it has just been driving
> forward, and any pivot spends that credit entirely.

The reasoning: the space behind it is the space it just came through, so a
short reverse retraces known-clear ground. A pivot destroys that knowledge —
after turning, "behind" is somewhere it has never been. Credit is capped
(`CREDIT_MAX_MS`) because beyond a second or so the estimate is fiction: the
robot has no encoders and no idea how far a given duty actually carried it.

A tempting alternative — *never reverse, always pivot in place* — was tried and
was dramatically worse (34 collisions against 1). Without reversing, the robot
gains no separation, re-triggers its avoid immediately, hits the stuck detector
constantly, and escapes; and the escape manoeuvre reverses furthest of all.
**Removing the dangerous move made the robot do more of it.**

### Using the information instead of removing the manoeuvre

There is a version of that idea which does work, and the difference is precise.

A **single** IR detector firing is not "wedged". It is the only lateral
information this robot ever gets: something is close on one shoulder, therefore
the other shoulder is clear. Pivot away from it. Reserve reversing for being
*squarely* up against something — both detectors firing at once, or an echo
inside `PIVOT_CM`.

| | reverses | avoids | escapes | gave up | collisions |
|---|---|---|---|---|---|
| back off whenever any IR fires | 12/12 seeds | 189 | 21 | 2/12 | 5 / 50 rooms |
| pivot away on a one-sided hit | **0/12 seeds** | 199 | **16** | **0/12** | 6 / 50 rooms |

Reversing disappeared entirely, escapes fell by a quarter, and no run ever gave
up. Collisions moved by one across fifty rooms — noise, and all six were the
sideswipe of §13.7, which nothing in this file can fix.

The distinction that matters: the failed experiment **deleted a capability**;
this one **acts on evidence it already had**. The robot still reverses when it
genuinely cannot rotate.

### A constant that turned out to be inert

`PIVOT_CM` was 14 cm, and lowering it to 5 changed **nothing** — every metric
byte-identical across twelve 120-second rooms. The reason: the robot brakes at
`STOP_CM` (20 cm) and stops within a centimetre or two, so a sonar-only trigger
leaves `raw` at about 18–20 cm. It never reaches 14, so the sonar half of the
`boxed` test never fired and the IR half decided everything.

Worth remembering when tuning: a threshold downstream of a *harder* threshold
can be unreachable. Measure whether a knob is connected before turning it.

## 13.5 Choosing a side without a servo

`SCAN` uses the chassis as the gimbal:

1. pivot left `SCAN_MS`, stop, settle `SETTLE_MS`, median of three at the full
   timeout;
2. pivot right `2 × SCAN_MS`, stop, settle, measure again;
3. score each side and turn toward the winner.

Two details matter:

- **The two turns are not symmetric.** The robot finishes the scan facing
  `SCAN_MS` worth to the right of where it started, so turning left needs
  `TURN_MS + SCAN_MS` and turning right needs `TURN_MS − SCAN_MS`.
- **No echo scores as blocked, not as open.** The robot is already stationary
  and already in trouble, so the flush-wall hypothesis is live. If both sides
  score equal, the tie-break alternates, which is what stops a symmetric corner
  becoming a metronome.

The median of three is worth its ~110 ms here and nowhere else: the robot is
stopped, so the latency is time it was not using anyway. Inside the control
loop the same median would be pure delay, which is why the moving robot pings
once per tick and relies on the *asymmetry* in §13.6 instead of averaging.

## 13.6 Fast to stop, slow to go

One reading below `STOP_CM` brakes immediately. Returning to full speed needs
`CLEAR_RUN` consecutive readings above `CLEAR_CM`.

A false brake costs a second. A false clear costs a collision. Filtering
symmetrically — a median, say — trades away detection latency to suppress
spikes that were harmless in the first place.

## 13.7 Failure taxonomy

| Failure | Cause | Mitigation in code | Residual |
|---|---|---|---|
| Drives into an angled wall | echo reflects away, reads `None` | `BLIND` state: slow down, watch IR, time out into a scan | real; slower is the only lever |
| Clips a chair leg | narrow object outside the cone and between the IR lobes | IR pair, low speed | real |
| **Sideswipes a wall** | driving nearly parallel; nothing looks sideways | none possible | **every collision left in simulation** |
| Reverses into something | no rear sensor | reverse credit (§13.4) | bounded, not eliminated |
| Ping-pongs in a corner | symmetric geometry | stuck detector → escape, alternating direction | mostly handled |
| Runs on with the motors powered | control loop stalls | `Drive.tick()` deadman, 300 ms TTL | a *dead* loop needs `estop()` in `finally:` |
| Drives with a dead sensor | module unplugged, echo stuck | pre-flight refuses to start | — |
| Drives with the switch off | 5 V rail down, silent no-op | pre-flight reads the battery divider | — |

## 13.7a The livelock, and why there is a `STUCK` state

The first run on real hardware found something 50 simulated rooms never
produced: **both IR detectors asserted permanently**. `danger()` was therefore
always true, so the robot could never cruise, could never earn reverse credit,
and ping-ponged `TURN` → `ESCAPE` → `TURN` at about 1 Hz — **33 escapes in
31 seconds**, forever, with no terminal state.

Three fixes came out of it:

1. **Pre-flight rejects it.** Both detectors asserted before the robot has
   moved is not an obstacle, it is a miscalibration, and no manoeuvre escapes
   it. `preflight()` now returns `BOTH IR STUCK ON`.
2. **A `STUCK` state.** Four escapes with no forward progress in between and
   the robot stops, says why, and waits for a sustained 3 s all-clear. Being
   trapped by geometry is recoverable; being trapped by a sensor telling you
   something untrue is not.
3. **Credit consistency.** The escalation from a blocked `TURN` was reversing
   without checking the credit that every other path respects.

The general lesson: a reactive state machine needs a state for *"none of my
manoeuvres are working"*. Without one, a stuck input turns a recovery
behaviour into an infinite loop, and infinite loops on a robot with wheels are
not harmless.

The same run also showed the heap sliding from 214 KB to **11.8 KB** between
collections. It recovered — no leak — but a GC pause is latency, so the app
now collects while it is stopped instead.

## 13.7b Degraded modes beat bypasses

With the IR pots uncalibrated the choice looked binary: ignore the pre-flight
check, or do not run. Neither is right. The app takes an injected global
instead:

```zsh
PG_SET='PG_NO_IR=1' ./pg dry avoider 60
```

`PG_SET` passes arbitrary globals through `pg run` and `pg dry`. In this mode
the IR pair is genuinely disabled rather than overridden: `Nav` stops reading
the pins, pre-flight skips its check, the app prints a warning, the panel says
`IR PAIR OFF - sonar only`, and telemetry carries `"ir":0`.

The robot then has one forward beam and **nothing watching its shoulders**, so
§13.7's sideswipe and close-angled-wall rows lose their only backstop. That is
acceptable for bring-up on a bench and unacceptable for leaving it running.

The general shape: when a sensor cannot be trusted, model its absence
explicitly and make the degradation visible in every output. A flag that
silences a safety check without changing the behaviour underneath is a lie the
robot will tell you again later.

## 13.8 Tuning on real hardware

None of the constants have been measured on the chassis. In order:

0. **Trim the IR pots.** LM393 is open-collector with external pull-ups, so
   idle is HIGH and LOW is the comparator sinking — the polarity needs no
   experiment. On this board both pins sit LOW in open space with the rail up,
   which means both pots are too sensitive. The green front LEDs mirror the
   outputs; turn each pot until its LED just goes out, then confirm with
   `./pg run ir_check 45`. Nothing downstream is testable until this is done.
1. **`./pg run sonar_check 30`** — point at a flat wall 30–60 cm away. If the
   answer rate at the short timeout is not near 100 %, raise `PING_US` before
   touching anything else. *(Done: 100 %, 3.0 ms, σ 0.09 cm.)*
2. **Find the real speed.** Wheels down, a metre of tape, `./pg run drive_check`
   modified to hold one duty for 3 s, and a stopwatch. There are no encoders —
   this is the only way. Repeat on a fresh pack and a tired one; the difference
   is large.
3. **Find the real stopping distance.** From that speed, brake and measure the
   overshoot. If it exceeds a third of `STOP_CM`, lower `CRUISE`.
4. **Time the turns.** `SCAN_MS` should be about a quarter turn and `TURN_MS`
   somewhere near a half. They will drift with battery voltage and there is
   nothing to be done about it.
5. Only then adjust thresholds.

Do steps 2–4 with the wheels on the ground and a hand on `./pg stop`.

## 13.9 If you want it to stop sideswiping

The TLC2543 line-sensor ADC has **six unused inputs** — A5 through A10, wired,
idle, and already driven by PIO on SM1. `01_sensorous` reads them and confirms
they float. Two analog IR distance sensors (a Sharp GP2Y0A21 or similar) on A5
and A6, aimed left and right, would cost **no GPIO at all** and would close the
one gap this design cannot reason its way around.

That is the highest-value addition to this platform after wheel encoders. See
`docs/09-extending-the-platform.md`.
