# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import math
import os
import sys
import termios
import time
import traceback
from contextlib import contextmanager
from io import StringIO
from typing import IO
from typing import Any
from typing import Generator
from typing import TextIO

from ..third_party.color import cescape
from ..third_party.color import clen
from ..third_party.color import cprint
from .term import terminal_size
from .time import hhmmss

SUPPRESS = -10
TRACE = 0
DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40
FATAL = 50
ALWAYS = 100


LEVEL = WARNING
TIMESTAMP = False
FORMAT = "%(prefix)s%(timestamp)s%(message)s"
WARNINGS = WARNING


builtin_print = print
log_levels = (TRACE, DEBUG, INFO, WARNING, ERROR, FATAL)
level_color_map: dict[int, str] = {
    TRACE: "c",
    DEBUG: "g",
    INFO: "b",
    WARNING: "Y",
    ERROR: "r",
    FATAL: "r",
}
level_name_map: dict[int, str] = {
    TRACE: "TRACE",
    DEBUG: "DEBUG",
    INFO: "INFO",
    WARNING: "WARNING",
    ERROR: "ERROR",
    FATAL: "FATAL",
}


def get_timestamp():
    """Get a string timestamp"""
    if TIMESTAMP:
        return datetime.datetime.now().strftime("[%Y-%m-%d-%H:%M:%S.%f] ")
    else:
        return ""


@contextmanager
def timestamps() -> Generator[None, None, None]:
    global TIMESTAMP
    save = TIMESTAMP
    TIMESTAMP = True
    yield
    TIMESTAMP = save


@contextmanager
def level(level: int) -> Generator[None, None, None]:
    global LEVEL
    save_level = LEVEL
    set_level(level)
    yield
    set_level(save_level)


def set_level(level: int) -> None:
    global LEVEL
    assert level in log_levels
    LEVEL = level


def set_warning_level(level: str) -> None:
    global WARNINGS
    assert level in ("all", "ignore", "error")
    if level == "all":
        WARNINGS = WARNING
    elif level == "ignore":
        WARNINGS = SUPPRESS
    elif level == "error":
        WARNINGS = ERROR


def set_format(format: str) -> None:
    global FORMAT
    FORMAT = format


def get_level(name: str | None = None) -> int:
    if name is None:
        return LEVEL
    for level_num, level_name in level_name_map.items():
        if name == level_name:
            return level_num
    raise ValueError(name)


def get_level_name(level: int) -> str:
    for level_num, level_name in level_name_map.items():
        if level == level_num:
            return level_name
    raise ValueError(level)


def level_color(level: int) -> str:
    for level_num, level_color in level_color_map.items():
        if level == level_num:
            return level_color
    raise ValueError(level)


def format_message(
    message: str,
    *,
    end: str = "\n",
    prefix: str | None = None,
    format: str | None = None,
    rewind: bool = False,
) -> str:
    if format == "center":
        _, width = terminal_size()
        dots = "." * clen(message)
        tmp = f" {dots} ".center(width, "-")
        message = tmp.replace(dots, message)
        format = "%(message)s"
    kwds = {"prefix": prefix or "", "timestamp": get_timestamp(), "message": cescape(str(message))}
    text = (format or FORMAT) % kwds
    file = StringIO()
    if rewind:
        file.write("\r")
    cprint(text, stream=file, end=end)
    file.flush()
    return file.getvalue()


def log(
    level: int,
    message: str,
    *,
    file: TextIO = sys.stdout,
    prefix: str | None = None,
    end: str = "\n",
    format: str | None = None,
    ex: Exception | None = None,
    rewind: bool = False,
) -> None:
    if level == SUPPRESS:
        return
    if level >= LEVEL:
        text = format_message(message, end=end, prefix=prefix, format=format, rewind=rewind)
        emit(text, file=file)
    if ex is not None:
        exc, tb = ex.__class__, ex.__traceback__
        lines = [_.rstrip("\n") for _ in traceback.format_exception(exc, ex, tb)]
        emit("\n".join(lines) + "\n", file=sys.stderr)


def emit(message: str, *, file: TextIO = sys.stdout) -> None:
    file.write(message)
    file.flush()


def trace(message: str, *, file: TextIO = sys.stdout, end: str = "\n") -> None:
    c = level_color(TRACE)
    log(TRACE, message, file=file, prefix="@*%s{==>} " % c, end=end)


def debug(message: str, *, file: TextIO = sys.stdout, end: str = "\n") -> None:
    c = level_color(DEBUG)
    log(DEBUG, message, file=file, prefix="@*%s{==>} " % c, end=end)


def info(message: str, *, file: TextIO = sys.stdout, end: str = "\n") -> None:
    c = level_color(INFO)
    log(INFO, message, file=file, prefix="@*%s{==>} " % c, end=end)


