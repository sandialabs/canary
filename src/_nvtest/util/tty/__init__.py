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

PRINT_TIMESTAMP = False
DEFAULT_PREFIX = "==>"
INDENT = "  "

DEBUG = 4
VERBOSE = 3
INFO = 2
WARN = 1
ERROR = 0


DEFAULT_LOG_LEVEL: int = int(os.getenv("NVTEST_LOG_LEVEL", str(INFO)))
LOG_LEVEL = DEFAULT_LOG_LEVEL
builtin_print = print


HAVE_DEBUG = False


def set_log_level(arg: int) -> int:
    global LOG_LEVEL
    global PRINT_TIMESTAMP
    assert arg in (DEBUG, VERBOSE, INFO, WARN, ERROR)
    orig = LOG_LEVEL
    LOG_LEVEL = arg
    if arg >= VERBOSE:
        PRINT_TIMESTAMP = True
    return orig


def is_verbose() -> bool:
    return LOG_LEVEL >= VERBOSE


def get_log_level() -> int:
    return LOG_LEVEL


def default_log_level() -> int:
    return DEFAULT_LOG_LEVEL


def min_log_level() -> int:
    return ERROR


def max_log_level() -> int:
    return DEBUG


def set_debug(arg: bool) -> None:
    global HAVE_DEBUG
    HAVE_DEBUG = arg


@contextmanager
def timestamps():
    global PRINT_TIMESTAMP
    save = PRINT_TIMESTAMP
    PRINT_TIMESTAMP = True
    yield
    PRINT_TIMESTAMP = save


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


def get_timestamp(force=False):
    """Get a string timestamp"""
    if LOG_LEVEL >= DEBUG or PRINT_TIMESTAMP or force:
        return datetime.now().strftime("[%Y-%m-%d-%H:%M:%S.%f] ")
    else:
        return ""


def emit(message, stream=sys.stdout) -> None:
    stream.write(message)
    stream.flush()


def print(*args, **kwargs):
    force = kwargs.pop("force", False)
    if not force and LOG_LEVEL < INFO:
        return
    centered = kwargs.pop("centered", False)
    char = kwargs.pop("char", "—")
    if centered:
        _, width = terminal_size()
        label = " ".join(str(_) for _ in args)
        repl = "." * clen(label)
        text = f" {repl} ".center(width, char)
        args = [text.replace(repl, label)]
    builtin_print(*args, **kwargs)


def format_message(message, *args, **kwargs) -> str:
    format = kwargs.get("format", "*b")
    wrap = kwargs.get("wrap", False)
    end = kwargs.get("end", "\n")
    prefix = kwargs.get("prefix", DEFAULT_PREFIX)
    st_text = ""
    if "countback" in kwargs:
        st_countback = kwargs.get("countback", 3)
        st_text = process_stacktrace(st_countback)
    if prefix is None:
        fmt = "%(ts)s%(msg)s"
    else:
        fmt = "@%(fmt)s{%(st_text)s%(prefix)s} %(ts)s%(msg)s"
    kwds = {
        "fmt": format,
        "st_text": st_text,
        "prefix": prefix,
        "ts": get_timestamp(),
        "msg": cescape(str(message)),
    }
    text = fmt % kwds
    stream = StringIO()
    cprint(text, stream=stream, end=end)
    for arg in args:
        if not wrap:
            stream.write(INDENT + str(arg) + end)
            continue
        lines = textwrap.wrap(
            str(arg),
            initial_indent=INDENT,
            subsequent_indent=INDENT,
            break_long_words=False,
        )
        for line in lines:
            stream.write(line + "\n")
    stream.flush()
    return stream.getvalue()


def info(message, *args, **kwargs):
    if LOG_LEVEL < INFO:
        return
    text = format_message(message, *args, **kwargs)
    emit(text, stream=kwargs.get("stream", sys.stdout))


def verbose(message, *args, **kwargs):
    if LOG_LEVEL < VERBOSE:
        return
    kwargs.setdefault("format", "*c")
    text = format_message(message, *args, **kwargs)
    emit(text, stream=kwargs.get("stream", sys.stdout))


def debug(message, *args, **kwargs):
    if not HAVE_DEBUG and LOG_LEVEL < DEBUG:
        return
    kwargs.setdefault("format", "*g")
    text = format_message(message, *args, **kwargs)
    emit(text, stream=kwargs.get("stream", sys.stdout))


