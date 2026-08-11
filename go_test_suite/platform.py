"""Platform / hardware capability detection.

Probes /proc and /sys so the suite enables only the tests that the current
controller actually supports. New hardware works without code changes as long
as it follows the same kernel conventions.
"""

import os
import re
import shutil

try:
    import netifaces
    _HAS_NETIFACES = True
except ImportError:
    _HAS_NETIFACES = False

try:
    import smbus2
    _HAS_SMBUS = True
except ImportError:
    _HAS_SMBUS = False


_MODEL_PATH    = "/proc/device-tree/model"
_CARDS_PATH    = "/proc/asound/cards"
_LED_SYSFS_FMT = "/sys/class/leds/case-led{}/brightness"
_LED_I2C_BUS   = 2
_LED_I2C_ADDR  = 0x14
_LED_REG_ENABLE = 0x00
_RTC_SYSFS     = "/sys/class/rtc"
_DRM_SYSFS     = "/sys/class/drm"
_INPUT_SYSFS   = "/sys/class/input"
_AUDIO_CARDS   = ("tas2505audio",)
_RTC_CHIPS     = ("pcf85063",)

_ABS_MT_POSITION_X = 0x35


def _read_model():
    try:
        with open(_MODEL_PATH, "rb") as f:
            return f.read().rstrip(b"\x00").decode(errors="replace").strip()
    except OSError:
        return "unknown"


def _probe_i2c_leds():
    """Return True when the I2C LED driver answers on its bus.

    Reading the enable register is enough to tell the chip is there and leaves
    the LEDs as they were, so probing costs nothing on units without it.
    """
    if not _HAS_SMBUS or not os.path.exists(f"/dev/i2c-{_LED_I2C_BUS}"):
        return False
    try:
        with smbus2.SMBus(_LED_I2C_BUS) as bus:
            bus.read_byte_data(_LED_I2C_ADDR, _LED_REG_ENABLE)
    except OSError:
        return False
    return True


def _detect_leds():
    """Return the backend driving the case LEDs, or None when there are none.

    Both backends have to be probed because both are supported by the LED test:
    some controllers expose the LEDs as sysfs class devices, others hang the
    same four RGB LEDs off an I2C driver with no sysfs entry at all. Checking
    sysfs alone hides the LED test on the latter.
    """
    if os.path.isfile(_LED_SYSFS_FMT.format(1)):
        return "sysfs"
    if _probe_i2c_leds():
        return "i2c"
    return None


def _detect_audio_card():
    try:
        with open(_CARDS_PATH) as f:
            cards = f.read()
    except OSError:
        return None
    for name in _AUDIO_CARDS:
        if re.search(rf"\b{re.escape(name)}\b", cards):
            return name
    return None


def _list_can():
    if not _HAS_NETIFACES:
        return []
    return sorted(i for i in netifaces.interfaces() if i.startswith("can"))


def _find_external_rtc():
    """Return the /sys/class/rtc/rtcN path of the first matching external RTC
    chip, or None if no known external chip is present."""
    try:
        entries = sorted(os.listdir(_RTC_SYSFS))
    except OSError:
        return None
    for entry in entries:
        try:
            with open(os.path.join(_RTC_SYSFS, entry, "name")) as f:
                name = f.read().strip().lower()
        except OSError:
            continue
        for chip in _RTC_CHIPS:
            if chip in name:
                return os.path.join(_RTC_SYSFS, entry)
    return None


def _find_display():
    """Return (connector sysfs path, first mode) for the first connected DRM
    connector, or (None, None) when nothing is attached.

    Entries without a dash are the card and render nodes (cardN, renderDN,
    version); only the connector directories carry status and modes.
    """
    try:
        entries = sorted(os.listdir(_DRM_SYSFS))
    except OSError:
        return None, None
    for entry in entries:
        if "-" not in entry:
            continue
        path = os.path.join(_DRM_SYSFS, entry)
        try:
            with open(os.path.join(path, "status")) as f:
                if f.read().strip() != "connected":
                    continue
            with open(os.path.join(path, "modes")) as f:
                mode = f.readline().strip() or None
        except OSError:
            continue
        return path, mode
    return None, None


def _find_touch():
    """Return /dev/input/eventN of the first multitouch digitiser, or None.

    Matched on the ABS_MT_POSITION_X capability bit rather than on a driver
    name, so a different controller on a future panel still works. The av123
    panel has no touch controller at all - no input devices are created there,
    which is normal and not a fault.
    """
    try:
        entries = sorted(os.listdir(_INPUT_SYSFS))
    except OSError:
        return None
    for entry in entries:
        if not entry.startswith("event"):
            continue
        caps = os.path.join(_INPUT_SYSFS, entry, "device", "capabilities", "abs")
        try:
            with open(caps) as f:
                mask = int(f.read().strip().replace(" ", ""), 16)
        except (OSError, ValueError):
            continue
        if mask & (1 << _ABS_MT_POSITION_X):
            node = os.path.join("/dev/input", entry)
            if os.path.exists(node):
                return node
    return None


def detect():
    led_backend = _detect_leds()
    audio_card = _detect_audio_card()
    rtc_path = _find_external_rtc()
    display_connector, display_mode = _find_display()
    # kmscube ships with the display rootfs variant only, so requiring it keeps
    # the display test off headless units without pulling it in as a package
    # dependency. A connected connector alone is not enough - a headless board
    # with a stray HDMI bridge would otherwise offer a test it cannot run.
    has_display = display_connector is not None and shutil.which("kmscube") is not None
    touch_device = _find_touch()
    return {
        "model":             _read_model(),
        "has_leds":          led_backend is not None,
        "led_backend":       led_backend,
        "has_audio":         audio_card is not None,
        "audio_card":        audio_card,
        "can_interfaces":    _list_can(),
        "has_rtc":           rtc_path is not None,
        "rtc_path":          rtc_path,
        "has_display":       has_display,
        "display_connector": display_connector,
        "display_mode":      display_mode,
        # The touch test draws on /dev/fb0 directly, so it needs a framebuffer
        # but not kmscube - hence its own condition rather than has_display.
        "has_touch":         touch_device is not None and os.path.exists("/dev/fb0"),
        "touch_device":      touch_device,
    }
