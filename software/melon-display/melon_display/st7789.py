"""Minimal ST7789 driver for the 2.0" 240x320 SPI TFT, used in landscape (320x240).

Only needs spidev and gpiozero (both in Raspberry Pi OS). Wiring (hardware doc §5):
SPI0 MOSI=GPIO10, SCLK=GPIO11, CS=GPIO8 (CE0), DC=GPIO25, RST=GPIO24, backlight tied to 3V3.
"""
import time

import numpy as np

# Panel commands
SWRESET, SLPOUT, NORON, INVOFF, INVON, DISPON = 0x01, 0x11, 0x13, 0x20, 0x21, 0x29
CASET, RASET, RAMWR, MADCTL, COLMOD = 0x2A, 0x2B, 0x2C, 0x36, 0x3A

# MADCTL bits
MY, MX, MV, BGR = 0x80, 0x40, 0x20, 0x08
ROTATIONS = {0: 0x00, 90: MV | MX, 180: MX | MY, 270: MV | MY}


def to_rgb565(img):
    """PIL RGB image -> big-endian RGB565 bytes."""
    a = np.asarray(img, dtype=np.uint16)
    v = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return v.astype(">u2").tobytes()


class ST7789:
    def __init__(self, port=0, cs=0, dc=25, rst=24, speed_hz=40_000_000,
                 rotation=90, invert=True, bgr=False, offset_x=0, offset_y=0):
        import spidev
        from gpiozero import DigitalOutputDevice

        self.width, self.height = (320, 240) if rotation in (90, 270) else (240, 320)
        self.ox, self.oy = offset_x, offset_y
        self.spi = spidev.SpiDev()
        self.spi.open(port, cs)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0
        self.dc = DigitalOutputDevice(dc)
        self.rst = DigitalOutputDevice(rst, initial_value=True) if rst is not None else None

        self._reset()
        self._cmd(SWRESET); time.sleep(0.150)
        self._cmd(SLPOUT); time.sleep(0.120)
        self._cmd(COLMOD, [0x55])                      # 16 bit/pixel
        self._cmd(MADCTL, [ROTATIONS[rotation] | (BGR if bgr else 0)])
        self._cmd(INVON if invert else INVOFF)         # most IPS modules need INVON
        self._cmd(NORON); time.sleep(0.010)
        self._cmd(DISPON); time.sleep(0.050)

    def _reset(self):
        if self.rst is None:
            return
        self.rst.on(); time.sleep(0.01)
        self.rst.off(); time.sleep(0.01)
        self.rst.on(); time.sleep(0.12)

    def _cmd(self, c, data=None):
        self.dc.off()
        self.spi.writebytes([c])
        if data:
            self.dc.on()
            self.spi.writebytes(list(data))

    def _window(self, x0, y0, x1, y1):
        x0 += self.ox; x1 += self.ox; y0 += self.oy; y1 += self.oy
        self._cmd(CASET, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(RASET, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(RAMWR)

    def show(self, img, x=0, y=0):
        """Push a PIL RGB image (full frame or a region at x, y)."""
        w, h = img.size
        self._window(x, y, x + w - 1, y + h - 1)
        self.dc.on()
        self.spi.writebytes2(to_rgb565(img))           # writebytes2 splits big buffers

    def close(self):
        self.spi.close()
