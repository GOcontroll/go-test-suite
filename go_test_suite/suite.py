#!/usr/bin/env python3
"""GOcontroll Test Suite - post-assembly hardware test runner"""

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
    ("CAN bus test  (can0 ↔ can1,  can2 ↔ can3)", test_can.run,   False),
    ("LED test  (4x RGB case LEDs)",                        test_leds.run,  True),
]


# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    print(f"{_ORANGE}  GOcontroll Test Suite  v{_PKG_VERSION}{_RESET}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Interactive arrow-key menu
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


def _draw(options, selected, first=False):
    lines = [_SEP]
    for i, opt in enumerate(options):
        if i == selected:
            lines.append(f"{_CYAN}  ► {opt}{_RESET}")
        else:
            lines.append(f"    {opt}")
    lines.append(_SEP)
    lines.append(f"{_DARK_GREY}  ↑/↓ navigate   Enter select   ← back{_RESET}")
    if not first:
        sys.stdout.write(f"\033[{len(lines)}A")
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\n")
    sys.stdout.flush()


def _select(options):
    """
    Interactive arrow-key menu. Returns selected index, or -1 for back/quit.
    Falls back to numbered input when stdin is not a TTY.
    """
    if not _HAS_TTY or not sys.stdin.isatty():
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
        _draw(options, selected, first=True)
        while True:
            key = _getch()
            if key == b"\x1b[A":                           # ↑
                selected = (selected - 1) % n
                _draw(options, selected)
            elif key == b"\x1b[B":                         # ↓
                selected = (selected + 1) % n
                _draw(options, selected)
            elif key in (b"\r", b"\n"):                    # Enter
                return selected
            elif key in (b"\x1b[D", b"q",                 # ← or q (back)
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
    print(f"\nRunning: {name}")
    print("-" * 40)
    if visual_confirm:
        print("  Watch the controller LEDs, then confirm below.")
        print()
        func()
        passed = _confirm("Did all LEDs flash red, green and blue correctly?")
    else:
        passed = func()
    icon = f"{_GREEN}✓{_RESET}" if passed else f"{_RED}✗{_RESET}"
    print(f"\n  {icon}  {name}")
    return passed


def _run_all():
    results = [(name, _run_test(name, func, confirm)) for name, func, confirm in TESTS]
    all_passed = all(passed for _, passed in results)

    print()
    print("=" * 40)
    print("Summary")
    print("=" * 40)
    for name, passed in results:
        icon = f"{_GREEN}✓{_RESET}" if passed else f"{_RED}✗{_RESET}"
        print(f"  {icon}  {name}")
    print()
    print("All tests passed!" if all_passed else "One or more tests failed.")
    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    options = [name for name, _, _ in TESTS] + ["Run all tests"]

    while True:
        _print_banner()
        choice = _select(options)

        if choice == -1:
            sys.exit(0)

        _print_banner()

        if choice == len(TESTS):
            _run_all()
        else:
            name, func, confirm = TESTS[choice]
            _run_test(name, func, confirm)

        try:
            input("\n  Press Enter to return to menu...")
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)


if __name__ == "__main__":
    main()
