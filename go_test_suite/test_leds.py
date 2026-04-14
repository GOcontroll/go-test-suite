"""LED test — adapted from go-leds"""

import os
import time

try:
    import smbus2
    _HAS_SMBUS = True
except ImportError:
    _HAS_SMBUS = False

_I2C_ADDR = 0x14
_RED      = 1
_GREEN    = 2
_BLUE     = 3


class _LedSysfs:
    def __init__(self, n):
        self._n = n
        with open(f"/sys/class/leds/case-led{n}/brightness") as f:
            self._brightness = int(f.read())
        with open(f"/sys/class/leds/case-led{n}/multi_intensity") as f:
            r, g, b = f.read().split()
            self._r, self._g, self._b = int(r), int(g), int(b)

    def _write_colour(self):
        with open(f"/sys/class/leds/case-led{self._n}/multi_intensity", "w") as f:
            f.write(f"{self._r} {self._g} {self._b}")

    def set_red(self, v):   self._r = v; self._write_colour()
    def set_green(self, v): self._g = v; self._write_colour()
    def set_blue(self, v):  self._b = v; self._write_colour()

    def set_brightness(self, v):
        self._brightness = v
        with open(f"/sys/class/leds/case-led{self._n}/brightness", "w") as f:
            f.write(str(v))


class _LedI2c:
    def __init__(self, n):
        self._n = n - 1
        self._bus = smbus2.SMBus(2)
        if self._bus.read_byte_data(_I2C_ADDR, 0) != 0x40:
            self._bus.write_byte_data(_I2C_ADDR, 0x17, 0xFF)
            self._bus.write_byte_data(_I2C_ADDR, 0x00, 0x40)
        self._brightness = 255
        self._r = self._g = self._b = 0

    def _write(self, channel, value):
        scaled = int((self._brightness / 255) * value)
        self._bus.write_i2c_block_data(_I2C_ADDR, 0x0A + self._n * 3 + channel, [scaled])

    def set_red(self, v):       self._r = v; self._write(_RED,   v)
    def set_green(self, v):     self._g = v; self._write(_GREEN, v)
    def set_blue(self, v):      self._b = v; self._write(_BLUE,  v)

    def set_brightness(self, v):
        self._brightness = v
        self._write(_RED,   self._r)
        self._write(_GREEN, self._g)
        self._write(_BLUE,  self._b)


def _get_led(n):
    if os.path.isfile(f"/sys/class/leds/case-led{n}/brightness"):
        return _LedSysfs(n)
    if not _HAS_SMBUS:
        raise RuntimeError("smbus2 not available and sysfs LED not found")
    return _LedI2c(n)


def run():
    leds = [_get_led(n) for n in range(1, 5)]

    for led in leds:
        led.set_brightness(127)

    for colour, setter in [("red", "set_red"), ("green", "set_green"), ("blue", "set_blue")]:
        for led in leds:
            getattr(led, setter)(255)
        time.sleep(2)
        for led in leds:
            getattr(led, setter)(0)

    for led in leds:
        led.set_brightness(0)
