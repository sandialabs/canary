# Copyright 2013-2019 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import fcntl
import os
import struct
import sys
import termios
import textwrap
import traceback
from contextlib import contextmanager
from datetime import datetime
from io import StringIO

from .color import cescape
from .color import clen
from .color import cprint

_stacktrace = False
_timestamp = False
_prefix = "==>"
indent = "  "

VERBOSE = 3
INFO = 2
WARN = 1
ERROR = 0

_level = INFO
_debug = False


def set_log_level(arg: int) -> int:
    global _level
    assert arg in (VERBOSE, INFO, WARN, ERROR)
    orig = _level
    _level = arg
    if arg == VERBOSE:
        set_timestamp_stat(True)
    return orig


def get_log_level() -> int:
    return _level


def default_log_level() -> int:
    return INFO


def min_log_level() -> int:
    return ERROR


def max_log_level() -> int:
    return VERBOSE


def set_debug_stat(arg: bool) -> bool:
    global _debug
    orig = _debug
    _debug = bool(arg)
    return orig


def get_debug_stat() -> bool:
    return _debug


def set_stacktrace_stat(arg: bool) -> bool:
    global _stacktrace
    orig = _stacktrace
    _stacktrace = bool(arg)
    return orig


def get_stacktrace_stat() -> bool:
    return _stacktrace


def set_timestamp_stat(arg: bool) -> bool:
    global _timestamp
    orig = _timestamp
    _timestamp = bool(arg)
    return orig


def get_timestamp_stat() -> bool:
    return _timestamp


def process_stacktrace(countback):
    """Gives file and line frame 'countback' frames from the bottom"""
    st = traceback.extract_stack()
    # Not all entries may be spack files, we have to remove those that aren't.
    file_list = []
    for frame in st:
        # Check that the file is a spack file
        if frame[0].find("/spack") >= 0:
            file_list.append(frame[0])
    # We use commonprefix to find what the spack 'root' directory is.
    root_dir = os.path.commonprefix(file_list)
    root_len = len(root_dir)
    st_idx = len(st) - countback - 1
    st_text = "%s:%i " % (st[st_idx][0][root_len:], st[st_idx][1])
    return st_text


def get_prefix():
    return _prefix


def get_timestamp(force=False):
    """Get a string timestamp"""
    if get_debug_stat() or _timestamp or force:
        return datetime.now().strftime("[%Y-%m-%d-%H:%M:%S.%f] ")
    else:
        return ""


def emit(message, *args, **kwargs):
    stream = kwargs.get("stream", sys.stdout)
    wrap = kwargs.get("wrap", False)
    end = kwargs.get("end", "\n")
    break_long_words = kwargs.get("break_long_words", False)
    cprint("%s" % str(message), stream=stream, end=end)
    for arg in args:
        if wrap:
            lines = textwrap.wrap(
                str(arg),
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=break_long_words,
            )
            for line in lines:
                stream.write(line + "\n")
        else:
            stream.write(indent + str(arg) + end)
    stream.flush()


def info(message, *args, **kwargs):
    if get_log_level() < INFO:
        return
    format = kwargs.get("format", "*b")
    stream = kwargs.get("stream", sys.stdout)
    wrap = kwargs.get("wrap", False)
    prefix = kwargs.get("prefix", get_prefix())
    end = kwargs.get("end", "\n")
    break_long_words = kwargs.get("break_long_words", False)
    st_countback = kwargs.get("countback", 3)
    if not prefix:
        emit(
            message,
            *args,
            stream=stream,
            wrap=wrap,
            end=end,
            break_long_words=break_long_words,
        )
        return

    reported_by = kwargs.get("reported_by")
    if reported_by is not None:
        message += " (reported by {0})".format(reported_by)

    st_text = ""
    if get_stacktrace_stat():
        st_text = process_stacktrace(st_countback)
    cprint(
        "@%s{%s%s} %s%s"
        % (format, st_text, prefix, get_timestamp(), cescape(str(message))),
        stream=stream,
        end=end,
    )
    for arg in args:
        if wrap:
            lines = textwrap.wrap(
                str(arg),
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=break_long_words,
            )
            for line in lines:
                stream.write(line + "\n")
        else:
            stream.write(indent + str(arg) + end)
    stream.flush()


