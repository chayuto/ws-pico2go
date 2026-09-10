"""Pico2Go pin map — the single source of truth.

Extracted from PicoGo_Schematic_V2.pdf and cross-checked against Waveshare's
MicroPython demos and jblanked's C headers. See docs/02-pinout-reference.md.

V2 boards only (TLC2543 line ADC). V1 boards use an ADS1015 on I2C1.
"""

# --- Bluetooth: JDY-32 on UART0 ------------------------------------------
BT_TX = 0          # MCU TX -> module RXD
BT_RX = 1          # MCU RX <- module TXD
BT_BAUD = 115200   # vendor demo value; module family default is 9600

# --- IR obstacle avoidance (ST188 -> LM393), active LOW -------------------
DSR = 2            # right
DSL = 3            # left

# --- Buzzer (S8050 NPN), active HIGH -------------------------------------
BUZZER = 4

# --- IR receiver (NEC), idle HIGH ----------------------------------------
IR_RX = 5

# --- Line-tracking ADC: TLC2543, 5 channels, driven by PIO ---------------
TRS_CLK = 6        # I/O CLOCK  (TLC2543 pin 18)
TRS_ADDR = 7       # DATA INPUT (pin 17)
TRS_DOUT = 27      # DATA OUT   (pin 16)
TRS_CS = 28        # CS         (pin 15), active LOW
TRS_CHANNELS = 5   # AIN0..AIN4 = IR1..IR5, left -> right

# --- LCD: ST7789 240x135 on SPI1 -----------------------------------------
LCD_DC = 8
LCD_CS = 9
LCD_CLK = 10
LCD_DIN = 11
LCD_RST = 12
LCD_BL = 13
LCD_W, LCD_H = 240, 135
LCD_COL_OFFSET, LCD_ROW_OFFSET = 40, 53

# --- Ultrasonic ----------------------------------------------------------
US_TRIG = 14
US_ECHO = 15

# --- Motors: TB6612FNG. Channel A = LEFT, channel B = RIGHT --------------
PWMA = 16
AIN2 = 17
AIN1 = 18
BIN1 = 19
BIN2 = 20
PWMB = 21
MOTOR_FREQ = 1000

# --- WS2812B x4, chained, 5 V powered ------------------------------------
RGB = 22
RGB_COUNT = 4

# --- On-module user LED (RP2350-Plus) ------------------------------------
LED = 25

# --- Analog --------------------------------------------------------------
BAT_ADC = 26       # battery sense, via a divider gated by the 5 V rail
TEMP_ADC_CH = 4    # RP2350 internal die temperature

# Battery divider ratio. Schematic shows a 100k/100k pair => 2.0.
# A third-party C driver uses 3.0. VERIFY AGAINST A MULTIMETER before
# trusting any low-battery logic. See docs/03-power-and-battery.md.
BAT_DIVIDER = 2.0
BAT_EMPTY_V = 3.0
BAT_FULL_V = 4.2

# PIO state machines already claimed by the vendor drivers.
SM_WS2812 = 0
SM_TRSENSOR = 1
# RP2350 has 12 (3 blocks x 4). 2-3 and 4-11 are free.

# Pins that must be forced low/zero to guarantee the robot stops moving.
ESTOP_PWM = (PWMA, PWMB)
ESTOP_LOW = (AIN1, AIN2, BIN1, BIN2, BUZZER)


def estop():
    """Kill motors and buzzer. Safe to call from anywhere, never raises."""
    from machine import Pin, PWM
    for p in ESTOP_PWM:
        try:
            PWM(Pin(p)).duty_u16(0)
        except Exception:
            pass
    for p in ESTOP_LOW:
        try:
            Pin(p, Pin.OUT).value(0)
        except Exception:
            pass
