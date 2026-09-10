---
name: pico2go-flashing
description: Flashing firmware and recovering the RP2350-Plus on a Pico2Go robot from macOS. Use when the board needs MicroPython flashed, is running unexpected firmware, won't appear as a serial port, shows "could not enter raw repl", enumerates on USB but has no /dev/cu node, needs BOOTSEL, appears bricked, or when switching between MicroPython, the Pico C SDK and Arduino.
---

# Flashing & recovery (macOS)

## Tools

```sh
brew install mpremote picotool coreutils     # NOT pip3 — Homebrew Python is PEP 668
```

## Entering BOOTSEL

| Situation | How |
|---|---|
| MicroPython running | `./pg bootsel` (uses `mpremote bootloader`) |
| Any firmware with USB stdio | `picotool reboot -u -f` — **wait 3–5 s**, the volume is slow to appear |
| Nothing works | Hold **BOOT**, tap **RESET**, release **RESET**, then **BOOT** |

Confirm with `ls /Volumes` → `RP2350` (RP2040 boards show `RPI-RP2`).

## Flashing

```sh
./pg flash                                  # vendor MicroPython from ref/
picotool load -x path/to/firmware.uf2       # anything else
```

**Never drag a `.uf2` in Finder.** The BOOTSEL volume is a fake filesystem; Finder writes
extended attributes, reads them back, gets garbage, and fails with
`kPOSIXErrorENOATTR`. If you must use the filesystem: `cp -X` or `rsync`.

"Disk Not Ejected Properly" right after flashing is **expected** — the board reboots the
instant the last block lands.

⚠ `PicoGo_Code_V2.zip` ships **two** images. `RPI_PICO2-*.uf2` is correct.
`RPI_PICO-*.uf2` is RP2040 and will not run. `./pg flash` refuses the wrong one.

## Diagnosing a board that "won't connect"

Work down this list — `./pg doctor` checks all of it:

1. **No `/dev/cu.usbmodem*` and no `/Volumes/RP2350` and nothing on USB**
   → charge-only cable, or unplugged. The kit ships a **USB-A→micro-B** cable but the
   RP2350-Plus is **USB-C**. Use a USB-C *data* cable.

2. **Enumerated on USB but no `/dev/cu` node** — check with:
   ```sh
   ioreg -p IOUSB -w0 -l | grep -A6 '"idVendor" = 11914'
   ioreg -c IOSerialBSDClient -r -l | grep IOCalloutDevice
   ```
   `idProduct = 5` + `"Board in FS mode"` means MicroPython is running fine and macOS
   just hasn't attached its CDC driver. **Unplug and replug.** The node can take up to
   ~a minute to appear after a BOOTSEL→app re-enumeration; poll rather than concluding
   failure. `ioreg -c IOSerialBSDClient` shows the real node name before `/dev` catches up.

3. **Serial port present, `mpremote` says "could not enter raw repl"**
   → it is not MicroPython. A **new RP2350-Plus ships with Waveshare factory GPIO-test
   firmware** (`RP2350_Plus_Test` v0.1, SDK 2.2.0) that spams a continuity report over
   USB serial and toggles pins — including the buzzer, so **the robot makes noise**.
   Fix: `./pg bootsel && ./pg flash`.

4. **Weird ADC values immediately after flashing** — the first run after a flash+reboot
   can read analog channels wildly wrong (observed: battery pinned at full scale, die
   temp −82 °C). Re-run; it settles. Don't chase it as a hardware fault.

## Back up before overwriting

Factory firmware has no download anywhere. From BOOTSEL:

```sh
picotool save -a ref/factory/RP2350_Plus_Test_factory.uf2
picotool info -a          # chip revision, package, SDK version, ARM/RISC-V
```

This repo already holds that backup plus a captured log of its output.

## Identifying the chip

```sh
picotool info -a          # BOOTSEL only
```
Reports `revision:` — **A4** or later means erratum E9 is fixed in silicon.

## Other toolchains

- **C/C++**: `xcode-select --install`, then the *Raspberry Pi Pico* extension from the
  VS Code marketplace (needs VS Code ≥ 1.105.1). It manages its own SDK in `~/.pico-sdk`
  — leave every path field on **Default**; the wiki's `C:\...\*.exe` values are Windows.
  `set(PICO_BOARD pico2 CACHE STRING "Board type")` or you silently build RP2040 code.
  Toolchain `13.2.Rel1` = Arm M33, `RISCV.13.3` = Hazard3 RISC-V — same silicon.
- **Arduino**: `arduino-pico` core; board *Raspberry Pi Pico 2* or the
  `waveshare_rp2350_plus` variant. Reset config with `rm -rf ~/Library/Arduino15`.
