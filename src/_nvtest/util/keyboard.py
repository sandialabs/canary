import curses.ascii
import fcntl
import os
import sys
import termios
from typing import Union


def key_mapping(char: str) -> str:
    if len(char) == 3 and curses.ascii.isctrl(char[0]):
        key = ord(char[2])
    elif len(char) > 1:
        return char
    else:
        key = ord(char)
    mapping = {
        127: "backspace",
        10: "return",
        32: "space",
        9: "tab",
        27: "esc",
        65: "up",
        66: "down",
        67: "right",
        68: "left",
    }
    return mapping.get(key, chr(key))


def get_key() -> Union[None, str]:
    fd = sys.stdin.fileno()
    oldterm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, newattr)
    oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
    char = None
    try:
        char = os.read(sys.stdin.fileno(), 3).decode()
    except IOError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
    return None if not char else key_mapping(char)
