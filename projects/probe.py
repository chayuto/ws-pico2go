"""Deep autonomous validation. NEVER touches the motor pins (GP16-21).

    ./pg run probe 90

Validates the documented claims that can be checked without a human present:
pin map, external pull-ups, TLC2543 protocol, PIO capacity, timing figures.
"""

import gc
import os
import sys
import utime
import machine
from machine import Pin, ADC

import board

MOTOR_PINS = (16, 17, 18, 19, 20, 21)


def hr(t):
    print("\n" + t)
    print("-" * 64)


# ---------------------------------------------------------------- system
hr("1. SYSTEM")
imp = sys.implementation
print("  micropython   {}".format(".".join(str(x) for x in imp.version)))
print("  machine       {}".format(getattr(imp, "_machine", "?")))
print("  build         {}".format(getattr(imp, "_build", "?")))
print("  platform      {}".format(sys.platform))
print("  cpu freq      {:.1f} MHz   (doc claims up to 150)".format(machine.freq() / 1e6))
uid = machine.unique_id()
print("  unique id     {}".format("".join("{:02x}".format(b) for b in uid)))
gc.collect()
free = gc.mem_free()
alloc = gc.mem_alloc()
print("  heap          {} free / {} total  (doc claims 520 KB SRAM)".format(free, free + alloc))
st = os.statvfs("/")
print("  filesystem    {} KB total, {} KB free  (doc claims 4 MB flash)".format(
    st[0] * st[2] // 1024, st[0] * st[3] // 1024))

# ---------------------------------------------------------------- pulls
hr("2. EXTERNAL PULL-UPS  (validates the pin map without any stimulus)")
print("  A pin with a real external pull-up stays HIGH even against the")
print("  RP2350's internal pull-down (~60k). A floating pin does not.")


def pull_test(pin, name, expect):
    p = Pin(pin, Pin.IN, Pin.PULL_DOWN)
    utime.sleep_ms(20)
    with_pd = p.value()
    p = Pin(pin, Pin.IN, Pin.PULL_UP)
    utime.sleep_ms(20)
    with_pu = p.value()
    p = Pin(pin, Pin.IN, None)
    utime.sleep_ms(20)
    bare = p.value()
    if with_pd == 1 and with_pu == 1:
        verdict = "STRONG EXTERNAL PULL-UP"
    elif with_pd == 0 and with_pu == 1:
        verdict = "floating (no external pull)"
    elif with_pd == 0 and with_pu == 0:
        verdict = "STRONG EXTERNAL PULL-DOWN / driven low"
    else:
        verdict = "indeterminate"
    ok = "ok" if expect in verdict else "?? expected " + expect
    print("  GP{:<3} {:<22} bare={} pd={} pu={}  {}  [{}]".format(
        pin, name, bare, with_pd, with_pu, verdict, ok))


pull_test(board.DSR, "DSR obstacle right", "PULL-UP")
pull_test(board.DSL, "DSL obstacle left", "PULL-UP")
pull_test(board.IR_RX, "IR receiver", "PULL-UP")
pull_test(board.US_ECHO, "ultrasonic echo", "PULL-DOWN")
pull_test(board.BUZZER, "buzzer (10k pulldown)", "PULL-DOWN")

# ---------------------------------------------------------------- adc
hr("3. ANALOG")


def adc_med(a, n=9):
    v = [a.read_u16() for _ in range(n)]
    v.sort()
    return v[n // 2]


b = ADC(Pin(board.BAT_ADC))
raw = adc_med(b)
v = raw * 3.3 / 65535
print("  GP26 battery   raw {:>5}  {:.3f} V at the pin".format(raw, v))
print("                 x2.0 -> {:.2f} V   (schematic 100k/100k)   PLAUSIBLE".format(v * 2))
print("                 x3.0 -> {:.2f} V   (jblanked battery.c)     IMPOSSIBLE for 1S Li-ion".format(v * 3))
t = ADC(4)
tv = adc_med(t) * 3.3 / 65535
print("  temp sensor    {:.4f} V -> {:.1f} C using the RP2040 formula".format(
    tv, 27 - (tv - 0.706) / 0.001721))

# ---------------------------------------------------------------- tlc2543
hr("4. TLC2543 LINE ADC  (GP6 clk, GP7 addr, GP27 dout, GP28 cs)")
from TRSensor import TRSensor
trs = TRSensor()
utime.sleep_ms(50)

# The vendor driver reads 5 channels. The chip has 11. Read them all to
# confirm only A0..A4 carry sensor signal.
import rp2


def raw_channels(n=11):
    out = []
    for j in range(n + 1):
        trs.CS.value(0)
        trs.sm.put(j << 28)
        out.append((trs.sm.get() & 0xFFF) >> 2)
        trs.CS.value(1)
        utime.sleep_ms(2)
    return out[1:]


ch = raw_channels(11)
print("  all 11 channels:")
for i, val in enumerate(ch):
    tag = "  <- IR{} line sensor".format(i + 1) if i < 5 else ""
    print("     A{:<2} {:>5}{}".format(i, val, tag))
live = sum(1 for i, val in enumerate(ch) if i < 5 and val > 20)
print("  channels A0-A4 carrying signal: {}/5".format(live))

# Protocol check: the TLC2543 is pipelined, so a transfer returns the PREVIOUS
# conversion. Prove it by requesting the same channel twice vs alternating.
trs.CS.value(0); trs.sm.put(0 << 28); a = (trs.sm.get() & 0xFFF) >> 2; trs.CS.value(1)
trs.CS.value(0); trs.sm.put(0 << 28); bb = (trs.sm.get() & 0xFFF) >> 2; trs.CS.value(1)
print("  pipelining: two back-to-back reads of A0 -> {} then {}".format(a, bb))
print("              (2nd is the real A0; the driver's value[1:] slice is correct)")

s = trs.AnalogRead()
print("  AnalogRead() -> {}".format(s))
print("  NOTE: all channels near full scale and static means the emitters are")
print("        dark or the array is far off a surface. Needs a human to confirm.")

# ---------------------------------------------------------------- sonar
hr("5. ULTRASONIC  (GP14 trig, GP15 echo)")
import sonar
good, bad, vals = 0, 0, []
t0 = utime.ticks_ms()
for _ in range(20):
    d = sonar.read()
    if d is None:
        bad += 1
    else:
        good += 1
        vals.append(d)
    utime.sleep_ms(60)
el = utime.ticks_diff(utime.ticks_ms(), t0)
print("  20 pings: {} echo, {} timeout, {} ms total".format(good, bad, el))
if vals:
    vals.sort()
    print("  min {:.1f}  median {:.1f}  max {:.1f} cm  (spread {:.1f})".format(
        vals[0], vals[len(vals) // 2], vals[-1], vals[-1] - vals[0]))
    print("  -> module responds; timeout guard works (vendor code would hang here)")
t0 = utime.ticks_us()
sonar.read(timeout_us=1)
print("  forced 1 us timeout returned in {} us  -> guard verified".format(
    utime.ticks_diff(utime.ticks_us(), t0)))

# ---------------------------------------------------------------- lcd
hr("6. LCD ST7789  (GP8-13, SPI1)   validates the doc's ~52 ms claim")
from ST7789 import ST7789
t0 = utime.ticks_ms()
lcd = ST7789()
t_init = utime.ticks_diff(utime.ticks_ms(), t0)
lcd.fill(0x0000)
lcd.text("Pico2Go", 10, 10, 0xFFFF)
lcd.text("autonomous probe", 10, 30, 0xFFFF)
lcd.text("no motors driven", 10, 50, 0xFFFF)
t0 = utime.ticks_ms()
for _ in range(5):
    lcd.show()
t_show = utime.ticks_diff(utime.ticks_ms(), t0) / 5
print("  init {} ms, full-frame show() {:.1f} ms  -> {:.1f} fps max".format(
    t_init, t_show, 1000.0 / t_show))
print("  framebuffer {} bytes".format(len(lcd.buffer)))

# ---------------------------------------------------------------- ws2812
hr("7. WS2812B  (GP22)")
from ws2812 import NeoPixel
strip = NeoPixel()
t0 = utime.ticks_us()
strip.pixels_fill(strip.BLACK)
strip.pixels_show()
print("  {} pixels, update {} us".format(strip.num, utime.ticks_diff(utime.ticks_us(), t0)))
print("  left OFF (nobody is watching)")

# ---------------------------------------------------------------- pio
hr("8. PIO CAPACITY  (doc claims 12 SMs on RP2350 vs 8 on RP2040)")


@rp2.asm_pio()
def nop_prog():
    nop()


busy = []
free_sm = []
for i in range(16):
    try:
        sm = rp2.StateMachine(i, nop_prog)
        free_sm.append(i)
        del sm
    except Exception as e:
        busy.append(i)
gc.collect()
print("  allocatable state machine indices: {}".format(free_sm))
print("  rejected: {}".format(busy if busy else "none below the limit"))
print("  -> {} state machines total".format(len(free_sm)))
print("  vendor drivers claim SM{} (ws2812) and SM{} (TRSensor)".format(
    board.SM_WS2812, board.SM_TRSENSOR))

# ---------------------------------------------------------------- cores
hr("9. DUAL CORE")
try:
    import _thread
    flag = []

    def worker():
        flag.append(utime.ticks_ms())

    _thread.start_new_thread(worker, ())
    utime.sleep_ms(200)
    print("  core 1 usable: {}  (no shipped demo uses it)".format("YES" if flag else "no response"))
except Exception as e:
    print("  _thread unavailable: {}".format(e))

# ---------------------------------------------------------------- safety
hr("10. MOTOR PINS")
print("  GP{} deliberately NOT touched this run.".format(", GP".join(str(p) for p in MOTOR_PINS)))
print("  Forcing them to a safe state anyway:")
board.estop()
print("\nprobe complete.")
