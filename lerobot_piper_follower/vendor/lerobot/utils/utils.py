# Vendored minimal version from LeRobot (Apache 2.0)
# Only the functions used by lerobot.motors.motors_bus are included.
import select
import sys
import platform


def enter_pressed() -> bool:
    if platform.system() == "Windows":
        import msvcrt
        if msvcrt.kbhit():
            key = msvcrt.getch()
            return key in (b"\r", b"\n")
        return False
    else:
        return select.select([sys.stdin], [], [], 0)[0] and sys.stdin.readline().strip() == ""


def move_cursor_up(lines):
    print(f"\033[{lines}A", end="")
