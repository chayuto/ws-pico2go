# 12 — CLI Workflow (no IDE)

Thonny is not required, and for this project it's actively the wrong tool. This page
is the replacement.

## 12.1 Why not Thonny

| | Thonny | `mpremote` + this repo |
|---|---|---|
| Where the code lives | **On the board.** You "Save as → device" and the device copy is the real one. | **In this repo.** The board is disposable. |
| Version control | None. A wipe or a reflash loses your work. | `git` — normal diffs, history, branches |
| Running a script | Click Run | `./pg run <app>` |
| Iterating | Re-save to device each time | `mpremote mount` serves this repo live — **no copy, no flash write** |
| Can Claude Code see it? | **No.** GUI-only; output is in a window I can't read. | **Yes.** Every operation is a shell command with readable output. |
| Emergency stop | Click Stop and hope | `./pg stop` kills motor PWM + direction pins directly |

The `mount` feature is the one that matters: `mpremote mount shared/lib run projects/x.py`
mounts this repo's `shared/lib` as the board's filesystem over the serial link and runs
your app against it. Edit a file, run again — **nothing is ever written to the board's
flash** until you deliberately `./pg install`.

## 12.2 Install once

```sh
brew install mpremote picotool coreutils
```

| Tool | Why |
|---|---|
| `mpremote` | Everything MicroPython: mount, run, exec, filesystem, REPL |
| `picotool` | UF2 flashing that bypasses Finder entirely; board info; force-BOOTSEL |
| `coreutils` | Provides `gtimeout`, so `./pg run` can cap a runaway loop |

`brew install`, not `pip3` — your Homebrew Python is PEP 668 externally-managed and
will refuse.

## 12.3 Repo layout

```
ws-pico2go/
├── pg                  # the only command you need
├── src/
│   ├── lib/            # device modules — mounted by `pg run`, deployed by `pg sync`
│   │   ├── board.py    #   ← pin map, single source of truth + estop()
│   │   ├── sonar.py    #   ← ultrasonic that cannot hang
│   │   ├── Motor.py    #   ← vendor drivers, original filenames kept
│   │   ├── ws2812.py   #      so every vendor demo and doc still applies verbatim
│   │   ├── ST7789.py
│   │   └── TRSensor.py
│   └── apps/           # runnable programs
│       ├── selftest.py     # bring-up check, never moves the robot
│       ├── sensors.py      # live readout, never moves the robot
│       └── drive_check.py  # MOVES — wheels off the ground
├── ref/             # Waveshare's originals + schematic (gitignored; `pg fetch`)
└── docs/               # 01–12
```

**Vendor filenames are kept exactly** (`Motor.py`, not `motor.py`) so the wiki, the
demos and docs 01–11 all still apply word for word — and because macOS is
case-insensitive, so `motor.py` vs `Motor.py` would be a trap.

## 12.4 The commands

```
SETUP
  ./pg doctor              host tools, serial port, BOOTSEL state, board, repo
  ./pg devs                list serial ports
  ./pg fetch               (re)download Waveshare demos + schematic
  ./pg bootsel             enter BOOTSEL without touching the buttons
  ./pg flash [file.uf2]    flash firmware (defaults to the vendor MicroPython)

DEVELOP — nothing is written to the board's flash
  ./pg run <app> [secs]    run with shared/lib mounted; auto E-STOP on exit
  ./pg exec '<code>'       one-liner
  ./pg eval '<expr>'       print an expression
  ./pg repl                interactive REPL (for you; Ctrl-] exits)

DEPLOY
  ./pg sync                copy shared/lib/*.py to the board
  ./pg install <app>       sync + install as main.py (runs on power-up)
  ./pg uninstall           remove main.py
  ./pg wipe                delete every file on the board

INSPECT
  ./pg ls | ./pg cat <f> | ./pg rm <f> | ./pg df | ./pg info

SAFETY
  ./pg stop                EMERGENCY STOP
```

`./pg run <app>` resolves `<app>` from `./`, then `projects/`, then
`ref/PicoGo_Code V2/` — so vendor demos work too:

```sh
./pg run Line-Tracking2.py 30
```

## 12.5 First bring-up

```sh
./pg doctor                       # before you even plug anything in
```

