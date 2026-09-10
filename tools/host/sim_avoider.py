#!/usr/bin/env python3
"""Run projects/02_avoider on the Mac, against a simulated robot and room.

    ./pg sim                       # 25 rooms, 120 simulated seconds each
    ./pg sim --seed 4 --trace      # one room, every line the app prints
    ./pg sim --dry                 # exercise the dry-run path

This is host Python 3, not MicroPython. It stubs `machine`, `utime`, `ST7789`
and `ws2812`, supplies a fake TB6612 that decodes the real direction-pin logic
out of shared/lib/drive.py, and integrates a differential-drive chassis inside
a box with obstacles.

Why bother: the avoider's failure mode is a collision, and the only way to see
one on real hardware is to cause one. Here a bad threshold shows up as a number
instead of a dent. The physics are crude - no encoders to model, no wheel slip,
a first-order lag standing in for inertia - so this proves the *logic*, never
the tuning. Constants still have to be earned on the floor.

Charged costs keep the virtual clock honest: an ultrasonic ping costs its own
flight time (or the full timeout on a miss) and an LCD blit costs the measured
78 ms, so the simulated control loop runs at the rate the real one will.
"""

import argparse
import math
import random
import sys
import types
import os

# tools/host/ is Mac-side Python 3. tools/*.py is MicroPython for the board;
# nothing in here is ever copied to it.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, "projects", "02_avoider", "main.py")

BLIT_MS = 78.0            # measured on this panel
MAX_CMS = 55.0            # chassis speed at 100 % duty on a fresh pack
TRACK_CM = 9.0            # wheel separation
TAU_DRIVE = 0.14          # first-order lag toward the commanded speed
TAU_BRAKE = 0.05
BODY_R = 6.0              # collision radius
IR_RANGE = 12.0           # ST188 pair, adjustable in reality
IR_ANGLE = 25.0           # degrees off centre
IR_LOBE = 10.0            # each emitter is a lobe, not a laser
SONAR_MAX = 400.0
SONAR_LOBE = 7.5          # HC-SR04 is a ~15 deg cone; it returns the FIRST
SONAR_RAYS = 5            #   echo from anywhere inside it, i.e. the nearest
GRAZE_DEG = 60.0          # beyond this incidence the echo goes elsewhere


