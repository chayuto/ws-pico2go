# 05 — The Official Demo Package

Download: **`PicoGo_Code_V2.zip`** →
`https://files.waveshare.com/wiki/PicoGo/PicoGo_Code_V2.zip`

Contents (14 Python files + 2 UF2 firmware images):

| File | Type | Depends on | Autorun as `main.py`? |
|---|---|---|---|
| `Motor.py` | **library** + self-test | — | no |
| `ws2812.py` | **library** + self-test | — | no |
| `ST7789.py` | **library** + self-test | — | no |
| `TRSensor.py` | **library** + self-test | — | no |
| `Ultrasonic_Ranging.py` | demo | — | no (prints to shell) |
| `Battery_Voltage.py` | demo | `ST7789` | optional |
| `IRremote.py` | demo | `Motor` | **yes** |
| `Infrared_obstacle_Avoidance.py` | demo | `Motor` | **yes** |
| `Ultrasonic_Obstacle_Avoidance.py` | demo | `Motor` | **yes** |
| `Ultrasionc-Infrared-Obstacle-Avoidance.py` | demo | `Motor` | **yes** |
| `Ultrasionc-Infrared-follow.py` | demo | `Motor`, `ws2812`, `ST7789` | **yes** |
| `Line-Tracking.py` | demo | `Motor`, `TRSensor` | **yes** |
| `Line-Tracking2.py` | demo | `Motor`, `TRSensor`, `ws2812` | **yes** |
| `bluetooth.py` | demo | `Motor`, `ws2812`, `ST7789` | **yes** |
| `uf2/RPI_PICO2-*.uf2` | firmware | — | flash this one |
| `uf2/RPI_PICO-*.uf2` | firmware | — | ❌ RP2040 only, wrong board |

> Note the typos in the shipped filenames — `Ultrasionc`, not `Ultrasonic`, in three of
> them. Reproduce them exactly in `import` statements or shell commands.

**Before running anything:** upload the four library files to the device, and turn the
**power switch ON**.

---

## The libraries

### `Motor.py` — class `PicoGo`

The core API everything else is built on.

| Method | Behaviour |
|---|---|
| `forward(speed)` | Both wheels forward. `speed` = **0–100 %** |
| `backward(speed)` | Both wheels reverse |
| `left(speed)` | **Spin in place** counter-clockwise (left wheel back, right forward) |
| `right(speed)` | **Spin in place** clockwise |
| `stop()` | PWM to 0 and all direction pins low (coast) |
| `setMotor(left, right)` | Independent, **signed** −100…+100 per wheel. The one you actually want. |

PWM frequency is 1 kHz; duty is `speed * 0xFFFF / 100`.

Self-test (`__main__`): forward → backward → left → right, 0.5 s each, then stop.

> ⚠️ `left()` and `right()` are **pivot turns**, not arcs. For arcs use
> `setMotor()` with two different positive values.

> ⚠️ `stop()` sets both direction pins low, which is TB6612 **coast/stop**, not
> **brake**. The robot rolls a little. For a hard brake, set both direction inputs
> HIGH (`AIN1=AIN2=1`) with PWM high — the shipped library has no method for it.

### `ws2812.py` — class `NeoPixel`

PIO-driven WS2812B on GP22, 4 LEDs, `brightness` default 0.8.

| Member | Behaviour |
|---|---|
| `pixels_set(i, color)` | Stage one pixel; `color` is an `(r, g, b)` tuple |
| `pixels_fill(color)` | Stage all |
| `pixels_show()` | Push staged buffer to the strip (applies `brightness`) |
| `color_chase(color, wait)` | Light one at a time |
| `wheel(pos)` | 0–255 → RGB colour-wheel tuple |
| `rainbow_cycle(wait)` | Full animated cycle |
| Constants | `BLACK RED YELLOW GREEN CYAN BLUE PURPLE WHITE`, and `COLORS` tuple |

Self-test: fills → chases → endless rainbow.

### `ST7789.py` — class `ST7789(framebuf.FrameBuffer)`

240×135 RGB565 framebuffer (**64,800 bytes** of RAM), SPI1 @ 10 MHz.
Inherits all of MicroPython's `framebuf` drawing: `fill`, `pixel`, `line`, `rect`,
`fill_rect`, `hline`, `vline`, `text`, `scroll`, `blit`.

`show()` blits the whole buffer. Because the panel is a 240×135 window inside the
controller's 240×320 address space, `show()` sets a fixed window at column offset
**40** (`0x28`) and row offset **53** (`0x35`).

> ⚠️ The colour constants in this driver are **not** textbook RGB565 — `GREEN` is
> defined as `0x001F` (which is pure blue in standard RGB565) and `BLUE` as `0xFF00`.
> Byte order between `framebuf` and the panel is doing something non-obvious here.
> Don't reason about colours from the constants; put a test pattern on screen and pick
> values empirically.

> ⚠️ `show()` sends 64,800 bytes per frame. Theory says ~52 ms at 10 MHz; **measured on
> hardware it is 77.8 ms** — an effective ~6.7 MHz once MicroPython's SPI overhead is
> counted. That caps naive full-frame refresh at **~12.9 fps** and stalls any control
> loop sharing the thread (init is 6 ms). The shipped demos work around this by only
> redrawing every 3 seconds and using `fill_rect` to patch small regions. **[measured]**

### `TRSensor.py` — class `TRSensor` (V2)

