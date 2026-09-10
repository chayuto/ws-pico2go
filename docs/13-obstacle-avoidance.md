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
| ping, echo returned | ~3.5 ms at 60 cm | 0.1 cm |
| ping, timed out at `PING_US` | 12 ms | 0.3 cm |
| LCD blit, on render ticks only | 78 ms | 2.0 cm |
| brake to a stop | measured in simulation at ~1.0 cm | 1.0 cm |

Worst case — a timed-out ping on a render tick — is about **4.4 cm**. Coasting
instead of braking nearly doubles the last term.

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

## 13.8 Tuning on real hardware

None of the constants have been measured on the chassis. In order:

1. **`./pg run sonar_check 30`** — point at a flat wall 30–60 cm away. If the
   answer rate at the short timeout is not near 100 %, raise `PING_US` before
   touching anything else; everything downstream assumes the beam usually
   answers.
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
