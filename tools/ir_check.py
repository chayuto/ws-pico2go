"""Settle the IR obstacle detectors: are they miscalibrated, or inverted?

    ./pg run ir_check 45

Wave a hand slowly across the LEFT sensor, then the RIGHT one. The LCD shows
both pins live and counts every transition; the serial link logs each one.

The polarity is not in doubt, and no hand is needed to establish it. The LM393
output is **open-collector** and GP2/GP3 carry external pull-ups (measured:
both held high against a 60 K internal pull-down). An open-collector output
idles high-impedance, so the pull-up decides the idle level: **idle is HIGH,
and LOW is the comparator actively sinking.** Active LOW is correct.

So a pin sitting LOW in open space means the comparator is asserted, which
means the trim pot for that sensor is wound too sensitive -- or the surface
under the robot is reflective enough to trip it.

**The pots are calibrated by eye, not by code.** Two green LEDs on the front
mirror the comparator outputs. Waveshare's own procedure: if an LED is always
on, turn that sensor's pot on the underside until it *just* goes out. That is
the point of maximum detection distance. This tool then confirms it.

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
        if idle_l == 0 or idle_r == 0:
            verdict = ["ASSERTED, NOT MOVING.", "",
                       "L=%d R=%d  (0 = detect)" % (idle_l, idle_r),
                       "the green front LEDs are on.",
                       "turn that pot underneath",
                       "until the LED just goes out."]
            print("\nStuck asserted: L=%d R=%d, and 0 means detect." % (idle_l, idle_r))
            print("The comparator is sinking, so its pot is too sensitive.")
            print("Look at the green LEDs on the front - the asserted side is lit.")
            print("Turn that sensor's pot on the underside until the LED just goes out.")
        else:
            verdict = ["IDLE AND CLEAR.", "",
                       "L=%d R=%d, nothing near." % (idle_l, idle_r),
                       "wave a hand to confirm",
                       "they can still detect."]
            print("\nBoth clear and stable. Wave a hand to confirm they still fire.")
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
