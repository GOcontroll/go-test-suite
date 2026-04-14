#!/usr/bin/env python3
"""GOcontroll Test Suite - post-assembly hardware test runner"""

import subprocess
import sys

try:
    import tty
    import termios
    _HAS_TTY = True
except ImportError:
    _HAS_TTY = False

_CYAN  = "\033[96m"   # light cyan — matches inquire::Select default
_GREEN = "\033[92m"
_RED   = "\033[91m"
_RESET = "\033[0m"

# Each entry: (display name, command, visual_confirm)
# visual_confirm=True: test has no automated pass/fail; user is asked after running.
TESTS = [
    ("CAN bus test  (can0 \u2194 can1,  can2 \u2194 can3)", "go-test-can",   False),
    ("LED test  (4x RGB case LEDs)",                        "go-test-leds",  True),
]


# ─────────────────────────────────────────────────────────────────────────────
# Banner  (same style as go-identify)
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner(version):
    text = f"  GOcontroll Test Suite  V{version}  "
    w = max(len(text), 60)
    print(f"╔{'═' * w}╗")
    print(f"║{text:<{w}}║")
    print(f"╚{'═' * w}╝")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Interactive arrow-key menu  (matches inquire::Select look and feel)
# ─────────────────────────────────────────────────────────────────────────────

def _getch():
    """Return one keypress as bytes; escape sequences are read in full."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.buffer.read(1)
        if ch == b"\x1b":
            ch += sys.stdin.buffer.read(2)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _draw(prompt, options, selected, first=False):
    lines = [f"{_CYAN}?{_RESET} {prompt}"]
    for i, opt in enumerate(options):
        if i == selected:
            lines.append(f"{_CYAN}> {opt}{_RESET}")
        else:
            lines.append(f"  {opt}")
    lines.append(f"{_CYAN}[\u2191\u2193 to move, enter to select]{_RESET}")

    if not first:
        sys.stdout.write(f"\033[{len(lines)}A")
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\n")
    sys.stdout.flush()


def _select(prompt, options):
    """
    Interactive arrow-key menu.  Returns the selected index, or -1 for quit.
    Falls back to numbered input when stdin is not a TTY.
    """
    if not _HAS_TTY or not sys.stdin.isatty():
        print(f"? {prompt}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        print()
        try:
            choice = input("Enter number (q to quit): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return -1
        if choice == "q":
            return -1
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        return -1

    selected = 0
    n = len(options)
    sys.stdout.write("\033[?25l")   # hide cursor
    sys.stdout.flush()
    try:
        _draw(prompt, options, selected, first=True)
        while True:
            key = _getch()
            if key == b"\x1b[A":            # ↑
                selected = (selected - 1) % n
                _draw(prompt, options, selected)
            elif key == b"\x1b[B":          # ↓
                selected = (selected + 1) % n
                _draw(prompt, options, selected)
            elif key in (b"\r", b"\n"):     # Enter
                return selected
            elif key in (b"\x03", b"\x04"): # Ctrl-C / Ctrl-D
                return -1
    finally:
        sys.stdout.write("\033[?25h")       # restore cursor
        sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Test runners
# ─────────────────────────────────────────────────────────────────────────────

def _run_quiet(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        pass
    return None


def _confirm(prompt):
    """Ask a yes/no question; returns True for yes (default)."""
    try:
        answer = input(f"  {prompt} [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "y"
    return answer in ("y", "yes", "")


def _run_test(name, command, visual_confirm=False):
    print(f"\nRunning: {name}")
    print("-" * 40)
    if visual_confirm:
        print("  Watch the controller LEDs, then confirm below.")
        print()
    result = subprocess.run([command])
    if visual_confirm:
        passed = _confirm("Did all LEDs flash red, green and blue correctly?")
    else:
        passed = result.returncode == 0
    icon = f"{_GREEN}\u2713{_RESET}" if passed else f"{_RED}\u2717{_RESET}"
    print(f"\n  {icon}  {name}")
    return passed


def _run_all():
    results = [(name, _run_test(name, cmd, confirm)) for name, cmd, confirm in TESTS]
    all_passed = all(passed for _, passed in results)

    print()
    print("=" * 40)
    print("Summary")
    print("=" * 40)
    for name, passed in results:
        icon = f"{_GREEN}\u2713{_RESET}" if passed else f"{_RED}\u2717{_RESET}"
        print(f"  {icon}  {name}")
    print()
    print("All tests passed!" if all_passed else "One or more tests failed.")
    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    version = _run_quiet(["dpkg-query", "-W", "-f=${Version}", "go-test-suite"]) or "1.0.0"
    _print_banner(version)

    options = [name for name, _, _ in TESTS] + ["Run all tests"]
    choice = _select("What do you want to test?", options)

    if choice == -1:
        sys.exit(0)

    print()

    if choice == len(TESTS):    # "Run all tests"
        passed = _run_all()
    else:
        name, command, confirm = TESTS[choice]
        passed = _run_test(name, command, confirm)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
