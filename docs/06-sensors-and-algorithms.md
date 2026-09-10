# 06 — Sensors & Algorithms

## 6.1 Line array: TLC2543 over PIO

### The part

**TLC2543** — 11-channel, 12-bit successive-approximation ADC with a serial interface.
Only 5 channels are used (`AIN0..AIN4` ← `IR1..IR5`, left to right). Reference is the
3V3 rail. **[schematic]**

### The protocol

The TLC2543 is **pipelined**: the data you clock *out* during a transfer is the result
of the *previous* conversion. So to read N channels you perform N+1 transfers and
discard the first result. Waveshare's driver does exactly this — and it's the single
most confusing line in the whole codebase if you don't know the part:

```python
for j in range(0, self.numSensors + 1):   # 0..5  →  six transfers
    self.CS.value(0)
    self.sm.put(j << 28)                  # send channel address j
    value[j] = self.sm.get() & 0xfff      # result of address j-1
    self.CS.value(1)
    value[j] >>= 2                         # 12-bit → 10-bit (0..1023)
time.sleep_ms(2)
return value[1:]                           # results for channels 0..4
```

> ✅ **Verified on hardware.** Two back-to-back reads of channel A0 returned **`508`
> then `959`** — the first is residue from the previously addressed channel, the second
> is the real A0. Reading all 11 channels shows A0–A4 carrying sensor signal and
> A5–A10 sitting on a decaying floating ramp (859 → 564), confirming that exactly five
> inputs are connected and that the `value[1:]` slice is correct. **[measured]**

### The PIO program

Waveshare implements the serial link as a two-instruction PIO SPI (CPHA=0), not with
the hardware SPI blocks — because the pins (GP6/GP7/GP27/GP28) don't map onto SPI0 or
SPI1:

```python
@rp2.asm_pio(out_shiftdir=0, autopull=True,  pull_thresh=12,
                             autopush=True,  push_thresh=12,
             sideset_init=rp2.PIO.OUT_LOW, out_init=rp2.PIO.OUT_LOW)
def spi_cpha0():
    out(pins, 1)  .side(0x0) [1]     # drive address bit, clock low
    in_(pins, 1)  .side(0x1) [1]     # sample data bit,  clock high
```

- `sideset_base` = GP6 (I/O CLOCK)
- `out_base` = GP7 (address in)
- `in_base` = GP27 (data out)
- CS on GP28 is toggled in Python, not PIO
- Clock: `freq = 4 × 200000` = 800 kHz PIO → **200 kHz** effective SPI (2 instructions
  × 2 cycles each)
- 12-bit thresholds match the TLC2543 word length; `j << 28` puts the 4-bit address in
  the top nibble of the 32-bit word so autopull emits it first.

Runs on **PIO0 state machine 1**.

### V1 boards are completely different

V1 uses an **ADS1015** (I²C, address `0x48`, on I²C1) for three of the channels and
reads the two outer sensors with the MCU's own ADC on GP27/GP28:

```python
value[0] = adc1.read_u16() * 1024 / 0x10000     # GP27, direct ADC
value[1..3] = ADS1015 single-shot channels 1..3  # I²C
value[4] = adc2.read_u16() * 1024 / 0x10000     # GP28, direct ADC
```

(The V1 driver also fires an extra dummy ADS1015 conversion first — same pipelining
idea.) **This is why the wiki says the tracking demos aren't cross-compatible.**

---

## 6.2 ⚠️ Sensor polarity: verify this before you trust the line follower

Waveshare's documentation contains **two statements that cannot both be true**:

1. The wiki: *"The data range is 600~900 when the PicoGo is put on white paper, and
   0~50 when the PicoGo is put in the air."* → **high value = more reflection = white**.
2. The driver docstring, inherited from Pololu's QTR library: *"The values returned are
   a measure of the reflectance… with **higher values corresponding to lower
   reflectance** (e.g. a black surface or a void)."* And `readLine()`'s default
   `white_line=0` explicitly *"assumes a dark line (high values)"*.

If (1) is right on your board, `readLine(white_line=0)` computes the centroid of the
**white background**, not the black line — the feedback sign inverts and the PD loop
diverges instead of converging.

