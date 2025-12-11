# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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
import time
from typing import IO
from typing import Any
from typing import Literal
from typing import cast

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
arrow = "==>"


class FileHandler(builtin_logging.FileHandler): ...


class MuteConsoleFilter(builtin_logging.Filter):
    def filter(self, record):
        # Returning false = block record
        return False


class StreamHandler(builtin_logging.StreamHandler):
    canary_stream = True

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
                prefix = "@*%s{%s} " % (level_color(record.levelno), arrow)
            elif record.levelno in (WARNING, ERROR, CRITICAL):
                prefix = "@*%s{%s} %s: " % (
                    level_color(record.levelno),
                    arrow,
                    record.levelname.title(),
                )
            else:
                prefix = "@*{%s} " % arrow
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
            if record.levelno in (WARNING, ERROR, CRITICAL):
                prefix = f"{arrow} {record.levelname.title()}"
            else:
                prefix = arrow
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


class ProgressMonitor:
    def __init__(self, logger_name: str, message: str) -> None:
        self.message = message
        self.logger_name = logger_name
        self.start = time.monotonic()
        get_logger(self.logger_name).log(INFO, self.message, extra={"end": "..."})

    def done(self, status: str = "done") -> None:
        end = "... %s (%.2fs.)\n" % (status, time.monotonic() - self.start)
        get_logger(self.logger_name).log(INFO, self.message, extra={"end": end, "rewind": True})


class CanaryLogger(builtin_logging.Logger):
    def progress_monitor(self, message: str) -> ProgressMonitor:
        return ProgressMonitor(self.name, message)


builtin_logging.setLoggerClass(CanaryLogger)


def get_logger(name: str | None = None) -> CanaryLogger:
    if name is None:
        name = root_log_name
    parts = name.split(".")
    if parts[0] != root_log_name:
        parts.insert(0, root_log_name)
        name = ".".join(parts)
    logger = cast(CanaryLogger, builtin_logging.getLogger(name))
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


def set_level(level: int | str, only: Literal["stream", "file"] | None = None) -> int | None:
    if only is not None:
        if only not in ("stream", "file"):
            raise ValueError(f"illegal value only={only}, (expected stream or file)")
    if isinstance(level, str):
        levelno = get_levelno(level)
    else:
        levelno = level
    for handler in builtin_logging.getLogger(root_log_name).handlers:
        if only == "stream":
            if isinstance(handler, StreamHandler):
                hold = handler.level
                handler.setLevel(levelno)
                return hold
        elif only == "file":
            if isinstance(handler, FileHandler):
                hold = handler.level
                handler.setLevel(levelno)
                return hold
        else:
            if levelno < handler.level:
                handler.setLevel(levelno)
    return None


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