# ------------------------------------------------------------------ world
class World:
    def __init__(self, rng, w=220.0, h=180.0):
        self.rng = rng
        self.w, self.h = w, h
        self.obstacles = [(rng.uniform(40, w - 40), rng.uniform(40, h - 40),
                           rng.uniform(6, 14)) for _ in range(4)]
        self.x, self.y = w / 2, 25.0
        self.th = math.radians(rng.uniform(60, 120))
        self.vl = self.vr = 0.0          # actual wheel speeds, cm/s
        self.cl = self.cr = 0.0          # commanded
        self.braking = False
        self.collisions = 0
        self.in_contact = False
        self.path = []
        self.t = 0.0
        self.hits = []           # (sim seconds, commanded left, commanded right)

    def step(self, dt):
        if dt <= 0:
            return
        tau = TAU_BRAKE if self.braking else TAU_DRIVE
        k = 1.0 - math.exp(-dt / tau)
        self.vl += (self.cl - self.vl) * k
        self.vr += (self.cr - self.vr) * k
        v = (self.vl + self.vr) / 2.0
        w = (self.vr - self.vl) / TRACK_CM
        self.th += w * dt
        self.x += v * math.cos(self.th) * dt
        self.y += v * math.sin(self.th) * dt
        self.x = min(max(self.x, BODY_R), self.w - BODY_R)
        self.y = min(max(self.y, BODY_R), self.h - BODY_R)
        self.t += dt
        touching = self.clearance() <= 0.5
        if touching and not self.in_contact:
            self.collisions += 1
            self.hits.append((self.t, self.vl, self.vr, self.contact_bearing(),
                              self.sonar(12000)))
        self.in_contact = touching
        self.path.append((self.x, self.y))

    def contact_bearing(self):
        """Bearing of the nearest surface relative to straight ahead, degrees.
        0 means dead ahead, +-90 means it is being sideswiped."""
        best, ang = 1e9, 0.0
        for d, a in ((self.x - BODY_R, math.pi), (self.w - self.x - BODY_R, 0.0),
                     (self.y - BODY_R, -math.pi / 2), (self.h - self.y - BODY_R, math.pi / 2)):
            if d < best:
                best, ang = d, a
        for ox, oy, orr in self.obstacles:
            d = math.hypot(self.x - ox, self.y - oy) - orr - BODY_R
            if d < best:
                best, ang = d, math.atan2(oy - self.y, ox - self.x)
        rel = math.degrees(math.atan2(math.sin(ang - self.th), math.cos(ang - self.th)))
        return rel

    def clearance(self):
        """Gap between the body and the nearest thing, cm."""
        d = min(self.x, self.y, self.w - self.x, self.h - self.y) - BODY_R
        for ox, oy, orr in self.obstacles:
            d = min(d, math.hypot(self.x - ox, self.y - oy) - orr - BODY_R)
        return d

    # -- ranging ------------------------------------------------------
    def _ray(self, ang, maxd=SONAR_MAX):
        """March a ray; returns (distance, incidence_deg) or (None, None).

        Incidence is measured from the surface normal: 0 is a square-on hit
        that echoes straight back, 90 is a graze that does not come back at
        all. That angle is the whole reason an ultrasonic avoider needs a
        second opinion.
        """
        def diff(a, b):
            return abs(math.degrees(math.atan2(math.sin(a - b), math.cos(a - b))))

        step = 1.0
        d = 1.0
        while d < maxd:
            px = self.x + d * math.cos(ang)
            py = self.y + d * math.sin(ang)
            if px <= 0 or px >= self.w or py <= 0 or py >= self.h:
                if px <= 0:
                    nrm = math.pi
                elif px >= self.w:
                    nrm = 0.0
                elif py <= 0:
                    nrm = -math.pi / 2
                else:
                    nrm = math.pi / 2
                return d, diff(ang, nrm)          # 0 = square on
            for ox, oy, orr in self.obstacles:
                if math.hypot(px - ox, py - oy) <= orr:
                    out = math.atan2(py - oy, px - ox)
                    return d, 180.0 - diff(ang, out)
            d += step
        return None, None

    def sonar(self, timeout_us):
        """Nearest echo anywhere in the cone, or None.

        Modelled as a fan of rays rather than one, because the body is wider
        than a line and so is the beam. A single-ray model slips past a chair
        leg the chassis then clips - which looks like an app bug and is not.
        """
        reach = min(SONAR_MAX, timeout_us * 1e-6 * 34300.0 / 2)
        best = None
        for i in range(SONAR_RAYS):
            off = math.radians(-SONAR_LOBE + 2 * SONAR_LOBE * i / (SONAR_RAYS - 1))
            d, inc = self._ray(self.th + off, reach)
            if d is None or inc > GRAZE_DEG:
                continue           # specular: the pulse leaves and never returns
            if best is None or d < best:
                best = d
        if best is None or best < 2.0:
            return None            # nothing, or the dead zone: both are unknown
        return best * self.rng.uniform(0.97, 1.03)

    def ir(self):
        out = []
        for s in (+1, -1):         # +1 = left
            hit = False
            for k in (-1, 0, 1):
                a = self.th + math.radians(s * IR_ANGLE + k * IR_LOBE)
                d, _ = self._ray(a, IR_RANGE + 1.0)
                if d is not None and d < IR_RANGE:
                    hit = True
                    break
            out.append(hit)
        return out[0], out[1]


# ------------------------------------------------------------------ clock
class Clock:
    def __init__(self, world):
        self.ms = 0.0
        self.world = world

    def advance(self, ms):
        if ms <= 0:
            return
        left = ms
        while left > 0:            # integrate in small slices for stability
            s = min(left, 10.0)
            self.world.step(s / 1000.0)
            self.ms += s
            left -= s


