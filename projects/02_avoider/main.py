"""02_avoider - reactive obstacle avoidance on one forward ultrasonic beam.

    ./pg dry avoider 60      # full behaviour, motors never touched
    ./pg run avoider 60      # WHEELS OFF THE GROUND FIRST

The robot drives forward, slows as something closes, brakes before it hits,
backs off, turns its whole body to look left and right, and takes the freer
side. It has one fixed forward-facing HC-SR04 and two short-range IR obstacle
detectors, no encoders, and no way to know where it is. Everything here is
reactive; none of it is navigation.

The three facts that shape the whole design
-------------------------------------------
1. **A timed-out ping is not "clear".** No echo means one of: nothing within
   range, a surface angled or soft enough to reflect the pulse away, or a
   target inside the sensor's ~2 cm dead zone. The last two are directly in
   front of you. `None` is therefore treated as *unknown*, never as open road.
2. **Fast to stop, slow to go.** One reading under the stop threshold brakes
   immediately - a false brake costs nothing. Resuming needs three consecutive
   clear readings. The asymmetry is the safety margin.
3. **The blit is not in the control path.** A full ST7789 frame costs 78 ms.
   Sensing and deciding run every ~45 ms; the screen is redrawn a few times a
   second. Letting the panel set the control rate would make the robot blind
   for most of its life.

Safety
------
`drive.Drive` caps speed, brakes rather than coasting, and carries a deadman.
`board.estop()` runs in a `finally:`. Unlike 01_sensorous this app does **not**
restart itself after an unhandled exception: an avoider that resurrects with an
unknown fault, on wheels, with nobody watching, is worse than a stopped one.
"""

import gc
import sys
import utime
from machine import Pin, ADC

import board
import sonar
import drive
from ST7789 import ST7789
from ws2812 import NeoPixel

# ---------------------------------------------------------------- tuning
TICK_MS      = 45         # control period; sense -> decide -> actuate
RENDER_MS    = 400        # while moving; the screen is a passenger
RENDER_IDLE  = 200        # while stopped there is time to spare
RENDER_MIN   = 150        # floor, so a flickering state cannot own the loop

CRUISE       = 45         # percent duty, not a speed - there are no encoders
CREEP        = 28         # used when the sensor has stopped answering
TURN_SPEED   = 40
BACK_SPEED   = 35

STOP_CM      = 20.0       # brake at or below this
SLOW_CM      = 45.0       # start easing off here
CLEAR_CM     = 60.0       # open road
CLEAR_RUN    = 3          # ...but only after this many in a row

# 12 ms of flight is ~2 m. Anything further is "clear" for avoidance purposes,
# and halving the worst-case ping cost halves the worst-case reaction latency.
PING_US      = 12000
SCAN_PING_US = 30000      # stationary, deliberate, can afford the full wait

BLIND_N      = 3          # consecutive timeouts before trusting the beam less
BLIND_MS     = 900        # blind for this long => assume a flush wall, go look
# Speed while the forward beam is silent. Deliberately below CREEP: the only
# thing still watching is a pair of IR detectors that see about 6 cm past the
# bumper, so this is the distance-per-second the robot is willing to cover
# with no real forward sensor.
BLIND_SPEED  = 22

BACK_MS      = 500
BACK_LONG_MS = 900
# Reversing is blind. There is no rear sensor and no free pin to add one to,
# so every centimetre backwards is taken on trust. The one thing the robot
# does know about the space behind it is that it just drove forward through
# it -- so it may reverse for at most as long as it has just been going
# forward, and a pivot spends that credit entirely, because after turning,
# "behind" is somewhere it has never been. This is the closest thing to
# odometry available on a robot with no encoders.
PIVOT_CM      = 14.0      # clearance ahead needed to simply turn on the spot
CREDIT_MAX_MS = 900       # cap: past this the estimate is fiction
MIN_BACK_MS   = 150       # a shorter reverse is not worth the risk
SCAN_MS      = 260        # quarter-ish turn; timing only, drifts with battery
SETTLE_MS    = 140        # let the chassis stop ringing before ranging
TURN_MS      = 700
ESCAPE_TURN  = 1100

