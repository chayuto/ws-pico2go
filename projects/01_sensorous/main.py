"""01_sensorous - measure everything this robot can measure, and show it.

    ./pg run sensorous 120

Reads every live sensor on the Pico2Go except the radio (the JDY-32 Bluetooth
module is deliberately not touched), renders the lot across six pages on the
1.14" LCD, mirrors a summary to the four RGB LEDs, and streams one JSON Lines
record per sample to the serial link.

NEVER drives the motors. GP16-GP21 are untouched; estop() runs on the way out.

Paging: any IR remote key steps to the next page and restarts the dwell timer.
With no remote it just auto-advances every 6 s. Either way the page moves by
one, so it works with whatever remote you happen to have.
"""

import gc
import os
import sys
import utime
import machine
from machine import Pin, ADC

import board
import sonar
from TRSensor import TRSensor
from ST7789 import ST7789
from ws2812 import NeoPixel

# ---------------------------------------------------------------- palette
# The vendor driver's colour constants are not textbook RGB565 (its GREEN is
# 0x001F, pure blue in standard RGB565), so only BLACK and WHITE are certain.
# Everything else uses the driver's own names - the same values Waveshare
# shipped - and the exact hues are unverified because nobody has eyes on the
# panel. See docs/06 and the pico2go-sensors-io skill.
BG     = 0x0000
FG     = 0xFFFF
DIM    = 0x8410
ACCENT = 0xFF00        # driver calls this BLUE
WARN   = 0xF800        # driver calls this RED
OK     = 0x001F        # driver calls this GREEN
HILITE = 0xFFE0        # driver calls this YELLOW

W, H = board.LCD_W, board.LCD_H
ROW = 11                     # 8 px font + 3 px leading
PAGES = ("OVERVIEW", "LINE ARRAY", "RANGE", "POWER", "INPUTS", "SYSTEM")
AUTO_MS = 6000

# Any key steps +1. No per-key map, so an unfamiliar remote still works.