# ------------------------------------------------------------------ stubs
def install_stubs(world, clock, trace):
    ut = types.ModuleType("utime")
    ut.ticks_ms = lambda: int(clock.ms)
    ut.ticks_us = lambda: int(clock.ms * 1000)
    ut.ticks_diff = lambda a, b: a - b
    ut.ticks_add = lambda a, b: a + b
    ut.sleep_ms = lambda m: clock.advance(m)
    ut.sleep_us = lambda u: clock.advance(u / 1000.0)
    ut.sleep = lambda s: clock.advance(s * 1000.0)

    class Pin:
        IN = 0
        OUT = 1

        def __init__(self, pin, mode=None, *a, **k):
            self.pin = pin if isinstance(pin, int) else pin.pin
            self._v = 0

        def value(self, v=None):
            if v is not None:
                self._v = v
                return None
            if self.pin == 3:          # DSL, active LOW
                return 0 if world.ir()[0] else 1
            if self.pin == 2:          # DSR
                return 0 if world.ir()[1] else 1
            if self.pin == 15:         # echo, idle low
                return 0
            return self._v

    class PWM:
        def __init__(self, pin):
            self.pin = pin.pin if hasattr(pin, "pin") else pin
            self.duty = 0

        def freq(self, f):
            pass

        def duty_u16(self, d):
            self.duty = d

    class ADC:
        def __init__(self, src):
            self.ch = src if isinstance(src, int) else src.pin

        def read_u16(self):
            if self.ch == 4:
                return int(0.700 / 3.3 * 65535)        # ~30 C
            return int(4.02 / 2 / 3.3 * 65535)          # battery, via /2 divider

    mach = types.ModuleType("machine")
    mach.Pin, mach.PWM, mach.ADC = Pin, PWM, ADC
    mach.freq = lambda: 150000000

    # Vendor Motor.PicoGo, faked at the pin level so drive.py's real direction
    # and brake logic is what gets exercised.
    # drive.brake() writes the direction pins and PWM registers directly
    # rather than going through setMotor(), so the fakes have to notify the
    # bridge on every write -- otherwise a brake is silently modelled as a
    # coast and every stopping distance in this simulator is a lie.
    class BPin(Pin):
        owner = None

        def value(self, v=None):
            r = Pin.value(self, v)
            if v is not None and self.owner is not None:
                self.owner._push()
            return r

    class BPWM(PWM):
        owner = None

        def duty_u16(self, d):
            PWM.duty_u16(self, d)
            if self.owner is not None:
                self.owner._push()

    class PicoGo:
        def __init__(self):
            self.PWMA, self.PWMB = BPWM(16), BPWM(21)
            self.AIN2, self.AIN1 = BPin(17, 1), BPin(18, 1)
            self.BIN1, self.BIN2 = BPin(19, 1), BPin(20, 1)
            self.stop()
            for o in (self.PWMA, self.PWMB, self.AIN1, self.AIN2,
                      self.BIN1, self.BIN2):
                o.owner = self

        def _push(self):
            def wheel(i1, i2, pwm):
                duty = pwm.duty / 0xFFFF
                a, b = i1._v, i2._v
                if a and b:
                    return 0.0, True                  # short brake
                if b and not a:
                    return +duty * MAX_CMS, False
                if a and not b:
                    return -duty * MAX_CMS, False
                return 0.0, False                     # coast
            l, bl = wheel(self.AIN1, self.AIN2, self.PWMA)
            r, br = wheel(self.BIN1, self.BIN2, self.PWMB)
            world.cl, world.cr = l, r
            world.braking = bl or br

        def stop(self):
            self.PWMA.duty_u16(0); self.PWMB.duty_u16(0)
            for p in (self.AIN1, self.AIN2, self.BIN1, self.BIN2):
                p.value(0)
            self._push()

        def setMotor(self, left, right):
            if left >= 0:
                self.AIN1.value(0); self.AIN2.value(1); self.PWMA.duty_u16(int(left * 0xFFFF / 100))
            else:
                self.AIN1.value(1); self.AIN2.value(0); self.PWMA.duty_u16(int(-left * 0xFFFF / 100))
            if right >= 0:
                self.BIN1.value(0); self.BIN2.value(1); self.PWMB.duty_u16(int(right * 0xFFFF / 100))
            else:
                self.BIN1.value(1); self.BIN2.value(0); self.PWMB.duty_u16(int(-right * 0xFFFF / 100))
            self._push()

        def forward(self, s): self.setMotor(s, s)
        def backward(self, s): self.setMotor(-s, -s)
        def left(self, s): self.setMotor(-s, s)
        def right(self, s): self.setMotor(s, -s)

    motor = types.ModuleType("Motor")
    motor.PicoGo = PicoGo

    class ST7789:
        def __init__(self):
            self.blits = 0

        def show(self):
            self.blits += 1
            clock.advance(BLIT_MS)

        def __getattr__(self, name):
            return lambda *a, **k: None

    st = types.ModuleType("ST7789")
    st.ST7789 = ST7789

    class NeoPixel:
        BLACK = (0, 0, 0)

        def __init__(self, *a, **k):
            pass

        def pixels_set(self, *a):
            pass

        def pixels_fill(self, *a):
            pass

        def pixels_show(self):
            clock.advance(0.2)

    ws = types.ModuleType("ws2812")
    ws.NeoPixel = NeoPixel

    # sonar: same contract as shared/lib/sonar.py, charged for flight time
    son = types.ModuleType("sonar")

    def read(timeout_us=30000):
        d = world.sonar(timeout_us)
        clock.advance((timeout_us / 1000.0) if d is None else (d * 2 / 34300.0 * 1000.0))
        return d
    son.read = read
    son.read_median = lambda n=5, timeout_us=30000: read(timeout_us)

    # MicroPython builtins the app expects. Patched onto the real modules
    # rather than shadowing them, so the harness itself keeps working.
    import gc as _gc
    import traceback as _tb
    if not hasattr(_gc, "mem_free"):
        _gc.mem_free = lambda: 200000
    if not hasattr(sys, "print_exception"):
        sys.print_exception = lambda e, *a: _tb.print_exception(type(e), e, e.__traceback__)

    for name, mod in (("utime", ut), ("machine", mach), ("Motor", motor),
                      ("ST7789", st), ("ws2812", ws), ("sonar", son)):
        sys.modules[name] = mod
    sys.path.insert(0, os.path.join(ROOT, "shared", "lib"))


