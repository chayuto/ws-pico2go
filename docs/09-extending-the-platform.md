# 09 — Extending the Platform

## 9.1 What the Pico2Go is missing

| Gap | Why it matters | Difficulty to add |
|---|---|---|
| **Wheel encoders** | No odometry, no closed-loop speed, robot drifts | 🟡 medium (needs 2–4 GPIO) |
| **IMU** | No heading, no tilt, no gyro-corrected turns | 🟢 easy (I²C — if you free the pins) |
| **Wi-Fi** | No web UI, no OTA, no telemetry to a laptop | 🟡 medium (module swap) |
| **Camera** | No vision | 🔴 hard (RP2350 is the wrong host) |
| **Bumpers / cliff sensors** | Falls off tables | 🟢 easy (2 GPIO) |
| **Current sensing** | No stall detection | 🟡 medium |
| **Free GPIO** | All 26 are used | — |

**The encoder gap is the important one.** Everything people expect from a "self-driving"
robot — drive 30 cm, turn exactly 90°, hold a straight line, match wheel speeds — needs
rotation feedback. Without it, `forward(50)` means "apply 50 % duty and hope".

---

## 9.2 Freeing up GPIO

Since nothing is spare, adding hardware means trading something away. In order of what
costs you least:

| Free up | Pins | What you lose | Verdict |
|---|---|---|---|
| **LCD** (`DC/CS/CLK/DIN/RST/BL`) | GP8–GP13 → **6 pins** | On-robot display | 🟢 Best trade. Move status to Bluetooth/Wi-Fi telemetry and you gain SPI1 plus 4 GPIO. |
| **Bluetooth** (`GP0/GP1`) | 2 pins | JDY-32 link | 🟢 Good if you replace it with something better on the same UART |
| **Ultrasonic** (`GP14/GP15`) | 2 pins | Ranging | 🟡 Swap for an I²C ToF sensor (VL53L0X/L1X) — better data on fewer pins |
| **RGB LEDs** (`GP22`) | 1 pin | Bling | 🟡 Cheap to give up, but only one pin |
| **IR receiver** (`GP5`) | 1 pin | IR remote | 🟡 Fine if you control over Bluetooth |
| **IR obstacle** (`GP2/GP3`) | 2 pins | Bump detection | 🔴 Keep it — it's your only close-range safety net |
| **Line array** (`GP6/GP7/GP27/GP28`) | 4 pins | Line following | 🔴 It's the headline feature |
| **Motors** (`GP16–GP21`) | 6 pins | Everything | 🔴 No |

> **Best single move:** drop the LCD, add an **I²C bus on GP8/GP9** (that's `WIRE0` in
> `arduino-pico` terms), and hang an IMU, a ToF sensor and an I²C GPIO expander off it.
> You get back more I/O than you gave up.

---

## 9.3 Adding encoders

The N20 motors in the kit are plain 2-wire — no encoder. Options:

1. **Buy N20 motors with built-in magnetic encoders** (6-wire: M+, M−, VCC, GND, C1,
   C2). Same 12 mm × 10 mm × 26 mm body and same mounting, so they drop straight into
   the chassis clips. This is the clean answer.
2. **Optical wheel encoders** — slotted disc + IR interrupter on each wheel. Cheaper,
   uglier, lower resolution.

Wiring: 4 GPIO for full quadrature on both wheels (2 if you accept single-channel and
give up direction sensing — acceptable when you already command direction).

**Read them with PIO.** RP2350 has 12 state machines and the chassis uses 2. A
quadrature decoder is a classic 4-instruction PIO program, it costs zero CPU, and it
never misses a transition the way an IRQ handler does under load. Then:

```
encoder counts ──► PI velocity loop per wheel ──► existing setMotor()
```

That single addition upgrades the platform from "toy" to "actually controllable":
straight-line driving, repeatable turns, distance commands, and stall detection.

---

## 9.4 Using what the RP2350 gave you

The upgrade from RP2040 to RP2350 handed you three resources that **no shipped demo
touches**:

### Core 1 — completely idle
```python
import _thread
_thread.start_new_thread(display_task, ())   # LCD blit + telemetry
# core 0 keeps the control loop at a fixed rate
```
The 52 ms LCD blit and the 67 ms IR decode both belong on core 1. Move them and your
control loop gets an order of magnitude more consistent.

