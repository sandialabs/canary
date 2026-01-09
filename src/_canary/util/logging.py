# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import datetime
import json
import logging as builtin_logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any
from typing import Literal
from typing import cast

from .rich import colorize

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


class MuteConsoleFilter(builtin_logging.Filter):
    def filter(self, record):
        # Returning false = block record
        return False


class QueueHandler(logging.handlers.QueueHandler):
    pass


class QueueListener(logging.handlers.QueueListener):
    pass


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
            if level_color(record.levelno):
                prefix = "[bold %s]%s[/]: " % (
                    level_color(record.levelno),
                    record.levelname.upper(),
                )
            else:
                prefix = f"{record.levelname.upper()}: "
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
            if record.levelno in (NOTSET, TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL):
                prefix = f"{record.levelname.upper()}: "
            else:
                prefix = ""
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
    def __init__(self, logger_name: str, message: str, levelno: int = INFO) -> None:
        self.message = message
        self.logger_name = logger_name
        self.start = time.monotonic()
        self.levelno = levelno
        get_logger(self.logger_name).log(self.levelno, self.message, extra={"end": "..."})

    def done(self, status: str = "done") -> None:
        x = {"end": "... %s (%.2fs.)\n" % (status, time.monotonic() - self.start), "rewind": True}
        get_logger(self.logger_name).log(self.levelno, self.message, extra=x)


class CanaryLogger(builtin_logging.Logger):
    def progress_monitor(self, message: str, levelno: int = INFO) -> ProgressMonitor:
        return ProgressMonitor(self.name, message, levelno)


class AdaptiveDebugLogger:
    """
    Dynamic debug logger that starts chatty and backs off exponentially
    while conditions remain unchanged. Resets immediately on state change.
    """

    def __init__(
        self,
        name: str,
        min_interval: float = 10.0,
        max_interval: float = 120.0,
        growth: float = 1.6,
    ) -> None:
        self.logger_name = name
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.growth = growth

        self._interval = min_interval
        self._last_emit = 0.0
        self._last_signature: tuple[Any, ...] = ()

    def emit(self, signature: tuple[Any, ...], msg: str) -> None:
        now = time.monotonic()

        if signature != self._last_signature:
            self._interval = self.min_interval
            self._last_signature = signature
            self._last_emit = 0.0

        if now - self._last_emit >= self._interval:
            get_logger(self.logger_name).debug(msg)
            self._last_emit = now
            self._interval = min(self._interval * self.growth, self.max_interval)


builtin_logging.setLoggerClass(CanaryLogger)


def get_logger(name: str | None = None) -> CanaryLogger:
    if name is None:
        name = root_log_name
    elif name == "root":
        name = ""
    else:
        parts = name.split(".")
        if parts[0] == "_canary":
            parts[0] = root_log_name
        elif parts[0] != root_log_name:
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
    for handler in builtin_logging.getLogger().handlers:
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
    root = builtin_logging.getLogger()
    root.setLevel(NOTSET)
    builtin_logging.addLevelName(TRACE, "TRACE")
    builtin_logging.addLevelName(EMIT, "EMIT")
    for h in root.handlers:
        if isinstance(h, StreamHandler):
            break
    else:
        sh = stream_handler()
        root.addHandler(sh)
    canary = builtin_logging.getLogger(root_log_name)
    canary.propagate = True


def stream_handler(levelno: int = INFO) -> StreamHandler:
    handler = StreamHandler(sys.stderr)
    fmt = Formatter(color=sys.stderr.isatty())
    handler.setFormatter(fmt)
    handler.setLevel(levelno)
    return handler


def json_file_handler(file: str | Path, levelno: int = NOTSET) -> FileHandler:
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.touch(exist_ok=True)
    handler = FileHandler(file, mode="a")
    fmt = JsonFormatter()
    handler.setFormatter(fmt)
    handler.setLevel(levelno)
    return handler


def add_handler(handler: builtin_logging.Handler) -> None:
    root = builtin_logging.getLogger()
    root.addHandler(handler)


def clear_handlers() -> None:
    root = builtin_logging.getLogger()
    for h in root.handlers[:]:
        try:
            h.flush()
            h.close()
        except Exception:  # nosec B110
            pass
        root.removeHandler(h)


def level_color(levelno: int) -> str:
    if levelno == NOTSET:
        return "cyan"
    elif levelno == TRACE:
        return "magenta"
    elif levelno == DEBUG:
        return "green"
    elif levelno == INFO:
        return "blue"
    elif levelno == WARNING:
        return "bright_yellow"
    elif levelno == ERROR:
        return "red"
    elif levelno == CRITICAL:
        return "red"
    elif levelno == EMIT:
        return ""
    raise ValueError(levelno)


def get_level() -> int:
    logger = builtin_logging.getLogger()
    for handler in logger.handlers:
        if isinstance(handler, StreamHandler):
            return handler.level
    return logger.getEffectiveLevel()


def info(*args, **kwargs):
    get_logger().info(*args, **kwargs)


def warning(*args, **kwargs):
    get_logger().warning(*args, **kwargs)


def error(*args, **kwargs):
    get_logger().error(*args, **kwargs)


def critical(*args, **kwargs):
    get_logger().critical(*args, **kwargs)


def exception(*args, **kwargs):
    get_logger().exception(*args, **kwargs)
