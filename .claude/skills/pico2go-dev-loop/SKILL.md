---
name: pico2go-dev-loop
description: The Pico2Go/PicoGo robot development workflow driven entirely from the terminal via ./pg (mpremote + picotool), with no IDE. Use whenever running, deploying, debugging, or stopping code on the robot; when the user says run/flash/deploy/install/stop/probe/selftest; when a board command fails or the board seems unresponsive; or when writing new device code for this repo. Also the entry point for any Pico2Go question - it routes to the other pico2go-* skills.
---

# Pico2Go dev loop

Source of truth is **this repo**, not the board. `./pg run` serves `shared/lib` over the
serial link with `mpremote mount`, so **nothing is written to the board's flash** until
an explicit `./pg install`.

## Before anything else

```sh
./pg doctor        # host tools, serial port, USB state, board, repo
```

Read its output before diagnosing anything. It distinguishes: no port / in BOOTSEL /
enumerated-but-no-CDC-node / running non-MicroPython firmware / healthy.

## Commands

| Task | Command |
|---|---|
| Unwedge after a killed run | `./pg unwedge` |
| Run an app | `./pg run <app> [secs]` — default cap 20 s, E-STOP on exit |
| One-liner probe | `./pg exec '<code>'` |
| Expression | `./pg eval '<expr>'` |
| Deploy libs | `./pg sync` |
| Standalone | `./pg install <app>` → writes `main.py` |
| Undo standalone | `./pg stop && ./pg uninstall` |
| Files | `./pg ls` · `./pg cat <f>` · `./pg rm <f>` · `./pg df` |
| **Emergency stop** | `./pg stop` |

`./pg run` resolves apps from `./`, then `projects/`, then `ref/PicoGo_Code V2/`.

## Rules for this robot

1. **Never drive the motors without confirming the wheels are off the ground.** If the
   user is away or hasn't confirmed, do not touch GP16–GP21 at all.
2. Every app ends with `board.estop()` in a `finally:` block. Keep that habit.
3. `./pg run` already traps EXIT/INT/TERM and forces motor PWM to 0 and GP17/18/19/20/4
   low, using **hardcoded** pin numbers so it works even with a broken filesystem.
4. Default runtime cap is 20 s. Raise deliberately: `./pg run sensors 120`.
5. **Long-running apps must stop themselves.** `pg run <app> <secs>` injects a global
   `PG_RUN_SECS` a few seconds below the host cap; loops should read it and `return`.
   A hard-killed `mpremote mount` **wedges the board** — port present, REPL silent — and
   only the RESET button clears it. `./pg unwedge` tries first. See `pico2go-unattended`.
6. **The chassis power switch must be ON** or the 5 V rail is down: motors, WS2812 RGB
   and the ST188 IR obstacle front-end all die. USB alone only supplies 3V3.

## Writing device code

- Put importable modules in `shared/lib/`, runnable programs in `projects/`.
- Vendor driver filenames are kept **exactly** (`Motor.py`, `ST7789.py`, `TRSensor.py`,
  `ws2812.py`) so vendor docs apply verbatim. macOS is case-insensitive — don't rename.
- Import pin numbers from `board`, never hardcode them: `import board; Pin(board.DSL)`.
- Use `sonar.read()`, not the vendor's `dist()` — the vendor version hangs forever on a
  missed echo.

## Debugging without a human present

`./pg exec` is the workhorse. Examples that need no physical interaction:

```sh
# Is a pin externally pulled, or floating?
./pg exec 'from machine import Pin
import utime
for name, p in (("DSL",3),("DSR",2),("IR",5)):
    a=Pin(p,Pin.IN,Pin.PULL_DOWN); utime.sleep_ms(20); pd=a.value()
    b=Pin(p,Pin.IN,Pin.PULL_UP);   utime.sleep_ms(20); pu=b.value()
    print(name, "pd",pd,"pu",pu, "=> external pull-up" if pd else "floating/driven low")'

# Full autonomous validation (never touches motors)
./pg run probe 120
```

`projects/probe.py` is the reference for what can be validated with nobody in the room.

## Routing

| Topic | Skill |
|---|---|
| pin numbers, electrical, what's connected | `pico2go-hardware` |
| firmware, BOOTSEL, bricked board, USB | `pico2go-flashing` |
| motors, driving, turning | `pico2go-motion` |
| line array, calibration, PID | `pico2go-line-following` |
| ultrasonic, IR obstacle, battery, LCD, RGB, buzzer | `pico2go-sensors-io` |
| IR remote, Bluetooth | `pico2go-remote-control` |
| screen layout, charts, fonts, colours | `pico2go-display-ui` |
| autorun, standalone, fault recovery, the mount wedge | `pico2go-unattended` |

Long-form reference lives in `docs/01`–`docs/12`.
