# 02 — Pinout Reference

> **This is the document Waveshare doesn't publish.** The Pico2Go and PicoGo wikis
> contain *no pinout table at all*. Everything below was reconstructed by extracting
> the net list from `PicoGo_Schematic_V2.pdf` and cross-checking it against every pin
> constant in Waveshare's MicroPython demos and in jblanked's C SDK headers. Where the
> two agree (they do, on every pin), the assignment is certain.

## 2.1 Master GPIO map

| GPIO | Header pin | Net | Subsystem | Direction | Notes |
|---|---|---|---|---|---|
| **GP0** | 1 | `GPIO0` | JDY-32 Bluetooth **RXD** | MCU → module | UART0 TX |
| **GP1** | 2 | `GPIO1` | JDY-32 Bluetooth **TXD** | module → MCU | UART0 RX |
| **GP2** | 4 | `DSR` | IR obstacle **right** (LM393 `OUT1`) | in | **Active LOW** = obstacle |
| **GP3** | 5 | `DSL` | IR obstacle **left** (LM393 `OUT2`) | in | **Active LOW** = obstacle |
| **GP4** | 6 | `BUZZER` | Buzzer via S8050 NPN | out | Active **HIGH** |
| **GP5** | 7 | `IR` | IR receiver output | in | Idle high, **weak** pull-up only — see note ✔measured |
| **GP6** | 9 | `GPIO6` | TLC2543 **I/O CLOCK** (pin 18) | out | Line-sensor ADC |
| **GP7** | 10 | `GPIO7` | TLC2543 **DATA INPUT / ADDR** (pin 17) | out | Line-sensor ADC |
| **GP8** | 11 | `DC` | LCD data/command | out | |
| **GP9** | 12 | `CS` | LCD chip select | out | |
| **GP10** | 14 | `CLK` | LCD SCK | out | **SPI1 SCK** |
| **GP11** | 15 | `DIN` | LCD MOSI | out | **SPI1 TX** |
| **GP12** | 16 | `RST` | LCD reset | out | |
| **GP13** | 17 | `BL` | LCD backlight enable | out | Drive high = on |
| **GP14** | 19 | `Trig` | Ultrasonic trigger | out | 10 µs pulse |
| **GP15** | 20 | `Echo` | Ultrasonic echo | in | Width ∝ distance |
| **GP16** | 21 | `PWMA` | TB6612 **PWMA** (left) | out | PWM, 1 kHz in the demos |
| **GP17** | 22 | `AIN2` | TB6612 **AIN2** (left) | out | |
| **GP18** | 24 | `AIN1` | TB6612 **AIN1** (left) | out | |
| **GP19** | 25 | `BIN1` | TB6612 **BIN1** (right) | out | |
| **GP20** | 26 | `BIN2` | TB6612 **BIN2** (right) | out | |
| **GP21** | 27 | `PWMB` | TB6612 **PWMB** (right) | out | PWM, 1 kHz in the demos |
| **GP22** | 29 | `RGB` | WS2812B data in (`L1`→`L2`→`L3`→`L4`) | out | 5 V-powered strip |
| **GP25** | — | on-module | **RP2350-Plus user LED** | out | Not on the 40-pin header |
| **GP26 / ADC0** | 31 | `ADC` | Battery voltage sense | analog in | Via switched divider — see [03](03-power-and-battery.md) |
| **GP27 / ADC1** | 32 | `GPIO27` | TLC2543 **DATA OUT** (pin 16) | in | Used as a *digital* PIO input, not ADC |
| **GP28 / ADC2** | 34 | `GPIO28` | TLC2543 **CS** (pin 15) | out | Active LOW |
| — | 4 (ADC ch) | — | RP2350 on-die temperature sensor | analog in | `machine.ADC(4)` |

### Free pins: **none**

GP23, GP24, GP29 are not brought out on the Pico-2 form factor. Every user GPIO from
GP0–GP22 and GP26–GP28 is committed by the chassis. **To add a peripheral you must
free an existing one** — see [09 — Extending the Platform](09-extending-the-platform.md)
for which subsystems are cheapest to sacrifice.

---

## 2.2 40-pin header, as wired on the Pico2Go mainboard

Standard Raspberry Pi Pico / Pico 2 physical pinout, annotated with the robot's nets.

