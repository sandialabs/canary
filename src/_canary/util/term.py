# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import fcntl
import os
import struct
import termios


def terminal_size():
    """Gets the dimensions of the console: (rows, cols)."""

    def ioctl_gwinsz(fd):
        try:
            rc = struct.unpack("hh", fcntl.ioctl(fd, termios.TIOCGWINSZ, "1234"))
        except BaseException:
            return
        return rc

    rc = ioctl_gwinsz(0) or ioctl_gwinsz(1) or ioctl_gwinsz(2)
    if not rc:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            rc = ioctl_gwinsz(fd)
            os.close(fd)
        except BaseException:
            pass

    if not rc:
        rc = (os.environ.get("LINES", 25), os.environ.get("COLUMNS", 80))

    return int(rc[0]) or 25, int(rc[1]) or 80
