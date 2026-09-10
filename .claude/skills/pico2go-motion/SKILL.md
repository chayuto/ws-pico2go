---
name: pico2go-motion
description: Driving the Pico2Go/PicoGo robot's two N20 motors through the TB6612FNG - forward, reverse, pivot, arcs, differential drive, speed control, braking, and the safety rules that go with a robot that has no encoders. Use for any movement, drive, turn, speed, steering, motor-wiring or robot-runaway question, and before writing any code that touches GP16-GP21.
---

# Motion

## ⚠ Safety first — read before writing motor code

1. **Wheels off the ground until the behaviour is proven.** Put the robot on a book.
2. **If the user is away or has not confirmed the wheels are clear, do not drive the
   motors at all.** There is no way to catch it remotely.
3. Motors need the **chassis power switch ON** — the TB6612's `VM` is the
   battery-derived 5 V rail, not USB. Switch off ⇒ silent no-op, not an error.
4. End every app with `board.estop()` in a `finally:`. `./pg run` also traps exit.
5. `./pg stop` is the emergency stop and works from any terminal at any time.

## Pins (channel A = LEFT, channel B = RIGHT)

| Signal | GPIO | |
|---|---|---|
| `PWMA` | 16 | left speed |
| `AIN1` / `AIN2` | 18 / 17 | left direction |
| `BIN1` / `BIN2` | 19 / 20 | right direction |
| `PWMB` | 21 | right speed |
| `STBY` | — | hard-tied; you cannot software-disable the bridge |

Direction truth: `xIN2=1, xIN1=0` → forward · `0,1` → reverse · `0,0` → coast.
PWM 1 kHz, duty = `speed * 0xFFFF // 100`.

## API — `shared/lib/Motor.py`, class `PicoGo`

| Call | Effect |
|---|---|
| `forward(s)` / `backward(s)` | both wheels, `s` = 0–100 **percent duty** |
| `left(s)` / `right(s)` | **pivot in place**, not an arc |
| `stop()` | PWM 0 + direction pins low = **coast**, robot rolls on |
| `setMotor(l, r)` | signed −100…+100 per wheel — **use this one** |

Arcs need `setMotor` with two different positive values, e.g. `setMotor(50, 25)`.

There is **no brake method**. TB6612 brake is both direction inputs HIGH with PWM high;
add it yourself if you need it.

## There are no encoders

This is the platform's defining limitation.

- `forward(50)` is a **duty cycle, not a speed**. Actual speed varies with battery
  voltage, surface and load.
- The robot **veers** — two N20 motors are never identical and there is no feedback to
  correct it. Only a hand-tuned per-wheel trim constant helps:
  ```python
  TRIM_L, TRIM_R = 1.00, 0.94     # measure on your own robot
  M.setMotor(int(v * TRIM_L), int(v * TRIM_R))
  ```
- **No odometry.** `drive(30cm)` and `turn(90°)` are not implementable open-loop with
  any reliability. Timed approximations drift badly as the battery sags.
- Battery voltage sags 100–300 mV under motor inrush — take battery readings with the
  motors stopped.

To fix this properly: swap in 6-wire N20 motors with magnetic encoders and decode them
with **PIO** (10 of 12 state machines are free). That upgrades the platform from
open-loop to genuinely controllable.

## Minimal safe test pattern

```python
import utime, board
from Motor import PicoGo
M = PicoGo()
try:
    M.setMotor(40, 40); utime.sleep_ms(600); M.stop(); utime.sleep_ms(400)
finally:
    board.estop()
```

`projects/drive_check.py` is the reference: short bounded bursts, `stop()` between each,
`estop()` in `finally`, and a 3-second warning before it starts.