STUCK_N      = 3          # avoid events...
STUCK_MS     = 10000      # ...inside this window means it is trapped

BAT_HALT_V   = 3.30       # motors misbehave long before the cells are empty
RAIL_DOWN_V  = 2.50       # divider is fed from the 5 V rail: low => switch off
BAT_EVERY_MS = 2000       # and only while stopped - motor inrush sags the rail

# ---------------------------------------------------------------- palette
# Vendor RGB565 constants are not textbook (its GREEN is 0x001F). Only BLACK
# and WHITE are certain; the rest keep Waveshare's own names and values.
BG, FG, DIM = 0x0000, 0xFFFF, 0x8410
ACCENT, WARN, OK, HILITE = 0xFF00, 0xF800, 0x001F, 0xFFE0

W, H = board.LCD_W, board.LCD_H

STATE_COLOUR = {
    "ARMING": (60, 40, 0), "CRUISE": (0, 55, 0),  "SLOW":  (55, 30, 0),
    "BLIND":  (0, 30, 55), "BRAKE":  (70, 0, 0),  "BACK":  (70, 0, 0),
    "SCAN":   (0, 0, 60),  "TURN":   (50, 0, 55), "ESCAPE": (60, 0, 60),
    "HALT":   (25, 0, 0),  "FAULT":  (70, 0, 0),
}


