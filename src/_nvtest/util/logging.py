import datetime
import sys
from io import StringIO
from typing import Optional
from typing import TextIO

from .color import cescape
from .color import clen
from .color import cprint
from .term import terminal_size

TRACE = 0
DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40
FATAL = 50


LEVEL = WARNING
PRINT_TIMESTAMP = False
INDENT = "  "


builtin_print = print


def get_timestamp():
    """Get a string timestamp"""
    if LEVEL <= DEBUG or PRINT_TIMESTAMP:
        return datetime.datetime.now().strftime("[%Y-%m-%d-%H:%M:%S.%f] ")
    else:
        return ""


def set_level(level: int) -> None:
    global LEVEL
    assert level in (TRACE, DEBUG, INFO, WARNING, ERROR, FATAL)
    LEVEL = level


def get_level() -> int:
    return LEVEL


def get_level_name() -> str:
    if LEVEL == TRACE:
        return "TRACE"
    if LEVEL == DEBUG:
        return "DEBUG"
    if LEVEL == INFO:
        return "INFO"
    if LEVEL == WARNING:
        return "WARNING"
    if LEVEL == ERROR:
        return "ERROR"
    if LEVEL == FATAL:
        return "FATAL"
    return "NOTSET"


def format_message(
    message: str,
    color: str = "*b",
    end: str = "\n",
    prefix: Optional[str] = "==>",
) -> str:
    format = "%(timestamp)s%(message)s"
    if prefix is not None:
        format = "@%(color)s{%(prefix)s} " + format
    kwds = {
        "color": color,
        "prefix": prefix,
        "timestamp": get_timestamp(),
        "message": cescape(str(message)),
    }
    text = format % kwds
    stream = StringIO()
    cprint(text, stream=stream, end=end)
    stream.flush()
    return stream.getvalue()


def puts(message: str, *, stream: TextIO = sys.stdout) -> None:
    stream.write(message)
    stream.flush()


def emit(message: str, *, stream: TextIO = sys.stdout, end="\n") -> None:
    text = format_message(message, end=end, prefix=None)
    puts(text, stream=stream)


def trace(
    message: str, *, stream: TextIO = sys.stdout, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > TRACE:
        return
    text = format_message(message, end=end, color="*c", prefix=prefix)
    puts(text, stream=stream)


def debug(
    message: str, *, stream: TextIO = sys.stdout, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > DEBUG:
        return
    text = format_message(message, end=end, color="*g", prefix=prefix)
    puts(text, stream=stream)


def info(
    message: str, *, stream: TextIO = sys.stdout, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > INFO:
        return
    text = format_message(message, end=end, color="*b", prefix=prefix)
    puts(text, stream=stream)


def warning(
    message: str, *, stream: TextIO = sys.stderr, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > ERROR:
        return
    text = format_message(f"Warning: {message}", end=end, color="*Y", prefix=prefix)
    puts(text, stream=stream)


def error(
    message: str, *, stream: TextIO = sys.stderr, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > ERROR:
        return
    text = format_message(f"Error: {message}", end=end, color="*r", prefix=prefix)
    puts(text, stream=stream)


def fatal(
    message: str, *, stream: TextIO = sys.stderr, end="\n", prefix: Optional[str] = "==>"
) -> None:
    if LEVEL > FATAL:
        return
    text = format_message(f"Fatal: {message}", end=end, color="*r", prefix=prefix)
    puts(text, stream=stream)


def hline(label: Optional[str] = None, char: str = "-", max_width: int = 64) -> None:
    """Draw a labeled horizontal line.

    Keyword Arguments:
        char (str): Char to draw the line with.  Default '-'
        max_width (int): Maximum width of the line.  Default is 64 chars.
    """
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
    out.write("\n")
    puts(out.getvalue())


def centered(level: int, text: str, *, stream: TextIO = sys.stdout, char: str = "-") -> None:
    if LEVEL > level:
        return
    _, width = terminal_size()
    dots = "." * clen(text)
    tmp = f" {dots} ".center(width, char)
    puts(tmp.replace(dots, text), stream=stream)
