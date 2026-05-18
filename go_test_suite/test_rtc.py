"""RTC test - verifies that the external battery-backed RTC chip is bound,
readable, ticks at the right rate and tracks the system clock. Does NOT
rely on the OS/POR flag, so it passes on freshly-assembled units whose
backup capacitor has not yet charged."""

import time

from go_test_suite import platform as _platform

_INTERVAL_S    = 3.0
_TICK_TOLERANCE = 1  # seconds of slack between rtc delta and sys delta


def _read_epoch(rtc_path):
    with open(f"{rtc_path}/since_epoch") as f:
        return int(f.read().strip())


def run():
    rtc_path = _platform.detect().get("rtc_path")
    if not rtc_path:
        return False

    try:
        rtc_1 = _read_epoch(rtc_path)
        sys_1 = int(time.time())
        time.sleep(_INTERVAL_S)
        rtc_2 = _read_epoch(rtc_path)
        sys_2 = int(time.time())
    except OSError:
        return False

    rtc_delta = rtc_2 - rtc_1
    sys_delta = sys_2 - sys_1

    # Chip must actually be ticking
    if rtc_delta < int(_INTERVAL_S) - _TICK_TOLERANCE:
        return False

    # RTC and system clock must track at the same rate
    if abs(rtc_delta - sys_delta) > _TICK_TOLERANCE:
        return False

    return True
