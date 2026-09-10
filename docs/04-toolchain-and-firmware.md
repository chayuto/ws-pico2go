# 04 — Toolchain & Firmware

The Pico2Go's controller is an **RP2350-Plus**, which for every toolchain purpose is a
**Raspberry Pi Pico 2** with a USB-C socket, a RESET button and 4 MB of flash. Anything
that targets `RPI_PICO2` / `rp2350` / `pico2` works.

> ⌨️ **This page documents what Waveshare says.** For how this repo actually works —
> `./pg`, `mpremote`, no IDE — see [12 — CLI Workflow](12-cli-workflow.md).
>
> 🍎 **macOS users: read [11 — macOS Setup](11-macos-setup.md) instead of following
> Waveshare's instructions literally.** Every vendor step below is written for Windows
> — a Windows Thonny zip, an offline `.vsix` bundle, `C:\Users\<name>\.pico-sdk`
> paths, `%LOCALAPPDATA%\Arduino15`. **Nothing here actually requires Windows**: there
> are no vendor drivers and no proprietary flashing tool. Doc 11 is the Mac-native
> equivalent of this entire page.

---

## 4.1 Entering bootloader mode

The RP2350-Plus has **both BOOT and RESET buttons** (the stock Pico 2 has only BOOT),
which gives you two options: **[vendor]**

| Method | Steps |
|---|---|
| **Pico-style** | Hold **BOOT** → plug USB → release **BOOT** |
| **Waveshare-style (no unplugging)** | With USB connected: hold **BOOT**, tap **RESET**, release **RESET** first, then release **BOOT** |

Either way a removable drive appears. Drag a `.uf2` onto it; the board reboots itself.

The second method is the one you want during development — the robot stays plugged in
and you never have to fish the USB cable out from under the acrylic deck.

---

## 4.2 MicroPython (what the demos use)

### Which firmware

| Source | File | Notes |
|---|---|---|
| **Bundled in the vendor demo zip** | `uf2/RPI_PICO2-20250415-v1.25.0.uf2` | ✅ Simplest — it's already in `PicoGo_Code_V2.zip` |
| micropython.org | Any `RPI_PICO2` build | Official, works directly on RP2350-Plus |
| Waveshare | `WAVESHARE-RP2350A-Board.zip` | Waveshare's own RP2350A build |

The demo zip also carries `RPI_PICO-20250415-v1.25.0.uf2` for the original RP2040
PicoGo — **do not flash that one** onto an RP2350-Plus.

