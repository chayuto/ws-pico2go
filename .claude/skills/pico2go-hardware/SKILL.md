---
name: pico2go-hardware
description: Authoritative pin map and electrical reference for the Waveshare Pico2Go / PicoGo robot on an RP2350-Plus board. Use when you need a GPIO number, need to know what a pin is wired to, are adding or removing a peripheral, are checking whether a pin is free, or are reasoning about power rails, the 5 V vs 3V3 split, PIO/PWM/UART/SPI resource conflicts, or which board revision (V1 ADS1015 vs V2 TLC2543) is in play.
---

# Pico2Go hardware reference

**The Pico2Go is the PicoGo chassis with an RP2350-Plus instead of a Pico.** Search for
"PicoGo" — same board, same schematic, same demos. Waveshare publishes **no pinout**;
this map was extracted from `PicoGo_Schematic_V2.pdf` and cross-checked against the
vendor demos and `jblanked/Waveshare` C headers.

Import these from `shared/lib/board.py` rather than hardcoding.

## GPIO map (V2 boards)

| GPIO | Net | Subsystem | Notes |
|---|---|---|---|
| 0 | `GPIO0` | JDY-32 Bluetooth RXD | UART0 TX |
| 1 | `GPIO1` | JDY-32 Bluetooth TXD | UART0 RX |
| 2 | `DSR` | IR obstacle **right** | **active LOW**, external pull-up ✔verified |
| 3 | `DSL` | IR obstacle **left** | **active LOW**, external pull-up ✔verified |
| 4 | `BUZZER` | buzzer via S8050 NPN | active HIGH, 10 K pulldown ✔verified |
| 5 | `IR` | IR receiver output | idle high, **weak** pull-up (see below) |
| 6 | — | TLC2543 I/O CLOCK (pin 18) | PIO |
| 7 | — | TLC2543 DATA INPUT/ADDR (pin 17) | PIO |
| 8 | `DC` | LCD data/command | |
| 9 | `CS` | LCD chip select | |
| 10 | `CLK` | LCD SCK | SPI1 |
| 11 | `DIN` | LCD MOSI | SPI1 |
| 12 | `RST` | LCD reset | |
| 13 | `BL` | LCD backlight | |
| 14 | `Trig` | ultrasonic trigger | 10 µs pulse |
| 15 | `Echo` | ultrasonic echo | idles LOW ✔verified |
| 16 | `PWMA` | TB6612 PWMA — **LEFT** | ⚠ motor |
| 17 | `AIN2` | TB6612 AIN2 — LEFT | ⚠ motor |
| 18 | `AIN1` | TB6612 AIN1 — LEFT | ⚠ motor |
| 19 | `BIN1` | TB6612 BIN1 — **RIGHT** | ⚠ motor |
| 20 | `BIN2` | TB6612 BIN2 — RIGHT | ⚠ motor |
| 21 | `PWMB` | TB6612 PWMB — RIGHT | ⚠ motor |
| 22 | `RGB` | WS2812B ×4 data | **5 V powered** |
| 25 | — | RP2350-Plus user LED | on-module, not on the header |
| 26 | `ADC` | battery sense | ADC0, divider **×2** ✔verified |
| 27 | — | TLC2543 DATA OUT (pin 16) | digital PIO input, not ADC |
| 28 | — | TLC2543 CS (pin 15) | active LOW |
| — | — | die temperature | `machine.ADC(4)` |

**Free GPIO: none.** GP23/24/29 aren't bonded out. Adding hardware means giving
something up — the LCD (GP8–13, 6 pins) is the cheapest trade.

## The power split — the #1 source of "it's broken"

```
USB-C  → MP28164 → 3V3 → MCU, LCD, IR receiver, TLC2543, LM393, JDY-32
14500 cells ×2 (PARALLEL) → IP5306 → [SWITCH] → 5 V → TB6612 motors,
                                                       WS2812B RGB,
                                                       ST188 IR emitters,
                                                       battery-sense divider
```

**Switch OFF + USB only ⇒ MCU boots, LCD works, but nothing moves and no LED lights.**

## Resource budget

| Resource | Used | Free |
|---|---|---|
| GPIO | all 26 | 0 |
| PIO state machines | SM0 (WS2812), SM1 (TLC2543) — both PIO0 | **10 of 12** ✔verified 12 total |
| CPU cores | 1 | **core 1 completely idle** ✔verified usable |
| PWM slices | 2 | 6 |
| UART0 | Bluetooth | UART1 pins taken |
| SPI1 | LCD | SPI0 pins taken |
| I²C | none on V2 | both — pins taken |

## Measured facts (this board, verified on hardware)

- RP2350A, **revision A4**, QFN60, ARM + RISC-V available, chipid `5707f03baa9f57ed`.
  A4 means **erratum E9 is fixed in silicon** — the floating-input concern on the PIO
  line-sensor read does not apply.
- 150.0 MHz; heap 497,472 B total; filesystem 3,072 KB on 4 MB flash.
- Battery pin 2.127 V → **4.25 V with ×2**. ×3.0 would give 6.38 V, impossible for a
  1S Li-ion behind an IP5306. **Use ×2.**
- Die temp 0.712 V → 23.3 °C via the RP2040 formula `27-(v-0.706)/0.001721`. It carries
  over to RP2350 and reads plausibly. Uncalibrated; trend only.
- **GP5 is only weakly pulled up** — it loses to the RP2350's ~60 K internal pulldown.
  The schematic's `R1 4.7k` was misattributed; the pull is likely the IR receiver's own
  internal ~30 K. Don't rely on a strong external pull-up there.

## V1 vs V2

V2 (Sept 2022 onward, what you have): line ADC is a **TLC2543** on GP6/7/27/28, PIO-driven.
V1: an **ADS1015 on I²C1** plus GP27/GP28 read directly as ADC. **`TRSensor.py` is not
interchangeable.** Use `PicoGo_Code_V2.zip`.

## Key parts

TB6612FNG (motors, `STBY` hard-tied, not GPIO) · TLC2543 (12-bit 11-ch serial ADC) ·
5× ITR20001/T (line) · 2× ST188 + LM393 (obstacle, trim pots underside) ·
ST7789 240×135 IPS · 4× WS2812B · JDY-32 (SPP+BLE) · IP5306 + S8261 + AO4406A (power).

**No wheel encoders anywhere.** No odometry, no closed-loop speed, robot drifts.
