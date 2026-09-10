"""Identify motor direction and channel, with the panel telling you what to watch.

    ./pg run motion_id 45        # WHEELS OFF THE GROUND

There are no encoders, so the only instrument for this is your eyes -- and the
first attempt failed because the prompts went to a terminal nobody was looking
at. Everything here goes to the LCD instead.

Each move is announced for three seconds before it happens, as a diagram: two
boxes for the two wheels, the active one lit, with arrows for the direction it
should turn. Then it runs, slowly, for long enough to see. The sequence
repeats, so a missed step comes round again.

Four questions, and only these four:

  1. does FORWARD actually drive forwards, or is the polarity inverted
  2. does BACKWARD do the opposite
  3. is channel A the LEFT wheel, as board.py assumes
  4. is channel B the RIGHT wheel

Get 1 or 3 wrong and an avoider drives into things confidently.
"""

import utime
import board
import drive
from ST7789 import ST7789

BG, FG, DIM = 0x0000, 0xFFFF, 0x8410
ACCENT, WARN, OK, HILITE = 0xFF00, 0xF800, 0x001F, 0xFFE0
W, H = board.LCD_W, board.LCD_H

SPEED = 25          # slow: this is about seeing direction, not performance
MOVE_MS = 2200
WARN_MS = 3000

# label, left wheel, right wheel  (-1 back, 0 still, +1 forward)
STEPS = (
    ("BOTH FORWARD",  +1, +1),
    ("BOTH BACKWARD", -1, -1),
    ("LEFT WHEEL",    +1,  0),
    ("RIGHT WHEEL",    0, +1),
)


def wheel_box(lcd, x, state, live):
    """One wheel: a box, filled while actually moving, arrows for direction."""
    col = DIM if state == 0 else (OK if live else HILITE)
    lcd.rect(x, 52, 60, 46, col)
    if state:
        if live:
            lcd.fill_rect(x + 2, 54, 56, 42, col)
        ac = BG if live else col
        for i in range(3):                       # three chevrons
            base = 60 + i * 12 if state > 0 else 88 - i * 12
            for k in range(7):
                yy = base + (k if state > 0 else -k)
                lcd.hline(x + 30 - (k + 1), yy, (k + 1) * 2, ac)
    else:
        lcd.text("--", x + 22, 71, DIM)


def frame(lcd, label, l, r, live, secs_left, cyc, cycles):
    lcd.fill(BG)
    lcd.text("MOTION ID", 2, 2, ACCENT)
    lcd.text("pass %d/%d" % (cyc, cycles), W - 66, 2, DIM)
    lcd.hline(0, 12, W, DIM)
    lcd.text("NOW MOVING:" if live else "GET READY:", 2, 18, OK if live else HILITE)
    lcd.text(label, 100, 18, FG)
    lcd.text("LEFT", 34, 40, DIM)
    lcd.text("RIGHT", 170, 40, DIM)
    wheel_box(lcd, 20, l, live)
    wheel_box(lcd, 160, r, live)
    lcd.text("chevrons up = forward", 2, 104, DIM)
    lcd.text("%ds" % secs_left, W - 26, 104, FG)
    lcd.hline(0, H - 11, W, DIM)
    lcd.text("WHEELS OFF THE GROUND" if live else "watch the wheels", 2, H - 9,
             WARN if live else DIM)
    lcd.show()


def hold(lcd, dr, label, l, r, live, ms, cyc, cycles):
    t0 = utime.ticks_ms()
    while True:
        el = utime.ticks_diff(utime.ticks_ms(), t0)
        if el >= ms:
            return
        if live:
            dr.set(l * SPEED, r * SPEED)     # re-issued: the deadman is 300 ms
        dr.tick()
        frame(lcd, label, l, r, live, (ms - el + 999) // 1000, cyc, cycles)


def main():
    try:
        limit_ms = int(PG_RUN_SECS) * 1000       # noqa: F821 - injected by pg
    except NameError:
        limit_ms = 45000

    lcd = ST7789()
    dr = drive.Drive()
    started = utime.ticks_ms()

    per_step = WARN_MS + MOVE_MS + 600
    cycles = max(1, limit_ms // (len(STEPS) * per_step))
    print("motion_id: %d pass(es), %d%% duty, %d ms per move" % (cycles, SPEED, MOVE_MS))

    stop = False
    try:
        for cyc in range(1, cycles + 1):
            for label, l, r in STEPS:
                print("  ready:  %s" % label)
                hold(lcd, dr, label, l, r, False, WARN_MS, cyc, cycles)
                print("  MOVING: %s   L=%+d R=%+d" % (label, l, r))
                hold(lcd, dr, label, l, r, True, MOVE_MS, cyc, cycles)
                dr.brake()
                utime.sleep_ms(600)
                if utime.ticks_diff(utime.ticks_ms(), started) > limit_ms - 2000:
                    stop = True
                    break
            if stop:
                break
    finally:
        dr.release()

    lcd.fill(BG)
    lcd.rect(0, 0, W, H, DIM)
    lcd.text("MOTION ID DONE", 12, 14, ACCENT)
    lcd.hline(12, 26, W - 24, DIM)
    lcd.text("did FORWARD go forward?", 12, 40, FG)
    lcd.text("was LEFT WHEEL the left?", 12, 54, FG)
    lcd.text("if either was wrong,", 12, 76, HILITE)
    lcd.text("board.py needs swapping.", 12, 88, HILITE)
    lcd.text("motors stopped.", 12, 112, DIM)
    lcd.show()
    print("\nDone. Did FORWARD go forwards, and was LEFT WHEEL the left one?")


try:
    main()
finally:
    board.estop()
