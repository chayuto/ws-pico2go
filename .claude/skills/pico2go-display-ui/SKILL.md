---
name: pico2go-display-ui
description: Laying out a readable UI on the Pico2Go's 1.14in 240x135 ST7789 - text grid maths, bars, charts, paging, the frame budget, and the colour trap. Use whenever drawing anything on this robot's screen, designing pages or a dashboard, adding a chart or sparkline, deciding what fits, or when the display looks wrong, frozen, mis-coloured, or a plot does not span the panel.
---

# 240×135 UI

## The grid

`ST7789` subclasses `framebuf.FrameBuffer`, so `fill`, `pixel`, `line`, `hline`,
`vline`, `rect`, `fill_rect`, `text`, `blit`, `scroll` all work. The **only** font is
framebuf's fixed **8 × 8**.

| | |
|---|---|
| Panel | 240 × 135, RGB565, framebuffer **64,800 bytes** |
| Text grid | **30 columns × 16 rows** at 8 px |
| Comfortable row pitch | **11 px** (8 px glyph + 3 leading) — 10 usable rows |
| Safe content band | y = 16 … 122, leaving room for header and footer chrome |
| Window offsets | column **40**, row **53** (the panel sits inside the controller's 240×320 memory) |

A 30-char line is the hard limit. `"%-18s %6d"` style formatting keeps columns aligned;
count the characters before trusting a layout.

## Frame budget — the blit dominates

Measured on hardware:

| | |
|---|---|
| `lcd.show()` full frame | **78 ms** |
| Per-page render | 3–6 ms typical |
| A page doing `statvfs` + `gc.collect()` | 25 ms |
| Whole loop with sampling | 90–114 ms → **9–11 fps** |

So the blit is **70–85 % of every frame**. Consequences:

- Don't chase faster sampling to raise the frame rate; it is not the bottleneck.
- Anything sharing the thread stalls for 78 ms per frame.
- To go faster: partial-window updates, a higher SPI clock, or move the blit to
  **core 1** (verified usable and completely idle).
- **Never report frame rate from anything but the whole loop.** Timing only the sensor
  read once produced a header claiming ~166 Hz against a real 9 fps.

## Charts — the mistake to not repeat

A history buffer and a pixel column are not the same thing. Plotting one pixel per
sample against a 60-sample history filled 60 of 240 columns — a permanent quarter-width
stub that looked like a rendering bug.

**Cap history at the panel width and map x across whatever exists**, so the plot spans
the full width immediately and gains resolution as it fills:

```python
if len(hist) > W:          # W = 240, one sample per pixel column
    hist.pop(0)
...
n = len(hist)
for px in range(W):
    v = hist[px * n // W]                    # always spans the panel
    yv = base - int(hgt * min(v, hi) / hi)
    if prev_y is None or abs(yv - prev_y) <= 1:
        lcd.pixel(px, yv, colour); lcd.pixel(px, yv + 1, colour)
    else:
        lcd.line(px - 1, prev_y, px, yv, colour)      # join the jumps
    prev_y = yv
```

Label the axes — top value, zero, and the time span (`n * frame_ms // 1000`), derived
from the measured frame time, never a hardcoded rate.

## Bars

```python
def bar(lcd, x, y, w, h, frac, colour):
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    lcd.rect(x, y, w, h, DIM)
    fill = int((w - 2) * frac)
    if fill > 0:
        lcd.fill_rect(x + 1, y + 1, fill, h - 2, colour)
```

9 px tall sits neatly on an 11 px row. A right-hand bar column starting at x≈150 leaves
18 characters of label.

## Paging

Six pages of ~8 rows beats one cramped screen. Rules that worked:

- **Any IR key steps +1** and restarts the dwell. No per-key map — an unfamiliar remote
  still works, and there is nothing to remember.
- Auto-advance steps +1 too, so both paths behave identically.
- Persistent chrome: title, page `n/N`, uptime, a rule top and bottom, and the real
  frame time in the footer.

## ⚠️ Colours are not standard RGB565

The vendor driver defines `GREEN = 0x001F` — pure **blue** in textbook RGB565 — and
`BLUE = 0xFF00`. Something in the byte order between `framebuf` and the panel is
non-obvious.

- **Only `0x0000` and `0xFFFF` are certain.**
- Use the driver's own named constants; the values Waveshare shipped at least render.
- **Never derive a colour by reasoning about RGB565 bit fields here.** Put a test
  pattern up and have a human look.
- Hues in `01_sensorous` remain unverified — nobody has confirmed them against the panel.

## ⚠️ A static panel looks exactly like a crash

The ST7789 holds its last frame forever with nothing driving it. When a program ends
cleanly, the screen keeps the final image and the robot appears hung — this was reported
as a hang once already, when the REPL was answering fine the whole time.

**Always paint an end card when a program stops**, naming the reason and how to restart,
and give the RGB LEDs a distinct idle pattern. Same for faults — see
`pico2go-unattended`.
