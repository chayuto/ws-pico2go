"""Event-driven pin-map + polarity validation. Does NOT move the robot.

    ./pg run validate 180

Waits for YOU rather than running on a clock, and exits as soon as everything
is confirmed. Uses the IR remote to label surfaces, which settles the line
sensor polarity contradiction in docs/06-sensors-and-algorithms.md 6.2.
"""

import utime
from machine import Pin

import board
from TRSensor import TRSensor

trs = TRSensor()
dsl = Pin(board.DSL, Pin.IN)
dsr = Pin(board.DSR, Pin.IN)
ir = Pin(board.IR_RX, Pin.IN)

KEY_1, KEY_2, KEY_3 = 0x0C, 0x18, 0x5E     # docs/07 key table


def read_ir():
    """Non-blocking-ish NEC decode. Returns a command byte or None."""
    if ir.value() != 0:
        return None
    c = 0
    while ir.value() == 0 and c < 100:
        c += 1
        utime.sleep_us(100)
    if c < 10:
        return None
    c = 0
    while ir.value() == 1 and c < 50:
        c += 1
        utime.sleep_us(100)
    idx = cnt = 0
    data = [0, 0, 0, 0]
    for _ in range(32):
        c = 0
        while ir.value() == 0 and c < 10:
            c += 1
            utime.sleep_us(100)
        c = 0
        while ir.value() == 1 and c < 20:
            c += 1
            utime.sleep_us(100)
        if c > 7:
            data[idx] |= 1 << cnt
        if cnt == 7:
            cnt, idx = 0, idx + 1
        else:
            cnt += 1
    if data[0] + data[1] == 0xFF and data[2] + data[3] == 0xFF:
        return data[2]
    return None


def sample(secs=2.0):
    cols = [[] for _ in range(board.TRS_CHANNELS)]
    t0 = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), t0) < int(secs * 1000):
        v = trs.AnalogRead()
        for i in range(board.TRS_CHANNELS):
            cols[i].append(v[i])
        utime.sleep_ms(40)
    out = []
    for c in cols:
        c.sort()
        out.append(c[len(c) // 2])
    return out


print("=" * 60)
print("STAGE 1 - waiting for you. Do these in any order, any pace:")
print("  (a) block the LEFT  front sensor with your finger")
print("  (b) block the RIGHT front sensor with your finger")
print("  (c) press any key on the IR remote, aimed at the front")
print("=" * 60)

got_l = got_r = False
keys = []
base = trs.AnalogRead()
lo = list(base)
hi = list(base)

t0 = utime.ticks_ms()
last = 0
while utime.ticks_diff(utime.ticks_ms(), t0) < 90000:
    if not got_l and dsl.value() == 0:
        got_l = True
        print("  >> GP3  DSL (LEFT)  triggered")
    if not got_r and dsr.value() == 0:
        got_r = True
        print("  >> GP2  DSR (RIGHT) triggered")
    k = read_ir()
    if k is not None and k not in keys:
        keys.append(k)
        print("  >> GP5  IR decoded 0x{:02X}".format(k))
    v = trs.AnalogRead()
    for i in range(board.TRS_CHANNELS):
        if v[i] < lo[i]:
            lo[i] = v[i]
        if v[i] > hi[i]:
            hi[i] = v[i]
    if got_l and got_r and keys:
        print("  >> all three confirmed")
        break
    el = utime.ticks_diff(utime.ticks_ms(), t0) // 1000
    if el >= last + 15:
        last = el
        miss = []
        if not got_l:
            miss.append("LEFT sensor")
        if not got_r:
            miss.append("RIGHT sensor")
        if not keys:
            miss.append("IR remote")
        print("  .. {}s, still waiting for: {}".format(el, ", ".join(miss)))
    utime.sleep_ms(10)

print("\nSTAGE 1 RESULT")
print("  GP3 DSL  : {}".format("OK" if got_l else "NEVER TRIGGERED"))
print("  GP2 DSR  : {}".format("OK" if got_r else "NEVER TRIGGERED"))
print("  GP5 IR   : {}".format(
    "OK  codes " + " ".join("0x{:02X}".format(k) for k in keys) if keys else "NO FRAMES"))
print("  line array range seen while you moved about:")
for i in range(board.TRS_CHANNELS):
    print("     IR{}  {:>4} .. {:>4}   (swing {})".format(i + 1, lo[i], hi[i], hi[i] - lo[i]))

if not keys:
    print("\nNo IR, so skipping the labelled surface test.")
    print("Re-run once the remote works, or tell me and I'll do it another way.")
else:
    print("\n" + "=" * 60)
    print("STAGE 2 - surface labelling. Press the remote key when in position:")
    print("   key 1  -> robot held UP IN THE AIR")
    print("   key 2  -> robot sitting on WHITE paper")
    print("   key 3  -> robot sitting on a DARK/BLACK surface")
    print("=" * 60)

    caps = {}
    want = ((KEY_1, "AIR"), (KEY_2, "WHITE"), (KEY_3, "BLACK"))
    t0 = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), t0) < 120000 and len(caps) < 3:
        k = read_ir()
        for code, label in want:
            if k == code and label not in caps:
                print("  capturing {} ...".format(label))
                caps[label] = sample(2.0)
                print("     {} = {}".format(label, caps[label]))
        utime.sleep_ms(10)

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    for label in ("AIR", "WHITE", "BLACK"):
        print("  {:<6} {}".format(label, caps.get(label, "not captured")))

    if "WHITE" in caps and "BLACK" in caps:
        w = caps["WHITE"][2]
        b = caps["BLACK"][2]
        print("\n  centre channel IR3:  white={}  black={}  contrast={}".format(w, b, abs(w - b)))
        if w > b:
            print("  HIGH = more reflection = WHITE.")
            print("  -> the wiki is right, the driver docstring is wrong.")
            print("  -> line following needs readLine(white_line=1)")
        elif b > w:
            print("  HIGH = BLACK.")
            print("  -> the driver docstring is right, readLine() as shipped is correct.")
        if abs(w - b) < 100:
            print("  !! contrast under 100 counts - use 15 mm matte black tape on white card")
print("=" * 60)

board.estop()