5-channel line array via the TLC2543 over a PIO SPI state machine. See
[06 — Sensors & Algorithms](06-sensors-and-algorithms.md) for the protocol.

| Method | Behaviour |
|---|---|
| `AnalogRead()` | List of 5 raw values, 0–1023 |
| `calibrate()` | Read 10× and narrow the stored min/max per channel |
| `readCalibrated()` | 5 values normalised to 0–1000 against the calibration |
| `readLine(white_line=0)` | `(position, values)` — `position` 0–4000, weighted centroid |

Self-test: prints `AnalogRead()` every 100 ms. **Run this first** on white paper, on
black tape, and held in the air, and write the three ranges down — see
[06 §6.2](06-sensors-and-algorithms.md).

---

## The demos

### `Ultrasonic_Ranging.py`
Prints distance in cm once a second. No motors involved, so it's the safest first
hardware check.

> Ultrasound reflects specularly. A wall at an angle to the sensor bounces the ping
> away and you get a wrong (usually too-large) reading. Waveshare says as much. **[vendor]**

### `Battery_Voltage.py`
Draws a framed panel on the LCD and updates die temperature, battery volts and a
percentage every second. Percentage is a linear voltage map and is admitted to be
approximate. **A good "is my whole stack alive" smoke test.**

### `IRremote.py`
NEC decode on GP5 → drive commands. Default mapping:

| Key | Action |
|---|---|
| `2` | forward |
| `8` | backward |
| `4` | turn left |
| `6` | turn right |
| `5` | stop |
| `+` / `-` | speed ±10 |
| `EQ` | reset speed to 50 |

Includes a watchdog: after ~800 consecutive polls with no valid frame it calls
`stop()`, so the robot doesn't run away when you put the remote down.

> Key codes differ between remotes. If your remote isn't the one in the box, capture
> your own codes — see [07 §7.1](07-remote-control.md) for the full table and a
> capture recipe.

### `Infrared_obstacle_Avoidance.py`
Reads `DSR`/`DSL`, drives forward at 20 % with no obstacle, turns at 10 % otherwise.

**Trim first**: with the robot powered and nothing in front of it, adjust the two
potentiometers on the underside until the green front LEDs *just* go out — that's
maximum sensitivity without false triggers. **[vendor]**

Behaviour is asymmetric and simple:

| DSL | DSR | Action |
|---|---|---|
| 0 (obstacle) | 0 (obstacle) | left @10 |
| 0 | 1 | right @10 |
| 1 | 0 | left @10 |
| 1 | 1 (clear) | forward @20 |

### `Ultrasonic_Obstacle_Avoidance.py`
Turn right at 20 % when anything is within **20 cm**, else forward at 20 %.

### `Ultrasionc-Infrared-Obstacle-Avoidance.py`
Both sensors OR'd together: turn if `distance ≤ 20 cm` **or** either IR sensor fires;
otherwise forward at 40 %. Waveshare's assessment — *"the combination of ultrasonic and
infrared has a better obstacle avoidance effect and a higher success rate"* — is
correct: ultrasonic misses angled and soft surfaces, IR misses dark and matte ones.
**[vendor]**

### `Ultrasionc-Infrared-follow.py`
Object following. Target distance ≈ **5 cm**.

| Condition | Action |
|---|---|
| `d < 5 cm` | stop |
| left IR only | turn left @20 |
| right IR only | turn right @20 |
| `5 < d < 7 cm`, or both IR see something | forward @30 |
| otherwise | stop |

Also runs the LCD status panel (every 3 s) and an animated RGB rainbow.

> ⚠️ Note the deliberate **dead-band**: forward only between 5 and 7 cm. Outside that,
> stop. It follows a hand held right in front of it; it will not chase anything across
> a room.

### `Line-Tracking.py`
The classic PID line follower.

1. **Calibration dance** — 100 iterations of alternating `setMotor(±30, ∓30)`,
   sweeping the array across the line while `calibrate()` records per-channel min/max.
   The pattern is: right for 25 steps, left for 50, right for 25 (ending centred).
2. **Control loop** — `position = readLine()`, `proportional = position - 2000`,
   `power_difference = proportional/30 + derivative*2` (a **PD** controller; the
   integral term is computed but never used), clamped to ±100, applied differentially
   at `maximum = 100`.
3. Bail-out: if `sum(sensor_values) > 4000` the robot stops.

> **Calibration is everything.** Waveshare: *"The operation error in the calibration
> phase will directly affect the tracking effect."* Place the robot with the centre
> sensor over the line before you start, on the same surface you'll run on. **[vendor]**

Track spec: **15 mm black tape on white KT board.** A dark background degrades it. **[vendor]**

### `Line-Tracking2.py`
`Line-Tracking.py` plus:
- RGB shows red/green/blue/yellow during calibration, rainbow while running.
- IR obstacle sensors: obstacle → stop **and sound the buzzer**; clear → resume.
- All-sensors-saturated → stop silently.

This is the demo to show people. It's also the one whose "lift the robot and the motors
stop" claim depends on your board's sensor polarity — see [06 §6.2](06-sensors-and-algorithms.md).

### `bluetooth.py`
JSON-over-SPP remote control at **115200 baud on UART0**, plus the LCD status panel.
Accepts movement, speed preset, buzzer, LED and RGB commands and echoes a `{"State":…}`
acknowledgement. Full protocol in [07 §7.2](07-remote-control.md).
