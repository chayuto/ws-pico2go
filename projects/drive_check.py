"""Motor check. THE ROBOT MOVES -- put it on a book so the wheels hang free.

    ./pg run drive_check 20

Requires the chassis power switch to be ON: the TB6612's motor supply is the
battery-derived 5 V rail, not USB.
"""

import utime
import board
from Motor import PicoGo

M = PicoGo()

STEPS = (
    ("forward",     lambda: M.forward(40)),
    ("backward",    lambda: M.backward(40)),
    ("spin left",   lambda: M.left(30)),
    ("spin right",  lambda: M.right(30)),
    ("left wheel",  lambda: M.setMotor(40, 0)),
    ("right wheel", lambda: M.setMotor(0, 40)),
    ("arc",         lambda: M.setMotor(50, 25)),
)

print("Wheels off the ground? Starting in 3 s...")
utime.sleep(3)

try:
    for name, fn in STEPS:
        print("  ->", name)
        fn()
        utime.sleep_ms(700)
        M.stop()
        utime.sleep_ms(400)
    print("\nDone. If nothing moved: the POWER SWITCH is off, or the cells are flat.")
    print("If it moved but veered: that is expected -- there are no encoders.")
finally:
    board.estop()
