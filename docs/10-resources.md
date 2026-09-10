# 10 — Resources

Every source used to build these notes, plus everything worth bookmarking.

---

## Primary — Waveshare

| Resource | URL |
|---|---|
| **Pico2Go wiki** | https://www.waveshare.com/wiki/Pico2Go |
| **Pico2Go product page** | https://www.waveshare.com/pico2go-kit.htm |
| **PicoGo wiki** (same hardware, more material) | https://www.waveshare.com/wiki/PicoGo |
| PicoGo product page | https://www.waveshare.com/picogo.htm |
| **RP2350-Plus wiki** | https://www.waveshare.com/wiki/RP2350-Plus |
| RP2350-Plus product page | https://www.waveshare.com/rp2350-plus.htm |
| Support ticket system | https://service.waveshare.com/ (9 AM–6 PM GMT+8, Mon–Fri, 1–2 working day reply) |

## Schematics

| Revision | URL |
|---|---|
| **V2 — current boards** | https://files.waveshare.com/upload/8/8b/PicoGo_Schematic_V2.pdf |
| V1 — pre-Sept 2022 | https://files.waveshare.com/upload/8/8f/PicoGo_Schematic.pdf |

The V2 schematic is the authoritative pinout source. It's a single sheet; the pin map
in [02](02-pinout-reference.md) was extracted from it net by net.

## Demo code & firmware

| Resource | URL |
|---|---|
| **PicoGo Demo V2** (use this) | https://files.waveshare.com/wiki/PicoGo/PicoGo_Code_V2.zip |
| PicoGo Demo V1 | https://files.waveshare.com/upload/0/00/PicoGo_Code.zip |
| MicroPython RP2350A (Waveshare) | https://files.waveshare.com/wiki/RP2350-Plus/WAVESHARE-RP2350A-Board.zip |
| MicroPython RP2350B | https://files.waveshare.com/wiki/RP2350-Plus/WAVESHARE-RP2350B-Board.zip |
| MicroPython RP2040 | https://files.waveshare.com/wiki/RP2350-Plus/WAVESHARE-RP2040-Board.zip |
| MicroPython official downloads | https://micropython.org/download/?vendor=Raspberry%20Pi |
| Thonny 3.3.3 (vendor-pinned, 2021) | https://files.waveshare.com/wiki/common/Thonny-3.3.3.zip |
| **Thonny current** (use this instead) | https://thonny.org/ |
| PicoGo Android app (`base.apk`) | https://files.waveshare.com/wiki/PicoGo/Base.zip |

### One-liner to grab everything

```sh
mkdir -p ref && cd ref
curl -LO https://files.waveshare.com/wiki/PicoGo/PicoGo_Code_V2.zip
curl -LO https://files.waveshare.com/upload/8/8b/PicoGo_Schematic_V2.pdf
curl -LO https://files.waveshare.com/wiki/PicoGo/Base.zip
unzip -o PicoGo_Code_V2.zip
```

## Component datasheets

| Part | Role | URL |
|---|---|---|
| **IP5306** | Battery PMIC / boost / gauge | https://files.waveshare.com/upload/b/b5/IP5306_EN.pdf |
| **S8261** | Li-ion protection | https://files.waveshare.com/upload/8/8d/S8261.pdf |
| **TB6612FNG** | Dual H-bridge | https://files.waveshare.com/upload/6/62/TB6612FNG_datasheet_en.pdf |
| **LM393** | Dual comparator | https://files.waveshare.com/upload/b/b8/Lm393.pdf |
| PCA9685 | (listed by vendor; not on the V2 schematic) | https://files.waveshare.com/upload/6/68/PCA96_datasheet.pdf |

**Not listed by Waveshare but present on the V2 board — look these up yourself:**
`TLC2543` (TI, 12-bit 11-ch serial ADC), `ST7789` (Sitronix LCD controller),
`WS2812B` (Worldsemi addressable RGB), `ITR20001/T` and `ST188` (reflective IR),
`JDY-32` (dual-mode BT), `AO4406A` / `AO3401` / `SI2305` (MOSFETs), `S8050` (NPN),
`MP28164` and `ETA6096` (on the RP2350-Plus).

## Raspberry Pi official

| Resource | URL |
|---|---|
| RP2350 / Pico 2 documentation hub | https://www.raspberrypi.com/documentation/microcontrollers/ |
| Pico VS Code extension announcement | https://www.raspberrypi.com/news/pico-vscode-extension/ |
| **RP2350 A4 stepping & the E9 fix** | https://www.raspberrypi.com/news/rp2350-a4-rp2354-and-a-new-hacking-challenge/ |
| pico-examples (C) | https://github.com/raspberrypi/pico-examples/ |
| pico-micropython-examples | https://github.com/raspberrypi/pico-micropython-examples |
| MicroPython rp2 port (build your own firmware) | https://github.com/micropython/micropython/tree/master/ports/rp2 |

## Third-party projects — the good stuff

### `jblanked/Waveshare` ⭐ most useful
https://github.com/jblanked/Waveshare — *"Drivers and examples for various Waveshare
devices"*, C, ~10 stars, actively maintained (mid-2026).

The `PicoGo/` tree is a complete rewrite of the robot's software:

