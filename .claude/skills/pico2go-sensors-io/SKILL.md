---
name: pico2go-sensors-io
description: The Pico2Go/PicoGo non-drive peripherals - HC-SR04 ultrasonic ranging, ST188+LM393 IR obstacle detection and its trim pots, battery voltage and die temperature ADC, the ST7789 1.14in LCD, the four WS2812B RGB LEDs, and the buzzer. Use for distance, ranging, sonar, obstacle avoidance, battery level, temperature, screen, display, framebuffer, NeoPixel, RGB or beep questions on this robot.
---

# Sensors & I/O

## Ultrasonic — GP14 trig, GP15 echo

⚠ **The vendor's `dist()` has no timeout** and spins forever on a missed echo — out of
range, angled wall, soft surface, unplugged module. The robot keeps driving with no code
running. This is the most likely cause of a Pico2Go "freezing" mid-run.

**Always use `shared/lib/sonar.py`:**

```python
import sonar
d = sonar.read()            # cm, or None on timeout (30 ms ≈ 5 m)
d = sonar.read_median(5)    # median of 5, ignores timeouts — use this
```

**Verified:** 20/20 pings returned; a forced 1 µs timeout returned in 205 µs, so the
guard works. Header runs at **3V3**, not 5 V — don't drop in a 5 V HC-SR04 unchecked.

Speed of sound is temperature-dependent (~+0.6 m/s per °C); `0.0343 cm/µs` assumes
~20 °C. Ultrasound reflects specularly — an angled surface bounces the ping away, so
never rely on it alone. Combine with the IR obstacle sensors.

Another vendor bug: `Ultrasionc-Infrared-follow.py` uses `sleep_ms(10)` for the trigger
instead of `sleep_us(10)` — 1000× too long.

## IR obstacle — GP2 (DSR, right), GP3 (DSL, left)

ST188 reflective sensors → LM393 comparator. **Active LOW = obstacle.**
**Verified:** both pins have strong external pull-ups, so idle reads 1.

- Threshold is set by **two trim potentiometers on the underside** — they ship untrimmed.
- The **green front LEDs mirror the comparator output**, so you can trim with no code
  running: adjust until the LED *just* goes out with nothing in front. That's maximum
  range.
- The ST188 **emitters run on the 5 V rail** — with the power switch off, these never
  trigger no matter what you put in front of them.
- Range is a few cm and surface-dependent. Matte black absorbs IR and reads as "clear".
  It is a **binary bumper**, not a rangefinder.

## Battery — GP26 / ADC0

```python
v = ADC(Pin(26)).read_u16() * 3.3 / 65535 * 2.0     # divider is x2
pct = max(0, min(100, (v - 3.0) * 100 / 1.2))       # 3.0 V = 0%, 4.2 V = 100%
```

**Verified: ×2 is correct** — measured 2.127 V at the pin → 4.25 V, a full 14500 cell.
jblanked's C driver uses ×3.0, which would give 6.38 V, impossible behind a single-cell
IP5306. Two 14500 cells are in **parallel**, not series.

- The sense divider is **gated by the 5 V rail** — readings are meaningless with the
  switch off.
- Take readings **with the motors stopped**; inrush sags the pack 100–300 mV.
- Improve on the vendor code with a median-of-9 filter and `v = 0.7*v + 0.3*new`.
- Percentage is a naive linear voltage map. Waveshare admits it's inaccurate.

## Die temperature — `machine.ADC(4)`

```python
v = ADC(4).read_u16() * 3.3 / 65535
c = 27 - (v - 0.706) / 0.001721
```

**Verified plausible on RP2350** (0.712 V → 23.3 °C). Uncalibrated and part-to-part
variable; it measures the **die**, not the room. Trend indicator only.

⚠ Immediately after a flash+reboot the ADC can read wildly wrong on **all** channels
(observed: battery pinned full-scale, temp −82 °C). Re-run before diagnosing.

## LCD — ST7789, GP8–13, SPI1

240 × 135 IPS, RGB565, framebuffer **64,800 bytes**. Subclasses `framebuf.FrameBuffer`,
so `fill/pixel/line/rect/fill_rect/text/blit/scroll` all work. `show()` blits the whole
buffer at a fixed window: column offset **40**, row offset **53** (the panel sits inside
the controller's 240×320 memory).

**Measured: `show()` takes 77.8 ms → ~12.9 fps max.** (Theory says 51.8 ms at 10 MHz;
MicroPython SPI overhead accounts for the rest.) Init is 6 ms.

That 78 ms **blocks any control loop on the same thread.** Fixes in order of payoff:
1. Redraw only what changed (`fill_rect` a patch, partial window).
2. Raise SPI to 30–60 MHz.
3. Move the blit to **core 1** (verified usable, and completely idle).

⚠ The driver's colour constants are **not** textbook RGB565 — `GREEN` is `0x001F`
(pure blue in standard RGB565), `BLUE` is `0xFF00`. Don't reason from them; put a test
pattern up and pick values empirically.

## WS2812B — GP22, 4 LEDs

PIO SM0, 8 MHz, GRB on the wire (handled by `pixels_set`). **Measured 641 µs per update.**

```python
from ws2812 import NeoPixel
s = NeoPixel()                       # brightness default 0.8
s.pixels_fill(s.RED); s.pixels_show()
s.rainbow_cycle(0.02)
```

Powered from **5 V** — dark with the switch off. Four LEDs at full white is ~240 mA and
shows up in the battery reading. Leave them `BLACK` when nobody's watching.

## Buzzer — GP4

Active HIGH via an S8050 NPN. **Verified: 10 K external pulldown, idles low.**

```python
Pin(4, Pin.OUT).value(1); utime.sleep_ms(80); Pin(4, Pin.OUT).value(0)
```

`board.estop()` forces it low. Don't leave it on — and don't beep when the user is away.
