"""Graphical touch test - draws five grey dots on the panel and turns each one
green when it is touched. The test passes once all five have been hit.

Used on HMI1 fitted with the av101 panel; the av123 has no touch controller at
all, so platform.detect() reports has_touch False there and the suite does not
offer this test.

Why five dots in the corners and the centre: a touch anywhere in the middle
proves the controller responds, but says nothing about the edges - and the
edges are exactly where a partially seated flex connector shows up first.
Forcing a hit near each corner turns "touch works" into "the whole digitiser
works".

Drawing goes straight to /dev/fb0. That needs no GUI stack, which suits an
image that deliberately ships without a compositor. fbcon is unbound for the
duration so the console does not overdraw the dots, and always rebound.
"""

import fcntl
import mmap
import os
import select
import struct
import time

from go_test_suite import platform as _platform

_FB_DEV      = "/dev/fb0"
_VTCONSOLE   = "/sys/class/vtconsole"
_TIMEOUT_S   = 90

# ioctls
_FBIOGET_VSCREENINFO = 0x4600
_FBIOGET_FSCREENINFO = 0x4602

# struct input_event on 64-bit: time (2x long), type, code, value
_EVENT_FMT  = "qqHHi"
_EVENT_SIZE = struct.calcsize(_EVENT_FMT)

_EV_KEY, _EV_ABS, _EV_SYN = 0x01, 0x03, 0x00
_BTN_TOUCH = 0x14a
_ABS_X, _ABS_Y = 0x00, 0x01
_ABS_MT_POSITION_X, _ABS_MT_POSITION_Y = 0x35, 0x36

_COLOUR_BG    = (0x10, 0x10, 0x10)
_COLOUR_DOT   = (0x88, 0x88, 0x88)
_COLOUR_HIT   = (0x00, 0xC8, 0x00)

last_result = {}


# ─────────────────────────────────────────────────────────────────────────────
# Framebuffer
# ─────────────────────────────────────────────────────────────────────────────