```
                        ___(_____)___
    JDY RXD  GP0    1  |   *USB-C*   | 40   VBUS
    JDY TXD  GP1    2  |             | 39   VSYS
             GND    3  |             | 38   GND
   DSR (R)   GP2    4  |             | 37   3V3_EN
   DSL (L)   GP3    5  |             | 36   3V3(OUT)
   BUZZER    GP4    6  |             | 35   ADC_VREF
   IR RX     GP5    7  |             | 34   GP28   TLC2543 CS
             GND    8  |             | 33   AGND
   ADC CLK   GP6    9  |  RP2350-A   | 32   GP27   TLC2543 DOUT
   ADC ADDR  GP7   10  |             | 31   GP26   BATTERY ADC
   LCD DC    GP8   11  |             | 30   RUN
   LCD CS    GP9   12  |             | 29   GP22   WS2812B DATA
             GND   13  |             | 28   GND
   LCD CLK   GP10  14  |             | 27   GP21   PWMB  (right)
   LCD DIN   GP11  15  |             | 26   GP20   BIN2  (right)
   LCD RST   GP12  16  |             | 25   GP19   BIN1  (right)
   LCD BL    GP13  17  |             | 24   GP18   AIN1  (left)
             GND   18  |             | 23   GND
   US TRIG   GP14  19  |             | 22   GP17   AIN2  (left)
   US ECHO   GP15  20  |____|_|_|____| 21   GP16   PWMA  (left)
                          SWCLK GND SWDIO
```

---

## 2.3 Per-subsystem wiring detail

### Motors — TB6612FNG

| TB6612 pin | Net | GPIO | Truth table |
|---|---|---|---|
| `PWMA` | `PWMA` | GP16 | Left-motor speed |
| `AIN1` | `AIN1` | GP18 | |
| `AIN2` | `AIN2` | GP17 | `AIN2=1, AIN1=0` → forward; `0,1` → reverse; `0,0` → coast/stop |
| `PWMB` | `PWMB` | GP21 | Right-motor speed |
| `BIN1` | `BIN1` | GP19 | |
| `BIN2` | `BIN2` | GP20 | `BIN2=1, BIN1=0` → forward |
| `STBY` | — | **not connected to a GPIO** | Hard-tied; you cannot software-disable the bridge |
| `VM1/2/3` | 5 V rail | — | **From the battery boost converter, not USB** |

Channel A = **left**, channel B = **right** (schematic nets `Motor-L` / `Motor-R`;
matches `setMotor(left, right)` in `Motor.py`). **[schematic][code]**

```python
# Minimal motor bring-up, MicroPython
from machine import Pin, PWM
PWMA = PWM(Pin(16)); PWMA.freq(1000)
AIN2 = Pin(17, Pin.OUT); AIN1 = Pin(18, Pin.OUT)
BIN1 = Pin(19, Pin.OUT); BIN2 = Pin(20, Pin.OUT)
PWMB = PWM(Pin(21)); PWMB.freq(1000)

def forward(pct):
    PWMA.duty_u16(pct * 0xFFFF // 100); PWMB.duty_u16(pct * 0xFFFF // 100)
    AIN2.value(1); AIN1.value(0); BIN2.value(1); BIN1.value(0)
```

> ⚠️ **PWM slice collision.** On RP2350, GP16 and GP21 land on *different* PWM slices
> (16 → slice 0 channel A, 21 → slice 2 channel B), so the two motors are independent.
> But GP16/GP17 share slice 0 and GP20/GP21 share slice 2 — since AIN2 (GP17) and BIN2
> (GP20) are used as plain GPIO, not PWM, there is no conflict. Do not try to PWM the
> direction pins.

### Line-tracking array — TLC2543 (V2 boards)

| TLC2543 | Pin | Connected to |
|---|---|---|
| `AIN0` | 1 | `IR1` — leftmost ITR20001/T |
| `AIN1` | 2 | `IR2` |
| `AIN2` | 3 | `IR3` — centre |
| `AIN3` | 4 | `IR4` |
| `AIN4` | 5 | `IR5` — rightmost |
| `CS` | 15 | **GP28** (active low) |
| `DATA OUT` | 16 | **GP27** |
| `DATA INPUT` (address) | 17 | **GP7** |
| `I/O CLOCK` | 18 | **GP6** |
| `VCC` | 20 | 3V3 |

Driven by a **PIO** state machine, not the hardware SPI blocks — see
[06 — Sensors & Algorithms](06-sensors-and-algorithms.md) for the protocol.

> On **V1** boards this block is an **ADS1015 on I²C1 at address `0x48`** (GP6=SDA,
> GP7=SCL) with the two outer sensors wired straight to `ADC1`/`ADC2` (GP27/GP28).
> Same pins, completely different protocol. The demos are not interchangeable.

### IR obstacle avoidance

```
ST188 (SR1, right) --ASR--> LM393 IN1 --OUT1--> GP2 (DSR)  + LEDR1
ST188 (SL1, left)  --ASL--> LM393 IN2 --OUT2--> GP3 (DSL)  + LEDL1
                              ^
                     trim pot threshold (underside of chassis)
```

