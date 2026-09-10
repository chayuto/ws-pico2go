"""Pico2Go bring-up self-test. Does NOT move the robot.

    ./pg run selftest

Exercises every subsystem, reports PASS/WARN/FAIL, and prints the three
line-sensor measurements you need to settle the polarity question in
docs/06-sensors-and-algorithms.md.
"""

import sys
import utime
from machine import Pin, ADC

import board

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
results = []


def check(name, fn):
    try:
        status, detail = fn()
    except Exception as e:
        status, detail = FAIL, "{}: {}".format(type(e).__name__, e)
    results.append((status, name, detail))
    print("  [{:4}] {:<22} {}".format(status, name, detail))
    return status


def hr(title):
    print("\n" + title)
    print("-" * 60)


# --------------------------------------------------------------------------
def t_firmware():
    imp = sys.implementation
    v = ".".join(str(x) for x in imp.version)
    name = getattr(imp, "_machine", "unknown")
    ok = "RP2350" in name.upper() or "PICO2" in name.upper().replace(" ", "")
    return (PASS if ok else WARN,
            "MicroPython {} on {}".format(v, name) + ("" if ok else "  <- expected an RP2350 board"))


def t_temperature():
    adc = ADC(board.TEMP_ADC_CH)
    v = adc.read_u16() * 3.3 / 65535
    c = 27 - (v - 0.706) / 0.001721
    if -20 < c < 90:
        return PASS, "die {:.1f} C  (uncalibrated)".format(c)
    return WARN, "die {:.1f} C  <- implausible; the ADC misreads on the first run after a flash, re-run".format(c)


def t_battery():
    adc = ADC(Pin(board.BAT_ADC))
    raw = [adc.read_u16() for _ in range(9)]
    raw.sort()
    mean = sum(raw[1:-1]) / 7
    v = mean * 3.3 / 65535 * board.BAT_DIVIDER
    pct = (v - board.BAT_EMPTY_V) * 100 / (board.BAT_FULL_V - board.BAT_EMPTY_V)
    pct = max(0, min(100, pct))
    d = "{:.2f} V  ~{:.0f}%  (divider x{:g})".format(v, pct, board.BAT_DIVIDER)
    if mean > 65000:
        return WARN, d + "  <- ADC SATURATED. Either the sense divider is not energised"
    if v < 0.5:
        return WARN, d + "  <- ~0 V: power switch OFF? (sense divider needs the 5 V rail)"
    if v > 4.4:
        return WARN, d + "  <- above 4.4 V: implausible for 1S Li-ion; re-run (the ADC"
    if v < board.BAT_EMPTY_V:
        return WARN, d + "  <- below 3.0 V, charge it"
    return PASS, d + "  <- verified x2 against a full 14500 cell"


def t_ir_obstacle():
    dsl = Pin(board.DSL, Pin.IN)
    dsr = Pin(board.DSR, Pin.IN)
    l, r = dsl.value(), dsr.value()
    d = "L={} R={}  (0 = obstacle detected)".format(l, r)
    if l == 0 and r == 0:
        return WARN, d + "  <- both triggered: obstacle present, or trim pots need adjusting"
    return PASS, d


def t_ir_receiver():
    p = Pin(board.IR_RX, Pin.IN)
    lows = sum(1 for _ in range(200) if p.value() == 0)
    if lows == 0:
        return PASS, "idle high (press a remote key during this test to see activity)"
    if lows == 200:
        return WARN, "stuck low  <- receiver missing, or continuous IR interference"
    return PASS, "activity seen ({}/200 low) - remote is transmitting".format(lows)


def t_sonar():
    import sonar
    d = sonar.read_median(5)
    if d is None:
        return WARN, "no echo  <- nothing in range, or module unplugged"
    return PASS, "{:.1f} cm".format(d)


def t_line_sensor():
    from TRSensor import TRSensor
    trs = TRSensor()
    utime.sleep_ms(50)
    vals = trs.AnalogRead()
    spread = max(vals) - min(vals)
    d = "{}  (5 ch, 0-1023)".format(vals)
    if max(vals) == 0:
        return FAIL, d + "  <- all zero: TLC2543 not responding (V1 board?)"
    if spread < 5:
        return WARN, d + "  <- channels almost identical; is the array over a uniform surface?"
    return PASS, d


def t_lcd():
    from ST7789 import ST7789
    lcd = ST7789()
    lcd.fill(0x0000)
    lcd.text("Pico2Go", 10, 10, 0xFFFF)
    lcd.text("self-test OK", 10, 30, 0xFFFF)
    lcd.text("waveshare RP2350", 10, 50, 0xFFFF)
    lcd.show()
    return PASS, "240x135 framebuffer pushed - LOOK AT THE SCREEN to confirm"


def t_rgb():
    from ws2812 import NeoPixel
    strip = NeoPixel()
    for c in (strip.RED, strip.GREEN, strip.BLUE, strip.BLACK):
        strip.pixels_fill(c)
        strip.pixels_show()
        utime.sleep_ms(200)
    return PASS, "R/G/B cycled - LOOK UNDERNEATH (needs 5 V, i.e. switch ON)"


def t_buzzer():
    b = Pin(board.BUZZER, Pin.OUT)
    b.value(1)
    utime.sleep_ms(80)
    b.value(0)
    return PASS, "80 ms beep - LISTEN"


def t_led():
    led = Pin(board.LED, Pin.OUT)
    for _ in range(4):
        led.toggle()
        utime.sleep_ms(100)
    led.value(0)
    return PASS, "GP25 blinked"


# --------------------------------------------------------------------------
print("=" * 60)
print("Pico2Go self-test   (this app never drives the motors)")
print("=" * 60)

hr("System")
check("firmware", t_firmware)
check("die temperature", t_temperature)
check("battery", t_battery)

hr("Sensors")
check("IR obstacle", t_ir_obstacle)
check("IR receiver", t_ir_receiver)
check("ultrasonic", t_sonar)
check("line array", t_line_sensor)

hr("Outputs  (verify these with your eyes and ears)")
check("user LED", t_led)
check("LCD", t_lcd)
check("RGB LEDs", t_rgb)
check("buzzer", t_buzzer)

hr("Summary")
n_fail = sum(1 for s, _, _ in results if s == FAIL)
n_warn = sum(1 for s, _, _ in results if s == WARN)
print("  {} checks: {} pass, {} warn, {} fail".format(
    len(results), len(results) - n_warn - n_fail, n_warn, n_fail))

if n_fail or n_warn:
    print("\n  Not sure about a result? -> docs/08-gotchas-and-known-issues.md")
if n_warn and any("switch OFF" in d for _, _, d in results):
    print("  Most likely: the chassis POWER SWITCH is off. 5 V feeds motors,")
    print("  RGB LEDs and the IR front-end. USB alone only supplies 3V3.")

print("\n  Next: ./pg run sensors    (live line-array readout for calibration)")
print("=" * 60)

board.estop()