### Settle it in 60 seconds

```python
from TRSensor import TRSensor
import time
t = TRSensor()
while True:
    print(t.AnalogRead())
    time.sleep(0.3)
```

Record three readings:

| Condition | Reading |
|---|---|
| centre sensor over **white** paper | ______ |
| centre sensor over **black** tape | ______ |
| robot held **in the air** | ______ |

**Decision rule:**

- **black > white** → the driver's assumption holds. Use `readLine()` as shipped.
- **white > black** → pass `white_line=1`, i.e. change `TRS.readLine()` to
  `TRS.readLine(1)` in `Line-Tracking.py` / `Line-Tracking2.py`. Also re-check the
  `sum(...) > 4000` bail-out condition, which will now trigger under the opposite
  circumstances.

This takes a minute and saves an evening of "why does it drive off the track".

---

## 6.3 Line-following control loop

```python
position, sensors = TRS.readLine()      # position ∈ [0, 4000]
proportional = position - 2000          # 0 when centred
derivative   = proportional - last_proportional
integral    += proportional             # computed, never used
last_proportional = proportional

power_difference = proportional/30 + derivative*2
power_difference = clamp(power_difference, -maximum, +maximum)   # maximum = 100

if power_difference < 0:
    M.setMotor(maximum + power_difference, maximum)   # slow the LEFT wheel
else:
    M.setMotor(maximum, maximum - power_difference)   # slow the RIGHT wheel
```

- It is a **PD** controller: `Kp = 1/30 ≈ 0.033`, `Kd = 2`, `Ki = 0`.
- Base speed is pinned at **100 %**. This is aggressive; the most useful single tweak
  for a wobbly robot is dropping `maximum` to 60–70.
- `Kd = 2` against `Kp = 0.033` is a **60:1 D:P ratio** — the loop is almost entirely
  derivative-driven, which is why calibration quality dominates behaviour. With no
  encoders and no loop-time control, `derivative` is a raw per-iteration difference,
  so its effective gain drifts with however long `readLine()` happens to take.

### Tuning order that actually works here

1. Fix `maximum` at 50 and set `Kd = 0`. Raise `Kp` until it oscillates, then back off ~30 %.
2. Add `Kd` until the oscillation damps.
3. Raise `maximum` last.
4. Leave `Ki` at zero — on a line follower it mostly integrates calibration error.

### The calibration dance

```python
for i in range(100):
    if i < 25 or i >= 75:  M.setMotor(30, -30)    # pivot right
    else:                  M.setMotor(-30, 30)    # pivot left
    TRS.calibrate()
```

Sweeps right → left → right, ending roughly where it started, taking 10 samples per
iteration (1000 samples total). Start with the **centre sensor on the line**, on the
**actual surface** you'll run on, under the **same lighting**. Ambient IR from sunlight
or halogen lamps will shift the whole calibration.

---

## 6.4 Ultrasonic ranging

```python
Trig.value(1); utime.sleep_us(10); Trig.value(0)
while Echo.value() == 0: pass          # wait for rising edge
ts = utime.ticks_us()
while Echo.value() == 1: pass          # wait for falling edge
te = utime.ticks_us()
distance_cm = ((te - ts) * 0.034) / 2
```

`0.034 cm/µs` = 340 m/s, the speed of sound at ~15 °C. This is temperature-dependent
(~+0.6 m/s per °C); at 30 °C you're reading ~2.5 % short.

### Three real problems with this implementation

1. **Unbounded blocking spin.** If no echo returns — out of range, absorbent surface,
   angled wall — both `while` loops hang **forever**. The robot keeps doing whatever it
   was doing, with no code running. This is the single most likely cause of a Pico2Go
   "freezing" mid-run.

   Fix:
   ```python
   def dist(timeout_us=30000):
       Trig.value(1); utime.sleep_us(10); Trig.value(0)
       t0 = utime.ticks_us()
       while Echo.value() == 0:
           if utime.ticks_diff(utime.ticks_us(), t0) > timeout_us: return -1
       ts = utime.ticks_us()
       while Echo.value() == 1:
           if utime.ticks_diff(utime.ticks_us(), ts) > timeout_us: return -1
       return (utime.ticks_diff(utime.ticks_us(), ts) * 0.034) / 2
   ```
   30 ms ≈ 5 m of round trip, comfortably beyond the sensor's range.