def warning(
    message: str, *, file: TextIO = sys.stderr, end: str = "\n", ex: Exception | None = None
) -> None:
    c = level_color(WARNING)
    log(WARNINGS, message, file=file, prefix="@*%s{==>} Warning: " % c, end=end, ex=ex)


def error(
    message: str, *, file: TextIO = sys.stderr, end: str = "\n", ex: Exception | None = None
) -> None:
    c = level_color(ERROR)
    log(ERROR, message, file=file, prefix="@*%s{==>} Error: " % c, end=end, ex=ex)


def exception(message: str, ex: Exception, *, file: TextIO = sys.stderr, end: str = "\n") -> None:
    c = level_color(ERROR)
    log(ERROR, message, file=file, prefix="@*%s{==>} Error: " % c, end=end, ex=ex)


def fatal(
    message: str, *, file: TextIO = sys.stderr, end: str = "\n", ex: Exception | None = None
) -> None:
    c = level_color(FATAL)
    log(FATAL, message, file=file, prefix="@*%s{==>} Fatal: " % c, end=end, ex=ex)


def progress_bar(
    total: int,
    complete: int,
    elapsed: float,
    average: float | None = None,
    width: int | None = None,
    level: int = ALWAYS,
) -> None:
    """Display test session progress

    Args:
    ----------
    case : Active test cases

    """
    blocks = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    lsep, rsep = "▏", "▕"

    total_width = width or (terminal_size()[1] - 3)

    frac = complete / total
    percent = frac * 100
    eta = None if not complete else round(elapsed * (1.0 - frac) / frac)

    w = len(str(total))
    info = f"  {complete:{w}d}/{total} {percent:5.1f}% ["
    info += f"elapsed: {hhmmss(elapsed, threshold=1)} "
    info += f"eta: {hhmmss(eta, threshold=0)} "
    info += f"ave: {hhmmss(average, threshold=1)}]   "

    bar_width = total_width - len(info)
    v = frac * bar_width
    x = math.floor(v)
    y = v - x
    base = 0.125
    prec = 3
    i = int(round(base * math.floor(float(y) / base), prec) / base)
    bar = "█" * x + blocks[i]
    n = bar_width - len(bar)
    pad = " " * n
    return log(level, f"\r{lsep}{bar}{pad}{rsep}{info}", prefix=None, end="")


def hline(
    label: str | None = None,
    char: str = "-",
    max_width: int = 64,
    file: TextIO = sys.stdout,
    end: str = "\n",
) -> None:
    """Draw a labeled horizontal line.

    Keyword Arguments:
        char (str): Char to draw the line with.  Default '-'
        max_width (int): Maximum width of the line.  Default is 64 chars.
    """
    _, cols = terminal_size()
    if max_width < 0:
        max_width = cols
    cols = min(max_width, cols - 2)

    if label is None:
        file.write(char * max_width)
    else:
        label = str(label)
        prefix = char * 2 + " "
        suffix = " " + (cols - len(prefix) - clen(label)) * char
        file.write(prefix)
        file.write(label)
        file.write(suffix)
        file.write(end)


def fileno(file_or_fd):
    if not hasattr(file_or_fd, "fileno"):
        raise ValueError("Expected a file (`.fileno()`) or a file descriptor")
    return file_or_fd.fileno()


def streamify(arg: TextIO | str, mode: str) -> tuple[IO[Any], bool]:
    if isinstance(arg, str):
        return open(arg, mode), True
    else:
        return arg, False


@contextmanager
def redirect_stdout(
    to: str | IO[Any] = os.devnull, stdout: TextIO | None = None
) -> Generator[TextIO, None, None]:
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
def capture(file_like: str | TextIO, mode: str = "w") -> Generator[None, None, None]:
    if file_like is None:
        yield
    else:
        file, fown = streamify(file_like, mode)
        with redirect_stdout(to=file):
            with merged_stderr_stdout():
                yield
        if fown:
            file.close()


def reset():
    if sys.stdin.isatty():
        fd = sys.stdin.fileno()
        save_tty_attr = termios.tcgetattr(fd)
        termios.tcsetattr(fd, termios.TCSAFLUSH, save_tty_attr)


class context:
    def __init__(self, message: str, *, file: TextIO = sys.stdout, level=INFO) -> None:
        self._start = -1.0
        self.message = message
        self.file = file
        self.level = level
        self.prefix = "@*%s{==>} " % level_color(level)

    def start(self) -> "context":
        self._start = time.monotonic()
        log(self.level, self.message, file=self.file, prefix=self.prefix, end="...")
        return self

    def stop(self):
        end = "... done (%.2fs.)\n" % (time.monotonic() - self._start)
        log(self.level, self.message, file=self.file, prefix=self.prefix, end=end, rewind=True)

    def __enter__(self) -> "context":
        return self.start()

    def __exit__(self, *args) -> None:
        self.stop()
