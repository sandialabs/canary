import contextlib
import errno
import os
import re
import signal
import time
from datetime import datetime
from datetime import timezone
from typing import Callable
from typing import Optional
from typing import Union

DEFAULT_TIMEOUT_MESSAGE = os.strerror(errno.ETIME)


def strftimestamp(timestamp: float, fmt: str = "%b %d %H:%M") -> str:
    s = datetime.fromtimestamp(timestamp).strftime(fmt)
    s += f" {time.tzname[1]}"
    return s


def timestamp(local: bool = True) -> float:
    return time.mktime(time.localtime()) if local else time.time()


def is_float(arg: str) -> bool:
    try:
        float(arg)
        return True
    except ValueError:
        return False


def is_hhmmss(arg: str) -> bool:
    return bool(re.search("^\d{1,2}:\d{1,2}:\d{1,2}$", arg))


def is_mmss(arg: str) -> bool:
    return bool(re.search("^\d{1,2}:\d{1,2}$", arg))


def dhms_to_s(day: int = 0, hour: int = 0, minute: int = 0, second: int = 0) -> int:
    return 24 * 60 * 60 * day + 60 * 60 * hour + 60 * minute + 1 * second


def hhmmss_to_s(arg: str) -> int:
    parts = [int(_) for _ in arg.split(":")]
    kwds = dict(zip(["second", "minute", "day"], parts[::-1]))
    return dhms_to_s(**kwds)


def time_in_seconds(
    arg: Union[str, int, float], round: bool = False, negatives: bool = False
) -> Union[int, float]:
    """Parse a string to num seconds. The string can be an integer or floating
    point number, or format HH:MM:SS, or 3d 10h 26m 10s. A value of None just
    returns None.

    :round: True means make the value an integer if parsed as a float
    :negatives: True means allow negative number of seconds
    """
    if not isinstance(arg, (str, int, float)):
        raise TypeError("expected string or number")
    elif isinstance(arg, (int, float)):
        value = arg
    elif not isinstance(arg, str) or not arg.strip():
        raise InvalidTimeFormat(arg)
    elif arg.isdigit():
        value = int(arg)
    elif is_float(arg):
        value = float(arg)
    elif is_hhmmss(arg):
        value = hhmmss_to_s(arg)
    elif is_mmss(arg):
        value = hhmmss_to_s(arg)
    else:
        try:
            value = _time_in_seconds(arg)
        except Exception:
            raise InvalidTimeFormat(arg) from None
    if value < 0 and not negatives:
        raise ValueError(f"negative seconds from {arg!r}")
    if round:
        value = int(value)
    return value


to_seconds = time_in_seconds


def _time_in_seconds(arg: str) -> Union[int, float]:
    parts = [_.strip() for _ in re.split("[, ]", arg) if _.split()]
    if not parts:
        raise Exception(arg)
    seconds = 0
    units_map = {"d": "day", "h": "hour", "m": "minute", "s": "second"}
    d_tokens = ("days", "day", "d")
    h_tokens = ("hours", "hour", "hr", "h")
    m_tokens = ("minutes", "minute", "mins", "min", "m")
    s_tokens = ("seconds", "second", "secs", "sec", "s")
    t_tokens = d_tokens + h_tokens + m_tokens + s_tokens
    while parts:
        token = parts.pop(0)
        if token.isdigit():
            value = int(token)
            units = parts.pop(0)
        elif is_float(token):
            value = float(token)  # type: ignore
            units = parts.pop(0)
        else:
            for i, char in enumerate(token):
                if not char.isdigit():
                    value = int(token[:i])
                    units = token[i:]
                    break
            else:
                raise ValueError(arg)
        if units not in t_tokens:
            raise ValueError(f"invalid units {units!r}")
        kwds = {units_map[units[0]]: value}
        seconds += dhms_to_s(**kwds)
    return seconds


def hhmmss(seconds: Optional[float], threshold: float = 2.0) -> str:
    if seconds is None:
        return "--:--:--"
    t = datetime.fromtimestamp(seconds)
    utc = datetime.fromtimestamp(seconds, timezone.utc)
    if seconds < threshold:
        return datetime.strftime(utc, "%H:%M:%S.%f")[:-4]
    return datetime.strftime(utc, "%H:%M:%S")


class timeout(contextlib.ContextDecorator):
    def __init__(
        self,
        seconds,
        *,
        timeout_message=DEFAULT_TIMEOUT_MESSAGE,
        suppress_timeout_errors=False,
    ):
        self.seconds = int(seconds)
        self.timeout_message = timeout_message
        self.suppress = bool(suppress_timeout_errors)

    def _timeout_handler(self, signum, frame):
        raise TimeoutError(self.timeout_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self._timeout_handler)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.alarm(0)
        if self.suppress and exc_type is TimeoutError:
            return True


def pretty_seconds_formatter(seconds: Union[int, float]) -> Callable:
    multiplier: float
    unit: str
    if seconds >= 1:
        multiplier, unit = 1, "s"
    elif seconds >= 1e-3:
        multiplier, unit = 1e3, "ms"
    elif seconds >= 1e-6:
        multiplier, unit = 1e6, "us"
    else:
        multiplier, unit = 1e9, "ns"
    return lambda s: "%.3f%s" % (multiplier * s, unit)


def pretty_seconds(seconds: Union[int, float]) -> str:
    """Seconds to string with appropriate units

    Arguments:
        seconds (float): Number of seconds

    Returns:
        str: Time string with units
    """
    return pretty_seconds_formatter(seconds)(seconds)


class InvalidTimeFormat(Exception):
    def __init__(self, fmt):
        super(InvalidTimeFormat, self).__init__(f"invalid time format {fmt!r}")
