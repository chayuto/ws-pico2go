# 11 — macOS Setup (you do **not** need Windows)

Waveshare's entire getting-started flow is written for Windows: a Windows-only Thonny
3.3.3 zip, an offline `.vsix` bundle with `C:\Users\<name>\.pico-sdk` paths, a
Google-Drive VS Code installer, and `%LOCALAPPDATA%\Arduino15` cleanup instructions.

**None of it is required.** Nothing about the Pico2Go is Windows-specific — no drivers,
no vendor flashing utility, no proprietary IDE. The board is a USB mass-storage device
in bootloader mode and a USB CDC serial port afterwards, both of which macOS supports
natively. Everything below is the macOS-native equivalent.

## What Waveshare says vs. what you actually do

| Waveshare's instruction | Why it's Windows-only | macOS equivalent |
|---|---|---|
| Download `Thonny-3.3.3.zip` | Windows installer, 2021 build | `brew install --cask thonny` (v5.x) |
| Download `pico-vscode` bundle from Google Drive, install `.vsix` | Offline Windows package | Install **Raspberry Pi Pico** from the VS Code marketplace |
| Copy `.pico-sdk` into `C:\Users\<name>` | Manual Windows SDK staging | Extension downloads it to `~/.pico-sdk` automatically |
| Set CMake/Ninja/Python paths to `...\*.exe` | Windows executables | Leave as **Default** — the extension manages them |
| Delete `C:\Users\...\AppData\Local\Arduino15` | Windows config path | `~/Library/Arduino15` |
| "A removable disk will appear, copy the firmware into it" | Finder does this badly | `cp -X`, `rsync`, or `picotool` (see §11.5) |
| Serial shows as `COM3` | — | `/dev/cu.usbmodem*` |

---

## 11.1 Your machine

Checked on this Mac — **macOS 26.6.2, Apple Silicon (arm64)**:

| Requirement | Status |
|---|---|
| Homebrew | ✅ `/opt/homebrew/bin/brew` |
| Xcode command line tools | ✅ (full Xcode at `/Applications/Xcode.app`) |
| Git ≥ 2.28 | ✅ 2.50.1 |
| VS Code ≥ 1.105.1 | ✅ 1.136.1 |
| CMake, Ninja | ✅ already installed |
| Python 3 | ✅ 3.14.3 (Homebrew) |
| Thonny / picotool / mpremote / Arduino | ❌ not installed yet |

Everything missing is one `brew` command away. Note that your Homebrew Python is
**PEP 668 externally-managed**, so `pip3 install mpremote` will be refused — use the
Homebrew formula instead.

---

## 11.2 One-shot install

> **This repo does not use Thonny.** The `brew install --cask thonny` line is kept
> below only for people following the vendor tutorials verbatim. The workflow that
> this repo is built around is in [12 — CLI Workflow](12-cli-workflow.md), and it
> needs no IDE at all.

```sh
# What this repo actually uses
brew install mpremote picotool coreutils

# Optional, only if you want the vendor's GUI experience
# brew install --cask thonny

# Only if you plan to write C/C++
xcode-select --install            # no-op if you already have Xcode
# then: VS Code → Extensions → search "Raspberry Pi Pico" → Install

# Only if you plan to use Arduino
brew install --cask arduino-ide
```

`brew install --cask` apps are unsigned-adjacent enough that Gatekeeper may complain on
first launch. Right-click → **Open**, or `xattr -dr com.apple.quarantine /Applications/Thonny.app`.

---

## 11.3 Get the firmware and demos

```sh
cd ~/repos/ws-pico2go
mkdir -p ref && cd ref
curl -LO https://files.waveshare.com/wiki/PicoGo/PicoGo_Code_V2.zip
unzip -o PicoGo_Code_V2.zip
ls "PicoGo_Code V2"          # note the space in the directory name
```

The MicroPython firmware you need is inside:
`PicoGo_Code V2/uf2/RPI_PICO2-20250415-v1.25.0.uf2`