class _Framebuffer:
    """Minimal /dev/fb0 writer. Reads the pixel layout from the driver rather
    than assuming one, so this keeps working if a panel comes up as RGB565."""

    def __init__(self, path=_FB_DEV):
        self.fd = os.open(path, os.O_RDWR)

        var = bytearray(160)
        fcntl.ioctl(self.fd, _FBIOGET_VSCREENINFO, var, True)
        (self.xres, self.yres, self.xres_virtual, _yres_virtual,
         _xoff, _yoff, self.bpp, _gray,
         self.r_off, self.r_len, _r_msb,
         self.g_off, self.g_len, _g_msb,
         self.b_off, self.b_len, _b_msb) = struct.unpack_from("17I", var, 0)

        # struct fb_fix_screeninfo up to line_length:
        #   id[16], smem_start (long), smem_len, type, type_aux, visual,
        #   xpanstep, ypanstep, ywrapstep (u16 each), pad, line_length.
        # line_length is field index 9 - the 2x padding yields no value.
        _FIX_FMT = "16sQIIIIHHH2xI"
        try:
            fix = bytearray(struct.calcsize(_FIX_FMT))
            fcntl.ioctl(self.fd, _FBIOGET_FSCREENINFO, fix, True)
            self.stride = struct.unpack(_FIX_FMT, bytes(fix))[9]
        except (OSError, struct.error, IndexError):
            self.stride = 0
        if not self.stride:
            self.stride = self.xres_virtual * (self.bpp // 8)

        self.bytes_pp = self.bpp // 8
        self.map = mmap.mmap(self.fd, self.stride * self.yres,
                             mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)

    def pack(self, rgb):
        r, g, b = rgb
        value = ((r >> (8 - self.r_len)) << self.r_off
                 | (g >> (8 - self.g_len)) << self.g_off
                 | (b >> (8 - self.b_len)) << self.b_off)
        return value.to_bytes(self.bytes_pp, "little")

    def fill(self, rgb):
        row = self.pack(rgb) * self.xres
        for y in range(self.yres):
            off = y * self.stride
            self.map[off:off + len(row)] = row

    def disc(self, cx, cy, radius, rgb):
        pixel = self.pack(rgb)
        for dy in range(-radius, radius + 1):
            y = cy + dy
            if not 0 <= y < self.yres:
                continue
            half = int((radius * radius - dy * dy) ** 0.5)
            x0 = max(0, cx - half)
            x1 = min(self.xres - 1, cx + half)
            if x1 < x0:
                continue
            off = y * self.stride + x0 * self.bytes_pp
            self.map[off:off + (x1 - x0 + 1) * self.bytes_pp] = pixel * (x1 - x0 + 1)

    def close(self):
        try:
            self.map.close()
        finally:
            os.close(self.fd)


# ─────────────────────────────────────────────────────────────────────────────
# fbcon
# ─────────────────────────────────────────────────────────────────────────────

def _fbcon_path():
    try:
        entries = sorted(os.listdir(_VTCONSOLE))
    except OSError:
        return None
    for entry in entries:
        path = os.path.join(_VTCONSOLE, entry)
        try:
            with open(os.path.join(path, "name")) as f:
                name = f.read().strip()
            with open(os.path.join(path, "bind")) as f:
                bound = f.read().strip()
        except OSError:
            continue
        if "frame buffer device" in name and bound == "1":
            return path
    return None


def _set_bind(path, value):
    try:
        with open(os.path.join(path, "bind"), "w") as f:
            f.write(value)
    except OSError:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Touch input
# ─────────────────────────────────────────────────────────────────────────────

def _absinfo(fd, axis):
    """Return (min, max) for an ABS axis via EVIOCGABS, or None.

    Without this the raw controller range has to be guessed; on the av101 it
    happens to match the panel, but that is a coincidence worth not relying on.

    EVIOCGABS has _IOC_READ set, so the request number has bit 31 set. Some
    CPython versions reject that as "signed integer is greater than maximum",
    hence the retry with the two's-complement equivalent.
    """
    size = struct.calcsize("6i")
    request = (2 << 30) | (size << 16) | (0x45 << 8) | (0x40 + axis)
    buf = bytearray(size)
    for req in (request, request - (1 << 32)):
        try:
            fcntl.ioctl(fd, req, buf, True)
            break
        except OverflowError:
            continue
        except OSError:
            return None
    else:
        return None
    _value, minimum, maximum, _fuzz, _flat, _res = struct.unpack("6i", bytes(buf))
    if maximum <= minimum:
        return None
    return minimum, maximum


def _scale(value, src, dst_max):
    lo, hi = src
    if hi <= lo:
        return 0
    pos = (value - lo) / float(hi - lo)
    return max(0, min(dst_max, int(pos * dst_max)))


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

def _dot_positions(w, h, radius):
    # 1.5x the radius from each edge: far enough out that a partially seated
    # flex connector shows up, close enough in that the whole dot stays on
    # screen. Gives roughly 88% edge-to-edge coverage on a 1280x720 panel.
    margin_x = margin_y = radius + radius // 2
    return [
        (margin_x,         margin_y),          # linksboven
        (w - 1 - margin_x, margin_y),          # rechtsboven
        (w // 2,           h // 2),            # midden
        (margin_x,         h - 1 - margin_y),  # linksonder
        (w - 1 - margin_x, h - 1 - margin_y),  # rechtsonder
    ]


def run():
    last_result.clear()

    info = _platform.detect()
    device = info.get("touch_device")
    if not device or not os.path.exists(_FB_DEV):
        return False

    fbcon = _fbcon_path()
    fb = None
    fd = None
    hit = set()

    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        x_axis = _absinfo(fd, _ABS_MT_POSITION_X) or _absinfo(fd, _ABS_X)
        y_axis = _absinfo(fd, _ABS_MT_POSITION_Y) or _absinfo(fd, _ABS_Y)

        if fbcon:
            _set_bind(fbcon, "0")

        fb = _Framebuffer()
        if x_axis is None:
            x_axis = (0, fb.xres - 1)
        if y_axis is None:
            y_axis = (0, fb.yres - 1)

        radius = max(24, min(fb.xres, fb.yres) // 14)
        dots = _dot_positions(fb.xres, fb.yres, radius)
        hit_radius_sq = int(radius * 1.8) ** 2

        fb.fill(_COLOUR_BG)
        for cx, cy in dots:
            fb.disc(cx, cy, radius, _COLOUR_DOT)

        deadline = time.time() + _TIMEOUT_S
        cur_x = cur_y = None

        while len(hit) < len(dots) and time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            try:
                data = os.read(fd, _EVENT_SIZE * 128)
            except BlockingIOError:
                # Non-blocking fd: select can report ready while another reader
                # drained the queue. Not an error, just nothing to do.
                continue
            for off in range(0, len(data) - _EVENT_SIZE + 1, _EVENT_SIZE):
                _s, _us, etype, code, value = struct.unpack_from(_EVENT_FMT, data, off)
                if etype == _EV_ABS:
                    if code in (_ABS_MT_POSITION_X, _ABS_X):
                        cur_x = value
                    elif code in (_ABS_MT_POSITION_Y, _ABS_Y):
                        cur_y = value
                elif etype == _EV_SYN and cur_x is not None and cur_y is not None:
                    px = _scale(cur_x, x_axis, fb.xres - 1)
                    py = _scale(cur_y, y_axis, fb.yres - 1)
                    for i, (dx, dy) in enumerate(dots):
                        if i in hit:
                            continue
                        if (px - dx) ** 2 + (py - dy) ** 2 <= hit_radius_sq:
                            hit.add(i)
                            fb.disc(dx, dy, radius, _COLOUR_HIT)

        if len(hit) == len(dots):
            time.sleep(1.0)                      # laat de operator het resultaat zien
        return len(hit) == len(dots)

    except OSError:
        return False
    finally:
        last_result.update({"hit": len(hit), "total": 5})
        if fb is not None:
            try:
                fb.fill(_COLOUR_BG)
                fb.close()
            except (OSError, ValueError):
                pass
        if fd is not None:
            os.close(fd)
        if fbcon:
            _set_bind(fbcon, "1")
