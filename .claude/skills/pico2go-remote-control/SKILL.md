---
name: pico2go-remote-control
description: Remote-controlling the Pico2Go/PicoGo robot over infrared (NEC protocol, GP5) or Bluetooth SPP (JDY-32 on UART0, JSON protocol). Use for IR remote, NEC decoding, key codes, the Waveshare Android app, JDY-32/JDY-33 pairing, AT commands, baud-rate problems, or building a custom phone/desktop controller for this robot.
---

# Remote control

## Infrared — GP5

3-pin receiver, idle HIGH. **Measured: only a weak pull-up** (loses to the RP2350's
~60 K internal pulldown), so the schematic's "4.7 K external pull-up" was a
misattribution — it's likely the receiver's own internal ~30 K.

### NEC framing as the vendor decoder sees it

| Phase | Timing | Detection |
|---|---|---|
| Leader | 9 ms low | count ≤100 × 100 µs while low; reject if `count < 10` |
| Space | 4.5 ms high | count ≤50 × 100 µs |
| 32 bits | 0.56 ms mark, then 0.56 ms (0) or 1.69 ms (1) space | `count > 7` ⇒ bit is 1 |
| Check | `addr + ~addr == 0xFF` and `cmd + ~cmd == 0xFF` | returns the command byte |

Failed validation returns `"repeat"` (NEC repeat frames land here).

⚠ It is **blocking** — ~67 ms per frame with nothing else running. Better: hang the same
decoder off a **falling-edge pin IRQ** with `Pin.PULL_UP`, as jblanked's driver does.

### Key codes (kit remote)

| Key | Code | Key | Code |
|---|---|---|---|
| `CH-` | `0x45` | `0` | `0x16` |
| `CH` | `0x46` | `1` | `0x0C` |
| `CH+` | `0x47` | `2` | `0x18` ← forward |
| prev | `0x44` | `3` | `0x5E` |
| next | `0x40` | `4` | `0x08` ← left |
| play/pause | `0x43` | `5` | `0x1C` ← stop |
| `-` | `0x07` ← speed −10 | `6` | `0x5A` ← right |
| `+` | `0x15` ← speed +10 | `7` | `0x42` |
| `EQ` | `0x09` ← speed = 50 | `8` | `0x52` ← backward |
| `100+` | `0x19` | `9` | `0x4A` |
| `200+` | `0x0D` | | |

Other remotes differ — capture codes with `projects/validate.py` (stage 1 prints every
code it decodes).

**Always keep a watchdog:** `IRremote.py` calls `stop()` after ~800 polls with no valid
frame. Never ship IR control without it.

## Bluetooth — JDY-32 on UART0

GP1 ← module TXD, GP0 → module RXD, VCC 3V3.

### Two traps

1. **Name mismatch.** The schematic says **JDY-32**; the wiki tells you to pair with
   **`JDY-33-SPP`** and warns that **`JDY-33-BLE` will fail**. The advertised name is a
   firmware setting. **Always pick the `-SPP` entry.**
2. **Baud.** The JDY family defaults to **9600**, but Waveshare's `bluetooth.py` opens
   **115200**. If you get garbage, try both. Confirm with `AT+BAUD`.

AT commands: `AT+BAUD` `AT+NAMES` (SPP name) `AT+NAME` (BLE name) `AT+PIN` (default
`1234`) `AT+MACS` `AT+MAC` `AT+RST` `AT+DEFAULT` `AT+DISC`.

### Wire protocol — JSON over SPP

Phone → robot:

| JSON | Effect |
|---|---|
| `{"Forward":"Down"}` / `{"Forward":"Up"}` | drive / stop |
| `{"Backward"...}` `{"Left"...}` `{"Right"...}` | same Down/Up convention |
| `{"Low":"Down"}` `{"Medium":"Down"}` `{"High":"Down"}` | speed 30 / 50 / 100 |
| `{"BZ":"on"|"off"}` | buzzer |
| `{"LED":"on"|"off"}` | GP25 user LED |
| `{"RGB":"(255,0,0)"}` | all four WS2812B |

Robot → phone: `{"State":"Forward"}`, `{"State":"Stop"}`, `{"BZ":"ON"}` …

### Two defects to fix in anything you ship

1. **No deadman timer.** It's press-and-hold; if the link drops mid-press the robot keeps
   driving.
   ```python
   if utime.ticks_diff(utime.ticks_ms(), last_cmd) > 500:
       M.stop()
   ```
2. **`eval()` on received data** — `rgb = tuple(eval(cmd))` is arbitrary code execution
   by anything that pairs. Replace:
   ```python
   rgb = tuple(int(x) for x in cmd.strip("()").split(","))
   ```

## The Android app

`https://files.waveshare.com/wiki/PicoGo/Base.zip` → `base.apk`.
Flow: *Bluetooth control* → **Search** → pick **`JDY-33-SPP`** → **Remote Control**.

Reality check from the APK: package id `com.example.myapplication`, built **Nov 2021**,
declares only legacy `BLUETOOTH`/`BLUETOOTH_ADMIN` + `ACCESS_FINE_LOCATION`, bundles
Firebase, **Android only — no iOS build exists**.

Alternatives: **Serial Bluetooth Terminal** (Android, maintained) to type the JSON by
hand; nRF Connect for the BLE side; or write your own — it's an SPP socket and one-line
JSON.

⚠ **macOS has effectively no Bluetooth SPP support**, so you cannot drive the robot from
the Mac this way. For development, control it over the USB serial REPL instead
(`./pg run`, `./pg exec`).
