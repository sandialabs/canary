# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import curses.ascii
import fcntl
import os
import sys
import termios

DISABLE_KEYBOARD_QUERY: bool | None = None


def disable_keyboard_query() -> bool:
    global DISABLE_KEYBOARD_QUERY
    envbool = lambda x: os.getenv(x, "").upper() in ("TRUE", "ON", "1", "YES")
    if DISABLE_KEYBOARD_QUERY is None:
        if not sys.stdin.isatty():
            DISABLE_KEYBOARD_QUERY = True
        elif any(envbool(_) for _ in ("GITLAB_CI", "CANARY_DISABLE_KB")):
            DISABLE_KEYBOARD_QUERY = True
        else:
            DISABLE_KEYBOARD_QUERY = False
    return DISABLE_KEYBOARD_QUERY


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


def _get_key() -> str | None:
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


def get_key() -> str | None:
    if disable_keyboard_query():
        return None
    try:
        return _get_key()
    except (Exception, termios.error):
        return None
