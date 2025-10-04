# /Formatter
#  Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import json
import logging as builtin_logging
import math
import os
import sys
import termios
from contextlib import contextmanager
from typing import IO
from typing import Any
from typing import Generator

from ..third_party.color import clen
from ..third_party.color import colorize
from .term import terminal_size
from .time import hhmmss

NOTSET = builtin_logging.NOTSET
TRACE = builtin_logging.DEBUG - 5
DEBUG = builtin_logging.DEBUG
INFO = builtin_logging.INFO
WARNING = builtin_logging.WARNING
ERROR = builtin_logging.ERROR
CRITICAL = builtin_logging.CRITICAL
EMIT = builtin_logging.CRITICAL + 5


builtin_print = print
root_log_name = "canary"


class FileHandler(builtin_logging.FileHandler): ...


class StreamHandler(builtin_logging.StreamHandler):
    def emit(self, record):
        """Emit a record.

        If a formatter is specified, it is used to format the record.  The record is then written
        to the stream with a trailing newline. If exception information is present, it is formatted
        using `traceback.print_exception` and appended to the stream.  If the stream has an
        'encoding' attribute, it is used to determine how to do the output to the stream.
        """
        try:
            formatted_record = self.format(record)
            starter = "\r" if hasattr(record, "rewind") else ""
            terminator = getattr(record, "end", self.terminator)
            self.stream.write(starter + formatted_record + terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


class Formatter(builtin_logging.Formatter):
    def __init__(self, **kwargs):
        fmt = kwargs.pop("fmt", "%(prefix)s%(message)s")
        color = kwargs.pop("color", None)
        assert color in (None, True, False)
        super().__init__(fmt, **kwargs)
        self.color = color

    def format(self, record):
        extra = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f"),
        }
        if not hasattr(record, "prefix"):
            if record.levelno in (TRACE, DEBUG, INFO):
                prefix = "@*%s{==>} " % level_color(record.levelno)
            elif record.levelno in (WARNING, ERROR, CRITICAL):
                prefix = "@*%s{==>} %s: " % (level_color(record.levelno), record.levelname.title())
            else:
                prefix = "@*{==>} "
            extra["prefix"] = prefix

        record.__dict__.update(extra)
        result = super().format(record)
        return colorize(result, color=self.color)


class JsonFormatter(builtin_logging.Formatter):
    def __init__(self, **kwargs):
        fmt = kwargs.pop("fmt", "%(prefix)s%(message)s")
        super().__init__(fmt, **kwargs)

    def format(self, record):
        extra = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f"),
        }
        if not hasattr(record, "prefix"):
            if record.levelno in (TRACE, DEBUG, INFO):
                prefix = "@*%s{==>} " % level_color(record.levelno)
            elif record.levelno in (WARNING, ERROR, CRITICAL):
                prefix = "@*%s{==>} %s: " % (level_color(record.levelno), record.levelname.title())
            else:
                prefix = "@*{==>} "
            extra["prefix"] = prefix
        record.__dict__.update(extra)
        record.message = record.getMessage()
        log_record = {
            "logger": record.name,
            "modulename": record.module,
            "func": record.funcName,
            "file": record.filename,
            "lineno": record.lineno,
            "level": record.levelname,
            "process": record.process,
            "thread": record.thread,
            "time": self.formatTime(record),
            "message": colorize(record.message, color=False),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info).replace("\n", " | ")
        if record.stack_info:
            log_record["stack"] = self.formatStack(record.stack_info).replace("\n", " | ")
        return json.dumps(log_record)


def level_name_mapping() -> dict[int, str]:
    mapping = {
        NOTSET: "NOTSET",
        TRACE: "TRACE",
        DEBUG: "DEBUG",
        INFO: "INFO",
        WARNING: "WARNING",
        ERROR: "ERROR",
        CRITICAL: "CRITICAL",
        EMIT: "EMIT",
    }
    return mapping


def get_logger(name: str | None = None) -> builtin_logging.Logger:
    if name is None:
        name = root_log_name
    parts = name.split(".")
    if parts[0] != root_log_name:
        parts.insert(0, root_log_name)
        name = ".".join(parts)
    logger = builtin_logging.getLogger(name)
    return logger


def get_level_name(levelno: int | None = None) -> str:
    mapping = level_name_mapping()
    return mapping[levelno or get_level()]


def get_levelno(levelname: str) -> int:
    mapping = level_name_mapping()
    for level, name in mapping.items():
        if name == levelname:
            return level
    raise ValueError(f"Invalid logging level name {levelname!r}")


def set_level(level: int | str) -> None:
    if isinstance(level, str):
        levelno = get_levelno(level)
    else:
        levelno = level
    for handler in builtin_logging.getLogger(root_log_name).handlers:
        if levelno < handler.level:
            handler.setLevel(levelno)


def setup_logging() -> None:
    logger = builtin_logging.getLogger(root_log_name)
    builtin_logging.addLevelName(TRACE, "TRACE")
    builtin_logging.addLevelName(EMIT, "EMIT")
    if not logger.handlers:
        sh = StreamHandler(sys.stderr)
        fmt = Formatter(color=sys.stderr.isatty())
        sh.setFormatter(fmt)
        sh.setLevel(INFO)
        # set the logger level higher than the streamhandler to assure that the messages of level
        # INFO will be emmitted.
        logger.addHandler(sh)
        logger.setLevel(TRACE)


def add_file_handler(file: str, levelno: int) -> None:
    logger = builtin_logging.getLogger(root_log_name)
    for handler in logger.handlers:
        if isinstance(handler, FileHandler) and handler.baseFilename == file:
            return
    os.makedirs(os.path.dirname(file), exist_ok=True)
    fh = FileHandler(file, mode="a")
    fmt = JsonFormatter()
    fh.setFormatter(fmt)
    fh.setLevel(levelno)
    logger.addHandler(fh)


def level_color(levelno: int) -> str:
    if levelno == NOTSET:
        return "c"
    elif levelno == TRACE:
        return "m"
    elif levelno == DEBUG:
        return "g"
    elif levelno == INFO:
        return "b"
    elif levelno == WARNING:
        return "Y"
    elif levelno == ERROR:
        return "r"
    elif levelno == CRITICAL:
        return "r"
    elif levelno == EMIT:
        return ""
    raise ValueError(levelno)


def get_level() -> int:
    logger = builtin_logging.getLogger(root_log_name)
    for handler in logger.handlers:
        if isinstance(handler, StreamHandler):
            return handler.level
    return logger.getEffectiveLevel()


def progress_bar(
    total: int,
    complete: int,
    elapsed: float,
    average: float | None = None,
    width: int | None = None,
    level: int = 0,
    file: IO[Any] = sys.stderr,
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
    file.write(f"\r{lsep}{bar}{pad}{rsep}{info}")


def hline(
    label: str | None = None,
    char: str = "-",
    max_width: int = 64,
    file: IO[Any] = sys.stdout,
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


def streamify(arg: IO[Any] | str, mode: str) -> tuple[IO[Any], bool]:
    if isinstance(arg, str):
        return open(arg, mode), True
    else:
        return arg, False


@contextmanager
def redirect_stdout(
    to: str | IO[Any] = os.devnull, stdout: IO[Any] | None = None
) -> Generator[IO[Any], None, None]:
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
def capture(file_like: str | IO[Any], mode: str = "w") -> Generator[None, None, None]:
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
