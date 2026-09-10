# 01 — Hardware Overview

## 1.1 What you actually bought

The Pico2Go is **not a new robot**. It is Waveshare's existing *PicoGo* chassis and
mainboard, shipped with an **RP2350-Plus-M** controller instead of a Raspberry Pi Pico.
This is confirmed by the vendor's own documentation: the Pico2Go wiki's "Resources"
section links to the **PicoGo** schematic (V1/V2) and the **PicoGo** demo code
packages, and every demo file still prints `"PicoGo"` on the LCD. **[vendor][code]**

Practical consequence: **all PicoGo documentation, demos, schematics and third-party
projects apply directly to the Pico2Go.** Search for "PicoGo", not "Pico2Go" — you will
find roughly 100× more material.

### Kit contents **[vendor]**

| Item | Qty | Notes |
|---|---|---|
| Pico2Go base board | 1 | The PicoGo mainboard (V2 revision) |
| Pico2Go acrylic panel | 1 | Top deck |
| 1.14inch LCD Module | 1 | ST7789, 240×135, plugs into an 8-pin header |
| Ultrasonic sensor | 1 | HC-SR04-class, 4-pin (VCC/Trig/Echo/GND) |
| **RP2350-Plus-M** | 1 | `-M` = pin headers pre-soldered |
| IR remote controller | 1 | NEC-protocol, small card remote |
| USB-A → micro-B cable, 1.2 m | 1 | ⚠️ see note below |
| PH2.0 8-pin cable, 5 cm, opposite-side headers | 1 | LCD flying lead |
| 5 V 3 A power supply | 1 | Optional / region plug selectable |
| Mini cross wrench sleeve, screwdriver, screws pack | 1 ea | Assembly hardware |

**⚠️ Cable mismatch:** the kit still ships the PicoGo-era **USB-A to micro-B** cable,
but the RP2350-Plus has a **USB Type-C** connector. Have a USB-C data cable ready — the
micro-B cable in the box will not connect to the new controller board. **[inference,
from the published package list vs. the RP2350-Plus connector]**

**⚠️ Batteries not included:** you need **two 14500 Li-ion cells (3.7 V nominal)**.
14500 is AA-sized but is *not* an AA. Do not put alkaline AAs in it.

---

## 1.2 Controller board — RP2350-Plus **[vendor]**

A Pico-2-form-factor board from Waveshare, pin-compatible with the Raspberry Pi Pico 2.

| Spec | Value |
|---|---|
| MCU | **RP2350A** (Raspberry Pi, UK) |
| Cores | Dual Arm Cortex-M33 **or** dual Hazard3 RISC-V, selectable at boot |
| Clock | up to 150 MHz |
| SRAM | 520 KB |
| Flash | 4 MB (`W25Q32JVSSIQ`) — 16 MB variant also exists (`W25Q128JVSIQ`) |
| USB | **Type-C**, USB 1.1 device *and* host |
| GPIO | 26 multifunction |
| Peripherals | 2 × SPI, 2 × I²C, 2 × UART, 4 × 12-bit ADC, 16 × PWM, on-die temp sensor |
| PIO | **12 state machines** (3 blocks × 4) — RP2040 had 8 |
| Regulator | **MP28164** buck-boost DC-DC, 2 A |
| Charger | **ETA6096** Li-ion charge manager |
| Battery header | **MX1.25**, 3.7 V Li-ion, charge-while-run |
| Buttons | BOOT, RESET (Pico 2 has BOOT only) |
| Extras | Castellated edges for direct solder-down; USB/BOOT/DEBUG test points |
| User LED | **GP25** **[3rd-party — `arduino-pico` variant `waveshare_rp2350_plus`]** |

### What the upgrade actually buys you over the original Pico-based PicoGo

- **~2× SRAM** (520 KB vs 264 KB) — the 64,800-byte LCD framebuffer stops being a big deal.
- **50% more clock** (150 vs 133 MHz) and a Cortex-M33 with FPU, DSP and optional
  security extensions.
- **50% more PIO** (12 vs 8 state machines) — this platform already burns 2 on
  WS2812 + the line-sensor ADC, so headroom matters.
- **RISC-V option** — you can run the exact same robot on Hazard3 cores by choosing a
  different toolchain. Genuinely useful as a teaching device.
- **USB-C + on-board battery charging + RESET button** on the controller itself.

### What it does *not* buy you

- **No Wi-Fi, no on-chip Bluetooth.** RP2350A has no radio. The robot's wireless is the
  separate JDY-32 module on the mainboard. If you want Wi-Fi you are adding a module.
- No extra GPIO — same 26 pins, and the chassis already uses all of them.

---

## 1.3 Mainboard subsystems (V2 revision)

Every part below was read off the V2 schematic net list. **[schematic]**

### Motion
| Part | Role |
|---|---|
| **TB6612FNG** (`TB1`) | Dual H-bridge motor driver. `AO1/AO2` → left motor (`Motor-L`), `BO1/BO2` → right motor (`Motor-R`). `VM1/2/3` fed from the 5 V rail; `STBY` is hard-tied, **not** GPIO-controlled. |
| 2 × **N20 micro gearmotor** | Metal gearbox, plugged into 2-pin `Wheel` headers. Gear ratio and RPM are **not published** by Waveshare. |
| — | **No encoders anywhere on the board.** No odometry, no closed-loop speed. |

### Line following
| Part | Role |
|---|---|
| **TLC2543** (`TL1`) | 11-channel, **12-bit**, SPI-ish serial ADC. Analog inputs `A0..A4` ← `IR1..IR5`. Control: `IOCLK`←GP6, `ADDR`←GP7, `DOUT`→GP27, `CS`←GP28. |
| 5 × **ITR20001/T** | Reflective IR emitter/phototransistor pairs, the downward-facing line array. Each with a 470 Ω emitter resistor; `R15` 15 K in the sense network. |

