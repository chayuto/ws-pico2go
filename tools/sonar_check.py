"""Characterise the ultrasonic before trusting a robot to it.

    ./pg run sonar_check 30

Never touches the motors. Point the robot at a flat wall roughly 30-60 cm away
and leave it. It reports what the avoider's constants actually depend on:

* **answer rate** - what fraction of pings come back at all, at the short
  timeout the control loop uses and at the full one
* **cost** - milliseconds per ping, which is latency straight into the control
  loop and therefore into stopping distance
* **jitter** - spread over a still target; anything wide means the medians and
  thresholds in 02_avoider need widening too
* **dead zone** - the closest reading it will produce before going silent

The number that matters most is the answer rate. A timed-out ping is not
"clear": it can equally be a wall at 3 cm reflecting the pulse away. If a
static, square-on target cannot hold near 100 %, no threshold downstream will
save the robot.
"""

import utime
import board
import sonar
from ST7789 import ST7789

BG, FG, DIM = 0x0000, 0xFFFF, 0x8410
ACCENT, WARN, OK, HILITE = 0xFF00, 0xF800, 0x001F, 0xFFE0
W, H = board.LCD_W, board.LCD_H

SHORT_US = 12000        # what 02_avoider uses in the control loop
FULL_US = 30000         # what it uses when stopped and deliberate


def burst(n, timeout_us):
    """n pings. Returns (values, total_ms)."""
    vals = []
    t0 = utime.ticks_ms()
    for _ in range(n):
        d = sonar.read(timeout_us)
        if d is not None:
            vals.append(d)
        utime.sleep_ms(10)          # let the echo tail die
    return vals, utime.ticks_diff(utime.ticks_ms(), t0) - n * 10


def stats(v):
    if not v:
        return None, None, None, None
    v = sorted(v)
    n = len(v)
    mean = sum(v) / n
    var = sum((x - mean) ** 2 for x in v) / n
    return v[0], v[-1], mean, var ** 0.5


def main():
    lcd = ST7789()
    print("sonar_check - point at a flat wall, 30-60 cm, and leave it alone")

    lcd.fill(BG)
    lcd.text("SONAR CHECK", 2, 2, ACCENT)
    lcd.hline(0, 12, W, DIM)
    lcd.text("sampling...", 2, 20, FG)
    lcd.show()

    N = 60
    rows = []
    for label, us in (("short %dms" % (SHORT_US // 1000), SHORT_US),
                      ("full  %dms" % (FULL_US // 1000), FULL_US)):
        vals, ms = burst(N, us)
        lo, hi, mean, sd = stats(vals)
        rate = 100 * len(vals) // N
        rows.append((label, rate, ms / N, mean, sd, lo, hi))
        print('{"t":"sonar","mode":"%s","answered":%d,"of":%d,"ms_per_ping":%.1f,'
              '"mean":%s,"sd":%s,"min":%s,"max":%s}' % (
                  label.split()[0], len(vals), N, ms / N,
                  "null" if mean is None else "%.1f" % mean,
                  "null" if sd is None else "%.2f" % sd,
                  "null" if lo is None else "%.1f" % lo,
                  "null" if hi is None else "%.1f" % hi))

    # Closest reading it will still produce, walking in from whatever it sees.
    closest = None
    for _ in range(40):
        d = sonar.read(FULL_US)
        if d is not None and (closest is None or d < closest):
            closest = d
        utime.sleep_ms(20)

    lcd.fill(BG)
    lcd.text("SONAR CHECK", 2, 2, ACCENT)
    lcd.hline(0, 12, W, DIM)
    y = 18
    lcd.text("mode     ans   ms   sd", 2, y, DIM); y += 11
    for label, rate, per, mean, sd, lo, hi in rows:
        lcd.text("%-9s %3d%% %4.1f %5s" % (
            label.split()[0], rate, per, "--" if sd is None else "%.1f" % sd),
            2, y, FG if rate > 90 else WARN)
        y += 11
    y += 4
    lo, hi, mean, sd = stats([r[3] for r in rows if r[3] is not None])
    lcd.text("mean %s cm" % ("--" if mean is None else "%.1f" % mean), 2, y, FG); y += 11
    lcd.text("closest %s cm" % ("--" if closest is None else "%.1f" % closest),
             2, y, FG); y += 11
    worst = min(r[1] for r in rows)
    lcd.text("a timeout is NOT clear", 2, y, HILITE if worst > 90 else WARN); y += 11
    lcd.text("it can be a wall at 3cm", 2, y, DIM)
    lcd.hline(0, H - 11, W, DIM)
    lcd.text("no motors were driven", 2, H - 9, DIM)
    lcd.show()

    print("\nanswer rate short/full: %d%% / %d%%" % (rows[0][1], rows[1][1]))
    print("cost per ping: %.1f ms short, %.1f ms full" % (rows[0][2], rows[1][2]))
    print("closest reading seen: %s cm" % ("none" if closest is None else "%.1f" % closest))
    if rows[0][1] < 90:
        print("WARNING: the short timeout is losing pings on a static target.")
        print("         Raise PING_US in 02_avoider, or expect frequent BLIND.")


try:
    main()
finally:
    board.estop()
