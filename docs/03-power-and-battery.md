# 03 — Power & Battery

Power is where most Pico2Go owners lose their first hour. The board has **two
independent supply domains** and they are not obviously connected.

## 3.1 The power tree

```
 USB-C on RP2350-Plus ─┬─► ETA6096 charger ─► MX1.25 batt hdr (unused on this chassis)
                       └─► MP28164 buck-boost ─► 3V3 ──► MCU, LCD, IR receiver,
                                                          TLC2543, ST188 front-ends,
                                                          LM393, JDY-32

 2 × 14500 Li-ion  ──► PPTC 16V/3A ──► S8261 + 2× AO4406A (protection)
   (in PARALLEL)                             │
                                             ▼
                                        IP5306 PMIC ──► boost ──► 5 V rail
                                          (S1 switch)              │
                                                                   ├─► TB6612 VM (MOTORS)
                                                                   ├─► WS2812B × 4
                                                                   ├─► ST188 IR emitters
                                                                   └─► battery-sense divider
```

### The rule that explains everything

> **3V3 comes from USB. 5 V comes from the batteries, through the slide switch.**

| Powered by | Switch | MCU boots | LCD | Motors | RGB LEDs | IR obstacle |
|---|---|---|---|---|---|---|
| USB only | **OFF** | ✅ | ✅ | ❌ | ❌ | ❌ |
| USB only | **ON** | ✅ | ✅ | ✅ | ✅ | ✅ |
| Battery only | ON | ✅ | ✅ | ✅ | ✅ | ✅ |
| Battery only | OFF | ❌ | ❌ | ❌ | ❌ | ❌ |

Waveshare states this, but buries it in a bullet halfway down the "Precautions"
section: *"The onboard infrared obstacle avoidance sensor, RGB LEDs, and motors all
need a 5 V power supply. If you don't turn on the power switch and only connect to the
USB power supply, these functions will not work normally."* **[vendor]**

**Charge-while-run is supported** — you can leave USB connected with the switch ON and
develop, debug and drive at the same time. **[vendor]**

---

## 3.2 Batteries — 14500 Li-ion

| | |
|---|---|
| Chemistry / voltage | Li-ion, **3.7 V nominal** (3.0–4.2 V working range) |
| Size | **14500** — 14 mm × 50 mm, i.e. AA-shaped |
| Quantity | **2, wired in parallel** (not series) |
| Included? | **No.** Buy separately. |
| Typical capacity | 700–1000 mAh each (be sceptical of "3000 mAh" listings) |

**Parallel, not series** — this is inferred but well-supported: the IP5306 is a
single-cell power-bank PMIC (3.7 V in, 5 V boost out), the S8261 is a single-cell
protector, and Waveshare's own fuel-gauge maths maps **3.0 V → 0 %** and **4.2 V →
100 %**. A series pack would present 6.0–8.4 V. **[inference from schematic + code]**

### Buying advice

- **Button-top, protected** cells are the safest choice for a holder like this.
- Buy a **matched pair** — same brand, same batch, same age. Paralleling mismatched
  cells means the stronger one dumps current into the weaker one.
- Avoid the "9900 mAh" fantasy cells; real 14500 capacity tops out near ~1100 mAh.
- **Never** put an alkaline or NiMH AA in these slots. 14500 slots are Li-ion slots.

---

## 3.3 Insertion, activation and the fuse

Waveshare's precautions, in the order they actually bite you: **[vendor]**

1. **Observe polarity** — it is silkscreened in each holder.
2. **Reverse-inserted cell** → the warning indicator lights and the **self-resetting
   PPTC fuse gets seriously hot**. Remove and reinstall the cells immediately. The
   fuse is 16 V / 3 A, 1812 package, in series with the holders. **[schematic]**
3. **After changing cells you must "activate" the pack**: connect USB power (or flip
   the switch) once, otherwise the protection IC stays latched off and the robot will
   not power up at all. This trips up nearly everyone once.
4. On USB connect or switch-on, the **power indicator (red)** and **battery indicator
   (yellow-green)** light. After you unplug USB and switch off, red goes out
   immediately and the battery indicator fades after a delay. Pressing the key wakes
   the gauge for a few seconds.
5. **One flashing indicator LED = low battery, go charge.**

### Charging

The IP5306 handles charging from the chassis USB path; the RP2350-Plus additionally
carries its own ETA6096 charger for the MX1.25 header (which this chassis does not
use). Charge current is set by the IP5306's configuration; the part supports up to
2.1 A. The four `LED1..LED4` outputs are the fuel gauge you see on the chassis.
`KEY` (pin 5) is the single-button control input; `R31` 10 K is its pull. **[schematic]**