# ---------------------------------------------------------------- sensing
class Nav:
    """Forward beam plus two short-range side detectors, fused.

    The IR pair is not a nicety. It sees exactly the case ultrasound misses -
    a close, angled or soft surface that returns no echo - and it reports which
    side, which is the only lateral information this robot has.
    """

    def __init__(self):
        self.dsl = Pin(board.DSL, Pin.IN)      # active LOW
        self.dsr = Pin(board.DSR, Pin.IN)
        self.echo = Pin(board.US_ECHO, Pin.IN)
        self.bat = ADC(Pin(board.BAT_ADC))
        self.die = ADC(board.TEMP_ADC_CH)

        self.d = None              # last valid range, cm
        self.raw = None            # this tick's reading, None on timeout
        self.hist = []             # one sample per pixel column
        self.blind = 0             # consecutive timeouts
        self.blind_since = None
        self.clear_run = 0         # consecutive readings above CLEAR_CM
        self.pings = 0
        self.timeouts = 0

        self.ir_l = False
        self.ir_r = False
        self.ir_hits = 0

        self.volts = 0.0
        self.pct = 0
        self.temp_c = 0.0
        self._bat_at = -BAT_EVERY_MS

    def ping(self, timeout_us=PING_US):
        d = sonar.read(timeout_us)
        self.pings += 1
        if d is None:
            self.timeouts += 1
        return d

    def sense(self, stopped):
        self.raw = self.ping()
        if self.raw is None:
            self.blind += 1
            if self.blind == BLIND_N:
                self.blind_since = utime.ticks_ms()
            self.clear_run = 0
        else:
            self.blind = 0
            self.blind_since = None
            self.d = self.raw
            self.hist.append(self.raw)
            if len(self.hist) > W:
                self.hist.pop(0)
            self.clear_run = self.clear_run + 1 if self.raw > CLEAR_CM else 0

        l, r = self.dsl.value() == 0, self.dsr.value() == 0
        if (l and not self.ir_l) or (r and not self.ir_r):
            self.ir_hits += 1
        self.ir_l, self.ir_r = l, r

        if stopped:
            now = utime.ticks_ms()
            if utime.ticks_diff(now, self._bat_at) > BAT_EVERY_MS:
                self._bat_at = now
                self.read_power()

    def read_power(self):
        v = [self.bat.read_u16() for _ in range(9)]
        v.sort()
        self.volts = v[4] * 3.3 / 65535 * board.BAT_DIVIDER
        p = (self.volts - board.BAT_EMPTY_V) * 100 / (board.BAT_FULL_V - board.BAT_EMPTY_V)
        self.pct = int(max(0, min(100, p)))
        t = [self.die.read_u16() for _ in range(5)]
        t.sort()
        self.temp_c = 27 - (t[2] * 3.3 / 65535 - 0.706) / 0.001721

    # -- fused judgements -------------------------------------------------
    def danger(self):
        """Something needs stopping for, right now."""
        return self.ir_l or self.ir_r or (self.raw is not None and self.raw <= STOP_CM)

    def unknown(self):
        """The beam has stopped answering for long enough to distrust it."""
        return self.blind >= BLIND_N

    def blind_ms(self):
        if self.blind_since is None:
            return 0
        return utime.ticks_diff(utime.ticks_ms(), self.blind_since)

    def look(self):
        """A deliberate, stationary measurement. Median of three, full timeout.

        This is the one place a median is worth its latency: the robot is
        already stopped, so the cost is time it is not using anyway.
        """
        vals = []
        for _ in range(3):
            d = self.ping(SCAN_PING_US)
            if d is not None:
                vals.append(d)
            utime.sleep_ms(12)
        if not vals:
            return None
        vals.sort()
        return vals[len(vals) // 2]

    def cruise_speed(self):
        """Scale duty with headroom, and be slow to go.

        One close reading is enough to brake; it takes CLEAR_RUN consecutive
        open readings to earn full speed back. A false brake costs a second, a
        false clear costs a collision, so the asymmetry is deliberate.
        """
        d = self.raw if self.raw is not None else self.d
        if d is None:
            return CREEP                     # unknown is never full speed
        if d <= SLOW_CM:
            return CREEP
        if d >= CLEAR_CM:
            return CRUISE if self.clear_run >= CLEAR_RUN else CREEP
        span = (d - SLOW_CM) / (CLEAR_CM - SLOW_CM)
        return int(CREEP + span * (CRUISE - CREEP))


# ---------------------------------------------------------------- drawing
def bar(lcd, x, y, w, h, frac, colour):
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    lcd.rect(x, y, w, h, DIM)
    fill = int((w - 2) * frac)
    if fill > 0:
        lcd.fill_rect(x + 1, y + 1, fill, h - 2, colour)


def render(lcd, n, dr, st, up, tick_ms, ev):
    lcd.fill(BG)
    lcd.text("AVOIDER", 2, 2, ACCENT)
    lcd.text(st.name, 84, 2, HILITE)
    lcd.text("%3ds" % up, W - 34, 2, DIM)
    lcd.hline(0, 12, W, DIM)

    d = n.raw if n.raw is not None else n.d
    if n.raw is None and n.blind >= BLIND_N:
        lcd.text("RANGE   no echo", 2, 17, WARN)
    elif d is None:
        lcd.text("RANGE     --", 2, 17, DIM)
    else:
        lcd.text("RANGE %6.1f cm%s" % (d, "" if n.raw is not None else " ?"),
                 2, 17, WARN if d <= STOP_CM else FG)

    # 0..100 cm, with the two thresholds marked so the numbers mean something.
    bar(lcd, 2, 28, W - 4, 11, 0.0 if d is None else min(d, 100.0) / 100.0,
        WARN if (d is not None and d <= STOP_CM) else OK)
    for cm, col in ((STOP_CM, WARN), (SLOW_CM, HILITE)):
        x = 2 + int((W - 6) * cm / 100.0)
        lcd.vline(x, 26, 15, col)

    lcd.text("L%s" % ("[HIT]" if n.ir_l else "[ - ]"), 2, 45,
             WARN if n.ir_l else DIM)
    lcd.text("R%s" % ("[HIT]" if n.ir_r else "[ - ]"), W - 50, 45,
             WARN if n.ir_r else DIM)
    lcd.text("ir x%d" % n.ir_hits, 96, 45, DIM)

    lcd.text("motor  L%+4d  R%+4d%s" % (dr.l, dr.r, " BRK" if dr.braking else ""),
             2, 58, FG if dr.moving() else DIM)
    lcd.text("avoid %d  escape %d  blind %d" % (ev[0], ev[1], ev[2]), 2, 69, DIM)
    lcd.text("batt %4.2fV %3d%%  %4.1fC" % (n.volts, n.pct, n.temp_c), 2, 80,
             FG if n.volts > BAT_HALT_V else WARN)

    # history, stretched across the panel whatever the fill level
    top, base, hgt = 92, 120, 28
    lcd.hline(0, top, W, DIM)
    lcd.hline(0, base, W, DIM)
    hist = n.hist
    ln = len(hist)
    if ln:
        hi = max(max(hist), 30.0)
        prev = None
        for px in range(W):
            v = hist[px * ln // W]
            yv = base - int(hgt * min(v, hi) / hi)
            col = WARN if v <= STOP_CM else OK
            if prev is None or abs(yv - prev) <= 1:
                lcd.pixel(px, yv, col)
            else:
                lcd.line(px - 1, prev, px, yv, col)
            prev = yv
        lcd.text("%.0f" % hi, 2, top + 2, DIM)

    lcd.hline(0, H - 11, W, DIM)
    if dr.dry:
        lcd.text("DRY RUN - motors untouched", 2, H - 9, HILITE)
    else:
        lcd.text("%dms tick  stall %d" % (tick_ms, dr.stalls), 2, H - 9, DIM)
    lcd.show()


def card(lcd, title, lines, colour=HILITE):
    lcd.fill(BG)
    lcd.rect(0, 0, W, H, DIM)
    lcd.text(title, 12, 14, colour)
    lcd.hline(12, 26, W - 24, DIM)
    y = 36
    for t in lines:
        lcd.text(t, 12, y, FG)
        y += 11
    lcd.show()


def ambient(strip, st, n):
    """Four LEDs, because you cannot read a 240x135 panel on a moving robot.
    Ends 1 and 2 mirror the side detectors; 0 and 3 carry the state colour."""
    c = STATE_COLOUR.get(st.name, (20, 20, 20))
    strip.pixels_set(0, c)
    strip.pixels_set(3, c)
    strip.pixels_set(1, (70, 0, 0) if n.ir_l else c)
    strip.pixels_set(2, (70, 0, 0) if n.ir_r else c)
    strip.pixels_show()


# ---------------------------------------------------------------- states
class State:
    """Current state plus its deadline and scratch space."""

    def __init__(self):
        self.name = "ARMING"
        self.since = utime.ticks_ms()
        self.until = utime.ticks_ms()
        self.step = 0
        self.side = "L"
        self.d_left = None
        self.d_right = None
        self.reason = ""

    def go(self, name, ms=0, reason=""):
        self.name = name
        self.since = utime.ticks_ms()
        self.until = utime.ticks_add(self.since, ms)
        self.step = 0
        if reason:
            self.reason = reason
        return name

    def expired(self):
        return utime.ticks_diff(utime.ticks_ms(), self.until) >= 0

    def age(self):
        return utime.ticks_diff(utime.ticks_ms(), self.since)


def preflight(n, dry):
    """Refuse to drive a robot whose only forward sensor might be dead.

    Returns None if good, else a reason string.
    """
    if Pin(board.US_ECHO, Pin.IN).value() == 1:
        return "ECHO STUCK HIGH"
    good = 0
    for _ in range(10):
        if n.ping(SCAN_PING_US) is not None:
            good += 1
        utime.sleep_ms(15)
    if good == 0 and not dry:
        return "NO ECHO IN 10 PINGS"
    n.read_power()
    if not dry:
        if n.volts < RAIL_DOWN_V:
            return "5V RAIL DOWN"
        if n.volts < BAT_HALT_V:
            return "BATTERY %.2fV" % n.volts
    return None


# ---------------------------------------------------------------- main
def main():
    try:
        dry = bool(PG_DRY)                       # noqa: F821 - injected by pg
    except NameError:
        dry = False
    try:
        limit_ms = int(PG_RUN_SECS) * 1000       # noqa: F821 - injected by pg
    except NameError:
        limit_ms = 0                             # 0 = until interrupted

    print("02_avoider -", "DRY RUN, motors untouched" if dry else "LIVE - wheels clear?")

    n = Nav()
    dr = drive.Drive(dry=dry)
    lcd = ST7789()
    strip = NeoPixel()
    st = State()

    avoids = 0
    escapes = 0
    blinds = 0
    credit = 0          # ms of reversing the robot has earned by going forward
    recent = []                 # timestamps of recent avoid events
    tick_ms = TICK_MS
    started = utime.ticks_ms()
    prev_t0 = started
    last_render = -RENDER_MS
    last_emit = utime.ticks_ms()
    rendered_state = ""

    arm_ms = 2500 if dry else 5000
    st.go("ARMING", arm_ms)
    card(lcd, "AVOIDER", [
        "dry run - no motors" if dry else "WHEELS OFF THE GROUND",
        "",
        "stop  %d cm    slow %d cm" % (STOP_CM, SLOW_CM),
        "cruise %d%%     max  %d%%" % (CRUISE, dr.max),
        "",
        "pre-flight...",
    ], ACCENT if dry else WARN)
    fault = preflight(n, dry)
    if fault:
        dr.halt()
        st.go("FAULT", 0, fault)

    try:
        while True:
            t0 = utime.ticks_ms()
            dt = utime.ticks_diff(t0, prev_t0)
            prev_t0 = t0
            if dr.l > 0 and dr.r > 0:
                credit = min(CREDIT_MAX_MS, credit + dt)     # earned
            elif dr.l < 0 and dr.r < 0:
                credit = max(0, credit - dt)                 # spent
            elif dr.l or dr.r:
                credit = 0              # pivoting: behind is now unknown
            stopped = not dr.moving()
            n.sense(stopped)
            if not dr.tick():
                print("deadman: control loop too slow, motors cut")

            # ---- pre-emption: nothing below gets to ignore this ----------
            if st.name in ("CRUISE", "SLOW", "BLIND") and n.danger():
                dr.brake()
                avoids += 1
                recent.append(utime.ticks_ms())
                while recent and utime.ticks_diff(recent[-1], recent[0]) > STUCK_MS:
                    recent.pop(0)
                # Back off only when too close to rotate, and never further
                # than the space it just came through.
                boxed = n.ir_l or n.ir_r or (n.raw is not None and n.raw < PIVOT_CM)
                if len(recent) >= STUCK_N:
                    escapes += 1
                    recent = []
                    esc = min(BACK_LONG_MS, credit)
                    if esc >= MIN_BACK_MS:
                        st.go("ESCAPE", esc, "trapped")
                        dr.backward(BACK_SPEED)
                    else:
                        st.side = "R" if st.side == "L" else "L"
                        st.go("TURN", ESCAPE_TURN, "trapped, nowhere to back")
                        dr.pivot(st.side, TURN_SPEED)
                elif boxed and min(BACK_MS, credit) >= MIN_BACK_MS:
                    st.go("BACK", min(BACK_MS, credit), "too close to turn")
                    dr.backward(BACK_SPEED)
                else:
                    st.go("SCAN", 0, "turn on the spot")

            # ---- states --------------------------------------------------
            name = st.name

            if name == "ARMING":
                if st.expired():
                    st.go("CRUISE", 0, "armed")

            elif name == "CRUISE" or name == "SLOW":
                if n.unknown():
                    blinds += 1
                    st.go("BLIND", 0, "no echo")
                    dr.forward(BLIND_SPEED)
                else:
                    s = n.cruise_speed()
                    dr.forward(s)
                    st.name = "SLOW" if s < CRUISE else "CRUISE"

            elif name == "BLIND":
                # The beam is silent. Creep, lean on the IR pair, and if it
                # stays silent assume a wall square-on and go and look.
                if not n.unknown():
                    st.go("CRUISE", 0, "echo back")
                elif n.blind_ms() > BLIND_MS:
                    dr.brake()
                    st.go("SCAN", 0, "blind too long")
                else:
                    dr.forward(BLIND_SPEED)

            elif name == "BACK" or name == "ESCAPE":
                if st.expired():
                    dr.brake()
                    if name == "ESCAPE":
                        st.side = "R" if st.side == "L" else "L"
                        st.go("TURN", ESCAPE_TURN, "escape turn")
                        dr.pivot(st.side, TURN_SPEED)
                    elif n.ir_l != n.ir_r:
                        # One side triggered and the other did not: that is
                        # real lateral information. Use it, skip the scan.
                        st.side = "R" if n.ir_l else "L"
                        st.go("TURN", TURN_MS, "turn away from IR")
                        dr.pivot(st.side, TURN_SPEED)
                    else:
                        st.go("SCAN", 0, "look both ways")
                elif credit <= 0:
                    dr.brake()                       # out of known-clear space
                    st.until = utime.ticks_ms()
                else:
                    dr.backward(BACK_SPEED)

            elif name == "SCAN":
                # Body-scan: no servo, so the chassis is the gimbal. Every
                # branch re-asserts the pivot, because a leg of this turn is
                # longer than the deadman's TTL and silence would cut power.
                if st.step == 0:
                    dr.pivot("L", TURN_SPEED)
                    st.until = utime.ticks_add(utime.ticks_ms(), SCAN_MS)
                    st.step = 1
                elif st.step == 1 and not st.expired():
                    dr.pivot("L", TURN_SPEED)
                elif st.step == 1:
                    dr.brake()
                    utime.sleep_ms(SETTLE_MS)
                    st.d_left = n.look()
                    dr.pivot("R", TURN_SPEED)
                    st.until = utime.ticks_add(utime.ticks_ms(), 2 * SCAN_MS)
                    st.step = 2
                elif st.step == 2 and not st.expired():
                    dr.pivot("R", TURN_SPEED)
                elif st.step == 2:
                    dr.brake()
                    utime.sleep_ms(SETTLE_MS)
                    st.d_right = n.look()
                    # No echo while stationary and already in trouble is the
                    # flush-wall case: score it as blocked, not as open.
                    sl = -1.0 if n.ir_l else (0.0 if st.d_left is None else st.d_left)
                    sr = -1.0 if n.ir_r else (0.0 if st.d_right is None else st.d_right)
                    if sl == sr:
                        st.side = "R" if st.side == "L" else "L"   # alternate
                    else:
                        st.side = "L" if sl > sr else "R"
                    # It is currently facing SCAN_MS worth to the right of
                    # where it started, so the two turns are not symmetric.
                    ms = TURN_MS + SCAN_MS if st.side == "L" else max(150, TURN_MS - SCAN_MS)
                    print('{"t":"scan","left":%s,"right":%s,"pick":"%s"}' % (
                        "null" if st.d_left is None else "%.1f" % st.d_left,
                        "null" if st.d_right is None else "%.1f" % st.d_right, st.side))
                    st.go("TURN", ms, "scanned")
                    dr.pivot(st.side, TURN_SPEED)

            elif name == "TURN":
                # The detector on the leading side is the one that matters.
                leading = n.ir_r if st.side == "R" else n.ir_l
                flips = st.step
                if st.expired():
                    dr.brake()
                    st.go("CRUISE", 0, "turned")
                elif leading and flips < 2:
                    # Turning into something. Abandon and try the other way -
                    # but only twice, or a corner becomes a perpetual flip.
                    dr.brake()
                    st.side = "R" if st.side == "L" else "L"
                    st.go("TURN", TURN_MS, "turn blocked")
                    st.step = flips + 1
                    dr.pivot(st.side, TURN_SPEED)
                elif leading:
                    escapes += 1
                    recent = []
                    dr.brake()
                    st.go("ESCAPE", BACK_LONG_MS, "boxed in")
                    dr.backward(BACK_SPEED)
                else:
                    dr.pivot(st.side, TURN_SPEED)

            elif name == "HALT" or name == "FAULT":
                dr.halt()

            # ---- battery guard, measured only while stopped ---------------
            if stopped and n.volts and n.volts < RAIL_DOWN_V and not dry:
                dr.halt()
                st.go("HALT", 0, "5V RAIL DOWN")
            elif stopped and BAT_HALT_V > n.volts > RAIL_DOWN_V and not dry:
                dr.halt()
                st.go("HALT", 0, "BATTERY %.2fV" % n.volts)

            # ---- output ---------------------------------------------------
            now = utime.ticks_ms()
            due = RENDER_IDLE if stopped else RENDER_MS
            gap = utime.ticks_diff(now, last_render)
            # A state change earns an early redraw, but never faster than
            # RENDER_MIN: CRUISE<->SLOW can flicker at the speed threshold, and
            # a 78 ms blit every 45 ms tick would leave no time to drive.
            if gap > due or (st.name != rendered_state and gap > RENDER_MIN):
                rendered_state = st.name
                last_render = now
                if st.name == "FAULT":
                    card(lcd, "PRE-FLIGHT FAILED", [st.reason, "",
                                                    "motors are not running.",
                                                    "check the sensor, the",
                                                    "power switch, the cells."], WARN)
                elif st.name == "HALT":
                    card(lcd, "HALTED", [st.reason, "", "motors stopped."], WARN)
                else:
                    render(lcd, n, dr, st, utime.ticks_diff(now, started) // 1000,
                           tick_ms, (avoids, escapes, blinds))
            ambient(strip, st, n)

            if utime.ticks_diff(now, last_emit) > 500:
                last_emit = now
                print(('{"t":"nav","up":%d,"state":"%s","why":"%s","d":%s,'
                       '"blind":%d,"irl":%d,"irr":%d,"l":%d,"r":%d,'
                       '"avoid":%d,"escape":%d,"pings":%d,"to":%d,'
                       '"v":%.2f,"credit":%d,"tick":%d,"heap":%d}') % (
                    utime.ticks_diff(now, started) // 1000, st.name, st.reason,
                    "null" if n.raw is None else "%.1f" % n.raw, n.blind,
                    1 if n.ir_l else 0, 1 if n.ir_r else 0, dr.l, dr.r,
                    avoids, escapes, n.pings, n.timeouts, n.volts,
                    credit, tick_ms, gc.mem_free()))

            if limit_ms and utime.ticks_diff(now, started) > limit_ms:
                dr.brake()
                dr.halt()
                print("time limit reached, stopping cleanly")
                card(lcd, "AVOIDER STOPPED", [
                    "time limit",
                    "",
                    "ran %ds" % (utime.ticks_diff(now, started) // 1000),
                    "avoided %d   escaped %d" % (avoids, escapes),
                    "pings %d   timeouts %d" % (n.pings, n.timeouts),
                    "moving %ds" % (dr.moving_ms // 1000),
                ], ACCENT)
                for _ in range(3):
                    strip.pixels_fill((0, 0, 20)); strip.pixels_show()
                    utime.sleep_ms(250)
                    strip.pixels_fill(strip.BLACK); strip.pixels_show()
                    utime.sleep_ms(250)
                return

            tick_ms = utime.ticks_diff(utime.ticks_ms(), t0)
            if tick_ms < TICK_MS:
                utime.sleep_ms(TICK_MS - tick_ms)
    finally:
        dr.release()


try:
    main()
except KeyboardInterrupt:
    print("interrupted")
except Exception as e:
    # No restart loop here, deliberately. See the module docstring: an avoider
    # that resurrects with an unknown fault, on wheels, is worse than a stopped
    # one. 01_sensorous restarts because it cannot move.
    board.estop()
    sys.print_exception(e)
    try:
        card(ST7789(), "CRASHED", ["%s:" % type(e).__name__, str(e)[:26], "",
                                   "motors stopped.",
                                   "it will NOT restart itself."], WARN)
    except Exception:
        pass
board.estop()
