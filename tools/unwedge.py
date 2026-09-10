"""Break a Pico2Go out of a wedged mpremote mount.

A hard-killed `mpremote mount` leaves the device blocked inside the remote
filesystem protocol: the USB serial port still exists, but the REPL never
answers. This talks raw serial and tries to interrupt it.

    python3 tools/unwedge.py [/dev/cu.usbmodemXXXX]

Run via `./pg unwedge`. If it fails, press RESET on the RP2350-Plus.
"""
import glob
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not available - run this through `./pg unwedge`")

port = sys.argv[1] if len(sys.argv) > 1 else None
if not port:
    found = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not found:
        sys.exit("no /dev/cu.usbmodem* found")
    port = found[0]

print("port:", port)
s = serial.Serial(port, 115200, timeout=0.4)
time.sleep(0.3)
s.reset_input_buffer()

for _ in range(8):
    s.write(b"\x03")          # Ctrl-C, interrupt whatever is running
    time.sleep(0.12)
s.write(b"\x02")              # Ctrl-B, leave raw REPL
time.sleep(0.3)
s.write(b"\x03\x04")          # Ctrl-C then Ctrl-D, soft reset
time.sleep(1.2)

reply = s.read(4000)
s.close()
print("device replied:", reply[-160:] if reply else b"(silence)")
sys.exit(0 if reply else 1)