> ⚠️ The same folder contains `RPI_PICO-*.uf2` — that's **RP2040**. The RP2350-Plus
> needs the **`RPI_PICO2`** one.

macOS `unzip` will scatter `__MACOSX/` and `._*` files around. Harmless; `rm -rf __MACOSX` if it bothers you.

---

## 11.4 Enter bootloader mode

With the USB-C cable connected to the RP2350-Plus:

> **Hold `BOOT` → tap `RESET` → release `RESET` → release `BOOT`.**

(The classic "hold BOOT while plugging in" also works, but the RP2350-Plus has a RESET
button precisely so you don't have to fish the cable out from under the acrylic deck.)

Confirm it appeared:

```sh
ls /Volumes
# expect a new volume — RP2350 (RP2040 boards show up as RPI-RP2)
```

If nothing appears: your USB-C cable is probably **charge-only**. Swap it. macOS needs
no drivers for this.

---

## 11.5 ⚠️ Flashing UF2 on macOS — do not drag it in Finder

The bootloader volume is a **fake** filesystem: it has no real storage behind it, and
it interprets sectors as they're written. Finder writes extended attributes and
resource forks alongside your file and then reads them back — the reads return garbage,
and Finder throws `kPOSIXErrorENOATTR ("Attribute not found")`.

This was acute on macOS Ventura 13.0–13.0.1 and Apple fixed the worst of it in 13.1, so
on macOS 26 a drag *usually* works. But the underlying mismatch is still there, and the
Terminal methods are strictly better. **[3rd-party — Raspberry Pi's own writeup]**

Pick any of these:

```sh
# Best: no filesystem involved at all, works from any state
picotool load -x ref/"PicoGo_Code V2"/uf2/RPI_PICO2-20250415-v1.25.0.uf2
#   -x  = execute (reboot into the new firmware) after loading

# Good: -X suppresses extended attributes / resource forks
cp -X ref/"PicoGo_Code V2"/uf2/RPI_PICO2-20250415-v1.25.0.uf2 /Volumes/RP2350/

# Also fine
rsync ref/"PicoGo_Code V2"/uf2/RPI_PICO2-20250415-v1.25.0.uf2 /Volumes/RP2350/
```

> **"Disk Not Ejected Properly" is expected.** The board reboots the instant the last
> UF2 block lands, so the volume vanishes without being unmounted. That notification
> means it worked. Same for a `cp` that reports an error at the very end.

`picotool` can also put the board into bootloader mode for you without touching the
buttons, once firmware is running:

```sh
picotool info -a          # what's on the board right now
picotool reboot -u        # reboot into USB bootloader (BOOTSEL)
```

---

## 11.6 MicroPython on macOS

### Find the serial port

```sh
ls /dev/cu.usbmodem*
# e.g. /dev/cu.usbmodem14101
```

Use the **`cu.*`** node, not `tty.*`. On macOS `tty.*` blocks on open waiting for
carrier detect; `cu.*` ("call-up") doesn't. Every tool below expects `cu.*`.

### Option A — Thonny (only if you're following the vendor tutorials verbatim)

1. Launch Thonny. First run: pick your language; for board environment choose
   **Raspberry Pi** (as the wiki says).
2. Bottom-right corner → **Configure interpreter…**
3. Interpreter: **MicroPython (Raspberry Pi Pico)**; Port: your `/dev/cu.usbmodem*`.
4. **OK**, then press **Stop** — you should get a `MicroPython v1.25.0 …` banner.
5. Upload the four library modules: open each from `ref/PicoGo_Code V2/`, then
   **File → Save as… → Raspberry Pi Pico**.

Ignore the wiki's insistence on Thonny 3.3.3 — it predates RP2350 by three years.
Thonny 5.x is what `brew` installs and it's fine.

### Option B — `mpremote` ✅ what this repo uses

Thonny's "save as → device" dance makes the *board* the source of truth, which is
exactly backwards. `mpremote` keeps your code in this repo and can even serve it to the
board live. This repo wraps all of it in `./pg` — see
[12 — CLI Workflow](12-cli-workflow.md) — but the raw commands are:

```sh
cd ref/"PicoGo_Code V2"

mpremote connect list                     # find the device
mpremote fs ls                            # list the device filesystem
mpremote fs cp Motor.py ws2812.py ST7789.py TRSensor.py :   # upload all four libs
mpremote repl                             # interactive REPL (Ctrl-] to exit)
mpremote run Line-Tracking2.py            # run a script from the Mac, no upload
mpremote fs cp Line-Tracking2.py :main.py # install as autorun
mpremote fs rm :main.py                   # uninstall autorun
mpremote soft-reset
```

`mpremote run` is the killer feature for this robot: it executes your script on the
device **without writing it to flash**, so you can iterate on the line-follower gains
without wearing out the filesystem or fighting `main.py`.

### The `./pg` wrapper

All of the above is already wrapped, with an emergency stop and a runtime cap:

```sh
./pg doctor            ./pg run <app> [secs]     ./pg install <app>
./pg flash             ./pg exec '<code>'        ./pg stop
```

See [12 — CLI Workflow](12-cli-workflow.md).

### Serial monitor without an IDE

```sh
mpremote repl                        # simplest
screen /dev/cu.usbmodem14101 115200  # Ctrl-A then K to quit
brew install minicom && minicom -D /dev/cu.usbmodem14101 -b 115200
```

> If you use `screen`, always exit with **Ctrl-A K** — killing the terminal window
> leaves a stale lock in `/var/lock` and the port appears busy afterwards.

---

## 11.7 C/C++ on macOS

Skip Waveshare's whole offline-bundle section. On macOS:

```sh
xcode-select --install     # provides git + tar; no-op if Xcode is installed
```

Then in VS Code: **Extensions → search "Raspberry Pi Pico" → Install** (publisher
`raspberry-pi`). Requires VS Code ≥ 1.105.1 — you're on 1.136.1. ✅

The extension downloads and manages **its own** SDK, toolchains, CMake, Ninja and
Python into `~/.pico-sdk`. **Leave every path field on "Default"** — the Windows
`${HOME}/.pico-sdk/cmake/v3.28.6/bin/cmake.exe` values in the wiki are wrong here, and
you don't need the Homebrew `cmake`/`ninja` you already have.

Creating a project:

1. **Pico: New C/C++ Project** from the command palette.
2. SDK version: latest.
3. Advanced configuration: **Yes**.
4. **Toolchain** — this is the interesting choice on RP2350:
   - `13.2.Rel1` → **Arm Cortex-M33**
   - `RISCV.13.3` → **Hazard3 RISC-V**
5. CMake / Ninja: **Default**.
6. **Board: Pico 2** (RP2350).

For an imported project, make sure `CMakeLists.txt` contains:

```cmake
set(PICO_BOARD pico2 CACHE STRING "Board type")
```

Without it you'll silently build RP2040 firmware even with Pico 2 selected. (Waveshare's
screenshot shows `pico`; for this robot it must be `pico2`.) Also: **no non-ASCII
characters anywhere in `CMakeLists.txt`**, comments included, or the import fails.

Flash with the extension's **Run**, or:

```sh
picotool load -x build/your_project.uf2
```

### Ready-made C drivers for this chassis

`jblanked/Waveshare` → `PicoGo/src/SDK/` gives you `motor`, `battery`, `lcd`,
`tracking_sensor`, `ultrasonic_sensor`, `infrared` and `bluetooth` as drop-in Pico-SDK
modules. Its build script assumes a Mac layout already
(`/Users/user/pico/micropython/ports/rp2`). See [10 — Resources](10-resources.md).

---

## 11.8 Arduino on macOS

```sh
brew install --cask arduino-ide
```

**Arduino IDE → Settings → Additional boards manager URLs:**

```
https://github.com/earlephilhower/arduino-pico/releases/download/4.5.2/package_rp2040_index.json
```

(Check the repo for the current release tag.) Then **Boards Manager → "pico" →
Install**, and pick **Raspberry Pi Pico 2** or the **Waveshare RP2350 Plus** variant —
the latter already defines `PIN_LED = 25`.

First upload: board in BOOTSEL, port shows as **"UF2 Board"**. After that a normal
`/dev/cu.usbmodem*` appears.

Full reset (the macOS equivalent of the wiki's `Arduino15` instructions):

```sh
rm -rf ~/Library/Arduino15
```

CLI alternative, if you prefer not to run the Electron IDE:

```sh
brew install arduino-cli
arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://github.com/earlephilhower/arduino-pico/releases/download/4.5.2/package_rp2040_index.json
arduino-cli core update-index
arduino-cli core install rp2040:rp2040
arduino-cli board listall | grep -i rp2350
```

---

## 11.9 macOS-specific gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Finder error copying `.uf2`, `kPOSIXErrorENOATTR` | Finder writes extended attributes to a fake filesystem | `cp -X`, `rsync`, or `picotool load` |
| "Disk Not Ejected Properly" after flashing | The board reboots the moment flashing completes | **Expected.** Ignore it. |
| `cp` reports an error but the board reboots | Same thing | It worked |
| No `/Volumes/RP2350` appears | Charge-only USB-C cable | Use a data cable |
| Port hangs when opened | Used `/dev/tty.*` | Use `/dev/cu.*` |
| "Resource busy" / port won't open | Thonny, `screen` or Arduino still holds it | Quit the other tool; `screen` exits with **Ctrl-A K** |
| `pip3 install mpremote` refused (PEP 668) | Homebrew Python is externally managed | `brew install mpremote` |
| App "cannot be opened" on first launch | Gatekeeper quarantine | Right-click → **Open**, or `xattr -dr com.apple.quarantine /Applications/<App>.app` |
| `__MACOSX/` and `._*` files after unzip | macOS archive metadata | Harmless; `rm -rf __MACOSX` |
| Bluetooth pairing to the robot from the Mac | macOS supports Bluetooth **SPP** poorly | Use the Android app, or a phone; on the Mac talk to the robot over USB serial instead |
| Wrong firmware flashed | Vendor zip contains both RP2040 and RP2350 images | Use `RPI_PICO2-*.uf2` |

> **The Bluetooth one is worth calling out.** macOS dropped practical Bluetooth-SPP
> support years ago, so you will not comfortably drive the JDY-32 from your Mac.
> Your options are the Android app, writing your own phone client, or — better for
> development — ignoring Bluetooth and controlling the robot over the USB serial REPL
> while it's tethered.

---

## 11.10 Command card

```sh
# --- flash MicroPython -------------------------------------------------
# BOOT held → tap RESET → release RESET → release BOOT
picotool load -x ref/"PicoGo_Code V2"/uf2/RPI_PICO2-20250415-v1.25.0.uf2

# --- deploy libraries --------------------------------------------------
cd ref/"PicoGo_Code V2"
mpremote fs cp Motor.py ws2812.py ST7789.py TRSensor.py :

# --- iterate (no flash writes) ----------------------------------------
mpremote run Line-Tracking2.py

# --- go standalone -----------------------------------------------------
mpremote fs cp Line-Tracking2.py :main.py && mpremote soft-reset

# --- get back control --------------------------------------------------
mpremote repl                 # Ctrl-C to break out of main.py, Ctrl-] to exit
mpremote fs rm :main.py

# --- diagnostics -------------------------------------------------------
ls /dev/cu.usbmodem*
picotool info -a
picotool reboot -u            # force BOOTSEL without touching buttons
```

Remember: **the power switch must be ON** for anything to move, even over USB.
See [03 — Power & Battery](03-power-and-battery.md).