def error(message, *args, **kwargs):
    if LOG_LEVEL < ERROR:
        return
    kwargs.setdefault("format", "*r")
    text = format_message("Error: " + str(message), *args, **kwargs)
    emit(text, stream=kwargs.get("stream", sys.stderr))


def warn(message, *args, **kwargs):
    if LOG_LEVEL < WARN:
        return
    kwargs.setdefault("format", "*Y")
    text = format_message("Warning: " + str(message), *args, **kwargs)
    emit(text, stream=kwargs.get("stream", sys.stderr))


def die(message, *args, **kwargs):
    if HAVE_DEBUG:
        kwargs.setdefault("countback", 4)
    code = kwargs.pop("code", 1)
    error(message, *args, **kwargs)
    sys.exit(code)


def hline(label=None, **kwargs):
    """Draw a labeled horizontal line.

    Keyword Arguments:
        char (str): Char to draw the line with.  Default '-'
        max_width (int): Maximum width of the line.  Default is 64 chars.
    """
    char = kwargs.pop("char", "—")
    max_width = kwargs.pop("max_width", 64)
    if kwargs:
        raise TypeError(
            "'%s' is an invalid keyword argument for this function."
            % next(kwargs.iterkeys())
        )

    _, cols = terminal_size()
    if max_width < 0:
        max_width = cols
    cols = min(max_width, cols - 2)

    out = StringIO()
    if label is None:
        out.write(char * max_width)
    else:
        label = str(label)
        prefix = char * 2 + " "
        suffix = " " + (cols - len(prefix) - clen(label)) * char
        out.write(prefix)
        out.write(label)
        out.write(suffix)
    builtin_print(out.getvalue())


def section(label, width=None, char="—", stream=None):
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
    if not hasattr(file_or_fd, "fileno"):
        raise ValueError("Expected a file (`.fileno()`) or a file descriptor")
    return file_or_fd.fileno()


def streamify(arg, mode):
    if isinstance(arg, str):
        return open(arg, mode), True
    else:
        return arg, False


@contextmanager
def redirect_stdout(to=os.devnull, stdout=None):
    stdout = stdout or sys.stdout
    stdout_fd = fileno(stdout)
    # copy stdout_fd before it is overwritten
    # NOTE: `copied` is inheritable on Windows when duplicating a standard stream
    with os.fdopen(os.dup(stdout_fd), "wb") as copied:
        stdout.flush()  # flush library buffers that dup2 knows nothing about
        os.dup2(fileno(to), stdout_fd)  # $ exec >&file
        try:
            yield stdout  # allow code to be run with the redirected stdout
        finally:
            # restore stdout to its previous value
            # NOTE: dup2 makes stdout_fd inheritable unconditionally
            stdout.flush()
            os.dup2(copied.fileno(), stdout_fd)  # $ exec >&copied


def merged_stderr_stdout():  # $ exec 2>&1
    return redirect_stdout(to=sys.stdout, stdout=sys.stderr)


@contextmanager
def log_output(file_like, mode="w"):
    if file_like is None:
        yield
    else:
        file, fown = streamify(file_like, mode)
        with redirect_stdout(to=file):
            with merged_stderr_stdout():
                yield
        if fown:
            file.close()


@contextmanager
def restore(fd=None):
    fd = fd or sys.stdin.fileno()
    if os.isatty(fd):
        save_tty_attr = termios.tcgetattr(fd)
        yield
        termios.tcsetattr(fd, termios.TCSAFLUSH, save_tty_attr)
    else:
        yield


def reset():
    fd = sys.stdin.fileno()
    save_tty_attr = termios.tcgetattr(fd)
    termios.tcsetattr(fd, termios.TCSAFLUSH, save_tty_attr)


class tee:
    def __init__(self):
        self.fh = None

    def open(self, filename):
        self.fh = open(filename, "w")

    def write(self, *args):
        if self.fh is None:
            raise Exception("tee being written to without being initialized")
        line = " ".join(str(_) for _ in args)
        self.fh.write(line + "\n")
        sys.stdout.write(line + "\n")

    def flush(self):
        if self.fh is not None:
            self.fh.flush()

    def close(self):
        if self.fh is not None:
            self.fh.close()
        self.fh = None
