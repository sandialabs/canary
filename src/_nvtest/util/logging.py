import datetime
import os
import sys
import termios
from contextlib import contextmanager
from io import StringIO
from typing import IO
from typing import Any
from typing import Generator
from typing import Optional
from typing import TextIO
from typing import Union

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
ALWAYS = 100


LEVEL = WARNING
TIMESTAMP = False
FORMAT = "%(prefix)s%(timestamp)s%(message)s"


builtin_print = print


def get_timestamp():
    """Get a string timestamp"""
    if LEVEL <= DEBUG or TIMESTAMP:
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


def set_level(level: int) -> None:
    global LEVEL
    assert level in (TRACE, DEBUG, INFO, WARNING, ERROR, FATAL)
    LEVEL = level


def set_format(format: str) -> None:
    global FORMAT
    FORMAT = format


def get_level(name: Optional[str] = None) -> int:
    if name is None:
        return LEVEL
    if name == "TRACE":
        return TRACE
    if name == "DEBUG":
        return DEBUG
    if name == "INFO":
        return INFO
    if name == "WARNING":
        return WARNING
    if name == "ERROR":
        return ERROR
    if name == "FATAL":
        return FATAL
    raise ValueError(name)


def get_level_name(level: int) -> str:
    if level == TRACE:
        return "TRACE"
    if level == DEBUG:
        return "DEBUG"
    if level == INFO:
        return "INFO"
    if level == WARNING:
        return "WARNING"
    if level == ERROR:
        return "ERROR"
    if level == FATAL:
        return "FATAL"
    raise ValueError(level)


def format_message(
    message: str,
    *,
    end: str = "\n",
    prefix: Optional[str] = "==> ",
    format: Optional[str] = None,
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
    cprint(text, stream=file, end=end)
    file.flush()
    return file.getvalue()


def log(
    level: int,
    message: str,
    *,
    file: TextIO = sys.stdout,
    prefix: Optional[str] = "==> ",
    end: str = "\n",
    format: Optional[str] = None,
) -> None:
    if level >= LEVEL:
        text = format_message(message, end=end, prefix=prefix, format=format)
        file.write(text)
        file.flush()


def emit(message: str, *, file: TextIO = sys.stdout, end="\n") -> None:
    log(ALWAYS, message, format="%(message)s", end=end, file=file)


def trace(message: str, *, file: TextIO = sys.stdout, end="\n") -> None:
    log(TRACE, message, file=file, prefix="@*c{==>} ", end=end)


def debug(message: str, *, file: TextIO = sys.stdout, end="\n") -> None:
    log(DEBUG, message, file=file, prefix="@*g{==>} ", end=end)


def info(message: str, *, file: TextIO = sys.stdout, end="\n") -> None:
    log(INFO, message, file=file, prefix="@*b{==>} ", end=end)


def warning(message: str, *, file: TextIO = sys.stderr, end="\n") -> None:
    log(WARNING, message, file=file, prefix="@*Y{==>} Warning: ", end=end)


def error(message: str, *, file: TextIO = sys.stderr, end="\n") -> None:
    log(ERROR, message, file=file, prefix="@*r{==>} Error: ", end=end)


def fatal(message: str, *, file: TextIO = sys.stderr, end="\n") -> None:
    log(FATAL, message, file=file, prefix="@*r{==>} Fatal: ", end=end)


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
    print(out.getvalue())


def fileno(file_or_fd):
    if not hasattr(file_or_fd, "fileno"):
        raise ValueError("Expected a file (`.fileno()`) or a file descriptor")
    return file_or_fd.fileno()


def streamify(arg: Union[TextIO, str], mode: str) -> tuple[IO[Any], bool]:
    if isinstance(arg, str):
        return open(arg, mode), True
    else:
        return arg, False


@contextmanager
def redirect_stdout(
    to: Union[str, IO[Any]] = os.devnull, stdout: Optional[TextIO] = None
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
def capture(file_like: Union[str, TextIO], mode: str = "w") -> Generator[None, None, None]:
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