Then, with USB-C connected and the **chassis power switch ON**:

```sh
# 1. flash MicroPython  (hold BOOT, tap RESET, release RESET then BOOT)
./pg flash

# 2. prove the whole stack works — this never drives the motors
./pg run selftest

# 3. read the line array over white / black tape / air (docs/06 §6.2)
./pg run sensors 60

# 4. wheels off the ground, then:
./pg run drive_check
```

## 12.6 The development loop

```sh
$EDITOR projects/my_follower.py     # or: code .
./pg run my_follower 15             # runs against shared/lib, no flash write
# read the output, edit, repeat
```

When it's good:

```sh
./pg install my_follower            # copies libs + sets main.py
# unplug USB, switch ON — it runs standalone
```

To take it back:

```sh
./pg stop && ./pg uninstall
```

## 12.7 Safety — this is a robot, not a blinking LED

`./pg run` installs an **E-STOP trap**. Whether the app finishes, throws, hits the
timeout, or you hit Ctrl-C, `pg` forces motor PWM to zero and all four TB6612 direction
pins low before returning. That behaviour is hardcoded in `pg` with literal pin numbers,
so it still works when the board's filesystem is empty or your code is broken.

```sh
./pg stop        # anytime, from any terminal
```

Every app in `projects/` also calls `board.estop()` in a `finally:` block. Please keep
that habit — a timeout-killed script that leaves 100 % duty on both motors will find
the edge of your desk.

The default `./pg run` cap is **20 seconds**. Raise it deliberately:
`./pg run sensors 120`.

## 12.8 Handy one-liners

```sh
# Battery voltage, right now
./pg eval "__import__('board') and None"
./pg exec 'import board
from machine import ADC, Pin
v = ADC(Pin(board.BAT_ADC)).read_u16()*3.3/65535*board.BAT_DIVIDER
print("{:.2f} V".format(v))'

# Are the IR obstacle sensors triggered?
./pg exec 'from machine import Pin
print("L", Pin(3, Pin.IN).value(), "R", Pin(2, Pin.IN).value())'

# One ultrasonic ping
./pg exec 'import sonar; print(sonar.read_median())'

# What is on the board's flash?
./pg ls && ./pg df

# Capture an IR remote key code
./pg exec 'from machine import Pin
import utime
p = Pin(5, Pin.IN)
print("press a key...")
# (paste getkey() from vendor IRremote.py, or use projects once written)'
```

## 12.9 VS Code, when you want it

VS Code here is **just a text editor**. There's no MicroPython extension to install and
nothing to "connect". `.vscode/settings.json` in this repo already:

- adds `shared/lib` to the Python analysis path, so `import board` resolves;
- silences `reportMissingImports` for `machine`, `rp2`, `utime`, `framebuf`;
- excludes `ref/` from search.

Optional autocomplete for the MicroPython API:

```sh
python3 -m venv .venv && .venv/bin/pip install -U micropython-rp2-rpi_pico2-stubs
# then point python.analysis.extraPaths at the installed stubs
```

Nice to have, not needed. Run everything through `./pg`.

## 12.10 What Claude Code can and can't do here

**Can** — because every step is a shell command with readable output:
- run `./pg doctor`, read the result, and tell you what's wrong;
- write and edit apps in `projects/`;
- `./pg run` an app and read its printed output to debug;
- `./pg exec` probes to interrogate the hardware live;
- tune the line-follower gains by editing, running and reading the numbers back;
- flash firmware, deploy, install, and stop the robot.

**Can't:**
- see the LCD, the RGB LEDs, or the robot moving — anything visual needs your eyes,
  which is why `selftest` prints *"LOOK AT THE SCREEN"*;
- press BOOT/RESET (though `./pg bootsel` avoids that when firmware is running);
- fit batteries, flip the power switch, or trim the two obstacle-sensor potentiometers;
- catch the robot before it hits the floor. **Wheels off the ground until you trust it.**

> ⚠️ **Untested against hardware.** Everything in `pg` and `src/` was written from the
> schematic and the vendor sources; the host-side commands are verified, but nothing has
> been run against a real Pico2Go yet. Expect to fix something on first contact — start
> with `./pg doctor`, then `./pg run selftest`.