# ------------------------------------------------------------------ driver
def run(seed, secs, trace, dry=False):
    rng = random.Random(seed)
    world = World(rng)
    clock = Clock(world)
    install_stubs(world, clock, trace)
    for m in ("board", "drive"):
        sys.modules.pop(m, None)

    src = open(APP).read()
    g = {"__name__": "__main__", "PG_RUN_SECS": secs}
    if dry:
        g["PG_DRY"] = 1

    states = []
    out = []
    real_print = print

    def cap(*a, **k):
        line = " ".join(str(x) for x in a)
        out.append(line)
        if trace:
            real_print("  %6.1fs %s" % (clock.ms / 1000.0, line))
    g["print"] = cap

    exec(compile(src, APP, "exec"), g)

    for line in out:
        if '"state"' in line:
            s = line.split('"state":"', 1)[1].split('"', 1)[0]
            if not states or states[-1] != s:
                states.append(s)
    return world, clock, states, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=int, default=120)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--dry", action="store_true",
                    help="exercise the dry-run path (motors never constructed)")
    a = ap.parse_args()

    total_c = 0
    for i in range(a.seeds):
        seed = a.seed + i
        world, clock, states, out = run(seed, a.secs, a.trace, a.dry)
        nav = [l for l in out if '"t":"nav"' in l]
        last = nav[-1] if nav else "{}"
        total_c += world.collisions
        print("seed %-3d  %5.1fs sim   collisions %-2d  min clearance kept  "
              "states %s" % (seed, clock.ms / 1000.0, world.collisions,
                             "->".join(states[:8]) + ("..." if len(states) > 8 else "")))
        if a.seeds == 1:
            for t, vl, vr, brg, snr in world.hits:
                st = "?"
                for line in nav:
                    up = int(line.split('"up":', 1)[1].split(",", 1)[0])
                    if up <= t:
                        st = line.split('"state":"', 1)[1].split('"', 1)[0]
                v = (vl + vr) / 2
                print("  HIT %5.1fs  state %-7s net %+5.1f cm/s (%s)  "
                      "contact %+4.0f deg off the nose  sonar %s" % (
                          t, st, v,
                          "reversing" if v < -0.5 else
                          "forward" if v > 0.5 else "rotating",
                          brg, "no echo" if snr is None else "%.0f cm" % snr))
            print("\nlast telemetry:\n  %s" % last)
            print("\ndistinct states seen: %s" % ", ".join(sorted(set(states))))
    if a.seeds > 1:
        print("\n%d seeds, %d collisions total" % (a.seeds, total_c))
    return 1 if total_c else 0


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
