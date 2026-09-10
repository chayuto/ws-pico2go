# 08 — Gotchas & Known Issues

Ordered roughly by how likely each is to cost you an hour.

---

## 🔴 Blockers

### 0a. A brand-new board is running factory test firmware, and it makes noise
An RP2350-Plus straight out of the box runs Waveshare's **`RP2350_Plus_Test` v0.1**
(SDK 2.2.0, built Dec 2025), not MicroPython. It streams a continuous GPIO continuity
report over USB serial **and toggles pins — including GP4, so the buzzer sounds.**
`mpremote` fails with `could not enter raw repl`.

> **Fix:** `./pg bootsel && ./pg flash`. Back it up first with
> `picotool save -a` — there is no download for it anywhere. This repo keeps a copy in
> `ref/factory/` along with a capture of its output. **[observed]**

### 0b. macOS enumerates the board but creates no `/dev/cu` node
After flashing, the board re-enumerates from BOOTSEL (mass storage) straight into
MicroPython (composite CDC) and macOS sometimes fails to attach its CDC driver. USB
shows `idVendor 11914 (0x2E8A)`, `idProduct 5`, `"Board in FS mode"` — but no serial
port.

> **Fix:** unplug and replug. Be patient: the node took **well over a minute** to appear
> in one observed case, so poll rather than concluding failure. Check the real state with
> `ioreg -c IOSerialBSDClient -r -l | grep IOCalloutDevice` — it shows the node name
> before `/dev` catches up. `./pg doctor` detects this state explicitly. **[observed]**

### 0c. The ADC reads garbage on the first run after a flash
Immediately after flashing and rebooting, **every** ADC channel can return nonsense —
observed: battery pinned at full scale (6.60 V) and die temperature at −82.5 °C. The
second run gave correct, stable, repeatable values, and a controlled ordering experiment
showed no mux or settling artifact in the code.

> **Fix:** re-run before diagnosing an analog fault. **[observed]**

### 1. Nothing moves on USB power alone
The motors, WS2812 LEDs and IR obstacle sensors all hang off the **5 V rail, which is
generated from the batteries via the IP5306**. USB only supplies 3V3 for the MCU.

> **Fix:** insert charged cells and slide the chassis power switch to **ON** — even
> when the robot is tethered by USB. Charge-while-run is supported.

See [03 — Power & Battery](03-power-and-battery.md).

### 2. Robot won't power on after a battery change
The protection IC latches off. Waveshare: *"After reinstalling the batteries, you need
to connect the power to Picogo to activate the batteries… otherwise the Picogo cannot
be powered normally."*

> **Fix:** plug USB in once (or flip the switch) to wake the pack.

### 3. `ImportError: no module named 'Motor'`
Running a demo in Thonny executes it on the device, but its `import` statements resolve
against the **device filesystem**, which starts empty.

> **Fix:** upload `Motor.py`, `ws2812.py`, `ST7789.py` and `TRSensor.py` to the Pico
> before running anything else.

### 4. Demo works tethered, does nothing standalone
MicroPython only autoruns **`main.py`**.

> **Fix:** save the demo on the device *as* `main.py`.

### 5. You downloaded the wrong demo package
V1 (pre-Sept 2022) boards use an **ADS1015** line-sensor ADC; V2 boards use a
**TLC2543**. The `TRSensor.py` implementations are mutually incompatible and fail
silently — you get plausible-looking numbers that mean nothing.

> **Fix:** a Pico2Go bought today is **V2**. Use `PicoGo_Code_V2.zip`.

### 6. You flashed the RP2040 UF2
The V2 zip contains **both** `RPI_PICO-*.uf2` (RP2040) and `RPI_PICO2-*.uf2` (RP2350).

> **Fix:** the RP2350-Plus needs **`RPI_PICO2-*.uf2`**.

### 7. The kit's USB cable doesn't fit the controller
The package still lists a **USB-A → micro-B** cable, a holdover from the Pico-based
PicoGo. The RP2350-Plus has **USB-C**.

> **Fix:** supply your own USB-C **data** cable (charge-only cables enumerate nothing).

---

## 🟠 Silent misbehaviour

### 8. Ultrasonic ranging can hang forever
`dist()` spins in `while Echo.value() == 0: pass` with no timeout. No echo (out of
range, angled wall, soft surface) → the loop never exits, the robot freezes mid-motion
with the motors still driven. This is the most common "my Pico2Go locked up" cause.

> **Fix:** add a timeout — code in [06 §6.4](06-sensors-and-algorithms.md).

### 9. `sleep_ms(10)` instead of `sleep_us(10)` in the follow demo
`Ultrasionc-Infrared-follow.py` sends a **10 ms** trigger pulse instead of 10 µs — a
1000× error that happens not to break most modules. Fix it anyway.

### 10. Line follower drives off the track
Almost always calibration, occasionally polarity.

- The calibration sweep must start with the **centre sensor on the line**, on the
  **actual surface**, under the **actual lighting**.
- Track spec is **15 mm black tape on white**. A dark background degrades tracking.
- Then check the sensor-polarity question in
  [06 §6.2](06-sensors-and-algorithms.md) — the vendor docs contradict themselves about
  whether high values mean black or white, and if your board reads high-on-white you
  need `readLine(white_line=1)`.

### 11. IR obstacle LEDs stuck on or stuck off
The comparator threshold is set by **two trim pots on the underside**, and they ship
untrimmed.

