# 07 — Remote Control

Two independent channels: **infrared** (line-of-sight, one-way, no pairing) and
**Bluetooth SPP** (bidirectional, phone app).

---

## 7.1 Infrared

### Hardware
3-pin IR receiver module on header `H1`, powered from 3V3, output → **GP5**. Idle high;
a burst pulls it low.

> ⚠️ **Correction.** This document previously claimed a 4.7 K external pull-up on GP5,
> read off `R1` in the schematic. Measurement refutes it: GP5 goes **low** against the
> RP2350's internal ~60 K pull-down, which a 4.7 K pull-up would win comfortably. `R1`
> belongs to an adjacent net in an overlapping region of the schematic sheet. The pull
> is most likely the receiver module's own internal ~30 K. GP2/GP3 pass the same test,
> so the method is sound. **[measured]**

### Protocol: NEC

Waveshare's decoder is a hand-rolled, polling bit-banger:

| Phase | Timing | How the code detects it |
|---|---|---|
| Leader (AGC burst) | 9 ms low | count up to 100 × 100 µs while low; reject if `count < 10` |
| Space | 4.5 ms high | count up to 50 × 100 µs while high |
| 32 data bits | 0.56 ms low mark, then 0.56 ms (=0) or 1.69 ms (=1) high space | `count > 7` (i.e. > 700 µs) → bit is 1 |
| Validation | address + ~address = `0xFF`, command + ~command = `0xFF` | returns `data[2]` (the command byte) |

If validation fails the function returns the string `"repeat"` — NEC repeat frames
(a 9 ms + 2.25 ms leader with no payload) land here.

```python
IR = Pin(5, Pin.IN)
key = getkey()          # returns command byte, None, or "repeat"
```

> ⚠️ This is **blocking and polling-based**. During decode (~67 ms for a full frame)
> nothing else runs. jblanked's version improves on it by hanging the same decoder off
> a **falling-edge pin IRQ** with `Pin.PULL_UP`, so the main loop isn't spinning on the
> pin — a worthwhile change to steal.

### Full key-code table

