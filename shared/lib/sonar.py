"""Ultrasonic ranging that cannot hang.

Waveshare's dist() spins in `while Echo.value() == 0: pass` with no timeout.
On a missed echo -- out of range, angled wall, soft surface, unplugged module
-- it never returns, and the robot keeps driving with no code running. This is
the most likely cause of a Pico2Go 'freezing' mid-run.

See docs/06-sensors-and-algorithms.md section 6.4.
"""

from machine import Pin
import utime
import board

_MAX_CM = 400.0
# 30 ms of round trip is ~5 m -- comfortably past the sensor's usable range.
_TIMEOUT_US = 30000

_trig = Pin(board.US_TRIG, Pin.OUT)
_echo = Pin(board.US_ECHO, Pin.IN)
_trig.value(0)


def read(timeout_us=_TIMEOUT_US):
    """Distance in cm, or None on timeout. Never blocks indefinitely."""
    _trig.value(1)
    utime.sleep_us(10)          # NB: the vendor 'follow' demo uses sleep_ms -- a bug
    _trig.value(0)

    t0 = utime.ticks_us()
    while _echo.value() == 0:
        if utime.ticks_diff(utime.ticks_us(), t0) > timeout_us:
            return None
    ts = utime.ticks_us()

    while _echo.value() == 1:
        if utime.ticks_diff(utime.ticks_us(), ts) > timeout_us:
            return None
    te = utime.ticks_us()

    cm = (utime.ticks_diff(te, ts) * 0.0343) / 2   # 343 m/s at ~20 C
    return cm if 0 < cm <= _MAX_CM else None


def read_median(n=5, timeout_us=_TIMEOUT_US):
    """Median of n pings, ignoring timeouts. None if every ping failed.

    Ultrasound is spiky -- a single specular reflection gives a wild reading.
    A median of 5 costs ~5 ms and removes nearly all of them.
    """
    vals = []
    for _ in range(n):
        d = read(timeout_us)
        if d is not None:
            vals.append(d)
        utime.sleep_ms(10)      # let the echo tail die down between pings
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]
