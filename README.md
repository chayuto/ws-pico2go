# ws-pico2go

Workspace for the **Waveshare Pico2Go** mobile robot — the PicoGo chassis driven by an
**RP2350-Plus** (RP2350A, Raspberry Pi Pico 2 compatible) instead of a Pico.

Built with an **agentic-first, no-IDE workflow** — MicroPython driven entirely from the
terminal through a single `./pg` command, with [Claude Code](https://claude.ai/code) as
the primary agent. Pin map, safety rules, vendor gotchas and everything measured on real
hardware live in `CLAUDE.md` and `.claude/skills/`, so the agent has full context from
the first message of every session.

Waveshare publishes **no pinout** for this robot and its setup guide is Windows- and
Thonny-only. Both problems are solved here.

---

## Board

| Feature | Detail |
|---|---|
| MCU | RP2350A, **rev A4** (erratum E9 fixed in silicon), dual Cortex-M33 **or** dual Hazard3 RISC-V, 150 MHz |
| Memory | 520 KB SRAM, 4 MB flash (3,072 KB filesystem) |
| Drive | 2 × N20 metal-gear motors, TB6612FNG H-bridge — **no encoders** |
| Line sensing | 5 × ITR20001/T → TLC2543 12-bit serial ADC, read over **PIO** |
| Obstacle | 2 × ST188 + LM393 comparator, trim pots on the underside |
| Ranging | HC-SR04-class ultrasonic, 3V3 |
| Display | 1.14" ST7789 IPS, 240 × 135, SPI1 |
| Lighting | 4 × WS2812B (5 V rail) |
| Wireless | JDY-32 dual-mode Bluetooth (SPP + BLE) on UART0 |
| Power | 2 × 14500 Li-ion **in parallel**, IP5306 PMIC, charge-while-run |
| PIO | **12 state machines** — 2 used, 10 free |

---

## Projects

| Project | Description |
|---|---|
| [`selftest`](projects/selftest.py) | 11-check bring-up across every subsystem. **Never drives the motors.** Detects the power-switch-off case from the battery reading. |
| [`probe`](projects/probe.py) | Deep autonomous validation — external pull-up detection, all 11 TLC2543 channels, protocol pipelining proof, PIO capacity, LCD/WS2812 timing. Never touches GP16–21. |
| [`validate`](projects/validate.py) | Event-driven, guided. Waits for you; uses IR remote keys to label surfaces and settle the line-sensor polarity question. |
| [`sensors`](projects/sensors.py) | Live line array / obstacle / sonar / battery readout for calibration. |
| [`drive_check`](projects/drive_check.py) | Bounded motion test. **Wheels off the ground.** |

---

## Feature Domains

| Area | Details |
|---|---|
| MicroPython on RP2350 | `mpremote mount` dev loop, no flash writes, `main.py` autorun, PEP 668-safe tooling |
| PIO | TLC2543 serial-ADC bit-bang, WS2812 driver, 10 free state machines for encoders |
| Sensing | 12-bit reflectance array, PID line following, ultrasonic timing, comparator-based IR bumpers |
| Control | Differential drive, PD tuning, open-loop limits without encoders |
| Analog | Switched battery divider, median + exponential filtering, on-die temperature |
| Reverse engineering | Full pin map recovered from a schematic PDF by positional net extraction |
| Safety engineering | Hardcoded emergency stop that survives a broken filesystem, runtime caps, `finally:` discipline |

---

## Repo Structure

```
ws-pico2go/
├── pg                    # the CLI — every device operation goes through it
├── projects/             # runnable MicroPython apps
├── shared/lib/           # device modules: board.py (pin map), sonar.py, vendor drivers
├── ref/                  # Waveshare originals + schematic (gitignored)
│   └── factory/          #   factory firmware backup — committed, no download exists
├── docs/                 # 01–12 reference
├── CLAUDE.md             # Agent context — pin map, safety rules, verified facts
└── .claude/skills/       # One agent skill per subsystem
```

---

## Agent Skills (Claude Code)

Skills load automatically when a session touches the matching subsystem, so the agent
applies board-specific rules without being told every time — including the ones that
matter, like *never drive the motors without confirming the wheels are clear*.

| Skill | What it knows |
|---|---|
| `pico2go-dev-loop` | The `./pg` workflow, `mpremote mount`, debugging with no human present. Entry point — routes to the rest. |
| `pico2go-hardware` | Full pin map, 5 V vs 3V3 split, resource budget, V1/V2 board revisions, measured electrical facts |
| `pico2go-flashing` | BOOTSEL, `picotool`, factory-firmware recovery, macOS CDC-attach failures, Pico SDK / Arduino |
| `pico2go-motion` | TB6612 truth tables, pivot vs arc, brake vs coast, and the safety rules for an encoder-less robot |
| `pico2go-line-following` | TLC2543 pipelining, calibration, the `white_line` polarity trap, PD tuning order |
| `pico2go-sensors-io` | Non-blocking ultrasonic, IR trim pots, battery maths, ST7789 timing, WS2812, buzzer |
| `pico2go-remote-control` | NEC decoding + full key-code table, JDY-32 pairing/baud traps, JSON protocol, deadman timers |

---

## Requirements & Building

```zsh
brew install mpremote picotool coreutils   # not pip3 — Homebrew Python is PEP 668 managed

./pg doctor                 # host tools, serial port, USB state, board, repo
./pg flash                  # MicroPython (bundled in the Waveshare package)
./pg run selftest           # 11 checks, never drives the motors
./pg run <app> [secs]       # mounts shared/lib — no flash write, E-STOP on exit
./pg install <app>          # deploy as main.py, runs standalone on power-up
./pg stop                   # EMERGENCY STOP
```

`./pg run` serves `shared/lib` to the board over the serial link with `mpremote mount`,
so **nothing is written to the board's flash** until an explicit `./pg install`.

> ⚠️ **The chassis power switch must be ON.** 3V3 comes from USB, but **5 V comes from
> the batteries through the slide switch** and feeds the motors, RGB LEDs and IR
> obstacle emitters. Switch off + USB only ⇒ the MCU boots and the LCD works, but
> nothing moves. It fails silently, not loudly.

---

## Documentation

| # | Document | |
|---|---|---|
| 01 | [Hardware Overview](docs/01-hardware-overview.md) | Kit contents, BOM by subsystem, V1/V2 revisions |
| 02 | [Pinout Reference](docs/02-pinout-reference.md) | **The GPIO map Waveshare doesn't publish** |
| 03 | [Power & Battery](docs/03-power-and-battery.md) | Power tree, 14500 cells, sense-divider maths |
| 04 | [Toolchain & Firmware](docs/04-toolchain-and-firmware.md) | What Waveshare says (Windows-centric) |
| 05 | [Official Demos](docs/05-official-demos.md) | Every vendor file, dependencies, behaviour |
| 06 | [Sensors & Algorithms](docs/06-sensors-and-algorithms.md) | TLC2543 PIO protocol, PD loop, ultrasonic |
| 07 | [Remote Control](docs/07-remote-control.md) | NEC key-code table, Bluetooth JSON protocol |
| 08 | [Gotchas](docs/08-gotchas-and-known-issues.md) | 28 ranked traps, hardware-confirmed |
| 09 | [Extending the Platform](docs/09-extending-the-platform.md) | Gaps, GPIO trades, project ladder |
| 10 | [Resources](docs/10-resources.md) | Every download URL and datasheet |
| 11 | [macOS Setup](docs/11-macos-setup.md) | The Mac-native path Waveshare doesn't document |
| 12 | [CLI Workflow](docs/12-cli-workflow.md) | **Start here.** No IDE. |

---

## Hardware validation status

Validated on a real board (RP2350A **rev A4**, QFN60, chipid `5707f03baa9f57ed`) via
`./pg run selftest` and `./pg run probe`:

| Subsystem | Status |
|---|---|
| MicroPython 1.25.0 / RPI_PICO2 / 150 MHz / 12 PIO SMs / core 1 | ✅ confirmed |
| Battery sense GP26, **×2 divider** → 4.25 V | ✅ confirmed, ×3.0 refuted |
| Die temperature (RP2040 formula holds on RP2350) | ✅ 23.3 °C |
| TLC2543 line ADC — pins, A0–A4 mapping, pipelining | ✅ confirmed |
| Ultrasonic GP14/GP15 + the non-blocking timeout guard | ✅ 20/20 pings |
| GP2/GP3 external pull-ups, GP4 pull-down, GP15 idle-low | ✅ confirmed |
| LCD ST7789 — **77.8 ms/frame, not the 52 ms theory predicts** | ✅ measured |
| WS2812B (641 µs/update), buzzer, user LED | ⚠️ driven without error; needs eyes/ears |
| GP5 IR receiver — claimed 4.7 K pull-up | ❌ **refuted**, weak pull only |
| IR remote decode, IR obstacle triggering, line-sensor polarity | ⏸ needs a human |
| **Motors GP16–21** | ⏸ **deliberately never driven** |

---

## Sibling repos

Waveshare board workspaces built with the same agentic-first workflow. If a technique is
missing here, it is probably solved in one of the others.

| Repo | Board | Focus |
|---|---|---|
| [`ws-ESP32-C6-Touch-AMOLED-1.8`](https://github.com/chayuto/ws-ESP32-C6-Touch-AMOLED-1.8) | ESP32-C6-Touch-AMOLED-1.8 — RISC-V C6, 1.8" SH8601 AMOLED, IMU, codec | MCP canvas, BitChat BLE relay, baby-cry DSP, sensory toys, Govee monitor |
| [`ws-ESP32-S3-Touch-AMOLED-1.8`](https://github.com/chayuto/ws-ESP32-S3-Touch-AMOLED-1.8) | ESP32-S3-Touch-AMOLED-1.8 — Xtensa S3 + PSRAM, 1.8" CO5300 AMOLED, CST820 touch | verified board notes, ESP-IDF template, ESP-SR voice picture book |
| [`ws-ESP32-S3-CAM`](https://github.com/chayuto/ws-ESP32-S3-CAM) | ESP32-S3-CAM-GC2145 — Xtensa S3 + 8 MB PSRAM, GC2145 DVP camera, ES8311/ES7210 audio | camera + audio bring-up, YAMNet baby-cry detection |
| [`ws-esp32c6-lcd147-projects`](https://github.com/chayuto/ws-esp32c6-lcd147-projects) | ESP32-C6 + 1.47" ST7789 LCD — RISC-V C6, 172×320 LCD, Wi-Fi 6 | LVGL animations, Wi-Fi 6 tools, MCP servers |
| [`ws-pico2go`](https://github.com/chayuto/ws-pico2go) **(this repo)** | Pico2Go robot — RP2350A, TB6612 drive, TLC2543 line array, ST7789 | MicroPython robotics, PIO sensing, schematic reverse engineering |

---

## ## Provenance & confidence

Everything here is traceable. Claims are tagged in-line where it matters:

- **[schematic]** — read directly off the Pico2Go/PicoGo V2 schematic net list.
- **[code]** — read out of Waveshare's shipped MicroPython demos or `arduino-pico`.
- **[vendor]** — stated by the Waveshare wiki or product page.
- **[3rd-party]** — community projects, datasheets, reseller listings.
- **[inference]** — my conclusion from the above; verify before betting hardware on it.

Sources are collected in [10 — Resources](docs/10-resources.md).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