def verbose(message, *args, **kwargs):
    if get_log_level() >= VERBOSE:
        kwargs.setdefault("format", "c")
        info(message, *args, **kwargs)


def debug(message, *args, **kwargs):
    if get_debug_stat():
        kwargs.setdefault("format", "g")
        kwargs.setdefault("stream", sys.stdout)
        info(message, *args, **kwargs)


def error(message, *args, **kwargs):
    if get_log_level() < ERROR:
        return

    kwargs.setdefault("format", "*r")
    kwargs.setdefault("stream", sys.stderr)
    info("Error: " + str(message), *args, **kwargs)


def warn(message, *args, **kwargs):
    if get_log_level() < WARN:
        return

    kwargs.setdefault("format", "*Y")
    kwargs.setdefault("stream", sys.stderr)
    info("Warning: " + str(message), *args, **kwargs)


def die(message, *args, **kwargs):
    kwargs.setdefault("countback", 4)
    error(message, *args, **kwargs)
    sys.exit(1)


def hline(label=None, **kwargs):
    """Draw a labeled horizontal line.

    Keyword Arguments:
        char (str): Char to draw the line with.  Default '-'
        max_width (int): Maximum width of the line.  Default is 64 chars.
    """
    char = kwargs.pop("char", "-")
    max_width = kwargs.pop("max_width", 64)
    if kwargs:
        raise TypeError(
            "'%s' is an invalid keyword argument for this function."
            % next(kwargs.iterkeys())
        )

    rows, cols = terminal_size()
    if not cols:
        cols = max_width
    else:
        cols -= 2
    cols = min(max_width, cols)

    label = str(label)
    prefix = char * 2 + " "
    suffix = " " + (cols - len(prefix) - clen(label)) * char

    out = StringIO()
    out.write(prefix)
    out.write(label)
    out.write(suffix)

    print(out.getvalue())


def section(label, width=None, char="=", stream=None):
    if width is None:
        _, width = terminal_size()
    repl = "." * clen(label)
    stream = stream or sys.stdout
    text = f" {repl} ".center(width, char)
    stream.write(text.replace(repl, label) + "\n")


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


def fileno(file_or_fd):
    fd = getattr(file_or_fd, "fileno", lambda: file_or_fd)()
    if not isinstance(fd, int):
        raise ValueError("Expected a file (`.fileno()`) or a file descriptor")
    return fd


def streamify(arg, mode):
    if isinstance(arg, str):
        return open(arg, mode), True
    else:
        return arg, False


@contextmanager
def redirect_stdout(file_like=os.devnull, mode="w", stdout=None):
    stdout = stdout or sys.stdout
    file, fown = streamify(file_like, mode)
    stdout_fd = fileno(stdout)
    # copy stdout_fd before it is overwritten
    # NOTE: `copied` is inheritable on Windows when duplicating a standard stream
    with os.fdopen(os.dup(stdout_fd), "wb") as copied:
        stdout.flush()  # flush library buffers that dup2 knows nothing about
        try:
            os.dup2(fileno(file), stdout_fd)  # $ exec >&file
        except ValueError:  # filename
            with open(file, "wb") as to_file:
                os.dup2(to_file.fileno(), stdout_fd)  # $ exec > file
        try:
            yield stdout  # allow code to be run with the redirected stdout
        finally:
            # restore stdout to its previous value
            # NOTE: dup2 makes stdout_fd inheritable unconditionally
            stdout.flush()
            os.dup2(copied.fileno(), stdout_fd)  # $ exec >&copied
            if fown:
                file.close()


@contextmanager
def log_output(file_like, mode="w"):
    if file_like is None:
        yield
    else:
        with redirect_stdout(file_like=file_like, mode=mode):
            with redirect_stdout(file_like=sys.stdout, stdout=sys.stderr):
                yield
