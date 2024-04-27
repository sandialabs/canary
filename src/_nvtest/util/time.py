import io
import re
import time
import tokenize
from datetime import datetime
from datetime import timezone
from typing import Callable
from typing import Optional
from typing import Union


def strftimestamp(timestamp: float, fmt: str = "%b %d %H:%M") -> str:
    s = datetime.fromtimestamp(timestamp).strftime(fmt)
    s += f" {time.tzname[1]}"
    return s


def timestamp(local: bool = True) -> float:
    return time.mktime(time.localtime()) if local else time.time()


def to_seconds(
    arg: Union[str, int, float], round: bool = False, negatives: bool = False
) -> Union[int, float]:
    if isinstance(arg, (int, float)):
        return arg
    units = {
        "second": 1,
        "minute": 60,  # 60 sec/min * 1 min
        "hour": 3600,  # 60 min/hr * 60 sec/min * 1hr
        "day": 86400,  # 24 hr/day * 60 min/hr * 60 sec/min * 1 day
        "month": 2592000,  # 30 day/mo 24 hr/day * 60 min/hr * 60 sec/min * 1 mo
        "year": 31536000,  # 365 day/yr * 30 day/mo * 24 hr/day * 60 min/hr * 60 sec/min * 1 year
    }
    units["s"] = units["sec"] = units["secs"] = units["seconds"] = units["second"]
    units["m"] = units["min"] = units["mins"] = units["minutes"] = units["minute"]
    units["h"] = units["hr"] = units["hrs"] = units["hours"] = units["hour"]
    units["d"] = units["days"] = units["day"]
    units["mo"] = units["mos"] = units["months"] = units["month"]
    units["y"] = units["yr"] = units["yrs"] = units["years"] = units["year"]

    if re.search("^\d{1,2}:\d{1,2}:\d{1,2}(\.\d+)?$", arg):
        hours, minutes, seconds = [float(_) for _ in arg.split(":")]
        return hours * units["hours"] + minutes * units["minutes"] + seconds * units["seconds"]
    elif re.search("^\d{1,2}:\d{1,2}(\.\d+)?$", arg):
        minutes, seconds = [float(_) for _ in arg.split(":")]
        return minutes * units["minutes"] + seconds * units["seconds"]

    tokens = [
        token
        for token in tokenize.tokenize(io.BytesIO(arg.encode("utf-8")).readline)
        if token.type not in (tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.ENCODING)
    ]
    stack = []
    for token in tokens:
        if token.type == tokenize.OP and token.string == "-":
            stack.append(-1.0)
        elif token.type == tokenize.NUMBER:
            number = float(token.string)
            if stack and stack[-1] == -1.0:
                stack[-1] *= number
            else:
                stack.append(number)
        elif token.type == tokenize.NAME:
            if token.string.lower() in ("and", "plus"):
                continue
            fac = units.get(token.string.lower())
            if fac is None:
                raise InvalidTimeFormat(arg)
            if not stack:
                stack.append(1)
            stack[-1] *= fac
        elif token.type == tokenize.OP and token.string in (".",):
            continue
        else:
            raise InvalidTimeFormat(arg)
    seconds = sum(stack)
    if seconds < 0 and not negatives:
        raise ValueError(f"negative seconds from {arg!r}")
    if round:
        return int(seconds)
    return seconds


time_in_seconds = to_seconds


def hhmmss(seconds: Optional[float], threshold: float = 2.0) -> str:
    if seconds is None:
        return "--:--:--"
    t = datetime.fromtimestamp(seconds)
    utc = datetime.fromtimestamp(seconds, timezone.utc)
    if seconds < threshold:
        return datetime.strftime(utc, "%H:%M:%S.%f")[:-4]
    return datetime.strftime(utc, "%H:%M:%S")


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


def pretty_seconds(seconds: Union[str, int, float]) -> str:
    """Seconds to string with appropriate units

    Arguments:
        seconds (float): Number of seconds

    Returns:
        str: Time string with units
    """
    if isinstance(seconds, str):
        seconds = to_seconds(seconds)
    return pretty_seconds_formatter(seconds)(seconds)


class InvalidTimeFormat(Exception):
    def __init__(self, fmt):
        super().__init__(f"invalid time format: {fmt!r}")
