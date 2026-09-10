"""Settle the IR obstacle detectors: are they miscalibrated, or inverted?

    ./pg run ir_check 45

Wave a hand slowly across the LEFT sensor, then the RIGHT one. The LCD shows
both pins live and counts every transition; the serial link logs each one.

Two hypotheses, and only a hand can separate them:

* `board.py` says these are **active LOW** (LOW = obstacle). If they sit LOW in
  open space, the trim pots on the underside are wound too sensitive and the
  comparators are latched on.
* Or the polarity is inverted on this board (LOW = clear), in which case they
  are idle and healthy and the pin map comment is wrong.

If a hand makes the pin change, the reading that *appears* when the hand is
there is the "obstacle" state, and that settles it. If nothing ever changes,
it is the pots -- or the emitters are dark, which means the 5 V rail is down
and the chassis power switch is off.

Never drives the motors.
"""

import utime
import board
from machine import Pin
from ST7789 import ST7789

BG, FG, DIM = 0x0000, 0xFFFF, 0x8410
ACCENT, WARN, OK, HILITE = 0xFF00, 0xF800, 0x001F, 0xFFE0
W, H = board.LCD_W, board.LCD_H


def main():
    lcd = ST7789()
    dsl = Pin(board.DSL, Pin.IN)
    dsr = Pin(board.DSR, Pin.IN)

    try:
        limit_ms = int(PG_RUN_SECS) * 1000       # noqa: F821 - injected by pg
    except NameError:
        limit_ms = 40000

    pl, pr = dsl.value(), dsr.value()
    idle_l, idle_r = pl, pr
    tl = tr = 0
    seen_l = {pl}
    seen_r = {pr}
    t0 = utime.ticks_ms()
    print("ir_check: idle GP3(left)=%d GP2(right)=%d -- wave a hand" % (pl, pr))

    while utime.ticks_diff(utime.ticks_ms(), t0) < limit_ms:
        l, r = dsl.value(), dsr.value()
        if l != pl:
            tl += 1
            seen_l.add(l)
            print('{"t":"ir","pin":"left","gp":3,"now":%d,"was":%d,"n":%d}' % (l, pl, tl))
        if r != pr:
            tr += 1
            seen_r.add(r)
            print('{"t":"ir","pin":"right","gp":2,"now":%d,"was":%d,"n":%d}' % (r, pr, tr))
        pl, pr = l, r

        lcd.fill(BG)
        lcd.text("IR OBSTACLE CHECK", 2, 2, ACCENT)
        lcd.hline(0, 12, W, DIM)
        lcd.text("WAVE A HAND across each", 2, 18, HILITE)
        lcd.text("sensor, one at a time", 2, 29, HILITE)
        lcd.text("LEFT  GP3   %d" % l, 2, 48, FG)
        lcd.fill_rect(150, 46, 40, 12, OK if l else WARN)
        lcd.text("changed %d" % tl, 2, 60, DIM if tl == 0 else FG)
        lcd.text("RIGHT GP2   %d" % r, 2, 78, FG)
        lcd.fill_rect(150, 76, 40, 12, OK if r else WARN)
        lcd.text("changed %d" % tr, 2, 90, DIM if tr == 0 else FG)
        lcd.hline(0, H - 11, W, DIM)
        lcd.text("%ds left   no motors" % (
            (limit_ms - utime.ticks_diff(utime.ticks_ms(), t0)) // 1000), 2, H - 9, DIM)
        lcd.show()

    verdict = []
    if tl == 0 and tr == 0:
        verdict = ["NOTHING MOVED.", "",
                   "stuck at L=%d R=%d." % (idle_l, idle_r),
                   "trim pots, or no hand."]
        print("\nNo transition on either pin.")
        print("Either no hand was presented, or both comparators are latched.")
        print("The pots are two small screws on the underside, one per sensor.")
    else:
        for name, t, seen, idle in (("left", tl, seen_l, idle_l),
                                    ("right", tr, seen_r, idle_r)):
            if t:
                other = [v for v in seen if v != idle]
                print("%s: idle=%d, goes to %s with a hand -> obstacle reads %s"
                      % (name, idle, other, other[0] if other else "?"))
        verdict = ["left  changed %d" % tl, "right changed %d" % tr, "",
                   "idle L=%d R=%d" % (idle_l, idle_r),
                   "see the serial log."]

    lcd.fill(BG)
    lcd.rect(0, 0, W, H, DIM)
    lcd.text("IR CHECK DONE", 12, 14, ACCENT)
    lcd.hline(12, 26, W - 24, DIM)
    y = 36
    for line in verdict:
        lcd.text(line, 12, y, FG)
        y += 11
    lcd.show()


try:
    main()
finally:
    board.estop()
