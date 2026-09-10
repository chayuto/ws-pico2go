---
name: pico2go-unattended
description: Running Pico2Go code standalone with no computer attached - installing to main.py, autorun on power-up, fault recovery, clean exits, and the mpremote mount wedge that only the RESET button clears. Use when code must keep running while nobody is watching, when deploying with pg install, when a long-running app must stop itself, when the board goes silent after a killed run, or when verifying that something really is running on its own.
---

# Unattended operation

## Deploy

```zsh
./pg install <app>        # sync shared/lib + copy the app to :main.py
./pg stop && ./pg uninstall
```

MicroPython autoruns `main.py` on every power-up. Unplug USB, flip the **chassis power
switch**, and it goes — no host, no REPL.

## ⚠️ Verify standalone the right way

**Attaching `mpremote` proves nothing.** Entering the raw REPL *suppresses* `main.py`,
so a board that would have run fine looks idle, and a board that is running gets
interrupted by the act of checking.

Read the serial line **raw** instead:

```python
import serial, time
s = serial.Serial('/dev/cu.usbmodem3101', 115200, timeout=1)
time.sleep(0.5); s.reset_input_buffer()
buf = b''; t0 = time.time()
while time.time() - t0 < 8:
    buf += s.read(2048)
s.close()
print(buf.decode('utf-8', 'replace'))
```

Look for telemetry arriving and **uptime climbing across a reset**. Use the interpreter
`mpremote` ships with — it already has pyserial:
`$(head -1 $(command -v mpremote) | sed 's|^#!||')`.

## ⚠️ The mount wedge — the failure that costs the most time

A hard-killed `mpremote mount` leaves the device blocked inside the remote-filesystem
protocol. Symptom: **the serial port still exists, but the REPL never answers.**

Every software recovery was tried and **all of them failed**: `mpremote soft-reset`, a
Ctrl-C storm over raw serial, Ctrl-B then Ctrl-C+Ctrl-D, DTR/RTS toggling, a 1200-baud
touch, and `picotool reboot -f`. **Only the physical RESET button cleared it.**

```zsh
./pg unwedge     # tries the serial recovery, then tells you to press RESET
```

### Prevent it — apps stop themselves

`pg run <app> <secs>` injects a global `PG_RUN_SECS` set a few seconds *below* the host
cap, so the app returns cleanly and the mount closes properly. The host timeout becomes
a backstop rather than the normal path:

```python
try:
    limit_ms = int(PG_RUN_SECS) * 1000    # injected by pg run
except NameError:
    limit_ms = 0                          # 0 = run until interrupted (main.py case)
...
if limit_ms and utime.ticks_diff(utime.ticks_ms(), started) > limit_ms:
    end_card(lcd, s, "TIME LIMIT")
    return
```

When installed as `main.py` nothing is injected, `limit_ms` is 0, and it loops forever —
which is exactly what standalone wants.

## Fault recovery — a fault must not leave a dead robot

Wrap the entry point so any unhandled exception stops the motors, **says what happened
on the panel**, and restarts:

```python
restarts = 0
while True:
    try:
        main()
        break                       # clean finish stays stopped
    except KeyboardInterrupt:
        break                       # a human is present
    except Exception as e:
        restarts += 1
        board.estop()               # motors off FIRST
        crash_card("{}: {}".format(type(e).__name__, e), restarts)
        sys.print_exception(e)
        # flash the LEDs red
        utime.sleep(5)
board.estop()
```

**Test the fault path by injecting a real exception**, don't assume it works. Doing so
caught three clean restarts in 30 s.

## Make every state visible

An unattended robot cannot answer questions, so the panel and LEDs must:

| State | Panel | LEDs |
|---|---|---|
| Running | live pages | live data mirror |
| Clean finish | **STOPPED** card — reason, counters, restart command | breathe blue ×3 |
| Fault | **FAULT** card — exception text + restart number | flash red |
| Idle after finish | the card stays up | dark |

The ST7789 holds its last frame forever, so a program that just ends leaves a frozen
screen that reads as a crash. This was reported as a hang once when the REPL was
answering the whole time. See `pico2go-display-ui`.

## Checklist before leaving a board running

1. `./pg run <app> <secs>` tethered first — no exceptions, clean exit.
2. Fault path exercised with an injected exception.
3. `./pg install <app>`, then hard reset and confirm via **raw serial**.
4. Battery charged — check the reading with the **motors stopped**.
5. Chassis power switch **ON**, or the 5 V rail is down and half the robot is dead.
6. If it drives, wheels off the ground unless a human has confirmed otherwise.