### Obstacle avoidance
| Part | Role |
|---|---|
| 2 × **ST188** (`SR1`, `SL1`) | Forward-facing reflective IR sensors → analog nets `ASR` (right) / `ASL` (left). |
| **LM393** | Dual comparator. `OUT1` → `DSR` (GP2), `OUT2` → `DSL` (GP3). Threshold set by the two **trim potentiometers on the underside**. |
| `LEDR1`, `LEDL1` | Green front indicator LEDs, driven off the comparator outputs — they show you the trigger state without any code running. |

### Ranging
| Part | Role |
|---|---|
| Ultrasonic header (4-pin) | `3V3`, `Trig`←GP14, `Echo`→GP15, `GND`. HC-SR04-class module supplied in the kit. |

### HMI
| Part | Role |
|---|---|
| **ST7789** 1.14" IPS LCD (`H2`, 8-pin) | 240×135, 65 K colours. SPI1: `DIN`←GP11, `CLK`←GP10, `CS`←GP9, `DC`←GP8, `RST`←GP12, `BL`←GP13. |
| 4 × **WS2812B** (`L1..L4`) | Daisy-chained RGB LEDs on the underside, data ← GP22, powered from **5 V**. |
| Buzzer (`B1`) | Active buzzer via `Q3` **S8050** NPN, base resistor `R34` 1 K, `R35` 10 K pulldown, driven from GP4 (active-high). |
| IR receiver (`H1`) | 3-pin (VCC/GND/Vout), 3V3-powered, output → GP5. Idle high via a **weak** pull only — the `R1 4.7 K` once attributed here belongs to an adjacent net. **[measured]** |

### Wireless
| Part | Role |
|---|---|
| **JDY-32** | Dual-mode Bluetooth: **BT 3.0 SPP + BLE 4.2**. `TXD`→GP1, `RXD`←GP0 (so it lands on **UART0**). `VCC` 3V3, `EN` on pin 14, `STAT`/`ALED` status pins present. |

> ⚠️ **Naming mismatch.** The V2 schematic says **JDY-32**; the wiki's pairing
> instructions tell you to select the device named **`JDY-33-SPP`** (and warn that
> `JDY-33-BLE` will fail to connect). Both are dual-mode SPP+BLE modules from the same
> family, and the advertised name is a firmware setting. Pair with whatever **`-SPP`**
> device appears; do not pick the `-BLE` one. **[schematic vs. vendor]**

### Power
| Part | Role |
|---|---|
| **IP5306** | Power-bank PMIC: 2.4 A boost to 5 V, 2.1 A charge, 4-LED fuel gauge, single-key control, 1 µH inductor, `R4` 0.5 Ω 1% current sense. |
| **S8261** + 2 × **AO4406A** | Single-cell Li-ion protection: over-charge, over-discharge, over-current, short-circuit. |
| `Q1` **SI2305** | P-channel MOSFET on the VSYS/5 V path (source select / reverse blocking). |
| `Q4` **AO3401** + `Q5` **S8050** | Switched battery-voltage divider feeding the ADC — see [03](03-power-and-battery.md). |
| PPTC fuse 16 V / 3 A (1812) | Self-resetting fuse in series with the battery holders `P5`/`P6`. This is the part that gets hot if you insert a cell backwards. |
| `S1` | Chassis slide power switch (enables the 5 V rail). |

---

## 1.4 Board revisions — V1 vs V2 **[vendor]**

> "From September 2022, the V2 version will be shipped as the original ADC chip is out
> of stock. The ADC chips are different in the V1 and V2 versions, **the tracking demos
> are not compatible**, but the function effects are the same."

| | V1 (pre-Sept 2022) | V2 (current, what you have) |
|---|---|---|
| Line-sensor ADC | **ADS1015** (I²C, 12-bit, 4-ch) at `0x48` on I²C1, *plus* two channels read directly by the RP2350's own ADC on GP27/GP28 | **TLC2543** (serial, 12-bit, 11-ch), all 5 channels through the ADC, bit-banged with **PIO** |
| Pins used | I²C1 (GP6/GP7) + ADC1/ADC2 (GP27/GP28) | GP6 (clock), GP7 (addr), GP27 (dout), GP28 (cs) |
| Demo file | `TRSensor.py` (V1 flavour) | `TRSensor.py` (V2 flavour) |
| Schematic | `PicoGo_Schematic.pdf` | `PicoGo_Schematic_V2.pdf` |

**Only `TRSensor.py` and `Ultrasionc-Infrared-follow.py` differ between the two demo
packages.** Everything else is byte-identical. **[verified by diffing the V1 and V2 zips]**

A 2026-purchase Pico2Go is V2. **Use `PicoGo_Code_V2.zip`.** If you download the V1
package by mistake, line following will return garbage and nothing will tell you why.

---

## 1.5 Physical

| | |
|---|---|
| Chassis | ~**110 × 45 mm** **[3rd-party, reseller listings]** |
| Shipped weight | ~370 g **[3rd-party]** |
| Drive | Two-wheel differential + caster/ball at the rear |
| Battery | 2 × 14500 in dedicated holders (`P5`, `P6`) |
| Assembly | Screwed acrylic deck; screwdriver and wrench included |

The kit ships unassembled. Waveshare publishes no written build instructions on the
Pico2Go wiki — assembly is inferred from the product photos on the shop page and the
PicoGo assembly videos. Budget 20–30 minutes.