### PIO — 10 of 12 state machines free
Good candidates, in order of payoff:
1. **Ultrasonic ping/echo timing** — removes the blocking spin *and* the hang risk.
2. **Quadrature encoder decode** (see above).
3. **ST7789 driving** with DMA feed (jblanked's C driver already has an
   `st7789_lcd.pio`).
4. **NEC IR decode** — a well-known PIO program; frees you from polling GP5.

### RISC-V
Rebuild the same C project with the `RISCV.13.3` toolchain and the identical robot runs
on Hazard3 cores. As a teaching artefact — same board, same peripherals, two ISAs —
this is genuinely rare and worth doing at least once.

---

## 9.5 Wireless upgrade paths

| Option | Effort | What you get |
|---|---|---|
| Keep JDY-32, write your own app | 🟢 low | Full control of the protocol, cross-platform |
| Replace JDY-32 with an **ESP32-C3 / ESP-01** on GP0/GP1 | 🟡 medium | Wi-Fi, a web UI, OTA, MQTT telemetry — at the cost of a serial bridge |
| Swap the **RP2350-Plus for a Pico 2 W** | 🟡 medium | On-board Wi-Fi + BLE, no radio module needed. **Check the pinout matches** — Pico 2 W is Pico-2-compatible, so it should drop in; verify the LED pin (`GP25` on RP2350-Plus is `WL_GPIO0` on W boards) and that the 5 V rail feeds it correctly before committing. |
| Add an **nRF24L01** or **LoRa** module | 🟡 medium | Long-range or multi-robot links |

> The Pico 2 W swap is the most interesting: you'd get Wi-Fi *and* proper BLE from the
> CYW43 and could free GP0/GP1 entirely by removing the JDY-32. Treat it as a project,
> not a five-minute change — verify pin compatibility on your own hardware first.

---

## 9.6 A project ladder

Roughly in increasing order of difficulty. Each builds on the last.

**Level 1 — get comfortable**
1. Run every shipped demo; write down what each actually does.
2. Trim the IR pots; measure the line-sensor ranges over white / black / air.
3. Verify the battery multiplier against a DMM.
4. Write a "system check" `main.py`: LCD splash, battery %, sensor sweep, RGB confirm.

**Level 2 — fix the shipped code**
5. Non-blocking ultrasonic with a timeout.
6. Deadman timer on the Bluetooth link; remove the `eval()`.
7. Move the LCD blit to core 1.
8. Retune the line-follower PD, with a settable base speed.
9. Refactor the demos into one state machine (`IDLE → LINE → AVOID → FOLLOW`), selected
   by IR remote or Bluetooth.

**Level 3 — new capability**
10. PIO quadrature encoders + per-wheel PI velocity control.
11. `drive(distance_cm)` and `turn(degrees)` primitives.
12. Bluetooth telemetry stream (position, speed, sensors) into a laptop plot.
13. Replace the ultrasonic with a VL53L1X ToF over I²C.
14. Add an IMU; fuse gyro heading with encoder odometry.

**Level 4 — real robotics**
15. Occupancy-grid mapping of a small arena from ToF + odometry.
16. Wall following with a proper PID and a state machine.
17. Multi-robot coordination over nRF24/ESP-NOW.
18. Micro-ROS or a small MQTT bridge, so the robot is a node in a larger system.
19. A neural policy for line following trained in sim, exported to fixed point, running
     on core 1 — the M33's DSP extensions make this plausible.

---

## 9.7 Realistic expectations

**What this platform is genuinely good at:**
- Teaching embedded C / MicroPython on real hardware with real sensors.
- Demonstrating PIO — it's one of the few cheap robots where PIO is *load-bearing*.
- Line following and reactive obstacle avoidance out of the box.
- An Arm-vs-RISC-V comparison on identical hardware.

**What it is not:**
- A mapping or navigation platform (no odometry, no vision).
- A ROS robot (no Linux, no camera, no LiDAR).
- Precise (no encoders; open-loop everything).
- Long-running (two 14500 cells, four RGB LEDs and two motors — expect well under
  an hour of continuous driving).

Sized correctly, it's a very good ~$51 teaching robot with an unusually capable MCU and
an unusually honest schematic. Sized as a research platform, it will disappoint.
