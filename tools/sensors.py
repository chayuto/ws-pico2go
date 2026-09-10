"""Live sensor readout. Does NOT move the robot.

    ./pg run sensors 30

Use this to settle the line-sensor polarity question (docs/06 section 6.2):
hold the robot over WHITE, then over BLACK TAPE, then IN THE AIR, and read off
the centre-channel value each time.

  black > white  -> vendor default is right: readLine() as shipped
  white > black  -> you need readLine(white_line=1)
"""

import utime
from machine import Pin, ADC

import board
import sonar
from TRSensor import TRSensor

trs = TRSensor()
dsl = Pin(board.DSL, Pin.IN)
dsr = Pin(board.DSR, Pin.IN)
bat = ADC(Pin(board.BAT_ADC))

print("line array (IR1..IR5, left->right) | obstacle | sonar | batt")
print("-" * 72)

try:
    while True:
        vals = trs.AnalogRead()
        d = sonar.read()
        v = bat.read_u16() * 3.3 / 65535 * board.BAT_DIVIDER
        print("{:>4} {:>4} {:>4} {:>4} {:>4}  | L{} R{}   | {:>7} | {:.2f}V".format(
            vals[0], vals[1], vals[2], vals[3], vals[4],
            dsl.value(), dsr.value(),
            "--" if d is None else "{:.1f}cm".format(d),
            v))
        utime.sleep_ms(300)
except KeyboardInterrupt:
    pass
finally:
    board.estop()