2. **Inconsistent trigger width.** `Ultrasonic_Ranging.py` and the obstacle demos use
   `sleep_us(10)` (correct), but `Ultrasionc-Infrared-follow.py` uses **`sleep_ms(10)`**
   — a 1000× longer trigger pulse. It happens to still work on most modules, but it's a
   bug; make it `sleep_us(10)`.

3. **Specular reflection.** A smooth surface at an angle reflects the ping away instead
   of back. You get a too-long reading or none at all. Waveshare acknowledges this.
   Practical consequence: **never** rely on ultrasonic alone for obstacle avoidance —
   which is exactly why the combined ultrasonic+IR demo exists.

**Better still:** move this to a PIO state machine or a pin IRQ so it doesn't block the
control loop at all. This is the highest-value single refactor on the platform.

---

## 6.5 IR obstacle avoidance (ST188 + LM393)

Analogue reflective sensors feeding a dual comparator whose threshold is set by two
**trim potentiometers on the underside of the chassis**.

- Output is **active LOW** when something is detected.
- The **green front LEDs** mirror the comparator output — trim with no code running.
- Waveshare's procedure: *"If the LED light is not on or always on, you can adjust the
  two potentiometers on the bottom of the robot to make the LED just turn off. The
  detection distance is the farthest."* **[vendor]**

Range is a few centimetres and is strongly surface-dependent: matte black absorbs IR
and reads as "no obstacle". Glossy white reads far. This is a **binary bumper**, not a
rangefinder.

---

## 6.6 WS2812B via PIO

Standard MicroPython WS2812 PIO program, 8 MHz, `T1=2 / T2=5 / T3=3` cycles, 24-bit
autopull, MSB-first, on **PIO0 state machine 0**.

- Data order on the wire is **GRB**, handled by `pixels_set()`:
  `ar[i] = (g << 16) | (r << 8) | b`.
- `brightness` (default 0.8) is applied as a plain multiply in `pixels_show()`.
- Powered from **5 V**, so nothing lights with the switch off.
- Four LEDs at full white is ~240 mA off the boost converter — noticeable on battery
  life, and the current spike shows up in the battery ADC reading.

---

## 6.7 ST7789 LCD internals

| | |
|---|---|
| Controller | ST7789 (V/VW class) |
| Panel | 1.14", 240 × 135, IPS, 65 K colours |
| Interface | SPI1, 10 MHz, mode 0, MOSI-only |
| Framebuffer | `bytearray(240 × 135 × 2)` = **64,800 bytes** |
| MADCTL (`0x36`) | `0x70` — landscape orientation |
| COLMOD (`0x3A`) | `0x05` — 16 bit/pixel |
| Inversion | `0x21` INVON — normal for IPS |
| Window on `show()` | CASET `0x0028`–`0x0117` (40–279), RASET `0x0035`–`0x00BB` (53–187) |

The column/row offsets exist because the ST7789's frame memory is 240×320; a 240×135
panel sits at an offset inside it. Get these wrong and your image is shifted or wrapped.

**Performance:** `write_cmd`/`write_data` send **one byte per call** and toggle CS each
time — fine for the ~60-byte init sequence, terrible in a loop. `show()` sends the
whole framebuffer in a single `spi.write()`, which is the right call. **Measured:
77.8 ms per frame (~12.9 fps), init 6 ms** — slower than the 51.8 ms a 10 MHz clock
implies, because of MicroPython SPI overhead. **[measured]**

**Speed-ups, in order of payoff:**
1. Only redraw what changed (`fill_rect` the patch, then a partial-window `show`).
2. Raise SPI to 30–60 MHz — ST7789 tolerates it and the RP2350 can drive it.
3. Move the blit to **core 1**, or to DMA, so the control loop never waits on it.

The shipped demos do #1 crudely (repaint one small rectangle every 3 seconds).
