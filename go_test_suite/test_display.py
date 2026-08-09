"""Display / GPU test - renders a spinning cube on the panel with kmscube and
asks the operator to confirm they saw it. Used on HMI1 (Moduline Display).

Covers three layers in one go, which is why it is worth the 20 seconds:

  * the GPU        - kmscube renders through OpenGL ES on the Vivante core
                     (etnaviv), it is not a framebuffer blit from the CPU;
  * the display     - the LCDIF controller does the modeset and page-flips
    controller       every frame to scanout;
  * the panel      - LVDS wiring, timings and backlight.

A steady frame rate matching the panel refresh is the real evidence: it means
every page-flip landed on a vblank. Marginal timings or a bad flex show up as a
low or fluctuating rate long before the picture visibly breaks up.
"""

import os
import re
import shutil
import subprocess
import tempfile
import time

from go_test_suite import platform as _platform

_VTCONSOLE  = "/sys/class/vtconsole"
_DRI_DIR    = "/dev/dri"
_DURATION_S = 20
_MIN_FRAMES = 30

_RENDERED_RE = re.compile(r"Rendered\s+(\d+)\s+frames in\s+([\d.]+)\s+sec\s+\(([\d.]+)\s+fps\)")

# Filled in by run() so the caller can report the measured rate.
last_result = {}


def _fbcon_path():
    """Return the vtconsole sysfs dir fbcon is currently bound to, or None.

    fbcon draws the Linux console straight onto the panel and takes the display
    back as soon as a DRM client does a modeset, so the rendered frames would
    only flash past. Unbinding it hands the panel to the GPU for the duration of
    the test; run() always binds it back.
    """
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


def _card_node(connector):
    """/sys/class/drm/card1-LVDS-1 -> /dev/dri/card1, or None."""
    base = os.path.basename(connector or "")
    if not base:
        return None
    node = os.path.join(_DRI_DIR, base.split("-", 1)[0])
    return node if os.path.exists(node) else None


def _run_kmscube(cmd):
    """Run kmscube for _DURATION_S seconds and return its output.

    stdin must stay open without ever becoming readable: kmscube puts fd 0 in
    its select() set and quits with "user interrupted!" the moment it is. Both
    DEVNULL and a closed pipe count as readable (immediate EOF), so either makes
    it exit after a fraction of a second while still returning 0 - which reads
    as a healthy run but shows the operator almost nothing. An unwritten pipe
    never becomes readable, so the process keeps rendering until we stop it.

    stdout goes to a temp file rather than a pipe so nothing can deadlock if the
    process outlives our read.
    """
    with tempfile.TemporaryFile("w+") as out:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(_DURATION_S)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdin:
                proc.stdin.close()
        out.seek(0)
        return out.read()


def run():
    """Return True when kmscube rendered a plausible number of frames.

    The operator still has to confirm they actually saw the cube - this only
    proves the software side reached scanout.
    """
    last_result.clear()

    info = _platform.detect()
    if not info.get("has_display"):
        return False

    kmscube = shutil.which("kmscube")
    if kmscube is None:
        return False

    cmd = [kmscube]
    card = _card_node(info.get("display_connector"))
    if card:
        cmd += ["-D", card]

    fbcon = _fbcon_path()
    if fbcon:
        _set_bind(fbcon, "0")

    try:
        output = _run_kmscube(cmd)
    except (OSError, ValueError):
        return False
    finally:
        if fbcon:
            _set_bind(fbcon, "1")

    frames = fps = 0.0
    for match in _RENDERED_RE.finditer(output):
        frames = int(match.group(1))
        fps = float(match.group(3))

    last_result.update({
        "frames": frames,
        "fps": fps,
        "mode": info.get("display_mode"),
        "connector": info.get("display_connector"),
    })

    # The frame rate is the part the operator cannot see: a picture that looks
    # fine but runs well below the panel refresh points at timings or wiring.
    if frames:
        print("  rendered %d frames at %.1f fps on %s"
              % (frames, fps, info.get("display_mode") or "unknown mode"))

    return frames >= _MIN_FRAMES