---

## 3.4 Reading battery voltage

### What the hardware does **[schematic]**

The battery-sense node is a **switched** divider, not a permanently connected one:
`Q4` (AO3401, P-MOSFET) gates the battery into a resistor chain (`R36` 100 K, `R37`
100 K, with `R39` 100 K / `R40` 47 K and `Q5` S8050 forming the enable network from
the **5 V** rail) down to **GP26 / ADC0**.

Two consequences:

1. **The divider only draws current when the 5 V rail is up.** Good for shelf life —
   but it also means **battery voltage reads meaningless with the switch off**.
2. The **100 K / 100 K** pair implies a **1:1 divider**, i.e. `V_batt = V_adc × 2`.

### What Waveshare's code does **[code]**

```python
bat = machine.ADC(Pin(26))
v = bat.read_u16() * 3.3 / 65535 * 2          # ×2 divider
p = (v - 3) * 100 / 1.2                        # 3.0 V = 0 %, 4.2 V = 100 %
p = max(0, min(100, p))
```

### ⚠️ A conflict worth knowing about

jblanked's C implementation of the same board uses a **×3.0** multiplier and a
**3.3 V → 0 % / 4.2 V → 100 %** curve:

```c
return result * (3.3 / (1 << 12)) * 3.0;   // battery.c
```

These cannot both be right. **Settled on hardware: ×2 is correct.**

Measured 2.127 V at GP26 on a charged pack:

| Multiplier | Implied pack voltage | Verdict |
|---|---|---|
| **×2.0** | **4.25 V** | ✅ exactly a full 14500 Li-ion |
| ×3.0 | 6.38 V | ❌ impossible for a 1S cell behind an IP5306 |

A pull test confirms GP26 is driven by a genuinely stiff source — the internal pull-up
*and* pull-down each move it by **0 %** — so it is a real divider on a real battery, not
a floating pin. Use **×2**. A DMM check is still worth one minute if you're building a
low-battery cutoff. **[measured]**

### A better fuel gauge than the shipped one

The stock percentage is a straight linear map of voltage, which Waveshare admits is
inaccurate ("*the actual battery voltage and electric quantity are not linear, so there
will be some errors*"). Two cheap improvements, both borrowed from the C driver:

- **Median-of-9 filter**: take 9 samples, sort, drop the highest and lowest, average
  the rest. Kills ADC noise from the motor PWM.
- **Exponential smoothing**: `v = 0.7·v_prev + 0.3·v_new`. Stops the reading collapsing
  every time the motors accelerate (motor inrush sags the pack by 100–300 mV).

Measure **with the motors stopped** if you want a number that means anything.

---

## 3.5 On-die temperature

```python
temp = machine.ADC(4)                                   # internal channel
reading = temp.read_u16() * 3.3 / 65535
temperature = 27 - (reading - 0.706) / 0.001721
```

This is the classic first-order RP2040 conversion, carried over verbatim into the
Pico2Go demos. **Measured on RP2350: 0.712 V → 23.3 °C**, a plausible room temperature,
so the formula does carry over. It remains **uncalibrated and part-to-part variable by
several degrees**, and it measures the *die*, not the room. Trend indicator only.
**[measured]**

> ⚠ **First run after a flash reads garbage.** Immediately after flashing and rebooting,
> the ADC was observed returning nonsense on *every* channel — battery pinned at full
> scale (6.60 V) and die temperature at −82.5 °C. A second run gave correct, stable,
> repeatable values. Re-run before diagnosing an analog fault. **[measured]**

---

## 3.6 Safety

Waveshare's own warnings, condensed — they are not boilerplate, Li-ion in a cheap
holder is a real hazard:

- Do not reverse polarity when charging or discharging.
- Do not mix old and new cells, or cells from different brands.
- Use cells from a reputable manufacturer, matched to a 3.7 V single-cell spec.
- Replace cells at end of cycle life or after ~2 years, whichever comes first.
- Store away from flammables and away from children.
- Don't charge unattended, and don't leave a robot with a swollen cell on a shelf.

**Practical additions:**
- Remove the cells if the robot is going in a drawer for a month.
- If the PPTC fuse has ever been hot, inspect the holders for melted plastic before
  reusing them.
- The 5 V rail feeds the motor driver directly; a stalled motor can pull well over 1 A.
  Don't hold the wheels while it drives at 100 % duty.