| Path | What |
|---|---|
| `PicoGo/src/SDK/` | Pico-SDK C drivers: `motor`, `battery`, `lcd` (ST7789 + PIO + 5 font sizes), `tracking_sensor` (PIO TLC2543), `ultrasonic_sensor`, `infrared`, `bluetooth` |
| `PicoGo/src/MicroPython/` | The same drivers as **native MicroPython C modules** (`waveshare_motor`, `waveshare_lcd`, …) |
| `PicoGo/builds/MicroPython/Waveshare-PicoGo.uf2` | Prebuilt MicroPython **with those modules baked in**, built for `BOARD=RPI_PICO2` — i.e. it runs on your RP2350-Plus |
| `PicoGo/examples/` | Python, Arduino and SDK examples, including the full IR key-code table |
| `PicoGo/tools/micropython.sh` | The build script, if you want to compile it yourself |

Its headers were the independent cross-check for every pin in
[02 — Pinout Reference](02-pinout-reference.md).

Companion video: https://www.youtube.com/watch?v=0yNG6QDzCWk
(*"Revamping the PicoGo RP2350 Robot with Epic Custom Firmware!"* — linked from the
Pico2Go wiki itself.)

### `MKesenheimer/pico-go`
https://github.com/MKesenheimer/pico-go — *"Code for the Pico-Go robot written purely
in C++"*. The upstream that jblanked's SDK drivers were translated from.

### `earlephilhower/arduino-pico`
https://github.com/earlephilhower/arduino-pico — Arduino core for RP2040/RP2350.
Ships a **`waveshare_rp2350_plus`** variant; its `pins_arduino.h` is the authoritative
source for the RP2350-Plus's `PIN_LED = 25`.

### `jblanked/Picoware`
https://github.com/jblanked/Picoware — broader open-source firmware for Pico-class
devices (PicoCalc, Cardputer, several Waveshare RP2350 boards). Not PicoGo-specific but
the same author and useful patterns.

### Waveshare's own GitHub
https://github.com/waveshareteam/Pico_MircoPython_Examples — general Pico MicroPython
examples (note the typo in the repo name).

---

## macOS tooling

| Tool | Install | Purpose |
|---|---|---|
| Thonny 5.x | `brew install --cask thonny` | *Optional.* GUI IDE. This repo uses `./pg` instead — see [12](12-cli-workflow.md). |
| `mpremote` | `brew install mpremote` | **The core tool.** `mount` serves this repo to the board live; `run`/`exec` need no flash write. |
| `picotool` | `brew install picotool` | Reliable UF2 flashing, board info, force-BOOTSEL |
| Arduino IDE | `brew install --cask arduino-ide` | |
| `arduino-cli` | `brew install arduino-cli` | Headless Arduino builds |
| Pico VS Code extension | VS Code marketplace, publisher `raspberry-pi` | Manages its own SDK in `~/.pico-sdk`; needs VS Code ≥ 1.105.1 and `xcode-select --install` |

- Pico VS Code extension source: https://github.com/raspberrypi/pico-vscode
- **The macOS UF2 / Finder problem** (why you use `cp -X` or `picotool`):
  https://www.raspberrypi.com/news/the-ventura-problem/

See [11 — macOS Setup](11-macos-setup.md) for the full walkthrough.

## Background reading

| Topic | Where |
|---|---|
| RP2350 E9 erratum, original discovery | https://hackaday.com/2024/09/04/the-worsening-raspberry-pi-rp2350-e9-erratum-situation/ |
| E9 redefined as leakage current | https://hackaday.com/2024/09/20/raspberry-pi-rp2350-e9-erratum-redefined-as-input-mode-leakage-current/ |
| E9 fixed in A4 stepping | https://www.cnx-software.com/2025/07/29/raspberry-pi-rp2350-a4-stepping-fixes-e9-gpio-erratum-9-glitching-bugs-introduces-2mb-flash-variants/ |
| E9 discussion thread | https://forums.raspberrypi.com/viewtopic.php?t=375631 |
| Waveshare's RP2350 USB-C board family | https://www.cnx-software.com/2024/11/28/waveshare-rp2350-usb-c-development-boards-castellated-design-battery-support-built-in-ethernet-port/ |
| JDY-32 dual-mode BT manual | https://manuals.plus/bluetooth-module/dual-mode-bluetooth-spp-ble-module-jdy-32-bluetooth-manual |
| MicroPython `machine` / `rp2` class references | linked from the RP2350-Plus wiki, "MicroPython Series Tutorials" |

## Where to buy / compare

Waveshare direct (~US$50.99), plus The Pi Hut, Botland, RobotShop, Micro Robotics,
Amazon and AliExpress carry the PicoGo/Pico2Go line. Reseller listings are also the
only published source for the chassis dimensions (~110 × 45 mm, ~370 g shipped).

---

## Search tips

- **Search for "PicoGo", not "Pico2Go".** Same hardware, ~100× the material.
- For the controller board, search **"RP2350-Plus"** or **"Waveshare RP2350 Plus"**.
- For firmware questions, **"Raspberry Pi Pico 2"** / **"RP2350"** answers apply directly.
- The Waveshare wiki is served from `waveshare.com/wiki/…`; downloads live on
  `files.waveshare.com`. `WebFetch`-style tools get 403'd by the wiki — fetch with a
  normal browser User-Agent instead.
