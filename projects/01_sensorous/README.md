# 01_sensorous

Measure everything this robot can measure, and show it. The line array, both IR
obstacle sensors, the ultrasonic ranger, battery voltage, die temperature and
the IR receiver — across six pages on the 1.14" LCD, mirrored to the four RGB
LEDs, with one JSON Lines record per second on the serial link.

**No radio.** The JDY-32 Bluetooth module is the only transceiver on this board
and it is deliberately never touched — no UART0 traffic, no pairing, nothing
transmitted.

**The motors are never driven.** GP16–GP21 are untouched and `board.estop()`
runs on the way out.

## Run

### Standalone — the normal way to use it

```zsh
./pg install sensorous
```

Installs as `main.py`, so it starts on every power-up and runs **forever** with
no computer attached. Unplug USB, flip the chassis switch, and it goes.
Verified: 8 telemetry records in 8 s with no REPL attached, uptime climbing
across a hard reset.

To stop it again:

```zsh
./pg stop && ./pg uninstall
```

### Tethered — while developing

```zsh
./pg run sensorous 60
```

Stops itself a few seconds before the host cap (via `PG_RUN_SECS`) so the mount
closes cleanly — see [Clean exit](#clean-exit). It also paints a **STOPPED**
card on the panel when it finishes, because the ST7789 holds its last frame
forever and a finished run otherwise looks exactly like a crash.

## Unattended behaviour

Built to survive with nobody watching:

| Event | What happens |
|---|---|
| Runs out of time (tethered) | STOPPED card, LEDs breathe blue three times, clean return |
| **Any unhandled exception** | `estop()`, a **FAULT** card naming the exception, LEDs flash red, 5 s pause, **restarts itself** — restart counter shown on screen |
| Ctrl-C | prints `interrupted`, `estop()`, exits for the human |
| Power-up | `main.py` autoruns, no host needed |

The fault path is tested by injecting a deliberate exception; it recovered and
restarted three times in 30 s without intervention.

## Pages

Any key on the IR remote steps to the next page and restarts the dwell timer;
with no remote it auto-advances every 6 s. Either way the page moves by one, so
an unfamiliar remote still works — there is no per-key map to remember.

| # | Page | Shows |
|---|---|---|
| 1 | **OVERVIEW** | battery + bar, die temp, distance + bar, obstacle L/R, line centroid + 5 mini bars, IR frame count |
| 2 | **LINE ARRAY** | per-channel raw / session min / session max, bar each, centroid |
| 3 | **RANGE** | now / median / min / max, ping and timeout counts, full-width history chart |
| 4 | **POWER** | volts, percent, raw ADC, volts at the pin, divider, die temp |
| 5 | **INPUTS** | obstacle state + edge counts per side, IR frame count, last six codes |
| 6 | **SYSTEM** | firmware, clock, heap, flash free, sample count, read/frame ms, spare ADC channels |

## What it reads

| Sensor | Pins | Notes |
|---|---|---|
| Line array, 5 ch | GP6/7/27/28 (TLC2543 A0–A4) | 12-bit, shifted to 0–1023 |
| Spare ADC, 6 ch | TLC2543 A5–A10 | nothing is wired to them; sampled anyway because "all metrics" means all of them |
| IR obstacle L/R | GP3 / GP2 | active LOW; rising-edge counters |
| Ultrasonic | GP14 / GP15 | `sonar.read()`, timeout-guarded |
| Battery | GP26 / ADC0 | ×2 divider, verified against a full 14500 cell |
| Die temperature | ADC ch 4 | uncalibrated, trend only |
| IR receiver | GP5 | NEC, decoded inline |

## Serial output

One record per second, JSON Lines — the same shape the original Sensorous wrote
to an SD card, except this board has no card, so it goes to the serial link:

```json
{"t":"sensor","up":34,"line":[1011,1016,1021,1003,1023],"lo":[...],"hi":[...],
 "dist":16.2,"pings":358,"to":0,"dsl":0,"dsr":0,"trig_l":1,"trig_r":1,
 "v":4.268,"pct":100,"raw":42378,"temp":23.3,"keys":0,"read":7,"frame":114,"heap":394208}
```

`dsl`/`dsr` are **raw pin levels**, so `0` means an obstacle is detected.
Capture a session with `./pg run sensorous 120 | tee run.jsonl`.

## Measured performance

| | |
|---|---|
| Sampling (`read`) | 5–7 ms |
| Whole frame (`frame`) | 90–114 ms → **~9–11 fps** |
| LCD blit alone | 78 ms — 70–85 % of the frame |
| Per-page render | 3–6 ms, except SYSTEM at 25 ms (`statvfs` + `gc.collect`) |

The blit dominates. If this ever needs to be faster, the fix is partial-window
updates or moving the blit to core 1 — not faster sampling.

## Clean exit

`pg run` injects `PG_RUN_SECS`, and this app returns on its own when it expires.
That is not cosmetic: hard-killing `mpremote mount` leaves the board blocked
inside the remote-filesystem protocol, with the serial port present but the REPL
silent. Recovery is `./pg unwedge`, and failing that the RESET button.

## Colours are unverified

The vendor ST7789 driver's constants are not textbook RGB565 — its `GREEN` is
`0x001F`, which is pure blue in standard RGB565. Only black and white here are
certain; everything else uses the driver's own names, and the exact hues have
not been checked against the panel. See `docs/06` §6.7.

## Known-open

The line array reads near full scale on every channel and barely moves, which
means the emitters are dark or the array is nowhere near a surface. The
polarity question in `docs/06` §6.2 is still unsettled — `./pg run validate`
resolves it.