Comparator output is **open-collector, active LOW when an obstacle is detected**.
The green front LEDs mirror the comparator state, so you can trim the pots with no
firmware running at all: adjust until the LED *just* goes out with no obstacle
present — that is maximum detection range. **[vendor][schematic]**

### Ultrasonic

4-pin header: `3V3 / Trig(GP14) / Echo(GP15) / GND`. Note the module runs at **3V3**
here, not 5 V — a genuine HC-SR04 is a 5 V part, so what ships is a 3.3 V-tolerant
equivalent. Do not swap in a random 5 V HC-SR04 without checking. **[schematic]**

### LCD (ST7789, 1.14", 240×135)

8-pin header `H2`, ordered **`VCC, GND, DIN, CLK, CS, DC, RST, BL`** (schematic pins
8→1). Wired to **SPI1** at up to 10 MHz in the demo driver.

| Signal | GPIO | SPI1 role |
|---|---|---|
| `DIN` | GP11 | MOSI / TX |
| `CLK` | GP10 | SCK |
| `CS` | GP9 | chip select (GPIO, not hardware CS) |
| `DC` | GP8 | data/command |
| `RST` | GP12 | reset |
| `BL` | GP13 | backlight |

There is **no MISO** — the panel is write-only in this design.

### WS2812B RGB

Single data line GP22 → `L1` → `L2` → `L3` → `L4`, all four on the **underside** of
the chassis. Powered from the **5 V** rail, so they are dark unless the power switch
is on. Driven by a PIO state machine at 8 MHz.

### Bluetooth (JDY-32)

| JDY-32 | GPIO | Note |
|---|---|---|
| `TXD` (pin 1) | GP1 | → MCU UART0 RX |
| `RXD` (pin 2) | GP0 | ← MCU UART0 TX |
| `VCC` (pin 13) | 3V3 | |
| `EN` (pin 14) | — | tied on board |
| `STAT` / `ALED` | — | connection-status indicators |

`CTS`/`RTS` are present on the module but unused. See
[07 — Remote Control](07-remote-control.md) for baud rate and the JSON protocol.

---

## 2.3b Verified on hardware

Measured on a real board (`./pg run probe`), not inferred:

| Claim | Method | Result |
|---|---|---|
| GP2 `DSR`, GP3 `DSL` have external pull-ups, active-low | held high against internal 60 K pull-down | ✅ confirmed |
| GP15 `Echo` idles low | pull test | ✅ confirmed driven low |
| GP4 buzzer has a 10 K pull-down | pull test | ✅ confirmed |
| GP5 IR has a 4.7 K pull-up | pull test | ❌ **refuted** — weak pull only |
| GP26 divider is ×2 | 2.127 V at pin → 4.25 V | ✅ confirmed (×3 gives an impossible 6.38 V) |
| TLC2543 on GP6/7/27/28, inputs A0–A4 | read all 11 channels | ✅ A0–A4 carry signal; A5–A10 float |
| TLC2543 is pipelined, `value[1:]` is right | two back-to-back A0 reads | ✅ `508` then `959` |
| GP14/GP15 ultrasonic | 20 pings | ✅ 20/20 echoes |
| RP2350 has 12 PIO state machines | allocate SM 0–15 | ✅ 0–11 accepted, 12–15 rejected |
| Core 1 usable and idle | `_thread` | ✅ confirmed |
| Motors GP16–21 | **not tested** — no motion permitted this session | ⏸ pending |

## 2.4 Resource budget

| Resource | Used by the chassis | Left for you |
|---|---|---|
| GPIO | **all 26** | 0 |
| PWM slices | 2 (motors) | 6 |
| UART | UART0 (Bluetooth) | UART1 — but its pins are taken |
| SPI | SPI1 (LCD) | SPI0 — pins taken |
| I²C | none on V2 (V1 used I²C1) | both — **pins taken** |
| ADC channels | ADC0 (battery), ADC4 (temp) | ADC1/ADC2 pins taken by TLC2543 |
| **PIO state machines** | **2** — SM0 = WS2812, SM1 = TLC2543, both in **PIO0** | 10 of 12 (RP2350 has 3 PIO blocks × 4) |
| Cores | 1 (all demos are single-core) | **Core 1 is completely idle** |

The two genuinely underused resources on this platform are **PIO** and **core 1**.
Both got substantially bigger with the RP2350 upgrade and neither is touched by any
shipped demo.

> ⚠️ The two PIO programs hardcode absolute state-machine indices — `StateMachine(0,…)`
> for WS2812 and `StateMachine(1,…)` for the line sensor. They coexist because the
> numbers differ, but if you add a third PIO peripheral, pick an explicit unused index
> (4–11 map to PIO1/PIO2 on RP2350) rather than letting them collide.
