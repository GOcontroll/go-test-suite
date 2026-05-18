"""Platform / hardware capability detection.

Probes /proc and /sys so the suite enables only the tests that the current
controller actually supports. New hardware works without code changes as long
as it follows the same kernel conventions.
"""

import os
import re

try:
    import netifaces
    _HAS_NETIFACES = True
except ImportError:
    _HAS_NETIFACES = False


_MODEL_PATH    = "/proc/device-tree/model"
_CARDS_PATH    = "/proc/asound/cards"
_LED_SYSFS_FMT = "/sys/class/leds/case-led{}/brightness"
_RTC_SYSFS     = "/sys/class/rtc"
_AUDIO_CARDS   = ("tas2505audio",)
_RTC_CHIPS     = ("pcf85063",)


def _read_model():
    try:
        with open(_MODEL_PATH, "rb") as f:
            return f.read().rstrip(b"\x00").decode(errors="replace").strip()
    except OSError:
        return "unknown"


def _has_leds():
    return os.path.isfile(_LED_SYSFS_FMT.format(1))


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


def detect():
    audio_card = _detect_audio_card()
    rtc_path = _find_external_rtc()
    return {
        "model":          _read_model(),
        "has_leds":       _has_leds(),
        "has_audio":      audio_card is not None,
        "audio_card":     audio_card,
        "can_interfaces": _list_can(),
        "has_rtc":        rtc_path is not None,
        "rtc_path":       rtc_path,
    }