> **Fix:** power up with nothing in front of the robot and turn each pot until its
> green front LED *just* goes out. No code needed.

### 12. Bluetooth connects but sends garbage
Baud mismatch. JDY-32/33 default to **9600**; Waveshare's `bluetooth.py` opens
**115200**.

> **Fix:** try both. Confirm/set with `AT+BAUD`.

### 13. Bluetooth pairing fails
Two devices advertise. **`JDY-33-SPP` works; `JDY-33-BLE` will not connect** with the
vendor app. **[vendor]**

### 14. LCD colours are wrong
The driver's own constants aren't standard RGB565 (`GREEN = 0x001F`, which is blue).
Don't reason from the constants — display a test pattern and pick values empirically.

### 15. Battery percentage looks wrong
Two separate issues: the divider multiplier (Waveshare's MicroPython says **×2**, a
third-party C driver says **×3.0** — the schematic's 100 K/100 K pair supports ×2), and
the fact that percentage is a naive linear voltage map. Also: **the sense divider is
gated by the 5 V rail**, so voltage reads meaningless with the switch off.

> **Fix:** verify against a DMM once, hardcode what you measured, and take readings
> with the motors stopped. [03 §3.4](03-power-and-battery.md).

### 16. Robot runs away when the phone disconnects
The Bluetooth protocol is press-and-hold with **no deadman timer**. Drop the link
mid-press and it keeps driving.

> **Fix:** add a 500 ms command timeout — code in [07 §7.2](07-remote-control.md).

### 17. `eval()` on the RGB command
`bluetooth.py` does `rgb = tuple(eval(cmd))` on data received over Bluetooth. That is
arbitrary code execution by anything that pairs with the robot. Harmless on your desk,
not harmless in a classroom or at a demo table.

---

## 🟡 Platform-level things to know

### 18. There are no wheel encoders
Nothing on the board measures wheel rotation. Consequences:

- `forward(50)` is **not** a speed — it's a duty cycle. Actual speed varies with
  battery voltage, surface, and load.
- The robot **drifts**: the two N20 motors are never identical, so "straight" curves.
  There is no way to correct this in closed loop; you can only add a hand-tuned
  per-wheel trim constant.
- **No odometry, no dead reckoning, no "drive 30 cm".**

This is the single biggest capability gap. See
[09 — Extending the Platform](09-extending-the-platform.md).

### 19. Zero free GPIO
All 26 user pins are committed. Any addition requires removing something. See
[02 §2.4](02-pinout-reference.md).

### 20. RP2350 erratum E9
The RP2350's E9 erratum (a leakage-current problem on GPIOs configured as inputs when
the pad sits between logic levels — up to ~120 µA, too much for the internal pull-up)
is worth knowing about on this board, because two of its inputs can float:

- **TLC2543 `DOUT` on GP27** goes high-Z whenever `CS` is deasserted, and it's sampled
  by **PIO** — for which the "disable the input buffer between reads" software
  workaround is *not* available.
- The **ultrasonic `Echo`** line, if the module is unplugged.

**Settled for this board:** `picotool info -a` reports **`revision: A4`**, QFN60. The
E9 fix landed in silicon at A3/A4, so **this concern does not apply here** — no external
pull-downs needed, and the PIO line-sensor read is safe. Worth re-checking on any board
you didn't buy recently; the erratum's external fix is a pull-down of **≤ 8.2 kΩ**.
**[measured]**

### 21. Every demo is single-core and blocking
Core 1 is completely idle in all shipped code. The LCD blit (~52 ms), the IR decode
(~67 ms) and the ultrasonic ping all stall the control loop. This is the main reason
the demos feel sluggish, and the main opportunity for improvement.

### 22. The vendor toolchain recommendations are stale
Thonny **3.3.3** is from 2021 and predates RP2350; the Android app is a 2021
`com.example.myapplication` build with pre-Android-12 Bluetooth permissions. Both
still work, neither is what you'd choose today.

### 22b. The setup guide looks like it needs Windows — it doesn't
Every toolchain instruction Waveshare publishes is Windows-only: a Windows Thonny
installer, a Google-Drive `.vsix` bundle, `C:\Users\<name>\.pico-sdk`,
`%LOCALAPPDATA%\Arduino15`. There are **no vendor drivers and no Windows-only tools**
in this stack — the board is USB mass storage in bootloader mode and USB CDC serial
afterwards, both native on macOS and Linux.

> **macOS:** see [11 — macOS Setup](11-macos-setup.md). Two Mac-specific traps worth
> knowing up front: **don't drag the `.uf2` in Finder** (use `picotool load -x` or
> `cp -X`), and **use `/dev/cu.*`, never `/dev/tty.*`**, for the serial port.

### 23. Waveshare publishes no pinout for this board
Not on the Pico2Go wiki, not on the PicoGo wiki, not on the product page. The only
sources are the schematic PDF and the demo source. That's why
[02 — Pinout Reference](02-pinout-reference.md) exists.

### 24. Filenames contain typos
`Ultrasionc-*` (three files), `Infrared_obstacle_Avoidance.py` (lowercase `o`),
`Ultrasonic_Obstacle_Avoidance.py` vs. the wiki's `Ultrasionc-Obstacle-Avoidance.py`.
Copy exactly.

### 25. No assembly instructions
The kit ships unassembled and the wiki has no build guide. Work from the product
photos and PicoGo assembly videos. ~20–30 minutes.
