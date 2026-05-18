"""Audio output test - plays a tone via the on-board DAC and asks the
operator to confirm they heard it. Used on HMI1 (tas2505 codec)."""

import os
import subprocess

from go_test_suite import platform as _platform

_SYSTEM_WAV   = "/usr/share/sounds/alsa/Front_Center.wav"
_BUNDLED_WAV  = os.path.join(os.path.dirname(__file__), "sounds", "test.wav")


def _pick_wav():
    if os.path.isfile(_SYSTEM_WAV):
        return _SYSTEM_WAV
    if os.path.isfile(_BUNDLED_WAV):
        return _BUNDLED_WAV
    return None


def run():
    info = _platform.detect()
    card = info.get("audio_card")
    if not card:
        return False

    wav = _pick_wav()
    if wav is None:
        return False

    try:
        subprocess.run(
            ["aplay", "-q", "-D", f"hw:CARD={card},DEV=0", wav],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True
