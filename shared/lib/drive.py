"""Motion with a brake, a speed ceiling, a deadman and a dry-run switch.

A thin layer over the vendor `Motor.PicoGo`, which is left byte-for-byte as
Waveshare shipped it so their docs keep applying. Everything here is what the
vendor class does not give you and an autonomous robot needs:

* **brake** — `PicoGo.stop()` sets both PWM to zero and both direction pins
  low. That is *coast*: the H-bridge goes high-impedance and the robot rolls
  on. The TB6612 has a real short-brake (both direction inputs HIGH), which is
  the difference between stopping at 20 cm and hitting the wall.
* **a speed ceiling** — nothing this module emits can exceed `max_speed`, so a
  bad constant in an app cannot launch the robot across the room.
* **a deadman** — every command carries an expiry. `tick()` cuts power if the
  control loop has not refreshed it in time. See the honest limits below.
* **dry run** — with `dry=True` the class never imports or instantiates
  `PicoGo`, so GP16-GP21 are not even configured as outputs. The whole
  behaviour above the motors can then be exercised on a desk with the robot
  guaranteed inert.

There are no encoders on this platform. Speeds are duty cycles, not velocities,
and they sag with the battery. Nothing here changes that.
"""

import utime
import board

# Ceiling for anything this module will emit, in percent duty. The chassis is
# geared low and 100 % on a fresh pack is faster than the ultrasonic loop can
# react to. Raise deliberately, per app, never globally.
MAX_SPEED = 60

# A command older than this is stale. Sized to be comfortably longer than a
# worst-case control tick (ping 12 ms + LCD blit 78 ms + slack) so that a
# healthy loop never trips it, and a wedged one trips it fast.
CMD_TTL_MS = 300

# Per-wheel correction for the fact that two N20 motors are never identical.
# Measure on your own robot: drive straight for 2 m and see which way it veers.
TRIM_L = 1.00
TRIM_R = 1.00

# Short-brake dwell. Long enough to actually arrest the chassis, short enough
# that it is not a meaningful blocking call in a control loop.
BRAKE_MS = 120


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class Drive:
    """Bounded, brakeable, deadman-guarded differential drive.

    Every method that commands motion refreshes the deadman. `tick()` must be
    called once per control-loop iteration.
    """

    def __init__(self, dry=False, max_speed=MAX_SPEED, ttl_ms=CMD_TTL_MS,
                 trim=(TRIM_L, TRIM_R)):
        self.dry = bool(dry)
        self.max = int(_clamp(max_speed, 0, 100))
        self.ttl = int(ttl_ms)
        self.trim_l, self.trim_r = trim

        self.l = 0                 # last commanded left,  -100..100
        self.r = 0                 # last commanded right
        self.braking = False

        self.moving_ms = 0         # cumulative time under power
        self.stalls = 0            # deadman trips
        self.commands = 0

        self._deadline = utime.ticks_ms()
        self._last = utime.ticks_ms()

        # In dry mode PicoGo is never constructed, so GP16-GP21 stay untouched
        # -- not merely idle, but not claimed as outputs at all.
        self.m = None
        if not self.dry:
            from Motor import PicoGo
            self.m = PicoGo()

    # -- primitives -------------------------------------------------------
    def _speed(self, v, trim):
        v = int(v * trim)
        return int(_clamp(v, -self.max, self.max))

    def set(self, l, r):
        """Signed per-wheel duty, -100..100. The one command everything uses."""
        self.l = self._speed(l, self.trim_l)
        self.r = self._speed(r, self.trim_r)
        self.braking = False
        self.commands += 1
        self._deadline = utime.ticks_add(utime.ticks_ms(), self.ttl)
        if self.m is not None:
            self.m.setMotor(self.l, self.r)

    def forward(self, s):
        self.set(s, s)

    def backward(self, s):
        self.set(-s, -s)

    def pivot(self, side, s):
        """Turn on the spot. side is 'L' or 'R'."""
        self.set(-s, s) if side == "L" else self.set(s, -s)

    def arc(self, s, curve):
        """Forward at s, biased by curve (-1 hard left .. +1 hard right)."""
        curve = _clamp(curve, -1.0, 1.0)
        inner = int(s * (1.0 - 2.0 * abs(curve)))
        return self.set(inner, s) if curve < 0 else self.set(s, inner)

    def coast(self):
        """High-impedance. The robot keeps rolling -- rarely what you want."""
        self.l = self.r = 0
        self.braking = False
        if self.m is not None:
            self.m.stop()

    def brake(self, ms=BRAKE_MS):
        """TB6612 short brake: both direction inputs HIGH. Blocks for `ms`,
        then releases to coast so the bridge is not held shorted."""
        self.l = self.r = 0
        self.braking = True
        self._deadline = utime.ticks_add(utime.ticks_ms(), self.ttl)
        if self.m is not None:
            m = self.m
            m.AIN1.value(1); m.AIN2.value(1)
            m.BIN1.value(1); m.BIN2.value(1)
            m.PWMA.duty_u16(0xFFFF); m.PWMB.duty_u16(0xFFFF)
        utime.sleep_ms(ms)
        self.braking = False
        if self.m is not None:
            self.m.stop()

    def halt(self):
        """Instant, non-blocking, never raises. Safe from anywhere."""
        self.l = self.r = 0
        self.braking = False
        if self.m is not None:
            self.m.stop()
        # In dry mode there is deliberately nothing to do: the pins were never
        # claimed, and calling estop() here would claim them as outputs.

    # -- the deadman ------------------------------------------------------
    def tick(self):
        """Call once per control-loop iteration.

        Returns False if the deadman fired. It catches a control loop that has
        gone *slow* -- a long blocking read, an over-fat render, a burst of GC.
        It cannot catch a loop that has gone *dead*, because then nothing calls
        it. That case is covered by `board.estop()` in a `finally:` and by the
        EXIT/INT/TERM trap in `pg run`. A hardware WDT would cover it too, but
        a WDT reset re-runs main.py, which on a robot with wheels means it
        drives off again with nobody watching -- so this repo does not use one.
        """
        now = utime.ticks_ms()
        dt = utime.ticks_diff(now, self._last)
        self._last = now
        if self.l or self.r:
            self.moving_ms += dt
            if utime.ticks_diff(now, self._deadline) > 0:
                self.stalls += 1
                self.halt()
                return False
        return True

    def moving(self):
        return bool(self.l or self.r)

    def release(self):
        """End of run. Belt and braces, and never raises."""
        try:
            self.halt()
        except Exception:
            pass
        if not self.dry:
            board.estop()