For the NEC card remote shipped with the kit. Values are the NEC **command** byte.
**[code — Waveshare demos + jblanked's `infrared.py` constant table]**

| Key | Code | Key | Code |
|---|---|---|---|
| `CH-` | `0x45` | `0` | `0x16` |
| `CH` | `0x46` | `1` | `0x0C` |
| `CH+` | `0x47` | `2` | `0x18` ← **forward** |
| `\|<<` (prev) | `0x44` | `3` | `0x5E` |
| `>>\|` (next) | `0x40` | `4` | `0x08` ← **left** |
| `>\|\|` (play/pause) | `0x43` | `5` | `0x1C` ← **stop** |
| `-` (vol down) | `0x07` ← **speed −10** | `6` | `0x5A` ← **right** |
| `+` (vol up) | `0x15` ← **speed +10** | `7` | `0x42` |
| `EQ` | `0x09` ← **speed = 50** | `8` | `0x52` ← **backward** |
| `100+` | `0x19` | `9` | `0x4A` |
| `200+` | `0x0D` | | |

The default drive mapping is the numeric keypad arranged as a D-pad:

```
        [2] forward
 [4] left  [5] stop  [6] right
        [8] backward
```

### If your remote is different

*"Different infrared remote controllers may have different key codes, if you use other
controllers, you may need to modify the codes."* **[vendor]**

Capture your own in 30 seconds:

```python
from machine import Pin
import utime
IR = Pin(5, Pin.IN)
# paste getkey() from IRremote.py here
while True:
    k = getkey()
    if k is not None and k != "repeat":
        print(hex(k))
```

### Safety net

`IRremote.py` counts consecutive polls with no valid frame and calls `M.stop()` after
~800 of them. Keep that behaviour in anything you write — a runaway robot with a
100 % duty cycle finds the stairs quickly.

---

## 7.2 Bluetooth

### Hardware
**JDY-32** dual-mode module — **Bluetooth 3.0 SPP + BLE 4.2**, 2.4 GHz GFSK, up to
5 dBm, ~40 m line of sight. **[schematic][3rd-party datasheet]**

Wired to **UART0**: module `TXD` → GP1 (MCU RX), module `RXD` ← GP0 (MCU TX), `VCC` 3V3.

### ⚠️ Two naming/baud traps

1. **Module name vs. advertised name.** The schematic says JDY-32; the wiki tells you
   to pair with **`JDY-33-SPP`** and explicitly warns that picking **`JDY-33-BLE`
   will fail**. The advertised name is a firmware setting (`AT+NAMES` / `AT+NAME`), so
   don't be alarmed by the mismatch. **Always choose the `-SPP` entry.**

2. **Baud rate.** The JDY-32/33 family defaults to **9600**, but Waveshare's
   `bluetooth.py` opens `UART(0, 115200)` — implying the shipped modules are
   pre-configured to 115200. Meanwhile `Ultrasionc-Infrared-follow.py` opens
   `UART(0, 9600)` (though it never actually uses the port). If Bluetooth gives you
   garbage, **try both baud rates** before assuming the module is dead.

### Useful JDY AT commands **[3rd-party]**

Send these over UART0 with the module in command mode:

| Command | Purpose |
|---|---|
| `AT+BAUD` | query / set baud rate |
| `AT+NAMES` | SPP advertised name |
| `AT+NAME` | BLE advertised name |
| `AT+PIN` | SPP pairing PIN (default `1234`) |
| `AT+MACS` / `AT+MAC` | SPP / BLE MAC address |
| `AT+RST` | soft reset |
| `AT+DEFAULT` | factory reset |
| `AT+DISC` | disconnect |

### The wire protocol: JSON over SPP

`bluetooth.py` reads whole UART chunks and parses them with `ujson.loads()`.

**Phone → robot:**

| JSON | Effect |
|---|---|
| `{"Forward":"Down"}` / `{"Forward":"Up"}` | forward at current speed / stop |
| `{"Backward":"Down"}` / `{"Backward":"Up"}` | reverse / stop |
| `{"Left":"Down"}` / `{"Left":"Up"}` | pivot left @20 / stop |
| `{"Right":"Down"}` / `{"Right":"Up"}` | pivot right @20 / stop |
| `{"Low":"Down"}` | speed = 30 |
| `{"Medium":"Down"}` | speed = 50 |
| `{"High":"Down"}` | speed = 100 |
| `{"BZ":"on"}` / `{"BZ":"off"}` | buzzer |
| `{"LED":"on"}` / `{"LED":"off"}` | GP25 user LED |
| `{"RGB":"(255,0,0)"}` | set all four WS2812B |

**Robot → phone:** `{"State":"Forward"}`, `{"State":"Stop"}`, `{"BZ":"ON"}`,
`{"LED":"OFF"}`, `{"State":"RGB:(...)"}` and so on.

The `Down`/`Up` convention is a **press-and-hold** model — the phone sends `Down` on
touch-down and `Up` on release. There is **no timeout on the robot side**: if the link
drops mid-press, the robot keeps driving. If you rely on Bluetooth control, add a
deadman timer:

```python
last_cmd = utime.ticks_ms()
# ...on every successfully parsed command: last_cmd = utime.ticks_ms()
if utime.ticks_diff(utime.ticks_ms(), last_cmd) > 500:
    M.stop()
```

> ⚠️ `{"RGB": ...}` is handled with `eval(cmd)`. That is arbitrary-code execution from
> whatever paired to your robot. Replace it with a parser
> (`tuple(int(x) for x in cmd.strip("()").split(","))`) if the robot ever leaves your desk.

### The Android app

`PicoGo APP` → `https://files.waveshare.com/wiki/PicoGo/Base.zip` (contains `base.apk`).

**Flow:** launch → *Bluetooth control* → **Search** (top right) → wait a few seconds →
pick the **`JDY-33-SPP`** device → next page → **Remote Control**.
Gives you a D-pad plus buzzer and RGB colour controls. **[vendor]**

**Realistic assessment of this app** (from inspecting the APK):

| Finding | Implication |
|---|---|
| Package id is `com.example.myapplication` | An unsigned-looking template build, never published to Play |
| Built **November 2021** | Predates Android 12's Bluetooth permission overhaul |
| Declares only legacy `BLUETOOTH` / `BLUETOOTH_ADMIN` + `ACCESS_FINE_LOCATION` | On Android 12+ these are compatibility-shimmed; on newer releases sideloading an app with an old `targetSdk` may be blocked outright |
| Bundles Firebase / Play Services | Unnecessary for a BT serial remote |
| **Android only** — no iOS build exists | iPhone users have no vendor app at all |

**Alternatives that will outlive the app:**

- **Serial Bluetooth Terminal** (Android, actively maintained) — pair the SPP device
  and type the JSON by hand. Perfect for debugging the protocol.
- **Bluefruit Connect** / **nRF Connect** — for the BLE side.
- Write your own: it's an SPP socket and one-line JSON. A 100-line Flutter/React Native
  app or a laptop Python script over `rfcomm` covers it.
- **Skip Bluetooth entirely**: replace the JDY-32 with an ESP32 or a Pico W-style
  module for a Wi-Fi/WebSocket UI. See
  [09 — Extending the Platform](09-extending-the-platform.md).

---

## 7.3 Choosing between them

| | Infrared | Bluetooth SPP |
|---|---|---|
| Range | ~5 m, line of sight | ~10–40 m, through walls |
| Direction | one-way | **bidirectional** (telemetry back) |
| Latency | ~70 ms per frame, blocking | low, but UART-buffered |
| Setup | none | pairing |
| Interference | sunlight, plasma displays | 2.4 GHz congestion |
| Cost to your CPU | high (blocking poll) | low |
| Good for | quick demos, classrooms | anything with telemetry or a real UI |

For serious work, use Bluetooth (or replace it) and keep IR as an emergency stop.