> ⚠️ The vendor wiki still recommends **Thonny 3.3.3** (a 2021 release, Windows-only
> zip). Thonny 3.3.3 predates RP2350 and its interpreter option is literally labelled
> "MicroPython (Raspberry Pi Pico)". It generally still works because it just talks
> serial REPL — but if you hit oddities, install a **current Thonny** from
> [thonny.org](https://thonny.org/) instead. There is no reason to run the 2021 build
> on a 2026 chip.

### Thonny setup

1. Install Thonny; on first run set **Language** and set the board environment to
   **Raspberry Pi**.
2. Connect the RP2350-Plus.
3. Bottom-right → **Configure interpreter** → **MicroPython (Raspberry Pi Pico)** →
   pick the port.
4. Press **Stop** to get a REPL banner in the Shell.

### Getting the demo modules onto the device — the step people skip

Most demos `import` sibling modules (`Motor`, `ws2812`, `ST7789`, `TRSensor`). Opening a
file in Thonny and pressing Run executes it *from your PC*, but the imports resolve
**on the device**. So:

> **Upload `Motor.py`, `ws2812.py`, `ST7789.py` and `TRSensor.py` to the Pico's
> filesystem first**, or every demo dies with `ImportError: no module named 'Motor'`.

Waveshare says this obliquely: *"Some demos will call other modules. The sample demo
must be saved to Raspberry Pi Pico before running."* **[vendor]**

### Autorun

MicroPython runs `main.py` on boot. To make the robot run untethered:

> Save the demo you want **as `main.py` on the device**, unplug USB, flip the switch.

This is required for anything that moves, because most motion demos are written to be
run without a USB cable attached.

**To stop an autorunning `main.py`**: connect in Thonny and hit **Stop/Restart**
(Ctrl-C at the REPL). If it's spinning tightly enough that you can't break in, re-flash
the MicroPython UF2 — that wipes the filesystem.

---

## 4.3 C / C++ with the Pico SDK

Use the official **Raspberry Pi Pico VS Code extension**. **[vendor]**

- Extension marketplace: search `raspberry-pi-pico`, or install the `.vsix` from
  Waveshare's offline bundle. VS Code **≥ v1.87.0** required.
- Create a project → pick SDK version → **advanced configuration: Yes**.
- **Toolchain choice is where the RP2350 gets interesting:**
  - `13.2.Rel1` → **Arm Cortex-M33**
  - `RISCV.13.3` → **Hazard3 RISC-V**
  Both target the same silicon. This is the cheapest RISC-V-vs-Arm A/B experiment
  available anywhere.
- Board: select a **Pico 2 / RP2350** board.
- Flash with the extension's **Run**, or drag the `.uf2` manually.

### Importing an existing project

Two traps Waveshare calls out: **[vendor]**

1. **No non-ASCII characters in `CMakeLists.txt`** (including comments) or the import fails.
2. You must have the board-type line present, or a "Pico 2" selection still builds
   RP2040 firmware:
   ```cmake
   set(PICO_BOARD pico2 CACHE STRING "Board type")
   ```
   (The wiki's screenshot shows `pico`; set it to `pico2` for this robot.)

### A ready-made C driver set

`jblanked/Waveshare` ships a complete Pico-SDK driver layer for exactly this chassis —
`motor`, `battery`, `lcd` (with ST7789 PIO + 5 font sizes), `tracking_sensor` (PIO
TLC2543), `ultrasonic_sensor`, `infrared`, `bluetooth`. It is derived from
`MKesenheimer/pico-go`. See [10 — Resources](10-resources.md).

---

## 4.4 Arduino

Use **`arduino-pico`** by Earle Philhower. **[vendor][3rd-party]**

Board Manager URL:
```
https://github.com/earlephilhower/arduino-pico/releases/download/4.5.2/package_rp2040_index.json
```
(check the repo for the newest release; append after a comma if you already have an
ESP32 URL).

Then **Tools → Board → Raspberry Pi Pico → Raspberry Pi Pico 2**, or select the
**Waveshare RP2350 Plus** variant directly — `arduino-pico` ships a
`waveshare_rp2350_plus` variant that already knows `PIN_LED = 25`.

First upload: put the board in BOOT mode; the port shows as **"uf2 Board"**. After the
first sketch lands, a normal COM/tty port appears.

> If you ever need to fully reset the Arduino IDE: uninstall, then manually delete
> everything in `%LOCALAPPDATA%\Arduino15` (Windows) / `~/Library/Arduino15` (macOS)
> before reinstalling.

---

## 4.5 Recommended workflow for this robot

1. **Flash MicroPython once**, upload the four library modules
   (`Motor.py`, `ws2812.py`, `ST7789.py`, `TRSensor.py`) and leave them there.
2. Develop the behaviour you're working on as a normal script in Thonny, running it
   over USB with the wheels off the ground and the **switch ON**.
3. Only when it works, save it as `main.py` and go untethered.
4. Keep a copy of `PicoGo_Code_V2.zip` unpacked locally — Waveshare's file server has
   no versioned archive, and the demo package is your only reference implementation.
5. Move to the C SDK when you need real-time behaviour (encoder-less speed profiling,
   fast LCD refresh, tight ultrasonic loops) or when you want to use core 1.

---

## 4.6 Firmware sources at a glance

| What | Where |
|---|---|
| Vendor demos V2 (use this) | `https://files.waveshare.com/wiki/PicoGo/PicoGo_Code_V2.zip` |
| Vendor demos V1 (pre-Sept 2022 boards only) | `https://files.waveshare.com/upload/0/00/PicoGo_Code.zip` |
| MicroPython for RP2350A (Waveshare) | `https://files.waveshare.com/wiki/RP2350-Plus/WAVESHARE-RP2350A-Board.zip` |
| MicroPython official | `https://micropython.org/download/?vendor=Raspberry%20Pi` |
| Third-party MicroPython + native C modules | `https://github.com/jblanked/Waveshare` → `PicoGo/builds/MicroPython/Waveshare-PicoGo.uf2` |
| Pure C++ port | `https://github.com/MKesenheimer/pico-go` |