# ---------------------------------------------------------------- sensors
class Sensors:
    """Every live sensor on the board. No radio, no motors."""

    def __init__(self):
        self.trs = TRSensor()
        self.dsl = Pin(board.DSL, Pin.IN)
        self.dsr = Pin(board.DSR, Pin.IN)
        self.ir = Pin(board.IR_RX, Pin.IN)
        self.bat = ADC(Pin(board.BAT_ADC))
        self.die = ADC(board.TEMP_ADC_CH)

        self.line = [0] * board.TRS_CHANNELS
        self.line_lo = [1023] * board.TRS_CHANNELS
        self.line_hi = [0] * board.TRS_CHANNELS
        self.spare = [0] * 6                 # TLC2543 A5..A10, unconnected

        self.dist = None
        self.dist_hist = []                  # rolling window, cm
        self.dist_lo = None
        self.dist_hi = None
        self.pings = 0
        self.timeouts = 0

        self.obstacle_l = False
        self.obstacle_r = False
        self.trig_l = 0
        self.trig_r = 0
        self._prev_l = 1
        self._prev_r = 1

        self.volts = 0.0
        self.pct = 0
        self.bat_raw = 0
        self.temp_c = 0.0

        self.keys = []                       # recent IR codes, newest first
        self.key_count = 0

        self.t0 = utime.ticks_ms()
        self.samples = 0
        self.loop_ms = 0        # time in sample(), excludes the LCD blit
        self.frame_ms = 0       # whole loop including render + blit

    # -- individual reads ------------------------------------------------
    def _adc_med(self, a, n=5):
        v = [a.read_u16() for _ in range(n)]
        v.sort()
        return v[n // 2]

    def read_line(self):
        self.line = self.trs.AnalogRead()
        for i, v in enumerate(self.line):
            if v < self.line_lo[i]:
                self.line_lo[i] = v
            if v > self.line_hi[i]:
                self.line_hi[i] = v

    def read_spare(self):
        """TLC2543 A5..A10 - nothing is wired to them, but they are real
        readings and 'all metrics' means all of them."""
        out = []
        for j in range(5, 12):
            self.trs.CS.value(0)
            self.trs.sm.put(j << 28)
            out.append((self.trs.sm.get() & 0xFFF) >> 2)
            self.trs.CS.value(1)
        self.spare = out[1:]

    def read_range(self):
        d = sonar.read()
        self.pings += 1
        if d is None:
            self.timeouts += 1
        else:
            self.dist = d
            self.dist_hist.append(d)
            if len(self.dist_hist) > W:          # one sample per pixel column
                self.dist_hist.pop(0)
            if self.dist_lo is None or d < self.dist_lo:
                self.dist_lo = d
            if self.dist_hi is None or d > self.dist_hi:
                self.dist_hi = d

    def read_obstacle(self):
        l, r = self.dsl.value(), self.dsr.value()
        if l == 0 and self._prev_l == 1:
            self.trig_l += 1
        if r == 0 and self._prev_r == 1:
            self.trig_r += 1
        self._prev_l, self._prev_r = l, r
        self.obstacle_l = (l == 0)
        self.obstacle_r = (r == 0)

    def read_power(self):
        self.bat_raw = self._adc_med(self.bat, 9)
        self.volts = self.bat_raw * 3.3 / 65535 * board.BAT_DIVIDER
        p = (self.volts - board.BAT_EMPTY_V) * 100 / (board.BAT_FULL_V - board.BAT_EMPTY_V)
        self.pct = int(max(0, min(100, p)))
        v = self._adc_med(self.die, 5) * 3.3 / 65535
        self.temp_c = 27 - (v - 0.706) / 0.001721

    def poll_ir(self):
        """NEC decode. Returns a command byte, or None. Blocks ~67 ms only
        while a frame is actually arriving."""
        if self.ir.value() != 0:
            return None
        c = 0
        while self.ir.value() == 0 and c < 100:
            c += 1
            utime.sleep_us(100)
        if c < 10:
            return None
        c = 0
        while self.ir.value() == 1 and c < 50:
            c += 1
            utime.sleep_us(100)
        idx = cnt = 0
        data = [0, 0, 0, 0]
        for _ in range(32):
            c = 0
            while self.ir.value() == 0 and c < 10:
                c += 1
                utime.sleep_us(100)
            c = 0
            while self.ir.value() == 1 and c < 20:
                c += 1
                utime.sleep_us(100)
            if c > 7:
                data[idx] |= 1 << cnt
            if cnt == 7:
                cnt, idx = 0, idx + 1
            else:
                cnt += 1
        if data[0] + data[1] == 0xFF and data[2] + data[3] == 0xFF:
            k = data[2]
            self.key_count += 1
            self.keys.insert(0, k)
            del self.keys[6:]
            return k
        return None

    def sample(self):
        t = utime.ticks_ms()
        self.read_line()
        self.read_range()
        self.read_obstacle()
        self.read_power()
        self.samples += 1
        if self.samples % 10 == 1:
            self.read_spare()
        self.loop_ms = utime.ticks_diff(utime.ticks_ms(), t)   # sampling only

    # -- derived ---------------------------------------------------------
    def uptime_s(self):
        return utime.ticks_diff(utime.ticks_ms(), self.t0) // 1000

    def dist_med(self):
        if not self.dist_hist:
            return None
        v = sorted(self.dist_hist[-9:])
        return v[len(v) // 2]

    def line_centroid(self):
        """Weighted centre of the array, 0..4000, or None if nothing stands out."""
        tot = sum(self.line)
        if tot <= 0:
            return None
        return sum(v * (i * 1000) for i, v in enumerate(self.line)) / tot

    def jsonl(self):
        d = self.dist
        return ('{"t":"sensor","up":%d,"line":%s,"lo":%s,"hi":%s,'
                '"dist":%s,"pings":%d,"to":%d,"dsl":%d,"dsr":%d,'
                '"trig_l":%d,"trig_r":%d,"v":%.3f,"pct":%d,"raw":%d,'
                '"temp":%.1f,"keys":%d,"read":%d,"frame":%d,"heap":%d}') % (
            self.uptime_s(), self.line, self.line_lo, self.line_hi,
            ("null" if d is None else "%.1f" % d), self.pings, self.timeouts,
            0 if self.obstacle_l else 1, 0 if self.obstacle_r else 1,
            self.trig_l, self.trig_r, self.volts, self.pct, self.bat_raw,
            self.temp_c, self.key_count, self.loop_ms, self.frame_ms, gc.mem_free())


# ---------------------------------------------------------------- drawing
def bar(lcd, x, y, w, h, frac, colour):
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    lcd.rect(x, y, w, h, DIM)
    fill = int((w - 2) * frac)
    if fill > 0:
        lcd.fill_rect(x + 1, y + 1, fill, h - 2, colour)


def chrome(lcd, s, page):
    lcd.fill(BG)
    lcd.text("SENSOROUS", 2, 2, ACCENT)
    lcd.text("%d/%d %s" % (page + 1, len(PAGES), PAGES[page]), 92, 2, FG)
    lcd.text("%3ds" % s.uptime_s(), W - 34, 2, DIM)
    lcd.hline(0, 12, W, DIM)
    lcd.hline(0, H - 11, W, DIM)
    lcd.text("%dfps  %dms" % (1000 // max(1, s.frame_ms), s.frame_ms), 2, H - 9, DIM)
    lcd.text("no radio", W - 66, H - 9, DIM)


def page_overview(lcd, s):
    y = 18
    lcd.text("BATT %4.2fV %3d%%" % (s.volts, s.pct), 2, y, FG)
    bar(lcd, 150, y - 1, 86, 9, s.pct / 100.0, OK if s.pct > 25 else WARN)
    y += ROW
    lcd.text("DIE  %5.1f C" % s.temp_c, 2, y, FG)
    y += ROW
    d = s.dist
    lcd.text("DIST %s" % ("  --  " if d is None else "%5.1fcm" % d), 2, y, FG)
    if d is not None:
        bar(lcd, 150, y - 1, 86, 9, min(d, 100) / 100.0, WARN if d < 10 else OK)
    y += ROW
    lcd.text("OBST L:%s R:%s" % ("HIT" if s.obstacle_l else " - ",
                                 "HIT" if s.obstacle_r else " - "), 2, y,
             WARN if (s.obstacle_l or s.obstacle_r) else FG)
    y += ROW
    c = s.line_centroid()
    lcd.text("LINE %s" % ("  --  " if c is None else "%4d" % int(c)), 2, y, FG)
    x = 150
    for v in s.line:
        h = int(9 * v / 1023)
        lcd.fill_rect(x, y + 8 - h, 14, max(1, h), HILITE)
        x += 17
    y += ROW
    lcd.text("IR   %d keys" % s.key_count, 2, y, FG)


def page_line(lcd, s):
    lcd.text("ch   raw   min   max", 2, 16, DIM)
    y = 27
    for i in range(board.TRS_CHANNELS):
        v = s.line[i]
        lcd.text("IR%d %4d  %4d  %4d" % (i + 1, v, s.line_lo[i], s.line_hi[i]), 2, y, FG)
        bar(lcd, 172, y - 1, 64, 9, v / 1023.0, HILITE)
        y += ROW
    c = s.line_centroid()
    lcd.text("centroid %s   TLC2543 12bit>>2" % ("--" if c is None else "%4d" % int(c)),
             2, y + 2, DIM)


def page_range(lcd, s):
    d, m = s.dist, s.dist_med()
    lcd.text("now %s" % ("  --  " if d is None else "%5.1f cm" % d), 2, 18, FG)
    lcd.text("med %s" % ("  --  " if m is None else "%5.1f cm" % m), 120, 18, FG)
    lcd.text("min %s" % ("  --" if s.dist_lo is None else "%5.1f" % s.dist_lo), 2, 29, DIM)
    lcd.text("max %s" % ("  --" if s.dist_hi is None else "%5.1f" % s.dist_hi), 120, 29, DIM)
    lcd.text("pings %d  timeout %d" % (s.pings, s.timeouts), 2, 40, DIM)
    # Chart, stretched across the whole panel. The history holds at most one
    # sample per pixel column; while it is still filling, x is mapped across
    # whatever exists so the plot always spans the full width.
    top, base, hgt = 54, 112, 56
    lcd.hline(0, base, W, DIM)
    lcd.hline(0, top, W, DIM)
    hist = s.dist_hist
    n = len(hist)
    if n:
        hi = max(max(hist), 10.0)
        prev_y = None
        for px in range(W):
            v = hist[px * n // W]
            yv = base - int(hgt * min(v, hi) / hi)
            colour = OK if v >= 10 else WARN
            if prev_y is None or abs(yv - prev_y) <= 1:
                lcd.pixel(px, yv, colour)
                lcd.pixel(px, yv + 1, colour)
            else:
                lcd.line(px - 1, prev_y, px, yv, colour)   # join the jumps
            prev_y = yv
        lcd.text("%.0f" % hi, 2, top + 2, DIM)
        lcd.text("0", 2, base - 9, DIM)
        lcd.text("%ds" % (n * max(1, s.frame_ms) // 1000), W - 34, base - 9, DIM)


def page_power(lcd, s):
    y = 18
    lcd.text("battery  %5.2f V" % s.volts, 2, y, FG); y += ROW
    lcd.text("charge   %5d %%" % s.pct, 2, y, FG)
    bar(lcd, 150, y - 1, 86, 9, s.pct / 100.0, OK if s.pct > 25 else WARN); y += ROW
    lcd.text("adc raw  %5d" % s.bat_raw, 2, y, DIM); y += ROW
    lcd.text("at pin   %5.3f V" % (s.bat_raw * 3.3 / 65535), 2, y, DIM); y += ROW
    lcd.text("divider  x%.1f" % board.BAT_DIVIDER, 2, y, DIM); y += ROW
    lcd.text("die temp %5.1f C" % s.temp_c, 2, y, FG); y += ROW
    lcd.text("5V rail needs the switch", 2, y, DIM)


def page_inputs(lcd, s):
    y = 18
    lcd.text("IR OBSTACLE (active low)", 2, y, DIM); y += ROW
    lcd.text("left  GP3  %s  x%d" % ("HIT" if s.obstacle_l else " - ", s.trig_l), 2, y,
             WARN if s.obstacle_l else FG); y += ROW
    lcd.text("right GP2  %s  x%d" % ("HIT" if s.obstacle_r else " - ", s.trig_r), 2, y,
             WARN if s.obstacle_r else FG); y += ROW + 4
    lcd.text("IR REMOTE (NEC, GP5)", 2, y, DIM); y += ROW
    lcd.text("frames %d" % s.key_count, 2, y, FG); y += ROW
    lcd.text("recent %s" % (" ".join("%02X" % k for k in s.keys) if s.keys else "-"),
             2, y, HILITE)


def page_system(lcd, s):
    gc.collect()
    st = os.statvfs("/")
    y = 18
    lcd.text("MicroPython %s" % ".".join(str(x) for x in sys.implementation.version[:3]),
             2, y, FG); y += ROW
    lcd.text("clock  %d MHz" % (machine.freq() // 1000000), 2, y, FG); y += ROW
    lcd.text("heap   %d KB free" % (gc.mem_free() // 1024), 2, y, FG); y += ROW
    lcd.text("flash  %d KB free" % (st[0] * st[3] // 1024), 2, y, FG); y += ROW
    lcd.text("sample %d  read %dms" % (s.samples, s.loop_ms), 2, y, DIM); y += ROW
    lcd.text("frame %d ms (blit 78)" % s.frame_ms, 2, y, DIM); y += ROW
    lcd.text("spare adc %s" % " ".join(str(v) for v in s.spare[:4]), 2, y, DIM); y += ROW
    lcd.text("A5-A10 float, unwired", 2, y, DIM)


RENDER = (page_overview, page_line, page_range, page_power, page_inputs, page_system)


# ---------------------------------------------------------------- ambient
def ambient(strip, s):
    """Four RGB LEDs as a second, much smaller screen: battery, obstacle L/R,
    range. Powered from the 5 V rail, so dark with the switch off."""
    strip.pixels_set(0, (0, 60, 0) if s.pct > 25 else (60, 0, 0))
    strip.pixels_set(1, (60, 0, 0) if s.obstacle_l else (0, 0, 12))
    strip.pixels_set(2, (60, 0, 0) if s.obstacle_r else (0, 0, 12))
    d = s.dist
    if d is None:
        strip.pixels_set(3, (12, 12, 0))
    elif d < 10:
        strip.pixels_set(3, (60, 0, 0))
    elif d < 30:
        strip.pixels_set(3, (45, 25, 0))
    else:
        strip.pixels_set(3, (0, 45, 0))
    strip.pixels_show()


# ---------------------------------------------------------------- main
def main():
    print("01_sensorous - every live sensor except the radio")
    print("pages:", ", ".join(PAGES))
    s = Sensors()
    lcd = ST7789()
    strip = NeoPixel()

    # `pg run <app> <secs>` injects this so the app stops itself cleanly rather
    # than being killed, which would leave the mount protocol wedged.
    try:
        limit_ms = int(PG_RUN_SECS) * 1000       # noqa: F821 - injected
    except NameError:
        limit_ms = 0                             # 0 = run until interrupted

    page = 0
    last_page = utime.ticks_ms()
    last_emit = utime.ticks_ms()
    started = utime.ticks_ms()

    while True:
        frame_t0 = utime.ticks_ms()

        # Any key press flips to the next page and restarts the dwell.
        if s.poll_ir() is not None:
            page = (page + 1) % len(PAGES)
            last_page = utime.ticks_ms()

        s.sample()

        # Auto-advance by one, same direction as a key press.
        if utime.ticks_diff(utime.ticks_ms(), last_page) > AUTO_MS:
            page = (page + 1) % len(PAGES)
            last_page = utime.ticks_ms()

        chrome(lcd, s, page)
        RENDER[page](lcd, s)
        lcd.show()

        ambient(strip, s)
        s.frame_ms = utime.ticks_diff(utime.ticks_ms(), frame_t0)

        if utime.ticks_diff(utime.ticks_ms(), last_emit) > 1000:
            last_emit = utime.ticks_ms()
            print(s.jsonl())

        if limit_ms and utime.ticks_diff(utime.ticks_ms(), started) > limit_ms:
            print("time limit reached, stopping cleanly")
            strip.pixels_fill(strip.BLACK)
            strip.pixels_show()
            return


try:
    main()
except KeyboardInterrupt:
    pass
finally:
    board.estop()
