---
name: pico2go-line-following
description: The Pico2Go/PicoGo 5-channel line-tracking array (TLC2543 read over PIO) and the PID line-follower - reading raw values, calibration, the white_line polarity question, tuning Kp/Kd, and debugging a robot that leaves the track. Use for line following, line tracking, TRSensor, TLC2543, readLine, calibrate, track building, or any "robot drives off the line" problem.
---

# Line following

## Hardware

5 × ITR20001/T reflective sensors → **TLC2543** (12-bit, 11-channel serial ADC),
channels **A0..A4 = IR1..IR5, left → right**. Driven by a **PIO** state machine (SM1),
not hardware SPI, because the pins don't map onto SPI0/SPI1.

| Signal | GPIO | TLC2543 pin |
|---|---|---|
| I/O CLOCK | 6 | 18 |
| DATA INPUT (address) | 7 | 17 |
| DATA OUT | 27 | 16 |
| CS (active low) | 28 | 15 |

**Verified on hardware:** A0–A4 carry signal; A5–A10 show a decaying floating ramp
(859→564), confirming only five inputs are connected.

## The pipelining gotcha

The TLC2543 returns the **previous** conversion. To read N channels you do N+1 transfers
and discard the first — which is exactly what the vendor's `value[1:]` slice does.

**Verified:** two back-to-back reads of A0 returned `508` then `959`. The first is
residue from the prior channel; the second is real. Never trust a single transfer.

Values are shifted `>>2` from 12-bit to **0–1023**.

## API — `shared/lib/TRSensor.py`

| Call | Returns |
|---|---|
| `AnalogRead()` | 5 raw values 0–1023 |
| `calibrate()` | reads 10× and narrows stored per-channel min/max |
| `readCalibrated()` | 5 values normalised 0–1000 |
| `readLine(white_line=0)` | `(position 0–4000, values)` weighted centroid |

## ⚠ Unresolved: sensor polarity

Waveshare's docs contradict themselves and **this has not yet been settled on hardware**:

- The wiki: *"600~900 on white paper, 0~50 in the air"* ⇒ **high = white**.
- The driver docstring (inherited from Pololu QTR): *"higher values = lower
  reflectance"*, and `readLine`'s default *"assumes a dark line (high values)"* ⇒
  **high = black**.

If the wiki is right, `readLine(white_line=0)` centroids the **white background**, the
feedback sign inverts, and the PD loop diverges instead of converging.

**Settle it before tuning anything.** Run `./pg run validate` (uses the IR remote to
label surfaces) or manually:

```sh
./pg run sensors 60     # then hold over white, over black tape, then in the air
```

| Result | Action |
|---|---|
| black > white | driver is right — `readLine()` as shipped |
| white > black | **use `readLine(white_line=1)`** in `Line-Tracking*.py`, and re-check the `sum(...) > 4000` bail-out, which now triggers under opposite conditions |

Readings pinned near ~950 on **all** channels and unchanging across surfaces mean the
emitters are dark or the array is nowhere near a surface — not a polarity answer.

## Calibration

```python
for i in range(100):
    M.setMotor(30, -30) if (i < 25 or i >= 75) else M.setMotor(-30, 30)
    TRS.calibrate()
```

Sweeps right → left → right, ending centred; 1000 samples total.

- **Start with the centre sensor on the line.**
- Calibrate on the **actual surface** under the **actual lighting** — ambient IR from
  sunlight or halogen shifts everything.
- Waveshare: *"operation error in the calibration phase will directly affect the
  tracking effect."* This dominates behaviour.

## Control loop

```python
proportional = position - 2000
derivative   = proportional - last_proportional
power_difference = proportional/30 + derivative*2     # Kp≈0.033, Kd=2, Ki=0
power_difference = clamp(power_difference, -maximum, maximum)
if power_difference < 0: M.setMotor(maximum + power_difference, maximum)
else:                    M.setMotor(maximum, maximum - power_difference)
```

It is a **PD** controller — `integral` is computed and never used. `maximum` is pinned
at **100**, which is aggressive.

**The D:P ratio is ~60:1**, so behaviour is almost entirely derivative-driven. And
`derivative` is a raw per-iteration difference with no loop-time normalisation, so its
effective gain drifts with however long `readLine()` takes.

### Tuning order that works

1. `maximum = 50`, `Kd = 0`. Raise `Kp` until it oscillates, back off ~30 %.
2. Add `Kd` until oscillation damps.
3. Raise `maximum` last.
4. Leave `Ki = 0` — on a line follower it mostly integrates calibration error.

## Track

**15 mm matte black tape on white KT board.** A dark background degrades tracking.
Contrast under ~100 counts between white and black ⇒ unreliable, change the surface.

## Debug checklist

| Symptom | Cause |
|---|---|
| All channels ~950, static | emitters dark, or array far off the surface |
| All zero | TLC2543 not responding — **V1 board?** (V1 uses an ADS1015 on I²C) |
| Values fine, robot leaves the line | polarity (`white_line`), or bad calibration |
| Wobbles violently | `maximum=100` too aggressive; drop to 60–70 |
| Stops randomly | `sum(sensors) > 4000` bail-out firing |
