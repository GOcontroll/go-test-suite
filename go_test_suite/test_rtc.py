"""RTC test - verifies that the external battery-backed RTC chip is bound,
readable, ticks at the right rate and tracks the system clock. Does NOT
rely on the OS/POR flag, so it passes on freshly-assembled units whose
backup capacitor has not yet charged.

Offered whenever the device tree declares the chip. A chip that is declared
but did not bind is a failure, not a reason to skip the test."""

import time

from go_test_suite import platform as _platform

_INTERVAL_S    = 3.0
_TICK_TOLERANCE = 1  # seconds of slack between rtc delta and sys delta


def _read_epoch(rtc_path):
    with open(f"{rtc_path}/since_epoch") as f:
        return int(f.read().strip())


def _set_clock_at_boot(rtc_path):
    """True when the kernel set the system clock from this RTC at boot, None
    when the kernel does not say."""
    try:
        with open(f"{rtc_path}/hctosys") as f:
            return f.read().strip() == "1"
    except OSError:
        return None


def run():
    info = _platform.detect()
    rtc_path = info.get("rtc_path")
    if not rtc_path:
        print("  RTC declared in the device tree (%s) but no driver bound."
              % info.get("rtc_dt_node"))
        print("  Check dmesg for the RTC probe error.")
        return False

    try:
        rtc_1 = _read_epoch(rtc_path)
        sys_1 = int(time.time())
        time.sleep(_INTERVAL_S)
        rtc_2 = _read_epoch(rtc_path)
        sys_2 = int(time.time())
    except OSError as e:
        print("  RTC could not be read: %s" % e)
        return False

    rtc_delta = rtc_2 - rtc_1
    sys_delta = sys_2 - sys_1

    # Chip must actually be ticking
    if rtc_delta < int(_INTERVAL_S) - _TICK_TOLERANCE:
        print("  RTC is not ticking (advanced %d s in %d s)."
              % (rtc_delta, int(_INTERVAL_S)))
        return False

    # RTC and system clock must track at the same rate
    if abs(rtc_delta - sys_delta) > _TICK_TOLERANCE:
        print("  RTC and system clock drift apart (%d s vs %d s)."
              % (rtc_delta, sys_delta))
        return False

    # Informational only: a unit whose RTC was first set after this boot
    # legitimately reports 0 here until the next boot.
    if _set_clock_at_boot(rtc_path) is False:
        print("  Note: the system clock was not set from the RTC at this boot.")

    return True
