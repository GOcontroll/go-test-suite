#!/usr/bin/env python3
"""GOcontroll Test Suite - post-assembly hardware test runner"""

import os
import select
import sys

from go_test_suite import __version__ as _PKG_VERSION
from go_test_suite import test_can, test_leds

try:
    import tty
    import termios
    _HAS_TTY = True
except ImportError:
    _HAS_TTY = False

_ORANGE    = "\x1b[38;2;255;102;0m"
_CYAN      = "\033[96m"
_GREEN     = "\033[92m"
_RED       = "\033[91m"
_DARK_GREY = "\033[90m"
_RESET     = "\033[0m"

_SEP = "  ------------------------------------"

# (display name, function, visual_confirm)
TESTS = [
    ("CAN tests", test_can.run,  False),
    ("LED test",  test_leds.run, True),
]


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    print(f"{_ORANGE}  GOcontroll Test Suite  v{_PKG_VERSION}{_RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Interactive arrow-key menu
# ─────────────────────────────────────────────────────────────────────────────

def _getch():
    """Return one keypress as bytes; escape sequences are read in full.
    Lone Esc returns b'\\x1b'; sequences like arrow keys return b'\\x1b[A' etc.
    Uses os.read() directly to bypass Python's buffered IO layer."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        if ch == b"\x1b" and select.select([fd], [], [], 0.1)[0]:
            ch += os.read(fd, 2)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _draw(description, options, selected, first=False, icons=None):
    lines = [_SEP, f"  {description}", _SEP]
    for i, opt in enumerate(options):
        if icons and i < len(icons) and icons[i] is not None:
            color = _GREEN if icons[i] else _RED
            mark = f"  {color}{'✓' if icons[i] else '✗'}{_RESET}"
        else:
            mark = ""
        if i == selected:
            lines.append(f"{_CYAN}  ► {opt}{_RESET}{mark}")
        else:
            lines.append(f"    {opt}{mark}")
    lines.append(_SEP)
    lines.append(f"{_DARK_GREY}  ↑/↓ navigate   Enter select   Esc back{_RESET}")
    if not first:
        sys.stdout.write(f"\033[{len(lines)}A")
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\n")
    sys.stdout.flush()


def _select(description, options, icons=None):
    """
    Interactive arrow-key menu. Returns selected index, or -1 for back/quit.
    Falls back to numbered input when stdin is not a TTY.
    """
    if not _HAS_TTY or not sys.stdin.isatty():
        print(_SEP)
        print(f"  {description}")
        print(_SEP)
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        print(_SEP)
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
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    try:
        _draw(description, options, selected, first=True, icons=icons)
        while True:
            key = _getch()
            if key == b"\x1b[A":                           # ↑
                selected = (selected - 1) % n
                _draw(description, options, selected, icons=icons)
            elif key == b"\x1b[B":                         # ↓
                selected = (selected + 1) % n
                _draw(description, options, selected, icons=icons)
            elif key in (b"\r", b"\n"):                    # Enter
                return selected
            elif key in (b"\x1b", b"\x1b[D",               # Esc or ← (back)
                         b"\x03", b"\x04"):               # Ctrl-C / Ctrl-D
                return -1
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Test runners
# ─────────────────────────────────────────────────────────────────────────────

def _confirm(prompt):
    """Ask a yes/no question; returns True for yes (default)."""
    try:
        answer = input(f"  {prompt} [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "y"
    return answer in ("y", "yes", "")



def _run_test(name, func, visual_confirm=False):
    print(_SEP)
    print(f"  Running {name}..")
    print(_SEP)
    try:
        if visual_confirm:
            print("  Watch the controller LEDs, then confirm below.")
            print()
            func()
            passed = _confirm("Did all LEDs flash red, green and blue correctly?")
        else:
            passed = func()
    except Exception:
        passed = False
    return passed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    test_results = {}  # test index → True/False

    try:
        while True:
            options = [name for name, _, _ in TESTS] + ["Run all tests"]
            icons   = [test_results.get(i) for i in range(len(TESTS))] + [None]

            _print_banner()
            choice = _select("Select the test you want to perform.", options, icons=icons)

            if choice == -1:
                sys.exit(0)

            if choice == len(TESTS):
                for i, (name, func, confirm) in enumerate(TESTS):
                    _print_banner()
                    test_results[i] = _run_test(name, func, confirm)
            else:
                _print_banner()
                name, func, confirm = TESTS[choice]
                test_results[choice] = _run_test(name, func, confirm)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
