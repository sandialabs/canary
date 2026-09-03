# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary logging infrastructure built on top of the standard ``logging`` module.

Extends the stdlib with a ``TRACE`` level, a ``EMIT`` level, color-aware
``StreamHandler``/``Formatter``, a ``JsonFormatter``, ``ProgressMonitor`` for
inline progress reporting, ``AdaptiveDebugLogger`` for back-off debug output,
and helper functions ``get_logger``, ``set_level``, ``setup_logging``, and
context managers ``suppress_stream_below``/``filter_warnings``.
"""

import datetime
import json
import logging as builtin_logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import Generator
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
    """Logging filter that blocks every record (use to silence a handler)."""

    def filter(self, record):
        # Returning false = block record
        return False


class QueueHandler(logging.handlers.QueueHandler):
    """Re-exported ``logging.handlers.QueueHandler`` for canary use."""

    pass


class QueueListener(logging.handlers.QueueListener):
    """Re-exported ``logging.handlers.QueueListener`` for canary use."""

    pass


class StreamHandler(builtin_logging.StreamHandler):
    """Stream handler that supports ``rewind`` and custom ``end`` log-record attributes."""

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
    """Log formatter that applies Rich markup colorization and injects a timestamp."""

    def __init__(self, **kwargs):
        """Initialize the formatter.

        Keyword Args:
            fmt: Log format string (default ``"%(prefix)s%(message)s"``).
            color: Force color on (``True``), off (``False``), or auto (``None``).
        """
        fmt = kwargs.pop("fmt", "%(prefix)s%(message)s")
        color = kwargs.pop("color", None)
        assert color in (None, True, False)
        super().__init__(fmt, **kwargs)
        self.color = color

    def format(self, record):
        """Format a log record, injecting a colored level prefix and timestamp."""
        extra = {"timestamp": datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")}
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
    """Log formatter that emits each record as a single-line JSON object."""

    def __init__(self, **kwargs):
        fmt = kwargs.pop("fmt", "%(prefix)s%(message)s")
        super().__init__(fmt, **kwargs)

    def format(self, record):
        """Serialize a log record to a JSON string."""
        extra = {"timestamp": datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")}
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
    """Return a mapping from canary log level integers to their string names."""
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
    """Inline progress reporter that overwrites the current log line on completion.

    Prints a ``"<message>..."`` line on construction and rewrites it as
    ``"<message>... done (X.XXs.)"`` when ``done()`` is called.

    Attributes:
        message: The progress description shown to the user.
        logger_name: Name of the logger used for output.
        levelno: Log level for the progress messages.
    """

    def __init__(self, logger_name: str, message: str, levelno: int = INFO) -> None:
        self.enabled = os.getenv("CANARY_MAKE_DOCS") is None
        self.message = message
        self.logger_name = logger_name
        self.start = time.monotonic()
        self.levelno = levelno
        end = "..." if self.enabled else "\n"
        get_logger(self.logger_name).log(self.levelno, self.message, extra={"end": end})

    def done(self, status: str = "done") -> None:
        """Overwrite the progress line with a completion message including elapsed time.

        Args:
            status: Short status string to append (default ``"done"``).
        """
        if not self.enabled:
            return
        x = {"end": "... %s (%.2fs.)\n" % (status, time.monotonic() - self.start), "rewind": True}
        get_logger(self.logger_name).log(self.levelno, self.message, extra=x)


class CanaryLogger(builtin_logging.Logger):
    """Logger subclass that adds a ``progress_monitor`` convenience factory."""

    def progress_monitor(self, message: str, levelno: int = INFO) -> ProgressMonitor:
        """Create and immediately start a ``ProgressMonitor`` for this logger.

        Args:
            message: Progress description to display.
            levelno: Log level to use (default ``INFO``).

        Returns:
            A running ``ProgressMonitor`` instance.
        """
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
        """Configure the adaptive logger.

        Args:
            name: Logger name passed to ``get_logger``.
            min_interval: Minimum seconds between emissions (reset on state change).
            max_interval: Maximum seconds between emissions.
            growth: Multiplicative factor applied to the interval after each emit.
        """
        self.logger_name = name
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.growth = growth

        self._interval = min_interval
        self._last_emit = 0.0
        self._last_signature: tuple[Any, ...] = ()

    def emit(self, signature: tuple[Any, ...], msg: str) -> None:
        """Emit a debug message if the back-off interval has elapsed.

        The interval resets to ``min_interval`` whenever ``signature`` changes.

        Args:
            signature: Tuple representing the current state; a change triggers
                an immediate emit and interval reset.
            msg: Debug message to log.
        """
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
    """Return the ``CanaryLogger`` for the given name.

    Names are normalized so that ``_canary.*`` becomes ``canary.*`` and
    unqualified names are rooted under ``canary``.

    Args:
        name: Logger name; ``None`` returns the root canary logger.

    Returns:
        The requested ``CanaryLogger`` instance.
    """
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
    """Return the string name for a log level number.

    Args:
        levelno: Log level integer; defaults to the current stream handler level.

    Returns:
        Level name string (e.g. ``"INFO"``).
    """
    mapping = level_name_mapping()
    return mapping[levelno or get_level()]


def get_levelno(levelname: str) -> int:
    """Return the integer log level for a level name string.

    Args:
        levelname: Level name such as ``"DEBUG"`` or ``"TRACE"``.

    Returns:
        Corresponding integer level.

    Raises:
        ValueError: If ``levelname`` is not recognized.
    """
    mapping = level_name_mapping()
    for level, name in mapping.items():
        if name == levelname:
            return level
    raise ValueError(f"Invalid logging level name {levelname!r}")


def set_level(level: int | str, only: Literal["stream", "file"] | None = None) -> int | None:
    """Set the logging level on active handlers.

    Args:
        level: New level as an integer or level-name string.
        only: Restrict the change to ``"stream"`` or ``"file"`` handlers;
            ``None`` updates all handlers whose current level exceeds ``level``.

    Returns:
        The previous level of the affected handler, or ``None``.
    """
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
    """Initialize the root logger with a ``StreamHandler`` if none is present.

    Sets the root logger to ``NOTSET``, registers ``TRACE`` and ``EMIT`` level
    names, and ensures the ``canary`` logger propagates to the root.
    """
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
    """Create a color-aware ``StreamHandler`` writing to ``sys.stderr``.

    Args:
        levelno: Minimum log level for the handler (default ``INFO``).

    Returns:
        Configured ``StreamHandler`` instance.
    """
    handler = StreamHandler(sys.stderr)
    fmt = Formatter(color=sys.stderr.isatty())
    handler.setFormatter(fmt)
    handler.setLevel(levelno)
    return handler


def json_file_handler(file: str | Path, levelno: int = NOTSET) -> FileHandler:
    """Create a ``FileHandler`` that writes JSON-formatted log records.

    Args:
        file: Path to the log file; parent directories are created as needed.
        levelno: Minimum log level for the handler (default ``NOTSET``).

    Returns:
        Configured ``FileHandler`` instance.
    """
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.touch(exist_ok=True)
    handler = FileHandler(file, mode="a")
    fmt = JsonFormatter()
    handler.setFormatter(fmt)
    handler.setLevel(levelno)
    return handler


def add_handler(handler: builtin_logging.Handler) -> None:
    """Attach ``handler`` to the root logger.

    Args:
        handler: The handler to add.
    """
    root = builtin_logging.getLogger()
    root.addHandler(handler)


def clear_handlers() -> None:
    """Flush, close, and remove all handlers from the root logger."""
    root = builtin_logging.getLogger()
    for h in root.handlers[:]:
        try:
            h.flush()
            h.close()
        except Exception:  # nosec B110
            pass
        root.removeHandler(h)


def level_color(levelno: int) -> str:
    """Return the Rich color name associated with ``levelno``, or ``""`` for EMIT.

    Args:
        levelno: A canary log level integer.

    Returns:
        A Rich color name string.

    Raises:
        ValueError: If ``levelno`` is not a recognized canary level.
    """
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
    """Return the effective log level from the first ``StreamHandler`` on the root logger.

    Falls back to the root logger's ``getEffectiveLevel()`` if no stream handler exists.

    Returns:
        Current effective log level integer.
    """
    logger = builtin_logging.getLogger()
    for handler in logger.handlers:
        if isinstance(handler, StreamHandler):
            return handler.level
    return logger.getEffectiveLevel()


def info(*args, **kwargs):
    """Log an INFO message on the root canary logger."""
    get_logger().info(*args, **kwargs)


def warning(*args, **kwargs):
    """Log a WARNING message on the root canary logger."""
    get_logger().warning(*args, **kwargs)


def error(*args, **kwargs):
    """Log an ERROR message on the root canary logger."""
    get_logger().error(*args, **kwargs)


def critical(*args, **kwargs):
    """Log a CRITICAL message on the root canary logger."""
    get_logger().critical(*args, **kwargs)


def exception(*args, **kwargs):
    """Log an exception (ERROR with traceback) on the root canary logger."""
    get_logger().exception(*args, **kwargs)


@contextmanager
def suppress_stream_below(level: int) -> Generator[None, None, None]:
    """Context manager that raises the stream handler level to ``level`` temporarily.

    Args:
        level: Minimum level to allow through the stream handler while active.
    """
    previous = set_level(level, only="stream")
    try:
        yield
    finally:
        if previous is not None:
            set_level(previous, only="stream")


@contextmanager
def filter_warnings() -> Generator[None, None, None]:
    """Context manager that suppresses all stream output below ERROR level."""
    with suppress_stream_below(ERROR):
        yield
